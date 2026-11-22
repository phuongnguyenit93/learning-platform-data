# complete, completeExceptionally và cạnh tranh hoàn thành trong CompletableFuture

> **Module:** Java 8 — CompletableFuture. Bài tập trung vào **chủ động hoàn thành một CompletableFuture** bằng `complete` hoặc `completeExceptionally`, cách nhiều luồng **cạnh tranh xác lập kết quả**, hệ quả với dependent stages, exception, cancellation, task nền và kiểm thử. Những API chính đều có từ Java 8 và vẫn là cơ chế hiện hành của `java.util.concurrent.CompletableFuture`.

## 1. Tư duy cốt lõi: ai được quyết định kết quả cuối cùng?

`CompletableFuture<T>` là một đối tượng có hai vai trò:

- **`Future<T>`:** đại diện cho một kết quả mà code khác có thể chờ và đọc.
- **`CompletionStage<T>`:** cho phép xây dựng pipeline như `thenApply`, `thenCompose`, `handle`, `whenComplete` hoặc `exceptionally` để phản ứng khi kết quả sẵn sàng.

Một `CompletableFuture` có thể được hoàn thành bởi:

1. Task được khởi chạy qua `supplyAsync` hoặc `runAsync`.
2. Một thread/logic bên ngoài gọi `complete(value)`.
3. Một thread/logic bên ngoài gọi `completeExceptionally(error)`.
4. Một thao tác như `cancel(...)`.
5. Kết quả của một dependent stage khi action của stage ấy kết thúc.

**Quy tắc căn bản:** Trong các thao tác hoàn thành thông thường cạnh tranh trên **cùng một CompletableFuture**, **chỉ một thao tác hoàn thành đầu tiên được chấp nhận**. Những thao tác hoàn thành sau trả về `false` và **không thay thế kết quả đã được xác lập**.

~~~text
                 CompletableFuture<T> chưa hoàn thành
                               |
               +---------------+-----------------+
               |               |                 |
        complete(value)   completeExceptionally  cancel(...)
               |               |                 |
        giá trị T/null       Throwable          cancellation
               |               |                 |
               +---------------+-----------------+
                               |
                    trạng thái đã hoàn thành
                 (một kết quả thông thường)
                               |
                   completion attempt muộn
                         trả false
~~~

Sơ đồ mô tả các đường hoàn thành thường gặp; `obtrudeValue` và `obtrudeException` là **cơ chế ghi đè đặc biệt**, được bàn riêng vì chúng không tuân theo quy tắc bất biến kết quả của các lời gọi `complete` thông thường.

### 1.1. Hoàn thành không đồng nghĩa bắt đầu xử lý

`CompletableFuture<String> future = new CompletableFuture<>()` tạo một future **chưa có kết quả**, không tự chạy một task. Trong khi đó `CompletableFuture.supplyAsync(supplier)` tạo future liên quan tới một tác vụ bất đồng bộ.

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();

// Chưa có code bất đồng bộ nào chạy chỉ nhờ constructor.
boolean success = pending.complete("READY");

// success == true; pending.join() trả "READY".
~~~

Đây là **đoạn minh họa**, cần `import java.util.concurrent.CompletableFuture;`.

Một `CompletableFuture` không nhất thiết được tính bởi CPU ở background. Nó còn có thể đóng vai trò **lời hứa do callback, sự kiện network, message bus hoặc thread khác giải quyết**.

### 1.2. Completion là một lần thắng race, không phải lệnh ghi giá trị tùy ý

Một khi future được hoàn thành bình thường hoặc bất thường, `complete(value)` và `completeExceptionally(error)` tiếp theo sẽ trả `false`. Hãy hiểu chúng là **thử hoàn thành nếu còn chỗ trống**, không phải setter như `AtomicReference.set`.

Mô hình an toàn:

~~~java
boolean won = future.complete(result);
if (won) {
    // Lời gọi này đã xác lập kết quả của future.
} else {
    // Future đã được hoàn thành trước đó bởi một nguồn khác.
}
~~~

Đây là **đoạn minh họa** với `future` và `result` đã có. Boolean của `complete` mô tả **lời gọi đã khiến future chuyển sang hoàn thành hay không**, không phải giá trị boolean của chính `result`.

## 2. complete(T value): hoàn thành thành công

Chữ ký Java 8:

~~~java
public boolean complete(T value)
~~~

Ý nghĩa:

- Nếu future đang chưa hoàn thành: chuyển sang trạng thái **hoàn thành bình thường** với `value`, trả `true`.
- Nếu future đã hoàn thành trước: không thay thế kết quả, trả `false`.
- `value` có thể là `null` nếu `T` là kiểu tham chiếu; `CompletableFuture<Void>` thường dùng `complete(null)` như tín hiệu hoàn thành.
- Future hoàn thành bình thường sẽ cho `join()`/`get()` trả giá trị đã chốt (hoặc null).
- Các dependent stages đủ điều kiện có thể được kích hoạt khi completion xảy ra.

Ví dụ:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

boolean first = result.complete("OK");
boolean second = result.complete("LATE");

System.out.println(first);        // true
System.out.println(second);       // false
System.out.println(result.join()); // OK
~~~

Đây là đoạn Java 8 minh họa. Lần hai không gây exception chỉ vì future đã completed; nó báo `false`.

### 2.1. complete(null) hợp lệ

~~~java
CompletableFuture<String> nullable = new CompletableFuture<>();

nullable.complete(null);

System.out.println(nullable.isDone());   // true
System.out.println(nullable.join() == null); // true
~~~

**Không** dùng `join() == null` như tín hiệu "chưa có dữ liệu": future có thể đã hoàn thành bình thường bằng null. Muốn kiểm tra trạng thái completion, dùng `isDone()`; muốn thể hiện kết quả không có giá trị và có ý nghĩa nghiệp vụ, định nghĩa contract riêng như `Optional<T>`.

Với một lời hứa chỉ báo task hoàn tất:

~~~java
CompletableFuture<Void> signal = new CompletableFuture<>();

// Khi công việc thật sự hoàn thành thành công:
signal.complete(null);
~~~

Đoạn này minh họa **tín hiệu hoàn thành**, không có giá trị tính toán để trả về.

### 2.2. Không nhầm complete với completedFuture

~~~java
CompletableFuture<String> a = new CompletableFuture<>();
a.complete("DONE");

CompletableFuture<String> b =
        CompletableFuture.completedFuture("DONE");
~~~

Cả hai có thể đọc được `"DONE"` ngay. Khác biệt:

- `new CompletableFuture<>()` cho phép giữ một future pending để callback/logic sau đó chủ động gọi `complete`.
- `completedFuture(value)` tạo **một CompletableFuture đã hoàn thành** ngay khi khởi tạo; phù hợp khi bạn đã có kết quả.
- Gọi `b.complete("OTHER")` không làm thay kết quả của `b`; nó trả false.

Không tạo pending future rồi lập tức complete chỉ để thay thế `completedFuture` nếu mục tiêu đơn giản là có một giá trị đã biết.

### 2.3. isDone không đồng nghĩa success

`isDone()` trả true khi future hoàn thành theo bất kỳ cách phù hợp: bình thường, exception hoặc cancellation.

~~~java
CompletableFuture<Integer> future = new CompletableFuture<>();

future.complete(42);

boolean done = future.isDone(); // true
boolean failed = future.isCompletedExceptionally(); // false
boolean cancelled = future.isCancelled(); // false
~~~

Nếu chỉ cần biết future đã quyết định kết quả hay chưa, dùng `isDone()`. Nếu cần phân biệt success/exception/cancel, phải xét nhiều trạng thái hoặc xử lý bằng pipeline phù hợp.

## 3. completeExceptionally(Throwable ex): hoàn thành với lỗi

Chữ ký:

~~~java
public boolean completeExceptionally(Throwable ex)
~~~

Nó cố gắng hoàn thành future ở trạng thái **exceptional completion**:

- Khi future còn pending: lưu thông tin lỗi `ex`, trả `true`.
- Khi đã completed: trả `false` và **không sửa kết quả trước đó**.
- `ex` **không được null**; `completeExceptionally(null)` ném `NullPointerException`.
- Lỗi được chuyển qua các pipeline phụ thuộc theo hợp đồng `CompletionStage`, trừ khi stage sau đó xử lý và khôi phục.

Ví dụ:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

boolean first = result.completeExceptionally(
        new IllegalStateException("backend unavailable"));

boolean second = result.complete("TOO_LATE");

// first == true
// second == false
// result.isDone() == true
// result.isCompletedExceptionally() == true
~~~

Đây là **đoạn minh họa**. Gọi `completeExceptionally` không ném ngay `IllegalStateException` tại nơi gọi; nó **đánh dấu future hoàn thành với lỗi**. Lỗi sẽ xuất hiện khi consumer gọi `get`/`join` hoặc qua dependent stage.

### 3.1. Thứ tự ngược lại: normal thắng, exception thua

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

boolean normalWon = result.complete("SUCCESS");
boolean errorWon = result.completeExceptionally(
        new IllegalStateException("late error"));

// normalWon == true
// errorWon == false
// result.join().equals("SUCCESS") == true
~~~

Lỗi đến muộn không tự biến thành trạng thái lỗi của future. **Tuy nhiên**, một lỗi do tác vụ hoặc nguồn dữ liệu đến muộn vẫn có thể cần log, metric hoặc xử lý nghiệp vụ — không thể chỉ dựa vào future để bảo đảm mọi lỗi bên ngoài đều được lưu.

### 3.2. Vì sao completeExceptionally(null) không giống complete(null)?

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

future.complete(null); // Hợp lệ, hoàn thành bình thường.

// Phản ví dụ trên future khác:
// future2.completeExceptionally(null); // Ném NullPointerException.
~~~

`complete(null)` là success với payload null. `completeExceptionally(null)` không có throwable hợp lệ để biểu diễn failure nên bị từ chối; future chưa hoàn thành không tự nhận một lỗi null.

### 3.3. Chọn Throwable hợp lý

Dù chữ ký nhận `Throwable`, thực tế nên dùng exception mô tả nguyên nhân, chẳng hạn `TimeoutException`, `IOException` (nếu truyền qua boundary thích hợp), `IllegalStateException` hoặc custom exception của domain. Đừng hoàn thành lỗi bằng một đối tượng vô nghĩa chỉ để đánh dấu fail.

Nếu API công khai, xác định lỗi nào có thể xảy ra, liệu caller có thể retry không, có cần giữ nguyên cause không và có phải một completion bình thường mang object kiểu `Result<T,Error>` sẽ diễn đạt nghiệp vụ tốt hơn không.

## 4. Lỗi xuất hiện thế nào khi đọc Future?

Một CompletableFuture hoàn thành exceptional có thể được đọc bằng `get()` hoặc `join()`, nhưng **kiểu exception bên ngoài khác nhau**:

| Cách đọc | Kết quả khi completed bình thường | Kết quả khi exceptional |
| --- | --- | --- |
| `join()` | Trả `T` hoặc null | Thường ném `CompletionException` chứa nguyên nhân; cancellation có `CancellationException` |
| `get()` | Trả `T` hoặc null | Ném `ExecutionException` với cause gốc; có checked `InterruptedException` |
| `get(timeout, unit)` | Chờ tối đa thời hạn | Ngoài những exception của `get`, có thể ném `TimeoutException` nếu chờ quá hạn |
| `getNow(fallback)` | Trả giá trị nếu đã completed | Trả fallback khi còn pending, có thể ném exception nếu đã failed |
| `handle(...)` | Hàm nhận value + null error | Hàm nhận null value + Throwable, có thể chuyển thành giá trị khác |
| `exceptionally(...)` | Không chạy recovery | Chạy recovery khi exceptional và có thể trả giá trị thay thế |

Ví dụ xử lý `join`:

~~~java
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(new IllegalStateException("boom"));

try {
    failed.join();
} catch (CompletionException ex) {
    Throwable root = ex.getCause();
    System.out.println(root.getClass().getSimpleName());
    // IllegalStateException
}
~~~

Đây là **đoạn minh họa**, cần import `CompletionException`. Khi lỗi gốc đã là một `CompletionException`, cơ chế wrapping có thể giữ nguyên wrapper; đừng viết code chỉ trông đợi chính xác một lớp wrap trong mọi nguồn lỗi.

Ví dụ xử lý `get`:

~~~java
try {
    failed.get();
} catch (ExecutionException ex) {
    Throwable root = ex.getCause();
    // Xử lý nguyên nhân.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Trả trạng thái gián đoạn cho caller.
}
~~~

Đây là đoạn minh họa. `get` có checked interruption; khôi phục interrupt flag nếu đang thoát khỏi method thay vì nuốt ngầm.

### 4.1. Không tự thêm get() chỉ để xem lỗi trong một pipeline

Nếu logic cần tiếp tục bằng phép biến đổi asynchronous, các combinator như `handle` hoặc `exceptionally` thường rõ hơn việc gọi `join()` ngay trên executor thread rồi gây blocking.

~~~java
CompletableFuture<String> recovery = failed.exceptionally(
        ex -> "FALLBACK");

String usable = recovery.join();
// FALLBACK
~~~

**Điểm rất quan trọng:** `recovery` là **dependent stage mới** hoàn thành bình thường. `failed` vẫn hoàn thành exceptional; `exceptionally` **không sửa kết quả của future nguồn**.

## 5. Truyền kết quả tới dependent stages

Một trong những lý do mạnh nhất để dùng `CompletableFuture` là có thể đăng ký các bước xử lý trước hoặc sau completion.

### 5.1. Stage đăng ký trước completion

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> length =
        source.thenApply(String::length);

source.complete("DONE");

System.out.println(length.join()); // 4
~~~

`length` sẽ có kết quả 4 khi source hoàn thành bình thường. Trong ví dụ `String::length` không ném lỗi.

### 5.2. Stage đăng ký sau completion

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("DONE");

CompletableFuture<Integer> length =
        source.thenApply(String::length);

System.out.println(length.join()); // 4
~~~

Stage tạo sau khi future đã có kết quả vẫn hoạt động; không bị mất sự kiện completion như một callback listener được đăng ký quá muộn. **Không cần chủ động kiểm tra `isDone()` rồi quyết định có đăng ký hay không** trong những pipeline thông thường.

### 5.3. Lỗi nguồn khiến thenApply không thực thi logic chuyển đổi

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> derived =
        source.thenApply(String::length);

source.completeExceptionally(
        new IllegalStateException("source failed"));

// String::length KHÔNG được gọi với kết quả thất bại.
// derived cũng hoàn thành exceptional theo hợp đồng.
~~~

Nếu cần xác định đường hồi phục, gắn `exceptionally`, `handle` hoặc `whenComplete` theo đúng vai trò.

### 5.4. exceptionally: chỉ đường lỗi

~~~java
CompletableFuture<String> recovered =
        source.exceptionally(ex -> "DEFAULT");

// recovered có thể hoàn thành bình thường với "DEFAULT".
~~~

Đây là đoạn minh họa tiếp nối ví dụ failed source. Khi source thành công, `exceptionally` truyền giá trị bình thường qua mà không gọi recovery. Khi source failed, recovery function nhận Throwable và trả một `T` thay thế.

### 5.5. handle: xử lý cả success và error

~~~java
CompletableFuture<String> classification = source.handle(
        (value, error) -> error == null ? "SUCCESS" : "ERROR");
~~~

Trong ví dụ, `classification` hoàn thành bình thường thành `"ERROR"` nếu nguồn thất bại, miễn action không ném exception. Sự tồn tại của `classification` không khiến `source` đổi trạng thái.

**Đừng coi `error == null` luôn là kết quả success với non-null value.** Một future có thể hoàn thành bình thường bằng `null`. Khi đó `handle((value,error))` nhận cả hai tham số null.

### 5.6. whenComplete: quan sát, không phải lựa chọn chính để recovery

~~~java
CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error != null) {
                // Ghi metric hoặc log thất bại.
            }
        });
~~~

`whenComplete` thường dùng để quan sát kết quả hoặc giải phóng tài nguyên. Nếu action không ném lỗi, dependent stage giữ completion tương ứng nguồn. Nó **không tự biến exceptional thành success**. Để chuyển failed future thành value thay thế, dùng `exceptionally` hoặc `handle`.

Nếu callback của `whenComplete` tự ném lỗi, dependent stage có thể trở thành exceptional; khi nguồn vốn đã failed, nguyên nhân nguồn có quy tắc ưu tiên riêng. Hạn chế side effect phức tạp hoặc callback có thể throw trong observer.

## 6. Cạnh tranh hoàn thành giữa nhiều thread: điều gì được bảo đảm?

Đây là trọng tâm của bài. Giả sử hai nơi độc lập cùng muốn chốt **một CompletableFuture**:

- Thread A gọi `future.complete(value)`.
- Thread B gọi `future.completeExceptionally(error)`.

Hai lời gọi có thể xảy ra gần như đồng thời. **Không có cam kết thread A hay thread B phải thắng**. Tuy nhiên, API bảo đảm trạng thái completion của future chỉ bị xác lập thành công một lần bởi các thao tác hoàn thành thông thường.

### 6.1. Kết quả boolean thể hiện người thắng

~~~java
CompletableFuture<String> f = new CompletableFuture<>();

// Hai thread chạy cạnh tranh:
boolean wonA = f.complete("OK");
boolean wonB = f.completeExceptionally(
        new IllegalArgumentException("FAILED"));

// Khi đúng hai thao tác này tranh trên một future chưa completed
// và cả hai đã thực thi xong, đúng một boolean sẽ là true.
~~~

Đây là **minh họa logic concurrency**, không phải chương trình hai thread độc lập. Không nên gán trước giá trị `wonA` và `wonB` bằng một chuỗi cố định trong bài test thật: thứ tự phụ thuộc scheduling.

Khi thực sự chạy cạnh tranh:

- Nếu A thắng: `f.join()` trả `"OK"`, B nhận false.
- Nếu B thắng: `f.join()` ném `CompletionException`, A nhận false.
- `f.isDone()` là true sau khi cả hai thao tác kết thúc.
- Không có trạng thái trung gian mà future thành công rồi bị `completeExceptionally` bình thường ghi đè.

### 6.2. Race là nondeterministic, kiểm thử phải có invariant

Đừng viết bài test như:

~~~java
// Sai về mặt kiểm thử concurrency:
// assertEquals("OK", f.join()); // Tưởng thread A luôn thắng.
~~~

Dòng minh họa này có thể fail hợp lệ nếu B thắng. Thay vào đó, kiểm tra những bất biến:

1. Có đúng **một** lời gọi completion trả true trong hai người cạnh tranh.
2. Future đã hoàn thành.
3. Giá trị hoặc lỗi của future **phù hợp với lời gọi thắng**.
4. Lời gọi thua **không sửa được kết quả đã chốt**.
5. Không có dữ liệu shared mutable bị race ngoài chính future.

### 6.3. Dùng CountDownLatch để tạo cạnh tranh thật

Đoạn đầy đủ sẽ xuất hiện trong chương trình cuối bài. Nguyên tắc:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Runnable contender = () -> {
    ready.countDown();
    try {
        start.await();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
    // Thử complete hoặc completeExceptionally tại đây.
};
~~~

Đây là **đoạn mã minh họa**, cần import `CountDownLatch`, `InterruptedException` từ `java.lang`, và lớp java.util.concurrent phù hợp. Test đợi cả hai thread sẵn sàng rồi mở gate `start`, làm tăng cơ hội cạnh tranh mà **không cố ép một thread phải thắng**.

Trong code test, còn cần đợi `Future.get()` hoặc join của các thread thực hiện hoàn thành trước khi đọc kết quả tổng hợp; nếu không, bộ đếm winner có thể chưa cập nhật xong.

### 6.4. Atomic chỉ đảm bảo completion của CompletableFuture, không đảm bảo nghiệp vụ ngoài nó

Giả sử trước khi gọi `complete`, mỗi contender đã:

- Gửi email xác nhận.
- Ghi một bản ghi trong DB.
- Trừ tiền trong hệ thống thanh toán.

Dù chỉ một `complete` trả true, **các side effect xảy ra trước đó vẫn có thể đã thực hiện ở cả hai thread**. CompletableFuture không tự cung cấp transaction, lock, exactly-once delivery hoặc idempotency cho side effect ngoại vi.

Muốn một hành động nghiệp vụ chỉ chạy một lần, phải thiết kế cơ chế riêng như:

- Idempotency key tại service nhận.
- Unique constraint/transaction tại DB.
- Atomic state machine hoặc cơ chế phân quyền winner **trước side effect**.
- Phân tách rõ "thử chốt promise" và "thực hiện thay đổi dữ liệu".

**Chỉ một completion thắng không đồng nghĩa chỉ một task đã chạy.**

## 7. Cạnh tranh với tác vụ supplyAsync đang chạy

Một tình huống đặc biệt dễ hiểu sai:

~~~java
CompletableFuture<String> f =
        CompletableFuture.supplyAsync(() -> performWork());

// Trong lúc supplier còn chạy:
boolean won = f.complete("MANUAL");
~~~

Đây là **đoạn minh họa**, giả định có method `performWork()` và import `CompletableFuture`. Khi `complete("MANUAL")` thắng, nó chốt kết quả mà consumer nhìn thấy. Nhưng thao tác đó **không phải một lời hủy tác vụ supplier đang chạy**.

Khi supplier sau đó trả `"WORKER_RESULT"`, nó sẽ thử hoàn thành cùng CompletableFuture, nhưng giá trị đã bị chốt; việc hoàn thành từ supplier không ghi đè `"MANUAL"`.

### 7.1. Tác vụ có thể vẫn thực hiện side effect

Giả sử supplier gửi request, cập nhật trạng thái hoặc viết file. Nếu hoàn thành thủ công trước khi supplier kết thúc:

- Kết quả `f.join()` có thể là giá trị thủ công.
- Supplier vẫn có thể tiếp tục chạy tới khi tự kết thúc.
- Side effect trong supplier có thể vẫn xảy ra.
- Exception bên trong supplier đến sau có thể không trở thành exception của `f` nếu future đã hoàn thành bằng giá trị khác.

Do đó, đừng dùng `complete(...)` để "tắt" một task nặng, ngăn gửi request trùng hoặc hủy I/O. Điều khiển lifecycle/cancellation của tác vụ nguồn là **một bài toán khác**.

### 7.2. completeExceptionally cũng không tự dừng supplier

~~~java
CompletableFuture<String> f =
        CompletableFuture.supplyAsync(() -> performWork());

boolean accepted = f.completeExceptionally(
        new TimeoutException("service timeout"));
~~~

Đây là **đoạn minh họa**, cần `TimeoutException` và method `performWork()`. Future có thể báo lỗi sớm cho caller, nhưng supplier không được tự động ngắt chỉ vì `completeExceptionally`.

Khi cần cancel đúng nghĩa, ứng dụng phải quản lý riêng task handle, cooperative cancellation, interrupt hoặc timeout của I/O theo hợp đồng của công nghệ đang dùng. **`CompletableFuture.cancel(true)` cũng không bảo đảm interrupt underlying supplier**, như mục 9 giải thích.

### 7.3. Không suy diễn nguồn completion từ giá trị

Nếu một future được hoàn thành `"MANUAL"`, caller không tự biết liệu supplier đã chạy hay chưa, trừ khi ứng dụng thiết kế trạng thái/metric riêng. `CompletableFuture` lưu kết quả cuối, không phải một audit trail đầy đủ của tất cả nỗ lực completion.

## 8. Cancellation tham gia cuộc đua hoàn thành

`cancel(boolean mayInterruptIfRunning)` là một cách khác để hoàn thành `CompletableFuture` trong trạng thái bị hủy. Với CompletableFuture, cancellation được xử lý như một dạng exceptional completion với `CancellationException`.

~~~java
CompletableFuture<String> f = new CompletableFuture<>();

boolean cancelled = f.cancel(true);
boolean normalAfter = f.complete("TOO_LATE");

// cancelled == true, normalAfter == false.
// f.isCancelled() == true.
// f.isDone() == true.
// f.isCompletedExceptionally() == true.
~~~

**Quan trọng:** tham số `mayInterruptIfRunning` **không có tác dụng interrupt trong implementation CompletableFuture** theo Javadoc, vì nó không dùng interrupt làm cơ chế kiểm soát processing. Không được suy ra `cancel(true)` sẽ cắt ngay một tác vụ đang chạy qua `supplyAsync`.

### 8.1. CancellationException khi join

~~~java
try {
    f.join();
} catch (CancellationException ex) {
    // Cancellation được phản ánh tại caller.
}
~~~

Đây là **đoạn minh họa** trên future đã cancel ở ví dụ trước. Với **future nguồn bị cancel trực tiếp**, `join()` có thể ném trực tiếp `CancellationException`. Với **dependent stage** phát sinh từ future đó, lỗi có thể được gói bởi `CompletionException`; xử lý đúng ngữ nghĩa khi truyền qua pipeline.

### 8.2. Cancellation không đồng nhất với generic failure

Một `TimeoutException` từ `completeExceptionally` nói một promise hết hạn theo chính sách ứng dụng. `CancellationException` nói luồng logic đã chọn trạng thái canceled. Hai loại có thể yêu cầu metric, retry hoặc logging khác nhau.

`isCompletedExceptionally()` là phép kiểm tra rộng về exceptional completion, có thể đúng cả với cancelled future; nếu cần phân loại cancellation, kiểm tra `isCancelled()` hoặc xử lý loại exception thích hợp.

### 8.3. Đừng coi cancel là điều khiển exactly-once

Nếu một task đã gửi request ra ngoài trước khi nhận cancellation, request đó có thể vẫn xử lý xong. Cancellation của future không làm giao dịch bên ngoài được rollback. Logic nghiệp vụ phải thiết kế idempotency và transaction độc lập.

## 9. obtrudeValue/obtrudeException: ngoại lệ đối với quy tắc "kết quả không đổi"

Java 8 có hai method chuyên biệt:

~~~java
future.obtrudeValue(value);
future.obtrudeException(throwable);
~~~

Đây là **đoạn minh họa với `future` đã có**, không phải lời gọi thông thường nên dùng trong business flow.

- `obtrudeValue` **ép** các lần `get`/`join` tiếp theo nhìn thấy giá trị được đưa vào.
- `obtrudeException` ép các lần đọc tiếp theo thấy exceptional completion.
- Khác `complete` và `completeExceptionally`, hai method này không thử thắng race rồi trả boolean; chúng là cơ chế **ghi đè cưỡng bức** đặc biệt.
- Những dependent stages đã được kích hoạt hoặc đã hoàn thành dưới kết quả cũ **có thể không đồng nhất** với kết quả mới.

### 9.1. Hệ quả "split brain" giữa future gốc và dependents

~~~java
CompletableFuture<String> original =
        CompletableFuture.completedFuture("FIRST");

CompletableFuture<Integer> length =
        original.thenApply(String::length);

// length đã có 5 từ "FIRST".
original.obtrudeValue("LONGER");

// original.join() bây giờ có thể là "LONGER".
// length.join() vẫn có thể là 5; không tự tính lại.
~~~

Đây là **đoạn minh họa** để giải thích rủi ro. Đừng dùng `obtrudeValue` làm thao tác cập nhật kết quả bình thường. Nó có thể tạo các pipeline phụ thuộc nhìn thấy lịch sử khác nhau, phá giả định của người đọc mã.

Nếu phát hiện một bug sau khi future hoàn tất, thường nên tạo **một future mới** hoặc xử lý retry/correction ở tầng nghiệp vụ. Chỉ cân nhắc obtrude trong những tình huống recovery đặc biệt được hiểu rõ và kiểm thử kỹ.

### 9.2. Không chọn obtrude để "sửa" người thua race

Nếu một completion đến muộn, nó nên nhận `false`; không dùng `obtrudeValue` chỉ để biến người đến muộn thành winner. Điều đó làm mất tính nhất quán của dependent stages và không rollback side effect đã chạy.

## 10. Thứ tự callback và mô hình thread

### 10.1. Non-async callbacks không có thread cố định

Những method như `thenApply`, `thenAccept`, `thenRun`, `whenComplete` có biến thể **không có hậu tố Async**. Với CompletableFuture, action của dependent stage không-async có thể chạy trong thread thực hiện completion hoặc một thread khác đang gọi completion, tùy ngữ cảnh triển khai.

**Không dựa vào tên thread hoặc thứ tự thời gian của callback** để quyết định correctness. Đặc biệt, không viết UI hoặc transaction logic giả định callback của `thenApply` luôn chạy trên main thread.

### 10.2. Async callbacks dùng executor

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<Integer> transformed =
            CompletableFuture.completedFuture(3)
                    .thenApplyAsync(n -> n * 2, executor);

    System.out.println(transformed.join()); // 6
} finally {
    executor.shutdown();
}
~~~

Đây là **đoạn minh họa Java 8**, cần import `ExecutorService`, `Executors` và `CompletableFuture`.

`thenApplyAsync` với explicit executor cho ứng dụng quyền chọn môi trường chạy action. Nhưng lựa chọn executor **không thay đổi** luật chỉ một completion được chấp nhận của future nguồn. Nếu không truyền executor, các async method thường dựa trên cơ chế executor mặc định của CompletableFuture (thường liên quan ForkJoin common pool), với chi tiết phụ thuộc runtime.

### 10.3. Hạn chế blocking và deadlock do thiết kế executor

Nếu gọi `join()` bên trong một task trên executor có đúng một worker, trong khi task cần giải quyết future lại cũng được submit vào **chính executor đó**, có thể tạo deadlock do worker đang bị chiếm bởi việc chờ.

Không thay toàn bộ luồng bất đồng bộ bằng chuỗi `join` blocking. Ưu tiên `thenCompose`/`thenCombine`/`handle` để nối pipeline; chỉ blocking tại boundary phù hợp như command-line main, test hoặc thread được thiết kế riêng cho việc chờ.

### 10.4. Callback chạy nhanh không đồng nghĩa thứ tự in được bảo đảm

Ngay cả khi hai stage đều phụ thuộc cùng future, đừng giả định chúng luôn in log theo thứ tự đăng ký. Nếu cần xác định thứ tự nghiệp vụ giữa các bước, hãy **chain các stage** thay vì đăng ký hai callback độc lập:

~~~java
CompletableFuture<Void> ordered =
        source.thenAccept(value -> stepOne(value))
                .thenRun(() -> stepTwo());
~~~

Đây là **đoạn minh họa**, giả định có các method `stepOne`, `stepTwo` và biến `source`. Khi stage đầu thành công, stage tiếp theo chạy theo dependency chain. Không hứa thứ tự giữa những sibling callbacks không có quan hệ phụ thuộc.

## 11. Timeout thủ công trong Java 8 là một cuộc đua completion

Mô hình phổ biến:

- Tác vụ thật cố hoàn thành với result.
- Một timer cố hoàn thành exceptional với `TimeoutException`.
- Ai đến **trước** theo trạng thái atomic sẽ được chấp nhận.
- Người đến sau nhận `false`.
- Thắng timeout **không tự hủy tác vụ thật**.

Java 8 có thể hiện thực timer bằng `ScheduledExecutorService`:

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
CompletableFuture<String> result = new CompletableFuture<>();

ScheduledFuture<?> timeoutTask = scheduler.schedule(
        () -> result.completeExceptionally(
                new TimeoutException("deadline reached")),
        2, TimeUnit.SECONDS);

result.whenComplete((value, error) ->
        timeoutTask.cancel(false));

// Bên ngoài ví dụ còn cần đóng scheduler và quản lý nguồn tác vụ.
// scheduler.shutdown();
~~~

Đây là **đoạn minh họa** (không phải chương trình tự chạy): cần `ScheduledExecutorService`, `Executors`, `ScheduledFuture`, `CompletableFuture`, `TimeoutException`, `TimeUnit`. Timer có thể thắng hoặc thua tùy nguồn kết quả và scheduling. `whenComplete` được dùng để cancel timer không cần thiết sau khi future đã hoàn thành.

Khi dùng thật, phải bảo đảm scheduler và resource được giải phóng, đặc biệt với nhiều request. Cần một hệ thống timer có khả năng scale, không tạo thread riêng cho từng request nếu không cần thiết.

### 11.1. Thận trọng với các method mới hơn Java 8

Trong JDK mới, `orTimeout`, `completeOnTimeout` và `completeAsync` cũng tồn tại. Nhưng chúng **không phải API có trong Java 8 gốc**. Nếu bài học hoặc hệ thống phải chạy với `--release 8`, hãy dùng cơ chế Java 8 như `ScheduledExecutorService` hoặc nâng target có chủ đích.

**Hướng dẫn đang áp dụng hiện nay:** Khi hệ thống đã dùng JDK hiện đại, có thể dùng API mới phù hợp; khi code buộc tương thích Java 8, không gọi các method được giới thiệu sau Java 8 và tưởng nó sẽ biên dịch.

### 11.2. Timing là một quyết định nghiệp vụ

Nếu task và timer hoàn thành gần như đồng thời, kết quả nào thắng có thể không dự đoán được. Nếu nghiệp vụ yêu cầu strict deadline theo clock (ví dụ đã qua deadline thì luôn tính fail ngay cả khi callback result đến cùng thời điểm), cần kiểm tra timestamp/deadline trong một cơ chế quyết định duy nhất, không chỉ dựa vào thứ tự scheduling của hai runnable.

## 12. Ví dụ Java 8 hoàn chỉnh, có cạnh tranh thật và stdout ổn định

Chương trình sau biểu diễn:

1. Completion bình thường rồi thử completion lần hai.
2. Stage được đăng ký trước và sau khi source đã completed.
3. Completion exceptional, `join`/`get` exception, recovery.
4. `complete(null)` hợp lệ, `completeExceptionally(null)` bị từ chối.
5. **Hai thread thực sự cạnh tranh** giữa normal và exceptional; không phụ thuộc thread nào thắng.
6. Cancellation thắng normal completion đến muộn.
7. Manual `complete` thắng khi supplier bất đồng bộ **đã bắt đầu nhưng chưa kết thúc**; supplier vẫn chạy mã.

Lưu thành **CompletionRaceDemo.java**. Toàn bộ method được dùng có từ Java 8. Không in tên worker thread hay giá trị winner ngẫu nhiên; stdout chỉ in các invariant ổn định.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class CompletionRaceDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> normal = new CompletableFuture<>();
        CompletableFuture<Integer> dependent = normal.thenApply(String::length);
        System.out.println("normal first = " + normal.complete("DONE"));
        System.out.println("normal second = " + normal.complete("IGNORED"));
        System.out.println("normal join = " + normal.join());
        System.out.println("dependent before = " + dependent.join());
        System.out.println("dependent after = "
                + normal.thenApply(String::length).join());

        CompletableFuture<String> failed = new CompletableFuture<>();
        System.out.println("exception first = "
                + failed.completeExceptionally(
                        new IllegalStateException("boom")));
        System.out.println("normal after exception = "
                + failed.complete("TOO_LATE"));
        System.out.println("failed flag = "
                + failed.isCompletedExceptionally());
        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("join cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
        try {
            failed.get();
        } catch (ExecutionException ex) {
            System.out.println("get cause = "
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("recovered = "
                + failed.exceptionally(ex -> "FALLBACK").join());

        CompletableFuture<String> nullable = new CompletableFuture<>();
        System.out.println("complete null = " + nullable.complete(null));
        System.out.println("nullable join null = " + (nullable.join() == null));

        CompletableFuture<String> invalid = new CompletableFuture<>();
        try {
            invalid.completeExceptionally(null);
        } catch (NullPointerException ex) {
            System.out.println("null throwable rejected = true");
        }
        System.out.println("invalid still pending = " + !invalid.isDone());

        CompletableFuture<String> race = new CompletableFuture<>();
        CompletableFuture<String> outcome = race.handle(
                (value, error) -> error == null ? "NORMAL" : "ERROR");
        AtomicInteger successes = new AtomicInteger(0);
        AtomicReference<String> winningKind = new AtomicReference<>();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService competitors = Executors.newFixedThreadPool(2);
        try {
            Future<?> normalTask = competitors.submit(() -> {
                ready.countDown();
                await(start);
                if (race.complete("VALUE")) {
                    successes.incrementAndGet();
                    winningKind.set("NORMAL");
                }
            });
            Future<?> errorTask = competitors.submit(() -> {
                ready.countDown();
                await(start);
                if (race.completeExceptionally(
                        new IllegalArgumentException("error"))) {
                    successes.incrementAndGet();
                    winningKind.set("ERROR");
                }
            });
            await(ready);
            start.countDown();
            normalTask.get();
            errorTask.get();
        } finally {
            start.countDown();
            competitors.shutdown();
        }
        System.out.println("race successes = " + successes.get());
        System.out.println("race settled = " + race.isDone());
        System.out.println("race winner consistent = "
                + winningKind.get().equals(outcome.join()));

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        System.out.println("cancel first = " + cancelled.cancel(true));
        System.out.println("complete after cancel = "
                + cancelled.complete("LATE"));
        System.out.println("isCancelled = " + cancelled.isCancelled());
        System.out.println("cancel exceptional = "
                + cancelled.isCompletedExceptionally());
        try {
            cancelled.join();
        } catch (CancellationException ex) {
            System.out.println("join cancelled = CancellationException");
        }

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean workerRan = new AtomicBoolean(false);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        CompletableFuture<String> running = CompletableFuture.supplyAsync(() -> {
            started.countDown();
            await(release);
            workerRan.set(true);
            return "SUPPLIER_RESULT";
        }, worker);
        try {
            await(started);
            boolean won = running.complete("MANUAL");
            release.countDown();
            worker.shutdown();
            if (!worker.awaitTermination(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not stop");
            }
            System.out.println("manual completion won = " + won);
            System.out.println("manual result = " + running.join());
            System.out.println("supplier code still ran = " + workerRan.get());
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }
}
~~~

Biên dịch với JDK hỗ trợ tùy chọn `--release 8`:

~~~bash
javac --release 8 CompletionRaceDemo.java
java CompletionRaceDemo
~~~

**Stdout đã được biên dịch và chạy kiểm tra:**

~~~text
normal first = true
normal second = false
normal join = DONE
dependent before = 4
dependent after = 4
exception first = true
normal after exception = false
failed flag = true
join cause = IllegalStateException
get cause = IllegalStateException
recovered = FALLBACK
complete null = true
nullable join null = true
null throwable rejected = true
invalid still pending = true
race successes = 1
race settled = true
race winner consistent = true
cancel first = true
complete after cancel = false
isCancelled = true
cancel exceptional = true
join cancelled = CancellationException
manual completion won = true
manual result = MANUAL
supplier code still ran = true
~~~

### 12.1. Vì sao race in kết quả xác định?

Hai contender cùng đợi `start` trước khi thử completion. Thread thắng và thread thua **không được dự đoán trước**. Chương trình chỉ in:

- `race successes = 1`: chính xác một lời gọi trả true.
- `race settled = true`: future cuối cùng đã completed.
- `race winner consistent = true`: outcome quan sát qua `handle` phù hợp với loại completion mà contender thắng đã ghi nhận.

Sau `normalTask.get()` và `errorTask.get()`, cả hai runnable đã kết thúc nên các phép đọc biến `AtomicInteger`/`AtomicReference` dùng để kiểm tra là hợp lệ. Kết quả không phụ thuộc thread được JVM chọn hay thứ tự log. **Không dùng `Thread.sleep` để "cố" tạo race**, vì sleep chỉ là thời gian tương đối và không tạo rào chắn synchronization.

### 12.2. Vì sao manual completion không dừng supplier?

`started` chỉ được giảm sau khi worker đã bắt đầu chạy lambda. Main chờ `started`, gọi `running.complete("MANUAL")` khi worker còn đợi `release`, sau đó giải phóng worker. Worker tiếp tục đặt `workerRan = true` và trả `SUPPLIER_RESULT`. Future đã completed bằng `MANUAL` nên kết quả supplier đến sau không thay thế.

Đây là bằng chứng riêng trong chương trình rằng **completion của future** và **lifecycle/side effect của task nguồn** là hai chiều khác nhau.

### 12.3. Vì sao result của failed future vẫn lỗi sau exceptionally?

`exceptionally` tạo **future mới** đại diện cho recovery, không sửa source. Chương trình gọi `failed.exceptionally(...).join()` và nhận `FALLBACK`, nhưng `failed.isCompletedExceptionally()` vẫn true, đúng với kết quả sau `completeExceptionally`.

## 13. Các lỗi phổ biến và cách khắc phục

### Lỗi 1 — Nghĩ complete là setter thay giá trị

Sau khi future completed, `complete(other)` trả false và không sửa giá trị. **Sửa:** kiểm tra boolean và định nghĩa ai sở hữu quyền giải quyết promise.

### Lỗi 2 — Bỏ qua boolean return trong trường hợp nhiều nguồn completion

Khi có hai callback/network response/timer, bỏ qua return khiến code log sai là “đã hoàn thành” cho cả hai. **Sửa:** ghi nhận winner bằng boolean và chỉ gắn side effect winner-specific đúng chỗ thiết kế.

### Lỗi 3 — Cho rằng completeExceptionally tự ném exception tại nơi gọi

Nó thường **lưu Throwable làm completion outcome**. Consumer đọc future bằng `join/get` hoặc dependent stage sẽ gặp exceptional completion. **Sửa:** kiểm tra outcome thay vì chờ một exception từ chính `completeExceptionally(ex)` (trừ lỗi gọi API không hợp lệ, như `ex == null`).

### Lỗi 4 — Gọi completeExceptionally(null)

`Throwable` không được null. **Sửa:** tạo exception có ý nghĩa; nếu đây là một kết quả success không giá trị, dùng `complete(null)` theo contract.

### Lỗi 5 — Dùng isDone làm dấu hiệu thành công

`isDone` true cả khi completed exceptionally hoặc cancelled. **Sửa:** xử lý result/exception hoặc xét `isCompletedExceptionally` và `isCancelled` nếu cần.

### Lỗi 6 — Giả định join và get ném cùng loại exception

`join` thường bọc lỗi trong `CompletionException`, còn `get` dùng `ExecutionException` và checked interruption. **Sửa:** chọn API và tầng catch đúng.

### Lỗi 7 — Dùng complete để dừng một supplier đang chạy

`complete` chỉ cố quyết định outcome của future, không hủy tác vụ. **Sửa:** thiết kế cancellation/cooperation hoặc quản lý task handle/executor riêng.

### Lỗi 8 — Nghĩ cancel(true) chắc chắn interrupt tác vụ CompletableFuture

Trong `CompletableFuture`, tham số interrupt không vận hành như một cơ chế stop underlying computation. **Sửa:** không dựa vào cancel để rollback I/O hoặc ngăn side effect đang chạy.

### Lỗi 9 — Cho rằng người đến sau thắng bằng completeExceptionally

Kết quả chỉ được xác lập một lần bởi các completion thông thường. **Sửa:** dùng boolean return để phân biệt người thắng/thua và xử lý late error theo nghiệp vụ nếu cần.

### Lỗi 10 — Viết test concurrency đòi thread A luôn thắng

Scheduling không xác định. **Sửa:** test invariant “chỉ một completion thắng”, “outcome khớp winner” thay vì assert chính xác thread thắng.

### Lỗi 11 — Ghi side effect trước khi quyết định winner

Hai contender có thể cùng gửi email hoặc ghi DB trước khi chỉ một `complete` thành công. **Sửa:** thiết kế idempotency/transaction và quyết định ownership trước side effect khi có thể.

### Lỗi 12 — Dùng khi source completed rồi vẫn bỏ qua dependent stages

Có thể đăng ký `thenApply` hoặc `handle` cả trước lẫn sau completion. **Sửa:** dùng `CompletionStage` trực tiếp; không cần một polling loop kiểm tra `isDone`.

### Lỗi 13 — Nghĩ exceptionally sửa future nguồn

`exceptionally` tạo dependent stage recovery, source vẫn exceptional. **Sửa:** giữ reference tới stage đã recovery nếu caller muốn đọc giá trị fallback.

### Lỗi 14 — Dùng whenComplete để phục hồi lỗi bằng return value

`whenComplete` dùng `BiConsumer` và không trả giá trị thay thế; return value của lambda là void. **Sửa:** dùng `handle`/`exceptionally` khi cần chuyển failed thành success.

### Lỗi 15 — Không phân biệt null success với missing result

`complete(null)` hợp lệ. **Sửa:** dùng `isDone` hoặc result type để biểu diễn trạng thái; không dùng payload null làm tín hiệu Future còn pending.

### Lỗi 16 — Giả định callback không-Async luôn chạy trong cùng một thread

JDK không cam kết thread cố định cho dependent action non-async. **Sửa:** nếu cần thread/executor cụ thể, dùng biến thể Async với explicit executor và tránh giả định lịch callback.

### Lỗi 17 — Blocking join trong single-thread executor gây deadlock

Nếu task cần giải quyết future cũng nằm trong executor bị chiếm bởi thread đang chờ join, không có worker để chạy tiếp. **Sửa:** dùng composition không blocking và tránh dependency cycle.

### Lỗi 18 — Dùng obtrudeValue để sửa kết quả muộn

`obtrudeValue` ép kết quả mới nhưng dependents đã tính theo kết quả cũ có thể không tính lại. **Sửa:** tránh cơ chế này trong flow thông thường; tạo future mới cho retry/correction.

### Lỗi 19 — Bỏ quên việc dừng scheduler/executor trong test

Thread không dừng có thể giữ tiến trình sống hoặc gây rò resource. **Sửa:** `shutdown`/`shutdownNow` trong `finally` khi ứng dụng sở hữu executor; đóng tài nguyên theo lifecycle.

### Lỗi 20 — Dùng timeout Java 9+ khi mục tiêu Java 8

`orTimeout`, `completeOnTimeout`, `completeAsync` không có trong Java 8. **Sửa:** nếu target Java 8 thì dùng scheduler/cơ chế phù hợp, hoặc nâng baseline JDK và khai báo rõ.

### Lỗi 21 — Nhầm exceptional completion với cancellation

Cả hai thuộc nhóm không thành công; `CancellationException` có nghĩa riêng và `isCancelled` phục vụ kiểm tra cụ thể. **Sửa:** phân loại outcome theo ngữ nghĩa, tránh biến mọi lỗi thành retry giống nhau.

### Lỗi 22 — Cho rằng "chỉ một completion thắng" đồng nghĩa exactly-once processing

API chỉ bảo vệ **một future**. Nó không bảo đảm tác vụ nền chạy một lần, side effect ngoài hệ thống một lần hoặc message được tiêu thụ đúng một lần. **Sửa:** dựa vào idempotency key, unique DB key, transaction và cơ chế queue phù hợp.

## 14. Bảng chọn API theo mục tiêu

| Bạn muốn | API phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Chốt giá trị nếu chưa completed | `complete(value)` | Boolean true nếu chốt được |
| Chốt lỗi nếu chưa completed | `completeExceptionally(error)` | Throwable khác null |
| Tạo ngay một future đã có giá trị | `completedFuture(value)` | Không cần new + complete |
| Đăng ký biến đổi khi success | `thenApply`/`thenCompose` | Không chạy action bình thường nếu source failed |
| Chuyển failure thành fallback | `exceptionally` | Tạo stage mới; source vẫn lỗi |
| Thống nhất xử lý success/error | `handle` | Nhận cả value và error |
| Quan sát completion mà không chủ động recover | `whenComplete` | Không phải recovery operator |
| Đọc kết quả, chấp nhận blocking | `get`/`join` | Khác exception wrapping; quản lý blocking |
| Đợi với timeout khi đọc | `get(timeout,unit)` | Timeout của lệnh chờ không tự hủy supplier |
| Chủ động ra tín hiệu cancellation | `cancel(...)` | Không bảo đảm interrupt task đang chạy |
| Thực thi dependent action trên executor | `thenApplyAsync(...,executor)` | Không thay đổi luật completion winner |
| Hết hạn promise trên Java 8 | `ScheduledExecutorService` + `completeExceptionally` | Completion race, quản lý timer và nguồn tác vụ |
| Ép thay kết quả dù đã completed | `obtrudeValue`/`obtrudeException` | Rủi ro trạng thái dependents không đồng nhất; tránh dùng thông thường |

## 15. Checklist triển khai và kiểm thử

### 15.1. Khi thiết kế CompletableFuture thủ công

1. Ai **tạo** future? Ai giữ reference có quyền gọi `complete`?
2. Có bao nhiêu nguồn có thể hoàn thành? Callback chính, timeout, cancel, retry, shutdown?
3. Khi nguồn A thắng, nguồn B đến muộn có cần log hay metric riêng không?
4. Có cần xử lý **lỗi đến muộn** mà future không thể ghi đè không?
5. `complete(null)` có ý nghĩa nghiệp vụ hợp lệ không?
6. Đối tượng `Throwable` có đảm bảo non-null không?
7. Đường success/exception/cancel được consumer phân biệt ra sao?
8. Task thật có đang chạy dù future đã completed không?
9. Ai chịu trách nhiệm ngừng/giải phóng task, network call hoặc executor?
10. Side effect ngoài future có idempotency hoặc transaction bảo vệ không?
11. Dependent stage sẽ dùng `thenApply`, `handle`, `whenComplete` hay `exceptionally`?
12. Có callback blocking hoặc phụ thuộc vòng tròn gây deadlock không?
13. Có cần explicit Executor cho dependent stages không?
14. Testing có kiểm tra bất biến concurrency, không giả định winner cố định không?
15. Đã test cạnh tranh giữa normal/exception/cancel và timeout chưa?
16. Có cơ chế trace để phân biệt **winner** với **attempt đến muộn**?
17. Có thật sự cần obtrude hay có thể dùng future mới?
18. Nếu target Java 8, đã tránh method được thêm vào JDK 9+ chưa?

### 15.2. Các trường hợp unit/integration test nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| Future pending nhận `complete("OK")` | true và `join()=="OK"` |
| Gọi complete lần hai | false; kết quả đầu không đổi |
| `complete(null)` | true, `join()==null`, `isDone` true |
| `completeExceptionally(error)` | true; `isCompletedExceptionally` true |
| Gọi normal sau exception | false; exception vẫn là outcome |
| Gọi exception sau normal | false; normal vẫn là outcome |
| `completeExceptionally(null)` | `NullPointerException`; pending future chưa completed |
| `join` trên failed future | `CompletionException` hoặc loại exception theo hợp đồng |
| `get` trên failed future | `ExecutionException` với cause |
| `exceptionally` sau fail | Stage mới trả fallback |
| `whenComplete` observer không throw | Completion vẫn được truyền tới stage kế |
| Dependent đăng ký trước completion | Kích hoạt sau khi source completed |
| Dependent đăng ký sau completion | Kích hoạt được; không bỏ sót kết quả |
| Hai thread normal/exception tranh | Đúng một winner; outcome khớp |
| Cancel thắng rồi gọi complete | Complete trả false; canceled status |
| Supplier đã bắt đầu + manual complete | Supplier vẫn có thể chạy, future giữ manual outcome |
| Timeout timer so với result | Chỉ một completion bình thường được chấp nhận |
| Long-running executor | Được shutdown và không rò thread |
| Repeated concurrency test | Bất biến ổn định qua nhiều vòng, không dựa winner |

### 15.3. Một phương pháp test race có ý nghĩa

1. Tạo một `CompletableFuture` chưa completed.
2. Tạo hai contender trên hai thread thật.
3. Dùng `CountDownLatch` để xác nhận cả hai đã chuẩn bị.
4. Mở cùng gate để chúng thử `complete`/`completeExceptionally`.
5. Đợi cả hai contender kết thúc bằng `Future.get()`.
6. Đếm return value `true` bằng `AtomicInteger`, kỳ vọng đúng 1.
7. So actual outcome với contender thắng, không đoán thread.
8. Lặp nhiều vòng nếu cần stress test; không dùng một lần thành công để kết luận race-free trong hệ thống toàn bộ.

## 16. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Hai thread cùng gọi `complete("A")` và `completeExceptionally(ex)` trên một pending future. Ai thắng?

**Đáp án:** Không thể dự đoán theo tên thread hay thứ tự trong source code. Một completion thông thường được chấp nhận trước; các lời gọi sau trả false.

**Câu 2.** `complete("OK")` gọi lại lần hai với `"NEW"` có sửa giá trị không?

**Đáp án:** Không. Lần hai trả false và kết quả đầu được giữ.

**Câu 3.** `completeExceptionally(ex)` có ném `ex` trực tiếp cho caller không?

**Đáp án:** Không. Nó cố đặt trạng thái future là exceptional; consumer gặp lỗi khi đọc hoặc trong pipeline, không phải tại nơi gọi method, trừ lỗi input API.

**Câu 4.** `completeExceptionally(null)` làm gì?

**Đáp án:** Ném `NullPointerException` vì throwable bắt buộc khác null. Một pending future không tự hoàn thành vì lời gọi không hợp lệ.

**Câu 5.** `complete(null)` có hợp lệ không?

**Đáp án:** Có. Future hoàn thành bình thường với null; `isDone()` true.

**Câu 6.** `isDone()` có chứng minh future thành công không?

**Đáp án:** Không. Exception và cancellation cũng khiến `isDone()` true.

**Câu 7.** Vì sao `join()` và `get()` trên failed future có cách bắt lỗi khác nhau?

**Đáp án:** `join` dùng unchecked `CompletionException` trong nhiều đường failure; `get` dùng checked `ExecutionException` và có `InterruptedException`.

**Câu 8.** `exceptionally` có đổi một `failed` source thành success không?

**Đáp án:** Không. Nó tạo **dependent stage mới** có thể hoàn thành bằng fallback; source không bị sửa.

**Câu 9.** `whenComplete` có phải operator phù hợp nhất để trả value fallback không?

**Đáp án:** Không. Dùng `handle` hoặc `exceptionally`; `whenComplete` thường dùng để quan sát completion.

**Câu 10.** Nếu manual `complete` thắng khi `supplyAsync` vẫn chạy, supplier có được dừng tự động không?

**Đáp án:** Không. Nó có thể tiếp tục chạy và có side effect, nhưng kết quả đến sau không thay thế future đã completed.

**Câu 11.** `cancel(true)` có bảo đảm interrupt một supplier CompletableFuture không?

**Đáp án:** Không. Theo hợp đồng CompletableFuture, tham số `mayInterruptIfRunning` không dùng để điều khiển interruption của nguồn công việc.

**Câu 12.** Kết quả của hai contender phải được test thế nào nếu cả hai có thể thắng?

**Đáp án:** Test đúng một boolean true, source completed, outcome khớp người thắng; không assert một người cụ thể thắng.

**Câu 13.** Gọi `complete` thành công có bảo đảm task bên ngoài chỉ gửi một email không?

**Đáp án:** Không. Future quản lý trạng thái completion, không bảo đảm exactly-once side effect; cần idempotency hoặc transaction.

**Câu 14.** Dùng `obtrudeValue` để sửa kết quả sau complete có an toàn cho dependent stages không?

**Đáp án:** Không nhất thiết. Dependents đã chạy với kết quả cũ có thể không tính lại, gây kết quả không nhất quán.

**Câu 15.** Có thể đăng ký `thenApply` sau khi source completed không?

**Đáp án:** Có. Stage vẫn xử lý kết quả đã chốt; completion không bị "bỏ lỡ" như sự kiện chỉ phát một lần.

**Câu 16.** `completeAsync` và `orTimeout` có trong Java 8 gốc không?

**Đáp án:** Không. Đây là những method được thêm sau Java 8; nếu target Java 8 cần giải pháp dựa trên API Java 8.

**Câu 17.** Nếu một timer gọi `completeExceptionally` thắng trước callback success, callback success có sửa future thành bình thường không?

**Đáp án:** Không; callback success gọi `complete` sẽ nhận false. Tuy nhiên, tác vụ/side effect ngoài future vẫn cần quản lý riêng.

**Câu 18.** Khi muốn lấy kết quả đã có mà không chờ, `getNow(fallback)` có luôn trả fallback nếu future failed không?

**Đáp án:** Không. Khi future đã failed, `getNow` có thể ném exceptional completion; fallback chỉ dành cho trạng thái còn pending.

## 17. Tổng kết

- **`complete(value)`** thử hoàn thành bình thường; **`completeExceptionally(error)`** thử hoàn thành exceptional. Cả hai trả boolean cho biết lời gọi có **được chấp nhận** hay không.
- **Chỉ một completion thông thường thắng** trên cùng pending CompletableFuture; completion đến muộn không sửa kết quả.
- **`complete(null)` hợp lệ**, còn **`completeExceptionally(null)` ném NullPointerException**.
- **`isDone` không đồng nghĩa success**. `isCompletedExceptionally` phản ánh kết quả bất thường; cancellation có trạng thái riêng.
- **`get`/`join` khác cách biểu diễn exception**; dependent stages có thể hồi phục bằng `exceptionally`/`handle` hoặc quan sát qua `whenComplete`.
- **Dependent stages đăng ký cả trước và sau completion đều được xử lý** theo hợp đồng.
- **Race cần test invariant**, không giả định thread nào thắng. `CountDownLatch` và `AtomicInteger` giúp xác minh điều đó.
- **Hoàn thành future không dừng supplier** đang chạy và không rollback side effect. `cancel(true)` cũng không bảo đảm interrupt một task CompletableFuture.
- **`obtrudeValue`/`obtrudeException` là override đặc biệt** có rủi ro dependents không đồng nhất; không dùng trong flow thông thường.
- **Timeout trên Java 8** có thể tạo bằng scheduler và cạnh tranh với result; quản lý lifecycle riêng.
- Các API chính trong bài vẫn còn áp dụng trên Java hiện đại. Tránh tự giả định thread, thứ tự callback hoặc exactly-once behavior từ một boolean completion.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — CompletableFuture: complete, completeExceptionally, cancel, obtrude](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 8 — CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 8 — Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html)
- [Oracle Java SE 8 — CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html)
- [Oracle Java SE 8 — ExecutorService](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 8 — ScheduledExecutorService](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ScheduledExecutorService.html)
- [Oracle Java SE 25 — CompletableFuture (API hiện hành)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
