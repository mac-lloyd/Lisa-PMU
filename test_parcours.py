# -*- coding: utf-8 -*-

import os
import socket
import time
import datetime
import pause
import numpy as np
import pandas as pd
import json
from scipy.interpolate import interp1d
from scipy.interpolate import lagrange
import threading
import logging
import math
from logging.handlers import RotatingFileHandler
import pandas as pd
import matplotlib.pyplot as plt
import glob

def lat_to_m(dlat, alat):
    """
    Fonction qui convertit une variation de latitude en mètres
    :param dlat: variation de latitude en degrés
    :param alat: latitude de référence
    :return: variation en m en coordonnées cartésienne sur Y
    """
    try:
        rlat = alat * np.pi / 180;  # conversion en radians
        m = 111132.09 - 566.05 * np.cos(2 * rlat) + 1.2 * np.cos(
            4 * rlat)  # longueur en metres pour un degre a la latitude alat
        dy = dlat * m  # longueur en metres pour la diff de latitude dlat
        dy = dlat * m  # longueur en metres pour la diff de latitude dlat
        return dy
    except:
        logging.error("erreur dans la fonction lat_to_m",exc_info=True)
        return 0

def lon_to_m(dlon, alat):
    """
    Fonction qui convertit une variation de longitude en mètres
    :param dlong: variation de longitude en degrés
    :param alat: latitude de référence
    :return: variation en m en coordonnées cartésiennes sur X
    """
    try:
        rlat = alat * np.pi / 180;  # conversion en rad
        p = 111415.13 * np.cos(rlat) - 94.55 * np.cos(3 * rlat);  # longueur d'un degre en longitude a alat
        dx = dlon * p
        return dx
    except:
        logging.error("erreur dans la fonction lon_to_m",exc_info=True)
        return 0

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
        logging.error("erreur dans la fonction m_to_lat",exc_info=True)
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
        logging.error("erreur dans la fonction m_to_lon",exc_info=True)
        return 0

def traitement_parcours(path_parcours, params):
    """
    Fonction qui traite le fichier de parcours avant la course

     :param file_parcours: path du fichier de parcours
     :param params: objet Parametres contenant les paramètres
     :return corde_interpol_x: points x sur la corde interpolés en coordonnées cartésiennes en m
     :return corde_interpol_y: points y sur la corde interpolés en coordonnées cartésiennes en m
     :return corde_2_interpol_x: points x sur la deuxieme corde interpolés en coordonnées cartésiennes en m
     :return corde_2_interpol_y: points y sur la deuxieme corde interpolés en coordonnées cartésiennes en m
     :return corde_ext_interpol_x: points x sur la corde extérieure interpolés en coordonnées cartésiennes en m
     :return corde_ext_interpol_y: points x sur la corde extérieure interpolés en coordonnées cartésiennes en m
     :return X_corde: points x sur la corde tous les 10 mètres
     :return Y_corde: points y sur la corde tous les 10 mètres
     :return centre_lat: centre de la piste au format lat 
     :return centre_long: centre de la piste au format long
     :return dist_totale_parcours: distance de la porte de depart à la port d'arrivée sur la deuxieme corde
     :return id_portes: identifiants des portes clés du parcours
     :return indice_portes: indices des portes sur le parcours interpolé
     :return dD_corde_inter: espacement entre les points interpolés sur la corde
     :return dD_corde_2: tableau des espacements entre les points interpolés sur la deuxieme corde    
    """

    path = path_parcours + "/*" + ".csv"
    print path
    for fname in glob.glob(path):
        print(fname)

        # On verifie si les fichiers de sortie existent deja

        # file_info = path_parcours + str("/info.json")
        file_info = os.path.join(path_parcours + "/result/", "info.json")
        # file_interpolation = path_parcours + str("\interpolation.csv")
        file_interpolation = os.path.join(path_parcours + "/result/", "interpolation.csv")

        if os.path.isfile(file_info):
            try:
                os.remove(file_info)
                msg_udp = "EvtMoteur: fichier " + str(file_info) + " supprime#"
                print msg_udp
            except:
                msg_udp = "ErreurMoteur: impossible de supprimer " + str(file_info) + "#"
                print msg_udp
                raise ValueError("impossible de supprimer le fichier info deja existant")

        if os.path.isfile(file_interpolation):
            try:
                os.remove(file_interpolation)
                msg_udp = "EvtMoteur: fichier " + str(file_interpolation) + " supprime#"
                print msg_udp
            except:
                msg_udp = "ErreurMoteur: impossible de supprimer " + str(file_interpolation) + "#"
                print msg_udp
                raise ValueError("impossible de supprimer le fichier interpolation déjà existant")


            # file_parcours = path_parcours + "/parcours.csv"
        file_parcours = fname #os.path.join(path_parcours, "parcours.csv")
        parcours = pd.read_csv(file_parcours, delimiter=";")
        parcours = np.array(parcours)
        PC = np.array(parcours[:, 7])
        msg_udp = "EvtMoteur: traitement parcours fichier ouvert#"
        print msg_udp



        ind_dep = np.where(PC == "PCDEP")
        if not ind_dep:
            msg_udp = "ErreurMoteur: pas de porte PCDEP dans le fichier de parcours#"
            print msg_udp
            raise ValueError('pas de porte de départ trouvée dans le fichier de parcours')

        ind_arr = np.where(PC == "PCARR")
        if not ind_arr:
            msg_udp = "ErreurMoteur: pas de porte PCARR dans le fichier de parcours#"
            print msg_udp
            raise ValueError('pas de porte darrivée trouvée dans le fichier de parcours')

        ind_dep_handicap = [i for i, s in enumerate(PC) if 'PCDEP' in s and s != 'PCDEP']
        ind_dep = int(ind_dep[0])
        ind_arr = int(ind_arr[0])

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

        largeur_max = 0
        msg_udp = "EvtMoteur: conversion des donnees GPS en coordonnees cartesiennes#"
        print msg_udp
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
                diff_x = (X_corde[-1] - X_corde[-2]) / norm_int
                diff_y = (Y_corde[-1] - Y_corde[-2]) / norm_int
                norm_ext = np.sqrt(np.square(X_corde_ext_2[-1] - X_corde_ext_2[-2]) + np.square(Y_corde_ext_2[-1] - Y_corde_ext_2[-2]))
                diff_x_ext = (X_corde_ext_2[-1] - X_corde_ext_2[-2]) / norm_ext
                diff_y_ext = (Y_corde_ext_2[-1] - Y_corde_ext_2[-2]) / norm_ext
                scal_int_ext = diff_x * diff_x_ext + diff_y * diff_y_ext
            else:
                scal_int_ext = 0
            if scal_int_ext > 0.95:
                if dist_ext > largeur_max:
                    largeur_max = dist_ext

        print "largeur max ", largeur_max
        if largeur_max == 0:
            msg_udp = "corde exterieure et corde intérieure pas suffisamment parallele"
            print msg_udp

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
            X_corde_ext.append(x + float(x_ext - x) * float(largeur_max) / float(norm))
            Y_corde_ext.append(y + float(y_ext - y) * float(largeur_max) / float(norm))
            lat_corde_ext.append(m_to_lat(X_corde_ext[-1], centre_lat) + centre_lat)
            long_corde_ext.append(m_to_lon(Y_corde_ext[-1], centre_lat) + centre_long)

        X_corde_ext = np.array(X_corde_ext)
        Y_corde_ext = np.array(Y_corde_ext)

        """
        plt.figure()
        plt.plot(X_corde, Y_corde,'.', label = "corde interieure")
        plt.plot(X_corde_ext, Y_corde_ext, '.', label = "corde_exterieure corrigee")
        plt.plot(X_corde_ext_2, Y_corde_ext_2, '.', label = "corde exterieure")
        plt.legend()
        plt.figure()
        plt.plot(X_corde)
        plt.figure()
        plt.plot(Y_corde)
        plt.figure()
        plt.plot()
        plt.plot(X_corde, Y_corde,'.', label = "corde interieure")
        plt.plot(X_corde_ext_2, Y_corde_ext_2, '.', label = "corde exterieure")
        plt.legend()
        plt.title(os.path.basename(fname))
        plt.show()
        """

        DIST_corde = (DIST_corde[0] - DIST_corde)
        DIST_corde = DIST_corde.astype(float)

        #### Interpolation
        msg_udp = "EvtMoteur: debut interpolation#"
        print msg_udp

        corde_interpol_x = []
        corde_interpol_y = []
        corde_2_interpol_x = []
        corde_2_interpol_y = []
        corde_ext_interpol_x = []
        corde_ext_interpol_y = []

        step_10pourc = int(np.float(X_corde_2.size - params.N_interp - params.N_interp) / np.float(10))

        plt.figure()
        for t in range(params.N_interp, X_corde_2.size - params.N_interp + 1):
            if t % step_10pourc == 0:
                msg_udp = "EvtMoteur: progression " + str(np.float(t) / np.float(step_10pourc) * 10) + "#"
                print msg_udp

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
                f2x = interp1d(scale_orig, points_x, fill_value='extrapolate')
            else:
                f2x = interp1d(scale_orig, points_x, kind='cubic')

            #f2x = lagrange(scale_orig, points_x)

            points_x_res = f2x(scale_res)
            corde_interpol_x = np.append(corde_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                # f2y = lagrange(scale_orig, points_y)
                f2y = interp1d(scale_orig, points_y, kind='cubic')



            points_y_res = f2y(scale_res)
            corde_interpol_y = np.append(corde_interpol_y, points_y_res)

            plt.plot(points_x_res, points_y_res, '.')
            #### Corde (a 2 metres)
            points_x = X_corde_2[t - params.N_interp: t + params.N_interp]
            points_y = Y_corde_2[t - params.N_interp: t + params.N_interp]

            if t == X_corde_2.size - params.N_interp:
                f2x = interp1d(scale_orig, points_x, fill_value='extrapolate')

            else:
                # f2x = lagrange(scale_orig, points_x)
                f2x = interp1d(scale_orig, points_x, kind='cubic')


            points_x_res = f2x(scale_res)
            corde_2_interpol_x = np.append(corde_2_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                # f2y = lagrange(scale_orig, points_y)
                f2y = interp1d(scale_orig, points_y, kind='cubic')



            points_y_res = f2y(scale_res)
            corde_2_interpol_y = np.append(corde_2_interpol_y, points_y_res)

            #### Corde exterieure
            points_x = X_corde_ext[t - params.N_interp: t + params.N_interp]
            points_y = Y_corde_ext[t - params.N_interp: t + params.N_interp]

            if t == X_corde_2.size - params.N_interp:
                f2x = interp1d(scale_orig, points_x, fill_value='extrapolate')
            else:
                # f2x = lagrange(scale_orig, points_x)
                f2x = interp1d(scale_orig, points_x, kind='cubic')


            points_x_res = f2x(scale_res)
            corde_ext_interpol_x = np.append(corde_ext_interpol_x, points_x_res)

            if t == X_corde_2.size - params.N_interp:
                f2y = interp1d(scale_orig, points_y, fill_value='extrapolate')
            else:
                # f2y = lagrange(scale_orig, points_y)
                f2y = interp1d(scale_orig, points_y, kind='cubic')


            points_y_res = f2y(scale_res)

            corde_ext_interpol_y = np.append(corde_ext_interpol_y, points_y_res)
        plt.plot(X_corde, Y_corde, '.'), plt.show()
        msg_udp = "EvtMoteur: fin interpolation#"
        print msg_udp

        msg_udp = "EvtMoteur: calcul des caracteristiques de portes#"
        print msg_udp

        indice_portes = []
        id_portes = []

        ind_deb = 0
        ind_fin = 0

        # indices auxquels se trouveront les portes
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
                        (DIST_corde[-1] - dist_course_handicap) + DIST_corde[int(indices_dep_handicap[0])] + 9) \
                        and not trouve_10:
                    indice_10 = i
                    trouve_10 = True
                if DIST_corde[i] > (
                        (DIST_corde[-1] - dist_course_handicap) + DIST_corde[int(indices_dep_handicap[0])] + 500) \
                        and not trouve_500:
                    indice_500 = i
                    trouve_500 = True

            if not trouve_500:
                indice_500 = np.size(DIST_corde) - 1
            if not trouve_10:
                indice_10 = np.size(DIST_corde) - 1
        print indice_10, indice_500, trouve_10, trouve_500

        ### calcul des paramètres de la porte de départ
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

        msg_udp = "EvtMoteur: calcul des increments de distance#"
        print msg_udp

        ### Calcul des incréments de distance pour la corde à 2m
        dD_corde_2 = np.zeros(np.size(corde_2_interpol_x))
        dist_totale_parcours = 0

        step_10pourc = int(np.float(np.size(corde_2_interpol_x)) / np.float(10))
        for k in range(1, np.size(corde_2_interpol_x)):
            if k % step_10pourc == 0:
                msg_udp = "EvtMoteur: progression " + str(np.float(k) / np.float(step_10pourc) * 10) + "#"
                print msg_udp

            dx = corde_2_interpol_x[k] - corde_2_interpol_x[k - 1]
            dy = corde_2_interpol_y[k] - corde_2_interpol_y[k - 1]
            dD = np.sqrt(np.square(dx) + np.square(dy))
            dD_corde_2[k] = dD
            if k >= ind_deb * params.res_interp and k <= ind_fin * params.res_interp:
                dist_totale_parcours = dist_totale_parcours + dD

        plt.figure,
        plt.plot(X_corde,Y_corde,'.')
        plt.plot(X_corde_ext, Y_corde_ext, '.')
        plt.plot(X_corde_ext_2, Y_corde_ext_2, '.')
        plt.plot(corde_interpol_x, corde_interpol_y, '.'),
        plt.plot(corde_ext_interpol_x, corde_ext_interpol_y, '.'),
        plt.plot(corde_2_interpol_x, corde_2_interpol_y, '.'),

        plt.show()

        #### distance deuxieme corde
        dist_x = X_corde[0] - X_corde_2[0]
        dist_y = Y_corde[0] - Y_corde_2[0]
        dist_corde_2 = np.sqrt(np.square(dist_x) + np.square(dist_y))
        dist_corde_2 = np.maximum(1, np.minimum(dist_corde_2, 2))
        dist_corde_2 = np.round(dist_corde_2)

        largeur_parcours = np.mean(np.sqrt(np.square(X_corde - X_corde_ext) + np.square(Y_corde - Y_corde_ext)))

        ##### Creation de dictionnaire d'information de parcours ###
        msg_udp = "EvtMoteur: stockage des resultats#"
        print msg_udp

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
        info_parcours["portes_depart_handicap"] = np.array(portes_depart_handicap).tolist()
        info_parcours["porte_arr"] = porte_arr
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
        self.cov_mode_pos = np.square([100, 5, 3, 1, 0.03, 0.5])
        self.cov_mode_v = np.square(np.float(0.2) / np.float(3.6))
        self.cov_etat = np.square(np.array([0.4, 0.4, 0.1]) * self.dt)  # np.square(np.array([0.2, 0.2, 0.1]) * self.dt)

        # Paramètres de détection du départ
        self.seuil_points_parcours = 10
        self.seuil_points_recul = 10
        self.seuil_duree_reinit = 20
        self.seuil_v_depart = 20 / 3.6 # m/s

par = Parametres()
folder = "D:/Lisa/Documents/PMU/parcours/reparcoursdeauville1erjuillet/"
traitement_parcours(folder, par)