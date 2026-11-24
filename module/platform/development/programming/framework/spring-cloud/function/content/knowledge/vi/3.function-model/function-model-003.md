# Consumer<T>: xử lý dữ liệu và tác dụng phụ

Trong **SPRING_CLOUD_FUNCTION**, **Consumer<T>** biểu diễn một khối logic **nhận dữ liệu kiểu T, thực hiện công việc và không trả về kết quả nghiệp vụ**. Đây là mô hình phù hợp với các tác vụ như ghi nhật ký kiểm toán, lưu sự kiện, cập nhật trạng thái hay gửi thông báo. Spring Cloud Function cho phép khai báo logic này như một bean chức năng, đăng ký trong **FunctionCatalog** và sử dụng qua HTTP, hệ thống sự kiện hoặc adapter serverless tùy môi trường.

Bài học thuộc chương **Mô hình hàm**, tập trung vào câu hỏi cốt lõi: **Consumer xử lý dữ liệu ra sao, tác dụng phụ được kiểm soát thế nào, và cần làm gì khi cùng dữ liệu có thể được xử lý lại?**

## 1. Consumer<T> là gì?

Trong Java, **java.util.function.Consumer<T>** là một functional interface có phương thức trừu tượng **accept(T value)**:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
~~~

Ý nghĩa của hợp đồng:

- **T** là kiểu đầu vào mà Consumer nhận mỗi lần được gọi.
- **accept(T value)** thực hiện xử lý trên giá trị đó.
- **void** nghĩa là phương thức không trả kết quả để đưa vào bước kế tiếp; **không có nghĩa là xử lý chắc chắn thành công**.
- Mỗi lần gọi **accept(...)** có thể tạo tác dụng phụ: ghi database, gọi API, phát metric, lưu file hoặc gửi email.
- Consumer vẫn có thể ném exception. Bên gọi hoặc adapter sẽ quyết định cách xử lý lỗi.

Ví dụ Java thuần:

~~~java
import java.util.function.Consumer;

Consumer<String> audit = message ->
    System.out.println("AUDIT: " + message);

audit.accept("ORDER_CREATED");
// In ra: AUDIT: ORDER_CREATED
~~~

Lệnh in ra console là một **tác dụng phụ** (*side effect*): nó tác động tới môi trường bên ngoài lời gọi hàm, thay vì tạo một giá trị đầu ra.

### So sánh các mô hình trong Spring Cloud Function

| Giao diện | Chữ ký | Công việc chính | Ví dụ |
| --- | --- | --- | --- |
| **Supplier<R>** | () → R | Tạo dữ liệu | Sinh heartbeat |
| **Function<T, R>** | T → R | Biến đổi dữ liệu thành kết quả | Tính báo giá |
| **Consumer<T>** | T → void | Nhận và xử lý dữ liệu | Ghi lịch sử đơn hàng |

Nếu tác vụ cần trả về báo giá hoặc thông tin đã biến đổi, hãy cân nhắc **Function<T, R>**. Nếu muốn tiếp nhận sự kiện và ghi lịch sử mà không cần phát kết quả nghiệp vụ, **Consumer<T>** là lựa chọn tự nhiên.

## 2. Tác dụng phụ là gì và vì sao quan trọng?

Một hàm biến đổi thuần có thể tính kết quả chỉ dựa trên input, trong khi Consumer thường gây thay đổi bên ngoài:

~~~mermaid
flowchart LR
    A["OrderPlacedEvent"] --> B["Consumer.accept(event)"]
    B --> C["Ghi audit vào database"]
    B --> D["Tăng metric"]
    B --> E["Gọi dịch vụ ngoài"]
~~~

Những thay đổi này không nhất thiết cùng thành công. Ví dụ, database đã ghi xong nhưng lời gọi gửi email bị lỗi; nếu hệ thống thử lại **accept(...)**, sự kiện có thể bị ghi hai lần.

Vì vậy, thiết kế Consumer cần trả lời tối thiểu bốn câu hỏi:

1. **Tác dụng phụ nào là nguồn sự thật?** Chẳng hạn bản ghi đơn hàng đã hoàn tất trong database.
2. **Điều gì xảy ra nếu cùng sự kiện đến hai lần?** Có bỏ qua, cập nhật hay thực hiện lại?
3. **Làm sao phát hiện và xử lý thất bại?** Ném exception để adapter xử lý hay lưu kết quả lỗi ở nơi khác?
4. **Thứ tự và tính nguyên tử có quan trọng không?** Một bản ghi đã lưu nhưng thông báo chưa gửi là trạng thái được phép hay cần cơ chế bù trừ?

**Consumer không tự đảm bảo exactly-once, transaction hoặc retry.** Các thuộc tính đó phụ thuộc vào nghiệp vụ, kho dữ liệu và cơ chế truyền tải. Spring Cloud Function cung cấp hợp đồng gọi hàm; Spring Cloud Stream/binder hoặc HTTP adapter đảm nhiệm phần giao thức tương ứng.

## 3. Ví dụ hoàn chỉnh: tiếp nhận và ghi nhận sự kiện đơn hàng

Giả sử dịch vụ **order-audit** nhận sự kiện một đơn hàng đã được tạo. Mỗi sự kiện có mã riêng **eventId** để có thể nhận ra lần gửi trùng, mã đơn **orderId** và tổng tiền **total**.

Với một ứng dụng Spring Boot dùng Java 17+ và Spring Cloud Function có phiên bản tương thích, khai báo bean Consumer:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderConsumerApplication.class, args);
    }

    @Bean
    AuditStore auditStore() {
        return new AuditStore();
    }

    @Bean
    Consumer<OrderPlacedEvent> recordOrder(AuditStore store) {
        return event -> {
            validate(event);
            store.recordIfAbsent(event);
        };
    }

    static void validate(OrderPlacedEvent event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()
                || event.total() == null
                || event.total().signum() < 0) {
            throw new IllegalArgumentException("Invalid order event");
        }
    }

    public record OrderPlacedEvent(
        String eventId,
        String orderId,
        BigDecimal total
    ) {}

    public record AuditEntry(
        String orderId,
        BigDecimal total
    ) {}

    public static class AuditStore {
        private final ConcurrentMap<String, AuditEntry> entries =
            new ConcurrentHashMap<>();

        public boolean recordIfAbsent(OrderPlacedEvent event) {
            AuditEntry entry =
                new AuditEntry(event.orderId(), event.total());

            return entries.putIfAbsent(event.eventId(), entry) == null;
        }

        public int size() {
            return entries.size();
        }
    }
}
~~~

**Cách đọc ví dụ:**

- **recordOrder** là tên bean chức năng mà Spring Cloud Function có thể nhận diện và tra cứu.
- Kiểu **Consumer<OrderPlacedEvent>** nói rằng mỗi lần gọi phải cung cấp một sự kiện có cấu trúc.
- **validate(...)** từ chối dữ liệu không đúng hợp đồng trước khi tạo tác dụng phụ.
- **AuditStore.recordIfAbsent(...)** minh họa tránh ghi trùng bằng khóa **eventId**.
- Vì **accept(...)** trả về **void**, bên gọi không nhận được giá trị **boolean** của **recordIfAbsent(...)**. Hành vi thành công/thất bại được phản ánh qua tác dụng phụ hoặc exception.

**Giới hạn có chủ ý của ví dụ:** **AuditStore** dùng **ConcurrentHashMap trong bộ nhớ** để minh họa logic idempotent và kiểm thử, **không phải kho lưu trữ bền vững**. Dữ liệu mất khi ứng dụng khởi động lại và không được chia sẻ giữa các instance. Trong triển khai thật, cần thay bằng kho bền vững với ràng buộc duy nhất cho **eventId**, cơ chế giao dịch phù hợp và chính sách cho trường hợp cùng ID nhưng payload khác nhau.

### Chạy logic không cần HTTP hoặc broker

Hợp đồng Java cho phép gọi trực tiếp:

~~~java
var app = new OrderConsumerApplication();
var store = new OrderConsumerApplication.AuditStore();

Consumer<OrderConsumerApplication.OrderPlacedEvent> consumer =
    app.recordOrder(store);

consumer.accept(new OrderConsumerApplication.OrderPlacedEvent(
    "evt-1001", "ORD-1001", new BigDecimal("250000")
));

System.out.println(store.size()); // 1
~~~

Lời gọi **accept(...)** không cần giao thức truyền tải. Đây là lý do Consumer có thể tách biệt khỏi HTTP và messaging.

## 4. Kích hoạt Consumer qua HTTP

Một adapter HTTP có thể biến request thành input kiểu **OrderPlacedEvent**, sau đó gọi Consumer. Với ứng dụng Spring Boot có starter web của Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Khi ứng dụng chạy trên cổng 8080 mặc định và bean **recordOrder** được expose qua adapter web, có thể gửi:

~~~bash
curl -i -X POST http://localhost:8080/recordOrder \
  -H "Content-Type: application/json" \
  -d '{"eventId":"evt-1001","orderId":"ORD-1001","total":250000}'
~~~

Đường xử lý:

~~~text
HTTP request JSON
  -> HTTP adapter / conversion
  -> OrderPlacedEvent
  -> recordOrder.accept(event)
  -> AuditStore
  -> HTTP adapter hoàn tất response
~~~

Consumer **không trả về dữ liệu nghiệp vụ**. Vì thế không nên thiết kế client trông đợi một **OrderQuote**, một payload JSON kết quả, hay mặc định một mã HTTP cụ thể chỉ từ chữ ký Consumer. Mã trạng thái và cách ánh xạ exception phụ thuộc adapter, phiên bản framework và cấu hình ứng dụng.

Một endpoint thay đổi trạng thái nên dùng HTTP method phù hợp như **POST**, đồng thời có xác thực, phân quyền, kiểm tra request và cơ chế bảo vệ khi client gửi lại. Tránh đặt Consumer làm hành động thay đổi dữ liệu qua GET.

Nếu API bắt buộc trả một đối tượng kết quả theo hợp đồng nghiệp vụ, có thể cân nhắc một **Function<Request, Response>** hoặc một HTTP controller bao quanh tầng service. Không nên cố trả kết quả từ **Consumer<T>** bằng cách sửa đổi request body hoặc dùng trạng thái dùng chung.

## 5. Đăng ký, tìm và gọi bằng FunctionCatalog

Spring Cloud Function quản lý các bean **Supplier**, **Function**, **Consumer** qua **FunctionCatalog**, cho phép adapter gọi logic dựa trên tên hàm.

~~~mermaid
flowchart TD
    A["Spring bean: recordOrder"] --> B["FunctionCatalog"]
    C["HTTP adapter"] --> B
    D["Stream binder"] --> B
    E["Serverless adapter"] --> B
    B --> F["Consumer.accept(OrderPlacedEvent)"]
    F --> G["Tác dụng phụ: AuditStore"]
~~~

Để minh họa cách gọi từ mã Java trong cùng ứng dụng Spring:

~~~java
import java.util.function.Consumer;
import org.springframework.cloud.function.context.FunctionCatalog;

public class CatalogInvoker {
    private final FunctionCatalog catalog;

    public CatalogInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void invoke(OrderConsumerApplication.OrderPlacedEvent event) {
        Consumer<OrderConsumerApplication.OrderPlacedEvent> handler =
            catalog.lookup("recordOrder");

        if (handler == null) {
            throw new IllegalStateException("Consumer not found");
        }

        handler.accept(event);
    }
}
~~~

Để được Spring cấp **FunctionCatalog**, lớp gọi cần được đăng ký trong application context (chẳng hạn bằng **@Component** hoặc **@Bean**). Catalog có thể trả về wrapper có hỗ trợ chuyển đổi kiểu và composition; đừng giả định kết quả tra cứu có cùng lớp triển khai với lambda gốc.

Khi ứng dụng có nhiều bean chức năng, khai báo tường minh định nghĩa cần expose hoặc bind:

~~~yaml
spring:
  cloud:
    function:
      definition: recordOrder
~~~

Tên **recordOrder** phải khớp tên bean/định nghĩa chức năng. Tên sai, thiếu adapter hoặc cấu hình binding không phù hợp đều có thể khiến adapter không tìm được Consumer cần dùng.

## 6. Composition và giới hạn của Consumer

Java cung cấp **Consumer.andThen(...)** để thực thi hai Consumer theo thứ tự:

~~~java
Consumer<String> validateCode = code -> {
    if (code == null || code.isBlank()) {
        throw new IllegalArgumentException("Code must not be blank");
    }
};

Consumer<String> logCode =
    code -> System.out.println("Accepted: " + code);

Consumer<String> pipeline = validateCode.andThen(logCode);

pipeline.accept("ORDER_CREATED");
~~~

Consumer thứ hai chỉ chạy nếu Consumer thứ nhất kết thúc bình thường. Nếu bước đầu ném exception, bước sau không được thực thi. Tuy nhiên, nếu bước đầu đã tạo một tác dụng phụ rồi bước sau bị lỗi, **andThen không hoàn tác tác dụng phụ đầu tiên**.

Trong Spring Cloud Function, composition thường kết hợp một bước **Function<T, R>** để chuẩn hóa dữ liệu với một **Consumer<R>** ở cuối chuỗi.

Ví dụ thêm kiểu input thô và bean biến đổi:

~~~java
public record RawOrderEvent(
    String eventId,
    String orderId,
    String total
) {}

@Bean
java.util.function.Function<RawOrderEvent, OrderPlacedEvent>
        parseOrder() {
    return raw -> new OrderPlacedEvent(
        raw.eventId(),
        raw.orderId(),
        new BigDecimal(raw.total())
    );
}
~~~

Khai báo **RawOrderEvent** và **parseOrder** trong ngữ cảnh lớp cấu hình ứng dụng có sẵn **OrderPlacedEvent** và các import cần thiết. Sau đó chọn chuỗi:

~~~yaml
spring:
  cloud:
    function:
      definition: parseOrder|recordOrder
~~~

Dữ liệu đi theo thứ tự:

~~~mermaid
flowchart LR
    A["RawOrderEvent"] --> B["parseOrder"]
    B --> C["OrderPlacedEvent"]
    C --> D["recordOrder"]
    D --> E["AuditStore"]
~~~

**Vì Consumer không có đầu ra**, một Consumer nằm ở cuối pipeline **Function → Consumer** là hợp lý; không thể lấy output nghiệp vụ từ Consumer để truyền trực tiếp sang một Function tiếp theo. Kiểu đầu ra của **parseOrder** phải tương thích với kiểu đầu vào của **recordOrder**.

Ví dụ **parseOrder** này dùng **BigDecimal(String)** và có thể ném exception nếu chuỗi số tiền sai định dạng hoặc null. Trong ứng dụng thật nên xác định quy tắc validation, số lượng chữ số và thông báo lỗi phù hợp trước khi tạo tác dụng phụ.

## 7. Consumer trong hệ thống sự kiện với Spring Cloud Stream

Sử dụng **Consumer<T>** là cách phổ biến để xử lý **sự kiện đến mà không phát sự kiện đầu ra**. Với Spring Cloud Stream và binder tương ứng, có thể bind bean **recordOrder** với một topic hoặc queue.

~~~yaml
spring:
  cloud:
    function:
      definition: recordOrder
    stream:
      bindings:
        recordOrder-in-0:
          destination: orders.placed
          group: order-audit
~~~

Giải thích:

- **recordOrder-in-0** là tên binding input của Consumer **recordOrder**.
- **destination: orders.placed** chỉ định đích logic nhận sự kiện; cách ánh xạ phụ thuộc binder/broker.
- **group: order-audit** tạo danh tính nhóm consumer theo ngữ nghĩa binder tương ứng. Điều này có thể giúp các instance cùng nhóm cùng chia tải thay vì mỗi instance nhận mọi sự kiện.
- Không có **recordOrder-out-0**, bởi Consumer không tạo output binding nghiệp vụ.

Dòng xử lý:

~~~mermaid
flowchart LR
    A["Broker: orders.placed"] --> B["Stream binder"]
    B --> C["Message conversion"]
    C --> D["recordOrder.accept(event)"]
    D --> E["Audit database"]
~~~

Cấu hình trên chỉ là phần định tuyến. Ứng dụng còn cần **Spring Cloud Stream**, binder tương ứng (Kafka, RabbitMQ, v.v.), broker khả dụng và cấu hình kết nối. Để gửi kết quả sang một topic khác, **Function<T, R>** phù hợp hơn với mô hình một input/một output; Consumer dùng khi tác dụng phụ là đích xử lý cuối.

**Khác biệt với HTTP:** broker có thể gửi lại thông điệp khi lỗi, timeout, rebalance hoặc theo chính sách delivery của hệ thống. Consumer phải có cách xử lý lặp phù hợp; không thể kết luận mỗi sự kiện được gọi **accept(...)** chính xác một lần chỉ dựa vào cấu hình binding.

## 8. Consumer<Message<T>> khi cần header và metadata

Một Consumer bình thường chỉ cần payload nghiệp vụ:

~~~java
Consumer<OrderPlacedEvent> recordOrder
~~~

Nếu logic cần đọc correlation ID, tên nguồn hoặc header khác, có thể sử dụng:

~~~java
Consumer<org.springframework.messaging.Message<OrderPlacedEvent>>
~~~

Ví dụ bean xử lý message, bổ sung vào lớp cấu hình:

~~~java
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderPlacedEvent>> recordOrderMessage(AuditStore store) {
    return message -> {
        OrderPlacedEvent event = message.getPayload();
        Object correlationId =
            message.getHeaders().get("correlationId");

        validate(event);
        store.recordIfAbsent(event);

        // Sử dụng correlationId khi ghi log/tracing nếu cần.
        // Không coi header do bên gửi cung cấp là dữ liệu đã xác thực.
    };
}
~~~

**Message<T>** đóng gói **payload** và **headers**. Header hỗ trợ observability, routing hoặc xử lý nghiệp vụ nếu đã có hợp đồng dữ liệu rõ ràng. Tuy nhiên, broker và adapter có thể ánh xạ, lọc hoặc thay đổi cách biểu diễn header; không nên mặc định mọi header tự động được giữ nguyên giữa HTTP, Kafka, RabbitMQ và serverless.

Đặc biệt, **message ID do framework tạo** không thay thế mã idempotency nghiệp vụ **eventId**. Message có thể được tái tạo với metadata khác khi retry, trong khi tác dụng phụ liên quan đến cùng một sự kiện nghiệp vụ.

## 9. Idempotency: nền tảng để kiểm soát tác dụng phụ

Một Consumer được gọi hai lần với cùng sự kiện **không nên vô tình tạo hai bản ghi kiểm toán, hai lần trừ tiền hoặc hai email giống nhau**, nếu quy tắc nghiệp vụ yêu cầu chỉ thực hiện một lần.

Ví dụ thời gian:

~~~text
T1: Broker giao evt-1001 cho Consumer
T2: Consumer ghi audit thành công
T3: Xác nhận xử lý về broker bị gián đoạn
T4: Broker giao lại evt-1001
T5: Consumer kiểm tra eventId, bỏ qua thao tác ghi trùng
~~~

**Idempotency** là thuộc tính mà việc lặp lại một thao tác với cùng yêu cầu nghiệp vụ không tiếp tục làm thay đổi kết quả mong muốn sau lần thành công đầu. Trong ví dụ trong bộ nhớ, **putIfAbsent(eventId, entry)** chỉ ghi vào map khi khóa chưa tồn tại. Nhưng giải pháp thực tế cần bền vững:

| Bài toán | Phương án thường dùng | Lưu ý |
| --- | --- | --- |
| Ghi một bản ghi nghiệp vụ theo eventId | Unique constraint + INSERT có xử lý conflict | Ghi và đánh dấu xử lý nên nằm trong transaction thích hợp |
| Thực hiện chuyển tiền | Idempotency key tại dịch vụ giao dịch | Phải xác minh payload tương ứng và kết quả cũ |
| Gửi email hoặc gọi API bên ngoài | Idempotency key do dịch vụ đích hỗ trợ; lưu trạng thái gửi | Không có transaction chung tự động với database nội bộ |
| Cập nhật trạng thái đơn hàng | Version, trạng thái hợp lệ, optimistic locking | Tránh sự kiện cũ ghi đè sự kiện mới |
| Ghi audit | Bản ghi duy nhất theo ID sự kiện | Quyết định rõ cách xử lý cùng ID nhưng payload khác nhau |

Không nên xây giải pháp idempotency bền vững bằng cặp thao tác **SELECT rồi INSERT** tách rời mà thiếu ràng buộc duy nhất: hai consumer đồng thời vẫn có thể cùng đọc “chưa tồn tại” rồi cùng ghi. Cần dùng constraint/giao dịch hoặc thao tác nguyên tử do kho dữ liệu bảo đảm.

Khi Consumer vừa lưu database vừa gửi một sự kiện khác, cần cân nhắc **transactional outbox**: lưu trạng thái nghiệp vụ và bản ghi sẽ phát trong cùng transaction database, rồi có tiến trình riêng gửi ra broker. Điều này giảm nguy cơ “lưu thành công nhưng gửi thất bại”; hệ thống nhận vẫn nên hỗ trợ idempotency.

## 10. Lỗi, retry và dead-letter

Nếu **accept(event)** ném exception, Consumer không có giá trị trả về để tự mô tả lỗi. Adapter quyết định cách ánh xạ nó: request HTTP lỗi, broker retry, chuyển message vào dead-letter destination hoặc báo thất bại cho runtime serverless.

Phân biệt ba nhóm lỗi:

1. **Dữ liệu sai hợp đồng:** thiếu eventId, tổng tiền âm, JSON không đọc được. Thường không có ích nếu retry vô hạn cùng payload chưa thay đổi.
2. **Lỗi tạm thời:** database quá tải, dịch vụ ngoài timeout. Có thể retry có giới hạn và backoff.
3. **Lỗi nghiệp vụ có trạng thái:** đơn đã hủy, dữ liệu đến sai thứ tự, giao dịch đã xử lý. Cần chính sách rõ cho reject, bỏ qua, bù trừ hoặc ghi nhận lỗi.

Ví dụ Consumer có hành vi báo lỗi minh bạch:

~~~java
@Bean
Consumer<OrderPlacedEvent> strictRecordOrder(AuditStore store) {
    return event -> {
        validate(event);
        store.recordIfAbsent(event);
        // Nếu store ném exception vì lỗi hạ tầng,
        // cho phép adapter nhận biết và áp dụng chính sách lỗi.
    };
}
~~~

**Không nuốt mọi exception** bằng một khối **catch (Exception e)** chỉ để ghi log rồi kết thúc: từ góc nhìn của binder hoặc adapter, tác vụ có thể bị hiểu nhầm là thành công, làm mất cơ hội retry đúng cách.

Ngược lại, retry thiếu kiểm soát cũng có thể gây quá tải. Với Spring Cloud Stream, retry, dead-letter, acknowledgment và chính sách lỗi **phụ thuộc binder và cấu hình**; cần kiểm tra chính xác binder đang dùng trước khi đặt ngưỡng và điều kiện retry. Với HTTP, một exception trong Consumer cũng **không mặc định** trở thành một status cụ thể nếu chưa xác minh cách adapter ánh xạ lỗi.

### Phân biệt idempotency và transaction

- **Transaction** bảo vệ tính nhất quán của những thao tác có thể được quản lý trong cùng ranh giới giao dịch.
- **Idempotency** bảo vệ trước việc *lặp lại yêu cầu* hoặc *nhận lại cùng sự kiện*.
- **Retry** giúp hồi phục sau lỗi tạm thời nhưng đồng thời làm tăng khả năng tác dụng phụ bị thực thi lại.

Ba cơ chế hỗ trợ nhau và không thể tùy ý thay thế cho nhau.

## 11. Cùng Consumer trong môi trường serverless

Một runtime serverless có thể nhận payload, chuyển thành **OrderPlacedEvent**, tra cứu **recordOrder** qua FunctionCatalog rồi gọi **accept(event)** bằng adapter tương thích.

~~~text
Cloud event / invocation
  -> serverless adapter
  -> OrderPlacedEvent
  -> Consumer.accept(event)
  -> side effect (database, API...)
~~~

Hàm Java có thể được giữ nguyên, nhưng triển khai vẫn phải cấu hình handler, packaging, dependency, trigger, timeout và quyền truy cập tài nguyên cho nền tảng cụ thể.

Không dựa vào một **ConcurrentHashMap** ở bộ nhớ instance serverless để bảo vệ idempotency: instance có thể bị tạo mới, chạy song song, ngừng hoạt động hoặc không chia sẻ bộ nhớ. Với tác dụng phụ quan trọng, dùng kho lưu trữ bền vững có cơ chế đồng thời phù hợp.

Nếu handler nhận nhiều bản ghi trong một lần gọi, chính sách xử lý lỗi từng bản ghi, batch retry và xác nhận phải theo hợp đồng của adapter. Không có một quy tắc ack chung cho mọi môi trường serverless.

## 12. Consumer đồng bộ, bất đồng bộ và reactive

Ở dạng phổ biến **Consumer<OrderPlacedEvent>**, phương thức **accept(...)** chạy đồng bộ theo cách implement. Nếu bên trong Consumer thực hiện I/O chặn lâu, thời gian xử lý và thông lượng của adapter sẽ bị ảnh hưởng.

Cần phân biệt các dạng:

| Dạng Consumer | Hàm nhận gì? | Điều cần chú ý |
| --- | --- | --- |
| **Consumer<T>** | Một giá trị T | Timeout, blocking I/O, exception và concurrency |
| **Consumer<Message<T>>** | Payload và headers | Chuyển đổi metadata và header đáng tin |
| **Consumer<Flux<T>>** | Một publisher phản ứng | Phải quản lý subscription, lỗi và vòng đời luồng |

Với Project Reactor, có thể thấy chữ ký:

~~~java
Consumer<reactor.core.publisher.Flux<OrderPlacedEvent>>
~~~

Tuy nhiên, Consumer phản ứng **không trả publisher kết quả cho framework**. Nếu tự dùng **subscribe()** trong thân Consumer, cần chịu trách nhiệm về lỗi bất đồng bộ, lifecycle, hủy subscription và việc báo hoàn tất xử lý cho adapter. Những tác dụng phụ lâu dài chỉ dùng **doOnNext(...)** cũng cần được kích hoạt bằng subscription thích hợp; nếu không, pipeline có thể không chạy.

Nếu cần một pipeline reactive mà framework quản lý rõ luồng đầu ra và lỗi, cân nhắc **Function<Flux<T>, Flux<R>>** hoặc mô hình tích hợp reactive được adapter hỗ trợ, thay vì tự tạo subscription tùy tiện trong Consumer.

### Thread safety và trạng thái chia sẻ

Spring bean chức năng thường được tái sử dụng qua nhiều lần gọi, có thể ở các thread khác nhau. Đừng để **Consumer<T>** ghi vào một biến mutable không được đồng bộ hóa:

~~~java
// Không an toàn nếu nhiều thread gọi accept đồng thời:
int[] processed = {0};
Consumer<String> unsafe = value -> processed[0]++;
~~~

Với thống kê trong một instance có thể dùng **AtomicLong/LongAdder**, nhưng metric production nên tích hợp thư viện observability thích hợp. Với dữ liệu nghiệp vụ quan trọng, đồng bộ trong JVM cũng không giải quyết được nhiều instance: phải sử dụng concurrency control ở kho dữ liệu chung.

## 13. Kiểm thử Consumer và tác dụng phụ

Khác với Function trả kết quả, Consumer cần kiểm thử **trạng thái sau khi accept(...)** hoặc tương tác với dependency. Unit test không cần khởi động HTTP server hay broker.

Ví dụ JUnit 5 cho lớp **OrderConsumerApplication** đã định nghĩa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;

class OrderConsumerApplicationTest {

    private final OrderConsumerApplication app =
        new OrderConsumerApplication();

    private final OrderConsumerApplication.AuditStore store =
        new OrderConsumerApplication.AuditStore();

    private final Consumer<OrderConsumerApplication.OrderPlacedEvent> consumer =
        app.recordOrder(store);

    @Test
    void recordsOneEvent() {
        consumer.accept(event("evt-1"));

        assertEquals(1, store.size());
    }

    @Test
    void ignoresDuplicateEventId() {
        consumer.accept(event("evt-1"));
        consumer.accept(event("evt-1"));

        assertEquals(1, store.size());
    }

    @Test
    void rejectsInvalidEventWithoutRecordingIt() {
        var invalid = new OrderConsumerApplication.OrderPlacedEvent(
            "evt-2", "ORD-2", new BigDecimal("-1")
        );

        assertThrows(IllegalArgumentException.class,
            () -> consumer.accept(invalid));

        assertEquals(0, store.size());
    }

    private static OrderConsumerApplication.OrderPlacedEvent event(String id) {
        return new OrderConsumerApplication.OrderPlacedEvent(
            id, "ORD-1", new BigDecimal("250000")
        );
    }
}
~~~

Bộ kiểm thử minh họa ba hợp đồng:

- Event hợp lệ tạo đúng một bản ghi.
- Lặp lại cùng **eventId** không làm tăng số bản ghi trong store.
- Event sai không tạo tác dụng phụ.

Đây mới là kiểm thử ở mức **một instance, trong bộ nhớ**. Trước khi đưa vào production, cần kiểm thử tích hợp với database thật hoặc môi trường test phù hợp để xác minh unique constraint, transaction và hành vi khi nhiều instance ghi đồng thời. Với Spring Cloud Stream, bổ sung test cho input binding, content type, retry và xử lý message lỗi. Với HTTP, kiểm tra POST, lỗi payload và chính sách mã trạng thái. Với serverless, kiểm tra event mapping và hành vi trigger theo runtime cụ thể.

## 14. Những lỗi triển khai phổ biến

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không nhận sự kiện | Sai tên bean, function definition hoặc input binding | Kiểm tra **recordOrder**, **recordOrder-in-0**, binder và destination |
| HTTP gửi thành công nhưng không thấy dữ liệu bền vững | Consumer chỉ ghi vào bộ nhớ hoặc chưa có repository thật | Kiểm tra side effect và thay kho demo bằng kho bền vững |
| Cùng sự kiện tạo hai bản ghi | Broker redelivery, retry, thiếu khóa idempotency | Tạo unique constraint theo eventId, thiết kế xử lý trùng |
| Sự kiện lỗi bị mất âm thầm | Bắt exception rồi chỉ ghi log | Quy định rõ reject/retry và truyền lỗi cho adapter khi cần |
| Tác vụ chậm hoặc treo | **accept(...)** thực hiện I/O chặn lâu | Timeout, giới hạn đồng thời, đo latency và giám sát lỗi |
| Kết quả khác nhau giữa các instance | Dùng biến mutable hoặc bộ nhớ cục bộ làm nguồn sự thật | Chuyển trạng thái nghiệp vụ sang kho dùng chung |
| Mất metadata quan trọng | Chuyển **Message<T>** thành **T** mà quên lưu thông tin cần thiết | Định nghĩa hợp đồng header và giữ metadata ở tầng phù hợp |
| Hai tác dụng phụ chỉ thành công một phần | Không có transaction/outbox hay cơ chế bù trừ | Xác định ranh giới transaction, dùng outbox khi thích hợp |

## 15. Bài tập thực hành

**Bài tập 1 — Consumer cơ bản.** Tạo **Consumer<PaymentEvent>** lưu lịch sử thanh toán. Chọn một loại storage in-memory để làm demo, rồi viết unit test kiểm tra số bản ghi sau một và hai lời gọi với cùng **eventId**.

**Bài tập 2 — Validation và lỗi.** Bổ sung điều kiện mã giao dịch không được rỗng, số tiền phải lớn hơn 0. Kiểm thử event sai không để lại tác dụng phụ. Giải thích tại sao exception trong Consumer chưa đủ để bảo đảm HTTP luôn trả về một mã trạng thái mong muốn.

**Bài tập 3 — Composition.** Viết **Function<RawPaymentEvent, PaymentEvent>** để chuẩn hóa dữ liệu, nối với **Consumer<PaymentEvent>** bằng định nghĩa **parsePayment|storePayment**. Vẽ sơ đồ kiểu dữ liệu đi qua từng bước.

**Bài tập 4 — Message và tracing.** Định nghĩa **Consumer<Message<PaymentEvent>>**, đọc header **correlationId**, ghi log theo chuẩn dự án và vẫn dùng **eventId** trong payload làm idempotency key. Nêu rủi ro nếu tin tưởng tuyệt đối một header do client gửi.

**Bài tập 5 — Phân tích tình huống production.** Một Consumer ghi bản ghi database rồi gọi API gửi email. Database thành công, API timeout và broker giao lại sự kiện. Hãy thiết kế giải pháp đảm bảo không ghi trùng, phân biệt lỗi tạm thời với lỗi dữ liệu và đề xuất cách tránh mất email. Mô tả vai trò của unique constraint, idempotency key và transactional outbox.

### Ghi nhớ

- **Consumer<T>** có chữ ký **T → void**; phương thức **accept(T)** dùng để xử lý input, thường tạo tác dụng phụ.
- **Spring Cloud Function** đăng ký Consumer vào **FunctionCatalog** và cho phép adapter HTTP, Stream hoặc serverless kích hoạt cùng logic với cấu hình tương ứng.
- **Consumer không trả kết quả nghiệp vụ**; composition với Consumer nên kết thúc tại bước xử lý, chẳng hạn **Function<T, R> → Consumer<R>**.
- Với Consumer có tác dụng phụ, phải thiết kế **validation, idempotency, transaction, retry, xử lý lỗi và quan sát hệ thống** theo ranh giới thực tế.
- Unit test kiểm tra trạng thái/tương tác sau **accept(...)**; integration test xác minh conversion, binding, giao dịch và hành vi adapter.
