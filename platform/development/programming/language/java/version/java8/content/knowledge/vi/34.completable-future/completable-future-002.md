# CompletableFuture: tạo future hoàn thành sẵn hoặc hoàn thành thủ công trong Java

## 1. Hiểu đúng hai cách tạo kết quả bất đồng bộ

`CompletableFuture<T>` (thuộc `java.util.concurrent`, có từ **Java 8** và vẫn được sử dụng trên JDK hiện đại) vừa thực hiện hợp đồng `Future<T>`, vừa triển khai `CompletionStage<T>` để xâu chuỗi các tác vụ phụ thuộc vào kết quả. Khác một `Future` chỉ để chờ kết quả, `CompletableFuture` có thể được **hoàn thành trực tiếp** từ code bằng `complete` hoặc `completeExceptionally`.

Hai tình huống cốt lõi:

1. **Kết quả đã biết sẵn:** tạo một `CompletableFuture` **đã hoàn thành** ngay lập tức bằng `CompletableFuture.completedFuture(value)`. Không cần khởi động một thread hay executor chỉ để trả một giá trị có sẵn.
2. **Kết quả chưa biết:** tạo `new CompletableFuture<T>()` ở trạng thái **chưa hoàn thành** (pending), rồi cho một nhà sản xuất kết quả gọi `complete(value)` khi thành công hoặc `completeExceptionally(error)` khi thất bại. Phương thức hoàn thành có thể được gọi bởi callback mạng, thread khác, handler sự kiện hoặc đoạn code bình thường.

```java
CompletableFuture<String> ready =
    CompletableFuture.completedFuture("OK");

CompletableFuture<String> waiting = new CompletableFuture<>();

// Khi dữ liệu thật đã xuất hiện:
waiting.complete("DONE");
```

Đây là **snippet** đặt trong method với `import java.util.concurrent.CompletableFuture;`. Cả hai biến cuối cùng đều có kết quả, nhưng **thời điểm và quyền kích hoạt hoàn thành** khác nhau.

`CompletableFuture` là một **bộ chứa kết quả tương lai có trạng thái**, không phải “một thread”. Việc tạo nó không đồng nghĩa phép tính đã được chạy ngầm. Muốn khởi động một tác vụ trên executor, dùng `supplyAsync`/`runAsync` hoặc thiết kế producer khác, rồi liên kết kết quả với future. Không thay `completedFuture` bằng `supplyAsync(() -> value)` khi đã có sẵn `value` chỉ vì API mang chữ “async”.

### 1.1. Bảng chọn API nhanh

| Nhu cầu | API | Có kết quả ngay lúc tạo? | Có tự khởi chạy công việc? |
| --- | --- | --- | --- |
| Đã có giá trị `T` | `CompletableFuture.completedFuture(value)` | Có, thành công | Không |
| Đã có `null` hợp lệ | `CompletableFuture.completedFuture(null)` | Có, thành công với `null` | Không |
| Có kết quả chưa biết | `new CompletableFuture<T>()` | Chưa | Không |
| Cấp giá trị cho future pending | `future.complete(value)` | Hoàn thành nếu chưa bị hoàn thành trước | Không; chỉ công bố kết quả |
| Cấp lỗi cho future pending | `future.completeExceptionally(error)` | Hoàn thành bất thường nếu chưa bị hoàn thành trước | Không |
| Muốn chạy supplier trên executor | `CompletableFuture.supplyAsync(supplier, executor)` | Sau khi tác vụ chạy xong | Có, thông qua executor |
| Muốn chạy tác vụ không trả dữ liệu | `CompletableFuture.runAsync(runnable, executor)` | Sau khi tác vụ chạy xong | Có, thông qua executor |
| Đã có lỗi, muốn future thất bại ngay | `CompletableFuture.failedFuture(error)` | Có, bất thường | Không; **chỉ từ Java 9** |
| Đã có giá trị, muốn chỉ lộ `CompletionStage` | `CompletableFuture.completedStage(value)` | Có | Không; **chỉ từ Java 9** |

**Lưu ý phiên bản:** `completedFuture`, `new CompletableFuture`, `complete`, `completeExceptionally`, `supplyAsync` và `runAsync` có từ Java 8. `failedFuture`, `failedStage`, `completedStage` và `completeAsync` là bổ sung sau đó, **từ Java 9**. Đây là API hiện đại và không lỗi thời, nhưng code yêu cầu `javac --release 8` không được gọi chúng.

## 2. `completedFuture(value)`: kết quả đã biết, không cần lập lịch

Khai báo:

```java
public static <U> CompletableFuture<U> completedFuture(U value)
```

Phương thức static tạo một `CompletableFuture<U>` **đã hoàn thành bình thường** với giá trị `value`. Ngay sau khi tạo:

- `isDone()` trả `true`.
- `join()` trả giá trị ngay, không phải đợi producer khác.
- `getNow(fallback)` trả **giá trị thật**, không dùng fallback.
- Những continuation phụ thuộc như `thenApply` có thể chạy khi được đăng ký hoặc qua thread thực hiện completion theo chính sách `CompletableFuture`; **không có cam kết mỗi continuation luôn được đưa lên một worker thread riêng**.
- Một lời gọi `complete(other)` thông thường sau đó trả `false` vì future đã hoàn thành.

```java
CompletableFuture<Integer> constant =
    CompletableFuture.completedFuture(42);

System.out.println(constant.isDone()); // true
System.out.println(constant.join());   // 42

CompletableFuture<Integer> doubled =
    constant.thenApply(n -> n * 2);
// doubled.join() == 84

boolean replaced = constant.complete(100);
// false; constant.join() vẫn là 42
```

Đây là snippet trong `main` hoặc method; cần import `CompletableFuture`. `completedFuture` đặc biệt phù hợp với đường đi dữ liệu được cache, cấu hình tĩnh hoặc một nhánh không cần I/O mà API công khai vẫn trả `CompletionStage<T>`.

### 2.1. Ví dụ về cache hit và cache miss

Giả sử service có cache và trả `CompletionStage<Product>`:

```java
CompletionStage<Product> loadProduct(String id) {
    Product cached = cache.get(id);
    if (cached != null) {
        return CompletableFuture.completedFuture(cached);
    }
    return remoteClient.loadProductAsync(id);
}
```

Đây là **snippet kiến trúc**, cần có các kiểu `Product`, `cache`, `remoteClient` do ứng dụng tự định nghĩa. Nó minh họa việc giữ một **kiểu trả về thống nhất** cho nhánh nhanh và nhánh bất đồng bộ; không có lý do phải tạo thread cho cache hit.

Cẩn thận nếu `null` cũng là giá trị cache hợp lệ: `cache.get(id) == null` có thể biểu thị “không có khóa” hoặc “giá trị null”, tùy collection. Khi đó cần thiết kế API cache phù hợp (ví dụ `Optional` hoặc `containsKey` nếu cho phép null) thay vì mặc định null là miss.

### 2.2. `completedFuture(null)` hoàn toàn hợp lệ

`CompletableFuture` cho phép **kết quả hoàn thành bình thường là `null`**:

```java
CompletableFuture<String> completedNull =
    CompletableFuture.completedFuture(null);

completedNull.isDone();          // true
completedNull.join();            // null
completedNull.getNow("DEFAULT"); // null, KHÔNG phải "DEFAULT"
```

`getNow(fallback)` chỉ trả fallback **nếu future chưa hoàn thành**. Nó không dùng fallback khi future đã hoàn thành với `null`. Đây là lý do không nên coi `null` và trạng thái `pending` là cùng nghĩa. Đặc biệt với `CompletableFuture<Void>`, hoàn thành bình thường thường dùng `complete(null)`, vì kết quả không có payload.

Nếu kết quả có thể thiếu, hãy định nghĩa rõ `null`, `Optional<T>` hoặc kiểu kết quả nghiệp vụ, thay vì khiến người gọi phải đoán.

### 2.3. `completedFuture` không tự nhân bản hoặc đóng băng giá trị

Giá trị `T` có thể là đối tượng mutable, ví dụ `List<String>` hoặc một DTO:

```java
List<String> names = new ArrayList<>();
names.add("An");

CompletableFuture<List<String>> result =
    CompletableFuture.completedFuture(names);

// result.join() nhận tham chiếu tới danh sách đã truyền vào.
```

Đây là snippet (cần import `List`, `ArrayList`, `CompletableFuture`). `CompletableFuture` bảo đảm cơ chế công bố trạng thái hoàn thành theo hợp đồng đồng thời, nhưng **không tự biến `names` thành immutable**, cũng không deep-copy các phần tử. Nếu producer tiếp tục sửa `names` từ nhiều thread, vẫn cần quy tắc đồng bộ hoặc snapshot bất biến.

## 3. `new CompletableFuture<T>()`: tạo promise chưa có kết quả

`new CompletableFuture<>()` tạo một future **chưa hoàn thành**. Các continuation có thể được đăng ký ngay, nhưng chưa thể nhận giá trị cho đến khi có bên gọi một thao tác hoàn thành.

```java
CompletableFuture<String> promise = new CompletableFuture<>();

boolean before = promise.isDone(); // false
String fallback = promise.getNow("WAITING"); // "WAITING"

CompletableFuture<Integer> lengthStage =
    promise.thenApply(String::length);

// Chưa có dữ liệu: lengthStage chưa thể tính ra chiều dài.
boolean dependencyBefore = lengthStage.isDone(); // false

boolean first = promise.complete("JAVA");  // true
boolean second = promise.complete("OTHER"); // false

String finalValue = promise.join();         // "JAVA"
int length = lengthStage.join();            // 4
```

Đoạn code minh họa dùng `CompletableFuture`. Nó thể hiện ba đặc điểm quan trọng:

1. `getNow` **không chờ** và **không hoàn thành future**; nó chỉ đọc trạng thái tại thời điểm gọi.
2. `thenApply` tạo **stage phụ thuộc** để biến đổi kết quả khi nguồn hoàn thành; nó không tự làm nguồn hoàn thành.
3. `complete` đầu tiên có hiệu lực, `complete` tiếp theo không thay thế kết quả bình thường đã chốt.

### 3.1. Vì sao cần “hoàn thành thủ công”?

Một ví dụ phổ biến là **bọc API callback** bằng `CompletionStage`. API cũ gọi callback sau khi đọc thiết bị, nhận phản hồi mạng hoặc được cấp quyền. Code mới muốn dùng các toán tử `thenApply`, `thenCompose`, `exceptionally` thay vì truyền callback nối tiếp.

Sơ đồ:

```text
Service gọi hàm bất đồng bộ
            |
            v
CompletableFuture<T> PENDING --------> Trả CompletionStage<T> cho caller
            |                                     |
            |                                     +-- thenApply(...)
            |                                     +-- exceptionally(...)
            |
Bên thứ ba gọi callback(value, error)
            |
      +-----+------------------+
      |                        |
   error == null          error != null
      |                        |
  complete(value)         completeExceptionally(error)
      |                        |
   SUCCESS                   FAILURE
      |                        |
      +---- các dependent stages được kích hoạt ---+
```

Mô hình này đóng vai trò *promise* (producer có quyền quyết định kết quả, consumer có khả năng chờ/xâu chuỗi). Việc gọi constructor **không phải** là khởi động một tác vụ. Nếu không producer nào gọi completion, future có thể **pending vô thời hạn**.

## 4. `complete(value)`: hoàn thành bình thường theo nguyên tắc thắng trước

Chữ ký:

```java
boolean complete(T value)
```

Nếu future chưa hoàn thành, `complete` đặt giá trị và trả **`true`**. Nếu đã hoàn thành trước đó (thành công, lỗi hoặc hủy), nó trả **`false`** và không thay thế kết quả đã được quyết định.

```java
CompletableFuture<String> answer = new CompletableFuture<>();

boolean first = answer.complete("A");   // true
boolean second = answer.complete("B");  // false

answer.join(); // "A"
```

Một future có thể có nhiều bên gọi `complete` gần như đồng thời (ví dụ callback thành công và timeout cùng đến). **Chỉ một bên thắng trong việc chốt trạng thái**; không nên dựa vào thread nào chắc chắn thắng nếu không điều khiển thứ tự sự kiện.

### 4.1. Hoàn thành bằng `null` không phải hoàn thành lỗi

```java
CompletableFuture<Void> signal = new CompletableFuture<>();

CompletableFuture<String> after =
    signal.thenApply(ignored -> "FINISHED");

boolean marked = signal.complete(null); // true
String text = after.join();               // "FINISHED"
```

Với `CompletableFuture<Void>`, `complete(null)` là cách biểu thị thành công **không trả payload**, ví dụ xử lý xong thao tác ghi, kết thúc một sự kiện hoặc nhận ACK. Không dùng `completeExceptionally(null)`: tham số lỗi phải là một đối tượng `Throwable` không null.

### 4.2. `complete` chỉ chốt future, không đảm bảo side effect đã dừng

Nếu có một tác vụ tính toán đang chạy song song và một thread khác gọi `complete("fallback")` trước, future có thể nhận fallback. Điều đó **không tự hủy phép tính đang chạy**. Producer vẫn phải quản lý vòng đời, hủy hoặc bỏ qua dữ liệu đến muộn theo kiến trúc riêng.

Ví dụ tình huống:

```text
T1: Bắt đầu request từ server
T2: Timeout policy quyết định dùng fallback; complete("cached")
T3: Network callback trở về; complete("remote") -> false

Future giữ "cached", nhưng I/O có thể đã chạy tới T3.
```

Đây là **timeline minh họa**, không phải thứ tự được Java bảo đảm. Trong trường hợp ngược lại, callback network thắng trước timeout thì callback timeout phải nhận `false` từ thao tác hoàn thành và không được ghi đè kết quả.

### 4.3. Chỉ một completion thành công, nhưng callback có thể có side effect riêng

Các continuation `thenApply`, `thenAccept` hoặc `whenComplete` có thể thực hiện logging hoặc cập nhật trạng thái ngoài future. Quy tắc first-wins chỉ bảo đảm **trạng thái hoàn thành của future**, không tự tạo transaction với database hay bảo đảm side effect bên ngoài chạy đúng một lần khi có retries khác.

Đối với nghiệp vụ như thanh toán, phát voucher, gửi email: **không dùng `complete(...) == true` thay thế idempotency key và transaction** của hệ thống. Việc future đã chốt không đồng nghĩa các hệ thống ngoài đã được xử lý đúng một lần.

## 5. `completeExceptionally(Throwable)`: thông báo thất bại cho consumer

Khi producer gặp lỗi, không nên im lặng và để promise pending. Dùng:

```java
CompletableFuture<String> data = new CompletableFuture<>();

boolean success = data.completeExceptionally(
    new IllegalStateException("Remote service unavailable"));
// success == true

boolean anotherCompletion = data.complete("OK");
// false; lỗi đã chốt
```

`completeExceptionally` là **hoàn thành terminal bất thường**: `isDone()` trả `true`, `isCompletedExceptionally()` trả `true`. Nó **không** đồng nghĩa future cứ ở trạng thái “chưa xong” vì có lỗi. Future đã có kết quả cuối cùng, nhưng kết quả đó là **failure**.

### 5.1. Future lỗi khác với future thành công chứa một `Throwable`

Hai cách viết này khác nhau:

```java
CompletableFuture<Throwable> errorAsValue =
    CompletableFuture.completedFuture(
        new IllegalArgumentException("bad"));
// Thành công bình thường; giá trị T là một Throwable.

CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(
    new IllegalArgumentException("bad"));
// Thất bại bất thường; join/get báo lỗi.
```

Để biểu diễn “kết quả nghiệp vụ là lỗi nhưng API vẫn thành công”, có thể dùng một sealed result model/`Either`/kiểu domain tùy ngữ cảnh; nhưng đó là thiết kế khác với **exceptional completion** của `CompletableFuture`.

### 5.2. Khôi phục bằng `exceptionally` và `handle`

`exceptionally` tạo **một stage mới** để chuyển failure thành một giá trị fallback. Nó không chữa trạng thái lỗi của future nguồn:

```java
CompletableFuture<Integer> original = new CompletableFuture<>();

CompletableFuture<Integer> recovered =
    original.exceptionally(error -> -1);

original.completeExceptionally(
    new IllegalArgumentException("invalid"));

boolean sourceFailed = original.isCompletedExceptionally();
// true

int value = recovered.join(); // -1
```

`handle((value,error) -> ...)` chạy logic cả khi thành công và thất bại, có thể trả kiểu kết quả mới. `whenComplete((value,error) -> ...)` thích hợp quan sát/log hành vi; theo thiết kế nó **giữ trạng thái kết quả của nguồn** nếu callback thành công, không phải công cụ chính để thay lỗi bằng fallback.

**Không coi `exceptionally` là “làm cho future nguồn không còn lỗi”**. Nó tạo một dependent stage. Nếu caller vẫn `join` original, caller vẫn nhận exception.

### 5.3. `join()` và `get()` báo lỗi theo các dạng khác nhau

Khi future hoàn thành bằng `completeExceptionally(new IllegalArgumentException(...))`:

- `join()` ném unchecked **`CompletionException`** bọc nguyên nhân (thường trong `getCause()`).
- `get()` ném checked **`ExecutionException`** bọc nguyên nhân; ngoài ra còn có thể ném `InterruptedException` trong lúc chờ.
- `get(timeout, unit)` còn có thể ném `TimeoutException` **khi thời gian chờ hết nhưng future vẫn chưa hoàn thành**.
- `getNow(fallback)` trên future đã kết thúc bằng exception **không trả fallback**, mà báo ngoại lệ theo hợp đồng của future.

```java
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(new IllegalStateException("broken"));

try {
    failed.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    // cause thường là IllegalStateException("broken")
}
```

Đây là snippet trong method (cần import `CompletionException`, `CompletableFuture`). Đừng gửi nguyên `ex.getMessage()` tới người dùng cuối nếu thông báo chứa dữ liệu hệ thống/remote stack trace.

## 6. Tạo future thất bại sẵn: khác biệt Java 8 và Java 9+

Trong Java 8 không có factory static `failedFuture(Throwable)`. Mẫu chuẩn là:

```java
static <T> CompletableFuture<T> failedFutureJava8(Throwable error) {
    CompletableFuture<T> promise = new CompletableFuture<>();
    promise.completeExceptionally(error);
    return promise;
}
```

Đây là **method snippet** cần đặt trong class; có thể dùng lại khi ứng dụng phải biên dịch với API Java 8. Khi đã biết lỗi từ bước validation đồng bộ nhưng API yêu cầu trả future, cách này giúp **trả về một future đã thất bại**, thay vì `throw` ở đầu phương thức nếu contract là “mọi lỗi được trả dưới dạng CompletionStage”.

Từ **Java 9**, Java đã có trực tiếp:

```java
CompletableFuture<String> failed =
    CompletableFuture.failedFuture(
        new IllegalArgumentException("invalid input"));

CompletionStage<String> failedOnlyStage =
    CompletableFuture.failedStage(
        new IllegalStateException("unavailable"));
```

Đây là snippet **Java 9+**, không được chèn vào ví dụ `javac --release 8`. Hai phương thức đều tạo kết quả **đã hoàn thành bất thường**, không tự lên lịch chạy code nền.

Cũng từ Java 9 có `completedStage(value)` cho trường hợp thành công sẵn nhưng chỉ cung cấp bề mặt `CompletionStage`. Ở Java 8, một cách diễn đạt API là **trả kiểu `CompletionStage<T>`** từ một `CompletableFuture.completedFuture(value)`, dù giá trị thực vẫn có thể là CompletableFuture nếu consumer cố cast; đây là **giới hạn API thiết kế**, không phải một rào bảo mật cho quyền complete.

### 6.1. Bảng phiên bản quan trọng

| API | Có từ phiên bản | Ý nghĩa |
| --- | --- | --- |
| `CompletableFuture.completedFuture` | Java 8 | Hoàn thành sẵn thành công |
| `new CompletableFuture<>()` | Java 8 | Tạo pending promise |
| `complete`, `completeExceptionally` | Java 8 | Hoàn thành thủ công |
| `supplyAsync`, `runAsync` | Java 8 | Khởi chạy tác vụ để tạo future |
| `thenApply`, `thenCompose`, `exceptionally`, `handle` | Java 8 | Xâu chuỗi và khôi phục |
| `get`, `join`, `getNow` | Java 8 | Truy xuất/đợi kết quả |
| `completedStage`, `failedFuture`, `failedStage` | Java 9 | Factory bổ sung |
| `completeAsync` | Java 9 | Lên lịch supplier để hoàn thành **future đang có** |
| `orTimeout`, `completeOnTimeout` | Java 9 | Hoàn thành khi quá hạn nếu trước đó chưa xong |
| `delayedExecutor` | Java 9 | Trì hoãn việc gửi task tới executor |
| `Future.resultNow`/`exceptionNow` | Java 19 | Truy vấn trạng thái/result theo hợp đồng Future mới |

Không đánh đồng “API bổ sung sau Java 8” với “API lỗi thời”: các API Java 9+ này **vẫn áp dụng hiện nay** nhưng đòi mức phiên bản phù hợp.

## 7. Xâu chuỗi future trước và sau khi hoàn thành

Một lợi ích của `CompletableFuture` là consumer có thể **đăng ký việc cần làm ngay cả khi producer chưa có kết quả**.

```java
CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<Integer> lengths =
    pending.thenApply(String::length);

CompletableFuture<String> labels =
    lengths.thenApply(n -> "length=" + n);

// Đăng ký xong rồi mới hoàn thành nguồn.
pending.complete("JAVA");

// lengths.join() == 4
// labels.join()  == "length=4"
```

Có ba stage: nguồn `pending`, stage độ dài và stage nhãn. Một stage phụ thuộc chỉ có thể tính sau khi stage trước có kết quả phù hợp; failure thường được lan truyền tới dependent stage nếu không có khôi phục.

Khi nguồn **đã hoàn thành**, đăng ký `thenApply` vẫn hợp lệ:

```java
CompletableFuture<String> ready =
    CompletableFuture.completedFuture("java");

CompletableFuture<String> upper =
    ready.thenApply(String::toUpperCase);

// upper.join() == "JAVA"
```

Code là snippet; nếu dùng locale-sensitive transformation trong nghiệp vụ, nên chọn `String.toUpperCase(Locale.ROOT)` hoặc locale phù hợp. `thenApply` không tự “bắt buộc tạo thread”; mặc định **non-async**.

### 7.1. `thenApply` khác `thenCompose`

Nếu callback biến giá trị sang **một giá trị thường**, dùng `thenApply`:

```java
CompletableFuture<Integer> len =
    CompletableFuture.completedFuture("abc")
        .thenApply(String::length);
// CompletableFuture<Integer>
```

Nếu callback **trả về một future/stage khác**, dùng `thenCompose` để nối phẳng:

```java
CompletableFuture<String> chain =
    CompletableFuture.completedFuture("a")
        .thenCompose(s ->
            CompletableFuture.completedFuture(s + "b"));
// CompletableFuture<String>, không phải Future<Future<String>>
```

Mẫu `thenCompose` đặc biệt quan trọng khi producer thủ công chỉ bắt đầu ở callback của một nguồn khác. Không tạo future lồng nhau rồi buộc caller gọi `join().join()` nếu thực chất cần chuỗi công việc.

### 7.2. Quan sát hoàn thành không giống biến đổi kết quả

- `thenApply(Function<T,U>)`: xử lý **thành công** rồi trả `U`.
- `thenAccept(Consumer<T>)`: làm việc với kết quả thành công, trả `CompletableFuture<Void>`.
- `thenRun(Runnable)`: chạy sau khi thành công nhưng không nhận kết quả.
- `whenComplete(BiConsumer<T,Throwable>)`: quan sát thành công hoặc thất bại, stage trả về cố giữ kết quả/lỗi nguồn.
- `handle(BiFunction<T,Throwable,U>)`: xử lý cả thành công và thất bại, tạo giá trị `U`.
- `exceptionally(Function<Throwable,T>)`: khôi phục riêng nhánh thất bại bằng giá trị `T`.

Nếu producer gọi `completeExceptionally`, những continuation **chỉ dành cho thành công** sẽ không chạy logic thành công; dependent tương ứng thường hoàn thành bất thường. Nên đặt error handler ở stage cuối cần phục hồi và xác định nơi log lỗi để tránh log lặp nhiều lần.

## 8. Đồng thời: nhiều producer cùng muốn chốt một future

`CompletableFuture` bảo đảm chỉ **một trong các tác nhân cạnh tranh** `complete`, `completeExceptionally` hoặc `cancel` có thể giành trạng thái hoàn thành ban đầu. Giả sử hai callback từ hai nguồn song song:

```java
CompletableFuture<String> firstResult = new CompletableFuture<>();

// Thread/callback A:
boolean wonA = firstResult.complete("primary");

// Thread/callback B:
boolean wonB = firstResult.complete("backup");
```

Đây là **snippet**, không phải một chương trình thread hoàn chỉnh. Để biết ai thắng, cần xem giá trị `boolean` tại runtime; không được đoán luôn `primary` hoặc `backup`. Nếu code như trên chạy **tuần tự** thì `wonA=true`, `wonB=false`; nếu chạy **đồng thời** thì thứ tự phụ thuộc scheduling và phải thiết kế theo quy tắc “first successful completion wins”.

### 8.1. Đừng làm phụ thuộc tính đúng vào lời gọi `complete` thứ hai

```java
if (!promise.complete(result)) {
    // Đã có ai đó chốt trạng thái.
    // Có thể bỏ dữ liệu đến muộn hoặc ghi metric idempotent.
}
```

Đây là snippet trong phạm vi có biến `promise` và `result`. Không được gọi `obtrudeValue` chỉ vì `complete` trả `false`; thao tác `obtrudeValue` là công cụ cưỡng bức thay thế kết quả **ngoại lệ đặc biệt** cho recovery, có thể khiến các dependent stages đã chạy với kết quả trước trong khi caller sau thấy kết quả mới. Nó không phù hợp với luồng completion bình thường.

### 8.2. Không có quy tắc gọi callback theo thứ tự đăng ký

Khi có nhiều continuation độc lập của cùng một future, không nên dựa vào việc chúng chạy theo thứ tự thêm. Nếu A phải chạy trước B, hãy xây **quan hệ phụ thuộc**:

```java
CompletableFuture<String> source =
    CompletableFuture.completedFuture("data");

CompletableFuture<String> ordered =
    source.thenApply(s -> s + "-A")
          .thenApply(s -> s + "-B");
// ordered.join() == "data-A-B"
```

Đây là chuỗi dependency có thứ tự nhân quả. Hai lời gọi `source.thenApply(...)` riêng biệt không tự tạo ràng buộc giữa các continuation đó.

### 8.3. Công bố kết quả không khiến đối tượng mutable tự thread-safe

Nếu `T` là object có trường mutable và producer sửa object đó sau khi gọi `complete(value)`, consumer có thể quan sát một trạng thái đang thay đổi. `CompletableFuture` giúp **phối hợp thời điểm kết quả sẵn có**, nhưng không thay thế các nguyên tắc đồng bộ khi nhiều thread cùng mutate dữ liệu. Ưu tiên DTO bất biến, defensive copy hoặc thiết kế ownership rõ ràng.

## 9. Hủy future: `cancel` không giống dừng thread

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` hoàn thành future theo **cơ chế bất thường với `CancellationException`** nếu chưa hoàn thành. Khác với một số implementation `Future` truyền thống, `CompletableFuture` **không có quyền điều khiển trực tiếp công việc producer**; tham số `mayInterruptIfRunning` **không có tác dụng ngắt** tác vụ trong implementation này.

```java
CompletableFuture<String> task = new CompletableFuture<>();

boolean cancelled = task.cancel(false); // true
boolean done = task.isDone();           // true
boolean cancelledFlag = task.isCancelled(); // true
boolean exceptional = task.isCompletedExceptionally(); // true
```

`task.join()` lúc này sẽ ném `CancellationException`; không phải “đợi cho đến khi producer dừng hẳn”. Nếu producer đang chạy một I/O bên ngoài, việc cancel future không tự đóng socket hoặc hủy HTTP request; cần thêm API hủy có chủ đích do tác vụ thực sự cung cấp.

### 9.1. `isDone()` không có nghĩa thành công

Ba trạng thái terminal có thể nhìn thấy qua `isDone() == true`:

- **Thành công bình thường**, gồm cả trả `null`.
- **Hoàn thành bất thường** bằng `completeExceptionally` hoặc lỗi callback.
- **Hủy** bằng `cancel` (một dạng exceptional completion).

Vì vậy không viết `if (f.isDone()) return f.join();` rồi cho rằng mọi thứ chắc chắn thành công. `join` có thể ném `CompletionException` hoặc `CancellationException`.

### 9.2. Cẩn thận giá trị boolean khi gọi `cancel` nhiều lần

`complete` trả `true` đúng khi lời gọi đó chuyển future từ pending sang done. Còn `cancel` có hợp đồng trả `true` khi **future hiện đang bị hủy**, nên việc hủy một future đã hủy có thể vẫn trả `true`. Không dùng `cancel` như bộ đếm chính xác số lần chuyển trạng thái; nếu cần đo một transition, thiết kế trạng thái/metric riêng.

## 10. `getNow`, `join`, `get`: đọc kết quả đúng cách

| API | Future pending | Đã thành công | Đã thất bại/hủy |
| --- | --- | --- | --- |
| `isDone()` | `false` | `true` | `true` |
| `getNow(defaultValue)` | Trả `defaultValue` ngay | Trả kết quả, kể cả `null` | Ném exception phù hợp |
| `join()` | **Chờ** completion | Trả kết quả | Thường `CompletionException` hoặc `CancellationException` |
| `get()` | **Chờ** completion, có thể bị interrupt | Trả kết quả | `ExecutionException` hoặc `CancellationException` |
| `get(timeout,unit)` | Chờ tối đa thời gian được cấp | Trả kết quả nếu sẵn | Có thể `TimeoutException`/lỗi completion |

### 10.1. Không gọi `join()` quá sớm trong luồng phải tự hoàn thành future

Đoạn sau là một **anti-pattern** có nguy cơ treo:

```java
CompletableFuture<String> promise = new CompletableFuture<>();

// Sai nếu cùng thread không còn producer nào khác:
String result = promise.join();  // chờ vô hạn
promise.complete("READY");        // không bao giờ tới dòng này
```

Đây là snippet minh họa **không nên chạy**. `join` chặn thread hiện tại cho đến khi future hoàn thành. Nếu dòng `complete` chỉ có thể được chạy bởi cùng thread sau `join`, sẽ không có completion để giải phóng.

**Cách đúng:** thiết lập producer/đăng ký callback trước; để event loop hoặc thread khác hoàn thành, và ở tầng consumer ưu tiên trả `CompletionStage` để xâu chuỗi non-blocking thay vì chặn.

### 10.2. Timeout khi chờ khác với hoàn thành future bằng timeout

Trong Java 8, bạn có thể dùng:

```java
try {
    String value = promise.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Luồng gọi đã hết thời gian chờ.
    // promise có thể VẪN đang pending và hoàn thành sau đó.
}
```

Đây là snippet trong method, cần thêm xử lý `InterruptedException` và `ExecutionException` hoặc khai báo `throws` phù hợp, cùng import `TimeUnit`, `TimeoutException`. `get(timeout,unit)` **không tự quyết định kết quả của future** khi timeout; nó chỉ giới hạn thời gian chờ của **lời gọi đó**.

Từ Java 9, `future.orTimeout(...)` có thể **hoàn thành chính future đó bất thường** nếu chưa có kết quả trước hạn, còn `future.completeOnTimeout(defaultValue,...)` hoàn thành chính future đó **bình thường với fallback** nếu chưa xong. Hai API này trả lại **cùng future**, và không tự dừng tác vụ nền. Với hệ thống có I/O thật, nên cân nhắc timeout ở cấp client/request bên dưới thay vì chỉ hoàn thành wrapper future và bỏ mặc tài nguyên.

### 10.3. `getNow` không phải `Optional` hoặc phương thức chờ

`getNow(valueIfAbsent)` trả giá trị fallback nếu chưa done, nhưng fallback có thể **trùng với một giá trị thật**. Nó không phải một kiểm tra trạng thái không mơ hồ:

```java
CompletableFuture<String> pending = new CompletableFuture<>();
String value = pending.getNow("WAITING"); // "WAITING"

// Nếu producer sau này complete("WAITING"),
// cùng chuỗi kết quả không nói được lần đọc nào là fallback.
```

Nếu cần phân biệt pending/success/failure, thiết kế trạng thái rõ ràng hoặc dùng continuation phù hợp. Đừng dùng một sentinel dễ trùng với dữ liệu người dùng mà không có hợp đồng.

## 11. Bọc callback thành `CompletionStage`: ứng dụng thực tế

Một chiến lược hữu ích trong hệ thống hỗn hợp callback và Future là **giữ `CompletableFuture` trong lớp adapter**, chỉ trả `CompletionStage` cho caller.

Ví dụ một client kiểu callback:

```java
interface AsyncLookup {
    void lookup(String id,
                BiConsumer<String, Throwable> callback);
}

static CompletionStage<String> lookupAsStage(
        AsyncLookup client, String id) {
    CompletableFuture<String> promise = new CompletableFuture<>();

    try {
        client.lookup(id, (value, error) -> {
            if (error != null) {
                promise.completeExceptionally(error);
            } else {
                promise.complete(value);
            }
        });
    } catch (RuntimeException error) {
        promise.completeExceptionally(error);
    }

    return promise;
}
```

Đây là **snippet trong class**, cần các import `CompletionStage`, `CompletableFuture` và `BiConsumer`, với interface `AsyncLookup` do ứng dụng định nghĩa. Nó thể hiện:

- Thành công và thất bại **đều hoàn thành promise**.
- Callback có thể được gọi sau khi phương thức adapter đã trả stage.
- Callback có thể được gọi **nhiều lần** do lỗi SDK; first-wins sẽ không cho ghi đè completion.
- Nếu việc **đăng ký callback tự ném exception đồng bộ**, adapter cũng hoàn thành future bất thường.
- Bên ngoài chỉ nhận `CompletionStage`, giao diện tốt hơn để trình bày khả năng xâu chuỗi thay vì khuyến khích consumer gọi `complete`. Tuy nhiên, trong Java 8, type interface không phải cơ chế bảo mật tuyệt đối nếu implementation thực vẫn có thể được downcast.

**Cần hiểu hợp đồng callback:** `value == null` có thể là kết quả hợp lệ hoặc sai protocol; `error != null` phải là một `Throwable` có ý nghĩa. Nếu SDK có cơ chế callback cả kết quả và lỗi cùng khác null, adapter phải ưu tiên hoặc từ chối theo hợp đồng nguồn chứ không suy đoán.

### 11.1. Không biến callback thành một thread riêng nếu không cần

`new CompletableFuture<>()` và `complete` chỉ liên kết kết quả với consumer. SDK callback đã chạy trên một thread/event loop do SDK quyết định; không có nhu cầu mặc định phải gọi `CompletableFuture.supplyAsync(() -> waitForCallback())` để đợi callback bằng blocking. Cách bọc callback chuẩn giúp chuyển API cũ sang mô hình continuation **mà không chiếm một worker chỉ để ngồi chờ**.

### 11.2. Tài nguyên và thời gian sống

Nếu callback không bao giờ được gọi, promise pending mãi; các dependent actions có thể giữ tham chiếu đến input, request context hoặc object lớn. Cần thiết kế timeout, cancellation của I/O gốc, cleanup listener và metric cho các promise pending lâu. Bản thân `CompletableFuture` không thể “tự giải phóng” một đăng ký listener ngoài hệ thống chỉ vì caller bỏ tham chiếu.

### 11.3. Lỗi callback và phân biệt trạng thái lỗi

Nếu callback vừa `completeExceptionally`, caller có thể dùng:

```java
lookupAsStage(client, id)
    .exceptionally(error -> "FALLBACK")
    .thenAccept(value -> {
        // Xử lý giá trị sau khi đã khôi phục hoặc nhận thành công.
    });
```

Đây là snippet, giả định đã có method `lookupAsStage` và các biến `client`, `id`. Cần thiết kế fallback thật sự phù hợp; không nuốt lỗi bất kỳ bằng chuỗi “FALLBACK” trong các nghiệp vụ quan trọng mà không có logging/giám sát an toàn.

## 12. `supplyAsync` khác tạo future hoàn thành sẵn hoặc thủ công

Có ba cách thường bị trộn lẫn:

```java
// A. Kết quả đã biết:
CompletableFuture<Integer> a =
    CompletableFuture.completedFuture(10);

// B. Để callback bên ngoài quyết định khi nào có kết quả:
CompletableFuture<Integer> b = new CompletableFuture<>();
// callback sau này gọi b.complete(value) hoặc completeExceptionally(error)

// C. Tự chạy một supplier bất đồng bộ:
CompletableFuture<Integer> c =
    CompletableFuture.supplyAsync(() -> expensiveComputation());
```

Đây là snippet: cần có hàm `expensiveComputation()` trong ứng dụng. Ở cách C, `supplyAsync` **lên lịch supplier**, tương lai mới có kết quả khi supplier chạy; nếu supplier ném exception, future hoàn thành bất thường.

### 12.1. Thread và executor của non-async continuation

`thenApply`/`whenComplete` không có hậu tố `Async` có thể được thực hiện bởi thread **đang hoàn thành** future hoặc thread khác tham gia completion theo hợp đồng. Vì vậy:

```java
CompletableFuture<String> p = new CompletableFuture<>();

CompletableFuture<String> transformed =
    p.thenApply(value -> expensiveTransform(value));

// p.complete(...) có thể kích hoạt transformed trên thread hoàn thành p.
```

Đây là snippet với `expensiveTransform` được ứng dụng định nghĩa. **Không bắt buộc mọi non-async action đều chạy trên thread pool nền**. Nếu callback xuất phát từ event loop hoặc thread nhận HTTP response, chạy CPU quá nặng trong continuation non-async có thể làm nghẽn đường callback.

### 12.2. Dùng `thenApplyAsync(..., executor)` khi cần cách ly công việc

```java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<String> p = new CompletableFuture<>();
    CompletableFuture<String> stage =
        p.thenApplyAsync(
            text -> text.toUpperCase(Locale.ROOT),
            executor);

    p.complete("java");
    System.out.println(stage.join()); // JAVA
} finally {
    executor.shutdown();
}
```

Đây là snippet trong method với `ExecutorService`, `Executors`, `Locale`, `CompletableFuture`. Việc chọn executor riêng giúp kiểm soát tài nguyên khi cần; với nhiều request, vẫn phải quản lý giới hạn hàng đợi, concurrency và shutdown. `join` trong snippet chỉ dùng để minh họa lấy kết quả; trong request handler non-blocking, ưu tiên trả stage và xâu chuỗi.

Các overload `thenApplyAsync(fn)` không truyền executor mặc định sử dụng cơ chế thực thi async của `CompletableFuture` (thông thường dựa trên ForkJoin common pool theo chính sách JDK), nhưng không nên xem đây là pool chuyên biệt riêng cho mỗi request. Không khởi tạo executor mới trong từng lời gọi business method rồi quên shutdown.

### 12.3. `completeAsync` từ Java 9 không giống `supplyAsync`

`CompletableFuture.supplyAsync(supplier)` tạo **một future mới** đại diện cho phép tính được lên lịch. Từ **Java 9**, `existingFuture.completeAsync(supplier[, executor])` lên lịch supplier để **cố hoàn thành future đang có**, rồi trả lại chính future đó. Nếu một producer khác hoàn thành trước, kết quả đã chốt vẫn có hiệu lực theo first-wins.

Không dùng `completeAsync` trong Java 8; nếu dự án đã dùng Java hiện đại và chọn API này, phải nhận thức rõ cạnh tranh giữa supplier được lên lịch và các lời gọi `complete` khác.

## 13. Chương trình Java hoàn chỉnh: thành công sẵn, pending, lỗi và callback

Ví dụ dưới đây chỉ sử dụng API **Java 8**, có thể biên dịch với `javac --release 8` trên JDK hỗ trợ tùy chọn này. Nó dùng dữ liệu cố định để stdout xác định, không dựa vào thời gian chờ, thứ tự chạy thread ngẫu nhiên hay dịch vụ bên ngoài.

Tạo file **CompletableFutureCompletionDemo.java**:

```java
import java.util.Locale;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.BiConsumer;

public class CompletableFutureCompletionDemo {
    interface Lookup {
        void find(String key,
                  BiConsumer<String, Throwable> callback);
    }

    static CompletionStage<String> adapt(Lookup lookup, String key) {
        CompletableFuture<String> promise = new CompletableFuture<>();
        try {
            lookup.find(key, (value, error) -> {
                if (error != null) {
                    promise.completeExceptionally(error);
                } else {
                    promise.complete(value);
                }
            });
        } catch (RuntimeException error) {
            promise.completeExceptionally(error);
        }
        return promise;
    }

    public static void main(String[] args) {
        CompletableFuture<String> ready =
            CompletableFuture.completedFuture("READY");

        System.out.println("Already done: " + ready.isDone());
        System.out.println("Already value: " + ready.join());
        System.out.println("Already map: "
            + ready.thenApply(s -> s + "!").join());
        System.out.println("Ready recomplete: "
            + ready.complete("OVERRIDE"));

        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<Integer> length =
            pending.thenApply(String::length);

        System.out.println("Pending done: " + pending.isDone());
        System.out.println("Pending getNow: "
            + pending.getNow("WAITING"));
        System.out.println("Dependent done before: "
            + length.isDone());

        System.out.println("Complete first: "
            + pending.complete("JAVA"));
        System.out.println("Complete second: "
            + pending.complete("OTHER"));
        System.out.println("Promise value: " + pending.join());
        System.out.println("Dependent length: " + length.join());

        CompletableFuture<String> completedNull =
            CompletableFuture.completedFuture(null);
        System.out.println("Completed null done: "
            + completedNull.isDone());
        System.out.println("Null getNow is null: "
            + (completedNull.getNow("DEFAULT") == null));

        CompletableFuture<Integer> failure = new CompletableFuture<>();
        CompletableFuture<Integer> recovered =
            failure.exceptionally(error -> -1);

        System.out.println("Exceptional first: "
            + failure.completeExceptionally(
                new IllegalArgumentException("invalid")));
        System.out.println("Exceptional second: "
            + failure.complete(7));
        System.out.println("Failure done/ex: "
            + failure.isDone() + "/"
            + failure.isCompletedExceptionally());
        System.out.println("Recovered: " + recovered.join());

        try {
            failure.join();
        } catch (CompletionException error) {
            System.out.println("join cause: "
                + error.getCause().getClass().getSimpleName());
        }

        try {
            failure.get();
        } catch (ExecutionException error) {
            System.out.println("get cause: "
                + error.getCause().getClass().getSimpleName());
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            System.out.println("get was interrupted");
        }

        CompletableFuture<String> cancelled =
            new CompletableFuture<>();
        System.out.println("Cancel first: "
            + cancelled.cancel(false));
        System.out.println("Cancel status: "
            + cancelled.isCancelled() + "/"
            + cancelled.isCompletedExceptionally());
        try {
            cancelled.join();
        } catch (CancellationException error) {
            System.out.println("Cancel join: CancellationException");
        }

        CompletableFuture<Void> signal = new CompletableFuture<>();
        CompletableFuture<String> afterSignal =
            signal.thenApply(ignored -> "SIGNALLED");
        System.out.println("Complete signal: "
            + signal.complete(null));
        System.out.println("Void continuation: "
            + afterSignal.join());

        Lookup successful = (key, callback) ->
            callback.accept("profile:" + key, null);
        Lookup unsuccessful = (key, callback) ->
            callback.accept(null,
                new IllegalStateException("unavailable"));

        System.out.println("Bridge normal: "
            + adapt(successful, "alice")
                .toCompletableFuture().join());
        System.out.println("Bridge recovered: "
            + adapt(unsuccessful, "bob")
                .exceptionally(error -> "FALLBACK")
                .toCompletableFuture().join());

        ExecutorService executor =
            Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> manual = new CompletableFuture<>();
            CompletableFuture<String> transformed =
                manual.thenApplyAsync(
                    text -> text.toLowerCase(Locale.ROOT),
                    executor);

            System.out.println("Async complete: "
                + manual.complete("JAVA"));
            System.out.println("Async result: "
                + transformed.join());
        } finally {
            executor.shutdown();
        }
    }
}
```

Biên dịch/chạy ở thư mục chứa file. Với JDK 9+ có thể thêm `--release 8` để kiểm tra API ở mức Java 8:

```bash
javac --release 8 -encoding UTF-8 CompletableFutureCompletionDemo.java
java CompletableFutureCompletionDemo
```

**Stdout chính xác:**

```text
Already done: true
Already value: READY
Already map: READY!
Ready recomplete: false
Pending done: false
Pending getNow: WAITING
Dependent done before: false
Complete first: true
Complete second: false
Promise value: JAVA
Dependent length: 4
Completed null done: true
Null getNow is null: true
Exceptional first: true
Exceptional second: false
Failure done/ex: true/true
Recovered: -1
join cause: IllegalArgumentException
get cause: IllegalArgumentException
Cancel first: true
Cancel status: true/true
Cancel join: CancellationException
Complete signal: true
Void continuation: SIGNALLED
Bridge normal: profile:alice
Bridge recovered: FALLBACK
Async complete: true
Async result: java
```

### 13.1. Giải thích các điểm đáng chú ý

1. `completedFuture("READY")` có `isDone()==true` ngay khi tạo; `thenApply` áp dụng lên kết quả thành công và trả stage với `"READY!"`. Lời gọi `complete("OVERRIDE")` không làm thay đổi `ready` vì nó đã hoàn thành.
2. `pending` chưa xong nên `getNow("WAITING")` trả fallback ngay; `length` phụ thuộc vào kết quả của `pending`, chưa thể hoàn thành trước nguồn.
3. `pending.complete("JAVA")` trả `true` và cho phép dependent tính độ dài 4. Lời gọi `complete("OTHER")` sau đó trả `false`; kết quả vẫn là `"JAVA"`.
4. `completedFuture(null)` chứng tỏ một giá trị `null` có thể là kết quả thành công thật. `getNow("DEFAULT")` không dùng fallback khi đã hoàn thành, dù kết quả là null.
5. `completeExceptionally` chốt failure; `isDone` vẫn true. Stage `recovered` được tạo trước khi lỗi được công bố, nên nhận fallback `-1`. Future nguồn vẫn lỗi: `join()` ném `CompletionException`, `get()` ném `ExecutionException`, cùng nguyên nhân `IllegalArgumentException`.
6. `cancel(false)` làm pending future chuyển sang cancelled/exceptional. `join()` ném `CancellationException`; điều này không chứng minh một thread công việc ngoài đã dừng.
7. `CompletableFuture<Void>` hoàn thành bằng `complete(null)` để gửi tín hiệu thành công không kèm payload, sau đó dependent trả `"SIGNALLED"`.
8. Adapter `adapt` biến callback thành `CompletionStage`, với nhánh thành công và nhánh lỗi. Các callback trong chương trình được gọi **đồng bộ để stdout xác định**; adapter vẫn hoạt động về mặt thiết kế nếu SDK thực gọi callback bất đồng bộ ở nơi khác.
9. Continuation `thenApplyAsync` nhận `ExecutorService` rõ ràng. Thread của executor có thể chạy vào thời điểm khác nhau, nhưng `transformed.join()` đảm bảo ta in đúng kết quả sau khi continuation hoàn thành; không cần giả định thứ tự scheduling.
10. `executor.shutdown()` được gọi trong `finally` để giải phóng executor; chương trình không dùng common pool mặc định cho continuation riêng này.

## 14. Thiết kế production: tránh future pending vô hạn và lỗi lifecycle

Tạo promise thủ công đòi hỏi trách nhiệm cao hơn `completedFuture`: producer phải **luôn có một con đường hoàn thành** hoặc có chính sách timeout/cancel và dọn tài nguyên thích hợp.

### 14.1. Quy tắc “mọi nhánh đều hoàn thành”

```java
CompletableFuture<Result> promise = new CompletableFuture<>();
try {
    Result result = executeOperation();
    promise.complete(result);
} catch (Exception error) {
    promise.completeExceptionally(error);
}
```

Đây là snippet với `Result`, `executeOperation()` do ứng dụng cung cấp. Nó minh họa nguyên tắc nhưng nếu toàn bộ phép tính chỉ chạy **đồng bộ**, việc tạo future thủ công có thể không mang lại lợi ích lớn; dùng `completedFuture` sau khi tính xong hoặc thay đổi contract cho phù hợp.

Khi bọc callback, hãy kiểm tra từng con đường: callback thành công, callback lỗi, lỗi đăng ký listener, timeout, hủy bên dưới, kết nối đóng trước khi callback, callback bị gọi nhiều lần, callback không được gọi. Một nhánh bị bỏ quên có thể khiến `join/get` ở nơi khác chờ vô hạn.

### 14.2. Timeout có hai tầng cần phân biệt

1. **Timeout của việc chờ kết quả:** `get(timeout, TimeUnit)` trong Java 8 chỉ chấm dứt lời gọi chờ khi quá hạn.
2. **Timeout của toàn tác vụ/promise:** `orTimeout` hoặc `completeOnTimeout` (Java 9+) có thể quyết định future hoàn thành dù producer chưa trả lời, nhưng không đảm bảo dừng I/O. Phải có cơ chế timeout/cancel ở client thật để tránh giữ socket/connection.

Với Java 8 có thể dùng scheduler/`ScheduledExecutorService` để dự kiến gọi `promise.completeExceptionally(new TimeoutException(...))`, nhưng phải **hủy scheduled task và cleanup tài nguyên** sau kết quả; một wrapper future tự đặt timeout mà không điều khiển tác vụ nền có thể gây rò rỉ và side effect muộn. Đây là một thiết kế riêng, không phải yêu cầu phải tự viết khi thư viện đã hỗ trợ timeout.

### 14.3. Hậu quả khi gọi `complete` trước khi đăng ký continuation

Đăng ký continuation **sau khi future đã hoàn thành** vẫn được phép; nhưng nếu continuation rất nặng và không có hậu tố `Async`, nó có thể thực hiện ngay trong luồng gọi đăng ký theo chính sách thực thi. Nếu ứng dụng cần tránh khối CPU nặng ngay cả trên nhánh cache hit, dùng `thenApplyAsync(..., executor)` khi phù hợp, không dựa vào giả định “completedFuture rất nhẹ thì mọi continuation cũng nhẹ”.

### 14.4. Không expose quyền hoàn thành một cách vô ý

Nếu code service công khai:

```java
public CompletableFuture<Result> fetchResult() { /* ... */ }
```

caller nhìn thấy method `complete`/`completeExceptionally` và có thể cố thay đổi trạng thái. Nếu consumer chỉ cần composition, có thể công khai:

```java
public CompletionStage<Result> fetchResult() { /* ... */ }
```

Đây là **chữ ký minh họa**, `Result` và implementation chưa được định nghĩa. `CompletionStage` giúp thể hiện **ý định API** là xâu chuỗi, không trao quyền sản xuất kết quả; tuy nhiên trong Java 8, caller có thể biết implementation thật là `CompletableFuture` và cố cast, nên đây **không phải biên an ninh**. Khi cần một bề mặt stage tối giản có kiểm soát hơn trên Java 9+, xem `minimalCompletionStage()`/`completedStage()`; khi cần tránh chia sẻ trạng thái thì thiết kế ownership, wrapper hoặc copy thích hợp.

### 14.5. Idempotency, cancellation và resource management

Khi callback đến hai lần, `complete` thứ hai trả `false`. Điều đó làm *result slot* được giữ nhất quán, nhưng không giải quyết tự động transaction, chi phí retry, giải phóng subscription hoặc side effect bên ngoài. Producer nên ghi nhận completion đầu tiên và vô hiệu hóa listener/timer theo API nguồn.

Nếu consumer hủy future, producer phải có giao thức riêng để dừng công việc (nếu API hỗ trợ), và vẫn phải biết callback đến sau cancellation có thể không thể hoàn thành future nữa. Không thiết kế hệ thống hủy network dựa duy nhất vào `CompletableFuture.cancel(true)`.

## 15. Lỗi thường gặp và cách sửa

### 15.1. Dùng `supplyAsync` chỉ để bọc hằng số

**Sai:** `supplyAsync(() -> 42)` cho một giá trị vốn đã biết, khiến hệ thống tốn scheduling. **Đúng:** `completedFuture(42)` khi không có phép tính bất đồng bộ cần chạy.

### 15.2. Tưởng `new CompletableFuture<>()` tự chạy công việc

**Sai:** tạo promise rồi chờ `join()` mà chưa thiết lập producer. **Đúng:** đăng ký callback/producer hoặc dùng `supplyAsync` để thực sự lên lịch tính toán.

### 15.3. Gọi `join()` trước `complete()` trong cùng thread

**Sai:** `join` chặn vô hạn và không đến dòng `complete`. **Đúng:** bố trí producer độc lập, trả `CompletionStage` hoặc gắn continuation mà không chặn.

### 15.4. Cho rằng `completedFuture(null)` là pending

**Sai:** thấy `getNow("fallback") == null` rồi suy ra future chưa xong. **Đúng:** future đã hoàn thành thành công với `null`; kiểm tra trạng thái hoặc quy định kiểu kết quả không mơ hồ.

### 15.5. Gọi `complete` hai lần rồi kỳ vọng lần sau ghi đè

**Sai:** `future.complete("second")` thay được kết quả first. **Đúng:** first completion wins; kiểm tra boolean trả về và xử lý kết quả tới muộn. Không dùng `obtrudeValue` như lối tắt.

### 15.6. Coi `isDone()` là thành công

**Sai:** future cancelled/failed vẫn `isDone()==true`. **Đúng:** xử lý normal/exceptional/cancellation; `join/get` có thể ném exception.

### 15.7. Dùng `completeExceptionally(null)`

**Sai:** truyền null làm error. **Đúng:** truyền `Throwable` thật; nếu thành công không payload dùng `complete(null)` với `CompletableFuture<Void>`.

### 15.8. Tưởng `exceptionally` sửa luôn future nguồn

**Sai:** future nguồn lỗi nên sau `exceptionally` nó sẽ thành công. **Đúng:** `exceptionally` trả dependent stage đã khôi phục; source vẫn exceptional.

### 15.9. Dùng `getNow(fallback)` như bộ phát hiện lỗi

**Sai:** cho rằng nó luôn trả fallback khi chưa có giá trị hoặc khi thất bại. **Đúng:** nó trả fallback cho pending, trả giá trị thật cho success (kể cả null), và báo exception cho failed/cancelled.

### 15.10. Coi `cancel(true)` chắc chắn ngắt worker

**Sai:** một `CompletableFuture` độc lập có quyền điều khiển producer. **Đúng:** cancellation là một dạng exceptional completion; phải có API hủy thực sự của tác vụ nền.

### 15.11. Quên phân biệt Java 8 với Java 9+

**Sai:** dùng `failedFuture`, `completedStage`, `orTimeout` hoặc `completeAsync` trong code build `--release 8`. **Đúng:** dùng `new CompletableFuture` + `completeExceptionally`, `completedFuture` và timeout mechanism tương thích Java 8, hoặc nâng mức API nếu dự án cho phép.

### 15.12. Để callback không bao giờ hoàn thành promise

**Sai:** chỉ hoàn thành ở success, bỏ error hoặc tình huống listener không được kích hoạt. **Đúng:** thiết kế complete/completeExceptionally cho tất cả nhánh, cùng timeout và cleanup.

### 15.13. Không kiểm soát tác vụ nặng của continuation non-async

**Sai:** mặc định `thenApply` luôn chạy trên background pool. **Đúng:** nó có thể chạy trên thread hoàn thành future; công việc nặng cần executor và cơ chế giới hạn tải phù hợp.

### 15.14. Quên cleanup executor

**Sai:** tạo `Executors.newSingleThreadExecutor()` cho mỗi request rồi không đóng. **Đúng:** dùng executor được quản lý theo vòng đời ứng dụng, shutdown theo chính sách và tránh tạo vô hạn thread/queue.

### 15.15. Tin completion đồng nghĩa toàn bộ hệ thống đã giao dịch thành công

**Sai:** dùng `complete(true)` để khẳng định database/email/network chắc chắn đã commit đúng một lần. **Đúng:** future chỉ đại diện kết quả do producer công bố; yêu cầu transaction/idempotency phải được bảo đảm bởi lớp nghiệp vụ và hệ thống ngoài.

## 16. Bảng kiểm ứng dụng

Trước khi quyết định tạo future hoàn thành sẵn hay thủ công, hãy kiểm tra:

1. **Kết quả có thực sự đã biết?** Nếu có, chọn `completedFuture`.
2. **Có một phép tính phải chạy?** Nếu có, cân nhắc `supplyAsync`/`runAsync` với executor thích hợp.
3. **Kết quả do callback bên ngoài quyết định?** Nếu có, dùng promise thủ công với `complete`/`completeExceptionally`.
4. **Mọi đường đi đều có completion?** Xử lý cả success, error, exception khi đăng ký, timeout và cancellation.
5. **Giá trị `null` có ý nghĩa?** Phân biệt null thành công với pending.
6. **Đã nghĩ đến race?** Tác nhân chốt trước thắng, boolean `complete` phải được kiểm tra nếu dữ liệu tới muộn có ý nghĩa.
7. **Caller chỉ nên quan sát hay được phép hoàn thành?** Cân nhắc trả `CompletionStage`, ownership và wrapper.
8. **Có continuation nặng?** Tránh chặn event loop; dùng async variant với executor được quản lý.
9. **Có nguy cơ join làm deadlock?** Không block luồng duy nhất có khả năng hoàn thành nguồn.
10. **Exception nào caller nhận?** Phân biệt `CompletionException`, `ExecutionException` và `CancellationException`.
11. **Timeout chờ và timeout tác vụ có khác nhau?** Kiểm tra xem timeout chỉ ngừng chờ hay thực sự kết thúc công việc.
12. **Có tác dụng phụ ngoài Future?** Cần transaction/idempotency thực, không chỉ dựa vào first-wins.
13. **Đang nhắm Java phiên bản nào?** Java 8 cho `completedFuture`/`complete`; Java 9+ bổ sung factory/timeout.
14. **Đã kiểm thử completion trước/sau đăng ký?** Cả nhánh ready lẫn pending đều phải xử lý đúng.
15. **Đã thử null, failure, cancel, duplicate callback và late response?** Đây là các trường hợp thường tạo lỗi ở production.

## 17. Câu hỏi tự luyện và đáp án

**1.** `CompletableFuture.completedFuture(42)` có tạo thread mới không?  
**Đáp án:** không. Nó tạo future đã hoàn thành với 42, không cần chạy supplier.

**2.** `new CompletableFuture<String>()` đã bắt đầu công việc gì?  
**Đáp án:** chưa. Nó chỉ tạo một promise pending; cần producer/callback hoặc cơ chế thực thi khác.

**3.** `complete("A")` rồi `complete("B")` cho kết quả nào?  
**Đáp án:** future giữ `"A"`; lời gọi đầu trả `true`, lời gọi sau trả `false` khi chạy tuần tự như ví dụ.

**4.** `complete(null)` trên `CompletableFuture<Void>` có hợp lệ không?  
**Đáp án:** có; là completion bình thường không payload.

**5.** `completedFuture(null).getNow("fallback")` trả gì?  
**Đáp án:** `null` vì future đã hoàn thành. Fallback chỉ dành cho pending.

**6.** `completeExceptionally(new IOException())` có khiến `isDone() == true` không?  
**Đáp án:** có. Future đã kết thúc bất thường; `isCompletedExceptionally()==true`.

**7.** `join()` và `get()` ném lỗi gì nếu hoàn thành bất thường với `IllegalArgumentException`?  
**Đáp án:** thường `CompletionException` và `ExecutionException` tương ứng, bọc nguyên nhân; `get` còn có `InterruptedException` trong lúc chờ.

**8.** Có factory `CompletableFuture.failedFuture` trong Java 8 không?  
**Đáp án:** không. Dùng `new CompletableFuture<>()` + `completeExceptionally`; factory ra mắt Java 9.

**9.** Nếu `promise.thenApply(...)` được tạo trước `promise.complete(...)` thì có chạy không?  
**Đáp án:** có; continuation được kích hoạt khi promise hoàn thành thành công.

**10.** `exceptionally` có thay đổi trạng thái failed future nguồn không?  
**Đáp án:** không. Nó tạo một dependent stage nhận fallback khi nguồn lỗi.

**11.** `get(timeout,unit)` hết thời gian chờ có làm future tự thất bại không?  
**Đáp án:** không. Nó ném `TimeoutException` cho lời gọi đó; future có thể hoàn thành sau.

**12.** `orTimeout` và `completeOnTimeout` có từ Java nào?  
**Đáp án:** Java 9. Chúng chốt chính future khi quá hạn nếu chưa hoàn thành, nhưng không tự hủy I/O gốc.

**13.** `cancel(true)` có bảo đảm ngắt thread producer không?  
**Đáp án:** không với `CompletableFuture`; tham số ngắt không có tác dụng trong implementation này.

**14.** Có nên expose `CompletableFuture` cho consumer không cần quyền complete?  
**Đáp án:** thường nên cân nhắc trả `CompletionStage` để mô tả ý định. Với Java 8, đây không phải sandbox quyền hạn tuyệt đối.

**15.** Khi có hai callback cùng gọi `complete`, có thể cả hai đều trả `true` không?  
**Đáp án:** không đối với hai lời gọi cạnh tranh để chốt cùng future ban đầu; chỉ một phép chuyển pending→completed thắng.

**16.** Vì sao không dùng `CompletableFuture.supplyAsync(() -> callbackWait())` để ngồi đợi callback?  
**Đáp án:** nó có thể chiếm thread chờ vô ích; bọc callback bằng promise thủ công giúp stage được hoàn thành khi event đến.

**17.** Nếu một callback hoàn thành future rồi callback khác đến muộn, phải làm gì?  
**Đáp án:** kiểm tra `complete(...)` trả `false` và xử lý kết quả đến muộn/cleanup theo quy tắc của SDK; không dùng `obtrudeValue` mặc định.

**18.** Một `whenComplete` non-async có chắc chạy trên thread khác thread gọi `complete` không?  
**Đáp án:** không. Nó có thể chạy trên thread thực hiện completion hoặc caller liên quan; dùng `whenCompleteAsync(..., executor)` nếu cần điều khiển vị trí thực thi.

## 18. Tài liệu API chính thức (còn áp dụng)

Các tài liệu Java SE hiện hành dùng để đối chiếu hợp đồng. Những API thêm sau Java 8 được đánh dấu trong bài; không cần dùng API legacy để thực hiện các mẫu cơ bản:

- [`CompletableFuture` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `completedFuture`, `complete`, `completeExceptionally`, `join`, `getNow`, cancellation, policies cho non-async actions và `obtrudeValue`.
- [`CompletionStage` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html): `thenApply`, `thenCompose`, `handle`, `whenComplete`, `exceptionally` và quy tắc dependent stages.
- [`Future` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): `get`, timed get, cancellation, trạng thái completion và hợp đồng bộ nhớ.
- [`ExecutorService` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): lập lịch/chạy tác vụ bằng executor quản lý vòng đời.
- [`CompletionException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionException.html): biểu diễn failure khi dùng `join` và các completion stages.
- [`ExecutionException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html): failure khi gọi `Future.get`.
