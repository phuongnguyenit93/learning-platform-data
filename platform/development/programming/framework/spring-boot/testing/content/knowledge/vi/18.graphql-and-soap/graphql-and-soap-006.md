# Kiểm thử subscription và dữ liệu phát ra

## 1. GraphQL subscription là gì, cần chứng minh điều gì?

Trong Spring Boot sử dụng **Spring for GraphQL**, ba kiểu operation phổ biến là `query`, `mutation` và `subscription`:

- **Query:** client yêu cầu dữ liệu, server trả một kết quả logic.
- **Mutation:** client yêu cầu thay đổi trạng thái hoặc thực hiện một hành động, thường nhận một kết quả logic.
- **Subscription:** client **đăng ký nhận chuỗi kết quả** khi nguồn dữ liệu phát sự kiện. Một lần đăng ký có thể tạo nhiều response theo thời gian, hoặc hoàn tất/lỗi/hủy.

Ví dụ trong hệ thống kho: thay vì liên tục gọi `query { stock(sku: "SKU-7") }`, client đăng ký:

~~~graphql
subscription WatchStock($sku: ID!) {
  stockUpdated(sku: $sku) {
    sku
    quantity
    sequence
  }
}
~~~

với biến:

~~~json
{"sku":"SKU-7"}
~~~

Khi nguồn cập nhật, server có thể phát:

~~~json
{"data":{"stockUpdated":{"sku":"SKU-7","quantity":3,"sequence":1}}}
{"data":{"stockUpdated":{"sku":"SKU-7","quantity":5,"sequence":2}}}
~~~

Đây là **hai response GraphQL riêng biệt trong stream**, không phải một JSON document gồm hai dòng để gửi như một HTTP body thông thường.

Với chủ đề **“Kiểm thử subscription và dữ liệu phát ra”**, một bài test đáng tin cậy nên trả lời được:

1. **Đăng ký có hợp lệ không?** GraphQL document, tên root field, biến, schema, resolver và wiring đúng?
2. **Có phát sự kiện không?** Luồng có `onNext`, mỗi event chứa đúng giá trị, đúng kiểu, đúng thứ tự nếu thứ tự là hợp đồng?
3. **Điều kiện lọc đúng không?** Chỉ nhận các event cho `sku`/user/tenant được phép, không lẫn event của subscription khác?
4. **Kết thúc thế nào?** Finite stream `onComplete`; stream dài hạn cần cancellation; lỗi upstream cần chính sách lỗi riêng.
5. **Đường truyền có hoạt động không?** Test resolver không có network khác với kiểm thử GraphQL subscription qua WebSocket thực.
6. **Tài nguyên có được giải phóng không?** Khi subscriber cancel hoặc client đóng kết nối, publisher không tiếp tục giữ tài nguyên không cần thiết.

**Không đánh đồng “controller đã trả về `Flux`” với “client đã subscribe và nhận được event”.** Reactor Publisher thường lazy: không có downstream subscriber thì phần lớn luồng chưa được thực thi.

## 2. Phạm vi GraphQL trong nhóm “GraphQL và SOAP”

Tên nhóm cấp cha gồm **GraphQL và SOAP**, nhưng từ khóa `subscription` và chuỗi event trong bài này có ý nghĩa **trực tiếp ở GraphQL subscriptions**. Trong Spring for GraphQL, một field trên root type `Subscription` có thể được ánh xạ bằng `@SubscriptionMapping` và trả `Flux<T>`/Reactive Streams `Publisher<T>`.

SOAP truyền thống chủ yếu dựa vào request/response XML qua HTTP. Một hệ thống SOAP **có thể** hỗ trợ thông báo sự kiện bằng các đặc tả hoặc kiến trúc như WS-Eventing/WS-Notification, nhưng **đó không phải GraphQL subscription** và không dùng `GraphQlTester.executeSubscription()`. Đừng dùng một bài test GraphQL để tuyên bố đã kiểm chứng SOAP eventing hoặc ngược lại.

| Vấn đề | GraphQL subscription | SOAP thông thường |
| --- | --- | --- |
| Mô tả hợp đồng | GraphQL SDL, root `type Subscription` | WSDL/XSD, SOAP envelope/operation |
| Dữ liệu phát ra | Nhiều GraphQL execution results | Thường một SOAP message response cho request; eventing cần cơ chế riêng |
| Spring test phù hợp | `GraphQlTester` + `StepVerifier`, WebSocket tester | Spring-WS `MockWebServiceServer`/HTTP SOAP client test, hoặc cơ chế eventing thật |
| Kênh truyền phổ biến | WebSocket, một số chế độ SSE/RSocket | HTTP/SOAP; eventing tùy giao thức triển khai |
| Assertion cốt lõi | Từng event, thứ tự, completion/cancel/error | SOAP body/header/fault/XSD; callback event riêng nếu có |

Phần còn lại tập trung đúng đề: **GraphQL subscription trên Spring Boot**, dữ liệu event được phát, GraphQL schema và transport.

## 3. Một subscription đi qua những tầng nào?

~~~text
GraphQL client
    |
    | subscription document + variables
    v
GraphQL operation / transport
    |                       \
    | server-side test       \ WebSocket integration
    v                        v
GraphQlService            WebSocket server/handler
    \                        /
     \                      /
      v                    v
        GraphQL Java execution
                 |
                 v
      @SubscriptionMapping method
                 |
                 v
          StockFeed.stream(sku)
                 |
                 v
        Flux<StockUpdate> events
                 |
             onNext / onComplete / onError / cancel
                 |
                 v
      GraphQL result per emitted item
                 |
                 v
          tester.toFlux(...)
                 |
                 v
          StepVerifier assertions
~~~

Phân biệt hai loại test chính:

- **Server-side GraphQL slice test:** `@GraphQlTest` + `GraphQlTester` được Spring Boot cấu hình để thực thi GraphQL mà **không mở HTTP/WebSocket server**. Nó chứng minh schema, mapping, decoding và hành vi resolver theo các collaborator được cung cấp.
- **WebSocket integration test:** `@SpringBootTest(RANDOM_PORT)` với WebFlux và WebSocket endpoint thực, tạo `WebSocketGraphQlTester` kết nối tới `ws://127.0.0.1:<port>/graphql`. Nó chứng minh cả WebSocket handshake/protocol path, server wiring và event tới client.

Có thể còn **unit test Publisher thuần** bằng JUnit + Reactor Test không nạp Spring, để kiểm tra operator, error/backpressure/cancel nhanh hơn.

### Không lẫn một HTTP query với subscription

`GraphQlTester.document(...).execute()` phù hợp cho `query` hoặc `mutation`, tạo response một lần. Với `subscription`, sử dụng:

~~~java
Flux<StockUpdate> events = tester.document(document)
        .variable("sku", "SKU-7")
        .executeSubscription()
        .toFlux("stockUpdated", StockUpdate.class);
~~~

`toFlux("stockUpdated", StockUpdate.class)` giải mã **mỗi response** từ trường `data.stockUpdated` thành `StockUpdate`; nó không tự trigger assertion về số event nếu không có subscriber. Hãy subscribe qua `StepVerifier` và quy định điều kiện kết thúc hoặc hủy.

## 4. Schema GraphQL và các điều kiện của event

Schema được Spring Boot tự phát hiện khi đặt tệp `.graphqls`/`.gqls` dưới `src/main/resources/graphql/**`. Trong ví dụ, ta dùng một `Query` nhỏ để có root query hợp lệ và một root subscription.

**Tệp `src/main/resources/graphql/schema.graphqls`:**

~~~graphql
type Query {
  ping: String!
}

type Subscription {
  stockUpdated(sku: ID!): StockUpdate!
}

type StockUpdate {
  sku: ID!
  quantity: Int!
  sequence: Int!
}
~~~

Ý nghĩa:

- `stockUpdated` là tên GraphQL field phải trùng mapping trong controller.
- `sku: ID!`: client bắt buộc truyền tham số khác null (thông thường là chuỗi định danh).
- `StockUpdate!`: **mỗi payload phát ra** phải phù hợp một object không null theo schema. Nó **không có nghĩa** subscription chắc chắn sẽ phát ít nhất một item.
- `quantity` và `sequence` là `Int!`: mỗi event phải có số nguyên hợp lệ, không null. GraphQL `Int` là loại số nguyên 32-bit có dấu; giá trị Java cần nằm trong miền biểu diễn được.
- `sequence` dùng để kiểm tra **thứ tự logic của event** do API quy định. Đây không phải ID được GraphQL tự sinh.

Một subscription có thể phát **0, 1 hoặc nhiều event**. Nếu publisher complete ngay không có `onNext`, cả sơ đồ schema và GraphQL controller vẫn có thể hợp lệ về mặt kỹ thuật; test cần quyết định xem đó là hành vi mong muốn hay là lỗi nghiệp vụ.

### Event và response không giống nhau

Mỗi `StockUpdate` từ `Flux` là **dữ liệu resolver**. GraphQL thực thi selection set để tạo response `{"data": {"stockUpdated": {...}}}` cho từng item. Client có thể chỉ yêu cầu `sku` và `quantity`; không nên kỳ vọng GraphQL response chứa mọi field của Java record nếu document không chọn chúng.

Nếu event vi phạm non-null/type contract hoặc resolver báo lỗi, response có thể chứa trường `errors`, hoặc stream được xử lý theo chính sách GraphQL transport. Vì vậy **lỗi GraphQL** và **lỗi Publisher thô** không nhất thiết có cùng Java exception class/stack trace khi quan sát ở client.

## 5. Cấu hình Gradle, WebFlux và WebSocket

Ví dụ chính dùng **Java 17, Spring Boot 3.5.16, Spring for GraphQL phiên bản được Boot quản lý, Reactor, JUnit Jupiter, Mockito và WebSocketGraphQlTester**. Không ép một phiên bản GraphQL độc lập không tương thích BOM.

**Tệp `build.gradle` (Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Tệp này cần Gradle Wrapper và project settings phù hợp. Spring Boot quản lý phiên bản Spring GraphQL/Reactor nên không chỉ định version riêng cho `spring-graphql-test` và `reactor-test`.

**Tệp `src/main/resources/application.properties`:**

~~~properties
spring.graphql.websocket.path=/graphql
~~~

Chỉ dùng `spring-boot-starter-graphql` chưa đủ để expose GraphQL ra mạng; WebFlux starter bổ sung HTTP/WebSocket runtime. Với **Spring Boot 3.5**, WebSocket GraphQL endpoint **tắt mặc định** cho tới khi cấu hình `spring.graphql.websocket.path`. Trong ứng dụng WebFlux, không cần `spring-boot-starter-websocket` riêng như cách thiết lập Servlet WebSocket; demo dùng WebFlux.

Đường HTTP GraphQL mặc định là POST `/graphql`; Spring Boot 3.5 còn hỗ trợ Server-Sent Events `text/event-stream` cho subscription ở HTTP endpoint. Tuy nhiên API `GraphQlTester.executeSubscription()` trong Spring for GraphQL 1.4 được tài liệu mô tả cho **server-side tester hoặc WebSocketGraphQlTester**. Không tự coi `HttpGraphQlTester` dùng như WebSocket tester để kiểm tra subscription qua HTTP; nếu muốn test SSE, hãy dùng công cụ đọc SSE phù hợp và kiểm tra transport riêng.

### Sơ đồ tệp

~~~text
src/main/java/com/example/graphqlsub/
  GraphQlSubscriptionApplication.java
  StockUpdate.java
  StockFeed.java
  DeterministicStockFeed.java
  StockSubscriptionController.java

src/main/resources/
  application.properties
  graphql/schema.graphqls

src/test/java/com/example/graphqlsub/
  StockGraphQlSliceTest.java
  StockSubscriptionWebSocketTest.java
  StockSubscriptionUnitTest.java

build.gradle
~~~

Lớp/tệp ở phần 6–9 dùng đúng package `com.example.graphqlsub`. Với mỗi `public` class hoặc interface, tên tệp trùng tên khai báo.

## 6. Ứng dụng mẫu đầy đủ: producer và @SubscriptionMapping

### 6.1. Entry point

**`src/main/java/com/example/graphqlsub/GraphQlSubscriptionApplication.java`:**

~~~java
package com.example.graphqlsub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlSubscriptionApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlSubscriptionApplication.class, args);
    }
}
~~~

### 6.2. Dữ liệu event

**`src/main/java/com/example/graphqlsub/StockUpdate.java`:**

~~~java
package com.example.graphqlsub;

public record StockUpdate(
        String sku,
        int quantity,
        int sequence
) {
}
~~~

Java record phù hợp làm DTO bất biến. Trong ví dụ, thứ tự sự kiện được thể hiện bởi `sequence = 1, 2`; không lấy thời gian thực hoặc random để tránh test không ổn định.

### 6.3. Interface nguồn event

**`src/main/java/com/example/graphqlsub/StockFeed.java`:**

~~~java
package com.example.graphqlsub;

import reactor.core.publisher.Flux;

public interface StockFeed {
    Flux<StockUpdate> stream(String sku);
}
~~~

Source trong hệ thống thật có thể đọc từ message broker, database change stream, `Sinks.Many` hoặc một upstream reactive client. Test GraphQL chỉ cần một `Flux<StockUpdate>` có thể kiểm soát.

### 6.4. Nguồn event deterministic cho WebSocket integration

**`src/main/java/com/example/graphqlsub/DeterministicStockFeed.java`:**

~~~java
package com.example.graphqlsub;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class DeterministicStockFeed implements StockFeed {

    @Override
    public Flux<StockUpdate> stream(String sku) {
        if ("UNKNOWN".equals(sku)) {
            return Flux.empty();
        }

        return Flux.just(
                new StockUpdate(sku, 3, 1),
                new StockUpdate(sku, 5, 2)
        );
    }
}
~~~

Nguồn này **không phải** một event bus production. Nó phát ngay hai item và complete, để test WebSocket không phải chờ message broker hay timer. `Flux.just(...)` là Publisher lạnh theo cách dùng ở đây: subscriber nhận event khi subscribe. Cùng một `sku` tạo cùng dữ liệu, nên test có expected output cố định.

Trong project thật, producer là singleton có thể được nhiều client subscribe. Một test cần thêm trường hợp **nhiều subscriber** và tenant/security khi nguồn event không còn deterministic.

### 6.5. GraphQL controller thật

**`src/main/java/com/example/graphqlsub/StockSubscriptionController.java`:**

~~~java
package com.example.graphqlsub;

import java.util.Objects;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class StockSubscriptionController {
    private final StockFeed feed;

    public StockSubscriptionController(StockFeed feed) {
        this.feed = Objects.requireNonNull(feed, "feed");
    }

    @QueryMapping
    public String ping() {
        return "pong";
    }

    @SubscriptionMapping
    public Flux<StockUpdate> stockUpdated(@Argument("sku") String sku) {
        return feed.stream(sku);
    }
}
~~~

`@SubscriptionMapping` mặc định map method `stockUpdated` tới field `Subscription.stockUpdated` trong schema. `@Argument("sku")` liên kết GraphQL argument với tham số Java theo tên tường minh, không phụ thuộc vào tên tham số biên dịch.

Không tự gọi `.subscribe()` hoặc `.block()` trong controller: GraphQL infrastructure subscribe và xuất event theo transport. Nếu resolver trả một `Flux` và không có client đăng ký, điều đó **không có nghĩa một HTTP response stream đã được tạo**.

**Không dùng `@SchemaMapping(typeName = "Query")` cho field subscription** rồi mong nó được đăng ký như Subscription: root type và operation phải đúng. `@SubscriptionMapping` là meta-annotation tương ứng với `@SchemaMapping(typeName = "Subscription")`.

## 7. Kiểm thử không có network: @GraphQlTest + GraphQlTester

`@GraphQlTest(StockSubscriptionController.class)` nạp Spring GraphQL infrastructure và controller đã chọn nhưng không khởi động HTTP/WebSocket server. Bean `DeterministicStockFeed` có `@Service` thường **không được slice scan**, vì vậy dùng `@MockitoBean` để cung cấp mock dependency trong Spring context.

Đây là cách phù hợp để kiểm tra **schema + resolver + event decoding + thứ tự** mà không bị phụ thuộc network.

**Tệp `src/test/java/com/example/graphqlsub/StockGraphQlSliceTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@GraphQlTest(StockSubscriptionController.class)
class StockGraphQlSliceTest {

    private static final String SUBSCRIPTION = """
            subscription WatchStock($sku: ID!) {
              stockUpdated(sku: $sku) {
                sku
                quantity
                sequence
              }
            }
            """;

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    StockFeed feed;

    private Flux<StockUpdate> updates(String sku) {
        return tester.document(SUBSCRIPTION)
                .variable("sku", sku)
                .executeSubscription()
                .toFlux("stockUpdated", StockUpdate.class);
    }

    @Test
    void emitsTwoEventsWithExactValuesAndOrder() {
        StockUpdate first = new StockUpdate("SKU-7", 3, 1);
        StockUpdate second = new StockUpdate("SKU-7", 5, 2);

        when(feed.stream("SKU-7"))
                .thenReturn(Flux.just(first, second));

        StepVerifier.create(updates("SKU-7"))
                .expectNext(first, second)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-7");
    }

    @Test
    void bindsSkuVariableAndReturnsOnlyRequestedSkuEvents() {
        StockUpdate one = new StockUpdate("SKU-9", 8, 1);
        when(feed.stream("SKU-9")).thenReturn(Flux.just(one));

        StepVerifier.create(updates("SKU-9"))
                .expectNext(one)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-9");
    }

    @Test
    void emptyFeedCompletesWithoutAnyPayload() {
        when(feed.stream("UNKNOWN")).thenReturn(Flux.empty());

        StepVerifier.create(updates("UNKNOWN"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("UNKNOWN");
    }

    @Test
    void canInspectIndividualResponseFields() {
        StockUpdate event = new StockUpdate("SKU-7", 3, 1);
        when(feed.stream("SKU-7")).thenReturn(Flux.just(event));

        Flux<GraphQlTester.Response> responses =
                tester.document(SUBSCRIPTION)
                        .variable("sku", "SKU-7")
                        .executeSubscription()
                        .toFlux();

        StepVerifier.create(responses)
                .assertNext(response -> {
                    response.path("stockUpdated.sku")
                            .entity(String.class)
                            .isEqualTo("SKU-7");
                    response.path("stockUpdated.quantity")
                            .entity(Integer.class)
                            .isEqualTo(3);
                    response.path("stockUpdated.sequence")
                            .entity(Integer.class)
                            .isEqualTo(1);
                })
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        verify(feed).stream("SKU-7");
    }

    @Test
    void cancellingAfterTwoEventsStopsLongLivedSource() {
        StockUpdate first = new StockUpdate("SKU-7", 3, 1);
        StockUpdate second = new StockUpdate("SKU-7", 5, 2);

        AtomicBoolean cancelled = new AtomicBoolean(false);
        Flux<StockUpdate> source = Flux.concat(
                Flux.just(first, second),
                Flux.<StockUpdate>never()
        ).doOnCancel(() -> cancelled.set(true));

        when(feed.stream("SKU-7")).thenReturn(source);

        StepVerifier.create(updates("SKU-7").take(2))
                .expectNext(first, second)
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertTrue(cancelled.get(), "upstream should receive cancellation");
        verify(feed).stream("SKU-7");
    }
}
~~~

### Vì sao từng test có giá trị?

| Test | Xác minh chính | Lỗi có thể phát hiện |
| --- | --- | --- |
| Hai sự kiện có thứ tự | Nội dung record, `sequence=1,2`, completion | Sai giá trị, thiếu event, đảo thứ tự, stream không hoàn tất |
| Variable `sku` | Argument mapping và dependency nhận SKU đúng | Hard-code SKU hoặc bind sai GraphQL variable |
| Feed rỗng | Không có `onNext` và có `onComplete` | Tự sinh dữ liệu không tồn tại, treo subscription |
| Kiểm tra response field | GraphQL serialization/selection set theo từng event | Sai field name, sai kiểu số/string, mapping/schema |
| Hủy sau 2 event | Downstream `take(2)` báo cancel upstream | Stream giữ tài nguyên ngay cả khi client ngừng đọc |

**Không chỉ dùng Mockito `verify(feed).stream(...)`:** method Java có thể được gọi khi GraphQL tạo Publisher, nhưng chưa chắc **event đã tới downstream**. `StepVerifier` thực hiện subscription và assert từng item.

**Không chỉ dùng `expectNextCount(2)`:** nó kiểm tra số lượng nhưng không phân biệt `quantity=3` với `quantity=-99` hoặc đảo sequence. Khi dữ liệu có ý nghĩa, assert chính xác record/field.

### Những giới hạn của slice test

Ca `cancellingAfterTwoEventsStopsLongLivedSource` chứng minh cancellation trong **server-side GraphQL execution path**. Nó **không chứng minh** WebSocket client thực gửi frame complete/cancel đúng, hoặc broker ngoài bị hủy; các lớp đó cần integration test và công cụ quan sát riêng.

Lớp slice không cần `@SpringBootTest` và không thực hiện WebSocket handshake. Việc `GraphQlTester` chạy thành công ở đây không bảo đảm `spring.graphql.websocket.path` đã bật trong môi trường deploy.

## 8. Kiểm thử transport thực: WebSocketGraphQlTester và RANDOM_PORT

Khi cần kiểm tra việc **subscription được gửi từ client, server trả event qua WebSocket thật**, dùng một integration test với server đang lắng nghe cổng ngẫu nhiên.

**Tệp `src/test/java/com/example/graphqlsub/StockSubscriptionWebSocketTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockSubscriptionWebSocketTest {

    private static final String SUBSCRIPTION = """
            subscription WatchStock($sku: ID!) {
              stockUpdated(sku: $sku) {
                sku quantity sequence
              }
            }
            """;

    @LocalServerPort
    int port;

    @Test
    void streamsTwoEventsOverActualWebSocket() {
        String url = "ws://127.0.0.1:" + port + "/graphql";

        WebSocketGraphQlTester tester = WebSocketGraphQlTester.builder(
                url,
                new ReactorNettyWebSocketClient()
        ).build();

        try {
            Flux<StockUpdate> events = tester.document(SUBSCRIPTION)
                    .variable("sku", "SKU-7")
                    .executeSubscription()
                    .toFlux("stockUpdated", StockUpdate.class);

            StepVerifier.create(events)
                    .expectNext(
                            new StockUpdate("SKU-7", 3, 1),
                            new StockUpdate("SKU-7", 5, 2)
                    )
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        } finally {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }

    @Test
    void unknownSkuCompletesWithoutAnEventOverWebSocket() {
        String url = "ws://127.0.0.1:" + port + "/graphql";
        WebSocketGraphQlTester tester = WebSocketGraphQlTester.builder(
                url,
                new ReactorNettyWebSocketClient()
        ).build();

        try {
            Flux<StockUpdate> events = tester.document(SUBSCRIPTION)
                    .variable("sku", "UNKNOWN")
                    .executeSubscription()
                    .toFlux("stockUpdated", StockUpdate.class);

            StepVerifier.create(events)
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        } finally {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }
}
~~~

### Những khác biệt quan trọng với @GraphQlTest

- `RANDOM_PORT` khởi động một **WebFlux HTTP/WebSocket server thật**. `@LocalServerPort` cung cấp cổng động, test không hard-code `8080`.
- `WebSocketGraphQlTester` kết nối tới `ws://.../graphql` bằng `ReactorNettyWebSocketClient`; server có property `spring.graphql.websocket.path=/graphql`.
- Đây là test **thực qua socket**: nếu endpoint chưa bật, handshake/protocol sai hoặc handler không đưa event ra transport, bài test sẽ thất bại.
- Integration test dùng **`DeterministicStockFeed` thật** trong Spring context, không dùng Mockito mock. Kết quả vẫn predictable vì feed không cần broker.
- `stop()` trả **`Mono<Void>`**: gọi `tester.stop();` mà không subscribe có thể không đóng kết nối. Trong test cleanup, `block(Duration.ofSeconds(5))` dùng để bảo đảm dọn WebSocket session; **không dùng `block()` trong reactive handler production**.
- `WebSocketGraphQlTester` có thể dùng chung kết nối để multiplex nhiều operations. Ví dụ cố ý tạo một tester riêng cho mỗi ca để test cô lập; một suite lớn có thể quản lý instance/cleanup cấp lớp nếu cần tối ưu.

**Đừng khẳng định WebSocket transport đã được test chỉ vì `@GraphQlTest` trả dữ liệu đúng.** Ngược lại, khi integration test WebSocket FAIL, hãy chạy slice test trước: slice PASS nhưng WebSocket FAIL thường gợi ý lỗi endpoint/property/protocol/security/handshake hơn là serialization/resolver.

## 9. Đơn vị Publisher thuần: kiểm tra lỗi upstream mà không suy đoán GraphQL error shape

Ở tầng Reactor, nguồn có thể báo `onError`. Nhưng GraphQL Java và transport có cơ chế tạo **GraphQL errors**; exception mà client nhận được không nhất thiết giữ nguyên tên/kiểu của exception upstream.

Bởi vậy, nếu điều cần kiểm tra là **chính sách lỗi của Publisher**, viết test trực tiếp lên một `Flux` trong unit test. Đừng so sánh mặc định `IllegalStateException` ở client WebSocket mà chưa thiết kế error contract ở GraphQL API.

**Tệp `src/test/java/com/example/graphqlsub/StockSubscriptionUnitTest.java`:**

~~~java
package com.example.graphqlsub;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StockSubscriptionUnitTest {

    @Test
    void controllerReturnsPublisherFromFeed() {
        StockFeed fake = sku -> Flux.just(
                new StockUpdate(sku, 3, 1)
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(fake);

        StepVerifier.create(controller.stockUpdated("SKU-7"))
                .expectNext(new StockUpdate("SKU-7", 3, 1))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void upstreamFailureIsVisibleToRawPublisherSubscriber() {
        StockFeed failing = sku -> Flux.error(
                new IllegalStateException("feed unavailable")
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(failing);

        StepVerifier.create(controller.stockUpdated("SKU-7"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "feed unavailable".equals(
                                        error.getMessage()
                                ))
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void independentSubscribersReceiveTheSameColdDemoEvents() {
        StockFeed cold = sku -> Flux.just(
                new StockUpdate(sku, 3, 1),
                new StockUpdate(sku, 5, 2)
        );

        StockSubscriptionController controller =
                new StockSubscriptionController(cold);

        Flux<StockUpdate> events = controller.stockUpdated("SKU-7");
        assertEquals(2L, events.count().block(Duration.ofSeconds(5)));

        StepVerifier.create(events)
                .expectNext(
                        new StockUpdate("SKU-7", 3, 1),
                        new StockUpdate("SKU-7", 5, 2)
                )
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

Ca cuối cố ý kiểm tra behavior của **cold demo publisher**: hai subscription độc lập nhận cùng dãy event. `events.count().block(...)` được gọi **chỉ trong unit test** để đếm một lần; không nên dùng `block()` trong WebFlux controller production. Nếu nguồn là hot `Sinks.Many`, hai subscriber có thể nhận các khoảng event khác nhau và không thể lấy cold test làm hợp đồng của hot stream.

## 10. Dữ liệu phát ra: kiểm tra giá trị, thứ tự, kiểu và ranh giới schema

Một subscription event không chỉ có số lượng. Với GraphQL SDL ở phần 4, hãy xác định hợp đồng:

| Thuộc tính | Assertion nên có | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| `sku` | Phải đúng `sku` đã subscribe | Rò dữ liệu khách hàng/tenant khác |
| `quantity` | Phải đúng giá trị business và nằm trong miền `Int` | Sai mapping, nhầm số lượng |
| `sequence` | Tăng theo thứ tự nếu API hứa ordering | Client apply update sai thứ tự |
| Số event | Có đúng 2 sự kiện cho finite demo | Thiếu/nhân đôi thông báo |
| Nullability | Không vi phạm non-null của SDL | GraphQL errors/null propagation |
| GraphQL selection set | Chỉ field đã yêu cầu xuất hiện trong data | Schema/resolver/serialization bị lệch |
| Completion | Finite demo complete đúng | Test treo, thiếu cleanup |
| Cancellation | Stream vô hạn dừng khi client không cần | Leak publisher/broker listener |

Trong test slice, dùng `expectNext(first, second)` khi Java record có `equals` theo component. Muốn kiểm tra **từng response GraphQL** thay vì POJO đã decode, dùng `executeSubscription().toFlux()` và `response.path("stockUpdated.quantity").entity(Integer.class).isEqualTo(...)`, như ví dụ.

### Kiểm tra điều kiện lọc của feed

Một subscription theo `sku` phải tránh phát dữ liệu của SKU khác. Nếu demo trả event theo tham số bằng `new StockUpdate(sku,...)`, test biến `sku` là đủ cho demo. Với nguồn production là event bus chung, cần kiểm tra **filter ở feed/resolver**:

~~~java
// Đoạn minh họa trong một service thực tế:
return allStockUpdates
        .filter(update -> sku.equals(update.sku()));
~~~

Đoạn này **không phải tệp Java độc lập**. Nếu nguồn `allStockUpdates` phát ba item theo thứ tự `SKU-7`, `SKU-9`, `SKU-7`, test nên chỉ nhận **hai item SKU-7** và giữ đúng thứ tự nội tại. Nếu còn tenant/user, phải filter hoặc authorize trên đúng boundary; không coi chỉ lọc SKU là đủ bảo mật.

### GraphQL errors không phải HTTP 500 cho mỗi item

Một GraphQL operation có thể nhận phản hồi chứa trường `errors` ngay cả khi HTTP status cho request đã được xử lý là 200. Với WebSocket, mỗi payload là một GraphQL execution result và lỗi có thể nằm trong message protocol thay vì một HTTP status mới. `toFlux("stockUpdated", StockUpdate.class)` sẽ dùng assertion/path mapping và có thể fail nếu response có GraphQL errors hoặc thiếu data được yêu cầu.

Khi **hợp đồng mong đợi một GraphQL error**, sử dụng `toFlux()` để kiểm tra `Response.errors()` theo API `GraphQlTester`, hoặc kiểm tra error envelope theo transport/protocol đã thiết kế. Không viết test `expectError(IllegalStateException.class)` ở WebSocket tester chỉ vì upstream thô ném `IllegalStateException`; hãy xác định mapping của error resolver rồi mới assert.

## 11. Kiểm thử completion, cancellation và long-lived subscription

Đối với hai event của demo, `expectComplete()` là điều kiện đúng. Nhưng nguồn sự kiện production thường **không bao giờ tự complete** khi người dùng đang mở subscription.

Đừng viết:

~~~java
// Không phù hợp nếu stream sống lâu và không có completion:
StepVerifier.create(liveUpdates)
        .expectNextCount(2)
        .verifyComplete();
~~~

Với stream vô hạn, `verifyComplete()` có thể chờ mãi. Nếu chỉ cần hai event đầu tiên:

~~~java
StepVerifier.create(liveUpdates.take(2))
        .expectNext(first, second)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

`take(2)` phát hai item rồi **cancel upstream** khi đủ dữ liệu; đó là hành vi mong muốn nếu bài test chỉ cần hai event. Có thể dùng `doOnCancel(...)` hoặc `PublisherProbe` ở cấp producer để chứng minh việc giải phóng subscription. Đừng mặc định cancellation của một test GraphQL slice tự chứng minh WebSocket frame và broker unsubscription ở production.

Nếu muốn kiểm tra hủy **khi chưa có event**:

~~~java
StepVerifier.create(Flux.<StockUpdate>never())
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Đoạn trên là minh họa Reactor thuần: một publisher không phát gì được test hủy chủ động, không cần chờ vô hạn.

### Timeout phải có nghĩa

- Một stream finite nên có giới hạn thời gian test, ví dụ `.expectComplete().verify(Duration.ofSeconds(5))`.
- Long-lived stream nên được `take(n)`, `thenCancel()`, hoặc xử lý cancellation theo hợp đồng.
- Đừng dùng `Thread.sleep(...)` để đợi sự kiện; trong test có producer kiểm soát, hãy dùng `StepVerifier`/publisher deterministic.
- Nếu test chạy với message broker và network thật, timeout cần phản ánh CI/environment, không giải quyết race chỉ bằng tăng timeout.
- Không áp dụng `timeout(Duration...)` lên production stream chỉ để làm test PASS nếu điều đó thay đổi semantics ứng dụng.

## 12. Virtual time và backpressure: khi nào cần?

Nếu producer dùng `Flux.interval(...)` để phát event theo thời gian, test chờ đồng hồ thật sẽ chậm và flaky. Project Reactor Test có `StepVerifier.withVirtualTime(...)`, hữu ích cho **operator thời gian** khi source được tạo trong supplier sau khi virtual scheduler đã được thiết lập.

Ví dụ Reactor thuần, không phụ thuộc Spring context:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2)
)
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(0L)
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(1L)
        .verifyComplete();
~~~

Đoạn này là body code minh họa, cần import `Duration`, `Flux`, `StepVerifier`. Nó kiểm tra giá trị `0L` sau tick đầu và `1L` sau tick thứ hai mà không cần sleep thực. Nếu source/timer đã được tạo **trước** supplier, virtual time có thể không điều khiển được scheduler như mong muốn.

### Backpressure không giống một event WebSocket = một request(n)

Reactive Streams có `request(n)`, `onNext` và cancellation, nhưng trong GraphQL WebSocket transport có thêm protocol frames, buffering và mapping mỗi GraphQL execution result. **Không suy rằng cứ mỗi frame mạng tương ứng chính xác một lần `request(1)`**.

- Ở producer/service: dùng `StepVerifier.create(flux, 0).thenRequest(1)` nếu cần kiểm tra request demand có kiểm soát.
- Ở GraphQL response: assert các event và thứ tự, khi cần thêm stress test với data lớn.
- Ở transport/broker: kiểm tra giới hạn buffer, slow clients và chính sách drop/replay/durable delivery riêng.

Ví dụ demand:

~~~java
StepVerifier.create(
        Flux.just("first", "second"),
        0
)
        .thenRequest(1)
        .expectNext("first")
        .thenRequest(1)
        .expectNext("second")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

Đây cũng là **đoạn minh họa Reactor thuần**, không kiểm tra một GraphQL WebSocket connection thực. Dùng nó khi contract cần backpressure, không thêm vào mọi subscription test như một thủ tục trang trí.

## 13. Hot versus cold: lỗi thường gặp khi dùng Sinks.Many

### Cold source

`Flux.just(...)` và một `Flux.defer(...)` trả dữ liệu theo từng subscription; mỗi subscriber mới có thể nhận cùng dãy event của demo. Test với expected `event1, event2, complete` rất ổn định.

### Hot source

Nguồn thật có thể là `Sinks.Many<StockUpdate>`, Kafka, Redis pub/sub hay change stream. Event được phát ra theo thời gian, **có thể mất nếu subscriber chưa thực sự đăng ký**, và các subscriber có thể bắt đầu ở các thời điểm khác nhau.

Một đoạn producer minh họa:

~~~java
Sinks.Many<StockUpdate> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<StockUpdate> events = sink.asFlux();
~~~

Đây là code Reactor minh họa, cần `reactor.core.publisher.Sinks`; **không phải một ví dụ đã thiết lập đầy đủ subscription lifecycle**. Việc gọi `sink.tryEmitNext(event)` ngay trước khi client/StepVerifier thực sự subscribe có thể không biểu diễn tình huống sản phẩm mong muốn, và cách sink lưu/bỏ event tùy loại sink. Đừng dùng `Thread.sleep(500)` để đoán đã có subscription.

Để test event bus thật:

1. Tạo subscription/StepVerifier hoặc client và xác định **subscriber đã sẵn sàng** (latch, handshake acknowledgement, hook do producer cung cấp).
2. Chỉ sau đó phát event test vào nguồn.
3. Assert đúng event và đúng thứ tự.
4. Cancel/đóng kết nối, kiểm tra nguồn dọn registration.
5. Tránh dùng chung sink mutable giữa các lớp test chạy song song mà không có isolation.

`Sinks.many().replay().limit(n)` có semantics replay khác `multicast`; chọn theo hợp đồng khi client reconnect và có missed events. Không coi mọi GraphQL subscription là một reliable queue: GraphQL không tự bảo đảm delivery exactly-once, lưu lịch sử hay replay khi mất mạng.

## 14. Nhiều subscriber, security và dữ liệu khách hàng

Trong production, câu hỏi không chỉ là có event mà là **ai được nhận event gì**.

### Phân vùng theo SKU/tenant/user

Nếu một client đăng ký SKU A nhưng nhận event SKU B, đó là lỗi lọc. Nếu một user thuộc tenant X nhận event tenant Y, đó có thể là lỗi bảo mật nghiêm trọng. Hãy kiểm tra bằng **hai subscription đồng thời**:

| Subscriber | Biến | Event cần nhận | Event không được nhận |
| --- | --- | --- | --- |
| Client A | `sku="A"`, tenant X | Cập nhật A trong X | B hoặc tenant Y |
| Client B | `sku="B"`, tenant X | Cập nhật B trong X | A hoặc tenant Y |
| Client C | Tenant Y | Chỉ event thuộc Y | Event tenant X |

Đừng dùng duy nhất `@Argument String sku` từ client để quyết định authorization. Trong Spring GraphQL thật, có thể sử dụng authentication principal, GraphQL context, `WebGraphQlInterceptor` hoặc service authorization. Test phải chứng minh **server không phát dữ liệu trái phép**, không chỉ frontend giấu sự kiện.

### WebSocket auth khác query HTTP ngắn hạn

- WebSocket có **connection handshake**; credential có thể được truyền qua headers hoặc connection-init payload theo protocol/client.
- Kết nối dài hạn có thể tồn tại khi token hết hạn hoặc quyền thay đổi. Chính sách re-authentication/reconnect cần được thiết kế và test.
- **Không** giả định mọi `@PreAuthorize` hoặc HTTP filter tự được áp dụng đúng tới từng event trong stream. Kiểm tra điều kiện thực của ứng dụng, kể cả lúc subscription start và lúc event phát.
- Khi client cancel/disconnect, xác nhận các listener/broker subscriptions được dispose.
- Nếu dùng CORS hoặc cross-origin browser WebSocket, hãy kiểm tra origin policy, cookies và session theo deployment thực tế.

### Client reconnect và dữ liệu mất

Test reconnect phải trả lời: event cũ có được replay không, có cursor/sequence number không, có duplicate không, và client xử lý idempotent ra sao. Không tự suy ra GraphQL transport sẽ bảo đảm exactly-once. Với hệ thống cần bảo đảm bền vững, bổ sung broker integration test và chính sách offset/replay cụ thể.

## 15. Khi lỗi xảy ra: raw Publisher error, GraphQL errors và transport failure

Ba lớp lỗi thường bị trộn lẫn:

| Nguồn lỗi | Ví dụ | Hướng kiểm thử |
| --- | --- | --- |
| **Publisher thô** | `Flux.error(new IllegalStateException(...))` | Unit test `StepVerifier.expectErrorMatches` trên Flux |
| **GraphQL execution/schema** | Field/type non-null sai, resolver exception, document/variable không hợp lệ | Test `GraphQlTester` response errors/path và error resolver theo hợp đồng |
| **WebSocket/transport** | Endpoint tắt, handshake thất bại, protocol mismatch, client mất kết nối | `WebSocketGraphQlTester` integration, xác nhận failure/reconnect/cleanup |

`@SubscriptionMapping` trả `Flux.error(...)` không đồng nghĩa WebSocket sẽ truyền Java class `IllegalStateException` nguyên vẹn. GraphQL Java/Spring for GraphQL có thể chuyển thành GraphQL error payload; nhiều implementation còn ẩn internal message để tránh rò thông tin. Nếu muốn test một error code ổn định, cần thiết kế `DataFetcherExceptionResolver`/GraphQL error extensions phù hợp trước.

**Không kiểm tra HTTP status 200 cho từng subscription event qua WebSocket.** Sau handshake (HTTP upgrade), payload được gửi bằng WebSocket messages; GraphQL error/success cần quan sát ở tầng GraphQL protocol, không phải HTTP status cho từng event.

Khi subscription test bị treo:

1. Kiểm tra endpoint `spring.graphql.websocket.path` và đúng schema.
2. Xác nhận document bắt đầu bằng operation `subscription` và root field đúng.
3. Xem upstream có `onNext` hoặc `onComplete` không; `Flux.never()` không tự complete.
4. Đảm bảo test đã subscribe bằng `StepVerifier.verify(...)`.
5. Với hot source, bảo đảm event chỉ phát sau khi subscription được đăng ký.
6. Kiểm tra security/connection-init, broker readiness và cleanup của WebSocket tester.
7. Nếu kết quả giải mã rỗng hoặc lỗi, kiểm tra GraphQL response `data`/`errors` và selection set.

## 16. Chạy test và hiểu đúng kết quả

Từ thư mục dự án có Gradle Wrapper, Java 17+:

~~~bash
./gradlew test --tests "com.example.graphqlsub.StockSubscriptionUnitTest"
./gradlew test --tests "com.example.graphqlsub.StockGraphQlSliceTest"
./gradlew test --tests "com.example.graphqlsub.StockSubscriptionWebSocketTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.graphqlsub.StockSubscriptionUnitTest"
.\gradlew.bat test --tests "com.example.graphqlsub.StockGraphQlSliceTest"
.\gradlew.bat test --tests "com.example.graphqlsub.StockSubscriptionWebSocketTest"
~~~

Theo code ở trên có **3 unit tests + 5 GraphQL slice tests + 2 WebSocket integration tests = 10 test methods**. Với dependencies, WebSocket endpoint và schema đúng, expected là các assertion PASS. **Đây là kết quả kỳ vọng từ phân tích code, không phải log JUnit đã chạy trong lúc biên soạn.** Không có `System.out.println` trong test, nên không có stdout cố định do mã ứng dụng tự in; thông báo Gradle/Spring thay đổi theo cấu hình.

Nếu môi trường CI không cho mở socket hoặc có policy hạn chế loopback, unit/slice tests vẫn có thể chạy nhưng integration test WebSocket có thể gặp lỗi hạ tầng. Không “sửa” bằng cách bỏ test transport rồi tuyên bố WebSocket đã được kiểm tra. Hãy cấu hình môi trường test phù hợp.

### Một chuỗi phát sự kiện đáng kiểm tra

~~~text
GraphQL document accepted
  -> resolver selected with sku="SKU-7"
  -> feed returns Publisher
  -> downstream subscribes
  -> event #1: SKU-7, 3, sequence 1
  -> event #2: SKU-7, 5, sequence 2
  -> stream completes (demo only)
  -> client test completes successfully
~~~

Ở source dài hạn, thay dòng “stream completes” bằng “client cancel và publisher giải phóng tài nguyên” theo hợp đồng. Không đòi completion từ một subscription production vốn chủ ý chạy liên tục.

## 17. Sai lầm phổ biến và cách sửa

1. **Dùng `execute()` thay vì `executeSubscription()`.** Không kiểm tra đúng response stream. **Sửa:** lấy `toFlux(...)` rồi `StepVerifier`.
2. **Chỉ gọi method trả `Flux` rồi cho rằng đã phát event.** Chưa có subscription. **Sửa:** subscribe và verify tín hiệu.
3. **Dùng `expectNextCount(2)` nhưng không kiểm giá trị.** Lọt event sai SKU, quantity hoặc sequence. **Sửa:** `expectNext(expected...)`/assert fields.
4. **Dùng `verifyComplete()` cho stream vô hạn.** Test treo. **Sửa:** `take(n)` hoặc `thenCancel()`, có timeout.
5. **Chỉ test controller unit rồi nói WebSocket hoạt động.** Không có handshake/protocol. **Sửa:** thêm integration `WebSocketGraphQlTester`.
6. **Chỉ test WebSocket happy path rồi không kiểm authorization/multi-tenant.** Có thể rò dữ liệu. **Sửa:** thêm per-user/per-SKU subscriptions và negative cases.
7. **Quên `spring.graphql.websocket.path`.** WebSocket endpoint không được bật mặc định. **Sửa:** cấu hình endpoint và test property tương ứng.
8. **Trộn `spring-boot-starter-web` và WebFlux mà không chú ý loại web app.** Spring Boot có thể chọn MVC khi cả hai trên classpath. **Sửa:** chỉ chọn stack phù hợp; với Servlet WebSocket cần starter riêng.
9. **Không thêm `spring-graphql-test` hoặc `reactor-test`.** Test classes thiếu `GraphQlTester`/`StepVerifier`. **Sửa:** dependency test đúng major version.
10. **Dùng `@Mock` thay Spring bean mock trong `@GraphQlTest`.** Resolver thiếu collaborator. **Sửa:** `@MockitoBean` của Spring Framework 6.2+.
11. **Giả định `@GraphQlTest` scan mọi service/configuration.** Slice được giới hạn. **Sửa:** mock/import bean phù hợp.
12. **Phát vào hot sink trước khi subscribe.** Test thiếu event ngẫu nhiên. **Sửa:** đồng bộ readiness trước emit.
13. **So sánh Java exception của producer với error WebSocket.** GraphQL có lớp mapping errors. **Sửa:** kiểm tra đúng error contract ở từng tầng.
14. **Gọi `block()` hoặc `subscribe()` trong `@SubscriptionMapping`.** Phá reactive composition, có thể nghẽn event loop. **Sửa:** trả Publisher trực tiếp.
15. **Không đóng WebSocketGraphQlTester.** Session/thread/resource có thể tồn tại sau test. **Sửa:** gọi `stop()` và subscribe Mono cleanup.
16. **Kết luận hot stream có replay vì cold test phát lại event.** Sai semantics nguồn. **Sửa:** test reconnect/late subscriber theo loại sink/broker thực tế.
17. **Giả định GraphQL subscription đồng nghĩa SOAP eventing.** Hai giao thức khác. **Sửa:** kiểm thử đúng operation/schema/transport của từng hệ.
18. **Không test cancellation.** Long-lived source có nguy cơ giữ broker listener sau khi client rời đi. **Sửa:** dùng `doOnCancel`/probe hoặc integration observation.
19. **Assert event có thứ tự tuyệt đối dù backend fan-out song song không bảo đảm thứ tự.** Test flaky hoặc đặt contract sai. **Sửa:** định nghĩa ordering bằng sequence/cursor khi sản phẩm cần.
20. **Không phân biệt GraphQL WebSocket với HTTP SSE.** Tester/transport có semantics khác nhau. **Sửa:** chọn transport tester phù hợp và ghi rõ phạm vi được chứng minh.

## 18. Checklist trước khi hoàn thành bài kiểm thử subscription

- [ ] Schema SDL có root `type Subscription` và field khớp `@SubscriptionMapping`?
- [ ] GraphQL operation gửi đúng `subscription`, đúng selection set và variables?
- [ ] `@GraphQlTest` nạp resolver thật, collaborator ngoài slice được mock/import có chủ đích?
- [ ] Test đã gọi `executeSubscription().toFlux(...)` và dùng `StepVerifier` thực sự subscribe?
- [ ] Assert từng event: SKU/ID, số lượng, sequence và số lượng item cần bảo vệ?
- [ ] Có ca không có event, ca có nhiều event và ca sai/thay đổi argument cần thiết?
- [ ] Với stream finite, test chờ completion có timeout?
- [ ] Với stream dài hạn, test cancel và quan sát cleanup, không chờ complete mãi?
- [ ] Có hiểu lỗi raw Publisher khác GraphQL execution errors và transport errors?
- [ ] Integration test đã bật WebSocket endpoint, dùng cổng ngẫu nhiên và client tester thật?
- [ ] `WebSocketGraphQlTester.stop()` được subscribe/chờ hoàn tất khi dọn?
- [ ] Không mặc định hot stream replay, không phát event trước readiness nếu cần chứng minh live delivery?
- [ ] Không suy ra mỗi WebSocket event tương ứng một HTTP status hoặc một request(n) cụ thể?
- [ ] Đã kiểm tra tenant/user isolation và auth nếu subscription chứa dữ liệu nhạy cảm?
- [ ] Nguồn event dùng test data riêng, không kết nối broker production và không phụ thuộc thứ tự test?
- [ ] Đã phân biệt GraphQL subscription với SOAP XML/request-response hoặc SOAP eventing tùy biến?

**Ghi nhớ:** Kiểm thử GraphQL subscription không dừng ở “resolver trả `Flux`”. Hãy **subscribe stream, xác nhận từng event, kiểm soát completion/cancellation và xác định rõ có kiểm tra WebSocket transport thật hay chỉ server-side GraphQL execution**. Dùng `@GraphQlTest` cho contract nhanh và đặc hiệu; dùng `WebSocketGraphQlTester` + `RANDOM_PORT` khi cần chứng minh kết nối và truyền event qua socket.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.5/reference/web/spring-graphql.html)
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL — Testing and Subscriptions](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL 1.4 — GraphQlTester.Subscription API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/test/tester/GraphQlTester.Subscription.html)
- [Spring for GraphQL 1.4 — WebSocketGraphQlTester API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/test/tester/WebSocketGraphQlTester.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [GraphQL Specification — Subscription Operations](https://spec.graphql.org/October2021/#sec-Subscription)