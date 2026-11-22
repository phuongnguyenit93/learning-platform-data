# Đợi điều kiện với giới hạn thay vì `Thread.sleep` cố định

Trong kiểm thử bất đồng bộ và xử lý song song, kết quả thường không xuất hiện ngay sau khi gọi phương thức. Một tác vụ có thể chạy trên executor, một event listener có thể được gọi sau khi sự kiện được phát, một message consumer có thể xử lý sau khi broker giao message, hoặc dữ liệu có thể chỉ nhìn thấy sau khi transaction khác commit.

Một cách làm dễ gặp là gọi `Thread.sleep(500)` rồi kiểm tra kết quả. Cách này chờ một khoảng thời gian cố định mà không biết công việc đã hoàn tất hay chưa. Nếu tác vụ xong sau 50 ms, test vẫn lãng phí thời gian còn lại. Nếu tác vụ cần 700 ms, test vẫn thất bại dù hệ thống hoạt động đúng. Trên CI, tải máy và lịch chạy thread thay đổi khiến một khoảng ngủ có vẻ đủ ở máy cá nhân trở thành nguyên nhân gây test chập chờn.

Thay vào đó, test nên chờ một điều kiện có ý nghĩa và đặt thời hạn tối đa. Điều kiện có thể là trạng thái chuyển sang `COMPLETED`, bản ghi xuất hiện trong repository, callback được gọi, queue nhận message hoặc future hoàn tất. Khi quá hạn, test thất bại với thông tin rõ ràng. Khi điều kiện xuất hiện sớm, test tiếp tục ngay.

## 1. Vì sao `Thread.sleep` cố định làm test thiếu ổn định?

Ví dụ một service khởi chạy tác vụ nền để tạo báo cáo:

```java
reportService.generateAsync(reportId);

Thread.sleep(500);

assertThat(reportRepository.findById(reportId)).isPresent();
```

Đoạn test này giả định 500 ms luôn đủ để tác vụ hoàn tất. Nhưng thời gian thực tế phụ thuộc vào nhiều yếu tố:

- Executor có thread rảnh hay đang xử lý các tác vụ khác.
- Máy CI có đang chịu tải CPU hoặc I/O cao không.
- Tác vụ có gọi database, HTTP service hoặc message broker không.
- Transaction đã commit và dữ liệu đã nhìn thấy từ connection khác chưa.
- Thread của test và thread nền được scheduler cấp CPU vào thời điểm nào.

`Thread.sleep` không đồng bộ hóa hai thread, không xác nhận tác vụ đã chạy và không đảm bảo dữ liệu được publish an toàn giữa các thread. Nó chỉ tạm dừng thread hiện tại.

Hai tình huống minh họa:

```text
Tác vụ hoàn tất sau 50 ms:
Test:   start ---------------- sleep 500 ms ---------------- assert
Worker:       start -- done
                              ^ test chờ thêm khoảng 450 ms không cần thiết

Tác vụ hoàn tất sau 700 ms:
Test:   start ---------------- sleep 500 ms -- assert (quá sớm)
Worker:       start -------------------------------- done
```

Chờ theo điều kiện sẽ lặp lại việc kiểm tra cho đến khi điều kiện đúng hoặc hết thời hạn. Test vì thế thích ứng với thời gian hoàn tất thực tế trong giới hạn đã chọn.

## 2. Chờ điều kiện bằng Awaitility

Awaitility là thư viện Java giúp viết assertion cho trạng thái bất đồng bộ theo cách dễ đọc. Thay vì tự viết vòng lặp, test mô tả điều kiện cần đạt và thời hạn tối đa.

Thêm dependency vào cấu hình test:

```groovy
testImplementation 'org.awaitility:awaitility'
```

Ví dụ chờ bản ghi được tạo:

```java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

@Test
void waitsUntilBackgroundTaskCreatesReport() {
    reportService.generateAsync("report-42");

    await()
            .atMost(2, TimeUnit.SECONDS)
            .untilAsserted(() ->
                    assertThat(reportRepository.findById("report-42"))
                            .isPresent());
}
```

`untilAsserted(...)` chạy assertion lặp lại cho đến khi assertion thành công hoặc thời hạn kết thúc. Nếu repository chưa có dữ liệu ở lần kiểm tra đầu tiên, Awaitility tiếp tục chờ. Khi bản ghi xuất hiện, test hoàn tất ngay.

Một dạng khác là chờ giá trị thỏa mãn matcher:

```java
await()
        .atMost(3, TimeUnit.SECONDS)
        .until(
                () -> reportRepository.findStatusById("report-42"),
                equalTo(ReportStatus.COMPLETED));
```

Ở đây, `findStatusById` được gọi nhiều lần cho đến khi trả về `COMPLETED`. `equalTo` là matcher của Hamcrest. Có thể dùng `untilAsserted` với AssertJ nếu muốn giữ toàn bộ assertion trong cùng một phong cách.

### Chọn khoảng polling

Awaitility mặc định kiểm tra điều kiện theo khoảng polling được cấu hình. Có thể chỉ định rõ khoảng chờ giữa các lần kiểm tra:

```java
await()
        .pollDelay(20, TimeUnit.MILLISECONDS)
        .pollInterval(50, TimeUnit.MILLISECONDS)
        .atMost(2, TimeUnit.SECONDS)
        .untilAsserted(() ->
                assertThat(jobService.status("job-17"))
                        .isEqualTo(JobStatus.DONE));
```

- `pollDelay` là thời gian đợi trước lần kiểm tra đầu tiên.
- `pollInterval` là khoảng cách giữa các lần kiểm tra tiếp theo.
- `atMost` là thời hạn tổng tối đa để điều kiện trở thành đúng.

Không nên đặt polling quá dày nếu điều kiện truy vấn database, HTTP service hoặc hệ thống bên ngoài. Polling mỗi vài mili giây có thể tạo tải không cần thiết và làm test ảnh hưởng chính hệ thống đang được kiểm tra. Chọn chu kỳ phù hợp với tốc độ cập nhật và chi phí đọc trạng thái.

### Chờ nhiều điều kiện

Một tác vụ có thể chỉ được coi là hoàn tất khi cả trạng thái và kết quả đều sẵn sàng:

```java
await()
        .atMost(3, TimeUnit.SECONDS)
        .untilAsserted(() -> {
            assertThat(jobService.status("job-17"))
                    .isEqualTo(JobStatus.DONE);
            assertThat(resultRepository.findByJobId("job-17"))
                    .isPresent();
        });
```

Đặt các assertion liên quan trong cùng một `untilAsserted` giúp test chờ đến khi toàn bộ trạng thái cần thiết cùng thỏa mãn. Nếu chỉ kiểm tra status, test có thể chạy tiếp trước khi kết quả được ghi xong.

## 3. Dùng điều kiện có ý nghĩa và có thể quan sát

Điều kiện chờ cần phản ánh điều test thực sự quan tâm. Ví dụ, nếu yêu cầu là message đã được lưu, hãy chờ bản ghi xuất hiện; nếu yêu cầu là callback đã chạy, hãy chờ callback; nếu yêu cầu là tác vụ đã kết thúc, hãy chờ trạng thái terminal.

Một số điều kiện thường gặp:

| Công việc bất đồng bộ | Điều kiện nên chờ |
|---|---|
| Tạo bản ghi nền | Repository trả về bản ghi có id cần kiểm tra. |
| Xử lý message | Message có trạng thái `PROCESSED` hoặc kết quả tương ứng xuất hiện. |
| Gửi notification | Notification được ghi nhận hoặc mock collaborator nhận invocation. |
| Tạo file | File xuất hiện và có kích thước/nội dung mong đợi. |
| Job chạy nền | Trạng thái chuyển sang `COMPLETED` hoặc `FAILED`. |
| Cập nhật cache | Cache trả về giá trị mới. |
| WebSocket/SSE | Client nhận được event cần thiết. |
| Consumer xử lý batch | Số phần tử đã xử lý đạt ngưỡng mong đợi. |

Tránh chờ những điều kiện không chứng minh kết quả, chẳng hạn “đã qua 500 ms” hoặc “thread đang ở trạng thái RUNNABLE”. Trạng thái thread thường là chi tiết thực thi, không phải hợp đồng nghiệp vụ của ứng dụng.

## 4. Chờ callback bằng CountDownLatch

Không phải lúc nào cũng cần polling. Nếu API cung cấp callback hoặc test kiểm soát được điểm hoàn tất, primitive đồng bộ hóa như `CountDownLatch` thường chính xác và hiệu quả hơn.

Ví dụ một component gọi callback khi hoàn tất:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@Test
void waitsForAsyncCallback() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<ReportResult> result = new AtomicReference<>();

    reportService.generateAsync("report-42", value -> {
        result.set(value);
        completed.countDown();
    });

    assertThat(completed.await(2, TimeUnit.SECONDS))
            .as("report callback should complete within the deadline")
            .isTrue();
    assertThat(result.get().reportId()).isEqualTo("report-42");
}
```

`await(timeout, unit)` trả về `false` nếu hết thời gian mà latch chưa được mở. Vì vậy test có thể thất bại ngay tại assertion thời hạn thay vì chờ vô hạn.

`CountDownLatch` còn cung cấp bảo đảm visibility: các hành động của thread trước khi gọi `countDown()` xảy ra trước các hành động sau khi một thread khác `await()` thành công. Vì vậy, dữ liệu được ghi vào `AtomicReference` trước `countDown()` có thể được đọc sau khi `await()` trả về `true`.

Nếu callback có thể thất bại, hãy lưu cả exception và mở latch trong mọi nhánh kết thúc:

```java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<ReportResult> result = new AtomicReference<>();
AtomicReference<Throwable> failure = new AtomicReference<>();

reportService.generateAsync("report-42", (value, error) -> {
    if (error != null) {
        failure.set(error);
    } else {
        result.set(value);
    }
    completed.countDown();
});

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(failure.get()).isNull();
assertThat(result.get()).isNotNull();
```

Trong thiết kế callback thực tế, nên bảo đảm callback được gọi đúng một lần cho cả thành công và lỗi. Nếu callback không bao giờ được gọi khi tác vụ lỗi, test sẽ chỉ timeout và khó phân biệt lỗi nghiệp vụ với lỗi quên callback.

## 5. Chờ CompletableFuture với timeout

Nếu API bất đồng bộ trả về `CompletableFuture`, có thể dùng trực tiếp `get(timeout, unit)`. Cách này chờ đúng future đại diện cho công việc, không cần polling trạng thái bên ngoài.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Test
void waitsForFutureResult() throws Exception {
    CompletableFuture<ReportResult> future = reportService.generateAsync("report-42");

    ReportResult result = future.get(2, TimeUnit.SECONDS);

    assertThat(result.reportId()).isEqualTo("report-42");
    assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
}
```

Nếu future không hoàn tất trong thời hạn, `get` ném `TimeoutException`. Nếu công việc thất bại, `get` ném `ExecutionException` và exception gốc nằm trong `getCause()`.

```java
assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(ReportGenerationException.class);
```

Nếu test cần xác nhận timeout xảy ra, có thể dùng `assertThrows(TimeoutException.class, ...)`. Lưu ý `get(timeout, unit)` chỉ giới hạn thời gian chờ của thread gọi. Nó không tự hủy tác vụ nền khi timeout. Nếu cần dừng công việc, phải định nghĩa rõ chính sách cancellation và kiểm tra kết quả của `future.cancel(true)` cùng hành vi interrupt của tác vụ.

### Không dùng join khi cần giới hạn thời gian

`CompletableFuture.join()` chờ cho đến khi future hoàn tất và không nhận timeout. Trong test có nguy cơ treo, `get(timeout, unit)` hoặc một API có deadline phù hợp sẽ an toàn hơn. `join()` phù hợp khi đã có bảo đảm khác rằng future sẽ hoàn tất và test không cần deadline riêng.

## 6. Chờ executor hoàn tất

Khi test trực tiếp quản lý `ExecutorService`, có thể gọi `shutdown()` rồi dùng `awaitTermination(timeout, unit)` để chờ các tác vụ đã submit kết thúc:

```java
executor.shutdown();

assertThat(executor.awaitTermination(2, TimeUnit.SECONDS))
        .as("executor should terminate within the deadline")
        .isTrue();
```

Nếu hết thời hạn, test có thể gọi `shutdownNow()` trong khối cleanup để gửi interrupt đến các tác vụ đang chạy. Tác vụ cần hợp tác với interruption; không nên giả định mọi tác vụ đều dừng ngay khi nhận interrupt.

`awaitTermination` chỉ xác nhận executor đã chấm dứt sau shutdown. Nếu executor là thread pool dùng chung của Spring application context, không tự shutdown nó trong test method. Khi đó hãy chờ điều kiện nghiệp vụ của tác vụ hoặc để Spring quản lý vòng đời executor.

## 7. Kiểm thử `@Async` trong Spring

Spring `@Async` chạy phương thức trên executor được cấu hình. Một phương thức `@Async` có thể trả `CompletableFuture`, `Future` hoặc `void`. Với `void`, caller không có future để chờ; cần quan sát kết quả qua callback, repository, event hoặc một điều kiện có thể kiểm tra.

Ví dụ service trả `CompletableFuture`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @Async
    public CompletableFuture<ReportResult> generateAsync(String reportId) {
        ReportResult result = createReport(reportId);
        return CompletableFuture.completedFuture(result);
    }

    private ReportResult createReport(String reportId) {
        return new ReportResult(reportId, ReportStatus.COMPLETED);
    }
}
```

Ứng dụng cần bật async processing:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
```

Test có thể inject bean từ Spring context và chờ future:

```java
@SpringBootTest
class ReportServiceAsyncTest {

    @Autowired
    ReportService reportService;

    @Test
    void waitsForAsyncReportResult() throws Exception {
        ReportResult result = reportService.generateAsync("report-42")
                .get(2, TimeUnit.SECONDS);

        assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
    }
}
```

Phải gọi phương thức qua Spring proxy để `@Async` được áp dụng. Gọi một phương thức async từ một phương thức khác trong cùng instance (self-invocation) thường không đi qua proxy và có thể chạy đồng bộ. Vì vậy test tích hợp nên lấy bean từ context thay vì tự `new ReportService()` nếu mục tiêu là xác nhận cấu hình async của Spring.

Với phương thức `@Async void`, exception không được trả về caller qua future. Spring sử dụng `AsyncUncaughtExceptionHandler` để xử lý exception của phương thức void. Nếu cần assert lỗi, cân nhắc thiết kế API trả `CompletableFuture` hoặc ghi nhận kết quả lỗi vào một nơi quan sát được.

## 8. Chờ trạng thái eventual consistency bằng Awaitility

Một số tác vụ không cung cấp future hoặc callback. Ví dụ message broker giao message cho consumer và consumer cập nhật database sau đó. Khi ấy, chờ một điều kiện có thể quan sát từ hệ thống là hợp lý.

```java
@SpringBootTest
class OrderEventIntegrationTest {

    @Autowired
    ApplicationEventPublisher eventPublisher;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void waitsUntilOrderEventIsProcessed() {
        eventPublisher.publishEvent(new OrderPlaced("order-42"));

        await()
                .atMost(5, TimeUnit.SECONDS)
                .pollInterval(100, TimeUnit.MILLISECONDS)
                .untilAsserted(() ->
                        assertThat(orderRepository.findStatusById("order-42"))
                                .isEqualTo(OrderStatus.PROCESSED));
    }
}
```

Test không giả định listener sẽ chạy trong bao lâu. Nó chờ trạng thái nghiệp vụ `PROCESSED` trong tối đa năm giây. Nếu listener không được đăng ký, ném exception hoặc không cập nhật database, test thất bại khi hết hạn.

Với broker hoặc hệ thống ngoài tiến trình, nên dùng deadline phù hợp với SLA của môi trường test và đảm bảo fixture không bị dùng chung giữa các test. Một id duy nhất cho mỗi test giúp tránh việc test đọc nhầm bản ghi do test khác tạo.

### Chú ý transaction trong test

Nếu test method được đánh dấu `@Transactional`, transaction của test thường không commit trước khi method kết thúc. Tác vụ async chạy trên thread khác dùng transaction khác có thể không nhìn thấy dữ liệu chưa commit từ test thread. Ngược lại, dữ liệu do worker ghi có thể không được transaction test nhìn thấy theo cách mong đợi.

Khi kiểm tra xử lý bất đồng bộ qua database:

- Commit dữ liệu đầu vào trước khi tác vụ nền cần đọc nó.
- Dùng transaction riêng hoặc fixture được commit rõ ràng khi cần.
- Không giả định transaction context tự truyền sang thread `@Async`.
- Dọn dữ liệu sau test theo cách tương thích với transaction của worker.

Awaitility không giải quyết visibility hoặc isolation của database. Nó chỉ lặp lại điều kiện; dữ liệu cần được publish và commit đúng cách để thread đang kiểm tra có thể nhìn thấy.

## 9. Kiểm tra request MVC bất đồng bộ

Spring MVC có thể trả response bất đồng bộ bằng `Callable`, `DeferredResult` hoặc `WebAsyncTask`. Với MockMvc, không nên sleep trước khi kiểm tra response. Thay vào đó, xác nhận request đã chuyển sang async rồi gọi `asyncDispatch` để hoàn tất assertion trên kết quả.

```java
MvcResult result = mockMvc.perform(get("/reports/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk())
        .andExpect(content().string("report-ready"));
```

`asyncStarted()` xác nhận request đã rời khỏi luồng dispatch ban đầu để xử lý bất đồng bộ. `asyncDispatch(result)` chờ kết quả async theo cơ chế Spring Test và tiếp tục kiểm tra response. Nếu ứng dụng dùng một callback hoặc worker độc lập không thuộc async lifecycle của Spring MVC, hãy dùng future, latch hoặc Awaitility để chờ điều kiện tương ứng.

## 10. Kiểm thử reactive bằng StepVerifier

Với Reactor `Mono` và `Flux`, không cần polling trạng thái bằng `Thread.sleep`. `StepVerifier` subscribe vào publisher và đồng bộ assertion với tín hiệu reactive:

```java
StepVerifier.create(reportService.generate("report-42"))
        .assertNext(result -> {
            assertThat(result.reportId()).isEqualTo("report-42");
            assertThat(result.status()).isEqualTo(ReportStatus.COMPLETED);
        })
        .verifyComplete();
```

Nếu publisher có thể không phát tín hiệu, đặt giới hạn thời gian:

```java
StepVerifier.create(reportService.generate("report-42"))
        .expectNextCount(1)
        .verifyComplete(Duration.ofSeconds(2));
```

`verifyComplete()` chờ `onComplete`; overload có `Duration` giới hạn tổng thời gian chờ. Với publisher vô hạn, kiểm tra các phần tử cần thiết rồi gọi `thenCancel()` thay vì chờ hoàn tất.

## 11. Visibility và thread safety của điều kiện chờ

Polling chỉ hữu ích nếu thread test có thể nhìn thấy trạng thái do thread nền cập nhật. Một biến boolean thông thường được ghi từ worker và đọc từ test thread mà không có synchronization có thể gây data race:

```java
boolean completed = false;

// Worker thread: completed = true;
// Test thread: await().until(() -> completed);
```

Không có bảo đảm visibility giữa hai thread trong ví dụ này. Test có thể tiếp tục đọc giá trị cũ hoặc hành vi không nhất quán.

Hãy dùng cơ chế đồng bộ phù hợp:

- `AtomicBoolean`, `AtomicReference` hoặc các atomic type khác cho trạng thái đơn giản.
- `volatile` khi chỉ cần visibility cho một biến trạng thái và không có thao tác read-modify-write phức tạp.
- `CountDownLatch`, `Semaphore`, `CompletableFuture` hoặc `BlockingQueue` để đồng bộ sự kiện.
- Collection thread-safe hoặc repository/database với transaction và isolation phù hợp.

Ví dụ dùng `AtomicBoolean`:

```java
AtomicBoolean completed = new AtomicBoolean(false);

executor.submit(() -> completed.set(true));

await()
        .atMost(1, TimeUnit.SECONDS)
        .untilTrue(completed);
```

Atomic type cung cấp semantics bộ nhớ cần thiết để thread test đọc được cập nhật. Tuy vậy, nếu điều kiện gồm nhiều trường cần nhất quán với nhau, một atomic boolean đơn lẻ có thể không đủ; hãy publish một immutable result qua `AtomicReference` hoặc đồng bộ hóa toàn bộ trạng thái.

## 12. Timeout, polling và thời gian chạy của test

Đặt timeout phải dựa trên thời gian hợp lý của tác vụ và môi trường. Timeout quá ngắn làm test thất bại ngẫu nhiên; timeout quá dài làm lỗi thật bị phát hiện chậm và kéo dài suite.

Một số nguyên tắc thực tế:

1. Chọn deadline đủ lớn so với thời gian bình thường của tác vụ trong môi trường CI.
2. Polling đủ thưa để không tạo tải không cần thiết, nhưng đủ nhanh để test phản hồi sớm khi điều kiện đã đúng.
3. Dùng deadline cho mỗi thao tác chờ, tránh một vòng lặp không có giới hạn.
4. Khi test có nhiều bước bất đồng bộ, cân nhắc deadline tổng để tổng thời gian không vượt quá mức chấp nhận.
5. Khi timeout, thông báo nên nêu điều kiện mong đợi và id của công việc để dễ chẩn đoán.

JUnit có thể đặt giới hạn tổng cho test method:

```java
@Test
@Timeout(value = 8, unit = TimeUnit.SECONDS)
void processesEventWithinTheOverallDeadline() {
    // Test có thể dùng Awaitility với deadline ngắn hơn bên trong.
}
```

`@Timeout` là lớp bảo vệ cuối cùng. Nó không thay thế timeout cụ thể của `await`, `Future.get`, `CountDownLatch.await` hoặc `StepVerifier`, vì các API đó cho biết chính xác thao tác nào không hoàn tất.

## 13. Xử lý lỗi trong lúc chờ

Điều kiện chờ có thể ném exception tạm thời khi trạng thái chưa sẵn sàng. Ví dụ repository trả `Optional.empty()` trước khi worker ghi dữ liệu; cách viết assertion với `untilAsserted` cho phép Awaitility thử lại assertion.

Tuy nhiên, không nên bỏ qua mọi exception. Nếu code truy vấn ném `IllegalStateException` do cấu hình sai hoặc database mất kết nối, việc bỏ qua lỗi đến hết timeout có thể che nguyên nhân thật.

Chỉ cấu hình bỏ qua exception khi đó là trạng thái tạm thời đã biết và có thể phục hồi. Với lỗi bất ngờ, để test thất bại ngay giúp giữ thông tin nguyên nhân. Khi dùng `ignoreExceptions()`, cần cân nhắc phạm vi rộng của nó; có thể dùng điều kiện hẹp hơn để chỉ bỏ qua loại exception cụ thể.

Nếu timeout xảy ra, Awaitility cung cấp thông tin về điều kiện không đạt được. Có thể thêm mô tả bằng `alias(...)`:

```java
await()
        .alias("order-42 should reach PROCESSED state")
        .atMost(3, TimeUnit.SECONDS)
        .until(() -> orderRepository.findStatusById("order-42"),
                equalTo(OrderStatus.PROCESSED));
```

Tên điều kiện giúp log lỗi dễ đọc hơn khi suite có nhiều tác vụ nền chạy song song.

## 14. Khi nào dùng Awaitility, latch hay Future?

| Cơ chế | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Awaitility | Trạng thái chỉ có thể quan sát qua repository, cache, mock hoặc API khác | Polling có chi phí; cần điều kiện thread-safe và deadline rõ ràng. |
| `CountDownLatch` | Có callback hoặc một điểm báo hoàn tất rõ ràng | Latch chỉ đếm xuống, không mang kết quả; lưu kết quả/lỗi riêng và mở latch ở mọi nhánh kết thúc. |
| `CompletableFuture.get(timeout, unit)` | API trả về future đại diện cho công việc | Timeout chờ không tự hủy tác vụ; lỗi được bọc trong `ExecutionException`. |
| `ExecutorService.awaitTermination(...)` | Test sở hữu executor và muốn chờ executor kết thúc | Chỉ dùng sau `shutdown`; không shutdown executor dùng chung của Spring. |
| `StepVerifier` | Kết quả là `Mono`/`Flux` | Đồng bộ theo tín hiệu reactive; đặt timeout nếu publisher có thể không kết thúc. |
| MockMvc `asyncDispatch` | Controller Spring MVC trả async result | Dùng lifecycle async của Spring Test thay vì sleep. |

Ưu tiên chờ trực tiếp vào primitive mà API cung cấp. Nếu có `CompletableFuture`, chờ future. Nếu có callback, dùng latch hoặc future. Nếu chỉ có trạng thái cuối cùng ở database hoặc hệ thống ngoài, Awaitility phù hợp hơn.

## 15. Những lỗi thường gặp

### Thay `Thread.sleep(500)` bằng một vòng lặp tự viết không có deadline

Polling không có deadline vẫn có thể làm test treo vô hạn. Mọi cơ chế chờ cần có thời hạn tối đa và thông báo lỗi rõ ràng.

### Polling quá dày

Kiểm tra database hàng nghìn lần mỗi giây không làm tác vụ nền nhanh hơn. Nó chỉ tăng tải và có thể làm hệ thống test chậm hơn. Chọn `pollInterval` hợp lý.

### Chờ trạng thái không phải kết quả cuối cùng

Ví dụ status đã là `STARTED` không có nghĩa file đã ghi xong hoặc message đã commit. Chờ trạng thái phản ánh điều kiện mà test cần xác nhận.

### Dùng biến thường giữa các thread

Nếu không có memory visibility, polling có thể không bao giờ nhìn thấy cập nhật. Dùng atomic, volatile, latch, future hoặc cấu trúc thread-safe.

### Dùng `Future.get()` không có timeout

`get()` không tham số có thể chờ vô hạn. Dùng overload có thời hạn cho test.

### Bắt exception rồi tiếp tục chờ mọi trường hợp

Chỉ bỏ qua lỗi tạm thời có chủ đích. Lỗi lập trình, cấu hình hoặc kết nối cần được báo ngay để không bị che bởi thông báo timeout chung.

### Transaction test che mất dữ liệu của worker

Test transaction chưa commit có thể không nhìn thấy từ thread khác. Thiết kế fixture và commit boundary rõ ràng khi kiểm thử xử lý async qua database.

### Timeout quá ngắn hoặc không thống nhất

Timeout của Awaitility, future, client và JUnit cần được sắp xếp hợp lý. Timeout tổng của test nên lớn hơn deadline của từng thao tác bên trong một khoảng dự phòng đủ để cleanup và tạo thông báo lỗi.

## 16. Checklist cho test bất đồng bộ

- [ ] Test xác định một điều kiện nghiệp vụ cụ thể cần chờ.
- [ ] Mọi thao tác chờ đều có deadline tối đa.
- [ ] Dùng Awaitility khi chỉ có thể quan sát trạng thái eventual.
- [ ] Dùng latch hoặc future khi API có tín hiệu hoàn tất trực tiếp.
- [ ] Dùng `StepVerifier` cho publisher reactive.
- [ ] Không dùng `Thread.sleep` cố định để đoán thời gian tác vụ hoàn tất.
- [ ] Trạng thái được chia sẻ giữa các thread có cơ chế visibility/thread safety.
- [ ] Polling interval phù hợp với chi phí truy vấn và tốc độ cập nhật.
- [ ] Assertion xác nhận kết quả cuối cùng, không chỉ xác nhận tác vụ đã bắt đầu.
- [ ] Lỗi bất ngờ không bị bỏ qua trong lúc chờ.
- [ ] Transaction và commit boundary phù hợp với thread thực hiện tác vụ nền.
- [ ] Timeout ở cấp test method bảo vệ toàn bộ test khi cần.

Chờ điều kiện có giới hạn làm cho test bất đồng bộ phản ánh trạng thái thật của hệ thống. Awaitility phù hợp khi cần quan sát eventual state; latch và future phù hợp khi API báo trực tiếp lúc hoàn tất; `StepVerifier` phù hợp với publisher reactive. Kết hợp điều kiện có ý nghĩa, đồng bộ hóa an toàn và deadline rõ ràng giúp test phản hồi ngay khi công việc xong và thất bại có kiểm soát khi công việc không hoàn tất.
