# completeExceptionally và failedFuture trong Java CompletableFuture

> **Chủ đề:** Java Core → Exception → CompletableFuture. Bài này phân tích hai cách biểu diễn thất bại trong `CompletableFuture`: `completeExceptionally(Throwable)` để hoàn tất bất thường một future **đang tồn tại**, và `CompletableFuture.failedFuture(Throwable)` để **tạo ngay** một future đã hoàn tất bất thường. Tập trung vào cơ chế hoàn tất, ngoại lệ quan sát được ở `get()`/`join()`, tác động tới dependent stages, lỗi thường gặp và cách chọn API phù hợp trong Java 17+.

## 1. Exceptional completion là trạng thái gì?

Một `CompletableFuture<T>` biểu diễn kết quả của một computation có thể đến ngay hoặc trong tương lai. Nó có các trạng thái quan sát chính:

- **Chưa hoàn tất:** chưa có kết quả cuối cùng; `isDone()` trả `false`.
- **Hoàn tất thành công:** chứa một giá trị kiểu `T`, kể cả `null`; người gọi có thể lấy giá trị với `get()` hoặc `join()`.
- **Hoàn tất bất thường (exceptional completion):** chứa thông tin về nguyên nhân thất bại; `isDone()` và `isCompletedExceptionally()` đều trả `true`.
- **Hủy (cancellation):** cũng là một dạng hoàn tất bất thường có ngữ nghĩa riêng; `isCancelled()` trả `true` đối với tương lai bị hủy theo cơ chế cancellation tương ứng.

Ví dụ: đọc tệp thất bại, dữ liệu không hợp lệ, dịch vụ không khả dụng, callback trả lỗi hoặc một stage ném exception. Các trường hợp này có thể được mô hình hóa bằng exceptional completion.

**Điểm quan trọng:** khi gọi `completeExceptionally(ex)`, phương thức **không ném `ex` ngay vào call stack của người gọi**. Nó ghi nhận `ex` làm trạng thái thất bại của future. Lỗi được biểu diễn lại ở nơi lấy kết quả hoặc xử lý stage, chẳng hạn `join()`, `get()`, `exceptionally(...)` hoặc `handle(...)`.

~~~text
                      CompletableFuture<T>
                             |
              +--------------+--------------+
              |                             |
         chưa hoàn tất                    hoàn tất
              |                             |
      complete(value)              +--------+---------+
      completeExceptionally(ex)    |                  |
              |                 thành công         bất thường
              |                 chứa value         chứa nguyên nhân lỗi
              |                  |                  |
              +------------------+------------------+
                                 |
                get(), join(), dependent stages
~~~

Một future đã hoàn tất theo cơ chế thông thường không thể chuyển từ thành công sang thất bại bằng một lần gọi `completeExceptionally` tiếp theo, hoặc ngược lại. Java chọn kết quả thắng cuộc khi có cạnh tranh hoàn tất. API nâng cao như `obtrudeValue`/`obtrudeException` có ngữ nghĩa khác và không nên được dùng như cách hoàn tất chuẩn.

## 2. completeExceptionally(Throwable): đánh dấu lỗi cho future đang có

Chữ ký instance method:

~~~java
public boolean completeExceptionally(Throwable ex)
~~~

Với một `CompletableFuture<T>` đã tạo, lời gọi:

~~~java
// Đoạn minh họa hợp lệ trong một phương thức Java.
CompletableFuture<String> promise = new CompletableFuture<>();
boolean won = promise.completeExceptionally(
        new IllegalStateException("service unavailable"));
~~~

có ý nghĩa:

1. Nếu `promise` chưa hoàn tất, nó được hoàn tất bất thường bằng `ex`; phương thức trả `true`.
2. Nếu `promise` đã hoàn tất (thành công, bất thường hoặc bị hủy), phương thức trả `false` và giữ nguyên trạng thái đã xác lập.
3. Phương thức là thao tác **hoàn tất future**, không phải lệnh yêu cầu worker đang chạy dừng hoặc undo tác dụng phụ.
4. Những stage phụ thuộc vào `promise` được kích hoạt/hoàn tất theo ngữ nghĩa của từng toán tử. Stage nhận lỗi có thể phục hồi, ghi nhận hoặc truyền lỗi tiếp.
5. Đối số `ex` phải khác `null`; truyền `null` sẽ dẫn tới `NullPointerException`. Loại `Throwable` có thể là checked exception như `IOException`, nhưng khi chờ kết quả, nó được báo qua wrapper phù hợp.

Giá trị boolean phản ánh **lần gọi này có thắng cuộc hoàn tất hay không**, không phản ánh thành công nghiệp vụ. Với một future đã được đánh dấu lỗi, `isCompletedExceptionally()` là `true` dù `completeExceptionally` đã trả `true` lúc trước.

### Nếu có nhiều nơi cùng complete

~~~java
// Minh họa trong một phương thức.
CompletableFuture<Integer> result = new CompletableFuture<>();

boolean first = result.complete(42); // true
boolean second = result.completeExceptionally(
        new IllegalStateException("too late")); // false
~~~

Future vẫn thành công với `42`. Nếu hai luồng thực sự tranh nhau gọi `complete(42)` và `completeExceptionally(ex)`, bên nào thắng phụ thuộc thứ tự thực thi; mỗi cuộc đua chỉ có **một** kết quả hoàn tất thông thường có hiệu lực. Không thiết kế nghiệp vụ dựa vào giả định cụ thể rằng luồng nào luôn thắng. Cần xác định rõ ai có quyền hoàn tất và ai có nhiệm vụ xử lý giá trị trả về `false`.

## 3. failedFuture(Throwable): tạo một future đã thất bại ngay

Chữ ký static factory:

~~~java
public static <U> CompletableFuture<U> failedFuture(Throwable ex)
~~~

Từ Java 9, có thể tạo trực tiếp:

~~~java
// Đoạn minh họa trong phương thức trả CompletableFuture<String>.
return CompletableFuture.failedFuture(
        new IllegalArgumentException("invalid customer id"));
~~~

Điều cần hiểu:

- Tạo một **đối tượng `CompletableFuture<U>` mới** đã hoàn tất bất thường từ thời điểm trả về.
- Không cần tạo `new CompletableFuture<>()` rồi gọi thêm `completeExceptionally(...)`.
- Không gửi công việc vào executor và không tạo thread; factory này **không phải** thao tác bất đồng bộ.
- Có thể làm phần kết quả của một API khai báo `CompletableFuture<T>` khi phát hiện lỗi đồng bộ (đầu vào sai, thiếu cấu hình, không đủ quyền) nhưng API vẫn nhất quán trả về một future.
- `ex` phải khác `null`, giống `completeExceptionally`.

Ví dụ:

~~~java
static CompletableFuture<String> lookup(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("id must not be blank"));
    }

    // Với hệ thống thật, nhánh hợp lệ thường sẽ gọi dịch vụ bất đồng bộ.
    return CompletableFuture.completedFuture("user:" + id);
}
~~~

Đây là một đoạn có thể đặt trong lớp Java thích hợp; `lookup(" ")` không cần đợi tác vụ nền để trở thành thất bại. Người gọi vẫn quyết định xử lý trạng thái lỗi của future qua `join()`, `get()` hoặc pipeline.

### Chọn kiểu generic

Khi return type của phương thức là `CompletableFuture<Order>`, trình biên dịch thường suy diễn `U = Order` từ ngữ cảnh trả về. Nếu thiếu ngữ cảnh, có thể chỉ rõ:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("invalid input"));
~~~

Đây là cú pháp type witness của static generic method trong Java, không phải một cách xử lý exception khác.

## 4. So sánh ngắn gọn hai API

| Tiêu chí | `completeExceptionally(Throwable)` | `CompletableFuture.failedFuture(Throwable)` |
|---|---|---|
| Loại phương thức | Instance method | Static factory |
| Đối tượng sử dụng | Future **đã tồn tại** | Tạo **future mới** |
| Giá trị trả về | `boolean`: lần hoàn tất có hiệu lực hay không | `CompletableFuture<U>` đã hoàn tất bất thường |
| Thời điểm dùng | Callback trả lỗi, nguồn dữ liệu đến muộn, bridge external API | Nhánh lỗi đã biết ngay lúc gọi một API trả future |
| Future trước lời gọi | Có thể pending hoặc đã hoàn tất | Không có future được chuyển trạng thái |
| Tác động đến completion đã tồn tại | Không thay nếu future đã done | Không đụng vào future nào khác |
| Tự khởi chạy bất đồng bộ | Không | Không |
| Khi đợi kết quả lỗi | `get()`/`join()` báo lỗi theo hợp đồng | Tương tự |
| Tác động tác vụ nền, side effect | Không tự hủy hoặc rollback | Không có tác vụ nền được khởi chạy bởi factory |

Hai API cùng dùng một kiểu `Throwable` để biểu diễn lỗi, nên khác biệt chủ yếu nằm ở **vòng đời và quyền sở hữu future**: đánh dấu một promise hiện hữu so với tạo một kết quả đã thất bại.

## 5. Ví dụ Java 17 chạy được: hoàn tất thất bại và đọc lỗi

Lưu toàn bộ mã dưới tên **`ExceptionalCompletionDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ExceptionalCompletionDemo {
    private static void show(String name, CompletableFuture<?> future) {
        try {
            future.join();
            System.out.println(name + ": success");
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(name + ": "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<Integer> length = pending.thenApply(String::length);

        boolean first = pending.completeExceptionally(
                new IllegalStateException("service unavailable"));
        boolean lateSuccess = pending.complete("too late");

        System.out.println("first failure won: " + first);
        System.out.println("late success won: " + lateSuccess);
        show("pending", pending);
        show("dependent", length);

        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad request"));
        show("failed", failed);

        CompletableFuture<String> recovered =
                failed.exceptionally(ex -> "fallback");
        System.out.println("recovery: " + recovered.join());

        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ready");
        System.out.println("overwrite success: "
                + success.completeExceptionally(
                        new IllegalStateException("ignored")));

        try {
            failed.get();
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            System.out.println("get cause: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac ExceptionalCompletionDemo.java
java ExceptionalCompletionDemo
~~~

**Standard output chính xác:**

~~~text
first failure won: true
late success won: false
pending: IllegalStateException: service unavailable
dependent: IllegalStateException: service unavailable
failed: IllegalArgumentException: bad request
recovery: fallback
overwrite success: false
get cause: IllegalArgumentException: bad request
~~~

Giải thích từng điểm:

1. `pending` ban đầu chưa hoàn tất, nên `completeExceptionally` thắng và trả `true`. `complete("too late")` sau đó không thể thay kết quả, trả `false`.
2. Stage `length = pending.thenApply(String::length)` đã được tạo trước thất bại. Khi nguồn hoàn tất bất thường, `thenApply` không gọi `String::length` và stage phụ thuộc cũng hoàn tất bất thường. `join()` của stage phụ thuộc báo `CompletionException` chứa nguyên nhân lỗi gốc.
3. `failedFuture` tạo ngay một future lỗi `IllegalArgumentException`, không lập lịch tác vụ nào.
4. `exceptionally` trả một **stage mới** có giá trị `"fallback"`, trong khi future `failed` vẫn là future hoàn tất bất thường.
5. `completedFuture("ready")` đã hoàn tất thành công, nên `completeExceptionally` gọi sau đó trả `false`.
6. `failed.get()` ném `ExecutionException` tại luồng gọi `get()`, và `getCause()` giữ `IllegalArgumentException` gốc.

Không có thread nền nào được tạo trong ví dụ; điều đó là chủ đích để kiểm chứng độc lập ngữ nghĩa completion trước khi thêm yếu tố concurrency.

## 6. join(), get() và getNow() báo lỗi ra sao?

Một future hoàn tất bất thường **không** khiến câu lệnh gọi `failedFuture(...)` hoặc `completeExceptionally(...)` ném ra ngoại lệ nguyên nhân. Lỗi được quan sát ở phương thức lấy kết quả.

| Cách đọc | Kiểu lỗi chính khi computation thất bại | Có checked exception trong hợp đồng? |
|---|---|---|
| `join()` | `CompletionException` thường chứa nguyên nhân qua `getCause()` | Không |
| `get()` | `ExecutionException` chứa nguyên nhân qua `getCause()` | Có: còn `InterruptedException` |
| `get(timeout, unit)` | `ExecutionException` nếu thất bại, `TimeoutException` nếu quá hạn chờ | Có |
| `getNow(valueIfAbsent)` | Nếu chưa xong thì trả fallback; nếu done exceptionally thì báo lỗi dạng completion | Không |
| `isCompletedExceptionally()` | Chỉ trả boolean, không cung cấp nguyên nhân | Không |

Trường hợp `CancellationException` có đường xử lý riêng. Đặc biệt `join()` có thể trực tiếp ném `CancellationException` với future bị hủy. Không nên khẳng định *mọi* exceptional completion đều chỉ ném `CompletionException`.

**Đọc nguyên nhân đúng cách:**

~~~java
// Trích đoạn trong một phương thức, đã có CompletableFuture<String> future.
try {
    String result = future.join();
    consume(result);
} catch (java.util.concurrent.CancellationException ex) {
    handleCancellation(ex);
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    handleFailure(cause);
}
~~~

`consume`, `handleCancellation` và `handleFailure` là những hàm minh họa phải được cung cấp bởi ứng dụng. Tương tự, với `get()`, cần bắt `InterruptedException` và `ExecutionException` theo đúng hợp đồng.

**Đừng phân loại dựa trên văn bản `getMessage()` của wrapper** nếu hệ thống cần quyết định retry hoặc mapping HTTP status. Hãy dùng kiểu exception/cause hoặc error code có hợp đồng ổn định.

### Có thể dùng checked exception làm cause không?

Có. Ví dụ:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(new java.io.IOException("disk full"));
~~~

`IOException` là checked exception, nhưng factory không khai báo `throws IOException` vì nó **chỉ chứa** exception trong future. Người gọi `get()` nhận `ExecutionException` và đọc `getCause()`; người gọi `join()` thấy `CompletionException` tương ứng. Đây là chuyển thông tin lỗi qua một đối tượng kết quả, không phải phá quy tắc kiểm tra checked exception của Java.

## 7. Recovery và observation của dependent stages

Các toán tử trên `CompletableFuture` xác định điều gì xảy ra sau khi một stage thất bại.

### 7.1. exceptionally: chuyển thất bại thành giá trị thành công mới

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("not found"));

CompletableFuture<String> fallback =
        source.exceptionally(ex -> "default");

System.out.println(fallback.join()); // default
~~~

`exceptionally` chỉ chạy ở nhánh lỗi. Nếu callback phục hồi trả giá trị, **stage phụ thuộc** có kết quả thành công. Nếu callback phục hồi ném exception, stage phụ thuộc lại thất bại. Future `source` ban đầu vẫn thất bại và sẽ tiếp tục báo lỗi nếu gọi `source.join()`.

### 7.2. handle: xử lý cả giá trị lẫn lỗi

~~~java
// Ví dụ trong phương thức Java.
CompletableFuture<Integer> normalized =
        CompletableFuture.<String>failedFuture(
                new IllegalStateException("unavailable"))
        .handle((value, error) -> error == null ? value.length() : -1);
~~~

`handle` nhận một trong hai dạng: giá trị thành công hoặc lỗi; nó có thể tạo kiểu kết quả khác. Ở đây `normalized.join()` trả `-1`. Khi nguồn thành công với giá trị `null`, `error == null` vẫn là dấu hiệu hoàn tất thành công; ứng dụng phải quyết định liệu `value` có thể null hay không trước khi gọi phương thức trên nó.

### 7.3. whenComplete: quan sát, không mặc định sửa trạng thái thất bại

~~~java
CompletableFuture<String> observed =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("bad"))
        .whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("logged failure");
            }
        });
~~~

`whenComplete` hữu ích để log, đo metrics, ghi trace. Nếu nguồn lỗi thì stage `observed` thông thường vẫn hoàn tất lỗi; không nên xem đây là phép recovery. Nếu muốn biến thất bại thành kết quả hợp lệ, dùng `exceptionally` hoặc `handle` và mô tả giá trị fallback.

### 7.4. thenApply, thenCompose và propagation

- `thenApply` chỉ chuyển đổi giá trị khi stage nguồn thành công; nếu nguồn thất bại thì function không được gọi, lỗi được biểu diễn ở stage phụ thuộc.
- `thenCompose` dùng khi callback trả về một `CompletionStage` khác, giúp tránh nested future. Trong callback có thể trả `CompletableFuture.failedFuture(ex)` để đại diện cho một nhánh kiểm tra thất bại.
- `thenAccept` và `thenRun` cũng cần nguồn hoàn tất thành công để thực thi action bình thường.
- Nếu một callback được chạy rồi tự ném exception, stage của callback có thể hoàn tất bất thường ngay cả khi stage nguồn thành công.

Không giả định stage phụ thuộc giữ cùng **đối tượng wrapper** hoặc cùng stack trace trong mọi trường hợp. Dùng hợp đồng exception/cause để phân loại, không so sánh reference identity một cách tùy tiện.

## 8. Ví dụ thực hành: validate trước rồi trả failedFuture

Giả sử một service public luôn trả `CompletableFuture<User>`. Nếu đầu vào sai ngay lúc gọi, không cần tạo executor task vô ích chỉ để ném exception ở thread nền.

~~~java
// Trích đoạn Java 17; các kiểu User, repository do ứng dụng định nghĩa.
CompletableFuture<User> findUser(String id) {
    if (id == null || id.isBlank()) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("user id required"));
    }
    return repository.findAsync(id);
}
~~~

Nhánh invalid trả **một future đã thất bại**, vì vậy:

- Chữ ký vẫn là `CompletableFuture<User>` cho mọi đường đi.
- Người gọi có thể gắn `exceptionally`, `handle` hoặc sử dụng `get()`/`join()`.
- Không tạo thread mới chỉ để báo lỗi xác thực.
- Caller không thể kết luận lỗi sẽ được “ném tại dòng gọi service” nếu hợp đồng được thiết kế là always return future.

Cần phân biệt hai hợp đồng public khác nhau:

~~~java
// Hợp đồng 1: fail fast bằng exception đồng bộ
CompletableFuture<User> a(String id) {
    if (id == null) {
        throw new IllegalArgumentException("id null");
    }
    return repository.findAsync(id);
}

// Hợp đồng 2: đưa lỗi vào future
CompletableFuture<User> b(String id) {
    if (id == null) {
        return CompletableFuture.failedFuture(
                new IllegalArgumentException("id null"));
    }
    return repository.findAsync(id);
}
~~~

Đây là hai **đoạn minh họa không độc lập**, dùng giả định `User` và `repository` có sẵn. Ở hợp đồng 1, `try/catch` quanh `a(null)` có thể bắt lỗi ngay; ở hợp đồng 2, phép gọi `b(null)` trả future và lỗi chỉ hiển thị qua đường xử lý kết quả. Cả hai đều có thể đúng nếu tài liệu nhất quán; thay đổi giữa chúng trong một API đã phát hành có thể phá hành vi caller.

## 9. Ví dụ thực hành: callback hoàn tất một promise đã tạo

`completeExceptionally` phù hợp khi sự kiện trả về sau khi tạo future, ví dụ wrapper API callback, event listener hoặc một callback từ client I/O.

~~~java
// Trích đoạn trong một phương thức; LegacyClient và Callback
// là abstraction do ứng dụng định nghĩa.
CompletableFuture<String> fetchAsFuture(String key) {
    CompletableFuture<String> result = new CompletableFuture<>();

    legacyClient.fetch(key, new Callback() {
        @Override
        public void onSuccess(String value) {
            result.complete(value);
        }

        @Override
        public void onFailure(Throwable error) {
            result.completeExceptionally(error);
        }
    });

    return result;
}
~~~

Khi callback báo thất bại, có **một future đang chờ kết quả** nên gọi `completeExceptionally` đúng mục đích hơn tạo một `failedFuture` mới rồi bỏ promise cũ. Nếu callback có thể bị gọi nhiều lần hoặc xảy ra cạnh tranh success/failure, chỉ completion đầu tiên thắng; có thể kiểm tra boolean để chẩn đoán sự kiện trùng:

~~~java
boolean accepted = result.completeExceptionally(error);
if (!accepted) {
    // Kết quả đã được chốt; log/đo lỗi callback đến muộn nếu cần.
}
~~~

**Một lỗi thiết kế thường gặp:**

~~~java
// Sai về ý nghĩa: tạo future thất bại rồi bỏ rơi nó.
legacyClient.fetch(key, new Callback() {
    @Override
    public void onFailure(Throwable error) {
        CompletableFuture.failedFuture(error); // Kết quả bị bỏ đi.
    }
});
~~~

Đoạn này chỉ minh họa lỗi logic, không phải chương trình Java độc lập. Người đợi `result` vẫn có thể chờ mãi, vì future mới hoàn toàn không có quan hệ với `result`.

### Nếu việc đăng ký callback tự ném exception đồng bộ

Đoạn bridge thật cần xem xét trường hợp `legacyClient.fetch(...)` ném trước khi callback được đăng ký. Nếu muốn duy trì hợp đồng “luôn trả future”, có thể bắt các exception dự kiến rồi dùng `result.completeExceptionally(ex)` để bảo đảm future không treo. Không bắt `Throwable` quá rộng và không biến các lỗi runtime nghiêm trọng thành lỗi nghiệp vụ theo mặc định; xác định loại được phép chuyển đổi trong hợp đồng client.

## 10. completeExceptionally và cạnh tranh hoàn tất

Trong code nhiều luồng, kết quả của `completeExceptionally` có thể cạnh tranh với `complete`, `cancel`, callback timeout hoặc một nguồn kết quả khác.

~~~java
// Trích đoạn trong phương thức.
CompletableFuture<String> promise = new CompletableFuture<>();
// Thread A:
boolean aWon = promise.complete("value");
// Thread B:
boolean bWon = promise.completeExceptionally(new RuntimeException("error"));
~~~

Đây là **hai thao tác đặt vào hai luồng theo minh họa**, không phải hai luồng thực sự được tạo bởi đoạn code. Không thể dự đoán `aWon` và `bWon` từ riêng mã mà không có thứ tự đồng bộ hóa. Một trong hai completion thông thường được chấp nhận; completion còn lại trả `false`.

Bảo đảm này chỉ nói về **trạng thái kết quả của future**, không bảo đảm các side effect mà cả hai producer đã tạo sẽ được rollback. Ví dụ, hai nguồn cùng ghi database trước khi gọi `complete` có thể cùng gây tác dụng phụ dù future chỉ nhận một kết quả.

Những cách thực hành hữu ích:

1. Thiết lập một owner cụ thể có quyền hoàn tất future nếu có thể.
2. Kiểm tra boolean khi callback đến muộn, trùng hoặc trong trường hợp timeout/cancellation.
3. Định nghĩa chính sách đối với tác vụ đã chạy và tạo side effect trước khi future bị hủy.
4. Không dùng `isDone()` rồi mới `complete(...)` như một phép kiểm tra-ghi nguyên tử; giữa hai lời gọi có thể có thread khác hoàn tất. Hãy dùng ngay kết quả boolean của completion.
5. Giữ nguyên nhân lỗi `Throwable` có ý nghĩa, bao gồm `cause` và mã tác vụ trong logging.

## 11. Completion có thể chạy dependent actions ngay trên thread gọi

Cả `completeExceptionally` và `failedFuture` đều không tự lập lịch tác vụ. Tuy vậy, khi hoàn tất một future có các dependent stages, các action **không có hậu tố Async** được phép chạy trên luồng đang hoàn tất future hoặc luồng khác tham gia xử lý completion theo quy tắc của `CompletableFuture`.

Vì vậy không nên nghĩ `completeExceptionally` luôn là “gán một field rồi trở về ngay” theo thời gian chạy. Trong chương trình thực tế, quá trình completion có thể kích hoạt các dependent actions và kéo theo công việc quan sát hay phục hồi lỗi.

Phân biệt:

- `exceptionally(fn)` là stage không có Async trong Java 17; function có thể thực thi theo chính sách non-async.
- `thenApplyAsync(fn, executor)` sử dụng executor được cung cấp cho action tương ứng.
- `whenCompleteAsync(action, executor)` cũng lập lịch phần callback qua executor.
- Nếu lỗi đã có sẵn trong `failedFuture`, một stage non-async gắn vào sau đó có thể được thực thi khi đăng ký stage, không nhất thiết trong một worker nền.

**Lưu ý:** callback khôi phục hoặc ghi log có thể ném lỗi. Future gốc đã hoàn tất bất thường không tự trở lại trạng thái pending; lỗi callback thường được phản ánh ở stage phụ thuộc. Tránh đặt side effect khó rollback trong callback nếu chưa định nghĩa rõ thứ tự và quyền sở hữu.

## 12. failedFuture khác gì failedStage và completedFuture?

Các factory tiện dụng liên quan:

| Factory | Kiểu trả về | Trạng thái ban đầu | Mục đích |
|---|---|---|---|
| `CompletableFuture.completedFuture(value)` | `CompletableFuture<U>` | Thành công với `value` | Giá trị sẵn có |
| `CompletableFuture.failedFuture(ex)` | `CompletableFuture<U>` | Bất thường với `ex` | Cần trả CompletableFuture đã lỗi |
| `CompletableFuture.completedStage(value)` | `CompletionStage<U>` | Thành công | Trả view kiểu CompletionStage |
| `CompletableFuture.failedStage(ex)` | `CompletionStage<U>` | Bất thường | API chỉ muốn công bố CompletionStage |

`failedFuture` và `failedStage` có từ Java 9. Điểm quan trọng khi thiết kế API là **kiểu trả về**: `CompletionStage<T>` bộc lộ các phép phối hợp stage, còn `CompletableFuture<T>` bộc lộ thêm những thao tác điều khiển completion/cancellation.

Nếu một API chỉ muốn caller nối stage mà không chủ động hoàn tất promise nội bộ, cân nhắc public contract `CompletionStage<T>`. Tuy vậy chỉ đổi chữ ký interface không tự là biện pháp bảo mật hay immutable guarantee; vẫn cần giữ quyền sở hữu dữ liệu và kiểm soát implementation.

**Đừng nhầm `failedFuture` với `supplyAsync(() -> { throw ex; })`.** Factory cho kết quả lỗi ngay, không tiêu tốn một nhiệm vụ trên executor. `supplyAsync` biểu diễn việc chạy một computation theo executor đã chọn, và lỗi phụ thuộc thời điểm computation thực thi.

## 13. Cancellation và timeout khác exceptional failure thế nào?

Cancellation trong `CompletableFuture` được xem là một dạng exceptional completion, nhưng mang ý nghĩa riêng:

~~~java
// Đoạn minh họa trong một phương thức.
CompletableFuture<String> task = new CompletableFuture<>();
boolean cancelled = task.cancel(true);
System.out.println(task.isCancelled()); // true
System.out.println(task.isCompletedExceptionally()); // true
~~~

Đối với `CompletableFuture`, tham số `mayInterruptIfRunning` của `cancel(boolean)` **không được dùng để điều khiển xử lý**, vì các phương thức của CompletableFuture không trực tiếp điều khiển một phép tính đang chạy. Vì thế **không** suy ra `cancel(true)` tự dừng thread đang làm việc hoặc hoàn tác giao dịch đã diễn ra.

Các thao tác timeout như `orTimeout(...)` làm future chưa hoàn tất trở thành exceptional completion với `TimeoutException` khi quá hạn; `completeOnTimeout(...)` cố hoàn tất thành công với một giá trị fallback. Chúng có thể cạnh tranh với completion bình thường, nên không kết luận kết quả chỉ từ việc “đã gọi timeout”. Timeout cũng không chứng minh việc I/O bên ngoài đã dừng hoặc chưa gây side effect.

Không dùng `failedFuture(new TimeoutException(...))` thay thế toàn bộ chức năng scheduling của timeout: nó chỉ tạo **kết quả lỗi đã biết ngay bây giờ**. Nếu cần hết hạn sau một khoảng thời gian, chọn API timeout thích hợp.

## 14. Bắt đúng loại lỗi, giữ cause và không bỏ quên future

### Kiểm soát lỗi

Hãy chọn một error type ổn định theo ngữ nghĩa:

- `IllegalArgumentException` khi đầu vào của API không hợp lệ.
- Exception miền nghiệp vụ nếu client cần quyết định retry, chọn fallback hoặc hiện thông điệp cụ thể.
- `IOException` hoặc loại khác được bảo toàn làm cause khi lỗi xảy ra từ hệ thống ngoài.
- Tránh dùng một `RuntimeException` chung cho mọi tình huống vì làm mất khả năng phân loại.

`failedFuture` nhận `Throwable` trực tiếp; không cần gói mọi checked exception vào `RuntimeException` chỉ để chuyển nó qua Future. Khi muốn thay đổi kiểu exception công khai, có thể dùng wrapper phù hợp với `cause`:

~~~java
Throwable root = new java.io.IOException("connection lost");
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("fetch failed", root));
~~~

Đoạn mã là một ví dụ trong phương thức; khi `get()`/`join()`, người gọi có thể truy lại chuỗi nguyên nhân.

### Theo dõi lỗi

Nếu tạo một future đã lỗi rồi bỏ nó mà không có caller, stage hoặc cơ chế logging nào quan sát, lỗi có thể bị bỏ qua ở cấp hệ thống. Không mặc định `failedFuture` hoặc `completeExceptionally` sẽ ghi stack trace ra stderr.

Khi phát triển thư viện, tài liệu nên trả lời:

1. Phương thức có thể **ném lỗi đồng bộ** ngay lúc gọi hay luôn trả future?
2. Lỗi đầu vào được đưa vào `failedFuture` hay thrown trực tiếp?
3. Lỗi computation đến từ stage nào, được wrap ra sao?
4. Caller nên dùng `get()`, `join()`, `handle` hoặc `exceptionally`?
5. Task đã chạy có dừng khi future bị hủy hoặc timeout không?
6. Khi lỗi xảy ra, trạng thái dữ liệu đã thay đổi đến mức nào?

## 15. Những lỗi lập trình thường gặp

1. **Dùng `completeExceptionally` như `throw`:** gọi completion không ném cause trực tiếp vào code phía sau; nếu muốn dừng xử lý, phải `return`/`throw` hoặc có cơ chế điều khiển riêng.
2. **Bỏ qua kết quả boolean:** callback lỗi đến muộn bị từ chối nhưng ứng dụng vẫn tưởng đã thay đổi kết quả cho caller.
3. **Gọi `completeExceptionally` trên một future mới rồi trả future khác:** người đợi future ban đầu có thể treo.
4. **Tạo `failedFuture` rồi không return/gắn stage:** future lỗi vừa tạo không liên quan đến pipeline thực tế.
5. **Cho rằng `failedFuture` chạy bất đồng bộ:** nó chỉ là completed future; không tạo worker.
6. **Cho rằng `completeExceptionally` làm task đang chạy dừng:** completion của kết quả khác với cancellation tác vụ thực.
7. **Dùng `exceptionally` để log mà vô tình biến lỗi thành thành công:** giá trị trả về callback là giá trị thành công của stage phục hồi.
8. **Dùng `whenComplete` để phục hồi:** nó chủ yếu quan sát completion, không mặc nhiên thay thế lỗi nguồn bằng thành công.
9. **Quên xử lý `ExecutionException.getCause()`:** mất kiểu lỗi nguyên nhân, nhầm lỗi task với interrupt của thread đang chờ.
10. **Coi mọi lỗi của `join()` là `CompletionException`:** future bị hủy có thể ném `CancellationException`.
11. **Dùng `isDone()` như guard chống race:** kiểm tra rồi gọi complete không nguyên tử; chỉ completion thực tế quyết định kết quả.
12. **Đổi API từ throw đồng bộ sang failedFuture mà không thông báo:** caller có `try/catch` cũ có thể không còn xử lý lỗi như dự kiến.
13. **Cho rằng lỗi trong future tự rollback dữ liệu:** exceptional completion chỉ là trạng thái kết quả, không phải transaction.
14. **Đặt `null` làm Throwable:** cả `completeExceptionally(null)` và `failedFuture(null)` đều không hợp lệ.

## 16. Kiểm thử đúng exceptional completion

Các test nên quan sát cả **trạng thái** lẫn **kênh báo lỗi**:

| Kịch bản | Điều phải xác minh |
|---|---|
| Future đang pending + `completeExceptionally(ex)` | Trả `true`; `isDone` và `isCompletedExceptionally` đúng |
| Gọi `complete(value)` sau lỗi | Trả `false`, lỗi ban đầu không bị ghi đè |
| Future đã thành công + `completeExceptionally(ex)` | Trả `false`; kết quả thành công vẫn giữ |
| `failedFuture(ex)` | Future nhận ngay trạng thái hoàn tất bất thường, không cần executor |
| `get()` trên future lỗi | `ExecutionException.getCause()` có đúng loại và nguyên nhân |
| `join()` trên future lỗi | `CompletionException` có `cause` thích hợp |
| `thenApply` trên nguồn lỗi | Transformation không chạy; dependent stage thất bại |
| `exceptionally` / `handle` | Stage phục hồi có giá trị đúng; nguồn vẫn ở trạng thái ban đầu |
| `whenComplete` | Quan sát lỗi nhưng không tự thay nguồn thành thành công |
| Hai producer completion tranh chấp | Chỉ một completion thường được chấp nhận; không assume thứ tự |
| Future bị `cancel` | Phân biệt cancellation với failed computation |
| Timeout và completion cạnh tranh | Chỉ một kết quả thắng; task/side effect bên ngoài được kiểm tra độc lập |

Ví dụ JUnit 5 minh họa (đoạn độc lập cần dependency JUnit ngoài JDK):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.*;

class ExceptionalFutureTest {
    @org.junit.jupiter.api.Test
    void firstCompletionWins() {
        CompletableFuture<String> future = new CompletableFuture<>();
        IllegalStateException cause = new IllegalStateException("failed");

        assertTrue(future.completeExceptionally(cause));
        assertFalse(future.complete("late"));
        assertTrue(future.isCompletedExceptionally());

        CompletionException thrown =
                assertThrows(CompletionException.class, future::join);
        assertSame(cause, thrown.getCause());
    }

    @org.junit.jupiter.api.Test
    void failedFutureCanBeRecovered() {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));
        assertTrue(failed.isCompletedExceptionally());
        assertEquals("fallback", failed.exceptionally(ex -> "fallback").join());
        assertTrue(failed.isCompletedExceptionally());
    }
}
~~~

Đây là **một lớp kiểm thử** được đặt trong cấu trúc dự án hỗ trợ JUnit 5, không chạy chỉ bằng `javac` JDK thuần nếu thiếu JUnit. Việc kiểm tra `assertSame(cause, thrown.getCause())` ở trường hợp completion trực tiếp giúp phát hiện wrapper/cause không đúng, còn test phục hồi bảo đảm nguồn lỗi không bị chuyển thành thành công.

Với concurrency test, dùng `CountDownLatch` hoặc cơ chế điều phối thích hợp để tạo tranh chấp; không đoán thứ tự bằng `Thread.sleep` và không coi một lần chạy thành công là bằng chứng loại bỏ race.

## 17. Checklist lựa chọn API trong code thật

- **Đã có một future đang chờ callback/kết quả chưa?** Có → dùng `completeExceptionally(ex)` để hoàn tất **future đó** khi thất bại.
- **Chưa có future và đã biết lỗi ngay?** Có → dùng `CompletableFuture.failedFuture(ex)` làm return value.
- **Caller phải nhận nguyên nhân?** Bảo đảm future/stage được tiêu thụ, giữ `cause` và loại lỗi rõ nghĩa.
- **Cần fallback?** Dùng `exceptionally` hoặc `handle`, phân biệt stage mới với source.
- **Chỉ cần log?** Dùng `whenComplete`, nhưng phải giữ nguồn lỗi đi tiếp nếu hệ thống cần xử lý.
- **Có nhiều producer cạnh tranh?** Quan sát giá trị boolean của completion, xác định owner, tránh side effect không phối hợp.
- **Có timeout/hủy?** Dùng hợp đồng timeout/cancel thích hợp; không đánh đồng trạng thái future với việc tác vụ thật đã dừng.
- **API public đang đổi cách báo lỗi?** Kiểm tra tương thích với caller đang dùng `try/catch` đồng bộ và caller đang đọc future.
- **Đã kiểm tra bất biến dữ liệu sau lỗi chưa?** Không dùng completion như cơ chế rollback.

## 18. Ghi nhớ

**`completeExceptionally(ex)`** hoàn tất bất thường **một CompletableFuture đã tồn tại** nếu future đó chưa được hoàn tất; nó trả boolean để cho biết lần gọi có thắng cuộc hay không. **`CompletableFuture.failedFuture(ex)`** tạo **một CompletableFuture mới đã thất bại ngay**, thích hợp cho đường trả về lỗi đã xác định sẵn.

Cả hai mô hình hóa thất bại ở **kết quả bất đồng bộ**, không tự ném nguyên nhân trên luồng tạo future, không khởi chạy task và không rollback tác dụng phụ. Người tiêu thụ nhận nguyên nhân qua `get()`/`join()` hoặc dependent stages, có thể phục hồi có chủ đích bằng `exceptionally`/`handle`. Thiết kế đúng phải giữ kênh lỗi, trạng thái completion, chính sách cancellation và trạng thái dữ liệu nhất quán với hợp đồng API.

### Tài liệu tham khảo

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CancellationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html)
