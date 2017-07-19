# -*- coding: utf-8 -*-

"""
Fichier pour recevoir des donnees PMU en temps reel et sortir des trames Json d'indicateurs
UPDATE 0405: intégration flux udp
UPDATE 0405: Ajout docstrings
UPDATE 0505: fichier parcours au format définitif et nouveau traitement ligne départ 
UPDATE 1005: intégration des flux sur le stream UDP
UPDATE 1105: prise en compte départ et arrivee, cut des données à l'arrivee
UPDATE 1205: prise en compte de la distance de la deuxieme corde selon le parcours
UPDATE 1605: traitement du signal de départ (règle des 20s)
UPDATE 1705: envoie de messages sur les états du moteur
UPDATE 1705: traitement parcours: création de fichiers de données interpolées
UPDATE 1805: amélioration gestion départ
UPDATE 1905: reception commandes parcours en 2 temps
UPDATE 2205: traitement irrégularités de parcours
UPDATE 2305: correction format tmes, ts 
UPDATE 2305: correction format temps de réaction
UPDATE 2405: utilisation de paths compatible tout environnement pour les parcours (bug / vs \)
UPDATE 2405: reinit de FIN_COURSE, DEPART_COURSE, RESTART quand on passe en veille
UPDATE 2405: correction bugs handicaps
UPDATE 2905: précision filtre Kalman
UPDATE 3005: format FFV15 (sans Qmod)
UPDATE 3105: calcul Qmod
UPDATE 3105: nouvelle gestion depart
UPDATE 0206: ajout résultat test Kalman sur fichier générés
UPDATE 0706: corrections du au test voiture:
UPDATE 0906: gestion des pb de précision: règle que si trop peu précis pendant trop de temps, on n'émet plus de json.
UPDATE 2106: nouvelle détection départ
UPDATE 2306: nouvelle gestion arrivee
UPDATE 2806: amélioration init
UPDATE 2806: persistence
UPDATE 2806: threads
UPDATE 2906: ajout stock
UPDATE 0507: covariances décroissantes
"""

import os
import socket
import time
import datetime
import pause
import numpy as np
import pandas as pd
import json
from scipy.interpolate import interp1d
import threading
import logging
import math
from logging.handlers import RotatingFileHandler
import csv
import matplotlib.pyplot as plt


def traitement_parcours(path_parcours, params): #hote , port_sender, sender_udp):
    """
    Fonction qui traite le fichier de parcours avant la course
    On enregistre les données de sortie dans 2 fichiers : interpolation.csv et info.json
    !!!!!! ATTENTION: cette fonction utilise "interp1d" du package scipy, dure à transcrire dans d'autres langages

     :param file_parcours: path du fichier de parcours
     :param params: objet Parametres contenant les paramètres
    """

    msg_udp = "DebutParcours #"
    print msg_udp
    logging.info(msg_udp)
    #sender_udp.sendto(msg_udp, (hote, port_sender))

    # file_info = path_parcours + str("/info.json")
    file_info = os.path.join(path_parcours, "info.json")
    # file_interpolation = path_parcours + str("\interpolation.csv")
    file_interpolation = os.path.join(path_parcours, "interpolation.csv")

    ## Si le fichier d'info sur le parcours existe déjà, on le supprime
    if os.path.isfile(file_info):
        try:
            os.remove(file_info)
            msg_udp = "EvtMoteur: fichier " + str(file_info) + " supprime#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
        except:
            msg_udp = "ErreurParcours: impossible de supprimer " + str(file_info) + "#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError("impossible de supprimer le fichier info deja existant")

    ## Si le fichier d'interpolation du parcours existe déjà, on le supprime
    if os.path.isfile(file_interpolation):
        try:
            os.remove(file_interpolation)
            msg_udp = "EvtMoteur: fichier " + str(file_interpolation) + " supprime#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
        except:
            msg_udp = "ErreurParcours: impossible de supprimer " + str(file_info) + "#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError("impossible de supprimer le fichier interpolation déjà existant")

    ## tentative de charger le csv de parcours
    try:
        # file_parcours = path_parcours + "/parcours.csv"
        file_parcours = os.path.join(path_parcours, "parcours.csv")
        parcours = pd.read_csv(file_parcours, delimiter=";")
        parcours = np.array(parcours)
        PC = np.array(parcours[:, 7])
        msg_udp = "EvtMoteur: traitement parcours fichier ouvert#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
    except:
        msg_udp = "ErreurParcours: impossible de charger le fichier de parcours " + str(file_parcours) + "#"
        print msg_udp
        logging.error(msg_udp, exc_info=True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        raise ValueError('erreur chargement du fichier de parcours (format attendu: séparateur , et décimales .)')

    try:
        ## On vérifie qu'il figure une porte PCDEP dans le parcours
        try:
            ind_dep = np.where(PC == "PCDEP")
        except:
            msg_udp = "ErreurParcours: pas de porte PCDEP dans le fichier de parcours#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError('pas de porte de départ trouvée dans le fichier de parcours')
        if np.size(ind_dep) == 0:
            msg_udp = "ErreurParcours: pas de porte PCDEP dans le fichier de parcours#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError('pas de porte de départ trouvée dans le fichier de parcours')

        ## On vérifie qu'il figure une porte PCARR dans le parcours
        try:
            ind_arr = np.where(PC == "PCARR")
        except:
            msg_udp = "ErreurParcours: pas de porte PCARR dans le fichier de parcours#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError('pas de porte darrivée trouvée dans le fichier de parcours')
        if np.size(ind_arr) == 0:
            msg_udp = "ErreurParcours: pas de porte PCARR dans le fichier de parcours#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            raise ValueError('pas de porte darrivée trouvée dans le fichier de parcours')

        ## On cherche les portes de handicap
        ind_dep_handicap = []
        for i in range(0, np.size(PC)):
            if 'PCDEP' in str(PC[i]) and str(PC[i]) != 'PCDEP':
                ind_dep_handicap.append(i)
        ind_dep = int(ind_dep[0])
        ind_arr = int(ind_arr[0])

        ## On remet les datas parcours dans l'ordre
        if ind_dep > ind_arr:  # on remet les points dans l'ordre
            if ind_dep_handicap:
                max_ind_dep = np.maximum(ind_dep, np.max(ind_dep_handicap))
            else:
                max_ind_dep = ind_dep

            ind_dep_handicap = np.insert(ind_dep_handicap, 0, ind_dep)
            ind_dep_handicap = max_ind_dep - ind_dep_handicap
            indices = np.array(range(max_ind_dep, ind_arr - 1, -1))
            parcours = parcours[indices, :]
        else:
            if ind_dep_handicap:
                min_ind_dep = np.minimum(ind_dep, np.min(ind_dep_handicap))
            else:
                min_ind_dep = ind_dep
            ind_dep_handicap = np.insert(ind_dep_handicap, 0, int(ind_dep))
            ind_dep_handicap = ind_dep_handicap - min_ind_dep
            parcours = parcours[min_ind_dep:ind_arr + 1, :]

        DIST_corde = np.array(parcours[:, 0])
        LAT_corde = np.array(parcours[:, 1])
        LONG_corde = np.array(parcours[:, 2])
        LAT_corde_2 = np.array(parcours[:, 3])
        LONG_corde_2 = np.array(parcours[:, 4])
        LAT_corde_ext = np.array(parcours[:, 5])
        LONG_corde_ext = np.array(parcours[:, 6])
        PC = np.array(parcours[:, 7])

        # Calcul des distances de course pour chaque porte handicap
        if np.size(ind_dep_handicap) > 1:
            val_dep_handicap = np.array(DIST_corde[ind_dep_handicap])
            val_dep_handicap = val_dep_handicap - val_dep_handicap[0]
            dist_course_handicap = np.zeros(np.size(val_dep_handicap) - 1)
            for k in range(0, np.size(dist_course_handicap)):
                if PC[int(ind_dep_handicap[k + 1])] == 'PCDEP50':
                    dist = DIST_corde[ind_dep_handicap[0]] - 0.5
                else:
                    dist = int(PC[ind_dep_handicap[k + 1]][5:])
                dist_course_handicap[k] = dist
            dist_course_handicap = np.insert(dist_course_handicap, 0, DIST_corde[ind_dep_handicap[0]])
            porte_dep_handicap = PC[ind_dep_handicap]
        else:
            val_dep_handicap = np.array(DIST_corde[int(ind_dep_handicap)])
            dist_course_handicap = DIST_corde[int(ind_dep_handicap)]
            porte_dep_handicap = PC[int(ind_dep_handicap)]

        #### Calcul du centre de la piste
        centre_lat = (np.max(LAT_corde_2) + np.min(LAT_corde_2)) / 2
        centre_long = (np.max(LONG_corde_2) + np.min(LONG_corde_2)) / 2

        #### Conversion en coordonnees cartesiennes
        X_corde_2 = []
        Y_corde_2 = []
        X_corde_ext_2 = []
        Y_corde_ext_2 = []
        X_corde = []
        Y_corde = []

        ## Données de verification pour les warnings
        check_distance = [0]
        check_alignement = [0]
        check_sens = [0, 0]
        check_sens_int_ext = [0]
        largeur_max = 0

        msg_udp = "EvtMoteur: conversion des donnees GPS en coordonnees cartesiennes#"
        print msg_udp
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        logging.info(msg_udp)
        for t in range(0, LAT_corde_2.size):
            x_int = lat_to_m(LAT_corde[t] - centre_lat, centre_lat)
            y_int = lon_to_m(LONG_corde[t] - centre_long, centre_lat)
            X_corde.append(x_int)
            Y_corde.append(y_int)
            x = lat_to_m(LAT_corde_2[t] - centre_lat, centre_lat)
            y = lon_to_m(LONG_corde_2[t] - centre_long, centre_lat)
            X_corde_2.append(x)
            Y_corde_2.append(y)
            x_ext = lat_to_m(LAT_corde_ext[t] - centre_lat, centre_lat)
            y_ext = lon_to_m(LONG_corde_ext[t] - centre_long, centre_lat)
            X_corde_ext_2.append(x_ext)
            Y_corde_ext_2.append(y_ext)
            dist_ext = np.sqrt(np.square(x_int - x_ext) + np.square(y_int - y_ext))
            if t > 0:
                norm_int = np.sqrt(np.square(X_corde[-1] - X_corde[-2]) + np.square(Y_corde[-1] - Y_corde[-2]))
                if norm_int > 0:
                    diff_x = (X_corde[-1] - X_corde[-2]) / norm_int
                    diff_y = (Y_corde[-1] - Y_corde[-2]) / norm_int
                else:
                    diff_x = 0
                    diff_y = 0

                norm_ext = np.sqrt(
                    np.square(X_corde_ext_2[-1] - X_corde_ext_2[-2]) + np.square(Y_corde_ext_2[-1] - Y_corde_ext_2[-2]))
                if norm_ext > 0:
                    diff_x_ext = (X_corde_ext_2[-1] - X_corde_ext_2[-2]) / norm_ext
                    diff_y_ext = (Y_corde_ext_2[-1] - Y_corde_ext_2[-2]) / norm_ext
                else:
                    diff_x_ext = 0
                    diff_y_ext = 0
                scal_int_ext = diff_x * diff_x_ext + diff_y * diff_y_ext
            else:
                scal_int_ext = 0
            if scal_int_ext > 0.95:
                if dist_ext > largeur_max:
                    largeur_max = dist_ext

            # Check distance
            if t > 0:
                dist_int = np.sqrt(np.square(X_corde[t] - X_corde[t - 1]) + np.square(Y_corde[t] - Y_corde[t - 1]))
                dist_th = np.abs(DIST_corde[t] - DIST_corde[t - 1])
                if abs(dist_int - dist_th) / dist_th > 0.05:
                    check_distance.append(1)
                    print dist_int, dist_th
                else:
                    check_distance.append(0)
                if scal_int_ext > 0 and scal_int_ext < 0.5:
                    check_alignement.append(1)
                else:
                    check_alignement.append(0)
                if scal_int_ext <= 0:
                    check_sens_int_ext.append(1)
                else:
                    check_sens_int_ext.append(0)

            if t > 1:
                dir = (X_corde[-1] - X_corde[-2]) * (X_corde[-2] - X_corde[-3]) + \
                      (Y_corde[-1] - Y_corde[-2]) * (Y_corde[-2] - Y_corde[-3])
                if dir > 0:
                    check_sens.append(0)
                else:
                    check_sens.append(1)

        if np.sum(check_distance) > 5:
            msg_udp = "WarningParcours: distance au parcours, " + str(np.sum(check_distance)) + " points sont imprecis#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            logging.info(msg_udp)

        if np.sum(check_alignement) > 0:
            msg_udp = "WarningParcours: alignement interieur / exterieur, " + str(
                np.sum(check_alignement)) + " points sont imprecis#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            logging.info(msg_udp)

        if np.sum(check_sens) > 0:
            msg_udp = "WarningParcours: avancement corde interieure, " + str(
                np.sum(check_sens)) + " points vont dans le mauvais sens#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            logging.info(msg_udp)

        if np.sum(check_sens_int_ext) > 0:
            msg_udp = "WarningParcours: corde interieure / exterieure vont dans les sens opposes " + str(
                np.sum(check_sens_int_ext)) + " fois#"
            print msg_udp
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            logging.info(msg_udp)

        print "largeur max ", largeur_max
        if largeur_max == 0:
            msg_udp = "ErreurParcours: corde exterieure et corde intérieure pas suffisamment coherentes#"
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            print msg_udp
            logging.error(msg_udp)
            raise ValueError('cordes exterieures et interieures non cohérents')

        X_corde = np.array(X_corde)
        Y_corde = np.array(Y_corde)
        X_corde_2 = np.array(X_corde_2)
        Y_corde_2 = np.array(Y_corde_2)
        X_corde_ext_2 = np.array(X_corde_ext_2)
        Y_corde_ext_2 = np.array(Y_corde_ext_2)
        dD_corde_inter = float(10) / float(params.res_interp)  # increment de distance dans le parcours interpole
        # construction corde extérieure
        X_corde_ext = []
        Y_corde_ext = []
        lat_corde_ext = []
        long_corde_ext = []
        for t in range(0, np.size(X_corde)):
            x = X_corde[t]
            y = Y_corde[t]
            x_ext = X_corde_ext_2[t]
            y_ext = Y_corde_ext_2[t]
            norm = np.sqrt(np.square(x - x_ext) + np.square(y - y_ext))
            if norm > 0:
                X_corde_ext.append(x + float(x_ext - x) * float(largeur_max) / float(norm))
                Y_corde_ext.append(y + float(y_ext - y) * float(largeur_max) / float(norm))
            else:
                X_corde_ext.append(x_ext)
                Y_corde_ext.append(y_ext)
            lat_corde_ext.append(m_to_lat(X_corde_ext[-1], centre_lat) + centre_lat)
            long_corde_ext.append(m_to_lon(Y_corde_ext[-1], centre_lat) + centre_long)

        X_corde_ext = np.array(X_corde_ext)
        Y_corde_ext = np.array(Y_corde_ext)

        DIST_corde = (DIST_corde[0] - DIST_corde)
        DIST_corde = DIST_corde.astype(float)

        #### Interpolation
        msg_udp = "EvtMoteur: debut interpolation#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        corde_interpol_x = []
        corde_interpol_y = []
        corde_2_interpol_x = []
        corde_2_interpol_y = []
        corde_ext_interpol_x = []
        corde_ext_interpol_y = []

        step_10pourc = int(np.float(X_corde_2.size - params.N_interp - params.N_interp) / np.float(10))

        for t in range(params.N_interp, X_corde_2.size - params.N_interp + 1):
            if t % step_10pourc == 0:
                msg_udp = "PourcParcours: progression interpolation " + str(
                    np.float(t) / np.float(step_10pourc) * 10) + "#"
                print msg_udp
                logging.info(msg_udp)

            scale_orig = np.array(DIST_corde[t - params.N_interp: t + params.N_interp])  # range(0, 2 * params.N_interp)
            debut_interp = np.float(DIST_corde[t])
            fin_interp = np.float(DIST_corde[t + 1])
            scale_res = np.array(range(0, params.res_interp)) * np.float(fin_interp - debut_interp) / np.float(
                params.res_interp) + np.float(debut_interp)
            # np.array(range(0, params.res_interp)) / np.float(params.res_interp) + params.N_interp - 1

            if t == params.N_interp:
                debut_interp = np.float(DIST_corde[0])
                fin_interp = np.float(DIST_corde[params.N_interp + 1])
                scale_res = np.array(range(0, params.res_interp * (params.N_interp + 1))) * np.float(
                    fin_interp - debut_interp) / (
                                np.float(params.res_interp) * np.float(params.N_interp + 1)) + np.float(debut_interp)
                # scale_res = np.array(range(0, params.res_interp * params.N_interp)) / np.float(params.res_interp)
            elif t == X_corde_2.size - params.N_interp:
                debut_interp = np.float(DIST_corde[X_corde_2.size - params.N_interp])
                fin_interp = np.float(DIST_corde[-1])
                scale_res = np.array(range(0, params.res_interp * (params.N_interp))) * np.float(
                    fin_interp + 1 - debut_interp) / (
                                np.float(params.res_interp) * np.float(params.N_interp)) + np.float(debut_interp)
                # scale_res = np.array(range(0, params.res_interp * params.N_interp + 1)) / np.float(
                #    params.res_interp) + params.N_interp -1

            #### Corde
            points_x = X_corde[t - params.N_interp: t + params.N_interp]
            points_y = Y_corde[t - params.N_interp: t + params.N_interp]
            if t == X_corde_2.size - params.N_interp:
                f2x = interp1d(scale_orig, points_x, fill_value = 'extrapolate')
            else:
                f2x = interp1d(scale_orig, points_x, kind='cubic')
            points_x_res = f2x(scale_res)
            corde_interpol_x = np.append(corde_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                f2y = interp1d(scale_orig, points_y, kind='cubic')
            points_y_res = f2y(scale_res)
            corde_interpol_y = np.append(corde_interpol_y, points_y_res)

            #### Corde (a 2 metres)
            points_x = X_corde_2[t - params.N_interp: t + params.N_interp]
            points_y = Y_corde_2[t - params.N_interp: t + params.N_interp]

            if t == X_corde_2.size - params.N_interp:
                f2x = interp1d(scale_orig, points_x, fill_value = 'extrapolate')
            else:
                f2x = interp1d(scale_orig, points_x, kind='cubic')
            points_x_res = f2x(scale_res)
            corde_2_interpol_x = np.append(corde_2_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                f2y = interp1d(scale_orig, points_y, kind='cubic')
            points_y_res = f2y(scale_res)
            corde_2_interpol_y = np.append(corde_2_interpol_y, points_y_res)

            #### Corde exterieure
            points_x = X_corde_ext[t - params.N_interp: t + params.N_interp]
            points_y = Y_corde_ext[t - params.N_interp: t + params.N_interp]

            if t == X_corde_2.size - params.N_interp:
                f2x = interp1d(scale_orig, points_x, fill_value = 'extrapolate')
            else:
                f2x = interp1d(scale_orig, points_x, kind='cubic')
            points_x_res = f2x(scale_res)
            corde_ext_interpol_x = np.append(corde_ext_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                f2y = interp1d(scale_orig, points_y, kind='cubic')
            points_y_res = f2y(scale_res)
            corde_ext_interpol_y = np.append(corde_ext_interpol_y, points_y_res)

        msg_udp = "EvtMoteur: fin interpolation#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        msg_udp = "EvtMoteur: calcul des caracteristiques de portes#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        indice_portes = []
        id_portes = []

        ind_deb = 0
        ind_fin = 0

        # indices auxquels se trouveront les portes dans l'interpolation
        for p in range(0, np.size(PC)):
            if not PC[p] == '0':
                indice_portes = np.append(indice_portes, p * params.res_interp - 1)
                id_portes = id_portes + [PC[p]]
                if PC[p] == 'PCDEP':
                    ind_deb = p
                if PC[p] == 'PCARR':
                    ind_fin = p

        # Update 0305 : distance totale sur la corde 2
        # dist_totale_parcours = 10 * (ind_fin - ind_deb)
        print id_portes
        print indice_portes
        print np.size(corde_interpol_x)
        indices_dep_handicap = ind_dep_handicap * params.res_interp

        msg_udp = "EvtMoteur: calcul des limites de la recherche du départ#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        #### recherche des limites de la recherche du départ
        if np.size(ind_dep_handicap) > 1:
            indice_10 = np.zeros(np.size(ind_dep_handicap))
            indice_500 = np.zeros(np.size(ind_dep_handicap))
            trouve_10 = [False] * np.size(ind_dep_handicap)
            trouve_500 = [False] * np.size(ind_dep_handicap)
            for i in range(0, np.size(DIST_corde)):
                for k in range(0, np.size(indice_10)):
                    if DIST_corde[i] > (
                            (DIST_corde[-1] - dist_course_handicap[k]) + DIST_corde[int(ind_dep_handicap[0])] + 9) \
                            and not trouve_10[k]:
                        indice_10[k] = i
                        trouve_10[k] = True
                    if DIST_corde[i] > (
                            (DIST_corde[-1] - dist_course_handicap[k]) + DIST_corde[int(ind_dep_handicap[0])] + 500) \
                            and not trouve_500[k]:
                        indice_500[k] = i
                        trouve_500[k] = True

            for k in range(np.size(indice_10)):
                if not trouve_500[k]:
                    indice_500[k] = np.size(DIST_corde) - 1
                if not trouve_10[k]:
                    indice_10[k] = np.size(DIST_corde) - 1
        else:
            indice_10 = 0
            indice_500 = 0
            trouve_10 = 0
            trouve_500 = 0
            for i in range(0, np.size(DIST_corde)):
                if DIST_corde[i] > (
                        (DIST_corde[-1] - dist_course_handicap) + DIST_corde[int(indices_dep_handicap[0])] + 9)\
                        and not trouve_10:
                    indice_10 = i
                    trouve_10 = True
                if DIST_corde[i] > (
                        (DIST_corde[-1] - dist_course_handicap) + DIST_corde[int(indices_dep_handicap[0])] + 500)\
                        and not trouve_500:
                    indice_500 = i
                    trouve_500 = True

            if not trouve_500:
                indice_500 = np.size(DIST_corde) - 1
            if not trouve_10:
                indice_10 = np.size(DIST_corde) - 1
        print indice_10, indice_500, trouve_10, trouve_500

        ### calcul des paramètres de la porte de départ
        """
        portes_depart_handicap = [{}] * np.size(ind_dep_handicap)
        if np.size(val_dep_handicap) > 1:
            for k in range(0, np.size(ind_dep_handicap)):
                porte_depart = {}
                porte_depart["corde"] = [X_corde[ind_dep_handicap[k]], Y_corde[ind_dep_handicap[k]]]
                porte_depart["corde_2"] = [X_corde_2[ind_dep_handicap[k]], Y_corde_2[ind_dep_handicap[k]]]
                porte_depart["corde_ext"] = [X_corde_ext[ind_dep_handicap[k]], Y_corde_ext[ind_dep_handicap[k]]]
                dep_dirx = corde_interpol_x[indices_dep_handicap[k] + 300] - corde_interpol_x[indices_dep_handicap[k]]
                dep_diry = corde_interpol_y[indices_dep_handicap[k] + 300] - corde_interpol_y[indices_dep_handicap[k]]
                norm_dep = np.sqrt(np.square(dep_dirx) + np.square(dep_diry))
                porte_depart["direction"] = [np.float(dep_dirx) / np.float(norm_dep),
                                             np.float(dep_diry) / np.float(norm_dep)]
                porte_depart["largeur"] = np.sqrt(
                    np.square(X_corde[ind_dep_handicap[k]] - X_corde_ext[ind_dep_handicap[k]]) +
                    np.square(Y_corde[ind_dep_handicap[k]] - Y_corde_ext[ind_dep_handicap[k]]))
                portes_depart_handicap[k] = porte_depart
        else:
            porte_depart = {}
            porte_depart["corde"] = [X_corde[int(ind_dep_handicap)], Y_corde[int(ind_dep_handicap)]]
            porte_depart["corde_2"] = [X_corde_2[int(ind_dep_handicap)], Y_corde_2[int(ind_dep_handicap)]]
            porte_depart["corde_ext"] = [X_corde_ext[int(ind_dep_handicap)], Y_corde_ext[int(ind_dep_handicap)]]
            dep_dirx = corde_interpol_x[int(indices_dep_handicap) + 300] - corde_interpol_x[int(indices_dep_handicap)]
            dep_diry = corde_interpol_y[int(indices_dep_handicap) + 300] - corde_interpol_y[int(indices_dep_handicap)]
            norm_dep = np.sqrt(np.square(dep_dirx) + np.square(dep_diry))
            porte_depart["direction"] = [np.float(dep_dirx) / np.float(norm_dep),
                                         np.float(dep_diry) / np.float(norm_dep)]
            porte_depart["largeur"] = np.sqrt(
                np.square(X_corde[int(ind_dep_handicap)] - X_corde_ext[int(ind_dep_handicap)]) +
                np.square(Y_corde[int(ind_dep_handicap)] - Y_corde_ext[int(ind_dep_handicap)]))
            portes_depart_handicap[0] = porte_depart

        ### calcul des paramètres de la porte d'arrivée
        porte_arr = {}
        porte_arr["corde"] = [X_corde[-1], Y_corde[-1]]
        porte_arr["corde_2"] = [X_corde_2[-1], Y_corde_2[-1]]
        porte_arr["corde_ext"] = [X_corde_ext[-1], Y_corde_ext[-1]]
        arr_dirx = corde_interpol_x[-1] - corde_interpol_x[-300]
        arr_diry = corde_interpol_y[-1] - corde_interpol_y[-300]
        norm_arr = np.sqrt(np.square(arr_dirx) + np.square(arr_diry))
        porte_arr["direction"] = [np.float(arr_dirx) / np.float(norm_arr), np.float(arr_diry) / np.float(norm_arr)]
        porte_arr["largeur"] = np.sqrt(
            np.square(X_corde[-1] - X_corde_ext[-1]) + np.square(Y_corde[-1] - Y_corde_ext[-1]))
        """

        msg_udp = "EvtMoteur: calcul des increments de distance#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        ### Calcul des incréments de distance pour la corde à 2m
        dD_corde_2 = np.zeros(np.size(corde_2_interpol_x))
        dist_totale_parcours = 0

        step_10pourc = int(np.float(np.size(corde_2_interpol_x)) / np.float(10))
        for k in range(1, np.size(corde_2_interpol_x)):
            if k % step_10pourc == 0:
                msg_udp = "PourcParcours: progression calcul des increments " + str(
                    np.float(k) / np.float(step_10pourc) * 10) + "#"
                print msg_udp
                logging.info(msg_udp)
                #sender_udp.sendto(msg_udp, (hote, port_sender))

            dx = corde_2_interpol_x[k] - corde_2_interpol_x[k - 1]
            dy = corde_2_interpol_y[k] - corde_2_interpol_y[k - 1]
            dD = np.sqrt(np.square(dx) + np.square(dy))
            dD_corde_2[k] = dD
            if k >= ind_deb * params.res_interp and k <= ind_fin * params.res_interp:
                dist_totale_parcours = dist_totale_parcours + dD

        #### distance deuxieme corde
        dist_x = X_corde[0] - X_corde_2[0]
        dist_y = Y_corde[0] - Y_corde_2[0]
        dist_corde_2 = np.sqrt(np.square(dist_x) + np.square(dist_y))
        dist_corde_2 = np.maximum(1, np.minimum(dist_corde_2, 2))
        dist_corde_2 = np.round(dist_corde_2)

        largeur_parcours = largeur_max # np.mean(np.sqrt(np.square(X_corde - X_corde_ext) + np.square(Y_corde - Y_corde_ext)))

        ##### Creation de dictionnaire d'information de parcours ###
        msg_udp = "EvtMoteur: stockage des resultats#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        info_parcours = dict()
        info_parcours["DIST_corde"] = DIST_corde.tolist()
        info_parcours["indice_10"] = np.array(indice_10).tolist()
        info_parcours["indice_500"] = np.array(indice_500).tolist()
        info_parcours["X_corde"] = X_corde.tolist()
        info_parcours["Y_corde"] = Y_corde.tolist()
        info_parcours["X_corde_ext"] = X_corde_ext.tolist()
        info_parcours["Y_corde_ext"] = Y_corde_ext.tolist()
        info_parcours["centre_lat"] = centre_lat
        info_parcours["centre_long"] = centre_long
        info_parcours["dist_totale_parcours"] = dist_totale_parcours
        info_parcours["id_portes"] = id_portes
        info_parcours["indice_portes"] = indice_portes.tolist()
        info_parcours["dD_corde_inter"] = dD_corde_inter
        #info_parcours["portes_depart_handicap"] = np.array(portes_depart_handicap).tolist()
        #info_parcours["porte_arr"] = porte_arr
        info_parcours["dist_corde_2"] = dist_corde_2
        info_parcours["indices_dep_handicap"] = indices_dep_handicap.tolist()
        info_parcours["dist_course_handicap"] = np.array(dist_course_handicap).tolist()
        info_parcours["porte_dep_handicap"] = np.array(porte_dep_handicap).tolist()
        info_parcours["largeur_parcours"] = np.array(largeur_parcours).tolist()

        with open(file_info, 'w') as fp:
            json.dump(info_parcours, fp, indent=2)

        #### Sauvegarde csv
        a = np.column_stack((corde_interpol_x, corde_interpol_y, corde_2_interpol_x, corde_2_interpol_y,
            corde_ext_interpol_x, corde_ext_interpol_y, dD_corde_2))
        np.savetxt(file_interpolation, a, delimiter=";")

        msg_udp = "SuccesParcours: le parcours " + str(file_parcours) + " a été traite avec succes#"
        print msg_udp
        logging.info(msg_udp)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
    except:
        msg_udp = "ErreurParcours: Le parcours n'a pas pu etre traite correctement#"
        print msg_udp
        logging.error(msg_udp, exc_info=True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

### Fonction non utilisée
def passage_porte(x, y, prev_x, prev_y, porte):
    """
    Fonction qui vérifie si la ligne a été franchie dans le sens de la course.
    :param x: position sur X en coordonnées cartésiennes
    :param y: position sur Y en coordonnées cartésiennes
    :param prev_x: position précédente sur X en coordonnées cartésiennes
    :param prev_y: position précédente sur Y en coordonnées cartésiennes
    :param porte: dictionnaire contenant les informations sur la porte 
    :return: booléen
    """
    try:
        if abs(x) > 0 and abs(y) > 0 and abs(prev_x) > 0 and abs(prev_y) > 0:
            ### on vérifie que les données gps placent le cheval entre la corde extérieure et la corde intérieure
            x_porte = porte["corde"][0]
            y_porte = porte["corde"][1]
            x_porte_ext = porte["corde_ext"][0]
            y_porte_ext = porte["corde_ext"][1]

            ## Vérifier si le cheval est dans le sens avant de la course
            avant = False
            vect_x = x - prev_x
            vect_y = y - prev_y
            produit_scalaire = vect_x * porte["direction"][0] + vect_y * porte["direction"][1]
            if produit_scalaire > 0:
                avant = True

            ## Calcul de la droite de la ligne de départ
            A = np.float(y_porte_ext - y_porte) / np.float(x_porte_ext - x_porte)
            B = np.float(y_porte_ext) - np.float(A) * np.float(x_porte_ext)

            ## On check si les 2 points se trouvent de part et d'autre de la ligne
            check1 = np.float(y) - np.float(A) * np.float(x) - np.float(B)
            check2 = np.float(prev_y) - np.float(A) * np.float(prev_x) - np.float(B)
            franchissement = False
            if check1 * check2 <= 0:
                franchissement = True

            ## On check que la distance au point de départ à la corde ne soit pas supérieure à la largeur de la piste
            dist_porte_corde = np.sqrt(np.square(x - x_porte) + np.square(y - y_porte))
            dist_porte_corde_ext = np.sqrt(np.square(x - x_porte_ext) + np.square(y - y_porte_ext))
            proche = False
            if dist_porte_corde <= porte["largeur"] and dist_porte_corde_ext <= porte["largeur"]:
                proche = True

            if proche and franchissement and avant:
                return True
            else:
                return False
        else:
            return False
    except:
        logging.error("erreur lors de la verification du passage de porte DEP ou ARR", exc_info=True)
        return False
###

def etape_Kalman(prev_Etat, Obs, P, Mat_etat, cov_etat, cov_obs):
    """
	Fonction qui effectue une étape du filtre de Kalman
    :param prev_Etat: état précédent (X,Y,V)
    :param Obs: observation courante (x,y,v)
    :param P: matrice de covariance à cette étape
    :param Mat_etat: matrice de transition de l'état
    :param cov_etat: matrice de covariance de l'état
    :param cov_obs: matrice de covariance de l'observation
    :return Etat: nouvel état
    :return P: nouvelle matrice de covariance
	"""
    try:
        ##### Prediction
        Etat = np.dot(Mat_etat, prev_Etat) # produit matriciel
        P = np.dot(Mat_etat, np.dot(P, Mat_etat.T)) + cov_etat
        ##### Correction
        ## Si pas d'observation on ne passe pas dans la correction
        if Obs[1] != 0 and Obs[0] != 0:
            Obs_estim = Etat
            S = P + cov_obs
            K = np.dot(P, np.linalg.inv(S))
            Etat = Etat + np.dot(K, (Obs - Obs_estim))
            P = P - np.dot(K, P)

        return Etat, P

    except:
        logging.error("erreur lors de l'execution du filter de Kalman", exc_info=True)
        return prev_Etat, P

def hhmmss_to_ts_utc(hhmmss):
    """
    :param hhmmss: timestamp de la carte au format hhmmssmmm
    :return timestamp: format classique en ms 
    """
    try:
        heure = np.int(np.floor(float(hhmmss) / float(10 ** 4)))
        minute = np.int(np.floor((hhmmss - heure * 10 ** 4) / float(10 ** 2)))
        sec = np.int(np.floor(hhmmss - heure * 10 ** 4 - minute * 10 ** 2))
        ms = np.int(float(hhmmss - heure * 10 ** 4 - minute * 10 ** 2 - sec) * 1000)
        now = datetime.datetime.utcnow()
        annee = now.year
        mois = now.month
        jour = now.day
        t = datetime.datetime(annee, mois, jour, heure, minute, sec, ms)
        timestamp = time.mktime(t.timetuple()) * 1000
        timestamp = timestamp + t.microsecond

        return np.round(float(timestamp) / float(100)) * 100  # np.int(timestamp)
    except:
        logging.error("erreur lors de la conversion du timestamp hhmmss", exc_info=True)
        return 0

### fonction non utilisée
def dur_to_mmssmmm(dur):
    """
	converti un timestamp en secondes au format ss:mmm
    :param dur: timestamp en secondes
    :return: string au format "secondes:millièmes"
	"""
    try:
        # minute = np.floor(float(dur) / float(60))
        # sec = np.floor(dur - minute * 60)
        sec = np.floor(dur)
        mmm = np.floor((dur - sec) * 1000)
        # mmm = dur - sec
        if sec < 10:
            sec_str = "0" + str(int(sec))
        else:
            sec_str = str(int(sec))
        # if minute < 10:
        # min_str = "0" + str(int(minute))
        # else:
        # min_str = str(int(minute))
        if mmm < 10:
            mmm_str = "00" + str(int(mmm))
        elif mmm < 100:
            mmm_str = "0" + str(int(mmm))
        else:
            mmm_str = str(int(mmm))
        # return min_str + ":" + sec_str + ":" + str(int(mmm))
        return sec_str + ":" + mmm_str
    except:
        logging.info("erreur dans la fonction dur_to_mmssmmm ", exc_info=True)
        return "00:000"
###

def heading(lat1, lon1, lat2, lon2):
    """
    Fonction l'orientation du mouvement à partir d'une variation de coordonnées lat-long
    :param lat1: latitude de départ
    :param lon1: longitude de départ
    :param lat2: latitude d'arrivée
    :param lon2: longitude d'arrivée
    :return: heading en degrés 
    """
    try:
        lat1 = float(lat1) / 180 * math.pi
        lat2 = float(lat2) / 180 * math.pi
        dLon = float(lon2 - lon1) / 180 * math.pi
        y = np.sin(dLon) * np.cos(lat2)
        x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dLon)
        brng = np.arctan2(y, x)
        return np.degrees(brng)
    except:
        logging.error("erreur dans le calcul du heading", exc_info=True)
        return 0

def lat_to_m(dlat, alat):
    """
    Fonction qui convertit une variation de latitude en mètres
    :param dlat: variation de latitude en degrés
    :param alat: latitude de référence
    :return: variation en m en coordonnées cartésienne sur Y
    """
    try:
        rlat = alat * np.pi / 180  # conversion en radians
        m = 111132.09 - 566.05 * np.cos(2 * rlat) + 1.2 * np.cos(
            4 * rlat)  # longueur en metres pour un degre a la latitude alat
        dy = dlat * m  # longueur en metres pour la diff de latitude dlat
        dy = dlat * m  # longueur en metres pour la diff de latitude dlat
        return dy
    except:
        logging.error("erreur dans la fonction lat_to_m", exc_info=True)
        return 0

def lon_to_m(dlon, alat):
    """
    Fonction qui convertit une variation de longitude en mètres
    :param dlong: variation de longitude en degrés
    :param alat: latitude de référence
    :return: variation en m en coordonnées cartésiennes sur X
    """
    try:
        rlat = alat * np.pi / 180  # conversion en rad
        p = 111415.13 * np.cos(rlat) - 94.55 * np.cos(3 * rlat)  # longueur d'un degre en longitude a alat
        dx = dlon * p
        return dx
    except:
        logging.error("erreur dans la fonction lon_to_m", exc_info=True)
        return 0

### Fonction non utilisée
def conv_deg_minutes(data):
    """
    Fonction qui convertit des degrés minutes en degrés décimaux
    :param data: angle en degré minutes
    :return: angle en degrés décimal
    """
    try:
        if np.size(data) > 1:
            deg_data = np.zeros(np.size(data))
            for k in range(np.size(data)):
                coord = data[k]
                deg = np.floor(coord)
                min = float(coord - deg) * 100
                # min = np.floor(float(coord - deg) * 100)
                # sec = float(coord - deg - float(min) / float(100)) * 100 * 100
                # deg_data[k] = deg + float(min) / float(60) + float(sec) / float(3600)
                deg_data[k] = deg + float(min) / float(60)
        else:
            coord = data
            deg = np.floor(coord)
            min = float(coord - deg) * 100
            # min = np.floor(float(coord - deg) * 100)
            # sec = float(coord - deg - float(min) / float(100)) * 100 * 100
            # deg_data[k] = deg + float(min) / float(60) + float(sec) / float(3600)
            deg_data = deg + float(min) / float(60)
        return deg_data
    except:
        logging.error("erreur dans la fonction conv_deg_to_minutes", exc_info=True)
        return 0
###

def m_to_lat(dy, alat):
    """
    Fonction qui convertit une distance en m en variation de latitude
    :param dy: variation en mètres sur l'axe Y des coordonnées cartésiennes
    :param alat: latitude de référence
    :return: variation de latitude en degrés décimal
    """
    try:
        rlat = alat * np.pi / 180
        m = 111132.09 - 566.05 * np.cos(2 * rlat) + 1.2 * np.cos(4 * rlat)
        dlat = dy / m
        return dlat
    except:
        logging.error("erreur dans la fonction m_to_lat", exc_info=True)
        return 0

def m_to_lon(dx, alat):
    """
    Fonction qui convertir une distance en mètres en variation de longitude
    :param dx: variation en mètres sur l'axe X des coordonnées cartésiennes
    :param alat: latitude de référence
    :return: variation de latitude en degrés décimal
    """
    try:
        rlat = alat * np.pi / 180
        p = 111415.13 * np.cos(rlat) - 94.55 * np.cos(3 * rlat)
        dlon = dx / p
        return dlon
    except:
        logging.error("erreur dans la fonction m_to_lon", exc_info=True)
        return 0

def init_depart(Mes, Ind, par, nb_handicaps, id_porte_dep, k):
    """
    Fonction d'initialisation des mesures et indicateurs après détection d'un franchissement du départ
    Met à jour les objets Mes et Ind
    
    :param Mes: 
    :param Ind: 
    :param par: 
    :param nb_handicaps: 
    :param id_porte_dep: 
    :param k: 
    :return Mes:
    :return Ind:
    """

    try:
        Ind.classement_cheval_ind[k] = 0
        Ind.dist_parcourue_reelle_ind[k] = 0
        Ind.dist_parcourue_proj_ind[k] = 0
        Ind.temps_pass_pc_ind[k] = 0
        Ind.pourc_progr_ind[k] = 0
        Ind.ecart_proj_premier_ind[k] = 0
        Ind.temps_passe_depart_ind[k] = 0
        Ind.cheval_traj_court_ind[k] = 0  # ['N'] # FFV15
        Ind.cheval_trajet_long_ind[k] = 0  # ['N'] # FFV15
        Ind.ecart_cheval_prec_ind[k] = 0
        Ind.v_pointe_cheval_ind[k] = 0
        Ind.v_moy_cheval_ind[k] = 0
        Ind.dist_restant_corde_premier_ind[k] = 0
        Ind.dist_inst_corde_cheval_ind[k] = 0
        Ind.dist_moy_corde_ind[k] = 0
        Ind.t_reac_sortie_ind[k] = 0
        Ind.franchissement_depart_ind[k] = 0  # ['N'] # FFV15
        Ind.franchissement_arrivee_ind[k] = 0  # ['N'] # FFV15

        Ind.en_course[k] = 0
        Ind.n_en_course[k] = 0

        Ind.avance_deb[k] = 0
        Ind.PC_franchis[k] = 0

        Ind.cheval_trajet_court = 0
        Ind.cheval_trajet_long = 0
        Ind.arrive[k] = 0
        Mes.avance_mesure[k] = 0

        if nb_handicaps:
            Mes.ind_parcours_mesure[k] = indices_dep_handicap[int(id_porte_dep[k])] - 1
            ind_depart = indices_dep_handicap[int(id_porte_dep[k])]

            Ind.ind_porte_courante[k] = id_portes.index(porte_dep_handicap[int(
                id_porte_dep[k])])  # np.where(id_portes == id_porte_dep[k])
        else:
            Mes.ind_parcours_mesure[k] = -1
            ind_depart = 0
            Ind.ind_porte_courante[k] = 0

        Mes.Etat_all_id[k, 0] = lat_to_m(Mes.lat_mesure[k] - centre_lat, centre_lat)
        Mes.Etat_all_id[k, 1] = lon_to_m(Mes.long_mesure[k] - centre_long,
                                         centre_lat)
        Mes.Etat_all_id[k, 2] = float(Mes.v_mesure[k])

        # Initialisation de la distance à la corde 0206
        if Mes.ind_parcours_mesure[k] > 0:
            tableau_corde_interp_x = corde_interpol_x[int(Mes.ind_parcours_mesure[k]): np.minimum(
                int(Mes.ind_parcours_mesure[k] + 50 * par.res_interp), np.size(corde_interpol_x) - 1)]
            tableau_corde_interp_y = corde_interpol_y[int(Mes.ind_parcours_mesure[k]): np.minimum(
                int(Mes.ind_parcours_mesure[k] + 50 * par.res_interp), np.size(corde_interpol_y) - 1)]
            dist_corde_interp = np.sqrt(
                np.square(tableau_corde_interp_x - Mes.Etat_all_id[k, 0]) + np.square(
                    tableau_corde_interp_y - Mes.Etat_all_id[k, 1]))

            Mes.stock_proche_corde[k] = np.argmin(dist_corde_interp) + Mes.ind_parcours_mesure[k]
            Mes.ind_parcours_mesure[k] = Mes.stock_proche_corde[k]
            Mes.distance_corde_mesure[k] = np.min(dist_corde_interp)
            Mes.stock_distance_corde[k] = Mes.distance_corde_mesure[k]

            if Mes.ind_parcours_mesure[k] > ind_depart:
                Mes.avance_mesure[k] = np.sum(
                    dD_corde_2[ind_depart: int(Mes.ind_parcours_mesure[k])])
                Ind.dist_parcourue_reelle_ind[k] = Mes.avance_mesure[k]
                Ind.dist_parcourue_proj_ind[k] = Mes.avance_mesure[k]
        else:
            dist_corde_tableau = np.sqrt(np.square(
                X_corde[0:np.minimum(10, np.size(X_corde) - 1)] - Mes.Etat_all_id[
                    k, 0]) + np.square(
                Y_corde[0:np.minimum(10, np.size(X_corde) - 1)] - Mes.Etat_all_id[
                    k, 1]))
            ind_mindist = np.argmin(dist_corde_tableau)
            tableau_corde_interp_x = corde_interpol_x[np.maximum(0, (
                ind_mindist - 1) * par.res_interp): np.minimum(
                (ind_mindist + 1) * par.res_interp, np.size(corde_interpol_x) - 1)]
            tableau_corde_interp_y = corde_interpol_y[np.maximum(0, (
                ind_mindist - 1) * par.res_interp): np.minimum(
                (ind_mindist + 1) * par.res_interp, np.size(corde_interpol_y) - 1)]
            dist_corde_interp = np.sqrt(
                np.square(tableau_corde_interp_x - Mes.Etat_all_id[k, 0]) + np.square(
                    tableau_corde_interp_y - Mes.Etat_all_id[k, 1]))

            Mes.stock_proche_corde[k] = np.argmin(dist_corde_interp) + np.maximum(0, (
                ind_mindist - 1) * par.res_interp)
            Mes.ind_parcours_mesure[k] = Mes.stock_proche_corde[k]
            Mes.distance_corde_mesure[k] = np.min(dist_corde_interp)
            Mes.stock_distance_corde[k] = Mes.distance_corde_mesure[k]
            if Mes.ind_parcours_mesure[k] > ind_depart:
                Mes.avance_mesure[k] = np.sum(
                    dD_corde_2[ind_depart: int(Mes.ind_parcours_mesure[k])])
                Ind.dist_parcourue_reelle_ind[k] = Mes.avance_mesure[k]
                Ind.dist_parcourue_proj_ind[k] = Mes.avance_mesure[k]
    except:
        msg_udp = "probleme lors de l'init du départ pour le cheval " + str(k) + "#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
    return Mes, Ind

def decoupage_trames_attente(k, frames):
    """
    Fonction pour récupérer la trame du capteur k dans l'ensemble des trames recue pour la boucle courante en mode attente
    :param k: indice du capteur
    :param frames: tableau des trames recues
    :return: 
    """
    try:
        if np.size(frames) > 0:
            if np.size(frames) == par.size_trame:  ### UPDATE
                if frames[0] == liste_id[k]:
                    trame_recue = True
                    trame = frames
                else:
                    trame_recue = False
                    trame = [0, 0, 0, 0, 0, 0, 0]
            else:
                id_trame = np.where(frames[:, 0] == int(liste_id[k]))[0]
                if np.size(id_trame) > 0:
                    trame_recue = True
                    trame = frames[id_trame[-1], :]
                else:
                    trame_recue = False
                    trame = [0, 0, 0, 0, 0, 0, 0]
        else:
            trame_recue = False
            trame = [0, 0, 0, 0, 0, 0, 0]
        return trame, trame_recue

    except:
        msg_udp = "probleme lors du découpage de la trame #"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

        trame_recue = False
        trame = [0, 0, 0, 0, 0, 0, 0]
        return trame, trame_recue

def decoupage_trames(k, frames):
    """
    Fonction pour récupérer la trame du capteur k dans l'ensemble des trames recues pour la boucle courante en mode course
    :param k: 
    :param frames: 
    :return: 
    """
    try:
        if np.size(frames) > 0:
            if np.size(frames) == par.size_trame:  ### UPDATE
                if frames[0] == liste_id[k]:
                    trame_recue = True
                    trame = frames
                    if trame[1] > 0:
                        trame[1] = hhmmss_to_ts_utc(trame[1])
                        trame[1] = int(np.round(trame[1] / float(100)) * 100)
                    if np.size(stock_trames[str(k)]) == 0:
                        stock_trames[str(k)] = trame
                    else:
                        stock_trames[str(k)] = np.vstack([stock_trames[str(k)], trame])
                        stock_trames[str(k)] = stock_trames[str(k)][stock_trames[str(k)][:, 1].argsort()]
                else:
                    trame_recue = False
                    trame = [0, 0, 0, 0, 0, 0, 0]
            else:
                id_trame = np.where(frames[:, 0] == int(liste_id[k]))[0]
                if np.size(id_trame) > 0:
                    for id in id_trame:
                        trame_recue = True
                        trame = frames[id, :]
                        if trame[1] > 0:
                            trame[1] = hhmmss_to_ts_utc(trame[1])
                            trame[1] = int(np.round(trame[1] / float(100)) * 100)
                        if np.size(stock_trames[str(k)]) == 0:
                            stock_trames[str(k)] = trame
                        else:
                            stock_trames[str(k)] = np.vstack([stock_trames[str(k)], trame])
                            stock_trames[str(k)] = stock_trames[str(k)][stock_trames[str(k)][:, 1].argsort()]
                else:
                    trame_recue = False
                    trame = [0, 0, 0, 0, 0, 0, 0]
        else:
            trame_recue = False
            trame = [0, 0, 0, 0, 0, 0, 0]
        return trame, trame_recue

    except:
        msg_udp = "probleme lors du découpage de la trame #"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp .sendto(msg_udp, (hote, port_sender))

        trame_recue = False
        trame = [0, 0, 0, 0, 0, 0, 0]
        return trame, trame_recue

def gestion_trame(Mes, trame_recue, trame, k):
    """
    On vérifie si on a reçu une trame pour le capteur k, et si elle semble correcte, sinon on affecte une trame nulle
    :param Mes: 
    :param trame_recue: 
    :param trame: 
    :param k: 
    :return: 
    """
    try:
        # if not trame_recue:
        #    print "pas de donnée ", str(k)
        if trame_recue:  # si on a recu une trame pour ce capteur
            trame[4] = trame[4] / 3.6 # de km/h à m/s
            if Mes.num_trames_recues[k] == 0:
                # print "premiere trame" + str(k) +
                Mes.num_trames_recues[k] = 1
                Mes.ts_mesure[k] = int(trame[1]) # hhmmss_to_ts_utc(trame[1])
                calculer_position = False
            else:  # on calcule les sorties normalement
                calculer_position = True
                if trame[2] != 0 and trame[3] != 0 and trame[1] != 0: # and trame[1] >= Mes.ts_mesure[k]:
                    # hhmmss_to_ts_utc(trame[1]) >= Mes.ts_mesure[k]:
                    Mes.Obs = [trame[2], trame[3], trame[4]]  # lat, Long, V
                    # conv des obs en cartesien en m
                    Mes.Obs[0] = lat_to_m(Mes.Obs[0] - centre_lat, centre_lat)
                    Mes.Obs[1] = lon_to_m(Mes.Obs[1] - centre_long, centre_lat)
                    Mes.ts_mesure[k] = int(trame[1]) # hhmmss_to_ts_utc(trame[1])
                    # print "pas prediction " + str(k)
                else:
                    print "prediction 1 " + str(k)
                    Mes.Obs = [0, 0, 0]
                    trame = [0, 0, 0, 0, 0, 0, 0]
                    Mes.ts_mesure[k] = TS_traitement
                    # calculer_position = True
                Mes.num_trames_recues[k] = Mes.num_trames_recues[k] + 1
                # print "trame " + str(Mes.num_trames_recues[k]) + " " + str(k)
        else:
            if Mes.num_trames_recues[
                k] > 1:  # Si on a deja recu des donnees pour ce capteur, on calcule ses sorties sans connaitre l'observation
                calculer_position = True
                Mes.Obs = [0, 0, 0]
                # print "prediction 2 " + str(k)
            else:  # on ne calcule pas les sorties
                calculer_position = False

            if Mes.ts_mesure[k] > 0:
                Mes.ts_mesure[k] = TS_traitement # Mes.ts_mesure[k] + 100

        return calculer_position, Mes
    except:
        msg_udp = "problème lors de la gestion de la trame #"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

def check_point_parcours(Mes, k, id_porte_dep):
    """
    Fonction pour vérifier si entre le point courant et le point précédent, le cheval avancait normalement dans le 
    parcours (v>20km/h), reculait, ou rien.

    :param id_porte_dep: 
    :param Mes: 
    :param k: 
    :return: 0 (rien), 1 (avance dans parcours), 2 (recul)
    """
    try:
        prev_x = Mes.prev_x_brute[k]
        prev_y = Mes.prev_y_brute[k]
        x = Mes.x_brute[k]
        y = Mes.y_brute[k]

        if prev_x != 0 and prev_y != 0 and x != 0 and y != 0:
            prev_ind_parcours = Mes.prev_ind_parcours_brut[k]
            vit = Mes.vit_brute[k]

            if np.size(indice_10) > 1:
                deb_search = int(indice_10[int(id_porte_dep[k])])
                fin_search = int(indice_500[int(id_porte_dep[k])])
            else:
                deb_search = int(indice_10)
                fin_search = int(indice_500)

            # On va chercher le point le plus proche du parcours
            dist_corde_tableau = np.square(X_corde[deb_search:fin_search] - x) \
                                 + np.square(Y_corde[deb_search:fin_search] - y)
            ind_opt = np.argmin(dist_corde_tableau) + deb_search
            dist_opt = np.sqrt(np.min(dist_corde_tableau))

            # On cherche + finement dans l'interpolation
            deb_search = np.minimum(np.maximum(0, (ind_opt - 1) * par.res_interp), np.size(corde_interpol_x))
            fin_search = np.minimum(np.maximum(0, (ind_opt + 1) * par.res_interp), np.size(corde_interpol_x))
            dist_corde_tableau = np.square(corde_interpol_x[deb_search:fin_search] - x) \
                                 + np.square(corde_interpol_y[deb_search:fin_search] - y)
            ind_parcours = deb_search + np.argmin(dist_corde_tableau)
            dist_corde = np.sqrt(np.min(dist_corde_tableau))

            x_corde = corde_interpol_x[ind_parcours]
            y_corde = corde_interpol_y[ind_parcours]
            x_corde_ext = corde_ext_interpol_x[ind_parcours]
            y_corde_ext = corde_ext_interpol_y[ind_parcours]
            largeur_corde = largeur_parcours # np.sqrt(np.square(x_corde - x_corde_ext) + np.square(y_corde - y_corde_ext))

            dist_corde_ext = np.sqrt(np.square(x - x_corde_ext) + np.square(y - y_corde_ext))

            if dist_corde_ext <= largeur_corde and dist_corde <= largeur_corde and \
                                    dist_corde_ext + dist_corde < largeur_corde + 0.2:
                dans_parcours = True
                # if not Mes.depart_franchis[k]:
                #    print "dans parcours ", str(k)
            else:
                dans_parcours = False

            if ind_parcours > prev_ind_parcours:
                avance = True
                # if not Mes.depart_franchis[k]:
                #    print "avance ", str(k)
            else:
                avance = False

            vitesse = False
            if vit > par.seuil_v_depart:
                vitesse = True
                # if not Mes.depart_franchis[k]:
                #    print "vitesse ", str(k)

            if dans_parcours and avance and vitesse:
                return 1, ind_parcours
                print liste_id[k], "avance"
            elif not avance:
                return 2, ind_parcours
                print liste_id[k], vitesse, dans_parcours, avance
            else:
                return 0, ind_parcours
                print liste_id[k], vitesse, dans_parcours, avance
        else:
            return -1, 0
            print liste_id[k], -1
    except:
        msg_udp = "probleme lors de la verification des points parours#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        return 0, 0

def check_course_capteur(Mes, trame, k, id_porte_dep, nb_handicaps):
    """
    Fonction pour connaitre l'état du capteur sur les 10 dernier points: avance dans parcours / recul dans parcours
    :param Mes: 
    :param trame: 
    :param k: 
    :return: 
    """
    try:
        Mes.prev_x_brute[k] = Mes.x_brute[k]
        Mes.prev_y_brute[k] = Mes.y_brute[k]
        if trame[2] > 0:
            Mes.x_brute[k] = lat_to_m(trame[2] - centre_lat, centre_lat)
        else:
            Mes.x_brute[k] = 0
        if trame[3] > 0:
            Mes.y_brute[k] = lon_to_m(trame[3] - centre_long, centre_lat)
        else:
            Mes.y_brute[k] = 0
        # print "x y brutes", Mes.x_brute[k], Mes.y_brute[k]
        Mes.prev_vit_brute[k] = Mes.vit_brute[k]
        Mes.vit_brute[k] = trame[4]
        Mes.prev_ind_parcours_brut[k] = Mes.ind_parcours_brut[k]
        Mes.stock_vit_brute[k, :] = np.concatenate((Mes.stock_vit_brute[k, 1:], [Mes.vit_brute[k]]))

        check, ind_parcours = check_point_parcours(Mes, k, id_porte_dep)

        depart_parcours = 0
        recul_parcours = 0
        Mes.ind_parcours_brut[k] = ind_parcours

        if check == 0:
            Mes.count_recul[k] = 0
            Mes.count_parcours_ok[k] = 0
        elif check == 1:
            Mes.count_recul[k] = 0
            Mes.count_parcours_ok[k] = Mes.count_parcours_ok[k] + 1
            if not Mes.depart_franchis[k]:
                print "count_parcours ", Mes.count_parcours_ok[k], str(k)

        elif check == 2:
            Mes.count_recul[k] = Mes.count_recul[k] + 1
            Mes.count_parcours_ok[k] = 0

        if Mes.count_recul[k] > par.seuil_points_recul:
            recul_parcours = 1
            Mes.count_recul[k] = 0

        if Mes.count_parcours_ok[k] > par.seuil_points_parcours and not Mes.depart_franchis[k]:
            Mes.T_detect[k] = Mes.ts_mesure[k]
            if nb_handicaps:
                ind_depart = indices_dep_handicap[int(id_porte_dep[k])]
            else:
                ind_depart = 0

            if Mes.ind_parcours_brut[k] > ind_depart:
                Mes.ts_passage_dep[k] = Mes.ts_mesure[k] - float(
                    np.sum(dD_corde_2[int(ind_depart):int(Mes.ind_parcours_brut[k])])) \
                                                           / float(np.median(Mes.stock_vit_brute[k, :])) * 1000
            else:
                Mes.ts_passage_dep[k] = Mes.T_detect[k]

            print "10 points parcours", k
            Mes.count_parcours_ok[k] = 0
            depart_parcours = 1

        return Mes, depart_parcours, recul_parcours

    except:
        msg_udp = "probleme dans la fonction check_course_capteur #"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        return Mes, 0, 0

def check_depart_20s(Mes, Ind, recul_parcours, nb_handicaps, id_porte_dep, k, TS_DEPART, COURSE_DEMARREE):
    """
    :param Mes: 
    :param Ind: 
    :param recul_parcours: 
    :param nb_handicaps: 
    :param id_porte_dep: 
    :param k: 
    :param TS_DEPART: 
    :param COURSE_DEMARREE: 
    :return: 
    """
    try:
        # On vérifie que cela ne fait pas 20s que le cheval a franchis le départ sans
        #  qu'il y ait eu de top départ, au quel cas on réinitialise
        if Mes.depart_franchis[k] and not COURSE_DEMARREE:
            if Mes.ts_mesure[k] - Mes.T_detect[k] > 20000:
                Mes, Ind = init_depart(Mes, Ind, par, nb_handicaps, id_porte_dep, k)
                Mes.depart_franchis[k] = 0
                Mes.ind_parcours_mesure[k] = -1
                Mes.stock_proche_corde[k] = 0
                Mes.distance_corde_mesure[k] = 0
                Mes.ts_passage_dep[k] = 0
                Mes.T_detect[k] = 0
                msg_udp = "EvtMoteur: reinit pour le cheval " + str(k) + "#"
                print msg_udp
                logging.info(msg_udp)

                TS_DEPART = np.max(Mes.ts_passage_dep)
                for l in range(0, nb_id):
                    if Mes.ts_passage_dep[l] < TS_DEPART and Mes.ts_passage_dep[l] > 0:
                        TS_DEPART = Mes.ts_passage_dep[l]
                        msg_udp = "EvtMoteur: TS_DEPART " + str(TS_DEPART) + "#"
                        print msg_udp
                        logging.info(msg_udp)

            if recul_parcours: # Si on a reculé après un passage de la ligne de départ et que le départ n'a pas encore été donné

                Mes, Ind = init_depart(Mes, Ind, par, nb_handicaps, id_porte_dep, k)
                Mes.depart_franchis[k] = 0
                Mes.ind_parcours_mesure[k] = -1
                Mes.stock_proche_corde[k] = 0
                Mes.distance_corde_mesure[k] = 0
                Mes.ts_passage_dep[k] = 0
                Mes.T_detect[k] = 0

                TS_DEPART = np.max(Mes.ts_passage_dep)
                for l in range(0, nb_id):
                    if Mes.ts_passage_dep[l] < TS_DEPART and Mes.ts_passage_dep[l] > 0:
                        TS_DEPART = Mes.ts_passage_dep[l]
                        msg_udp = "EvtMoteur: TS_DEPART " + str(TS_DEPART) + "#"
                        print msg_udp
                        logging.info(msg_udp)

        return Mes, Ind, TS_DEPART
    except:
        msg_udp = "probleme dans la fonction check_depart_20s#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        return Mes, Ind, TS_DEPART

def check_bonne_data(trame, Mes, k):
    """
    On vérifie si la data a l'air ok: dans la parcours, vitesse cohérente

    :param trame: 
    :param Mes: 
    :param k: 
    :return: 
    """
    try:
        if (trame[4] == 0.0 and Mes.v_mesure[k] > 3.0) or (trame[4] > 25.0) \
                or (abs(Mes.v_mesure[k] - trame[4]) > 5.0 and Mes.v_mesure[
                    k] > 3.0):
            print "vitesse", trame[4], Mes.v_mesure[k], str(k)
            trame[4] = Mes.v_mesure[k]
            Mes.Obs[2] = Mes.v_mesure[k]

        # Calcul de la distance globale au parcours pour déterminer
        # si la mesure est valable vis à vis du parcours
        # Si le point est à plus de 5 mètres du parcours, on ne le prend pas en compte
        # critère sur la vitesse
        x = lat_to_m(trame[2] - centre_lat, centre_lat)
        y = lon_to_m(trame[3] - centre_long, centre_lat)

        dist_tableau = np.array(np.square(X_corde - x) + np.square(Y_corde - y))
        mindist = np.sqrt(np.min(dist_tableau))
        ind_mindist = np.argmin(dist_tableau)

        dist_tableau_ext = np.array(np.square(X_corde_ext - x) + np.square(Y_corde_ext - y))
        mindist_ext = np.sqrt(np.min(dist_tableau_ext))

        # largeur = np.sqrt(np.square(X_corde[ind_mindist] - X_corde_ext[ind_mindist]) + \
        #              np.square(Y_corde[ind_mindist] - Y_corde_ext[ind_mindist]))

        # diagonale = np.sqrt(np.square(largeur) + 100)

        # if mindist > largeur_parcours + 5 or mindist_ext > largeur_parcours + 5:
        if mindist > largeur_parcours + 2.5 or mindist_ext > largeur_parcours + 2.5:
            Mes.Obs = [0, 0, 0]
            # print "prediction 3 " + str(k)
            # print mindist, mindist_ext, largeur_parcours + 5, Mes.ts_mesure[k
            # ], str(k)
            print "largeur_parcours ", k, mindist, mindist_ext, largeur_parcours

        return Mes, trame
    except:
        msg_udp = "probleme dans la fonction check_bonne_data#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))
        return Mes, trame

def recherche_prediction(Mes, k, trame, dist_totale):
    """
    Préparation des variable avant passage dans le filtre de Kalman

    :param Mes: 
    :param k: 
    :param trame: 
    :param dist_totale: 
    :return: 
    """
    try:
        #### On cherche le point a v dt de l'etat qui conserve la distance a la corde
        #### NOTE :traiter les cas ou possiblement on ira dans le mauvais sens ?
        dD = Mes.v_mesure[k] * par.dt
        avance = 0
        ind_avance = np.int(Mes.ind_parcours_mesure[k])
        dx = 0
        dy = 0

        # decordage_brut = float(Mes.stock_distance_corde_brut[k, -1] - \
        #                 Mes.stock_distance_corde_brut[k, -2])

        #if abs(decordage_brut) > par.decordage_max:
        #    Mes.Obs = [0, 0, 0]
        #    print "decordage " + str(liste_id[k])

        while avance < dD and ind_avance < np.size(corde_interpol_x):
            # vecteur orthogonal a la corde entre corde_ext et corde
            # On avance d'un indice dans le parcours,
            vect_eq_x = corde_ext_interpol_x[ind_avance] - corde_interpol_x[ind_avance]
            vect_eq_y = corde_ext_interpol_y[ind_avance] - corde_interpol_y[ind_avance]
            norm_vect = np.sqrt(np.square(vect_eq_x) + np.square(vect_eq_y))
            vect_eq_x = vect_eq_x / norm_vect
            vect_eq_y = vect_eq_y / norm_vect
            # et on replace le point à distance constante à  la corde
            nouveau_x = corde_interpol_x[ind_avance] + vect_eq_x * Mes.distance_corde_mesure[k]
            # + vect_eq_x # update 0305
            nouveau_y = corde_interpol_y[ind_avance] + vect_eq_y * Mes.distance_corde_mesure[k]
            # + vect_eq_y # update 0305
            dx = nouveau_x - Mes.x_mesure[k]
            dy = nouveau_y - Mes.y_mesure[k]
            avance = np.sqrt(np.square(dx) + np.square(dy))
            ind_avance = ind_avance + 1


        # print "recherche prediction ", corde_interpol_x[int(Mes.ind_parcours_mesure[k])],corde_interpol_y[int(Mes.ind_parcours_mesure[k])] ,nouveau_x, nouveau_y
        # On construit la matrice qui permet de passer de l'état précédent au nouveau point
        norm_ = np.sqrt(np.square(dx) + np.square(dy))
        if norm_ > 0:
            dir_x = dx / norm_
            dir_y = dy / norm_
        else:
            dir_x = 0
            dir_y = 0

        Mat_etat = par.Mat_etat
        Mat_etat[0, 2] = dir_x * par.dt
        Mat_etat[1, 2] = dir_y * par.dt

        prev_etat = Mes.Etat
        prev_P = Mes.P_all_id[k, :, :]

        ### covariance en fonction du mode gps
        #cov_etat = np.diag(par.cov_etat)
        #cov_obs = np.diag([par.cov_mode_pos[int(trame[5])],
        #                   par.cov_mode_pos[int(trame[5])], par.cov_mode_v])

        ######### Covariance de l'observation
        mode = int(trame[5])

        cov_v = par.max_cov_v
        if mode == 1 or mode == 2:
            Mes.count_mode[k, 1] = Mes.count_mode[k, 1] + 1
            Mes.count_mode[k, 2] = Mes.count_mode[k, 2] + 1
            Mes.count_mode[k, 4] = 0
            Mes.count_mode[k, 5] = 0
            cov_v = par.max_cov_v - np.exp(- np.square(float(Mes.count_mode[k,mode]) / float(par.sigma_dec_cov)) / 2) * float(par.max_cov_v -\
                                                par.min_cov_v)

        elif mode == 4 or mode == 5:
            Mes.count_mode[k, 4] = Mes.count_mode[k, 4] + 1
            Mes.count_mode[k, 5] = Mes.count_mode[k, 5] + 1
            Mes.count_mode[k, 1] = 0
            Mes.count_mode[k, 2] = 0

        cov_pos = np.exp(- np.square(float(Mes.count_mode[k,mode]) / float(par.sigma_dec_cov)) / 2) * float(par.max_cov_mode[mode] -\
                                                par.min_cov_mode[mode]) + par.min_cov_mode[mode]

        cov_obs = np.diag(np.square([cov_pos, cov_pos, cov_v]))

        ######## Covariance de l'état
        if Mes.avance_mesure[k] > dist_totale - 300:
            cov_etat = par.max_cov_etat - max(0,(dist_totale - Mes.avance_mesure[k])) / float(300) * (par.max_cov_etat -\
                par.min_cov_etat)
            cov_etat = np.diag(np.square(cov_etat))
        else:
            Mes.count_kalman[k] = Mes.count_kalman[k] + 1
            cov_etat = np.exp(- np.square(float(Mes.count_kalman[k]) / float(par.sigma_dec_cov_etat)) / 2) *\
                       (par.max_cov_etat - par.min_cov_etat) + par.min_cov_etat
            cov_etat = np.diag(np.square(cov_etat))

        return Mes, Mat_etat, cov_obs, cov_etat, prev_etat, prev_P

    except:
        msg_udp = "probleme dans la fonction recherche_prediction#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        # sender_udp.sendto(msg_udp, (hote, port_sender))
        prev_etat = Mes.Etat
        prev_P = Mes.P_all_id[k, :, :]

        return Mes, np.eye(3),np.eye(3),np.eye(3), prev_etat, prev_P

def calcul_corde(Mes, k):
    """

    :param Mes: 
    :param k: 
    :return: 
    """
    #### Calcul de la distance a la corde pour l'etat

    x = Mes.Etat[0]
    y = Mes.Etat[1]

    deb_search = int(np.minimum(np.maximum(0, Mes.ind_parcours_mesure[k] - 1000), np.size(corde_interpol_x)))
    fin_search = int(np.minimum(np.maximum(0, Mes.ind_parcours_mesure[k] + 10000), np.size(corde_interpol_x)))
    dist_corde_tableau = np.square(corde_interpol_x[deb_search:fin_search] - x) \
                         + np.square(corde_interpol_y[deb_search:fin_search] - y)
    ind_parcours = deb_search + np.argmin(dist_corde_tableau)

    if ind_parcours > Mes.ind_parcours_mesure[k]:
        dist_corde = np.sqrt(np.min(dist_corde_tableau))
        d_avance = np.sum(dD_corde_2[int(Mes.ind_parcours_mesure[k]):int(ind_parcours)])
    else: # si l'état recule, on garde l'état précédent
        # dist_corde = np.sqrt(np.min(dist_corde_tableau))
        # d_avance = np.sum(dD_corde_2[int(Mes.ind_parcours_mesure[k]):int(ind_parcours)])

        print "recul etat ", k, Mes.ind_parcours_mesure[k], ind_parcours
        dist_corde = Mes.stock_distance_corde[k]
        ind_parcours = Mes.ind_parcours_mesure[k]
        d_avance = 0
        Mes.Etat[0] = Mes.x_mesure[k]
        Mes.Etat[1] = Mes.y_mesure[k]

    return Mes, d_avance, ind_parcours, dist_corde

def calcul_corde_brut(Mes, k, trame):
    """
    :param Mes: 
    :param k: 
    :return: 
    """
    #### Calcul de la distance a la corde pour l'etat

    x = lat_to_m(trame[2] - centre_lat, centre_lat)
    y = lon_to_m(trame[3] - centre_long, centre_lat)

    deb_search = int(np.minimum(np.maximum(0, Mes.ind_parcours_mesure[k] - 1000), np.size(corde_interpol_x)))
    fin_search = int(np.minimum(np.maximum(0, Mes.ind_parcours_mesure[k] + 10000), np.size(corde_interpol_x)))
    dist_corde_tableau = np.square(corde_interpol_x[deb_search:fin_search] - x) \
                         + np.square(corde_interpol_y[deb_search:fin_search] - y)
    ind_parcours = deb_search + np.argmin(dist_corde_tableau)

    dist_corde = np.sqrt(np.min(dist_corde_tableau))

    return dist_corde

def format_sortie_rien(k):
    """
    format pour les sorties nulles
    :param k: 
    :return: 
    """
    dict_indicateur = dict()
    dict_indicateur = {"Capt": [], "Tmes": [], "Pos": {"lat": [], "long": []},
                       "Vit": [],
                       "PosC": [], "DrDp": [],
                       "DpDp": [], "Qcor": [], "Pcen": [],
                       "Eprm": [], "Axl": [], "TDLD": [], "RKRD": [], "RKPD": [],
                       "Pcou": [],
                       "Plon": [],
                       "Epre": [], "Vmax": [], "Vmoy": [], "Dprm": [], "Dcor": [],
                       "DmCo": [],
                       "HedA": [], "HedR": [], "Qmod": [], "Tdep": []}
    dict_indicateur["Tmes"] = int(0)
    dict_indicateur["Capt"] = str(int(liste_id[k]))
    dict_indicateur["Pos"]["lat"] = 0.0
    dict_indicateur["Pos"]["long"] = 0.0
    dict_indicateur["Vit"] = 0.0
    dict_indicateur["PosC"] = 0
    dict_indicateur["DrDp"] = 0
    dict_indicateur["DpDp"] = 0
    dict_indicateur["Qcor"] = 0
    dict_indicateur["Qmod"] = 0
    dict_indicateur["Pcen"] = 0
    dict_indicateur["Eprm"] = 0
    dict_indicateur["Axl"] = 0.0
    dict_indicateur["TDLD"] = 0
    dict_indicateur["RKRD"] = 0
    dict_indicateur["RKPD"] = 0
    dict_indicateur["Pcou"] = 0
    dict_indicateur["Plon"] = 0
    dict_indicateur["Epre"] = 0
    dict_indicateur["Vmax"] = 0
    dict_indicateur["Vmoy"] = 0
    dict_indicateur["Dprm"] = 0
    dict_indicateur["Dcor"] = 0
    dict_indicateur["DmCo"] = 0
    dict_indicateur["Tdep"] = 0
    dict_indicateur["Dep"] = 0
    dict_indicateur["Reac"] = 0
    dict_indicateur["Ariv"] = 0
    dict_indicateur["HedA"] = 0
    dict_indicateur["HedR"] = 0

    return dict_indicateur

def format_sortie_GPS(k, Mes, Ind):
    """
    format pour les sorties gps brutes

    :param k: 
    :param Mes: 
    :param Ind: 
    :return: 
    """
    dict_indicateur = dict()
    dict_indicateur = {"Capt": [], "Tmes": [], "Pos": {"lat": [], "long": []},
                       "Vit": [],
                       "PosC": [], "DrDp": [],
                       "DpDp": [], "Qcor": [], "Pcen": [],
                       "Eprm": [], "Axl": [], "TDLD": [], "RKRD": [], "RKPD": [],
                       "Pcou": [],
                       "Plon": [],
                       "Epre": [], "Vmax": [], "Vmoy": [], "Dprm": [], "Dcor": [],
                       "DmCo": [],
                       "HedA": [], "HedR": [], "Qmod": [], "Tdep": []}
    dict_indicateur["Tmes"] = int(Ind.ts_ind[k])
    dict_indicateur["Capt"] = str(int(Ind.id_ind[k]))
    Ind.pos_cheval_ind["long"] = Mes.long_mesure[k]
    Ind.pos_cheval_ind["lat"] = Mes.lat_mesure[k]
    dict_indicateur["Pos"]["lat"] = Ind.pos_cheval_ind["lat"]
    dict_indicateur["Pos"]["long"] = Ind.pos_cheval_ind["long"]
    dict_indicateur["Vit"] = 0.0
    dict_indicateur["PosC"] = 0
    dict_indicateur["DrDp"] = 0
    dict_indicateur["DpDp"] = 0
    dict_indicateur["Qcor"] = 0
    dict_indicateur["Qmod"] = int(Ind.mode[k])
    dict_indicateur["Pcen"] = 0
    dict_indicateur["Eprm"] = 0
    dict_indicateur["Axl"] = 0.0
    dict_indicateur["TDLD"] = 0
    dict_indicateur["RKRD"] = 0
    dict_indicateur["RKPD"] = 0
    dict_indicateur["Pcou"] = 0
    dict_indicateur["Plon"] = 0
    dict_indicateur["Epre"] = 0
    dict_indicateur["Vmax"] = 0
    dict_indicateur["Vmoy"] = 0
    dict_indicateur["Dprm"] = 0
    dict_indicateur["Dcor"] = 0
    dict_indicateur["DmCo"] = 0
    dict_indicateur["Tdep"] = 0
    dict_indicateur["Dep"] = 0
    dict_indicateur["Reac"] = 0
    dict_indicateur["Ariv"] = 0
    dict_indicateur["HedA"] = 0
    dict_indicateur["HedR"] = 0

    return dict_indicateur

def format_sortie_full(k, Mes, Ind):
    """
    format données métier enrichies
    :param k: 
    :param Mes: 
    :param Ind: 
    :return: 
    """
    dict_indicateur = dict()
    dict_indicateur = {"Capt": [], "Tmes": [], "Pos": {"lat": [], "long": []},
                       "Vit": [],
                       "PosC": [], "DrDp": [],
                       "DpDp": [], "Qcor": [], "Pcen": [],
                       "Eprm": [], "Axl": [], "TDLD": [], "RKRD": [], "RKPD": [],
                       "Pcou": [],
                       "Plon": [],
                       "Epre": [], "Vmax": [], "Vmoy": [], "Dprm": [], "Dcor": [],
                       "DmCo": [],
                       "HedA": [], "HedR": [], "Qmod": [], "Tdep": []}

    dict_indicateur["Tmes"] = int(Ind.ts_ind[k])
    dict_indicateur["Capt"] = str(int(Ind.id_ind[k]))
    Ind.pos_cheval_ind["long"] = np.round(Mes.long_mesure[k], 8)
    Ind.pos_cheval_ind["lat"] = np.round(Mes.lat_mesure[k], 8)
    dict_indicateur["Pos"]["lat"] = Ind.pos_cheval_ind["lat"]
    dict_indicateur["Pos"]["long"] = Ind.pos_cheval_ind["long"]
    dict_indicateur["Vit"] = np.round(Mes.v_mesure[k], 2)
    dict_indicateur["PosC"] = int(Ind.classement_cheval_ind[k])
    dict_indicateur["DrDp"] = np.round(Ind.dist_parcourue_reelle_ind[k], 2)
    dict_indicateur["DpDp"] = np.round(Ind.dist_parcourue_proj_ind[k], 2)
    if Ind.PC_franchis[k]:
        dict_indicateur["Tcle"] = int(Ind.temps_pass_pc_ind[k])
        dict_indicateur["Dcle"] = Ind.pc_ind[k]
        dict_indicateur["RKRP"] = int(Ind.red_km_reelle_pc_ind[k])  # FFV15
        dict_indicateur["RKPP"] = int(Ind.red_km_proj_pc_ind[k])  # FFV15

    dict_indicateur["Qcor"] = int(float(Ind.qualite_donnee_ind[k]) * float(100))
    dict_indicateur["Qmod"] = int(Ind.mode[k])
    dict_indicateur["Pcen"] = int(Ind.pourc_progr_ind[k] * 100)
    dict_indicateur["Eprm"] = np.round(Ind.ecart_proj_premier_ind[k], 2)
    dict_indicateur["Axl"] = Ind.acc_lisse_ind[k]
    dict_indicateur["TDLD"] = int(Ind.temps_passe_depart_ind[k])
    dict_indicateur["RKRD"] = int(Ind.red_km_reelle_ind[k])  # FFV15
    dict_indicateur["RKPD"] = int(Ind.red_km_proj_ind[k])  # FFV15

    dict_indicateur["Pcou"] = int(Ind.cheval_traj_court_ind[k])  # ffv15
    dict_indicateur["Plon"] = int(Ind.cheval_trajet_long_ind[k])  # ffv15
    dict_indicateur["Epre"] = round(Ind.ecart_cheval_prec_ind[k], 2)
    dict_indicateur["Vmax"] = round(Ind.v_pointe_cheval_ind[k], 2)
    dict_indicateur["Vmoy"] = round(Ind.v_moy_cheval_ind[k], 2)
    dict_indicateur["Dprm"] = round(Ind.dist_restant_corde_premier_ind[k], 2)
    dict_indicateur["Dcor"] = round(Ind.dist_inst_corde_cheval_ind[k], 2)
    dict_indicateur["DmCo"] = round(Ind.dist_moy_corde_ind[k], 2)
    dict_indicateur["Tdep"] = int(Ind.Tdep[k])

    dict_indicateur["Dep"] = int(Ind.franchissement_depart_ind[k])
    dict_indicateur["Reac"] = int(Ind.t_reac_sortie_ind[k])
    dict_indicateur["Ariv"] = int(Ind.franchissement_arrivee_ind[k])

    if int(Ind.heading_abs_ind[k]) >= 0:
        dict_indicateur["HedA"] = int(Ind.heading_abs_ind[k])
    else:
        dict_indicateur["HedA"] = int(Ind.heading_abs_ind[k] + 360)
    if int(Ind.heading_rel_ind[k]) >= 0:
        dict_indicateur["HedR"] = int(Ind.heading_rel_ind[k])
    else:
        dict_indicateur["HedR"] = int(Ind.heading_rel_ind[k] + 360)

    return dict_indicateur

def heading_relatif(Mes, Ind,k):
    """
    Calcul de l'indicateur heading relatif 
    :param Mes: 
    :param Ind: 
    :param k: 
    :return: 
    """
    try:
        vect_corde_x = corde_interpol_x[int(
            min(Mes.ind_parcours_mesure[k], np.size(corde_interpol_x) - 1))] - corde_interpol_x[
                           int(min(Mes.prev_ind_parcours_mesure[k],
                                   np.size(corde_interpol_x) - 1))]
        vect_corde_y = corde_interpol_y[int(
            min(Mes.ind_parcours_mesure[k], np.size(corde_interpol_y) - 1))] - corde_interpol_y[
                           int(min(Mes.prev_ind_parcours_mesure[k],
                                   np.size(corde_interpol_y) - 1))]
        vect_cheval_x = Mes.x_mesure[k] - Mes.prev_x_mesure[k]
        vect_cheval_y = Mes.y_mesure[k] - Mes.prev_y_mesure[k]
        norm_ch = np.sqrt(np.square(vect_cheval_x) + np.square(vect_cheval_y))
        norm_corde = np.sqrt(np.square(vect_corde_x) + np.square(vect_corde_y))
        if norm_ch > 0:
            vect_cheval_x = vect_cheval_x / norm_ch
            vect_cheval_y = vect_cheval_y / norm_ch
        if norm_corde > 0:
            vect_corde_x = vect_corde_x / norm_corde
            vect_corde_y = vect_corde_y / norm_corde
        try:
            prod_scal = vect_cheval_x * vect_corde_x + vect_cheval_y * vect_corde_y
            if abs(prod_scal) < 1:
                heading_rel_inst = np.degrees(np.arccos(prod_scal))
            else:
                heading_rel_inst = 0

        except:
            heading_rel_inst = 0
        # lissage du heading relatif

        Ind.stock_heading_rel_1s[k, :] = np.append(Ind.stock_heading_rel_1s[k, 1:],
                                                        heading_rel_inst)
        Ind.heading_rel_ind[k] = np.mean(Ind.stock_heading_rel_1s[k, :])

        return Mes, Ind
    except:
        msg_udp = "ErreurMoteur: probleme dans la fonction heading_relatif#"
        print msg_udp
        logging.error(msg_udp, exc_info = True)
        #sender_udp.sendto(msg_udp, (hote, port_sender))

class Parametres:
    """
	Classe des paramètres qui seront utilisés dans l'algorithme :
	"""

    def __init__(self):
        self.size_trame = 7
        # Pour l'interpolation du parcours
        self.res_interp = 1000  # resolution de l'interpolation
        self.N_interp = 5  # On interpole en utilisant N points avant et apres

        # distance à la corde de la corde_2
        self.dist_corde2 = 1  # 1 si trot, 2 si galop

        # Parametres moteur
        self.dt = 0.1
        self.Hz = 10

        # Pour le filtre de Kalman
        self.Mat_etat = np.eye(3)
        self.cov_mode_pos = [100, 3, 1.5, 1, 0.03, 0.5] # [100, 2, 0.8, 1, 0.03, 0.2]) #
        self.cov_mode_v = np.float(0.1) / np.float(3.6)
        self.cov_etat = np.square(np.array([0.4, 0.4, 0.2]) * self.dt)  # np.square(np.array([0.2, 0.2, 0.1]) * self.dt)

        self.max_cov_etat = np.array([2, 2, 0.3]) * self.dt  # np.array([0.4, 0.4, 0.2]) * self.dt #
        self.min_cov_etat = np.array([0.5, 0.5, 0.1]) * self.dt  # self.max_cov_etat  #
        self.duree_dec_cov_etat = 30 * self.Hz
        self.sigma_dec_cov_etat = self.duree_dec_cov_etat / 2

        self.max_cov_v = 0.5 / np.float(3.6)
        self.min_cov_v = 0.1 / np.float(3.6) # 0.03 / np.float(3.6)
        self.max_cov_mode = [100, 5, 2, 1, 0.03, 0.5] # [100, 3, 1.5, 1, 0.03, 0.5]  #
        self.min_cov_mode = [100, 2, 0.8, 1, 0.03, 0.5] # self.max_cov_mode  #
        self.duree_dec_cov = 3 * self.Hz  # n secondes
        self.sigma_dec_cov = self.duree_dec_cov / 2

        # Paramètres de détection du départ
        self.seuil_points_parcours = 10
        self.seuil_points_recul = 10
        self.seuil_duree_reinit = 20
        self.seuil_v_depart = 20 / 3.6 # m/s

        self.seuil_persistence = 2

        # Paramètres gestion stock de trames
        self.facteur_seuil_stock = 5
        self.retard_stock = 300

        self.taille_stock_dist = 10

        self.decordage_max = 0.5

class Mesures:
    """ 
    Classe qui contient toutes les mesures
    """

    def __init__(self, nb_id, par):
        self.ts_passage_dep = np.zeros(nb_id)
        self.TS_dep = 0

        self.indice_trame = 0
        self.Obs = [0, 0, 0]
        self.prev_Obs = [0, 0, 0]
        self.Etat_all_id = np.zeros((nb_id, 3))
        self.Etat = [0, 0, 0]
        # self.trames = np.zeros((nb_id, par.size_trame)) ## UPDATE 1205 nouveau format trame

        self.indice_parcours_mesure = np.zeros(nb_id) - 1

        self.stock_proche_corde = np.zeros(
            nb_id)  # on stocke le point de la corde le + proche de l'etat pour chaque cheval
        self.stock_distance_corde = np.zeros(nb_id) + 1000  # distance a la corde pour chaque cheval

        ### Mesures
        self.lat_mesure = np.zeros(nb_id)
        self.long_mesure = np.zeros(nb_id)
        self.prev_lat_mesure = np.zeros(nb_id)
        self.prev_long_mesure = np.zeros(nb_id)
        self.avance_mesure = np.zeros(nb_id)

        self.distance_corde_mesure = np.zeros(nb_id)
        self.or_mesure = np.zeros(nb_id)
        self.v_mesure = np.zeros(nb_id)
        self.ts_mesure = np.zeros(nb_id)
        self.precision_mesure = np.zeros(nb_id)
        self.ind_parcours_mesure = np.zeros(nb_id)
        self.prev_ind_parcours_mesure = np.zeros(nb_id)
        self.prev_x_mesure = np.zeros(nb_id)
        self.prev_y_mesure = np.zeros(nb_id)
        self.x_mesure = np.zeros(nb_id)
        self.y_mesure = np.zeros(nb_id)
        self.num_trames_recues = np.zeros(nb_id)
        self.P_all_id = np.zeros((nb_id, 3, 3))
        self.mode_gps = np.zeros(nb_id)

        self.depart_franchis = [False] * nb_id
        self.arr_franchis = [False] * nb_id

        ### nouvelle détection départ
        self.x_brute = np.zeros(nb_id)
        self.y_brute = np.zeros(nb_id)
        self.vit_brute = np.zeros(nb_id)
        self.prev_x_brute = np.zeros(nb_id)
        self.prev_y_brute = np.zeros(nb_id)
        self.ind_parcours_brut = np.zeros(nb_id)
        self.prev_ind_parcours_brut = np.zeros(nb_id)
        self.prev_vit_brute = np.zeros(nb_id)
        self.count_recul = np.zeros(nb_id)
        self.count_parcours_ok = np.zeros(nb_id)
        self.T_detect = np.zeros(nb_id)
        self.stock_vit_brute = np.zeros((nb_id, par.seuil_points_parcours))
        self.distance_corde_brut = np.zeros(nb_id)
        self.stock_distance_corde_brut = np.zeros((nb_id, par.taille_stock_dist))

        self.count_persistence = np.zeros(nb_id)

        ### Pour le calcul de la cov selon le mode
        self.count_mode = np.zeros((nb_id, 6))
        self.count_kalman = np.zeros(nb_id)

class Indicateurs:
    """ Classe qui contient tous les indicateurs """

    def __init__(self, nb_id, par):
        self.id_ind = np.zeros(nb_id)
        self.ts_ind = np.zeros(nb_id)
        self.pos_cheval_ind = {"lat": np.zeros(nb_id), "long": np.zeros(nb_id)}
        self.v_inst_cheval_ind = np.zeros(nb_id)
        self.classement_cheval_ind = np.zeros(nb_id)
        self.dist_parcourue_reelle_ind = np.zeros(nb_id)
        self.dist_parcourue_proj_ind = np.zeros(nb_id)
        self.temps_pass_pc_ind = np.zeros(nb_id)
        self.pc_ind = [""] * nb_id
        self.red_km_reelle_pc_ind = np.zeros(nb_id) # [''] * nb_id #FFV15
        self.red_km_proj_pc_ind = np.zeros(nb_id) # [''] * nb_id #FFV15
        self.qualite_donnee_ind = np.zeros(nb_id)
        self.pourc_progr_ind = np.zeros(nb_id)
        self.ecart_proj_premier_ind = np.zeros(nb_id)
        self.acc_lisse_ind = np.zeros(nb_id)
        self.temps_passe_depart_ind = np.zeros(nb_id)
        self.red_km_reelle_ind = np.zeros(nb_id) # [''] * nb_id #FFV15
        self.red_km_proj_ind = np.zeros(nb_id) # [''] * nb_id #FFV15
        self.cheval_traj_court_ind = np.zeros(nb_id) # ['N'] * nb_id # FFV15
        self.cheval_trajet_long_ind = np.zeros(nb_id) # ['N'] * nb_id # FFV15
        self.ecart_cheval_prec_ind = np.zeros(nb_id)
        self.v_pointe_cheval_ind = np.zeros(nb_id)
        self.v_moy_cheval_ind = np.zeros(nb_id)
        self.dist_restant_corde_premier_ind = np.zeros(nb_id)
        self.dist_inst_corde_cheval_ind = np.zeros(nb_id)
        self.dist_moy_corde_ind = np.zeros(nb_id)
        self.t_reac_sortie_ind = np.zeros(nb_id)
        self.franchissement_depart_ind = np.zeros(nb_id) # ['N'] * nb_id # FFV15
        self.franchissement_arrivee_ind = np.zeros(nb_id) # ['N'] * nb_id # FFV15
        self.heading_abs_ind = np.zeros(nb_id)
        self.heading_rel_ind = np.zeros(nb_id)

        self.ts_dep = np.zeros(nb_id)
        self.ts_arr = np.zeros(nb_id)

        self.stock_v_1s = np.zeros((nb_id, par.Hz * 1))  # 1s
        self.stock_acc_1s = np.zeros((nb_id, par.Hz * 1))  # 1s
        self.en_course = np.zeros(nb_id)  #### 1 entre depart et arrivee
        self.n_en_course = np.zeros(nb_id)
        self.etat_cheval = np.ones(nb_id)  #### flux binaire
        self.ind_porte_courante = np.zeros(nb_id)

        self.avance_deb = np.zeros(nb_id)
        self.PC_franchis = np.zeros(nb_id)

        self.stock_heading_abs_1s = np.zeros((nb_id, par.Hz * 1))  # 1s
        self.stock_heading_rel_1s = np.zeros((nb_id, par.Hz * 1))  # 1s

        # Initialisation variables
        self.stock_v_1s = np.zeros((nb_id, par.Hz * 1))  # 1s
        self.stock_acc_1s = np.zeros((nb_id, par.Hz * 1))  # 1s
        self.en_course = np.zeros(nb_id)  #### 1 entre depart et arrivee
        self.n_en_course = np.zeros(nb_id)
        self.ind_porte_courante = np.zeros(nb_id)

        self.cheval_trajet_court = 0
        self.cheval_trajet_long = 0
        self.arrive = np.zeros(nb_id)

        self.mode = np.zeros(nb_id)
        self.Tdep = np.zeros(nb_id)

        self.count_precision_2m = np.zeros(nb_id)
        self.donnee_precise = np.ones(nb_id)

class Moteur:
    def __init__(self,par, nb_id,handicaps,dist_course_handicap, handicaps_recus):
        self.id_porte_dep = []
        self.num_analyse = -1
        self.tous_arrives = 0
        self.top_depart = 0
        self.Mes = ''
        self.Ind = ''
        self.TS_DEPART = 0
        self.frames = FRAMES()
        self.handicaps = []
        self.nb_handicaps = 0
        try:
            ##### INIT DONNEES #####
            self.Ind = Indicateurs(nb_id, par)
            self.Mes = Mesures(nb_id, par)
            self.TS_DEPART = 0
            self.num_analyse = -1
            #### Intégration des handicaps
            self.nb_handicaps = np.size(dist_course_handicap) - 1
            if not handicaps_recus:
                if self.nb_handicaps:
                    self.handicaps = np.ones(nb_id) * dist_course_handicap[0]
                else:
                    self.handicaps = np.ones(nb_id) * dist_course_handicap
            else:
                self.handicaps = handicaps
            self.id_porte_dep = np.zeros(nb_id)
            for i in range(0, nb_id):
                self.id_porte_dep[i] = np.argmin(np.abs(self.handicaps[i] - dist_course_handicap))
        except:
            msg_udp = "ErreurMoteur: impossible d'initialiser le moteur"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
            #try:
            #    sender_udp.sendto(msg_udp, (hote, port_sender))
            #except:
            #    pass

    def boucle_traitement(self):
        global etats_partants
        global etats_capteurs
        global RESTART
        global FIN_COURSE
        global DEPART_COURSE
        global COURSE_DEMARREE
        global handicaps
        global connexion_avec_serveur
        global par
        global frames
        global t_start
        global t
        global stock_trames
        global TS_traitement
        global NUM_trames_recues
        global debut_traitement
        # gestion des états transmis via udp
        self.top_depart = 0

        if RESTART:  # gestion du restart

            msg_udp = "EvtMoteur: restart: reinit donnees#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            self.Mes = Mesures(nb_id, par)
            self.Ind = Indicateurs(nb_id, par)
            RESTART = 0
            COURSE_DEMARREE = 0
            COURSE_TERMINEE = 0

        if DEPART_COURSE:
            COURSE_DEMARREE = 1
            self.tous_arrives = 0

            msg_udp = "EvtMoteur: top depart#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))

            DEPART_COURSE = 0
            COURSE_TERMINEE = 0
            self.top_depart = 1

        if FIN_COURSE:
            COURSE_TERMINEE = 1
            FIN_COURSE = 0

            msg_udp = "EvtMoteur: fin course reçu#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))

        self.num_analyse = self.num_analyse + 1
        # print "********", self.num_analyse
        # gestion du mode d'émission
        if MODE == "attente":
            self.Ind = Indicateurs(nb_id, par)
            par.seuil_persistence = 2
            ##### début du moteur
            stock_trames = dict()
            TS_traitement = 0
            NUM_trames_recues = 0
            debut_traitement = False
            for k in range(0, nb_id):
                stock_trames[str(k)] = []
        else:
            par.seuil_persistence = 50

        #print "**** Acquisition des trames recues"
        #frames.lock.acquire()
        #print np.size(frames.content)
        self.frames.content = frames #.content
        frames = []
        #frames.lock.release()
        #print np.size(self.frames.content)
        if np.size(self.frames.content) == 0:
            msg_udp = "ErreurMoteur: pas de trame recue #"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
            #sender_udp.sendto(msg_udp, (hote, port_sender))

        #### sauvegarde data brute: écrit les data brutes recues dans un ficheir csv
        if np.size(self.frames.content) > 0:
            if np.size(self.frames.content) == par.size_trame:
                with open('data_brute' + str(t_start) + '.csv', 'a') as csvfile:
                    spamwriter = csv.writer(csvfile, delimiter=';')
                    spamwriter.writerow(frames)
            else:
                for frame in self.frames.content:
                    with open('data_brute' + str(t_start) + '.csv', 'a') as csvfile:
                        spamwriter = csv.writer(csvfile, delimiter=';')
                        spamwriter.writerow(frame)

        with open('data_brute' + str(t_start) + '.csv', 'a') as csvfile:
            spamwriter = csv.writer(csvfile, delimiter=';')
            spamwriter.writerow([int(time.time())])
        #### fin sauvegarde

        if MODE == "course":
            # Ici on gère le stock de trames. Dès qu'on a recu suffisamment de trames, on assigne à la variable
            # TS_traitement la valeur médiane des dernières trames recues par capteur - retard_stock.
            # A chaque boucle TS_traitement s'incremente de 100 milli.
            premier_traitement = False
            if NUM_trames_recues < int(par.facteur_seuil_stock * nb_id):
                debut_traitement = False
            for k in range(0, nb_id):
                trame, trame_recue = decoupage_trames(k, self.frames.content)
                if trame_recue:
                    NUM_trames_recues = NUM_trames_recues + 1

                if NUM_trames_recues >= int(par.facteur_seuil_stock * nb_id) and not debut_traitement:

                    premier_traitement = True
                    debut_traitement = True
                    ts_recents = []
                    for k in range(0,nb_id):
                        if np.size(ts_recents) > 0:
                            if np.size(stock_trames[str(k)]) == par.size_trame:
                                ts_recents = np.append(ts_recents,stock_trames[str(k)][1])
                            elif np.size(stock_trames[str(k)]) > par.size_trame:
                                ts_recents = np.append(ts_recents,stock_trames[str(k)][-1,1])
                        else:
                            if np.size(stock_trames[str(k)]) == par.size_trame:
                                ts_recents = [stock_trames[str(k)][1]]
                            elif np.size(stock_trames[str(k)]) > par.size_trame:
                                ts_recents = [stock_trames[str(k)][-1,1]]

                    TS_traitement = np.median(ts_recents) - par.retard_stock
                    TS_traitement = int(np.round(TS_traitement / float(100)) *100)
                    print ts_recents
                    print TS_traitement

            if TS_traitement > 0 and not premier_traitement:
                TS_traitement = TS_traitement + 100
        else:
            stock_trames = dict()
            TS_traitement = 0
            NUM_trames_recues = 0
            # print "attente"
            for i in range(0, nb_id):
                stock_trames[str(i)] = []
            debut_traitement = False
        # print NUM_trames_recues, int(par.facteur_seuil_stock * nb_id)

        self.Ind.PC_franchis = np.zeros(nb_id)
        if MODE == "attente":
            self.Ind = Indicateurs(nb_id, par)
            self.Mes = Mesures(nb_id, par)

        # Si tous les chevaux sont arrivés, on réinitialise
        # if np.sum(Ind.arrive) == np.sum(etats_partants) and not tous_arrives: #and COURSE_TERMINEE
        if not self.tous_arrives:
            ok_arriv = True
            # On ckecke si tous les partants sont bien arrivés.
            for k in range(0, nb_id):
                if etats_partants[k]:
                    if not self.Ind.arrive[k]:
                        ok_arriv = False

            if ok_arriv: # Si oui, on reinit les sorties.
                self.Ind = Indicateurs(nb_id, par)
                self.Mes = Mesures(nb_id, par)
                etats_partants = np.zeros(nb_id)
                COURSE_DEMARREE = 0
                self.tous_arrives = 1
                msg_udp = "tous arrives"
                print msg_udp
                logging.info(msg_udp)
                #sender_udp.sendto(msg_udp, (hote, port_sender))

        if self.top_depart:
            msg_udp = "EvtMoteur: self.TS_DEPART " + str(self.TS_DEPART) + "#"
            print msg_udp
            logging.info(msg_udp)
            #sender_udp.sendto(msg_udp, (hote, port_sender))

        #print "TS_traitement", TS_traitement
        for k in range(0, nb_id):
            if etats_capteurs[k] > 0:
                if MODE == "course":
                    # on stocke pour chaque capteur toutes les trames recues > à TS_traitement, et on supprime les autres
                    trame_trouvee = -1
                    id_trash = -1
                    stock = np.array(stock_trames[str(k)])
                    if TS_traitement > 0 and np.size(stock) > 0:
                        if np.size(stock) == par.size_trame: # si une seule trame dans le stock
                            donnee = stock
                            try:
                                if donnee[1] < TS_traitement:
                                    id_trash = 0
                                if donnee[1] == TS_traitement:
                                    trame_trouvee = 0
                            except:
                                if donnee[0,1] < TS_traitement:
                                    id_trash = 0
                                if donnee[0,1] == TS_traitement:
                                    trame_trouvee = 0
                        elif np.size(stock) > par.size_trame:
                            for i in range(0, np.size(stock[:,1])):
                                donnee = stock[i,:]
                                if donnee[1] < TS_traitement:
                                    id_trash = i
                                if donnee[1] == TS_traitement:
                                    trame_trouvee = i

                    if trame_trouvee >=0:
                        trame_recue = True
                        stock = np.array(stock_trames[str(k)])
                        if np.size(stock) == par.size_trame:
                            try:
                                trame = stock[0,:]
                            except:
                                trame = stock
                            stock_trames[str(k)] = []
                        elif np.size(stock) > par.size_trame:
                            trame = stock[trame_trouvee,:]
                            if trame_trouvee < np.size(stock[:,1]) - 1:
                                stock_trames[str(k)] = stock[trame_trouvee + 1:,:]
                            else:
                                stock_trames[str(k)] = []

                    elif id_trash >=0:
                        trame_recue = False
                        trame = [0, 0, 0, 0, 0, 0, 0]
                        stock = np.array(stock_trames[str(k)])
                        if np.size(stock) > par.size_trame:
                            if id_trash < np.size(stock[:,1]) - 1:
                                stock_trames[str(k)] = stock[id_trash + 1:,:]
                            else:
                                stock_trames[str(k)] = []
                    else:
                        trame_recue = False
                        trame = [0, 0, 0, 0, 0, 0, 0]
                    # print stock_trames[str(k)]
                else:
                    trame, trame_recue = decoupage_trames_attente(k, self.frames.content)

                ########################################
                ######### Calcul des mesures ###########
                ########################################
                calculer_position = False

                # On recherche si une trame a été recue pour le capteur étudié k
                if trame_recue:
                    self.Mes.count_persistence[k] = 0
                    # print k, trame, self.Mes.ts_mesure[k]
                else:
                    #print stock_trames[str(k)]
                    stock = np.array(stock_trames[str(k)])
                    #try:
                    #    print "pas de trame ", liste_id[k], TS_traitement, stock[0,1], stock[-1,1]
                    #except:
                    #    print "pas de trame ", liste_id[k], TS_traitement

                    self.Mes.count_persistence[k] = self.Mes.count_persistence[k] + 1

                self.Mes.mode_gps[k] = int(trame[5])

                calculer_position, self.Mes = gestion_trame(self.Mes, trame_recue, trame, k)

                if calculer_position and MODE == "course" and etats_capteurs[k] == 2 and not (
                            self.Mes.arr_franchis[
                                k] or self.tous_arrives):  # ajout not tous_arrives 0706 # and not self.Mes.arr_franchis[k]:

                    first_dep = 0
                    recul_parcours = 0
                    depart_parcours = 0
                    # print k, self.Mes.ind_parcours_brut[k], self.Mes.ind_parcours_mesure[k]
                    if (not COURSE_DEMARREE) or (COURSE_DEMARREE and not self.Mes.depart_franchis[k]):
                        self.Mes, depart_parcours, recul_parcours = check_course_capteur(self.Mes, trame, k,
                                                                                    self.id_porte_dep,
                                                                                    self.nb_handicaps)
                        if depart_parcours:
                            first_dep = 1

                    self.Mes.Etat = self.Mes.Etat_all_id[k, :]
                    # On vérifie s'il faut réinitialiser le départ
                    self.Mes, self.Ind, self.TS_DEPART = check_depart_20s(self.Mes, self.Ind, recul_parcours, self.nb_handicaps, \
                                                           self.id_porte_dep, k, self.TS_DEPART,
                                                           COURSE_DEMARREE)

                    if self.Mes.depart_franchis[k] and (not self.Ind.arrive[k]) and (not first_dep):

                        if trame[2] != 0 and trame[3] != 0 and trame[1] != 0:
                            self.Mes, trame = check_bonne_data(trame, self.Mes, k)
                            # Calcul de la prediction, maj des cov et états
                        if self.nb_handicaps:
                            dist_param = dist_course_handicap[int(self.id_porte_dep[k])]
                        else:
                            dist_param = dist_course_handicap

                        if trame[2] != 0 and trame[3] != 0:
                            dist_corde_brut = calcul_corde_brut(self.Mes, k, trame)
                        else:
                            dist_corde_brut = self.Mes.distance_corde_brut[-1]

                        self.Mes.stock_distance_corde_brut[k,:-1] = self.Mes.stock_distance_corde_brut[k, 1:]
                        self.Mes.stock_distance_corde_brut[k,-1] = dist_corde_brut

                        self.Mes, Mat_etat, cov_obs, cov_etat, prev_etat, prev_P = recherche_prediction(self.Mes, k, trame, dist_param)


                        # Passage dans le filtre de Kalman
                        # if self.Mes.Obs[0] == 0:
                        #    print k, "prediction"
                        self.Mes.Etat, P = etape_Kalman(prev_etat, self.Mes.Obs, prev_P, Mat_etat, cov_etat,
                                                   cov_obs)

                        # Calcul de la distance a la corde pour l'etat
                        self.Mes, d_avance, ind_parcours, dist_corde = calcul_corde(self.Mes, k)

                        # Mise à jour des mesures
                        self.Mes.Etat_all_id[k, :] = self.Mes.Etat
                        self.Mes.P_all_id[k, :, :] = P

                        self.Mes.stock_proche_corde[k] = ind_parcours
                        self.Mes.stock_distance_corde[k] = dist_corde
                        distance_corde = dist_corde

                        #### Sortie mesure
                        self.Mes.lat_mesure[k] = m_to_lat(self.Mes.Etat[0],
                                                     centre_lat) + centre_lat  # trame[2] #
                        self.Mes.long_mesure[k] = m_to_lon(self.Mes.Etat[1],
                                                      centre_lat) + centre_long  # trame[3] #
                        self.Mes.avance_mesure[k] = self.Mes.avance_mesure[
                                                   k] + d_avance  # - dD_corde_2[ind_parcours]

                        self.Mes.distance_corde_mesure[k] = distance_corde
                        self.Mes.or_mesure[k] = heading(self.Mes.prev_lat_mesure[k], self.Mes.prev_long_mesure[k],
                                                   self.Mes.lat_mesure[k], self.Mes.long_mesure[k])
                        self.Mes.v_mesure[k] = self.Mes.Etat[2]
                        self.Mes.precision_mesure[k] = np.float(
                            np.sqrt(np.float(P[1, 1]) + np.float(P[0, 0])))
                        self.Mes.prev_lat_mesure[k] = self.Mes.lat_mesure[k]
                        self.Mes.prev_long_mesure[k] = self.Mes.long_mesure[k]
                        self.Mes.prev_ind_parcours_mesure[k] = self.Mes.ind_parcours_mesure[k]
                        self.Mes.ind_parcours_mesure[k] = self.Mes.stock_proche_corde[k]
                        self.Mes.prev_x_mesure[k] = self.Mes.x_mesure[k]
                        self.Mes.prev_y_mesure[k] = self.Mes.y_mesure[k]
                        self.Mes.x_mesure[k] = self.Mes.Etat[0]
                        self.Mes.y_mesure[k] = self.Mes.Etat[1]

                    else:
                        # Si on est en course mais pas dans le parcours et qu'on recoit des donnees gps:
                        if trame[2] != 0 and trame[3] != 0:
                            self.Mes.prev_lat_mesure[k] = trame[2]
                            self.Mes.prev_long_mesure[k] = trame[3]
                            self.Mes.prev_x_mesure[k] = self.Mes.x_mesure[k]
                            self.Mes.prev_y_mesure[k] = self.Mes.y_mesure[k]

                            self.Mes.lat_mesure[k] = trame[2]
                            self.Mes.long_mesure[k] = trame[3]
                            self.Mes.x_mesure[k] = lat_to_m(self.Mes.lat_mesure[k] - centre_lat, centre_lat)
                            self.Mes.y_mesure[k] = lon_to_m(self.Mes.long_mesure[k] - centre_long, centre_lat)
                            self.Mes.Etat_all_id[k, :] = [lat_to_m(trame[2] - centre_lat, centre_lat),
                                                     lon_to_m(trame[3] - centre_long, centre_lat), 0]
                            self.Mes.v_mesure[k] = trame[4]
                            self.Mes.or_mesure[k] = heading(self.Mes.prev_lat_mesure[k], self.Mes.prev_long_mesure[k],
                                                       self.Mes.lat_mesure[k],
                                                       self.Mes.long_mesure[k])
                            self.Mes.avance_mesure[k] = 0
                            self.Mes.distance_corde_mesure[k] = 0
                            self.Mes.ind_parcours_mesure[k] = -1
                            # if  depart_franchis and not self.Ind.arrive[k]:
                            if depart_parcours and not self.Ind.arrive[k]:
                                self.Mes.depart_franchis[k] = 1
                                print "depart franchis " + str(k) + " course demarree: " + str(COURSE_DEMARREE)
                                # self.Mes.ts_passage_dep[k] = self.Mes.ts_mesure[k]
                                if not COURSE_DEMARREE or self.TS_DEPART == 0:
                                    self.TS_DEPART = np.max(self.Mes.ts_mesure)
                                    for l in range(0, nb_id):
                                        if self.Mes.ts_passage_dep[l] < self.TS_DEPART and self.Mes.ts_passage_dep[l] > 0:
                                            self.TS_DEPART = self.Mes.ts_passage_dep[l]
                                            msg_udp = "EvtMoteur: self.TS_DEPART " + str(self.TS_DEPART) + "#"
                                            print msg_udp
                                            logging.info(msg_udp)


                                self.Mes, self.Ind = init_depart(self.Mes, self.Ind, par, self.nb_handicaps, self.id_porte_dep, k)

                                # print k, self.Mes.ind_parcours_brut[k], self.Mes.ind_parcours_mesure[k], self.Mes.stock_distance_corde[k]

                                # print "depart ", str(k), self.Ind.ind_porte_courante[k], \
                                # id_portes[int(self.Ind.ind_porte_courante[k])]
                                msg_udp = "EvtMoteur: depart franchis " + str(k) + "#"
                                print msg_udp
                                logging.info(msg_udp)

                            if self.Mes.arr_franchis[k]:
                                self.Mes.ind_parcours_mesure[k] = np.size(corde_interpol_x) + 1
                                self.Mes.avance_mesure[k] = self.Mes.avance_mesure[k] + self.Mes.v_mesure[k] * par.dt
                                self.Mes.distance_corde_mesure[k] = distance_corde

                            self.Mes.Etat[0] = self.Mes.x_mesure[k]
                            self.Mes.Etat[1] = self.Mes.y_mesure[k]
                            self.Mes.Etat[2] = self.Mes.v_mesure[k]
                            self.Mes.precision_mesure[k] = np.sqrt(par.cov_mode_pos[int(trame[5])])
                        else:
                            self.Mes.v_mesure[k] = 0.0

                else:  # mode attente
                    if trame[2] != 0 and trame[3] != 0:

                        self.Mes.lat_mesure[k] = trame[2]
                        self.Mes.long_mesure[k] = trame[3]

                        self.Mes.x_mesure[k] = lat_to_m(self.Mes.lat_mesure[k] - centre_lat, centre_lat)
                        self.Mes.y_mesure[k] = lon_to_m(self.Mes.long_mesure[k] - centre_long, centre_lat)
                        self.Mes.Etat_all_id[k, :] = [lat_to_m(trame[2] - centre_lat, centre_lat),
                                                 lon_to_m(trame[3] - centre_long, centre_lat), 0]
                        self.Mes.prev_lat_mesure[k] = trame[2]
                        self.Mes.prev_long_mesure[k] = trame[3]
                        self.Mes.v_mesure[k] = trame[4]
                        self.Mes.precision_mesure[k] = np.sqrt(par.cov_mode_pos[int(trame[5])])
                        self.Mes.or_mesure[k] = 0.0
                    else:
                        self.Mes.v_mesure[k] = 0.0

                ##################################################################
                ################## INDICATEURS INDIVIDUELS #######################
                ##################################################################
                self.Ind.id_ind[k] = liste_id[k]
                self.Ind.ts_ind[k] = self.Mes.ts_mesure[k]
                if etats_capteurs[k] == 1:
                    self.Ind.qualite_donnee_ind[k] = self.Mes.precision_mesure[k]
                    if self.Mes.mode_gps[k] == 0:
                        self.Ind.mode[k] = 6
                    elif self.Mes.mode_gps[k] == 1:
                        self.Ind.mode[k] = 7
                    else:
                        self.Ind.mode[k] = 8

                if etats_capteurs[k] == 2:
                    self.Ind.v_inst_cheval_ind[k] = self.Mes.v_mesure[k]
                    self.Ind.qualite_donnee_ind[k] = self.Mes.precision_mesure[k]
                    self.Ind.franchissement_depart_ind[k] = 0  # "N" # FFV15
                    self.Ind.franchissement_arrivee_ind[k] = 0  # "N" # FFV15
                    self.Ind.heading_rel_ind[k] = 0
                    self.Ind.heading_abs_ind[k] = 0
                    self.Ind.dist_inst_corde_cheval_ind[k] = 0
                    self.Ind.dist_restant_corde_premier_ind[k] = 0

                    #### Calcul de Qmod
                    if MODE == "course":
                        self.Ind.mode[k] = self.Mes.mode_gps[k]
                    else:
                        if self.Mes.mode_gps[k] == 0:
                            self.Ind.mode[k] = 6
                        elif self.Mes.mode_gps[k] == 1:
                            self.Ind.mode[k] = 7
                        else:
                            self.Ind.mode[k] = 8

                    #### gestion des données si la précision n'est pas suffisamment bonne:
                    # Si la précision est de plus de 2m pendant + de 5 sec ---> On sort le capteur du classement,
                    # mais les calculs continuent de tourner, et on ne sort aucun indicateur
                    # Si la précision retourne sous les 1m, on remet les ind et le classement pour ce capteur.
                    if self.Ind.en_course[k] and self.Mes.precision_mesure[k] > 2.0 and self.Ind.donnee_precise[k]:
                        self.Ind.count_precision_2m[k] = self.Ind.count_precision_2m[k] + 1
                    else:
                        self.Ind.count_precision_2m[k] = 0

                    if self.Ind.count_precision_2m[k] > 50:
                        msg_udp = "capteur " + str(liste_id[k]) + "sorti " + str(self.num_analyse) + " " + str(self.Mes.ts_mesure[k])
                        print msg_udp
                        self.Ind.donnee_precise[k] = 0
                        self.Ind.count_precision_2m[k] = 0

                    if self.Ind.en_course[k] and self.Mes.precision_mesure[k] < 1.0 and not self.Ind.donnee_precise[k]:
                        self.Ind.donnee_precise[k] = 1
                        msg_udp = "capteur " + str(k) + "re entre " + str(self.num_analyse)
                        print msg_udp

                    if calculer_position and MODE == "course" and not self.tous_arrives:
                        if self.Ind.en_course[k]:
                            if self.TS_DEPART > 0:
                                self.Ind.temps_passe_depart_ind[k] = self.Mes.ts_mesure[k] - self.TS_DEPART
                            else:
                                self.Ind.temps_passe_depart_ind[k] = self.Ind.temps_passe_depart_ind[k] + 100
                            self.Ind.dist_parcourue_reelle_ind[k] = self.Ind.dist_parcourue_reelle_ind[k] + \
                                                               self.Ind.v_inst_cheval_ind[k] * par.dt
                            # if self.Ind.dist_parcourue_reelle_ind[k] < 0:
                            #    print self.Ind.dist_parcourue_reelle_ind[k], self.Ind.v_inst_cheval_ind[k], par.dt

                            self.Ind.dist_parcourue_proj_ind[k] = self.Mes.avance_mesure[k]

                            if self.nb_handicaps:
                                self.Ind.pourc_progr_ind[k] = self.Ind.dist_parcourue_proj_ind[k] / dist_course_handicap[
                                    int(self.id_porte_dep[k])]
                            else:
                                self.Ind.pourc_progr_ind[k] = self.Ind.dist_parcourue_proj_ind[k] / dist_course_handicap

                            if self.Ind.dist_parcourue_reelle_ind[k] > 20:  # on ne calcule qu'à partir de 20 m parcourus
                                self.Ind.red_km_reelle_ind[k] = float(self.Ind.temps_passe_depart_ind[k]) / float(
                                    self.Ind.dist_parcourue_reelle_ind[k]) * float(1000)

                            if self.Ind.dist_parcourue_proj_ind[k] > 20:  # on ne calcule qu'à partir de 20 m parcourus
                                self.Ind.red_km_proj_ind[k] = float(self.Ind.temps_passe_depart_ind[k]) / float(
                                    self.Ind.dist_parcourue_proj_ind[k]) * float(1000)

                            if self.Ind.v_pointe_cheval_ind[k] < self.Ind.v_inst_cheval_ind[k]:
                                self.Ind.v_pointe_cheval_ind[k] = self.Ind.v_inst_cheval_ind[k]

                            if self.Ind.dist_parcourue_proj_ind[k] > 20:  # on ne calcule qu'à partir de 20 m parcourus
                                self.Ind.v_moy_cheval_ind[k] = (self.Ind.v_moy_cheval_ind[k] * self.Ind.n_en_course[k] +
                                                           self.Ind.v_inst_cheval_ind[k]) / (self.Ind.n_en_course[k] + 1)

                            self.Ind.dist_inst_corde_cheval_ind[k] = (self.Mes.distance_corde_mesure[
                                                                     k] - par.dist_corde2)  # update 0305

                            self.Ind.dist_inst_corde_cheval_ind[k] = np.minimum(
                                np.maximum(self.Ind.dist_inst_corde_cheval_ind[k], -par.dist_corde2),
                                largeur_parcours)

                            if self.Ind.dist_parcourue_proj_ind[k] > 20:  # on ne calcule qu'à partir de 20 m parcourus
                                self.Ind.dist_moy_corde_ind[k] = (self.Ind.dist_moy_corde_ind[k] * self.Ind.n_en_course[k] +
                                                             self.Ind.dist_inst_corde_cheval_ind[k]) / (
                                                                self.Ind.n_en_course[k] + 1)

                            # heading relatif
                            self.Mes, self.Ind = heading_relatif(self.Mes, self.Ind, k)
                            self.Ind.n_en_course[k] = self.Ind.n_en_course[k] + 1
                        ## Passage des portes
                        if 1:
                            if (self.Ind.ind_porte_courante[k] < np.size(indice_portes) and self.Mes.depart_franchis[
                                k] and not self.Ind.arrive[k]) or (self.Mes.arr_franchis[k] and not self.Ind.arrive[
                                k]):

                                if self.Mes.ind_parcours_mesure[k] >= indice_portes[int(self.Ind.ind_porte_courante[k])]:

                                    self.Ind.PC_franchis[k] = 1
                                    msg_udp = "EvtMoteur:" + str(k) + ' porte ' + id_portes[
                                        int(self.Ind.ind_porte_courante[k])] + "#"
                                    print msg_udp
                                    logging.info(msg_udp)
                                    #sender_udp.sendto(msg_udp, (hote, port_sender))

                                    if id_portes[int(self.Ind.ind_porte_courante[k])].startswith('PCDEP') and not \
                                    self.Ind.en_course[k]:
                                        self.Ind.ts_dep[k] = self.Ind.ts_ind[k]
                                        self.Ind.en_course[k] = 1

                                        self.Ind.Tdep[k] = self.Mes.ts_passage_dep[k]

                                        self.Ind.avance_deb[k] = self.Mes.avance_mesure[k]
                                        self.Ind.franchissement_depart_ind[k] = 1  # 'O' # FFV15
                                        #### Temps de réaction
                                        if self.TS_DEPART > 0:
                                            if COURSE_DEMARREE:
                                                self.Ind.t_reac_sortie_ind[k] = 0
                                            else:
                                                self.Ind.t_reac_sortie_ind[k] = self.Ind.ts_dep[k] - self.TS_DEPART
                                        else:
                                            self.Ind.t_reac_sortie_ind[k] = 0.0

                                    if id_portes[int(self.Ind.ind_porte_courante[k])] == 'PCARR':
                                        self.Ind.ts_arr[k] = self.Ind.ts_ind[k]
                                        self.Ind.en_course[k] = 0
                                        self.Ind.franchissement_arrivee_ind[k] = 1  # FFV15
                                        self.Ind.arrive[k] = 1
                                        self.Mes.arr_franchis[k] = 1

                                    self.Ind.temps_pass_pc_ind[k] = self.Ind.temps_passe_depart_ind[k]

                                    self.Ind.pc_ind[k] = id_portes[int(self.Ind.ind_porte_courante[k])]
                                    if self.Ind.dist_parcourue_reelle_ind[k] > 0:
                                        self.Ind.red_km_reelle_pc_ind[k] = self.Ind.red_km_reelle_ind[k]
                                    if self.Mes.avance_mesure[k] > 0:
                                        if self.Mes.avance_mesure[k] - self.Ind.avance_deb[k] > 0:
                                            self.Ind.red_km_proj_pc_ind[k] = self.Ind.red_km_proj_ind[k]
                                        else:
                                            self.Ind.red_km_proj_pc_ind[k] = 0  # FFV15
                                    self.Ind.ind_porte_courante[k] = self.Ind.ind_porte_courante[k] + 1
                                else:
                                    self.Ind.franchissement_depart_ind[k] = 0  # FFV15
                                    self.Ind.franchissement_arrivee_ind[k] = 0  # FFV15
                                    self.Ind.red_km_reelle_pc_ind[k] = 0  # FFV15
                                    self.Ind.red_km_proj_pc_ind[k] = 0  # FFV15
                                    self.Ind.temps_pass_pc_ind[k] = 0
                                    self.Ind.pc_ind[k] = ""
                            else:
                                self.Ind.franchissement_depart_ind[k] = 0  # FFV15
                                self.Ind.franchissement_arrivee_ind[k] = 0  # FFV15
                                self.Ind.red_km_reelle_pc_ind[k] = 0  # FFV15
                                self.Ind.red_km_proj_pc_ind[k] = 0  # FFV15
                                self.Ind.temps_pass_pc_ind[k] = 0
                                self.Ind.pc_ind[k] = ""

                        # Acceleration lissee
                        self.Ind.stock_v_1s[k, :] = np.append(self.Ind.stock_v_1s[k, 1:], self.Ind.v_inst_cheval_ind[k])
                        self.Ind.stock_acc_1s[k, :] = np.append(self.Ind.stock_acc_1s[k, 1:], (
                            self.Ind.stock_v_1s[k, -1] - self.Ind.stock_v_1s[k, -2]) / par.dt)
                        # lissage heading
                        self.Ind.stock_heading_abs_1s[k, :] = np.append(self.Ind.stock_heading_abs_1s[k, 1:],
                                                                   self.Mes.or_mesure[k])

                        if self.Ind.n_en_course[k] > np.size(self.Ind.stock_v_1s[k, :]):
                            self.Ind.acc_lisse_ind[k] = np.mean(self.Ind.stock_acc_1s[k, :])
                            self.Ind.heading_abs_ind[k] = np.mean(self.Ind.stock_heading_abs_1s[k, :])  # self.Mes.or_mesure
                        else:
                            self.Ind.acc_lisse_ind[k] = 0.0
                            self.Ind.heading_abs_ind[k] = 0.0
                else:
                    self.Ind = Indicateurs()
        ##################################################################
        ###################### INDICATEURS COLLECTIFS ####################
        ##################################################################
        premier_arrive = False
        nb_arrive = 0
        for k in range(0, nb_id):
            if self.Ind.arrive[k] and etats_partants[k] and self.Ind.donnee_precise[
                k] and self.Mes.count_persistence <= par.seuil_persistence:  # and mode_course[k]: # on conserve le classement du cheval qui est arrivé
                nb_arrive = nb_arrive + 1
                premier_arrive = True
            else:
                self.Ind.classement_cheval_ind[k] = 0  # on va calculer le classement du cheval, il n'est pas arrivé.

        self.Ind.ecart_proj_premier_ind = np.zeros(nb_id)
        self.Ind.ecart_cheval_prec_ind = np.zeros(nb_id)
        self.Ind.cheval_traj_court_ind = np.zeros(nb_id)  # ffv15
        self.Ind.cheval_trajet_long_ind = np.zeros(nb_id)  # ffv15
        self.Ind.dist_restant_corde_premier_ind = np.zeros(nb_id)

        if 1:
            donnee_persiste = np.array(self.Mes.count_persistence <= par.seuil_persistence)
            chevaux_en_course = np.where(
                etats_partants + etats_capteurs + self.Ind.en_course + self.Ind.donnee_precise + donnee_persiste  == 6)  # seulement les chevaux entre le
            # départ et l'arrivée et dont les flux chauds indiquent qu'il doit être pris en compte
            # dans le classement

            nb_chevaux_en_course = np.size(chevaux_en_course)
            if nb_chevaux_en_course > 0:
                classement_chevaux = np.zeros((5, nb_chevaux_en_course))
                self.Mes.ind_parcours_mesure = np.array(self.Mes.ind_parcours_mesure)
                classement_chevaux[1, :] = self.Mes.ind_parcours_mesure[chevaux_en_course]
                classement_chevaux[2, :] = np.array(chevaux_en_course)
                classement_chevaux[3, :] = self.Ind.dist_parcourue_reelle_ind[chevaux_en_course]
                classement_chevaux[4, :] = self.Ind.dist_parcourue_proj_ind[chevaux_en_course]

                classement_chevaux = classement_chevaux[:, np.argsort(-classement_chevaux[1, :])]
                classement_chevaux[0, :] = range(1, nb_chevaux_en_course + 1)
                # traitement des ex aequos
                for i in range(1, nb_chevaux_en_course):
                    if classement_chevaux[1, i] == classement_chevaux[1, i - 1]:
                        classement_chevaux[0, i] = classement_chevaux[0, i - 1]

                premier_cheval = int(classement_chevaux[2, 0])
                for i in range(0, nb_chevaux_en_course):
                    id_cheval = int(classement_chevaux[2, i])
                    self.Ind.classement_cheval_ind[id_cheval] = classement_chevaux[0, i] + nb_arrive
                    if not premier_arrive:  # Règle: si le premier est arrivé, on ne calcule plus l'indicateur
                        self.Ind.ecart_proj_premier_ind[id_cheval] = np.sum(dD_corde_2[
                                                                       int(classement_chevaux[1, i]):int(
                                                                           classement_chevaux[1, 0])])
                    if i == 0:
                        self.Ind.ecart_cheval_prec_ind[id_cheval] = 0
                    else:
                        # update 0305 écart sur la corde 2
                        # on cherche le cheval précédent (au cas où il y a des ex aequos)
                        j = i - 1
                        while classement_chevaux[0, i] == classement_chevaux[0, j] and j > 0:
                            j = j - 1
                        self.Ind.ecart_cheval_prec_ind[id_cheval] = np.sum(
                            dD_corde_2[int(classement_chevaux[1, i]):int(classement_chevaux[1, j])])

                if not self.Ind.arrive[self.Ind.cheval_trajet_court]:
                    self.Ind.cheval_trajet_court = int(
                        classement_chevaux[2, np.argmin(classement_chevaux[3, :])])
                    self.Ind.cheval_traj_court_ind[self.Ind.cheval_trajet_court] = 1  # 'O' # FFV15

                if self.Ind.arrive[self.Ind.cheval_trajet_long]:
                    if max(classement_chevaux[3, :]) > self.Ind.dist_parcourue_reelle_ind[
                        self.Ind.cheval_trajet_long]:
                        self.Ind.cheval_trajet_long = int(
                            classement_chevaux[2, np.argmax(classement_chevaux[3, :])])
                        self.Ind.cheval_trajet_long_ind[self.Ind.cheval_trajet_long] = 1  # 'O' # FFV15
                else:
                    self.Ind.cheval_trajet_long = int(
                        classement_chevaux[2, np.argmax(classement_chevaux[3, :])])
                    self.Ind.cheval_trajet_long_ind[self.Ind.cheval_trajet_long] = 1  # 'O' # FFV15

                if not premier_arrive:  # Régle: on ne calcule plus l'indicateur si un cheval est arrivé.
                    if self.nb_handicaps:
                        self.Ind.dist_restant_corde_premier_ind = np.ones(nb_id) * (
                            dist_course_handicap[int(self.id_porte_dep[k])] - classement_chevaux[4, 0])
                    else:
                        self.Ind.dist_restant_corde_premier_ind = np.ones(nb_id) * (
                            dist_course_handicap - classement_chevaux[4, 0])

        ##################################################################
        ######################### ECRITURE JSON ##########################
        ##################################################################
        # On envoie le message
        if MODE == "attente":
            dt_thread = 10.0
        else:
            dt_thread = 0.1

        next_t = t + dt_thread
        pause.until(next_t)
        t = time.time()
        dic_global = dict()
        d = datetime.datetime.utcnow()
        epoch = datetime.datetime(1970, 1, 1)
        t_capture = (d - epoch).total_seconds()
        dic_global = {"Ts": int(float(t_capture) * float(1000)),
                      "captures": []}
        # msg_udp =  "t_capture ", t_capture
        # print msg_udp
        # logging.info(msg_udp)
        indice_dict = -1
        ###  Consitution du dictionnaire de sortie
        for k in range(0, nb_id):
            indice_dict = indice_dict + 1

            if etats_capteurs[k] == 0:
                dict_indicateur = format_sortie_rien(k)
            elif self.Mes.count_persistence[k] > par.seuil_persistence:
                dict_indicateur = format_sortie_rien(k)
            elif (etats_capteurs[k] == 2 and self.Ind.en_course[k] and self.Ind.donnee_precise[k]
                  and etats_partants[k]) or self.Ind.franchissement_arrivee_ind[k]:
                dict_indicateur = format_sortie_full(k, self.Mes, self.Ind)
            elif self.Ind.en_course[k] and not self.Ind.donnee_precise[k]:
                dict_indicateur = format_sortie_rien(k)
            else:
                dict_indicateur = format_sortie_GPS(k, self.Mes, self.Ind)

            if not dic_global["captures"]:
                dic_global["captures"] = [dict_indicateur.copy()]

            else:
                dic_global["captures"].append(dict_indicateur.copy())
                dic_global["captures"][indice_dict]["Pos"] = dict_indicateur["Pos"].copy()

        message_sortie = json.dumps(dic_global, indent=2, sort_keys=True)

        msg_a_envoyer = message_sortie
        # Peut planter si vous tapez des caracteres speciaux
        msg_a_envoyer = msg_a_envoyer.encode()


        try:
            # connexion_avec_serveur.send(msg_a_envoyer)
            with open('result_live' + str(int(t_start)) + '.json', 'ab') as fp:
                fp.write(message_sortie)
            if MODE == "attente":
                msg_udp = "EvtMoteur: envoi json mode attente#"
                print msg_udp
                logging.info(msg_udp)
                #sender_udp.sendto(msg_udp, (hote, port_sender))

                # print msg_a_envoyer
        except Exception as e:
            msg_udp = "ErreurMoteur: le json n'a pas pu etre envoye, reconnexion#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
            #sender_udp.sendto(msg_udp, (hote, port_sender))
            tcp_connected = False

        #### ECRITURE FICHIER SORTIE
        #if MODE == "course":
        #    with open('result_live' + str(int(t_start)) + '.json', 'ab') as fp:
        #        fp.write(message_sortie)

class FRAMES:
    def __init__(self):
        self.content = []
        self.lock = threading.Lock()

class Thread_A(threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)
        self.name = name

    def run(self):
        # plt.ion()
        global etats_partants
        global etats_capteurs
        global RESTART
        global FIN_COURSE
        global DEPART_COURSE
        global handicaps

        global connexion_avec_serveur
        global par
        global tcp_connected
        global COURSE_DEMARREE
        global stock_trames
        global TS_traitement
        global NUM_trames_recues
        global debut_traitement
        global frames
        global t_start
        print "EvtMoteur: ouverture du moteur de calcul#"
        logging.info("ouverture du moteur de calcul")

        first_false = 1
        global t
        while True:
            time.sleep(0.1)

            if STATE_UDP:
                first_false = 0
                try:
                    if np.size(dist_course_handicap) > 1:
                        handicaps = np.ones(nb_id) * dist_course_handicap[0]
                    else:
                        handicaps = np.ones(nb_id) * dist_course_handicap

                    Mot = Moteur(par, nb_id,handicaps,dist_course_handicap, handicaps_recus)
                    # initialisation pour la gestion du timer
                    t_start = time.time()
                    dt_thread = 0.1
                    t = t_start

                    Mot.num_analyse = 0
                    COURSE_DEMARREE = 0
                    COURSE_TERMINEE = 0
                    Mot.tous_arrives = 0

                    ##### début du moteur
                    stock_trames = dict()
                    TS_traitement = 0
                    NUM_trames_recues = 0
                    debut_traitement = False
                    for k in range(0, nb_id):
                        stock_trames[str(k)] = []

                except:
                    msg_udp = "ErreurMoteur: impossible d'initialiser le moteur"
                    print msg_udp
                    logging.error(msg_udp, exc_info=True)

                try:

                    # initialisation pour la gestion du timer
                    t_start = time.time()
                    dt_thread = 0.1
                    t = t_start
                    num_analyse = 0

                    # initialisation
                    #CALCUL_MESURES = np.zeros(nb_id)
                    COURSE_DEMARREE = 0
                    COURSE_TERMINEE = 0
                    tous_arrives = 0
                    attente_depart = 1

                    ts_deb = hhmmss_to_ts_utc(DATA[0,1])
                    ts_fin = hhmmss_to_ts_utc(DATA[-1,1])
                    curr_ts = ts_deb
                    t_analyse = ts_deb
                    indice_trame = 0
                    n_data = np.size(DATA[:,0])
                    connected = True
                    while t_analyse < ts_fin and STATE_UDP and connected:
                        """
                        if num_analyse % 20 == 0:
                            plt.figure(1)
                            plt.cla()
                            for k in range(0, nb_id):
                                if Mot.Mes.lat_mesure[k] != 0 and Mot.Mes.long_mesure[k] != 0 and Mot.Ind.donnee_precise[k]:
                                    plt.plot(Mot.Mes.lat_mesure[k],Mot.Mes.long_mesure[k],'.',label = str(k))
                            ind1 = np.maximum(0,float(np.max(Mot.Mes.ind_parcours_mesure))/ float(par.res_interp) - 10.0 )
                            ind2 = np.minimum(float(np.max(Mot.Mes.ind_parcours_mesure))/ float(par.res_interp) + 10.0 , np.size(lat_corde)-1)
                            plt.plot(lat_corde[int(ind1) :int(ind2)], long_corde[int(ind1):int(ind2)],'.')
                            plt.plot(lat_corde_ext[int(ind1):int(ind2)], long_corde_ext[int(ind1):int(ind2)], '.')
                            plt.legend()
                            plt.draw()
                            plt.pause(0.0001)
                        """

                        ##### début du moteur

                        # gestion des états transmis via udp
                        top_depart = 0
                        if num_analyse == 100: #np.sum(Mes.depart_franchis) > np.int(nb_id / 4) and attente_depart:
                            DEPART_COURSE = 1
                            attente_depart = 0

                        num_analyse = num_analyse + 1
                        # gestion du mode d'émission
                        if MODE == "attente":
                            dt_thread = 10.0
                            Ind = Indicateurs(nb_id, par)
                        else:
                            dt_thread = 0.0001

                        next_t = t + dt_thread

                        # réception du message TCP
                        #connexion_avec_serveur.settimeout(max(0, float(next_t - time.time())))
                        pause.until(next_t)
                        t = time.time()

                        frames = []
                        while curr_ts <= t_analyse + 0.1 * float(1000) and indice_trame < n_data - 1:
                            # print curr_ts
                            ### Stockage des trames dans le dixième de secondes en cours d'analyse
                            frame = DATA[indice_trame, [0, 1, 2, 3, 6, 7, 8]]
                            if np.size(frames) == 0:
                                frames = frame
                            else:
                                frames = np.vstack([frames, frame])

                            indice_trame = indice_trame + 1
                            curr_ts = hhmmss_to_ts_utc(DATA[indice_trame, 1])
                        Mot.boucle_traitement()
                        t_analyse = t_analyse + 100

                except Exception as e:
                    msg_udp = "ErreurMoteur: erreur TCP#"
                    print msg_udp
                    logging.error(msg_udp, exc_info=True)

class Thread_B(threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)
        self.name = name

    def run(self):
        global STATE_UDP # True = on réceptionne les trames
        global PATH_PARCOURS
        global MODE # "veille" (rien) "attente" (0.1 Hz) ou "course" (10 Hz)
        global etats_partants # tableau au nombre de partants. 0 -> NP / 1 -> P
        global etats_capteurs # 0 -> veille / 1 -> attente / 2 -> course
        global liste_id # liste des partants
        global nb_id
        global par
        global DEPART_COURSE
        global FIN_COURSE
        global RESTART
        global etats_capteurs
        global ETAT_MOTEUR

        ## Données parcours
        global corde_interpol_x
        global corde_interpol_y
        global corde_2_interpol_x
        global corde_2_interpol_y
        global corde_ext_interpol_x
        global corde_ext_interpol_y
        global X_corde
        global Y_corde
        global DIST_corde
        global indice_10
        global indice_500
        global X_corde_ext
        global Y_corde_ext
        global centre_lat
        global centre_long
        global dist_totale_parcours
        global id_portes
        global indice_portes
        global dD_corde_inter
        global dD_corde_2
        # global porte_depart
        # global porte_arr
        global indices_dep_handicap
        global dist_course_handicap
        global porte_dep_handicap
        # global portes_depart_handicap
        global sender_udp
        global hote
        global port_sender
        global handicaps
        global handicaps_recus
        global largeur_parcours

        global lat_corde
        global long_corde
        global lat_corde_ext
        global long_corde_ext

        sender_udp = 0
        hote = 0
        port_sender = 0

        global DATA

        handicaps_recus = False
        ETAT_MOTEUR = "veille"
        par = Parametres()

        STATE_UDP = False
        DEPART_COURSE = 0
        FIN_COURSE = 0
        RESTART = 0
        PATH_PARCOURS = ' '
        MODE = "attente"
        parcours_traite = 0


        data_course = "D:/Lisa/Documents/PMU/moteurs_PMU/courses/f1.csv"

        ETAT_MOTEUR = "traitement parcours"
        PATH_PARCOURS = os.path.join("D:/","Lisa","Documents","PMU","parcours")
        PATH_COURSE = PATH_PARCOURS

        file_parcours = os.path.join(PATH_PARCOURS, "parcours.csv")
        data_parcours = np.array(pd.read_csv(file_parcours, delimiter=";"))
        lat_corde = data_parcours[:,1]
        lat_corde = lat_corde[::-1]
        long_corde = data_parcours[:,2]
        long_corde = long_corde[::-1]
        lat_corde_ext = data_parcours[:,5]
        lat_corde_ext = lat_corde_ext[::-1]
        long_corde_ext = data_parcours[:, 6]
        long_corde_ext = long_corde_ext[::-1]


        #### Message udp
        msg_udp = "FluxRecu: PATH PARCOURS " + PATH_PARCOURS + "#"
        print msg_udp
        logging.info(msg_udp)
        try:
            ### TRAITEMENT DU FICHIER DE PARCOURS
            traitement_parcours(PATH_PARCOURS, par) #, hote, port_sender, sender_udp)
            ##### Message udp
            msg_udp = "EvtMoteur: Fin du traitement#"
            print msg_udp
            logging.info(msg_udp)
        except:
            logging.error(
                "flux PathParcours: le fichier de parcours n a pas pu etre traite correctement",
                exc_info=True)

        try:
            ### Chargement des donnees parcours
            ETAT_MOTEUR = "integration parcours"
            ### Donnees d'interpolation
            #### Message UDP
            msg_udp = "EvtMoteur: chargement interpolation#"
            print msg_udp
            logging.info(msg_udp)

            #file_info = PATH_COURSE + str("\info.json")
            file_info = os.path.join(PATH_COURSE, "info.json")
            #file_interpolation = PATH_COURSE + str("\interpolation.csv")
            file_interpolation = os.path.join(PATH_COURSE, "interpolation.csv")
            parcours = pd.read_csv(file_interpolation, delimiter=";")
            parcours = np.array(parcours)
            corde_interpol_x = parcours[:, 0]
            corde_interpol_y = parcours[:, 1]
            corde_2_interpol_x = parcours[:, 2]
            corde_2_interpol_y = parcours[:, 3]
            corde_ext_interpol_x = parcours[:, 4]
            corde_ext_interpol_y = parcours[:, 5]
            dD_corde_2 = parcours[:, 6]

            ### informations sur le parcours
            msg_udp = "EvtMoteur: chargement infos parcours#"
            print msg_udp
            logging.info(msg_udp)

            with open(file_info) as data_file:
                info_parcours = json.load(data_file)
            X_corde = info_parcours["X_corde"]
            Y_corde = info_parcours["Y_corde"]
            DIST_corde = info_parcours["DIST_corde"]
            indice_10 = info_parcours["indice_10"]
            indice_500 = info_parcours["indice_500"]
            X_corde_ext = info_parcours["X_corde_ext"]
            Y_corde_ext = info_parcours["Y_corde_ext"]
            centre_lat = info_parcours["centre_lat"]
            centre_long = info_parcours["centre_long"]
            dist_totale_parcours = info_parcours["dist_totale_parcours"]
            id_portes = info_parcours["id_portes"]
            indice_portes = info_parcours["indice_portes"]
            dD_corde_inter = info_parcours["dD_corde_inter"]
            #portes_depart_handicap = info_parcours["portes_depart_handicap"]
            #porte_arr = info_parcours["porte_arr"]
            dist_corde_2 = info_parcours["dist_corde_2"]
            indices_dep_handicap = info_parcours["indices_dep_handicap"]
            dist_course_handicap = info_parcours["dist_course_handicap"]
            porte_dep_handicap = info_parcours["porte_dep_handicap"]
            largeur_parcours = info_parcours["largeur_parcours"]


            parcours_traite = 1
            ETAT_MOTEUR = "veille"
        except:
            msg_udp = "ErreurMoteur: impossible de charger les fichiers de traitement de parcours#"
            logging.error(msg_udp, exc_info=True)

        DATA = pd.read_csv(data_course, delimiter=",")
        DATA = np.array(DATA)

        try:
            #liste_id =  [16, 32, 33, 37, 31, 40]
                                        # [11,12,13,14,18,21,22,29,39] # [13,18,21,22,23,26,29,34,35] # [16,19,20,31,32,33,37,40] #### TEST
            liste_id = np.unique(DATA[:, 0])
            print "liste id"
            print liste_id
            nb_id = np.size(liste_id)
            etats_partants = np.ones(nb_id)
            etats_capteurs = ["veille"] * nb_id
            ### Message udp
            msg_udp = "EvtMoteur: liste de partants recue et integree#"
            print msg_udp
            logging.info(msg_udp)
        except:
            msg_udp = "ErreurMoteur: Probleme lors du chargement de la liste des partants#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)

        try:
            etats_partants = np.ones(nb_id)
            msg_udp = "EvtMoteur: etat des partants recu et integre#"
            print msg_udp
            logging.info(msg_udp)
        except Exception as e:
            msg_udp = "ErreurMoteur: probleme lors du chargement des etats des partants#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
        print "etats partants"
        print etats_partants

        try:
            etats_capteurs = np.ones(nb_id) * 2
            msg_udp = "EvtMoteur: etat des capteurs recu et integre#"
            print msg_udp
            logging.info(msg_udp)
        except Exception as e:
            msg_udp = "ErreurMoteur: probleme lors du chargement des etats des capteurs#"
            print msg_udp
            logging.error(msg_udp, exc_info=True)
        print "etats capteurs"
        print etats_capteurs

        if np.size(dist_course_handicap) > 1:
            handicaps = np.ones(nb_id) * dist_course_handicap[0]
        else:
            handicaps = np.ones(nb_id) * dist_course_handicap
        handicaps_recus = True
        print handicaps
        msg_udp = "EvtMoteur: handicaps des partants recu et integre#"
        print msg_udp
        logging.info(msg_udp)


        if parcours_traite:
            MODE = "course"
            ETAT_MOTEUR = "course"
        else:
            msg_udp =  "ErreurMoteur: impossible de passer en mode course, aucun parcours traite#"
            print msg_udp
            logging.info(msg_udp)

        STATE_UDP = True
        print "STATE UDP " + str(STATE_UDP) + " mode " + str(MODE)

class Thread_etat_moteur(threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)
        self.name = name

    def run(self):
        while True:
            try:
                msg_udp = "EtatMoteur: " + ETAT_MOTEUR + "#"
                print msg_udp
                logging.info(msg_udp)
                time.sleep(10.0)
            except:
                pass

def main():
    global version
    global msg_lancement
    version  = "v0.3.5"
    msg_lancement = "lancement moteur PMU version " + version + "#"
    print msg_lancement

    logging.basicConfig(format = version + ' %(asctime)s %(funcName)s (%(lineno)d) %(message)s',filename='logs.log', level=logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        'logs.log', maxBytes= 1024)
    logging._addHandlerRef(handler)

    b = Thread_B("myThread_name_B")
    a = Thread_A("myThread_name_A")
    c = Thread_etat_moteur("Etat Moteur")

    b.start()
    a.start()
    c.start()

    # a.join()
    # b.join()
    # c.join()


if __name__ == "__main__":
    main()
