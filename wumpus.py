import random

from wumpus_kb import BaseConocimiento

MUNDO_N = 4
MUNDO_S = MUNDO_N * MUNDO_N

mundo = [None] * MUNDO_S
a_x = 0
a_y = 0
vivo = True
flechas = 1
run = True
oro = False

kb = BaseConocimiento(ancho=MUNDO_N)

def limpiar_mundo():
    global a_x, a_y, vivo, flechas, oro
    for j in range(MUNDO_S):
        mundo[j] = ""
    a_x = 0
    a_y = 0
    vivo = True
    flechas = 1
    oro = False


def generar_mundo():
    n_pozos = 0.2 * MUNDO_S # %20 de n^2
    n_pozos = round(n_pozos)

    for i in range(n_pozos):
        p = random.randint(0, MUNDO_S - 1)

        while mundo[p] != "":
            p = random.randint(0, MUNDO_S - 1)
        
        mundo[p] = "P"
    
        # wumpus
    w = random.randint(0, MUNDO_S - 1)
    mundo[w] += "W"

        # oro
    g = random.randint(0, MUNDO_S - 1)
    mundo[g] += "G"


def ce(x, y):
    return mundo[x + (y * MUNDO_N)]


def dibujar_mundo():
    for j in range(MUNDO_N):
        for i in range(MUNDO_N):
            if i == a_x and j == MUNDO_N - a_y - 1:
                print("A", end="")
            print(ce(i, MUNDO_N - j - 1), end="-\t")
        print("")


def mover():
    global a_x, a_y, flechas, run, oro, kb
    print("Guardar Base:\n-SB")
    print("Mover:")
    print("-M0: mover arriba")
    print("-M1: mover derecha")
    print("-M2: mover abajo")
    print("-M3: mover izquierda")
    print("Acciones:")

    if flechas:
        print("-D0: disparar arriba")
        print("-D1: disparar derecha")
        print("-D2: disparar abajo")
        print("-D3: disparar izquierda")

    g = "G" in ce(a_x, a_y)
    if g:
        print("-T: tomar oro")

    s = a_x == 0 and a_y == 0
    if s:
        print("-S: salir")

    valido = False
    while not valido:
        i = input(":")

        if i == "SB":
            kb.guardar_base()

        if len(i) > 0:
            if i[0] == "M":
                if len(i) == 2:
                    if ("0" <= i[1] and i[1] <= "3"):
                        if i[1] == "0":
                            if a_y != MUNDO_N - 1:
                                a_y += 1
                                valido = True
                        elif i[1] == "1":
                            if a_x != MUNDO_N - 1:
                                a_x += 1
                                valido = True
                        elif i[1] == "2":
                            if a_y != 0:
                                a_y -= 1
                                valido = True
                        else:
                            if a_x != 0:
                                a_x -= 1
                                valido = True
            elif i[0] == "D" and flechas:
                if len(i) == 2:
                    if ("0" <= i[1] and i[1] <= "3"):
                        valido = True
                        flechas = 0
                        wumpus = True
                        if i[1] == "0":
                            for j in range(a_y + 1, MUNDO_N):
                                if "W" in ce(a_x, j):
                                    mundo[a_x + j * MUNDO_N] = mundo[a_x + j * MUNDO_N].replace("W", "")
                                    wumpus = False
                                    break

                        elif i[1] == "1":
                            for j in range(a_x + 1, MUNDO_N):
                                if "W" in ce(j, a_y):
                                    mundo[j + a_y * MUNDO_N] = mundo[j + a_y * MUNDO_N].replace("W", "")
                                    wumpus = False
                                    break

                        elif i[1] == "2":
                            for j in range(a_y - 1, -1, -1):
                                if "W" in ce(a_x, j):
                                    mundo[a_x + j * MUNDO_N] = mundo[a_x + j * MUNDO_N].replace("W", "")
                                    wumpus = False
                                    break

                        elif i[1] == "3":
                            for j in range(a_x - 1, -1, -1):
                                if "W" in ce(j, a_y):
                                    mundo[j + a_y * MUNDO_N] = mundo[j + a_y * MUNDO_N].replace("W", "")
                                    wumpus = False
                                    break
                        if not wumpus:
                            print("Wumpus emite un grito")
            elif i == "T":
                if g:
                    oro = True
                    mundo[a_x + (a_y * MUNDO_N)] = ""
                    valido = True
            elif i == "S":
                if s:
                    run = False
                    valido = True
            
        if not valido:
            print("Opcion no valida")



def alrededor(x, y, a):
    resp = False
    if x != 0:
        if a in ce(x - 1, y):
            resp = True
    if x != MUNDO_N - 1:
        if a in ce(x + 1, y):
            resp = True
    if y != 0:
        if a in ce(x, y - 1):
            resp = True
    if y != MUNDO_N - 1:
        if a in ce(x, y + 1):
            resp = True
    return resp


def percibir():
    print("Te encuentras en", a_x + 1, ",", a_y + 1)
    resp = ""
    if alrededor(a_x, a_y, "P"):
        resp += "B"
    if alrededor(a_x, a_y, "W"):
        resp += "S"
    if alrededor(a_x, a_y, "G"):
        resp += "R"
    return resp

def peligros():
    global vivo

    if "W" in ce(a_x, a_y) or "P" in ce(a_x, a_y):
        vivo = False


def reset():
    limpiar_mundo()
    generar_mundo()

reset()

print("KB reglas:")
print(kb.mostrar(True) + "\n")

while run:
    peligros()

    if oro:
        print("Ganaste")
        i = input("Continuar? S/N")
        if i == "S":
            reset()
        else:
            run = False
    if not vivo:
        print("Perdiste")
        i = input("Continuar? S/N")
        if i == "S":
            reset()
        else:
            run = False

    dibujar_mundo()
    if run:
        percepciones = percibir()
        kb.traducir_percepciones((a_x, a_y), list(percepciones))
        print("\nKB:")
        kb.imprimir()
        mover()
