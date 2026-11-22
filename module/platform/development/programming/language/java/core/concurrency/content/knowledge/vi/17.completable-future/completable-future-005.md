# thenCompose() để nối các tác vụ bất đồng bộ trong Java CompletableFuture

## 1. Mục tiêu: tác vụ sau cần kết quả của tác vụ trước

Một chuỗi bất đồng bộ có thể gồm nhiều bước **phụ thuộc dữ liệu**:

1. Tìm mã người dùng từ một yêu cầu.
2. Có mã rồi mới truy vấn hồ sơ.
3. Có hồ sơ rồi mới tìm thông tin bổ sung.
4. Khi cả chuỗi hoàn tất, tạo kết quả cuối.

Giả sử mỗi bước trả về một `CompletableFuture`. Nếu viết lồng các callbacks hoặc gọi `join()` bên trong một worker để đợi bước sau, ta dễ tạo code khó đọc và có nguy cơ chiếm worker vô ích. `thenCompose()` được thiết kế để mô tả **bước tiếp theo sinh ra một CompletionStage mới** mà không tạo một future lồng nhau ở phía caller.

~~~java
CompletableFuture<String> result =
    lookupUserIdAsync("alice")
        .thenCompose(id -> loadProfileAsync(id))
        .thenCompose(profile -> loadPermissionsAsync(profile));
~~~

Đây là **mã minh họa trong một method**: ba hàm `lookupUserIdAsync`, `loadProfileAsync` và `loadPermissionsAsync` do ứng dụng định nghĩa với kiểu kết quả tương thích. Ý nghĩa là bước sau chỉ được gọi khi bước trước **hoàn tất bình thường**, và kết quả ngoài cùng phản ánh kết quả của stage cuối.

### Kết quả học tập

Sau bài này, bạn có thể:

- Hiểu chính xác chữ ký tổng quát `thenCompose(Function<T, CompletionStage<U>>)`.
- Phân biệt `thenApply()` (**map** giá trị đồng bộ) với `thenCompose()` (**flatMap** một stage bất đồng bộ).
- Giải thích khi nào hàm mapper chạy, khi nào stage kết quả hoàn tất và tại sao không có `CompletableFuture<CompletableFuture<T>>`.
- Hiểu `thenComposeAsync()` chỉ điều phối **cách thực thi hàm compose**, không đồng nghĩa tự động chuyển mọi I/O trong inner stage sang executor đó.
- Thiết kế chuỗi `CompletionStage` không chặn bằng `join/get` bên trong callbacks.
- Xử lý exceptional completion từ stage nguồn, mapper và stage phụ thuộc; dùng `exceptionally`, `handle`, `whenComplete` và `exceptionallyCompose` đúng vai trò.
- Nhận biết cancellation/timeout của stage kết quả **không tự tạo cascade cancellation hoặc kill công việc nền**.
- Chạy các chương trình Java 17+ cho chaining, flattening, executor routing và error recovery với kết quả ổn định.
- Tránh các vòng phụ thuộc, hạn chế oversubscription của pool và kiểm soát I/O/blocking bằng deadline riêng.

**Phạm vi:** Java SE concurrency tổng quát, `java.util.concurrent`; không phụ thuộc thư viện hoặc framework bên ngoài. Các chương trình đầy đủ sử dụng JDK 17+.

## 2. API thenCompose(): chữ ký và ý nghĩa

Trong `CompletionStage<T>`:

~~~java
<U> CompletionStage<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
~~~

Trong `CompletableFuture<T>`, phương thức tương ứng trả về một `CompletableFuture<U>` theo API của class này.

Giải thích từng thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `T` | Kiểu kết quả của stage hiện tại |
| `fn` | Function nhận **giá trị T** của stage hiện tại sau khi thành công |
| `CompletionStage<U>` | Stage mới do function tạo/trả về |
| `U` | Kiểu dữ liệu cuối cùng của stage mới |
| Giá trị return | **Một** stage kiểu U, được hoàn tất tương ứng với stage mà fn trả về |

Cơ chế:

~~~text
upstream: CompletionStage<T>
       │
       │ hoàn tất bình thường với T
       ▼
  gọi fn(T)
       │
       ▼
  inner: CompletionStage<U>
       │
       │ inner hoàn tất (normal / exceptional)
       ▼
composed: CompletionStage<U>
       │
       ▼
  caller theo dõi U
~~~

**Chỉ khi upstream hoàn tất bình thường**, function `fn` mới được áp dụng. Nếu upstream hoàn tất exceptionally, mapper không được gọi; dependent stage cũng hoàn tất exceptionally theo CompletionStage rules. Nếu `fn` trả một stage chưa hoàn tất, dependent stage **vẫn pending**, cho tới khi inner stage có kết quả hoặc lỗi.

Một câu cần nhớ: **`thenCompose()` nối hai giai đoạn phụ thuộc; nó không đợi đồng bộ bằng việc giữ một thread ở `join()`.**

### Tính tương đồng với flatMap

Với một giá trị đồng bộ:

~~~java
Optional<String> nickname =
        Optional.of("alice").flatMap(name -> Optional.of(name.toUpperCase()));
~~~

`Optional.flatMap` trả một Optional không lồng Optional. Tương tự, `thenCompose` trả một CompletionStage không lồng CompletionStage. Đây là liên hệ khái niệm, không có nghĩa Optional và CompletableFuture có cùng cơ chế concurrency.

## 3. thenApply khác thenCompose ở điểm nào?

### thenApply: Function trả một **giá trị thường**

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("123")
                .thenApply(Integer::parseInt);
~~~

Ở đây `Integer.parseInt` trả `int/Integer`, nên result là `CompletableFuture<Integer>`.

Nếu `thenApply` nhận function trả **một CompletableFuture**:

~~~java
CompletableFuture<CompletableFuture<Integer>> nested =
        CompletableFuture.completedFuture("12")
                .thenApply(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

Kết quả bị lồng **hai lớp**. `nested.join()` trả `CompletableFuture<Integer>`, và muốn lấy số thực tế caller phải `nested.join().join()` — thêm một lớp quản lý không cần thiết.

### thenCompose: Function trả **CompletionStage**

~~~java
CompletableFuture<Integer> flat =
        CompletableFuture.completedFuture("12")
                .thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

`flat` là một `CompletableFuture<Integer>`. Không có future lồng bên trong return type.

| Hỏi | `thenApply` | `thenCompose` |
|---|---|---|
| Mapper trả gì? | Giá trị `U` | `CompletionStage<U>` |
| Type kết quả | `CompletableFuture<U>` | `CompletableFuture<U>` |
| Nếu mapper trả một CF<U> | `CF<CF<U>>` | `CF<U>` |
| Tình huống chính | Biến đổi đồng bộ từ T sang U | Bước kế tiếp **tự bất đồng bộ**, phụ thuộc T |
| Có đợi bằng cách block worker? | Không tự đợi | Không tự đợi |
| Bắt đầu làm gì khi upstream lỗi? | Không gọi mapper | Không gọi mapper |

**Không “đổi mọi thenApply thành thenCompose”.** Nếu function trả giá trị ngay như `String::toUpperCase`, dùng `thenApply` là đúng. Nếu function trả `CompletionStage<U>`, `thenCompose` là đúng.

## 4. Ví dụ runnable 1: so sánh nested và flattened

Lưu **ThenComposeVsApplyDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ThenComposeVsApplyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("21");

        CompletableFuture<CompletableFuture<Integer>> nested =
                source.thenApply(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text) * 2));

        CompletableFuture<Integer> flat =
                source.thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text) * 2));

        System.out.println("nested=" + nested.join().join());
        System.out.println("flat=" + flat.join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThenComposeVsApplyDemo.java
java ThenComposeVsApplyDemo
~~~

Stdout:

~~~text
nested=42
flat=42
~~~

Hai phép tính cùng cho số 42; **khác nhau nằm ở kiểu kết quả và mô hình chaining**. `nested.join().join()` phải unwrap hai lớp. `flat.join()` chỉ unwrap một lớp.

### Lưu ý về toán tử và method reference

`thenCompose` không nhận một `Supplier<CompletionStage<U>>` không tham số khi upstream có kết quả T; nó nhận `Function<T, CompletionStage<U>>`. Nếu bước sau không cần giá trị T, vẫn dùng lambda nhận tham số nhưng bỏ qua có chủ đích:

~~~java
CompletableFuture<String> next =
    CompletableFuture.completedFuture("ignored")
        .thenCompose(unused ->
                CompletableFuture.completedFuture("ready"));
~~~

Nếu chỉ muốn **chạy một tác vụ sau một stage** mà không cần result, `thenRun` hoặc `thenRunAsync` có thể phù hợp hơn. Nếu muốn run một Runnable rồi trả CompletableFuture<Void>, thiết kế kiểu trả về tương ứng.

## 5. Ví dụ runnable 2: chain hai tác vụ bất đồng bộ phụ thuộc

Đây là một chương trình Java 17+ hoàn chỉnh dùng **executor do ứng dụng sở hữu**. Bước 1 tạo user id; bước 2 chỉ được gọi khi có id; bước 3 biến đổi chuỗi trả về.

Lưu **ThenComposePipelineDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenComposePipelineDemo {
    static CompletableFuture<String> findId(
            String name, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> "id-" + name, executor);
    }

    static CompletableFuture<String> findRole(
            String id, ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> id + ":reader", executor);
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<String> answer =
                    findId("alice", executor)
                            .thenCompose(id -> findRole(id, executor))
                            .thenApply(role -> "result=" + role);

            System.out.println(answer.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac ThenComposePipelineDemo.java
java ThenComposePipelineDemo
~~~

Stdout:

~~~text
result=id-alice:reader
~~~

**Diễn giải:**

1. `findId` trả `CompletableFuture<String>`. `supplyAsync` submit supplier vào executor.
2. Khi `findId` thành công với `"id-alice"`, hàm được truyền vào `thenCompose` mới có input hợp lệ để gọi `findRole`.
3. `findRole` trả **một CompletableFuture khác**; stage kết quả của thenCompose lấy completion của stage này.
4. `thenApply` biến đổi role thành chuỗi hoàn chỉnh, vì bước này trả giá trị đồng bộ.
5. `answer.join()` xuất hiện **chỉ ở ranh giới main** để chương trình console chờ đầu ra rồi in; không có lời gọi `join` bên trong worker-stage callback.
6. Executor được shutdown trong finally để tránh giữ platform threads sau khi hoàn tất.

Chương trình không dựa vào thread name, lịch scheduling hay thời gian sleep; vì thế stdout xác định. Dù bước 1 và 2 chạy trên cùng hoặc khác worker, **bước 2 cần id nên không thể sử dụng kết quả trước khi bước 1 hoàn tất**.

### Nhận xét về hai tác vụ

Vì bước 2 cần id từ bước 1 nên các bước **không có parallel speedup nội tại giữa chính chúng**. thenCompose mô tả **asynchronous dependency**, không phải cách chạy hai tasks phụ thuộc đồng thời. Để chạy hai tác vụ **độc lập**, xem `thenCombine` hoặc `allOf`, sau đó ghép kết quả.

## 6. thenCompose không gọi function trước khi upstream thành công

Dùng một `CompletableFuture` được điều khiển thủ công để quan sát chính xác khi nào mapper chạy và khi nào composed stage hoàn tất, không dùng `Thread.sleep()`.

Lưu **ThenComposeOrderingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenComposeOrderingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        AtomicInteger mapperCalls = new AtomicInteger();

        CompletableFuture<String> result =
                first.thenCompose(id -> {
                    mapperCalls.incrementAndGet();
                    return second.thenApply(value -> id + ":" + value);
                });

        System.out.println("before=" + mapperCalls.get());
        first.complete("user-7");
        System.out.println("afterFirst=" + mapperCalls.get());
        System.out.println("doneAfterFirst=" + result.isDone());

        second.complete("ready");
        System.out.println("afterSecond=" + result.join());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ThenComposeOrderingDemo.java
java ThenComposeOrderingDemo
~~~

Stdout:

~~~text
before=0
afterFirst=1
doneAfterFirst=false
afterSecond=user-7:ready
~~~

**Vì sao không có race trong output?**

- `first` và `second` là CompletableFuture chưa hoàn tất. Trước `first.complete`, mapper chưa có giá trị input để chạy.
- `thenCompose` (bản non-Async) gắn dependent action; khi main gọi `first.complete("user-7")`, callback có thể được main chạy trong quá trình completion.
- `first.complete` trả về sau khi dependent action đã được kích hoạt cho chuỗi này trong mô hình ví dụ; mapperCalls là 1 khi in `afterFirst`.
- Mapper trả `second.thenApply(...)` nhưng `second` vẫn pending, nên composed result chưa done.
- `second.complete("ready")` làm stage phụ thuộc tính chuỗi; `result.join()` trả `"user-7:ready"`.

**Hệ quả:** `thenCompose` không phải `join` dưới vỏ bọc. Nó chỉ nối đồ thị phụ thuộc và trả về một stage mới; completion có thể xảy ra ở tương lai.

## 7. Bản đồng bộ và bất đồng bộ của compose

Ba overload quan trọng của `CompletableFuture`:

~~~java
<U> CompletableFuture<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);

<U> CompletableFuture<U> thenComposeAsync(
        Function<? super T, ? extends CompletionStage<U>> fn);

<U> CompletableFuture<U> thenComposeAsync(
        Function<? super T, ? extends CompletionStage<U>> fn,
        Executor executor);
~~~

Khác biệt:

- `thenCompose(fn)`: dependent function có thể chạy ở thread **hoàn tất stage trước** hoặc thread liên quan tới completion; **không bảo đảm** sẽ tạo một worker mới hay chạy trên executor khác.
- `thenComposeAsync(fn)`: function được dispatch theo **default asynchronous execution facility** của stage; với CompletableFuture mặc định thường là `ForkJoinPool.commonPool()`, có fallback theo API khi parallelism không đáp ứng yêu cầu.
- `thenComposeAsync(fn, executor)`: function được dispatch bằng **Executor chỉ định**; dễ kiểm soát thread naming, quota, ownership và giám sát hơn.
- Cả ba vẫn **compose kết quả của stage do fn trả về**; chúng không tự biến một blocking external operation thành non-blocking operation.

### Một ngộ nhận quan trọng

~~~java
source.thenComposeAsync(value -> slowBlockingCall(value), executor);
~~~

Nếu `slowBlockingCall` **trả CompletionStage** sau một ít logic synchronous, phần mapper được gọi bằng executor. Nhưng nếu `slowBlockingCall` **block 30 giây trước khi trả stage**, thread executor vẫn bị block 30 giây. Nếu method trả thẳng `String` thay vì CompletionStage, code không phù hợp chữ ký thenCompose.

Muốn I/O bất đồng bộ thật, lựa chọn phụ thuộc API: một non-blocking client trả stage, hoặc dùng executor thích hợp cho blocking work qua `supplyAsync`, có timeout và giới hạn concurrency.

## 8. Ví dụ runnable 4: thenComposeAsync dùng executor chỉ định

Lưu **ThenComposeExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenComposeExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "compose-worker"));

        try {
            CompletableFuture<String> output =
                    CompletableFuture.completedFuture("payload")
                            .thenComposeAsync(value ->
                                    CompletableFuture.completedFuture(
                                            Thread.currentThread().getName()
                                                    + ":" + value),
                                    executor);

            System.out.println(output.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ThenComposeExecutorDemo.java
java ThenComposeExecutorDemo
~~~

Stdout:

~~~text
compose-worker:payload
~~~

**Lý do:** executor chỉ có một thread được đặt tên `compose-worker` và overload `thenComposeAsync(fn, executor)` chạy mapper trên executor đó. Mapper dùng `Thread.currentThread().getName()` **bên trong callback**, không dựa vào tên thread chạy `main` hoặc stage nguồn. Inner stage đã hoàn tất ngay bằng `completedFuture`; không có task I/O khác cần dispatch.

Đừng suy từ ví dụ này rằng mọi bước sau trong chuỗi mặc định đều chạy trên compose-worker. Một `supplyAsync` ở mapper dùng **executor riêng** sẽ thực thi supplier theo executor đó; một `thenApply` non-Async tiếp theo có chính sách completion-thread riêng.

## 9. Chọn executor: trách nhiệm của từng stage

Ví dụ mô hình:

~~~java
CompletableFuture<String> pipeline =
    CompletableFuture.supplyAsync(() -> readInput(), ioExecutor)
        .thenCompose(input -> queryAsync(input))
        .thenApply(result -> normalize(result))
        .thenComposeAsync(normalized -> writeAsync(normalized), writeExecutor);
~~~

Đây là đoạn **minh họa tích hợp**, các function và executors do ứng dụng định nghĩa. Trước khi chọn overload, hỏi:

1. `readInput()` có blocking không? Nếu có, ioExecutor có giới hạn số workers hợp lý không?
2. `queryAsync()` đã trả một stage bất đồng bộ tự quản lý I/O chưa? Có cần dispatch mapper riêng không?
3. `normalize()` là phép biến đổi CPU ngắn hay công việc nặng? Nếu nặng, có nên dùng `thenApplyAsync(..., cpuExecutor)`?
4. `writeAsync()` có side effect/idempotency, timeout và cancellation policy thế nào?
5. Ai sở hữu `ioExecutor`, `writeExecutor`, khi nào shutdown?
6. Các callbacks có giữ lock hoặc chờ Future từ chính executor một thread không?

**Không phải mọi stage đều cần Async.** Dùng Async ở mọi nơi có thể tạo overhead chuyển queue/context không cần thiết. Ngược lại, callback CPU-bound dài trong non-Async stage có thể chiếm thread đang hoàn tất upstream và gây độ trễ cho completion khác.

### Common pool không phải lựa chọn mặc định phù hợp mọi I/O

Nếu dựa vào `supplyAsync` không truyền executor cho nhiều blocking calls, tải có thể cạnh tranh với công việc khác trên `ForkJoinPool.commonPool()`. Cần cân nhắc executor riêng, giới hạn số request đồng thời, backpressure và timeout tương ứng. Với Java 21+, virtual threads có thể hữu ích cho blocking I/O nhưng **không tự** giới hạn downstream connections/rate; tránh xem chúng là lý do để bỏ admission limits.

## 10. Lỗi stage nguồn: mapper không được gọi

Nếu source future thất bại, lambda của `thenCompose` không chạy:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));

CompletableFuture<String> composed =
        failed.thenCompose(value ->
                CompletableFuture.completedFuture("never"));
~~~

`composed` hoàn tất exceptionally theo quy tắc CompletionStage. Điều quan trọng là **không gửi bước phụ thuộc** như thể nguồn đã thành công. Đây là semantics fail-fast thường mong muốn cho bước sau bắt buộc cần dữ liệu từ bước trước.

Ba nguồn lỗi thường gặp:

| Điểm thất bại | Hệ quả |
|---|---|
| Upstream completed exceptionally | Không gọi function compose, dependent exceptional |
| Mapper tự ném exception trước khi trả CompletionStage | Dependent exceptional |
| Inner CompletionStage hoàn tất exceptionally | Composed stage exceptional theo inner stage |
| Mapper trả null thay vì CompletionStage | Không có stage hợp lệ để compose, dependent exceptional (thường NullPointerException) |

**Đừng nuốt exception bằng cách trả null** khi method phải trả CompletionStage. Nếu nghiệp vụ cần “không có dữ liệu”, hãy trả một stage hoàn tất bình thường với giá trị domain phù hợp như `Optional.empty()` hoặc `completedFuture(null)` nếu null có ý nghĩa rõ ràng; khác với **trả null chính CompletionStage**.

## 11. Recovery: exceptionally, handle, whenComplete và exceptionallyCompose

Các API này có vai trò khác nhau.

### exceptionally: phục hồi bằng giá trị T

~~~java
CompletableFuture<String> result = pipeline
        .exceptionally(error -> "fallback-value");
~~~

Chỉ chạy khi stage trước lỗi; trả một giá trị thường để khôi phục normal completion của dependent stage. Không dùng `exceptionally` để **trả một CompletableFuture<String>** khi kiểu cần là String.

### exceptionallyCompose: phục hồi bằng stage bất đồng bộ

Java 12+ có `exceptionallyCompose`:

~~~java
CompletableFuture<String> result =
        primaryAsync()
                .exceptionallyCompose(error ->
                        fallbackAsync(error));
~~~

Đoạn này cần ứng dụng cung cấp `primaryAsync` và `fallbackAsync` cùng kiểu phù hợp. Đây là **nhánh bất đồng bộ chỉ dùng khi primary fail**, có ý nghĩa gần tương ứng `thenCompose` nhưng áp dụng lên đường exceptional completion. Nó không tự động cancel primary I/O nếu primary đã có side effects.

### handle: quan sát cả success và failure, chuyển thành giá trị

~~~java
CompletableFuture<String> summarized = pipeline.handle(
        (value, error) -> error == null
                ? "ok:" + value
                : "failed");
~~~

`handle` chạy trên cả hai nhánh, có thể ánh xạ outcome sang một result mới. Vì vậy nó hữu ích để chuyển success/failure thành một return type thống nhất.

### whenComplete: quan sát side effect như metrics/log

~~~java
CompletableFuture<String> logged = pipeline.whenComplete(
        (value, error) -> recordOutcome(value, error));
~~~

Đây là đoạn method tích hợp có `recordOutcome` do ứng dụng định nghĩa. `whenComplete` **không** dùng để thay thế kết quả như `handle`; nó giữ giá trị/exception upstream trừ khi callback ném exception theo quy tắc Javadoc. Dùng cho logging/metrics/cleanup nhẹ, tránh làm callback block lâu.

### Chọn vị trí recovery

~~~text
A.thenCompose(B).exceptionally(fallback)
  → bắt failure của cả A và B

A.exceptionally(fallbackA).thenCompose(B)
  → recover A trước, rồi B được gọi với giá trị dự phòng

A.thenCompose(B).exceptionallyCompose(fallbackAsync)
  → lỗi của A hoặc B kích hoạt fallback bất đồng bộ

A.thenCompose(B).handle(outcome)
  → chuyển cả success/failure sang một kiểu kết quả mới
~~~

Vị trí operator **có ý nghĩa ngữ nghĩa**, không chỉ là phong cách code.

## 12. Ví dụ runnable 5: exceptional completion và fallback

Lưu **ThenComposeErrorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenComposeErrorDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("primary unavailable"));

        CompletableFuture<String> pipeline = source.thenCompose(value -> {
            calls.incrementAndGet();
            return CompletableFuture.completedFuture("unused");
        });

        String recovered = pipeline
                .exceptionally(error -> "fallback")
                .join();

        CompletableFuture<String> secondaryFailure =
                CompletableFuture.completedFuture("user")
                        .thenCompose(id ->
                                CompletableFuture.<String>failedFuture(
                                        new IllegalArgumentException("bad id")));

        String outcome = secondaryFailure
                .handle((value, error) ->
                        error == null ? "ok" : "failed")
                .join();

        System.out.println("mapperCalls=" + calls.get());
        System.out.println("recovered=" + recovered);
        System.out.println("innerOutcome=" + outcome);
    }
}
~~~

Lệnh:

~~~bash
javac ThenComposeErrorDemo.java
java ThenComposeErrorDemo
~~~

Stdout:

~~~text
mapperCalls=0
recovered=fallback
innerOutcome=failed
~~~

**Lý giải:**
- Source đã failed trước khi compose, nên mapper không chạy; `calls` vẫn 0.
- `exceptionally` tạo một dependent stage hoàn tất bình thường với "fallback".
- Ở phép gọi thứ hai, source "user" hoàn tất bình thường, mapper trả **một failed future**. Composed stage nhận lỗi đó; `handle` chuyển thành chuỗi "failed".
- Chương trình không cần dự đoán exception message hay thread scheduling để in đúng kết quả.

### Tìm nguyên nhân lỗi của join

`join()` thường ném `CompletionException` với cause do upstream/mapper/inner stage gây ra; với cancellation trực tiếp có thể nhận `CancellationException` theo contract. `get()` ném `ExecutionException` (checked) và có `InterruptedException`. Không dùng `join` như một cách “biến lỗi thành giá trị”; nếu muốn recovery, gắn `exceptionally`/`handle` vào stage chain.

## 13. Tại sao không join/get ngay trong thenCompose?

Sai lầm thường thấy:

~~~java
CompletableFuture<User> brokenShape =
        loadIdAsync()
                .thenCompose(id -> {
                    User user = loadUserAsync(id).join();
                    return CompletableFuture.completedFuture(user);
                });
~~~

Đây là **mã minh họa sai** với các method/kiểu `User` do ứng dụng định nghĩa. Nếu `loadUserAsync(id)` chưa hoàn tất, `join()` **block thread đang thực thi callback**. Điều này làm mất lợi ích composition và có thể gây starvation nếu inner work cần đúng worker đang bị block.

Cách đúng:

~~~java
CompletableFuture<User> good =
        loadIdAsync()
                .thenCompose(id -> loadUserAsync(id));
~~~

Nếu thực sự cần biến đổi User sau khi inner stage xong:

~~~java
CompletableFuture<String> display =
        loadIdAsync()
                .thenCompose(id -> loadUserAsync(id))
                .thenApply(user -> user.displayName());
~~~

Cả hai là đoạn minh họa tích hợp. Không có `join()` trong mapper; `join()` chỉ nên dùng tại ranh giới **thực sự cần** kết quả đồng bộ, chẳng hạn main/CLI/test hoặc API imperative có nghĩa rõ ràng.

### Thread-starvation deadlock

Tình huống:
1. Executor có **một worker**.
2. Callback chạy trong worker đó.
3. Callback submit một task khác vào **cùng executor**.
4. Callback gọi `join()` chờ task mới.
5. Task mới đang queue, không có worker rảnh.
6. Worker duy nhất vẫn bị callback giữ đến khi join return.

Có thể chờ vô hạn. Thay bằng thenCompose non-blocking để worker trả quyền thực thi cho executor. Nhưng cũng phải tránh **dependency cycle** thật sự: stage A phụ thuộc B, còn B lại phụ thuộc A. Composition không tự giải quyết một graph có vòng.

## 14. Kiểu return CompletionStage hay CompletableFuture?

Chữ ký interface chấp nhận `CompletionStage<U>`. Vì thế mapper không nhất thiết phải trả một concrete `CompletableFuture<U>`: nó có thể trả một implementation khác của CompletionStage nếu tương thích.

Ví dụ:

~~~java
CompletionStage<Integer> stage =
        CompletableFuture.completedFuture("12")
                .thenCompose(text ->
                        CompletableFuture.completedFuture(
                                Integer.parseInt(text)));
~~~

Trong Java code, `CompletionStage` mang ý nghĩa **graph of dependent computations**; `CompletableFuture` bổ sung `complete`, `cancel`, `join`, `get` và các methods cụ thể. Nếu thiết kế API chỉ muốn expose khả năng chaining, có thể trả `CompletionStage<T>` thay vì cho caller quyền chủ động complete future nội bộ.

**Chú ý:** khác biệt concrete type ảnh hưởng khả năng gọi `join` trực tiếp. `CompletionStage` interface không có `join`; muốn chờ theo CompletableFuture API thường gọi `toCompletableFuture()` (với implementation phù hợp).

### Generic inference

`thenCompose` có type parameter `U`. Một function trả `CompletionStage<String>` và một function khác trả `CompletionStage<Integer>` sẽ cần mapping/union type rõ ràng nếu muốn dùng trong cùng một nhánh. Nếu lambda có nhiều branches với return types bất đồng, compiler có thể không suy được U mong muốn.

Chọn domain return type thống nhất và hạn chế raw `CompletionStage`/raw `CompletableFuture` để giữ static type safety.

## 15. Cancellation và timeout: compose không tự phá chuỗi công việc

`CompletableFuture.cancel(true)` có hiệu lực theo **completion state**, không phải lệnh interrupt thread đang chạy như người mới thường mong đợi. Javadoc `CompletableFuture` nêu `mayInterruptIfRunning` **không có hiệu lực** ở implementation này; interrupts không được dùng để điều khiển processing theo cách đó.

Các tình huống:

- Cancel **composed stage** không có hợp đồng tự động cancel mọi upstream hoặc inner stage.
- Cancel source `CompletableFuture` có thể khiến dependent stage hoàn tất exceptionally, nhưng không nhất thiết hủy công việc I/O thực sự chạy ở nguồn.
- Một inner stage đã được tạo có thể tiếp tục chạy sau khi composed stage bị cancel.
- `orTimeout` và `completeOnTimeout` hoàn tất **chính CompletableFuture được gọi** nếu chưa done trong thời hạn (một bằng exception, một bằng giá trị); không tự dừng toàn bộ task/connection ngoài.
- `get(timeout, unit)` giới hạn **thời gian caller đợi** và **không tự cancel** future.
- `join()` không nhận timeout và có thể đợi vô hạn.

### Ví dụ về timeout của composed stage

~~~java
CompletableFuture<Result> composed =
        loadIdAsync()
                .thenCompose(id -> queryAsync(id));

composed.orTimeout(500, TimeUnit.MILLISECONDS);
~~~

Đây là đoạn tích hợp dùng `Result` và methods ứng dụng; `orTimeout` có từ Java 9. Nếu quá hạn mà composed chưa hoàn tất, nó complete exceptionally với TimeoutException. **Đừng suy rằng `queryAsync` đã dừng**: điều đó phụ thuộc timeout/cancel của I/O API và chính hệ thống backend.

Nếu nghiệp vụ yêu cầu timeout **tổng** của nhiều stage, cần giữ một deadline chung thay vì mỗi step có toàn bộ timeout mới:
- Tính deadline bằng `System.nanoTime()` và budget.
- Trước mỗi step, tính remaining time.
- Không để stage sau bắt đầu một request với deadline đã hết.
- Cấu hình timeout ở client/network operation đúng theo contract.
- Nếu cần cleanup, thiết kế owner thực hiện cancellation tại từng nguồn, đóng tài nguyên hoặc dừng pipeline.

### Cancel khi đã có side effects

Nếu bước 2 đã ghi dữ liệu bên ngoài rồi step 3 bị timeout, cancellation không hoàn tác bước 2. Các bước ghi có thể cần idempotency keys, transaction protocol hoặc compensation. Một CompletableFuture graph không phải transaction manager.

## 16. Trả null stage: anti-pattern tinh tế

Người viết đôi khi trả `null` thay vì một CompletionStage:

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("id")
                .thenCompose(id -> null); // Sai: không có CompletionStage để compose
~~~

Đây là đoạn minh họa lỗi. Khi function trả null, stage phụ thuộc hoàn tất exceptionally do thiếu stage hợp lệ; có thể thấy NullPointerException trong nguyên nhân. Nếu null là **giá trị dữ liệu hợp lệ**, cần trả một stage thực sự:

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("id")
                .thenCompose(id ->
                        CompletableFuture.completedFuture(null));
~~~

Phân biệt:
- `return null;`: **không có stage** để compose.
- `return CompletableFuture.completedFuture(null);`: có stage hoàn tất bình thường với **giá trị null**.

Nếu null có ý nghĩa không tìm thấy, cân nhắc `CompletableFuture<Optional<T>>` hoặc domain result type rõ ràng để tránh null-laden code.

## 17. thenCompose không đảm bảo retry hay fallback

Một chain:

~~~java
loadIdAsync().thenCompose(id -> loadUserAsync(id))
~~~

không tự:
- Retry khi loadUserAsync thất bại.
- Đổi sang nguồn dự phòng.
- Chờ một source khác thành công.
- Chạy nhiều sources độc lập cùng lúc.
- Giới hạn số request đồng thời.
- Hủy công việc upstream nếu downstream timeout.

Những chức năng đó phải được thiết kế riêng:

| Nhu cầu | Công cụ thích hợp |
|---|---|
| Chạy bước sau phụ thuộc kết quả bước trước | `thenCompose` |
| Biến đổi giá trị đồng bộ | `thenApply` |
| Ghép **hai công việc độc lập** có kết quả | `thenCombine` |
| Chờ nhiều futures độc lập cùng hoàn tất | `CompletableFuture.allOf` |
| Chờ một future hoàn tất sớm (kể cả failure) | `CompletableFuture.anyOf` |
| Xử lý fallback bằng một giá trị | `exceptionally` |
| Fallback bằng một stage mới | `exceptionallyCompose` |
| Quan sát outcome | `whenComplete` |
| Chọn recovery cho cả success/failure | `handle` |
| Giới hạn thời gian hoàn tất CF | `orTimeout` hoặc `completeOnTimeout` |
| Chờ timeout ở caller | `get(timeout, unit)` |

Nếu bạn muốn “first successful response” giữa nhiều futures, `anyOf` không tương đương vì future đầu tiên có thể fail và `anyOf` complete exceptionally; cần một coordinator có success policy rõ ràng hoặc API khác thích hợp.

## 18. Liên hệ với thenCombine và allOf: tuần tự theo phụ thuộc, không phải chờ mọi nhánh

Ví dụ A và B độc lập:

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 10, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 20, executor);

CompletableFuture<Integer> sum =
        a.thenCombine(b, Integer::sum);
~~~

Đây là đoạn tích hợp với `executor` được định nghĩa. Cả a và b có thể được lên lịch độc lập; `thenCombine` chờ cả hai rồi cộng. **Đừng dùng thenCompose để buộc b bắt đầu sau a nếu chúng thật sự độc lập**, vì sẽ giới hạn parallelism không cần thiết.

Khi B cần A:

~~~java
CompletableFuture<Integer> chained =
        a.thenCompose(value ->
                CompletableFuture.supplyAsync(
                        () -> expensiveStep(value), executor));
~~~

Nếu B phụ thuộc A, việc B chỉ bắt đầu sau A là **đúng nghiệp vụ**. Chọn API dựa trên dependency graph, không dựa vào số lượng stages.

## 19. Không có guarantee về thread thực thi non-Async callback

Một cuộc đua thời điểm completion:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> result =
        source.thenCompose(value -> makeStage(value));
~~~

Nếu `source` chưa hoàn tất, callback được đăng ký rồi có thể được chạy khi source hoàn tất. Nếu source đã hoàn tất sẵn, callback có thể chạy ngay trên thread gắn dependent stage. Nếu source hoàn tất từ một thread khác, thread hoàn tất có thể chạy callback đó. Javadoc của CompletableFuture không bảo đảm callback non-Async sẽ luôn chạy một thread cố định.

Các hệ quả:
- Không phụ thuộc `Thread.currentThread().getName()` trừ khi có executor policy được chỉ định và kiểm thử phù hợp.
- Callback non-Async nên **nhẹ**, không block lâu.
- Đừng giữ `synchronized` lock rồi complete một CompletableFuture mà callbacks có thể block/đụng lại cùng tài nguyên; tránh lock ordering cycles.
- Tránh cập nhật shared mutable state trong mapper mà không có memory visibility/synchronization thích hợp.
- Nếu cần đưa callback lên đúng executor, dùng overload `thenComposeAsync(fn, executor)`.

### Async không tự bảo đảm tiến triển nếu pool bị starve

Ngay cả khi dùng thenComposeAsync, nếu executor đã shutdown, task async có thể bị reject và dependent stage có thể hoàn tất exceptionally. Nếu executor chỉ có một worker và mapper cố `join` một task mới submit vào chính pool, vẫn có thể starvation. Async operator giúp **dispatch function**, không giải được dependency graph sai.

## 20. Thiết kế một pipeline có giới hạn tài nguyên

Một hệ thống thật cần đặt vấn đề ngoài cú pháp:

**Đầu vào:** có bao nhiêu requests đến đồng thời? Có limit, queue/backpressure không?

**Nguồn dữ liệu:** mỗi stage trả một CompletionStage thực sự hay nó block thread trước khi trả? Nếu block, executor có bao nhiêu threads? Downstream có connection limit/rate quota?

**Kết quả:** giá trị `null` hay empty có nghĩa gì? Cần validation trước bước sau?

**Exception:** một stage fail sẽ làm pipeline fail, hay cần fallback/retry có giới hạn? Nếu retry, có tổng deadline và idempotency?

**Lifecycle:** ai sở hữu executor, khi nào shutdown, còn inner stages chưa hoàn tất không?

**Observability:** đo queue time, thời gian mỗi stage, tỷ lệ lỗi/timeouts, số tasks cancel mà vẫn tiếp tục I/O, tail latency.

**Data safety:** dữ liệu truyền giữa stages nên immutable hoặc có ownership rõ ràng. CompletableFuture giúp chuyển completion/result có các memory consistency guarantees thích hợp khi sử dụng đúng, nhưng **không tự bảo vệ** các mutations đồng thời lên một shared object bên ngoài.

## 21. Một ví dụ API design tốt hơn nested callbacks

### Callbacks lồng sâu, khó xử lý

~~~java
startAsync().thenAccept(id -> {
    loadAsync(id).thenAccept(record -> {
        enrichAsync(record).thenAccept(enriched -> {
            saveAsync(enriched).thenAccept(saved -> {
                logResult(saved);
            });
        });
    });
});
~~~

Đây là đoạn minh họa với các methods ứng dụng. Vấn đề:
- Stage ngoài có thể hoàn tất **trước** các inner callbacks.
- Exceptions trong inner chains có thể không được quan sát/lan truyền tới đúng đối tượng caller theo kỳ vọng.
- Người dùng khó thêm một timeout, fail-fast hoặc logging ở cấp pipeline.
- Trách nhiệm cancel và lifecycle bị phân tán.

### Compose một graph rõ ràng

~~~java
CompletableFuture<Result> pipeline =
        startAsync()
            .thenCompose(id -> loadAsync(id))
            .thenCompose(record -> enrichAsync(record))
            .thenCompose(enriched -> saveAsync(enriched))
            .whenComplete((result, error) ->
                    logOutcome(result, error));
~~~

Đây là đoạn minh họa tích hợp, `Result` và các phương thức do ứng dụng định nghĩa. Khi các methods trả CompletableFuture/CompletionStage tương thích, ta có **một graph kết quả** để caller monitor, timeout, log và xử lý lỗi. Mỗi stage được nối bằng thenCompose thay vì một thenAccept callback không trả/đợi inner stage.

**Lưu ý:** `whenComplete` trả thêm một dependent stage; log của bạn cũng có thể thất bại. Nếu muốn đảm bảo không mất exception gốc, logging nên tránh ném exception ngoài dự kiến.

## 22. Những sai lầm thường gặp khi review

**Sai lầm 1:** Dùng `thenApply` cho function trả CompletableFuture rồi nhận `CF<CF<T>>` không mong muốn. Dùng `thenCompose` nếu cần flatten.

**Sai lầm 2:** Dùng `thenCompose` cho function chỉ trả String/Integer. Mapper cần trả CompletionStage<U>, không phải U.

**Sai lầm 3:** Gọi `join()` trong mapper để biến future thành giá trị thường. Nó block thread callback; dùng composition non-blocking.

**Sai lầm 4:** Cho rằng `thenCompose` tự tạo thread mới. Non-Async không có guarantee thread hop.

**Sai lầm 5:** Cho rằng `thenComposeAsync` tự làm mọi inner operations asynchronous. Nó dispatch callback theo executor; method trả stage vẫn có thể block trước khi trả.

**Sai lầm 6:** Bỏ qua failure upstream; mapper không chạy khi upstream exceptional, nên phải xử lý recovery đúng vị trí.

**Sai lầm 7:** Mapper trả null `CompletionStage`. Đó là lỗi, không phải “future hoàn tất với null”.

**Sai lầm 8:** Dùng `exceptionally` để trả một CompletableFuture khi dependent type là T. Dùng `exceptionallyCompose` cho fallback stage.

**Sai lầm 9:** Đặt fallback quá sớm và vô tình cho phép bước sau chạy với dữ liệu không phù hợp. Chọn chỗ recovery theo nghiệp vụ.

**Sai lầm 10:** Tưởng `cancel(true)` của CompletableFuture sẽ interrupt worker đang chạy. Default implementation không dùng mayInterruptIfRunning như lệnh kill.

**Sai lầm 11:** Tưởng `orTimeout` hủy network I/O và rollback writes. Nó điều chỉnh completion của CF; I/O cần timeout/cancel riêng.

**Sai lầm 12:** Cho rằng `get(timeout)` tự cancel task. Nó chỉ giới hạn caller wait.

**Sai lầm 13:** Đưa cả hai tác vụ độc lập vào chuỗi thenCompose, làm mất khả năng song song cần thiết. Dùng `thenCombine`/`allOf` nếu phù hợp.

**Sai lầm 14:** Cho rằng success của upstream khiến toàn pipeline done, dù inner stage còn pending. Composed stage chờ inner completion.

**Sai lầm 15:** Tạo dependency cycle, ví dụ stage A chờ stage B và B chờ A. CompletableFuture graph vẫn có thể không tiến triển.

**Sai lầm 16:** Không shutdown executor tự sở hữu; giữ platform threads không cần thiết. Ngược lại shutdown executor **shared** sau một request cũng sai ownership.

**Sai lầm 17:** Không handle `CompletionException` ở boundary, khiến lỗi thực bị che. Kiểm tra cause và log theo policy.

**Sai lầm 18:** Quên ngưỡng concurrent requests; mỗi request chain nhiều I/O có thể làm bùng tải downstream. Dùng semaphore, queue bound, connection limit/rate limit.

**Sai lầm 19:** Giữ mutable data chung qua nhiều callbacks mà thiếu thread safety. Kết quả của stage an toàn không biến mọi object được tham chiếu thành immutable.

**Sai lầm 20:** Dùng callback chain làm thay transaction manager. Khi bước sau fail, các side effects của bước trước không được tự rollback.

## 23. Checklist ứng dụng

- [ ] Bước kế tiếp **phụ thuộc giá trị T** từ bước trước?
- [ ] Mapper có trả `CompletionStage<U>`, không phải U hay null?
- [ ] Dùng `thenApply` cho synchronous map, `thenCompose` cho async stage?
- [ ] Tránh `join/get` trong callback trên worker?
- [ ] Có nhận biết source failure và inner failure đều làm composed stage exceptional?
- [ ] Cần fallback bằng giá trị hay bằng stage mới?
- [ ] Async overload có dùng đúng executor theo workload CPU/I/O?
- [ ] Không mặc định non-Async callback chạy trên một thread cố định?
- [ ] Đã kiểm soát blocking work, queue capacity và downstream concurrency?
- [ ] Có tổng deadline, timeout của mỗi I/O stage và cleanup riêng?
- [ ] Không giả định cancellation tự propagate tới mọi futures/inner tasks?
- [ ] Có log outcome/tracing của từng stage với correlation id phù hợp?
- [ ] Data objects có ownership rõ ràng, tránh race?
- [ ] Có xử lý errors từ mapper và từ inner stage?
- [ ] Nếu cần parallel independent stages, dùng `thenCombine`/`allOf`?
- [ ] Executor có owner và shutdown/awaitTermination rõ?
- [ ] Tests có điều phối completion bằng `CompletableFuture.complete` hoặc latch, không sleep đoán scheduler?
- [ ] Sau side effects, đã xử lý idempotency, retry budget và transaction consistency?

## 24. Bài tập tự kiểm tra

**Câu 1.** `thenApply(id -> loadAsync(id))` khi `loadAsync` trả `CompletableFuture<User>` thì type kết quả là gì?

**Đáp án:** `CompletableFuture<CompletableFuture<User>>` (giả sử source là CompletableFuture<String>).

**Câu 2.** Đổi thành `thenCompose(id -> loadAsync(id))` thì type kết quả?

**Đáp án:** `CompletableFuture<User>`.

**Câu 3.** Stage A hoàn tất exceptionally; function đưa vào `A.thenCompose(fn)` có được gọi không?

**Đáp án:** Không. Dependent stage hoàn tất exceptionally; cần recovery phù hợp nếu muốn tiếp tục.

**Câu 4.** A thành công, fn trả một CompletableFuture chưa xong. Composed stage đã done chưa?

**Đáp án:** Chưa; nó theo dõi completion của inner stage.

**Câu 5.** `thenComposeAsync(fn, executor)` đảm bảo điều gì?

**Đáp án:** Function compose được thực thi qua executor được chỉ định; không hứa tất cả inner work cũng chạy trên executor đó.

**Câu 6.** Một inner stage hoàn tất exceptionally. Composed stage thế nào?

**Đáp án:** Hoàn tất exceptionally; boundary join/get sẽ thể hiện lỗi theo contract tương ứng.

**Câu 7.** Khi mapper muốn trả giá trị null hợp lệ, nên `return null` hay `return completedFuture(null)`?

**Đáp án:** `completedFuture(null)`. Trả null thay vì một stage là sai hợp đồng.

**Câu 8.** Vì sao `join()` trong mapper có thể gây deadlock ở executor một worker?

**Đáp án:** Mapper giữ worker chờ một task mới được submit vào chính executor đó nhưng không có worker rảnh để chạy task mới.

**Câu 9.** Bước A và B độc lập, cần tổng A+B. Dùng thenCompose để chạy B sau A có tối ưu không?

**Đáp án:** Không cần. Nên khởi động A và B độc lập rồi dùng `thenCombine` hoặc `allOf` để ghép khi cả hai xong.

**Câu 10.** `CompletableFuture.cancel(true)` có chắc interrupt công việc phía sau composed stage không?

**Đáp án:** Không. Javadoc nói tham số mayInterruptIfRunning không có hiệu lực trong CompletableFuture mặc định và cancellation không tự đi khắp graph.

**Câu 11.** `orTimeout(100, MILLISECONDS)` có chắc remote request đã dừng ở 100ms không?

**Đáp án:** Không. Nó làm CompletableFuture bị completed exceptionally khi quá hạn, không tự quản lý tài nguyên remote.

**Câu 12.** Nếu chỉ muốn fallback bất đồng bộ khi pipeline lỗi thì dùng gì?

**Đáp án:** `exceptionallyCompose(error -> fallbackAsync(error))` với Java 12+.

## 25. Tài liệu chính thức

- **CompletableFuture — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **CompletionStage — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Executor — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- **ExecutorService — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ForkJoinPool — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **TimeUnit — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html
- **Future — Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html

**Kết luận:** `thenCompose()` là phép **flatMap của các CompletionStage**, giúp nối những bước bất đồng bộ **phụ thuộc kết quả** mà không tạo nested futures hoặc phải block worker bằng `join()`. Stage ngoài chỉ hoàn tất khi stage mà mapper trả về hoàn tất; lỗi upstream/mapper/inner stage được đưa qua exceptional-completion rules. Dùng `thenComposeAsync` khi thực sự cần executor policy, `thenApply` cho biến đổi đồng bộ, `thenCombine` cho nhánh độc lập, và quản lý riêng timeout/cancellation/side effects của các công việc nền.
