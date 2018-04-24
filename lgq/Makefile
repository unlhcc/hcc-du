TARGET = lgq
CC = gcc
BISON = bison
FLEX = flex
CFLAGS = -Wall -g
DFLAGS =
INCS = -I lustre/lustre/include -I lustre/libcfs/include -I lustre/lnet/include
#SRCS = ${sort ${wildcard *.c} conf.tab.c lex.conf.c}
SRCS = ${sort ${wildcard *.c}}
OBJS = ${patsubst %.c,%.o,${SRCS}}
DEPS = ${patsubst %.c,%.d,${SRCS}}
SHARED_LIBS =
STATIC_LIBS =

all: ${TARGET}

${DEPS}: %.d: %.c
	${CC} ${CFLAGS} ${DFLAGS} ${INCS} \
	-MM -MG -MF ${patsubst %.c,%.d,${<}} ${<}

source_code.h: Makefile ${DEPS}
	echo 'const char source_code[] = {' > ${@}
	( \
		echo Makefile ; \
		cat *.d | \
		sed -e 's/^ \+//g' -e 's/ \\$$//g' -e 's/ /\n/g' | \
		grep -Ev '((\.o:)|(source_code\.h))$$' \
	) | \
	tar -cf - -T /dev/stdin | \
	gzip -9 | \
	xxd -i    >> ${@}
	echo '};' >> ${@}

${TARGET}: source_code.h ${OBJS}
	${CC} ${CFLAGS} -o ${@} ${OBJS} ${SHARED_LIBS}

#conf.tab.c: conf.y
#	${BISON} conf.y

#lex.conf.c: conf.lex
#	${FLEX} conf.lex

${OBJS}: %.o: %.c
	${CC} -c ${CFLAGS} ${DFLAGS} ${INCS} ${<}

-include ${DEPS}

clean:
	-rm -f conf.tab.c conf.tab.h lex.conf.c source_code.h \
	${DEPS} ${OBJS} ${TARGET}
