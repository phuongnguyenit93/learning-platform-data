# Chọn cách làm dễ hiểu trước khi tăng mức xử lý song song

Thuộc nhóm **Kiểm thử và tối ưu**: nội dung này tập trung vào cách xác định bottleneck, chọn mức concurrency/parallelism phù hợp và kiểm chứng hiệu năng trước khi tăng độ phức tạp. Bài ưu tiên API còn được hỗ trợ trong **Java SE hiện hành**; chương trình mẫu tương thích Java 8, còn virtual threads được giới thiệu riêng cho Java 21+.

## 1. Nguyên tắc: làm đúng và rõ trước, tăng concurrency sau khi có bằng chứng

Khi một đoạn Java chạy chậm, phản xạ đầu tiên thường là tạo thêm thread, dùng parallelStream hoặc chia công việc thành nhiều task. Nhưng **nhiều luồng không tự động làm chương trình nhanh hơn**. Chúng cũng tạo chi phí lập lịch, chuyển ngữ cảnh, phối hợp kết quả, đồng bộ, cấp phát bộ nhớ và xử lý lỗi.

Một cách làm dễ hiểu thường có những ưu điểm rất thực tế:

- Dễ đọc, review và sửa khi yêu cầu thay đổi.
- Dễ kiểm thử vì ít trạng thái dùng chung và ít thứ tự thực thi bất định.
- Dễ tìm lỗi và đo thời gian của từng bước.
- Có ít chi phí điều phối hơn với workload nhỏ.
- Làm baseline để so sánh khi thử cách song song.

**Nguyên tắc thực hành:** bắt đầu bằng phiên bản tuần tự đúng và đơn giản; đo trong điều kiện gần thực tế; xác định bottleneck; chỉ song song hóa phần công việc độc lập có khả năng đem lại lợi ích; đo lại cả hiệu năng lẫn độ phức tạp vận hành.

Ví dụ, một vòng lặp xử lý 100 phần tử với vài phép tính nhẹ thường không cần tạo 100 task. Việc tạo, gửi, lập lịch và gom 100 kết quả có thể tốn nhiều hơn phần tính toán.

**Mục tiêu không phải loại bỏ concurrency.** Mục tiêu là dùng mức xử lý phù hợp với loại công việc, giới hạn tài nguyên và yêu cầu của ứng dụng.

## 2. Phân biệt concurrency, parallelism và asynchronous

Ba thuật ngữ có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Concurrency** | Nhiều công việc cùng tiến triển trong một khoảng thời gian; có thể luân phiên trên một CPU | Một server tiếp nhận nhiều request và chuyển sang request khác khi một request đang chờ I/O |
| **Parallelism** | Nhiều công việc thực sự chạy đồng thời trên các đơn vị xử lý khác nhau | Chia phép tính CPU thành các phần chạy trên nhiều core |
| **Asynchronous** | Người gọi không phải chờ đồng bộ ngay tại điểm bắt đầu; kết quả/lỗi được nhận sau | Gửi tác vụ bằng CompletableFuture và xử lý khi hoàn tất |

Một chương trình asynchronous có thể chỉ dùng một thread. Một chương trình concurrent có thể chạy trên một core bằng cách luân phiên. Parallelism đòi hỏi tài nguyên thực thi đồng thời.

**Đừng dùng số lượng thread làm thước đo hiệu năng.** Cần biết ứng dụng đang tiêu tốn CPU, chờ mạng, chờ database, chờ lock hay chờ hàng đợi.

## 3. Xây baseline tuần tự có thể kiểm chứng

Trước khi tối ưu, viết một phiên bản có kết quả xác định:

~~~java
long total = 0L;
for (int value : values) {
    total += calculate(value);
}
~~~

Baseline nên làm rõ:

- Input nào được chấp nhận và output nào được mong đợi.
- Có thứ tự xử lý nào cần giữ không?
- Có side effect nào không (ghi database, gửi message, cập nhật file)?
- Trường hợp lỗi, null, timeout và input rỗng được xử lý ra sao?
- Phần nào là logic nghiệp vụ, phần nào là I/O hoặc điều phối?

**Tách hàm tính toán khỏi side effect** nếu có thể. Ví dụ, biến một bản ghi thành kết quả thuần trước, sau đó mới ghi kết quả vào storage. Một hàm thuần dễ chạy tuần tự, dễ test và cũng dễ phân chia cho nhiều worker.

Giữ baseline trong test suite để kiểm tra mọi biến thể song song cho ra cùng kết quả và vẫn giữ các invariant nghiệp vụ.

## 4. Đo trước khi kết luận chương trình chậm ở đâu

Đừng chỉ đo thời gian toàn bộ một lần chạy rồi suy ra method nào là bottleneck. Hãy xác định các chỉ số phù hợp với hệ thống:

- **Latency:** thời gian một request hoặc một tác vụ hoàn tất.
- **Throughput:** số request/tác vụ hoàn tất trong một đơn vị thời gian.
- **Tail latency:** p95, p99 hoặc p99.9, giúp phát hiện các request chậm bất thường.
- **CPU utilization:** CPU có thực sự bận tính toán không?
- **Allocation và GC:** tạo quá nhiều object hoặc garbage collection có đang chiếm thời gian?
- **Lock contention:** thread có chờ monitor/lock không?
- **Queue depth và rejection:** tác vụ đang xếp hàng lâu hoặc bị từ chối?
- **I/O wait:** thời gian chờ database, network, filesystem hay dịch vụ ngoài?

**Tối ưu đúng chỉ số của mục tiêu.** Nếu yêu cầu là p99 của API, một benchmark chỉ báo average time của một method không đủ. Nếu yêu cầu là tổng throughput batch, chỉ nhìn latency của một item cũng chưa đủ.

So sánh trước/sau với cùng input, cùng cấu hình JVM, cùng dữ liệu và điều kiện tải. Ghi rõ phiên bản JDK, phần cứng, giới hạn container, heap và số worker để kết quả có thể lặp lại.

## 5. Tìm bottleneck trước khi thay đổi kiến trúc

Một ứng dụng chậm có thể gặp nhiều nguyên nhân khác nhau:

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Một hoặc vài core bận liên tục | Tính toán CPU, thuật toán hoặc vòng lặp tốn kém | Profile hot methods, kiểm tra thuật toán và allocation |
| CPU thấp nhưng request vẫn chậm | Chờ I/O, lock, queue hoặc dịch vụ ngoài | Theo dõi latency theo dependency, thread state và I/O |
| Queue tăng liên tục | Tốc độ nhận việc cao hơn tốc độ xử lý | Backpressure, giới hạn admission, tăng capacity có kiểm chứng |
| GC thường xuyên hoặc pause dài | Allocation quá nhiều, object sống lâu hoặc heap pressure | JFR, allocation profile, heap analysis |
| Nhiều thread ở trạng thái blocked/waiting | Contention hoặc dependency đồng bộ | Lock profile, thread dump, giảm vùng critical section |
| Một task lớn chạy lâu hơn hẳn các task khác | Chia việc mất cân bằng | Điều chỉnh partition, kích thước task và thuật toán |

Tăng thread count không sửa được thuật toán có độ phức tạp quá cao, query database thiếu index, network timeout, lock contention hay queue không giới hạn.

**Tìm phần chiếm nhiều thời gian nhất trước.** Nếu một bước chỉ chiếm 2% tổng thời gian, tăng tốc bước đó gấp đôi chỉ cải thiện tổng thời gian rất ít.

## 6. Quy luật Amdahl: phần tuần tự giới hạn mức tăng tốc

Giả sử một tỷ lệ **s** của chương trình bắt buộc chạy tuần tự, phần còn lại có thể chia đều trên **p** bộ xử lý. Mức tăng tốc lý tưởng được giới hạn bởi:

\[
Speedup(p) = \frac{1}{s + \frac{1-s}{p}}
\]

Ví dụ, nếu 20% thời gian không thể song song hóa, kể cả có vô hạn bộ xử lý thì mức tăng tốc tối đa cũng chỉ là 5 lần theo mô hình lý tưởng.

Trong chương trình thật còn có chi phí:

- Chia input và tạo task.
- Chờ task hoàn tất.
- Kết hợp kết quả.
- Đồng bộ và tranh chấp tài nguyên.
- Chuyển ngữ cảnh và cache miss.
- Garbage collection do nhiều object trung gian.

Vì vậy, kết quả thực tế thường thấp hơn giới hạn lý tưởng. Nếu workload quá nhỏ, overhead có thể làm bản song song chậm hơn bản tuần tự.

**Tách phần song song được và phần phải tuần tự.** Ví dụ, nhiều ảnh có thể xử lý độc lập nhưng bước ghi vào một file tổng hợp có thể phải tuần tự hóa hoặc dùng một writer riêng.

## 7. Chọn cách theo loại workload

### CPU-bound

Công việc chủ yếu tính toán, ít chờ I/O: mã hóa ảnh, nén, tính toán số, parse dữ liệu trong RAM hoặc xử lý từng phần dữ liệu độc lập.

Hướng phù hợp:

- Bắt đầu bằng vòng lặp hoặc Stream tuần tự.
- Nếu workload đủ lớn, thử parallel stream hoặc một executor có parallelism được kiểm soát.
- Chia công việc thành các phần đủ lớn để giảm overhead.
- Tránh tạo quá nhiều task nhỏ.
- Theo dõi CPU, allocation, lock và thời gian gom kết quả.

Với CPU-bound, số worker khởi điểm thường dựa trên số CPU có thể sử dụng, nhưng phải đo dưới giới hạn thực của máy/container và tải của các ứng dụng khác.

### I/O-bound

Công việc thường chờ database, HTTP, file hoặc dịch vụ khác:

- Nhiều request có thể cùng chờ I/O, nên concurrency có thể tăng throughput.
- Cần giới hạn số request đồng thời theo connection pool, quota, rate limit và khả năng chịu tải của dependency.
- Dùng executor có worker/queue bounds phù hợp hoặc virtual threads trên Java 21+ khi ứng dụng dùng blocking I/O.
- Đo thời gian chờ và timeout, không chỉ CPU.

**Thêm thread không làm database có thêm connection hay API ngoài tăng quota.** Nếu downstream đã bão hòa, tăng concurrency chỉ tạo thêm queue, timeout và retry.

### Mixed workload

Nếu task vừa tính toán vừa chờ I/O, xác định hai pha và giới hạn riêng từng tài nguyên. Không dùng một con số thread chung cho mọi loại công việc mà không có dữ liệu.

## 8. Khi nào vòng lặp tuần tự là lựa chọn tốt?

Giữ cách tuần tự khi:

- Dữ liệu ít hoặc mỗi phần tử xử lý rất nhanh.
- Các bước phụ thuộc kết quả trước đó.
- Cần thứ tự side effect rõ ràng.
- Logic có nhiều state dùng chung.
- Dependency bên ngoài đã có giới hạn concurrency thấp.
- Hiệu năng đã đáp ứng SLA và chi phí thay đổi không đáng.
- Độ phức tạp điều phối làm tăng rủi ro nhiều hơn lợi ích.

Một vòng lặp rõ ràng cũng thường dễ debug hơn một pipeline có nhiều callback lồng nhau. Khi có bottleneck, có thể tối ưu thuật toán, giảm cấp phát, batch I/O hoặc cache trước khi thêm parallelism.

**Đừng tối ưu chỉ vì có thể.** Một implementation dễ hiểu và đủ nhanh thường là nền tảng tốt hơn cho thay đổi sau này.

## 9. Stream tuần tự: cách biểu đạt khai báo, chưa cần nhiều thread

Java Stream giúp mô tả pipeline xử lý dữ liệu:

~~~java
long total = values.stream()
        .filter(value -> value > 0)
        .mapToLong(this::calculate)
        .sum();
~~~

Stream mặc định là **sequential**. Các bước filter, map và sum được kết hợp thành pipeline; terminal operation như sum kích hoạt việc xử lý.

Dùng Stream khi nó làm rõ phép biến đổi dữ liệu. Dùng vòng lặp khi có nhiều nhánh, trạng thái, break/continue hoặc side effect khiến pipeline khó đọc.

**Không phải Stream lúc nào cũng nhanh hơn for-loop.** Mục tiêu chính của Stream là biểu đạt aggregate operations rõ ràng; hiệu năng phụ thuộc source, pipeline, JIT, allocation và workload.

## 10. Parallel stream: dùng khi phép xử lý độc lập và đủ lớn

Có thể thử thay:

~~~java
long total = values.stream()
        .mapToLong(this::calculate)
        .sum();
~~~

bằng:

~~~java
long total = values.parallelStream()
        .mapToLong(this::calculate)
        .sum();
~~~

Hoặc:

~~~java
long total = values.stream()
        .parallel()
        .mapToLong(this::calculate)
        .sum();
~~~

Các thao tác map/filter/reduce phải được thiết kế để cho kết quả đúng khi chạy ở nhiều thread. Hàm xử lý nên **stateless** và **non-interfering**: không thay đổi source đang được pipeline đọc và không phụ thuộc vào state có thể thay đổi giữa các lần gọi.

**parallelStream không phải nút tăng tốc chung cho mọi collection.** Cần cân nhắc kích thước input, chi phí mỗi phần tử, chất lượng Spliterator khi chia source, tính độc lập, chi phí combine/reduce, yêu cầu encounter order và các task khác đang sử dụng common pool.

Một list nhỏ với công việc nhẹ có thể chạy chậm hơn khi dùng parallelStream.

## 11. Tránh side effect và mutable shared state trong parallel stream

Đoạn sau có thể sai khi chạy song song:

~~~java
List<Integer> results = new ArrayList<Integer>();
values.parallelStream()
        .map(this::calculate)
        .forEach(value -> results.add(value));
~~~

**ArrayList không an toàn cho nhiều thread cùng ghi.** Việc bọc list bằng synchronized collection có thể tránh một số race condition, nhưng lock chung lại gây contention và làm mất lợi ích song song.

Ưu tiên reduction/collect:

~~~java
List<Integer> results = values.parallelStream()
        .map(this::calculate)
        .collect(Collectors.toList());
~~~

Với phép cộng, dùng reduction:

~~~java
long total = values.parallelStream()
        .mapToLong(this::calculate)
        .sum();
~~~

Không cập nhật counter dùng chung trong map/filter bằng biến mutable. Tránh stateful predicate như "nếu đã thấy phần tử này thì đổi kết quả" khi thứ tự xử lý không được kiểm soát.

**Side effect trong behavioral parameter còn có thể bị bỏ qua** nếu Stream implementation chứng minh stage đó không ảnh hưởng kết quả terminal operation. Không dùng map/peek như nơi bắt buộc phải ghi log hoặc ghi database.

## 12. Associativity và tính đúng của reduction

Parallel reduction chia input thành các phần, tính kết quả từng phần rồi kết hợp. Phép combine cần có tính chất phù hợp, đặc biệt là **associative** trong miền giá trị được xét.

Phép cộng số nguyên trong giới hạn không tràn có tính kết hợp:

\[
(a+b)+c = a+(b+c)
\]

Nhưng phép trừ không có tính kết hợp:

\[
(a-b)-c \ne a-(b-c)
\]

Vì thế, không thay một vòng lặp phụ thuộc thứ tự bằng parallel reduce với phép combine tùy ý.

**Overflow cũng có thể phá kỳ vọng toán học.** Phép cộng long trong Java có thể wrap khi vượt giới hạn; nếu nghiệp vụ cần tổng chính xác, hãy dùng kiểm tra tràn, BigInteger hoặc giới hạn input phù hợp trước khi parallelize.

Với mutable reduction, dùng Collector đúng contract. Không tự viết collector concurrent chỉ vì muốn bỏ bước merge; hãy xác định rõ container có thread-safe, unordered và combiner có semantics đúng hay không.

## 13. Encounter order và thứ tự side effect

Nguồn như List thường có encounter order. Kết quả của các phép biến đổi vẫn có thể giữ thứ tự này ngay cả khi xử lý song song, nhưng **thứ tự thực thi lambda trên từng phần tử không được bảo đảm**.

- **forEach** không hứa thứ tự theo encounter order.
- **forEachOrdered** giữ thứ tự quan sát của terminal action, nhưng có thể làm giảm lợi ích song song.
- **findAny** cho phép lấy một phần tử bất kỳ; **findFirst** phải tôn trọng encounter order khi source có thứ tự.
- **unordered()** có thể giúp một số operation chạy hiệu quả hơn nếu nghiệp vụ không cần thứ tự.

Không gửi email, ghi log nghiệp vụ theo thứ tự, cập nhật một transaction phụ thuộc thứ tự hoặc thay đổi state tuần tự từ lambda của parallel stream.

Nếu thứ tự side effect là yêu cầu, tách tính toán song song thành kết quả thuần, sau đó xử lý/commit kết quả theo thứ tự đã định.

## 14. Common ForkJoinPool và giới hạn của parallel stream

Các thao tác parallel stream trong JDK thường sử dụng **ForkJoinPool.commonPool**. Đây là pool dùng chung cho các công việc fork/join trong JVM; các API async của CompletableFuture không chỉ định Executor cũng thường dùng pool này.

Hệ quả:

- Nhiều phần không liên quan có thể tranh chấp cùng tài nguyên.
- Blocking I/O trong worker có thể làm giảm khả năng xử lý các task khác.
- Tải từ một library có thể ảnh hưởng pipeline của code khác.
- Khó kiểm soát riêng queue, admission và lifecycle theo từng workload.

**parallelStream không có tham số Executor trong API Stream chuẩn.** Nếu cần kiểm soát pool, queue, rejection hoặc ưu tiên của workload, cân nhắc submit các task qua ExecutorService hoặc một cấu trúc điều phối riêng đã được đo kiểm.

Không tùy tiện thay đổi system property của common pool để "sửa" một service. Đó là cấu hình toàn JVM và có thể ảnh hưởng những thành phần khác.

## 15. ExecutorService: tách mô tả task khỏi cách chạy task

ExecutorService cho phép submit Runnable hoặc Callable và nhận Future:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    Future<Long> result = executor.submit(() -> calculateBatch());
    long value = result.get();
} finally {
    executor.shutdown();
}
~~~

Đây là snippet cần import java.util.concurrent.* và method calculateBatch có sẵn. **Future.get() chờ kết quả**; nếu task thất bại, get ném ExecutionException và cause chứa lỗi gốc.

ExecutorService hữu ích khi cần số worker có thể kiểm soát, gom nhiều task độc lập, chờ kết quả bằng Future, quản lý shutdown/cancellation và chọn queue/thread factory/rejection policy ở mức ThreadPoolExecutor.

**Đừng tạo một pool mới cho từng phần tử.** Tạo executor theo lifecycle của component/service, tái sử dụng đúng phạm vi và shutdown khi component kết thúc.

## 16. Chọn pool size và queue theo tài nguyên

Với CPU-bound, bắt đầu thử số worker gần số CPU có thể sử dụng. Với I/O-bound, có thể có nhiều task chờ hơn, nhưng cần tính giới hạn connection, file descriptor, remote quota và memory.

Không có một công thức thread count đúng cho mọi ứng dụng. Đo CPU được cấp cho process/container, số worker active/idle, queue depth, thời gian nằm trong queue, throughput, p95/p99 latency, rejection và timeout.

**Executors.newFixedThreadPool(n)** giới hạn số worker nhưng sử dụng một shared queue không giới hạn dung lượng. Nếu producer gửi task nhanh hơn tốc độ xử lý, queue có thể tăng liên tục và giữ nhiều object/request trong heap.

Khi cần giới hạn backlog, dùng **ThreadPoolExecutor** với bounded queue và rejection policy rõ ràng. Ví dụ:

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(200),
        new ThreadPoolExecutor.AbortPolicy());
~~~

Khi pool và queue đều đầy, AbortPolicy ném RejectedExecutionException để caller biết hệ thống đang bão hòa. Caller có thể trả lỗi quá tải, retry có backoff hoặc áp dụng admission control theo hợp đồng ứng dụng.

**CallerRunsPolicy** là một lựa chọn tạo backpressure vì thread submit sẽ tự chạy task khi pool bão hòa; nó cũng có thể làm chậm request thread gọi submit. Chỉ dùng khi hành vi đó phù hợp. Tránh DiscardPolicy nếu caller cần bảo đảm task được xử lý.

## 17. CompletableFuture: ghép các bước bất đồng bộ

CompletableFuture biểu diễn một kết quả có thể hoàn tất trong tương lai và cho phép nối các bước:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(this::loadUser, ioExecutor)
                .thenApply(this::formatUser);
~~~

Đây là snippet có ioExecutor và các method đã được định nghĩa.

Một số operation thường dùng:

| Method | Vai trò |
| --- | --- |
| **supplyAsync** | Chạy Supplier và tạo kết quả |
| **runAsync** | Chạy Runnable không trả kết quả |
| **thenApply** | Biến đổi kết quả khi stage trước hoàn tất |
| **thenCompose** | Nối một stage khác, tránh Future lồng nhau |
| **thenCombine** | Kết hợp hai kết quả độc lập |
| **allOf** | Chờ tất cả CompletableFuture hoàn tất |
| **exceptionally / handle** | Xử lý kết quả hoặc lỗi |

**Không cần dùng CompletableFuture chỉ để làm một vòng lặp đơn giản.** Nó phù hợp hơn khi có nhiều bước async hoặc nhiều dependency có thể chạy độc lập.

Các continuation không có hậu tố Async như thenApply có thể chạy trên thread hoàn tất stage trước hoặc thread gọi completion. Các phương thức Async không truyền Executor thường sử dụng common pool. Khi workload cần pool riêng, truyền Executor rõ ràng cho supplyAsync/thenApplyAsync.

## 18. Lỗi, cancellation và timeout phải có policy

Bất đồng bộ làm luồng lỗi ít hiển nhiên hơn:

- **Future.get()** có thể ném InterruptedException hoặc ExecutionException.
- **CompletableFuture.join()** thường bọc lỗi trong CompletionException.
- **cancel(true)** trên Future yêu cầu interrupt task đang chạy, nhưng task phải hợp tác bằng cách kiểm tra interrupt hoặc gọi API interruptible.
- CompletableFuture.cancel không phải cơ chế dừng thread nền một cách bảo đảm; nó hoàn tất future theo trạng thái cancellation.
- Một timeout ở caller không đồng nghĩa công việc phía database/HTTP đã dừng.
- Khi nhiều stage phụ thuộc nhau, xác định lỗi nào khiến cả pipeline thất bại và lỗi nào được phép fallback.

Java 8 có các overload **Future.get(timeout, unit)** để giới hạn thời gian chờ. Các API như **CompletableFuture.orTimeout** được thêm sau Java 8; chỉ dùng khi runtime target hỗ trợ.

**Không retry vô hạn và không retry ngay lập tức** khi dependency đang quá tải. Retry cần giới hạn số lần, backoff, jitter, idempotency và ngân sách thời gian tổng.

## 19. Blocking I/O trong worker và virtual threads trên Java 21+

Với Java 8, blocking I/O thường được quản lý bằng một executor có worker và queue giới hạn, kết hợp timeout/connection pool/admission control.

Từ **Java 21**, virtual threads là lựa chọn hiện hành cho nhiều tác vụ blocking I/O. Ví dụ:

~~~java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Response> first = executor.submit(this::callServiceA);
    Future<Response> second = executor.submit(this::callServiceB);

    Response a = first.get();
    Response b = second.get();
}
~~~

Đây là snippet Java 21+, cần các method callServiceA/callServiceB và kiểu Response có sẵn. Executor tạo virtual thread cho từng task; try-with-resources đóng executor và chờ các task đã submit hoàn tất.

**Virtual threads không làm CPU tính toán nhanh hơn** và không nên được pool như platform threads. Chúng giúp xử lý nhiều task đang chờ blocking I/O với chi phí thread thấp hơn, nhưng không làm database tăng số connection hoặc bỏ giới hạn remote service.

Ngay cả với virtual threads, vẫn phải giới hạn tài nguyên thực như connection pool, request quota, memory, số file đang mở và công việc CPU-intensive. Java 8 không có virtual threads; dùng ExecutorService tương thích runtime mục tiêu.

## 20. Chia task: đủ lớn, độc lập và cân bằng

Khi tự chia workload:

- Mỗi task cần đủ việc để chi phí submit/scheduling không chiếm phần lớn runtime.
- Các phần nên có chi phí tương đối cân bằng.
- Input được chia cần tránh bị sửa trong lúc worker đọc.
- Kết quả cần có cách combine đúng và không phụ thuộc thứ tự hoàn tất.
- Số task không cần bằng số phần tử; thường chỉ cần số chunk hợp lý.
- Không tạo task con rồi block chờ task con trong cùng pool nhỏ nếu có nguy cơ worker starvation/deadlock.

Nếu một chunk lớn gấp nhiều lần chunk khác, một worker có thể trở thành tail task giữ cả pipeline chờ. Có thể thử partition theo số phần tử, kích thước dữ liệu hoặc ước lượng chi phí; sau đó đo độ lệch thời gian giữa các chunk.

**Task granularity là một trade-off:** quá nhỏ thì overhead lớn; quá lớn thì mất cân bằng tải và khả năng điều phối/cancel.

## 21. Ví dụ hoàn chỉnh: cùng một kết quả theo bốn cách

Chương trình sau chạy được trên Java 8 trở lên. Nó so sánh cách tính tổng tuần tự, parallel stream, ExecutorService với bốn chunk và CompletableFuture dùng cùng executor.

Hàm work là deterministic và không sửa state dùng chung. Chương trình **không in thời gian chạy**, vì thời gian phụ thuộc máy, JVM, tải nền và môi trường. Mục tiêu của ví dụ là kiểm chứng tính đúng và cách quản lý lifecycle.

Lưu file **SimpleBeforeParallelDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class SimpleBeforeParallelDemo {
    private static final int ITEM_COUNT = 10000;
    private static final int PARTS = 4;
    private static final int ROUNDS = 100;

    private static long work(int seed) {
        long value = seed;
        for (int i = 0; i < ROUNDS; i++) {
            value = (value * 1664525L + 1013904223L) & 0x7fffffffL;
        }
        return value;
    }

    private static long sumRange(List<Integer> items, int from, int to) {
        long total = 0L;
        for (int i = from; i < to; i++) {
            total += work(items.get(i));
        }
        return total;
    }

    private static long sumSequential(List<Integer> items) {
        return sumRange(items, 0, items.size());
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        List<Integer> items = IntStream.rangeClosed(1, ITEM_COUNT)
                .boxed()
                .collect(Collectors.toList());

        long sequential = sumSequential(items);
        long parallelStream = items.parallelStream()
                .mapToLong(SimpleBeforeParallelDemo::work)
                .sum();

        ExecutorService executor = Executors.newFixedThreadPool(PARTS);
        boolean terminated = false;
        try {
            List<Future<Long>> submitted = new ArrayList<Future<Long>>();
            for (int part = 0; part < PARTS; part++) {
                final int from = part * items.size() / PARTS;
                final int to = (part + 1) * items.size() / PARTS;
                Callable<Long> task = () -> sumRange(items, from, to);
                submitted.add(executor.submit(task));
            }

            long executorResult = 0L;
            for (Future<Long> future : submitted) {
                executorResult += future.get();
            }

            List<CompletableFuture<Long>> stages =
                    new ArrayList<CompletableFuture<Long>>();
            for (int part = 0; part < PARTS; part++) {
                final int from = part * items.size() / PARTS;
                final int to = (part + 1) * items.size() / PARTS;
                stages.add(CompletableFuture.supplyAsync(
                        () -> sumRange(items, from, to), executor));
            }
            CompletableFuture<?>[] all =
                    stages.toArray(new CompletableFuture<?>[0]);
            CompletableFuture.allOf(all).join();

            long futureResult = 0L;
            for (CompletableFuture<Long> stage : stages) {
                futureResult += stage.join();
            }

            System.out.println("items: " + items.size());
            System.out.println("sequential result: " + sequential);
            System.out.println("parallel stream matches: " +
                    (parallelStream == sequential));
            System.out.println("fixed executor matches: " +
                    (executorResult == sequential));
            System.out.println("completable future matches: " +
                    (futureResult == sequential));
            System.out.println("submitted chunks: " + submitted.size());
            System.out.println("async stages: " + stages.size());
        } finally {
            executor.shutdown();
            try {
                terminated = executor.awaitTermination(10, TimeUnit.SECONDS);
                if (!terminated) {
                    executor.shutdownNow();
                    terminated = executor.awaitTermination(10, TimeUnit.SECONDS);
                }
            } catch (InterruptedException interrupted) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                throw interrupted;
            }
        }
        System.out.println("executor terminated: " + terminated);
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 SimpleBeforeParallelDemo.java
java SimpleBeforeParallelDemo
~~~

Có thể kiểm tra cùng source ở target Java 8 bằng JDK mới:

~~~bash
javac -Xlint:-options --release 8 SimpleBeforeParallelDemo.java
java -cp . SimpleBeforeParallelDemo
~~~

Hoặc dùng javac/java trực tiếp trên JDK 8.

**Stdout đã kiểm chứng ở cả target Java 17 và Java 8:**

~~~text
items: 10000
sequential result: 10738027989448
parallel stream matches: true
fixed executor matches: true
completable future matches: true
submitted chunks: 4
async stages: 4
executor terminated: true
~~~

**Điều ví dụ chứng minh:** ba cách điều phối cho cùng kết quả với input và hàm tính thuần. Nó **không chứng minh parallel nhanh hơn**. Chỉ benchmark trong môi trường phù hợp mới cho biết chi phí/thời gian; một bài test correctness không phải benchmark.

## 22. Benchmark micro và JMH

Đồng hồ bấm giờ trong một vòng lặp Java thường cho kết quả sai lệch vì JVM warmup/JIT compilation, dead-code elimination, inlining, escape analysis, allocation, GC và tiến trình nền.

**JMH (Java Microbenchmark Harness)** là công cụ của OpenJDK dành cho benchmark code chạy trên JVM. Dự án JMH khuyến nghị tạo project độc lập bằng Maven archetype, build executable benchmark JAR và chạy từ command line; thêm mỗi jmh-core vào ứng dụng hoặc chạy tùy tiện trong IDE chưa đủ để tạo benchmark đáng tin.

Tạo project theo hướng dẫn của JMH:

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=bench -Dversion=1.0
cd bench
mvn clean verify
java -jar target/benchmarks.jar
~~~

Ví dụ benchmark cần các import từ **org.openjdk.jmh.annotations** và **java.util.concurrent.TimeUnit**:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(2)
public class SumBenchmark {
    @Param({"1000", "100000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) {
            values[i] = i + 1;
        }
    }

    private static long work(int value) {
        long result = value;
        for (int i = 0; i < 100; i++) {
            result = (result * 1664525L + 1013904223L)
                    & 0x7fffffffL;
        }
        return result;
    }

    @Benchmark
    public long sequential() {
        long total = 0L;
        for (int value : values) {
            total += work(value);
        }
        return total;
    }

    @Benchmark
    public long parallelStream() {
        return IntStream.range(0, values.length)
                .parallel()
                .mapToLong(index -> work(values[index]))
                .sum();
    }
}
~~~

Đây là **benchmark class** cần JMH project/annotation processor, không phải file Java độc lập để chạy bằng javac thường. Mỗi method trả về kết quả để harness có thể quan sát; dữ liệu được chuẩn bị ở setup ngoài vùng đo.

**Đọc kết quả có trách nhiệm:**

- Warmup để JVM đạt trạng thái ổn định trước đo.
- Measurement có nhiều iteration để quan sát biến thiên.
- Fork chạy trong JVM process riêng nhằm giảm ảnh hưởng trạng thái JVM giữa các benchmark.
- Dùng nhiều kích thước input; một phương pháp có thể tốt ở dữ liệu lớn nhưng thua ở dữ liệu nhỏ.
- Giữ nguyên workload, môi trường, JDK và cấu hình khi so sánh.
- Không lấy một score đơn lẻ làm SLA production.

JMH phù hợp đo method/algorithm. Đo throughput và latency của toàn service dưới tải đồng thời cần **load test** với request mix, dữ liệu và dependency thực tế.

## 23. Profiling với Java Flight Recorder và JDK Mission Control

Khi biết service chậm nhưng chưa rõ method/lock/GC nào gây ra, dùng profiling để quan sát runtime.

**Java Flight Recorder (JFR)** thu thập các event về JVM và ứng dụng. **JDK Mission Control (JMC)** giúp phân tích recording, gồm code/hot methods, threads, locks, I/O, memory và garbage collection.

Trên JDK hiện đại có JFR và công cụ jcmd/jfr, có thể bắt đầu recording trong một khoảng ngắn:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
jfr summary profile.jfr
~~~

Mở file profile.jfr trong JMC để phân tích. Lệnh là mẫu cho process đang chạy và cần quyền attach phù hợp; thay **<pid>** bằng process ID thực. Tùy JDK/distribution và môi trường container, quyền attach hoặc vị trí tool có thể khác.

Khi xem recording, tập trung vào:

- **Hot methods:** method nào chiếm nhiều CPU samples?
- **Thread states:** thread chạy, blocked, waiting hay chờ I/O?
- **Locks:** có monitor contention hoặc lock hold time dài?
- **Allocation/GC:** object nào được tạo nhiều, GC pause/heap growth ra sao?
- **I/O:** thời gian chờ network/file/database có nổi bật?
- **CPU load:** JVM có bận hay máy đang bị process khác chiếm CPU?

JFR có overhead, dù các cấu hình phù hợp có thể dùng để chẩn đoán hệ thống đang chạy. Chọn template và thời lượng recording phù hợp; không bật profiling nặng vô thời hạn chỉ để thu thập dữ liệu.

## 24. Đánh giá hiệu năng bằng tải gần production

Microbenchmark trả lời câu hỏi hẹp về một đoạn code. Nó không mô phỏng đầy đủ nhiều client cùng gửi request, queue/timeout/retry, database connection pool, HTTP connection limits, serialization/logging, heap/GC khi chạy lâu hoặc burst traffic.

Một load test tốt cần xác định:

1. Workload mix và tốc độ request đầu vào.
2. Thời lượng warm-up, thời gian đo và thời gian nghỉ.
3. Số client/concurrent request.
4. Input/data size và trạng thái cache.
5. Mục tiêu throughput, p95/p99, error rate và resource limits.
6. Kịch bản tăng tải, giữ tải, giảm tải và burst.
7. Ngưỡng bão hòa: queue bắt đầu tăng, rejection/timeout xuất hiện ở đâu?

**Không chỉ tăng client cho đến khi hệ thống sập.** Ghi nhận vùng hoạt động ổn định, giới hạn tài nguyên và cách ứng dụng phản ứng khi quá tải.

So sánh baseline tuần tự và bản song song bằng cùng workload; kiểm tra kết quả nghiệp vụ, không chỉ score. Nếu throughput tăng nhưng p99, error rate hoặc chi phí CPU/memory xấu đi, thay đổi đó có thể không đáp ứng mục tiêu.

## 25. Các sai lầm phổ biến khi tăng xử lý song song

1. **Song song hóa trước khi đo.** Có thể tối ưu nhầm phần không phải bottleneck.
2. **Cho rằng nhiều thread luôn nhanh hơn.** Scheduling, context switch và contention cũng tốn tài nguyên.
3. **Dùng parallelStream cho list nhỏ.** Overhead chia/ghép có thể lớn hơn phần tính toán.
4. **Dùng parallel stream cho blocking I/O không kiểm soát.** Worker pool dùng chung có thể bị ảnh hưởng.
5. **Sửa ArrayList/HashMap dùng chung từ lambda.** Có thể data race hoặc mất tính đúng.
6. **Dùng synchronized collection làm giải pháp cho mọi shared state.** Lock chung có thể triệt tiêu parallelism.
7. **Dùng side effect trong map/filter/peek.** Hành vi có thể khó dự đoán hoặc bị tối ưu bỏ.
8. **Dùng reduction không associative.** Kết quả có thể khác khi combine theo nhóm khác.
9. **Giả định forEach luôn giữ thứ tự.** Parallel stream không bảo đảm thứ tự side effect.
10. **Dùng forEachOrdered ở mọi nơi.** Có thể thêm chi phí đồng bộ/thứ tự không cần thiết.
11. **Tạo một task cho mỗi phần tử nhỏ.** Overhead task lớn và queue phình to.
12. **Không quản lý executor lifecycle.** Thread tồn tại sau khi component đã kết thúc.
13. **Dùng fixed thread pool rồi quên queue không giới hạn.** Backlog có thể tiêu thụ heap.
14. **Dùng cached thread pool cho tải không giới hạn.** Thread count có thể tăng mạnh.
15. **Không định nghĩa rejection/backpressure.** Hệ thống nhận nhiều việc hơn khả năng xử lý.
16. **Dùng common pool cho mọi workload.** Các tác vụ không liên quan có thể tranh chấp.
17. **Gọi join/get bên trong cùng pool theo dependency lồng nhau.** Có thể gây starvation hoặc deadlock.
18. **Nuốt exception của Future/CompletableFuture.** Lỗi tác vụ biến thành kết quả thiếu hoặc sai.
19. **Coi timeout ở caller là task đã dừng.** I/O hoặc tác vụ bên dưới có thể vẫn tiếp tục.
20. **Retry ngay và vô hạn.** Khi dependency quá tải, retry làm tải tăng thêm.
21. **Dùng virtual threads để tăng tốc CPU-bound.** Virtual threads chủ yếu giúp concurrency cho blocking tasks.
22. **Benchmark bằng một lần System.nanoTime.** Warmup/JIT/GC và dead-code elimination làm sai kết luận.
23. **So sánh hai phiên bản với input hoặc môi trường khác nhau.**
24. **Tối ưu throughput nhưng bỏ qua p99 và error rate.**
25. **Đổi nhiều yếu tố cùng lúc.** Khó xác định thay đổi nào tạo lợi ích hoặc regression.
26. **Không giữ baseline và test correctness.** Có thể nhanh hơn nhưng trả kết quả sai.
27. **Chỉ đo ở máy developer.** CPU quota, container, JDK và tải production có thể khác đáng kể.

## 26. Quy trình ra quyết định có thể lặp lại

Áp dụng theo trình tự:

1. **Viết bản tuần tự dễ hiểu.** Định nghĩa input, output, invariant và lỗi.
2. **Chạy test correctness.** Bao gồm input rỗng, biên, lỗi và dữ liệu đại diện.
3. **Đo baseline.** Ghi latency, throughput, p95/p99, CPU, memory, GC và I/O.
4. **Profile bottleneck.** Dùng JFR/JMC hoặc profiler phù hợp để tìm hot method, lock, allocation và I/O wait.
5. **Thử tối ưu tuần tự trước.** Giảm độ phức tạp thuật toán, query, allocation, serialization hoặc số lần gọi dependency.
6. **Phân loại workload.** CPU-bound, I/O-bound hay mixed.
7. **Chọn primitive phù hợp.** Sequential Stream/loop, parallel stream, ExecutorService, CompletableFuture hoặc virtual threads theo runtime và workload.
8. **Giới hạn tài nguyên.** Worker, queue, connection, timeout, retry, admission và rejection.
9. **Test correctness song song.** Xác minh thứ tự, race, cancellation, exception và state.
10. **Benchmark/load test lại.** Dùng JMH cho code path, load test cho service.
11. **So sánh toàn diện.** Kiểm tra throughput, tail latency, error rate, CPU/memory và vận hành.
12. **Giữ thay đổi nếu lợi ích đo được đáng với độ phức tạp.** Ghi lại cấu hình, điều kiện test và giới hạn áp dụng.

## 27. Checklist trước khi đưa code song song vào production

**Tính đúng:** mỗi task độc lập hay có dependency? Dữ liệu nguồn có bị sửa khi xử lý? Reduction có đúng? Kết quả có giữ thứ tự cần thiết?

**An toàn thread:** có shared mutable state, lock hoặc side effect không? Có object nào không thread-safe bị dùng chung?

**Tài nguyên:** worker count, queue capacity, DB/HTTP connections, memory và downstream quota đã được giới hạn?

**Điều phối:** executor có owner/lifecycle rõ? Có rejection policy, cancellation, timeout và shutdown?

**Lỗi:** exception từ task có được truyền tới caller? Retry có giới hạn và idempotent? Timeout có dừng hoặc cô lập tài nguyên bên dưới?

**Quan sát:** có queue depth, active workers, completed/rejected tasks, latency và error metrics? Có thể profile JFR khi cần?

**Hiệu năng:** có baseline, benchmark/load test lặp lại? Đã đo p95/p99 và error rate, không chỉ average?

**Bảo trì:** người khác có thể hiểu vì sao phần này cần chạy song song, cách chia task và cách combine không?

Nếu không giải thích được lợi ích và giới hạn của việc song song hóa bằng dữ liệu, hãy giữ bản đơn giản và tiếp tục điều tra bottleneck.

## 28. Bài tập và đáp án

**1.** Concurrency và parallelism khác nhau thế nào?  
**Đáp án:** Concurrency là nhiều việc cùng tiến triển; parallelism là thực thi thực sự đồng thời trên nhiều đơn vị xử lý.

**2.** Một vòng lặp nhỏ có cần parallelStream không?  
**Đáp án:** Không mặc định; chi phí chia/ghép và điều phối có thể lớn hơn lợi ích.

**3.** Stream mặc định chạy tuần tự hay song song?  
**Đáp án:** Tuần tự, trừ khi gọi parallel/parallelStream.

**4.** Lambda của parallel stream nên có đặc tính gì?  
**Đáp án:** Thường cần stateless và non-interfering; tránh mutable shared state và side effect không được kiểm soát.

**5.** Vì sao không cộng vào một ArrayList từ parallel forEach?  
**Đáp án:** ArrayList không hỗ trợ nhiều thread cùng ghi; dùng collect/reduction phù hợp.

**6.** Khi nào parallel reduction có thể giữ kết quả ổn định?  
**Đáp án:** Khi accumulator/combiner thỏa contract, phép combine có tính kết hợp trong miền dữ liệu và không có side effect sai.

**7.** parallelStream có tham số Executor chuẩn không?  
**Đáp án:** Không; nếu cần kiểm soát executor, dùng mô hình submit task rõ ràng.

**8.** newFixedThreadPool(4) có queue giới hạn không?  
**Đáp án:** Không, factory này dùng shared unbounded queue; cần ThreadPoolExecutor với bounded queue khi phải giới hạn backlog.

**9.** CompletableFuture.supplyAsync không truyền executor thường dùng gì?  
**Đáp án:** ForkJoinPool.commonPool.

**10.** thenApply và thenApplyAsync khác nhau thế nào?  
**Đáp án:** thenApply có thể chạy trên thread hoàn tất stage trước; thenApplyAsync điều phối async, mặc định common pool nếu không truyền Executor.

**11.** Future.get thất bại thì đọc lỗi gốc ở đâu?  
**Đáp án:** ExecutionException.getCause().

**12.** Virtual threads có phải giải pháp tăng tốc CPU-bound không?  
**Đáp án:** Không; chúng phù hợp nhiều tác vụ blocking I/O.

**13.** Vì sao JMH có warmup và fork?  
**Đáp án:** Giảm sai lệch do JIT/warmup và trạng thái JVM giữa các phép đo.

**14.** JMH thay thế load test không?  
**Đáp án:** Không; JMH đo code/benchmark cô lập, load test đo service dưới tải đồng thời.

**15.** Khi nào nên giữ bản tuần tự?  
**Đáp án:** Khi hiệu năng đáp ứng yêu cầu, dữ liệu nhỏ, logic phụ thuộc thứ tự hoặc lợi ích song song chưa được chứng minh.

## 29. Tài liệu Java hiện hành

- **Java Stream package (Java SE 26):** sequential/parallel mode, stateless behavior, non-interference, side effects, ordering và reduction: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- **ExecutorService (Java SE 26):** submit, Future, shutdown, lifecycle và quản lý task: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Executors (Java SE 26):** fixed/single/work-stealing/virtual-thread executors và hành vi các factory: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html
- **ThreadPoolExecutor (Java SE 26):** core/max pool, work queue, bounded queue và rejection policy: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **CompletableFuture (Java SE 26):** completion stages, executor mặc định, supplyAsync/runAsync và error handling: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **ForkJoinPool (Java SE 26):** work stealing, common pool và parallelism: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **Virtual Threads (Java SE 26):** mô hình blocking I/O, giới hạn CPU-bound và cách sử dụng virtual-thread executor: https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html
- **OpenJDK JMH project:** hướng dẫn tạo benchmark Maven độc lập, annotation processor, build và chạy benchmark: https://github.com/openjdk/jmh
- **Java SE 26 troubleshooting guide:** chẩn đoán hiệu năng bằng Flight Recorder, CPU, GC, synchronization, I/O và code execution: https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html
- **JDK Mission Control User Guide:** phân tích flight recording, method profiling, threads, locks, memory và I/O: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html

**Phiên bản:** Vòng lặp, Stream, ExecutorService, ForkJoinPool và CompletableFuture trong chương trình mẫu tương thích Java 8. Virtual threads là lựa chọn bổ sung từ Java 21+, không được dùng trong ví dụ Java 8. JMH là dependency benchmark riêng, không phải API tích hợp sẵn trong JDK. JFR/JMC được giới thiệu như công cụ chẩn đoán trên JDK hiện đại; cần kiểm tra command, quyền attach và cấu hình của runtime đang triển khai.

**Kết luận:** bắt đầu bằng cách làm tuần tự dễ hiểu, đo đúng bottleneck và giữ baseline. Khi có bằng chứng rằng phần việc độc lập đủ lớn, chọn primitive phù hợp, giới hạn tài nguyên và kiểm chứng cả tính đúng lẫn hiệu năng. Song song hóa là một quyết định kiến trúc có chi phí, không phải bước mặc định sau khi viết xong vòng lặp.
