# Nhận diện Function và Consumer trong CompletableFuture (Java 17+)

## 1. Bối cảnh: CompletableFuture nhận hành vi dưới dạng functional interface

`CompletableFuture<T>` biểu diễn một tác vụ hoặc kết quả có thể hoàn thành ở tương lai với giá trị kiểu `T`, hoặc hoàn thành ngoại lệ. Nó triển khai `Future<T>` và `CompletionStage<T>`. Các phương thức như `thenApply`, `thenAccept` và `thenCompose` nhận **hành vi** dưới dạng lambda hoặc method reference, nhờ đó ta tạo các giai đoạn phụ thuộc nhau mà không cần tự gọi `get()` để chờ kết quả ở từng bước.

Để đọc đúng API, câu hỏi đầu tiên là: **Callback có trả lại một giá trị mà giai đoạn tiếp theo cần dùng hay chỉ tiêu thụ giá trị?**

- **`Function<T,R>`** nhận `T` và trả `R`: phù hợp khi **biến đổi** dữ liệu. Phương thức nổi bật là `thenApply`.
- **`Consumer<T>`** nhận `T`, không trả kết quả: phù hợp khi **xử lý/tiêu thụ** kết quả (ghi log, gửi thông báo, cập nhật một nơi nhận dữ liệu). Phương thức nổi bật là `thenAccept`.
- **`Runnable`** không nhận kết quả của giai đoạn trước và không trả giá trị: dùng với `thenRun`.
- Ngoài hai interface trên, API còn dùng `Supplier<T>`, `BiFunction<T,U,R>`, `BiConsumer<T,U>` và các biến thể có ngữ nghĩa chuyên biệt.

“Không trả kết quả” ở `Consumer` nghĩa là phương thức `accept` có kiểu trả về `void`; stage tạo bởi `thenAccept` có kiểu `CompletableFuture<Void>` và khi thành công, `join()` cho `null`. Điều đó không đồng nghĩa với `CompletableFuture<Void>` hoàn thành ngay lập tức hoặc callback không được chờ.

## 2. Đọc chữ ký API để phân biệt

Xét các chữ ký rút gọn theo `CompletionStage`/`CompletableFuture` (bỏ bớt wildcard và chi tiết override để dễ tập trung):

~~~java
<U> CompletableFuture<U> thenApply(Function<? super T, ? extends U> fn);

CompletableFuture<Void> thenAccept(Consumer<? super T> action);

CompletableFuture<Void> thenRun(Runnable action);

<U> CompletableFuture<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
~~~

Cách đọc:

1. Nếu tham số callback là `Function<? super T, ? extends U>`, kết quả của callback là **giá trị U mới**; stage tiếp theo chứa `U`.
2. Nếu callback là `Consumer<? super T>`, nó **nhận kết quả T** của stage trước nhưng không tạo giá trị kết quả mới. Stage kế tiếp có kiểu `Void`.
3. Nếu callback là `Runnable`, nó không có tham số cho kết quả `T`; nó chỉ chạy sau khi stage trước hoàn thành bình thường.
4. Nếu callback là `Function<T, CompletionStage<U>>`, ý nghĩa vẫn là “nhận T và trả một giá trị”, nhưng giá trị ấy **chính là một giai đoạn bất đồng bộ**. `thenCompose` sẽ nối/flatten stage bên trong thành một stage `U` duy nhất.

Trong code thực tế, có thể dùng method reference thay cho lambda khi chữ ký tương thích:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("  Java  ");

CompletableFuture<String> trimmed =
        source.thenApply(String::trim); // Function<String, String>

CompletableFuture<Integer> length =
        trimmed.thenApply(String::length); // Function<String, Integer>

CompletableFuture<Void> printed =
        trimmed.thenAccept(System.out::println); // Consumer<String>
~~~

`printed` đại diện cho sự hoàn thành của hành động in; `length` đại diện cho một kết quả `Integer`. Đây là **hai nhánh phụ thuộc độc lập** từ `trimmed`: mỗi nhánh dùng cùng giá trị `String` nhưng có mục tiêu khác nhau.

## 3. `thenApply`: Function biến đổi T thành U

Ví dụ:

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture(" java ");

CompletableFuture<Integer> number = future
        .thenApply(String::trim)
        .thenApply(String::length);

System.out.println(number.join()); // 4
~~~

Đường đi dữ liệu:

~~~text
CompletableFuture<String> (" java ")
    │
    └─ thenApply(String::trim)       [Function<String, String>]
              │                      -> "java"
              └─ thenApply(String::length) [Function<String, Integer>]
                        │
                        └─ CompletableFuture<Integer> (4)
~~~

`thenApply` tạo stage mới có giá trị trả về từ `Function.apply`. Nếu giai đoạn trước hoàn thành bình thường với giá trị `x`, callback `fn.apply(x)` được gọi để tạo kết quả cho stage phụ thuộc. Nếu callback ném ngoại lệ, stage phụ thuộc hoàn thành ngoại lệ. Nếu stage trước đã hoàn thành ngoại lệ, `thenApply` thông thường **không được gọi**; ngoại lệ sẽ lan sang stage phụ thuộc.

Có thể hình dung:

~~~java
Function<String, Integer> parseLength = String::length;
CompletableFuture<Integer> result = future.thenApply(parseLength);
~~~

`Function` **phải có giá trị trả về phù hợp**. Một lambda chỉ gọi phương thức có kết quả `void` như `s -> System.out.println(s)` không thích hợp cho `thenApply` khi không trả ra giá trị `U`.

### 3.1. Function có thể thay đổi kiểu

~~~java
CompletableFuture<Integer> size =
        CompletableFuture.completedFuture("abc")
                .thenApply(String::length);
~~~

Ở đây kiểu đầu là `String`, kiểu đầu ra là `Integer`. Đừng suy từ tên `thenApply` rằng kiểu của stage phải giữ nguyên.

## 4. `thenAccept`: Consumer nhận T và kết thúc bằng Void

Ví dụ:

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture("Java");

CompletableFuture<Void> logged = future
        .thenAccept(value -> System.out.println("Received: " + value));

logged.join();
~~~

Stdout:

~~~text
Received: Java
~~~

Đường đi:

~~~text
CompletableFuture<String> ("Java")
    │
    └─ thenAccept(value -> print(value)) [Consumer<String>]
                 │
                 └─ CompletableFuture<Void> (hoàn thành bình thường)
~~~

Consumer có một phương thức trừu tượng `void accept(T value)`. Vì thế:

~~~java
Consumer<String> printer = System.out::println;
CompletableFuture<Void> completed = future.thenAccept(printer);
~~~

là cách biểu diễn rõ ràng việc dùng một hành động phụ thuộc vào kết quả của `future`.

**Lưu ý quan trọng:** `thenAccept` không trả nguyên dữ liệu `T` để chain tiếp. Nếu muốn tạo kết quả mới sau khi xử lý, hãy cân nhắc `thenApply` với giá trị trả về có chủ đích; nếu cần cả hành động phụ lẫn giữ kết quả gốc, xem `whenComplete` ở phần 8 hoặc tách hai nhánh stage.

~~~java
CompletableFuture<String> input =
        CompletableFuture.completedFuture("hello");

CompletableFuture<Void> sideEffect =
        input.thenAccept(System.out::println);

// Không hợp lệ: sideEffect.thenApply(String::length)
// vì stage trước mang kiểu Void, không phải String.
~~~

Khi stage trước hoàn thành ngoại lệ, Consumer của `thenAccept` không chạy và stage sau cũng hoàn thành ngoại lệ. Nếu `accept` tự ném ngoại lệ, stage phụ thuộc cũng hoàn thành ngoại lệ.

### 4.1. `thenRun` khác gì?

`thenRun(Runnable)` cũng trả stage `Void` nhưng callback **không nhận giá trị của stage trước**:

~~~java
CompletableFuture<Void> done =
        CompletableFuture.completedFuture("ignored")
                .thenRun(() -> System.out.println("Finished"));
~~~

`thenAccept(value -> ...)` dùng được `value`; `thenRun(() -> ...)` không có `value` làm tham số. Cả hai chỉ chạy sau khi giai đoạn phụ thuộc hoàn thành bình thường.

## 5. `thenCompose`: Function trả một CompletionStage khác

Nếu hàm xử lý đã là API bất đồng bộ, chữ ký của nó thường có dạng `T -> CompletionStage<U>`. `thenCompose` nhận chính **Function** đó rồi nối stage được trả về.

Giả sử có API:

~~~java
static CompletableFuture<String> findNameAsync(int id) {
    return CompletableFuture.completedFuture("User-" + id);
}
~~~

Dùng `thenCompose`:

~~~java
CompletableFuture<String> name =
        CompletableFuture.completedFuture(7)
                .thenCompose(id -> findNameAsync(id));
// Tương đương: .thenCompose(Demo::findNameAsync)

System.out.println(name.join()); // User-7
~~~

Nếu dùng `thenApply` với cùng hàm async:

~~~java
CompletableFuture<CompletableFuture<String>> nested =
        CompletableFuture.completedFuture(7)
                .thenApply(id -> findNameAsync(id));
~~~

`nested` có **hai tầng future**, vì `thenApply` giữ nguyên đối tượng future mà callback trả về làm “giá trị” của stage tiếp theo. `thenCompose` tạo một `CompletableFuture<String>` phụ thuộc cả stage trước lẫn stage được callback tạo ra:

~~~text
thenApply(T -> CompletableFuture<U>):
    CompletableFuture<T>
      └─ CompletableFuture<CompletableFuture<U>>

thenCompose(T -> CompletableFuture<U>):
    CompletableFuture<T>
      └─ CompletableFuture<U>
~~~

Quy tắc nhận diện: Nếu callback trả một **giá trị đồng bộ U**, dùng `thenApply`; nếu callback trả một **CompletionStage<U>`** và muốn nối luồng bất đồng bộ, dùng `thenCompose`.

`thenCompose` không dùng `Consumer` vì callback phải trả một stage, không phải `void`. Nó cũng không “đợi bằng cách block” như `join()` trong callback; đây là kết hợp các stage bất đồng bộ.

## 6. Bảng nhận diện nhanh các API phổ biến

| Phương thức | Callback chính | Kết quả stage | Ý định |
| --- | --- | --- | --- |
| `thenApply(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Biến đổi kết quả |
| `thenApplyAsync(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Biến đổi, lên lịch theo cơ chế async |
| `thenAccept(action)` | `Consumer<T>` | `CompletableFuture<Void>` | Tiêu thụ kết quả |
| `thenAcceptAsync(action)` | `Consumer<T>` | `CompletableFuture<Void>` | Tiêu thụ, lên lịch theo cơ chế async |
| `thenRun(action)` | `Runnable` | `CompletableFuture<Void>` | Chạy hành động không cần T |
| `thenCompose(fn)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | Nối tiếp thao tác async |
| `thenCombine(other,fn)` | `BiFunction<T,U,V>` | `CompletableFuture<V>` | Kết hợp hai giá trị thành giá trị mới |
| `thenAcceptBoth(other,action)` | `BiConsumer<T,U>` | `CompletableFuture<Void>` | Tiêu thụ hai giá trị |
| `exceptionally(fn)` | `Function<Throwable,T>` | `CompletableFuture<T>` | Phục hồi từ lỗi bằng giá trị |
| `handle(fn)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | Chuyển đổi kết quả/lỗi thành U |
| `whenComplete(action)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | Quan sát thành công hoặc lỗi |

Bảng dùng kiểu generic khái quát để dễ đọc; API thực tế có wildcard `? super`/`? extends` và một số biến thể trả `CompletionStage` khi được nhìn qua interface `CompletionStage`. Điểm cốt lõi là **kiểu SAM và loại kết quả stage**.

`thenCombine` và `thenAcceptBoth` cho thấy quy tắc được mở rộng từ một sang hai tham số: **BiFunction** trả giá trị; **BiConsumer** không trả giá trị.

~~~java
CompletableFuture<Integer> a = CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b = CompletableFuture.completedFuture(3);

CompletableFuture<Integer> total =
        a.thenCombine(b, Integer::sum); // BiFunction<Integer,Integer,Integer>

CompletableFuture<Void> show =
        a.thenAcceptBoth(b, (x, y) -> System.out.println(x + y));
~~~

Không phải mọi API có tên `*Async` đều nhận `Function`: `supplyAsync` nhận `Supplier<T>`, `runAsync` nhận `Runnable`.

## 7. Ví dụ Java 17+ đầy đủ, chạy với stdout xác định

Lưu thành `CompletableFutureCallbacksDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

public class CompletableFutureCallbacksDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture(" java ");

        Function<String, String> trim = String::trim;
        CompletableFuture<Integer> length = source
                .thenApply(trim)
                .thenApply(String::length);
        System.out.println("length=" + length.join());

        Consumer<String> printer =
                s -> System.out.println("accept=" + s);
        CompletableFuture<Void> consumed = source
                .thenApply(String::trim)
                .thenAccept(printer);
        consumed.join();
        System.out.println("Void result=" + consumed.join());

        CompletableFuture<Void> ignored =
                source.thenRun(() -> System.out.println("run=done"));
        ignored.join();

        CompletableFuture<String> composed =
                CompletableFuture.completedFuture(7)
                        .thenCompose(id -> findNameAsync(id));
        System.out.println("composed=" + composed.join());

        CompletableFuture<Integer> failed =
                CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad"))
                        .thenApply(String::length);
        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> -1);
        System.out.println("recovered=" + recovered.join());

        CompletableFuture<String> handled =
                CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("oops"))
                        .handle((value, error) ->
                                error == null ? value.toUpperCase() : "fallback");
        System.out.println("handled=" + handled.join());

        AtomicInteger observations = new AtomicInteger();
        CompletableFuture<Integer> watched =
                CompletableFuture.completedFuture(4)
                        .whenComplete((value, error) ->
                                observations.incrementAndGet());
        watched.join();
        System.out.println("observed=" + observations.get());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> async =
                    CompletableFuture.supplyAsync(() -> "abc", pool)
                            .thenApplyAsync(String::length, pool);
            System.out.println("async=" + async.join());
        } finally {
            pool.shutdown();
        }
    }

    static CompletableFuture<String> findNameAsync(int id) {
        return CompletableFuture.completedFuture("User-" + id);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CompletableFutureCallbacksDemo.java
java CompletableFutureCallbacksDemo
~~~

Stdout:

~~~text
length=4
accept=java
Void result=null
run=done
composed=User-7
recovered=-1
handled=fallback
observed=1
async=3
~~~

Tại sao thứ tự output dự đoán được? Các stage đầu sử dụng `completedFuture` hoặc `failedFuture` nên callback không-async có thể chạy ngay trên luồng gọi khi đăng ký; chương trình `join()` tại từng bước trước khi in tiếp. Phần cuối có executor riêng, nhưng chương trình chỉ in sau khi `async.join()` hoàn thành. Ví dụ được thiết kế để giải thích callback và kiểu trả về, **không dùng thứ tự scheduling ngẫu nhiên để chứng minh thứ tự in**.

## 8. Xử lý ngoại lệ: Function và Consumer vẫn xuất hiện, nhưng ý nghĩa khác

### 8.1. `exceptionally` nhận Function để *phục hồi*

~~~java
CompletableFuture<Integer> number =
        CompletableFuture.<Integer>failedFuture(
                new IllegalStateException("unavailable"))
                .exceptionally(error -> 0);

System.out.println(number.join()); // 0
~~~

`exceptionally` nhận `Function<Throwable, ? extends T>` để cung cấp **giá trị dự phòng kiểu T** khi stage trước hoàn thành ngoại lệ. Nếu stage trước thành công, callback phục hồi **không chạy**. Điều này khác `thenApply`: `thenApply` chạy trên nhánh thành công; `exceptionally` chạy trên nhánh thất bại.

Một callback xử lý lỗi chỉ in log, không trả giá trị, **không hợp lệ** làm toàn bộ đối số `exceptionally`:

~~~java
// Sai vì lambda không trả Integer:
// failed.exceptionally(error -> System.out.println(error));
~~~

Nếu muốn log và phục hồi, viết lambda có giá trị trả về:

~~~java
CompletableFuture<Integer> safe = number.exceptionally(error -> {
    System.err.println(error.getMessage());
    return -1;
});
~~~

Trong đoạn này, vì `number` đã được phục hồi thành công thành `0` nên `exceptionally` tiếp theo không chạy. Đây là chủ ý minh họa rằng **vị trí đặt callback phục hồi quyết định nó có nhận lỗi hay không**; muốn log lỗi gốc, hãy gắn callback lên stage thất bại chưa được phục hồi.

### 8.2. `handle` nhận BiFunction để *biến đổi cả hai trường hợp*

~~~java
CompletableFuture<String> status =
        CompletableFuture.<String>failedFuture(
                new RuntimeException("service down"))
                .handle((value, error) ->
                        error == null ? value : "default");

System.out.println(status.join()); // default
~~~

`handle(BiFunction<T,Throwable,U>)` được gọi khi stage trước hoàn thành, dù thành công hay thất bại. Thông thường, ở nhánh thành công `error == null`, còn nhánh lỗi `error != null`; nếu cần, có thể trả `U` khác `T`. Lambda có **giá trị trả về**, vì callback là `BiFunction`.

### 8.3. `whenComplete` nhận BiConsumer để *quan sát*

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("ok")
                .whenComplete((value, error) -> {
                    if (error == null) {
                        System.out.println("completed=" + value);
                    } else {
                        System.err.println("failed=" + error);
                    }
                });
~~~

`whenComplete(BiConsumer<T,Throwable>)` thường dùng để log, metric, cleanup nhẹ hoặc quan sát cả thành công lẫn thất bại. Nó **không đổi giá trị thành công**, và không biến lỗi thành thành công chỉ nhờ in log. Nếu callback `whenComplete` ném lỗi, stage sau có thể hoàn thành ngoại lệ; nếu stage gốc đã lỗi thì lỗi gốc được ưu tiên theo hợp đồng API.

Phân biệt rõ:

| Nhu cầu | API | Vì sao |
| --- | --- | --- |
| Biến đổi kết quả thành công | `thenApply` | `Function<T,U>` trả U |
| Sử dụng kết quả thành công, không lấy U mới | `thenAccept` | `Consumer<T>` trả void |
| Phục hồi lỗi bằng giá trị dự phòng | `exceptionally` | `Function<Throwable,T>` trả T |
| Chuyển đổi từ kết quả hoặc lỗi | `handle` | `BiFunction<T,Throwable,U>` trả U |
| Ghi nhận kết quả hoặc lỗi và giữ trạng thái gốc | `whenComplete` | `BiConsumer<T,Throwable>` trả void |

## 9. Đồng bộ, bất đồng bộ và thread thực thi callback

Tên `CompletableFuture` dễ gây hiểu nhầm rằng mọi callback đều chạy trên một thread riêng. Thực tế:

- `thenApply`, `thenAccept`, `thenCompose` **không có hậu tố Async** có thể chạy trên thread hoàn thành stage trước hoặc thread khác đang đăng ký/điều khiển hoàn thành; **đừng giả định cố định thread cụ thể**.
- `thenApplyAsync`, `thenAcceptAsync`, `thenComposeAsync` là các biến thể lên lịch callback theo cơ chế async. Khi không truyền executor, `CompletableFuture` thường dùng `ForkJoinPool.commonPool()` theo chính sách thực thi của lớp (có quy định dự phòng khi common pool không đủ parallelism).
- Truyền `Executor` vào các overload tương ứng khi cần kiểm soát nơi thực thi hoặc cách cấp thread.
- `thenApply` và `thenAccept` khác nhau ở **contract của callback**; từ `Async` khác nhau ở **cách thực thi**. Đó là hai trục phân biệt độc lập.

Ví dụ với executor riêng (đặt trong chương trình có `main`):

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<Void> pipeline =
            CompletableFuture.supplyAsync(() -> "data", executor)
                    .thenApplyAsync(String::toUpperCase, executor)
                    .thenAcceptAsync(System.out::println, executor);

    pipeline.join();
} finally {
    executor.shutdown();
}
~~~

Khi dùng callback có blocking I/O, không nên lạm dụng common pool mà không xem xét đặc điểm tải và chiến lược executor. Việc `thenAccept` là Consumer không tự quyết định callback chạy đồng bộ trên thread nào.

`join()` và `get()` là những lời gọi **chờ kết quả**; nên đặt ở ranh giới thực sự cần kết quả, tránh gọi `join()` bên trong từng callback async một cách tùy tiện vì có thể gây block và làm giảm khả năng kết hợp bất đồng bộ. `join()` ném `CompletionException` cho các lỗi cần được bọc; `get()` có thể ném checked `ExecutionException` và `InterruptedException`. Điều này không thay đổi bản chất của `Function`/`Consumer`, nhưng ảnh hưởng cách bạn xử lý lỗi của pipeline.

## 10. Null, lỗi, side effect và sự khác biệt về khả năng chain

### 10.1. Một kết quả null là hợp lệ, nhưng callback cần sẵn sàng

~~~java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

CompletableFuture<String> copied =
        empty.thenApply(value -> value); // Hoàn thành với null.
~~~

Tại đây `thenApply` vẫn có thể chạy vì stage trước **hoàn thành bình thường**, dù giá trị là null. Nếu viết `String::length` thì việc nhận receiver null sẽ ném `NullPointerException` và stage phụ thuộc trở thành exceptional completion. `thenAccept` cũng có thể nhận null làm tham số; người viết Consumer phải quyết định cách xử lý.

### 10.2. Side effect và lỗi trong Consumer không bị “nuốt”

~~~java
CompletableFuture<Void> logged =
        CompletableFuture.completedFuture("x")
                .thenAccept(value -> {
                    throw new IllegalStateException("log failed");
                });

// logged.join() sẽ ném CompletionException
// với nguyên nhân liên quan đến IllegalStateException.
~~~

Không có kết quả `U` nghĩa là không có giá trị kinh doanh để truyền tiếp, **không có nghĩa là callback bất khả thất bại**. Nếu side effect của Consumer quan trọng, phải quan sát hoặc kết hợp stage `CompletableFuture<Void>` của nó vào luồng điều phối phù hợp.

### 10.3. Consumer không phải cách giữ nguyên giá trị

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("abc");

CompletableFuture<Void> consumed =
        source.thenAccept(System.out::println); // mất T ở nhánh này

CompletableFuture<String> kept =
        source.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println(value);
            }
        }); // vẫn là CompletableFuture<String>
~~~

`whenComplete` được thiết kế để quan sát kết quả, nhưng cả hai ví dụ đều có side effect; vì vậy cần thận trọng nếu callback được gắn nhiều lần hoặc luồng có retry ở tầng ứng dụng.

### 10.4. Thứ tự giữa nhiều nhánh không được bảo đảm

Nếu gắn hai `thenAccept` trên cùng source async, cả hai là stage phụ thuộc và không có ràng buộc mặc định cho thứ tự hoàn thành của chúng. Nếu thứ tự là yêu cầu nghiệp vụ, hãy nối stage rõ ràng qua `thenCompose` hoặc `thenRun`/`thenAccept` và chờ stage tổng hợp tương ứng.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng `thenApply(s -> println(s))` | `println` trả void, nhưng Function phải trả U | Dùng `thenAccept(System.out::println)` |
| Mong `thenAccept` trả lại `T` | Consumer không sinh giá trị U | Dùng `thenApply` hoặc `whenComplete` tùy mục đích |
| Dùng `thenApply` cho hàm trả Future rồi mong stage được flatten | `thenApply` giữ Future bên trong làm giá trị | Dùng `thenCompose` |
| Dùng `thenAccept` để nối API async | Consumer không trả stage để kết hợp | Dùng `thenCompose` |
| Cho rằng `thenRun` nhận kết quả trước đó | Runnable không có tham số | Dùng `thenAccept` nếu cần T |
| Cho rằng `whenComplete` xử lý xong lỗi | BiConsumer chỉ quan sát, không cung cấp giá trị hồi phục | Dùng `exceptionally` hoặc `handle` |
| Viết `exceptionally(e -> log(e))` nhưng không trả T | Function cần giá trị phù hợp | Log rồi `return fallback;` |
| Nghĩ mọi callback chạy thread mới | Bản không Async không cam kết thread cụ thể | Dùng overload Async + Executor nếu cần |
| Gọi `join()` liên tục trong từng callback | Blocking làm pipeline kém hiệu quả | Chain bằng `thenApply`/`thenCompose`, chờ ở cuối |
| Bỏ qua stage `Void` sau side effect | Lỗi callback vẫn nằm ở stage phụ thuộc | Kết hợp/kiểm tra stage đó với `join`, `whenComplete` hoặc cơ chế giám sát |

## 12. Bài tập ngắn có đáp án

**Câu 1.** Có `CompletableFuture<String> f`. Muốn biến chuỗi thành độ dài số nguyên, dùng API và interface nào?

Đáp án: `f.thenApply(String::length)`, tương ứng `Function<String,Integer>` và trả `CompletableFuture<Integer>`.

**Câu 2.** Muốn ghi kết quả String ra console, không cần giá trị kết quả mới?

Đáp án: `f.thenAccept(System.out::println)`, tương ứng `Consumer<String>`, trả `CompletableFuture<Void>`.

**Câu 3.** Callback nào nhận kết quả rồi trả một `CompletableFuture<User>` từ API khác để thực hiện tiếp mà không tạo hai lớp Future?

Đáp án: `thenCompose(id -> findUserAsync(id))`. Đây là Function trả `CompletionStage<User>`, không phải Consumer.

**Câu 4.** `thenAccept` có chạy khi future trước đó hoàn thành ngoại lệ không?

Đáp án: không. Stage phụ thuộc hoàn thành ngoại lệ; cần `exceptionally`, `handle` hoặc `whenComplete` để xử lý/quan sát đường lỗi theo đúng mục đích.

**Câu 5.** Vì sao `handle` dùng `BiFunction` nhưng `whenComplete` dùng `BiConsumer`?

Đáp án: cả hai nhận `(value, error)`, nhưng `handle` **trả U mới** để xác định kết quả tiếp theo, còn `whenComplete` **không trả giá trị** và dùng chủ yếu để quan sát mà giữ trạng thái của stage trước.

**Câu 6.** `thenApplyAsync` và `thenAcceptAsync` có cùng loại callback không?

Đáp án: không. `thenApplyAsync` nhận Function, `thenAcceptAsync` nhận Consumer; hậu tố Async chỉ liên quan cơ chế lên lịch thực thi.

## Ghi nhớ

Để nhận diện callback trong `CompletableFuture`, hãy đọc chữ ký phương thức và nhìn **kết quả mà hành vi cần trả**:

- **`Function<T,U>` = nhận T, trả U**, thường gặp ở `thenApply` (biến đổi) và `thenCompose` (trả CompletionStage để nối async).
- **`Consumer<T>` = nhận T, trả void**, thường gặp ở `thenAccept` (tiêu thụ kết quả).
- **`Runnable` = không nhận T, trả void**, thường gặp ở `thenRun`.
- **`BiFunction`** biến hai đầu vào thành kết quả mới; **`BiConsumer`** quan sát/tiêu thụ hai đầu vào và không trả kết quả.
- Khi xử lý lỗi, **`exceptionally` = Function phục hồi**, **`handle` = BiFunction chuyển đổi**, còn **`whenComplete` = BiConsumer quan sát**.

Các stage trả `Void` vẫn có ý nghĩa về **hoàn thành và thất bại**. Chọn đúng interface giúp bảo toàn kiểu dữ liệu, nối stage chính xác và xử lý exception có chủ đích.
