FROM golang:1.14.4-stretch

RUN apt-get update && \
    apt-get install -y  \
    gcc cmake autoconf build-essential libtool pkg-config libmnl-dev libyaml-dev wget git net-tools


RUN cd ~
RUN cd $GOPATH/src && git clone --recursive https://github.com/my5G/my5G-core


RUN cd $GOPATH/src && git clone https://github.com/my5G/my5G-non3GPP-access.git $GOPATH/src/my5G-core/src/ue
RUN cd $GOPATH/src/my5G-core && go build -o bin/ue -x src/ue/ue.go
 
# Backup of the config folder
RUN cd $GOPATH/src/my5G-core  && mv -f config config.orig

# Using my5g_wifi_config folder for configuration
RUN cd $GOPATH/src/my5G-core  && cp -R src/ue/sample/my5g_wifi_config/ config

# set UE http bind address 
RUN cd $GOPATH/src/my5G-core  && sed -i 's/HttpIPv4Address: .*/HttpIPv4Address: 10.100.200.100/' config/uecfg.conf


RUN echo "I am running fine"