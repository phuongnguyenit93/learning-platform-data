# Kiểm thử đồng thời, giới hạn tài nguyên và đóng đúng vòng đời

Một chương trình chạy đồng thời chỉ đáng tin cậy khi có thể chứng minh ba điều: các tác vụ phối hợp đúng dưới nhiều lịch chạy khác nhau, lượng tài nguyên sử dụng luôn nằm trong giới hạn dự kiến, và mọi tác vụ/tài nguyên đều kết thúc khi công việc hoàn tất hoặc bị hủy.

Trong Java 26, có thể xây dựng các kiểm thử này bằng API ổn định như `ExecutorService`, virtual threads, `Semaphore`, `CountDownLatch`, `Future` và try-with-resources. Java 26 còn bổ sung `Process.close()`, giúp quản lý vòng đời tiến trình hệ điều hành bằng cùng mô hình `AutoCloseable`. **Structured Concurrency (JEP 525) vẫn là preview lần thứ sáu trong JDK 26**; đây là lựa chọn thử nghiệm hữu ích cho nhóm tác vụ có quan hệ cha-con, nhưng cần bật preview và không nên coi API là hợp đồng ổn định.

Bài học thuộc module **JAVA_VERSION_JAVA26**. Nội dung tập trung vào cách tạo kiểm thử đồng thời có thể tái lập, kiểm soát số tác vụ đang chạy và hàng đợi, xử lý timeout/cancellation, đóng executor/process đúng cách, đồng thời phân biệt API ổn định với StructuredTaskScope preview. Các ví dụ dùng API còn áp dụng trên JDK 26 và 27.

Trong tổng thể Java 26, HTTP/3 và các cập nhật bảo mật là những thay đổi ở lớp giao tiếp và nền tảng; primitive pattern matching còn ở preview, Vector API còn ở incubator, còn Structured Concurrency là preview. Các trạng thái này cần được phân biệt khi chọn tính năng cho sản phẩm. Riêng kiểm soát concurrency và vòng đời trong bài này dựa trên API ổn định; StructuredTaskScope chỉ được giới thiệu như một API preview có thể thử nghiệm.

## 1. Ba mục tiêu cần kiểm thử

| Mục tiêu | Câu hỏi cần trả lời | Bằng chứng kiểm thử |
|---|---|---|
| Tính đúng đắn đồng thời | Khi nhiều thread cùng đọc/ghi hoặc gọi một dịch vụ, kết quả có còn đúng không? | Invariant, số lần xử lý, dữ liệu không mất/trùng, kết quả không phụ thuộc thứ tự lịch chạy |
| Giới hạn tài nguyên | Khi tải tăng, số thao tác đồng thời, thread, queue, connection và process có vượt ngưỡng không? | Số tác vụ đang chạy cực đại, queue depth, rejection, thời gian chờ permit, memory và file descriptor |
| Vòng đời | Khi hoàn tất, timeout, lỗi hoặc shutdown, tác vụ và tài nguyên có được dọn dẹp không? | Executor terminated, task không còn chạy, stream/connection đóng, process đã kết thúc, interrupt được xử lý |

Ba mục tiêu liên quan nhưng không thay thế nhau. Một chương trình có thể cho kết quả đúng trong thử nghiệm nhỏ nhưng vẫn tạo hàng đợi vô hạn khi tải tăng. Một executor có thể đóng đúng nhưng các task bên trong không giải phóng socket hoặc transaction. Một semaphore có thể giới hạn số request nhưng không tự bảo đảm dữ liệu được cập nhật thread-safe.

Hãy xác định invariant và giới hạn trước khi viết test. Ví dụ:

- Mỗi đơn hàng chỉ được ghi nhận một lần dù có nhiều request đồng thời.
- Tối đa 12 truy vấn cùng truy cập một dịch vụ ngoài.
- Tối đa 8 tác vụ chờ trong queue của worker pool.
- Khi request timeout, không còn task nền tiếp tục giữ connection.
- Sau khi test kết thúc, executor đã shutdown và không còn task thuộc test chạy nền.

## 2. Chọn API ổn định hay preview trong JDK 26

| API | Trạng thái | Dùng cho |
|---|---|---|
| `ExecutorService`, `Future`, `ThreadPoolExecutor` | Stable | Điều phối task, giới hạn worker/queue, lấy kết quả và đóng executor |
| `ExecutorService.close()` | Stable từ Java 19 | Shutdown orderly bằng try-with-resources |
| Virtual threads và `newVirtualThreadPerTaskExecutor()` | Stable từ Java 21 | Tạo task I/O đồng thời với chi phí thread thấp |
| `Semaphore`, `CountDownLatch`, `CyclicBarrier` | Stable | Giới hạn concurrency và đồng bộ kiểm thử |
| `Process.close()` | Stable mới từ JDK 26 | Đóng stream và chờ tiến trình con kết thúc |
| `StructuredTaskScope` | **Preview lần thứ sáu trong JDK 26, JEP 525** | Gom các subtask có quan hệ trong một scope, xử lý lỗi và cancellation cùng nhau |

Structured Concurrency tiếp tục là preview ở JDK 27 (lần thứ bảy, JEP 533) và API tiếp tục thay đổi. Nếu cần triển khai production với API ổn định, dùng `ExecutorService`, `Future`, cancellation và try-with-resources. Có thể dùng StructuredTaskScope trong nhánh thử nghiệm để đánh giá mô hình structured concurrency, nhưng phải bật preview khi biên dịch/chạy và kiểm tra lại mã khi nâng JDK.

## 3. Kiểm thử đồng thời mà không phụ thuộc Thread.sleep()

Không dùng `Thread.sleep()` để giả định các thread đã đến một điểm cụ thể. Lịch chạy thay đổi theo CPU, tải máy, JIT và hệ điều hành; sleep chỉ trì hoãn thread trong một khoảng thời gian, không chứng minh thread khác đã chạy đến đâu.

Dùng các công cụ đồng bộ phù hợp:

| Công cụ | Cách dùng trong test |
|---|---|
| `CountDownLatch` | Cho N worker báo đã sẵn sàng, sau đó mở cổng để chúng bắt đầu gần đồng thời |
| `CyclicBarrier` | Cho một nhóm thread chờ nhau tại nhiều vòng đồng bộ |
| `Phaser` | Điều phối nhiều phase với số participant thay đổi |
| `Semaphore` | Giới hạn số thread được đi vào một vùng thao tác |
| `Future.get(timeout, unit)` | Chờ kết quả với giới hạn thời gian và làm lộ task bị treo |
| `AtomicInteger` / `LongAdder` | Đếm hoạt động đồng thời hoặc tổng số thao tác mà không tạo data race |

Ví dụ kiểm tra nhiều worker cùng bắt đầu:

    import java.util.ArrayList;
    import java.util.List;
    import java.util.concurrent.CountDownLatch;
    import java.util.concurrent.Executors;
    import java.util.concurrent.Future;
    import java.util.concurrent.TimeUnit;

    int workers = 20;
    CountDownLatch ready = new CountDownLatch(workers);
    CountDownLatch start = new CountDownLatch(1);
    CountDownLatch done = new CountDownLatch(workers);
    List<Future<?>> futures = new ArrayList<>();

    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        for (int i = 0; i < workers; i++) {
            futures.add(executor.submit(() -> {
                try {
                    ready.countDown();
                    start.await();

                    performOperation();

                } finally {
                    done.countDown();
                }
            }));
        }

        boolean allReady = ready.await(5, TimeUnit.SECONDS);
        // Luôn mở cổng để worker không mắc kẹt nếu assertion thất bại.
        start.countDown();

        if (!allReady) {
            throw new AssertionError("Không phải mọi worker đều sẵn sàng");
        }

        if (!done.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError("Worker không hoàn thành trong thời hạn");
        }

        // Lấy kết quả để lỗi bên trong task được truyền về test thread.
        for (Future<?> future : futures) {
            future.get();
        }
    }

`ready` xác nhận các worker đã đến cổng bắt đầu; `start` mở cổng cho cả nhóm; `done` xác nhận mọi worker đã kết thúc. Các timeout làm test thất bại rõ ràng nếu task bị kẹt. Trong test thực tế, cần giữ và kiểm tra các `Future` để thu nhận exception của task; không bỏ qua lỗi chỉ vì latch đã đếm đủ.

### Kiểm tra race condition

Để kiểm tra một thao tác cập nhật đồng thời, tạo nhiều worker, mở cổng cùng lúc rồi xác minh invariant sau khi tất cả kết thúc. Ví dụ, nếu mỗi worker tăng một bộ đếm N lần, tổng cuối cùng phải bằng số worker nhân số lần tăng. Dùng biến thường không đồng bộ để minh họa race là hữu ích, nhưng test production phải kiểm tra giải pháp thật: `AtomicInteger`, `LongAdder`, lock hoặc cấu trúc dữ liệu concurrent phù hợp.

Không chỉ chạy một lần. Lặp lại test với nhiều số worker, nhiều kích thước dữ liệu và các điểm tranh chấp khác nhau. Với lỗi memory visibility hoặc interleaving khó tái hiện, dùng công cụ stress test chuyên dụng như OpenJDK jcstress và chạy trên đúng kiến trúc CPU/runtime mục tiêu.

## 4. Kiểm tra giới hạn concurrency bằng Semaphore

Virtual thread giúp tạo nhiều tác vụ I/O đang chờ mà không chiếm một platform thread cho toàn bộ thời gian chờ. Tuy nhiên, virtual thread không làm cho database, API ngoài, file descriptor hay bộ nhớ trở nên vô hạn.

Nếu một dịch vụ chỉ chấp nhận tối đa 10 request đồng thời, dùng `Semaphore(10)` để giới hạn số tác vụ được đi vào vùng gọi dịch vụ:

    private final Semaphore permits = new Semaphore(10);

    Result callPartner() throws InterruptedException {
        permits.acquire();

        try {
            return partnerClient.call();
        } finally {
            permits.release();
        }
    }

Đặt `acquire()` ngay trước thao tác sử dụng tài nguyên và `release()` trong `finally`. Nếu có exception, timeout hoặc return sớm, permit vẫn được trả lại.

Nếu không muốn chờ vô thời hạn, dùng `tryAcquire(timeout, unit)`:

    if (!permits.tryAcquire(200, TimeUnit.MILLISECONDS)) {
        throw new RejectedExecutionException(
                "Partner service is at capacity"
        );
    }

    try {
        return partnerClient.call();
    } finally {
        permits.release();
    }

Thời gian chờ permit là một phần của latency request. Hãy ghi nhận số lần không lấy được permit và thời gian chờ; nếu không, ứng dụng có thể có p99 rất cao dù số request đồng thời vẫn nằm trong giới hạn.

### Kiểm thử giới hạn thực tế

Ví dụ sau tạo nhiều virtual thread, nhưng chỉ cho phép tối đa ba tác vụ đi vào vùng được bảo vệ. `CountDownLatch` giữ các task đang ở trong vùng để phép đo có thể quan sát concurrency cực đại:

    import java.util.ArrayList;
    import java.util.List;
    import java.util.concurrent.CountDownLatch;
    import java.util.concurrent.ExecutorService;
    import java.util.concurrent.Executors;
    import java.util.concurrent.Future;
    import java.util.concurrent.Semaphore;
    import java.util.concurrent.TimeUnit;
    import java.util.concurrent.atomic.AtomicInteger;

    public class SemaphoreLimitTest {
        public static void main(String[] args) throws Exception {
            int taskCount = 30;
            int limit = 3;

            Semaphore permits = new Semaphore(limit);
            AtomicInteger active = new AtomicInteger();
            AtomicInteger maxObserved = new AtomicInteger();

            CountDownLatch entered = new CountDownLatch(limit);
            CountDownLatch release = new CountDownLatch(1);

            List<Future<?>> futures = new ArrayList<>();

            try (ExecutorService executor =
                    Executors.newVirtualThreadPerTaskExecutor()) {

                try {
                    for (int i = 0; i < taskCount; i++) {
                        futures.add(executor.submit(() -> {
                            permits.acquire();

                            try {
                                int now = active.incrementAndGet();
                                maxObserved.accumulateAndGet(
                                        now,
                                        Math::max
                                );

                                entered.countDown();
                                release.await();

                            } finally {
                                active.decrementAndGet();
                                permits.release();
                            }
                        }));
                    }

                    if (!entered.await(5, TimeUnit.SECONDS)) {
                        throw new AssertionError(
                                "Không đạt số task đồng thời dự kiến"
                        );
                    }

                } finally {
                    // Mở cổng kể cả khi assertion hoặc test bị lỗi.
                    release.countDown();
                }

                for (Future<?> future : futures) {
                    future.get(5, TimeUnit.SECONDS);
                }
            }

            if (maxObserved.get() > limit) {
                throw new AssertionError(
                        "Concurrency vượt giới hạn: " + maxObserved.get()
                );
            }

            System.out.println("Max active: " + maxObserved.get());
        }
    }

Trong test, mỗi task chỉ tăng `active` sau khi lấy được permit và giảm trước khi trả permit. Giá trị lớn nhất được ghi bằng `accumulateAndGet`. Test sẽ thất bại nếu worker không vào được vùng kiểm tra trong thời hạn hoặc bất kỳ Future nào không hoàn tất.

Semaphore giới hạn **số thao tác đồng thời**, không giới hạn số request mỗi giây. Nếu cần rate limit, dùng thuật toán token bucket/leaky bucket hoặc dịch vụ rate limiter. Nếu connection pool đã giới hạn số connection database, pool đó thường đã là giới hạn concurrency; tránh thêm một semaphore khác có cùng mục đích mà không có lý do rõ ràng.

## 5. Giới hạn worker và hàng đợi bằng ThreadPoolExecutor

Khi cần giới hạn cả số platform worker và số task chờ, cấu hình `ThreadPoolExecutor` với queue có capacity hữu hạn:

    import java.util.concurrent.ArrayBlockingQueue;
    import java.util.concurrent.ThreadPoolExecutor;
    import java.util.concurrent.TimeUnit;

    try (var executor = new ThreadPoolExecutor(
            4,
            8,
            30,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(100),
            new ThreadPoolExecutor.AbortPolicy()
    )) {
        executor.submit(() -> processBatch());
    }

Trong ví dụ:

- Tối đa 4 worker được giữ ở core size.
- Khi core worker bận, task được đưa vào queue có tối đa 100 phần tử.
- Khi queue đầy, executor có thể tăng worker đến tối đa 8.
- Nếu cả worker tối đa và queue đều đầy, task mới bị từ chối bằng `RejectedExecutionException`.

Không nhầm `Executors.newFixedThreadPool(n)` với một hàng đợi có giới hạn. Factory này dùng số worker cố định nhưng queue công việc không giới hạn capacity; nếu producer gửi nhanh hơn tốc độ xử lý trong thời gian dài, queue có thể tăng và tiêu thụ bộ nhớ lớn.

### Chọn chính sách khi executor bão hòa

| Rejection policy | Hành vi | Khi phù hợp |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Ứng dụng cần biết và xử lý việc không nhận task |
| `CallerRunsPolicy` | Thread gửi task tự chạy task | Có thể tạo backpressure bằng cách làm chậm producer, nếu chạy task trên caller là an toàn |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Chỉ dùng khi mất task được chấp nhận theo nghiệp vụ |
| `DiscardOldestPolicy` | Bỏ task cũ nhất trong queue rồi thử gửi lại | Hiếm khi phù hợp; có thể làm mất công việc đang chờ |

Không chọn policy chỉ để tránh exception. Với tác vụ thanh toán, ghi dữ liệu hoặc gửi thông báo bắt buộc, bỏ task âm thầm thường không chấp nhận được. Hãy xác định rõ hệ thống sẽ từ chối request, retry có giới hạn, ghi vào durable queue hay áp dụng backpressure.

## 6. Virtual threads không phải là giới hạn tài nguyên

Virtual threads là API ổn định từ Java 21 và phù hợp với số lượng lớn tác vụ chủ yếu chờ I/O. Chúng không chạy code nhanh hơn platform thread và không làm CPU có thêm lõi xử lý.

Dùng executor tạo virtual thread cho mỗi task:

    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        Future<String> profile =
                executor.submit(() -> fetchProfile(userId));

        Future<String> orders =
                executor.submit(() -> fetchOrders(userId));

        return new Dashboard(profile.get(), orders.get());
    }

Executor này không phải thread pool. Mỗi task được thực thi bằng một virtual thread riêng. Không tạo pool virtual thread để tái sử dụng chúng như platform worker; nếu cần giới hạn số lần truy cập tài nguyên ngoài, dùng Semaphore hoặc pool tài nguyên tương ứng.

Cần đặt giới hạn ở các điểm thực sự khan hiếm:

- Số request đang gọi một partner API.
- Số connection database đang được mượn.
- Số file đang mở.
- Số process bên ngoài đang chạy.
- Số tác vụ được nhận vào hệ thống và lượng dữ liệu chờ trong bộ nhớ.

Không chỉ giới hạn concurrency mà quên tổng lượng task đang chờ. Nếu hàng triệu request cùng tạo virtual thread rồi chờ semaphore, số thao tác tới partner đã được giới hạn nhưng vẫn có thể tồn tại rất nhiều task, context và dữ liệu request trong bộ nhớ. Cần thêm admission control, giới hạn queue hoặc từ chối sớm khi hệ thống quá tải.

Virtual threads phù hợp với I/O-bound workload. Với CPU-bound workload, throughput vẫn bị giới hạn bởi số core; dùng pool có kích thước phù hợp với CPU và đo thực tế. Không dùng số lượng virtual thread lớn để che một thuật toán CPU đang quá tải.

### Thay đổi runtime trong JDK 26

JDK 26 cải thiện một tình huống của virtual threads: khi virtual thread chờ một thread khác hoàn tất class initialization, nó trong hầu hết trường hợp được unmount khỏi carrier. Điều này giải phóng platform thread cho virtual thread khác và giảm nguy cơ cạn carrier trong một tình huống deadlock đặc biệt. Đây là cải tiến runtime, không phải API mới; nó không có nghĩa mọi trường hợp pinning hoặc blocking đều biến mất. Vẫn cần đo trên JDK đích và tránh giữ monitor/khóa trong các vùng I/O blocking không cần thiết.

## 7. StructuredTaskScope trong JDK 26: dùng thử với preview

Structured concurrency nhóm các subtask thuộc cùng một công việc vào một scope. Scope có owner thread, các task được fork bên trong scope và owner join để lấy kết quả. Khi một subtask thất bại theo chính sách mặc định, các subtask còn lại bị cancel và được interrupt. Scope đóng sẽ đợi các thread của subtask kết thúc.

Ví dụ JDK 26:

    import java.util.concurrent.StructuredTaskScope;

    Dashboard loadDashboard(String userId)
            throws InterruptedException {

        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> fetchProfile(userId));
            var orders = scope.fork(() -> fetchOrders(userId));

            // Mặc định: đợi tất cả thành công hoặc hủy khi một task lỗi.
            scope.join();

            return new Dashboard(profile.get(), orders.get());
        }
    }

Quy tắc quan trọng:

- Chỉ owner thread được gọi `fork`, `join` và `close`.
- Fork các task trước khi gọi join.
- Sau khi fork, phải gọi join để nhận outcome.
- `close()` hủy scope nếu chưa bị hủy, interrupt các subtask còn chạy và đợi chúng kết thúc.
- Subtask phải phản hồi interruption. Nếu subtask mắc kẹt trong API không interruptible hoặc bỏ qua interrupt, `close()` có thể phải đợi rất lâu.
- Có thể cấu hình timeout cho scope bằng API preview; timeout hủy scope và interrupt subtask đang chạy.

Trong JDK 26, StructuredTaskScope là **JEP 525 — Sixth Preview**. Biên dịch và chạy cần bật preview:

    javac --release 26 --enable-preview -d out src/StructuredDemo.java
    java --enable-preview -cp out StructuredDemo

Không dùng đoạn mã preview trên như ví dụ stable API. JDK 27 tiếp tục ở JEP 533 — Seventh Preview và chữ ký API có thay đổi. Khi nâng JDK, đọc lại preview API specification và biên dịch lại mã thử nghiệm.

## 8. Cancellation và interruption phải có hợp đồng rõ ràng

`Future.cancel(true)` yêu cầu hủy task và nếu task đang chạy thì gửi interrupt tới thread thực thi. Nó không cưỡng bức dừng mọi đoạn code. Task phải tự phản hồi interrupt hoặc dùng API blocking có hỗ trợ interruption.

Mẫu xử lý trong task:

    void performWork() throws InterruptedException {
        while (hasMoreWork()) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("Task cancelled");
            }

            processNextChunk();
        }
    }

Với API blocking đã ném `InterruptedException`, đừng bắt rồi bỏ qua. Nếu tầng hiện tại không thể truyền exception lên, khôi phục interrupt status:

    try {
        blockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }

Khi kiểm thử cancellation:

1. Dùng latch để giữ task tại một điểm chờ đã biết.
2. Gửi cancellation bằng `Future.cancel(true)` hoặc đóng scope.
3. Xác nhận task quan sát interrupt và chạy cleanup trong `finally`.
4. Chờ task thật sự kết thúc bằng Future, latch hoặc executor termination.
5. Xác nhận permit, connection và các resource khác đã được trả lại.

Không kết luận task đã dừng chỉ vì `cancel(true)` trả về true. Cũng không dùng `Thread.stop()` để ép task dừng; cách đó không an toàn với invariant và tài nguyên đang giữ.

## 9. Đóng ExecutorService đúng cách

Từ Java 19, `ExecutorService` triển khai `AutoCloseable`. Có thể dùng try-with-resources:

    try (ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor()) {
        Future<Result> future = executor.submit(this::calculate);
        Result result = future.get(5, TimeUnit.SECONDS);
        return result;
    }

Khi ra khỏi block, `close()`:

- Bắt đầu orderly shutdown.
- Từ chối task mới.
- Chờ các task đã gửi hoàn tất và executor terminated.
- Nếu thread gọi close bị interrupt, executor dừng task đang chạy như thể gọi `shutdownNow()`, tiếp tục chờ các task đang thực thi kết thúc và khôi phục interrupt status trước khi trả về.

Vì close chờ task hoàn tất, try-with-resources không tự tạo deadline shutdown. Nếu task không bao giờ kết thúc hoặc bỏ qua interruption, việc đóng executor có thể chờ vô thời hạn. Với service có shutdown deadline, dùng hai giai đoạn:

    static void shutdownAndAwait(ExecutorService executor)
            throws InterruptedException {

        executor.shutdown();

        if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                System.err.println("Executor vẫn chưa terminated");
            }
        }
    }

Trong ứng dụng production, cần quyết định rõ nơi sở hữu executor. Nếu executor sống suốt vòng đời service, không tạo và đóng lại cho từng request. Thành phần tạo executor chịu trách nhiệm shutdown khi service dừng. Với executor cục bộ cho một nhóm task hữu hạn, try-with-resources là lựa chọn phù hợp.

## 10. Đóng tiến trình hệ điều hành bằng Process trong JDK 26

Một cập nhật API trực tiếp của JDK 26 là `java.lang.Process` triển khai `Closeable` và `AutoCloseable`. Có thể dùng try-with-resources để đóng các stream, chờ tiến trình kết thúc và giải phóng resource liên quan:

    import java.io.BufferedReader;
    import java.io.IOException;
    import java.util.List;
    import java.util.concurrent.TimeUnit;

    static List<String> captureOutput() throws Exception {
        ProcessBuilder builder = new ProcessBuilder(
                "java",
                "-version"
        );

        builder.redirectErrorStream(true);

        try (Process process = builder.start();
             BufferedReader reader = process.inputReader()) {

            if (!process.waitFor(5, TimeUnit.SECONDS)) {
                process.destroy();

                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor();
                }
            }

            // java -version tạo output ngắn; process đã kết thúc nên có thể đọc đến EOF.
            List<String> lines = reader.lines().toList();
            int exitCode = process.exitValue();

            if (exitCode != 0) {
                throw new IOException(
                        "Child process exited with code " + exitCode
                );
            }

            return lines;
        }
    }

Với process chạy lâu hoặc có thể tạo lượng output lớn, phải tiêu thụ stdout/stderr đồng thời trong lúc process chạy; nếu pipe đầy, child có thể block trước khi `waitFor(timeout)` trả về. Mẫu trên dùng `java -version` với output ngắn để minh họa việc đọc kết quả sau khi process kết thúc.

Các điểm cần nhớ:

- Nếu cần output của process, đọc stream trước khi gọi `close()`; nội dung chưa đọc có thể bị loại bỏ khi close.
- Nếu cần exit code, gọi `waitFor()` và lấy exitValue trước khi close.
- `Process.close()` đóng các reader/writer stream và đợi process kết thúc.
- Nếu thread đang chờ trong close bị interrupt, process bị forcibly destroyed; close tiếp tục chờ process kết thúc rồi khôi phục interrupt status.
- Chỉ đóng đối tượng Process trực tiếp không đồng nghĩa tự động dừng toàn bộ process descendants do nó tạo ra. Nếu cần quản lý process tree, phải thiết kế riêng việc theo dõi và dừng child/descendant.

Không bỏ reference đến Process rồi kỳ vọng garbage collection tự dừng process. Process có thể tiếp tục chạy bất đồng bộ sau khi không còn reference Java. Hãy đóng tường minh và kiểm tra trạng thái kết thúc.

## 11. Timeout cần đặt ở nhiều lớp

Một timeout ở Future hoặc scope không tự động giới hạn thời gian của mọi thao tác bên trong. Ví dụ, hủy một task đang gọi HTTP không đảm bảo socket read lập tức dừng nếu HTTP client không có timeout hoặc cancellation phù hợp.

Nên xác định deadline cho từng lớp:

| Lớp | Ví dụ giới hạn |
|---|---|
| Chờ admission | `Semaphore.tryAcquire(timeout)` |
| Chờ queue/executor | Giới hạn queue và chính sách reject |
| Task tổng thể | `Future.get(timeout)` hoặc timeout của scope preview |
| Kết nối mạng | Connect timeout và request/read timeout của HTTP client |
| Database | Query timeout, transaction timeout và pool acquisition timeout |
| Process ngoài | `Process.waitFor(timeout, unit)` và chính sách destroy |
| Shutdown service | Grace period, sau đó cancellation/forced termination |

Khi `Future.get(timeout)` ném `TimeoutException`, chủ động gọi `future.cancel(true)` nếu tác vụ cần dừng. Sau đó kiểm tra task có thật sự kết thúc và resource đã được trả lại. Đặt một deadline tổng thể và truyền thời gian còn lại xuống các lớp con để tránh mỗi tầng chờ timeout đầy đủ nối tiếp nhau.

## 12. Các test cần có cho một thành phần đồng thời

| Nhóm test | Kịch bản | Điều cần xác nhận |
|---|---|---|
| Concurrent correctness | N worker cập nhật cùng dữ liệu hoặc cùng một key | Invariant cuối cùng đúng, không mất hoặc nhân đôi thao tác |
| Burst load | Gửi nhanh hơn tốc độ xử lý | Queue không vượt capacity, rejection/backpressure hoạt động |
| Concurrency limit | Nhiều task tranh semaphore/connection | Số thao tác đồng thời không vượt giới hạn |
| Timeout | Task hoặc dependency phản hồi chậm | Request kết thúc trong deadline và task bị hủy đúng |
| Cancellation | Hủy task khi đang chờ hoặc xử lý | Task phản hồi interrupt và cleanup chạy |
| Failure fan-out | Một subtask lỗi trong nhóm tác vụ | Lỗi được truyền về caller, task còn lại bị cancel nếu policy yêu cầu |
| Shutdown | Dừng service khi còn task đang chạy/chờ | Không nhận task mới, task hoàn tất hoặc bị hủy theo grace period |
| Resource leak | Lặp test nhiều lần | Executor terminated, connection/stream/process không bị rò rỉ |
| Saturation | Vượt worker, queue hoặc permit | Hệ thống từ chối hoặc backpressure đúng policy, không tăng bộ nhớ vô hạn |

Mỗi test nên có thời hạn tối đa để tránh CI treo. Nếu test thất bại, ghi nhận task nào chưa kết thúc, queue/permit state, thread dump và exception gốc. Không chỉ tăng timeout thật lớn để che một deadlock.

## 13. Những nguồn gây test flaky và rò rỉ

- **Dựa vào sleep:** không đảm bảo thứ tự thread; thay bằng latch/barrier và timeout.
- **Không lấy Future result:** exception trong task submit có thể bị giữ trong Future và không xuất hiện ở test thread; gọi `get()`.
- **Không đóng executor:** thread và task có thể tồn tại sau test, ảnh hưởng test kế tiếp.
- **Queue vô hạn:** test tải nhỏ pass nhưng khi stress sẽ tăng bộ nhớ.
- **Virtual thread không giới hạn admission:** nhiều task chờ vẫn tiêu thụ memory/context và giữ request data.
- **Bỏ qua interrupt:** cancellation không kết thúc task, khiến close hoặc scope close chờ mãi.
- **Giữ permit sai:** thiếu release khi exception hoặc return sớm làm hệ thống kẹt; đặt release trong finally.
- **Đếm sai concurrency:** dùng biến thường để đo active task tạo thêm race trong chính test; dùng AtomicInteger.
- **Dùng semaphore trùng connection pool:** hai lớp giới hạn không đồng bộ làm giảm capacity và gây queue kép.
- **Dùng timeout không nhất quán:** timeout của caller ngắn hơn timeout I/O bên trong khiến task tiếp tục chạy nền.
- **Đóng resource sai thứ tự:** đóng connection trước khi result stream/statement đã hoàn tất có thể làm thao tác đọc dở dang.
- **Dùng API preview như API stable:** nâng JDK có thể cần sửa mã, flags và cách xử lý exception.

## 14. Đo tải và quan sát trong runtime

Khi test tải, thu thập tối thiểu:

- Số request/task đã nhận, hoàn tất, thất bại và bị từ chối.
- Số task đang chạy cực đại và số task đang chờ.
- Thời gian chờ semaphore, queue và connection pool.
- Throughput cùng latency p50/p95/p99.
- Heap used, allocation rate, GC pause và native memory.
- Số platform thread, virtual thread và thread bị pin nếu công cụ/runtime cung cấp.
- Số connection/file/process đang mở và số resource được trả lại.
- Số task còn hoạt động sau khi shutdown bắt đầu.

Có thể dùng Java Flight Recorder và thread dump để chẩn đoán khi tải cao hoặc shutdown bị kẹt. Khi dùng StructuredTaskScope preview, thread dump trên JDK hỗ trợ có thể hiển thị quan hệ scope/subtask giúp quan sát cây tác vụ. Log nên ghi request ID, task ID, scope/service và trạng thái cancellation; không log dữ liệu nhạy cảm chỉ để debug concurrency.

Đừng chỉ dùng microbenchmark để quyết định cấu hình production. Kiểm tra cả stress test và load test với tỷ lệ lỗi, burst, thời gian dependency chậm và shutdown trong lúc còn tải.

## 15. Quy trình thực hành trên JDK 26

1. Xác định invariant, concurrency cap, queue capacity, deadline và owner của từng resource.
2. Viết test đồng thời bằng CountDownLatch/CyclicBarrier thay cho sleep.
3. Dùng AtomicInteger hoặc công cụ đo thread-safe để ghi nhận concurrency cực đại.
4. Thử giới hạn tài nguyên bằng Semaphore hoặc bounded ThreadPoolExecutor.
5. Kiểm tra overload/rejection policy và backpressure.
6. Với I/O-bound task, thử virtual thread per task; giới hạn tài nguyên downstream riêng.
7. Dùng Future timeout/cancel và xác nhận task thật sự kết thúc.
8. Đóng ExecutorService bằng try-with-resources hoặc quy trình shutdown có deadline.
9. Đóng Process bằng try-with-resources trên JDK 26; đọc output và exit code trước khi close.
10. Nếu thử StructuredTaskScope, bật preview, kiểm tra cancellation/interrupt và ghi rõ phụ thuộc preview.
11. Chạy test nhiều lần trên đúng JDK/vendor, CPU quota, memory limit và provider/runtime của production.
12. Xác nhận không còn task, connection, stream hoặc process bị rò rỉ sau khi test kết thúc.

## 16. Biên dịch và chạy

Các ví dụ dùng `Semaphore`, `CountDownLatch`, `ExecutorService`, virtual threads và `Process.close()` là API ổn định trên JDK 26:

    javac --release 26 -encoding UTF-8 -d out src/SemaphoreLimitTest.java
    java -cp out SemaphoreLimitTest

Không cần `--enable-preview` cho các ví dụ stable.

Chỉ ví dụ dùng `StructuredTaskScope` mới cần bật preview:

    javac --release 26 --enable-preview -encoding UTF-8 -d out src/StructuredDemo.java
    java --enable-preview -cp out StructuredDemo

Không bật preview cho toàn bộ dự án chỉ vì một test đang thử StructuredTaskScope. Cô lập source set/module thử nghiệm và cấu hình compiler/runtime tương ứng. Khi chuyển sang JDK 27, đọc JEP 533 và API preview mới trước khi biên dịch lại.

## Tài liệu chính thức

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517): cập nhật HTTP Client API trong JDK 26.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): trạng thái preview của pattern matching primitive trong JDK 26.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): trạng thái incubator của Vector API trong JDK 26.
- [Java SE 26 API — ExecutorService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, shutdown, shutdownNow, awaitTermination và close.
- [Java SE 26 API — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/max worker, queue, saturation và rejection policies.
- [Java SE 26 API — Semaphore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html): permit, acquire/release, fairness và giới hạn truy cập tài nguyên.
- [Java SE 26 API — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ test và quan hệ happens-before.
- [Oracle — Virtual Threads, Java SE 26](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): cách tạo virtual thread, giới hạn concurrency bằng Semaphore và hướng dẫn áp dụng.
- [Java SE 26 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): JEP 525 preview lần thứ sáu, owner, fork/join/close, Joiner và timeout.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): trạng thái và mục tiêu của preview trên JDK 26.
- [JDK 27 Release Notes — JEP 533](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): Structured Concurrency tiếp tục là preview lần thứ bảy và API thay đổi.
- [Java SE 26 API — Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): Process implements AutoCloseable, close semantics, streams, waitFor và process termination.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): virtual thread unmount khi chờ class initializer và Process hỗ trợ AutoCloseable.
- [OpenJDK jcstress](https://openjdk.org/projects/code-tools/jcstress/): công cụ stress test các hành vi đồng thời và memory model.

Kiểm thử đồng thời tốt phải kiểm tra cả kết quả lẫn cách hệ thống chịu tải và kết thúc. Dùng latch để điều khiển thời điểm trong test, semaphore hoặc bounded queue để giới hạn tài nguyên, timeout/cancellation để chặn công việc kéo dài, và try-with-resources để đóng executor/process. Trên JDK 26, StructuredTaskScope có thể giúp thử nghiệm cấu trúc tác vụ rõ ràng hơn nhưng vẫn là preview; các API stable là nền tảng phù hợp cho hợp đồng production lâu dài.
