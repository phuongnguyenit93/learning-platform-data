# Phân biệt số liệu kỹ thuật với sự kiện nghiệp vụ trong quan sát chương trình bằng AOP

## 1. Vì sao hai loại thông tin dễ bị nhầm lẫn?

Aspect-Oriented Programming (AOP) cho phép bổ sung hành vi xuyên suốt như đo thời gian, ghi log, thống kê lỗi và tracing tại các **join point** đã chọn. Một *around advice* có thể biết rằng phương thức `placeOrder()` được gọi, mất bao lâu và kết thúc bằng giá trị trả về hay ngoại lệ. Tuy nhiên, chỉ từ những dấu hiệu đó, advice **chưa thể kết luận** rằng “đơn hàng đã được đặt thành công” theo ý nghĩa nghiệp vụ.

Hai câu sau có nghĩa khác nhau:

- **“Có một lần gọi `placeOrder()`, chạy trong 12 ms và trả về bình thường.”** Đây là thông tin quan sát kỹ thuật về một lần thực thi.
- **“Đơn hàng O-100 đã được chấp nhận và trở thành đơn hàng hợp lệ.”** Đây là một sự kiện nghiệp vụ, phải được xác nhận bằng quy tắc và ranh giới trạng thái của domain.

Một lời gọi có thể trả về bình thường nhưng giao dịch lưu dữ liệu vẫn bị rollback ở bước sau; một lời gọi có thể bị retry nhiều lần nhưng chỉ tạo một đơn hàng; một tác vụ bất đồng bộ có thể đã được nhận vào hàng đợi nhưng chưa thực hiện. Vì thế, dùng log/metric tự động từ AOP làm “bằng chứng đã xảy ra sự kiện nghiệp vụ” sẽ dẫn tới đếm sai, phát thông báo sai hoặc tạo lịch sử nghiệp vụ không đáng tin.

**Mục tiêu học tập:** nhận diện nguồn và ý nghĩa của dữ liệu quan sát, chọn nơi đặt advice, giữ quyền quyết định sự kiện nghiệp vụ ở domain, và thiết kế phép đo không làm thay đổi kết quả chương trình.

## 2. Hai khái niệm và sự khác nhau cốt lõi

### 2.1. Số liệu kỹ thuật (technical telemetry)

Số liệu kỹ thuật mô tả **hệ thống vận hành như thế nào**. Chúng thường gồm:

- **Metric:** giá trị định lượng có thể tổng hợp qua thời gian, chẳng hạn số lời gọi, tỷ lệ lỗi, độ trễ, kích thước hàng đợi, bộ nhớ đang sử dụng.
- **Log:** bản ghi về tình huống, thao tác hoặc ngoại lệ tại một thời điểm; thường có mức độ nghiêm trọng và ngữ cảnh.
- **Trace/span:** chuỗi hoặc đoạn hoạt động dùng để lần theo đường đi của một yêu cầu qua những lời gọi, tác vụ và thành phần khác nhau.

AOP phù hợp để thu thập những thông tin này vì có thể can thiệp lặp lại vào một nhóm join point mà không phải chèn cùng đoạn code đo thời gian vào từng phương thức. Dữ liệu kỹ thuật thường dùng để trả lời: “Có gì chậm?”, “Lỗi xảy ra ở đâu?”, “Bao nhiêu lần gọi đã được thực hiện?”.

### 2.2. Sự kiện nghiệp vụ (business/domain event)

Sự kiện nghiệp vụ là **một điều đã xảy ra và có ý nghĩa đối với domain**, thường đặt tên ở thì quá khứ: `OrderPlaced`, `PaymentAuthorized`, `InventoryReserved`. Nó mô tả sự thay đổi hoặc một sự thật nghiệp vụ mà hệ thống khác có thể cần xử lý.

Một sự kiện đáng tin cần xác định rõ:

1. **Điều kiện phát sinh:** quy tắc/domain nào cho phép nói rằng sự kiện đã xảy ra?
2. **Mốc hiệu lực:** thay đổi đã được chấp nhận trong bộ nhớ, hoàn tất giao dịch hay được xác nhận bởi hệ thống bên ngoài?
3. **Danh tính:** sự kiện nào, thuộc thực thể nào; có thể phân biệt với một lần phát lại không?
4. **Dữ liệu:** những trường tối thiểu để người nhận hiểu sự kiện.
5. **Chủ sở hữu ý nghĩa:** thành phần nghiệp vụ nào quyết định khi nào phát sinh?

Ví dụ `OrderPlaced` có thể cần `eventId`, `orderId`, `occurredAt`, `schemaVersion` và trạng thái/giá trị đơn hàng được chấp nhận. Các trường này **không** đồng nghĩa với tên phương thức, số lần gọi hoặc độ dài một span.

| Tiêu chí | Quan sát kỹ thuật | Sự kiện nghiệp vụ |
| --- | --- | --- |
| Câu hỏi chính | Hệ thống đã thực thi thế nào? | Điều gì đã xảy ra trong domain? |
| Ví dụ | `order.place.duration=12ms`; span `OrderService.place` | `OrderPlaced(orderId=O-100)` |
| Nguồn xác thực | Join point, runtime, logger, collector | Quy tắc domain và ranh giới trạng thái đã xác nhận |
| Tần suất | Có thể ghi mỗi lần gọi, retry, lỗi | Theo sự thật nghiệp vụ; thường cần chống trùng |
| Nhãn/dữ liệu | Label ít biến thể để tổng hợp; trace ID để tương quan | ID sự kiện/thực thể, payload có ý nghĩa nghiệp vụ |
| Độ bền | Tùy hệ thống lưu telemetry, chính sách lấy mẫu và thời gian giữ | Theo yêu cầu vận hành/audit/tích hợp nghiệp vụ |
| Hệ quả khi mất một bản ghi | Giảm khả năng chẩn đoán hoặc thống kê | Có thể làm sai lệch tiến trình tích hợp hoặc lịch sử nghiệp vụ |
| Xử lý lỗi | Lỗi ghi telemetry thường không nên đổi kết quả nghiệp vụ | Lỗi tạo/lưu/phát sự kiện phải theo hợp đồng nhất quán đã thiết kế |

Một **log có câu chữ nghiệp vụ** vẫn chỉ là log nếu không có hợp đồng sự kiện, bảo đảm lưu trữ và xử lý trùng. Một **metric đếm “đặt đơn thành công”** chưa phải số lượng đơn hàng nếu nó chỉ đếm lần phương thức trả về mà không đối chiếu trạng thái đã xác nhận.

## 3. Những trường hợp dễ phát sinh số liệu sai

Xét luồng nhận yêu cầu đặt hàng:

```text
Yêu cầu đặt đơn
  -> advice ghi một lần gọi kỹ thuật
  -> kiểm tra dữ liệu và quy tắc
  -> thay đổi trạng thái nghiệp vụ
  -> commit thay đổi
  -> phát sự kiện theo chính sách tin cậy
  -> xử lý bất đồng bộ ở các thành phần khác
```

Các kịch bản có thể quan sát được:

| Kịch bản | Số liệu kỹ thuật có thể ghi | Sự kiện nghiệp vụ phù hợp |
| --- | --- | --- |
| Dữ liệu không hợp lệ, hàm ném ngoại lệ | 1 invocation, 1 failure, thời gian xử lý | Không có `OrderPlaced` |
| Một đơn hợp lệ được xác nhận | 1 invocation, 1 success | 1 `OrderPlaced` theo hợp đồng |
| Client timeout rồi retry cùng thao tác | 2 invocations; có thể 1 timeout và 1 success | Có thể chỉ 1 `OrderPlaced` nếu idempotency bảo đảm |
| Lời gọi trả về nhưng transaction rollback sau đó | Advice có thể thấy “return success” | Không được xác nhận `OrderPlaced` nếu hợp đồng đòi commit |
| Phương thức chỉ gửi tác vụ vào hàng đợi | 1 lần submit thành công | Chưa thể suy ra tác vụ nghiệp vụ đã hoàn tất |
| Sự kiện đã ghi bền nhưng gửi lên broker bị retry | Nhiều lần gửi hoặc nhận kỹ thuật | Vẫn là một sự kiện logic, người nhận cần chống xử lý trùng |

Như vậy:

```text
method_invocation_count  != business_event_count
method_returned_normally != transaction_committed
task_submitted           != task_completed
event_delivery_count     != unique_business_event_count
```

Các dấu `!=` biểu diễn những đại lượng **không mặc nhiên bằng nhau**, không phủ nhận việc chúng đôi khi có giá trị bằng nhau trong một trường hợp cụ thể.

## 4. AOP chịu trách nhiệm phần nào?

### 4.1. AOP quan sát lời gọi, không xác nhận domain event

Trong AOP, **join point** là vị trí có thể can thiệp; **pointcut** chọn vị trí và **advice** thực hiện phép đo. **Around advice** có thể lấy thời gian bằng `System.nanoTime()` quanh `proceed()`, còn after-returning và after-throwing quan sát hai kiểu kết thúc của chính lời gọi. Phạm vi thực tế phụ thuộc cơ chế interception/weaving.

**Các tín hiệu đó xác nhận điều xảy ra tại một lần thực thi, không tự xác nhận việc commit hoặc phát sinh sự kiện nghiệp vụ.** Dù advice nhìn thấy return thành công, quyền định nghĩa `OrderPlaced` vẫn thuộc về logic domain và ranh giới trạng thái đáng tin cậy.

### 4.2. Ranh giới trách nhiệm

**Nên giao cho aspect quan sát kỹ thuật:**

- Đếm số lần gọi và lỗi theo loại thao tác.
- Đo độ trễ của join point hoặc giai đoạn bất đồng bộ được khai báo rõ.
- Gắn trace/span và tương quan các lời gọi.
- Ghi log chẩn đoán đã loại bỏ dữ liệu nhạy cảm.
- Theo dõi số lần cố gắng publish sự kiện, độ trễ gửi, lỗi kết nối.

**Nên giao cho logic nghiệp vụ và cơ chế lưu/phát sự kiện:**

- Xác định khi nào `OrderPlaced` thực sự có hiệu lực.
- Xác minh điều kiện domain, transaction và idempotency.
- Tạo định danh, phiên bản, payload sự kiện.
- Đảm bảo thay đổi dữ liệu và việc lưu sự kiện được xử lý nhất quán.
- Quy định retry, chống trùng, thứ tự và chính sách xử lý lỗi.

AOP có thể giúp **quan sát quá trình phát sự kiện**, hoặc gắn metadata kỹ thuật vào một envelope theo hợp đồng được phê duyệt, nhưng không nên tự tạo một `OrderPlaced` chỉ vì phương thức tên `placeOrder` đã trả về. Đổi tên phương thức, tách lời gọi, retry hoặc thay đổi ranh giới transaction sẽ làm quy tắc ngầm ấy sai lệch.

### 4.3. Pseudocode: advice đo kỹ thuật

```text
around(joinPoint):
    t0 = monotonicClock.now()
    success = false
    try:
        value = proceedExactlyOnce(joinPoint)
        success = true
        return value
    finally:
        elapsed = monotonicClock.now() - t0
        try:
            technicalMetrics.record(
                operation = stableOperationName,
                outcome = success ? SUCCESS : ERROR,
                duration = elapsed
            )
        catch telemetryError:
            reportTelemetryProblemWithoutChangingBusinessResult()
```

Đây là **pseudocode AOP**, không phải cú pháp Java độc lập. Đồng hồ đơn điệu thích hợp để tính thời lượng; thời gian lịch (wall-clock) hữu ích để đóng dấu `occurredAt` cho sự kiện nhưng không thay thế đồng hồ đơn điệu khi đo latency.

Một aspect tốt gọi `proceed()` đúng một lần khi hợp đồng không đòi retry, bảo toàn giá trị trả về và ngoại lệ. Nếu việc thu thập metric là best-effort, lỗi từ metric sink không được biến thao tác nghiệp vụ thành thất bại hoặc che mất ngoại lệ gốc.

## 5. Ví dụ Java 17 hoàn chỉnh: hai nguồn thông tin độc lập

Ví dụ dưới dùng **decorator** để mô phỏng một around advice ở ranh giới gọi phương thức. `OrderService` là nơi quyết định và tạo sự kiện nghiệp vụ; `TimingAspect` chỉ thu thập metric kỹ thuật. Mẫu này hoạt động bằng Java thuần và có thể được áp dụng thành advice/weaving trong một hệ thống AOP độc lập.

Tạo tệp **AopObservationDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class AopObservationDemo {
    record OrderPlaced(String orderId, long amountVnd) {}

    interface EventSink {
        void publish(OrderPlaced event);
    }

    static final class InMemoryEventSink implements EventSink {
        final List<OrderPlaced> events = new ArrayList<>();

        @Override
        public void publish(OrderPlaced event) {
            events.add(event);
        }
    }

    interface OrderUseCase {
        void place(String orderId, long amountVnd);
    }

    static final class OrderService implements OrderUseCase {
        private final EventSink eventSink;

        OrderService(EventSink eventSink) {
            this.eventSink = eventSink;
        }

        @Override
        public void place(String orderId, long amountVnd) {
            if (orderId == null || orderId.isBlank() || amountVnd <= 0) {
                throw new IllegalArgumentException("invalid order");
            }
            // Ví dụ bộ nhớ: sau khi chấp nhận, domain phát sinh event.
            eventSink.publish(new OrderPlaced(orderId, amountVnd));
        }
    }

    record Observation(String operation, String outcome, long durationNanos) {}

    static final class TechnicalMetrics {
        final List<Observation> observations = new ArrayList<>();

        void record(String operation, String outcome, long durationNanos) {
            observations.add(new Observation(operation, outcome, durationNanos));
        }
    }

    // Decorator minh họa around advice ở ranh giới thực thi phương thức.
    static final class TimingAspect implements OrderUseCase {
        private final OrderUseCase target;
        private final TechnicalMetrics metrics;

        TimingAspect(OrderUseCase target, TechnicalMetrics metrics) {
            this.target = target;
            this.metrics = metrics;
        }

        @Override
        public void place(String orderId, long amountVnd) {
            long started = System.nanoTime();
            boolean success = false;
            try {
                target.place(orderId, amountVnd); // tương đương proceed()
                success = true;
            } finally {
                long elapsed = System.nanoTime() - started;
                try {
                    metrics.record("order.place", success ? "SUCCESS" : "ERROR", elapsed);
                } catch (RuntimeException ignored) {
                    // Telemetry không được thay đổi kết quả nghiệp vụ.
                }
            }
        }
    }

    public static void main(String[] args) {
        InMemoryEventSink events = new InMemoryEventSink();
        TechnicalMetrics metrics = new TechnicalMetrics();
        OrderUseCase service = new TimingAspect(new OrderService(events), metrics);

        service.place("O-100", 250_000);
        try {
            service.place("O-101", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("technical.count=" + metrics.observations.size());
        System.out.println("technical.outcomes=" + metrics.observations.stream()
                .map(Observation::outcome).toList());
        System.out.println("business.count=" + events.events.size());
        System.out.println("business.event=" + events.events.get(0));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 AopObservationDemo.java
java AopObservationDemo
```

**Stdout chính xác:**

```text
rejected: invalid order
technical.count=2
technical.outcomes=[SUCCESS, ERROR]
business.count=1
business.event=OrderPlaced[orderId=O-100, amountVnd=250000]
```

Giải thích:

1. Lần đầu có lời gọi hợp lệ. `OrderService` tạo một `OrderPlaced`; `TimingAspect` ghi một observation SUCCESS.
2. Lần sau có lời gọi không hợp lệ. Advice vẫn quan sát một lần gọi ERROR, nhưng `OrderService` không phát ra `OrderPlaced`.
3. Vì vậy **2 số liệu về lần gọi kỹ thuật** đi cùng **1 sự kiện nghiệp vụ**. Không có mâu thuẫn: hai nguồn mô tả hai loại sự thật khác nhau.
4. `durationNanos` được đo bằng `System.nanoTime()`, nhưng chương trình cố ý không in một con số thời gian cố định vì độ trễ thực tế thay đổi theo mỗi lần chạy.

**Giới hạn cố ý của ví dụ:** dữ liệu và event sink đều ở bộ nhớ, không có transaction, broker, đa luồng hay bảo đảm lưu bền; `ArrayList` chỉ phù hợp với tình huống một luồng minh họa. Khi ứng dụng thực dùng concurrency, collector phải an toàn luồng và tránh tạo điểm nghẽn. Đoạn code không chứng minh tính nguyên tử giữa ghi cơ sở dữ liệu và phát sự kiện; vấn đề đó được giải quyết ở phần tiếp theo.

## 6. Transaction, outbox và ranh giới “đã xảy ra”

Khi một sự kiện tuyên bố “đơn hàng đã đặt”, hệ thống cần xác định mốc nào khiến lời tuyên bố đó đúng. Với nghiệp vụ dựa trên giao dịch cơ sở dữ liệu, chỉ thực thi thành công phương thức **chưa chắc** đồng nghĩa với commit thành công.

### 6.1. Sự cố phát sinh từ việc tạo event trong advice

Ví dụ có thể xảy ra:

```text
around advice: enter placeOrder()
  -> domain cập nhật trạng thái
  -> placeOrder() trả về bình thường
  -> after-returning advice tự publish OrderPlaced
  -> transaction commit bị lỗi / rollback
Kết quả: bên nhận đã thấy "OrderPlaced" nhưng DB không có đơn đã commit.
```

Điểm mấu chốt là **thời điểm advice quan sát sự trở về không nhất thiết là ranh giới commit**. Vị trí transaction nằm ở đâu và advice bao quanh lớp nào quyết định thứ tự thật. Do đó, chỉ dựa vào tên phương thức hoặc `return normally` để phát event có thể sai.

### 6.2. Mẫu transactional outbox (khái niệm)

Khi yêu cầu sự kiện phản ánh trạng thái commit và được phát đáng tin:

1. Logic domain xác nhận điều kiện phát sinh `OrderPlaced`.
2. Trong **cùng một transaction cơ sở dữ liệu**, lưu trạng thái đơn hàng và một bản ghi outbox chứa event ID, loại, payload, aggregate ID và trạng thái gửi.
3. Commit transaction. Nếu rollback, cả thay đổi nghiệp vụ lẫn bản ghi outbox cùng bị huỷ.
4. Một bộ chuyển tiếp đọc các bản ghi outbox đã commit và gửi tới nơi nhận.
5. Nếu gửi lỗi, bộ chuyển tiếp retry; người nhận dùng **event ID/idempotency** để tránh xử lý sự kiện logic nhiều lần.

```text
BEGIN TRANSACTION
    update order state
    insert outbox(OrderPlaced, eventId, orderId, payload)
COMMIT
          |
          v
    outbox relay --retry--> event broker/consumer
                                  |
                                  v
                       deduplicate by eventId
```

Outbox giúp tránh trường hợp “ghi DB thành công nhưng publish thất bại rồi mất sự kiện”, **không tự mang lại exactly-once delivery**. Relay có thể gửi trùng nếu crash sau khi gửi nhưng trước khi đánh dấu đã gửi; consumer vẫn cần idempotency. Nếu transaction không hỗ trợ outbox chung, phải lựa chọn cơ chế nhất quán phù hợp và nêu rõ giới hạn bảo đảm.

Advice có thể đo `outbox.insert.duration`, `event.publish.attempts` hoặc `event.delivery.failure`; chính sách quyết định event nào được lưu và lúc nào có hiệu lực vẫn thuộc domain và kiến trúc dữ liệu.

### 6.3. Retry và đếm riêng các lớp

Một lần `OrderPlaced` logic có thể tương ứng với nhiều lượt HTTP, nhiều attempt xử lý message và nhiều lần publish. Cần phân biệt các đại lượng:

- `request.attempt.count`: có bao nhiêu yêu cầu/attempt kỹ thuật đi qua ranh giới.
- `order.placed.event.count`: có bao nhiêu sự kiện logic được tạo hoặc ghi bền, xác định theo ID duy nhất.
- `event.delivery.attempt.count`: có bao nhiêu lần thử chuyển sự kiện.
- `event.consumer.processed.count`: có bao nhiêu xử lý thực sự thành công sau quy tắc chống trùng.

Các tên trên chỉ minh họa cách đặt tên metric, không phải API chuẩn. Phải ghi rõ đếm **lần thử**, **sự kiện duy nhất**, hay **thực thi sau chống trùng**. Nếu bộ thu metric nhận trùng thì chính các metric cũng có thể lệch; báo cáo tài chính/nghiệp vụ chính thức nên dựa vào nguồn trạng thái bền vững được kiểm soát.

## 7. Log và audit log có phải sự kiện nghiệp vụ không?

Không nên quyết định dựa trên tên công cụ lưu trữ. **Định nghĩa và hợp đồng dữ liệu** mới quan trọng:

- **Log chẩn đoán:** “`placeOrder completed in 12ms`”, dùng để vận hành, có thể được lấy mẫu hoặc xoá theo thời hạn.
- **Audit record:** “người dùng X yêu cầu thay đổi Y lúc T”, nhằm chứng minh hành vi truy cập/thao tác và tuân theo chính sách audit; không nhất thiết chứng minh thay đổi đã có hiệu lực.
- **Domain event:** “`OrderPlaced` đã có hiệu lực đối với đơn O-100”, có cấu trúc và ý nghĩa nghiệp vụ rõ, tiêu thụ bởi các workflow khác.

Một audit record được lưu bền và định nghĩa như sự kiện trong kiến trúc cụ thể có thể được xử lý như một loại event; tuy nhiên **không thể suy ra mọi log/audit record là domain event**. Ví dụ “người dùng nhấn nút Thanh toán” khác “thanh toán đã được ghi nhận thành công”.

Ngay cả khi aspect ghi log có thông tin `orderId`, đó cũng không đủ để làm log trở thành bằng chứng nghiệp vụ. Trước khi dùng một dòng log để kích hoạt xử lý nghiệp vụ, phải có hợp đồng về ý nghĩa, tính bền, thứ tự, chống trùng, kiểm soát truy cập và xử lý lỗi.

## 8. Quan sát ranh giới bất đồng bộ mà không tạo sự kiện giả

Khi một lời gọi trả về `CompletionStage`, `Future` hoặc chỉ đẩy `Runnable` vào executor, advice quanh phương thức tạo việc chỉ biết **chi phí tạo/gửi**. Tác vụ có thể chờ hàng đợi, chạy, thất bại hoặc bị huỷ sau khi lời gọi trả về.

```text
t0: advice vào enqueue()
t1: enqueue() trả về handle      -> submission latency = t1 - t0
t2: worker bắt đầu chạy          -> queue wait = t2 - t1 (chỉ khi các mốc phù hợp)
t3: worker hoàn thành xử lý
t4: observer nhìn thấy completion -> observed completion = t4 - t0
```

Muốn đo completion phải gắn observer vào handle hoặc instrument trực tiếp thân tác vụ. `CompletionStage.whenComplete(...)` là cách quan sát không chặn, nhưng thời điểm callback chạy **có thể muộn hơn lúc tác vụ thực sự hoàn tất**; callback không có nghĩa là transaction đã commit hay sự kiện nghiệp vụ đã phát. Không dùng `Future.get()` hoặc `join()` ngay trong advice nếu yêu cầu giữ bản chất bất đồng bộ.

Một luồng ví dụ:

```text
Task submitted (technical)
   -> Task started (technical)
   -> Domain validates order (business rule)
   -> Transaction commits (business state)
   -> OrderPlaced persisted in outbox (business event)
   -> Observer sees completion (technical)
```

Nếu task thất bại sau khi được gửi, telemetry vẫn có `submission.success` nhưng không có `OrderPlaced` hợp lệ. Nếu task thực hiện nhiều lệnh nghiệp vụ, một `completion` kỹ thuật chưa thể thay thế các sự kiện tương ứng với từng thay đổi.

Trong trace phân tán, **trace ID** và **correlation ID** giúp tìm các bản ghi liên quan. Event ID dùng để nhận diện sự kiện logic và chống trùng; một trace có thể chứa nhiều event, một event có thể được xử lý trong nhiều trace. Đừng dùng trace ID như event ID một cách mặc định.

## 9. Thiết kế dữ liệu để không lẫn lộn ý nghĩa

### 9.1. Metric cho vận hành

Nên đặt các tên phản ánh đúng phạm vi đo, ví dụ:

```text
use_case.invocation.total{operation="order.place",outcome="success"}
use_case.invocation.total{operation="order.place",outcome="error"}
use_case.duration.seconds{operation="order.place"}
event.publish.attempt.total{event_type="OrderPlaced",outcome="error"}
```

Đây là **các tên và label minh họa**, không khẳng định cú pháp bắt buộc của một thư viện đo đạc. `operation`, `outcome`, `event_type` là label có tập giá trị hữu hạn, phù hợp để tổng hợp. Không đưa `orderId`, `customerId`, event ID hoặc toàn bộ exception message vào label metric vì chúng có cardinality cao, tăng số lượng chuỗi thời gian, tốn bộ nhớ và làm giảm khả năng vận hành.

Ngược lại, bản thân event có thể cần `orderId` và `eventId` trong payload theo hợp đồng nghiệp vụ. Không áp dụng hạn chế cardinality của metric cho danh tính nghiệp vụ trong bản ghi sự kiện.

### 9.2. Envelope cho sự kiện nghiệp vụ

Ví dụ một biểu diễn cấu trúc:

```json
{
  "eventId": "evt-100",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "aggregateId": "O-100",
  "occurredAt": "2026-10-20T02:15:00Z",
  "payload": {
    "amountVnd": 250000
  },
  "correlationId": "req-900"
}
```

Các giá trị là **dữ liệu minh họa**, không phải một sự kiện đã xảy ra thực. `occurredAt` thường là thời điểm hiệu lực do hệ thống phát sự kiện định nghĩa; `publishedAt` nếu có là thời điểm gửi đi và có thể muộn hơn. `correlationId` hỗ trợ truy vết, không thay thế `eventId` để chống trùng. Hợp đồng phải quy định phiên bản schema và cách consumer xử lý thay đổi.

### 9.3. Tránh làm rò rỉ dữ liệu

Aspect quan sát nhiều điểm gọi nên đặc biệt dễ thu thập quá mức. Không tự động log mọi tham số, token, mật khẩu, thông tin thanh toán hoặc toàn bộ payload event. Chọn trường cần thiết, ẩn dữ liệu nhạy cảm và áp dụng chính sách lưu trữ. Một event nghiệp vụ cũng phải giới hạn dữ liệu trong payload theo nhu cầu người nhận.

## 10. Lỗi thiết kế phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách thiết kế lại |
| --- | --- | --- |
| Tạo `OrderPlaced` từ after-returning của phương thức tên `placeOrder` | Có thể phát event khi transaction rollback hoặc phương thức chỉ gửi việc | Domain xác định điều kiện; lưu event nhất quán với trạng thái |
| Đếm số lần gọi thành số đơn mới | Retry và lỗi làm số liệu phình lên | Tách invocation metric khỏi unique event/state |
| Coi event publish thành công là consumer đã xử lý | Không nhìn thấy lỗi hoặc độ trễ phía nhận | Theo dõi publish, delivery và processing riêng |
| Thêm `orderId` vào metric label | Cardinality tăng mạnh, metric khó tổng hợp | Dùng label ít biến thể; ID ở log/trace/event theo chính sách |
| Ghi event nghiệp vụ chỉ bằng log text | Không có schema, tính bền, replay và idempotency rõ ràng | Sử dụng hợp đồng event, ID, lưu trữ và phân phối phù hợp |
| Advice ghi log/metric ném lỗi làm use case thất bại | Quan sát trở thành tác nhân gây lỗi | Đảm bảo recorder best-effort hoặc xử lý lỗi theo hợp đồng rõ ràng |
| Gọi `join()` khi instrument async | Chặn luồng, thay đổi latency thực tế | Theo dõi callback hoặc mốc thực thi riêng |
| Một nghiệp vụ qua nhiều tầng đều bị pointcut bắt | Đếm nhiều invocation cho cùng một operation | Chọn ranh giới instrumentation; chuẩn hóa operation name |
| Tưởng không có trace là không có event | Trace có thể bị sampling/mất dữ liệu | Lấy nguồn sự kiện từ trạng thái/event store bền vững |

## 11. Kiểm thử đúng cả hai loại thông tin

Một bộ kiểm thử đủ sức phát hiện việc lẫn ranh giới nên bao gồm:

1. **Đường thành công:** xác nhận một thao tác nghiệp vụ hợp lệ tạo đúng event theo hợp đồng; metric ghi nhận invocation và thời gian.
2. **Đầu vào sai:** advice vẫn ghi error và thời lượng; không được tạo `OrderPlaced`.
3. **Rollback sau khi phương thức trả về:** nếu event đòi commit, không có event đã xác nhận; một bản ghi “method returned” kỹ thuật vẫn có thể tồn tại.
4. **Retry có cùng idempotency key:** số attempt tăng nhưng số event logic duy nhất không tăng theo.
5. **Broker hoặc consumer nhận trùng:** event ID không đổi khi retry; consumer không thực hiện tác dụng phụ nhiều lần.
6. **Tác vụ gửi thành công nhưng xử lý thất bại:** submission metric vẫn đúng, completion metric phản ánh thất bại, domain event chỉ tồn tại nếu điều kiện nghiệp vụ của nó đã đạt.
7. **Lỗi collector:** telemetry thất bại không che ngoại lệ hoặc thay đổi trạng thái nghiệp vụ, nếu chính sách telemetry là best-effort.
8. **Kiểm tra hiệu năng:** advice gây ít overhead, không tạo vòng gọi đệ quy vô hạn qua logger/collector, và việc bật/tắt quan sát không đổi kết quả domain.

Trong ví dụ Java ở trên, có thể kiểm ngay bất biến: `technical.count == 2`, `business.count == 1`, một lần ERROR không phát sinh event. Với ứng dụng có database và broker, cần kiểm thử tích hợp transaction/outbox thay vì chỉ kiểm thử method-call mock.

## 12. Cách tự xác định “đây là telemetry hay business event?”

Khi định thu thập một thông tin bằng AOP, hãy hỏi:

- **Nếu đổi cách cài đặt mà không đổi kết quả nghiệp vụ, thông tin này có thể đổi không?** Nếu có, rất có thể đó là telemetry: số method call, stack trace, latency, số retry.
- **Nếu telemetry collector mất dữ liệu thì sự thật nghiệp vụ có còn tồn tại không?** Một `OrderPlaced` đã commit không được phụ thuộc vào việc span có được lấy mẫu hay không.
- **Ai có quyền tuyên bố sự kiện đã xảy ra?** Phải là quy tắc domain và mốc hiệu lực đã định nghĩa, không phải tên pointcut.
- **Người tiêu thụ dùng nó để làm gì?** Dashboard hiệu năng dùng metric/trace; một workflow gửi hàng cần event đáng tin và cơ chế xử lý trùng.
- **Một lời gọi nhiều lần có thể cùng một sự thật nghiệp vụ không?** Nếu có retry/idempotency, phải tách invocation count khỏi event count.

**Nguyên tắc thực hành:** để AOP đo **hoạt động của phần mềm tại các ranh giới kỹ thuật**, còn domain quyết định **sự kiện nào thật sự có ý nghĩa và có hiệu lực**. Hai lớp có thể chia sẻ correlation ID để chẩn đoán, nhưng cần giữ riêng thời điểm, định danh, bảo đảm lưu trữ và ý nghĩa của từng loại dữ liệu.
