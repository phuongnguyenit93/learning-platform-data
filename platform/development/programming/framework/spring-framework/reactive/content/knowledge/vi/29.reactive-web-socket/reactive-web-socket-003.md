# Đăng ký đường dẫn cho handler và cấu hình handshake

Spring WebFlux cung cấp API WebSocket reactive để xây dựng kết nối hai chiều giữa client và server. Một kết nối WebSocket bắt đầu bằng HTTP handshake: client gửi một HTTP GET kèm các header Upgrade, Connection, Sec-WebSocket-Key và Sec-WebSocket-Version; server kiểm tra request rồi nâng cấp kết nối. Khi handshake thành công, server trả status 101 Switching Protocols và hai phía trao đổi message trên cùng một kết nối.

Trong WebFlux, WebSocket endpoint không được đăng ký bằng annotation controller như một REST route thông thường. Ứng dụng tạo một đối tượng WebSocketHandler, ánh xạ URL tới handler bằng HandlerMapping (thường là SimpleUrlHandlerMapping), sau đó WebSocketHandlerAdapter chuyển request handshake tới WebSocketService. WebSocketService mặc định dùng HandshakeWebSocketService, và service này gọi RequestUpgradeStrategy tương ứng với server engine đang chạy.

Bài này tập trung vào đăng ký đường dẫn, thứ tự HandlerMapping, cấu hình handshake, subprotocol, origin/CORS, session attributes, giới hạn frame và cách kiểm thử một WebSocket endpoint bằng client reactive.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích luồng HTTP Upgrade và status 101 của WebSocket handshake.
2. Tạo WebSocketHandler xử lý inbound và outbound message theo kiểu reactive.
3. Đăng ký nhiều URL bằng SimpleUrlHandlerMapping.
4. Chọn order để WebSocket mapping được xét trước annotated controller mapping.
5. Hiểu vai trò của WebSocketHandlerAdapter và WebSocketService.
6. Cấu hình HandshakeWebSocketService qua WebFluxConfigurer.
7. Chọn RequestUpgradeStrategy theo Reactor Netty, Tomcat hoặc Jetty.
8. Thương lượng subprotocol bằng WebSocketHandler.getSubProtocols().
9. Kiểm soát Origin bằng CorsConfigurationSource hoặc CORS mapping.
10. Chuyển một số WebSession attributes vào WebSocketSession.
11. Giới hạn frame size và hiểu ping/pong, compression.
12. Bảo vệ handshake bằng authentication, authorization và origin allowlist.
13. Kiểm thử handshake, subprotocol, message echo và origin rejection.

## 2. WebSocket handshake hoạt động thế nào?

WebSocket sử dụng HTTP để bắt đầu kết nối. Client gửi một GET request với các header đặc biệt:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1
Origin: https://app.example.test
~~~

Các header có ý nghĩa:

| Header | Vai trò |
| --- | --- |
| Upgrade | Yêu cầu chuyển giao thức sang websocket |
| Connection | Báo rằng Upgrade là hop-by-hop connection option |
| Sec-WebSocket-Key | Nonce do client tạo để server xác minh handshake |
| Sec-WebSocket-Version | Phiên bản WebSocket protocol, thường là 13 |
| Sec-WebSocket-Protocol | Các subprotocol client muốn thương lượng |
| Origin | Origin của trang khởi tạo kết nối, quan trọng với browser client |

Nếu handshake hợp lệ, server trả response dạng:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
Sec-WebSocket-Protocol: chat.v1
~~~

Status 101 cho biết kết nối đã được nâng cấp. Sau thời điểm này, hai bên gửi frame WebSocket trên kết nối đang mở; đây không còn là chuỗi request/response HTTP thông thường.

Handshake có thể thất bại nếu method/header/version không hợp lệ, origin bị từ chối, xác thực thất bại, endpoint không tồn tại hoặc server engine không thể nâng cấp connection.

## 3. Các thành phần WebSocket server của WebFlux

Một endpoint WebFlux thường gồm bốn thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| WebSocketHandler | Xử lý message trong một session |
| HandlerMapping | Ánh xạ URL đến WebSocketHandler |
| WebSocketHandlerAdapter | Kết nối handler với DispatcherHandler |
| WebSocketService | Xử lý handshake và gọi upgrade strategy |

Luồng request:

~~~text
HTTP GET /ws/echo
       |
       v
DispatcherHandler
       |
       v
SimpleUrlHandlerMapping
       |
       v
WebSocketHandlerAdapter
       |
       v
WebSocketService
       |
       v
HandshakeWebSocketService
       |
       v
RequestUpgradeStrategy
       |
       v
WebSocketHandler.handle(session)
       |
       v
WebSocket messages
~~~

Trong ứng dụng dùng WebFlux Java configuration (bao gồm cấu hình WebFlux do Spring Boot cung cấp), WebSocketHandlerAdapter được đăng ký sẵn. Ứng dụng chỉ cần map WebSocketHandler vào URL. Nếu không dùng WebFlux configuration, phải tự khai báo adapter.

Không cần thêm @EnableWebFlux chỉ để đăng ký WebSocket handler trong Spring Boot. Implement WebFluxConfigurer để tùy biến cấu hình mà vẫn giữ cơ chế auto-configuration của Boot.

## 4. Tạo WebSocketHandler

Interface WebSocketHandler có phương thức:

~~~java
Mono<Void> handle(WebSocketSession session);
~~~

Publisher Mono<Void> thể hiện vòng đời xử lý session. Session có hai stream chính:

| API | Mô tả |
| --- | --- |
| session.receive() | Flux<WebSocketMessage> chứa message client gửi |
| session.send(Publisher<WebSocketMessage>) | Gửi message server tạo ra |
| session.close() | Đóng WebSocket session |
| session.getHandshakeInfo() | Thông tin handshake, URI, headers, principal, subprotocol và attributes |
| session.getAttributes() | Attributes được gắn với session |

Handler phải ghép inbound và outbound thành một reactive flow và trả về publisher đại diện cho công việc. Không tự subscribe vào receive hoặc send; WebFlux cần kiểm soát subscription, cancellation và đóng session.

### 4.1. Handler echo text

Ví dụ sau nhận text message và gửi lại với tiền tố echo:

~~~java
final class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(message ->
                session.textMessage(
                    "echo: " + message.getPayloadAsText()
                )
            );

        return session.send(replies);
    }
}
~~~

Handler này giả định client gửi text message. Nếu endpoint phải nhận binary message, cần kiểm tra message type và xử lý payload binary riêng.

Luồng trên giữ backpressure: server chỉ tạo output theo inbound publisher và nhu cầu downstream. Khi client đóng kết nối, receive hoàn tất; send cũng hoàn tất và Mono<Void> kết thúc.

### 4.2. Ghép input và output độc lập

Một handler có thể nhận dữ liệu và gửi một nguồn dữ liệu khác:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
        .concatMap(message -> processIncoming(message))
        .then();

    Flux<String> notifications = notificationSource();

    Mono<Void> output = session.send(
        notifications.map(session::textMessage)
    );

    return input.and(output);
}
~~~

Đây là mẫu minh họa; processIncoming và notificationSource là API nghiệp vụ của ứng dụng. Operator and ghép vòng đời hai luồng. Khi một luồng kết thúc, publisher tổng thể kết thúc và luồng còn lại được cancellation theo semantics của operator.

Không dùng block hoặc subscribe trong handler. Nếu phải gọi database/network, ưu tiên API reactive; nếu có thao tác blocking, chuyển sang scheduler phù hợp và quản lý giới hạn concurrency.

## 5. Đăng ký đường dẫn bằng SimpleUrlHandlerMapping

WebFlux dùng HandlerMapping để tìm handler theo URL. Cách thông dụng là tạo map từ path đến WebSocketHandler:

~~~java
@Configuration
class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        int order = -1; // trước annotated controller mappings

        return new SimpleUrlHandlerMapping(handlers, order);
    }

    @Bean
    EchoWebSocketHandler echoWebSocketHandler() {
        return new EchoWebSocketHandler();
    }
}
~~~

SimpleUrlHandlerMapping nhận URL map và order. Có thể đăng ký nhiều endpoint:

~~~java
Map<String, WebSocketHandler> handlers = new HashMap<>();
handlers.put("/ws/chat", chatHandler);
handlers.put("/ws/notifications", notificationHandler);
handlers.put("/ws/echo", echoHandler);

return new SimpleUrlHandlerMapping(handlers, -1);
~~~

### 5.1. Vì sao order thường là -1?

Spring WebFlux có nhiều HandlerMapping. Annotated controller mapping cũng tìm URL cho các method có @GetMapping, @PostMapping và annotation liên quan.

WebSocket mapping thường được đặt order -1 để được xét trước mapping của annotated controller. Nếu hai mapping cùng có thể khớp một path, thứ tự có thể quyết định handler nào nhận request.

Không đặt hai handler khác nhau cùng một URL mà không có quy tắc ưu tiên rõ ràng. Nên dành prefix riêng như /ws/** cho WebSocket endpoint và /api/** cho REST endpoint để route dễ hiểu.

### 5.2. URL pattern

SimpleUrlHandlerMapping hỗ trợ URL pattern. Ví dụ:

~~~java
handlers.put("/ws/**", chatHandler);
~~~

Dùng pattern rộng chỉ khi một handler thực sự có thể phục vụ mọi path bên dưới. Nếu cần nhiều handler theo tenant, room hoặc chức năng, có thể dùng nhiều pattern cụ thể hoặc một handler đọc path/handshake metadata và kiểm tra quyền.

Đăng ký route không đồng nghĩa với việc endpoint đã được bảo vệ. Mỗi path vẫn cần authentication, authorization và kiểm soát origin phù hợp.

## 6. WebSocketHandlerAdapter và WebFlux configuration

WebSocketHandlerAdapter là HandlerAdapter dành cho handler kiểu WebSocketHandler. Trong ứng dụng dùng WebFlux configuration, adapter được khai báo sẵn.

Nếu không dùng WebFlux configuration, có thể khai báo thủ công:

~~~java
@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter() {
    return new WebSocketHandlerAdapter();
}
~~~

Nếu cần custom WebSocketService, adapter có constructor nhận service:

~~~java
@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter(
        WebSocketService webSocketService) {
    return new WebSocketHandlerAdapter(webSocketService);
}
~~~

Không tạo thêm adapter thứ hai khi WebFlux configuration đã đăng ký adapter mặc định. Thay vào đó, override WebFluxConfigurer.getWebSocketService() để cung cấp service tùy biến.

## 7. HandshakeWebSocketService

WebSocketHandlerAdapter ủy quyền handshake cho WebSocketService. Mặc định WebFlux dùng HandshakeWebSocketService.

Service này thực hiện các kiểm tra handshake cơ bản rồi gọi RequestUpgradeStrategy phù hợp với server engine hiện tại. Các server được hỗ trợ có thể gồm Reactor Netty, Tomcat và Jetty; danh sách cụ thể phụ thuộc phiên bản Spring Framework.

HandshakeWebSocketService có constructor mặc định tự phát hiện strategy từ classpath:

~~~java
HandshakeWebSocketService service =
    new HandshakeWebSocketService();
~~~

Hoặc truyền strategy cụ thể:

~~~java
HandshakeWebSocketService service =
    new HandshakeWebSocketService(requestUpgradeStrategy);
~~~

### 7.1. Tùy biến qua WebFluxConfigurer

Khi dùng WebFlux Java configuration, override getWebSocketService():

~~~java
@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}
~~~

Ví dụ này giữ strategy tự phát hiện và chỉ cấu hình việc copy session attributes. Nó không tạo một adapter mới.

### 7.2. Session attribute predicate

WebSocket handshake có thể dùng WebSession đã tồn tại trước đó. HandshakeWebSocketService cho phép chọn các key của WebSession để đưa vào WebSocketSession attributes:

~~~java
service.setSessionAttributePredicate(
    name -> name.startsWith("ws.")
);
~~~

Nếu WebSession có các key ws.userId và ws.tenantId, predicate trên cho phép chúng được copy vào attributes của WebSocketSession. Các key khác không được copy.

Cơ chế này chỉ chuyển attributes. Nó không xác thực người dùng, không tự tạo tenant context và không thay thế authorization. Ứng dụng phải đặt các giá trị đó vào WebSession từ một nguồn đã được xác thực trước handshake.

## 8. RequestUpgradeStrategy và cấu hình server engine

RequestUpgradeStrategy là abstraction để Spring thực hiện HTTP-to-WebSocket upgrade trên server engine cụ thể.

- ReactorNettyRequestUpgradeStrategy dành cho Reactor Netty.
- TomcatRequestUpgradeStrategy dành cho Tomcat.
- JettyRequestUpgradeStrategy dành cho Jetty.

Các tùy chọn không giống nhau giữa server. Chỉ cấu hình strategy của engine mà ứng dụng thực sự chạy.

### 8.1. Ví dụ Reactor Netty: giới hạn frame payload

Reactor Netty cho phép tạo strategy với WebsocketServerSpec.Builder:

~~~java
ReactorNettyRequestUpgradeStrategy strategy =
    new ReactorNettyRequestUpgradeStrategy(
        () -> WebsocketServerSpec.builder()
            .maxFramePayloadLength(128 * 1024)
    );

HandshakeWebSocketService service =
    new HandshakeWebSocketService(strategy);
~~~

Ví dụ đặt giới hạn payload mỗi frame là 128 KiB. Đây là giới hạn frame, không phải giới hạn tổng dữ liệu một session có thể trao đổi. Nếu message lớn hơn, client có thể cần chia dữ liệu thành nhiều frame hoặc ứng dụng cần chọn giới hạn phù hợp.

Reactor Netty builder cũng có các tùy chọn liên quan ping handling và compression. Chỉ bật compression khi có nhu cầu và đã đánh giá chi phí CPU, memory cùng rủi ro bảo mật của dữ liệu nén.

### 8.2. Ví dụ Tomcat: idle timeout

Nếu ứng dụng chạy trên Tomcat và muốn tùy biến idle timeout, Spring có ví dụ:

~~~java
TomcatRequestUpgradeStrategy strategy =
    new TomcatRequestUpgradeStrategy();

strategy.setMaxSessionIdleTimeout(60_000L);

HandshakeWebSocketService service =
    new HandshakeWebSocketService(strategy);
~~~

Giá trị 60.000 ms tương đương 60 giây. Đây là ví dụ riêng cho Tomcat; không dùng API này khi server là Reactor Netty.

### 8.3. Tích hợp strategy vào WebFluxConfigurer

Với Reactor Netty, có thể kết hợp giới hạn frame và session attribute predicate:

~~~java
@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        ReactorNettyRequestUpgradeStrategy strategy =
            new ReactorNettyRequestUpgradeStrategy(
                () -> WebsocketServerSpec.builder()
                    .maxFramePayloadLength(128 * 1024)
            );

        HandshakeWebSocketService service =
            new HandshakeWebSocketService(strategy);

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}
~~~

Đây là cấu hình dành cho ứng dụng thực sự chạy Reactor Netty. Nếu chuyển sang Tomcat hoặc Jetty, chọn RequestUpgradeStrategy tương ứng.

## 9. Thương lượng subprotocol

WebSocket protocol cho phép hai phía thương lượng subprotocol qua header Sec-WebSocket-Protocol.

Client có thể gửi:

~~~http
Sec-WebSocket-Protocol: chat.v1, chat.v2
~~~

Handler khai báo các protocol server hỗ trợ bằng:

~~~java
@Override
public List<String> getSubProtocols() {
    return List.of("chat.v1", "chat.v2");
}
~~~

Spring chọn protocol phù hợp trong danh sách client đề xuất và server hỗ trợ. Protocol được chọn có thể đọc qua:

~~~java
String protocol =
    session.getHandshakeInfo().getSubProtocol();
~~~

Subprotocol định nghĩa hợp đồng message ở tầng ứng dụng, ví dụ format JSON chat, STOMP hoặc một protocol nghiệp vụ riêng. Nó không thay thế WebSocket framing và cũng không phải extension nén.

Nếu ứng dụng yêu cầu một subprotocol bắt buộc, hãy kiểm tra kết quả thương lượng và từ chối session nếu không có protocol phù hợp. Không giả định mọi client đều gửi header này.

## 10. Kiểm soát Origin và CORS

Browser gửi header Origin trong WebSocket handshake. Server cần quyết định origin nào được phép kết nối.

Trong WebFlux, cách trực tiếp là để WebSocketHandler implement CorsConfigurationSource:

~~~java
final class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    EchoWebSocketHandler() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        config.setAllowedMethods(List.of("GET"));
        this.corsConfiguration = config;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return this.corsConfiguration;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()
                ))
        );
    }
}
~~~

Chỉ origin https://app.example.test được phép theo cấu hình này. Trong production, dùng danh sách origin chính xác; không bật wildcard chỉ để sửa lỗi kết nối.

### 10.1. Cấu hình CORS theo URL pattern

Nếu không muốn handler implement CorsConfigurationSource, có thể đặt CORS mapping trên SimpleUrlHandlerMapping:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(
    List.of("https://app.example.test")
);
cors.setAllowedMethods(List.of("GET"));

Map<String, CorsConfiguration> corsMap = new HashMap<>();
corsMap.put("/ws/**", cors);

SimpleUrlHandlerMapping mapping =
    new SimpleUrlHandlerMapping(handlers, -1);

mapping.setCorsConfigurations(corsMap);
~~~

Nếu cả handler và mapping cùng cung cấp CORS configuration, Spring kết hợp chúng theo quy tắc CorsConfiguration.combine. Hãy tránh các cấu hình chồng chéo không chủ ý.

### 10.2. Origin không phải authentication

Origin validation chủ yếu bảo vệ browser client khỏi việc một trang không được phép mở kết nối tới endpoint. Client không phải browser có thể tự gửi Origin header tùy ý.

Do đó:

- Xác thực principal bằng Spring Security hoặc cơ chế tương đương.
- Kiểm tra principal có quyền truy cập room, tenant hoặc resource yêu cầu.
- Dùng origin allowlist cho browser.
- Không xem Origin là bằng chứng nhận dạng người dùng.
- Không đưa token nhạy cảm vào query string vì URL có thể xuất hiện trong log/proxy history.
- Nếu dùng cookie/session authentication, cân nhắc rủi ro cross-site WebSocket hijacking và chính sách cookie phù hợp.

## 11. Xác thực và authorization ở handshake

Handshake là một HTTP GET trước khi protocol được nâng cấp. Spring Security WebFlux có thể bảo vệ path như endpoint HTTP thông thường.

Ví dụ cấu hình security mang tính minh họa:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/ws/**").authenticated()
            .anyExchange().permitAll()
        )
        .build();
}
~~~

Cấu hình thực tế còn phụ thuộc authentication mechanism, CSRF policy và các endpoint khác. Sau handshake, handler vẫn phải kiểm tra quyền trên từng thao tác nhạy cảm, chẳng hạn subscribe vào room hoặc gửi message tới tenant khác.

Không phải cứ handshake thành công là user được phép thực hiện mọi hành động trên session. Authorization có thể cần kiểm tra lại khi message mang room ID hoặc resource ID.

## 12. Client gửi subprotocol và mở kết nối

Spring WebFlux cung cấp WebSocketClient abstraction. Với Reactor Netty:

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("ws://localhost:8080/ws/echo");

client.execute(uri, session ->
    session.send(Mono.just(session.textMessage("hello")))
        .then(
            session.receive()
                .take(1)
                .doOnNext(message ->
                    System.out.println(message.getPayloadAsText())
                )
                .then()
        )
);
~~~

Đoạn code gửi một text message và đọc một response. Trong ứng dụng thực tế, ghép send/receive theo lifecycle session và subscribe bằng tầng gọi. Không gọi block trên event loop.

Nếu cần gửi header handshake như Origin hoặc Sec-WebSocket-Protocol, dùng overload execute nhận HttpHeaders:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.set("Origin", "https://app.example.test");
headers.set("Sec-WebSocket-Protocol", "chat.v1");

client.execute(uri, headers, session ->
    session.receive().then()
);
~~~

Client phải offer đúng subprotocol mà server hỗ trợ. Khi handshake thành công, client có thể kiểm tra session.getHandshakeInfo().getSubProtocol().

## 13. Ví dụ Java 17 chạy được với Spring Boot WebFlux

Ví dụ dùng Java 17, Spring Boot 3.3.5 và Reactor Netty. Nó đăng ký endpoint /ws/echo, chỉ chấp nhận origin đã cấu hình, thương lượng subprotocol chat.v1 và giới hạn frame payload.

### 13.1. Cấu trúc dự án

~~~text
webflux-websocket-demo/
├── build.gradle
├── src/main/java/demo/WebSocketApplication.java
└── src/test/java/demo/WebSocketIntegrationTest.java
~~~

### 13.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 13.3. WebSocketApplication.java

~~~java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.server.WebSocketService;
import org.springframework.web.reactive.socket.server.support.HandshakeWebSocketService;
import org.springframework.web.reactive.socket.server.upgrade.ReactorNettyRequestUpgradeStrategy;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import reactor.netty.http.server.WebsocketServerSpec;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}

@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Bean
    EchoWebSocketHandler echoWebSocketHandler() {
        return new EchoWebSocketHandler();
    }

    @Bean
    HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        return new SimpleUrlHandlerMapping(handlers, -1);
    }

    @Override
    public WebSocketService getWebSocketService() {
        ReactorNettyRequestUpgradeStrategy strategy =
            new ReactorNettyRequestUpgradeStrategy(
                () -> WebsocketServerSpec.builder()
                    .maxFramePayloadLength(128 * 1024)
            );

        HandshakeWebSocketService service =
            new HandshakeWebSocketService(strategy);

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}

final class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    EchoWebSocketHandler() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        config.setAllowedMethods(List.of("GET"));
        this.corsConfiguration = config;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return this.corsConfiguration;
    }

    @Override
    public List<String> getSubProtocols() {
        return List.of("chat.v1");
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()
                ))
        );
    }
}
~~~

Các type phụ được khai báo package-private trong cùng file để giữ ví dụ gọn. Trong dự án thực tế, có thể tách handler, config và DTO thành các file riêng.

### 13.4. WebSocketIntegrationTest.java

~~~java
package demo;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;

import org.springframework.web.reactive.socket.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    private final WebSocketClient client =
        new ReactorNettyWebSocketClient();

    private URI endpoint() {
        return URI.create(
            "ws://localhost:" + port + "/ws/echo"
        );
    }

    @Test
    void handshakeNegotiatesProtocolAndEchoesMessage() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("Origin", "https://app.example.test");
        headers.set("Sec-WebSocket-Protocol", "chat.v1");

        AtomicReference<String> protocol = new AtomicReference<>();
        AtomicReference<String> reply = new AtomicReference<>();

        client.execute(endpoint(), headers, session -> {
            protocol.set(
                session.getHandshakeInfo().getSubProtocol()
            );

            Mono<Void> send = session.send(
                Mono.just(session.textMessage("ping"))
            );

            Mono<Void> receive = session.receive()
                .take(1)
                .doOnNext(message ->
                    reply.set(message.getPayloadAsText())
                )
                .then();

            return Mono.when(send, receive);
        }).block(Duration.ofSeconds(5));

        assertEquals("chat.v1", protocol.get());
        assertEquals("echo: ping", reply.get());
    }

    @Test
    void handshakeRejectsUnlistedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("Origin", "https://evil.example.test");
        headers.set("Sec-WebSocket-Protocol", "chat.v1");

        StepVerifier.create(
            client.execute(endpoint(), headers, session ->
                session.receive().then()
            )
        )
        .expectError()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

Test thứ nhất xác minh handshake thành công, subprotocol được chọn và server echo message. Test thứ hai xác minh origin ngoài allowlist bị từ chối. Nếu transport wrap lỗi handshake trong exception khác nhau, chỉ cần kiểm tra publisher kết thúc bằng error; không phụ thuộc một exception implementation cụ thể.

### 13.5. Chạy test

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Ví dụ dùng server port ngẫu nhiên, không cần chạy server thủ công và không gọi dịch vụ bên ngoài.

## 14. Vận hành WebSocket endpoint

WebSocket là kết nối dài hạn. Sau handshake, connection có thể tồn tại nhiều phút hoặc nhiều giờ. Vì vậy cấu hình route và handshake chỉ là bước đầu.

### 14.1. Reverse proxy và load balancer

Nếu ứng dụng chạy sau Nginx, ingress hoặc load balancer, proxy phải chuyển tiếp WebSocket Upgrade và Connection headers đúng cách. Cần kiểm tra:

- Proxy hỗ trợ HTTP Upgrade tới upstream.
- Idle timeout đủ dài cho workload.
- Load balancer không đóng connection trước heartbeat interval.
- Sticky session chỉ dùng khi kiến trúc thực sự cần session affinity.
- TLS termination và forwarded headers được cấu hình đúng.
- Autoscaling/draining có cách xử lý các WebSocket connection đang mở.

### 14.2. Heartbeat và ping/pong

Ping/pong giúp phát hiện connection không còn phản hồi và giữ đường mạng hoạt động qua một số proxy. Reactor Netty có thể tự trả pong cho ping frame theo cấu hình mặc định; ứng dụng chỉ cần xử lý ping trực tiếp nếu có nhu cầu proxy hoặc protocol riêng.

Heartbeat ở tầng ứng dụng khác với protocol ping/pong. Nếu gửi text heartbeat, hai bên cần thống nhất message format và tần suất.

### 14.3. Giới hạn message và backpressure

Đặt giới hạn frame payload phù hợp để tránh client gửi frame quá lớn. Ngoài frame limit, ứng dụng nên có giới hạn message logic sau khi ghép fragment, số message mỗi giây, số connection theo user/tenant, queue outbound khi client đọc chậm, chính sách đóng session khi vi phạm protocol và giới hạn thời gian xử lý mỗi message.

Không dùng một queue không giới hạn để buffer message cho client chậm. Khi downstream chậm, cần backpressure hoặc chính sách drop/reject rõ ràng.

### 14.4. Đóng session đúng cách

Khi một bên hoàn tất inbound stream, handler nên kết thúc reactive flow và để framework đóng session theo lifecycle. Nếu ứng dụng cần đóng có mã/lý do cụ thể, dùng session.close(CloseStatus) theo API và chính sách protocol.

Đừng giữ WebSocketSession trong static map mà không có cleanup. Nếu cần registry connection, gắn lifecycle add/remove, xử lý disconnect/error/cancel và giới hạn số entry.

### 14.5. Observability

Theo dõi ít nhất:

- Số connection đang mở.
- Số handshake thành công/thất bại theo endpoint và lý do.
- Số message nhận/gửi và kích thước.
- Số session bị đóng bởi client, server hoặc timeout.
- Thời gian sống trung bình và percentile.
- Queue outbound, message processing latency và error rate.
- Số kết nối theo tenant/user nếu không vi phạm privacy.

Không log toàn bộ message có thể chứa token hoặc dữ liệu cá nhân. Dùng correlation ID và log metadata đã lọc.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đăng ký WebSocketHandler bằng @GetMapping | Handler không được map theo cơ chế WebSocket | Dùng SimpleUrlHandlerMapping |
| Quên WebSocketHandlerAdapter khi không dùng WebFlux config | DispatcherHandler không biết gọi WebSocketHandler | Đăng ký adapter thủ công |
| Tạo adapter thứ hai trong Spring Boot | Bean cấu hình trùng hoặc lifecycle khó hiểu | Dùng adapter do WebFlux config cung cấp |
| Đặt mapping order sau annotated controllers | Route có thể bị handler mapping khác chiếm trước | Đặt order phù hợp, thường là -1 |
| Map nhiều handler cùng URL | Kết quả route phụ thuộc thứ tự mapping | Dùng path riêng hoặc quy tắc rõ ràng |
| Trả Mono.empty ngay trong handle | Session kết thúc ngay sau handshake | Ghép receive/send thành publisher sống theo session |
| Tự subscribe vào receive | Mất kiểm soát lifecycle và error propagation | Trả publisher từ handle |
| Không xử lý client disconnect | Task nghiệp vụ tiếp tục chạy không cần thiết | Propagate cancellation và cleanup |
| Không thương lượng subprotocol | Client/server có thể dùng message format khác nhau | Implement getSubProtocols và kiểm tra handshake result |
| Tin Origin là authentication | Client không phải browser có thể giả header | Dùng authentication và authorization thực sự |
| Cho phép mọi origin | Website bất kỳ có thể mở kết nối từ browser | Allowlist origin cụ thể |
| Dùng sessionAttributePredicate như authorization | Attribute được copy nhưng không chứng minh quyền | Xác minh principal và policy trước khi cho phép thao tác |
| Tăng frame limit không giới hạn | Client có thể gửi frame lớn gây áp lực memory | Đặt frame/message quota theo nhu cầu |
| Bật compression không đánh giá | Tăng CPU/memory và rủi ro liên quan dữ liệu nén | Chỉ bật khi cần và đã đánh giá |
| Không cấu hình proxy Upgrade | Handshake thất bại sau reverse proxy | Chuyển tiếp Upgrade/Connection và chỉnh timeout |
| Lưu session trong map nhưng không cleanup | Rò session và memory | Xóa entry khi complete/error/cancel |
| Không test origin và subprotocol | Lỗi handshake chỉ lộ ra khi deploy | Test success, rejected origin và protocol negotiation |
| Dùng REST request/response mindset cho WebSocket | Không quản lý connection dài hạn và backpressure | Thiết kế lifecycle hai stream |

## 16. Checklist triển khai

Trước khi đưa WebSocket endpoint vào production, kiểm tra:

1. **Handler:** WebSocketHandler trả Mono<Void> đại diện cho toàn bộ session chưa?
2. **Inbound/outbound:** receive và send được ghép theo lifecycle đúng chưa?
3. **Route:** SimpleUrlHandlerMapping đăng ký đúng path chưa?
4. **Order:** mapping được xét trước annotated controller khi cần chưa?
5. **Adapter:** WebFlux config đã cung cấp WebSocketHandlerAdapter chưa?
6. **Handshake service:** có cần custom WebSocketService hoặc RequestUpgradeStrategy không?
7. **Server engine:** strategy có khớp Reactor Netty, Tomcat hoặc Jetty đang chạy không?
8. **Subprotocol:** client và server có cùng protocol được thương lượng không?
9. **Origin:** browser origin có được allowlist không?
10. **Authentication:** handshake có được bảo vệ bằng principal hợp lệ không?
11. **Authorization:** user có quyền truy cập room/tenant/resource sau handshake không?
12. **Session attributes:** chỉ copy các attribute cần thiết và đã xác minh chưa?
13. **Frame/message limits:** kích thước và tốc độ message có giới hạn không?
14. **Backpressure:** client chậm có thể làm queue tăng không giới hạn không?
15. **Proxy:** Upgrade headers, TLS và idle timeout có đúng không?
16. **Lifecycle:** disconnect, error, cancellation và server shutdown có cleanup không?
17. **Observability:** metrics connection, handshake, message và close reason có được theo dõi không?
18. **Tests:** có test handshake success, subprotocol, origin rejection và echo message không?

**Ghi nhớ:** WebFlux đăng ký WebSocket endpoint bằng cách map WebSocketHandler vào URL qua SimpleUrlHandlerMapping. WebSocketHandlerAdapter chuyển handler tới WebSocketService; HandshakeWebSocketService kiểm tra handshake và gọi RequestUpgradeStrategy của server engine. Dùng WebFluxConfigurer.getWebSocketService() để tùy biến handshake service, subprotocol qua getSubProtocols(), origin qua CorsConfigurationSource và session attributes qua predicate. Handshake thành công mới chỉ mở kết nối; authentication, authorization, backpressure, giới hạn message và cleanup vẫn phải được thiết kế cho toàn bộ vòng đời session.

## Tài liệu tham khảo

- Spring Framework — WebFlux WebSocket: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework — WebFlux Configuration and WebSocketService: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebSocketHandler API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html
- Spring Framework — HandshakeWebSocketService API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html
- Spring Framework — ReactorNettyRequestUpgradeStrategy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/server/upgrade/ReactorNettyRequestUpgradeStrategy.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Reactor Netty — WebsocketServerSpec API: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/server/WebsocketServerSpec.html
