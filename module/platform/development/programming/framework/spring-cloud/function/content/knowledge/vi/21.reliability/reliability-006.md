# Tránh lặp tác dụng phụ khi dữ liệu được gửi lại

## 1. Mục tiêu bài học

Một sự kiện tạo đơn hàng có thể đến **hai lần** dù người gửi chỉ tạo **một yêu cầu nghiệp vụ**. HTTP client gửi lại `POST` sau timeout; message broker giao lại event khi chưa nhận acknowledgement; nền tảng serverless gọi lại invocation đã thất bại; hoặc người vận hành replay một message từ dead-letter queue. Nếu cùng một `Consumer` gửi email, trừ tiền, cấp quyền hay ghi thêm một bản ghi mới mỗi lần được gọi, dữ liệu sẽ mất nhất quán.

Trong module **SPRING_CLOUD_FUNCTION**, logic được tổ chức bằng `Supplier`, `Function`, `Consumer`, đăng ký vào `FunctionCatalog` và có thể ghép thành pipeline độc lập với cách kích hoạt qua HTTP, sự kiện hoặc serverless. Sự độc lập về giao thức **không** làm dữ liệu chỉ đến một lần; chính **ranh giới tác dụng phụ** phải được thiết kế để chịu được việc phát lại.

Bài thuộc chương **Độ tin cậy** và tập trung vào **tránh lặp tác dụng phụ khi dữ liệu được gửi lại**. Sau bài này, bạn có thể:

- Giải thích vì sao retry, redelivery, replay và reinvocation có thể lặp **một yêu cầu logic**.
- Phân biệt hàm thuần, idempotency nghiệp vụ và cơ chế deduplication.
- Chọn định danh xử lý ổn định, phân biệt `eventId`, `requestId`, `orderId` và `operationVersion`.
- Phát hiện trường hợp cùng idempotency key nhưng payload khác; không âm thầm ghi đè.
- Tổ chức `Function` thuần trước `Consumer` có side effect qua `FunctionCatalog`.
- Dùng unique constraint và transaction để chống hai instance cùng xử lý một event.
- Thiết kế transactional inbox/outbox, giới hạn bảo đảm của publish/ack, và xử lý lỗi sau commit.
- Kiểm tra hành vi HTTP, message binder, serverless và Reactor khi input được gọi lại.
- Viết unit test, integration test và thử nghiệm concurrency/crash windows.

> **Nguyên tắc xuyên suốt:** Không lấy “framework đã retry” hay “message có delivery guarantee” làm bằng chứng rằng side effect chỉ chạy một lần. Định nghĩa **một lần theo nghiệp vụ**, dùng khóa ổn định, lưu trạng thái ở nơi bền vững và kiểm chứng cả tình huống không biết commit đã thành công hay chưa.

## 2. Tại sao một thông điệp có thể được xử lý nhiều lần?

Xét một event được gửi đến Function:

~~~json
{
  "eventId": "evt-778",
  "orderId": "ORD-42",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

Một chuỗi sự cố phổ biến:

~~~text
Broker gửi event evt-778
       |
       v
Consumer nhận và tính báo giá
       |
       v
Database COMMIT thành công
       |
       v
Process dừng trước khi ACK
       |
       v
Broker không biết đã xử lý thành công
       |
       v
Broker giao lại evt-778
       |
       v
Consumer chạy lại toàn bộ logic
~~~

Nếu Consumer dùng `INSERT` không ràng buộc uniqueness hoặc gửi email vô điều kiện, cùng một yêu cầu có thể tạo nhiều tác dụng phụ.

### 2.1. Các đường vào khác nhau, cùng một rủi ro

| Nguồn gọi | Tại sao dữ liệu lặp? | Điều ứng dụng phải chịu được |
|---|---|---|
| HTTP/SDK | Client timeout và gửi lại `POST` | Cùng request key không tạo nghiệp vụ trùng |
| Kafka/RabbitMQ/broker | Chưa ack, rebalance, lỗi xử lý, at-least-once delivery | Giao lại cùng event |
| Serverless | Retry invocation, timeout, event source redelivery | Một event đến nhiều invocation/instance |
| Scheduler/poller | Quét lại dữ liệu chưa đánh dấu hoàn tất | Lấy lại cùng công việc |
| Operator replay | Chạy lại từ DLQ hoặc offset cũ | Event lịch sử xuất hiện trở lại |
| Reactor | `retry` hoặc subscriber mới kích hoạt lại cold Publisher | Callback có side effect chạy lại |

Không phải mọi adapter mặc định retry giống nhau. Ví dụ HTTP web adapter của Spring Cloud Function không tự làm mọi request được gửi một lần duy nhất; lỗi/timeout và việc client resend nằm ở ranh giới khác. Cần kiểm tra binder/trigger/version thực tế.

### 2.2. Lỗi sau commit là tình huống cần ưu tiên

Có ba thời điểm:

1. **Trước khi có side effect:** validation thất bại; chưa ghi gì.
2. **Trong giao dịch trước commit:** transaction có thể rollback.
3. **Sau commit nhưng trước ack/response:** side effect đã thành công, caller có thể nhìn thấy lỗi.

Trường hợp thứ ba khiến việc “catch exception rồi retry” nguy hiểm. **Timeout không chứng minh giao dịch chưa commit**.

## 3. Pure, idempotency, deduplication và exactly-once

Bốn khái niệm này dễ bị trộn lẫn:

| Khái niệm | Nghĩa | Ví dụ |
|---|---|---|
| Hàm thuần | Cùng input cho cùng output, không đổi trạng thái ngoài | Tính `total = quantity * unitPrice` |
| Idempotency nghiệp vụ | Gọi lại cùng yêu cầu không tạo thêm ảnh hưởng ngoài ý muốn | Ghi cùng Quote hai lần vẫn có một bản ghi |
| Dedupe | Nhận diện các lần lặp của cùng request/event | Kiểm tra `eventId` trong bảng đã xử lý |
| Exactly-once | Một phạm vi xử lý có các bảo đảm xác định về việc không lặp hiệu ứng | Phụ thuộc transaction và hệ thống được xét |

Ví dụ một `Function<Integer,Integer> addOne = x -> x + 1` là thuần, nhưng không idempotent theo công thức toán học `f(f(x))=f(x)`. Còn một `Consumer<Quote>` có thể không thuần nhưng idempotent nếu cùng key được lưu một lần.

**Không nên tuyên bố “Spring Cloud Function đảm bảo exactly-once”** chỉ vì dùng `FunctionCatalog`, `Consumer` hoặc một binder. Một số công nghệ cung cấp transactional/exactly-once semantics trong **phạm vi xác định**, chẳng hạn một số thao tác giữa topic trong Kafka, nhưng điều đó không tự mở rộng sang database độc lập, email, REST API hoặc nhà cung cấp thanh toán.

### 3.1. Khi nào dedupe là chưa đủ?

Giả sử Consumer kiểm tra một bảng `processed_events` rồi ghi vào bảng `quotes` bằng hai giao dịch riêng:

~~~text
Đánh dấu event đã xử lý  → COMMIT
Ghi Quote                → thất bại
~~~

Lần tiếp theo thấy event đã xử lý và bỏ qua. Kết quả: **không có Quote** dù event đã được đánh dấu hoàn tất.

Nếu đảo thứ tự:

~~~text
Ghi Quote                → COMMIT
Đánh dấu event xử lý      → process chết
~~~

Lần tiếp theo không thấy dấu và ghi lại Quote. Kết quả: **có thể ghi trùng**.

Vì vậy, dedupe an toàn cần đi cùng **ranh giới giao dịch và định nghĩa hoàn tất nghiệp vụ**, không chỉ một tập key đã nhìn thấy.

## 4. Xác định thế nào là “cùng một yêu cầu”

Một lựa chọn key sai có thể khiến hệ thống bỏ nhầm một operation hợp lệ hoặc xử lý lặp một operation cũ.

| Khóa | Ý nghĩa | Rủi ro nếu dùng sai |
|---|---|---|
| `eventId` | Một sự kiện được publish với định danh cụ thể | Nếu retry tạo event ID mới, không nhận ra cùng nghiệp vụ |
| `requestId` / `Idempotency-Key` | Một lời gọi logic từ client | Nếu client tạo key mới mỗi retry, không dedupe |
| `orderId` | Một aggregate/đơn hàng | Có thể chặn cập nhật hợp lệ của cùng đơn |
| `tenantId + orderId` | Khóa nghiệp vụ có phạm vi tenant | Tránh va chạm ID giữa tenant |
| `orderId + operation + version` | Một hành động cụ thể tại một phiên bản | Phù hợp khi cùng đơn có nhiều hành động theo thời gian |
| `payloadHash` | Dấu vân tay nội dung | Hai operation khác nhau có thể trùng payload |

Quy tắc cần thiết:

1. **Cùng yêu cầu gửi lại phải giữ nguyên key.**
2. Key phải đại diện đúng phạm vi nghiệp vụ, không chỉ định danh kết nối HTTP hay lần nhận message.
3. Cùng key, cùng payload: có thể coi là replay của cùng operation.
4. Cùng key, payload khác: báo **conflict**, không âm thầm overwrite hoặc xem là thành công.
5. Nếu một operation mới trên cùng đối tượng là hợp lệ, phải có key/operation version khác.

### 4.1. Minh họa phân biệt event ID và order ID

~~~text
evt-101: CreateOrder(ORD-42, quantity=2)
evt-101: CreateOrder(ORD-42, quantity=2)  ← redelivery, cần dedupe

evt-102: ChangeQuantity(ORD-42, quantity=3)
                                            ← nghiệp vụ khác, hợp lệ nếu version đúng

evt-103: CreateOrder(ORD-42, quantity=2)
                                            ← có thể là duplicate logic nhưng eventId mới
~~~

Nếu chỉ dedupe theo `eventId`, `evt-103` không bị chặn. Nếu chỉ dedupe theo `orderId`, có thể chặn nhầm `ChangeQuantity`. Cần cả **định danh event** để nhận biết delivery và **business constraint/version** để bảo vệ invariant của aggregate.

### 4.2. Có nên dùng hash của payload làm key?

Có thể dùng hash để so sánh payload của **cùng key**, nhưng không nên tự mặc định hash là toàn bộ định danh operation. Hai yêu cầu khác nhau có thể có nội dung giống nhau và vẫn cần được xử lý độc lập.

Khi tính fingerprint, cần:

- Định nghĩa canonical payload sau chuẩn hóa hợp lệ.
- Chọn các trường có ý nghĩa nghiệp vụ, không gồm timestamp mỗi lần nhận hoặc header transport thay đổi.
- Dùng serialization xác định, thứ tự field ổn định, xử lý số/locale/timezone nhất quán.
- Dùng thuật toán hash phù hợp và so sánh trong phạm vi key/tenant.
- Tránh log nguyên payload nhạy cảm hoặc sử dụng hash như một chứng cứ xác thực danh tính.

## 5. Chọn ranh giới chống lặp trong pipeline

Một pipeline thích hợp có thể chia thành lõi thuần và lớp I/O:

~~~text
Input event / HTTP request
           |
           v
Transport adapter (parse, auth, schema)
           |
           v
normalizeOrder            Function<OrderCommand, OrderCommand>
           |
           v
validateOrder             Function<OrderCommand, ValidatedOrder>
           |
           v
calculateQuote            Function<ValidatedOrder, Quote>
           |
           v
recordQuoteOnce           Consumer<Quote> + persistent dedupe
           |
           v
DB transaction / outbox / response-ack
~~~

**Các Function tính toán không cần có tác dụng phụ.** Nhưng chỉ để Consumer ở cuối chưa đủ. Consumer phải thực thi một thao tác lưu **idempotent** được storage bảo vệ.

### 5.1. Một ranh giới rõ giúp tái sử dụng

- HTTP có thể gọi `normalize|validate|calculate` để xem trước báo giá mà không ghi.
- Message Consumer có thể gọi cùng lõi rồi `recordQuoteOnce`.
- Serverless handler có thể gọi cùng hàm khi trigger đến.
- Retry của Function thuần dễ kiểm tra kết quả, còn retry của bước ghi được bảo vệ bằng key/transaction.
- Tầng adapter quyết định status/ack/DLQ, không nhúng vào `calculateQuote`.

### 5.2. Không đánh đồng Consumer với “chạy đúng một lần”

`Consumer<T>` chỉ định nghĩa `accept(T) -> void`. Nó không bắt buộc Java/Spring ghi nhớ các phần tử đã xử lý. Một Consumer gọi `repository.save` hai lần có thể tạo hai bản ghi trừ khi implementation/storage bảo vệ.

Tương tự, `FunctionCatalog.lookup("validateOrder|calculateQuote|recordQuoteOnce")` có thể ghép đúng tên, nhưng **không tự tạo bảng dedupe, transaction hoặc unique constraint**.

## 6. Dữ liệu ví dụ và quy tắc nghiệp vụ

Ta nhận một yêu cầu tạo báo giá:

~~~json
{
  "eventId": "evt-778",
  "tenantId": "shop-a",
  "orderId": "ORD-42",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

Yêu cầu nghiệp vụ:

- `eventId` ổn định khi cùng thông điệp được giao lại.
- `tenantId` đặt phạm vi cho `orderId` và idempotency.
- `orderId` xác định báo giá của một đơn cụ thể.
- `sku` đúng mẫu, `quantity` từ 1 tới 100.
- Đơn giá minh họa cố định `125_000 VND`.
- Cùng `tenantId + eventId` với cùng nội dung là replay.
- Cùng key với nội dung khác phải báo conflict.
- Cùng `tenantId + orderId` không được tạo hai báo giá không nhất quán.

### 6.1. Kiểu dữ liệu Java 17

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderCommand(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            Integer quantity) {}

    public record ValidatedOrder(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String eventId,
            String tenantId,
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

Dùng kiểu riêng `ValidatedOrder` giúp các bước sau biết dữ liệu đã qua kiểm tra. Record không tự bảo đảm mọi field hợp lệ nếu code khác gọi constructor trực tiếp; trong ứng dụng production, nên dùng factory/constructor kiểm tra bất biến hoặc đảm bảo các đường gọi được kiểm soát.

### 6.2. Các loại lỗi

~~~java
package example.functions;

public final class OrderErrors {

    private OrderErrors() {}

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class DuplicateConflictException
            extends RuntimeException {
        public DuplicateConflictException(String message) {
            super(message);
        }
    }

    public static class TransientStoreException
            extends RuntimeException {
        public TransientStoreException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Các loại lỗi giúp adapter phân biệt request sai, cùng key có payload khác và lỗi hạ tầng tạm thời. Không nên chuyển tất cả exception database thành `TransientStoreException`, vì unique violation, conflict hoặc bug không chắc phục hồi bằng retry.

## 7. Các Function thuần trong Spring Cloud Function

Khai báo bean `Function`:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@Configuration
public class OrderFunctions {

    private static String canonical(String raw) {
        return raw == null
                ? null
                : raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<OrderCommand, OrderCommand> normalizeOrder() {
        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        "OrderCommand khong duoc null");
            }

            return new OrderCommand(
                    input.eventId() == null
                        ? null : input.eventId().trim(),
                    input.tenantId() == null
                        ? null : input.tenantId().trim(),
                    canonical(input.orderId()),
                    canonical(input.sku()),
                    input.quantity());
        };
    }

    @Bean
    public Function<OrderCommand, ValidatedOrder> validateOrder() {
        return input -> {
            if (input == null
                    || input.eventId() == null
                    || input.eventId().isBlank()
                    || input.tenantId() == null
                    || input.tenantId().isBlank()
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.sku() == null
                    || !input.sku().matches("SKU-[0-9]+")
                    || input.quantity() == null
                    || input.quantity() < 1
                    || input.quantity() > 100) {
                throw new InvalidOrderException(
                        "OrderCommand khong hop le");
            }

            return new ValidatedOrder(
                    input.eventId(),
                    input.tenantId(),
                    input.orderId(),
                    input.sku(),
                    input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.eventId(),
                order.tenantId(),
                order.orderId(),
                order.sku(),
                order.quantity(),
                Math.multiplyExact(
                    (long) order.quantity(), 125_000L));
    }
}
~~~

Đơn giá cố định để nhấn mạnh tính xác định của phép tính. Nếu lấy giá từ database/API ở mỗi lần retry, cùng `OrderCommand` có thể cho tổng tiền khác nhau. Khi cần tái xử lý lịch sử nhất quán, đưa snapshot giá/quy tắc vào input hoặc lưu version đã áp dụng.

### 7.1. Vì sao tách normalize và validate?

Input có thể chứa `" ord-42 "` và `" sku-7 "`. Hàm normalize đưa chúng về dạng canonical, sau đó validate theo regex. Không tự sửa những giá trị sai nghiệp vụ thành một mã hợp lệ; normalize chỉ thực hiện biến đổi được hợp đồng cho phép.

### 7.2. Thứ tự quan trọng hơn việc gom tất cả vào một hàm

~~~text
normalize → validate → calculate → record
~~~

Nếu input thiếu event ID hoặc quantity bằng 0, `validateOrder` từ chối **trước khi bất kỳ Consumer ghi nào chạy**. Việc validation không thay thế dedupe nhưng giúp tránh ghi dữ liệu sai trong mỗi attempt.

## 8. Ghép lõi theo tên bằng FunctionCatalog

Tra cứu pipeline thuần:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;

@Service
public class QuotePreviewService {

    private final FunctionCatalog catalog;

    public QuotePreviewService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote preview(OrderCommand request) {
        Function<OrderCommand, Quote> core = catalog.lookup(
                "normalizeOrder|validateOrder|calculateQuote");

        if (core == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return core.apply(request);
    }
}
~~~

Hợp đồng tổng thể: `Function<OrderCommand,Quote>`. Cùng request, hàm thuần tạo cùng `Quote` và không tự lưu dữ liệu.

Khi thêm `Consumer<Quote> recordQuoteOnce` vào cuối, chuỗi:

~~~text
normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce
~~~

có hợp đồng dự kiến `Consumer<OrderCommand>`. Khả năng composition/runtime adaptation của từng hình thức hàm cần được xác minh bằng integration test trên phiên bản Spring Cloud Function đang dùng; chuỗi tên không thay thế kiểm tra kiểu và hoạt động thật.

### 8.1. Cấu hình definition không đồng nghĩa có dedupe

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce"
~~~

`spring.cloud.function.definition` lựa chọn tổ hợp hàm cho adapter. Nó **không bật sẵn** lưu idempotency key, unique constraint, retry/DLQ hay giao dịch. HTTP/Stream/serverless cần cấu hình vận chuyển phù hợp.

## 9. Một port cho ranh giới ghi idempotent

Thay vì để `calculateQuote` gọi repository trực tiếp, định nghĩa một port thể hiện **ý định ghi một lần theo nghiệp vụ**:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteRecorder {
    void recordOnce(Quote quote);
}
~~~

Bean `Consumer` gọi port này:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteRecordingFunctions {

    @Bean
    public Consumer<Quote> recordQuoteOnce(
            QuoteRecorder recorder) {
        return recorder::recordOnce;
    }
}
~~~

Lợi ích:

- `calculateQuote` không biết database, broker, retry hoặc transaction.
- Phần ghi có một giao diện rõ để gắn idempotency policy.
- Cùng Function thuần dùng được cho preview, test và workflow ghi thật.
- Có thể thay `QuoteRecorder` in-memory bằng JDBC/JPA mà không sửa logic tính giá.

**Port chỉ là hợp đồng:** Tên `recordOnce` không khiến implementation tự idempotent. Cần bằng chứng ở storage và test concurrent/replay.

### 9.1. Khi cùng key lặp nhưng dữ liệu khác

Một Recorder đúng không được viết:

~~~java
if (alreadyProcessed(eventId)) {
    return; // Chưa đủ nếu payload hiện tại khác payload trước.
}
~~~

Nếu attacker hoặc bug sử dụng lại `eventId` với nội dung khác, việc bỏ qua âm thầm có thể che dữ liệu không nhất quán. Quy tắc cần là:

~~~text
eventId chưa tồn tại
    → xử lý atomically và lưu fingerprint

eventId đã tồn tại + fingerprint giống
    → duplicate hợp lệ: không tạo side effect mới

eventId đã tồn tại + fingerprint khác
    → conflict: từ chối và cảnh báo/điều tra
~~~

Fingerprint nên được tính trên **trường canonical có ý nghĩa nghiệp vụ**, không gồm header redelivery, timestamp lần nhận hoặc offset transport có thể đổi.

## 10. In-memory Recorder để nhìn rõ semantics

Trước khi dùng database thật, ta có thể mô phỏng hai ràng buộc trong **một JVM**:

1. Một `tenantId + eventId` không được xử lý với hai payload khác nhau.
2. Một `tenantId + orderId` không được tạo hai báo giá có nội dung xung đột.

Để tránh race condition giữa hai bảng map trong một process, ví dụ dùng một `synchronized` method. Đây **không phải thiết kế production cho nhiều instance** và không lưu bền vững.

~~~java
package example.functions;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

@Profile("demo")
@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {

    public record EventKey(String tenantId, String eventId) {}
    public record OrderKey(String tenantId, String orderId) {}

    private final Map<EventKey, Quote> handledEvents =
            new HashMap<>();
    private final Map<OrderKey, Quote> quotes =
            new HashMap<>();

    @Override
    public synchronized void recordOnce(Quote quote) {
        if (quote == null
                || quote.eventId() == null
                || quote.tenantId() == null
                || quote.orderId() == null) {
            throw new IllegalArgumentException(
                    "Quote va identity khong duoc null");
        }

        EventKey eventKey = new EventKey(
                quote.tenantId(), quote.eventId());
        OrderKey orderKey = new OrderKey(
                quote.tenantId(), quote.orderId());

        Quote sameEvent = handledEvents.get(eventKey);

        if (sameEvent != null) {
            if (!sameEvent.equals(quote)) {
                throw new DuplicateConflictException(
                        "Event key tai su dung voi payload khac");
            }
            return;
        }

        Quote sameOrder = quotes.get(orderKey);

        if (sameOrder != null) {
            if (!sameBusinessQuote(sameOrder, quote)) {
                throw new DuplicateConflictException(
                        "Order da co Quote khac");
            }

            // Event ID mới nhưng cùng thao tác tạo Quote về mặt nghiệp vụ.
            // Không tạo bản ghi Quote thứ hai.
            handledEvents.put(eventKey, quote);
            return;
        }

        // Trong một JVM: cả hai map cùng dưới một lock.
        quotes.put(orderKey, quote);
        handledEvents.put(eventKey, quote);
    }

    private static boolean sameBusinessQuote(Quote a, Quote b) {
        return Objects.equals(a.tenantId(), b.tenantId())
                && Objects.equals(a.orderId(), b.orderId())
                && Objects.equals(a.sku(), b.sku())
                && a.quantity() == b.quantity()
                && a.totalVnd() == b.totalVnd();
    }

    public synchronized Quote find(
            String tenantId, String orderId) {
        return quotes.get(new OrderKey(tenantId, orderId));
    }

    public synchronized int quoteCount() {
        return quotes.size();
    }

    public synchronized int handledEventCount() {
        return handledEvents.size();
    }

    public synchronized void clear() {
        quotes.clear();
        handledEvents.clear();
    }
}
~~~

`sameBusinessQuote` không so sánh `eventId` vì hai event ID khác nhau có thể đại diện cho **cùng yêu cầu tạo Quote** sau khi bên phát sinh gửi lại bằng một ID mới. Đây là **quy tắc của ví dụ**, không phải kết luận rằng mọi event ID mới trên một order đều là duplicate. Trong ứng dụng cho phép cập nhật Quote, cần tách operation/version và không dùng cùng cách xử lý để bỏ qua cập nhật hợp lệ.

### 10.1. Bảng hành vi

| Lời gọi | Số Quote | Số event ID đã nhận diện | Hành vi |
|---|---:|---:|---|
| `evt-778, ORD-42, quantity=2` lần đầu | 1 | 1 | Lưu |
| Giao lại đúng `evt-778`, payload giống | 1 | 1 | No-op |
| `evt-778` nhưng quantity=3 | 1 | 1 | Conflict |
| `evt-779, ORD-42` cùng nghiệp vụ | 1 | 2 | No-op Quote, lưu event mới |
| `evt-780, ORD-42` với quantity=3 | 1 | 2 | Conflict |
| `evt-781, ORD-43`, quantity=2 | 2 | 3 | Lưu Quote khác |

Tất cả đều chỉ đúng trong một instance JVM. Nếu triển khai hai replica, mỗi replica có `HashMap` riêng; nếu process chết, dữ liệu mất. Không dùng lớp này làm bằng chứng idempotency production.

### 10.2. Tính nguyên tử trong process không thay transaction

`synchronized` bảo vệ các thread cùng JVM, nhưng không bảo vệ:

- Hai instance khác nhau.
- Crash hoặc restart giữa các thay đổi bền vững.
- Lệnh gửi email/broker ngoài map.
- Database commit và message acknowledgement.

Khi cần bảo đảm qua restart và nhiều replica, phải chuyển ranh giới chống lặp sang **storage giao dịch dùng chung**.

## 11. Thiết kế bảng inbox, Quote và outbox trong database

Đối với event-driven, **transactional inbox** là mẫu lưu dấu event đã được xử lý trong cùng transaction với tác dụng phụ database. Nếu còn publish event, **transactional outbox** lưu ý định phát cũng trong transaction đó.

Ví dụ lược đồ PostgreSQL minh họa:

~~~sql
CREATE TABLE processed_event (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE order_quote (
    tenant_id       VARCHAR(80) NOT NULL,
    order_id        VARCHAR(80) NOT NULL,
    sku             VARCHAR(80) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    total_vnd       BIGINT NOT NULL CHECK (total_vnd >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE outbox_event (
    outbox_id       UUID PRIMARY KEY,
    tenant_id       VARCHAR(80) NOT NULL,
    order_id        VARCHAR(80) NOT NULL,
    event_type      VARCHAR(80) NOT NULL,
    payload         JSONB NOT NULL,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Lược đồ này minh họa các ràng buộc quan trọng:

- `processed_event` có unique key `(tenant_id,event_id)` để dedupe cùng message.
- `payload_hash` giúp phát hiện **key giống nhưng nội dung khác**.
- `order_quote` có unique key `(tenant_id,order_id)` để bảo vệ nghiệp vụ tạo Quote.
- `outbox_event` có `outbox_id` ổn định cho downstream dedupe.

Đây là lược đồ học tập; production còn cần migration/index theo truy vấn, chiến lược retention, phân quyền, dữ liệu PII và cấu trúc trạng thái outbox phù hợp.

### 11.1. Câu lệnh nhận một event ID một cách nguyên tử

Trong PostgreSQL:

~~~sql
INSERT INTO processed_event (
    tenant_id,
    event_id,
    payload_hash
)
VALUES (:tenantId, :eventId, :payloadHash)
ON CONFLICT (tenant_id, event_id) DO NOTHING
RETURNING event_id;
~~~

Nếu câu lệnh trả một dòng, transaction hiện tại **đã claim được event key**. Nếu không có dòng, key đã tồn tại và ứng dụng cần đọc `payload_hash` đã lưu để phân biệt replay hợp lệ với conflict.

**Cần lưu ý concurrency:** Trong PostgreSQL, một insert đụng unique key đang được transaction khác giữ có thể chờ transaction kia commit/rollback rồi mới quyết định conflict. Hãy cấu hình timeout và xử lý lỗi database đúng policy. Không thay thế unique constraint bằng một bước `SELECT` trước `INSERT` độc lập.

### 11.2. Vì sao inbox và Quote phải commit cùng nhau?

Đặt trong một database transaction:

~~~text
BEGIN TRANSACTION

1. Claim (tenantId,eventId) bằng UNIQUE INSERT
2. Nếu duplicate:
     - so sánh payload hash
     - trả kết quả đã xử lý hoặc conflict
3. Nếu claim mới:
     - kiểm tra business constraint cho order
     - INSERT Quote nếu operation mới
     - INSERT OutboxEvent nếu cần phát event
4. COMMIT

Sau COMMIT mới ACK hoặc trả response theo adapter
~~~

Nếu transaction rollback vì lỗi ghi Quote hoặc outbox, claim trong `processed_event` cũng rollback; lần nhận lại sau đó có thể thử xử lý.

Nếu tất cả commit thành công mà process chết trước ACK, lần nhận lại thấy inbox và **không tạo Quote/outbox mới**.

### 11.3. Khi event khác ID nhưng cùng order

Inbox chỉ giúp nhận diện cùng `eventId`. Nếu một producer phát lại cùng operation bằng `eventId` mới, `processed_event` vẫn xem là event mới. Unique constraint ở `order_quote` sẽ ngăn tạo Quote thứ hai cho cùng `tenantId+orderId`.

Bước service phải xác định:

- Quote hiện có và nội dung **giống nghiệp vụ**: có thể coi là duplicate của create operation rồi đánh dấu event mới đã xử lý.
- Quote hiện có và nội dung **khác**: conflict; không ghi đè.
- Event là **operation cập nhật phiên bản mới**: xử lý theo hợp đồng update/version riêng, không áp dụng quy tắc create-only.

Không nên dựa duy nhất vào event ID để bảo vệ invariant của aggregate.

## 12. Ranh giới @Transactional trong Spring

Ví dụ service khái niệm cho database transaction:

~~~java
package example.functions;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

@Profile("prod")
@Service
public class TransactionalQuoteRecorder implements QuoteRecorder {

    private final ProcessedEventStore inbox;
    private final QuoteTable quotes;
    private final OutboxTable outbox;
    private final QuoteFingerprint fingerprint;

    public TransactionalQuoteRecorder(
            ProcessedEventStore inbox,
            QuoteTable quotes,
            OutboxTable outbox,
            QuoteFingerprint fingerprint) {
        this.inbox = inbox;
        this.quotes = quotes;
        this.outbox = outbox;
        this.fingerprint = fingerprint;
    }

    @Override
    @Transactional
    public void recordOnce(Quote quote) {
        String hash = fingerprint.of(quote);

        boolean claimed = inbox.insertIfAbsent(
                quote.tenantId(), quote.eventId(), hash);

        if (!claimed) {
            String stored = inbox.getFingerprint(
                    quote.tenantId(), quote.eventId());

            if (!hash.equals(stored)) {
                throw new DuplicateConflictException(
                        "Event key voi payload khac");
            }
            return; // Đã commit operation này ở lần trước.
        }

        // Kiểm tra/tạo theo unique key (tenantId, orderId).
        QuoteTable.InsertResult result =
                quotes.insertOrCompare(quote);

        if (result == QuoteTable.InsertResult.CONFLICT) {
            throw new DuplicateConflictException(
                    "Order da co Quote khac");
        }

        if (result == QuoteTable.InsertResult.CREATED) {
            outbox.insertQuoteCreated(quote);
        }

        // Nếu exception xảy ra, rollback mọi ghi ở trên.
        // Nếu commit, inbox + quote + outbox cùng có hiệu lực.
    }
}
~~~

Ở đây `ProcessedEventStore`, `QuoteTable`, `OutboxTable` và `QuoteFingerprint` là **các port/repository phải được triển khai** với SQL và transaction thật; ví dụ thể hiện luồng xử lý và điểm quyết định, không phải một ứng dụng có thể chạy ngay mà không bổ sung các adapter này.

Cần đảm bảo:

- Cả ba bảng dùng **cùng datasource/transaction manager** cho ranh giới này.
- `insertIfAbsent` thực hiện bằng ghi nguyên tử dựa trên unique constraint.
- `insertOrCompare` bảo vệ khóa business dưới concurrency; không dùng `SELECT` rồi `INSERT` không có constraint.
- `@Transactional` thực sự được Spring proxy áp dụng (không gọi qua `this.recordOnce(...)` bypass proxy).
- Exception gây rollback theo policy giao dịch; với Spring mặc định, unchecked exception thường kích hoạt rollback.
- Không gọi một dịch vụ remote từ giữa transaction rồi giả định nó rollback theo DB.

### 12.1. Một vấn đề quan trọng với duplicate chưa commit

Nếu event thứ hai đến trong lúc event thứ nhất **vẫn đang xử lý**, không thể trả “đã xử lý thành công” chỉ vì thấy một marker “đang chạy” được tạo sớm. Có thể cần đợi transaction kết thúc, trả `IN_PROGRESS` hoặc chọn cơ chế claim/lease có thể khôi phục.

Trong ví dụ transaction với unique key, các thao tác cạnh tranh phụ thuộc cơ chế khóa của database và có thể chờ commit/rollback. Nếu thiết kế tách trạng thái `RECEIVED/PROCESSING/DONE` thành nhiều transaction, phải có chính sách lease timeout và recovery khi worker chết giữa các bước.

### 12.2. Transaction không làm remote side effect trở thành atomic

Nếu `recordOnce` gọi thêm email API:

~~~java
@Transactional
public void recordOnce(Quote quote) {
    inbox.insert(...);
    quotes.insert(...);
    emailClient.send(...); // Remote API nằm ngoài DB transaction.
}
~~~

Đây là mã khái niệm về điều **nên tránh giả định**. Nếu email gửi thành công nhưng DB rollback, email đã phát mà inbox không lưu. Khi retry, email có thể gửi lại.

Nên đưa ý định gửi vào một bảng/outbox hoặc sử dụng provider hỗ trợ idempotency key, tùy yêu cầu nghiệp vụ. Transaction annotation không tạo giao dịch phân tán với mọi hệ thống ngoài.

## 13. Các port giao dịch và dấu vân tay payload

Trong ví dụ `TransactionalQuoteRecorder`, các phụ thuộc cần được triển khai bằng adapter JDBC/JPA. Hợp đồng có thể là:

~~~java
package example.functions;

public interface ProcessedEventStore {
    // INSERT theo unique key (tenantId,eventId).
    // Trả true khi insert thành công trong transaction.
    boolean insertIfAbsent(
            String tenantId, String eventId, String payloadHash);

    // Đọc fingerprint đã lưu cho cùng key.
    String getFingerprint(String tenantId, String eventId);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteTable {

    enum InsertResult {
        CREATED,
        ALREADY_PRESENT,
        CONFLICT
    }

    InsertResult insertOrCompare(Quote quote);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface OutboxTable {
    void insertQuoteCreated(Quote quote);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteFingerprint {
    String of(Quote quote);
}
~~~

Các interface giúp mô tả ranh giới. **Chúng không tự cung cấp SQL hoặc transaction**; phải có implementation bảo đảm constraint tại database thật.

### 13.1. Fingerprint phải xác định và có phiên bản

Không dùng `UUID.randomUUID()` làm fingerprint mỗi lần. Nên hash một cấu trúc canonical có các trường nghiệp vụ ổn định, ví dụ:

~~~java
record QuoteFingerprintInput(
        String tenantId,
        String orderId,
        String sku,
        int quantity,
        long totalVnd,
        String ruleVersion) {}
~~~

Implementation có thể serialize dạng ổn định rồi dùng SHA-256. Cần thống nhất thứ tự field, cách biểu diễn số, timezone và quy tắc chuẩn hóa.

Phân biệt ba loại:

- **Command fingerprint:** dữ liệu đầu vào của event, để phát hiện cùng event ID nhưng payload khác.
- **Business fingerprint:** kết quả nghiệp vụ, để phát hiện cùng order nhưng Quote khác.
- **Event identity:** định danh lần phát event để nhận biết redelivery.

Khi quy tắc tính giá đổi sau deploy, một event cũ replay có thể cho kết quả mới nếu cứ tính lại. Nếu cần replay chính xác, hãy lưu giá/rule version hoặc kiểm tra duplicate theo command key **trước khi chạy lại phần tính có thể đổi**.

### 13.2. Hai lớp uniqueness cần tách rõ

~~~text
(tenantId,eventId)             → nhận biết event bị giao lại
(tenantId,orderId,operation)   → bảo vệ invariant nghiệp vụ
~~~

Một event ID mới có thể là cùng thao tác create bị gửi lại. Một operation update hợp lệ trên cùng order không nên bị chặn chỉ vì order đã tồn tại: cần operation/version phù hợp.

### 13.3. Chỉ kích hoạt một implementation QuoteRecorder

`InMemoryQuoteRecorder` và `TransactionalQuoteRecorder` là hai **phương án thay thế**. Nếu cả hai cùng được Spring đăng ký, dependency injection có thể mơ hồ.

Có thể đánh dấu từng class bằng `@Profile("demo")` và `@Profile("prod")` hoặc dùng conditional bean để chỉ đăng ký một implementation tại một thời điểm.

~~~java
// Minh họa annotation cần gắn vào class hiện có:
@Profile("demo")
@Component
public class InMemoryQuoteRecorder implements QuoteRecorder {
    // Thân lớp ở mục 10.
}

@Profile("prod")
@Service
public class TransactionalQuoteRecorder implements QuoteRecorder {
    // Thân lớp ở mục 12.
}
~~~

Đây là ví dụ định hướng **gắn annotation**, không phải yêu cầu copy lại hai class song song. Trong integration test hãy bật profile demo hoặc cung cấp mock bean, còn production dùng implementation database.

## 14. Outbox vẫn có thể phát trùng

Transactional outbox giúp tránh **mất ý định publish** sau DB commit. Nó không tự bảo đảm broker chỉ nhận một message.

~~~text
COMMIT Quote + OutboxEvent
            |
            v
Worker đọc event chưa publish
            |
            v
Publish sang broker
            |
            v
Nhận xác nhận
            |
            v
Đánh dấu outbox đã publish
~~~

Nếu worker chết sau publish nhưng trước cập nhật trạng thái, worker khác có thể phát lại cùng event. Downstream phải chịu được duplicate bằng event ID ổn định và dedupe/idempotency của chính nó.

### 14.1. Lock và lease không loại bỏ crash window

Khi nhiều worker đọc outbox, có thể dùng row lock, lease hoặc `FOR UPDATE SKIP LOCKED` ở database hỗ trợ. Cách này tránh tranh chấp đồng thời nhưng **không loại bỏ được** cửa sổ publish thành công rồi chưa kịp ghi nhận.

### 14.2. Email và API ngoài không nằm trong DB transaction

~~~java
@Transactional
public void saveAndNotify(Quote quote) {
    repository.save(quote);
    emailClient.sendQuote(quote);
}
~~~

Đây là ví dụ về một giả định sai. Email có thể gửi thành công trong khi transaction rollback. Nếu retry, email có thể bị gửi lại. Có thể ghi yêu cầu gửi vào outbox hoặc truyền idempotency key cho nhà cung cấp nếu họ hỗ trợ. Gắn `@Transactional` không biến hai hệ thống thành một giao dịch nguyên tử.

## 15. Khi nào đánh dấu một event là DONE?

Mốc hoàn tất phụ thuộc yêu cầu nghiệp vụ:

| Yêu cầu | Điểm hoàn tất |
|---|---|
| Tính preview | Tính được và trả Quote |
| Lưu Quote | Transaction inbox + Quote commit |
| Lưu và phát event | Commit Quote + outbox; publish là bước riêng |
| Gửi email | Phân biệt queued, provider accepted, delivered |
| Cấp quyền hoặc thanh toán | Phải có trạng thái nghiệp vụ và provider idempotency |

### 15.1. PROCESSING không phải DONE

Một bảng idempotency đôi khi có trạng thái:

~~~text
RECEIVED → PROCESSING → DONE
                  |
                  +----> FAILED_RETRYABLE
                  |
                  +----> FAILED_FINAL
~~~

Nếu `PROCESSING` được commit riêng và worker chết, cần cơ chế lease/timeout/recovery. Khi request lặp thấy `PROCESSING`, không được tự coi nghiệp vụ đã hoàn tất; có thể chờ, trả trạng thái đang xử lý hoặc hẹn xử lý lại.

Nếu inbox marker và Quote đều commit trong một transaction ngắn, có thể tránh phải dùng nhiều trạng thái bền vững. Chọn thiết kế tùy thời gian I/O và yêu cầu phục hồi.

### 15.2. Replay sau khi rule thay đổi

Nếu event `evt-778` được replay sau một lần deploy cập nhật bảng giá, tính lại cùng command có thể cho Quote khác. Để ổn định:

1. Kiểm tra định danh/fingerprint command trước xử lý.
2. Nếu đã xử lý, lấy kết quả đã lưu thay vì tự tính lại theo rule mới.
3. Với event mới, lưu rule version/snapshot giá được dùng.
4. Phân biệt replay và thao tác tạo/cập nhật mới.

Vì Recorder trong ví dụ đơn giản nhận Quote **sau khi tính**, production có thể chuyển dedupe trước bước tính, hoặc bảo đảm input chứa snapshot quy tắc bất biến. Việc ngăn ghi trùng cần đi cùng khả năng tái tạo đúng kết quả.

## 16. Consumer lỗi và duplicate có ý nghĩa khác nhau

Một `Consumer<Quote>` cuối pipeline có thể:

- Kết thúc bình thường do lưu lần đầu.
- Kết thúc bình thường vì đã thấy cùng key, cùng payload và kết quả cũ đã commit.
- Ném `DuplicateConflictException` với cùng key nhưng payload khác.
- Ném lỗi hạ tầng nếu database tạm thời không sẵn sàng.
- Rơi vào tình huống **không rõ commit đã thành công chưa** khi mất kết nối.

Không nên viết:

~~~java
Consumer<Quote> unsafe = quote -> {
    try {
        recorder.recordOnce(quote);
    } catch (Exception ignored) {
        // Sai: adapter co the tuong da thanh cong.
    }
};
~~~

Nếu binder dùng kết quả Consumer để quyết định ACK, nuốt lỗi có thể làm mất event chưa xử lý. Trong khi đó, duplicate hợp lệ nên được coi là đã xử lý thành công (no-op) chứ không phải lỗi transient cần retry vô hạn.

### 16.1. Không tự tạo công việc async rồi bỏ qua kết quả

~~~java
Consumer<Quote> unsafeAsync = quote -> {
    asyncGateway.save(quote); // Bo qua completion/failure.
};
~~~

Khi `asyncGateway.save` trả một `CompletableFuture` hoặc Publisher, Consumer có thể trả về trước khi side effect hoàn tất. Hãy dùng hợp đồng bất đồng bộ được adapter hỗ trợ, hoặc theo dõi completion/error theo cách đúng với framework; không tự ý `subscribe()` rồi bỏ kết quả.

## 17. HTTP: Idempotency-Key khi client gửi lại POST

Một API có thể nhận request:

~~~http
POST /quotes HTTP/1.1
Content-Type: application/json
Idempotency-Key: req-3af9

{"orderId":"ORD-42","sku":"SKU-7","quantity":2}
~~~

Header `Idempotency-Key` là **hợp đồng do ứng dụng định nghĩa**, không phải chức năng tự bật của Spring Cloud Function. Server cần scoped key theo tenant/principal/operation, kiểm tra fingerprint và ghi lại kết quả để phục vụ lần resend.

### 17.1. Ba nhánh của một request

~~~text
Key mới
    → validate → tạo Quote → COMMIT key + Quote
    → trả response đầu tiên

Key cũ, cùng fingerprint
    → không ghi lại
    → đọc/trả kết quả đã lưu

Key cũ, fingerprint khác
    → conflict
    → không ghi đè và không phát side effect
~~~

Tùy API, server có thể trả `201` cho tạo mới, `200` khi đọc kết quả đã lưu hoặc replay nguyên response gốc; công việc bất đồng bộ có thể dùng `202`. Trạng thái cụ thể phải được ghi rõ trong hợp đồng, không mặc định từ Spring Cloud Function.

### 17.2. Sau commit nhưng trước response

~~~text
Client                      Server
    |                         |
    | POST key=K              |
    |------------------------>|
    |                         | COMMIT
    |        response bị mất X|
    |                         |
    | POST key=K              |
    |------------------------>|
    |                         | Tìm key đã commit
    |<------------------------|
    | nhận kết quả cũ         |
~~~

Nếu không có idempotency, HTTP client resend có thể tạo bản ghi mới hoặc gửi thông báo lần nữa. Nếu chỉ lưu key mà không giữ kết quả cần replay, server tránh được ghi trùng nhưng chưa chắc trả được response có nghĩa. Hãy thiết kế lưu trạng thái/kết quả trong cùng ranh giới commit khi cần.

### 17.3. Key không thay thế bảo mật

Một client không được đọc kết quả của tenant khác chỉ vì biết key. Phải kiểm tra authorization độc lập; phạm vi key nên bao gồm tenant, operation hoặc identity đáng tin cậy theo nghiệp vụ. Giới hạn kích thước/định dạng và không log key nhạy cảm tùy chính sách.

### 17.4. Cập nhật là operation khác

`POST CreateQuote(ORD-42)` và `PUT UpdateQuote(ORD-42,version=2)` là hai operation khác nhau. Không dùng một marker create để vô tình chặn update hợp lệ. Cần khóa/version và quy tắc chống ghi đè riêng.

## 18. Messaging: ACK sau khi lưu an toàn

Với Spring Cloud Stream, có thể dùng một bean Consumer đồng bộ gọi các Function thuần và port lưu:

~~~java
package example.functions;

import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class OrderMessageHandler {

    @Bean
    public Consumer<OrderCommand> receiveOrder(
            @Qualifier("normalizeOrder")
            Function<OrderCommand, OrderCommand> normalize,
            @Qualifier("validateOrder")
            Function<OrderCommand, ValidatedOrder> validate,
            @Qualifier("calculateQuote")
            Function<ValidatedOrder, Quote> calculate,
            QuoteRecorder recorder) {

        return raw -> {
            OrderCommand input = normalize.apply(raw);
            ValidatedOrder valid = validate.apply(input);
            Quote quote = calculate.apply(valid);
            recorder.recordOnce(quote);
        };
    }
}
~~~

Bean trên minh họa orchestration tường minh; nó dùng lại các Function nghiệp vụ. Trong ứng dụng dùng composition theo tên, có thể chọn biểu thức tương đương nhưng phải kiểm thử với phiên bản framework đang chạy.

### 18.1. Binding minh họa

~~~yaml
spring:
  cloud:
    function:
      definition: receiveOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: order-commands
          group: quote-service
~~~

Cần thêm binder, converter, retry, DLQ và cấu hình acknowledgement tùy broker/version. Property `definition` và `bindings` không tự tạo dedupe ở database.

### 18.2. Thứ tự hoàn tất

~~~text
Broker giao message
       |
       v
Deserialize và validate
       |
       v
DB transaction: inbox + Quote + outbox
       |
       v
COMMIT thành công
       |
       v
ACK theo chính sách binder
~~~

Nếu ACK trước commit và process chết, có thể mất công việc. Nếu ACK sau commit mà ACK thất bại, broker có thể giao lại; inbox/unique constraint giúp xử lý mà không tạo side effect mới.

Không mặc định tất cả binder ACK theo cách này. Cần integration test đúng Kafka/RabbitMQ, loại consumer, delivery semantics và cấu hình thực tế.

### 18.3. Duplicate hợp lệ được xử lý thành công

Khi event cũ đến lại với cùng fingerprint và dữ liệu trước đã commit, Recorder có thể kết thúc bình thường mà không ghi mới. Như vậy lần redelivery được coi là xử lý thành công, tránh retry vòng lặp cho một event đã hoàn tất.

Nếu cùng key nhưng payload khác, đó là conflict cần báo/cách ly theo policy, **không** được im lặng ACK như một duplicate bình thường.

### 18.4. Poison message khác transient failure

| Lỗi | Chính sách tham khảo |
|---|---|
| JSON/schema sai cố định | Adapter có thể từ chối/DLQ |
| Quantity 0 | Không retry vô hạn |
| DB connection timeout | Có thể retry giới hạn và idempotent |
| DB commit rồi mất ACK | Redelivery, no-op theo inbox |
| Payload khác cùng event ID | Conflict, quan sát và điều tra |

Cách DLQ, requeue, retry, ack và error channel hoạt động tùy binder/phiên bản. Consumer group hoặc partition không thay thế transaction và uniqueness khi xử lý redelivery.

## 19. Serverless: reinvocation trên một instance mới

Nền tảng serverless có thể gọi lại một event sau timeout hoặc lỗi, và lần gọi thứ hai có thể chạy trên instance khác.

~~~text
Event evt-778
    |
    v
Invocation 1 (instance A)
    |
    +-- DB COMMIT
    +-- timeout trước response
    |
    v
Platform gọi lại event
    |
    v
Invocation 2 (instance B)
    |
    +-- đọc inbox chung
    +-- duplicate hợp lệ → no-op
~~~

Bộ nhớ static hoặc HashMap ở instance A không bảo vệ instance B. Cần storage dùng chung, bền vững và idempotency key ổn định.

### 19.1. Event identity và business identity

Một trigger có thể cung cấp event ID riêng; cần kiểm tra schema thực tế. Nếu producer publish lại cùng business operation với event ID mới, dedupe theo event ID không đủ. Unique key theo tenant, order, operation/version vẫn cần thiết.

### 19.2. Retry lồng nhau và deadline

Application có thể retry I/O trong một invocation, còn cloud trigger có thể reinvoke cả handler. Không chọn khoảng backoff dài hơn thời gian còn lại; tổng attempts và deadline phải được kiểm soát. Idempotency bao phủ cả retry nội bộ lẫn invocation mới.

### 19.3. Đừng báo thành công trước khi side effect hoàn tất

Bắt mọi exception rồi trả success có thể làm mất operation chưa commit. Ngược lại, nếu commit đã thành công nhưng response thất bại, reinvocation cần tra cứu key và trả kết quả đã lưu thay vì ghi lại.

## 20. Reactor: resubscription có thể lặp side effect

Một Function thuần có thể được dùng trong Flux:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;

Function<OrderCommand, Quote> core = catalog.lookup(
        "normalizeOrder|validateOrder|calculateQuote");

if (core == null) {
    throw new IllegalStateException("Missing core");
}

Function<Flux<OrderCommand>, Flux<Quote>> quoteStream =
        flux -> flux.map(core);
~~~

Ở đây catalog là dependency được inject. Mapper thường thực thi khi subscription nhận phần tử, không phải lúc xây dựng pipeline.

Nếu thêm một tác dụng phụ:

~~~java
Flux<Quote> withWrite = inputFlux
        .map(core)
        .doOnNext(recorder::recordOnce);
~~~

Với cold Publisher, subscribe lại hoặc retry có thể gọi Recorder một lần nữa. `doOnNext` chỉ minh họa nguy cơ; không mặc định nó là cơ chế persistence transaction đáng tin cậy.

### 20.1. Retry toàn Flux phát lại phần tử trước lỗi

~~~java
Flux<Integer> values = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

Một subscriber có thể nhận:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

`retry(1)` subscribe lại toàn upstream. Nếu một Consumer đã ghi `1`, lần retry có thể ghi lần nữa.

### 20.2. Retry của từng inner Publisher

~~~java
Flux<Quote> result = inputEvents
        .concatMap(command ->
            service.process(command)
                .retryWhen(retryPolicy));
~~~

`inputEvents`, `service.process` và `retryPolicy` là dependency minh họa. Đặt retry ở inner Publisher để chỉ thử lại command hiện tại, tránh phát lại các item trước đó của outer Flux.

Nhưng cùng command vẫn có thể được ghi lại khi commit đã xong mà phản hồi mất; vì vậy `service.process` vẫn cần idempotency. Khi một inner Publisher hết lượt rồi lỗi, phải quyết định có kết thúc toàn stream hay cách ly message đó.

### 20.3. Không nuốt lỗi bằng Mono.empty một cách tùy tiện

Nếu đặt `onErrorResume(error -> Mono.empty())` trên mọi lỗi, adapter có thể xem message đã xử lý dù database chưa commit. Chỉ dùng kết quả rỗng khi nghiệp vụ cho phép bỏ qua và tầng transport có chính sách quarantine/ack phù hợp.

### 20.4. Consumer async tự subscribe có thể trả quá sớm

~~~java
Consumer<Flux<Quote>> unsafe = flux -> {
    flux.subscribe(recorder::recordOnce);
};
~~~

Nếu `accept` trả về khi Publisher còn chạy, binder có thể không thấy lỗi async để ACK/retry đúng. Cần tuân theo lifecycle và hợp đồng reactive của adapter.

### 20.5. Transaction reactive và JDBC khác nhau

Với R2DBC, reactive transaction manager gắn vào context của Publisher. Với JDBC blocking, transaction imperative thường dựa trên thread và proxy. Đừng mặc định `@Transactional` trên một method trả Mono sẽ tự bao phủ lời gọi JDBC chạy trên scheduler khác; phải kiểm chứng datasource, transaction manager, proxy và subscription thực tế.

## 21. Retry có giới hạn vẫn cần idempotency

Một lần retry duy nhất cũng có thể ghi trùng nếu lần đầu commit thành công nhưng response mất:

~~~text
Attempt 1: COMMIT thành công → timeout
Attempt 2: xử lý lại cùng key
~~~

Nếu storage có inbox/unique constraint, attempt 2 nhận diện replay và kết thúc no-op. Nếu không có, retry với backoff dài hay ngắn đều có thể tạo tác dụng phụ thứ hai.

### 21.1. Phân loại lỗi trước khi retry

| Lỗi | Hành động |
|---|---|
| Input invalid | Từ chối, không retry cùng payload |
| Cùng key nhưng payload khác | Conflict, không overwrite |
| DB tạm thời mất kết nối | Retry có giới hạn nếu idempotent |
| Không chắc commit đã thành công | Tra cứu key hoặc retry idempotent |
| Duplicate đã hoàn tất | No-op rồi kết thúc |
| Lỗi lập trình | Không dùng retry để che lỗi |

### 21.2. Retry riêng thao tác Recorder trong Reactor

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.util.retry.Retry;

Mono<Void> persisted = Mono.<Void>fromRunnable(
        () -> recorder.recordOnce(quote))
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(error ->
                error instanceof OrderErrors.TransientStoreException));
~~~

Ở đây `recorder` và `quote` là dependency được cung cấp. `Retry.backoff(2, ...)` cho tối đa hai lần retry thêm; `boundedElastic` cô lập lời gọi blocking, không tự làm JDBC non-blocking.

Bộ lọc không retry validation/conflict. Tuy nhiên, retry vẫn có thể gọi `recordOnce` sau một commit thành công mà mất xác nhận; idempotency tại storage là bắt buộc.

### 21.3. Không retry toàn bộ chuỗi phát event

Nếu workflow có `recordQuoteOnce` và `publishQuoteCreated`, một retry ở cuối có thể gọi lại cả hai. Quote có thể được dedupe nhưng message vẫn có thể phát trùng. Dùng outbox và downstream dedupe khi cần, thay vì cho rằng composition cung cấp giao dịch xuyên hai hệ thống.

## 22. Những cửa sổ lỗi cần kiểm thử

| Điểm hỏng | Trạng thái dự kiến | Kiểm tra cần làm |
|---|---|---|
| Trước validation | Chưa có side effect | Không có marker DONE |
| Sau validation, trước transaction | Chưa ghi | Retry không làm lặp side effect |
| Sau claim inbox, trước Quote nhưng chưa commit | Transaction có thể rollback | Marker cũng rollback |
| Sau Quote insert, trước outbox nhưng chưa commit | Transaction rollback | Không có Quote lẻ |
| Sau commit, trước ACK | Inbox, Quote, outbox đã có | Redelivery no-op |
| Sau publish, trước đánh dấu outbox | Broker có thể đã nhận | Publisher gửi lại cùng event ID |
| Hai worker cùng event ID | Race unique constraint | Một winner, không nhân Quote |
| Hai event ID cùng thao tác create | Inbox không nhận ra | Business uniqueness bảo vệ |
| Same event ID, payload khác | Dữ liệu xung đột | Conflict, không overwrite |
| Replay sau update rule | Giá tính lại khác | Snapshot hoặc kết quả cũ |
| Worker chết ở PROCESSING | Marker chưa DONE | Lease/recovery, không kẹt vĩnh viễn |

### 22.1. Transaction phải gắn với mốc hoàn tất

Nếu marker inbox ghi transaction A, còn Quote ghi transaction B, process chết giữa hai lần commit có thể để trạng thái không nhất quán. Hãy đảm bảo những thay đổi cần cùng thành công nằm trong một transaction thích hợp.

### 22.2. Không phải side effect nào cũng rollback được

Email đã gửi, một yêu cầu tới cổng thanh toán đã được chấp nhận hoặc event đã vào broker không tự rollback khi DB thất bại. Các thao tác này có thể cần provider idempotency, outbox, saga hoặc bù trừ, tùy nghiệp vụ.

### 22.3. Duplicate không nhất thiết là lỗi vận hành

Một event đã xử lý đúng được giao lại là trường hợp dự kiến trong at-least-once delivery. Có thể đo số duplicate và kết thúc no-op. Nếu số duplicate tăng bất thường, điều đó vẫn hữu ích để chẩn đoán mất ACK, retry storm hoặc lỗi producer.

## 23. Retention, TTL và replay từ lịch sử

Bảng `processed_event` không thể phát triển vô hạn mà không có chiến lược lưu giữ, nhưng xóa marker quá sớm lại khiến một event cũ được xử lý như mới.

### 23.1. Thời gian lưu key phải đủ dài

Retention cần xét:

- Thời gian tối đa broker có thể redeliver.
- Thời gian event nằm trong dead-letter/quarantine trước khi replay.
- Thời gian client có thể gửi lại request với cùng idempotency key.
- Yêu cầu audit/pháp lý và chính sách bảo vệ dữ liệu.
- Khả năng một producer gửi lại event cũ sau thời gian dài.

Nếu xóa marker sau một giờ mà event được replay sau bảy ngày, inbox có thể coi nó là mới. Lúc đó business unique constraint vẫn giúp chống trùng Quote, nhưng các side effect khác phải được bảo vệ độc lập.

### 23.2. Dedupe theo business key có thể cần sống lâu hơn event key

Với operation CreateQuote, unique key `tenantId + orderId` thường tồn tại cùng bản ghi Quote trong vòng đời nghiệp vụ, trong khi event marker có thể có TTL. Điều này cung cấp một lớp phòng vệ bổ sung khi replay rất muộn.

Với update/delete, cần version hoặc sequence và lưu đủ lịch sử để phân biệt thao tác mới với replay cũ. Không được chỉ coi mọi event trên cùng order là duplicate.

### 23.3. Xóa marker cũng là một thao tác cần kiểm soát

Việc cleanup cần tránh xóa marker đang dùng trong transaction hoặc đang có công việc chưa hoàn tất. Nếu dùng bảng trạng thái, phân biệt `DONE`, `FAILED_FINAL` và `IN_PROGRESS` trước khi archive. Không xóa marker chỉ vì nhìn thấy một lỗi transient.

### 23.4. Bảo mật dữ liệu dedupe

Chỉ lưu fingerprint/metadata cần thiết, không giữ payload cá nhân lâu hơn chính sách cho phép. Hash không tự làm dữ liệu vô danh; các giá trị thấp entropy có thể bị đoán. Cần quyền truy cập, mã hóa, logging hạn chế và retention phù hợp.

## 24. Unit test: giao lại cùng event không ghi trùng

Các test dưới đây dùng JUnit 5 với `InMemoryQuoteRecorder` để kiểm tra quy tắc nghiệp vụ. Chúng **không** chứng minh transaction của database production, nhưng giúp phát hiện việc thay đổi code vô tình làm sai semantics dedupe.

### 24.1. Ghi cùng một event hai lần

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class QuoteRecorderIdempotencyTest {

    @Test
    void sameEventIsRecordedOnlyOnce() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        recorder.recordOnce(quote);
        recorder.recordOnce(quote);

        assertEquals(1, recorder.quoteCount());
        assertEquals(1, recorder.handledEventCount());
        assertEquals(
                quote,
                recorder.find("shop-a", "ORD-42"));
    }
}
~~~

Test này thể hiện retry/redelivery **đúng event ID, đúng payload** là no-op ở lần xử lý sau.

### 24.2. Cùng event ID nhưng payload khác là conflict

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.DuplicateConflictException;

class ConflictingEventTest {

    @Test
    void sameEventIdWithDifferentPayloadIsRejected() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote original = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        Quote conflicting = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                3, 375_000L);

        recorder.recordOnce(original);

        assertThrows(DuplicateConflictException.class,
                () -> recorder.recordOnce(conflicting));

        assertEquals(1, recorder.quoteCount());
        assertEquals(1, recorder.handledEventCount());
        assertEquals(
                original,
                recorder.find("shop-a", "ORD-42"));
    }
}
~~~

Cùng key không đủ để kết luận là replay hợp lệ. Nếu payload thay đổi, không được im lặng bỏ qua hoặc overwrite.

### 24.3. Event ID mới, business operation giống nhau

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class NewEventSameBusinessOperationTest {

    @Test
    void newEventIdDoesNotCreateSecondQuote() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.recordOnce(new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        recorder.recordOnce(new Quote(
                "evt-779", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        assertEquals(1, recorder.quoteCount());
        assertEquals(2, recorder.handledEventCount());
    }
}
~~~

Đây là **quy tắc create-only của ví dụ**. Nếu một event mới đại diện cho update hợp lệ, phải có operation/version và test riêng, không gắn quy tắc này cho mọi thao tác trên order.

### 24.4. Hai tenant có cùng order ID

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class TenantScopedIdempotencyTest {

    @Test
    void tenantsWithSameOrderIdAreIndependent() {
        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        recorder.recordOnce(new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L));

        recorder.recordOnce(new Quote(
                "evt-778", "shop-b",
                "ORD-42", "SKU-7",
                2, 250_000L));

        assertEquals(2, recorder.quoteCount());
        assertEquals(2, recorder.handledEventCount());
    }
}
~~~

Test này cho thấy idempotency key phải được **scoped** theo tenant. Không dùng một ID do client tự nhập làm khóa toàn cầu nếu nhiều tenant có thể phát sinh cùng ID.

## 25. Unit test concurrent: hai worker cùng sự kiện

Chống duplicate trong một thread chưa đủ. Một hệ thống message/HTTP có thể xử lý đồng thời khi hai request đến gần nhau.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.Quote;

class ConcurrentDeduplicationTest {

    @Test
    void concurrentReplayStillCreatesOneQuote()
            throws Exception {

        InMemoryQuoteRecorder recorder =
                new InMemoryQuoteRecorder();

        Quote quote = new Quote(
                "evt-778", "shop-a",
                "ORD-42", "SKU-7",
                2, 250_000L);

        int workers = 12;
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                tasks.add(pool.submit(() -> {
                    try {
                        start.await();
                        recorder.recordOnce(quote);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }
                }));
            }

            start.countDown();

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertEquals(1, recorder.quoteCount());
            assertEquals(1, recorder.handledEventCount());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

`synchronized` trong Recorder khiến ví dụ này an toàn trong một process. Nhưng **hai instance JVM** không chia sẻ lock/map; test này không chứng minh production cross-instance. Với database, cần test hai transaction đồng thời cùng insert key và kiểm tra unique constraint/rollback thật.

### 25.1. Test thêm tình huống concurrent conflict

Với hai worker cùng `eventId` nhưng một payload quantity 2 và payload kia quantity 3, chỉ một giá trị có thể thành công; yêu cầu còn lại phải conflict và không ghi đè. Kết quả thắng có thể phụ thuộc thứ tự scheduling, nên test không nên hard-code rằng worker A luôn thắng.

### 25.2. Lock application không thay unique constraint

Một `synchronized` block trong Java không ngăn instance B xử lý cùng event. Ngay cả distributed lock cũng cần cân nhắc lease expiry, fencing token và recovery. Với trạng thái nghiệp vụ nằm trong relational database, unique constraint/transaction thường là tuyến phòng thủ quan trọng.

## 26. Integration test FunctionCatalog và Consumer

Tạo Spring Boot application cùng package với các bean ví dụ:

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

Với profile `demo` cho `InMemoryQuoteRecorder` và Spring Cloud Function context, có thể test tổ hợp theo tên:

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
import org.springframework.test.context.ActiveProfiles;

import example.functions.OrderModels.OrderCommand;
import example.functions.OrderModels.Quote;
import example.functions.OrderErrors.InvalidOrderException;

@SpringBootTest(classes = QuoteApplication.class)
@ActiveProfiles("demo")
class QuoteCatalogReplayTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteRecorder recorder;

    @Test
    void purePipelineReturnsQuote() {
        Function<OrderCommand, Quote> core = catalog.lookup(
                "normalizeOrder|validateOrder|calculateQuote");

        assertNotNull(core);

        Quote output = core.apply(new OrderCommand(
                "evt-801", "shop-a",
                " ord-801 ", " sku-7 ", 2));

        assertEquals(250_000L, output.totalVnd());
        assertEquals("ORD-801", output.orderId());
    }

    @Test
    void redeliveryDoesNotCreateSecondQuote() {
        Consumer<OrderCommand> pipeline = catalog.lookup(
                "normalizeOrder|validateOrder"
                + "|calculateQuote|recordQuoteOnce");

        assertNotNull(pipeline);

        OrderCommand command = new OrderCommand(
                "evt-802", "shop-a",
                "ORD-802", "SKU-7", 2);

        pipeline.accept(command);
        pipeline.accept(command);

        assertEquals(
                new Quote(
                    "evt-802", "shop-a",
                    "ORD-802", "SKU-7", 2, 250_000L),
                recorder.find("shop-a", "ORD-802"));
    }

    @Test
    void invalidDataDoesNotReachRecorder() {
        Consumer<OrderCommand> pipeline = catalog.lookup(
                "normalizeOrder|validateOrder"
                + "|calculateQuote|recordQuoteOnce");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(new OrderCommand(
                    "evt-803", "shop-a",
                    "ORD-803", "SKU-7", 0)));

        assertEquals(null, recorder.find(
                "shop-a", "ORD-803"));
    }
}
~~~

Bộ test này xác minh tên bean, thứ tự composition, contract kiểu và chống ghi trùng **trong một Spring context demo**. Nếu chạy test song song với context dùng chung, hãy cô lập Recorder/reset hoặc dùng key độc lập theo test; không coi ví dụ là chiến lược isolation cho mọi cấu hình CI.

### 26.1. Khi chạy trên profile prod

Profile `prod` cần các adapter `ProcessedEventStore`, `QuoteTable`, `OutboxTable`, `QuoteFingerprint` dùng database thực. Không thể chạy integration test production chỉ bằng in-memory implementation rồi khẳng định đã kiểm tra transaction.

### 26.2. Test lỗi trước và sau commit khác nhau

Unit test có thể xác minh lỗi validation không gọi Recorder. Nhưng kịch bản **database commit rồi mất ACK** phải có integration/fault-injection test trên storage và adapter hoặc một harness mô phỏng mất xác nhận **sau commit**.

Mục tiêu không chỉ thấy exception: phải kiểm tra **số Quote**, **số inbox marker**, **số outbox event** và trạng thái sau redelivery.

## 27. Test database thật: transaction, concurrency và crash windows

In-memory test kiểm tra logic quyết định, còn database integration test mới kiểm tra được uniqueness, transaction isolation và các tình huống crash/recovery liên quan storage.

### 27.1. Ma trận kiểm thử transactional inbox

| Kịch bản | Bước gây lỗi | Kết quả kỳ vọng sau restart/redelivery |
|---|---|---|
| Event mới hợp lệ | Không lỗi | Một inbox marker, một Quote, một outbox event |
| Duplicate đúng event ID | Sau lần đầu commit | Không tăng số Quote/outbox |
| Cùng event ID, payload khác | Đọc fingerprint cũ | Conflict, dữ liệu cũ giữ nguyên |
| Hai event IDs cùng create operation | Hai transaction đồng thời | Business unique constraint ngăn Quote thứ hai |
| Fail sau claim nhưng trước insert Quote | Trong transaction | Rollback claim; lần sau có thể xử lý |
| Fail sau Quote insert nhưng trước outbox insert | Trong transaction | Rollback cả Quote và claim |
| Fail sau commit nhưng trước ACK | Ngoài transaction | Lần sau đọc marker và no-op |
| Process chết khi marker PROCESSING | Sau claim riêng | Lease/recovery, không kẹt vĩnh viễn |
| Publisher outbox chết sau publish | Sau broker ACK, trước mark published | Publish có thể lặp cùng event ID |
| Consumer downstream nhận trùng | Khi inbox downstream đã commit | Không tạo tác dụng phụ thứ hai |

Khi dùng PostgreSQL thật, có thể dùng Testcontainers hoặc môi trường database cô lập để kiểm tra giao dịch. Không dùng H2 rồi mặc định semantics của `ON CONFLICT`, lock hay isolation giống PostgreSQL.

### 27.2. Thử hai transaction đồng thời

Một kịch bản đáng kiểm tra:

~~~text
Transaction A                         Transaction B
-------------                         -------------
INSERT inbox evt-778
                                      INSERT inbox evt-778
                                      chờ/đụng unique constraint
INSERT Quote
INSERT Outbox
COMMIT
                                      phát hiện duplicate
                                      so sánh fingerprint
                                      không ghi Quote/Outbox
                                      kết thúc
~~~

Sau cùng, query trạng thái:

~~~sql
SELECT COUNT(*)
FROM processed_event
WHERE tenant_id = 'shop-a'
  AND event_id = 'evt-778';

SELECT COUNT(*)
FROM order_quote
WHERE tenant_id = 'shop-a'
  AND order_id = 'ORD-42';

SELECT COUNT(*)
FROM outbox_event
WHERE tenant_id = 'shop-a'
  AND order_id = 'ORD-42'
  AND event_type = 'QuoteCreated';
~~~

Trong quy tắc create-only của bài, mỗi count dự kiến là **1**. Nếu một query trả 2, thiết kế uniqueness hoặc transaction đang sai. Khi hệ thống cho phép nhiều operation/version trên cùng order, phải thay điều kiện query và invariant tương ứng.

### 27.3. Tạo lỗi sau commit không giống rollback

Một integration test có thể chủ động:

1. Gọi handler để thực hiện transaction tạo Quote và inbox.
2. Để transaction commit thật.
3. Mô phỏng mất ACK/response ở adapter, không rollback DB.
4. Gọi lại cùng event.
5. Xác nhận không có Quote/outbox mới.
6. Xác nhận caller có thể nhận lại trạng thái/kết quả phù hợp.

Nếu test chỉ ném exception **trước commit**, nó chưa thử đúng lỗi nguy hiểm nhất của redelivery.

### 27.4. Test khi cùng event ID nhưng payload thay đổi

Gửi `evt-778` lần đầu với quantity 2, sau đó gửi lại `evt-778` với quantity 3. Test cần xác nhận:

- Lần thứ hai phát conflict.
- Quote vẫn giữ quantity 2 và total 250000.
- Outbox không phát event thứ hai.
- Không có cập nhật âm thầm.
- Conflict có log/metric điều tra mà không lộ payload nhạy cảm.

### 27.5. Test outbox publisher sau crash

Nếu publisher đã gửi `outboxId=X` nhưng mất kết nối trước khi mark published, worker mới có thể gửi `X` lần nữa. Cần test rằng **subscriber downstream** với inbox riêng nhận hai bản nhưng chỉ tạo một tác dụng phụ nghiệp vụ.

Đây là test end-to-end có cả publisher và consumer, không phải bằng chứng có thể rút ra từ unit test của `QuoteRecorder`.

## 28. Observability: phân biệt duplicate hợp lệ với lỗi

Các số liệu cần có không chỉ là số exception. Để điều tra redelivery và khả năng chống trùng, nên đo:

- `events_received_total`: số lượt nhận, bao gồm duplicate.
- `events_processed_new_total`: operation mới được commit.
- `events_duplicate_total`: event cũ, cùng fingerprint, no-op.
- `events_conflict_total`: cùng key nhưng payload khác.
- `events_invalid_total`: input/schema không hợp lệ.
- `event_processing_attempts`: số attempts của retry adapter/application.
- `inbox_claim_latency` hoặc thời gian chờ lock/unique conflict.
- `transaction_rollback_total` và loại nguyên nhân.
- `outbox_pending`, `outbox_oldest_age`, `outbox_publish_retries`.
- `message_redelivery_total`, `dlq_count` theo binder nếu có dữ liệu.

Tên metric ở đây là **đề xuất của ứng dụng**, không phải danh sách metric mặc định của Spring Cloud Function.

### 28.1. Correlation ID và idempotency key

Một log có cấu trúc có thể chứa:

~~~text
event=quote_processing
tenant=shop-a
eventId=evt-778
orderId=ORD-42
outcome=duplicate_noop
attempt=2
source=stream-consumer
~~~

Tránh log nguyên payload khách hàng, giá trị thanh toán nhạy cảm hoặc token. Cần áp dụng chính sách privacy, giới hạn truy cập log và retention.

### 28.2. Phân biệt retry do đâu

Một yêu cầu có thể bị lặp vì nhiều tầng. Khi có thể, ghi:

| Trường | Ý nghĩa |
|---|---|
| `operationId` | Định danh một operation nghiệp vụ |
| `eventId` | Định danh event được giao |
| `deliveryCount` | Số lần giao nếu adapter cung cấp đáng tin |
| `attemptIndex` | Thứ tự retry tại application |
| `retryOwner` | App, HTTP client, binder, cloud trigger |
| `outcome` | New, duplicate, conflict, invalid, failed |
| `commitStatus` | Known committed/rolled back/unknown |
| `durationMs` | Thời gian xử lý |
| `traceId` | Kết nối trace xuyên thành phần |

Không mặc định header `deliveryCount` tồn tại hoặc đáng tin trong mọi broker. Nó có thể chỉ là metadata best-effort. Một chỉ số `attemptIndex` ở application cũng không cho biết toàn bộ số lượt redelivery của broker.

### 28.3. Cảnh báo nào có ý nghĩa?

- Tỷ lệ duplicate tăng đột ngột: có thể mất ACK, retry storm hoặc producer gửi lặp.
- Conflict tăng: có thể reuse key sai hoặc bug thay payload.
- Inbox claim chờ lâu: có thể contention/lock hotspot.
- Outbox tồn đọng tăng: publisher/downstream không theo kịp.
- Lỗi sau commit tăng: cần kiểm tra transport, deadline và status response.
- Poison message trong DLQ tăng: schema/version hoặc validation không tương thích.

Duplicate no-op đôi khi là một kết quả đúng bình thường; metric cần giúp điều tra **xu hướng**, không biến mọi duplicate thành alert khẩn cấp.

## 29. Các lỗi thiết kế thường gặp

| Thiết kế chưa tốt | Rủi ro | Cách cải thiện |
|---|---|---|
| Ghi inbox trước rồi commit riêng | Process chết trước khi ghi Quote, event bị bỏ qua | Inbox + Quote trong cùng transaction |
| Ghi Quote trước, marker sau | Crash trước marker khiến replay ghi lại | Transaction chung và uniqueness |
| Chỉ dùng HashMap/static state | Nhiều replica hoặc restart không chia sẻ dữ liệu | Storage dùng chung, bền vững |
| Chỉ dedupe bằng event ID | Event ID mới có thể mang lại cùng operation | Business uniqueness/version |
| Chỉ dedupe bằng order ID | Chặn nhầm cập nhật hợp lệ | Phân biệt operation/version |
| Cùng key nhưng payload khác bị bỏ qua | Conflict bị che giấu | Fingerprint và lỗi conflict |
| Hash gồm timestamp của lần nhận | Replay giống nội dung thành hash khác | Canonical payload không chứa delivery metadata |
| Replay chạy lại rule tính giá mới | Kết quả cũ có thể khác | Snapshot/version hoặc trả kết quả đã lưu |
| ACK trước database commit | Có thể mất event nếu process chết | Hoàn tất transaction trước ACK theo adapter |
| Bắt mọi lỗi trong Consumer | Adapter tưởng đã thành công | Phân loại và truyền lỗi |
| Retry toàn pipeline có email/publish | Tác dụng phụ lặp | Outbox, provider idempotency |
| Tin outbox nghĩa là exactly-once | Publish có thể lặp khi crash | Downstream inbox/dedupe |
| TTL inbox quá ngắn | Replay muộn bị coi như event mới | Retention theo replay window |
| PROCESSING bị coi là DONE | Duplicate bị bỏ qua dù chưa hoàn tất | Lease/recovery và trạng thái rõ |
| Dùng @Transactional cho API bên ngoài | Remote effect không rollback cùng DB | Outbox/saga hoặc provider idempotency |
| Chỉ test tuần tự một request | Không phát hiện race condition | Test concurrent và fault injection |

### 29.1. Anti-pattern: check rồi ghi không nguyên tử

~~~java
if (!eventRepository.exists(eventId)) {
    quoteRepository.save(quote);
    eventRepository.markProcessed(eventId);
}
~~~

Nếu không có unique constraint/transaction, hai worker có thể cùng thấy key chưa tồn tại rồi ghi trùng. Nếu process chết giữa `save` và `markProcessed`, lần sau không biết bản ghi trước đã commit hay chưa.

Thay bằng thao tác claim dựa trên unique key và transaction chung với dữ liệu nghiệp vụ.

### 29.2. Anti-pattern: catch-all trả success

~~~java
try {
    recorder.recordOnce(quote);
} catch (Exception ex) {
    return "SUCCESS"; // Sai: không biết có commit chưa.
}
~~~

Một exception không tự chứng minh rằng side effect đã thất bại hoặc đã thành công. Ranh giới xử lý phải phân loại lỗi, tra cứu trạng thái theo key khi cần và tránh response thành công giả.

### 29.3. Anti-pattern: kiểm tra duplicate sau khi gửi email

~~~text
sendEmail(...)
checkProcessed(eventId)
~~~

Nếu email đã được gửi, phát hiện duplicate sau đó không hoàn tác được. Tách side effect có thể kiểm soát qua outbox hoặc provider idempotency; đừng chỉ thêm dedupe như bước cuối hình thức.

## 30. Checklist trước khi đưa production

### 30.1. Identity và dữ liệu

- [ ] Một operation nghiệp vụ được tính là một lần đã được định nghĩa rõ.
- [ ] Event/request ID ổn định qua retry, redelivery và reinvocation.
- [ ] Idempotency key scoped theo tenant, operation và version khi cần.
- [ ] Cùng key nhưng payload khác bị phát hiện và từ chối.
- [ ] Fingerprint canonical có ngữ nghĩa được ghi rõ.
- [ ] Rule version/snapshot được quản lý khi replay dữ liệu cũ.
- [ ] Update hợp lệ không bị chặn như duplicate của create.

### 30.2. Giao dịch và side effect

- [ ] Inbox marker, Quote và outbox commit atomically khi cùng datasource.
- [ ] Storage có unique constraint hoặc ghi nguyên tử cho concurrent workers.
- [ ] DONE khác PROCESSING và commit unknown.
- [ ] Có phương án xử lý crash sau commit nhưng trước ACK.
- [ ] Outbox publisher có claim/lease và downstream dedupe.
- [ ] Email, payment, API ngoài có idempotency hoặc cách phục hồi riêng.
- [ ] Có recovery cho marker/lease bị kẹt.

### 30.3. Spring Cloud Function và adapter

- [ ] Validation và Function thuần chạy trước Consumer có side effect.
- [ ] FunctionCatalog đăng ký và ghép đúng tên/kiểu.
- [ ] Definition chọn đúng pipeline/binding trên môi trường thực.
- [ ] HTTP resend cùng Idempotency-Key không tạo operation trùng.
- [ ] Message binder nhận completion/error đúng để ACK/retry/DLQ.
- [ ] Serverless reinvocation trên instance khác vẫn dedupe qua DB.
- [ ] Reactive retry/resubscription không lặp effect không kiểm soát.
- [ ] Retry được giới hạn và không lặp validation/conflict vô ích.

### 30.4. Kiểm thử và vận hành

- [ ] Test một event được gửi hai lần và nhiều lần.
- [ ] Test cùng key, payload khác.
- [ ] Test event ID mới nhưng cùng business operation.
- [ ] Test hai tenant cùng order ID.
- [ ] Test concurrent xử lý một event.
- [ ] Test crash trước commit, sau commit và sau publish.
- [ ] Test trên database thật, không chỉ in-memory.
- [ ] Test adapter HTTP/message/serverless phù hợp triển khai.
- [ ] Có metric new, duplicate, conflict và outbox pending.
- [ ] Retention của inbox phù hợp replay window và chính sách dữ liệu.

Nếu thiếu các bằng chứng trên, hãy mô tả giới hạn hiện tại thay vì cam kết exactly-once end-to-end.

## 31. Bài tập thực hành

**Bài 1 — Mất ACK.** Broker giao `evt-778`, Consumer lưu Quote thành công nhưng process chết trước ACK. Broker giao lại cùng event. Hãy mô tả trạng thái inbox/Quote/outbox trước và sau lần nhận lại.

**Bài 2 — Key bị tái sử dụng sai.** Một event ID được gửi với quantity 2, sau đó cùng event ID được gửi với quantity 3. Vì sao chỉ kiểm tra key rồi return không đủ? Nên báo lỗi nào?

**Bài 3 — Event ID mới cho cùng thao tác.** Producer gửi `evt-778: CreateQuote(ORD-42,2)` rồi `evt-779: CreateQuote(ORD-42,2)`. Inbox coi event thứ hai là mới. Cơ chế nào ngăn tạo Quote thứ hai?

**Bài 4 — Update hợp lệ.** Sau khi tạo `ORD-42`, ứng dụng nhận `UpdateQuote(ORD-42,version=2)`. Vì sao dedupe chỉ bằng `orderId` có thể chặn nhầm operation hợp lệ?

**Bài 5 — Hai worker.** Hai replica cùng thấy event chưa tồn tại bằng `SELECT`. Vì sao cả hai có thể ghi trùng? Đề xuất unique key và transaction.

**Bài 6 — Giao dịch tách đôi.** Transaction A commit marker DONE, transaction B ghi Quote. Process chết sau A và trước B. Hậu quả là gì? Hãy đề xuất một ranh giới transaction mới.

**Bài 7 — Outbox.** Publisher gửi `QuoteCreated` tới broker nhưng chết trước khi đánh dấu published. Worker mới gửi lại. Vì sao downstream vẫn cần inbox?

**Bài 8 — HTTP.** Client gửi `POST` có `Idempotency-Key=req-3af9`, response mất sau DB commit rồi client resend. Làm sao trả kết quả đã lưu? Nếu payload mới khác, cần làm gì?

**Bài 9 — Serverless.** Hai invocation xử lý cùng event trên hai instance khác nhau. Vì sao `static ConcurrentHashMap` không phải cơ chế chống trùng production?

**Bài 10 — Reactor.** Cho `Flux.just("1","bad","3").map(Integer::parseInt).retry(1)`. Hãy dự đoán các tín hiệu. Nếu có bước ghi dữ liệu cho `1`, rủi ro là gì?

**Bài 11 — Validation.** Event có quantity bằng `0`. Tại sao Consumer phải từ chối trước khi ghi? Retry cùng payload có giúp nó hợp lệ không?

**Bài 12 — Rule version.** Event cũ được replay sau khi bảng giá tăng. Nếu tính lại rồi so sánh Quote, có thể phát hiện xung đột giả thế nào? Đề xuất cách giữ snapshot/command fingerprint.

**Bài 13 — Concurrency test.** Thiết kế test với 12 thread cùng gọi `recordOnce` cho cùng Quote. Cần assertion gì ngoài việc không có exception?

**Bài 14 — TTL.** Inbox xóa marker sau 24 giờ, nhưng DLQ có thể replay sau 30 ngày. Hệ thống còn lớp bảo vệ nào? Bạn sẽ chọn retention ra sao?

**Bài 15 — Email.** Method `@Transactional` lưu Quote rồi gửi email. Vì sao rollback DB không hoàn tác email? Làm sao giảm nguy cơ gửi trùng?

**Bài 16 — ACK và async completion.** Một `Consumer<Flux<Quote>>` tự subscribe rồi trả ngay. Điều gì có thể xảy ra với ACK nếu lỗi nằm trong subscription?

**Bài 17 — Tenant scope.** Shop A và shop B cùng dùng `orderId=ORD-42` và `eventId=evt-778`. Vì sao không dùng mỗi event ID làm khóa toàn cục?

**Bài 18 — Fault injection.** Chọn ba điểm crash trong transaction inbox/Quote/outbox và kịch bản publish. Với mỗi điểm, nêu invariant cần kiểm tra khi xử lý lại.

**Bài 19 — Duplicate và alert.** Vì sao một duplicate no-op không nhất thiết là incident, nhưng tỷ lệ duplicate tăng cao vẫn cần quan sát?

**Bài 20 — FunctionCatalog.** So sánh hai definition `normalizeOrder|validateOrder|calculateQuote` và `normalizeOrder|validateOrder|calculateQuote|recordQuoteOnce`. Pipeline nào có side effect, và framework có tự dedupe không?

### Gợi ý lời giải

- **Bài 1:** DB đã commit nên lần nhận lại đọc inbox, không tạo Quote/outbox mới, rồi hoàn tất theo chính sách ACK của binder.
- **Bài 2:** Key trùng không chứng minh payload giống. So sánh fingerprint và trả conflict, giữ dữ liệu cũ.
- **Bài 3:** Unique business key theo tenant, order và operation/version; so sánh nội dung Quote.
- **Bài 4:** Create và Update là hai operation, cần operation/version/optimistic locking riêng.
- **Bài 5:** `SELECT` rồi `INSERT` có race condition. Dùng unique constraint và thao tác claim/ghi nguyên tử trong transaction.
- **Bài 6:** Marker DONE nhưng Quote chưa lưu làm event bị bỏ qua. Inbox và Quote phải commit cùng nhau.
- **Bài 7:** Crash sau publish khiến outbox event có thể được phát lại; consumer downstream dedupe theo event ID.
- **Bài 8:** Lấy trạng thái/response cũ theo key đã commit; payload khác cần conflict, không ghi đè.
- **Bài 9:** Instance không chia sẻ bộ nhớ và có thể restart; dùng storage bền vững với key ổn định.
- **Bài 10:** Có thể phát `1` hai lần rồi `onError`; storage phải idempotent khi callback có thể chạy lại.
- **Bài 11:** Dữ liệu sai không tự sửa nhờ retry; validation trước side effect.
- **Bài 12:** Rule mới làm Quote khác dù command giống; lưu rule/snapshot hoặc nhận diện replay trước khi tính lại.
- **Bài 13:** Đồng bộ start bằng latch, đợi mọi future; kiểm tra chỉ một Quote và một event được ghi.
- **Bài 14:** Business uniqueness có thể ngăn một số duplicate, nhưng retention inbox cần xét cửa sổ replay thực tế và chính sách dữ liệu.
- **Bài 15:** Email ở hệ thống ngoài DB; dùng outbox và provider idempotency key khi hỗ trợ.
- **Bài 16:** Binder có thể ACK trước khi async Publisher kết thúc, không nhìn thấy lỗi; cần quản lý terminal signal đúng contract.
- **Bài 17:** Key phải scoped theo tenant/principal/operation, tránh va chạm giữa khách hàng.
- **Bài 18:** Trước commit phải rollback marker và Quote; sau commit trước ACK phải no-op; sau publish trước mark có thể phát lại nhưng downstream dedupe.
- **Bài 19:** Duplicate có thể bình thường trong at-least-once delivery; tỷ lệ tăng có thể báo vấn đề ACK/retry/producer.
- **Bài 20:** Pipeline thứ nhất trả `Function<OrderCommand,Quote>` thuần; thêm Consumer cuối tạo `Consumer<OrderCommand>` có side effect. `FunctionCatalog` không tự triển khai idempotency.

## 32. Ghi nhớ

- **Một yêu cầu nghiệp vụ có thể được gửi lại**, qua HTTP client retry, broker redelivery, serverless reinvocation, DLQ replay hoặc Reactor resubscription.
- Một Function tính toán thuần dễ chạy lại, nhưng **Consumer có side effect** phải được bảo vệ bởi business idempotency, không chỉ bởi cú pháp Java.
- Dedupe theo `eventId` nhận biết một message bị giao lại; **business key/operation version** bảo vệ khi producer phát event ID mới cho cùng thao tác.
- Cùng key và cùng payload có thể xử lý no-op; **cùng key nhưng payload khác là conflict** cần được phát hiện.
- **Inbox, Quote và outbox cùng commit** khi chúng cần thành công nguyên tử; unique constraint xử lý cạnh tranh giữa nhiều worker.
- ACK sau commit vẫn có cửa sổ redelivery khi ACK mất; storage phải chịu được nhận lại.
- Transactional outbox giảm nguy cơ mất sự kiện nhưng có thể publish trùng; consumer downstream cần xử lý idempotent.
- HTTP Idempotency-Key, Spring Cloud Stream binder và serverless trigger có hợp đồng riêng. `FunctionCatalog` và `spring.cloud.function.definition` không tự cung cấp exactly-once.
- Retention, rule version/snapshot và business operation phải được thiết kế để replay muộn không tạo kết quả sai.
- **Độ tin cậy được chứng minh bằng trạng thái sau lỗi và sau replay**, cùng test concurrency/crash windows, không chỉ bằng việc không có exception.










