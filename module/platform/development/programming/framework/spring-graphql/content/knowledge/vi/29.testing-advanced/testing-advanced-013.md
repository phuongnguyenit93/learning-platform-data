# Test timeout và transport error

Khi kiểm thử Spring for GraphQL, một request có thể thất bại vì nhiều nguyên nhân: GraphQL trả về lỗi trong response, server không trả HTTP thành công, kết nối không thiết lập được, kết nối bị ngắt giữa chừng hoặc response không hoàn tất trong thời gian cho phép. Các trường hợp này có ý nghĩa khác nhau và cần được kiểm thử ở đúng tầng.

`GraphQlTester` cung cấp `responseTimeout(Duration)` để giới hạn thời gian chờ một GraphQL response trong test. Với lỗi xảy ra ở tầng giao vận, client có thể phát sinh `GraphQlTransportException`. Với subscription, cần phân biệt lỗi GraphQL được server gửi qua protocol với lỗi kết nối như `WebSocketDisconnectedException`.

Bài học này trình bày cách đặt timeout cho test, cấu hình timeout ở HTTP client và server, mô phỏng transport failure, kiểm tra subscription stream, cancellation và retry. Mục tiêu là làm cho test có giới hạn thời gian rõ ràng, ổn định và phát hiện đúng loại lỗi.

## 1. Phân biệt GraphQL error, HTTP error và transport error

Một request GraphQL đi qua nhiều lớp. Lỗi ở mỗi lớp được biểu diễn theo cách khác nhau:

~~~mermaid
flowchart TD
    A["Test / GraphQL client"] --> B["Transport client"]
    B --> C{"Kết nối và HTTP/WebSocket/RSocket"}
    C -->|Không kết nối / timeout / disconnect| D["Transport exception"]
    C -->|Nhận HTTP response| E["GraphQL server"]
    E --> F{"GraphQL request"}
    F -->|Parse / validation / execution| G["GraphQL response errors"]
    F -->|Thành công| H["GraphQL data"]
    D --> I["Assert transport failure"]
    G --> J["Assert errors trong response"]
    H --> K["Assert data"]
~~~

Ba nhóm chính:

| Nhóm | Ví dụ | Cách quan sát |
| --- | --- | --- |
| GraphQL response error | Resolver ném exception, field bị cấm, input không hợp lệ | Response có key `errors`; dùng `GraphQlTester.errors()` hoặc `ClientGraphQlResponse.getErrors()` |
| HTTP/protocol error | HTTP 401, 404, 429, 500; WebSocket handshake thất bại | HTTP status hoặc exception do transport client phát ra |
| Transport failure | Connection refused, DNS failure, TLS error, connect timeout, response timeout, WebSocket disconnect | `GraphQlTransportException` hoặc exception ở tầng WebClient/transport |

Một GraphQL response có thể chứa cả `data` và `errors`. Đây là kết quả thực thi GraphQL hợp lệ về mặt giao thức, không đồng nghĩa kết nối bị lỗi.

Ngược lại, nếu server không khả dụng hoặc client không nhận được response, sẽ không có GraphQL response để kiểm tra bằng `errors()`. Khi đó test cần kiểm tra exception hoặc HTTP status ở tầng transport.

## 2. Timeout có nhiều phạm vi khác nhau

Không có một timeout duy nhất áp dụng cho toàn bộ hệ thống. Cần xác định chính xác khoảng thời gian nào đang được giới hạn:

| Timeout | Phạm vi | Nơi cấu hình |
| --- | --- | --- |
| Test response timeout | Thời gian test chờ GraphQL response | `GraphQlTester.Builder.responseTimeout(...)` |
| Client connect timeout | Thời gian thiết lập kết nối TCP/TLS | HTTP/WebSocket/RSocket client |
| Client response/read timeout | Thời gian chờ dữ liệu response từ server | HTTP client hoặc transport tương ứng |
| Connection pool acquire timeout | Thời gian chờ lấy connection từ pool | Connection pool |
| Overall operation timeout | Tổng thời gian cho một publisher/request | Reactor `timeout(...)` hoặc blocking timeout |
| Server GraphQL request timeout | Thời gian server cho phép xử lý request | `TimeoutWebGraphQlInterceptor` |
| Subscription idle/event timeout | Thời gian chờ event tiếp theo trong stream | Reactor `timeout(...)` hoặc chính sách stream |

Các timeout này bảo vệ những tài nguyên khác nhau. Ví dụ `GraphQlTester.responseTimeout` giới hạn thời gian test chờ kết quả; nó không tự cấu hình timeout TCP của HTTP client. Server timeout lại là giới hạn ở phía xử lý request, không thay thế timeout của client.

Khi test timeout, hãy ghi rõ đang xác minh timeout ở lớp nào. Nếu chỉ cấu hình một timeout nhưng mô tả nó như timeout cho toàn bộ request từ đầu đến cuối, test sẽ dễ gây hiểu nhầm.

## 3. Cấu hình responseTimeout của GraphQlTester

Tất cả builder của `GraphQlTester` có thể cấu hình thời gian tối đa chờ GraphQL response bằng `responseTimeout(Duration)`.

Theo mặc định, timeout này là 5 giây. Có thể thay đổi khi tạo tester:

~~~java
import java.time.Duration;

import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient.Builder clientBuilder = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql");

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(clientBuilder)
                .responseTimeout(Duration.ofSeconds(2))
                .build();
~~~

Sau đó dùng tester như bình thường:

~~~java
graphQlTester.document("""
        query {
            health
        }
        """)
        .execute()
        .path("health")
        .entity(String.class)
        .isEqualTo("UP");
~~~

`responseTimeout` áp dụng cho thời gian chờ một response của request test. Nó hữu ích khi test endpoint có thể bị treo hoặc khi muốn đặt giới hạn ngắn hơn mặc định.

Không đặt timeout quá ngắn chỉ để test chạy nhanh. Môi trường CI, container hoặc máy phát triển có độ trễ khác nhau. Hãy chọn giá trị đủ lớn cho test thành công bình thường và đủ nhỏ để test không treo quá lâu khi có lỗi.

## 4. Test timeout với một resolver không hoàn tất

Một cách kiểm tra response timeout là tạo resolver không phát kết quả:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class TimeoutTestController {

    @QueryMapping
    public Mono<String> neverResponds() {
        return Mono.never();
    }
}
~~~

`Mono.never()` không phát giá trị, cũng không hoàn tất hoặc phát lỗi. Đây là nguồn test hữu ích để kiểm tra timeout mà không phụ thuộc vào một dịch vụ ngoài.

Tạo tester có timeout ngắn:

~~~java
HttpGraphQlTester tester =
        HttpGraphQlTester.builder(clientBuilder)
                .responseTimeout(Duration.ofMillis(300))
                .build();
~~~

Trong integration test, thực thi operation `neverResponds` bằng tester này và xác minh lời gọi kết thúc vì response timeout. Kiểu exception hoặc cause cụ thể có thể phụ thuộc tester extension và transport đang được sử dụng; hãy kiểm tra kiểu/cause ổn định mà phiên bản thư viện của dự án phát ra, không phụ thuộc vào message nội bộ của Reactor Netty hoặc HTTP connector. Tránh assertion chung chung rằng bất kỳ `Exception` nào cũng được xem là timeout, vì nó có thể che giấu lỗi cấu hình hoặc lỗi test khác.

Ví dụ này chỉ xác minh test không chờ vô hạn. Nếu muốn kiểm tra server có thực sự hủy xử lý khi timeout hay không, cần thêm một test riêng cho server-side timeout và cancellation.

## 5. Dùng StepVerifier cho publisher và timeout

Với code reactive, có thể áp dụng timeout trực tiếp lên `Mono` hoặc `Flux`:

~~~java
Mono<ClientGraphQlResponse> response = graphQlClient
        .document("""
                query {
                    health
                }
                """)
        .execute()
        .timeout(Duration.ofSeconds(2));
~~~

`timeout(Duration)` giới hạn thời gian tổng thể chờ publisher phát tín hiệu tiếp theo. Nếu hết thời gian, publisher kết thúc bằng `TimeoutException` và hủy subscription nguồn.

Dùng `StepVerifier` để xác minh:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.test.StepVerifier;

@Test
void clientOperationTimesOut() {
    Mono<String> result = Mono.<String>never()
            .timeout(Duration.ofMillis(100));

    StepVerifier.create(result)
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
}
~~~

Ở đây có hai giới hạn:

- `Mono.timeout(...)` là hành vi đang được kiểm tra.
- `StepVerifier.verify(Duration)` là giới hạn bảo vệ chính test, để test không thể treo vô hạn nếu pipeline bị lỗi.

Với test chỉ xác minh operator timeout, có thể dùng `StepVerifier.withVirtualTime(...)` để không phải chờ đồng hồ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(10))
)
        .thenAwait(Duration.ofSeconds(10))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
~~~

Virtual time phù hợp với publisher dựa trên Reactor scheduler. Nó không tự tăng tốc socket thật, DNS, HTTP client hoặc WebSocket server; các integration test qua mạng vẫn cần thời gian thực và một `verify(Duration)` giới hạn.

## 6. Phân biệt test timeout với server request timeout

Spring for GraphQL có `TimeoutWebGraphQlInterceptor` để giới hạn thời gian server xử lý web request. Khi timeout, interceptor trả lỗi HTTP tương ứng và gửi tín hiệu cancel lên chuỗi xử lý. Reactive DataFetcher có thể nhận tín hiệu hủy để dừng công việc đang chạy.

Trong Spring Boot, đăng ký bean:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(3));
    }
}
~~~

Timeout này thuộc phía server. Nó khác với `GraphQlTester.responseTimeout`:

- `GraphQlTester.responseTimeout`: test dừng chờ khi chưa nhận được response đúng hạn.
- `TimeoutWebGraphQlInterceptor`: server chủ động giới hạn thời gian xử lý và hủy công việc upstream khi timeout.

Một client timeout có thể xảy ra trước server timeout. Ví dụ client chỉ chờ 1 giây nhưng server cho phép 3 giây. Khi đó test có thể dừng trước trong khi server vẫn đang xử lý nếu việc ngắt kết nối không được truyền thành cancellation tới tầng xử lý.

Với HTTP status do server timeout trả về, nên dùng `WebTestClient` để kiểm tra status trực tiếp. `HttpGraphQlTester` được thiết kế cho GraphQL response thành công và có thể báo assertion khi HTTP status khác 200.

## 7. Cấu hình connect timeout và response timeout cho HTTP client

`HttpGraphQlClient` dùng `WebClient`. Nếu ứng dụng dùng Reactor Netty, có thể cấu hình timeout ở `HttpClient` rồi gắn vào `WebClient`.

Ví dụ:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.graphql.client.HttpGraphQlClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Trong ví dụ:

- `CONNECT_TIMEOUT_MILLIS` giới hạn thời gian thiết lập kết nối.
- `responseTimeout` của Reactor Netty giới hạn khoảng chờ dữ liệu response theo chính sách của HTTP client.
- `GraphQlTester.responseTimeout` nếu có sẽ là một giới hạn riêng ở tầng test.

Reactor Netty còn có timeout cho việc chờ lấy connection từ pool, TLS handshake và DNS resolution. Nếu ứng dụng dùng connector khác, API cấu hình sẽ khác. Không áp dụng đoạn cấu hình Reactor Netty cho mọi `WebClient`.

## 8. Test HTTP transport error

HTTP transport error có thể xảy ra trước khi GraphQL server trả response:

- Server không chạy hoặc connection bị từ chối.
- Không phân giải được hostname.
- TLS handshake thất bại.
- Server/proxy trả HTTP 502 hoặc 503.
- Request bị từ chối do xác thực hoặc giới hạn lưu lượng.
- Client hết thời gian chờ response.

Đối với `GraphQlClient`, lỗi từ `GraphQlTransport` được biểu diễn hoặc bọc trong `GraphQlTransportException`. Có thể kiểm tra bằng `StepVerifier`:

~~~java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.test.StepVerifier;

@Test
void reportsTransportFailureWhenServerIsUnavailable() {
    Mono<ClientGraphQlResponse> response = graphQlClient
            .document("""
                    query {
                        health
                    }
                    """)
            .execute();

    StepVerifier.create(response)
            .expectError(GraphQlTransportException.class)
            .verify(Duration.ofSeconds(3));
}
~~~

Để test ổn định, hãy trỏ client đến một endpoint test không có server lắng nghe hoặc một mock server được điều khiển bởi test. Không dùng hostname ngoài Internet hoặc một dịch vụ công cộng làm nguồn lỗi vì kết quả phụ thuộc mạng bên ngoài.

Nếu cần kiểm tra HTTP status cụ thể như 503, dùng `WebTestClient` hoặc mock HTTP server để trả status đó. Với `HttpGraphQlTester`, response status không phải 200 có thể làm request assertion thất bại trước khi có `GraphQlTester.Response` để kiểm tra.

## 9. Phân biệt GraphQL errors với transport exceptions

Không dùng cùng một assertion cho mọi loại lỗi.

Ví dụ GraphQL execution error:

~~~java
graphQlTester.document("""
        query {
            book(id: "missing") {
                id
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                "book".equals(error.getPath())
                        && "NOT_FOUND".equals(
                                error.getExtensions().get("code")))
        .verify();
~~~

Ở đây server đã nhận và thực thi GraphQL request. Test có một response để kiểm tra `errors`.

Với transport exception, request không nhận được GraphQL response:

~~~java
StepVerifier.create(
        graphQlClient.document("{ health }").execute()
)
        .expectError(GraphQlTransportException.class)
        .verify(Duration.ofSeconds(3));
~~~

Không gọi `errors().expect(...)` để kiểm tra connection refused hoặc DNS failure. Các API `errors()` chỉ kiểm tra GraphQL errors trong một response đã nhận được.

Với HTTP, cũng cần phân biệt status với GraphQL error. Theo GraphQL over HTTP behavior của Spring for GraphQL, server unavailable, credential không hợp lệ hoặc body không phải JSON có thể tạo HTTP 4xx/5xx. Sau khi GraphQL request đã được validate, lỗi trong quá trình thực thi field thường nằm trong phần `errors` của response. Với media type `application/graphql-response+json`, lỗi parse/validation có thể dùng 4xx; legacy `application/json` có hành vi status khác.

## 10. Kiểm tra HTTP status bằng WebTestClient

Khi cần kiểm tra server trả status nào, dùng `WebTestClient` trực tiếp. Ví dụ server hoặc test stub trả 503:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ health }"))
        .exchange()
        .expectStatus()
        .is5xxServerError();
~~~

Cách này phù hợp để kiểm tra:

- Server không khả dụng hoặc service phụ thuộc đang bảo trì.
- Authentication/authorization ở tầng HTTP.
- Gateway hoặc reverse proxy trả 502/503/504.
- Server-side timeout được chuyển thành HTTP status.

Không hard-code status code nếu hợp đồng ứng dụng chỉ yêu cầu nhóm 5xx. Nếu API của dự án công bố một status cụ thể cho tình huống đó, hãy assertion chính xác status theo hợp đồng.

Với `HttpGraphQlTester`, request có status không phải 200 có thể thất bại ngay ở bước execute. Khi mục tiêu test là status HTTP, `WebTestClient` trực tiếp giúp assertion rõ ràng hơn.

## 11. Test WebSocket disconnect

`WebSocketGraphQlClient` dùng một connection chia sẻ cho nhiều request. Nếu connection bị đóng hoặc mất, client có thể phát sinh `GraphQlTransportException`, với subtype như `WebSocketDisconnectedException`.

Có thể kiểm tra lỗi này ở mức subscription:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class);

StepVerifier.create(events)
        .expectNext("event-1")
        .expectError(WebSocketDisconnectedException.class)
        .verify(Duration.ofSeconds(5));
~~~

Ví dụ giả định test server phát `event-1` rồi chủ động đóng WebSocket connection. Trong integration test, hãy điều khiển server/test fixture để việc disconnect xảy ra đúng thời điểm, thay vì chờ một server bên ngoài tự ngắt.

Với request query/mutation một response, nếu connection mất trước khi nhận kết quả, kiểm tra transport exception tương ứng. Với subscription, stream có thể đã phát một số event trước khi lỗi xuất hiện; test nên kiểm tra cả event đã nhận và lỗi kết thúc.

RSocket cũng dùng một session chia sẻ. Nếu session bị đóng trong khi request đang chạy, kiểm tra transport exception từ request đó. Với session đã mất, `RSocketGraphQlClient` có thể thiết lập lại ở request tiếp theo hoặc khi gọi `start()`. Hãy dùng RSocket server/test fixture cục bộ để chủ động đóng session trong test.

## 12. Phân biệt SubscriptionErrorException và WebSocketDisconnectedException

Hai trường hợp này đều có thể kết thúc subscription stream bằng exception, nhưng nguyên nhân khác nhau:

| Exception | Ý nghĩa | Test nên kiểm tra |
| --- | --- | --- |
| `SubscriptionErrorException` | Server gửi protocol message `error` chứa GraphQL errors | Danh sách GraphQL errors và mã lỗi trong response |
| `WebSocketDisconnectedException` | WebSocket connection bị đóng hoặc mất | Connection failure, reconnect/retry behavior |
| `GraphQlTransportException` | Lỗi chung từ transport hoặc exception được transport bọc lại | Loại transport, cause và request liên quan |

Ví dụ kiểm tra subscription kết thúc bằng GraphQL error:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.graphql.client.SubscriptionErrorException;

StepVerifier.create(subscriptionFlux)
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(SubscriptionErrorException.class);

            SubscriptionErrorException subscriptionError =
                    (SubscriptionErrorException) error;

            assertThat(subscriptionError.getErrors())
                    .anySatisfy(graphQlError ->
                            assertThat(graphQlError.getMessage())
                                    .contains("subscription rejected"));
        })
        .verify(Duration.ofSeconds(5));
~~~

Ví dụ kiểm tra WebSocket disconnect:

~~~java
StepVerifier.create(subscriptionFlux)
        .expectError(WebSocketDisconnectedException.class)
        .verify(Duration.ofSeconds(5));
~~~

Nếu test chỉ kiểm tra `GraphQlTransportException` chung, nó có thể bỏ qua sự khác biệt giữa server gửi GraphQL error và connection bị ngắt. Hãy dùng subtype khi subtype là một phần của hành vi cần xác minh.

## 13. Kiểm thử subscription timeout và cancellation

Subscription là một stream kéo dài theo thời gian, không phải một request có đúng một response. Do đó, không nên dùng response timeout của request thông thường như giới hạn thời gian sống của toàn bộ stream.

Có thể dùng Reactor `timeout` để giới hạn thời gian chờ event tiếp theo:

~~~java
Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu không có event mới trong khoảng thời gian cho phép, stream phát `TimeoutException`. Với WebSocket, việc hủy subscription từ client sẽ gửi message `complete` để báo server dừng subscription đó.

Kiểm thử cancellation sau khi nhận đủ số event:

~~~java
StepVerifier.create(events)
        .expectNext("event-1")
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

Nếu muốn xác minh server đã nhận cancellation, test fixture có thể ghi nhận hook `doOnCancel` hoặc tín hiệu cleanup ở publisher phía server:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<String> eventSink =
        Sinks.many().multicast().onBackpressureBuffer();
Sinks.One<Void> cancellationSignal = Sinks.one();

Flux<String> eventPublisher = eventSink.asFlux()
        .doOnCancel(() -> cancellationSignal.tryEmitEmpty());

StepVerifier.create(eventPublisher)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

StepVerifier.create(cancellationSignal.asMono())
        .expectComplete()
        .verify(Duration.ofSeconds(2));
~~~

Sau khi client cancel, test có thể chờ `cancellationSignal` hoàn tất để xác minh server đã dọn subscription. Không dùng `Thread.sleep` để đoán server đã nhận message; hãy đồng bộ bằng signal hoặc latch có timeout.

## 14. Retry sau transport failure

Một subscription có thể được khởi động lại khi transport mất kết nối. Spring for GraphQL client docs minh họa việc dùng Reactor `retry` cho `GraphQlTransportException`, chẳng hạn `WebSocketDisconnectedException`.

Ví dụ retry có giới hạn:

~~~java
import reactor.util.retry.Retry;

Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(WebSocketDisconnectedException.class::isInstance));
~~~

Retry chỉ nên áp dụng cho loại lỗi được xem là có thể phục hồi:

- Mất kết nối tạm thời.
- Gateway reset connection.
- Server restart trong một cửa sổ triển khai có kiểm soát.

Không retry vô điều kiện cho mọi exception. Ví dụ `SubscriptionErrorException` có thể biểu thị server chủ động từ chối subscription; retry liên tục không sửa được lỗi nghiệp vụ hoặc quyền truy cập.

Đặc biệt cẩn thận với mutation. Nếu client mất kết nối sau khi server đã thực hiện mutation nhưng trước khi response về, client không biết thao tác đã commit hay chưa. Retry có thể thực hiện mutation lần thứ hai. Chỉ retry mutation khi operation có idempotency key hoặc cơ chế bảo đảm không tạo tác dụng phụ trùng lặp.

## 15. Quản lý vòng đời tester và connection trong test

`WebSocketGraphQlTester` và `RSocketGraphQlTester` là connection-oriented. Mỗi tester duy trì một connection/session dùng chung cho các request. Nên tái sử dụng một tester cho các request cùng server và đóng connection sau khi test hoàn tất.

`RSocketGraphQlClient` cũng duy trì một session dùng chung. Nếu session bị mất, client thiết lập lại ở request tiếp theo hoặc khi gọi `start()`; `stop()` hủy request đang chạy và đóng session. Vì vậy, test RSocket nên xác định rõ đang kiểm tra lỗi của một request hay hành vi reconnect của session.

Ví dụ:

~~~java
WebSocketGraphQlTester tester =
        WebSocketGraphQlTester.builder(uri, webSocketClient).build();

try {
    tester.document("query { health }")
            .execute()
            .path("health")
            .entity(String.class)
            .isEqualTo("UP");
}
finally {
    tester.stop();
}
~~~

`RSocketGraphQlTester` cũng có `stop()` để đóng session. Không tạo nhiều tester WebSocket/RSocket cho từng assertion nếu test có thể dùng lại một instance; mỗi instance có thể mở connection riêng.

Nếu dùng `WebSocketGraphQlClient`, phương thức `stop()` đóng connection và hủy request đang chạy. Test cần gọi nó trong teardown để tránh connection còn sống sau khi test kết thúc.

## 16. Thiết kế test timeout ổn định

Timeout test rất dễ flaky nếu phụ thuộc vào tốc độ máy, tải CI hoặc dịch vụ bên ngoài. Một số nguyên tắc:

- Dùng `Mono.never()` hoặc publisher do test kiểm soát để mô phỏng không có response.
- Đặt thời gian timeout có khoảng cách đủ lớn so với độ trễ dự kiến.
- Bao mọi `StepVerifier.verify(...)` bằng một thời gian tối đa.
- Dùng virtual time cho publisher thuần Reactor khi có thể.
- Không dùng `Thread.sleep` để chờ một trạng thái bất đồng bộ.
- Không gọi dịch vụ Internet công cộng để tạo connection failure.
- Không assertion nguyên văn thông báo lỗi của Netty, DNS hoặc TLS nếu message không phải hợp đồng ổn định.
- Đóng tester/connection trong `finally`, `@AfterEach` hoặc lifecycle callback.
- Kiểm tra cả cancellation khi timeout, không chỉ kiểm tra exception.
- Tách test server timeout khỏi test client response timeout.

Với HTTP tester, tạo một tester có `responseTimeout` ngắn như phần trước, gọi operation `neverResponds` và assertion theo timeout exception/cause mà transport của dự án phát ra. Không dùng assertion chung rằng bất kỳ `Exception` nào cũng là timeout; cách đó có thể chấp nhận nhầm lỗi cấu hình, lỗi serialization hoặc lỗi test fixture.

Ở test khác, kiểm tra client publisher timeout:

~~~java
@Test
void reactiveClientTimeoutIsBounded() {
    StepVerifier.create(Mono.<String>never()
                    .timeout(Duration.ofMillis(100)))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
}
~~~

Hai test này kiểm tra hai tầng khác nhau. Giữ chúng độc lập giúp khi thất bại có thể biết lỗi nằm ở test harness hay ở logic timeout của publisher.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test treo khi resolver không hoàn tất | Chưa đặt `GraphQlTester.responseTimeout` hoặc giới hạn cuối cho StepVerifier | Đặt response timeout và `verify(Duration)` |
| Test timeout nhưng server vẫn chạy | Chỉ cấu hình timeout ở client | Kiểm tra server timeout và cancellation riêng |
| `errors()` không bắt được connection refused | Không có GraphQL response để kiểm tra | Assert `GraphQlTransportException` hoặc cause |
| HTTP 503 bị xem như GraphQL error | Nhầm HTTP status với response `errors` | Dùng `WebTestClient` kiểm tra status |
| Test phụ thuộc message của Netty | Message có thể thay đổi theo connector/OS | Kiểm tra exception type và cause ổn định |
| WebSocket test để lại connection | Quên gọi `stop()` | Đóng tester/client trong teardown |
| Subscription không kết thúc sau `thenCancel()` | Server không nhận hoặc không xử lý cancellation | Xác minh publisher có cleanup và chờ signal có timeout |
| Retry lặp vô hạn | Retry không có giới hạn hoặc không lọc exception | Dùng `Retry.backoff` có giới hạn và predicate cụ thể |
| Mutation bị thực hiện hai lần sau retry | Client không biết lần đầu đã commit hay chưa | Dùng idempotency key hoặc không retry mutation không an toàn |
| Timeout test lúc pass lúc fail | Dựa vào `sleep`, thời gian quá sát hoặc mạng ngoài | Dùng publisher có thể kiểm soát và timeout có khoảng an toàn |
| Server timeout bị nhầm với client timeout | Chỉ nhìn thấy request kết thúc mà không biết lớp nào dừng | Kiểm tra status server và cấu hình timeout từng tầng |

## 18. Quy trình kiểm thử timeout và transport error

Khi viết test cho một GraphQL operation, hãy thực hiện theo thứ tự:

1. Xác định request là query/mutation một response hay subscription stream.
2. Xác định lỗi cần kiểm tra là GraphQL response error, HTTP status, transport failure hay timeout.
3. Chọn đúng tester/client cho transport đang dùng.
4. Đặt `GraphQlTester.responseTimeout` để giới hạn thời gian test chờ response.
5. Cấu hình connect/response timeout ở HTTP hoặc WebSocket/RSocket client khi cần.
6. Dùng publisher có thể điều khiển để mô phỏng resolver chậm hoặc không hoàn tất.
7. Dùng `StepVerifier` để xác minh timeout, stream error và cancellation.
8. Kiểm tra server timeout riêng bằng `TimeoutWebGraphQlInterceptor` và `WebTestClient`.
9. Kiểm tra transport failure bằng exception/cause hoặc HTTP status tương ứng.
10. Chỉ retry lỗi tạm thời và có giới hạn; đặc biệt tránh retry mutation không idempotent.
11. Đóng connection/session sau test và bảo đảm mọi thao tác bất đồng bộ đều có giới hạn thời gian.

## 19. Những điểm cần ghi nhớ

- `GraphQlTester.responseTimeout(Duration)` giới hạn thời gian chờ GraphQL response; mặc định là 5 giây.
- Test timeout, client network timeout và server request timeout là ba phạm vi riêng.
- `GraphQlTransportException` biểu thị lỗi từ transport hoặc exception được transport bọc lại.
- `SubscriptionErrorException` mang GraphQL errors do server gửi qua subscription protocol.
- `WebSocketDisconnectedException` biểu thị WebSocket connection bị mất.
- `GraphQlTester.errors()` kiểm tra GraphQL response errors, không kiểm tra connection failure.
- Dùng `WebTestClient` trực tiếp khi cần assertion HTTP status.
- Dùng `StepVerifier.verify(Duration)` để bảo vệ test reactive khỏi treo vô hạn.
- Subscription timeout/cancel cần được kiểm tra như một stream; cancellation WebSocket gửi message `complete`.
- Retry phải giới hạn và chỉ áp dụng cho lỗi tạm thời; mutation cần bảo đảm idempotency trước khi retry.

Kiểm thử timeout và transport error tốt giúp phát hiện lỗi ở đúng ranh giới của hệ thống. Khi tách biệt GraphQL response errors, HTTP status và transport exceptions, đồng thời giới hạn thời gian cho cả request lẫn stream, test sẽ dễ chẩn đoán và ít phụ thuộc vào môi trường chạy hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlTransportException API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransportException.html)
- [Reactor Netty — Timeout Configuration](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html)

