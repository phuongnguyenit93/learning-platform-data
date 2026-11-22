# Bức tranh tổng thể của java.util.concurrent

## 1. Thư viện giải quyết những vấn đề nào?

Một chương trình đồng thời có nhiều việc có thể tiến triển trong cùng một khoảng thời gian: xử lý nhiều yêu cầu, chờ nhiều nguồn dữ liệu, tính các phần độc lập hoặc chuyển dữ liệu giữa các bộ phận.

Từ đó xuất hiện nhiều câu hỏi khác nhau:

1. Ai nhận và thực thi tác vụ?
2. Bên gọi nhận kết quả hoặc lỗi bằng cách nào?
3. Các tác vụ phối hợp, chờ hoặc giới hạn số việc đang làm ra sao?
4. Dữ liệu dùng chung được cập nhật thế nào cho đúng?
5. Ai chịu trách nhiệm kết thúc, hủy và giải phóng tài nguyên?

`java.util.concurrent` cùng các gói liên quan `java.util.concurrent.locks` và `java.util.concurrent.atomic` cung cấp những công cụ cho các nhóm vấn đề đó. Nó không phải chỉ là tập cách tạo thêm luồng.

Trong ngữ cảnh học Java 5 bằng Java hiện đại, cần hiểu các nền tảng vẫn được dùng và cách chúng kết nối. Bài cũng chỉ ra những mở rộng hiện đại liên quan để tránh nhầm toàn bộ thư viện hiện nay đều xuất hiện cùng một phiên bản.

Đồng thời không tự có nghĩa chạy song song trên nhiều lõi, và cũng không bảo đảm nhanh hơn. Với một công việc nhỏ hoặc phụ thuộc tuần tự, chi phí phối hợp có thể lớn hơn lợi ích.

## 2. Mô hình đầu tiên: tác vụ khác luồng thực thi

**Tác vụ (task)** là đơn vị công việc, chẳng hạn xử lý một lô bản ghi. **Luồng (thread)** là ngữ cảnh thực thi mã. Một cơ chế thực thi có thể dùng luồng hiện có, tạo luồng mới hoặc thậm chí chạy ngay trong luồng gọi, tùy hợp đồng.

Hai kiểu mô tả tác vụ thường gặp:

| Kiểu | Hình dạng hành vi | Vai trò |
| --- | --- | --- |
| `Runnable` | `void run()` | Việc không có giá trị trả về qua phương thức |
| `Callable<V>` | `V call() throws Exception` | Việc có kết quả kiểu V và có thể báo ngoại lệ được kiểm tra |

Chỉ tạo một đối tượng tác vụ không tự làm nó chạy bất đồng bộ. Tác vụ cần được gọi trực tiếp hoặc giao cho cơ chế thực thi.

`Executor` cung cấp điểm nhận `Runnable` qua `execute`. Nó tách yêu cầu “làm việc này” khỏi quyết định dùng luồng nào. Vì vậy, không suy ra rằng mỗi lần `execute` đều tạo một luồng mới.

`ExecutorService` mở rộng mô hình với quản lý vòng đời và các cách giao việc có kết quả. Tổng quan chính thức mô tả rõ các vai trò này tại [java.util.concurrent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html).

## 3. Bản đồ các nhóm công cụ

| Nhóm vấn đề | Công cụ điển hình | Câu hỏi nó trả lời |
| --- | --- | --- |
| Giao và quản lý tác vụ | `Executor`, `ExecutorService`, `ThreadPoolExecutor` | Ai chạy việc và quản lý tài nguyên? |
| Nhận một kết quả | `Future<V>`, `FutureTask<V>` | Việc đã xong chưa, kết quả/lỗi là gì? |
| Xử lý một nhóm việc | `invokeAll`, `invokeAny`, `ExecutorCompletionService` | Đợi tất cả, đợi một kết quả, hay lấy theo thứ tự hoàn thành? |
| Trì hoãn/lặp theo thời gian | `ScheduledExecutorService` | Khi nào giao việc chạy trong tiến trình? |
| Trao đổi dữ liệu giữa tác vụ | `BlockingQueue` và các hàng đợi đồng thời | Chuyển phần tử, chờ có dữ liệu/chỗ trống thế nào? |
| Lưu dữ liệu dùng chung | `ConcurrentHashMap`, collection đồng thời | Đọc/cập nhật cấu trúc chung ra sao? |
| Phối hợp các mốc | `CountDownLatch`, `CyclicBarrier` | Khi nào đủ điều kiện đi tiếp? |
| Giới hạn số bên cùng dùng tài nguyên | `Semaphore` | Có bao nhiêu giấy phép đang được sử dụng? |
| Bảo vệ quy tắc nhiều bước | `Lock`, `ReentrantLock`, `Condition` | Vùng mã nào cần loại trừ hoặc chờ điều kiện? |
| Cập nhật một biến nguyên tử | `AtomicInteger`, `AtomicLong`, `AtomicReference` | Một phép đọc-sửa-ghi có được thực hiện nguyên tử không? |
| Ghép các giai đoạn kết quả | `CompletableFuture`, `CompletionStage` | Khi kết quả có rồi thì làm bước nào tiếp? |
| Phân chia công việc tính toán | `ForkJoinPool` | Chia nhỏ và thực thi các phần phù hợp mô hình fork/join thế nào? |

Đây là bản đồ chọn hướng, không phải danh sách phải dùng hết trong một chương trình. Mỗi công cụ có phạm vi đảm bảo riêng.

`CompletableFuture` và `ForkJoinPool` là những bổ sung sau Java 5; virtual threads là khả năng của Java hiện đại. Chúng được đặt cạnh nền tảng để thấy mối liên hệ, không được gán thành tính năng cùng xuất hiện ở Java 5.

## 4. ExecutorService: giao việc và quản lý vòng đời

Một luồng sử dụng thường có dạng:

```text
Bên sở hữu tạo executor
        ↓
Giao các tác vụ
        ↓
Theo dõi kết quả/lỗi/hủy
        ↓
Ngừng nhận việc và chờ kết thúc theo chính sách
```

Các thao tác quan trọng:

- `execute(Runnable)`: giao việc, không trả `Future`.
- `submit(Callable)` hoặc `submit(Runnable)`: giao việc và nhận `Future`.
- `shutdown()`: ngừng nhận việc mới, cho các việc đã nhận tiếp tục theo hợp đồng.
- `shutdownNow()`: cố gắng ngăn các việc đang chờ bắt đầu và yêu cầu dừng việc đang chạy.
- `awaitTermination(...)`: chờ executor kết thúc trong giới hạn thời gian.
- `isTerminated()`: kiểm tra đã thực sự kết thúc.

`shutdown` không phải lời gọi “đợi đến khi mọi việc đã xong”. `shutdownNow` cũng không bảo đảm một tác vụ không hợp tác sẽ bị ép dừng ngay. Trách nhiệm vòng đời thuộc bên tạo/sở hữu executor; một hàm chỉ được truyền executor dùng chung không nên tùy ý đóng nó.

Trong mã Java 21+ có thể dùng khả năng `AutoCloseable` của `ExecutorService` cho phạm vi phù hợp. Ví dụ của bài dùng `shutdown`/`awaitTermination` để chạy được với mức Java 17 và thể hiện rõ các bước; đó vẫn là API có hợp đồng hiện hành. Xem [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).

### Số luồng không phải giới hạn duy nhất

Một nhóm hai luồng không đồng nghĩa hệ thống chỉ giữ hai tác vụ. Nó còn có thể có hàng đợi nhiều việc.

Ví dụ `Executors.newFixedThreadPool(n)` có hàng đợi không được cấu hình giới hạn cố định theo số lượng tác vụ. Với đầu vào tăng liên tục, giới hạn số worker không tự giới hạn bộ nhớ giữ các việc đang chờ.

Trong dịch vụ thực, cần quyết định số tác vụ đang chờ, cơ chế từ chối khi quá tải và giới hạn tài nguyên bên ngoài. `ThreadPoolExecutor` cho phép cấu hình các phần đó; không chọn kích thước pool chỉ theo một con số được sao chép từ ví dụ. Xem các lựa chọn tại [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 5. Future: có kết quả không đồng nghĩa kết quả thành công

Một `Future<V>` đại diện cho kết quả tương lai của một công việc. Nó không chứa một luồng riêng và không tự thực thi mọi việc.

Bên gọi cần xử lý các khả năng:

| Tình huống | Ý nghĩa |
| --- | --- |
| `get()` trả V | Tác vụ đã hoàn thành thành công |
| `ExecutionException` | Tác vụ thất bại; xem nguyên nhân |
| `InterruptedException` | Luồng đang chờ bị ngắt |
| `CancellationException` | Kết quả đã bị hủy |
| `get(timeout, unit)` báo `TimeoutException` | Hết thời gian chờ của lời gọi |

Hết thời gian chờ không tự có nghĩa tác vụ đã bị hủy. Nếu cần hủy, phải có quyết định và xử lý riêng.

`cancel(true)` có thể yêu cầu ngắt tác vụ đang chạy theo cách triển khai; không xem đó là bảo đảm đã giải phóng kết nối, hoàn tác thay đổi hoặc dừng mã ngay. Tác vụ cần hợp tác với cơ chế ngắt và quản lý tài nguyên của nó.

Không bỏ quên `Future` sau `submit` nếu tác vụ có thể thất bại mà lỗi cần được quan sát. Một ngoại lệ trong tác vụ thường được giữ trong kết quả, không tự xuất hiện như ngoại lệ ném trực tiếp từ lời gọi `submit` của bên giao việc.

### Nhóm tác vụ và thứ tự lấy kết quả

- Duyệt danh sách `Future` theo thứ tự giao giúp kết quả có thứ tự cố định, nhưng có thể phải chờ một việc chậm trước khi xử lý kết quả đã xong của việc sau.
- `ExecutorCompletionService` giúp lấy các kết quả theo thứ tự hoàn thành.
- `invokeAll` và `invokeAny` cung cấp các chính sách nhóm phổ biến theo hợp đồng riêng.

Chọn theo nhu cầu, không cho rằng mọi cách lấy kết quả đều có cùng độ trễ và thứ tự.

## 6. Dữ liệu dùng chung: an toàn của cấu trúc khác nguyên tử của nghiệp vụ

### 6.1. ConcurrentHashMap

`ConcurrentHashMap` cho phép truy cập/cập nhật đồng thời theo hợp đồng. Nhưng ghép nhiều lời gọi riêng lẻ chưa chắc tạo một thao tác nguyên tử.

Ví dụ “đọc số đếm rồi ghi số đếm + 1” gồm nhiều bước. Hai tác vụ có thể đọc cùng số cũ rồi ghi đè kết quả nhau. Với đếm theo khóa, dùng thao tác như `merge` phù hợp hơn.

Trong ví dụ của bài:

```java
// counts là ConcurrentHashMap được tham chiếu qua Map.
counts.merge(word, 1, Integer::sum);
```

Phép cập nhật được thực hiện nguyên tử theo khóa bởi cách triển khai cụ thể. Điều đó không làm mọi quy tắc gồm nhiều khóa tự trở thành một giao dịch.

Cũng không cho rằng `size()` hoặc một lần duyệt khi đang có cập nhật là ảnh chụp bất biến của toàn bản đồ. Muốn in kết quả cuối ổn định, ví dụ chờ mọi tác vụ liên quan xong trước. Xem phạm vi đảm bảo tại [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### 6.2. Collection đồng thời không bảo vệ mọi phần tử bên trong

Một collection an toàn luồng không tự làm một đối tượng có thể thay đổi được chứa trong nó an toàn luồng. Nếu map chứa các danh sách thông thường và nhiều tác vụ sửa cùng một danh sách, cần xử lý phần dữ liệu đó riêng.

Trước khi thêm khóa hay atomic, nên hỏi có thể tránh chia sẻ trạng thái không. Dữ liệu đầu vào bất biến, kết quả riêng của mỗi tác vụ và tổng hợp sau khi hoàn tất thường dễ hiểu hơn.

### 6.3. BlockingQueue

Hàng đợi chặn hỗ trợ mô hình bên sản xuất đưa dữ liệu, bên tiêu thụ lấy dữ liệu. Một hàng đợi có giới hạn có thể giúp bên sản xuất chờ hoặc thất bại có chủ đích khi đầy, tùy phương thức dùng.

Tuy nhiên, vẫn cần quy tắc kết thúc: không có thêm dữ liệu nữa, tác vụ bị hủy hoặc hệ thống đang dừng thì bên đang chờ được báo ra sao? Một lời gọi `take()` không tự biết toàn bộ công việc của ứng dụng đã kết thúc.

## 7. Phối hợp, khóa và biến nguyên tử

### Công cụ phối hợp

| Công cụ | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `CountDownLatch` | Chờ số sự kiện đếm xuống về 0 | Một lượt; không đặt lại để dùng như barrier lặp |
| `CyclicBarrier` | Các bên gặp nhau tại một điểm rồi đi tiếp | Có thể dùng qua nhiều vòng; cần xử lý barrier bị hỏng |
| `Semaphore` | Giới hạn số giấy phép đồng thời | Không tự là giới hạn số yêu cầu mỗi giây |
| `BlockingQueue` | Chuyển dữ liệu và chờ theo trạng thái hàng đợi | Cần chính sách đóng luồng dữ liệu |

Không dùng `Thread.sleep` để chứng minh tác vụ khác đã hoàn thành. Thời gian trôi qua không phải bằng chứng đồng bộ.

### Khóa

`synchronized` vẫn là công cụ hợp lệ của Java hiện đại. `ReentrantLock` cung cấp thêm các lựa chọn như thử lấy khóa hoặc chờ theo cách có thể ngắt. Không có quy tắc “dùng concurrent thì phải bỏ synchronized”.

Nếu lấy khóa thủ công, mở khóa trong `finally` theo đúng hợp đồng. Nhiều khóa hoặc thứ tự lấy khóa không nhất quán có thể gây bế tắc. Đừng thêm khóa trước khi xác định trạng thái và quy tắc cần bảo vệ. Xem [java.util.concurrent.locks](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/package-summary.html).

### Atomic

`AtomicInteger.incrementAndGet()` là thao tác tăng nguyên tử trên một biến. Một biến `volatile int` với `count++` không có cùng đảm bảo, vì phép tăng gồm đọc, cộng và ghi.

Hai biến atomic vẫn không tự bảo đảm một quan hệ nhiều biến. Nếu điều kiện là tổng hoặc thứ tự giữa nhiều trường phải luôn đúng, cần một thiết kế bảo vệ toàn bộ quy tắc.

`LongAdder` có thể phù hợp cho bộ đếm thống kê chịu nhiều cập nhật, nhưng không coi một lần `sum()` trong lúc cập nhật là một giao dịch ảnh chụp toàn cục. Xem nhóm công cụ tại [java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).

## 8. Đảm bảo nhìn thấy dữ liệu là một phần của hợp đồng

Vấn đề đồng thời không chỉ là hai luồng viết cùng lúc. Một bên còn cần thấy những thay đổi mà bên kia đã thực hiện theo thứ tự đúng.

Các API có những quan hệ đảm bảo thứ tự/khả năng nhìn thấy dữ liệu, thường được diễn đạt bằng quan hệ xảy-ra-trước (happens-before). Ví dụ, tác động trong một tác vụ được quan sát theo đảm bảo của `Future.get` khi bên gọi lấy kết quả; hàng đợi và các công cụ phối hợp cũng có hợp đồng truyền dữ liệu tương ứng.

Điều đó không cho phép tiếp tục sửa dữ liệu tùy ý sau khi giao cho tác vụ mà không phối hợp. Truyền một tham chiếu vào executor không tự đóng băng đối tượng.

Ở ví dụ, các lô đầu vào là danh sách không sửa được chứa chuỗi, map được cập nhật bằng thao tác phù hợp, và tổng `processed` chỉ được thay đổi bởi luồng chính sau khi nhận kết quả. Mỗi phần có trách nhiệm rõ thay vì dựa vào “chạy vài lần không lỗi”.

## 9. Mở rộng hiện đại nằm ở đâu trong bản đồ?

### CompletableFuture

`CompletableFuture`/`CompletionStage` hữu ích khi kết quả của một bước dẫn tới bước sau: chuyển đổi, kết hợp, xử lý lỗi. Nó là cách tổ chức các giai đoạn, không phải bảo đảm mỗi bước tự có luồng riêng.

Phương thức không có hậu tố `Async` có thể chạy trong luồng hoàn thành kết quả. Phương thức async không truyền executor có chính sách executor mặc định theo API. Khi có I/O chặn hoặc yêu cầu cách ly tài nguyên, cần chọn rõ cơ chế thực thi thay vì vô tình dồn vào pool dùng chung.

Quản lý timeout, lỗi và hủy vẫn cần đọc hợp đồng; `CompletableFuture.cancel` không có cùng ý nghĩa ngắt tác vụ như mọi loại `Future`. Xem [CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

### ForkJoinPool

Mô hình fork/join phù hợp với các công việc có thể chia nhỏ theo thiết kế của nó, thường gặp trong tính toán. Nó không phải lựa chọn tự động cho mọi tác vụ chặn I/O hoặc mọi bài toán cần song song.

### Virtual threads

Trong Java 21+, virtual threads cung cấp cách thực thi nhiều tác vụ chờ I/O với mô hình một luồng cho một tác vụ. `Executors.newVirtualThreadPerTaskExecutor()` tạo virtual thread mới cho mỗi tác vụ; không cần lập pool virtual threads để tái sử dụng chúng theo cách pool platform thread.

Virtual threads không làm CPU thực hiện một phép tính nhanh hơn, không xóa race condition và không làm cơ sở dữ liệu có vô hạn kết nối. Giới hạn tài nguyên bên ngoài vẫn cần semaphore, connection pool hoặc cơ chế phù hợp.

Vì thế, nền tảng tác vụ, kết quả, hủy, chia sẻ dữ liệu và vòng đời vẫn có giá trị. Xem vị trí và mục tiêu của khả năng này tại [Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

## 10. Chương trình Java 17+ nối các khái niệm thành một luồng xử lý

Lưu mã sau thành `ConcurrentOverview.java`. Chương trình không cần thư viện ngoài.

Ba tác vụ đếm từ trong ba lô đầu vào. Mỗi tác vụ trả số phần tử đã xử lý; các số đếm theo từ được cập nhật vào `ConcurrentHashMap`. Sau đó chương trình cố ý giao một tác vụ lỗi để chứng minh lỗi được quan sát qua `Future`.

Ví dụ chỉ có bốn tác vụ hữu hạn nên dùng fixed thread pool nhỏ để dễ thấy mô hình. Nó không phải cấu hình hàng đợi cho một dịch vụ nhận đầu vào không giới hạn. Lambda, method reference và `List.of` được dùng như cú pháp/API hiện đại; không được trình bày như các tính năng xuất hiện ở Java 5.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentOverview {
    private static int checks;

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        checks++;
    }

    private static void stop(ExecutorService executor) {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        List<List<String>> batches = List.of(
                List.of("java", "task", "java"),
                List.of("future", "task"),
                List.of("java", "map", "future"));
        Map<String, Integer> counts = new ConcurrentHashMap<>();
        ExecutorService executor = Executors.newFixedThreadPool(2);
        int processed = 0;
        String failureType = "";

        try {
            List<Future<Integer>> results = new ArrayList<>();
            for (List<String> batch : batches) {
                results.add(executor.submit(() -> {
                    for (String word : batch) {
                        counts.merge(word, 1, Integer::sum);
                    }
                    return batch.size();
                }));
            }

            // Only the main thread changes this accumulator.
            for (Future<Integer> result : results) {
                processed += result.get();
            }

            check(processed == 8, "All tokens must be processed");
            check(counts.get("java") == 3, "java count");
            check(counts.get("task") == 2, "task count");
            check(counts.get("future") == 2, "future count");
            check(counts.get("map") == 1, "map count");

            Future<Integer> failed = executor.submit(() -> {
                throw new IllegalArgumentException("invalid batch");
            });
            boolean failureObserved = false;
            try {
                failed.get();
            } catch (ExecutionException ex) {
                check(ex.getCause() instanceof IllegalArgumentException,
                        "Original task failure must be preserved");
                failureType = ex.getCause().getClass().getSimpleName();
                failureObserved = true;
            }
            check(failureObserved, "Task failure must be observed");
        } finally {
            stop(executor);
        }

        check(executor.isTerminated(), "Owned executor must terminate");
        System.out.println("processed=" + processed);
        System.out.println("counts=" + new TreeMap<>(counts));
        System.out.println("observedFailure=" + failureType);
        System.out.println("terminated=" + executor.isTerminated());
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ConcurrentOverview.java
java ConcurrentOverview
```

Stdout:

```text
processed=8
counts={future=2, java=3, map=1, task=2}
observedFailure=IllegalArgumentException
terminated=true
PASS checks=8
```

Không in thứ tự bắt đầu/kết thúc tác vụ vì thứ tự đó không được bảo đảm. `TreeMap` chỉ được tạo sau khi các tác vụ đếm đã hoàn thành để trình bày khóa theo thứ tự ổn định, không dùng nó như collection cập nhật đồng thời.

Hàm `check` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Tám kiểm tra xác nhận tổng và các số đếm, nguyên nhân tác vụ thất bại được giữ, lỗi đã được quan sát và executor kết thúc trong đường chạy bình thường.

Hàm `stop` thể hiện dừng có chờ và yêu cầu dừng mạnh hơn khi quá thời gian; nếu luồng chờ bị ngắt, nó khôi phục trạng thái ngắt sau khi yêu cầu executor dừng. Nó không tuyên bố có thể ép mọi mã tác vụ dừng. Các tác vụ trong ví dụ là hữu hạn và không có I/O chặn.

## 11. Tiêu chí chọn công cụ trước khi viết mã

| Nếu yêu cầu là… | Điểm bắt đầu hợp lý |
| --- | --- |
| Một việc đơn giản, không cần đồng thời | Mã tuần tự |
| Giao tác vụ độc lập và nhận kết quả | `ExecutorService` + `Callable`/`Future` |
| Xử lý ngay kết quả nào hoàn thành trước | `ExecutorCompletionService` |
| Chuỗi bước phụ thuộc kết quả | `CompletionStage`/`CompletableFuture` |
| Chuyển phần tử giữa bên sản xuất/tiêu thụ | Hàng đợi có hợp đồng phù hợp |
| Đếm theo từng khóa dùng chung | Collection đồng thời + phép cập nhật nguyên tử tương ứng |
| Bảo vệ điều kiện nhiều trường | Thiết kế trạng thái/khóa cho toàn bộ quy tắc |
| Hạn chế số tác vụ đang dùng dịch vụ ngoài | Giới hạn tài nguyên theo chính sách, chẳng hạn semaphore |
| Nhiều tác vụ chờ I/O trên Java 21+ | Đánh giá virtual threads và giới hạn tài nguyên ngoài |
| Tác vụ lặp theo khoảng thời gian | `ScheduledExecutorService`, với chính sách lỗi/hủy rõ |

Lập lịch theo khoảng trong tiến trình không đồng nghĩa lịch nghiệp vụ “mỗi ngày 09:00 theo múi giờ”. Lịch theo ngày địa phương cần tính ranh giới, vùng và xử lý thay đổi offset riêng.

## 12. Lỗi thường gặp và thực hành

Các lỗi cần tránh:

- Tạo một luồng cho mỗi việc mà không đánh giá tải hoặc vòng đời.
- Nghĩ pool ít luồng tự giới hạn hàng đợi.
- Gọi `get` ngay sau từng `submit` trong vòng lặp rồi vô tình làm mọi việc tuần tự.
- Bỏ Future nên không quan sát lỗi.
- Coi timeout là đã hủy, hoặc coi hủy là đã dừng hoàn toàn.
- Nuốt `InterruptedException` khiến cơ chế dừng không còn được tôn trọng.
- Ghép `get` rồi `put` và nghĩ toàn bộ phép tăng là nguyên tử.
- Dùng collection đồng thời rồi sửa đối tượng bên trong mà không có quy tắc.
- Dùng sleep như bằng chứng đồng bộ.
- Nghĩ virtual threads thay thế mọi cơ chế bảo vệ trạng thái.

Bài tập:

1. **Thêm một lô `["java", "java"]`.** Kết quả mong đợi: processed = 10, java = 5. Không thay thuật toán chỉ để khớp con số mới.

2. **Mỗi tác vụ trả một map riêng rồi tổng hợp ở luồng chính.** So sánh trách nhiệm và lượng trạng thái dùng chung với cách dùng `ConcurrentHashMap`.

3. **Tách thứ tự giao việc khỏi thứ tự hoàn thành.** Thiết kế cách quan sát với `ExecutorCompletionService`; đừng dùng thứ tự hoàn thành ngẫu nhiên làm stdout cố định của kiểm thử.

4. **Đổi tác vụ sang gọi một dịch vụ ngoài.** Trước khi tăng số worker hoặc dùng virtual threads, xác định giới hạn kết nối, timeout, hủy và số yêu cầu đang chờ.

5. **Có quy tắc chuyển tiền giữa hai tài khoản.** Giải thích vì sao hai số dư atomic riêng không tự bảo vệ toàn bộ giao dịch. Chỉ rõ phạm vi quy tắc cần được bảo đảm.

Bức tranh tổng thể của thư viện là sự kết hợp của giao việc, kết quả, phối hợp, bảo vệ dữ liệu và vòng đời tài nguyên. Chọn đúng nhóm công cụ theo vấn đề sẽ giúp mã đồng thời dễ kiểm chứng hơn việc bắt đầu bằng câu hỏi “tạo bao nhiêu luồng?”.
