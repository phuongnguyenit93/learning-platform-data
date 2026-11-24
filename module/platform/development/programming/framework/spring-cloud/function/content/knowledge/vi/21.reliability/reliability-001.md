# Thiết kế hàm thuần và cô lập tác dụng phụ

## 1. Mục tiêu bài học

Spring Cloud Function cho phép xây dựng nghiệp vụ bằng các bean `Supplier`, `Function` và `Consumer`, sau đó ghép chúng bằng `FunctionCatalog` và dùng cùng logic qua Java, HTTP, hệ thống sự kiện hoặc serverless khi có adapter phù hợp. Tuy nhiên, ghép đúng cú pháp **không đồng nghĩa** pipeline đã đáng tin cậy. Một thao tác bị gọi lại sau timeout hoặc message được giao lại có thể làm dữ liệu bị ghi trùng.

Trong chương **Độ tin cậy**, bài học này giải thích cách giữ **logic tính toán thuần** và đặt **tác dụng phụ tại ranh giới được kiểm soát**. Mục tiêu là làm rõ đâu là công việc có thể tính lại, đâu là công việc phải xử lý retry, transaction và idempotency.

Sau bài học, bạn có thể:

- Nhận diện hàm thuần, trạng thái dùng chung và tác dụng phụ ẩn.
- Phân biệt tính thuần, tính xác định, idempotency và giao dịch.
- Thiết kế mô hình **Functional Core, Imperative Shell** trong Spring Cloud Function.
- Xây dựng Function thuần cho parse, validation và pricing.
- Đặt Consumer hoặc port ghi dữ liệu ở ranh giới, sau khi xử lý thành công.
- Kiểm thử core, cơ chế chống ghi trùng và composition qua `FunctionCatalog`.
- Đưa dữ liệu ngoài như thời gian, UUID, bảng giá thành input tường minh.
- Hiểu những giới hạn của retry, reactive subscription và adapter HTTP/message/serverless.

## 2. Hàm thuần và tác dụng phụ

Hàm thuần có hai đặc điểm:

1. Cùng input, cùng quy tắc thì cho cùng output.
2. Không sửa trạng thái bên ngoài hay tạo tác dụng phụ quan sát được qua lời gọi.

Ví dụ một hàm Java thuần:

~~~java
import java.util.function.Function;

Function<Integer, Long> calculateTotal =
        quantity -> quantity * 125_000L;

System.out.println(calculateTotal.apply(2)); // 250000
System.out.println(calculateTotal.apply(2)); // 250000
~~~

Hàm không phụ thuộc giờ hiện tại, database hay counter dùng chung.

Ngược lại:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

AtomicInteger sequence = new AtomicInteger();

Function<String, String> generateCode =
        prefix -> prefix + sequence.incrementAndGet();

System.out.println(generateCode.apply("ORD-")); // ORD-1
System.out.println(generateCode.apply("ORD-")); // ORD-2
~~~

Cùng `"ORD-"`, kết quả thay đổi vì hàm đọc và sửa `sequence`. Đây là một Function **không thuần**.

| Thao tác | Tính thuần | Lý do |
|---|---|---|
| `trim`, `toUpperCase(Locale.ROOT)` | Có thể thuần | Xử lý dựa trên input, không sửa bên ngoài |
| `Math.multiplyExact` | Thuần | Tính toán xác định, có thể ném lỗi khi tràn số |
| `Instant.now()` | Không thuần | Phụ thuộc thời điểm gọi |
| `UUID.randomUUID()` | Không thuần | Kết quả ngẫu nhiên nằm ngoài input |
| Đọc database/API bên trong hàm | Không thuần | Kết quả phụ thuộc trạng thái ngoài |
| `repository.save` hoặc gửi broker | Không thuần | Thay đổi hệ thống bên ngoài |
| Thay đổi mutable field của bean dùng chung | Không thuần | Lời gọi khác có thể quan sát thay đổi |
| Ghi log hoặc metrics | Side effect theo nghĩa nghiêm ngặt | Sinh output ngoài giá trị trả về |

Logging vẫn cần cho production. Ta không cần cấm mọi side effect, mà cần xác định rõ **nơi nào được phép có chúng**.

### 2.1. Hàm thuần vẫn có thể trả lỗi

~~~java
Function<String, Integer> parsePositive = text -> {
    int value = Integer.parseInt(text.trim());
    if (value <= 0) {
        throw new IllegalArgumentException("Quantity phai duong");
    }
    return value;
};
~~~

Hàm này không sửa dữ liệu bên ngoài. Với input không hợp lệ, lỗi là một phần hợp đồng đã biết. Nếu cần biểu diễn nhiều lỗi mà không ném exception, có thể dùng kiểu `ValidationResult<T>` hoặc `Either<Error,T>`.

### 2.2. Giao diện Function không tự bảo đảm tính thuần

Một `Function<Order,Quote>` có thể ngầm đọc database. Một `Supplier<String>` có thể lấy bản ghi từ queue. Một `Consumer<Quote>` có thể gửi sự kiện. Các giao diện Java quy định **input và output**, không kiểm tra bên trong có side effect hay không.

Đặc biệt, Spring Cloud Function cho phép tái sử dụng bean, không áp đặt rằng bean phải stateless hoặc deterministic. Người thiết kế phải tự bảo vệ các hợp đồng ấy.

## 3. Pure khác idempotent

**Pure:** cùng input cho cùng output và không thay đổi trạng thái ngoài.

**Idempotent:** gọi lại cùng thao tác không tạo thêm tác động sau lần đầu, theo trạng thái mà nghiệp vụ quan tâm.

Ví dụ:

~~~java
Function<Integer, Integer> addOne = value -> value + 1;
~~~

`addOne` là hàm thuần, nhưng `addOne(addOne(3)) = 5` khác `addOne(3) = 4`; nó không idempotent theo công thức toán học `f(f(x)) = f(x)`.

Trong khi đó, một `Consumer<Quote>` ghi bản ghi theo khóa `orderId` có thể **không thuần nhưng idempotent**: cùng báo giá được ghi lại không tạo bản ghi thứ hai.

| Đặc tính | Câu hỏi cần giải đáp |
|---|---|
| Pure | Hàm có đọc/sửa trạng thái ngoài input không? |
| Deterministic | Với cùng dữ liệu và quy tắc, kết quả có giống nhau không? |
| Idempotent | Thực thi lại cùng yêu cầu có thay đổi thêm trạng thái không? |
| Atomic | Những thay đổi có thành công hoặc thất bại cùng nhau không? |
| Delivery | Message có thể mất, giao trùng hay được retry không? |

Cần phân biệt những đặc tính này khi xây dựng hệ thống đáng tin cậy. `FunctionCatalog` và dấu `|` không tự mang lại transaction hoặc exactly-once.

## 4. Functional Core và Imperative Shell

Một cách tổ chức hữu ích là **Functional Core, Imperative Shell**.

~~~text
HTTP request / Message / Serverless event
                    |
                    v
           Imperative Shell
       deserialize, đọc context, auth
                    |
                    v
             Functional Core
      normalize → parse → validate → calculate
                    |
                    v
                 Quote
                    |
                    v
           Imperative Shell
       persist / publish / ack / response
~~~

Phần lõi thực hiện tính toán dựa trên input tường minh, còn lớp ngoài kết nối I/O, lấy thời gian, tạo ID, quản lý giao dịch và xử lý retry.

Trong Spring Cloud Function:

| Loại Java | Phương thức | Vai trò hay dùng | Có mặc định thuần? |
|---|---|---|---|
| `Supplier<T>` | `get()` | Lấy/tạo dữ liệu nguồn | Không |
| `Function<T,R>` | `apply(T)` | Biến đổi và tính toán | Không |
| `Consumer<T>` | `accept(T)` | Ghi/lưu/gửi kết quả | Không |
| `Runnable` | `run()` | Tác vụ không input/output | Không |

Dùng Function cho lõi thuần và Consumer cho bước cuối có side effect là một **quy ước thiết kế tốt**, chứ không phải điều Java hoặc framework tự cưỡng chế.

## 5. Ví dụ xuyên suốt: tính và ghi báo giá

Ta thiết kế chức năng nhận input:

~~~text
" ord-42, sku-7, 2 "
~~~

Luồng xử lý:

~~~text
String
   |
   v
normalizeOrder             Function<String,String>            (thuần)
   |
   v
parseOrder                 Function<String,OrderDraft>        (thuần)
   |
   v
validateOrder              Function<OrderDraft,ValidatedOrder>(thuần)
   |
   v
calculateQuote             Function<ValidatedOrder,Quote>     (thuần)
   |
   +-----------------------------+
   |                             |
   v                             v
Trả Quote                    recordQuote
                             Consumer<Quote>
                                  |
                                  v
                         QuoteRecorder (I/O)
~~~

Có hai nhu cầu: **chỉ tính báo giá** và **tính rồi lưu**. Cả hai dùng chung lõi; tác dụng phụ chỉ có trong nhánh thứ hai.

### 5.1. Mô hình dữ liệu

Dùng Java 17:

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderDraft(
            String orderId,
            String sku,
            int quantity) {}

    public record ValidatedOrder(
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

`OrderDraft` đã parse nhưng chưa xác thực; `ValidatedOrder` đã qua quy tắc; `Quote` là kết quả nghiệp vụ. Dùng record có ý nghĩa giúp phát hiện lỗi kiểu khi ghép và tránh truyền `Map<String,Object>` giữa mọi bước.

Record chỉ bất biến ở các field; nếu một record chứa mutable collection, vẫn cần copy phòng vệ. Đồng thời, tên `ValidatedOrder` không tự ngăn code bất kỳ tạo object sai; khi cần, hãy kiểm soát constructor/factory.

## 6. Định nghĩa các Function thuần

Ví dụ Spring Boot/Spring Cloud Function:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<String, String> normalizeOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Order input khong duoc null");
            }
            return raw.trim().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, OrderDraft> parseOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Order input khong duoc null");
            }

            String[] parts = raw.split(",", -1);
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                        "Can orderId,sku,quantity");
            }

            String orderId = parts[0].trim();
            String sku = parts[1].trim();

            final int quantity;
            try {
                quantity = Integer.parseInt(parts[2].trim());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Quantity phai la so nguyen", ex);
            }

            return new OrderDraft(orderId, sku, quantity);
        };
    }

    @Bean
    public Function<OrderDraft, ValidatedOrder> validateOrder() {
        return draft -> {
            if (draft == null
                    || draft.orderId() == null
                    || !draft.orderId().matches("ORD-[0-9]+")
                    || draft.sku() == null
                    || !draft.sku().matches("SKU-[0-9]+")
                    || draft.quantity() < 1
                    || draft.quantity() > 100) {
                throw new IllegalArgumentException(
                        "Don hang khong hop le");
            }

            return new ValidatedOrder(
                    draft.orderId(),
                    draft.sku(),
                    draft.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd);

            return new Quote(
                    order.orderId(),
                    order.sku(),
                    order.quantity(),
                    totalVnd);
        };
    }
}
~~~

Các Function không truy cập database, không dùng clock/randomness, không thay đổi state chia sẻ. Đơn giá cố định phục vụ bài học; với giá động, cần đưa snapshot giá vào input như mục sau.

Kết quả cho input `" ord-42, sku-7, 2 "`:

~~~text
Quote[orderId=ORD-42, sku=SKU-7, quantity=2, totalVnd=250000]
~~~

### 6.1. Vì sao loại bỏ side effect khỏi Function có ích?

- Có thể kiểm thử `calculateQuote` mà không chạy database/broker.
- Retry phép tính không tạo bản ghi mới.
- Có thể dùng cùng Function cho chế độ xem trước và chế độ ghi thật.
- Kết quả dễ so sánh giữa các lần xử lý nếu cùng input và policy.
- Khi có lỗi, xác định được bước nào thất bại trước ranh giới I/O.

## 7. Ghép lõi thuần bằng Java

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

QuoteFunctions config = new QuoteFunctions();

Function<String, String> normalize =
        config.normalizeOrder();
Function<String, OrderDraft> parse =
        config.parseOrder();
Function<OrderDraft, ValidatedOrder> validate =
        config.validateOrder();
Function<ValidatedOrder, Quote> price =
        config.calculateQuote();

Function<String, Quote> pipeline =
        normalize.andThen(parse)
                 .andThen(validate)
                 .andThen(price);

Quote result = pipeline.apply(" ord-42, sku-7, 2 ");
System.out.println(result.totalVnd()); // 250000
~~~

`andThen` thực hiện normalize → parse → validate → price. Java generic kiểm tra kiểu trung gian. Việc gọi trực tiếp các method `@Bean` ở đây chỉ minh họa Java thuần; trong Spring context, nên inject bean hoặc dùng `FunctionCatalog`.

### 7.1. Validation chạy trước khi ghi

Input `"ORD-42,SKU-7,0"` parse được nhưng thất bại ở `validateOrder`. Chừng nào bước ghi chỉ nằm sau validation thì đầu vào không hợp lệ chưa tạo side effect lưu báo giá.

Một pipeline làm ngược lại `recordRaw → validate → calculate` có thể ghi dữ liệu sai trước khi phát hiện lỗi. Nếu audit raw input là yêu cầu thật, cần tách audit thành một hành động có chính sách riêng, không để nó lẫn vào lõi thuần.

## 8. Cô lập ranh giới ghi bằng port

Định nghĩa một port I/O:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteRecorder {
    void record(Quote quote);
}
~~~

Consumer bean ủy quyền vào port:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteRecorderFunctions {

    @Bean
    public Consumer<Quote> recordQuote(QuoteRecorder recorder) {
        return recorder::record;
    }
}
~~~

Nhờ đó, `calculateQuote` không phụ thuộc repository, HTTP context hoặc broker. `QuoteRecorder` có thể được triển khai bằng JPA/JDBC, message producer hoặc bộ nhớ trong test.

Tuy nhiên, việc dùng một `Consumer` **không tự làm cho thao tác ghi idempotent**. Đó là trách nhiệm của port implementation và storage.

## 9. Ví dụ idempotency trong bộ nhớ

~~~java
package example.functions;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;

@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {

    private final ConcurrentHashMap<String, Quote> records =
            new ConcurrentHashMap<>();

    @Override
    public void record(Quote quote) {
        if (quote == null || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Quote va orderId phai ton tai");
        }

        Quote previous =
                records.putIfAbsent(quote.orderId(), quote);

        if (previous != null && !previous.equals(quote)) {
            throw new IllegalStateException(
                    "Cung orderId nhung du lieu khac");
        }
    }

    public Quote find(String orderId) {
        return records.get(orderId);
    }

    public int size() {
        return records.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

Hợp đồng trong một JVM:

| Yêu cầu | Hành vi |
|---|---|
| Ghi `ORD-42` lần đầu | Lưu một bản ghi |
| Ghi lại cùng Quote cho `ORD-42` | Không tăng số bản ghi |
| Ghi cùng ID nhưng nội dung khác | Báo conflict |
| Ghi `ORD-43` mới | Thêm bản ghi mới |

`putIfAbsent` là thao tác nguyên tử trong một `ConcurrentHashMap`, nhưng kho in-memory **không bền vững, không chia sẻ giữa nhiều instance và không bảo đảm transaction với broker**. Trong production, cần unique constraint/upsert nguyên tử/transaction theo storage thật.

Cũng không nên dùng cách `SELECT` kiểm tra tồn tại rồi mới `INSERT` nếu không có cơ chế uniqueness: hai replica có thể cùng thấy “chưa có” và cùng ghi.

## 10. Ghép phần thuần với Consumer qua FunctionCatalog

Bốn Function nghiệp vụ đã đăng ký có thể tạo một pipeline trả `Quote`:

~~~text
normalizeOrder|parseOrder|validateOrder|calculateQuote
    ⇒ Function<String, Quote>
~~~

Khi thêm `recordQuote` ở cuối, hợp đồng tổng thể thành `Consumer<String>`:

~~~text
normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote
    ⇒ Consumer<String>
~~~

Service Spring:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.Quote;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(String rawOrder) {
        Function<String, Quote> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return pipeline.apply(rawOrder);
    }

    public void processAndRecord(String rawOrder) {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay record pipeline");
        }

        pipeline.accept(rawOrder);
    }
}
~~~

`preview(...)` trả giá trị, không ghi; `processAndRecord(...)` tái sử dụng lõi rồi thực hiện side effect trong Consumer cuối. Giao diện của pipeline được xác định bởi **đầu vào của bước đầu và đầu ra của bước cuối**, không phải kiểu người viết tùy chọn trong code.

### 10.1. Vì sao Consumer nên đứng cuối?

Consumer nhận `Quote`, nhưng `accept(...)` trả `void`. Nó không cung cấp output để tiếp tục truyền sang Function khác.

Ví dụ chuỗi:

~~~text
calculateQuote|recordQuote|formatQuote
~~~

không có hợp đồng nối dữ liệu thông thường vì `recordQuote` không trả `Quote` cho `formatQuote`. Nếu nghiệp vụ vừa muốn ghi vừa muốn trả văn bản, hãy có một orchestration tường minh hoặc một Function có hợp đồng trả kết quả rõ và quản lý lỗi/transaction đúng cách.

### 10.2. FunctionCatalog không chứng minh tính thuần

`catalog.lookup("A|B|C")` chỉ tra cứu/ghép hàm theo tên và type metadata. Spring Cloud Function không biết một `Function` có lén gọi repository, đọc clock hay sửa static field hay không. Việc tách logic thuần là quyết định thiết kế và cần được duy trì bằng review/test.

Tương tự, việc Java compiler chấp nhận `andThen` không chứng minh rằng dữ liệu có đúng ý nghĩa nghiệp vụ, ví dụ `String` là order ID khác với `String` là email.

## 11. Chọn pipeline bằng spring.cloud.function.definition

Nếu ứng dụng muốn adapter sử dụng pipeline chỉ tính báo giá:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|parseOrder|validateOrder|calculateQuote"
~~~

Nếu adapter cần pipeline nhận dữ liệu và lưu:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote"
~~~

Dạng properties:

~~~properties
spring.cloud.function.definition=normalizeOrder|parseOrder|validateOrder|calculateQuote|recordQuote
~~~

Thuộc tính này **chọn chuỗi function** cho phần tích hợp; nó không tự tạo endpoint HTTP, topic Kafka, consumer group, trigger serverless, transaction, retry hoặc lịch chạy.

| Cách tiếp cận | Vai trò | Rủi ro cần xem xét |
|---|---|---|
| Java gọi `FunctionCatalog.lookup` | Tra cứu một pipeline theo tên | Tên bean, kiểu và runtime |
| HTTP adapter | Ánh xạ request/response | Timeout, client retry, mapping lỗi |
| Spring Cloud Stream | Kết nối message/binder | Redelivery, ack, content-type |
| Serverless adapter | Kết nối cloud trigger | Retry invocation, cold start |
| Supplier kết hợp pipeline | Chủ động tạo/lấy dữ liệu | Poll, duplicate, nguồn không có dữ liệu |
| Reactive Publisher | Luồng giá trị qua subscription | Resubscribe, backpressure, lỗi async |

Cùng logic thuần có thể tái sử dụng giữa những adapter đó, nhưng **độ tin cậy end-to-end** còn phụ thuộc vào cách adapter kích hoạt và xác nhận xử lý.

## 12. Đưa nguồn dữ liệu thay đổi vào input tường minh

Một Function có thể trông giống phép tính thuần nhưng phụ thuộc vào thời gian hoặc ngẫu nhiên:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Function;

// Receipt là kiểu domain được định nghĩa ở phần tiếp.
Function<String, Receipt> issue = raw ->
        new Receipt(UUID.randomUUID(), Instant.now(), raw);
~~~

Cùng `raw` nhưng có thể sinh ID và thời gian khác nhau. Hãy chuyển các yếu tố đó thành input:

~~~java
import java.time.Instant;
import java.util.UUID;

record ReceiptInput(
        String payload,
        UUID receiptId,
        Instant issuedAt) {}

record Receipt(
        UUID receiptId,
        Instant issuedAt,
        String payload) {}
~~~

Hàm thuần:

~~~java
Function<ReceiptInput, Receipt> buildReceipt =
        input -> new Receipt(
                input.receiptId(),
                input.issuedAt(),
                input.payload());
~~~

Ranh giới ngoài quyết định giá trị:

~~~java
UUID receiptId = UUID.randomUUID();
Instant issuedAt = Instant.now();

ReceiptInput input = new ReceiptInput(
        "ORD-42", receiptId, issuedAt);

Receipt result = buildReceipt.apply(input);
~~~

Khi `buildReceipt` nhận lại **cùng `ReceiptInput`**, kết quả xác định. Tuy nhiên, nếu lớp vỏ tự tạo UUID mới **ở mỗi lần retry**, toàn bộ quy trình vẫn không có kết quả cố định. Để retry đúng nghiệp vụ, idempotency key/receipt ID cần được ổn định hoặc tra cứu theo request gốc.

### 12.1. Giá và chính sách định giá là dữ liệu đầu vào

Giá bán có thể thay đổi qua database hoặc API. Không nên giấu thao tác đọc giá trong một Function rồi tuyên bố kết quả chỉ phụ thuộc `order`.

Một mẫu:

~~~java
record PricingInput(
        OrderModels.ValidatedOrder order,
        long unitPriceVnd,
        String priceVersion) {}

Function<PricingInput, OrderModels.Quote> priceWithContext =
        input -> new OrderModels.Quote(
                input.order().orderId(),
                input.order().sku(),
                input.order().quantity(),
                Math.multiplyExact(
                    input.order().quantity(),
                    input.unitPriceVnd()));
~~~

Lớp vỏ đọc snapshot giá và `priceVersion`, còn hàm chỉ tính dựa trên snapshot. Nếu cần audit/tái tính lịch sử, hãy lưu phiên bản chính sách và đơn giá đã dùng; model `Quote` trong ví dụ nên được mở rộng khi nghiệp vụ cần dữ liệu đó.

### 12.2. Một Function thuần có thể nhận cấu hình cố định

Đọc một cấu hình bất biến lúc khởi tạo bean rồi giữ trong closure có thể tạo Function xác định cho **cùng instance**. Nhưng nếu nghiệp vụ muốn kết quả giống nhau qua nhiều lần deploy với cấu hình khác, hãy lưu cả phiên bản cấu hình hoặc truyền rule snapshot vào input. Tính thuần không tự giải quyết versioning của quy tắc nghiệp vụ.

## 13. Ba thời điểm lỗi khác nhau

Xét:

~~~text
normalize → parse → validate → calculate → record → ack/response
                                  |             |
                                  |             +-- có thể mất xác nhận
                                  +-- chưa ghi
~~~

Các trường hợp:

1. **Lỗi trước Consumer:** validation hoặc tính toán thất bại; `recordQuote` chưa được gọi.
2. **Lỗi trong Consumer trước khi commit:** transaction/storage quyết định có rollback được không.
3. **Lỗi sau commit hoặc mất response/ack:** dữ liệu có thể đã ghi xong nhưng người gọi chưa biết; retry có thể chạy lại.

Một timeout ở HTTP hoặc broker **không chứng minh** rằng giao dịch chưa thành công. Đây là lý do cần cơ chế ghi idempotent tại storage, không chỉ dùng hàm thuần trước đó.

### 13.1. Không nuốt lỗi rồi giả vờ đã thành công

Ví dụ cần tránh:

~~~java
Consumer<OrderModels.Quote> unsafe = quote -> {
    try {
        recorder.record(quote);
    } catch (Exception ignored) {
        // Sai: che giau that bai.
    }
};
~~~

Ở đây `recorder` đại diện cho một `QuoteRecorder` được cung cấp bởi ứng dụng. Nếu Consumer nuốt lỗi, adapter có thể trả HTTP success hoặc xác nhận message dù dữ liệu chưa được lưu. Nên truyền lỗi tới cơ chế xử lý phù hợp hoặc diễn tả rõ trạng thái thất bại.

### 13.2. Retry phải theo loại lỗi

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Input không hợp lệ | Số lượng 0, SKU sai mẫu | Không retry vô hạn |
| Lỗi mạng tạm thời | Timeout kết nối database | Retry có giới hạn/backoff |
| Conflict idempotency key | Cùng ID nhưng payload khác | Trả conflict và điều tra |
| Không chắc commit hay chưa | Mất response sau commit | Tra cứu/tried lại qua key idempotent |

Retry vô hạn đối với validation error sẽ không làm input tự trở thành hợp lệ. Chính sách retry, dead-letter và acknowledgement phụ thuộc tầng transport/hạ tầng.

## 14. Transaction, retry và transactional outbox

Một luồng có hai tác dụng phụ:

~~~text
recordQuote (DB) → publish QuoteCreated (broker)
~~~

Nếu ứng dụng chết sau khi database commit nhưng trước khi publish, hệ thống sẽ lưu được Quote mà chưa phát sự kiện. Ngược lại, nếu publish thành công rồi việc xác nhận thất bại, message có thể được phát lại.

**Việc ghép các Consumer không tự tạo transaction phân tán.** Nếu cần nhất quán giữa cập nhật DB và phát sự kiện, một chiến lược phổ biến là transactional outbox:

~~~text
Trong cùng transaction database:
  - lưu Quote
  - lưu OutboxEvent cần phát
COMMIT
    |
    v
Outbox publisher đọc bản ghi chưa gửi
    |
    v
Broker
    |
    v
Consumer downstream kiểm tra duplicate
~~~

Outbox giữ được ý định phát ngay cả khi process dừng. Worker có thể phát lại khi có sự cố. Nhưng publisher/broker vẫn có thể giao cùng sự kiện nhiều lần; consumer phía nhận nên có idempotency theo event ID hoặc khóa nghiệp vụ.

### 14.1. Cần tách các phạm vi bảo đảm

- Pure core bảo đảm tính lại kết quả dễ kiểm chứng, không tự thay đổi storage.
- Repository/bảng dữ liệu bảo đảm uniqueness và atomic update.
- Transaction/outbox bảo vệ tính nhất quán giữa các thay đổi trong database.
- Broker/binder quyết định delivery, retry và acknowledgement.
- Consumer downstream xử lý duplicate theo hợp đồng nghiệp vụ.

Không có một lệnh `FunctionCatalog.lookup(...)` nào thay thế tất cả các tầng trên.

## 15. Reactive và side effect có thể lặp khi subscribe lại

Một Function thuần có thể được nâng thành biến đổi trên `Flux`:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<OrderModels.ValidatedOrder,
         OrderModels.Quote> priceOne =
        new QuoteFunctions().calculateQuote();

Function<Flux<OrderModels.ValidatedOrder>,
         Flux<OrderModels.Quote>> priceStream =
        flux -> flux.map(priceOne);
~~~

Với Publisher lạnh, mapper thường chạy khi có subscription. Nếu subscribe lại, tính toán có thể được thực hiện lại nhưng không tự ghi dữ liệu.

Ngược lại:

~~~java
// inputFlux va recorder la dependency minh hoa.
Flux<OrderModels.Quote> withWrite =
        inputFlux.map(priceOne)
                 .doOnNext(recorder::record);
~~~

Nếu có resubscription hoặc retry, `record` có thể chạy lặp lại. `doOnNext` chủ yếu thích hợp cho quan sát/side effect đồng bộ cần thiết; nó không phải cơ chế persistence/transaction mặc định đáng tin cậy.

Nếu `record` là I/O blocking, gọi nó trên event-loop có thể làm nghẽn luồng. Với I/O bất đồng bộ, hãy thiết kế adapter trả `Mono<Void>`/`Mono<Result>` tương ứng, dùng `flatMap`/`concatMap` với quản lý concurrency, lỗi, subscription và idempotency rõ ràng.

### 15.1. Những điều cần kiểm tra khi dùng Reactor

- `apply(...)` trả `Flux` có thể mới chỉ xây dựng pipeline; khi nào Publisher được subscribe?
- `retry` hoặc một subscription mới có kích hoạt lại tác dụng phụ không?
- Có cần giữ thứ tự phần tử bằng `concatMap` hay cho phép `flatMap` concurrent?
- Nếu Subscriber hủy, giao dịch đang chạy sẽ có trạng thái gì?
- Adapter Spring Cloud Function/Stream xử lý backpressure, ack và error signal như thế nào?

Hàm thuần giúp an toàn khi tính lại, nhưng **không làm cho side effect nằm trong reactive operator tự động an toàn**.

## 16. Không gắn side effect với tên Function một cách mơ hồ

Tên function nên bộc lộ trách nhiệm:

| Nên dùng | Tránh mơ hồ |
|---|---|
| `normalizeOrder` | `processStep1` |
| `validateOrder` | `checkThenSave` nếu mục tiêu chỉ kiểm tra |
| `calculateQuote` | `calculateAndPublish` khi cần lõi thuần |
| `recordQuote` | `handleData` |
| `loadPriceSnapshot` (adapter) | `calculateQuote` tự đọc database mỗi lần |

Khi code review, hãy hỏi: một người chỉ nhìn vào tên và generic của bean có thể đoán được nó **làm thay đổi dữ liệu bên ngoài hay không**? Nếu không, ranh giới đang thiếu rõ ràng.

## 17. Unit test cho lõi thuần

Vì lõi không phụ thuộc storage hoặc adapter, có thể test chỉ với JUnit 5, không cần khởi động Spring.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

class PureQuoteFunctionsTest {

    private final QuoteFunctions config =
            new QuoteFunctions();

    @Test
    void sameInputProducesSameQuote() {
        Function<String, String> normalize =
                config.normalizeOrder();
        Function<String, OrderDraft> parse =
                config.parseOrder();
        Function<OrderDraft, ValidatedOrder> validate =
                config.validateOrder();
        Function<ValidatedOrder, Quote> price =
                config.calculateQuote();

        Function<String, Quote> pipeline =
                normalize.andThen(parse)
                         .andThen(validate)
                         .andThen(price);

        Quote first = pipeline.apply(" ord-42, sku-7, 2 ");
        Quote second = pipeline.apply(" ord-42, sku-7, 2 ");

        assertEquals(first, second);
        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                first);
    }

    @Test
    void invalidQuantityIsRejected() {
        Function<OrderDraft, ValidatedOrder> validate =
                config.validateOrder();

        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(
                    new OrderDraft("ORD-42", "SKU-7", 0)));
    }
}
~~~

Bài test đầu xác minh tính xác định ở các input được chọn; nó không phải chứng minh toán học cho mọi input, nhưng dễ phát hiện khi sau này một developer vô tình thêm state mutable hoặc dependency bên ngoài.

Bài test thứ hai kiểm tra validation độc lập với database. Với logic quan trọng, có thể bổ sung parameterized test hoặc property-based test để kiểm tra nhiều bộ dữ liệu.

## 18. Unit test cho Recorder idempotent

Bộ test này nhắm vào ranh giới side effect, không trộn với logic tính giá:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class QuoteRecorderTest {

    @Test
    void repeatedRequestCreatesOneRecord() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "ORD-42", "SKU-7", 2, 250_000L);

        recorder.record(quote);
        recorder.record(quote);

        assertEquals(1, recorder.size());
        assertEquals(quote, recorder.find("ORD-42"));
    }

    @Test
    void conflictingPayloadIsRejected() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.record(new Quote(
                "ORD-42", "SKU-7", 2, 250_000L));

        assertThrows(IllegalStateException.class,
                () -> recorder.record(new Quote(
                    "ORD-42", "SKU-7", 3, 375_000L)));

        assertEquals(1, recorder.size());
    }
}
~~~

Đây là bằng chứng cho **một instance in-memory**, không chứng minh khả năng chịu lỗi của database nhiều replica. Đối với hệ thống thật, cần kiểm thử transaction và unique constraint dưới đồng thời, cũng như kịch bản process chết sau commit.

## 19. Integration test với FunctionCatalog

Unit test lõi không kiểm tra được tên bean hoặc khả năng ghép qua catalog. Tạo lớp Spring Boot chính:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

Đặt các lớp ví dụ trong package `example.functions` hoặc package con để component scan mặc định phát hiện, thêm Spring Cloud Function context và Spring Boot Test phù hợp.

Kiểm thử hai pipeline:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteRecorder recorder;

    @Test
    void purePipelineReturnsQuote() {
        Function<String, Quote> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder|calculateQuote");

        assertNotNull(pipeline);

        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                pipeline.apply(" ord-42, sku-7, 2 "));
    }

    @Test
    void repeatedRecordingIsIdempotent() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        assertNotNull(pipeline);

        pipeline.accept(" ord-77, sku-7, 2 ");
        pipeline.accept(" ord-77, sku-7, 2 ");

        assertEquals(
                new Quote("ORD-77", "SKU-7", 2, 250_000L),
                recorder.find("ORD-77"));
    }

    @Test
    void invalidInputDoesNotReachRecorder() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrder|parseOrder|validateOrder"
                + "|calculateQuote|recordQuote");

        assertNotNull(pipeline);

        assertThrows(IllegalArgumentException.class,
                () -> pipeline.accept("ORD-99,SKU-7,0"));

        assertEquals(null, recorder.find("ORD-99"));
    }
}
~~~

Những test sử dụng các khóa `ORD-42`, `ORD-77` và `ORD-99` khác nhau để tránh phụ thuộc đơn giản giữa các test. Với nhiều test song song hoặc context dùng chung, vẫn nên cô lập trạng thái bằng fixture/reset hoặc cấu hình isolation phù hợp.

### 19.1. Test điều gì ở từng tầng?

| Tầng | Test cần có | Điều chưa được chứng minh |
|---|---|---|
| Unit test core | Cùng input cho kết quả đúng, validation đúng | Chưa xác minh đăng ký tên bean |
| Unit test port | Một key không tạo trùng, conflict bị từ chối | Chưa chứng minh multi-instance/transaction |
| Integration test catalog | Ghép đúng tên, thứ tự và kiểu tổng thể | Chưa chứng minh binder/HTTP hoạt động |
| Integration test adapter | Payload, header, route, binding, ack/retry | Chưa bảo đảm toàn hệ thống không bao giờ lỗi |
| Resilience/fault test | Mất mạng, timeout, crash, race condition | Cần kết hợp giám sát vận hành |

Kiểm thử catalog phải kiểm tra **tác dụng phụ không xảy ra khi bước thuần thất bại**, không chỉ kiểm tra rằng exception được ném.

## 20. Checklist vận hành và các lỗi thiết kế thường gặp

### 20.1. Các lỗi thiết kế cần tránh

| Mẫu thiết kế chưa tốt | Rủi ro | Hướng cải thiện |
|---|---|---|
| `calculateQuote` gọi `repository.save` | Mỗi lần tính lại có thể ghi thêm | Tách Function tính và Consumer ghi |
| `calculateQuote` gọi `Instant.now()` | Kết quả không tái lập | Truyền timestamp qua input |
| `generateId` tạo UUID mới mỗi retry | Khó dedupe theo yêu cầu | Lưu idempotency key ổn định |
| `SELECT` rồi `INSERT` không unique | Race condition giữa replica | Uniqueness và ghi nguyên tử |
| `Consumer` nuốt exception | Adapter có thể ack sai | Phân loại, trả/lan truyền lỗi |
| Ghi DB rồi publish trực tiếp | Có thể commit DB nhưng mất event | Transactional outbox khi phù hợp |
| Side effect trong `Flux.map` | Retry/subscribe lại gây trùng | Cô lập I/O, idempotency, quản lý luồng |
| Coi `definition` là cấu hình broker | Thiếu binding/transport | Cấu hình adapter riêng |
| Dùng mutable field trong Function bean | Concurrent invocation có thể sai | Stateless hoặc đồng bộ rõ ràng |

### 20.2. Bảng hỏi trước khi đưa production

1. Các Function lõi có phụ thuộc trạng thái ẩn, clock, randomness hoặc I/O không?
2. Với cùng input và cùng phiên bản policy, có thể tái tính cùng kết quả không?
3. Validation có chạy trước side effect quan trọng không?
4. Tác dụng phụ có port/adapter được kiểm soát không?
5. Idempotency key có ổn định qua retry không?
6. Storage có uniqueness hoặc transaction phù hợp cho concurrent request không?
7. Cùng key nhưng payload khác được báo xung đột hay âm thầm ghi đè?
8. Nếu ghi DB thành công mà response/ack thất bại, có xử lý trùng an toàn không?
9. Nếu cần phát event, có chiến lược tránh mất event sau DB commit không?
10. Retry có giới hạn và phân biệt lỗi tạm thời/vĩnh viễn không?
11. `FunctionCatalog.lookup` đã được integration test trên phiên bản framework đang dùng chưa?
12. HTTP/event/serverless adapter có test serialization, content-type, headers và retry thực tế chưa?
13. Với reactive, subscription lại có làm lặp side effect không?

## 21. Bài tập thực hành

**Bài 1 — Nhận diện tính thuần.** Xem ba Function: tính `quantity * 125_000L`, tạo ID bằng `UUID.randomUUID()` và đọc giá từ database. Hàm nào thuần? Vì sao?

**Bài 2 — Refactor.** Một `Function<Order,Receipt>` vừa tính hóa đơn vừa gọi `repository.save`. Hãy tách phần thuần và phần side effect thành những giao diện Java có tên rõ ràng.

**Bài 3 — Pure hay idempotent?** Vì sao `addOne(x) = x + 1` là hàm thuần nhưng không idempotent theo `f(f(x))=f(x)`? Vì sao `saveOnce` có thể idempotent mà không thuần?

**Bài 4 — Thời gian và ID.** Một Function tạo `UUID.randomUUID()` và `Instant.now()` bên trong. Hãy chuyển chúng thành input và nêu điều cần lưu ổn định để retry một yêu cầu.

**Bài 5 — Composition.** Viết biểu thức catalog cho pipeline trả `Quote` và pipeline ghi Quote. Hai pipeline được gọi bằng phương thức nào?

**Bài 6 — Client retry.** Database đã commit nhưng response HTTP mất. Một client gửi lại cùng đơn hàng. Nếu code chỉ `INSERT`, có thể xảy ra điều gì? Nêu cách thiết kế idempotency key.

**Bài 7 — Concurrent worker.** Vì sao hai worker cùng làm `SELECT` rồi `INSERT` vẫn có thể ghi trùng? Hãy nêu giải pháp ở tầng database.

**Bài 8 — Outbox.** Giải thích vì sao lưu Quote rồi phát Kafka ở hai lệnh riêng có thể làm thiếu event. Outbox bảo vệ điều gì và còn nguy cơ gì?

**Bài 9 — Reactive.** Nếu `doOnNext(recorder::record)` được thực hiện lại do `retry` hoặc subscription mới, phải làm gì để không tạo tác dụng phụ trùng?

**Bài 10 — Lớp test.** Đề xuất một unit test core, một test port idempotent, một test catalog và một test binder. Mỗi loại giúp bắt lỗi gì?

### Gợi ý lời giải

- **Bài 1:** Phép tính số lượng với giá cố định thuần; UUID và đọc DB không thuần.
- **Bài 2:** `Function<ValidatedOrder,Receipt> calculate` và `Consumer<Receipt> record` hoặc port I/O do shell gọi.
- **Bài 3:** `addOne(addOne(x))` khác `addOne(x)`; `saveOnce` thay đổi storage lần đầu nhưng lần sau không thêm tác động.
- **Bài 4:** Dùng record có `receiptId` và `issuedAt`; ổn định idempotency key/ID theo yêu cầu qua retry.
- **Bài 5:** `"normalizeOrder|parseOrder|validateOrder|calculateQuote"` trả `Function<String,Quote>` và gọi `apply`; thêm `"|recordQuote"` trả `Consumer<String>` và gọi `accept`.
- **Bài 6:** Có thể ghi trùng; dùng key cố định, unique constraint hoặc ghi idempotent nguyên tử.
- **Bài 7:** Hai worker cùng quan sát “chưa có”; phải cưỡng chế uniqueness tại storage.
- **Bài 8:** Process có thể chết giữa commit DB và publish; outbox ghi ý định phát trong DB transaction, nhưng downstream vẫn cần dedupe.
- **Bài 9:** Thiết kế ranh giới ghi idempotent, quản lý retry/subscribe và concurrency đúng framework.
- **Bài 10:** Core test tính xác định; port test chống trùng; catalog test ghép tên; binder test delivery/ack/serialization.

## 22. Ghi nhớ

- **Hàm thuần** phụ thuộc input, không tự thay đổi hệ thống ngoài và cho kết quả xác định theo cùng quy tắc.
- `Supplier`, `Function` và `Consumer` là các hợp đồng Java về input/output, **không tự quy định tính thuần**.
- Mô hình **Functional Core, Imperative Shell** tách parse/validate/calculate khỏi clock, randomness, database, broker và transaction.
- Đặt side effect ở một port/Consumer cuối pipeline giúp rõ ranh giới kiểm thử; idempotency vẫn phải do implementation và storage thực hiện.
- Tính thuần và idempotency khác nhau. Lõi thuần có thể chạy lại, nhưng ghi dữ liệu cần cơ chế chống trùng.
- `FunctionCatalog` và `spring.cloud.function.definition` giúp ghép/chọn logic, không cung cấp transaction, exactly-once hay transport configuration.
- Với HTTP, sự kiện, serverless hoặc reactive, phải kiểm tra retry, ack, resubscription, error signal và giao dịch tại adapter thực tế.



