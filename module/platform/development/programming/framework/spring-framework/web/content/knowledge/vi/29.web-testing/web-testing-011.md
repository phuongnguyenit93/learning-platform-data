# Kiểm thử HTTP Service Client và WebSocket/STOMP theo hợp đồng

## 1. Mục tiêu: kiểm thử hợp đồng thật sự diễn ra trên đường truyền

Một interface Java có `@HttpExchange` có thể biên dịch thành công nhưng proxy vẫn gửi nhầm HTTP method, URL, query, header hoặc JSON. Một `@MessageMapping` của STOMP cũng có thể hoạt động trong unit test gọi method trực tiếp nhưng client thực tế không CONNECT, SUBSCRIBE hoặc nhận được MESSAGE.

**Kiểm thử theo hợp đồng (contract testing)** nghĩa là xác minh những điều hai đầu giao tiếp cùng cam kết: request/destination, dữ liệu, loại thông điệp, status/error và quy tắc tương thích. Hợp đồng cần được xác minh ở tầng mà lỗi có thể phát sinh, thay vì chỉ mock một method Java rồi coi như giao thức hoạt động.

Trong bài này có hai đường giao tiếp:

- **HTTP Service Client:** ứng dụng là consumer của REST API. Interface được Spring tạo proxy qua `HttpServiceProxyFactory` và `RestClientAdapter` hoặc `WebClientAdapter`. Kiểm tra request HTTP thật mà proxy tạo ra cùng phản hồi mà adapter decode.
- **WebSocket/STOMP:** client mở WebSocket handshake rồi dùng STOMP `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ERROR`, `DISCONNECT`. Kiểm tra mapping của Spring `@MessageMapping`, broker và cách dữ liệu đi qua phiên bất đồng bộ.

Bài dùng Java 17+, Spring Framework 6.1 với Spring Boot 3.3.x. Ví dụ runnable tạo một HTTP interface proxy và một STOMP endpoint cục bộ. Không cần API provider bên ngoài hoặc message broker riêng; Spring simple broker dùng trong demo chạy trên một JVM.

Sau bài học, bạn có thể:
1. Chọn unit, mock HTTP, mock socket, integration hoặc consumer-driven contract test phù hợp với rủi ro.
2. Test `@HttpExchange`: method, URI template, path/query encoding, request headers/body, JSON response và error status; kiểm tra cấu hình proxy.
3. Test STOMP từ một client thực: handshake, subscribe, send, nhận payload và timeout; tách kiểm tra destination và transport.
4. Dùng `RECEIPT` khi cần đồng bộ thời điểm subscription được broker xử lý, tránh test race do dùng `Thread.sleep`.
5. Lập ma trận thay đổi phiên bản, lỗi auth/CSRF/Origin, reconnect, fallback SockJS và delivery semantics; nhận biết giới hạn từng loại test.

## 2. “Hợp đồng” khác chữ ký interface Java

Trong HTTP Service Client, chữ ký:

~~~java
@GetExchange("/{id}")
Item findById(@PathVariable("id") long id);
~~~

mô tả **một phần** hợp đồng. Để xác minh trọn vẹn, cần biết base URL, tiền tố endpoint `@HttpExchange`, method GET, mã HTTP thành công/lỗi, `Accept`, JSON shape, field bắt buộc, auth headers và chính sách version. Ví dụ nếu server chỉ nhận `/v2/items/7` nhưng proxy thực tế gọi `/v1/items/7`, Java vẫn biên dịch và unit test mock interface có thể vẫn xanh.

Hợp đồng STOMP cũng có nhiều phần hơn một method:

~~~java
@MessageMapping("/echo")
@SendTo("/topic/echo")
public EchoReply echo(EchoRequest request) { /* ... */ }
~~~

Cần biết endpoint WebSocket HTTP (ví dụ `/events`), application destination prefix (`/app`), client gửi `/app/echo`, server phát đến `/topic/echo`, JSON payload, STOMP headers, điều kiện authentication/authorization và hành vi reconnect. HTTP URL `/events` **khác** STOMP destination `/app/echo`: client gửi `SEND` sau khi đã có kết nối, proxy HTTP không route tới `/app/echo` như một HTTP path.

| Tầng | Điều cần bảo vệ | Kiểm thử nên dùng |
| --- | --- | --- |
| Facade/business | Điều phối, phép tính, lựa chọn fallback | Unit test với fake/mock interface |
| HTTP proxy mapping | URL, method, path/query/header, JSON, status | `MockRestServiceServer` gắn với `RestClient.Builder` |
| HTTP transport | DNS/TLS, redirect, connection timeout, HTTP encoder, proxy | WireMock/MockWebServer qua cổng mạng thật |
| Provider HTTP contract | Server còn chấp nhận request và trả schema/status đã cam kết | Provider verification/consumer-driven contract |
| STOMP handler | `@MessageMapping`, conversion, validation, định tuyến tới broker | Test có Spring messaging infrastructure |
| STOMP end to end | Handshake, `CONNECTED`, `SUBSCRIBE`, `SEND`, `MESSAGE` | `WebSocketStompClient` qua local/random port |
| Deployment | LB, TLS termination, Origin, CSRF, SockJS fallback, broker relay | Integration/E2E qua đường mạng deployment |

**Mỗi cấp chỉ chứng minh phần nó thực sự chạy qua.** Unit test mock CatalogClient không chứng minh HTTP proxy. Test `MockRestServiceServer` không chứng minh TLS thật. Test dùng `WebSocketStompClient` trong một JVM không chứng minh sticky sessions trên cluster hoặc thông điệp được phục hồi sau mất mạng.

## 3. Thiết kế HTTP contract có thể kiểm thử được

Giả sử dịch vụ catalog có:
- `GET /api/items/{id}` trả 200 JSON `{"id":7,"name":"Pen"}`; yêu cầu header `X-Tenant`.
- `POST /api/items` nhận JSON `{"name":"Pen"}` và trả 201 cùng DTO.
- Khi item không có, GET trả 404.
- Phản hồi là JSON; các endpoint còn được version hóa hoặc chuyển host theo cấu hình.

Interface dự kiến:

~~~java
@HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
public interface CatalogClient {
    @GetExchange("/{id}")
    Item findById(@PathVariable("id") long id,
                  @RequestHeader("X-Tenant") String tenant);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Item create(@RequestBody CreateItem body);

    record Item(long id, String name) {}
    record CreateItem(String name) {}
}
~~~

Kiểm thử phải tạo **proxy thật** bằng `HttpServiceProxyFactory` trên một `RestClient` có cấu hình tương đương production. Sau đó test điều mà proxy gửi, không stub `CatalogClient.findById()` bằng Mockito.

### 3.1. MockRestServiceServer

Trong Spring Framework 6.1, có thể bind `MockRestServiceServer` vào `RestClient.Builder`:

~~~java
RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://catalog.example.test");

MockRestServiceServer server =
    MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();
CatalogClient catalog = HttpServiceProxyFactory
    .builderFor(RestClientAdapter.create(restClient))
    .build()
    .createClient(CatalogClient.class);
~~~

**Thứ tự quan trọng:** bind mock server **trước** `builder.build()`, để RestClient sử dụng request factory do Spring Test lắp vào. Mock server kiểm tra method, URI, headers, body; không mở TCP socket và không đi ra `https://catalog.example.test`. Tên miền .test chỉ để xác minh route.

Những assertion cần làm rõ:
- URL đầy đủ khớp base URL + path khai báo; path variable/query param được encode đúng.
- HTTP method GET/POST/PUT/DELETE chính xác, không chỉ kiểm status.
- Request body encode JSON và Content-Type phù hợp. Khi POST có body, kiểm cả field names, type và nội dung.
- Header auth/tenant/correlation ID xuất hiện đúng, không lộ header của dịch vụ khác.
- Response JSON được decode thành kiểu DTO; test nullable/required fields và thêm field khi schema cho phép.
- 404/429/500 và các lỗi theo contract được chuyển thành exception/status đúng.
- Retry chỉ xảy ra khi được cấu hình có chủ đích; số request và idempotency key phải được xác nhận nếu có retry.

### 3.2. WebClient interface cần kiểm thêm reactive semantics

Với WebClientAdapter, interface thường trả `Mono<Item>` hoặc `Flux<Item>`. HTTP request sẽ được thực hiện khi publisher được subscribe; chỉ gọi method rồi không subscribe **không chứng minh request được gửi**. Test nên dùng `StepVerifier` từ reactor-test cùng mock HTTP server.

Snippet minh họa tích hợp:

~~~java
Mono<Item> result = reactiveCatalog.findById(7L);

StepVerifier.create(result)
    .expectNextMatches(item ->
        item.id() == 7L && "Pen".equals(item.name()))
    .verifyComplete();
~~~

Đoạn này **không standalone**: `reactiveCatalog` là proxy WebClientAdapter đã được tạo, `Item` là DTO, test cần `reactor-test`, mock HTTP server và imports tương ứng. Ngoài success, cần test error signal, timeout, cancellation, retry/resubscription và request count. Nếu mock trả `Mono.just(...)` cho một interface thay vì chạy WebClient proxy, những lỗi URI/header/codec và HTTP status sẽ không được phát hiện.

Kiểm tra `Publisher` bằng `StepVerifier` và response ở mock HTTP server là hai lớp evidence bổ sung: StepVerifier xác minh tín hiệu reactive; mock HTTP server xác minh giao thức bên ngoài.

## 4. Hợp đồng WebSocket và STOMP

Spring STOMP over WebSocket thường có luồng:

~~~mermaid
sequenceDiagram
    participant Client as STOMP client
    participant Server as Spring WebSocket endpoint
    participant Handler as @MessageMapping
    participant Broker as STOMP simple broker
    Client->>Server: HTTP GET /events + Upgrade
    Server-->>Client: 101 Switching Protocols
    Client->>Server: STOMP CONNECT
    Server-->>Client: STOMP CONNECTED
    Client->>Server: STOMP SUBSCRIBE /topic/echo
    Client->>Server: STOMP SEND /app/echo + JSON
    Server->>Handler: Resolve @MessageMapping("/echo")
    Handler->>Broker: Publish to /topic/echo
    Broker-->>Client: STOMP MESSAGE + JSON
~~~

Các rủi ro khác nhau:
- **Handshake:** endpoint sai, WebSocket Upgrade không được proxy chuyển tiếp, TLS/WSS, origin policy hoặc authentication khiến kết nối không mở.
- **CONNECT:** WebSocket được mở nhưng STOMP CONNECT thất bại do header, CSRF hoặc auth; `101` không chứng minh STOMP đã `CONNECTED`.
- **SUBSCRIBE:** destination, permission và định tuyến broker sai. Subscriber chưa được broker ghi nhận khi message đến sẽ có thể không nhận gì.
- **SEND:** client gửi sai `/app` prefix, Content-Type không khớp converter, JSON malformed hoặc Bean Validation bị từ chối.
- **MESSAGE:** payload có schema khác, destination sai, không được broadcast đến subscriber dự kiến.
- **ERROR/close/reconnect:** session cũ mất, client phải connect và subscribe lại; message trong khoảng disconnect cần cơ chế replay ở tầng nghiệp vụ khi contract yêu cầu.

**Không lấy việc gọi trực tiếp một method `@MessageMapping` làm kiểm thử STOMP contract hoàn chỉnh.** Gọi trực tiếp chỉ xác minh logic Java; không đi qua STOMP frame decoder, channel dispatch, message conversion hoặc broker subscription.

### 4.1. Tránh race condition trong integration test

Một test thường viết:

~~~java
session.subscribe("/topic/echo", handler);
session.send("/app/echo", new EchoRequest("ping"));
~~~

Hai hành động diễn ra nhanh trên phía client. Tuy khung SUBSCRIBE được gửi trước SEND, xử lý bất đồng bộ ở server hoặc broker có thể khiến message xuất hiện khi subscription chưa được ghi nhận. `Thread.sleep(500)` chỉ là đoán thời gian, dễ flaky trên CI.

STOMP hỗ trợ header `receipt`: client yêu cầu server trả `RECEIPT` sau khi frame được xử lý. Trong Spring `StompSession`, gọi `setAutoReceipt(true)` trước `subscribe`, sau đó dùng `Subscription.addReceiptTask(...)`. Để receipt tracking hoạt động, `WebSocketStompClient` phải có `TaskScheduler`; test nên đặt timeout có giới hạn và xử lý receipt-lost. Tùy broker/server, **RECEIPT cần được hỗ trợ**; nếu môi trường production dùng broker khác, xác minh khả năng này trước khi chọn chiến lược test.

Không nên assert thứ tự delivery toàn cục giữa nhiều connections: STOMP ordering là vấn đề của từng channel, broker và cấu hình Spring. Nếu nghiệp vụ cần thứ tự nghiêm ngặt hoặc at-least-once, đó phải là contract có sequence/ack riêng và test tương ứng.

## 5. Ví dụ độc lập: HTTP Service Client proxy + STOMP qua socket thật

Ví dụ dưới đây dùng **Java 17+**, **Maven** và Spring Boot **3.3.13** (Spring Framework 6.1). Một project chứa:
- Interface `CatalogClient` để test URI, header, JSON và 404 bằng `MockRestServiceServer`.
- WebSocket STOMP endpoint `/events`, destination `/app/echo` và `/topic/echo`.
- Integration test `@SpringBootTest(webEnvironment = RANDOM_PORT)` tạo client STOMP, chờ SUBSCRIBE receipt, gửi JSON và nhận MESSAGE.

Server demo dùng **simple broker**, một JVM; không giả lập cluster hoặc broker relay. URL catalog trong HTTP test là `.test`, không có outbound network. WebSocket test mở socket **localhost** trên cổng Spring Boot chọn ngẫu nhiên.

### 5.1. Cấu trúc

~~~text
contract-testing-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ContractTestingApplication.java
    │   ├── CatalogClient.java
    │   └── SocketConfiguration.java
    └── test/java/demo/
        ├── HttpProxyContractTest.java
        └── StompContractTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>contract-testing-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-websocket` kéo theo Spring MVC, messaging/STOMP và các thành phần Jackson cần cho demo; `spring-boot-starter-test` cung cấp JUnit 5, MockRestServiceServer và AssertJ/JUnit assertions. Khi nâng cấp Boot/Spring, phải xem lại signatures của các API, đặc biệt `HttpServiceProxyFactory.builderFor` và `WebSocketStompClient.connectAsync`.

### 5.3. ContractTestingApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContractTestingApplication.class, args);
    }
}
~~~

### 5.4. CatalogClient.java

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
public interface CatalogClient {

    @GetExchange("/{id}")
    Item findById(@PathVariable("id") long id,
                  @RequestHeader("X-Tenant") String tenant);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    Item create(@RequestBody CreateItem input);

    record Item(long id, String name) {}
    record CreateItem(String name) {}
}
~~~

Đây là interface cho proxy client; demo không triển khai REST server `/api/items` vì MockRestServiceServer đóng vai provider trong HTTP tests.

### 5.5. SocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.stereotype.Controller;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class SocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/events");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }

    public record EchoRequest(String text) {}
    public record EchoReply(String text) {}

    @Controller
    public static class EchoController {
        @MessageMapping("/echo")
        @SendTo("/topic/echo")
        public EchoReply echo(EchoRequest request) {
            return new EchoReply("echo:" + request.text());
        }
    }
}
~~~

WebSocket endpoint `/events` là native WebSocket, không bật SockJS. Cấu hình mẫu cố ý không có authentication để kiểm thử contract cơ bản. Hệ thống thật cần xác thực/authorization STOMP destinations, validate payload và bảo vệ Origin/CSRF theo security policy.

### 5.6. HttpProxyContractTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class HttpProxyContractTest {

    private CatalogClient proxy(RestClient.Builder builder) {
        return HttpServiceProxyFactory
            .builderFor(RestClientAdapter.create(builder.build()))
            .build()
            .createClient(CatalogClient.class);
    }

    @Test
    void getUsesAnnotatedPathMethodHeaderAndJson() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        CatalogClient client = proxy(builder);

        server.expect(requestTo(
                "https://catalog.example.test/api/items/7"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Tenant", "tenant-1"))
            .andRespond(withSuccess(
                "{\"id\":7,\"name\":\"Pen\"}",
                MediaType.APPLICATION_JSON));

        assertEquals(
            new CatalogClient.Item(7L, "Pen"),
            client.findById(7L, "tenant-1"));
        server.verify();
    }

    @Test
    void postSerializesBodyAndUsesExpectedEndpoint() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        CatalogClient client = proxy(builder);

        server.expect(requestTo(
                "https://catalog.example.test/api/items"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(content().json("{\"name\":\"Pen\"}"))
            .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"id\":8,\"name\":\"Pen\"}"));

        assertEquals(
            new CatalogClient.Item(8L, "Pen"),
            client.create(new CatalogClient.CreateItem("Pen")));
        server.verify();
    }

    @Test
    void missingResourceIsReportedAsHttp404() {
        RestClient.Builder builder = RestClient.builder()
            .baseUrl("https://catalog.example.test");
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
        CatalogClient client = proxy(builder);

        server.expect(requestTo(
                "https://catalog.example.test/api/items/999"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThrows(HttpClientErrorException.NotFound.class,
            () -> client.findById(999L, "tenant-1"));
        server.verify();
    }
}
~~~

Giải thích:
- `proxy(builder)` tạo proxy thật trên adapter RestClient. `bindTo(builder)` được gọi trước đó để thay request factory phục vụ test.
- Test GET kiểm URL, method, header và DTO; nếu annotation path thay đổi hoặc header biến mất, mock expectation lỗi.
- Test POST kiểm Content-Type, request JSON và body response, tránh trường hợp interface type-safe nhưng wire format bị sai.
- Test 404 bảo vệ semantics lỗi: mặc định `retrieve` của RestClient báo 4xx qua exception. Nếu ứng dụng có custom status handler, sửa assertion theo **hợp đồng được công bố**, không theo mặc định ngầm.
- `server.verify()` xác minh những request mong đợi đã thực sự xảy ra; test không tạo TCP connection ra ngoài.

### 5.7. StompContractTest.java

~~~java
package demo;

import java.lang.reflect.Type;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StompContractTest {

    @LocalServerPort
    int port;

    private WebSocketStompClient stompClient;
    private ThreadPoolTaskScheduler scheduler;

    @BeforeEach
    void setUp() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.initialize();

        stompClient = new WebSocketStompClient(
            new StandardWebSocketClient());
        stompClient.setTaskScheduler(scheduler);
        stompClient.setMessageConverter(
            new MappingJackson2MessageConverter());
    }

    @AfterEach
    void tearDown() {
        if (stompClient != null) {
            stompClient.stop();
        }
        if (scheduler != null) {
            scheduler.shutdown();
        }
    }

    @Test
    void clientCanConnectSubscribeSendAndReceiveJson() throws Exception {
        CompletableFuture<SocketConfiguration.EchoReply> received =
            new CompletableFuture<>();
        CompletableFuture<Void> subscribed =
            new CompletableFuture<>();

        StompSession session = stompClient.connectAsync(
                "ws://127.0.0.1:" + port + "/events",
                new StompSessionHandlerAdapter() {})
            .get(10, TimeUnit.SECONDS);

        try {
            // Yêu cầu broker ACK việc xử lý SUBSCRIBE bằng RECEIPT.
            session.setAutoReceipt(true);
            StompSession.Subscription subscription =
                session.subscribe("/topic/echo", new StompFrameHandler() {
                    @Override
                    public Type getPayloadType(StompHeaders headers) {
                        return SocketConfiguration.EchoReply.class;
                    }

                    @Override
                    public void handleFrame(
                            StompHeaders headers, Object payload) {
                        received.complete(
                            (SocketConfiguration.EchoReply) payload);
                    }
                });

            subscription.addReceiptTask(() ->
                subscribed.complete(null));
            subscription.addReceiptLostTask(() ->
                subscribed.completeExceptionally(
                    new IllegalStateException("SUBSCRIBE receipt timeout")));

            subscribed.get(10, TimeUnit.SECONDS);
            session.send("/app/echo",
                new SocketConfiguration.EchoRequest("ping"));

            SocketConfiguration.EchoReply reply =
                received.get(10, TimeUnit.SECONDS);
            assertEquals(
                new SocketConfiguration.EchoReply("echo:ping"), reply);
        } finally {
            session.disconnect();
        }
    }
}
~~~

Test sử dụng `connectAsync` (trả CompletableFuture, API thích hợp của Spring 6.1), thay cho các overload `connect(...)` cũ đã bị deprecated. `@LocalServerPort` lấy cổng thật do Boot cấp. Client `StandardWebSocketClient` mở WebSocket TCP trên localhost, STOMP handshake đi qua Spring server, SUBSCRIBE vào simple broker, SEND tới controller và chờ MESSAGE JSON.

**Tại sao chờ RECEIPT?** Nếu test gửi message quá sớm sau SUBSCRIBE, broker có thể chưa thêm subscription. Chờ callback receipt cung cấp điểm đồng bộ dựa trên giao thức. `ThreadPoolTaskScheduler` cho phép theo dõi receipt và timeout; `CompletableFuture.get(10, TimeUnit.SECONDS)` giúp test thất bại rõ ràng nếu không CONNECT, không nhận RECEIPT hoặc không nhận MESSAGE. Không dùng `Thread.sleep` đoán thời điểm sẵn sàng.

**Giới hạn:** việc nhận một MESSAGE chứng minh luồng cơ bản hoạt động qua localhost, chưa chứng minh auth/Origin/CORS, loss/replay, network proxy hay scale-out. Server/broker thật phải hỗ trợ STOMP receipts; nếu chính sách của broker không cung cấp receipt, dùng cơ chế synchronization đã kiểm chứng riêng thay cho sleep.

### 5.8. Cách chạy và kỳ vọng

Đặt đúng các file như cấu trúc trên, cài JDK 17+ và Maven, trong thư mục project chạy:

~~~bash
mvn -q test
~~~

Có **4 phương thức `@Test`** trong hai class: 3 HTTP proxy tests và 1 STOMP integration test. Trạng thái mong đợi nếu môi trường và code phù hợp là Maven exit code **0**. Báo cáo chi tiết được sinh tại `target/surefire-reports/`; `-q` có thể không in tổng số test ra stdout. Bài này trình bày code để người đọc thực thi, **không khẳng định các test đã được chạy thành công trong môi trường biên soạn**.

Nếu test STOMP timeout, lần lượt kiểm:
1. Server đã bind port chưa; endpoint đúng `/events` và URL dùng `ws://` chưa?
2. Đã có frame `CONNECTED` chưa?
3. `SUBSCRIBE` destination có đúng prefix `/topic`? Broker có gửi `RECEIPT`?
4. `SEND` tới `/app/echo` có được map vào `@MessageMapping("/echo")`?
5. Converter có tạo/đọc JSON đúng record? Có STOMP ERROR, conversion exception hoặc close bất thường không?
6. Test có dùng timeout hữu hạn và đóng session/client/scheduler để tránh leak tài nguyên không?

Đối với HTTP proxy test fail, bật log request status/URL ở môi trường test, đọc mismatch từ MockRestServiceServer; xác định lỗi là URI/template, method, headers, body converter hay status mapping. Không sửa expected URL chỉ để xanh nếu hợp đồng provider yêu cầu URL cũ.

## 6. Làm rõ HTTP contract với nhiều dịch vụ và nhiều phiên bản

Nếu ứng dụng gọi Inventory Service v1 và Pricing Service v2, mỗi proxy cần baseUrl, credentials, timeout và error policy phù hợp. Kiểm thử không chỉ tạo các interface riêng mà nên lấy **bean cấu hình production** trong Spring context rồi kiểm tra chúng route đúng.

Ma trận ví dụ:

| Kiểm tra | Inventory Client | Pricing Client |
| --- | --- | --- |
| Base URL | inventory.example.test | pricing.example.test |
| HTTP path | /v1/stock/A-1 | /v2/prices/A-1 |
| Authentication | Audience inventory | Audience pricing |
| Response | Stock DTO | Price DTO |
| Error | OUT_OF_STOCK/404 theo contract | PRICE_UNAVAILABLE/503 theo contract |
| Schema evolution | Field available hoặc quantity | amountMinorUnits + currency |
| Negative security test | Không có token pricing | Không có token inventory |

Đừng gộp cả hai vào cùng một mock server nếu mục tiêu là xác minh **cách ly host và token**: dùng hai mock servers riêng hoặc hai cổng HTTP mock network thực. Đảm bảo factory tạo từ chính `RestClient.Builder` production hoặc cấu hình tương đương; test interface trên builder khác với production có thể bỏ sót sai cấu hình baseUrl.

### 6.1. Contract của provider, không chỉ stub theo kỳ vọng consumer

Mock HTTP test xác nhận “client gửi như consumer nghĩ API hoạt động”. Nó không đảm bảo service thật trả đúng JSON đó. Hợp đồng cần được thống nhất, version hóa và xác minh ở provider bằng:
- OpenAPI/schema + provider contract tests, hoặc consumer-driven contracts (Pact, Spring Cloud Contract nếu phù hợp stack).
- Tập JSON fixtures: field bắt buộc, field mới, missing/null, numeric boundaries, timezone/currency, status codes và error body.
- Provider verification trong CI đối với các consumer versions vẫn đang hoạt động.
- Compatibility check trước deployment: provider mới phải đáp ứng các hợp đồng đã xuất bản hoặc cung cấp API version mới.
- Integration tests với provider sandbox/staging để bắt những rủi ro ngoài contract đã mô tả như auth, redirects, certificates, rate limits.

Một thay đổi thêm field response thường tương thích khi consumer bỏ qua unknown fields; **đổi tên/xóa field bắt buộc hoặc đổi đơn vị tiền** có thể là breaking change dù JSON vẫn parse được. Client có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)` có chọn lọc, nhưng phải validation required semantics.

### 6.2. Retry và tác dụng phụ

Test HTTP proxy có retry cần kiểm **số request thực tế** và chính sách `maxRetries`. Tăng retry nhưng không dùng idempotency trên POST tạo đơn/thanh toán có thể nhân đôi side effects. Test theo kịch bản:
- GET 503 → 200, đúng tối đa số lượt; lỗi 400 không retry.
- POST response mất sau khi server đã commit: chỉ retry khi server hỗ trợ cùng Idempotency-Key với deduplication.
- Không sinh key mới trong từng lần resubscribe.
- Khi hết retry, trả lỗi cuối hoặc lỗi domain đúng contract, không biến thành thành công giả.
- Timeout toàn chuỗi phù hợp SLA của caller, không để CI chờ vô hạn.

Với MockRestServiceServer có thể khai báo các expected requests theo thứ tự, nhưng muốn kiểm kết nối ngắt, read timeout/TLS và retry ở transport thật thì dùng mock web server chạy socket thay cho request factory giả.

## 7. Thiết kế hợp đồng STOMP tương thích qua các phiên bản

STOMP contract có cả:
- **Endpoint URL:** ví dụ `/events` để mở transport; đổi path gây lỗi handshake.
- **Application destinations:** `SEND /app/echo`; đổi prefix hoặc method mapping gây lỗi route.
- **Subscribe destinations:** `SUBSCRIBE /topic/echo`; đổi topic khiến subscriber không nhận MESSAGE.
- **Payload schema:** trường tên, kiểu, nullable, default, enum và ý nghĩa thời gian/số tiền.
- **Error semantics:** STOMP ERROR frame, application-level error message, hoặc close code theo giao thức được thống nhất.
- **Security:** websocket origin, STOMP CONNECT token/CSRF, quyền SEND/SUBSCRIBE từng destination; không chỉ auth HTTP handshake.
- **Delivery:** client nhận được bao nhiêu lần? Broker giữ message khi client offline không? Có ACK/redelivery hoặc replay theo sequence ID không?
- **Reconnect/resubscribe:** người dùng/máy khách có thể ngắt mạng; session ID và subscriptions mới cần khôi phục.

Các thay đổi như `/topic/echo` thành `/topic/messages` là breaking cho client đang SUBSCRIBE topic cũ. Thêm field tùy chọn JSON có thể tương thích khi client decoder chấp nhận. Đổi String `text` thành object phức tạp là thay đổi contract đáng test ở cả producer và consumer.

**Simple broker của Spring** phù hợp demo/test một JVM; subscription nằm trong bộ nhớ của node. Chạy nhiều instance có thể cần broker relay/external STOMP broker và session affinity SockJS, nhưng việc test một node thành công không chứng minh cluster hoạt động. Không khẳng định STOMP mang lại exactly-once delivery; phần đó cần protocol/logic application riêng.

## 8. Socket tests nên bao phủ gì ngoài đường thành công?

| Kịch bản | Cách test phù hợp | Điều xác minh |
| --- | --- | --- |
| Sai endpoint WebSocket | WebSocketStompClient đến URI không tồn tại | Handshake fail có giới hạn thời gian |
| Origin không được phép | Test handshake với Origin header thực | Request không vượt qua allowed-origin policy |
| CONNECT không có auth/CSRF khi bật Security | Kết nối với STOMP headers thiếu/thừa | Từ chối đúng lúc, không để subscribe trái phép |
| SUBSCRIBE destination sai | Subscribe topic không tồn tại/không có quyền | Không nhận thông điệp hoặc bị từ chối theo contract |
| SEND JSON malformed | Client gửi payload raw sai hoặc content-type không đúng | Error behavior/conversion được quan sát |
| SEND hợp lệ | Subscription rồi SEND, chờ MESSAGE | Mapping/JSON/broker end-to-end |
| Đa subscriber | Hai sessions SUBSCRIBE topic | Broadcast đúng các subscriber có quyền |
| Unsubscribe | UNSUBSCRIBE, sau đó SEND | Session đã bỏ đăng ký không nhận thêm |
| Heartbeat/idle timeout | Test với scheduler/timeouts rút ngắn | Disconnect/reconnect phù hợp policy |
| Reconnect | Đóng socket rồi tạo session mới | CONNECT lại, SUBSCRIBE lại, missing message policy rõ |
| SockJS HTTP fallback | SockJsClient/Browser ép xhr-polling | HTTP transports hoạt động, không chỉ 101 Upgrade |
| LB + hai node | Integration qua load balancer thật | Sticky session/broker relay/routing |
| Broker unavailable | Tắt broker relay trong staging test | App/client báo lỗi và phục hồi đúng |

**Tách lớp test:** server-side test có thể dùng `ChannelInterceptor` hoặc `TestChannelInterceptor` để quan sát messages gửi/nhận trên Spring channels mà không mở WebSocket. Cách này nhanh để kiểm `@MessageMapping` và conversion, nhưng phải gắn đúng `clientInboundChannel`/`clientOutboundChannel` và xử lý executor bất đồng bộ; nó không thay thế bài test handshake. Khi sử dụng `@SendToUser`, test phải có session/principal và định tuyến user destination, không chỉ so nội dung message.

### SockJS khi có proxy

Một STOMP native WebSocket test **không** kiểm SockJS fallback. Nếu endpoint dùng `registry.addEndpoint("/events").withSockJS()`, một SockJS client thường truy cập HTTP base URL `http://host/events`, gọi `/events/info` rồi chọn WebSocket hoặc XHR transport. Proxy phải cho GET/POST/OPTIONS phù hợp và chuyển tiếp session paths, xử lý buffering/timeout và CORS/CSRF.

Trong production, có thể thêm test qua browser hoặc SockJsClient giới hạn transport:
- WebSocket transport: thấy handshake 101, CONNECT/SUBSCRIBE/SEND/MESSAGE.
- XHR polling: không cần 101; có `/info`, `/xhr`, `/xhr_send`; vẫn nhận MESSAGE.
- XHR streaming: kiểm data tới client trước khi proxy giữ buffer.
- Với nhiều backend: cùng SockJS session phải được định tuyến nhất quán, sau reconnect vẫn subscribe lại.

Không áp chính sách `"Access-Control-Allow-Origin: *"` với credentialed requests hoặc tắt toàn bộ CSRF chỉ để test xanh. Khi có Spring Security, kiểm tra STOMP CONNECT CSRF, Origin, session cookie và quyền destination trong môi trường gần production.

## 9. Giảm flaky tests và chứng minh negative paths

Kiểm thử mạng và messaging thường bất đồng bộ; **không dùng sleep làm cơ chế đồng bộ chính**. Dùng `CompletableFuture`, `BlockingQueue.poll(timeout)`, `CountDownLatch.await(timeout)`, hoặc STOMP RECEIPT và instrumentation hợp lệ. Mỗi wait phải có timeout hữu hạn; đảm bảo test đóng session, scheduler và socket.

Khi kiểm “không nhận MESSAGE” hoặc “người dùng chưa được phép SUBSCRIBE”, việc chờ ngắn rồi không thấy message **không phải bằng chứng mạnh** rằng server đã chặn. Cần quan sát dấu hiệu từ chối rõ ràng, STOMP ERROR, frame close/authorization exception, broker receipt hoặc server logs/metrics trong test. Với notification stream, so sánh số lượng và định danh messages; tránh nhận nhầm message cũ từ test trước.

Một số kỹ thuật nâng chất lượng:
1. Dùng test isolation: session/destination hoặc correlation ID riêng cho mỗi test; tránh shared broker state từ context cache.
2. Mock provider HTTP tại biên giao thức, không mock interface khi mục tiêu là proxy mapping.
3. Khi test STOMP, subscribe sau CONNECTED và chờ broker acknowledgement nếu broker hỗ trợ; gửi sau mốc synchronization thật.
4. Assert cả dữ liệu **và** status/headers/destination; test chỉ `notNull` có thể bỏ sót contract break.
5. Kiểm đúng số HTTP attempts và số STOMP messages khi retry/reconnect.
6. Giữ `maxWait` hợp lý theo CI; chẩn đoán transport/broker/serializer khi timeout, không tăng timeout vô hạn.
7. Dùng port động (`RANDOM_PORT`) và đóng clients; tránh cổng hardcode hoặc leak thread giữa các suite.
8. Chỉ test dữ liệu nhạy cảm bằng sample vô hại; không ghi token thật hoặc nội dung nghiệp vụ nhạy cảm vào log/assertion.
9. Khi test proxy HTTPS/WSS qua edge, kiểm certificate, forwarded headers, Origin, query/path rewriting và no mixed-content.
10. Đảm bảo tests chỉ gọi server giả/trong local hoặc sandbox được phép, không vô tình chạy write command vào production.

## 10. Ma trận kiểm thử kết hợp HTTP + STOMP

Một tính năng như “đặt hàng rồi nhận thông báo trạng thái” kết hợp HTTP POST để tạo đơn và STOMP topic để phát cập nhật. Cần tách hợp đồng:

| Trường hợp | HTTP Service Client | STOMP |
| --- | --- | --- |
| Happy path | POST đúng body/status/ID | Sau subscribe, nhận event theo order ID |
| Input lỗi | 400/422 ProblemDetail theo contract | Payload bất hợp lệ từ SEND bị xử lý theo policy |
| Resource không có | 404 JSON/ProblemDetail đúng | Topic/destination hoặc event “not found” theo contract |
| Sai quyền | HTTP 401/403, không tạo đơn | CONNECT/SUBSCRIBE/SEND unauthorized không được thực hiện |
| Retry | Có giới hạn; POST dùng key idempotent nếu server hỗ trợ | Reconnect không được tự tạo đơn lần nữa |
| Schema mới | Fields optional mới không phá DTO cũ | Event versioning, unknown fields, enum values |
| Gián đoạn mạng | Timeout rồi truy vấn trạng thái operation | Reconnect + resubscribe + reconcile missing events |
| Trùng dữ liệu | Server dedup key operation | Consumer event dedup theo eventId nếu contract cần |
| Scale out | Cấu hình host/auth/timeout chính xác | Broker relay/affinity/session và broadcast nhiều node |

Một “unit test chạy xanh” cho facade không đủ chứng minh hệ thống này. Ngoài hai bộ contract tests tách biệt, cần một vài **end-to-end business scenarios**: cùng order ID được trả bởi HTTP và xuất hiện trong event, status update không đến trước điều kiện mong muốn, duplicate/replay được xử lý theo idempotency contract.

## 11. Sai lầm phổ biến

- **Mock interface @HttpExchange rồi kết luận URL đúng:** không chạy proxy; thêm MockRestServiceServer hoặc mock HTTP socket server.
- **Bind MockRestServiceServer sau khi đã build RestClient:** RestClient dùng request factory cũ và mock không chặn request; bind trước build.
- **Chỉ assert HTTP status:** request có thể sai path/header/body nhưng stub vẫn trả dữ liệu; kiểm request đúng contract.
- **Dùng WebClient nhưng quên subscribe:** publisher chưa chạy, không có HTTP call; dùng StepVerifier và mock server.
- **Không test custom status handler:** 404/409/429 bị chuyển sai thành fallback hoặc exception không mong muốn.
- **Chỉ test @MessageMapping bằng gọi method Java:** không kiểm STOMP frame, converter, broker/destination.
- **Coi WebSocket 101 là STOMP CONNECTED:** handshake thành công vẫn có thể bị từ chối ở STOMP CONNECT.
- **Gửi ngay sau SUBSCRIBE rồi sleep nếu flaky:** race chưa được xử lý; dùng RECEIPT/điểm đồng bộ thật.
- **Quên task scheduler cho STOMP receipt:** callback và timeout tracking không hoạt động như mong muốn.
- **Đổi WebSocket native thành SockJS mà giữ URL ws://:** SockJS thường nhận HTTP base URL; cần test client đúng protocol.
- **Bỏ qua Origin/CSRF/auth:** localhost test không có security không đại diện production.
- **Tin vào simple broker khi scale cluster:** một node test không chứng minh cross-node fan-out.
- **Giả định reconnect sẽ replay message:** STOMP session mới không tự chứa history; thiết kế replay riêng.
- **Bắt timeout mà không đóng session:** leak socket/thread và khiến CI test sau thất bại ngẫu nhiên.
- **Đổi code để test xanh khi provider thật đã breaking:** version contract, cảnh báo và phối hợp rollout/rollback.

## 12. Checklist khi bổ sung một endpoint mới

**HTTP Service Client**
- Interface và proxy có method, base URL, URI template, query/header/body, Accept/Content-Type đúng.
- Có contract status 2xx, lỗi 4xx/5xx, media type và DTO nullable/required rõ.
- Mock HTTP test bảo vệ request và JSON; integration/contract verification kết nối provider thật hoặc sandbox khi cần.
- Có negative auth/rate limit/timeout và retry/idempotency tests tương ứng.
- Nếu thêm API version, test song song consumer cũ/mới và rollback.

**WebSocket/STOMP**
- Handshake URL, CONNECT headers, destination SEND/SUBSCRIBE và payload version được mô tả rõ.
- Có test qua STOMP client thật xác minh `MESSAGE` sau subscription, không chỉ mở socket.
- Có test ERROR/authorization, reconnect/subscribe lại và duplicate/delivery policy khi áp dụng.
- SockJS fallback, CORS/CSRF/cookies và proxy/LB được test riêng trong môi trường có chúng.
- Timeout/receipt/lifecycle được kiểm soát; resources được giải phóng sau test.

## 13. Kết luận

HTTP Service Client và WebSocket/STOMP đều có những **hợp đồng ẩn phía sau interface và annotation**: HTTP cần đúng request và response; STOMP cần đúng kết nối, destination, frames và delivery. Bảo vệ hợp đồng cần đặt assertions ở biên giao thức và thêm provider verification; một mock method Java không thay thế được điều đó.

Với HTTP, hãy dùng `MockRestServiceServer` cho `RestClient` proxy tests nhanh, mock HTTP server chạy socket cho transport và provider contracts cho khả năng tương thích. Với WebSocket/STOMP, hãy dùng test messaging có Spring infrastructure và một số integration tests với `WebSocketStompClient` kiểm CONNECT → SUBSCRIBE → SEND → MESSAGE. Khi hệ thống thực có authentication, SockJS, reverse proxy, broker relay hoặc nhiều nodes, các lớp đó cần test riêng theo đúng topology production.

## Tài liệu tham khảo

- Spring Framework Reference — HTTP Interface Client và RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework 6.1 Javadoc — HttpServiceProxyFactory: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
- Spring Framework 6.1 Javadoc — MockRestServiceServer: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html
- Spring Framework Reference — Testing Client Applications: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- Spring Framework Reference — STOMP over WebSocket testing: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/testing.html
- Spring Framework 6.1 Javadoc — WebSocketStompClient: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html
- Spring Framework Reference — STOMP Client, RECEIPT: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html
- Spring Framework Reference — SockJS fallback: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html
- Spring Security Reference — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
