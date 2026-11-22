# HTTP/2 và điều kiện hỗ trợ của máy chủ, connector trong Spring WebFlux

## 1. Mục tiêu

Spring WebFlux cung cấp mô hình xử lý HTTP bất đồng bộ, non-blocking và reactive. Tuy nhiên, WebFlux không tự triển khai giao thức mạng ở tầng transport. Request thực tế được nhận và gửi bởi **server connector** hoặc **client connector** mà ứng dụng sử dụng.

Vì vậy, việc một controller trả về **Mono** hoặc **Flux** không có nghĩa request đã chạy bằng HTTP/2. Muốn dùng HTTP/2, cần kiểm tra đồng thời:

- Server hoặc client connector có hỗ trợ HTTP/2 không.
- Phiên bản Spring Boot, Spring Framework và thư viện connector có tương thích không.
- TLS/ALPN đã được cấu hình đúng nếu dùng HTTP/2 qua HTTPS.
- Proxy, ingress, load balancer và client ở từng chặng có hỗ trợ protocol tương ứng không.
- Client thực sự thương lượng thành công HTTP/2 thay vì fallback về HTTP/1.1.

Bài học này trình bày HTTP/2 ở mức cần thiết để triển khai WebFlux, cách bật ở server bằng Spring Boot, điều kiện của Reactor Netty/Tomcat/Jetty/Undertow, cách cấu hình WebClient, cách kiểm tra protocol trên đường truyền và những giới hạn vận hành cần theo dõi.

Ví dụ dùng Java 17+, Spring Boot 3.5.x hoặc 4.1.x tương thích. Tên dependency và khả năng của embedded server có thể thay đổi giữa các thế hệ Boot; luôn đối chiếu đúng release đang dùng.

## 2. HTTP/2 là gì?

HTTP/2 là phiên bản giao thức HTTP được chuẩn hóa trong RFC 9113. Nó giữ semantics HTTP như method, status code, headers và body, nhưng thay đổi cách biểu diễn và truyền thông điệp trên kết nối.

HTTP/2 đưa vào các đặc điểm chính:

- **Binary framing:** dữ liệu được chia thành các frame có cấu trúc nhị phân thay cho cú pháp text của HTTP/1.1.
- **Streams:** mỗi request/response exchange được gắn với một stream có ID riêng.
- **Multiplexing:** nhiều stream có thể truyền xen kẽ trên cùng một kết nối TCP.
- **Header compression:** HPACK nén các field header để giảm dữ liệu lặp lại.
- **Flow control:** kiểm soát lượng dữ liệu được gửi trên từng stream và trên toàn connection.
- **Connection reuse:** một kết nối có thể phục vụ nhiều request đồng thời, giảm nhu cầu mở nhiều TCP/TLS connections.

HTTP/2 vẫn mang semantics của HTTP. Controller WebFlux vẫn dùng @GetMapping, @PostMapping, ResponseEntity, Mono và Flux như trước. Việc thay đổi nằm ở connector và cấu hình transport, không yêu cầu viết controller riêng cho HTTP/2.

### 2.1. So sánh HTTP/1.1 và HTTP/2

| Đặc điểm | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Biểu diễn thông điệp | Text-based | Binary frames |
| Request đồng thời trên một connection | Thường cần nhiều connection; pipelining ít được dùng | Nhiều stream multiplex trên một connection |
| Header | Gửi lại nhiều field lặp lại | HPACK header compression |
| Flow control | Chủ yếu ở tầng TCP | Có flow control ở connection và stream, bên cạnh TCP |
| Connection | Thường mở nhiều connection để tăng concurrency | Có thể chia sẻ một connection cho nhiều request |
| Framing body | Content-Length hoặc chunked transfer encoding | DATA frames và END_STREAM; không dùng HTTP/1.1 chunked encoding |
| Bảo mật trong trình duyệt | HTTP và HTTPS | HTTP/2 qua TLS |

HTTP/2 không làm thay đổi ý nghĩa của GET, POST, status code, Content-Type hay JSON. Nó thay đổi cách các message được đóng gói và multiplex qua kết nối.

### 2.2. Streams và multiplexing

Giả sử một WebClient cần gọi ba endpoint cùng host:

```text
HTTP/1.1:
Connection A -> request 1
Connection B -> request 2
Connection C -> request 3

HTTP/2:
Connection A
  Stream 1 -> request 1
  Stream 3 -> request 2
  Stream 5 -> request 3
```

Với HTTP/2, frame của nhiều stream có thể xen kẽ trên một TCP connection. Một response lớn không nhất thiết buộc các response nhỏ khác phải chờ hoàn tất ở tầng HTTP application. Điều này giúp giảm chi phí TCP/TLS handshake và sử dụng connection hiệu quả hơn.

Multiplexing không có nghĩa server xử lý mọi request song song vô hạn. Số stream đồng thời chịu ảnh hưởng của SETTINGS từ peer, giới hạn connector, connection pool, tài nguyên server và application concurrency.

### 2.3. Flow control và giới hạn TCP

HTTP/2 có hai lớp flow control:

- **Stream-level window:** giới hạn dữ liệu đang được gửi trên một stream.
- **Connection-level window:** giới hạn tổng dữ liệu đang được gửi trên connection.

Receiver có thể gửi WINDOW_UPDATE để cho phép sender tiếp tục truyền dữ liệu. Mục tiêu là không để sender đẩy quá nhiều dữ liệu vào receiver đang chậm.

Đây là flow control của protocol. Reactor Streams backpressure là cơ chế demand ở tầng ứng dụng. Connector cần phối hợp hai lớp này; không nên xem HTTP/2 flow control và Reactor backpressure là một cơ chế duy nhất.

Multiplexing loại bỏ một phần head-of-line blocking ở tầng HTTP/1.1, nhưng HTTP/2 vẫn chạy trên TCP. Nếu một TCP packet bị mất, các byte tiếp theo trên connection có thể phải chờ TCP retransmission trước khi các stream khác tiếp tục nhận dữ liệu. HTTP/2 không loại bỏ mọi dạng head-of-line blocking.

### 2.4. Header compression và framing

HTTP/2 dùng HPACK để nén header fields. Frame có thể mang HEADERS, DATA, SETTINGS, WINDOW_UPDATE, PING, RST_STREAM hoặc GOAWAY.

Một request HTTP/2 vẫn có status và headers tương đương HTTP/1.1, nhưng được biểu diễn bằng pseudo-header như :method, :scheme, :authority và :path.

HTTP/2 không dùng các header connection-specific của HTTP/1.1 như Connection, Keep-Alive, Proxy-Connection, Transfer-Encoding hoặc Upgrade. Proxy chuyển đổi giữa HTTP/2 và HTTP/1.1 phải xử lý đúng khác biệt này.

## 3. Hai cách thiết lập HTTP/2: h2 và h2c

HTTP/2 có hai dạng nhận diện phổ biến:

| Protocol identifier | Transport | Cách bắt đầu | Trường hợp dùng |
| --- | --- | --- | --- |
| h2 | TLS | TLS handshake và ALPN negotiation | HTTPS public, trình duyệt, API production |
| h2c | TCP cleartext | Prior knowledge; HTTP/1.1 Upgrade cũ đã bị RFC 9113 deprecate | Mạng nội bộ hoặc chặng sau proxy TLS termination khi được kiểm soát |

### 3.1. h2: HTTP/2 qua TLS

Khi client truy cập URL HTTPS, client và server thiết lập TLS. Trong TLS handshake, hai bên dùng **ALPN (Application-Layer Protocol Negotiation)** để thống nhất protocol ứng dụng.

Client có thể đề xuất các protocol như:

- h2: HTTP/2.
- http/1.1: HTTP/1.1.

Nếu server và client thống nhất h2, các request tiếp theo dùng HTTP/2. Nếu không, hai bên có thể dùng HTTP/1.1 nếu protocol đó cũng được hỗ trợ.

Điều kiện quan trọng:

- Có certificate và private key hợp lệ.
- Hostname trong certificate phù hợp với tên server mà client truy cập.
- TLS provider và connector hỗ trợ ALPN.
- Client và server cùng hỗ trợ HTTP/2.
- Proxy hoặc load balancer không làm mất protocol negotiation ở chặng đang được kiểm tra.

Java 17+ có ALPN support trong JDK. Với một số cấu hình hoặc runtime cũ, connector có thể cần thư viện native như Netty tcnative hoặc Conscrypt. Hãy kiểm tra hướng dẫn connector thay vì thêm native library một cách mặc định.

### 3.2. h2c: HTTP/2 không mã hóa

h2c chạy HTTP/2 trực tiếp trên TCP mà không có TLS. Client cần biết trước endpoint hỗ trợ h2c và có thể gửi connection preface theo cơ chế prior knowledge.

RFC 9113 deprecate việc nâng cấp HTTP/1.1 bằng header Upgrade: h2c vì cơ chế đó không được triển khai rộng rãi. Do vậy, khi kiểm thử h2c nên phân biệt:

- **Prior knowledge:** client đã biết endpoint hỗ trợ h2c và bắt đầu bằng HTTP/2 connection preface.
- **HTTP/1.1 Upgrade cũ:** cơ chế Upgrade token h2c đã bị deprecate trong RFC 9113.

h2c có thể hữu ích khi TLS đã được terminate tại proxy và proxy mở một kết nối HTTP/2 cleartext tới backend. Chỉ dùng trên mạng nội bộ được kiểm soát, có phân đoạn mạng và policy bảo mật phù hợp. Không xem h2c là thay thế TLS cho kết nối public.

### 3.3. HTTP/2 có TLS không đồng nghĩa end-to-end

Một request có thể đi qua nhiều chặng:

```text
Browser -- HTTPS / h2 --> Load balancer
Load balancer -- h2c --> WebFlux server
WebFlux server -- HTTP/1.1 --> Internal service
```

Trong sơ đồ này, client đã dùng HTTP/2 với load balancer. Chặng từ load balancer đến WebFlux cũng dùng h2c. Nhưng WebFlux gọi service tiếp theo bằng HTTP/1.1.

Protocol được thương lượng độc lập trên từng connection. Vì vậy, không thể chỉ nhìn vào browser hoặc một proxy rồi kết luận mọi chặng đều đang dùng HTTP/2.

## 4. Vai trò của WebFlux, server connector và client connector

Spring WebFlux xây dựng trên abstraction HTTP handler và các adapter cho server. Embedded server/connector thực hiện việc bind port, TLS, protocol negotiation, đọc frame, quản lý connection và ghi response.

### 4.1. Server-side

Các thành phần thường gặp:

- **HttpHandler:** contract xử lý HTTP non-blocking ở mức thấp.
- **HttpWebHandlerAdapter:** adapter kết nối WebHandler với HttpHandler.
- **Server adapter:** tích hợp HttpHandler với Reactor Netty, Tomcat, Jetty hoặc servlet container tương thích.
- **Embedded server:** thực sự mở socket, xử lý TLS/HTTP protocol và chuyển request vào WebFlux.

Spring Boot starter WebFlux mặc định dùng Reactor Netty. Có thể thay bằng Tomcat hoặc Jetty; Boot 3.5 còn hỗ trợ Undertow trong reactive stack. Khả năng HTTP/2 cụ thể phụ thuộc phiên bản server và các module/dependency cần thiết.

### 4.2. Client-side

WebClient cũng không tự mở socket. Nó dùng một ClientHttpConnector để gửi request và nhận response.

Các connector/client phổ biến:

- Reactor Netty.
- JDK HttpClient.
- Jetty Reactive HttpClient.
- Apache HttpComponents.

Spring Boot có thể tự chọn connector theo thư viện có trên classpath. Nếu cần protocol cụ thể, phải cấu hình underlying HTTP client tương ứng. Chỉ thêm spring-boot-starter-webflux không có nghĩa mọi WebClient request tự động chuyển sang HTTP/2.

### 4.3. Controller không cần biết protocol

Ví dụ controller:

```java
@RestController
@RequestMapping("/api")
public class HelloController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello over HTTP",
                "framework", "Spring WebFlux"));
    }
}
```

Controller này có thể được gọi bằng HTTP/1.1 hoặc HTTP/2 nếu server connector đã hỗ trợ và thương lượng thành công. Không cần tạo một method khác cho HTTP/2.

## 5. Điều kiện hỗ trợ theo server connector

Bảng dưới đây tổng hợp theo tài liệu Spring Boot 3.5 và 4.1. Đây là hướng dẫn chọn connector; hãy kiểm tra đúng version BOM và server dependency đang chạy.

| Server trong WebFlux | Boot 3.5 | Điều kiện HTTP/2 chính | Ghi chú |
| --- | --- | --- | --- |
| Reactor Netty | Có, là mặc định | Hỗ trợ h2 và h2c; h2 cần TLS/ALPN | Native tcnative có thể dùng để tối ưu TLS |
| Tomcat 10.1.x | Có | Hỗ trợ h2/h2c; kiểm tra native TLS support theo runtime | Boot 4.1 dùng Tomcat 11.x với hỗ trợ h2/h2c out of the box |
| Jetty | Có | Cần jetty-http2-server; h2 cần ALPN implementation | h2c không cần cùng bộ ALPN TLS |
| Undertow | Có trong Boot 3.5 reactive stack | Tài liệu Boot 3.5 ghi nhận h2 và h2c | Kiểm tra support khi nâng Boot major; Boot 4.1 reactive server list tập trung vào Reactor Netty, Tomcat và Jetty |

### 5.1. Reactor Netty

Đây là lựa chọn mặc định khi dùng spring-boot-starter-webflux. Reactor Netty hỗ trợ HTTP/2 qua TLS và h2c. Với h2, TLS phải được cấu hình; ALPN sẽ chọn h2 hoặc HTTP/1.1 theo khả năng hai bên.

Tài liệu Boot có đề cập thư viện:

```text
io.netty:netty-tcnative-boringssl-static
```

Thư viện này cung cấp native SSL implementation. Nó có thể cải thiện hiệu năng hoặc đáp ứng một số môi trường TLS cụ thể; không phải lúc nào cũng bắt buộc trên JDK mới có ALPN.

### 5.2. Tomcat

Tomcat có hỗ trợ HTTP/2 ở tầng connector. Khả năng cụ thể phụ thuộc nhánh Tomcat, JDK, TLS provider và native library.

- Boot 3.5 sử dụng Tomcat 10.1.x theo mặc định trong servlet stack; tài liệu Boot ghi nhận h2/h2c.
- Boot 4.1 sử dụng Tomcat 11.0.x và ghi nhận h2/h2c out of the box.
- libtcnative có thể được dùng để hỗ trợ/tối ưu TLS tùy môi trường.

Không chỉ kiểm tra annotation controller. Cần kiểm tra Tomcat HTTP connector, SSL host config, ALPN và dependency native nếu deployment yêu cầu.

### 5.3. Jetty

Jetty cần module server HTTP/2:

```text
org.eclipse.jetty.http2:jetty-http2-server
```

Để chạy h2c, Jetty không cần cùng bộ dependency ALPN TLS. Để chạy h2 qua TLS, cần ALPN implementation, ví dụ:

- org.eclipse.jetty:jetty-alpn-java-server để dùng hỗ trợ của JDK.
- org.eclipse.jetty:jetty-alpn-conscrypt-server cùng thư viện Conscrypt.

Khi dùng Spring Boot, ưu tiên dependency được quản lý bởi BOM. Không tự chọn một version Jetty khác với version mà Boot đang quản lý.

### 5.4. Undertow

Spring Boot 3.5 có hướng dẫn thay Reactor Netty bằng Undertow trong reactive stack và ghi nhận Undertow hỗ trợ h2c/h2. Khi nâng lên Boot 4.x, kiểm tra lại danh sách server starter được hỗ trợ và trạng thái tương thích. Không giả định mọi server được hỗ trợ ở Boot 3.x đều có starter tương ứng trong Boot 4.x.

## 6. Bật HTTP/2 ở Spring Boot server

Trong Spring Boot, property chính là:

```properties
server.http2.enabled=true
```

Property này yêu cầu embedded server bật HTTP/2 nếu môi trường hiện tại hỗ trợ. Cách chọn h2/h2c phụ thuộc SSL:

- Nếu đã cấu hình SSL/TLS, server có thể phục vụ h2.
- Nếu không bật SSL, Boot sử dụng h2c theo tài liệu cấu hình HTTP/2.
- Server connector và deployment vẫn phải hỗ trợ protocol tương ứng.

### 6.1. Cấu hình HTTPS + HTTP/2

Ví dụ với PEM certificate/private key:

Tệp src/main/resources/application.properties:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.certificate=classpath:localhost.crt
server.ssl.certificate-private-key=classpath:localhost.key
```

Certificate cần phù hợp với hostname client dùng để truy cập. Với môi trường production, certificate phải được cấp bởi CA được client tin cậy và private key phải được bảo vệ.

Có thể dùng PKCS#12 keystore thay cho PEM:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=change-this-password
server.ssl.key-alias=server
```

Đây là giá trị minh họa; production lấy password từ secret manager hoặc biến môi trường, không commit password thật vào repository.

### 6.2. Cấu hình h2c cho mạng nội bộ

Ví dụ:

```properties
server.port=8080
server.http2.enabled=true
```

Không cấu hình server.ssl cho listener này. Theo cấu hình Spring Boot, server sử dụng h2c nếu SSL không được bật.

h2c nên được giới hạn trong mạng nội bộ và được cấu hình đồng bộ với proxy/ingress. Client cần prior knowledge hoặc cơ chế được connector hỗ trợ. RFC 9113 đã deprecate HTTP/1.1 Upgrade token h2c.

### 6.3. Bật HTTP/2 không tự tạo hai listener HTTP và HTTPS

Khi cấu hình SSL bằng application properties, Boot thường cấu hình HTTPS connector. Nếu muốn đồng thời có một listener HTTP cleartext và một listener HTTPS, cần cấu hình connector bổ sung bằng API server-specific. Không giả định rằng chỉ đặt server.port và server.ssl.* sẽ tự mở cả hai cổng.

Trong production, thường để ingress/load balancer quản lý public HTTP/HTTPS redirect và chỉ expose listener backend theo đúng network policy.

## 7. Ví dụ Spring Boot WebFlux server hoàn chỉnh

Ví dụ dùng Spring Boot 3.5.x, Java 17+ và Reactor Netty mặc định.

### 7.1. Dependencies

Tệp build.gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dùng Spring Boot Gradle plugin và dependency management để chọn phiên bản tương thích. Starter WebFlux mặc định đưa Reactor Netty vào classpath.

### 7.2. Application class

Tệp src/main/java/demo/Http2Application.java:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Http2Application {

    public static void main(String[] args) {
        SpringApplication.run(Http2Application.class, args);
    }
}
```

### 7.3. Controller

Tệp src/main/java/demo/HelloController.java:

```java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello over HTTP",
                "server", "Spring WebFlux"));
    }
}
```

Controller không kiểm tra HTTP version. Server connector xử lý protocol trước khi request đến WebFlux.

### 7.4. Kiểm thử API semantics

Tệp src/test/java/demo/HelloControllerTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HelloControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void returnsHelloPayload() {
        client.get()
                .uri("/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello over HTTP")
                .jsonPath("$.server").isEqualTo("Spring WebFlux");
    }
}
```

Test này xác nhận controller và HTTP response semantics. Nếu WebTestClient được bind trực tiếp vào application context hoặc test adapter, nó không chứng minh TLS/ALPN đã thương lượng HTTP/2 trên socket thật. Muốn xác minh protocol, chạy server thật và kiểm tra bằng curl/openssl hoặc một client hỗ trợ HTTP/2.

## 8. Cấu hình server connector khác Reactor Netty

### 8.1. Chuyển sang Jetty

Ví dụ Gradle thay Reactor Netty bằng Jetty:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    implementation 'org.eclipse.jetty.http2:jetty-http2-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dùng version Jetty được Boot BOM quản lý. Đối với h2 qua TLS, bổ sung ALPN implementation theo hướng dẫn Jetty/Boot version đang dùng. Cấu hình server.http2.enabled=true và SSL properties vẫn là điểm bắt đầu của Boot.

### 8.2. Chuyển sang Undertow trong Boot 3.5

Ví dụ dependency replacement theo tài liệu Boot 3.5:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-undertow'

    modules {
        module('org.springframework.boot:spring-boot-starter-reactor-netty') {
            replacedBy(
                    'org.springframework.boot:spring-boot-starter-undertow',
                    'Use Undertow instead of Reactor Netty')
        }
    }
}
```

Sau khi thay server, kiểm tra WebClient connector riêng. Nếu vẫn muốn WebClient dùng Reactor Netty, dependency Reactor Netty client có thể vẫn cần thiết; server và client là hai lựa chọn connector độc lập.

### 8.3. Không trộn dependency server tùy tiện

Nếu để nhiều server starter cùng trên classpath, Boot có thể chọn một server theo auto-configuration hoặc phát hiện conflict. Hãy loại starter server mặc định đúng cách khi thay connector và kiểm tra dependency tree.

Đặc biệt, đừng lấy một version Jetty/Tomcat/Netty mới hơn rồi override một module đơn lẻ ngoài BOM. Các module connector, transport, TLS và Spring Boot auto-configuration cần tương thích.

## 9. Cấu hình HTTP/2 cho WebClient

WebClient dùng ClientHttpConnector để thực hiện request. Với Spring Boot, connector có thể được auto-detect theo classpath. Reactor Netty thường được ưu tiên khi có mặt cùng WebFlux starter.

**Client mặc định không nhất thiết tự dùng HTTP/2.** Với Reactor Netty, cần cấu hình protocol và TLS:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.HttpProtocol;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class Http2ClientConfiguration {

    @Bean
    WebClient http2WebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .protocol(HttpProtocol.H2)
                .secure();

        return builder
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Giải thích:

- HttpClient.create() tạo Reactor Netty HTTP client.
- protocol(HttpProtocol.H2) yêu cầu HTTP/2.
- secure() bật TLS để sử dụng h2 qua HTTPS.
- ReactorClientHttpConnector gắn client này vào WebClient.
- Các request được gửi bằng WebClient vẫn dùng API fluent bình thường.

Cấu hình chỉ HTTP/2 như ví dụ trên sẽ không fallback về HTTP/1.1. Nếu cần thương lượng HTTP/2 nhưng vẫn cho phép endpoint cũ, cấu hình cả hai protocol:

```java
HttpClient httpClient = HttpClient.create()
        .protocol(HttpProtocol.H2, HttpProtocol.HTTP11)
        .secure();
```

Khi đó HTTP/2 được ưu tiên trong ALPN negotiation; HTTP/1.1 có thể được chọn nếu peer không hỗ trợ h2.

### 9.1. WebClient h2c

Với một endpoint nội bộ đã xác nhận hỗ trợ h2c prior knowledge, có thể cấu hình Reactor Netty client:

```java
HttpClient httpClient = HttpClient.create()
        .protocol(HttpProtocol.H2C);

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

Sử dụng URL http://... và bảo đảm server thực sự hỗ trợ h2c prior knowledge. Không gửi h2c tới endpoint HTTP/1.1 thông thường.

### 9.2. Client connector khác

WebClient hỗ trợ Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient và Apache HttpComponents. Khả năng HTTP/2, cách bật protocol, TLS và connection pool khác nhau theo từng thư viện.

Nếu đổi connector, không copy nguyên cấu hình HttpProtocol.H2 của Reactor Netty sang connector khác. Dùng API và tài liệu chính thức của JDK, Jetty hoặc Apache HttpComponents đang chạy.

## 10. HTTP/2 và WebClient connection pool

HTTP/2 cho phép nhiều stream chia sẻ một connection. Reactor Netty dùng connection pool có cơ chế phân bổ stream riêng cho HTTP/2.

Một số khái niệm quan trọng:

- **maxConnections:** giới hạn số connection trong pool.
- **minConnections:** số connection tối thiểu muốn duy trì ở mức best-effort.
- **maxConcurrentStreams:** giới hạn stream đồng thời trên một connection; giới hạn thực tế còn phụ thuộc SETTINGS của server.
- **strictConnectionReuse:** ưu tiên sử dụng connection đang có stream capacity thay vì mở thêm.
- **streamBatchSize:** số stream có thể được mở theo một batch khi strict reuse được bật.

Không tăng connection count chỉ vì nghĩ HTTP/2 vẫn cần một connection cho mỗi request. Ngược lại, không ép một connection duy nhất phục vụ mọi tải nếu server hoặc mạng không chịu được.

Cần đo:

- Số connection active.
- Số stream active/pending.
- Thời gian chờ lấy stream hoặc connection.
- Số lần reconnect/TLS handshake.
- Latency p50/p95/p99.
- Tỷ lệ reset stream và lỗi GOAWAY.
- CPU, memory, network throughput và server concurrency.

### 10.1. Multiplexing không phải unlimited concurrency

Server gửi SETTINGS_MAX_CONCURRENT_STREAMS để thông báo giới hạn stream đồng thời. Client không được mở vượt giới hạn mà peer cho phép. Nếu nhiều request đồng thời hơn khả năng connection, chúng có thể chờ hoặc pool mở thêm connection.

Ứng dụng vẫn phải giới hạn concurrency ở tầng service. Một WebClient phát ra hàng trăm nghìn request đồng thời có thể làm cạn connection pool, queue, CPU hoặc tài nguyên downstream dù HTTP/2 multiplexing được bật.

### 10.2. Backpressure và HTTP/2 flow control

Reactor Flux/Mono dùng demand để điều tiết publisher. HTTP/2 flow control dùng window update để điều tiết byte transfer trên stream/connection.

Connector kết nối hai cơ chế này. Tuy nhiên, nếu ứng dụng gom toàn bộ body vào bộ nhớ, gọi collectList() hoặc dùng blocking I/O, HTTP/2 không tự làm cho ứng dụng trở nên streaming/non-blocking.

Hãy thiết kế pipeline reactive và giới hạn concurrency như bình thường; HTTP/2 là tầng transport bổ sung.

## 11. Proxy, ingress và load balancer

Trong hệ thống production, client hiếm khi kết nối trực tiếp với embedded server. Một request có thể đi qua CDN, WAF, reverse proxy, ingress controller, service mesh và backend.

Mỗi chặng có thể dùng protocol khác:

| Client → edge | Edge → backend | Protocol backend nhận được |
| --- | --- | --- |
| h2 | h2 | HTTP/2 |
| h2 | h2c | HTTP/2 cleartext |
| h2 | HTTP/1.1 | HTTP/1.1 |
| HTTP/1.1 | h2 | HTTP/2 |
| HTTP/1.1 | HTTP/1.1 | HTTP/1.1 |

Vì vậy, việc browser hiển thị h2 không chứng minh backend cũng nhận HTTP/2.

Khi triển khai sau proxy:

1. Xác định TLS được terminate ở đâu.
2. Kiểm tra protocol client→proxy.
3. Kiểm tra protocol proxy→backend.
4. Nếu dùng h2c nội bộ, chỉ mở cổng đó trong private network và giới hạn source.
5. Kiểm tra health check của load balancer có dùng protocol backend phù hợp.
6. Đảm bảo proxy chuyển tiếp headers đúng và không giữ các connection-specific header của HTTP/1.1 trong HTTP/2.
7. Đặt timeout, idle timeout và max concurrent streams ở mức phù hợp.
8. Kiểm tra graceful shutdown và GOAWAY khi backend rolling deploy.

Nếu proxy terminate TLS, backend có thể nhận HTTP/1.1 dù client đã dùng h2. Đó là cấu hình hợp lệ; chỉ cần hiểu rõ protocol trên từng hop.

## 12. Kiểm tra server đã dùng HTTP/2 hay chưa

Không chỉ kiểm tra property đã khai báo. Phải kiểm tra protocol thực tế trên socket.

### 12.1. Kiểm tra curl hỗ trợ HTTP/2

Chạy:

```bash
curl -V
```

Trong danh sách Features cần có HTTP2. Nếu không có, binary curl không hỗ trợ HTTP/2; kết quả kiểm tra sẽ không có ý nghĩa.

### 12.2. Kiểm tra HTTPS + h2

Chạy với server local ở port 8443:

```bash
curl -vk --http2 https://localhost:8443/hello
```

Trong output verbose, tìm thông tin ALPN và response status line:

```text
ALPN: server accepted h2
< HTTP/2 200
```

Với certificate self-signed chỉ trong môi trường local, -k bỏ qua xác thực certificate để phục vụ kiểm thử. Không dùng -k trong production; production phải xác thực certificate chain và hostname.

Lưu ý: curl --http2 có thể thương lượng rồi fallback về HTTP/1.1 nếu peer không hỗ trợ h2. Hãy đọc output protocol thực tế, không chỉ dựa vào việc curl trả status 200.

### 12.3. Kiểm tra h2c prior knowledge

Nếu server bật h2c trên port 8080:

```bash
curl -v --http2-prior-knowledge http://localhost:8080/hello
```

Response mong đợi có dòng:

```text
< HTTP/2 200
```

Tùy phiên bản curl, tùy chọn prior-knowledge có thể không có hoặc tên option khác. Kiểm tra curl --help all và curl -V trước khi dùng.

### 12.4. Kiểm tra ALPN bằng OpenSSL

Chạy:

```bash
openssl s_client   -connect localhost:8443   -servername localhost   -alpn h2
```

Nếu TLS handshake thành công và ALPN chọn HTTP/2, output có thông tin tương tự:

```text
ALPN protocol: h2
```

Nếu không có ALPN protocol hoặc server chọn http/1.1, kiểm tra certificate, TLS provider, server connector và ALPN configuration.

### 12.5. Kiểm tra bằng browser

Mở Developer Tools → Network → chọn request → xem cột Protocol. Chrome/Edge thường hiển thị h2 khi request dùng HTTP/2.

Nếu cột Protocol không xuất hiện, bật cột này trong bảng Network. Cần kiểm tra đúng request và đúng domain; một trang có thể tải tài nguyên từ nhiều origin dùng protocol khác nhau.

### 12.6. Kiểm tra qua log/metrics

Reactor Netty có metrics cho active connections và HTTP/2 streams. Có thể dùng access log, tracing hoặc server metrics để xác định protocol. Không bật wire logging toàn bộ trong production nếu chưa đánh giá lượng log và nguy cơ lộ headers/body.

## 13. HTTP/2 ảnh hưởng gì tới ứng dụng WebFlux?

### 13.1. Controller và router không cần thay đổi

Controller có thể tiếp tục trả Mono/Flux. Functional endpoint cũng không cần thay đổi route chỉ vì HTTP/2 được bật.

### 13.2. Không làm mọi request nhanh hơn tự động

HTTP/2 có thể giảm số connection, giảm chi phí handshake và cải thiện concurrency. Nhưng hiệu năng thực tế phụ thuộc:

- Latency và packet loss.
- Kích thước response.
- Số request đồng thời.
- CPU cho TLS và header compression.
- Giới hạn stream và connection pool.
- Proxy/load balancer.
- Backpressure và blocking code trong ứng dụng.
- Downstream services và database.

Hãy benchmark bằng workload đại diện. Một API có ít request, payload lớn hoặc backend chậm có thể không thấy cải thiện đáng kể.

### 13.3. Không sửa semantics của timeout

HTTP/2 có connection và stream riêng. Timeout ở tầng connect, TLS handshake, response/read, stream và idle connection không hoàn toàn giống nhau.

Khi tune timeout, phân biệt:

- TCP connect timeout.
- TLS handshake timeout.
- Response timeout.
- Read/write timeout.
- Idle timeout cho connection pool.
- Stream timeout hoặc application deadline.

Không đặt một timeout quá thấp cho toàn bộ connection chỉ để xử lý một request chậm. Cần theo dõi timeout theo từng chặng.

### 13.4. Xử lý stream reset và GOAWAY

HTTP/2 có lỗi ở mức stream và mức connection. Một stream có thể bị reset trong khi các stream khác trên connection vẫn tiếp tục. GOAWAY cho client biết server chuẩn bị đóng connection và stream nào đã được xử lý.

Khi server rolling restart, cần graceful shutdown để không làm mất các request đang chạy. Client nên retry có điều kiện, đặc biệt với request idempotent; không tự động retry POST có side effect nếu không có idempotency key và chính sách phù hợp.

### 13.5. Connection reuse và DNS/load balancing

HTTP/2 khuyến khích connection tồn tại lâu hơn. Điều đó giúp giảm handshake nhưng cũng có thể khiến một connection tiếp tục gắn với một backend lâu hơn dự kiến.

Nếu DNS hoặc load balancer thay đổi backend, connection đang mở không nhất thiết tự chuyển sang node khác. Cần thiết kế pool eviction, max connection age/idle timeout và graceful drain phù hợp với hạ tầng.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ WebFlux reactive nghĩa là HTTP/2 | Request vẫn có thể dùng HTTP/1.1 | Kiểm tra server/client connector và protocol thực tế |
| Chỉ đặt server.http2.enabled=true nhưng không có TLS | Boot dùng h2c; client public có thể không kết nối theo cách mong muốn | Cấu hình SSL cho h2 hoặc dùng h2c nội bộ có chủ đích |
| Certificate không khớp hostname | TLS handshake hoặc xác thực certificate thất bại | Dùng certificate hợp lệ và hostname đúng |
| ALPN không được hỗ trợ/cấu hình | Client và server không thương lượng được h2 | Kiểm tra JDK/TLS provider/connector/native dependency |
| Jetty thiếu HTTP/2 server module | Server không khởi động hoặc không hỗ trợ h2 | Thêm jetty-http2-server và ALPN implementation phù hợp |
| Dùng client mặc định rồi nghĩ WebClient luôn là h2 | Client có thể tiếp tục dùng HTTP/1.1 | Cấu hình underlying HttpClient/connector |
| Cấu hình H2 nhưng endpoint chỉ hỗ trợ HTTP/1.1 | Request thất bại nếu không có fallback | Cho phép H2 + HTTP11 hoặc nâng endpoint |
| Browser dùng h2 nhưng backend dùng HTTP/1.1 | Hiểu nhầm protocol end-to-end | Kiểm tra từng hop proxy/backend |
| Dùng h2c trên mạng public | Không có TLS bảo vệ transport | Dùng HTTPS/h2 |
| Dùng HTTP/1.1 Upgrade h2c theo ví dụ cũ | Cơ chế Upgrade đã bị RFC 9113 deprecate | Dùng h2 qua ALPN hoặc h2c prior knowledge trong mạng kiểm soát |
| Mở concurrency vô hạn | Pool, server hoặc downstream quá tải | Giới hạn concurrency và max streams |
| Ép một connection phục vụ mọi tải | Stream queue hoặc throughput giảm khi connection bão hòa | Tune pool và đo workload |
| Nghĩ HTTP/2 loại bỏ TCP head-of-line blocking | Packet loss vẫn có thể chặn dữ liệu trên connection | Đánh giá mạng; HTTP/3 là giao thức khác |
| Tự retry mọi lỗi stream | Có thể thực hiện side effect hai lần | Retry có điều kiện và dùng idempotency key |
| Test bằng WebTestClient mock rồi kết luận h2 đã hoạt động | Test không xác minh ALPN/socket protocol | Test server thật bằng curl/openssl |
| Chỉ nhìn status 200 | Không biết protocol đã được thương lượng | Kiểm tra HTTP/2 status line, ALPN hoặc DevTools |
| Bật wire logging quá rộng | Lộ headers/body và tạo lượng log lớn | Dùng metrics/tracing và redact dữ liệu |

## 15. Checklist triển khai HTTP/2

1. Xác định đang cần HTTP/2 ở server inbound hay WebClient outbound.
2. Kiểm tra Spring Boot version, Spring Framework version và embedded server/client dependency thật.
3. Xác nhận connector đang dùng có hỗ trợ HTTP/2 ở release đó.
4. Chọn h2 qua TLS hay h2c nội bộ.
5. Với h2, cấu hình certificate, private key, hostname và ALPN.
6. Với h2c, xác nhận client prior-knowledge và server hỗ trợ cùng mode.
7. Đặt server.http2.enabled=true nếu dùng embedded server Spring Boot.
8. Nếu đổi connector, loại dependency server mặc định đúng cách và thêm module HTTP/2 cần thiết.
9. Nếu dùng WebClient, cấu hình underlying ClientHttpConnector/HttpClient để bật HTTP/2.
10. Kiểm tra proxy/load balancer trên từng hop.
11. Xác minh bằng curl, openssl hoặc browser DevTools.
12. Đo active connections, active/pending streams, latency và reset/GOAWAY.
13. Tune max concurrent streams, pool, idle timeout và concurrency theo tải thật.
14. Test graceful shutdown, retry và idempotency.
15. Giữ TLS/certificate validation và bảo mật mạng nội bộ đúng policy.

## 16. Tài liệu tham khảo chính thức

- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): framing, streams, multiplexing, flow control, h2, h2c và TLS/ALPN.
- [Spring Boot 3.5 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): server.http2.enabled, h2/h2c và điều kiện cho Tomcat, Jetty, Reactor Netty, Undertow.
- [Spring Boot 4.1 – Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): cấu hình HTTP/2 theo embedded server ở thế hệ Boot mới.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux server support và auto-configuration.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): WebClient runtime, connector auto-detection và thứ tự ưu tiên.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình Reactor Netty, JDK HttpClient, Jetty và ClientHttpConnector.
- [Reactor Netty – HTTP Server Reference](https://projectreactor.io/docs/netty/release/reference/http-server.html): bật H2/H2C, TLS và protocol selection phía server.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): bật HTTP/2 phía client, ALPN, connection pool và stream allocation.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): HttpHandler adapters và server/client connector abstractions.

## 17. Ghi nhớ

**HTTP/2 là trách nhiệm của server/client connector, không phải annotation của controller.** Spring WebFlux vẫn xử lý request bằng cùng WebHandler, controller và Reactor publishers; connector quyết định protocol trên socket.

Trong Spring Boot, bật server bằng server.http2.enabled=true. Với HTTPS, cần TLS và ALPN để thương lượng h2. Nếu không bật SSL, Boot có thể dùng h2c; chỉ sử dụng cleartext HTTP/2 trên mạng nội bộ được kiểm soát và hiểu rằng RFC 9113 đã deprecate HTTP/1.1 Upgrade h2c. Reactor Netty, Tomcat, Jetty và Undertow có điều kiện hỗ trợ khác nhau theo version. WebClient cũng cần cấu hình connector/client riêng nếu muốn dùng HTTP/2 outbound.

Multiplexing giúp nhiều stream chia sẻ một connection, nhưng vẫn có giới hạn concurrent streams, flow control và TCP head-of-line blocking. Kiểm tra protocol thực tế bằng curl/ALPN hoặc browser DevTools, đo connection/stream metrics và kiểm thử qua toàn bộ đường đi proxy tới backend trước khi kết luận HTTP/2 đã được bật đúng.
