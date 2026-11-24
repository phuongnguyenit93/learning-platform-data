# Chờ điều kiện bất đồng bộ và kiểm thử timeout có tính xác định

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và client library tương ứng. Những luồng như gửi message vào SQS/Pub/Sub, xử lý file trên worker, cập nhật database, nhận event từ storage hoặc chạy tác vụ bằng `@Async` thường hoàn tất sau khi method ban đầu đã trả về.

Trong integration test, việc gọi một API publish message thành công chưa có nghĩa consumer đã xử lý xong. Một HTTP request trả `202 Accepted` cũng không chứng minh job đã hoàn tất. Test cần chờ một **điều kiện quan sát được** với deadline rõ ràng, đồng thời phải thất bại nhanh khi workflow đi vào trạng thái lỗi không thể phục hồi.

`Thread.sleep()` thường được dùng để chờ, nhưng thời gian chờ cố định không chứng minh điều kiện đã xảy ra. Nếu chờ quá ngắn, test flaky; nếu chờ quá dài, toàn bộ suite chậm. **Awaitility** cung cấp cách polling có giới hạn thời gian; JUnit cung cấp timeout cho test; `CompletableFuture`, Reactor và các clock/scheduler có thể giúp kiểm thử những phần bất đồng bộ theo cách có thể kiểm soát.

Sau bài này, bạn có thể:

- Phân biệt timeout của test, timeout của lần gọi dịch vụ, deadline nghiệp vụ và ack/visibility timeout.
- Dùng Awaitility để chờ trạng thái database, message consumer và job bất đồng bộ.
- Chọn `atMost`, `pollInterval`, `pollDelay`, `untilAsserted`, `during` và fail-fast condition đúng mục đích.
- Kiểm thử `@Async`, `CompletableFuture`, SQS listener và Pub/Sub subscriber.
- Thiết kế retry/backoff nằm trong deadline tổng.
- Dùng clock và virtual scheduler để tránh phụ thuộc thời gian thực trong unit test.
- Ngăn race condition, duplicate delivery, test transaction chưa commit và resource leak.
- Tạo test ổn định khi chạy song song hoặc trên CI có tải biến động.

## 2. Vì sao `Thread.sleep()` làm test bất ổn?

Giả sử một test gửi message rồi chờ worker cập nhật trạng thái:

~~~java
publisher.publish(event);
Thread.sleep(2_000);
assertEquals(JobStatus.COMPLETED, repository.findStatus(event.jobId()).orElse(null));
~~~

Đoạn code có ba vấn đề:

1. Nếu worker hoàn tất sau 100 ms, test vẫn lãng phí gần 1,9 giây.
2. Nếu CI tải cao và worker cần 2,1 giây, test thất bại dù ứng dụng hoạt động đúng.
3. Nếu worker thất bại trước khi cập nhật database, test vẫn chờ đủ hai giây mới phát hiện.

Một bài kiểm thử tốt cần diễn đạt điều kiện mong đợi, ví dụ “job có trạng thái COMPLETED trong tối đa 5 giây”. Framework sẽ kiểm tra điều kiện nhiều lần cho tới khi thành công hoặc hết deadline.

Không phải mọi khoảng chờ đều có thể thay bằng polling. Nếu đang kiểm tra logic thời gian thuần như hết hạn token, lịch retry hoặc ngày hết hạn hợp đồng, hãy kiểm soát clock/scheduler thay vì chờ đồng hồ thật chạy.

## 3. Phân biệt các loại timeout

Từ timeout của test đến timeout của message broker là những giới hạn khác nhau:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Test timeout | Giới hạn tổng thời gian một test được phép chạy | JUnit `@Timeout`, `assertTimeout` |
| Condition timeout | Thời gian tối đa chờ một trạng thái xuất hiện | Awaitility `atMost(5s)` |
| Poll interval | Khoảng cách giữa hai lần kiểm tra điều kiện | 100 ms |
| Client/request timeout | Thời gian tối đa cho một lần gọi HTTP, gRPC hoặc SDK | AWS SDK API call timeout |
| Future wait timeout | Thời gian test chờ kết quả của `Future` | `future.get(3, SECONDS)` |
| Business deadline | Thời điểm muộn nhất nghiệp vụ phải hoàn tất | Preview sẵn sàng trong 2 phút |
| SQS visibility timeout | Khoảng thời gian message đang xử lý chưa được giao lại | 30 giây |
| Pub/Sub ack deadline | Thời gian broker chờ acknowledgment trước khi redelivery | 10 giây, có thể được client gia hạn |
| Retry budget | Tổng thời gian dành cho các lần thử và backoff | 3 attempts trong 5 giây |

Không dùng một giá trị timeout cho tất cả lớp. Condition timeout phải đủ lớn để bao gồm thời gian publish, queue delivery, xử lý và ghi dữ liệu. Test timeout ngoài cùng phải lớn hơn thời gian condition cộng setup/cleanup.

Có thể đặt thêm `@Timeout` ở cấp JUnit test như một hàng rào cuối cùng. Timeout này không thay thế deadline riêng cho request hoặc điều kiện Awaitility; nó chỉ giới hạn tổng thời gian test.

## 4. Thiết kế deadline tổng

Một workflow có thể gồm nhiều lần gọi dịch vụ, retry và backoff. Hãy ước lượng thời gian tổng trước khi chọn timeout:

\[
T_{workflow} \leq \sum_{i=1}^{n} T_{attempt_i} + \sum_{j=1}^{n-1} T_{backoff_j}
\]

Ví dụ:

- Mỗi lần gọi dependency có timeout 800 ms.
- Tối đa 3 lần thử.
- Backoff giữa các lần thử là 200 ms rồi 400 ms.

\[
T_{workflow} \leq 3 \times 0,8 + 0,2 + 0,4 = 3,0\text{ giây}
\]

Nếu test chỉ chờ 2 giây thì test timeout có thể nhỏ hơn retry budget của ứng dụng. Nếu test chờ 30 giây cho một luồng đáng lẽ kết thúc trong 3 giây, test sẽ che giấu lỗi và làm CI chậm.

Một quy tắc hữu ích:

- Timeout của mỗi request phải nằm trong phần ngân sách còn lại của workflow.
- Tổng retry/backoff phải nằm trong business deadline.
- Awaitility timeout phải bao phủ workflow nhưng vẫn đủ ngắn để phát hiện regression.
- Test timeout phải có thêm khoảng đệm cho Spring context, container và cleanup.
- Ack deadline/visibility timeout phải phù hợp thời gian xử lý message; nếu xử lý lâu, cần cơ chế gia hạn hoặc thiết kế lại.

Các con số trên chỉ là ví dụ. Dùng latency thực tế, retry policy và yêu cầu sản phẩm để chọn deadline.

## 5. Chọn công cụ chờ theo tình huống

| Tình huống | Công cụ phù hợp | Lý do |
|---|---|---|
| Chờ database được worker cập nhật | Awaitility | Điều kiện có thể đọc lại nhiều lần |
| Chờ `CompletableFuture` hoàn tất | `get(timeout)` hoặc Awaitility | Có Future trực tiếp để chờ |
| Kiểm tra method hoàn tất trong giới hạn | JUnit `assertTimeout` | Kiểm tra thời gian thực thi đoạn code |
| Kiểm tra stream theo virtual time | Reactor `StepVerifier.withVirtualTime` | Không phải đợi đồng hồ thật |
| Kiểm tra business rule phụ thuộc ngày/giờ | Inject `Clock` | Đặt thời điểm test xác định |
| Kiểm tra task scheduler | Scheduler có thể điều khiển trong test | Kích hoạt task theo ý test |
| Kiểm tra consumer nhận message | Awaitility + trạng thái bền vững | Chờ side effect nghiệp vụ |
| Kiểm tra message đã được ack | Ack callback/metric hoặc quan sát broker phù hợp | Trạng thái database không chứng minh ack |

Không dùng Awaitility để đo chính xác latency hoặc benchmark throughput. Polling có overhead và chỉ cho biết điều kiện đã đúng tại một lần quan sát.

## 6. Thêm Awaitility vào dự án

Awaitility là thư viện dành cho kiểm thử bất đồng bộ. Ví dụ Maven với Awaitility 4.3.1:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.3.1</version>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án quản lý version qua dependency management hoặc version catalog, đặt version ở một nơi dùng chung. Awaitility 4.x hỗ trợ Java `Duration`, lambda và `untilAsserted`.

Các static import thường dùng:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

Awaitility mặc định chờ tối đa 10 giây và polling mỗi 100 ms. Trong test quan trọng, hãy đặt timeout và polling tường minh để không phụ thuộc cấu hình mặc định toàn cục.

## 7. Chờ một trạng thái database bằng Awaitility

Ví dụ service nhận yêu cầu tạo preview, worker cập nhật trạng thái job trong database. Test không cần đoán worker mất bao lâu; nó chỉ cần chờ trạng thái cuối.

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class PreviewWorkflowIT {

    @Test
    void completesPreviewWithinDeadline() {
        UUID jobId = UUID.randomUUID();

        previewPublisher.publish(new PreviewRequested(jobId));

        await()
                .alias("preview job " + jobId + " completed")
                .pollDelay(Duration.ZERO)
                .pollInterval(Duration.ofMillis(100))
                .atMost(Duration.ofSeconds(5))
                .untilAsserted(() ->
                        assertEquals(
                                JobStatus.COMPLETED,
                                jobRepository.findStatus(jobId).orElse(null)));
    }
}
~~~

`untilAsserted` chạy lại assertion khi assertion chưa đạt và kết thúc ngay khi assertion thành công. `alias` làm thông báo lỗi dễ đọc hơn nếu một test có nhiều điểm chờ.

Trong ví dụ, repository được truy vấn nhiều lần nên method đọc phải an toàn và không có side effect. Không gọi `publish`, `send`, `delete` hoặc cập nhật trạng thái bên trong lambda polling vì lambda có thể được thực thi nhiều lần.

Sử dụng ID duy nhất cho từng test giúp tránh đọc nhầm trạng thái từ một test khác hoặc từ lần chạy trước.

## 8. Polling, `atMost`, `pollDelay` và `pollInterval`

Một cấu hình Awaitility thường có bốn thành phần:

~~~java
await()
        .alias("document uploaded")
        .pollDelay(Duration.ZERO)
        .pollInterval(Duration.ofMillis(150))
        .atMost(Duration.ofSeconds(8))
        .until(() -> storageRepository.exists(objectKey));
~~~

- `atMost`: deadline tổng cho điều kiện.
- `pollDelay`: thời gian chờ trước lần kiểm tra đầu tiên.
- `pollInterval`: khoảng cách giữa các lần kiểm tra tiếp theo.
- `alias`: tên mô tả điểm chờ.

Polling quá dày có thể tạo tải không cần thiết lên database, broker hoặc API. Nếu test chờ một event trong queue, 100–250 ms thường là điểm khởi đầu hợp lý; nếu trạng thái cập nhật theo batch mỗi vài giây, polling có thể thưa hơn.

Polling interval không phải SLA. Một điều kiện có thể hoàn tất ngay sau lần kiểm tra, nhưng test chỉ phát hiện ở lần polling kế tiếp.

## 9. Chờ điều kiện ổn định và fail-fast

Đôi khi điều kiện đúng một lần chưa đủ. Ví dụ, một trạng thái có thể tạm thời là COMPLETED rồi bị một bước khác ghi đè. Awaitility hỗ trợ `during` để xác nhận điều kiện tiếp tục đúng trong một khoảng thời gian:

~~~java
await()
        .during(Duration.ofMillis(500))
        .atMost(Duration.ofSeconds(5))
        .until(() ->
                jobRepository.findStatus(jobId)
                        .filter(JobStatus.COMPLETED::equals)
                        .isPresent());
~~~

`during` phù hợp để kiểm tra trạng thái duy trì, không phải để chứng minh thời gian xử lý tối thiểu. Tránh dùng `atLeast` để ép một workflow phải chậm; điều đó khiến test phụ thuộc tốc độ máy và làm chậm suite.

Nếu có trạng thái không thể phục hồi, hãy fail-fast thay vì chờ hết timeout:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .failFast(
                "Preview job entered terminal failure",
                () -> jobRepository.findStatus(jobId)
                        .filter(JobStatus.FAILED::equals)
                        .isPresent())
        .until(() ->
                jobRepository.findStatus(jobId)
                        .filter(JobStatus.COMPLETED::equals)
                        .isPresent());
~~~

Ví dụ sẽ thất bại ngay khi job chuyển sang FAILED, thay vì đợi đủ 5 giây. Fail-fast hữu ích cho trạng thái terminal như FAILED, CANCELLED hoặc REJECTED.

## 10. Xử lý exception trong lúc chờ

Một điều kiện có thể tạm thời chưa đọc được:

- Record chưa tồn tại.
- Read replica chưa nhận dữ liệu.
- Resource emulator chưa sẵn sàng.
- Một endpoint trả lỗi tạm thời trong lúc khởi động.

Ưu tiên biểu diễn trạng thái chưa có dữ liệu bằng `Optional`, boolean hoặc trạng thái rõ ràng. Nếu thật sự cần bỏ qua exception trung gian, chỉ ignore loại exception cụ thể:

~~~java
await()
        .ignoreException(TransientDataAccessResourceException.class)
        .atMost(Duration.ofSeconds(5))
        .until(() -> repository.isVisible(jobId));
~~~

Không dùng `ignoreExceptions()` cho mọi exception. Nếu cấu hình quá rộng, lỗi sai SQL, lỗi credentials hoặc lỗi lập trình có thể bị biến thành timeout khó chẩn đoán.

Awaitility mặc định có thể thu thập uncaught exception từ các thread khác và chuyển lỗi về thread đang chờ. Điều này hữu ích khi worker ném exception ngoài test thread. Không tắt cơ chế này chỉ để test chuyển từ fail sang pass; hãy tìm và xử lý exception gốc.

Awaitility không tự bảo đảm thread safety hoặc memory visibility. Điều kiện cần đọc dữ liệu từ repository/thread-safe collection hoặc biến có cơ chế đồng bộ phù hợp. Không dùng một field mutable bình thường được ghi từ worker rồi đọc từ test mà không có happens-before hoặc synchronization.

## 11. Kiểm thử Spring `@Async`

`@Async` đưa lời gọi method vào `TaskExecutor`; method trả về ngay cho caller. Method có giá trị trả về phải dùng `Future` hoặc `CompletableFuture`. Method `void` không truyền exception ngược về caller; cần `AsyncUncaughtExceptionHandler` nếu muốn xử lý lỗi đó.

Bật annotation-driven async bằng `@EnableAsync` trong cấu hình Spring. Executor có thể được đặt tên và chọn qua thuộc tính của `@Async`.

Ví dụ service:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PreviewDispatcher {
    private final PreviewWorker worker;

    public PreviewDispatcher(PreviewWorker worker) {
        this.worker = worker;
    }

    @Async("previewExecutor")
    public CompletableFuture<Void> dispatch(UUID jobId) {
        worker.generate(jobId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Test gọi bean được Spring inject, tức lời gọi đi qua proxy:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PreviewDispatcherIT {
    @Autowired
    PreviewDispatcher dispatcher;

    @Test
    void asyncMethodCompletesWithinDeadline() throws Exception {
        CompletableFuture<Void> result =
                dispatcher.dispatch(UUID.randomUUID());

        result.get(3, TimeUnit.SECONDS);
    }
}
~~~

Nếu cần xác minh side effect được commit, hãy chờ trạng thái trong database bằng Awaitility sau khi Future hoàn tất hoặc dùng Future như tín hiệu hoàn thành nếu contract của method bảo đảm nó chỉ hoàn tất sau side effect.

Các lỗi thường gặp:

- Gọi method `@Async` từ một method khác trong cùng object (self-invocation), khiến lời gọi không đi qua proxy.
- Test tự tạo object bằng `new` thay vì inject Spring bean.
- Executor queue bị đầy hoặc thread pool bị shutdown.
- Method `void` ném exception nhưng test chỉ chờ một flag không bao giờ được cập nhật.

## 12. Chờ `CompletableFuture` và phân biệt timeout với cancellation

Khi có Future trực tiếp, `get(timeout)` là cách đơn giản để chờ:

~~~java
CompletableFuture<UploadResult> future =
        storageService.uploadAsync(document);

UploadResult result = future.get(5, TimeUnit.SECONDS);
assertEquals(UploadStatus.STORED, result.status());
~~~

`get(timeout)` ném `TimeoutException` nếu Future chưa hoàn tất trong thời gian cho phép. Nó không mặc nhiên dừng tác vụ đang chạy. Nếu test muốn hủy công việc, cần gọi `cancel(true)` hoặc cơ chế cancellation của client, đồng thời xác minh tác vụ bên dưới có thực sự dừng hay không.

`CompletableFuture.orTimeout(...)` làm Future hoàn tất exceptional khi hết thời gian, nhưng không đảm bảo I/O bên ngoài hoặc tác vụ đã submit bị hủy. Không nhầm “Future báo timeout” với “server không còn xử lý request”.

Nếu Future chỉ báo publisher đã gửi message, hãy tiếp tục chờ trạng thái consumer riêng. Completion của publish future thường chỉ chứng minh broker đã chấp nhận publish, không chứng minh subscriber đã xử lý message.

## 13. Kiểm thử luồng SQS với Spring Cloud AWS

Một integration test có thể gửi message qua `SqsTemplate`, sau đó chờ `@SqsListener` cập nhật trạng thái nghiệp vụ:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import io.awspring.cloud.sqs.operations.SqsTemplate;

@SpringBootTest
class PreviewQueueIT {
    @Autowired
    SqsTemplate sqsTemplate;

    @Autowired
    JobRepository jobRepository;

    @Test
    void waitsUntilListenerCompletesJob() {
        UUID jobId = UUID.randomUUID();
        jobRepository.createPending(jobId);

        sqsTemplate.send("preview-requests", new PreviewRequested(jobId));

        await()
                .alias("SQS preview job " + jobId)
                .pollInterval(Duration.ofMillis(150))
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertEquals(
                                JobStatus.COMPLETED,
                                jobRepository.findStatus(jobId).orElse(null)));
    }
}
~~~

Listener cần hoàn tất phần xử lý đồng bộ trước khi framework acknowledge message theo acknowledgement mode đang cấu hình:

~~~java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
class PreviewRequestListener {
    private final PreviewProcessor processor;

    PreviewRequestListener(PreviewProcessor processor) {
        this.processor = processor;
    }

    @SqsListener("preview-requests")
    public void handle(PreviewRequested event) {
        processor.generateAndPersist(event.jobId());
    }
}
~~~

Ví dụ dùng tên queue đã được tạo trong test environment. Khi chạy với LocalStack/Testcontainers, cấu hình endpoint và resource trước khi Spring listener container khởi động.

Không gọi một method `@Async void` rồi trả về ngay từ listener nếu acknowledgement phụ thuộc vào việc xử lý hoàn tất. Khi listener trả về thành công, container có thể xem message đã xử lý xong và acknowledge trong khi worker nền vẫn đang chạy. Nếu cần xử lý bất đồng bộ, dùng cơ chế listener/acknowledgement được Spring Cloud AWS hỗ trợ và chỉ ack sau khi side effect bền vững.

## 14. Kiểm thử Pub/Sub và acknowledgment

Với Spring Framework on Google Cloud, `PubSubTemplate.publish()` trả về một future. Có thể chờ publish hoàn tất với timeout:

~~~java
String messageId = pubSubTemplate
        .publish("preview-requests", new PreviewRequested(jobId))
        .get(5, TimeUnit.SECONDS);
~~~

Sau đó, dùng Awaitility để chờ consumer cập nhật database:

~~~java
await()
        .alias("Pub/Sub job " + jobId + " completed")
        .pollInterval(Duration.ofMillis(150))
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertEquals(
                        JobStatus.COMPLETED,
                        jobRepository.findStatus(jobId).orElse(null)));
~~~

Hai bước kiểm tra hai điều khác nhau:

- Publish future hoàn tất: publisher đã nhận kết quả gửi message.
- Database có trạng thái COMPLETED: consumer đã thực hiện side effect mà test quan tâm.

Với subscriber, acknowledgment phải diễn ra sau khi xử lý thành công theo contract. `PubSubTemplate` hỗ trợ ack/nack; `PubSubInboundChannelAdapter` có các chế độ AUTO, AUTO_ACK và MANUAL. Chọn mode phù hợp với error handler. Nếu error handler nuốt exception và hoàn tất bình thường, adapter có thể xem flow là thành công và ack message.

## 15. Ack deadline, visibility timeout và redelivery

Timeout của test không thay thế timeout của broker:

| Broker | Cơ chế | Khi xử lý quá thời hạn |
|---|---|---|
| Amazon SQS | Visibility timeout | Message có thể xuất hiện lại và được consumer khác nhận |
| Google Cloud Pub/Sub | Ack deadline | Message chưa ack có thể được redeliver; client có thể gia hạn ack deadline |

Với SQS, Spring Cloud AWS cho phép cấu hình visibility timeout hoặc gia hạn visibility trong lúc listener xử lý. Với Pub/Sub, subscriber client có thể tự gia hạn ack deadline; Spring Framework on Google Cloud cung cấp `max-ack-extension-period` để giới hạn thời gian gia hạn.

Test nên xác minh:

- Message không bị ack trước khi business transaction commit.
- Message được redeliver nếu consumer thất bại theo policy.
- Consumer idempotent khi cùng một event được giao lại.
- Retry và DLQ behavior đúng với cấu hình đã kiểm thử.
- Job không bị đánh dấu COMPLETED trước khi kết quả được lưu bền vững.

Đừng cố định test vào một thời điểm redelivery chính xác nếu broker dùng polling, backoff hoặc scheduling nội bộ. Hãy chờ điều kiện có ý nghĩa như `attemptCount >= 2`, trạng thái RETRYING hoặc message xuất hiện ở DLQ trong deadline hợp lý.

## 16. Retry, backoff và kiểm tra số lần thử

Retry thường có delay tăng dần và có thể thêm jitter. Vì vậy, test không nên giả định lần thử thứ hai luôn diễn ra đúng 200 ms sau lần đầu.

Có thể kiểm tra bằng trạng thái/metric:

~~~java
await()
        .alias("dependency retry observed")
        .pollInterval(Duration.ofMillis(100))
        .atMost(Duration.ofSeconds(5))
        .until(() -> retryRepository.countAttempts(jobId) >= 2);
~~~

Đối với test unit, inject một abstraction cho backoff/sleeper hoặc scheduler để test có thể kích hoạt lần retry mà không chờ thời gian thực. Với integration test, giữ retry policy thực nhưng đặt deadline đủ lớn và kiểm tra kết quả cuối cùng.

Không đặt retry vô hạn trong test. Một lỗi vĩnh viễn cần chuyển sang FAILED/DLQ và phải được test nhận diện bằng fail-fast condition. Nếu retry không có giới hạn, test có thể chờ đến outer test timeout mà không cho biết workflow bị kẹt ở đâu.

## 17. Virtual time, `Clock` và scheduler có thể điều khiển

### 17.1. Reactor virtual time

Với Reactor, `StepVerifier.withVirtualTime` cho phép kiểm tra publisher có delay/interval mà không đợi đồng hồ thực:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsThreeTicksWithoutWaitingInRealTime() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofSeconds(1)).take(3))
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
}
~~~

Tạo publisher bên trong supplier để Reactor cài virtual scheduler trước khi publisher được khởi tạo. Virtual time chỉ áp dụng cho scheduler được Reactor hỗ trợ; một HTTP client hoặc thread pool bên ngoài vẫn dùng thời gian thật.

### 17.2. Inject `Clock` cho logic thời gian

Không gọi `Instant.now()` trực tiếp trong business logic nếu test cần kiểm tra thời hạn. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class DownloadTokenService {
    private final Clock clock;

    public DownloadTokenService(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAt() {
        return Instant.now(clock).plus(15, ChronoUnit.MINUTES);
    }
}
~~~

Trong unit test, dùng `Clock.fixed` để đặt thời điểm xác định:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-24T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Khi cần tiến thời gian, dùng một `Clock` test có thể điều chỉnh hoặc abstraction `TimeProvider` do dự án định nghĩa. `Clock.fixed` không tự chạy nhanh theo thời gian; nó luôn trả cùng một instant.

### 17.3. Scheduler có thể điều khiển

Với `@Scheduled`, delayed retry hoặc tác vụ định kỳ, tách phần tính thời điểm khỏi cơ chế thực thi. Inject `TaskScheduler` hoặc một interface scheduler do ứng dụng sở hữu, rồi thay bằng implementation test có thể kích hoạt task thủ công. Với Reactor, dùng `VirtualTimeScheduler`/`StepVerifier`.

Không cố dùng Awaitility để chờ một lịch chạy sau 24 giờ. Hãy điều khiển scheduler hoặc clock để kiểm tra logic lập lịch và chỉ dùng một smoke test ngắn để xác minh wiring thực tế.

## 18. Race condition, transaction và cleanup

Một test bất đồng bộ có thể thất bại dù code đúng nếu dữ liệu test chưa được commit hoặc tài nguyên đã bị dọn quá sớm.

### 18.1. Transaction chưa commit

Spring test transaction thường gắn với thread của test. Worker chạy ở thread khác có thể không nhìn thấy dữ liệu chưa commit. Nếu test publish message trong một transaction chưa commit, consumer có thể đọc dữ liệu không tồn tại hoặc test rollback trước khi worker hoàn tất.

Đối với integration test bất đồng bộ:

- Tạo dữ liệu cần thiết bằng transaction đã commit trước khi publish.
- Không giả định transaction của test tự bao phủ thread của consumer.
- Dọn dữ liệu sau khi consumer hoàn tất.
- Nếu cần kiểm tra outbox, xác minh commit của outbox trước khi chờ publisher relay.

### 18.2. Timeout preemptive và ThreadLocal

JUnit `assertTimeout` chạy đoạn code trong cùng thread và báo lỗi nếu quá thời gian; nó không chủ động dừng đoạn code đang chạy. `assertTimeoutPreemptively` chạy đoạn code trong thread khác và ngắt khi timeout. Điều này có thể làm mất ngữ cảnh `ThreadLocal`, đặc biệt là transaction context của Spring. Một thao tác database trong thread mới có thể commit độc lập dù transaction của test thread bị rollback.

Không dùng `assertTimeoutPreemptively` quanh code phụ thuộc Spring transaction, security context hoặc các ThreadLocal khác nếu chưa hiểu hệ quả. Đặt timeout ở mức test bằng chế độ thread phù hợp và dùng deadline riêng cho thao tác bất đồng bộ.

### 18.3. Cleanup

Chỉ cleanup sau khi workflow đã kết thúc hoặc đã bị hủy một cách có kiểm soát:

- Dừng listener container trước khi xóa queue/subscription.
- Chờ message đang xử lý hoàn tất hoặc xác minh đã được redeliver.
- Xóa bucket/object, topic/subscription, queue và record test.
- Dùng resource name có UUID để các test song song không đụng nhau.
- Dùng `try/finally` hoặc lifecycle callback để cleanup khi assertion thất bại.
- Không để `@Async` task chạy tiếp sau khi Spring context đã đóng.

## 19. Chẩn đoán timeout và ổn định CI

Khi Awaitility timeout, đừng chỉ tăng timeout lên. Ghi lại trạng thái trung gian để biết workflow dừng ở đâu.

Nên thu thập:

- Job ID/correlation ID và trạng thái cuối đọc được.
- Số lần retry và error class gần nhất.
- Message ID, queue/subscription và thời điểm publish.
- Consumer lag, queue age, visibility/ack deadline nếu có.
- Log của listener, worker và dependency.
- Thời gian đã trôi qua và poll count.

Awaitility hỗ trợ condition evaluation listener để ghi log giá trị trung gian. Ví dụ:

~~~java
await()
        .conditionEvaluationListener(
                condition -> log.debug(
                        "Waiting for job {}: elapsed={}ms, remaining={}ms",
                        jobId,
                        condition.getElapsedTimeInMS(),
                        condition.getRemainingTimeInMS()))
        .atMost(Duration.ofSeconds(5))
        .until(() -> jobRepository.isCompleted(jobId));
~~~

Các nguyên tắc giúp CI ổn định:

1. Đặt timeout/poll interval tường minh, không phụ thuộc default toàn cục.
2. Poll một truy vấn đọc nhẹ, không tạo thêm message hoặc side effect.
3. Dùng resource ID riêng cho từng test.
4. Tránh giả định thứ tự hoàn tất giữa các consumer song song.
5. Giới hạn số test chạy đồng thời nếu dùng chung emulator/broker.
6. Dùng virtual time cho logic timer và retry thuần.
7. Chờ trạng thái nghiệp vụ thay vì chờ một khoảng thời gian cố định.
8. Khi test fail, lưu logs/container output trước khi cleanup.

Nếu test thỉnh thoảng timeout, so sánh poll history, CI load, consumer concurrency, database connection pool và broker backlog trước khi tăng deadline.

## 20. Tổng kết và bài tập thực hành

Kiểm thử bất đồng bộ cần chờ **điều kiện có thể quan sát** với deadline hữu hạn. Awaitility phù hợp để chờ trạng thái database, job hoặc message consumer; `Future.get(timeout)` phù hợp khi có Future trực tiếp; JUnit timeout giới hạn thời gian test; Reactor virtual time và injected `Clock`/scheduler giúp kiểm tra logic thời gian mà không phải chờ đồng hồ thực.

Timeout phải được thiết kế theo từng lớp: request, retry, workflow, condition, test và broker acknowledgment. Với SQS/Pub/Sub, publish hoàn tất không đồng nghĩa consumer hoàn tất; ack/visibility deadline và redelivery cần được kiểm thử riêng. Đặc biệt, chỉ acknowledge message sau khi side effect nghiệp vụ đã bền vững.

### Bài tập A — Chờ job hoàn tất

Tạo endpoint nhận yêu cầu preview và trả job ID. Worker chạy bất đồng bộ, cập nhật trạng thái trong database. Viết integration test gửi request rồi dùng Awaitility chờ COMPLETED trong 5 giây. Khi FAILED xuất hiện, test phải fail-fast.

### Bài tập B — Kiểm thử SQS

Gửi `PreviewRequested` qua `SqsTemplate`, nhận bằng `@SqsListener` và chờ trạng thái job. Thử làm handler ném exception để quan sát retry/redelivery. Xác minh message không bị ack trước khi transaction commit.

### Bài tập C — Kiểm thử Pub/Sub

Publish event bằng `PubSubTemplate`, chờ publish future hoàn tất, rồi chờ subscriber ghi kết quả. Thử các ack mode AUTO, AUTO_ACK và MANUAL; quan sát khác biệt khi handler ném exception hoặc error handler xử lý xong.

### Bài tập D — Retry có deadline

Tạo dependency giả lập lỗi hai lần rồi thành công ở lần thứ ba. Đặt timeout cho mỗi attempt và backoff. Xác minh tổng thời gian nằm trong deadline, số lần thử đúng và không có retry vô hạn.

### Bài tập E — Virtual time

Viết Reactor pipeline có `delayElements` hoặc `retryWhen`. Dùng `StepVerifier.withVirtualTime` để xác minh thứ tự event và backoff mà không phải đợi thời gian thật.

### Bài tập F — Transaction và race condition

Viết một test transactional publish message trước commit, quan sát consumer không đọc được dữ liệu chưa commit. Sau đó sửa test để commit trước khi publish và cleanup sau khi consumer hoàn tất.

### Câu hỏi tự kiểm tra

1. **Vì sao `Thread.sleep()` làm test flaky?** Vì nó chờ một khoảng cố định, không kiểm tra điều kiện và phụ thuộc tải máy.
2. **`atMost` trong Awaitility biểu thị điều gì?** Deadline tối đa để điều kiện trở thành đúng.
3. **`pollInterval` có phải SLA không?** Không; nó chỉ quy định tần suất kiểm tra điều kiện.
4. **Vì sao không đặt side effect trong lambda Awaitility?** Lambda có thể chạy nhiều lần.
5. **Khi nào dùng `untilAsserted`?** Khi muốn chạy lại assertion cho đến khi assertion thành công hoặc hết deadline.
6. **`during` dùng để làm gì?** Xác minh điều kiện duy trì đúng trong một khoảng thời gian.
7. **`Future.get(timeout)` có tự hủy tác vụ không?** Không; timeout chờ không đảm bảo tác vụ nền hoặc I/O đã dừng.
8. **Publish future hoàn tất có chứng minh consumer đã xử lý message không?** Không; cần kiểm tra side effect hoặc tín hiệu consumer riêng.
9. **SQS visibility timeout và Pub/Sub ack deadline ảnh hưởng thế nào?** Nếu message chưa được ack trước hạn, broker có thể giao lại.
10. **Vì sao `assertTimeoutPreemptively` có thể nguy hiểm với Spring transaction?** Vì code chạy ở thread khác và không dùng transaction ThreadLocal của test thread.
11. **Khi nào nên dùng virtual time?** Khi kiểm thử timer, delay, interval hoặc retry logic do scheduler hỗ trợ.
12. **Làm sao tránh race condition giữa test và consumer?** Dùng ID riêng, commit dữ liệu trước khi publish, chờ trạng thái bền vững và cleanup sau khi xử lý hoàn tất.

### Tài liệu tham khảo chính thức

- [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage)
- [Awaitility — Changelog](https://github.com/awaitility/awaitility/blob/master/changelog.txt)
- [JUnit 5 — Assertions and timeouts](https://docs.junit.org/5.14.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html)
- [JUnit 5 — User Guide, timeout thread modes](https://docs.junit.org/5.14.0/user-guide/index.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Cloud AWS — SQS sending, listeners and acknowledgements](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html)
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html)
- [Google Cloud — Pub/Sub subscriber acknowledgement deadlines](https://cloud.google.com/pubsub/docs/subscriber)
- [Project Reactor — Testing with StepVerifier and virtual time](https://projectreactor.io/docs/core/release/reference/testing.html)
