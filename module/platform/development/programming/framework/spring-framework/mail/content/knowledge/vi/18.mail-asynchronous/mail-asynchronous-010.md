# Executor riêng cho mail và các tác vụ khác

## 1. Vấn đề khi tất cả tác vụ bất đồng bộ dùng chung một executor

Trong **Spring Framework Mail**, gửi email qua `JavaMailSender` thường là một thao tác **I/O có thể chặn thread**. Dù SMTP server hoạt động bình thường, mỗi lần gửi vẫn phải thiết lập hoặc sử dụng kết nối, trao đổi lệnh SMTP, truyền dữ liệu và chờ phản hồi. Nếu server phản hồi chậm, thread gửi mail bị giữ trong thời gian tương ứng.

Ứng dụng Spring còn có thể chạy các việc khác: tạo báo cáo PDF, xuất Excel, cập nhật search index, xử lý ảnh, gửi webhook, đồng bộ dữ liệu hoặc chạy tác vụ nền. Nếu mọi công việc dùng chung một thread pool, chúng tranh giành số thread và dung lượng queue:

~~~text
REST request ─────┐
Order event ──────┤      Một executor dùng chung
Report request ───┼────► [mail][mail][report][mail][image][mail]...
Image task ───────┤               |
Webhook task ─────┘         Số worker hữu hạn
                                  |
                         Các tác vụ chờ nhau
~~~

Giả sử SMTP provider phản hồi chậm trong vài phút. Nhiều mail task đồng thời có thể chiếm hết worker, khiến tác vụ tạo báo cáo phải chờ dù báo cáo không liên quan SMTP. Ngược lại, một đợt tạo báo cáo nặng CPU có thể chiếm pool và làm email thông báo chậm hàng phút.

**Giải pháp là tạo executor riêng cho các nhóm workload có đặc tính và mức ưu tiên khác nhau**, ví dụ:

- `mailTaskExecutor` cho việc gửi email.
- `reportTaskExecutor` cho tác vụ tạo báo cáo.
- `integrationTaskExecutor` cho đồng bộ hoặc webhook nếu cần giới hạn độc lập.

Tách executor là một hình thức **bulkhead isolation**: khi một nhóm công việc chậm hoặc bão hòa, nó không trực tiếp làm cạn toàn bộ thread và queue của nhóm khác. Đây là cách giới hạn ảnh hưởng giữa các loại tác vụ trong cùng ứng dụng.

## 2. Executor riêng giải quyết những gì, không giải quyết những gì?

Một `Executor` trong Java cung cấp cơ chế nhận công việc và thực thi công việc trên thread do nó quản lý. `ThreadPoolTaskExecutor` của Spring bổ sung cấu hình pool, queue, thread naming và tích hợp với hạ tầng `@Async`.

| Mục tiêu | Executor riêng có giúp không? | Giới hạn |
|---|---|---|
| Mail chậm không chiếm hết thread của report | Có | Hai pool vẫn dùng chung CPU, RAM và mạng của process |
| Giới hạn số mail gửi đồng thời | Có | Không tự giới hạn số mail/giây theo quota provider |
| Hạn chế số task đang chờ | Có, khi đặt queue hữu hạn | Phải xử lý khi queue đầy |
| Gán tên thread để quan sát | Có | Cần thêm log/metrics để vận hành |
| Gửi SMTP mà không giữ request thread | Có thể, khi dispatch thật sự bất đồng bộ | Submit vẫn có thể bị từ chối; chi phí xử lý còn tồn tại |
| Bảo đảm email không mất khi ứng dụng restart | Không | Task đang ở queue trong RAM có thể mất |
| Bảo đảm gửi đúng một lần | Không | SMTP acceptance và crash có thể dẫn đến duplicate |
| Truyền nguyên transaction hoặc SecurityContext sang thread mới | Không tự động | Cần thiết kế ranh giới và context propagation |

Điểm dễ nhầm: **executor chỉ quản lý tài nguyên thực thi trong process**, không phải hàng đợi bền vững. Nếu yêu cầu gửi email phải sống sót sau khi process bị kill, cần một cơ chế lưu job bền vững như transactional outbox hoặc message broker, sau đó có thể dùng executor để xử lý các job đã claim.

## 3. Đặc tính workload mail khác report và các tác vụ khác

Không nên cấp cùng số thread và queue cho mọi loại công việc. Hãy xem công việc bị giới hạn bởi tài nguyên nào:

| Workload | Đặc điểm thường gặp | Ràng buộc chính |
|---|---|---|
| Gửi SMTP | Chờ network, provider và timeout | Concurrency SMTP, connection, quota provider |
| Render template đơn giản | CPU nhẹ, thời gian ngắn | CPU/memory, ít cần pool riêng |
| Render PDF lớn | Có thể nặng CPU và memory | CPU cores, heap, file I/O |
| Nén/resize ảnh | Thường nặng CPU và memory | CPU cores, kích thước ảnh |
| Gọi API đối tác | I/O mạng có thể chậm | Timeout, rate limit, số connection |
| Ghi hoặc đọc file lớn | I/O đĩa hoặc object storage | Băng thông, fd, memory |
| Cập nhật search index | I/O và batch/network | Throughput downstream |

Ví dụ, pool dành cho SMTP có thể cần một số thread lớn hơn số CPU cores vì nhiều thread đang chờ mạng. Nhưng pool chạy tác vụ tính toán nặng thường không nên tăng thread tùy ý vì quá nhiều runnable thread gây tranh chấp CPU và heap.

**Executor riêng không đồng nghĩa mỗi loại công việc phải có một pool mới.** Hãy tách theo khác biệt đáng kể về thời gian chạy, mức ưu tiên, SLA, cách retry và rủi ro bão hòa. Tạo hàng chục pool nhỏ không có giới hạn cũng có thể làm cạn tài nguyên process.

## 4. Kiến trúc đề xuất trong Spring

Một thiết kế cơ bản:

~~~mermaid
flowchart TB
    API[REST / Application service] --> MAIL[Mail async gateway]
    API --> REPORT[Report async service]
    MAIL --> ME[mailTaskExecutor]
    REPORT --> RE[reportTaskExecutor]
    ME --> MS[Mail sender adapter]
    MS --> SMTP[SMTP server]
    RE --> PDF[PDF/CSV generator]
    SMTP -.-> LIMIT[Provider latency / quota]
    PDF -.-> CPU[CPU / memory]
~~~

Ý nghĩa:

1. Application service tạo một yêu cầu gửi mail rõ ràng, chứa dữ liệu cần gửi.
2. Mail async gateway được Spring dispatch sang executor của mail.
3. Report service được dispatch sang executor của report, không chia queue với mail.
4. Mỗi executor có chính sách concurrency, queue và rejection riêng.
5. Các tác vụ liên quan HTTP và nghiệp vụ vẫn phải xử lý exception, overload và transaction phù hợp.

Việc tách pool là **tách năng lực thực thi**, không bắt buộc tách hệ thống thành nhiều microservice. Một Spring Boot process vẫn có thể chứa nhiều executor có tên.

## 5. Khai báo hai ThreadPoolTaskExecutor bằng Java configuration

Một ví dụ cho Spring Boot sử dụng Java 17+ và Spring Framework 6:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }

    @Bean(name = "reportTaskExecutor")
    public ThreadPoolTaskExecutor reportTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(40);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
~~~

Các con số **4/8/200** và **2/4/40** chỉ là cấu hình minh họa, không phải thông số tối ưu cho mọi hệ thống. Kích thước thực tế cần được xác định từ thời gian xử lý SMTP, quota, lưu lượng, RAM, CPU và độ trễ cho phép.

### Vai trò của từng tham số

| Tham số | Vai trò |
|---|---|
| `corePoolSize` | Số thread lõi pool duy trì theo chính sách thông thường |
| `maxPoolSize` | Giới hạn số thread tối đa trong pool |
| `queueCapacity` | Số task tối đa đang chờ trong queue của executor |
| `keepAliveSeconds` | Thời gian thread vượt số core được giữ khi idle |
| `threadNamePrefix` | Tiền tố tên thread giúp phân biệt log và thread dump |
| `RejectedExecutionHandler` | Chính sách xử lý khi pool không thể nhận task |
| `waitForTasksToCompleteOnShutdown` | Ảnh hưởng việc chờ xử lý các task khi shutdown |
| `awaitTerminationSeconds` | Thời gian tối đa lifecycle chờ executor kết thúc |

Bean name `mailTaskExecutor` và `reportTaskExecutor` là phần quan trọng để các phương thức dùng `@Async("...")` chọn đúng executor. Không đổi tên bean mà quên cập nhật qualifier tại các điểm sử dụng.

### Cách Spring sử dụng core, queue và max

Với `ThreadPoolTaskExecutor` dựa trên `ThreadPoolExecutor`, khi `queueCapacity > 0`, một luồng hoạt động điển hình là:

1. Nếu số worker còn ít hơn core size, tạo worker để thực thi.
2. Khi các core thread đều bận, task mới được thêm vào queue.
3. Khi queue đầy, pool có thể tăng số worker tới max size.
4. Khi queue đã đầy và số worker đạt max, task mới bị xử lý theo rejection policy.

Do đó, **maxPoolSize không có nghĩa pool lập tức sử dụng số thread tối đa khi bận**. Với queue lớn, nhiều task có thể chờ trước khi pool tăng từ core lên max.

Nếu queue không giới hạn, pool có thể liên tục xếp hàng mà ít hoặc không mở rộng vượt core size. Vì vậy không nên chỉ đặt maxPoolSize rồi mặc định pool sẽ tăng tới max. Cần chọn queue capacity và concurrency đồng thời.

## 6. Chỉ định executor rõ ràng với @Async

Spring dùng `@EnableAsync` để bật cơ chế xử lý các lời gọi `@Async` qua proxy hoặc cơ chế AOP tương ứng. Gắn tên executor trực tiếp vào method:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportAsyncService {
    private final ReportGenerator reportGenerator;

    public ReportAsyncService(ReportGenerator reportGenerator) {
        this.reportGenerator = reportGenerator;
    }

    @Async("reportTaskExecutor")
    public CompletableFuture<ReportResult> generate(
            ReportRequest request) {
        ReportResult result = reportGenerator.create(request);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Với mail service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MailAsyncGateway {
    private final MailSubmissionService submissionService;

    public MailAsyncGateway(
            MailSubmissionService submissionService) {
        this.submissionService = submissionService;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<MailSubmissionResult> submit(
            MailCommand command) {
        MailSubmissionResult result =
                submissionService.submitToSmtp(command);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Ở đây `MailCommand`, `MailSubmissionResult`, `MailSubmissionService`, `ReportRequest` và `ReportGenerator` là các kiểu ứng dụng tự định nghĩa. `submitToSmtp` thực hiện logic xây dựng và gửi message bằng `JavaMailSender` trong thread của mail executor.

Ứng dụng gọi gateway:

~~~java
CompletableFuture<MailSubmissionResult> future =
        mailAsyncGateway.submit(command);

// Lời gọi đã giao task cho executor; kết quả SMTP đến sau.
// Chỉ join/get nếu caller thật sự muốn chờ và xử lý kết quả.
~~~

**Không để một `@Async` không có qualifier vô tình sử dụng executor mặc định khi ứng dụng có nhiều workload.** Tên executor ngay trong annotation làm ranh giới tài nguyên rõ ràng và giúp code dễ kiểm tra.

### @Async không đổi bản chất gửi SMTP

`JavaMailSender.send(...)` trong thread của mail executor vẫn là thao tác I/O có thể block. `@Async` chỉ chuyển phần việc đó khỏi thread gọi vào executor; nó không tự làm SMTP trở thành non-blocking I/O và không tự thêm retry, idempotency hay queue bền vững.

## 7. Ví dụ mail submission service tách khỏi async gateway

Một service gửi SMTP đồng bộ có thể được gọi từ mail executor:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailSubmissionService {
    private final JavaMailSender mailSender;

    public MailSubmissionService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MailSubmissionResult submitToSmtp(
            MailCommand command) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    false,
                    StandardCharsets.UTF_8.name());
            helper.setFrom("notifications@example.test");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(command.html(), true);

            mailSender.send(message);
            return new MailSubmissionResult(command.id(), "SUBMITTED");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot compose MIME mail", ex);
        }
    }
}

public record MailCommand(
        String id,
        String recipient,
        String subject,
        String html) {
}

public record MailSubmissionResult(
        String id,
        String status) {
}
~~~

Đây là ví dụ thiết kế lớp, không phải bộ source nguyên file có thể copy nguyên xi do trong Java mỗi public top-level type thường cần file riêng. Phần `MailCommand` nên là DTO bất biến; có thể chọn các tên class khác tùy ứng dụng.

`mailSender.send(message)` có thể ném các exception thuộc Spring Mail như `MailException` (unchecked). Trong ví dụ, chúng không bị nuốt mà được truyền ra `CompletableFuture` kết quả của gateway. Lỗi tạo message theo `MessagingException` được phân biệt với lỗi SMTP submission.

**Trạng thái SUBMITTED chỉ nên có nghĩa SMTP server đã chấp nhận yêu cầu gửi**, không có nghĩa người nhận đã nhận được vào Inbox hoặc mở email.

## 8. Queue hữu hạn và cơ chế chống quá tải

Tách pool không giúp hệ thống vô hạn năng lực xử lý. Nếu email được tạo nhanh hơn tốc độ gửi trong thời gian dài, queue của mail executor sẽ tăng. Với queue không giới hạn, process có thể giữ ngày càng nhiều task trong heap, làm tăng độ trễ và cuối cùng gặp vấn đề bộ nhớ.

Ví dụ:

~~~text
Luồng yêu cầu mới: 15 mail/giây
Năng lực SMTP thực tế:  5 mail/giây
Chênh lệch:            10 mail/giây

Sau 60 giây, hàng chờ có thể tăng khoảng 600 task
nếu không có giới hạn và không thay đổi lưu lượng.
~~~

Đây chỉ là phép tính minh họa theo giả định throughput ổn định, không phải kết quả đo trên một SMTP provider cụ thể.

Vì vậy nên:

- Đặt `queueCapacity` hữu hạn cho executor xử lý trực tiếp trong bộ nhớ.
- Giới hạn số thread/concurrency để không làm quá tải SMTP provider.
- Đặt timeout để một task không giữ worker vô hạn.
- Có chính sách xử lý khi queue đầy, thay vì chấp nhận mãi.
- Đo thời gian nằm trong queue và số task bị từ chối.
- Với email quan trọng, lưu intent bền vững vào outbox/broker trước khi giao cho executor.

### Executor saturation

Với cấu hình `core=4, max=8, queueCapacity=200`:

~~~text
Các task đến liên tiếp
        |
        v
Tối đa 4 core workers
        |
        v
Tới 200 task trong queue
        |
        v
Pool có thể mở rộng tới 8 workers
        |
        v
Pool và queue đều kín
        |
        v
Task mới bị từ chối theo rejection policy
~~~

Task bị từ chối không có nghĩa SMTP đã thử gửi và thất bại. Nó có nghĩa **executor chưa nhận việc**. Nếu caller bỏ qua sự kiện này, email có thể mất hoàn toàn mà không có SMTP error để điều tra.

## 9. Rejection policy: chọn rõ hành vi khi pool đầy

`ThreadPoolExecutor` của Java cung cấp các rejection handler phổ biến:

| Handler | Khi executor bão hòa | Hệ quả đối với mail |
|---|---|---|
| `AbortPolicy` | Ném exception | Caller biết task chưa được tiếp nhận, có thể ghi trạng thái/chuyển sang outbox |
| `CallerRunsPolicy` | Chạy task ngay trên thread gọi (khi executor chưa shutdown) | Request thread hoặc transaction thread có thể bị block bởi SMTP |
| `DiscardPolicy` | Bỏ task âm thầm | Không phù hợp khi cần biết email nào chưa được gửi |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue rồi thử nhận task mới | Có thể làm mất một email đang chờ |

Với email có ý nghĩa nghiệp vụ, `AbortPolicy` thường dễ kiểm soát hơn vì thất bại nhận task được báo rõ. Trong Spring, lệnh submit bị từ chối có thể xuất hiện dưới dạng `TaskRejectedException`.

~~~java
import org.springframework.core.task.TaskRejectedException;

try {
    mailAsyncGateway.submit(command);
} catch (TaskRejectedException ex) {
    // Executor chưa nhận task.
    // Báo lỗi có kiểm soát hoặc bảo đảm intent vẫn nằm
    // trong outbox / hàng đợi bền vững để thử lại.
    throw ex;
}
~~~

Không nên coi `TaskRejectedException` là lỗi SMTP. Nếu request chưa được lưu bền vững, quyết định trả lỗi hay lưu lại yêu cầu phụ thuộc vào hợp đồng của API. Nếu dùng outbox, việc executor đầy chỉ nên làm job **vẫn ở trạng thái chờ**, không làm mất bản ghi đã commit.

### Vì sao CallerRunsPolicy có thể nguy hiểm?

Giả sử controller gọi `mailAsyncGateway.submit(...)` trong request thread. Khi pool hết chỗ, CallerRunsPolicy có thể thực hiện chính việc gửi SMTP trên request thread. Kết quả:

- HTTP request đột nhiên chậm nhiều giây.
- Thread xử lý web bị cạn trong giờ cao điểm.
- Nếu caller đang ở transaction, SMTP có thể xảy ra trước khi commit.
- SLA và bulkhead isolation ban đầu bị phá vỡ.

CallerRunsPolicy có thể hữu ích cho một số workload cần backpressure đồng bộ, nhưng **không nên chọn máy móc cho gửi SMTP**. Đối với mail, nên thiết kế hành vi overload có chủ đích và theo dõi rejection.

### Không được bỏ qua future bị lỗi

Một phương thức `@Async` trả `CompletableFuture` có thể hoàn tất ở trạng thái thất bại. Caller không xử lý future và chỉ log “queued” sẽ bỏ sót lỗi SMTP về sau.

~~~java
mailAsyncGateway.submit(command)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Ghi metric và correlation ID.
                // Không log toàn bộ nội dung email.
                return;
            }
            // Ghi nhận SMTP submission thành công.
        });
~~~

Callback này phục vụ quan sát và xử lý kết quả, **không thay thế persistent state** khi cần retry qua restart. Nếu callback chạy trong bộ nhớ mà process chết, bản thân callback cũng mất.

## 10. Sizing mail executor theo thời gian I/O và throughput

Không có giá trị core/max duy nhất tốt cho mọi hệ thống. Một cách ước lượng ban đầu là dựa trên:

- `λ`: số email đến trung bình mỗi giây.
- `W`: thời gian một task giữ worker, tính bằng giây.
- `L`: số task đồng thời trung bình cần thiết.

Theo mối liên hệ gần đúng của **Little's Law** trong hệ thống ổn định:

\[
L \approx \lambda \times W
\]

Ví dụ nếu ứng dụng cần xử lý trung bình 6 email/giây và thời gian SMTP submission trung bình là 2 giây:

\[
L \approx 6 \times 2 = 12
\]

Kết quả gợi ý khoảng 12 request đang được xử lý đồng thời trong điều kiện lý tưởng. Đây **không phải công thức tự động đặt maxPoolSize** vì còn phải xét:

- SMTP provider cho phép bao nhiêu kết nối đồng thời.
- Giới hạn rate gửi/phút hoặc gửi/ngày.
- Latency p95/p99 chứ không chỉ trung bình.
- Khả năng thiết lập và reuse SMTP connection.
- Kích thước mỗi email và attachment.
- CPU, memory, network egress của instance.
- Số replica và tổng concurrency của cả cụm.

Ví dụ một SMTP provider chỉ cho phép 5 submission đồng thời, việc đặt 20 worker cho một instance có thể tạo thêm lỗi throttling chứ không làm email gửi nhanh hơn.

### Một pool riêng không phải bộ giới hạn rate

Giới hạn thread chỉ khống chế **số task đang chạy đồng thời**, không bảo đảm tối đa N email/giây. Nếu mỗi SMTP call rất nhanh, một thread có thể gửi nhiều email trong một giây. Khi provider áp dụng quota theo thời gian, cần thêm **rate limiter** ở mail dispatcher hoặc provider adapter.

~~~text
Mail queue
    |
    v
Rate limiter (tốc độ cho phép)
    |
    v
Mail executor (concurrency cho phép)
    |
    v
JavaMailSender / SMTP provider
~~~

Nếu có 4 replica, mỗi replica dùng 8 mail threads thì cụm có thể đồng thời thực thi tới 32 SMTP tasks. Rate limiter cục bộ trên mỗi replica không tự bảo đảm giới hạn toàn cụm; khi có quota chung, cần điều phối theo provider/account hoặc dùng một cơ chế phân phối công việc phù hợp.

### Queue capacity nên gắn với độ trễ chờ cho phép

Nếu hệ thống xử lý ổn định 4 mail/giây và queue có 200 task, một task mới ở cuối queue có thể chờ hàng chục giây trước khi được xử lý, tùy concurrency và thời gian mỗi task. Queue lớn làm giảm rejection nhất thời nhưng tăng latency, không tăng năng lực gửi thực tế.

Nên định nghĩa mục tiêu: “email thông báo nên bắt đầu xử lý trong bao lâu?” rồi đo **queue wait time**, không chọn queueSize theo cảm tính.

## 11. Timeout SMTP là một phần của thiết kế executor

Nếu SMTP connection hoặc thao tác truyền bị treo không có timeout hợp lý, các worker có thể bị giữ rất lâu. Trong Spring Boot, có thể cấu hình các timeout Jakarta Mail như sau:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các giá trị timeout là mili giây và chỉ để minh họa. `connectiontimeout` giới hạn chờ kết nối, `timeout` giới hạn thao tác đọc và `writetimeout` liên quan thao tác ghi. Nên chọn phù hợp với mạng, provider và giới hạn thời gian job.

Timeout không biến SMTP thành exactly-once. Nếu kết nối mất sau khi client đã gửi message body nhưng chưa nhận được phản hồi cuối, việc server đã chấp nhận email hay chưa có thể không rõ. Worker cần trạng thái và chính sách retry phù hợp thay vì mặc định mọi timeout đều an toàn để gửi lại.

**Không dùng một mail executor lớn để che việc chưa cấu hình timeout.** Khi provider gặp sự cố, số thread lớn chỉ làm nhiều thread bị treo hơn.

## 12. Hai cấp backpressure: trước và sau khi nhận việc

Cần phân biệt:

1. **Admission control:** executor hoặc hệ thống nhận bao nhiêu task mới.
2. **Dispatch control:** worker gửi bao nhiêu message đồng thời hoặc theo thời gian.

Nếu task chưa được lưu bền vững, admission failure phải được trả về caller hoặc xử lý theo nghiệp vụ. Nếu dùng outbox, việc nhận request có thể kết thúc sau khi outbox record commit, còn dispatcher chỉ nhận số lượng job mà executor có khả năng xử lý:

~~~text
HTTP request
     |
     v
DB transaction: business data + mail outbox
     |
     v
COMMIT thành công
     |
     v
Outbox records (bền vững)
     |
     v
Poll/claim theo capacity còn trống
     |
     v
mailTaskExecutor
     |
     v
SMTP submission
~~~

**Đừng claim hàng nghìn record rồi submit vào queue executor chỉ có vài trăm chỗ.** Nếu task bị từ chối sau khi claim, phải trả record về trạng thái chờ/đến hạn hoặc để lease hết hạn theo cơ chế đã thiết kế. Một cách tốt hơn là dispatcher tính toán số slot xử lý được, rồi claim batch phù hợp.

Khi cả outbox backlog và SMTP bị chậm, hệ thống vẫn tiếp nhận ý định gửi qua database (theo năng lực lưu trữ), nhưng các worker không cần làm process nổ tung vì vô hạn task trong RAM.

## 13. Những điều kiện để @Async thật sự chạy trên executor đã chọn

`@Async` thường được Spring áp dụng qua proxy. Vì vậy cần lưu ý **cách gọi method**, không chỉ chỗ đặt annotation.

### Gọi qua Spring-managed bean

Ví dụ đúng:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationFacade {
    private final MailAsyncGateway mailAsyncGateway;

    public OrderNotificationFacade(
            MailAsyncGateway mailAsyncGateway) {
        this.mailAsyncGateway = mailAsyncGateway;
    }

    public void requestWelcomeEmail(MailCommand command) {
        mailAsyncGateway.submit(command);
    }
}
~~~

`OrderNotificationFacade` gọi một bean khác là `MailAsyncGateway`, do đó lời gọi đi qua proxy của Spring và được dispatch theo `@Async("mailTaskExecutor")`.

Ví dụ **không nên**:

~~~java
@Service
public class WrongMailService {

    public void execute(MailCommand command) {
        sendAsync(command); // self-invocation
    }

    @Async("mailTaskExecutor")
    public void sendAsync(MailCommand command) {
        // Có thể vẫn chạy ngay trên caller thread.
    }
}
~~~

Trong chế độ proxy mặc định, lời gọi nội bộ cùng object không đi qua proxy nên annotation có thể không có tác dụng. Đưa async method sang một Spring bean khác và gọi qua bean đó.

### Các bẫy khác

- Không giả định `@Async` trên `private` method sẽ được Spring intercept ở proxy mode.
- Không gọi async method bằng `new MailAsyncGateway(...)` rồi mong Spring tự inject executor.
- Không dựa vào lời gọi trong constructor để kích hoạt proxy AOP đã hoàn tất.
- Không để `@Async` không có executor qualifier trong hệ thống có nhiều bean executor và mong nó tự chọn đúng pool.
- Không truyền object mutable còn đang được caller chỉnh sửa sau khi submit; thread mail có thể đọc ở thời điểm khác.
- Không gọi `join()` ngay trong HTTP request nếu mục tiêu là giải phóng request thread; việc chờ future có thể khiến request vẫn block.

### Dùng Executor trực tiếp thay vì @Async

Không phải use case nào cũng cần annotation. Có thể inject đúng executor theo qualifier và dispatch:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class MailTaskDispatcher {
    private final TaskExecutor mailExecutor;
    private final MailSubmissionService submissionService;

    public MailTaskDispatcher(
            @Qualifier("mailTaskExecutor") TaskExecutor mailExecutor,
            MailSubmissionService submissionService) {
        this.mailExecutor = mailExecutor;
        this.submissionService = submissionService;
    }

    public void dispatch(MailCommand command) {
        mailExecutor.execute(
                () -> submissionService.submitToSmtp(command));
    }
}
~~~

Cách này hữu ích khi cần điều phối batch, claim outbox, hoặc muốn nhận/catch lỗi submit một cách trực tiếp. Tuy nhiên, khi dùng `execute(Runnable)`, exception xảy ra **sau khi task bắt đầu chạy** không quay lại caller như lỗi ném đồng bộ. Task phải có cơ chế xử lý lỗi/ghi trạng thái riêng.

## 14. Ranh giới transaction: không để async mail chạy trước commit

Một sai lầm phổ biến là gọi `@Async` ngay trong một method `@Transactional`:

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailAsyncGateway.submit(buildMailCommand(order));
}
~~~

Lệnh submit có thể đưa task vào mail executor **trước khi transaction database commit**. Thread mail có thể gửi thông báo khi dữ liệu vẫn đang chưa được commit; nếu transaction rollback sau đó, người nhận có email xác nhận cho một đơn hàng không tồn tại.

Ngoài ra, transaction của thread caller **không tự được truyền sang thread executor**. `@Transactional` dùng context gắn với thread hoặc cơ chế transaction tương ứng. Không nên giả định worker mail có thể đọc dữ liệu chưa commit của caller hoặc dùng chung persistence context.

### Hướng A: event sau commit cho mail best-effort

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCommittedMailListener {
    private final MailSubmissionService mailService;

    public OrderCommittedMailListener(
            MailSubmissionService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCommitted event) {
        mailService.submitToSmtp(event.mailCommand());
    }
}
~~~

Application service publish event khi đang trong transaction:

~~~java
@Transactional
public UUID placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    eventPublisher.publishEvent(
            new OrderCommitted(buildImmutableMailCommand(order)));
    return order.getId();
}
~~~

Handler AFTER_COMMIT được kích hoạt sau khi transaction commit; `@Async` chuyển việc xử lý sang mail executor. Cách này tránh gửi trước commit nhưng event chỉ ở bộ nhớ process: ứng dụng có thể chết ngay sau commit, task có thể bị reject hoặc mất khi restart. Do đó phù hợp **best-effort**, không phải bảo đảm bền vững.

### Hướng B: transactional outbox cho mail cần bền vững

~~~text
@Transactional application service
    |
    +--> save order
    |
    +--> insert mail_outbox record
    |
    v
COMMIT
    |
    v
Outbox poller / queue consumer
    |
    v
mailTaskExecutor (concurrency bounded)
    |
    v
JavaMailSender.send
    |
    v
Update outbox state
~~~

Trong kiến trúc này, **executor vẫn hữu ích** để giới hạn concurrency SMTP, nhưng **outbox** mới là cơ chế giữ yêu cầu gửi qua restart.

Outbox dispatcher không nên claim lượng job vượt năng lực xử lý còn trống. Cần tách transaction claim khỏi SMTP call, dùng lease, timeout và state transition rõ ràng. Nếu pool từ chối nhận task, job phải được giữ ở trạng thái có thể retry, không coi là SMTP submission thất bại.

### Không dùng @Async để “mở” transaction khác mà không hiểu mục tiêu

Khi một method `@Async` có `@Transactional`, transaction của nó có thể bắt đầu trong worker thread thông qua proxy Spring. Điều đó **không làm nó tham gia transaction caller**. Nếu muốn ghi outbox atomic cùng order, việc insert outbox phải xảy ra trong transaction nghiệp vụ ban đầu, không đưa insert đó sang async thread.

## 15. Exception handling khác nhau cho void và CompletableFuture

Một async method có thể trả `void`, `Future` hoặc `CompletableFuture`. Cách xử lý exception khác nhau:

### CompletableFuture

~~~java
CompletableFuture<MailSubmissionResult> submitted =
        mailAsyncGateway.submit(command);

submitted.whenComplete((result, error) -> {
    if (error != null) {
        metrics.recordMailSubmissionFailure();
        return;
    }
    metrics.recordMailSubmissionSuccess();
});
~~~

Nếu SMTP call lỗi trong worker, future có thể hoàn tất exceptionally để caller xử lý. Chỉ có future không đồng nghĩa có retry bền vững; nếu process chết, future mất theo process.

### Method trả void

~~~java
@Async("mailTaskExecutor")
public void submitWithoutResult(MailCommand command) {
    submissionService.submitToSmtp(command);
}
~~~

Caller không nhận được future để quan sát lỗi. Với Spring `@Async`, các exception không được bắt trong `void` async method có thể được chuyển tới `AsyncUncaughtExceptionHandler`.

Có thể cấu hình handler:

~~~java
import java.lang.reflect.Method;
import java.util.concurrent.Executor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler
    getAsyncUncaughtExceptionHandler() {
        return (throwable, method, params) -> {
            // Ghi metric, loại lỗi và định danh an toàn.
            // Không tự động log toàn bộ params: có thể chứa PII.
        };
    }
}
~~~

Handler minh họa trên không gọi lại tác vụ. Trong thực tế, cần ghi log/metric hữu ích; với tác vụ bền vững, trạng thái retry phải được quản lý qua outbox hoặc job store.

Đối với giao dịch quan trọng, kiểu trả kết quả rõ ràng và pipeline quản lý trạng thái thường dễ kiểm soát hơn một `void @Async` “fire-and-forget”. Nếu chọn `void`, phải chủ động thiết kế đường đi của failure.

## 16. Context propagation: MDC, SecurityContext, locale

Vì mail task chạy trên thread khác, thông tin gắn với thread gọi **không tự đi theo task**. Ví dụ:

- MDC chứa request ID hoặc correlation ID.
- Spring SecurityContext chứa thông tin xác thực.
- LocaleContext hoặc tenant context.
- TransactionSynchronizationManager và persistence context.

Không nên dựa vào `ThreadLocal` của HTTP request khi render/gửi email trong worker thread. Cách bền vững nhất là đưa các giá trị cần thiết vào **MailCommand bất biến**: recipient, locale, tenant ID, event ID, template ID và dữ liệu nội dung được phép gửi.

### TaskDecorator để chuyển MDC phục vụ logging

Nếu hệ thống cần giữ correlation ID qua executor, có thể dùng `TaskDecorator`:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcCopyingTaskDecorator
        implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                delegate.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Gắn decorator vào executor trước `initialize()`:

~~~java
executor.setTaskDecorator(new MdcCopyingTaskDecorator());
~~~

Đoạn code sao chép MDC tại thời điểm submit, thiết lập trên worker rồi **khôi phục trạng thái trước đó** ở finally. Việc khôi phục đặc biệt quan trọng vì thread pool tái sử dụng thread, tránh correlation ID của task trước bị rò sang task sau.

Nếu cần chuyển security context, có thể xem các executor wrapper hỗ trợ `DelegatingSecurityContextAsyncTaskExecutor` của Spring Security. Tuy nhiên, **không nên chuyển toàn bộ quyền người dùng sang background task một cách máy móc**. Worker nên dùng quyền service tối thiểu cần thiết và kiểm tra tenant/authorization tại ranh giới nghiệp vụ. Transaction context không được sao chép sang thread mới.

### Lưu ý tenant và locale

Nếu ứng dụng đa tenant, nên ghi rõ tenant ID và locale trong request/outbox payload. Đừng phụ thuộc vào biến ThreadLocal của request khi job chạy vài phút sau. Worker đọc đúng tenant, template và cấu hình sender; dùng `Locale` cụ thể thay vì locale mặc định ngẫu nhiên của worker thread.

## 17. Quan sát từng executor riêng biệt

Một lợi ích lớn của việc tách pool là có thể biết chính xác workload nào đang gây tải:

~~~text
mailTaskExecutor
    activeThreads = 8
    poolSize      = 8
    queuedTasks   = 200
    rejectedTasks tăng

reportTaskExecutor
    activeThreads = 1
    poolSize      = 2
    queuedTasks   = 0
~~~

Trong ví dụ, mail pool đã gần hoặc ở trạng thái bão hòa, nhưng report pool vẫn còn khả năng thực thi. Nếu chỉ dùng một pool chung, dashboard khó cho biết mail hay report là nguồn gây ra độ trễ.

### Các metric nên theo dõi

| Metric | Ý nghĩa | Gợi ý cảnh báo |
|---|---|---|
| Active threads | Số worker đang bận | Liên tục sát max pool |
| Pool size | Tổng worker đã tạo | Pool luôn cần mở tới max |
| Queue size | Task đang chờ | Hàng đợi lớn và liên tục tăng |
| Queue wait duration | Thời gian từ submit tới bắt đầu chạy | p95/p99 vượt SLA |
| Task execution duration | Thời gian một task giữ thread | SMTP latency tăng |
| Rejection count | Task không được nhận | Xuất hiện đột biến hoặc kéo dài |
| Submission success/failure | Kết quả gửi | Thất bại tăng theo provider |
| SMTP timeout count | Số lần timeout | Tăng sau sự cố mạng/provider |
| Outbox backlog age | Tuổi job chờ bền vững | Worker không theo kịp |

`ThreadPoolTaskExecutor` cung cấp một số giá trị runtime để quan sát. Ví dụ:

~~~java
ThreadPoolTaskExecutor mailExecutor = ...;

int active = mailExecutor.getActiveCount();
int poolSize = mailExecutor.getPoolSize();
int queued = mailExecutor.getThreadPoolExecutor()
        .getQueue()
        .size();
~~~

Đây là thao tác quan sát trong code; cách xuất metric cụ thể có thể dùng Micrometer/Actuator hoặc công cụ monitoring khác mà ứng dụng đang dùng. Nên đặt tag như `executor=mail` và `executor=report`. Tránh gắn tag theo recipient hoặc subject vì cardinality cao và làm lộ dữ liệu.

### Queue size không phải toàn bộ backlog

Trong hệ thống dùng outbox, **backlog thực tế** bao gồm cả record đang chờ trong database và task đã được claim/đưa vào executor. Nếu chỉ xem queue size bằng 0, chưa thể kết luận không có email chờ: worker có thể đang chết, không poll hoặc bị pause.

Nên quan sát cả:

~~~text
outbox_pending / outbox_retry
    +
executor_queue
    +
executor_active
    +
smtp_inflight
~~~

Các thành phần có thể trùng nhau tùy trạng thái claim và mô hình đo, vì vậy **không cộng mù các metric để coi là số email duy nhất**. Hãy thống nhất định nghĩa metric và status lifecycle để tránh double count.

## 18. Graceful shutdown không thay thế lưu trữ bền vững

Khi ứng dụng nhận tín hiệu shutdown, Spring có thể cho executor dừng nhận task mới, chờ task đang chạy hoặc xử lý những task còn trong queue theo cấu hình lifecycle.

Hai cấu hình thường được dùng:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Ý nghĩa:

- Cố gắng cho các task đã được executor nhận hoàn tất theo chính sách shutdown.
- Chờ tối đa một khoảng thời gian khi Spring đóng application context.

**Những giá trị này không bảo đảm task hoàn tất nếu process bị kill, máy mất điện hoặc container bị dừng cưỡng bức.** Một request gửi mail chỉ được lưu trong RAM có thể mất. Ngoài ra, thời gian chờ của executor phải phù hợp grace period của orchestrator hoặc container runtime.

Khi có outbox:

1. Dừng claim thêm job mới khi ứng dụng đang shutdown.
2. Cho task đang gửi hoàn tất trong khoảng grace period hợp lý.
3. Update trạng thái trong database nếu có kết quả.
4. Những record chưa hoàn tất sẽ được worker khác hoặc process mới claim lại khi lease hết hạn.

Nếu SMTP đã accepted nhưng state update chưa kịp commit, retry có thể tạo email trùng. Graceful shutdown giảm xác suất nhưng không loại bỏ hoàn toàn crash window.

### Không dùng thread daemon để “đỡ phải chờ”

Đặt worker threads thành daemon chỉ khiến JVM có thể thoát mà không chờ chúng hoàn tất; điều này không phù hợp với yêu cầu gửi mail quan trọng. Hãy kiểm soát lifecycle, timeout và job persistence, không cố giải quyết vấn đề bằng cách bỏ trách nhiệm hoàn tất task.

## 19. Kiểm thử mail executor và report executor tách biệt

Phần kiểm thử nên tách ba mục tiêu:

1. **Dispatch đúng executor**: mail chạy trên thread có prefix mail, report chạy trên thread có prefix report.
2. **Không tranh chấp cùng queue**: khi mail pool bận, report vẫn có thể nhận task trong pool của nó, với điều kiện process còn đủ tài nguyên.
3. **Hành vi khi quá tải**: queue đầy dẫn đến rejection được xử lý đúng, không mất job một cách âm thầm.

### Test @Async chọn đúng executor

Có thể dùng Spring Test với một probe tối giản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        AsyncExecutorConfiguration.class,
        AsyncDispatchTest.TestBeans.class
})
class AsyncDispatchTest {
    @Autowired
    private Probe probe;

    @Test
    void runsMailAndReportOnDifferentExecutors() {
        String mailThread = probe.mailThread().join();
        String reportThread = probe.reportThread().join();

        assertThat(mailThread).startsWith("mail-");
        assertThat(reportThread).startsWith("report-");
    }

    @Configuration
    static class TestBeans {
        @Bean
        Probe probe() {
            return new Probe();
        }
    }

    static class Probe {
        @Async("mailTaskExecutor")
        public CompletableFuture<String> mailThread() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }

        @Async("reportTaskExecutor")
        public CompletableFuture<String> reportThread() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }
}
~~~

Test cần chạy trong Spring context có `@EnableAsync`; ở đây annotation nằm trong `AsyncExecutorConfiguration`. Không gọi `new Probe()` trực tiếp trong test vì như vậy bỏ qua proxy. Prefix thread là tín hiệu dễ đọc, nhưng nếu ứng dụng tùy chỉnh naming thì assertion cần thay theo cấu hình.

### Test rejection của executor đơn lẻ

Có thể dựng executor nhỏ với một worker và queue không có chỗ chờ:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorOverloadTest {
    @Test
    void rejectsWhenSingleWorkerIsBusy() throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(0);
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.initialize();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();

            assertThatThrownBy(() -> pool.execute(() -> {
                // Executor đang đầy: task này bị từ chối.
            })).isInstanceOf(TaskRejectedException.class);
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
~~~

Test minh họa cơ chế overload của pool, **không liên hệ SMTP**. Trong test thực, nên có timeout cho latch để test không treo vô hạn nếu worker không chạy vì sự cố. Khi cần kiểm tra nhiều executor không ảnh hưởng nhau, có thể chạy một mail task chờ latch và đồng thời gửi report task vào report pool, sau đó assert report hoàn tất trong giới hạn mong đợi.

### Test lỗi gửi SMTP

Một test mail gateway có thể dùng mock `MailSubmissionService` cho ném `MailSendException` và assert `CompletableFuture` hoàn tất exceptionally. Việc verify lời gọi mock chỉ chứng minh wiring và error propagation, **không chứng minh SMTP transaction thực tế**. Để kiểm tra giao thức, dùng SMTP test server với cấu hình local/test phù hợp.

### Test transaction boundary

Một test quan trọng là làm rollback transaction sau khi tạo event/request gửi, sau đó xác nhận mail không được submit. Với outbox, xác nhận cả business data và outbox record rollback cùng nhau. Đây là integration test ở database/transaction layer; không đủ nếu chỉ mock repository.

## 20. Cấu hình qua properties thay vì hardcode

Khi vận hành nhiều môi trường, có thể đặt các tham số executor trong cấu hình riêng của ứng dụng:

~~~yaml
app:
  async:
    mail:
      core-size: 4
      max-size: 8
      queue-capacity: 200
      shutdown-wait-seconds: 30
    report:
      core-size: 2
      max-size: 4
      queue-capacity: 40
      shutdown-wait-seconds: 30
~~~

Đây là **namespace cấu hình tự định nghĩa**, không phải các thuộc tính được Spring Boot tự gắn cho hai executor chỉ vì có tiền tố `app.async`. Cần dùng `@ConfigurationProperties` hoặc cơ chế bind tương đương để đọc giá trị và cấu hình các bean.

Ví dụ bind giá trị kiểu record trong Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.async.mail")
public record MailExecutorProperties(
        int coreSize,
        int maxSize,
        int queueCapacity,
        int shutdownWaitSeconds) {
}
~~~

Sau đó đăng ký `@EnableConfigurationProperties(MailExecutorProperties.class)` hoặc cấu hình scanning phù hợp và inject properties vào bean factory. Cần validate:

- `coreSize` là số dương.
- `maxSize >= coreSize`.
- `queueCapacity >= 0`.
- Shutdown wait không âm.
- Tổng concurrency theo replica không vượt khả năng downstream/provider.

Không nên cho phép cấu hình sản xuất vô tình đặt queue capacity cực lớn hoặc `maxPoolSize` quá cao mà không có giới hạn bộ nhớ và connection tương ứng.

## 21. Tách scheduler khỏi executor gửi SMTP

Trong hệ thống có outbox, thường có một scheduler đánh thức dispatcher để lấy job từ database:

~~~java
@Scheduled(fixedDelay = 1000)
public void pollMailOutbox() {
    dispatcher.claimAndDispatchReadyMails();
}
~~~

Scheduler **không nhất thiết là worker gửi SMTP**. Nó nên thực hiện công việc ngắn: xác định năng lực còn trống, claim số record phù hợp và giao cho mail executor. Nếu để scheduler trực tiếp gửi nhiều email đồng bộ, scheduler có thể bị chiếm trong thời gian dài và không kịp chạy các job hẹn giờ khác.

~~~text
Scheduler thread
      |
      v
Outbox dispatcher (claim batch ngắn)
      |
      v
mailTaskExecutor
      |
      +-- SMTP task 1
      +-- SMTP task 2
      +-- SMTP task 3

report scheduler
      |
      v
reportTaskExecutor
      |
      +-- Report task 1
~~~

Nếu ứng dụng có nhiều scheduled tasks cần cách ly, có thể cấu hình `TaskScheduler` riêng hoặc scheduler pool phù hợp. **`TaskScheduler` và `TaskExecutor` là hai trách nhiệm khác nhau**: scheduler quyết định *khi nào chạy*, executor quyết định *task chạy trên nguồn lực nào*. Không nên mặc định cấu hình mailTaskExecutor sẽ tự thay thế scheduler của `@Scheduled`.

### Tránh poller tạo quá nhiều tác vụ

Ngay cả khi mail executor có queue hữu hạn, một poller chạy quá nhanh có thể liên tục claim job và làm queue đầy. Các chiến lược:

- Poll theo tốc độ xử lý quan sát được, không chỉ theo khoảng thời gian cố định.
- Chỉ claim khi mail executor còn capacity.
- Dùng batch size nhỏ và tăng/giảm theo backlog, độ trễ SMTP.
- Khi overload, ngừng claim tạm thời thay vì làm record chuyển qua CLAIMED rồi để lease hết hạn vô ích.
- Có trạng thái retry hợp lý nếu submission task không được executor nhận.

Khi cần đồng bộ hoá claim và executor capacity trong nhiều replica, có thể chọn cơ chế điều phối ở database/broker thay vì chỉ nhìn queue cục bộ.

## 22. Một số lựa chọn thay ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` phù hợp cho nhiều ứng dụng Spring có blocking I/O. Tuy nhiên, nó không phải công cụ duy nhất.

### ExecutorService của Java

Java `ExecutorService`, ví dụ `ThreadPoolExecutor`, có thể được dùng trực tiếp. Spring `ThreadPoolTaskExecutor` thường thuận tiện hơn khi cần lifecycle bean, `TaskDecorator`, `@Async` và các giá trị quan sát tích hợp.

### Virtual threads trên Java 21+

Java 21 có **virtual threads**, phù hợp để giảm chi phí quản lý nhiều blocking operations so với mỗi tác vụ giữ một platform thread. Spring ở các phiên bản hỗ trợ có thể dùng các executor khởi chạy virtual thread.

Tuy nhiên:

- Virtual thread không làm SMTP server nhận email nhanh hơn.
- Không tự giới hạn tổng số kết nối hoặc tốc độ gửi.
- Không phải queue bền vững và không thay transactional outbox.
- Vẫn cần timeout, admission control, quota và giới hạn số submission đồng thời.
- Cần xem xét thư viện, tài nguyên bị pinning và đặc tính của runtime thực tế.

Nếu chọn virtual threads, việc tách workload mail/report ở **mức chính sách concurrency, queue/dispatcher, rate limit và quan sát** vẫn quan trọng, ngay cả khi mô hình thread khác với pool truyền thống. Không vì virtual threads rẻ hơn mà cho phép vô hạn tác vụ đồng thời gọi cùng SMTP provider.

### Broker và worker service riêng

Nếu hệ thống có lưu lượng lớn, nhiều tenant hoặc yêu cầu bảo đảm bền vững, có thể tách mail dispatcher thành một process/service riêng đọc outbox/broker. Cách này cung cấp mức cô lập tốt hơn thread pool vì CPU, heap và deployment có thể độc lập.

Mặt khác, thêm service, broker và CI/CD riêng cũng tăng chi phí vận hành. Đối với một monolith Spring có lưu lượng vừa phải, **executor riêng trong cùng process + outbox khi cần** thường là một điểm khởi đầu hợp lý.

## 23. Những anti-pattern thường gặp

### Dùng chung một @Async executor cho mọi việc

Khi SMTP provider chậm, các tác vụ report hoặc xử lý ảnh có thể bị starvation. Tách pool theo workload và ưu tiên, đồng thời quan sát từng queue.

### Tạo executor mới cho mỗi email

~~~java
// Không nên tạo một thread pool mới cho từng mail.
ExecutorService executor = Executors.newFixedThreadPool(4);
executor.submit(() -> mailSender.send(message));
~~~

Mỗi executor có thread, queue và lifecycle riêng. Tạo pool theo request dễ làm cạn tài nguyên và khó shutdown. Hãy dùng **Spring bean singleton** quản lý executor dùng chung cho workload mail.

### @Async không qualifier trong ứng dụng có nhiều executor

Không giả định Spring luôn chọn đúng một pool khi có nhiều bean. Dùng `@Async("mailTaskExecutor")` hoặc inject `@Qualifier("mailTaskExecutor")` để nêu rõ ý định.

### Queue không giới hạn

Task backlog trong RAM có thể tăng mãi trong lúc SMTP bị gián đoạn, dẫn tới latency lớn hoặc OOM. Đặt queue hữu hạn, backpressure và lưu ý định gửi bền vững nếu cần.

### Tăng maxPoolSize để “sửa” provider chậm

Khi provider throttling hoặc connection timeout, nhiều thread hơn có thể gây thêm lỗi. Cần quan sát latency, response code, provider quota, connection limit và rate limiter trước khi tăng concurrency.

### CallerRunsPolicy trên HTTP transaction thread

Pool đầy có thể khiến SMTP chạy trực tiếp trên caller thread, làm request chậm hoặc email gửi trước database commit. Chọn rejection policy theo hợp đồng nghiệp vụ, không chỉ vì muốn “không mất task”.

### Bỏ qua lỗi của CompletableFuture

Việc method trả về nhanh không phải bằng chứng gửi thành công. Future có thể hoàn tất exceptionally hoặc task có thể bị reject khi submit. Theo dõi cả lỗi admission và lỗi SMTP runtime.

### Dựa vào @Async để bảo đảm email không mất

Queue trong RAM bị mất khi process crash. Dùng outbox hoặc broker nếu phải giữ mail intent qua restart.

### Truyền Entity hoặc Request object mutable sang worker

JPA entity có thể lazy-load sau khi transaction caller đã kết thúc; HTTP request/security context cũng có vòng đời khác. Tạo DTO bất biến chứa dữ liệu cần thiết và định danh an toàn.

### Copy mọi ThreadLocal một cách máy móc

Chuyển toàn bộ SecurityContext hoặc tenant context mà không đánh giá quyền có thể tạo rủi ro. Chỉ đưa thông tin cần thiết vào task; dùng context propagation có kiểm soát, cleanup và quyền tối thiểu.

### Không tính tổng concurrency toàn cụm

Mỗi replica có maxPoolSize 8, nhưng 10 replica có thể tạo tối đa 80 submission đồng thời. Tính quota và resource theo **toàn cụm**, không chỉ theo một JVM.

### Dùng chung pool với tác vụ scheduled chạy lâu

Một scheduled task tạo report hoặc gửi mail đồng bộ có thể giữ scheduler thread làm các lịch khác trễ. Để scheduler điều phối ngắn và chuyển phần việc nặng sang executor thích hợp.

## 24. Checklist triển khai executor riêng cho mail

### Thiết kế

1. Phân loại workload theo I/O, CPU, độ trễ và mức ưu tiên.
2. Xác định mail có cần được lưu bền vững trước khi dispatch hay không.
3. Tạo ít nhất một mail executor riêng nếu SMTP latency có thể ảnh hưởng các task khác.
4. Đặt bean name và qualifier rõ ràng cho từng `@Async`.
5. Đặt concurrency/queue hữu hạn; xác định chính sách rejection.
6. Đặt timeout SMTP phù hợp và giới hạn tốc độ theo provider.

### Ranh giới nghiệp vụ

7. Không gọi mail executor trước database commit nếu email phản ánh giao dịch đã commit.
8. Dùng AFTER_COMMIT cho best-effort hoặc outbox/broker khi cần khôi phục.
9. Truyền DTO bất biến và các thông tin cần thiết như locale/tenant/event ID.
10. Có chính sách xử lý exception, retry và kết quả submission không chắc chắn.

### Vận hành

11. Theo dõi queue wait, active threads, rejection, SMTP duration và backlog.
12. Cấu hình graceful shutdown nhưng không coi nó là durable persistence.
13. Đo tác động của nhiều replica lên quota SMTP toàn cụm.
14. Test dispatch qua Spring proxy, overload, transaction boundary và shutdown/restart.
15. Chỉ tăng thread/queue sau khi có dữ liệu từ monitoring và kiểm tra giới hạn downstream.

## 25. Tổng kết

Trong Spring Framework Mail, **executor riêng cho mail** giúp cách ly việc gửi SMTP khỏi các workload khác như tạo báo cáo, xử lý ảnh hoặc gọi API đối tác. Với `ThreadPoolTaskExecutor`, hãy cấu hình bean riêng, đặt `@Async("mailTaskExecutor")` cho mail và `@Async("reportTaskExecutor")` cho report. Thiết kế pool cần đồng thời xét core threads, max threads, queue capacity, rejection policy và timeout SMTP.

Điều quan trọng không chỉ là chạy bất đồng bộ, mà là **kiểm soát năng lực tiếp nhận và xử lý**:

- Task gửi mail đã được nhận vào executor chưa?
- Queue có tăng và vượt độ trễ mục tiêu không?
- SMTP provider có giới hạn concurrency/rate không?
- Lỗi async được đưa về caller, metric hoặc job store thế nào?
- Email có thể bị mất nếu process restart không?
- Việc gửi có xảy ra trước transaction commit không?

**Tách pool để chống tranh chấp tài nguyên; dùng backpressure để chống quá tải; dùng transaction/outbox để giữ đúng nghiệp vụ và độ bền.** Ba trách nhiệm này bổ sung nhau nhưng không thay thế cho nhau.
