# supplyAsync() không chỉ định executor và nguy cơ dùng chung common pool

## Mục tiêu và phạm vi

Trong ứng dụng Java và Spring, `CompletableFuture.supplyAsync(...)` giúp chạy một `Supplier<T>` ở nơi khác và trả về `CompletableFuture<T>` để caller tiếp tục công việc. Nhưng **không truyền `Executor`** không có nghĩa là Spring tự chọn thread pool của ứng dụng. Trong Java 17, overload một tham số **mặc định gửi task vào `ForkJoinPool.commonPool()`**, một tài nguyên **dùng chung trong JVM**.

Đây là điểm quan trọng khi ghép nhiều `CompletableFuture`: công việc vô tình chia sẻ common pool có thể tranh chấp worker với công việc của thư viện hoặc thành phần khác, đặc biệt khi task **blocking I/O**, chạy lâu hoặc khi lưu lượng tăng đột biến.

Sau bài này, bạn có thể:

- Phân biệt chính xác `supplyAsync(supplier)` và `supplyAsync(supplier, executor)`, kể cả ngoại lệ của JDK khi common pool không có mức song song tối thiểu.
- Giải thích `ForkJoinPool.commonPool()` là pool dùng chung toàn JVM, không phải pool riêng cho mỗi request, bean Spring hay lần gọi `supplyAsync`.
- Phân tích tác động của CPU-bound work, blocking I/O, task dài, quá nhiều future và các bước chaining đối với tài nguyên chung.
- Cấu hình một `ThreadPoolTaskExecutor` Spring rồi **truyền tường minh** vào `supplyAsync` và những stage `...Async` cần điều phối.
- Kiểm tra thread thực thi bằng tên thread/metrics mà không viết bài test phụ thuộc tên worker cố định của common pool.
- Phân biệt lỗi trong `Supplier`, lỗi **rejection tại thời điểm submit**, timeouts, cancellation và context propagation.
- Chọn cách kết hợp `CompletableFuture` an toàn, dễ giám sát, có giới hạn tài nguyên và vòng đời phù hợp production.

**Phiên bản chạy ví dụ:** Java 17+; ví dụ Spring dùng **Spring Framework 6.1.3**, Maven và Java 17+. Tài liệu kỹ thuật được đối chiếu theo Javadoc Java SE 17 và tài liệu Spring. Trọng tâm là cơ chế thực thi và kiểm soát tài nguyên, không phải cách sử dụng các API nội bộ hoặc thay đổi toàn cục của JVM.

## 1. Hai overload có vẻ giống nhau nhưng khác nơi chạy

`CompletableFuture` có hai phương thức tĩnh:

~~~java
// Chữ ký API rút gọn — không phải Java class độc lập.
static <U> CompletableFuture<U> supplyAsync(Supplier<U> supplier);

static <U> CompletableFuture<U> supplyAsync(
        Supplier<U> supplier, Executor executor);
~~~

Với overload thứ nhất, `Supplier.get()` được chạy trên cơ chế thực thi bất đồng bộ **mặc định của JDK**. Theo Javadoc Java 17, các async methods không nhận `Executor` được thực thi bởi `ForkJoinPool.commonPool()`, **trừ trường hợp** common pool không hỗ trợ mức song song ít nhất 2: khi đó `CompletableFuture` tạo **một thread mới cho mỗi task** tương ứng. Vì vậy nói “luôn có một worker mang tên `ForkJoinPool.commonPool-worker-*`” là không chính xác cho mọi JVM.

Overload thứ hai dùng chính `Executor` được truyền. Trong Spring, `ThreadPoolTaskExecutor` triển khai `Executor`, nên có thể dùng trực tiếp làm tham số thứ hai. Nó **không được chọn tự động** chỉ vì ứng dụng đã khai báo một `TaskExecutor` bean.

Ví dụ minh họa:

~~~java
// Fragment, giả sử ioExecutor là Executor đã được cấu hình.
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A"); // executor mặc định

CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", ioExecutor); // chọn rõ
~~~

Hai lời gọi cùng trả `CompletableFuture<String>`, nhưng **tài nguyên thực thi khác nhau**. Việc kiểm soát queue, thread name, số worker, thread context và metrics phụ thuộc executor thực sự nhận task, không phụ thuộc kiểu Future trả về.

| Tiêu chí | `supplyAsync(supplier)` | `supplyAsync(supplier, executor)` |
| --- | --- | --- |
| Nơi chạy mặc định | `ForkJoinPool.commonPool()` của JVM; có ngoại lệ parallelism nhỏ | Executor bạn cung cấp |
| Có dùng Spring `TaskExecutor` bean đã khai báo không? | **Không tự động** | Có nếu bạn **truyền chính bean đó** |
| Giới hạn concurrency | Theo chính sách common pool và tài nguyên JVM | Theo cấu hình executor riêng |
| Tách biệt tải của nghiệp vụ | Không, chia sẻ với code khác dùng common pool | Có thể tách riêng theo loại workload |
| Thread name / metrics / shutdown | Phụ thuộc common pool | Có thể chủ động cấu hình, quan sát và quản lý |
| Nguy cơ tác vụ blocking chiếm worker chung | Có | Có thể khống chế bằng pool riêng và giới hạn downstream |
| Exception của Supplier | Future hoàn tất thất bại | Future hoàn tất thất bại |
| Executor từ chối nộp | Thường không do queue ứng dụng Spring | Có thể ném `RejectedExecutionException`/Spring `TaskRejectedException` ngay |

**Phân biệt:** `CompletableFuture.completedFuture(value)` không nộp task chạy bất đồng bộ; nó tạo future **đã hoàn tất**. `CompletableFuture.supplyAsync(...)` mới lập lịch `Supplier` chạy theo một executor. Một `CompletableFuture` tồn tại không tự chứng minh task được chạy ở thread khác.

## 2. ForkJoinPool.commonPool là gì?

`ForkJoinPool` là executor của JDK được thiết kế để hỗ trợ chia nhỏ và xử lý nhiều công việc song song, có cơ chế work-stealing. `ForkJoinPool.commonPool()` là một **instance dùng chung** trong quá trình chạy JVM. Nhiều thành phần gọi các API bất đồng bộ không chỉ định executor có thể đồng thời đưa công việc vào đây.

~~~text
Module báo cáo                Module thông báo             Thư viện khác
       |                            |                           |
       | supplyAsync(supplier)      | runAsync(runnable)        | thenApplyAsync(fn)
       v                            v                           v
       +----------------------------+---------------------------+
                                    |
                             commonPool (JVM)
                                    |
                  workers thực thi nhiều loại task chung
                                    |
                 một task chậm có thể ảnh hưởng task khác
~~~

Điều này không nghĩa rằng mọi task trong common pool **luôn chạy tuần tự**: pool có nhiều workers và work-stealing. Vấn đề là **chia sẻ giới hạn tài nguyên** và khó cô lập, dự đoán độ trễ khi các module có tải khác nhau.

### Vì sao dùng chung đôi khi vẫn hợp lý?

Với một lượng nhỏ các tính toán **CPU-bound**, ngắn, độc lập, không yêu cầu pool riêng và không chứa I/O chặn lâu, common pool có thể là lựa chọn đơn giản. JDK đã thiết kế `CompletableFuture` để người dùng không nhất thiết tự tạo executor cho mọi tác vụ.

Nhưng ở một dịch vụ production, hãy đánh giá **khối lượng công việc, mức chặn, khả năng cùng tồn tại với các module khác, SLA và yêu cầu điều phối**. Không có quy tắc rằng mọi `supplyAsync` đều nguy hiểm; rủi ro xuất hiện khi mặc định dùng tài nguyên chung **mà không cân nhắc tải và trách nhiệm**.

### Kiểm tra common pool, không đoán từ số lõi

~~~java
int parallelism = ForkJoinPool.getCommonPoolParallelism();
System.out.println("commonParallelism=" + parallelism);
~~~

Đây là fragment cần import `java.util.concurrent.ForkJoinPool`. Kết quả phụ thuộc cấu hình JVM và môi trường, vì vậy không có stdout số cố định. `getCommonPoolParallelism()` trả **mức song song mục tiêu**, không phải số thread đang chạy ở thời điểm đó và không phải con số tối đa mọi task ứng dụng có thể đồng thời hoàn tất.

Một số tham số hệ thống ảnh hưởng common pool, chẳng hạn `java.util.concurrent.ForkJoinPool.common.parallelism`. Nhưng đây là **điều chỉnh phạm vi JVM** và có thể ảnh hưởng các thư viện khác; đừng dùng việc tăng tham số toàn cục làm cách xử lý đầu tiên cho một workload cần cô lập.

## 3. Rủi ro khi không truyền Executor

### 3.1. Blocking I/O có thể chiếm các worker chung

Giả sử `Supplier` gọi HTTP, JDBC hoặc một SDK đồng bộ:

~~~java
// Phản ví dụ kiến trúc: client.fetch(id) là lời gọi chặn.
// Mã chỉ minh họa, không phải chương trình độc lập.
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> client.fetch(id));
~~~

Nếu lời gọi `fetch` chặn lâu, worker thực thi nó bị giữ trong thời gian đó. Khi nhiều task tương tự được nộp vào common pool, việc xử lý các tác vụ CPU-bound ngắn khác có thể bị **trễ**. `ForkJoinPool` có những cơ chế hỗ trợ một số tình huống blocking (ví dụ managed blocking), nên không nên khẳng định nó **không bao giờ bù worker**. Nhưng thư viện HTTP/JDBC thông thường không tự động cung cấp bảo đảm bù tài nguyên theo nhu cầu nghiệp vụ.

**Cách sửa thông dụng:** truyền executor dành cho I/O có giới hạn concurrency và đo tài nguyên downstream:

~~~java
// ioExecutor là Executor/ThreadPoolTaskExecutor được cấu hình.
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> client.fetch(id),
                ioExecutor
        );
~~~

Pool riêng cũng có thể quá tải, vì vậy cần quan tâm `maxPoolSize`, `queueCapacity`, HTTP timeout, connection pool của database và cơ chế từ chối task. Tách executor **không làm một API đồng bộ trở thành non-blocking I/O**; nó chỉ chọn nơi giữ các worker chờ I/O.

### 3.2. Hai module có thể ảnh hưởng nhau mà không biết

Một tác vụ gửi email chậm và một tác vụ tính toán ngắn có thể cùng dùng common pool nếu cả hai sử dụng `supplyAsync(...)` mặc định. Module tính toán không nhìn thấy cấu hình của module email, nhưng vẫn chia sẻ năng lực thực thi. Khi đo latency tăng, developer dễ tập trung sai vào thuật toán của module tính toán.

Tách executor giúp đặt giới hạn và chỉ số riêng: tên thread, active workers, queue depth, rejection rate, task waiting time, p95/p99 latency. Tuy nhiên, ngay cả hai executor riêng vẫn **chia sẻ CPU, bộ nhớ và downstream** của máy; đó là cô lập ở tầng lập lịch, không phải phân vùng tài nguyên tuyệt đối.

### 3.3. “Chạy async” không tương đương không bị chậm

`supplyAsync` trả một `CompletableFuture` sớm, nhưng nếu caller gọi ngay `join()`, caller vẫn chờ kết quả:

~~~java
// Fragment minh họa cách vô tình biến async thành blocking.
String value = CompletableFuture
        .supplyAsync(() -> expensiveOperation())
        .join();
~~~

Không chỉ định executor khiến tác vụ vào cơ chế mặc định; `join()` làm caller đợi. Nếu code thực thi trong request thread, latency của request vẫn có thể kéo dài. Cân nhắc giữ Future và tiếp tục công việc độc lập, hoặc trả `CompletableFuture` lên tầng hỗ trợ asynchronous response nếu framework phù hợp.

### 3.4. Quá nhiều Future không tạo thêm năng lực CPU

Gửi 100.000 `supplyAsync` không biến 8 lõi CPU thành 100.000 lõi. Tác vụ có thể chờ lâu, dùng bộ nhớ và gây áp lực lên CPU/GC. Nếu work là I/O blocking, số worker và khả năng phục vụ phụ thuộc vào executor và downstream. Hãy quản lý concurrency theo **khả năng hệ thống**, không chỉ đếm số future.

Không nên tạo một `newFixedThreadPool` mới **mỗi request** để né common pool: cách đó gây tràn thread, mất khả năng dùng chung pool đúng cách và phức tạp hóa shutdown. Thay vì thế, dùng **executor bean dùng chung theo loại workload**, được tạo một lần trong Spring.

## 4. Bước tiếp theo của CompletableFuture có tự kế thừa executor không?

**Không.** Việc bạn nộp bước đầu bằng `supplyAsync(supplier, ioExecutor)` không tạo ra quy tắc rằng **mọi stage sau này tự động chạy trên `ioExecutor`**.

| Stage | Có truyền Executor? | Thread thực hiện theo hợp đồng |
| --- | --- | --- |
| `thenApply(fn)` | Không có overload Executor (non-async) | Có thể chạy ở thread hoàn tất stage trước hoặc thread gọi completion |
| `thenCompose(fn)` | Non-async | Có thể chạy ở thread hoàn tất hoặc gọi completion |
| `thenApplyAsync(fn)` | Không | Dùng default asynchronous execution facility, thường là common pool |
| `thenApplyAsync(fn, ioExecutor)` | Có | Được gửi tới `ioExecutor` |
| `thenComposeAsync(fn, ioExecutor)` | Có | Phần callback composition được gửi tới `ioExecutor`; future do hàm trả về có lifecycle riêng |
| `handleAsync(fn)` | Không | Dùng default async execution facility |
| `handleAsync(fn, ioExecutor)` | Có | Được gửi tới `ioExecutor` |

Ví dụ:

~~~java
// Fragment có biến ioExecutor kiểu Executor.
CompletableFuture<String> first =
        CompletableFuture.supplyAsync(() -> "spring", ioExecutor);

// Không cam kết tiếp tục dùng ioExecutor:
CompletableFuture<String> second =
        first.thenApplyAsync(String::toUpperCase);

// Yêu cầu stage tiếp tục được lên lịch trên ioExecutor:
CompletableFuture<String> third =
        first.thenApplyAsync(String::toUpperCase, ioExecutor);
~~~

**Điểm tinh tế:** `thenApply` **không có chữ Async** có thể chạy ngay tại thread đăng ký callback nếu future đã hoàn tất, hoặc trên thread hoàn tất future, tùy timing. Vì vậy không thiết kế nghiệp vụ dựa vào giả định cố định “`thenApply` chắc chắn ở worker Spring”. Với stage `...Async` mà context, metrics hoặc pool isolation quan trọng, hãy truyền executor tường minh.

Mặt khác, không cần chuyển mọi phép tính nhỏ sang thread khác. Một `thenApply` biến đổi chuỗi rất nhanh thường có chi phí thấp; dùng `thenApplyAsync(..., executor)` khi bạn thật sự muốn **scheduling boundary** và kiểm soát nơi chạy.

## 5. Ví dụ Java 17+ chạy độc lập: mặc định và executor tường minh

Chương trình sau minh họa hai hướng:

- Tác vụ mặc định tạo kết quả `default-ok`; **nơi chạy** được quy định bởi Javadoc `supplyAsync`, không cần gán cứng tên thread.
- Executor riêng cấp tên `business-*`. Cả task đầu và stage `thenApplyAsync(..., businessPool)` đều dùng executor này.
- `Supplier` ném exception; future hoàn tất lỗi và `handle` đọc cause.

Lưu thành `SupplyAsyncExecutorDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class SupplyAsyncExecutorDemo {

    public static void main(String[] args) throws Exception {
        AtomicInteger ids = new AtomicInteger();

        ExecutorService businessPool = Executors.newFixedThreadPool(
                2,
                task -> {
                    Thread worker = new Thread(task);
                    worker.setName("business-" + ids.incrementAndGet());
                    return worker;
                }
        );

        try {
            // Không truyền executor: dùng default async facility.
            CompletableFuture<String> implicit =
                    CompletableFuture.supplyAsync(() -> "default-ok");

            // Truyền executor tường minh cho cả task và stage async.
            CompletableFuture<String> explicit =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            businessPool
                    ).thenApplyAsync(
                            threadName -> "dedicated="
                                    + threadName.startsWith("business-"),
                            businessPool
                    );

            // Lỗi xảy ra trong Supplier đi vào CompletableFuture.
            CompletableFuture<Integer> failed =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("bad-input");
                    }, businessPool);

            System.out.println("default=" + implicit.join());
            System.out.println(explicit.join());

            String error = failed.handle((value, throwable) -> {
                if (throwable == null) {
                    return "none";
                }
                Throwable root = throwable instanceof CompletionException
                        ? throwable.getCause() : throwable;
                return root.getClass().getSimpleName()
                        + ":" + root.getMessage();
            }).join();

            System.out.println("error=" + error);
        } finally {
            businessPool.shutdown();
            if (!businessPool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                businessPool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac SupplyAsyncExecutorDemo.java
java SupplyAsyncExecutorDemo
~~~

Các dòng chương trình in (không tính log công cụ ngoài):

~~~text
default=default-ok
dedicated=true
error=IllegalArgumentException:bad-input
~~~

**Vì sao không in tên thread từ task mặc định?** Vì tên thread, số worker và nhánh fallback khi common pool có mức song song thấp **phụ thuộc JVM/môi trường**. Nếu cần debug, có thể cho supplier trả `Thread.currentThread().getName()` và ghi log **như dữ liệu quan sát**, không assert một chuỗi tên cố định.

**Vì sao `dedicated=true` chắc chắn?** `businessPool` dùng thread factory đặt tên `business-1`, `business-2`, và stage đầu trả về tên của chính thread đó. `thenApplyAsync(..., businessPool)` vẫn được gửi tới cùng pool. Giá trị boolean được tính từ tên thread thu được, không phụ thuộc worker nào chạy stage.

**Vì sao `error` có `IllegalArgumentException`?** Exception trong supplier không được ném đồng bộ về dòng tạo future; future hoàn tất **exceptionally**. `handle` đọc throwable, gỡ lớp `CompletionException` khi có, rồi tạo chuỗi kết quả.

`shutdown()` chỉ áp dụng cho **businessPool tự tạo**. Chương trình **không shutdown common pool toàn JVM**; việc tự đóng common pool không phải biện pháp dọn dẹp phù hợp cho một module ứng dụng.

## 6. Minh họa tranh chấp một executor dùng chung (không tác động common pool)

Để hiểu tình huống “task dài làm task ngắn phải chờ”, ta dùng một executor **chỉ có 1 worker** do ví dụ tự tạo. Đây là **mô hình mô phỏng sự chia sẻ tài nguyên**, không phải khẳng định common pool thực tế cũng luôn chỉ có một worker, hay hoàn toàn giống cách `ForkJoinPool` lên lịch.

Lưu thành `SharedExecutorContentionDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class SharedExecutorContentionDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService shared = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> slow =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        }
                        return "slow-finished";
                    }, shared);

            started.await(); // worker duy nhất đang giữ task slow

            CompletableFuture<String> quick =
                    CompletableFuture.supplyAsync(
                            () -> "quick-finished", shared);

            System.out.println("quickBeforeRelease=" + quick.isDone());
            release.countDown();
            System.out.println("slow=" + slow.join());
            System.out.println("quick=" + quick.join());
        } finally {
            release.countDown();
            shared.shutdown();
            if (!shared.awaitTermination(5, TimeUnit.SECONDS)) {
                shared.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac SharedExecutorContentionDemo.java
java SharedExecutorContentionDemo
~~~

Đầu ra:

~~~text
quickBeforeRelease=false
slow=slow-finished
quick=quick-finished
~~~

Task slow giữ worker theo latch; quick được gửi vào **cùng executor**, nhưng chưa có worker rảnh, nên chưa thể hoàn tất trước khi main mở latch. Sau đó cả hai task hoàn tất. `quick.isDone()` trước `release.countDown()` là `false` bởi pool có đúng một worker và slow còn đang giữ nó.

Thí nghiệm này **không sử dụng hoặc chỉnh sửa common pool**, tránh việc một bài demo làm chậm những thư viện khác trong cùng JVM. Nó giúp hiểu nguyên lý chia sẻ tài nguyên; còn `ForkJoinPool.commonPool()` có nhiều worker và work-stealing nên cần đánh giá bằng metrics và workload thật, không suy luận tốc độ chính xác từ thí nghiệm một worker.

## 7. Tích hợp Spring: truyền ThreadPoolTaskExecutor tường minh

Spring `ThreadPoolTaskExecutor` vừa đóng vai trò `TaskExecutor`, vừa có thể truyền như một `java.util.concurrent.Executor` cho `CompletableFuture.supplyAsync(supplier, executor)`. Khuyến nghị là cấu hình **bean dùng chung** theo loại workload, ví dụ `ioExecutor` cho các công việc I/O đồng bộ có giới hạn.

### 7.1. Dự án Maven Spring Framework 6.1.3

Ví dụ sau dùng Spring Framework **thuần**, không yêu cầu Spring Boot, `@EnableAsync` hay Spring AOP proxy: gọi trực tiếp `CompletableFuture.supplyAsync` với executor đã được inject. Cấu trúc:

~~~text
spring-supply-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── IoExecutorConfig.java
                ├── DocumentService.java
                └── SpringSupplyAsyncDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-supply-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringSupplyAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/IoExecutorConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class IoExecutorConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("io-");
        return pool; // Spring container quản lý init/shutdown
    }

    @Bean
    public DocumentService documentService(
            @Qualifier("ioExecutor") ThreadPoolTaskExecutor executor) {
        return new DocumentService(executor);
    }
}
~~~

Tệp `src/main/java/demo/DocumentService.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class DocumentService {

    private final Executor executor;

    public DocumentService(Executor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> load(String documentId) {
        return CompletableFuture.supplyAsync(() -> {
            boolean isolated = Thread.currentThread()
                    .getName().startsWith("io-");
            return "document:" + documentId + "|isolated=" + isolated;
        }, executor);
    }
}
~~~

Tệp `src/main/java/demo/SpringSupplyAsyncDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class SpringSupplyAsyncDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             IoExecutorConfig.class)) {

            DocumentService service =
                    context.getBean(DocumentService.class);

            System.out.println(service.load("A42").join());
        }
    }
}
~~~

Chạy trong thư mục `spring-supply-demo`:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra do Java in:

~~~text
document:A42|isolated=true
~~~

**Vì sao ví dụ này chạy qua executor Spring?** Method `DocumentService.load` **truyền trường `executor`** vào overload hai tham số của `supplyAsync`; trường đó được nhận từ bean `ioExecutor` do Spring container quản lý. `ThreadPoolTaskExecutor` tạo worker với tiền tố tên `io-`. Khi supplier chạy, nó kiểm tra chính thread hiện hành và trả `isolated=true`.

Không có `@Async` trên `DocumentService.load`, vì bài này chủ động dùng **Java CompletableFuture API** thay vì proxy-based asynchronous method invocation của Spring. Không cần `@EnableAsync` để gọi trực tiếp `supplyAsync(..., executor)`. `try-with-resources` đóng Spring context, từ đó container dọn executor bean.

**Đừng sao chép thông số pool vào production một cách máy móc.** `core=2`, `max=4`, `queueCapacity=20` chỉ làm rõ khả năng giới hạn số worker và hàng đợi. Cần hiệu chỉnh theo tải, độ dài task, số kết nối downstream, timeout và SLA.

### 7.2. Dùng interface TaskExecutor trong service

`org.springframework.core.task.TaskExecutor` **kế thừa `java.util.concurrent.Executor`**, nên có thể truyền trực tiếp làm tham số thứ hai của `CompletableFuture.supplyAsync`, dù interface Spring chỉ cần `execute(Runnable)`:

~~~java
// Fragment khi đã inject taskExecutor kiểu TaskExecutor:
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ok", taskExecutor);
~~~

Nếu biến chỉ có kiểu `TaskExecutor`, bạn không thể gọi `taskExecutor.submitCompletable(...)` vì đây là method của `AsyncTaskExecutor`, nhưng **`supplyAsync(..., taskExecutor)` vẫn hợp lệ** vì chỉ cần `Executor`. Đây là cách hữu ích khi tích hợp với Spring 5.x, nơi `submitCompletable` chưa có.

**Cẩn thận:** Implementation `SyncTaskExecutor` chạy task **ngay trên caller thread**; nếu bạn truyền một executor đồng bộ, future có thể hoàn tất ngay nhưng việc `supplyAsync` đã thực thi đồng bộ. Không suy luận “không chặn caller” chỉ từ kiểu `CompletableFuture`. Kiểm tra implementation thực của bean.

## 8. @Async và supplyAsync không tự chọn executor giống nhau

`@Async` của Spring dùng cơ chế interceptor/proxy khi application context bật `@EnableAsync`. Executor của `@Async` có thể được chọn bởi annotation `@Async("name")`, cấu hình `AsyncConfigurer` hoặc Spring bean resolution phù hợp. Trong khi đó, `CompletableFuture.supplyAsync(supplier)` là lời gọi **static của JDK**, không đọc `@Async` hay Spring configuration.

Một phản ví dụ:

~~~java
// Fragment trong Spring service, giả sử đã bật @EnableAsync:
@Async("springExecutor")
public CompletableFuture<String> calculate() {
    return CompletableFuture.supplyAsync(
            () -> blockingLookup());
}
~~~

Đoạn này **không phải chương trình độc lập**; cần `blockingLookup()` và bean `springExecutor`. Method được Spring `@Async` gửi vào `springExecutor`, **nhưng** ngay trong method lại gọi `supplyAsync` **không truyền executor**. Vì vậy **Supplier bên trong** được gửi tiếp đến common pool (hoặc nhánh fallback của JDK). Việc đã có `@Async("springExecutor")` **không khiến inner supplyAsync tự kế thừa pool Spring**.

Thường nên chọn một trong hai chiến lược rõ ràng:

1. **Dùng `@Async("springExecutor")`:** target method tính toán trong worker Spring rồi trả `CompletableFuture.completedFuture(result)`, để proxy đại diện cho việc chạy bất đồng bộ.
2. **Dùng `CompletableFuture.supplyAsync(supplier, springExecutor)`:** method bình thường (không cần `@Async`) trả future được nộp trực tiếp đến executor lựa chọn.

Nếu thật sự cần cả hai tầng scheduling, giải thích lý do bằng kiến trúc và giới hạn tài nguyên; đừng vô tình tạo **double scheduling** sang common pool rồi đoán sai thread nào đang chạy I/O.

## 9. Thread context: transaction, MDC, SecurityContext, ThreadLocal

Spring thường có dữ liệu gắn với **thread hiện tại** như log MDC, `SecurityContext`, request attributes và transaction context. Chuyển công việc sang common pool không tự động mang tất cả dữ liệu đó theo. Một số framework có cơ chế propagation riêng; tùy version/config, không thể chỉ giả định chúng có sẵn.

Các rủi ro:

- **Log mất correlation ID:** MDC được cài trong request thread nhưng không thấy trong worker, khiến trace phân tán.
- **SecurityContext trống hoặc không đúng:** nếu framework áp dụng per-thread security context và bạn không truyền, kiểm tra quyền trong worker có thể thiếu thông tin.
- **Transaction không trải theo async task:** một transaction gắn với caller thread không tự mở rộng sang worker. Task phải có transaction boundary thích hợp nếu truy cập database.
- **ThreadLocal rò rỉ dữ liệu:** nếu tự gắn context lên pool worker mà không dọn `finally`, worker được tái sử dụng có thể giữ context cũ sang task khác.

Cách áp dụng: **truyền thông tin nghiệp vụ bất biến một cách tường minh** khi có thể; nếu cần context propagation, dùng cơ chế được framework hỗ trợ, `TaskDecorator`, hoặc executor wrapper phù hợp. Với `ThreadPoolTaskExecutor.setTaskDecorator(...)`, chú ý decorator có thể nhận một task wrapper do `CompletableFuture` tạo, không nhất thiết nguyên `Supplier`; test end-to-end việc context được đặt **và dọn** ở đúng lúc.

Không điều chỉnh context của **common pool worker** bằng cách lưu một `ThreadLocal` toàn cục như giải pháp nhanh; worker có thể phục vụ những phần code khác.

## 10. Exception, rejection, timeout và cancellation

### 10.1. Lỗi trong Supplier: Future hoàn tất exceptionally

Nếu `Supplier.get()` ném `IllegalArgumentException` hoặc exception runtime khác **sau khi được executor nhận**, `CompletableFuture` hoàn tất thất bại.

~~~java
CompletableFuture<Integer> failed =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalArgumentException("invalid");
        }, executor);

// Fragment với executor kiểu Executor đã có.
CompletableFuture<Integer> recovered =
        failed.exceptionally(error -> -1);
~~~

Nếu gọi `failed.join()` mà không phục hồi, Java thường ném `CompletionException` chứa cause gốc; `failed.get()` có thể ném `ExecutionException` (checked). Dùng `handle` hoặc `exceptionally` để chuyển sang giá trị dự phòng khi **nghiệp vụ cho phép**, không tự động nuốt mọi lỗi.

`Supplier<T>` khác `Callable<T>` ở chỗ `Supplier.get()` **không khai báo checked exceptions**. Nếu Supplier thực hiện I/O ném checked exception, bạn phải bắt và chuyển đổi hoặc thiết kế API tương thích; không trực tiếp ném checked exception từ lambda không được khai báo.

### 10.2. Rejection tại thời điểm nộp: chưa có Future

Với `CompletableFuture.supplyAsync(supplier, executor)`, executor được truyền có thể **từ chối** task ngay lúc gọi `execute` bên dưới. Ví dụ khi `ThreadPoolTaskExecutor` đầy hoặc đã shutdown, lời gọi có thể ném **`TaskRejectedException`** (subclass của `RejectedExecutionException`) **trước khi trả Future**. Vì thế `future.exceptionally(...)` không xử lý được lời gọi chưa tạo ra Future.

~~~java
// Fragment trong service có biến ioExecutor kiểu ThreadPoolTaskExecutor.
// Method bao quanh có return type CompletableFuture<String>.
try {
    return CompletableFuture.supplyAsync(
            () -> loadFromRemote(), ioExecutor);
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Quyết định phản hồi quá tải / fallback theo hợp đồng nghiệp vụ.
    return CompletableFuture.failedFuture(ex);
}
~~~

`CompletableFuture.failedFuture(ex)` có từ Java 9+, nên hợp lệ trên Java 17. Ở đây biến rejection đồng bộ thành một future lỗi **có chủ đích** để tầng gọi vẫn có cùng kiểu trả về. Không phải trường hợp nào cũng nên làm vậy: một API HTTP đồng bộ có thể cần fail fast, còn một API trả Future có thể mong một failed future. Quan trọng là **không lờ đi rejection**.

### 10.3. Timeout của Future không tự dừng I/O

~~~java
// Fragment khi đã có future và các import TimeUnit:
future.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` khiến Future hoàn tất exceptionally nếu không có kết quả đúng hạn, **nhưng không bảo đảm dừng Supplier hoặc network request đã khởi chạy**. `completeOnTimeout` cũng chỉ cung cấp kết quả fallback khi quá hạn; I/O thực sự có thể tiếp tục và gây side effect.

`CompletableFuture.cancel(true)` về hợp đồng chủ yếu là **exceptional completion**; `mayInterruptIfRunning` không có tác dụng ngắt worker trực tiếp như nhiều implementation của `FutureTask`. Để kiểm soát lifetime của I/O, thiết lập timeout của HTTP client, database, queue và cancellation hợp tác ở tầng tài nguyên.

### 10.4. Đừng đợi phụ thuộc ngay trong cùng pool nhỏ

Một task A chạy trên executor một worker, lại gửi task B đến **cùng executor** rồi gọi `B.join()`. A giữ worker duy nhất để đợi B, B nằm trong queue không có worker để chạy → **thread-starvation deadlock**. Đừng dùng `supplyAsync` hoặc common pool như phép màu loại bỏ mọi deadlock. Tách các bước thành `thenCompose`/`thenCombine` hoặc thiết kế executor và ranh giới chờ phù hợp.

## 11. Chọn executor theo workload và đo lường

| Workload / yêu cầu | Hướng xử lý |
| --- | --- |
| Tính toán CPU-bound, ít task, độc lập, ngắn | Common pool có thể chấp nhận nếu không cần isolation; đo trước khi quyết định |
| Tính toán CPU-bound quan trọng, có SLA riêng | Executor riêng với concurrency giới hạn, tránh tranh chấp ngoài ý muốn |
| Blocking I/O: HTTP/JDBC/SDK đồng bộ | Executor I/O riêng có giới hạn, timeout thực tế ở downstream |
| Nhiều request/tenant có mức ưu tiên khác nhau | Cân nhắc pool/rate limit/semaphore/queue theo workload và trách nhiệm |
| Công việc rất ngắn, stage chỉ biến đổi giá trị | `thenApply` có thể đủ, không nhất thiết reschedule |
| Stage async cần context hoặc pool cụ thể | `thenApplyAsync(fn, executor)`, `handleAsync(fn, executor)`, v.v. |
| Spring `@Async` dùng executor đã cấu hình | Gọi method qua proxy; đừng mặc định inner `supplyAsync` kế thừa pool |
| Task có thể không được mất | Durable queue/outbox và acknowledgment; Future/ThreadPool không phải hàng đợi bền vững |

### Giám sát

- Với Spring `ThreadPoolTaskExecutor`, theo dõi `getPoolSize()`, `getActiveCount()` và `getQueueSize()` theo thời gian, không chỉ một snapshot.
- Đo **thời gian chờ vào queue**, thời gian chạy task, throughput, rejection rate, timeout và p95/p99 latency.
- Với common pool, có thể tham khảo `ForkJoinPool.commonPool().getPoolSize()`, `getActiveThreadCount()`, `getQueuedSubmissionCount()` và `getStealCount()`. Đây là **số đo ước lượng/quan sát**, không có nghĩa bạn sở hữu pool hoặc có thể quy mọi task về một module riêng.
- Gắn tên executor và correlation ID để trace khi dùng pool riêng; tránh log tên thread làm test bắt buộc vì runtime có thể thay đổi thread.
- Thử nghiệm dưới lưu lượng thực tế, gồm **task dài, I/O chậm, shutdown, rejection**, trước khi thay đổi parallelism của common pool toàn cục.

### Checklist code review

1. Tìm `CompletableFuture.supplyAsync(...)` và `runAsync(...)` không có đối số Executor.
2. Với mỗi call, phân loại CPU-bound / I/O-bound / có chặn / độ dài task / SLA.
3. Xác định rõ **owner** của executor, cách khởi tạo, giới hạn worker/queue và shutdown.
4. Chuyển các tác vụ cần isolation sang overload có `Executor`; trong Spring dùng bean dùng chung đã cấu hình.
5. Rà soát **mọi stage `...Async`**: `thenApplyAsync(fn)` không tự kế thừa pool bước trước. Truyền executor khi cần.
6. Bảo đảm context/transaction/security propagation và cleanup phù hợp; không dựa vào `ThreadLocal` của caller.
7. Xử lý riêng exception **bên trong Supplier** và rejection **tại thời điểm submit**.
8. Đặt timeout cho I/O thật; không dùng `orTimeout`/`cancel` làm bằng chứng ngừng tác vụ bên dưới.
9. Không `join` task con ngay trong một worker thuộc pool nhỏ đang chạy task cha.
10. Dùng monitoring và load test để xác nhận giới hạn của executor; đừng chỉ tăng số worker khi hệ thống đang nghẽn downstream.

## 12. Sai lầm thường gặp

**“Có `@Async` hoặc `ThreadPoolTaskExecutor` bean thì `supplyAsync(supplier)` tự chọn Spring pool.”** Sai: lời gọi static của JDK không tự truy vấn Spring container.

**“Tạo một CompletableFuture là đã có một thread mới.”** Sai: thường là một tác vụ được executor thực thi, worker được tái sử dụng. JDK có nhánh fallback tạo thread mới khi parallelism common pool không đủ 2, nhưng không phải hành vi chung cần dựa vào.

**“Task đầu dùng ioExecutor thì `thenApplyAsync(fn)` cũng dùng ioExecutor.”** Sai: stage Async không executor dùng default async facility, thường common pool.

**“Common pool luôn không thể chạy blocking task.”** Sai: có thể chạy, nhưng dùng chung và nguy cơ ảnh hưởng throughput/latency; cần đánh giá cơ chế blocking và giới hạn tài nguyên.

**“Dùng `join()` không chặn vì CompletableFuture là async.”** Sai: `join()` có thể chặn caller đến khi future hoàn tất.

**“Tăng common pool parallelism là sửa được mọi nghẽn.”** Sai: đây là cấu hình toàn JVM, không giải quyết giới hạn DB, HTTP, memory hay thiết kế task.

**“Bật timeout trên CompletableFuture sẽ ngắt HTTP request.”** Sai: timeout của future không bảo đảm ngắt hoạt động I/O bên dưới.

**“`exceptionally(...)` sẽ bắt mọi lỗi, kể cả executor từ chối trước khi trả future.”** Sai: rejection có thể được ném đồng bộ trước khi có future.

**“Truyền một TaskExecutor bất kỳ luôn khiến công việc chạy background.”** Sai: `SyncTaskExecutor` có thể chạy ngay trên caller thread.

**“Mỗi request tự tạo một thread pool riêng sẽ cô lập tốt hơn.”** Sai trong phần lớn ứng dụng web: quá nhiều thread/pool và thiếu lifecycle còn gây rủi ro tài nguyên cao hơn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.supplyAsync(() -> load())` trong ứng dụng có bean Spring `ioExecutor` sẽ chạy ở đâu?  
**Trả lời:** Theo default async facility của JDK (common pool khi hỗ trợ parallelism ít nhất 2, nếu không dùng thread mới cho từng task); không tự chọn `ioExecutor`.

**Câu 2.** Muốn `load()` chạy trên Spring `ThreadPoolTaskExecutor` thì sửa thế nào?  
**Trả lời:** Truyền chính bean executor làm đối số thứ hai: `CompletableFuture.supplyAsync(() -> load(), ioExecutor)`.

**Câu 3.** Vì sao `thenApplyAsync(fn)` đặt sau `supplyAsync(supplier, ioExecutor)` có thể quay lại common pool?  
**Trả lời:** Stage `thenApplyAsync` không truyền executor sẽ dùng default async facility; executor truyền ở stage trước không tự kế thừa.

**Câu 4.** `thenApply(fn)` có cam kết chạy ở ioExecutor không?  
**Trả lời:** Không. Non-async completion có thể chạy ở thread hoàn tất future hoặc một thread gọi completion, phụ thuộc timing.

**Câu 5.** Vì sao việc đưa hàng nghìn lời gọi HTTP đồng bộ vào common pool có thể gây vấn đề?  
**Trả lời:** Worker chung có thể bị giữ khi I/O chặn, làm những task khác chia sẻ tài nguyên phải chờ lâu; khó cô lập, định hạn và giám sát theo workload.

**Câu 6.** `CompletableFuture.supplyAsync(supplier, ioExecutor)` bị pool từ chối có thể được `future.exceptionally(...)` bắt không?  
**Trả lời:** Không nếu chính lời gọi gửi ném exception trước khi trả future; catch tại điểm gọi rồi quyết định fail fast hoặc tạo failed future.

**Câu 7.** `orTimeout(2, SECONDS)` có bảo đảm ngắt query DB sau 2 giây?  
**Trả lời:** Không. Nó thay trạng thái future theo timeout, còn DB query cần timeout/cancellation ở tầng JDBC/database.

**Câu 8.** Khi nào dùng common pool có thể chấp nhận được?  
**Trả lời:** Với công việc nhỏ, CPU-bound, ngắn, không blocking, không đòi hỏi isolation và đã đo được tương tác với tải khác.

## Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): overload `supplyAsync`, chính sách default async facility, `thenApplyAsync`, lỗi, timeout và cancellation.
- [Java SE 17 — ForkJoinPool Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, parallelism, work-stealing, managed blocking và metrics.
- [Java SE 17 — Executor Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): contract `execute(Runnable)` và sự khác biệt giữa các implementation.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor bean, core/max/queue, TaskDecorator, quản lý vòng đời và rejection.
- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): `submit`/`submitCompletable` của Spring và interface kế thừa từ `TaskExecutor`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): các `TaskExecutor` implementation, `@Async`, chọn executor và giới hạn ứng dụng.
