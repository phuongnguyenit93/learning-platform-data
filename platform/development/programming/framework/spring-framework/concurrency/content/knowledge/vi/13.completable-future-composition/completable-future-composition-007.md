# Các bước không có hậu tố Async có thể chạy trên luồng hoàn tất

Trong Java 17+ và Spring Framework, `CompletableFuture` cho phép ghép nhiều bước xử lý bằng `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `handle`, `thenCombine`... Một hiểu lầm rất phổ biến là: “Đã dùng `CompletableFuture` nên mọi callback đều chạy trên một thread nền”, hoặc “callback nối sau một `@Async` sẽ luôn dùng đúng executor đã khai báo tại `@Async`”.

**Không đúng.** Theo chính sách thực thi của `CompletableFuture`, hành động của các phương thức **không có hậu tố `Async`** có thể được thực hiện bởi **thread làm cho future trước đó hoàn tất**, hoặc một thread khác tham gia thao tác hoàn tất. Nếu stage đã hoàn tất khi ta đăng ký callback, callback có thể chạy **ngay trên thread đang đăng ký**. Vì vậy, callback không có hậu tố `Async` **không có bảo đảm chuyển luồng**.

Đây là kiến thức nền tảng trong nhóm **Kết hợp CompletableFuture** của module **Spring Framework – concurrency**: cần biết callback có thể chạy ở đâu trước khi đặt vào đó truy vấn chặn luồng, tính toán nặng, logic transaction, logging context hoặc code phụ thuộc thread.

## 1. Hình dung một chuỗi CompletableFuture

```text
Thread "request"
     |
     | đăng ký callback
     v
CompletableFuture<String> source
     |
     +-- thenApply(transform) ------------> stage B
     |             ^
     |             | có thể chạy trên thread hoàn tất source
     |
     +-- thenApplyAsync(transform, pool) --> stage C
                   |
                   | xếp lịch callback qua executor đã chỉ định
                   v
              pool worker
```

Hai điểm cần phân biệt:

1. **Stage có thể chưa hoàn thành** dù phương thức đăng ký callback như `thenApply(...)` đã trả về một `CompletableFuture` mới.
2. **Luồng chạy callback** không nhất thiết là luồng gọi phương thức đăng ký; với phương thức không `Async`, luồng đó phụ thuộc vào thời điểm và cơ chế hoàn tất.

“Không có `Async`” **không đồng nghĩa** “luôn chạy trên main thread”, “luôn chạy đồng bộ từ đầu đến cuối” hoặc “luôn chạy trên thread mà producer được khởi tạo”. Nó có nghĩa **không yêu cầu executor riêng để chuyển callback** theo chính sách non-async.

### Những thành phần cần hiểu

| Thành phần | Vai trò |
| --- | --- |
| `CompletableFuture<T>` | Biểu diễn kết quả có thể hoàn thành trong tương lai; có thể hoàn tất bình thường, ngoại lệ hoặc bị hủy |
| `CompletionStage<T>` | API ghép các bước phụ thuộc vào kết quả tương lai |
| Upstream stage | Stage đầu vào mà một callback chờ |
| Dependent stage | Stage mới do `thenApply`/`thenCompose`/... trả về |
| Completion thread | Thread thực hiện hành động hoàn tất upstream, ví dụ gọi `complete(...)` hoặc kết thúc async computation |
| Registration thread | Thread gọi `thenApply(...)` để gắn một callback |
| Executor | Đối tượng nhận task để lên lịch thực thi, ví dụ `ThreadPoolTaskExecutor` hoặc `ExecutorService` |

Một stage mới cũng có thể là upstream cho các stage phía sau; mỗi điểm nối có quy tắc thực thi riêng.

## 2. Chính sách chính thức: non-Async không có thread affinity

Javadoc `CompletableFuture` trong Java SE 17 nêu chính sách cho các hành động của dependent completion **non-async**: chúng *may be performed by the thread that completes the current CompletableFuture, or by any other caller of a completion method*. Đây là chính sách **có thể**, không phải lời hứa cố định thread nào sẽ chạy.

Có ba tình huống nên nhớ:

### Tình huống A — Callback được đăng ký khi upstream chưa hoàn tất

```java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> next =
        source.thenApply(String::toUpperCase);

source.complete("hello");
```

Ở cách triển khai phổ biến của JDK 17, nếu callback đã đăng ký trước `complete` và không có thao tác hoàn tất cạnh tranh, thread gọi `source.complete("hello")` có thể thực thi ngay `String::toUpperCase` trước khi hoàn tất việc xử lý các dependent completions.

**Không nên dựa vào tên thread để coi đây là hợp đồng.** Nếu nhiều thread tham gia hoàn tất hoặc có race giữa đăng ký và hoàn tất, luồng thực tế có thể khác. Điểm được bảo đảm về mặt ý nghĩa là **stage phụ thuộc phải tính đúng kết quả**, không phải thread identity.

### Tình huống B — Upstream đã hoàn tất trước khi callback được đăng ký

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("hello");

CompletableFuture<String> next =
        ready.thenApply(String::toUpperCase);
```

Với implementation JDK 17 thông thường, callback `thenApply` có thể được chạy **ngay lúc gọi `thenApply` trên registration thread**, bởi kết quả đầu vào đã sẵn có.

**Hậu quả:** nếu đoạn xử lý trong `thenApply` tốn 500 ms, lệnh đăng ký callback trong request thread có thể tốn gần 500 ms. Đừng cho rằng “đã là callback Future thì thao tác đăng ký luôn gần như tức thì”.

### Tình huống C — Future hoàn tất trên worker của executor

```java
ExecutorService worker = Executors.newSingleThreadExecutor();

CompletableFuture<String> source =
        CompletableFuture.supplyAsync(() -> "hello", worker);

CompletableFuture<String> next =
        source.thenApply(String::toUpperCase);
```

Đây là **fragment**, cần khai báo imports và đóng `worker`. Khi task của `supplyAsync` hoàn tất sau lúc callback đã được đăng ký, callback non-async **có thể chạy trên worker vừa hoàn tất upstream**. Nếu upstream hoàn tất quá nhanh trước khi `thenApply` được gọi, callback có thể chạy ngay trên registration thread. Chỉ đọc hai dòng code không đủ để kết luận tên thread.

**Tóm lại:** phương thức non-async **có thể chạy trên luồng hoàn tất**, nhưng **không được hứa luôn chạy trên luồng đó**.

## 3. So sánh phương thức có và không có hậu tố Async

| Non-Async | Async tương ứng | Điểm khác về scheduling |
| --- | --- | --- |
| `thenApply(fn)` | `thenApplyAsync(fn)` | Async yêu cầu thực thi fn qua default asynchronous execution facility |
| `thenApply(fn)` | `thenApplyAsync(fn, executor)` | Cho phép chọn executor rõ ràng cho fn |
| `thenAccept(action)` | `thenAcceptAsync(action, executor)` | Action nhận kết quả, trả `CompletableFuture<Void>` |
| `thenRun(action)` | `thenRunAsync(action, executor)` | Action không nhận kết quả đầu vào |
| `thenCompose(fn)` | `thenComposeAsync(fn, executor)` | Async chuyển bước gọi hàm tạo stage con qua executor |
| `thenCombine(other, fn)` | `thenCombineAsync(other, fn, executor)` | Hàm kết hợp được scheduling qua executor |
| `whenComplete(action)` | `whenCompleteAsync(action, executor)` | Callback quan sát kết quả/lỗi cũng có thể được scheduling |
| `handle(fn)` | `handleAsync(fn, executor)` | Hàm chuyển đổi cả success/error qua executor |

Một số operation như `exceptionally(...)` có phiên bản async trong các Java release hiện đại (`exceptionallyAsync(...)` của Java 12+); cần xem API của phiên bản JDK đang dùng. Các phương thức **không có hậu tố Async** trong bảng không được hứa thread identity.

### 3.1. Default Async dùng ở đâu?

Với `CompletableFuture`, overload `thenApplyAsync(fn)` không truyền `Executor` sử dụng **default asynchronous execution facility**, thường là `ForkJoinPool.commonPool()` trong Java 17. Javadoc còn lưu ý trường hợp common pool không hỗ trợ mức parallelism ít nhất 2 thì implementation có thể dùng thread mới cho từng task. Đây là **chính sách của `CompletableFuture`**, không tự lấy `ThreadPoolTaskExecutor` của Spring.

Vì vậy:

```java
var step = source.thenApplyAsync(this::heavyCalculation);
```

Không đồng nghĩa step dùng bean `applicationTaskExecutor` hoặc bean `reportExecutor` do Spring tạo. Nếu muốn đảm bảo điểm chuyển execution được đưa vào pool đã chọn, truyền explicit executor:

```java
var step = source.thenApplyAsync(this::heavyCalculation, cpuExecutor);
```

Hai đoạn trên là **fragment**: `source`, `heavyCalculation` và `cpuExecutor` phải tồn tại trong class ứng dụng.

### 3.2. Async không nhất thiết “tạo thread mới”

Hậu tố `Async` nghĩa là callback được **lên lịch theo chính sách executor**, không phải “khởi động `new Thread` cho mỗi callback” hay “chắc chắn khác thread”.

Một `Executor` tùy chỉnh kiểu:

```java
Executor direct = Runnable::run;
future.thenApplyAsync(value -> transform(value), direct);
```

có thể thực hiện action **ngay trên thread gọi `execute`**, vì direct executor chạy `Runnable.run()` tại chỗ. `CallerRunsPolicy` của một pool quá tải cũng có thể khiến caller trực tiếp làm việc. Do đó, nếu hệ thống cần **cô lập tài nguyên hoặc tránh block request thread**, phải kiểm soát cả behavior của executor, overload/rejection policy và task duration; không chỉ thêm hậu tố `Async`.

## 4. Java 17 runnable: ba trường hợp thread khác nhau, kết quả xác định

Chương trình sau minh họa ba trường hợp:

1. `thenApply` đăng ký **trước khi** source hoàn tất; worker của producer gọi `complete`.
2. `thenApply` gắn vào `completedFuture` ngay trên registration thread.
3. `thenApplyAsync` dùng **executor được chỉ định rõ** để thực thi callback.

Dùng `CountDownLatch` thay vì `Thread.sleep(...)` để tạo thứ tự sự kiện chắc chắn. Chủ động đặt tên thread để stdout không phụ thuộc tên do hệ điều hành/JVM tự cấp.

Lưu nội dung vào **ContinuationThreadDemo.java**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContinuationThreadDemo {
    private static ExecutorService oneWorker(String name) {
        return Executors.newSingleThreadExecutor(
                task -> new Thread(task, name));
    }

    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("registration-thread");

        ExecutorService producer = oneWorker("completion-worker");
        ExecutorService cpu = oneWorker("cpu-worker");
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            Future<?> producerJob = producer.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    source.complete("payload");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    source.completeExceptionally(e);
                }
            });

            started.await();

            // Source chưa hoàn tất: callback đã được đăng ký.
            CompletableFuture<String> deferred =
                    source.thenApply(value ->
                            Thread.currentThread().getName() + ":" + value);

            release.countDown();
            String a = deferred.join();
            producerJob.get();

            // Source đã hoàn tất trước khi đăng ký callback.
            CompletableFuture<String> ready =
                    CompletableFuture.completedFuture("ready");
            String b = ready.thenApply(value ->
                    Thread.currentThread().getName() + ":" + value).join();

            // Chỉ định rõ nơi thực thi action bất đồng bộ.
            String c = ready.thenApplyAsync(value ->
                    Thread.currentThread().getName() + ":" + value,
                    cpu).join();

            System.out.println("pending thenApply -> " + a);
            System.out.println("completed thenApply -> " + b);
            System.out.println("explicit thenApplyAsync -> " + c);
        } finally {
            release.countDown();
            producer.shutdownNow();
            cpu.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ContinuationThreadDemo.java
java ContinuationThreadDemo
```

**Stdout của chương trình trên khi chạy với Java 17 trong tình huống mô tả:**

```text
pending thenApply -> completion-worker:payload
completed thenApply -> registration-thread:ready
explicit thenApplyAsync -> cpu-worker:ready
```

**Vì sao không phải chỉ tình cờ?**

- `started.await()` đảm bảo producer task đã bắt đầu và đang chờ `release`, nên registration thread có thời gian gắn `thenApply` trước khi producer gọi `complete`.
- Chỉ có producer thread gọi `source.complete(...)` sau khi latch mở, không có thread khác cạnh tranh hoàn tất source. Với cơ chế non-async của JDK 17, dependent action được thực thi trên completion worker trong tình huống này.
- `ready` được tạo qua `completedFuture` ngay trên registration thread; callback ngắn của `thenApply` đã có input ngay lúc đăng ký.
- `thenApplyAsync(..., cpu)` gửi callback vào executor `cpu` chỉ có một thread đặt tên `cpu-worker`.
- Kết quả được lưu thành ba biến rồi **in từ main theo thứ tự cố định**, thay vì print trực tiếp từ ba callback có thể thay nhau ghi stdout.
- `finally` đóng hai executor. `shutdownNow` ở đây chỉ để dọn tài nguyên của demo; ứng dụng cần chính sách graceful shutdown phù hợp.

**Phạm vi kết luận:** demo xác định luồng thực thi trong **điều kiện có latch, thread factory và implementation JDK 17 đang dùng**; không biến những kết quả này thành quy tắc mọi `CompletableFuture` non-async ở mọi hệ thống luôn chạy trên cùng tên thread.

## 5. Chuyển tiếp non-Async: có thể “ăn” thời gian của completion thread

Giả sử một tác vụ I/O hoàn tất trên worker `io-1`, rồi đăng ký:

```java
CompletableFuture<Invoice> parsed =
        fetchInvoiceAsync(id)
                .thenApply(this::parseInvoice)
                .thenApply(this::validate)
                .thenApply(this::calculateLargeReport);
```

Đây là **fragment**, không có implementation `Invoice`/các method. Vấn đề không nằm ở việc gọi `thenApply` nhiều lần mà ở **nội dung callback** và **thread thực thi**.

Nếu `fetchInvoiceAsync` chưa hoàn tất khi các dependent actions được đăng ký, cùng một thread vừa hoàn tất I/O có thể tiếp tục chạy các callback đó. Khi `calculateLargeReport` tốn CPU hàng trăm mili giây, completion thread phải làm thêm CPU thay vì giải phóng công việc khác.

Hệ quả có thể gồm:

- Worker của một `ThreadPoolTaskExecutor` bị chiếm ngoài dự kiến; queue task khác phải chờ.
- Nếu upstream hoàn tất trên thread xử lý HTTP/Netty event loop, callback blocking có thể làm chậm cả event loop.
- Nếu upstream đã hoàn tất trước khi đăng ký và callback non-async được chạy ngay trong caller, request thread có thể bị block ngay tại câu lệnh `thenApply`.
- Khi có nhiều dependent stages, không dự đoán thứ tự chúng được chạy dựa vào thứ tự viết code; tránh side effect yêu cầu ordering ngoài quan hệ phụ thuộc rõ ràng.
- Nếu callback ném exception, dependent future có thể hoàn tất ngoại lệ; lỗi đó không nhất thiết xuất hiện trực tiếp ở thời điểm caller gọi `thenApply` trong mọi tình huống.

### 5.1. Tách CPU work sang executor phù hợp

```java
CompletableFuture<Invoice> result =
        fetchInvoiceAsync(id)
                .thenApply(this::parseSmallPayload)
                .thenApplyAsync(this::calculateLargeReport, cpuExecutor);
```

**Ý nghĩa:** `parseSmallPayload` là bước nhỏ có thể để inline nếu đã đánh giá an toàn; `calculateLargeReport` được giao cho `cpuExecutor` chuyên trách. Trong thực tế, nếu parsing cũng CPU-heavy hoặc có thể block, hãy chuyển cả bước đó vào executor thích hợp.

Đừng dùng mặc định `ForkJoinPool.commonPool()` cho mọi loại công việc trong web service khi cần kiểm soát quota, log, saturation và lifecycle theo bean Spring.

### 5.2. Async ở một bước không “lây” sang mọi bước sau

```java
var b = source.thenApplyAsync(this::cpuStep, cpuExecutor);
var c = b.thenApply(this::nextStep);
```

`cpuStep` được scheduling qua `cpuExecutor`, nhưng `nextStep` **là non-async**. Nếu `b` chưa hoàn tất khi `nextStep` được đăng ký, `nextStep` có thể chạy ngay trên thread hoàn tất `b` — thường là worker đang làm `cpuStep`. Nếu `b` đã hoàn tất rồi mới đăng ký `nextStep`, action có thể chạy ngay trên thread gọi dòng hai.

Không có “executor gắn vĩnh viễn vào chain” chỉ vì một bước từng dùng `thenApplyAsync(..., cpuExecutor)`. **Mỗi điểm nối cần quyết định rõ** có cần dispatch hay không.

## 6. Những phương thức non-Async cần chú ý ngoài thenApply

### 6.1. `thenAccept` và `thenRun`

```java
stage.thenAccept(result -> saveToDatabase(result));
stage.thenRun(() -> refreshCache());
```

`thenAccept` nhận kết quả upstream; `thenRun` không nhận kết quả. Cả hai là non-async trong hai lệnh trên. Nếu các action ghi DB/cache có I/O blocking, chúng có thể **chặn completion thread hoặc caller**.

Nếu workload nặng hoặc phải isolate, dùng `thenAcceptAsync(..., ioExecutor)` hay `thenRunAsync(..., executor)` với executor phù hợp. Đồng thời, không coi thực thi action này là transaction của upstream nếu có thread khác và boundary riêng.

### 6.2. `whenComplete` không chỉ là “observer nhẹ” theo mặc định

```java
CompletableFuture<Order> observed = stage.whenComplete(
        (value, error) -> audit(value, error));
```

Đây là fragment. `whenComplete` tạo một dependent stage và chạy action khi upstream hoàn tất. Nếu `audit` ghi log ngắn, chi phí có thể nhỏ; nhưng nếu `audit` gọi REST hoặc thực hiện nhiều truy vấn, callback có thể chiếm completion thread.

**Semantics lỗi:** `whenComplete` chủ yếu dùng quan sát kết quả/lỗi, không biến một failure thành success như `handle`. Nếu action ném lỗi, dependent stage có thể nhận failure theo quy tắc `whenComplete`; không nên sử dụng `whenComplete` để mặc định “nuốt mọi exception”.

### 6.3. `handle` và `exceptionally` cũng non-Async

```java
CompletableFuture<String> recovered =
        stage.handle((value, error) ->
                error == null ? value : "fallback");
```

`handle` chạy khi stage hoàn tất bình thường hoặc ngoại lệ và **chuyển đổi** result. `exceptionally` chỉ xử lý nhánh ngoại lệ. Cả hai có thể chạy trên completion thread khi gọi các bản non-async.

Một fallback gọi service ngoài có thể chặn worker, nên đừng mặc định code xử lý lỗi là nhẹ. Khi JDK hỗ trợ, `handleAsync(..., executor)` hoặc `exceptionallyAsync(..., executor)` giúp định tuyến các bước fallback đắt đỏ.

### 6.4. `thenCompose` khác `thenApply`

Giả sử hàm `fetchProfileAsync` đã trả về một `CompletionStage<Profile>`. Khi ghép:

```java
CompletableFuture<Receipt> chain =
        lookupUserAsync(id)
                .thenCompose(user -> fetchReceiptAsync(user));
```

`thenCompose` (non-async) **có thể chạy hàm `user -> fetchReceiptAsync(user)` trên completion thread của upstream**. Nhưng nó **không đồng nghĩa toàn bộ việc fetch receipt chạy trên cùng thread**: stage do `fetchReceiptAsync` trả về có thể thực hiện I/O hoặc hoàn tất ở một nơi khác. `thenCompose` chỉ làm phẳng `CompletionStage<CompletionStage<T>>` thành stage kết quả.

Nếu bước **khởi tạo** request con cũng cần chuyển thread, dùng `thenComposeAsync(user -> fetchReceiptAsync(user), executor)`. Hãy tránh `join()` bên trong `thenCompose`; ghép stage bằng cách return chính stage con thường tốt hơn:

```java
// Không nên nếu có khả năng block:
.thenApply(user -> fetchReceiptAsync(user).join())

// Nên dùng composition, không chặn callback để đợi stage con:
.thenCompose(user -> fetchReceiptAsync(user))
```

Hai dòng trên là **fragment chain**, không phải chương trình độc lập.

### 6.5. `thenCombine`, `runAfterBoth`, `allOf`

- `thenCombine(a, b, fn)` chạy `fn` khi cả hai stage đầu vào có kết quả thành công; với bản non-async, callback có thể thực hiện trên thread hoàn tất một trong hai stage hoặc thread tham gia hoàn tất.
- `runAfterBoth` có callback không nhận result; có bản Async tương ứng nếu cần chuyển nơi thực thi.
- `CompletableFuture.allOf(a, b)` trả về future phụ thuộc vào các future đầu vào. Nếu nối `allOf(...).thenRun(this::aggregate)`, bước `aggregate` vẫn là **non-async**, không tự có thread riêng.
- `anyOf` cũng tạo một completion stage theo điều kiện bất kỳ kết quả hoàn tất; nối callback phía sau phải xét tương tự.

**Quy tắc:** việc có **nhiều upstream future** không cung cấp bảo đảm về thread chạy callback cuối. Quan hệ phụ thuộc quyết định **khi nào được phép xử lý**, không cố định **thread nào xử lý**.

## 7. Bối cảnh Spring: @Async executor không tự truyền vào continuation

Trong Spring Framework, `@EnableAsync` và `@Async("ioExecutor")` có thể giao method vào một bean `ThreadPoolTaskExecutor` tên `ioExecutor`. Tuy nhiên, code gọi method có thể nối tiếp `CompletableFuture`:

```java
CompletableFuture<String> loaded = dataService.loadAsync(id);

CompletableFuture<Result> result =
        loaded.thenApply(this::heavyTransform);
```

Câu hỏi **“`heavyTransform` chạy trên `ioExecutor` hay HTTP request thread?”** không thể trả lời bằng một tên cố định:

- Nếu `loaded` chưa hoàn tất khi `thenApply` đăng ký, callback non-async có thể chạy trên thread làm future hoàn tất (thường có liên quan worker của `ioExecutor`).
- Nếu `loaded` hoàn tất trước khi `thenApply` đăng ký, callback có thể chạy inline trên request thread.
- Nếu code khác tham gia hoàn tất dependent stage, có thể phát sinh đường thực thi khác theo completion policy.
- `@Async` xác định interceptor của **method được annotate**; nó **không gắn một executor mặc định vào mọi dependent callback** sau khi method trả Future.

**Không mặc định `thenApplyAsync` không truyền executor sẽ chọn `ioExecutor`.** Nó sử dụng default asynchronous execution facility của `CompletableFuture`, thường là common pool của JDK, không tự kế thừa bean Spring.

### 7.1. Ví dụ Spring Boot 3.x đầy đủ

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.x/Spring Framework 6.x** với dependency `spring-boot-starter-web`. Khai báo hai executor rõ ràng:

- `ioExecutor` nhận việc `@Async` mô phỏng đọc dữ liệu blocking.
- `cpuExecutor` nhận continuation xử lý CPU qua `thenApplyAsync(..., cpuExecutor)`.

Lưu thành **src/main/java/com/example/demo/ContinuationApplication.java**:

```java
package com.example.demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class ContinuationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContinuationApplication.class, args);
    }

    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(50);
        pool.setThreadNamePrefix("io-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Bean("cpuExecutor")
    ThreadPoolTaskExecutor cpuExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(30);
        pool.setThreadNamePrefix("cpu-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }
}

@Service
class DataService {
    @Async("ioExecutor")
    public CompletableFuture<String> loadAsync(String id) {
        try {
            Thread.sleep(150); // Mô phỏng đọc dữ liệu blocking
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return CompletableFuture.completedFuture("item:" + id);
    }
}

@Service
class WorkflowService {
    private final DataService dataService;
    private final Executor cpuExecutor;

    WorkflowService(
            DataService dataService,
            @Qualifier("cpuExecutor") Executor cpuExecutor) {
        this.dataService = dataService;
        this.cpuExecutor = cpuExecutor;
    }

    public CompletableFuture<String> process(String id) {
        return dataService.loadAsync(id)
                .thenApplyAsync(
                        value -> value.toUpperCase(Locale.ROOT),
                        cpuExecutor);
    }
}

@RestController
class WorkflowController {
    private final WorkflowService workflow;

    WorkflowController(WorkflowService workflow) {
        this.workflow = workflow;
    }

    @GetMapping("/process/{id}")
    public CompletableFuture<String> process(@PathVariable String id) {
        return workflow.process(id);
    }
}
```

Chạy bằng build Spring Boot có dependencies tương ứng:

```bash
./gradlew bootRun
curl -s http://localhost:8080/process/Z1
```

Trên Windows, dùng `gradlew.bat bootRun`. Khi request được tiếp nhận và hai bước thực thi thành công, response body là:

```text
ITEM:Z1
```

**Giải thích luồng:**

1. Spring tạo các `ThreadPoolTaskExecutor` dưới dạng bean và quản lý initialization/shutdown.
2. Controller gọi `WorkflowService.process`; service gọi bean `DataService` khác nên lời gọi `loadAsync` đi qua Spring `@Async` proxy ở chế độ mặc định.
3. Method `loadAsync` chạy trong worker của `ioExecutor`. `Thread.sleep` chỉ mô phỏng I/O blocking, **không phải non-blocking I/O**.
4. `thenApplyAsync(..., cpuExecutor)` đưa bước chuyển đổi vào executor `cpuExecutor`; không dựa vào việc thread nào hoàn tất `loadAsync`. `toUpperCase` ở đây nhẹ để minh họa, thực tế chỉ cần tách pool khi task đủ lớn hoặc có yêu cầu isolation.
5. Controller trả `CompletableFuture<String>` để Spring MVC xử lý kết quả khi hoàn tất. **HTTP client vẫn chờ response body**; đây không phải API trả job ID 202 ngay.
6. Nếu pool bị bão hòa hoặc một bước ném exception, request sẽ không có response thành công như ví dụ; cần mapping lỗi/overload theo hợp đồng của ứng dụng.

**Điểm quan trọng:** dùng `@Async("ioExecutor")` cho method gốc không buộc callback `thenApply(...)` phía sau dùng `ioExecutor`. Nếu muốn tránh tính toán nặng trên I/O worker hoặc request thread, quyết định tại **chính callback** bằng `thenApplyAsync(..., cpuExecutor)`.

### 7.2. Vì sao không tự tạo một executor mới mỗi request?

`Executors.newFixedThreadPool(...)` được tạo trong controller/service mỗi request sẽ gây bùng số threads, khó quan sát và không tự được Spring quản lý shutdown. Hãy tạo executor **bean dùng chung** có giới hạn rõ ràng và inject theo qualifier.

Nếu custom `TaskExecutor` quá tải, nó có thể từ chối scheduling. Tách pool giúp **cô lập tài nguyên**, nhưng không bảo đảm các tác vụ luôn được nhận; vẫn cần đo queue, active threads và xử lý lỗi từ chối.

## 8. ThreadLocal, MDC, Spring transaction và security context

Một callback non-async có thể chạy ở nhiều thread khác nhau theo timing. Điều này làm những logic dựa vào **thread-local state** trở nên nguy hiểm.

### 8.1. MDC logging

Nếu callback lấy `MDC.get("traceId")` và giả định luôn có ID của HTTP request, kết quả có thể thay đổi:

- Callback chạy inline trên request thread: có thể thấy request MDC.
- Callback chạy trên một pooled worker: MDC **không tự động được truyền** từ request thread.
- Nếu worker không cleanup MDC đúng cách, callback có thể thấy **trace ID cũ** của task khác trên cùng worker.

Khi cần correlation ID, truyền bằng dữ liệu tường minh trong payload hoặc thiết kế context propagation phù hợp. Với Spring `ThreadPoolTaskExecutor`, có thể dùng `TaskDecorator` để copy/restore context ở điểm submit nếu cần, nhưng **không được nghĩ decorator chỉ gắn lên upstream executor sẽ bao trùm mọi callback non-async về sau**. Callback inline trên một thread bất kỳ không chắc đi qua task decorator của executor đã cấu hình.

### 8.2. Transaction context

Spring transaction thông thường gắn với thread. Một callback non-async có thể chạy trên thread hoàn tất hoặc thread đăng ký; **không được dựa vào timing** để đoán transaction của caller có còn hiện diện hay không.

Ví dụ:

```java
@Transactional
public void createOrder() {
    CompletableFuture<String> f = remoteCallAsync();
    f.thenApply(result -> updateOrder(result));
}
```

Đây là fragment có nguy cơ: `thenApply` có thể thực thi ở thread khác ngoài transaction của `createOrder`, hoặc inline trong caller tùy completion timing. Nếu `updateOrder` cần transaction, hãy đưa nó vào một **Spring-managed service method** với boundary transaction rõ ràng và gọi qua proxy; không đặt giả định transaction tự “chảy” sang mọi callback.

Ngay cả khi callback tình cờ chạy inline và thấy transaction, đó không phải thiết kế bền vững. Trong các pipeline async, xác định ranh giới transaction cho từng thao tác dữ liệu, bảo đảm idempotency và consistency khi cần.

### 8.3. Security/request context

`SecurityContextHolder` mặc định thường gắn state với thread. `RequestContextHolder` cũng có các giả định về thread/request lifecycle. Không đưa các object request sống ngắn hoặc mutable request context vào queue/continuation rồi dùng lâu sau khi HTTP request kết thúc.

Nếu cần danh tính để xử lý công việc nền, truyền **dữ liệu danh tính đã kiểm chứng và tối thiểu cần thiết**, hoặc dùng các wrapper/executor hỗ trợ context propagation có kiểm soát. Không tự sao chép toàn bộ context nhạy cảm giữa thread nếu không hiểu boundary.

## 9. Callback blocking có thể tạo starvation và deadlock

Hai anti-pattern đáng tránh:

### 9.1. Chặn completion thread để chờ một task khác cùng pool

```java
CompletableFuture<String> result =
        upstream.thenApply(value -> {
            // Nếu downstream cần worker đang bị callback này chiếm,
            // việc chờ có thể gây starvation.
            return nextAsync(value).join();
        });
```

Đây là fragment minh họa. Nếu pool chỉ có một worker và `nextAsync` cũng phải được lên lịch vào cùng pool, callback chiếm worker rồi `join` chờ task chưa thể bắt đầu: **starvation deadlock**.

Thay bằng composition:

```java
CompletableFuture<String> result =
        upstream.thenCompose(value -> nextAsync(value));
```

`thenCompose` không cần chặn thread chỉ để đợi stage con. Tuy vậy, **hàm khởi tạo stage con vẫn là non-async** và có thể chạy trên completion thread; nếu việc khởi tạo bản thân nặng, cân nhắc `thenComposeAsync(..., executor)`.

### 9.2. Blocking trong event loop

Với WebFlux/Netty và thư viện reactive/non-blocking, completion thread đôi khi là event-loop thread. Một callback `thenApply` gọi JDBC, `Thread.sleep` hoặc xử lý CPU nặng có thể chặn event loop và làm ảnh hưởng nhiều kết nối. Hãy dùng cơ chế scheduling/offloading phù hợp với framework và thư viện đang sử dụng; không suy luận “Future là async nên blocking ở đâu cũng được”.

### 9.3. Callback đồng bộ chạy ngay trên caller

Ngay cả trong servlet MVC truyền thống, `completedFuture(...).thenApply(this::slowStep)` có thể gọi `slowStep` inline lúc đăng ký, giữ request thread. Vì vậy hai request giống nhau nhưng upstream completion timing khác nhau có thể có **latency khác nhau ở điểm nối**.

Không nên dùng phương thức non-async cho work nặng chỉ vì thử nghiệm một lần cho thấy callback chạy trên background worker.

## 10. Exception cũng là completion; xử lý lỗi có thể chạy inline

Một future có thể hoàn tất ngoại lệ:

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(new IllegalStateException("service down"));

CompletableFuture<String> recovered =
        source.exceptionally(error -> "fallback");
```

Nếu `source` đã hoàn tất ngoại lệ trước lúc đăng ký, `exceptionally` có thể chạy ngay tại registration thread. Với upstream chưa hoàn tất, fallback non-async có thể chạy trên thread thực hiện exceptional completion.

Một callback lỗi gọi thêm DB/HTTP để dự phòng cũng có nguy cơ block giống callback thành công.

### Những quy tắc quan trọng

- `thenApply` thường chỉ chạy action khi upstream hoàn tất bình thường; nếu upstream exceptional, dependent stage truyền tiếp trạng thái lỗi theo quy tắc CompletionStage.
- `handle` nhận cả result và throwable; phù hợp khi muốn chuyển đổi cả success và failure.
- `whenComplete` thích hợp cho logging/observability nhưng có thể tạo một dependent stage bị lỗi nếu callback cũng lỗi; không phải công cụ “nuốt mọi exception”.
- `exceptionally` có thể khôi phục một upstream failure thành kết quả bình thường nếu trả fallback; **phải xác định** fallback nào chấp nhận được theo nghiệp vụ.
- `join()` ném `CompletionException` cho failure; `get()` có thể ném `ExecutionException`/`InterruptedException`. Quan sát đúng đường lỗi.
- Khi dùng custom executor, task scheduling có thể bị **rejected** nếu pool quá tải hoặc đang shutdown; không hứa `thenApplyAsync` luôn thành công chỉ vì nó có hậu tố Async.

Trong Spring, quản lý riêng đường lỗi của `@Async void` và `CompletableFuture<T>`: handler uncaught async được dùng cho void, còn caller Future cần quan sát exceptional completion bằng `whenComplete`/`handle` hoặc framework error mapping phù hợp.

## 11. Đo lường, kiểm thử và quyết định thiết kế

### 11.1. Kiểm thử thread thực thi bằng điều kiện xác định

Một bài test đáng tin không dựa vào `Thread.sleep(100)` và đoán worker đã hoàn tất. Dùng:

1. `CompletableFuture<String>` chưa hoàn tất.
2. `CountDownLatch` giữ completion worker trước khi gọi `complete`.
3. Đăng ký `thenApply` trước khi mở latch.
4. Trong callback lưu thread name, không đưa nghiệp vụ vào việc so sánh cứng tên thread.
5. Mở latch, dùng `join`/`get` để chờ kết quả.
6. So sánh với một `completedFuture` đã hoàn tất trước khi đăng ký.
7. Đăng ký `thenApplyAsync(fn, executor)` trên executor có tên và kiểm tra bước cần isolate đi qua đó.

Demo `ContinuationThreadDemo.java` bên trên thực hiện đúng ba trường hợp đầu với output có thể kiểm chứng.

### 11.2. Chọn non-Async hay Async như thế nào?

| Tình huống | Gợi ý |
| --- | --- |
| Mapping giá trị rất nhỏ, pure function, không blocking | `thenApply` có thể phù hợp |
| Ghi log/metric rất nhẹ, không phụ thuộc ThreadLocal | `whenComplete` có thể phù hợp |
| Biến đổi CPU nặng | `thenApplyAsync(fn, cpuExecutor)` |
| Gọi blocking I/O trong callback | `thenCompose` với API async thực sự, hoặc `thenApplyAsync`/`thenComposeAsync` trên executor I/O thích hợp |
| Đăng ký callback trong HTTP request, không được block request thread | Tránh callback non-async nặng; tách qua executor |
| Kết hợp hai Future rồi xử lý nặng | `thenCombineAsync(..., executor)` |
| Cần gọi API con trả `CompletionStage<T>` | `thenCompose` để flatten, thêm Async nếu bước tạo stage cần dispatch |
| Nghiệp vụ cần transaction riêng | Gọi Spring bean method với transaction boundary rõ, không dựa vào thread của callback |
| Cần context MDC/security | Propagate context có chủ đích; không tin future tự kế thừa thread-local |
| Dự án cần quota và độ trễ đo lường được | Executor bean có giới hạn, metric, overload policy và lifecycle |
| Một stage trước đã dùng `thenApplyAsync` | Vẫn đánh giá độc lập stage sau, vì executor không được tự động “kế thừa” |

Chọn theo **chi phí thực thi và ranh giới tài nguyên**, không theo quy tắc “luôn Async là tốt” hoặc “luôn non-Async là nhanh”. Dispatch quá nhiều callback rất nhỏ có thể làm tăng scheduling overhead; để callback lớn chạy inline có thể làm nghẽn completion worker.

### 11.3. Theo dõi để phát hiện callback chạy sai nơi

Đối với hệ thống Spring có nhiều executor, quan sát:

- Tên thread khi callback bắt đầu, nhưng **không dùng thread name làm logic nghiệp vụ**.
- Thời gian chạy từng continuation và độ trễ end-to-end.
- `ThreadPoolTaskExecutor#getActiveCount()`, `getPoolSize()`, queue depth.
- Tỷ lệ rejected scheduling, exceptional completion, timeout và cancellation.
- Thread dump khi hệ thống nghẽn, xem completion workers bị chiếm bởi callback hay đang chờ `join`.
- Latency HTTP request và event loop khi upstream đã hoàn tất nhanh, vì callback có thể chạy inline trong caller.

Một callback mất 800 ms không phải “nhẹ” chỉ vì nằm trong `thenApply`. Nhận diện cụ thể callback nào chiếm thread nào giúp quyết định chỗ cần offload.

## 12. Lỗi phổ biến

**Lỗi 1 — Tin rằng mọi `thenApply` đều chạy trên thread tạo future.** Future có thể được hoàn tất ở thread khác, hoặc đã hoàn tất trước khi callback đăng ký.

**Lỗi 2 — Tin rằng non-Async chắc chắn chạy trên completion thread.** Đây là khả năng phổ biến, **không phải bảo đảm duy nhất**; callback có thể chạy ngay trên registration thread.

**Lỗi 3 — Tin rằng `thenApplyAsync` luôn dùng executor của `@Async` Spring.** Nếu không truyền executor, `CompletableFuture` sử dụng default async facility của nó, thường là common pool.

**Lỗi 4 — Tách CPU work bằng `thenApplyAsync` nhưng quên explicit executor.** Có thể đẩy computation vào shared common pool không được giám sát như pool Spring.

**Lỗi 5 — Dùng `thenApply` để gọi blocking API hoặc tính toán dài.** Completion worker/request thread/event loop có thể bị giữ ngoài dự kiến.

**Lỗi 6 — Nối `thenApply` sau một `thenApplyAsync` rồi nghĩ executor vẫn được “kế thừa”.** Non-async continuation vẫn có chính sách không cố định thread.

**Lỗi 7 — `thenCompose` tự được hiểu là “mọi thứ bất đồng bộ”.** Callback tạo stage con vẫn có thể chạy inline; chỉ việc chờ stage con được flatten, không block qua `join`.

**Lỗi 8 — `join()` trong callback chạy trên single-thread executor.** Nếu task được đợi cần cùng worker đó, có thể starvation deadlock.

**Lỗi 9 — Dựa vào `ThreadLocal`/transaction của request trong callback.** Completion thread không ổn định theo timing và thread-local không tự chuyển theo CompletableFuture.

**Lỗi 10 — Cho rằng `@Async` tự hoạt động khi method tự gọi trong cùng bean.** Self-invocation ở chế độ proxy mặc định bỏ qua interceptor.

**Lỗi 11 — Không quan sát exceptional completion.** Future có thể đã kết thúc bằng lỗi, nhưng callback `thenApply` không chạy và endpoint vẫn không biết thất bại nếu bỏ qua Future.

**Lỗi 12 — Tạo executor mới cho mỗi callback.** Dẫn đến rò rỉ thread và thiếu capacity control; ưu tiên shared, managed executor.

**Lỗi 13 — Chuyển mọi callback nhỏ thành Async vô điều kiện.** Tăng scheduling overhead mà không cải thiện throughput. Cần đo và chọn các ranh giới thật sự có giá trị.

**Lỗi 14 — Kiểm thử bằng sleep rồi khẳng định luồng chạy luôn cố định.** Timing biến đổi giữa JVM, máy và tải; dùng latch/executor tên rõ ràng cho thí nghiệm, nhưng ứng dụng production vẫn không ràng business logic vào thread identity.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.completedFuture("x").thenApply(fn)` có luôn chạy trên worker thread không?

**Đáp án:** Không. Future đã hoàn tất trước khi đăng ký, nên với implementation thường gặp, `fn` có thể chạy ngay trong thread gọi `thenApply`.

**Câu 2.** Method `@Async("ioExecutor")` trả `CompletableFuture<String>`. Nối `thenApply(this::heavyCpu)` thì heavyCpu chắc chắn chạy trên `ioExecutor`?

**Đáp án:** Không. Non-async callback có thể chạy trên completion thread hoặc registration/completion-related thread tùy thời điểm. Nếu muốn định tuyến CPU work, dùng `thenApplyAsync(this::heavyCpu, cpuExecutor)`.

**Câu 3.** `thenApplyAsync(fn)` không truyền executor sẽ tự dùng `ThreadPoolTaskExecutor` mặc định của Spring?

**Đáp án:** Không. Theo chính sách của `CompletableFuture` trong JDK, thường dùng `ForkJoinPool.commonPool()`, không tự động lấy Spring bean.

**Câu 4.** `thenApplyAsync(fn, directExecutor)` có bảo đảm khác thread không?

**Đáp án:** Không. Một direct executor như `Runnable::run` có thể thực thi action ngay trên caller của `execute`. “Async” là cơ chế scheduling qua executor, không phải bảo đảm tạo mới hay đổi thread.

**Câu 5.** `thenCompose(user -> fetchAsync(user))` có tự block đợi `fetchAsync` không?

**Đáp án:** Không. Nó gộp stage con vào stage kết quả. Tuy nhiên callback khởi tạo `fetchAsync` là non-async và có thể chạy trên completion thread.

**Câu 6.** Vì sao không nên `thenApply(x -> fetchAsync(x).join())` trên một pool nhỏ?

**Đáp án:** Callback có thể chiếm worker và block đợi task con cũng cần worker đó, gây starvation hoặc deadlock. Thường nên dùng `thenCompose(x -> fetchAsync(x))`.

**Câu 7.** Nếu callback `whenComplete` chỉ ghi log thì có an toàn không?

**Đáp án:** Có thể phù hợp nếu thực sự nhẹ, không blocking và không phụ thuộc context không được truyền. Nếu log/telemetry làm I/O chậm hoặc cần context đặc biệt, phải đánh giá lại nơi thực thi.

**Câu 8.** Một callback non-async tình cờ thấy transaction/request MDC của caller trong một test. Có nên dựa vào điều đó?

**Đáp án:** Không. Nếu future hoàn tất ở thời điểm khác, callback có thể chạy trên thread khác và thiếu context. Thiết kế transaction, security và correlation rõ ràng theo ranh giới.

**Câu 9.** Một bước `thenApplyAsync(..., cpuExecutor)` đã hoàn tất. `thenApply(...)` gắn sau đó sẽ chạy ở đâu?

**Đáp án:** Có thể chạy inline trên thread đăng ký vì upstream đã hoàn tất; nếu đăng ký trước khi upstream kết thúc, có thể chạy trên thread hoàn tất stage. Không có quy tắc “luôn CPU executor”.

## Tóm tắt

- **Non-Async continuation không có thread affinity được bảo đảm.** Nó có thể chạy trên completion thread hoặc thread khác tham gia completion; nếu upstream đã sẵn kết quả, có thể chạy ngay tại lúc đăng ký.
- **Hậu tố Async đặt ra yêu cầu lên lịch**, nhưng không đảm bảo “thread mới”; khi cần ranh giới tài nguyên rõ ràng, hãy truyền **executor cụ thể**.
- **Spring `@Async` chỉ điều phối phương thức được proxy intercept**, không gắn bean executor ấy vào mọi continuation của `CompletableFuture`.
- Chỉ để callback nhỏ, pure, không blocking chạy non-async khi phù hợp. **Offload xử lý CPU nặng, blocking I/O hoặc bước cần isolation** sang executor thích hợp.
- Tránh `join()` blocking trong completion callback; dùng `thenCompose` cho stage con. Không dựa vào ThreadLocal, MDC, transaction hay tên thread trùng hợp theo timing.
- Kiểm chứng bằng test có `CountDownLatch`, explicit executor và đo callback latency, thay vì kết luận từ một lần chạy ngẫu nhiên.

## Tài liệu tham khảo

1. Java SE 17 API — CompletableFuture, asynchronous completion policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
2. Java SE 17 API — CompletionStage methods: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
3. Java SE 17 API — Executor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
4. Spring Framework Reference — Task Execution and Scheduling, `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
5. Spring Framework Javadoc — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
6. Spring Framework Reference — AOP proxying and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
