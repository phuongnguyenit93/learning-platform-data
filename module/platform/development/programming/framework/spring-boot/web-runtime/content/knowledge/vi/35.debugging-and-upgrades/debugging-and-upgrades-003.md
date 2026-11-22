# Ứng dụng chạy nhưng không truy cập được do port, address hoặc proxy trong Spring Boot

## 1. Tình huống và mục tiêu

Spring Boot có thể ghi `Started Application` vào console mà trình duyệt vẫn trả `ERR_CONNECTION_REFUSED`, `timeout`, HTTP 404, 502, 504 hoặc chuyển hướng sai. Một thông báo **“ứng dụng đã chạy” không chứng minh mọi khách hàng truy cập được**. Chỉ có thể kết luận đúng sau khi xác định request bị dừng ở lớp nào:

~~~text
Client (browser, curl, mobile app)
  |
  v
DNS + IP routing + scheme + port
  |
  v
Firewall / CDN / HTTPS load balancer / reverse proxy
  |
  v
Docker host port mapping / Kubernetes Service
  |
  v
Spring Boot HTTP listening socket
  |
  v
Servlet / WebFlux router + context path
  |
  v
Spring Security / Controller / Response
~~~

**Ba câu hỏi cốt lõi**:
1. Java có thực sự mở **HTTP socket** ở IP:port mà ta đang gọi không?
2. Mọi lớp NAT/Service/reverse proxy có chuyển request tới **đúng IP:port** không?
3. Nếu request đã đến HTTP server, có đúng **Host, scheme, URL path, context, security** không?

Sau bài học, cần phân biệt bind address với client destination, port của app với host/Service port; tìm override cấu hình; kiểm tra Docker/Kubernetes/NGINX; hiểu forwarded headers, TLS/redirect loop; và dùng lệnh/test có thể tái hiện để xác nhận vấn đề đã được giải quyết.

**Phạm vi ví dụ:** Java 17+, Spring Boot 3.3.x, Spring MVC trên embedded Tomcat. Những nguyên tắc kết nối cũng dùng cho Jetty/Undertow/Reactor Netty, nhưng property/ngữ nghĩa riêng phải kiểm theo embedded server thực. Không dùng một cấu hình proxy chưa được xác nhận để mở public endpoints trên production.

## 2. Triệu chứng gợi ý vị trí lỗi

| Kết quả từ client | Bản chất có thể có | Bước kiểm tra tiếp |
| --- | --- | --- |
| `Connection refused` | Không có listener tại IP:port, hoặc chủ thể mạng chủ động reject | Process, bind address, container port mapping |
| `Connection timed out` | Firewall/routing drop, LB/upstream không trả lời kịp | Đường đi IP, security group, listener, timeout |
| `Empty reply`/`EOF`/`reset` | Kết nối bị đóng giữa chừng, protocol mismatch, shutdown | HTTP/TLS, process logs, proxy errors |
| `HTTP 404` | Đã có HTTP server trả lời; mapping/context/rewrite/backend có thể sai | So direct route với proxy route |
| `HTTP 401/403` | Authentication, authorization, CORS preflight hoặc gateway/WAF chặn | Security config, response headers |
| `HTTP 301/302 liên tiếp` | Scheme/Host/forwarded prefix/redirect policy lệch | Xem từng header Location |
| `HTTP 502` | Gateway không kết nối hoặc không hiểu phản hồi upstream | proxy_pass IP/port/protocol, ingress error log |
| `HTTP 503` | App/gateway unavailable, backend chưa Ready, shutdown | Endpoints, readiness, node health |
| `HTTP 504` | Gateway chờ upstream quá lâu | Upstream latency, proxy timeout, DB |
| `Browser CORS error, curl 200` | Browser chặn cross-origin HTTP response | Allowed origins, OPTIONS, Security |
| `Certificate invalid` | TLS SNI/cert/chain/hostname | Test TLS ở proxy và client |
| `Actuator health UP, controller lỗi` | Management port/context khác hoặc API path/auth khác | Main application port |

**Ranh giới:** HTTP 404/401/403 đã có HTTP communication, không phải lỗi không thể thiết lập TCP. HTTP 502/504 có thể do gateway sinh ra **trước khi request vào Spring**, nên không nhất thiết có access log ở app.

## 3. “Process running”, “listener exists” và “reachable” khác nhau

Bốn mốc:

~~~text
JVM running
   -> WebApplicationContext initialized?
   -> HTTP server has bound IP:port?
   -> Is that IP:port reachable through actual network path?
   -> Did the requested route answer correctly?
~~~

Một process chỉ chạy batch job vẫn có thể in `Started ...`. Một Servlet app với `server.port=-1` có context nhưng **không có HTTP endpoints**. Một process lắng nghe `127.0.0.1:8080` phục vụ localhost nhưng không lắng nghe trên private IP của máy.

Bởi vậy, không chỉ dựa vào dòng `Started` mà cần tìm dòng HTTP server startup (ví dụ Tomcat started on port), sau đó xác minh **socket thực** và request qua từng hop.

### Cổng 8080 mặc định và các ngoại lệ

~~~properties
server.port=8080
~~~

là ví dụ cổng embedded Spring Boot thường gặp. Nhưng:
- `server.port=9090` đổi cổng.
- `server.port=0` để hệ điều hành cấp một port trống **ngẫu nhiên**.
- `server.port=-1` tắt HTTP endpoints nhưng vẫn có WebApplicationContext.
- `spring.main.web-application-type=none` không khởi động HTTP web server.
- `management.server.port=9091` có thể khởi động Actuator management listener riêng, khác app port.
- Khi deploy WAR vào **external Tomcat**, container ngoài quyết định connector port, không phải `server.port` trong WAR.

**Ví dụ:** nếu bật `server.port=0` mà log báo port 51627 (chỉ minh họa), gọi `localhost:8080` không chứng minh app hỏng. Phải gọi port thực 51627 hoặc dùng `@LocalServerPort` trong test.

## 4. server.address: interface mà embedded HTTP server bind

Spring Boot hỗ trợ:

~~~properties
server.address=127.0.0.1
~~~

hoặc:

~~~properties
server.address=0.0.0.0
~~~

| Bind address | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| Không cấu hình | Server/OS chọn binding theo runtime, thường all interfaces | Cần đo socket thực, không đoán |
| `127.0.0.1` | IPv4 loopback của **network namespace chứa JVM** | Remote peers không tới qua machine/container IP |
| `0.0.0.0` | Tất cả IPv4 interfaces trong namespace ấy | Có thể nhận từ private/public interfaces nếu network cho phép |
| `192.168.1.10` | Chỉ interface cụ thể đã được gán | IP đổi hoặc không tồn tại có thể bind fail |
| `::1` | IPv6 loopback | Không tương đương IPv4 127.0.0.1 |
| `::` | IPv6 wildcard (IPv4 mapping phụ thuộc OS) | Cần test dual-stack rõ |

Ví dụ app đang bind loopback:

~~~properties
server.port=8080
server.address=127.0.0.1
~~~

Trên **cùng host**:

~~~bash
curl -i http://127.0.0.1:8080/ping
~~~

có thể thành công. Nhưng máy khác gọi `http://192.168.1.10:8080/ping` có thể nhận refused vì Tomcat **không lắng nghe 192.168.1.10**.

Khi cần cho app nhận từ network interfaces (ví dụ container/Pod):

~~~properties
server.port=8080
server.address=0.0.0.0
~~~

**Đây không phải lời khuyên mở service cho cả Internet.** Bind là hành vi ở process, còn exposed network phải được kiểm soát bằng firewall/security group, load balancer, Docker publish IP, Kubernetes Service/NetworkPolicy, TLS và auth. Không tắt firewall để giải quyết vấn đề bind.

### Localhost có nhiều nghĩa

- `localhost` ở laptop → laptop.
- `localhost` bên trong Docker container → **chính container đó**.
- `localhost` bên trong Kubernetes Pod → network namespace chung của Pod; không phải node/Service.
- `localhost` bên trong NGINX container → NGINX container, không phải Spring container ở dịch vụ khác.
- `localhost` trong CI runner → runner (nếu không share network namespace).

Khi dùng proxy container để gọi app container, thường phải dùng Docker Compose service name `web:8080` hoặc Kubernetes Service DNS, không phải localhost.

## 5. IPv4, IPv6 và DNS: tên đúng nhưng địa chỉ kết nối sai

`localhost` có thể resolve thành cả `127.0.0.1` và `::1`. Nếu Java chỉ bind IPv4 mà client thử IPv6 trước, kết quả tùy DNS/client fallback.

So sánh:

~~~bash
curl -4 -v http://localhost:8080/ping
curl -6 -v http://localhost:8080/ping
curl -v http://127.0.0.1:8080/ping
curl -g -v "http://[::1]:8080/ping"
~~~

Với public domain có cả DNS A và AAAA nhưng chỉ triển khai IPv4, một nhóm clients có thể thất bại khi cố IPv6. Xem `A`/`AAAA`, listening sockets, load balancer dual-stack và firewall IPv6. `0.0.0.0` là IPv4 wildcard; không nên tuyên bố đó là IPv6 wildcard.

### Bắt đúng Host/SNI khi DNS chưa cập nhật

Ví dụ kiểm thử HTTP Host với IP tài liệu:

~~~bash
curl -v --resolve demo.example.test:80:192.0.2.10 \
  http://demo.example.test/ping
~~~

`192.0.2.10` là IP ví dụ, phải thay IP thật của ingress; không phải IP public của lab. `--resolve` gắn hostname+port với địa chỉ được chọn, nhưng HTTP Host vẫn là `demo.example.test`.

Với HTTPS, dùng:

~~~bash
curl -v --resolve demo.example.test:443:192.0.2.10 \
  https://demo.example.test/ping
~~~

Cách này phù hợp để test TLS SNI/hostname verification. Đừng dùng `-k` như cách sửa cert errors: nó vô hiệu hóa kiểm tra danh tính server.

## 6. Build một project Spring Boot Java 17+ để tái hiện lỗi

Ta cần một endpoint đơn giản không phụ thuộc DB và một endpoint hiển thị request metadata để so sánh direct/proxy.

### 6.1. Cấu trúc

~~~text
network-access-lab/
├── settings.gradle
├── build.gradle
├── Dockerfile
└── src/
    ├── main/
    │   ├── java/demo/network/
    │   │   ├── NetworkLabApplication.java
    │   │   └── DiagnosticController.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/network/NetworkLabHttpTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'network-access-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'network-access-lab.jar'
}
~~~

Starter Web dựng **Tomcat embedded** cho Spring MVC; Actuator hỗ trợ health. Đổi embedded server/Java phiên bản phải giữ dependency compatibility.

### 6.2. Main class

`src/main/java/demo/network/NetworkLabApplication.java`:

~~~java
package demo.network;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NetworkLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NetworkLabApplication.class, args);
    }
}
~~~

### 6.3. Controller để chẩn đoán request

`src/main/java/demo/network/DiagnosticController.java`:

~~~java
package demo.network;

import java.net.URI;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class DiagnosticController {

    @GetMapping(value = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping("/where")
    public Map<String, Object> where(HttpServletRequest request) {
        return Map.of(
                "scheme", request.getScheme(),
                "host", request.getServerName(),
                "port", request.getServerPort(),
                "contextPath", request.getContextPath(),
                "requestUri", request.getRequestURI(),
                "remoteAddress", request.getRemoteAddr()
        );
    }

    @GetMapping("/jump")
    public ResponseEntity<Void> jump() {
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/ping")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(location)
                .build();
    }
}
~~~

- `GET /ping` trả body **`pong`** để kiểm tra route.
- `GET /where` trả host/scheme/port/context/remote address theo servlet request mà app thấy. Proxy có thể thay đổi những giá trị này.
- `GET /jump` trả HTTP 302 với `Location` do Spring MVC tạo từ current request context, giúp thấy lỗi forwarded scheme/host/port hoặc prefix.
- Dữ liệu `remoteAddress` chỉ để học. **Không public /where trong production**: nó có thể lộ cấu trúc network và IP của clients; dùng protected diagnostics/logs.

### 6.4. application.properties

~~~properties
spring.application.name=network-access-lab

server.port=8080
server.address=0.0.0.0
server.forward-headers-strategy=none

management.endpoint.health.probes.enabled=true
~~~

Ban đầu `none` giúp quan sát cách servlet server nhìn request trực tiếp. Khi đã đặt app sau proxy **được tin cậy**, thử `framework` ở mục 13 để xem redirect external URL.

### 6.5. Chạy

Linux/macOS:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/network-access-lab.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\network-access-lab.jar
~~~

Nếu chưa có Gradle wrapper, dùng Gradle phiên bản tương thích để tạo wrapper hoặc chạy `gradle clean test bootJar`.

Trên terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/ping
curl -i http://127.0.0.1:8080/where
curl -i http://127.0.0.1:8080/jump
~~~

Với cURL IPv4 direct, dự kiến:

~~~text
GET /ping -> HTTP 200, body: pong
GET /where -> HTTP 200, JSON có scheme=http, port=8080, requestUri=/where
GET /jump -> HTTP 302, Location: http://127.0.0.1:8080/ping
~~~

Đây là **kết quả logic**, không cam kết header order/timezone, JSON field order hay IP khi chạy trong container/proxy. Nếu `/where` cho host khác hoặc redirect Location sai, xem request Host/header config.

## 7. HTTP integration tests: dùng cổng thực, không hard-code 8080

`src/test/java/demo/network/NetworkLabHttpTest.java`:

~~~java
package demo.network;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class NetworkLabHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    @Test
    void pingWorksOverHttp() {
        ResponseEntity<String> r =
                http.getForEntity("/ping", String.class);

        assertThat(port).isBetween(1, 65535);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo("pong");
    }

    @Test
    void whereShowsRequestPath() {
        ResponseEntity<String> r =
                http.getForEntity("/where", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).contains("/where");
        assertThat(r.getBody()).contains("requestUri");
    }

    @Test
    void unknownPathIs404() {
        ResponseEntity<String> r =
                http.getForEntity("/no-such-route", String.class);

        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.network.NetworkLabHttpTest
~~~

Test mở HTTP server trên random port và kiểm tra route thực; **không chứng minh Docker host, Kubernetes Service, ingress hoặc DNS public đã đúng**. Nó xác nhận app layer ở môi trường test.

### Port 0 và -1

~~~bash
java -jar build/libs/network-access-lab.jar --server.port=0
~~~

Sẽ chọn port ngẫu nhiên. Xem startup logs hoặc dùng `WebServerInitializedEvent` để đọc port thực. Trong JUnit `@LocalServerPort` là cách thuận tiện; không inject `local.server.port` vào bean initialization quá sớm.

~~~bash
java -jar build/libs/network-access-lab.jar --server.port=-1
~~~

Không có HTTP endpoint để cURL, dù Spring context vẫn khởi tạo theo Boot behavior. Nếu trước đó bạn thấy Actuator port riêng hoặc một app khác trả lời, đừng nhầm nó với listener chính đang bị tắt.

## 8. Config precedence: sao file ghi 8080 nhưng log báo 9090?

Spring Boot nhận config từ nhiều nguồn:
- `application.properties` đóng trong JAR;
- external `application.properties` và `config/`;
- `application-prod.properties` khi profile `prod` đang active;
- OS environment `SERVER_PORT`/`SERVER_ADDRESS`;
- Java system properties `-Dserver.port=...`;
- command-line args `--server.port=...`;
- test-specific properties hoặc config imports.

Ví dụ:

~~~properties
server.port=8080
~~~

Nhưng khi chạy:

~~~bash
SERVER_PORT=9090 java -jar build/libs/network-access-lab.jar
~~~

port là **9090** theo default precedence. Nếu thêm:

~~~bash
SERVER_PORT=9090 java -jar build/libs/network-access-lab.jar \
  --server.port=7070
~~~

command-line argument `7070` thường ưu tiên hơn env `9090`. Java system property đặt **trước** `-jar`:

~~~bash
java -Dserver.port=9090 -jar build/libs/network-access-lab.jar
~~~

Còn Spring args đặt **sau** JAR:

~~~bash
java -jar build/libs/network-access-lab.jar --server.port=9090
~~~

### Cách tìm nguồn override

1. Đọc startup logs từ **đúng PID/timestamp**, không phải console lịch sử.
2. Kiểm tra command-line args, JVM `-D` và launcher scripts.
3. Đọc env vars `SERVER_PORT`, `SERVER_ADDRESS`, `SPRING_PROFILES_ACTIVE`.
4. Kiểm tra profile-specific và external configs theo working directory.
5. Trong Docker: image default, docker run `-e`, Compose environment.
6. Trong Kubernetes: Deployment env, ConfigMap/Secret, JVM opts.
7. Nếu policy cho phép, kiểm tra Actuator `env`/`configprops` trong network bảo vệ; không expose public vì có thể chứa cấu hình nhạy cảm.
8. Kiểm tra app thật là embedded JAR hay WAR trong external Tomcat.

Đừng kết luận config “đúng” chỉ vì file source nói vậy. **Hiệu lực runtime** mới là thứ quyết định socket thực.

## 9. Lệnh chẩn đoán listening sockets

### Linux/macOS

~~~bash
ss -lntp | grep ':8080'
~~~

Hoặc nếu có lsof:

~~~bash
sudo lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Ví dụ output:

~~~text
LISTEN 0 100 127.0.0.1:8080 0.0.0.0:* users:(("java",pid=12345,fd=42))
~~~

**Đọc cột local address**, không nhầm `0.0.0.0:*` ở cột peer address. Dòng trên chứng minh socket **127.0.0.1:8080**, không lắng nghe 192.168.x.x. Nếu local address là `0.0.0.0:8080`, nó lắng nghe IPv4 interfaces trong namespace này nhưng firewall/routing vẫn có thể chặn remote traffic.

Nếu Java ở Docker/Pod, chạy công cụ trong **đúng network namespace** (ví dụ debug container hoặc exec có công cụ phù hợp). `ss` trên Docker host không luôn cho thấy listener trong container.

### Windows PowerShell

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess

Test-NetConnection 127.0.0.1 -Port 8080
curl.exe -v http://127.0.0.1:8080/ping
~~~

Hoặc:

~~~powershell
netstat -ano | findstr :8080
~~~

Trên Windows PowerShell 5.1, `curl` có thể là alias `Invoke-WebRequest`; dùng **`curl.exe`** để `-v`, `--resolve` và các flags cURL hoạt động như ví dụ. Không kill một PID trước khi xác nhận đúng process/container.

### Cấu trúc lệnh cURL có thể tái hiện

~~~bash
curl -v --connect-timeout 3 --max-time 8 \
  http://127.0.0.1:8080/ping
~~~

- `-v`: DNS, TCP/TLS setup, request/response headers và thông tin lỗi.
- `--connect-timeout 3`: giới hạn kết nối, không phải total request duration.
- `--max-time 8`: giới hạn toàn bộ cURL transfer.
- `-i`: in response headers; `-L`: follow redirects (dùng có giới hạn).
- `--noproxy '*'`: bỏ qua outbound HTTP proxy được cấu hình trên máy client.

Với một HTTP **404**, socket và HTTP layer đã hoạt động ở một server nào đó; tiếp tục xem path/backend, không đổ lỗi kết nối TCP.

## 10. Docker: EXPOSE, -p, host port và container bind là bốn khái niệm

Tệp `Dockerfile` dựa trên project đã build:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /opt/app
COPY build/libs/network-access-lab.jar /opt/app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Build image:

~~~bash
./gradlew bootJar
docker build -t network-access-lab:1.0 .
~~~

Chạy:

~~~bash
docker run --rm --name network-lab \
  -p 127.0.0.1:18080:8080 \
  network-access-lab:1.0
~~~

Sơ đồ:

~~~text
Host 127.0.0.1:18080
       |
       v
Docker publish/NAT
       |
       v
ContainerIP:8080
       |
       v
Java listener 0.0.0.0:8080
       |
       v
GET /ping -> 200 pong
~~~

Host gọi:

~~~bash
curl -i http://127.0.0.1:18080/ping
~~~

**Không gọi host 8080** trong ví dụ mapping này. Các lỗi thường gặp:

| Sai lầm | Vì sao fail | Cách sửa |
| --- | --- | --- |
| Dockerfile có `EXPOSE 8080` nhưng `docker run` không `-p` | EXPOSE chỉ metadata, không publish host port | Dùng `-p`/Compose ports |
| `-p 18080:8080` nhưng cURL host 8080 | Sai host port | Gọi host 18080 |
| Spring bind `127.0.0.1:8080` trong container | NAT tới container IP, không phải container loopback | Bind `0.0.0.0` trong container |
| `-e SERVER_PORT=9090`, vẫn `-p 18080:8080` | Container nghe 9090, NAT chuyển tới 8080 | `-p 18080:9090` |
| Proxy container gọi `127.0.0.1:8080` | Loopback là proxy container | Dùng DNS service `web:8080` |
| Host bind `0.0.0.0:18080` ngoài ý muốn | Publish trên mọi host IPv4 interfaces | `-p 127.0.0.1:18080:8080` khi chỉ test local |
| Chạy hai containers cùng host port | Port publish conflict | Dùng host port khác hoặc dừng container đúng |
| Container restarted/OOM | Mapping tồn tại nhưng Java chưa Ready | `docker ps`/`docker logs`/inspect health |

**Chú ý bảo mật:** `docker run -p 18080:8080` thường publish port trên tất cả host interfaces, có thể lộ service ngoài máy. Bind host `127.0.0.1` cho lab; production ingress do LB/firewall policy kiểm soát. Docker NAT/network modes/versions có nuances nên đo thực tế.

### Lệnh kiểm tra Docker

~~~bash
docker ps
docker port network-lab
docker logs --tail 100 network-lab
docker inspect network-lab
~~~

`docker inspect` có thể chứa env vars và secrets, không đưa output thô vào ticket public. Nếu container chạy trên một Docker network, HTTP service-to-service dùng service DNS/port **nội bộ** chứ không cần host published port.

### Docker Compose

~~~yaml
services:
  web:
    image: network-access-lab:1.0
    environment:
      SERVER_PORT: "8080"
      SERVER_ADDRESS: "0.0.0.0"
    ports:
      - "127.0.0.1:18080:8080"
~~~

~~~bash
docker compose up
curl -i http://127.0.0.1:18080/ping
~~~

Nếu thêm một NGINX container **trong cùng Compose network**, NGINX upstream nên trỏ `http://web:8080`. Không trỏ `localhost:18080` vì đó là loopback của NGINX container và host mapping không phải đường service discovery.

## 11. Kubernetes: PodIP, Service port, targetPort và Endpoints

Một Spring Boot app trong cluster có ít nhất ba endpoints quan trọng:

~~~text
PodIP:8080                         (Java listens here)
Service ClusterIP:80              (Service port)
Ingress Host:443 / public domain  (if exposed externally)
~~~

**Ví dụ Deployment + Service**: image `network-access-lab:1.0` phải được push vào registry được cluster truy cập hoặc load sẵn vào kind/minikube. Tệp `k8s-network-lab.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: network-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: network-lab
  template:
    metadata:
      labels:
        app: network-lab
    spec:
      containers:
        - name: app
          image: network-access-lab:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_PORT
              value: "8080"
            - name: SERVER_ADDRESS
              value: "0.0.0.0"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
---
apiVersion: v1
kind: Service
metadata:
  name: network-lab
spec:
  selector:
    app: network-lab
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
  type: ClusterIP
~~~

Diễn giải:

- `containerPort: 8080` **không tự khiến Java listen 8080**; nó là metadata/port name của container.
- `Service.port: 80` là nơi clients trong cluster kết nối.
- `targetPort: http` tham chiếu `containerPort` có tên `http` → giá trị 8080.
- `selector.app=network-lab` phải khớp labels của Pod; nếu không Service không có backends.
- Pod Ready = false thì Service không route normal traffic vào Pod ấy; kiểm tra probe path và Spring Security.
- `type: ClusterIP` không tự tạo public IP/Ingress.
- `server.address=127.0.0.1` trong Pod thường khiến remote Pod traffic tới PodIP:8080 không được, dù bên trong Pod cURL localhost có thể 200.

Chạy:

~~~bash
kubectl apply -f k8s-network-lab.yaml
kubectl get pods -l app=network-lab -o wide
kubectl get svc network-lab
kubectl get endpointslice \
  -l kubernetes.io/service-name=network-lab
kubectl describe svc network-lab
kubectl logs deployment/network-lab --tail=100
~~~

Nếu dùng **kind** và image có ở Docker host, có thể load:

~~~bash
kind load docker-image network-access-lab:1.0
~~~

Nếu `ImagePullBackOff`, hãy sửa image availability trước khi debug port. Nếu `CrashLoopBackOff`, xem Java startup exception. Nếu `Running but NotReady`, xem `kubectl describe pod` và probe HTTP/status.

### Kiểm tra qua Service từ trong cluster

Một test Pod dùng cURL:

~~~bash
kubectl run network-client --rm -i \
  --restart=Never --image=curlimages/curl:8.10.1 -- \
  curl -sv http://network-lab:80/ping
~~~

Chỉ thực hiện khi test image được phép dùng và có thể pull. Ở namespace khác, dùng FQDN `network-lab.<namespace>.svc.cluster.local`. Nếu trả HTTP 200 `pong`, Service → app route trong cluster đã hoạt động, nhưng chưa chứng minh external ingress đúng.

### Port-forward không phải Ingress test

~~~bash
kubectl port-forward service/network-lab 18080:80
~~~

Sau đó `curl http://localhost:18080/ping` có thể 200. Tuy nhiên `port-forward` là **đường debug của Kubernetes API server**, thường chọn một Pod; nó không đi qua DNS public, TLS termination, Ingress rules và external LB. Không dùng kết quả này để tuyên bố người dùng trên Internet truy cập được.

### Khi Service không có endpoints

1. Đọc Service selectors và Pod labels.
2. Đọc `readinessProbe` response/status; health path có đúng không?
3. Xác nhận named `targetPort` khớp `containerPort`.
4. Xác nhận Java bind Pod interface, không loopback-only.
5. Kiểm tra Pod restarts, HPA/rollout/draining.
6. Kiểm tra NetworkPolicy/service mesh/mTLS, DNS và CNI connectivity.
7. Test Pod IP từ một debug Pod được phép; tách lỗi Pod listening khỏi Service.
8. Ghi timestamp của Pod/EndpointSlice transitions, tránh xem một snapshot duy nhất lúc endpoints đang đổi.

## 12. Ingress: Host/Path/Service name/TLS đều phải đúng

Ingress manifest minh họa, với controller class tên `nginx` đã được cài trong cluster:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: network-lab
spec:
  ingressClassName: nginx
  rules:
    - host: demo.example.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: network-lab
                port:
                  number: 80
~~~

**Không coi manifest này là HTTPS config hoàn chỉnh.** Cần ingress controller, DNS thật, LB và TLS config/cert khi muốn phục vụ cổng 443. `demo.example.test` là hostname ví dụ, phải dùng hostname của staging khi chạy thật.

Những lỗi thường gặp:

| Lỗi | Đầu mối |
| --- | --- |
| Ingress chưa có controller | Object tồn tại nhưng không ai phục vụ HTTP |
| `ingressClassName` không khớp | Controller không nhận rule |
| Host không match | Default backend trả 404 |
| Path rule không match | Ingress 404 hoặc route nhầm service |
| Backend service port 8080 nhưng Service chỉ port 80 | Upstream target cấu hình sai |
| Service không có ready EndpointSlices | Gateway có thể trả 503 |
| NGINX Ingress rewrite khác app context | Spring 404 |
| TLS secret/certificate lỗi | Browser bị chặn trước Spring |
| DNS A/AAAA trỏ LB cũ | Chỉ một số clients vào sai nơi |

**Phân biệt:**
- `Service.port` = 80 trong manifest.
- `Pod.containerPort` = 8080.
- `Ingress.service.port.number` phải tham chiếu **80**, không phải 8080.
- `server.port` của Spring phải là 8080 như container listener.
- Nếu còn proxy ngoài cluster, phải xét thêm TLS/Host/path của proxy đó.

## 13. NGINX proxy_pass và dấu slash cuối: nguồn HTTP 404 rất phổ biến

Giả sử Spring có mapping:

~~~java
@GetMapping("/ping")
public String ping() {
    return "pong";
}
~~~

Client public gọi `/api/ping`, còn upstream Spring cần `/ping`.

### Đúng nếu muốn strip prefix /api/

~~~nginx
server {
    listen 8088;
    server_name localhost;

    location /api/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /api;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Đoạn này giả định NGINX **cùng host** với Spring và NGINX là trusted entrypoint. Ở production còn cần LB/TLS/security; nếu NGINX container riêng, đổi upstream theo service DNS.

Kết quả:

~~~text
Client  -> GET /api/ping
NGINX   -> GET /ping
Spring  -> HTTP 200, body pong
~~~

Vì với prefix location `/api/`, `proxy_pass http://127.0.0.1:8080/;` **có URI `/`**, NGINX thay phần prefix khớp bằng URI đó.

### Sai nếu kỳ vọng strip prefix nhưng không có slash

~~~nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
}
~~~

Trường hợp không có URI trong `proxy_pass`, request URI thường được chuyển tiếp nguyên:

~~~text
Client  -> GET /api/ping
NGINX   -> GET /api/ping
Spring  -> 404 vì chỉ map /ping
~~~

**Bảng dễ nhớ:**

| Location | proxy_pass | Client URI | URI vào upstream |
| --- | --- | --- | --- |
| `/api/` | `http://app:8080/` | `/api/ping` | `/ping` |
| `/api/` | `http://app:8080` | `/api/ping` | `/api/ping` |
| `/api/` | `http://app:8080/v1/` | `/api/ping` | `/v1/ping` |

Đây là prefix location đơn giản; regexp location, rewrite/variables và URI normalization có semantics khác. Nếu Spring đã có `server.servlet.context-path=/api` thì app **cần nhận `/api/ping`**, do đó không strip một lần nữa.

### NGINX chạy ở đâu?

- Cùng VM với app → upstream `127.0.0.1:8080` có thể đúng.
- NGINX trong Docker container khác → `127.0.0.1` là NGINX container; dùng `web:8080` trong Compose network.
- NGINX Ingress trong Kubernetes → đi qua Kubernetes Service `network-lab:80`.
- Host có Docker published port → upstream có thể trỏ host published port, nhưng cần biết host routing, network mode và firewall.

**Một upstream sai IP/port thường trả 502**, còn upstream đúng mà path sai thường trả 404. Đối chiếu NGINX error/access logs với Spring access logs để phân biệt.

## 14. server.servlet.context-path và spring.mvc.servlet.path

Một HTTP listener khỏe cũng trả 404 nếu request URL không chứa prefix mà app thực sự đăng ký.

Trong Spring MVC:

~~~properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/api
~~~

Với controller `@GetMapping("/ping")`, URL embedded Servlet app thường là:

~~~text
http://localhost:8080/shop/api/ping
~~~

Lớp đường dẫn:

~~~text
Port                  :8080
Servlet context       /shop
DispatcherServlet     /api
Controller mapping    /ping
Full path             /shop/api/ping
~~~

Đừng đổi cổng khi lỗi thực tế là thiếu `/shop/api`. Spring WebFlux có cấu hình `spring.webflux.base-path`; không dùng `spring.mvc.servlet.path` trong ứng dụng WebFlux/Netty rồi kết luận mapping WebFlux hoạt động.

**External WAR:** nếu app đóng thành `shop.war` và deploy lên external Tomcat, context thường `/shop` do container quyết định; `server.port` của Boot không điều khiển Tomcat connector port. URL còn phụ thuộc WAR name/context descriptor.

### Context path và reverse proxy phải nhất quán

Có hai thiết kế:
1. Spring ở root `/ping`, proxy nhận `/api/ping` rồi **strip `/api`**.
2. Spring có context `/api`, proxy nhận `/api/ping` và **giữ** prefix.

Cả hai hợp lệ nếu cấu hình rõ. Lỗi xảy ra khi proxy strip mà app vẫn chờ prefix, hoặc proxy preserve mà app chỉ map root.

## 15. Forwarded headers: hostname/scheme/port/public prefix sau proxy

Một triển khai TLS termination:

~~~text
Browser: https://shop.example.test/api/ping
  |
  v
Ingress / NGINX TLS :443
  |
  | proxy HTTP to 10.0.0.20:8080
  | Host: shop.example.test
  | X-Forwarded-Proto: https
  | X-Forwarded-Host: shop.example.test
  | X-Forwarded-Port: 443
  | X-Forwarded-Prefix: /api
  v
Spring Boot HTTP :8080
~~~

Nếu app không hiểu external URL, `ServletUriComponentsBuilder` hoặc redirect/cookie logic có thể sinh:

~~~http
HTTP/1.1 302
Location: http://10.0.0.20:8080/ping
~~~

thay vì `https://shop.example.test/api/ping`. Browser có thể mắc redirect loop, mixed-content hoặc truy cập host nội bộ không định tuyến được.

### server.forward-headers-strategy

Spring Boot 3.3 có ba lựa chọn:

~~~properties
server.forward-headers-strategy=none
~~~

Không dùng Spring-level forwarded-header processing. Phù hợp khi không có trusted proxy; runtime defaults có thể khác theo cloud platform.

~~~properties
server.forward-headers-strategy=native
~~~

Dùng cơ chế native HTTP server, ví dụ Tomcat RemoteIpValve, thường đủ để xử lý `X-Forwarded-For`/`X-Forwarded-Proto` khi trusted proxy đúng. Với Tomcat TLS terminated ở proxy, Boot docs còn đề cập:

~~~properties
server.forward-headers-strategy=native
server.tomcat.redirect-context-root=false
~~~

để forwarded proto được xét trước một số context-root redirects.

~~~properties
server.forward-headers-strategy=framework
~~~

Dùng `ForwardedHeaderFilter` trong Servlet MVC hoặc `ForwardedHeaderTransformer` trong WebFlux; hữu ích khi cần thêm `X-Forwarded-Prefix` cho generated redirects/links hoặc native handling chưa đủ.

**Không bật và tin headers bất kỳ từ Internet**. Attacker có thể gửi `X-Forwarded-Host: attacker.example`, `X-Forwarded-Proto: https` hoặc giả `X-Forwarded-For`. Gateway phải strip/overwrite untrusted forwarded headers và cấu hình trusted proxy ranges. Với multiple proxies, xác định hop nào có quyền khai external Host/scheme/IP, không lấy giá trị do client tự nói.

### NGINX forwarded config mẫu

Đoạn dưới nằm trong server block đã được cấu hình HTTPS hợp lệ:

~~~nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /api;

    # Chỉ đúng nếu NGINX chính là trusted ingress entrypoint.
    proxy_set_header X-Forwarded-For $remote_addr;
}
~~~

Nếu NGINX còn nằm sau CDN/LB, `$scheme` và `$server_port` có thể là giá trị *internal hop*, không phải public HTTPS scheme/port. Cần xác định trusted source và chain. Đừng cộng raw `$http_x_forwarded_for` của client Internet vào quyền xác định remote identity.

**Cực kỳ quan trọng:** `server.forward-headers-strategy=framework` **không tự thay** `proxy_pass` URI rewrite. Nó điều chỉnh request metadata/generation, không phải một guarantee tự strip mọi prefix khỏi route. Trước hết sửa upstream URI cho đúng controller mapping.

### Test redirect

~~~bash
curl -i http://127.0.0.1:8080/jump
curl -i http://127.0.0.1:8088/api/jump
~~~

So `Location`:
- direct có thể là `http://127.0.0.1:8080/ping`;
- qua trusted proxy có forwarded strategy phù hợp thì public URL phải khớp public scheme, host, port và prefix khi framework/server hỗ trợ.

Không giả định kết quả chỉ từ config; kiểm tra header thực, Spring version và proxy chain.

## 16. TLS: HTTP/HTTPS mismatch, SNI và redirect loop

HTTP direct 200 không chứng minh HTTPS public đúng. Xác định vị trí TLS termination:

| Client → proxy | Proxy → Spring | Spring |
| --- | --- | --- |
| HTTPS 443 | HTTP 8080 | App HTTP listener |
| HTTPS 443 | HTTPS 8443 | App HTTPS listener |
| Không có proxy | HTTP 8080 | App HTTP listener |

Các lỗi:
- `https://host:8080` gọi server HTTP-only → TLS handshake lỗi, không phải controller 404.
- `proxy_pass https://app:8080` tới app HTTP → upstream SSL failure/502.
- Certificate hết hạn, SAN không khớp domain, chain thiếu hoặc SNI sai.
- CDN/ingress đổi HTTP→HTTPS nhưng app tiếp tục redirect về HTTP do không tin forwarded proto → vòng lặp.
- App trả `Location` tới port nội bộ/hostname private.
- HSTS trong browser khiến request HTTP tự thành HTTPS, khác thử nghiệm cURL.

Dùng:

~~~bash
curl -v https://shop.example.test/api/ping
curl -I https://shop.example.test/api/jump
curl -v -L --max-redirs 5 \
  https://shop.example.test/api/jump
~~~

Đây là ví dụ khi DNS/cert staging đã hợp lệ. `curl -L` giúp xem redirect chain; giới hạn số redirects khi điều tra loop. Không dùng `curl -k`/`--insecure` như fix lâu dài vì nó bỏ cert verification và che lỗi security.

### Khi proxy đã terminate TLS, app có cần bật server.ssl không?

Không nhất thiết. Với thiết kế NGINX TLS termination + HTTP upstream trong trusted private network, app nghe HTTP :8080 và proxy nhận HTTPS :443. Nếu policy yêu cầu TLS end-to-end, app phải phục vụ HTTPS ở port/certificate cấu hình rõ và NGINX `proxy_pass https://...` tương ứng. Không trộn hai thiết kế.

## 17. Firewall, security groups, VPC và client proxy environment

Nếu app nghe `0.0.0.0:8080` nhưng remote machine timeout:

1. Kiểm tra remote đang gọi **đúng private/public IP** của VM/node/LB.
2. Test từ cùng host rồi cùng subnet rồi outside subnet.
3. Kiểm tra OS firewall, cloud security group/source CIDR, NAT, routing table, network policies.
4. Kiểm tra DNS A/AAAA và certificate/Host ở LB.
5. Xem cloud LB target health và backend port.
6. Không mở inbound `0.0.0.0/0:8080` nếu mô hình chỉ cho phép traffic từ LB; đặt minimal allowed source ranges.

Các lệnh:

~~~bash
# Nếu được cài trong OS:
getent hosts shop.example.test
nslookup shop.example.test
curl -v --connect-timeout 3 http://private-host:8080/ping
~~~

PowerShell:

~~~powershell
Resolve-DnsName shop.example.test
Test-NetConnection shop.example.test -Port 443
~~~

**Client-side HTTP proxy** cũng cần xét. Trên máy corporate, `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY` có thể khiến cURL đi qua proxy của công ty, không kết nối trực tiếp. So:

~~~bash
curl -v http://127.0.0.1:8080/ping
curl -v --noproxy '*' http://127.0.0.1:8080/ping
~~~

Nếu cách thứ hai hoạt động, xem outbound proxy settings. Không coi kết quả proxy công ty trả 502 là chứng cứ Spring không nghe.

## 18. Management server khác main app server

Ví dụ:

~~~properties
server.port=8080
management.server.port=9091
~~~

Actuator có thể chạy trên management web server riêng. Khi đó:

~~~text
GET http://localhost:9091/actuator/health -> HTTP 200
GET http://localhost:8080/ping          -> có thể vẫn lỗi
~~~

Một health check ở management port **không chứng minh** main application port accept connections. Khi hai ports tách biệt, health groups không nhất thiết dùng cùng server infrastructure.

Với Actuator Spring Boot 3.3:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

có thể cung cấp thêm `/livez` và `/readyz` trên **main server port** để probes đánh giá đúng listener cần phục vụ traffic. Cần test paths theo context/security mapping của runtime thực.

**Tránh mở public** `/actuator/env`, `/actuator/configprops` hoặc `/actuator/heapdump` để debug: có thể lộ cấu hình, secrets và hệ thống nội bộ. Dùng network/authorization đủ mạnh, tránh gửi logs chứa token trong ticket.

### Readiness/liveness trong Kubernetes

- Pod `Running` không có nghĩa Ready.
- Pod Ready không chứng minh public Ingress/TLS đúng.
- Management health UP không thay HTTP synthetic test qua main port.
- Readiness wrong path hoặc Spring Security bảo vệ health có thể làm Pod never Ready; Ingress/Service không có endpoints.
- Liveness không nên phụ thuộc DB chung một cách ngây thơ, tránh restart storm khi dependency tạm thời lỗi.

## 19. 404, 401, 403, CORS không phải lỗi bind TCP

### 404

Nếu server trả HTTP 404, kiểm tra:
- `@RestController` có nằm trong component scan không?
- `@GetMapping` đúng method/URI/case/trailing slash chưa?
- `server.servlet.context-path`/`spring.mvc.servlet.path`/WAR context đúng chưa?
- NGINX có strip/preserve prefix đúng không?
- Request đã vào đúng backend hay ingress default backend?
- React/WebFlux app có route khác Servlet Spring MVC không?

### 401 / 403

Nếu có response, một security layer đã nhận request. Xem:
- Spring Security filter chain, authentication, authorization.
- CSRF với browser session và non-safe HTTP methods.
- API gateway auth/WAF/allowlist.
- OPTIONS preflight chưa được phép qua filter/proxy.
- Header Host/Authorization/cookie có bị proxy bỏ hoặc sửa sai không?

Không thay `server.port` để “fix” 401/403.

### CORS

Browser ở `http://localhost:3000` gọi API `http://localhost:8080` là **cross-origin vì port khác**, dù cùng host. cURL không enforce CORS như browser nên cURL 200 nhưng browser báo CORS error là có thể.

Cần allowlist origins/methods/headers và cho OPTIONS preflight đi qua đúng Spring Security/NGINX. Không dùng wildcard `Access-Control-Allow-Origin: *` kết hợp credentials; chính sách an toàn cần rõ nguồn frontend thật.

## 20. Gateway lỗi 502, 503, 504: phân biệt upstream path, port và timeout

### 502 Bad Gateway

Gateway không nhận phản hồi hợp lệ từ upstream:
- `proxy_pass` sai port/IP/hostname (127.0.0.1 sai container namespace).
- Spring bind loopback nhưng gateway nối Pod IP.
- TLS mismatch: proxy HTTPS → app HTTP hoặc ngược lại.
- K8s Service không có backend Ready hoặc targetPort sai.
- Pod dừng/restart trong khi proxy dùng connection cũ.
- Upstream reset hoặc gửi invalid HTTP response.

Xem NGINX `error_log` (ví dụ connect() failed/connection refused) và Spring logs ở cùng timestamp. Nếu request chưa tới Spring, access log app có thể không có record.

### 503 Service Unavailable

Có thể do:
- Spring/app chủ động load shedding.
- Gateway/Ingress không có upstream Ready.
- Rolling deployment/graceful shutdown.
- Maintenance mode hoặc rate/concurrency policy.

Mã 503 **không tự chứng minh** Spring listener đã từ chối; cần xác định layer phát response.

### 504 Gateway Timeout

Gateway chờ upstream quá lâu. NGINX `proxy_read_timeout` là khoảng giữa hai lần đọc response từ upstream, **không phải tổng deadline cố định cho mọi request**. App có thể đang thực hiện DB query hoặc có thể đã commit rồi dù client thấy 504. Với POST có side effect, cần idempotency/reconciliation trước retry.

### Bảng so direct với proxy

| Origin trực tiếp | Qua proxy | Hướng kiểm tra |
| --- | --- | --- |
| 200 | 502 | IP/port/upstream scheme/network namespace |
| 200 | 404 | Host route, proxy_pass URI rewrite/context |
| 200 | Redirect loop | Forwarded proto/Host/prefix hoặc TLS redirect |
| 200 | 401/403 | Gateway auth/WAF, forwarded headers, CORS |
| Chậm | 504 | App/downstream latency và timeout budget |
| Refused | 502 | App listener/port/bind trước proxy |
| 200 | Browser TLS error | Certificate/SNI/chain, không phải controller |

## 21. Khác biệt giữa Tomcat, Jetty, Undertow, Reactor Netty và external WAR

### Embedded Servlet

Spring Boot `spring-boot-starter-web` dùng Tomcat mặc định. Có thể đổi Jetty/Undertow qua starter dependencies nhưng `server.port`/`server.address` vẫn là properties chung cho embedded server. Một số connector-specific options khác giữa các engines; không copy `server.tomcat.*` sang Jetty rồi chờ tác dụng.

### WebFlux/Reactor Netty

`spring-boot-starter-webflux` thường chạy trên Reactor Netty khi không thêm Servlet starter. `server.port`/`server.address` vẫn quan trọng, nhưng `server.servlet.context-path` và `spring.mvc.servlet.path` không phải cơ chế route path cho WebFlux. Dùng `spring.webflux.base-path` khi cần global prefix đúng reactive stack.

Nếu thêm cả `starter-web` và `starter-webflux`, Boot 3.x thường ưu tiên Spring MVC Servlet. Không kết luận server là Netty chỉ vì code dùng `WebClient`.

### External WAR

Khi triển khai WAR vào Tomcat ngoài:
- Tomcat connector config quyết định port/public bind.
- WAR filename/context descriptor quyết định context path.
- SpringBootServletInitializer khởi tạo app khi container deploy.
- `server.port` trong packaged app không làm Tomcat ngoài mở cổng riêng.
- External Tomcat có thể đang phục vụ nhiều WAR/shared JVM; cần xác định app context trước khi test.

### Management context

Nếu `management.server.port` khác `server.port`, health listener là một endpoint riêng. Không xem việc vào được management :9091 là bằng chứng main API :8080 accessible.

## 22. Quy trình debug 12 bước để không đổi sai tầng

1. **Ghi rõ URL lỗi:** scheme, Host, port, prefix, route, request method; ví dụ `https://shop.example.test/api/ping`.
2. **Kiểm tra runtime:** Java process, embedded JAR/Netty hay external Tomcat WAR? Có HTTP listener thật không?
3. **Đọc logs hiện tại:** cổng, active profiles, context path, startup errors và PID (không đọc log cũ).
4. **Xem config hiệu lực:** `server.port`, `server.address`, env/profile/CLI, port 0/-1, non-web type.
5. **Đọc listening socket trong đúng namespace:** `ss`/`lsof`/`Get-NetTCPConnection`; loopback vs wildcard, IPv4 vs IPv6.
6. **Gọi direct local HTTP path:** cURL `/ping` có 200 body `pong` không? Nếu 404/401, xem app route/security.
7. **Gọi private IP từ peer network:** nếu fail, kiểm tra bind/firewall/SG/routing.
8. **Nếu Docker:** so port mapping Host:Container, Java listener container, proxy DNS.
9. **Nếu Kubernetes:** Pod Ready, Service selector/EndpointSlices, Service port→targetPort, NetworkPolicy.
10. **Nếu proxy/Ingress:** Host/path/TLS/upstream scheme+port/rewrite, forwarded headers trust và proxy error logs.
11. **Nếu browser khác cURL:** xem CORS, cookies, HSTS, client HTTP proxy, cert, redirect chain và IPv6.
12. **Sau khi đổi một config:** restart/rollout, chạy lại tests qua direct, Service và public URL, lưu output status/body/Location/timestamps.

### Biểu đồ quyết định

~~~text
App báo Started, client không truy cập
  |
  v
Có HTTP listener đúng IP:port?
  | NO -> starter/webApplicationType, server.port=0/-1,
  |       server.address, port conflict, process startup
  v
Local curl /ping = 200?
  | NO -> protocol, context path, mapping, security
  v
Private-network peer tới app IP:port?
  | NO -> bind loopback, firewall, route, container NAT
  v
Docker/Kubernetes Service tới app?
  | NO -> publish port, targetPort, selector, readiness
  v
Public Ingress/DNS/Host/TLS đúng?
  | NO -> ingressClass, DNS, SNI, certificates, firewall
  v
Public path /api/ping map đúng?
  | NO -> proxy_pass URI, slash, prefix, context
  v
Redirect /jump đúng https/domain/prefix?
  | NO -> trusted forwarded headers, TLS termination
  v
Browser còn báo lỗi?
         CORS, auth, CSRF, cookie SameSite,
         HSTS, client proxy/cache
~~~

## 23. Bài tập tình huống có đáp án

**1.** `server.port=8080` trong source, nhưng JVM chạy `--server.port=9090`. Cổng nào thực sự nhận HTTP?

**Đáp án:** 9090 theo Spring Boot command-line precedence mặc định. Xác nhận startup logs/socket và source override.

**2.** `server.port=0`, app Started, cURL 8080 bị refused.

**Đáp án:** Server chọn port ngẫu nhiên. Đọc startup port thực hoặc `@LocalServerPort` trong tests.

**3.** `server.port=-1` có chắc crash app?

**Đáp án:** Không. Boot vẫn có thể tạo WebApplicationContext nhưng không phục vụ HTTP endpoints.

**4.** `server.address=127.0.0.1`, cURL localhost 200 nhưng LAN host IP không được.

**Đáp án:** Listener chỉ ở loopback. Bind interface cần thiết và mở network policy tối thiểu thay vì tắt firewall.

**5.** Docker `-p 18080:8080` mà host gọi localhost:8080 thất bại.

**Đáp án:** Host port là 18080. Phải gọi `localhost:18080`.

**6.** Docker container dùng `SERVER_ADDRESS=127.0.0.1` và đã publish port đúng.

**Đáp án:** NAT tới container IP không tới container loopback. Bind 0.0.0.0 trong container, giới hạn host publish bằng 127.0.0.1 nếu cần.

**7.** NGINX container proxy tới `127.0.0.1:8080` nhưng Spring chạy container khác.

**Đáp án:** Loopback thuộc NGINX container. Dùng DNS service `web:8080` hoặc network target thực.

**8.** K8s Pod nghe 8080, Service targetPort 9090.

**Đáp án:** Service gửi vào cổng không có listener. Đổi targetPort 8080 hoặc named port khớp Pod.

**9.** `kubectl port-forward svc/network-lab 18080:80` hoạt động nhưng public Ingress 502.

**Đáp án:** Port-forward là đường debug khác Ingress. Kiểm tra ingress controller/class, backend Service name/port, endpoints, upstream errors và TLS/LB.

**10.** NGINX `location /api/` + `proxy_pass http://app:8080;` chuyển request `/api/ping` tới đâu?

**Đáp án:** Thường giữ `/api/ping`. Nếu app chỉ map `/ping` thì 404. Dùng URI slash trong proxy_pass để strip prefix khi đó là contract.

**11.** Browser HTTPS bị redirect về `http://10.0.0.20:8080/ping`.

**Đáp án:** App chưa hiểu external scheme/host/prefix hoặc proxy forwarded headers sai/trust policy thiếu. Xem `server.forward-headers-strategy`, gateway overwrite và Location.

**12.** Browser báo CORS nhưng `curl http://localhost:8080/ping` trả 200.

**Đáp án:** CORS là browser cross-origin policy, không phải TCP socket error. Xử lý OPTIONS/allowed origins/security.

**13.** Actuator health ở 9091 báo UP nhưng `/ping` tại 8080 không dùng được.

**Đáp án:** Management listener có thể riêng. Test main server port và đường route thật; có thể dùng readiness additional paths trên main port.

**14.** Proxy nhận 504 sau 30s và client retry POST tạo đơn hàng.

**Đáp án:** 504 không xác nhận server chưa COMMIT; dùng idempotency key và durable reconciliation trước retry non-idempotent.

**15.** DNS có cả A và AAAA, cURL -4 hoạt động còn -6 fail.

**Đáp án:** Hệ thống IPv6 listener/routing/firewall chưa nhất quán với DNS AAAA; sửa theo dual-stack topology, không đổ lỗi controller.

**16.** WAR trong external Tomcat dùng `server.port=9090` nhưng Tomcat ngoài chỉ nghe 8080.

**Đáp án:** External servlet container sở hữu connector port. Sửa Tomcat config; test WAR context path như `/app/hello`.

## 24. Checklist trước khi coi sự cố đã khắc phục

- [ ] Đã xác định đúng **client URL** (scheme, hostname, port, prefix, route)?
- [ ] HTTP server thực đang chạy, không phải batch app/non-web hoặc port=-1?
- [ ] Port hiệu lực không bị override bởi CLI/profile/env/management?
- [ ] Listening socket đúng bind IP/IPv4/IPv6 và process/PID?
- [ ] cURL direct app thành công ở cùng network namespace?
- [ ] Remote private-network connectivity qua firewall/SG/VPC đúng?
- [ ] Docker `-p`, `EXPOSE` và container server port/address nhất quán?
- [ ] Kubernetes Service port/targetPort, selectors, Pod Ready/endpoints đúng?
- [ ] Ingress controller/class/Host/path/backend Service port/TLS đúng?
- [ ] NGINX proxy_pass đúng scheme, upstream address, URI rewrite/trailing slash?
- [ ] Context path/mvc servlet path/WebFlux base path/external WAR context đúng?
- [ ] Forwarded headers chỉ đến từ trusted proxies và generated redirects chính xác?
- [ ] HTTP↔HTTPS, SNI/cert và HSTS nhất quán?
- [ ] CORS/auth/CSRF lỗi HTTP không bị nhầm với connection refused?
- [ ] Management health và main HTTP listener được test riêng?
- [ ] 502/503/504 được đối chiếu edge/proxy/origin, không chỉ xem một log?
- [ ] Không public diagnostic /where hoặc Actuator config endpoints?
- [ ] Đã test thật từ local, host, in-cluster Service và public ingress sau khi sửa?
- [ ] Đã ghi runbook: URL, port map, config source, response và nguyên nhân gốc?

## 25. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): port 0/-1, server.port, forwarded headers, Tomcat proxy config.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): server.address và embedded Servlet server customization.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): precedence của file/env/JVM/CLI/profile.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): server.port, server.address, management.server.port.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): readiness/liveness, management port, additional probe paths.
- [Spring Framework — Servlet filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): ForwardedHeaderFilter và request wrappers.
- [Docker — Publishing and exposing ports](https://docs.docker.com/engine/network/port-publishing/): -p host/container mapping, published bind address.
- [Docker Compose — Networking](https://docs.docker.com/compose/how-tos/networking/): service DNS và container ports.
- [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/): port/targetPort, labels/selectors và backend discovery.
- [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): ready endpoints được Service theo dõi.
- [Kubernetes — Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/): hostname, path, ingressClass và backend ports.
- [Kubernetes — Liveness/Readiness/Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): probe semantics.
- [NGINX — HTTP proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass): URI rewrite với và không có proxy_pass URI.
- [NGINX — HTTP core module](https://nginx.org/en/docs/http/ngx_http_core_module.html): location prefix, redirect và routing.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser cross-origin và preflight.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): phân biệt 404, 502, 503, 504.

**Kết luận:** Khi ứng dụng báo `Started` nhưng không thể truy cập, hãy xem **socket thực, địa chỉ bind, port đang gọi và mạng của caller** trước. Nếu direct origin hoạt động, kiểm tra tiếp Docker/Kubernetes/Ingress/NGINX/TLS và forwarding. Một HTTP 404 là vấn đề path/router; một TCP refused là vấn đề socket/network; một 502/504 có thể do gateway. Phân loại đúng lỗi và kiểm chứng từng hop sẽ giải quyết vấn đề mà không phá cấu hình bảo mật hoặc thay đổi sai lớp.
