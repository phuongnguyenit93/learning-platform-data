# minimalCompletionStage() và copy(): giới hạn quyền hoàn tất future của bên nhận

## 1. Vấn đề: một CompletableFuture vừa là lời hứa kết quả, vừa là quyền thay đổi kết quả

`CompletableFuture<T>` có hai nhóm khả năng trong cùng một đối tượng:

- **Tiêu thụ kết quả / phối hợp bất đồng bộ:** `thenApply`, `thenCompose`, `handle`, `whenComplete`, `thenCombine`, `toCompletableFuture`…
- **Chủ động điều khiển completion:** `complete(value)`, `completeExceptionally(error)`, `cancel(...)`, `obtrudeValue(...)`, `obtrudeException(...)`, `completeOnTimeout`, `orTimeout`…

Điều đó rất tiện cho code **sở hữu** future. Nhưng nó trở thành một vấn đề khi cùng một `CompletableFuture` được trao nguyên vẹn cho code bên ngoài: bên nhận có thể `complete("FAKE")` trước khi công việc thật hoàn tất, `cancel`, hoặc dùng `obtrudeValue` để thay đổi kết quả quan sát được. Những hành vi đó phá vỡ ranh giới ownership của ứng dụng.

~~~java
class UnsafeService {
    private final CompletableFuture<String> result =
            new CompletableFuture<>();

    public CompletableFuture<String> result() {
        return result; // LỘ future gốc có quyền complete/cancel!
    }

    public void finish() {
        result.complete("trusted");
    }
}
~~~

Đây là **đoạn minh họa** với import `java.util.concurrent.CompletableFuture`. Consumer có thể gọi `service.result().complete("fake")` trước `finish()` và làm completion thật không thắng được cuộc đua. Nếu chỉ muốn client **đợi** hoặc **gắn callback** lên kết quả, trả trực tiếp future gốc trao quá nhiều quyền.

Từ Java 9, `CompletableFuture` có hai API phục vụ ranh giới này:

1. `minimalCompletionStage()` — cấp cho bên nhận một **CompletionStage<T> giới hạn** các thao tác trong interface `CompletionStage`.
2. `copy()` — cấp cho bên nhận **một CompletableFuture<T> độc lập về trạng thái completion**, có cùng outcome với nguồn nếu bản sao chưa được bên nhận hoàn tất trước.

**Ý cốt lõi:** hai API bảo vệ **quyền điều khiển completion của đối tượng gốc**, nhưng **không có nghĩa tạo bản sao sâu dữ liệu T, không tự dừng I/O, và không phải cơ chế bảo mật chống code đối địch có toàn quyền JVM**.

### Mục tiêu học

Sau bài này, bạn sẽ:
- Hiểu chính xác chữ ký và semantics Java 17 của hai API.
- Phân biệt **interface restriction** với **independent completable copy**.
- Biết tác động của `complete`, `cancel` và `obtrudeValue` trên future trả cho client.
- Hiểu luồng hoàn tất bình thường, exceptional completion và chuỗi `CompletionException`.
- Dùng `CompletionStage.toCompletableFuture()` đúng cách, không nhầm nó “mở lại” quyền sửa source.
- Thiết kế public API để source future do component sở hữu được giữ `private`.
- Nhận biết shallow data sharing với objects mutable và đề xuất immutable DTO/snapshot.
- Biết giới hạn về backpressure, cancellation propagation, timeouts và liveness.
- Chạy các chương trình Java 17+ xác định kết quả bằng `complete()` và callback, không cần `sleep()`.
- Áp dụng checklist code review và giải các bài tập về quyền truy cập future.

**Phạm vi:** Java SE concurrency (`java.util.concurrent`), không phụ thuộc framework.

## 2. Hai API và hợp đồng chính thức

Trong Java SE 17:

~~~java
public CompletableFuture<T> copy();

public CompletionStage<T> minimalCompletionStage();
~~~

`copy()` trả một `CompletableFuture<T>` **mới**. Tài liệu JDK mô tả hành vi của nó tương đương:

~~~java
CompletableFuture<T> copy = source.thenApply(x -> x);
~~~

Đây là một **dependent future mới**, không phải alias của source. Khi source hoàn tất bình thường, bản sao hoàn tất cùng **giá trị T** nếu chưa bị hoàn tất độc lập trước đó. Khi source hoàn tất đặc biệt, bản sao nhận exceptional completion theo Javadoc, với `CompletionException` bao nguyên nhân thích hợp.

`minimalCompletionStage()` trả một `CompletionStage<T>` **mới**, chỉ hỗ trợ hành vi thuộc interface `CompletionStage` và không thể được hoàn tất độc lập bằng các thao tác quản lý trạng thái không thuộc interface đó. Nó cũng theo kết quả của source khi source hoàn tất.

**Sự khác nhau cốt lõi:**

| Tiêu chí | `source` trực tiếp | `source.copy()` | `source.minimalCompletionStage()` |
|---|---|---|---|
| Kiểu trả về theo API | `CompletableFuture<T>` | `CompletableFuture<T>` | `CompletionStage<T>` |
| Bên nhận gọi `thenApply/thenCompose/handle` | Có | Có | Có |
| Bên nhận gọi `complete(value)` trực tiếp | Có, sửa source | Có, sửa **copy**, không sửa source | Không có method này ở interface |
| Bên nhận gọi `cancel(...)` trực tiếp | Có, cancel source | Có, cancel **copy** | Không có method này ở interface |
| Bên nhận gọi `join()` trực tiếp | Có | Có | Không có method `join` ở interface |
| Bên nhận chờ thông qua `toCompletableFuture().join()` | Có thể | Có thể | Có thể; nhận future non-minimal mới theo implementation chuẩn |
| Quyền chủ động quyết định source hoàn tất | **Có** | **Không** | **Không** |
| Kết quả có thể là reference T gốc | Có | **Có** | **Có** |
| Là deep copy của T? | Không | **Không** | **Không** |
| Client có thể tự tạo các dependent stages? | Có | Có | Có |
| Có tự điều khiển hủy background task? | Không bảo đảm | Không | Không |

Lưu ý: cột `minimalCompletionStage()` xét **API hợp đồng và implementation chuẩn**, không khẳng định một object Java không thể bị quan sát qua reflection hoặc môi trường đặc quyền. Không nên dùng như sandbox bảo mật cho mã không tin cậy.

## 3. Ranh giới owner và observer

Một thiết kế tốt phân biệt:

- **Producer/owner:** tạo `CompletableFuture`, quản lý luồng làm việc thực tế, quyết định normal/exceptional completion.
- **Observer/consumer:** đăng ký callback, nối stage hoặc chờ kết quả, nhưng **không được quyết định source đã hoàn tất hay chưa**.

Sơ đồ:

~~~text
                   Service (owner)
                          |
              private CompletableFuture<T>
                          |
             complete / completeExceptionally
                          |
           +--------------+---------------+
           |                              |
     minimalCompletionStage()           copy()
           |                              |
    CompletionStage<T>             CompletableFuture<T>
           |                              |
      client compose                  client join/get
      / handle                       / compose
           |                              |
      client KHÔNG có               client CÓ THỂ complete
      complete() trực tiếp          copy riêng của mình
           |                              |
           +--------------+---------------+
                          |
           KHÔNG sửa completion của source
~~~

**Nguyên tắc:** owner giữ source trong một field không bị expose trực tiếp. Không tạo một phương thức khác vô tình trả source gốc; nếu có, việc dùng `copy` ở endpoint khác không còn bảo vệ ownership tổng thể.

## 4. Vì sao chỉ khai báo return type CompletionStage chưa đủ?

Một cách viết thường thấy:

~~~java
class Service {
    private final CompletableFuture<String> internal =
            new CompletableFuture<>();

    public CompletionStage<String> status() {
        return internal; // Kiểu public giới hạn, object thật vẫn là source!
    }
}
~~~

**Hợp đồng compile-time** là `CompletionStage`: code dùng biến kiểu này không nhìn thấy `complete`. Nhưng trong Java, caller có thể kiểm tra runtime type:

~~~java
CompletionStage<String> published = service.status();
if (published instanceof CompletableFuture<?>) {
    // Có thể cast để chạm tới chính object gốc.
}
~~~

Đây là các đoạn minh họa, cần class `service` được khởi tạo và xử lý generic cast thích hợp ở nơi thực hiện. Vì trả **đúng source object** mang runtime type `CompletableFuture`, một caller có thể cast ra concrete type để gọi `complete/cancel/obtrude`.

Vì vậy, **return type chỉ là một phần của thiết kế**. Để **thực sự không trao source object**, dùng:

~~~java
public CompletionStage<String> status() {
    return internal.minimalCompletionStage();
}
~~~

Bên nhận nhận **một stage wrapper/dependent mới**, không phải source gốc. Hoặc khi signature cần `CompletableFuture` cho API cũ, dùng:

~~~java
public CompletableFuture<String> statusForLegacyClient() {
    return internal.copy();
}
~~~

Cả hai là code trích trong class với field `internal` như trên.

## 5. copy(): defensive completion copy nhưng vẫn có thể bị client sửa

`copy()` có thể trông giống “immutable CompletableFuture”, nhưng đây là cách hiểu sai. Nó là một **CompletableFuture thông thường**, và client có thể gọi tất cả các phương thức mutation trên **chính bản sao**.

Điều được bảo vệ: **sửa bản sao không sửa state của source**.

### Ví dụ độc lập 1: client complete copy trước owner

Lưu tệp **CompletableFutureCopyIsolationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureCopyIsolationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> exposed = source.copy();

        boolean clientCompleted = exposed.complete("client-value");
        boolean sourceWasDone = source.isDone();
        boolean ownerCompleted = source.complete("owner-value");

        System.out.println("clientCompleted=" + clientCompleted);
        System.out.println("sourceWasDone=" + sourceWasDone);
        System.out.println("ownerCompleted=" + ownerCompleted);
        System.out.println("source=" + source.join());
        System.out.println("exposed=" + exposed.join());
    }
}
~~~

Biên dịch và chạy JDK 17+:

~~~bash
javac CompletableFutureCopyIsolationDemo.java
java CompletableFutureCopyIsolationDemo
~~~

Stdout:

~~~text
clientCompleted=true
sourceWasDone=false
ownerCompleted=true
source=owner-value
exposed=client-value
~~~

**Diễn giải:**

1. Source lúc đầu pending; copy được tạo và cũng pending.
2. Client hoàn tất **copy** bằng `"client-value"`, nên `exposed.complete` trả true.
3. Source **vẫn pending**, do đó `source.isDone()` trả false.
4. Owner gọi `source.complete("owner-value")`; lệnh thành công vì source chưa bị client đụng.
5. Copy đã hoàn tất trước đó nên **không đổi sang "owner-value"**.
6. Kết quả caller nhìn thấy qua copy đã khác với source. Do đó copy **không bảo đảm client sẽ thấy kết quả thật** nếu chính client chủ động mutate bản sao.

**Đây là ranh giới quyền:** client không thể quyết định completion của **source**, nhưng vẫn có quyền quyết định outcome cục bộ trên **copy**. Nếu một API cần giảm rủi ro sửa nhầm cả ở đối tượng trả về, `minimalCompletionStage` là lựa chọn biểu đạt chặt hơn.

### Hậu quả đối với callbacks của client

Nếu client đã tự `complete("client-value")` bản sao rồi gắn callback `thenApply`, callback thấy client-value. Owner vẫn có thể hoàn tất source bằng owner-value, nhưng callback trên copy đã hoàn tất trước đó sẽ không chạy lại.

Không dùng copy nếu yêu cầu là **ép client phải quan sát kết quả đúng bất kể client cố ý sửa view riêng**. API này chỉ bảo vệ source, không áp đặt sự trung thực cho một client được cấp mutable copy.

## 6. minimalCompletionStage(): cấp quyền nối chuỗi mà không cấp quyền complete

Giá trị trả về có type `CompletionStage<T>`. Các thao tác được phép nằm ở interface:

~~~java
CompletionStage<String> view = source.minimalCompletionStage();

CompletionStage<Integer> length =
        view.thenApply(String::length);

CompletionStage<String> chain =
        view.thenCompose(value ->
                CompletableFuture.completedFuture(
                        "processed:" + value));
~~~

Đây là đoạn minh họa trong method với `source` kiểu `CompletableFuture<String>`. Client có thể tạo **các dependent stages** để xử lý dữ liệu. Tuy nhiên interface `CompletionStage` **không** có các method `complete`, `cancel`, `obtrudeValue` hay `join`.

Khi caller chỉ nhận `CompletionStage<T>`, code sau **không biên dịch**:

~~~java
CompletionStage<String> view = source.minimalCompletionStage();

// view.complete("fake");   // Không có method complete ở interface.
// view.cancel(true);       // Không có method cancel ở interface.
// view.join();             // Không có method join ở interface.
~~~

Các dòng comment là ví dụ về **compile-time restriction**, không phải code runnable độc lập. Nếu cần chờ ở ranh giới hệ thống, interface có `toCompletableFuture()`.

### Điểm tinh tế: runtime object không chỉ là một interface trừu tượng

Implementation JDK chuẩn có thể dùng một class nội bộ mở rộng `CompletableFuture` cho minimal stage. Vì vậy có người thử cast minimal stage thành `CompletableFuture` rồi gọi `complete/get/join`.

**Đừng làm điều đó.** Các method không thuộc `CompletionStage` **không được hỗ trợ** trên minimal stage; implementation chuẩn có thể ném `UnsupportedOperationException`. Điều đúng là:
- Giữ biến dưới type `CompletionStage<T>`.
- Dùng `thenApply`, `thenCompose`, `handle` và các methods thuộc interface.
- Nếu cần API `Future` ở caller, chuyển thành **future độc lập** qua `toCompletableFuture()`.

Đừng suy “đã cast thành CompletableFuture thì client đã lấy lại quyền sửa source”. Nếu một method bị unsupported, cast không làm thay đổi hợp đồng của stage.

## 7. toCompletableFuture(): cầu nối, không phải rò rỉ quyền owner

`CompletionStage<T>.toCompletableFuture()` trả `CompletableFuture<T>` để tương tác với code cần Future API như `join/get`, `get(timeout)`, `cancel`.

Javadoc `CompletableFuture.minimalCompletionStage()` ghi rõ: **trừ khi subclass override**, gọi `toCompletableFuture()` trên minimal stage có thể tạo ra **một non-minimal CompletableFuture mới**, có đầy đủ method. Điều đó không đồng nghĩa trả **source gốc**.

### Ví dụ độc lập 2: sửa future lấy từ toCompletableFuture không sửa source

Lưu **MinimalStageBridgeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class MinimalStageBridgeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletionStage<String> published =
                source.minimalCompletionStage();

        CompletableFuture<String> clientBridge =
                published.toCompletableFuture();

        boolean clientCompleted = clientBridge.complete("fake");
        boolean sourceWasDone = source.isDone();

        source.complete("real");
        String stageResult = published
                .thenApply(value -> "observed:" + value)
                .toCompletableFuture()
                .join();

        System.out.println("clientCompleted=" + clientCompleted);
        System.out.println("sourceWasDone=" + sourceWasDone);
        System.out.println("source=" + source.join());
        System.out.println("clientBridge=" + clientBridge.join());
        System.out.println("stageResult=" + stageResult);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac MinimalStageBridgeDemo.java
java MinimalStageBridgeDemo
~~~

Stdout:

~~~text
clientCompleted=true
sourceWasDone=false
source=real
clientBridge=fake
stageResult=observed:real
~~~

**Giải thích kỹ:**

- `published` là minimal stage theo dõi source.
- `clientBridge` là CompletableFuture không phải source. Client `complete("fake")` thành công trên bridge của nó.
- `source.isDone()` vẫn false trước khi owner complete.
- Owner sau đó hoàn tất `source` bằng "real"; minimal stage và chuỗi `thenApply` nhận dữ liệu đó.
- `clientBridge` đã bị hoàn tất độc lập, nên vẫn giữ "fake".
- Việc gọi `published.toCompletableFuture()` để **tạo cầu nối mới** là hợp lệ; không đòi hỏi can thiệp quyền owner.

**Cảnh báo:** Không nên nói `toCompletableFuture()` của **mọi CompletionStage implementation** đều tạo bản sao. Với một `CompletableFuture` thường, `source.toCompletableFuture()` có thể trả **chính source**. Hợp đồng tránh rò rỉ ở đây gắn với **minimal stage do CompletableFuture.minimalCompletionStage() tạo**, không phải tất cả CompletionStage trên đời.

## 8. Khi nào chọn copy, khi nào chọn minimal?

| Điều kiện | Nên cân nhắc |
|---|---|
| Public API mới chỉ cần chain, không cần caller manipulate `Future` | `CompletionStage<T>` từ `minimalCompletionStage()` |
| Legacy API bắt buộc return `CompletableFuture<T>` | `copy()` |
| Client thực sự cần `join/get(timeout)` trực tiếp | `copy()` hoặc `minimalStage.toCompletableFuture()` tại boundary |
| Muốn tránh client được quyền `complete` nhầm trên giá trị trực tiếp nhận | `minimalCompletionStage()` |
| Muốn client có thể complete/cancel **view riêng** mà source không bị sửa | `copy()` |
| Muốn client hủy **computation thực sự** do service sở hữu | Cần **cancel API riêng** có contract và authorization rõ; cả hai không tự làm việc này |
| Muốn deep copy mutable result | Dùng immutable DTO/defensive data copy; hai method **không** deep-copy T |
| Muốn ngăn code không tin cậy can thiệp vào toàn JVM | Cần isolation/security boundary khác; hai method không phải sandbox |

**Quy tắc thiết kế thường dùng:** expose `CompletionStage<T>` qua `minimalCompletionStage()` ở public async contract; chỉ expose `CompletableFuture<T>` qua `copy()` khi integration thật sự cần concrete type.

## 9. Ví dụ độc lập 3: một service expose cả hai kiểu nhưng giữ source private

Lưu **CompletionOwnershipServiceDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletionOwnershipServiceDemo {
    static final class ResultService {
        private final CompletableFuture<String> internal =
                new CompletableFuture<>();

        CompletionStage<String> observe() {
            return internal.minimalCompletionStage();
        }

        CompletableFuture<String> legacyFuture() {
            return internal.copy();
        }

        boolean finish(String value) {
            return internal.complete(value);
        }

        boolean isFinished() {
            return internal.isDone();
        }
    }

    public static void main(String[] args) {
        ResultService service = new ResultService();

        CompletionStage<String> view = service.observe();
        CompletableFuture<String> legacy = service.legacyFuture();

        legacy.complete("legacy-fake");
        boolean ownerWasDone = service.isFinished();

        service.finish("actual");
        String observed = view
                .thenApply(x -> x.toUpperCase())
                .toCompletableFuture()
                .join();

        System.out.println("ownerWasDone=" + ownerWasDone);
        System.out.println("observed=" + observed);
        System.out.println("legacy=" + legacy.join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CompletionOwnershipServiceDemo.java
java CompletionOwnershipServiceDemo
~~~

Stdout:

~~~text
ownerWasDone=false
observed=ACTUAL
legacy=legacy-fake
~~~

Ở đây:
- Service giữ `internal` private, chỉ `finish` có quyền complete source.
- Client được `observe` để chain, `legacyFuture` là copy có quyền tự complete **copy**.
- Một client thao tác trên legacy view không thể đẩy source sang done.
- Completion của owner vẫn truyền tới minimal stage view, nên observer thấy ACTUAL.
- Legacy copy vốn đã completed fake không tự đổi thành actual.

Nếu service muốn cho caller yêu cầu hủy tác vụ thật, thiết kế **một method riêng** như `requestCancellation()` với lifecycle rõ ràng và quyền truy cập phù hợp. Không dùng việc expose source gốc như một “kênh cancellation” ngoài ý muốn.

## 10. Luồng completion khi client không tự sửa bản sao

Giả sử `source`, `copy` và `minimal` lúc đầu đều chưa hoàn tất:

~~~text
t0: source = incomplete
    copy   = incomplete
    minimal= incomplete

t1: source.complete("OK")
      │
      ├─ copy completes normally with "OK"
      └─ minimal completes normally with "OK"
            └─ continuation registered by client runs

Client đã chỉ quan sát, không chủ động complete/cancel copy.
~~~

Nếu source hoàn tất trước khi client gọi `copy()` hay `minimalCompletionStage()`, kết quả view mới **đã hoàn tất** theo trạng thái nguồn. Không cần tạo worker riêng chỉ để duy trì hai views. Các methods này là cơ chế phụ thuộc completion, **không phải tác vụ chạy tính toán async mới**.

Nếu client đã tự hoàn tất copy **trước** source, copy giữ outcome riêng. Nếu client đã complete các dependent stages tự tạo trên copy, những stages đó cũng có outcome theo graph của client.

### Không bảo đảm thứ tự callbacks

Một source có thể có nhiều dependents; thứ tự chạy callbacks từ completion không phải contract để xây business ordering. Đừng dùng “đăng ký callback A trước B” làm giao thức giao dịch. Nếu nghiệp vụ đòi thứ tự, xây chain rõ ràng: `thenCompose`/`thenRun` theo dependency, hoặc executor tuần tự có quyền sở hữu.

## 11. Exceptional completion đi qua copy/minimal như thế nào?

Giả sử owner gọi:

~~~java
source.completeExceptionally(
        new IllegalStateException("upstream failure"));
~~~

`copy()` và `minimalCompletionStage()` sẽ hoàn tất exceptionally. Theo JDK, khi source completed exceptionally, views sẽ nhận một `CompletionException` với nguyên nhân thích hợp.

Điểm cần phân biệt:

- `join()` trên CompletableFuture bị exceptional có thể ném `CompletionException`.
- `get()` thường ném `ExecutionException` (checked), có cause mang exception gốc.
- `whenComplete` quan sát `(value, error)` tương ứng.
- `exceptionally` có thể recover thành một giá trị khác ở **dependent stage của client**, không có quyền sửa source.
- Khi source bị cancel, completion thường lan sang các dependents như exceptional completion; việc `isCancelled()` ở một dependent **không bắt buộc** giống `isCancelled()` của source, vì cancellation có thể được bọc thành CompletionException.

### Ví dụ độc lập 4: lỗi của source truyền qua cả hai views

Lưu **CompletionViewFailureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class CompletionViewFailureDemo {
    private static String causeType(CompletableFuture<?> future) {
        try {
            future.join();
            return "none";
        } catch (CompletionException e) {
            Throwable cause = e.getCause();
            return cause.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> copy = source.copy();
        CompletionStage<String> stage =
                source.minimalCompletionStage();

        source.completeExceptionally(
                new IllegalStateException("upstream failed"));

        System.out.println("copyCause=" + causeType(copy));
        System.out.println("stageCause=" +
                causeType(stage.toCompletableFuture()));
        System.out.println("sourceExceptional=" +
                source.isCompletedExceptionally());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CompletionViewFailureDemo.java
java CompletionViewFailureDemo
~~~

Stdout:

~~~text
copyCause=IllegalStateException
stageCause=IllegalStateException
sourceExceptional=true
~~~

**Vì sao?** Hai views đều đi theo exceptional result của source. `join` bộc lộ `CompletionException`; cause là `IllegalStateException` mà owner đã truyền. Trong ví dụ không có cạnh tranh với client tự complete copy, do đó không có ambiguity về outcome.

**Lưu ý:** Trong hệ thống thật, nếu exception ban đầu đã là một `CompletionException`, cách bọc cause được xử lý theo quy tắc `CompletableFuture`; đừng viết code phụ thuộc vào một số lượng lớp wrapper cố định mà không kiểm tra loại Throwable. Với logging cần lưu stack trace gốc và nhận diện nguyên nhân.

## 12. copy và CompletionStage không phải deep copy của dữ liệu T

Đây là một bẫy lớn: `copy()` sao chép **completion state/outcome dependency**, không copy nội dung mutable mà future trả về.

Ví dụ `T = List<String>`:
- Source hoàn tất với reference tới một `ArrayList`.
- Copy hoàn tất bình thường với **cùng reference** đó (theo semantics `thenApply(x -> x)`).
- Client có thể mutate danh sách và owner nhìn thấy thay đổi nếu vẫn giữ reference.
- `minimalCompletionStage` cũng chuyển **giá trị T**, không tự clone object.

### Ví dụ độc lập 5: cùng dữ liệu mutable dù là hai future khác nhau

Lưu **CompletionViewShallowValueDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class CompletionViewShallowValueDemo {
    public static void main(String[] args) {
        List<String> internalData = new ArrayList<>();
        internalData.add("server");

        CompletableFuture<List<String>> source =
                CompletableFuture.completedFuture(internalData);
        CompletableFuture<List<String>> view = source.copy();

        view.join().add("client");

        System.out.println("sameReference=" +
                (source.join() == view.join()));
        System.out.println("sourceSize=" + source.join().size());
        System.out.println("sourceData=" + source.join());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CompletionViewShallowValueDemo.java
java CompletionViewShallowValueDemo
~~~

Stdout:

~~~text
sameReference=true
sourceSize=2
sourceData=[server, client]
~~~

Trong ví dụ này mọi việc diễn ra tuần tự ở main nên không có data race; nó chỉ chứng minh **object aliasing**. Nếu các threads đồng thời sửa/đọc ArrayList, còn có nguy cơ data race và trạng thái không nhất quán.

Giải pháp có thể là:
- Trả một `record`/immutable DTO có fields không cho sửa.
- Dùng `List.copyOf(mutableList)` khi xây kết quả để tạo snapshot danh sách; chú ý **shallow copy của phần tử**: nếu element mutable vẫn có thể bị sửa.
- Dùng immutable persistent data structures khi cần chia sẻ an toàn.
- Không expose internal collections trực tiếp; tạo defensive copy của value **trước khi hoàn tất source** hoặc khi tạo view với `thenApply(v -> deepCopy(v))` nếu thực sự cần deep copy.

### Copy cả dữ liệu nếu yêu cầu

~~~java
CompletableFuture<List<String>> publicCopy =
        internalFuture.thenApply(List::copyOf);
~~~

Đây là đoạn minh họa, `internalFuture` có kiểu `CompletableFuture<List<String>>`. `List.copyOf` cung cấp một **danh sách không thể sửa**, nhưng **không deep-copy các object element mutable**. Ngoài ra, `List.copyOf` từ chối null elements; phải xét contract dữ liệu trước khi dùng.

Nếu mục tiêu vừa là hạn chế completion vừa là snapshot:
- Owner xây immutable result.
- Expose `minimalCompletionStage` của future đã chứa immutable result.
- Hoặc tạo future kết quả `thenApply(immutableConversion).minimalCompletionStage()`, bảo đảm `immutableConversion` đúng với domain.

## 13. Cancellation: cancel view không mặc nhiên cancel computation gốc

Trong `CompletableFuture`, cancellation là một dạng exceptional completion. Nó **không phải** hành động ngắt I/O hoặc kill worker tùy ý. Java docs nêu `mayInterruptIfRunning` không có hiệu lực đối với implementation `CompletableFuture` mặc định.

Xét:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> view = source.copy();

view.cancel(true);
System.out.println(source.isDone()); // false trong cùng thread, chưa ai complete source
~~~

Bản sao bị cancel, source vẫn pending. Client có thể dùng cancel như một lựa chọn **ngừng quan tâm view riêng**, nhưng owner vẫn có thể tiếp tục công việc và complete source.

Đối với minimal stage:
- Nó không expose `cancel` trực tiếp trong interface.
- Nếu client gọi `toCompletableFuture()` rồi cancel **cầu nối**, hành vi đó không bảo đảm hủy source.
- Từ minimal stage, một client có thể gắn callback để quan sát/ignore kết quả, không cần có quyền cancel future owner.
- Nếu application cần người dùng yêu cầu hủy computation thực, **thiết kế một cancel token/API riêng** theo quyền hạn và lifecycle; không coi cancel view là đủ.

### Ví dụ độc lập 6: cancel bản sao giữ source nguyên vẹn

Lưu **CompletionCopyCancellationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletionCopyCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> clientView = source.copy();

        boolean cancelled = clientView.cancel(true);
        boolean ownerWasDone = source.isDone();

        boolean ownerCompleted = source.complete("finished");
        System.out.println("cancelledView=" + cancelled);
        System.out.println("ownerWasDone=" + ownerWasDone);
        System.out.println("ownerCompleted=" + ownerCompleted);
        System.out.println("source=" + source.join());
        System.out.println("viewCancelled=" + clientView.isCancelled());
    }
}
~~~

Lệnh:

~~~bash
javac CompletionCopyCancellationDemo.java
java CompletionCopyCancellationDemo
~~~

Stdout:

~~~text
cancelledView=true
ownerWasDone=false
ownerCompleted=true
source=finished
viewCancelled=true
~~~

Task gốc vẫn có quyền hoàn tất sau khi view bị cancel. **Đừng suy rằng bản sao bị cancel thì I/O/batch work do owner thực hiện đã dừng**.

## 14. Timeout: cẩn thận API thay đổi chính future nào

`orTimeout(timeout, unit)` và `completeOnTimeout(value, timeout, unit)` **hoàn tất chính CompletableFuture nhận lệnh gọi** nếu chưa done sau khoảng thời gian.

Vì vậy:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

source.orTimeout(1, TimeUnit.SECONDS);
// Tác động tới SOURCE — có thể phá ownership nếu client nhận source!
~~~

Nếu client nhận một `copy()`:

~~~java
CompletableFuture<String> view = source.copy();
view.orTimeout(1, TimeUnit.SECONDS);
// Tác động tới VIEW riêng; không tự làm source bị TimeoutException.
~~~

Đây là các đoạn minh họa trong method với import `TimeUnit`. Quan trọng: đây **không** phải timeout của I/O gốc; nếu source được tính bằng remote request, network call có thể vẫn chạy sau khi view timeout.

**Không dùng `minimalStage.toCompletableFuture()` rồi gọi `orTimeout` và tưởng source bị timeout.** Cầu nối là một future độc lập; timeout cục bộ có thể đúng cho caller, nhưng owner vẫn tiếp tục theo lifecycle riêng.

### Timeout của caller không mutate future

`get(timeout, unit)` chờ có giới hạn và ném `TimeoutException` nếu chưa hoàn tất. Nó **không tự complete/cancel** bất kỳ CompletableFuture nào chỉ vì caller hết thời gian đợi.

| API | Tác động lên | Khi hết hạn |
|---|---|---|
| `source.get(timeout)` | Chỉ lời chờ caller | Throw TimeoutException; source vẫn có thể pending |
| `source.orTimeout(...)` | Chính source | Source exceptional nếu chưa done |
| `source.completeOnTimeout(value, ...)` | Chính source | Source hoàn tất bình thường với value nếu chưa done |
| `source.copy().orTimeout(...)` | Copy mới | Copy exceptional; source vẫn do owner điều khiển |
| `source.minimalCompletionStage().toCompletableFuture().orTimeout(...)` | Cầu nối mới | Cầu nối exceptional, không tự complete source |

**Lưu ý**: muốn một overall deadline đúng cần quản lý cả việc scheduling, queue, I/O timeout và cleanup. Timeout của view không phải termination guarantee của worker.

## 15. Hành vi completion khi nguồn đã thành công trước khi tạo view

Không phải hai API này tạo tasks mới cần chạy. Nếu source đã done:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> copy = source.copy();
CompletionStage<String> minimal = source.minimalCompletionStage();

System.out.println(copy.join());
System.out.println(minimal.toCompletableFuture().join());
~~~

Đây là đoạn tích hợp, import `CompletableFuture` và `CompletionStage`. Stdout hai dòng đều là `ready`.

Khi source chưa done, view mới theo dõi completion sau này. Khi source đã done, view có completion tương ứng. Không cần dùng `supplyAsync` để “gây bất đồng bộ” chỉ vì đang tạo một dependent stage.

### Callback của client có thể chạy ở thread nào?

`thenApply` không có hậu tố Async có thể chạy ngay trong thread đang tạo callback nếu source đã done, hoặc trong thread làm source complete, hoặc các thread khác tham gia completion. Không nên dựa vào thread name của callback để suy ra owner.

Nếu callback có tính blocking/nặng, client nên dùng `thenApplyAsync(fn, executor)` với một executor phù hợp, tránh chiếm thread hoàn tất source. Bản thân `copy()` và `minimalCompletionStage()` không cấp cho client một executor mới.

## 16. Chuỗi dependent stages vẫn có thể được client tự hoàn tất

Ngay cả khi client chỉ nhận `CompletionStage<T>`, client có quyền **tạo dependent stages**. Những stages là kết quả của các phép `thenApply`, `thenCompose`, `handle`, v.v. có own completion semantics. Nếu client chuyển dependent stage thành `CompletableFuture` của mình, client có thể mutate **stage do client sở hữu**, không phải source.

Ví dụ:

~~~java
CompletionStage<Integer> projected =
        serviceView.thenApply(String::length);

CompletableFuture<Integer> ownFuture =
        projected.toCompletableFuture();

ownFuture.complete(0); // Kết quả riêng của caller.
~~~

Đây là đoạn method tích hợp với `serviceView` trả `CompletionStage<String>`. Việc client tự hạ ownFuture về 0 không có nghĩa future gốc của service đã trả chuỗi có length 0.

**Không xem các view là “bằng chứng dữ liệu không thể bị người nhận làm giả”**. Nếu một client kiểm soát output pipeline riêng của mình, nó có thể tự tạo result giả ở phía nó. Ranh giới quan trọng là **nó không thể thay đổi sự thật của source được service sở hữu thông qua API đã cấp**.

## 17. Interface nhỏ là thiết kế tốt, nhưng phải kiểm tra implementation

Một câu hay được nói: “Chỉ cần return CompletionStage thì mọi thứ an toàn.” Điều này **chưa đủ**, vì source concrete vẫn có thể bị cast nếu trả trực tiếp.

Phân biệt:

~~~java
public CompletionStage<String> unsafeReadOnly() {
    return internal; // chính object gốc
}

public CompletionStage<String> betterReadOnly() {
    return internal.minimalCompletionStage();
}
~~~

Nếu có một method `getInternalFuture()`, exposure ở nơi khác có thể làm mọi protection mất ý nghĩa. Cần review toàn bộ public API, callback registry và object graph.

Ngay cả với minimal stage:
- T chỉ được chuyển theo reference; nếu mutable, client vẫn có thể mutate value.
- Client có thể tổ chức callbacks tạo CPU hoặc I/O workload mới; API này không kiểm soát tài nguyên của **mọi thao tác client tự tạo**.
- Client có thể quyết định outcome của **copies** hoặc **dependent stages** của mình.
- Java reflection/môi trường có quyền cao là một bài toán an ninh khác; minimal stage không phải boundary cho mã độc không tin cậy.
- Nếu code subclass override các methods, hãy dựa vào public contract và test implementation, không suy mọi runtime class sẽ giống exact JDK internal class.

**Thiết kế đúng:** private source future, nhỏ hóa public interface, dùng immutable results, có API cancellation và ownership riêng khi thật sự cần.

## 18. So sánh completedStage và completedFuture

Java 9+ còn có:

~~~java
CompletableFuture<String> mutableFuture =
        CompletableFuture.completedFuture("ok");

CompletionStage<String> minimalStage =
        CompletableFuture.completedStage("ok");
~~~

`completedFuture("ok")` trả một `CompletableFuture` đã done **nhưng vẫn expose các method mutation như `obtrudeValue`**. Vì vậy “đã completed” không đồng nghĩa “không thể bị thay đổi về mặt quan sát”.

`completedStage("ok")` trả một `CompletionStage` hỗ trợ interface-only semantics tương tự minimal stage, khi result **đã có sẵn**. Nếu một computation còn pending và cần phát hành view, dùng `source.minimalCompletionStage()`.

Tương tự:
- `failedFuture(Throwable)` trả full CompletableFuture completed exceptionally.
- `failedStage(Throwable)` trả minimal CompletionStage completed exceptionally.

### Chọn completedStage trong thiết kế API

~~~java
public CompletionStage<String> cachedLookup(String key) {
    if (key.isBlank()) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("key blank"));
    }
    return CompletableFuture.completedStage("cached:" + key);
}
~~~

Đây là method độc lập đặt trong class và cần imports `CompletionStage`, `CompletableFuture`. Nó trả stage đã hoàn tất với API bị giới hạn; không cần tự tạo source CompletableFuture mutable cho trường hợp kết quả đã biết.

## 19. Thời điểm tạo bản sao và lỗi race

Khi owner và client cùng tác động vào different futures:
- Owner complete source.
- Client complete/cancel copy.
- Các operations này có thể xảy ra đồng thời.
- **Completion nào đến trước trên copy** sẽ quyết định outcome của copy (trừ các override/obtrude do client tự gọi sau đó).
- Source chỉ bị điều khiển bởi owner và những bên có thực sự giữ reference tới source.

Vì vậy không được hứa “copy sẽ luôn phản ánh kết quả cuối của source” trong trường hợp client cố ý hoàn tất copy trước source. `copy` là **defensive completion isolation**, không phải một live proxy mà consumer không thể can thiệp.

Đối với minimal stage, client không có method complete trực tiếp. Khi source hoàn tất, minimal stage phản ánh outcome theo contract, và client có thể chọn tạo các derivatives để tính toán hoặc phục hồi lỗi.

### Cancellation và exceptional propagation

Nếu source bị cancel, bản thân source có thể báo `isCancelled()==true`. Một dependent `copy` có thể completed exceptionally với `CompletionException` bọc `CancellationException`, vì vậy `copy.isCancelled()` không nên được coi là đồng bộ tuyệt đối với `source.isCancelled()`. Để phân loại upstream cancellation, inspect exception cause chain, không dùng duy nhất trạng thái cancel của các derivatives.

Tuy nhiên, nếu client gọi `copy.cancel(...)` trực tiếp, bản sao sẽ có trạng thái cancelled theo chính lời gọi đó, còn source không bị cancel.

## 20. Side effects, data race và consistency

Một future chỉ là **phương tiện báo outcome**, không phải transaction. Nếu source hoàn tất sau khi đã thực hiện side effects:
- Client `copy.cancel()` không rollback transaction.
- Client `minimalStage.toCompletableFuture().complete("fake")` không khiến database ghi lại fake hay owner mất state.
- Client mutate một DTO mutable có thể làm service bị ảnh hưởng nếu cả hai chia cùng reference.
- Nếu producer publish một object rồi tiếp tục mutate không đồng bộ, callbacks có thể đọc dữ liệu đang đổi, dẫn tới data race.
- Nếu mã client trong callback ném exception, dependent stage có thể fail, nhưng điều đó không nhất thiết làm source fail.

Các bước phòng ngừa:
1. Trả immutable value types hoặc defensive snapshots.
2. Giữ source private, không expose alias qua getters/public collections.
3. Không đặt callbacks bên ngoài trong critical section kéo dài.
4. Dùng `whenComplete` để quan sát outcome, tránh ném exception không mong muốn trong logging.
5. Đặt timeout cho external operations và truyền deadline tương thích.
6. Định nghĩa cancellation upstream ở một API/service method riêng khi thực sự muốn hủy công việc.
7. Nếu cần write consistency, dùng transaction/idempotency/compensation đúng domain; view future không thay thế các cơ chế này.

## 21. Các lỗi thường gặp trong code review

**Lỗi 1 — Trả trực tiếp `CompletableFuture` private.** Client có thể `complete`/`cancel` chính source.

**Lỗi 2 — Chỉ thay return type thành `CompletionStage` nhưng vẫn return source object.** Client có thể cast concrete object về CompletableFuture và can thiệp.

**Lỗi 3 — Nghĩ `copy()` là immutable future.** Nó là CompletableFuture đầy đủ, client vẫn complete/cancel/obtrude **copy**.

**Lỗi 4 — Nghĩ `minimalCompletionStage()` là interface mask đơn thuần trên cùng source.** API trả một stage mới với restricted completion semantics.

**Lỗi 5 — Gọi `join()` trực tiếp trên CompletionStage interface.** Interface không có join; dùng `toCompletableFuture()` tại boundary nếu cần.

**Lỗi 6 — Cast minimal stage thành CompletableFuture rồi gọi complete/join.** Không được bảo đảm; implementation chuẩn có thể ném UnsupportedOperationException cho method ngoài CompletionStage.

**Lỗi 7 — Nghĩ `toCompletableFuture()` trên minimal stage trả source gốc.** Java docs nêu nó tạo non-minimal future mới theo mặc định, không trao source.

**Lỗi 8 — Nghĩ mọi `toCompletableFuture()` đều defensive copy.** Với CompletableFuture bình thường nó có thể trả chính instance; xem implementation/hợp đồng.

**Lỗi 9 — Nghĩ `copy()` sao chép sâu payload T.** Nó chia reference kết quả như identity map; mutable payload vẫn được chia sẻ.

**Lỗi 10 — Dùng `completeOnTimeout`/`orTimeout` trên source từ client.** Sửa source outcome ngoài quyền; hãy dùng view/copy nếu chỉ cần timeout local.

**Lỗi 11 — Tin cancel copy dừng I/O owner.** Cancellation của copy không tự lan ngược tới computation nguồn.

**Lỗi 12 — Tin `cancel(true)` của CompletableFuture luôn interrupt worker.** mayInterruptIfRunning không có hiệu lực theo Javadoc CF mặc định.

**Lỗi 13 — Nhầm exceptional propagation với cancellation flag.** Copy nhận CompletionException/cause, `isCancelled` có thể không giống source.

**Lỗi 14 — Không bảo vệ shared mutable results.** completion isolation không phải data isolation.

**Lỗi 15 — Gọi `obtrudeValue` trên copy rồi tưởng source thay đổi.** Nó tác động đến copy; nếu gọi trên source thì lại phá owner semantics.

**Lỗi 16 — Dùng API hạn chế làm sandbox.** Người nhận vẫn có thể làm giả outcome của graph riêng hoặc tương tác với mutable T; cần security boundary khác khi code không tin cậy.

**Lỗi 17 — Không xử lý duplicate completion.** Nếu source đã complete, `complete` lần sau trả false; không nên vô tình bỏ qua kết quả “đã có owner khác complete”.

**Lỗi 18 — Gắn callback blocking dài vào stage non-Async.** Có thể chiếm thread đang complete source; dùng Async overload với executor phù hợp.

**Lỗi 19 — Không đóng executor sở hữu.** copy/minimal không tự quản lý worker lifecycle, resource cleanup hoặc deadline.

**Lỗi 20 — Dùng deep copy quá trễ sau khi source expose mutable value.** Client có thể đã giữ reference trước đó; thiết kế immutable ngay ở boundary.

## 22. Checklist cho public async API

- [ ] Source `CompletableFuture<T>` do component sở hữu được giữ `private`?
- [ ] Public API có thực sự chỉ cần `CompletionStage<T>` không?
- [ ] Đã tránh `return internal;` dù return type interface?
- [ ] Nếu cần full CompletableFuture ở client, đã dùng `copy()`?
- [ ] Đã hiểu client có thể complete/cancel **copy riêng**, nhưng không complete source?
- [ ] Nếu dùng minimal, đã hiểu client vẫn có thể dùng `toCompletableFuture()` để chờ result?
- [ ] Không giả định mọi CompletionStage implementation đều defensive khi toCompletableFuture?
- [ ] Đã bảo vệ mutable result T bằng immutable DTO/defensive copy?
- [ ] Có phân biệt normal completion với exceptional/cancelled completion?
- [ ] Các callbacks không làm block owner thread không cần thiết?
- [ ] Có cancellation API riêng nếu client cần hủy công việc thực?
- [ ] Có timeout local cho caller mà không sửa source ngoài ý muốn?
- [ ] Có xét side effects đã xảy ra trước cancellation?
- [ ] Có kiểm tra race client complete copy vs source complete, không suy view luôn phản ánh owner?
- [ ] Nếu dùng Java subclass của CompletableFuture, đã test các overrides hợp đồng?
- [ ] Đã kiểm thử tình huống source completed trước khi tạo view?
- [ ] Đã test source lỗi và propagation cause?
- [ ] Đã kiểm soát owner executor/queue và shutdown?
- [ ] Có documentation công khai về “client chỉ observe, không điều khiển source”?

## 23. Câu hỏi luyện tập có đáp án

**Câu 1.** `CompletableFuture<String> internal` được trả nguyên qua method khai báo `CompletionStage<String> result()`. Đã bảo vệ source hoàn toàn chưa?

**Đáp án:** Chưa. Runtime object có thể vẫn là CompletableFuture gốc, client có thể cast nếu được tiếp cận reference đó. Dùng `minimalCompletionStage()` để không expose source.

**Câu 2.** `CompletableFuture<String> exposed = internal.copy()`; client gọi `exposed.complete("fake")`. Source thay đổi không?

**Đáp án:** Không. `copy()` là dependent CompletableFuture riêng. Client chỉ sửa outcome của copy.

**Câu 3.** `CompletionStage<String> view = internal.minimalCompletionStage()`. Client có gọi `view.complete("fake")` trực tiếp được không?

**Đáp án:** Không. Interface CompletionStage không có `complete`.

**Câu 4.** Client gọi `view.toCompletableFuture().complete("fake")`. Source có bị completed fake không?

**Đáp án:** Với minimal stage của CompletableFuture chuẩn, không. `toCompletableFuture` tạo non-minimal future mới theo Javadoc, không trả source.

**Câu 5.** Source hoàn tất bình thường với `ArrayList<String>`. Copy nhận một danh sách độc lập không?

**Đáp án:** Không. `copy` chuyển cùng reference T. Nếu cần data isolation, tạo snapshot/immutable result.

**Câu 6.** Source đã completed exceptionally. Copy và minimal stage nhìn thấy gì?

**Đáp án:** Exceptional completion tương ứng, theo Javadoc với CompletionException bọc nguyên nhân. `join` trên một CompletableFuture view có thể ném CompletionException.

**Câu 7.** Client `copy.cancel(true)`; task nguồn có chắc đã dừng?

**Đáp án:** Không. Chỉ copy bị cancel; mặc định CompletableFuture.cancel không bảo đảm interrupt computation hay lan ngược tới source.

**Câu 8.** Nếu API cần chờ đồng bộ và caller chưa thể dùng CompletionStage-only, nên làm gì?

**Đáp án:** Cân nhắc trả `copy()` cho legacy API hoặc dùng `minimalStage.toCompletableFuture()` tại caller để `join/get` mà không expose source.

**Câu 9.** Sự khác nhau chính giữa `completedFuture(value)` và `completedStage(value)`?

**Đáp án:** completedFuture trả full CompletableFuture với methods mutation; completedStage trả interface-limited CompletionStage đã completed.

**Câu 10.** Có phải minimalCompletionStage dùng để chống mã độc chạy cùng JVM?

**Đáp án:** Không. Nó là API/encapsulation boundary cho quyền completion, không phải security sandbox.

**Câu 11.** Nếu client tạo `copy.orTimeout(...)` rồi timeout, source có tự completed exceptionally không?

**Đáp án:** Không. Timeout đặt trên copy; source vẫn do owner quyết định. Background I/O cũng không tự bị kill.

**Câu 12.** Vì sao `source.copy()` tương đương `source.thenApply(x -> x)`?

**Đáp án:** Cả hai tạo dependent future mới, chuyển normal result theo identity function, và propagation exceptional theo quy tắc CompletionStage.

## 24. Tài liệu chính thức

- **CompletableFuture, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **CompletionStage, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Future, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **CompletionException, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html
- **CancellationException, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html
- **Java 17 API, CompletableFuture.copy():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#copy()
- **Java 17 API, CompletableFuture.minimalCompletionStage():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#minimalCompletionStage()

**Tổng kết:** `minimalCompletionStage()` cấp **một CompletionStage hạn chế quyền thao tác completion**, còn `copy()` cấp **một CompletableFuture riêng có thể mutate nhưng không làm đổi source**. Chúng giúp service giữ ownership của việc complete/cancel future gốc. Tuy nhiên cả hai **không copy sâu dữ liệu T, không tự cancel background work, không bảo đảm client sẽ thấy source outcome nếu họ cố tình hoàn tất view riêng, và không thay thế ranh giới bảo mật/transaction**. Hãy giữ future gốc private, expose đúng abstraction và trả kết quả immutable khi có thể.
