# Không đọc failed message trong MailSendException

Khi ứng dụng **Spring Framework Mail** gửi nhiều email trong một batch, một lỗi của lệnh `JavaMailSender.send(...)` không nhất thiết có nghĩa **tất cả message đều thất bại theo cùng cách**. Một email có thể đã được SMTP relay chấp nhận, email khác bị từ chối vì recipient không hợp lệ, và email còn lại chưa được gửi do kết nối bị ngắt.

Một anti-pattern thường gặp:

~~~java
try {
    mailSender.send(messages);
} catch (MailException ex) {
    log.error("Gửi email thất bại", ex);
    markEveryJobAsFailed(batch);
}
~~~

Code trên chỉ nhìn **exception tổng thể** và bỏ qua thông tin message-level mà Spring có thể cung cấp. Khi exception cụ thể là `MailSendException`, phương thức `getFailedMessages()` trả về map liên kết **message không gửi được** với **exception tương ứng**; `getMessageExceptions()` có thể dùng để xem các lỗi message đã được tổng hợp.

Việc **không đọc failed message trong MailSendException** khiến hệ thống khó chẩn đoán lỗi theo job, dễ retry sai phạm vi, ghi audit thiếu thông tin và khó phân biệt message-level failure với lỗi transport cấp batch.

Tuy nhiên, `getFailedMessages()` **không phải delivery ledger**. Nó không chứng minh email vắng mặt trong map đã vào inbox; cũng không tự xử lý partial recipients hoặc SMTP timeout sau `DATA`. Muốn xử lý đáng tin cậy cần hiểu **exception type, object identity, scope của lỗi, idempotency, outbox và điều kiện retry**.

Bài học phân tích các API Spring Mail, cách xây diagnostic theo từng message, ví dụ Java, trường hợp gửi một/nhiều recipients, cause chain của Jakarta Mail, cấu trúc logging an toàn, kiểm thử và vận hành.

## 1. Một email khác batch email như thế nào?

Với một message duy nhất:

~~~java
MimeMessage mime =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                mime, false, "UTF-8"
        );

helper.setTo("buyer@example.org");
helper.setSubject("Đã xác nhận đơn hàng");
helper.setText("Đơn hàng ORD-981 đã xác nhận.");

mailSender.send(mime);
~~~

Nếu có lỗi, caller biết job đang xử lý vì chỉ có một message. Tuy nhiên, vẫn phải phân loại lỗi và xem khả năng SMTP đã accept trước khi kết nối bị ngắt.

Với batch:

~~~java
MimeMessage a = createMessageA();
MimeMessage b = createMessageB();
MimeMessage c = createMessageC();

mailSender.send(a, b, c);
~~~

Một tình huống có thể là:

~~~text
Message A: relay accepted
Message B: recipient invalid
Message C: gặp lỗi transport hoặc chưa được thử
~~~

Nếu catch exception tổng rồi mark toàn bộ `FAILED` hoặc retry cả batch, message A có nguy cơ được gửi lại và người nhận nhận thư trùng.

Ngược lại, nếu chỉ log exception rồi mark batch hoàn tất, B hoặc C có thể không bao giờ được retry/xử lý.

**Muốn ra quyết định theo mail job, phải liên hệ được thông tin lỗi với từng message thực tế.**

## 2. Các exception Spring Mail có liên quan

| Exception | Phạm vi khái quát | Hướng xử lý |
| --- | --- | --- |
| `MailException` | Base abstraction cho lỗi Spring Mail | Catch tổng, log/propagate theo policy |
| `MailSendException` | Lỗi khi gửi, có thể có failed-message map | Đọc `getFailedMessages()` và cause |
| `MailAuthenticationException` | Xác thực SMTP thất bại | Kiểm tra credential, không retry nóng |
| `MailPreparationException` | Chuẩn bị mail thất bại | Kiểm tra composer/template |
| `MailParseException` | Vấn đề parse/chuẩn bị nội dung | Kiểm tra MIME/địa chỉ/dữ liệu |
| Jakarta Mail `MessagingException` | Lỗi cấp mail transport/format | Thường xuất hiện trong cause/nested chain |

Không phải tất cả lỗi đều mang dữ liệu `getFailedMessages()`. Bắt quá tổng quát có thể đánh mất nhánh xử lý đặc thù:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    // Message-level + transport diagnostics.
} catch (MailAuthenticationException ex) {
    // Credential/account-level error.
} catch (MailException ex) {
    // Những dạng Spring Mail error khác.
}
~~~

Các catch độc lập nêu trên minh họa trật tự từ chuyên biệt đến tổng quát. `MailAuthenticationException` và `MailSendException` là các nhánh khác nhau của `MailException`; nếu đặt `MailException` trước, các nhánh sau không thể reach.

## 3. getFailedMessages() trả về dữ liệu gì?

API:

~~~java
Map<Object, Exception> failures =
        mailSendException.getFailedMessages();
~~~

Mỗi entry gồm:

- **Key:** message object được ghi nhận là thất bại.
- **Value:** `Exception` mô tả nguyên nhân tương ứng.

Kiểu key là **`Object`** chứ không phải luôn `MimeMessage`. Trong đường đi Spring Mail thông thường, nó có thể liên hệ với `MimeMessage` hoặc `SimpleMailMessage` nguyên gốc tùy overload và quá trình chuyển đổi nội bộ.

Ví dụ mô hình:

~~~text
MailSendException
  failedMessages:
    MimeMessage B -> SendFailedException
    MimeMessage C -> MessagingException
~~~

Một sai lầm là cast vô điều kiện:

~~~java
for (Object key : ex.getFailedMessages().keySet()) {
    MimeMessage failed = (MimeMessage) key;
}
~~~

Code này có thể lỗi nếu ứng dụng gửi `SimpleMailMessage[]` và map chứa các original simple messages.

**Quy tắc:** Xử lý kiểu object tương ứng với sender API/overload được sử dụng; nếu không nhận diện được, ghi nhận unknown mapping thay vì cast hoặc gán sang job khác.

## 4. getMessageExceptions() khác getFailedMessages()

Có thể đọc:

~~~java
Exception[] messageCauses =
        ex.getMessageExceptions();
~~~

Đây là cách xem các exception liên quan tới thất bại ở cấp message. Nhưng khi cần biết **mail job nào gặp exception nào**, map key → value thường hữu ích hơn.

| API | Cung cấp | Không tự bảo đảm |
| --- | --- | --- |
| `getFailedMessages()` | Message object → exception | Toàn bộ delivery/attempt state |
| `getMessageExceptions()` | Mảng exception liên quan message | Mapping tới từng job nếu không có keys |
| `getCause()` | Cause tổng/cấp cao | Mọi lỗi từng recipient |
| `getMessage()` | Text mô tả | Định dạng máy có thể parse ổn định |
| Stack trace | Vị trí gọi trong code | SMTP acceptance/delivery outcome |

Không suy ra index message từ thứ tự mảng exception, và không parse `getMessage()` bằng regex rồi đưa thành nguồn sự thật cho permanent/transient policy.

## 5. Ví dụ đọc failed-message map khi catch

~~~java
try {
    mailSender.send(messages);

} catch (MailSendException ex) {

    Map<Object, Exception> failures =
            ex.getFailedMessages();

    log.warn(
            "Mail batch failure, failedEntries={}",
            failures.size()
    );

    for (Map.Entry<Object, Exception> entry
            : failures.entrySet()) {

        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        log.warn(
                "Mail item failure: messageType={}, causeType={}",
                failedMessage == null
                        ? "unknown"
                        : failedMessage.getClass()
                                .getSimpleName(),
                cause == null
                        ? "unknown"
                        : cause.getClass()
                                .getSimpleName()
        );
    }

    throw ex;
}
~~~

Ở đây chỉ log **type** để tránh vô tình ghi raw recipient/subject/body. Trong production nên log thêm `mailJobId`, `attemptId`, `providerId` hoặc error category đã chuẩn hóa.

Gọi `throw ex` giúp upstream tiếp tục biết batch thất bại. Nếu gateway đã ghi trạng thái cho từng job và không throw lại, cần hợp đồng rõ để caller không coi toàn batch đã thành công.

## 6. Vì sao không chỉ log exception tổng?

Hai cách logging:

~~~java
log.error("Could not send mail", ex);
~~~

và:

~~~text
batchId: batch-981
providerId: relay-a
failedEntries: 2

jobId: job-B
  failureCategory: INVALID_RECIPIENT

jobId: job-C
  failureCategory: TEMPORARY_TRANSPORT
~~~

khác nhau đáng kể về tính hữu ích.

Log tổng có stack trace nhưng không nhất thiết trả lời được:

- Có mấy message thất bại?
- Job cụ thể nào bị lỗi?
- Có recipient nào sai định dạng/không tồn tại?
- Lỗi là account-level hay message-level?
- Có thể retry riêng từng job không?
- Đã có attempt nào có kết quả chưa chắc chắn?
- Sự cố ảnh hưởng một tenant hay toàn provider?

Nếu mỗi batch chứa hàng chục email, không đọc failed map làm giảm khả năng điều tra sự cố và quyết định retry chính xác.

## 7. Map rỗng không đồng nghĩa không có lỗi

`getFailedMessages()` có thể **rỗng** khi exception đại diện cho vấn đề tổng ở cấp transport/connection hoặc khi implementation không đưa chi tiết vào map.

Không viết:

~~~java
if (ex.getFailedMessages().isEmpty()) {
    markBatchSubmitted(batchId);
}
~~~

Đây là cách hiểu sai. Exception đã báo lỗi, chỉ là **không có failed-message entry để đối chiếu**.

Một pattern an toàn hơn:

~~~java
Map<Object, Exception> failed =
        ex.getFailedMessages();

if (failed.isEmpty()) {
    recordGlobalFailure(
            batchId,
            ex.getCause()
    );
} else {
    recordItemFailures(
            batchId,
            failed
    );
}
~~~

`recordGlobalFailure` và `recordItemFailures` là abstraction của ứng dụng. Khi thiếu chứng cứ kết quả từng message, trạng thái nên phản ánh **unresolved/unknown outcome** thay vì biến toàn batch thành success.

## 8. Message vắng mặt trong map có chắc đã gửi thành công?

**Không có quy tắc phổ quát “not in failed map = delivered”.**

Cần xét:

1. Spring sender có thể gửi thành công một số message trước khi lỗi.
2. Một số message chưa được thử do connection failure.
3. Relay có thể accept message nhưng client mất response.
4. Một MIME message có nhiều recipients, server có thể accept một phần.
5. Thư viện sender/overload có thể khác nhau ở cách ghi failed entries.
6. Delivery đến inbox là quá trình phía sau submission.

Ở một implementation/version cụ thể, sau khi đọc contract và thử nghiệm, bạn có thể biết điều kiện mà sender ghi keys. Nhưng không nên đưa một giả định không được kiểm chứng thành bảo đảm nghiệp vụ toàn hệ thống.

**`getFailedMessages()` là thông tin thất bại quan sát được; nó không phải danh sách xác nhận mọi external side effect.**

## 9. Liên kết failed message với mail job

Một batch nên giữ job ID cùng object đã tạo:

~~~java
public record MailItem(
        UUID jobId,
        MimeMessage message) {
}
~~~

~~~java
List<MailItem> items =
        prepareMessages(outboxJobs);

MimeMessage[] batch =
        items.stream()
                .map(MailItem::message)
                .toArray(MimeMessage[]::new);
~~~

Với MIME object dùng trong batch, có thể lập map theo **object identity**:

~~~java
Map<MimeMessage, UUID> jobByObject =
        new IdentityHashMap<>();

for (MailItem item : items) {
    jobByObject.put(
            item.message(),
            item.jobId()
    );
}
~~~

Khi catch:

~~~java
for (Map.Entry<Object, Exception> entry
        : ex.getFailedMessages().entrySet()) {

    UUID jobId = null;
    Object key = entry.getKey();

    if (key instanceof MimeMessage mime) {
        jobId = jobByObject.get(mime);
    }

    if (jobId == null) {
        recordUnmappedFailure(
                batchId, entry.getValue()
        );
    } else {
        recordFailureForJob(
                jobId, entry.getValue()
        );
    }
}
~~~

`prepareMessages` và các methods record là API minh họa. `IdentityHashMap` hữu ích khi cần đối chiếu **đúng instance** đã truyền vào sender.

Điều kiện quan trọng: key trong failed map phải là object mà integration boundary có thể map. Không mặc định mọi implementation/overload luôn giữ cùng identity.

## 10. Vì sao không map job theo subject hoặc recipient?

Một anti-pattern:

~~~java
UUID jobId =
        findJobBySubject(message.getSubject());
~~~

Nhiều mail có thể cùng subject `Xác nhận đơn hàng`. Một recipient có thể nhận nhiều thông báo với To giống nhau; một mail cũng có thể có nhiều recipients.

Header `Message-ID` hoặc `X-Correlation-ID` có thể giúp trace, nhưng:

- Có thể được tạo lại khi compose/retry.
- Có thể thiếu hoặc bị thay đổi.
- Không bảo đảm external provider dedupe.
- Không nên thay thế job/attempt ID nội bộ.

**Gắn job ID với object tại thời điểm tạo batch** giúp rõ hơn việc đoán mapping từ nội dung email.

## 11. SimpleMailMessage cần xử lý key riêng

Ví dụ:

~~~java
SimpleMailMessage first =
        new SimpleMailMessage();

first.setTo("first@example.org");
first.setSubject("Thông báo A");
first.setText("Nội dung A");

SimpleMailMessage second =
        new SimpleMailMessage();

second.setTo("second@example.org");
second.setSubject("Thông báo B");
second.setText("Nội dung B");

mailSender.send(first, second);
~~~

Đường gửi simple mail có thể lưu **original SimpleMailMessage** làm key, trong khi đường gửi MIME có thể dùng `MimeMessage`.

Một adapter chẩn đoán có thể nhận biết:

~~~java
Object key = entry.getKey();

if (key instanceof SimpleMailMessage simple) {
    // Lookup original simple message -> jobId.
} else if (key instanceof MimeMessage mime) {
    // Lookup MIME instance -> jobId.
} else {
    // Không gán nhầm: record unknown message type.
}
~~~

Không cast mọi key sang MIME. Khi gửi dữ liệu nhạy cảm, không gọi `simple.toString()` hoặc serialize full message vào log để đối chiếu.

## 12. Đừng suy thứ tự batch từ failed map

Không nên dùng:

~~~java
int failedIndex =
        ex.getFailedMessages().size() - 1;
~~~

Số lượng entries không đồng nghĩa vị trí message đầu tiên thất bại. `Map` không phải contract về index của mảng đầu vào. Cũng không thể dùng thứ tự `getMessageExceptions()` để khôi phục index tin cậy.

Cần:

- Giữ `MailItem(jobId, message)` theo batch.
- Gắn attempt ID cho mỗi job.
- Map object identity khi API cho phép.
- Đánh dấu unknown mapping nếu không thể đối chiếu.
- Không tự suy rằng message có index thấp hơn đã chắc chắn delivered.

Với use case cần outcome rõ theo job và không cần hiệu năng batch, lựa chọn **một send call cho một message** thường giảm complexity đáng kể.


## 13. Một failed MIME message có thể chứa nhiều recipients

Một message:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, false, "UTF-8"
        );

helper.setTo(new String[] {
        "a@example.org",
        "b@example.org",
        "c@example.org"
});

helper.setSubject("Thông báo bảo trì");
helper.setText("Dịch vụ bảo trì theo lịch.");

mailSender.send(message);
~~~

Một SMTP relay có thể accept `a@example.org`, từ chối `b@example.org` và chưa gửi cho `c@example.org`. `MailSendException#getFailedMessages()` biểu diễn thất bại theo **message object**, không phải một map riêng cho từng recipient.

Một exception message-level có thể chứa thông tin recipient-level trong Jakarta Mail:

~~~text
MimeMessage:
  recipient A: validSent
  recipient B: invalid
  recipient C: validUnsent

MailSendException:
  key = MimeMessage
  value = SendFailedException / transport detail
~~~

Không có nghĩa mọi provider luôn trả đủ các mảng này. Đó là thông tin tùy connection, SMTP reply và transport behavior.

Nếu retry nguyên MIME, A có thể nhận trùng. Nếu bỏ hết MIME, C có thể không nhận thông báo. Vì vậy hệ thống cần một policy thật sự hiểu **partial send**.

## 14. SendFailedException và các nhóm address

Jakarta Mail có `SendFailedException` với các API:

~~~java
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

void reportRecipientGroups(
        SendFailedException ex) {

    Address[] invalid =
            ex.getInvalidAddresses();

    Address[] validSent =
            ex.getValidSentAddresses();

    Address[] validUnsent =
            ex.getValidUnsentAddresses();

    log.warn(
            "Recipient outcomes: invalid={}, " +
            "validSent={}, validUnsent={}",
            invalid == null ? 0 : invalid.length,
            validSent == null ? 0 : validSent.length,
            validUnsent == null ? 0 : validUnsent.length
    );
}
~~~

Ý nghĩa khái quát:

| Nhóm | Ý nghĩa được báo cáo |
| --- | --- |
| `invalidAddresses` | Các địa chỉ transport xác định không hợp lệ |
| `validSentAddresses` | Các địa chỉ được transport báo đã gửi/được nhận ở mức liên quan |
| `validUnsentAddresses` | Các địa chỉ hợp lệ nhưng chưa gửi |
| null/rỗng | Không có thông tin cho nhóm này; không suy ra kết quả nhóm khác |

**ValidSent không chứng minh delivered vào inbox.** Nó chỉ mô tả kết quả ở tầng transport của exception, không phải event delivery cuối cùng.

Trong production, cần theo dõi recipient ID ở job store và so sánh dữ liệu transport theo một mapping đáng tin, không log toàn bộ địa chỉ nếu không có lý do và quyền tương ứng.

### Vì sao một job một recipient thường dễ hơn?

Với một job/recipient:

- Idempotency key rõ theo recipient.
- Retry độc lập.
- Suppression và unsubscribe rõ.
- Không lộ To/Cc của người nhận khác.
- Dễ ghi attempt/delivery status.
- Thất bại của B không bắt buộc kéo theo A.

Nếu nghiệp vụ sử dụng một message nhiều người, phải có recipient-level outcome handling hoặc chấp nhận chính sách retry đặc thù.

## 15. Cause chain của Jakarta Mail

Lỗi SMTP thực tế có thể được Spring bọc lại thành `MailSendException`, bên trong có `MessagingException` hoặc subclass.

Điều tra cần xem:

~~~java
Throwable topCause =
        ex.getCause();

Map<Object, Exception> failed =
        ex.getFailedMessages();

Exception[] messageFailures =
        ex.getMessageExceptions();
~~~

Đừng chỉ đọc một dòng `ex.getMessage()` rồi kết luận nguyên nhân.

Jakarta Mail `MessagingException` còn có:

~~~java
MessagingException#getNextException()
~~~

Nó có thể chứa additional transport error không đi theo Java `getCause()` giống cách ứng dụng tưởng tượng.

Ví dụ diagnostic traversal có giới hạn:

~~~java
import jakarta.mail.MessagingException;

void visitMailExceptions(
        MessagingException initial) {

    MessagingException current = initial;

    int depth = 0;

    while (current != null && depth++ < 16) {

        log.debug(
                "Mail nested exception type={}",
                current.getClass().getSimpleName()
        );

        Exception next =
                current.getNextException();

        current = next instanceof
                MessagingException nested
                        ? nested
                        : null;
    }
}
~~~

Ví dụ chỉ đi qua các node `MessagingException`. Một collector đầy đủ cũng có thể ghi nhận node cuối không thuộc kiểu đó, đồng thời theo dõi visited identities để phòng vòng lặp bất thường.

### Không parse exception text thành business rule

Tránh:

~~~java
if (ex.getMessage().contains("Mailbox unavailable")) {
    markPermanent(jobId);
}
~~~

Nội dung message không phải protocol machine-readable ổn định. Các SMTP providers dùng wording khác nhau, tiếng Anh/locale khác nhau và nested exception formats khác nhau.

Nếu có reply code/enhanced status từ transport và provider contract, dùng dữ liệu có cấu trúc đó trong classifier. Nếu thiếu dữ liệu, giữ category `UNKNOWN` để xử lý an toàn.

## 16. SMTP 4xx, 5xx và giới hạn phân loại

SMTP reply code có thể hỗ trợ phân biệt:

- 4xx: lỗi tạm thời theo chuẩn giao thức, thường có thể thử lại.
- 5xx: lỗi vĩnh viễn theo mã phản hồi, thường không nên retry cùng payload/route ngay.

Nhưng cần thận trọng:

1. Một provider có thể dùng mã riêng cho quota, sender verification hoặc policy.
2. Một lệnh SMTP thất bại không nhất thiết xác định mọi recipient thất bại.
3. Exception có thể chứa nhiều mã từ RCPT/DATA.
4. Timeout không có reply code nghĩa là chưa chắc kết quả.
5. Một lỗi 5xx của credential/sender account có thể ảnh hưởng mọi jobs trên account.
6. Một lỗi permanent có thể cần sửa cấu hình rồi mới retry chứ không phải delete job.

Do đó:

~~~text
Spring Mail exception
  -> Jakarta Mail cause / nextException
  -> SMTP reply / enhanced status nếu có
  -> provider policy
  -> classify attempt
  -> decide retry / hold / permanent / unknown
~~~

Không áp một quy tắc duy nhất như “mọi MailSendException đều retry sau 30 giây”.

## 17. MailSendException và lỗi connection-level

Một batch có thể bị lỗi trước khi gửi message đầu tiên:

~~~text
Connect to SMTP host
  -> TLS handshake failure
  -> exception
  -> no message submitted
~~~

Hoặc:

~~~text
Connect OK
  -> AUTH rejected
  -> cannot send
~~~

Nhưng nếu lỗi xảy ra sau một số message, state khác:

~~~text
Connect OK
  -> A accepted
  -> B accepted
  -> socket closed before C
~~~

Các tình huống này có thể đều được biểu diễn thành mail-related exception ở application boundary.

Vì thế, chẩn đoán cần có:

- Loại transport error.
- Có cause liên quan TLS/AUTH/connection không?
- Failed-message entries có gì?
- Attempt/batch/job IDs tương ứng.
- Sender account/provider nào được chọn?
- Có SMTP acceptance confirmation đáng tin cho item nào?
- Có unknown outcome khi connection mất sau DATA không?

Đối với lỗi account-level như AUTH, không retry nóng toàn bộ outbox jobs bằng password cũ; cần sửa credential/refresh cache và giảm áp lực account.

## 18. Lỗi preparation khác lỗi send

Với `MimeMessagePreparator`:

~~~java
mailSender.send(mime -> {

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    mime, true, "UTF-8"
            );

    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(html, true);

    // Thêm attachment, inline asset, headers...
});
~~~

Nếu template/render/attachment setup thất bại, hệ thống có thể phát sinh `MailPreparationException` hoặc lỗi khác trước khi SMTP submission thực sự được thử.

Cần tách:

| Giai đoạn | Lỗi ví dụ | Hướng xử lý |
| --- | --- | --- |
| Business validation | Recipient không được phép | Từ chối tạo job |
| Template rendering | Thiếu biến, template lỗi | Sửa template/payload |
| MIME preparation | Attachment mất, invalid header | Fix content/storage |
| SMTP connect/auth | TLS/credential failure | Alert provider/account |
| SMTP RCPT | Một recipient bị reject | Phân loại per recipient |
| SMTP DATA | Message quá lớn, policy reject | Không retry cùng payload vô hạn |
| SMTP response lost | Unknown outcome | Reconcile/retry có xét trùng |
| Provider delivery | Bounce/complaint | Feedback workflow riêng |

`getFailedMessages()` chỉ sử dụng được khi có `MailSendException` tương ứng. Nó không nên bị dùng để che việc pipeline chưa tạo được MIME.

## 19. Một helper diagnostic có type rõ ràng

Có thể tạo một model trả kết quả chẩn đoán, không log thẳng email:

~~~java
public enum MailFailureScope {
    MESSAGE,
    BATCH,
    CONNECTION,
    UNKNOWN
}
~~~

~~~java
public record MessageFailureDiagnostic(
        UUID jobId,
        String exceptionType,
        MailFailureScope scope) {
}
~~~

Một boundary nhận `MailSendException` và mapping:

~~~java
public List<MessageFailureDiagnostic> diagnostics(
        MailSendException exception,
        Map<MimeMessage, UUID> jobsByMime) {

    List<MessageFailureDiagnostic> result =
            new ArrayList<>();

    for (Map.Entry<Object, Exception> entry
            : exception.getFailedMessages().entrySet()) {

        UUID jobId = null;

        if (entry.getKey()
                instanceof MimeMessage mime) {
            jobId = jobsByMime.get(mime);
        }

        Exception failure = entry.getValue();

        result.add(
                new MessageFailureDiagnostic(
                        jobId,
                        failure == null
                                ? "unknown"
                                : failure.getClass()
                                        .getSimpleName(),
                        jobId == null
                                ? MailFailureScope.UNKNOWN
                                : MailFailureScope.MESSAGE
                )
        );
    }

    return result;
}
~~~

Đây là ví dụ **chuyển đổi diagnostic**, không phải bộ phân loại outcome gửi email. Khi failed map rỗng, kết quả list rỗng nhưng exception tổng vẫn còn; caller phải ghi batch-level error riêng. Khi `jobId == null`, không được tự gán lỗi cho job đầu tiên.

### Đừng biến null jobId thành success

Nếu mapping không tìm được job, có thể:

- Dùng overload gửi không khớp.
- Key object khác object lúc build.
- Key là SimpleMailMessage.
- Sender/custom adapter thay đổi object identity.
- Context mapping bị mất qua async boundary.

Đó là lỗi correlation cần được log theo batch ID và điều tra, không phải lý do bỏ qua thất bại.

## 20. Một mail gateway nên trả outcome có cấu trúc

Một API dùng trong application có thể mô tả:

~~~java
public enum SubmissionOutcome {
    SUBMITTED,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE,
    UNKNOWN_OUTCOME
}
~~~

~~~java
public record MailSubmissionResult(
        UUID mailJobId,
        UUID attemptId,
        SubmissionOutcome outcome,
        String failureCategory) {
}
~~~

Tầng gateway sẽ:

1. Chọn approved sender account.
2. Compose message.
3. Gắn job/attempt correlation.
4. Gửi.
5. Khi `MailSendException`, đọc map và cause.
6. Phân loại kết quả trong phạm vi chắc chắn.
7. Trả kết quả/ghi attempt theo ID có thẩm quyền.

Nếu gửi một job mỗi call, mapping đơn giản hơn:

~~~java
public void submitOne(
        UUID jobId,
        MimeMessage mime) {

    try {
        mailSender.send(mime);
        resultStore.recordSubmitted(jobId);

    } catch (MailSendException ex) {
        Exception itemFailure =
                ex.getFailedMessages().get(mime);

        resultStore.recordSendFailure(
                jobId, ex, itemFailure
        );
    }
}
~~~

Đây là khung: `resultStore` phải phân loại và lưu transaction ngắn; `recordSendFailure` không nên tự mark permanent nếu thông tin không đủ. Nếu lỗi record DB xảy ra sau SMTP acceptance, job có thể được retry. Ví dụ cố ý không hứa exactly-once.

Khi có nhiều tenant/provider, sender instance phải được chọn theo route trước khi tạo `MimeMessage`. Không đổi username/password của shared sender giữa nhiều threads.

## 21. Batch lớn thường làm partial failure khó hiểu hơn

Một lời gọi:

~~~java
mailSender.send(
        mimeA, mimeB, mimeC, mimeD, mimeE
);
~~~

có thể giảm overhead một số trường hợp, nhưng tăng complexity:

- Job nào đã được relay accept?
- Job nào chưa attempt?
- Job nào reject tạm thời?
- Retry có gửi trùng không?
- Một message có nhiều recipients không?
- Có thể map key object về job không?
- Có thể audit từng attempt không?

Nếu email là transactional, ít message mỗi lần và yêu cầu tracking rõ, gửi từng job trong worker thường là thiết kế dễ bảo trì.

Nếu volume lớn và batch thực sự mang lại lợi ích đo được, cần xây result adapter cho đúng phiên bản sender đang dùng, có test partial failures và unknown outcomes.

**Không chọn batch chỉ vì method cho phép nhận varargs.** Hãy chọn theo nhu cầu throughput, latency, rate limiting và độ phức tạp retry.

## 22. Outbox pattern xử lý lỗi theo job

Một hệ thống cần bền vững thường lưu mail intent trong `mail_outbox` cùng transaction nghiệp vụ:

~~~text
Business transaction:
  UPDATE order
  INSERT mail_outbox
  COMMIT

Worker:
  claim one mail job
  compose MimeMessage
  JavaMailSender.send
  record outcome
  retry if policy allows
~~~

Một schema cơ bản:

~~~text
mail_outbox:
  id
  tenant_id
  purpose
  recipient_contact_id
  sender_profile_id
  status
  attempt_count
  next_attempt_at
  lease_token
  last_failure_category
  last_failure_scope
  last_failed_message_type
  created_at
  updated_at
~~~

Đối với một job/recipient, failure correlation thường gắn trực tiếp với `jobId`. Với batch, mapping `failedMessages` giúp record result đúng job.

Điều quan trọng: **transaction outbox và SMTP không commit nguyên tử**. Nếu `send` thành công nhưng worker crash trước khi update DB, job có thể được submit lần nữa khi lease hết hạn.

## 23. Crash window và unknown SMTP outcome

Một tình huống:

~~~text
Worker gửi MIME qua SMTP.
Server chấp nhận DATA.
Network đứt trước khi client đọc phản hồi.
JavaMailSender ném lỗi.
Worker có thể retry.
Recipient có thể nhận hai email.
~~~

Đây không phải lỗi có thể sửa bằng một lệnh:

~~~java
if (failed.containsKey(mime)) {
    retry(mime);
}
~~~

Bởi vì failed map cho biết transport **đã báo lỗi**, không chứng minh external relay **chưa nhận nội dung**.

Đối với email tài chính, OTP hoặc notification nhạy cảm, cần có phương án:

- Nội dung idempotent hoặc token version.
- Outbox attempt IDs.
- Duplicate-tolerant business semantics khi có thể.
- Reconciliation qua provider API nếu provider có correlation.
- Retry với chính sách phù hợp.
- Không hứa exact-once SMTP nếu contract không hỗ trợ.

`Message-ID` cố định hữu ích cho tracing, nhưng không có quy định mọi SMTP/receiving server phải dedupe theo header này.

## 24. Phân loại retry dựa trên bằng chứng

Một classifier có thể định nghĩa:

~~~java
public enum MailFailureCategory {
    TEMPORARY_TRANSPORT,
    PROVIDER_THROTTLED,
    AUTHENTICATION_FAILED,
    TLS_FAILURE,
    INVALID_RECIPIENT,
    INVALID_SENDER,
    MESSAGE_TOO_LARGE,
    CONTENT_REJECTED,
    ATTACHMENT_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    UNKNOWN
}
~~~

Bảng policy minh họa:

| Category | Hành động |
| --- | --- |
| Temporary transport trước submission | Retry với backoff |
| SMTP throttling rõ | Retry sau delay |
| Auth failure | Hold account/alert, refresh credential |
| TLS verification failure | Fix trust/endpoint, không tắt TLS |
| Invalid recipient permanent | Không retry y nguyên; suppression phù hợp |
| Invalid sender/domain | Fix sender verification |
| Message too large | Giảm attachment hoặc dùng link |
| Attachment storage temporarily down | Retry khi resource còn hợp lệ |
| Timeout sau DATA | Unknown outcome/reconcile |
| Không đủ thông tin | Unknown, không tự mark submitted |

Không đồng nhất exception class với policy: `MailSendException` chỉ là điểm bắt đầu. Cần xem cause/code/provider response và điều kiện nghiệp vụ.

## 25. Retry backoff và hạn mức

Lỗi tạm ở SMTP không nên tạo vòng lặp retry nóng:

~~~text
Attempt 1 -> immediate
Attempt 2 -> 30 seconds later
Attempt 3 -> 1 minute later
Attempt 4 -> 2 minutes later
Attempt 5 -> 4 minutes later
... bounded by max delay and age
~~~

Áp jitter để nhiều worker không retry đồng loạt.

Ngoài backoff:

- Đặt maximum attempts/age theo mail purpose.
- Không gửi OTP/password reset token đã hết hạn.
- Recheck unsubscribe/consent khi gửi marketing.
- Giới hạn concurrency theo SMTP account.
- Giới hạn quota provider và tenant.
- Không retry nguyên MIME nhiều recipients nếu có partial accept mà chưa xác định recipient outcomes.
- Không giữ attachment quá thời hạn sử dụng.
- Khi account bị lỗi AUTH, hold jobs thay vì spam provider.

Một map failed messages chính xác giúp chọn job nào cần xử lý nhưng **không thay thế retry policy và business authorization**.

## 26. Ghi log lỗi theo job, không lộ nội dung email

Một log tốt:

~~~text
mailJobId: mail-981
attemptId: attempt-2
batchId: batch-47
providerId: relay-a
senderProfileId: tx-tenant-42
failureScope: MESSAGE
exceptionType: SendFailedException
failureCategory: INVALID_RECIPIENT
outcome: PERMANENT_FAILURE
~~~

Không nên log:

~~~java
log.error(
        "Failed message={}",
        failedMimeMessage
);
~~~

hoặc serialize đối tượng message đầy đủ vì có thể lộ:

- Recipient và thông tin liên hệ.
- Subject chứa thông tin riêng tư.
- Nội dung HTML/plain text.
- Password reset/OTP token.
- Attachment filename hoặc content.
- Confidential customer data.

Có thể log masked recipient/contact ID theo chính sách. Nếu cần debug exception stack, lưu trong hệ thống được phân quyền và có retention phù hợp, tránh log credential hay MIME raw.

### Không dùng nội dung message làm metric label

Một metric có label `subject` hoặc `recipient` có thể tạo cardinality vô hạn và rò PII. Dùng `failureCategory`, `providerId`, `purpose` và nhóm account có kiểm soát.


## 27. Monitoring failed messages và phân loại lỗi

Các metrics hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_submit_attempt_total` | Số send attempts |
| `mail_send_exception_total` | Lượt gặp Spring Mail exception |
| `mail_failed_message_total` | Số failed-message entries được báo |
| `mail_send_batch_failure_total` | Batch có exception tổng |
| `mail_failure_category_total` | Lỗi theo classifier |
| `mail_unknown_outcome_total` | Attempt có kết quả không chắc |
| `mail_partial_recipient_failure_total` | Lỗi partial recipients được quan sát |
| `mail_job_retry_total` | Số job được lập lịch retry |
| `mail_job_permanent_failure_total` | Job không tiếp tục retry |
| `mail_outbox_oldest_pending_age_seconds` | Độ tuổi công việc chờ |
| `mail_provider_auth_failure_total` | Lỗi AUTH |
| `mail_provider_throttle_total` | Throttling |
| `mail_message_correlation_miss_total` | Key trong failed map không map được job |
| `mail_submit_duration_seconds` | Thời gian SMTP submission |

Một số metrics phản ánh **exception observation** chứ không phải tỷ lệ delivered. Không cộng số failed-message entries rồi gọi đó là “tổng email chưa tới người nhận”.

### Alert nên có

- `MailSendException` tăng sau deploy.
- SMTP AUTH/TLS failure lặp lại theo provider account.
- Map failed messages nhiều key nhưng correlation miss cao.
- Outbox retry backlog tăng và oldest age vượt SLA.
- Lỗi permanent recipient tăng đột biến.
- UNKNOWN_OUTCOME tăng sau mất mạng/timeout.
- Một provider chịu throttling kéo dài.
- Nhiều jobs một tenant bị ảnh hưởng hơn bình thường.

Không đưa recipient email, subject hoặc raw exception message làm metrics label. Khi cần tra cứu chi tiết, dùng job/attempt ID trong structured log có kiểm soát truy cập.

## 28. Trong multi-tenant, lỗi phải được quy đúng phạm vi

Một SaaS có thể gửi mail cho nhiều tenant qua những sender account khác nhau:

~~~text
tenant-a -> smtp-account-a
tenant-b -> smtp-account-b
tenant-c -> shared-platform-account
~~~

Lỗi AUTH của account A không nhất thiết ảnh hưởng account B; lỗi quota shared account có thể ảnh hưởng nhiều tenant sử dụng chung.

Khi đọc `MailSendException`, record:

- Mail job và tenant ID đáng tin.
- Provider/account route đã chọn.
- Sender domain/From identity được duyệt.
- Failure category.
- Attempt number.
- Unknown/partial outcome nếu có.
- Chính sách retry phù hợp provider/tenant/purpose.

**Không chọn retry destination dựa vào From trong MIME object chưa được authorize.** Tenant routing phải được quyết định từ job và policy, không từ subject hoặc recipient được đọc lại từ exception.

Nếu backup provider được dùng, cần verified domain, SPF/DKIM/DMARC, bounce routing, quota và policy tương thích. Không tự chuyển marketing mail sang security account vì một batch có vài failed entries.

## 29. Async gửi email: đừng để exception biến mất

Một method:

~~~java
@Async("mailExecutor")
public void sendInBackground(
        MimeMessage message) {

    mailSender.send(message);
}
~~~

chạy trong worker thread. Nếu lỗi `MailSendException` xảy ra, HTTP thread ban đầu không trực tiếp catch được như một synchronous call.

Cần:

- Worker bắt lỗi và đọc `getFailedMessages()`.
- Ghi attempt/outcome vào durable store.
- Nếu dùng `CompletableFuture`, propagate hoặc observe failed future.
- Nếu dùng `void @Async`, có exception handling phù hợp.
- Không chỉ log rồi quên job.
- Không phụ thuộc thread-local tenant context của request đã kết thúc.
- Không coi executor RAM là durable queue.

Một service submit kiểu CompletableFuture có thể:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> submit(
        MimeMessage message) {

    mailSender.send(message);

    return CompletableFuture.completedFuture(null);
}
~~~

Caller cần observe exception của future. Nếu chỉ gọi rồi bỏ future, lỗi có thể không dẫn đến retry nghiệp vụ. Với yêu cầu gửi bền vững, transactional outbox thường phù hợp hơn việc chỉ bọc `mailSender.send` bằng `@Async`.

## 30. API HTTP nên hứa trạng thái gì?

Nếu API chỉ enqueue outbox job:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"mailJobId":"mail-981","status":"PENDING"}
~~~

Nghĩa là yêu cầu gửi đã được tiếp nhận theo contract API, **không phải email delivered**.

Nếu endpoint gửi đồng bộ và `JavaMailSender.send` trả về không lỗi, cũng không nên khẳng định recipient đã mở thư. Provider có thể trả bounce sau.

Trong trường hợp batch partial failure, API có thể chọn:

- Không expose chi tiết SMTP cho public client; chỉ trả job IDs và status theo authorization.
- Theo dõi mỗi job trong một resource riêng.
- Trả một batch ID để client xem trạng thái.
- Không tiết lộ raw exception nội bộ, provider credential hoặc thông tin recipient thuộc tenant khác.

Map `getFailedMessages()` là diagnostic nội bộ, không nên serialize trực tiếp vào JSON HTTP response.

## 31. Đừng phân loại lỗi bằng toString() của message

Một số đoạn debug viết:

~~~java
Object failed = entry.getKey();

log.warn(
        "Failed message: {}",
        failed.toString()
);
~~~

Điều này có thể vô tình ghi ra recipient/subject/body hoặc metadata nhạy cảm. Cũng không nên tạo hash của toàn bộ body chỉ để mapping job khi đã có job ID.

Một chiến lược tốt hơn:

~~~text
Compose:
  jobId -> MimeMessage instance

Send:
  same MimeMessage instance(s)

Catch:
  getFailedMessages -> object identity lookup

Log:
  jobId, attemptId, provider, category
~~~

Nếu dùng message object có mutable fields, không nên thay content trong khi một thread khác đang gửi. Không dùng một `MimeMessage` dùng chung cho nhiều jobs.

## 32. Các giới hạn của logging exception raw

Ngay cả khi không in message, một stack trace hoặc exception text từ provider có thể chứa:

- SMTP command details.
- Recipient address.
- Provider host.
- Một phần raw response.
- Địa chỉ From hoặc subject.
- Thông tin server/account.

Vì vậy:

1. Log `exceptionType` và category vào metrics.
2. Log stack trace ở nơi có access control phù hợp khi cần chẩn đoán.
3. Tránh log credentials, OAuth token hoặc full MIME.
4. Mask email address nếu policy yêu cầu.
5. Đặt retention/rotation.
6. Giữ correlation ID/job ID để có thể đối chiếu mà không cần raw body.

**Không đọc failed map** làm giảm khả năng chẩn đoán; **đọc rồi dump toàn bộ object** lại gây rủi ro bảo mật. Cần trích thông tin có cấu trúc và vừa đủ.

## 33. Unit test đọc getFailedMessages()

Có thể dựng `MailSendException` giả chứa một map lỗi:

~~~java
@Test
void extractsFailedMimeMessage() throws Exception {

    MimeMessage failed =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    MessagingException cause =
            new MessagingException(
                    "Simulated SMTP failure"
            );

    Map<Object, Exception> failures =
            new LinkedHashMap<>();

    failures.put(failed, cause);

    MailSendException exception =
            new MailSendException(
                    "Batch failed",
                    null,
                    failures
            );

    assertEquals(
            1,
            exception.getFailedMessages().size()
    );

    assertSame(
            cause,
            exception.getFailedMessages().get(failed)
    );
}
~~~

Các import cơ bản:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailSendException;
~~~

Đây là unit test minh họa việc đọc map; không cần kết nối SMTP. Tạo fixture có hai failed messages và một message không nằm trong map để kiểm tra kết quả diagnostic và nhánh unknown.

### Test không đồng nghĩa kiểm tra delivery

Một synthetic `MailSendException` kiểm tra logic adapter của ứng dụng, không chứng minh SMTP provider thực sẽ trả map giống vậy trong mọi trường hợp.

## 34. Test liên kết thất bại với từng mail job

Một test nên chuẩn bị:

~~~text
job-A -> mime-A
job-B -> mime-B
job-C -> mime-C

Exception failed map:
  mime-B -> invalid recipient
  mime-C -> temporary transport
~~~

Các assertion:

- Diagnostic ghi job-B đúng failure type.
- Diagnostic ghi job-C đúng failure type.
- Không gán B's error cho A.
- A không bị **khẳng định delivered** chỉ vì vắng map.
- Nếu failed map có key lạ, ghi correlation miss.
- Nếu map rỗng, ghi global/batch-level failure.
- Nếu message key là SimpleMailMessage, không cast sang MimeMessage.

Một test có thể dùng `IdentityHashMap` và `assertSame` để xác minh boundary liên kết đúng object identity.

### Kiểm thử map empty là rất quan trọng

~~~java
@Test
void emptyFailedMapIsNotSuccess() {

    MailSendException exception =
            new MailSendException(
                    "Transport failed"
            );

    FailureAnalysis analysis =
            analyzer.analyze(
                    batchContext,
                    exception
            );

    assertNotEquals(
            SubmissionOutcome.SUBMITTED,
            analysis.batchOutcome()
    );
}
~~~

`FailureAnalysis`, `analyzer` và `batchContext` là test seam do dự án định nghĩa; mục đích là tránh diễn giải map rỗng thành submission success.

## 35. Kiểm thử SimpleMailMessage và MimeMessage

Nếu ứng dụng có hai overload gửi, cần fixture riêng:

| Đường gửi | Test |
| --- | --- |
| `send(SimpleMailMessage)` | Key là simple message theo implementation/contract |
| `send(SimpleMailMessage[])` | Mapping nhiều simple objects |
| `send(MimeMessage)` | MIME object key và job ID |
| `send(MimeMessage[])` | Partial batch diagnostics |
| `send(MimeMessagePreparator)` | Lỗi preparation khác send failure |
| `send(MimeMessagePreparator[])` | Giai đoạn prepare từng MIME và lỗi SMTP |
| Custom mail sender | Key semantics được xác nhận theo adapter |

Một test thiếu tương quan key có thể tạo code chạy được cho MIME nhưng ném `ClassCastException` khi chuyển sang simple messages ở production.

Nên test sender integration boundary riêng, không để business service chịu trách nhiệm tìm hiểu loại key lạ.

## 36. Integration test với SMTP test server

Dùng GreenMail, Mailpit hoặc SMTP server cô lập có khả năng giả lập lỗi phù hợp:

~~~text
Spring Mail Gateway
    |
    v
JavaMailSender
    |
    v
Isolated SMTP Test Server
    |
    v
Capture / reject / disconnect scenarios
~~~

Các trường hợp:

1. Gửi một MIME message hợp lệ.
2. Gửi batch nhiều message.
3. Server từ chối recipient cụ thể khi test server hỗ trợ.
4. Server tắt connection trước send.
5. Server ngắt kết nối giữa transaction.
6. Provider response timeout giả.
7. Lỗi account-level AUTH/TLS giả trong fixture tương thích.
8. Phân loại failed map/cause.
9. Ghi job/attempt ID tương ứng.
10. Retry và kiểm tra không tự mark delivered.

Không phải SMTP test server nào cũng hỗ trợ mô phỏng partial recipients, response-after-DATA loss hoặc những code 4xx/5xx cụ thể. Khi thiếu capability, có thể dùng fake sender ở unit/component test để tạo `MailSendException` có kiểm soát, kết hợp một số integration tests với SMTP server để kiểm tra transport thực.

**Không dùng SMTP production trong automated tests**, không dựa vào “email mới nhất” trong mailbox dùng chung.

## 37. Test unknown outcome và duplicate window

Một scenario:

~~~text
Attempt 1:
  fake sender ghi nhận SMTP acceptance
  nhưng mô phỏng mất reply / lỗi trước DB status update

Outbox:
  job vẫn chưa SUBMITTED

Attempt 2:
  worker retry
  fake sender ghi nhận submission thứ hai
~~~

Test này chứng minh outbox không thể tự tạo exactly-once SMTP. Phải bảo đảm:

- Không đánh dấu job thành `DELIVERED` vô căn cứ.
- Có attempt log.
- Retry policy hiểu possibility of duplicate.
- Job không mất nếu worker crash.
- Khi dùng provider idempotency token, chỉ dựa vào documented provider contract.
- Các email chứa token có thời hạn được revalidate trước retry.

Nên tách **recorded failure** với **known no-submission**; chúng không phải đồng nghĩa.

## 38. Ma trận tình huống cần kiểm thử

| Tình huống | Mong đợi |
| --- | --- |
| Một mail gửi thành công | Ghi SUBMITTED theo contract |
| Một mail `MailSendException` có failed map | Ghi job + message cause |
| Failed map rỗng | Ghi batch/global failure, không coi success |
| Failed map chứa key không nhận diện | Ghi correlation miss |
| Key `SimpleMailMessage` | Không cast sai |
| Key `MimeMessage` | Map đúng MIME job |
| Hai messages cùng subject | Không gán chéo job |
| Một message nhiều recipients | Xử lý partial outcome có policy |
| Exception cause có nested chain | Không bỏ sót diagnostic |
| AUTH failure | Alert account, không retry nóng |
| TLS failure | Fix config/trust, không tắt verify |
| Hard invalid recipient | Permanent/suppression policy |
| SMTP 4xx temporary | Backoff/retry nếu an toàn |
| SMTP timeout sau DATA | UNKNOWN_OUTCOME |
| Send succeeded rồi DB update fail | Chấp nhận nguy cơ retry/duplicate |
| Bulk batch partial failure | Không mark all failed không điều kiện |
| Template preparation error | Không coi như SMTP reject |
| Attachment không đọc được | Lỗi storage/compose riêng |
| Async task failure | Durable job được cập nhật |
| Provider outage | Backlog alert và rate limit |
| Tenant khác cùng provider | Không lộ message/recipient của tenant |
| Log exception | Không leak PII/credential |

Không cần chạy tất cả case qua network thật. Dùng unit/fake để tạo edge cases có cấu trúc và SMTP integration test để kiểm chứng những hành vi transport quan trọng.

## 39. Những lỗi triển khai phổ biến

### 39.1. Catch MailException rồi bỏ qua failed map

Bỏ thông tin message-level, khó biết job nào cần xử lý.

### 39.2. Retry toàn bộ batch khi một item lỗi

Có thể gửi trùng những message đã accepted.

### 39.3. Coi mọi item vắng map là delivered

Map không phải delivery ledger; connection/global errors có thể tạo outcome không xác định.

### 39.4. Coi map rỗng nghĩa không có lỗi

Sai: exception vẫn tồn tại, chỉ không có per-message entries.

### 39.5. Chỉ dùng getMessageExceptions rồi suy index

Mảng exception không phải mapping tin cậy tới batch index.

### 39.6. Cast mọi key sang MimeMessage

Đường SimpleMailMessage có thể dùng key khác.

### 39.7. Map failed message bằng subject

Nhiều message trùng subject, dễ gán sai job.

### 39.8. Map bằng recipient duy nhất

Một recipient có thể có nhiều jobs; một MIME có thể nhiều recipients.

### 39.9. Chỉ đọc getCause mà bỏ qua nextException

Jakarta Mail có thêm nested errors qua `getNextException()`.

### 39.10. Parse exception text để quyết định permanent

Message string không phải API machine-readable ổn định.

### 39.11. Gộp connection failure và invalid recipient

Một lỗi ảnh hưởng account, lỗi khác ảnh hưởng một mail/recipient.

### 39.12. Retry hard 5xx hoặc message too large vô hạn

Tạo queue chờ không hồi phục nếu không sửa dữ liệu/cấu hình.

### 39.13. Coi 4xx luôn an toàn retry tức thì

Cần backoff, quota và xem outcome/SMTP stage.

### 39.14. Bỏ qua partial recipient acceptance

Có thể resend cho người đã được provider accept.

### 39.15. Coi SMTP accepted là delivered

Bounce/deferred có thể xuất hiện về sau.

### 39.16. Coi Message-ID cố định ngăn mọi duplicate

SMTP không có universal dedupe theo Message-ID.

### 39.17. Log cả MimeMessage khi thất bại

Có thể lộ recipient, body, token và attachment metadata.

### 39.18. Nuốt exception mà không ghi outbox state

Job có thể bị coi đã hoàn tất hoặc mất khả năng retry.

### 39.19. Dùng @Async không theo dõi failed future

Lỗi ở background thread không tự trở lại request thread.

### 39.20. Giữ một shared JavaMailSender mutable cho nhiều tenant

Đổi username/password giữa threads có thể gửi sai account.

### 39.21. Không có correlation job/attempt

Failed map có key nhưng application không biết job nào.

### 39.22. Không kiểm thử map rỗng và unknown key

Code chỉ chạy đúng ở trường hợp dễ, sai ở failure path.

## 40. Câu hỏi thực hành

**Câu 1.** Tại sao `catch (MailException)` rồi log chung chưa đủ khi gửi batch?

Vì có thể bỏ qua per-message failures trong `MailSendException#getFailedMessages()`.

**Câu 2.** `getFailedMessages()` trả kiểu dữ liệu gì?

`Map<Object, Exception>`, key là message object, value là exception liên quan.

**Câu 3.** Có thể cast mọi key thành `MimeMessage` không?

Không. Với simple messages hoặc sender adapter khác, key có thể có type khác.

**Câu 4.** `getMessageExceptions()` có giữ mapping job ID không?

Không tự có. Nó cung cấp mảng exception, thiếu object-key context để map trực tiếp.

**Câu 5.** Failed map rỗng khi MailSendException được ném có nghĩa mọi mail thành công?

Không. Chỉ có nghĩa không có per-message entries trong map.

**Câu 6.** Một message vắng khỏi failed map có chắc được delivered?

Không. Map không phải delivery ledger, và SMTP accepted cũng chưa phải inbox delivered.

**Câu 7.** Tại sao dùng subject làm correlation key sai?

Subject có thể trùng và không phải identity ổn định của job.

**Câu 8.** Với batch MIME, có thể map bằng gì?

Giữ job ID cùng MIME object trước send, dùng object identity khi API giữ đúng original objects.

**Câu 9.** `SendFailedException` cho biết gì về recipient?

Có thể có các nhóm invalid, valid sent và valid unsent addresses, tùy transport.

**Câu 10.** Một recipient đã được accept, người khác bị reject. Retry nguyên MIME có nguy cơ gì?

Người đã được accept có thể nhận thư trùng.

**Câu 11.** Ngoài Java cause chain, Jakarta Mail còn cung cấp API nested nào?

`MessagingException#getNextException()`.

**Câu 12.** SMTP timeout sau DATA có chắc relay chưa nhận?

Không. Có thể là unknown outcome.

**Câu 13.** Lỗi template khi prepare MIME có chắc là MailSendException không?

Không. Có thể là MailPreparationException hoặc lỗi khác trước SMTP.

**Câu 14.** AUTH failure có nên retry tất cả jobs ngay lập tức không?

Không. Nên hold/backoff theo account, kiểm tra credential và alert.

**Câu 15.** Outbox unique idempotency key bảo đảm mỗi email chỉ gửi một lần?

Không. Nó chống duplicate enqueue; crash sau SMTP acceptance vẫn có thể tạo resend.

**Câu 16.** `@Async void` có làm request thread bắt được MailSendException không?

Không mặc định. Phải xử lý lỗi trong worker hoặc theo dõi future/handler tương ứng.

**Câu 17.** Có nên log `MimeMessage.toString()` khi lỗi không?

Không nên. Có thể lộ PII/content; ghi job ID, type và failure category.

**Câu 18.** Một batch partial failure có thể được xử lý đơn giản hơn thế nào?

Có thể gửi một message per job/call để dễ correlation và retry độc lập, nếu throughput cho phép.

## 41. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Mail jobs + job IDs"] --> B["Compose Simple/MIME messages"]
    B --> C["Giữ object -> job mapping"]
    C --> D["JavaMailSender.send"]
    D --> E{"Có exception?"}
    E -->|"Không"| F["SUBMITTED theo transport contract"]
    E -->|"Có"| G{"MailSendException?"}
    G -->|"Không"| H["Phân loại preparation/auth/other"]
    G -->|"Có"| I["getFailedMessages()"]
    I --> J{"Map có entry?"}
    J -->|"Có"| K["Map message key tới job"]
    J -->|"Rỗng"| L["Global/unknown failure"]
    K --> M["Inspect per-message exception"]
    M --> N["Jakarta cause/nextException"]
    N --> O["Classify transient/permanent/unknown"]
    O --> P["Retry/hold/fail + attempt log"]
    H --> P
    L --> P
    P --> Q["Observability + provider feedback"]
~~~

Những nguyên tắc quan trọng:

1. **`MailSendException` có thể chứa lỗi riêng theo message**; đừng chỉ log exception tổng.
2. **`getFailedMessages()` trả `Map<Object, Exception>`**, cần xử lý key type phù hợp.
3. **`getMessageExceptions()` có nguyên nhân nhưng thiếu object-key correlation** so với map.
4. **Không cast key mù quáng**; SimpleMailMessage và MimeMessage có đường gửi khác nhau.
5. **Gắn job ID với original message object trước send**, không dò bằng subject hoặc To.
6. **Map rỗng không có nghĩa không lỗi**, và item vắng map không tự được xác nhận delivered.
7. **Một MIME có nhiều recipients có thể bị partial acceptance**; cần xem recipient-level transport details.
8. **Jakarta Mail có cause và nextException chain**, hữu ích để phân loại nhưng không parse text tùy tiện.
9. **Phân biệt preparation, authentication, SMTP send và delivery feedback**, không gộp mọi lỗi thành một.
10. **Timeout sau SMTP DATA có thể là unknown outcome**, retry có nguy cơ gửi trùng.
11. **Outbox hỗ trợ durable intent và retry**, nhưng không bảo đảm exactly-once SMTP.
12. **Retry theo failure category, purpose, backoff và deadline**, không retry mọi `MailSendException` vô hạn.
13. **Log job/attempt/provider/category**, không dump message hoặc credential.
14. **Metrics/alert phải thể hiện failures, correlation miss, backlog và unknown outcomes**, không chỉ một số “send failed”.
15. **Kiểm thử map populated, map empty, unknown key, Simple/MIME, partial recipients và crash windows**.
16. **Một job/recipient, một send call** thường dễ quản lý hơn batch phức tạp khi yêu cầu chính xác cao.

Trong Spring Framework Mail, xử lý `MailSendException` đúng không dừng ở câu lệnh `catch`. Cần **đọc failed messages**, hiểu phạm vi của từng lỗi, liên kết được với mail job thật, đồng thời giữ rõ ranh giới giữa **lỗi quan sát được**, **submission đã được xác nhận** và **delivery chưa chắc chắn**. Khi kết hợp diagnostic map với idempotency, retry/outbox, logging có cấu trúc và kiểm thử failure paths, hệ thống có thể phục hồi sau lỗi SMTP mà giảm tối đa nguy cơ mất email hoặc gửi trùng.


