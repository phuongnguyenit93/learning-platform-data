# Dọn dữ liệu ngữ cảnh để tránh rò rỉ giữa các yêu cầu trong AOP

> **Mục tiêu:** Hiểu cách advice quản lý ngữ cảnh theo yêu cầu (request context), vì sao **ThreadLocal không tự là request scope**, cách dữ liệu của request A có thể xuất hiện trong request B khi thread được tái sử dụng, và cách mở/đóng scope an toàn. Phân biệt **xóa ở root boundary** với **khôi phục ngữ cảnh cha ở nested boundary**; phân tích ngoại lệ, retry, cancellation, callback bất đồng bộ, class loader, bộ nhớ và dữ liệu nhạy cảm. Hai ví dụ Java 17 có thể biên dịch/chạy độc lập với stdout xác định. Phạm vi là Aspect-Oriented Programming (AOP) cơ bản và nâng cao nói chung; những hành vi phụ thuộc công cụ được nêu có điều kiện.

## 1. Tình huống điển hình: dữ liệu của A theo sang B

Một server có thread pool và ghi requestId vào context cho log:

~~~text
Worker thread T1
  Request A:
    set(requestId = "REQ-A")
    execute A
    exception xảy ra
    quên xóa context

  Request B:
    code đọc context từ T1
    nhận "REQ-A" thay vì ngữ cảnh của B
~~~

Hậu quả không chỉ là log sai. Dữ liệu tenant, actor, correlation ID hoặc một object lớn gắn A có thể bị giữ lại hoặc được sử dụng nhầm ở B. Nếu context còn được dùng để quyết định policy bảo mật, lỗi có thể trở nên nghiêm trọng.

**Quy tắc chính:** một scope đã cài ngữ cảnh phải có **đường đóng scope** đúng, ngay cả khi hoạt động thất bại. Việc request đã xử lý xong **không đồng nghĩa** ThreadLocal entry đã được xóa.

## 2. Hợp đồng cleanup: dữ liệu nào phải biến mất sau scope?

Bài về trạng thái theo luồng đã giải thích cơ chế `ThreadLocal` và việc thread pool tái sử dụng worker. Ở đây hãy chuyển kiến thức đó thành **hợp đồng có thể kiểm thử**: sau khi một scope do advice mở kết thúc, worker phải thấy lại **đúng trạng thái trước khi mở scope**, kể cả khi nghiệp vụ ném ngoại lệ.

Một scope quản lý context cần xác định đủ năm yếu tố:

| Yếu tố | Câu hỏi khi review |
| --- | --- |
| **Owner** | Advice nào thực hiện enter và chịu trách nhiệm close? |
| **Boundary** | Bắt đầu và kết thúc tại method call, execution, task hay async completion? |
| **Value** | Những trường context nào được phép cài, có giữ object lớn hay secret không? |
| **Exit paths** | Return, target throw, advice throw, timeout, cancel và nested call được xử lý ra sao? |
| **Postcondition** | Sau close, binding là `previous` hoặc **không còn binding**, đúng như trước enter |

Ví dụ nếu trước scope hiện tại chưa có trace ID, postcondition là không còn trace ID của request vừa xử lý. Nếu trước đó có một trace ID cha, postcondition là **khôi phục ID cha**, không được xóa cha và cũng không được giữ ID con.

## 3. Lựa chọn đúng ranh giới kết thúc

Một advice around một method không tự động sở hữu toàn bộ vòng đời logical request. Phạm vi có thể là:

- **Method invocation:** enter trước khi chuyển tiếp method, exit khi method return/throw.
- **Task execution:** enter trên thread thực thi task và exit khi callable/runnable kết thúc.
- **Async logical operation:** có thể kéo dài qua nhiều thread/stage; context snapshot sống đến một completion có quy tắc.
- **Nested operation:** scope trong hoạt động tạm thời, sau đó phục hồi scope ngoài.

Nếu method trả `CompletionStage` đang pending, `finally` của method sẽ chạy khi **method trả stage**, không đợi công việc nền hoàn tất. Nếu tài nguyên cần còn tồn tại cho task nền, advice phải bàn giao ownership hoặc gắn lifecycle đúng task; không giữ binding của thread gọi đến khi task khác hoàn thành.

Điều cần ghi vào thiết kế không phải tên API advice, mà là **điểm bắt đầu, điểm đóng, chủ thể đóng và điều kiện task thực sự hoàn thành**.

## 4. Ma trận cleanup theo đường đi

| Tình huống | Rủi ro cụ thể | Postcondition cần chứng minh |
| --- | --- | --- |
| Method trả bình thường | Scope con vẫn hiện diện trong worker | Binding cũ được phục hồi |
| Target ném ngoại lệ | Dòng cleanup sau `proceed` bị bỏ qua | Close chạy từ `finally`, exception gốc giữ đúng |
| Before/setup ném lỗi | Một phần context đã cài, nhưng chưa vào vùng `try` | Mọi phần đã cài thành công đều được dọn |
| Scope con đóng | `remove` vô điều kiện xóa cha | Context cha được phục hồi |
| Advice ghi log khi close thất bại | Lỗi phụ che nguyên nhân gốc | Có chính sách lỗi và đường ghi lỗi riêng |
| Task bị cancel trước khi chạy | Không có scope nào được worker mở | Không có cleanup giả trên một thread không sở hữu scope |
| Task đã bắt đầu rồi bị interrupt | Thoát có thể bị trì hoãn hoặc không xảy ra ngay | Cleanup theo thực tế đường unwind, có deadline giám sát |
| Worker được tái sử dụng | Request B đọc context A | Test task B trên đúng worker sau A |

Khác với lỗi data race giữa hai thread cùng ghi một biến chung, **stale context** là lỗi theo thời gian trên *cùng một worker*: request trước kết thúc nhưng binding vẫn còn. Bài kiểm thử phải phản ánh chính cơ chế đó.

## 5. Phân biệt xóa binding với đặt giá trị rỗng

`ThreadLocal.get()`, `set(...)` và `remove()` làm việc trên binding của **thread hiện tại**. Hai thao tác sau không nên được coi là giống hệt nhau:

```java
// Mảnh minh họa; biến LOCAL được giả định đã khai báo.
LOCAL.set(null); // Vẫn có phép gán giá trị null vào ThreadLocal.
LOCAL.remove();  // Gỡ binding hiện tại.
```

Với `ThreadLocal.withInitial(supplier)`, sau `remove()`, một lần `get()` có thể gọi lại supplier để tạo giá trị ban đầu; do đó phép kiểm tra `get()==null` chỉ là đủ cho trường hợp dùng `new ThreadLocal<>()` với giá trị ban đầu mặc định null. Nếu **null** tự nó là giá trị nghiệp vụ hợp lệ và cần phân biệt “không có binding”, phải thiết kế một representation riêng hoặc scope abstraction có lưu trạng thái tồn tại trước đó.

Đừng cố làm cleanup từ thread gọi chỉ vì task đã hoàn tất: `remove()` trên main thread không dọn được binding của executor worker. Cần đóng scope **trên đúng thread đã cài binding**.

## 6. Đặt cleanup gần thao tác cài context nhất

Một thiết kế dễ chứng minh hơn tách rời `before=set` rồi `afterReturning=remove` là tạo một **scope có owner rõ ràng**. Mẫu đồng bộ:

```java
// Mã minh họa, không phải chương trình độc lập.
Context previous = CURRENT.get();
CURRENT.set(context);
try {
    return proceed();
} finally {
    if (previous == null) CURRENT.remove();
    else CURRENT.set(previous);
}
```

Mẫu trên đúng khi `null` biểu diễn “không có context trước đó”; nếu dùng `ThreadLocal` có initializer hoặc `null` là một trạng thái quan trọng, scope manager phải lưu đầy đủ trạng thái cần phục hồi. Điều quan trọng là **mỗi lần cài có một nơi sở hữu việc phục hồi** và không có nhánh return/exception nào lách qua cleanup.

Nếu việc chuẩn bị bao gồm nhiều bước có thể lỗi, không đặt tất cả setup trước vùng bảo vệ rồi hy vọng cuối cùng sẽ cleanup. Mỗi resource/binding đã mở phải được bảo vệ từ lúc nó được thiết lập thành công.

## 7. Root scope khác nested scope ở postcondition

`Root scope` được tạo khi chưa có context. Kết thúc root cần bỏ binding do root tạo.

`Nested scope` thay tạm context A bằng B. Khi B thoát, **A phải vẫn đang hiện diện**:

```text
trước root: none
  root enter: A
    child enter: B
    child close: A
  root close: none
```

Một scope manager có thể lưu previous, kiểm soát thứ tự đóng LIFO và ngăn double-close hoặc close từ thread khác. Không đủ chỉ gọi `remove()` mỗi lần vì child sẽ xóa luôn context của parent; nhưng cũng không được để child giữ binding B khi parent đã tiếp tục.

Với các lời gọi AOP lồng nhau, test cả trình tự **A → B → A → none**, không chỉ “B thấy B” khi đang chạy.

## 8. Phân quyền sở hữu: ai cài, ai chỉ đọc?

Nếu Trace, Audit và Metrics cùng sử dụng một context, nên định nghĩa một **owner** mở/đóng scope và các consumer chỉ đọc. Nếu mỗi consumer tự `remove()` khi xong việc của mình, một consumer có thể xóa context trong lúc phần khác vẫn cần.

```text
ContextOwner.enter(A)
    Trace.read(A)
    Audit.read(A)
    Metrics.read(A)
ContextOwner.close()  -> previous
```

Một consumer muốn thêm thông tin tạm (ví dụ child span) có thể tạo scope con của chính nó, nhưng phải phục hồi đúng trước khi trả điều khiển về owner ngoài. Không dùng một cờ static hoặc shared instance để biết “context hiện tại”, vì dữ liệu thuộc từng invocation và có thể chạy đồng thời.

## 9. Chốt tiêu chí review trước ví dụ runnable

Các ví dụ tiếp theo kiểm chứng hai tính chất khác nhau:

1. **Phát hiện bug:** task A ném lỗi, để lại `ThreadLocal`; task B trên cùng worker đọc nhầm A. Việc sau cùng gọi cleanup chứng minh lý do lỗi có thể ẩn khi chỉ thử trên thread mới.
2. **Ngăn bug:** scope có enter/close, lưu previous và đóng trong `finally`; nested scope và worker propagation dùng snapshot đúng chủ sở hữu.

Sau khi chạy ví dụ, chỉ coi cleanup đạt yêu cầu khi xác minh được **trạng thái sau scope và task tiếp theo**, ngoài việc lời gọi nghiệp vụ trả kết quả. Điều này phân biệt bài về **cleanup contract và leak prevention** với bài trước về khái niệm `ThreadLocal`/thread pools.

## 10. Ví dụ Java 17 số 1 — chứng minh ThreadLocal leak

Chương trình cố ý để task A quên cleanup rồi ném exception. Task B chạy trên **cùng worker thread** và đọc A. Sau đó B xóa; C mở scope có try/finally; D xác nhận dữ liệu đã sạch.

Đây là Java thuần để mô phỏng lỗi trong advice/interceptor, **không phải mã của một bộ dệt AOP**.

Lưu file **ThreadLocalLeakDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadLocalLeakDemo {
    private static final ThreadLocal<String> REQUEST =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            var failed = executor.submit(() -> {
                REQUEST.set("REQ-A");
                System.out.println("[A] context=" + REQUEST.get());
                // Cố tình thiếu finally/remove để chứng minh bug.
                throw new IllegalStateException("A failed");
            });

            try {
                failed.get();
            } catch (ExecutionException error) {
                System.out.println("[main] A failed: "
                        + error.getCause().getMessage());
            }

            executor.submit(() -> {
                System.out.println("[B] stale=" + REQUEST.get());
                REQUEST.remove();
                System.out.println("[B] cleaned=" + REQUEST.get());
            }).get();

            executor.submit(() -> {
                REQUEST.set("REQ-C");
                try {
                    System.out.println("[C] active=" + REQUEST.get());
                } finally {
                    REQUEST.remove();
                    System.out.println("[C] cleaned=" + REQUEST.get());
                }
            }).get();

            executor.submit(() -> {
                System.out.println("[D] context=" + REQUEST.get());
            }).get();
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy với JDK 17:

~~~bash
javac ThreadLocalLeakDemo.java
java ThreadLocalLeakDemo
~~~

**Stdout:**

~~~text
[A] context=REQ-A
[main] A failed: A failed
[B] stale=REQ-A
[B] cleaned=null
[C] active=REQ-C
[C] cleaned=null
[D] context=null
~~~

### 10.1. Tại sao B nhận được A?

Single-thread executor sử dụng một worker cho các task tuần tự. A để lại REQUEST trong worker, dù Future của A thất bại. B đọc từ worker ấy nên thấy stale value.

Một thread pool lớn hơn có thể khiến lỗi **không tái hiện ổn định** vì task B rơi vào worker khác; nó không làm thiết kế thiếu cleanup trở nên an toàn.

### 10.2. Main không thể dọn hộ worker

failed.get chạy trên main thread, còn REQUEST.set chạy trên worker thread. Nếu main gọi REQUEST.remove, nó dọn entry của main chứ **không xóa entry trên worker**.

Mỗi thread-local binding phải được dọn trong thread sở hữu nó, hoặc hệ thống phải dùng một mô hình khác với lifecycle tường minh.

### 10.3. Vì sao D sạch?

B gọi remove trên worker, C mở và đóng trong cùng worker bằng finally, D kiểm tra get là null. **Test âm sau khi scope đóng** quan trọng ngang test dương khi scope đang hoạt động.

## 11. Vì sao before/after-returning không luôn đủ

Một thiết kế:

~~~text
before advice: set context
after-returning advice: remove context
~~~

có thể dọn được normal return nhưng bỏ sót exceptional exit nếu advice thứ hai chỉ chạy khi không có lỗi.

An toàn hơn là quanh advice sở hữu đồng thời enter và exit, hoặc một cơ chế after/finally có semantics được công cụ bảo đảm. Không tự ghép một before trên join point này với một after trên điểm khác nếu lifecycle của hai điểm không khớp tuyệt đối.

Khi nhiều aspect phối hợp, precedence còn ảnh hưởng thứ tự enter/close. Context owner cần bao phủ các consumer mà nó phục vụ.

## 12. Scope object trong Java

Một API scope có thể cho phép:

~~~text
scope = enter(newContext)
try:
    execute action
finally:
    scope.close()
~~~

Với Java, **AutoCloseable** và try-with-resources giúp đóng scope trên normal/exceptional exit.

Scope cần nhớ:

- **previous:** binding trước khi vào.
- **installed:** binding vừa đặt.
- **owner thread:** thread đã mở.
- **closed:** ngăn close lặp.
- **LIFO:** tránh đóng outer trước inner.

Một scope không nên được chuyền qua thread khác để close. ThreadLocal.remove của thread khác không xử lý entry của owner và còn có thể ảnh hưởng context riêng của thread đang close.

## 13. Ví dụ Java 17 số 2 — scope lồng nhau và async propagation

Ví dụ dùng record bất biến làm Context, Scope có ownership và restore, cùng một worker từ executor.

**Đây là Java thuần minh họa request-context lifecycle; không có weaving tự động.**

Lưu **ContextScopeDemo.java**:

~~~java
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContextScopeDemo {
    record Context(String requestId, String actor) {}

    private static final ThreadLocal<Context> CURRENT =
            new ThreadLocal<>();

    static String label() {
        Context c = CURRENT.get();
        return c == null ? "none" : c.requestId() + "/" + c.actor();
    }

    static Scope enter(Context value) {
        return new Scope(value);
    }

    static final class Scope implements AutoCloseable {
        private final Thread owner;
        private final Context previous;
        private final Context installed;
        private boolean closed;

        Scope(Context value) {
            owner = Thread.currentThread();
            previous = CURRENT.get();
            installed = Objects.requireNonNull(value);
            CURRENT.set(installed);
        }

        @Override
        public void close() {
            if (Thread.currentThread() != owner) {
                throw new IllegalStateException("wrong thread");
            }
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            if (CURRENT.get() != installed) {
                throw new IllegalStateException("close out of order");
            }
            closed = true;
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            System.out.println("[main] before=" + label());
            try (Scope outer = enter(new Context("R-1", "alice"))) {
                System.out.println("[outer] context=" + label());

                try (Scope inner = enter(
                        new Context("R-1-child", "service"))) {
                    System.out.println("[inner] context=" + label());
                }
                System.out.println("[outer] restored=" + label());

                Context snapshot = CURRENT.get();
                Future<?> task = executor.submit(() -> {
                    System.out.println("[worker] before=" + label());
                    try (Scope workerScope = enter(snapshot)) {
                        System.out.println("[worker] inside=" + label());
                    }
                    System.out.println("[worker] after=" + label());
                });
                task.get();
            }
            System.out.println("[main] after=" + label());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ContextScopeDemo.java
java ContextScopeDemo
~~~

**Stdout:**

~~~text
[main] before=none
[outer] context=R-1/alice
[inner] context=R-1-child/service
[outer] restored=R-1/alice
[worker] before=none
[worker] inside=R-1/alice
[worker] after=none
[main] after=none
~~~

### 13.1. Inner phải restore outer

Khi outer enter, previous là null. Khi inner enter, previous là Context R-1/alice. Khi inner close, nó set lại previous. Sau khi outer close, vì previous của outer là null nên remove.

Nếu inner luôn remove, outer mất binding dù scope của outer chưa kết thúc.

### 13.2. Worker không tự nhận ThreadLocal từ main

Context từ main được chụp dưới dạng record bất biến rồi **truyền tường minh vào lambda**. Worker tự enter và close theo thread của worker. Điều đó không có nghĩa có một ThreadLocal value được chia sẻ giữa hai thread.

Snapshot trong ví dụ có cả actor để minh họa. Trong sản phẩm, nên truyền **tối thiểu những trường được phép và cần thiết**, không mặc định truyền danh tính người dùng tới mọi tác vụ nền.

### 13.3. Vì sao kiểm tra thread owner và thứ tự close?

Nếu close trên thread khác, ThreadLocal.remove tác động tới thread đó thay vì owner. Kiểm tra owner giúp phát hiện bug.

Nếu outer close trước inner, state bị phục hồi sai; kiểm tra installed identity phát hiện sai thứ tự trong các trường hợp này. Dù cơ chế scope phát hiện lỗi, code thực tế vẫn phải bảo đảm **mở và đóng đúng thứ tự** để giữ tính đúng đắn.

## 14. Propagation bất đồng bộ không tự xảy ra

Một logical request có thể đi qua:

~~~text
Thread T1: bắt đầu request
    install context A
    submit task
    close context A trên T1

Thread T2: chạy task
    install snapshot phù hợp
    do work
    close snapshot trên T2

Thread T3: chạy completion callback
    install approved snapshot
    handle completion
    close trên T3
~~~

Không được giữ context của T1 mãi chỉ để chờ async task hoàn tất: T1 có thể đã quay lại pool và bắt đầu request B.

Từng **execution boundary trên mỗi thread** phải có scope riêng. Logical request lifetime có thể dài hơn bất kỳ thread-local binding đơn lẻ nào.

## 15. Future trả về không đồng nghĩa tác vụ hoàn tất

Một quanh advice bọc method trả CompletableFuture có thể chạy finally ngay sau khi method trả handle. Công việc thực tế sau đó vẫn tiếp tục và có thể thất bại trên thread khác.

Vì vậy:

- Phạm vi **method return** khác phạm vi **future completion**.
- Nếu callback cần context, nó phải nhận một snapshot đúng quyền và tự quản lý scope.
- Callback success, failure, timeout và cancellation đều cần chính sách ngữ cảnh.
- Không tự giả định callback sẽ chạy trong một thread cụ thể.
- Context sau completion cần được dọn ở thread nơi callback thực sự chạy.

ThreadLocal chỉ là một cách lưu ambient context trong call stack, không phải cơ chế truyền tự động qua mọi kiểu async.

## 16. Cancellation, interruption và timeout

Một task có thể bị cancel hoặc interrupt. Nếu nó đã enter scope và sau đó đi qua finally, cleanup có thể diễn ra. Nhưng **cancel không bảo đảm task dừng ngay lập tức**.

Các khả năng cần phân tích:

- Task chưa được chạy: không có scope worker nào được mở.
- Task đang chạy và phản ứng với interrupt: finally có thể cleanup.
- Task bị kẹt trong I/O không phản ứng ngay: scope vẫn tồn tại cho tới khi thoát.
- Caller timeout và kết thúc chờ: worker vẫn có thể tiếp tục.
- Callback nhận cancellation: cần scope riêng nếu dùng context.

Caller gọi remove trên thread của nó **không thể dọn** ThreadLocal entry của một worker khác. Hủy tác vụ và dọn binding là hai trách nhiệm riêng.

## 17. Cẩn thận với InheritableThreadLocal

**InheritableThreadLocal** cung cấp cơ chế khởi tạo value cho thread con khi thread được tạo. Nhưng request được giao vào **thread pool đã có worker từ trước** không đồng nghĩa với tạo thread con mới cho request ấy.

Vì thế InheritableThreadLocal không thể được coi là giải pháp **per-task context propagation** mặc định.

Ngoài ra, giá trị được kế thừa có thể không có lifecycle giống logical request, và người dùng có thể nhầm dữ liệu được copy lúc tạo thread với dữ liệu current context mới nhất.

Thiết kế đúng cần xét **thời điểm thread được tạo, task được giao và scope được đóng**.

## 18. Memory leak do giá trị ThreadLocal

Một context có thể giữ nhiều dữ liệu:

~~~text
Worker thread
   |
   ThreadLocal entry
      |
      RequestContext
         |
         +-- payload
         +-- user profile
         +-- buffers
~~~

Nếu worker sống lâu, entry không được xóa có thể giữ cả object graph lâu hơn request.

Ở các Java implementation thường dùng, ThreadLocalMap có key yếu nhưng value vẫn có thể được giữ mạnh khi entry chưa được dọn. Việc key ThreadLocal không còn được tham chiếu không có nghĩa value được thu hồi ngay.

Do đó **remove đúng thời điểm** vừa ngăn logical leak vừa giảm retention. Một requestId nhỏ vẫn cần dọn vì nó có thể gây sai log, dù ảnh hưởng bộ nhớ không lớn.

## 19. Context giữa các aspect có chung owner

Ví dụ ba aspect cùng dùng context:

~~~text
ContextOwner
    Trace reads
    Audit reads
    Metrics reads
ContextOwner closes
~~~

Nếu Metrics tự remove context, Trace/Audit sau nó có thể không nhìn thấy context nữa.

Hãy định nghĩa owner:

1. Ai tạo context?
2. Ai được đọc?
3. Ai được tạo scope con?
4. Scope con phải restore về đâu?
5. Ai đóng root scope?
6. Khi nào consumer cuối đã hoàn tất?
7. Có ranh giới async nào cần snapshot không?

Precedence của các around advice có thể quyết định chính sách nào bao ngoài; thứ tự phải dựa trên **bảo đảm của công cụ AOP**, không dựa vào tên class hoặc vị trí file.

## 20. Retry và multiple proceed

Một around advice có thể gọi continuation nhiều lần nếu cơ chế cho phép. Nếu context owner nằm ngoài Retry:

~~~text
ContextOwner enter A
   Retry
      attempt 1
      attempt 2
ContextOwner close A
~~~

Cả hai attempts có thể dùng chung request context. Nếu scope được mở trong mỗi attempt, từng attempt có thể có context phụ nhưng phải được đóng riêng.

Không đặt cleanup ở vị trí chỉ được gọi **một lần** nếu đã mở nhiều scope trong các attempts. Một thiết kế cần đảm bảo **mỗi enter có đúng một close** và data owner rõ.

## 21. Exception trong cleanup có thể che lỗi gốc

Original có thể ném exception E, nhưng cleanup của advice tự ném F trong finally, khiến Caller thấy F thay vì E.

ThreadLocal.remove tự nó đơn giản; nguy cơ tăng nếu cleanup còn gọi logger, serializer, remote sink hoặc resource close.

Một scope context nên có **close path tối giản và có thể kiểm thử**. Nếu cần đóng tài nguyên phức tạp, hãy có chính sách primary/suppressed exceptions phù hợp, tránh làm mất nguyên nhân nghiệp vụ.

Nếu scope phát hiện bị đóng sai thread hoặc sai LIFO, đó là lỗi sử dụng API cần được điều tra; không nên nuốt ngầm chỉ để log trông sạch.

## 22. Không đưa dữ liệu nhạy cảm vào ambient context tùy tiện

Nếu context chứa actor hoặc tenant, một code nhánh B vô tình đọc A có thể tạo vấn đề phân tách thông tin.

Cần:

- Chỉ cài actor/tenant đã được xác thực theo một ranh giới tin cậy.
- Không dùng một requestId tự khai báo làm chứng cứ quyền truy cập.
- Giới hạn các trường truyền qua async boundary.
- Sử dụng snapshot bất biến, không chia sẻ mutable map tùy tiện.
- Không giữ raw token, cookie hoặc payload nếu không cần.
- Không log toàn bộ context bằng toString ở mọi advice.
- Có chính sách khi currentContext không tồn tại.

**Missing context** không được giải quyết bằng cách đọc lại stale context của request trước.

## 23. Logging diagnostic context cũng cần cleanup

Các hệ logging có thể cung cấp diagnostic context để gắn requestId hoặc traceId vào log. Khi cơ chế dựa trên thread, lỗi thread reuse có thể gây log của B mang ID của A.

Một aspect xử lý logging context nên:

- Mở binding tại ranh giới đã chọn.
- Chỉ thêm metadata cần thiết.
- Cho consumer phù hợp đọc.
- Restore previous hoặc remove khi rời scope.
- Dọn cả đường exception.
- Propagate snapshot có chọn lọc cho async task.
- Không tin rằng logger tự quản lý request lifecycle.

Không giả định mọi thư viện logging có cùng API hoặc cùng cách lưu trữ; đây là nguyên lý về **scope và ownership**.

## 24. Unit test cần có cả ca âm

Chỉ kiểm tra:

~~~text
Inside request A: context=A
~~~

chưa chứng minh cleanup.

Cần kiểm tra:

~~~text
After A: context=none hoặc previous
B trên cùng worker: không nhìn thấy A
~~~

Những ca tối thiểu:

| Ca | Kỳ vọng |
|---|---|
| A hoàn tất bình thường | Entry A được dọn |
| A ném RuntimeException | Finally vẫn cleanup khi rời scope |
| Inner scope B kết thúc | Previous A được khôi phục |
| Root scope kết thúc | Không còn A |
| Request B chạy cùng worker sau A | B không nhìn thấy A |
| Hai threads song song | Entry không lẫn nhau |
| Worker task hoàn thành exceptionally | Worker scope được đóng |
| Callback chạy trên executor | Context vào đúng nơi, cleanup đúng nơi |
| Cancellation/timeout | Không giả định Caller dọn được worker |
| Scope close sai thread | Lỗi ownership được phát hiện |
| Scope close sai thứ tự | Không âm thầm làm hỏng context |
| Aspect ngoài short-circuit | Không để context mồ côi |
| Retry nhiều attempts | Scope không bị đóng thiếu/thừa |
| Không có context | Có hành vi theo hợp đồng, không dùng stale data |
| Context chứa object lớn | Không giữ sống quá lâu ngoài ý định |

Executor có **một worker thread** giúp kiểm thử leak ổn định. Nếu sử dụng nhiều worker, việc B chạy ở thread khác có thể che bug.

## 25. Quy trình chẩn đoán khi log B mang ID của A

1. Xác định dữ liệu requestId được lưu ở đâu.
2. Phân biệt ThreadLocal với global/static và per-target aspect state.
3. Xác định thread thực hiện set và get.
4. Xem executor có tái sử dụng thread không.
5. Xác định advice nào sở hữu việc mở context.
6. Kiểm tra tất cả đường thoát khỏi scope.
7. Kiểm tra finally, try-with-resources hoặc after/finally semantics.
8. Xem nested advice có restore previous hay chỉ remove.
9. Kiểm tra handler nào tự remove context của owner khác.
10. Xem context có được truyền có chủ đích qua executor hay không.
11. Kiểm tra callback success/failure/timeout/cancel.
12. Kiểm tra use of InheritableThreadLocal.
13. Kiểm tra stale value hoặc value giữ object graph lớn.
14. Tạo test với hai request trên cùng single-thread executor.
15. Sửa tại **scope owner**, không chèn remove tùy ý trong mọi consumer.

Không sửa lỗi chỉ bằng cách thay tên correlation ID trong log. Nếu binding vẫn rò, các consumers khác vẫn có thể đọc nhầm.

## 26. Lỗi thường gặp

**Lỗi 1: set mà không remove.** Thread pool giữ context A cho B.

**Lỗi 2: chỉ cleanup trên normal return.** Exceptional path để lại stale entry.

**Lỗi 3: nested scope chỉ remove.** Làm mất context cha.

**Lỗi 4: close Scope trên thread khác.** Dọn nhầm thread, owner vẫn rò.

**Lỗi 5: singleton aspect field lưu actor hiện tại.** Nhiều invocation dùng chung field.

**Lỗi 6: dùng per-target state làm request scope.** Cùng Service target xử lý nhiều request.

**Lỗi 7: assume ThreadLocal tự lan truyền qua executor.** Worker không nhất thiết có context.

**Lỗi 8: dùng InheritableThreadLocal với thread pool như per-task scope.** Giá trị có thể lỗi thời.

**Lỗi 9: callback không mở/đóng scope.** Rò ngữ cảnh sau completion.

**Lỗi 10: Caller remove hộ worker.** Chỉ dọn entry của Caller thread.

**Lỗi 11: truyền raw context không kiểm duyệt.** Lộ dữ liệu và kéo dài object lifetime.

**Lỗi 12: cleanup logger ném lỗi rồi che lỗi gốc.** Phải thiết kế error contract.

**Lỗi 13: chỉ test context bên trong request.** Không phát hiện dữ liệu còn sót sau request.

**Lỗi 14: coi context là quyền truy cập.** Actor không được xác thực có thể bị dùng sai.

## 27. Khi nào nên truyền context tường minh?

Trong chuỗi async phức tạp, có thể chọn explicit parameters:

~~~text
process(Context ctx, Input input)
  -> validate(ctx, input)
  -> submitAsync(ctx, input)
~~~

Ưu điểm là rõ dữ liệu được đưa tới đâu, dễ test và ít phụ thuộc ambient state. Nhược điểm là cần truyền xuyên nhiều tầng.

ThreadLocal có thể thuận tiện trong synchronous call stack nếu mở/đóng scope chặt chẽ; explicit context có thể phù hợp khi một logical request di chuyển qua nhiều executor.

Không có cơ chế thắng mọi tình huống. Cần dựa trên **execution model, concurrency, security và lifecycle ownership**.

## 28. Checklist thiết kế một advice quản lý context

- [ ] Xác định logical request boundary thực tế.
- [ ] Chỉ đặt thông tin được phép và cần thiết.
- [ ] Có một owner chịu trách nhiệm enter/close.
- [ ] Có quy tắc root-remove và nested-restore.
- [ ] Dùng finally hoặc scope có cleanup bảo đảm theo ranh giới.
- [ ] Không đóng ThreadLocal scope từ thread khác.
- [ ] Không dùng shared mutable static currentRequest.
- [ ] Không coi per-target aspect state là per-request.
- [ ] Không giả định ThreadLocal tự propagation sang executor.
- [ ] Có snapshot đã kiểm duyệt ở async boundary.
- [ ] Worker/callback tự enter/close trong thread thực thi.
- [ ] Đường exception, retry và short-circuit đều được kiểm thử.
- [ ] Cancellation/timeout được phân biệt với cleanup.
- [ ] Không để cleanup che lỗi nghiệp vụ ngoài hợp đồng.
- [ ] Có test trên thread pool reuse.
- [ ] Kiểm tra context sau request không còn dữ liệu của request trước.
- [ ] Không dùng requestId hay actor không đáng tin như quyền truy cập.

## 29. Bài tập tự kiểm tra

### Câu 1: ThreadLocal và thread pool

A set ngữ cảnh rồi ném lỗi, quên cleanup. B chạy sau trên cùng worker thread. B có thể đọc A không?

**Đáp án:** có. ThreadLocal theo thread, không theo Future hoặc request.

### Câu 2: Main remove giúp worker

Main gọi ThreadLocal.remove sau khi Future của A thất bại. Entry ở worker chắc chắn được dọn không?

**Đáp án:** không. Remove chỉ tác động tới entry của thread gọi.

### Câu 3: Nested scope

A enter, B enter rồi B dùng remove. A có còn context A không?

**Đáp án:** không nếu B không restore previous. Nested scope phải phục hồi A.

### Câu 4: Per-target và per-request

Một target Service chung phục vụ A và B. Per-target aspect instance có tự chứa context riêng mỗi request không?

**Đáp án:** không. Trạng thái của target có thể sống qua nhiều request.

### Câu 5: Future chưa hoàn tất

Method trả CompletableFuture, quanh advice close context khi method return. Future sau đó hoàn thành trên thread khác. Callback có tự thấy context ban đầu không?

**Đáp án:** không có bảo đảm. Callback cần scope/context propagation riêng.

### Câu 6: InheritableThreadLocal

Dùng InheritableThreadLocal có tự lấy context hiện hành của từng task vào worker của thread pool không?

**Đáp án:** không. Kế thừa xảy ra theo thread creation, không phải mỗi lần submit task.

### Câu 7: Cancellation

Caller timeout rồi close scope của Caller. Worker vẫn chạy. Context worker đã sạch chưa?

**Đáp án:** chưa chắc. Worker phải cleanup scope của chính nó khi thực sự thoát.

### Câu 8: Scope owner

Audit chỉ đọc context do Tracing tạo. Audit có nên remove nó sau khi ghi xong không?

**Đáp án:** không. Owner của context phải quản lý đóng scope; consumer chỉ đọc không tự xóa.

### Câu 9: Finally và exception

Original ném IOException, cleanup logger trong finally ném RuntimeException. Có nguy cơ che IOException không?

**Đáp án:** có. Nên giữ cleanup đơn giản và có chính sách lỗi rõ.

### Câu 10: Kiểm thử tối thiểu

Chỉ kiểm tra trong A có requestId A đã đủ chưa?

**Đáp án:** chưa. Phải kiểm tra sau A đã sạch, và request B trên cùng thread không nhìn thấy A.

## 30. Tổng kết

**Dọn dữ liệu ngữ cảnh để tránh rò rỉ giữa các yêu cầu** là một trách nhiệm lifecycle riêng, không tự được hoàn thành chỉ vì advice có thể đọc và đặt request metadata.

Những nguyên tắc cần nhớ:

- **ThreadLocal là thread-scoped, không phải request-scoped**.
- **Thread pool reuse** khiến dữ liệu request trước tồn tại trong request sau nếu quên dọn.
- **Mỗi enter cần một close**; root scope remove, nested scope restore previous.
- **Chỉ owner đóng scope**, consumer không tự dọn context của người khác.
- **Thread khác không thể dọn binding của owner bằng ThreadLocal.remove**.
- **Async task và callback** phải có scope riêng và propagation có chủ đích.
- **Context bất biến, tối thiểu và có nguồn đáng tin** giúp giảm rủi ro chia sẻ sai.
- **Per-target state và singleton aspect fields** không phải nơi phù hợp cho dữ liệu request hiện tại.
- **Finally không thay thế toàn bộ cancellation/deadline management** và cleanup cũng cần có error contract.
- **Test âm trên cùng worker sau request** mới chứng minh state không còn rò.

**Câu hỏi cốt lõi của mỗi advice quản lý context:** *Ai mở scope này, nó thuộc thread/execution boundary nào, và ai chắc chắn phục hồi hoặc xóa đúng dữ liệu trước khi một yêu cầu khác dùng lại môi trường đó?*
