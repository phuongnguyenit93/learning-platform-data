# CompletionException, ExecutionException và nguyên nhân gốc khi ghép tác vụ (Java 8)

Khi ghép nhiều `CompletableFuture`, thất bại thường không xuất hiện ngay tại nơi nó được tạo ra. Lỗi có thể phát sinh trong một hàm gọi mạng, đi qua `thenCompose`, làm `thenCombine` hoặc `allOf` hoàn thành ngoại lệ, rồi cuối cùng được quan sát tại `join()` hoặc `get()`. Khi đó stack trace có thể bắt đầu bằng `CompletionException` hoặc `ExecutionException`, trong khi **lỗi nghiệp vụ hoặc hạ tầng thực sự** lại là `IOException`, `IllegalArgumentException`, `TimeoutException` hoặc một ngoại lệ khác nằm trong `getCause()`.

Ví dụ một bước lấy tồn kho thất bại:

```text
fetchStock(sku) -> IOException("stock-service-down")
       |
       v
thenCompose -> CompletableFuture<Integer> hoàn thành ngoại lệ
       |
       v
thenApply phía sau không được gọi
       |
       +--- join() -> CompletionException
       |                    -> IOException("stock-service-down")
       |
       +--- get()  -> ExecutionException
                            -> IOException("stock-service-down")
```

**Mục tiêu của bài này** là hiểu được **mối quan hệ giữa lỗi gốc, exceptional completion, wrapper ở ranh giới quan sát, hành vi của phép ghép tác vụ, cancellation và các bước recovery**. Chúng ta sẽ tìm hiểu cách phân tích cause chain mà không nuốt lỗi, lý do `allOf` không tự tổng hợp tất cả ngoại lệ, và cách chọn `handle`, `exceptionally` hoặc `whenComplete`.

Bài thuộc nhóm **Ghép tác vụ** trong module **Java 8**, sử dụng các API `java.util.concurrent.CompletableFuture`, `CompletionStage` và exception types **vẫn đang được sử dụng trên Java hiện đại**. Các mã hoàn chỉnh đều biên dịch ở mức Java 8, có kiểm thử assertions và stdout được xác minh. Không sử dụng những tiện ích chỉ có từ Java 9 trở lên như `CompletableFuture.failedFuture`, `orTimeout` hay `exceptionallyCompose`.

## 1. Phân biệt ba lớp: nguồn lỗi, stage lỗi và người quan sát

Khi một lambda trong pipeline ném exception, Java đánh dấu **stage liên quan đã hoàn thành ngoại lệ**. Stage tiếp theo có thể lan truyền thất bại hoặc xử lý nó, tùy toán tử. Phương thức lấy kết quả ở cuối pipeline quyết định **kiểu wrapper quan sát được**.

Ba lớp ngữ nghĩa cần tách:

1. **Lỗi gốc:** ví dụ `IOException("stock-service-down")` hoặc `IllegalArgumentException("invalid-code")`. Nó nói **điều gì đã hỏng**.
2. **Exceptional completion của stage:** một `CompletableFuture<T>` đã hoàn thành nhưng **không có giá trị thành công**. Lỗi được lưu và có thể truyền sang các dependent stages.
3. **Wrapper tại điểm lấy kết quả:** `get()` thường ném `ExecutionException`, còn `join()` thường ném `CompletionException`. Wrapper cho biết **cách người gọi quan sát thất bại**, không nhất thiết là nguyên nhân nghiệp vụ.

Một hàm gọi `future.get()` không khiến IOException do async task phát sinh trở thành checked IOException trực tiếp tại dòng gọi. Nó thường trở thành **cause của ExecutionException**.

Tương tự, `future.join()` không ném IOException checked trực tiếp; nó thường ném **CompletionException** có IOException làm cause.

### Checked và unchecked

| Thuộc tính | `ExecutionException` | `CompletionException` |
| --- | --- | --- |
| Loại | Checked exception | Unchecked, kế thừa RuntimeException |
| Thường thấy tại | `Future.get()` / `CompletableFuture.get()` | `CompletableFuture.join()` / `getNow()` và luồng lỗi completion |
| Có `getCause()`? | Có | Có |
| Bản thân nói được lỗi nghiệp vụ? | Không đủ, cần xem cause | Không đủ, cần xem cause |
| Có cần khai báo/bắt khi gọi trực tiếp? | Có, do checked | Không bắt buộc về cú pháp |
| Có đảm bảo luôn là lớp ngoài cùng? | Không với cancellation trực tiếp | Không với cancellation trực tiếp |

**Không so mức độ nghiêm trọng bằng lớp wrapper.** Checked/unchecked là quyết định thiết kế API; `IOException` ở dưới hai wrapper vẫn có cùng bản chất.

## 2. get(), join(), getNow(): cùng lỗi, các hình thức quan sát khác nhau

Khi future thành công:

```java
// Đoạn minh họa.
CompletableFuture<Integer> done =
    CompletableFuture.completedFuture(42);

int a = done.get();  // 42, cần xử lý checked exceptions ở caller
int b = done.join(); // 42
```

Khi future thất bại:

```java
// Đoạn minh họa, trong phương thức có import phù hợp.
IOException root = new IOException("inventory-down");
CompletableFuture<Integer> failed = new CompletableFuture<>();
failed.completeExceptionally(root);

try {
    failed.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (ExecutionException e) {
    Throwable cause = e.getCause(); // thường là root
}

try {
    failed.join();
} catch (CompletionException e) {
    Throwable cause = e.getCause(); // thường là root
}
```

Trong Java 8, `getNow(valueIfAbsent)` **không chờ**. Nếu future còn pending, trả giá trị dự phòng; nhưng nếu future đã **hoàn thành ngoại lệ**, nó thường ném `CompletionException`. Giá trị fallback của `getNow` **không phải error handler**.

**Ngoại lệ cần đặc biệt nhớ:** khi gọi trực tiếp trên một future đã bị cancel, `get`, `join` và `getNow` có thể ném **`CancellationException` trực tiếp**; không được viết code chỉ bắt hai wrapper rồi tin rằng đã bao phủ toàn bộ exceptional completion.

## 3. Chương trình 1 — cùng root cause, hai wrapper

Tệp **`FailureBoundaryDemo.java`** tạo một IOException duy nhất, gắn nó vào future bằng `completeExceptionally` rồi kiểm tra lớp wrapper, kiểu cause và việc bảo toàn chính instance lỗi gốc.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class FailureBoundaryDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> success =
            CompletableFuture.completedFuture(42);

        IOException root = new IOException("inventory-down");
        CompletableFuture<Integer> failed = new CompletableFuture<>();
        failed.completeExceptionally(root);

        String getWrapper = "", joinWrapper = "";
        boolean getRootSame = false, joinRootSame = false;

        try {
            failed.get();
            throw new AssertionError("expected failure");
        } catch (ExecutionException ex) {
            getWrapper = ex.getClass().getSimpleName();
            getRootSame = ex.getCause() == root;
        }

        try {
            failed.join();
            throw new AssertionError("expected failure");
        } catch (CompletionException ex) {
            joinWrapper = ex.getClass().getSimpleName();
            joinRootSame = ex.getCause() == root;
        }

        boolean getNowFailed = false;
        try {
            failed.getNow(-1);
        } catch (CompletionException ex) {
            getNowFailed = ex.getCause() == root;
        }

        check(success.get() == 42 && success.join() == 42,
              "success");
        check("ExecutionException".equals(getWrapper)
            && "CompletionException".equals(joinWrapper),
              "wrappers");
        check(getRootSame && joinRootSame && getNowFailed,
              "root cause preserved");

        System.out.println("success=" + success.join());
        System.out.println("getWrapper=" + getWrapper);
        System.out.println("joinWrapper=" + joinWrapper);
        System.out.println("getCauseSameRoot=" + getRootSame);
        System.out.println("joinCauseSameRoot=" + joinRootSame);
        System.out.println("getNowCauseSameRoot=" + getNowFailed);
        System.out.println("PASS");
    }
}
```

Biên dịch/chạy với JDK 8 trở lên:

```bash
javac -encoding UTF-8 FailureBoundaryDemo.java
java FailureBoundaryDemo
```

Nếu sử dụng JDK mới và muốn xác minh **chỉ dùng API Java 8**:

```bash
javac --release 8 -encoding UTF-8 FailureBoundaryDemo.java
java FailureBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
success=42
getWrapper=ExecutionException
joinWrapper=CompletionException
getCauseSameRoot=true
joinCauseSameRoot=true
getNowCauseSameRoot=true
PASS
```

Giải thích:

- `completeExceptionally(root)` khiến future kết thúc **không có giá trị thành công**.
- `get()` bọc thất bại thành ExecutionException.
- `join()` và `getNow()` trên future lỗi bọc thành CompletionException.
- `ex.getCause() == root` được dùng trong **fixture kiểm thử** để chứng minh lỗi gốc được giữ đúng instance. Ở hệ thống thật, nhiều framework có thể chủ động tạo wrapper khác, vì vậy phân loại nghiệp vụ nên dựa vào **loại lỗi, mã lỗi và contract**, không phụ thuộc mọi tầng phải bảo toàn object identity.
- Dòng `PASS` chỉ xuất hiện nếu toàn bộ assertions đạt.

## 4. Ghép tác vụ: thất bại không dừng ở stage nơi nó phát sinh

`CompletableFuture` cho phép kết nối nhiều phép biến đổi:

```text
Stage A
   |
   v
thenApply / thenCompose
   |
   v
Stage B
   |
   v
thenApply
   |
   v
Stage C
```

Nếu **Stage B hoàn thành ngoại lệ** và không có nhánh phục hồi:

- Một `thenApply` phụ thuộc bình thường thường **không thực thi** hàm biến đổi của nó.
- Dependent stage cũng thường hoàn thành ngoại lệ do lỗi upstream.
- Callback xử lý lỗi như `exceptionally`, `handle` và `whenComplete` có cơ hội quan sát lỗi theo hợp đồng riêng.
- Khi cuối pipeline gọi `get` hoặc `join`, wrapper phản ánh API lấy kết quả tại điểm đó.

**Không nên suy rằng Stage C vẫn được gọi với null khi Stage B lỗi.** Nếu stage upstream thất bại, callback chỉ dành cho thành công của `thenApply` không nhận null thay thế một cách mặc định. Có thể có `null` hợp lệ khi upstream **thành công với giá trị null**, nhưng đó là trường hợp khác hẳn.

### Khi thenCompose trả một future đã lỗi

`thenCompose` dùng khi callback trả `CompletionStage<U>` hoặc `CompletableFuture<U>`. Nó tạo một stage nối phẳng kết quả của future con.

```java
// Đoạn minh họa; fetchStockAsync(sku) trả CompletableFuture<Integer>.
CompletableFuture<Integer> stock =
    CompletableFuture.completedFuture("A-1")
        .thenCompose(sku -> fetchStockAsync(sku));
```

Nếu `fetchStockAsync` trả một future hoàn thành ngoại lệ, future kết quả của `thenCompose` cũng thất bại, thay vì trả một `CompletableFuture<CompletableFuture<Integer>>` lồng.

**Tránh thay bằng `thenApply(key -> fetchStockAsync(key).join())`** chỉ để gỡ future lồng: cách này có thể chặn thread đang chạy callback và tạo nguy cơ nghẽn executor. Dùng `thenCompose` đúng mục đích.

## 5. Chương trình 2 — IOException đi qua thenCompose, thenApply bị bỏ qua

Tệp **`ComposedFailureDemo.java`** dùng future thất bại có kiểm soát, không phụ thuộc mạng hay timing, để kiểm cause lan qua nhiều stage.

```java
import java.io.IOException;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ComposedFailureDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static CompletableFuture<Integer> fetchStock(
            String sku, IOException root) {
        CompletableFuture<Integer> failed = new CompletableFuture<>();
        failed.completeExceptionally(root);
        return failed;
    }

    public static void main(String[] args) {
        IOException root = new IOException("stock-service-down");
        AtomicInteger downstreamCalls = new AtomicInteger();

        CompletableFuture<Integer> chain =
            CompletableFuture.completedFuture("A-1")
                .thenCompose(sku -> fetchStock(sku, root))
                .thenApply(stock -> {
                    downstreamCalls.incrementAndGet();
                    return stock + 10;
                });

        Throwable cause = null;
        try {
            chain.join();
            throw new AssertionError("must fail");
        } catch (CompletionException ex) {
            cause = ex.getCause();
        }

        check(cause == root && downstreamCalls.get() == 0,
              "root preserved, success stage skipped");

        CompletableFuture<Integer> healthy =
            CompletableFuture.completedFuture(7);
        int recovered = chain.exceptionally(ex -> -1).join();
        int independent = healthy.thenApply(n -> n * 2).join();

        check(recovered == -1 && independent == 14,
              "recovery does not change other stage");

        System.out.println("composedCause=" +
            cause.getClass().getSimpleName()
            + ":" + cause.getMessage());
        System.out.println("downstreamCalls=" + downstreamCalls.get());
        System.out.println("recovered=" + recovered);
        System.out.println("independent=" + independent);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ComposedFailureDemo.java
java ComposedFailureDemo
```

**Stdout đã kiểm chứng:**

```text
composedCause=IOException:stock-service-down
downstreamCalls=0
recovered=-1
independent=14
PASS
```

Bài học:

1. `thenCompose` nối một future trả lỗi với pipeline, cause vẫn là IOException ban đầu.
2. `thenApply` phía sau không chạy, vì nó chỉ nhận **giá trị thành công**. Giá trị `downstreamCalls=0` xác minh điều đó.
3. `exceptionally` tạo **stage hồi phục mới** trả `-1`; nó không sửa lịch sử thất bại của stage `chain` đã có.
4. Một future thành công **độc lập** vẫn chạy và trả 14, không tự bị lỗi vì pipeline khác thất bại.
5. Trong sản phẩm thật, fallback `-1` chỉ dùng khi nó có nghĩa nghiệp vụ rõ; đừng biến mọi lỗi hạ tầng thành một “giá trị hợp lệ” âm thầm.

### Lỗi nằm ở bước nào?

Với một chuỗi dài, nên gắn context tại ranh giới mỗi bước: tên bước, mã tác vụ/trace ID, loại thao tác và khóa nghiệp vụ không nhạy cảm. Nếu chỉ đợi đến `join()` ở cuối rồi log “CompletionException”, người vận hành sẽ không biết lỗi từ **tính giá**, **kiểm tồn kho**, **giao hàng** hay **ghi dữ liệu**.

Tuy nhiên không nhất thiết đặt `exceptionally` để **nuốt mọi lỗi** ở từng stage. Có thể dùng `whenComplete` để quan sát thất bại với context, rồi để stage lỗi tiếp tục lan tới một nơi chịu trách nhiệm xử lý.

## 6. thenCombine: một bên lỗi thì nhánh kết hợp không có giá trị để chạy

`thenCombine` ghép **hai stage thành công** rồi gọi BiFunction để tạo giá trị tổng hợp:

```java
CompletableFuture<Integer> total =
    priceFuture.thenCombine(quantityFuture,
        (price, quantity) -> price * quantity);
```

Nếu một stage đầu vào hoàn thành ngoại lệ, stage kết quả có thể hoàn thành ngoại lệ; **BiFunction không được gọi với một giá trị lỗi giả**. Nếu cả hai đều lỗi hoặc có races phức tạp, không nên dựa vào việc lỗi nào được chọn để đại diện làm cause trừ khi API/ứng dụng đã có hợp đồng riêng.

Tương tự, `thenAcceptBoth`, `runAfterBoth` và các phép chỉ dành cho kết quả thành công không nên được coi là nhánh error handling.

**Giới hạn quan trọng:** `thenCombine` không thu thập một danh sách lỗi của cả hai tác vụ để người gọi giải quyết. Nếu business cần báo *tất cả* lỗi kiểm tra độc lập, phải chuyển mỗi kết quả thành một giá trị mô tả thành công/thất bại trước khi combine, hoặc xây cấu trúc thu thập riêng.

## 7. allOf: barrier cho các tác vụ, không phải danh sách nguyên nhân lỗi

`CompletableFuture.allOf(f1, f2, f3)` trả về một **`CompletableFuture<Void>`** hoàn thành khi tất cả futures được cung cấp đã hoàn thành. Nếu một hoặc nhiều future hoàn thành ngoại lệ, future tổng cũng hoàn thành ngoại lệ, thường được quan sát qua CompletionException với một cause.

Điều **allOf không tự làm**:

- Nó không trả về `List<T>` gồm mọi kết quả.
- Nó không gom một danh sách tất cả exception của từng input.
- Nó không định nghĩa một “nguyên nhân gốc tổng hợp” duy nhất đầy đủ khi nhiều input cùng lỗi.
- Nó không tự tạo một chiến lược retry, dừng I/O hay bồi thường side effect.

Nếu cần biết **từng task nào thất bại**, giữ tham chiếu từng future và kiểm trạng thái/cause từng cái sau khi chúng hoàn thành, hoặc chuyển chúng thành dạng `Result<T>` để tổng hợp an toàn.

### Nếu có nhiều lỗi đồng thời?

Đừng khẳng định allOf bắt buộc chọn lỗi đầu tiên theo thời gian hay lỗi ở phần tử đầu danh sách. API không nên bị dùng như cơ chế xác định “lỗi ưu tiên” trong trường hợp nhiều future thất bại. Nếu thứ tự ưu tiên business quan trọng, xử lý thứ tự ấy **trong logic ứng dụng**.

## 8. anyOf: người hoàn thành trước quyết định outcome

`CompletableFuture.anyOf(f1, f2, ...)` trả về `CompletableFuture<Object>` hoàn thành với **kết quả hoặc exception của một future hoàn thành đầu tiên**.

Nếu một future hoàn thành ngoại lệ **trước** các future khác, `anyOf` có thể hoàn thành ngoại lệ dù những tác vụ còn lại về sau có thể thành công. Vì thế:

- `anyOf` là **race theo completion**, không phải toán tử “chờ thành công đầu tiên”.
- Những task còn lại không tự bị cancel chỉ vì anyOf đã hoàn thành.
- Nếu nhiều futures đã hoàn thành hoặc race sát nhau, không nên thiết kế nghiệp vụ dựa vào một thứ tự không được bảo đảm.
- Nếu muốn “first successful result”, cần logic riêng quản lý thất bại của từng nhánh và success thắng một cách có chủ đích.

Đặc biệt trong orchestration, đừng đọc `CompletionException` từ anyOf rồi tưởng rằng **tất cả các tác vụ** đều đã thất bại.

## 9. Chương trình 3 — lỗi qua thenCombine, allOf và anyOf

Tệp **`AggregateFailureDemo.java`** sử dụng đúng **một future lỗi** và một future thành công để quan sát việc lan truyền cause một cách xác định; `anyOf` còn có một future pending nên không có cuộc đua mơ hồ giữa nhiều kết quả hoàn thành.

```java
import java.io.IOException;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class AggregateFailureDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        IOException root = new IOException("price-down");
        CompletableFuture<Integer> price = new CompletableFuture<>();
        price.completeExceptionally(root);

        CompletableFuture<Integer> quantity =
            CompletableFuture.completedFuture(3);
        AtomicBoolean combinerRan = new AtomicBoolean(false);

        CompletableFuture<Integer> combined = price.thenCombine(
            quantity, (p, q) -> {
                combinerRan.set(true);
                return p * q;
            });

        boolean combineCause = false;
        try {
            combined.join();
        } catch (CompletionException ex) {
            combineCause = ex.getCause() == root;
        }

        CompletableFuture<Void> all = CompletableFuture.allOf(
            price, quantity);
        boolean allCause = false;
        try {
            all.join();
        } catch (CompletionException ex) {
            allCause = ex.getCause() == root;
        }

        CompletableFuture<Integer> stillPending = new CompletableFuture<>();
        CompletableFuture<Object> any = CompletableFuture.anyOf(
            stillPending, price);
        boolean anyCause = false;
        try {
            any.join();
        } catch (CompletionException ex) {
            anyCause = ex.getCause() == root;
        }

        check(combineCause && allCause && anyCause,
              "aggregation cause");
        check(!combinerRan.get(), "combiner not executed");
        check(!stillPending.isDone(), "anyOf does not complete source");

        System.out.println(
            "thenCombineCauseSameRoot=" + combineCause);
        System.out.println("combinerRan=" + combinerRan.get());
        System.out.println("allOfCauseSameRoot=" + allCause);
        System.out.println("anyOfCauseSameRoot=" + anyCause);
        System.out.println("pendingSourceStillPending=" +
            !stillPending.isDone());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 AggregateFailureDemo.java
java AggregateFailureDemo
```

**Stdout đã kiểm chứng:**

```text
thenCombineCauseSameRoot=true
combinerRan=false
allOfCauseSameRoot=true
anyOfCauseSameRoot=true
pendingSourceStillPending=true
PASS
```

**Giải thích:**

- `thenCombine` không gọi hàm nhân khi future giá đã lỗi.
- `allOf` hoàn thành ngoại lệ vì một trong hai future đầu vào lỗi.
- `anyOf` hoàn thành ngoại lệ theo `price`, vì nhánh còn lại là future pending tại thời điểm tạo `anyOf`.
- `anyOf` không làm `stillPending` hoàn thành/hủy.
- Ở **fixture cụ thể này**, cause trong ba stage kết quả đều tham chiếu cùng IOException; với orchestration phức tạp, nên kiểm qua cause chain và không giả định mọi tầng sẽ giữ object identity trong mọi kết hợp.
- Khi các input đồng thời lỗi, phải đọc riêng từng future nếu cần danh sách đầy đủ nguyên nhân.

## 10. Cause chain: không phải lúc nào chỉ có một lớp wrapper

Một thư viện có thể đã bọc lỗi trước khi hoàn thành future. Ví dụ:

```text
CompletionException
  -> ExecutionException
      -> IOException("gateway-503")
```

Khi gọi `join()`, wrapper `CompletionException` có thể được ném lại **chính instance đã được lưu**. Khi gọi `get()`, API có thể chuyển sang `ExecutionException` nhưng cause trực tiếp vẫn là một `ExecutionException` bên trong. Vì thế:

- `ex.getCause()` là **một bước** xuống cause chain, không phải lúc nào đã là lỗi cuối.
- Không nên phân loại lỗi chỉ bằng cách kiểm `ex.getCause() instanceof IOException` một lần trong mọi pipeline.
- Ngược lại, không được lột mọi loại wrapper tùy ý: một ngoại lệ nghiệp vụ có cause riêng có thể mang ngữ nghĩa quan trọng.
- Cần lưu **outer exception** để có stack trace/call boundary, và dùng phiên bản đã unwrap để **phân loại** nguyên nhân khi thật sự cần.

### Hàm unwrap các wrapper đã biết

Một đoạn minh họa cho exception của CompletableFuture:

```java
// Hàm minh họa; import java.util.concurrent.*.
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    int depth = 0;

    while ((current instanceof CompletionException
         || current instanceof ExecutionException)
         && current.getCause() != null
         && current.getCause() != current) {
        if (++depth > 32) {
            throw new IllegalStateException("cause cycle?");
        }
        current = current.getCause();
    }
    return current;
}
```

Hàm này **chỉ tháo những wrapper cụ thể**: CompletionException và ExecutionException. Nó không được quảng bá như giải pháp duy nhất cho mọi Throwable của JVM. Giới hạn bước là phòng vệ tránh chain bất thường hoặc bị ghép vòng; với dữ liệu không đáng tin cậy/đường kiểm toán nghiêm ngặt, có thể dùng identity set để phát hiện chu kỳ tổng quát thay vì chỉ giới hạn độ sâu.

**Lưu ý an toàn:** không dùng `getMessage()` của root exception như thông điệp trả thẳng cho client, vì nó có thể chứa URL, tên file, SQL, thông tin hạ tầng hoặc dữ liệu nhạy cảm. Phân loại để tạo một mã lỗi/ thông điệp an toàn; giữ chi tiết trong log có kiểm soát.

## 11. Chương trình 4 — lớp wrapper lồng nhau và root IOException

Tệp **`DiagnosticUnwrapDemo.java`** cố ý tạo chuỗi CompletionException → ExecutionException → IOException để xác nhận vì sao chỉ gọi `getCause()` một lần có thể chưa đủ.

```java
import java.io.IOException;
import java.util.concurrent.*;

public class DiagnosticUnwrapDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static Throwable unwrapCompletion(Throwable error) {
        Throwable current = error;
        int depth = 0;
        while ((current instanceof CompletionException
             || current instanceof ExecutionException)
             && current.getCause() != null
             && current.getCause() != current) {
            if (++depth > 32) {
                throw new IllegalStateException("cause cycle?");
            }
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        IOException root = new IOException("gateway-503");
        ExecutionException intermediate = new ExecutionException(root);
        CompletionException prewrapped = new CompletionException(intermediate);
        CompletableFuture<String> future = new CompletableFuture<>();
        future.completeExceptionally(prewrapped);

        Throwable observedGet = null, observedJoin = null;
        boolean joinSameInstance = false;

        try {
            future.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AssertionError(ex);
        } catch (ExecutionException ex) {
            observedGet = ex;
        }

        try {
            future.join();
        } catch (CompletionException ex) {
            observedJoin = ex;
            joinSameInstance = ex == prewrapped;
        }

        check(observedGet instanceof ExecutionException,
              "get wrapper");
        check(observedJoin instanceof CompletionException,
              "join wrapper");
        check(joinSameInstance, "join preserves original wrapper");
        check(unwrapCompletion(observedGet) == root,
              "get unwrap root");
        check(unwrapCompletion(observedJoin) == root,
              "join unwrap root");

        System.out.println("getWrapper=" +
            observedGet.getClass().getSimpleName());
        System.out.println("getDirectCause=" +
            observedGet.getCause().getClass().getSimpleName());
        System.out.println("joinWrapper=" +
            observedJoin.getClass().getSimpleName());
        System.out.println("joinSameInstance=" + joinSameInstance);
        System.out.println("unwrappedRoot=" +
            unwrapCompletion(observedJoin).getClass().getSimpleName()
            + ":" + unwrapCompletion(observedJoin).getMessage());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 DiagnosticUnwrapDemo.java
java DiagnosticUnwrapDemo
```

**Stdout đã kiểm chứng:**

```text
getWrapper=ExecutionException
getDirectCause=ExecutionException
joinWrapper=CompletionException
joinSameInstance=true
unwrappedRoot=IOException:gateway-503
PASS
```

Đây là một **phản ví dụ quan trọng** cho giả định “sau get phải chỉ cần `getCause()` đúng một lần”. Cause trực tiếp của wrapper `get()` trong fixture này là **ExecutionException**, và IOException nằm sâu hơn.

**Không áp dụng unwrap một cách mù quáng cho mọi lỗi.** Ví dụ một exception nghiệp vụ có cause là SQLException có thể cần giữ nguyên thông tin ngữ cảnh của exception nghiệp vụ. Hàm này chỉ tháo các wrapper **được xác định rõ là do ranh giới completion**.

## 12. Recovery operators: xử lý lỗi không có nghĩa xóa lỗi khỏi lịch sử

Trong một pipeline, bạn có thể:

- **Quan sát** lỗi: ghi log, cập nhật metrics.
- **Phục hồi**: biến lỗi thành kết quả thay thế hợp lệ.
- **Biến đổi kết quả**: tạo một kiểu biểu diễn cả thành công/thất bại.
- **Tiếp tục thất bại**: truyền ngoại lệ gốc cho upstream caller xử lý.
- **Hủy**: xử lý cancellation như một trạng thái riêng nếu domain yêu cầu.

Ba phương thức Java 8 thường gặp:

| Phương thức | Callback được gọi khi | Có thể làm gì? |
| --- | --- | --- |
| `exceptionally(Function<Throwable, ? extends T>)` | Stage hoàn thành lỗi | Trả fallback kiểu T |
| `handle(BiFunction<T,Throwable,U>)` | Thành công **hoặc** lỗi | Ánh xạ thành kiểu U khác hoặc cùng kiểu |
| `whenComplete(BiConsumer<T,Throwable>)` | Thành công **hoặc** lỗi | Quan sát/side effect, **không tự thay giá trị hoặc phục hồi** |

### exceptionally — hồi phục đúng trường hợp

```java
CompletableFuture<Integer> safe =
    priceFuture.exceptionally(error -> {
        // Chỉ fallback nếu policy nghiệp vụ cho phép.
        return -1;
    });
```

Khi `priceFuture` lỗi, stage `safe` có thể hoàn thành **thành công** với -1. Nhưng `priceFuture` ban đầu vẫn **lỗi**. Nếu -1 có thể bị hiểu là một giá trị giá hợp lệ, nên thay bằng Result/Optional/error type đúng domain thay vì nuốt.

### handle — biến cả hai đường đi thành một kiểu kết quả

```java
CompletableFuture<String> result =
    priceFuture.handle((value, error) ->
        error == null ? "VALUE:" + value : "FAILED");
```

`handle` luôn có cơ hội quan sát kết quả và có thể tạo kiểu khác, ví dụ một `Result<Price>` chứa trạng thái thành công/thất bại thay vì string minh họa. Nếu callback `handle` tự ném lỗi, stage mới lại thất bại.

### whenComplete — quan sát mà không tự xử lý

```java
CompletableFuture<Integer> observed =
    priceFuture.whenComplete((value, error) -> {
        if (error != null) {
            // Ghi log và metrics theo policy.
        }
    });
```

`whenComplete` thường phù hợp để **ghi nhận context** nhưng không biến một lỗi dữ liệu thành kết quả thành công. Nếu callback observer ném exception, kết quả phụ thuộc trạng thái upstream và quy tắc của `whenComplete`; tốt nhất observer không nên tự phá hỏng luồng vì một lỗi log không cần thiết.

### Thứ tự đặt recovery ảnh hưởng pipeline

```text
stage A (lỗi)
    |
    +-- exceptionally -> stage B thành công với fallback
                              |
                              +-- thenApply tiếp tục chạy

stage A (lỗi)
    |
    +-- whenComplete  -> stage C vẫn lỗi
                              |
                              +-- thenApply thường bị bỏ qua
```

Vậy trước khi đưa `exceptionally` vào một chuỗi ghép tác vụ, hãy xác định rõ: **có cho phép các bước sau chạy với fallback hay không?** Nếu không, chỉ nên quan sát và để lỗi lan lên.

## 13. Cancellation: không phải luôn đi qua hai wrapper thông thường

Trong Java 8, `CompletableFuture.cancel(mayInterruptIfRunning)` hoàn thành future theo kiểu cancellation. Khi gọi trực tiếp trên **chính future bị hủy**:

- `future.join()` có thể ném `CancellationException` trực tiếp.
- `future.get()` có thể ném `CancellationException` trực tiếp.
- `future.getNow(default)` không trả default mà cũng có thể ném CancellationException.

Nhưng nếu tạo dependent stage:

```java
CompletableFuture<Integer> source = new CompletableFuture<>();
CompletableFuture<Integer> dependent =
    source.thenApply(x -> x + 1);

source.cancel(true);
```

thì `dependent.get()` thường ném **`ExecutionException` có cause là `CancellationException`**; `dependent.join()` thường ném **`CompletionException` có cause là CancellationException**. Vị trí quan sát quyết định wrapper.

### cancel(true) không đồng nghĩa dừng thread

Đối với CompletableFuture, tham số `mayInterruptIfRunning` **không được dùng để điều khiển interrupt của computation** theo hợp đồng JavaDoc. Vì vậy future bị cancel không bảo đảm công việc I/O hay CPU phía sau dừng thật. Muốn hủy hoạt động nền cần thiết kế cơ chế cancel/interrupt/timeouts phù hợp ở nơi thực hiện công việc.

**Không tự retry cancellation như IOException.** Cancellation có thể là hành động cố ý do người dùng hoặc hệ thống; chính sách retry phải phân biệt.

## 14. Chương trình 5 — observer, recovery và cancellation ở dependent stage

Tệp **`RecoveryAndCancellationDemo.java`** cho thấy rõ `whenComplete` không phục hồi, `exceptionally` và `handle` có thể phục hồi, và cancellation trực tiếp khác dependent error wrapper.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class RecoveryAndCancellationDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        IllegalArgumentException root =
            new IllegalArgumentException("invalid-code");
        CompletableFuture<Integer> failed = new CompletableFuture<>();
        failed.completeExceptionally(root);

        AtomicBoolean observed = new AtomicBoolean(false);
        CompletableFuture<Integer> watched =
            failed.whenComplete((value, error) -> {
                observed.set(error != null);
            });

        boolean stillFailed = false;
        try {
            watched.join();
        } catch (CompletionException ex) {
            stillFailed = ex.getCause() == root;
        }

        int byExceptionally =
            failed.exceptionally(error -> -1).join();
        String byHandle = failed.handle((value, error) ->
            error == null ? "VALUE:" + value : "FAIL:" +
                error.getClass().getSimpleName()).get();

        CompletableFuture<Integer> canceled = new CompletableFuture<>();
        CompletableFuture<Integer> dependent =
            canceled.thenApply(x -> x + 1);
        canceled.cancel(true);

        boolean directCancelled = false;
        boolean dependentWrapped = false;

        try {
            canceled.join();
        } catch (CancellationException ex) {
            directCancelled = true;
        }

        try {
            dependent.get();
        } catch (ExecutionException ex) {
            dependentWrapped =
                ex.getCause() instanceof CancellationException;
        }

        check(observed.get() && stillFailed,
              "whenComplete observed not repaired");
        check(byExceptionally == -1
           && "FAIL:IllegalArgumentException".equals(byHandle),
              "explicit fallback");
        check(directCancelled && dependentWrapped,
              "cancellation forms");

        System.out.println("observed=" + observed.get());
        System.out.println("whenCompleteStillFailed=" + stillFailed);
        System.out.println("exceptionally=" + byExceptionally);
        System.out.println("handle=" + byHandle);
        System.out.println("directCancellation=" + directCancelled);
        System.out.println("dependentExecutionCauseCancellation=" +
            dependentWrapped);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 RecoveryAndCancellationDemo.java
java RecoveryAndCancellationDemo
```

**Stdout đã kiểm chứng:**

```text
observed=true
whenCompleteStillFailed=true
exceptionally=-1
handle=FAIL:IllegalArgumentException
directCancellation=true
dependentExecutionCauseCancellation=true
PASS
```

Giải thích:

1. Callback `whenComplete` đã quan sát lỗi: `observed=true`. Nhưng future của observer vẫn lỗi: `whenCompleteStillFailed=true`.
2. `exceptionally` tạo stage hồi phục với -1.
3. `handle` đổi outcome thành chuỗi diễn giải, dùng trong fixture.
4. `join()` trên future bị hủy trực tiếp nhận CancellationException.
5. `get()` trên dependent của source bị hủy nhận ExecutionException có cause CancellationException.
6. Lỗi và cancellation là **các trạng thái khác nhau của domain**, dù đều có thể xuất hiện trong exceptional completion.

## 15. TimeoutException: có hai nguồn khác nhau

Từ góc nhìn người gọi, cần phân biệt:

### A. Người chờ hết thời gian

```java
CompletableFuture<String> pending = new CompletableFuture<>();

try {
    pending.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Caller đã đợi quá giới hạn.
}
```

`TimeoutException` ở đây được ném **trực tiếp từ get(timeout)** vì future chưa hoàn thành trong thời gian cho phép. Nó **không tự đánh dấu future đã lỗi**, không tự cancel I/O và không chứng minh side effect đã dừng.

### B. Chính tác vụ hoàn thành ngoại lệ vì deadline

```java
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(
    new TimeoutException("service-deadline"));
```

Lúc này future đã hoàn thành ngoại lệ với root TimeoutException. Khi đọc:

- `failed.get()` ném ExecutionException với cause TimeoutException.
- `failed.join()` ném CompletionException với cause TimeoutException.

Hai tình huống có thể cùng nhắc tới “timeout”, nhưng **cách xử lý khác nhau**: trường hợp A người gọi hết thời gian chờ trong khi task còn sống; trường hợp B task đã tự kết thúc dưới dạng lỗi.

**Java 8 compatibility:** `CompletableFuture.orTimeout` và `completeOnTimeout` không thuộc API Java 8. Nếu cần deadline ở pipeline Java 8, dùng `ScheduledExecutorService` hoặc cơ chế timeout tại I/O của thư viện, cùng chính sách hủy và dọn tài nguyên; không chỉ dựa vào `get(timeout)`.

## 16. Chương trình 6 — caller timeout khác root TimeoutException

Tệp **`CallerTimeoutVsRootTimeoutDemo.java`** không dùng sleep. Nó xác minh timeout chờ khi thời hạn bằng 0 và future vẫn pending sau đó, rồi chủ động hoàn thành future bằng root TimeoutException.

```java
import java.util.concurrent.*;

public class CallerTimeoutVsRootTimeoutDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();

        boolean waitTimedOut = false;
        try {
            pending.get(0, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            waitTimedOut = true;
        }
        boolean stillPending = !pending.isDone();

        TimeoutException root =
            new TimeoutException("service-deadline");
        pending.completeExceptionally(root);

        boolean getWrappedTimeout = false;
        boolean joinWrappedTimeout = false;

        try {
            pending.get();
        } catch (ExecutionException ex) {
            getWrappedTimeout = ex.getCause() == root;
        }

        try {
            pending.join();
        } catch (CompletionException ex) {
            joinWrappedTimeout = ex.getCause() == root;
        }

        check(waitTimedOut && stillPending,
              "wait timeout not completion");
        check(getWrappedTimeout && joinWrappedTimeout,
              "root timeout is different");

        System.out.println("callerTimedOut=" + waitTimedOut);
        System.out.println("futureStillPendingAfterWait=" + stillPending);
        System.out.println("getWrappedRootTimeout=" + getWrappedTimeout);
        System.out.println("joinWrappedRootTimeout=" + joinWrappedTimeout);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CallerTimeoutVsRootTimeoutDemo.java
java CallerTimeoutVsRootTimeoutDemo
```

**Stdout đã kiểm chứng:**

```text
callerTimedOut=true
futureStillPendingAfterWait=true
getWrappedRootTimeout=true
joinWrappedRootTimeout=true
PASS
```

Bài học: khi caller hết thời gian đợi, future có thể vẫn chưa done và kết quả thật có thể xuất hiện sau đó. Với API có side effect như thanh toán hoặc tạo đơn, retry ngay sau caller timeout có thể làm phát sinh công việc trùng. Cần có idempotency key hoặc cơ chế truy vấn trạng thái tác vụ.

## 17. Interruption: đừng nhầm với exceptional completion của task

`Future.get()` và `CompletableFuture.get()` có thể ném **`InterruptedException`** khi luồng chờ bị interrupt. Đây là **tín hiệu đối với luồng đang chờ**, không nhất thiết là root error mà stage tương lai đã hoàn thành với nó.

Trong code đồng bộ:

```java
// Đoạn minh họa.
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Wait interrupted", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException(
        "Asynchronous stage failed", ex.getCause());
}
```

Đoạn trên là **một lựa chọn minh họa** cho service không thể khai báo InterruptedException. Hợp đồng thực có thể phải ném tiếp InterruptedException hoặc báo cancellation theo kiểu domain. Mục tiêu là **không nuốt cờ ngắt**.

`join()` không khai báo checked `InterruptedException`, và có thể tiếp tục chờ cho đến khi future hoàn thành dù luồng bị interrupt. Điều đó không khiến join phù hợp hơn ở mọi chỗ: nếu request cancellation/shutdown phải phản ứng nhanh, cần thiết kế đường chờ hoặc pipeline tương ứng.

**Không nhầm `Thread.join()` với `CompletableFuture.join()`.** Hai phương thức trùng tên nhưng thuộc hai API khác nhau.

## 18. Bảo toàn nguyên nhân gốc khi chuyển lỗi giữa các tầng

Một adapter có thể muốn biến lỗi kỹ thuật thành lỗi nghiệp vụ:

```java
// Đoạn minh họa, không phải class standalone.
Throwable root = unwrapCompletion(error);

if (root instanceof IllegalArgumentException) {
    // Trả lỗi validation theo hợp đồng.
} else if (root instanceof java.io.IOException) {
    // Trả lỗi hạ tầng hoặc đặt retry policy có kiểm soát.
} else {
    // Ghi nhận unknown failure, không tự nuốt.
}
```

Khi ném exception mới, nên bảo toàn nguyên nhân:

```java
throw new IllegalStateException("Order pipeline failed", root);
```

Với logging, cần ít nhất:

- Operation và tên stage phù hợp (ví dụ fetchStock, reserveInventory, calculatePrice).
- Correlation/trace ID và khóa nghiệp vụ được phép log.
- Kiểu wrapper quan sát được và root cause sau xử lý.
- Stack trace đủ để chẩn đoán; không chỉ thông điệp `CompletionException`.
- Một số metric phân loại lỗi ổn định, tránh nhét toàn bộ exception message (cardinality cao) vào tag/label.

**Đừng log và throw lại cùng một lỗi ở mọi stage** nếu điều đó làm một failure xuất hiện như nhiều sự cố độc lập. Quy định một số điểm ghi log/metrics có context, sau đó xử lý tập trung ở boundary.

### “Nguyên nhân gốc” không phải lúc nào cũng chỉ có một

- Với một chain tuyến tính có một exception, root chain thường có một lỗi ban đầu.
- Với `allOf` có **nhiều task thất bại độc lập**, có thể có **nhiều nguyên nhân**; `allOf.join()` không cung cấp danh sách đầy đủ một cách tự động.
- Với bất kỳ recovery nào lại ném exception mới, có thể mất original error nếu code không gắn cause/suppressed.
- Khi một logger/observer tự ném lỗi, cần tránh vô tình thay thế cause quan trọng.

Vì vậy đừng cố ép mọi orchestration phức tạp thành một “root cause string” duy nhất rồi xóa mất thông tin của các nhánh khác. Nếu sản phẩm cần đối soát từng nhánh, thu thập **kết quả của từng tác vụ**.

## 19. Thiết kế Result cho trường hợp muốn gom tất cả thất bại

Một cách hữu ích là **biến cả thành công và thất bại thành các giá trị**, rồi dùng `allOf` trên các future đã được recovery thành Result. Ví dụ về kiến trúc:

```text
Task A ------ handle(value,error) ---> ResultA
Task B ------ handle(value,error) ---> ResultB
Task C ------ handle(value,error) ---> ResultC
                                      |
                                      v
                    allOf(ResultA, ResultB, ResultC)
                                      |
                                      v
                 Tổng hợp thành công + từng lỗi theo task
```

Ý tưởng:

```java
// Snippet minh họa: có Result<T> phù hợp domain,
// không phải một chương trình standalone.
CompletableFuture<Result<Order>> safeOrder =
    orderFuture.handle((value, error) ->
        error == null
            ? Result.success(value)
            : Result.failure(unwrapCompletion(error)));
```

Trong code thực tế, cần định nghĩa `Result<T>` rõ ràng hoặc dùng kiểu của thư viện được lựa chọn; `java.util.concurrent` Java 8 không tự cung cấp một lớp Result chuẩn với hai factory nêu trong snippet.

**Ưu điểm:** mỗi nhánh có kết quả riêng nên không mất mọi ngoại lệ chỉ vì allOf tổng có một wrapper. **Nhược điểm:** nếu tự chuyển mọi exception thành dữ liệu, có nguy cơ che đi lỗi nghiêm trọng hoặc cancellation; phải phân loại và quy định outcome rõ.

### allOf không tự cancel các tác vụ khác

Nếu một tác vụ lỗi, đừng giả định những tác vụ khác đã dừng. Những side effects độc lập có thể vẫn diễn ra. Với hệ thống đặt hàng, cần chính sách nhất quán: có chờ các kết quả còn lại không, có bồi thường rollback không, và đâu là nguồn sự thật cho kết quả cuối?

## 20. Tác động của thứ tự đặt exceptionally/handle

Hãy xét hai chuỗi:

**A. Hồi phục sớm**

```java
// Minh họa, futures đã được định nghĩa bởi ứng dụng.
CompletableFuture<Integer> a =
    lookupFuture.exceptionally(ex -> 0)
                .thenApply(n -> n + 1);
```

Nếu lookup lỗi, `exceptionally` trả 0, `thenApply` chạy và cho 1. Đây có thể là mong muốn nếu 0 là “không có hàng”; nhưng rất nguy hiểm nếu 0 bị hiểu là lượng hàng thực.

**B. Chỉ hồi phục ở cuối**

```java
CompletableFuture<Integer> b =
    lookupFuture.thenApply(n -> n + 1)
                .exceptionally(ex -> -1);
```

Nếu lookup lỗi, `thenApply` bị bỏ qua rồi stage cuối cho -1. Hợp đồng khác A. Nếu `thenApply` tự ném exception, B cũng có thể hồi phục ở cuối. Vị trí recovery quyết định **những lỗi nào được bắt** và **bước nào tiếp tục chạy**.

**Không thêm `exceptionally(ex -> null)` vào mọi stage chỉ để “pipeline không throw”.** Lỗi bị che có thể trở thành NullPointerException ở bước sau, khiến nguyên nhân ban đầu khó tìm hơn.

## 21. Khi nào get/join nên xuất hiện trong ghép tác vụ?

Trong một pipeline ghép tác vụ đúng nghĩa, không nên gọi get/join ngay tại từng callback:

```java
// Không nên nếu lookupAsync() trả về CompletableFuture.
CompletableFuture<Integer> blocked =
    keyFuture.thenApply(key -> lookupAsync(key).join());
```

Điều này chặn luồng thực thi callback và có thể gây starvation/deadlock khi executor hạn chế. Thay bằng:

```java
CompletableFuture<Integer> composed =
    keyFuture.thenCompose(key -> lookupAsync(key));
```

Ở đây `keyFuture`/`lookupAsync` là các thành phần ứng dụng nên hai đoạn là **snippet minh họa, không phải chương trình độc lập**.

Các điểm gọi get/join hợp lý:

1. CLI hoặc main cần đợi toàn bộ quá trình trước khi thoát.
2. Adapter đồng bộ phải trả một giá trị theo hợp đồng có deadline.
3. Unit/integration test cần chờ để assert, có cơ chế chống treo.
4. Biên chuyển đổi từ asynchronous API sang synchronous API được thiết kế rõ.

Ở HTTP request thread, event loop hoặc executor chạy số lượng lớn tác vụ, cần cân nhắc kỹ trước khi chặn.

## 22. Phân biệt wrapper lỗi với lỗi business ở giao diện người dùng

Với hệ thống thật, không đưa nguyên văn những lỗi như:

```text
java.util.concurrent.CompletionException:
  java.io.IOException: gateway-503
```

lên màn hình người dùng. Thay vào đó:

- Chọn mã lỗi phù hợp, ví dụ validation_error, upstream_unavailable, operation_cancelled, request_timeout.
- Ghi log stacktrace/cause ở nơi có quyền truy cập phù hợp.
- Với cancellation, nếu do người dùng chủ động hủy thì không gắn nhãn “lỗi hệ thống” một cách máy móc.
- Với timeout, phân biệt “caller đợi hết thời gian nhưng công việc có thể vẫn chạy” và “task hoàn thành lỗi vì deadline”.
- Nếu có nhiều future lỗi độc lập, trả cấu trúc errors theo từng phần nghiệp vụ khi contract yêu cầu, thay vì chỉ một message của allOf.

**Không bịa lại nguyên nhân từ wrapper.** `CompletionException` chỉ là phương tiện truyền lỗi; phân loại phải dựa vào cause được ghi nhận và thông tin về stage/domain.

## 23. Ma trận kiểm thử exception propagation

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Future thành công | `completedFuture(42)` | get/join đều 42 |
| Direct root IOException | `completeExceptionally(root)` | get: ExecutionException, join: CompletionException |
| getNow với future lỗi | Future đã exceptional | CompletionException, không dùng default |
| thenApply sau thất bại | Upstream lỗi | Callback thành công không chạy |
| thenCompose trả future lỗi | Hàm async trả failed future | Dependent hoàn thành lỗi |
| thenCombine một nhánh lỗi | Một completed, một failed | Combiner không chạy |
| allOf một nhánh lỗi | Mọi input đã complete | Result allOf thất bại |
| allOf nhiều nhánh lỗi | Hai nhánh lỗi độc lập | Không suy rằng allOf tự gom mọi cause |
| anyOf một failed và một pending | Failed đã xong | anyOf thất bại; pending không tự cancel |
| anyOf nhiều nhánh race | Nhiều completion cạnh tranh | Không suy thứ tự outcome cố định |
| Prewrapped CompletionException | CompletionException có cause ExecutionException | join có thể giữ wrapper cũ |
| Nested wrapper | CompletionException → ExecutionException → IOException | Unwrap đúng root |
| whenComplete trên lỗi | Observer không throw | Ghi nhận lỗi, stage vẫn lỗi |
| exceptionally trên lỗi | Callback trả fallback | Stage mới thành công nếu callback không throw |
| handle trên lỗi | Callback ánh xạ | Stage mới mang kiểu/giá trị tương ứng |
| Direct canceled future | source.cancel(true) | source.join() ném CancellationException |
| Dependent sau cancel | source.thenApply() | dependent.get() có thể có cause CancellationException |
| Caller timeout | pending.get(0, MILLISECONDS) | TimeoutException trực tiếp, future còn pending |
| Root timeout | completeExceptionally(new TimeoutException) | get/join bọc nguyên nhân |
| get interrupted | Thread đang chờ bị interrupt | InterruptedException, không mặc định stage đã lỗi |
| join interrupted | Thread chờ join bị interrupt | Không có checked InterruptedException |
| Competing completions | Hai complete/completeExceptionally | Một kết quả thắng theo completion state |
| Fault trong observer | whenComplete callback throw | Kiểm policy của stage kết quả |
| Java 8 compatibility | Biên dịch --release 8 | Không dùng Java 9+ API |

**Ưu tiên fixture quyết định được** để test wrapper/cause, như một CompletableFuture được `completeExceptionally` ngay trong test. Với concurrency thật, dùng `CountDownLatch`/cơ chế synchronization và timeout test có giới hạn, tránh `Thread.sleep` tùy tiện.

## 24. Những lỗi thiết kế thường gặp

| Lỗi | Tại sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ log `CompletionException` | Không biết lỗi thật | Xem cause chain, giữ stack trace |
| Catch `ExecutionException` khi gọi `join()` | Không đúng wrapper thông thường | Catch CompletionException/CancellationException |
| Catch `CompletionException` và cho rằng đã xử lý cancel | Direct cancellation có thể ném CancellationException | Xử lý cancel riêng |
| Chỉ gọi `getCause()` một lần cho mọi pipeline | Lỗi gốc có thể nằm nhiều tầng | Unwrap wrapper đã biết có kiểm soát |
| Unwrap mọi Throwable đến cuối rồi bỏ hết context | Mất thông tin stage/domain | Giữ outer exception, chỉ unwrap để phân loại |
| Bắt `Exception` và trả null | Che lỗi thành công giả | Ánh xạ lỗi thành domain result rõ |
| Coi `allOf` gom mọi ngoại lệ | Mất thông tin của các nhánh lỗi khác | Thu thập từng stage |
| Coi `anyOf` chờ thành công đầu tiên | Một exception có thể thắng race | Thiết kế first-success riêng |
| Gọi join bên trong thenApply | Chặn executor callback | thenCompose |
| Hồi phục mọi stage bằng `exceptionally(ex -> null)` | Mất lỗi ban đầu, tạo lỗi sau | Recovery theo policy |
| Dùng whenComplete làm fallback | Observer không tự sửa outcome | exceptionally/handle |
| Dùng `cancel(true)` và nghĩ task chắc chắn dừng | Có thể chỉ cancel future state | Cancellation/IO cooperation |
| Dùng `get(timeout)` như deadline của công việc | Caller hết chờ nhưng work còn chạy | Deadline của task riêng |
| Retry sau caller timeout mà không idempotency | Side effect có thể bị nhân đôi | State/idempotency key |
| Nuốt InterruptedException | Shutdown/cancel bị hỏng | Restore flag hoặc propagate |
| Dùng Java 9+ `failedFuture` trong bài Java 8 | Không biên dịch mức Java 8 | new CompletableFuture + completeExceptionally |
| Dùng Java 9+ `orTimeout` trong Java 8 | Không phù hợp module | get(timeout) hoặc scheduler |
| Chỉ test một nhánh lỗi trong orchestration thật | Bỏ sót nhiều lỗi đồng thời | Test nhiều lỗi và thu thập riêng |
| Nghĩ cause của `CompletionException` luôn là IOException | Nó phụ thuộc stage lỗi | Xác minh loại root thực tế |
| Dựa vào exception message như metric label | High cardinality, lộ dữ liệu | Dùng error code/class hữu hạn |

## 25. Bài tập thực hành và đáp án

**Bài 1 — chọn wrapper.** Một future hoàn thành ngoại lệ bằng IOException. Khi gọi `get()` và `join()`, wrapper thông thường nào xuất hiện?

**Đáp án:** `get()` ném ExecutionException, `join()` ném CompletionException; `getCause()` cho IOException gốc.

**Bài 2 — thenCompose lỗi.** Một công đoạn lấy tồn kho trả future lỗi. Bước `thenApply(stock -> stock + 1)` phía sau có chạy với stock=null không?

**Đáp án:** không. Nó bị bỏ qua do upstream exceptional completion, trừ khi có recovery tạo giá trị thành công trước bước đó.

**Bài 3 — allOf nhiều lỗi.** Ba tác vụ song song, hai tác vụ bị lỗi. `allOf.join()` có tự trả đầy đủ cả hai exception không?

**Đáp án:** không. allOf có thể hoàn thành ngoại lệ nhưng không phải cấu trúc gom toàn bộ lỗi. Nếu cần tất cả, thu thập outcome từng future.

**Bài 4 — anyOf bị lỗi trước.** Một nhánh trả kết quả tốt sau 500 ms, nhánh còn lại hoàn thành lỗi trước. Có nên tin anyOf sẽ chờ nhánh thành công?

**Đáp án:** không. anyOf có thể hoàn thành ngay theo lỗi của nhánh xong trước. Muốn first-success cần thiết kế khác.

**Bài 5 — wrapper lồng.** Một lỗi được bọc CompletionException(ExecutionException(IOException)). Chỉ gọi getCause một lần sau khi catch join có đủ để phân loại IOException không?

**Đáp án:** không. Có thể cần unwrap các wrapper đã biết đến IOException, đồng thời giữ outer exception để debug.

**Bài 6 — whenComplete.** Callback log của `whenComplete` được gọi khi upstream lỗi. Có nghĩa stage đã thành công không?

**Đáp án:** không. whenComplete thường quan sát và truyền tiếp lỗi, không tự tạo giá trị hồi phục.

**Bài 7 — cancellation.** Source bị cancel, stage dependent ném ExecutionException có cause CancellationException. Có nên coi đó là IOException rồi retry không?

**Đáp án:** không. Cần phân loại cancellation đúng ngữ nghĩa, xác định yêu cầu hủy và trạng thái work bên dưới.

**Bài 8 — timeout ở người chờ.** `get(timeout)` ném TimeoutException. Có chắc task đã dừng hoặc future đã exceptional không?

**Đáp án:** không. Chỉ có caller hết thời gian chờ; cần chính sách quản lý work tiếp tục.

**Bài 9 — timeout là cause.** Future bị `completeExceptionally(new TimeoutException("service-deadline"))`. Khi gọi get(), exception ngoài cùng là gì?

**Đáp án:** thông thường ExecutionException với cause TimeoutException; khác với TimeoutException trực tiếp từ get(timeout) trên future pending.

**Bài 10 — recovery placement.** `lookup.exceptionally(ex -> 0).thenApply(n -> n+1)` và `lookup.thenApply(n -> n+1).exceptionally(ex -> -1)` có cùng hành vi khi lookup lỗi không?

**Đáp án:** không. Chuỗi đầu hồi phục thành 0 trước rồi bước sau chạy cho 1; chuỗi sau bỏ qua transform và hồi phục cuối thành -1.

**Bài 11 — callback blocking.** Một callback trả về CompletableFuture. Nên dùng `thenCompose` hay `thenApply(x -> async(x).join())`?

**Đáp án:** `thenCompose` để nối bất đồng bộ, tránh chặn luồng callback không cần thiết.

**Bài 12 — nguyên nhân gốc cho API.** Một controller bắt CompletionException có cause IOException. Nên gửi nguyên văn message/stacktrace cho client không?

**Đáp án:** không. Phân loại root theo mã lỗi an toàn, log cause/context phù hợp và giữ trace để chẩn đoán.

## 26. Câu hỏi tự kiểm tra

**1. ExecutionException checked hay unchecked?**  
Checked. Nó thường được dùng bởi Future.get.

**2. CompletionException checked hay unchecked?**  
Unchecked (RuntimeException).

**3. get và join có cùng giá trị khi success không?**  
Có, cùng giá trị T.

**4. Exception nào thường mang lỗi gốc khi gọi get trên stage lỗi?**  
ExecutionException; đọc getCause.

**5. Exception nào thường mang lỗi gốc khi gọi join trên stage lỗi?**  
CompletionException; đọc getCause.

**6. CancellationException có luôn bị bọc không?**  
Không. Gọi trực tiếp trên future bị hủy có thể ném CancellationException trực tiếp.

**7. thenApply có chạy khi upstream thất bại không?**  
Không, trừ khi trước đó có stage hồi phục tạo thành công.

**8. thenCompose giải quyết vấn đề gì?**  
Nối phẳng các công đoạn async trả CompletionStage/CompletableFuture mà không buộc tạo future lồng.

**9. allOf có tự trả List các nguyên nhân lỗi không?**  
Không.

**10. anyOf có chờ thành công đầu tiên không?**  
Không; nó theo một future hoàn thành trước, kể cả hoàn thành lỗi.

**11. khi nào cần unwrap nhiều tầng?**  
Khi các wrapper CompletionException/ExecutionException lồng nhau che root cause.

**12. whenComplete có tự làm stage thất bại thành công không?**  
Không, nó chủ yếu quan sát kết quả.

**13. exceptionally và handle khác nhau ra sao?**  
exceptionally tạo fallback khi lỗi; handle xử lý cả value lẫn error, có thể đổi kiểu kết quả.

**14. TimeoutException trực tiếp từ get(timeout) có nghĩa future đã hoàn thành lỗi không?**  
Không.

**15. Vì sao không gọi join trong mọi thenApply?**  
Có thể chặn executor, gây starvation hoặc deadlock và làm mất lợi ích composition.

**16. Khi lỗi gốc là IOException nhưng wrapper là CompletionException, nên retry dựa vào yếu tố nào?**  
Root cause, lỗi nghiệp vụ và retry policy/idempotency; không chỉ wrapper.

## Tài liệu Java SE 8 chính thức

- [CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html) — completeExceptionally, get, join, getNow, thenCompose, thenCombine, allOf, anyOf, cancel.
- [CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html) — hợp đồng ghép và truyền kết quả/lỗi giữa các stage.
- [Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html) — get, get(timeout), cancel và hợp đồng interruption.
- [CompletionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionException.html) — wrapper unchecked cho exceptional completion.
- [ExecutionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ExecutionException.html) — wrapper checked ở Future.get.
- [CancellationException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CancellationException.html) — trạng thái hủy và propagation.
- [TimeoutException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeoutException.html) — timeout chờ hoặc timeout được task chọn làm cause.
- [TimeUnit](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/TimeUnit.html) — đơn vị thời gian cho get(timeout).
- [InterruptedException](https://docs.oracle.com/javase/8/docs/api/java/lang/InterruptedException.html) — kiểm soát interruption của luồng chờ.

**Ghi nhớ:** trong `CompletableFuture`, ngoại lệ được nhìn thấy ở `get()`/`join()` thường là **wrapper của exceptional completion**, không phải lỗi nghiệp vụ ban đầu. Để chẩn đoán đúng một pipeline ghép tác vụ, hãy xác định **stage nguồn**, giữ **cause chain**, hiểu quy tắc của `thenCompose`/`thenCombine`/`allOf`/`anyOf`, phân biệt **cancellation** và **timeout**, và chỉ dùng recovery có chủ đích. Giữ ngữ nghĩa lỗi gốc, không nuốt lỗi bằng fallback vô nghĩa; chỉ block ở ranh giới thực sự cần đồng bộ.