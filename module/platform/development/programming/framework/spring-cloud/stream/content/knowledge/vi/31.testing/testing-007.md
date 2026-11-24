# Kiểm thử ghép hàm, định tuyến và StreamBridge

Trong ứng dụng Spring Cloud Stream, một luồng xử lý có thể được tạo từ nhiều function nhỏ, chọn handler dựa trên thông tin của message hoặc gửi message tới destination được xác định khi chạy. Ba khả năng này thường xuất hiện cùng nhau: function composition tạo pipeline, routing chọn nhánh xử lý, còn StreamBridge kết nối một nguồn dữ liệu bên ngoài với output binding.

Kiểm thử cần xác minh cả logic và cách framework nối các thành phần. Một function có thể chạy đúng khi gọi trực tiếp nhưng binding composition lại đặt sai tên; router có thể chọn nhầm handler do header hoặc biểu thức; StreamBridge có thể gửi tới destination không được phép hoặc không có cấu hình producer mong đợi.

Spring Cloud Stream cung cấp Spring Integration Test Binder để kiểm thử trong JVM mà không cần Kafka, RabbitMQ hoặc Pulsar. Test Binder cho phép gửi message vào input binding và nhận message ở output binding. Sau đó, integration test với broker thật xác minh các hành vi phụ thuộc middleware như provisioning topic/queue, serialization, routing key, partition, ACL, retry và delivery semantics.

## 1. Phân biệt ba khả năng cần kiểm thử

| Thành phần | Vai trò | Điều cần xác minh |
|---|---|---|
| Function composition | Nối nhiều Supplier/Function/Consumer thành một handler. | Thứ tự thực thi, chuyển đổi kiểu, input/output binding name và payload cuối. |
| Event routing | Chọn function/consumer hoặc output destination dựa trên message/property. | Quy tắc chọn route, header, fallback, destination được phép và lỗi route không hợp lệ. |
| StreamBridge | Gửi object hoặc Message từ REST, scheduler, callback hay nguồn ngoài binder tới output binding. | Tên binding/destination, payload, headers, content type, kết quả send và hành vi tạo binding động. |

Không nên gộp tất cả vào một test lớn ngay từ đầu. Kiểm thử function riêng giúp tìm lỗi nghiệp vụ nhanh; Test Binder xác minh wiring trong ứng dụng; integration test xác minh broker và binder cụ thể.

## 2. Cài đặt Spring Integration Test Binder

Test Binder hiện tại nằm trong artifact `spring-cloud-stream-test-binder`. Khai báo dependency ở test scope để nó không trở thành binder chạy production.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

Phiên bản dependency nên được quản lý bởi Spring Cloud BOM tương ứng với Spring Boot/Spring Cloud của dự án. Không tự chọn một phiên bản test binder khác dòng với Spring Cloud Stream đang dùng.

Để bật binder trong test context, dùng `@EnableTestBinder`:

~~~java
@SpringBootTest
class OrderStreamTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

`InputDestination` đại diện cho các input binding trong test; `OutputDestination` cho phép đọc message mà ứng dụng gửi ra output binding. Khi ứng dụng có nhiều input/output, hãy truyền rõ binding name hoặc destination vào `send` và `receive` để test không phụ thuộc thứ tự binding.

## 3. Kiểm thử function trực tiếp trước khi kiểm thử binding

Business logic nên tách khỏi binder để có thể kiểm thử bằng unit test thông thường. Ví dụ:

~~~java
@Component
class OrderNormalizer {

    Order normalize(Order order) {
        return new Order(
            order.id().trim(),
            order.customerId().trim().toUpperCase(Locale.ROOT),
            order.amount()
        );
    }
}
~~~

Unit test chỉ kiểm tra kết quả của hàm:

~~~java
@Test
void normalizesCustomerId() {
    OrderNormalizer normalizer = new OrderNormalizer();

    Order result = normalizer.normalize(
        new Order(" order-1 ", " cust-7 ", 125_000)
    );

    assertThat(result.id()).isEqualTo("order-1");
    assertThat(result.customerId()).isEqualTo("CUST-7");
    assertThat(result.amount()).isEqualTo(125_000);
}
~~~

Unit test không cần tạo Spring context hoặc test binder. Sau khi logic đã đúng, có thể bọc nó trong function bean và kiểm thử binding riêng.

## 4. Ghép các function bằng spring.cloud.function.definition

Spring Cloud Function cho phép ghép các function bằng toán tử `|` hoặc dấu phẩy trong thuộc tính `spring.cloud.function.definition`. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase|addSuffix
~~~

Với hai bean `uppercase` và `addSuffix`, framework gọi `uppercase` trước rồi chuyển kết quả sang `addSuffix`. Chuỗi composition được xem như một function ở runtime.

~~~java
@Configuration
class TextFunctions {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, String> addSuffix() {
        return value -> value + "!";
    }
}
~~~

Nếu input là `hello`, output composition là `HELLO!`.

### 4.1. Tên binding của composition

Tên binding mặc định của composition được tạo từ tên các function theo thứ tự ghép. Với `uppercase|addSuffix`, binding thường là:

| Binding | Ý nghĩa |
|---|---|
| `uppercaseaddSuffix-in-0` | Input của function đã ghép. |
| `uppercaseaddSuffix-out-0` | Output của function đã ghép. |

Khi cấu hình destination:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase|addSuffix
    stream:
      bindings:
        uppercaseaddSuffix-in-0:
          destination: text.raw
        uppercaseaddSuffix-out-0:
          destination: text.normalized
~~~

Nếu tên binding dài hoặc khó đọc, có thể ánh xạ tên binding chức năng qua `spring.cloud.stream.function.bindings`. Khi đổi tên binding, mọi thuộc tính cấu hình và test phải dùng tên đã ánh xạ.

Không nhầm dấu phân cách:

- `uppercase|addSuffix` ghép hai function thành một pipeline.
- `uppercase;reverse` chọn hai function độc lập trong cùng ứng dụng, mỗi function có input/output binding riêng.

### 4.2. Test composition bằng Test Binder

Test sau xác minh cả thứ tự ghép và binding name:

~~~java
@SpringBootTest(
    classes = CompositionTest.TestApplication.class,
    properties = "spring.cloud.function.definition=uppercase|addSuffix"
)
class CompositionTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void appliesFunctionsInDeclaredOrder() {
        Message<byte[]> message = MessageBuilder
            .withPayload("hello".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(message, "uppercaseaddSuffix-in-0");

        Message<byte[]> result = output.receive(
            1_000,
            "uppercaseaddSuffix-out-0"
        );

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("HELLO!");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }

        @Bean
        Function<String, String> addSuffix() {
            return value -> value + "!";
        }
    }
}
~~~

Test Binder dùng message channel trong JVM nên không cần broker. `receive` có timeout giúp test thất bại rõ ràng nếu output không xuất hiện, thay vì chờ vô hạn.

Nên bổ sung các trường hợp:

- Function đầu vào nhận dữ liệu không hợp lệ.
- Function ở giữa ném exception.
- Function đầu ra tạo payload rỗng hoặc null theo contract.
- Content type không đúng với kiểu argument.
- Header cần thiết có được giữ/chuyển đổi như mong đợi hay không.

Mặc định, input headers không tự động được truyền hết qua output của function. Nếu cần giữ header, function có thể nhận `Message<?>` và chủ động tạo Message output, hoặc cấu hình `copy-input-headers` cho function tương ứng. Hãy test các header nghiệp vụ quan trọng thay vì giả định chúng luôn tồn tại.

## 5. Ghép Function với Consumer hoặc Supplier

Spring Cloud Function hỗ trợ một số composition khác nhau:

| Composition | Kiểu kết quả |
|---|---|
| Supplier + Function | Supplier |
| Supplier + Consumer | Runnable |
| Function + Function | Function |
| Function + Consumer | Consumer |

Không phải mọi cặp đều ghép được. Ví dụ Consumer không tạo output để truyền vào Function tiếp theo. Khi ghép Function với Consumer, composition kết thúc bằng Consumer và không có output binding.

Khi test composition kết thúc bằng Consumer, hãy kiểm tra side effect qua collaborator giả (mock/fake/recorder), thay vì chờ `OutputDestination`. Khi composition bắt đầu bằng Supplier, cần điều khiển poller hoặc cách kích hoạt Supplier; tránh để test chờ poll mặc định ngoài ý muốn.

Với reactive function, cần lưu ý function có thể được gọi một lần để tạo Publisher thay vì được gọi một lần cho mỗi message. Nếu ghép reactive function với Consumer, phải bảo đảm Consumer thực sự subscribe/consume stream theo mô hình được chọn. Test cần kiểm tra subscription và completion/error của Publisher.

## 6. Định tuyến message tới function hoặc Consumer

`RoutingFunction` cho phép một input binding nhận message rồi chọn function/consumer đích. Bật routing bằng:

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
~~~

Input binding của router có tên `functionRouter-in-0`. Message có thể mang một trong hai header:

- `spring.cloud.function.definition`: tên function/consumer hoặc composition cần gọi.
- `spring.cloud.function.routing-expression`: biểu thức SpEL để xác định function đích.

Ví dụ các handler:

~~~java
@Bean
Consumer<String> priorityHandler() {
    return value -> log.info("Priority order: {}", value);
}

@Bean
Consumer<String> standardHandler() {
    return value -> log.info("Standard order: {}", value);
}
~~~

Message gửi tới router có header:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-100")
    .setHeader("spring.cloud.function.definition", "priorityHandler")
    .build();
~~~

Router gọi `priorityHandler`. Nếu message chọn `standardHandler`, router gọi handler còn lại.

### 6.1. Test routing tới Consumer

Để kiểm tra route mà không phụ thuộc log, dùng một recorder thread-safe:

~~~java
class RouteRecorder {
    private final BlockingQueue<String> received = new LinkedBlockingQueue<>();

    void record(String route, String value) {
        received.add(route + ":" + value);
    }

    String next() throws InterruptedException {
        return received.poll(1, TimeUnit.SECONDS);
    }
}
~~~

Ứng dụng kiểm thử:

~~~java
@SpringBootApplication
@EnableTestBinder
class RoutingTestApplication {

    @Bean
    RouteRecorder routeRecorder() {
        return new RouteRecorder();
    }

    @Bean
    Consumer<String> priorityHandler(RouteRecorder recorder) {
        return value -> recorder.record("priority", value);
    }

    @Bean
    Consumer<String> standardHandler(RouteRecorder recorder) {
        return value -> recorder.record("standard", value);
    }
}
~~~

Test:

~~~java
@SpringBootTest(
    classes = RoutingTestApplication.class,
    properties = "spring.cloud.stream.function.routing.enabled=true"
)
class RoutingTest {

    @Autowired
    InputDestination input;

    @Autowired
    RouteRecorder recorder;

    @Test
    void routesToFunctionNamedInHeader() throws Exception {
        Message<byte[]> message = MessageBuilder
            .withPayload("order-100".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .setHeader("spring.cloud.function.definition", "priorityHandler")
            .build();

        input.send(message, "functionRouter-in-0");

        assertThat(recorder.next()).isEqualTo("priority:order-100");
    }
}
~~~

Vì handler là Consumer nên router không tạo output binding để trả message. Recorder cho phép xác minh chính xác handler nào được gọi.

### 6.2. Routing bằng SpEL

Khi cần chọn handler theo header, có thể dùng biểu thức:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-101")
    .setHeader("route", "priority")
    .setHeader(
        "spring.cloud.function.routing-expression",
        "headers['route'] == 'priority' ? 'priorityHandler' : 'standardHandler'"
    )
    .build();
~~~

SpEL nhận Message làm root object; có thể truy cập payload và headers. Cần kiểm thử:

- Giá trị header hợp lệ cho từng nhánh.
- Header bị thiếu hoặc null.
- Giá trị không được nhận diện.
- Function đích không tồn tại.
- Biểu thức lỗi hoặc trả về tên function không hợp lệ.

Không cho client không tin cậy tự gửi biểu thức SpEL hoặc function definition tùy ý. Hãy dùng một tập route được phép, validate dữ liệu đầu vào và kiểm soát những function có thể được gọi.

### 6.3. MessageRoutingCallback cho logic phức tạp

Khi quy tắc định tuyến không phù hợp với SpEL, có thể cung cấp bean `MessageRoutingCallback`:

~~~java
@Bean
MessageRoutingCallback messageRoutingCallback() {
    return message -> {
        String eventType = (String) message.getHeaders().get("eventType");

        return switch (eventType == null ? "" : eventType) {
            case "PRIORITY_ORDER" -> "priorityHandler";
            case "STANDARD_ORDER" -> "standardHandler";
            default -> throw new IllegalArgumentException(
                "Unsupported event type: " + eventType
            );
        };
    };
}
~~~

`MessageRoutingCallback` nhận `Message<?>` và trả về function definition. Callback được ưu tiên hơn header và routing properties. Nếu callback tồn tại, các chỉ dẫn `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` khác sẽ bị bỏ qua.

Test callback độc lập bằng cách truyền Message giả và assert function name được trả về. Sau đó dùng Test Binder kiểm tra tích hợp để xác nhận router thực sự gọi đúng Consumer.

## 7. RoutingFunction khi đích là Function

Khi router chọn Consumer, không cần output vì Consumer không trả kết quả. Khi router chọn Function, kết quả Function có thể được gửi ra output binding của RoutingFunction. Framework tạo output binding khi cần; không nên mặc định rằng router luôn có output binding ngay cả khi tất cả đích là Consumer.

Nếu cần kiểm thử route tới Function:

1. Tạo hai Function có cùng kiểu input/output tương thích.
2. Gửi message tới `functionRouter-in-0` với header chọn từng Function.
3. Nhận kết quả từ output binding do router tạo.
4. Assert payload và header cần thiết.

Nếu các Function có kiểu output khác nhau, hãy kiểm tra type conversion/content type và xác định rõ contract của output. Không để một output binding phải nhận nhiều kiểu payload không có schema hoặc content type thống nhất.

## 8. Định tuyến output bằng spring.cloud.stream.sendto.destination

Routing FROM Consumer cho phép một function quyết định destination output bằng header `spring.cloud.stream.sendto.destination`.

~~~java
record OrderEvent(String orderId, String region) {}

@Bean
Function<OrderEvent, Message<OrderEvent>> routeByRegion() {
    return event -> MessageBuilder
        .withPayload(event)
        .setHeader(
            "spring.cloud.stream.sendto.destination",
            "orders." + event.region()
        )
        .build();
}
~~~

Nếu region là `eu`, framework gửi output tới destination `orders.eu`. Nếu destination đã biết trước, nên khai báo producer properties tương ứng. Nếu tạo destination động, có thể dùng `spring.cloud.stream.dynamicDestinations` để chỉ cho phép danh sách destination đã định trước.

Không nối trực tiếp dữ liệu đầu vào không tin cậy vào tên destination. Hãy chuyển giá trị nghiệp vụ thành tên topic từ một bảng ánh xạ được kiểm soát, ví dụ `EU -> orders.eu`, `US -> orders.us`. Điều này tránh việc người gửi tạo topic tùy ý.

### 8.1. Test định tuyến output động

Test Binder có thể xác minh function đặt đúng header destination và message xuất hiện ở output tương ứng:

~~~java
@SpringBootTest(
    classes = DestinationRoutingTest.TestApplication.class,
    properties = {
        "spring.cloud.function.definition=routeByRegion",
        "spring.cloud.stream.dynamic-destinations=orders.eu"
    }
)
class DestinationRoutingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void routesOutputToRegionDestination() {
        Message<byte[]> message = MessageBuilder
            .withPayload("eu|order-9".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(message, "routeByRegion-in-0");

        Message<byte[]> routed = output.receive(1_000, "orders.eu");
        assertThat(routed).isNotNull();
        assertThat(new String(routed.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("order-9");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, Message<String>> routeByRegion() {
            return input -> {
                String[] parts = input.split("\\|", 2);
                String destination = switch (parts[0]) {
                    case "eu" -> "orders.eu";
                    default -> throw new IllegalArgumentException("Unknown region");
                };
                return MessageBuilder.withPayload(parts[1])
                    .setHeader("spring.cloud.stream.sendto.destination", destination)
                    .build();
            };
        }
    }
}
~~~

Test này xác minh route mapping trong ứng dụng và allowlist của Test Binder. Integration test với broker thật vẫn cần xác minh topic provisioning, quyền publish và producer properties của destination động.

## 9. StreamBridge dùng khi nào?

Function và Supplier là nguồn tự nhiên của mô hình streaming. Tuy nhiên, nguồn message có thể đến từ REST controller, scheduler, callback của hệ thống cũ, listener không dùng binder hoặc một service nghiệp vụ khác. `StreamBridge` cho phép gửi object/Message từ các nguồn đó tới output binding.

Ví dụ một publisher:

~~~java
@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

Nếu `orders-out-0` đã được khai báo là output binding, StreamBridge sử dụng binding đó. Có thể tạo binding từ lúc khởi động bằng:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

`StreamBridge.send` nhận `Object`, nên có thể gửi POJO hoặc `Message<?>`. Payload đi qua quy trình chuyển đổi, partitioning và producer properties như output được tạo bởi Function/Supplier.

## 10. Binding tĩnh và destination động với StreamBridge

Hai cách gửi thường gặp:

| Cách gửi | Ví dụ | Hành vi |
|---|---|---|
| Binding đã khai báo | `send("orders-out-0", event)` | Dùng output binding đã được cấu hình với destination và producer properties. |
| Destination động | `send("orders.eu", event)` | Nếu binding chưa tồn tại, StreamBridge tạo output binding khi gửi lần đầu và cache để tái sử dụng. |

Khi dùng destination động:

- Có thể tự động provision destination nếu binder hỗ trợ và tài khoản có quyền.
- Binding động được cache để dùng lại.
- Cache mặc định có kích thước 10; có thể cấu hình `spring.cloud.stream.dynamic-destination-cache-size`.
- Khi có quá nhiều destination, binding cũ có thể bị evict và cần tạo lại.
- Binding động do StreamBridge tạo không được quản lý trong application context giống binding tĩnh.

Với nhiều destination có thể dự đoán trước, nên khai báo binding rõ ràng để kiểm soát partition, serializer, retry, DLQ, required groups và các thuộc tính riêng của binder.

### 10.1. Giới hạn destination động

Cấu hình allowlist:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.us
        - orders.apac
~~~

Khi danh sách được đặt, chỉ destination trong danh sách mới được bind động. Đây là biện pháp quan trọng khi destination được quyết định từ dữ liệu request hoặc header.

Nếu dùng nhiều binder, có thể chỉ định binder trong overload:

~~~java
streamBridge.send("orders-out-0", "kafka", event);
~~~

Các overload hỗ trợ binder name còn có biến thể nhận `MimeType`. Binder name chỉ có tác dụng khi StreamBridge tạo binding động; nếu binding đã được tạo sẵn hoặc khai báo trong `spring.cloud.stream.output-bindings`, đối số binder name không thay đổi binder đã gắn với binding.

## 11. StreamBridge gửi đồng bộ và bất đồng bộ

Mặc định StreamBridge gửi trên thread của bên gọi và thao tác send là blocking. Có thể bật asynchronous send:

~~~java
streamBridge.setAsync(true);
boolean accepted = streamBridge.send("orders-out-0", event);
~~~

Async send hữu ích khi không muốn thread gọi chờ thao tác gửi. Tuy nhiên, việc chuyển sang thread khác ảnh hưởng observability context/tracing. Nếu cần giữ trace context, hãy cấu hình Micrometer context propagation theo hướng dẫn của phiên bản đang dùng.

Không coi `send(...) == true` là xác nhận end-to-end rằng consumer đã xử lý hoặc broker đã lưu bền vững message. Giá trị boolean cho biết thao tác gửi được chấp nhận ở tầng channel của framework. Delivery guarantee, broker acknowledgment và transaction còn phụ thuộc binder, producer configuration và middleware.

Nếu ứng dụng cần phản hồi HTTP, hãy xác định rõ API trả về có nghĩa là “đã nhận yêu cầu”, “đã đưa vào channel” hay “đã được broker xác nhận”. Không mô tả một trạng thái mạnh hơn điều mà send thực sự bảo đảm.

## 12. Test StreamBridge với Test Binder

Test Binder cho phép kiểm tra StreamBridge mà không cần broker:

~~~java
@SpringBootTest(
    classes = StreamBridgeTest.TestApplication.class,
    properties = "spring.cloud.stream.dynamic-destinations=orders.eu"
)
class StreamBridgeTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void sendsToAllowedDynamicDestination() {
        Message<byte[]> message = MessageBuilder
            .withPayload("order-200".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        assertThat(streamBridge.send("orders.eu", message)).isTrue();

        Message<byte[]> received = output.receive(1_000, "orders.eu");
        assertThat(received).isNotNull();
        assertThat(new String(received.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("order-200");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {
    }
}
~~~

Test này kiểm tra StreamBridge tạo binding động, gửi message tới đúng destination và giữ payload/content type như mong đợi trong môi trường Test Binder.

Nên có thêm test:

- Gửi tới binding tĩnh đã cấu hình.
- Gửi tới destination không nằm trong allowlist và xác minh thao tác thất bại.
- Gửi POJO và kiểm tra JSON conversion.
- Gửi Message có header nghiệp vụ.
- Kiểm tra `send` trả về false khi channel không chấp nhận message trong điều kiện test phù hợp.
- Kiểm tra destination name được tạo từ route mapping chứ không lấy trực tiếp từ input tùy ý.

Đối với logic gọi StreamBridge, có thể inject `StreamOperations` (interface mà StreamBridge triển khai) để mock trong unit test. Cách này cho phép kiểm tra binding name, payload và số lần gọi mà không khởi tạo binder.

## 13. Test nhiều function độc lập và nhiều output

Khi ứng dụng có nhiều function nhưng không ghép chúng thành một pipeline, khai báo danh sách function bằng dấu `;`:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

Mỗi function có input/output binding riêng. Test nên gửi tới đúng input binding và đọc đúng output binding:

~~~java
input.send(message, "uppercase-in-0");
input.send(message, "reverse-in-0");

Message<byte[]> upper = output.receive(1_000, "uppercase-out-0");
Message<byte[]> reversed = output.receive(1_000, "reverse-out-0");
~~~

Với function có nhiều output, tên binding có index như `split-out-0` và `split-out-1`. Test cần assert cả hai nhánh, số lượng message và payload tương ứng; không chỉ đọc output đầu tiên rồi kết thúc.

Với nhiều input, dùng `InputDestination.send(message, destinationName)` để đưa message vào đúng nguồn. Điều này đặc biệt quan trọng với function có arity nhiều input, bởi dữ liệu gửi nhầm input binding có thể làm topology chờ một input khác hoặc tạo kết quả khác mong đợi.

## 14. Kiểm thử header và content type

Routing, composition và StreamBridge thường phụ thuộc header. Nên kiểm tra:

- `MessageHeaders.CONTENT_TYPE` có đúng định dạng mà converter cần hay không.
- `spring.cloud.function.definition` có đúng function đích hay không.
- `spring.cloud.function.routing-expression` có trả về route hợp lệ hay không.
- `spring.cloud.stream.sendto.destination` có đúng destination được phép hay không.
- Correlation ID, trace ID hoặc tenant ID có được truyền theo contract hay không.
- Header nhạy cảm có bị loại trước khi publish hay không.

Không giả định mọi header input tự động xuất hiện ở output. Function trả về payload thuần thường không giữ toàn bộ header. Nếu cần truyền header, trả về `Message<?>` và sao chép có chọn lọc:

~~~java
@Bean
Function<Message<String>, Message<String>> enrich() {
    return input -> MessageBuilder
        .withPayload(input.getPayload().trim())
        .setHeader("correlationId", input.getHeaders().get("correlationId"))
        .setHeader("processedBy", "order-normalizer")
        .build();
}
~~~

Chỉ sao chép header cần thiết. Tránh chuyển tiếp token, credential hoặc header nội bộ tới destination bên ngoài.

## 15. Test Binder không thay thế integration test với broker

Spring Integration Test Binder là message broker in-JVM dựa trên Spring Integration. Nó rất phù hợp để kiểm tra function, composition, binding wiring và message flow cơ bản mà không cần middleware.

Test Binder không chứng minh các thuộc tính riêng của Kafka, RabbitMQ hoặc Pulsar hoạt động đúng. Sau khi unit test và Test Binder pass, cần integration test với binder thật cho các yêu cầu sau:

| Hành vi | Vì sao cần broker thật |
|---|---|
| Topic/queue/exchange provisioning | Phụ thuộc quyền, topology và cấu hình của broker. |
| Partition, routing key, consumer group | Cách phân phối và ordering do binder/broker quyết định. |
| Serialization và schema registry | Phụ thuộc serializer, schema và broker validation. |
| Retry, acknowledgment, DLQ | Semantics khác nhau giữa Kafka, RabbitMQ và Pulsar. |
| Transaction và delivery guarantee | Phụ thuộc producer, broker và binder cụ thể. |
| ACL, authentication, TLS | Không được mô phỏng đầy đủ bằng in-memory binder. |
| Dynamic destination lifecycle | Cần xác minh provisioning, cache và cleanup trên broker thật. |

Một chiến lược phù hợp:

1. Unit test cho function thuần và route mapping.
2. Test Binder cho composition, input/output binding, routing header và StreamBridge.
3. Integration test với broker thật (có thể dùng Testcontainers) cho provisioning, serialization, routing, partition và delivery behavior.
4. Smoke test trên môi trường triển khai để xác minh cấu hình, quyền truy cập và quan sát.

Lưu ý: khi `spring-cloud-stream-test-binder` có mặt trên test classpath, Spring Cloud Stream sử dụng Test Binder cho mục đích test. Không trộn Test Binder và regular middleware binder trong cùng module test rồi kỳ vọng một test context dùng cả hai. Tách integration test dùng Kafka/Rabbit/Pulsar binder thật khỏi test module sử dụng in-JVM Test Binder, hoặc cấu hình loại trừ auto-configuration Test Binder theo hướng dẫn của phiên bản.

## 16. Ma trận test gợi ý

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Composition | `uppercase|addSuffix` với payload hợp lệ. | Output đúng thứ tự biến đổi. |
| Composition | Function đầu vào lỗi. | Exception/error flow được quan sát đúng. |
| Composition | Kiểu output của function trước không khớp input function sau. | Conversion đúng hoặc test phát hiện lỗi kiểu. |
| Composition | Header correlation ID. | Header được giữ/chuyển theo contract đã cấu hình. |
| Independent functions | `uppercase;reverse`. | Mỗi binding nhận và trả đúng message riêng. |
| Routing | Header chọn `priorityHandler`. | Chỉ handler priority được gọi. |
| Routing | Header chọn `standardHandler`. | Chỉ handler standard được gọi. |
| Routing | Thiếu route hoặc route không hợp lệ. | Fail/fallback theo chính sách đã chọn, không route ngẫu nhiên. |
| Routing | MessageRoutingCallback tồn tại. | Callback được ưu tiên hơn routing headers/properties. |
| Output routing | `sendto.destination=orders.eu`. | Output tới destination đã chọn. |
| StreamBridge | Binding tĩnh. | Gửi qua đúng output binding. |
| StreamBridge | Destination động hợp lệ. | Binding được tạo và message đến đúng destination. |
| StreamBridge | Destination ngoài allowlist. | Không tạo binding ngoài danh sách. |
| StreamBridge | Nhiều destination động. | Cache/eviction được hiểu và vận hành đúng. |
| StreamBridge | Async send. | Caller không bị chặn theo cấu hình; trace context được xử lý. |
| Broker integration | ACL/provisioning/partition/schema. | Broker thật thực thi đúng cấu hình. |

## 17. Lỗi thường gặp

1. Dùng dấu `;` khi muốn ghép function bằng `|`; kết quả là hai function độc lập thay vì một pipeline.
2. Dùng tên binding của function gốc khi test composition; composition có binding name riêng.
3. Giả định Consumer tạo output binding; Consumer không trả dữ liệu để publish.
4. Gửi routing message vào `uppercase-in-0` thay vì `functionRouter-in-0`.
5. Cho rằng header `spring.cloud.function.definition` luôn thắng; `MessageRoutingCallback` có thể được ưu tiên cao hơn.
6. Cho phép client gửi function name hoặc SpEL tùy ý, làm route vượt khỏi danh sách handler được phép.
7. Định tuyến output bằng destination lấy trực tiếp từ payload không qua allowlist.
8. Nhầm `sendto.destination` với `StreamBridge.send` binding name; hai cách định tuyến output khác nhau.
9. Gọi `StreamBridge.send` bằng tên physical destination nhưng lại cấu hình binding tĩnh dưới tên binding khác.
10. Nghĩ `send() == true` đồng nghĩa broker đã lưu message hoặc consumer đã xử lý.
11. Tạo quá nhiều dynamic destinations mà không giới hạn danh sách/cache.
12. Dùng Test Binder để kết luận partition, retry, DLQ hoặc transaction của broker thật hoạt động đúng.
13. Giả định header input luôn được truyền sang output của function.
14. Test nhiều input/output nhưng không chỉ định binding name, khiến message được gửi hoặc đọc nhầm destination.

## 18. Quy trình triển khai và kiểm thử

1. Viết từng function nhỏ và unit test business logic.
2. Khai báo composition bằng `spring.cloud.function.definition` và xác nhận binding names.
3. Dùng Test Binder gửi input vào đúng binding và assert output.
4. Nếu cần route tới handler, bật RoutingFunction và xác định route contract.
5. Validate route bằng allowlist hoặc MessageRoutingCallback; test cả route hợp lệ và không hợp lệ.
6. Nếu route output động, dùng `sendto.destination` hoặc StreamBridge và giới hạn destination được phép.
7. Test StreamBridge với binding tĩnh trước, sau đó test destination động và cache behavior.
8. Kiểm tra content type, payload, key, correlation ID và header cần thiết.
9. Integration test với đúng Kafka/RabbitMQ/Pulsar binder cho provisioning, partition, serialization, security và delivery semantics.
10. Theo dõi log, metric và trace để biết route nào được chọn, message được gửi tới đâu và lỗi phát sinh ở ranh giới nào.

Function composition giúp tách logic thành các bước nhỏ có thể kiểm thử riêng; routing quyết định handler hoặc destination dựa trên message; StreamBridge đưa dữ liệu từ nguồn ngoài vào cùng cơ chế binding của Spring Cloud Stream. Khi kiểm thử theo từng lớp và xác minh broker ở integration test, ứng dụng có thể thay đổi pipeline hoặc destination mà vẫn giữ được contract message rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 – Testing with Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream – Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Stream – Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function 4.0 – Function Composition and Routing](https://docs.spring.io/spring-cloud-function/docs/current/reference/html/spring-cloud-function.html)
