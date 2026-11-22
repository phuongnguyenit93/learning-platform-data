# Giới hạn tốc độ để không làm đầy mail server trong Spring Framework Mail

Khi ứng dụng gửi email bất đồng bộ, việc chuyển lệnh gửi ra khỏi HTTP request chỉ giải quyết vấn đề **không bắt người dùng chờ SMTP**. Nó không tự bảo vệ mail server khỏi lượng email đột biến. Một hệ thống có thể tạo hàng chục nghìn thông báo từ sự kiện đơn hàng, chiến dịch, import dữ liệu hoặc quá trình replay; nếu worker cùng gọi `JavaMailSender.send(...)` hết tốc lực, SMTP relay có thể quá tải, tăng hàng đợi, từ chối kết nối, trì hoãn thư hoặc áp dụng chính sách giới hạn.

Vì vậy, kiến trúc gửi email bất đồng bộ cần một cơ chế **rate limiting** (giới hạn số lần gửi theo thời gian) kết hợp với **concurrency limiting** (giới hạn số lệnh SMTP đang chạy đồng thời), **backpressure** (điều tiết khi hệ thống phía sau chậm) và **queue management** (quản lý backlog bền vững). Mục tiêu không đơn giản là “gửi chậm đi”, mà là **gửi với tốc độ hệ thống và nhà cung cấp chấp nhận được, không làm mất email quan trọng và không tạo hàng đợi tăng vô hạn**.

Trong Spring Framework Mail, `JavaMailSender` cung cấp API tạo và gửi email. Nó không tự áp đặt hạn mức toàn cục theo provider, domain, tenant hay chiến dịch. Các chính sách điều tiết phải được thiết kế ở tầng ứng dụng, dispatcher hoặc dịch vụ email được dùng chung.

## 1. “Làm đầy mail server” có nghĩa là gì?

Mail server thường tiếp nhận thư, đưa vào hàng đợi và chuyển tiếp tới các máy chủ nhận. Nếu lượng thư đến vượt khả năng xử lý hoặc hạn mức được cấp, một số vấn đề có thể xuất hiện:

- Hàng đợi tại SMTP relay tăng, thư được giao chậm.
- Server từ chối thêm kết nối hoặc lệnh gửi trong một khoảng thời gian.
- Vượt quota số thông điệp hoặc số người nhận trong một phút, giờ, ngày.
- Bộ nhớ, CPU, đĩa hoặc tài nguyên xử lý MIME bị tiêu hao.
- Quá nhiều kết nối SMTP song song dẫn đến timeout.
- Nhà cung cấp tạm hạn chế người gửi do chính sách chống spam hoặc chất lượng lưu lượng.
- Các miền nhận có thể áp dụng chính sách throttling riêng dù relay đầu tiên vẫn chấp nhận thư.
- Một chiến dịch email tùy chọn chiếm tài nguyên khiến email OTP hoặc giao dịch quan trọng bị chậm.

Không nên hiểu “đầy” chỉ là hết dung lượng ổ đĩa. Nó còn bao gồm **hết năng lực xử lý, hết quota hoặc tồn đọng quá nhiều thông điệp** ở ứng dụng, broker, relay hoặc hệ thống nhận.

### Những vị trí có hàng đợi

~~~mermaid
flowchart LR
    A["Business events"] --> B["App outbox / queue"]
    B --> C["Mail workers"]
    C --> D["Rate & concurrency gates"]
    D --> E["SMTP relay"]
    E --> F["Relay delivery queue"]
    F --> G["Recipient MX"]
    G --> H["Mailbox"]
~~~

Mỗi vị trí có tốc độ và khả năng chứa khác nhau. Khi SMTP relay trả lời rằng đã chấp nhận thư, relay vẫn có thể phải tiếp tục xếp hàng và giao thư ở các bước sau. **Thành công của `send()` không có nghĩa người nhận đã thấy email trong inbox.**

## 2. Phân biệt rate limit, concurrency limit và backpressure

Ba cơ chế giải quyết những vấn đề khác nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Rate limiting | Số thông điệp/người nhận/byte trong một khoảng thời gian | Tối đa 300 email mỗi phút |
| Concurrency limiting | Số thao tác SMTP chạy đồng thời | Tối đa 4 kết nối hoặc lần gửi đang hoạt động |
| Queue bounding | Số công việc đang chờ trong bộ nhớ/broker | Giới hạn 500 tác vụ trong executor |
| Backpressure | Điều chỉnh tốc độ lấy/nhận việc khi downstream chậm | Worker ngừng claim khi không còn permit |
| Retry backoff | Khoảng cách giữa các lần thử sau lỗi | Thử lại sau 1, 2, 4 phút theo chính sách |
| Circuit breaking | Tạm ngừng gọi downstream khi lỗi diện rộng | Tạm dừng SMTP khi relay không khả dụng |

**Chỉ giới hạn số thread không tương đương giới hạn số email mỗi phút.** Một thread có thể gửi rất nhanh và vượt quota. Ngược lại, giới hạn 100 email/phút nhưng cho 100 kết nối hoạt động đồng thời có thể tạo burst gây quá tải relay. Thực tế thường cần cả giới hạn tốc độ lẫn mức song song.

### Ví dụ: 4 worker không đảm bảo 4 email/giây

Nếu mỗi lần gửi mất khoảng 100 ms, bốn worker có thể hoàn tất hàng chục lần gửi mỗi giây. Nếu provider cho phép thấp hơn, giới hạn 4 worker là chưa đủ. Nếu mỗi lần gửi mất 10 giây, cùng 4 worker lại làm throughput giảm mạnh. Rate limit quy định **ngân sách theo thời gian**, còn concurrency limit quy định **số lời gọi đang diễn ra**.

### Công thức năng lực hàng đợi

Gọi:

- `λ` (lambda): tốc độ thông điệp đến ứng dụng, tính bằng email/giây.
- `μ` (mu): tốc độ xử lý/gửi ổn định, tính bằng email/giây.
- `Q`: số email đang chờ.

Khi hệ thống liên tục có việc, tốc độ tăng backlog gần đúng:

\[
\frac{dQ}{dt} \approx \lambda - \mu
\]

Nếu `λ > μ` kéo dài, backlog tăng; không có một queue dung lượng hữu hạn nào có thể chứa mãi. Nếu `λ < μ` trong đủ thời gian, hệ thống có cơ hội xử lý hết lượng tồn. **Rate limiting bảo vệ mail server, nhưng phải đi kèm kiểm soát đầu vào và năng lực xử lý lâu dài để queue không tăng vô hạn.**

## 3. Xác định hạn mức thực tế trước khi cấu hình

Hạn mức có thể đến từ SMTP provider, relay nội bộ, các miền nhận và chính sách của ứng dụng. Trước khi chọn một con số, cần xác định **đơn vị đo và phạm vi**.

| Loại hạn mức | Đơn vị ví dụ | Câu hỏi cần xác nhận |
| --- | --- | --- |
| Messages per second | 5 message/giây | Áp dụng cho một tài khoản hay toàn hệ thống? |
| Messages per minute | 300 message/phút | Có cho phép gửi dồn 300 thư đầu phút không? |
| Recipients per minute | 500 recipient/phút | Một email có nhiều To/Cc/Bcc được tính thế nào? |
| Daily sending quota | 20.000 message/ngày | Chu kỳ reset theo UTC hay giờ của provider? |
| Max concurrent connections | 3 kết nối | Tính theo IP, account hay SMTP credential? |
| Max message size | Theo provider | Giới hạn gồm MIME/Base64 và attachment không? |
| Per-domain limit | Ví dụ theo gmail.com | Có giới hạn riêng theo domain/MX không? |
| Per-tenant budget | Ví dụ theo doanh nghiệp | Tenant nào được dùng bao nhiêu năng lực? |
| Campaign cap | Ví dụ theo chiến dịch | Email tùy chọn có được dùng toàn bộ quota không? |

Các số trong bảng là **ví dụ minh họa**, không phải giới hạn mặc định của Spring hoặc của một nhà cung cấp cụ thể. Hãy lấy quota được cấp từ tài liệu provider, hợp đồng và dữ liệu vận hành hiện tại.

### Không chỉ đếm số email

Một MIME message gửi cho 30 địa chỉ có thể được provider tính theo số recipient, dù phía ứng dụng chỉ gọi `send()` một lần. Nhiều nhà cung cấp giới hạn số recipient trên mỗi message hoặc theo khoảng thời gian. Vì vậy nên tách:

- **Message budget:** số message được submit.
- **Recipient budget:** tổng số người nhận trên To/Cc/Bcc.
- **Byte budget:** lượng dữ liệu MIME hoặc attachment.
- **Connection budget:** số phiên SMTP đang hoạt động.

Với thông báo cá nhân hóa, thường nên gửi riêng mỗi người nhận để bảo vệ thông tin và hỗ trợ theo dõi kết quả. Không gộp hàng trăm người nhận vào Bcc chỉ để đánh lừa quota; chính sách provider có thể vẫn đếm từng người.

### Giới hạn nội bộ phải chừa biên an toàn

Nếu provider cho phép một tốc độ tối đa, ứng dụng thường nên bắt đầu dưới mức đó vì còn:

- Retry và email phát sinh từ nhiều dịch vụ.
- Quota chia sẻ với hệ thống khác.
- Sự không ổn định của network/relay.
- Chiến dịch theo giờ cao điểm.
- Các chính sách riêng theo người gửi hoặc domain.

Không nên coi một giá trị cấu hình là đúng mãi. Theo dõi response, độ trễ và tỷ lệ lỗi để điều chỉnh.

## 4. Đặt giới hạn tại đâu trong kiến trúc bất đồng bộ?

Một kiến trúc bền vững thường gồm producer, outbox/queue và worker:

~~~text
HTTP / business transaction
       |
       v
Save domain event + mail outbox
       |
       v
      COMMIT
       |
       v
Due-message scheduler
       |
       v
Claim work with lease
       |
       v
Render and validate content
       |
       v
Concurrency permit + rate permit
       |
       v
JavaMailSender.send(...)
       |
       v
Update SUBMITTED / RETRY_PENDING / FAILED
~~~

**Điểm giới hạn quan trọng là ngay trước SMTP submission.** Không nên chỉ rate-limit API tạo notification, vì một ngày sau worker replay có thể đẩy hàng nghìn message ra SMTP mà không đi qua API đó. Cũng không nên chỉ giới hạn một executor trong một instance nếu ứng dụng được chạy trên nhiều replica.

### Hai cấp điều tiết

1. **Admission control:** giới hạn lượng yêu cầu được phép tạo hoặc nằm trong queue, tùy loại thông báo. Email tùy chọn có thể bị trì hoãn, từ chối hoặc suppress khi hệ thống quá tải.
2. **Dispatch control:** giới hạn lượng message đang được submit vào SMTP. Email bắt buộc được lưu bền vững và xử lý theo ưu tiên khi có năng lực.

Không xóa hoặc bỏ âm thầm email bắt buộc chỉ vì thiếu permit tại thời điểm hiện tại. Hãy giữ trạng thái PENDING/RETRY_PENDING, đặt thời điểm thử tiếp và phát cảnh báo nếu backlog vượt SLA.

## 5. Các thuật toán rate limiting thường dùng

### 5.1. Fixed window counter

Đếm số lần gửi trong một khoảng thời gian cố định, ví dụ mỗi phút:

~~~text
Window 10:00-10:01: 0 ... 300 message
Window 10:01-10:02: counter reset
~~~

Ưu điểm: đơn giản, dễ lưu vào Redis hoặc database. Nhược điểm: có thể xảy ra burst ở ranh giới hai cửa sổ, ví dụ gửi nhiều thư cuối phút rồi lại gửi nhiều thư đầu phút sau.

### 5.2. Sliding window

Tính số lần gửi trong một cửa sổ trượt gần đây, ví dụ 60 giây tính từ thời điểm hiện tại. Nó giảm burst ở ranh giới nhưng cần lưu timestamp hoặc dùng cơ chế ước lượng. Phù hợp khi nhà cung cấp áp dụng quota kiểu sliding window.

### 5.3. Leaky bucket

Đưa công việc vào một hàng đợi được xả theo tốc độ ổn định. Thích hợp khi cần luồng gửi đều, tránh burst lớn. Tuy nhiên, bucket/queue phải có dung lượng hữu hạn và có chính sách xử lý khi đầy.

### 5.4. Token bucket

Một bucket chứa permit. Permit được bổ sung theo tốc độ ổn định; mỗi lần gửi tiêu thụ một số permit. Bucket có dung lượng tối đa để giới hạn burst.

Ví dụ:

- Tốc độ bổ sung: 5 token/giây.
- Dung lượng: 10 token.
- Mỗi email tiêu thụ 1 token.

Sau thời gian rảnh, ứng dụng có thể gửi một burst tối đa 10 message; sau đó phải chờ token được bổ sung. Nếu cần hạn chế burst chặt chẽ, giảm capacity hoặc kết hợp với pacing/leaky bucket.

~~~mermaid
flowchart LR
    A["Pending email"] --> B{"Token available?"}
    B -- "Yes" --> C["Consume permit"]
    C --> D["SMTP send"]
    B -- "No" --> E["Keep pending / schedule later"]
    E --> B
~~~

Token bucket phổ biến vì vừa hỗ trợ tốc độ trung bình vừa cho phép burst có kiểm soát. Nhưng phải hiểu nhà cung cấp giới hạn theo đơn vị nào: message, recipient, kết nối hoặc byte.

## 6. Cài đặt token bucket đơn giản trong một JVM

Ví dụ dưới đây minh họa một limiter dựa trên `System.nanoTime()`. Đây là **limiter trong bộ nhớ của một process**, không có tác dụng giới hạn tổng tốc độ của nhiều replica.

~~~java
package com.example.mail;

public final class InMemoryTokenBucket {

    private final double capacity;
    private final double refillPerSecond;

    private double availableTokens;
    private long lastRefillNanos;

    public InMemoryTokenBucket(
            double capacity,
            double refillPerSecond) {

        if (capacity < 1 || refillPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "Capacity and refill rate must be positive");
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.availableTokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    public synchronized boolean tryAcquire(int permits) {
        if (permits <= 0 || permits > capacity) {
            throw new IllegalArgumentException(
                    "Invalid permit count");
        }

        long now = System.nanoTime();
        double elapsedSeconds =
                Math.max(0L, now - lastRefillNanos)
                        / 1_000_000_000.0;

        availableTokens = Math.min(
                capacity,
                availableTokens + elapsedSeconds * refillPerSecond);
        lastRefillNanos = now;

        if (availableTokens < permits) {
            return false;
        }

        availableTokens -= permits;
        return true;
    }
}
~~~

Đặc điểm của ví dụ:

- `synchronized` giúp các thread trong cùng JVM không cùng tiêu thụ vượt số token.
- `System.nanoTime()` là nguồn thời gian đơn điệu phù hợp để đo khoảng trôi qua trong process.
- Token được bổ sung theo tốc độ đã định và không vượt capacity.
- `tryAcquire` trả `false` ngay khi thiếu token; không ngủ trong thread.
- Một lệnh gửi nhiều recipient có thể cần nhiều permit theo chính sách.

### Ví dụ cấu hình bean

~~~java
@Configuration
public class MailRateConfiguration {

    @Bean
    public InMemoryTokenBucket mailTokenBucket() {
        // Trung bình tối đa 4 message/giây, burst 8 message.
        return new InMemoryTokenBucket(8, 4);
    }
}
~~~

Đây không phải giới hạn chuẩn của SMTP; giá trị phải dựa trên quota thực tế. Nếu chạy ba replica, mỗi replica dùng limiter riêng với 4 token/giây có thể tạo tổng khoảng 12 message/giây. **Khi cần giới hạn toàn cụm, sử dụng limiter phân tán hoặc một cổng gửi tập trung.**

### Khi không có permit

Không nên:

~~~java
while (!bucket.tryAcquire(1)) {
    // Busy spin: đốt CPU trong lúc chờ.
}
~~~

Cũng không nên đưa hàng nghìn task vào executor chỉ để chúng `Thread.sleep(...)` chờ quota. Cách tốt hơn là giữ job trong outbox/queue và lên lịch lần dispatch tiếp theo. Nếu tần suất thấp và latency cho phép, scheduler có thể kiểm tra permit định kỳ; với lưu lượng cao, limiter nên trả thời gian sẵn sàng gần đúng để worker có thể lập lịch hiệu quả.

## 7. Giới hạn số kết nối và lần gửi đồng thời

Ngay cả khi có token bucket, vẫn cần chặn việc quá nhiều lời gọi SMTP chạy cùng lúc. Một cách đơn giản trong một JVM là `Semaphore`:

~~~java
import java.util.concurrent.Semaphore;

public final class SmtpConcurrencyGate {

    private final Semaphore slots;

    public SmtpConcurrencyGate(int maxConcurrentSends) {
        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrentSends must be positive");
        }
        this.slots = new Semaphore(maxConcurrentSends);
    }

    public boolean tryEnter() {
        return slots.tryAcquire();
    }

    public void leave() {
        slots.release();
    }
}
~~~

Với đoạn code này, chỉ những lần `tryEnter()` trả về `true` mới được gọi `leave()`. Không gọi `leave()` khi chưa lấy được permit, vì sẽ tăng số slot ảo.

### Kết hợp rate và concurrency

~~~java
public DispatchResult trySubmit(PreparedMail prepared) {
    if (!smtpGate.tryEnter()) {
        return DispatchResult.DEFERRED_CONCURRENCY;
    }

    try {
        if (!tokenBucket.tryAcquire(1)) {
            return DispatchResult.DEFERRED_RATE;
        }

        mailSender.send(prepared.message());
        return DispatchResult.SUBMITTED;
    } finally {
        smtpGate.leave();
    }
}
~~~

`PreparedMail` và `DispatchResult` là các kiểu do ứng dụng định nghĩa. Method này mô tả việc lấy slot trước, sau đó lấy token và submit; nếu không có token, trả kết quả trì hoãn để worker giữ job chờ, không đánh dấu FAILED. Nếu SMTP ném exception, tầng gọi phải phân loại và cập nhật trạng thái outbox.

Token đã tiêu thụ thường không được hoàn lại sau một lần thử SMTP, vì nhà cung cấp có thể đã nhận một phần hoặc toàn bộ request, và quota thường tính cả attempts. Đây là lựa chọn chính sách: nếu chắc chắn chưa hề gọi SMTP, ứng dụng có thể có quy tắc hoàn permit riêng; không tự ý refund sau kết quả không rõ.

### Concurrency limit không phải connection pool

Giới hạn 3 lần gửi đồng thời không đồng nghĩa ứng dụng luôn giữ 3 kết nối SMTP mở. Việc tái sử dụng hoặc mở mới kết nối phụ thuộc vào transport/Jakarta Mail và cách triển khai. Nếu sử dụng session/connection pooling, vẫn cần giới hạn số kết nối hoạt động theo quota provider.

## 8. Bounded executor khi dùng @Async

Một lỗi thường gặp là dùng `@Async` để “gửi nhanh” nhưng không giới hạn số task được đưa vào executor:

~~~java
@Async
public void sendEmail(MimeMessage message) {
    mailSender.send(message);
}
~~~

Nếu hàng nghìn request cùng gọi method, các task có thể chờ trong executor hoặc chạy song song nhiều hơn khả năng SMTP. `@Async` không tự áp dụng quota email/giây và không biến công việc thành durable queue.

### Cấu hình ThreadPoolTaskExecutor hữu hạn

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mail-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Khi dùng:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> sendInBackground(
        PreparedMail message) {
    mailDispatcher.submit(message);
    return CompletableFuture.completedFuture(null);
}
~~~

Những giới hạn này chỉ là ví dụ. Khi queue đầy và không thể tạo thêm worker, `AbortPolicy` từ chối task thay vì tạo backlog vô hạn trong heap. Caller phải bắt/ghi nhận việc từ chối và giữ bản ghi cần gửi ở outbox. Không âm thầm mất email bắt buộc.

### Lưu ý về executor

- `corePoolSize` là số thread lõi.
- `maxPoolSize` là số thread tối đa.
- `queueCapacity` là số task được phép chờ.
- Khi queue đầy và thread đạt giới hạn, rejection policy quyết định cách phản ứng.
- `@Async` qua Spring proxy không tự hoạt động khi method được gọi trực tiếp từ một method khác trong cùng bean (self-invocation).
- Task trong memory executor có thể mất nếu process dừng; không thay thế outbox/queue bền vững.
- Với `void @Async`, exception có thể không quay về HTTP caller; cần cơ chế xử lý và ghi trạng thái riêng.

`CallerRunsPolicy` có thể tạo backpressure bằng cách chạy task trong thread của người gọi, nhưng với mail gửi từ HTTP request, nó có thể khiến request bất ngờ chờ SMTP. Hãy chọn rejection policy theo ngữ cảnh, không dùng CallerRunsPolicy như một giải pháp chung.

## 9. Không để queue tăng vô hạn

Rate limiting có thể khiến tốc độ gửi thấp hơn tốc độ tạo notification. Nếu producer liên tục tạo nhiều việc hơn worker xử lý được, backlog sẽ tăng. Vì vậy, cần **bounded queues và chính sách admission**.

### Phân loại công việc khi quá tải

| Loại email | Khi backlog cao |
| --- | --- |
| OTP, xác thực | Ưu tiên xử lý nhanh, giới hạn request và cảnh báo khi vượt SLA |
| Biên nhận, xác nhận đơn hàng | Lưu bền vững, retry và theo dõi tuổi backlog |
| Thông báo trạng thái cần thiết | Giữ bền vững, có thể batch điều phối theo ưu tiên |
| Newsletter | Trì hoãn, kiểm tra consent và expiry |
| Khuyến mại | Có thể suppress/hủy nếu campaign hết hạn hoặc quá tải |
| Báo cáo định kỳ không khẩn cấp | Có thể gộp, giảm tần suất hoặc lên lịch ngoài giờ cao điểm |

**Không ưu tiên email marketing trước OTP chỉ vì marketing được tạo trước trong queue.** Một hàng đợi FIFO duy nhất có thể gây head-of-line blocking: hàng nghìn email tùy chọn ở đầu queue làm email bảo mật đến sau phải chờ.

### Queue trong bộ nhớ và outbox bền vững

Một queue trong `ThreadPoolTaskExecutor` giúp giới hạn task đang chờ ở một process. Nó không đủ để bảo đảm yêu cầu gửi sống qua restart. Outbox hoặc broker bền vững lưu yêu cầu; worker chỉ lấy một lượng việc phù hợp với permit và concurrency.

Nên tách:

- **Persistent backlog:** outbox, broker hoặc job store.
- **In-flight batch:** số công việc đã claim có lease.
- **Executor queue:** lượng task đang chờ trong process.
- **SMTP connection capacity:** số kết nối/lần gửi đang hoạt động.

Nếu không có token, worker không nên claim thêm hàng nghìn bản ghi rồi giữ chúng ở trạng thái PROCESSING. Điều này khiến lease hết hạn, tạo claim lại và khó quan sát.

## 10. Backpressure từ dispatcher đến producer

Backpressure là khả năng phản ứng khi downstream không còn đủ năng lực. Nó không có nghĩa cứ gặp lỗi là trả HTTP 500 cho mọi request.

### Ở phía producer

- Giới hạn số notification tùy chọn được tạo theo user/tenant/campaign.
- Giới hạn tốc độ API có thể sinh email, ví dụ endpoint yêu cầu OTP.
- Hủy hoặc gộp thông báo trùng/không thiết yếu.
- Khi queue đạt ngưỡng, trì hoãn chiến dịch lớn.
- Không bỏ yêu cầu giao dịch bắt buộc nếu chưa có phương án nghiệp vụ thay thế.

### Ở phía worker

- Chỉ claim số record tương ứng với slot và permit có thể dùng.
- Tạm ngừng claim khi limiter hết quota.
- Giảm concurrency khi SMTP timeout hoặc throttling tăng.
- Dừng worker hoặc mở circuit breaker khi provider outage diện rộng.
- Reschedule thay vì sleep trong transaction.

### Tại sao không xử lý hàng đợi bằng cách tăng thread?

Nếu downstream là SMTP relay đang là nút thắt, tăng số thread chỉ tăng số lời gọi đang chờ, số connection và tỷ lệ timeout. Khi provider đã áp dụng quota, tăng thread không tăng quota. Cần điều chỉnh **tốc độ đưa việc vào relay**, không phải chỉ tăng năng lực tiêu thụ CPU của ứng dụng.

## 11. Ưu tiên email quan trọng và công bằng giữa các nguồn

Hệ thống thường cần gửi nhiều nhóm email:

- Security/OTP.
- Transactional.
- Product notifications.
- Marketing/campaign.

Nếu dùng chung một bucket và hàng đợi, chiến dịch marketing có thể tiêu thụ hết permit ngay trước khi OTP xuất hiện. Một thiết kế tốt có thể:

1. Đặt một **global provider limit** không được vượt.
2. Chia budget theo nhóm ưu tiên.
3. Dành một phần năng lực cho security/transactional.
4. Đặt giới hạn riêng theo tenant/campaign.
5. Có cơ chế fairness để một tenant không chiếm toàn bộ quota.

~~~text
                   GLOBAL SMTP BUDGET
                           |
          +----------------+----------------+
          |                |                |
      Security         Transactional     Optional
       priority          priority          budget
          |                |                |
      User limits       Tenant limits   Campaign limits
          +----------------+----------------+
                           |
                        SMTP relay
~~~

Phân chia này phải kiểm soát tổng không vượt global limit. Không tạo bốn limiter độc lập với tổng quota lớn hơn provider cho phép.

### Reserved capacity và starvation

Dành năng lực cho OTP giúp tránh chậm thông báo bảo mật. Tuy nhiên, nếu luôn ưu tiên tuyệt đối, email thông thường có thể bị đói tài nguyên khi traffic security liên tục cao. Có thể dùng weighted fair scheduling, giới hạn tối thiểu/tối đa theo nhóm hoặc quy tắc mượn quota khi nhóm ưu tiên đang rảnh.

Quy tắc cụ thể phụ thuộc SLA. Nếu OTP chỉ có hiệu lực vài phút, độ trễ được chấp nhận phải thấp hơn email bản tin. Nếu chiến dịch đã hết hạn, có thể dừng gửi thay vì chiếm quota để xử lý backlog cũ.

## 12. Giới hạn theo provider, domain và tenant

Một ứng dụng có thể dùng nhiều SMTP provider hoặc nhiều tài khoản. Ngược lại, nhiều service có thể cùng dùng một tài khoản SMTP. Vì vậy, cần xác định **đúng khóa rate limit**.

| Khóa | Ví dụ khái niệm | Lý do |
| --- | --- | --- |
| Provider/account | `smtp-account:transactional` | Không vượt quota của credential |
| Sender/domain | `sender:mail.example.com` | Tuân theo policy người gửi |
| Recipient domain | `recipient-domain:example.net` | Giảm burst tới miền nhận |
| Tenant | `tenant:tenant-42` | Tránh một tenant chiếm toàn bộ năng lực |
| Campaign | `campaign:campaign-184` | Khống chế đợt gửi tùy chọn |
| Notification category | `category:security` | Ưu tiên email thiết yếu |

Một message có thể cần lấy permit ở **nhiều tầng**: provider toàn cục, tenant, category và recipient domain. Chỉ khi tất cả điều kiện đạt mới được submit.

### Đừng lấy nhiều token không nguyên tử rồi bỏ dở

Giả sử ứng dụng đã tiêu thụ token global nhưng không lấy được token domain. Nếu cứ thử lại liên tục, global bucket có thể bị tiêu hao mà không có message nào được gửi. Một triển khai nhiều quota cần:

- Kiểm tra các budget theo thứ tự hoặc giao dịch nguyên tử trong cùng limiter store.
- Có chính sách hoàn/release permit nếu chắc chắn chưa gọi SMTP.
- Tránh deadlock khi đồng thời lấy các permit theo nhiều khóa.
- Đặt thời gian chờ và reschedule khi một lớp giới hạn không còn năng lực.
- Tách **rate quota** khỏi **concurrency slot** nếu cơ chế hoàn trả khác nhau.

Trong hệ phân tán, thường nên dùng một dịch vụ admission/limiter tập trung hoặc thư viện hỗ trợ atomic multi-key theo đúng nhu cầu. Không tự giả định việc gọi nhiều limiter độc lập luôn cho ra ngân sách chính xác.

### Recipient domain không đồng nghĩa SMTP server đích

Một địa chỉ `customer@example.net` có domain `example.net`, nhưng email thực tế có thể được chuyển tới MX thuộc nhà cung cấp khác. Chính sách rate theo recipient domain là một phép nhóm hữu ích ở mức ứng dụng, không phải mô hình chính xác của mọi kết nối tới máy chủ nhận.

Khi phân nhóm, sử dụng domain từ địa chỉ đã được parse/validate, không tách tùy tiện theo chuỗi không tin cậy. Cần chú ý địa chỉ quốc tế hóa, chữ hoa/thường và quy tắc chuẩn hóa đã được hệ thống thống nhất.

## 13. Giới hạn tốc độ trong ứng dụng nhiều replica

Limiter trong bộ nhớ của từng JVM **không bảo đảm giới hạn toàn cụm**. Giả sử ứng dụng có 5 pod, mỗi pod cho 10 message/giây. Tổng throughput có thể lên đến khoảng 50 message/giây, vượt hạn mức provider chỉ 10 message/giây.

### Những cách tổ chức phổ biến

| Cách | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Một mail dispatcher tập trung | Dễ áp dụng rate limit và concurrency toàn cục | Cần high availability và tránh single point of failure |
| Redis-backed rate limiter | Các replica cùng tiêu thụ budget chia sẻ | Cần atomic operations, xử lý Redis outage và độ trễ |
| Broker có consumer được giới hạn | Dễ kiểm soát số consumer, prefetch và pacing | Số consumer không tự bảo đảm message rate |
| Database-based limiter | Có thể dùng hạ tầng database sẵn có | Dễ tạo contention và độ trễ nếu lưu lượng cao |
| API email provider có quota enforcement | Provider tự chặn khi vượt ngưỡng | Ứng dụng vẫn phải tránh đẩy quá nhiều request bị từ chối |

Với Redis, có thể cài fixed-window counter bằng lệnh nguyên tử hoặc Lua script; token bucket phân tán cần cập nhật token và timestamp **nguyên tử**. Đọc giá trị, tính toán ở JVM rồi ghi lại bằng nhiều lệnh không khóa có thể tạo race condition.

### Ví dụ Lua fixed-window giới hạn một khóa

~~~lua
-- KEYS[1]: rate-limit key
-- ARGV[1]: số lần tối đa trong cửa sổ
-- ARGV[2]: thời gian cửa sổ tính bằng mili giây
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return 0
end

current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('PEXPIRE', KEYS[1], windowMs)
end
return 1
~~~

Script trên minh họa một limiter fixed window có tính nguyên tử cho một key, không phải giải pháp production hoàn chỉnh. Cần xử lý valid arguments, TTL, namespace key, quota ngày, quyền truy cập và tình huống Redis không khả dụng. Fixed window vẫn có burst tại ranh giới; nếu provider áp dụng sliding window hoặc giới hạn burst nghiêm ngặt, chọn thuật toán thích hợp hơn.

### Limiter store bị lỗi thì làm gì?

Nếu Redis hoặc limiter service không khả dụng, việc cho tất cả worker gửi không giới hạn có thể lập tức làm quá tải SMTP. Chính sách an toàn thường là:

- **Không vượt quota khi thiếu thông tin điều tiết.**
- Dừng hoặc trì hoãn dispatch, nhưng tiếp tục giữ email bắt buộc trong outbox.
- Báo lỗi hạ tầng và đặt alert.
- Chỉ dùng một fallback rate rất thấp nếu thiết kế đã kiểm chứng rằng nó không thể vượt tổng quota trong tình huống lỗi.

Không nhầm *fail closed đối với việc gửi ngay* với *xóa yêu cầu gửi*. Email vẫn có thể chờ được phục hồi.

## 14. SMTP throttling và phản hồi lỗi tạm thời

Rate limit nên chủ động ngăn quá tải, nhưng hệ thống vẫn phải xử lý phản hồi từ SMTP server. Một số phản hồi thường gặp:

| SMTP code | Ý nghĩa điển hình | Hướng xử lý |
| --- | --- | --- |
| `421` | Dịch vụ tạm thời không sẵn sàng / đóng kênh | Giảm tốc, ngắt kết nối và retry có backoff |
| `450` | Hộp thư tạm không khả dụng | Retry theo chính sách, không nhất thiết là quota |
| `451` | Lỗi cục bộ trong quá trình xử lý | Retry có backoff và theo dõi |
| `452` | Không đủ tài nguyên lưu trữ/hệ thống | Tránh tiếp tục dồn tải, retry sau |
| `4.7.x` enhanced status | Thường liên quan chính sách, security hoặc throttling tùy provider | Xem phản hồi/tài liệu provider |
| `5xx` | Lỗi vĩnh viễn đối với yêu cầu hiện tại | Không retry mù; xử lý nguyên nhân |

**Không phải mọi SMTP 4xx đều là lỗi vượt tốc độ.** Ví dụ mailbox tạm unavailable khác với provider throttling. Hệ thống nên lưu mã lỗi SMTP và enhanced status code nếu có; dựa vào đó và tài liệu provider để quyết định giảm throughput, retry hay xử lý một recipient cụ thể.

### SMTP khác HTTP 429

Khi dùng HTTP email API, server có thể trả `429 Too Many Requests` kèm `Retry-After`. SMTP không có cơ chế header HTTP `Retry-After` tiêu chuẩn trong phản hồi gửi thư. Một SMTP provider có thể ghi thời điểm khuyến nghị thử lại trong text response hoặc tài liệu riêng; ứng dụng cần xử lý theo quy ước của provider, không giả định luôn có một header retry chuẩn.

### Tránh retry storm

Nếu nhiều worker cùng nhận lỗi throttling rồi đồng loạt retry sau đúng 60 giây, hệ thống có thể tạo một đợt burst mới. Cần:

- Exponential backoff và jitter.
- Giảm tốc độ tổng khi phát hiện throttling diện rộng.
- Hạn chế số retry đang chờ và số kết nối.
- Không để retry chiếm toàn bộ budget của email mới quan trọng.
- Dùng một điều khiển tốc độ chung trên toàn cụm.

## 15. Retry cũng phải đi qua rate limiter

Một lỗi phổ biến là chỉ giới hạn email mới, còn email retry được xử lý qua một worker khác không có limiter. Khi SMTP phục hồi, các retry cũ có thể cùng chạy và làm đầy server ngay lập tức.

**Mọi đường gửi ra SMTP cần đi qua cùng chính sách dispatch:** email mới, retry tự động, manual replay, resend và chiến dịch batch.

~~~mermaid
flowchart TD
    A["New outbox records"] --> D["Shared dispatch gate"]
    B["Scheduled retries"] --> D
    C["Manual replay / resend"] --> D
    D --> E["Global + tenant + domain budget"]
    E --> F["Concurrency gate"]
    F --> G["JavaMailSender"]
~~~

Nếu ứng dụng có nhiều provider, có thể có budget riêng cho từng provider và một coordinator phân tuyến theo chính sách. Tránh để fallback provider bị gửi toàn bộ backlog trong một đợt không kiểm soát.

### Retry transient khác replay permanent

- Lỗi tạm thời: lên lịch `nextAttemptAt` và retry tự động.
- Lỗi recipient hoặc cấu hình vĩnh viễn: dừng, ghi FAILED/DEAD_LETTER và đợi sửa nguyên nhân.
- Kết quả SMTP không xác định: có nguy cơ duplicate, cần đối soát trước khi retry theo policy.
- Email đã SUBMITTED: không gửi lại tự động vì `send()` không đồng nghĩa delivered.

Rate limiter điều tiết tốc độ, nhưng không thay thế logic idempotency, trạng thái outbox hoặc phân loại lỗi.

## 16. Thiết kế worker từ outbox tới SMTP

Một worker gửi email không nên claim hàng nghìn record rồi xếp chúng vào memory executor. Nó nên claim một batch nhỏ dựa trên năng lực thực tế và giao lại những bản ghi chưa thể gửi.

### Các trạng thái có thể dùng

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Đã được lưu, chờ gửi |
| PROCESSING | Worker đã claim với lease |
| DEFERRED_RATE | Tạm chờ vì chưa có quota |
| DEFERRED_CAPACITY | Tạm chờ vì hết slot/concurrency |
| RETRY_PENDING | Lỗi SMTP tạm thời, đã lên lịch retry |
| SUBMITTED | SMTP relay đã chấp nhận theo kết quả ứng dụng nhận |
| SUBMISSION_UNKNOWN | Không xác định relay đã nhận hay chưa |
| FAILED_PERMANENT | Lỗi không nên retry mù |
| SUPPRESSED / EXPIRED | Không gửi theo consent hoặc thời hạn |

DEFERRED_RATE/DEFERRED_CAPACITY có thể là trạng thái riêng hoặc chỉ là PENDING với thời điểm thử tiếp, tùy mô hình. **Không tăng failure attempts khi chỉ thiếu token và chưa gọi SMTP**, nếu attempts đại diện cho số lần thực sự thử gửi.

### Pseudocode dispatcher

~~~text
dispatchDueMessages():
    if globalGate.isUnavailable():
        record operational alert
        return

    budget = estimateCapacityForSmallBatch()
    if budget <= 0:
        return

    jobs = outbox.claimDueWithLease(budget)
    for job in jobs:
        if job.expired or job.suppressed:
            update terminal state
            continue

        try:
            mime = renderAndValidate(job)
        catch permanentContentError:
            mark FAILED_PERMANENT
            continue

        if not concurrencyGate.tryEnter():
            releaseClaimAndDefer(job)
            continue

        try:
            if not rateGate.tryAcquire(job.recipientCount):
                releaseClaimAndDefer(job)
                continue

            try:
                smtp.send(mime)
                mark SUBMITTED
            catch temporarySmtpError:
                scheduleRetryWithBackoff(job)
            catch permanentSmtpError:
                mark FAILED_PERMANENT
            catch uncertainSmtpOutcome:
                mark SUBMISSION_UNKNOWN
        finally:
            concurrencyGate.leave()
~~~

Pseudocode tách rõ việc thiếu permit khỏi lỗi SMTP. Với một ứng dụng thật, claim và cập nhật trạng thái cần chạy trong các transaction ngắn, còn SMTP send chạy ngoài transaction. Mỗi lần hoàn tất phải cập nhật đúng record ID/lease owner, tránh worker cũ ghi đè trạng thái của worker mới sau khi lease hết hạn.

### Giới hạn claim batch

Nếu một worker có tối đa 4 lần gửi đồng thời, nó không nên claim 5.000 record mà không có cơ chế kéo dài lease hoặc streaming work phù hợp. Có thể:

- Claim tối đa bằng số slot rảnh cộng một buffer nhỏ.
- Kiểm tra limiter budget trước khi claim, nhưng vẫn xác nhận token bằng thao tác nguyên tử ngay trước gửi.
- Khi không có token, trả record về PENDING với `nextAttemptAt` để tránh polling nóng.
- Giữ lease đủ dài cho thời gian gửi dự kiến và hỗ trợ renew khi cần.

Không dùng một phương thức `@Transactional` bao quanh toàn bộ lần gửi email. Mail server ngoài database không cùng tham gia ACID transaction; việc giữ lock trong lúc chờ mạng vừa tốn tài nguyên vừa không bảo đảm exactly-once.

## 17. Adaptive throttling khi mail server bắt đầu chậm

Hạn mức tĩnh là điểm khởi đầu, nhưng khả năng xử lý của relay có thể thay đổi. Khi queue phía provider tăng hoặc tỷ lệ lỗi throttling cao, có thể giảm tốc độ gửi. Khi hệ thống ổn định lâu dài, có thể tăng lại từ từ trong giới hạn được cấp.

Một ý tưởng điều chỉnh kiểu **AIMD (Additive Increase, Multiplicative Decrease)**:

~~~text
Nếu phát hiện throttling có độ tin cậy cao:
    newRate = max(minRate, currentRate * 0.5)

Nếu ổn định trong nhiều cửa sổ theo dõi:
    newRate = min(configuredMaxRate, currentRate + smallStep)
~~~

Các hệ số chỉ là ví dụ, không phải khuyến nghị cố định. Cần:

- Không vượt quota provider đã xác nhận.
- Dùng cửa sổ quan sát đủ dài để tránh dao động quá nhanh.
- Phân biệt lỗi throttling với lỗi do recipient.
- Có ngưỡng và thời gian ổn định trước khi tăng lại.
- Theo dõi theo provider/account và nhóm recipient thích hợp.
- Không tự tăng vô hạn chỉ vì tạm thời không thấy lỗi.

### Những tín hiệu hữu ích

| Tín hiệu | Điều có thể gợi ý |
| --- | --- |
| Tăng tỷ lệ SMTP 421/4.7.x liên quan throttling | Provider đang yêu cầu giảm tải |
| Thời gian submit tăng | Relay hoặc network có dấu hiệu chậm |
| Số connection timeout tăng | Vấn đề network/capacity |
| Quota remaining giảm | Sắp đạt hạn mức |
| Relay spool/queue tăng | Khả năng giao thư phía sau không theo kịp |
| Tuổi outbox backlog tăng | Năng lực dispatch không theo kịp producer |
| Tỷ lệ bounce/spam complaint tăng | Vấn đề chất lượng lưu lượng, cần xem lại chính sách gửi |

Không tự suy ra rate limit chỉ từ một metric. Ví dụ SMTP 450 có thể liên quan hộp thư cụ thể, không phải toàn bộ provider. Điều chỉnh rate toàn cục từ lỗi một recipient có thể làm chậm các email không liên quan.

### Warm-up và uy tín gửi

Khi một tài khoản/domain/IP mới bắt đầu gửi, việc tăng đột ngột từ vài email đến hàng trăm nghìn email có thể ảnh hưởng deliverability. Nhiều hệ thống áp dụng warm-up: tăng tốc từ từ và theo dõi chất lượng nhận, bounce, complaint và phản hồi từ provider. Đây là vấn đề **uy tín gửi** bên cạnh năng lực kỹ thuật của mail server. Không thể giải quyết bằng cách chỉ tăng số thread.

## 18. Quota theo ngày, cửa sổ và dự phòng cho email thiết yếu

Provider có thể áp dụng hạn mức ngày ngoài hạn mức giây/phút. Một bucket cho message/giây không thể bảo đảm không vượt tổng số message/ngày.

### Quản lý nhiều cấp

~~~text
1. Daily remaining budget?
2. Hourly/minute budget?
3. Per-domain or per-tenant budget?
4. Burst/token budget?
5. SMTP concurrency slot?
6. Submit message
~~~

Đơn vị phải nhất quán. Nếu daily quota tính theo recipient, không dùng message counter làm đại diện. Nếu provider chia quota giữa nhiều tài khoản hoặc service, cần lấy tổng dữ liệu phù hợp.

### Cửa sổ reset

Một hạn mức “mỗi ngày” có thể reset theo UTC, timezone của account hoặc sliding 24 giờ. Không tự giả định reset lúc 00:00 theo giờ của ứng dụng. Khi triển khai Redis key theo ngày, phải dùng đúng định nghĩa cửa sổ của provider hoặc một giới hạn bảo thủ hơn.

### Dự phòng năng lực

Nếu hệ thống gửi cả email giao dịch và marketing, có thể dành một phần quota ngày cho giao dịch. Khi gần hết quota:

- Ngừng tạo chiến dịch marketing mới.
- Tạm dừng newsletter.
- Dành budget còn lại cho OTP và email giao dịch cần thiết.
- Alert để điều chỉnh provider quota hoặc năng lực.

Không coi reserved capacity là quyền được vượt hạn mức toàn cục. Tổng số message/recipient vẫn phải nằm trong quota.

## 19. Giới hạn kích thước và tổng byte khi gửi

Một message có attachment lớn tiêu tốn nhiều băng thông và thời gian SMTP hơn một email text. Nếu rate limiter chỉ tính một token cho mọi message, hệ thống có thể vẫn gây áp lực lớn về network và storage.

Với luồng có attachment, cân nhắc:

- Giới hạn kích thước từng attachment.
- Giới hạn tổng MIME message.
- Giới hạn số attachment.
- Giới hạn tổng byte gửi theo một khoảng thời gian nếu provider yêu cầu.
- Giới hạn concurrency cho message lớn.
- Tách batch báo cáo lớn khỏi email giao dịch nhỏ.

Khi MIME mã hóa binary attachment bằng Base64, kích thước truyền thường tăng khoảng một phần ba, chưa kể header, boundary và line wrapping. Vì vậy, cần để dư dung lượng so với giới hạn message size của provider.

### Weighted permit

Một policy có thể tính permit theo số recipient hoặc kích thước:

~~~java
int messagePermits = 1;
int recipientPermits = message.recipientCount();
long byteBudget = estimatedEncodedSize(message);
~~~

Các giá trị trên thuộc **những ngân sách riêng**, không nhất thiết cộng tất cả thành một số token. Nếu provider đếm message và recipient độc lập, hãy dùng limiter tương ứng cho từng loại quota. Khi kích thước không biết chính xác trước khi serialize, dùng estimate bảo thủ và xác nhận trước submission.

## 20. Circuit breaker khi SMTP mất khả năng phục vụ

Nếu SMTP provider bị outage diện rộng, tiếp tục gọi `send()` với tốc độ tối đa chỉ làm timeout và tốn worker. Một circuit breaker có thể mở khi tỷ lệ lỗi đáng tin cậy tăng, tạm dừng request mới rồi cho phép một số probe có kiểm soát.

~~~text
CLOSED: submit bình thường trong quota
   |
   | lỗi diện rộng vượt ngưỡng
   v
OPEN: không gọi SMTP; giữ outbox và defer
   |
   | sau khoảng nghỉ
   v
HALF_OPEN: một số request thử nghiệm
   |
   +-- thành công ổn định --> CLOSED
   |
   +-- tiếp tục lỗi --------> OPEN
~~~

Circuit breaker không thay thế rate limiter. Khi breaker đóng trở lại, backlog có thể rất lớn; limiter vẫn phải giới hạn tốc độ drain để không tạo thác lũ mới.

### Phân biệt outage với lỗi recipient

Không mở circuit breaker toàn provider vì một địa chỉ nhận bị lỗi 550. Nên dùng tín hiệu lỗi kết nối, lỗi dịch vụ diện rộng, throttling provider và các loại lỗi tương ứng. Một recipient sai phải được xử lý ở mức notification, không làm ngừng mọi email.

### Chọn hành vi khi breaker mở

- Email bắt buộc: giữ trong outbox, cập nhật lịch retry và cảnh báo.
- Email tùy chọn: trì hoãn, hết hạn hoặc suppress theo policy.
- HTTP request: nếu chức năng thật sự cần SMTP tức thời, trả thông báo phù hợp; nếu không, xác nhận công việc đã được xếp hàng.

Không tạo task vô hạn trong memory chỉ để chờ breaker đóng.

## 21. Theo dõi năng lực và backlog

Không có observability thì rate limiter dễ bị cấu hình quá thấp hoặc quá cao mà không ai biết. Nên theo dõi cả **tốc độ sản xuất**, **tốc độ gửi**, **thời gian chờ** và **tình trạng provider**.

| Metric | Ý nghĩa |
| --- | --- |
| `mail_outbox_pending` | Số thông điệp chờ gửi |
| `mail_outbox_oldest_age_seconds` | Tuổi thông điệp chờ lâu nhất |
| `mail_dispatch_attempts_total` | Số lần thử submit |
| `mail_submitted_total` | Số lần SMTP chấp nhận theo phản hồi |
| `mail_rate_limited_total` | Số lần thiếu quota trước khi gửi |
| `mail_concurrency_deferred_total` | Số lần không còn slot |
| `mail_smtp_temp_failures_total` | Lỗi SMTP có thể retry |
| `mail_smtp_perm_failures_total` | Lỗi SMTP vĩnh viễn |
| `mail_smtp_latency_seconds` | Độ trễ submit |
| `mail_inflight_sends` | Số lời gọi send đang hoạt động |
| `mail_retry_pending` | Số record chờ retry |
| `mail_dead_letter_total` | Số record được đưa vào vùng lỗi |
| `mail_rate_configured` | Tốc độ hiện tại theo provider/category |

Tên metric chỉ là ví dụ; có thể triển khai bằng Micrometer/Actuator hoặc hệ thống telemetry hiện có. Nhãn metric nên có cardinality thấp như provider ID, category và nhóm lỗi.

### Đừng đưa dữ liệu người nhận vào metric label

Không dùng full recipient email, notification UUID hoặc subject làm label cho từng time series. Những giá trị này vừa tạo cardinality rất cao vừa có thể làm lộ dữ liệu. Dùng log có correlation ID hoặc hệ thống tracing bảo vệ quyền truy cập để điều tra trường hợp cụ thể.

### Alert nào hữu ích?

- Backlog giao dịch có tuổi vượt SLA.
- Rate-limited count tăng bất thường.
- SMTP temporary failures vượt ngưỡng.
- Hạn mức ngày sắp hết.
- Circuit breaker ở trạng thái OPEN kéo dài.
- Dead-letter tăng nhanh.
- Queue in-memory chạm capacity.
- Độ trễ OTP vượt ngưỡng chấp nhận.

Alert nên xét loại email. Một backlog marketing vài giờ có thể chấp nhận được, trong khi OTP chờ vài phút có thể đã hết giá trị.

## 22. Kiểm thử limiter và điều tiết bất đồng bộ

Kiểm thử cần chứng minh giới hạn thực sự có tác dụng, không chỉ rằng `JavaMailSender` được gọi khi có job.

### Test token bucket trong một JVM

Với một bucket không refill nhanh trong khoảng test:

~~~java
@Test
void rejectsWhenBurstCapacityIsConsumed() {
    InMemoryTokenBucket bucket =
            new InMemoryTokenBucket(2, 0.0001);

    assertTrue(bucket.tryAcquire(1));
    assertTrue(bucket.tryAcquire(1));
    assertFalse(bucket.tryAcquire(1));
}
~~~

Trong test production, nên inject clock/ticker giả để kiểm tra refill và ranh giới thời gian một cách tất định, thay vì phụ thuộc vào `Thread.sleep(...)` hoặc tốc độ máy chạy CI. Test trên chỉ minh họa một tình huống burst capacity.

### Test concurrency bằng công cụ đồng bộ hóa

Có thể dùng `CountDownLatch` và mock sender giữ nhiều task tại điểm gửi, sau đó xác nhận không bao giờ có hơn N task đang chạy đồng thời. Test nên kiểm tra cả nhánh exception để bảo đảm slot được `release()` trong `finally`.

### Test nhiều replica

Limiter in-memory không đủ cho giới hạn toàn cụm. Cần integration test với Redis hoặc limiter store thực:

1. Chạy nhiều worker cùng lấy permit.
2. Bảo đảm tổng số permit được cấp không vượt quota trong cửa sổ.
3. Kiểm tra tình huống một worker chết giữa lúc xử lý.
4. Kiểm tra quota reset/TTL theo đúng thuật toán.
5. Kiểm tra hành vi khi limiter store unavailable.

### Test queue đầy

Với bounded executor, submit nhiều task hơn tổng thread/queue capacity và xác nhận rejection được ghi nhận. Email bắt buộc phải còn trong outbox, không bị mất. Nếu ứng dụng dùng broker, kiểm tra prefetch, consumer concurrency, redelivery và retry behavior.

### Test SMTP throttling

Mock transport hoặc dùng SMTP test server có thể trả phản hồi tạm thời như `421` hoặc `451`. Kiểm tra:

- Message không bị đánh dấu SUBMITTED.
- Retry được lên lịch với backoff.
- Tốc độ có thể bị giảm theo policy nếu là throttling diện rộng.
- Không phát lại đồng loạt sau sự cố.
- Lỗi vĩnh viễn không bị retry vô hạn.

### Test ưu tiên

Tạo backlog marketing lớn, sau đó tạo OTP và xác nhận OTP vẫn được dispatch trong SLA nhờ reserved capacity/priority policy. Kiểm tra thêm fairness để một tenant không chiếm toàn bộ budget của các tenant khác.

## 23. Quy trình triển khai thực tế

Một nhóm phát triển có thể bắt đầu với cấu hình đơn giản rồi mở rộng khi lưu lượng tăng:

1. **Liệt kê các nguồn email**: OTP, giao dịch, thông báo sản phẩm, marketing, replay.
2. **Xác nhận quota provider**: message, recipient, connection, daily và message size.
3. **Chọn SLO/SLA**: thời gian chờ tối đa theo từng category.
4. **Tạo outbox hoặc queue bền vững** để không phụ thuộc memory executor.
5. **Đặt một điểm dispatch chung** qua đó mọi lệnh gửi SMTP phải đi qua.
6. **Áp dụng limiter theo tốc độ** và **giới hạn in-flight**.
7. **Tách budget theo category/tenant**, giữ quota toàn cục.
8. **Giới hạn batch claim và executor queue**, không kéo vô hạn task vào RAM.
9. **Phân loại lỗi SMTP và retry có backoff**, đưa lỗi permanent vào xử lý riêng.
10. **Giảm tốc khi provider throttling** và có chính sách outage/circuit breaker.
11. **Gắn metric, log, alert** cho queue age, rate, error và quota remaining.
12. **Chạy thử với lưu lượng tăng dần**, có thể điều chỉnh cấu hình mà không deploy nếu hệ thống hỗ trợ.

### Bảng quyết định khi phát sinh sự cố

| Hiện tượng | Việc nên làm |
| --- | --- |
| SMTP trả 421/4.7.x do throttling | Giảm throughput, tăng backoff và xem quota provider |
| Nhiều connection timeout | Giảm concurrency, kiểm tra network/relay |
| Outbox tăng liên tục | So sánh tốc độ vào và ra, giới hạn producer tùy chọn, tăng quota hợp lệ hoặc scale đúng bottleneck |
| Queue executor đầy | Giữ job trong outbox, giảm claim và xử lý rejection có chủ đích |
| Marketing làm OTP chậm | Dùng priority/reserved budget, không để một queue FIFO độc chiếm |
| Backlog bùng nổ sau outage | Drain có rate limit, không replay mọi job cùng lúc |
| Nhiều email cùng một recipient | Deduplicate/gộp notification khi nghiệp vụ cho phép |
| Quota ngày gần hết | Dừng chiến dịch tùy chọn, bảo toàn budget cho thông báo thiết yếu |
| Limiter store mất kết nối | Không bypass toàn bộ quota; defer và alert |
| Gửi thành công nhưng mailbox vẫn chậm | Kiểm tra relay queue, provider event và hệ thống nhận; `send()` không chứng minh delivered |

## 24. Những sai lầm thường gặp

### 24.1. Nghĩ @Async tự giới hạn tốc độ

`@Async` chỉ chuyển việc thực thi sang executor. Nếu nhiều task cùng chạy, tốc độ gửi vẫn có thể vượt quota. Kết hợp rate limiter, concurrency gate và executor queue hữu hạn.

### 24.2. Chỉ giới hạn số thread

Ít thread không đồng nghĩa ít email mỗi phút. Đặt budget theo đúng đơn vị provider.

### 24.3. Một rate limiter riêng trên mỗi pod

Tổng tốc độ có thể nhân lên theo số replica. Dùng limiter phân tán hoặc dispatcher tập trung.

### 24.4. Cho phép token bucket burst quá lớn

Bucket capacity quá lớn có thể cho phép dồn hàng trăm lệnh SMTP trong một khoảng ngắn. Giảm burst capacity hoặc dùng pacing khi provider không chấp nhận burst.

### 24.5. Retry không qua limiter

Sau outage, retry có thể đổ dồn vào SMTP. Mọi đường gửi phải qua cùng dispatch gate.

### 24.6. Sleep hàng nghìn thread để đợi quota

Thread bị giữ trong lúc chờ và heap executor đầy. Reschedule trong outbox hoặc để broker giữ công việc.

### 24.7. Claim quá nhiều bản ghi

Worker không có permit vẫn giữ nhiều lease PROCESSING. Chỉ claim batch nhỏ dựa trên năng lực sẵn có.

### 24.8. Xóa email bắt buộc khi queue đầy

Đây là mất thông điệp nghiệp vụ. Giữ yêu cầu trong outbox bền vững, alert và giải quyết capacity.

### 24.9. Không ưu tiên email giao dịch

Marketing chiếm hết quota làm OTP và biên nhận chậm. Áp dụng category budget và fairness.

### 24.10. Coi mọi 4xx là throttling

Một số lỗi 4xx có nguyên nhân recipient/hạ tầng khác. Phân loại theo mã, enhanced status và tài liệu provider.

### 24.11. Dùng HTTP Retry-After cho SMTP

SMTP không có header HTTP `Retry-After` tiêu chuẩn. Chỉ dùng hướng dẫn retry khi provider thật sự công bố.

### 24.12. Mở circuit breaker rồi gửi bù không giới hạn

Sau khi relay phục hồi, backlog có thể rất lớn. Giữ rate limiter và tăng tốc từ từ.

### 24.13. Không đo tuổi backlog

Chỉ đếm số message chờ có thể che giấu email giao dịch bị kẹt quá SLA. Theo dõi oldest age theo category.

### 24.14. Dùng giới hạn message trong khi provider đếm recipient

Một message nhiều người nhận có thể dùng nhiều đơn vị quota. Đếm đúng theo chính sách được cấp.

### 24.15. Gửi thành công nghĩa là đã giao

`JavaMailSender.send()` thường chỉ cho biết SMTP submission thành công. Giao đến mailbox và khả năng hiển thị cần tín hiệu bổ sung từ provider/bounce.

## 25. Câu hỏi tự kiểm tra

**1. Vì sao gửi email bằng @Async chưa đủ để bảo vệ mail server?**

Vì `@Async` chỉ đưa công việc sang executor. Nó không tự giới hạn message/giây, recipient/phút hoặc tổng kết nối SMTP.

**2. Rate limit khác concurrency limit như thế nào?**

Rate limit giới hạn số lần gửi theo thời gian; concurrency limit giới hạn số lời gọi gửi đang hoạt động. Hai cơ chế thường phải kết hợp.

**3. Token bucket cho phép burst ra sao?**

Permit được bổ sung dần và tích tối đa đến capacity. Khi bucket đầy, ứng dụng có thể gửi burst tương ứng, sau đó phải chờ refill.

**4. In-memory limiter có bảo vệ được toàn cụm nhiều replica không?**

Không. Mỗi JVM có bucket riêng nên tổng tốc độ có thể tăng theo số replica. Cần shared limiter hoặc dispatcher tập trung.

**5. Nếu hết token nhưng email là bắt buộc, nên làm gì?**

Giữ yêu cầu trong outbox bền vững, reschedule và theo dõi SLA; không âm thầm xóa email.

**6. Vì sao không nên dùng Thread.sleep() trong hàng nghìn task gửi?**

Nó giữ thread trong khi không làm việc, tăng queue/memory pressure và khó khôi phục qua restart. Dùng `nextAttemptAt` hoặc scheduler.

**7. SMTP 421 có phải luôn do rate limit?**

Không. Đây là lỗi dịch vụ tạm thời không sẵn sàng/đóng kênh; phải xem ngữ cảnh và phản hồi provider.

**8. Có thể bỏ qua rate limiter khi replay email lỗi không?**

Không. Replay là một nguồn phát sinh gửi SMTP và phải qua cùng budget như email mới.

**9. Tại sao cần giới hạn số recipient?**

Vì provider có thể tính quota theo người nhận chứ không chỉ số message. Nhiều recipient trên một email có thể tiêu thụ nhiều quota.

**10. Backpressure giải quyết điều gì?**

Nó giúp producer/dispatcher chậm lại, trì hoãn hoặc từ chối công việc không thiết yếu khi downstream không đủ năng lực, tránh backlog tăng vô hạn.

**11. Đóng circuit breaker rồi mở lại có cần rate limiter không?**

Có. Backlog sau outage có thể rất lớn; nếu gửi bù hết tốc lực, provider có thể quá tải trở lại.

**12. Vì sao nên theo dõi tuổi bản ghi pending thay vì chỉ số lượng?**

Vì một queue nhỏ vẫn có thể chứa email OTP hoặc giao dịch bị kẹt quá SLA.

**13. Rate limiter store không hoạt động có nên cho tất cả worker gửi không?**

Không. Nên defer, alert và giữ outbox, hoặc dùng fallback đã được thiết kế để không thể vượt quota.

**14. Quota hằng ngày và quota mỗi giây có thay thế nhau không?**

Không. Cần đáp ứng đồng thời các cửa sổ và đơn vị quota được provider áp dụng.

## Kết luận

**Giới hạn tốc độ gửi email bất đồng bộ là một cơ chế bảo vệ toàn bộ đường giao thư, không phải chỉ giảm số thread trong ứng dụng.** Hãy xác định quota theo message, recipient, kích thước và kết nối; áp dụng rate limiter cùng concurrency gate ngay trước `JavaMailSender.send(...)`; lưu backlog trong outbox/queue bền vững; và chỉ claim công việc theo năng lực thực tế. Trong hệ thống nhiều replica, cần một ngân sách dùng chung để tổng tốc độ không vượt quota của provider. Retry, manual replay và resend cũng phải qua cùng limiter, kèm backoff và phân loại SMTP 4xx/5xx đúng ngữ cảnh. Khi server quá tải, dùng backpressure, ưu tiên email thiết yếu, theo dõi tuổi backlog và giảm throughput có kiểm soát. **Mục tiêu cuối cùng là giữ mail server ổn định, ngăn hàng đợi tăng vô hạn và vẫn xử lý email quan trọng đúng chính sách mà không đánh mất thông điệp.**
