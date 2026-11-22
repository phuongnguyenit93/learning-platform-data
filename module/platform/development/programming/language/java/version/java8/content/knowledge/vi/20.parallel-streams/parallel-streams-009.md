# I/O chặn và ảnh hưởng lên common pool trong Parallel Stream (Java 8+)

## 1. Bài toán và mục tiêu

**Parallel Stream** có thể chia dữ liệu thành nhiều phần để xử lý đồng thời. Khi các phần tử đòi hỏi nhiều tính toán CPU độc lập, điều này có thể đem lại lợi ích. Tuy nhiên, nếu mapper phải chờ **blocking I/O** như HTTP đồng bộ, truy vấn JDBC, đọc socket hoặc file chậm, thread chạy mapper bị giữ trong thời gian chờ. **parallel() không tự làm lời gọi I/O đồng bộ trở thành bất đồng bộ.**

Trong cách thực thi phổ biến của JDK, Parallel Stream có thể dùng **ForkJoinPool.commonPool()**, pool chia sẻ giữa những thành phần trong JVM. Nếu nhiều worker bị giữ bởi I/O chặn, các tác vụ khác dùng chung pool có thể bị chậm, ngay cả khi chúng chỉ xử lý CPU.

Sau bài này, bạn có thể giải thích cơ chế đó, xác định giới hạn của cơ chế bù worker, và chọn khi nào dùng stream tuần tự, executor riêng, API async hoặc virtual threads. Bài tập trung vào kiến thức hiện còn áp dụng trong Java hiện đại; tính năng chỉ có từ Java 21 được ghi rõ.

## 2. Parallel Stream và common pool

~~~java
int squares = java.util.stream.IntStream.rangeClosed(1, 4)
        .parallel()
        .map(n -> n * n)
        .sum(); // 30
~~~

Ở ví dụ này, kết quả là **1 + 4 + 9 + 16 = 30**. Các phép bình phương độc lập và thuần CPU; phần mềm có thể chia việc rồi kết hợp kết quả.

**ForkJoinPool** là một ExecutorService tối ưu cho việc tách công việc thành các tác vụ nhỏ. Nó sử dụng **work stealing**: worker rảnh có thể lấy công việc từ worker khác. **ForkJoinPool.commonPool()** là pool dùng chung mà các thành phần trong cùng JVM có thể sử dụng.

~~~text
                         Một JVM
                            |
       +--------------------+--------------------+
       |                    |                    |
  Parallel Stream     CompletableFuture      ForkJoinTask
   thông thường        async mặc định       dùng pool chung
       |                    |                    |
       +--------------------+--------------------+
                            |
                   ForkJoinPool.commonPool()
                            |
                  Các worker được chia sẻ
~~~

Đây là **mô hình triển khai thường gặp**, không phải hợp đồng đảm bảo mọi parallel stream trong mọi ngữ cảnh sẽ chạy ở một pool cố định. **Stream.parallel() không nhận tham số Executor.** Không giả định tên worker, số lượng thread hoặc thứ tự chạy của lambda.

**commonPool().getParallelism()** trả *target parallelism*, không phải số kết nối HTTP/JDBC hoặc mức request đồng thời an toàn. Giá trị này còn phụ thuộc tài nguyên CPU, cấu hình và môi trường JVM.

## 3. Phân biệt CPU-bound và I/O-bound

| Loại công việc | Thread làm gì? | Ví dụ | Cách tổ chức thường phù hợp |
| --- | --- | --- | --- |
| CPU-bound | Thực hiện phép tính | Tính toán độc lập, biến đổi dữ liệu thuần | Xem xét Parallel Stream sau benchmark |
| Blocking I/O | Chờ nguồn ngoài hoàn tất | HTTP sync, JDBC, socket, file read chậm | Executor riêng hoặc virtual threads tùy ngữ cảnh |
| I/O bất đồng bộ | API trả completion trong tương lai | HttpClient.sendAsync | Điều phối futures, timeout và mức đồng thời |
| Workload hỗn hợp | Vừa chờ I/O vừa tính CPU | Tải dữ liệu rồi xử lý | Xác định giới hạn của từng pha |

Đoạn minh họa sau **không phải chương trình độc lập** vì repository và Item chỉ là ví dụ:

~~~java
List<Item> items = ids.parallelStream()
        .map(repository::findById)
        .collect(Collectors.toList());
~~~

Nếu **findById** truy vấn DB đồng bộ, worker chạy mapper phải chờ. **Không được đồng nhất chạy song song với không chặn thread.**

## 4. Điều gì xảy ra khi worker bị giữ bởi I/O?

~~~text
Worker A: [ HTTP call ] ...... chờ ....... [ tiếp tục ]
Worker B: [ JDBC call ] ...... chờ ....... [ tiếp tục ]
Worker C: [ socket ] ......... chờ ....... [ tiếp tục ]
                  |
          Các tác vụ khác chờ worker
~~~

Khi nhiều worker bị giữ:

- **Thông lượng (throughput)** có thể giảm vì ít việc được hoàn thành mỗi giây.
- **Độ trễ (latency)** tăng vì task khác có thể phải chờ.
- **p95/p99** có thể xấu đi khi những lời gọi I/O chậm gây tắc nghẽn.
- Những thành phần **không liên quan** dùng chung common pool có thể bị ảnh hưởng.
- Nếu task đang chạy lại chờ một Future mà chính pool đó cần thực thi để hoàn tất, có nguy cơ thiếu tiến triển hoặc chờ kéo dài.

Ví dụ hình dung: **12** công việc độc lập, mỗi việc giữ một worker **200 ms**, cùng lúc tối đa **4** việc. Nếu chia thành ba đợt hoàn hảo, bỏ qua overhead, tổng thời gian khoảng **3 × 200 ms = 600 ms**. Đây là **mô hình giả định**, không phải dự đoán số worker hoặc latency thực tế của ForkJoinPool.

Blocking I/O trong Parallel Stream không đương nhiên gây deadlock hoặc luôn chậm hơn tuần tự. Vấn đề là mức sử dụng tài nguyên và khả năng cách ly khi tải tăng.

## 5. ForkJoinPool có tự động bù worker không?

ForkJoinPool có cơ chế hỗ trợ tiến triển của các tác vụ fork/join và API **ForkJoinPool.managedBlock(ManagedBlocker)**. Khi một lời gọi blocking được tích hợp đúng vào giao thức này, pool **có thể** bổ sung worker để duy trì mức song song trong giới hạn được phép.

Nhưng tài liệu API nêu rõ: **không có bảo đảm bù worker khi gặp I/O hoặc đồng bộ không được quản lý**. Một lời gọi HTTP/JDBC đồng bộ hoặc **Thread.sleep** trong mapper không tự nhiên trở thành managed blocking.

~~~text
Fork/join hoặc ManagedBlocker được phối hợp đúng
    -> pool có thể bù worker

HTTP/JDBC/sleep chặn không được quản lý
    -> không có bảo đảm tự bù đủ worker
~~~

**ManagedBlocker** vẫn là API hiện hành. Nó có các phương thức **isReleasable()** và **block()** cần được triển khai đúng. Đây là công cụ chuyên sâu cho mã fork/join, không phải cách chữa mặc định cho mọi pipeline I/O. Với I/O của dịch vụ ngoài, việc chọn executor riêng hoặc API async thường minh bạch hơn.

## 6. Chương trình Java đầy đủ: mô phỏng I/O chặn

Để chạy mà không phụ thuộc mạng hoặc DB, **Thread.sleep(40)** được dùng mô phỏng một thao tác phải chờ. Đây **không phải phép đo hiệu năng HTTP/JDBC**.

Tạo tệp **BlockingIoCommonPoolDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class BlockingIoCommonPoolDemo {
    static String simulatedIo(int id) {
        try {
            Thread.sleep(40);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting", ex);
        }
        return "item-" + id;
    }

    public static void main(String[] args) {
        List<Integer> ids = Arrays.asList(1, 2, 3, 4);

        List<String> viaParallelStream = ids.parallelStream()
                .map(BlockingIoCommonPoolDemo::simulatedIo)
                .collect(Collectors.toList());

        ExecutorService ioExecutor = Executors.newFixedThreadPool(4);
        List<String> viaDedicatedPool;
        try {
            List<CompletableFuture<String>> futures = ids.stream()
                    .map(id -> CompletableFuture.supplyAsync(
                            () -> simulatedIo(id), ioExecutor))
                    .collect(Collectors.toList());

            viaDedicatedPool = futures.stream()
                    .map(CompletableFuture::join)
                    .collect(Collectors.toList());
        } finally {
            ioExecutor.shutdown();
        }

        int cpuSum = IntStream.rangeClosed(1, 4)
                .parallel()
                .map(n -> n * n)
                .sum();

        System.out.println("parallel stream: " + viaParallelStream);
        System.out.println("dedicated I/O: " + viaDedicatedPool);
        System.out.println("CPU sum: " + cpuSum);
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac BlockingIoCommonPoolDemo.java
java BlockingIoCommonPoolDemo
~~~

Stdout đã kiểm chứng:

~~~text
parallel stream: [item-1, item-2, item-3, item-4]
dedicated I/O: [item-1, item-2, item-3, item-4]
CPU sum: 30
~~~

Mẫu sử dụng API đã có từ Java 8; mã không dùng tính năng preview.

## 7. Phân tích ví dụ: cùng kết quả, khác cách quản lý worker

### 7.1. Parallel Stream chứa thao tác chặn

~~~java
List<String> viaParallelStream = ids.parallelStream()
        .map(BlockingIoCommonPoolDemo::simulatedIo)
        .collect(Collectors.toList());
~~~

Mỗi mapper đợi 40 ms. Trong cách thực thi dùng common pool, worker thực hiện mapper có thể bị giữ trong lúc chờ. Kết quả vẫn đúng: nguồn List có encounter order và **Collectors.toList()** giữ thứ tự phần tử. Nhưng **thứ tự hoàn tất của các mapper không nhất thiết bằng thứ tự input**.

### 7.2. Tách tác vụ chờ sang ExecutorService riêng

~~~java
ExecutorService ioExecutor = Executors.newFixedThreadPool(4);

List<CompletableFuture<String>> futures = ids.stream()
        .map(id -> CompletableFuture.supplyAsync(
                () -> simulatedIo(id), ioExecutor))
        .collect(Collectors.toList());
~~~

**ids.stream()** chỉ gửi việc theo thứ tự, còn executor riêng quyết định việc nào chạy đồng thời. **Không cần parallelStream() để gửi task vào executor đã hỗ trợ concurrency.**

~~~java
List<String> results = futures.stream()
        .map(CompletableFuture::join)
        .collect(Collectors.toList());
~~~

**join()** trong ví dụ gọi từ main thread; main chờ tương ứng từng future rồi lắp lại kết quả đúng thứ tự input. Các task hoàn thành theo thứ tự nào không ảnh hưởng List kết quả. **shutdown()** đóng quyền nhận tác vụ mới của executor sau khi các Future đã được join ở đường chạy thành công.

Điểm quan trọng là **kiểm soát được pool phục vụ I/O**, không phải chỉ thay đổi cú pháp Stream. Trong hệ thống thật cần timeout, cancellation, xử lý lỗi và vòng đời executor theo phạm vi ứng dụng.

**Giới hạn:** **Executors.newFixedThreadPool(4)** giới hạn số worker, nhưng mặc định hàng đợi có thể tăng rất lớn. Không nên submit hàng trăm nghìn I/O vào một executor rồi giữ toàn bộ futures không giới hạn. Áp dụng bounded queue, batching hoặc backpressure theo tài nguyên đích.

## 8. CompletableFuture mặc định có thể tiếp tục dùng common pool

~~~java
// Dạng không chỉ định Executor:
CompletableFuture<String> first =
        CompletableFuture.supplyAsync(() -> simulatedIo(1));

// Dạng chỉ định rõ Executor:
CompletableFuture<String> second =
        CompletableFuture.supplyAsync(
                () -> simulatedIo(1), ioExecutor);
~~~

Đây là đoạn **minh họa**, đặt bên trong class có hàm simulatedIo và biến ioExecutor đang hoạt động.

Các phương thức async của CompletableFuture không nhận Executor **thường chạy trên ForkJoinPool.commonPool()**; tài liệu API có ngoại lệ với một số cấu hình parallelism thấp. Vì vậy không coi đây là quy tắc tuyệt đối trong mọi môi trường. Nếu gọi **supplyAsync** để bọc I/O sync mà không truyền Executor, bạn có thể vẫn dùng tài nguyên chung với Parallel Stream.

**Không tạo một pool mới cho mỗi phần tử hay mỗi HTTP request.** Pool riêng cần thuộc vòng đời một component, có giới hạn và đóng đúng thời điểm.

## 9. Chọn công cụ theo loại công việc

| Nhu cầu | Gợi ý | Điều cần xác minh |
| --- | --- | --- |
| Tính toán CPU độc lập, lượng việc đủ lớn | Parallel Stream | Tính kết hợp của reduction, benchmark |
| Một số lời gọi I/O đơn giản, không cần đồng thời | Stream tuần tự hoặc vòng lặp | Tính dễ hiểu, timeout |
| Nhiều I/O chặn, giới hạn platform threads | ExecutorService riêng + Future/CompletableFuture | Kích thước queue, lỗi, resource lifecycle |
| HTTP client hỗ trợ non-blocking API | HttpClient.sendAsync | Giới hạn request và callback |
| Nhiều tác vụ chờ I/O trên Java 21+ | Virtual threads | Khả năng mở rộng, connection limit, quota |
| Fork/join có bước chặn chủ động quản lý | ManagedBlocker | Hợp đồng block/isReleasable |

Một Parallel Stream có I/O chặn không tự động sai; vấn đề chính là liệu nó dùng tài nguyên chung không kiểm soát và có đạt throughput/latency cần thiết dưới tải thực tế không.

## 10. I/O bất đồng bộ: HttpClient.sendAsync từ Java 11

**HttpClient.sendAsync(...)** trả **CompletableFuture<HttpResponse<T>>**, để thread gọi không phải đợi nguyên thời gian phản hồi.

Ví dụ minh họa (biến **uri** là một URI hợp lệ có sẵn, cần import **java.net.http**, **java.time.Duration**):

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

CompletableFuture<String> body = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body);
~~~

Đây **không phải chương trình độc lập**. Trong ứng dụng thật phải kiểm tra endpoint, lỗi, timeout và giới hạn request. Không giả định **thenApply** luôn được chạy trên một thread riêng; executor/continuation phụ thuộc hợp đồng và cách gọi.

**CompletableFuture.allOf** có thể phối hợp nhiều future. Dùng **join/get** để đợi kết quả có thể vẫn chặn thread gọi. Không tạo phụ thuộc mà tất cả worker trên một pool đều đợi một task chưa được thực thi cũng bởi pool đó.

**orTimeout(...)** (Java 9+) có thể hoàn tất future bằng lỗi timeout; điều này **không mặc nhiên bảo đảm** lời gọi I/O nền đã được hủy. Timeout mạng và cancellation phải được cấu hình/kiểm tra ở API I/O thật.

## 11. Virtual threads Java 21+: cách tổ chức I/O chặn hiện đại

**Virtual threads** là tính năng chính thức từ Java 21. Chúng là những thread nhẹ được JVM sắp lịch trên carrier threads (platform threads). Khi virtual thread thực hiện blocking operation được hỗ trợ, JVM thường có thể tạm dừng virtual thread và trả carrier cho công việc khác.

Virtual threads hữu ích với nhiều tác vụ **chủ yếu chờ I/O**. Chúng giúp tăng khả năng mở rộng/throughput mà không giữ một platform thread cho mỗi request đang đợi. **Chúng không làm một HTTP/SQL call đơn lẻ tự nhanh hơn.**

Các nguyên tắc còn áp dụng:

- Một virtual thread cho mỗi task, **không tạo fixed pool để tái sử dụng virtual threads** như platform threads.
- Vẫn giới hạn kết nối DB, API quota, bộ nhớ, timeout và tác vụ in-flight.
- Chúng không tự biến Parallel Stream thành một cơ chế I/O riêng.
- Một số native/foreign blocking call có thể giữ carrier; quan sát theo JVM/thư viện được sử dụng.

### Mã Java 21+ chạy được

Tạo tệp **VirtualIoDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualIoDemo {
    static String simulatedIo(int id) throws InterruptedException {
        Thread.sleep(30);
        return "item-" + id;
    }

    public static void main(String[] args) throws Exception {
        List<Integer> ids = List.of(1, 2, 3);
        List<String> results = new ArrayList<>();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();
            for (int id : ids) {
                futures.add(executor.submit(() -> simulatedIo(id)));
            }

            for (Future<String> future : futures) {
                results.add(future.get());
            }
        }

        System.out.println("virtual I/O: " + results);
    }
}
~~~

Biên dịch và chạy trên JDK 21 trở lên:

~~~bash
javac VirtualIoDemo.java
java VirtualIoDemo
~~~

Stdout:

~~~text
virtual I/O: [item-1, item-2, item-3]
~~~

Một virtual thread được tạo cho mỗi task. **Future.get()** ở main lấy kết quả theo thứ tự futures, dù thứ tự hoàn thành thực tế có thể khác. **try-with-resources** đóng executor theo hợp đồng hiện hành. Đây là mô phỏng wait bằng sleep, không chứng minh tốc độ mạng hay DB.

## 12. Concurrency, quota, queue và backpressure

Giới hạn số worker **không đồng nghĩa** giới hạn số request an toàn. Một DB có thể chỉ cho phép một số kết nối, hoặc API có rate limit. Cần chú ý:

1. Số connection của JDBC/HTTP client và thời gian chờ lấy connection.
2. Quota/rate limit và số request đang bay (in-flight).
3. Kích thước hàng đợi; pool platform threads cố định vẫn có thể xếp hàng quá nhiều việc.
4. Timeout, retry/backoff, cancellation và chính sách khi phụ thuộc bị lỗi.
5. Bộ nhớ cho request/response/future, khi một đợt lớn chưa hoàn tất.
6. Vòng đời executor và cơ chế đóng ứng dụng.

**ThreadPoolExecutor** có thể dùng hàng đợi hữu hạn và rejection policy theo nhu cầu. Với virtual threads, dùng giới hạn resource như connection pool hoặc **Semaphore** khi chưa có giới hạn tương ứng; nhớ release trong finally và xử lý interruption. Không cần cố giới hạn virtual threads theo kiểu fixed platform thread pool.

## 13. Timeout và xử lý lỗi khi đang chờ

Khi gọi I/O chặn cần quy định timeout ở tầng HTTP/DB/socket. **Future.join()** có thể ném **CompletionException** khi task lỗi; không giả định tất cả thành công. **Future.cancel()** hoặc timeout ở future không chắc hủy được mọi I/O nền.

Đoạn trong chương trình chạy được xử lý interrupt như sau:

~~~java
static String simulatedIo(int id) {
    try {
        Thread.sleep(40);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted while waiting", ex);
    }
    return "item-" + id;
}
~~~

Khi bắt InterruptedException, phương thức khôi phục interrupted flag rồi chuyển lỗi. Đây là ví dụ về cách không nuốt interruption; chính sách lỗi của ứng dụng phải rõ ràng. Không dùng **Thread.sleep** trong production chỉ để mong điều tiết tốc độ: hãy thiết kế limiter/backpressure.

## 14. Sai lầm phổ biến

- **Giả định parallel() mở một thread cho mỗi phần tử:** Stream chỉ chọn chế độ xử lý song song; số worker và lịch chạy không được hứa trước.
- **Bọc I/O sync bằng supplyAsync mà không truyền Executor:** có thể vẫn tranh common pool.
- **Chờ Future ngay trong các worker mà kết quả Future phụ thuộc cùng pool:** có thể làm tăng độ trễ hoặc thiếu tiến triển.
- **Chỉnh java.util.concurrent.ForkJoinPool.common.parallelism như cách chữa chung:** thay đổi phạm vi JVM, ảnh hưởng các thành phần khác và không loại bỏ bản chất I/O chặn.
- **Dựa vào việc chạy Parallel Stream trong một ForkJoinPool tùy chỉnh để coi đã chọn được pool theo hợp đồng:** Stream.parallel() không cung cấp Executor parameter; chọn API có overload Executor nếu cần kiểm soát rõ ràng.
- **Gọi shutdown() hoặc shutdownNow() để tắt commonPool:** theo API, những lời gọi đó không làm common pool dừng; chỉ đóng executor do mình sở hữu.
- **Ghi biến mutable dùng chung từ map/forEach:** nguy cơ race; lambda nên stateless và non-interfering.
- **Tin thứ tự log của lambda là thứ tự dữ liệu:** execution order có thể khác encounter order; List kết quả từ ordered Stream với collector phù hợp vẫn có thể giữ thứ tự.
- **Tin virtual threads xóa bỏ connection/rate limits:** không; chúng chủ yếu giảm chi phí chờ platform threads.

## 15. Quan sát và kiểm chứng dưới tải thực

CPU thấp không có nghĩa hệ thống không bị nghẽn I/O. Nên quan sát:

| Tín hiệu | Cách sử dụng |
| --- | --- |
| Latency p95/p99 | Kiểm tra độ trễ phần đuôi khi dependency chậm |
| Throughput và queue depth | Xem công việc có bị dồn không |
| HTTP/JDBC latency, connection saturation | Tìm điểm nghẽn dịch vụ ngoài |
| Thread dump/stack trace | Xác định worker đang chặn tại API nào |
| Active/queued commonPool estimates | Quan sát sức tải pool và hàng đợi |
| Số future còn chờ, memory/GC | Phát hiện tạo quá nhiều công việc cùng lúc |

Có thể đọc số liệu tức thời qua API:

~~~java
ForkJoinPool pool = ForkJoinPool.commonPool();

int parallelism = pool.getParallelism();
int active = pool.getActiveThreadCount();
int queued = pool.getQueuedSubmissionCount();
~~~

Đây là **đoạn minh họa** cần import java.util.concurrent.ForkJoinPool, đặt trong method/class. Các con số mang tính tức thời/ước lượng, không có stdout cố định.

Dùng Java Flight Recorder (JFR), thread dump, tracing, profiler và metric của client để tìm vị trí chờ. Hãy benchmark cùng dữ liệu, timeout và dịch vụ test với những phương án sequential, parallelStream, executor riêng, API async, virtual threads (nếu có JDK 21+). Đo error rate, throughput, p95/p99 và kiểm tra tính đúng. **Một lần chạy bốn phần tử không đủ để quyết định tối ưu production.**

## 16. Luyện tập và giải đáp

**Câu 1.** Vì sao Parallel Stream đọc HTTP đồng bộ có thể làm tác vụ CPU khác chậm?

**Đáp án:** Một số worker có thể đợi HTTP. Nếu worker đó thuộc common pool, tác vụ khác dùng chung pool có thể phải chờ. ForkJoinPool không bảo đảm bù worker cho unmanaged blocking I/O.

**Câu 2.** Chỉ đổi sang CompletableFuture.supplyAsync mà không chỉ định Executor đã cách ly I/O chưa?

**Đáp án:** Chưa chắc; async mặc định thường dùng common pool. Nếu cần cách ly, chọn overload truyền executor riêng hoặc mô hình async/virtual threads phù hợp.

**Câu 3.** Fixed thread pool có 4 worker đã giới hạn mọi công việc đang chờ về tối đa 4 chưa?

**Đáp án:** Chưa. Số worker đang chạy là bốn, nhưng hàng đợi có thể tăng lớn. Cần bounded queue, batching hoặc backpressure.

**Câu 4.** Có 12 việc chờ 200 ms, mỗi đợt tối đa 4 việc, trong mô hình lý tưởng mất bao lâu?

**Đáp án:** Ba đợt, **600 ms**, bỏ qua overhead. Đây không phải dự đoán runtime thực.

**Câu 5.** Virtual threads có tăng tốc một lần truy vấn SQL không?

**Đáp án:** Không tự động. Chúng cho phép phục vụ nhiều tác vụ chủ yếu chờ I/O mà không giữ một platform thread riêng cho mỗi task; SQL và DB connection vẫn có giới hạn.

**Câu 6.** Timeout của CompletableFuture có chắc hủy socket operation không?

**Đáp án:** Không. Phải thiết kế timeout và cancellation theo hợp đồng HTTP/JDBC/socket thực tế.

## 17. Ghi nhớ

1. **Parallel Stream hợp với CPU-bound độc lập** khi có đủ việc và đã benchmark.
2. **I/O chặn có thể giữ worker của common pool**, gây nhiễu tới công việc khác dùng chung tài nguyên.
3. **ForkJoinPool không bảo đảm tự bù worker cho unmanaged blocking I/O**; ManagedBlocker là cơ chế chuyên sâu.
4. **CompletableFuture async mặc định thường dùng common pool**; truyền executor nếu cần tách workload chờ.
5. **HttpClient.sendAsync Java 11+** và **virtual threads Java 21+** là các cách tiếp cận hiện hành tùy nhu cầu.
6. **Virtual threads giúp mở rộng workload chờ**, không thay thế connection limits, quota, timeout và backpressure.
7. Đánh giá bằng tính đúng, throughput, latency p95/p99 và tài nguyên thực; không suy ra hiệu suất chỉ từ demo.

### Tài liệu Java chính thức còn áp dụng

- ForkJoinPool: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- CompletableFuture: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Stream package: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- ExecutorService: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- HttpClient: https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html
- Virtual Threads: https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html
