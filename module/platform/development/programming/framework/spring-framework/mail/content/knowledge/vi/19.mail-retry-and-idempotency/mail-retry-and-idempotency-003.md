# Backoff, jitter và số lần thử tối đa trong Spring Framework Mail

Gửi email qua `JavaMailSender` là một thao tác mạng, vì vậy một lần gửi có thể thất bại khi SMTP server đang bận, kết nối bị gián đoạn hoặc provider tạm thời giới hạn lưu lượng. Nhưng không phải lỗi nào cũng được giải quyết bằng cách gửi lại. Nếu retry liên tục mà không có khoảng chờ và giới hạn, ứng dụng có thể gây ra **retry storm**, tiêu tốn worker, làm quá tải SMTP relay và thậm chí gửi trùng email.

Một retry policy đáng tin cậy cần trả lời ba câu hỏi: **lỗi nào nên thử lại**, **chờ bao lâu trước lần kế tiếp**, và **khi nào phải dừng**. Backoff quyết định khoảng chờ, jitter ngẫu nhiên hóa thời điểm thử lại, còn `maxAttempts` đặt giới hạn tổng số lần gửi. Với email quan trọng, cần thêm deadline nghiệp vụ, lưu trạng thái retry bền vững và cơ chế xử lý kết quả SMTP không rõ ràng.

Trong Spring Framework Mail, `JavaMailSender` phụ trách thực hiện một lần gửi. Logic retry thường nên đặt ở application/worker thay vì trộn vào cách dựng `MimeMessage`. Spring Retry có thể hỗ trợ các lần thử lại ngắn trong process; transactional outbox phù hợp khi yêu cầu gửi phải tồn tại sau restart.

## 1. Vì sao retry ngay lập tức thường có hại?

Giả sử SMTP provider báo đang bận. Nếu 1.000 task gửi mail cùng gặp lỗi rồi retry ngay, chúng có thể tiếp tục cùng kết nối vào server vừa quá tải.

~~~text
1.000 lần gửi email
        |
        v
SMTP tạm từ chối
        |
        v
1.000 lần retry ngay lập tức
        |
        v
SMTP lại từ chối
        |
        v
Lặp lại, tạo tải lớn hơn
~~~

Khi mọi worker dùng lịch chờ giống nhau, chúng có thể tạo đỉnh tải vào cùng thời điểm. Đây là tình huống thường được gọi là *thundering herd* hoặc *retry storm*.

Một chính sách tốt cần:

- Phân loại lỗi tạm thời và lỗi vĩnh viễn.
- Giãn thời gian retry theo số lần thất bại.
- Thêm jitter để các worker không cùng thử vào một mốc.
- Đặt số lần thử tối đa và deadline.
- Tôn trọng quota/concurrency của provider.
- Không giữ database transaction hoặc HTTP request thread trong lúc chờ dài.
- Ghi nhận attempts, next attempt time và kết quả để dễ vận hành.

Retry tăng khả năng vượt qua lỗi **có thể phục hồi**, không phải cơ chế chữa mọi lỗi.

## 2. Phân biệt attempt, retry và maxAttempts

Một lỗi thiết kế phổ biến là nhầm số lần gửi tổng cộng với số lần gửi lại.

- **Attempt**: một lần thực sự gọi hệ thống gửi mail.
- **Initial attempt**: lần gửi đầu tiên.
- **Retry**: một attempt bổ sung sau lần trước thất bại.
- **maxAttempts**: trong bài này là tổng số attempt cho phép, **bao gồm lần đầu**.

Ví dụ `maxAttempts = 5`:

| Lần thực hiện | Loại lần thử | Attempts đã dùng |
| --- | --- | ---: |
| 1 | Gửi lần đầu | 1 |
| 2 | Retry số 1 | 2 |
| 3 | Retry số 2 | 3 |
| 4 | Retry số 3 | 4 |
| 5 | Retry số 4 | 5 |
| 6 | Không được phép | Vượt giới hạn |

Như vậy `maxAttempts = 5` tương ứng **một lần đầu và tối đa bốn lần retry**.

Một số thư viện hoặc ứng dụng có thể dùng trường `maxRetries` để đếm riêng số lần gửi bổ sung. Nếu chọn quy ước này, phải đặt tên rõ. Không để một phần code hiểu `5` là năm lần gửi, trong khi phần khác hiểu là năm lần gửi lại.

### Đếm attempt ở thời điểm nào?

Nếu worker đọc record từ outbox rồi cố gọi SMTP, nên thống nhất:

1. Claim record.
2. Khi thực sự bắt đầu một lần gửi, ghi nhận attempt tương ứng.
3. Gửi qua adapter.
4. Cập nhật SUBMITTED hoặc RETRY_WAIT/FAILED.

Nếu executor từ chối một task trước khi worker gửi, cần quyết định có tính đó là attempt gửi hay chỉ là **dispatch attempt**. Không nên cộng số lần thử tại nhiều nơi cho cùng một lần thực thi.

## 3. Khi nào nên retry?

Không nên bắt mọi `MailException` rồi gửi lại. Hãy phân loại lỗi theo nguyên nhân và, nếu có thể, giai đoạn của SMTP conversation.

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| Tạm thời (TRANSIENT) | SMTP server bận, network gián đoạn, lỗi timeout trước submission, throttling tạm thời | Retry có backoff và jitter |
| Vĩnh viễn (PERMANENT) | Recipient sai, MIME vượt giới hạn, loại file bị chặn | Không retry nguyên message |
| Cấu hình (CONFIGURATION) | Sai credential, TLS/certificate, host không hợp lệ | Cảnh báo/sửa cấu hình, không lặp nhanh |
| Không rõ kết quả (AMBIGUOUS) | Timeout sau khi DATA đã được gửi và server có thể đã nhận | Cần chính sách đối soát/idempotency trước retry |
| Delivery failure sau submission | Bounce do mailbox hoặc policy ở chặng sau | Xử lý event/suppression riêng |

### SMTP 4xx và 5xx

Phản hồi SMTP bắt đầu bằng số `4` thường biểu thị lỗi tạm thời; số `5` thường là lỗi vĩnh viễn. Ví dụ:

- `421`: SMTP service không sẵn sàng hoặc đóng kết nối; thường mang tính tạm thời.
- `450`, `451`, `452`: nhiều trường hợp mailbox, processing hoặc resource tạm thời chưa đáp ứng.
- `550`: thường là mailbox không tồn tại hoặc yêu cầu bị từ chối theo policy.
- `552`: có thể liên quan hạn mức/dung lượng; cần xem nội dung và chính sách provider.

Đây là gợi ý phân loại, không phải bảng ánh xạ tuyệt đối. Enhanced status code, thông điệp của provider, giai đoạn SMTP và policy riêng có thể thay đổi cách xử lý. Retry lại cùng một message quá lớn thường không thể giúp vượt giới hạn size.

### Lấy thông tin lỗi từ Spring Mail

`JavaMailSender` có thể ném những subclass của `MailException`. `MailSendException` có thể chứa các nguyên nhân từ Jakarta Mail/SMTP transport. Adapter nên giữ exception gốc làm cause, trích xuất mã phản hồi khi có và chuyển sang lỗi ứng dụng mang ý nghĩa:

~~~java
public enum MailFailureCategory {
    TRANSIENT,
    PERMANENT,
    CONFIGURATION,
    AMBIGUOUS
}
~~~

Lỗi không xác định phải có policy riêng. Không nên coi mọi timeout là chưa gửi. Cũng không nên chỉ dùng so khớp một đoạn chuỗi error message tự do để phân loại, nếu API provider cung cấp response code/exception type chính thức.

## 4. Backoff cố định

Backoff cố định dùng một khoảng chờ không đổi:

~~~text
Attempt 1: gửi ngay
Attempt 2: chờ 10 giây
Attempt 3: chờ 10 giây
Attempt 4: chờ 10 giây
Attempt 5: chờ 10 giây
~~~

Ưu điểm: đơn giản, dễ dự đoán và phù hợp một số lỗi ngắn hạn. Nhược điểm: nhiều request gặp lỗi cùng lúc có thể tiếp tục retry đồng loạt, và số lần thử không thưa dần khi provider gặp outage kéo dài.

Có thể dùng backoff cố định cho retry nội bộ rất ngắn hoặc workload ít. Với số lượng mail lớn, exponential backoff kết hợp jitter thường phù hợp hơn.

## 5. Exponential backoff

Exponential backoff tăng khoảng chờ theo số lần thất bại:

~~~text
unclampedDelay(k) = initialDelay * multiplier^(k - 1)

cappedDelay(k) = min(maxDelay, unclampedDelay(k))
~~~

Trong đó:

- `k` là thứ tự retry sắp diễn ra, bắt đầu từ 1.
- `initialDelay` là khoảng chờ trước retry thứ nhất.
- `multiplier` là hệ số tăng, ví dụ 2.
- `maxDelay` là giới hạn trần của mỗi khoảng chờ.

Ví dụ: `initialDelay = 2 giây`, `multiplier = 2`, `maxDelay = 30 giây`.

| Attempt | Loại | Delay trước lần thử |
| --- | --- | ---: |
| 1 | Gửi ban đầu | 0 |
| 2 | Retry 1 | 2 giây |
| 3 | Retry 2 | 4 giây |
| 4 | Retry 3 | 8 giây |
| 5 | Retry 4 | 16 giây |
| 6 | Retry 5 | 30 giây |
| 7 | Retry 6 | 30 giây |

Từ retry 5 trở đi, delay đã chạm cap 30 giây. Bảng trên giả sử tất cả attempts đều được phép; trong thực tế, nếu `maxAttempts = 5` thì các attempt 6 và 7 không được thực hiện.

### Vì sao cần maxDelay?

Nếu không có cap, phép lũy thừa tiếp tục tăng nhanh. Sau nhiều lần thất bại, delay có thể dài đến mức email không còn ý nghĩa, hoặc phép tính số nguyên bị overflow.

`maxDelay` giới hạn thời gian chờ theo thuật toán. Nó không phải giấy phép bỏ qua thời gian chờ dài hơn do provider yêu cầu; nếu provider yêu cầu chờ một giờ, ứng dụng không nên cố thử sớm hơn chỉ vì cap nội bộ là hai phút.

## 6. Jitter ngăn nhiều worker retry cùng lúc

Exponential backoff đơn thuần có thể vẫn làm các request đồng bộ.

~~~text
Không jitter:
  10:00:00 - 500 tác vụ gặp lỗi
  10:00:02 - 500 tác vụ retry cùng lúc
  10:00:06 - 500 tác vụ retry cùng lúc
  10:00:14 - 500 tác vụ retry cùng lúc

Có jitter:
  10:00:00 - 500 tác vụ gặp lỗi
  10:00:00–10:00:02 - các retry được phân tán
  Những vòng sau tiếp tục phân tán thời điểm gửi
~~~

Jitter là phần ngẫu nhiên thêm vào delay nhằm:

- Giảm đỉnh kết nối SMTP sau một outage.
- Làm mềm tải lên provider.
- Tránh các instance ứng dụng có cùng lịch retry.
- Giúp rate limiter và worker pool điều phối thuận lợi hơn.

Jitter không thay thế rate limiter. Nếu provider chỉ chấp nhận một số email mỗi giây, hệ thống vẫn cần điều tiết tổng throughput.

## 7. Full jitter, equal jitter và decorrelated jitter

Giả sử `cap` là delay exponential sau khi giới hạn bởi `maxDelay`.

### Full jitter

~~~text
delay = random(0, cap)
~~~

Mỗi retry chọn một giá trị ngẫu nhiên từ 0 đến cap. Ưu điểm: phân tán mạnh; nhược điểm: có thể chọn thời gian rất gần 0. Nếu provider đang quá tải, nên kết hợp floor delay hoặc giới hạn tốc độ để tránh retry nóng.

### Equal jitter

~~~text
delay = cap / 2 + random(0, cap / 2)
~~~

Giữ lại ít nhất một nửa cap, còn lại là phần ngẫu nhiên. Nếu cap là 8 giây, delay xấp xỉ 4–8 giây. Chiến lược này hạn chế các retry quá sớm nhưng vẫn phân tán các tác vụ.

### Decorrelated jitter

Một biến thể phổ biến:

~~~text
delay = min(maxDelay, random(baseDelay, previousDelay * 3))
~~~

Delay mới phụ thuộc vào delay của lần trước thay vì bám sát một chuỗi lũy thừa cố định. Cần lưu `previousDelay` theo từng email nếu muốn tái lập lịch trong outbox.

### So sánh

| Chiến lược | Đặc điểm | Lưu ý |
| --- | --- | --- |
| Không jitter | Delay đúng bằng cap | Đơn giản nhưng dễ đồng bộ |
| Full jitter | Ngẫu nhiên từ 0 tới cap | Phân tán mạnh, có thể retry rất sớm |
| Equal jitter | Ngẫu nhiên từ cap/2 tới cap | Ít retry quá sớm hơn |
| Decorrelated jitter | Dựa vào delay trước đó | Cần trạng thái bổ sung |

Không có chiến lược tốt nhất cho mọi provider. Khi chưa có yêu cầu riêng, bounded exponential backoff với equal/full jitter và deadline rõ ràng là điểm khởi đầu hợp lý để kiểm thử.

## 8. MaxAttempts không thay thế deadline

Một email có thể hết giá trị dù chưa thử đủ số lần. Ví dụ:

- OTP hết hạn sau vài phút.
- Reset password token đã bị thu hồi.
- Một email mời tham dự sự kiện không còn giá trị sau giờ bắt đầu.
- Newsletter không nên gửi lại khi người dùng đã unsubscribe.

Retry phải xét cả số lần thử và thời hạn nghiệp vụ:

~~~text
Có được retry?
  lỗi thuộc loại có thể retry
  AND attempts < maxAttempts
  AND now < expiresAt
  AND nội dung vẫn hợp lệ theo nghiệp vụ
  AND không vi phạm cooldown/provider policy
~~~

Nếu retry tiếp theo dự kiến sau `expiresAt`, nên dừng thay vì gửi một email đã quá hạn.

### Các loại giới hạn

| Giới hạn | Mục đích |
| --- | --- |
| `maxAttempts` | Tránh gọi SMTP vô hạn |
| `maxDelay` | Tránh delay lũy thừa quá lớn |
| `maxAge`/`expiresAt` | Dừng khi email không còn ý nghĩa |
| `rateLimit` | Giới hạn tổng tốc độ gửi |
| `maxConcurrentSends` | Giới hạn kết nối/tác vụ đồng thời |
| `maxQueueAge` | Ngăn email tồn đọng vượt SLA |

Không gộp những khái niệm này thành một thông số duy nhất.

## 9. Mô hình retry policy bằng Java

Có thể giữ retry policy độc lập với Spring Mail để dễ test.

~~~java
import java.time.Duration;

public record MailRetrySettings(
    int maxAttempts,
    Duration initialDelay,
    Duration maxDelay,
    Duration maxAge
) {
    public MailRetrySettings {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive");
        }
        if (initialDelay.isZero()
                || initialDelay.isNegative()
                || maxDelay.compareTo(initialDelay) < 0
                || maxAge.isNegative()
                || maxAge.isZero()) {
            throw new IllegalArgumentException(
                "Invalid retry durations");
        }
    }
}
~~~

Các giá trị là cấu hình nghiệp vụ, không phải thông số mặc định của Spring Framework Mail.

Một outcome có thể được chuẩn hóa:

~~~java
public record RetryDecision(
    boolean retry,
    Instant nextAttemptAt,
    String reason
) {}
~~~

Bước phân loại lỗi thuộc adapter/provider integration; bước tính delay thuộc retry policy; bước lưu `nextAttemptAt` thuộc worker/outbox orchestration. Tách trách nhiệm như vậy giúp sửa một phần mà không ảnh hưởng những phần còn lại.

## 10. Cài đặt exponential backoff với equal jitter

Ví dụ Java 17+, dùng `RandomGenerator` để có thể truyền nguồn ngẫu nhiên cố định khi test.

~~~java
package example.mail.retry;

import java.time.Duration;
import java.util.random.RandomGenerator;

public final class MailBackoffPolicy {

    private final long initialMillis;
    private final long maxMillis;

    public MailBackoffPolicy(Duration initial, Duration max) {
        if (initial.isZero() || initial.isNegative()
                || max.isZero() || max.isNegative()) {
            throw new IllegalArgumentException(
                "Delays must be positive");
        }

        this.initialMillis = initial.toMillis();
        this.maxMillis = max.toMillis();

        if (initialMillis <= 0
                || maxMillis < initialMillis
                || maxMillis == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Invalid delay range");
        }
    }

    /**
     * failedAttempt=1: vừa thất bại lần gửi đầu.
     * failedAttempt=2: vừa thất bại lần retry đầu.
     */
    public Duration delayAfterFailure(
            int failedAttempt,
            RandomGenerator random) {

        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                "failedAttempt must be >= 1");
        }

        long cap = initialMillis;

        // Nhân đôi với cap, tránh overflow.
        for (int i = 1; i < failedAttempt; i++) {
            if (cap >= maxMillis / 2) {
                cap = maxMillis;
            } else {
                cap = Math.min(maxMillis, cap * 2);
            }
        }

        long minimum = cap / 2;
        long additionalRange = cap - minimum;

        long jitter = random.nextLong(additionalRange + 1);
        return Duration.ofMillis(minimum + jitter);
    }
}
~~~

Ví dụ dùng:

~~~java
MailBackoffPolicy policy = new MailBackoffPolicy(
    Duration.ofSeconds(2),
    Duration.ofMinutes(2)
);

Duration delay = policy.delayAfterFailure(
    3,
    ThreadLocalRandom.current()
);
~~~

Với `failedAttempt = 3`, cap là 8 giây và equal jitter tạo delay trong khoảng khoảng 4–8 giây. `failedAttempt` biểu diễn số lần đã gửi và đã thất bại; không phải số lần retry còn lại.

### Lưu ý về phép tính

- Dùng `long` và giới hạn cap để tránh overflow.
- Không dùng `Math.pow` trên số lần thử không giới hạn rồi ép thẳng sang `long`.
- Giữ initial và max delay trong phạm vi thực tế, không cấu hình giá trị sát giới hạn kiểu số.
- Jitter nên được tính riêng cho từng record/lần gửi.
- Với test, inject RNG/`Clock` để kết quả có thể tái lập.
- Hàm chỉ tính delay; nó **không** tự biết lỗi có retry được hay không.

## 11. Quyết định retry theo lỗi, attempts và deadline

Ví dụ policy độc lập:

~~~java
public RetryDecision decide(
        MailFailureCategory failure,
        int attemptsSoFar,
        int maxAttempts,
        Instant now,
        Instant expiresAt,
        Duration delay) {

    if (failure != MailFailureCategory.TRANSIENT) {
        return new RetryDecision(
            false, null, "Failure is not safely retryable");
    }

    if (attemptsSoFar >= maxAttempts) {
        return new RetryDecision(
            false, null, "Max attempts reached");
    }

    if (!now.isBefore(expiresAt)) {
        return new RetryDecision(
            false, null, "Business deadline expired");
    }

    Instant nextAttemptAt = now.plus(delay);

    if (!nextAttemptAt.isBefore(expiresAt)) {
        return new RetryDecision(
            false, null, "Next retry is beyond deadline");
    }

    return new RetryDecision(
        true, nextAttemptAt, "Transient failure");
}
~~~

Trong ví dụ, lỗi `AMBIGUOUS` không tự động retry vì có rủi ro gửi trùng. Đây là một **lựa chọn policy thận trọng**; ứng dụng khác có thể quyết định khác khi có provider idempotency key hoặc nghiệp vụ cho phép duplicate.

Trong production, thêm xử lý `expiresAt` tùy chọn, provider cooldown, lỗi cấu hình và tình trạng suppression của recipient. Không retry một thông báo khi người dùng đã hủy đăng ký hoặc nội dung đã trở nên không hợp lệ.

## 12. Kết quả SMTP không rõ ràng và rủi ro duplicate

Một tình huống khó là timeout sau khi SMTP server đã nhận nội dung:

~~~text
Ứng dụng                        SMTP server
    |                                |
    |---------- SMTP DATA ---------->|
    |                                | Nhận đủ message
    |                                | Lưu để chuyển tiếp
    |<--- phản hồi bị mất / timeout --|
    |
    +--> Client thấy lỗi
~~~

Ứng dụng không biết server đã chấp nhận message hay chưa. Nếu retry, người nhận có thể nhận hai email.

Phân biệt:

- Lỗi trước khi kết nối: thường chưa submit.
- Lỗi trong phiên giao tiếp trước khi gửi DATA: thường ít nguy cơ duplicate hơn.
- Timeout sau khi dữ liệu đã truyền: kết quả có thể không rõ.
- Server trả phản hồi thành công: biết submission đã được chấp nhận, **không** chứng minh email vào Inbox.

Đừng coi mọi `MailSendException` hoặc timeout đều có thể retry an toàn. Hãy giữ mã lỗi, cause và phase nếu transport cung cấp để phân loại.

### Idempotency key không phải thuốc chữa mọi trường hợp

Một unique key trong database giúp ngăn tạo hai outbox record cho cùng sự kiện nghiệp vụ, nhưng không tự loại bỏ lần SMTP gửi lại của **cùng** record.

Nếu provider qua HTTP API hỗ trợ idempotency key, có thể truyền cùng key trong mọi lần retry. Với SMTP truyền thống, không có cơ chế idempotency chuẩn áp dụng cho mọi server. Header `Message-ID` hữu ích để correlation nhưng không bảo đảm mailbox/provider sẽ deduplicate.

Vì vậy, cần quyết định rõ cách xử lý AMBIGUOUS: đối soát provider nếu có API, chuyển sang trạng thái cần kiểm tra, hoặc chấp nhận retry khi duplicate ít gây hại và đã có biện pháp giảm rủi ro.

## 13. Tôn trọng hướng dẫn retry của provider

Một số email API trả HTTP `429` hoặc `503` cùng `Retry-After`. Nếu provider yêu cầu chờ tới một thời điểm, không nên retry sớm hơn.

Trong SMTP, phản hồi `4xx` thể hiện nhiều loại lỗi tạm thời nhưng không có một header `Retry-After` chuẩn chung tương đương HTTP cho mọi server. Nhà cung cấp có thể ghi khoảng cooldown hoặc quota trong tài liệu riêng.

Một chính sách phối hợp:

~~~text
algorithmNotBefore = now + backoffWithJitter
providerNotBefore  = thời điểm provider cho phép (nếu có)

nextAttemptAt = max(algorithmNotBefore, providerNotBefore)

Nếu nextAttemptAt >= businessExpiresAt:
    không retry nữa
~~~

`maxDelay` của thuật toán không được dùng để vi phạm cooldown dài hơn do provider yêu cầu. Nếu provider yêu cầu nghỉ 30 phút nhưng OTP chỉ còn hạn 5 phút, nên kết thúc thông báo thay vì cố gửi sau 2 phút.

### Phân biệt retry và rate limiting

- Retry backoff điều chỉnh **từng email thất bại**.
- Rate limiter điều chỉnh **tổng số email** trong một đơn vị thời gian.
- Thread pool/concurrency limit điều chỉnh **bao nhiêu lần gửi đang chạy đồng thời**.

Một ứng dụng có jitter nhưng 100 instance đều gửi quá nhiều email vẫn có thể vi phạm quota. Với nhiều instance, cần phối hợp quota theo account/provider, không chỉ đặt limiter cục bộ tại mỗi JVM.

## 14. Spring Retry cho retry ngắn hạn

Spring Retry cho phép khai báo retry qua `@Retryable`. Ví dụ dưới đây áp dụng khi dự án dùng phiên bản Spring Retry có các thuộc tính annotation tương ứng, cùng cơ chế AOP proxy phù hợp.

Bật retry:

~~~java
@Configuration
@EnableRetry
public class RetryConfiguration {
}
~~~

Service:

~~~java
@Service
public class RetryingMailSubmission {

    private final MailDeliveryPort mailDelivery;

    public RetryingMailSubmission(MailDeliveryPort mailDelivery) {
        this.mailDelivery = mailDelivery;
    }

    @Retryable(
        retryFor = TransientMailSubmissionException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 1000,
            multiplier = 2.0,
            maxDelay = 10_000,
            random = true
        )
    )
    public void submit(OutgoingMail mail) {
        mailDelivery.send(mail);
    }
}
~~~

Cần thư viện `spring-retry` và AOP/proxy dependencies phù hợp; các annotation nằm trong package `org.springframework.retry.annotation`. `maxAttempts = 4` ở đây bao gồm lần gọi ban đầu.

Các tham số:

- `delay`: khoảng chờ ban đầu theo mili giây.
- `multiplier`: hệ số tăng.
- `maxDelay`: cap độ trễ.
- `random`: bật cơ chế ngẫu nhiên hóa theo implementation Spring Retry.

Không mặc định coi `random = true` của Spring Retry là **full jitter chính xác** theo công thức ở phần 7. Nếu cần một phân phối jitter, deadline hoặc scheduler đặc thù, nên dùng retry policy tùy chỉnh hoặc scheduling ở outbox worker.

### Giới hạn của retry đồng bộ

Nếu một lời gọi `@Retryable` chờ backoff trên thread đang thực thi, thread đó vẫn bị chiếm dụng trong thời gian chờ. Nếu gọi trong HTTP request hoặc database transaction dài, latency và tài nguyên sẽ tăng.

Ngoài ra:

- Context retry không tự sống sót sau process crash.
- Self-invocation không đi qua Spring proxy mặc định.
- Không tự tạo idempotency.
- Không tự biết SMTP đã nhận message khi timeout.
- Không bảo đảm email được giao tới Inbox.
- Không tự khôi phục task đã bị mất khi process restart.

Dùng Spring Retry chủ yếu khi số lần retry ngắn, thời gian chờ nhỏ và yêu cầu không cần durability riêng. Với email giao dịch quan trọng, outbox/worker thường phù hợp hơn.

## 15. @Recover và xử lý khi đã hết attempts

Một service Spring Retry có thể khai báo `@Recover` để xử lý sau khi số lần thử đã cạn:

~~~java
@Service
public class RetryingMailSubmission {

    private final MailDeliveryPort mailDelivery;

    public RetryingMailSubmission(MailDeliveryPort mailDelivery) {
        this.mailDelivery = mailDelivery;
    }

    @Retryable(
        retryFor = TransientMailSubmissionException.class,
        maxAttempts = 3,
        backoff = @Backoff(
            delay = 1000,
            multiplier = 2.0
        )
    )
    public void submit(OutgoingMail mail) {
        mailDelivery.send(mail);
    }

    @Recover
    public void recover(
            TransientMailSubmissionException cause,
            OutgoingMail mail) {

        throw new MailSubmissionExhaustedException(
            "Mail attempts exhausted", cause
        );
    }
}
~~~

`@Recover` có thể chuyển exception hoặc ghi trạng thái thất bại. Nếu email cần theo dõi và retry sau restart, hãy cập nhật outbox trong transaction thích hợp thay vì chỉ log.

### Tránh nhiều tầng retry lồng nhau

Nếu outbox worker cho phép 5 attempts và mỗi attempt gọi một service `@Retryable(maxAttempts=4)`, ứng dụng có thể gọi SMTP tới 20 lần, không phải 5 lần.

Một thiết kế nên có **một owner của retry budget**. Nếu có retry bên trong transport cho lỗi kết nối cực ngắn, cần tính rõ những lần thử đó vào metrics và giới hạn tổng số lần gửi.

## 16. Không dùng Thread.sleep cho retry dài

Một vòng lặp dễ viết nhưng nguy hiểm:

~~~java
for (int attempt = 1; attempt <= 5; attempt++) {
    try {
        mailSender.send(message);
        return;
    } catch (MailException exception) {
        Thread.sleep(30_000);
    }
}
~~~

Những vấn đề:

- Sleep cả sau attempt cuối nếu không kiểm soát.
- Giữ HTTP/worker thread dù không làm việc.
- Có thể giữ database transaction và connection.
- Không phân loại lỗi trước retry.
- Không xử lý kết quả AMBIGUOUS.
- Không lưu attempts và lịch retry bền vững.
- Khi process chết, mọi trạng thái trên stack bị mất.

Với delay hàng giây hoặc phút, nên lưu thời điểm `nextAttemptAt` rồi để scheduler/worker kích hoạt lại. Trong lúc chờ, thread được trả về pool để xử lý email khác.

~~~text
SMTP trả lỗi tạm thời
          |
          v
Tính backoff + jitter
          |
          v
Ghi nextAttemptAt
          |
          v
Trả thread về executor
          |
          v
Scheduler chạy khi đến hạn
~~~

## 17. Kết hợp backoff với transactional outbox

Transactional outbox lưu yêu cầu gửi cùng transaction dữ liệu nghiệp vụ. Sau commit, worker lấy record, gửi email và cập nhật trạng thái.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- thành công ----> SUBMITTED
   |
   +---- lỗi tạm -------> RETRY_WAIT
   |                          |
   |                          v
   |                    đến nextAttemptAt
   |                          |
   |                          +---> PROCESSING
   |
   +---- lỗi vĩnh viễn -> FAILED
   |
   +---- hết attempt --> FAILED / DEAD_LETTER
~~~

Một outbox record cần:

| Trường | Vai trò |
| --- | --- |
| `id` | ID yêu cầu gửi |
| `idempotency_key` | ID ổn định cho sự kiện nghiệp vụ |
| `status` | PENDING, PROCESSING, RETRY_WAIT, SUBMITTED, FAILED |
| `attempts` | Số lần đã thực hiện send |
| `next_attempt_at` | Lịch thử tiếp theo |
| `created_at` và `expires_at` | Kiểm soát tuổi/deadline |
| `locked_by` và `locked_until` | Lease để tránh nhiều worker claim cùng lúc |
| `last_failure_class` | Phân loại lỗi |
| `last_error_code` | Mã lỗi đã chuẩn hóa |
| `provider_message_id` | ID provider nếu có |

Outbox giúp phục hồi sau process crash. Nó không thể đảm bảo exactly-once cho SMTP khi worker chết sau lúc server nhận email nhưng trước khi ghi SUBMITTED.

## 18. Ví dụ schema outbox với retry metadata

~~~sql
CREATE TABLE mail_outbox (
    id                 UUID PRIMARY KEY,
    idempotency_key    VARCHAR(200) NOT NULL UNIQUE,
    event_type         VARCHAR(120) NOT NULL,
    payload            JSONB NOT NULL,
    status             VARCHAR(30) NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    locked_by          VARCHAR(120),
    locked_until       TIMESTAMPTZ,
    last_failure_class VARCHAR(40),
    last_error_code    VARCHAR(120),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at       TIMESTAMPTZ
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Đây là schema PostgreSQL minh họa. Với database khác, đổi kiểu JSON, timestamp, syntax index. Index PENDING/RETRY_WAIT chưa bao quát các record PROCESSING hết lease; cần query/index bổ sung khi triển khai reclaim worker bị chết.

Không đưa attachment lớn thành Base64 trong payload nếu có thể dùng file reference bền vững. Không lưu secret/OTP plaintext quá thời hạn cần thiết.

### Attempt phải được ghi nhất quán

Một cách triển khai: khi claim để thực sự gửi, worker tăng `attempts`. Nếu chỉ submit vào executor nhưng pool từ chối trước khi task chạy, có thể giữ attempts không đổi và lưu `dispatch_failures` riêng.

Quan trọng là phép so sánh `attempts >= maxAttempts` được áp dụng sau khi attempts phản ánh đúng số lần gửi thực tế; tránh tăng hai lần cho một attempt.

## 19. Worker điều phối retry

Worker nên tách các transaction:

1. Claim outbox record trong transaction ngắn, đặt PROCESSING/lease.
2. Commit.
3. Gửi email qua `MailDeliveryPort` ngoài transaction.
4. Mở transaction khác để ghi SUBMITTED hoặc lịch retry.

Ví dụ xử lý kết quả ở mức khái niệm:

~~~java
public void process(MailOutboxRecord record) {
    try {
        mailDelivery.send(render(record));

        resultService.markSubmitted(record.id());

    } catch (PermanentMailSubmissionException exception) {
        resultService.markFailed(
            record.id(),
            "PERMANENT"
        );

    } catch (TransientMailSubmissionException exception) {
        RetryDecision decision = retryCoordinator.decide(
            record,
            MailFailureCategory.TRANSIENT
        );

        if (decision.retry()) {
            resultService.scheduleRetry(
                record.id(),
                decision.nextAttemptAt()
            );
        } else {
            resultService.markFailed(
                record.id(),
                decision.reason()
            );
        }

    } catch (AmbiguousMailSubmissionException exception) {
        resultService.markNeedsReconciliation(record.id());
    }
}
~~~

Các class `MailOutboxRecord`, `MailDeliveryPort` và `resultService` là abstraction của ứng dụng, không phải API có sẵn của Spring Framework Mail. Điều phối logic retry riêng khỏi adapter giúp không làm adapter SMTP phụ trách scheduler, transaction và deadline.

### Khi worker chết

Nếu worker chết ở trạng thái PROCESSING, lease hết hạn để worker khác claim. Nhưng nếu SMTP đã nhận email trước khi worker chết, retry có thể gây duplicate. Idempotency/reconciliation là bài toán riêng, không được giải quyết chỉ bằng lease.

## 20. Scheduler lấy record tới hạn

Có thể dùng `@Scheduled` và query database chọn record đến hạn:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxScheduler(MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "${app.mail.poll-delay-ms:1000}")
    public void tick() {
        dispatcher.dispatchDueBatch();
    }
}
~~~

Bật scheduling theo cấu hình phù hợp, ví dụ `@EnableScheduling`. Dispatcher cần claim record atomically và có chiến lược lease.

Ví dụ SQL PostgreSQL trong transaction:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

`FOR UPDATE SKIP LOCKED` giúp nhiều worker không cùng giữ lock trên một row đang được transaction khác claim. Sau claim cần cập nhật trạng thái/lease rồi commit trước khi gọi SMTP; không giữ database lock trong thời gian chờ network.

Nếu hệ thống có nhiều instance hoặc worker bị crash, phải reclaim PROCESSING khi lease hết hạn. Không chỉ polling PENDING mà để record PROCESSING kẹt mãi.

## 21. Rate limiter và retry storm sau outage

Sau một outage dài, nhiều record có thể đến hạn gần nhau. Jitter giúp phân tán nhưng không đảm bảo provider sẽ không bị vượt quota.

Nên kết hợp:

- Thread pool giới hạn concurrency.
- Rate limiter theo SMTP account/provider.
- Claim batch vừa với executor capacity.
- Backoff có jitter cho lỗi tạm thời.
- Circuit breaker/cooldown nếu provider lỗi diện rộng.
- Queue/outbox bền vững để giữ yêu cầu gửi.
- Metrics để điều chỉnh kích thước batch và rate.

Nếu dispatcher claim 1.000 record rồi đưa vào queue nội bộ chỉ chứa 100 task, nhiều record có thể có lease hết hạn trước khi được xử lý. Hãy claim theo capacity, hoặc thiết kế lease bắt đầu khi task thực sự được nhận; khi submit bị reject, trả record về trạng thái chờ an toàn.

Không để một chu kỳ scheduler bơm hàng nghìn task chỉ vì tất cả record đã đến `nextAttemptAt`.

## 22. Idempotency của job và của SMTP khác nhau

Một unique constraint có thể ngăn tạo nhiều yêu cầu gửi cho cùng một business event:

~~~sql
INSERT INTO mail_outbox (
    id, idempotency_key, event_type,
    payload, status
)
VALUES (
    :id, :key, :eventType, :payload, 'PENDING'
)
ON CONFLICT (idempotency_key) DO NOTHING;
~~~

Nhưng worker vẫn có thể gửi trùng **một** record:

~~~text
Worker A gọi SMTP, server chấp nhận
       |
       v
Worker A crash trước khi mark SUBMITTED
       |
       v
Lease hết hạn
       |
       v
Worker B retry
       |
       v
Người nhận có thể nhận hai email
~~~

Do đó cần phân biệt:

- **Job idempotency**: tránh enqueue trùng trong database.
- **Transport idempotency**: tránh side effect gửi trùng ở provider.

Không có cơ chế transport idempotency chung cho mọi SMTP server. `Message-ID` hữu ích để theo dõi, không phải cam kết dedup. Nếu provider API hỗ trợ idempotency key, hãy truyền cùng key cho những lần thử lại của cùng event.

Với kết quả không rõ, có thể chọn trạng thái AMBIGUOUS/NEEDS_RECONCILIATION để kiểm tra thêm thay vì tự động retry ngay.

## 23. Retry theo loại email

Không nên dùng một policy cho tất cả thông báo:

| Loại email | Yêu cầu thời gian | Hướng retry |
| --- | --- | --- |
| OTP | Phải đến trước TTL của mã | Ít attempts, deadline ngắn, không gửi mã hết hạn |
| Reset password | Token có hạn và có thể thu hồi | Dừng khi token không còn hợp lệ |
| Xác nhận đơn hàng | Cần lưu yêu cầu và retry | Outbox, exponential + jitter |
| Hóa đơn | Có thể chờ lâu hơn | Retry với snapshot/file reference bất biến |
| Newsletter | Lượng lớn, có unsubscribe | Campaign queue và rate limit riêng |
| Email debug | Không phải nghiệp vụ quan trọng | Có thể không retry |

Các giá trị cụ thể phải dựa trên SLA nghiệp vụ và chính sách provider, không lấy một con số chung từ ví dụ.

Nếu dữ liệu có thể thay đổi khi retry sau vài phút, nên lưu snapshot/version thích hợp. Ví dụ hóa đơn được cập nhật sau khi event phát sinh thì worker phải biết gửi phiên bản nào, không tự động đọc bản mới nhất nếu điều đó làm sai nội dung của sự kiện.

## 24. MaxAttempts và trạng thái cuối

Khi đã hết giới hạn, record cần chuyển sang trạng thái có thể quan sát:

~~~text
PENDING
  |
  v
PROCESSING (attempt 1)
  |
  v
RETRY_WAIT
  |
  v
PROCESSING (attempt 2)
  |
  ...
  |
  v
PROCESSING (attempt 5)
  |
  v
FAILED / DEAD_LETTER
~~~

Không nên để record ở RETRY_WAIT vô thời hạn dù không còn được phép retry. Khi chuyển FAILED, lưu reason như:

- `MAX_ATTEMPTS_REACHED`.
- `BUSINESS_DEADLINE_EXPIRED`.
- `RECIPIENT_INVALID`.
- `PROVIDER_POLICY_REJECTION`.
- `MANUAL_REVIEW_REQUIRED`.

Có thể xây cơ chế requeue thủ công sau khi sửa nguyên nhân. Requeue cần audit, phân quyền và xem lại deadline/idempotency. Không tự động reset attempts về 0 mỗi khi worker khởi động, vì như vậy maxAttempts mất ý nghĩa.

## 25. Metrics và log cho retry policy

Các số liệu nên theo dõi:

- Số attempt theo provider và outcome.
- Tổng retry được lên lịch theo failure category.
- Số job đạt maxAttempts.
- Độ trễ `nextAttemptAt - now`.
- Tuổi record PENDING/RETRY_WAIT lâu nhất.
- SMTP timeout, throttling, authentication failure.
- Số executor task bị reject.
- Số job AMBIGUOUS cần reconciliation.
- Thời gian từ created_at tới submitted_at.
- Tỷ lệ SUBMITTED của từng loại email.

Ví dụ log:

~~~json
{
  "notificationId": "notif-8fe2",
  "category": "ORDER_CONFIRMATION",
  "provider": "primary-smtp",
  "attempt": 3,
  "maxAttempts": 5,
  "failureCategory": "TRANSIENT",
  "smtpCode": "421",
  "retryDelayMs": 7421,
  "nextAttemptAt": "2026-11-12T12:00:07Z",
  "status": "RETRY_WAIT"
}
~~~

Không ghi raw email body, credentials, reset token hoặc toàn bộ thông tin cá nhân vào log. Ưu tiên internal notification ID, error code chuẩn hóa và metadata đủ để chẩn đoán.

### Cảnh báo vận hành

Cần chú ý khi:

- RETRY_WAIT tăng bất thường.
- Nhiều job liên tục chạm maxAttempts.
- Provider trả 4xx/throttling tăng.
- Tuổi record chưa gửi vượt SLA.
- Record PROCESSING hết lease tăng.
- AMBIGUOUS tăng, có thể do timeout mạng.
- Mail submitted giảm mạnh trong khi lượng job mới vẫn tăng.

Đừng tăng maxAttempts trước khi xác định nguyên nhân. Nếu credential sai, tăng retries chỉ tạo thêm thất bại.

## 26. Kiểm thử backoff và jitter

Retry policy có thể unit test mà không cần SMTP server.

### Kiểm tra exponential cap

Với initial 1 giây, max 8 giây:

~~~text
failedAttempt = 1 => cap 1s
failedAttempt = 2 => cap 2s
failedAttempt = 3 => cap 4s
failedAttempt = 4 => cap 8s
failedAttempt = 5 => cap 8s
~~~

Nếu dùng jitter, delay thực tế không bằng cap cố định. Test nên kiểm tra delay nằm trong khoảng hợp lệ.

Ví dụ equal jitter:

~~~java
@Test
void equalJitterFallsWithinExpectedRange() {
    MailBackoffPolicy policy = new MailBackoffPolicy(
        Duration.ofSeconds(1),
        Duration.ofSeconds(8)
    );

    RandomGenerator random = new Random(1234L);

    Duration result = policy.delayAfterFailure(3, random);

    assertFalse(result.compareTo(Duration.ofSeconds(2)) < 0);
    assertFalse(result.compareTo(Duration.ofSeconds(4)) > 0);
}
~~~

`failedAttempt = 3` có cap 4 giây nên equal jitter tạo 2–4 giây. Seed cố định giúp test tái lập được, nhưng không nên kiểm tra một chuỗi random duy nhất nếu chỉ cần xác nhận giới hạn.

### Kiểm tra attempts và deadline

Test cần bao gồm:

1. Lần thử đầu được tính là attempt 1.
2. `maxAttempts = 5` không tạo attempt thứ sáu.
3. Lỗi permanent không được lên lịch lại.
4. Lỗi transient tạo `nextAttemptAt` sau thời điểm hiện tại.
5. Email hết hạn không được gửi.
6. Lỗi ambiguous có quyết định riêng.
7. Provider cooldown muộn hơn backoff được tôn trọng.
8. Khi deadline gần hơn next attempt, policy dừng.

### Kiểm tra worker

Với fake `MailDeliveryPort` và test database:

- Worker thử lại sau lỗi tạm thời.
- Worker mark SUBMITTED khi adapter trả thành công.
- Lease hết hạn được reclaim.
- Hai worker không claim một record cùng lúc.
- Executor rejection không làm mất yêu cầu.
- Process crash sau submission có thể tạo duplicate; hệ thống có trạng thái/đối soát phù hợp.
- Không giữ DB transaction trong lúc sleep hoặc gửi SMTP.

Inject `Clock` để test không phải `Thread.sleep` nhiều giây và không phụ thuộc thời gian thực.

## 27. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Retry mọi `MailException` | Lặp lỗi permanent/cấu hình | Phân loại lỗi |
| Retry ngay không backoff | Retry storm | Backoff có giới hạn |
| Không jitter | Nhiều worker retry đồng thời | Jitter phân tán |
| Không maxAttempts | Email lỗi có thể lặp mãi | Max attempts + failed state |
| Không deadline | Gửi OTP/email hết hạn | `expiresAt` theo nghiệp vụ |
| Không cap delay | Khoảng chờ quá lớn/overflow | `maxDelay` và tính toán an toàn |
| Sleep trong transaction | Giữ connection/lock database | Lưu nextAttemptAt và scheduler |
| Retry trong HTTP request thời gian dài | Giữ thread, gây timeout | Worker/outbox |
| Worker + Spring Retry lồng nhau | Nhiều call SMTP hơn dự định | Một retry owner rõ ràng |
| Coi timeout luôn là chưa gửi | Duplicate email | Xử lý AMBIGUOUS |
| Coi Message-ID là dedup chắc chắn | Không có guarantee từ SMTP | Idempotency provider nếu có |
| Chỉ dùng @Async queue trong bộ nhớ | Crash làm mất job | Durable outbox/broker |
| Retry không tôn trọng provider cooldown | Tiếp tục bị throttling | Honor Retry-After/policy |
| Claim quá nhiều task | Record kẹt/lease hết hạn | Bounded batch |
| Coi SUBMITTED là DELIVERED | Báo sai trạng thái người nhận | Delivery events riêng |
| Log nội dung email và secret | Rò rỉ dữ liệu | Log ID/code/attempt tối thiểu |

## 28. Quy trình triển khai

Một luồng retry hoàn chỉnh có thể thực hiện theo thứ tự:

1. **Định nghĩa mail category và SLA**: OTP, transactional, invoice, campaign.
2. **Tách delivery adapter** để một lời gọi tương ứng một attempt gửi.
3. **Phân loại lỗi** thành transient, permanent, configuration và ambiguous.
4. **Cấu hình maxAttempts, initialDelay, multiplier, maxDelay, jitter và deadline**.
5. **Áp dụng rate limit/concurrency limit** theo provider.
6. **Với email quan trọng, lưu outbox** trong cùng database transaction với thay đổi nghiệp vụ.
7. **Worker claim record** trong transaction ngắn, đặt lease và thực hiện send ngoài transaction.
8. **Nếu SUBMITTED**, lưu kết quả; theo dõi delivery event riêng nếu có.
9. **Nếu permanent**, mark FAILED mà không retry.
10. **Nếu ambiguous**, đối soát hoặc áp dụng policy idempotency đã được quyết định.
11. **Nếu transient**, kiểm tra attempts/deadline, tính delay có jitter và provider cooldown.
12. **Lưu nextAttemptAt**, trả thread về pool, đợi scheduler.
13. **Nếu exhausted**, mark FAILED/DEAD_LETTER và cảnh báo.
14. **Theo dõi metrics**, kiểm thử overload, process crash, concurrency và lỗi provider.

~~~text
Outbox record đến hạn
          |
          v
Claim + kiểm tra deadline
          |
          v
Gửi qua MailDeliveryPort
          |
          +---- SUCCESS ------> SUBMITTED
          |
          +---- FAILURE
                    |
                    v
             Phân loại lỗi
                    |
        +-----------+-----------+
        |           |           |
    PERMANENT    AMBIGUOUS   TRANSIENT
        |           |           |
        v           v           v
      FAILED     Reconcile   Kiểm tra giới hạn
                                |
                           +----+----+
                           |         |
                         Stop      Continue
                           |         |
                           v         v
                         FAILED   Backoff + jitter
                                     |
                                     v
                                nextAttemptAt
                                     |
                                     v
                                 RETRY_WAIT
~~~

## 29. Ghi nhớ

- Retry chỉ hiệu quả với lỗi có khả năng phục hồi; lỗi vĩnh viễn cần sửa nguyên nhân.
- SMTP timeout không luôn có nghĩa email chưa được gửi, nên có rủi ro duplicate.
- `maxAttempts` phải có quy ước rõ; ở đây nó **bao gồm lần gửi đầu tiên**.
- Exponential backoff tăng delay theo số lần lỗi và được chặn bằng `maxDelay`.
- Jitter phân tán thời điểm retry để giảm thundering herd.
- Full, equal và decorrelated jitter có đặc điểm khác nhau; không dùng một công thức cho mọi SLA.
- Deadline nghiệp vụ có thể buộc dừng trước khi đạt maxAttempts.
- Tôn trọng hướng dẫn cooldown của provider và giới hạn tổng tốc độ gửi.
- Spring Retry phù hợp với retry ngắn trong process; không thay thế durable outbox.
- Tránh sleep dài trong HTTP request hoặc database transaction.
- Outbox worker nên lưu `nextAttemptAt`, lease và số attempts để phục hồi sau restart.
- Idempotency trong database khác với idempotency của SMTP; Message-ID không bảo đảm dedup.
- Đừng lồng nhiều tầng retry khiến tổng lần gửi vượt budget.
- Ghi metrics/log đủ để theo dõi retry exhausted, queue age và ambiguous outcomes.
- Khi đã hết attempts hoặc hết deadline, kết thúc job bằng trạng thái có thể quan sát và xử lý.

Một retry policy tốt không cố gửi mãi bằng mọi giá. Nó chọn đúng lỗi để retry, giãn nhịp gửi bằng backoff và jitter, dừng khi thông báo không còn giá trị và giữ trạng thái đủ bền vững để vận hành. Trong Spring Framework Mail, kết hợp **bounded exponential backoff, jitter, maxAttempts, deadline và outbox worker** giúp hệ thống chịu lỗi tạm thời mà vẫn kiểm soát tải SMTP và nguy cơ gửi trùng.
