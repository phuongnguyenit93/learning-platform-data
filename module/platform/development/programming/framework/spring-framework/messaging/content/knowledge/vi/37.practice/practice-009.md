# Xây dựng RSocket Request-Response và Request-Stream với Spring

RSocket cung cấp nhiều kiểu tương tác trên một kết nối hai chiều. Trong bài thực hành này, ta xây dựng một responder Spring có hai route: `quotes.latest` nhận một yêu cầu và trả đúng một `Quote` bằng **Request-Response**; `quotes.stream` nhận một yêu cầu và trả nhiều `Quote` bằng **Request-Stream**.

Điểm phân biệt nằm ở số lượng phần tử của request và response:

| Interaction | Dữ liệu gửi đi | Dữ liệu trả về | Kiểu Spring thường dùng |
| --- | --- | --- | --- |
| Request-Response | Một payload (hoặc không có payload) | Một response | `Mono<T>` |
| Request-Stream | Một payload (hoặc không có payload) | Nhiều response theo stream | `Flux<T>` |
| Request-Channel | Một stream payload | Một hoặc nhiều response | `Flux<T>` đầu vào và `Flux<T>` đầu ra |
| Fire-and-Forget | Một payload | Không có response nghiệp vụ | `Mono<Void>` ở phía xử lý; `send()` ở requester |

Với Request-Response, requester gửi một request và chờ một response. Với Request-Stream, requester gửi một request ban đầu rồi nhận một chuỗi response; requester có thể điều khiển tốc độ phát bằng backpressure. Spring ánh xạ hai kiểu này từ cardinality của tham số và giá trị trả về trong `@MessageMapping`.

## 1. Chuẩn bị project Spring Boot

Ví dụ dùng Java 17+ và Spring Boot 4.1.0. `spring-boot-starter-rsocket` cung cấp hạ tầng RSocket server/client, Spring Messaging và codec JSON/CBOR được Boot tự cấu hình. `reactor-test` dùng để kiểm thử publisher với `StepVerifier`.

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>rsocket-practice</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

Chạy server TCP độc lập bằng cấu hình:

**src/main/resources/application.properties**

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Spring Boot tự tạo `RSocketMessageHandler` để tìm các `@Controller` có `@MessageMapping`. Không cần tự khởi tạo `RSocketServer` hoặc đăng ký handler thủ công trong cấu hình Boot thông thường.

Class khởi động:

```java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteRSocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteRSocketApplication.class, args);
    }
}
```

## 2. Khai báo payload gửi và nhận

Request-Response nhận một `QuoteRequest`; Request-Stream nhận một `QuoteStreamRequest` có số lượng phần tử muốn lấy. Cả hai đều trả `Quote`.

**QuoteRequest.java**

```java
package example.rsocket;

public record QuoteRequest(String symbol) { }
```

**QuoteStreamRequest.java**

```java
package example.rsocket;

public record QuoteStreamRequest(String symbol, int count) { }
```

**Quote.java**

```java
package example.rsocket;

import java.math.BigDecimal;

public record Quote(String symbol, BigDecimal price, int sequence) { }
```

Record phù hợp cho DTO bất biến. Trong hệ thống thực tế, request có thể chứa filter, khoảng thời gian, cursor hoặc giới hạn dữ liệu; response nên có schema được version hóa nếu nhiều service/client triển khai độc lập.

## 3. Viết service trả Mono và Flux

`Mono<T>` biểu diễn tối đa một giá trị bất đồng bộ; `Flux<T>` biểu diễn từ 0 đến nhiều giá trị. Service trả publisher để controller có thể chuyển tiếp việc xử lý mà không block thread.

**QuoteService.java**

```java
package example.rsocket;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class QuoteService {

    public Mono<Quote> latest(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            return Mono.error(new IllegalArgumentException("symbol is required"));
        }
        return Mono.just(new Quote(symbol, new BigDecimal("101.25"), 1));
    }

    public Flux<Quote> stream(String symbol, int count) {
        if (symbol == null || symbol.isBlank()) {
            return Flux.error(new IllegalArgumentException("symbol is required"));
        }
        if (count < 1 || count > 100) {
            return Flux.error(new IllegalArgumentException("count must be between 1 and 100"));
        }
        return Flux.range(1, count)
                .map(sequence -> new Quote(symbol,
                        BigDecimal.valueOf(10_000L + sequence * 25L, 2), sequence));
    }
}
```

`Flux.range` là nguồn hữu hạn và hỗ trợ backpressure: nó chỉ phát thêm phần tử khi downstream yêu cầu. Giới hạn `count` là kiểm soát tài nguyên; API streaming production cũng nên giới hạn kích thước, thời gian và số request đồng thời.

## 4. Xây dựng RSocket responder

Spring dùng `@MessageMapping` để ánh xạ route RSocket tới method. Route không cần dấu `/` ở đầu. Kiểu tham số và kiểu trả về quyết định interaction:

- Một payload đầu vào + `Mono<Quote>` đầu ra → Request-Response.
- Một payload đầu vào + `Flux<Quote>` đầu ra → Request-Stream.

**QuoteRSocketController.java**

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class QuoteRSocketController {
    private final QuoteService quoteService;

    public QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.latest")
    public Mono<Quote> latest(@Payload QuoteRequest request) {
        return quoteService.latest(request.symbol());
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(@Payload QuoteStreamRequest request) {
        return quoteService.stream(request.symbol(), request.count());
    }
}
```

Không gọi `.subscribe()` bên trong handler. Hãy trả `Mono` hoặc `Flux` cho framework để nó quản lý subscription, lỗi, cancellation và demand từ requester. Tự subscribe trong controller có thể làm mất liên hệ giữa vòng đời request với công việc nền và khiến client không nhận được response đúng cách.

## 5. Gửi Request-Response từ requester

Requester tạo request bằng `RSocketRequester`. `route(...)` đặt tên route vào metadata; `data(...)` đặt object nghiệp vụ vào vùng data; `retrieveMono(...)` khai báo kiểu response mong đợi.

```java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("localhost", 7000);

Mono<Quote> latest = requester.route("quotes.latest")
        .data(new QuoteRequest("VN30"))
        .retrieveMono(Quote.class);
```

Kết quả là một `Mono<Quote>`. Khi subscribe, Spring serialize `QuoteRequest`, gửi request tới route `quotes.latest`, chờ response và decode thành `Quote`.

Request-Response phù hợp khi caller cần một kết quả duy nhất: lấy thông tin hiện tại, tính toán một kết quả, kiểm tra trạng thái hoặc yêu cầu một command trả về xác nhận. Nếu server không trả payload theo hợp đồng, hãy thiết kế interaction phù hợp; đừng chọn `retrieveMono` chỉ vì muốn chờ một thao tác mà không có response.

## 6. Gửi Request-Stream từ requester

Request-Stream vẫn chỉ gửi một payload ban đầu, nhưng responder có thể phát nhiều response. Dùng `retrieveFlux(...)` để nhận luồng:

```java
Flux<Quote> quotes = requester.route("quotes.stream")
        .data(new QuoteStreamRequest("VN30", 5))
        .retrieveFlux(Quote.class);
```

Client có thể xử lý từng phần tử ngay khi nó tới:

```java
quotes
        .doOnNext(quote -> log.info("Received {}", quote))
        .doOnError(error -> log.error("Quote stream failed", error))
        .doOnComplete(() -> log.info("Quote stream completed"))
        .subscribe();
```

Đoạn code trên minh họa subscriber ở tầng ứng dụng. Trong WebFlux/controller hoặc service reactive, thường nên trả `Flux<Quote>` cho caller thay vì tự subscribe. Nếu cần side effect trong stream, dùng các operator có chủ đích và bảo đảm lỗi được xử lý.

## 7. Kiểm thử end-to-end bằng StepVerifier

Unit test cho `QuoteService` chưa kiểm tra transport, route, codec và RSocket interaction type. Integration test dưới đây khởi động server thật trên port ngẫu nhiên, tạo requester TCP, rồi kiểm tra cả hai interaction.

**QuoteRSocketIntegrationTest.java**

```java
package example.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class QuoteRSocketIntegrationTest {
    @Value("${local.rsocket.server.port}")
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = requesterBuilder.tcp("localhost", port);
    }

    @AfterEach
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsOneQuote() {
        Mono<Quote> response = requester.route("quotes.latest")
                .data(new QuoteRequest("VN30"))
                .retrieveMono(Quote.class);

        StepVerifier.create(response)
                .assertNext(quote -> {
                    assertEquals("VN30", quote.symbol());
                    assertEquals(0, new java.math.BigDecimal("101.25").compareTo(quote.price()));
                    assertEquals(1, quote.sequence());
                })
                .verifyComplete();
    }

    @Test
    void requestStreamHonorsDemandAndCompletes() {
        Flux<Quote> response = requester.route("quotes.stream")
                .data(new QuoteStreamRequest("VN30", 5))
                .retrieveFlux(Quote.class);

        StepVerifier.create(response, 0)
                .thenRequest(1)
                .assertNext(quote -> assertEquals(1, quote.sequence()))
                .thenRequest(4)
                .expectNextCount(4)
                .verifyComplete();
    }
}
```

`@SpringBootTest` khởi động RSocket server của ứng dụng. Giá trị `spring.rsocket.server.port=0` yêu cầu hệ điều hành cấp port trống; Spring Boot công bố port thực tế qua `local.rsocket.server.port`. Test tạo requester tới port đó và gọi route như một client độc lập.

`StepVerifier.create(response, 0)` bắt đầu với demand bằng 0. Test yêu cầu một phần tử, xác nhận sequence 1, sau đó yêu cầu thêm bốn phần tử. Đây là cách kiểm tra luồng có thể được tiêu thụ theo demand và kết thúc đúng cách, không cần `Thread.sleep`.

Chạy kiểm thử:

```bash
mvn test
```

Kết quả kiểm thử mẫu đã chạy với Maven và Spring Boot 4.1.0:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Project thử nghiệm đặt `java.version=17`; mã nguồn dùng record và API tương thích Java 17+. Integration test đã chạy thành công trên JDK 24 với target Java 17.

## 8. Hiểu backpressure trong Request-Stream

Backpressure là một phần của RSocket protocol. Requester gửi số lượng phần tử muốn nhận ban đầu và có thể gửi thêm demand trong quá trình stream. RSocket truyền demand qua ranh giới mạng để responder không cần đẩy vô hạn vào một buffer ở phía client.

Trong Spring, `Flux` là kiểu trả về tự nhiên cho Request-Stream. Hãy ưu tiên nguồn dữ liệu có khả năng phát theo demand như `Flux.fromIterable`, `Flux.range`, `Flux.generate` hoặc publisher reactive từ database/client.

Các nguyên tắc thực hành:

- Không gọi `.collectList()` nếu caller cần stream từng phần tử; thao tác này gom toàn bộ dữ liệu thành một collection và làm mất lợi ích streaming.
- Tránh nạp toàn bộ dữ liệu từ database vào `List` rồi mới tạo `Flux`. Dùng cursor, paging hoặc reactive repository phù hợp.
- Không dùng `subscribe()` bên trong responder để chạy một stream độc lập với request.
- Nếu cần giới hạn tốc độ, dùng `limitRate`, `delayElements` hoặc policy ở nguồn dữ liệu theo yêu cầu nghiệp vụ; không mặc định thêm buffer lớn.
- Khi client hủy subscription, cancellation được truyền tới responder. Dùng `doFinally` hoặc resource management của Reactor để giải phóng cursor, subscription và tài nguyên đang mở.
- Nếu dùng `flatMap` để gọi nhiều dependency song song, đặt giới hạn concurrency và kiểm tra thứ tự kết quả. Dùng `concatMap` khi cần xử lý tuần tự.

Ví dụ client chỉ lấy tối đa 10 phần tử:

```java
Flux<Quote> firstTen = requester.route("quotes.stream")
        .data(new QuoteStreamRequest("VN30", 100))
        .retrieveFlux(Quote.class)
        .take(10);
```

`take(10)` hủy subscription sau phần tử thứ mười; responder có thể nhận cancellation và dừng công việc còn lại. Đây là một khác biệt quan trọng so với tải toàn bộ 100 phần tử rồi bỏ 90 phần tử ở phía client.

## 9. Codec, data, metadata và route

`RSocketRequester` nhận và trả object, còn framework chuyển đổi object thành byte thông qua `RSocketStrategies` và encoder/decoder.

- Spring Boot tự cấu hình `RSocketStrategies`; Boot 4.1 thử codec CBOR với Jackson trước, sau đó JSON với Jackson. `spring-boot-starter-rsocket` cung cấp dependency cần thiết.
- Nếu dùng Spring Framework trực tiếp không qua Boot, codec cơ bản mặc định hỗ trợ `String`, `byte[]` và `ByteBuffer`. Muốn serialize DTO JSON/CBOR cần đăng ký encoder/decoder phù hợp.
- `route("quotes.latest")` được gửi trong metadata routing. `data(new QuoteRequest(...))` là payload nghiệp vụ.
- MIME type của data và metadata được khai báo trong RSocket `SETUP` và áp dụng cho connection. Hai đầu phải tương thích về MIME type và codec.
- Metadata composite cho phép gửi nhiều entry độc lập như route, authentication hoặc tracing; mỗi entry cần encoder/decoder hoặc extractor phù hợp.

Nếu kết nối với client viết bằng ngôn ngữ khác, hãy thống nhất schema, MIME type, route và cách biểu diễn số/ngày giờ. Không giả định một DTO Java tự động tương thích với mọi serializer ở phía client.

## 10. Timeout, lỗi và vòng đời kết nối

Requester được tạo bằng `builder.tcp(...)` chưa nhất thiết mở socket ngay; kết nối được thiết lập khi request được thực hiện. Một requester có thể dùng chung cho nhiều request trên cùng connection. Đóng requester khi component sở hữu nó dừng:

```java
requester.dispose();
```

Spring Boot cung cấp `RSocketRequester.Builder` dưới dạng prototype bean vì builder có trạng thái. Mỗi điểm injection nhận một builder riêng; không giữ một builder đã cấu hình rồi tái sử dụng cho nhiều kết nối với setup khác nhau.

Timeout ở mức reactive có thể đặt cho từng request:

```java
Mono<Quote> response = requester.route("quotes.latest")
        .data(new QuoteRequest("VN30"))
        .retrieveMono(Quote.class)
        .timeout(Duration.ofSeconds(3));
```

Đoạn code cần import `java.time.Duration`. Timeout ở client chỉ cho biết caller không nhận được response trong thời hạn; không chứng minh server chưa thực hiện nghiệp vụ. Với command có side effect, cần idempotency key hoặc cơ chế tra cứu kết quả trước khi retry.

RSocket error frame kết thúc request/stream tương ứng. Phân loại lỗi validation, lỗi nghiệp vụ và lỗi hạ tầng; dùng `@ControllerAdvice` hoặc xử lý lỗi reactive ở đúng boundary để tạo error contract an toàn. Không trả stack trace hoặc thông tin nội bộ trong payload lỗi.

Request-Stream có thể kết thúc bình thường, phát lỗi hoặc bị requester hủy. Client nên xử lý đủ ba tín hiệu: `onComplete`, `onError` và cancellation. Khi retry stream, cân nhắc cursor/sequence để tránh phát lại hoặc bỏ sót phần tử.

## 11. TCP và WebSocket transport

Ví dụ chính dùng TCP server độc lập trên port 7000. Nếu cần đưa RSocket qua WebSocket endpoint trong ứng dụng WebFlux, cấu hình mapping path và transport:

```properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
```

RSocket được tích hợp vào web server chỉ khi dùng Reactor Netty. Client WebSocket có thể tạo requester bằng URI tương ứng:

```java
RSocketRequester requester = RSocketRequester.builder()
        .webSocket(URI.create("ws://localhost:8080/rsocket"));
```

TCP thường phù hợp cho service-to-service trong network nội bộ. WebSocket hữu ích khi RSocket cần đi qua hạ tầng HTTP/WebSocket hoặc tích hợp với môi trường client đã hỗ trợ WebSocket. Transport không thay đổi semantics của Request-Response và Request-Stream.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Route không được tìm thấy | Tên route giữa `.route(...)` và `@MessageMapping` khác nhau | So sánh route chính xác; kiểm tra controller có được component scan |
| Client báo lỗi decode | Hai đầu không thống nhất MIME type hoặc thiếu codec | Kiểm tra `RSocketStrategies`, `dataMimeType` và schema payload |
| `retrieveMono` không nhận response như mong đợi | Responder trả cardinality khác hoặc route dùng nhầm interaction | Đảm bảo handler trả đúng một `Mono<T>` cho Request-Response |
| Stream chỉ phát một phần tử | Handler trả `Mono` hoặc publisher đã bị `take`, `next`, `single` | Kiểm tra kiểu trả về và các operator giới hạn stream |
| Stream bị lỗi khi client chậm | Nguồn push không theo demand hoặc buffer vượt giới hạn | Dùng publisher backpressure-aware; kiểm tra overflow và concurrency |
| Request treo | Chưa subscribe, responder không emit/complete, dependency không trả kết quả hoặc timeout chưa cấu hình | Kiểm tra subscription, trace route và deadline của dependency |
| Server không khởi động | Port đã được dùng hoặc transport/dependency cấu hình sai | Kiểm tra port, `spring-boot-starter-rsocket` và log bind server |
| Tài nguyên không được giải phóng sau khi client ngắt | Stream không gắn cleanup với cancellation | Dùng `doFinally`, `usingWhen` hoặc cơ chế resource cleanup của Reactor |
| Client mất kết nối sau thời gian idle | Keepalive/timeout của network hoặc RSocket connection | Kiểm tra keepalive, proxy idle timeout, reconnect và session resumption nếu được cấu hình |

Checklist debug theo thứ tự:

1. Xác nhận server đang lắng nghe đúng TCP port hoặc WebSocket path.
2. Kiểm tra requester có subscribe vào `Mono`/`Flux` hay chưa.
3. So sánh route ở client và `@MessageMapping`.
4. Kiểm tra cardinality: một request/một response hay một request/nhiều response.
5. Kiểm tra encoder/decoder và MIME type trên cả hai phía.
6. Theo dõi error signal, timeout và cancellation trong reactive chain.
7. Với stream, kiểm tra demand, operator concurrency và nguồn dữ liệu có hỗ trợ backpressure.

## 13. Mở rộng sau khi chạy được hai interaction

- **Validation:** kiểm tra symbol, count, giới hạn truy vấn và quyền truy cập trước khi gọi service.
- **Authentication:** cấu hình RSocket Security hoặc cơ chế xác thực phù hợp; không tin user/tenant trong payload nếu chưa xác minh.
- **Metadata:** gửi correlation id, tenant hoặc token bằng composite metadata và đăng ký extractor/decoder ở responder.
- **Observability:** ghi route, connection id, request duration, số phần tử stream, lỗi và cancellation; tránh đưa user id hoặc request id có cardinality cao vào metric tag.
- **Timeout/retry:** đặt deadline rõ ràng; chỉ retry lỗi tạm thời và bảo đảm idempotency cho command có side effect.
- **Resume:** RSocket session resumption có thể giúp phục hồi session khi mất kết nối nếu hai phía cấu hình và giữ state phù hợp; nó không thay thế durable event store hoặc business-level replay.
- **Service interface:** khi muốn định nghĩa contract requester/responder bằng Java interface, xem `@RSocketExchange` và `RSocketServiceProxyFactory` như lựa chọn thay thế cho gọi `route(...)` trực tiếp.

## 14. Ghi nhớ

- Request-Response: một request, một response; Spring thường dùng `Mono<T>` và `retrieveMono(T.class)`.
- Request-Stream: một request, nhiều response; Spring thường dùng `Flux<T>` và `retrieveFlux(T.class)`.
- Route nằm trong metadata; object truyền qua `.data(...)` là payload nghiệp vụ.
- Spring Boot tự cấu hình `RSocketMessageHandler` và codec qua `spring-boot-starter-rsocket`.
- RSocket truyền backpressure qua network boundary; dùng nguồn reactive có thể đáp ứng demand.
- Không tự subscribe trong responder; để framework quản lý request, error và cancellation.
- Dùng integration test với port ngẫu nhiên và `StepVerifier` để kiểm tra interaction thật.
- Quản lý timeout, idempotency, security, codec và lifecycle kết nối trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Framework 7.0 — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 4.1 — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketMessageHandler.html)
- [Spring Boot API — Local RSocket server port](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)