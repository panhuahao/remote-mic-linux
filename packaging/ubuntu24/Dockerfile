ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
ARG APT_MIRROR=http://archive.ubuntu.com/ubuntu
RUN sed -i -E "s@http://(archive|security).ubuntu.com/ubuntu/?@${APT_MIRROR}/@g" /etc/apt/sources.list.d/ubuntu.sources && apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-gi python3-cairo \
    gir1.2-gtk-3.0 gir1.2-atspi-2.0 gir1.2-ayatanaappindicator3-0.1 \
    build-essential binutils squashfs-tools pkg-config \
    libgtk-3-bin libgdk-pixbuf2.0-bin librsvg2-common \
    glib-networking dconf-gsettings-backend adwaita-icon-theme \
    gsettings-desktop-schemas libgtk-3-0t64 libglib2.0-bin hicolor-icon-theme \
    bluez pipewire pipewire-bin wl-clipboard xwayland \
    xvfb xauth dbus-x11 dbus-user-session at-spi2-core ca-certificates \
    fonts-noto-cjk fonts-dejavu-core desktop-file-utils \
    && rm -rf /var/lib/apt/lists/*
# Keep the default Ubuntu input method available in the private GTK cache.
RUN apt-get update && apt-get install -y --no-install-recommends ibus-gtk3 \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv
COPY requirements.txt /tmp/requirements.txt
ARG PIP_PROXY=
RUN HTTPS_PROXY="$PIP_PROXY" HTTP_PROXY="$PIP_PROXY" \
 /opt/venv/bin/pip install --timeout=120 --no-cache-dir -r /tmp/requirements.txt
RUN useradd --create-home --uid 1001 tester
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
