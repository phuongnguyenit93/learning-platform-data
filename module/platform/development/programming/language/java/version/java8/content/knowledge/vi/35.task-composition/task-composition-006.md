# CompletableFuture.exceptionally và phục hồi lỗi khi ghép tác vụ trong Java

## 1. Vì sao cần xử lý lỗi ngay trong chuỗi tác vụ?

`CompletableFuture` cho phép viết một chuỗi tính toán mà một bước chỉ chạy sau khi bước trước hoàn thành:

```java
CompletableFuture<Integer> result =
    CompletableFuture.completedFuture("42")
        .thenApply(Integer::parseInt)
        .thenApply(n -> n * 2);
// result.join() == 84
```

Đây là snippet dùng `import java.util.concurrent.CompletableFuture;`. Khi bước parse gặp `"abc"`, `Integer.parseInt` ném `NumberFormatException`; kết quả của stage đó **hoàn thành bất thường**, và những stage chỉ dành cho nhánh thành công phía sau không tự động chạy logic thành công. Nếu không xử lý, lời gọi `join()` ở cuối sẽ báo lỗi, thường qua `CompletionException`.

Với chuỗi đồng bộ, ta có thể hình dung `try/catch`. Với `CompletableFuture`, cách thường dùng để **biến một failure thành giá trị hợp lệ** là **`exceptionally(...)`**:

```java
CompletableFuture<Integer> recovered =
    CompletableFuture.completedFuture("abc")
        .thenApply(Integer::parseInt)
        .exceptionally(error -> 0);
// recovered.join() == 0
```

`exceptionally` không phải một thao tác chạy lại bước bị lỗi. Nó **đăng ký một hàm fallback**; nếu stage ngay trước đã hoàn thành bất thường, hàm đó nhận nguyên nhân lỗi và tạo **một giá trị thay thế cùng kiểu kết quả**. Nếu stage trước thành công, giá trị đi tiếp mà không cần gọi fallback.

**Bài học cốt lõi:** Đặt `exceptionally` đúng vị trí, hiểu nó trả **stage mới**, nhận diện loại lỗi cần khôi phục và chọn fallback không làm sai nghiệp vụ. API `exceptionally` có từ **Java 8**, vẫn còn được hỗ trợ và phù hợp trong các ứng dụng Java hiện đại.

### 1.1. Mô hình success/failure

```text
        Nguồn
          |
     thenApply(A)
          |
     thenApply(B)
          |
     exceptionally(error -> fallback)
          |
          v
     Stage kết quả cuối
        /           \
  A,B thành công     Có failure trước handler
       |                    |
 giữ kết quả B          dùng fallback
        \                  /
         \________________/
                  |
           tiếp tục thenApply(C)
```

Sơ đồ minh họa **phạm vi bắt lỗi** của `exceptionally`: chỉ những lỗi đã xuất hiện ở stage **thượng nguồn được nối vào handler** mới có thể khiến handler đó chạy. Nếu `thenApply(C)` phát sinh lỗi sau handler, handler trước đó không thể quay ngược lại để bắt.

## 2. Hợp đồng chính xác của `exceptionally(Function)`

Với `CompletableFuture<T>`, chữ ký:

```java
public CompletableFuture<T> exceptionally(
    Function<Throwable, ? extends T> fn)
```

Ở cấp interface `CompletionStage<T>`, kết quả có kiểu `CompletionStage<T>`. Hàm `fn` nhận một `Throwable` của stage nguồn và trả một giá trị **thuộc kiểu `T` hoặc subtype của `T`**. Đây là lý do `exceptionally` rất phù hợp để **phục hồi lỗi nhưng giữ nguyên kiểu kết quả**.

Quy tắc:

1. **Nguồn thành công:** handler `fn` **không được gọi**; stage kết quả nhận cùng giá trị thành công (kể cả `null`).
2. **Nguồn hoàn thành bất thường:** handler được gọi với lỗi và có thể trả một giá trị fallback; nếu handler **trả về bình thường**, stage kết quả **thành công** với giá trị ấy.
3. **Chính handler ném lỗi:** stage kết quả mới **hoàn thành bất thường** với lỗi của handler, thường được biểu diễn qua `CompletionException` khi `join()`.
4. **Nguồn chưa hoàn thành:** stage mới cũng chưa có kết quả. Chỉ đăng ký handler không tự chốt nguồn hoặc tạo ra fallback tức thì.
5. **Nguồn bị hủy:** cancellation cũng là dạng exceptional completion đối với `CompletableFuture`; handler có thể nhận và phục hồi tùy chính sách.
6. **Không thay đổi stage nguồn:** `exceptionally` **tạo stage phụ thuộc mới**, không sửa trạng thái `failed` của nguồn.

Mỗi hàm `exceptionally` là một nhánh **bắt lỗi của chính đoạn pipeline đứng trước nó**, giống một khối `catch` của luồng tính toán đó, nhưng không phải global exception handler cho cả JVM.

### 2.1. Bảng trạng thái trước và sau handler

| Nguồn | Handler có chạy? | Kết quả từ `exceptionally` |
| --- | --- | --- |
| Thành công với `"OK"` | Không | Thành công với `"OK"` |
| Thành công với `null` | Không | Thành công với `null` |
| Pending | Chưa | Pending |
| Failure, handler trả `"CACHE"` | Có | Thành công với `"CACHE"` |
| Failure, handler trả `null` | Có | Thành công với `null` |
| Failure, handler ném `IllegalArgumentException` | Có | Stage mới thất bại |
| Cancelled, handler trả fallback | Có thể chạy do exceptional completion | Stage mới có thể thành công với fallback |

Việc "khôi phục" **không xóa dấu vết rằng nguồn đã lỗi**: những nhánh khác đang chờ nguồn có thể vẫn gặp lỗi.

## 3. Trường hợp thành công: `exceptionally` được bỏ qua

```java
AtomicInteger recoveryCalls = new AtomicInteger();

CompletableFuture<String> success =
    CompletableFuture.completedFuture("READY")
        .exceptionally(error -> {
            recoveryCalls.incrementAndGet();
            return "FALLBACK";
        });

// success.join() == "READY"
// recoveryCalls.get() == 0
```

Snippet cần `AtomicInteger` và `CompletableFuture`. Khi nguồn thành công, hàm fallback **không phải** được gọi rồi kết quả bị bỏ đi; nó không chạy. Điều này quan trọng vì một fallback có thể tốn I/O, tạo số liệu log hoặc cập nhật metric. Không nên đặt công việc cần xảy ra trong **mọi trường hợp** vào `exceptionally`; hãy dùng `whenComplete` hoặc `handle` nếu thực sự cần quan sát cả hai nhánh.

### 3.1. Thành công với `null` không giống failure

```java
CompletableFuture<String> withNull =
    CompletableFuture.completedFuture(null);

CompletableFuture<String> after = withNull
    .exceptionally(error -> "DEFAULT");

// after.join() == null
```

Nếu API quy định kết quả có thể `null`, `exceptionally` không tự chuyển `null` thành `"DEFAULT"`. Để biến kết quả null thành default, đó là **quy tắc dữ liệu nhánh thành công**, nên dùng `thenApply(value -> value == null ? "DEFAULT" : value)` hoặc một kiểu trả kết quả tường minh hơn như `Optional<T>` theo hợp đồng nghiệp vụ.

Đừng nhầm `completedFuture(null)`, `new CompletableFuture<>()` và `completeExceptionally(error)`. Chúng lần lượt là **đã thành công null**, **chưa xong** và **đã thất bại**.

## 4. Trường hợp thất bại: fallback tạo stage kết quả thành công

Một mẫu tối giản:

```java
CompletableFuture<String> original = new CompletableFuture<>();

CompletableFuture<String> recovered =
    original.exceptionally(error -> "CACHE");

original.completeExceptionally(
    new IllegalStateException("Service unavailable"));

// original.isCompletedExceptionally() == true
// recovered.isCompletedExceptionally() == false
// recovered.join() == "CACHE"
```

`completeExceptionally` công bố lỗi của nguồn. Handler chuyển lỗi thành một **giá trị cùng kiểu `String`**, nên chỉ stage `recovered` là bình thường. Nếu caller vẫn giữ và `join()` đối tượng `original`, họ vẫn gặp lỗi. Vì vậy việc chọn **trả stage nào** từ service là một quyết định thiết kế quan trọng.

### 4.1. Đừng bỏ mất stage đã khôi phục

**Sai:**

```java
CompletableFuture<String> original = new CompletableFuture<>();
original.exceptionally(error -> "CACHE"); // kết quả bị bỏ đi
original.completeExceptionally(
    new IllegalStateException("offline"));

// original vẫn thất bại, không biến thành "CACHE".
```

**Đúng:**

```java
CompletableFuture<String> original = new CompletableFuture<>();
CompletableFuture<String> safe =
    original.exceptionally(error -> "CACHE");

original.completeExceptionally(
    new IllegalStateException("offline"));
// safe.join() == "CACHE"
```

Hai đoạn là snippet trong method; bản đầu không nên được dùng khi kỳ vọng biến `original` sẽ chuyển thành giá trị fallback. Tất cả các toán tử chain như `thenApply`/`handle`/`exceptionally` thường trả **stage mới**; đặt tên rõ giúp tránh nhầm "đã xử lý lỗi" với "đã tạo một nhánh có khả năng xử lý lỗi".

### 4.2. Phục hồi sau khi nguồn đã hoàn thành lỗi

Đăng ký handler **sau khi future đã lỗi** vẫn hợp lệ:

```java
CompletableFuture<Integer> failed = new CompletableFuture<>();
failed.completeExceptionally(
    new IllegalArgumentException("Invalid id"));

CompletableFuture<Integer> safe =
    failed.exceptionally(error -> -1);

// safe.join() == -1
```

Trong implementation, handler có thể thực hiện ngay trên thread **đang đăng ký** nếu nguồn đã hoàn thành. Đừng vì đã thấy `exceptionally` gọi sau `completeExceptionally` mà suy ra callback sẽ chạy trong background pool.

## 5. Vị trí `exceptionally` quyết định phạm vi lỗi được bắt

Đây là điểm ảnh hưởng tính đúng nhiều nhất khi **ghép tác vụ**.

### 5.1. Đặt trước phép toán có thể ném lỗi

```java
CompletableFuture<Integer> result =
    CompletableFuture.completedFuture("abc")
        .exceptionally(error -> "0")
        .thenApply(Integer::parseInt);

// thenApply ném NumberFormatException, nên result thất bại.
// Handler trước thenApply KHÔNG bắt được lỗi tương lai đó.
```

Với `completedFuture("abc")`, stage nguồn là thành công, vì vậy handler **không chạy**. `Integer.parseInt` phía sau mới ném lỗi; không có handler tiếp theo để phục hồi. Nếu dùng `join()`, sẽ nhận exception.

### 5.2. Đặt sau phép toán có thể ném lỗi

```java
CompletableFuture<Integer> result =
    CompletableFuture.completedFuture("abc")
        .thenApply(Integer::parseInt)
        .exceptionally(error -> 0);

// result.join() == 0
```

Ở đây lỗi của `thenApply(Integer::parseInt)` là **thượng nguồn** của `exceptionally`, nên handler chạy và trả `Integer 0`.

### 5.3. Một handler đặt cuối bao phủ các bước trước nó

```java
CompletableFuture<String> processed =
    CompletableFuture.completedFuture("15")
        .thenApply(Integer::parseInt)
        .thenApply(n -> n * 2)
        .thenApply(n -> "value=" + n)
        .exceptionally(error -> "UNAVAILABLE");
```

Lỗi ở một trong ba bước trước handler có thể khiến dependent stage cuối phục hồi bằng `"UNAVAILABLE"`. Nhưng một fallback **chung** như vậy có thể che mất **nguyên nhân nghiệp vụ quan trọng**; đôi khi nên đặt handler ngay sau mỗi bước cụ thể và phân biệt lỗi có thể phục hồi hay phải lan truyền.

Một chuỗi có **nhiều handler** sẽ tạo nhiều ranh giới phục hồi. Một khi handler đầu khôi phục bằng giá trị, handler tiếp theo chỉ chạy nếu có lỗi mới được tạo ở giữa hoặc handler trước tự thất bại.

### 5.4. Phục hồi sớm hay muộn?

| Vị trí | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Sau bước gọi remote | Có thể fallback cache khi remote lỗi | Có thể che lỗi remote nếu fallback không phù hợp |
| Sau parse/validate | Trả giá trị mặc định cho input lỗi được phép | Dễ biến dữ liệu sai thành giá trị hợp lệ giả |
| Cuối chuỗi | Một điểm xử lý exception chung | Khó biết bước nào lỗi; fallback quá rộng |
| Trong mỗi stage | Điều khiển chính xác loại lỗi và fallback | Có thể nhiều handler/lỗi bị nuốt, giảm khả năng quan sát |
| Sau `allOf` | Phục hồi lỗi tổng hợp | Có thể che kết quả phụ thuộc nào thất bại |

Không có quy tắc “luôn đặt `exceptionally` cuối” hoặc “luôn đặt ngay sau supplier”. Phải xác định **giá trị nào có thể thay thế an toàn**, lỗi nào cần được báo ra và phần pipeline nào được phép phục hồi.

## 6. Chọn fallback đúng kiểu và đúng nghiệp vụ

`exceptionally` nhận một hàm `Throwable -> T`. Với `CompletableFuture<Integer>`, một fallback thông thường cũng phải là `Integer`, ví dụ `0` hoặc `-1`. Nếu muốn chuyển hoàn toàn sang một kiểu kết quả khác, dùng `handle` hoặc các stage khác với kiểu phù hợp.

```java
CompletableFuture<Integer> failedCount = new CompletableFuture<>();
failedCount.completeExceptionally(
    new IllegalStateException("counter unavailable"));

CompletableFuture<Integer> recoveredCount =
    failedCount.exceptionally(error -> -1);
```

**Nhưng `-1` có thực sự an toàn không?** Một đếm số lượng có thể dùng `-1` làm "không biết" nếu domain quy định như vậy. Nếu `0` nghĩa là **không có đơn hàng**, dùng `0` để che lỗi lấy số liệu có thể đưa ra quyết định kinh doanh sai. Trong nghiệp vụ quan trọng, nên trả một kiểu mô tả rõ:

- `Optional<T>` nếu "không có giá trị" là một trạng thái hợp lệ, **khác với** "không truy cập được nguồn".
- `Result<T,Error>`/kiểu domain có trạng thái để caller phân biệt `SUCCESS`, `DEGRADED` và `FAILURE`.
- Hoặc giữ exceptional completion để caller xử lý.

### 6.1. Fallback null hợp lệ về cú pháp nhưng cần xem nghĩa

```java
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(new IllegalStateException("offline"));

CompletableFuture<String> result =
    failed.exceptionally(error -> null);

// result.isCompletedExceptionally() == false
// result.join() == null
```

Không có lỗi `NullPointerException` chỉ vì fallback trả `null`. Nhưng `null` có thể gây lỗi **ở continuation tiếp theo**:

```java
CompletableFuture<Integer> length =
    result.thenApply(String::length);

// NPE khi thenApply chạy với null; length thất bại.
```

Nếu phải biểu diễn "không có dữ liệu", cân nhắc dùng `Optional.empty()`, một DTO có trạng thái rõ ràng hoặc quy định null cụ thể và kiểm tra trước khi dùng.

### 6.2. Fallback là giá trị, không phải thao tác retry

```java
CompletableFuture<String> fallback =
    remoteCall()
        .exceptionally(error -> "CACHED_VALUE");
```

Đây là snippet kiến trúc, cần method `remoteCall()` do ứng dụng định nghĩa. Nó **không chạy lại** `remoteCall`. Nếu muốn retry, phải tạo **lần thử mới** theo chính sách có giới hạn, idempotency và backoff, thường bằng một `CompletionStage` thứ hai. Đừng đặt lại `exceptionally` nhiều lần rồi tưởng rằng mỗi handler là một lần gửi request mới.

## 7. Đọc lỗi đúng cách: `Throwable`, `CompletionException` và `ExecutionException`

Lambda `exceptionally(error -> ...)` nhận một `Throwable`. Loại cụ thể phụ thuộc **cách upstream thất bại**:

- `completeExceptionally(new IOException(...))` công bố exception được cung cấp.
- Hàm trong `thenApply`/`supplyAsync` tự ném `RuntimeException` có thể khiến dependent stage nhận lỗi được **bọc trong `CompletionException`**.
- Ghép `allOf` hoặc `thenCombine` có thể lan truyền lỗi với `CompletionException`.
- Cancellation có thể truyền `CancellationException` trực tiếp hoặc trong lớp bọc ở dependent stage.

**Không luôn giả định `error instanceof IOException`** dù nguyên nhân thật ban đầu là `IOException`, vì nó có thể nằm trong `error.getCause()`. Ngược lại, cũng không mặc định mọi exception đều có cause.

### 7.1. `join` và `get` cho API caller

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(
    new IllegalStateException("down"));

try {
    source.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    // IllegalStateException trong ví dụ này.
}
```

`join()` thường ném unchecked `CompletionException` với cause khi exceptional completion. `get()` từ `Future` ném checked `ExecutionException` (và có thể `InterruptedException` khi chờ). `get(timeout,unit)` còn có `TimeoutException` khi **lời gọi chờ hết hạn**; timeout chờ không tự kết thúc future.

Cancellation trực tiếp trên future có thể làm `join()` ném `CancellationException`, không nhất thiết bọc trong `CompletionException`. Tầng gọi phải xử lý cả các trường hợp này theo contract.

### 7.2. Helper bóc lớp bọc có kiểm soát

```java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **method snippet** cần import `CompletionException`, `ExecutionException`. Nó tháo các lớp bọc thường gặp để **phân loại nguyên nhân**. Không nên bóc mọi `getCause()` vô điều kiện: một `Throwable` nghiệp vụ có cause nhưng **bản thân nó** mới là loại lỗi mà caller cần quan sát.

Không cần tháo wrapper trong mọi handler. Nếu chỉ trả fallback dựa trên một chính sách chung, có thể xử lý `Throwable` ở mức cao. Nhưng nếu phân biệt lỗi "not found" với lỗi "permission denied", hãy xem đúng root cause, không dựa vào chuỗi `getMessage()`.

### 7.3. Đừng dùng message như giao thức nghiệp vụ

`ex.getMessage()` và stack trace có thể chứa hostname, URI, khóa truy cập, tên file hoặc dữ liệu khách hàng. Tránh viết logic kiểu `if (ex.getMessage().contains("timeout")) ...`. Hãy phân loại theo **kiểu exception**, mã lỗi domain hoặc response status có cấu trúc. Log có redaction, correlation ID, severity; không gửi stack trace/cause nội bộ ra client.

## 8. Handler tự thất bại: phục hồi không phải cam kết thành công

`exceptionally` nhận một hàm người dùng; hàm này có thể ném exception:

```java
CompletableFuture<String> original = new CompletableFuture<>();
original.completeExceptionally(new IllegalStateException("offline"));

CompletableFuture<String> recovered =
    original.exceptionally(error -> {
        throw new IllegalArgumentException("fallback invalid");
    });

// recovered.isCompletedExceptionally() == true
```

Khi `recovered.join()`, caller nhìn thấy thất bại của handler, thường qua `CompletionException` với cause là `IllegalArgumentException`. Future nguồn **vẫn có lỗi cũ**, còn future phụ thuộc mới chứa lỗi handler. Không thể diễn giải “cứ gọi `exceptionally` là kết quả an toàn”.

### 8.1. Fallback dựa vào một dịch vụ khác cũng có thể lỗi

```java
CompletableFuture<User> recovered =
    primaryFetch()
        .exceptionally(error -> loadBackupSynchronously());
```

Đây là **snippet kiến trúc**, `User`, `primaryFetch`, `loadBackupSynchronously` do ứng dụng định nghĩa. Nếu backup phải gọi mạng và có thể chặn lâu, `exceptionally` ở đây có thể chạy trên **thread đang hoàn thành upstream** và gây nghẽn event loop. Nếu backup **bất đồng bộ**, `exceptionally` không phải toán tử phù hợp để trả thẳng `CompletionStage<User>`; hãy xem `handle(...).thenCompose(...)` trên Java 8 hoặc `exceptionallyCompose` trên Java 12+.

### 8.2. Nếu muốn giữ lỗi gốc khi fallback lỗi?

Không có một chính sách chung. Có thể cần:

- Lưu **nguyên nhân remote chính** và **nguyên nhân cache phụ** vào exception domain có hai cause/metadata.
- Phân biệt retryable, non-retryable và canceled.
- Không nuốt lỗi fallback rồi trả một giá trị “thành công” tùy ý nếu có tác động tài chính hoặc an toàn.
- Đảm bảo không làm mất thông tin phục vụ điều tra nhưng vẫn ẩn dữ liệu nhạy cảm.

`CompletionException`/`ExecutionException` chỉ là cơ chế truyền lỗi qua các stage; **quyết định nghiệp vụ** thuộc về ứng dụng.

## 9. So sánh `exceptionally`, `handle` và `whenComplete`

Ba toán tử này đều tham gia luồng xử lý exceptional completion, nhưng ý định khác nhau:

| Toán tử (Java 8) | Khi nguồn thành công | Khi nguồn lỗi | Ý nghĩa chính | Kiểu kết quả |
| --- | --- | --- | --- | --- |
| `exceptionally(fn)` | Bỏ qua `fn`, chuyển nguyên giá trị | Gọi `fn(error)` tạo fallback | **Khôi phục lỗi** | Giữ kiểu `T` |
| `handle(fn)` | Gọi `fn(value,null)` | Gọi `fn(null,error)` | **Biến đổi cả hai nhánh** | Có thể thành `U` |
| `whenComplete(action)` | Chạy action để quan sát | Chạy action để quan sát | **Quan sát/metrics/cleanup**, không chủ đích đổi kết quả | Giữ kiểu `T` và ưu tiên outcome nguồn |

### 9.1. `handle` có thể thay kiểu dữ liệu

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(
    new IllegalStateException("offline"));

CompletableFuture<Integer> lengthOrMinusOne =
    source.handle((value, error) ->
        error == null ? value.length() : -1);

// lengthOrMinusOne.join() == -1
```

Ở đây nguồn có kiểu `String` nhưng stage kết quả là `Integer`. Nếu muốn phục hồi lỗi mà **giữ nguyên `String`**, `exceptionally` thường diễn đạt ý định rõ và gọn hơn.

Vì `handle` chạy ở **cả hai nhánh**, cần kiểm tra `error == null` trước khi truy cập `value`, đặc biệt khi value có thể null nhưng vẫn là thành công hợp lệ. Với kiểu kết quả nullable, `value == null` tự nó không chứng minh lỗi.

### 9.2. `whenComplete` không phải công cụ thay lỗi bằng fallback

```java
CompletableFuture<String> source = new CompletableFuture<>();
source.completeExceptionally(
    new IllegalStateException("offline"));

CompletableFuture<String> observed =
    source.whenComplete((value, error) -> {
        if (error != null) {
            // Log metric, dọn tài nguyên, correlation ID.
        }
    });

// observed vẫn hoàn thành bất thường.
```

`whenComplete` chủ đích **bảo toàn outcome của nguồn**. Nếu callback quan sát không ném lỗi, kết quả/lỗi nguồn được giữ lại. Nếu callback lại ném exception, quy tắc propagation ưu tiên lỗi của **nguồn đã thất bại**; còn nguồn thành công có thể trở thành lỗi do callback. Không nên lạm dụng `whenComplete` để dùng cho fallback; dùng `exceptionally` hoặc `handle` nếu muốn **biến đổi kết quả**.

### 9.3. Tổ hợp quan sát rồi khôi phục

```java
CompletableFuture<String> safe =
    remoteFetch()
        .whenComplete((value, error) -> {
            if (error != null) {
                recordFailureMetric();
            }
        })
        .exceptionally(error -> "CACHE");
```

Đây là **snippet kiến trúc** yêu cầu định nghĩa `remoteFetch` và `recordFailureMetric`. Việc ghi metric không nên tự ném lỗi hoặc chiếm thread quá lâu; nếu metric có thể lỗi, phải quyết định nó có được phép ảnh hưởng outcome hay không. Nếu log và phục hồi cùng nằm trong một handler, hãy tránh log hai lần ở nhiều stage.

## 10. `exceptionally` không tương đương `thenCompose`: fallback bất đồng bộ

### 10.1. Tại sao không được trả `CompletableFuture` từ handler trả `T`?

Giả sử `CompletableFuture<String> primary` thất bại, và backup trả `CompletableFuture<String>`. `exceptionally` mong chờ một **`String`**, không phải một `CompletableFuture<String>`:

```java
CompletableFuture<String> primary = new CompletableFuture<>();

// Không compile (mismatch): handler cần String, backup trả Future<String>.
// CompletableFuture<String> wrong =
//     primary.exceptionally(error -> asyncBackup());
```

Đây là snippet minh họa lỗi kiểu, `asyncBackup()` do ứng dụng định nghĩa. Không giải quyết bằng `backup.join()` trong handler: làm vậy **chặn thread** đang chạy handler và có thể gây treo nếu phụ thuộc cùng event loop/executor.

### 10.2. Java 8: `handle` tạo stage rồi `thenCompose` làm phẳng

```java
static CompletableFuture<String> withAsyncFallback(
        CompletableFuture<String> source, String key) {
    return source.handle((value, error) ->
        error == null
            ? CompletableFuture.completedFuture(value)
            : fetchBackupAsync(key)
    ).thenCompose(Function.identity());
}
```

Đây là **method snippet**, cần `CompletableFuture`, `Function` và method `fetchBackupAsync(key)` trả `CompletableFuture<String>` do ứng dụng cung cấp.

Cơ chế:

1. `handle` chạy với thành công/lỗi, quyết định chọn **stage đã có giá trị** hay **stage backup**.
2. Kiểu trung gian là một stage của stage, tương đương ý tưởng `CompletableFuture<CompletableFuture<String>>`.
3. `thenCompose(Function.identity())` làm phẳng thành một `CompletableFuture<String>` cuối cùng. Không dùng `thenApply(Function.identity())` vì phép apply thông thường sẽ tạo result lồng nhau.
4. Backup chỉ cần được gọi trên nhánh thất bại. Nếu backup cũng thất bại, stage cuối vẫn thất bại, chứ không có fallback thứ ba trừ khi ứng dụng định nghĩa.

Mẫu này vẫn dùng các API **Java 8**, và không cần đưa thread vào trạng thái ngủ/chờ chỉ để lấy backup.

### 10.3. Java 12+: `exceptionallyCompose` diễn đạt trực tiếp fallback theo stage

Java **12** giới thiệu `CompletionStage.exceptionallyCompose` và các biến thể async để dễ viết:

```java
CompletionStage<String> safe =
    primary.exceptionallyCompose(
        error -> fetchBackupAsync("A7"));
```

Đây là snippet **Java 12+**, với `primary` là `CompletionStage<String>`, `fetchBackupAsync` được định nghĩa trong ứng dụng. Hàm fallback trả một `CompletionStage<String>`; toán tử tự compose kết quả stage đó. Nếu upstream thành công, backup không chạy.

Các biến thể **`exceptionallyComposeAsync`** (Java 12+) có thể chạy logic chọn backup trên default async executor hoặc executor cụ thể; vẫn phải phân biệt **việc gọi supplier/handler** với **tác vụ I/O thật của backup**. Một API `fetchBackupAsync` có thể dùng executor hoặc event loop của client riêng.

**Không sử dụng `exceptionallyCompose` trong code nhắm `javac --release 8`**. Đây là API hiện hành nhưng được bổ sung sau Java 8.

### 10.4. Nếu fallback cũng thất bại?

```java
CompletionStage<String> result = primary
    .exceptionallyCompose(error -> backupAsync())
    .exceptionally(error -> "NO_DATA");
```

Đây là snippet Java 12+, cần `backupAsync()` do ứng dụng định nghĩa. Handler thứ hai có thể chặn lỗi của primary hoặc backup, nhưng logic này **cố ý che cả hai lỗi** bằng giá trị `"NO_DATA"`. Chỉ làm vậy khi hợp đồng cho phép, và cần observability đủ để biết tỷ lệ thất bại gốc/backup.

## 11. Async execution: ai chạy hàm phục hồi?

`exceptionally` là toán tử **non-async**. Theo hợp đồng của `CompletableFuture`, action của những continuation non-async có thể chạy bởi thread hoàn thành nguồn hoặc một caller liên quan đến completion. Không có cam kết rằng nó sẽ luôn chạy trên ForkJoin common pool.

```java
CompletableFuture<String> promise = new CompletableFuture<>();

CompletableFuture<String> recovered =
    promise.exceptionally(error -> expensiveFallback());

// Thread hoàn thành promise có thể phải chạy expensiveFallback().
```

Đây là snippet, cần method `expensiveFallback`. Nếu một callback mạng gọi `completeExceptionally` và fallback thực hiện DB lookup đồng bộ kéo dài, bạn có thể **chặn thread callback**. Hệ quả có thể là latency cao, nghẽn event loop, hoặc một thread ít tài nguyên gánh thêm CPU.

### 11.1. Java 8: dùng `handleAsync(..., executor)` để phục hồi trên executor

```java
ExecutorService executor =
    Executors.newFixedThreadPool(2);

try {
    CompletableFuture<String> source = new CompletableFuture<>();
    CompletableFuture<String> safe =
        source.handleAsync((value, error) ->
            error == null ? value : "FALLBACK", executor);

    source.completeExceptionally(
        new IllegalStateException("offline"));

    String result = safe.join(); // "FALLBACK"
} finally {
    executor.shutdown();
}
```

Đây là snippet trong method, cần `ExecutorService`, `Executors` và `CompletableFuture`. `handleAsync` chạy cả trường hợp thành công lẫn lỗi trên executor được cung cấp, vì vậy **không cùng nghĩa tối ưu** với một handler chỉ chạy ở nhánh thất bại. Nhưng đây là cách đơn giản trong **Java 8** khi cần điều khiển nơi thực thi logic recovery.

Nếu executor bị shutdown hoặc không nhận thêm task, dependent stage có thể kết thúc bất thường theo chính sách executor; không xem một executor như “cứ có là chắc chắn được phục hồi”.

### 11.2. Java 12+: `exceptionallyAsync`

`exceptionallyAsync(fn)` và `exceptionallyAsync(fn, executor)` (Java **12+**) diễn đạt recovery chỉ dành cho lỗi nhưng **lên lịch hàm xử lý lỗi** bằng cơ chế async. Nó khác `exceptionallyComposeAsync`: một bên trả giá trị `T`, bên còn lại trả `CompletionStage<T>`.

```java
CompletionStage<String> safe =
    primary.exceptionallyAsync(
        error -> "FALLBACK", recoveryExecutor);
```

Đây là **snippet Java 12+**, cần `primary` kiểu `CompletionStage<String>` và `recoveryExecutor` kiểu `Executor` do ứng dụng quản lý. Những method này **không có trong Java 8**, dù vẫn đang được hỗ trợ trên Java hiện đại.

### 11.3. Không chặn pool bằng `join()` trong handler

```java
CompletableFuture<String> risky =
    primary.exceptionally(error -> backupAsync().join());
```

Đây là snippet mô tả **điều cần tránh**. Nó biến backup bất đồng bộ thành **chặn đồng bộ**. Có thể gây starvation nếu completion handler và backup cùng cần một executor có ít worker, nhất là trong chuỗi phức tạp hoặc event-loop.

Ưu tiên `handle + thenCompose` (Java 8) hoặc `exceptionallyCompose` (Java 12+) để duy trì composition không chặn.

## 12. Cancellation và timeout: không phục hồi mọi lỗi một cách mù quáng

### 12.1. Cancellation cũng là exceptional completion

`CompletableFuture.cancel(false)` hoặc `cancel(true)` có thể chốt future chưa xong bằng `CancellationException`. Một stage `exceptionally` phụ thuộc vào đó có thể chạy và trả fallback:

```java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> safe =
    source.exceptionally(error -> "CANCEL_FALLBACK");

source.cancel(false);

// source.isCancelled() == true
// safe.join() == "CANCEL_FALLBACK"
```

Nhưng **có nên biến hủy thành thành công không?** Thường là **không**, nếu người dùng đã yêu cầu hủy thao tác. `CancellationException` nên được phân biệt khỏi lỗi mạng có thể thay thế bằng cache.

Nếu muốn giữ cancellation:

```java
CompletableFuture<String> safe = source.exceptionally(error -> {
    Throwable cause = unwrapCompletion(error);
    if (cause instanceof CancellationException) {
        throw (CancellationException) cause;
    }
    return "CACHE";
});
```

Đây là snippet cần `unwrapCompletion`, `CancellationException`. Nó chủ ý **tái ném** cancellation, nên stage mới tiếp tục thất bại. Với thiết kế phức tạp, có thể đưa chính sách cancellation ra tầng orchestration riêng, thay vì để mọi stage tự quyết.

**Lưu ý:** `cancel(true)` của `CompletableFuture` không bảo đảm ngắt producer; tham số `mayInterruptIfRunning` không trực tiếp ngắt tác vụ theo implementation của lớp này. Completion bất thường và dừng I/O thật là hai việc khác nhau.

### 12.2. Timeout chờ khác với timeout làm future thất bại

Trong Java 8:

```java
try {
    String result = future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    // Chỉ lời gọi get này hết thời gian chờ.
    // Future có thể vẫn pending, handler exceptionally chưa chạy.
}
```

Snippet cần `future`, `TimeUnit`, `TimeoutException` và xử lý các checked exceptions khác (`InterruptedException`, `ExecutionException`) ở tầng phương thức.

`get(timeout, unit)` ném `TimeoutException` cho **caller đang chờ**, nhưng **không tự gọi `completeExceptionally` trên future**. Vì vậy một `exceptionally` gắn vào future **không nhất thiết chạy chỉ vì có ai đó timed get bị timeout**.

Từ **Java 9**, có:

- `orTimeout(timeout, unit)`: nếu future chưa xong sau hạn, **hoàn thành chính future đó bất thường** với `TimeoutException`, khiến recovery handler có thể chạy.
- `completeOnTimeout(value, timeout, unit)`: nếu chưa xong, **hoàn thành chính future bình thường** bằng fallback, nên `exceptionally` sau nó không chạy đối với timeout đã được chuyển thành thành công.

Cả hai không tự hủy I/O gốc. Cần quản lý timeout/cancel ở network client hoặc nguồn công việc thật để tránh giữ socket, thread và tài nguyên ngoài khi wrapper future đã hoàn thành.

## 13. Ghép nhiều tác vụ: `thenCombine`, `allOf` và nhánh lỗi

Vì bài học thuộc nhóm **Ghép tác vụ**, cần hiểu lỗi di chuyển thế nào qua các nhánh.

### 13.1. `thenCombine`: cần cả hai thành công

```java
CompletableFuture<Integer> price =
    CompletableFuture.completedFuture(100);

CompletableFuture<Integer> discount = new CompletableFuture<>();
discount.completeExceptionally(
    new IllegalStateException("discount unavailable"));

CompletableFuture<Integer> total = price
    .thenCombine(discount, (p, d) -> p - d)
    .exceptionally(error -> 100);

// total.join() == 100
```

`thenCombine` cần cả hai nguồn để áp dụng hàm kết hợp. Nếu một nguồn lỗi, stage tổng hợp có thể thất bại rồi `exceptionally` **trên stage tổng hợp** tạo fallback.

**Nhưng** nếu chỉ muốn "khuyến mãi lỗi thì coi giảm giá bằng 0", đôi khi nên đặt recovery **ngay trên nhánh discount trước khi combine**:

```java
CompletableFuture<Integer> safeDiscount =
    discount.exceptionally(error -> 0);

CompletableFuture<Integer> total =
    price.thenCombine(safeDiscount, (p, d) -> p - d);
// total.join() == 100
```

Cách sau phân biệt **lỗi giá** (có thể phải chặn giao dịch) với **lỗi giảm giá** (có thể fallback 0). Handler trên tổng hợp dễ vô tình che cả lỗi giá, từ đó đưa ra giá sai.

### 13.2. `allOf`: lỗi của một nhánh làm tổng hợp lỗi

```java
CompletableFuture<String> first =
    CompletableFuture.completedFuture("A");
CompletableFuture<String> second = new CompletableFuture<>();
second.completeExceptionally(new IllegalStateException("B failed"));

CompletableFuture<Void> all =
    CompletableFuture.allOf(first, second);

CompletableFuture<String> outcome = all
    .thenApply(ignored -> "ALL_OK")
    .exceptionally(error -> "AGGREGATE_FALLBACK");
```

`allOf` hoàn thành khi tất cả future đầu vào kết thúc; nếu có bất kỳ failure, nó hoàn thành bất thường. `exceptionally` của `allOf` **nhận một lỗi đại diện**, **không tự liệt kê mọi lỗi** nếu nhiều nhánh cùng thất bại. Muốn tổng hợp lỗi của tất cả nhánh, phải thiết kế cách thu thập kết quả/lỗi riêng cho từng future, ví dụ chuyển từng outcome thành DTO thành công/thất bại trước khi `allOf`.

Đừng ngầm kết luận các nguồn còn lại **đã bị hủy** khi `allOf` báo lỗi. `allOf` không tự dừng các tác vụ remote; phải quản lý tài nguyên/cancellation theo business logic.

### 13.3. `anyOf` không phải “thành công nhanh nhất”

`CompletableFuture.anyOf` hoàn thành khi **một trong các future** hoàn thành, theo trạng thái thành công hoặc thất bại của nhánh thắng. Nếu một nguồn nhanh chóng lỗi, `anyOf` có thể báo lỗi dù nguồn khác sẽ thành công ngay sau đó. Đặt `exceptionally` lên `anyOf` có thể tạo fallback quá sớm.

Nếu nghiệp vụ cần **kết quả thành công đầu tiên**, phải xây dựng mô hình chọn success có chủ đích (và xác định chính sách khi mọi nguồn đều lỗi), không mặc định `anyOf` luôn chọn thành công. Cũng không coi cancellation của aggregate là cơ chế dừng tự động tất cả nguồn.

### 13.4. Vị trí recovery thay đổi ý nghĩa ghép tác vụ

```text
A --------\
           thenCombine --> exceptionally  : fallback cho lỗi của cả aggregate
B --------/

A ----------------------\
                         thenCombine       : chỉ fallback lỗi của B
B --> exceptionally ----/
```

Với dữ liệu có trọng số nghiệp vụ khác nhau, lựa chọn đặt handler **trên nhánh cụ thể** hoặc **sau phép ghép** rất quan trọng.

## 14. Phân biệt fallback, retry và circuit breaker

Ba khái niệm hay xuất hiện cùng nhau nhưng không giống nhau:

- **Fallback:** thay một failure bằng **giá trị khác** hoặc **stage khác**. `exceptionally` và `exceptionallyCompose` thực hiện vai trò này.
- **Retry:** **gửi lại** một phép toán theo chính sách số lần, backoff, timeout, idempotency. Chỉ gắn một handler không tự retry.
- **Circuit breaker:** tránh gửi thêm tới một dependency đang lỗi theo thống kê/trạng thái; có thể trả failure hoặc fallback ngay, tùy thiết kế ứng dụng.

### 14.1. Retry phải có giới hạn

Một anti-pattern:

```java
// Chỉ minh họa lỗi thiết kế: không có giới hạn retries.
CompletableFuture<String> endless =
    remoteCall().exceptionally(error -> remoteCall().join());
```

Nó chỉ chạy backup một lần trong snippet, không thật sự “endless”, nhưng nếu đem logic này đặt đệ quy không giới hạn hoặc dùng cùng mô hình chờ `join`, hệ thống có thể gây nghẽn/đánh sập dependency. Cách đúng là đặt **số lần thử tối đa**, chính sách delay có jitter, timeout, cancellation, và chỉ retry loại lỗi thực sự có tính tạm thời.

Với POST thanh toán hay thao tác có side effect, retry phải kèm **idempotency** hoặc bảo đảm transaction; không chỉ dựa vào cơ chế completion của `CompletableFuture`.

### 14.2. Tránh cascade fallback không được giám sát

```text
Primary lỗi -> Backup A lỗi -> Backup B lỗi -> "EMPTY"
```

Đây có thể là một kiến trúc có ích nếu domain chấp nhận dữ liệu giảm chất lượng. Nhưng nếu mọi thất bại đều được chuyển thành `"EMPTY"` mà không có metrics, hệ thống có thể hiển thị sai “không có dữ liệu” trong khi thực tế **không truy cập được hệ thống**.

Định nghĩa rõ:

- Lỗi nào được phục hồi, lỗi nào phải lan truyền.
- Giá trị nào được phép dùng làm fallback.
- Timeout cho primary và backup.
- Mức concurrency tối đa / tài nguyên executor.
- Metadata báo trạng thái degraded để hỗ trợ UI, logs, SLO và alert.
- Khi nào phải tắt fallback để tránh dữ liệu cũ vượt giới hạn an toàn.

## 15. Chương trình Java chạy được: đủ các nhánh phục hồi

Ví dụ **tương thích Java 8** dưới đây không sử dụng `failedFuture` (Java 9+) hay `exceptionallyCompose`/`exceptionallyAsync` (Java 12+). Mọi kết quả đều xác định; chỉ có một tác vụ async minh họa chạy trên executor riêng, và chương trình gọi `join` trước khi in kết quả để stdout không phụ thuộc lịch thread.

Tạo file **CompletableFutureExceptionalRecoveryDemo.java**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

public class CompletableFutureExceptionalRecoveryDemo {
    static <T> CompletableFuture<T> failed(Throwable error) {
        CompletableFuture<T> future = new CompletableFuture<>();
        future.completeExceptionally(error);
        return future;
    }

    static String causeType(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException ||
                current instanceof ExecutionException) &&
                current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getSimpleName();
    }

    static CompletableFuture<String> backup(String key) {
        return CompletableFuture.completedFuture("backup:" + key);
    }

    static CompletableFuture<String> fallbackStageJava8(
            CompletableFuture<String> primary, String key) {
        return primary.handle((value, error) ->
            error == null
                ? CompletableFuture.completedFuture(value)
                : backup(key)
        ).thenCompose(Function.identity());
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> success =
            CompletableFuture.completedFuture("ORIGINAL")
                .exceptionally(error -> {
                    calls.incrementAndGet();
                    return "FALLBACK";
                });
        System.out.println("Success passes: " + success.join());
        System.out.println("Recovery calls on success: " + calls.get());

        CompletableFuture<String> primary = new CompletableFuture<>();
        CompletableFuture<String> recovered =
            primary.exceptionally(error -> "CACHED");
        System.out.println("Recovered pending before: " + recovered.isDone());
        System.out.println("Primary exceptional completion: " +
            primary.completeExceptionally(new IllegalStateException("offline")));
        System.out.println("Recovered value: " + recovered.join());
        System.out.println("Primary still exceptional: " +
            primary.isCompletedExceptionally());
        System.out.println("Recovered exceptional: " +
            recovered.isCompletedExceptionally());

        try {
            primary.join();
        } catch (CompletionException error) {
            System.out.println("Original join cause: " + causeType(error));
        }
        try {
            primary.get();
        } catch (ExecutionException error) {
            System.out.println("Original get cause: " + causeType(error));
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new AssertionError(error);
        }

        CompletableFuture<Integer> early =
            CompletableFuture.completedFuture("not-a-number")
                .exceptionally(error -> "0")
                .thenApply(Integer::parseInt);
        CompletableFuture<Integer> late =
            CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt)
                .exceptionally(error -> 0);
        System.out.println("Early handler misses later error: " +
            early.isCompletedExceptionally());
        System.out.println("Late handler recovers: " + late.join());

        CompletableFuture<String> nullSource =
            failed(new IllegalStateException("offline"));
        CompletableFuture<String> nullFallback =
            nullSource.exceptionally(error -> null);
        System.out.println("Null fallback is success: " +
            !nullFallback.isCompletedExceptionally());
        System.out.println("Null fallback is null: " +
            (nullFallback.join() == null));

        CompletableFuture<String> handlerSource =
            failed(new IllegalStateException("offline"));
        CompletableFuture<String> handlerFailure =
            handlerSource.exceptionally(error -> {
                throw new IllegalArgumentException("invalid fallback");
            });
        System.out.println("Handler failure is exceptional: " +
            handlerFailure.isCompletedExceptionally());
        try {
            handlerFailure.join();
        } catch (CompletionException error) {
            System.out.println("Handler failure cause: " + causeType(error));
        }

        CompletableFuture<String> handleSource =
            failed(new IllegalStateException("offline"));
        CompletableFuture<Integer> handled =
            handleSource.handle((value, error) ->
                error == null ? value.length() : 77);
        System.out.println("handle changes type: " + handled.join());

        AtomicInteger observed = new AtomicInteger();
        CompletableFuture<String> observedSource =
            failed(new IllegalStateException("offline"));
        CompletableFuture<String> observedStage =
            observedSource.whenComplete((value, error) ->
                observed.incrementAndGet());
        System.out.println("whenComplete observer calls: " + observed.get());
        System.out.println("whenComplete remains failed: " +
            observedStage.isCompletedExceptionally());

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        CompletableFuture<String> cancellationRecovery =
            cancelled.exceptionally(error -> "CANCEL_FALLBACK");
        System.out.println("Cancel succeeded: " + cancelled.cancel(false));
        System.out.println("Source cancelled: " + cancelled.isCancelled());
        System.out.println("Cancellation recovered value: " +
            cancellationRecovery.join());

        CompletableFuture<String> backupPrimary =
            failed(new IllegalStateException("backend down"));
        System.out.println("Composed backup: " +
            fallbackStageJava8(backupPrimary, "A7").join());
        System.out.println("Composed success: " +
            fallbackStageJava8(
                CompletableFuture.completedFuture("LIVE"), "A7").join());

        CompletableFuture<Void> all = CompletableFuture.allOf(
            CompletableFuture.completedFuture("OK"),
            failed(new IllegalStateException("one dependency failed")));
        System.out.println("allOf recovery: " +
            all.thenApply(ignored -> "ALL_OK")
               .exceptionally(error -> "AGGREGATE_FALLBACK").join());

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> asyncSource =
                failed(new IllegalStateException("down"));
            CompletableFuture<String> asyncRecovery =
                asyncSource.handleAsync((value, error) ->
                    error == null ? value : "EXECUTOR_FALLBACK", executor);
            System.out.println("handleAsync recovery: " + asyncRecovery.join());
        } finally {
            executor.shutdown();
        }
    }
}
```

Lệnh biên dịch và chạy trên JDK hiện đại (tùy chọn `--release 8` giúp đảm bảo không dùng API sau Java 8):

```bash
javac --release 8 -encoding UTF-8 CompletableFutureExceptionalRecoveryDemo.java
java CompletableFutureExceptionalRecoveryDemo
```

**Stdout chính xác:**

```text
Success passes: ORIGINAL
Recovery calls on success: 0
Recovered pending before: false
Primary exceptional completion: true
Recovered value: CACHED
Primary still exceptional: true
Recovered exceptional: false
Original join cause: IllegalStateException
Original get cause: IllegalStateException
Early handler misses later error: true
Late handler recovers: 0
Null fallback is success: true
Null fallback is null: true
Handler failure is exceptional: true
Handler failure cause: IllegalArgumentException
handle changes type: 77
whenComplete observer calls: 1
whenComplete remains failed: true
Cancel succeeded: true
Source cancelled: true
Cancellation recovered value: CANCEL_FALLBACK
Composed backup: backup:A7
Composed success: LIVE
allOf recovery: AGGREGATE_FALLBACK
handleAsync recovery: EXECUTOR_FALLBACK
```

### 15.1. Giải thích output theo từng nhóm

- **Hai dòng đầu:** Nguồn đã thành công với `"ORIGINAL"`, nên `exceptionally` không chạy và biến `AtomicInteger` vẫn là 0. Đây là bằng chứng rằng handler chỉ dành cho nhánh lỗi.
- **Pending rồi thất bại:** `recovered.isDone()` ban đầu `false`. Khi `primary.completeExceptionally(...)` được gọi, handler trả `"CACHED"`. Source vẫn exceptional, stage mới thì thành công.
- **`join` vs `get`:** Trên nguồn thất bại, `join()` dùng `CompletionException` và `get()` dùng `ExecutionException`; code kiểm tra nguyên nhân bên dưới của cả hai, không so nguyên thông báo lỗi.
- **Vị trí handler:** `exceptionally` đặt **trước** `Integer.parseInt` không thể phục hồi lỗi xảy ra về sau; đặt **sau** parse thì trả được 0.
- **Null fallback:** Việc trả `null` từ handler có thể làm stage hoàn thành bình thường; đó không phải kết quả pending.
- **Handler ném lỗi:** Recovery đã chạy nhưng chính nó thất bại; stage recovery mang lỗi mới `IllegalArgumentException`.
- **`handle` vs `whenComplete`:** `handle` tạo giá trị kiểu `Integer` là 77; `whenComplete` tăng counter một lần nhưng không thay lỗi nguồn.
- **Cancellation:** Cancellation là exceptional completion, nên handler có thể biến nó thành fallback. Ví dụ làm vậy để minh họa hợp đồng, **không có nghĩa production luôn nên nuốt cancellation**.
- **Fallback theo stage:** Hàm `fallbackStageJava8` sử dụng `handle` + `thenCompose`; với nguồn lỗi, nó lấy `"backup:A7"`, còn nguồn thành công giữ `"LIVE"`.
- **`allOf`:** Khi một dependency lỗi, aggregate thất bại; `exceptionally` trên aggregate biến nó thành giá trị `"AGGREGATE_FALLBACK"`.
- **Executor:** `handleAsync` với executor riêng trả `"EXECUTOR_FALLBACK"`, đã được `join` đảm bảo hoàn thành trước khi in. Executor được shutdown sau thử nghiệm.

## 16. Thiết kế phục hồi lỗi trong ứng dụng thực

### 16.1. Chỉ khôi phục lỗi được phép khôi phục

Giả sử API lấy giá vận chuyển: nếu dịch vụ báo giá tạm thời không phản hồi, dùng cached price có TTL hợp lệ có thể được phép. Nhưng nếu lỗi là **không có quyền**, **chữ ký dữ liệu sai**, **giá trị thanh toán không hợp lệ** hoặc **hủy bởi người dùng**, không nên biến tất cả thành giá mặc định.

Một mẫu phân loại:

```java
CompletableFuture<String> safe =
    primary.exceptionally(error -> {
        Throwable cause = unwrapCompletion(error);
        if (cause instanceof IllegalArgumentException) {
            throw new CompletionException(cause); // lỗi không recover
        }
        return "CACHED"; // chỉ hợp lý nếu contract cho phép
    });
```

Đây là snippet yêu cầu biến `primary`, helper `unwrapCompletion` và import `CompletionException`; nó chỉ minh họa **có nhánh tái ném**, không phải quy tắc rằng mọi `IllegalArgumentException` luôn không phục hồi. Trong production, định nghĩa taxonomy exception theo domain và chính sách rõ, không catch/recover `Throwable` một cách mù quáng.

### 16.2. Telemetry trước và sau recovery

Khi một future được phục hồi, downstream có thể chỉ nhìn thấy **thành công**. Vì vậy số liệu “tỷ lệ request lỗi” nếu chỉ đếm exceptional completion ở stage cuối có thể bỏ sót số lần backend lỗi rồi fallback.

Có thể theo dõi riêng:

- `primary_failure_count`: số lần nguồn lỗi.
- `fallback_success_count`: số lần fallback giúp trả kết quả.
- `fallback_failure_count`: số lần fallback cũng lỗi.
- `degraded_response_count`: kết quả trả thành công kỹ thuật nhưng chất lượng thấp hơn.
- Latency, số tác vụ in-flight, độ bão hòa executor, timeout thật của network client.

Không ném lỗi từ metric/logger nếu ý định của `whenComplete` chỉ là quan sát; nếu cần giao thức đảm bảo ghi log, thiết kế giao dịch/queue riêng.

### 16.3. Bảo toàn thông tin lỗi mà không leak

Không cần gửi `Throwable.toString()`, toàn bộ stack trace hoặc remote response body cho người dùng cuối. Một API có thể trả mã lỗi `REMOTE_UNAVAILABLE`, trạng thái `DEGRADED` hoặc một đối tượng domain riêng, trong khi log nội bộ giữ correlation ID và thông tin đã che nhạy cảm.

Nếu fallback thất bại, cân nhắc giữ lỗi gốc làm cause/suppressed trong error object khi cần audit. Tránh mất hoàn toàn dấu vết bằng cách chỉ trả `null` cho mọi exception.

### 16.4. Điều phối tài nguyên khi backup bất đồng bộ

Một fallback có thể tạo thêm tải ngay lúc primary đang lỗi hàng loạt, gây **retry storm** hoặc overload backup. Bảo đảm:

- Có giới hạn số request/connection đang mở tới backup.
- Có timeout ở I/O và deadline toàn request.
- Không giữ worker chỉ để `join()` một backup bất đồng bộ.
- Có circuit breaker hoặc load shedding nếu backup cũng bão hòa.
- Xử lý callback đến muộn và cleanup listener.
- Không tự tạo `ExecutorService` cho từng request rồi quên `shutdown`.

`exceptionally` xử lý **luồng kết quả**, không thay thế các chính sách tài nguyên của hệ thống phân tán.

## 17. Các lỗi phổ biến cần tránh

### 17.1. Tưởng `exceptionally` chạy trên success

Không. `exceptionally` chỉ gọi hàm hồi phục khi **stage nguồn hoàn thành bất thường**. Nếu muốn chạy ở hai nhánh, dùng `handle` hoặc `whenComplete` theo mục đích.

### 17.2. Tưởng handler sửa được future nguồn

Không. Nó trả một **stage mới**, source vẫn có lỗi. Phải giữ hoặc trả đúng stage `recovered` cho caller.

### 17.3. Đặt handler trước đoạn ném lỗi

`exceptionally(...).thenApply(parse)` không bắt được lỗi của `parse`. Đặt handler **sau** đoạn cần phục hồi hoặc tách nhánh thích hợp.

### 17.4. Trả fallback sai kiểu `T`

`CompletableFuture<Integer>.exceptionally(error -> "zero")` không type-check. Dùng giá trị `Integer` hoặc chuyển kiểu bằng `handle`/mô hình domain khác.

### 17.5. Trả `null` và cho rằng đó là pending

`exceptionally(error -> null)` có thể tạo stage **thành công với null**. Continuation tiếp theo không kiểm tra null có thể tự ném NPE.

### 17.6. Đọc nguyên nhân bằng chuỗi message

Lỗi trong dependent stage có thể bị bọc `CompletionException`. Dùng kiểu error/cause phù hợp, đừng dựa vào `ex.getMessage().contains(...)`.

### 17.7. Bắt mọi cancellation rồi trả thành công

Cancellation thường mang ý nghĩa người dùng hoặc tác vụ đã bị hủy. Chỉ recover nếu domain thực sự cho phép, còn không nên tái ném/lan truyền.

### 17.8. Coi `get(timeout,unit)` bị timeout là nguồn future đã thất bại

Không đúng. `TimeoutException` có thể chỉ thuộc **lời gọi chờ**; future vẫn pending. Phân biệt với `orTimeout`/`completeOnTimeout` (Java 9+) là thao tác chốt future.

### 17.9. Coi `exceptionally` là retry

Nó không tự chạy lại supplier/I/O. Retry cần gọi lại tác vụ theo chiến lược, giới hạn số lần, backoff và idempotency.

### 17.10. Chặn bằng `backupAsync().join()` trong handler

Có thể gây starvation hoặc deadlock với executor hạn chế. Dùng `handle(...).thenCompose(...)` trên Java 8 hoặc `exceptionallyCompose` (Java 12+).

### 17.11. Nhầm `whenComplete` với recovery

`whenComplete` chủ yếu dùng quan sát kết quả/lỗi. Để thay kết quả khi có lỗi, dùng `exceptionally` hoặc `handle`.

### 17.12. Quên xử lý lỗi do handler tạo ra

Nếu fallback ném exception, stage đã phục hồi dự kiến trở thành exceptional. Test cả **nguồn lỗi** lẫn **fallback lỗi**, không chỉ một nhánh happy path.

### 17.13. Cho rằng continuation non-async luôn chạy nền

`exceptionally` có thể chạy trên thread đang complete upstream. Với công việc nặng, dùng executor hoặc API compose phù hợp.

### 17.14. Cho rằng `allOf` tự thu thập tất cả nguyên nhân lỗi

`allOf` cung cấp exceptional completion của stage tổng hợp, không phải một báo cáo đầy đủ mọi lỗi nguồn. Muốn báo cáo tất cả, thu thập outcome từng nhánh.

### 17.15. Dùng `exceptionallyCompose` trong Java 8

`exceptionallyCompose` và `exceptionallyAsync` có từ Java 12; không dùng trong nguồn Java 8. `failedFuture`/`orTimeout` có từ Java 9. Phân biệt **API hiện đại** và **API có sẵn trong phiên bản build**.

### 17.16. Nuốt lỗi quan trọng bằng hằng số

Trả `0` cho lỗi kiểm tra thanh toán hoặc `"EMPTY"` cho dữ liệu không truy cập được có thể làm hệ thống sai ngữ nghĩa. Chỉ dùng fallback khi domain rõ ràng cho phép trạng thái degraded.

## 18. Bảng quyết định

| Tình huống | Giải pháp phù hợp | Cần lưu ý |
| --- | --- | --- |
| Giá trị đã thành công, chỉ muốn giữ nguyên | Không cần handler, hoặc `exceptionally` pass-through | Handler không chạy |
| Remote lỗi, fallback cache đã có | `exceptionally(error -> cached)` | Kiểm tra TTL/chính sách cache |
| Handler cần đổi `T` thành `U` | `handle((value,error) -> ...)` | Chạy cả hai trạng thái |
| Chỉ muốn log lỗi rồi truyền tiếp | `whenComplete((value,error) -> ...)` | Không ném exception từ logger |
| Backup trả `CompletionStage<T>` trên Java 8 | `handle(...).thenCompose(...)` | Không chặn bằng `join` |
| Backup trả stage trên Java 12+ | `exceptionallyCompose(...)` | Phân biệt nhánh fallback |
| Recovery cần executor riêng trên Java 8 | `handleAsync(..., executor)` | Chạy cả hai nhánh trên executor |
| Recovery chỉ nhánh lỗi, chạy async trên Java 12+ | `exceptionallyAsync(...)` | Quản lý executor |
| Cần biết nguyên nhân gốc | Kiểm tra `CompletionException.getCause()` | Không dựa vào message |
| Future nguồn bị cancel | Phân biệt `CancellationException` | Không nuốt cancellation mặc định |
| Timeout chờ ở Java 8 | `get(timeout, TimeUnit)` | Future không tự bị complete |
| Phục hồi lỗi của nhánh B trong `thenCombine` | Bọc B bằng `exceptionally` trước khi combine | Không che lỗi A |
| Phục hồi lỗi tổng hợp của `allOf` | Handler trên aggregate | Không được suy ra mọi nguyên nhân |
| Cần retry có backoff | Workflow retry riêng | Không coi `exceptionally` là retry |
| Tính chính xác cao: payment/permission | Giữ failure hoặc dùng result domain | Không tạo thành công giả |
| Unit test recovery | Future hoàn thành sẵn/bất thường thủ công | Không phụ thuộc sleep/race |

## 19. Câu hỏi tự luyện và đáp án

**1.** `exceptionally` chạy khi stage nguồn thành công với `null` không?  
**Đáp án:** không. Đó vẫn là normal completion.

**2.** `exceptionally(error -> -1)` có thay đổi future nguồn đã lỗi thành thành công không?  
**Đáp án:** không. Nó tạo **dependent stage** thành công với `-1` nếu handler trả bình thường.

**3.** Tại sao `completedFuture("abc").exceptionally(...).thenApply(Integer::parseInt)` vẫn thất bại?  
**Đáp án:** lỗi parse xảy ra **sau handler**; handler chỉ thấy kết quả thành công `"abc"` của stage trước đó.

**4.** Khác biệt giữa `exceptionally` và `handle`?  
**Đáp án:** `exceptionally` chỉ gọi callback khi lỗi và giữ kiểu `T`; `handle` gọi callback ở cả success/failure và có thể tạo kiểu `U`.

**5.** `whenComplete` có phải cách chính để thay failure bằng fallback không?  
**Đáp án:** không; chủ yếu để quan sát, thường giữ outcome nguồn.

**6.** Nếu hàm fallback ném `IllegalArgumentException`, stage recovered có thành công không?  
**Đáp án:** không. Nó thất bại với lỗi handler, thường thấy qua `CompletionException` khi `join`.

**7.** `error` trong `exceptionally` có luôn là root exception gốc không?  
**Đáp án:** không. Có thể là `CompletionException` bọc nguyên nhân; phải kiểm tra wrapper/cause phù hợp.

**8.** `CompletableFuture.cancel(true)` có chắc ngắt I/O đang chạy không?  
**Đáp án:** không. Cancellation ở `CompletableFuture` không đồng nghĩa hủy tài nguyên producer.

**9.** `exceptionally(error -> null)` là lỗi cú pháp hay completion bất thường?  
**Đáp án:** không phải. Nó có thể **thành công với null**, nếu loại kết quả là reference type.

**10.** `get(timeout,unit)` hết giờ thì `exceptionally` của future có chắc chạy không?  
**Đáp án:** không. Lời gọi `get` có thể ném `TimeoutException` riêng trong khi future vẫn pending.

**11.** Muốn backup trả future trên Java 8 thì làm sao tránh `join`?  
**Đáp án:** dùng `handle` chọn stage (thành công/bù) rồi `thenCompose` làm phẳng.

**12.** `exceptionallyCompose` có từ phiên bản nào?  
**Đáp án:** Java 12, được hỗ trợ trên JDK hiện đại.

**13.** `exceptionallyAsync` khác `exceptionallyComposeAsync` ở kiểu fallback thế nào?  
**Đáp án:** bản đầu trả giá trị `T`, bản sau trả `CompletionStage<T>` để compose.

**14.** Khi `thenCombine` có lỗi ở nhánh discount nhưng price hợp lệ, nên đặt fallback ở đâu nếu chỉ discount được phép lỗi?  
**Đáp án:** đặt `exceptionally` lên nhánh discount **trước** `thenCombine`.

**15.** `allOf` cung cấp danh sách đầy đủ tất cả lỗi của các nguồn không?  
**Đáp án:** không. Muốn lấy từng lỗi, phải thu thập outcome riêng từng nguồn.

**16.** Vì sao không nên trả `0` cho mọi lỗi đọc số tiền?  
**Đáp án:** vì `0` có thể bị hiểu là tiền thật bằng 0 trong khi nguồn dữ liệu bị lỗi, dẫn tới quyết định sai.

**17.** Muốn fallback chạy trên executor trong Java 8, API gần nhất là gì?  
**Đáp án:** `handleAsync(..., executor)` (chạy cho cả success/failure), hoặc thiết kế composition không chặn bằng executor của backup.

**18.** Vì sao quan sát tỷ lệ lỗi chỉ ở stage cuối là chưa đủ nếu có `exceptionally`?  
**Đáp án:** nhiều lỗi upstream đã được chuyển thành kết quả thành công, nên cần metrics cho primary failure, fallback success và degraded response.

## 20. Tài liệu chính thức và các phiên bản API

Tất cả các API chính nêu trong bài còn được duy trì. Những tính năng bổ sung sau Java 8 được ghi rõ để người đọc không nhầm giữa **“Java 8-compatible”** và **“Java hiện đại”**:

- [`CompletionStage` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html): `exceptionally`, `handle`, `whenComplete`, propagation, `thenCompose` và mốc `Since: 12` cho `exceptionallyAsync`/`exceptionallyCompose`.
- [`CompletableFuture` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `completeExceptionally`, `join`, `get`, `isCompletedExceptionally`, `cancel`, `allOf`, `anyOf`, chính sách continuation non-async.
- [`CompletionException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper unchecked của failure trong pipeline.
- [`ExecutionException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html): lỗi được báo qua `Future.get`.
- [`Future` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, cancellation và việc chờ kết quả.
- [`ExecutorService` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): executor có quản lý vòng đời cho `handleAsync` và continuation.
