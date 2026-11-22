# 8.7 Bọc xử lý lỗi bằng catchException và dọn dẹp bằng tryFinally

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 8. Kết hợp lời gọi  
**Phạm vi:** Hai combinator của `java.lang.invoke.MethodHandles`: `catchException` và `tryFinally` (Java 17+).

## 1. Mục tiêu học tập

Khi chương trình phải tạo lời gọi động bằng `MethodHandle`, ta thường muốn thực thi logic đích mà vẫn giữ những chính sách quen thuộc: phục hồi khi một loại exception xuất hiện, ghi log, giải phóng tài nguyên và không để lại trạng thái dở dang. Hai combinator giải quyết các nhu cầu đó mà không cần biến mọi phương thức đích thành một khối `try/catch/finally` riêng.

Sau bài này, bạn sẽ:

1. Hiểu `MethodHandles.catchException(target, exType, handler)` xử lý **đúng nhóm exception nào**, chuyển những đối số nào đến handler, và giữ `MethodType` của adapter thế nào.
2. Hiểu `MethodHandles.tryFinally(target, cleanup)` gọi cleanup trên cả đường **trả về bình thường** lẫn **ném exception**, bao gồm chữ ký bắt buộc của cleanup.
3. Phân biệt **khôi phục thành giá trị** (catchException) và **dọn dẹp sau khi gọi** (tryFinally); biết tại sao bản thân tryFinally không chuyển exception thành kết quả thành công.
4. Chọn thứ tự bọc hai combinator để xác định cleanup quan sát exception **trước hay sau recovery**.
5. Biết tác động của exception phát sinh trong cleanup, các quy tắc `MethodType` cho target/handler/cleanup, và trường hợp phương thức đích trả `void`.
6. Biên dịch và chạy ví dụ Java 17+, kiểm tra đầu ra thực tế thay vì suy luận từ tên API.

## 2. Combinator là một phép biến đổi trên method handle

Một `MethodHandle` mô tả cách gọi một tác vụ, đồng thời mang `MethodType`: danh sách kiểu tham số và kiểu trả về. `MethodHandles` cung cấp các **combinator** để xây handle mới có hành vi bổ sung từ các handle sẵn có:

~~~text
target:        (A, B, ...) -> R
                      |
             +--------+--------+
             |                 |
        catchException      tryFinally
             |                 |
        handler nếu lỗi   cleanup trên cả
        đúng loại         thành công và lỗi
             |                 |
           adapter: (A, B, ...) -> R
~~~

Đây là sơ đồ khái niệm, không phải bytecode. Cả hai combinator đều **trả một handle mới**, không sửa thân mã hay `MethodType` của target gốc. Hai handle adapter thường giữ **đúng kiểu lời gọi của target**; chỉ các handle phụ (handler/cleanup) cần chữ ký bổ sung để nhận thông tin về exception hoặc kết quả.

Cần phân biệt:

- **Lỗi khi ghép handle:** `IllegalArgumentException` (hoặc `NullPointerException` cho đầu vào null) có thể phát sinh ngay lúc gọi combinator nếu các `MethodType` không thỏa hợp đồng.
- **Lỗi khi thực thi target:** có thể bị xử lý bởi `catchException`, hoặc đi qua `tryFinally` sau khi cleanup được gọi.
- **Lỗi khi gọi adapter sai descriptor:** `MethodHandle.invokeExact` có thể ném `WrongMethodTypeException` nếu call site không khớp `adapter.type()`. Đây là kiểm tra invocation riêng, không có nghĩa handler/cleanup sai.

## 3. `catchException`: khôi phục khi gặp đúng loại lỗi

API:

~~~java
MethodHandle recovered =
        MethodHandles.catchException(target, exceptionType, handler);
~~~

Đây là đoạn minh họa có sẵn biến `target`, `exceptionType`, `handler`; không phải một chương trình độc lập.

### 3.1. Quy tắc chữ ký chính xác

Giả sử target có dạng:

~~~text
R target(A, B, C)
~~~

Handler có thể chỉ nhận exception, hoặc exception cộng **một phần đầu liên tiếp (prefix)** của các tham số target:

~~~text
R handler(E)
R handler(E, A)
R handler(E, A, B)
R handler(E, A, B, C)
~~~

Với `E` là **chính `exceptionType` hoặc một supertype phù hợp** trong vị trí tham số đầu tiên. Kiểu trả về `R` của handler **phải trùng** kiểu trả về `R` của target, kể cả khi nhánh handler luôn ném lỗi. Các tham số đứng sau exception phải trùng **đúng kiểu và thứ tự** với phần đầu tương ứng của target.

Không thể tùy ý bỏ tham số ở giữa rồi lấy tham số cuối. Nếu target nhận `(String, int)` thì handler `(IllegalArgumentException, int)` **không** có nghĩa “chỉ lấy tham số int thứ hai”: nó sai prefix vì đối số đầu target là `String`.

Ví dụ cụ thể:

~~~text
target:  (String, int)String
exType:  IllegalArgumentException
handler: (IllegalArgumentException, String)String
adapter: (String, int)String
~~~

Handler này lấy exception và đối số `String` đầu tiên của target; đối số `int` thứ hai bị bỏ. Khi target trả về bình thường, handler **không chạy**. Khi target ném `IllegalArgumentException` hoặc subtype của nó, handler chạy và giá trị handler trả về trở thành kết quả của adapter.

### 3.2. Ngữ nghĩa bằng giả mã

~~~java
String adapted(String text, int count) {
    try {
        return target(text, count);
    } catch (IllegalArgumentException error) {
        return handler(error, text);
    }
}
~~~

Đây là **pseudocode minh họa**, không phải khai báo thật có thể biên dịch độc lập vì các tên `target`/`handler` biểu diễn method handle. Đặc điểm quan trọng:

- Kiểu exception được so khớp theo loại thực tế tại runtime như `catch` tương ứng: subtype của `exType` cũng khớp.
- Một exception **không khớp `exType`** đi ra ngoài, không bị biến thành thành công.
- **Handler ném lỗi** thì lỗi mới đi ra ngoài; `catchException` không tự gọi lại chính handler để xử lý lỗi đó.
- Các đối số cung cấp cho handler là **đối số gốc của lời gọi adapter**, không phải trạng thái bị thay đổi bên trong stack frame của target.
- Handler không phải trả lại exception đã ném; nếu mục tiêu là log rồi ném tiếp, cần một handler có đúng return type danh nghĩa và đường ném được thiết kế rõ (ví dụ dùng combinator `throwException` khi thích hợp).
- Không bắt `Throwable`/`Exception` một cách tùy tiện trong hệ thống yêu cầu tính nhất quán: sự cố hạ tầng, bug và business error thường cần chính sách khác nhau.

## 4. `tryFinally`: cleanup trên cả hai đường đi

API:

~~~java
MethodHandle withCleanup =
        MethodHandles.tryFinally(target, cleanup);
~~~

`tryFinally` chạy target và sau đó thực thi cleanup **dù target trả về bình thường hay ném exception**, theo logic tương đương Java `try/finally`. Cần hiểu đầy đủ cấu trúc lời gọi để không tạo nhầm cleanup.

### 4.1. Chữ ký của cleanup khi target có kết quả

Giả sử:

~~~text
R target(A, B, C)
~~~

thì cleanup phải có các **tham số đầu bắt buộc**:

~~~text
R cleanup(Throwable, R)
~~~

và có thể nhận **một prefix** các tham số của target:

~~~text
R cleanup(Throwable, R, A)
R cleanup(Throwable, R, A, B)
R cleanup(Throwable, R, A, B, C)
~~~

Hai tham số đứng đầu là:

1. `Throwable failure`: **`null` nếu target trả bình thường**, hoặc exception mà target đã ném. Dùng `Throwable` là lựa chọn an toàn; dùng loại hẹp hơn có thể khiến một exception bất ngờ không gán được vào tham số cleanup và bị che bởi `ClassCastException`.
2. `R result`: **giá trị target trả về** khi thành công; khi target ném exception, JVM cung cấp **giá trị mặc định của kiểu `R`**: `null` với reference, `0` với kiểu số, `false` với boolean.

`cleanup` phải **trả đúng kiểu `R` như target**. Giá trị cleanup trả lại là kết quả cuối của adapter khi target hoàn thành bình thường; điều này cho phép log, chuẩn hóa, gắn nhãn hoặc xác nhận dữ liệu trước khi caller nhận kết quả. Nếu target ném exception thì **giá trị return của cleanup không biến lời gọi lỗi thành thành công**.

Với target nhận `(String, int)String`, cleanup phù hợp có thể có kiểu:

~~~text
(Throwable, String, String, int)String
~~~

Trong đó `String` thứ nhất sau `Throwable` là **result**, `String` tiếp theo là **đối số target thứ nhất**, và `int` là đối số target thứ hai. Nhầm result với đối số đầu target là một lỗi thiết kế rất phổ biến vì hai kiểu có thể cùng là String.

### 4.2. Target trả `void`: không có tham số result

Đối với:

~~~text
void target(A, B)
~~~

cleanup phải có return `void`, bắt đầu bằng `Throwable` và sau đó có thể nhận prefix của các tham số target:

~~~text
void cleanup(Throwable)
void cleanup(Throwable, A)
void cleanup(Throwable, A, B)
~~~

**Không** thêm tham số “`void result`” hoặc `Object result` vào cleanup. Kiểu `void` không có giá trị để truyền như một đối số Java. Chương trình `CleanupEdgeDemo` ở mục 7 minh họa trường hợp này.

### 4.3. Ngoại lệ sẽ đi đâu?

Ngữ nghĩa khái quát:

~~~text
target trả về R
    -> cleanup(null, R, originalArgs...)
    -> trả về giá trị do cleanup trả lại

target ném Throwable T
    -> cleanup(T, giá trị mặc định của R, originalArgs...)
    -> nếu cleanup trả bình thường: ném lại T
    -> nếu cleanup ném Throwable U: U là lỗi thoát ra
~~~

Điểm mấu chốt: `tryFinally` **không tự catch lỗi thành một kết quả fallback**. Nếu muốn recovery, phải thêm `catchException` hoặc một chính sách xử lý riêng.

Khi cleanup **cũng ném lỗi**, lỗi cleanup có thể che lỗi ban đầu tương tự một khối `finally` thông thường có ném exception. `tryFinally` không mặc định tự ghi lỗi ban đầu vào `Throwable.getSuppressed()` của lỗi cleanup. Nếu phải giữ cả hai lỗi, cần thiết kế explicit policy: ghi log/báo cáo lỗi cleanup, chủ động quản lý suppressed exception khi phù hợp, hoặc dùng `try-with-resources` trong mã Java thông thường.

### 4.4. Cleanup **không** tự quản lý tài nguyên

Tên `tryFinally` có thể tạo cảm giác nó tự đóng file/socket/connection. Không đúng. Nó chỉ **gọi cleanup handle do bạn cung cấp**. Chỉ khi logic cleanup thực sự gọi `close()`, giải phóng lock/lease hoặc cập nhật trạng thái thì tài nguyên mới được dọn dẹp.

Nó cũng không bảo đảm cleanup khi JVM bị kết thúc cưỡng bức, mất điện, `Runtime.halt`, process crash, hoặc tác vụ được trả về dạng `CompletableFuture` rồi chạy bất đồng bộ sau khi target đã trả về. `tryFinally` bọc **lời gọi đồng bộ đến handle**, không tự theo dõi vòng đời tác vụ async.

## 5. Thực hành Java 17+: xử lý lỗi rồi dọn dẹp

Bài thực hành tạo một target có hai tham số và ba trường hợp:

- `"good"`: target trả kết quả bình thường.
- `"bad"`: target ném `IllegalArgumentException`, được handler chuyển thành fallback.
- `"fatal"`: target ném `IllegalStateException`, không thuộc loại đang catch nên sẽ tiếp tục truyền ra sau khi cleanup chạy.

Ta cũng đổi **thứ tự bọc** để thấy cleanup quan sát lỗi ở điểm nào.

**Tệp Java chạy độc lập:** `HandleErrorCleanupDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HandleErrorCleanupDemo {
    public static String work(String key, int attempt) {
        System.out.println("work:" + key + ":" + attempt);
        if ("bad".equals(key)) {
            throw new IllegalArgumentException("bad-input");
        }
        if ("fatal".equals(key)) {
            throw new IllegalStateException("server-down");
        }
        return "ok:" + key;
    }

    public static String recover(IllegalArgumentException error, String key) {
        System.out.println("recover:" + key + ":" + error.getMessage());
        return "fallback:" + key;
    }

    public static String cleanup(Throwable failure, String result,
                                 String key, int attempt) {
        String state = failure == null
                ? "success"
                : failure.getClass().getSimpleName();
        System.out.println("cleanup:" + key + ":" + state + ":" + result);
        return result == null ? null : result + "|closed";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(
                HandleErrorCleanupDemo.class, "work",
                MethodType.methodType(String.class, String.class, int.class));
        MethodHandle handler = lookup.findStatic(
                HandleErrorCleanupDemo.class, "recover",
                MethodType.methodType(
                        String.class, IllegalArgumentException.class, String.class));
        MethodHandle cleaner = lookup.findStatic(
                HandleErrorCleanupDemo.class, "cleanup",
                MethodType.methodType(
                        String.class, Throwable.class, String.class,
                        String.class, int.class));

        MethodHandle recoverFirst = MethodHandles.tryFinally(
                MethodHandles.catchException(
                        target, IllegalArgumentException.class, handler),
                cleaner);
        MethodHandle cleanupFirst = MethodHandles.catchException(
                MethodHandles.tryFinally(target, cleaner),
                IllegalArgumentException.class, handler);

        System.out.println("type=" + recoverFirst.type());
        System.out.println("normal=" + (String) recoverFirst.invokeExact("good", 1));
        System.out.println("handled=" + (String) recoverFirst.invokeExact("bad", 2));
        try {
            String unused = (String) recoverFirst.invokeExact("fatal", 3);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException error) {
            System.out.println("propagate=" + error.getMessage());
        }
        System.out.println("alternate=" + (String) cleanupFirst.invokeExact("bad", 4));
    }
}
~~~

**Biên dịch và chạy bằng JDK 17+:**

~~~bash
javac --release 17 -d out HandleErrorCleanupDemo.java
java -cp out HandleErrorCleanupDemo
~~~

`javac -d out` tạo output directory nếu cần. **Stdout đã kiểm chứng với đúng source trên:**

~~~text
type=(String,int)String
work:good:1
cleanup:good:success:ok:good
normal=ok:good|closed
work:bad:2
recover:bad:bad-input
cleanup:bad:success:fallback:bad
handled=fallback:bad|closed
work:fatal:3
cleanup:fatal:IllegalStateException:null
propagate=server-down
work:bad:4
cleanup:bad:IllegalArgumentException:null
recover:bad:bad-input
alternate=fallback:bad
~~~

### 5.1. Đọc chính xác kết quả

**Lần 1 — bình thường:**

~~~text
work:good:1
cleanup:good:success:ok:good
normal=ok:good|closed
~~~

Target trả `"ok:good"`, cleanup nhận `failure == null` và `result == "ok:good"`, rồi trả `"ok:good|closed"`. Giá trị sau cleanup trở thành kết quả cuối cùng.

**Lần 2 — đã phục hồi trước cleanup:**

~~~text
work:bad:2
recover:bad:bad-input
cleanup:bad:success:fallback:bad
handled=fallback:bad|closed
~~~

`catchException` ở bên **trong** đã biến `IllegalArgumentException` thành `"fallback:bad"`. Do vậy `tryFinally` ở ngoài nhìn thấy **target của chính nó hoàn thành bình thường** và truyền `failure == null` cho cleanup. Không có gì mâu thuẫn: exception đã được handler tiêu thụ trước đó.

**Lần 3 — exception không được catch:**

~~~text
work:fatal:3
cleanup:fatal:IllegalStateException:null
propagate=server-down
~~~

Handler chỉ áp dụng cho `IllegalArgumentException`, nên `IllegalStateException` vẫn đi ra. `tryFinally` chạy cleanup với exception tương ứng và `result == null` (mặc định cho `String`); dù cleanup trả về `null` hay một String khác, exception gốc vẫn được ném lại nếu cleanup không ném lỗi mới.

**Lần 4 — cleanup trước, handler sau:**

~~~text
work:bad:4
cleanup:bad:IllegalArgumentException:null
recover:bad:bad-input
alternate=fallback:bad
~~~

Ở pipeline này, `tryFinally` ở **bên trong** nhìn thấy `IllegalArgumentException` và chạy cleanup trước; chỉ sau đó `catchException` bên ngoài nhận lỗi và tạo fallback. Vì cleanup không nhận giá trị fallback, kết quả cuối **không thêm `|closed`** trong ví dụ. Đây là khác biệt thứ tự, không phải nondeterminism.

## 6. Thứ tự ghép combinator có ý nghĩa nghiệp vụ

### 6.1. Hai pipeline khác nhau

**Pipeline A — Recovery rồi cleanup**

~~~java
MethodHandle pipelineA = MethodHandles.tryFinally(
        MethodHandles.catchException(target, IllegalArgumentException.class, handler),
        cleaner);
~~~

Sơ đồ:

~~~text
CALL -> target
          | success -> result ---------------------+
          | IllegalArgumentException -> handler --+
          | other exception ----------------------+
                                                   |
                                               cleanup
                                                   |
                                               RETURN/THROW
~~~

Nếu handler **trả bình thường**, cleanup nhận `failure == null` và **kết quả đã phục hồi**. Nếu handler lại ném exception khác, cleanup quan sát exception mới. Với hệ thống cần “mọi kết quả kể cả fallback đều đi qua bước hậu xử lý”, pipeline A thường dễ hiểu.

**Pipeline B — Cleanup rồi Recovery**

~~~java
MethodHandle pipelineB = MethodHandles.catchException(
        MethodHandles.tryFinally(target, cleaner),
        IllegalArgumentException.class,
        handler);
~~~

Sơ đồ:

~~~text
CALL -> target -> cleanup -> success result
                       |
                       +-- exception -> catchException -> handler -> fallback
                       |
                       +-- unhandled exception -> propagate
~~~

Cleanup nhận đúng exception **chưa bị recovery**, hữu ích khi cần log lỗi gốc hoặc ghi chỉ số thất bại ngay ở ranh giới target. Tuy nhiên cleanup của pipeline B **không chạy sau handler**. Nếu handler cần giải phóng một resource khác, phải có chính sách khác phù hợp.

**So sánh:**

| Câu hỏi | Pipeline A: `tryFinally(catchException(...), cleaner)` | Pipeline B: `catchException(tryFinally(...), ..., handler)` |
| --- | --- | --- |
| Cleanup có chạy sau target thành công? | Có | Có |
| Handler có chạy khi gặp loại lỗi đã chọn? | Có | Có, sau cleanup |
| Cleanup nhìn thấy lỗi gốc đã được handler chuyển thành fallback? | Không, nếu handler trả bình thường | Có, vì cleanup chạy trước handler |
| Cleanup có thể biến đổi fallback của handler? | Có | Không, vì handler chạy sau cleanup |
| Exception từ handler đi qua cùng cleanup? | Có | Không; adapter `tryFinally` đã hoàn tất trước handler |
| Exception từ cleanup có thể bị outer handler bắt? | Không có outer catch trong biểu thức này | Có, **nếu** loại exception cleanup ném khớp `exType` |

Chọn pipeline dựa trên **ý nghĩa** của cleanup: nó là một bước “hậu xử lý kết quả cuối” hay là một bước “dọn trạng thái ngay sau target”? Trong mã thật, đôi khi cần cả hai — nhưng không nên bọc lồng combinator khi thiết kế một khối Java `try/catch/finally` bình thường dễ đọc hơn.

### 6.2. Handler và cleanup nhận **prefix** nào?

Ví dụ target `(String key, int attempt)String`:

- Handler `(IllegalArgumentException, String)String`: nhận exception + `key`, bỏ `attempt`.
- Cleanup `(Throwable, String result, String key, int attempt)String`: nhận exception + result + **cả hai** đối số target.
- Nếu cleanup chỉ cần result, có thể dùng `(Throwable, String)String` mà không cần biết `key`/`attempt`.
- Nếu cleanup cần `attempt` nhưng không cần `key`, không thể tự bỏ `key` rồi nhận `attempt` làm tham số kế tiếp. Dùng thêm adapter sắp xếp/ghép đối số (`dropArguments`, `permuteArguments`, `filterArguments`... tùy yêu cầu) hoặc đổi thiết kế để chữ ký phù hợp.

**Không được lấy các đối số bị bỏ của handler/cleanup để suy ra dữ liệu đã biến đổi bên trong target:** combinator truyền **các đối số gốc**, không chụp toàn bộ local variables của target.

## 7. Hai trường hợp cạnh cần biết: cleanup ném lỗi và target trả `void`

Ví dụ độc lập sau kiểm chứng cả hai tình huống. Chạy cùng thư mục dự án với file `CleanupEdgeDemo.java`.

~~~java
import java.lang.invoke.*;

public class CleanupEdgeDemo {
    public static String failing() {
        throw new IllegalArgumentException("primary");
    }

    public static String failingCleanup(Throwable cause, String result) {
        throw new IllegalStateException("secondary");
    }

    public static void perform(String value) {
        System.out.println("perform:" + value);
    }

    public static void performCleanup(Throwable cause, String value) {
        System.out.println("performCleanup:"
                + (cause == null ? "ok" : "error") + ":" + value);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup l = MethodHandles.lookup();
        MethodHandle f = l.findStatic(
                CleanupEdgeDemo.class, "failing",
                MethodType.methodType(String.class));
        MethodHandle c = l.findStatic(
                CleanupEdgeDemo.class, "failingCleanup",
                MethodType.methodType(String.class, Throwable.class, String.class));
        MethodHandle wrapped = MethodHandles.tryFinally(f, c);

        try {
            String ignored = (String) wrapped.invokeExact();
        } catch (IllegalStateException e) {
            System.out.println("observed=" + e.getMessage()
                    + ",suppressed=" + e.getSuppressed().length);
        }

        MethodHandle a = l.findStatic(
                CleanupEdgeDemo.class, "perform",
                MethodType.methodType(void.class, String.class));
        MethodHandle b = l.findStatic(
                CleanupEdgeDemo.class, "performCleanup",
                MethodType.methodType(void.class, Throwable.class, String.class));
        MethodHandles.tryFinally(a, b).invokeExact("job");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -d out CleanupEdgeDemo.java
java -cp out CleanupEdgeDemo
~~~

Stdout đã kiểm chứng:

~~~text
observed=secondary,suppressed=0
perform:job
performCleanup:ok:job
~~~

Ý nghĩa:

- `failing()` ném `IllegalArgumentException("primary")`, nhưng cleanup lại ném `IllegalStateException("secondary")`. Exception nhìn thấy ở ngoài là **lỗi cleanup**, và trong ví dụ không có suppressed exception được tự thêm (`suppressed=0`).
- `perform` trả `void`, nên cleanup đúng chữ ký **`void(Throwable, String)`**, không có tham số result. `tryFinally` vẫn chạy cleanup sau `perform("job")`.
- Không dùng `tryFinally` như một thay thế mặc định cho `try-with-resources`: `try-with-resources` có chính sách xử lý suppressed exception riêng khi tự đóng resource.

## 8. Những lỗi thiết kế và cách chẩn đoán

| Vấn đề | Lý do thường gặp | Cách khắc phục |
| --- | --- | --- |
| Ghép `catchException` báo `IllegalArgumentException` | Handler trả kiểu khác target hoặc tham số sau exception không trùng prefix target | In `target.type()` và `handler.type()`; kiểm tra chính xác return và thứ tự đối số |
| Ghép `tryFinally` báo `IllegalArgumentException` | Cleanup thiếu `Throwable`/result, dùng sai kiểu trả về, hoặc truyền đối số target sai prefix | In `cleaner.type()`; đối chiếu quy tắc non-void/void |
| Handler không được gọi | Target không ném exception hoặc lỗi không thuộc `exType` | Kiểm tra class thực của exception và vị trí bọc; đừng bắt tràn lan chỉ để “cho chạy” |
| Cleanup nhận `failure == null` dù có lỗi trong target gốc | Handler phía trong đã recovery thành kết quả bình thường | Kiểm tra thứ tự `tryFinally(catchException(...), cleanup)` |
| Cleanup nhận `result == null` dù target có return type String | Target ném exception; `null` là placeholder cho String | Kiểm tra `failure` trước khi dùng `result`; tránh dereference placeholder |
| Lỗi gốc biến mất khi cleanup ném lỗi mới | Exception của finally đã thay exception ban đầu | Thiết kế chính sách logging/propagation, đừng để close error che lỗi chính ngoài ý muốn |
| `WrongMethodTypeException` khi `invokeExact` | Kiểu tĩnh của lời gọi không khớp adapter.type() | Cast return và truyền argument đúng type, hoặc thích nghi handle bằng `asType` có chủ đích |
| `NullPointerException` trong cleanup | Dùng `failure.getMessage()` khi failure null hoặc `result.length()` khi result null | Phân nhánh theo failure/result; null có ngữ nghĩa đặc biệt |
| Cleanup không chạy sau tác vụ async | Handle chỉ trả một `Future`/`CompletionStage`, không chờ công việc kết thúc | Gắn cleanup vào lifecycle async ở tầng phù hợp |
| `ClassCastException` trong cleanup | Kiểu tham số Throwable quá hẹp so với lỗi thực tế | Ưu tiên khai báo `Throwable` làm tham số đầu |
| Thấy tài nguyên vẫn mở | Cleanup chỉ log, không thực sự gọi close/release | Kiểm tra logic cleanup, đo resource lifecycle trong test |

### 8.1. Mẫu điều tra từng bước

1. In `target.type()`, `handler.type()` và `cleanup.type()` **trước khi ghép**.
2. Đảm bảo handler nhận exception và **prefix đối số**, có cùng return type với target.
3. Đảm bảo cleanup nhận `Throwable`, result nếu target không phải `void`, rồi optional prefix, có return type đúng.
4. Ghi rõ thứ tự combinator: recovery trước hay cleanup trước; mô hình hóa ba đường **thành công / lỗi được catch / lỗi không được catch**.
5. Kiểm tra exception từ **target**, từ **handler** và từ **cleanup** riêng biệt; lỗi dọn dẹp có thể thay lỗi chính.
6. In `adapter.type()` sau khi ghép; kiểm tra cast trong lời gọi `invokeExact`. Khi cần chuyển đổi type hợp lệ, dùng `asType` một cách tường minh.
7. Kiểm thử tài nguyên được release **đúng một lần** ở mỗi đường chạy; bao gồm failure trong cleanup. `tryFinally` chỉ bảo đảm cơ chế gọi, không xác nhận `close()` thành công.

### 8.2. An toàn và trách nhiệm vận hành

- **Không swallow mọi lỗi** bằng một fallback chung khi mất kết nối, dữ liệu sai, hoặc hỏng trạng thái nội bộ. Chỉ recover lỗi đã có chính sách hợp lệ.
- **Không catch `Throwable` đại trà** chỉ để hệ thống không báo lỗi. Một số `Error` phản ánh tình trạng không thể tiếp tục bình thường; handler cần biết phạm vi của mình.
- **Cleanup nên đơn giản, có tính dự đoán và idempotent khi có thể**. Nếu cleanup ném exception mới, hãy xác định quy tắc ưu tiên và cách ghi nhận lỗi ban đầu.
- **Không dùng cleanup để tin tưởng dữ liệu chưa được xác thực**. Những đối số truyền vào cleanup đến từ caller; chính sách phân quyền, validate input và isolation vẫn nằm ở tầng thích hợp.
- **Hiểu checked exception:** lời gọi `MethodHandle.invokeExact`/`invoke` khai báo `throws Throwable`; compiler không suy ra tập exception thực của target chỉ từ handle.type(). Ví dụ chọn `main throws Throwable` vì mục tiêu giảng dạy.
- **Không mặc định ưu việt hơn Java thường:** khi có resource theo block lexical, một khối `try-with-resources` trực tiếp dễ đọc và có suppressed-exception semantics rõ ràng. Combinator hữu ích nhất khi **pipeline gọi động** cần ghép chính sách mà không thể sửa target method.

## 9. Bài tập thực hành

1. **Rút gọn handler:** Đổi `recover` sang chữ ký `String recover(IllegalArgumentException error)`. Sửa `MethodType` khi `findStatic`. Dự đoán output nào khác, output nào không đổi.
2. **Rút gọn cleanup:** Đổi `cleanup` thành `String cleanup(Throwable failure, String result)`. Bỏ các log dùng `key`/`attempt` và cập nhật `MethodType`. Chứng minh `recoverFirst.type()` vẫn giữ `(String,int)String`.
3. **Bắt đúng loại:** Cho target ném `IllegalArgumentException` rồi thay exType thành `RuntimeException.class`; cập nhật handler nhận `RuntimeException` hoặc supertype. Quan sát fallback. Nếu giữ nguyên handler kiểu `IllegalArgumentException`, giải thích vì sao ghép có thể thất bại.
4. **Thay đổi thứ tự:** Chạy hai pipeline A/B với `"bad"`, lập bảng `work`/`recover`/`cleanup` theo đúng thứ tự. Vì sao chỉ pipeline A trả `fallback:bad|closed`?
5. **Lỗi khi dọn dẹp:** Sửa cleanup thành luôn ném `IllegalStateException("close-failed")`. Khi target cũng ném `IllegalArgumentException`, exception nào đến caller? Làm sao thiết kế việc bảo tồn root cause mà không làm mất cảnh báo cleanup thất bại?
6. **Kiểu `void`:** Thay `perform` ở `CleanupEdgeDemo` thành một method ném `IllegalStateException` với một giá trị đầu vào cụ thể. Bổ sung log trong `performCleanup` để thấy `failure` khác null; xác định có result parameter hay không.
7. **Pipeline nghiệp vụ:** Một plugin xử lý document có thể ném lỗi dữ liệu có thể recover hoặc lỗi lưu trữ không thể recover. Đề xuất exType cụ thể, handler phù hợp và cleanup giải phóng lease. Mô tả khác biệt giữa cleanup cần thấy lỗi gốc và cleanup cần thấy dữ liệu fallback.

## 10. Ghi nhớ

- `catchException(target, exType, handler)` tạo adapter cùng `MethodType` với target, chỉ gọi handler khi **target ném exception thuộc exType**, và có thể biến exception đó thành giá trị fallback.
- Handler nhận **exception trước, rồi optional prefix của đối số target**; phải trả đúng return type của target.
- `tryFinally(target, cleanup)` cũng giữ `MethodType` của target; cleanup chạy sau target khi **thành công lẫn lỗi**.
- Cleanup nhận **`Throwable`**, sau đó **result nếu target không trả `void`**, sau đó optional prefix đối số; trả cùng kiểu với target. Khi target ném, result là giá trị mặc định.
- `tryFinally` **không đổi ngoại lệ thành kết quả bình thường**; nếu cleanup ném lỗi mới, lỗi đó có thể thay lỗi ban đầu.
- **Thứ tự bọc quan trọng:** `tryFinally(catchException(...), cleaner)` cho cleanup nhìn thấy kết quả fallback; `catchException(tryFinally(...), ..., handler)` cho cleanup nhìn thấy lỗi trước khi recover.
- Đừng nhầm “cleanup được gọi” với “resource đã được đóng thành công”. Tài nguyên, bất đồng bộ và chính sách ngoại lệ vẫn phải được kiểm thử riêng.

## Tài liệu tham khảo chính thức

- [Java SE 17 — `MethodHandles.catchException` và `MethodHandles.tryFinally`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#catchException(java.lang.invoke.MethodHandle,java.lang.Class,java.lang.invoke.MethodHandle))
- [Java SE 17 — `MethodHandles.tryFinally`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#tryFinally(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle))
- [Java SE 17 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java Language Specification — `try / catch / finally`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20)
