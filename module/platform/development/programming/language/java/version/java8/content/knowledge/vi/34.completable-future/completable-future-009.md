# CompletableFuture: Tách tác vụ CPU với tác vụ I/O chặn

**Chủ đề cha:** CompletableFuture. **Mục tiêu:** Thiết kế các pipeline bất đồng bộ trong Java sao cho công việc **tính toán CPU-bound** không bị cản trở bởi các tác vụ **I/O chặn** (blocking I/O); chọn `Executor` đúng cho từng stage; hiểu lịch thực thi của `supplyAsync`, `thenApplyAsync`, `thenCompose` và `thenCombineAsync`; quản lý hàng đợi, giới hạn tải, timeout, lỗi, vòng đời executor và kiểm thử. Phần cuối giới thiệu **virtual threads từ Java 21+** như một lựa chọn hiện đại cho I/O chặn, không nhầm với kỹ thuật có sẵn trên Java 8.

Các API nền tảng `CompletableFuture`/`Executor`/`ExecutorService` được giới thiệu trước hoặc trong Java 8 và **vẫn là API hiện hành**. Các chương trình chính dùng **Java 17+**, với ngày giờ/kết quả cố định và stdout không phụ thuộc thứ tự lên lịch. Đoạn dành cho virtual threads được ghi **Java 21+** riêng, vì không biên dịch trên Java 17.

> **Thông điệp cốt lõi:** Không dùng chung một executor nhỏ cho cả những tác vụ phải **chờ dịch vụ/đĩa/cơ sở dữ liệu** và những tác vụ **ngốn CPU**. Khi một stage đang chờ I/O chặn, thread nền tảng của nó có thể bị giữ mà không làm được tính toán hữu ích. Với `CompletableFuture`, hãy **đặt stage chờ I/O vào executor I/O** và **đặt stage CPU nặng vào executor CPU** bằng overload nhận `Executor`. Việc nối stage không có executor hoặc gọi `join()` bên trong worker có thể phá vỡ sự phân tách này.

## 1. CPU-bound và blocking I/O khác nhau ra sao?

Một tác vụ **CPU-bound** dành phần lớn thời gian để thực hiện phép tính: mã hóa/nén, xử lý dữ liệu lớn, phân tích cú pháp phức tạp, chạy thuật toán, kiểm tra chữ ký hay mô phỏng. Năng lực chính giới hạn nó là **CPU, bộ nhớ/cache, băng thông bộ nhớ**; tăng số thread vô hạn không làm CPU nhanh hơn, thậm chí có thể tăng context switching.

Một tác vụ **blocking I/O** dành nhiều thời gian **đợi** kết quả bên ngoài: đọc socket qua API blocking, đợi HTTP client đồng bộ, đọc file bằng API blocking, đợi JDBC query hoặc chờ connection pool. Khi dùng thread nền tảng, một thread có thể bị chiếm trong thời gian chờ. Số thread cần để duy trì throughput I/O có thể khác đáng kể số core, nhưng tải thực vẫn bị giới hạn bởi **connection pool, tài nguyên dịch vụ downstream, latency và queue**.

**Không đánh đồng mọi I/O với blocking I/O.** API như `HttpClient.sendAsync(...)` (Java 11+) đã trả `CompletableFuture` và quản lý I/O bất đồng bộ; không có lý do mặc định để bọc nó thêm trong `supplyAsync(() -> sendAsync(...).join(), ioPool)`. Cách bọc này tạo ra một worker phải chờ một future, làm mất lợi thế của API non-blocking.

### 1.1. Bảng phân loại công việc

| Công việc | Bản chất thường gặp | Hướng xử lý |
| --- | --- | --- |
| Xử lý một triệu phần tử, nén dữ liệu | CPU-bound | Executor CPU, số worker hữu hạn |
| JDBC query đồng bộ, đọc stream blocking | Blocking I/O | Executor I/O hoặc virtual threads từ Java 21+ |
| Gọi HTTP bằng `HttpClient.send(...)` | Blocking I/O | Executor I/O, có client timeout |
| Gọi HTTP bằng `HttpClient.sendAsync(...)` | I/O bất đồng bộ | Dùng future trả về, không tạo thread chỉ để `join` |
| Chuyển đổi chuỗi/ngắn, ghép vài field | Công việc rất nhẹ | Có thể dùng `thenApply` không async nếu không gây chặn |
| Parse JSON rất lớn, tính checksum/nén | CPU-bound | `thenApplyAsync(..., cpuExecutor)` |
| Ghi log thông qua appender có thể chặn | Có thể có blocking I/O | Kiểm tra library, tránh chặn stage CPU quan trọng |
| `Thread.sleep(...)` trong ví dụ | Mô phỏng **chờ**, không phải I/O thật | Dùng trong test để minh họa, không lấy làm benchmark |

Phân loại phải dựa vào **hành vi thư viện và profiler**, không chỉ tên phương thức. Một “gọi database” có thể gồm cả phần chờ kết nối lẫn CPU parse hàng trăm nghìn dòng. Khi stage bao gồm cả hai pha lớn, nên tách chúng thay vì coi cả hàm là một loại.

## 2. Vấn đề khi mọi stage chạy chung một executor

Giả sử pool có 4 platform threads. Nếu cả 4 thread đều đang chờ các HTTP call blocking lâu, những task CPU ngắn nhưng cần chạy trên pool này sẽ phải **đợi chỗ**. Dù máy còn core rảnh, pool vẫn không có worker khả dụng để khởi chạy stage CPU.

Tình huống phổ biến:

```java
CompletableFuture<String> response =
        CompletableFuture.supplyAsync(
                () -> blockingHttpCall()); // Không truyền executor
CompletableFuture<Result> transformed =
        response.thenApply(this::heavyParse); // Không truyền executor
```

**Đây là phản ví dụ minh họa bên trong class**, các phương thức `blockingHttpCall`/`heavyParse` và kiểu `Result` là giả định, **không phải chương trình độc lập**.

Các vấn đề:

1. `supplyAsync` **không có executor** thường sử dụng `ForkJoinPool.commonPool()`. Đây là tài nguyên chia sẻ của JVM, có thể đang phục vụ nhiều pipeline và các thuật toán song song khác.
2. `heavyParse` trong `thenApply` **không async**: nó có thể chạy ngay trên thread hoàn thành stage trước hoặc thread đã đăng ký callback sau khi future hoàn thành. Không có bảo đảm nó chuyển sang pool CPU.
3. Nếu một tác vụ chờ I/O chạy lâu trong common pool, nó có thể chiếm worker dành cho công việc khác; mức độ ảnh hưởng phụ thuộc đặc điểm và cấu hình JVM, không phải một “deadlock chắc chắn” trong mọi trường hợp.
4. Các tác vụ nhỏ từ request A có thể bị ảnh hưởng bởi request B, dù hai loại tải không liên quan nghiệp vụ.
5. Nếu hệ thống chỉ tăng số thread mà không kiểm soát queue và số yêu cầu downstream, có nguy cơ bão hòa kết nối, bộ nhớ và thời gian chờ.

**Giải pháp cơ bản:** đưa I/O blocking vào một executor riêng, đưa CPU nặng vào executor khác; quản lý giới hạn concurrency/queue và không để workers chờ nhau vô cớ.

## 3. Kiến trúc phân tách CPU và blocking I/O

Một pipeline điển hình:

```text
Request / scheduler
        |
        v
supplyAsync(blockingFetch, ioExecutor)
        |       [chờ HTTP/JDBC/đĩa trên I/O worker]
        v
thenApplyAsync(cpuTransform, cpuExecutor)
        |       [phân tích/nén/tính toán trên CPU worker]
        v
thenCombine / allOf / next stage
        |
        v
join/get tại ranh giới đồng bộ CÓ CHỦ ĐÍCH
hoặc trả CompletionStage cho caller bất đồng bộ
```

Hướng dẫn thiết kế:

- **I/O executor:** nhận những đoạn **blocking**; giới hạn theo sức chịu của dịch vụ và connection pool, không tùy tiện mở vô hạn platform threads.
- **CPU executor:** nhận đoạn tính toán đủ nặng để đáng scheduling riêng, thường số worker quanh năng lực CPU thực tế là điểm xuất phát để đo đạc, không phải công thức cố định.
- **Stage phối hợp:** chỉ ghép kết quả rất nhẹ có thể dùng `thenApply`/`thenCombine` không async; nếu phối hợp có CPU đáng kể thì chọn `thenCombineAsync(..., cpuExecutor)`.
- **Caller:** có thể trả `CompletableFuture<Result>` ngay để tiếp tục bất đồng bộ. `join`/`get` chỉ được gọi ở biên mà hệ thống **cố ý chờ**, không ở bên trong worker CPU đang giữ một thread cần thiết cho các task con.
- **Tài nguyên downstream:** với JDBC, connection pool vẫn quyết định tối đa có bao nhiêu query đồng thời; executor không tạo ra thêm kết nối hợp lệ.

### 3.1. Tại sao cần executor riêng?

**Cách ly tài nguyên** là lợi ích chính. Khi I/O upstream chậm, hàng đợi I/O có thể tăng, nhưng ít nhất thread CPU không bị dùng trực tiếp để chờ socket; CPU pool tiếp tục xử lý các kết quả đã có. Ngược lại, một tác vụ CPU rất nặng không tự chiếm toàn bộ thread dành để chờ kết quả từ dịch vụ khác.

Đây là **cách ly tương đối**, không có nghĩa hệ thống không thể ảnh hưởng chéo. Hai nhóm vẫn chia sẻ CPU vật lý, heap, GC, network, database và queue tổng thể; với quá nhiều tác vụ I/O hoàn thành cùng lúc, hàng đợi CPU có thể bị quá tải. Vì thế phải theo dõi **cả hai chiều**, không chỉ đặt tên cho executor.

## 4. CompletableFuture: Phương thức nào quyết định chạy ở đâu?

| API | Hàm được chạy thế nào? | Điểm lưu ý |
| --- | --- | --- |
| `supplyAsync(supplier)` | Dùng executor mặc định, thường common pool | Không phù hợp làm mặc định cho I/O blocking nặng |
| `supplyAsync(supplier, ioExecutor)` | Gửi supplier vào I/O executor | Biên I/O rõ ràng |
| `runAsync(runnable, executor)` | Giống supplyAsync nhưng không trả giá trị nghiệp vụ | Kết quả future là `Void` |
| `thenApply(fn)` | Non-async, có thể chạy trong thread hoàn thành hoặc thread đăng ký callback | Không nên coi là pool CPU riêng |
| `thenApplyAsync(fn)` | Async theo executor mặc định | Thường trở về common pool |
| `thenApplyAsync(fn, cpuExecutor)` | Async theo executor CPU | Cách phân tách stage CPU |
| `thenCompose(fn)` | Hàm trả một CompletionStage và được flatten | Không thêm worker chỉ để chờ future con |
| `thenComposeAsync(fn, executor)` | Gửi **hàm tạo stage** vào executor chỉ định | Stage mà hàm trả về vẫn có executor/lịch riêng của nó |
| `thenCombine(other, fn)` | Kết hợp sau khi hai stage hoàn thành | Hàm có thể chạy trên thread hoàn thành một stage |
| `thenCombineAsync(other, fn, cpuExecutor)` | Kết hợp trên pool CPU | Hữu ích khi hợp nhất có tính toán nặng |
| `handle` / `exceptionally` | Xử lý kết quả/lỗi theo chính sách stage | Non-async callback không bảo đảm pool riêng |
| `whenComplete` | Quan sát kết quả/lỗi, không mặc định “nuốt” lỗi | Tránh đặt logging blocking nặng trên thread CPU |

**Cảnh báo về mặc định:** Các async method không chỉ định `Executor` của `CompletableFuture` tiêu chuẩn chủ yếu chạy bằng `ForkJoinPool.commonPool()`. Javadoc nêu trường hợp commonPool không hỗ trợ hơn một parallel worker thì có thể dùng một thread mới cho mỗi task; subclass cũng có thể tùy biến default executor cho non-static methods. Vì vậy không viết test khẳng định tên thread luôn là `ForkJoinPool.commonPool-worker-N`.

### 4.1. `thenApply` khác `thenApplyAsync` ở điểm quan trọng

Với một future chưa hoàn tất, callback `thenApply` có thể chạy ngay ở thread **hoàn thành** stage trước. Nếu future đã hoàn tất trước khi đăng ký callback, callback có thể chạy trên **thread hiện đang đăng ký**. Do đó không có hợp đồng “thenApply luôn chạy cùng thread I/O” hay “thenApply luôn chạy thread caller”.

`thenApplyAsync(fn, cpuExecutor)` yêu cầu thực hiện stage thông qua executor CPU. Đây là lựa chọn rõ ràng khi `fn` thật sự CPU-bound.

Nếu `fn` chỉ kiểm tra null hoặc đổi tên một field rất nhỏ, việc chuyển pool bắt buộc có overhead. Không ép tất cả các phép map nhẹ thành async; mục tiêu là **đặt đúng stage nặng** lên đúng nơi.

## 5. Ví dụ đầy đủ Java 17+: Mỗi loại việc chạy trên executor riêng

Tạo file **`CpuIoSeparationDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class CpuIoSeparationDemo {
    record Fetched(String key, String data, boolean onIo) {}
    record Result(String key, int score, boolean io, boolean cpu) {}

    static ThreadFactory named(String prefix) {
        AtomicInteger sequence = new AtomicInteger();
        return task ->
                new Thread(task, prefix + sequence.incrementAndGet());
    }

    static String blockingFetch(String key) {
        // Chỉ mô phỏng thời gian chờ I/O để demo chạy offline.
        try {
            Thread.sleep(20);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
        return "item-" + key;
    }

    static int checksum(String data) {
        int sum = 0;
        for (int i = 1; i <= 10_000; i++) {
            sum += i;
        }
        return sum + data.charAt(data.length() - 1);
    }

    static CompletableFuture<Result> pipeline(
            String key, Executor io, Executor cpu) {
        return CompletableFuture.supplyAsync(
                () -> new Fetched(
                        key,
                        blockingFetch(key),
                        Thread.currentThread()
                                .getName().startsWith("io-")),
                io
        ).thenApplyAsync(
                fetched -> new Result(
                        fetched.key(),
                        checksum(fetched.data()),
                        fetched.onIo(),
                        Thread.currentThread()
                                .getName().startsWith("cpu-")),
                cpu
        );
    }

    public static void main(String[] args) {
        ExecutorService io = Executors.newFixedThreadPool(
                2, named("io-"));
        ExecutorService cpu = Executors.newFixedThreadPool(
                2, named("cpu-"));

        try {
            CompletableFuture<Result> first =
                    pipeline("A", io, cpu);
            CompletableFuture<Result> second =
                    pipeline("B", io, cpu);

            Result a = first.join();
            Result b = second.join();

            System.out.println("A: " + a.score()
                    + " io=" + a.io() + " cpu=" + a.cpu());
            System.out.println("B: " + b.score()
                    + " io=" + b.io() + " cpu=" + b.cpu());
            System.out.println("Total: "
                    + (a.score() + b.score()));
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 CpuIoSeparationDemo.java
java CpuIoSeparationDemo
```

**Stdout xác định:**

```text
A: 50005065 io=true cpu=true
B: 50005066 io=true cpu=true
Total: 100010131
```

**Giải thích:**

1. `blockingFetch` **dùng Thread.sleep để giả lập chờ**; đó không phải một lời gọi HTTP/JDBC thật. Mục tiêu của demo là kiểm tra cách **phân phối stage**, không benchmark hiệu suất I/O.
2. `supplyAsync(..., io)` chạy trên thread được tạo bởi factory mang tiền tố `io-`; `onIo` cho biết điều này mà không phụ thuộc tên/số thứ tự thread ngẫu nhiên.
3. `thenApplyAsync(..., cpu)` chạy phần checksum trên thread có tiền tố `cpu-`. Hai giá trị boolean `true` chứng minh hai pha của pipeline được gửi đúng executor.
4. Tổng từ 1 đến 10.000 là 50.005.000; cộng mã ký tự `A = 65` hoặc `B = 66` cho hai giá trị 50.005.065 và 50.005.066. Tổng in ra 100.010.131, vẫn trong phạm vi `int`.
5. Hai pipeline có thể được lên lịch theo thứ tự khác nhau, nhưng **chỉ thread main in kết quả sau `join`**, vì vậy thứ tự dòng stdout không dao động.
6. `Executors.newFixedThreadPool` ở đây chỉ dùng để minh họa executor riêng. Trong production, queue mặc định của fixed thread pool có thể **không giới hạn**, cần chiến lược capacity rõ ràng ở phần sau.
7. `shutdown` được gọi trong `finally` để ngừng nhận task mới. Trong ví dụ, hai kết quả đã được `join` trước khi shutdown; nếu sản phẩm có nhiều task đang chạy, nên kết hợp shutdown và `awaitTermination` theo vòng đời ứng dụng.

## 6. Fan-out I/O, fan-in CPU: thenCombine và thenCompose

Một request thường cần truy vấn hai nguồn I/O độc lập, rồi xử lý kết quả chung. Không cần gọi `join` ngay sau khi khởi chạy truy vấn thứ nhất, vì như vậy caller sẽ **đợi tuần tự** trước khi kịp gửi truy vấn thứ hai.

**Mẫu hợp lý:**

```java
CompletableFuture<String> left =
        CompletableFuture.supplyAsync(
                () -> fetchFromSourceA(), ioExecutor);

CompletableFuture<String> right =
        CompletableFuture.supplyAsync(
                () -> fetchFromSourceB(), ioExecutor);

CompletableFuture<Summary> summary =
        left.thenCombineAsync(
                right, this::computeSummary, cpuExecutor);
```

Đây là **pseudocode Java trong một class**, chưa khai báo các phương thức `fetchFromSourceA/B`, `computeSummary`, kiểu `Summary` và hai executor, nên **không chạy độc lập**. Ý chính là hai tác vụ I/O được gửi đi, phần kết hợp CPU chỉ chạy **sau khi cả hai thành công**, trên executor CPU được chỉ định.

### 6.1. `thenCompose`: Không chờ future con trong worker

Khi tác vụ thứ hai phụ thuộc kết quả tác vụ thứ nhất và **tự trả CompletableFuture**, dùng `thenCompose` để flatten:

```java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("A")
            .thenCompose(id ->
                CompletableFuture.supplyAsync(
                    () -> blockingFetch(id), ioExecutor))
            .thenApplyAsync(
                    String::toUpperCase, cpuExecutor);
```

Đây là **minh họa bên trong class**; `blockingFetch` và executor phải được khai báo. `thenCompose` tạo pipeline có kết quả cuối `String`, không cần dùng `thenApply(id -> supplyAsync(...))` rồi tạo `CompletableFuture<CompletableFuture<String>>`.

**Cảnh báo:** `thenComposeAsync(fn, cpuExecutor)` chỉ đưa **hàm fn** sang executor CPU; nếu `fn` trả một future I/O, bản thân I/O vẫn phải được gửi vào executor I/O hoặc dùng API non-blocking. Không nghĩ truyền CPU executor cho một stage là toàn bộ cây future bên dưới tự chạy trên CPU executor.

## 7. Java 17+ runnable: Kết hợp hai I/O và một phép tính CPU

Tạo file **`FanOutCpuMergeDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FanOutCpuMergeDemo {
    static String fetch(String key) {
        // Giả lập chờ dịch vụ bên ngoài, không phải I/O thật.
        try {
            Thread.sleep(10);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
        return "data-" + key;
    }

    static long digest(String a, String b) {
        long sum = 0;
        for (int i = 1; i <= 10_000; i++) {
            sum += i;
        }
        return sum + a.length() + b.length();
    }

    public static void main(String[] args) {
        ExecutorService io = Executors.newFixedThreadPool(2);
        ExecutorService cpu = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<String> left =
                    CompletableFuture.supplyAsync(
                            () -> fetch("A"), io);
            CompletableFuture<String> right =
                    CompletableFuture.supplyAsync(
                            () -> fetch("B"), io);

            CompletableFuture<Long> combined =
                    left.thenCombineAsync(
                            right,
                            FanOutCpuMergeDemo::digest,
                            cpu);

            CompletableFuture<String> composed =
                    CompletableFuture.completedFuture("A")
                            .thenCompose(id ->
                                    CompletableFuture.supplyAsync(
                                            () -> fetch(id), io))
                            .thenApplyAsync(
                                    String::toUpperCase, cpu);

            System.out.println("Combined digest: "
                    + combined.join());
            System.out.println("Composed: " + composed.join());
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
```

Chạy:

```bash
javac --release 17 FanOutCpuMergeDemo.java
java FanOutCpuMergeDemo
```

**Stdout:**

```text
Combined digest: 50005012
Composed: DATA-A
```

**Vì sao:** Hai giá trị `"data-A"` và `"data-B"` có độ dài 6; `digest` trả 50.005.000 + 6 + 6 = 50.005.012. `thenCombineAsync(..., cpu)` bảo đảm phần tính digest được gửi sang executor CPU. `thenCompose` giữ pipeline phẳng trong khi truy vấn phụ thuộc vẫn nằm ở executor I/O.

Trong thực tế, nếu phép kết hợp chỉ cộng hai con số nhỏ, `thenCombine` không async có thể rẻ hơn; demo dùng một vòng lặp để minh họa ranh giới CPU. Chỉ chọn async khi độ nặng của công việc và nhu cầu isolation biện minh cho scheduling overhead.

## 8. Không gọi `join()` hoặc `get()` giữa pipeline CPU khi không cần

Một trong những lỗi nghiêm trọng nhất là tạo một task trên executor nhỏ rồi ngay bên trong task đó **submit task con vào cùng executor và chờ nó**.

**Phản ví dụ cố ý gây nguy cơ deadlock, tuyệt đối không chạy như một chương trình mẫu:**

```java
ExecutorService oneThread =
        Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> inner =
                    CompletableFuture.supplyAsync(
                            () -> 42, oneThread);
            return inner.join(); // Worker đang chiếm thread duy nhất.
        }, oneThread);

int value = outer.join(); // Có thể chờ mãi.
```

Đây là **đoạn mã nguy hiểm minh họa**, không phải mã để chạy: worker thứ nhất giữ thread duy nhất của `oneThread`, rồi chờ future thứ hai vốn đang xếp hàng **không có thread để chạy**. Trong trường hợp cụ thể này, không có tiến triển tự nhiên nào để phá vòng chờ.

**Thay bằng composition:**

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("start")
                .thenCompose(ignored ->
                        CompletableFuture.supplyAsync(
                                () -> 42, oneThread));
```

Đây là đoạn minh họa trong phương thức có executor đã tạo. Caller chỉ nên `join` ở ranh giới mà hệ thống chủ ý chuyển từ bất đồng bộ sang đồng bộ; đừng chiếm thread pool để chờ một task nằm trong chính hàng đợi của pool đó.

### 8.1. Blocking `join` sau `allOf` thì sao?

`CompletableFuture.allOf(a, b, c)` hoàn thành khi cả ba future hoàn thành (hoặc hoàn thành exceptionally theo contract); nó trả `CompletableFuture<Void>`, **không tự gom thành List kết quả**. Sau khi `allOf(...).join()` thành công ở ranh giới đồng bộ, `a.join()`/`b.join()` để đọc các giá trị hoàn thành là hợp lý nếu đó là nơi được phép chờ.

Nhưng nếu tất cả phép `join` nằm trong một worker của executor mà các future con **cần chính worker đó**, vẫn có thể deadlock hoặc làm giảm throughput nghiêm trọng. Cách ly stage bằng composition và tránh block trong worker.

## 9. Executor CPU: Bao nhiêu thread là hợp lý?

Một điểm bắt đầu thường gặp cho CPU-bound tasks là số worker **xấp xỉ số CPU khả dụng** với process, chẳng hạn `Runtime.getRuntime().availableProcessors()`. Nhưng đây **không phải chân lý tối ưu cho mọi máy**: còn có quota/container, shared hosts, SMT/hyper-threading, memory bandwidth, GC, blocking ẩn và đặc tính thuật toán.

Nguyên tắc:

1. Dùng **executor chuyên cho tác vụ CPU thực sự**, để các task chờ socket không chiếm chỗ.
2. Khởi đầu từ mức parallelism hữu hạn, sau đó benchmark và quan sát. Không tăng thread count theo số request.
3. Nếu công việc CPU nhỏ dưới vài micro/millisecond, cân nhắc overhead scheduling; chưa chắc cần stage async riêng.
4. Nếu pipeline có **nhiều stage CPU nặng**, có thể dùng cùng CPU executor hoặc các nhóm riêng theo SLA/priority, nhưng không phân mảnh quá nhiều pool mà không có bằng chứng.
5. Nếu tác vụ CPU cần kết quả I/O, **đừng chặn CPU thread bằng `get/join`**; dùng stage phụ thuộc.
6. Hạn chế số tác vụ **chờ trong queue CPU**, vì executor ít thread với queue vô hạn vẫn có thể gây OOM hoặc latency không kiểm soát.

Ví dụ cấu hình minh họa cho một ứng dụng tự quản lý vòng đời:

```java
int workers = Math.max(
        1, Runtime.getRuntime().availableProcessors());
ExecutorService cpuExecutor =
        Executors.newFixedThreadPool(workers);
```

Đây là **đoạn trong phương thức**, không phải một cấu hình bắt buộc. `newFixedThreadPool` có **queue không giới hạn** theo factory mặc định; trong hệ thống áp lực tải cao cần thêm cơ chế giới hạn queue/submit hoặc một `ThreadPoolExecutor` cấu hình bounded.

### 9.1. ForkJoinPool có phải lúc nào cũng tốt cho CPU?

`ForkJoinPool` và common pool được thiết kế hữu ích cho các tác vụ có thể chia nhỏ/worker-stealing; nhưng **common pool** là tài nguyên **chia sẻ**, không bảo đảm isolation theo workload. `CompletableFuture.supplyAsync(...)` mặc định thường dùng common pool. Với một dịch vụ nhiều nguồn tải cần latency ổn định, CPU executor riêng có thể dễ vận hành và giám sát hơn.

Nếu một ứng dụng đã có thư viện quản lý CPU scheduling hoặc workload chia nhỏ tốt, bạn có thể sử dụng pool chuyên dụng tương ứng. Không có yêu cầu rằng **mọi** pipeline phải dùng `Executors.newFixedThreadPool`; điều quan trọng là **tách khỏi nơi có blocking I/O lâu** và quản lý giới hạn.

## 10. Executor I/O platform threads: Giới hạn theo tài nguyên downstream

Với I/O chặn chạy trên **platform threads**, số worker có thể lớn hơn CPU pool vì nhiều worker chỉ đang đợi. Nhưng đặt 1.000 worker cho database chỉ cho phép 20 connection **không làm tăng năng lực database**; nó chủ yếu tăng số thread chờ connection hoặc queue.

Hãy quan sát:

- **Connection pool**: số connection đang dùng, còn trống, thời gian chờ acquire.
- **I/O latency**: p50/p95/p99 và tỉ lệ timeout.
- **Hàng đợi executor**: kích thước, tuổi của task, số lần reject.
- **Số request đồng thời** và khả năng downstream chấp nhận.
- **Thread đang blocked/waiting** và chi phí bộ nhớ.
- **Retry/circuit breaker**: retry đồng loạt có thể làm bão tải nặng hơn.

Đặt **kích thước queue hữu hạn** và lựa chọn policy khi đầy. `Executors.newFixedThreadPool(n)` dễ dùng để học, nhưng dùng một `LinkedBlockingQueue` không giới hạn số phần tử trong cấu hình factory; dưới tải liên tục, task có thể tích tụ quá mức. Đừng ngầm hiểu “fixed n threads” nghĩa là bộ nhớ/hàng đợi đã bị giới hạn.

### 10.1. Chính sách khi pool I/O đã quá tải

Một `ThreadPoolExecutor` với `ArrayBlockingQueue` có thể giới hạn số task **đang chạy + đang xếp hàng**. Khi đã đầy, có thể:

- **AbortPolicy**: ném `RejectedExecutionException`, phù hợp khi caller có cơ chế trả “busy / 503 / retry later”.
- **CallerRunsPolicy**: chạy task ở thread gọi submit; tạo dạng backpressure, **nhưng có thể làm block request/event-loop thread**, nên không mặc định an toàn.
- **Custom rejection policy**: có thể kiểm soát admission, nhưng phải tránh bỏ task mà vẫn để future chưa bao giờ hoàn thành.
- **Semaphore/Rate limiter**: chặn hoặc từ chối trước khi submit, phù hợp khi resource cần giới hạn số request đồng thời.

Chọn chính sách theo SLA và yêu cầu hệ thống. Không để hệ thống âm thầm drop công việc quan trọng mà caller vẫn tưởng thành công.

## 11. Java 17+ runnable: Hàng đợi I/O bounded và từ chối overload

Tạo file **`BoundedIoExecutorDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedIoExecutorDemo {
    static int waitForRelease(
            CountDownLatch started, CountDownLatch release) {
        started.countDown();
        try {
            release.await();
            return 1;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor io = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            CompletableFuture<Integer> first =
                    CompletableFuture.supplyAsync(
                            () -> waitForRelease(
                                    started, release), io);

            // Chắc chắn worker đã bị giữ bởi first.
            started.await();

            // Task thứ hai xếp hàng, chờ worker duy nhất.
            CompletableFuture<Integer> second =
                    CompletableFuture.supplyAsync(
                            () -> 2, io);

            boolean rejected = false;
            try {
                CompletableFuture.supplyAsync(
                        () -> 3, io);
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("Third rejected: " + rejected);
            release.countDown();
            System.out.println("Results: "
                    + first.join() + ", " + second.join());
        } finally {
            release.countDown();
            io.shutdown();
            if (!io.awaitTermination(3, TimeUnit.SECONDS)) {
                io.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 BoundedIoExecutorDemo.java
java BoundedIoExecutorDemo
```

**Stdout:**

```text
Third rejected: true
Results: 1, 2
```

**Tại sao test có tính xác định?**

- `started.await()` bảo đảm task đầu **đang chiếm worker** trước khi tiếp tục.
- Hàng đợi `ArrayBlockingQueue<>(1)` chứa task thứ hai, vì vậy pool đã hết chỗ với task thứ ba.
- `AbortPolicy` khiến lời gọi `supplyAsync` thứ ba ném `RejectedExecutionException` tại bước submit; code bắt ngoại lệ và in true.
- `release.countDown()` giải phóng task đầu; task thứ hai có thể chạy và trả 2.
- `finally` mở latch ngay cả khi có lỗi, rồi `shutdown` và `awaitTermination` để tránh treo JVM.
- Kích thước pool/queue chỉ là cấu hình **demo**, không phải mức capacity nên dùng cho production.

**Bài học:** Tách pool CPU/I/O là điều kiện cần nhưng chưa đủ; còn phải xử lý khi số yêu cầu vượt năng lực. Trong API service, hãy biến rejection thành phản hồi tải cao có ý nghĩa, không để request tiếp tục như đã được chấp nhận.

## 12. Timeout, ngoại lệ và hủy: Hoàn tất future không đồng nghĩa dừng I/O

Một tác vụ I/O chặn có thể không phản hồi hoặc chỉ phản hồi sau nhiều giây. Các công cụ cần phân biệt:

| API / chiến lược | Vai trò | Cảnh báo |
| --- | --- | --- |
| HTTP/JDBC/socket connect/read/query timeout | Giới hạn hoạt động I/O thực tại nguồn | Thường là cách quan trọng nhất để giải phóng tài nguyên |
| `CompletableFuture.orTimeout(t, unit)` | Hoàn tất future **exceptionally** bằng TimeoutException nếu quá hạn | **Không bảo đảm tác vụ I/O đang chạy bị ngắt** |
| `completeOnTimeout(value, t, unit)` | Hoàn tất future với giá trị fallback khi quá hạn | Có thể che lỗi nếu giá trị fallback làm người dùng tưởng dữ liệu đầy đủ |
| `future.get(t, unit)` | Caller đợi tối đa một khoảng trước khi ném TimeoutException | Không mặc nhiên cancel/dừng tác vụ nền |
| `exceptionally(fn)` | Chuyển failure thành kết quả fallback | Chạy non-async; hãy giữ handler nhẹ |
| `handle((value,error)->...)` | Phân nhánh trên success/failure | Đừng âm thầm nuốt lỗi thật |
| `whenComplete((value,error)->...)` | Quan sát để log/metric | Không tự biến mọi lỗi thành thành công |
| `cancel(true)` trên CompletableFuture | Yêu cầu completion bị hủy | Flag interrupt **không có tác dụng** với implementation CompletableFuture tiêu chuẩn |

**Điểm rất dễ sai:** `CompletableFuture.cancel(true)` không giống `FutureTask.cancel(true)` của một worker được quản lý theo cơ chế interrupt. Javadoc `CompletableFuture` ghi rõ tham số `mayInterruptIfRunning` **không có tác dụng** đối với loại future này vì interrupt không dùng để điều khiển quá trình xử lý. `orTimeout` cũng không tự đóng socket hoặc trả connection cho pool ngay lập tức.

Vì vậy, **cấu hình timeout ở thư viện I/O nguồn** là bắt buộc nếu tài nguyên cần được giải phóng đúng hạn. Tùy API, có thể cần hủy riêng HTTP request/JDBC statement, đóng resource hoặc thiết kế interruption/cooperative cancellation hợp lệ.

### 12.1. Ngoại lệ được truyền qua chain

Nếu `supplyAsync` ném `IllegalStateException`, stage dependent bình thường không thực thi. Future sẽ hoàn thành exceptionally; `join` ở biên ném `CompletionException` bọc nguyên nhân. `get` ném `ExecutionException` và có thể ném `InterruptedException`. Trong các handler, hãy ghi nhận **nguyên nhân gốc**, không làm mất stack trace hoặc coi mọi failure là timeout.

Không lặp lại toàn bộ task I/O bên trong `exceptionally` chỉ để retry một cách vô hạn: điều đó có thể làm bão tải khi downstream đang lỗi. Retry cần số lần tối đa, exponential backoff/jitter phù hợp, deadline tổng và tính **idempotent** của thao tác.

## 13. Java 17+ runnable: Failure và timeout của CompletableFuture

Tạo file **`CompletableFutureFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletableFutureFailureDemo {
    public static void main(String[] args) {
        ExecutorService io =
                Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<String> failed =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalStateException(
                                "downstream failure");
                    }, io);

            CompletableFuture<String> handled =
                    failed.exceptionally(ex -> "fallback");

            System.out.println("Fallback: "
                    + handled.join());

            // Future không hoàn thành: minh họa timeout,
            // không đại diện cho một I/O bị hủy.
            CompletableFuture<String> never =
                    new CompletableFuture<>();

            CompletableFuture<String> timeout =
                    never.orTimeout(
                            25, TimeUnit.MILLISECONDS)
                            .exceptionally(ex -> "timed-out");

            System.out.println("Timeout: "
                    + timeout.join());
            System.out.println("Source failed: "
                    + failed.isCompletedExceptionally());
        } finally {
            io.shutdown();
        }
    }
}
```

Chạy với Java 17+:

```bash
javac --release 17 CompletableFutureFailureDemo.java
java CompletableFutureFailureDemo
```

**Stdout:**

```text
Fallback: fallback
Timeout: timed-out
Source failed: true
```

**Giới hạn của ví dụ:** `orTimeout` được bổ sung trong **Java 9**, nên chương trình này không phải mã nguồn biên dịch ở mức `--release 8`. Nó hợp lệ ở Java 17 và các JDK hiện hành. `never` là một future không gắn tác vụ I/O thật; demo chỉ cho thấy **cách hoàn tất future khi timeout**, không chứng minh việc hủy HTTP request.

Khi đưa vào sản phẩm, hãy cấu hình đồng thời: timeout tại client I/O, deadline của toàn pipeline, cơ chế release resource, chính sách fallback và metric cho lỗi/timeout. `exceptionally` không phân biệt TimeoutException với mọi lỗi khác trong demo; code production thường phải tách ra nếu hành vi xử lý khác nhau.

## 14. Blocking I/O và API bất đồng bộ thật: Không bọc future trong future

Nếu thư viện đã có API async:

```java
CompletableFuture<HttpResponse<String>> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());

CompletableFuture<Parsed> parsed =
        response.thenApplyAsync(
                httpResponse -> parseExpensive(
                        httpResponse.body()),
                cpuExecutor);
```

Đây là **đoạn mã mô tả kiến trúc, không tự chạy độc lập**: `client`, `request`, `cpuExecutor` và `Parsed/parseExpensive` chưa được khai báo. `HttpClient.sendAsync` có từ Java 11 và trả `CompletableFuture`. Không cần một platform worker riêng chỉ để gọi `sendAsync(...)` rồi chờ nó.

**Phản ví dụ nên tránh:**

```java
CompletableFuture<String> bad =
        CompletableFuture.supplyAsync(
                () -> client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString())
                        .join()
                        .body(),
                ioExecutor);
```

Đây là **phản ví dụ phụ thuộc client/request giả định**, không phải code khuyến nghị. Nó dùng một thread I/O pool để **chặn tại `join`**, trong khi API nguồn vốn hỗ trợ bất đồng bộ.

**Khi nào dùng `supplyAsync` cho I/O?** Khi bạn thật sự phải gọi API **blocking**, chẳng hạn repository JDBC đồng bộ hay HTTP client synchronous `send`. Khi thư viện đã trả CompletionStage hoặc một publisher phản ứng có cơ chế scheduling/backpressure riêng, nên tích hợp theo hợp đồng của thư viện đó.

### 14.1. JDBC không biến thành non-blocking chỉ nhờ CompletableFuture

`CompletableFuture.supplyAsync(repository::findAll, ioExecutor)` **không khiến JDBC trở thành non-blocking I/O**. Nó chỉ dời lời gọi JDBC chặn từ caller sang một worker. JDBC connection và transaction vẫn phải được quản lý như trước, và việc đẩy thao tác sang thread khác có thể ảnh hưởng các context gắn thread (transaction, security, MDC).

Phải kiểm tra framework thực tế về thread-bound transaction/context. Đừng lấy một transaction object hoặc connection **không thread-safe** rồi sử dụng song song trên nhiều worker. Nếu framework đã cung cấp executor, transaction boundary hoặc async repository API riêng, cần tôn trọng hợp đồng của nó.

## 15. Java 21+: Virtual threads cho I/O chặn

Từ **Java 21**, virtual threads là tính năng chính thức. `Executors.newVirtualThreadPerTaskExecutor()` tạo **một virtual thread cho mỗi task**, hữu ích cho nhiều tác vụ phần lớn thời gian chờ I/O. Virtual thread có thể được runtime tạm tháo khỏi platform carrier khi blocking API được hỗ trợ, để platform carrier chạy tác vụ khác.

Điểm then chốt:

1. Virtual threads **không làm phép tính CPU chạy nhanh hơn**. CPU-bound tasks vẫn bị giới hạn bởi CPU thực.
2. Virtual-thread executor **không đặt giới hạn số virtual threads theo kiểu pool cố định**. Vì virtual threads có thể rất nhiều, vẫn cần **giới hạn request/connection/DB concurrency** bằng connection pool, `Semaphore`, rate limiter hoặc admission control.
3. **Không “pool virtual threads”** chỉ để tái sử dụng chúng như platform threads. Mô hình được khuyến nghị là tạo virtual thread theo task và giới hạn **tài nguyên thật**.
4. Không phải mọi thư viện blocking đều tự động tận dụng virtual threads tối ưu; cần kiểm tra JDBC driver, native/foreign calls, lock contention, quan sát carrier pinning nếu có.
5. Không dùng virtual threads để bọc vòng lặp CPU vô tận rồi mong tăng throughput; giữ CPU stage nặng trên CPU executor riêng theo nhu cầu.
6. Java 17 **không** có `Executors.newVirtualThreadPerTaskExecutor` hay `Thread.isVirtual()`. Đoạn dưới **chỉ Java 21+**.

### 15.1. Java 21+ runnable: Virtual I/O + platform CPU

Tạo file **`VirtualThreadIoDemo.java`** (yêu cầu **JDK 21+**):

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualThreadIoDemo {
    static String simulateBlockingIo() {
        try {
            Thread.sleep(15);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
        return "I/O virtual: "
                + Thread.currentThread().isVirtual();
    }

    public static void main(String[] args) {
        try (ExecutorService io =
                     Executors.newVirtualThreadPerTaskExecutor();
             ExecutorService cpu =
                     Executors.newFixedThreadPool(1)) {

            CompletableFuture<String> result =
                    CompletableFuture.supplyAsync(
                            VirtualThreadIoDemo::simulateBlockingIo,
                            io)
                            .thenApplyAsync(
                                    value -> value
                                            + ", CPU virtual: "
                                            + Thread.currentThread()
                                                    .isVirtual(),
                                    cpu);

            System.out.println(result.join());
        }
    }
}
```

Biên dịch và chạy **Java 21+**, không dùng `--release 17`:

```bash
javac VirtualThreadIoDemo.java
java VirtualThreadIoDemo
```

**Stdout:**

```text
I/O virtual: true, CPU virtual: false
```

**Giải thích:** `supplyAsync` được gửi vào executor tạo virtual thread mới cho I/O; stage CPU kế tiếp được gửi vào `Executors.newFixedThreadPool(1)` dùng platform thread trong ví dụ. `Thread.sleep` vẫn chỉ là giả lập thời gian chờ, không phải benchmark công nghệ virtual threads. Kết quả `true/false` kiểm tra thread type, không chứng minh latency/throughput sẽ cải thiện.

**Vì sao dùng `try-with-resources` ở Java 21+?** `ExecutorService` có phương thức `close` ở JDK hiện đại, cho phép đóng có cấu trúc. Với các ví dụ Java 17 ở trên, dùng `shutdown`/`awaitTermination` vì chúng phải biên dịch trên Java 17.

### 15.2. Virtual threads thay thế mọi CompletableFuture?

**Không.** Virtual threads giúp viết code chờ I/O theo phong cách tuần tự dễ đọc hơn và có thể mở rộng tốt khi nhiều request chờ. CompletableFuture giúp **mô hình hóa dependency, fan-out/fan-in, xử lý bất đồng bộ, exception stages**. Hai công cụ có thể kết hợp, nhưng không nên ép mọi API async thành blocking chỉ vì có virtual threads; giữ nguyên mô hình phù hợp với thư viện và độ phức tạp ứng dụng.

Virtual threads đặc biệt thích hợp nếu một dịch vụ chủ yếu dùng API blocking và cần phục vụ nhiều request đồng thời. Khi đã có client non-blocking hiệu quả, đừng giả định chuyển sang virtual threads luôn nhanh hơn. Dùng **profiling, load test và metric** thay cho kết luận chung.

## 16. Giới hạn đồng thời: Phân biệt số thread, queue và tài nguyên

Giả sử dịch vụ chỉ cho phép 20 database connections:

- CPU executor có 8 threads không tạo ra thêm connection.
- I/O executor có 100 threads có thể khiến nhiều thread **chờ connection**.
- Virtual-thread executor có thể tạo hàng nghìn task đồng thời nhưng vẫn chỉ 20 query có connection được chạy.
- Hàng đợi application và hàng đợi connection pool cộng lại có thể làm tăng latency quá mức.

Một cơ chế rõ ràng khi dùng virtual threads là **Semaphore** để giới hạn số lời gọi downstream:

```java
Semaphore permits = new Semaphore(20);

String callLimitedService() throws InterruptedException {
    permits.acquire();
    try {
        return blockingCall();
    } finally {
        permits.release();
    }
}
```

Đây là **mẫu method minh họa trong class**, chưa khai báo `blockingCall()` và `permits` như một field; cần import `java.util.concurrent.Semaphore`. Trong implementation thực tế, nên đặt `permits` ở scope chia sẻ của service, không tạo semaphore mới ở mỗi request; đồng thời xử lý interruption, timeout khi chờ permit, rate limit và các tình huống tài nguyên khác.

**Không luôn cần semaphore bên ngoài database connection pool** nếu connection pool đã điều khiển tốt chính xác resource đó. Nhưng nếu một downstream API có quota khác (ví dụ 10 request đồng thời) hoặc mỗi request tốn nhiều connection, semaphore/rate limiter có thể hữu ích.

### 16.1. Admission control và backpressure

Một hệ thống chỉ “đặt queue rất lớn để không mất request” thường sẽ làm lỗi đến **muộn hơn** và tiêu tốn bộ nhớ. Thay vào đó:

- Giới hạn inflight request/task.
- Có timeout/deadline **bao trùm cả thời gian chờ queue** nếu yêu cầu SLA có deadline tổng.
- Quan sát queue depth, queue wait time, active workers, completion time, rejection.
- Từ chối quá tải sớm và rõ ràng, hoặc áp dụng retry có backoff khi hành vi nghiệp vụ cho phép.
- Tách hàng đợi của các dependency quan trọng để một downstream đang lỗi không kéo sập workload khác.

Khi queue đầy, `RejectedExecutionException` có thể được ném ngay ở bước gọi `supplyAsync(..., executor)`. Nó không nhất thiết trở thành **exceptional completion trong CompletableFuture**, vì future có thể chưa được tạo và trả về. Code gọi cần có chiến lược xử lý **cả lỗi submit và lỗi trong stage**.

## 17. Truyền context, transaction và observability qua các executor

Chuyển giữa I/O executor và CPU executor đồng nghĩa các stage có thể chạy trên **những thread khác nhau**.

**Những điều không được giả định tự động:**

- `ThreadLocal` đặt ở request thread luôn có giá trị trên I/O/CPU worker.
- MDC/tracing context được chuyển nguyên vẹn qua mọi `thenApplyAsync`.
- Security context hoặc transaction của framework tự đi theo CompletableFuture.
- Connection/EntityManager/Session không thread-safe có thể được chia sẻ giữa worker mà không cần ranh giới.
- Thread name là ID bền vững của request.

Giải pháp phụ thuộc framework:

1. Gắn **correlation ID / request ID** rõ ràng vào dữ liệu pipeline hoặc sử dụng context propagation do framework hỗ trợ.
2. Tách transaction boundary hợp lý, không đẩy một transaction thread-bound sang thread khác nếu API không hỗ trợ.
3. Đóng connection/stream trong chính scope sử dụng (`try-with-resources`), không để resource vượt quá vòng đời request vô tình.
4. Theo dõi stage I/O và CPU tách riêng; log lỗi gốc, không chỉ thông báo `CompletionException`.
5. Không viết unit test khẳng định tên thread theo số thứ tự worker của ForkJoinPool, vì scheduler có thể thay đổi.

Trong demo đầu, tên thread chỉ dùng để **chứng minh executor được chọn**; không phải cơ chế bảo mật, tracking request hay đảm bảo thứ tự.

## 18. Cách đo hiệu quả đúng: Throughput, latency và fairness

Khi so sánh “dùng chung commonPool” với “tách CPU/I/O”, cần một test tải có kiểm soát:

| Chỉ số | Kỳ vọng phân tích |
| --- | --- |
| Throughput | Bao nhiêu request/s thành công với SLA chấp nhận được |
| End-to-end latency p50/p95/p99 | Queue và downstream có làm chậm phần lớn request không |
| CPU utilization & run queue | CPU có bị thiếu việc hay quá tải/context switch |
| Active I/O workers / virtual tasks | Số đang chạy, đang chờ, chờ resource |
| CPU queue wait | Stage CPU có bị I/O cản trở hay không |
| I/O queue wait | Downstream chậm có tích task không |
| Timeout/rejection/error rate | Có overload, bão retry hoặc resource leak không |
| Heap/GC/threads | Tăng concurrency có gây chi phí bộ nhớ quá mức không |
| Connection pool wait/saturation | Giới hạn bottleneck thật có nằm ở DB không |
| Fairness / isolation | Workload A có kéo chậm workload B hay không |

**Đừng benchmark bằng một vòng `Thread.sleep(100)` rồi tuyên bố đã đo I/O thật.** Sleep chỉ mô phỏng chờ; behavior thực chịu ảnh hưởng từ socket timeout, TLS, serialization, connection pool, network variability và server capacity. Với CPU, dùng phép tính đủ lớn, warm-up, dữ liệu thực tế và công cụ benchmark như **JMH** khi cần kết luận vi mô; đồng thời đo **load test end-to-end**.

### 18.1. Quy trình tuning thực tế

Bắt đầu bằng cách **phân loại stage** qua profiler. Tạo executor riêng với giới hạn rõ; đặt deadline I/O và chính sách reject. Quan sát trong tải đủ cao để lộ queue. Sau đó điều chỉnh độc lập kích thước CPU executor, I/O concurrency, queue capacity và connection pool; thay một biến có kiểm soát để nhận biết nguồn cải thiện hoặc xấu đi. Test cả các trường hợp downstream chậm/bị lỗi, spike request và shutdown ứng dụng.

Không nên tối ưu bằng cách tăng số thread trước khi hiểu bottleneck. Nếu CPU saturation đã chạm giới hạn, thêm I/O thread sẽ không giải quyết phép tính nặng; nếu DB connection pool là bottleneck, CPU pool lớn hơn cũng không giúp.

## 19. Những sai lầm phổ biến

1. **Đưa blocking I/O vào `CompletableFuture.supplyAsync(...)` không executor** và nghĩ nó có pool cách ly: mặc định thường dùng commonPool.
2. **Gọi `thenApply(cpuHeavy)` và nghĩ chắc chắn chạy trên CPU pool:** non-async stage không chọn executor cụ thể.
3. **Gọi `thenApplyAsync(cpuHeavy)` không executor** rồi tin nó theo executor I/O trước: thường trở về default executor/commonPool.
4. **Dùng chung một fixed pool bé cho CPU và I/O chặn:** có thể bão hòa workers vì các request chờ.
5. **Tạo executor mới trong mỗi request** rồi không shutdown: tốn thread/tài nguyên và gây khó quản lý.
6. **Gọi `join()` ở giữa worker CPU cho task con trong cùng single-thread executor:** có thể deadlock.
7. **Bọc `HttpClient.sendAsync` vào `supplyAsync(...join...)`:** biến non-blocking thành blocking vô ích.
8. **Tưởng CompletableFuture làm JDBC non-blocking:** chỉ chuyển lời gọi chặn sang thread khác.
9. **Tăng vô hạn số I/O worker để tăng throughput:** downstream, connection pool và tài nguyên vẫn có giới hạn.
10. **Tưởng `newFixedThreadPool(n)` có queue bounded:** factory mặc định dùng queue không giới hạn.
11. **Tưởng thread pool nhỏ sẽ tự giới hạn tổng số request:** queue có thể tích tụ vô hạn nếu không cấu hình.
12. **Dùng CallerRunsPolicy trên event-loop mà không suy xét:** caller có thể bị kéo vào tác vụ chặn.
13. **Không bắt `RejectedExecutionException` tại bước submit:** có thể chưa có future để xử lý qua `exceptionally`.
14. **Dùng `orTimeout` và nghĩ socket/JDBC lập tức bị hủy:** future timeout không tự ngắt I/O.
15. **Dùng `cancel(true)` trên CompletableFuture và tin nó interrupt underlying task:** implementation này không dùng interrupt để điều khiển xử lý.
16. **Chỉ đặt timeout cho toàn future, bỏ qua connect/read/query timeout:** resource nguồn có thể vẫn bị giữ.
17. **Tạo retry vô hạn trong exceptionally:** có thể nhân tải đúng lúc downstream quá tải.
18. **Bỏ qua resource cleanup vì pipeline async:** connection, stream, statement vẫn phải đóng đúng vòng đời.
19. **Cho rằng callback non-async luôn chạy trên cùng thread với stage trước:** nếu future đã completed, caller có thể chạy callback.
20. **Tin rằng virtual threads có từ Java 8 hoặc Java 17:** chính thức từ Java 21.
21. **Tin virtual threads làm CPU nhanh hơn:** chúng chủ yếu giúp scale số task đang chờ I/O.
22. **Pool virtual threads như platform thread workers:** dùng per-task virtual thread và giới hạn tài nguyên thật.
23. **Cho rằng virtual threads bỏ được connection pool limit:** không, connection vẫn là tài nguyên hữu hạn.
24. **Sử dụng blocking JDBC/HTTP trong stage của framework non-blocking mà không xét event-loop:** có thể block event loop, gây suy giảm nghiêm trọng.
25. **Coi commonPool hoàn toàn không bao giờ xử lý blocking:** tùy implementation và `ForkJoinPool.managedBlock`, nhưng không lấy đó làm lý do mặc định đẩy I/O chặn vào pool chia sẻ.
26. **Không xét vùng CPU quota/container:** `availableProcessors` là điểm xuất phát, không phải định mức tối ưu cứng.
27. **Coi tăng số task đồng thời chắc chắn giảm latency:** có thể chỉ tăng queue wait và contention.
28. **Đặt xử lý CPU nặng trong `whenComplete` chỉ để log:** callback có thể cản worker hoàn thành task.
29. **Bỏ qua ngữ cảnh ThreadLocal/MDC/transaction khi đổi thread:** tracing hoặc transaction có thể sai.
30. **So sánh thời gian chạy một lần với Thread.sleep và kết luận tối ưu:** không thay thế benchmark và load testing.

## 20. Checklist thiết kế và code review

Trước khi merge một pipeline CompletableFuture có cả CPU và I/O, kiểm tra:

- [ ] Đã phân loại stage: **CPU-bound**, **blocking I/O**, **non-blocking API**, **lightweight glue**?
- [ ] Mọi blocking call quan trọng đã được đặt vào I/O executor (hoặc virtual thread model thích hợp), thay vì vô tình chặn CPU pool/commonPool?
- [ ] Mọi stage CPU nặng đã chọn executor có capacity phù hợp bằng `thenApplyAsync/thenCombineAsync` hoặc cơ chế tương đương?
- [ ] Có tránh việc `thenApply` non-async chứa phép tính hoặc I/O chặn kéo dài?
- [ ] Có tránh `join/get` bên trong worker đang đợi task con của cùng executor?
- [ ] Có dùng `thenCompose` để flatten dependent future thay vì future lồng nhau hoặc block?
- [ ] Có giới hạn I/O concurrency theo connection/resource downstream và queue bounded/admission?
- [ ] Có xử lý `RejectedExecutionException` ngay khi submit, không chỉ lỗi stage?
- [ ] Có timeout thực ở HTTP/JDBC/socket **và** deadline end-to-end?
- [ ] Có chính sách error/fallback/retry rõ, không làm mất root cause?
- [ ] Executor có vòng đời application-level, shutdown/awaitTermination khi phù hợp, không tạo vô hạn?
- [ ] Có tách xử lý non-blocking API như `sendAsync` khỏi API blocking như `send`?
- [ ] Nếu dùng virtual threads, đã kiểm tra runtime **Java 21+**, tài nguyên downstream và phạm vi tác vụ CPU?
- [ ] Có truyền correlation ID, security/transaction context theo contract framework?
- [ ] Có metric queue depth, queue wait, active tasks, p95/p99 latency, timeout và reject?
- [ ] Có test overload, failure, timeout, shutdown, rủi ro deadlock và tính xác định output?
- [ ] Có benchmark/load test trước khi tuyên bố sizing tối ưu?

Một code review không chỉ nhìn số lượng `CompletableFuture` hay `Async` trong tên phương thức. Nó phải làm rõ **stage nào có thể chặn bao lâu, sử dụng executor nào, chịu giới hạn nào, và ai chịu trách nhiệm dọn tài nguyên khi thất bại**.

## 21. Bài kiểm thử tự động Java 17+ cho tách executor

Tạo file **`CpuIoBoundaryChecks.java`**. Chương trình kiểm tra CPU/I/O thực thi trong hai executor riêng qua thread-name prefix, đồng thời kiểm tra kết quả tính và trạng thái future; không phụ thuộc cờ JVM `-ea`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class CpuIoBoundaryChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static ThreadFactory named(String prefix) {
        AtomicInteger sequence = new AtomicInteger();
        return task ->
                new Thread(task, prefix + sequence.incrementAndGet());
    }

    public static void main(String[] args) {
        ExecutorService io =
                Executors.newSingleThreadExecutor(named("io-"));
        ExecutorService cpu =
                Executors.newSingleThreadExecutor(named("cpu-"));

        try {
            CompletableFuture<String> ioStage =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            io);

            CompletableFuture<String> cpuStage =
                    ioStage.thenApplyAsync(
                            threadName -> threadName + " -> "
                                    + Thread.currentThread().getName(),
                            cpu);

            String route = cpuStage.join();
            check(route.startsWith("io-"),
                    "I/O stage on wrong executor");
            check(route.contains(" -> cpu-"),
                    "CPU stage on wrong executor");
            System.out.println("Executor routing: PASS");

            CompletableFuture<Long> calculate =
                    CompletableFuture.supplyAsync(() -> {
                        long sum = 0;
                        for (int i = 1; i <= 10_000; i++) {
                            sum += i;
                        }
                        return sum;
                    }, cpu);

            check(calculate.join() == 50_005_000L,
                    "wrong CPU result");
            System.out.println("CPU result: PASS");

            CompletableFuture<String> left =
                    CompletableFuture.supplyAsync(
                            () -> "a", io);
            CompletableFuture<String> right =
                    CompletableFuture.supplyAsync(
                            () -> "b", io);
            CompletableFuture<String> combined =
                    left.thenCombineAsync(
                            right, String::concat, cpu);

            check("ab".equals(combined.join()),
                    "wrong fan-in result");
            System.out.println("Fan-in: PASS");
            System.out.println("All checks: PASS");
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
```

Chạy:

```bash
javac --release 17 CpuIoBoundaryChecks.java
java CpuIoBoundaryChecks
```

**Stdout:**

```text
Executor routing: PASS
CPU result: PASS
Fan-in: PASS
All checks: PASS
```

**Giới hạn của test:** Prefix thread-name chỉ kiểm tra stage được submit vào executor dự kiến, không thể chứng minh hệ thống sẽ có throughput cao hay không bao giờ deadlock trong workload thật. Test thêm bounded queue/rejection (`BoundedIoExecutorDemo`), failure/timeout (`CompletableFutureFailureDemo`) và load test thực tế ở môi trường phù hợp.

## 22. Câu hỏi ôn tập

1. Vì sao `ForkJoinPool.commonPool()` có thể không phải nơi thích hợp để chạy hàng loạt blocking HTTP/JDBC calls?
2. `supplyAsync(fn)` và `supplyAsync(fn, ioExecutor)` khác nhau về điều gì?
3. `thenApply(fn)` có luôn chạy trong thread hoàn thành stage trước không?
4. Muốn bảo đảm phần parse CPU nặng đi vào executor CPU, dùng API nào?
5. `thenApplyAsync(fn)` không truyền executor có tự lấy executor IO của `supplyAsync` trước đó không?
6. `thenCompose` khác `thenApply` khi callback trả `CompletableFuture`?
7. Một task trên single-thread executor tạo task con cùng executor và gọi `join` có rủi ro gì?
8. Vì sao fixed thread pool n workers vẫn có thể tiêu thụ bộ nhớ không kiểm soát khi downstream chậm?
9. `RejectedExecutionException` tại thời điểm submit có thể phát sinh trước khi method `supplyAsync` trả future không?
10. `CompletableFuture.orTimeout` và `cancel(true)` có bảo đảm đóng socket ngay lập tức không?
11. Nếu một HTTP client đã có `sendAsync`, có nên gọi `sendAsync(...).join()` bên trong `supplyAsync` không?
12. Virtual threads hữu ích nhất với công việc CPU-bound hay I/O blocking?
13. Virtual threads có làm database connection pool 20 connections thành 200 connections không?
14. Nếu stage CPU đã được tách nhưng callback `whenComplete` ghi log blocking lâu, hệ thống còn có thể bị kéo chậm không?
15. Để đo hiệu quả của việc tách pool, cần nhìn metric nào ngoài tổng thời gian chạy một demo?
16. Hai code dùng `ThreadLocal` có tự động thấy cùng context sau khi đổi executor không?

**Gợi ý đáp án:** (1) commonPool là shared resource; blocking giữ worker, có thể làm chậm task khác. (2) overload thứ hai chọn executor rõ ràng. (3) không, nếu future đã hoàn thành thì caller đăng ký có thể chạy callback. (4) `thenApplyAsync(fn,cpuExecutor)`. (5) không, thường dùng default/commonPool. (6) Compose flatten future con, không tạo future lồng. (7) deadlock/starvation vì worker đang chờ task cần chính worker đó. (8) factory default có queue không giới hạn. (9) có. (10) không, cần I/O/client cancellation và timeout thật. (11) không, làm worker chặn một future đã async. (12) I/O chặn, không tăng tốc tính CPU. (13) không, connection vẫn hữu hạn. (14) có, callback non-async có thể cản thread hoàn thành. (15) throughput, p95/p99, active/queue wait, rejection/timeout, CPU, memory, downstream pool. (16) không được mặc định; cần context propagation theo framework.

**Kết luận:** Tách tác vụ CPU và I/O blocking trong `CompletableFuture` là việc **quản lý nơi thực thi và năng lực hệ thống**, không chỉ thêm hậu tố `Async`. Dùng `supplyAsync(..., ioExecutor)` cho API blocking, `thenApplyAsync(..., cpuExecutor)`/`thenCombineAsync(..., cpuExecutor)` cho tính toán nặng, `thenCompose` để giữ dependency graph không chặn, và quản lý bounded queue, rejection, deadline, lỗi, shutdown và context. Với **Java 21+**, virtual threads giúp mở rộng mô hình I/O blocking nhưng **không làm CPU nhanh hơn và không loại bỏ giới hạn tài nguyên**. Kiểm thử deterministic giúp chứng minh routing đúng; benchmark/load test mới giúp quyết định cách sizing thực tế.

## Tài liệu chính thức Java hiện hành

- `CompletableFuture` — async/default executor, `thenApplyAsync`, `thenCombineAsync`, `thenCompose`, `orTimeout`, `cancel`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- `CompletionStage` — quy tắc callback đồng bộ/bất đồng bộ, composition: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html
- `Executor` / `ExecutorService` — thực thi task, vòng đời và shutdown: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- `Executors` — factory cho fixed pool, thread factory và virtual threads: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html
- `ThreadPoolExecutor` — queue, sizing và rejection policy: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- `ForkJoinPool` — common pool, work stealing và các cảnh báo về blocking: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- `Semaphore` — giới hạn đồng thời bằng permit: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html
- Java 21+ virtual threads (tài liệu hiện hành của Oracle): https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html
- `HttpClient` — `send` blocking và `sendAsync`: https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html
