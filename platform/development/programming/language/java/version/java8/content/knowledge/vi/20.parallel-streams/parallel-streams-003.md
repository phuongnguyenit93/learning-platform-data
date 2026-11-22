# Common ForkJoinPool và tài nguyên dùng chung trong Java Parallel Stream

## Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích common ForkJoinPool, cách fork/join chia và ghép việc, cùng cơ chế work-stealing.
2. Hiểu parallelStream() thường sử dụng tài nguyên thực thi nào trong OpenJDK, và phân biệt hành vi triển khai với cam kết của Stream API.
3. Nhận diện tranh chấp CPU, worker, connection pool, I/O, bộ nhớ và khóa đồng bộ khi nhiều chức năng chạy song song trong cùng JVM.
4. Sử dụng phép toán stateless, non-interfering và collector đúng cách, tránh shared mutable state.
5. Hiểu tác hại của I/O chặn trong một pool dành cho phép tính chia nhỏ và ý nghĩa có giới hạn của ManagedBlocker.
6. Chọn giữa parallelStream(), ExecutorService riêng, ForkJoinPool riêng và virtual threads khi yêu cầu thực tế khác nhau.
7. Quan sát, benchmark, kiểm thử và quản lý lifecycle mà không tác động đến các tác vụ khác.

**Phạm vi phiên bản:** Các khái niệm ForkJoinPool.commonPool và Stream.parallel đã có từ Java 8 và **vẫn còn áp dụng trên JDK hiện hành**. Các chương trình đầy đủ dùng Java 17+ để chạy độc lập; những tính năng có từ Java 21+ được phân biệt rõ. Bài không dạy những API hoặc cách làm đã legacy.

## 1. ForkJoinPool và work-stealing

ForkJoinPool là ExecutorService hỗ trợ kiểu tính toán chia để trị: **fork** một việc lớn thành các task nhỏ; **join** để ghép kết quả. Trong cơ chế *work-stealing*, một worker đã hết việc có thể lấy task từ hàng đợi của worker khác nhằm cân bằng tải.

Ví dụ tính tổng bình phương các số từ 1 đến 8:

~~~text
              [1,2,3,4,5,6,7,8]
                    /     \
            [1,2,3,4]    [5,6,7,8]
             /     \       /    \
          [1,2]   [3,4] [5,6]  [7,8]
             |       |     |      |
           1+4    9+16  25+36  49+64
             \      /      \    /
                30            174
                       |
                      204
~~~

Việc chia task có thể diễn ra theo nhiều mức khác nhau. Sơ đồ chỉ minh họa ý tưởng; Java không hứa sẽ chia thành đúng bốn nhánh hay tạo đúng bốn worker. Phép cộng cho kết quả đúng dù đổi cách nhóm các nhánh trong miền số không tràn.

**Parallelism** là mức song song mục tiêu của pool, không phải lời cam kết mọi thời điểm có bấy nhiêu thread chạy CPU. Số worker đang hoạt động, số task đang chờ và khả năng xử lý thực tế còn phụ thuộc tải, JDK, máy chủ và giới hạn môi trường.

## 2. Common pool là tài nguyên của cả JVM

**ForkJoinPool.commonPool()** trả về common ForkJoinPool: một pool dùng chung trong **cùng một tiến trình JVM**, không tạo mới theo từng lời gọi, từng module, từng request hoặc từng Stream.

~~~java
// Mảnh mã: cần import java.util.concurrent.ForkJoinPool
ForkJoinPool common = ForkJoinPool.commonPool();
~~~

Common pool giúp tái sử dụng worker và giảm chi phí tạo pool riêng cho nhiều tác vụ nhỏ. Đổi lại, nếu nhiều tác vụ dùng chung, chúng sẽ cạnh tranh khả năng thực thi. Common pool trong JVM A không phải pool dùng chung toàn hệ điều hành với JVM B; hai JVM vẫn cạnh tranh CPU vật lý và bộ nhớ máy chủ như các tiến trình khác.

| Khái niệm | Cần hiểu |
|---|---|
| Common pool | ForkJoinPool dùng chung trong một JVM |
| Worker | Thread được pool dùng để xử lý task |
| ForkJoinTask | Đơn vị tính toán có thể fork/join |
| Parallelism | Mức song song mục tiêu, không phải thread count cố định |
| Work-stealing | Worker lấy thêm task để cân bằng tải |
| CPU core | Tài nguyên phần cứng, có thể còn bị tiến trình khác sử dụng |

**Đừng gọi commonPool().shutdown() như thể đây là pool của riêng bạn.** Tài liệu Java chỉ rõ những lần gọi shutdown/shutdownNow không thay đổi trạng thái chạy của common pool; việc cố đóng nó vẫn là thiết kế sai quyền sở hữu. Với pool ứng dụng tự tạo, cần quản lý shutdown theo lifecycle phù hợp.

## 3. Parallel Stream có thực sự chạy trên common pool?

Một pipeline Stream có thể chuyển sang chế độ song song bằng Collection.parallelStream() hoặc BaseStream.parallel():

~~~java
long sum = java.util.stream.LongStream.rangeClosed(1, 1000)
        .parallel()
        .map(n -> n * n)
        .sum();
~~~

Đây là mảnh mã biên dịch được trong một phương thức Java, không phải chương trình độc lập.

Trong những triển khai **OpenJDK** phổ biến, khi gọi parallelStream từ một thread thông thường, việc xử lý thường được chia thành ForkJoinTask và sử dụng **common pool**. Thread gọi cũng có thể trực tiếp tham gia. Tuy nhiên, **hợp đồng Stream API không có tham số Executor**, không cam kết một pool cụ thể, không cố định số task và không cam kết lambda chạy trên một thread nhất định.

Do đó:

- Không suy ra tất cả lambda chạy trên các thread có tên ForkJoinPool.commonPool-worker-*.
- Không suy ra thread gọi luôn đứng ngoài quá trình tính toán.
- Không coi số task là số core, số worker hoặc số phần tử.
- Không dùng Thread.currentThread().getName() làm khóa nghiệp vụ.
- Không dựa vào thứ tự thực thi lambda để suy ra thứ tự kết quả.

Parallel mode ảnh hưởng **cách triển khai xử lý**, còn đúng/sai của phép biến đổi phải theo hợp đồng Stream: behavioral parameter thường phải *stateless* (không dựa trên trạng thái ngoài thay đổi) và *non-interfering* (không sửa nguồn dữ liệu trong lúc đang duyệt).

Với nguồn List có encounter order, những thao tác có cam kết giữ thứ tự phải giữ đúng thứ tự kết quả, dù các lambda có thể được thực hiện theo thứ tự khác nhau. Chẳng hạn map(...).toList() trên List trả kết quả theo encounter order. Stream.toList() có từ Java 16; nó trả List không sửa được.

## 4. Vì sao các tính năng khác có thể ảnh hưởng đến nhau?

Giả sử một JVM vừa phục vụ HTTP, vừa chạy batch job và đồng thời sử dụng CompletableFuture:

~~~text
HTTP request A -> parallelStream() --------\
                                            \
Batch job B ----> parallelStream() ----------> CPU và nhóm worker chung
                                            /   (thường là common pool
Async task C ----> CompletableFuture -------/    trong OpenJDK)
                                                  |
                                            CPU / heap / GC
~~~

Ba công việc có thể đúng riêng lẻ nhưng **cạnh tranh worker, CPU và bộ nhớ**, khiến độ trễ của HTTP request tăng trong lúc batch job nặng chạy. Common pool chỉ là một điểm chia sẻ; nếu các task còn truy cập DB, HTTP hoặc file, mức cạnh tranh tăng ở các tài nguyên đó.

Với các lời gọi CompletableFuture.supplyAsync(...) và những phương thức async không chỉ định Executor, JDK hiện đại thường dùng common pool làm executor mặc định. Oracle Java 25 ghi nhận rõ việc dùng common pool cho phương thức async không có Executor. Các phiên bản và cấu hình cũ có thể có cơ chế fallback khác khi parallelism rất thấp; **không lấy hành vi fallback này làm cách cô lập tài nguyên**.

Nếu cần xác định chính xác nơi tác vụ được submit, truyền Executor:

~~~java
// Mảnh mã, với compute và executor do ứng dụng cung cấp:
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(this::compute, executor);
~~~

**Quan trọng:** Đặt parallelStream bên trong một tác vụ CompletableFuture chạy trên Executor riêng không bảo đảm tất cả task con của Stream cũng dùng Executor đó. Việc một triển khai JDK đôi khi dùng pool của thread hiện hành là chi tiết triển khai, không phải API ổn định để chọn Executor cho Stream.

## 5. Các loại tài nguyên dùng chung thường gây nghẽn

| Tài nguyên | Tình huống | Hệ quả |
|---|---|---|
| CPU | Nhiều tác vụ CPU-bound cùng chạy | CPU bão hòa, context switch, tăng độ trễ |
| Common pool workers | Task xử lý lâu hoặc chặn worker | Task khác có thể phải chờ |
| Heap và GC | Nhiều buffer/List/Map trung gian | Áp lực cấp phát và GC tăng |
| Database connection pool | Nhiều worker gọi JDBC đồng thời | Chờ connection, timeout |
| HTTP connection pool | Nhiều worker gửi request ra ngoài | Chờ kết nối, remote rate-limit |
| synchronized/Lock | Nhiều worker lấy cùng một lock | Tranh chấp khiến pipeline gần như tuần tự |
| Disk/socket I/O | Task chờ dữ liệu | Worker bị chiếm dù CPU có thể rảnh |
| ThreadLocal | State gắn với worker tái sử dụng | Rò hoặc nhầm state giữa task |

Ví dụ một endpoint xử lý nhiều người dùng, mỗi request lại gọi parallelStream để truy vấn DB cho hàng chục ID. Nếu connection pool có 10 kết nối khả dụng, tạo 100 task không tạo 100 kết nối. Nhiều task hơn có thể chỉ làm **hàng đợi mượn connection dài thêm** và tăng nguy cơ timeout.

Không có quan hệ tự động “gấp đôi worker = gấp đôi tốc độ”: tài nguyên giới hạn có thể nằm ở CPU, lock, connection pool, dịch vụ ngoài, memory bandwidth hoặc thuật toán.

## 6. Ví dụ 1 — phép tính CPU thuần và kết quả xác định

Trường hợp phù hợp cho parallel Stream là dữ liệu đủ lớn, có thể chia đều, mỗi phần tử độc lập và công việc CPU tương đối đáng kể. Chương trình nhỏ sau kiểm chứng **ngữ nghĩa**, không dùng làm benchmark.

Tạo file **ParallelCompute.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class ParallelCompute {
    public static void main(String[] args) {
        long sumSquares = LongStream.rangeClosed(1, 10)
                .parallel()
                .map(n -> n * n)
                .sum();

        List<Integer> squares = IntStream.rangeClosed(1, 5)
                .parallel()
                .map(n -> n * n)
                .boxed()
                .toList();

        System.out.println("sumSquares=" + sumSquares);
        System.out.println("squares=" + squares);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~text
javac --release 17 ParallelCompute.java
java ParallelCompute
~~~

Stdout:

~~~text
sumSquares=385
squares=[1, 4, 9, 16, 25]
~~~

- n -> n*n là hàm thuần, không truy cập một biến đếm chung.
- Phép cộng long để tính tổng bình phương không tràn trong ví dụ; với dữ liệu thực cần kiểm tra miền số.
- List được tạo theo encounter order của IntStream.rangeClosed, không theo thứ tự worker hoàn thành phép tính.
- Tập dữ liệu ví dụ quá nhỏ để kết luận parallel nhanh hơn sequential. Trong thực tế, overhead phân hoạch/lập lịch/ghép có thể chiếm phần lớn thời gian.

## 7. Shared mutable state: lỗi an toàn và hiệu năng

Đoạn sau **sai** nếu chạy song song:

~~~java
// PHẢN VÍ DỤ (cần import List, ArrayList, IntStream)
List<Integer> values = new ArrayList<>();
IntStream.range(0, 1000)
        .parallel()
        .forEach(values::add);
~~~

ArrayList không an toàn với nhiều thread cùng thay đổi cấu trúc. Kết quả có thể thiếu dữ liệu, hỏng nội dung hoặc phát sinh lỗi; việc chạy thử vài lần ra đúng 1000 phần tử không chứng minh thiết kế đúng.

### Hãy dùng phép reduction đúng hợp đồng

~~~java
// Mảnh mã; List kết quả không sửa được từ Java 16.
List<Integer> values = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();
~~~

Nếu cần ArrayList mutable cụ thể:

~~~java
// Mảnh mã.
List<Integer> values = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
~~~

Trong collector thông thường không khai báo CONCURRENT, Stream có thể sử dụng **container trung gian riêng cho các phần xử lý**, rồi gộp chúng. Vì vậy một ArrayList dùng đúng qua collector có thể an toàn dù ArrayList tự nó không thread-safe. Đây là điều khác với nhiều thread đồng thời add vào **cùng một ArrayList toàn cục**.

Một AtomicInteger có thể bảo vệ một phép tăng biến đếm; Collections.synchronizedList có thể bảo vệ cập nhật List. Nhưng đồng bộ hóa làm tăng tranh chấp và không tự giải quyết yêu cầu thứ tự nghiệp vụ. Với bài toán đếm/tổng, nên dùng count(), mapToLong(...).sum(), counting(), summingInt() hoặc một collector phù hợp.

**Không sửa nguồn:** đoạn dưới cũng sai đối với một ArrayList nguồn bình thường:

~~~java
// PHẢN VÍ DỤ: sửa nguồn đang được duyệt.
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
source.parallelStream().forEach(n -> source.add(n * 10));
~~~

Non-interference áp dụng cả với Stream tuần tự: không sửa nguồn không concurrent trong khi terminal operation đang chạy.

## 8. Ví dụ 2 — collector thay cho HashMap chia sẻ

Khi tính tổng và đếm theo nhóm, dùng collector để thư viện quản lý trạng thái tích lũy. Không tự viết forEach cập nhật một HashMap chung.

Tạo file **SafeParallelGrouping.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class SafeParallelGrouping {
    record Sale(String id, String region, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("O1", "North", 120),
                new Sale("O2", "South", 50),
                new Sale("O3", "North", 80),
                new Sale("O4", "West", 40),
                new Sale("O5", "South", 70)
        );

        Map<String, Integer> amounts = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)
                ));

        ConcurrentMap<String, Long> counts = sales.parallelStream()
                .unordered()
                .collect(Collectors.groupingByConcurrent(
                        Sale::region,
                        Collectors.counting()
                ));

        System.out.println("amounts=" + amounts);
        System.out.println("counts=" + new TreeMap<>(counts));
    }
}
~~~

Chạy:

~~~text
javac --release 17 SafeParallelGrouping.java
java SafeParallelGrouping
~~~

Stdout:

~~~text
amounts={North=200, South=120, West=40}
counts={North=2, South=2, West=1}
~~~

**Điểm học tập:**

1. groupingBy với TreeMap::new cho kết quả được sắp xếp theo khóa và downstream summingInt cộng tiền trong từng nhóm.
2. groupingByConcurrent trả ConcurrentMap và cho phép concurrent reduction không yêu cầu encounter order; nó có thể cải thiện hiệu năng trong một số workload nhưng không được mặc nhiên coi là nhanh hơn.
3. ConcurrentMap tự nó không hứa thứ tự duyệt, nên chương trình chủ động tạo TreeMap khi in.
4. Nếu kết quả là Map<K, List<T>>, dù Map concurrent, danh sách trong mỗi nhóm **không mặc nhiên an toàn** để ứng dụng sửa đồng thời sau khi collect.
5. Bài toán số học vẫn cần chọn kiểu số không tràn khi dữ liệu thật có giá trị lớn.

## 9. Blocking I/O trong common ForkJoinPool

ForkJoinPool phù hợp với nhiều dạng chia nhỏ công việc CPU. Khi một worker bị chặn do JDBC, HTTP đồng bộ, đọc file lâu, Thread.sleep hoặc synchronized lock, worker đó không thể làm tính toán có ích trong khoảng chờ.

~~~text
worker A: chạy phép tính CPU
worker B: chờ database connection
worker C: chờ response HTTP
worker D: chờ monitor lock
          |
          +-- các task tiếp theo có thể bị chậm
~~~

Đây là sơ đồ hiện tượng, không phải giả định pool có đúng bốn worker.

### ManagedBlocker không phải phép màu

Java có ForkJoinPool.ManagedBlocker và ForkJoinPool.managedBlock(...) để diễn tả một số chờ đồng bộ; pool **có thể** tạo hoặc kích hoạt worker dự phòng khi phù hợp. Java API không hứa bù mọi thao tác I/O chặn. ManagedBlocker cũng không tạo thêm database connection, không vượt qua remote rate-limit và không loại bỏ độ trễ mạng.

Lựa chọn thực tế:

- **CPU-bound, dữ liệu độc lập:** thử Stream tuần tự trước, chỉ chọn parallelStream sau khi kiểm chứng hiệu quả.
- **I/O chặn:** dùng Executor/async API có concurrency giới hạn, timeout, backpressure; tránh đẩy vô hạn task vào pool.
- **Java 21+:** virtual threads phù hợp với nhiều dạng chờ I/O, nhưng không biến parallelStream thành virtual-thread stream và không giúp CPU-bound vượt số core.
- **Công việc pha trộn:** tách phần gọi I/O và phần biến đổi CPU khi cần kiểm soát tài nguyên theo từng loại.

## 10. Đo common pool mà không suy đoán thread

Mảnh mã chẩn đoán:

~~~java
// Cần import java.util.concurrent.ForkJoinPool.
ForkJoinPool pool = ForkJoinPool.commonPool();
int parallelism = pool.getParallelism();
int poolSize = pool.getPoolSize();
int active = pool.getActiveThreadCount();
long queued = pool.getQueuedTaskCount();
long steals = pool.getStealCount();
~~~

Các giá trị là **ảnh chụp phụ thuộc thời điểm và môi trường**, vì vậy không có stdout cố định.

| API | Đo gì | Đừng hiểu nhầm |
|---|---|---|
| getParallelism() | Mức song song mục tiêu | Không phải số thread đang xử lý mọi lúc |
| getPoolSize() | Quy mô worker hiện tại theo pool | Có thể thay đổi theo tải |
| getActiveThreadCount() | Ước lượng worker đang hoạt động | Không phải phép đo đồng bộ tuyệt đối |
| getQueuedTaskCount() | Ước lượng số task chờ trong worker queues | Không bao gồm mọi backlog ứng dụng |
| getStealCount() | Số lần work-steal tích lũy | Không tự chứng minh nhanh/chậm |

Runtime.availableProcessors() cũng phụ thuộc JVM/container/cgroup; không mặc định suy ra số worker chính xác bằng số core trừ một. Khi điều tra performance, nhìn đồng thời CPU, GC, allocation, thời gian chờ connection pool, độ trễ p95/p99 và throughput. Có thể dùng JFR để phân tích runtime, dùng JMH để benchmark microbenchmark có phương pháp; đừng đo nhanh/chậm bằng System.currentTimeMillis quanh một pipeline vài phần tử.

### Cấu hình common parallelism

Common pool có các cơ chế cấu hình với phạm vi toàn JVM. System property java.util.concurrent.ForkJoinPool.common.parallelism tồn tại trong JDK, nhưng tài liệu Java hiện đại khuyến cáo thận trọng khi dùng; một số JDK còn có API điều chỉnh parallelism với ràng buộc về phiên bản/cấu hình. Tăng worker cho một endpoint có thể làm ảnh hưởng các CompletableFuture và phần xử lý khác cùng dùng common pool.

**Không coi cấu hình global là giải pháp đầu tiên** cho nghẽn DB/I/O hoặc cho một pipeline riêng. Hãy quan sát nút thắt trước rồi chọn nơi đặt giới hạn thực sự.

## 11. Ví dụ 3 — Executor riêng cho nhóm tác vụ có ngân sách thực thi

Nếu yêu cầu là nhóm CPU task có giới hạn thread riêng, một ExecutorService được truyền tường minh có ý nghĩa rõ ràng hơn việc bọc parallelStream trong một lambda rồi mong Stream dùng đúng pool đó.

Tạo file **DedicatedExecutorDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

public class DedicatedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<CompletableFuture<Integer>> futures =
                    IntStream.rangeClosed(1, 5)
                            .mapToObj(n ->
                                    CompletableFuture.supplyAsync(
                                            () -> n * n, executor
                                    )
                            )
                            .toList();

            int sumSquares = futures.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("tasks=" + futures.size());
            System.out.println("sumSquares=" + sumSquares);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 DedicatedExecutorDemo.java
java DedicatedExecutorDemo
~~~

Stdout:

~~~text
tasks=5
sumSquares=55
~~~

Giải thích:

- Cả năm CompletableFuture được submit **tường minh** tới executor. Chỉ tạo tối đa hai thread làm việc theo cấu hình fixed thread pool; năm task có thể chờ trong queue.
- Việc tạo task qua IntStream **tuần tự** giúp tránh tự tạo thêm lớp song song không kiểm soát.
- Sau khi submit tất cả task, thread gọi join các kết quả. Không block các worker trong cùng executor để đợi những task mà chỉ executor ấy có thể hoàn thành.
- Ví dụ shutdown pool thuộc sở hữu chương trình. Trong một server, thường nên sở hữu và dùng lại executor theo vòng đời component thay vì tạo pool mới cho mỗi request.
- Fixed thread pool **không đồng nghĩa** hàng đợi task bị chặn kích thước. Với tải lớn phải có backpressure, semaphore, rejected-execution policy hoặc cơ chế giới hạn task đang chờ/đang chạy.

Executor riêng không tạo CPU mới. Nếu có nhiều pool lớn trong cùng JVM, tình trạng oversubscription có thể làm performance xấu đi.

## 12. Ví dụ 4 — ForkJoinPool riêng bằng API fork/join trực tiếp

Nếu cần chủ động chọn một ForkJoinPool, bạn có thể submit ForkJoinTask/RecursiveTask **trực tiếp** thay vì phụ thuộc hành vi pool bên trong Stream API.

Tạo file **DedicatedForkJoinDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class DedicatedForkJoinDemo {
    private static final class SumSquares extends RecursiveTask<Long> {
        private final int from;
        private final int toExclusive;

        SumSquares(int from, int toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            if (toExclusive - from <= 3) {
                long sum = 0;
                for (int n = from; n < toExclusive; n++) {
                    sum += (long) n * n;
                }
                return sum;
            }

            int mid = (from + toExclusive) / 2;
            SumSquares left = new SumSquares(from, mid);
            SumSquares right = new SumSquares(mid, toExclusive);

            left.fork();
            long rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            long result = pool.invoke(new SumSquares(1, 11));
            System.out.println("sumSquares=" + result);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 DedicatedForkJoinDemo.java
java DedicatedForkJoinDemo
~~~

Stdout:

~~~text
sumSquares=385
~~~

- Pool tự tạo có parallelism mục tiêu 2, độc lập với common pool.
- RecursiveTask được **invoke trực tiếp** lên pool đã chọn. Fork/join chia dải [from, toExclusive) rồi ghép tổng kết quả.
- Việc fork một nhánh, tự compute nhánh kia và join giúp hạn chế tạo task không cần thiết; thực tế ngưỡng phân chia nên chọn theo workload.
- Cuối cùng shutdown pool thuộc quyền sở hữu của chương trình.
- Mẫu pool.submit(() -> items.parallelStream()...) có thể có hành vi sử dụng pool khác nhau giữa triển khai; **không coi nó là hợp đồng Executor chính thức của Stream**.

## 13. Các lỗi thường gặp khi chia sẻ tài nguyên

### 13.1. Song song lồng nhau không có ngân sách

~~~java
// Phản ví dụ về cấu trúc có thể gây quá tải:
// requests và process thuộc ứng dụng, không phải chương trình độc lập.
requests.parallelStream().forEach(request ->
        request.items().parallelStream().forEach(this::process));
~~~

Hai lớp parallel có thể làm tăng task, lock contention và overhead. Cần xác định **một ranh giới song song chính** theo workload; không mặc định thêm parallel() ở mọi cấp.

### 13.2. Gọi I/O trong map

~~~java
// Mảnh mã cảnh báo, blockingClient thuộc ứng dụng.
var results = ids.parallelStream()
        .map(blockingClient::fetch)
        .toList();
~~~

Nếu kết nối DB/HTTP có hạn, nhân số task không làm dịch vụ nhanh hơn. Tính tổng thời gian chờ, hạn chế concurrency, dùng timeout và cơ chế backpressure đúng cách.

### 13.3. Dùng ThreadLocal để mang request context

ThreadLocal giữ dữ liệu theo **thread**, không theo phần tử hoặc request. Worker của pool được tái sử dụng, còn các stage của cùng một phần tử không được API cam kết chạy trên cùng thread. Vì vậy không mặc định context trong ThreadLocal sẽ đi theo toàn bộ parallel pipeline. Ưu tiên truyền context tường minh. Nếu dùng ThreadLocal ở hệ thống thread pool, phải thiết kế cleanup và phạm vi sống rõ ràng.

### 13.4. Fire-and-forget và lifecycle

Worker của ForkJoinPool thường là daemon thread. Đừng gửi tác vụ chưa join rồi thoát chương trình với kỳ vọng common pool tự giữ JVM sống đến khi công việc hoàn thành. Với tác vụ cần hoàn tất, cần quản lý Future, join/get hoặc điều phối lifecycle rõ ràng.

### 13.5. Chờ kết quả trong task của pool quá nhỏ

Nếu mọi worker của một executor nhỏ đang chạy task A, mà task A lại block đợi task B chỉ có thể chạy trong **chính executor đó**, bạn có thể tạo deadlock/starvation. ForkJoinPool hỗ trợ một số mẫu join đặc thù, nhưng không biến mọi dạng chờ đồng bộ trở nên an toàn. Tránh future.get()/join() tùy tiện trong những công việc cùng pool; thiết kế dependency và composition rõ ràng.

### 13.6. Cho rằng forEachOrdered loại bỏ mọi rủi ro

forEachOrdered có cam kết thực hiện action theo encounter order, nhưng có thể làm giảm song song hữu ích và không giải quyết tính mutable/shared state ở các giai đoạn trước. Khi mục tiêu là tạo List theo đúng thứ tự, nên dùng map(...).toList() nếu phù hợp.

### 13.7. Bỏ qua ngoại lệ, timeout hoặc cancellation

parallelStream không tự cấp cho mỗi tác vụ I/O timeout, retry, giới hạn số request hay một quy trình hủy hoàn chỉnh. Nếu workflow cần quản lý deadline, hãy cân nhắc Executor/Future và API client hỗ trợ timeout/cancellation.

## 14. Checklist quyết định

Trước khi dùng parallelStream(), hãy trả lời:

1. Dữ liệu có đủ lớn và chia phần hợp lý không? Công việc chủ yếu CPU hay chặn I/O?
2. Lambda có stateless, non-interfering, không sửa nguồn hoặc trạng thái ngoài không?
3. Reduction có identity/combiner associative khi cần và dữ liệu số có thể tràn không?
4. Có yêu cầu encounter order hay cần một collector unordered/concurrent?
5. CPU, worker, memory, DB/HTTP connection, rate-limit và lock là các giới hạn nào?
6. Công việc này có thể ảnh hưởng đến request hoặc job khác trong cùng JVM không?
7. Có cần giới hạn task in-flight hoặc độ dài queue, thời gian chờ và timeout không?
8. Nếu tạo Executor/ForkJoinPool riêng, thành phần nào quản lý vòng đời và shutdown?
9. Có benchmark so sequential/parallel và đo throughput, p95/p99 latency, GC, CPU, connection wait không?
10. Có đang dựa vào tên thread, số worker hay pool nội bộ của parallelStream như một cam kết không?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Common pool có phải một pool mới mỗi khi gọi parallelStream không?

*Đáp án:* Không. Nó là tài nguyên JVM dùng chung trong các tình huống triển khai phổ biến, có thể bị nhiều tác vụ tranh chấp.

**Câu 2.** Có thể khẳng định parallelStream luôn dùng đúng số worker bằng số core không?

*Đáp án:* Không. Stream API không cam kết số worker, tên thread hoặc lịch lập lịch cố định.

**Câu 3.** Vì sao forEach(sharedArrayList::add) song song sai, nhưng collect(toCollection(ArrayList::new)) hợp lệ?

*Đáp án:* Mẫu đầu sửa cùng List mutable từ nhiều thread; collector bình thường quản lý container trung gian và kết hợp các phần theo hợp đồng.

**Câu 4.** Nếu 100 task gọi DB nhưng connection pool chỉ có 10 connection, tăng common parallelism có chắc giúp không?

*Đáp án:* Không. Các task có thể chỉ chờ connection lâu hơn; cần kiểm soát số yêu cầu đồng thời và đo bottleneck thực.

**Câu 5.** Để chắc chắn task dùng pool riêng, có nên chỉ đặt parallelStream bên trong CompletableFuture.supplyAsync(..., executor) không?

*Đáp án:* Không coi đó là cam kết API. Gửi task tường minh bằng Executor, hoặc dùng ForkJoinTask/ForkJoinPool trực tiếp.

**Câu 6.** Virtual threads có giúp xử lý CPU nhanh hơn số core không?

*Đáp án:* Không. Virtual threads chủ yếu giúp mô hình nhiều tác vụ chờ I/O; vẫn cần giới hạn connection và rate-limit.

## Tài liệu tham khảo đang được duy trì

- Oracle Java SE 25 — ForkJoinPool: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- Oracle Java SE 25 — ForkJoinPool.ManagedBlocker: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html
- Oracle Java SE 25 — Stream package: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 25 — CompletableFuture: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 25 — Collectors: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- Oracle Java SE 25 — ExecutorService: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 25 — Thread và virtual threads: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html

**Ghi nhớ:** Common pool giúp tái sử dụng tài nguyên fork/join trong JVM, nhưng parallelStream chỉ đáng dùng khi phép tính đúng hợp đồng, dữ liệu phù hợp và hiệu năng được đo. Với workload có nhu cầu cô lập SLA, giới hạn I/O hoặc quản lý task rõ ràng, hãy dùng Executor/ForkJoinPool theo ranh giới ứng dụng một cách có chủ đích.
