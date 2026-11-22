# Phân biệt cấu hình máy chủ reactive và cấu hình WebClient trong Spring Boot

## 1. Mục tiêu và phạm vi

Một ứng dụng Spring Boot WebFlux thường **đồng thời nhận HTTP request** từ người dùng và **gửi HTTP request** tới dịch vụ khác. Hai hướng lưu lượng này có thể cùng dùng Reactor Netty, nhưng **không phải một hệ thống cấu hình duy nhất**.

Bài học giúp phân biệt:

- **Reactive HTTP server (inbound)**: ứng dụng lắng nghe địa chỉ/cổng, nhận request, chạy WebFlux handler, tạo response.
- **WebClient (outbound)**: ứng dụng chủ động mở kết nối HTTP(S) tới một upstream, gửi request, nhận và decode response.
- Cơ chế server factory so với client builder/connector; phạm vi của `server.*`, `spring.webflux.*`, `spring.http.reactiveclient.*` (Boot 3.5) và `spring.http.clients.*` (Boot 4.x).
- Tình huống **chia sẻ tài nguyên** Reactor Netty/Jetty mà không làm lẫn lộn server và client.
- Các thay đổi thường gặp: cổng bind, base URL, connect/read/response timeout, SSL, proxy, header, codec, metrics và testing.

Ví dụ chính dùng **Spring Boot 3.5.x, Java 17+ và Reactor Netty**, vì vậy import Java và tên property của ví dụ đã được giới hạn theo dòng phiên bản đó. Với Boot 4.x, cần tra lại starter, package và namespace của HTTP client trước khi sao chép.

## 2. Cùng một tiến trình có hai vai trò mạng

~~~text
                   ỨNG DỤNG SPRING BOOT WEBFLUX
  Client bên ngoài
       |
       | GET http://service:8088/api/proxy
       v
  [HTTP SERVER / INBOUND]
       | TCP listener do embedded Reactor Netty tạo
       | server.port, server.address, server.ssl.*, ...
       v
  WebFlux HttpHandler -> Router/Controller
       |
       | Controller gọi WebClient.get(...)
       v
  [HTTP CLIENT / OUTBOUND]
       | baseUrl, request headers, ClientHttpConnector,
       | connect timeout, read timeout, TLS trust, proxy...
       v
  Dịch vụ upstream khác (hoặc loopback tới server này)
       |
       v
  Response upstream -> Mono/Flux -> response cho client ban đầu
~~~

Ở chiều vào, Spring Boot tạo **ReactiveWebServerApplicationContext**, lựa chọn một **ReactiveWebServerFactory**, rồi khởi động server nhận kết nối. Ở chiều ra, Spring Boot có thể cung cấp một **WebClient.Builder** đã cấu hình, cho phép tạo WebClient với **ClientHttpConnector** thích hợp.

Cả hai có thể chạy trên event loop của Reactor Netty và chia sẻ một số tài nguyên. Điều đó **không biến** `HttpServer` thành `HttpClient`, không biến `server.port` thành địa chỉ upstream và không khiến cấu hình TLS một chiều tự động áp dụng cho chiều còn lại.

## 3. Bảng phân biệt cốt lõi

| Khía cạnh | Reactive server (inbound) | WebClient (outbound) |
|---|---|---|
| Ai khởi xướng kết nối? | Client khác kết nối vào ứng dụng | Ứng dụng kết nối ra dịch vụ đích |
| API Spring Boot/Spring Framework | `ReactiveWebServerFactory`, `WebServerFactoryCustomizer` | `WebClient.Builder`, `WebClientCustomizer`, `ClientHttpConnector` |
| Reactor Netty API nền tảng | `reactor.netty.http.server.HttpServer` | `reactor.netty.http.client.HttpClient` |
| Địa chỉ/port chính | `server.address`, `server.port` | `WebClient.Builder.baseUrl(...)` và URI của request |
| TLS | Certificate/private key để **nhận** HTTPS, ví dụ `server.ssl.*` | Trust CA, optional client certificate, hostname verification để **gọi** HTTPS |
| Timeout | Idle/request/read trên kết nối đến (tùy server) | Connect/read/response/request pipeline khi gọi ra |
| HTTP proxy | Reverse proxy phía trước server, forwarded headers | Forward proxy mà outbound client sử dụng |
| Routing | `@GetMapping`, `RouterFunction`, `spring.webflux.base-path` | `WebClient.get().uri(...)`, base URL, filter |
| Headers | HTTP request vào và HTTP response ra | HTTP request ra và HTTP response từ upstream |
| Codec | WebFlux đọc body của request và ghi response | WebClient encode request body và decode upstream response |
| Tài nguyên | Listener, sockets nhận kết nối, event loops | Kết nối đi, connection pool, event loops |
| Khởi động | Thường cùng vòng đời Spring application context | Có thể tạo bean trước, nhưng network call thường xảy ra khi subscribe |
| Kiểm thử | `@SpringBootTest(RANDOM_PORT)` hoặc `WebTestClient` | Test outbound qua mock HTTP server hoặc upstream test thật |

**Mẹo ghi nhớ:** server là nơi **người khác gọi đến**, WebClient là cách **mình gọi người khác**. Chữ “reactive” mô tả mô hình lập trình non-blocking, không đồng nghĩa với việc mọi cấu hình Netty đều có hiệu lực cho cả hai.

## 4. Cấu hình server reactive: thuộc tính, factory, vòng đời

### 4.1. Dùng server.* cho yêu cầu phổ biến

Một số property của embedded reactive server:

~~~properties
server.port=8088
server.address=127.0.0.1
server.compression.enabled=true
# Ví dụ HTTPS inbound (chỉ bật khi đã cấu hình certificate và khóa):
# server.ssl.enabled=true
# server.ssl.bundle=my-server-bundle
~~~

- `server.port`: cổng mà server **lắng nghe**, không phải remote port của WebClient.
- `server.address`: địa chỉ bind server, chẳng hạn `127.0.0.1` giới hạn truy cập từ loopback. Nó không chọn source IP cho mọi outbound connection.
- `server.compression.*`: nén HTTP response của server theo điều kiện kích thước/content type; không ép upstream gửi compressed response.
- `server.ssl.*`: TLS **server-side**, không tự chỉ dẫn WebClient tin một certificate của upstream.

Bản chất giá trị `server.port=0` là yêu cầu OS cấp cổng còn trống cho server thật; `server.port=-1` tắt listener HTTP chính nhưng vẫn giữ web application context. Hai giá trị này **không làm WebClient biến mất**, vì outbound calls còn phụ thuộc service/runner nào sử dụng nó.

### 4.2. Tác động của spring.webflux.*

Các thiết lập như `spring.webflux.base-path`, static resource mapping hoặc cấu hình WebFlux ảnh hưởng tới **định tuyến server**. Chúng không tạo remote base URL của WebClient. Ví dụ nếu dùng:

~~~properties
spring.webflux.base-path=/v1
~~~

thì đường đến một handler được triển khai với mapping `/api/hello` có thể thành `/v1/api/hello`. Nhưng WebClient đang có `baseUrl("https://payments.example")` vẫn gọi host đó; Spring Boot không tự thêm `/v1` vào URI outbound.

Tương tự, `WebFluxConfigurer` là điểm mở rộng cấu hình server-side handler/mapping/formatters. Nó **không thay thế** `WebClient.Builder`. Khi thiết kế hệ thống, phải chỉ rõ bạn đang thay đổi router nhận request hay HTTP client gọi API bên ngoài.

### 4.3. Khi property chưa đủ: WebServerFactoryCustomizer

Trong Spring Boot 3.5, có thể định nghĩa:

~~~java
import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
WebServerFactoryCustomizer<NettyReactiveWebServerFactory> nettyServerCustomizer() {
    return factory -> factory.addServerCustomizers(
            server -> server.idleTimeout(Duration.ofSeconds(20)));
}
~~~

Đây là **đoạn method thuộc một class `@Configuration`**, không phải file Java hoàn chỉnh. `NettyReactiveWebServerFactory` tạo server, còn `addServerCustomizers` thêm callback cấu hình Reactor Netty **HttpServer**. Idle timeout ở đây giới hạn thời gian một kết nối HTTP phía server chờ request tiếp theo, **không** phải timeout của WebClient khi chờ upstream.

Nên dùng `addServerCustomizers` khi thật sự muốn **bổ sung**; `setServerCustomizers` có thể thay toàn bộ các customizer đã có. Thông thường, trước khi viết code, hãy kiểm tra xem `server.*` hoặc property riêng của `server.netty.*` ở đúng Boot version đã đáp ứng yêu cầu chưa.

Khác với Servlet MVC factory, các factory của reactive web stack có interface và lifecycle riêng. Nếu dùng WebFlux trên Jetty/Tomcat, generic `WebServerFactoryCustomizer<NettyReactiveWebServerFactory>` sẽ không áp dụng cho các factory đó. Không suy luận chỉ từ một JAR Netty trên classpath rằng WebFlux server thực tế đang chạy bằng Netty.

### 4.4. Hạn chế thay toàn bộ factory

Nếu khai báo một `ReactiveWebServerFactory` bean riêng, nhánh auto-configuration tạo factory mặc định có thể nhường chỗ. Boot vẫn có khả năng áp dụng những auto-configured `WebServerFactoryCustomizer` phù hợp lên factory do ứng dụng tạo, nhưng ứng dụng cần bảo đảm type compatibility và các cấu hình server cần thiết. Chỉ dùng cách này khi phải thay phương thức khởi tạo server, không phải để đổi một timeout hay port.

## 5. Cấu hình WebClient: builder, connector và upstream URI

### 5.1. Cách khuyến nghị trong Spring Boot

Spring Boot 3.5 cung cấp `WebClient.Builder` bean đã được auto-configure và có phạm vi prototype. Nên **inject builder** rồi tạo WebClient cho từng upstream/service:

~~~java
@Bean
WebClient catalogWebClient(WebClient.Builder builder) {
    return builder.baseUrl("https://catalog.example")
            .defaultHeader("X-Client-Name", "inventory")
            .build();
}
~~~

Đây là đoạn method minh họa, đặt trong `@Configuration` và thêm import phù hợp. `baseUrl` chọn nơi gửi HTTP request **đi ra**, không liên quan `server.port`. `defaultHeader` thiết lập header mặc định của request WebClient, không phải header đáp lại từ server Spring WebFlux.

WebClient được build ra có thể dùng lại giữa nhiều request và là API immutable. **Builder** thì stateful: thay đổi builder ảnh hưởng những client được build sau thay đổi đó. Nếu tạo nhiều client từ cùng một builder trong một method, cân nhắc `builder.clone()` để tránh cấu hình baseUrl/header của client này đi sang client kia.

`WebClient.create()` hoặc `WebClient.builder()` gọi tĩnh không tự thừa hưởng tất cả cấu hình mà Spring Boot đặt lên builder được inject. Điều này có thể làm mất shared HTTP resources, codec customizers, observability hoặc HTTP client settings theo framework. Tránh tự tạo client trực tiếp trừ khi có lý do rõ ràng.

### 5.2. HTTP client implementation không nhất thiết giống HTTP server

Boot có thể tự chọn `ClientHttpConnector` cho WebClient theo các HTTP client libraries nằm trên classpath; ở dòng 3.5 thứ tự ưu tiên gồm Reactor Netty, Jetty RS client, Apache HttpClient và JDK HttpClient. WebFlux starter mặc định mang Reactor Netty làm cả HTTP server và có thể làm HTTP client.

Nhưng hai lựa chọn độc lập về chức năng:

- WebFlux server chạy trên **Tomcat reactive** vẫn có thể dùng WebClient + **Reactor Netty HttpClient**.
- WebFlux server chạy **Reactor Netty** vẫn có thể gọi API bằng WebClient có **Jetty client connector** khi dependency và cấu hình phù hợp.
- Một app Spring MVC/Servlet cũng có thể dùng WebClient để gọi dịch vụ ngoài; không có nghĩa toàn bộ server chuyển sang WebFlux.
- Nếu có nhiều client connector implementation trong classpath, hãy xác minh lựa chọn đã được auto-configure thay vì suy đoán chỉ qua dependency đầu tiên.

### 5.3. Timeout của WebClient trong Spring Boot 3.5

Tài liệu chính thức Spring Boot 3.5 hỗ trợ cấu hình HTTP client ở namespace:

~~~properties
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
spring.http.reactiveclient.redirects=dont-follow
~~~

Những thuộc tính này điều chỉnh **HTTP client connector** do Boot tự cấu hình, không đổi idle/read timeout của server đang nhận request.

- **Connect timeout**: giới hạn thời gian thiết lập kết nối tới đích.
- **Read timeout**: giới hạn tương ứng cho việc nhận dữ liệu ở HTTP client theo connector được sử dụng.
- **Redirect policy**: client có tự đi theo redirect response hay không.
- Mọi timeout có ngữ nghĩa cụ thể tùy connector. Đừng đánh đồng connect timeout, time-to-first-byte, thời gian tải hết body và **deadline tổng** của một nghiệp vụ.

Muốn đặt giới hạn tổng cho một chuỗi reactive cụ thể có thể thêm Reactor operator:

~~~java
Mono<String> body = webClient.get()
        .uri("/v1/data")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(5));
~~~

Đây là đoạn method minh họa, cần `webClient` và imports phù hợp. `timeout(Duration)` là timeout của **Publisher pipeline** tính từ subscription, không phải server accept timeout và không phải một cách thay thế đầy đủ connect/read timeout ở socket.

**Cảnh báo về phiên bản:** Spring Boot 4.x đổi tổ chức namespace HTTP client. Theo tài liệu 4.1, dạng cấu hình client chung là `spring.http.clients.connect-timeout`, `spring.http.clients.read-timeout` và lựa chọn reactive connector là `spring.http.clients.reactive.connector`. Không sao chép nguyên văn các khóa `spring.http.reactiveclient.*` của Boot 3.5 sang 4.x nếu chưa đối chiếu property metadata của phiên bản đích.

### 5.4. Customize riêng Reactor Netty HttpClient

Khi property chưa đủ, có thể tạo một HTTP client và đưa vào **WebClient**:

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(4));

WebClient specialClient = builder.clone()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://partner.example")
        .build();
~~~

Đây là **trích đoạn Java**; yêu cầu imports `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector`, `org.springframework.web.reactive.function.client.WebClient` và `java.time.Duration`; biến `builder` là `WebClient.Builder` được inject.

- `HttpClient.create()` là **client**, không phải `reactor.netty.http.server.HttpServer`.
- `responseTimeout` điều chỉnh hành vi chờ HTTP response của client cụ thể; không thay port/server idle timeout.
- `clientConnector(...)` thay connector của client được build. Việc này có thể bỏ qua một phần cấu hình connector/SSL/resource management do Boot tạo tự động; cần tự xác minh khi override.
- Nếu muốn thay đổi chung cho nhiều client, cân nhắc các Boot-level client connector customizers được cung cấp bởi **đúng phiên bản** thay vì tự `new` connector cho từng service.

Không nên `block()` trong thread event loop của một WebFlux controller. Ví dụ ở phần 8 sẽ trả `Mono<String>` không chặn luồng; việc gọi `block()` chỉ đặt trong ví dụ JUnit đang chạy ở test thread.

### 5.5. Proxy outbound khác reverse proxy inbound

**Inbound reverse proxy:** Nginx, gateway hoặc load balancer đứng trước Spring Boot; cấu hình `server.forward-headers-strategy`, trusted proxy và header chuyển tiếp để server xác định scheme/host của request.

**Outbound forward proxy:** WebClient chủ động đi ra mạng qua HTTP proxy; cần cấu hình chính **HTTP client connector**. Ví dụ với Reactor Netty có API `HttpClient.proxy(...)` và hỗ trợ xác thực proxy theo cách phù hợp. Không đặt `server.forward-headers-strategy` rồi kỳ vọng WebClient bắt đầu đi qua proxy.

Với service URL do client đầu vào quyết định, phải kiểm soát allowlist hostname/IP, redirect và DNS để tránh SSRF. Cấu hình outbound HTTP client là một biên bảo mật riêng so với inbound routing.

## 6. TLS, mTLS và SSL bundle: hai hướng tín nhiệm khác nhau

Khi ứng dụng **nhận HTTPS**, server cần certificate và private key để chứng minh danh tính trước client. Các thiết lập thường đặt ở `server.ssl.*`/SSL bundle server, phù hợp server implementation và phiên bản.

Khi **WebClient gọi HTTPS**, client phải xác thực certificate của dịch vụ đích; nếu upstream yêu cầu mTLS, client còn phải cung cấp client certificate phù hợp. Việc application đã có HTTPS endpoint **không khiến WebClient tự dùng certificate đó**, và việc đã thêm CA tin cậy cho outbound **không khiến server bật HTTPS**.

Trong Boot 3.5, có thể inject `WebClientSsl` và dùng SSL bundle đã khai báo, ví dụ đoạn method trong một class cấu hình:

~~~java
@Bean
WebClient partnerClient(WebClient.Builder builder, WebClientSsl ssl) {
    return builder.baseUrl("https://partner.example")
            .apply(ssl.fromBundle("partner-trust"))
            .build();
}
~~~

Import `org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl` là dành cho **Boot 3.5**. Một bundle thực tế cần cấu hình truststore/certificate và secret bằng cơ chế quản lý bí mật; đoạn code không thể tự hoạt động nếu chưa có bundle tên `partner-trust`.

Không tắt hostname verification hay trust-all certificate để “sửa” lỗi SSL trong production. Phải xác minh cert chain, SAN/hostname, thời hạn, CA và sự khác biệt giữa mTLS client identity và server identity.

## 7. Phần nào có thể chia sẻ giữa server và WebClient?

Spring Boot có thể tạo `ReactorResourceFactory` hoặc `JettyResourceFactory` để quản lý tài nguyên HTTP. Khi **cùng công nghệ** được dùng cho client và server, và client được tạo từ **Boot auto-configured WebClient.Builder**, tài nguyên Netty/Jetty có thể được chia sẻ để giảm overhead.

Điều có thể chia sẻ:

- Event loop resources và những tài nguyên IO nền tảng mà Spring Boot quản lý.
- Cấu hình lifecycle/shutdown tài nguyên được Boot kết nối với application context.
- Một số codec configuration khi cả WebFlux server và Boot-built WebClient sử dụng auto-configuration tương ứng.

Điều **không nên suy ra** là dùng chung:

- Cổng lắng nghe inbound và port remote/outbound.
- HTTP server socket với một outbound connection socket.
- SSL identity của server với trust settings của client.
- Timeout idle server với response timeout WebClient.
- Authorization policy của inbound handler với credential của outbound call.
- HTTP headers của request vào với headers của request do WebClient phát ra.

**Bẫy thường gặp:** tự khai báo một `ReactorResourceFactory` bean tùy biến có thể ảnh hưởng **cả client và server** nếu cả hai dùng resource bean đó. Ngược lại, tạo một WebClient với custom `ReactorClientHttpConnector` có thể không sử dụng đúng sharing model của Boot nữa. Vì thế ranh giới độc lập về chức năng **không đồng nghĩa** mọi resource setting hoàn toàn tách biệt.

Nếu tự quản lý connection pool hoặc LoopResources, phải kiểm tra ownership và đóng tài nguyên khi application context kết thúc. Tạo mới event loops/pools vô hạn cho từng request có thể gây leak threads/sockets và làm hiệu năng giảm.

## 8. Ví dụ đầy đủ: một app vừa làm WebFlux server vừa dùng WebClient

Ví dụ chạy bằng Spring Boot **3.5.16**, Java 17+, Reactor Netty. Để không lệ thuộc upstream thật, WebClient sẽ gọi ngược lại một endpoint riêng **trong cùng ứng dụng**. Điều đó vẫn là một HTTP call outbound thật qua network stack loopback; nó minh họa hai vai trò tách biệt rõ ràng.

### 8.1. Cấu trúc project

~~~text
reactive-server-client/
  pom.xml
  src/
    main/
      java/com/example/reactive/ServerClientDemoApplication.java
      resources/application.properties
    test/
      java/com/example/reactive/ServerClientDemoTest.java
~~~

### 8.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-server-client</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Không thêm `spring-boot-starter-web`: sự hiện diện đồng thời MVC và WebFlux có thể khiến Boot suy ra loại web application là **SERVLET** thay vì REACTIVE. Dự án ví dụ cố ý dùng chỉ WebFlux starter để giữ reactive web server và controller hoạt động như thiết kế.

### 8.3. application.properties

~~~properties
# HTTP SERVER: ứng dụng nhận request trên loopback port 8088.
server.address=127.0.0.1
server.port=8088
server.compression.enabled=true

# HTTP CLIENT: URL của dịch vụ được WebClient gọi ra.
# Demo dùng chính server trên để tránh phụ thuộc API bên ngoài.
demo.upstream.base-url=http://127.0.0.1:8088

# HTTP CLIENT: chỉ áp dụng theo API property Spring Boot 3.5.
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
spring.http.reactiveclient.redirects=dont-follow
~~~

`server.port=8088` và `demo.upstream.base-url=http://127.0.0.1:8088` tình cờ trùng cổng **chỉ do demo gọi loopback**. Đổi server port thành 8099 **không tự làm** WebClient đổi base URL. Trong hệ thống thật, upstream thường là host khác, nên hai giá trị phải được quản lý độc lập.

`server.compression.enabled=true` không bảo đảm response ngắn `inbound-ok` sẽ nén vì còn có ngưỡng kích thước và content type; không dùng ví dụ này để kết luận compression đã bật đúng chỉ bằng header Content-Encoding.

### 8.4. File Java hoàn chỉnh

Lưu file `src/main/java/com/example/reactive/ServerClientDemoApplication.java`:

~~~java
package com.example.reactive;

import java.time.Duration;

import reactor.core.publisher.Mono;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootApplication
public class ServerClientDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServerClientDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class HttpRolesConfiguration {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
    inboundServerCustomizer() {
        return factory -> factory.addServerCustomizers(
                server -> server.idleTimeout(Duration.ofSeconds(20)));
    }

    @Bean
    WebClient upstreamWebClient(
            WebClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {

        return builder.baseUrl(baseUrl)
                .defaultHeader("X-Demo-Client", "client-demo")
                .build();
    }
}

@RestController
class DemoController {
    private final WebClient upstream;

    DemoController(@Qualifier("upstreamWebClient") WebClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/hello")
    Mono<String> hello() {
        return Mono.just("inbound-ok");
    }

    @GetMapping("/upstream/data")
    Mono<String> upstream(
            @RequestHeader(name = "X-Demo-Client",
                           required = false) String marker) {
        return Mono.just("upstream-ok|marker="
                + (marker == null ? "none" : marker));
    }

    @GetMapping("/api/proxy")
    Mono<String> proxy() {
        return upstream.get()
                .uri("/upstream/data")
                .retrieve()
                .bodyToMono(String.class)
                .map(body -> "proxy:" + body);
    }
}
~~~

**Giải thích từng phần:**

1. `inboundServerCustomizer()` bổ sung cấu hình cho **server factory**, giới hạn thời gian idle của kết nối phía server. Nó không thiết lập read timeout của outbound WebClient.
2. `upstreamWebClient(...)` nhận **builder do Spring Boot auto-configure** và tạo client có base URL và header riêng. Nó không tạo server listener và không đổi cổng nhận HTTP.
3. Controller `/api/hello` đáp ứng trực tiếp từ server; không có outbound call.
4. Controller `/upstream/data` là endpoint đóng vai upstream trong demo. Nó trả header do **WebClient gửi vào** dưới dạng string body để quan sát.
5. Controller `/api/proxy` gửi một HTTP request mới bằng `WebClient` tới `/upstream/data`, nhận body và trả body đã thêm prefix. Nó trả `Mono<String>`; không dùng `block()` trong reactive request thread.
6. Một ứng dụng có thể dùng cùng Reactor Netty runtime cho cả hai vai trò; **hai HTTP request khác nhau** vẫn xảy ra và có thể được ghi log/đo riêng.

Đây là ứng dụng demo. Trong production, việc WebClient gọi ngược chính server là không cần thiết trừ một số kiến trúc đặc thù; thay bằng baseUrl của upstream thật và kiểm soát access token, timeout, retry, circuit breaker, DNS/proxy phù hợp.

### 8.5. Chạy và kiểm tra output

Yêu cầu Maven và JDK 17+; tại thư mục dự án chạy:

~~~bash
mvn spring-boot:run
~~~

Hoặc dùng `./mvnw spring-boot:run` nếu project có wrapper (Windows: `mvnw.cmd spring-boot:run`).

Gửi các request:

~~~bash
curl -sS http://127.0.0.1:8088/api/hello
curl -sS http://127.0.0.1:8088/upstream/data
curl -sS http://127.0.0.1:8088/api/proxy
~~~

Body kỳ vọng chính xác theo thứ tự:

~~~text
inbound-ok
upstream-ok|marker=none
proxy:upstream-ok|marker=client-demo
~~~

Mỗi dòng là body của **một lệnh riêng**, không phải stdout gộp mà shell chắc chắn in thành ba dòng: các controller trả String không kèm ký tự newline, còn `curl -sS` không tự thêm newline.

Quan sát ý nghĩa: `/api/hello` chứng minh server nhận inbound, `/upstream/data` thể hiện incoming header khi gọi trực tiếp, và `/api/proxy` thể hiện WebClient đã tạo **một outbound request mới** với `X-Demo-Client`. Việc endpoint proxy chạy được không có nghĩa client sử dụng server port property; điều đó chỉ vì cấu hình demo.upstream.base-url đang trỏ tới loopback 8088.

### 8.6. Kiểm thử tự động cổng ngẫu nhiên

Trong kiểm thử HTTP tích hợp, dùng cổng ngẫu nhiên để tránh xung đột. Tạo file `src/test/java/com/example/reactive/ServerClientDemoTest.java`:

~~~java
package com.example.reactive;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServerClientDemoTest {

    @LocalServerPort
    int port;

    @Autowired
    WebClient.Builder clientBuilder;

    @Test
    void serverPortAndOutboundClientAreIndependent() {
        assertTrue(port > 0);

        WebClient testClient = clientBuilder.clone()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        String response = testClient.get()
                .uri("/api/hello")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("inbound-ok", response);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` khởi động một embedded reactive server thật trên cổng hệ điều hành cấp, và `@LocalServerPort` nhận cổng thực. Test tạo một outbound WebClient riêng cho cổng đó bằng builder clone. Nó **không giả định** `server.port` luôn là 8088.

Lưu ý: bean `upstreamWebClient` của ứng dụng vẫn dùng `demo.upstream.base-url=...:8088` trong test này. Test chỉ gọi `/api/hello`, không gọi `/api/proxy`; nếu muốn test proxy khi server có random port, phải cấu hình upstream URL động cho đúng port hoặc dùng một mock upstream HTTP server được khởi động độc lập. Đây là lý do nên tách remote endpoint config khỏi server port.

`block(Duration)` trong **JUnit test thread** là được cho phép để lấy kết quả xác nhận; tránh sao chép cách block đó vào handler WebFlux production.

## 9. Những cấu hình sai phổ biến

### Sai 1. Đổi server.port để WebClient gọi upstream khác

~~~properties
server.port=9090
~~~

Thuộc tính trên chỉ đổi cổng mà **ứng dụng nhận request**. Muốn WebClient gọi sang địa chỉ mới, đổi giá trị đã đưa vào `WebClient.Builder.baseUrl(...)`, URI của request, service discovery hoặc configuration riêng của HTTP client.

### Sai 2. Chỉnh HttpServer timeout rồi đợi WebClient hết timeout

`NettyReactiveWebServerFactory.addServerCustomizers(server -> server.idleTimeout(...))` chỉ điều chỉnh server. Muốn thay connect/read/response timeout khi gọi ra, cấu hình HTTP client connector hoặc operator reactive đúng chỗ. Không có quy tắc “Netty timeout” áp dụng cho mọi chiều lưu lượng.

### Sai 3. Tạo HttpClient rồi nghĩ server sẽ dùng

`HttpClient.create()` thuộc Reactor Netty outbound. Chuyển một `HttpClient` vào `ReactorClientHttpConnector` chỉ áp dụng cho WebClient dùng connector đó. HTTP server vẫn được Spring Boot khởi tạo từ reactive server factory.

### Sai 4. Gắn server.ssl.* để WebClient tin upstream CA

Server SSL certificate/private key không thay thế truststore của WebClient. Nếu upstream có certificate không được tin cậy, phải xử lý client SSL bundle/trust chain đúng cách, không tắt TLS verification.

### Sai 5. Dùng WebFluxConfigurer để đổi WebClient baseUrl

`WebFluxConfigurer` cấu hình WebFlux server-side request handling, không phải factory của HTTP client. Tạo/inject `WebClient.Builder` và cung cấp upstream base URL riêng.

### Sai 6. Tự tạo WebClient.create() và mong Boot áp dụng tất cả customizer

API tạo tĩnh của Spring Framework không tự kế thừa đầy đủ Boot auto-configuration. Khi cần HTTP resources, codecs, observability và cấu hình connector chuẩn của ứng dụng, ưu tiên builder do Boot cung cấp.

### Sai 7. Coi chia sẻ tài nguyên là chia sẻ cấu hình kinh doanh

Dù client/server có thể cùng sử dụng `ReactorResourceFactory`, chúng vẫn có auth, TLS, routes, timeout và error handling độc lập. Nếu cần thay toàn bộ resource bean, phải kiểm tra cả phía server lẫn client.

### Sai 8. Gọi .block() trong WebFlux handler

Blocking trên Netty event loop có thể dẫn tới `IllegalStateException` hoặc nghẽn khả năng xử lý request. Nên trả `Mono`/`Flux` hoặc kết hợp bằng `map`/`flatMap`. Với thư viện blocking bắt buộc, chuyển sang scheduler phù hợp và đánh giá tác động lên tài nguyên.

### Sai 9. Trộn HTTP client error với HTTP server error

`WebClient.retrieve()` mặc định phát error signal cho response 4xx/5xx từ upstream. Một lỗi từ upstream có thể trở thành lỗi server khi ứng dụng không xử lý, nhưng nguồn gây lỗi là **outbound HTTP call**. Phân biệt log/metrics của server-side 5xx với client-side timeout, DNS, SSL hoặc upstream status. Thiết kế mapping lỗi và circuit breaker có chủ đích.

### Sai 10. Áp dụng property namespace của Boot khác phiên bản

Boot 3.5: `spring.http.reactiveclient.*`. Boot 4.1: nhóm `spring.http.clients.*`, lựa chọn reactive connector qua `spring.http.clients.reactive.connector`. Luôn tra **Common Application Properties** của chính build và dùng integration tests để xác minh, đặc biệt khi nâng cấp major.

## 10. Chẩn đoán từ triệu chứng thực tế

| Triệu chứng | Phía nào cần kiểm tra trước? | Dấu hiệu/hành động |
|---|---|---|
| Không thể curl vào localhost:8088 | Server inbound | `server.port`, `server.address`, web application type, startup log, firewall |
| Local route trả 200 nhưng gọi upstream thất bại | Client outbound | baseUrl, DNS, proxy, TLS trust, connect/read timeout, auth |
| Đổi server.port nhưng WebClient vẫn gọi cổng cũ | Client configuration | Remote base URL độc lập hoặc service discovery config |
| Lỗi `Connection refused` từ WebClient | Outbound | Đích/port sai, upstream không lắng nghe, network |
| Lỗi `DataBufferLimitException` khi decode response | Client codecs / buffering | Xem giới hạn codec của WebClient, kích thước payload và streaming |
| 502/504 tại gateway trước ứng dụng | Gateway + server path | Timeout và upstream health ở reverse proxy; đối chiếu server logs |
| Reactor Netty threads/pools không giải phóng | Shared resources/lifecycle | `ReactorResourceFactory`, custom connector/pool, context shutdown |
| SSL handshake lỗi khi gọi remote HTTPS | Client TLS | CA, hostname, mTLS client certificate, bundle của client |
| SSL handshake lỗi khi browser vào ứng dụng | Server TLS | `server.ssl.*`, certificate/private key, binding, reverse proxy |
| Sau thay Jetty/Tomcat server, WebClient vẫn dùng Netty | Không nhất thiết lỗi | HTTP server và HTTP client có connector lựa chọn độc lập |
| HTTP response server không có gzip | Server compression policy | Content type, response size threshold, client `Accept-Encoding` |
| Test RANDOM_PORT pass /api/hello nhưng /api/proxy fail | Outbound config | Proxy client vẫn gọi URL cố định 8088, không tự theo test port |

## 11. Quy trình thiết kế an toàn cho production

1. **Xác định luồng cần đổi.** Vẽ rõ request inbound vào app và outbound tới downstream nào; ghi lại host/port/TLS/trust/timeout tại mỗi ranh giới.
2. **Cấu hình server bằng property trước.** `server.port`, `server.address`, SSL, compression, forwarded headers; khi thiếu mới dùng `WebServerFactoryCustomizer` đúng server implementation.
3. **Cấu hình client theo từng upstream.** Inject Boot `WebClient.Builder`, đặt `baseUrl`, credentials/header và policy riêng; tránh dùng một global builder mutable cho mọi client.
4. **Giới hạn tài nguyên và timeout.** Connect/read timeout, overall request deadline, connection pooling; xác định chính xác settings là của `HttpClient` hay `HttpServer`.
5. **TLS và bảo mật đúng chiều.** Server có certificate riêng, client có trust policy riêng; kiểm tra SSRF, redirect, proxy, authentication và authorization.
6. **Xác minh chia sẻ tài nguyên.** Nếu dùng `ReactorResourceFactory` hoặc custom connector, kiểm tra lifecycle, pool/loop configuration cho cả hai vai trò.
7. **Dùng bài test phù hợp.** Test inbound bằng random port, test outbound bằng upstream mock server/contract test; kiểm tra cả error, timeout, SSL và connection leak.
8. **Quan sát hai vai trò riêng.** Phân biệt incoming request metrics, outgoing client metrics, trace ID propagation (có chính sách), timeout và upstream status.
9. **Kiểm tra phiên bản trước khi migrate.** Đặc biệt Boot 3.5 → 4.x, tên property HTTP client, import `NettyReactiveWebServerFactory`, starter và API customization có thể khác.

**Kết luận:** máy chủ reactive và WebClient là **hai thành phần vận hành khác hướng**: server nhận HTTP và được điều khiển bằng `server.*`/reactive server factory; WebClient phát HTTP và được điều khiển bằng builder/ClientHttpConnector/cấu hình client. Chúng có thể chia sẻ IO resources, nhưng không chia sẻ mặc định base URL, port, TLS identity, timeout hay chính sách bảo mật.

## Tài liệu chính thức để tra cứu

- Spring Boot 3.5 — Reactive Web Applications và Customizing Reactive Servers: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Embedded Web Servers và `WebServerFactoryCustomizer`: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Calling REST Services / WebClient Runtime / HTTP Connector Configuration: https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.1 — Reactive Web Applications (server factory API có thể đổi package): https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot 4.1 — Calling REST Services / HTTP clients namespace: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework — WebClient configuration, codecs, clientConnector, resources: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Boot 3.5 API — NettyReactiveWebServerFactory: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html
- Reactor Netty — HTTP Server Configuration/Timeout: https://projectreactor.io/docs/netty/release/reference/http-server.html
