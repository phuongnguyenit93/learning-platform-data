# Backpressure ở queue gửi mail

Trong ứng dụng **Spring Framework Mail**, chuyển việc gửi email sang một hàng đợi giúp HTTP request không phải chờ `JavaMailSender.send(...)`. Tuy nhiên, thêm queue không tự giải quyết vấn đề hiệu năng. Nếu ứng dụng tạo email nhanh hơn khả năng gửi của SMTP provider, số job chờ sẽ tăng liên tục. Khi bộ nhớ, dung lượng lưu trữ hoặc hạn mức nhà cung cấp bị vượt, hệ thống có thể bị nghẽn, trễ email quan trọng, phát sinh retry ồ ạt và cuối cùng làm chậm cả những nghiệp vụ không liên quan đến mail.

**Backpressure** là cơ chế báo hoặc áp dụng giới hạn khi bên tiêu thụ không theo kịp bên sản xuất. Trong mail pipeline, mục tiêu là giữ lượng công việc chưa xử lý trong mức có thể kiểm soát, bảo vệ SMTP provider, bảo vệ tài nguyên ứng dụng và duy trì hành vi rõ ràng khi quá tải.

Một nguyên tắc quan trọng:

> **Queue hấp thụ chênh lệch tải trong một khoảng thời gian; backpressure quyết định hệ thống làm gì khi chênh lệch đó kéo dài.**

Bài học trình bày các nguồn gây nghẽn, cách tính năng lực gửi, lựa chọn queue bounded và admission control, cấu hình `ThreadPoolTaskExecutor` cho `@Async`, kiểm soát worker với queue/outbox bền vững, rate limit theo SMTP route, retry có backoff, công bằng giữa tenant/loại thư, quan sát bằng metric và kiểm thử khi hệ thống quá tải.

## 1. Backpressure trong hệ thống gửi mail nghĩa là gì?

Một email có thể đi qua chuỗi:

```text
HTTP / Business event / Scheduler
              |
              v
      Create mail request
              |
              v
       Queue / Outbox
              |
              v
           Workers
              |
              v
       Render + MIME build
              |
              v
     JavaMailSender.send(...)
              |
              v
       SMTP provider
              |
              v
      Downstream delivery
```

Producer là thành phần tạo nhu cầu gửi. Consumer là worker xử lý job và submit tới SMTP. **Backpressure** xuất hiện khi consumer hoặc provider không thể xử lý với tốc độ producer tạo job.

Ví dụ:

- Một chiến dịch tạo 20.000 email trong vài phút.
- SMTP provider chỉ chấp nhận một số lượng submission nhất định mỗi giây.
- Ảnh inline và attachment lớn khiến mỗi lần gửi mất lâu hơn.
- Một mạng lỗi làm thời gian kết nối SMTP tăng từ vài trăm millisecond lên vài giây.
- Provider phản hồi tạm thời bằng mã 4xx hoặc áp dụng throttling.
- Worker bị restart hoặc không claim được job từ database.
- Một tenant gửi khối lượng quá lớn, khiến email của tenant khác bị chậm.

Nếu không có backpressure, các tầng có thể tiếp tục tạo thêm job trong khi backlog đã vượt khả năng xử lý.

### Backpressure không phải chỉ là retry

**Retry** là cách thử lại một công việc thất bại. **Backpressure** là cách giới hạn tốc độ tạo, nhận hoặc thực hiện công việc để hệ thống không quá tải. Retry thiếu kiểm soát còn có thể *làm tình trạng nghẽn nặng hơn*, vì những job thất bại tiếp tục quay lại queue.

### Backpressure không có nghĩa luôn từ chối email

Tùy kiến trúc, phản ứng với quá tải có thể là:

1. **Giảm tốc producer** trong phạm vi an toàn.
2. **Trì hoãn việc nhận thêm** và trả thông tin quá tải.
3. **Lưu bền vững rồi hẹn xử lý sau** nếu storage còn dung lượng.
4. **Giới hạn số worker/SMTP connections** để không vượt quota.
5. **Ưu tiên hoặc phân làn** cho email khẩn cấp.
6. **Từ chối công việc mới** theo chính sách có thể giải thích.
7. **Dừng một nhóm gửi không quan trọng** cho tới khi backlog giảm.

Không nên mặc định “đã có queue thì nhận vô hạn”. Hàng đợi vô hạn chỉ dời điểm lỗi sang bộ nhớ, database, broker hoặc provider.

## 2. Phân biệt giới hạn ở từng tầng

Mail pipeline có nhiều tài nguyên hữu hạn:

| Tầng | Giới hạn thường gặp | Hậu quả nếu vượt |
|---|---|---|
| HTTP ingress | Request threads, connection pool, rate limit | Request trễ hoặc bị từ chối |
| Template rendering | CPU, heap, cache, dữ liệu đầu vào | Render chậm, heap pressure |
| MIME/attachment | Bộ nhớ, file descriptor, I/O | OOM, đọc file chậm, attachment lỗi |
| In-memory executor | Threads, queue capacity | `TaskRejectedException`, mất việc khi process chết |
| Database outbox | Disk, write throughput, index, locking | Transaction chậm, storage đầy |
| Message broker | Queue depth, disk, unacked messages | Broker quá tải, consumer lag |
| SMTP transport | Connections, network, TLS handshakes | Timeout, socket exhaustion |
| SMTP provider | Messages/s, recipient/s, quota theo giờ/ngày | 4xx throttling, block hoặc suspension |
| Receiving systems | Recipient/domain rate, reputation | Deferral/bounce, delivery chậm |

Backpressure phải dựa trên **điểm nghẽn thật**, không chỉ số lượng thread. Nếu SMTP provider giới hạn 10 message/s, tăng từ 5 lên 100 worker không làm hạn mức đó biến mất. Nó có thể tạo thêm kết nối, gây throttling, khiến retry và queue dài hơn.

### Một câu hỏi thiết kế then chốt

Khi API nói “đã nhận yêu cầu gửi email”, hệ thống đã làm điều gì?

- Chỉ thêm `Runnable` vào queue RAM?
- Đã commit một bản ghi outbox?
- Broker đã xác nhận publish bền vững?
- Worker đã bắt đầu attempt?
- SMTP đã chấp nhận message?

Mỗi mốc có độ tin cậy khác nhau. Backpressure cần giữ **hợp đồng chấp nhận yêu cầu** rõ ràng khi queue đầy hoặc provider đang lỗi.

## 3. Tính toán tốc độ vào và năng lực xử lý

Dùng hai đại lượng:

- \(\lambda\): tốc độ tạo mail job, tính theo message/giây.
- \(\mu\): năng lực xử lý mail job, tính theo message/giây.

Nếu hệ thống ở trạng thái ổn định và trung bình \(\lambda < \mu\), backlog có cơ hội giảm sau các burst. Nếu \(\lambda > \mu\) liên tục, backlog tăng xấp xỉ theo chênh lệch giữa hai tốc độ.

\[
\Delta Q \approx (\lambda-\mu)\cdot \Delta t
\]

trong đó \(Q\) là số job đang chờ và công thức chỉ là ước lượng khi các tốc độ tương đối ổn định.

### Ví dụ năng lực không đủ

Giả sử:

- Hệ thống tạo trung bình **30 email/giây**.
- Mỗi worker xử lý được **2 email/giây**.
- Có **10 worker**.

Khi chưa xét giới hạn khác, năng lực danh nghĩa:

\[
\mu = 10 \times 2 = 20\ \text{email/giây}
\]

Backlog tăng khoảng **10 email/giây**. Sau 10 phút:

\[
Q \approx 10 \times 600 = 6000\ \text{email}
\]

Nếu không giảm tốc producer hoặc mở rộng năng lực thực, queue sẽ tiếp tục lớn lên.

Tuy nhiên, nếu provider chỉ cho phép **15 email/giây**, dù thêm worker, năng lực hữu dụng có thể bị chặn ở 15 email/giây. Vì vậy phải xét đồng thời worker, network và quota provider.

### Little's Law và độ trễ hàng đợi

Khi hệ thống có trạng thái ổn định, Little's Law mô tả:

\[
L = \lambda \times W
\]

với \(L\) là số công việc trung bình trong hệ thống, \(\lambda\) là throughput thực tế và \(W\) là thời gian công việc nằm trong hệ thống.

Ví dụ hệ thống xử lý ổn định 10 email/giây, mỗi job mất trung bình 5 giây từ lúc vào đến lúc hoàn tất. Số job trung bình đang tồn tại trong hệ thống xấp xỉ 50.

**Không dùng Little's Law để khẳng định một queue đang tăng vô hạn có thời gian chờ ổn định.** Khi producer liên tục nhanh hơn consumer, độ trễ có xu hướng tăng theo backlog.

### Đo thay vì suy đoán

Các con số cần đo ở môi trường thật:

- Arrival rate theo notification type.
- SMTP attempts per second và accepted rate.
- P50/p95/p99 thời gian một attempt.
- Queue wait latency và tuổi job chờ lâu nhất.
- Số kết nối SMTP đồng thời.
- Provider throttling/4xx rate.
- Kích thước message trung bình và phân phối attachment size.

Chọn giới hạn queue/concurrency từ các phép đo này, không chỉ từ số CPU core.

## 4. Hệ thống cần một ngân sách backlog

Queue có thể được dùng để hấp thụ burst ngắn. Nhưng hệ thống cần quyết định trước **backlog tối đa** và **độ trễ tối đa chấp nhận được**.

Ví dụ:

| Nhóm email | Mục tiêu vận hành minh họa | Hướng chính sách |
|---|---|---|
| OTP/đăng nhập | Rất nhạy với độ trễ; token có thời hạn | Luồng ưu tiên, quota riêng, không cho chờ quá lâu |
| Reset password | Ưu tiên, cần chống abuse | Admission và rate limit theo tài khoản/IP, thời hạn rõ |
| Xác nhận đơn hàng | Có thể chờ ngắn, cần đáng tin cậy | Outbox bền vững, retry có giới hạn |
| Báo cáo định kỳ | Có thể chờ vài phút hoặc lâu hơn | Queue theo batch, concurrency/rate limit |
| Marketing/newsletter | Khối lượng lớn, không nên chiếm lane giao dịch | Queue/budget riêng, schedule, suppression |

Các thời gian trong hệ thống thật phải đến từ SLA, yêu cầu bảo mật và năng lực provider; bảng chỉ thể hiện cách phân loại.

Một job có TTL nghiệp vụ không nên bị gửi sau khi hết ý nghĩa. Ví dụ OTP hết hạn sau vài phút nhưng nằm trong queue vài chục phút: gửi nó ra có thể gây nhầm lẫn. Khi xử lý, worker cần xác định policy **expire/cancel**, ghi trạng thái phù hợp, không chỉ gửi mọi job còn trong queue.

### Bounded backlog và admission

Khi độ sâu queue vượt ngưỡng, có thể giảm/từ chối loại email có mức ưu tiên thấp. Với loại giao dịch quan trọng, trước hết cân nhắc capacity reservation hoặc route khác đã được phê duyệt thay vì bỏ job.

Không được ngầm “drop” email quan trọng rồi trả API thành công. Nếu một yêu cầu bị từ chối, trả trạng thái/exception rõ; nếu được lưu bền vững, lưu ID để truy vấn và retry.

## 5. Queue trong bộ nhớ và queue bền vững khác nhau

Hai thiết kế phổ biến:

### 5.1. `@Async` với ThreadPoolTaskExecutor

```text
Caller -> executor queue (RAM) -> worker -> SMTP
```

Ưu điểm:

- Dễ cấu hình.
- Không cần broker.
- Phù hợp email ít quan trọng, tải thấp và chấp nhận mất task khi process chết.

Giới hạn:

- Queue biến mất khi process dừng bất ngờ.
- Caller có thể chỉ biết task được nhận vào RAM.
- Khi queue đầy, executor phải từ chối hoặc áp dụng rejection policy.
- Mở nhiều replica tạo nhiều queue và concurrency riêng, khó quản lý quota SMTP toàn cục.

### 5.2. Database outbox hoặc broker bền vững

```text
Business transaction -> outbox/broker -> workers -> SMTP
```

Ưu điểm:

- Ý định gửi có thể tồn tại qua restart nếu được commit/publish bền vững.
- Có trạng thái, retry schedule và khả năng điều tra.
- Worker có thể điều tiết tốc độ độc lập với API.
- Có thể giám sát backlog và phục hồi sau sự cố.

Giới hạn:

- Database hoặc broker cũng có sức chứa hữu hạn.
- Cần claim, ack, retry, lease và xử lý trùng.
- Một job được lưu bền vững vẫn có thể chờ rất lâu nếu capacity thiếu.
- Có rủi ro timeout sau SMTP accepted nhưng trước khi commit trạng thái.

**Queue bền vững không đồng nghĩa queue vô hạn.** Phải áp dụng admission, retention, capacity và xử lý sự cố storage.

## 6. Bounded ThreadPoolTaskExecutor trong Spring

`ThreadPoolTaskExecutor` thường được dùng với `@Async`. Ví dụ:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailExecutorConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mail-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(25);

        return executor;
    }
}
```

Các giá trị chỉ để minh họa. Khi sử dụng:

| Cấu hình | Ý nghĩa |
|---|---|
| `corePoolSize` | Số worker core được quản lý theo pool |
| `maxPoolSize` | Số worker tối đa khi pool được mở rộng |
| `queueCapacity` | Số task chờ tối đa trong executor |
| `RejectedExecutionHandler` | Quy tắc khi không thể nhận task |
| `threadNamePrefix` | Hỗ trợ quan sát và debug |
| `waitForTasksToCompleteOnShutdown` | Chính sách drain task khi shutdown |
| `awaitTerminationSeconds` | Thời gian đợi executor kết thúc |

### Điểm dễ nhầm: maxPoolSize không luôn được dùng trước

Với kiểu queue dương thường dùng trong `ThreadPoolTaskExecutor`, pool thường:

1. Tạo worker tới `corePoolSize`.
2. Đưa task tiếp theo vào queue.
3. Khi queue đầy, mới mở rộng số worker tối đa tới `maxPoolSize`.
4. Sau đó từ chối nếu không còn capacity.

Do đó `corePoolSize=4, maxPoolSize=8, queueCapacity=10000` không có nghĩa hệ thống thường xuyên dùng 8 worker. Nó có thể giữ 4 worker và tích nhiều task trong hàng đợi rất lớn, làm tăng thời gian chờ.

**Chọn queue capacity là một quyết định về độ trễ và backpressure**, không chỉ về bộ nhớ.

## 7. Rejection policy là một phần của hợp đồng API

Khi executor đã đầy, `ThreadPoolTaskExecutor` có thể phát sinh `TaskRejectedException`. Ứng dụng phải quyết định điều đó có ý nghĩa gì cho caller.

Những policy thường thấy trong Java:

| Policy | Hành vi khái quát | Rủi ro đối với mail |
|---|---|---|
| `AbortPolicy` | Từ chối bằng exception | Cần xử lý và trả kết quả rõ, không nuốt lỗi |
| `CallerRunsPolicy` | Chạy task trên thread gọi khi pool bận và chưa shutdown | Có thể biến HTTP request thành gửi SMTP đồng bộ, gây trễ dây chuyền |
| `DiscardPolicy` | Bỏ task mà không báo lỗi | Có thể mất email âm thầm |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue để thử thêm task mới | Có thể làm mất mail quan trọng, sai thứ tự |
| Custom rejection handler | Theo chính sách ứng dụng | Phải bảo đảm không làm mất công việc đã được báo nhận |

### Vì sao CallerRunsPolicy cần đặc biệt thận trọng?

`CallerRunsPolicy` tạo backpressure bằng cách làm chậm producer: khi queue đầy, thread submit tự chạy task. Điều này đôi khi phù hợp với pipeline tính toán nội bộ.

Nhưng nếu thread submit là HTTP request thread và task gọi `JavaMailSender.send`, request có thể bất ngờ phải chờ SMTP. Với nhiều request đồng thời, điều đó làm cạn request threads, dù mục tiêu ban đầu của `@Async` là không block.

Ngoài ra, khi executor đã shutdown, `CallerRunsPolicy` có thể **không chạy task**. Vì thế nó không thích hợp làm đảm bảo duy nhất rằng một yêu cầu gửi mail được lưu lại.

### Vì sao DiscardPolicy đặc biệt nguy hiểm?

Một API có thể trả `202 Accepted` sau khi submit vào executor nhưng task đã bị drop. Caller tưởng yêu cầu được chấp nhận trong khi không có job bền vững nào để retry.

Với email quan trọng, nên dùng cách **từ chối rõ ràng** hoặc **ghi outbox trước rồi dispatch best-effort**, thay vì bỏ task im lặng.

## 8. Xử lý TaskRejectedException mà không nói dối caller

Ví dụ dịch vụ submit trực tiếp vào executor:

```java
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class InMemoryMailSubmissionService {

    private final ThreadPoolTaskExecutor mailExecutor;
    private final MailWorker worker;

    public InMemoryMailSubmissionService(
            ThreadPoolTaskExecutor mailExecutor,
            MailWorker worker
    ) {
        this.mailExecutor = mailExecutor;
        this.worker = worker;
    }

    public void submit(MailCommand command) {
        try {
            mailExecutor.execute(() -> worker.send(command));
        } catch (TaskRejectedException exception) {
            throw new MailCapacityExceededException(
                    "Mail executor is full",
                    exception
            );
        }
    }
}
```

`MailCommand`, `MailWorker` và `MailCapacityExceededException` là thành phần do ứng dụng định nghĩa.

Nếu caller là HTTP endpoint, có thể ánh xạ lỗi quá tải thành mã phản hồi phù hợp như `429 Too Many Requests` hoặc `503 Service Unavailable` theo hợp đồng API, kèm thông tin retry khi hợp lý. Không khẳng định “đã gửi thành công” hoặc “đã vào queue” nếu executor từ chối.

### Hai vấn đề vẫn còn

1. Executor chấp nhận task nhưng process chết trước khi chạy: task trong RAM có thể mất.
2. Request đã nhận task nhưng SMTP lỗi sau khi request trả về: caller không tự biết kết quả.

Vì vậy giải pháp này chỉ phù hợp khi yêu cầu độ bền công việc thấp. Với email giao dịch cần bảo đảm ý định gửi, hãy lưu outbox trước.

## 9. Outbox làm ranh giới chấp nhận yêu cầu bền vững

Một mô hình tốt cho nghiệp vụ quan trọng:

```text
HTTP request / domain event
             |
             v
    Database transaction
       ├── Save business data
       └── Insert mail outbox(PENDING)
             |
             v
           Commit
             |
             v
       Return receipt
             |
             v
   Background poller / worker
             |
             v
       SMTP submission
```

Điểm cộng của outbox là người dùng có thể nhận **notification ID** sau khi commit, còn worker được phép gửi sau. Nếu worker tạm thời quá tải, notification vẫn nằm ở `PENDING` thay vì biến mất.

### Bounded admission ở tầng outbox

Outbox có thể từ chối request mới khi hệ thống chạm giới hạn:

- Số `PENDING` toàn hệ thống.
- Số `PENDING` theo loại mail hoặc tenant.
- Tổng dung lượng payload/attachment cần lưu.
- Tuổi backlog lớn hơn SLO.
- Database disk/latency vượt ngưỡng vận hành.
- Provider quota không thể đáp ứng thời hạn nghiệp vụ.

Admission check không nên là `SELECT COUNT(*)` rồi `INSERT` thuần túy nếu cần **giới hạn cứng dưới concurrency**, vì hai transaction có thể cùng thấy chỗ trống rồi cùng insert. Với giới hạn cứng, cần cơ chế giữ quota/slot nguyên tử hoặc transaction/locking phù hợp.

Trong thực tế, có thể dùng ngưỡng mềm cho cảnh báo sớm và một cơ chế admission đủ chặt để không vượt tài nguyên tối đa.

## 10. Dispatch best-effort sau khi đã commit outbox

Một thiết kế có thể dùng executor như một tín hiệu “xử lý sớm”, nhưng **outbox vẫn là nguồn sự thật**.

```java
public MailReceipt requestMail(MailCommand command) {
    // Hàm này phải commit việc lưu notification
    // trước khi trả về.
    MailJob job = outboxService.createPending(command);

    try {
        mailExecutor.execute(
                () -> mailWorker.processById(job.id())
        );
    } catch (TaskRejectedException rejected) {
        // Không xóa job và không giả định đã gửi.
        // Poller định kỳ vẫn có thể nhặt job PENDING.
        log.info(
                "Mail dispatch saturated; outbox job remains pending"
        );
    }

    return new MailReceipt(job.id(), "QUEUED");
}
```

Các kiểu và phương thức trên chỉ là mô hình minh họa. Trong triển khai thật, cần đảm bảo:

- `createPending` thực sự commit trước khi dispatch, nếu gọi trong một transaction lớn thì có thể dispatch quá sớm.
- `processById` thực hiện claim có khóa hoặc cơ chế chống xử lý đồng thời.
- Poller định kỳ phục hồi các job chưa được executor xử lý.
- Trạng thái `QUEUED` nghĩa là outbox đã commit, **không phải SMTP đã chấp nhận**.
- Không tăng `mail.message.created` thêm lần nữa khi cùng job được retry.

### Khi executor đầy, đừng cố “cứu” bằng recursion

Không nên viết:

```java
try {
    mailExecutor.execute(task);
} catch (TaskRejectedException rejected) {
    // Không nên: lập tức gọi lại vô hạn trong cùng request.
    submitAgain(task);
}
```

Cách này có thể làm nghẽn CPU hoặc thread, không giải quyết được capacity. Nếu job đã bền vững, cứ để poller/worker xử lý khi còn năng lực. Nếu chưa bền vững, từ chối rõ ràng thay vì vòng lặp không có điểm dừng.

## 11. Không claim job nhiều hơn khả năng worker xử lý

Với database outbox, worker thường poll theo batch. Một sai lầm là claim 10.000 job, đánh dấu chúng là `PROCESSING` rồi mới xếp vào một executor có queue 100 task.

Khi executor đầy:

- Nhiều job đã bị claim nhưng chưa chạy.
- Lease có thể hết hạn trước khi SMTP bắt đầu.
- Worker khác có thể claim lại và gửi trùng.
- Job trông như đang xử lý nhưng thực tế chỉ nằm trong một hàng đợi RAM khác.

Một nguyên tắc:

> **Số job đã claim và chưa hoàn tất nên phù hợp với số slot xử lý, queue buffer nhỏ và chính sách lease.**

Cách triển khai có thể:

1. Tính số worker slot đang rảnh.
2. Chỉ claim tương ứng số job phù hợp.
3. Nếu không có slot hoặc provider không còn quota, không claim thêm.
4. Chỉ giữ lease khi job thực sự tiến hành xử lý.
5. Hoàn tất/ghi kết quả trước khi release slot.
6. Khi shutdown, dừng claim trước khi đợi in-flight.

### Claim với locking

Trên database hỗ trợ, worker có thể dùng kỹ thuật khóa hàng, ví dụ `SELECT ... FOR UPDATE SKIP LOCKED`, kết hợp transaction claim và cập nhật state.

Đây là kỹ thuật tùy hệ quản trị cơ sở dữ liệu; cú pháp, isolation và hiệu năng khác nhau. Không được xem một câu SELECT đơn lẻ là đủ bảo đảm ownership nếu transaction và update không được thiết kế nhất quán.

Cần có `claimToken` hoặc một dạng fencing/version check nếu lease có thể hết hạn và worker cũ vẫn còn chạy.

## 12. Semaphore giới hạn số attempt đang chạy

Ngoài queue bounded, có thể dùng `Semaphore` để giới hạn số lần gửi SMTP đồng thời của **một instance**.

Ví dụ:

```java
import java.util.concurrent.Semaphore;
import org.springframework.mail.javamail.JavaMailSender;

public final class LimitedSmtpGateway {

    private final JavaMailSender sender;
    private final Semaphore permits = new Semaphore(4);

    public LimitedSmtpGateway(JavaMailSender sender) {
        this.sender = sender;
    }

    public boolean trySend(MimeMessage message) {
        if (!permits.tryAcquire()) {
            // Caller phải giữ job PENDING hoặc hẹn xử lý sau.
            return false;
        }

        try {
            sender.send(message);
            return true;
        } finally {
            permits.release();
        }
    }
}
```

Trong ví dụ, `false` có nghĩa **không giành được slot để bắt đầu**, không phải SMTP đã từ chối message. Với ứng dụng thật, tránh dùng một boolean duy nhất cho accepted, failed và not-admitted; nên tách kết quả admission khỏi outcome của `send`.

### Semaphore không thay rate limit

Giới hạn 4 kết nối đồng thời không có nghĩa chỉ gửi 4 email/giây. Nếu mỗi email hoàn thành trong 100 ms, bốn slot có thể tạo nhiều attempt trong một giây.

Do đó cần phân biệt:

- **Concurrency limit:** số attempt đang chạy cùng lúc.
- **Rate limit:** số attempt được phép khởi động trong một đơn vị thời gian.
- **Quota limit:** tổng số email/recipient/byte được phép theo giờ hoặc ngày.
- **Backlog limit:** số job đang đợi được chấp nhận.

Nhiều hệ thống cần kết hợp cả bốn.

## 13. Rate limiting theo SMTP provider và route

SMTP provider thường có hạn mức. Nếu mỗi replica tự gửi ở tốc độ tối đa, tổng traffic có thể vượt quota chung.

Ví dụ:

```text
Provider allows 20 submissions/second

Replica A  -> 15/s
Replica B  -> 15/s
Replica C  -> 15/s
---------------------
Total      -> 45/s (over quota)
```

Một limiter chỉ nằm trong RAM của mỗi instance không giải quyết quota **toàn hệ thống**.

### Token bucket

Một cơ chế phổ biến là **token bucket**:

- Bucket chứa tối đa một số token.
- Token được bổ sung theo tốc độ cho phép.
- Mỗi submission tiêu thụ token theo chính sách.
- Khi hết token, job được chờ hoặc hẹn chạy sau.
- Burst ngắn có thể được hấp thụ tới dung lượng bucket.

```text
Provider budget
    |
    v
Token bucket
    |
    +-- token available --> worker may submit
    |
    +-- no token --------> keep job pending / reschedule
```

Ví dụ logic ở mức service:

```java
public void processOne(MailJob job) {
    if (!quotaLimiter.tryAcquire(job.smtpRoute())) {
        outboxRepository.deferUntil(
                job.id(),
                quotaLimiter.nextAvailableTime(job.smtpRoute())
        );
        return;
    }

    smtpGateway.send(job);
}
```

`quotaLimiter` và `outboxRepository` là thành phần minh họa. Trong production, cần xử lý **atomic quota allocation**, claim ownership, deadline và việc token bị giữ nhưng attempt không bắt đầu.

### Quota phân tán

Nếu nhiều instance cùng dùng một provider limit, có thể chọn:

- Một worker pool tập trung quản lý route.
- Token bucket dùng storage/coordination chia sẻ.
- Broker partition hoặc consumer group có giới hạn concurrency.
- Dịch vụ gateway chuyên gửi mail, chịu trách nhiệm rate limiting.
- Phân chia quota tĩnh mỗi replica khi số replica ổn định và có dự phòng.

Không dùng phép cộng “mỗi instance 20/s” nếu provider chỉ cho tổng 20/s. Khi autoscaling, phải điều chỉnh limit per-instance hoặc dùng cơ chế quota phối hợp.

## 14. Provider throttling là tín hiệu backpressure từ phía ngoài

Khi SMTP server trả phản hồi tạm thời, chẳng hạn nhóm 4xx, đó có thể là tín hiệu provider đang quá tải hoặc áp dụng rate/policy limit.

Các phản hồi như `421`, `451` hoặc `4.7.x` có thể liên quan tới tạm thời không khả dụng hoặc throttling, nhưng ý nghĩa cụ thể phụ thuộc server và mã mở rộng.

Không nên phản ứng bằng cách:

```text
4xx -> retry immediately -> 4xx -> retry immediately -> ...
```

Thay vào đó:

1. Phân loại lỗi từ SMTP response và cause chain.
2. Nếu provider công bố thời gian retry, áp dụng hướng dẫn đó khi phù hợp.
3. Giảm tốc route tương ứng.
4. Dùng exponential backoff với jitter và giới hạn số attempt.
5. Giữ notification trong storage bền vững.
6. Quan sát tốc độ accepted, 4xx, queue age và provider quota.
7. Khôi phục tốc độ từ từ khi provider ổn định.

**Không coi mọi mã 4xx là throttling.** Có thể là lỗi tạm thời ở recipient hoặc network. Phân loại đúng giúp không làm chậm cả route do một lỗi riêng lẻ.

## 15. Retry storm và tác động lên backlog

Một lỗi phổ biến khi dùng queue:

```text
Producer generates 100 jobs/s
          |
          v
Provider slows down
          |
          v
Workers fail 80 jobs/s
          |
          v
Immediate retry adds 80 jobs/s
          |
          v
Total effective demand = original + retries
          |
          v
Queue and provider overloaded further
```

Nếu retry tăng nhanh, tốc độ tạo **attempt** có thể vượt xa tốc độ tạo **logical notification**. Dashboard nhìn thấy nhiều lần gửi nhưng số thông báo mới không tăng tương ứng.

### Backoff theo attempt

Một lịch minh họa:

```text
Attempt 1 fails -> wait about 30 seconds
Attempt 2 fails -> wait about 60 seconds
Attempt 3 fails -> wait about 120 seconds
Attempt 4 fails -> stop or escalate by policy
```

Các giá trị không phải mặc định Spring Mail. Dùng jitter để tránh mọi worker retry đúng cùng một thời điểm sau khi provider phục hồi.

Ví dụ công thức:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

trong đó \(d_n\) là thời gian backoff nền và \(d_{\max}\) là giới hạn. Sau đó áp dụng jitter theo chính sách.

### Retry có deadline nghiệp vụ

Một số email không còn giá trị nếu gửi trễ:

- OTP hết hạn.
- Link reset password đã bị thu hồi.
- Reminder cho sự kiện đã qua.
- Báo cáo đã được thay bằng phiên bản mới.

Worker cần kiểm tra `expiresAt` hoặc điều kiện nghiệp vụ trước retry. Nếu hết hạn, chuyển job sang trạng thái `EXPIRED` hoặc `CANCELLED_BY_POLICY`, không cố gửi vô hạn.

### Dead-letter queue không phải thùng rác tự động

Job vượt số lần retry có thể chuyển sang DLQ hoặc trạng thái cần can thiệp. Vẫn cần:

- Lý do và loại lỗi.
- Notification ID, attempt history.
- Quyền và quy trình reprocess.
- Giới hạn tốc độ khi replay.
- Chính sách retention và xóa dữ liệu nhạy cảm.

Nếu operator replay hàng nghìn job một lúc mà không áp dụng backpressure, DLQ có thể trở thành nguồn gây overload mới.

## 16. Unknown outcome và nguy cơ gửi trùng khi retry

SMTP có một trường hợp khó: server có thể đã nhận message, nhưng client mất kết nối trước khi nhận phản hồi cuối cùng sau `DATA`.

```text
Worker                          SMTP server
  |---- MIME DATA ----------------->|
  |                                  |
  |                            Message accepted
  |                                  |
  X<--- connection lost ------------|
  |
  v
Timeout or MailException
```

Lúc này không biết chắc message đã được submit thành công hay chưa. Nếu backpressure làm tăng timeout rồi worker retry liên tục, người nhận có thể nhận nhiều bản trùng.

Nên phân biệt outcome:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `SMTP_ACCEPTED` | Có phản hồi transport xác nhận thành công | Không retry chỉ vì chưa có event delivery |
| `KNOWN_REJECTED` | Có bằng chứng message chưa được chấp nhận | Retry tùy loại lỗi |
| `UNKNOWN` | Không biết chắc SMTP đã nhận chưa | Reconcile nếu có thể; controlled retry với rủi ro trùng |
| `EXPIRED` | Job không còn giá trị nghiệp vụ | Không gửi theo chính sách |

`MailException` là nhóm exception, không phải bằng chứng tuyệt đối rằng email chưa ra khỏi ứng dụng. Cần classification dựa trên cause, SMTP stage và provider response khi có.

### Idempotency đúng phạm vi

Một `idempotencyKey` có thể giúp không tạo hai notification logic cho cùng event. Một `notificationId` nên giữ ổn định qua các lần retry; `attemptId` thay đổi theo lần thử.

Tuy nhiên, **idempotency của outbox không bảo đảm exactly-once delivery** giữa SMTP và database. Không kỳ vọng việc giữ nguyên MIME `Message-ID` khiến mọi mail server loại bỏ bản trùng.

## 17. Broker backpressure: RabbitMQ và consumer prefetch

Nếu dùng RabbitMQ làm queue gửi mail, cần quan tâm **prefetch** — số message có thể được broker gửi tới một consumer trước khi được acknowledge, theo semantics cấu hình.

Nếu prefetch quá lớn:

- Consumer giữ quá nhiều message chưa ACK.
- Message có thể nằm trong bộ nhớ consumer mà chưa có worker slot.
- Khi consumer chết, nhiều message phải requeue.
- Một consumer có thể chiếm phần lớn backlog, ảnh hưởng phân phối công việc.
- Khó ước lượng chính xác in-flight SMTP attempts từ số unacked.

Một cách tiếp cận:

1. Giới hạn số consumer và concurrency.
2. Đặt prefetch gần với khả năng xử lý thực tế, có buffer nhỏ theo đo đạc.
3. Chỉ ACK sau mốc công việc đã được hoàn thành theo hợp đồng.
4. Với lỗi tạm thời, đưa retry theo lịch hoặc delay queue thay vì requeue tức thì.
5. Theo dõi ready messages, unacked messages, consumer count và delivery rate.

### ACK là ranh giới tin cậy

Nếu broker là nơi duy nhất lưu job:

- ACK **trước** khi SMTP attempt được xử lý bền vững có thể làm mất job khi process chết.
- ACK **sau** SMTP accepted tạo khả năng broker redeliver khi worker chết trước ACK, dẫn tới gửi trùng.

Đây là hệ quả của việc không có transaction chung giữa SMTP và broker. Cần idempotency, attempt record và retry policy phù hợp.

Nếu broker chỉ vận chuyển tín hiệu “có outbox record mới”, còn database lưu job bền vững, ACK semantics có thể phản ánh việc đã nhận tín hiệu thay vì đã gửi email. Phải nêu rõ nguồn dữ liệu nào là sự thật.

## 18. Kafka: consumer lag và điều tiết xử lý

Với Kafka, cần quan sát sự khác biệt giữa:

- Producer append record thành công.
- Consumer fetch record.
- Worker gửi SMTP.
- Offset được commit.

Một consumer có thể poll nhiều record trong khi SMTP chậm. Nếu xử lý blocking quá lâu hoặc không duy trì heartbeat/poll đúng yêu cầu, consumer có thể bị rebalance. Khi đó record chưa commit có thể được xử lý lại, tạo nguy cơ duplicate.

Các lựa chọn:

- Giới hạn số record lấy mỗi lượt và số job đưa vào worker pool.
- Dùng cơ chế pause/resume partition khi không còn worker capacity.
- Tiếp tục poll/heartbeat phù hợp khi xử lý bị pause, theo contract Kafka client.
- Quản lý offset commit theo kết quả xử lý và thứ tự partition.
- Tách storage bền vững/idempotency nếu gửi email cần retry.
- Theo dõi consumer lag theo partition và nhóm.

**Không commit offset chỉ vì task đã được submit vào executor RAM** nếu Kafka record là bằng chứng duy nhất cho yêu cầu mail và cần bảo đảm có thể xử lý lại sau crash.

### Scale consumer không vượt số partition hữu ích

Nếu consumer group có ít partition, tăng số instance không nhất thiết tăng throughput. Đồng thời SMTP quota vẫn là giới hạn cuối. Scale cần dựa trên partition assignment, capacity worker và provider limit.

## 19. Fairness: đừng để một tenant chiếm toàn bộ queue

Một hệ thống nhiều tenant có thể gặp:

```text
Tenant A: 50,000 campaign emails
Tenant B: 12 password resets
Tenant C: 200 order confirmations
```

Nếu chỉ dùng một FIFO queue và A chiếm hầu hết backlog, email của B/C có thể phải chờ sau hàng chục nghìn job, dù có ít và quan trọng hơn.

Các cơ chế giảm starvation:

- Queue hoặc topic riêng theo lớp ưu tiên: transactional và bulk.
- Reserved worker/concurrency capacity cho loại khẩn cấp.
- Per-tenant enqueue quota và dispatch quota.
- Weighted fair scheduling hoặc round-robin giữa tenant.
- Giới hạn burst của tenant lớn.
- Ưu tiên theo deadline/expiry trong từng lane khi phù hợp.

### Priority không chỉ là một trường số

Nếu mọi loại email đều tự gắn `priority=HIGH`, cơ chế ưu tiên không còn tác dụng. Nên có catalog priority do backend xác định, không tin giá trị do client tùy ý gửi.

Ví dụ:

| Lớp | Ví dụ | Quy tắc |
|---|---|---|
| Critical transactional | OTP, reset password | Reserved capacity, TTL ngắn, chống abuse |
| Normal transactional | Xác nhận đơn hàng, biên nhận | Reliable queue, retry |
| Bulk/non-urgent | Báo cáo, newsletter | Rate limit thấp, schedule, có thể pause |

Không cho phép campaign bulk chiếm slot được dành cho security-critical mail. Ngược lại, hệ thống vẫn cần bảo vệ OTP endpoint khỏi spam và enumeration, vì một lane ưu tiên không có nghĩa nhận vô hạn request.

### Không để starvation vô hạn

Priority tuyệt đối có thể khiến job bulk chờ mãi nếu lane critical luôn đầy. Cần chính sách tối thiểu về fairness, quota hoặc expiry, và theo dõi tuổi job từng lớp.

## 20. Thứ tự gửi và xử lý email cũ

Email có thể có quan hệ thứ tự nghiệp vụ:

- Email “Đơn hàng đã tạo” trước “Đơn hàng đã hủy”.
- Email “Mã OTP mới” sau “Mã OTP cũ”.
- Reminder lần 1 trước reminder lần 2.

Backpressure và retry có thể làm đảo thứ tự. Một job cũ thất bại rồi retry sau có thể đến sau job mới.

Cần quyết định:

- Email nào được phép đến sai thứ tự?
- Có cần ordering per aggregate (orderId/accountId) không?
- Nếu job cũ hết giá trị, có thể cancel thay vì gửi không?
- Có cần sequence/version để kiểm tra trước khi gửi?
- Có được phép xử lý song song các thông báo cùng recipient không?

Không nên dùng FIFO toàn hệ thống để cố đảm bảo mọi nghiệp vụ có thứ tự; điều này thường làm giảm throughput lớn và không giải quyết được vấn đề ở nhiều broker/replica.

Một cách thực tế là lưu `businessVersion` hoặc `expiresAt` trong job và kiểm tra trạng thái hiện hành trước khi gửi các email có thể trở nên lỗi thời.

## 21. Attachment và MIME size ảnh hưởng tới backpressure

Không phải mọi email có chi phí bằng nhau.

Một mail text-only 2 KB có thể gửi nhanh hơn nhiều so với mail có PDF 15 MB. Khi hệ thống chỉ giới hạn số message/s, một vài file lớn có thể giữ worker và SMTP connection quá lâu.

Cần xem xét:

- Số byte MIME sau encoding.
- Chi phí render template.
- Chi phí đọc file/object storage.
- Số attachment và nguồn dữ liệu.
- Thời gian upload dữ liệu qua SMTP.
- Bộ nhớ giữ byte array.
- Quota provider theo message size hoặc recipient.

Binary attachment thường được base64-encode, làm tăng kích thước dữ liệu truyền so với byte gốc. Vì vậy giới hạn 10 MB file không đồng nghĩa SMTP payload đúng 10 MB.

### Cost-aware scheduling

Có thể chia lane:

- Small transactional.
- Attachment-heavy.
- Bulk send.

Hoặc dùng hạn mức đồng thời riêng cho message lớn. Không để 8 worker đều bị giữ bởi attachment lớn khiến những email OTP nhỏ phải chờ.

Nếu cần giới hạn bytes-in-flight, có thể dùng weighted permit theo kích thước ước lượng, nhưng cần tránh thiết kế quá phức tạp trước khi có số đo. Một giới hạn concurrency theo loại mail thường là bước đầu dễ vận hành.

## 22. Quản lý bộ nhớ: queue chứa gì?

Một anti-pattern:

```java
byte[] attachment = Files.readAllBytes(path);

mailExecutor.execute(() -> {
    sendMail(attachment);
});
```

Nếu queue có nhiều task, mỗi `Runnable` có thể giữ một mảng byte lớn trong heap. Queue capacity 100 task với mỗi attachment 10 MB có thể giữ lượng dữ liệu rất lớn, chưa tính overhead.

Một hướng an toàn hơn:

```text
Queue job:
  notificationId
  tenantRef
  templateVersion
  approvedAttachmentId
  storageKey/version

Worker when ready:
  -> load approved data
  -> build MIME
  -> send
  -> release resources
```

Giữ **metadata nhỏ** trong queue; lưu attachment tại storage bền vững có quyền truy cập rõ ràng, version/retention phù hợp và giới hạn bytes khi đọc. Điều này cũng giúp worker trên replica khác có thể xử lý job.

Tuy nhiên, đừng lưu URL có token quá ngắn hạn trong queue rồi kỳ vọng worker lấy được sau nhiều giờ. Nên lưu storage key/version nội bộ và lấy credential khi cần theo chính sách.

## 23. Timeout phải phối hợp với concurrency

Nếu SMTP chậm, mỗi worker giữ slot lâu hơn. Khi số worker cố định, throughput giảm, backlog tăng. Do đó timeout là một phần của backpressure.

Ví dụ cấu hình:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.starttls.enable": true
      "mail.smtp.starttls.required": true
      "mail.smtp.connectiontimeout": 5000
      "mail.smtp.timeout": 5000
      "mail.smtp.writetimeout": 5000
```

Các giá trị millisecond chỉ minh họa. Ba timeout không phải một deadline tổng cố định của cả attempt; thao tác gửi có nhiều giai đoạn đọc/ghi.

### Tăng worker có phải giải pháp?

Nếu latency một attempt tăng, tăng concurrency có thể giúp tận dụng thời gian chờ I/O, nhưng đồng thời:

- Tăng số connection.
- Tăng áp lực CPU/TLS/heap.
- Có thể vi phạm provider concurrency quota.
- Làm tăng timeout nếu provider bị quá tải.
- Tăng khả năng retry storm.

Hãy thử nghiệm theo các mức concurrency có giới hạn và quan sát throughput accepted, p95/p99 latency, 4xx rate và bytes-in-flight. Dừng tăng khi throughput không còn tăng hoặc error rate bắt đầu xấu đi.

## 24. Bulkhead và circuit breaker cho SMTP route

Một hệ thống có thể dùng hai SMTP provider: transactional primary và bulk provider. Nếu bulk provider chậm, không nên làm cạn toàn bộ worker slot của transactional route.

**Bulkhead** giúp cô lập tài nguyên:

```text
Mail dispatcher
    |
    +--> Transactional pool (reserved capacity)
    |       +--> SMTP route A
    |
    +--> Bulk pool (bounded)
            +--> SMTP route B
```

**Circuit breaker** giúp tạm ngưng gọi một route khi tỷ lệ lỗi cao theo chính sách. Nhưng việc mở circuit phải đi cùng xử lý job:

- Không xóa job.
- Giữ ở PENDING/DEFERRED hoặc chuyển route theo quyền đã duyệt.
- Hẹn thử lại có giới hạn.
- Tránh tất cả worker cùng bắn thử khi circuit half-open.
- Đừng dùng circuit breaker để che lỗi cấu hình SMTP AUTH vĩnh viễn.

Failover sang route khác phải xét quyền sender, SPF/DKIM/DMARC, hạn mức, content policy và tính nhất quán của provider ID/webhook. Không chuyển route tùy tiện chỉ vì primary chậm.

## 25. Backpressure ở API: trả gì cho producer?

Khi người dùng gọi endpoint tạo notification, trạng thái HTTP phải phản ánh **hợp đồng admission**.

### Trường hợp A: outbox đã commit

Có thể trả:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "notif-503",
  "status": "QUEUED"
}
```

Điều này nghĩa là yêu cầu đã được chấp nhận vào hệ thống xử lý theo hợp đồng, **không phải email đã được SMTP nhận hoặc người dùng đã đọc**.

### Trường hợp B: admission từ chối do overload

Có thể trả:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/json

{
  "errorCode": "MAIL_QUEUE_OVER_CAPACITY",
  "message": "Mail submission is temporarily unavailable"
}
```

Hoặc `429 Too Many Requests` khi đây là giới hạn theo caller/tenant, tùy contract. `Retry-After` chỉ nên đưa ra khi có chính sách thời gian thử lại phù hợp và không gây lộ thông tin.

**Không trả 202 khi chưa lưu job vào nơi đủ bền vững theo hợp đồng.**

### Email là side effect của nghiệp vụ khác

Nếu endpoint tạo đơn hàng rồi ghi outbox trong transaction:

- Khi SMTP down, đơn hàng có thể vẫn được tạo và outbox giữ notification.
- Nếu outbox bị quá tải, cần quyết định liệu toàn bộ transaction nên fail hay có degraded policy được phép.
- Không được âm thầm tạo đơn hàng rồi báo email đã gửi.
- Không retry tạo đơn hàng chỉ vì gửi email thất bại, tránh tạo đơn trùng.

Một quyết định quan trọng là email có bắt buộc đối với thao tác chính hay không; nó thuộc thiết kế nghiệp vụ chứ không chỉ cấu hình queue.

## 26. Bảo đảm admission atomic khi tải cao

Giả sử quota pending cho mỗi tenant là 1000 job.

Hai request đồng thời:

```text
Request A reads pending=999
Request B reads pending=999

A inserts job -> 1000
B inserts job -> 1001
```

Một câu `COUNT(*) < 1000` trước `INSERT` không bảo đảm giới hạn cứng dưới concurrency.

Các kỹ thuật tùy storage:

- Transaction giữ/giải phóng quota slot trên một row có locking/version.
- Unique constraint và reservation record.
- Atomic quota counter được cập nhật có điều kiện.
- Broker quota hoặc ingress rate limit phối hợp với backpressure chính.
- Ngưỡng cảnh báo mềm cộng cơ chế bảo vệ dung lượng cứng ở tầng storage.

Nếu dùng counter phân tán, phải có chính sách **reconciliation** khi process chết trước khi release quota slot. Một slot bị giữ vĩnh viễn có thể khiến tenant không bao giờ gửi được nữa.

Không xây quota chỉ bằng biến static trong một replica nếu hệ thống có nhiều instance và yêu cầu giới hạn toàn cục.

## 27. Shutdown và backpressure là hai mặt liên quan

Khi ứng dụng nhận SIGTERM hoặc context close, worker nên:

1. Dừng nhận việc mới vào executor sắp shutdown.
2. Dừng poll/claim job mới từ outbox/broker.
3. Để những attempt đang chạy hoàn thành trong deadline.
4. Ghi kết quả và release lease/slot theo policy.
5. Cho worker khác hoặc lần khởi động sau xử lý job chưa hoàn tất.

Nếu tiếp tục claim vô hạn trong lúc shutdown, backlog in-flight sẽ tăng và vượt termination grace period.

Với `ThreadPoolTaskExecutor`, cài đặt:

```java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(25);
```

giúp điều khiển chờ hoàn tất task trong quá trình đóng executor. Nó **không bảo đảm task trong RAM tồn tại qua `SIGKILL`, mất điện hoặc process crash**. Nếu email phải được gửi đáng tin cậy, cần storage bền vững và retry/lease phù hợp.

### Kết quả SMTP không chắc chắn sau force kill

Nếu worker đã truyền dữ liệu nhưng chết trước khi lưu `SMTP_ACCEPTED`, job có thể được gửi lại. Backpressure cần phối hợp idempotency và kiểm soát retry, không chỉ số worker.

## 28. Sự khác nhau giữa backpressure và autoscaling

Autoscaling thêm worker khi backlog tăng, nhưng nó không thay thế backpressure.

Ví dụ:

- Queue tăng vì SMTP provider giới hạn 15 messages/s.
- Autoscaler tăng từ 5 lên 50 worker.
- Tất cả worker cùng tranh quota 15 messages/s.
- Provider trả nhiều 4xx hơn.
- Retry làm backlog lớn thêm.

Autoscaling chỉ có lợi khi bottleneck là **năng lực xử lý có thể mở rộng**, chẳng hạn CPU render hoặc số worker chưa đủ trong giới hạn provider.

Một chiến lược scale tốt cần xem:

- Queue depth và oldest age.
- Worker in-flight và CPU/memory.
- SMTP accepted throughput.
- Provider quota, rate-limit/error signals.
- Số partition/consumer có thể hoạt động song song.
- Chi phí và độ trễ khởi động worker mới.

**Tăng worker tới quota provider không phải mục tiêu vô hạn.** Có thể cần scale down/pause khi provider đang từ chối, để giảm retry storm.

## 29. Quan sát backpressure bằng Micrometer

Trong Spring Boot, Micrometer có thể dùng để ghi counter, timer và gauge.

Các meter hữu ích:

| Metric đề xuất | Loại | Ý nghĩa |
|---|---|---|
| `mail.notification.created` | Counter | Số notification logic mới |
| `mail.queue.admission.rejected` | Counter | Số yêu cầu bị từ chối vì capacity |
| `mail.send.attempt` | Counter | Số lần bắt đầu SMTP attempt |
| `mail.send.accepted` | Counter | Attempt được SMTP chấp nhận |
| `mail.send.failed` | Counter | Attempt có known failure |
| `mail.send.unknown` | Counter | Attempt không rõ kết quả |
| `mail.smtp.throttled` | Counter | Phản hồi provider được phân loại throttling |
| `mail.outbox.pending` | Gauge | Số job đang chờ |
| `mail.outbox.oldest.age` | Gauge | Tuổi job chờ lâu nhất (seconds) |
| `mail.worker.inflight` | Gauge | Số worker slot đang bận |
| `mail.executor.queue.depth` | Gauge | Số task trong queue RAM |
| `mail.queue.wait.duration` | Timer | Thời gian từ enqueue tới xử lý |
| `mail.smtp.attempt.duration` | Timer | Độ trễ thao tác gửi SMTP |

Các tên chỉ là quy ước minh họa, không phải toàn bộ metric do Spring Mail tự xuất ra.

### Metric nào cho biết nghẽn thật?

Một tình huống:

```text
created/s          = 50
smtp accepted/s    = 15
outbox pending     = increasing
oldest pending age = increasing
provider 4xx       = increasing
```

Đây là tín hiệu hệ thống không theo kịp. Nếu chỉ nhìn `smtp accepted/s`, có thể nhầm rằng throughput đang tốt; cần kết hợp tốc độ đến và tốc độ ra.

### Queue age quan trọng hơn chỉ queue depth

Một backlog 500 job có thể bình thường sau burst ngắn. Nhưng 20 job đã chờ hơn 30 phút có thể nghiêm trọng nếu email có deadline vài phút.

Nên theo dõi cả:

- `pending_count`.
- `oldest_pending_age_seconds`.
- Phân phối queue wait.
- Job hết hạn hoặc vượt SLO.
- Backlog theo lớp ưu tiên/route.

## 30. Giữ tags có cardinality thấp

Một metric được lưu theo mỗi tổ hợp nhãn. Nếu gắn `notificationId` hoặc recipient email làm tag, hệ thống có thể tạo hàng trăm nghìn series.

Các tag phù hợp:

```text
type=transactional|bulk|security
route=primary|backup|marketing
result=accepted|failed|unknown
reason=capacity|rate_limit|shutdown
error=authentication|connection|tls|throttling|unclassified
```

Không nên dùng:

- `correlationId`, `notificationId`, `attemptId`.
- Địa chỉ email người nhận.
- Raw SMTP exception message.
- Mã đơn hàng, user ID, tenant ID không có giới hạn.
- Toàn bộ URL, filename hoặc token.

Giữ ID để tra cứu trong log và outbox record, không dùng làm metric label. Nếu cần quota theo tenant, lưu quota trong storage và phát metric tổng hợp theo nhóm/lớp tenant có cardinality kiểm soát.

## 31. Prometheus và dashboard khi queue bị nghẽn

Giả sử có những series:

```text
mail_notification_created_total
mail_send_attempt_total
mail_send_accepted_total
mail_queue_admission_rejected_total
mail_outbox_pending
mail_outbox_oldest_age_seconds
```

Tên export cụ thể có thể khác tùy Micrometer registry và unit naming. Luôn kiểm tra endpoint `/actuator/prometheus` của phiên bản thật trước khi sao chép PromQL.

### Tốc độ tạo notification

```promql
sum(rate(mail_notification_created_total[5m]))
```

### Tốc độ SMTP accepted

```promql
sum(rate(mail_send_accepted_total[5m]))
```

### Chênh lệch nhu cầu và throughput

```promql
sum(rate(mail_notification_created_total[5m]))
-
sum(rate(mail_send_accepted_total[5m]))
```

Biểu thức cuối là **tín hiệu xu hướng sơ bộ**, không phải công thức chính xác tính queue growth vì created và accepted có thể thuộc những cohort khác nhau, có retry, expiry và nhiều recipient. Gauge `mail_outbox_pending` mới phản ánh backlog tại thời điểm đo.

### Số lần admission bị từ chối

```promql
sum(increase(mail_queue_admission_rejected_total[15m]))
```

### Backlog theo route

```promql
sum by (route) (mail_outbox_pending)
```

Nếu cùng backlog được export ở nhiều instance qua cùng nguồn DB, tổng qua tất cả replica sẽ **đếm trùng**. Hãy có một cơ chế export hợp lý (ví dụ một collector, leader, hoặc truy vấn có phân vùng rõ) rồi mới tổng hợp.

### Tỷ lệ throttling

Nếu có counter riêng:

```promql
sum(rate(mail_smtp_throttled_total[5m]))
/
sum(rate(mail_send_attempt_total[5m]))
```

Khi mẫu số bằng 0, không được diễn giải tỷ lệ thành 0% hoặc 100% tùy tiện. Alert nên có ngưỡng traffic tối thiểu và cửa sổ quan sát.

## 32. Alert cho nghẽn mail queue

Một dashboard không đủ nếu không có cảnh báo đúng sự cố.

### Alert theo queue age

Ví dụ policy: cảnh báo khi tuổi job `PENDING` lâu nhất vượt ngưỡng của loại email và kéo dài đủ thời gian để tránh nhiễu.

Cần tránh một ngưỡng chung cho OTP và báo cáo tuần; SLO của chúng khác nhau.

### Alert theo admission rejection

Nếu `mail.queue.admission.rejected` tăng liên tục, producer đang bị backpressure. Đây có thể là hành vi bảo vệ đúng, nhưng cần điều tra lý do capacity không đủ.

### Alert theo worker stall

```text
mail_outbox_pending > 0
AND
mail_send_attempt rate ~= 0
```

Nếu còn job và không có attempt nào trong một khoảng phù hợp, worker/scheduler/consumer có thể dừng hoặc bị pause vì circuit/rate limit.

### Alert theo provider throttling

Nếu 4xx throttling tăng đồng thời accepted throughput giảm và queue age tăng, nên giảm tốc route thay vì đơn giản tăng số worker.

### Alert theo tài nguyên storage

Nếu disk/outbox table hoặc broker queue sắp đầy, hệ thống phải chủ động bảo vệ. Không để database đầy rồi làm thất bại cả transaction nghiệp vụ chính.

### Không alert chỉ vì queue depth lớn

Một batch được thiết kế trước có thể tạo queue depth cao trong thời gian ngắn. Cần kết hợp oldest age, drain trend và SLO, tránh cảnh báo giả mỗi lần chạy campaign.

## 33. Runbook khi backlog tăng nhanh

### Bước 1: xác định backlog thuộc loại nào

- Executor queue RAM?
- Database outbox?
- RabbitMQ ready/unacked messages?
- Kafka consumer lag?
- Provider queue/deferred events?

Mỗi nơi có cách giảm tải khác nhau. Không nên áp dụng một thao tác “clear queue” cho mọi trường hợp.

### Bước 2: tìm bottleneck

Kiểm tra:

- Created rate.
- SMTP accepted rate.
- 4xx/throttling và timeout.
- Worker in-flight.
- CPU/heap/GC.
- Database/broker latency.
- Attachment size và route bị ảnh hưởng.

### Bước 3: giảm nguồn phát sinh không quan trọng

Có thể pause bulk/campaign, giảm batch size, giới hạn producer và áp dụng per-tenant quota. Không tự động chặn OTP hoặc email bảo mật nếu không có phương án xử lý phù hợp.

### Bước 4: giảm retry storm

Kiểm tra lịch retry, jitter, số attempt và lỗi AUTH vĩnh viễn. Nếu credential sai, dừng retry route cho đến khi được sửa thay vì tiếp tục tiêu hao quota.

### Bước 5: khôi phục theo capacity thực

Sau khi provider phục hồi, tăng dần concurrency/rate trong giới hạn. Giữ backlog bền vững và không replay toàn bộ DLQ trong một lượt.

### Bước 6: kiểm tra job hết hạn

OTP/reminder đã quá deadline có thể cần chuyển `EXPIRED`, không gửi trễ gây sai nghiệp vụ. Những email có nghĩa vụ lưu giữ khác cần quy trình riêng.

### Bước 7: theo dõi sau khôi phục

Xác nhận:

- Backlog và oldest age giảm.
- SMTP accepted rate ổn định.
- 4xx/timeout giảm.
- In-flight và queue bounded nằm trong giới hạn.
- Không có lượng gửi trùng bất thường.
- Không bỏ mất job được API xác nhận đã nhận.

## 34. Unit test: executor đầy phải từ chối rõ ràng

Một cách test cụ thể là cấu hình executor có một worker và queue nhỏ, cho task đầu giữ worker bằng latch, task thứ hai vào queue và task thứ ba bị từ chối.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsWhenWorkerAndQueueAreFull() throws Exception {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(1);
    executor.initialize();

    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);

    try {
        executor.execute(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });

        // Bảo đảm task thứ nhất đang chiếm worker.
        org.assertj.core.api.Assertions.assertThat(
                started.await(5, TimeUnit.SECONDS)
        ).isTrue();

        executor.execute(() -> {
            // Task thứ hai nằm trong queue.
        });

        assertThatThrownBy(() ->
                executor.execute(() -> {})
        ).isInstanceOf(TaskRejectedException.class);
    } finally {
        release.countDown();
        executor.shutdown();
    }
}
```

Trong test thực tế có thể dùng executor lifecycle khác và thêm cleanup phù hợp nếu assertion lỗi. Không cần gửi email thật: test này xác nhận behavior khi capacity đầy.

### Test API không báo success giả

Khi executor bị reject:

- Nếu job chỉ ở RAM, service không được báo đã queue thành công.
- Nếu job đã commit vào outbox, service có thể trả `QUEUED` dù dispatch best-effort bị reject.
- Không nên tăng `mail.send.accepted` khi chưa gọi SMTP.

Đây là contract test của application service, độc lập với SMTP provider.

## 35. Test worker giữ tối đa concurrency

Với `Semaphore` hoặc worker pool bounded, cần kiểm tra:

1. Tạo số job lớn hơn giới hạn.
2. Dùng fake SMTP sender có latch để giữ các attempt.
3. Đo số attempt đang hoạt động đồng thời.
4. Xác nhận nó không vượt số permit.
5. Release latch; xác nhận permit được trả trong `finally`.
6. Thử exception; không để permit bị rò rỉ.
7. Xác nhận job chưa được nhận vẫn trong outbox/PENDING.

Không dùng `Thread.sleep(...)` tùy ý làm bằng chứng concurrency vì test dễ flake. `CountDownLatch` hoặc `Phaser` giúp kiểm soát lịch trình chính xác hơn.

### Với nhiều replica

Một test in-memory chỉ chứng minh giới hạn của một instance. Để xác minh quota provider toàn cục, cần integration test với nhiều worker/replica hoặc test cơ chế quota phân tán, không suy ra từ một `Semaphore(4)`.

## 36. Test retry có backoff và không tạo thêm notification

Ví dụ kịch bản:

```text
Create notification N -> created +1
Attempt A1 -> known 4xx, schedule retry
Before nextAttemptAt -> worker must not claim N
After nextAttemptAt -> attempt A2
A2 -> SMTP accepted
Notification N -> final submission state accepted
```

Các assertion:

- Notification ID không đổi.
- Attempt ID khác nhau.
- Created count không tăng lại ở A2.
- Job có `nextAttemptAt` theo policy.
- Không retry ngay trong vòng lặp nóng.
- Khi vượt max attempts hoặc TTL, job chuyển trạng thái rõ.
- Không có hai worker cùng claim một job khi lease còn hợp lệ.
- Không gộp UNKNOWN outcome vào known rejection.

Clock trong test nên cố định bằng `Clock.fixed(...)` hoặc fake clock, không phụ thuộc thời gian thật.

## 37. Test broker và outbox khi có sự cố

Các kịch bản integration quan trọng:

| Sự cố | Kỳ vọng |
|---|---|
| Worker crash trước khi gửi | Job còn ở queue/outbox và có thể khôi phục |
| Crash sau SMTP accepted trước DB commit | Recovery không tuyên bố exactly-once; attempt có dấu hiệu unknown/needs reconciliation |
| RabbitMQ redelivery | Handler idempotent với logical notification |
| Kafka rebalance | Không commit offset như thể đã xử lý khi công việc chưa bền vững |
| SMTP provider trả throttling liên tục | Worker giảm tốc, retry có backoff, backlog không tạo hot loop |
| Outbox sắp đầy | Admission bảo vệ storage và trả trạng thái có ý nghĩa |
| Bulk chiếm tải | Critical lane vẫn có reserved capacity |
| Force shutdown | Không claim mới, job còn pending/lease |
| Attachment quá lớn | Không nạp nhiều byte vào executor RAM |
| DLQ replay hàng loạt | Áp dụng cùng limiter như traffic bình thường |

Nên dùng SMTP test server hoặc fake sender cho các case, không dùng credential production. Test queue/outbox cần kiểm tra state thực, không chỉ metric counter.

## 38. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Queue RAM gần như vô hạn | Heap tăng, delay ẩn, mất task khi crash | Bounded queue và hợp đồng overload |
| Tăng maxPoolSize nhưng queueCapacity rất lớn | Worker khó mở rộng như kỳ vọng | Hiểu thứ tự queue/pool và đo |
| Dùng `CallerRunsPolicy` ở HTTP thread | Request có thể bị block bởi SMTP | Admission rõ hoặc outbox bền vững |
| Dùng `DiscardPolicy` | Mất email âm thầm | Từ chối hoặc persist |
| Claim quá nhiều outbox job | Lease hết trước khi gửi, duplicate | Claim theo slot/permit |
| Mỗi replica có limiter bằng toàn provider quota | Tổng vượt quota | Limiter toàn cục hoặc phân quota |
| Retry ngay sau mọi 4xx | Retry storm | Phân loại lỗi, backoff/jitter |
| Retry SMTP timeout như chắc chắn chưa gửi | Email trùng | UNKNOWN/reconciliation |
| Đếm attempt thành message created | Dashboard sai khi retry | Logical notification ID |
| Chỉ theo queue depth | Không thấy job lâu năm | Oldest-age và SLO |
| Scale worker vô hạn | Provider throttling nặng hơn | Scale trong quota thực |
| Dùng một FIFO cho OTP và bulk | OTP bị chậm | Lanes, fairness, reserved capacity |
| Giữ attachment byte[] trong queue task | OOM khi backlog | Metadata nhỏ + storage riêng |
| Gắn tenant/notificationId làm metric label | Cardinality cao | Nhãn hữu hạn, ID trong DB/log |
| Báo 202 trước khi enqueue bền vững | Mất job dù caller tưởng đã nhận | Commit/publish confirmation trước |
| Không có shutdown admission | Job bị reject/lost khi redeploy | Dừng claim, drain, retry |
| Xử lý job OTP hết hạn | Gửi mã vô dụng hoặc gây nhầm | TTL/expiry policy |

## 39. Checklist thiết kế và vận hành

Trước khi đưa queue gửi mail vào production:

1. **Xác định đơn vị job:** một notification logic theo recipient hay batch nhiều recipient.
2. **Đo arrival rate và SMTP accepted throughput** ở tải thực.
3. **Biết provider quota:** messages/s, recipients/s, concurrency, quota theo ngày nếu có.
4. **Giới hạn queue RAM:** threads, queue capacity và rejection policy rõ.
5. **Không drop job đã xác nhận nhận** nếu hợp đồng yêu cầu bền vững.
6. **Dùng outbox/broker bền vững** cho email nghiệp vụ quan trọng.
7. **Giới hạn admission** theo năng lực storage và backlog/SLO.
8. **Giới hạn claim/in-flight** theo worker slots và lease.
9. **Áp dụng rate limiter toàn route/provider** nếu nhiều replica dùng chung quota.
10. **Retry với backoff, jitter, max attempts và deadline** thay vì retry nóng.
11. **Phân biệt SMTP accepted, known failure và unknown outcome**.
12. **Có ưu tiên/fairness** để bulk không chặn email quan trọng.
13. **Quản lý attachment** ngoài queue RAM và giới hạn bytes-in-flight.
14. **Thiết kế shutdown** dừng nhận mới, drain trong thời hạn và khôi phục job.
15. **Theo dõi queue depth, oldest age, accepted throughput, throttling và in-flight**.
16. **Bảo vệ metric cardinality** và không để lộ PII.
17. **Kiểm thử overload**, task rejection, crash/retry, broker redelivery và timeout.
18. **Có runbook** giảm producer, pause bulk, sửa SMTP route và replay có kiểm soát.

Không cần triển khai tất cả cơ chế cùng lúc trong ứng dụng nhỏ. Nhưng ít nhất cần có **giới hạn hữu hạn**, **hành vi khi đầy** và **một câu trả lời đúng về việc đã chấp nhận job hay chưa**.

## 40. Ghi nhớ

- Backpressure kiểm soát chênh lệch giữa tốc độ tạo email và năng lực gửi của worker/SMTP provider.
- Queue hấp thụ burst, nhưng queue lớn vô hạn không làm năng lực xử lý tăng.
- `ThreadPoolTaskExecutor` cần giới hạn `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection policy; queue RAM không bền vững qua crash.
- Với queue capacity dương, worker có thể chỉ mở rộng tới `maxPoolSize` khi queue đã đầy.
- `CallerRunsPolicy` có thể biến gửi bất đồng bộ thành block HTTP thread; `DiscardPolicy` và `DiscardOldestPolicy` có nguy cơ mất mail.
- Email quan trọng nên được ghi bền vững bằng queue/outbox và nhận diện bằng notification ID trước khi trả trạng thái accepted.
- Không claim nhiều job hơn khả năng xử lý; quản lý lease và claim token khi có nhiều worker.
- Concurrency limit, rate limit, quota và backlog limit là bốn cơ chế khác nhau.
- SMTP 4xx/throttling phải được phân loại và xử lý bằng backoff/jitter, không retry vô hạn.
- Retry có thể tạo email trùng khi kết quả SMTP không chắc chắn; outbox không tự bảo đảm exactly-once.
- Tách lane/priority/quota để bulk không làm trễ OTP và email giao dịch quan trọng.
- Giữ attachment ở storage an toàn, không nhét nhiều byte array lớn vào task đang chờ.
- Quan sát cả created rate, accepted throughput, retry, queue age, in-flight và admission rejection.
- Khi provider giới hạn tốc độ, autoscaling worker vô hạn chỉ làm overload nặng thêm.
- Quy trình dừng ứng dụng phải ngừng nhận/claim việc mới, drain trong deadline và giữ job chưa hoàn tất cho lần retry sau.

**Kết luận:** Backpressure của mail queue không phải một tùy chọn cấu hình đơn lẻ mà là **hợp đồng điều tiết xuyên suốt producer, queue, worker và SMTP provider**. Một hệ thống tốt chủ động thừa nhận khi nào nó đủ capacity, lúc nào cần chờ và khi nào phải từ chối; giữ công việc quan trọng trong storage bền vững, tránh retry storm và đo được độ trễ thật của từng loại email. Nhờ đó, Spring Framework Mail có thể gửi ổn định khi tải tăng mà không đánh đổi việc mất message âm thầm hoặc làm nghẽn toàn bộ ứng dụng.
