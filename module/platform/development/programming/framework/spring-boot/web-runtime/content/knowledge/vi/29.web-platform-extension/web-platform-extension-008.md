# RSocket qua TCP hoặc WebSocket và điều kiện dùng chung máy chủ web

## 1. Mục tiêu và điểm mấu chốt

RSocket là giao thức messaging nhị phân dùng trên các byte-stream transports. RSocket không phải HTTP, cũng không phải WebSocket: **TCP và WebSocket là hai cách vận chuyển RSocket frames**. Spring Boot 3.3 có thể mở một RSocket listener **độc lập** hoặc ghép **RSocket-over-WebSocket vào cùng web server** khi thỏa điều kiện cụ thể.

Cần nhớ:

- `spring.rsocket.server.port=9898`: yêu cầu listener RSocket **riêng**. Với `transport=tcp`, đó là TCP RSocket; với `transport=websocket`, đó là RSocket-over-WebSocket standalone.
- `server.port=8080`: là cổng embedded HTTP web server, **không tự biến cổng 8080 thành RSocket TCP**.
- Muốn RSocket **dùng chung cổng HTTP** theo Spring Boot auto-configuration, phải có **WebFlux application type REACTIVE**, embedded **Reactor Netty**, `transport=websocket`, `mapping-path=/rsocket` và **không có RSocket server port riêng**.
- **Spring MVC/Servlet chạy Tomcat không được Boot ghép RSocket vào cùng embedded web listener bằng cấu hình shared-port nói trên.** Có thể chạy standalone RSocket listener trong JVM hoặc dùng reverse proxy để có một public entry point; đó là topology khác.

Bài nằm trong nhóm **Mở rộng nền tảng web**. Bạn sẽ học cách so sánh hai transports, bốn interaction models, Spring Boot profiles, port binding, requester/responder, codec, backpressure, TLS, proxy, WebFlux/MVC và chạy ví dụ Java 17+/Spring Boot 3.3.5 với cả chế độ TCP và WebSocket.

## 2. Phân biệt bốn lớp khái niệm

~~~text
HTTP request-response bình thường
  Browser -- HTTP GET /http/ping --> Spring WebFlux
  Browser <-- HTTP 200 + body ------ Spring WebFlux

RSocket trên TCP
  RSocketRequester == TCP connection ==> RSocket responder
                 RSocket SETUP / request frames

RSocket trên WebSocket
  RSocketRequester -- HTTP upgrade --> WebFlux Reactor Netty
                      == WebSocket frames ==
                      bên trong là RSocket binary frames

STOMP trên WebSocket (KHÁC RSocket)
  STOMP client -- WebSocket --> STOMP processor/broker
                CONNECT / SEND / SUBSCRIBE / MESSAGE
~~~

**HTTP** có method, URL, status và headers; **WebSocket** có handshake/frames và truyền hai chiều; **RSocket** có setup, stream IDs, metadata, backpressure và interaction models; **STOMP** là giao thức messaging riêng có commands/destinations. Không lấy client STOMP hay browser `new WebSocket(...)` gửi text thuần để kỳ vọng Spring tự xử lý RSocket metadata route.

Trên WebSocket transport, HTTP path `/rsocket` là **điểm bắt đầu handshake**, không phải tất cả RSocket routes được biểu diễn thành `/rsocket/greet` hoặc các HTTP endpoints khác. Route `greet` được gửi bên trong **RSocket routing metadata** sau handshake.

## 3. Bốn interaction models của RSocket

| Interaction | Requester | Responder | Spring API |
| --- | --- | --- | --- |
| Request-response | Một message | Một message | `retrieveMono(Class<T>)` / `Mono<T>` |
| Fire-and-forget | Một message | Không mong response nghiệp vụ | `send(): Mono<Void>` |
| Request-stream | Một request | Stream nhiều messages | `retrieveFlux(Class<T>)` / `Flux<T>` |
| Request-channel | Stream request messages | Stream response messages | `data(Flux<T>, T.class)` / `retrieveFlux(...)` |

### 3.1. Request-response

~~~text
Requester                 Responder
   |-- REQUEST_RESPONSE ---->|
   |<----- PAYLOAD ----------|
~~~

Phù hợp truy vấn profile, sản phẩm, tính toán nhanh. Không có HTTP 200 trong RSocket exchange; kết quả đi qua RSocket PAYLOAD và lỗi qua RSocket ERROR semantics.

### 3.2. Request-stream và backpressure

~~~text
Requester                 Responder
   |-- REQUEST_STREAM ------>|
   |<--- PAYLOAD #1 ---------|
   |-- REQUEST_N (+2) ------>|
   |<--- PAYLOAD #2 ---------|
   |<--- PAYLOAD #3 ---------|
   |<--- COMPLETE -----------|
~~~

Requester có thể đưa ra **demand** về số items được chấp nhận. RSocket dùng các tín hiệu như `REQUEST_N` để điều tiết stream xuyên network boundary. Đây là điểm khác với raw WebSocket: bạn không cần tự thiết kế demand protocol cho các interaction models của RSocket. Tuy nhiên, backpressure **không** tự tạo persistence, offline inbox, durable queue hay exactly-once semantics.

### 3.3. Fire-and-forget

Requester gửi một message không yêu cầu response nghiệp vụ. Khi Spring `send()` trả `Mono<Void>` hoàn tất, điều đó không xác nhận responder đã commit database hoặc hoàn thành tác vụ bất đồng bộ. Nếu cần business acknowledgement, chọn request-response hoặc cơ chế xác nhận riêng.

### 3.4. Request-channel

Cả hai phía trao đổi streams trong cùng một interaction:

~~~text
Requester -- "one" ----> Responder
Requester -- "two" ----> Responder
Requester <-- "ONE" ---- Responder
Requester <-- "TWO" ---- Responder
~~~

Channel không phải hai HTTP requests, cũng không phải STOMP subscription. Spring responder có thể nhận `Flux<String>` và trả `Flux<String>`. Việc gửi stream cần chú ý demand, cancellation và xử lý lỗi.

### 3.5. Requester và responder không khóa cứng theo client/server

Sau RSocket `SETUP`, hai phía có thể có khả năng gửi interactions. Vì thế mô hình RSocket phân biệt **requester/responder theo interaction**, không coi bên chủ động TCP connection mãi chỉ gửi requests. Để nhận request từ phía server, client cần đăng ký responder thích hợp; không tự bật chỉ vì đã có connection.

## 4. TCP transport: một listener riêng

~~~text
RSocketRequester
     |
     | TCP connect localhost:9898
     | RSocket SETUP / frames
     v
RSocket TCP server :9898

Spring HTTP web server :8080  (nếu có) — listener khác
~~~

Cấu hình:

~~~properties
server.port=8080
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=9898
~~~

- `server.port` điều khiển HTTP listener.
- `spring.rsocket.server.port` điều khiển RSocket standalone listener.
- Dù hai listeners thuộc **cùng Spring Boot process**, chúng vẫn khác địa chỉ/cổng/sockets.
- `curl http://localhost:9898` không phải RSocket client; TCP RSocket **không** đọc HTTP method/path.
- Đừng khai báo `spring.rsocket.server.mapping-path` để “gắn path” vào TCP: mapping path chỉ có nghĩa với WebSocket transport.
- Nếu không cần HTTP, bạn có thể dùng một ứng dụng Boot non-web chỉ có `spring-boot-starter-rsocket` và standalone TCP RSocket port.

TCP thường phù hợp service-to-service trong hạ tầng cho phép raw TCP, nhưng cần cấu hình firewall, TLS/mTLS, load balancing và client health riêng.

## 5. WebSocket transport: handshake HTTP, frames RSocket

~~~text
RSocketRequester
  |
  | GET /rsocket HTTP/1.1
  | Upgrade: websocket
  v
Reactor Netty WebFlux :8080
  |
  | HTTP 101 Switching Protocols
  | WebSocket binary frames chứa RSocket SETUP
  | Sau SETUP: request-response / request-stream / channel ...
  v
Spring RSocketMessageHandler
  |
  '--> @MessageMapping("greet")
~~~

Hai bước **độc lập**:

1. **HTTP WebSocket handshake**: transport mở thành công. Status `101` không chứng minh RSocket đã sẵn sàng.
2. **RSocket SETUP**: thống nhất MIME settings, keepalive và những điều kiện kết nối; sau đó mới gửi RSocket request frames, route metadata và payload.

`ws://` là WebSocket cleartext; `wss://` dùng TLS. Browser native WebSocket **không** tự biết mã hóa RSocket frames. Với browser phải có thư viện RSocket/WS tương thích; lab dùng Spring Java `RSocketRequester` cho kết quả rõ ràng.

**HTTP/2 lưu ý:** đa số ví dụ WebSocket dùng HTTP/1.1 Upgrade. WebSocket over HTTP/2 có RFC 8441 extended CONNECT và đòi hỏi hỗ trợ từng lớp. Đừng giả định browser sử dụng h2 cho HTTP page thì mọi WebSocket/RSocket chặng cũng h2.

## 6. Điều kiện ghép RSocket vào web server theo Spring Boot 3.3

Spring Boot cung cấp RSocket auto-configuration qua `spring-boot-starter-rsocket`. Hai kiểu tổ chức server:

- **Independent RSocket server:** khai báo `spring.rsocket.server.port`, có RSocket server độc lập (transport TCP hoặc WebSocket).
- **Integrated RSocket WebSocket server:** ghép vào Reactor Netty WebFlux web listener với cấu hình riêng.

Để **integrated/shared-port**, tất cả điều kiện sau phải đúng:

1. Ứng dụng thực sự là `WebApplicationType.REACTIVE`/Spring WebFlux.
2. Embedded web server thực là **Reactor Netty**.
3. Có dependency `spring-boot-starter-rsocket` cùng WebFlux.
4. `spring.rsocket.server.transport=websocket`.
5. `spring.rsocket.server.mapping-path=/rsocket` (hoặc path hợp lệ khác).
6. **Không khai báo `spring.rsocket.server.port`** để yêu cầu RSocket listener riêng.
7. Web listener hoạt động ở `server.port`; network/proxy/security cho phép WS upgrade tới mapping path.

Cấu hình tối thiểu để chia sẻ HTTP port:

~~~properties
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket

# Không đặt spring.rsocket.server.port.
~~~

Khi đủ điều kiện:

~~~text
HTTP GET http://localhost:8080/http/ping
RSocket WS ws://localhost:8080/rsocket
      \_______________________/
           cùng port 8080
~~~

**Quan trọng:** Spring Boot docs quy định tích hợp này **chỉ hỗ trợ Reactor Netty**. Tomcat/Servlet MVC có thể hỗ trợ WebSocket thuần và STOMP, nhưng không vì thế mà Boot tự cắm RSocket WebSocket vào cùng Tomcat listener. Nếu app có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot 3.3 thường chọn **SERVLET**, không phải REACTIVE. Phải kiểm tra application type và web server thực tế.

## 7. Bảng lựa chọn topology

| Runtime và cấu hình | HTTP listener | RSocket | Kết luận |
| --- | --- | --- | --- |
| WebFlux/Reactor Netty + WS + mapping-path, không port RSocket | `server.port` | WS trên chính HTTP port | **Chia sẻ embedded listener** |
| WebFlux/Reactor Netty + TCP + port=9898 | `server.port` | TCP :9898 | Hai listeners |
| WebFlux/Reactor Netty + WS + port=9898 | `server.port` | Standalone WS :9898 | Hai listeners |
| Servlet MVC/Tomcat + TCP + port=9898 | Tomcat HTTP | TCP :9898 | RSocket độc lập, không shared |
| Servlet MVC/Tomcat + WS + mapping-path, không RSocket port | Tomcat HTTP | Không có tích hợp shared-port Boot hỗ trợ | Đừng kỳ vọng tự hoạt động |
| Non-web Boot + TCP + port=9898 | Không có HTTP | TCP :9898 | RSocket-only process |
| WebFlux + transport=WS, thiếu mapping-path và port | HTTP nếu web starter có | Không yêu cầu listener RSocket đủ điều kiện | Có starter chưa đủ |

**Phân biệt “cùng JVM”, “cùng backend listener” và “cùng public port”:** ba khái niệm khác nhau. Hai listeners trong JVM có thể được reverse proxy/ingress gom vào một public `:443`, nhưng đó là chia sẻ **ở edge**, không phải shared Reactor Netty embedded server.

### 7.1. Bốn properties dễ nhầm

| Property | Nghĩa | Có tác dụng đối với? |
| --- | --- | --- |
| `server.port` | HTTP web server port | WebFlux/MVC listener |
| `spring.rsocket.server.port` | RSocket standalone port | TCP hoặc independent WS |
| `spring.rsocket.server.transport` | `tcp` hoặc `websocket` (mặc định tcp) | RSocket wire transport |
| `spring.rsocket.server.mapping-path` | HTTP WebSocket upgrade path | Integrated WebFlux WS topology |

`spring.rsocket.server.address` chọn bind address của standalone RSocket listener, khác với `server.address` của web listener. Khi shared-port, web listener network binding phụ thuộc `server.address`.

## 8. Lab: Java 17, Spring Boot 3.3.5, chạy TCP và WS từ cùng code

Chúng ta sẽ tạo một ứng dụng có ba profiles:

- `tcp`: WebFlux HTTP trên `127.0.0.1:8080` và RSocket **TCP riêng** trên `127.0.0.1:9898`.
- `ws`: WebFlux HTTP trên `127.0.0.1:8080` và RSocket **WS cùng cổng** tại `/rsocket`.
- `client`: Spring application **non-web** dùng `RSocketRequester` kiểm chứng cả bốn interaction models. Client chạy **process riêng** và không mở listener.

Không cần database, Docker hay broker. Chỉ cần Maven 3.x, JDK 17+ và các Spring dependencies do Boot starter parent quản lý. Bài dùng text payload có định dạng rõ để dễ quan sát.

### 8.1. Cấu trúc project

~~~text
rsocket-transport-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/rsocketlab/
    │   ├── RSocketTransportLabApplication.java
    │   ├── HttpProbeController.java
    │   ├── DemoRSocketController.java
    │   └── RSocketDemoClientRunner.java
    └── resources/
        ├── application.properties
        ├── application-tcp.properties
        ├── application-ws.properties
        └── application-client.properties
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rsocket-transport-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-webflux` cung cấp reactive web server dùng Reactor Netty mặc định; `spring-boot-starter-rsocket` cung cấp RSocket Java, Spring messaging codecs và requester/responder. **Không** thêm `spring-boot-starter-web` của Servlet MVC vào project lab shared-port này.

### 8.3. Spring Boot main

**`src/main/java/com/example/rsocketlab/RSocketTransportLabApplication.java`:**

~~~java
package com.example.rsocketlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketTransportLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketTransportLabApplication.class, args);
    }
}
~~~

### 8.4. HTTP controller để kiểm chứng server.port

**`src/main/java/com/example/rsocketlab/HttpProbeController.java`:**

~~~java
package com.example.rsocketlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HttpProbeController {

    @GetMapping("/http/ping")
    public Mono<String> ping() {
        return Mono.just("HTTP OK");
    }
}
~~~

Đây là **HTTP endpoint** dùng WebFlux, khác với RSocket route. Nó chạy ở web listener `server.port=8080` trong cả hai server profiles.

### 8.5. RSocket responder đầy đủ

**`src/main/java/com/example/rsocketlab/DemoRSocketController.java`:**

~~~java
package com.example.rsocketlab;

import java.time.Duration;
import java.util.Locale;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    // Request-response: một yêu cầu và một kết quả.
    @MessageMapping("greet")
    public Mono<String> greet(String name) {
        return Mono.just("Xin chào, " + name + "!");
    }

    // Request-stream: kết quả gồm đúng 3 items.
    @MessageMapping("ticks")
    public Flux<String> ticks(String name) {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(150))
                .map(n -> "event-" + n + ":" + name);
    }

    // Request-channel: nhận Flux, trả Flux.
    @MessageMapping("upper")
    public Flux<String> upper(Flux<String> values) {
        return values.map(v -> v.toUpperCase(Locale.ROOT));
    }

    // Fire-and-forget: không trả response nghiệp vụ.
    @MessageMapping("notify")
    public Mono<Void> notify(String message) {
        System.out.println("SERVER NOTIFY: " + message);
        return Mono.empty();
    }
}
~~~

**Giải thích:**

- `@MessageMapping` ở đây thuộc **RSocket responder**; route là metadata `greet`, `ticks`, `upper` hoặc `notify`, không tạo HTTP GET endpoints.
- `Mono<String>` là request-response, `Flux<String>` là request-stream/channel tùy inbound payload type.
- `Flux.range(1,3)` luôn tạo ba items có thứ tự; `delayElements` giúp quan sát stream.
- `notify` chỉ in ra console, không có durable queue. Client `send()` thành công không bảo đảm handler đã commit một transaction thực.
- `upper` nhận stream request payloads và map thành uppercase theo `Locale.ROOT`.
- Code không dùng blocking DB, `Thread.sleep` hoặc `block()` bên trong reactive responder; với các tác vụ blocking thực, cần thread scheduling/architecture phù hợp.

### 8.6. Properties dùng chung

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=rsocket-transport-lab
server.port=8080

# Không đặt spring.rsocket.server.port ở file chung:
# mỗi profile sẽ chọn mô hình riêng.
~~~

### 8.7. TCP profile: 2 listeners

**`src/main/resources/application-tcp.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=9898

# TCP transport không dùng mapping-path.
~~~

Khi chạy profile `tcp`, HTTP ở 8080 và RSocket TCP ở 9898. Không suy ra RSocket TCP 9898 được TLS bảo vệ nếu mới chỉ cấu hình HTTP `server.ssl.*`.

### 8.8. WebSocket profile: shared port

**`src/main/resources/application-ws.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket

# BẮT BUỘC không khai báo spring.rsocket.server.port.
~~~

Đây là cấu hình minh họa chuẩn để ghép RSocket-over-WebSocket vào Reactor Netty WebFlux server. HTTP `/http/ping` và RSocket WS `/rsocket` ở cùng cổng 8080.

### 8.9. Client profile không mở web server

**`src/main/resources/application-client.properties`:**

~~~properties
spring.main.web-application-type=none

app.client.transport=tcp
app.client.host=127.0.0.1
app.client.port=9898
app.client.ws-url=ws://127.0.0.1:8080/rsocket
~~~

`web-application-type=none` làm app client không khởi động embedded HTTP web listener. File không khai báo RSocket server port, vì process này là **requester** chứ không mở RSocket listener. Chạy client với profile `client` không phải mở thêm port 8080/9898.

### 8.10. RSocketRequester client dùng chung cho TCP/WS

**`src/main/java/com/example/rsocketlab/RSocketDemoClientRunner.java`:**

~~~java
package com.example.rsocketlab;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

@Component
@Profile("client")
public class RSocketDemoClientRunner implements ApplicationRunner {

    private final RSocketRequester.Builder builder;
    private final String transport;
    private final String host;
    private final int port;
    private final URI wsUri;

    public RSocketDemoClientRunner(
            RSocketRequester.Builder builder,
            @Value("${app.client.transport:tcp}") String transport,
            @Value("${app.client.host:127.0.0.1}") String host,
            @Value("${app.client.port:9898}") int port,
            @Value("${app.client.ws-url:ws://127.0.0.1:8080/rsocket}")
            URI wsUri) {
        this.builder = builder;
        this.transport = transport;
        this.host = host;
        this.port = port;
        this.wsUri = wsUri;
    }

    @Override
    public void run(ApplicationArguments args) {
        RSocketRequester.Builder configured =
                builder.dataMimeType(MimeTypeUtils.TEXT_PLAIN);

        RSocketRequester requester;
        if ("tcp".equalsIgnoreCase(transport)) {
            requester = configured.tcp(host, port);
        } else if ("websocket".equalsIgnoreCase(transport)) {
            requester = configured.websocket(wsUri);
        } else {
            throw new IllegalArgumentException(
                    "Unsupported transport: " + transport);
        }

        String greeting = requester.route("greet")
                .data("Lan")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_RESPONSE: " + greeting);

        List<String> ticks = requester.route("ticks")
                .data("Lan")
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_STREAM: " + ticks);

        List<String> uppercase = requester.route("upper")
                .data(Flux.just("one", "two"), String.class)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_CHANNEL: " + uppercase);

        requester.route("notify")
                .data("client says hi")
                .send()
                .block(Duration.ofSeconds(5));
        System.out.println("FIRE_AND_FORGET: send completed");
    }
}
~~~

**Giải thích code client:**

1. `@Profile("client")` làm runner chỉ thực thi ở client profile; server profiles không tự gửi requests kiểm thử.
2. Spring Boot auto-configure `RSocketRequester.Builder`; constructor injection cấp builder để thiết lập transport và codecs.
3. `dataMimeType(MimeTypeUtils.TEXT_PLAIN)` xác định String payload là text/plain, không phụ thuộc vào HTTP Content-Type ở handshake.
4. `.tcp(host, port)` và `.websocket(wsUri)` là hai API tạo requester đúng cho Spring Framework 6.1. Requester có thể **kết nối lazy** khi có request được subscribe, không phải tạo object là đủ xác nhận server sống.
5. `retrieveMono` nhận một item, `retrieveFlux` nhận stream; `.data(Flux.just(...), String.class)` gửi stream cho request-channel.
6. `block(Duration.ofSeconds(5))` chỉ được sử dụng trong CLI test **non-web**; không gọi `block()` trên Reactor Netty WebFlux event-loop thread.
7. `send()` với fire-and-forget báo hoàn tất việc gửi, không phải business acknowledgment.
8. Requester tái sử dụng kết nối theo cơ chế client library; nếu cần pool/load balancing/resume/auth/keepalive, phải cấu hình thêm.

## 9. Chạy bài thực hành ở TCP mode

Trong thư mục dự án:

~~~bash
mvn clean package
~~~

Mở **terminal A**:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=tcp
~~~

Trên Windows PowerShell có thể viết thành một dòng:

~~~powershell
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=tcp
~~~

Khi app chạy, kiểm tra HTTP từ **terminal B**:

~~~bash
curl -i http://127.0.0.1:8080/http/ping
~~~

Response thành công có HTTP 200 và body chính xác:

~~~text
HTTP OK
~~~

Sau đó chạy client profile:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client
~~~

Các dòng do runner in ra sau khi gọi thành công:

~~~text
REQUEST_RESPONSE: Xin chào, Lan!
REQUEST_STREAM: [event-1:Lan, event-2:Lan, event-3:Lan]
REQUEST_CHANNEL: [ONE, TWO]
FIRE_AND_FORGET: send completed
~~~

Ứng dụng Spring Boot cũng có startup logs; bốn dòng trên chỉ mô tả stdout **do client runner in**, không phải toàn bộ stdout cố định. Ở terminal A, handler `notify` có thể in:

~~~text
SERVER NOTIFY: client says hi
~~~

Hai kết nối được chứng minh độc lập: `HTTP 8080` và `RSocket TCP 9898`. Gọi `http://127.0.0.1:9898/http/ping` bằng curl **không** dùng HTTP web controller.

Để dừng server, nhấn `Ctrl+C` ở terminal A. Không chạy đồng thời hai instances cùng bind port 8080/9898.

## 10. Chạy WS mode dùng chung HTTP listener

Dừng server TCP và chạy:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=ws
~~~

HTTP route vẫn có:

~~~bash
curl -i http://127.0.0.1:8080/http/ping
~~~

RSocket client chuyển sang WebSocket trên **cùng web port 8080**:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client \
  --app.client.transport=websocket
~~~

Với project này, client WS URL mặc định là `ws://127.0.0.1:8080/rsocket`. Sau kết nối thành công, bốn dòng request-response, request-stream, channel và FNF **giữ nguyên kết quả** như TCP mode, vì responder/business logic giống nhau.

**Điểm cần kết luận từ kết quả:**

- HTTP `/http/ping` và RSocket WS `/rsocket` đang dùng **một embedded Reactor Netty port 8080**.
- Trong WS profile **không có** RSocket TCP 9898 do cấu hình này tạo.
- WebSocket handshake URL `/rsocket` **khác** RSocket route `greet`.
- Không cần rewrite Java `@MessageMapping` khi chuyển transport.

### 10.1. Đổi server.port trong WS mode

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=ws \
  --server.port=9080
~~~

Cả HTTP và RSocket WS shared đều chuyển sang `9080`:

~~~text
http://127.0.0.1:9080/http/ping
ws://127.0.0.1:9080/rsocket
~~~

Client tương ứng:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client \
  --app.client.transport=websocket \
  --app.client.ws-url=ws://127.0.0.1:9080/rsocket
~~~

Trong **TCP mode**, đổi `server.port` không tự thay `spring.rsocket.server.port` và ngược lại.

### 10.2. Vì sao curl GET /rsocket không phải test đúng?

~~~bash
curl http://127.0.0.1:8080/rsocket
curl http://127.0.0.1:8080/greet
~~~

Hai lệnh chỉ gửi HTTP GET thông thường; chúng **không gửi WebSocket Upgrade, RSocket SETUP và RSocket request frames**. HTTP error từ hai GET đó không chứng minh `@MessageMapping("greet")` sai.

Đoạn browser sau cũng **chưa** phải RSocket client:

~~~javascript
const socket = new WebSocket("ws://127.0.0.1:8080/rsocket");
socket.onopen = () => socket.send("hello");
~~~

WebSocket mở chưa đủ; `hello` text thuần không phải RSocket frame. Browser cần một RSocket-JavaScript implementation tương thích, codec/metadata/SETUP đúng.

## 11. YAML tương đương cho các topology

### 11.1. Shared WS + WebFlux + Reactor Netty

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      # Không có port RSocket độc lập
~~~

### 11.2. Hai listeners: HTTP + TCP RSocket

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

### 11.3. Non-web RSocket-only

~~~yaml
spring:
  main:
    web-application-type: none
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

Đối với RSocket-only, `spring-boot-starter-rsocket` và annotated responder thích hợp là phần chính; không cần web server. RSocket standalone có thể được chạy trong một ứng dụng Spring Boot không phải WebFlux HTTP server nếu đúng auto-configuration.

### 11.4. Standalone RSocket-over-WebSocket

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.port=9898
~~~

Đây là WebSocket RSocket **cổng riêng**, không phải chia sẻ `server.port`. Có `mapping-path` trong file khác không biến nó thành integrated listener khi đã khai báo cổng standalone. Để kiểm tra path thực tế của standalone implementation, dùng RSocket client/transport phù hợp với version và server config, thay vì giả định path `/rsocket` của chế độ WebFlux shared.

## 12. RSocket route, data và metadata MIME types

Một request RSocket có:

- **Route**: xác định handler, ví dụ `greet`, được gửi trong routing metadata.
- **Data payload**: dữ liệu nghiệp vụ như chuỗi `Lan` hoặc record JSON.
- **Metadata**: route, authentication, tracing… tùy negotiated metadata MIME type.
- **Stream ID** và frame type: phục vụ multiplexing và interaction semantics.

`@MessageMapping("greet")` không phải HTTP `@GetMapping("/greet")`. Đổi TCP sang WS chỉ thay **transport/handshake**, không thay định nghĩa route.

Spring Boot auto-configures `RSocketStrategies` với codecs; theo tài liệu Boot 3.3, framework có thể ưu tiên CBOR, rồi JSON nếu dependency tương ứng sẵn. Khi dùng String-only như lab, `MimeTypeUtils.TEXT_PLAIN` giúp codec dễ xác định.

Ví dụ RSocket request-response:

~~~java
Mono<String> result = requester.route("greet")
        .data("Lan")
        .retrieveMono(String.class);
~~~

Đây là **snippet trong phương thức có `requester`**, không phải class Java độc lập. `result` là Mono; network exchange diễn ra khi được subscribe.

Ví dụ sử dụng JSON record **chỉ mang tính minh họa**:

~~~java
public record ProductView(String id, String name) {}

// Gửi/nhận khi đã cấu hình cùng JSON/CBOR MIME và codecs:
// Mono<ProductView> p = requester.route("product.find")
//       .data("42").retrieveMono(ProductView.class);
~~~

Không lấy HTTP `Content-Type` của WebSocket handshake làm cơ chế serialization cho mọi RSocket message. RSocket có negotiated data/metadata MIME riêng qua SETUP.

## 13. TLS của shared WS và standalone TCP không tự đồng nhất

### 13.1. Bốn trường hợp

~~~text
TCP không TLS:
  requester ===== TCP cleartext ===== :9898

TCP với TLS:
  requester ===== TLS/TCP ============ :9898

WebSocket không TLS:
  requester ===== ws:// ============== :8080/rsocket

WebSocket có TLS:
  requester ===== wss:// ============= :8443/rsocket
~~~

Nếu RSocket WS **dùng chung** Reactor Netty web server, TLS cho cổng HTTP/WSS đến từ cấu hình web TLS như `server.ssl.*` và certificate của embedded web server. Khi có **RSocket TCP port độc lập**, TLS phải được cấu hình và kiểm tra **cho RSocket server**; Spring Boot 3.3 có nhóm `spring.rsocket.server.ssl.*` và `spring.rsocket.server.ssl.bundle` riêng.

Ví dụ minh họa web TLS + RSocket shared WS:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/etc/app/tls/web.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}

spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

Đoạn này phụ thuộc certificate/keystore có sẵn và secret environment; nó **không phải lab chạy ngay** trên localhost. Client sẽ dùng `wss://.../rsocket` và phải xác minh CA/hostname. Đừng dùng trust-all certificate manager hay tắt TLS verification trong production.

**Không suy ra:** Bật `server.ssl.enabled=true` trên web port 8443 thì RSocket TCP listener 9898 đã có TLS. Mỗi listener có identity/trust và network policy riêng.

### 13.2. HTTP security và RSocket security là hai lớp

- HTTP filter chain có thể bảo vệ HTTP endpoints và WebSocket handshake nếu shared transport đi qua web server.
- RSocket SETUP/metadata/routes có thể cần xác thực và phân quyền riêng. Spring Security có tích hợp `RSocketSecurity` và socket acceptor/payload interceptors.
- Không mặc định rằng `authorizeHttpRequests()` hoặc `authorizeExchange()` bao phủ mọi RSocket frames, nhất là TCP listener riêng không đi qua HTTP.
- Kiểm tra authentication trên connection/setup và authorization theo route, tenant, data scope.
- WebSocket Origin header có ích cho policy browser, nhưng **không phải authentication**; clients ngoài browser có thể giả Origin.
- Giới hạn message sizes, rate, concurrent streams và payload validation để chống lạm dụng.

## 14. Proxy/Ingress, một public port và hai listeners

### 14.1. NGINX WebSocket upgrade

Trong shared WS topology, reverse proxy phải chuyển `/rsocket` thành WebSocket upgrade hợp lệ. Ví dụ directive cốt lõi:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    # Cần ssl_certificate và ssl_certificate_key thực tế.

    location /rsocket {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

Đây là **snippet kiến trúc**, chưa phải NGINX production config hoàn chỉnh vì thiếu certificate và security controls. Public client gọi `wss://api.example.com/rsocket`, proxy terminate TLS ở edge và chuyển upgrade đến `ws://127.0.0.1:8080/rsocket`. Nếu chính sách yêu cầu mã hóa chặng proxy→backend, cấu hình TLS/re-encryption thích hợp thay vì HTTP thuần.

**RSocket TCP không được HTTP `location` proxy_pass route theo `/rsocket`**, vì nó không có HTTP URL/path. Phải dùng L4 TCP proxy/load balancer hoặc RSocket-aware gateway.

### 14.2. Public port chung khác embedded port chung

~~~text
Case A — embedded shared:
  HTTP client -----\
                    --> Reactor Netty :8080
  RSocket WS ------/       /http/ping và /rsocket

Case B — chỉ public edge chung:
  Client --> NGINX :443
               |--> MVC HTTP :8080
               '--> RSocket WS standalone :9898
~~~

Ở case B, browser có thể chỉ thấy một port 443, nhưng backend có hai listeners. **Không được nói Tomcat đã chia sẻ embedded RSocket web port** chỉ vì NGINX route hai upstream về cùng public endpoint.

### 14.3. Multi-instance, long-lived connections và state

RSocket connections kéo dài thường được gắn với một backend pod trong suốt thời gian sống. Khi pod restart, client phải reconnect; reconnection có thể chọn replica khác. Session state, stream progress, in-memory subscriptions và side effects **không tự** di chuyển theo connection. Nếu cần durability/replay, thiết kế lưu offset/cursor, outbox, persistence hoặc resumption với sự hỗ trợ thực tế của protocol/implementation.

## 15. Backpressure, cancellation, timeout và tài nguyên

**REQUEST_N/demand** của RSocket giúp điều tiết lượng messages mà requester sẵn sàng nhận. Một responder dùng `Flux` nên tôn trọng cancellation và giữ nguồn dữ liệu không blocking. Tuy nhiên:

- Backpressure không làm mất yêu cầu giới hạn RAM, buffers, message size hoặc slow consumers.
- `Flux.interval`/telemetry stream dài cần chính sách cancel khi client disconnected.
- Khi user hủy stream, công việc side effect đã commit không tự rollback.
- Fire-and-forget không có business response; muốn biết kết quả, phải thiết kế xác nhận độc lập.
- Timeout có nhiều lớp: TCP connect, TLS handshake, WebSocket handshake, RSocket SETUP, per-route response, keepalive và proxy idle timeout.
- Client reconnect storm có thể làm server suy yếu thêm; dùng backoff/jitter, giới hạn attempts và concurrency.
- Protocol hỗ trợ resumption/leases ở mức tính năng, **không có nghĩa Boot tự bật hoàn chỉnh** hay mọi business messages được replay.

Ví dụ timeout trong reactive service:

~~~java
// Đoạn trong method đã có requester:
Mono<String> greeting = requester.route("greet")
        .data("Lan")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

Đây không phải file Java độc lập. `timeout` phát error khi vượt hạn; project production cần map lỗi theo business contract, không mặc định trả fallback thành công cho giao dịch quan trọng.

**Đừng dùng `Thread.sleep`/`block()` trên Reactor Netty event loop**. Trong CLI client lab, `block(Duration)` được dùng có chủ đích ngoài server event loop.

## 16. So sánh RSocket với REST, SSE, raw WebSocket và STOMP

| Công nghệ | Tầng / kiểu | Điểm mạnh | Khi không phù hợp |
| --- | --- | --- | --- |
| HTTP REST | HTTP request-response | Hệ sinh thái lớn, cache/proxy/browser-friendly | Streaming full-duplex phức tạp |
| SSE | HTTP server→client stream | Browser EventSource, thông báo một chiều | Cần client→server streams hai chiều |
| Raw WebSocket | WS transport và app protocol tùy biến | Linh hoạt text/binary, full-duplex | Muốn built-in routing/backpressure kiểu RSocket |
| STOMP-over-WebSocket | WS + STOMP text messaging/broker | Topic subscription, Spring MVC STOMP integration | Client không dùng STOMP hoặc cần RSocket interaction semantics |
| **RSocket TCP** | RSocket binary/TCP | Service-to-service, four interactions, backpressure | Hạ tầng không cho raw TCP port |
| **RSocket WebSocket** | RSocket binary/WS | Dễ đi qua WS-capable edge, WebFlux shared-port | Không có RSocket client library hoặc proxy không upgrade |
| gRPC | RPC phổ biến trên HTTP/2 | Schema protobuf/tooling, unary/streaming | Khi client/proxy target không đáp ứng HTTP/2/gRPC |

Chọn RSocket khi có nhu cầu thật về **streaming, bidirectional interactions, demand/cancellation** và client ecosystem hỗ trợ. Không chỉ chọn vì “WebSocket mới hơn HTTP” hoặc “RSocket chắc chắn nhanh hơn gRPC”. Cần đo CPU, networking, latency, resource budgets và maintainability.

## 17. Quy trình chẩn đoán từng lỗi

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| RSocket TCP connect refused | Port 9898 chưa nghe, firewall hoặc profile sai | Kiểm tra process/listener, config `spring.rsocket.server.port` |
| HTTP 8080 chạy nhưng RSocket không | Web starter hoạt động không đồng nghĩa RSocket transport có listener | So profile, transport, mapping-path/port |
| WS handshake 404 | Sai `/rsocket`, proxy rewrite, RSocket route nhầm URL | Kiểm tra mapping-path và actual WS URL |
| WS handshake không có HTTP 101 | Proxy không Upgrade, TLS/Origin/auth lỗi | Xem Network WS, reverse proxy logs |
| WS đã OPEN nhưng RSocket request lỗi | Chưa gửi RSocket SETUP, unsupported MIME, frame invalid | Dùng RSocketRequester, xem RSocket logs |
| HTTP GET /rsocket trả error | GET không phải RSocket WS upgrade | Thử client RSocket thật |
| Route greet không được xử lý | Nhầm `@GetMapping` với `@MessageMapping`, route metadata sai | So `requester.route` và handler |
| MVC/Tomcat không có RSocket WS shared path | Không đúng điều kiện Reactor Netty/REACTIVE | Chuyển WebFlux/Netty hoặc RSocket standalone |
| Có cả starter-web và starter-webflux | Boot ưu tiên Servlet MVC | Xem dependency tree và web application type |
| Đặt mapping-path và port nhưng không shared | RSocket port yêu cầu standalone server | Bỏ RSocket port khi muốn shared WebFlux |
| TLS web chạy nhưng TCP RSocket chưa mã hóa | SSL config hai listeners khác nhau | Cấu hình `spring.rsocket.server.ssl.*` |
| Stream chậm hoặc timeout | Demand/backpressure, upstream, Netty event loop hoặc proxy idle | Xem stream metrics, timeout layers |
| RSocket connection mất khi deploy | Pod restart, long-lived connection | Reconnect/backoff, state and replay strategy |
| Tải cao dẫn đến OOM | Không giới hạn payloads, buffers, concurrent streams | Set resource limits, metrics, load tests |
| Client chỉ dùng STOMP.js | Nhầm STOMP with RSocket | Dùng RSocket protocol client |
| FNF sent nhưng server không ghi nhận | Network/handler failure, không có ACK nghiệp vụ | Dùng request-response/receipt khi cần xác nhận |

### 17.1. Checklist debug từng tầng

1. **Ứng dụng**: web application type thực là REACTIVE/SERVLET/NONE; web server Netty hay Tomcat?
2. **Transport**: TCP hay WS, có dedicated RSocket port không?
3. **Network**: đúng DNS/host/port, firewall, ingress, TLS/SNI/certificate chưa?
4. **Handshake**: TCP connection, HTTP WS Upgrade 101 nếu WS, RSocket SETUP thực sự thành công chưa?
5. **Routing**: metadata route và `@MessageMapping` đúng? RSocket codecs tương thích?
6. **Interaction**: Request-response, stream, channel hay FNF? Có backpressure/cancellation không?
7. **Production**: metrics/errors, retry storm, memory buffers, proxy idle timeouts, multi-instance behavior?

Nếu không biết lỗi ở tầng nào, trước hết thử lab local trực tiếp, rồi thêm proxy/TLS/balancer từng lớp để tìm chính xác điểm sai.

## 18. Lỗi tư duy thường gặp

1. **“RSocket qua TCP chính là WebSocket.”** Không: TCP và WebSocket là hai transports khác.
2. **“server.port=8080 là RSocket port.”** Không: đó là web listener.
3. **“WebFlux nghĩa mọi RSocket tự shared-port.”** Không: còn cần WS transport, mapping path, không dedicated RSocket port.
4. **“Có WebSocket trên Tomcat là Boot tích hợp RSocket WS vào Tomcat.”** Không theo documented shared-port auto-config.
5. **“Một process nghĩa là một socket.”** Không: web :8080 và RSocket TCP :9898 có thể tồn tại cùng JVM.
6. **“Cùng public :443 nghĩa là cùng embedded server.”** Không: proxy có thể route tới nhiều backends.
7. **“WS handshake 101 nghĩa là RSocket SETUP thành công.”** Không: RSocket frames là giai đoạn sau.
8. **“RSocket route greet là HTTP GET /greet.”** Không: đó là metadata route.
9. **“RSocket có backpressure thì chắc chắn không mất messages.”** Không: persistence/replay vẫn là thiết kế riêng.
10. **“Fire-and-forget hoàn thành nghĩa là business đã xử lý xong.”** Không.
11. **“server.ssl bảo vệ luôn RSocket TCP port riêng.”** Không tự động.
12. **“WebSocket native browser tự nói được RSocket.”** Không: cần RSocket protocol client.
13. **“@MessageMapping ở RSocket và STOMP là một broker.”** Không: cùng annotation name nhưng handlers/wire protocols khác.
14. **“Block() trong reactive server là vô hại.”** Không: có nguy cơ chặn event loop.

## 19. Bài tập tự kiểm tra

**Câu 1.** RSocket và WebSocket khác nhau ở lớp giao thức nào?

**Câu 2.** Nêu đầy đủ điều kiện để WebFlux Spring Boot 3.3 host RSocket WS trên cùng HTTP listener.

**Câu 3.** Tại sao `server.port=8080` và `spring.rsocket.server.port=9898` không có nghĩa một cổng chung?

**Câu 4.** Ứng dụng Spring MVC/Tomcat có thể đạt một public port cho HTTP và RSocket bằng cách nào mà không đồng nghĩa shared embedded server?

**Câu 5.** Trong lab, `/http/ping`, `/rsocket` và `greet` khác nhau như thế nào?

**Câu 6.** Client gọi `GET /rsocket` nhưng bị 404/400; tại sao chưa đủ để nói RSocket responder sai?

**Câu 7.** Khi server profile `ws` hoạt động, liệu RSocket TCP 9898 tự mở không?

**Câu 8.** RSocket request-stream điều tiết messages bằng cơ chế gì? Nó có tự lưu message khi client offline không?

**Câu 9.** Có cần bật TLS riêng cho TCP RSocket port khi HTTP listener đã HTTPS không?

**Câu 10.** Vì sao Spring Boot client profile không mở listener nhưng vẫn có thể gọi route RSocket?

**Câu 11.** Một request-channel có thể nhận `Flux<String>` và trả `Flux<String>` không? Việc đó khác raw WebSocket thế nào?

**Câu 12.** Fire-and-forget có đáp ứng yêu cầu “chỉ báo thành công sau khi DB commit” không?

**Đáp án gợi ý:**

1. RSocket là protocol messaging nhị phân; WebSocket là một transport có handshake/frames.
2. WebApplicationType.REACTIVE, embedded Reactor Netty, starter-rsocket + webflux, `transport=websocket`, `mapping-path`, không RSocket port riêng, web listener hoạt động.
3. Hai properties điều khiển hai listeners khác nhau.
4. Dùng reverse proxy/ingress route public WS path tới RSocket standalone backend, hoặc đổi app sang WebFlux/Netty.
5. `/http/ping` là HTTP route; `/rsocket` là WebSocket handshake path; `greet` là RSocket metadata route.
6. GET thường không gửi WS upgrade/RSocket SETUP/REQUEST_RESPONSE.
7. Không; profile `ws` không cấu hình TCP 9898.
8. RSocket demand/REQUEST_N; không tự có durable replay.
9. Có, phải kiểm chứng cấu hình RSocket SSL độc lập.
10. Client profile dùng `RSocketRequester` outbound, không cần inbound server port.
11. Có, request-channel hỗ trợ flow control theo RSocket protocol; raw WS cần app protocol tự quản lý.
12. Không, cần request-response/ack nghiệp vụ hoặc durable workflow.

## 20. Checklist triển khai thực tế

- [ ] Xác định đúng mục tiêu: standalone TCP, standalone WS, shared WS trên Netty hay edge proxy chung.
- [ ] Xác minh Spring Boot web application type thực và embedded server (Reactor Netty/Tomcat).
- [ ] Đối với shared: REACTIVE + Reactor Netty + transport=websocket + mapping-path + **không RSocket port**.
- [ ] Đối với TCP: RSocket port riêng và service/network policy riêng.
- [ ] Phân biệt HTTP `server.port` và RSocket `spring.rsocket.server.port`.
- [ ] Dùng RSocket client có hỗ trợ SETUP, metadata, codecs, routes và interaction models.
- [ ] Có timeout, backpressure, cancellation và concurrent stream limits.
- [ ] Payload, frame sizes và codecs được giới hạn/kiểm tra rõ ràng.
- [ ] Với WSS, TLS certificate và proxy Upgrade/path đúng, Origin/auth policy phù hợp.
- [ ] Với TCP, TLS/mTLS và authorization RSocket riêng, không suy từ HTTP SSL.
- [ ] Không nhầm RSocket và STOMP/raw WS/HTTP SSE.
- [ ] Có backoff/jitter khi reconnect, không tạo reconnect storm.
- [ ] Khi nhiều replicas, có kế hoạch state/replay/resume và graceful shutdown.
- [ ] Có metrics/trace cho RSocket SETUP/errors/routes/connection/stream và web requests riêng.
- [ ] Test thành công, sai transport, sai MIME/route, timeout, proxy idle, restart và unauthorized access.

## 21. Tài liệu tham khảo

- Spring Boot 3.3 — RSocket server auto-configuration và WebFlux shared transport: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- Spring Boot 3.3 — Common Application Properties (spring.rsocket.server.*, server.*): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Framework — RSocket protocol, four interaction models, SETUP, metadata, @MessageMapping, requesters: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework 6.1 — RSocketRequester.Builder, tcp/websocket: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Boot 3.4 — RSocket reference (đối chiếu mô hình): https://docs.spring.io/spring-boot/3.4/reference/messaging/rsocket.html
- Spring Security — Reactive RSocket security: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- RSocket Protocol Specification: https://rsocket.io/about/protocol/
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- RFC 8441 — Bootstrapping WebSockets with HTTP/2: https://www.rfc-editor.org/rfc/rfc8441
