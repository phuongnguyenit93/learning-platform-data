# CompletableFuture.get(), join() và sự khác biệt ngoại lệ trong Java 8

Trong Java 8, `CompletableFuture<T>` biểu diễn một kết quả có thể hoàn thành **về sau**. Hai phương thức quen thuộc để lấy kết quả là `get()` và `join()`. Cả hai trả về cùng giá trị khi tác vụ hoàn thành bình thường và đều có thể **chặn luồng đang gọi** cho đến khi tương lai hoàn thành. Nhưng khi tác vụ thất bại, bị hủy hoặc luồng bị ngắt, **hợp đồng ngoại lệ khác nhau**, ảnh hưởng trực tiếp đến cách thiết kế API, xử lý lỗi và viết kiểm thử.

Ví dụ, một future bị hoàn thành lỗi bằng `IOException("remote-down")`:

- `future.get()` ném **`ExecutionException`**, bên trong `getCause()` là `IOException`.
- `future.join()` ném **`CompletionException`**, bên trong `getCause()` cũng là `IOException`.
- `get()` có checked exceptions, nên mã Java phải khai báo hoặc bắt `InterruptedException` và `ExecutionException`.
- `join()` dùng unchecked exceptions, nên cú pháp ngắn hơn nhưng **không có nghĩa lỗi ít nghiêm trọng hơn**.
- Khi future **bị hủy trực tiếp**, cả `get()` lẫn `join()` có thể ném **`CancellationException` trực tiếp**, không nhất thiết thông qua wrapper trên.

Bài thuộc nhóm **CompletableFuture** của module **Java 8**. Tất cả ví dụ chỉ dùng những API Java 8 vẫn được hỗ trợ trong Java hiện đại, tuân thủ yêu cầu tránh kiến thức lỗi thời. Nội dung phân biệt **checked/unchecked**, ngoại lệ gốc và wrapper, timeout, interruption, cancellation, `getNow`, `exceptionally`/`handle`/`whenComplete`, `thenCompose` và những lựa chọn xử lý lỗi an toàn ở ranh giới đồng bộ–bất đồng bộ. Có **5 chương trình Java độc lập**, đã biên dịch với mức Java 8 và chạy để đối chiếu đầu ra.

## 1. CompletableFuture có thể kết thúc theo những trạng thái nào?

Một `CompletableFuture<T>` có thể đang **chưa hoàn thành**, hoàn thành **thành công**, hoàn thành **ngoại lệ** hoặc được **hủy**. Những trạng thái này quyết định hành vi của cả `get`, `join` và các callback phụ thuộc.

| Trạng thái | Ví dụ tạo | `get()` | `join()` |
| --- | --- | --- | --- |
| Chưa hoàn thành | `new CompletableFuture<>()` | Chờ; có thể bị ngắt | Chờ; không khai báo `InterruptedException` |
| Thành công | `completedFuture("OK")` | Trả `"OK"` | Trả `"OK"` |
| Thất bại vì một exception | `completeExceptionally(new IOException(...))` | `ExecutionException` có cause | `CompletionException` có cause |
| Hủy trực tiếp | `cancel(true)` | `CancellationException` | `CancellationException` |
| Dependent stage thất bại do source bị hủy | `cancelled.thenApply(...)` | Thường `ExecutionException`, cause liên quan cancellation | Thường `CompletionException`, cause liên quan cancellation |

Một future **đã hoàn thành ngoại lệ** vẫn được xem là **done**. `isDone()` chỉ cho biết kết quả đã được quyết định, **không chứng minh thành công**. `isCompletedExceptionally()` có thể đúng với cả trường hợp bị hủy.

### Completion có tính một lần

Khi `complete(value)` hoặc `completeExceptionally(error)` quyết định kết quả trước, những lần hoàn thành cạnh tranh sau sẽ không thay thế được kết quả bằng các phương thức complete thông thường. Giá trị boolean trả về từ `complete`/`completeExceptionally` giúp xác định lượt gọi có thật sự hoàn thành future hay không.

Đây không phải lời mời dùng `complete` để điều khiển tùy tiện một pipeline đang chạy. Cần có cơ chế ownership của future và quy tắc ai được phép hoàn thành nó.

## 2. API cốt lõi: get, get(timeout), join và getNow

### `get()`

`CompletableFuture` implements `Future<T>`. Vì vậy `get()` là API Future có hợp đồng checked exceptions:

```java
// Minh họa bên trong phương thức có throws hoặc try/catch.
String result = future.get();
```

Khi future chưa xong, luồng gọi có thể chờ vô thời hạn nếu không có cơ chế hoàn thành/cancel từ nơi khác. Khi tác vụ thất bại, `get()` ném `ExecutionException`; khi luồng đang chờ bị ngắt, nó ném `InterruptedException`.

### `get(long timeout, TimeUnit unit)`

Phiên bản có timeout hạn chế **thời gian chờ của người gọi**:

```java
String result = future.get(250, TimeUnit.MILLISECONDS);
```

Ngoài `InterruptedException` và `ExecutionException`, phương thức có thể ném **`TimeoutException`** nếu chưa có kết quả trước khi hết thời gian chờ. **Timeout của get không tự làm future thất bại hay bị hủy**. Future có thể hoàn thành bình thường sau khi người gọi hết thời gian chờ.

### `join()`

```java
String result = future.join();
```

`join()` không khai báo checked exceptions. Nếu future hoàn thành lỗi, nó thường ném **`CompletionException`**. Nếu future bị hủy, nó có thể ném **`CancellationException` trực tiếp**. Việc không phải viết `throws` hay `catch` không làm lỗi biến mất.

Trong Java 8 **không có overload `join(timeout, unit)`**. Nếu cần hạn thời gian chờ của luồng gọi trong Java 8, dùng `get(timeout, unit)` hoặc thiết kế timeout ở pipeline/scheduler của ứng dụng; không dùng API mới hơn rồi tuyên bố ví dụ chạy trên Java 8.

### `getNow(valueIfAbsent)`

```java
String current = future.getNow("NOT_READY");
```

Đây là thao tác **không chờ**. Nếu chưa hoàn thành, trả ngay giá trị dự phòng. Nếu đã hoàn thành bình thường, trả kết quả. Nếu đã hoàn thành ngoại lệ, `getNow` **ném exception giống đường lỗi unchecked** (thường là CompletionException; hủy trực tiếp là CancellationException), **không dùng giá trị dự phòng để nuốt lỗi**.

**Lưu ý:** `getNow` không đồng nghĩa `exceptionally`. Nó chỉ cung cấp giá trị khi **chưa hoàn thành**, không phải phương án xử lý thất bại đã xảy ra.

## 3. Bảng so sánh ngắn gọn

| Tiêu chí | `get()` | `join()` |
| --- | --- | --- |
| Thuộc hợp đồng | `Future.get` | Phương thức `CompletableFuture` |
| Có thể block? | Có | Có |
| Kết quả thành công | Giá trị T | Giá trị T |
| Thất bại bình thường | `ExecutionException` | `CompletionException` |
| Exception gốc | Trong `getCause()` | Trong `getCause()` |
| Checked exception? | Có, `InterruptedException` và `ExecutionException` | Không |
| Hủy chính future | `CancellationException` unchecked | `CancellationException` unchecked |
| Hỗ trợ timeout chờ trực tiếp? | Có, `get(long,TimeUnit)` | Không trong Java 8 |
| Khi luồng chờ bị interrupt | Có thể ném `InterruptedException` | Thường tiếp tục chờ, không ném checked InterruptedException; cờ interrupt được giữ/đặt lại |
| Tương tác với code legacy yêu cầu Future | Phù hợp | Không phải phương thức của interface Future |
| Thuận tiện trong pipeline/biên đồng bộ | Cần quản lý checked exceptions | Cú pháp ngắn nhưng vẫn phải quản lý lỗi |

Từ bảng trên không thể kết luận `join` luôn “tốt hơn” `get`. Chọn phương thức dựa vào **hợp đồng exception**, **chính sách ngắt**, **timeout** và **kiểu giao diện gọi**.

## 4. Ngoại lệ gốc và wrapper: đừng bắt nhầm lớp

Giả sử tác vụ xử lý file hoặc mạng thất bại với:

```java
IOException root = new IOException("remote-down");
CompletableFuture<String> f = new CompletableFuture<>();
f.completeExceptionally(root);
```

Với `get()`:

```java
try {
    f.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Trả về / lan truyền trạng thái hủy do ngắt.
} catch (ExecutionException e) {
    Throwable rootCause = e.getCause();
    // rootCause là IOException trong trường hợp này.
}
```

Với `join()`:

```java
try {
    f.join();
} catch (CompletionException e) {
    Throwable rootCause = e.getCause();
    // rootCause là IOException trong trường hợp này.
}
```

Hai đoạn **không hoàn toàn thay thế nhau**: `get` cho nhánh xử lý interruption tường minh, trong khi `join` không đưa `InterruptedException` vào hợp đồng checked. Cả hai cần cách nhận diện nguyên nhân và ánh xạ thành lỗi nghiệp vụ hoặc vận hành.

**Phân biệt hai tầng:**

- **Wrapper** `ExecutionException`/`CompletionException` cho biết lỗi xảy ra trong một kết quả bất đồng bộ được quan sát ở ranh giới.
- **Cause** như `IOException`, `IllegalArgumentException`, `TimeoutException` nghiệp vụ hoặc `IllegalStateException` mới mô tả nguyên nhân ban đầu (nếu nó được giữ lại).

Không nên hiển thị nguyên văn toàn bộ stacktrace của wrapper cho người dùng cuối. Nhưng cũng không được xóa cause khỏi log/trace, vì sẽ mất đường dẫn gốc để chẩn đoán.

## 5. Chương trình 1 — get ném ExecutionException, join ném CompletionException

Tệp **`GetJoinExceptionsDemo.java`** sau đây là chương trình đầy đủ. Nó kiểm thành công, thất bại với IOException và lỗi từ một `thenApply`.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class GetJoinExceptionsDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> ok =
            CompletableFuture.completedFuture("OK");
        check("OK".equals(ok.get()), "get ok");
        check("OK".equals(ok.join()), "join ok");

        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(new IOException("remote-down"));

        String getType = "";
        String getCause = "";
        try {
            failed.get();
            throw new AssertionError("expected get failure");
        } catch (ExecutionException ex) {
            getType = ex.getClass().getSimpleName();
            getCause = ex.getCause().getClass().getSimpleName()
                + ":" + ex.getCause().getMessage();
        }

        String joinType = "";
        String joinCause = "";
        try {
            failed.join();
            throw new AssertionError("expected join failure");
        } catch (CompletionException ex) {
            joinType = ex.getClass().getSimpleName();
            joinCause = ex.getCause().getClass().getSimpleName()
                + ":" + ex.getCause().getMessage();
        }

        check("ExecutionException".equals(getType), "get wrapper");
        check("CompletionException".equals(joinType), "join wrapper");
        check("IOException:remote-down".equals(getCause)
              && getCause.equals(joinCause), "underlying cause");

        CompletableFuture<Integer> stageFailure =
            CompletableFuture.completedFuture(7).thenApply(n -> {
                throw new IllegalArgumentException("invalid-7");
            });

        String stageCause = "";
        try {
            stageFailure.join();
            throw new AssertionError("expected pipeline failure");
        } catch (CompletionException ex) {
            stageCause = ex.getCause().getClass().getSimpleName()
                + ":" + ex.getCause().getMessage();
        }

        check("IllegalArgumentException:invalid-7".equals(stageCause),
              "pipeline cause");

        System.out.println("getOK=" + ok.get());
        System.out.println("joinOK=" + ok.join());
        System.out.println("getType=" + getType);
        System.out.println("getCause=" + getCause);
        System.out.println("joinType=" + joinType);
        System.out.println("joinCause=" + joinCause);
        System.out.println("stageCause=" + stageCause);
        System.out.println("PASS");
    }
}
```

Chạy với JDK 8:

```bash
javac -encoding UTF-8 GetJoinExceptionsDemo.java
java GetJoinExceptionsDemo
```

Hoặc với JDK mới nhưng chỉ dùng API Java 8:

```bash
javac --release 8 -encoding UTF-8 GetJoinExceptionsDemo.java
java GetJoinExceptionsDemo
```

**Stdout đã kiểm chứng:**

```text
getOK=OK
joinOK=OK
getType=ExecutionException
getCause=IOException:remote-down
joinType=CompletionException
joinCause=IOException:remote-down
stageCause=IllegalArgumentException:invalid-7
PASS
```

**Giải thích:**

1. Khi future hoàn thành thành công, `get` và `join` trả cùng `"OK"`.
2. Cùng lỗi IOException được bọc khác nhau theo phương thức quan sát kết quả.
3. Ngoại lệ xuất hiện trong lambda của `thenApply` làm **dependent stage** hoàn thành ngoại lệ; `join` trên stage đó báo `CompletionException` với cause `IllegalArgumentException`.
4. Mã dùng `completeExceptionally` để tạo trạng thái lỗi **xác định**, không cần mạng thật hay sleep, nên stdout ổn định.
5. Test kiểm cả **kiểu wrapper** lẫn **nguyên nhân gốc**, thay vì chỉ assert “có bất kỳ exception nào”.

## 6. Vì sao có ExecutionException và CompletionException?

Lý do nằm ở thiết kế API:

- `Future.get` của Java dùng `ExecutionException` là checked exception để báo **kết quả tác vụ thất bại**. Code gọi phải khai báo hoặc bắt.
- `CompletableFuture.join` dùng `CompletionException` là unchecked exception (một `RuntimeException`), thuận tiện ở ranh giới nơi không muốn khai báo checked exceptions.
- `CompletableFuture.get` vẫn tuân theo hợp đồng Future; nó không chuyển thành join chỉ vì đối tượng là CompletableFuture.
- Hai kiểu đều hỗ trợ `getCause()` để xem nguyên nhân.

**Checked không đồng nghĩa “lỗi do người dùng sửa được”**, cũng như unchecked không đồng nghĩa “có thể bỏ qua”. Cách xử lý dựa trên **loại cause và contract** của tầng ứng dụng.

Ví dụ một `IOException` do hệ thống lưu trữ tạm không sẵn sàng có thể dẫn đến retry có kiểm soát; một `IllegalArgumentException` do dữ liệu đầu vào sai có thể là validation error; còn lỗi lập trình cần được ghi log và sửa. Đừng quyết định retry chỉ vì wrapper là CompletionException hoặc ExecutionException.

### Nếu lỗi gốc là CompletionException thì sao?

Một stage có thể đã hoàn thành ngoại lệ với chính một `CompletionException`, ví dụ thư viện hoặc một bước phụ thuộc trước đó đã bọc lỗi. Trong trường hợp đó:

- `join()` có thể ném lại **chính instance CompletionException đã lưu**.
- `get()` thông thường tạo `ExecutionException` có cause là **nguyên nhân bên trong CompletionException**, chứ không chồng thêm một tầng wrapper theo cùng cách `join`.

Vì vậy trong những pipeline phức tạp không nên mặc định cause chain luôn chỉ sâu đúng một tầng, hoặc bất kỳ thư viện nào cũng bọc y hệt. Khi cần chẩn đoán, duyệt chain có kiểm soát và giữ thông tin ban đầu.

## 7. Chương trình 2 — thenCompose và CompletionException đã được bọc sẵn

Tệp **`CauseAndCompositionDemo.java`** minh họa một tác vụ bất đồng bộ trả về một future khác, sử dụng `thenCompose` thay vì chặn bằng join trong lambda.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class CauseAndCompositionDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    static CompletableFuture<Integer> lengthLookup(String key) {
        if ("valid".equals(key)) {
            return CompletableFuture.completedFuture(key.length());
        }

        CompletableFuture<Integer> failed = new CompletableFuture<>();
        failed.completeExceptionally(
            new IOException("lookup-failed:" + key));
        return failed;
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> success =
            CompletableFuture.completedFuture("valid")
                .thenCompose(CauseAndCompositionDemo::lengthLookup);

        CompletableFuture<Integer> failure =
            CompletableFuture.completedFuture("missing")
                .thenCompose(CauseAndCompositionDemo::lengthLookup);

        int value = success.get();
        boolean getWrapped = false;
        boolean joinWrapped = false;

        try {
            failure.get();
        } catch (ExecutionException ex) {
            getWrapped = ex.getCause() instanceof IOException;
        }

        try {
            failure.join();
        } catch (CompletionException ex) {
            joinWrapped = ex.getCause() instanceof IOException;
        }

        CompletionException prewrapped =
            new CompletionException(new IOException("prewrapped-io"));
        CompletableFuture<String> wrapped = new CompletableFuture<>();
        wrapped.completeExceptionally(prewrapped);

        boolean getUnwrappedCause = false;
        boolean joinPreservedWrapper = false;

        try {
            wrapped.get();
        } catch (ExecutionException ex) {
            getUnwrappedCause = ex.getCause() instanceof IOException;
        }

        try {
            wrapped.join();
        } catch (CompletionException ex) {
            joinPreservedWrapper = (ex == prewrapped);
        }

        check(value == 5, "compose success");
        check(getWrapped && joinWrapped, "compose failure wrappers");
        check(getUnwrappedCause && joinPreservedWrapper,
              "already wrapped behavior");

        System.out.println("composedSuccess=" + value);
        System.out.println("getWrapsLookupFailure=" + getWrapped);
        System.out.println("joinWrapsLookupFailure=" + joinWrapped);
        System.out.println("getUnwrapsPrewrappedCause=" + getUnwrappedCause);
        System.out.println("joinPreservesPrewrappedException=" +
            joinPreservedWrapper);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CauseAndCompositionDemo.java
java CauseAndCompositionDemo
```

**Stdout đã kiểm chứng:**

```text
composedSuccess=5
getWrapsLookupFailure=true
joinWrapsLookupFailure=true
getUnwrapsPrewrappedCause=true
joinPreservesPrewrappedException=true
PASS
```

**Tại sao dùng thenCompose?** Hàm `lengthLookup` trả về một `CompletableFuture<Integer>`. Nếu dùng `thenApply`, kiểu kết quả sẽ là `CompletableFuture<CompletableFuture<Integer>>`, tức future lồng. `thenCompose` **nối phẳng hai công đoạn bất đồng bộ** thành một future kết quả mà không bắt buộc chặn một worker thread để lấy dữ liệu từ future con.

Ví dụ này hoàn thành đồng bộ bằng fixture để có output đáng tin. Trong ứng dụng thật, `lengthLookup` có thể triển khai trên I/O bất đồng bộ hoặc executor chuyên dụng, nhưng hợp đồng lỗi của các stage và `get`/`join` vẫn có ý nghĩa tương tự.

## 8. get(timeout) không giống timeout của tác vụ

Hãy tách hai vấn đề:

- **Thời gian chờ của caller**: quá 250 ms mà kết quả chưa xong, `future.get(250,TimeUnit.MILLISECONDS)` có thể ném `TimeoutException`.
- **Deadline của chính tác vụ**: công việc nền phải có cơ chế time budget, cancel hoặc dừng I/O tương ứng. Chỉ timeout tại phương thức get **không tự triển khai** deadline ấy.

Ví dụ:

```java
CompletableFuture<String> future = new CompletableFuture<>();

try {
    future.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Người gọi hết thời gian chờ.
    // Future vẫn có thể pending, rồi hoàn thành sau đó.
}
```

Nếu bạn cần xử lý tiếp sau timeout, nên quyết định:

1. Caller có thể trả trạng thái “đang xử lý” cho người dùng hay không?
2. Có được phép hủy công việc không? Ai thực sự có khả năng dừng I/O?
3. Kết quả hoàn thành muộn sẽ được lưu, bỏ qua hay gửi thông báo?
4. Retry có thể tạo **hai tác vụ cùng thực hiện** không? Có cần idempotency key?
5. Thời gian timeout lấy từ SLA nghiệp vụ hay cấu hình, không chỉ từ một con số đặt tùy tiện?

**Quan trọng:** trong Java 8, `CompletableFuture` không có các convenience methods `orTimeout` và `completeOnTimeout` vốn xuất hiện ở các phiên bản Java mới hơn. Không đưa chúng vào mã được yêu cầu biên dịch ở mức Java 8. Có thể dùng `ScheduledExecutorService` hoặc cơ chế timeout của thư viện, nhưng phải quản lý tài nguyên và kết quả muộn đúng cách.

### Phân biệt TimeoutException ở get với lỗi gốc

Một `TimeoutException` do `get(timeout)` ném trực tiếp thể hiện **caller đã đợi quá lâu**. Còn nếu tác vụ tự hoàn thành ngoại lệ bằng một `TimeoutException`, khi bạn gọi `get()` nó thường nằm **bên trong ExecutionException**, hoặc bên trong `CompletionException` nếu gọi `join()`. Hai nguồn lỗi này cần được phân biệt trong telemetry và retry policy.

## 9. Interruption: get có thể bị ngắt, join không khai báo InterruptedException

Khi một luồng đang chờ `get()` trên future chưa hoàn thành, `Thread.interrupt()` có thể làm lời gọi chấm dứt bằng **`InterruptedException`**. Khi exception được ném, cờ interrupt thường đã bị xóa bởi cơ chế chờ ngắt được.

`join()`, ngược lại, chờ theo cơ chế **không ném checked InterruptedException**. Nếu luồng bị interrupt trong lúc join đang chờ, nó thường **vẫn chờ kết quả**, sau đó giữ/đặt lại cờ interrupt.

Đừng hiểu điều đó thành “join an toàn hơn với việc hủy yêu cầu”. Việc không phản ứng bằng checked exception có thể khiến một luồng phục vụ request **chờ lâu hơn** mong muốn. Nếu luồng cần hỗ trợ shutdown/cancellation theo interruption, `get` hoặc một thiết kế không chặn thường phù hợp hơn.

### Quy tắc phục hồi cờ interrupt

Trong code production bắt `InterruptedException` mà không thể khai báo/ném tiếp, thường nên:

```java
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting interrupted", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Asynchronous task failed",
                                    ex.getCause());
}
```

Đây là **đoạn minh họa**, không phải chính sách bắt buộc rằng mọi interruption cần đổi thành IllegalStateException. Trong service thực tế, hãy áp loại exception/hợp đồng cancel thích hợp. Điều quan trọng là **không nuốt interruption một cách âm thầm**, nhất là khi hệ thống cần ngắt luồng để dừng tác vụ.

**Lưu ý:** `Thread.join()` là phương thức chờ một Java Thread kết thúc; nó **khác** `CompletableFuture.join()`, dù trùng tên. Trong các test dưới đây cả hai đều xuất hiện ở các vai trò riêng.

## 10. Chương trình 3 — timeout, ngắt get và trạng thái interrupt khi join

Tệp **`TimeoutInterruptionDemo.java`** dùng CountDownLatch và future chưa hoàn thành để kiểm hành vi không phụ thuộc sleep. Mọi luồng phụ được chờ kết thúc trước khi chương trình thoát.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class TimeoutInterruptionDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pendingGet = new CompletableFuture<>();

        boolean timedOut = false;
        try {
            pendingGet.get(0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }
        check(timedOut, "get(timeout) must time out");

        CountDownLatch getStarted = new CountDownLatch(1);
        AtomicBoolean getInterrupted = new AtomicBoolean(false);
        AtomicBoolean interruptCleared = new AtomicBoolean(false);

        Thread getWaiter = new Thread(() -> {
            getStarted.countDown();
            try {
                pendingGet.get();
                throw new AssertionError("pending get must be interrupted");
            } catch (InterruptedException expected) {
                getInterrupted.set(true);
                interruptCleared.set(!Thread.currentThread().isInterrupted());
            } catch (ExecutionException other) {
                throw new AssertionError(other);
            }
        }, "get-waiter");

        getWaiter.start();
        getStarted.await();
        getWaiter.interrupt();
        getWaiter.join();

        check(getInterrupted.get() && interruptCleared.get(),
              "get responds to interrupt");

        CompletableFuture<String> pendingJoin = new CompletableFuture<>();
        CountDownLatch joinStarted = new CountDownLatch(1);
        AtomicReference<String> joined = new AtomicReference<>();
        AtomicBoolean joinInterruptRetained = new AtomicBoolean(false);

        Thread joinWaiter = new Thread(() -> {
            joinStarted.countDown();
            joined.set(pendingJoin.join());
            joinInterruptRetained.set(Thread.currentThread().isInterrupted());
        }, "join-waiter");

        joinWaiter.start();
        joinStarted.await();
        joinWaiter.interrupt();
        pendingJoin.complete("READY");
        joinWaiter.join();

        check("READY".equals(joined.get())
              && joinInterruptRetained.get(),
              "join returns normally and preserves interrupt flag");

        System.out.println("timeoutException=" + timedOut);
        System.out.println("getInterrupted=" + getInterrupted.get());
        System.out.println("getInterruptFlagCleared=" + interruptCleared.get());
        System.out.println("joinResult=" + joined.get());
        System.out.println("joinInterruptFlagRetained=" +
            joinInterruptRetained.get());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 TimeoutInterruptionDemo.java
java TimeoutInterruptionDemo
```

**Stdout đã kiểm chứng:**

```text
timeoutException=true
getInterrupted=true
getInterruptFlagCleared=true
joinResult=READY
joinInterruptFlagRetained=true
PASS
```

**Diễn giải:**

- `get(0, MILLISECONDS)` trên pending future ném TimeoutException ngay vì không có thời gian chờ.
- Một thread khác đang chờ `get()` bị interrupt và đi vào nhánh `InterruptedException`.
- Cờ interrupt của get-waiter sau khi nhận exception đã bị xóa; ở test này chủ đích **đo hành vi**, không phải mẫu xử lý production.
- Join-waiter bị interrupt trước khi future hoàn thành, nhưng `join()` vẫn trả `"READY"` khi kết quả có sẵn, và trạng thái interrupt vẫn được ghi nhận.
- Test không dùng thời gian ngủ để chứng minh trạng thái, nên tránh phụ thuộc vào scheduler theo mức mili giây.

## 11. CancellationException: trường hợp đặc biệt không bọc như lỗi thông thường

`CompletableFuture.cancel(mayInterruptIfRunning)` cố gắng hoàn thành future theo kiểu cancellation. Với `CompletableFuture`, hủy được thể hiện như **exceptional completion với CancellationException**.

Khi gọi `get` hoặc `join` trực tiếp trên chính future bị hủy, ngoại lệ có thể là **`CancellationException` trực tiếp**, không phải bắt buộc `ExecutionException` hay `CompletionException`. Do đó:

```java
try {
    future.join();
} catch (CancellationException cancel) {
    // Future đã bị hủy.
} catch (CompletionException failure) {
    // Failure khác, có thể xem failure.getCause().
}
```

**Một dependent stage lại khác.** Nếu future cha bị hủy, một stage như `cancelled.thenApply(...)` thường hoàn thành **ngoại lệ với CompletionException mà cause là CancellationException**. Vì vậy không thể luôn khẳng định “nếu source bị hủy thì join trên mọi stage sẽ ném CancellationException trực tiếp”.

### cancel(true) có dừng computation đang chạy không?

**Không nên tin rằng `cancel(true)` chắc chắn interrupt tác vụ nền.** JavaDoc của `CompletableFuture.cancel` cho biết tham số `mayInterruptIfRunning` **không có tác dụng với implementation này**, vì interruption không được dùng làm cơ chế kiểm soát quá trình xử lý. Việc hủy **trạng thái future** không nhất thiết dừng được I/O/CPU do một thư viện hoặc thread khác đang thực hiện.

Nếu nghiệp vụ yêu cầu dừng công việc thật, cần một cancellation token, timeout phía I/O, Future/Executor phù hợp hoặc cơ chế dừng có cộng tác. Không coi việc `isCancelled() == true` là bằng chứng một giao dịch nền đã ngừng.

### isDone và isCompletedExceptionally sau khi cancel

Một future trực tiếp bị cancel có thể đồng thời:

- `isDone() == true`.
- `isCancelled() == true`.
- `isCompletedExceptionally() == true`.

Những trạng thái này không mâu thuẫn. `isDone` nghĩa là đã hoàn thành ở bất kỳ dạng nào; `isCompletedExceptionally` bao gồm cả cancellation.

## 12. Chương trình 4 — cancel, getNow và dependent failure

Tệp **`CancellationAndGetNowDemo.java`** kiểm rõ trường hợp giá trị dự phòng khi pending và exception khi canceled.

```java
import java.util.concurrent.*;

public class CancellationAndGetNowDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        String before = pending.getNow("NOT_READY");
        pending.complete("READY");
        String after = pending.getNow("NOT_READY");

        check("NOT_READY".equals(before) && "READY".equals(after),
              "getNow is non-blocking");

        CompletableFuture<String> cancelled = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
            cancelled.thenApply(String::length);

        boolean cancellationAccepted = cancelled.cancel(true);
        boolean getCancelled = false;
        boolean joinCancelled = false;
        boolean getNowCancelled = false;
        boolean dependentWrapped = false;

        try {
            cancelled.get();
        } catch (CancellationException expected) {
            getCancelled = true;
        }

        try {
            cancelled.join();
        } catch (CancellationException expected) {
            joinCancelled = true;
        }

        try {
            cancelled.getNow("FALLBACK");
        } catch (CancellationException expected) {
            getNowCancelled = true;
        }

        try {
            dependent.join();
        } catch (CompletionException ex) {
            dependentWrapped =
                ex.getCause() instanceof CancellationException;
        }

        check(cancellationAccepted && cancelled.isCancelled(),
              "cancelled");
        check(cancelled.isDone() && cancelled.isCompletedExceptionally(),
              "cancelled state");
        check(getCancelled && joinCancelled && getNowCancelled,
              "cancellation exceptions");
        check(dependentWrapped, "dependent wraps cancellation");

        System.out.println("getNowPending=" + before);
        System.out.println("getNowCompleted=" + after);
        System.out.println("cancelAccepted=" + cancellationAccepted);
        System.out.println("isCancelled=" + cancelled.isCancelled());
        System.out.println("isCompletedExceptionally=" +
            cancelled.isCompletedExceptionally());
        System.out.println("getThrowsCancellation=" + getCancelled);
        System.out.println("joinThrowsCancellation=" + joinCancelled);
        System.out.println("getNowThrowsCancellation=" + getNowCancelled);
        System.out.println("dependentCompletionCauseCancellation=" +
            dependentWrapped);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CancellationAndGetNowDemo.java
java CancellationAndGetNowDemo
```

**Stdout đã kiểm chứng:**

```text
getNowPending=NOT_READY
getNowCompleted=READY
cancelAccepted=true
isCancelled=true
isCompletedExceptionally=true
getThrowsCancellation=true
joinThrowsCancellation=true
getNowThrowsCancellation=true
dependentCompletionCauseCancellation=true
PASS
```

**Giải thích theo ba trường hợp riêng:**

1. Future **pending**: `getNow("NOT_READY")` trả giá trị dự phòng.
2. Future **completed bình thường**: `getNow` trả `"READY"`.
3. Future **cancelled**: `getNow` không trả fallback mà ném CancellationException. `get`/`join` trên chính future bị hủy cũng ném CancellationException trực tiếp.
4. Dependent stage trên future bị hủy có thể báo lỗi qua CompletionException với cause CancellationException, cho thấy **vị trí trong pipeline** ảnh hưởng lớp wrapper quan sát được.

Đừng chuyển mọi `CancellationException` thành “lỗi mạng” hoặc tự retry. Cancellation có thể là tín hiệu do người dùng, request hoặc hệ thống chủ động tạo ra.

## 13. Xử lý lỗi trong pipeline mà không block: exceptionally, handle, whenComplete

Không phải lúc nào cũng cần chờ rồi mới xử lý lỗi. `CompletableFuture` có các phép biến đổi stage để **phục hồi**, **ghi nhận** hoặc **ánh xạ** thất bại.

### exceptionally: phục hồi nếu lỗi

```java
CompletableFuture<Integer> safe =
    upstream.exceptionally(error -> -1);
```

Nếu `upstream` hoàn thành bình thường, giá trị được truyền qua. Nếu upstream hoàn thành ngoại lệ, callback được gọi và có thể trả giá trị dự phòng cùng kiểu T. Đây là **một stage mới**; không làm upstream đã thất bại bỗng trở thành thành công.

Không dùng một fallback như `-1` trong ứng dụng thật nếu `-1` có thể bị hiểu là kết quả hợp lệ hoặc gây mất thông tin. Nên chọn một biểu diễn kết quả có ý nghĩa domain.

### handle: ánh xạ cả thành công lẫn lỗi

```java
CompletableFuture<String> normalized =
    upstream.handle((value, error) ->
        error == null ? "OK:" + value : "FAILED");
```

Callback của `handle` nhận **giá trị nếu thành công** và **exception nếu thất bại**. Nó trả kết quả mới và có thể chuyển sang **kiểu khác**. Đây là điểm khác với `exceptionally` chủ yếu dùng khi lỗi và trả cùng loại T.

### whenComplete: quan sát side effect, không tự phục hồi

```java
CompletableFuture<Integer> observed =
    upstream.whenComplete((value, error) -> {
        if (error != null) {
            // Ghi log/metrics, không trả giá trị fallback ở đây.
        }
    });
```

`whenComplete` phục vụ quan sát, không phải hàm biến đổi kết quả. Khi upstream lỗi, stage từ `whenComplete` thường **tiếp tục lỗi**. Nếu callback `whenComplete` tự ném exception trong lúc upstream thành công, stage mới có thể thất bại vì exception đó. Nếu upstream vốn đã lỗi thì lỗi upstream có quyền ưu tiên theo hợp đồng method.

### Chọn đúng mục tiêu

| Mục tiêu | Toán tử |
| --- | --- |
| Chuyển dữ liệu khi thành công | `thenApply` |
| Bắt đầu một công đoạn async khác | `thenCompose` |
| Thay thế giá trị khi lỗi | `exceptionally` |
| Dùng cả value và error để tạo kết quả mới | `handle` |
| Ghi nhận kết quả/lỗi, giữ semantics chính | `whenComplete` |
| Chờ kết quả tại điểm đồng bộ | `get` hoặc `join` |
| Chờ với timeout tại điểm đồng bộ | `get(timeout,unit)` |

**Quan trọng:** các callback có thể chạy trên luồng hoàn thành stage hoặc executor tùy biến thể và trạng thái pipeline. Không thực hiện blocking I/O kéo dài ngay trong callback đồng bộ mà không hiểu executor, nhất là khi dùng ForkJoin common pool.

## 14. Chương trình 5 — whenComplete không phục hồi, exceptionally và handle có thể phục hồi

Tệp **`FailureRecoveryDemo.java`** kiểm cả ba phương thức trên.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class FailureRecoveryDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> failed =
            CompletableFuture.completedFuture(5).thenApply(n -> {
                throw new IllegalStateException("bad-transform");
            });

        AtomicBoolean observed = new AtomicBoolean(false);
        CompletableFuture<Integer> observedOnly =
            failed.whenComplete((value, error) -> {
                observed.set(error != null);
            });

        boolean whenCompleteStillFails = false;
        try {
            observedOnly.join();
        } catch (CompletionException ex) {
            whenCompleteStillFails =
                ex.getCause() instanceof IllegalStateException;
        }

        int fallback = failed.exceptionally(error -> -1).join();
        int handled = failed.handle((value, error) ->
            error == null ? value : 0).get();
        int healthy = CompletableFuture.completedFuture(8)
            .thenApply(n -> n * 2).get();

        check(observed.get() && whenCompleteStillFails,
              "whenComplete observes, does not recover");
        check(fallback == -1 && handled == 0 && healthy == 16,
              "recovery operators");

        System.out.println("observedFailure=" + observed.get());
        System.out.println("whenCompleteStillFails=" +
            whenCompleteStillFails);
        System.out.println("exceptionallyFallback=" + fallback);
        System.out.println("handleFallback=" + handled);
        System.out.println("healthyPipeline=" + healthy);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 FailureRecoveryDemo.java
java FailureRecoveryDemo
```

**Stdout đã kiểm chứng:**

```text
observedFailure=true
whenCompleteStillFails=true
exceptionallyFallback=-1
handleFallback=0
healthyPipeline=16
PASS
```

**Các điểm cần hiểu:**

- Upstream thất bại vì `IllegalStateException` ném từ `thenApply`.
- `whenComplete` được gọi, ghi nhận có lỗi, nhưng `observedOnly.join()` vẫn ném CompletionException.
- `exceptionally` trên upstream tạo stage mới có kết quả `-1`.
- `handle` cũng tạo kết quả mới `0` theo logic cụ thể.
- Một pipeline thành công không kích hoạt fallback, vẫn cho giá trị `16`.
- Việc phục hồi có **chủ đích và có kiểu trả về**, không phải dùng try/catch bắt tất cả exceptions rồi trả null.

## 15. Cẩn trọng với nguyên nhân ngoại lệ nhiều tầng

Một ứng dụng có thể nhận chuỗi wrapper:

```text
ExecutionException
    -> CompletionException
         -> IOException
```

hoặc:

```text
CompletionException
    -> IllegalArgumentException
```

Cấu trúc cụ thể phụ thuộc vào việc thư viện tạo future như thế nào, có hoàn thành với CompletionException sẵn hay không, và stage bị quan sát ở đâu.

### Nguyên tắc unwrap có kiểm soát

Nếu cần phân loại nguyên nhân, có thể loại bỏ **những wrapper thực sự biết** và giữ nguyên toàn bộ exception làm dữ liệu chẩn đoán:

```java
// Đoạn minh họa độc lập về thao tác Throwable, không phải
// một chương trình có main().
static Throwable rootOfCompletion(Throwable error) {
    Throwable current = error;
    while ((current instanceof ExecutionException
            || current instanceof CompletionException)
           && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **mẫu minh họa cho exception bất đồng bộ**, không phải hàm “lấy root cause chung” cho mọi trường hợp có thể tồn tại trên JVM. Trong code production, cần lưu exception gốc để truy vết và giới hạn việc unwrap theo ranh giới của lớp ứng dụng.

**Không tự động unwrap `CancellationException` thành error rồi retry.** Cancellation là trạng thái có thể do người dùng hoặc hệ thống chủ động yêu cầu. Cần xử lý nó như một tín hiệu điều khiển khi hợp đồng có phân biệt hủy.

### Không nuốt lỗi bằng catch Exception

Mẫu code sau là anti-pattern:

```java
// Mã sai về mặt thiết kế trong phần lớn trường hợp.
try {
    return future.join();
} catch (Exception ignored) {
    return null;
}
```

Nó có thể biến một lỗi nghiêm trọng thành giá trị null hợp lệ và che giấu sự khác nhau giữa “không tìm thấy”, “tác vụ lỗi”, “tác vụ bị hủy”. Hãy thiết kế một kiểu kết quả tường minh hoặc ánh xạ exception sang domain error đúng nghĩa.

## 16. Ở vị trí nào nên gọi get/join?

Trong kiến trúc bất đồng bộ, gọi `get/join` ở **mọi stage** làm mất lợi ích của CompletableFuture:

```java
// Không khuyến khích: chặn ngay trong callback.
CompletableFuture<Integer> result =
    CompletableFuture.completedFuture("key")
        .thenApply(key -> lookupAsync(key).join());
```

Đoạn trên có thể chặn thread đang thực thi callback. Nếu `lookupAsync` cũng phải chờ một executor giới hạn số luồng, có nguy cơ cạn thread, nghẽn hoặc deadlock theo thiết kế executor.

Thay bằng composition:

```java
// Phù hợp khi lookupAsync trả CompletableFuture<Integer>.
CompletableFuture<Integer> result =
    CompletableFuture.completedFuture("key")
        .thenCompose(key -> lookupAsync(key));
```

**Lưu ý:** hai snippet giả định có phương thức `lookupAsync` trong code ứng dụng; chúng không phải chương trình chạy độc lập. Demo có thể chạy đầy đủ về `thenCompose` đã nằm ở mục 7.

Có ba vùng dùng get/join hợp lý:

1. **Biên đồng bộ thực sự:** hàm `main`, CLI hoặc test cần chờ kết quả cuối.
2. **Lớp adapter bắt buộc trả giá trị đồng bộ:** có chính sách timeout, interruption và exception rõ.
3. **Test xác minh stage:** chờ future hoàn thành để assert kết quả/cause, luôn có cơ chế bảo đảm stage có thể kết thúc hoặc có timeout ở các test thực thi async không xác định.

Ở lớp web/event loop hoặc executor phục vụ nhiều request, tránh block kéo dài. Nếu framework hỗ trợ trả CompletionStage hay xử lý callback, ưu tiên chuyển tiếp kết quả bất đồng bộ theo contract.

### get/join không làm công việc async biến thành đồng bộ tuyệt đối

Một stage có thể đã chạy nền trước đó, và `join` chỉ chờ kết quả. Sự khác biệt giữa `get`/`join` nằm chủ yếu ở **hợp đồng chờ và ngoại lệ**, không phải một phương thức “chạy task” còn phương thức kia “không chạy task”.

## 17. Quản lý timeout, interruption và cancellation trong service

Một service đồng bộ gọi vào CompletableFuture cần ba quyết định riêng biệt:

### Thời gian chờ tối đa

Dùng `get(timeout)` khi caller phải trả lời trong một deadline. Nếu timeout, quyết định công việc nền được tiếp tục hay hủy; không ngầm khẳng định TimeoutException nghĩa là tác vụ đã dừng.

### Yêu cầu dừng do interruption

Khi `InterruptedException` xuất hiện, bảo toàn tín hiệu hủy và cờ interrupt nếu không ném tiếp. Đừng chạy lại `get()` vô hạn trong catch, vì có thể làm mất khả năng shutdown thread.

### Yêu cầu hủy của chính future

`CancellationException` có thể đi trực tiếp qua `get`/`join` trên canceled future, hoặc nằm trong cause của wrapper trên dependent. Cần mapping rõ sang trạng thái “canceled” thay vì cùng nhãn với lỗi tính toán.

### Retry phải cẩn thận

Chỉ retry với loại lỗi và nghiệp vụ cho phép. Nếu tác vụ bị timeout ở caller nhưng vẫn chạy, một retry mới có thể tạo công việc trùng. Với thao tác có side effect (thanh toán, tạo đơn, gửi email), cần idempotency và trạng thái kết quả nền rõ ràng.

### Không làm mất stacktrace và cause

Khi ánh xạ lỗi, truyền cause vào exception mới hoặc lưu trace ID/stacktrace ở nơi quan sát được. Trả cho người dùng thông báo an toàn, không tiết lộ chi tiết nội bộ nhạy cảm; nhưng không xóa dữ liệu chẩn đoán khỏi hệ thống.

## 18. Bảng quyết định cho những tình huống thực tế

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Chờ kết quả cuối ở CLI/test đơn giản, muốn cú pháp gọn | `join()` + xử lý CompletionException/CancellationException tại boundary |
| Gọi thư viện qua interface `Future<T>` | `get()` |
| Cần checked exception và chính sách ngắt rõ | `get()` |
| Cần timeout chờ của caller bằng API Java 8 | `get(timeout,TimeUnit)` |
| Cần kiểm ngay trạng thái không block | `getNow(default)`, nhưng hiểu rõ lỗi vẫn được ném |
| Cần xử lý fallback khi future lỗi | `exceptionally` |
| Cần transform cả success và failure | `handle` |
| Cần ghi log/metrics khi hoàn thành | `whenComplete` |
| Cần nối các phép async trả CompletableFuture | `thenCompose` |
| Cần xử lý tác vụ bị hủy | Nhận diện CancellationException và stage cha/con |
| Cần deadline thực cho I/O | Timeout/cancellation ở tầng I/O hoặc scheduler; không chỉ get(timeout) |
| Cần tránh chặn executor | Dùng pipeline non-blocking và chỉ đồng bộ ở boundary |
| Cần xác minh exception gốc | Kiểm `getCause()`, có thể unwrap wrapper được biết |
| Cần giữ Java 8 compatibility | Dùng API Java 8, không dùng convenience API của bản mới hơn |

### So với Future truyền thống

`Future.get` cung cấp một cửa chờ kết quả. `CompletableFuture` thêm khả năng **compose** stage, xử lý kết quả/lỗi bằng callback và đồng bộ nhiều công đoạn. Vì thế khi dùng CompletableFuture, điểm mạnh không chỉ là thay `get` bằng `join`: điểm mạnh là **tổ chức luồng xử lý bất đồng bộ** và chỉ quyết định cách chờ tại đúng ranh giới cần thiết.

## 19. Ma trận kiểm thử cần có

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Completed normal | `completedFuture("OK")` | get/join trả OK |
| Root IOException | `completeExceptionally(new IOException(...))` | get: ExecutionException; join: CompletionException |
| Error cause | Kiểm `getCause()` của wrapper | Root IOException được bảo toàn |
| Lambda failure | `thenApply` ném IllegalArgumentException | Dependent stage hoàn thành lỗi |
| Prewrapped error | `completeExceptionally(new CompletionException(root))` | get nhìn thấy ExecutionException với root; join có thể giữ wrapper |
| getNow pending | Chưa complete | Trả fallback ngay |
| getNow completed | Complete bình thường | Trả giá trị thực |
| getNow cancelled | Canceled future | Ném CancellationException, không fallback |
| Direct cancellation | `cancel(true)` | get/join ném CancellationException trực tiếp |
| Dependent of cancelled stage | `thenApply` nối future bị hủy | join có thể ném CompletionException, cause cancellation |
| isDone on cancel | Future bị cancel | true |
| isCompletedExceptionally on cancel | Future bị cancel | true |
| Timeout pending | `get(0, MILLISECONDS)` | TimeoutException |
| Completion after timeout | Future complete sau caller timeout | Future vẫn có thể thành công |
| get interrupted | Thread chờ pending get bị interrupt | InterruptedException |
| Interrupt flag after get | Catch InterruptedException | Cờ đã bị xóa trong test |
| join while interrupted | Thread bị interrupt, future sau đó complete | join trả kết quả, trạng thái interrupt được giữ |
| exceptionally | Failure + fallback | Tạo stage với giá trị fallback |
| handle | Failure + mapping | Tạo stage recovered |
| whenComplete | Failure + observer | Ghi nhận lỗi, vẫn failure |
| Healthy chain | thenApply trên completedFuture | Kết quả transform đúng |
| thenCompose | Hàm callback trả CompletableFuture | Không tạo future lồng |
| Service mapping | Root error vs cancellation | Không lẫn loại nghiệp vụ |
| Async executor | Blocking join trong callback | Được xem xét tránh nghẽn/starvation |
| Java 8 compatibility | Biên dịch `--release 8` | Không gọi API Java 9+ |

**Đừng chỉ kiểm `assertThrows(Exception.class)`**. Mục tiêu bài học là phân biệt chính xác **lớp ngoại lệ, cause và trạng thái future**. Dùng các future hoàn thành bằng fixture để test deterministic; với test concurrency thực, dùng latch/synchronization thay vì sleep tùy ý.

## 20. Những anti-pattern thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ join không ném lỗi vì không khai báo throws | Runtime exception vẫn làm flow thất bại | Catch/propagate theo contract |
| Catch chỉ `ExecutionException` khi gọi join | Bỏ lỡ CompletionException | Bắt wrapper đúng API |
| Catch chỉ `CompletionException` khi future canceled | Bỏ lỡ CancellationException trực tiếp | Xử lý cancel riêng |
| Catch InterruptedException rồi lờ đi | Thread không shutdown đúng | Restore flag hoặc propagate |
| Dùng `get()` không có deadline trong request có SLA | Có thể chờ vô hạn | get(timeout) và policy deadline |
| Coi get(timeout) tự hủy tác vụ | Work vẫn có thể chạy | Thiết kế cancellation/IO timeout |
| Dùng `getNow(default)` như error recovery | Exceptional completion vẫn ném lỗi | exceptionally/handle |
| Dùng `whenComplete` như phép thay giá trị khi lỗi | Error vẫn được truyền | exceptionally hoặc handle |
| Dùng `exceptionally` và nuốt mọi Throwable | Che lỗi lập trình/cancel | Phân loại rõ cause |
| Dùng `cancel(true)` như bằng chứng worker đã dừng | CompletableFuture không bắt buộc interrupt task | Cooperative cancellation/IO timeout |
| Gọi `join()` trong callback của pool nhỏ | Nghẽn hoặc deadlock | thenCompose/non-blocking |
| Retry mọi TimeoutException | Có thể nhân đôi side effect | Idempotency + chính sách retry |
| Không lưu cause khi chuyển exception | Mất thông tin debug | Bọc kèm cause hoặc trace |
| Dùng `failedFuture` trong mã Java 8 | API đó có từ Java 9 | new CompletableFuture + completeExceptionally |
| Dùng `orTimeout` trong mã Java 8 | API có từ Java 9 | get(timeout) / scheduler phù hợp |
| Nói mọi lỗi async luôn có đúng một wrapper | Cấu trúc wrapper có thể khác | Kiểm chain thực và unit tests |
| Chỉ kiểm isDone trước get rồi tin thành công | isDone cũng đúng khi lỗi/cancel | Kiểm kết quả hoặc completion status |
| Tự đoán task backend đã dừng khi future canceled | Side effect vẫn có thể diễn ra | Thiết kế lifecycle work riêng |

## 21. Bài tập thực hành có đáp án

### Bài 1 — Checked vs unchecked

**Đề:** một `CompletableFuture<Integer>` đã hoàn thành ngoại lệ bằng `IllegalStateException("bad")`. Phân biệt exception của `get()` và `join()`.

**Đáp án:** get ném `ExecutionException` và `getCause()` là IllegalStateException; join ném `CompletionException` và `getCause()` cũng là IllegalStateException. Không bắt trực tiếp IllegalStateException như ngoại lệ top-level từ hai API này trong trường hợp thông thường.

### Bài 2 — Future bị cancel

**Đề:** gọi `cancel(true)` trên future chưa hoàn thành, rồi gọi get và join trên chính future đó. Hai phương thức có nhất thiết ném các wrapper như bài 1 không?

**Đáp án:** không. Cả hai có thể ném `CancellationException` trực tiếp. `cancel(true)` không chứng minh computation bên dưới đã bị interrupt.

### Bài 3 — getNow

**Đề:** future chưa hoàn thành; gọi `getNow(99)` thì được gì? Nếu future đã hoàn thành lỗi thì sao?

**Đáp án:** pending trả 99 ngay. Nếu future hoàn thành ngoại lệ thì có thể ném unchecked exception, không dùng 99 làm error fallback.

### Bài 4 — Timeout

**Đề:** gọi `get(100, MILLISECONDS)` và bắt TimeoutException. Future chắc chắn đã bị cancel chưa?

**Đáp án:** chưa. Chỉ có caller hết thời gian đợi; trạng thái future vẫn có thể pending. Cần chính sách riêng cho work chạy tiếp/hủy/retry.

### Bài 5 — Interruption

**Đề:** thread đang chờ get bị interrupt. Nếu bắt InterruptedException và không thể throw tiếp, nên làm gì?

**Đáp án:** thường cần gọi `Thread.currentThread().interrupt()` rồi xử lý/lan truyền trạng thái hủy theo contract của service, tránh nuốt tín hiệu.

### Bài 6 — Khi nào dùng exceptionally?

**Đề:** một stage lỗi nhưng business cho phép trả kết quả dự phòng. `whenComplete` có thay được `exceptionally` không?

**Đáp án:** không. `whenComplete` quan sát completion, còn `exceptionally` có thể tạo một stage thành công bằng cách trả fallback phù hợp.

### Bài 7 — thenCompose hay thenApply?

**Đề:** `lookupAsync(id)` trả `CompletableFuture<Order>`. Muốn có một `CompletableFuture<Order>` ở kết quả cuối thay vì một future lồng, chọn gì?

**Đáp án:** dùng `thenCompose(id -> lookupAsync(id))`. Không gọi join bên trong callback nếu có thể nối bất đồng bộ.

### Bài 8 — Cancellation trên dependent

**Đề:** stage A bị hủy; stage B được tạo bằng `A.thenApply(...)`. Vì sao `B.join()` có thể ném CompletionException thay vì CancellationException trực tiếp?

**Đáp án:** B là một **dependent stage đã hoàn thành ngoại lệ** do upstream cancellation, và lỗi có thể được bọc trong CompletionException; cần quan sát cause.

### Bài 9 — API cần timeout trên Java 8

**Đề:** một hàm đồng bộ phải chờ tối đa 300 ms để đọc kết quả của CompletableFuture. Có thể dùng `join(300, MILLISECONDS)` không?

**Đáp án:** không có overload ấy trong Java 8. Dùng `get(300, TimeUnit.MILLISECONDS)` và xử lý TimeoutException, InterruptedException, ExecutionException, CancellationException.

### Bài 10 — Chuyển exception cho tầng controller

**Đề:** controller gọi một future thất bại do IOException. Có nên trả nguyên stacktrace CompletionException cho client?

**Đáp án:** không. Phân loại cause, trả mã lỗi và thông báo an toàn theo contract; ghi log/trace có context và cause cho hệ thống chẩn đoán.

## 22. Câu hỏi tự kiểm tra

**1. get() của CompletableFuture kế thừa hợp đồng từ interface nào?**  
`Future<T>`.

**2. Khi thành công, get và join có trả khác giá trị không?**  
Không; chúng đều trả kết quả T.

**3. get ném wrapper nào khi tác vụ thất bại?**  
`ExecutionException` trong trường hợp thất bại thông thường.

**4. join ném wrapper nào khi tác vụ thất bại?**  
`CompletionException` trong trường hợp thất bại thông thường.

**5. Vì sao checked và unchecked ở đây không chứng minh lỗi nặng hay nhẹ?**  
Chúng phản ánh thiết kế hợp đồng API; phải xem nguyên nhân gốc và ngữ cảnh nghiệp vụ.

**6. get có overload chờ timeout không?**  
Có: `get(long, TimeUnit)`.

**7. join Java 8 có overload timeout không?**  
Không.

**8. TimeoutException từ get(timeout) có tự cancel future không?**  
Không.

**9. Bị cancel trực tiếp thì get/join nhất thiết ném wrapper thông thường không?**  
Không, có thể ném `CancellationException` trực tiếp.

**10. getNow(default) dùng default để xử lý lỗi đã xảy ra không?**  
Không; default áp dụng khi future chưa hoàn thành.

**11. whenComplete có tự recovery không?**  
Không, nó chủ yếu quan sát completion.

**12. exceptionally khác handle ra sao?**  
exceptionally chạy khi lỗi để cung cấp fallback cùng kiểu; handle nhận cả value và error, có thể tạo kiểu mới.

**13. Khi future phụ thuộc bị lỗi từ source, cause có thể đi qua nhiều wrapper không?**  
Có. Cần kiểm chain có kiểm soát, không giả định độ sâu cố định.

**14. cancel(true) của CompletableFuture có đảm bảo interrupt tác vụ đang chạy không?**  
Không.

**15. Khi nào chọn thenCompose?**  
Khi callback trả một CompletableFuture/CompletionStage khác và muốn nối phẳng pipeline bất đồng bộ.

## Tài liệu Java SE 8 chính thức

- [CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html) — `get`, `join`, `getNow`, `completeExceptionally`, `cancel`, `exceptionally`, `handle`, `whenComplete` và `thenCompose`.
- [CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html) — hợp đồng composition và callback xử lý kết quả/lỗi.
- [Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html) — `get()`, `get(timeout)` và cancellation.
- [ExecutionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ExecutionException.html) — checked wrapper của Future.get.
- [CompletionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionException.html) — unchecked wrapper của CompletableFuture.
- [CancellationException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CancellationException.html) — trạng thái hủy.
- [TimeoutException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeoutException.html) — thời gian chờ hết hạn.
- [TimeUnit](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeUnit.html) — đơn vị thời gian cho get(timeout).
- [InterruptedException](https://docs.oracle.com/javase/8/docs/api/java/lang/InterruptedException.html) và [Thread](https://docs.oracle.com/javase/8/docs/api/java/lang/Thread.html) — tín hiệu ngắt và cờ interrupt.
- [CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html) — phối hợp test concurrency mà không đoán lịch thread.

**Ghi nhớ:** `get` và `join` đều chờ kết quả nhưng khác **hợp đồng ngoại lệ**: lỗi thông thường qua `ExecutionException` (checked) hoặc `CompletionException` (unchecked), còn cancellation có thể ném `CancellationException` trực tiếp. `get(timeout)` giới hạn **thời gian chờ**, không tự dừng tác vụ; `get` có thể phản ứng với interruption còn `join` không khai báo InterruptedException. Trong ứng dụng bất đồng bộ, ưu tiên `thenCompose` và các stage xử lý lỗi khi thích hợp; chỉ block tại ranh giới có chủ đích và luôn giữ nguyên nhân gốc để chẩn đoán.