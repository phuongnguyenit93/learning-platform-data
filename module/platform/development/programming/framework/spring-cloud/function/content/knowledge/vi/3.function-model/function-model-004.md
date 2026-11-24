# BiFunction và BiConsumer với payload cùng Map chứa header

Trong **SPRING_CLOUD_FUNCTION**, đôi khi dữ liệu nghiệp vụ nằm trong **payload**, nhưng cách xử lý còn cần **header** của thông điệp: mã tương quan để truy vết, loại sự kiện, định dạng nội dung hoặc thông tin định tuyến. Spring Cloud Function hỗ trợ **BiFunction** và **BiConsumer** để nhận đồng thời **payload** và một **Map chứa headers** mà không bắt logic nghiệp vụ phải nhận trực tiếp đối tượng `Message<T>` của Spring Messaging.

Bài học thuộc chương **Mô hình hàm**. Ta sẽ đi từ hợp đồng Java, quy tắc đặc biệt của Spring Cloud Function, ví dụ code có thể kiểm thử, tới cách sử dụng qua HTTP, sự kiện và môi trường serverless. Trọng tâm là **hiểu đúng đối số thứ hai**, bảo toàn metadata khi cần và kiểm soát lỗi hoặc tác dụng phụ.

## 1. BiFunction và BiConsumer trong Java thuần

Java cung cấp hai functional interface:

~~~java
@FunctionalInterface
public interface BiFunction<T, U, R> {
    R apply(T first, U second);
}

@FunctionalInterface
public interface BiConsumer<T, U> {
    void accept(T first, U second);
}
~~~

- **BiFunction<T, U, R>** nhận hai đối số **T, U** và trả về **R**.
- **BiConsumer<T, U>** nhận hai đối số **T, U**, thực hiện xử lý và trả về **void**.
- Trong **Java thuần**, kiểu **U** có thể là bất kỳ kiểu nào, ví dụ Integer, String hoặc Map.
- Trong **mô hình tích hợp BiFunction/BiConsumer của Spring Cloud Function**, trường hợp được framework hỗ trợ có **đối số thứ hai là Map chứa message headers**. Đây là ràng buộc quan trọng hơn chữ ký Java nói chung.

Ví dụ Java thuần đơn giản:

~~~java
import java.util.Map;
import java.util.function.BiFunction;
import java.util.function.BiConsumer;

BiFunction<String, Map<String, Object>, String> describe =
    (payload, headers) ->
        payload + " [correlationId=" + headers.get("correlationId") + "]";

BiConsumer<String, Map<String, Object>> logEvent =
    (payload, headers) ->
        System.out.println(headers.get("correlationId") + ": " + payload);

Map<String, Object> metadata = Map.of("correlationId", "trace-001");

String result = describe.apply("ORDER_CREATED", metadata);
logEvent.accept("ORDER_CREATED", metadata);
~~~

Khi gọi trực tiếp bằng Java, **apply(payload, headers)** và **accept(payload, headers)** hoạt động như hai tham số thông thường. Khi được đăng ký làm bean trong Spring Cloud Function, framework dùng một quy tắc riêng để lấy hai tham số đó từ **Message**.

## 2. Quy tắc của Spring Cloud Function: đối số thứ hai phải là Map

Ở tầng truyền tải, một thông điệp thường có hai phần:

~~~text
Message<T>
├── payload: T
└── headers: Map<String, Object>
~~~

Spring Cloud Function nhận diện bean kiểu **BiFunction<T, Map, R>** hoặc **BiConsumer<T, Map>** theo quy ước:

1. Adapter tiếp nhận dữ liệu và cung cấp nó dưới dạng message có **payload** và **headers**.
2. Framework lấy **payload** đưa vào tham số thứ nhất.
3. Framework lấy **headers** đưa vào tham số thứ hai có kiểu **Map**.
4. Framework gọi **apply(payload, headers)** hoặc **accept(payload, headers)**.
5. Với BiFunction, kết quả được chuyển tiếp tới adapter; với BiConsumer, không có kết quả nghiệp vụ.

~~~mermaid
flowchart LR
    A["HTTP / Broker / Serverless"] --> B["Message<T>"]
    B --> C["payload: T"]
    B --> D["headers: Map"]
    C --> E["BiFunction.apply / BiConsumer.accept"]
    D --> E
    E --> F["BiFunction: kết quả R"]
    E --> G["BiConsumer: tác dụng phụ"]
~~~

**Ràng buộc bắt buộc:** tham số thứ hai phải là **Map**; có thể khai báo rõ hơn như **Map<String, Object>**. **BiFunction<OrderId, Quantity, Price>** không được Spring Cloud Function tự hiểu là hai payload nghiệp vụ riêng biệt. Nếu cần nhiều giá trị nghiệp vụ, hãy gói chúng trong một **record/DTO** duy nhất làm payload.

~~~java
// Phù hợp với cơ chế payload + headers của Spring Cloud Function:
BiFunction<OrderEvent, Map<String, Object>, OrderView>

// Không biểu đạt payload + headers theo quy ước đó:
BiFunction<OrderEvent, Integer, OrderView>
~~~

**Đừng nhầm Map headers với Map payload.** Một payload hoàn toàn có thể là **Map<String, Object>**; khi đó cả payload lẫn headers đều có kiểu Map nhưng có **vai trò khác nhau** và nằm ở hai đối số riêng:

~~~java
BiFunction<Map<String, Object>, Map<String, Object>, String>
~~~

Chữ ký trên chỉ rõ kiểu Map của cả hai đối số, nhưng không thể hiện rõ ý nghĩa nghiệp vụ. Nếu biết schema, ưu tiên DTO/record cho payload, ví dụ **OrderEvent**, để code dễ đọc và dễ kiểm thử.

## 3. Khi nào nên dùng BiFunction, BiConsumer và Message<T>?

| Mô hình | Dữ liệu mà logic nhận | Kết quả | Khi nào phù hợp |
| --- | --- | --- | --- |
| **Function<T, R>** | Chỉ payload | R | Biến đổi nghiệp vụ không cần header |
| **Consumer<T>** | Chỉ payload | void | Xử lý sự kiện mà không quan tâm metadata |
| **Function<Message<T>, R>** | Message chứa payload và header | R | Cần Spring Messaging API trong logic |
| **Consumer<Message<T>>** | Message chứa payload và header | void | Cần thao tác trực tiếp với Message |
| **BiFunction<T, Map<String, Object>, R>** | Payload và Map headers tách riêng | R | Đọc metadata nhưng giữ chữ ký gần với Java/POJO |
| **BiConsumer<T, Map<String, Object>>** | Payload và Map headers tách riêng | void | Xử lý tác dụng phụ có truy vết/metadata |

Ví dụ hai cách viết tương đương về nhu cầu đọc metadata:

~~~java
import java.util.function.Function;
import java.util.function.BiFunction;
import java.util.Map;
import org.springframework.messaging.Message;

// Nhận cả đối tượng Message:
Function<Message<String>, String> byMessage =
    message -> message.getPayload() + "-"
        + message.getHeaders().get("correlationId");

// Nhận riêng payload và Map headers:
BiFunction<String, Map<String, Object>, String> byBiFunction =
    (payload, headers) -> payload + "-"
        + headers.get("correlationId");
~~~

Cách thứ hai không bắt phần biến đổi nghiệp vụ phải gọi **message.getPayload()** và **message.getHeaders()**. Tuy vậy, **Map headers** vẫn là metadata từ lớp truyền tải; việc đọc header không tự bảo đảm tính xác thực hoặc tính toàn vẹn của giá trị đó.

## 4. Ví dụ xuyên suốt: xử lý sự kiện đơn hàng cùng correlationId

Giả sử dịch vụ nhận **OrderEvent** và cần làm hai việc độc lập:

- **summarizeOrder:** tạo bản tóm tắt đơn hàng có mã tương quan để ghi nhận nguồn request.
- **auditOrder:** ghi nhận một bản audit theo **eventId** và lưu mã tương quan cho việc tra cứu log.

**eventId** nằm trong payload và làm khóa nghiệp vụ để giảm ghi trùng; **correlationId** nằm ở header và được dùng cho observability. Không sử dụng correlationId làm bằng chứng người gọi có quyền thao tác.

### 4.1. Khai báo ứng dụng và hai bean

Ví dụ dùng Java 17+ và Spring Boot với phiên bản Spring Cloud Function tương thích:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HeaderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderFunctionApplication.class, args);
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        BigDecimal amount
    ) {}

    public record OrderView(
        String orderId,
        BigDecimal amount,
        String correlationId
    ) {}

    public record AuditEntry(
        String eventId,
        String orderId,
        String correlationId
    ) {}

    public static class AuditStore {
        private final ConcurrentMap<String, AuditEntry> entries =
            new ConcurrentHashMap<>();

        public boolean recordOnce(AuditEntry entry) {
            return entries.putIfAbsent(entry.eventId(), entry) == null;
        }

        public int size() {
            return entries.size();
        }
    }

    @Bean
    AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    BiFunction<OrderEvent, Map<String, Object>, OrderView>
            summarizeOrder() {
        return (event, headers) -> {
            validate(event);

            return new OrderView(
                event.orderId(),
                event.amount(),
                correlationId(headers)
            );
        };
    }

    @Bean
    BiConsumer<OrderEvent, Map<String, Object>>
            auditOrder(AuditStore store) {
        return (event, headers) -> {
            validate(event);

            store.recordOnce(new AuditEntry(
                event.eventId(),
                event.orderId(),
                correlationId(headers)
            ));
        };
    }

    static void validate(OrderEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()
                || event.amount() == null
                || event.amount().signum() < 0) {
            throw new IllegalArgumentException("Invalid order event");
        }
    }

    static String correlationId(Map<String, Object> headers) {
        if (headers == null) {
            return "unavailable";
        }

        Object value = headers.get("correlationId");
        if (value instanceof String text && !text.isBlank()) {
            return text;
        }

        return "unavailable";
    }
}
~~~

Trong ví dụ:

1. **OrderEvent** là payload nghiệp vụ có schema rõ ràng.
2. **summarizeOrder** có chữ ký **BiFunction<OrderEvent, Map<String,Object>, OrderView>** và trả về dữ liệu mới.
3. **auditOrder** có chữ ký **BiConsumer<OrderEvent, Map<String,Object>>** và thực hiện tác dụng phụ vào **AuditStore**.
4. **correlationId(...)** đọc metadata bằng khóa rõ ràng, xử lý trường hợp header thiếu hoặc không phải String.
5. **validate(...)** từ chối payload không hợp lệ trước khi biến đổi hoặc ghi audit.
6. **recordOnce(...)** sử dụng **eventId** để minh họa tránh ghi trùng trong một instance.

**Giới hạn của AuditStore:** kho **ConcurrentHashMap** chỉ phục vụ ví dụ và unit test. Nó không bền vững khi ứng dụng restart và không phối hợp giữa nhiều instance. Nếu đưa Consumer vào production, hãy dùng database hoặc kho chung có unique constraint/giao dịch phù hợp với **eventId**.

### 4.2. Gọi trực tiếp mà không có Spring adapter

Ta có thể kiểm thử hai bean như Java thuần:

~~~java
var app = new HeaderFunctionApplication();

var event = new HeaderFunctionApplication.OrderEvent(
    "evt-001", "ORD-101", new BigDecimal("250000")
);
Map<String, Object> headers =
    Map.of("correlationId", "trace-123");

var summarize = app.summarizeOrder();
var view = summarize.apply(event, headers);
// view.orderId()       -> "ORD-101"
// view.correlationId() -> "trace-123"

var store = new HeaderFunctionApplication.AuditStore();
var audit = app.auditOrder(store);

audit.accept(event, headers);
audit.accept(event, headers);
System.out.println(store.size()); // 1
~~~

Việc gọi trực tiếp xác minh logic của **BiFunction/BiConsumer**. Nhưng thử trực tiếp **không kiểm tra** cơ chế Spring Cloud Function tách **Message** thành hai đối số; phần đó cần kiểm thử tích hợp riêng.

## 5. FunctionCatalog: từ Message đến hai tham số

Một điểm dễ nhầm: trong Spring Cloud Function, **bean do bạn khai báo** là BiFunction/BiConsumer, nhưng framework có thể **bọc hàm lại thành dạng Function nhận Message** để thuận tiện cho conversion, composition và adapter.

~~~mermaid
flowchart TB
    A["Bean: BiFunction<T, Map, R>"] --> B["FunctionCatalog / wrapper"]
    C["Message<T>"] --> B
    B --> D["Tách payload và headers"]
    D --> E["BiFunction.apply(payload, headers)"]
    E --> F["R"]
~~~

Bởi vậy cần phân biệt **cách gọi trực tiếp bean** với **cách gọi qua catalog/adapter**:

- **Bean Java thuần:** dùng **apply(payload, headers)** hoặc **accept(payload, headers)**.
- **Catalog/adapter:** truyền **Message<T>** tới wrapper để framework tách thành payload và Map headers. Không giả định wrapper lúc nào cũng là một đối tượng BiFunction có thể gọi trực tiếp bằng hai tham số.
- **Conversion:** adapter có thể chuyển byte/JSON sang kiểu payload T dựa trên khai báo hàm và content type. Nếu kiểu hoặc header không khớp, cần kiểm tra cấu hình converter.

Ví dụ một lớp Spring thực sự nhận `FunctionCatalog` qua constructor injection rồi gọi wrapper bằng `Message`:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CatalogCaller {
    private final FunctionCatalog catalog;

    public CatalogCaller(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Object invokeSummary() {
        HeaderFunctionApplication.OrderEvent event =
            new HeaderFunctionApplication.OrderEvent(
                "evt-001", "ORD-101", new BigDecimal("250000")
            );

        Message<HeaderFunctionApplication.OrderEvent> message =
            MessageBuilder.withPayload(event)
                .setHeader("correlationId", "trace-123")
                .build();

        Function<Message<HeaderFunctionApplication.OrderEvent>, ?>
            invocation = catalog.lookup("summarizeOrder");

        if (invocation == null) {
            throw new IllegalStateException("Function not found");
        }

        return invocation.apply(message);
    }
}
~~~

Ví dụ đặt **CatalogCaller** thành một lớp riêng trong cùng package với **HeaderFunctionApplication**, còn đối tượng trả về từ wrapper có thể cần được kiểm tra kiểu tùy cơ chế chuyển đổi đã chọn. Ý quan trọng là **Message** được truyền đến catalog, còn bean BiFunction nhận **payload** và **Map headers**.

Có thể chọn định nghĩa khi ứng dụng chứa nhiều hàm:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
~~~

Trong một ứng dụng chỉ nhận sự kiện để audit, định nghĩa tương ứng là **auditOrder**. Các tên này phải khớp tên bean đăng ký.

## 6. Headers là Map: đọc thế nào để không gây lỗi?

Giá trị của header không bắt buộc là String. Các thành phần tích hợp có thể lưu content type, timestamp, ID hoặc metadata khác ở nhiều kiểu Java.

~~~java
Object raw = headers.get("correlationId");

if (raw instanceof String correlationId) {
    System.out.println(correlationId);
}
~~~

Không nên cast mù quáng:

~~~java
// Có thể ném ClassCastException nếu header không phải String:
String correlationId = (String) headers.get("correlationId");
~~~

Các tình huống cần tính đến:

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Header **correlationId** không tồn tại | **get(...)** trả về null | Có giá trị mặc định hoặc quy tắc từ chối rõ ràng |
| Header có kiểu khác String | Cast lỗi | Kiểm tra kiểu hoặc định nghĩa converter |
| Tên header thay đổi hoa/thường | Tra cứu theo tên thất bại | Chuẩn hóa theo hợp đồng adapter; kiểm thử HTTP header mapping |
| Payload Map và headers Map cùng tồn tại | Dễ đọc nhầm | Dùng DTO cho payload, tên tham số rõ ràng |
| Header chứa metadata nhạy cảm | Log có thể làm lộ dữ liệu | Chỉ ghi trường cần thiết, che thông tin nhạy cảm |

Đặc biệt, **Map headers do framework đưa vào thường là MessageHeaders**, là dạng map chỉ đọc. Không nên sửa trực tiếp:

~~~java
// Tránh thao tác sửa headers nhận từ Message:
headers.put("processedBy", "order-service");
~~~

Nếu cần bổ sung hoặc thay header đầu ra, hãy tạo một **Message mới** thay vì cố mutate Map đầu vào.

## 7. Bảo toàn hoặc bổ sung header ở đầu ra

**BiFunction<T, Map, R>** trả về **R**. Không nên mặc định mọi input header được tự động sao chép sang output. Khi nghiệp vụ cần kiểm soát metadata đầu ra, có thể sử dụng **Function<Message<T>, Message<R>>**:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderEvent>, Message<OrderView>> summarizeMessage() {
    BiFunction<OrderEvent, Map<String, Object>, OrderView> summary =
        summarizeOrder();

    return input -> {
        OrderView view = summary.apply(
            input.getPayload(),
            input.getHeaders()
        );

        return MessageBuilder.withPayload(view)
            .copyHeaders(input.getHeaders())
            .setHeader("processedBy", "summarizeMessage")
            .build();
    };
}
~~~

Đặt bean **summarizeMessage** trong cùng lớp cấu hình ví dụ, nơi đã khai báo **OrderEvent**, **OrderView** và **summarizeOrder**. Đoạn code tạo **Message<OrderView>** mới và quyết định rõ header nào được giữ/thêm. Nếu chỉ cần một vài header, có thể dùng **setHeader(...)** thay cho sao chép toàn bộ. Tránh lan truyền tự động header nội bộ hoặc nhạy cảm ra hệ thống bên ngoài.

Spring Cloud Function còn có những tùy chọn như **copy-input-headers** cho một số trường hợp cần bảo toàn metadata ở output:

~~~yaml
spring:
  cloud:
    function:
      configuration:
        summarizeOrder:
          copy-input-headers: true
~~~

Tùy chọn này không thay thế việc thiết kế header contract. Cần xác minh theo phiên bản framework, adapter và thứ tự composition đang sử dụng; nhất là khi đầu ra cần loại bỏ header không được phép truyền tiếp.

## 8. Qua HTTP: body là payload, header là metadata

Với adapter web của Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Chọn **summarizeOrder** rồi khởi chạy ứng dụng Spring Boot:

~~~yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
~~~

Thử gửi POST tới endpoint tương ứng khi ứng dụng dùng cổng 8080:

~~~bash
curl -i -X POST http://localhost:8080/summarizeOrder \
  -H "Content-Type: application/json" \
  -H "correlationId: trace-123" \
  -d '{"eventId":"evt-001","orderId":"ORD-101","amount":250000}'
~~~

Ý nghĩa của request:

- **JSON body** là nguồn dữ liệu để adapter chuyển thành **OrderEvent**.
- **Content-Type** giúp adapter chọn cách diễn giải body.
- **correlationId** là header ứng dụng muốn đọc bằng tham số Map.
- **BiFunction** trả ra **OrderView**, adapter có thể serialize thành JSON.

Ví dụ phản hồi khi adapter ánh xạ header đúng như cấu hình:

~~~json
{
  "orderId": "ORD-101",
  "amount": 250000,
  "correlationId": "trace-123"
}
~~~

**Lưu ý về tên header:** các lớp HTTP, proxy, container servlet và message adapter có thể thay đổi cách biểu diễn tên header. Đừng coi tên **correlationId** hoặc việc giữ nguyên chữ hoa/chữ thường là bảo đảm xuyên suốt mọi môi trường. Trong hệ thống thực, thường chọn một tên header nhất quán như **X-Correlation-Id** và viết phép ánh xạ/kiểm thử phù hợp với adapter. Nếu không được chuyển tiếp, logic ví dụ sẽ trả **unavailable**.

Cần nhớ **BiConsumer không có dữ liệu nghiệp vụ trả về**. Nếu expose **auditOrder** qua HTTP, client không nên chờ một **OrderView**; việc adapter trả mã HTTP nào khi thành công hoặc khi Consumer ném exception cần kiểm tra theo phiên bản và cấu hình.

## 9. Qua Spring Cloud Stream: header và payload của event

Khi xử lý sự kiện từ Kafka, RabbitMQ hoặc broker khác, phần payload được deserialize sang **OrderEvent**, còn message headers có thể chứa metadata của producer, binder và tracing.

Ví dụ cấu hình cho **auditOrder**:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrder
    stream:
      bindings:
        auditOrder-in-0:
          destination: orders.created
          group: order-audit
~~~

Đây là cấu hình minh họa **input binding**. Ứng dụng cần thêm Spring Cloud Stream, binder thích hợp, broker và thông tin kết nối. **BiConsumer** được framework thích nghi để nhận **payload cùng headers**; hành vi đăng ký/wrapping và binding cụ thể nên được kiểm thử tích hợp với phiên bản đã chọn.

~~~mermaid
flowchart LR
    A["Broker / orders.created"] --> B["Stream binder"]
    B --> C["Message<OrderEvent>"]
    C --> D["payload OrderEvent"]
    C --> E["headers Map"]
    D --> F["auditOrder.accept"]
    E --> F
    F --> G["AuditStore"]
~~~

Khác với HTTP, message broker có thể **gửi lại một thông điệp** sau timeout, retry hoặc restart. Bởi vậy:

- Chọn một **eventId nghiệp vụ ổn định** trong payload để làm idempotency key.
- Đừng chỉ dùng Message ID/offset hoặc **correlationId** làm khóa chống trùng nếu hợp đồng nghiệp vụ không bảo đảm tính ổn định của chúng.
- Khi database ghi thành công nhưng việc acknowledgment thất bại, binder có thể giao lại event; Consumer phải chịu được lặp.
- Không suy ra cơ chế **exactly once** chỉ vì code sử dụng BiConsumer hay vì broker có transaction riêng.

Trong ví dụ, **ConcurrentHashMap.putIfAbsent** giúp tránh trùng khi cùng một instance còn sống. Khi triển khai nhiều instance, phải dùng unique constraint và transaction tại storage bền vững.

### Khi metadata quan trọng hơn payload

Một số tích hợp phát các sự kiện đặc biệt như **tombstone record** trong Kafka, nơi payload có thể rỗng hoặc mang dấu hiệu xóa. Việc lấy Map headers tách riêng có thể hữu ích để truy cập metadata khi xử lý payload null. Tuy nhiên, cách adapter biểu diễn null/tombstone phụ thuộc binder, kiểu serializer và phiên bản. Không được mặc định một **record OrderEvent** luôn tồn tại trong trường hợp này; cần thiết kế một nhánh riêng hoặc handler phù hợp khi quy trình hỗ trợ tombstone.

## 10. Serverless vẫn dùng cùng hợp đồng hàm

Một runtime serverless có thể chuyển event đầu vào thành Message rồi đưa vào adapter Spring Cloud Function:

~~~text
Cloud invocation / event
  -> adapter
  -> Message<OrderEvent>
  -> payload + headers
  -> summarizeOrder hoặc auditOrder
  -> kết quả trả về / tác dụng phụ
~~~

Điểm tái sử dụng là **chữ ký nghiệp vụ**. Phần code tính toán hoặc audit không cần trực tiếp đọc request HTTP hay API broker. Tuy nhiên, serverless vẫn cần **handler**, dependency adapter, packaging, quy tắc mapping event, timeout và cấp quyền tương ứng với nền tảng.

Một event serverless có thể không có header tên **correlationId** mặc định. Nếu cần metadata tương quan, hãy xác định cách adapter chuyển thông tin từ **event envelope** hoặc runtime context sang Map headers, rồi viết integration test kiểm tra. Đừng tự suy ra rằng mọi metadata của provider đã nằm trong Map giống HTTP.

## 11. Composition khi một bước cần metadata

Spring Cloud Function cho phép ghép các hàm theo thứ tự bằng dấu **|** khi kiểu dữ liệu và hợp đồng xử lý phù hợp. Với chuỗi có một BiFunction cần header, phải cân nhắc **header có còn tồn tại sau bước trước hay không**.

Ví dụ, một bước chuẩn hóa input có thể nhận Message và trả Message để **bảo toàn header**:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderEvent>, Message<OrderEvent>>
        normalizeOrderMessage() {
    return message -> {
        OrderEvent original = message.getPayload();

        OrderEvent normalized = new OrderEvent(
            original.eventId(),
            original.orderId().trim(),
            original.amount()
        );

        return MessageBuilder.withPayload(normalized)
            .copyHeaders(message.getHeaders())
            .build();
    };
}
~~~

Sau đó cấu hình chuỗi dự kiến:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrderMessage|summarizeOrder
~~~

Tư duy xử lý:

~~~mermaid
flowchart LR
    A["Message<OrderEvent>"] --> B["normalizeOrderMessage"]
    B --> C["Message<OrderEvent> có headers"]
    C --> D["BiFunction summarizeOrder"]
    D --> E["OrderView"]
~~~

Nhờ bước đầu trả Message với headers được sao chép, bước BiFunction có thể đọc **correlationId** sau khi payload đã được chuẩn hóa. Cần kiểm thử composition thật trong phiên bản Spring Cloud Function đang dùng, nhất là conversion, wrapper type và những header do adapter bổ sung.

Không nên coi **BiFunction<T, Map, R>** là một pipeline hai đầu vào nghiệp vụ độc lập. Nếu bước trước phải tạo cả payload và metadata, hãy tạo **Message** mới để biểu diễn ranh giới đó.

## 12. BiConsumer và tác dụng phụ: retry, bảo mật, tính nhất quán

Với BiConsumer, phần header thường hỗ trợ **truy vết** hoặc **quyết định kỹ thuật**, còn dữ liệu tác dụng phụ phải dựa trên một hợp đồng nghiệp vụ đã được xác thực.

Ví dụ tình huống:

~~~text
T1: Nhận eventId=evt-001, correlationId=trace-123
T2: auditOrder ghi thành công vào database
T3: Xác nhận với broker thất bại
T4: Broker giao lại eventId=evt-001, correlationId có thể khác
T5: Audit kiểm tra eventId đã tồn tại rồi bỏ qua ghi trùng
~~~

Nếu dùng correlationId làm khóa idempotency, dữ liệu có thể bị ghi trùng ở bước T5. **EventId** hoặc khóa nghiệp vụ ổn định đáng tin cậy mới nên bảo vệ tác dụng phụ.

### Các nguyên tắc triển khai

| Chủ đề | Cách làm | Vì sao |
| --- | --- | --- |
| **Header không tin cậy** | Không dùng header người gọi tự khai báo để quyết định quyền truy cập hoặc chủ sở hữu dữ liệu | Header có thể bị giả mạo |
| **Validation** | Xác minh DTO, field bắt buộc và kiểu metadata trước khi thực hiện tác dụng phụ | Tránh ghi dữ liệu sai |
| **Idempotency** | Dùng khóa nghiệp vụ, unique constraint/transaction | Chịu được gửi lại, chạy song song |
| **Retry** | Chỉ thử lại lỗi tạm thời, có giới hạn và backoff | Tránh retry vô hạn dữ liệu sai |
| **Dead-letter / lỗi** | Cấu hình theo broker, binder và chính sách vận hành | Không làm mất hoặc lặp thông điệp vô kiểm soát |
| **Quan sát hệ thống** | Ghi eventId và correlationId đã được chuẩn hóa; tránh dữ liệu nhạy cảm | Theo dõi một xử lý qua nhiều dịch vụ |
| **Bất biến** | Không mutate Map headers đầu vào | MessageHeaders có thể là read-only |
| **Header propagation** | Chỉ copy metadata thực sự cần thiết | Tránh lộ header nội bộ qua hệ thống khác |

**Exception trong accept(...)** không tự quyết định cách HTTP map sang status code hoặc cách broker retry. Tầng adapter/binder và cấu hình xử lý lỗi mới quy định việc này. Đừng bắt toàn bộ exception rồi âm thầm bỏ qua khi muốn hệ thống truyền tải nhận biết lỗi.

Khi BiConsumer vừa cập nhật database vừa gọi API bên ngoài, có thể xuất hiện trạng thái chỉ một tác dụng phụ thành công. Nếu phải đảm bảo phát sự kiện sau khi ghi transaction, cân nhắc transactional outbox; với HTTP API bên ngoài, sử dụng idempotency key và cơ chế bù trừ phù hợp.

## 13. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| BiFunction có đối số thứ hai kiểu String/Integer không được nhận diện như mong đợi | Framework quy ước đối số thứ hai là Map headers | Dùng **Map<String, Object>**, gói nhiều field nghiệp vụ vào payload DTO |
| Đọc header ra null | Tên sai, không có header hoặc adapter không ánh xạ | Kiểm tra header thực tế bằng integration test |
| **ClassCastException** khi đọc header | Giả định mọi giá trị header đều là String | Kiểm tra kiểu bằng **instanceof** hoặc converter rõ ràng |
| **UnsupportedOperationException** khi **put** vào headers | Header map read-only | Tạo Message mới với header thay đổi |
| Header có ở input nhưng mất sau Function | Chưa có chiến lược propagation | Trả Message rõ ràng hoặc cấu hình copy-input-headers theo phiên bản |
| Tra cứu catalog như BiFunction rồi gọi hai tham số bị sai | Wrapper có thể nhận Message và được expose như Function | Phân biệt bean gốc và wrapper; kiểm thử qua catalog |
| Không tạo được output binding mong muốn | Dùng BiConsumer trả void cho pipeline cần phát dữ liệu | Dùng BiFunction/Function nếu nghiệp vụ cần output; xác minh binding thực tế |
| Ghi audit hai lần | Retry/redelivery, thiếu idempotency key | Dùng eventId ổn định + unique constraint ở storage |
| Header correlationId bị tin tưởng như danh tính | Nhầm metadata và thông tin xác thực | Dùng cơ chế authentication/authorization của môi trường |
| Unit test qua bean pass nhưng HTTP/Stream sai | Test chưa đi qua conversion hoặc message adapter | Bổ sung integration test cho payload, headers và binding |

## 14. Kiểm thử BiFunction và BiConsumer

### 14.1. Unit test trực tiếp: payload và headers

Ví dụ JUnit 5 dựa trên **HeaderFunctionApplication**:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;

class HeaderFunctionApplicationTest {

    private final HeaderFunctionApplication app =
        new HeaderFunctionApplication();

    private HeaderFunctionApplication.OrderEvent validEvent() {
        return new HeaderFunctionApplication.OrderEvent(
            "evt-001", "ORD-101", new BigDecimal("250000")
        );
    }

    @Test
    void biFunctionReadsCorrelationIdFromMap() {
        var summary = app.summarizeOrder();

        var result = summary.apply(
            validEvent(),
            Map.of("correlationId", "trace-123")
        );

        assertEquals("ORD-101", result.orderId());
        assertEquals("trace-123", result.correlationId());
    }

    @Test
    void biFunctionHandlesMissingHeader() {
        var result = app.summarizeOrder().apply(
            validEvent(),
            Map.of()
        );

        assertEquals("unavailable", result.correlationId());
    }

    @Test
    void biConsumerDoesNotDuplicateEventId() {
        var store = new HeaderFunctionApplication.AuditStore();
        var audit = app.auditOrder(store);

        audit.accept(validEvent(), Map.of("correlationId", "trace-123"));
        audit.accept(validEvent(), Map.of("correlationId", "trace-456"));

        assertEquals(1, store.size());
    }

    @Test
    void invalidEventDoesNotCreateSideEffect() {
        var store = new HeaderFunctionApplication.AuditStore();

        var invalid = new HeaderFunctionApplication.OrderEvent(
            "evt-002", "ORD-102", new BigDecimal("-1")
        );

        assertThrows(IllegalArgumentException.class,
            () -> app.auditOrder(store).accept(invalid, Map.of()));

        assertEquals(0, store.size());
    }
}
~~~

Các test trên xác nhận chữ ký Java, quy tắc xử lý header và side effect của hai bean; chúng **chưa khẳng định** framework tách Message thành hai đối số trong HTTP/Stream.

### 14.2. Integration test nên kiểm tra điều gì?

Một kiểm thử tích hợp cho Spring Cloud Function nên dựng Spring application context thật và gọi catalog hoặc adapter bằng **MessageBuilder.withPayload(...)** có header minh họa. Các điều cần xác minh:

1. Bean BiFunction/BiConsumer xuất hiện với **đúng tên** trong FunctionCatalog.
2. Wrapper nhận Message, ánh xạ **OrderEvent** vào payload và Map vào headers.
3. Header **correlationId** đi từ request/event tới đúng tham số thứ hai.
4. Payload JSON được deserialize đúng kiểu, cả khi thiếu field hoặc sai content type.
5. Kết quả BiFunction được serialize đúng; BiConsumer không bị hiểu sai là nguồn dữ liệu kết quả.
6. Với Stream, input binding, retry, idempotency và acknowledgment phù hợp binder thực tế.
7. Nếu dùng composition, header vẫn tồn tại sau từng bước theo hợp đồng mong muốn.

Chỉ khi đi qua adapter mới kiểm tra được độ chính xác của ánh xạ **payload + headers** từ giao thức bên ngoài. Điều này đặc biệt quan trọng khi nâng phiên bản Spring Boot/Spring Cloud Function hoặc đổi binder.

## 15. Thực hành củng cố

**Bài tập 1 — BiFunction có metadata.** Tạo **BiFunction<PaymentEvent, Map<String,Object>, PaymentSummary>**, đọc header **correlationId** và trả về mã giao dịch, tổng tiền, mã tương quan. Kiểm thử cả khi header thiếu.

**Bài tập 2 — BiConsumer ghi audit.** Tạo **BiConsumer<PaymentEvent, Map<String,Object>>** ghi audit vào store. Cùng **eventId** đi vào hai lần với correlationId khác nhau chỉ được ghi một lần. Giải thích vì sao không được dùng correlationId làm idempotency key trong tình huống này.

**Bài tập 3 — Message và propagation.** Chuyển bài tập 1 thành **Function<Message<PaymentEvent>, Message<PaymentSummary>>**. Chỉ giữ lại **correlationId**, thêm header **processedBy**, không sao chép các header nhạy cảm không cần thiết.

**Bài tập 4 — Phân biệt các loại hai đầu vào.** Một yêu cầu cần tính tổng từ **quantity** và **unitPrice**. Giải thích vì sao **BiFunction<Integer, BigDecimal, BigDecimal>** không phù hợp với quy ước payload+headers của Spring Cloud Function. Đề xuất DTO **PriceRequest(quantity, unitPrice)** và chữ ký Function hoặc BiFunction đúng.

**Bài tập 5 — Thay giao thức.** Giữ nguyên bean **auditOrder**. Viết cấu hình binding Spring Cloud Stream để nhận sự kiện từ broker; xác định các integration test cần có nếu chuyển sang serverless trigger, nhất là cách mapping correlationId và xử lý retry.

### Ghi nhớ

- Trong Java thuần, **BiFunction<T, U, R>** nhận hai đối số và trả **R**; **BiConsumer<T, U>** nhận hai đối số rồi trả **void**.
- Trong **Spring Cloud Function**, quy ước hỗ trợ là **BiFunction<T, Map, R>** và **BiConsumer<T, Map>**: **tham số thứ nhất nhận payload, tham số thứ hai nhận Map headers**.
- Framework có thể bọc bean để nhận **Message<T>**, tách payload và headers trước khi gọi. Cần phân biệt **bean gốc** với đối tượng tra cứu từ **FunctionCatalog**.
- Map headers dùng để đọc metadata; không tự sửa header đầu vào hoặc coi header do client gửi là dữ liệu xác thực.
- **BiFunction** phù hợp khi cần output; **BiConsumer** phù hợp cho tác dụng phụ. Bảo toàn header, composition, retry và idempotency phải được thiết kế theo adapter và nghiệp vụ.

### Tài liệu tham khảo

- [Spring Cloud Function — Programming model, mục BiFunction](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): quy tắc tách payload và Map headers cho BiFunction/BiConsumer.
