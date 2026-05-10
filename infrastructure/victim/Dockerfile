FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Install a lightweight Desktop (XFCE), VNC, noVNC, and SSH
RUN apt-get update && apt-get install -y \
    xfce4 xfce4-goodies \
    x11vnc xvfb \
    novnc websockify \
    openssh-server net-tools nmap \
    && rm -rf /var/lib/apt/lists/*

# Setup SSH and Persistence Directories
RUN mkdir /var/run/sshd && mkdir -p /root/Desktop /home/ubuntu/Desktop
RUN echo 'root:password' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true

EXPOSE 22 80 5900

# Start the virtual screen, desktop, VNC, Websockify (Port 80), and SSH
CMD rm -rf /tmp/.X* && \
    Xvfb :0 -screen 0 1280x720x24 & \
    sleep 2 && \
    DISPLAY=:0 xfce4-session & \
    x11vnc -display :0 -nopw -forever & \
    websockify --web=/usr/share/novnc/ 80 localhost:5900 & \
    service ssh start && \
    tail -f /dev/null
