# ForkJoin common pool phía sau parallel streams trong Java

## 1. Parallel stream thực thi ở đâu?

`Stream.parallel()` và `Collection.parallelStream()` cho phép một pipeline xử lý phần tử theo cách song song. Với các triển khai Stream của JDK hiện hành, khi gọi pipeline từ thread ứng dụng bình thường, công việc song song thường được chia thành các tác vụ kiểu fork/join và chạy thông qua **`ForkJoinPool.commonPool()`**. Đây là một pool dùng chung trong tiến trình Java, không phải pool mới được tạo riêng cho từng stream.

Điểm quan trọng cần phân biệt:

- **Stream API** quy định phép xử lý, quy tắc thứ tự, tính kết hợp, side effect và kết quả. API **không hứa** phải dùng một pool hoặc một số thread cố định.
- **ForkJoinPool** là cơ chế thực thi công việc nhiều tác vụ nhỏ. `commonPool()` cung cấp một pool chia sẻ để các thành phần Java dùng khi phù hợp.
- Tác vụ chạy song song có thể sử dụng cả **thread gọi terminal operation** bên cạnh worker của pool. Không được hiểu `parallel()` là “tất cả công việc bắt buộc chuyển sang các worker khác”.
- `parallel()` là gợi ý phương thức thực thi của stream, **không bảo đảm nhanh hơn** sequential và không làm dữ liệu hoặc side effect tự trở nên thread-safe.

Bài học tập trung vào Java concurrency chuẩn, không phụ thuộc framework.

### Kết quả cần nắm

Sau bài này, bạn có thể giải thích việc chia dữ liệu thành task, vai trò của work-stealing trong common pool, sự khác biệt giữa parallelism và số thread thật, ảnh hưởng của nguồn `Spliterator`, cách viết pipeline an toàn, cách chẩn đoán tranh chấp tài nguyên và khi nào không nên dùng parallel stream.

## 2. Vòng đời từ pipeline đến fork/join tasks

Một biểu thức như:

~~~java
long result = java.util.stream.LongStream.rangeClosed(1, 1_000_000)
    .parallel()
    .filter(n -> (n & 1L) == 0L)
    .map(n -> n * 2)
    .sum();
~~~

có các bước logic:

1. `rangeClosed` tạo nguồn có khả năng chia khoảng số thành các đoạn.
2. `parallel()` đánh dấu chế độ thực thi song song; lúc này phần lớn thao tác vẫn **lazy**, chưa chạy toàn bộ pipeline.
3. `filter` và `map` mô tả các intermediate operations.
4. `sum()` là terminal operation, kích hoạt traversal, chia việc và kết hợp các partial results.
5. Các phần việc độc lập có thể xử lý trên nhiều thread; phép cộng kết hợp kết quả cuối.

Có thể hình dung:

~~~text
Một Stream source
       |
       v
Spliterator: chia nguồn thành các phần
       |
       +---------+---------+---------+
       |         |         |         |
    task A     task B     task C    task D
       |         |         |         |
    worker X  worker Y  caller/   worker Z
                       worker
       +---------+---------+---------+
                 |
                 v
       kết hợp các kết quả
                 |
                 v
           terminal result
~~~

Sơ đồ mô tả ý tưởng, không ấn định số task hay số worker. Một pipeline có thể chia nhiều tác vụ hơn số worker; kích thước phần việc và cách kết hợp phụ thuộc implementation, nguồn dữ liệu, phép toán và mức parallelism.

Nếu stream đã ở trạng thái song song, gọi `sequential()` có thể chuyển pipeline về thực thi tuần tự; tương tự `parallel()` trên một stream tuần tự chuyển về chế độ song song. Một stream chỉ được tiêu thụ một lần; thay đổi chế độ không biến cùng một stream thành hai pipeline độc lập có thể chạy lại.

## 3. ForkJoinPool.commonPool() và work-stealing

`ForkJoinPool` được thiết kế cho các công việc có thể chia nhỏ và kết hợp. Worker thường có hàng đợi tác vụ riêng. Khi worker hết việc, nó có thể **steal** tác vụ từ hàng đợi của worker khác để cân bằng tải. Cơ chế này hữu ích khi công việc được chia thành nhiều phần độc lập, tương đối ngắn và nặng CPU.

Các khái niệm quan trọng:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `ForkJoinPool.commonPool()` | Singleton pool dùng chung trong một JVM cho các thành phần sử dụng nó |
| `ForkJoinPool.getCommonPoolParallelism()` | Mức parallelism cấu hình/được báo cáo cho common pool; không phải số thread chính xác đang xử lý stream |
| `ForkJoinPool.commonPool().getPoolSize()` | Số worker đang tồn tại tại thời điểm lấy mẫu, không tính đầy đủ mọi thread gọi stream |
| `ForkJoinPool.commonPool().getActiveThreadCount()` | Ước lượng worker đang hoạt động tại một thời điểm |
| Work-stealing | Worker rảnh lấy việc có thể thực hiện từ worker khác |
| Fork/join task | Đơn vị công việc có thể chia và kết hợp kết quả |
| Caller participation | Thread gọi terminal operation có thể tự xử lý một phần việc |

**Pool chung là tài nguyên chia sẻ.** Các parallel streams khác nhau hoặc những thành phần Java khác sử dụng common pool có thể cùng tranh chấp worker/CPU. Ví dụ, các overload `CompletableFuture.supplyAsync(...)` và `runAsync(...)` không truyền executor thường dùng common pool trong điều kiện cấu hình thông thường; có ngoại lệ triển khai khi common-pool parallelism không đáp ứng điều kiện nhất định. Vì vậy sự cạnh tranh với chúng cũng cần xem xét trong cùng một ứng dụng.

`ForkJoinPool.commonPool().shutdown()` không phải cách quản lý vòng đời pool của một parallel stream: common pool là tài nguyên chung của runtime; các lời gọi shutdown kiểu thông thường không làm pool chung dừng như một executor tự tạo. Bạn không cần và không nên đóng common pool sau mỗi stream.

Một parallel stream có thể chờ bên trong terminal operation cho đến khi có kết quả; gọi `parallel()` **không** biến terminal operation thành API trả `Future`/`CompletionStage`. Nếu thread gọi `sum()`, `collect()` hoặc `forEach()`, lời gọi ấy chỉ trở về khi terminal operation kết thúc bình thường hoặc báo lỗi.

## 4. Parallelism và cấu hình kích thước common pool

Ở nhiều cấu hình JDK phổ biến, parallelism mặc định của common pool được suy ra từ số bộ xử lý mà JVM nhận biết, thường gần `availableProcessors() - 1` nhưng có mức tối thiểu và các quy tắc/cấu hình cụ thể. JVM có thể nhìn thấy số CPU bị giới hạn bởi container hoặc chính sách chạy ứng dụng. **Không viết logic phụ thuộc vào một số worker mặc định cố định.**

Kiểm tra thông tin tại runtime:

~~~java
import java.util.concurrent.ForkJoinPool;

int cpuCount = Runtime.getRuntime().availableProcessors();
int commonParallelism = ForkJoinPool.getCommonPoolParallelism();

System.out.println("CPU JVM nhìn thấy: " + cpuCount);
System.out.println("Common parallelism: " + commonParallelism);
~~~

Đây là đoạn minh họa đặt trong phương thức hoặc class có import phù hợp; hai số in ra thay đổi theo máy/JVM. Muốn điều chỉnh cấu hình common pool, có thể dùng thuộc tính hệ thống lúc khởi động JVM:

~~~bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 ParallelCommonPoolDemo
~~~

Cú pháp trên là cách truyền cấu hình vào **JVM mới**; ví dụ chương trình ở mục 5 không giả định rằng thiết lập này cho đúng bốn worker hoạt động ở mọi thời điểm. Nên đặt thuộc tính trước khi common pool được khởi tạo (truyền qua `-D` lúc chạy), thay vì gọi `System.setProperty(...)` muộn và chờ pool đổi kích thước. Giá trị phù hợp phụ thuộc tải, CPU và các công việc khác cùng chia sẻ pool.

Đặc biệt:

- **Parallelism không đồng nghĩa throughput.** Ví dụ parallelism = 4 không bảo đảm bốn phép xử lý luôn cùng chạy, bởi có scheduling, người gọi cùng tham gia, công việc có thể quá nhỏ hoặc chỉ có ít nhánh để chia.
- **Không đồng nghĩa số thread toàn JVM.** Có thread ứng dụng, thread GC, thread I/O, các executor khác và thread caller.
- **Giá trị metric là ảnh chụp tại một thời điểm.** `getPoolSize()`, `getActiveThreadCount()` và `getStealCount()` chỉ giúp quan sát, không chứng minh một task cụ thể đã chạy ở worker nào.

Không đặt `common.parallelism` cao vô hạn để “tăng tốc”: task nặng CPU có thể cạnh tranh nhau trên cùng lõi; block I/O có thể làm worker bận chờ; nhiều parallel streams đồng thời có thể cùng gây áp lực cho pool.

## 5. Ví dụ Java 17 chạy được và kết quả xác định

Tạo file `ParallelCommonPoolDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

public class ParallelCommonPoolDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 1000)
            .sum();

        int parallelSum = IntStream.rangeClosed(1, 1000)
            .parallel()
            .sum();

        List<Integer> doubled = IntStream.rangeClosed(1, 8)
            .parallel()
            .map(n -> n * 2)
            .boxed()
            .toList();

        long evenCount = IntStream.rangeClosed(1, 1000)
            .parallel()
            .filter(n -> n % 2 == 0)
            .count();

        System.out.println("sequential=" + sequentialSum);
        System.out.println("parallel=" + parallelSum);
        System.out.println("doubled=" + doubled);
        System.out.println("evenCount=" + evenCount);
        System.out.println(
            "sameCommonPool=" +
            (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac -encoding UTF-8 ParallelCommonPoolDemo.java
java ParallelCommonPoolDemo
~~~

Stdout xác định:

~~~text
sequential=500500
parallel=500500
doubled=[2, 4, 6, 8, 10, 12, 14, 16]
evenCount=500
sameCommonPool=true
~~~

Giải thích:

- `rangeClosed(1, 1000)` có tổng `1000 × 1001 / 2 = 500500`. `sum()` là phép kết hợp phù hợp cho các phần việc; ở đây không có overflow `int`.
- `IntStream.rangeClosed` cung cấp nguồn có thứ tự encounter order xác định. Phép `map` giữ thứ tự logic. `Stream.toList()` trên ordered stream trả danh sách theo encounter order ngay cả khi xử lý các phần tử diễn ra không theo thứ tự.
- `evenCount` chỉ đếm phần tử thoả điều kiện; thứ tự xử lý thực tế không ảnh hưởng kết quả.
- `ForkJoinPool.commonPool()` trả về cùng một pool được chia sẻ. Dòng cuối minh họa identity của đối tượng pool, **không chứng minh** rằng mọi pipeline buộc phải dùng common pool theo contract của Stream API.

Đây là minh hoạ về **tính đúng của kết quả**, không phải benchmark tốc độ. Với 1.000 số nguyên, overhead chia việc có thể lớn hơn lợi ích song song.

## 6. Các thread thực thi và tính không xác định của lịch chạy

Nếu thêm lệnh ghi thread name:

~~~java
// Minh họa, đặt trong main() hoặc một phương thức Java.
java.util.stream.IntStream.range(0, 12)
    .parallel()
    .forEach(n ->
        System.out.println(
            n + " -> " + Thread.currentThread().getName()));
~~~

bạn có thể thấy tên kiểu `main` và `ForkJoinPool.commonPool-worker-N` trên một lần chạy điển hình. Tuy nhiên:

- Thứ tự dòng in không cố định.
- Không bảo đảm mọi lần chạy đều xuất hiện worker thread, hay xuất hiện đúng N worker.
- `System.out.println` dùng đồng bộ nội bộ, làm thay đổi mức contention; quan sát này không phản ánh chính xác hiệu năng pipeline CPU thuần.
- Tên thread chỉ là chi tiết chẩn đoán, không phải hợp đồng nghiệp vụ.

Tránh đặt assertion về thứ tự hoặc tên thread trong test của parallel stream. Test nên khẳng định **kết quả**, thứ tự encounter nếu phép toán giữ thứ tự, và các tính chất bất biến của pipeline.

Một điểm tinh tế: gọi parallel stream **bên trong một `ForkJoinPool` do ứng dụng tự tạo** có thể dẫn đến thực thi trên worker của pool đang gọi trong các JDK hiện hành. Hành vi này phụ thuộc chi tiết implementation; Stream API không cung cấp tham số “executor của tôi”. Không coi `customPool.submit(() -> stream.parallel()...)` là cơ chế cô lập tài nguyên có hợp đồng ổn định. Nếu bắt buộc kiểm soát executor, lịch và ranh giới resource, thiết kế rõ các `Callable`/`CompletableFuture` với executor, hoặc fork/join tasks cụ thể.

## 7. Spliterator quyết định khả năng chia dữ liệu

Song song hữu ích khi nguồn có thể được chia thành các phần đủ lớn với chi phí thấp. Stream thường dựa vào `Spliterator` để traversal và chia việc bằng `trySplit()`.

Các characteristics thường gặp:

| Characteristic | Tác dụng điển hình |
| --- | --- |
| `SIZED` | Biết kích thước ước lượng chính xác cho nguồn/phần được mô tả |
| `SUBSIZED` | Các spliterator con sau khi chia cũng có kích thước chính xác |
| `ORDERED` | Có encounter order; một số terminal operation phải giữ thứ tự này |
| `DISTINCT` | Các phần tử đã không trùng theo ngữ nghĩa nguồn |
| `SORTED` | Dữ liệu theo thứ tự đã định, có thể giúp tối ưu một số phép toán |

Các nguồn như mảng, `ArrayList` và `IntStream.range(...)` thường có khả năng chia việc tốt. Nguồn qua iterator, chuỗi sinh phụ thuộc trạng thái, hoặc dữ liệu vốn được đọc tuần tự có thể khó tách công việc và khiến parallel overhead lớn.

Ví dụ:

~~~java
int[] numbers = java.util.stream.IntStream
    .range(0, 1_000_000).toArray();

long total = java.util.Arrays.stream(numbers)
    .parallel()
    .asLongStream()
    .sum();
~~~

Đoạn trên là minh họa không có lớp `main` riêng. Mảng và phạm vi số có phân đoạn rõ ràng, phù hợp hơn để kiểm tra lợi ích tính toán song song. Tuy vậy, ngay cả nguồn dễ chia cũng không bảo đảm nhanh nếu công việc mỗi phần tử quá nhẹ.

### Stateful và ordered operations có thể làm giảm khả năng mở rộng

Các phép như `sorted()`, `distinct()`, `limit()` hay `skip()` trên nguồn có thứ tự đôi khi đòi hỏi phối hợp hoặc buffering, tùy đặc tính pipeline. `findFirst()` phải tôn trọng encounter order; `findAny()` có thể chấp nhận bất kỳ phần tử phù hợp. `forEachOrdered()` tôn trọng thứ tự encounter và có thể làm giảm lợi ích song song so với `forEach()` nếu ứng dụng không cần thứ tự.

Nếu nghiệp vụ cho phép kết quả không có thứ tự, `unordered()` hoặc các phép kết thúc không phụ thuộc thứ tự có thể tạo cơ hội tối ưu. Chỉ bỏ ràng buộc thứ tự khi thực sự **không quan trọng**; không đổi `findFirst()` thành `findAny()` nếu logic cần phần tử đầu tiên.

## 8. Stateless, non-interfering và phép giảm kết hợp được

Để parallel streams cho kết quả đúng, function trong pipeline thường phải **stateless** (không phụ thuộc trạng thái thay đổi giữa các phần tử) và **non-interfering** (không sửa nguồn đang duyệt), trừ nơi API mô tả hành vi rõ ràng. Một lỗi phổ biến:

~~~java
// Sai: ArrayList không an toàn cho nhiều thread cùng add.
java.util.List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.range(0, 10_000)
    .parallel()
    .forEach(output::add);
~~~

Đây là ví dụ chống chỉ định, không phải đoạn code nên chạy trong ứng dụng. Nhiều thread có thể sửa cùng `ArrayList`, gây data race, thiếu phần tử hoặc lỗi khác. Ngay cả khi thay bằng `Collections.synchronizedList(...)`, đoạn viết vẫn có contention và phụ thuộc side effect.

Cách đúng theo Stream API:

~~~java
java.util.List<Integer> output =
    java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

Hệ thống stream tự quản lý cách gom các partial results rồi tạo danh sách. `toList()` đưa ra danh sách **không thể sửa bằng các mutator của List**, và bảo toàn thứ tự encounter nếu nguồn có thứ tự.

Tương tự, tránh dùng biến accumulator dùng chung:

~~~java
// Sai: ++ trên mảng chia sẻ không có tính nguyên tử.
long[] total = {0};
java.util.stream.LongStream.range(1, 10_001)
    .parallel()
    .forEach(n -> total[0] += n);
~~~

Thay bằng:

~~~java
long total = java.util.stream.LongStream.range(1, 10_001)
    .parallel()
    .sum();
~~~

Ở phép reduction tổng quát, operation cần có **identity** phù hợp và **associative** để chia nhóm/tái kết hợp không làm thay đổi ý nghĩa:

~~~java
int sum = java.util.stream.IntStream.rangeClosed(1, 100)
    .parallel()
    .reduce(0, Integer::sum);
~~~

`0` là identity cho phép cộng, và phép cộng số nguyên (xét theo quy tắc arithmetic của Java) kết hợp được. Phép trừ không associative: `reduce(0, (a,b) -> a - b)` có thể cho kết quả khác khi chia/recombine. Với số dấu phẩy động, phép cộng có sai khác do thứ tự làm tròn; đừng đòi kết quả bit-for-bit bằng nhau giữa parallel và sequential nếu thuật toán chưa xử lý điều đó.

Với `collect(supplier, accumulator, combiner)` hoặc `Collector`, mỗi container tích luỹ và phép combiner phải thoả contract. Không tự đưa một container mutable dùng chung cho mọi partition rồi cùng sửa. `Collectors.groupingByConcurrent(...)` có thể hỗ trợ collection concurrent nhưng không có nghĩa luôn nhanh hơn `groupingBy(...)`; chọn theo thứ tự cần giữ, contention và chi phí grouping.

## 9. Vì sao common pool dễ bị nghẽn bởi blocking I/O?

Fork/join thường phù hợp công việc **CPU-bound, ngắn, có thể chia và tái kết hợp**. Hãy xét:

~~~java
// Minh hoạ anti-pattern, giả định urls và fetchBlocking() đã có.
urls.parallelStream()
    .map(url -> fetchBlocking(url))
    .toList();
~~~

Nếu `fetchBlocking` chờ network/DB/file, worker có thể dành nhiều thời gian **đợi I/O** thay vì tính toán. Các parallel stream khác và công việc dùng common pool có thể phải cạnh tranh với các worker đang chặn. Khả năng ForkJoinPool bù thread khi tác vụ block có giới hạn và không thể giả định mọi kiểu chờ I/O thông thường đều được runtime nhận diện hoặc bù tự động.

Nếu bài toán chủ yếu là I/O:

- Dùng `ExecutorService` có giới hạn concurrency rõ ràng, hoặc API bất đồng bộ được thiết kế cho I/O.
- Tách phần tải dữ liệu và phần xử lý CPU; có thể dùng parallel stream ở **bước CPU** sau khi dữ liệu đã có.
- Nếu thao tác phải gọi thư viện blocking, kiểm soát số request đồng thời, timeout và áp lực lên downstream thay vì chỉ tăng common parallelism.

`ForkJoinPool.ManagedBlocker` tồn tại cho một số tình huống fork/join biết trước việc blocking; việc đặt một cuộc gọi I/O bất kỳ bên trong `map` không đồng nghĩa đã dùng `managedBlock`.

### Ví dụ tác động chéo

Giả sử hai thành phần chạy đồng thời:

1. Một parallel stream xử lý hàng triệu phần tử và tiêu thụ gần hết CPU.
2. Một tác vụ khác gọi `CompletableFuture.supplyAsync(...)` không truyền executor, nên trong cấu hình thông thường cần worker từ common pool.

Cả hai có thể tăng độ trễ cho nhau. Khi hệ thống có yêu cầu latency/throughput rõ ràng, không nên chỉ xét thời gian xử lý riêng một pipeline; cần quan sát tải chung và thiết kế executor ownership phù hợp.

## 10. Exception, cancellation và việc đợi kết quả

Khi function trong `map` hoặc `filter` ném exception, terminal operation có thể kết thúc bất thường và exception được truyền tới thread gọi, đôi khi có wrapper tuỳ đường thực thi. Không giả định các task của partition khác bị ngắt tức thì ở đúng thời điểm một partition lỗi. Tác vụ đã bắt đầu có thể còn hoàn tất công việc đang thực hiện.

~~~java
// Minh hoạ: terminal operation có thể ném exception.
long total = java.util.stream.LongStream.range(0, 100)
    .parallel()
    .map(n -> {
        if (n == 42) {
            throw new IllegalArgumentException("invalid item");
        }
        return n;
    })
    .sum();
~~~

Dùng `try/catch` ở ranh giới gọi terminal operation và để framework/executor cấp trên quản lý policy lỗi nếu pipeline là một phần của hệ thống lớn.

Một parallel stream không trực tiếp cung cấp `cancel()` kiểu `Future`. Các phép short-circuit như `anyMatch`, `findAny`, `limit` có thể bỏ bớt công việc khi đã đủ điều kiện, nhưng không có bảo đảm mọi lambda đang chạy đều bị dừng ngay. Không dựa vào side effect của pipeline để xác định chính xác phần tử nào đã được truy cập khi một phép toán short-circuit kết thúc.

Nếu đặt parallel stream bên trong `CompletableFuture`:

~~~java
// Đoạn minh họa đặt trong phương thức; nguồn dữ liệu đã có.
java.util.concurrent.CompletableFuture<Long> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> java.util.stream.LongStream.rangeClosed(1, 1_000_000)
            .parallel()
            .sum());
~~~

việc huỷ `result` không đồng nghĩa huỷ chắc chắn mọi fork/join subtask của phép tính đang chạy. Việc chọn executor riêng cho stage ngoài cũng không biến Stream API thành một pipeline có cơ chế huỷ subtask được cam kết. Với quy trình cần deadline, backpressure hoặc điều khiển huỷ chi tiết, hãy dùng abstraction có ownership/cancellation rõ ràng.

## 11. Đo đạc: khi nào parallel stream thật sự nhanh hơn?

Tổng thời gian có thể hình dung gồm:

~~~text
Tổng thời gian parallel
  = chi phí thiết lập/chia việc
  + thời gian xử lý các phần
  + chi phí scheduling/work-stealing
  + chi phí kết hợp/bảo toàn thứ tự
  + thời gian tranh chấp/chờ
~~~

Parallelism đem lại lợi ích khi phép tính mỗi phần tử đủ nặng, nguồn chia tốt, dữ liệu đủ lớn, các phép reduction an toàn, và máy có CPU khả dụng. Ngược lại, pipeline với thao tác cực nhẹ trên vài chục phần tử thường tốn thêm overhead; pipeline lệ thuộc thứ tự cũng khó mở rộng.

Hướng kiểm chứng:

1. Đo **sequential và parallel** với cùng dữ liệu và cùng logic; kiểm tra kết quả trước khi so hiệu năng.
2. Dùng benchmark như **JMH** nếu cần số liệu đáng tin: warm-up JIT, nhiều lượt đo, fork JVM, tránh dead-code elimination và kiểm soát allocation/GC.
3. Chạy cả khi hệ thống **có tải đồng thời**, vì common pool dùng chung; một benchmark trong JVM nhàn rỗi có thể bỏ qua contention quan trọng.
4. Theo dõi CPU usage, allocation, GC, throughput, latency và các số liệu `ForkJoinPool`; metric pool là chỉ dấu, không tự thay thế profiling.
5. Nếu yêu cầu performance quan trọng, thử thay đổi kích thước dữ liệu, loại `Spliterator`, mức parallelism cấu hình từ lúc khởi động và số tiến trình đồng chạy.

Không dùng riêng `System.nanoTime()` quanh một lần chạy rồi kết luận “parallel nhanh hơn x lần”; first-run JIT, cache, GC và scheduling làm kết quả dao động.

## 12. Bảng quyết định và lỗi thường gặp

| Tình huống | Nên làm |
| --- | --- |
| Tính toán CPU nặng trên mảng/range lớn, operations stateless | Thử `parallel()` và benchmark |
| Một vài phần tử, logic rất nhẹ | Ưu tiên sequential đơn giản |
| Nhiều cuộc gọi network/DB blocking | Dùng cơ chế I/O/executor có giới hạn và đo tải |
| Muốn giữ đúng thứ tự phần tử ở đầu ra | Dùng terminal giữ encounter order như `toList()` hoặc `forEachOrdered()` khi cần |
| Muốn ghi vào `ArrayList` dùng chung từ `forEach` | Thay bằng `collect`/`toList` hoặc reduction đúng contract |
| Muốn chỉ định pool của parallel stream theo API chính thức | Stream API không có tham số executor; cân nhắc mô hình task/executor do ứng dụng quản lý |
| Thấy `ForkJoinPool.commonPool-worker-*` trong thread dump | Đây là dấu hiệu pool đang làm việc, không đủ để suy ra mọi stream dùng chung thread |
| Muốn đóng pool sau `parallelStream()` | Không `shutdown()` common pool; nó thuộc runtime |
| Cần “dừng ngay tất cả task” khi một phần tử lỗi | Không giả định short-circuit/exception tự tạo cơ chế cancel hoàn chỉnh |
| Stream cho kết quả sai không ổn định | Kiểm tra shared mutation, stateful lambdas, non-associative reduce và encounter order |

Các lỗi dễ mắc nhất là coi `parallel()` như một nút tăng tốc chắc chắn; nghĩ mỗi stream có pool riêng; đếm tên thread rồi suy ra contract; sửa collection chia sẻ từ `forEach`; đưa I/O chặn vào common pool; và áp đặt thứ tự thực thi vật lý trong khi Java chỉ bảo đảm thứ tự kết quả ở những thao tác có contract phù hợp.

## 13. Ghi nhớ khi áp dụng

**Parallel streams** mô tả cách pipeline có thể được xử lý song song; **ForkJoin common pool** là cơ chế thực thi chia sẻ thường được các triển khai JDK sử dụng phía sau. Work-stealing giúp phân phối task, nhưng hiệu quả còn phụ thuộc `Spliterator`, mức độ độc lập của phép toán, chi phí kết hợp, tải CPU và tranh chấp với công việc khác.

Viết các lambda thuần, dùng reduction/collector đúng contract, tránh biến mutable dùng chung và blocking I/O, kiểm tra bằng benchmark thực tế. Khi cần kiểm soát chính xác thread pool, deadline, huỷ và độ trễ giữa các loại công việc, hãy đưa scheduling vào một API executor/task rõ ràng thay vì dựa vào chi tiết nội bộ của parallel streams.