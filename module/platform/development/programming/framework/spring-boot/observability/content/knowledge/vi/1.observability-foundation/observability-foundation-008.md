# Khi nào cần custom instrumentation trong Spring Boot?

Trong module **SPRING_BOOT_OBSERVABILITY**, observability là khả năng hiểu ứng dụng đang làm gì từ **metrics, logs và distributed traces**, đặc biệt khi cần điều tra lỗi, độ trễ và hành vi trong môi trường thực. Spring Boot Actuator và Micrometer cung cấp nhiều điểm đo sẵn có; **custom instrumentation** là việc chủ động thêm điểm đo cho hành vi mà hệ thống chưa quan sát được ở mức cần thiết. Quyết định thêm điểm đo phải bắt đầu từ một **câu hỏi vận hành hoặc nghiệp vụ cụ thể**, thay vì chỉ từ mong muốn có thêm dữ liệu.

Ví dụ, một request `POST /checkout` mất 2 giây. Metric HTTP cho biết endpoint chậm, trace HTTP có thể cho biết một lời gọi mạng mất 1,6 giây, nhưng chưa chắc trả lời được: *thời gian nằm ở bước kiểm tra tồn kho, áp mã giảm giá hay xác thực thanh toán?* Nếu các bước đó quan trọng khi chẩn đoán hoặc đặt SLO, cần instrument trực tiếp chúng.

## 1. Xác định khoảng trống trong tín hiệu có sẵn

Với các dependency và cấu hình thích hợp, Spring Boot/Micrometer có thể tự cung cấp quan sát cho nhiều thành phần, chẳng hạn HTTP server, các HTTP client được hỗ trợ và một số tích hợp framework. Phạm vi thực tế **phụ thuộc phiên bản Spring Boot, thư viện, cách khởi tạo client và cấu hình**. Không nên mặc định rằng mọi truy vấn database, tác vụ nền, hàng đợi hoặc thư viện bên thứ ba đều đã được instrument.

Ví dụ một luồng xử lý:

```text
POST /checkout                       <-- HTTP server observation thường có sẵn
  ├─ validateCart()                  <-- Quy tắc nghiệp vụ: có thể chưa có
  ├─ reserveInventory()             <-- Bước nghiệp vụ: có thể chưa có
  ├─ authorizePayment()             <-- Bước nghiệp vụ: có thể chưa có
  │    └─ POST /provider/authorize  <-- HTTP client observation có thể có sẵn
  └─ publishOrderConfirmed()        <-- Hàng đợi/sự kiện: tùy tích hợp
```

Thông thường **không cần** thêm một timer hoặc span nữa cho toàn bộ `POST /checkout` nếu framework đã đo chính xác phần đó. Nhưng có thể cần một observation tên `payment.authorize` bao quanh nghiệp vụ xác thực thanh toán: nó có ý nghĩa ổn định ngay cả khi thay HTTP provider bằng SDK, và cho phép tách kết quả *approved*, *declined*, *error*.

Hãy kiểm tra dashboard, trace thực tế và tài liệu instrumentation của các dependency đang sử dụng trước khi quyết định thêm gì.

## 2. Khi nào nên và không nên thêm?

| Tình huống | Quyết định | Vì sao? |
| --- | --- | --- |
| Muốn biết tổng RPS, lỗi 5xx, p95 latency của một endpoint đã được Actuator đo | **Ưu tiên tín hiệu có sẵn** | Đo lại cùng phạm vi dễ sinh metric/span trùng và tăng chi phí |
| Cần phân biệt thời gian của từng bước `validateCart`, `reserveInventory`, `authorizePayment` | **Thêm Observation** tại bước có giá trị chẩn đoán | HTTP metric không thể hiện cấu trúc nghiệp vụ bên trong |
| Muốn biết số đơn chuyển sang kiểm duyệt thủ công theo lý do | **Thêm counter nghiệp vụ** | Đây là sự kiện nghiệp vụ, không phải latency của request |
| Tác vụ nền, scheduler, batch hoặc consumer thiếu trace/metric hữu ích | **Xem xét instrument** ranh giới tác vụ | Cần biết thời lượng, kết quả và liên hệ với tác vụ gốc |
| Cần phân biệt hai nhà cung cấp thanh toán có tập giá trị hữu hạn | **Thêm low-cardinality key-value** | Có thể lọc và so sánh latency/tỉ lệ lỗi theo provider |
| Muốn gắn `userId`, `orderId` hoặc URL đầy đủ vào mọi time series | **Không dùng làm metric tag** | Số tổ hợp nhãn tăng theo dữ liệu và có rủi ro riêng tư |
| Chỉ cần đọc một chi tiết lúc điều tra một giao dịch cụ thể | **Ưu tiên log có cấu trúc hoặc trace attribute phù hợp** | Không cần sinh metric series mới cho từng giao dịch |
| HTTP client đã tạo span con, nay muốn thêm span thứ hai cho chính cùng lời gọi HTTP | **Cân nhắc bỏ span trùng** | Span mới chỉ có ích nếu thể hiện một ranh giới nghiệp vụ khác |

**Nguyên tắc chọn:** thêm instrumentation khi nó giúp trả lời một câu hỏi còn bỏ ngỏ, dẫn tới hành động điều tra hoặc cảnh báo rõ ràng, và có chi phí cardinality/volume chấp nhận được.

## 3. Chọn đúng công cụ cho câu hỏi

Trong Micrometer, ba loại tín hiệu liên quan nhau nhưng không thay thế hoàn toàn cho nhau:

| Mục tiêu | Công cụ phù hợp | Ví dụ |
| --- | --- | --- |
| Đo **thời lượng và kết quả** của một thao tác; muốn có metric và trace tùy cấu hình | `ObservationRegistry` + `Observation` | `payment.authorize` |
| Đếm một **sự kiện nghiệp vụ** không gắn với thời lượng của một thao tác | `MeterRegistry` với `Counter` | `orders.manual_review` |
| Đo kích thước hàng đợi, số tác vụ đang chạy, trạng thái hiện thời | `Gauge` hoặc metric trạng thái có vòng đời rõ | Số job chờ xử lý |
| Ghi ngữ cảnh chẩn đoán, nguyên nhân lỗi, quyết định rẽ nhánh | Log có cấu trúc | `outcome=declined reason=insufficient_funds` |
| Theo dấu đường đi và quan hệ nhân quả qua các service | Trace/span và context propagation | Checkout → Payment → Provider |

**Observation** là API ở mức khái niệm thao tác. Nó đi qua các `ObservationHandler` và convention được cấu hình. Tùy hệ thống, một observation có thể tạo metric, span, cả hai hoặc không được xuất ra tín hiệu nào. Vì vậy, chỉ gọi `Observation.createNotStarted(...)` **không chứng minh** trace đã đến backend hay metric đã được scrape; cần kiểm tra registry, handler, tracing bridge và exporter trong môi trường triển khai.

**MeterRegistry** thích hợp khi thật sự cần counter, timer hoặc gauge chuyên biệt. Đừng đồng thời tạo `Observation` và một `Timer` thủ công cho cùng thao tác nếu chúng ghi cùng ý nghĩa: số liệu có thể bị đếm hai lần trong dashboard. Muốn truy vấn p95 ổn định từ nhiều instance, còn cần cấu hình histogram/percentile phù hợp với metric backend.

## 4. Ví dụ: instrument ranh giới nghiệp vụ xác thực thanh toán

Giả sử ứng dụng đã có `PaymentGateway`, `PaymentRequest` và `PaymentResult` trong domain. Dùng `ObservationRegistry` của Spring để đo toàn bộ **quyết định xác thực thanh toán**, bao gồm thời gian xử lý ở service và lời gọi gateway; tên observation không phụ thuộc endpoint vật lý của provider.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentAuthorizationService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentAuthorizationService(
            ObservationRegistry observationRegistry,
            PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentRequest request) {
        // method() và provider() trả về enum có số giá trị hữu hạn.
        String method = request.method().name().toLowerCase(java.util.Locale.ROOT);
        String provider = gateway.provider().name().toLowerCase(java.util.Locale.ROOT);

        Observation observation = Observation
                .createNotStarted("payment.authorize", observationRegistry)
                .contextualName("authorize payment")
                .lowCardinalityKeyValue("payment.method", method)
                .lowCardinalityKeyValue("payment.provider", provider);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            PaymentResult result = gateway.authorize(request);
            observation.lowCardinalityKeyValue(
                    "outcome", result.approved() ? "approved" : "declined");
            return result;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }
}
```

*Các kiểu `PaymentRequest`, `PaymentResult`, `PaymentGateway` là kiểu miền của ứng dụng giả định; thay bằng kiểu thực tế trong dự án. Phần minh họa tập trung vào vòng đời Observation.*

Ở đây:

1. `createNotStarted` tạo observation theo một **tên ổn định**, không chứa ID giao dịch; `contextualName` cung cấp tên dễ đọc cho trace nếu tracing handler hỗ trợ.
2. `start()` bắt đầu phép đo, `openScope()` đưa observation vào scope của thread hiện tại để các thao tác con có thể lấy ngữ cảnh cha. `Scope` được đóng tự động.
3. `outcome=approved` hoặc `declined` là kết quả nghiệp vụ. Từ chối thanh toán có thể là kết quả hợp lệ và **không nhất thiết là exception**.
4. Khi có lỗi kỹ thuật, `error(ex)` ghi nhận lỗi theo handler đang cấu hình; exception vẫn được ném lại để giữ hành vi của chương trình.
5. `stop()` trong `finally` giúp phép đo kết thúc trên cả đường thành công lẫn thất bại.

Nếu HTTP client được instrument tự động, trace có thể có cấu trúc sau:

```text
server: POST /checkout
  └─ custom: payment.authorize (outcome=approved)
       └─ client: POST /payments/authorize
```

Observation thủ công biểu đạt **nghiệp vụ xác thực thanh toán**; observation của HTTP client biểu đạt **lời gọi mạng**. Hai phép đo này có mục đích khác nhau, do đó có thể tồn tại cùng nhau mà không trùng nghĩa. Nếu provider timeout, người điều tra có thể biết độ trễ nằm ở gateway hay phần xử lý nội bộ. Việc có đầy đủ span cha/con còn tùy tracing được bật, sampling và propagation đúng.

### Dùng `@Observed` khi ranh giới là một phương thức

Nếu chỉ cần đo thời lượng và lỗi của phương thức Spring bean, annotation giúp giảm mã quản lý `start/stop`:

```java
import io.micrometer.observation.annotation.Observed;

@Observed(
    name = "pricing.calculate",
    contextualName = "calculate price",
    lowCardinalityKeyValues = {"component", "pricing"})
public PriceQuote calculate(PriceRequest request) {
    return pricingEngine.calculate(request);
}
```

Annotation này cần cơ chế **AOP interception** hoạt động, thường là có Spring AOP và đăng ký `ObservedAspect` với `ObservationRegistry`; chỉ đặt annotation không bảo đảm được instrument. Ví dụ cấu hình cho Spring Boot sử dụng AOP:

```java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ObservedConfiguration {
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
```

Với Spring proxy AOP, lời gọi **nội bộ từ một phương thức sang phương thức khác trên chính đối tượng đó** (self-invocation) thường không đi qua proxy, nên annotation có thể không được áp dụng. Cũng cần kiểm tra tránh đo chồng lên các phương thức HTTP/framework vốn đã được instrument. Khi cần thêm tag động phụ thuộc kết quả, xử lý exception theo miền hoặc quản lý scope phức tạp, API `Observation` thủ công thường rõ ràng hơn.

## 5. Quy tắc đặt tên và quản lý cardinality

Metric backend lưu dữ liệu theo các tổ hợp nhãn. Với ba nhãn lần lượt có 4, 5 và 1.000 giá trị, số tổ hợp có thể lên đến **4 × 5 × 1.000 = 20.000** cho một metric trước khi tính các chiều khác. Đây là lý do phải giới hạn key-value ngay từ lúc thiết kế.

| Thành phần | Nên | Tránh |
| --- | --- | --- |
| Observation name | `payment.authorize`, `inventory.reserve` | `payment.authorize.abc123` (ID nằm trong tên) |
| Low-cardinality key | `payment.method=card/bank_transfer/wallet` | `payment.customer_id=...` |
| Trạng thái | `outcome=approved/declined/error` | Thông báo lỗi nguyên văn làm nhãn |
| Provider | Tên chuẩn hóa thuộc danh sách hữu hạn | Hostname/URL do người dùng cung cấp |
| High-cardinality key | Mã truy vết nội bộ đã qua kiểm tra chính sách dữ liệu, chỉ khi cần | Email, token, số thẻ, thông tin định danh nhạy cảm |

Trong Micrometer Observation, `lowCardinalityKeyValue` thường được dùng cho **metric tags và trace attributes**; `highCardinalityKeyValue` hướng tới ngữ cảnh chi tiết của tracing và thường không được dùng để tạo time series bởi handler metric mặc định. Tuy vậy, handler tùy biến có thể xử lý khác. Hãy kiểm tra pipeline thực tế, giới hạn thu thập và quy tắc bảo vệ dữ liệu trước khi thêm cả high-cardinality attributes.

Một tên và bộ key ổn định đóng vai trò là **hợp đồng telemetry**: thay đổi tên có thể làm dashboard, alert và truy vấn lịch sử không còn khớp. Ưu tiên từ điển key được thống nhất và số trạng thái hữu hạn. Không dùng dữ liệu từ request thô làm key hoặc value của metric.

## 6. Khi nào dùng metric thủ công thay vì thêm span?

Một hành động kinh doanh có thể cần **đếm số lần xảy ra** nhưng không cần một duration/span riêng. Ví dụ, mỗi đơn chuyển sang luồng kiểm tra thủ công cần một counter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public void recordManualReview(MeterRegistry registry, ReviewReason reason) {
    // ReviewReason là enum hữu hạn: FRAUD_RULE, LIMIT, OTHER...
    Counter.builder("orders.manual_review")
            .description("Orders sent to manual review")
            .tag("reason", reason.name().toLowerCase(java.util.Locale.ROOT))
            .register(registry)
            .increment();
}
```

Một `Counter` cho biết **có bao nhiêu lần** đơn rơi vào nhánh này; nó không tự biểu diễn thời gian xử lý. Ngược lại, nếu cần p95 của `inventory.reserve` và liên hệ với trace của checkout, `Observation` thường là điểm khởi đầu tốt hơn. Nếu cần số job đang chờ, dùng một `Gauge` lấy trạng thái hiện tại thay vì cộng dồn counter rồi suy ra giá trị.

Lưu ý: khi `Observation` đã ghi số lần chạy và duration của chính thao tác, chỉ tạo thêm counter nếu nó đo **một sự kiện có ngữ nghĩa khác**. Thêm các meter vì “cho chắc” gây khó diễn giải khi dashboard.

## 7. Instrumentation khi đi qua thread, queue và service

Với tác vụ bất đồng bộ, thời lượng và trace của một request thường không đủ để thể hiện công việc xảy ra **sau khi trả HTTP response**. Khi đó cần cân nhắc đo ở ranh giới tác vụ:

- **Scheduler/batch:** tạo observation cho mỗi lần chạy job hoặc mỗi batch có ý nghĩa; ghi `outcome` hữu hạn và số bản ghi xử lý bằng meter thích hợp. Tránh một span cho từng item nếu khối lượng quá lớn.
- **Message producer/consumer:** kiểm tra instrumentation có sẵn của framework trước. Nếu thiếu, đo thời gian xử lý message và kết quả, xác định chính xác ranh giới ack/retry/dead-letter. Không xem một message được retry là một giao dịch duy nhất nếu các lần thử có ngữ nghĩa khác nhau.
- **Async executor/`CompletableFuture`:** scope của observation thường dựa vào ngữ cảnh gắn với thread; chuyển sang thread khác có thể mất quan hệ cha/con. Sử dụng cơ chế context propagation được framework và Micrometer hỗ trợ, ví dụ executor/task decoration hoặc Micrometer Context Propagation, theo stack đang dùng.
- **Qua service khác:** để trace liên tục, cần tracing bridge và propagator tương thích; thường dùng W3C Trace Context thông qua thư viện/framework. Không tự tạo `traceId` rồi truyền header tùy ý để thay thế chuẩn propagation.

Hai kiểm tra quan trọng: (1) span con thực sự nối vào đúng trace cha khi qua thread/service, và (2) log tại worker có thể tương quan với trace khi tracing và MDC correlation được cấu hình. **Một observation mở scope trên thread gốc không tự động bảo đảm propagation** tới mọi executor.

Sampling ảnh hưởng đến lượng trace được giữ hoặc xuất. Một trace không xuất hiện có thể do sampling, exporter hoặc lỗi propagation; không nên kết luận rằng thao tác không chạy. Metric vẫn có thể được ghi từ observation ngay cả khi trace của cùng thao tác không được lấy mẫu, tùy cấu hình handlers.

## 8. Những lỗi thiết kế thường gặp

**Đo trùng phạm vi.** Đặt `@Observed` trên HTTP controller đã có server observation, rồi lại tạo `Timer` cho toàn bộ request, tạo nhiều tín hiệu cùng ý nghĩa. Hãy đặt instrument ở ranh giới chưa được đo, như tính giá hoặc giữ tồn kho.

**Tag có giá trị vô hạn.** Đặt `orderId`, URL có query, raw exception message hay email vào low-cardinality key-value sẽ làm tăng mạnh số time series, chi phí lưu trữ và khả năng lộ dữ liệu.

**Gộp lỗi kỹ thuật với kết quả nghiệp vụ.** Một giao dịch bị từ chối hợp lệ (`declined`) khác lỗi timeout (`error`). Đặt hai trường hợp vào cùng một nhãn thất bại làm cảnh báo kém chính xác.

**Bỏ sót đường thất bại.** Quên `stop()` khi ném exception, hoặc bắt exception nhưng không ghi `observation.error(ex)`, khiến thời lượng/lỗi bị phản ánh sai.

**Span quá nhỏ và quá nhiều.** Thêm span cho mỗi hàm getter, từng item trong một batch khổng lồ hoặc mỗi vòng lặp sẽ tăng overhead và làm trace khó đọc. Hãy chọn các ranh giới có ý nghĩa vận hành, đo overhead khi tải cao.

**Nhầm logs với metrics.** Một log per request rất hữu ích để điều tra nhưng không tự tạo ra tỉ lệ lỗi đáng tin cậy; một metric tổng hợp tốt cho cảnh báo nhưng không chứa chi tiết từng giao dịch. Thiết kế ba tín hiệu để bổ trợ nhau và liên kết qua trace context khi thích hợp.

## 9. Quy trình ra quyết định và kiểm chứng

Trước khi thêm custom instrumentation, trả lời bốn câu hỏi:

1. **Cần quyết định điều gì?** Ví dụ: “p95 xác thực thanh toán tăng do xử lý tại service hay do provider?” Một câu hỏi cụ thể cho biết ranh giới cần instrument.
2. **Đã có tín hiệu đủ dùng chưa?** Xem metric HTTP, client spans, logs, built-in observations và phiên bản thư viện. Tách khoảng trống của tín hiệu khỏi vấn đề dashboard chưa được xây dựng.
3. **Tên và nhãn sẽ phát triển ra sao?** Liệt kê tên observation, từng nhãn và tập giá trị tối đa; đánh giá PII, overhead, sampling và chi phí exporter trước khi ghi.
4. **Kiểm chứng được trong ba kịch bản nào?** Chạy thành công, từ chối nghiệp vụ và lỗi kỹ thuật; quan sát đúng tên, thời lượng, outcome, lỗi, quan hệ span cha/con và correlation của log.

Với ví dụ `payment.authorize`, tiêu chí chấp nhận tối thiểu là:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Provider trả `approved` | `outcome=approved`; duration được đo; không đánh dấu exception |
| Provider trả `declined` hợp lệ | `outcome=declined`; không tự động biến thành lỗi kỹ thuật |
| Gateway ném exception | `outcome=error`; observation được stop; exception vẫn truyền lên caller |
| Có tracing và propagation | Span nghiệp vụ (nếu được lấy mẫu) là con đúng trace của checkout; lời gọi HTTP có quan hệ thích hợp |
| Quan sát metrics | Có series với tập nhãn hữu hạn; không có token, email, ID giao dịch hoặc URL động trong labels |

Tùy backend, cần kiểm tra cả **đường xuất dữ liệu**: Actuator/Micrometer tạo dữ liệu → observation handlers/tracing bridge → registry/exporter → backend (chẳng hạn Prometheus hoặc hệ thống thu trace) → dashboard và alert. Một phép đo không hiển thị chưa chắc do mã nghiệp vụ: có thể do exporter, endpoint scrape, sampling hay bộ lọc telemetry.

**Quy tắc áp dụng:** Custom instrumentation đáng làm khi biến một câu hỏi vận hành mơ hồ thành một tín hiệu có thể đối chiếu và hành động: *bước nào chậm, loại lỗi nào tăng, lần thử nào thất bại, điều gì xảy ra sau khi request kết thúc*. Thiết kế ít điểm đo nhưng đúng ranh giới, nhãn có kiểm soát, lỗi được ghi rõ và context được truyền đúng sẽ hữu ích hơn một lượng lớn span/metric thiếu ngữ nghĩa.
