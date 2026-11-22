# Tùy chỉnh NettyReactiveWebServerFactory và HttpServer trong Spring Boot

## 1. Mục tiêu

Khi Spring Boot chạy một ứng dụng **Spring WebFlux** với **Reactor Netty** làm embedded HTTP server, lớp tích hợp trung tâm là NettyReactiveWebServerFactory. Factory này tạo NettyWebServer, còn cấu hình tầng HTTP/TCP cụ thể được áp dụng lên **reactor.netty.http.server.HttpServer** trước khi server bind và bắt đầu nhận request.

Bài học hướng dẫn cách tùy chỉnh đúng hai cấp:

1. **Cấp Spring Boot web server factory**: cổng, địa chỉ bind, SSL, HTTP/2, compression, lifecycle, tài nguyên Reactor Netty.
2. **Cấp Reactor Netty HttpServer**: idle timeout, access log, wiretap, HTTP decoder, TCP/channel và các hook đặc thù Netty khi cần.

Nguyên tắc quan trọng: **ưu tiên cấu hình application.properties/application.yaml; khi không có property phù hợp mới dùng WebServerFactoryCustomizer; chỉ thay factory bằng bean tự xây dựng ở trường hợp thực sự đặc biệt**. Không tạo một HttpServer riêng bằng HttpServer.create().bindNow() trong customizer vì nó không tự gắn với pipeline, cổng và lifecycle mà Spring Boot đang quản lý.

Ví dụ trong bài áp dụng **Spring Boot 3.3.x, Java 17+, Spring WebFlux và Reactor Netty 1.1.x do Spring Boot quản lý phiên bản**. Tên package, API và tùy chọn có thể thay đổi ở các dòng Spring Boot/Reactor Netty lớn hơn; kiểm tra Javadoc của đúng phiên bản trước khi chuyển mã giữa các phiên bản.

## 2. Điều kiện để NettyReactiveWebServerFactory được sử dụng

Một project reactive phổ biến khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

spring-boot-starter-webflux thường đưa Spring WebFlux và Reactor Netty vào runtime classpath. Khi Spring Boot chọn **WebApplicationType.REACTIVE**, auto-configuration phù hợp sẽ cung cấp ReactiveWebServerFactory, trong trường hợp Reactor Netty là NettyReactiveWebServerFactory.

**Lưu ý về lựa chọn stack:** Nếu cả spring-boot-starter-web (Spring MVC) và spring-boot-starter-webflux cùng tồn tại trên classpath, Spring Boot thường **ưu tiên Servlet/Spring MVC**. Khi đó tùy chỉnh NettyReactiveWebServerFactory không trở thành tùy chỉnh HTTP server MVC. Có thể chủ động chọn reactive bằng spring.main.web-application-type=reactive nếu dependency và kiến trúc thực sự phù hợp.

Ví dụ cấu hình ép reactive trong trường hợp có cả hai starter:

~~~properties
spring.main.web-application-type=reactive
~~~

Nếu chỉ có starter-webflux như ví dụ hoàn chỉnh bên dưới thì thông thường không cần khai báo này. Cũng cần nhớ: Reactor Netty có thể được dùng làm **HTTP client WebClient** trong ứng dụng MVC; việc thư viện Netty nằm trên classpath không chứng minh Netty đang phục vụ request đến ứng dụng.

## 3. Các lớp và hook liên quan

~~~mermaid
flowchart TD
    A["SpringApplication / Reactive ApplicationContext"] --> B["ReactiveWebServerFactoryAutoConfiguration"]
    B --> C["NettyReactiveWebServerFactory"]
    D["server.* properties và các factory customizer"] --> C
    E["WebServerFactoryCustomizer<NettyReactiveWebServerFactory>"] --> C
    C --> F["NettyServerCustomizer"]
    F --> G["Reactor Netty HttpServer builder"]
    C --> G
    G --> H["NettyWebServer: bind / start / stop"]
    H --> I["HTTP request -> Spring WebFlux HttpHandler"]
~~~

| Thành phần | Vai trò |
| --- | --- |
| ReactiveWebServerFactory | Giao diện tạo embedded reactive web server |
| NettyReactiveWebServerFactory | Factory do Spring Boot cung cấp cho Reactor Netty |
| WebServerFactoryCustomizer<T> | Hook của Boot cho phép chỉnh factory trước khi server được tạo |
| NettyServerCustomizer | Hàm tùy biến HttpServer của Reactor Netty; nhận HttpServer, trả về HttpServer đã cấu hình |
| HttpServer | Builder dạng fluent của Reactor Netty dùng để định nghĩa server transport/HTTP |
| NettyWebServer | Adapter WebServer do Boot quản lý vòng đời và gắn HttpHandler vào Reactor Netty |
| HttpHandler | Entry point HTTP của Spring WebFlux do framework cung cấp |

**Phân biệt rõ:** NettyReactiveWebServerFactory thuộc package org.springframework.boot.web.embedded.netty; WebServerFactoryCustomizer thuộc org.springframework.boot.web.server; HttpServer thuộc reactor.netty.http.server. NettyServerCustomizer của Spring Boot là adapter để biến đổi HttpServer builder, không phải Servlet Filter hay WebFlux WebFilter.

## 4. Thứ tự lựa chọn cấu hình: property trước, customizer sau

### 4.1 Cấu hình thường dùng bằng application.properties

~~~properties
# Cổng và interface HTTP
server.port=8080
# Chỉ dùng server.address nếu thực sự cần bind một interface cụ thể
# server.address=127.0.0.1

# Giới hạn idle connection trên Netty
server.netty.idle-timeout=30s

# HTTP request decoder
server.netty.max-initial-line-length=4KB
server.max-http-request-header-size=8KB

# Bật nén response khi có lợi
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/plain,text/html
~~~

Các giá trị là ví dụ điều chỉnh; không phải khuyến nghị cố định cho mọi hệ thống. Cần kiểm thử với request thực tế, connection keep-alive, streaming và chính sách proxy/load balancer. Với nhiều ứng dụng, đặt property như trên đã đủ; không cần viết mã Netty riêng.

Một số property đáng chú ý ở Spring Boot 3.3:

| Property | Ý nghĩa |
| --- | --- |
| server.port | HTTP port; 0 yêu cầu hệ điều hành chọn cổng trống |
| server.address | Địa chỉ mạng mà web server bind |
| server.netty.idle-timeout | Thời gian tối đa kênh Netty ở trạng thái idle; nếu không chỉ định có thể chờ không giới hạn |
| server.netty.connection-timeout | Connection timeout của Netty channel; không phải timeout tổng xử lý nghiệp vụ |
| server.netty.max-initial-line-length | Giới hạn chiều dài request line được HTTP decoder chấp nhận |
| server.netty.initial-buffer-size | Kích thước buffer ban đầu cho HTTP request decoding |
| server.netty.validate-headers | Kiểm tra header khi decoding |
| server.netty.max-keep-alive-requests | Số request tối đa có thể dùng trên một connection |
| server.max-http-request-header-size | Giới hạn kích thước header HTTP; cách áp dụng phụ thuộc từng embedded server |
| server.compression.* | Cấu hình nén response, ngưỡng và media type |
| server.ssl.* / server.ssl.bundle | SSL/TLS, certificate, bundle |
| server.http2.enabled | Bật hỗ trợ HTTP/2 nếu tổ hợp server/protocol cho phép |
| server.shutdown | Cơ chế graceful shutdown khi cấu hình tương ứng |
| spring.lifecycle.timeout-per-shutdown-phase | Thời gian cho shutdown phase |

**Không nhầm timeout:** connection timeout, idle timeout, read timeout, request timeout và WebClient response timeout liên quan tới các giai đoạn khác nhau. Không có một property toàn năng có thể giới hạn mọi loại request/connection. Spring Boot property list của từng phiên bản là điểm xác nhận tên và ngữ nghĩa chính xác.

### 4.2 Khi nào cần viết customizer?

Sử dụng customizer khi cần API riêng của Reactor Netty mà Boot không có property tương ứng, hoặc cần gắn một chính sách tổng hợp từ nhiều giá trị cấu hình. Ví dụ: bật Reactor Netty access logging theo điều kiện riêng, wiretap có kiểm soát, hook của TCP channel, hoặc điều chỉnh phần xây dựng HttpServer.

Đừng mặc định chuyển mọi server.* property sang code. Cách dùng property có các lợi ích: cấu hình được theo môi trường, dễ audit, thay đổi không phải build lại, dễ hiểu hơn khi debug.

## 5. WebServerFactoryCustomizer<NettyReactiveWebServerFactory>

API chính:

~~~java
public interface WebServerFactoryCustomizer<T extends WebServerFactory> {
    void customize(T factory);
}
~~~

Trong Spring Boot, có thể đăng ký WebServerFactoryCustomizer thành một Spring bean. Nó được gọi trước khi embedded server khởi động, cho phép chỉnh factory đúng thời điểm.

Ví dụ đơn giản theo Spring Boot 3.3:

~~~java
package com.example.nettydemo;

import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class NettyFactoryCustomizer
        implements WebServerFactoryCustomizer<NettyReactiveWebServerFactory> {

    @Override
    public void customize(NettyReactiveWebServerFactory factory) {
        factory.addServerCustomizers(httpServer ->
                httpServer.idleTimeout(Duration.ofSeconds(30))
                          .accessLog(true));
    }
}
~~~

Giải thích từng lớp:

1. @Component làm class trở thành bean để Spring Boot phát hiện.
2. Generic NettyReactiveWebServerFactory giới hạn customizer cho factory Reactor Netty reactive, không vô tình áp vào Tomcat Servlet factory.
3. factory.addServerCustomizers nhận lambda có kiểu NettyServerCustomizer.
4. Lambda biến đổi HttpServer builder bằng idleTimeout và accessLog; nó **trả về** builder kết quả để Boot tiếp tục xây dựng server.
5. Không có bindNow, không gọi HttpServer.create và không khởi động server thứ hai. Spring Boot vẫn điều phối cổng, HttpHandler, tài nguyên và lifecycle.

NettyServerCustomizer là hook **cấp HttpServer**, còn WebServerFactoryCustomizer là hook **cấp factory**. Đây là sự phân tầng cần hiểu, không phải hai framework server độc lập.

### 5.1 addServerCustomizers hay setServerCustomizers?

NettyReactiveWebServerFactory có các phương thức:

~~~text
addServerCustomizers(NettyServerCustomizer...)
setServerCustomizers(Collection<? extends NettyServerCustomizer>)
getServerCustomizers()
~~~

- addServerCustomizers: **bổ sung** các customizer; phù hợp với phần lớn ứng dụng.
- setServerCustomizers: **thay thế** collection customizer hiện có. Nếu gọi không thận trọng, có thể loại bỏ customizer do Boot hoặc thư viện khác đã thêm.
- getServerCustomizers: trả collection có thể chỉnh sửa, nhưng dùng addServerCustomizers thường diễn đạt ý đồ an toàn và rõ hơn.

Boot tự áp dụng một số customizer của framework. Theo tài liệu Spring Boot 3.3, các WebServerFactoryCustomizer do Boot auto-configure thường có order 0 và chạy trước customizer ứng dụng trừ khi bạn đặt order khác tường minh. Khi nhiều customizer cùng chỉnh một cấu hình, kết quả còn phụ thuộc **thứ tự biến đổi builder**; không suy đoán đơn giản “property luôn thắng” hoặc “code luôn thắng” trong mọi tình huống.

### 5.2 setPort và các thiết lập cấp factory

Nếu ứng dụng cần đổi port bằng code:

~~~java
@Override
public void customize(NettyReactiveWebServerFactory factory) {
    factory.setPort(9090);
    factory.addServerCustomizers(server ->
            server.idleTimeout(Duration.ofSeconds(30)));
}
~~~

Đoạn trên là phương thức minh họa thay cho phần thân customize trong class trước đó, **không phải file Java độc lập**. Tuy nhiên, để đổi port thông thường, hãy dùng server.port=9090; như vậy không cố định cổng trong code và tránh khó khăn khi test RANDOM_PORT. Nếu dùng factory.setPort(9090) phải chú ý thứ tự và tác động lên cấu hình của Spring Boot test, container và môi trường triển khai.

Factory còn cung cấp khả năng cấu hình address, HTTP/2, compression, SSL và lifecycle timeout. Với SSL/certificate, ưu tiên property và SSL bundle thay vì tự xây SslContext trong code nếu không có nhu cầu đặc biệt.

## 6. Tùy chỉnh trực tiếp Reactor Netty HttpServer

Một NettyServerCustomizer biến đổi HttpServer hiện tại và phải trả về phiên bản builder được áp dụng thay đổi.

Ví dụ minh họa:

~~~java
factory.addServerCustomizers(httpServer ->
        httpServer.idleTimeout(Duration.ofSeconds(45))
                  .accessLog(true)
                  .wiretap(false));
~~~

Đây là đoạn bên trong customize(...), không phải một chương trình độc lập. wiretap(false) được viết để minh họa chế độ tắt; mặc định thường đã tắt, nên không cần khai báo nếu chỉ dùng cấu hình chuẩn.

Các API thường dùng:

| HttpServer API | Mục đích | Cần chú ý |
| --- | --- | --- |
| idleTimeout(Duration) | Đóng connection chờ quá lâu khi idle | Không đồng nghĩa timeout xử lý service |
| accessLog(boolean) | Bật/tắt Reactor Netty HTTP access log | Không nên đưa token hoặc dữ liệu riêng tư vào log tùy biến |
| wiretap(boolean) | Ghi log ở mức network để debug | Có thể rất nhiều log, lộ payload/header nhạy cảm |
| compress(boolean) | Bật tính năng nén HTTP response ở Netty | Thường ưu tiên server.compression.* của Boot |
| httpRequestDecoder(...) | Tùy chỉnh parser/decoder request | Tăng giới hạn header/request line cần cân nhắc bảo mật |
| protocol(...) | Tùy chọn protocol HTTP server | Cần khớp HTTP/2, TLS, proxy và client |
| secure(...) | Cấu hình TLS ở mức Netty | Thường ưu tiên server.ssl.* của Boot |
| doOnConnection(...) | Hook khi channel/connection được tạo | Can thiệp pipeline cần hiểu rõ event loop và Netty |
| option(...) / childOption(...) | Thiết lập TCP/channel option | Chỉ chọn option hợp lệ cho server channel/accepted channel |
| metrics(...) | Cấu hình Reactor Netty metrics | Tránh nhãn URI không giới hạn cardinality |

Một số method hoặc overload có thể khác giữa Reactor Netty 1.1.x và 1.2/1.3. Để tránh code không biên dịch, kiểm tra Javadoc và dependency lock của project; không sao chép snippet từ dòng tài liệu mới hơn rồi mặc định dùng được trên Spring Boot 3.3.

### 6.1 Immutable-style fluent configuration

Trong Reactor Netty, các bước cấu hình HttpServer theo mô hình fluent, thường trả về một HttpServer đã cập nhật. Vì vậy mẫu đúng là:

~~~java
factory.addServerCustomizers(server ->
        server.idleTimeout(Duration.ofSeconds(30)));
~~~

Mẫu dễ sai là chỉ gọi một method rồi bỏ qua builder trả về:

~~~java
factory.addServerCustomizers(server -> {
    server.idleTimeout(Duration.ofSeconds(30));
    return server; // Có thể bỏ mất cấu hình trên builder trả về!
});
~~~

Ưu tiên lambda dạng expression để luôn chuyển tiếp HttpServer đã được cấu hình, đặc biệt khi xâu chuỗi nhiều thao tác.

## 7. Ví dụ hoàn chỉnh chạy được với Java 17 và Gradle

Ví dụ dưới đây có một endpoint GET /ping dùng Spring WebFlux; Reactor Netty là embedded server. Chúng ta cấu hình port và compression bằng property, còn idle timeout và access log bằng factory customizer.

### 7.1 Cấu trúc project

~~~text
netty-boot-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/nettydemo/
    │   │   ├── NettyBootApplication.java
    │   │   └── NettyFactoryCustomizer.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/nettydemo/
            └── NettyBootApplicationTests.java
~~~

### 7.2 File settings.gradle

~~~groovy
rootProject.name = 'netty-boot-demo'
~~~

### 7.3 File build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chỉ dùng starter-webflux, **không thêm starter-web**, để tránh Boot chuyển mặc định sang Servlet/MVC. Gradle plugin quản lý dependency đồng bộ trong family Boot 3.3; không tự đặt version React Netty/Netty khác nếu chưa có lý do và kiểm thử tương thích.

### 7.4 File NettyBootApplication.java

~~~java
package com.example.nettydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class NettyBootApplication {

    public static void main(String[] args) {
        SpringApplication.run(NettyBootApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

Một file Java có một public class NettyBootApplication và một package-private class PingController; cả hai thuộc cùng package nên component scan phát hiện controller.

### 7.5 File NettyFactoryCustomizer.java

~~~java
package com.example.nettydemo;

import java.time.Duration;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.stereotype.Component;

@Component
public class NettyFactoryCustomizer
        implements WebServerFactoryCustomizer<NettyReactiveWebServerFactory> {

    @Override
    public void customize(NettyReactiveWebServerFactory factory) {
        factory.addServerCustomizers(server ->
                server.idleTimeout(Duration.ofSeconds(30))
                      .accessLog(true));
    }
}
~~~

Tại thời điểm Spring Boot tạo reactive server, phương thức customize được gọi, bổ sung NettyServerCustomizer vào factory. Reactor Netty sau đó nhận cấu hình idleTimeout và accessLog trên HttpServer builder mà Boot quản lý.

### 7.6 File application.properties

~~~properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=2KB
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

Không khai báo server.netty.idle-timeout ở file này vì code đã đặt 30 giây; điều này giúp tránh hai nguồn cấu hình cùng tác động một tham số trong bài thực hành. Endpoint /ping chỉ trả bốn ký tự nên không có lý do để kỳ vọng response được nén khi min-response-size=2KB.

### 7.7 Chạy và xác nhận

Tại thư mục project, dùng Gradle đã cài hoặc Gradle wrapper nếu project có wrapper:

~~~bash
gradle bootRun
~~~

Trong terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/ping
~~~

Kết quả kỳ vọng là HTTP 200 và response body:

~~~text
pong
~~~

Header cụ thể như Date, Content-Type, Content-Length, Connection có thể phụ thuộc server và nội dung request, vì vậy không khẳng định một tập header cố định cho mọi môi trường. Access log được ghi bởi Reactor Netty logger khi cấu hình logging cho phép; format cụ thể và thời điểm flush phụ thuộc hệ thống log. Dùng log để xác nhận customizer accessLog thực sự có hiệu lực, không coi việc endpoint trả 200 là chứng minh mọi thuộc tính tuning đều đã được áp dụng.

Để chạy bằng cổng khác, truyền tham số của ứng dụng:

~~~bash
gradle bootRun --args='--server.port=9090'
~~~

Vì customizer không gọi factory.setPort, server.port=9090 có thể thay đổi cổng mà không phải sửa code.

## 8. Kiểm thử tích hợp: HTTP server thật và RANDOM_PORT

Test tốt không nên bắt buộc port 8080 còn trống. Spring Boot test có thể chọn một cổng ngẫu nhiên, rồi dùng WebTestClient gọi vào server thực.

File NettyBootApplicationTests.java:

~~~java
package com.example.nettydemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NettyBootApplicationTests {

    @LocalServerPort
    private int port;

    @Test
    void respondsOverEmbeddedNetty() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Test này chứng minh reactive ứng dụng có thể khởi động server HTTP thật trên cổng do hệ điều hành cấp và endpoint trả body như mong đợi. Muốn kiểm chứng **idleTimeout chính xác 30 giây** cần test giữ TCP connection ở trạng thái idle và quan sát việc server đóng connection; một HTTP GET đơn lẻ không đủ.

Nếu dùng @SpringBootTest(webEnvironment = MOCK), server không được bind TCP như RANDOM_PORT, nên không thích hợp cho test đặc tính kết nối Netty.

## 9. Timeout: đừng trộn lẫn bốn khái niệm

### 9.1 Idle timeout

HttpServer.idleTimeout(Duration) giới hạn thời gian connection giữ mở chờ một HTTP request tiếp theo khi idle. Cấu hình thường dùng:

~~~java
factory.addServerCustomizers(server ->
        server.idleTimeout(Duration.ofSeconds(30)));
~~~

Giá trị hợp lý phụ thuộc keep-alive clients và proxy. Đặt quá ngắn có thể tăng reconnect, đặt quá dài có thể giữ connection không cần thiết. Không suy rằng controller xử lý lâu hơn 30 giây sẽ luôn bị chặn bởi idleTimeout; đó không phải giới hạn thời gian xử lý method nghiệp vụ.

### 9.2 Connection timeout

server.netty.connection-timeout là connection timeout của Netty channel theo cách Spring Boot biểu diễn. Nó không đồng nghĩa WebClient.connectTimeout, không bảo đảm giới hạn toàn bộ thời gian đọc HTTP body và không thay thế deadline nghiệp vụ.

### 9.3 HTTP request read timeout

Khi yêu cầu giới hạn tốc độ đọc body hoặc thời gian đọc request toàn phần, cần xem API HttpServer của **đúng Reactor Netty phiên bản**. Dòng tài liệu mới hơn có thể có readTimeout/requestTimeout, nhưng không nên mặc định overload nào cũng có trong 1.1.x. Nếu không dùng được một API mới, hãy chọn giải pháp tương thích với 1.1.x (ví dụ cấu hình pipeline đúng cách hoặc giới hạn tại proxy) và kiểm thử cả upload chậm, request streaming, keep-alive.

Khi dùng Netty pipeline handler như ReadTimeoutHandler, phải hiểu đơn vị, chu kỳ nhận bytes, điều kiện add/remove handler, tương tác với HTTP/2 và pooling; không cài một handler chung theo suy đoán vì dễ đóng nhầm connection hợp lệ.

### 9.4 WebClient timeout là cấu hình khác

WebClient dùng Reactor Netty HttpClient để gọi **ra ngoài**. Tuning server HttpServer không thay đổi HTTP client. Nếu muốn giới hạn thời gian kết nối/response khi gọi upstream, cấu hình ReactorClientHttpConnector, HttpClient hoặc cơ chế reactive timeout tương ứng, thay vì chỉnh NettyReactiveWebServerFactory.

## 10. Nén response và HTTP decoder

### 10.1 Response compression

Spring Boot hỗ trợ response compression trực tiếp bằng:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
server.compression.mime-types=application/json,text/html,text/plain
~~~

Ở mức Reactor Netty có HttpServer.compress(boolean), nhưng ưu tiên dùng server.compression.* để giữ hành vi nhất quán với Boot. Nén chỉ hữu ích khi client gửi Accept-Encoding phù hợp và response đáp ứng kích thước/media type; payload nhỏ có thể không được nén.

Đừng bật nén tùy tiện cho dữ liệu đã nén sẵn, dữ liệu nhạy cảm ở bối cảnh có nguy cơ side channel hoặc streaming mà hiệu quả thấp. Kiểm tra CPU, throughput và latency trước/sau.

### 10.2 HTTP request decoder và giới hạn header

Một số giới hạn thường nên cấu hình qua property:

~~~properties
server.netty.max-initial-line-length=8KB
server.max-http-request-header-size=16KB
server.netty.validate-headers=true
~~~

Tăng giới hạn giúp ứng dụng nhận request có URL hoặc header dài hợp lệ, nhưng cũng tăng bề mặt tiêu tốn tài nguyên và độ khó phòng vệ trước request bất thường. Hãy đối chiếu với proxy/API gateway. Trên Reactor Netty, giới hạn header có ngữ nghĩa khác một số servlet container; không so sánh ngây thơ hai số byte giữa Netty và Tomcat rồi kết luận chúng tương đương.

Có thể dùng httpRequestDecoder(...) trên HttpServer nếu cần API chuyên biệt ngoài các property Boot, nhưng chỉ nên viết code đó sau khi xác nhận overload và syntax của Reactor Netty đang cài.

## 11. Access log, wiretap và khả năng quan sát

### 11.1 HTTP access log

Để bật access log theo API Reactor Netty:

~~~java
factory.addServerCustomizers(server -> server.accessLog(true));
~~~

Đoạn này phải nằm trong phương thức customize của factory customizer; bản thân nó không phải class độc lập. Có thể cấu hình logger:

~~~properties
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

Access log tập trung vào yêu cầu HTTP: method, URI, status, kích thước và các thuộc tính khác tùy formatter. Không ghi toàn bộ JWT, Authorization header, cookie/session và các dữ liệu cá nhân vào mẫu log tùy chỉnh. Với high traffic, cân nhắc async appenders, log rotation và chi phí I/O.

Reactor Netty cũng hỗ trợ bật access log qua system property reactor.netty.http.server.accessLogEnabled khi môi trường hỗ trợ. Khi có cấu hình programmatic accessLog(...), thứ tự và ưu tiên cần được kiểm chứng theo đúng phiên bản Reactor Netty.

### 11.2 Wiretap để debug ở mức network

HttpServer.wiretap(true) giúp quan sát dữ liệu network chi tiết. Nó hữu ích khi đang điều tra lỗi protocol, nhưng có thể tạo log lớn và lộ HTTP payload hoặc header nhạy cảm.

Ví dụ **chỉ bật ở môi trường thử nghiệm có kiểm soát**:

~~~java
factory.addServerCustomizers(server -> server.wiretap(true));
~~~

Ngoài việc gọi wiretap(true), phải bật logging level phù hợp cho logger Reactor Netty; nếu không có thể không nhìn thấy thông tin mong muốn. Tắt sau khi điều tra; không khuyến khích bật không giới hạn trong production.

### 11.3 Metrics và tracing

Spring Boot Actuator/Micrometer và Reactor Netty có các khả năng metrics khác nhau. Việc dùng WebServerFactoryCustomizer không tự tạo một endpoint /actuator/prometheus. Nếu cần Prometheus, phải thêm dependency và cấu hình exposure, registry, quyền truy cập phù hợp. Không tạo metric tag từ raw URL path có ID/UUID không giới hạn, vì có thể gây nổ cardinality.

## 12. TLS, HTTP/2 và reverse proxy

### 12.1 TLS bằng cấu hình Boot

Đối với HTTPS, ưu tiên Spring Boot SSL properties/SSL bundle:

~~~properties
server.port=8443
server.ssl.bundle=server
~~~

Đoạn này **chỉ là ví dụ thuộc tính tham chiếu đến SSL bundle mang tên server**. Ứng dụng phải khai báo bundle thực tế và cung cấp certificate/key hợp lệ; chỉ đặt hai dòng trên không tạo chứng chỉ. Thông tin bí mật nên được quản lý qua secret store hoặc cấu hình triển khai, không commit password/khóa riêng vào repo.

Spring Boot cũng hỗ trợ server.ssl.key-store và các thuộc tính liên quan khi dùng Java KeyStore. Đừng đồng thời trộn cấu hình bundle với các thuộc tính key-store rời không tương thích.

### 12.2 HTTP/2

~~~properties
server.http2.enabled=true
~~~

HTTP/2 hoạt động đúng cần có tổ hợp protocol, TLS/ALPN nếu cần h2 qua TLS, dependency và client hỗ trợ. Reactor Netty có thể phục vụ h2c và h2 tùy cấu hình. Không chỉ đặt protocol(...) trên HttpServer rồi quên TLS hoặc làm xung đột các thiết lập mà Boot đã chọn.

### 12.3 Forwarded headers sau load balancer

Nếu chạy sau reverse proxy, ứng dụng có thể thấy remote address và scheme nội bộ thay vì HTTPS client-facing. Spring Boot có các chiến lược xử lý forwarded headers, ví dụ:

~~~properties
server.forward-headers-strategy=framework
~~~

Giá trị native hoặc framework có hành vi khác nhau tùy stack và phiên bản. NettyReactiveWebServerFactory cũng có setUseForwardHeaders(boolean), nhưng cần tránh tự bật lặp nhiều cơ chế mà chưa hiểu tác động.

**Cảnh báo an toàn:** không tin các header X-Forwarded-* hoặc Forwarded từ client không đáng tin. Cấu hình proxy phải loại bỏ/ghi đè header giả mạo và chỉ cung cấp forwarded information từ hop tin cậy; kiểm thử scheme, host, redirect URL và client IP trước khi đưa vào production.

## 13. Tài nguyên Netty: event loop, connection và memory

Netty hoạt động dựa trên event loop và non-blocking I/O. Cấu hình server đúng không đủ nếu controller hay service gọi JDBC/blocking HTTP/disk I/O trực tiếp trên event-loop thread trong thời gian dài.

Những điều cần cân nhắc:

- Tránh block() và các thao tác blocking kéo dài trên Netty event loop.
- Nếu phải tích hợp thư viện blocking, tách ra scheduler phù hợp có giới hạn tài nguyên và hiểu chi phí chuyển thread.
- Theo dõi event-loop saturation, connection count, memory trực tiếp và heap khi tăng throughput.
- Điều chỉnh số event loop, native transport và tài nguyên Reactor Netty theo kiểm thử tải, không dựa vào giá trị ngẫu nhiên trên Internet.
- Tránh tự tạo/dispose LoopResources trong request handler; tài nguyên server phải sống theo vòng đời ứng dụng.
- Nếu customizing ReactorResourceFactory qua factory.setResourceFactory(...), phải xác định rõ ownership/lifecycle và việc chia sẻ tài nguyên với HttpClient. Đừng ghi đè resource factory chỉ để thay đổi port hay idle timeout.

NettyReactiveWebServerFactory có setResourceFactory(ReactorResourceFactory) và setLifecycleTimeout(Duration). Đây là hook nâng cao. Factory được Boot quản lý thường đã được cấu hình để phối hợp server resource và shutdown; thay thế không có kế hoạch có thể dẫn tới thread leak, shutdown treo hoặc cấu hình client/server không nhất quán.

## 14. Customizer được áp dụng lúc nào và theo thứ tự nào?

WebServerFactoryCustomizer bean được xử lý trong giai đoạn sớm của ApplicationContext lifecycle. Khi đó factory chưa bind server. Boot dùng BeanPostProcessor để áp dụng các customizer, rồi sau đó server được tạo.

Điểm cần nhớ:

1. **Các customizer bean có thứ tự**: @Order/Ordered có thể ảnh hưởng thời điểm chạy. Không đổi order để “chữa cháy” khi chưa hiểu customizer nào đang chỉnh cùng thuộc tính.
2. **NettyServerCustomizer có thứ tự áp dụng bên trong factory**: addServerCustomizers thêm vào collection hiện tại. Hai callback cùng chỉnh idleTimeout có thể tạo kết quả phụ thuộc thứ tự.
3. **Bean khởi tạo sớm**: không nên inject một graph bean nặng vào WebServerFactoryCustomizer nếu nó gây eager initialization, circular dependency hoặc sử dụng web server trước khi được tạo.
4. **Tùy chỉnh final** cần đối chiếu với các server.* properties và auto-configured factory customizers.
5. **Tự tạo NettyReactiveWebServerFactory bean** là phương án cuối cùng; auto-configured customizers có thể vẫn được áp dụng, nhưng bạn phải chịu trách nhiệm về lifecycle/resource và các thuộc tính mặc định.

Không có lý do thông thường để gọi factory.getWebServer(...) bằng tay từ @Configuration hay service. Đây là nhiệm vụ của Boot khi khởi tạo web application context.

## 15. Khi nào Netty customization không có hiệu lực?

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Application báo embedded Tomcat thay vì Netty | Có spring-boot-starter-web khiến Boot chọn SERVLET không? |
| Bean customizer không được gọi | Bean có nằm trong component scan? Có đúng generic NettyReactiveWebServerFactory? Có thực sự dùng Reactor Netty reactive? |
| Đặt idle timeout nhưng thấy connection sống lâu | Đang nhìn HTTP server connection hay WebClient connection? Có proxy/keep-alive? Có HTTP/2 multiplexing? |
| server.port đổi không có hiệu lực | Có customizer factory.setPort khác, command-line args hoặc môi trường áp dụng không? |
| Set accessLog nhưng không thấy log | Có accessLog(true), logger INFO và log appender phù hợp không? |
| wiretap bật nhưng thiếu log | Logging level/category có phù hợp không? |
| Header quá dài bị HTTP 431/400 | Kiểm tra decoder/header limit trên server và các lớp proxy phía trước |
| HTTPS không chạy | Có chứng chỉ/SSL bundle hợp lệ, server.port và protocol tương ứng không? |
| HTTP/2 không hoạt động | Cấu hình HTTP/2, ALPN, TLS/h2c, proxy và client |
| CPU cao dù Netty non-blocking | Có blocking trên event loop, logger đồng bộ, nén/crypto hoặc metric cardinality cao không? |
| Khởi động lỗi missing ReactiveWebServerFactory | Kiểm tra starter-webflux/reactor-netty runtime dependency, WebApplicationType và auto-configuration |
| Startup lỗi port already in use | Kiểm tra cổng đang LISTEN và PID; thay đổi cổng hoặc dừng đúng instance cũ |
| Trong test bean/cổng sai | Dùng RANDOM_PORT, không hard-code factory.setPort và xác nhận đúng test profile |

Cần phân biệt lỗi **không khởi động được server** với lỗi **server khởi động nhưng request không đến đúng route**. Nếu nhận 404 tại /unknown, server có thể vẫn hoạt động bình thường; xem path, mapping và proxy trước khi đổ lỗi cho Netty factory.

## 16. Cách debug khi tùy chỉnh không có tác dụng

### 16.1 Kiểm tra runtime classpath

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Tìm spring-boot-starter-webflux, spring-boot-starter-reactor-netty và bảo đảm không vô tình kéo spring-boot-starter-web vào nếu mong muốn Boot chọn REACTIVE tự động.

### 16.2 Xem báo cáo điều kiện auto-configuration

~~~bash
gradle bootRun --args='--debug'
~~~

Kiểm tra ReactiveWebServerFactoryAutoConfiguration, NettyReactiveWebServerFactory, loại web application, và các auto-configuration có match hay không. Log debug có thể chứa cấu hình nhạy cảm; lọc trước khi chia sẻ.

### 16.3 Kiểm tra cổng đang nghe

Trên Linux:

~~~bash
ss -ltnp 'sport = :8080'
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Lệnh chỉ cho biết socket, không khẳng định Netty customizer đã được áp dụng. Kết hợp log, endpoint test và các phép thử riêng của tính năng được tuning.

### 16.4 Kiểm tra hành vi tương ứng với từng tùy chỉnh

- Đổi port: dùng curl đúng cổng mới.
- Access log: bật logger rồi gửi request và xem log.
- Idle timeout: giữ connection keep-alive idle qua thời gian cấu hình, quan sát close.
- Compression: gửi Accept-Encoding phù hợp với response đủ lớn; xem Content-Encoding và tải CPU.
- Header limit: gửi request có header ở gần giới hạn, xác minh phản hồi không làm cạn tài nguyên.
- TLS: xác nhận certificate chain, hostname và protocol thực tế bằng client chuẩn.
- HTTP/2: kiểm tra negotiated protocol qua client/proxy phù hợp.

Tránh chỉ nhìn vào một bean đã tồn tại rồi đánh dấu “tuning thành công”; phải kiểm thử **hành vi runtime**.

## 17. Một số lỗi thiết kế cần tránh

### Lỗi 1: Khởi động server thứ hai trong customizer

~~~java
// Sai ý đồ với Spring Boot embedded web server:
HttpServer.create().port(9090).bindNow();
~~~

Lệnh này mở một listener do bạn quản lý, không tự gắn Spring WebFlux HttpHandler, lifecycle, Actuator và cổng server.port của Boot. Đặc biệt nguy hiểm khi gọi trong bean startup và vô tình chiếm port.

**Đúng:** đăng ký WebServerFactoryCustomizer và trả về HttpServer builder đã tùy chỉnh, để Boot start/stop server.

### Lỗi 2: Thay toàn bộ server customizer collection khi chỉ muốn thêm một hook

~~~java
// Không nên dùng để bổ sung một thiết lập nếu không muốn thay customizer cũ:
factory.setServerCustomizers(java.util.List.of(
        server -> server.idleTimeout(Duration.ofSeconds(30))));
~~~

Đoạn trên chỉ minh họa trong phương thức customize. Nó có thể loại các customizer đã có. Thường dùng addServerCustomizers.

### Lỗi 3: Dùng code server để cấu hình WebClient

HttpServer và HttpClient là hai API khác nhau. Cấu hình idleTimeout của server không điều chỉnh thời gian response của client gọi upstream.

### Lỗi 4: Dựa vào classpath mà quên loại ứng dụng

Có WebFlux API và reactor-netty artifact không chứng minh Spring Boot chọn REACTIVE nếu starter-web cũng có mặt.

### Lỗi 5: Bật wiretap trong production không giới hạn

Wiretap có thể ghi dữ liệu rất chi tiết, làm tăng chi phí I/O và gây lộ thông tin nhạy cảm.

### Lỗi 6: Vô tình vượt quyền sở hữu tài nguyên

Tạo/dispose LoopResources hoặc server riêng ngoài Boot có thể làm rò thread, xung đột cổng, lỗi graceful shutdown hoặc khó kiểm soát lịch trình khởi động.

## 18. Checklist triển khai thực tế

1. Xác nhận ứng dụng chạy **WebFlux + Reactor Netty** (không chỉ có WebClient).
2. Thử cấu hình server.* chuẩn trước.
3. Chỉ dùng WebServerFactoryCustomizer khi cần API sâu hơn.
4. Sử dụng addServerCustomizers thay vì ghi đè collection nếu chỉ bổ sung hook.
5. Trong lambda, trả về HttpServer sau khi biến đổi; không gọi bindNow.
6. Ghi rõ lý do và thứ tự của các customizer có khả năng xung đột.
7. Dùng property/SSL bundle cho cổng, SSL, HTTP/2, compression nếu khả thi.
8. Xác định timeout ứng với giai đoạn kết nối/request/response nào.
9. Tránh ghi token hoặc payload nhạy cảm trong access log/wiretap.
10. Giữ nguyên lifecycle của tài nguyên Reactor Netty được Boot quản lý nếu không có yêu cầu đặc biệt.
11. Tạo test RANDOM_PORT + HTTP request thật.
12. Test từng tính năng server theo hành vi quan sát được, không chỉ việc compile.

## 19. Tóm tắt

**NettyReactiveWebServerFactory** là cầu nối giữa Spring Boot reactive web application và embedded Reactor Netty server. **WebServerFactoryCustomizer** chỉnh factory trước khi server bắt đầu; **NettyServerCustomizer** là cách thích hợp để biến đổi **HttpServer builder** bên trong quá trình dựng server. Mặc định nên cấu hình server.* properties; dùng customizer cho trường hợp sâu hơn. Hãy để Boot giữ quyền tạo/bind/start/stop server và kiểm thử cấu hình bằng runtime behavior thực tế.

## 20. Tài liệu tham khảo

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — NettyReactiveWebServerFactory Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor Netty — HTTP Server Reference (chọn version khớp Reactor Netty trong project): https://projectreactor.io/docs/netty/release/reference/http-server.html
