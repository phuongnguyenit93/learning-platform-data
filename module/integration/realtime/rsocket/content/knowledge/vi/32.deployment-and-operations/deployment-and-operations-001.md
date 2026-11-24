# Đóng gói ứng dụng và công bố cổng TCP hoặc WebSocket

Một ứng dụng RSocket chỉ có thể được client sử dụng khi artifact chạy đúng runtime, server bind vào địa chỉ có thể truy cập và hạ tầng triển khai công bố đúng cổng/đường dẫn. Với Spring Boot, cùng một ứng dụng có thể chạy RSocket qua TCP trên một listener độc lập hoặc tích hợp RSocket WebSocket vào web server reactive. Hai cách triển khai có cấu hình và đường mạng khác nhau; cần chọn rõ transport trước khi đóng gói image và tạo Service/Ingress.

Quy trình triển khai gồm bốn phần: tạo executable JAR, cấu hình server theo môi trường, đóng gói runtime thành container image và công bố endpoint qua Docker/Kubernetes/load balancer. Sau khi deploy, cần xác minh cả kết nối thật, readiness, TLS, proxy timeout và khả năng shutdown/drain.

## 1. Bức tranh triển khai

```mermaid
flowchart TD
    A[Java source + Gradle] --> B[Spring Boot executable JAR]
    B --> C[OCI container image]
    C --> D[Container runtime / Kubernetes]
    D --> E{RSocket transport}
    E -->|TCP| F[Dedicated RSocket port]
    E -->|WebSocket| G[Reactive web server + mapping path]
    F --> H[TCP Load Balancer / Service]
    G --> I[HTTP(S) Ingress / WebSocket proxy]
    H --> J[RSocket client]
    I --> J
    D --> K[Health, metrics and logs]
```

RSocket là protocol chạy trên byte-stream transport. TCP và WebSocket có thể mang các interaction model giống nhau, nhưng network infrastructure công bố endpoint khác nhau. TCP thường dùng cổng riêng; WebSocket thường đi qua cổng HTTP(S) và một mapping path như `/rsocket`.

## 2. Chọn mô hình server trước khi đóng gói

Spring Boot hỗ trợ hai cách triển khai phổ biến:

| Mô hình | Cấu hình chính | Cổng được công bố |
|---|---|---|
| RSocket TCP server độc lập | `spring.rsocket.server.transport=tcp`, `spring.rsocket.server.port` | Cổng RSocket riêng, ví dụ `7000` |
| RSocket WebSocket gắn vào WebFlux server | `transport=websocket`, `mapping-path=/rsocket` | Cổng web server, ví dụ `8080`, cùng path `/rsocket` |
| RSocket server độc lập qua WebSocket | `transport=websocket`, `port` và cấu hình path phù hợp | Cổng riêng của embedded RSocket server |

Với WebFlux application, Spring Boot chỉ gắn RSocket WebSocket vào web server khi ứng dụng là reactive và có cả `spring.rsocket.server.mapping-path` cùng `spring.rsocket.server.transport=websocket`. Cách tích hợp này chỉ được hỗ trợ với Reactor Netty. Nếu không dùng mô hình đó, Spring Boot có thể khởi chạy RSocket server độc lập; server độc lập cần khai báo port. Không nhầm cổng HTTP của ứng dụng với cổng RSocket TCP. [Spring Boot RSocket reference](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)

Một cấu hình auto-configuration chọn một transport cho RSocket server đó. Nếu cần đồng thời TCP và WebSocket, hãy thiết kế hai listener rõ ràng bằng cấu hình server riêng được quản lý tường minh hoặc triển khai hai workload; không giả định một property tự động mở cả hai cổng.

## 3. Chuẩn bị dependency và executable JAR

Với Gradle và Spring Boot plugin, dependency RSocket thường là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
}
```

Nếu muốn tích hợp WebSocket vào HTTP web server, thêm WebFlux:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

`spring-boot-starter-rsocket` cung cấp hạ tầng Spring Messaging/RSocket và codec mặc định. WebFlux cung cấp reactive web server để tích hợp WebSocket vào cùng cổng HTTP. Ứng dụng TCP-only không cần thêm WebFlux chỉ vì dùng RSocket.

Build executable JAR:

```bash
./gradlew clean bootJar
```

Artifact thường nằm trong `build/libs/`. Có thể kiểm tra nội dung archive và chạy thử:

```bash
jar tf build/libs/rsocket-service.jar
java -jar build/libs/rsocket-service.jar
```

Tên JAR trong ví dụ cần thay bằng artifact thực tế của dự án. Nên chạy cùng JDK/runtime major version được hỗ trợ bởi ứng dụng và kiểm tra cấu hình profile trước khi đưa vào image.

## 4. Cấu hình RSocket TCP server

TCP server độc lập thường dùng port riêng:

```yaml
spring:
  application:
    name: device-service
  rsocket:
    server:
      transport: tcp
      address: 0.0.0.0
      port: 7000
```

`address: 0.0.0.0` cho phép process bind trên các network interface của container. Nếu bind vào `127.0.0.1`, container port mapping hoặc Kubernetes Service từ bên ngoài container sẽ không truy cập được listener đó. Chỉ bind địa chỉ cụ thể khi hạ tầng có yêu cầu rõ ràng.

Các biến môi trường tương ứng thường có thể dùng để override cấu hình Spring Boot:

```text
SPRING_RSOCKET_SERVER_TRANSPORT=tcp
SPRING_RSOCKET_SERVER_ADDRESS=0.0.0.0
SPRING_RSOCKET_SERVER_PORT=7000
```

Client TCP kết nối tới host/port đã công bố:

```java
RSocketRequester requester = builder
    .tcp("device-service.internal", 7000);
```

Không dùng `localhost` từ container client để gọi container server khác. Trong Docker Compose hoặc Kubernetes, hãy dùng service name/DNS nội bộ và port của service.

## 5. Cấu hình WebSocket gắn vào WebFlux server

Khi ứng dụng là WebFlux reactive application và dùng Reactor Netty, có thể gắn RSocket vào web server hiện có:

```yaml
spring:
  main:
    web-application-type: reactive
  application:
    name: realtime-gateway
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket

server:
  address: 0.0.0.0
  port: 8080
```

Trong mô hình này, `server.port` là cổng web server. RSocket được phục vụ tại path `/rsocket` trên cổng đó; không cần mở thêm một cổng TCP RSocket riêng. Nếu ứng dụng có HTTP API, Actuator hoặc endpoint web khác, chúng có thể dùng cùng web server và cần được bảo vệ theo security policy.

Client WebSocket kết nối bằng URI đầy đủ:

```java
Mono<RSocketRequester> requester = builder
    .websocket(URI.create("wss://realtime.example.com/rsocket"));
```

URI công khai phải khớp scheme (`ws`/`wss`), hostname, port và mapping path mà proxy chuyển tiếp. Browser client thường dùng `wss://` khi truy cập qua HTTPS.

## 6. WebSocket server độc lập

Không phải mọi ứng dụng đều muốn tích hợp RSocket vào WebFlux web server. Spring Boot cũng hỗ trợ một RSocket server embedded độc lập qua WebSocket. Trong trường hợp đó, cấu hình `spring.rsocket.server.transport=websocket` và khai báo `spring.rsocket.server.port`; mapping path và endpoint phải được xác định nhất quán với client và phiên bản Boot đang dùng.

Ví dụ cấu hình server độc lập:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      address: 0.0.0.0
      port: 8090
      mapping-path: /rsocket
```

Khi chạy theo mô hình này, công bố cổng `8090` của embedded RSocket server. Đừng cấu hình nhầm port này thành `server.port` của web server nếu mục tiêu là listener độc lập. Hãy kiểm tra startup log và kết nối bằng client ở đúng URI trước khi triển khai rộng.

## 7. TCP và WebSocket khác nhau ở network boundary

| Tiêu chí | TCP RSocket | WebSocket RSocket |
|---|---|---|
| Endpoint | `host:port` | `ws(s)://host:port/path` |
| Cổng thường gặp | Cổng riêng như `7000` | Cổng web như `8080` hoặc `443` qua ingress |
| Hạ tầng | TCP load balancer, firewall, Kubernetes Service | HTTP reverse proxy/Ingress có hỗ trợ WebSocket upgrade |
| Client phổ biến | Java/service-to-service | Browser, Java và client hỗ trợ WebSocket |
| TLS | TLS trực tiếp trên transport hoặc bảo vệ ở network layer | `wss` từ client tới TLS endpoint; có thể terminate ở proxy |
| Timeout | TCP idle timeout và keepalive | HTTP/WebSocket proxy idle timeout và keepalive |

HTTP Ingress thông thường không tự động forward raw TCP RSocket. Nếu chọn TCP, cần LoadBalancer/NodePort/TCP proxy hoặc cấu hình TCP routing riêng của nền tảng. Nếu chọn WebSocket, proxy phải hỗ trợ HTTP Upgrade và giữ connection dài hạn.

## 8. Đóng gói bằng Dockerfile

Ví dụ Dockerfile tối giản cho executable JAR và RSocket TCP port `7000`:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

COPY build/libs/rsocket-service.jar /app/app.jar

USER 10001:10001

EXPOSE 7000/tcp

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0"

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ví dụ giả định build dùng Java 21 và base image có các tiện ích tạo user như Debian/Ubuntu. Chọn image/runtime phù hợp với Java version, kiến trúc CPU và chính sách bảo mật của tổ chức. Có thể dùng distroless hoặc image tối giản khác, nhưng cần điều chỉnh cách tạo user và entrypoint.

Với WebSocket gắn vào WebFlux server, công bố web port thay cho TCP RSocket port:

```dockerfile
EXPOSE 8080/tcp
```

`EXPOSE` chỉ là metadata mô tả cổng dự kiến của image; nó không tự publish cổng ra host. Lệnh chạy container hoặc cấu hình Service của orchestration mới quyết định port mapping.

## 9. Dùng Spring Boot Buildpacks

Spring Boot Gradle plugin có thể tạo OCI image bằng `bootBuildImage`:

```bash
./gradlew bootBuildImage --imageName=registry.example.com/device-service:1.0.0
```

Buildpacks nhận executable archive và tạo image theo buildpack lifecycle. Cách này giảm nhu cầu tự duy trì Dockerfile; vẫn cần cấu hình image name, registry credentials, Java runtime, environment và port phù hợp. Kiểm tra image được tạo trước khi push.

Không build image với tag `latest` duy nhất cho mọi lần release. Dùng version hoặc immutable digest để rollback và xác định chính xác artifact đang chạy.

## 10. Chạy container và publish port

TCP:

```bash
docker build -t device-service:1.0.0 .
docker run --rm \
  --name device-service \
  -e SPRING_RSOCKET_SERVER_TRANSPORT=tcp \
  -e SPRING_RSOCKET_SERVER_ADDRESS=0.0.0.0 \
  -e SPRING_RSOCKET_SERVER_PORT=7000 \
  -p 7000:7000 \
  device-service:1.0.0
```

WebSocket gắn vào WebFlux:

```bash
docker run --rm \
  --name realtime-gateway \
  -e SPRING_RSOCKET_SERVER_TRANSPORT=websocket \
  -e SPRING_RSOCKET_SERVER_MAPPING_PATH=/rsocket \
  -e SERVER_PORT=8080 \
  -p 8080:8080 \
  realtime-gateway:1.0.0
```

Trong Docker Compose, các container cùng network có thể gọi nhau bằng service name và container port. Không cần publish ra host nếu chỉ giao tiếp nội bộ.

## 11. Kubernetes Deployment cho TCP

Deployment khai báo container port để mô tả listener:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: device-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: device-service
  template:
    metadata:
      labels:
        app: device-service
    spec:
      containers:
        - name: app
          image: registry.example.com/device-service:1.0.0
          ports:
            - name: rsocket-tcp
              containerPort: 7000
              protocol: TCP
          env:
            - name: SPRING_RSOCKET_SERVER_TRANSPORT
              value: tcp
            - name: SPRING_RSOCKET_SERVER_ADDRESS
              value: 0.0.0.0
            - name: SPRING_RSOCKET_SERVER_PORT
              value: "7000"
```

Service nội bộ:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: device-service
spec:
  type: ClusterIP
  selector:
    app: device-service
  ports:
    - name: rsocket-tcp
      port: 7000
      targetPort: rsocket-tcp
      protocol: TCP
```

Service DNS nội bộ thường là `device-service` trong cùng namespace hoặc `device-service.<namespace>.svc`. Client kết nối tới port `7000` của Service; Kubernetes phân phối connection mới tới pod ready. Một RSocket connection dài hạn thường tiếp tục gắn với backend đã được chọn khi connection được thiết lập.

## 12. Kubernetes Service và Ingress cho WebSocket

Khi RSocket WebSocket được gắn vào WebFlux web server, container lắng nghe `8080` và path `/rsocket`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: realtime-gateway
spec:
  type: ClusterIP
  selector:
    app: realtime-gateway
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
```

Ingress ví dụ với path prefix:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: realtime-gateway
spec:
  rules:
    - host: realtime.example.com
      http:
        paths:
          - path: /rsocket
            pathType: Prefix
            backend:
              service:
                name: realtime-gateway
                port:
                  number: 80
```

Ingress controller phải hỗ trợ WebSocket upgrade và cấu hình timeout đủ dài cho connection realtime. Annotation và cấu hình timeout phụ thuộc controller (NGINX, Traefik, cloud ingress, v.v.); manifest Ingress chuẩn không bảo đảm mọi controller có cùng behavior. Kiểm tra path rewrite, idle timeout, buffering và TLS termination theo implementation cụ thể.

## 13. Công bố cổng không có nghĩa listener đã sẵn sàng

Một container có thể ở trạng thái running nhưng RSocket server chưa bind thành công hoặc dependency bắt buộc chưa sẵn sàng. `EXPOSE`, `containerPort` và Service port chỉ mô tả/cấu hình đường mạng; chúng không chứng minh handler có thể xử lý request.

Với WebFlux app có Actuator HTTP endpoint, có thể bật health probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
```

Kubernetes probe:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
```

Với TCP-only server không có HTTP management listener, HTTP probe trên `8080` sẽ không hoạt động. Có thể dùng TCP socket probe để kiểm tra port đang listen, nhưng nó chỉ xác minh socket accept connection, không chứng minh service dependency hoặc handler đã sẵn sàng. Nếu cần readiness sâu, triển khai management endpoint riêng hoặc health probe phù hợp với ứng dụng.

Không đưa mọi dependency tùy chọn vào liveness check. Một database tạm thời mất kết nối có thể khiến readiness chuyển false để ngừng nhận traffic, nhưng không nhất thiết nên làm Kubernetes restart process liên tục.

## 14. TLS cho TCP và WebSocket

Trên môi trường không tin cậy, bảo vệ transport bằng TLS và xác minh certificate ở client.

- **TCP:** có thể bật TLS trực tiếp cho RSocket server bằng SSL configuration/SSL bundle mà phiên bản Spring Boot hỗ trợ, hoặc bảo vệ đường truyền bằng service mesh/network layer có mutual TLS.
- **WebSocket:** client dùng `wss://`; TLS có thể kết thúc ở ingress/reverse proxy hoặc tại web server. Nếu proxy chuyển tiếp HTTP nội bộ không mã hóa, đánh giá trust boundary và yêu cầu mã hóa hop-to-hop.
- **mTLS:** chỉ bật client authentication khi đã cấp trust store/certificate cho đúng workload; quản lý rotation và expiry.
- **Hostname verification:** certificate SAN phải khớp hostname mà client dùng. Không tắt verification để chữa lỗi certificate.

Ví dụ khai báo SSL bundle/SSL properties phụ thuộc dòng Spring Boot và cách quản lý certificate. Hãy dùng secret mount hoặc secret manager; không commit private key/password vào `application.yml`, Dockerfile hay image layer. Khi TLS terminate ở proxy, cấu hình ingress và backend encryption theo policy của môi trường.

## 15. Network policy và firewall

Chỉ công bố đúng listener cần thiết:

| Transport | Cổng trong pod/container | Đường vào |
|---|---:|---|
| TCP RSocket | `7000/TCP` | Service/LoadBalancer/TCP proxy được phép |
| WebSocket qua WebFlux | `8080/TCP` | HTTP(S) Ingress/reverse proxy tới path `/rsocket` |
| Management HTTP (nếu tách riêng) | Ví dụ `8081/TCP` | Chỉ monitoring/probe network |

NetworkPolicy nên cho phép caller/service đúng namespace hoặc workload identity truy cập cổng RSocket. Không mở cổng TCP RSocket ra Internet chỉ vì ứng dụng cần kết nối nội bộ. Với WebSocket public, giới hạn origin/host ở tầng phù hợp, yêu cầu authentication và rate/connection quota.

## 16. Cấu hình theo môi trường và secrets

Không đóng cứng host, port, credentials hoặc endpoint production trong JAR. Dùng environment variables, Spring profiles, ConfigMap và Secret/secret manager:

```yaml
spring:
  config:
    activate:
      on-profile: production
  rsocket:
    server:
      transport: tcp
      address: 0.0.0.0
      port: ${RSOCKET_PORT:7000}
```

Ví dụ biến môi trường:

```text
SPRING_PROFILES_ACTIVE=production
RSOCKET_PORT=7000
```

Đối với Kubernetes, ConfigMap phù hợp cho cấu hình không bí mật; Secret hoặc external secret manager dành cho credential/certificate. Lưu ý Secret dạng Kubernetes mặc định được base64 encode, không phải tự động mã hóa an toàn ở mọi tầng; bật encryption at rest và giới hạn RBAC theo chính sách cluster.

## 17. Resource limits và JVM trong container

RSocket giữ connection và stream dài hạn, do đó memory không chỉ phụ thuộc request đang xử lý. Cần tính heap, direct memory, Netty buffer, TLS buffer, scheduler queue, payload buffer và số connection đồng thời.

Ví dụ giới hạn tài nguyên Kubernetes:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "2"
    memory: "1536Mi"
```

JVM có thể dùng container-aware memory sizing, ví dụ `-XX:MaxRAMPercentage=70`. Con số cần đo bằng tải thực tế; không đặt heap sát memory limit vì process còn cần metaspace, code cache, thread stack và direct memory. Theo dõi số connection, stream, pending payload, direct buffer và GC pause khi tăng tải.

Giới hạn frame/payload và fragment size cần phù hợp với client, transport và memory budget. Không tăng frame limit chỉ để tránh lỗi payload lớn; cân nhắc chunking, bounded buffer và giới hạn kích thước message.

## 18. Graceful shutdown và rolling deployment

RSocket connection có thể sống lâu hơn HTTP request thông thường. Khi deploy phiên bản mới, cần ngừng nhận connection mới, cho interaction đang chạy thời gian hoàn tất và đóng connection cũ có kiểm soát.

Với web server Spring Boot, có thể bật graceful shutdown:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

Đối với RSocket server độc lập, xác minh lifecycle bean/server thực sự dừng nhận connection mới và dispose connection theo behavior của implementation. Không giả định cấu hình graceful shutdown của web server tự động drain mọi listener RSocket độc lập.

Kubernetes nên có `terminationGracePeriodSeconds` đủ dài cho thời gian drain. Khi pod bắt đầu terminate, readiness cần chuyển false để Service ngừng chọn pod cho connection mới; sau đó chờ in-flight work theo deadline rồi kết thúc process. Client cần reconnect với backoff/jitter. Request có side effect cần idempotency; stream cần business cursor nếu protocol resume không còn khả dụng.

## 19. Kiểm tra endpoint sau khi deploy

Thực hiện kiểm tra theo thứ tự:

1. Container/pod ở trạng thái running và không restart liên tục.
2. Log xác nhận đúng profile, transport, port và mapping path.
3. Process bind đúng interface (`0.0.0.0` khi cần truy cập từ ngoài container).
4. Docker publish port hoặc Kubernetes Service targetPort trỏ đúng listener.
5. NetworkPolicy/firewall cho phép caller dự kiến.
6. TCP client kết nối đúng host/port hoặc WebSocket client kết nối đúng `ws(s)` URI/path.
7. SETUP/authentication thành công.
8. Gửi request-response thử tới route health/application đã định nghĩa.
9. Với WebSocket, xác minh proxy upgrade và idle timeout bằng connection giữ lâu.
10. Với rolling deployment, xác minh readiness, drain và reconnect không tạo retry storm.

TCP port check chỉ chứng minh có listener. Cần một RSocket interaction thật để xác minh protocol, route, codec và authentication.

## 20. Lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Container chạy nhưng client không kết nối được | Server bind `localhost` trong container | Bind `0.0.0.0` hoặc interface phù hợp |
| `Connection refused` | Sai port, listener chưa start hoặc Service targetPort sai | Kiểm tra startup log, container port và Service |
| TCP chạy local nhưng lỗi trên Kubernetes | Chưa expose Service/NetworkPolicy hoặc dùng sai DNS | Kiểm tra Service selector, port, policy và DNS |
| WebSocket handshake 404 | Sai mapping path hoặc Ingress rewrite | Đồng bộ `/rsocket` giữa server, proxy và client |
| WebSocket handshake 400/426 | Proxy không forward Upgrade hoặc subprotocol cần thiết | Cấu hình WebSocket support trên ingress/proxy |
| WebSocket ngắt sau một khoảng idle | Proxy/load balancer idle timeout | Đồng bộ keepalive và timeout của các hop |
| HTTP Ingress không truy cập được TCP RSocket | Ingress chỉ route HTTP(S) | Dùng TCP LoadBalancer/proxy hoặc chuyển sang WebSocket |
| Pod Ready nhưng handler chưa hoạt động | Probe chỉ kiểm tra process/port | Dùng readiness probe phản ánh khả năng phục vụ |
| Pod bị restart khi tải tăng | Memory limit quá thấp, heap/direct buffer vượt budget | Đo memory, giảm buffer/connection hoặc điều chỉnh limit |
| Deploy làm stream bị ngắt | Pod bị terminate trước khi drain | Readiness false, grace period và client reconnect/resume |
| TLS handshake thất bại | Certificate/SAN/trust chain không khớp | Sửa certificate và trust configuration, không tắt verification |

## 21. Quy trình đóng gói và công bố endpoint

1. Chọn TCP, WebSocket tích hợp WebFlux hoặc WebSocket server độc lập.
2. Thêm `spring-boot-starter-rsocket`; thêm WebFlux nếu tích hợp WebSocket vào reactive web server.
3. Build executable JAR bằng `bootJar` và chạy thử với cấu hình môi trường.
4. Tạo OCI image bằng Dockerfile hoặc `bootBuildImage`; chạy dưới non-root user.
5. Externalize port, profile, certificate và secrets.
6. Với TCP, bind port riêng và công bố bằng TCP Service/LoadBalancer.
7. Với WebSocket, công bố web port và path qua reverse proxy hỗ trợ Upgrade.
8. Cấu hình readiness/liveness, resource limit, network policy và TLS.
9. Thiết kế graceful shutdown, drain, reconnect và business recovery.
10. Kiểm thử bằng client RSocket thật sau khi deploy, không chỉ kiểm tra port.

## 22. Quy tắc thiết kế

1. Đóng gói ứng dụng thành executable JAR và OCI image có version/digest xác định.
2. Cấu hình transport/port/path qua môi trường, không hardcode endpoint production.
3. TCP RSocket dùng cổng riêng; WebSocket tích hợp WebFlux dùng web port và mapping path.
4. Chỉ dùng mô hình WebSocket gắn vào web server khi app là reactive và server là Reactor Netty.
5. Phân biệt container `EXPOSE`, Docker publish port và Kubernetes Service targetPort.
6. Dùng TCP load balancer cho TCP; dùng ingress/reverse proxy có WebSocket upgrade cho WebSocket.
7. Bind interface có thể truy cập từ container network và giới hạn network policy.
8. Bảo vệ transport bằng TLS, quản lý certificate/secret bên ngoài image.
9. Dùng readiness để ngừng nhận connection mới và drain trước khi shutdown.
10. Kiểm tra RSocket interaction thật sau deployment và theo dõi connection/stream lifecycle.

Đóng gói đúng chỉ tạo ra một process có thể chạy; công bố đúng endpoint mới giúp client tìm và kết nối được server. TCP cần listener và đường mạng TCP riêng, còn WebSocket tích hợp WebFlux dùng cổng web cùng mapping path và proxy hỗ trợ upgrade. Khi port mapping, readiness, TLS, resource limit và shutdown lifecycle được cấu hình đồng bộ, ứng dụng RSocket có thể được triển khai và nâng cấp mà không phụ thuộc vào cấu hình máy phát triển.

## Tài liệu tham khảo

- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot Reference — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot Gradle Plugin — Building OCI images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html)
- [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
