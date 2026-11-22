# Cấu hình cổng, địa chỉ lắng nghe và tài nguyên trong container

## 1. Bối cảnh của bài học

Bài học thuộc mục **Triển khai ứng dụng** trong Spring Boot web runtime. Một ứng dụng chạy hoàn hảo ở máy phát triển nhưng khi đóng gói Docker, triển khai Kubernetes hay chuyển lên PaaS lại gặp các lỗi:

- Log Spring Boot báo `Tomcat started on port 8080` nhưng host gọi `localhost:18080` không được.
- Dockerfile khai báo `EXPOSE 8080` mà không thấy cổng nào mở trên máy host.
- Pod có trạng thái `Running` nhưng Service không có ready endpoints, hoặc client nhận connection refused.
- Container bị `OOMKilled` dù Java heap chưa chạm `-Xmx`.
- CPU quota một core nhưng tăng Tomcat worker threads không cải thiện throughput.
- Health probe kiểm tra một management port khác, báo khỏe trong khi main HTTP connector không nhận request.
- Rolling update khiến kết nối dài bị cắt, Java process không nhận `SIGTERM` đúng cách.

Để khắc phục, cần phân biệt **lớp ứng dụng, lớp network namespace và lớp quản lý tài nguyên**. Cấu hình `server.port` là một quyết định của Java process; Docker `-p` và Kubernetes `Service.targetPort` là routing bên ngoài process; memory/CPU cgroups là ngân sách runtime mà JVM phải tôn trọng.

Mục tiêu sau bài học:
1. Giải thích `server.port`, `server.address`, `PORT`/`SERVER_PORT` và cấu hình externalized của Spring Boot 3.5.
2. Phân biệt `127.0.0.1`, `0.0.0.0`, container IP, Pod IP và các lớp host/Pod network namespace.
3. Cấu hình Dockerfile, `EXPOSE`, `docker run -p`, Compose, Kubernetes `containerPort`, Service `port`/`targetPort` và Ingress.
4. Đặt tài nguyên CPU, RAM, JVM heap/direct/native memory, file descriptor và temp storage hợp lý.
5. Triển khai liveness/readiness/startup probes trên đúng port, giữ hành vi graceful shutdown trong container.
6. Xây ứng dụng Java 17 runnable, đóng gói multi-stage image non-root, kiểm tra port thực tế bằng HTTP.
7. Chẩn đoán sai cổng, bind sai địa chỉ, CPU throttling, memory pressure và lỗi probe trước khi chỉnh nhầm controller.

> **Phiên bản thực hành:** Spring Boot **3.5.x**, Java **17+**, Gradle Groovy, Spring MVC/Tomcat, Docker và Kubernetes cơ bản. Với Boot 3.5, embedded server mặc định listen cổng **8080** nếu không override. Một số lựa chọn container/JVM/probe có thể khác theo kernel, JDK patch version và platform; luôn kiểm tra dữ liệu runtime thay vì khẳng định con số demo là mặc định ở mọi hệ thống.

## 2. Phân biệt ba cổng trong một HTTP request

Một ví dụ Docker:

~~~text
Browser/host
    |
    | http://localhost:18080/api/hello
    v
Host port 18080
    |
    | docker -p 18080:8080
    v
Container port 8080
    |
    | Spring server.port=8080
    v
Embedded Tomcat -> Controller
~~~

Một ví dụ Kubernetes:

~~~text
Client trong cluster -> runtime-demo:80
                            |
                            v
                   Service.port = 80
                            |
                            v
                   Service.targetPort = http
                            |
                            v
                   Pod containerPort name=http = 8080
                            |
                            v
                   Spring Boot listen :8080
~~~

Các con số khác nhau **hoàn toàn bình thường**. Chỉ cần từng cạnh routing đúng:

| Thuộc tính | Tầng quản lý | Ví dụ | Có khởi động listener thật không? |
|---|---|---|---|
| `server.port` | Spring Boot JVM | 8080 | **Có**: embedded server bind port |
| `server.address` | Spring Boot JVM | `0.0.0.0` | Chọn IP/interface để bind |
| `EXPOSE 8080` | Dockerfile image metadata | 8080 | **Không** |
| Docker `-p 18080:8080` | Docker host NAT/publish | Host 18080 → container 8080 | Publish host port, không thay Spring |
| Compose `ports` | Docker networking | `127.0.0.1:18080:8080` | Host mapping |
| Kubernetes `containerPort` | Pod spec | 8080 | **Không**: mô tả port |
| Kubernetes `Service.port` | Service | 80 | Client-facing port của Service |
| Kubernetes `Service.targetPort` | Service → Pod | 8080 hoặc `http` | Chọn đích ở Pod |
| Ingress/Gateway | Edge | HTTPS 443 | Route đến Service, không đổi Java port |
| `management.server.port` | Spring Actuator | 9090 | Có thể tạo management listener riêng |

**Quy tắc:** Spring phải listen đúng port mà `-p`/`targetPort` hướng tới; không ép Java listen cổng public 80/443 khi TLS kết thúc ở Ingress hoặc reverse proxy.

## 3. server.port: default, override và random port

Spring Boot 3.5 có main HTTP port mặc định **8080**. Có thể khai báo:

~~~yaml
server:
  port: 8080
~~~

Hoặc:

~~~properties
server.port=8080
~~~

Hoặc đổi khi chạy:

~~~bash
java -jar app.jar --server.port=9090
~~~

Hoặc OS env:

~~~bash
SERVER_PORT=9090 java -jar app.jar
~~~

Hoặc Java system property:

~~~bash
java -Dserver.port=9090 -jar app.jar
~~~

`SERVER_PORT` được Spring Boot relaxed binding hiểu là `server.port`. Boot có nhiều property sources với thứ tự ưu tiên; command-line arguments thường có thể override config file và env được ưu tiên hơn value trong `application.yml`. Khi thực tế port khác mong đợi, kiểm tra tất cả env, CLI, system properties, profile-specific config và startup logs thay vì đoán do Docker.

### Biến PORT do PaaS cấp

Một số PaaS cấp `PORT`, nhưng **PORT không phải tên property chuẩn Boot tự map vào server.port**. Viết explicit:

~~~yaml
server:
  port: ${PORT:8080}
~~~

Giải thích cú pháp placeholder:
- Khi `PORT=9090`: Spring dùng 9090.
- Khi PORT không có: dùng 8080.
- Nếu có `SERVER_PORT` hoặc `--server.port` ưu tiên cao hơn, chúng có thể override YAML này.

**Chọn một contract:** hoặc dùng `SERVER_PORT` trực tiếp từ môi trường, hoặc dùng `PORT` trong YAML. Không đặt hai nguồn giá trị khác nhau rồi assume bên nào thắng.

### server.port=0 và =-1

- `server.port=0`: để OS chọn một port còn rảnh; hữu ích với integration tests/`@LocalServerPort`.
- `server.port=-1`: theo Boot docs, tắt HTTP endpoints nhưng vẫn có thể tạo WebApplicationContext.
- `spring.main.web-application-type=none`: bỏ web application type, không giống hệt `server.port=-1`.

**Không dùng port 0 tùy tiện khi Kubernetes Service.targetPort cố định**: Pod có thể listen ephemeral port khác 8080, Service vẫn gửi về 8080 và không kết nối được.

### Port conflict là phạm vi network namespace

Hai Docker containers bình thường có network namespace riêng, có thể cùng listen **internal port 8080**. Hai Kubernetes Pods cũng vậy. Nhưng **hai containers trong cùng một Kubernetes Pod chia sẻ network namespace**, nên có thể xung đột nếu cùng bind một IP:port. Docker host có thể xung đột khi hai containers cùng publish **host port 18080**.

## 4. server.address và địa chỉ bind

~~~yaml
server:
  address: "0.0.0.0"
  port: 8080
~~~

Ý nghĩa các giá trị:

| Bind address | Ý nghĩa | Có nhận request qua Pod/container IP? |
|---|---|---|
| `0.0.0.0` | Mọi IPv4 interfaces trong **namespace của process** | Thường có nếu mạng/port cho phép |
| `127.0.0.1` | IPv4 loopback của **namespace đó** | Thường **không** khi request tới Pod IP |
| Một IP cụ thể | Interface có địa chỉ đó | Chỉ khi IP tồn tại trong namespace và route tới |
| `::` | IPv6 wildcard | IPv4 dual-stack còn tùy JVM/OS socket configuration |
| Hostname | Resolve rồi bind IP | Có thể fail nếu hostname không resolve thành IP local |

### 0.0.0.0 không phải tự động public Internet

`0.0.0.0` chỉ có nghĩa process chấp nhận connections trên các IPv4 interfaces của network namespace. Có public hay không còn tùy host port publishing, firewall, Kubernetes Service/Ingress, NetworkPolicy, cloud security group và authentication.

### 127.0.0.1 trong container không phải localhost của host

~~~text
Host namespace:       localhost -> host loopback
Container A:          localhost -> A loopback
Container B:          localhost -> B loopback
Pod X:                localhost -> shared loopback của các containers cùng Pod
Pod Y:                localhost -> loopback của Pod Y, không phải Pod X
~~~

Nếu Spring listen `127.0.0.1:8080` bên trong Docker container, Docker publish `-p 18080:8080` thường forward tới container network IP:8080, **không đến socket chỉ bind loopback**; host request thất bại dù log Boot báo 8080. Sửa thành `server.address=0.0.0.0` cho main listener container.

Ngược lại, bind management listener vào loopback có thể hữu ích cho tác vụ nội bộ cùng namespace, nhưng **không thay auth/security** và làm remote scraper/probe khó truy cập.

### Bind hostname hoặc Pod IP trực tiếp có rủi ro gì?

Pod IP có thể thay đổi khi restart/rolling deploy. Nếu hardcode Pod IP trong `server.address` hoặc HTTP client URL, phiên bản mới có thể bind lỗi hoặc client không tìm được đúng Pod. Dùng `0.0.0.0` cho listener và **Service DNS** cho kết nối tới một service khác. Không coi `localhost` là DNS của một service Kubernetes khác.

## 5. Environment variables, profile và thứ tự ưu tiên

Các cách cấu hình:

| Nguồn | Ví dụ | Dùng cho |
|---|---|---|
| `application.yml` | `server.port: 8080` | Default trong source |
| OS environment | `SERVER_PORT=9090` | Runtime override |
| Custom env placeholder | `server.port: ${PORT:8080}` | PaaS cấp PORT |
| CLI arg | `--server.port=9090` | Test/launcher override |
| JVM option | `-Dserver.port=9090` | Java process flag |
| ConfigMap | `PORT=8080` | Config không nhạy cảm trong K8s |
| Secret/external vault | Password/token/cert | Dữ liệu cần bảo vệ |

Một cấu hình dễ kiểm soát cho bài thực hành:

~~~yaml
server:
  port: ${PORT:8080}
  address: ${SERVER_ADDRESS:0.0.0.0}
  shutdown: graceful
~~~

Khi run Docker, đặt `PORT=8080`, không đặt thêm `SERVER_PORT` tranh ưu tiên. `SERVER_ADDRESS=127.0.0.1` có thể dùng để thử lỗi bind từ bên ngoài, nhưng deployment bình thường nên để 0.0.0.0.

Nếu có `application-prod.yml`, `spring.profiles.active`, `spring.config.additional-location` hoặc `SPRING_APPLICATION_JSON`, chúng có thể override giá trị. Đừng đoán “Docker đã đổi port” trong khi profile file mới là nguồn override. Khi cần điều tra, dùng startup logs, actuator configprops/env **được bảo vệ** hoặc Java runtime endpoint không chứa secrets.

## 6. Dockerfile EXPOSE không publish host port

Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

chỉ báo image dự kiến sử dụng port 8080. Nó **không tự tạo host-published socket**. Để host gọi ứng dụng, dùng:

~~~bash
docker run --rm -p 18080:8080 runtime-demo:1.0
~~~

- 18080 bên host.
- 8080 bên container.
- Boot vẫn listen 8080.
- Host truy cập `http://localhost:18080`.

### Publish chỉ trên host loopback để học an toàn

~~~bash
docker run --rm \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

`127.0.0.1` trong Docker `-p` ở **phía host**, không phải Spring `server.address`. Với Docker daemon phổ biến, nếu không chỉ định host IP, published port có thể tiếp cận từ nhiều host interfaces; không public debug/Actuator trên máy dùng chung chỉ vì tiện.

### -p khác -P

- `-p 18080:8080`: mapping explicit.
- `-P`/`--publish-all`: Docker tự gán host ports cho các EXPOSE ports; xem mapping bằng `docker port`.
- `--expose`: thêm port metadata, không tự publish.
- `--network host` (khi runtime hỗ trợ) làm container dùng host network, thay đổi isolation và thường bỏ qua port publishing; không dùng làm “fix nhanh” cho sai mapping.

### Các tình huống thường gặp

| Spring listener | Docker mapping | Kết quả |
|---|---|---|
| `0.0.0.0:8080` | `-p 18080:8080` | Host tới 18080 |
| `0.0.0.0:9090` | `-p 18080:8080` | Sai đích 8080, request fail |
| `127.0.0.1:8080` | `-p 18080:8080` | Loopback-only, external forwarding thường fail |
| `0.0.0.0:8080` | EXPOSE 8080 nhưng không `-p` | Không tự truy cập từ host localhost |
| `0.0.0.0:8080` | `-p 127.0.0.1:19090:8080` | Host dùng 19090, listener vẫn 8080 |

## 7. Demo runnable Spring Boot Java 17

Demo tạo:
- `GET /api/hello` trả JSON cố định.
- `GET /api/runtime` đọc **cổng thực tế** mà embedded Tomcat đang nghe, JVM processor count và max heap size.
- Actuator health, liveness và readiness paths.
- Không trả env vars, tokens hoặc JVM secret options ra HTTP endpoint.

### 7.1. Tạo project

Trong Spring Initializr:
- Spring Boot **3.5.x**.
- Java **17+**.
- Gradle **Groovy**.
- Group: `demo`; Artifact: `runtime-demo`.
- Dependencies: **Spring Web**, **Spring Boot Actuator**, **Spring Boot Starter Test**.

Trong `build.gradle` của project Initializr, dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Thêm sau block dependencies để tạo executable jar có tên ổn định:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

Đây là **Gradle fragments** trong project đã có Spring Boot plugin/repositories/Gradle wrapper; không phải `build.gradle` hoàn chỉnh khi đứng riêng.

### 7.2. Java source file hoàn chỉnh

Tạo `src/main/java/demo/runtime/ContainerRuntimeApplication.java`:

~~~java
package demo.runtime;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ContainerRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerRuntimeApplication.class, args);
    }
}

@RestController
class RuntimeController {

    private final ServletWebServerApplicationContext context;

    RuntimeController(ServletWebServerApplicationContext context) {
        this.context = context;
    }

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }

    @GetMapping("/api/runtime")
    public Map<String, Object> runtime() {
        Runtime jvm = Runtime.getRuntime();

        return Map.of(
            "message", "running",
            "listenPort", context.getWebServer().getPort(),
            "availableProcessors", jvm.availableProcessors(),
            "maxHeapMiB", jvm.maxMemory() / (1024 * 1024)
        );
    }
}
~~~

**QA cấu trúc source:**
- File `ContainerRuntimeApplication.java` có một public class cùng tên, thêm một class package-private `RuntimeController`; Java 17 cho phép cấu trúc này.
- `@SpringBootApplication` thực hiện component scan trong `demo.runtime` nên có controller.
- `ServletWebServerApplicationContext.getWebServer().getPort()` trả actual port, gồm trường hợp test port=0.
- `Runtime.availableProcessors()` phản ánh JVM processor count theo heuristics/flags, **không phải guarantee số core host hoặc CPU request**.
- `Runtime.maxMemory()` là max Java heap của JVM, **không phải process RSS/cgroup memory limit**.
- JSON `Map.of` không đảm bảo thứ tự fields, nên tests nên kiểm tra theo key, không so raw string.

Nếu dùng Spring WebFlux/Reactor Netty thay MVC/Tomcat, interface context tương ứng là reactive; đừng copy nguyên `ServletWebServerApplicationContext` rồi nghĩ sẽ hoạt động trên reactive-only starter.

### 7.3. application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: ${PORT:8080}
  address: ${SERVER_ADDRESS:0.0.0.0}
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Ý nghĩa:
- PORT khi không set là 8080.
- SERVER_ADDRESS khi không set là 0.0.0.0.
- `server.shutdown: graceful` khai báo explicit; Boot 3.5 đã bật graceful mặc định cho embedded web servers được hỗ trợ.
- `timeout-per-shutdown-phase=25s` là **ngân sách chờ theo từng nhóm SmartLifecycle phase**, không phải hard timeout cho toàn process/container.
- Health probes được bật trong local/cluster.
- `add-additional-paths=true` đặt `/livez` và `/readyz` trên **main server port**, giúp probes quan sát chính HTTP connector nhận traffic.

### 7.4. Run local

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ở terminal khác:

~~~bash
curl -sS -i http://localhost:8080/api/hello
curl -sS http://localhost:8080/api/runtime
curl -sS -i http://localhost:8080/readyz
~~~

`/api/hello` trả HTTP 200 và JSON:

~~~json
{"message":"hello"}
~~~

`/api/runtime` có thể trả:

~~~json
{
  "message": "running",
  "listenPort": 8080,
  "availableProcessors": 2,
  "maxHeapMiB": 384
}
~~~

**Hai số 2 và 384 chỉ là minh họa, không phải kết quả cố định.** Chúng phụ thuộc JVM, cgroups/host và flags. `listenPort` là 8080 nếu không có override. `/readyz` trả success khi app đã ở trạng thái accepting traffic.

### 7.5. Thử đổi cổng

Build executable jar:

~~~bash
./gradlew bootJar
~~~

Windows:

~~~powershell
.\gradlew.bat bootJar
~~~

Chạy:

~~~bash
java -jar build/libs/app.jar --server.port=9090
~~~

Kiểm tra:

~~~bash
curl -sS http://localhost:9090/api/runtime
~~~

Kỳ vọng JSON có `"listenPort":9090`. Nếu jar đã bị đổi tên vì build khác, điều chỉnh theo output thật; demo Gradle cấu hình jar tên `app.jar`.

Thử random port:

~~~bash
java -jar build/libs/app.jar --server.port=0
~~~

OS chọn port còn rảnh; xem startup logs hoặc dùng `@LocalServerPort` trong tests để biết. Đừng hardcode client tới 8080 trong case này.

## 8. Dockerfile multi-stage cho Java 17

Tạo `Dockerfile` tại root project:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS builder

WORKDIR /workspace

COPY gradlew ./gradlew
COPY gradle/ ./gradle/
COPY settings.gradle build.gradle ./
COPY src/ ./src/

RUN chmod +x ./gradlew && ./gradlew --no-daemon bootJar

FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --from=builder --chown=10001:10001 \
    /workspace/build/libs/app.jar /app/app.jar

USER 10001:10001

# EXPOSE mô tả port, không tự publish host.
EXPOSE 8080

# Exec form để JVM nhận SIGTERM trực tiếp.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là Dockerfile hoàn chỉnh cho **Gradle Groovy project từ Initializr**, đã bổ sung `bootJar.archiveFileName='app.jar'`. Nếu project dùng `build.gradle.kts` hoặc multi-module, cần sửa Docker COPY và Gradle output path tương ứng. Không đưa Dockerfile demo vào production mà không scan base images và pin versions/digests phù hợp với quy trình bảo mật.

Ưu điểm:
- Builder image dùng JDK để compile.
- Runtime image chỉ cần JRE + app.jar, không cần Gradle trong production.
- Java process chạy bằng UID/GID 10001, không dùng root khi không cần.
- `EXPOSE 8080` là metadata.
- Exec-form ENTRYPOINT giúp platform send signals tới JVM, hỗ trợ graceful shutdown.
- Dữ liệu được copy tách builder/runtime; không mang source/build tools vào runtime image.

Tạo `.dockerignore`:

~~~text
.git
.gradle
build
out
*.log
.env
.env.*
.idea
.vscode
~~~

Không ignore `gradlew` hoặc `gradle/wrapper`, vì Docker build cần chúng.

### Build và chạy

~~~bash
docker build -t runtime-demo:1.0 .
~~~

Chạy:

~~~bash
docker run --rm \
  --name runtime-demo \
  --memory=768m \
  --cpus=1 \
  -e PORT=8080 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=55.0" \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

Ở terminal host:

~~~bash
curl -sS -i http://localhost:18080/api/hello
curl -sS http://localhost:18080/api/runtime
curl -sS -i http://localhost:18080/readyz
~~~

**Điểm cần quan sát:** JSON của `/api/runtime` vẫn có `listenPort=8080`, không phải 18080. `JAVA_TOOL_OPTIONS` tác động JVM heap sizing, không đổi HTTP port. `--memory`/`--cpus` tạo resource limits mà container JVM phải xử lý theo runtime.

### Thử sai mapping để hiểu lỗi

~~~bash
docker run --rm \
  -e PORT=9090 \
  -p 127.0.0.1:19090:8080 \
  runtime-demo:1.0
~~~

Spring listen **9090** nhưng Docker chuyển host 19090 đến container 8080 nên thường connection refused/reset. Sửa:

~~~bash
docker run --rm \
  -e PORT=9090 \
  -p 127.0.0.1:19090:9090 \
  runtime-demo:1.0
~~~

Dù Dockerfile `EXPOSE 8080`, explicit `-p ...:9090` vẫn hợp lệ; nhưng hãy cập nhật metadata/manifest khi thay port thật cho deployment production.

### Nếu bind loopback bên trong

~~~bash
docker run --rm \
  -e SERVER_ADDRESS=127.0.0.1 \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

Listener của Spring chỉ nằm tại **container loopback** nên host-published traffic tới container IP thường không đến được. Thử nghiệm xong đổi lại 0.0.0.0.

## 9. Docker Compose và service DNS

Tạo `compose.yaml`:

~~~yaml
services:
  runtime:
    build: .
    image: runtime-demo:1.0
    environment:
      PORT: "8080"
      SERVER_ADDRESS: "0.0.0.0"
      JAVA_TOOL_OPTIONS: "-XX:MaxRAMPercentage=55.0"
    ports:
      - "127.0.0.1:18080:8080"
    restart: unless-stopped
~~~

Chạy:

~~~bash
docker compose up --build
~~~

Host truy cập `http://localhost:18080/api/hello`. Một container khác **trong cùng Compose network** thường gọi `http://runtime:8080/api/hello` bằng **service name** và container port, không gọi host-published 18080 hoặc `localhost` của container khác.

`restart: unless-stopped` không sửa sai port hoặc leak memory; nó chỉ giúp process khởi động lại theo chính sách Docker. Compose `mem_limit`/`cpus`/`deploy.resources` có mức hỗ trợ và semantics phụ thuộc Compose/runtime, nên kiểm tra enforcement thực qua `docker inspect`/`docker stats` nếu dùng.

## 10. Kubernetes containerPort, Service.port, targetPort

Pod fragment:

~~~yaml
ports:
  - name: http
    containerPort: 8080
    protocol: TCP
~~~

Đó là metadata cho routing/probes; **không tự đặt** `server.port`. App phải listen trên Pod interface:8080 bằng cấu hình Spring tương ứng.

Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: runtime-demo
spec:
  selector:
    app: runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

- `port: 80`: port mà clients trong cluster dùng để gọi Service.
- `targetPort: http`: tra named port `http` trong Pod, ở đây 8080.
- `selector app: runtime-demo` phải khớp labels của Pod.
- `type: ClusterIP` không tự mở public Internet endpoint; muốn public có thể dùng Ingress/Gateway/LoadBalancer.
- Nếu Pod không ready hoặc selector sai, Service có thể không có endpoints hữu dụng.
- Nếu Spring listen `127.0.0.1:8080`, kube-proxy gửi tới **Pod IP**:8080 thường không gặp listener.

Dùng named `targetPort: http` hoặc numeric `targetPort: 8080` đều hợp lệ; named port giúp mô tả ý nghĩa khi số port thay đổi. `containerPort` không phải hostPort; đừng thêm `hostPort: 8080` chỉ để fix Service sai route.

## 11. Manifest Kubernetes Deployment + Service

Ví dụ phù hợp với Java demo và Dockerfile trước đó:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-demo
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: runtime-demo
  template:
    metadata:
      labels:
        app: runtime-demo
    spec:
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: runtime
          image: registry.example.test/runtime-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: PORT
              value: "8080"
            - name: SERVER_ADDRESS
              value: "0.0.0.0"
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=55.0"
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "768Mi"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 3
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: runtime-demo
spec:
  selector:
    app: runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

**Lưu ý bắt buộc trước khi deploy:** image `registry.example.test/runtime-demo:1.0.0` là tên image minh họa, không phải registry có sẵn của người học. Cần thay bằng image đã build, tag, push và có quyền pull trong cluster (hoặc load image qua công cụ cluster local). Đừng deploy trực tiếp một image không tồn tại rồi gọi `ImagePullBackOff` là lỗi Spring.

### Giải thích phần resources/probes

- `resources.requests` phục vụ scheduling, CPU shares/priority và bộ nhớ dự kiến của Pod.
- `resources.limits.cpu` dẫn tới CPU quota/throttling khi load lớn.
- `resources.limits.memory` được kernel cgroups enforcement, có thể gây OOMKill khi process dùng quá nhiều physical memory.
- `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=55.0` gợi ý max heap khoảng 55% memory base mà JVM xác định; không hard cap toàn process.
- `readOnlyRootFilesystem:true` giúp giảm khả năng ghi lên image layer, nhưng cần volume `/tmp` vì Java/HTTP frameworks có thể tạo temp files.
- `startupProbe` tạm bảo vệ ứng dụng lúc startup chậm khỏi liveness kill sớm.
- `readinessProbe` quyết định Pod có nên nhận new Service traffic.
- `livenessProbe` dùng cho process failure cần restart.
- `terminationGracePeriodSeconds:60` là **toàn bộ Pod termination budget**, gồm preStop nếu khai báo và thời gian dừng các phases; không cộng thêm cho Spring.

### Kiểm tra sau khi image đã hợp lệ

~~~bash
kubectl apply -f k8s-runtime.yaml
kubectl get pods -l app=runtime-demo
kubectl get service runtime-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=runtime-demo
kubectl rollout status deployment/runtime-demo
~~~

Trong môi trường chỉ có ClusterIP, có thể debug từ laptop:

~~~bash
kubectl port-forward service/runtime-demo 18080:80
~~~

Sau đó ở terminal khác:

~~~bash
curl -sS -i http://localhost:18080/api/hello
curl -sS http://localhost:18080/api/runtime
curl -sS -i http://localhost:18080/readyz
~~~

Khi port-forward, host dùng 18080, Service port là 80, Pod vẫn listen 8080. `kubectl port-forward` là một kết nối debug tạm, **không phải Ingress public**.

## 12. Ingress, TLS và reverse proxy

Flow thực tế có thể gồm:

~~~text
https://api.example.com:443
       |
       v
Ingress / Load Balancer, TLS termination
       |
       | Service runtime-demo:80
       v
Kubernetes Service
       |
       | targetPort http -> 8080
       v
Pod IP:8080
       |
       v
Spring Boot server.port=8080
~~~

TLS `443` ở edge không có nghĩa Java phải listen cổng 443. Trong cluster riêng có thể dùng HTTP nội bộ hoặc mTLS/end-to-end TLS theo security policy. Nếu ứng dụng sinh redirects, OAuth callback URLs hoặc `Secure` cookies, cần bảo đảm scheme/host được khôi phục đúng từ **trusted proxies**.

Spring Boot có `server.forward-headers-strategy` để điều chỉnh xử lý `Forwarded`/`X-Forwarded-*`. **Không bật tin tưởng mọi forwarded header do client bên ngoài tùy ý gửi**; kiểm soát proxy chain và chặn/ghi đè headers ở edge trước khi cho application dùng.

Không dùng `0.0.0.0` như biện pháp public Internet tự động; chỉ bind. Việc publish còn do Service type, Ingress, firewall/cloud security groups và NetworkPolicies.

## 13. CPU requests, CPU limits và throttling

Trong Kubernetes:

~~~yaml
resources:
  requests:
    cpu: "200m"
  limits:
    cpu: "1000m"
~~~

- `200m` CPU là 0,2 CPU unit được scheduler xét khi đặt Pod; nó có thể ảnh hưởng CPU shares khi node tranh chấp.
- `1000m` là 1 CPU unit limit danh nghĩa; kernel thường enforcement qua quota/throttling.
- CPU request không hard cap CPU thực tế; khi node rảnh process có thể dùng nhiều hơn request trong limit.
- CPU limit **không cho phép 8 worker threads cùng có hiệu năng 8 cores** nếu quota chỉ 1 core.
- Tăng `server.tomcat.threads.max` khi CPU đang throttled có thể làm tăng context switches, queues và latency.
- Nếu ứng dụng chủ yếu chờ DB/HTTP client, tăng CPU limit có thể không sửa bottleneck. Cần đo downstream latency/connection pools trước.

Java 17 JVM dùng `Runtime.availableProcessors()` cho nhiều heuristics (GC, ForkJoinPool, executor sizing); nó có thể phản ánh cgroup constraints tùy JDK/OS. Đừng mặc định giá trị bằng số physical cores của host.

Có thể override JVM active processor count:

~~~bash
JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=2"
~~~

Nhưng flag này **không tăng CPU quota** của container. Chỉ dùng khi benchmark cho thấy JVM heuristics cần điều chỉnh.

## 14. Memory requests/limits và JVM heap: hai ngân sách khác nhau

~~~yaml
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "768Mi"
~~~

- Memory request chủ yếu phục vụ scheduler/availability planning.
- Memory limit là cgroup budget mà kernel enforce khi cần; khi vượt có thể OOMKill process/container.
- Java `-Xmx` chỉ giới hạn **heap**; process còn metaspace, code cache, direct/Netty buffers, thread stacks, TLS/native, mapped files và overhead khác.
- `-XX:MaxRAMPercentage` điều chỉnh **max heap sizing**, không điều chỉnh tổng RSS.
- Nếu không có limit memory thích hợp, JVM container-aware có thể sizing heap dựa trên một memory base lớn; cần thiết kế đồng bộ với platform.

Một công thức budget sơ bộ:

~~~text
Container memory limit
  >= Java heap live/committed
   + Direct/native buffers
   + Metaspace and code cache
   + GC/thread stack overhead
   + TLS/HTTP I/O buffers
   + Temporary/shared/accounted memory
   + Safety margin
~~~

Không thể đo chính xác mọi hạng mục bằng một snapshot duy nhất; memory reserved/committed/RSS và cgroup accounting khác nhau.

Ví dụ thiết kế **để cân nhắc, không phải production default**:

| Khoản | Ví dụ |
|---|---:|
| Container memory limit | 768 MiB |
| JVM target max heap 55% | ~422 MiB |
| Phần còn lại theo phép trừ | ~346 MiB |
| Dùng cho | Native/direct, stacks, metaspace, TLS, GC, buffers, margin |

`422 MiB` chỉ là phép ước tính, không bảo đảm JVM chọn đúng con số đó do flags, small-heap heuristics, rounding và JDK implementation. Heap max chưa phải heap used; phần còn lại không phải guaranteed free memory. Đo process/container thực tế dưới tải.

### Java 17 container support

Trên nền tảng Linux/HotSpot được hỗ trợ, `UseContainerSupport` mặc định bật ở Java 17; JVM phát hiện CPU/memory constraints qua cgroups. Kiểm tra:

~~~bash
java -Xlog:os+container=info -version
~~~

Khi có JDK diagnostics:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

`-Xmx512m` thường override max heap size được tính từ percentage. Không đặt đồng thời `-Xmx` và `MaxRAMPercentage` khác nhau nếu không hiểu precedence. Tránh `-XX:-UseContainerSupport` vì JVM có thể sizing theo host thay vì container, tăng rủi ro OOMKilled.

### OOMKilled khác Java heap OOM

- `java.lang.OutOfMemoryError: Java heap space`: Java heap không đủ.
- `OutOfMemoryError: Cannot reserve ... direct buffer memory`: direct/native allocation pressure hoặc giới hạn liên quan.
- Pod `OOMKilled`: kernel/cgroup termination; có thể không có Java heap OOM log.
- Process RSS cao nhưng JVM heap thấp: điều tra native/direct/threads/mapped memory, không chỉ `-Xmx`.

Quan sát `docker stats`, `kubectl top pod`, JVM Micrometer `jvm.memory.used`, `jvm.gc.pause`, NIO buffer pools và Reactor Netty metrics theo stack, cùng OS/cgroup. Một snapshot cao **chưa đủ kết luận memory leak**; xem trends, active requests và GC.

## 15. Threads, file descriptors và network connections

Container còn bị giới hạn bởi:
- OS file descriptors/socket limits.
- Number of threads và per-thread stack memory.
- Tomcat accept queue/worker pool; Reactor Netty event loops.
- Network receive/send buffers.
- Lượng connections keep-alive, SSE, WebSocket.
- Multipart temporary disk, heap/direct/serialization buffers.

Một JVM có 10.000 connections idle có thể dùng nhiều sockets/buffers nhưng ít HTTP active requests; không đồng nhất requests/sec với connections. Với streaming lớn, kết hợp backpressure/slow-client policies, giới hạn outbound queue và temporary files.

Kiểm tra FD limit trong Linux shell nếu có:

~~~bash
ulimit -n
~~~

Ví dụ Docker runtime cho FD limit khi host policy cho phép:

~~~bash
docker run --ulimit nofile=65535:65535 \
  -p 127.0.0.1:18080:8080 runtime-demo:1.0
~~~

65535 chỉ là **ví dụ**; tăng FD limits không sửa connection leak hoặc thiếu memory. Nếu container tối giản không có shell/`ulimit`, dùng host metrics/debug container theo quyền được cấp.

### CPU limit và HTTP threading model

| Stack | Cấu trúc thường gặp | Lỗi hay gặp |
|---|---|---|
| Spring MVC/Tomcat | Blocking servlet worker threads | Tăng max threads nhưng DB pool/CPU vẫn nghẽn |
| Spring WebFlux/Reactor Netty | Event-loop non-blocking I/O | Gọi `block()`/`Thread.sleep()` trên event loop |
| Async executor | Worker pool + queue | Queue không giới hạn, shutdown không drain |
| SSE/WebSocket | Connections lâu | Buffer per client và reconnect storm |

Trước khi chỉnh worker counts cần đo CPU throttling, p95/p99 latency, JVM GC, DB pool waits, HTTP active/queue và actual memory.

## 16. Writable /tmp, ephemeral storage và non-root

Kubernetes manifest dùng:

~~~yaml
securityContext:
  readOnlyRootFilesystem: true

volumeMounts:
  - name: tmp
    mountPath: /tmp

volumes:
  - name: tmp
    emptyDir:
      sizeLimit: 128Mi
~~~

Điều này cần vì Java/Servlet libraries có thể ghi temp files (multipart, TLS/native scratch, `java.io.tmpdir`). Nếu root filesystem read-only mà app không có writable temp directory, có thể nhận lỗi `Read-only file system` hoặc upload failure.

**Không coi `emptyDir` là durable storage.** Khi Pod bị xóa, dữ liệu volume này mất; cần object storage/PVC cho files cần bền. Nếu dùng `emptyDir.medium: Memory`, tmpfs có thể tính vào memory cgroup và làm OOM sớm; disk-backed emptyDir có áp lực ephemeral storage riêng. Với uploads lớn, đặt quotas, giới hạn multipart, theo dõi ephemeral storage usage và cleanup.

Chạy UID/GID không root:

~~~dockerfile
USER 10001:10001
~~~

và:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
~~~

Cần cho mount permissions phù hợp, không tự động nâng container lên root chỉ để ghi file. Cổng HTTP bên trong chọn 8080/9090 thay vì cố bind low port 80/443 nếu không cần; ingress có thể expose 80/443 ở ngoài.

## 17. Health probes: readiness, liveness, startup

Spring Boot Actuator 3.5 có Kubernetes probe support:
- `/actuator/health/liveness`.
- `/actuator/health/readiness`.
- Với `management.endpoint.health.probes.add-additional-paths=true` có `/livez` và `/readyz` trên **main HTTP server port**.

Trong demo:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Khi `management.server.port` tách riêng, dùng `/livez`/`/readyz` trên main server vẫn giúp kiểm tra chính connector đang nhận business traffic; management context khỏe không nhất thiết nghĩa main connector khỏe.

| Probe | Mục đích | Nếu fail |
|---|---|---|
| Startup | Khởi động đã đủ tiến triển để bắt đầu liveness/readiness checks | Tạm chờ, sau failure budget có thể restart |
| Readiness | Có nên route requests mới tới Pod không | Loại Pod khỏi ready endpoints |
| Liveness | Process có bị treo cần restart không | Restart container theo thresholds |

**Không gắn database/Redis/partner outage thành liveness fail** trừ khi thật sự chỉ restart app mới sửa được; nếu tất cả replicas restart khi dependency tạm outage sẽ gây cascading failure. Readiness có thể gồm checks phản ánh khả năng nhận workload, nhưng phải được thiết kế để tránh flapping/cost.

Probes cần trỏ **Pod/container port** (8080 hoặc named `http`), không trỏ mặc định Service.port 80 khi kubelet gọi Pod IP. Test path thực sự tồn tại; Actuator starter phải được thêm và nhóm probes phải enabled theo môi trường.

### Management port riêng

Có thể cấu hình:

~~~yaml
management:
  server:
    port: 9090
    address: "127.0.0.1"
~~~

Theo Spring Boot, `management.server.address` khác main listener chỉ cấu hình được khi management port khác. Với địa chỉ loopback trong container, external scraper/Pod network probe tới 9090 thường **không tới được**. Để scrape từ nơi khác, phải thiết kế network/access phù hợp, không chỉ mở port trong YAML. Bảo vệ metrics bằng auth/mTLS/NetworkPolicy/firewall; không expose `/actuator/env`, `heapdump` hoặc toàn bộ Actuator công khai.

## 18. Graceful shutdown và signal handling

Spring Boot 3.5 mặc định dùng HTTP graceful shutdown với embedded servers được hỗ trợ; config rõ trong demo:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

`timeout-per-shutdown-phase` là thời gian chờ **mỗi SmartLifecycle phase**, không phải tổng JVM process deadline. Kubernetes:

~~~yaml
terminationGracePeriodSeconds: 60
~~~

là **ngân sách tổng cho Pod termination**, bao gồm preStop và thời gian chờ Spring/other cleanup. Nếu preStop 15s + nhiều phases tổng 60s, Pod có thể bị forced kill trước khi Java hoàn tất. Phải đo shutdown timeline, request durations và resource drain.

Dockerfile dùng exec-form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

để JVM nhận SIGTERM khi container stop. Shell form `ENTRYPOINT java -jar /app/app.jar` có thể khiến shell PID1 không forward signal; khi đó Java không chạy graceful hook đúng. Nếu cần script launcher, dùng `exec java -jar ...`.

SSE/WebSocket hoặc streaming lâu hơn grace period **không tự chuyển kết nối sang Pod khác**. Cần readiness false/draining, chủ động close, client reconnect/backoff và cursor/replay. Với POST có side effect, dùng idempotency key/operation status vì client mất response không chứng minh server chưa commit.

## 19. Logs và metrics trong container

Ưu tiên logs lên **stdout/stderr** để Docker/Kubernetes collecting/rotation. Không ghi log file không giới hạn trong container overlay writable layer. Với logs lâu dài dùng centralized logging, retention và privacy controls.

Các chỉ số cần theo dõi:

| Nhóm | Metric/signal |
|---|---|
| Cổng/HTTP | Startup port logs, ready endpoints, ingress 502/503, RPS và latency |
| JVM | `jvm.memory.used`, max heap, GC pauses, direct buffer metrics |
| Container | Memory working set/RSS/cgroup usage, CPU usage, CPU throttled time |
| Threads | Tomcat busy/current, executor active/queued, event loop lag |
| Connections | Active HTTP requests, TCP sockets, SSE/WebSocket sessions |
| Storage | Ephemeral bytes/inodes, temp file usage, volume quotas |
| Deploy | Readiness, liveness, restartCount, lastState.terminated.reason |
| Security | Bind addresses, NodePort/Ingress exposure, secrets, denied requests |

Không đưa raw JWT, cookies, usernames, IP addresses cá nhân hoặc request IDs vào high-cardinality Prometheus tags. `/api/runtime` trong demo chỉ trả thông tin kỹ thuật tối thiểu; production nên bảo vệ hoặc loại bỏ nếu không cần.

## 20. Integration test ngẫu nhiên hóa cổng

Tạo `src/test/java/demo/runtime/ContainerRuntimeApplicationTests.java`:

~~~java
package demo.runtime;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ContainerRuntimeApplicationTests {

    @LocalServerPort
    int port;

    @Test
    void runtimeReportsRealPort() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/api/runtime"))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"listenPort\":" + port));
        assertTrue(response.body().contains(
            "\"message\":\"running\""));
    }

    @Test
    void helloReturnsExpectedBody() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/api/hello"))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"message\":\"hello\""));
    }
}
~~~

Tests dùng Java 17 HTTP client + JUnit 5 từ starter test. `@LocalServerPort` cho phép so sánh cổng server thực tế khi Boot test chọn ephemeral port. Không assert CPU/heap cụ thể vì phụ thuộc runtime. Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Đây là code hướng dẫn để người học thực thi; **không tuyên bố tests đã PASS** nếu chưa chạy. Mock/server test trên host không thay cho test Docker port mapping/Service networking khi deploy.

## 21. Các bước chẩn đoán nhanh khi không truy cập được

1. **Client URL:** host/scheme/port đúng chưa?
2. **Host publish:** Docker có `-p`, Compose ports hoặc Ingress/LB đúng chưa?
3. **Service:** selector, port, targetPort đúng Pod listener chưa?
4. **Ready endpoints:** Pod có ready không, EndpointSlices có địa chỉ không?
5. **Container listener:** Spring actual `server.port` và `server.address` là gì?
6. **Security/firewall:** NetworkPolicy, security group, ingress whitelist và TLS có chặn?
7. **Application:** controller có mapping thật? 404 khác connection refused.
8. **Resources:** OOMKilled, CPU throttling, file descriptor limit và startup probe flapping?
9. **Shutdown:** container đang terminate và ngừng nhận new traffic?
10. **Logs/metrics:** đối chiếu tại cùng timestamp giữa host, proxy, Pod, JVM.

### Lệnh Docker

~~~bash
docker ps
docker port runtime-demo
docker logs --tail 100 runtime-demo
docker stats runtime-demo
docker inspect runtime-demo
~~~

`docker inspect` có thể chứa env/secrets; không chia sẻ raw output công khai.

### Lệnh Kubernetes

~~~bash
kubectl get pods -l app=runtime-demo -o wide
kubectl describe deployment runtime-demo
kubectl describe service runtime-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=runtime-demo
kubectl logs deployment/runtime-demo --tail=100
kubectl top pod -l app=runtime-demo
kubectl rollout status deployment/runtime-demo
~~~

`kubectl top` cần metrics-server; `kubectl get endpointslices` cần RBAC quyền đọc tương ứng. Nếu Pod restart, lấy **tên Pod thật** từ `kubectl get pods` rồi chạy `kubectl logs POD_NAME --previous`. Một image runtime nhỏ có thể không có `curl`, `ss`, `netstat`; debug qua port-forward, host curl, proxy metrics hoặc ephemeral debug container được phép.

### Phân biệt lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Điều cần xác minh |
|---|---|---|
| Connection refused từ Docker host | Thiếu publish/sai target/bind localhost | `docker port` + Spring bind |
| Timeout qua Service | NetworkPolicy/LB/Service targetPort | Endpoints, probe, network path |
| HTTP 404 | Đã vào HTTP server nhưng route không match | Context path/controller mappings |
| HTTP 502 | Proxy không giao tiếp upstream | Gateway/proxy logs, Pod readiness |
| HTTP 503 | Pod draining/unavailable hoặc server response | Ingress/status nguồn |
| Pod `ImagePullBackOff` | Image registry/tag/credentials sai | `kubectl describe pod` |
| Pod `CrashLoopBackOff` | App startup error/bind/OOM/probes | Previous logs và Events |
| Pod `OOMKilled` | Cgroup RAM vượt limit | RSS/heap/native metrics |
| CPU cao, latency tăng | Saturation/throttling/blocking | CPU quota, GC, traces, queues |
| Process started nhưng probe fail | Probe path/port/management context sai | `/livez`/`/readyz` trên main port |
| Upload lỗi read-only FS | Không có writable temp dir | Mount `/tmp`/permissions/quota |
| Stop không graceful | Signal không tới JVM PID1 | Docker ENTRYPOINT, stop deadline |

**Không tăng `-Xmx` hoặc `server.tomcat.threads.max` như phản xạ** khi thực tế là sai port/probe/Service routing.

## 22. Bảo mật mạng, container và config

- Chỉ publish ports cần thiết; Docker host `-p 127.0.0.1:18080:8080` phù hợp local demo hơn `-p 18080:8080` khi không cần truy cập từ LAN.
- Dùng `USER 10001:10001`/`runAsNonRoot` và read-only root filesystem nếu app tương thích; cung cấp writable mounts có quota.
- Tách management endpoints khỏi public API hoặc bảo vệ bằng authentication/authorization, network policies, TLS/mTLS; không dùng `management.endpoints.web.exposure.include="*"`.
- Khi TLS terminate ở proxy, chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy tin cậy, tránh spoofing host/scheme.
- Không đóng gói secrets trong Docker image layers hoặc commit vào `application.yml`. Dùng Secrets manager/Kubernetes Secrets với RBAC/encryption/rotation phù hợp.
- Không log toàn bộ `System.getenv()` hay expose `/actuator/env`/heapdump trên Internet.
- Giới hạn HTTP body, concurrent requests, slow-client timeouts và outbound queues để tránh memory/FD exhaustion.
- Không gắn Pod IP cố định vào `server.address` vì Pods sẽ được thay thế.
- Thử readiness/termination khi rolling deploy, không để Pod unready kéo dài chỉ vì startup probe quá chặt.

### Các nguồn cấu hình nên dùng theo môi trường

| Môi trường | Spring bind | Client port | Security/resource focus |
|---|---|---|---|
| Local jar | 8080/9090, theo nhu cầu | Same bound port | Đừng hardcode env secrets |
| Docker local | 0.0.0.0:8080 | Host 127.0.0.1:18080 | Non-root, Docker memory/CPU |
| Compose | 0.0.0.0:8080 | Host ports hoặc service DNS:8080 | Service network, environment |
| Kubernetes | 0.0.0.0:8080 | Service 80 → Pod 8080 | Requests/limits/probes/securityContext |
| Ingress HTTPS | 0.0.0.0:8080 | Public 443 → Service 80 | TLS/proxy trusted headers |
| PaaS có PORT | `${PORT:8080}` | Platform URL | Platform quota và JVM heap |

## 23. Câu hỏi tự kiểm tra

**1.** `server.port=8080` và `docker run -p 18080:8080` thì host gọi port nào?

**Đáp án:** Host **18080**; Spring trong container vẫn **8080**.

**2.** Dockerfile có `EXPOSE 8080` mà không dùng `-p`, host có tự truy cập cổng 8080 không?

**Đáp án:** Không. EXPOSE là metadata, không publish host port.

**3.** Vì sao `server.address=127.0.0.1` có thể khiến Docker/K8s Service không kết nối được?

**Đáp án:** App chỉ bind loopback trong network namespace; routing ngoài thường nhắm container/Pod IP, không tới loopback socket.

**4.** `0.0.0.0` có tự public app ra Internet không?

**Đáp án:** Không. Nó là wildcard bind trong namespace; việc public do Docker publish, Ingress/LB/firewall/network policy quyết định.

**5.** `containerPort: 8080` có tự đặt server.port cho Boot không?

**Đáp án:** Không. Đó là mô tả Pod, không khởi động Java listener.

**6.** Service `port:80,targetPort:8080` nghĩa JVM phải listen port 80?

**Đáp án:** Không. JVM listen 8080; Service nhận 80 và route vào Pod 8080.

**7.** Vì sao hai Pods đều listen 8080 được, nhưng hai containers cùng Pod có thể xung đột?

**Đáp án:** Hai Pods thường có network namespaces khác nhau; containers cùng Pod chia sẻ namespace.

**8.** Biến `PORT=9090` có luôn tự thay đổi Spring Boot port không?

**Đáp án:** Không, trừ khi config map nó bằng `server.port: ${PORT:8080}` hoặc platform có integration. Boot trực tiếp hiểu `SERVER_PORT`.

**9.** `server.port=0` có phù hợp manifest Kubernetes targetPort 8080 cố định không?

**Đáp án:** Không, trừ khi có dynamic discovery/route đặc biệt; port ephemeral có thể khác 8080.

**10.** Container memory limit 768Mi có bảo đảm đặt `-Xmx768m` là an toàn không?

**Đáp án:** Không. JVM còn native/direct/metaspace/thread stacks và cgroup overhead ngoài heap.

**11.** `MaxRAMPercentage=55` nghĩa process không vượt quá 55% RAM?

**Đáp án:** Không. Nó là phần trăm dùng để sizing max Java heap; RSS/process native memory vẫn có thể vượt.

**12.** `ActiveProcessorCount=8` có cấp tám CPU cho container CPU limit một core không?

**Đáp án:** Không. JVM heuristics thay đổi nhưng kernel quota không đổi, có thể dẫn đến throttling.

**13.** CPU limit bị vượt và memory limit bị vượt có cùng kết quả?

**Đáp án:** Không. CPU thường bị throttling; memory pressure có thể OOMKill.

**14.** Vì sao liveness không nên phụ thuộc hoàn toàn vào database status?

**Đáp án:** External DB outage có thể làm tất cả Pods restart liên tục, tạo cascading failure.

**15.** Tại sao đặt /readyz ở main port khi management chạy port riêng?

**Đáp án:** Để probe kiểm tra chính HTTP connector phục vụ business traffic.

**16.** `terminationGracePeriodSeconds=60` có cho từng Spring lifecycle phase 60 giây riêng không?

**Đáp án:** Không. Đây là tổng termination budget của Kubernetes, gồm preStop và app cleanup.

**17.** Docker ENTRYPOINT exec-form giúp gì?

**Đáp án:** Giúp Java nhận stop signal trực tiếp và chạy shutdown hook/graceful process khi đủ budget.

**18.** Java non-root/read-only filesystem upload bị lỗi ghi /tmp thì xử lý gì?

**Đáp án:** Cấp writable temp volume/directory với permissions/quota thích hợp; không cần chạy root.

**19.** Spring JVM heap metric thấp nhưng container OOMKilled thì nên điều tra gì?

**Đáp án:** Native/direct memory, thread stacks, RSS, cgroup temp/cache, concurrency và JVM flags.

**20.** Service không kết nối được, trước khi tăng Tomcat threads phải làm gì?

**Đáp án:** Kiểm tra port/address bind, Service selector/targetPort, Pod readiness, network policies và proxy route.

### Bài tập mở rộng

1. Chạy jar với 8080 rồi 9090, xem `/api/runtime` báo actual listenPort.
2. Build image Docker, publish 18080:8080, chứng minh host port khác container port.
3. Đổi PORT=9090 nhưng cố tình giữ Docker mapping tới 8080, ghi nhận lỗi và sửa.
4. Bind 127.0.0.1 trong container rồi thử host publish, giải thích network namespace.
5. Dùng `--memory=768m`/`--cpus=1` và `MaxRAMPercentage=55`, so sánh JVM maxHeap với `docker stats` dưới tải nhỏ.
6. Dùng Compose, từ container khác gọi `http://runtime:8080` thay vì `localhost:18080`.
7. Deploy image test vào Kubernetes; dùng `kubectl port-forward service/runtime-demo 18080:80` và kiểm tra /readyz.
8. Cố ý cấu hình sai `targetPort` ở test cluster rồi chẩn đoán EndpointSlices và logs.
9. Thử CPU throttling trong test rồi đánh giá latency, queue, GC; không tấn công production.
10. Bật readOnlyRootFilesystem với writable /tmp, quan sát file temp và quota.
11. Khi rolling deployment, đo readiness transition, SIGTERM, HTTP graceful, Pod termination budget.
12. Viết test random port dùng `@LocalServerPort`, không assert cứng 8080.

## 24. Tài liệu chính thức

- [Spring Boot 3.5 — Embedded Web Servers / Change HTTP Port](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Docker Docs — Running Containers and Publishing Ports](https://docs.docker.com/engine/containers/run/)
- [Docker Docs — Dockerfile Reference: EXPOSE/ENTRYPOINT](https://docs.docker.com/reference/dockerfile/)
- [Docker Docs — Compose Services](https://docs.docker.com/compose/compose-file/05-services/)
- [Kubernetes — Service port and targetPort](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes — Resource Management for Pods/Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes — Startup, Liveness, Readiness Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [Oracle Java 17 — java launcher and Container Support](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)

**Kết luận:** Spring Boot quyết định **cổng và interface listener bên trong JVM**; Docker/Kubernetes quyết định **đường route từ ngoài vào listener**. `EXPOSE` và `containerPort` không làm app listen, còn `-p` và `Service.targetPort` phải trỏ đúng. CPU/memory limits không chỉ là JVM heap, readiness phải kiểm tra đúng main port, và container cần non-root permissions, writable temp paths, logs/metrics cùng graceful signal handling. Khi gặp lỗi deploy, kiểm tra **bind → network namespace → publish/Service → readiness → resources → handler**, thay vì thay đổi tất cả cấu hình cùng lúc.
