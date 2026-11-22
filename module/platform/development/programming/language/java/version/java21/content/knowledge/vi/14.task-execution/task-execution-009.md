# Fan-out nhiều tác vụ bằng các API ExecutorService đã ổn định

Fan-out là cách chia một yêu cầu thành nhiều tác vụ độc lập để thực hiện đồng thời; fan-in là bước thu thập và tổng hợp kết quả. Trong Java 21, có thể xây dựng mô hình này bằng các API ổn định của `ExecutorService`, `Callable`, `Future`, `invokeAll()` và `invokeAny()`. Khi cần xử lý kết quả theo thứ tự hoàn thành, kết hợp `ExecutorCompletionService`.

Chọn executor theo đặc điểm công việc: virtual-thread-per-task executor phù hợp với nhiều tác vụ thường xuyên chờ I/O; fixed-size platform-thread executor phù hợp với tác vụ CPU-bound hoặc khi cần giới hạn số worker. Dù chọn loại nào, fan-out vẫn cần giới hạn số công việc đang hoạt động, xử lý lỗi và hủy tác vụ đúng cách.

## 1. Mô hình fan-out/fan-in

Một request tổng hợp dữ liệu từ nhiều nguồn thường có các bước:

1. Nhận đầu vào chung.
2. Tạo một tác vụ cho mỗi nguồn dữ liệu hoặc phần việc độc lập.
3. Gửi các tác vụ vào executor.
4. Chờ kết quả, xử lý lỗi và timeout.
5. Tổng hợp kết quả thành phản hồi chung.

Ví dụ, một trang tổng quan có thể gọi đồng thời dịch vụ đơn hàng, thanh toán và giao vận rồi ghép kết quả thành một `Dashboard`.

```text
                         Request
                            |
                     Fan-out tasks
                    /       |       \
             Orders API  Payment API  Shipping API
                    \       |       /
                     Fan-in results
                            |
                        Dashboard
```

Các tác vụ chỉ nên chạy song song khi chúng không phụ thuộc kết quả của nhau. Nếu tác vụ B cần kết quả A, hãy thể hiện quan hệ phụ thuộc rõ ràng thay vì gửi cả hai như các công việc độc lập.

## 2. Chọn ExecutorService phù hợp

`ExecutorService` tách việc gửi tác vụ khỏi cách executor tổ chức thread và lập lịch. Java 21 cung cấp các factory phổ biến:

| Executor | Phù hợp với | Đặc điểm cần nhớ |
|---|---|---|
| `Executors.newVirtualThreadPerTaskExecutor()` | Nhiều tác vụ I/O có thời gian chờ lớn | Mỗi task chạy trên virtual thread riêng; số task không được giới hạn bởi executor |
| `Executors.newFixedThreadPool(n)` | Tác vụ CPU-bound hoặc workload cần số worker cố định | Số worker cố định nhưng hàng đợi mặc định không giới hạn |
| `Executors.newWorkStealingPool()` | Công việc chia nhỏ thành nhiều task CPU có thể lấy cắp | Dựa trên work-stealing; không phải giới hạn tải đầu vào |
| `ThreadPoolExecutor` với bounded queue | Hệ thống cần giới hạn worker và backlog | Có thể cấu hình queue hữu hạn và chính sách từ chối |

Với tác vụ chờ HTTP hoặc JDBC, virtual thread giúp tăng khả năng phục vụ đồng thời. Với phép tính CPU-bound kéo dài, tăng số virtual thread không làm tăng năng lực CPU; nên giới hạn worker theo năng lực máy và đo đạc thực tế.

## 3. Gửi từng tác vụ bằng submit() và nhận Future

`submit()` nhận `Runnable` hoặc `Callable` và trả về `Future`. `Runnable` không trả kết quả; `Callable<V>` trả về giá trị kiểu `V` và có thể ném checked exception.

```java
record Quote(String supplier, BigDecimal price) { }

static Quote fetchQuote(String supplier) throws IOException {
    // Gọi dịch vụ báo giá của supplier.
    return new Quote(supplier, remotePrice(supplier));
}

static List<Quote> loadQuotes(List<String> suppliers)
        throws InterruptedException, ExecutionException {

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        List<Future<Quote>> futures = new ArrayList<>();

        for (String supplier : suppliers) {
            futures.add(executor.submit(() -> fetchQuote(supplier)));
        }

        List<Quote> quotes = new ArrayList<>();
        for (Future<Quote> future : futures) {
            quotes.add(future.get());
        }

        return quotes;
    }
}
```

Các lời gọi `submit()` gửi task để executor thực thi. `future.get()` chờ task tương ứng hoàn tất và trả kết quả. Nếu task ném exception, `get()` ném `ExecutionException` và exception gốc nằm trong `getCause()`.

Danh sách `Future` trong ví dụ được duyệt theo thứ tự gửi task. Nếu task cuối hoàn tất trước task đầu, code vẫn chờ `Future` đầu tiên trước khi đọc kết quả tiếp theo. Đây có thể tạo head-of-line waiting ở bước fan-in, dù các task vẫn chạy đồng thời.

`submit()` không ném exception của task trực tiếp tại thời điểm gửi. Exception được giữ trong `Future` và chỉ quan sát được khi gọi `get()`. Vì vậy, không bỏ qua Future nếu kết quả hoặc lỗi của task quan trọng.

## 4. Dùng invokeAll() khi cần mọi kết quả

`invokeAll()` nhận một collection `Callable` và trả về danh sách `Future` sau khi tất cả task hoàn tất hoặc bị hủy. Danh sách Future có thứ tự tương ứng với thứ tự iterator của collection task đầu vào.

```java
static List<Quote> loadAllQuotes(List<String> suppliers)
        throws InterruptedException {

    List<Callable<Quote>> tasks = suppliers.stream()
            .<Callable<Quote>>map(supplier -> () -> fetchQuote(supplier))
            .toList();

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        List<Future<Quote>> futures = executor.invokeAll(tasks);
        List<Quote> quotes = new ArrayList<>();
        List<Throwable> failures = new ArrayList<>();

        for (Future<Quote> future : futures) {
            try {
                quotes.add(future.get());
            } catch (ExecutionException failure) {
                failures.add(failure.getCause());
            }
        }

        if (!failures.isEmpty()) {
            throw new QuoteAggregationException(failures);
        }

        return quotes;
    }
}
```

`QuoteAggregationException` trong ví dụ là exception của ứng dụng, có thể giữ từng nguyên nhân dưới dạng suppressed exception:

```java
static final class QuoteAggregationException extends RuntimeException {
    QuoteAggregationException(List<Throwable> failures) {
        super("Không lấy được đầy đủ báo giá từ các nguồn");
        failures.forEach(this::addSuppressed);
    }
}
```

Trong ví dụ, `invokeAll()` đợi mọi task kết thúc. Một task thất bại không làm `invokeAll()` ném ngay exception của task đó; Future tương ứng sẽ ở trạng thái completed exceptionally và `get()` ném `ExecutionException`. Vì vậy, fan-in có thể thu thập nhiều lỗi thay vì dừng ở lỗi đầu tiên.

Nếu thread gọi `invokeAll()` bị interrupt, phương thức ném `InterruptedException` và hủy các task chưa hoàn tất. Caller nên truyền tiếp exception hoặc khôi phục interrupt status nếu bắt rồi xử lý tại chỗ.

### invokeAll() có timeout

Overload có timeout chỉ chờ trong khoảng thời gian được chỉ định:

```java
List<Future<Quote>> futures = executor.invokeAll(
        tasks,
        2,
        TimeUnit.SECONDS
);

for (Future<Quote> future : futures) {
    if (future.isCancelled()) {
        System.out.println("Task chưa hoàn tất trước deadline");
        continue;
    }

    try {
        Quote quote = future.get();
        System.out.println(quote);
    } catch (ExecutionException failure) {
        System.err.println("Task thất bại: " + failure.getCause());
    }
}
```

Khi hết thời gian, các task chưa hoàn tất bị cancel. Future của chúng thường có `isCancelled() == true`. Timeout tính cho toàn bộ lời gọi `invokeAll`, bao gồm thời gian task chờ được chạy và thời gian thực thi.

Hủy task là yêu cầu dừng, không phải bằng chứng code đã dừng tức thì. Task cần phản ứng với interrupt hoặc dùng API I/O có cơ chế timeout/cancellation phù hợp.

## 5. Dùng invokeAny() khi chỉ cần một kết quả thành công

`invokeAny()` chạy các `Callable` và trả kết quả của một task hoàn thành thành công. Khi có kết quả thành công, các task còn lại chưa hoàn tất sẽ bị hủy. Nếu tất cả task đều thất bại, phương thức ném `ExecutionException`.

Trường hợp phù hợp là gọi một trong nhiều replica có thể trả cùng một dữ liệu:

```java
static Product loadFromAnyReplica(String productId)
        throws InterruptedException, ExecutionException {

    List<Callable<Product>> replicas = List.of(
            () -> fetchProduct("replica-a", productId),
            () -> fetchProduct("replica-b", productId),
            () -> fetchProduct("replica-c", productId)
    );

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        return executor.invokeAny(replicas);
    }
}
```

Phương thức trả về kết quả thành công đầu tiên theo thời gian hoàn tất, không nhất thiết là task đầu tiên trong danh sách. Một task thất bại sớm không ngăn task khác tiếp tục; chỉ khi không task nào thành công thì caller mới nhận `ExecutionException`.

Overload `invokeAny(tasks, timeout, unit)` ném `TimeoutException` nếu không có task nào thành công trong thời gian cho phép. Khi phương thức kết thúc, các task còn lại bị hủy.

Chỉ dùng `invokeAny()` khi các tác vụ có thể chạy độc lập và việc có một kết quả bất kỳ là đúng về nghiệp vụ. Không dùng cho thao tác ghi có side effect như trừ tiền, tạo đơn hoặc gửi email nếu các bản sao cùng chạy có thể thực hiện hành động nhiều lần. Cancellation không đảm bảo tác vụ đã gửi request tới dịch vụ bên ngoài có thể thu hồi side effect đó.

## 6. Xử lý kết quả theo thứ tự hoàn thành

Nếu muốn xử lý task nào xong trước thì nhận trước, dùng `ExecutorCompletionService`. Nó bọc một `ExecutorService`, gửi task qua `submit()` và đưa Future hoàn tất vào completion queue.

```java
static List<Quote> loadInCompletionOrder(List<String> suppliers)
        throws InterruptedException, ExecutionException {

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        CompletionService<Quote> completed =
                new ExecutorCompletionService<>(executor);

        for (String supplier : suppliers) {
            completed.submit(() -> fetchQuote(supplier));
        }

        List<Quote> quotes = new ArrayList<>();
        List<Throwable> failures = new ArrayList<>();
        for (int i = 0; i < suppliers.size(); i++) {
            Future<Quote> future = completed.take();
            try {
                quotes.add(future.get());
            } catch (ExecutionException failure) {
                failures.add(failure.getCause());
            }
        }

        if (!failures.isEmpty()) {
            throw new QuoteAggregationException(failures);
        }

        return quotes;
    }
}
```

`take()` chờ Future tiếp theo hoàn tất; `poll()` kiểm tra ngay mà không chờ; `poll(timeout, unit)` chờ tối đa khoảng thời gian chỉ định. Thứ tự nhận không phụ thuộc thứ tự submit mà phụ thuộc thời điểm task hoàn tất.

`ExecutorCompletionService` hữu ích khi có thể xử lý và lưu từng kết quả ngay khi nó sẵn sàng, ví dụ hiển thị kết quả tìm kiếm từng nguồn hoặc cập nhật tiến độ. Nếu cần giữ thứ tự đầu vào, hãy gắn index với mỗi task rồi sắp xếp kết quả sau khi thu thập.

## 7. Giới hạn số tác vụ đang hoạt động

Fan-out không đồng nghĩa gửi tất cả công việc vào executor cùng một lúc. Hai factory phổ biến đều có thể tạo backlog lớn:

- `newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task và không giới hạn số thread.
- `newFixedThreadPool(n)` giới hạn số worker nhưng dùng hàng đợi chia sẻ không giới hạn.

Nếu danh sách đầu vào rất lớn, gửi tất cả task có thể tiêu thụ nhiều bộ nhớ, giữ quá nhiều request chờ và làm quá tải dịch vụ phía sau. Có thể xử lý theo batch để giới hạn số task được gửi trong mỗi lượt:

```java
static List<Quote> loadInBatches(List<String> suppliers, int batchSize)
        throws InterruptedException, ExecutionException {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    List<Quote> result = new ArrayList<>();

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        for (int start = 0; start < suppliers.size(); start += batchSize) {
            int end = Math.min(start + batchSize, suppliers.size());
            List<Callable<Quote>> batch = suppliers.subList(start, end).stream()
                    .<Callable<Quote>>map(supplier -> () -> fetchQuote(supplier))
                    .toList();

            for (Future<Quote> future : executor.invokeAll(batch)) {
                result.add(future.get());
            }
        }
    }

    return result;
}
```

Batch giới hạn số task trong một đợt và chỉ gửi đợt kế tiếp sau khi đợt hiện tại hoàn tất. Đổi lại, một task chậm trong batch sẽ làm chậm thời điểm bắt đầu batch tiếp theo. Nếu cần sử dụng tài nguyên liên tục và xử lý kết quả ngay khi hoàn tất, có thể kết hợp `ExecutorCompletionService` với một giới hạn số task đang in-flight.

### Dùng ThreadPoolExecutor với bounded queue

Khi cần giới hạn cả số worker lẫn backlog, tạo `ThreadPoolExecutor` với queue hữu hạn:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        Thread.ofPlatform().name("cpu-worker-", 0).factory(),
        new ThreadPoolExecutor.AbortPolicy()
);

try (executor) {
    Future<Result> future = executor.submit(this::calculate);
    Result result = future.get();
}
```

Khi cả 8 worker đang bận và queue đã đầy, `AbortPolicy` từ chối task mới bằng `RejectedExecutionException`. Caller cần chuyển tình trạng quá tải thành phản hồi phù hợp, retry có giới hạn hoặc đẩy công việc sang hệ thống queue bên ngoài. Không retry vô hạn vì điều đó có thể làm hệ thống quá tải nặng hơn.

`CallerRunsPolicy` là một lựa chọn backpressure khác: khi executor còn hoạt động nhưng đã đầy, task được chạy trên thread gọi `execute()`. Điều này làm chậm bên gửi nhưng cũng có thể khiến thread xử lý request phải chạy công việc nặng; chỉ dùng khi hành vi đó phù hợp với kiến trúc.

## 8. Timeout, cancellation và interrupt

`Future` cung cấp các phương thức quan trọng:

| API | Tác dụng |
|---|---|
| `get()` | Chờ hoàn tất và nhận kết quả |
| `get(timeout, unit)` | Chờ có giới hạn; ném `TimeoutException` khi hết thời gian |
| `cancel(true)` | Yêu cầu hủy và cho phép interrupt thread đang chạy |
| `isDone()` | Kiểm tra Future đã hoàn tất, thất bại hoặc bị hủy |
| `isCancelled()` | Kiểm tra Future đã bị hủy |

Khi một task bị interrupt, code nên dừng hợp tác và giải phóng tài nguyên bằng try-with-resources. Không bắt `InterruptedException` rồi bỏ qua; nếu không thể truyền exception lên, khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()`.

Ví dụ chờ có deadline:

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Response> future = executor.submit(this::callRemoteService);

    try {
        Response response = future.get(2, TimeUnit.SECONDS);
        process(response);
    } catch (TimeoutException timeout) {
        future.cancel(true);
        throw new ServiceTimeoutException(timeout);
    } catch (ExecutionException failure) {
        throw new ServiceCallException(failure.getCause());
    }
}
```

`get(timeout)` chỉ giới hạn thời gian caller chờ kết quả. Khi timeout, task vẫn có thể chạy nếu chưa gọi `cancel(true)`. Ngay cả sau khi gọi cancel, task hoặc thư viện I/O có thể cần thời gian để phản ứng với interrupt. Đặt timeout ở API I/O cụ thể và dùng deadline tổng cho request; đừng dựa riêng vào timeout của Future.

Nếu thread đang chờ `invokeAll`, `invokeAny` hoặc `CompletionService.take()` bị interrupt, truyền tiếp `InterruptedException` khi có thể. Đây là tín hiệu hủy từ caller và không nên bị biến thành một lỗi nghiệp vụ thông thường.

## 9. Quản lý vòng đời ExecutorService trong Java 21

Trong Java 21, `ExecutorService` triển khai `AutoCloseable`, vì vậy có thể dùng try-with-resources:

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> fetchText());
    System.out.println(future.get());
}
```

Khi thoát khỏi khối, `close()` khởi tạo orderly shutdown và chờ các task đã submit hoàn tất. Sau khi shutdown, executor không nhận task mới. Do đó, không đóng executor ngay sau khi gửi task nếu caller vẫn cần submit thêm công việc.

Các phương thức vòng đời:

- `shutdown()` ngừng nhận task mới nhưng tiếp tục chạy các task đã submit.
- `shutdownNow()` cố gắng dừng task đang chạy bằng interrupt và trả về danh sách task chưa bắt đầu; đây là nỗ lực best-effort.
- `awaitTermination(timeout, unit)` chờ executor kết thúc trong thời gian giới hạn.
- `close()` thực hiện shutdown có trật tự và chờ executor kết thúc. Nếu thread gọi bị interrupt trong lúc chờ, `close()` gọi hành vi tương đương `shutdownNow()`, tiếp tục chờ các task đang hoạt động kết thúc rồi khôi phục interrupt status trước khi trả về.

`close()` có thể chờ lâu nếu task không kết thúc. Vì vậy, task I/O cần timeout, cancellation và cleanup đúng cách. Đóng executor không tự đóng socket hoặc connection do task sở hữu; task vẫn phải giải phóng resource của mình.

## 10. Phối hợp kết quả và xử lý lỗi

Trong một fan-out, có thể chọn một trong ba chính sách:

| Chính sách | Cách triển khai | Khi phù hợp |
|---|---|---|
| All-or-nothing | Nếu một task lỗi, hủy các task còn lại và trả lỗi chung | Tất cả dữ liệu đều bắt buộc để tạo kết quả |
| Partial result | Thu thập kết quả thành công và ghi nhận từng lỗi | Dashboard có thể hiển thị dữ liệu thiếu một phần |
| First successful | Dùng `invokeAny()` và lấy kết quả thành công đầu tiên | Nhiều replica cung cấp cùng một dữ liệu |

Không nên mặc định task lỗi nào cũng có thể bỏ qua. Ví dụ, thiếu dữ liệu giao vận có thể chấp nhận được trên dashboard, nhưng thiếu kết quả kiểm tra hạn mức tín dụng có thể phải từ chối giao dịch.

Khi gom nhiều lỗi, giữ lại exception gốc để phục vụ log và truy vết. Có thể dùng một exception tổng hợp và gắn các lỗi thành suppressed exception:

```java
RuntimeException aggregate = new RuntimeException("Một số nguồn không phản hồi");

for (Throwable failure : failures) {
    aggregate.addSuppressed(failure);
}

throw aggregate;
```

Nếu kết quả của các task được ghi vào collection dùng chung, hãy bảo vệ dữ liệu bằng cấu trúc concurrent hoặc chỉ tổng hợp ở thread điều phối sau khi Future hoàn tất. Không thêm vào `ArrayList` dùng chung từ nhiều task mà không có đồng bộ hóa.

## 11. Các lỗi thường gặp khi fan-out

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gửi quá nhiều task cùng lúc | Tăng bộ nhớ, queue và tải downstream | Batch, giới hạn in-flight hoặc bounded queue |
| Gọi `Future.get()` ngay sau từng `submit()` | Vô tình tuần tự hóa việc chờ kết quả | Submit toàn bộ nhóm trước, rồi thu thập; hoặc dùng CompletionService |
| Không gọi `get()` hoặc không kiểm tra Future | Bỏ sót exception của task | Thu kết quả và xử lý `ExecutionException` |
| Dùng `invokeAny()` cho task có side effect | Nhiều bản sao có thể thực hiện hành động dù chỉ nhận một kết quả | Chỉ dùng cho thao tác an toàn/idempotent hoặc có idempotency key |
| Cho rằng `cancel(true)` dừng task ngay lập tức | Task vẫn có thể chạy và giữ resource | Thiết kế task phản ứng với interrupt và timeout I/O |
| Không xử lý `InterruptedException` | Caller mất khả năng hủy fan-out | Truyền tiếp hoặc khôi phục interrupt status |
| Đóng executor trước khi submit xong | Task mới bị từ chối | Đặt executor ở phạm vi bao trùm toàn bộ fan-out/fan-in |
| Chờ task con trong cùng fixed pool đã hết worker | Có thể deadlock/starvation | Tránh nested blocking dependency hoặc dùng executor phù hợp |

## 12. Quy trình thiết kế fan-out an toàn

1. Xác định task nào độc lập và task nào phụ thuộc kết quả của task khác.
2. Chọn executor theo workload: virtual thread cho I/O, worker hữu hạn cho CPU hoặc ThreadPoolExecutor với bounded queue khi cần giới hạn backlog.
3. Chọn API điều phối: `submit()` cho từng Future, `invokeAll()` khi cần tất cả, `invokeAny()` khi chỉ cần một thành công, CompletionService khi cần kết quả theo thứ tự hoàn tất.
4. Đặt deadline tổng và timeout cho từng thao tác I/O; xác định task nào phải hủy khi quá hạn.
5. Chọn chính sách lỗi: all-or-nothing, partial result hoặc first successful.
6. Giới hạn số task đang hoạt động và tải lên database/dịch vụ bên ngoài.
7. Thu thập kết quả, xử lý exception và interrupt; không nuốt lỗi hoặc giả định cancellation đã hoàn tất.
8. Đóng executor ở phạm vi điều phối bằng try-with-resources và theo dõi latency, queue depth, rejection cùng lỗi downstream.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — ExecutorCompletionService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
- [Java SE 21 API — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
