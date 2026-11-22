# Discard versus exception khi validation fail

**Message Filter** trong Spring Integration quyết định một message có được đi tiếp hay không. Khi predicate trả `false`, có ba kết quả thường gặp: **bỏ message**, **đưa message vào `discardChannel`**, hoặc **ném exception**. Sự khác nhau không chỉ là cấu hình Java DSL: nó ảnh hưởng đến nghiệp vụ, độ tin cậy, retry, ACK broker, quan sát và cách người gửi nhận phản hồi.

Bài này thuộc chương **Message filter và validation** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu module là học triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, cùng kiểm thử và theo dõi các nhánh xử lý.

**Thông điệp chính:** Không đồng nhất *không được chọn bởi Filter* với *dữ liệu không hợp lệ*. Với trường hợp **không đủ điều kiện kinh doanh nhưng hợp lệ** (chẳng hạn không tham gia chương trình ưu đãi), discard có kiểm soát thường hợp lý. Với **vi phạm hợp đồng dữ liệu** hoặc hành vi không thể chấp nhận (thiếu ID bắt buộc, dữ liệu sai kiểu, không có quyền), cần có kết quả lỗi rõ ràng: throw exception, phản hồi validation error, hoặc tuyến quarantine có audit tùy kiến trúc. Đừng để lỗi hợp đồng quan trọng biến mất như một message được lọc bình thường.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **Filter predicate trả false** với **validator ném exception**.
2. Hiểu mặc định của Spring Integration `MessageFilter` khi một message bị từ chối.
3. Cấu hình `discardChannel`, `discardFlow` và `throwExceptionOnRejection(true)`.
4. Giải thích hành vi khi **discard channel và throw exception cùng được bật**.
5. Chọn xử lý cho expected rejection, malformed message, security rejection, transient dependency failure và lỗi nội bộ.
6. Đọc đúng `MessageRejectedException` so với exception từ validator/handler.
7. Phân biệt `discardChannel` với `errorChannel`; hiểu exception trong `DirectChannel` và async flow.
8. Viết Java DSL thể hiện rõ validation trước Filter và hai cách xử lý rejection.
9. Viết JUnit 5 unit test và integration test trên Spring channels thực.
10. Kiểm soát retry/redelivery, poison message, DLQ/quarantine và idempotency.
11. Thiết kế reason code, audit, metric, trace và cảnh báo mà không lộ dữ liệu.
12. Tránh làm mất business action khi Filter reject một part cần cho Aggregator.

## 2. Bài toán: hai loại "không được đi tiếp"

Giả sử một hệ thống nhận `InvoiceSubmission` và có chương trình ưu đãi chỉ áp dụng cho hóa đơn đủ điều kiện.

~~~text
InvoiceSubmission
  requestId = REQ-1001
  tenantId = tenant-a
  invoiceId = INV-1001
  amount = 250000 VND
  campaignEligible = false
~~~

Message trên **có định dạng hợp lệ**, số tiền hợp lệ, danh tính tồn tại; nó chỉ **không được chọn** để xử lý ưu đãi. Việc không đi qua nhánh ưu đãi **không phải lỗi nhập liệu**.

Một message khác:

~~~text
InvoiceSubmission
  requestId = REQ-1002
  tenantId = tenant-a
  invoiceId = ""
  amount = -15000 VND
  campaignEligible = true
~~~

Message này **vi phạm hợp đồng dữ liệu**: thiếu invoice ID và amount âm. Nếu chọn `campaignEligible=true` rồi gửi thẳng vào handler, hệ thống có thể gây lỗi hoặc ghi dữ liệu sai. Nếu chỉ loại âm thầm, người gửi và vận hành có thể không biết vì sao hóa đơn không được xử lý.

~~~mermaid
flowchart TD
    IN["Inbound message"] --> VALID{"Contract validation"}
    VALID -->|"Invalid"| ERR["Reject with reason / quarantine"]
    VALID -->|"Valid"| FILTER{"Business eligibility Filter"}
    FILTER -->|"Accepted"| NEXT["Normal processing"]
    FILTER -->|"Not eligible"| DISC["Discard/audit branch"]
~~~

**Validation** hỏi: *message có đáp ứng ràng buộc để hệ thống xử lý an toàn hay không?* **Filter** hỏi: *một message hợp lệ có được tham gia nhánh này hay không?* Hai quyết định có thể được kết hợp, nhưng càng tách rõ thì càng dễ test và vận hành.

## 3. Filter là gì trong Spring Integration?

Message Filter là một endpoint có `MessageSelector` hoặc một method/predicate trả boolean. Với mỗi message đi vào:

- `true`: message đi tới output channel của Filter.
- `false`: message không đi tới output channel bình thường; endpoint áp dụng **rejection policy**.
- Selector ném exception: đây là **handler failure**, không phải kết quả `false`; exception đi theo cơ chế xử lý lỗi của flow.

~~~mermaid
flowchart LR
    IN["Message input"] --> F{"MessageFilter predicate"}
    F -->|"true"| PASS["outputChannel"]
    F -->|"false"| R{"Rejection policy"}
    R --> DROP["Drop"]
    R --> DISC["discardChannel"]
    R --> EX["MessageRejectedException"]
~~~

Mỗi output của Filter được chọn **giữa pass và rejection**; Filter không tự route message tới một kênh ngẫu nhiên theo payload như content-based Router.

### 3.1. `false` không đồng nghĩa exception

Một predicate thuần:

~~~java
public boolean eligible(InvoiceSubmission invoice) {
    return invoice.campaignEligible();
}
~~~

trả `false` khi hóa đơn không tham gia chương trình. Nó **không ném lỗi**, không báo dữ liệu sai. Cấu hình của Filter mới quyết định kết quả `false` được drop, discard hay ném exception.

### 3.2. Ném exception trong predicate khác `throwExceptionOnRejection`

~~~java
public boolean check(InvoiceSubmission invoice) {
    if (invoice.invoiceId() == null
            || invoice.invoiceId().isBlank()) {
        throw new IllegalArgumentException(
                "INVOICE_ID_REQUIRED");
    }

    return invoice.campaignEligible();
}
~~~

Ở đây thiếu ID làm predicate **ném `IllegalArgumentException`**, không phải trả `false`. `throwExceptionOnRejection(true)` chỉ điều khiển đường **rejection khi selector trả false**, không biến mọi exception tùy ý thành `MessageRejectedException`.

## 4. Bốn lựa chọn xử lý rejection

Theo Spring Integration, Filter có `discardChannel` và `throwExceptionOnRejection`. Kết hợp hai cờ tạo bảng sau:

| `discardChannel` | `throwExceptionOnRejection` | Khi predicate trả false |
|---|---|---|
| Không cấu hình | `false` (mặc định) | Message bị drop, không đi qua normal output |
| Có | `false` | Message được gửi tới discard channel, không ném rejection exception |
| Không | `true` | Ném `MessageRejectedException` |
| Có | `true` | **Gửi tới discard channel, sau đó ném exception** |

**Cảnh báo:** lựa chọn cuối không có nghĩa "chỉ log và không fail". Discard handler có thể tạo một side effect rồi exception vẫn khiến caller/broker retry; nếu không có idempotency, side effect ở discard branch có thể bị lặp.

### 4.1. Mặc định: drop

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible)
~~~

Nếu selector trả `false` và không có discard/throw, message **không tới output channel**. Với phiên bản Spring Integration từ 6.1, MessageFilter có thể ghi **warning log** cho trường hợp bị drop mặc định; không nên mô tả hành vi là "không có dấu vết nào" trên mọi phiên bản.

### 4.2. Discard có chủ đích

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec.discardChannel("campaign.rejected"))
~~~

Khi `false`, message đi tới `campaign.rejected`. Đây là một **nhánh nghiệp vụ** để audit, đo rejected count hoặc thông báo "không đủ điều kiện". Không tự động coi đây là error channel.

### 4.3. Exception khi bị reject

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec.throwExceptionOnRejection(true))
~~~

Khi `false`, Filter ném `org.springframework.integration.MessageRejectedException`. Vì vậy **không nên bật flag này cho một business rule bình thường** nếu việc không được chọn là kết quả hợp lệ và upstream không mong nhận exception.

### 4.4. Cả discard và exception

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        spec -> spec
                .discardChannel("campaign.rejected")
                .throwExceptionOnRejection(true))
~~~

Message có thể đi qua discard branch **rồi** exception phát sinh. Nếu discard branch gọi một API gửi email còn broker retry message, email có thể gửi lặp. Chỉ dùng khi bạn thực sự muốn **ghi audit/quarantine rồi fail attempt**, và đã xác định idempotency, ACK và retry contract.

## 5. Khi nào chọn discard, khi nào chọn exception?

| Tình huống | Bản chất | Hướng xử lý thường phù hợp | Vì sao |
|---|---|---|---|
| Hóa đơn không đủ điều kiện ưu đãi | Expected business skip | Discard/explicit skip outcome | Không phải lỗi |
| Event đã quá cũ, được policy bỏ qua | Expected stale message | Discard có metric | Tránh retry vô ích |
| Message duplicate đã được xử lý | Expected idempotent no-op | Dedup discard hoặc cached result | Không chạy lại side effect |
| Thiếu invoice ID bắt buộc | Contract violation | Validation exception hoặc quarantine | Không thể xử lý an toàn |
| Amount âm ngoài contract | Contract violation | Exception/reject với reason | Producer phải sửa |
| Payload sai schema/kiểu | Contract violation | Reject, non-retryable | Retry y nguyên thường vô ích |
| User không có quyền | Security/authorization failure | Deny + audit, có thể exception | Không được chuyển tới handler |
| Payment API timeout | Transient dependency failure | Exception + bounded retry/reconciliation | Không phải business filter false |
| DB deadlock | Infrastructure failure | Retry theo policy | Không được drop như invalid |
| Hóa đơn đã hủy trước khi chạy ưu đãi | Domain policy | Discard hoặc explicit state transition | Tùy SLA/contract |
| Không tìm thấy foreign-key reference | Có thể tạm thời hoặc vĩnh viễn | Reconcile/retry có giới hạn hoặc reject | Cần phân loại nguồn lỗi |

**Không có mapping chung** "invalid = luôn retry". Exception cần một **lỗi được phân loại**: lỗi dữ liệu mang tính xác định thường phải đưa vào non-retryable rejection hoặc quarantine, không gửi broker retry vô hạn.

## 6. Discard channel không phải error channel

Hai channel có nguồn message và mục đích khác nhau:

| Thuộc tính | `discardChannel` | `errorChannel` |
|---|---|---|
| Nguồn vào | Selector `false` và Filter cấu hình discard | Exception được error infrastructure phát |
| Payload thường gặp | **Message gốc bị từ chối** | `ErrorMessage` chứa Throwable |
| Điều kiện kích hoạt | Business/validation predicate rejection | Handler/poller/async exception |
| Thông tin lý do | Không tự có reason code chi tiết | Throwable/cause chain |
| Có nghĩa retry? | Không | Phụ thuộc error handler/adapter |
| Có thể nối audit? | Có | Có |
| Có bảo đảm ACK? | Không tự động | Không tự động |

Ví dụ:

~~~text
Filter returns false
  -> discardChannel: Message<InvoiceSubmission>

Filter throws MessageRejectedException in async task
  -> errorChannel (nếu được error handler route):
     ErrorMessage(Throwable)
~~~

**Không gửi ngẫu nhiên một original message vào `errorChannel` rồi mong downstream nhận `ErrorMessage`.** Hai contract payload khác nhau.

### 6.1. Discard không có nghĩa đã xử lý thành công nghiệp vụ

Một MessageFilter gửi message vào discard channel chỉ cho biết nó **không đi qua normal output**. Nếu một outbound broker cần ACK hoặc một Gateway cần reply, contract riêng mới quyết định gọi đó là "đã hoàn tất" hay "chưa xử lý".

### 6.2. Discard làm mất thông tin lý do nếu không thiết kế

Một rejected message đi vào discard channel thường là **message gốc**. Không mặc nhiên có header `validationReason` hoặc danh sách constraint failures.

Nếu cần lý do:

- Tính và validate ở một bước trước Filter.
- Chỉ gắn **reason code an toàn** sau khi phân loại.
- Hoặc discard flow tự gọi một pure classifier trên payload để tạo `RejectionRecord`.
- Không copy toàn bộ payload chứa PII sang log/metric.
- Cẩn thận nếu một predicate đọc current database state: khi discard flow đánh giá lại, kết quả có thể khác.

## 7. Phân loại lỗi validation: cấu trúc, business rule và hạ tầng

Từ "validation" được dùng cho nhiều việc không giống nhau:

1. **Structural validation**: thiếu ID, amount sai phạm vi, schema không tương thích.
2. **Business invariant validation**: invoice thuộc tenant khác, transition không hợp lệ, không đủ tồn kho bắt buộc.
3. **Eligibility check**: đúng định dạng nhưng không thuộc segment của chương trình ưu đãi.
4. **Authentication/authorization**: người gửi không có quyền tác động tài nguyên.
5. **Infrastructure availability**: database, broker, external API đang lỗi.

Một cùng phương thức Java trả `boolean` cho tất cả năm loại sẽ khó phân biệt **skip hợp lệ**, **lỗi phải sửa**, **lỗi có thể retry** và **an ninh**.

### 7.1. Quyết định dựa trên khả năng phục hồi

~~~mermaid
flowchart TD
    X["Message bị từ chối hoặc xử lý lỗi"] --> Q{"Đây là một kết quả business hợp lệ?"}
    Q -->|"Có"| D["Discard + audit/metric hoặc explicit result"]
    Q -->|"Không"| R{"Cùng message retry có thể thành công?"}
    R -->|"Không"| N["Reject + non-retryable quarantine/feedback"]
    R -->|"Có"| T["Exception + bounded retry/backoff"]
    R -->|"Không chắc"| U["Reconciliation/UNKNOWN state"]
~~~

Không biến validation fail thành `false` **chỉ để tránh exception** nếu upstream cần biết vì sao không nhận được dữ liệu.

## 8. Model Java 17 dùng trong các ví dụ

Ví dụ invoice submission:

~~~java
import java.math.BigDecimal;

public record InvoiceSubmission(
        String requestId,
        String tenantId,
        String invoiceId,
        BigDecimal amount,
        boolean campaignEligible
) {}
~~~

Record có thể chứa dữ liệu chưa hợp lệ; vì muốn test rõ, ta **không chặn bằng constructor** trong ví dụ. Tại ingress, `SubmissionValidator` sẽ kiểm tra các trường.

### 8.1. Enum reason code

~~~java
public enum ValidationCode {
    REQUEST_ID_REQUIRED,
    TENANT_ID_REQUIRED,
    INVOICE_ID_REQUIRED,
    AMOUNT_REQUIRED,
    AMOUNT_MUST_BE_POSITIVE
}
~~~

### 8.2. Domain validation exception

~~~java
import java.util.List;

public final class InvalidSubmissionException
        extends RuntimeException {

    private final List<ValidationCode> codes;

    public InvalidSubmissionException(
            List<ValidationCode> codes) {
        super("INVALID_INVOICE_SUBMISSION");
        this.codes = List.copyOf(codes);
    }

    public List<ValidationCode> codes() {
        return codes;
    }
}
~~~

### 8.3. Pure validator với danh sách lỗi có cấu trúc

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public final class SubmissionValidator {

    public List<ValidationCode> validate(
            InvoiceSubmission submission) {

        if (submission == null) {
            return List.of(ValidationCode.REQUEST_ID_REQUIRED);
        }

        List<ValidationCode> failures = new ArrayList<>();

        if (blank(submission.requestId())) {
            failures.add(ValidationCode.REQUEST_ID_REQUIRED);
        }
        if (blank(submission.tenantId())) {
            failures.add(ValidationCode.TENANT_ID_REQUIRED);
        }
        if (blank(submission.invoiceId())) {
            failures.add(ValidationCode.INVOICE_ID_REQUIRED);
        }
        if (submission.amount() == null) {
            failures.add(ValidationCode.AMOUNT_REQUIRED);
        }
        else if (submission.amount()
                .compareTo(BigDecimal.ZERO) <= 0) {
            failures.add(ValidationCode.AMOUNT_MUST_BE_POSITIVE);
        }

        return List.copyOf(failures);
    }

    public boolean isValid(InvoiceSubmission submission) {
        return validate(submission).isEmpty();
    }

    public InvoiceSubmission requireValid(
            InvoiceSubmission submission) {

        List<ValidationCode> failures = validate(submission);
        if (!failures.isEmpty()) {
            throw new InvalidSubmissionException(failures);
        }

        return submission;
    }

    private boolean blank(String input) {
        return input == null || input.isBlank();
    }
}
~~~

Đây là **validation nội dung dữ liệu**. Kiểm tra `tenantId` có đúng principal được xác thực hay không là trách nhiệm riêng ở security boundary. Không dùng `campaignEligible` như điều kiện structural validity vì một hóa đơn không tham gia chương trình vẫn hợp lệ.

### 8.4. Vì sao tách requireValid khỏi isValid?

- `isValid` phù hợp với boolean Filter khi chỉ cần kết quả true/false.
- `requireValid` ném exception giàu reason codes, thuận tiện phản hồi producer hoặc xử lý non-retryable error.
- `validate` là logic thuần, dùng được trong unit test, quarantine classifier và API validation.

Một Filter `throwExceptionOnRejection(true)` chỉ cung cấp `MessageRejectedException` theo việc selector trả false; nó không tự chứa đầy đủ danh sách `ValidationCode`. Nếu cần reason, ưu tiên explicit validator hoặc có adapter bổ sung reason metadata.

## 9. Cách A: reject có discard channel khi business không đủ điều kiện

Flow minh họa hai bước **validation trước, eligibility filter sau**:

~~~text
Inbound InvoiceSubmission
  -> requireValid (invalid: exception)
  -> campaignEligible?
       true  -> accepted output
       false -> discard channel
~~~

### 9.1. Java DSL configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DiscardOnBusinessSkipConfig {

    @Bean
    public SubmissionValidator submissionValidator() {
        return new SubmissionValidator();
    }

    @Bean(name = "campaign.discard.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "campaign.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "campaign.discarded")
    public PollableChannel discarded() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow campaignFilterFlow(
            SubmissionValidator validator) {

        return IntegrationFlow
                .from("campaign.discard.in")
                .transform(
                        InvoiceSubmission.class,
                        validator::requireValid)
                .filter(
                        InvoiceSubmission.class,
                        InvoiceSubmission::campaignEligible,
                        f -> f.discardChannel("campaign.discarded"))
                .channel("campaign.accepted")
                .get();
    }
}
~~~

Đây là flow **đồng bộ tại DirectChannel** và output queues phục vụ test. Với message hợp lệ nhưng không eligible, endpoint không ném rejection exception; nó gửi message tới `campaign.discarded`. Với message invalid, `requireValid` ném `InvalidSubmissionException` **trước khi Filter**, không gọi discard branch.

### 9.2. Vì sao không Filter trực tiếp trên invoiceId?

Nếu dùng:

~~~java
.filter(InvoiceSubmission.class,
        invoice -> invoice.invoiceId() != null)
~~~

thì một message thiếu ID có thể bị **drop mặc định** rồi producer không nhận được reason. Khi dữ liệu quan trọng, nên **phân loại** và trả kết quả hợp đồng rõ ràng thay vì dùng silent filter.

### 9.3. Discard branch có ý nghĩa nghiệp vụ

Khi campaign không áp dụng, discard branch có thể phát `CampaignNotEligible` event hoặc cập nhật trạng thái SKIPPED. Nhưng nó không nên mặc nhiên xóa hóa đơn khỏi toàn bộ hệ thống: Filter ở đây chỉ điều khiển **nhánh campaign**, không quyết định invoice có tồn tại hay không.

## 10. Cách B: throw exception khi selector từ chối validation

Ví dụ sau diễn giải kiểu cấu hình `throwExceptionOnRejection(true)`. Nó phù hợp khi selector **chỉ thực hiện validation** và caller cần biết dữ liệu không đạt contract.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class ThrowOnInvalidConfig {

    @Bean
    public SubmissionValidator strictValidator() {
        return new SubmissionValidator();
    }

    @Bean(name = "strict.validation.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "strict.validation.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow strictValidationFlow(
            SubmissionValidator validator) {

        return IntegrationFlow
                .from("strict.validation.in")
                .filter(
                        InvoiceSubmission.class,
                        validator::isValid,
                        f -> f.throwExceptionOnRejection(true))
                .channel("strict.validation.accepted")
                .get();
    }
}
~~~

Khi `isValid` trả false:

- Message **không** đi tới `strict.validation.accepted`.
- Filter ném một `MessageRejectedException`.
- Với `DirectChannel` đồng bộ, exception có thể lan về caller của `send()`.
- Không có `discardChannel` ở flow này.
- Exception có thể được wrapper theo endpoint/call stack; nên kiểm tra cause chain trong test.

### 10.1. Khi cần reason chi tiết

`MessageRejectedException` diễn đạt **Filter selector từ chối**, nhưng không tự cung cấp `ValidationCode.INVOICE_ID_REQUIRED` hay `AMOUNT_MUST_BE_POSITIVE`. Nếu API phải trả reason codes, hãy dùng `requireValid` như một Transformer/Service Activator ở bước trước và map `InvalidSubmissionException` vào response hoặc error flow phù hợp.

### 10.2. Đừng áp dụng throw cho mọi business false

Nếu cùng Filter gồm cả contract validation lẫn `campaignEligible`:

~~~java
.filter(InvoiceSubmission.class,
        invoice -> validator.isValid(invoice)
                && invoice.campaignEligible(),
        f -> f.throwExceptionOnRejection(true))
~~~

thì một invoice hợp lệ nhưng không tham gia chương trình cũng làm phát sinh `MessageRejectedException`, thường là **sai ngữ nghĩa**. Nên tách validation và eligibility filter như flow ở mục 9.

## 11. Cách C: drop mặc định và `nullChannel`

Khi không cấu hình discard và throw, Filter drop message bị từ chối:

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible)
~~~

Từ Spring Integration **6.1**, default drop (không có discard và không throw) có thể được ghi warning bởi MessageFilter. Khi chủ đích chấp nhận bỏ message không cần log warning, có thể định hướng rejected message sang built-in `nullChannel`:

~~~java
.filter(InvoiceSubmission.class,
        InvoiceSubmission::campaignEligible,
        f -> f.discardChannel("nullChannel"))
~~~

**Chỉ dùng với thông điệp có thể bỏ đúng hợp đồng**, ví dụ một event telemetry quá cũ hoặc một nhánh ưu đãi không áp dụng. Không dùng `nullChannel` cho financial command, dữ liệu cần audit hay trường hợp producer cần nhận feedback.

### 11.1. Silent drop không phải fallback

Một message bị drop sẽ không tự đi sang subscriber khác của input channel theo nghĩa "đợi người xử lý phù hợp hơn". Khi có nhiều selective consumers trên point-to-point channel, interaction giữa dispatcher và handler rejection cần được thiết kế và kiểm thử riêng; `throwExceptionOnRejection` có thể ảnh hưởng dispatch strategy, nhưng không nên lợi dụng mặc định drop để mô phỏng Router.

## 12. Khi cấu hình cả discard và throw: side effect kép

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant F as MessageFilter
    participant D as Discard handler
    participant E as Error handling

    P->>F: InvoiceSubmission
    F->>F: predicate=false
    F->>D: Gửi original message tới discardChannel
    D-->>F: Discard branch đã xử lý
    F--xP: Ném MessageRejectedException
    P->>E: Có thể retry/reject theo transport
~~~

Một discarded message có thể đã được log, ghi DB hoặc phát ra broker **trước khi** exception kích hoạt retry. Nếu discard handler có side effect không idempotent:

~~~text
Attempt 1:
  discard -> gửi email từ chối
  exception -> broker retry

Attempt 2:
  discard -> gửi email từ chối lần thứ hai
  exception -> retry tiếp
~~~

Chỉ dùng cả hai khi thật sự muốn **audit/quarantine rồi báo lỗi**, và đã thiết kế chống lặp và retry category đúng. Nếu discard branch chỉ tạo log/metric, nó vẫn có thể bị nhân đôi; metrics cần nói rõ đếm attempts hay unique rejected messages.

### 12.1. `discardWithinAdvice`

Spring Integration hỗ trợ `discardWithinAdvice` (mặc định true) để quyết định discard/exception xảy ra **bên trong hay bên ngoài phạm vi advice chain** của Filter. Nếu có retry advice:

- Discard trong advice có thể khiến **cả discard handler** được retry khi lỗi.
- Throw trong advice có thể khiến retry advice thử lại rejection nếu không phân loại.
- `discardWithinAdvice(false)` thay đổi phạm vi advice, nhưng không tự giải quyết semantic retry.

Cần kiểm thử chính xác topology khi có transaction advice, retry advice, Wire Tap hoặc handler ở discard channel. Không dùng tùy chọn này để che lỗi dữ liệu.

## 13. XML và annotation: tương đương về ý nghĩa

### 13.1. XML filter với discard channel

~~~xml
<int:filter
    id="campaignFilter"
    input-channel="campaignInput"
    output-channel="campaignAccepted"
    ref="eligibilitySelector"
    method="eligible"
    discard-channel="campaignRejected"/>
~~~

### 13.2. XML filter với exception

~~~xml
<int:filter
    id="strictValidationFilter"
    input-channel="strictInput"
    output-channel="strictAccepted"
    ref="validationSelector"
    method="isValid"
    throw-exception-on-rejection="true"/>
~~~

Ví dụ XML giả định namespace `int` đã được khai báo và các beans/channels thực đã tồn tại. Chúng minh họa chính sách tương ứng, không phải XML document chạy độc lập.

### 13.3. Annotation `@Filter`

~~~java
import org.springframework.integration.annotation.Filter;

public final class EligibilitySelector {

    @Filter(
        inputChannel = "campaignInput",
        outputChannel = "campaignAccepted",
        discardChannel = "campaignRejected")
    public boolean eligible(InvoiceSubmission invoice) {
        return invoice.campaignEligible();
    }
}
~~~

Annotation endpoint cần được phát hiện/đăng ký vào Spring context và channel names phải hợp lệ. Không khai báo đồng thời annotation và Java DSL endpoint **cùng lắng nghe một input** nếu mục tiêu chỉ có một consumer.
## 14. Unit test: validation và expected skip là hai thứ khác nhau

Trước khi kiểm thử channel, ta kiểm tra `SubmissionValidator` thuần. Test phải chứng minh **invoice hợp lệ nhưng không đủ điều kiện chương trình vẫn valid**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubmissionValidatorTest {

    private final SubmissionValidator validator =
            new SubmissionValidator();

    @Test
    void validButNotEligibleStillPassesValidation() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1001", "tenant-a", "INV-1001",
                new BigDecimal("250000"), false);

        assertTrue(validator.isValid(input));
        assertFalse(input.campaignEligible());
        assertSame(input, validator.requireValid(input));
    }

    @Test
    void invalidReportsMultipleReasonCodes() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1002", "tenant-a", "",
                new BigDecimal("-100"), true);

        assertEquals(
                List.of(
                    ValidationCode.INVOICE_ID_REQUIRED,
                    ValidationCode.AMOUNT_MUST_BE_POSITIVE),
                validator.validate(input));

        InvalidSubmissionException error = assertThrows(
                InvalidSubmissionException.class,
                () -> validator.requireValid(input));

        assertEquals(2, error.codes().size());
    }

    @Test
    void amountNullIsInvalidWithoutNullPointer() {
        InvoiceSubmission input = new InvoiceSubmission(
                "REQ-1003", "tenant-a", "INV-1003",
                null, false);

        assertEquals(
                List.of(ValidationCode.AMOUNT_REQUIRED),
                validator.validate(input));
    }
}
~~~

Unit tests này không chứng minh Spring channel routing hoặc broker ACK. Chúng chỉ kiểm tra **hợp đồng dữ liệu** và reason codes.

## 15. Integration test: pass, discard, validation exception

`DiscardOnBusinessSkipConfig` ở mục 9 dùng `DirectChannel` ở input và hai `QueueChannel` ở output. Test dưới đây xác minh ba trường hợp khác nhau trên endpoint thật.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = DiscardOnBusinessSkipConfig.class)
class CampaignDiscardFlowTest {

    @Autowired @Qualifier("campaign.discard.in")
    MessageChannel input;

    @Autowired @Qualifier("campaign.accepted")
    PollableChannel accepted;

    @Autowired @Qualifier("campaign.discarded")
    PollableChannel discarded;

    private InvoiceSubmission input(
            String id, boolean eligible) {

        return new InvoiceSubmission(
                "REQ-" + id, "tenant-a", id,
                new BigDecimal("250000"), eligible);
    }

    @Test
    void passesEligibleMessage() {
        InvoiceSubmission submitted = input("INV-2001", true);

        assertTrue(input.send(
                MessageBuilder.withPayload(submitted).build()));

        Message<?> message = accepted.receive(1000);
        assertNotNull(message);
        assertEquals(submitted, message.getPayload());
        assertNull(discarded.receive(0));
    }

    @Test
    void discardsValidButNotEligibleMessage() {
        InvoiceSubmission submitted = input("INV-2002", false);

        assertTrue(input.send(
                MessageBuilder.withPayload(submitted).build()));

        Message<?> message = discarded.receive(1000);
        assertNotNull(message);
        assertEquals(submitted, message.getPayload());
        assertNull(accepted.receive(0));
    }

    @Test
    void validationFailureThrowsBeforeFilter() {
        InvoiceSubmission invalid = new InvoiceSubmission(
                "REQ-2003", "tenant-a", "",
                new BigDecimal("-10"), false);

        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

        assertTrue(ErrorCauseChecks.contains(
                error, InvalidSubmissionException.class));
        assertNull(accepted.receive(0));
        assertNull(discarded.receive(0));
    }
}
~~~

Vì Spring messaging layer có thể bọc exception, ta kiểm tra cause chain thay vì hardcode wrapper cụ thể:

~~~java
public final class ErrorCauseChecks {

    private ErrorCauseChecks() {}

    public static boolean contains(
            Throwable thrown,
            Class<? extends Throwable> expected) {

        Throwable current = thrown;
        while (current != null) {
            if (expected.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

`ErrorCauseChecks` nằm trong source file test riêng. Để tránh shared queue contamination khi các test dùng chung cached context, nên drain output sau mỗi test hoặc cô lập context; không trộn với test có group/queue chưa hoàn tất.

**Test chứng minh:** message hợp lệ/eligible đi normal output; hợp lệ/not eligible đi discard; invalid ném exception **trước** business Filter. Nó không chứng minh broker ACK/NACK, vì flow trong ví dụ chỉ có các channel local.

## 16. Integration test: `throwExceptionOnRejection(true)`

Kiểm thử `ThrowOnInvalidConfig` từ mục 10:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ThrowOnInvalidConfig.class)
class StrictValidationFlowTest {

    @Autowired @Qualifier("strict.validation.in")
    MessageChannel input;

    @Autowired @Qualifier("strict.validation.accepted")
    PollableChannel accepted;

    @Test
    void invalidInputCausesMessageRejectedException() {
        InvoiceSubmission invalid = new InvoiceSubmission(
                "REQ-3001", "tenant-a", "",
                new BigDecimal("-100"), true);

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(invalid).build()));

        assertTrue(ErrorCauseChecks.contains(
                thrown, MessageRejectedException.class));
        assertNull(accepted.receive(0));
    }

    @Test
    void validButNotEligiblePassesStrictValidation() {
        InvoiceSubmission valid = new InvoiceSubmission(
                "REQ-3002", "tenant-a", "INV-3002",
                new BigDecimal("100"), false);

        assertTrue(input.send(
                MessageBuilder.withPayload(valid).build()));

        Message<?> result = accepted.receive(1000);
        assertNotNull(result);
        assertEquals(valid, result.getPayload());
    }
}
~~~

Lưu ý: `throwExceptionOnRejection` áp dụng cho selector **trả false**. Nếu chính selector ném một exception khác, đó là lỗi từ code của selector; không nên mặc định cause chain có `MessageRejectedException`.

Không test bằng `MessageBuilder.withPayload(null)`, vì builder có thể từ chối null trước khi message tới Filter. Để test thiếu dữ liệu, hãy đưa field null/blank trong DTO, hoặc test decoding tại inbound adapter.

## 17. Integration test: discard rồi vẫn throw

Trường hợp bật **cả discard và throw** dễ gây side effect lặp khi retry. Flow minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class BothPoliciesConfig {

    @Bean(name = "both.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "both.accepted")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "both.discarded")
    public PollableChannel discarded() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow bothPoliciesFlow() {
        return IntegrationFlow.from("both.in")
                .filter(
                    InvoiceSubmission.class,
                    InvoiceSubmission::campaignEligible,
                    spec -> spec
                            .discardChannel("both.discarded")
                            .throwExceptionOnRejection(true))
                .channel("both.accepted")
                .get();
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = BothPoliciesConfig.class)
class BothPoliciesFlowTest {

    @Autowired @Qualifier("both.in")
    MessageChannel input;

    @Autowired @Qualifier("both.discarded")
    PollableChannel discarded;

    @Autowired @Qualifier("both.accepted")
    PollableChannel accepted;

    @Test
    void rejectedMessageIsDiscardedAndExceptionStillThrown() {
        InvoiceSubmission excluded = new InvoiceSubmission(
                "REQ-4001", "tenant-a", "INV-4001",
                new BigDecimal("100"), false);

        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(
                    MessageBuilder.withPayload(excluded).build()));

        assertTrue(ErrorCauseChecks.contains(
                error, MessageRejectedException.class));

        Message<?> message = discarded.receive(1000);
        assertNotNull(message);
        assertEquals(excluded, message.getPayload());
        assertNull(accepted.receive(0));
    }
}
~~~

Khi caller hoặc broker retry vì exception, discard handler **có thể xử lý lại cùng message**. Nếu discard branch tạo audit row hoặc phát notification, dùng idempotency key ổn định (`requestId` hoặc `eventId` đúng phạm vi), không dựa vào `MessageHeaders.ID` khi redelivery có thể tạo message instance mới.

## 18. Exception đồng bộ và bất đồng bộ

Một Filter ném `MessageRejectedException` nhưng nơi quan sát exception phụ thuộc topology.

### 18.1. DirectChannel: exception có thể trở về caller

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant D as DirectChannel
    participant F as MessageFilter
    C->>D: send(message)
    D->>F: handleMessage
    F--xC: MessageRejectedException
~~~

`DirectChannel` gọi handler trên sender thread. Vì vậy synchronous caller có thể bắt exception. Nếu flow được mở bằng HTTP/Gateway, việc map exception sang status code là **trách nhiệm adapter/gateway**, không phải chức năng tự động của Filter.

### 18.2. ExecutorChannel/poller: cần xử lý lỗi async

~~~mermaid
sequenceDiagram
    participant C as Producer
    participant E as ExecutorChannel
    participant F as MessageFilter
    participant H as Error handler

    C->>E: send(message)
    E-->>C: Dispatched/accepted
    E->>F: handleMessage trên worker thread
    F--xH: MessageRejectedException
    H->>H: ErrorMessage theo cấu hình
~~~

Nếu handler chạy trên task thread, producer có thể đã quay về và **không thể nhận exception qua call stack cũ**. Một `MessagePublishingErrorHandler` hoặc cơ chế lỗi của adapter có thể gửi `ErrorMessage` tới header `errorChannel` hoặc global `errorChannel`.

**Không khẳng định mọi exception đồng bộ tự vào `errorChannel`.** Hãy xác định rõ executor, poller, inbound adapter và error handler đang dùng.

### 18.3. ErrorMessage có payload khác discard

~~~text
Filter predicate=false
  -> discardChannel:
     Message<InvoiceSubmission>

Async handler exception
  -> errorChannel (nếu được route):
     ErrorMessage<Throwable>
~~~

Nếu handler discard cố cast `ErrorMessage` hoặc handler error cố cast payload thành `InvoiceSubmission`, sẽ phát sinh lỗi thứ cấp. Viết hai consumer theo đúng contract của kênh tương ứng.

## 19. Discard, quarantine, DLQ và error channel

| Cơ chế | Thường chứa gì | Sử dụng khi nào |
|---|---|---|
| `discardChannel` | Original rejected Message | Expected business rejection |
| Quarantine ứng dụng | Envelope có reason code/source/tracking | Dữ liệu cần sửa/điều tra |
| Broker DLQ | Message không delivery thành công theo broker policy | Retry exhausted hoặc reject không requeue |
| `errorChannel` | ErrorMessage với Throwable | Handler/poller/async exception |
| Audit stream | Outcome và metadata an toàn | Quan sát/tuân thủ |

**Discard channel không tự trở thành DLQ.** Nếu cần đưa message vào broker, phải cấu hình outbound adapter, ACK/NACK và retention riêng.

Một quarantine record ví dụ:

~~~java
import java.time.Instant;
import java.util.List;

public record RejectedEnvelope(
        String requestId,
        String tenantId,
        List<ValidationCode> validationCodes,
        String source,
        Instant rejectedAt
) {}
~~~

Đây là record **do ứng dụng tạo**, không phải metadata tự gắn bởi Filter. Nếu lưu payload gốc, cần encryption, masking, access control và TTL phù hợp.

### 19.1. Lý do discard không tự có

Nếu predicate trả false, Spring Integration không tự biến nó thành `ValidationCode.INVOICE_ID_REQUIRED`. Để giữ reason:

1. Dùng classifier/validator thuần tính code trước Filter.
2. Đưa code an toàn vào một outcome/envelope của ứng dụng.
3. Hoặc tạo typed exception với danh sách codes.
4. Không dùng raw exception text chứa PII làm taxonomy.
5. Không gọi lại API bất ổn trong discard branch chỉ để "đoán lý do".

### 19.2. Non-retryable khác transient

Một payload thiếu invoiceId là lỗi **deterministic**, retry nguyên payload nhiều lần thường vô ích. Database timeout hoặc lỗi mạng là **transient**, có thể thành công sau backoff. Cả hai có thể ném exception, nhưng đường retry/quarantine phải được **phân loại**.
## 20. Retry, ACK và poison message

### 20.1. Discard thành công có thể là một attempt hoàn tất

Khi Filter trả false, gửi message vào discard channel và **không ném exception**, nhiều inbound adapters có thể xem handler invocation đã hoàn thành rồi ACK theo cấu hình. Nhưng đây là **hành vi phụ thuộc adapter/transaction**, không phải bảo đảm chung của `discardChannel`.

Cần kiểm tra thực tế:

- Consumer auto-ack hay manual-ack?
- ACK xảy ra trước hay sau khi discard branch xử lý xong?
- Discard branch có transaction riêng không?
- Message tới broker outbound có bảo đảm lưu bền trước ACK không?
- Nếu discard handler thất bại, exception có được truyền về listener không?
- Khi reprocess từ quarantine, idempotency key có ổn định không?

Một `MessageChannel.send()` trả true cũng không tự chứng minh business side effect đã commit.

### 20.2. Exception có thể làm message redeliver

Với một broker adapter, exception có thể dẫn đến rollback/NACK/requeue theo cấu hình. Nếu input vĩnh viễn không hợp lệ:

~~~text
Malformed message
  -> throwExceptionOnRejection(true)
  -> redelivery
  -> same validation failure
  -> redelivery mãi
~~~

Đây là **poison message loop**. Giải pháp:

1. Đánh dấu lỗi deterministic validation là **non-retryable**.
2. Chuyển vào quarantine hoặc DLQ theo contract của broker.
3. Tránh requeue vô hạn; có max attempts/backoff với transient errors.
4. Chỉ reprocess khi dữ liệu được sửa hoặc hợp đồng thay đổi.
5. Ghi nguồn event, stable event ID và reason codes để chẩn đoán.

### 20.3. DB timeout không phải Filter false

Ví dụ anti-pattern:

~~~java
// Anti-pattern: mất kết nối DB trở thành "not eligible".
try {
    return invoiceRepository.existsById(invoiceId);
}
catch (RuntimeException ignored) {
    return false;
}
~~~

Khi DB không phản hồi, không thể kết luận invoice chắc chắn không tồn tại. Nếu trả false và drop, một message hợp lệ có thể **mất vĩnh viễn**. Phải tách infrastructure exception ra khỏi kết quả business không đủ điều kiện.

### 20.4. Không retry lỗi dữ liệu bằng default advice vô hạn

Nếu Filter có retry advice mà `throwExceptionOnRejection(true)`, việc trả false do invalid có thể được retry **dù message không thay đổi**. Nên cấu hình classifier/non-retryable exceptions hoặc đẩy validation vào adapter boundary trước retrying handler, với error outcome được theo dõi.

## 21. Gateway, request-reply và silent drop

Một Gateway thường chờ phản hồi. Khi Filter default-drop request, handler tiếp theo không chạy và có thể không gửi reply:

~~~text
Gateway request
   -> Filter returns false
   -> drop
   -> Gateway waits
   -> reply timeout
~~~

Nếu người gọi cần biết tại sao invoice không được chấp nhận:

- Trả typed validation error hoặc một `RejectedOutcome` có reason.
- Với expected skip, trả `SKIPPED` theo API contract.
- Với security denial, trả phản hồi giới hạn thông tin theo security policy.
- Với lỗi DB/network, trả lỗi tạm thời hoặc asynchronous tracking state phù hợp.
- Không trông chờ `nullChannel` tự tạo HTTP 400/422.

### 21.1. DTO phản hồi minh họa

~~~java
public enum SubmissionStatus {
    ACCEPTED,
    SKIPPED,
    INVALID
}

public record SubmissionReply(
        String requestId,
        SubmissionStatus status,
        String reasonCode
) {}
~~~

Đây là **model nghiệp vụ**, không phải output mặc định của MessageFilter. Phải có endpoint/route rõ để tạo và gửi `SubmissionReply` về `replyChannel` của Gateway hoặc adapter HTTP.

### 21.2. HTTP status do adapter quyết định

Một `MessageRejectedException` trong Spring Integration **không tự có nghĩa là HTTP 400**. Ứng dụng cần mapping: invalid contract → 400/422 theo API, authorization denial → 403 theo security layer, transient errors → 5xx hoặc async retry response. Chọn response semantics nhất quán để client không retry vô hạn một lỗi không thể tự chữa.

## 22. Filter sau Splitter có thể làm Aggregator kẹt

Splitter tạo bốn message có sequence metadata:

~~~text
part #1: sequenceNumber=1, sequenceSize=4
part #2: sequenceNumber=2, sequenceSize=4
part #3: sequenceNumber=3, sequenceSize=4
part #4: sequenceNumber=4, sequenceSize=4
~~~

Nếu Filter bỏ part #2 nhưng vẫn giữ `sequenceSize=4` trên các part khác:

~~~text
Aggregator receives: #1, #3, #4
Missing:             #2
Expected:            4
~~~

Release strategy dựa trên đủ số part có thể **chờ mãi hoặc tới expiry**. Filter đã "làm đúng" theo predicate nhưng tổng thể flow vẫn không thể hoàn thành.

Hướng giải quyết:

1. **Filter collection trước Splitter** để Splitter biết đúng số phần sau khi lọc.
2. Dùng **skipped marker** ở vị trí #2 nếu downstream có contract xử lý phần bị bỏ.
3. Custom release strategy hiểu các part có thể bị bỏ có chủ đích.
4. Nếu một part invalid làm toàn bộ batch sai, reject/reconcile cả group.
5. Có timeout/expiry và incomplete group policy.
6. Giữ correlation ID/sequence headers và theo dõi số part bị reject.

### 22.1. Resequencer cũng chịu ảnh hưởng

Nếu Resequencer nhận 1,3,4 nhưng không có 2, nó có thể giữ các part sau vì gap. Chọn discard hoặc exception ở một Filter **trước** Resequencer không chỉ ảnh hưởng message đó mà còn ảnh hưởng thứ tự và latency của cả sequence.

### 22.2. Không dùng thông tin sequence như validation key

`sequenceNumber` và `sequenceSize` là metadata của chuỗi, không tự thay business identity hoặc content validation. Nếu các part bị Filter loại nhưng sequence size không cập nhật, đừng tự sửa ngẫu nhiên size của những message còn lại; cần một protocol rõ giữa Splitter, Filter, Resequencer/Aggregator.

## 23. Security: không che authorization failure bằng discard

Nếu message khai `tenantId` thuộc tenant khác hoặc chứa token không hợp lệ, nó không chỉ là "không đủ điều kiện campaign".

- Authenticate nguồn trước khi tin headers/payload.
- Authorize quyền trên tài nguyên trước business side effects.
- Không tiết lộ dữ liệu người khác trong error message hoặc discard queue.
- Có audit cho security denial.
- Không bắt mọi lỗi authorization rồi trả false để né exception.
- Không để đầu vào tùy ý quyết định tên channel nội bộ.
- Không xuất payload gốc vào logs hoặc quarantine không được bảo vệ.

**Kiểm soát bảo mật phải nằm ở trust boundary phù hợp**, không dựa vào một Filter sâu trong flow sau khi dữ liệu đã đi qua nhiều endpoint.

## 24. Observability: đo outcome theo đúng ý nghĩa

| Metric | Nội dung | Label phù hợp |
|---|---|---|
| `filter_received_total` | Message đến | flow/source |
| `filter_accepted_total` | Message pass | flow |
| `filter_discarded_total` | Expected business skips | reason/category |
| `filter_invalid_total` | Contract violations | validation code |
| `filter_exception_total` | Rejection exceptions | error class |
| `filter_retry_total` | Số attempt retry | flow/reason |
| `filter_quarantine_total` | Số message cách ly | source/reason |
| `filter_dlq_total` | Số message vào DLQ | flow/reason |
| `filter_async_error_total` | ErrorMessage từ async task | error class |
| `filter_gateway_timeout_total` | Gateway thiếu reply | flow |

Một log có cấu trúc:

~~~text
flow=invoice-campaign
requestId=REQ-1001
outcome=DISCARDED_EXPECTED
reasonCode=NOT_ELIGIBLE
source=invoice-submission
traceId=trace-1001
~~~

Không sử dụng invoice ID, request ID, trace ID hoặc customer ID làm **metric labels có cardinality cao**. Dùng logs/traces có quyền và retention phù hợp khi cần truy tìm một request cụ thể.

### 24.1. Phân biệt skip hợp lệ với lỗi producer

Nếu một campaign chỉ nhận 5% invoice, 95% `filter(false)` là điều bình thường — không nên phát 95% error alerts. Ngược lại, nếu lỗi invoiceId trống bị coi là "expected discard", producer có thể gửi dữ liệu sai suốt nhiều ngày mà không ai biết.

Ít nhất hãy tách:

~~~text
ACCEPTED
DISCARDED_EXPECTED
REJECTED_INVALID
FAILED_RETRYABLE
~~~

Đối với remote actions không rõ đã thực hiện hay chưa, cân nhắc trạng thái `UNKNOWN`/reconciliation thay vì dùng discard như kết quả giả.

### 24.2. Khả năng audit bền vững

Warning log khi default-drop trong Spring Integration 6.1+ không thay một **audit record bền vững**. Nếu chính sách yêu cầu bằng chứng vì sao bị từ chối, tạo một event/record với reason code và danh tính phù hợp; kiểm thử rollback/ACK nếu audit phải là một phần của giao dịch.

## 25. Anti-pattern thường gặp

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Mọi Filter false đều là error | Business skip gây retry/alert không cần | Tách validation và eligibility |
| Dữ liệu sai bị drop mặc định | Mất message không feedback | Typed error/quarantine |
| Nghĩ Filter false mặc định throw | Không có exception | `throwExceptionOnRejection(true)` |
| Nghĩ discard nhận ErrorMessage | Cast sai payload | Discard nhận original message |
| Nghĩ throwExceptionOnRejection bắt mọi lỗi | Exception riêng của selector không được phân biệt | Theo dõi cause chain |
| Bật discard + throw không chủ đích | Side effect discard rồi retry | Định nghĩa rõ outcome/idempotency |
| Dùng nullChannel cho financial command | Lost work | Chỉ drop message disposable |
| Catch database exception rồi return false | Che transient failure | Throw + bounded retry |
| Invalid broker message retry vô hạn | Poison loop | Non-retryable/DLQ |
| Discard = DLQ tự động | Không có broker policy | Cấu hình outbound/adapter |
| Silent drop trong Gateway | Timeout thay vì response | Explicit reply/error |
| Filter part sau Splitter | Aggregator/Resequencer thiếu part | Pre-filter/marker/release |
| Không kiểm tra retry advice và discardWithinAdvice | Discard side effect bị retry | Test advice boundary |
| Quarantine chứa payload nhạy cảm | Lộ dữ liệu | Masking/retention/access control |
| Không test sync vs async exception | Sai kỳ vọng đường lỗi | Integration tests đúng topology |
| Dùng warning log làm audit | Thiếu bằng chứng bền vững | Audit/outcome record |
| Đếm duplicate attempts như unique rejects | Sai metric | Stable idempotency key |

## 26. Bài tập thực hành

**Bài 1 — Phân loại:** với invoice không eligible, invoiceId trống, amount âm, DB timeout, tenant sai quyền và event đã xử lý, chọn discard/exception/quarantine/retry kèm giải thích.

**Bài 2 — Unit validator:** chạy `SubmissionValidatorTest`; xác nhận invoice hợp lệ nhưng not eligible vẫn valid.

**Bài 3 — Discard flow:** gửi hai invoice hợp lệ eligible/not eligible vào `DiscardOnBusinessSkipConfig` và kiểm tra accepted/discarded channels.

**Bài 4 — Invalid before Filter:** gửi invoiceId trống, amount âm vào flow trên; assert exception và hai output channels rỗng.

**Bài 5 — Throw filter:** gửi invalid vào `ThrowOnInvalidConfig`; assert cause chain có `MessageRejectedException`.

**Bài 6 — Both policies:** bật discard và throw đồng thời; assert discard nhận original message dù caller vẫn nhận exception.

**Bài 7 — Duplicate discard side effect:** thay QueueChannel bằng audit handler, mô phỏng retry rồi thêm idempotency.

**Bài 8 — Async error:** dùng ExecutorChannel hoặc poller có error handler; test `ErrorMessage` thay vì trực tiếp bắt exception từ `send()`.

**Bài 9 — Poison message:** cho một invalid event redelivery qua broker, cấu hình max attempts/non-retryable policy và DLQ.

**Bài 10 — Gateway:** so sánh silent drop gây reply timeout với explicit invalid reply/error mapping.

**Bài 11 — Aggregator gap:** split bốn part rồi discard phần 2; quan sát release behavior, thiết kế pre-filter hoặc skipped marker.

**Bài 12 — Headers:** xác nhận correlation/trace headers phù hợp tồn tại trên accepted/discarded route, nhưng security secrets không bị phát ra ngoài.

**Bài 13 — Quarantine:** tạo `RejectedEnvelope` và quy định reason code, retention, encryption và quyền truy cập.

**Bài 14 — Observability:** tạo metrics accepted, expected discard, validation fail và retryable error với labels không có IDs cá nhân.

**Bài 15 — Reprocessing:** lấy message từ quarantine sau khi sửa dữ liệu; dùng stable business key để không lặp side effects.

### Câu hỏi tự kiểm tra

1. Filter trả true và false có nghĩa gì?
2. Vì sao Filter false không phải lúc nào cũng validation fail?
3. Khi không cấu hình discard/throw, message bị từ chối đi đâu?
4. Spring Integration 6.1+ có thể log gì khi default drop?
5. `discardChannel` thường nhận original message hay ErrorMessage?
6. `throwExceptionOnRejection(true)` tạo exception loại nào?
7. Nếu selector tự ném IllegalArgumentException, có phải MessageRejectedException không?
8. Nếu bật cả discard và throw thì chuyện gì xảy ra?
9. Vì sao discard branch có side effect cần idempotency khi retry?
10. Vì sao nullChannel không phù hợp cho dữ liệu tài chính?
11. Structural validity khác business eligibility thế nào?
12. Khi nào cần validation reason codes thay cho boolean?
13. Trong DirectChannel, exception đi đâu?
14. Trong ExecutorChannel, caller có luôn bắt được lỗi không?
15. `errorChannel` và `discardChannel` có cùng payload contract không?
16. DB timeout có nên được coi như Filter false không?
17. Vì sao malformed event có thể gây poison retry loop?
18. Discard có đồng nghĩa với broker ACK không?
19. Vì sao Filter sau Splitter có thể làm Aggregator kẹt?
20. Gateway chờ reply sẽ gặp gì khi Filter silent drops?
21. Security denial có thể được discard như not eligible không?
22. Đặt metric thế nào để tránh xem expected skip là lỗi?
23. `discardWithinAdvice` có thể ảnh hưởng phạm vi retry như thế nào?
24. Test nào chứng minh discard và throw xảy ra cùng nhau?

## 27. Checklist triển khai

- [ ] Đã phân loại **invalid**, **not eligible**, **transient failure** và **security denial**.
- [ ] Validation nằm trước những business side effects quan trọng.
- [ ] Filter kiểm tra eligibility trên payload đã được xác nhận hợp lệ.
- [ ] Hiểu default drop của MessageFilter và warning behavior từ 6.1.
- [ ] `discardChannel` được cấu hình khi cần expected reject branch.
- [ ] `throwExceptionOnRejection` chỉ bật với rejection thực sự cần error.
- [ ] Không bật discard + throw cùng lúc mà không tính retry/idempotency.
- [ ] Có stable reason codes cho dữ liệu sai.
- [ ] Exception validation khác exception hạ tầng.
- [ ] Non-retryable errors không được requeue vô hạn.
- [ ] Transient failures có bounded retries/backoff và DLQ policy.
- [ ] Discard consumer hiểu original message, error consumer hiểu ErrorMessage.
- [ ] Sync/async error path được test với topology thực.
- [ ] Không dùng nullChannel cho nghiệp vụ không được phép mất.
- [ ] Gateway/API có reply hoặc error mapping rõ khi rejection.
- [ ] Filter sau Splitter không phá release/sequence contract.
- [ ] Correlation, trace headers được giữ/loại phù hợp trust boundary.
- [ ] Quarantine có retention, masking, encryption, audit và quyền.
- [ ] ACK/NACK behavior được xác minh với inbound adapter tương ứng.
- [ ] Có unit tests và integration tests cho pass/discard/throw.
- [ ] Có test cả discard và throw, cùng khả năng retry side effect.
- [ ] Metrics tách accepted, expected discard, invalid và retryable.
- [ ] Không đưa PII/IDs cardinality cao vào metric labels.
- [ ] Reprocessing từ quarantine có stable idempotency identity.

## 28. Tổng kết

**Discard versus exception khi validation fail** là lựa chọn **ngữ nghĩa** của luồng message, không chỉ là một flag. Nếu một message **hợp lệ nhưng không thuộc nhánh**, discard có chủ đích là kết quả business bình thường. Nếu message **vi phạm contract**, cần phản hồi lỗi hoặc quarantine có reason code. Nếu gặp lỗi hạ tầng, cần exception và retry có kiểm soát, không che nó bằng Filter false.

Trong Spring Integration, selector trả false thì Filter mặc định **drop**. `discardChannel` chuyển **original rejected message** sang nhánh riêng, còn `throwExceptionOnRejection(true)` ném `MessageRejectedException`. Nếu bật cả hai, message được gửi vào discard branch **rồi vẫn có thể ném exception**, gây duplicate side effects khi caller retry. Exception qua `DirectChannel` đồng bộ thường trở về caller; với async flow phải hiểu `ErrorMessage` và error handler.

Trong **SPRING_INTEGRATION_PATTERN**, việc tách validation và Filter business rule, đặt retry/ACK theo loại lỗi, bảo toàn correlation, kiểm thử Gateway/Aggregator và quan sát đúng outcomes giúp hệ thống tích hợp **không làm mất tác vụ vì một lỗi dữ liệu bị lặng lẽ bỏ qua**.

### Tài liệu tham khảo

- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration API — MessageFilter: https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html
- Spring Integration API — FilterEndpointSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html
- Spring Integration API — MessageRejectedException: https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Handler Advice: https://docs.spring.io/spring-integration/reference/handler-advice.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/





