# Kiểm thử contract của từng provider

Khi ứng dụng **Spring Framework Mail** có nhiều nhà cung cấp gửi thư, việc các adapter đều triển khai một giao diện như `MailSender` hoặc `MailProvider` **không có nghĩa chúng có cùng hành vi**. Một provider có thể nhận SMTP ở cổng 587 qua STARTTLS; provider khác dùng SMTP implicit TLS ở cổng 465 hoặc HTTP API. Có nơi yêu cầu app password, nơi khác dùng OAuth2, API token, IP allowlist hoặc quyền gửi thay mặt một địa chỉ đã xác minh. Cách trả lỗi, giới hạn tốc độ, xử lý recipient, trả message ID và thông báo bounce cũng có thể khác nhau.

Nếu chỉ viết một unit test rằng mock `JavaMailSender.send(...)` không ném exception, ứng dụng chưa chứng minh được adapter thực tế **tuân thủ hợp đồng gửi thư**. Khi failover, đổi provider hoặc triển khai ở một region khác, sự khác biệt này có thể gây mất email, gửi trùng, ghi sai trạng thái, bỏ qua địa chỉ người nhận hoặc diễn giải nhầm `accepted` thành `delivered`.

**Kiểm thử contract của từng provider** là cách xác nhận các bảo đảm mà ứng dụng kỳ vọng ở ranh giới tích hợp: dữ liệu đầu vào, khả năng provider hỗ trợ, bảo mật transport, kết quả submission, lỗi và retry, định danh message, delivery event, quota và quyền truy cập. Các test dùng chung bảo vệ hành vi chung; các test theo provider kiểm tra những điểm đặc thù; test bằng sandbox/staging xác nhận thực tế bên ngoài các mock.

Bài học này trình bày cách thiết kế hợp đồng, lập capability matrix, xây test suite tái sử dụng với JUnit 5, kiểm tra SMTP/API adapter, mô phỏng lỗi và webhook, kiểm thử routing/failover, quản lý credential an toàn và phát hiện contract drift sau khi provider thay đổi chính sách.

## 1. Contract là gì trong tích hợp gửi mail?

Một **contract** ở đây là tập các điều kiện và kết quả quan sát được mà hai bên đã thống nhất:

- **Ứng dụng yêu cầu**: provider nhận một email hợp lệ cho recipient và sender được phép gửi.
- **Adapter bảo đảm**: chuyển đúng dữ liệu sang SMTP/API, không làm mất nội dung hoặc gửi nhầm recipient.
- **Provider phản hồi**: accepted, rejected hoặc trạng thái không xác định theo giao thức.
- **Ứng dụng diễn giải**: cập nhật trạng thái, quyết định retry và phát log/metric đúng nghĩa.
- **Provider thông báo về sau**: có thể phát delivered, bounced, deferred, complaint hoặc các event khác; contract chỉ áp dụng những khả năng thực sự hỗ trợ.

Một contract test không nhất thiết kiểm tra toàn bộ hệ thống. Nó kiểm tra **ranh giới giữa hai thành phần** bằng những ví dụ và bất biến đã được xác định.

### Phân biệt bốn lớp contract

| Lớp | Ví dụ | Kiểm thử ở đâu? |
|---|---|---|
| **Domain contract** | Một notification cho đúng người nhận, đúng template/locale | Unit test service và renderer |
| **Provider-port contract** | `submit` trả accepted/rejected/unknown đúng nghĩa | Bộ test chung cho mọi adapter |
| **Protocol contract** | SMTP AUTH/TLS/MIME hoặc HTTP method/header/body/error mapping | SMTP test server, HTTP mock server |
| **External/provider contract** | Quyền sender, quota, event schema và hành vi thật | Sandbox/staging/live canary có kiểm soát |

Một bài test qua Mockito chỉ kiểm tra lời gọi Java, không tự xác nhận phía provider chấp nhận dữ liệu. Một bài test chạy với SMTP test server chỉ xác nhận một phần giao thức, không chứng minh chính sách tài khoản thật của provider.

### Mục tiêu quan trọng nhất

**Mọi provider phải tuân thủ contract chung của ứng dụng, nhưng không được giả vờ rằng mọi provider hỗ trợ cùng một tính năng.** Khi một tính năng không được hỗ trợ, adapter cần từ chối rõ ràng hoặc chọn một hành vi thay thế đã được phê duyệt; không được âm thầm bỏ qua dữ liệu quan trọng.

## 2. Tại sao cần kiểm thử riêng từng provider?

Một cấu hình “chạy được” hôm nay có thể không tương đương ở hệ thống khác.

Ví dụ luồng gửi hóa đơn:

```text
Business service
       |
       v
MailProviderPort.submit(invoice notification)
       |
       +--- SMTP Provider A
       |      - STARTTLS
       |      - username + app password
       |      - 4xx/5xx replies
       |
       +--- SMTP Provider B
       |      - implicit TLS
       |      - OAuth2/XOAUTH2
       |      - different limits
       |
       +--- HTTP API Provider C
              - bearer token
              - JSON payload
              - API request ID
              - async delivery webhook
```

Những trường hợp dễ gây sai lệch:

1. Provider A chấp nhận địa chỉ `From` nhưng B yêu cầu sender/domain đã xác minh.
2. A trả mã 4xx tạm thời, B trả HTTP 429 với hướng dẫn retry.
3. Một adapter trả provider message ID, adapter khác không có ID như vậy qua SMTP.
4. Một API nhận recipient dưới dạng danh sách, SMTP có thể trả kết quả chấp nhận một phần.
5. Provider hỗ trợ custom metadata qua API nhưng không bảo đảm giữ header tùy chỉnh khi gửi qua SMTP.
6. Provider có webhook `delivered` mang nghĩa server đích đã chấp nhận, không phải inbox.
7. Provider A dùng sandbox thật, provider B ở test mode chỉ giả lập acceptance.
8. Cấu hình timeout/connection reuse khác khiến số attempt hoặc độ trễ khác nhau.
9. Provider không hỗ trợ cấu trúc inline MIME, file đính kèm lớn hoặc địa chỉ quốc tế hóa.
10. Trong failover, cùng notification có nguy cơ được submit hai lần nếu outcome của attempt đầu không rõ.

Nếu bộ test chỉ chạy với provider mặc định, những vấn đề này dễ xuất hiện sau deploy hoặc trong sự cố production — đúng lúc fallback được kỳ vọng hoạt động.

## 3. Chốt contract của ứng dụng trước khi viết adapter

Nên tách **ý định gửi logic** khỏi thông số giao thức cụ thể.

Một model minh họa:

```java
import java.time.Instant;
import java.util.List;

public record MailSubmissionCommand(
        String notificationId,
        String correlationId,
        String senderProfile,
        List<String> recipients,
        String subject,
        String plainText,
        String html,
        List<AttachmentRef> attachments,
        Instant expiresAt
) {
}

public record AttachmentRef(
        String id,
        String safeFilename,
        String mediaType,
        long contentLength
) {
}
```

`senderProfile` nên là ID cấu hình nội bộ được quản lý, không phải địa chỉ `From` tùy ý do client cung cấp. `AttachmentRef` là reference tới tài nguyên đã được xét quyền; việc tải byte thực tế có thể nằm ở một service riêng.

Nên có model kết quả submission phân biệt ba tình huống:

```java
public enum SubmissionOutcome {
    ACCEPTED,
    REJECTED,
    UNKNOWN
}
```

```java
import java.time.Instant;

public record ProviderSubmissionResult(
        SubmissionOutcome outcome,
        String providerRoute,
        String providerMessageId,
        String errorCategory,
        boolean retryable,
        Instant observedAt
) {
}
```

Trong code thật, nên ràng buộc các field hợp lệ theo từng outcome:

- `ACCEPTED`: provider/transport xác nhận **submission**, không phải delivery.
- `REJECTED`: có căn cứ provider không chấp nhận attempt.
- `UNKNOWN`: không biết chắc message đã được chấp nhận hay chưa.

`providerMessageId` có thể `null` nếu đường SMTP/adapter không cung cấp ID có ý nghĩa đó. Không tự chế một ID provider từ notification ID rồi coi chúng là tương đương.

### Giao diện ở ranh giới tích hợp

```java
public interface MailProviderPort {
    String routeId();

    ProviderCapabilities capabilities();

    ProviderSubmissionResult submit(
            MailSubmissionCommand command,
            String attemptId
    );
}
```

Một adapter cho SMTP có thể dùng `JavaMailSender` hoặc `JavaMailSenderImpl`; adapter cho HTTP API dùng HTTP client do ứng dụng chọn. Business service chỉ phụ thuộc `MailProviderPort`.

Điều quan trọng là **contract test chạy trên tất cả adapter**, không chỉ kiểm thử interface tồn tại về mặt kiểu dữ liệu.

## 4. Capability matrix cho từng provider

Đừng dùng một tập boolean không được kiểm soát rồi ngầm giả định provider nào cũng hỗ trợ mọi thứ. Hãy công bố capability theo route.

Một bảng giả định (không mô tả nhà cung cấp thương mại cụ thể):

| Khả năng | SMTP Route A | SMTP Route B | HTTP API Route C |
|---|---|---|---|
| Kênh gửi | SMTP | SMTP | HTTP API |
| Transport security | STARTTLS | Implicit TLS | HTTPS |
| Authentication | Username/app password | XOAUTH2 | API token |
| Plain text + HTML | Có | Có | Có |
| Attachment | Có, theo giới hạn | Có, giới hạn khác | Có, giới hạn API |
| Inline CID | Cần kiểm thử MIME | Cần kiểm thử MIME | Theo API contract |
| Sender identity | Domain cho phép | Mailbox được cấp quyền | Verified sender |
| Multiple recipients | Có thể | Có thể | Theo API contract |
| Provider message ID trả ngay | Không bảo đảm | Không bảo đảm | Thường tùy API |
| Delivery webhook | Tùy dịch vụ | Tùy dịch vụ | Tùy gói/contract |
| Idempotency server-side | Không mặc định | Không mặc định | Chỉ nếu API công bố |
| Quota/rate limit | Theo SMTP account | Theo mailbox/tenant | Theo token/account |

Bảng này là **template để nhóm dự án điền bằng dữ liệu chính thức**, không phải tuyên bố đặc tính của provider nào. Khi các thuộc tính chưa được xác minh, nên ghi `UNKNOWN` và không bật tính năng phụ thuộc vào chúng.

Có thể đưa capability vào code:

```java
public record ProviderCapabilities(
        boolean supportsHtml,
        boolean supportsAttachments,
        boolean supportsInlineImages,
        boolean supportsDeliveryEvents,
        boolean supportsProviderIdempotency,
        int maxRecipientsPerSubmission,
        long maxMimeBytes
) {
}
```

Thêm trường theo nhu cầu, nhưng đừng trộn giá trị cấu hình local với điều provider bảo đảm. Ví dụ max MIME size có thể phụ thuộc account, plan hoặc environment và có thể đổi theo thời gian.

### Khi thiếu capability

Nếu command có attachment nhưng provider route không hỗ trợ attachment:

- Từ chối trước khi gọi provider bằng mã lỗi rõ ràng.
- Hoặc chuyển sang route khác **có capability** và được policy cho phép.
- Không âm thầm xóa attachment rồi gửi email thiếu tài liệu.

Nếu message chứa HTML và provider chỉ hỗ trợ plain text, chỉ dùng plain text khi sản phẩm đã chấp thuận fallback này. Contract test nên xác nhận không có silent degradation.

## 5. Lập danh mục hành vi cần kiểm thử

Mỗi route nên có tập test ít nhất cho:

| Nhóm | Câu hỏi contract |
|---|---|
| Configuration | Host/base URL/port/credential/sender profile đúng môi trường? |
| Security | Bắt buộc TLS phù hợp, không fallback sang plain connection? |
| Identity | From, Reply-To, envelope sender và quyền Send As hợp lệ? |
| Data fidelity | Subject, plain, HTML, recipient, Unicode, attachment nguyên vẹn? |
| Transport | Thao tác gửi thực sự được gọi đúng một lần mỗi attempt? |
| Success | Response accepted được map đúng, không đánh đồng delivery? |
| Failure | 4xx/5xx/429/auth/timeouts được phân loại đúng? |
| Unknown | Mất response cuối được phản ánh không chắc chắn? |
| Limits | Recipient count, byte size, quota/rate limit có được xử lý? |
| Idempotency | Retry/failover không tạo notification mới sai? |
| Events | Webhook schema, chữ ký, duplicate và out-of-order? |
| Observability | Correlation/notification/attempt IDs có thể tra cứu? |
| Privacy | Không log secret, token, raw MIME hoặc PII ngoài chính sách? |
| Operational | Config rotate, provider outage, route disable và recovery? |

Không phải mọi adapter cần thử mọi chức năng bằng cách gửi thư thật. Phân chia thành **test thuần ứng dụng**, **protocol simulation**, **sandbox test** và **live canary đã được kiểm soát** sẽ hiệu quả và an toàn hơn.

## 6. Chia test thành các lớp và mục tiêu

### Unit contract tests

Đối tượng:

- Mapping command → SMTP MIME/API payload.
- Mapping response → `ProviderSubmissionResult`.
- Validation capability và sender profile.
- Phân loại lỗi, retryability và unknown outcome.
- Không gửi khi validation thất bại.

Ưu điểm: chạy nhanh, không cần network, dễ tạo lỗi khó gặp.

### Protocol tests

Đối tượng:

- SMTP test server cho STARTTLS/AUTH và MIME behavior mà server hỗ trợ.
- HTTP mock server cho method/path/headers/body/status codes.
- Timeouts, disconnection, lỗi hoặc response malformed.
- Webhook verification và idempotent handling.

Các mock server xác nhận **adapter nói đúng giao thức mô phỏng**, không thay cho chính sách của provider thật.

### Sandbox/staging provider verification

Đối tượng:

- Credential và quyền gửi được provider cấp.
- Domain/sender verification.
- API version, supported auth mechanism.
- Quota và cách provider trả lỗi.
- Event/webhook schema trong môi trường kiểm thử.
- Mapping IDs và những capability cần xác nhận.

Chỉ dùng account/tenant/sandbox được phép. Sandbox có thể không thực sự gửi email ra Internet, nên phải biết mức độ giả lập.

### Controlled production canary

Khi một khả năng không thể xác nhận trong sandbox, có thể dùng bài kiểm thử có kiểm soát theo quy trình vận hành: mailbox thử nghiệm trong allowlist, rate nhỏ, nội dung synthetic, theo dõi provider và tách KPI khỏi mail nghiệp vụ.

**Không tự động chạy test gửi thật đến người nhận tùy ý trong CI hoặc health endpoint.**

## 7. Kiến trúc test: một bộ chung, nhiều adapter

Mục tiêu là phát hiện hai loại sai:

1. **Vi phạm contract chung:** adapter gửi sai recipient, trả `DELIVERED` khi chỉ accepted, nuốt lỗi...
2. **Vi phạm contract đặc thù:** gửi SMTP không đúng TLS, bỏ qua HTTP `Retry-After`, không xác thực webhook provider...

Mô hình:

```text
                         Shared contract suite
                         /        |         \
                        v         v          v
                   SMTP A      SMTP B      HTTP C
                    tests       tests       tests
                      |           |           |
                      v           v           v
                 Protocol     Protocol    Mock HTTP
                  server       server       server
                      \           |           /
                       \          |          /
                        Provider-specific tests
                                  |
                                  v
                         Staging verification
```

Đừng sao chép toàn bộ test rồi sửa tên lớp. Một **hợp đồng dùng chung** giúp thay đổi yêu cầu được kiểm tra ở tất cả route; các bài test riêng chỉ mô tả khác biệt thật sự.

## 8. Một interface contract test với JUnit 5

Có thể định nghĩa interface test rồi cho từng adapter triển khai. Ví dụ dưới đây dùng abstraction test harness; lớp adapter thực tế sẽ cung cấp cách dựng, giả lập transport và đọc submission.

```java
public interface ProviderContractHarness
        extends AutoCloseable {

    MailProviderPort provider();

    MailSubmissionCommand validCommand();

    void simulateAcceptedSubmission();

    int submissionCount();

    CapturedMail lastSubmittedMail();

    @Override
    void close() throws Exception;
}

public record CapturedMail(
        String subject,
        String plainText,
        String html,
        java.util.List<String> recipients
) {
}
```

Test contract chung:

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

public interface MailProviderContract {

    ProviderContractHarness newHarness() throws Exception;

    @Test
    default void acceptedSubmissionDoesNotMeanDelivered()
            throws Exception {

        try (ProviderContractHarness harness = newHarness()) {
            harness.simulateAcceptedSubmission();

            MailSubmissionCommand command =
                    harness.validCommand();

            ProviderSubmissionResult result =
                    harness.provider().submit(
                            command,
                            "attempt-001"
                    );

            assertThat(result.outcome())
                    .isEqualTo(SubmissionOutcome.ACCEPTED);

            assertThat(result.providerRoute())
                    .isEqualTo(
                            harness.provider().routeId()
                    );

            assertThat(harness.submissionCount())
                    .isEqualTo(1);
        }
    }

    @Test
    default void retainsCoreMessageData()
            throws Exception {

        try (ProviderContractHarness harness = newHarness()) {
            harness.simulateAcceptedSubmission();

            MailSubmissionCommand command =
                    harness.validCommand();

            harness.provider().submit(command, "attempt-002");

            CapturedMail captured =
                    harness.lastSubmittedMail();

            assertThat(captured.subject())
                    .isEqualTo(command.subject());

            assertThat(captured.recipients())
                    .containsExactlyElementsOf(
                            command.recipients()
                    );
        }
    }
}
```

Đây là skeleton: `ProviderContractHarness` phải được hiện thực riêng cho SMTP A/B và API C. Test không kết nối Internet vì harness sử dụng fake/test transport.

Một class cụ thể:

```java
class SmtpProviderAContractTest
        implements MailProviderContract {

    @Override
    public ProviderContractHarness newHarness()
            throws Exception {
        return SmtpProviderATestHarness.create();
    }
}
```

Không bắt buộc phải sử dụng interface test; abstract base test hoặc factory-based parameterized test cũng phù hợp. Điều quan trọng là **same assertions chạy với từng provider implementation**.

## 9. Những bất biến chung nên nằm trong shared contract

Các bất biến cơ bản:

- Không gửi khi `notificationId`, recipient hoặc sender profile bắt buộc không hợp lệ.
- Mọi recipient trong command đều được ánh xạ đúng theo contract, không bỏ sót âm thầm.
- Subject, plain text và HTML có nội dung đúng hoặc fallback được phê duyệt.
- Giá trị Unicode không bị hỏng ở bước mapping.
- `submit` không tuyên bố `DELIVERED` khi chỉ có accepted của SMTP/API.
- Một invocation chỉ bắt đầu **một attempt transport** theo contract đồng bộ; retry tự động phải được mô tả riêng.
- Không trả `ACCEPTED` sau khi transport thực sự từ chối.
- Khi kết quả không rõ, không tự phân loại là definitely rejected.
- Mã lỗi trong kết quả thuộc tập error categories đã chuẩn hóa.
- Không dùng provider credentials làm trường trong log trả ra caller.
- Khi capability không hỗ trợ, phải có failure rõ hoặc route khác được phê duyệt.
- Không biến retry thành tạo notification mới.
- Không gửi qua provider bị disabled hoặc chưa được cấu hình.

Một test không nên yêu cầu các route trả cùng `providerMessageId` vì có provider không cung cấp ID ngay lúc submit.

## 10. Contract về sender và recipient

Địa chỉ `From`, `Reply-To` và SMTP envelope sender không đồng nhất.

Ví dụ email:

```text
From: Notifications <notifications@example.org>
Reply-To: support@example.org
To: customer@example.net
Subject: Đơn hàng đã xác nhận
```

SMTP có thể dùng một envelope sender khác:

```text
MAIL FROM:<bounce-route@example.org>
RCPT TO:<customer@example.net>
```

Một provider có thể áp dụng policy lên header From, sender domain hoặc envelope sender. Adapter khác có thể tự đặt bounce address.

Contract nên kiểm tra:

1. Sender profile được chọn từ danh mục đã được cấp quyền.
2. Header `From` đúng địa chỉ được phê duyệt.
3. `Reply-To` có/không đúng theo yêu cầu.
4. Envelope sender/return path dùng đúng policy route nếu có thể cấu hình.
5. Không cho caller tùy ý mạo danh domain.
6. Recipient `To/Cc/Bcc` không bị hoán đổi hoặc lộ ngoài ý muốn.
7. Provider rejection vì sender authorization được map đúng.
8. Khi failover, route dự phòng phải có quyền gửi với sender identity đó.

### Contract per-recipient

Một số provider xử lý nhiều recipients trong một submission; kết quả có thể khác theo người nhận. Nếu ứng dụng đòi hỏi trạng thái từng người, nên định nghĩa **mỗi logical notification ứng với một recipient** hoặc có model `RecipientSubmissionOutcome`.

Không gom mọi recipient vào trạng thái accepted duy nhất nếu provider trả partial acceptance. Test cần có trường hợp một recipient được chấp nhận, một recipient bị từ chối — với loại transport cho phép tình huống đó.

## 11. Contract MIME: subject, HTML, plain text và charset

Với SMTP provider, `JavaMailSenderImpl` sử dụng Jakarta Mail để đóng gói message. Khi tạo test, có thể kiểm tra cấu trúc MIME trong bộ nhớ mà không gửi thật.

Ví dụ:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message =
        new JavaMailSenderImpl().createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng số 102 🎉");
helper.setText(
        "Đơn hàng số 102 đã xác nhận.",
        "<p>Đơn hàng <strong>102</strong> đã xác nhận.</p>"
);

message.saveChanges();
```

Các assertion nên kiểm:

- `message.getSubject()` trả đúng chuỗi Unicode.
- Có `text/plain` và `text/html` khi hợp đồng yêu cầu.
- Multipart mode/cây MIME phù hợp với attachment/inline resource.
- `To`, `Cc`, `Bcc` và `Reply-To` đúng.
- Charset cho phần text được cấu hình đúng.
- Không có raw header injection từ subject hoặc filename.
- Dữ liệu template có HTML escaping đúng ở lớp renderer.

**Không dựa vào thứ tự index cố định của multipart part.** Có thể duyệt cây MIME theo content type và disposition vì `multipart/mixed` và `multipart/related` có thể lồng nhau.

### SMTP không tự chứng minh client render

Đúng MIME structure không bảo đảm Outlook, Gmail và các mail client khác hiển thị y hệt. Nếu yêu cầu giao diện cao, cần preview/visual test riêng. Provider contract test tập trung vào **dữ liệu và định dạng được submit**, không phải ảnh chụp inbox của mọi client.

## 12. Attachment và inline content: kiểm thử fidelity

Những trường cần kiểm tra khi adapter hỗ trợ attachment:

| Dữ liệu | Bất biến cần kiểm |
|---|---|
| Filename | Tên hiển thị an toàn, encoding/Unicode đúng chính sách |
| Content type | Đúng MIME type được cho phép |
| Bytes | Sau decode, byte đúng nguồn được phê duyệt |
| Size | Không vượt giới hạn provider/route |
| Disposition | `attachment` hoặc `inline` đúng |
| CID | HTML `cid:...` trùng `Content-ID` của inline part |
| File count | Không bỏ, lặp hoặc hoán đổi tệp |
| Access | Chỉ đọc storage key/attachment ID đã được cấp quyền |

Ví dụ fixture nên có:

- File PDF nhỏ từ byte test.
- Tên file tiếng Việt hoặc ký tự Unicode.
- Attachment rỗng nếu policy cho phép/từ chối.
- File ngay sát giới hạn size.
- Một ảnh inline có Content-ID.
- Một tên file chứa CR/LF bị từ chối trước khi xây MIME.

Không dùng attachment thật của người dùng để chạy contract test. Kiểm tra dữ liệu ở môi trường kiểm soát; log chỉ lưu attachment ID hoặc kích thước, không ghi nội dung.

### Giới hạn kích thước cần thử theo route

Provider có thể giới hạn kích thước MIME tổng, không chỉ số byte gốc. Binary attachment mã hóa base64 làm payload tăng. Nếu capability khai báo `maxMimeBytes`, test phải áp dụng giới hạn theo cách đo thực tế hoặc với headroom phù hợp, không chỉ so sánh `Files.size(...)` của từng file.

## 13. Contract transport: STARTTLS, implicit TLS và AUTH

Trong SMTP, cần kiểm thử **cấu hình transport** riêng theo provider.

Ví dụ STARTTLS:

```yaml
mail:
  providers:
    route-a:
      host: smtp-a.example.org
      port: 587
      transport: starttls
      auth: password
```

Ví dụ implicit TLS:

```yaml
mail:
  providers:
    route-b:
      host: smtp-b.example.org
      port: 465
      transport: implicit-tls
      auth: oauth2
```

Đây là YAML mô hình của ứng dụng, **không phải property mặc định của Spring Boot**. Adapter phải ánh xạ thành cấu hình Jakarta Mail chính xác cho từng route.

STARTTLS thường cần:

```properties
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

Implicit TLS thường cần:

```properties
mail.smtp.auth=true
mail.smtp.ssl.enable=true
```

Các property phải được điều chỉnh theo provider và transport đã chọn. Không bật cả hai kiểu theo thói quen hoặc tắt `starttls.required` để vượt qua một lỗi TLS trong môi trường production.

### Test vận hành cần xác minh

- Kết nối dùng đúng hostname/port.
- STARTTLS được yêu cầu khi policy bắt buộc.
- Không tiếp tục gửi credential qua kênh chưa bảo vệ.
- TLS certificate/hostname verification tuân thủ policy đã chọn.
- Username format đúng; credential lấy từ secret source.
- Mechanism `PLAIN`/`LOGIN`/`XOAUTH2` phù hợp.
- Kết nối và authentication timeout có giới hạn.
- Credential hoặc token không bị in ra SMTP debug log.

Các test cấu hình chỉ kiểm tra giá trị property chưa đủ để chứng minh endpoint thật có chứng chỉ hợp lệ và quyền đăng nhập đúng. Phần đó cần staging/sandbox verification có kiểm soát.

## 14. OAuth2/XOAUTH2 cần contract về vòng đời token

Một SMTP route có thể dùng token thay vì password. Khi đó contract không chỉ là “đã đặt `mail.smtp.auth.mechanisms=XOAUTH2`”.

Cần xác minh:

1. Ứng dụng lấy token cho đúng scope/quyền SMTP.
2. Token thuộc đúng mailbox/tenant theo policy provider.
3. Token hết hạn được làm mới trước khi dùng, theo chiến lược an toàn.
4. Token bị thu hồi hoặc thiếu permission được phân loại rõ.
5. Không retry gửi cùng token hỏng liên tục.
6. Không log access token hoặc refresh token.
7. Concurrent refresh không tạo bão request tới identity provider.
8. Khi xoay secret/certificate, route lấy được credential mới.

Ví dụ test logic của token supplier:

```java
@Test
void refreshesExpiredTokenBeforeSubmission() {
    TokenSupplier supplier = fakeTokenSupplier(
            expiredToken(),
            freshToken()
    );

    MailProviderPort provider =
            createOauthSmtpProvider(supplier);

    provider.submit(
            validCommand(),
            "attempt-token-001"
    );

    assertThat(supplier.refreshCount()).isEqualTo(1);
}
```

Các kiểu/hàm `TokenSupplier`, `fakeTokenSupplier`, `expiredToken` và `createOauthSmtpProvider` là fixture minh họa, không phải API có sẵn trong Spring.

Cần test thêm token refresh thất bại không làm adapter gửi request với token cũ mà không rõ chính sách.

## 15. SMTP contract: accepted không có nghĩa delivered

Trong SMTP submission:

```text
EHLO
STARTTLS / AUTH
MAIL FROM
RCPT TO
DATA
MIME body
Server: 250 queued/accepted
```

Một phản hồi thành công sau DATA thường cho biết **next-hop SMTP server đã nhận message để xử lý**. Nó không chứng minh MX đích nhận, thư ở inbox hay người dùng đã đọc.

Provider contract test phải xác nhận mapping:

```text
SMTP transport returns normally
       -> SubmissionOutcome.ACCEPTED

SMTP explicitly rejects before acceptance
       -> SubmissionOutcome.REJECTED

Connection lost at uncertain stage
       -> SubmissionOutcome.UNKNOWN
```

Không được map success thành `DELIVERED`. Nếu provider có webhook `delivered` đến sau, đó là một **contract khác**.

### Test SMTP response codes

| Tình huống mô phỏng | Kỳ vọng phân loại |
|---|---|
| AUTH 535 | Rejected/authentication, thường cần sửa credential/quyền |
| Recipient 550 rõ ràng | Rejected/recipient hoặc policy tùy ngữ cảnh |
| Temporary 421/451 | Rejected tạm thời hoặc transient theo stage đã xác định |
| SMTP 250 sau DATA | Accepted bởi next-hop SMTP |
| Timeout trước khi connect | Thường có thể xác định chưa submit message |
| Timeout sau khi truyền DATA, chưa nhận final reply | Unknown outcome nếu không có bằng chứng |
| Có recipient được chấp nhận, recipient khác bị từ chối | Partial outcome theo transport và contract |
| Server không hỗ trợ AUTH mechanism bắt buộc | Configuration/protocol failure |

Không quy mọi `MessagingException` hoặc `MailException` thành một loại kết quả. Cần đọc cause và giai đoạn xảy ra lỗi.

## 16. HTTP API contract: method, headers, payload và response

Một provider qua HTTP API có thể yêu cầu:

```http
POST /v1/messages
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: <key-if-supported>

{
  "from": "notifications@example.org",
  "to": ["customer@example.net"],
  "subject": "Order confirmed",
  "text": "Your order is confirmed",
  "html": "<p>Your order is confirmed</p>"
}
```

Đây là ví dụ giả định, không phải schema của provider cụ thể.

Các test protocol nên kiểm tra:

- Đúng HTTP method/path/API version.
- Authorization header được gửi qua HTTPS và không lộ vào log.
- Content-Type và JSON encoding đúng.
- Recipient list không bị đảo, thiếu hoặc thêm địa chỉ.
- Plain/HTML mapping đúng.
- Custom metadata chỉ gửi nếu API hỗ trợ.
- Attachment encoding và giới hạn đúng.
- Request ID/idempotency key chỉ dùng theo contract công bố.
- Thành công HTTP không bị diễn giải vượt quá response semantics.

### Response mapping phải theo provider contract

Giả sử API trả:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "messageId": "provider-message-801",
  "status": "queued"
}
```

Ứng dụng nên map sang **provider accepted/queued** theo contract, không map ngay thành delivered.

HTTP 200/201/202 không có ý nghĩa giống nhau ở mọi provider; payload có thể nói một số recipient bị reject ngay cả khi HTTP request thành công. Khi cần, bộ phân loại phải xét cả status và response body.

### Thông điệp lỗi không phải nhãn metric

API có thể trả lỗi chi tiết chứa địa chỉ email hoặc request ID. Không dùng toàn bộ raw error message làm `errorCategory` hoặc Micrometer tag. Hãy map sang danh mục có giới hạn như `auth`, `rate_limit`, `invalid_sender`, `recipient_rejected`, `timeout`, `unknown`.

## 17. WireMock hoặc HTTP mock server cho provider API

Một mock HTTP server có thể tạo phản hồi ổn định, bắt và kiểm tra request của adapter mà không kết nối Internet.

Ví dụ dùng WireMock với API giả định:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

@Test
void mapsAcceptedApiResponseWithoutClaimingDelivery() {
    wireMockServer.stubFor(
            post(urlEqualTo("/v1/messages"))
                .withHeader(
                        "Content-Type",
                        containing("application/json")
                )
                .willReturn(
                        aResponse()
                            .withStatus(202)
                            .withHeader(
                                    "Content-Type",
                                    "application/json"
                            )
                            .withBody(
                                    "{\"messageId\":\"provider-801\","
                                  + "\"status\":\"queued\"}"
                            )
                )
    );

    ProviderSubmissionResult result =
            apiProvider.submit(
                    validCommand(),
                    "attempt-api-001"
            );

    assertThat(result.outcome())
            .isEqualTo(SubmissionOutcome.ACCEPTED);

    assertThat(result.providerMessageId())
            .isEqualTo("provider-801");
}
```

`wireMockServer`, `apiProvider` và `validCommand()` là fixture được khởi tạo trong test thực tế. Ví dụ chỉ minh họa cấu trúc; package/API của WireMock phụ thuộc version và test dependencies của dự án.

Nên mở rộng test:

- `401/403`: authentication/authorization error.
- `429` với retry hint nếu provider hỗ trợ.
- `400` invalid payload hoặc sender.
- `5xx` từ provider.
- Response malformed JSON.
- Empty body.
- Kết nối bị ngắt trước khi response được đọc.
- Duplicate request khi retry.
- API version thay đổi trường bắt buộc.

### Không hard-code retry dựa trên HTTP status đơn lẻ

HTTP 429 thường gợi ý rate limiting, nhưng chính sách retry còn phụ thuộc provider, idempotency, retry hint, deadline và việc attempt có thể đã được xử lý hay chưa. HTTP 5xx cũng không luôn chứng minh request không được nhận — nhất là nếu connection đã bị cắt sau khi provider xử lý.

Với trạng thái không chắc chắn, map `UNKNOWN` hoặc chọn reconciliation theo chính sách thay vì khẳng định chắc chắn rejected.

## 18. Test retry hint và rate limit

Mỗi provider có giới hạn khác nhau:

- Requests/second.
- Messages/second.
- Recipients/second.
- Concurrent connections.
- Daily quota.
- Attachment size.
- Quota per account/tenant/sender domain.

Contract cần diễn giải đúng tín hiệu throttling từ provider, ví dụ SMTP 4xx hoặc HTTP 429 và các header/body hướng dẫn retry.

Ví dụ case:

```text
Given provider responds:
  HTTP 429
  Retry-After: 30

Then adapter:
  - classifies as RATE_LIMITED
  - does not immediately resend in a hot loop
  - exposes retry hint to scheduler when supported
  - keeps notification in durable queue
  - preserves notificationId
  - creates new attemptId on actual retry
```

`Retry-After` có thể biểu diễn số giây hoặc HTTP-date theo chuẩn; nếu provider sử dụng một trường khác, cần parser riêng. Test nên gồm giá trị thiếu, không hợp lệ, rất lớn và thời gian đã qua.

**Retry hint không phải mệnh lệnh bất chấp TTL nghiệp vụ.** Nếu OTP hết hạn trước thời gian retry, chuyển job sang trạng thái hết hạn theo policy thay vì gửi mã đã vô dụng.

### Giới hạn toàn hệ thống

Nếu nhiều replica dùng cùng một provider quota, test unit của limiter trong một JVM chưa chứng minh tổng tốc độ gửi không vượt quota. Cần kiểm thử coordination hoặc kiểm thử multi-instance với fake clock, fake provider và budget chung.

## 19. Idempotency có phạm vi khác nhau theo provider

Một HTTP API có thể hỗ trợ idempotency key, nhưng phải kiểm tra:

- Key được provider coi là unique trong phạm vi nào?
- Thời gian hiệu lực là bao lâu?
- Retry cùng key nhưng body khác dẫn tới gì?
- Provider có trả cùng message ID cho request lặp?
- Key áp dụng cho một recipient hay cả batch?
- Idempotency có tồn tại ở sandbox lẫn production không?

Nếu provider không công bố hỗ trợ, **không tự giả định header `Idempotency-Key` có tác dụng**.

Với SMTP, gửi lại cùng MIME `Message-ID` không phải một cơ chế chống trùng được mọi server bảo đảm. Local idempotency trong outbox tránh tạo nhiều notification logic, nhưng vẫn có thể gửi trùng khi worker mất kết nối sau SMTP acceptance.

### Contract test cho API có idempotency

```text
Attempt A:
  idempotencyKey = notification-001
  response lost after provider accepted

Attempt B (retry):
  idempotencyKey = notification-001
  same logical payload

Expected:
  follow provider's documented deduplication result
  record the returned provider ID/evidence
```

Không đặt hai retry là “idempotent” nếu adapter tạo key mới mỗi lần mà provider cần key ổn định. Đồng thời không tái dùng key cho **hai notification khác nhau**.

## 20. Delivery webhook là contract riêng sau submission

Một số provider báo sự kiện:

```text
accepted
processed
deferred
delivered
bounced
complaint
suppressed
open
click
```

Danh sách và cách đặt tên thay đổi theo provider. Không phải mọi provider hỗ trợ mọi sự kiện; ngay cả một event cùng tên cũng có thể có **ngữ nghĩa khác nhau**.

Ví dụ:

```text
Provider X "delivered":
    recipient MX accepted message

Provider Y "delivered":
    event follows provider-specific handoff rule

Neither necessarily means:
    message landed in inbox
    recipient actually read the content
```

Contract nên xác định với từng event:

- Nguồn và phiên bản schema.
- Trường định danh provider message ID/recipient.
- Timestamp của event và thời điểm nhận.
- Điều kiện xác thực webhook.
- Phương thức deduplication.
- Khả năng event đến sai thứ tự.
- Cách xử lý unknown event types.
- Quy tắc state transition hoặc event history.
- Mức chứng cứ mà event thực sự cung cấp.

Không dùng `JavaMailSender.send` trả về bình thường để giả tạo event delivered.

## 21. Kiểm thử xác thực webhook và replay

Một webhook có thể bị gửi lại khi endpoint timeout. Nó cũng có thể bị giả mạo nếu ứng dụng không xác minh nguồn.

Test cần có:

1. Payload có chữ ký hợp lệ được chấp nhận.
2. Payload bị sửa byte sau khi ký bị từ chối.
3. Chữ ký thiếu hoặc sai bị từ chối.
4. Timestamp quá thời gian cho phép bị từ chối nếu provider sử dụng timestamp.
5. Event trùng ID không được áp dụng hai lần.
6. Event của provider A không được ghi vào route/provider B.
7. Event về recipient khác không cập nhật nhầm notification.
8. Event không map được có thể lưu để reconciliation theo policy mà không lộ dữ liệu.
9. Payload quá lớn hoặc sai schema bị từ chối/giới hạn.
10. Event đến sai thứ tự không làm mất dữ liệu đã có.

### Chữ ký phải tính trên đúng dữ liệu provider định nghĩa

Nhiều webhook xác thực chữ ký trên **raw request body bytes**, đôi khi kèm timestamp/header. Nếu code deserialize JSON rồi serialize lại trước khi kiểm chữ ký, whitespace hoặc thứ tự trường có thể khác và xác thực sai.

Hãy dùng thuật toán và quy tắc canonicalization do provider công bố. Không tự thiết kế “so sánh một token trong query string” nếu provider yêu cầu HMAC hoặc chữ ký bất đối xứng.

### Đối chiếu webhook về notification

Một bảng mapping có thể chứa:

| Trường | Vai trò |
|---|---|
| `notificationId` | Email logic nội bộ |
| `attemptId` | Lần submit cụ thể |
| `providerRoute` | Route đã gửi |
| `providerMessageId` | ID được provider cấp |
| `recipientRef` | Người nhận logic |
| `providerEventId` | Khóa deduplicate sự kiện |
| `eventType` | Trạng thái theo provider |
| `occurredAt` | Thời điểm nhà cung cấp ghi nhận |
| `receivedAt` | Thời điểm hệ thống nhận |

Nếu provider SMTP không trả ID qua submission, cần xem provider có cơ chế mapping nào khác được bảo đảm. Không giả định custom `X-Correlation-ID` header sẽ luôn có trong webhook.

## 22. Event đến sai thứ tự: test state machine thay vì last-write-wins

Ví dụ:

```text
12:00 Provider emits DELIVERED
12:01 Webhook DELIVERED received
12:02 Older DEFERRED webhook received
```

Nếu handler luôn lấy event nhận sau cùng để ghi status, hệ thống có thể chuyển `DELIVERED` về `DEFERRED` sai.

Contract test:

- Gửi sự kiện delivered.
- Gửi lại một deferred event xảy ra trước nhưng nhận đến sau.
- Xác nhận event history giữ cả hai.
- Derived state tuân theo policy.
- Trường `receivedAt` không được thay `occurredAt`.

Một số provider có thể có bounce/complaint sau delivered; không nên áp đặt tuyến tính quá cứng nếu contract cho phép. Tốt nhất lưu lịch sử provider events và tính derived status theo quy tắc nghiệp vụ đã công bố.

## 23. Contract về lỗi và Retryability

Nên định nghĩa taxonomy lỗi chung, sau đó map response từng provider.

Ví dụ:

```java
public enum ProviderErrorCategory {
    AUTHENTICATION,
    AUTHORIZATION,
    INVALID_SENDER,
    INVALID_RECIPIENT,
    INVALID_MESSAGE,
    RATE_LIMITED,
    TEMPORARY_UNAVAILABLE,
    CONNECTION,
    TLS,
    QUOTA_EXCEEDED,
    UNKNOWN
}
```

Đừng map mọi status 4xx thành retryable và mọi 5xx thành permanent khi đang phối hợp SMTP và HTTP:

- **SMTP 4xx** thường mô tả lỗi tạm thời, nhưng phải xét lệnh và mã mở rộng.
- **SMTP 5xx** thường mô tả từ chối vĩnh viễn trong ngữ cảnh thao tác.
- **HTTP 4xx** thường là client error, nhưng HTTP 429 có thể retry sau delay.
- **HTTP 5xx** thường biểu thị lỗi server, nhưng không bảo đảm request chưa được xử lý.
- **Timeout** có thể xảy ra trước hoặc sau khi provider nhận message.
- **OAuth token error** có thể cần refresh, thay quyền hoặc dừng route.

### Bảng giả lập mapping

| Tín hiệu | Outcome gợi ý | Error category | Retry |
|---|---|---|---|
| SMTP 535 AUTH reject | REJECTED | AUTHENTICATION | Không retry cùng credential vô hạn |
| SMTP 550 invalid recipient | REJECTED | INVALID_RECIPIENT | Thường không retry tự động |
| SMTP 421 trước submission | REJECTED tạm thời | TEMPORARY_UNAVAILABLE | Có backoff khi phù hợp |
| HTTP 429 kèm retry hint | Theo contract | RATE_LIMITED | Trì hoãn theo chính sách |
| HTTP 400 invalid sender | REJECTED | INVALID_SENDER | Sửa cấu hình/permission |
| HTTP connection timeout trước khi truyền request | Thường chưa submit, nếu có bằng chứng | CONNECTION | Phân loại theo stage |
| Mất kết nối sau khi upload body | UNKNOWN nếu không có bằng chứng | UNKNOWN | Reconcile/controlled retry |
| SMTP 250 sau DATA | ACCEPTED | Không có | Không gửi lại chỉ vì thiếu webhook |

Đây là quy tắc định hướng; test phải dựa vào **response thực sự mà provider trả trong ngữ cảnh**, không lấy mã một cách máy móc.

## 24. Mô phỏng lỗi ngay ở các ranh giới mạng

Mock transport nên có khả năng tạo:

- Connect refused.
- DNS failure.
- TLS handshake failure.
- AUTH reject.
- Slow greeting hoặc response timeout.
- Timeout khi đang gửi request body.
- Mất kết nối trước khi nhận final acceptance.
- Response accepted nhưng local database update lỗi.
- API 429/5xx với header và body thay đổi.
- Provider trả JSON không hợp lệ hoặc thiếu trường bắt buộc.

Một test quan trọng:

```text
Given:
  provider may have accepted message
  transport loses final response

When:
  adapter.submit(command)

Then:
  result is UNKNOWN
  notificationId remains unchanged
  attempt history stores uncertainty
  no automatic claim of definitive delivery
  retry policy considers duplicate risk
```

Không nhất thiết mô phỏng mọi lỗi bằng network thật. Unit test ở lớp adapter có thể inject fake transport ném exception đại diện cho từng giai đoạn; protocol integration test kiểm tra một số case phức tạp hơn.

## 25. Provider contract và thời hạn xử lý

Một số provider có latency cao hoặc độ trễ webhook đáng kể. Contract nên có ngân sách thời gian rõ:

- Connection timeout.
- Read/write timeout.
- Total submission deadline nếu HTTP client hỗ trợ.
- Provider retry policy.
- Queue wait SLO.
- Notification TTL.
- Webhook delivery window.
- API polling/reconciliation interval.

Ví dụ email OTP có hạn 5 phút nhưng provider đang retry 15 phút. Hợp đồng nghiệp vụ phải quyết định job có được gửi tiếp hay không. Không nên bỏ qua `expiresAt` của `MailSubmissionCommand`.

### Không đồng nhất timeout với failed

Khi adapter báo timeout, cần ghi nhận stage nếu có. Một request bị timeout **sau khi provider xử lý** là kết quả khác với không tạo được TCP connection ngay từ đầu.

Test phải phân biệt hai trường hợp, đặc biệt trước khi bật failover tự động.

## 26. Routing và failover cũng có contract

Khi có nhiều provider, route selection thường dựa trên:

- Notification type (transactional, security, bulk).
- Sender domain/profile.
- Tenant hoặc region đã được phép.
- Capability (attachment, HTML, metadata, event support).
- Availability/circuit breaker.
- Rate limit/quota.
- Chi phí hoặc mục tiêu vận hành.
- Data residency và chính sách dữ liệu.

Một router có thể sử dụng:

```java
public interface MailProviderRouter {
    MailProviderPort choose(
            MailSubmissionCommand command
    );
}
```

Contract test của router cần xác nhận:

1. Đúng route cho loại notification.
2. Route có capability đáp ứng message.
3. Route bị disabled không được chọn.
4. Sender profile được phép trên route.
5. Không vượt data-residency policy.
6. Khi provider primary không khả dụng, secondary phù hợp được chọn nếu chính sách cho phép.
7. Không fallback làm mất attachment/metadata.
8. Không tự gửi trùng khi trạng thái primary là UNKNOWN.
9. Retry giữ notification ID và tạo attempt ID mới.
10. Mỗi attempt ghi rõ provider route để correlating webhook.

### Failover không phải lúc nào cũng nên tự động

```text
Primary -> explicit reject before accepting
       -> eligible for fallback depending on policy

Primary -> accepted
       -> no failover just because delivery webhook is late

Primary -> unknown after request body
       -> reconcile or controlled policy; duplicate risk
```

Đây là một trong những contract quan trọng nhất của hệ thống nhiều nhà cung cấp. Nếu adapter mất thông tin outcome, router có thể failover sai và tạo hai email.

## 27. Contract về dữ liệu khi chuyển provider

Một provider có thể đặt yêu cầu định dạng khác cho:

- Sender display name và Reply-To.
- Cách encode subject Unicode.
- Custom headers hoặc metadata.
- Attachment content type và file name.
- Inline image/CID.
- Template rendering phía provider hoặc phía ứng dụng.
- Các trường tracking, unsubscribe và category.
- Recipient personalization.
- DKIM signing và sender domain.
- Return-Path/bounce handling.

Nếu ứng dụng **render trước rồi gửi MIME** qua SMTP, adapter nhận nội dung đã render. Nếu provider API hỗ trợ template ID và biến riêng, adapter có thể chuyển **template reference** thay vì HTML. Hai cách có contract rất khác nhau.

### Chọn một nguồn sự thật cho nội dung

Với nhiều provider, thường thuận tiện hơn khi ứng dụng render subject/plain/HTML một lần rồi chuyển cho adapter. Điều này giảm nguy cơ mỗi provider render khác nhau.

Nếu cần dùng provider-side templates:

- Version hóa template theo provider.
- Ghi mapping logical template → provider template ID.
- Test missing variable, locale, fallback, placeholder syntax.
- Test output preview nếu API cho phép.
- Không giả định hai provider có semantics Mustache/Handlebars giống nhau.
- Có plan khi route failover nhưng secondary không có cùng template version.

**Không tự động chuyển từ provider template ID sang provider khác** nếu không có mapping hoặc bản render tương đương được kiểm chứng.

## 28. Khả năng quan sát và correlation qua provider

Mỗi attempt nên ghi:

```text
correlationId = corr-801
notificationId = notif-601
attemptId = attempt-601-02
providerRoute = smtp-secondary
transport = SMTP
submissionOutcome = ACCEPTED
providerMessageId = null (if unavailable)
```

Provider event về sau có thể có:

```text
providerRoute = smtp-secondary
providerEventId = evt-921
providerMessageId = provider-msg-204
eventType = delivered
```

Khi test contract, xác nhận các ID thuộc **đúng phạm vi**:

- `correlationId`: luồng nghiệp vụ.
- `notificationId`: thông báo logic.
- `attemptId`: một lần thử gửi.
- MIME `Message-ID`: header email theo giao thức.
- `providerMessageId`: ID mà provider công bố.
- `providerEventId`: ID sự kiện callback.

Không tự cho rằng một ID có thể thay thế ID khác. Việc mapping cần lưu bền vững khi cần xử lý webhook sau nhiều giờ.

### Metrics cho provider test

Các meter hữu ích:

```text
mail.provider.submission.attempt
mail.provider.submission.accepted
mail.provider.submission.rejected
mail.provider.submission.unknown
mail.provider.throttled
mail.provider.event.received
mail.provider.event.rejected
mail.provider.event.duplicate
```

Tags nên lấy từ danh mục hữu hạn như `route`, `transport`, `outcome` và `errorCategory`. Không dùng notification ID, recipient hoặc raw exception làm metric tag vì tạo cardinality cao và rủi ro PII.

## 29. Contract testing trong CI không dùng credential production

Một pipeline gợi ý:

```text
Pull request
    |
    +--> Unit contract suite (all adapters)
    +--> SMTP protocol tests with local server
    +--> HTTP API tests with mock server
    +--> Webhook signature/schema tests
    +--> Routing/failover tests
    |
    v
Merge / release candidate
    |
    +--> Provider sandbox verification (approved secrets)
    +--> Contract schema compatibility checks
    |
    v
Controlled deployment
    |
    +--> Low-rate synthetic canary if authorized
    +--> Metrics + webhook monitoring
```

Những điểm cần bảo vệ:

- CI pull request từ code chưa tin cậy không được có credential production.
- Sandbox credential có quyền tối thiểu.
- SMTP test server chỉ nhận thư test, không chuyển tiếp ra Internet.
- HTTP mock server chỉ chạy local/test network.
- Không gửi tới recipient do contributor tùy ý chọn.
- Không log token, password, raw AUTH command hoặc presigned attachment URL.
- Test độc lập, có cleanup, tránh dùng mailbox chung dễ bị nhiễu.

### Tách tên test theo bản chất

Có thể dùng naming:

```text
SmtpProviderAContractTest
SmtpProviderAProtocolTest
SmtpProviderAStagingVerificationTest

ApiProviderCContractTest
ApiProviderCProtocolTest
ApiProviderCStagingVerificationTest

ProviderRoutingContractTest
ProviderWebhookContractTest
```

Staging verification nên được kích hoạt khi có secret/sandbox được cấp phép; nếu thiếu, báo SKIPPED theo test framework hoặc pipeline policy, không âm thầm báo “provider contract passed” khi chỉ chạy mock.

## 30. Contract drift: provider thay đổi chính sách hoặc response

Ngay cả khi code không đổi, provider có thể:

- Ngừng hỗ trợ cơ chế AUTH cũ.
- Thay đổi quota, size limit hoặc recipient limit.
- Yêu cầu sender/domain verification mới.
- Thêm/bỏ trường JSON.
- Đổi webhook signature scheme hoặc event schema.
- Thay đổi status code hoặc retry advice.
- Phân tách API endpoint theo region.
- Ngừng cho phép một loại attachment.
- Thay đổi cách phát provider message ID.
- Đưa ra API version mới hoặc ngừng phiên bản cũ.

Đây là **contract drift**: môi trường bên ngoài không còn khớp giả định được mã hóa trong adapter.

Biện pháp:

1. Ghi rõ API/protocol version được hỗ trợ.
2. Theo dõi changelog và thời hạn thay đổi.
3. Có test schema/provider verification chạy theo lịch được phê duyệt.
4. Giám sát error categories mới và unknown response.
5. Dùng contract fixtures đã version hóa.
6. Khi đổi provider/API version, chạy shared suite lẫn provider-specific suite.
7. Có khả năng disable route theo cấu hình khi contract bị phá vỡ.
8. Không tự động fallback sang route không đủ capability.

**Không để một bài test mock luôn xanh đánh lừa rằng provider thật vẫn tương thích.** Mock chỉ biết những tình huống nhóm đã mô hình hóa.

## 31. Cập nhật contract fixtures theo phiên bản

Một tập fixture có thể có:

```text
contracts/
  smtp/
    accepted-response.txt
    auth-rejected-response.txt
    temporary-failure-response.txt
  api-provider-c/
    v1/
      accepted.json
      rate-limited.json
      invalid-sender.json
      webhook-delivered.json
      webhook-bounced.json
    v2/
      accepted.json
      webhook-delivered.json
```

Đây là cấu trúc tham khảo, không phải yêu cầu tổ chức thư mục của dự án.

Khi cập nhật fixture:

- Ghi rõ provider và phiên bản.
- Ghi nguồn/điều kiện thu thập được phép.
- Loại bỏ token, email thật và PII.
- Không sao chép response chứa dữ liệu khách hàng vào repo.
- Giữ fixture có thể tái hiện trong CI.
- Khi schema thay đổi, review tác động tới mapping và event store.

Không coi việc cập nhật snapshot/fixture cho test xanh là đủ; phải xác nhận **ngữ nghĩa response mới** không làm sai trạng thái nghiệp vụ.

## 32. Kiểm thử sandbox: những điều cần xác minh thật

Sandbox có thể dùng credential riêng và có behavior khác production. Một checklist:

| Nhóm | Kiểm tra |
|---|---|
| Authentication | Credential/scope đúng, token refresh, quyền API/SMTP |
| Sender | Verified sender/domain và quyền sử dụng From |
| Transport | DNS, endpoint, TLS, port, certificate |
| Submission | Accepted response, message ID, status/body |
| Content | Unicode, HTML/plain, attachment nếu sandbox hỗ trợ |
| Limits | Một số giới hạn có thể khác production — ghi nhận rõ |
| Webhook | Event schema, chữ ký, ID, duplicate handling |
| Failure | Các lỗi có thể chủ động mô phỏng trong sandbox |
| Monitoring | Log/metric gắn route và attempt đúng |
| Isolation | Không gửi thư thật ngoài allowlist, không chứa dữ liệu production |

Sandbox test **không cần thử brute-force credential** hoặc cố làm provider khóa tài khoản. Các lỗi như 401/429/5xx nên mô phỏng ở protocol test; sandbox chỉ xác nhận hành vi được phép và khả thi.

Một số sandbox trả success nhưng không thực hiện delivery. Khi đó không đánh dấu test là “confirmed delivered”. Chỉ ghi `SANDBOX_ACCEPTED` hoặc mốc tương ứng.

## 33. Kiểm thử failover với provider lỗi

Ví dụ kịch bản:

```text
Notification N
  |
  +-- Attempt A1 at Provider A
  |      -> known rejection (temporary)
  |
  +-- Policy checks Provider B capabilities
  |
  +-- Attempt B1 at Provider B
         -> accepted
```

Các assertion:

- Notification ID không đổi.
- Attempt ID A1 khác B1.
- Log và DB lưu đúng route mỗi attempt.
- Provider B hỗ trợ đúng sender, attachment, recipient và region.
- Accepted từ B không bị nhầm thành delivered.
- Không gửi thêm lần nữa qua A sau B accepted chỉ vì retry scheduler còn job.
- Không đánh dấu A1 là delivered nếu B1 nhận webhook.
- Error reason dùng taxonomy ổn định.

Kịch bản khác:

```text
Provider A accepts request but response is lost
  -> outcome UNKNOWN

Router:
  -> must not blindly submit to B as though A definitely rejected
```

Tùy policy, cần reconciliation, delay hoặc controlled retry có ghi nhận rủi ro duplicate.

### Sender identity khi failover

Một domain đã xác minh ở A không tự động được xác minh ở B. Contract test phải xác nhận route dự phòng có cấu hình sender/DKIM/SPF/DMARC phù hợp trước khi nhận traffic. Đây không chỉ là vấn đề HTTP 200 hay SMTP 250 mà còn ảnh hưởng deliverability và chính sách bảo mật.

## 34. Kiểm thử multi-provider ở môi trường nhiều tenant

Nếu ứng dụng chọn provider theo tenant hoặc region, các test cần xác nhận:

- Tenant A không được sử dụng credential/sender profile của tenant B.
- Route selection dùng tenant từ security context hoặc bản ghi đã xác minh, không tin input không xác thực.
- Outbox record lưu route/policy context cần thiết.
- Worker ở replica khác có thể tái tạo đúng sender profile.
- Provider webhook chỉ cập nhật notification thuộc route/tenant phù hợp.
- Cross-region failover tuân thủ data residency.
- Địa chỉ recipient không bị lộ trong metric labels hoặc raw debug log.
- Config rotation không làm request đang chạy dùng sai tenant token.

Tránh dùng `tenantId` tự do làm Micrometer metric tag nếu số tenant lớn. Với giám sát theo tenant, dùng dữ liệu bền vững và hệ thống truy vấn có quyền phù hợp.

## 35. Một bộ test case theo ma trận

| Tình huống | Shared contract | Provider-specific |
|---|---|---|
| Email text-only hợp lệ | Có | Kiểm tra transport/response |
| HTML và plain text | Có | Kiểm tra encoding/MIME/API mapping |
| Recipient không hợp lệ | Có | Error code và policy cụ thể |
| Sender chưa được phê duyệt | Có | Quyền From/domain thực tế |
| Subject Unicode | Có | Header encoding hoặc API JSON |
| Attachment sát size limit | Có | Limit/encoding từng provider |
| Inline CID | Chỉ khi capability hỗ trợ | MIME/API contract riêng |
| SMTP AUTH reject | Không áp dụng cho API token | SMTP-specific |
| API token hết hạn | Không áp dụng cho password SMTP | API-specific |
| HTTP 429 Retry-After | Taxonomy chung | Parsing theo API |
| SMTP 4xx temporary | Taxonomy chung | SMTP-specific |
| Timeout sau request body | Unknown outcome | Mock transport cụ thể |
| Provider accepted | Không map thành delivered | Response-specific |
| Webhook trùng | Dedupe chung | Signature/event schema |
| Event sai thứ tự | State policy chung | Timestamp/ID semantics |
| Fallback route | Không gửi trùng, giữ logical ID | Capability/identity |
| Provider-specific quota | Giới hạn chung | Quota/hint từng route |
| Credential rotation | Không lộ secret, xử lý failure | Auth lifecycle |
| Missing capability | Fail rõ hoặc route hợp lệ | Capability matrix |
| Malformed response | Unknown/protocol error có kiểm soát | Parser schema |
| Sandbox accepted/no delivery | Không nói delivered | Đặc tính sandbox |

Ma trận không phải danh sách bắt buộc giống nhau cho mọi sản phẩm. Chỉ chạy test có ý nghĩa với capability của provider; với chức năng không hỗ trợ, cần một test xác nhận **ứng dụng từ chối rõ ràng** thay vì bỏ qua.

## 36. Kịch bản test dữ liệu biên

Bên cạnh response codes, cần test dữ liệu:

- Recipient `null`, rỗng, khoảng trắng và địa chỉ sai định dạng.
- Một recipient, nhiều recipient và duplicate recipient.
- Subject Unicode, emoji, dấu nháy, CR/LF hoặc quá dài.
- Body trống, plain-only, HTML-only, plain+HTML.
- HTML chứa nội dung user đã được escape.
- Attachment rỗng, nhiều attachment và size sát giới hạn.
- Filename có dấu, ký tự điều khiển hoặc path separator.
- Sender profile không tồn tại hoặc bị disabled.
- Expiry timestamp đã qua.
- Template version không có trên route provider-side.
- Provider ID không có, quá dài hoặc sai schema.
- Webhook payload có event ID trùng và timestamp bất thường.

Khi thiếu trường required, adapter không nên thực hiện network call. Ví dụ:

```java
@Test
void rejectsMissingRecipientBeforeCallingTransport() {
    MailSubmissionCommand invalid =
            commandWithRecipients(java.util.List.of());

    assertThatThrownBy(() ->
            provider.submit(invalid, "attempt-invalid")
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(transportClient);
}
```

`commandWithRecipients`, `provider` và `transportClient` là fixture; nếu ứng dụng dùng kiểu kết quả validation thay exception thì assertion phải theo contract đó.

## 37. Kiểm thử cấu hình đúng provider

Khi dùng nhiều `JavaMailSenderImpl`, cần tránh inject nhầm bean.

Ví dụ cấu hình Spring có tên cụ thể:

```java
@Configuration
public class MailProvidersConfiguration {

    @Bean("primaryMailSender")
    public JavaMailSenderImpl primaryMailSender(
            PrimarySmtpProperties properties
    ) {
        return configureSender(properties);
    }

    @Bean("backupMailSender")
    public JavaMailSenderImpl backupMailSender(
            BackupSmtpProperties properties
    ) {
        return configureSender(properties);
    }
}
```

`PrimarySmtpProperties`, `BackupSmtpProperties` và `configureSender` là thành phần minh họa của ứng dụng.

Ở adapter:

```java
public SmtpBackupAdapter(
        @Qualifier("backupMailSender")
        JavaMailSender sender
) {
    this.sender = sender;
}
```

Contract/component test cần bảo đảm:

1. Primary adapter dùng primary sender, backup adapter dùng backup sender.
2. Credential không bị trộn giữa hai cấu hình.
3. Property TLS/auth đúng cho mỗi bean.
4. Sender profile/From mapping đúng route.
5. Khi thiếu bean, ứng dụng fail cấu hình rõ thay vì fallback ngầm.
6. Secret không xuất hiện trong `toString()`, health detail hoặc log.
7. Không dùng `@Primary` làm lối tắt dẫn đến mọi adapter cùng dùng một sender.

Nếu dùng HTTP client riêng, áp dụng tương tự với base URL và authentication provider-specific.

## 38. Không chạy real send trong health indicator

Một mail provider có thể hỗ trợ test connection hoặc health endpoint. Nhưng health check không được gọi `submit` rồi gửi email thật mỗi lần được scrape.

Các mức cần tách:

- Cấu hình adapter có đủ field hợp lệ.
- SMTP connect/auth bằng `JavaMailSenderImpl.testConnection()` khi được phép.
- HTTP provider health/status API nếu có và công bố.
- Worker/queue/outbox health.
- Synthetic E2E send có chủ đích theo lịch và allowlist recipient.

Một sandbox contract test có thể gửi email test vì đó là **một test được phê duyệt**, không phải health probe định kỳ.

Nếu có nhiều provider, việc test connection tất cả route trên mọi `GET /actuator/health` có thể gây thừa số lần AUTH, chậm request hoặc kích hoạt rate limit. Nên cân nhắc cache, background probe và health group phù hợp.

## 39. Hạn chế test flaky và phụ thuộc môi trường

Contract test dễ không ổn định nếu dùng:

- Email provider thật trong mọi unit test.
- Thời gian hiện tại `Instant.now()` không được cố định.
- Mailbox test dùng chung với nhiều pipeline.
- Retry dùng `Thread.sleep(...)` với timing khó kiểm soát.
- Random IDs không được giữ khi assertion.
- API rate limit bị nhiều job CI cùng sử dụng.
- Webhook async không có cách chờ/đối chiếu ổn định.
- DNS/network Internet phụ thuộc điều kiện ngoài dự án.

Biện pháp:

1. Mock protocol cho unit test.
2. Dùng clock/ID supplier có thể thay bằng fixture.
3. Fake retry scheduler để assert thời điểm hẹn, không sleep thật.
4. Dùng port ngẫu nhiên/local server khi có thể.
5. Namespace notification ID theo test run.
6. Có timeout hữu hạn và cleanup tất cả resource.
7. Phân tách sandbox verification khỏi pull-request checks.
8. Log failure có attempt/provider route nhưng không có secrets.
9. Khi test external thất bại, phân biệt **provider unavailable** với **contract violated**.
10. Không auto-retry test nhiều lần để che một lỗi contract thật.

### Trạng thái kiểm thử phải trung thực

Nếu sandbox chưa chạy vì thiếu token, báo **SKIPPED** ở pipeline stage tương ứng; không trình bày kết quả mock như một lần xác minh provider thật.

Nếu staging đang outage, ghi nhận đó là blocker verification; không tự sửa assertion cho “xanh” khi ngữ nghĩa chưa được hiểu.

## 40. Quy trình kiểm thử khi onboarding provider mới

Một workflow thực tế:

1. **Thu thập tài liệu chính thức:** SMTP/API endpoint, authentication, sender policy, payload, error model, quota, webhook.
2. **Tạo capability profile:** đánh dấu supported/unsupported/unknown rõ.
3. **Định nghĩa mapping vào common port:** notification, recipient, content, attachment, outcome.
4. **Tạo adapter:** tách mapping và transport khỏi business service.
5. **Chạy shared contract suite:** các bất biến chung cho mọi provider.
6. **Viết provider-specific protocol tests:** AUTH/TLS hoặc HTTP schema/headers/status.
7. **Kiểm thử failure classification:** 4xx/5xx/429, timeout, partial acceptance, missing ID.
8. **Kiểm thử webhook:** signature, dedupe, mapping, out-of-order.
9. **Kiểm thử routing/failover:** sender capability, policy, unknown outcome.
10. **Sandbox verification:** credential/sender/response thực, dưới giới hạn được cho phép.
11. **Controlled canary nếu cần:** mailbox synthetic, rate nhỏ, theo dõi.
12. **Quan sát sau rollout:** accepted rate, unknown errors, throttling, bounce và contract drift.
13. **Version hóa contract:** khi provider thay đổi API hoặc policy, cập nhật fixtures/tests có review.

Nếu provider không hỗ trợ một feature quan trọng, hãy thay đổi route policy hoặc hợp đồng sản phẩm có chủ đích; không đơn giản bỏ assertion để đưa provider vào production.

## 41. Runbook khi provider bắt đầu vi phạm contract

### Trường hợp A: SMTP AUTH đột nhiên bị từ chối

- Xác định route và số instance bị ảnh hưởng.
- Kiểm tra secret/token rotation, policy AUTH, endpoint và TLS.
- Không retry liên tục cùng credential.
- Chạy connectivity test có giới hạn.
- Nếu có failover, kiểm tra secondary đủ quyền sender và phù hợp dữ liệu.
- Ghi nhận contract giả định nào đã thay đổi.

### Trường hợp B: API trả một trường JSON mới hoặc bỏ trường cũ

- Ghi nhận response version/status và parser failure an toàn.
- Giữ raw response có kiểm soát quyền nếu chính sách cho phép; loại bỏ PII/secret.
- Nếu thiếu bằng chứng accepted, không tự báo success.
- Cập nhật fixture và mapping theo tài liệu provider.
- Chạy lại protocol tests và staging verification.

### Trường hợp C: Webhook delivered không map được message

- Xác minh chữ ký/schema/provider route.
- Kiểm tra provider message ID và recipient mapping.
- Kiểm tra có event từ attempt cũ hoặc failover không.
- Không cập nhật notification bằng correlation ID đơn lẻ.
- Đưa event chưa map vào luồng điều tra/reconciliation, tránh mất dữ liệu.

### Trường hợp D: Provider throttling tăng sau khi thêm replica

- Kiểm tra tổng rate trên mọi instance.
- Xem quota theo account/region/sender, không chỉ local limiter.
- Giảm concurrency/rate, bật backoff và jitter.
- Không gửi replay backlog một lần.
- Test lại retry hint và fairness trước khi mở rộng.

### Trường hợp E: Test mock xanh nhưng sandbox thất bại

- Kiểm tra mock đã mô hình hóa đúng tài liệu provider chưa.
- So sánh API version và quyền của sandbox account.
- Phân biệt chính sách/giới hạn môi trường test với production.
- Không giả định sandbox success chứng minh delivery.
- Cập nhật contract profile và bổ sung regression fixture có kiểm soát.

## 42. Checklist kiểm thử trước khi bật provider

| Câu hỏi | Kỳ vọng |
|---|---|
| Common provider-port contract đã được mô tả? | Có |
| Shared contract suite chạy với adapter mới? | Có |
| Capability profile được xác minh và version hóa? | Có |
| Không tự bỏ attachment/recipient khi không hỗ trợ? | Có |
| Sender profile được phép trên route? | Có |
| Auth/TLS đúng và không gửi credential qua kênh yếu? | Có |
| Subject, HTML/plain, Unicode và MIME mapping đúng? | Có |
| Accepted không đồng nghĩa delivered? | Có |
| Rejected/unknown được phân biệt? | Có |
| Provider ID có thể trống và được xử lý đúng? | Có |
| Error taxonomy và retryability được kiểm thử? | Có |
| Rate limit/quota được áp dụng đúng phạm vi? | Có |
| Webhook được xác thực/deduplicate nếu hỗ trợ? | Có |
| Event trễ/sai thứ tự không làm sai trạng thái? | Có |
| Failover không gửi trùng mù khi primary UNKNOWN? | Có |
| Multi-tenant/region data policy được kiểm tra? | Có nếu áp dụng |
| Mock protocol và sandbox test có mục tiêu riêng? | Có |
| CI không dùng credential production/recipient tùy ý? | Có |
| Có runbook khi contract drift? | Có |
| Có log/metric theo provider route và attempt? | Có |

## 43. Các hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| “Cùng interface thì provider thay thế cho nhau hoàn toàn” | Capability, policy, quota và event semantics có thể khác. |
| “Mock send thành công nghĩa là provider hoạt động” | Mock chỉ chứng minh code của mình tương tác với giả lập. |
| “SMTP 250 nghĩa là người nhận đã đọc thư” | Thường chỉ là acceptance của next-hop SMTP tại bước tương ứng. |
| “Provider trả HTTP 202 là delivered” | HTTP 202 thường chỉ là accepted/queued theo contract. |
| “Timeout nghĩa là chắc chắn chưa gửi” | Có thể đã xử lý trước khi response bị mất. |
| “Mọi lỗi 4xx đều retry giống nhau” | SMTP và HTTP có ngữ nghĩa khác; cần phân loại theo stage/provider. |
| “Bật idempotency header là đủ” | Chỉ có tác dụng nếu provider hỗ trợ và scope/key đúng. |
| “Provider nào cũng có webhook delivered” | Có thể không hỗ trợ hoặc chỉ hỗ trợ theo gói/cấu hình. |
| “Custom email header chắc chắn quay lại trong webhook” | Phụ thuộc provider; không có bảo đảm chung. |
| “Failover qua provider B luôn an toàn” | Cần capability, sender identity, data policy và outcome của primary. |
| “Một sandbox test đủ cho production” | Sandbox có thể mô phỏng/giới hạn khác và không gửi thật. |
| “Tăng worker sẽ vượt qua rate limit” | Có thể làm throttling và retry storm nặng hơn. |
| “Cập nhật fixture để test xanh là hoàn tất” | Cần hiểu thay đổi ngữ nghĩa và ảnh hưởng trạng thái nghiệp vụ. |

## 44. Ghi nhớ

- **Contract của từng provider** gồm khả năng được hỗ trợ, authentication/TLS, mapping nội dung, sender/recipient policy, response semantics, quota, webhook và lỗi.
- Một provider port chung giúp business service độc lập với SMTP/API, nhưng không có nghĩa tất cả provider đồng nhất.
- Dùng **shared contract tests** cho các bất biến chung và **provider-specific tests** cho điểm khác biệt thật.
- Test SMTP protocol bằng server thử nghiệm; test HTTP provider bằng mock server; dùng sandbox/staging để xác minh quyền và hành vi thực sự.
- `JavaMailSender.send(...)` thành công hoặc HTTP API accepted **không chứng minh inbox delivery**.
- Phân biệt `ACCEPTED`, `REJECTED` và `UNKNOWN` để không retry/failover mù dẫn tới gửi trùng.
- Không giả định provider nào cũng có message ID, idempotency hoặc delivery webhook.
- Webhook phải được xác thực, deduplicate, map đúng provider/recipient/attempt và chịu được event sai thứ tự.
- Capability không hỗ trợ phải bị từ chối rõ ràng hoặc được route sang provider tương thích; không bỏ dữ liệu âm thầm.
- Rate limit và quota là tài nguyên hữu hạn, có thể dùng chung giữa nhiều replica.
- Giữ notification ID ổn định; tạo attempt ID riêng cho mỗi lần thử và lưu provider route của attempt.
- Test credential và sender permission trong môi trường được phê duyệt; không dùng credential production trong unit/PR test.
- Provider có thể thay đổi contract ngay cả khi code không đổi; cần versioned fixtures, sandbox verification và runbook.
- Health probe không được tự động gửi email thật; synthetic delivery test cần tần suất, mailbox và quyền riêng.
- Khi failover, điều quan trọng là **không thay đổi ý nghĩa nghiệp vụ của email** và không khẳng định chắc chắn một kết quả mà transport chưa chứng minh.

**Kết luận:** Trong hệ thống Spring Framework Mail dùng nhiều nhà cung cấp, độ tin cậy không đến từ việc thêm một adapter mới rồi thấy `send` trả về thành công. Nó đến từ **hợp đồng được viết rõ, bộ kiểm thử dùng chung áp dụng cho mọi adapter, test giao thức đặc thù và xác minh với provider thật ở môi trường có kiểm soát**. Khi từng route chứng minh được khả năng, cách phản hồi, giới hạn và sự kiện delivery của mình, ứng dụng có thể đổi route, failover và nâng cấp tích hợp mà không đánh đổi tính chính xác của nội dung, trạng thái hoặc dữ liệu người nhận.
