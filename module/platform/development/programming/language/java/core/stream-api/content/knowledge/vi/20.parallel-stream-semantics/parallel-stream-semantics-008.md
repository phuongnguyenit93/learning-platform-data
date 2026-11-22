# ForkJoinPool chung, tác vụ chặn và giới hạn kiểm soát bộ thực thi

> **Chương:** Ngữ nghĩa xử lý song song  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API thông qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Khi thêm `.parallel()` hoặc gọi `parallelStream()`, chương trình có thể sử dụng nhiều luồng để xử lý một nguồn dữ liệu. Nhưng **“chạy song song” không đồng nghĩa “có một bộ luồng riêng cho công việc này”**, cũng không bảo đảm nhanh hơn. Đặc biệt, nếu từng phần tử gọi HTTP, truy vấn cơ sở dữ liệu, chờ khóa hoặc thực hiện I/O chặn, việc sử dụng pool chia sẻ có thể làm chậm các tác vụ khác trong ứng dụng.

Bài này giúp bạn hiểu vai trò của `ForkJoinPool.commonPool()`, cách tác vụ chặn tác động đến tiến độ, giới hạn kiểm soát executor qua Stream API, và cách chọn một mô hình thực thi khác khi cần giới hạn đồng thời, timeout hoặc cách ly tài nguyên.

Sau khi học, bạn có thể:

1. Phân biệt **hợp đồng Java Stream API** với **chi tiết triển khai thường gặp** của parallel stream.
2. Nhận diện vì sao `ForkJoinPool` phù hợp với tính toán CPU-bound có thể chia nhỏ, nhưng không phải lựa chọn mặc định tốt cho I/O chặn.
3. Hiểu `ManagedBlocker` giải quyết phần nào vấn đề chờ, song không thay thế kiểm soát tải.
4. Sử dụng `CompletableFuture` cùng `ExecutorService` được truyền **tường minh** khi phải điều khiển số tác vụ I/O đang chạy; phân biệt với `ForkJoinTask` dùng pool chuyên biệt cho tác vụ CPU.

## 1. `parallelStream()` làm gì và không làm gì?

Trong Java, hai cách sau đều yêu cầu một pipeline ở **chế độ song song**:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

Stream<Integer> a = numbers.parallelStream();
Stream<Integer> b = numbers.stream().parallel();

System.out.println(a.isParallel()); // true
System.out.println(b.isParallel()); // true
```

`parallel()` là **intermediate operation** cấu hình chế độ thực thi của pipeline, không lập tức chạy công việc. Việc duyệt xảy ra khi gọi một **terminal operation** như `sum`, `reduce`, `collect` hoặc `forEach`. Một số phần của pipeline có thể được chia nhỏ cho nhiều tác vụ; cách chia thực tế phụ thuộc nguồn, `Spliterator`, phép toán và môi trường.

Song song không có nghĩa:

- Mỗi phần tử được giao cho một thread riêng.
- Số thread luôn bằng số lõi CPU, hoặc có thể chỉ định trực tiếp bằng `.parallel(4)` — **không có overload như vậy**.
- Mọi phần tử được xử lý theo thứ tự xuất hiện trong nguồn.
- Một nguồn ít phần tử sẽ được chia đều.
- Các thao tác chặn được tự động giới hạn hay có timeout.
- Pipeline có bộ thực thi (executor) biệt lập với các tác vụ khác.

**Quan trọng:** Java Stream API chỉ quy định ngữ nghĩa tính toán và những ràng buộc như tính không can thiệp (*non-interference*) và tính không phụ thuộc trạng thái (*statelessness*) của nhiều lambda. Nó **không có phương thức chuẩn để truyền một `Executor` hoặc `ForkJoinPool` cho từng pipeline song song**.

## 2. `ForkJoinPool.commonPool()` và cơ chế work-stealing

`ForkJoinPool` là một `ExecutorService` được thiết kế cho những nhiệm vụ có thể **chia thành các công việc nhỏ**, sau đó **gộp kết quả**. Những worker có thể lấy công việc từ hàng đợi của nhau (*work-stealing*) nhằm cân bằng tải.

```text
               Bài toán cần tính toán
                       │
                   chia nguồn
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Task A     Task B     Task C
             │         │         │
             └─────── gộp ───────┘
                       │
                   kết quả
```

Trong **triển khai OpenJDK thông dụng**, một parallel stream được gọi từ ngữ cảnh bình thường thường tận dụng `ForkJoinPool.commonPool()` — pool dùng chung trong JVM. Luồng gọi terminal operation cũng có thể tham gia xử lý. Các điều này là **mô tả hành vi triển khai**, không phải hợp đồng cho phép chương trình gắn một executor riêng vào Stream API.

Có thể quan sát cấu hình và tên các luồng trong một lần chạy:

```java
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

System.out.println("Common pool parallelism: "
        + ForkJoinPool.getCommonPoolParallelism());

List<String> seenThreads = IntStream.range(0, 20)
        .parallel()
        .mapToObj(i -> Thread.currentThread().getName())
        .distinct()
        .sorted()
        .toList();

System.out.println(seenThreads);
```

Đầu ra về tên thread **không cố định**: có thể thấy `main`, các thread có tên tương tự `ForkJoinPool.commonPool-worker-...`, hoặc ít thread hơn mức song song cấu hình. Một lần chạy không cho biết giới hạn vĩnh viễn về số thread hoặc hiệu suất. `getCommonPoolParallelism()` phản ánh mức song song mục tiêu được cấu hình cho common pool, **không phải** một cam kết về số thread thực sự đang chạy trong riêng pipeline.

### Vì sao gọi là “chung”?

Một common pool có thể được sử dụng bởi **nhiều thành phần trong cùng JVM**, ví dụ các parallel stream khác, các tác vụ Fork/Join do ứng dụng hoặc thư viện gửi tới common pool, và những phép `CompletableFuture.supplyAsync(...)` không chỉ định executor trong các cấu hình thường gặp.

```text
    Module A: parallelStream() ───┐
                                  ├──► commonPool() ──► workers dùng chung
    Module B: parallelStream() ───┤
                                  │
    Async work mặc định ──────────┘
```

`CompletableFuture` có quy tắc triển khai riêng: các async method không truyền executor thường dùng common pool nếu nó hỗ trợ mức song song lớn hơn một; ở môi trường có mức song song thấp, nó có thể dùng cách thực thi thay thế. Không nên suy rằng **mọi** async operation hoặc **mọi** parallel stream nhất thiết dùng đúng những thread này trong tất cả JDK và cấu hình.

Hậu quả thực tế là tranh chấp tài nguyên: một module đưa nhiều công việc chậm vào pool chia sẻ có thể làm giảm năng lực của các module khác. Đây là một dạng **ảnh hưởng chéo (noisy neighbor)** trong cùng quá trình.

## 3. `ForkJoinPool` phù hợp với loại công việc nào?

Nó thường phù hợp với công việc **CPU-bound**, ít chặn, có chi phí đủ lớn để bù chi phí chia và hợp nhất:

```java
import java.util.stream.LongStream;

long sum = LongStream.rangeClosed(1, 1_000_000)
        .parallel()
        .sum();

System.out.println(sum); // 500000500000
```

Ví dụ này cho thấy tính đúng đắn của phép cộng trên nguồn hữu hạn trong miền `long`; nó **không** chứng minh bản song song nhanh hơn bản tuần tự. Với phép cộng đơn giản, overhead song song thậm chí có thể chiếm phần lớn thời gian.

Một nguồn dễ chia như dải số, mảng hoặc cấu trúc có `Spliterator` tốt có nhiều cơ hội phân phối công việc hiệu quả hơn một nguồn I/O tuần tự khó chia. `SIZED`, `SUBSIZED` và `trySplit()` của `Spliterator` hỗ trợ triển khai lên kế hoạch xử lý, nhưng không bảo đảm tăng tốc.

| Tác vụ | Đặc điểm | Khuyến nghị ban đầu |
| --- | --- | --- |
| Tính toán số học trên mảng lớn | CPU-bound, không chặn, dễ chia | Có thể thử parallel stream và đo hiệu năng. |
| Biến đổi các phần tử độc lập với chi phí CPU đáng kể | Stateless, ít I/O | Có thể cân nhắc song song. |
| Gọi HTTP/JDBC cho từng phần tử | Chờ mạng hoặc CSDL, độ trễ thay đổi | Dùng executor có giới hạn rõ và cơ chế timeout/backpressure. |
| Ghi log/ghi file/khóa đồng bộ cho từng phần tử | Side effect, có thể chặn hoặc tranh chấp | Xem lại thiết kế; không mặc định parallel. |
| Nguồn rất nhỏ | Chi phí chia/gộp có thể lớn hơn tính toán | Thường ưu tiên `stream()` tuần tự. |

## 4. Vì sao blocking I/O là vấn đề với common pool?

Xem một pipeline như:

```java
// Ví dụ minh họa, KHÔNG nên mặc định triển khai theo cách này:
List<String> results = ids.parallelStream()
        .map(id -> blockingHttpLookup(id))
        .toList();
```

`ids` là tập định danh đầu vào, còn `blockingHttpLookup` đại diện cho hàm gọi mạng **đồng bộ** do ứng dụng cung cấp. Với mỗi `id`, worker có thể phải chờ kết nối, máy chủ, cơ sở dữ liệu hoặc timeout. Trong khi chờ, worker không thể thực hiện phần CPU hữu ích của tác vụ đang giữ.

Điều này gây ra những rủi ro:

1. **Giữ worker quá lâu:** nhiều phần tử chặn đồng thời có thể chiếm phần lớn năng lực của pool.
2. **Ảnh hưởng tác vụ không liên quan:** common pool là tài nguyên chia sẻ; công việc của module khác có thể phải chờ.
3. **Không chủ động giới hạn lưu lượng dịch vụ đích:** kích thước pool không phải chính sách rate limit hoặc số kết nối tối đa được thỏa thuận với API/CSDL.
4. **Độ trễ khó dự đoán:** các bước đang chờ không tuân theo một deadline do parallel stream tự đặt.
5. **Nguy cơ vòng chờ:** nếu tác vụ chặn chờ một tác vụ khác cần chính pool đang bị chiếm, thiết kế có thể bị kẹt hoặc tăng mạnh thời gian chờ.

`ForkJoinPool` có cơ chế hỗ trợ một số kiểu chờ phối hợp của Fork/Join và có `ManagedBlocker` để thông báo về những thao tác chặn. Tuy nhiên, **không thể suy ra nó tự động bù đủ worker cho mọi lời gọi JDBC, HTTP hoặc `Thread.sleep` tùy ý**. Chính sách thực thi, giới hạn tài nguyên và cách sử dụng các API chặn quyết định hành vi thực tế.

### `parallelStream()` không thay thế timeout

```java
// limit(10) chỉ giới hạn số phần tử, KHÔNG phải giới hạn thời gian.
List<String> firstTen = ids.parallelStream()
        .limit(10)
        .map(id -> blockingHttpLookup(id))
        .toList();
```

`limit(10)` không bảo đảm hoàn thành trước một số mili giây. Nếu dịch vụ đích treo, pipeline vẫn có thể chờ lâu. Timeout phải được đặt ở **lời gọi I/O**, ở tác vụ hoặc tại cấp điều phối với hành vi hủy được thiết kế rõ ràng.

## 5. `ForkJoinPool.ManagedBlocker`: công cụ chuyên biệt, không phải thuốc chữa chung

`ForkJoinPool.managedBlock(ManagedBlocker)` cho phép một tác vụ thông báo với `ForkJoinPool` rằng nó **có thể chặn**, giúp pool có cơ hội điều chỉnh nguồn worker theo chính sách và giới hạn triển khai.

Hai phương thức của `ManagedBlocker`:

- `isReleasable()`: kiểm tra liệu đã có thể tiếp tục mà không chặn hay chưa.
- `block()`: thực hiện thao tác có thể chặn và trả trạng thái đã hoàn tất.

Ví dụ **minh họa cú pháp**, không phải giải pháp được khuyến nghị cho HTTP:

```java
import java.util.concurrent.ForkJoinPool;

final class WaitOnce implements ForkJoinPool.ManagedBlocker {
    private volatile boolean done;

    @Override
    public boolean isReleasable() {
        return done;
    }

    @Override
    public boolean block() throws InterruptedException {
        if (!done) {
            Thread.sleep(50); // Chỉ giả lập chờ
            done = true;
        }
        return true;
    }
}

// Trong một phương thức có khai báo throws InterruptedException:
ForkJoinPool.managedBlock(new WaitOnce());
```

Đây là ví dụ giảng giải giao diện, không nên sao chép thành một đoạn benchmark. **`ManagedBlocker` không tự đặt giới hạn truy cập API, không cung cấp timeout cho toàn pipeline, không bảo đảm không cạn tài nguyên và không biến common pool thành một pool độc lập.** Nó chỉ phù hợp khi người phát triển kiểm soát cơ chế chờ và hiểu hợp đồng Fork/Join.

Trong phần lớn ứng dụng gọi nhiều dịch vụ bên ngoài, cách rõ ràng hơn là tách tác vụ I/O sang **executor chuyên dụng**, giới hạn tải và đặt timeout tại lời gọi.

## 6. Ví dụ Java 17+ hoàn chỉnh: I/O chặn với `ExecutorService` tường minh

Thay vì sử dụng common pool ngầm, ta có thể tạo executor riêng cho tác vụ I/O chặn. Ví dụ dưới đây dùng `Thread.sleep` **chỉ để giả lập độ trễ**, nên chạy được mà không cần máy chủ hoặc kết nối mạng. Lưu thành `ControlledIoTasksDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ControlledIoTasksDemo {
    static String simulateRemoteLookup(int id) {
        try {
            Thread.sleep(80); // Giả lập thời gian chờ I/O
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Tra cứu bị ngắt", e);
        }
        return "item-" + id;
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(1, 2, 3, 4, 5, 6);

        // Giới hạn tối đa 3 worker thực thi lookup đồng thời
        // trong riêng ExecutorService này.
        ExecutorService ioPool = Executors.newFixedThreadPool(3);

        try {
            List<CompletableFuture<String>> futures = ids.stream()
                    .map(id -> CompletableFuture.supplyAsync(
                            () -> simulateRemoteLookup(id),
                            ioPool
                    ))
                    .toList();

            // Đọc kết quả theo đúng thứ tự danh sách futures.
            List<String> results = futures.stream()
                    .map(CompletableFuture::join)
                    .toList();

            System.out.println(results);
        } finally {
            ioPool.shutdown();
        }
    }
}
```

Kết quả:

```text
[item-1, item-2, item-3, item-4, item-5, item-6]
```

Điểm quan trọng trong thiết kế:

- `ids.stream()` ở đây là **Stream tuần tự** để **gửi tác vụ**. Tính đồng thời đến từ `CompletableFuture.supplyAsync(..., ioPool)`, không đến từ `.parallel()`.
- `ioPool` được truyền tường minh nên không dựa vào common pool cho phần tra cứu này.
- `newFixedThreadPool(3)` giới hạn tối đa ba worker xử lý tác vụ trong pool, dù danh sách có sáu công việc. Việc các tác vụ chạy xong theo thứ tự nào vẫn không được bảo đảm.
- `futures.stream().map(CompletableFuture::join)` lấy kết quả **theo thứ tự các future trong danh sách**, không phải theo thời điểm tác vụ hoàn thành. `join()` có thể chờ.
- `shutdown()` bắt đầu đóng executor; với ví dụ này, các `join` đã hoàn tất bình thường trước khi gọi `shutdown`. Ứng dụng sản xuất vẫn cần thiết kế nhánh lỗi, hủy và dọn dẹp theo yêu cầu.

**Lưu ý thiết yếu:** `Executors.newFixedThreadPool(3)` dùng hàng đợi tác vụ không giới hạn số phần tử theo cấu hình thường gặp. Nó giới hạn **số tác vụ chạy đồng thời**, **không** tự giới hạn số tác vụ đang chờ. Nếu đẩy hàng triệu yêu cầu, bộ nhớ hàng đợi vẫn có thể tăng mạnh.

## 7. Giới hạn hàng đợi, backpressure và timeout

Nếu ứng dụng cần giới hạn cả lượng tác vụ chờ, có thể dùng `ThreadPoolExecutor` với hàng đợi có dung lượng cố định:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor ioPool = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.CallerRunsPolicy()
);
```

Đoạn này chỉ minh họa **cấu hình**. Sau khi sử dụng, phải quản lý vòng đời và gọi `shutdown()` hoặc chính sách dừng phù hợp.

Khi bốn worker bận và 16 công việc đã xếp hàng, `CallerRunsPolicy` có thể chạy tác vụ mới **trên thread gọi `execute`**, tạo áp lực ngược (*backpressure*) bằng cách khiến phía gửi công việc cũng phải xử lý. Nhưng:

- Cơ chế này có thể **chặn thread gửi việc**; không nên tự ý áp dụng trên event loop hoặc đường xử lý yêu cầu độ trễ thấp.
- `CallerRunsPolicy` có hành vi riêng nếu executor đã shutdown; nó không thay thế quy tắc chấp nhận và hủy yêu cầu.
- Không có cấu hình queue nào tự giải quyết giới hạn kết nối CSDL, rate limit của dịch vụ hoặc retry quá mức. Các giới hạn đó cần được đặt riêng.

### Timeout của `CompletableFuture`

Trên Java 9+, có `orTimeout` để hoàn tất future theo dạng lỗi nếu quá thời hạn:

```java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(
                () -> simulateRemoteLookup(1), ioPool
        ).orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` giới hạn **thời gian đợi kết quả từ future** theo ngữ nghĩa hoàn tất của `CompletableFuture`. Nó **không tự bảo đảm ngắt được** lời gọi mạng/JDBC đang chặn phía dưới. `CompletableFuture.cancel(true)` cũng không nên bị hiểu là một cơ chế chắc chắn ngắt tác vụ đang chạy. Trong hệ thống thật, hãy cấu hình **connect timeout, read/request timeout** ở HTTP/JDBC client và quy định xử lý các tác vụ quá hạn.

Đừng chỉ thêm timeout ở future rồi mặc định rằng worker, socket hoặc tài nguyên đã được giải phóng. **Timeout của kết quả** và **hủy thực thi ở nguồn** là hai mối quan tâm khác nhau.

## 8. Muốn kiểm soát pool cho CPU-bound: dùng API có executor tường minh

Một cách hay được truyền miệng là bọc parallel stream trong `ForkJoinPool` riêng:

```java
// KHÔNG phải API chuẩn để gắn pool cho mỗi parallel Stream:
// customPool.submit(() -> data.parallelStream().map(...).toList()).join();
```

Trong một số triển khai, parallel stream được khởi chạy từ worker của một `ForkJoinPool` tùy biến có thể tận dụng pool đó. Nhưng đây **không phải hợp đồng chuẩn** để chọn executor cho mỗi pipeline; cũng không giải quyết các yêu cầu về timeout, kiểm soát I/O chặn hoặc tính biệt lập trong mọi môi trường. Không nên đưa cách này thành điều kiện đúng đắn của ứng dụng.

Nếu cần **chủ động chọn `ForkJoinPool`** cho một tính toán chia để trị, hãy dùng trực tiếp `ForkJoinTask`/`RecursiveTask`. Ví dụ Java 17+ sau tính tổng trên khoảng `[1, 1_000_001)` bằng pool có mức song song mục tiêu bằng hai. Lưu thành `DedicatedForkJoinDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class DedicatedForkJoinDemo {
    static final class RangeSumTask extends RecursiveTask<Long> {
        private static final long THRESHOLD = 20_000;

        private final long fromInclusive;
        private final long toExclusive;

        RangeSumTask(long fromInclusive, long toExclusive) {
            this.fromInclusive = fromInclusive;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            long length = toExclusive - fromInclusive;

            if (length <= THRESHOLD) {
                long sum = 0;
                for (long i = fromInclusive; i < toExclusive; i++) {
                    sum += i;
                }
                return sum;
            }

            long middle = fromInclusive + length / 2;
            RangeSumTask left = new RangeSumTask(fromInclusive, middle);
            RangeSumTask right = new RangeSumTask(middle, toExclusive);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool dedicatedPool = new ForkJoinPool(2);
        try {
            long sum = dedicatedPool.invoke(
                    new RangeSumTask(1, 1_000_001)
            );
            System.out.println(sum); // 500000500000
        } finally {
            dedicatedPool.shutdown();
        }
    }
}
```

Ở đây:

1. `dedicatedPool.invoke(task)` gửi **tác vụ Fork/Join** đến pool đã chọn **tường minh**.
2. `compute()` chia nguồn khi số phần tử lớn hơn ngưỡng; nhánh trái `fork()`, nhánh phải được tính trong luồng hiện tại, rồi `join()` kết quả trái.
3. Hai nhánh đại diện cho các khoảng **không giao nhau**, không bỏ sót, và phép cộng trong dữ liệu này không tràn `long`.
4. `new ForkJoinPool(2)` giúp kiểm soát một mức song song mục tiêu cho **pool chuyên biệt**, nhưng không nên coi đây là cam kết cứng rằng hệ điều hành chỉ tạo đúng hai thread cho mọi cơ chế hỗ trợ hoặc bù chặn.

Đây là một ví dụ **có kiểm soát executor rõ ràng**, nhưng nó dùng `RecursiveTask`, **không phải** `Stream.parallel()`. Nếu chỉ cần cộng số trên dải nhỏ, `LongStream.rangeClosed(...).sum()` vẫn gọn hơn; tự viết Fork/Join đáng cân nhắc khi thiết kế chia để trị hoặc isolation là yêu cầu thực tế.

## 9. So sánh các cách điều phối tác vụ

| Cách làm | Chọn executor cho công việc? | Tình huống phù hợp | Giới hạn phải nhớ |
| --- | --- | --- | --- |
| `stream().parallel()` | **Không** có API chuẩn truyền executor riêng | Tính toán CPU stateless, dễ chia, đủ lớn | Thường dùng pool chia sẻ theo triển khai; không có timeout/backpressure tích hợp. |
| `CompletableFuture.supplyAsync(task)` | Không chỉ định | Tác vụ bất đồng bộ đơn giản khi chấp nhận chính sách executor mặc định | Có thể dùng common pool hoặc cơ chế mặc định khác; dễ gây tranh chấp. |
| `CompletableFuture.supplyAsync(task, executor)` | **Có** | I/O hoặc công việc bất đồng bộ cần pool chuyên biệt | Phải giới hạn thread, hàng đợi, deadline và dọn dẹp. |
| `ForkJoinPool.invoke(RecursiveTask)` | **Có** | CPU divide-and-conquer cần kiểm soát pool | Tự thiết kế chia, ngưỡng, gộp kết quả và tránh blocking. |
| `ExecutorService.submit(Callable)` | **Có** | Muốn quản lý `Future`, hủy và cơ chế chờ tường minh | Hành vi hủy/ngắt phụ thuộc loại công việc và executor. |

Từ Java 21, **virtual threads** cung cấp một lựa chọn cho nhiều tác vụ I/O chặn có thể mở rộng khả năng xử lý đồng thời: `Executors.newVirtualThreadPerTaskExecutor()`. Nhưng đó là cơ chế điều phối riêng, **không có nghĩa `parallelStream()` tự chuyển sang virtual threads**, và virtual threads vẫn cần giới hạn kết nối, truy vấn và tốc độ gửi yêu cầu. Ví dụ chính của bài sử dụng Java 17 nên không gọi API Java 21.

## 10. Thứ tự, side effects, cancellation và các giới hạn khác

### Giữ tính đúng đắn trước khi tối ưu

Các lambda trong Stream thường nên **không can thiệp nguồn, không giữ trạng thái dùng chung và không phụ thuộc thứ tự thực thi giữa các phần tử**:

```java
import java.util.List;

List<Integer> doubled = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8]
```

`map` là phép biến đổi độc lập, dễ song song hóa. Với nguồn `List` có encounter order và `toList()`, thứ tự kết quả được duy trì theo ngữ nghĩa pipeline; **thứ tự thực tế các lời gọi lambda và thread xử lý có thể khác nhau**.

Ngược lại, đoạn sau không an toàn:

```java
// Không nên: ArrayList dùng chung không an toàn khi nhiều thread thêm.
// List<Integer> shared = new ArrayList<>();
// numbers.parallelStream().forEach(shared::add);
```

Nếu cần kết quả là danh sách, dùng `collect(Collectors.toList())` hoặc `toList()` thay vì thay đổi một `ArrayList` bên ngoài. Việc dùng collector chuẩn cho phép framework quản lý vùng tích lũy và gộp kết quả phù hợp.

### `forEach` và `forEachOrdered`

`forEach` trên parallel stream **không bảo đảm thứ tự xử lý**; `forEachOrdered` duy trì encounter order khi nguồn có thứ tự, nhưng có thể giảm hiệu quả song song:

```java
List.of("A", "B", "C").parallelStream()
        .forEachOrdered(System.out::print); // ABC
```

Đừng đồng nhất thứ tự **kết quả được trả về** với thứ tự **callback được chạy**. Nếu chương trình cần side effect ngoài như gửi email, ghi CSDL, gọi API theo thứ tự, hãy thiết kế điều phối riêng thay vì suy từ `parallelStream()`.

### Khi nào dừng và hủy?

Stream API có các terminal operation ngắn mạch như `findAny`, `anyMatch` hoặc `limit` ở pipeline tương ứng, nhưng đó **không phải API điều khiển hủy tất cả tác vụ** hay đặt deadline. Một số công việc có thể đã bắt đầu trước khi kết quả ngắn mạch được xác định.

Không có `stream.cancel()` chung để dừng chắc chắn mọi tác vụ đang chặn. Nếu cần deadline, hủy hoặc trả kết quả từng phần, hãy chọn mô hình task có công cụ điều phối và định nghĩa rõ việc ngắt, kiểm tra trạng thái hủy và đóng tài nguyên.

### Tránh song song lồng nhau theo thói quen

Một parallel stream bên trong lambda của parallel stream khác có thể tăng độ phức tạp lập lịch, tạo nhiều tác vụ nhỏ và gây khó đo hiệu năng. Không mặc định song song ở cả hai cấp; thường nên chọn **một cấp phù hợp** để song song và giữ các bước còn lại tuần tự, hoặc thiết kế Fork/Join có ngưỡng chia rõ ràng.

## 11. Cấu hình và quan sát common pool: biết giới hạn can thiệp

JDK có một số system property ảnh hưởng đến common pool, chẳng hạn `java.util.concurrent.ForkJoinPool.common.parallelism`. Việc cấu hình này có phạm vi **toàn JVM**, không phải chỉ một `parallelStream()`. Nó cũng chịu ảnh hưởng thời điểm common pool được khởi tạo và cấu hình runtime.

Vì vậy:

- Không dùng system property toàn JVM như một phương thức chọn executor riêng cho từng pipeline.
- Không tùy ý chỉnh parallelism của common pool chỉ để một module chạy nhanh hơn; có thể làm ảnh hưởng module khác.
- Không lấy `Runtime.getRuntime().availableProcessors()` làm số luồng chính xác trong mọi môi trường, nhất là khi cấu hình CPU/cgroup/container thay đổi.
- Quan sát `ForkJoinPool.getCommonPoolParallelism()`, CPU, độ trễ, hàng đợi, trạng thái blocking và các chỉ số hệ thống, nhưng không suy từ một con số rằng throughput đã được kiểm soát.

Với nhu cầu kiểm soát chặt, hãy chọn cơ chế có **executor truyền tường minh**, đặt giới hạn tải và timeout ở tầng gọi dịch vụ.

### Đo hiệu năng thay vì suy luận từ `.parallel()`

Để đánh giá cần hay không cần parallel stream, đo trên dữ liệu và môi trường đại diện:

1. Xác định công việc là CPU-bound hay I/O-bound; đo tỉ lệ thời gian thật sự dùng CPU so với thời gian chờ.
2. Đo cả **throughput và latency**, không chỉ thời gian của một phép chạy ấm bộ nhớ.
3. So sánh bản tuần tự, parallel stream, và executor chuyên biệt nếu có nhiều I/O.
4. Kiểm tra tải cùng lúc từ các module khác khi dùng common pool.
5. Với phép đo vi mô Java, cân nhắc **JMH** thay vì lấy thời gian một lần `System.nanoTime()` rồi kết luận.

Không nên tăng số luồng quá mức chỉ vì tác vụ đang chậm; có thể làm tăng tranh chấp CPU, kết nối, bộ nhớ hoặc giới hạn phía dịch vụ đích.

## 12. Những lỗi thường gặp

| Lỗi | Tác động có thể xảy ra | Cách khắc phục |
| --- | --- | --- |
| Tin rằng `parallelStream()` luôn dùng một pool riêng | Các công việc không liên quan có thể tranh chấp common pool | Hiểu giới hạn API; dùng executor tường minh khi cần isolation. |
| Đặt I/O đồng bộ chặn trong `map` của parallel stream | Worker bị chiếm khi chờ; độ trễ module khác tăng | Dùng executor riêng, timeout và giới hạn tải I/O. |
| Tăng `common.parallelism` để “sửa” mọi vấn đề blocking | Ảnh hưởng phạm vi JVM, tăng tranh chấp tài nguyên | Điều chỉnh kiến trúc, timeout, backpressure; chỉ cấu hình global có chủ đích. |
| Coi `ManagedBlocker` bảo đảm bù đủ worker | Vẫn có thể thiếu tài nguyên hoặc bị nghẽn | Dùng nó trong trường hợp chuyên biệt, không thay thế cách ly pool. |
| Dùng `newFixedThreadPool(n)` rồi cho rằng hàng đợi cũng bị giới hạn | Tác vụ chờ có thể tích lũy rất lớn | Dùng queue có dung lượng, chính sách từ chối/backpressure hoặc semaphore. |
| Chỉ dùng `orTimeout` rồi tưởng đã ngắt I/O | Future lỗi nhưng công việc gốc vẫn có thể chạy/chặn | Đặt timeout tại HTTP/JDBC client và thiết kế hủy tài nguyên. |
| Tin việc bọc parallel stream trong custom FJP là API portable chọn pool | Phụ thuộc implementation, khó kiểm soát | Dùng ForkJoinTask hoặc executor API có hợp đồng tường minh. |
| Dùng `forEach` với trạng thái mutable dùng chung | Race và kết quả sai | Dùng `collect`, reduce có phép gộp đúng hoặc đồng bộ hóa theo thiết kế. |
| Cho rằng số thread luôn bằng số CPU | Dự đoán sai mức đồng thời và hiệu năng | Quan sát runtime và đo tải thực tế. |
| Song song các tác vụ quá nhỏ hoặc lồng nhau | Overhead vượt lợi ích, khó lập lịch | Chọn cấp song song và ngưỡng chia phù hợp. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Có thể gọi `numbers.parallelStream().executor(myExecutor)` trong Java Stream API chuẩn không?

**Đáp án:** Không. Stream API không cung cấp phương thức chuẩn để gắn executor cho từng pipeline. Khi cần chọn executor tường minh, dùng API như `CompletableFuture.supplyAsync(task, executor)` hoặc `ForkJoinPool.invoke(task)`.

**Câu 2.** Vì sao `ForkJoinPool.commonPool()` có thể gây ảnh hưởng chéo giữa nhiều module?

**Đáp án:** Trong triển khai thông dụng, nó là pool dùng chung trong JVM. Khi một module giữ nhiều worker bằng tác vụ chặn, module khác dùng cùng pool có thể thiếu năng lực xử lý.

**Câu 3.** `newFixedThreadPool(4)` có tự giới hạn số yêu cầu đang chờ ở bốn không?

**Đáp án:** Không. Nó giới hạn số worker xử lý đồng thời; hàng đợi mặc định không có một giới hạn dung lượng nhỏ được đặt sẵn. Cần thêm bounded queue, chính sách từ chối hoặc kiểm soát số yêu cầu đầu vào.

**Câu 4.** `CompletableFuture.orTimeout(...)` có bảo đảm socket HTTP đã đóng và lời gọi I/O bị ngắt không?

**Đáp án:** Không. Nó ảnh hưởng trạng thái hoàn tất future; hành vi hủy tác vụ gốc phụ thuộc lời gọi và cơ chế thực thi. Cần đặt timeout, hủy và đóng tài nguyên ở client thực tế.

**Câu 5.** Tại sao `parallelStream().map(cpuHeavyPureFunction).collect(...)` có thể phù hợp hơn `parallelStream().map(blockingDatabaseQuery).collect(...)`?

**Đáp án:** Tính toán CPU độc lập có thể chia/gộp hiệu quả; truy vấn chặn giữ worker khi chờ I/O, tạo tranh chấp trên pool và kết nối. Truy vấn cần cơ chế điều phối có giới hạn và timeout.

**Câu 6.** Cần chọn một `ForkJoinPool(2)` dành riêng cho thuật toán chia để trị. Có cách nào có hợp đồng rõ ràng?

**Đáp án:** Gửi trực tiếp `RecursiveTask`/ `ForkJoinTask` qua `dedicatedPool.invoke(task)` hoặc `submit`. Cách này điều khiển pool của tác vụ đã gửi; đừng coi việc bọc một parallel stream bên trong pool là phương thức cấu hình chuẩn của Stream.

## Ghi nhớ

- `parallelStream()` chỉ yêu cầu pipeline xử lý song song; **không có API chuẩn truyền executor riêng cho từng Stream**.
- Trong triển khai OpenJDK thông dụng, parallel stream thường tận dụng **`ForkJoinPool.commonPool()` dùng chung**, nên công việc chặn có thể ảnh hưởng những tác vụ khác.
- `ForkJoinPool` hiệu quả hơn cho công việc CPU có thể chia và gộp; **I/O chặn cần giới hạn đồng thời, timeout và backpressure** ở mô hình thực thi thích hợp.
- `ManagedBlocker` hỗ trợ thông báo một số thao tác chặn nhưng không tự mang lại isolation hoặc bảo đảm số worker; `orTimeout` không tự ngắt công việc nền.
- Khi cần kiểm soát rõ ràng, dùng `CompletableFuture.supplyAsync(..., executor)` / `ExecutorService` hoặc gửi `ForkJoinTask` đến pool chuyên biệt; giữ lambda an toàn, quản lý tài nguyên và **đo hiệu năng trước khi tối ưu**.
