# Truyền ngữ cảnh qua tác vụ bất đồng bộ có kiểm soát trong AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, advice thường cần biết thông tin về lần xử lý hiện tại: mã tương quan (correlation/trace ID), phạm vi quan sát, tên operation, thời hạn, tenant đã được xác minh hoặc chính sách áp dụng cho một lời gọi. Những dữ liệu này thường được gọi là **ngữ cảnh thực thi (execution context)**. Ở luồng gọi **đồng bộ** trong cùng một thread, có thể truyền trực tiếp qua tham số, local variable hoặc một context holder được quản lý cẩn thận.

Tuy nhiên, một phương thức nghiệp vụ có thể **gửi tác vụ sang executor**, trả về `Future` hoặc `CompletionStage`, rồi công việc thật tiếp tục trên **thread khác**. Khi đó, ngữ cảnh từ caller **không tự xuất hiện** trong thread chạy tác vụ. Nếu advice chỉ đặt một giá trị vào `ThreadLocal` ở thread ban đầu rồi giả định tác vụ bất đồng bộ sẽ đọc được, kết quả có thể là mất trace, gắn sai tenant, dùng thông tin của request cũ hoặc ghi audit sai chủ thể.

Một cách giải quyết có kiểm soát gồm các bước:

1. **Capture:** lấy snapshot ngữ cảnh được phép truyền tại **ranh giới tạo/gửi tác vụ**.
2. **Propagate:** gắn snapshot đó vào tác vụ bằng wrapper, tham số hoặc API hỗ trợ.
3. **Install/activate:** cài snapshot vào phạm vi thực thi của thread đang chạy **trong lúc tác vụ thực sự thực hiện**.
4. **Execute:** cho phần nghiệp vụ và advice cần context chạy bên trong phạm vi ấy.
5. **Restore/clear:** trong `finally`, khôi phục giá trị có từ trước hoặc xóa context, kể cả khi có ngoại lệ/cancellation.
6. **Verify:** kiểm thử task bình thường, lồng nhau, lỗi, thread pool tái sử dụng và các nhánh async khác.

**Hai quy tắc cốt lõi:** context phải thuộc **đúng invocation/logical operation**, không phải một field dùng chung của aspect; và phải **chủ động xác định ranh giới, dữ liệu, thời điểm và thời hạn truyền**, không truyền toàn bộ request object hoặc credentials theo quán tính.

Bài này nói về **AOP cơ bản và nâng cao nói chung**, không áp đặt một framework riêng. Ví dụ Java 17 thuần dùng một lớp wrapper mô phỏng advice tại thời điểm scheduling; nó không phải một bộ weaver tự can thiệp mọi lời gọi hoặc một cơ chế pointcut phổ quát.

## 1. Những loại ngữ cảnh cần phân biệt

| Loại dữ liệu | Ví dụ | Có nên tự động truyền? | Điều kiện |
| --- | --- | --- | --- |
| Correlation/trace ID | `trace-42` | Có thể | Format hợp lệ, độ dài giới hạn, ngăn dữ liệu nhạy cảm |
| Span/operation context | Parent trace/span, sampling flag | Có thể | Tuân thủ ngữ nghĩa span và thời điểm completion |
| Tenant identity đã xác minh | Tenant ID | Chỉ khi nghiệp vụ cần | Lấy từ nguồn tin cậy, không tin một chuỗi client tùy ý |
| Auth principal/token | Credential, access token | **Không mặc định** | Security design rõ, least privilege, expiry/revocation |
| Deadline/cancellation | Hạn chót, tín hiệu hủy | Thường cần mô hình riêng | Truyền và kiểm tra ở điểm thích hợp |
| Locale/timezone | Ngôn ngữ định dạng | Khi ảnh hưởng kết quả hợp đồng | Bất biến hoặc snapshot rõ |
| Transaction context | Định danh giao dịch, connection | **Không tự sao chép** | Transaction có ownership/thread binding và commit rules riêng |
| Logging context | Operation/category đã duyệt | Có thể | Dọn sạch, giới hạn field, không truyền PII |
| Mutable request/response object | Toàn bộ HTTP request, payload | Nên tránh | Vòng đời, thread safety, quyền truy cập, retention |

**Không có một “context toàn năng”.** Một trace ID phục vụ tương quan sự kiện; nó **không xác nhận danh tính người dùng**. Một tenant ID do caller tự truyền vào cũng không phải giấy phép truy cập dữ liệu của tenant ấy. Một advice bảo mật phải luôn xác minh identity/authorization tại ranh giới đáng tin, theo hợp đồng cụ thể.

### 1.1 Ngữ cảnh join point và ngữ cảnh nghiệp vụ

AOP có thể đưa tới advice những giá trị:
- `args`: tham số của invocation hiện tại.
- `target`: đối tượng đích của điểm đang xét khi có.
- `this`: đối tượng đang thực thi, tùy loại join point và mô hình.
- Metadata của phương thức/chữ ký.
- Context riêng của một trace hoặc thao tác logic.

Không phải dữ liệu nào ở join point cũng cần đưa sang async task. Truyền toàn bộ `args`, `target` hay một object proxy sang nơi chạy sau có thể **giữ object sống lâu hơn cần thiết**, làm rò thông tin hoặc phá thread safety. Chỉ copy các field được phép và thực sự dùng ở phía tác vụ.

### 1.2 Context khác shared aspect state

Một aspect dùng chung có thể nhận hàng nghìn invocation đồng thời. Nếu có field `currentTraceId`, T2 có thể ghi đè khi T1 chưa xử lý xong. Khi mang context sang task:
- **Sai:** lưu trace/tenant hiện tại vào field của shared aspect.
- **Đúng hơn:** capture một object **bất biến** cho invocation, rồi truyền nó qua wrapper/task boundary.
- Nếu phải giữ state theo một workflow, cần scope/key/lifecycle rõ, không dùng một biến global tùy tiện.

## 2. Vì sao ThreadLocal không tự truyền ngữ cảnh?

`ThreadLocal<T>` trong Java cung cấp một value **riêng cho mỗi Java thread**. Khi caller T1 chạy:

~~~text
Thread T1 (request handler):
    ThreadLocal.trace = "A"
    executor.submit(task)
~~~

Tác vụ có thể chạy trên worker T2:

~~~text
Thread T2 (executor worker):
    read ThreadLocal.trace
    => không tự có "A"
~~~

Một thread trong pool thường đã tồn tại từ trước, hoặc được tạo ở một thời điểm không trùng với caller. **Không có cam kết ThreadLocal của T1 được copy sang T2**.

### 2.1 Thread pool tái sử dụng còn nguy hiểm hơn mất context

Nếu một task cài `trace=A` trên worker nhưng **không xóa**:
1. Task A hoàn tất.
2. Executor tái sử dụng **chính worker** cho task B.
3. Task B đọc `trace=A` mặc dù không thuộc request A.

Lúc đó dữ liệu có thể bị **gắn sai correlation, sai tenant, sai audit subject**, dẫn tới lỗi bảo mật hoặc truy vết rất khó phát hiện. Dùng một worker cho nhiều task là chủ ý của thread pool, không phải bug executor.

### 2.2 Không đồng nhất per-thread với per-request

Một logical request:
- Có thể đi qua **nhiều thread** vì async fan-out, callback, timeout handler.
- Có thể có **nhiều child tasks** chạy song song.
- Có thể kết thúc ở thread khác thread đã bắt đầu.

Một thread:
- Có thể phục vụ **nhiều request** nối tiếp nhau.
- Có thể xử lý nested flow với context tạm thời khác.
- Có thể chạy task sau khi request ban đầu đã hết hạn.

Vì vậy **request context cần được mô hình hóa theo hoạt động logic**, còn ThreadLocal (nếu dùng) chỉ là **cơ chế gắn tạm vào phạm vi của thread hiện tại**.

## 3. Capture → wrap → restore: giao thức truyền có kiểm soát

Một giao thức cơ bản:

~~~text
Caller T1                            Executor worker T2
    |                                       |
    | context A (verified & minimal)        |
    |                                       |
    | capture snapshot A                    |
    | ---- submit(wrapped task A) --------> |
    |                                       | save previous context P
    |                                       | install snapshot A
    |                                       | run task + applicable advice
    |                                       | finally restore P (or remove)
    |                                       |
    | <----------- Future result --------- |
    | caller scope exits; restore caller    |
~~~

Những khác biệt quan trọng:
- **Capture** xảy ra ở **caller thread tại thời điểm scheduling**, không phải lúc task bắt đầu chạy.
- **Install** xảy ra ở **worker thread khi task bắt đầu chạy**.
- **Restore** xảy ra trong `finally` của chính worker.
- Việc restore ở caller **không** dọn context trên worker; mỗi bên có scope riêng.
- Khi tác vụ chạy nhiều thread hoặc chia ra child tasks, mỗi ranh giới cần propagation theo thiết kế.
- Truyền đúng context **không tự bảo đảm** task còn được quyền thực hiện thao tác tại thời điểm chạy; các policy có expiry/revocation phải được tái kiểm tra nếu hợp đồng yêu cầu.

### 3.1 Vì sao phải snapshot?

Nếu advice giữ tham chiếu tới một map mutable `currentContext` rồi submit:
- Caller hoặc invocation B có thể thay map trước khi task A bắt đầu.
- Một task có thể thấy field phiên bản cũ xen field phiên bản mới.
- Có thể chia sẻ object request hết hạn hoặc dữ liệu không còn hợp lệ.

Một object bất biến chứa **một tập field có chủ đích** tạo ranh giới rõ hơn. Snapshot không nhất thiết là "copy toàn bộ object"; cần chọn field, validate và tránh chứa các tham chiếu mutable chưa kiểm soát.

### 3.2 Vì sao restore chứ không chỉ clear?

Giả sử worker đang chạy một context P (ví dụ một lời gọi lồng nhau), sau đó tạm gọi một đoạn code với context A. Khi kết thúc A, phải **khôi phục P**, không luôn luôn remove:

~~~text
worker initially: P
  enter nested scope A
    current: A
  exit nested scope A
worker current again: P
~~~

Nếu trước đó không có context, `remove()` hợp lý. Nếu có context, `set(previous)` giữ đúng scope lồng nhau. Đây là cùng nguyên tắc **push/pop trạng thái**, không xóa tùy tiện context của phạm vi ngoài.

### 3.3 Phạm vi exception và cancellation

`try/finally` là yêu cầu tối thiểu: task có thể return, throw hoặc thực hiện cleanup. Với cancel:
- Nếu task **chưa chạy**, wrapper không cài ThreadLocal; không có gì phải dọn trên worker.
- Nếu task **đang chạy và bị ngắt**, cleanup trong `finally` chạy khi control thực sự thoát scope; không được mặc định `cancel(true)` tức khắc giết task.
- Nếu task **không đáp ứng interruption hoặc bị kẹt**, context có thể còn trong worker trong lúc task tiếp tục chạy. Do đó cần timeout, interrupt handling và task ownership phù hợp.
- Với callback bất đồng bộ được đăng ký về sau, scope hiện tại đóng rồi **không đủ** để giữ context cho callback; phải xử lý chính boundary đó.

## 4. Java 17 chạy độc lập: có truyền, không truyền, nested và exception

Ví dụ dưới đây dùng:
- `TraceContext` là Java record bất biến, chỉ chứa **traceId** và **tenantId giả**.
- `ContextScope` quản lý ThreadLocal bằng `with(snapshot, Callable)` có **restore trong finally**.
- `PropagationAdvice.prepare` **capture ngữ cảnh ở thời điểm gửi task** và trả một `Callable` đã bọc.
- `Executors.newSingleThreadExecutor()` để **tái sử dụng cùng worker**, giúp chứng minh không rò context.
- `Future.get()` và chỉ in ở thread chính để **stdout có thứ tự xác định**, không phụ thuộc lịch print giữa các task.
- Trường hợp raw task không bọc, task có bọc, scope lồng nhau, task ném lỗi và tác vụ sau cùng không có context.

Mẫu này mô phỏng cách **một advice ở boundary scheduling** có thể bọc task. Nó **không tự dệt bytecode** vào mọi `Executor.submit`; caller phải dùng wrapper (hoặc một cơ chế instrumentation phù hợp) ở các boundary được chọn.

Tạo file `AsyncContextAdviceDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncContextAdviceDemo {
    record TraceContext(String traceId, String tenantId) {}

    static final class ContextScope {
        private static final ThreadLocal<TraceContext> CURRENT =
                new ThreadLocal<>();

        static TraceContext current() {
            return CURRENT.get();
        }

        static String describe() {
            TraceContext c = current();
            if (c == null) {
                return "trace=none tenant=none";
            }
            return "trace=" + c.traceId() + " tenant=" + c.tenantId();
        }

        static <T> T with(TraceContext next, Callable<T> task)
                throws Exception {
            TraceContext previous = CURRENT.get();

            if (next == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(next);
            }

            try {
                return task.call();
            } finally {
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
            }
        }
    }

    // Advice mô phỏng tại boundary gửi tác vụ.
    static final class PropagationAdvice {
        static <T> Callable<T> prepare(Callable<T> task) {
            TraceContext snapshot = ContextScope.current();
            return () -> ContextScope.with(snapshot, task);
        }
    }

    public static void main(String[] args) throws Exception {
        TraceContext a = new TraceContext("A", "alpha");
        TraceContext b = new TraceContext("B", "beta");

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            String sync = ContextScope.with(
                    a, ContextScope::describe);
            System.out.println("SYNC " + sync);

            Future<String> raw = ContextScope.with(
                    a, () -> pool.submit(
                            () -> "RAW " + ContextScope.describe()));
            System.out.println(raw.get());

            Future<String> wrapped = ContextScope.with(
                    a, () -> pool.submit(
                            PropagationAdvice.prepare(
                                    () -> "SAFE "
                                            + ContextScope.describe())));
            System.out.println(wrapped.get());

            Future<String> nested = ContextScope.with(
                    a, () -> pool.submit(
                            PropagationAdvice.prepare(() -> {
                                String before = ContextScope.describe();
                                String inner = ContextScope.with(
                                        b, ContextScope::describe);
                                String after = ContextScope.describe();
                                return "NESTED before=[" + before
                                        + "] inner=[" + inner
                                        + "] after=[" + after + "]";
                            })));
            System.out.println(nested.get());

            Future<String> failure = ContextScope.with(
                    a, () -> pool.submit(
                            PropagationAdvice.<String>prepare(() -> {
                                throw new IllegalStateException("boom");
                            })));

            try {
                failure.get();
            } catch (ExecutionException error) {
                Throwable cause = error.getCause();
                System.out.println("ERROR "
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }

            Future<String> following = pool.submit(
                    () -> "POST " + ContextScope.describe());
            System.out.println(following.get());
        } finally {
            pool.shutdownNow();
        }

        System.out.println("MAIN " + ContextScope.describe());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac AsyncContextAdviceDemo.java
java AsyncContextAdviceDemo
~~~

Stdout xác định:

~~~text
SYNC trace=A tenant=alpha
RAW trace=none tenant=none
SAFE trace=A tenant=alpha
NESTED before=[trace=A tenant=alpha] inner=[trace=B tenant=beta] after=[trace=A tenant=alpha]
ERROR IllegalStateException:boom
POST trace=none tenant=none
MAIN trace=none tenant=none
~~~

### 4.1 Giải thích `RAW`: worker không kế thừa ThreadLocal

Caller T1 có context A khi submit `raw`, nhưng `raw` không được bọc. Thread do executor sử dụng có ThreadLocal của **chính nó**, ban đầu không có context nên in:

~~~text
RAW trace=none tenant=none
~~~

Đây là **hành vi đúng theo Java ThreadLocal**, không phải lỗi executor. Không dùng sự vắng context trong worker để suy rằng caller đã mất context; hai thread có holder khác nhau.

### 4.2 Giải thích `SAFE`: capture ở caller, install trên worker

`PropagationAdvice.prepare` được gọi **bên trong `ContextScope.with(a,...)` của caller**, nên capture `TraceContext("A","alpha")`. Nó trả một callable mới để khi worker chạy sẽ:
1. Save context trước đó (ở ví dụ là null).
2. Set context A.
3. Thực hiện business callable.
4. Restore null bằng `remove()` trong finally.

Kết quả:

~~~text
SAFE trace=A tenant=alpha
~~~

Như vậy, ngữ cảnh không được “copy thần kỳ” bởi ThreadLocal; **wrapper chủ động truyền qua ranh giới task**.

### 4.3 Giải thích nested: trả lại context ngoài

Bên trong task A, `ContextScope.with(b,...)` tạm thay A bằng B và gọi một đoạn logic. Khi đóng scope B, `finally` khôi phục A. Vì thế cùng một worker in:
- Before: A.
- Inner: B.
- After: A.

Điều này đặc biệt quan trọng khi advice trong một request cần tạm sử dụng một **scope quan sát phụ**, nhưng không được phép làm rò context phụ sang phần còn lại của request.

### 4.4 Giải thích error: cleanup vẫn xảy ra

Task lỗi ném `IllegalStateException("boom")`. `Future.get()` báo `ExecutionException` chứa lỗi gốc. Dù target ném lỗi, `ContextScope.with(...)` vẫn thực hiện `finally`.

Task tiếp theo trên cùng **single-thread executor worker** in `POST trace=none tenant=none`. Đây là bằng chứng kiểm tra cleanup trong demo. Nếu wrapper bỏ `finally`, task tiếp theo có thể vô tình thấy A.

### 4.5 Giải thích MAIN: caller cũng restore

`ContextScope.with(a,...)` trên caller đã restore giá trị trước đó sau khi submit mỗi task. Vì vậy sau toàn bộ demo, thread main không giữ A hoặc B:

~~~text
MAIN trace=none tenant=none
~~~

**Cả hai phía đều cần scope đúng:** worker cleanup không thay thế caller cleanup, và ngược lại.

### 4.6 Giới hạn của ví dụ

- Dùng **wrapper Java 17 thuần**, không dùng pointcut/weaver để tự động chọn mọi lệnh submit.
- Context chỉ gồm **dữ liệu giả**; không đưa access token/credential thật vào ThreadLocal.
- Không có propagation sang process khác hoặc qua network.
- `ExecutorService` chỉ giúp chạy tác vụ, không tự xử lý trách nhiệm security/tracing của ứng dụng.
- `shutdownNow()` ở cuối được gọi sau các `Future.get()` trong demo; trong production cần quản lý vòng đời executor theo chủ sở hữu của nó, không shutdown một pool dùng chung sau mỗi request.
- Ví dụ bắt `ExecutionException` để minh họa; các lỗi `InterruptedException`, `CancellationException` và tình huống task bị treo cần xử lý theo chính sách thực tế.
- Không giữ context qua toàn bộ thời gian của một chuỗi `CompletionStage` tự động; mỗi boundary tiếp tục cần lựa chọn propagation phù hợp.

## 5. Ranh giới AOP: intercept ở submission hay execution?

Có ít nhất hai thời điểm khác nhau:

**A. Scheduling/submission boundary:** caller gọi `submit(task)` và advice có thể capture **ngữ cảnh ở caller** rồi bọc `task`. Đây là thời điểm phù hợp để lấy snapshot.

**B. Worker execution boundary:** task bắt đầu chạy. Advice có thể cài snapshot vào worker, thực thi task và dọn context trong finally.

Nếu chỉ instrument `Runnable.run()` hoặc một method execution xảy ra **trên worker** mà không mang snapshot sang, advice chỉ thấy **context đang có của worker**, không tự biết context của caller nào đã submit task.

~~~text
Caller (T1)              Task queue              Worker (T2)
  context A
     |
     | capture A
     v
  wrap task(A)  ----------> queued  ----------> activate A
                                                  |
                                                  v
                                             business + advice
                                                  |
                                                  v
                                             restore previous
~~~

### 5.1 Mỗi loại join point cho ngữ cảnh khác nhau

Trong một số mô hình AOP, pointcut chọn method-call join point ở phía caller hoặc method-execution join point ở phía callee. Một proxy/wrapper cũng có thể chỉ nhận những lời gọi đi qua đối tượng trung gian.

Nếu lời gọi scheduling bypass proxy, advice đặt trên proxy submit **không được gọi**; nếu task chạy qua một đường không được instrument, execution advice cũng không tự xuất hiện. Cần kiểm tra đúng **tập join point được chọn và đường gọi thực tế**.

### 5.2 Không nhầm `this`, `target`, `args` với context đang truyền

`this` và `target` có ý nghĩa theo loại join point; `args` là tham số invocation. Một callable có thể capture một object target qua closure nhưng không có nghĩa mọi dữ liệu trong object đó là **execution context hợp lệ để chuyển sang thread khác**.

Giữ một reference target lớn trong task có thể:
- Kéo dài vòng đời object và tài nguyên.
- Giữ một session/context request đã đóng.
- Làm nhiều thread truy cập một object không thread-safe.
- Gây nhầm identity nếu thao tác chạy sau khi trạng thái target đã đổi.

Giới hạn context trong một **hợp đồng truyền riêng** thay vì coi mọi captured reference là "ngữ cảnh".

## 6. CompletableFuture và callback: mỗi stage là một boundary

Một luồng bất đồng bộ có thể:

~~~text
Caller
  |
  +--> supplyAsync(task1)
             |
             +--> thenApply(transform)
             |
             +--> thenApplyAsync(transform2, executorB)
             |
             +--> whenComplete(audit)
~~~

Không thể mặc định **mọi stage chạy trên cùng thread**:
- Stage không có hậu tố `Async` có thể được kích hoạt bởi thread hoàn tất stage trước hoặc thread gắn continuation theo hợp đồng API.
- Stage có hậu tố `Async` sử dụng một executor tương ứng hoặc default asynchronous execution facility.
- Thời điểm callback được gắn so với thời điểm stage trước hoàn thành có thể ảnh hưởng thread thực thi của callback.

Do đó **ThreadLocal hiện tại ở stage trước không tự thành context của stage tiếp theo**.

### 6.1 Cách tiếp cận với stage async

Ở mỗi continuation cần context:
1. **Capture** một snapshot được phê duyệt ở ranh giới lập stage.
2. Bọc lambda/callback để **install/restore** khi callback thực thi.
3. Truyền rõ executor nếu yêu cầu execution policy cụ thể.
4. Định nghĩa context của child task: kế thừa trace parent hay tạo span con?
5. Không chia sẻ mutable tracing state không đồng bộ giữa sibling branches.
6. Cleanup theo completion, error và cancellation.

Ví dụ ý tưởng:

~~~text
snapshot = captureAllowedContext()
stage = async(task)
stage2 = stage.thenApplyAsync(
    value -> withContext(snapshot, () -> transform(value)),
    chosenExecutor
)
~~~

Đây là **giả mã**, không phải một đoạn Java độc lập. Nếu dùng API Java có checked exceptions, adapter lambda phải map lỗi sang dạng phù hợp với `CompletionStage` (ví dụ `CompletionException`), không ném checked exception tùy tiện ra khỏi `Function`.

### 6.2 Không lấy context từ thread đăng ký callback một cách mù quáng

Giả sử callback được đăng ký **sau khi request ban đầu đã kết thúc**. Nếu lúc đó thread đang xử lý một request khác, việc “capture current ThreadLocal” tại callback registration có thể lấy **sai ngữ cảnh**. Context của stage nên được gắn với **logical operation** hoặc capture ở thời điểm chính xác đã định trong kiến trúc.

Ví dụ khi fan-out từ request A sang ba task, nên có snapshot A rõ ràng để từng child tạo span con riêng (nếu tracing model yêu cầu), thay vì đọc `ThreadLocal` của một worker bất kỳ vào lúc nó nhận việc.

### 6.3 Trả Future khác với hoàn thành công việc

Một method có thể trả `CompletionStage` rất nhanh, trong khi nghiệp vụ vẫn chạy. Với một around advice:

~~~text
before
result = proceed()   // trả stage
after-returning       // chạy khi stage đã được trả
~~~

`after-returning` trong phạm vi **lời gọi trả stage** chưa chắc ghi nhận **thành công cuối của tác vụ**. Muốn kết luận thành công/lỗi của async operation, phải quan sát **completion** và map đúng exception/cancellation.

Không giữ `startTime` hoặc `lastFuture` trong shared aspect field rồi chờ task, vì các request đồng thời có thể ghi đè. Dùng local/immutable operation context hoặc state keyed theo logical operation có vòng đời được quản lý.

## 7. Fan-out, fan-in và ngữ cảnh cha/con

Một request có thể phát nhiều child tasks:

~~~text
Request A [trace A]
      |
      +--> Task A1 [parent A, child span 1]
      +--> Task A2 [parent A, child span 2]
      +--> Task A3 [parent A, child span 3]
      |
      v
   join results
~~~

Các child có thể chia sẻ **trace correlation** của parent, nhưng không có nghĩa được dùng chung **một span mutable đang ghi** hoặc **một biến `currentChild`** của shared aspect. Mỗi child nên có context riêng theo ngữ nghĩa tracing, trong đó liên kết parent/child rõ ràng.

Ở bước fan-in, cần quyết định:
- Context của phép kết hợp là context parent hay tạo span mới?
- Phép tính có tiếp tục khi một child lỗi hoặc bị hủy không?
- Nếu một child hoàn tất sau timeout, có được phát event nữa không?
- Error aggregation là một lỗi chung hay danh sách lỗi con?
- Ai chịu trách nhiệm cleanup state thuộc request parent?

**Dùng correlation ID không giải quyết mọi câu hỏi trên.** Nó chỉ hỗ trợ nối các sự kiện; không cho phép một child tự sử dụng identity hoặc quyền của parent ngoài hợp đồng.

## 8. Ngữ cảnh tại ranh giới dịch vụ từ xa

Truyền context qua **network/process boundary** khác với copy `ThreadLocal`:
- Phải serialize những metadata được phép vào giao thức.
- Bên nhận cần validate format, version, kích thước và nguồn dữ liệu.
- Trace context bên ngoài có thể bị client giả mạo; không dùng nó như token xác thực.
- Authentication/authorization phải dựa vào cơ chế tin cậy độc lập.
- Không tự truyền raw access token, session object hoặc dữ liệu cá nhân chỉ vì caller có chúng trong context.
- Bên nhận phải áp dụng chính sách tenant và quyền theo dữ liệu đáng tin.

Một nguyên tắc hữu ích: **propagate correlation, revalidate authority**. Nếu một identity đã được xác thực và được phép ủy quyền, phải dùng cơ chế ủy quyền chính thức có ràng buộc audience/scope/expiry, không thay thế bằng chuỗi tenant ID do trace gửi đến.

### 8.1 Baggage/metadata phải có ngân sách

Một số hệ thống truyền nhiều field phụ trong context. Nếu chấp nhận mọi field tùy ý, dữ liệu có thể tăng không giới hạn qua các hop, làm nặng request hoặc vô tình mang bí mật đi xa. Nên:
- Allowlist key.
- Giới hạn tổng kích thước và độ dài value.
- Dùng encoding hợp lệ.
- Không truyền object graph, stack trace, response body tùy tiện.
- Định nghĩa TTL/hop budget nếu nghiệp vụ cần.
- Có chiến lược bỏ những field không quan trọng khi vượt ngân sách.

## 9. Thiết kế API để không phụ thuộc ngầm vào ThreadLocal

Một cách dễ kiểm thử là truyền context **tường minh**:

~~~java
// MẢNH MINH HỌA, không phải chương trình chạy độc lập.
record OperationContext(String traceId, String tenantId) {}

interface AsyncOperation {
    java.util.concurrent.CompletionStage<String> run(
            OperationContext context, String requestId);
}
~~~

Ưu điểm:
- Caller nhìn thấy dependency context trong chữ ký.
- Không cần đoán worker thread.
- Mỗi child task có thể nhận snapshot riêng.
- Dễ viết test cho identity, deadline, trace propagation.
- Ít rủi ro thread pool giữ state của request trước.

Nhược điểm:
- Phải truyền tham số qua nhiều tầng.
- Một số thư viện/legacy API có chữ ký không thể thay.
- Code cần một abstraction để tránh passing context không cần thiết vào những domain functions thuần.

Khi AOP được dùng để giảm boilerplate, lời khuyên không phải "luôn truyền mọi context bằng tay", mà là **thiết kế contract ngữ cảnh rõ**, rồi chọn giữa explicit parameter, scoped context holder, wrapper, hoặc API hỗ trợ sao cho các boundary được quản lý nhất quán.

### 9.1 Context object nên bất biến

Java record là một lựa chọn tiện cho các field bất biến về mặt tham chiếu. Nhưng record chứa `List` hoặc `Map` mutable vẫn có thể bị sửa nội dung bên trong. Khi snapshot chứa collection, cần tạo **immutable copy** hoặc dùng kiểu bất biến theo hợp đồng.

Không giữ reference đến request body, stream, connection hoặc object có lifecycle ngắn trong context sống lâu. Điều này có thể gây leak, xử lý trên tài nguyên đã đóng, hoặc sử dụng dữ liệu sau khi quyền đã hết hạn.

## 10. Chính sách propagation theo từng loại concern

### 10.1 Tracing

- Capture trace context tại đúng operation boundary.
- Tạo parent/child span hợp lệ khi fan-out.
- Kết thúc span ở **async completion**, không khi trả future nếu đo toàn operation.
- Đảm bảo một span không được kết thúc hai lần do callback và timeout cạnh tranh.
- Tránh dùng global `currentSpan` field của shared aspect.

### 10.2 Logging

- Chỉ truyền một vài field an toàn như traceId, operationName.
- Không in raw `args`, token hoặc payload.
- Dọn logging context ở worker trong finally.
- Không để logging advice tự instrument chính sink của nó rồi tạo vòng recursion.
- Kết hợp với structured events và correlation ID để không dựa vào thứ tự dòng log giữa thread.

### 10.3 Authorization

- Không dùng traceId/tenantId từ context như bằng chứng đã xác thực.
- Nếu cần người đại diện để chạy tác vụ, sử dụng delegation model có quyền tối thiểu, expiry và revocation rõ.
- Revalidate quyền tại thời điểm tác vụ thực thi nếu chính sách yêu cầu.
- Nếu request kết thúc/cancel trước khi child chạy, xác định tác vụ có còn được phép tiếp tục không.
- Không để shared aspect field giữ `lastAuthorizedUser` rồi gán cho child task.

### 10.4 Transaction

- Transaction context có thể gắn với thread/resource và có vòng đời riêng.
- Không copy `ThreadLocal` transaction tùy tiện sang executor: connection, lock, transaction manager có thể không cho phép truy cập đa luồng như vậy.
- Cân nhắc ranh giới transaction **mới** cho async task hoặc hợp đồng propagation được nền tảng hỗ trợ.
- Định nghĩa rollback/error khi parent/child hoàn tất khác thời điểm.

### 10.5 Retry, deadline và cancellation

- Correlation context có thể được dùng lại qua retry, nhưng mỗi attempt cần event/ID phân biệt.
- Một deadline có thể được truyền dưới dạng thời điểm tuyệt đối hoặc budget có quy tắc; tránh reset deadline ở mỗi hop khiến request chạy mãi.
- Propagation context không tự hủy task. Cần cancellation signal, xử lý interruption và cleanup phù hợp.
- Nếu retry task trong worker khác, phải đảm bảo **cùng logical operation context hợp lệ** được dùng, không capture ngẫu nhiên thread local của worker retry.

## 11. Lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh | Hướng sửa |
| --- | --- | --- | --- |
| Task async mất trace ID | Không capture ở submission | So sánh caller vs worker context | Bọc task bằng snapshot hợp lệ |
| Task B mang trace của A | Quên restore/clear ThreadLocal | Chạy hai task nối tiếp trên cùng pool worker | `finally` restore previous/remove |
| Nested task mất parent context | Luôn `remove()` khi thoát scope con | Kiểm tra before/inner/after | Save/restore previous |
| Một child mang tenant sai | Dùng shared mutable field | Concurrent test fan-out | Immutable context per invocation |
| Context còn trên caller sau submit | Caller cài nhưng không restore | Assert context sau khi gửi task | Dùng scope `try/finally` |
| Trace kết thúc sớm | After-returning lúc trả stage | Đo thời điểm stage completion | Hook completion phù hợp |
| Callback stage tiếp theo mất context | Chưa bọc continuation mới | Kiểm tra từng stage boundary | Propagate cho mỗi callback cần |
| Ngữ cảnh cũ sau timeout | Task chạy tiếp hoặc cleanup thiếu | Test timeout/cancel/interrupt | Cancellation policy và finally |
| Log nhầm người dùng | Identity lấy từ trace metadata | Security test nhiều tenant | Dùng trusted authorization source |
| Tăng RAM sau tải cao | Context giữ request/target lớn | Heap analysis/retention | Minimal immutable fields, release |
| Context từ luồng khác không thấy | ThreadLocal không xuyên executor | Task raw vs wrapped | Explicit wrapper/context API |
| Số lần gọi advice sai | Proxy bypass hoặc nested advice | Trace submission/execution join points | Kiểm tra actual interception scope |
| Async error không được ghi | Chỉ có after-returning đồng bộ | Test failing future/stage | Theo dõi completion/error |
| Request context bị trộn | Capture reference mutable | Stress test xen kẽ | Snapshot bất biến |
| Điều kiện security đã hết hiệu lực | Snapshot quyền quá lâu | Test revoke trong hàng đợi | Revalidate khi execute nếu cần |

## 12. Kiểm thử propagation một cách có chứng cứ

Không đủ để assert “từng có dòng trace A trong log”. Hãy phân biệt **đúng boundary, đúng scope, đúng lifetime và không rò sang task khác**.

| Trường hợp | Kết quả kỳ vọng |
| --- | --- |
| Caller có context A, raw task trên pool | Không mặc định có A |
| Caller có A, wrapped task | Worker thấy A trong task |
| Caller đổi sang B sau scheduling A | Task A vẫn dùng snapshot A nếu thiết kế vậy |
| Hai child A1/A2 song song | Mỗi child giữ context riêng đúng parent |
| Nested scope B trong task A | Sau B phải restore A |
| Task ném exception | Worker cleanup và caller thấy lỗi nguyên nhân |
| Task bị cancel trước khi chạy | Không cài context trên worker |
| Task bị cancel lúc đang chạy | Cleanup khi task thực sự thoát scope |
| Pool tái sử dụng worker | Task không context không thấy context cũ |
| `CompletionStage` chain | Mỗi continuation cần context có chủ đích |
| Retry ở worker khác | Giữ correlation hợp lệ, phân biệt attempts |
| Deadline hết hạn | Không tiếp tục hành động trái policy |
| Multi-tenant | Không lẫn identity/tenant giữa các request |
| Sensitive context | Không truyền token/secret không cần thiết |
| Logging sink lỗi | Không gây recursion và rò context |
| Parent request kết thúc | Child có ownership/lifetime rõ |
| Direct/proxy calls | Biết lời gọi nào thực sự có advice |

### 12.1 Kiểm thử thứ tự không cần dựa vào scheduler

Dùng `Future.get()` hoặc cơ chế phối hợp task giúp assert **kết quả sau khi hoàn tất**, không đòi log từ T1/T2 phải in cùng thứ tự ở mọi máy. Với concurrency test, chú trọng:
- Giá trị context tại worker đúng với snapshot lúc submission.
- Không có context sau khi rời scope.
- Không có cross-request contamination.
- Những bất biến concurrency/security luôn đúng.

### 12.2 Thử trường hợp thất bại, không chỉ happy path

Một số bug chỉ xuất hiện ở nhánh lỗi:
- Callback làm exception rồi quên clear.
- Task bị interrupt khi đang chờ I/O.
- Retry tạo task mới từ worker nhưng không mang context đúng.
- Logging sink ném lỗi làm advice bỏ qua `finally` không đúng.
- Async stage hoàn tất exceptional nhưng audit chỉ gắn vào success path.

Đặt cleanup trong `finally` của phạm vi đã cài context, không chỉ ở sau lệnh `return` của nhánh thành công.

## 13. Reentrancy, pointcut và scope của advice

Một aspect có thể tự kích hoạt khi code truyền context gọi API helper cũng bị pointcut chọn. Ví dụ:

~~~text
Business call
    -> Advice captures context
        -> Logger/TaskWrapper helper
            -> Pointcut cũng chọn helper
                -> Advice captures context again
                    -> ...
~~~

Đây là vấn đề **reentrancy/cycle**, không phải do ThreadLocal thiếu visibility. Sửa bằng:
- Chọn pointcut có phạm vi nghiệp vụ rõ.
- Loại helper/infrastructure nội bộ khỏi concern quan sát chung khi được phép.
- Tách kênh event/sink theo dependency một chiều.
- Không tạo wrapper lặp không có điều kiện dừng.
- Kiểm thử recursion/stack depth, không cố chữa bằng global boolean dùng chung.

Nếu phải dùng reentrancy guard, chọn scope đúng, restore trong finally và **không dùng để bỏ qua security/audit bắt buộc**.

### 13.1 Bỏ qua proxy khác với mất context

Khi caller giữ target gốc và gọi trực tiếp, advice trên proxy có thể không chạy. Khi advice có chạy nhưng task được gửi không bọc, worker có thể mất context. Hai nguyên nhân khác nhau:
1. **Advice không được kích hoạt tại boundary.**
2. **Advice đã kích hoạt nhưng không thực hiện propagation tới boundary tiếp theo.**

Muốn chẩn đoán chính xác, ghi sự kiện tối thiểu tại **submission intercept** và **worker execution**; không chỉ xem log nghiệp vụ của một task.

## 14. An toàn đa luồng của shared aspect

Một aspect instance dùng chung có thể đồng thời chuẩn bị tasks của request A/B. Sai lầm:

~~~text
sharedAspect.currentContext = contextA
submit(taskA)

sharedAspect.currentContext = contextB
submit(taskB)

taskA reads sharedAspect.currentContext  // có thể thành B
~~~

Không dùng field mutable chung làm chỗ giữ request-specific snapshot. Một wrapper `Callable` được tạo cho từng submission và capture **final/effectively final reference tới immutable snapshot** là cách đơn giản, tách A/B tự nhiên.

Nếu context chứa mutable map dù reference final, cả hai child vẫn có thể sửa nó. Dùng immutable copy hoặc xác định synchronization/ownership.

### 14.1 Policy cập nhật lúc request đang chạy

Cấu hình AOP có thể đổi động. Snapshot context A tại submission không tự bao gồm policy mới nhất khi task chạy sau một giờ. Phải xác định:
- Field nào được snapshot để giữ consistency **một logical operation**.
- Field nào phải **đọc lại khi execute** vì quyền, rate limit hoặc safety.
- Có cần policy version hoặc expiry trong context không?
- Nếu operation bị revoke, tác vụ queued có phải bị hủy?

Đây là quyết định **ngữ nghĩa nghiệp vụ**, không phải chỉ chọn `AtomicReference` hay ThreadLocal.

### 14.2 Nhiều process

ThreadLocal và object context trong JVM không đi qua process/network. Với message queue, phải serialize metadata tối thiểu trong envelope, validate ở consumer và kết hợp trusted authentication theo giao thức. Đừng coi trace baggage do người gửi tự khai là authority.

## 15. Hiệu năng và vòng đời

Mỗi task wrapper/context snapshot có chi phí:
- Tạo wrapper và snapshot.
- Set/remove ThreadLocal hoặc cài context theo cơ chế tương đương.
- Quản lý queue, callback, retention.
- Gắn span/event tại các boundary.
- Tăng nguy cơ memory leak nếu closure giữ object lớn.

Thường chi phí này nhỏ so với I/O của tác vụ, nhưng không thể khẳng định “miễn phí”. Với rất nhiều tasks nhỏ, nên đo overhead thực tế và chỉ propagate **field cần thiết**.

Một tác vụ queued có thể nằm rất lâu trước khi thực thi. Nếu closure giữ reference tới request object, response stream, user entity lớn hoặc session, request không được GC đúng lúc. Thay vào đó lưu **ID/context nhỏ có TTL và ownership rõ**, đóng resource riêng trước khi trả về.

### 15.1 Context lifetime khác task lifetime

Có các thời điểm:
1. Request nhận vào.
2. Tác vụ được scheduling.
3. Caller request trả response.
4. Tác vụ mới bắt đầu chạy.
5. Tác vụ hoàn tất/hủy.

Nếu task chạy ở (4) sau (3), vẫn cần biết nó có quyền làm việc **sau khi request hoàn tất** không. Với audit/notification nền có ownership riêng, điều đó có thể hợp lệ; với thao tác yêu cầu transaction/request-bound resource, có thể không. Context propagation là cơ chế truyền dữ liệu, **không quyết định chính sách sống còn của tác vụ**.

## 16. Những ngộ nhận cần tránh

1. **“ThreadLocal của caller tự sang mọi executor worker.”** Không.
2. **“Một request luôn chạy trên một thread.”** Async có thể chuyển thread.
3. **“Thread pool luôn tạo thread mới cho request.”** Pool thường tái sử dụng thread.
4. **“Chỉ set context trên worker, không cần clear.”** Có nguy cơ rò sang task tiếp theo.
5. **“Clear về null là đủ cho mọi scope.”** Nested scope cần restore previous.
6. **“Copy toàn bộ request object là nhanh nhất.”** Có thể vi phạm lifetime, thread safety và privacy.
7. **“Trace ID chứng minh user đã đăng nhập.”** Không, đây là metadata tương quan.
8. **“Tenant ID từ baggage đủ để phân quyền.”** Không, cần trusted identity/policy.
9. **“Bọc task đầu tiên là mọi callback đều có context.”** Không, mỗi async stage có boundary riêng.
10. **“After-returning của method trả Future báo tác vụ đã thành công.”** Không mặc định.
11. **“`cancel(true)` luôn dừng task tức thì.”** Không bảo đảm.
12. **“`InheritableThreadLocal` giải quyết thread pools.”** Không phù hợp mặc định với worker tái sử dụng và lifecycle riêng.
13. **“Stateless aspect không cần lo context.”** Nó vẫn có thể gọi dependency cần dữ liệu của invocation.
14. **“Đặt context vào shared aspect field để child đọc.”** Có race/cross-request contamination.
15. **“Mọi async lỗi đều xuất hiện ở thread submit.”** Thường được biểu diễn qua Future/Stage completion.
16. **“Cứ truyền transaction connection qua thread khác.”** Không an toàn nếu thiếu hợp đồng transaction/resource cụ thể.
17. **“Context truyền tới worker đồng nghĩa được cấp quyền.”** Propagation không phải authorization.
18. **“Chỉ cần log thấy một trace ID là chứng minh đúng.”** Phải kiểm tra trace đúng request và không rò sang task khác.
19. **“Dùng `finally` ở caller đủ dọn worker.”** Hai thread có scopes độc lập.
20. **“Tăng context fields không có chi phí.”** Có overhead, retention và nguy cơ truyền bí mật.

## 17. Checklist triển khai AOP async propagation

- [ ] Xác định những **join point** và boundary thật cần capture/activate context.
- [ ] Phân biệt **submission** và **execution** trên thread khác.
- [ ] Thiết kế **minimal immutable context** với field được phê duyệt.
- [ ] Không coi correlation ID là security identity.
- [ ] Capture ở thời điểm scheduling đúng logical operation.
- [ ] Bọc `Runnable`/`Callable`/callback/stage phù hợp; không giả định tự truyền.
- [ ] Set context tại worker và restore previous trong `finally`.
- [ ] Xóa ThreadLocal khi không có previous; tránh thread pool leak.
- [ ] Kiểm tra nested scope, fan-out/fan-in và callback ở thread khác.
- [ ] Định nghĩa outcome của Future/Stage tách với return đồng bộ.
- [ ] Kiểm tra ngoại lệ, cancellation, timeout, retry, interruption.
- [ ] Không truyền transaction/resource thread-bound khi chưa được hỗ trợ.
- [ ] Với identity/tenant, lấy từ nguồn đáng tin và kiểm tra policy khi cần.
- [ ] Có expiry, revocation và ownership cho queued/background task.
- [ ] Chỉ serialize metadata được phép khi qua network/message queue.
- [ ] Test worker reuse: task không context không thấy dữ liệu task trước.
- [ ] Tránh shared mutable currentContext field trong aspect.
- [ ] Kiểm tra pointcut không tự chọn helper/sink gây reentrancy.
- [ ] Giới hạn baggage, size, retention và dữ liệu nhạy cảm.
- [ ] Test coverage: task qua proxy/advice và direct/bypass paths.
- [ ] Đo chi phí context wrappers, logging, metrics và memory.
- [ ] Viết regression test cho đúng context của từng invocation.

## 18. Bài tập tự kiểm tra

**Câu 1.** Caller đặt trace A trong ThreadLocal, submit một Callable thô vào thread pool. Worker có chắc thấy A không?

**Đáp:** không. ThreadLocal thuộc thread; muốn worker thấy A phải propagate qua boundary bằng cơ chế được thiết kế.

**Câu 2.** Task A cài context A lên worker rồi ném ngoại lệ. Nếu không cleanup, task B trên cùng worker có thể gặp gì?

**Đáp:** B có thể thấy context A còn sót, gây sai tracing hoặc lộ thông tin giữa request. Cần restore/remove trong finally.

**Câu 3.** Tại sao phải capture lúc submit thay vì đọc ThreadLocal khi worker bắt đầu?

**Đáp:** lúc worker bắt đầu, context trong thread worker có thể null hoặc thuộc task khác; snapshot của logical operation phải được chuyển từ caller qua task wrapper/metadata.

**Câu 4.** Vì sao `restore previous` an toàn hơn luôn `remove` cho nested scope?

**Đáp:** nếu một scope ngoài đang có context P, scope con A phải trả quyền điều khiển với context P; remove sẽ xóa cả ngữ cảnh hợp lệ của scope ngoài.

**Câu 5.** Có thể dùng traceId làm khóa kiểm tra quyền thay cho principal được xác thực không?

**Đáp:** không. TraceId là metadata tương quan, có thể bị giả mạo. Authorization phải dựa vào nguồn nhận dạng và policy đáng tin.

**Câu 6.** Một method AOP trả `CompletionStage`; `after-returning` của lời gọi chạy ngay khi trả stage. Nó đã đo đúng thời điểm task hoàn tất chưa?

**Đáp:** chưa chắc. Muốn đo completion phải gắn quan sát vào điểm kết thúc stage, phân biệt success, exception và cancellation.

**Câu 7.** Nếu một task gốc fan-out sang ba tasks trên executor khác, chỉ truyền context ở task gốc có đủ không?

**Đáp:** không mặc định. Cần cơ chế propagation có chủ đích tại từng boundary cần context, tạo ngữ nghĩa parent/child phù hợp.

**Câu 8.** Có nên gửi toàn bộ access token và raw request object vào tracing baggage qua hệ thống từ xa?

**Đáp:** không. Chỉ truyền metadata tối thiểu theo allowlist; authority phải được xác minh bằng giao thức bảo mật riêng.

**Câu 9.** Trong Java demo, tại sao `POST` in `trace=none` ngay sau task lỗi?

**Đáp:** `ContextScope.with` dọn context trong `finally`, nên worker không giữ A cho task kế tiếp dù task trước ném lỗi.

**Câu 10.** Một shared aspect dùng field `currentContext` để các task đọc sau. Tại sao nguy hiểm?

**Đáp:** nhiều invocations concurrent có thể ghi đè field; task A đọc context B. Capture snapshot riêng và immutable cho từng submission.

## 19. Kết luận

**Truyền ngữ cảnh qua tác vụ bất đồng bộ có kiểm soát** là bài toán **phạm vi và vòng đời của dữ liệu theo logical operation**, không chỉ là “đặt ThreadLocal”.

Một thiết kế đúng phải:
1. **Capture** dữ liệu tối thiểu, đã được phép, tại ranh giới scheduling.
2. **Propagate** snapshot qua task/callback bằng hợp đồng rõ ràng.
3. **Activate** ở worker khi tác vụ thực sự chạy.
4. **Restore/clear** chính xác trong `finally`, kể cả nested và exception paths.
5. **Phân biệt tracing với security**, đồng bộ với bất đồng bộ, stage return với completion, local thread với process khác.
6. **Kiểm thử không rò ngữ cảnh**, cùng với correctness, authorization, timeout, cancellation và retention.

Ghi nhớ: **AOP giúp tách concern truyền context ra khỏi nghiệp vụ**, nhưng chỉ an toàn khi mọi boundary được chọn và mọi dữ liệu được truyền **có scope, ownership, quyền truy cập và cơ chế cleanup rõ ràng**.
