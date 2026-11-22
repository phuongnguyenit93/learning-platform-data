# Test WebSocket subscription

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích phạm vi kiểm thử của WebSocketGraphQlTester.
- Cấu hình WebSocket endpoint và tạo tester kết nối tới server đang chạy.
- Gửi subscription bằng executeSubscription() và kiểm tra stream với StepVerifier.
- Đồng bộ test với thời điểm server đã đăng ký event source.
- Kiểm tra event payload, thứ tự phát và kết thúc stream.
- Xác minh cancellation được truyền tới publisher để giải phóng tài nguyên.
- Phân biệt lỗi GraphQL của subscription với lỗi WebSocket transport.
- Kiểm thử authentication qua connection_init và nhiều operation trên một connection.
- Chọn đúng mức kiểm thử cho resolver, WebSocket protocol và toàn bộ deployment.

## Vì sao cần kiểm thử qua WebSocket?

Subscription khác query và mutation ở chỗ một operation có thể tạo ra nhiều response theo thời gian. Resolver thường trả về Flux hoặc một Reactive Streams Publisher. Server đăng ký publisher, sau đó phát từng kết quả tới client khi event xuất hiện.

Một unit test gọi trực tiếp method trả Flux có thể xác minh publisher phát đúng dữ liệu, nhưng không kiểm tra được:

- WebSocket endpoint có được bật và truy cập đúng path hay không.
- Client và server có bắt tay WebSocket thành công hay không.
- Hai phía có dùng cùng GraphQL over WebSocket subprotocol hay không.
- Message connection initialization và subscription operation có được xử lý đúng hay không.
- Event có được gửi thành nhiều response tới client hay không.
- Client hủy stream có khiến server dừng publisher hay không.
- Connection đóng có kết thúc các operation đang chạy hay không.

Spring for GraphQL cung cấp WebSocketGraphQlTester để kiểm thử GraphQL request qua một WebSocket connection thực. Tester dùng chung workflow GraphQlTester nhưng bổ sung cấu hình và lifecycle của WebSocket transport. [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)

## Phân biệt các lớp kiểm thử Subscription

Không phải mọi test subscription đều cần mở WebSocket. Hãy chọn tester theo ranh giới muốn xác minh:

| Cách kiểm thử | Điều được xác minh | Điều không được xác minh |
| --- | --- | --- |
| Unit test publisher bằng StepVerifier | Logic tạo event, thứ tự và cancellation của Flux | GraphQL schema, resolver mapping, WebSocket protocol |
| ExecutionGraphQlServiceTester | GraphQL subscription execution ở server side | WebSocket handshake và message protocol |
| WebGraphQlTester | WebGraphQlHandler, interceptor chain và subscription execution ở server side | WebSocket handshake, connection_init và transport thực |
| WebSocketGraphQlTester | WebSocket connection, GraphQL operation, event stream và cancellation | TLS/proxy/load balancer thật nếu test không chạy qua các thành phần đó |
| End-to-end test trên môi trường triển khai | Tích hợp server, proxy, auth, mạng và client thực tế | Không thay thế được unit test nhanh cho logic publisher |

Nếu mục tiêu là kiểm tra publisher hoặc business logic, unit test thường nhanh và dễ chẩn đoán hơn. Nếu cần chứng minh subscription đi qua WebSocket đúng cách, hãy dùng WebSocketGraphQlTester với server đang chạy.

## Chuẩn bị endpoint và dependency

Ứng dụng cần có Spring for GraphQL và một WebSocket server transport. Spring Boot không bật endpoint GraphQL WebSocket mặc định; cấu hình path để đăng ký handler:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 20s
~~~

Với Spring MVC, thêm spring-boot-starter-websocket. Với Spring WebFlux, WebSocket transport đã có trong stack WebFlux. Ứng dụng cũng cần spring-boot-starter-graphql.

Ở phía test, cần spring-graphql-test và reactor-test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

WebSocketGraphQlTester dùng WebSocketClient từ Spring WebFlux. Nếu ứng dụng MVC không có sẵn WebSocket client, thêm Spring WebFlux và một implementation client như Reactor Netty vào test runtime theo dependency management của Spring Boot. Không cần thay server MVC bằng WebFlux chỉ để chạy tester.

Giữ phiên bản Spring GraphQL, Spring Boot, Spring Framework và Reactor tương thích theo BOM của dự án. API ví dụ dưới đây dùng kiểu API hiện hành của Spring for GraphQL; nếu dự án ở release line cũ, kiểm tra package và dependency tương ứng.

## Tạo WebSocketGraphQlTester

WebSocketGraphQlTester cần endpoint URL và một WebSocketClient. Ví dụ test khởi động ứng dụng trên cổng ngẫu nhiên:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.graphql.websocket.path=/graphql")
class BookSubscriptionWebSocketTests {

    @LocalServerPort
    int port;

    @Autowired
    TestBookEventSource eventSource;

    WebSocketGraphQlTester tester;

    @BeforeEach
    void setUp() {
        String url = "ws://localhost:" + port + "/graphql";
        tester = WebSocketGraphQlTester.builder(
                url, new ReactorNettyWebSocketClient()).build();
    }

    @AfterEach
    void tearDown() {
        if (tester != null) {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }
}
~~~

RANDOM_PORT cho phép Spring Boot khởi động server thật trong test. URL client dùng ws:// cho kết nối không mã hóa; môi trường HTTPS cần endpoint wss:// cùng cấu hình TLS phù hợp.

WebSocketGraphQlTester là connection-oriented và multiplexed. Mỗi instance duy trì một connection dùng chung cho nhiều request/operation. Hãy tái sử dụng tester trong phạm vi test suite hoặc test class thay vì tạo instance mới cho từng event. Gọi stop() khi hoàn tất để đóng connection và hủy request đang chạy.

Connection thường được thiết lập tự động khi request đầu tiên được gửi. Có thể gọi tester.start().block() nếu test cần mở connection tường minh trước khi gửi operation, ví dụ để kiểm tra handshake hoặc thời điểm khởi tạo. Không bắt buộc gọi start() trước mọi request.

## Viết subscription resolver mẫu

Schema khai báo root Subscription:

~~~graphql
type Subscription {
  greetings: String!
}
~~~

Resolver trả về một stream hữu hạn:

~~~java
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class GreetingSubscriptionController {

    @SubscriptionMapping
    public Flux<String> greetings() {
        return Flux.just("Hi", "Bonjour", "Hola");
    }
}
~~~

Resolver phát ba giá trị rồi hoàn tất. Đây là nguồn event hữu hạn, phù hợp để kiểm tra việc nhận nhiều response và kết thúc operation mà không cần đồng bộ với một publisher dùng chung.

Với event động, schema và resolver có thể khai báo như sau:

~~~graphql
enum BookCategory {
  TECHNOLOGY
  FICTION
}

extend type Subscription {
  bookCreated(category: BookCategory): BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  book: BookView!
}

type BookView {
  id: ID!
  title: String!
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;

@Controller
public class BookSubscriptionController {

    private final TestBookEventSource eventSource;

    public BookSubscriptionController(TestBookEventSource eventSource) {
        this.eventSource = eventSource;
    }

    @SubscriptionMapping
    public Flux<BookCreatedEvent> bookCreated(
            @Argument("category") BookCategory category) {
        return eventSource.events()
                .filter(event -> category == null
                        || event.category() == category);
    }
}
~~~

Các kiểu dữ liệu Java tương ứng:

~~~java
public enum BookCategory {
    TECHNOLOGY, FICTION
}

public record BookCreatedEvent(
        String eventId,
        BookView book,
        BookCategory category) {
}

public record BookView(String id, String title) {
}
~~~

Trong ứng dụng thật, event source nên lọc theo quyền và tenant ở server. Ví dụ trên chỉ minh họa cách filter để kiểm thử argument; không dùng category do client gửi làm cơ chế authorization.

## Kiểm tra event stream bằng executeSubscription()

Đối với subscription, dùng executeSubscription() thay cho execute(). Phương thức này trả về một stream response; toFlux(path, type) giải mã field tại path của từng response:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import org.springframework.graphql.client.SubscriptionErrorException;

@Test
void receivesAllGreetingEvents() {
    Flux<String> greetings = tester.document("""
            subscription GreetingEvents {
                greetings
            }
            """)
            .executeSubscription()
            .toFlux("greetings", String.class);

    StepVerifier.create(greetings)
            .expectNext("Hi")
            .expectNext("Bonjour")
            .expectNext("Hola")
            .verifyComplete(Duration.ofSeconds(10));
}
~~~

StepVerifier kiểm tra thứ tự, nội dung và tín hiệu kết thúc của Flux. verifyComplete(Duration) đặt giới hạn thời gian cho toàn bộ test để một subscription bị treo không làm suite chờ vô hạn.

execute() dành cho operation có một response như query hoặc mutation. Dùng nó cho subscription sẽ không kiểm tra được chuỗi response. Khi subscription cần phát dữ liệu liên tục, luôn kiểm tra stream bằng executeSubscription() và Reactor Test.

## Kiểm tra variables và arguments

Subscription có thể nhận argument giống query:

~~~graphql
extend type Subscription {
  bookCreated(category: BookCategory): BookCreatedEvent!
}
~~~

Client truyền variable:

~~~java
Flux<BookCreatedEvent> events = tester.document("""
        subscription BookCreated($category: BookCategory) {
            bookCreated(category: $category) {
                eventId
                book {
                    id
                    title
                }
            }
        }
        """)
        .variable("category", "TECHNOLOGY")
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);
~~~

Test nên xác minh event source nhận đúng filter và không phát event ngoài phạm vi:

- Phát một event thuộc TECHNOLOGY.
- Phát một event thuộc FICTION.
- Xác minh subscriber chỉ nhận event TECHNOLOGY.
- Xác minh subscriber khác có filter riêng không nhận dữ liệu của nhau.

Không chỉ kiểm tra event payload. Khi filter là một phần của contract, hãy kiểm tra cả hành vi lọc để tránh lỗi lộ dữ liệu giữa nhóm người đăng ký.

## Đồng bộ test với thời điểm server đã subscribe

Một lỗi phổ biến trong test bất đồng bộ là phát event quá sớm. StepVerifier.create(flux) đăng ký vào Flux phía client, nhưng điều đó không có nghĩa server đã nhận message subscribe và đăng ký vào event publisher.

Nếu test phát event ngay sau khi tạo Flux, event có thể xuất hiện trước khi server đăng ký. Với multicast sink không replay, event đó sẽ bị bỏ lỡ và test có thể timeout.

Một test fixture có thể phát tín hiệu khi publisher được subscribe và khi cancellation đến:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class TestBookEventSource {

    private final Sinks.Many<BookCreatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(16, false);

    private final CountDownLatch subscribed = new CountDownLatch(1);
    private final CountDownLatch cancelled = new CountDownLatch(1);

    public Flux<BookCreatedEvent> events() {
        return sink.asFlux()
                .doOnSubscribe(subscription -> subscribed.countDown())
                .doOnCancel(cancelled::countDown);
    }

    public void publish(BookCreatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException("Could not publish test event: " + result);
        }
    }

    public boolean awaitSubscribed(Duration timeout) throws InterruptedException {
        return subscribed.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public boolean awaitCancelled(Duration timeout) throws InterruptedException {
        return cancelled.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Đây là fixture minh họa cho một test đơn lẻ; nếu dùng nhiều test trên cùng bean, hãy tạo lại latch hoặc reset trạng thái cho mỗi test. onBackpressureBuffer(16, false) giới hạn buffer và giữ sink hoạt động sau khi subscriber cuối cùng hủy. Test fixture phải kiểm tra EmitResult để không âm thầm bỏ qua lỗi phát event.

Test subscription có thể chờ tín hiệu subscribe trước khi phát:

~~~java
@Test
void receivesEventAndCancelsSource() throws Exception {
    BookCreatedEvent expected = new BookCreatedEvent(
            "event-1",
            new BookView("book-101", "Spring for GraphQL"),
            BookCategory.TECHNOLOGY);

    Flux<BookCreatedEvent> events = tester.document("""
            subscription {
                bookCreated {
                    eventId
                    book {
                        id
                        title
                    }
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookCreated", BookCreatedEvent.class);

    StepVerifier.create(events)
            .then(() -> {
                assertThat(eventSource.awaitSubscribed(Duration.ofSeconds(5)))
                        .isTrue();
                eventSource.publish(expected);
            })
            .expectNext(expected)
            .thenCancel()
            .verify(Duration.ofSeconds(10));

    assertThat(eventSource.awaitCancelled(Duration.ofSeconds(5))).isTrue();
}
~~~

Khi client hủy subscription, transport gửi message complete cho operation đó. Server hủy subscription tới publisher; test fixture quan sát cancellation qua doOnCancel. Điều này chứng minh event source được giải phóng sau khi client không còn nhận event.

Không dùng Thread.sleep() để đoán thời điểm server đã subscribe. Dùng latch, signal hoặc cơ chế đồng bộ có điều kiện để test ổn định trên máy chậm và CI.

## Kiểm tra nhiều subscription trên một connection

WebSocketGraphQlTester multiplex nhiều operation trên cùng một connection. Mỗi subscription operation có ID riêng trong protocol, vì vậy server phải ghép đúng event stream với đúng operation.

Có thể kiểm thử hai subscription đồng thời:

~~~java
Flux<BookCreatedEvent> technologyEvents = tester.document("""
        subscription {
            bookCreated(category: TECHNOLOGY) {
                eventId
                book { id title }
            }
        }
        """)
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);

Flux<BookCreatedEvent> fictionEvents = tester.document("""
        subscription {
            bookCreated(category: FICTION) {
                eventId
                book { id title }
            }
        }
        """)
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);
~~~

Đăng ký hai stream trong cùng test, chờ cả hai nguồn đã subscribe, sau đó phát event cho từng category. Xác minh mỗi stream chỉ nhận đúng event. Khi kết thúc, hủy cả hai stream và kiểm tra publisher không còn subscriber.

Không tạo một WebSocketGraphQlTester riêng cho mỗi operation nếu muốn kiểm tra multiplexing. Cùng một tester mới chứng minh nhiều operation đang dùng một connection chung.

## Kiểm tra cancellation và cleanup

Cancellation là một phần của contract subscription. Khi người dùng rời trang, đóng màn hình hoặc hủy tác vụ, client phải dừng nhận event. Server cần giải phóng:

- Listener đăng ký với event source hoặc message broker.
- Tài nguyên database cursor hoặc stream từ hệ thống ngoài.
- Buffer và queue dành cho operation.
- Context, tracing span và các callback gắn với stream.

Một test cancellation nên xác minh hai điều:

1. Flux ở client kết thúc theo cancellation mà test yêu cầu.
2. Publisher hoặc adapter ở server nhận cancellation và cleanup listener/tài nguyên.

StepVerifier.thenCancel() chỉ hủy subscription ở phía client. Để chứng minh server cleanup, cần quan sát source bằng latch, counter, spy hoặc một resource test fixture. Không kết luận rằng server đã giải phóng tài nguyên chỉ vì test client đã gọi dispose hoặc cancel.

Khi test nhiều operation, hủy từng stream hoặc gọi tester.stop() để đóng connection. stop() hủy các request đang chạy, đóng WebSocket connection và từ chối request mới qua tester đó. Sau khi stop, tạo tester mới nếu test cần kết nối lại.

## Kiểm tra lỗi của subscription

Cần phân biệt lỗi xảy ra trong GraphQL subscription với lỗi ở tầng WebSocket:

| Loại lỗi | Ví dụ | Kết quả phía client |
| --- | --- | --- |
| Lỗi GraphQL trong publisher | Publisher kết thúc bằng error và được SubscriptionExceptionResolver chuyển thành GraphQL errors | SubscriptionErrorException |
| WebSocket bị đóng giữa stream | Server restart, proxy đóng connection hoặc client stop | WebSocketDisconnectedException, là một GraphQlTransportException |
| Lỗi mở connection hoặc khởi tạo protocol | Sai endpoint, handshake thất bại hoặc connection init bị từ chối | Lỗi transport/connection initialization |
| Query document không hợp lệ | Sai field hoặc sai kiểu variable | Lỗi GraphQL request; operation không tạo stream bình thường |

Lỗi phát sinh sau khi subscription Publisher đã được tạo không đi qua DataFetcherExceptionResolver thông thường, vì data fetcher chỉ tạo Publisher ban đầu. Spring for GraphQL có SubscriptionExceptionResolver để chuyển lỗi từ Publisher thành GraphQL errors gửi trong message error cuối cùng. [Request Execution – Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)

SubscriptionErrorException là một GraphQlTransportException có chứa danh sách GraphQL errors nhận từ message error của operation. WebSocketDisconnectedException cũng là GraphQlTransportException nhưng biểu thị connection bị đóng hoặc mất trong khi stream còn hoạt động. Phân biệt hai nguyên nhân này giúp client chọn cách xử lý phù hợp.

Ví dụ kiểm tra lỗi đã được resolver chuyển thành subscription error:

~~~java
Flux<String> greetings = tester.document("""
        subscription {
            greetings
        }
        """)
        .executeSubscription()
        .toFlux("greetings", String.class);

StepVerifier.create(greetings)
        .expectNext("Hi")
        .expectError(SubscriptionErrorException.class)
        .verify(Duration.ofSeconds(10));
~~~

Test này giả định server publisher phát "Hi" rồi kết thúc bằng lỗi đã được SubscriptionExceptionResolver xử lý. Có thể kiểm tra các GraphQL errors bên trong SubscriptionErrorException để xác minh mã lỗi theo contract của ứng dụng.

Với transport disconnect, hãy kiểm tra WebSocketDisconnectedException hoặc lớp cha GraphQlTransportException tùy mức chi tiết mà test cần. Không assert mọi lỗi subscription đều là lỗi GraphQL; mất kết nối là một lỗi transport khác.

## Kiểm tra authentication qua connection_init

WebSocket protocol có message connection_init ở đầu connection. Nếu server lấy token từ payload này, test client cần gửi payload đúng cách.

Spring for GraphQL cung cấp WebSocketGraphQlClientInterceptor để tạo connection initialization payload. WebSocketGraphQlTester builder cũng cho phép đăng ký client interceptor:

~~~java
import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import reactor.core.publisher.Mono;

WebSocketGraphQlClientInterceptor authInterceptor =
        new WebSocketGraphQlClientInterceptor() {

            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                        "Authorization", "Bearer test-token"));
            }
        };

WebSocketGraphQlTester authenticatedTester =
        WebSocketGraphQlTester.builder(
                url, new ReactorNettyWebSocketClient())
                .interceptor(authInterceptor)
                .build();
~~~

Server cần có WebSocket authentication interceptor tương ứng để đọc payload, xác thực token và truyền SecurityContext tới các request subscription. Có interceptor built-in AuthenticationWebSocketInterceptor cho WebMVC và WebFlux; ứng dụng cũng có thể tự triển khai WebSocketGraphQlInterceptor.

Test nên có ít nhất hai trường hợp:

- Token hợp lệ: connection được chấp nhận và subscription chỉ nhận event trong phạm vi quyền của principal.
- Token không hợp lệ hoặc thiếu token: connection init bị từ chối hoặc operation không được phép chạy theo policy của server.

Đừng chỉ kiểm tra rằng client gửi header hoặc payload. Hãy xác minh server thực sự áp dụng identity và authorization bằng kết quả subscription. Header của WebSocket handshake và payload của connection_init là hai vị trí khác nhau; dùng đúng nơi mà server authentication interceptor đang đọc.

## Connection lifecycle, reconnect và timeout

WebSocketGraphQlTester giữ connection dùng chung. Có thể chủ động mở connection bằng start() và đóng bằng stop(). Khi connection mất, tester/client có thể kết nối lại cho request tiếp theo hoặc khi gọi start lại; subscription đang chạy có thể kết thúc bằng lỗi transport.

Reconnect không tự bảo đảm event delivery:

- Event phát trong lúc client mất kết nối có thể bị bỏ lỡ.
- Nếu nguồn event replay, client có thể nhận lại event đã xử lý.
- Retry subscription không tự cung cấp exactly-once delivery.

Nếu ứng dụng cần resume, event nên có ID hoặc cursor. Client lưu checkpoint cuối cùng đã xử lý và gửi cursor khi đăng ký lại; server dùng event store hoặc broker hỗ trợ replay để tiếp tục từ vị trí phù hợp. Test reconnect nên xác minh đúng contract replay/idempotency của ứng dụng thay vì giả định WebSocket sẽ tự lưu lịch sử.

Đặt timeout cho cả response và stream:

- responseTimeout trên tester giới hạn thời gian chờ response theo cấu hình chung.
- StepVerifier.verify(Duration) giới hạn thời gian test stream.
- connection-init-timeout phía server giới hạn thời gian chờ connection initialization.
- keep-alive và timeout của proxy/load balancer phải tương thích để tránh đóng connection nhàn rỗi ngoài dự kiến.

Test nên dùng timeout hữu hạn để thất bại nhanh khi server không phát event hoặc handshake bị treo.

## Kiểm tra protocol và giới hạn của tester

WebSocketGraphQlTester kiểm tra WebSocket client transport và GraphQL operation theo giao thức mà Spring for GraphQL hỗ trợ. Nó trừu tượng hóa chi tiết message nên test không cần tự viết JSON cho connection_init, subscribe, next, error và complete.

Nếu cần xác minh chính xác frame, close code hoặc một hành vi protocol đặc thù ở tầng thấp, hãy bổ sung test với WebSocket client cấp thấp hoặc protocol conformance test. Không ép test nghiệp vụ phải phụ thuộc vào chuỗi JSON nội bộ của từng message.

Spring for GraphQL hỗ trợ GraphQL over WebSocket theo protocol graphql-transport-ws từ dự án graphql-ws. Protocol cũ subscriptions-transport-ws là một giao thức khác; client và server phải thống nhất protocol. [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)

WebSocketGraphQlTester không kiểm tra TLS certificate, reverse proxy, load balancer, firewall hay giới hạn connection của production nếu test không chạy qua các thành phần đó. Các rủi ro triển khai này cần integration hoặc end-to-end test riêng.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Handshake trả 404 | WebSocket endpoint chưa được bật hoặc path sai | Cấu hình spring.graphql.websocket.path và kiểm tra URL |
| Handshake thất bại | Dùng http/https không đúng scheme hoặc server chưa sẵn sàng | Dùng ws/wss tương ứng và chờ server khởi động |
| Test timeout, không nhận event | Event được phát trước khi server subscribe | Đồng bộ bằng latch hoặc subscription signal |
| Chỉ nhận một response rồi test kết thúc | Dùng execute() thay vì executeSubscription() | Dùng executeSubscription() và StepVerifier |
| Test treo khi publisher không hoàn tất | Dùng verifyComplete cho stream vô hạn | Dùng thenCancel() hoặc timeout có chủ đích |
| Cancellation không giải phóng listener | Source không xử lý cancel hoặc test chỉ hủy phía client | Quan sát doOnCancel/doFinally và cleanup thực tế |
| Event của subscription khác bị trộn | Lọc sai hoặc ghép operation không đúng | Dùng tester chung, filter rõ và kiểm tra từng stream |
| Lỗi publisher thành lỗi transport | Không cấu hình SubscriptionExceptionResolver hoặc server đóng connection | Phân biệt SubscriptionErrorException với GraphQlTransportException |
| Authentication test luôn anonymous | Gửi credential ở handshake nhưng server đọc connection_init | Gửi payload qua WebSocketGraphQlClientInterceptor |
| Test reconnect nhận thiếu hoặc trùng event | Không có cursor hoặc idempotency | Xây dựng event ID/checkpoint và test replay contract |
| Test chạy qua WebGraphQlTester nhưng WS production lỗi | Test chưa đi qua WebSocket transport | Bổ sung WebSocketGraphQlTester với server thật |

## Thực hành tổng hợp

Xây dựng integration test cho tính năng thông báo sách mới:

1. Bật endpoint bằng spring.graphql.websocket.path=/graphql.
2. Khai báo Subscription.bookCreated và BookCreatedEvent trong SDL.
3. Tạo publisher phát event và có thể quan sát subscribe/cancel trong test fixture.
4. Viết resolver @SubscriptionMapping trả về Flux<BookCreatedEvent>.
5. Khởi động ứng dụng bằng @SpringBootTest(webEnvironment = RANDOM_PORT).
6. Tạo WebSocketGraphQlTester bằng endpoint ws:// và ReactorNettyWebSocketClient.
7. Gửi subscription qua executeSubscription() và xác minh event bằng StepVerifier.
8. Chờ server subscribe trước khi phát event để tránh race condition.
9. Hủy stream bằng thenCancel() và xác minh server publisher nhận cancellation.
10. Tạo subscription có filter category và xác minh mỗi client chỉ nhận event phù hợp.
11. Gửi token qua connection_init payload và kiểm thử token hợp lệ/không hợp lệ.
12. Kiểm tra SubscriptionErrorException, WebSocketDisconnectedException và cleanup connection.
13. Gọi tester.stop() sau test để đóng connection.

Sau khi hoàn thành, hãy giải thích vì sao StepVerifier cần đồng bộ với server-side subscription, khác biệt giữa lỗi Publisher và lỗi transport, và cách xác minh cancellation đã thực sự tới event source.

## Ghi nhớ

WebSocketGraphQlTester kiểm thử subscription qua WebSocket connection thực. Tạo tester bằng endpoint URL và WebSocketClient, gửi operation bằng executeSubscription() rồi dùng StepVerifier để xác minh event, thứ tự và tín hiệu kết thúc. Với publisher bất đồng bộ, đồng bộ thời điểm server subscribe trước khi phát event; tránh dùng sleep để đoán thời gian. Dùng thenCancel() để hủy stream và kiểm tra publisher server nhận cancellation. Phân biệt SubscriptionErrorException do GraphQL publisher error với WebSocketDisconnectedException do transport mất kết nối. Dùng WebSocketGraphQlClientInterceptor để gửi connection_init payload khi kiểm thử authentication. Tái sử dụng connection trong test, đặt timeout hữu hạn và luôn gọi stop() để cleanup.

## Tài liệu tham khảo

- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [WebSocketGraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/WebSocketGraphQlTester.html)
- [GraphQlClient.RequestSpec – executeSubscription](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [Spring for GraphQL – Client WebSocket](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL – Request Execution, Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
