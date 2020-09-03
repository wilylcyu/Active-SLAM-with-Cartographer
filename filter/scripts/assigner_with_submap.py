#!/usr/bin/env python

# --------Include modules---------------
from copy import copy
import rospy
from visualization_msgs.msg import Marker
from geometry_msgs.msg import Point
from nav_msgs.msg import OccupancyGrid
import tf
from filter.msg import PointArray
from time import time
from numpy import array
from numpy import linalg as LA
from numpy import all as All
from numpy import inf
from functions import robot, informationGain, discount
from numpy.linalg import norm
import numpy as np

# Subscribers' callbacks------------------------------
mapData = OccupancyGrid()
frontiers = []
# global1 = OccupancyGrid()
# global2 = OccupancyGrid()
# global3 = OccupancyGrid()
# globalmaps = []


def callBack(data):
    global frontiers
    frontiers = []
    for point in data.points:
        frontiers.append(array([point.x, point.y]))


def mapCallBack(data):
    global mapData
    mapData = data
# Node----------------------------------------------


def node():
    global frontiers, mapData  # , global1, global2, global3, globalmaps
    rospy.init_node('assigner', anonymous=False)

    # fetching all parameters
    map_topic = rospy.get_param('~map_topic', '/map')
    # this can be smaller than the laser scanner range, >> smaller >>less computation time>> too small is not good, info gain won't be accurate
    info_radius = rospy.get_param('~info_radius', 1.0)
    info_multiplier = rospy.get_param('~info_multiplier', 3.0)
    # at least as much as the laser scanner range
    hysteresis_radius = rospy.get_param('~hysteresis_radius', 3.0)
    # bigger than 1 (biase robot to continue exploring current region
    hysteresis_gain = rospy.get_param('~hysteresis_gain', 2.0)
    frontiers_topic = rospy.get_param('~frontiers_topic', '/filtered_points')
    n_robots = rospy.get_param('~n_robots', 1)
    namespace = rospy.get_param('~namespace', '')
    namespace_init_count = rospy.get_param('namespace_init_count', 1)
    delay_after_assignement = rospy.get_param('~delay_after_assignement', 0.5)
    rateHz = rospy.get_param('~rate', 100)

    rate = rospy.Rate(rateHz)
# -------------------------------------------
    rospy.Subscriber(map_topic, OccupancyGrid, mapCallBack)
    rospy.Subscriber(frontiers_topic, PointArray, callBack)
# ---------------------------------------------------------------------------------------------------------------

# wait if no frontier is received yet
    while len(frontiers) < 1:
        rate.sleep()
        pass
    centroids = copy(frontiers)
# wait if map is not received yet
    while (len(mapData.data) < 1):
        rate.sleep()
        pass
    rospy.loginfo('after check')

    robots = []
    robotsTime = []
    rejectTime = []
    robotsLastPos = []
    robots.append(robot(''))
    robotsTime.append(rospy.Time.now().to_sec())
    rejectTime.append(0)
    robotsLastPos.append(robots[0].getPosition())
    rospy.logerr('robot created')
    for i in range(0, n_robots):
        robots[i].sendGoal(robots[i].getPosition())
    # distance = 0
# -------------------------------------------------------------------------
# ---------------------     Main   Loop     -------------------------------
# -------------------------------------------------------------------------
    while not rospy.is_shutdown():
        centroids = copy(frontiers)
# -------------------------------------------------------------------------
# Get information gain for each frontier point
        infoGain = []
        for ip in range(0, len(centroids)):
            infoGain.append(informationGain(
                mapData, [centroids[ip][0], centroids[ip][1]], info_radius))
# -------------------------------------------------------------------------
# get number of available/busy robots
        na = []  # available robots
        nb = []  # busy robots
        for i in range(0, n_robots):
            if (robots[i].getState() == 1):
                nb.append(i)
            else:
                na.append(i)
        rospy.loginfo("available robots: "+str(na))
# -------------------------------------------------------------------------
# get dicount and update informationGain
        for i in nb+na:
            infoGain = discount(
                mapData, robots[i].assigned_point, centroids, infoGain, info_radius)
# -------------------------------------------------------------------------
        revenue_record = []
        centroid_record = []
        id_record = []

        now = rospy.Time.now().to_sec()
        # distance = norm(robotsLastPos[0] - robots[0].getPosition())
        # robotsLastPos[0] = robots[0].getPosition()
        for ir in na:
            rospy.loginfo('arrive')
            for ip in range(0, len(centroids)):
                cost = norm(robots[ir].getPosition()-centroids[ip])
                threshold = 1
                information_gain = infoGain[ip]
                if (norm(robots[ir].getPosition()-centroids[ip]) <= hysteresis_radius):

                    information_gain *= hysteresis_gain
                revenue = information_gain*info_multiplier-cost
                revenue_record.append(revenue)
                centroid_record.append(centroids[ip])
                id_record.append(ir)
            robotsTime[ir] = now
            robotsLastPos[ir] = robots[i].getPosition()
            # distance = 0
            # rejectTime[ir] = 0

        # # try doing sth. to get away from unaccessable point
        # if len(na) < 1:
        #     revenue_record = []
        #     centroid_record = []
        #     id_record = []
        #     for ir in nb:
        #         for ip in range(0, len(centroids)):
        #             cost = norm(robots[ir].getPosition()-centroids[ip])
        #             threshold = 1
        #             information_gain = infoGain[ip]
        #             if (norm(robots[ir].getPosition()-centroids[ip]) <= hysteresis_radius):
        #                 information_gain *= hysteresis_gain

        #             if ((norm(centroids[ip]-robots[ir].assigned_point)) < hysteresis_radius):
        #                 information_gain = informationGain(
        #                     mapData, [centroids[ip][0], centroids[ip][1]], info_radius)*hysteresis_gain

        #             revenue = information_gain*info_multiplier-cost
        #             revenue_record.append(revenue)
        #             centroid_record.append(centroids[ip])
        #             id_record.append(ir)
        if len(na) < 1:
            now = rospy.Time.now().to_sec()
            for ir in nb:
                doReset = False
                if now - robotsTime[ir] > 10:
                    robotsTime[ir] = now
                    if norm(robotsLastPos[ir] - robots[ir].getPosition()) < 0.2: # too less move
                        rospy.logwarn('reset goal... time:%lf' % (now))
                        # distance = 0
                        robotsTime[ir] = now
                        robotsLastPos[ir] = robots[i].getPosition()
                        doReset = True
                if robots[ir].getState() == 5:
                    if rejectTime[ir] == 0:
                        rejectTime = now
                    elif now - rejectTime[ir] > 1.5:
                        doReset = True
                        rejectTime[ir] = 0
                # if doReset:
                for ip in range(0, len(centroids)):
                    cost = norm(robots[ir].getPosition()-centroids[ip])
                    threshold = 1
                    information_gain = -infoGain[ip]
                    if (norm(robots[ir].getPosition()-centroids[ip]) <= hysteresis_radius):
                        information_gain *= -hysteresis_gain

                    if ((norm(centroids[ip]-robots[ir].assigned_point)) < hysteresis_radius):
                        information_gain = -informationGain(
                           mapData, [centroids[ip][0], centroids[ip][1]], info_radius)*hysteresis_gain
                    
                        # do reset
                        # if doReset:
                        # information_gain = -information_gain # kill current goal
                            # should I cancel old goal ?
                        # else:
                        #     information_gain = np.inf # fobid reset (if the old goal already accessable)
                    
                    revenue = information_gain*info_multiplier-cost
                    if information_gain < 0:
                        if doReset:
                            revenue = 0 - cost
                        else:
                            revenue = - information_gain*info_multiplier - cost
                    revenue_record.append(revenue)
                    centroid_record.append(centroids[ip])
                    id_record.append(ir)

        # rospy.loginfo("revenue record: "+str(revenue_record))
        # rospy.loginfo("centroid record: "+str(centroid_record))
        # rospy.loginfo("robot IDs record: "+str(id_record))

# -------------------------------------------------------------------------
        if (len(id_record) > 0):
            winner_id = revenue_record.index(max(revenue_record))
            robots[id_record[winner_id]].sendGoal(centroid_record[winner_id])
            rospy.loginfo(namespace+str(namespace_init_count +
                                        id_record[winner_id])+"  assigned to  "+str(centroid_record[winner_id]))
            rospy.sleep(delay_after_assignement)
# -------------------------------------------------------------------------
        rate.sleep()
# -------------------------------------------------------------------------


if __name__ == '__main__':
    try:
        node()
    except rospy.ROSInterruptException:
        pass

