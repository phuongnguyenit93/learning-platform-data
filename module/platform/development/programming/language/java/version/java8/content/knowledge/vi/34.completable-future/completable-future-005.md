# CompletableFuture: Biến thể Async và lựa chọn Executor trong Java

**`CompletableFuture`** là một trong các API trọng tâm của Java 8 để mô tả **kết quả sẽ hoàn thành trong tương lai**, ghép các bước xử lý, hợp nhất nhiều tác vụ và xử lý lỗi mà không nhất thiết chặn luồng ngay ở mỗi bước. Trong các phương thức như `thenApply`, `thenApplyAsync` và `thenApplyAsync(fn, executor)`, **hậu tố `Async` và đối số `Executor` ảnh hưởng trực tiếp đến việc callback được lập lịch ở đâu**.

Đây không chỉ là vấn đề viết ít hay nhiều ký tự. Chọn sai biến thể có thể làm một thread đang hoàn thành I/O phải chạy thêm phép tính nặng, khiến nhóm thread chung bị tranh chấp, tạo tình huống chờ lẫn nhau hoặc vô tình làm ứng dụng khó đóng tài nguyên. Chọn đúng giúp phân tách công việc, giới hạn tài nguyên, giữ độ trễ dự đoán được hơn và kiểm thử dễ hơn.

Bài Knowledge này giải thích chính xác **các biến thể Async**, **quy tắc Executor mặc định**, **khi nào truyền Executor riêng**, **các nhóm thenApply / thenCompose / thenCombine / handle / whenComplete**, **thread starvation**, **backpressure**, **shutdown**, **context propagation**, các tính năng Java 9+/21+ vẫn áp dụng và nhiều ví dụ Java 17+ độc lập. Phần API cốt lõi tương thích Java 8; không sử dụng giải pháp đã lỗi thời làm hướng triển khai chính.

## 1. Mô hình: stage phụ thuộc và nơi chạy callback

Một `CompletableFuture<T>` vừa là một `Future<T>` có thể hoàn thành, vừa triển khai `CompletionStage<T>` cho phép khai báo bước xử lý tiếp theo:

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(10)
                .thenApply(x -> x + 2)
                .thenApply(x -> x * 3);

// result.join() == 36
```

Đoạn trên nằm trong một phương thức có import `java.util.concurrent.CompletableFuture`. Mỗi `thenApply` tạo một **stage mới** có kết quả riêng; việc sử dụng `thenApply` **không có nghĩa tự khởi tạo thread mới**.

Ba câu hỏi độc lập:
1. **Callback làm gì?** Ánh xạ một giá trị (`thenApply`), tiêu thụ không trả giá trị (`thenAccept`), chạy Runnable không nhận giá trị (`thenRun`), ghép future (`thenCompose`) hay kết hợp hai future (`thenCombine`)?
2. **Khi nào callback được phép chạy?** Sau khi stage trước **hoàn thành bình thường**, hoặc sau bất kỳ trạng thái hoàn thành nào trong nhóm xử lý lỗi.
3. **Callback được gửi tới đâu?** Biến thể không Async, Async dùng executor mặc định, hay Async dùng executor được cung cấp.

**Async không đổi phép tính toán học của callback; nó đổi cơ chế thực thi/lập lịch callback.** Còn `thenCompose` và `thenCombine` thay đổi cách kết hợp stage; phải chọn theo phụ thuộc dữ liệu chứ không chỉ theo thread.

## 2. Ba biến thể cần phân biệt

Giả sử `source` có kiểu `CompletableFuture<Integer>`:

| Cách viết | Nơi thực thi callback | Ý nghĩa |
| --- | --- | --- |
| `source.thenApply(fn)` | Có thể chạy trên thread hoàn thành `source`, thread gọi completion, hoặc caller đang đăng ký nếu nguồn đã xong | **Non-Async**, không bảo đảm chuyển sang pool riêng |
| `source.thenApplyAsync(fn)` | **Default asynchronous execution facility** của stage, với `CompletableFuture` chuẩn thường là `ForkJoinPool.commonPool()` | Có lập lịch bất đồng bộ, nhưng **không nêu pool riêng** |
| `source.thenApplyAsync(fn, executor)` | Gửi callback cho `executor` do caller cung cấp | Kiểm soát chính sách lập lịch theo Executor |

Dạng mẫu:

```java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> direct =
        source.thenApply(x -> x + 1);

CompletableFuture<Integer> defaultAsync =
        source.thenApplyAsync(x -> x + 1);

CompletableFuture<Integer> explicitAsync =
        source.thenApplyAsync(x -> x + 1, executor);
```

Đoạn minh họa giả định `executor` đã được khai báo và đang hoạt động. Không nên suy rằng `direct` luôn chạy trên đúng thread tạo `source`; luật của non-Async **không bảo đảm một thread duy nhất**. Cũng không suy `Async` tạo **một thread mới cho mỗi stage**: tùy Executor, task có thể chạy trên worker đã có, thread ảo, hoặc thậm chí ngay trên caller nếu dùng một Executor trực tiếp `Runnable::run`.

**Hậu tố Async chỉ có ý nghĩa cùng với Executor mà phương thức chọn.** Nó không tự bảo đảm chạy song song, tách biệt tuyệt đối, tốc độ nhanh hơn hay có thứ tự completion giống thứ tự đăng ký.

## 3. Hai dạng nguồn: `supplyAsync` và `runAsync`

`CompletableFuture` tạo tác vụ nguồn bằng hai factory phổ biến:

```java
CompletableFuture<Integer> value =
        CompletableFuture.supplyAsync(() -> 42);

CompletableFuture<Void> sideEffect =
        CompletableFuture.runAsync(() -> {
            // Một Runnable không trả dữ liệu.
        });
```

- `supplyAsync(Supplier<T>)` nhận một hàm **trả giá trị** và trả `CompletableFuture<T>`.
- `runAsync(Runnable)` nhận công việc không trả giá trị và trả `CompletableFuture<Void>`.
- Mỗi phương thức có overload nhận `Executor`, ví dụ `supplyAsync(supplier, ioExecutor)` hoặc `runAsync(action, executor)`.
- Hai factory gửi công việc tới một Executor; chúng khác `completedFuture(value)`, vốn tạo future **đã hoàn thành** và không tự gửi task.

**Không có lý do mặc định phải tạo `CompletableFuture` chỉ để thay một lời gọi đồng bộ cực ngắn.** Nếu một phép nhân đơn giản cần kết quả ngay, `supplyAsync(() -> a*b).join()` có thể chậm hơn gọi trực tiếp vì thêm scheduling rồi chờ.

`CompletableFuture` mang lại giá trị khi có thể **ghép pipeline không blocking**, chạy nhiều công việc độc lập hoặc giữ được một API bất đồng bộ qua các tầng.

## 4. Biến thể non-Async: callback có thể chạy trên thread nào?

Tài liệu `CompletableFuture` quy định callback của các dependent stage **non-Async** có thể được thực hiện bởi thread làm stage trước hoàn thành hoặc một caller của completion method. Nếu stage trước **đã hoàn thành**, callback rất thường chạy ngay trong thread đang đăng ký.

```java
String caller = Thread.currentThread().getName();

boolean observedInline =
        CompletableFuture.completedFuture(10)
                .thenApply(x ->
                        Thread.currentThread().getName()
                                .equals(caller))
                .join();
```

Đoạn minh họa dùng để **quan sát** tình huống `completedFuture` trong thực thi cụ thể; không tạo hợp đồng “thenApply luôn chạy cùng thread main” cho mọi thời điểm/race.

Điều này quan trọng khi:
- Callback **nhẹ**, thuần tính toán, không blocking: `thenApply` thường phù hợp, tránh chi phí gửi task mới.
- Callback **nặng hoặc blocking**: non-Async có thể làm nghẽn thread đang hoàn thành stage trước (event loop, thread xử lý request, thread callback I/O). Cân nhắc `thenApplyAsync(..., executor)`.
- Cần thread-affinity (UI thread hoặc thread quản lý tài nguyên): đừng trông cậy non-Async; phải sử dụng executor/dispatcher đúng contract ứng dụng.
- Stage đã hoàn thành trước khi bạn đăng ký: callback có thể xảy ra **ngay trong lời gọi `thenApply`**, không phải “lúc nào đó sau này”.

Không nói “non-Async chắc chắn chạy trên worker của source”: ngay cả khi source tạo bằng `supplyAsync(..., pool)`, thread thực thi dependent non-Async có thể khác tùy race và thời điểm callback được gắn.

## 5. Biến thể Async không truyền Executor: mặc định ở đâu?

Với `CompletableFuture` thông thường, các phương thức async không truyền Executor sử dụng **default asynchronous execution facility**. Trong tài liệu JDK, đó là `ForkJoinPool.commonPool()` khi common pool có mức parallelism thích hợp. Với cấu hình mà common pool không hỗ trợ ít nhất hai thread song song, implementation có thể dùng thread riêng cho từng task async thay thế; vì vậy **không hardcode tên thread trong test**.

Điểm chính:

```java
CompletableFuture<Integer> stage =
        CompletableFuture.completedFuture(10)
                .thenApplyAsync(x -> x + 2);
```

- Java có thể **lập lịch trên shared common pool**, không thuộc quyền sở hữu của riêng pipeline này.
- Một tác vụ blocking lâu có thể tranh tài nguyên với tác vụ khác cũng dùng common pool.
- Các thư viện khác hoặc phần khác của chương trình cũng có thể dùng common pool.
- Không có gì bảo đảm tác vụ chạy trước theo thứ tự đăng ký callback.
- Thời điểm hoàn thành và thời điểm chạy phụ thuộc scheduler, queue và tải hệ thống.
- Dùng biến thể này hợp lý cho công việc ngắn, không blocking đáng kể, khi chia sẻ common pool là chấp nhận được.

Từ **Java 9**, `CompletableFuture.defaultExecutor()` có thể được override ở subclass để thay default facility cho các method instance async. Đây là khả năng mở rộng nâng cao, **không phải điều xảy ra chỉ vì root được tạo bằng custom Executor**.

**Không tùy tiện gọi `ForkJoinPool.commonPool().shutdown()`** để kết thúc một pipeline. Common pool là tài nguyên dùng chung; executor riêng mới là thứ bạn chủ động quản lý vòng đời.

## 6. Biến thể Async truyền Executor: kiểm soát ranh giới thực thi

Nếu bạn biết tác vụ có tính chất I/O, CPU-intensive, cần isolation, giới hạn song song hoặc thread naming, hãy chủ động truyền Executor:

```java
ExecutorService ioPool =
        Executors.newFixedThreadPool(8);

CompletableFuture<String> data =
        CompletableFuture.supplyAsync(
                () -> fetchFromService(), ioPool);

CompletableFuture<Integer> size =
        data.thenApplyAsync(
                String::length, cpuPool);
```

Đây là **đoạn minh họa bên trong một phương thức**, với `fetchFromService()`, `cpuPool` và quản lý vòng đời pool do ứng dụng cung cấp. Số 8 chỉ là ví dụ, **không phải quy tắc sizing cho mọi hệ thống**.

Một `Executor` là giao diện **cách gửi Runnable để được thực thi** (`execute(Runnable)`). `ExecutorService` mở rộng khả năng quản lý shutdown, submit, chờ hoàn thành... `Executors` có nhiều factory; `ThreadPoolExecutor` cho cấu hình queue/capacity/rejection chi tiết hơn.

Khi truyền executor vào `thenApplyAsync(fn, executor)`, bạn chỉ chỉ định **executor của callback đó**, **không chuyển tự động toàn bộ pipeline** hoặc mọi stage con sang executor này. Nếu callback trả một `CompletableFuture` được tạo trên pool khác, phần công việc bên trong vẫn chạy theo executor của nó.

### Executor phù hợp không đồng nghĩa chắc chắn có thread mới

Một Executor có thể:
- Đẩy vào `ThreadPoolExecutor`.
- Dùng `ForkJoinPool`.
- Dùng một thread điều phối sự kiện.
- Tạo virtual thread theo task (Java 21+).
- Chạy ngay trong caller, ví dụ `Runnable::run`.

Do đó, **Async = có chính sách gửi qua Executor**, không phải cam kết callback được chạy ở một thread OS mới hay chắc chắn chạy song song với source. Nếu yêu cầu chạy ngoài caller, phải dùng executor có contract đáp ứng yêu cầu đó.

## 7. Chương trình Java: non-Async, thenApplyAsync, thenAcceptAsync và thenRunAsync

Tạo tệp `VariantBasicsDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class VariantBasicsDemo {
    public static void main(String[] args) {
        ExecutorService worker =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "demo-worker"));

        try {
            String caller = Thread.currentThread().getName();

            boolean inline =
                    CompletableFuture.completedFuture(10)
                            .thenApply(v ->
                                    Thread.currentThread()
                                            .getName().equals(caller))
                            .join();

            int transformed =
                    CompletableFuture.completedFuture(10)
                            .thenApplyAsync(v -> v + 5, worker)
                            .join();

            String asyncName =
                    CompletableFuture.completedFuture(10)
                            .thenApplyAsync(
                                    v -> Thread.currentThread()
                                            .getName(), worker)
                            .join();

            AtomicInteger accepted = new AtomicInteger();
            CompletableFuture<Void> accept =
                    CompletableFuture.completedFuture(12)
                            .thenAcceptAsync(accepted::set, worker);
            accept.join();

            AtomicReference<String> ran =
                    new AtomicReference<>();
            CompletableFuture<Void> end =
                    CompletableFuture.completedFuture(99)
                            .thenRunAsync(
                                    () -> ran.set(
                                            Thread.currentThread()
                                                    .getName()),
                                    worker);
            end.join();

            System.out.println("inline on caller = " + inline);
            System.out.println(
                    "thenApplyAsync value = " + transformed);
            System.out.println("explicit worker = " + asyncName);
            System.out.println(
                    "thenAcceptAsync value = " + accepted.get());
            System.out.println(
                    "thenRunAsync worker = " + ran.get());
        } finally {
            worker.shutdown();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 VariantBasicsDemo.java
java VariantBasicsDemo
```

Đầu ra đã kiểm thử:

```text
inline on caller = true
thenApplyAsync value = 15
explicit worker = demo-worker
thenAcceptAsync value = 12
thenRunAsync worker = demo-worker
```

`inline on caller = true` là kết quả quan sát **khi nguồn completedFuture đã hoàn thành**. Nó không biến non-Async thành contract thread-affinity. Các callback được gắn `worker` thì chạy trên executor tạo thread tên `demo-worker`, nên stdout có thể kiểm chứng không dựa vào common-pool thread name.

- `thenApplyAsync`: nhận `T` → trả `U`.
- `thenAcceptAsync`: nhận `T` → không trả giá trị; kết quả `CompletableFuture<Void>`.
- `thenRunAsync`: không nhận result và không trả result; chỉ chạy khi stage trước hoàn thành bình thường.
- Chúng đều có biến thể không Async và biến thể Async không truyền executor.

## 8. Chọn Executor theo đặc tính công việc

Một tiêu chí thực tiễn:

| Kiểu công việc | Lựa chọn nên cân nhắc | Vì sao? |
| --- | --- | --- |
| Phép biến đổi nhỏ không blocking | `thenApply` / non-Async | Tránh scheduling thừa |
| Công việc CPU-bound đáng kể | Executor giới hạn theo tài nguyên CPU | Tách khỏi thread I/O; kiểm soát độ tranh chấp |
| Chờ I/O blocking (JDBC/HTTP blocking) | I/O executor riêng, bounded concurrency, hoặc virtual threads Java 21+ | Tránh chiếm common pool bởi wait |
| Async I/O thật sự không chặn thread | Tiếp tục bằng CompletionStage/callback phù hợp | Không cần bọc trong `supplyAsync(...).join()` |
| Nhiều tenant / nghiệp vụ có SLA khác | Executor/queue/bulkhead có cách ly | Một tenant không làm nghẽn tất cả |
| UI hoặc framework event loop | Executor/dispatcher do framework cung cấp | Callback về đúng thread/loop theo contract |
| Công việc có deadline và backpressure | Executor quản lý queue/rejection/timeout | Tránh queue dài vô hạn và độ trễ ẩn |

**Không có một con số “pool size tốt nhất” cho mọi ứng dụng.** Với CPU-bound, có thể bắt đầu từ khả năng CPU có sẵn rồi đo thực tế; với I/O blocking cần xét số kết nối, khoảng chờ, tài nguyên upstream và mức đồng thời được phép. Số thread cao không tự làm database có nhiều connection hơn.

Nếu có hai nhóm việc khác nhau, một thiết kế thường hợp lý là **ioPool** cho tác vụ chờ I/O và **cpuPool** cho biến đổi CPU, đồng thời cấu hình queue, giới hạn tác vụ pending, timeout, monitoring và vòng đời.

## 9. Chương trình Java: hai executor riêng cho nguồn và kết hợp

Tạo `SupplyAndCombineDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class SupplyAndCombineDemo {
    public static void main(String[] args) {
        AtomicInteger ioSeq = new AtomicInteger();
        AtomicInteger cpuSeq = new AtomicInteger();

        ExecutorService io = Executors.newFixedThreadPool(
                2, r -> new Thread(
                        r, "io-" + ioSeq.incrementAndGet()));

        ExecutorService cpu = Executors.newFixedThreadPool(
                2, r -> new Thread(
                        r, "cpu-" + cpuSeq.incrementAndGet()));

        try {
            CompletableFuture<String> word =
                    CompletableFuture.supplyAsync(
                            () -> "Java", io);
            CompletableFuture<Integer> number =
                    CompletableFuture.supplyAsync(
                            () -> 4, io);

            CompletableFuture<String> combined =
                    word.thenCombineAsync(
                            number,
                            (w, n) -> w.toUpperCase(Locale.ROOT)
                                    + "-" + n,
                            cpu);

            CompletableFuture<String> tested =
                    combined.thenApplyAsync(
                            v -> Thread.currentThread()
                                    .getName().startsWith("cpu-")
                                    + " " + v,
                            cpu);

            System.out.println(
                    "combine result = " + tested.join());

            CompletableFuture<Void> ran =
                    CompletableFuture.runAsync(() -> {}, io);
            ran.join();

            System.out.println(
                    "runAsync completed = " + ran.isDone());
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 SupplyAndCombineDemo.java
java SupplyAndCombineDemo
```

```text
combine result = true JAVA-4
runAsync completed = true
```

Hai tác vụ nguồn có thể hoàn thành theo **bất kỳ thứ tự nào**; `thenCombineAsync` chỉ chạy callback ghép **sau khi cả hai nguồn hoàn thành bình thường** và gửi callback vào `cpu`. Ta in giá trị cuối, không giả định thread `io-1` luôn chạy task nào trước.

`thenCombineAsync(other, fn, cpu)` còn minh họa việc **Executor của stage kết hợp** không cần giống executor của hai nguồn. Nếu cả hai nguồn đã thất bại, stage kết hợp có thể hoàn thành exceptionally; exception propagation cần được xử lý ở tầng thích hợp.

## 10. Một hiểu lầm quan trọng: Executor nguồn không tự “di truyền” cho Async tiếp theo

Đoạn code:

```java
CompletableFuture<String> root =
        CompletableFuture.supplyAsync(
                () -> fetch(), customExecutor);

CompletableFuture<String> later =
        root.thenApplyAsync(String::trim);
```

Đây là đoạn minh họa có `fetch()` và `customExecutor` được quản lý bởi ứng dụng. **`later` không tự kế thừa `customExecutor` chỉ vì `root` được tạo bằng `supplyAsync(..., customExecutor)`.**

Với `CompletableFuture` chuẩn, `thenApplyAsync(fn)` hỏi **default async executor của stage**, thường là common pool, không phải “executor đã thực thi source trước đó”. Muốn dùng chính custom executor cho callback:

```java
CompletableFuture<String> later =
        root.thenApplyAsync(String::trim, customExecutor);
```

Đây cũng là lý do việc đặt tên thread và log giai đoạn **không đủ để suy ra** toàn bộ chuỗi đang ở pool nào. Hãy truyền executor có chủ đích tại **mỗi ranh giới cần kiểm soát**.

Có trường hợp mở rộng class `CompletableFuture` (Java 9+) bằng `defaultExecutor()` và `newIncompleteFuture()`, nhưng đấy là cơ chế override riêng của subclass, **không phải hành vi mặc định của CompletableFuture**. Trong code ứng dụng thường nên minh bạch ở các overload có tham số Executor thay vì phụ thuộc subclass tinh vi.

## 11. Chương trình Java: nguồn custom nhưng Async tiếp theo dùng default

Tạo `DefaultExecutorDemo.java`:

```java
import java.util.concurrent.*;

public class DefaultExecutorDemo {
    public static void main(String[] args) {
        ExecutorService rootExecutor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "custom-root"));

        try {
            CompletableFuture<String> root =
                    CompletableFuture.supplyAsync(
                            () -> "OK", rootExecutor);

            CompletableFuture<String> noArg =
                    root.thenApplyAsync(
                            v -> Thread.currentThread().getName());

            CompletableFuture<String> explicit =
                    root.thenApplyAsync(
                            v -> Thread.currentThread().getName(),
                            rootExecutor);

            System.out.println("root value = " + root.join());
            System.out.println(
                    "default continuation on custom-root = " +
                            noArg.join().equals("custom-root"));
            System.out.println(
                    "explicit continuation thread = " +
                            explicit.join());
        } finally {
            rootExecutor.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 DefaultExecutorDemo.java
java DefaultExecutorDemo
```

```text
root value = OK
default continuation on custom-root = false
explicit continuation thread = custom-root
```

Chúng ta **không in tên thread mặc định** (tên thread common pool thay đổi theo cấu hình/JDK). Chỉ kiểm tra rằng nó **không phải worker mang tên `custom-root`**, trong khi overload có truyền executor chạy trên worker custom.

**Đây là hành vi được quan sát với CompletableFuture chuẩn và common pool của môi trường kiểm thử.** Khi dùng custom subclass override `defaultExecutor()`, hoặc một Executor rất đặc biệt, phải xét contract tương ứng; không dựa vào phép đo này để suy “mọi hệ thống có đúng cùng thread name”.

## 12. `thenApply` so với `thenCompose`: ánh xạ hay làm phẳng future?

Không nên chọn `thenComposeAsync` chỉ vì nghe có vẻ “song song hơn”. Cốt lõi là **kiểu kết quả của callback**.

Giả sử `lookupAsync(id)` trả `CompletableFuture<User>`. Khi từ `id` sang một future khác:

```java
CompletableFuture<CompletableFuture<User>> nested =
        idFuture.thenApply(id -> lookupAsync(id));
```

Vì callback trả `CompletableFuture<User>`, `thenApply` tạo **future lồng future**.

Nếu muốn pipeline cuối trả `CompletableFuture<User>` trực tiếp:

```java
CompletableFuture<User> flat =
        idFuture.thenCompose(id -> lookupAsync(id));
```

`thenCompose` **làm phẳng** stage trả về, tương đương ý tưởng `flatMap`; không chặn bằng `join()` bên trong callback.

Có hai biến thể khi cần điều phối vị trí chạy hàm tạo stage:

```java
idFuture.thenComposeAsync(id -> lookupAsync(id));
idFuture.thenComposeAsync(id -> lookupAsync(id), executor);
```

Hàm `id -> lookupAsync(id)` được lập lịch theo async facility hoặc executor chỉ định. Nhưng **công việc bên trong future do `lookupAsync` trả về vẫn chạy theo executor/cơ chế của chính nó**; `thenComposeAsync(..., cpuPool)` không tự chuyển toàn bộ I/O của `lookupAsync` sang cpuPool.

Đây là những đoạn minh họa trong service có `User`, `idFuture`, `lookupAsync` và `executor` đã tồn tại. Ví dụ runnable ngay sau dùng số nguyên để chứng minh kiểu/kết quả.

## 13. Chương trình Java: nested future vs flattened future

Tạo `ComposeVsApplyDemo.java`:

```java
import java.util.concurrent.*;

public class ComposeVsApplyDemo {
    public static void main(String[] args) {
        ExecutorService one =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "compose-worker"));

        try {
            CompletableFuture<CompletableFuture<Integer>> nested =
                    CompletableFuture.completedFuture(3)
                            .thenApply(
                                    v -> CompletableFuture.supplyAsync(
                                            () -> v * 10, one));

            CompletableFuture<Integer> flat =
                    CompletableFuture.completedFuture(3)
                            .thenComposeAsync(
                                    v -> CompletableFuture.supplyAsync(
                                            () -> v * 10, one),
                                    one);

            System.out.println(
                    "nested type contains future = " +
                            (nested.join()
                                    instanceof CompletableFuture));
            System.out.println(
                    "nested value = " + nested.join().join());
            System.out.println(
                    "flattened value = " + flat.join());
        } finally {
            one.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ComposeVsApplyDemo.java
java ComposeVsApplyDemo
```

```text
nested type contains future = true
nested value = 30
flattened value = 30
```

`nested.join().join()` chỉ xuất hiện ở **main để minh họa kiểu lồng nhau**, không nằm trong worker callback; nó chờ outer rồi inner. Trong ứng dụng thật, dùng `thenCompose` sẽ tránh phải lồng xử lý future.

Ví dụ `flat` không deadlock trên single-thread executor vì callback `thenComposeAsync` **tạo và trả inner future ngay**, không `join()` nó trong cùng worker. Inner task được chạy sau khi callback ngoài trả lại worker.

**Phản ví dụ nguy hiểm:** gọi `CompletableFuture.supplyAsync(..., sameSingleThreadExecutor).join()` **bên trong** một task cũng đang chiếm thread duy nhất của executor đó. Inner task không có worker rảnh để chạy, outer task vẫn chờ, gây **thread starvation deadlock**.

## 14. Các nhóm combinator khác và biến thể Async

Từ `CompletionStage` có các họ phương thức:

| Mục đích | Non-Async | Async default | Async explicit |
| --- | --- | --- | --- |
| Biến đổi `T → U` | `thenApply(fn)` | `thenApplyAsync(fn)` | `thenApplyAsync(fn, ex)` |
| Tiêu thụ `T → void` | `thenAccept(action)` | `thenAcceptAsync(action)` | `thenAcceptAsync(action, ex)` |
| Chạy Runnable sau success | `thenRun(action)` | `thenRunAsync(action)` | `thenRunAsync(action, ex)` |
| Ghép future phụ thuộc | `thenCompose(fn)` | `thenComposeAsync(fn)` | `thenComposeAsync(fn, ex)` |
| Ghép **hai** kết quả normal | `thenCombine(other, fn)` | `thenCombineAsync(other, fn)` | `thenCombineAsync(other, fn, ex)` |
| Tiêu thụ hai kết quả | `thenAcceptBoth(other, action)` | `thenAcceptBothAsync(other, action)` | `thenAcceptBothAsync(other, action, ex)` |
| Khi cả hai normal, chạy Runnable | `runAfterBoth(other, action)` | `runAfterBothAsync(other, action)` | `runAfterBothAsync(other, action, ex)` |
| Chọn kết quả **bình thường** xuất hiện trước | `applyToEither(other, fn)` | `applyToEitherAsync(other, fn)` | `applyToEitherAsync(other, fn, ex)` |
| Một trong hai normal → tiêu thụ | `acceptEither(other, action)` | `acceptEitherAsync(other, action)` | `acceptEitherAsync(other, action, ex)` |
| Một trong hai hoàn thành normal → chạy Runnable | `runAfterEither(other, action)` | `runAfterEitherAsync(other, action)` | `runAfterEitherAsync(other, action, ex)` |
| Quan sát normal/error | `whenComplete(action)` | `whenCompleteAsync(action)` | `whenCompleteAsync(action, ex)` |
| Chuyển cả result/error thành value | `handle(fn)` | `handleAsync(fn)` | `handleAsync(fn, ex)` |

Phân biệt:
- `thenCombine` cần **hai nguồn đều hoàn thành bình thường** để dùng cả hai giá trị.
- `applyToEither` phục vụ **một kết quả bình thường** đầu tiên; cách giải quyết exceptional completion phải theo quy tắc `CompletionStage`, không coi là "cứ future nào xong trước dù lỗi" mà luôn thắng.
- `CompletableFuture.anyOf(...)` trả future hoàn thành theo **một nguồn bất kỳ**, kể cả exceptional completion, và thường trả `CompletableFuture<Object>`; khác kiểu/ý nghĩa với `applyToEither`.
- `CompletableFuture.allOf(...)` tạo `CompletableFuture<Void>` hoàn thành khi **tất cả** future tham gia hoàn thành; muốn lấy giá trị phải truy cập riêng các future nguồn hoặc có cách ghép kiểu.
- `thenRun` không nhận result; nếu cần giá trị, chọn `thenAccept`/`thenApply` phù hợp.

**Không có một overload `Async` riêng cho mọi factory hoặc mọi helper**. `allOf` và `anyOf` bản thân là các phương thức tổng hợp completion, không nhận `Executor`; muốn xử lý kết quả trên pool riêng, gắn tiếp `thenRunAsync`/`thenApplyAsync` với executor khi cần.

## 15. Lựa chọn hợp lý giữa đồng bộ, non-Async và async

Ví dụ pipeline:
1. Gọi dịch vụ lấy bản ghi (blocking I/O).
2. Chuẩn hóa dữ liệu trả về bằng thao tác rất nhẹ.
3. Tính toán CPU đáng kể.
4. Ghi kết quả vào một hệ thống ngoài.

Một thiết kế hợp lý là:

```java
CompletableFuture<Result> pipeline =
        CompletableFuture.supplyAsync(
                () -> fetchBlocking(), ioExecutor)
                .thenApply(raw -> normalize(raw))
                .thenApplyAsync(data -> compute(data), cpuExecutor)
                .thenCompose(data -> persistAsync(data));
```

Đây là **mã thiết kế minh họa** trong class có `Result`, `fetchBlocking`, `normalize`, `compute`, `persistAsync`, `ioExecutor` và `cpuExecutor` thuộc ứng dụng. Điều quan trọng:
- `fetchBlocking` nằm ở I/O executor riêng, không mặc định dùng common pool.
- `normalize` nhẹ dùng non-Async để tránh hop thừa.
- `compute` tốn CPU được gửi vào cpuExecutor có giới hạn.
- `persistAsync` **đã trả CompletionStage** nên dùng `thenCompose` và không join bên trong worker.
- Callback tạo `persistAsync` có thể chạy trên thread completion của `compute`; nếu bản thân việc **khởi tạo** I/O cũng blocking đáng kể thì cần thiết kế lại ranh giới executor.

Nếu `persistAsync` thực sự asynchronous nonblocking, không cần bọc thêm bằng `supplyAsync(() -> persistAsync(...).join())`. Điều đó biến một công việc có thể không blocking thành **chiếm thread để chờ**, có thể phá mục tiêu của pipeline.

## 16. Kết quả lỗi: callback nào chạy, callback nào bị bỏ qua?

`CompletableFuture` có **normal completion** (thành công) và **exceptional completion** (thất bại hoặc cancellation). Tác động:

- `thenApply` / `thenApplyAsync` / `thenAcceptAsync` / `thenComposeAsync` chạy phần hành động chính **chỉ khi stage upstream thành công**. Nếu upstream thất bại, stage dependent thường hoàn thành exceptionally, không chạy function thành công.
- `whenComplete` / `whenCompleteAsync` nhận `(value, throwable)` để **quan sát** cả thành công lẫn lỗi; không phải API chính để đổi lỗi thành fallback.
- `handle` / `handleAsync` nhận `(value, throwable)`, **chuyển cả success/error thành một giá trị mới** có thể khác kiểu.
- `exceptionally(fn)` chỉ chạy khi thất bại và có thể tạo fallback cùng kiểu.
- `exceptionallyAsync(fn)` và `exceptionallyComposeAsync(fn)` được thêm ở các JDK mới hơn Java 8 (Java 12+): vẫn là API hiện hành, nhưng **không biên dịch trên Java 8**.
- `join()` có thể ném `CompletionException` (hoặc `CancellationException` đối với cancellation); `get()` dùng checked exceptions như `ExecutionException` / `InterruptedException`.

```java
CompletableFuture<Integer> failed =
        CompletableFuture.supplyAsync(
                () -> {
                    throw new IllegalStateException("bad");
                }, executor);

CompletableFuture<String> recovered =
        failed.handleAsync((value, error) ->
                error != null ? "fallback" : "ok:" + value,
                executor);
```

Đây là đoạn minh họa trong một phương thức có `executor` quản lý ở ngoài.

**Async biến đổi nơi chạy callback xử lý lỗi, không tự biến lỗi thành success.** Nếu dùng `whenCompleteAsync` để log error, stage đó thông thường vẫn giữ exceptional completion; `handleAsync` hoặc `exceptionally` mới tạo fallback phù hợp.

## 17. Chương trình Java: `handleAsync`, `whenCompleteAsync` và callback bị bỏ qua

Tạo `ErrorsAndCallbacksDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ErrorsAndCallbacksDemo {
    public static void main(String[] args) {
        ExecutorService worker =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "error-worker"));

        try {
            AtomicInteger observed = new AtomicInteger();
            AtomicBoolean mapped = new AtomicBoolean();

            CompletableFuture<Integer> failed =
                    CompletableFuture.supplyAsync(
                            () -> {
                                throw new IllegalStateException(
                                        "boom");
                            },
                            worker);

            CompletableFuture<String> handled =
                    failed.handleAsync(
                            (v, ex) ->
                                    ex == null ? "ok" : "fallback",
                            worker);

            CompletableFuture<Integer> watched =
                    failed.whenCompleteAsync(
                            (v, ex) -> observed.incrementAndGet(),
                            worker);

            CompletableFuture<Integer> skipped =
                    failed.thenApplyAsync(
                            v -> {
                                mapped.set(true);
                                return v + 1;
                            },
                            worker);

            String kind = "none";
            try {
                watched.join();
            } catch (CompletionException ex) {
                kind = ex.getCause()
                        .getClass().getSimpleName();
            }

            try {
                skipped.join();
            } catch (CompletionException ignored) {
                // Đang minh họa việc callback success bị bỏ qua.
            }

            System.out.println(
                    "handled = " + handled.join());
            System.out.println(
                    "watched error cause = " + kind);
            System.out.println(
                    "observer count = " + observed.get());
            System.out.println(
                    "thenApplyAsync ran = " + mapped.get());
        } finally {
            worker.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ErrorsAndCallbacksDemo.java
java ErrorsAndCallbacksDemo
```

```text
handled = fallback
watched error cause = IllegalStateException
observer count = 1
thenApplyAsync ran = false
```

Giải thích:
- `failed` ném `IllegalStateException` ở trong Supplier, vì vậy future hoàn thành exceptionally.
- `handleAsync` được gửi vào `worker` và tạo fallback `"fallback"`.
- `whenCompleteAsync` vẫn chạy để ghi một lượt quan sát, nhưng **không nuốt lỗi nguồn**; `watched.join()` vẫn ném `CompletionException` có cause `IllegalStateException`.
- `thenApplyAsync` không chạy lambda vì upstream thất bại, nên `mapped` vẫn false.

Ví dụ catch có chủ đích trong chương trình nhỏ để in kết quả. Trong code production, không nên catch `CompletionException` rồi im lặng nếu không có một chính sách lỗi phù hợp.

## 18. Executor cho CPU-bound và blocking I/O: chọn theo đặc tính, không theo tên

**CPU-bound**: tác vụ tính toán sử dụng CPU liên tục. Tạo hàng nghìn platform threads thường không làm phép tính nhanh hơn; cần giới hạn cạnh tranh theo số lõi thực tế, quota container và loại workload. `ForkJoinPool`/`Executors.newFixedThreadPool`/pool ứng dụng tùy nhu cầu; benchmark bằng tải đại diện.

**Blocking I/O**: task dành nhiều thời gian chờ socket, database, file hoặc dịch vụ ngoài. Nếu dùng common pool cho rất nhiều task chặn lâu, các stage khác có thể bị đói worker. Có thể dùng:
- **Executor riêng** cho nhóm I/O, kèm giới hạn số task đang chạy/chờ.
- API **asynchronous thật** nếu thư viện đã trả stage/publisher nonblocking, không chặn worker để gọi `join()`.
- **Virtual threads (Java 21+)** cho nhiều blocking operations phù hợp, kèm semaphore/connection limits để không vượt năng lực dịch vụ ngoài.

Đừng nhầm `Executors.newCachedThreadPool()` với một pool có giới hạn cứng: nó có thể tăng số thread theo tải. `newFixedThreadPool(n)` giới hạn worker nhưng mặc định dùng **queue không giới hạn dung lượng** theo kiểu factory này, vì vậy backlog có thể tăng quá mức nếu upstream gửi việc nhanh hơn khả năng xử lý.

Một giải pháp production phải xét **capacity**, **queue**, **rejection**, **rate limiting**, **bulkhead**, **timeouts** và cả downstream service constraints. Số thread không đồng nghĩa số kết nối hay throughput vô hạn.

## 19. Thread starvation deadlock: gọi `join()` ở sai nơi

Một phản ví dụ quan trọng với executor chỉ có một thread:

```java
ExecutorService single =
        Executors.newSingleThreadExecutor();

CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> inner =
                    CompletableFuture.supplyAsync(
                            () -> 7, single);
            return inner.join(); // NGUY HIỂM!
        }, single);

// outer.join() có thể chờ mãi.
```

**Không chạy đoạn này** như một bài kiểm thử tự động: nó minh họa deadlock. Worker duy nhất của `single` đang chạy `outer`, trong khi `inner` nằm trong hàng đợi của cùng executor. `outer` đợi `inner`, `inner` không có worker để chạy.

Cách tốt hơn:

```java
CompletableFuture<Integer> safe =
        CompletableFuture.completedFuture(0)
                .thenCompose(unused ->
                        CompletableFuture.supplyAsync(
                                () -> 7, single));
```

Ở đây `thenCompose` **trả inner future** thay vì `join` nó trong task đang chiếm worker. `safe.join()` có thể được gọi ở boundary có chủ đích (ví dụ main/test), nhưng không nên chặn thread điều phối cùng một pool có thể bị đói.

Trên fixed pool nhiều thread vẫn có thể có **thread starvation** nếu toàn bộ worker đang chờ tác vụ phụ thuộc cũng xếp trong queue đó. Không nên “chữa” bằng cách tăng pool size tùy tiện mà vẫn giữ mô hình blocking dependencies kém an toàn.

## 20. Rejection, queue và backpressure

Một Executor có thể **từ chối task** khi đang đóng hoặc đạt giới hạn; `ThreadPoolExecutor` có thể dùng `RejectedExecutionHandler` để quyết định chính sách. Dạng mẫu sản xuất (**đoạn cấu hình minh họa, cần quản lý lifecycle và giám sát**):

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        Executors.defaultThreadFactory(),
        new ThreadPoolExecutor.AbortPolicy());
```

Đoạn mã trong phương thức với `import java.util.concurrent.*;`. Ý nghĩa:
- Ít nhất 2 core threads, tối đa 4 workers.
- Queue có sức chứa 100 task.
- Khi đã hết khả năng tiếp nhận, policy `AbortPolicy` có thể ném `RejectedExecutionException`.
- `keepAliveTime` có ý nghĩa cho workers vượt core size theo quy tắc pool.
- Đây **không phải cấu hình tối ưu sẵn**; cần benchmark và monitoring theo tải/độ dài công việc.

Đừng dựa vào việc `CompletableFuture` luôn **nuốt `RejectedExecutionException` thành future bị lỗi**: lỗi khi `Executor.execute` bị từ chối có thể xuất hiện ở thời điểm đăng ký/chuyển callback hoặc qua exceptional completion tùy luồng thực thi. Hãy test thư viện/runtime và có chiến lược kiểm soát capacity.

Các rejection policies khác như `CallerRunsPolicy` có thể thực thi task trên caller để làm chậm producer, nhưng đổi thread chạy và độ trễ của caller. **Không chọn policy mà không đánh giá ý nghĩa đối với request thread/event loop**.

Giới hạn **tác vụ pending** cũng quan trọng: một queue lớn có thể làm application chờ lâu dù số threads cố định. Đôi khi nên trả lỗi quá tải hoặc giảm tốc producer sớm hơn thay vì chất hàng ngàn tác vụ để rồi hết timeout.

## 21. Executor lifecycle: ai tạo thì ai đóng?

Một `ExecutorService` tự tạo từ `Executors` giữ tài nguyên thread/queue. Trong ví dụ nhỏ:

```java
ExecutorService executor =
        Executors.newFixedThreadPool(2);
try {
    CompletableFuture<Integer> task =
            CompletableFuture.supplyAsync(
                    () -> 42, executor);
    System.out.println(task.join());
} finally {
    executor.shutdown();
}
```

Đây là đoạn code đặt trong method có import `java.util.concurrent.*`. `shutdown()` yêu cầu **ngừng nhận task mới** và cho phép task đã được gửi tiếp tục, **không tự chờ mọi task kết thúc**. Với service cần lifecycle hoàn chỉnh, dùng `awaitTermination`/cancellation theo chính sách và bảo đảm không còn người gửi task.

Các nguyên tắc quan trọng:
- Nếu **tự tạo executor** trong thành phần, thành phần ấy cần chính sách đóng.
- Nếu **được inject một executor dùng chung**, không tự ý shutdown nó khi một future hoàn thành.
- Đừng đóng executor ngay sau `supplyAsync` nếu pipeline còn các `thenApplyAsync(..., sameExecutor)` chưa được lập lịch; stage sau có thể bị từ chối.
- Không tự gọi shutdown cho common pool.
- Trong ứng dụng web/server, executor thường do container/framework quản lý; hãy dùng lifecycle hooks của framework.
- Cân nhắc giữ executor **tái sử dụng**, không tạo một pool mới cho mỗi request; tạo pool liên tục gây chi phí và khó kiểm soát.

JDK hiện đại còn hỗ trợ `ExecutorService.close()` / try-with-resources trong các phiên bản hỗ trợ; các chương trình đầy đủ ở đây dùng **`try/finally + shutdown()`** để tương thích và minh bạch trên JDK 17+. `close()` có semantics chờ completion khác `shutdown()`, nên khi nâng cấp JDK cần đọc contract cụ thể thay vì coi chúng là tên gọi thay thế đơn giản.

## 22. Timeout không tự dừng công việc nguồn

`CompletableFuture.orTimeout(timeout, unit)` (Java 9+) giúp **hoàn thành future theo lỗi TimeoutException nếu chưa xong đúng hạn**. `completeOnTimeout(value, timeout, unit)` (Java 9+) cung cấp giá trị fallback nếu chưa xong.

Cần nhớ:
- Hai method này **thay đổi chính CompletableFuture receiver** và trả nó, không giống `thenApply` tạo stage mới độc lập.
- Timeout của future **không tự hủy mọi I/O underlying** hoặc bảo đảm ngắt thread.
- `cancel(true)` trên `CompletableFuture` có semantics **exceptional completion**; tham số `mayInterruptIfRunning` **không có tác dụng điều khiển interruption** đối với tác vụ underlying như một số `FutureTask`.
- Với I/O thật, phải kết hợp timeout của HTTP client/driver, cancellation thực sự, deadline end-to-end và xử lý tài nguyên.

`CompletableFuture.delayedExecutor(delay, unit, executor)` (Java 9+) trả về một **Executor wrapper trì hoãn việc gửi task** đến executor đích, không yêu cầu `Thread.sleep` trong một worker. Thành phần dùng để trigger delay không có nghĩa Supplier được chạy trên thread timer đó; Supplier được gửi tới base executor theo hợp đồng.

Đối với chỉ một lần delay không cần executor riêng, có overload `delayedExecutor(delay, unit)` dùng default async facility.

**Không dùng timeout như một cơ chế backpressure thay cho giới hạn đồng thời.** Task nguồn có thể còn chạy sau khi result future đã timeout, tiếp tục chiếm kết nối hoặc tài nguyên.

## 23. Chương trình Java: delayedExecutor với executor riêng và shutdown

Tạo `DelayedAndShutdownDemo.java`:

```java
import java.util.concurrent.*;

public class DelayedAndShutdownDemo {
    public static void main(String[] args) {
        ExecutorService ex =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "delay-worker"));

        try {
            Executor delayed =
                    CompletableFuture.delayedExecutor(
                            0, TimeUnit.MILLISECONDS, ex);

            CompletableFuture<String> f =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread().getName(),
                            delayed);

            System.out.println("delayed worker = " + f.join());

            System.out.println("delayed value = " +
                    CompletableFuture.supplyAsync(
                                    () -> 41, delayed)
                            .thenApplyAsync(v -> v + 1, ex)
                            .join());
        } finally {
            ex.shutdown();
        }

        System.out.println(
                "executor shutdown = " + ex.isShutdown());
    }
}
```

```bash
javac -encoding UTF-8 DelayedAndShutdownDemo.java
java DelayedAndShutdownDemo
```

```text
delayed worker = delay-worker
delayed value = 42
executor shutdown = true
```

Delay đặt bằng **0** để mẫu chạy nhanh và không phụ thuộc scheduler. Nếu đặt delay > 0, thời điểm bắt đầu có thể trễ hơn giá trị định sẵn vì scheduler và tải; không dùng nó để cam kết thực thi chính xác tới nanosecond.

Executor `ex` thuộc phạm vi `main` và đã dùng xong trước khi shutdown. **Không lấy pattern đóng executor ngay sau supplyAsync mà không chờ dependent stage** trong ứng dụng production; tất cả continuation cần executor phải có cơ hội được lập lịch trước khi pool đóng.

## 24. ThreadLocal, MDC, security context và tracing

Các framework thường lưu context ở `ThreadLocal` hoặc các cơ chế gắn với execution context:
- Request ID/correlation ID.
- Logging MDC.
- Security principal.
- Transaction context.
- Locale/tenant.
- OpenTelemetry tracing span.

Khi chuyển từ thread caller sang thread của Executor bằng `thenApplyAsync`, **không được giả định context trong ThreadLocal sẽ tự truyền theo**. Một worker có thể được tái sử dụng cho nhiều request và chứa giá trị khác của request trước nếu code không reset đúng.

Ví dụ **mẫu wrapper minh họa**:

```java
String requestId = RequestContext.currentId();

CompletableFuture<String> stage =
        upstream.thenApplyAsync(value -> {
            String previous = RequestContext.currentId();
            try {
                RequestContext.setId(requestId);
                return service.process(value);
            } finally {
                RequestContext.setId(previous);
            }
        }, executor);
```

Đây là **đoạn minh họa không độc lập**: `RequestContext`, `upstream` và `service` là API giả định của ứng dụng. Ý nghĩa là **capture context trước khi đổi thread**, đặt context trong worker rồi khôi phục trạng thái cũ trong `finally`. Với framework thực, ưu tiên integration/context-propagation library tương ứng thay vì tự xây wrapper tràn lan.

**Không truyền transaction JDBC thread-bound sang worker khác** rồi giả định nó vẫn hợp lệ. Hợp đồng resource/transaction của framework mới quyết định có thể di chuyển xử lý giữa các thread không.

## 25. Virtual threads (Java 21+) là lựa chọn hiện đại, không phải thay thế mọi pool

Từ Java 21, virtual threads là tính năng ổn định. `Executors.newVirtualThreadPerTaskExecutor()` tạo một executor sử dụng **virtual thread mới cho mỗi task**:

```java
// Chỉ chạy trên JDK 21+; KHÔNG biên dịch trên Java 17.
try (ExecutorService io =
        Executors.newVirtualThreadPerTaskExecutor()) {

    CompletableFuture<String> f =
            CompletableFuture.supplyAsync(
                    () -> blockingRead(), io);

    System.out.println(f.join());
}
```

Đây là **đoạn thiết kế JDK 21+**, giả định `blockingRead()` của ứng dụng và `import java.util.concurrent.*;`, không phải chương trình Java 17 độc lập. Thích hợp cho nhiều tác vụ kiểu blocking I/O có khả năng scale tốt khi được dùng đúng.

Cần hiểu:
- Virtual threads **không làm phép tính CPU tự nhiên nhanh hơn**.
- Executor theo task **không giới hạn số task** chỉ vì là virtual threads; vẫn cần hạn chế số request tới database/upstream theo capacity.
- Không dùng `ThreadLocal` như một cơ chế cache tài nguyên lớn gắn cố định với mỗi request mà không cân nhắc số lượng task/threads.
- Các tình huống pinning hoặc native blocking tùy JDK/framework có thể ảnh hưởng lợi ích; phải đo và cập nhật runtime hiện hành.
- `CompletableFuture` vẫn có thể ghép pipeline; việc dùng virtual threads có khi cho phép viết code blocking đơn giản hơn, nhưng không buộc phải bọc tất cả bằng `supplyAsync`.

Đặc biệt, **có từ Java 21** chứ không thuộc Java 8; tách biệt version để người học Java 8 không nghĩ phương thức tồn tại ở compiler cũ. Đây là hướng triển khai còn dùng ngày nay, không phải API legacy.

## 26. Kiểm thử CompletableFuture Async mà không phụ thuộc timing may rủi

Test dùng `Thread.sleep(100)` rồi suy “callback chắc chắn đã chạy” thường flaky khi scheduler hoặc máy CI chậm.

Thay vào đó:
1. Tạo executor riêng với tên thread xác định nếu cần kiểm tra **executor lựa chọn**.
2. Dùng `CompletableFuture.completedFuture(value)` khi chỉ muốn test callback trên một stage có kết quả đã sẵn.
3. Dùng `new CompletableFuture<>()` để điều khiển lúc hoàn thành trong test.
4. Dùng `CountDownLatch` hoặc `Phaser` khi phải kiểm soát thứ tự giữa các thread, nhưng **không chặn worker đang chờ chính công việc nằm ở executor đó**.
5. Dùng `join()` ở **test boundary** để biết các kết quả cần thiết đã có trước khi assert.
6. Không assert common-pool thread name cụ thể hay thứ tự scheduling độc lập.
7. Dùng `try/finally` để shutdown executor sau khi mọi stage cần nó đã hoàn tất.
8. Xác thực cả **normal completion** lẫn **exceptional completion**, callback được chạy hoặc không được chạy.
9. Với timeout, dùng timeout test đủ rõ và điều khiển completion nhân tạo thay vì sleep chính xác từng millisecond.
10. Chạy tải tích hợp để phát hiện queue buildup, rejection và thread starvation, vì unit test giá trị đúng không chứng minh production không nghẽn.

Ví dụ trong một phương thức test:

```java
CompletableFuture<Integer> source =
        new CompletableFuture<>();
CompletableFuture<Integer> stage =
        source.thenApplyAsync(x -> x * 2, executor);

source.complete(21);
int result = stage.join();
// result == 42
```

**Đây là snippet minh họa** cần `executor` đang hoạt động. Kết quả là 42, không có yêu cầu phụ thuộc vào số milliseconds mà callback chạy. Nếu cần assert thread nơi chạy, nên dùng tên thread do ThreadFactory của executor test tạo ra và không dựa vào scheduling của common pool.

## 27. Thực hành thiết kế API giữa các tầng

Một API trả `CompletableFuture<T>` thường không nên quyết định một cách bí mật mọi thread trong hệ thống. Có thể chọn một trong các chiến lược:
- **Inject Executor** vào service, dùng explicit overload ở những bước do service sở hữu.
- Cho phép caller truyền Executor trong một API đặc biệt nếu use case thực sự cần thread policy từ caller.
- Giữ phần transformation non-blocking ở pipeline; chỉ chuyển executor tại các **ranh giới tốn tài nguyên**.
- Nếu dùng framework (web/reactive/event loop), tuân thủ scheduler/dispatch policy của framework thay vì tự tạo pool cho mỗi lời gọi.
- Ghi tài liệu về việc API có thể hoàn thành **synchronously/inline**, khả năng blocking, exception propagation, cancellation và ai quản lý executor.
- Đặt các timeout/capacity limits ở biên I/O thay vì chỉ timeout stage cuối.
- Tránh đánh đồng “API trả CompletableFuture” với “đã thật sự asynchronous và non-blocking”: một phương thức có thể hoàn thành future ngay, hoặc làm blocking trước khi trả future.

Ví dụ pattern:

```java
class ProfileService {
    private final Executor ioExecutor;
    private final Executor cpuExecutor;

    ProfileService(
            Executor ioExecutor, Executor cpuExecutor) {
        this.ioExecutor = ioExecutor;
        this.cpuExecutor = cpuExecutor;
    }

    CompletableFuture<String> loadProfile(String userId) {
        return CompletableFuture.supplyAsync(
                        () -> fetchBlocking(userId),
                        ioExecutor)
                .thenApply(String::trim)
                .thenApplyAsync(
                        value -> transform(value),
                        cpuExecutor);
    }

    // fetchBlocking(...) và transform(...) là method nghiệp vụ
    // do ứng dụng cần hiện thực theo yêu cầu.
}
```

Đây là **mã kiến trúc minh họa, không phải class chạy độc lập** vì còn hai method nghiệp vụ. Service **không shutdown** executor được inject vì quyền sở hữu thuộc caller/container. Lifecycle và xử lý lỗi được cấu hình ở tầng có thẩm quyền.

## 28. Các lỗi phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách đúng hơn |
| --- | --- | --- |
| Cho rằng `thenApply` luôn chạy trên thread main | Callback có thể chạy trên completion thread | Không dựa vào thread-affinity |
| Cho rằng `thenApplyAsync` chắc chắn tạo thread mới | Executor có thể tái sử dụng worker/chạy inline | Hiểu contract của Executor |
| Cho rằng custom executor ở `supplyAsync` tự kế thừa | Stage `thenApplyAsync` không truyền executor có thể dùng common pool | Truyền explicit executor tại chỗ cần |
| Đưa blocking I/O nặng lên common pool | Tranh worker với các tác vụ khác | I/O executor riêng/nonblocking API/virtual threads phù hợp |
| Gọi `join()` bên trong callback của cùng single-thread pool | Thread starvation deadlock | `thenCompose` và không chặn worker |
| Dùng `thenApply` khi lambda trả future | `CompletableFuture<CompletableFuture<T>>` | `thenCompose`/`thenComposeAsync` |
| Dùng `thenCombineAsync` cho dữ liệu phụ thuộc | Tạo việc song song không cần thiết | `thenCompose` nếu task 2 phụ thuộc task 1 |
| Dùng `thenRunAsync` khi cần result upstream | Runnable không nhận giá trị | `thenAcceptAsync`/`thenApplyAsync` |
| Cho rằng `whenCompleteAsync` biến lỗi thành fallback | Stage quan sát lỗi vẫn exceptional | `handleAsync`/`exceptionally` |
| Không kiểm tra error path | Callback success có thể bị bỏ qua | Test exceptional completion |
| `allOf` rồi nghĩ có danh sách giá trị đã gom | `allOf` có kiểu `Void` | Truy xuất future con sau completion |
| `anyOf` rồi nghĩ chỉ chọn normal completion | Có thể hoàn thành exceptional từ nguồn đầu tiên | Chọn đúng combinator |
| Không shutdown executor tự tạo | Thread/resource leak | Lifecycle `shutdown/awaitTermination` |
| Shutdown executor được inject dùng chung | Làm hỏng thành phần khác | Owner đóng executor |
| Shutdown trước khi dependent async được gửi | RejectedExecutionException / pipeline lỗi | Đợi pipeline hoàn tất hoặc có lifecycle orchestration |
| Dùng newFixedThreadPool(n) nhưng tin queue bounded | Queue của factory có thể không giới hạn | Cấu hình bounded queue/backpressure |
| Không xét rejection policy | Mất task hoặc dội latency lên caller | Xử lý backpressure/rejection rõ |
| Dùng sleep làm đồng bộ test async | Flaky, chậm | Completion, latch, join tại boundary |
| Không capture/restore tracing context | Mất request ID hoặc rò context | Context propagation |
| `orTimeout` rồi nghĩ I/O dừng | Future timeout không bảo đảm cancel underlying task | Timeout/cancellation ở thư viện nguồn |
| Dùng virtual threads cho CPU-bound để “tăng tốc CPU” | Không thêm CPU capacity | Đo tải và giới hạn tác vụ đúng |

Các vấn đề trên không được giải quyết chỉ bằng đổi tên `thenApply` thành `thenApplyAsync`. Cần hiểu **kiến trúc stage**, **đường đi của task**, **sự sở hữu executor** và **giới hạn tài nguyên**.

## 29. Quy trình quyết định Executor cho một stage

Trước một callback `fn`, hỏi:

1. **Nó có cần kết quả stage trước không?** Nếu có, chọn `thenApply` hoặc `thenCompose` tùy có trả future hay không.
2. **fn có quá nhẹ để đáng gửi sang pool khác?** Nếu nhẹ, không blocking và không có yêu cầu thread-affinity, non-Async thường là điểm bắt đầu hợp lý.
3. **fn có blocking I/O không?** Nếu có, tìm API async thật hoặc executor I/O có giới hạn; không mặc định dùng common pool.
4. **fn có CPU-bound nặng không?** Cân nhắc CPU executor với giới hạn song song phù hợp máy/quota.
5. **fn có phải chạy ở một thread/dispatcher đặc biệt không?** Truyền đúng Executor do framework cung cấp.
6. **Có nguy cơ callback chờ future cũng xếp trên chính pool đó?** Tránh `join`/`get` trong worker nếu có thể; dùng compose.
7. **Điều gì xảy ra khi executor full/shutdown?** Xác định rejection, backpressure và error propagation.
8. **Ai đóng ExecutorService?** Chỉ owner thực hiện shutdown; caller khác chỉ sử dụng.
9. **Context/logging/security có cần được truyền không?** Không giả định ThreadLocal tự đi theo.
10. **Tác vụ lỗi hoặc timeout thì sao?** Dùng `handle`/`whenComplete` đúng vai trò và timeout ở lớp I/O underlying.
11. **Có cần Java 8 runtime không?** Chỉ dùng API có ở Java 8, tránh `delayedExecutor`/`orTimeout` (Java 9+) hoặc virtual threads (Java 21+) nếu runtime chưa hỗ trợ.
12. **Đã đo tải thật chưa?** Theo dõi thread count, queue length, rejected tasks, latency, p95/p99 và CPU.

Nếu sau những câu hỏi này **không có yêu cầu tách thread rõ**, non-Async transformation đơn giản thường là lựa chọn đủ tốt. Nếu có yêu cầu tài nguyên, **explicit Executor** làm phụ thuộc dễ kiểm soát và kiểm thử hơn.

## 30. Bài tập tự kiểm tra

**Câu 1.** `thenApply` khác `thenApplyAsync` thế nào?  
**Đáp án:** Cùng biến đổi kết quả thành stage mới, nhưng non-Async không chỉ định executor mới và có thể chạy trong thread completion/caller; Async dùng default async execution facility.

**Câu 2.** `thenApplyAsync(fn, executor)` bảo đảm chạy trên thread mới không?  
**Đáp án:** Không. Nó gửi task vào executor được cung cấp; executor có thể tái sử dụng thread hoặc chạy trực tiếp tùy contract.

**Câu 3.** `supplyAsync(supplier, ioPool).thenApplyAsync(fn)` có nhất thiết dùng ioPool cho `fn`?  
**Đáp án:** Không. Với CompletableFuture chuẩn, method Async không truyền executor dùng default async executor, thường là common pool.

**Câu 4.** Khi `fn` là phép chuẩn hóa chuỗi cực nhỏ, không blocking, nên thử phương thức nào?  
**Đáp án:** `thenApply(fn)` thường đủ; tránh scheduling thừa trừ khi phải điều phối thread.

**Câu 5.** Khi `fn` gọi JDBC blocking lâu, nên mặc định dùng common pool?  
**Đáp án:** Không. Cân nhắc I/O executor có giới hạn, API nonblocking thực hoặc virtual threads JDK21+; xét pool connection và backpressure.

**Câu 6.** `thenApply(x -> loadAsync(x))` tạo kiểu gì?  
**Đáp án:** Future lồng future. `thenCompose(x -> loadAsync(x))` làm phẳng thành future kết quả.

**Câu 7.** `thenComposeAsync(fn, cpuPool)` có bắt inner future của `fn` chạy CPU pool không?  
**Đáp án:** Không. Chỉ callback tạo stage dùng cpuPool; inner future chạy theo executor/cơ chế riêng của nó.

**Câu 8.** Vì sao `join` bên trong single-thread executor khi task con cũng ở đó có thể deadlock?  
**Đáp án:** Worker duy nhất bị chiếm để đợi; task con đang chờ worker rảnh trong cùng queue.

**Câu 9.** `thenCombineAsync` dùng khi nào?  
**Đáp án:** Khi cần cả hai kết quả bình thường của hai stage; callback kết hợp có thể được chạy trên executor chỉ định.

**Câu 10.** `whenCompleteAsync` có tự phục hồi lỗi thành thành công không?  
**Đáp án:** Không. Nó dùng để quan sát success/error; `handleAsync` có thể map thành fallback.

**Câu 11.** `CompletableFuture.allOf` trả danh sách giá trị từ nguồn chứ?  
**Đáp án:** Không; trả `CompletableFuture<Void>` hoàn thành khi các future nguồn hoàn tất.

**Câu 12.** `cancel(true)` trên CompletableFuture có luôn interrupt task đang chạy không?  
**Đáp án:** Không. CompletableFuture cancellation là exceptional completion; tham số mayInterruptIfRunning không điều khiển underlying computation theo contract.

**Câu 13.** Tại sao không tạo `Executors.newFixedThreadPool` mới cho mỗi request?  
**Đáp án:** Tốn chi phí tạo/đóng thread, khó quản lý lifecycle và tài nguyên. Nên dùng pool được quản lý/tái sử dụng.

**Câu 14.** `newFixedThreadPool(n)` có giới hạn số task pending không?  
**Đáp án:** Factory dùng queue không giới hạn dung lượng theo contract; nếu cần bounded queue hãy chọn cấu hình rõ.

**Câu 15.** `CompletableFuture.delayedExecutor` có trong Java 8 không?  
**Đáp án:** Không, đây là API Java 9+. Nó vẫn hiện hành và có overload truyền base executor.

**Câu 16.** `Executors.newVirtualThreadPerTaskExecutor()` có trong Java 17 không?  
**Đáp án:** Không, có từ Java 21; hữu ích cho nhiều blocking I/O phù hợp nhưng không tự giới hạn concurrency.

**Câu 17.** Vì sao test không nên assert tên common-pool thread?  
**Đáp án:** Tên và số thread phụ thuộc môi trường, runtime, cấu hình pool; test nên assert giá trị và dùng executor test riêng nếu cần.

**Câu 18.** Nếu `supplyAsync` thất bại, `thenApplyAsync` kế tiếp có gọi lambda không?  
**Đáp án:** Không, lambda biến đổi bình thường không được gọi; stage dependent hoàn thành exceptionally trừ khi đã có bước recovery.

**Câu 19.** Có nên shutdown executor do framework inject vào service trong `whenComplete`?  
**Đáp án:** Không nếu service không sở hữu executor; lifecycle thuộc framework hoặc composition root.

**Câu 20.** Cần tách số thread ở CPU executor và I/O executor theo công thức cố định nào?  
**Đáp án:** Không có một công thức đúng mọi workload. Bắt đầu từ CPU quota, độ chờ I/O, giới hạn downstream và đo tải/queue/rejection thực tế.

## 31. Ghi nhớ

- **Non-Async** (`thenApply`, `thenCompose`, `thenCombine`...) không bảo đảm dùng thread riêng; callback có thể chạy trên thread hoàn thành stage trước hoặc caller.
- **Async không truyền Executor** dùng default async execution facility, thường là `ForkJoinPool.commonPool()` trên CompletableFuture chuẩn; **custom Executor ở root không tự kế thừa**.
- **Async có Executor** (`thenApplyAsync(fn, executor)`, `thenComposeAsync(fn, executor)`...) cho phép chọn rõ nơi gửi callback. **Không đồng nghĩa luôn tạo thread mới**.
- **`supplyAsync`** tạo future có giá trị; **`runAsync`** tạo future kiểu Void. `thenApply` ánh xạ, `thenCompose` làm phẳng nested future, `thenCombine` ghép hai kết quả.
- **`handleAsync` phục hồi bằng mapping success/error; `whenCompleteAsync` quan sát nhưng không tự nuốt lỗi**. Success-only dependent callback bị bỏ qua khi upstream thất bại.
- Chọn executor dựa trên **CPU-bound, blocking I/O, isolation, queue, rejection và lifecycle**; tránh blocking `join()` trên cùng pool đang cần chạy tác vụ con.
- **Không tắt common pool, không tự tắt pool được inject, không tạo pool mới mỗi request.** Quản lý shutdown/backpressure/timeout và context propagation.
- **Java 9+/21+ có thêm delayedExecutor, timeout helpers và virtual threads**, nhưng phân biệt version rõ để code Java 8 không sử dụng nhầm.
- Kiểm thử bằng completion điều khiển được và executor riêng; đừng phụ thuộc vào sleep hoặc tên common-pool thread.

### Tài liệu chính thức đang áp dụng

- [Oracle Java SE 26 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): chính sách non-Async, default executor, supply/run/thenApply/thenCompose, cancellation và timeout.
- [Oracle Java SE 27 — `CompletionStage`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html): các biến thể Async, kết hợp và exceptional completion.
- [Oracle Java SE 26 — `Executor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executor.html) và [`ExecutorService`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): hợp đồng thực thi và quản lý vòng đời.
- [Oracle Java SE 26 — `Executors`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html): single/fixed thread pool, virtual thread executor (JDK21+).
- [Oracle Java SE 27 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue, sizing, rejection policy.
- [Oracle Java SE 26 — `ForkJoinPool`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool và mô hình work-stealing.
- [Oracle Java SE 26 — `CompletionException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html), [`RejectedExecutionException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RejectedExecutionException.html), [`TimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeoutException.html).
