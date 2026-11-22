# Vì sao blocking I/O có thể làm nghẽn parallel stream?

**Câu trả lời:** `parallelStream()` giúp chia công việc thành các phần có thể thực thi đồng thời, đặc biệt hữu ích khi mỗi phần **tính toán trên CPU**. Trong cách thực thi phổ biến của JDK, các công việc của parallel stream được tổ chức bằng `ForkJoinPool` và thường dùng `ForkJoinPool.commonPool()`. Khi mã `map()`, `filter()`, `forEach()` hoặc một bước xử lý khác gọi **blocking I/O** (chờ HTTP, socket, tệp, cơ sở dữ liệu...), worker có thể phải **đứng chờ** thay vì xử lý phần dữ liệu tiếp theo. Nếu nhiều worker đồng thời chờ, việc phân chia song song không còn giúp xử lý công việc hiệu quả: các phần tử chưa được xử lý phải xếp hàng, thời gian hoàn thành tăng và các tác vụ khác chia sẻ pool cũng có thể bị ảnh hưởng.

Bài này chỉ nói về **Java concurrency và Java Stream API**, không bàn về cơ chế cấu hình riêng của Spring.

## 1. Nền tảng: parallel stream được chạy như thế nào?

Một stream tuần tự thường áp dụng pipeline theo một luồng thực thi:

```java
List<String> result = ids.stream()
        .map(this::calculate)
        .toList();
```

Khi dùng `parallelStream()` (hoặc `stream().parallel()`), Stream API có thể phân chia nguồn dữ liệu thành các phần và thực thi các tác vụ qua cơ chế fork/join:

```text
Danh sách đầu vào: [1, 2, 3, 4, 5, 6, 7, 8]
                    |
                  split
            /                 \
       [1,2,3,4]           [5,6,7,8]
         /   \               /    \
      [1,2] [3,4]         [5,6] [7,8]
         \   /               \    /
             kết hợp kết quả
                    |
          [result-1, ..., result-8]
```

`ForkJoinPool` dùng các worker (platform threads) và cơ chế *work stealing* để giảm thời gian worker rảnh khi còn phần việc phù hợp để xử lý. Với tác vụ CPU-bound ngắn và có thể tách/ghép, đây thường là lựa chọn hợp lý.

**Phân biệt quan trọng:**

- `parallelStream()` là một **cách thực thi pipeline** của Stream API, không phải giao diện tạo một nhóm request bất đồng bộ.
- Một pipeline có thể chạy trên các worker `ForkJoinPool.commonPool()` **và có thể dùng cả thread gọi**. Không được khẳng định mọi phần tử nhất thiết chạy trên common-pool worker.
- Mức song song thông dụng của common pool liên quan tới số bộ xử lý được JVM nhận biết và cấu hình runtime; nó không phải "mỗi phần tử một thread".
- Một stream không mặc nhiên tạo thread riêng cho mỗi thao tác I/O hay tự động mở rộng pool theo số request đang đợi.
- Tốc độ còn phụ thuộc cách chia nguồn (`Spliterator`), chi phí mỗi phần tử, thứ tự kết quả, việc đồng bộ và tác vụ khác đang dùng chung pool.

## 2. Vì sao blocking I/O làm nghẽn?

Blocking I/O là khi một lời gọi **chưa thể trả kết quả** và luồng đang thực thi phải chờ, chẳng hạn:

- Đợi socket nhận dữ liệu hoặc phản hồi từ một HTTP service.
- Chờ truy vấn database hoàn thành hoặc chờ lấy connection từ pool.
- Chờ đọc/ghi tệp, hoặc chờ một khóa/tài nguyên dùng chung.
- `Thread.sleep()` dùng để mô phỏng thời gian chờ trong ví dụ; bản thân nó **không phải I/O thật**.

Ví dụ:

```java
List<Response> responses = urls.parallelStream()
        .map(url -> blockingHttpCall(url))
        .toList();
```

Đây là **mã minh họa**, cần định nghĩa `Response` và `blockingHttpCall` trong chương trình. Phần `map` không còn là phép biến đổi CPU thuần túy: mỗi lần gọi có thể treo một worker cho đến khi có phản hồi.

Giả sử có 4 đơn vị thực thi cùng xử lý, 12 request, mỗi request mất khoảng 1 giây để **chờ mạng**:

```text
Thời gian       Worker-1      Worker-2      Worker-3      Worker-4
0–1 giây        request 1     request 2     request 3     request 4
                [chờ I/O]     [chờ I/O]     [chờ I/O]     [chờ I/O]
1–2 giây        request 5     request 6     request 7     request 8
                [chờ I/O]     [chờ I/O]     [chờ I/O]     [chờ I/O]
2–3 giây        request 9     request 10    request 11    request 12
                [chờ I/O]     [chờ I/O]     [chờ I/O]     [chờ I/O]
```

Đây là **mô hình trực quan giả định** có 4 worker hữu dụng và không có cơ chế bù worker; **không phải lịch chạy được Java bảo đảm**. Khi cả bốn worker chờ, CPU có thể đang rảnh nhưng những việc còn lại vẫn đợi lượt. Để có thông lượng cao hơn khi phần lớn thời gian là chờ I/O, cần cơ chế cho phép nhiều request cùng chờ hơn và vẫn kiểm soát giới hạn tài nguyên thực.

Điểm gây nghẽn là **số worker có thể tiếp tục xử lý tác vụ** chứ không phải thiếu CPU tính toán. Ngoài ra, khi một stream chiếm các worker của common pool bằng những thao tác blocking kéo dài, công việc khác dùng common pool cũng có nguy cơ bị đói worker (*thread starvation*).

### Một phép ước lượng để hiểu hiện tượng

Trong trường hợp đơn giản có `P` lượt gọi I/O đồng thời, mỗi lượt mất trung bình `L` giây và tài nguyên phía ngoài không có giới hạn khác, thông lượng xấp xỉ tối đa `P / L` lượt/giây khi tải đủ lớn. Đây chỉ là mô hình định tính: thực tế còn có độ trễ biến động, thời gian CPU, scheduling, mạng, giới hạn connection và chính sách thực thi của pool. Không nên dùng công thức này để suy ra chính xác số request/giây của một parallel stream cụ thể.

## 3. Vì sao ForkJoinPool không tự xử lý hết chuyện blocking?

`ForkJoinPool` được thiết kế để tận dụng tốt công việc có thể chia nhỏ và kết hợp. Khi worker đợi **một tác vụ fork/join khác** hoàn thành bằng các cơ chế mà pool hiểu được, nó có thể hỗ trợ thực thi phần việc khác thay vì chỉ đứng yên.

Tuy nhiên, **chờ I/O không được quản lý** khác với chờ fork/join. Tài liệu API `ForkJoinPool` lưu ý rằng pool **không bảo đảm điều chỉnh số worker để bù lại** khi có blocked I/O hoặc đồng bộ hóa không được quản lý. Một số kiểu chờ có thể được hỗ trợ bằng `ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)`; nhưng không có nghĩa mọi lời gọi HTTP/JDBC/socket hoặc `Thread.sleep()` trong `map()` đều tự động khiến pool tạo worker thay thế.

Bởi vậy, hai khẳng định sau đều sai nếu nói tuyệt đối:

- "Common pool luôn cố định chính xác P threads, không thể có thêm thread nào."
- "Common pool luôn tự mở đủ thread bù cho mọi thao tác blocking."

**Kết luận thực tế:** Việc điều chỉnh worker phụ thuộc loại blocking, runtime và đường gọi cụ thể. Không thiết kế một I/O pipeline cần độ đồng thời cao dựa vào giả định ForkJoinPool chắc chắn sẽ bù worker.

### Những hiệu ứng cộng hưởng

1. **Cùng dùng common pool:** Stream A làm blocking I/O có thể làm trễ Stream B hoặc các `CompletableFuture.supplyAsync(...)` sử dụng common pool mặc định.
2. **Đồng bộ trong pipeline:** Khóa chung, ghi vào một cấu trúc không an toàn hay đợi tài nguyên chật có thể khiến nhiều tác vụ nối đuôi nhau dù stream ở chế độ parallel.
3. **Yêu cầu thứ tự:** `forEachOrdered` phải tôn trọng encounter order và có thể làm một số bước cần phối hợp/tuần tự hóa. `toList()` giữ encounter order cho nguồn có thứ tự nhưng không buộc mọi phần tử tính toán tuần tự.
4. **I/O bên ngoài chậm:** Connection pool 10 kết nối hoặc dịch vụ chỉ chịu 20 request đồng thời là nút thắt riêng; tăng số thread không giúp vượt giới hạn này và có thể làm hệ thống xấu đi.
5. **Lỗi và thời gian chờ:** Request không có timeout hợp lý có thể giữ worker lâu; nếu dùng queue, số việc đang đợi tiếp tục tăng.

## 4. Ví dụ Java 17+ độc lập: cùng dữ liệu, hai cách điều phối

Chương trình sau tạo tám tác vụ độc lập. Hàm `simulatedBlockingCall()` dùng `Thread.sleep(80)` **để mô phỏng** một thao tác chờ. Chạy lần đầu bằng `parallelStream()`; lần sau dùng một executor **riêng cho I/O** với bốn platform threads. Kết quả dữ liệu giống nhau, nhưng nơi thực thi và chính sách giới hạn tác vụ khác nhau.

**Tệp: `BlockingIoParallelStreamDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

public class BlockingIoParallelStreamDemo {

    private static String simulatedBlockingCall(int id) {
        try {
            Thread.sleep(80); // Chỉ giả lập thời gian chờ I/O.
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at id=" + id, e);
        }
        return "item-" + id;
    }

    public static void main(String[] args) throws Exception {
        List<Integer> ids = IntStream.rangeClosed(1, 8).boxed().toList();

        // Cách 1: blocking trong parallel stream.
        List<String> fromParallelStream = ids.parallelStream()
                .map(BlockingIoParallelStreamDemo::simulatedBlockingCall)
                .toList();
        System.out.println("parallel=" + fromParallelStream);

        // Cách 2: tách công việc blocking sang executor chuyên dụng.
        ExecutorService ioExecutor = Executors.newFixedThreadPool(4);
        try {
            List<Callable<String>> tasks = ids.stream()
                    .<Callable<String>>map(id ->
                            () -> simulatedBlockingCall(id))
                    .toList();

            List<Future<String>> futures = ioExecutor.invokeAll(tasks);
            List<String> fromExecutor = new ArrayList<>();
            for (Future<String> future : futures) {
                fromExecutor.add(future.get());
            }
            System.out.println("ioExecutor=" + fromExecutor);
        } finally {
            ioExecutor.shutdown();
        }
    }
}
```

**Biên dịch và chạy bằng Java 17+:**

```bash
javac BlockingIoParallelStreamDemo.java
java BlockingIoParallelStreamDemo
```

**Kết quả xác định (không in thread name hoặc thời gian):**

```text
parallel=[item-1, item-2, item-3, item-4, item-5, item-6, item-7, item-8]
ioExecutor=[item-1, item-2, item-3, item-4, item-5, item-6, item-7, item-8]
```

Giải thích:

- `parallelStream()` yêu cầu pipeline thực thi song song, nhưng không quy định số worker cố định; `sleep(80)` khiến thread đang chạy phần tử chờ. Đây là mô hình đơn giản cho *blocking*, không đo năng lực socket/JDBC thực tế.
- `newFixedThreadPool(4)` tách công việc blocking khỏi common pool và cho **tối đa bốn task của executor này chạy đồng thời**. Con số 4 chỉ để minh họa, không phải cấu hình tối ưu.
- `invokeAll()` chờ các task hoàn tất và trả `Future` theo thứ tự danh sách task. `Future.get()` có thể ném `ExecutionException` nếu task lỗi; đoạn `main throws Exception` để ví dụ gọn.
- `List.toList()` giữ thứ tự gặp của stream có thứ tự như danh sách `ids`; do đó thứ tự **in kết quả** không phản ánh thứ tự các thread chạy.
- `shutdown()` thông báo executor không nhận thêm task. Nếu cần dừng theo timeout/cancel, ứng dụng phải xử lý thêm và có thể dùng `awaitTermination` / `shutdownNow` đúng hợp đồng.
- `Executors.newFixedThreadPool()` dùng hàng đợi task **không giới hạn độ dài theo cấu hình mặc định**. Nó tránh chiếm common pool nhưng **không tự giải quyết backpressure** khi tốc độ submit cao: sản xuất cần một hàng đợi giới hạn hoặc cách kiểm soát đầu vào riêng.

**Đừng kết luận từ ví dụ rằng executor riêng luôn nhanh hơn.** Với chỉ tám task, parallel stream có thể bằng hoặc nhanh hơn tùy máy và số worker; mục tiêu là thấy **phạm vi tài nguyên và quyền điều khiển**. Chỉ benchmark trên tải, mạng và giới hạn thực mới trả lời được thông lượng/độ trễ.

## 5. Chẩn đoán hiện tượng nghẽn khi chạy thật

Một parallel stream bị ảnh hưởng bởi blocking I/O có thể có các dấu hiệu:

- **CPU thấp nhưng throughput thấp:** nhiều worker ở trạng thái chờ I/O, latency tăng; CPU chưa được sử dụng tương xứng.
- **Hàng đợi hoặc số tác vụ chờ tăng:** công việc đến nhanh hơn tốc độ I/O trả về.
- **p95/p99 tăng mạnh:** một phần request chậm có thể kéo dài thời gian hoàn tất của pipeline tổng hợp, nhất là khi chờ toàn bộ kết quả.
- **Các tác vụ chia sẻ common pool chậm theo:** mặc dù bản thân chúng không dùng cùng dịch vụ bên ngoài.
- **Thread dump cho thấy chờ:** stack có thể nằm ở socket read, await, lock, blocking client hoặc `Thread.sleep`; cần phân biệt chờ mạng và chờ connection pool.

Cần kiểm tra bằng **JFR, thread dump, profiler**, metrics của remote service và connection pool. `ForkJoinPool.commonPool().getActiveThreadCount()`, `getQueuedTaskCount()` hay `getPoolSize()` có thể hỗ trợ quan sát nhưng là các số đo gần đúng/tức thời; chúng không phản ánh hết thread của caller, tài nguyên ngoài hay hàng đợi ứng dụng.

### Thử nghiệm giới hạn song song của common pool

Có thể chạy ví dụ trên với tham số JVM sau để **quan sát khác biệt trên một môi trường cụ thể**:

```bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=2 BlockingIoParallelStreamDemo
```

Property được đặt **khi khởi động JVM**, trước khi common pool được khởi tạo. Giá trị này điều chỉnh target parallelism của common pool; **không phải cam kết về số thread đang chạy mọi lúc**, cũng không bao gồm một cách đơn giản mọi lời gọi có thể chạy trên caller thread. Không lấy số đo duy nhất hoặc ví dụ `sleep` làm benchmark kết luận.

## 6. Lựa chọn phù hợp cho I/O-bound workload

### Lựa chọn A: ExecutorService riêng cho blocking I/O

Với Java 17, một `ExecutorService` riêng có thể là giải pháp dễ triển khai khi bắt buộc dùng thư viện blocking:

1. Xác định phạm vi công việc I/O cần giới hạn, không dùng `parallelStream()` để kích hoạt lời gọi blocking.
2. Gửi task tới executor được quản lý rõ vòng đời.
3. Cấu hình số worker theo khả năng của remote service, connection pool, CPU, memory và thử nghiệm tải.
4. Thêm **queue hữu hạn, cơ chế từ chối/đợi hợp lý và timeout**, thay vì chỉ thay common pool bằng một `newFixedThreadPool` với queue mặc định vô hạn.
5. Thu hồi `Future`, xử lý lỗi và hủy/chờ theo timeout để tránh giữ task quá hạn.

Ví dụ `Executors.newFixedThreadPool(4)` ở trên là minh họa ngắn; khi sản xuất cần **bounded queue và admission control** có thể dùng `ThreadPoolExecutor` với `BlockingQueue` hữu hạn và `RejectedExecutionHandler` phù hợp. Không nên tăng worker đến vô hạn để che dịch vụ đích chậm.

### Lựa chọn B: Virtual threads cho blocking I/O (Java 21+)

Khi mỗi task chủ yếu chờ blocking I/O theo API mà JVM hỗ trợ, Java 21+ cho phép tạo **một virtual thread cho mỗi task**:

```java
// Đoạn minh họa Java 21+, giả định ids và blockingCall đã được định nghĩa.
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    var futures = ids.stream()
            .map(id -> executor.submit(() -> blockingCall(id)))
            .toList();

    for (var future : futures) {
        System.out.println(future.get());
    }
}
```

Đây là **snippet minh họa**, không phải chương trình độc lập; nó dùng API Java 21+ và phải cung cấp `ids`, `blockingCall` cùng việc xử lý exception. Khi virtual thread chờ I/O được JDK hỗ trợ, carrier platform thread có thể được giải phóng để chạy việc khác. So với chiếm một số nhỏ worker của parallel stream, cách này phù hợp hơn cho nhiều công việc chủ yếu chờ.

**Nhưng virtual threads không làm dịch vụ bên ngoài nhanh hơn**. Dùng `Semaphore`/connection pool để giới hạn số thao tác tới tài nguyên đích, thêm backpressure để giới hạn tổng số task đã nhận. Đừng pool virtual threads chỉ để giữ một lượng virtual threads cố định; executor kiểu `newVirtualThreadPerTaskExecutor()` tạo virtual thread **theo từng task**, không tái sử dụng chúng như worker của fixed pool.

### Lựa chọn C: API bất đồng bộ / non-blocking khi hệ thống hỗ trợ

Dùng I/O async thực sự (ví dụ một số API Java networking hỗ trợ bất đồng bộ) để request đang chờ **không chiếm worker platform thread như blocking call**. Khi kết hợp `CompletableFuture`:

- `CompletableFuture.supplyAsync(task)` **không truyền executor** thường vẫn dùng common pool; nếu `task` là blocking I/O, nó có thể tiếp tục gây tranh chấp common pool.
- `supplyAsync(task, dedicatedExecutor)` đưa **blocking task** sang executor chỉ định, nhưng bản thân lời gọi blocking vẫn chiếm worker của executor đó.
- Một API I/O **thực sự bất đồng bộ** trả một future khi khởi động I/O có thể khác về cách sử dụng thread; cần xem contract API cụ thể thay vì suy ra chỉ từ kiểu trả về `CompletableFuture`.

Không cần chuyển mọi code sang non-blocking nếu API synchronous + virtual threads đáp ứng tốt độ trễ và throughput. Hãy chọn theo mục tiêu vận hành và hệ sinh thái Java đang dùng.

## 7. Có nên dùng ForkJoinPool.ManagedBlocker?

`ForkJoinPool.managedBlock(...)` cho phép code **khai báo một thao tác có thể block** cho ForkJoinPool, từ đó pool *có thể* bố trí worker bù phù hợp khi blocked. Đây là API nâng cao hữu ích khi trực tiếp xây tác vụ fork/join và quản lý việc chờ.

Tuy nhiên:

- `ManagedBlocker` cần cài đặt đúng hai phương thức `isReleasable()` và `block()` theo hợp đồng; không thể chỉ đặt một lời gọi I/O bất kỳ trong `map()` rồi mặc định có cơ chế bù.
- Cơ chế bù **không biến remote service thành vô hạn** và không bảo đảm toàn bộ bottleneck biến mất.
- Hỗ trợ kiểu blocking này có thể phù hợp với một thư viện cụ thể, nhưng thường khó hơn việc **tách I/O sang executor chuyên dụng** hoặc dùng virtual threads/async I/O cho ứng dụng.
- Không khuyến khích viết một `ManagedBlocker` tùy tiện cho mọi HTTP call chỉ để tiếp tục ép blocking I/O vào parallel stream.

## 8. Một số nhận định sai thường gặp

| Nhận định | Thực tế |
| --- | --- |
| "Gọi `parallelStream()` là mọi I/O đều chạy nhanh hơn." | Chỉ có thể tăng số việc thực hiện đồng thời trong phạm vi pool; chờ I/O vẫn tiêu tốn worker platform thread. |
| "ForkJoinPool luôn bù đủ worker cho blocking I/O." | Không có bảo đảm với blocked I/O hoặc synchronization không được quản lý. |
| "Tất cả việc đều chạy trên common-pool worker." | Thread gọi cũng có thể tham gia; execution detail không được cố định theo số phần tử. |
| "Dùng `CompletableFuture.supplyAsync` mặc định là đã tránh common pool." | Mặc định vẫn có thể dùng common pool; phải xét executor và API I/O thực sự. |
| "Đổi sang pool 1000 threads là hết nghẽn." | Thường chỉ dời bottleneck sang database, network, RAM, connection hoặc queue. |
| "CPU thấp chứng minh ứng dụng khỏe." | CPU thấp cùng nhiều worker chờ có thể là dấu hiệu nghẽn I/O/starvation. |
| "Chọn `parallel()` cho mọi map/filter." | Với việc nhỏ, ngắn, có side effect hoặc có yêu cầu thứ tự, overhead và contention có thể làm chậm hơn tuần tự. |
| "Virtual threads cho tốc độ mỗi request nhanh hơn." | Virtual threads chủ yếu cải thiện khả năng mở rộng số tác vụ đồng thời chờ, không giảm latency của một lời gọi mạng. |

## 9. Cách lựa chọn trong thực tế

- **Phần CPU-bound, độc lập, đủ lớn:** `parallelStream()` có thể tốt. Đo trên dữ liệu thật; để ý thứ tự, shared mutable state và overhead split/merge.
- **Nhiều blocking I/O:** Tách sang một cơ chế concurrency dành cho I/O với giới hạn tài nguyên rõ: executor chuyên dụng, virtual thread per task (Java 21+) hoặc API async thật sự.
- **Vừa CPU vừa I/O:** Phân chia giai đoạn. Không đặt trực tiếp remote call chậm trong một phép `map()` CPU vốn dự kiến chạy trên common pool.
- **Tài nguyên ngoài có quota:** Dù dùng cách nào vẫn cần giới hạn số request/connection thực, timeout, retry có kiểm soát và backpressure.
- **Cần đo hiệu năng:** Quan sát throughput, latency theo phần vị, thời gian chờ I/O, queue depth, pool/connection metrics, CPU và thread dump; đo với warm-up và môi trường tải đại diện.

**Ghi nhớ:** Parallel stream phù hợp với việc **chia nhỏ phép tính**; blocking I/O làm worker **chờ thay vì tính**. Nếu quá nhiều worker cùng chờ, pool có thể không còn đủ tài nguyên thực thi những phần việc khác. Hãy chọn cơ chế điều phối I/O riêng và giới hạn đúng tài nguyên đích.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, common pool, giới hạn điều chỉnh worker khi unmanaged blocking, `ManagedBlocker`.
- [Java SE 21 API — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): pipeline, parallel execution, ordering và yêu cầu tránh can thiệp/side effects.
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default asynchronous execution facility và overload truyền executor.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): tác vụ blocking I/O trên virtual thread, hiệu quả tài nguyên, giới hạn concurrency.
