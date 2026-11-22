# Luồng hoàn tất và ngữ cảnh chạy bước tiếp theo trong CompletableFuture

## 1. Mục tiêu bài học

Trong Java, CompletableFuture mô tả một **kết quả sẽ có trong tương lai** và cho phép đăng ký các bước xử lý phụ thuộc. Nhưng **một CompletableFuture không sở hữu một thread cố định**. Câu hỏi “callback thenApply chạy ở thread nào?” phụ thuộc vào trạng thái hoàn tất của upstream, thời điểm đăng ký, loại phương thức non-async/Async và Executor.

Bài này thuộc chủ đề **CompletableFuture**, giải thích đúng hai việc:

- **Luồng hoàn tất**: thread khiến một stage hoàn tất, ví dụ gọi complete hoặc thực thi Supplier trong supplyAsync.
- **Ngữ cảnh chạy bước tiếp theo**: thread/Executor, ThreadLocal, request/MDC/security context có mặt khi callback phụ thuộc được thực thi.

Các nguyên tắc cốt lõi của CompletableFuture trong Java 8 **vẫn còn áp dụng hiện nay**. Sáu ví dụ Java độc lập trong bài được biên dịch và chạy bằng Java 17, kiểm thử stdout thay vì phỏng đoán theo lịch chạy.

Sau bài học, bạn có thể giải thích chính xác việc thực thi callback non-async, các biến thể Async/default executor/custom executor, trường hợp source đã hoàn tất, cách chờ dependent stage, truyền ngữ cảnh ThreadLocal, xử lý lỗi, compose và combine, tránh block/ deadlock, và chọn pool phù hợp với workload.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Không nên giả định |
|---|---|---|
| CompletableFuture<T> | Kết quả có thể hoàn tất bình thường hoặc bất thường | Có một thread sở hữu suốt đời |
| CompletionStage<T> | Mô hình quan hệ phụ thuộc giữa các giai đoạn | Mỗi giai đoạn tự sinh một thread |
| Completion | Trạng thái chuyển sang có kết quả hoặc lỗi | Tất cả callback đã kết thúc khi root hoàn tất |
| Dependent action | Function, Consumer hoặc Runnable chạy khi điều kiện phụ thuộc đáp ứng | Được chạy ở thread đăng ký |
| Non-async | thenApply, thenAccept, thenRun, thenCompose, handle... | Luôn chạy ở main hoặc pool cụ thể |
| Async | thenApplyAsync và các phương thức tương tự | Bắt buộc tạo một thread mới |
| Executor | Cách gửi, queue, thực thi Runnable | Chắc chắn chạy ở một thread khác |
| Execution context | ThreadLocal, MDC, trace/tenant, security/transaction context | Tự đi theo CompletableFuture qua mọi thread |

**Stage hoàn tất** và **dependent action hoàn tất** là hai sự kiện có thể khác nhau. Với pipeline có bước Async hoặc stage phụ thuộc nhiều nguồn, root.isDone() chưa đủ để biết toàn bộ xử lý đã xong.

## 3. Non-async continuation chạy ở thread nào?

Oracle JavaDoc của CompletableFuture nêu rằng các action dependent completion **không-async** có thể được chạy bởi **thread hoàn tất CompletableFuture hiện tại**, hoặc bởi **một caller khác của phương thức completion**.

Ví dụ:

~~~java
// Mảnh mã; cần import java.util.concurrent.*.
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<String> downstream = source.thenApply(
        data -> data.toUpperCase());

source.complete("ready");
~~~

Nếu downstream đã được đăng ký trước khi source hoàn tất, trong một luồng điều khiển đơn giản, thread gọi source.complete có thể thực thi callback. Nếu callback làm việc nặng hoặc block, lệnh complete có thể phải mất thời gian chạy callback trước khi quay về.

Nếu source **đã hoàn tất trước khi đăng ký**, phương thức thenApply có thể thực thi callback **ngay trên thread đang đăng ký**. Đây là hành vi thông dụng của OpenJDK, nhưng JavaDoc **không bảo đảm một thread identity cố định** cho mọi continuation non-async.

Không nên viết logic đòi callback phải chạy trên một thread cụ thể. Cần tránh phụ thuộc vào trạng thái thread-local, một transaction gắn thread, hoặc một event loop khi không kiểm soát được đường completion.

### Đăng ký trước và đăng ký sau completion

~~~text
Trường hợp A:              Trường hợp B:
main đăng ký thenApply     worker đã complete(source)
thread worker complete     main đăng ký thenApply
callback có thể chạy       callback có thể chạy
trong worker               ngay trong main

Cùng API thenApply, nhưng execution context khác.
~~~

Phần quan trọng là **may**, không phải **must**. JavaDoc không cấp thread affinity cho continuation non-async. Trong tình huống đua giữa nhiều caller, behavior có thể thay đổi và chỉ có thể dựa vào các điều kiện hoàn tất do API bảo đảm.

## 4. Ví dụ chạy được 1 — callback trước và sau completion

Tạo file **CompletionThreadDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class CompletionThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> early = source.thenApply(
                text -> Thread.currentThread().getName() + ":" + text.toUpperCase());
        Thread completer = new Thread(
                () -> source.complete("ready"), "completer-thread");
        completer.start();
        completer.join();
        System.out.println("early=" + early.join());
        AtomicReference<String> lateOutput = new AtomicReference<>();
        Thread registrant = new Thread(() -> {
            lateOutput.set(source.thenApply(text ->
                    Thread.currentThread().getName() + ":" + text).join());
        }, "registrant-thread");
        registrant.start();
        registrant.join();
        System.out.println("late=" + lateOutput.get());
        System.out.println("source=" + source.join());
    }
}
~~~

Chạy:

~~~text
javac --release 17 CompletionThreadDemo.java
java CompletionThreadDemo
~~~

Stdout trên Java 17 đã kiểm thử:

~~~text
early=completer-thread:READY
late=registrant-thread:ready
source=ready
~~~

**Giải thích:** early được đăng ký lúc source chưa có kết quả; trong tình huống này callback chạy trên completer-thread. late được đăng ký từ registrant-thread **sau** khi source đã hoàn tất; callback chạy ngay trên thread đăng ký. Hai thread được đặt tên và thứ tự đăng ký được kiểm soát nên có thể quan sát rõ. **Đây không phải cam kết chung rằng callback non-async luôn chạy trên đúng hai thread này** trong mọi triển khai.

### Một lời gọi complete có phải chờ cả pipeline?

Không được suy luận rằng complete(source) trả về nghĩa là mọi dependent stage bất kỳ đã kết thúc. Một stage Async có thể vẫn ở queue, một thenCombine có thể còn chờ upstream thứ hai, hoặc một thenCompose có thể chờ inner stage. Hãy **join/get trên future của bước kết quả**, hoặc allOf nhận chính những dependent futures cần chờ.

## 5. Phân biệt các biến thể thenApply

### thenApply(fn) — non-async

~~~java
// Mảnh mã.
CompletableFuture<Integer> length =
        source.thenApply(String::length);
~~~

Callback được kích hoạt khi source hoàn tất **bình thường**, nhưng không có Executor riêng được chỉ định. Nó có thể chạy trên thread hoàn tất hoặc một caller completion khác theo contract. Không thích hợp để ép một thread cố định.

### thenApplyAsync(fn) — default async executor

~~~java
// Mảnh mã.
CompletableFuture<Integer> length =
        source.thenApplyAsync(String::length);
~~~

Với **CompletableFuture chuẩn**, phương thức Async không truyền Executor sử dụng **ForkJoinPool.commonPool()**. Nếu common pool không hỗ trợ parallelism ít nhất 2, Javadoc cho phép tạo một Thread mới cho mỗi tác vụ. Tên thread, số worker, thời điểm bắt đầu và chính sách scheduling không phải thứ bạn nên hardcode.

Kể từ Java 9, subclass có thể override defaultExecutor() cho các phương thức instance Async, nên không được coi mọi future trong hệ thống đều dùng cùng một default pool nếu đang dùng subclass.

### thenApplyAsync(fn, executor) — Executor được cung cấp

~~~java
// Mảnh mã.
CompletableFuture<Integer> length =
        source.thenApplyAsync(String::length, businessExecutor);
~~~

Cách này cho phép ứng dụng điều khiển thread pool, queue, số worker, chính sách từ chối và lifecycle. Tuy nhiên Executor là **interface về thực thi Runnable**, không phải lời hứa rằng task chắc chắn chạy trên một thread khác.

### Async không đồng nghĩa new Thread

~~~java
// Mảnh mã minh họa direct Executor.
Executor direct = Runnable::run;
CompletableFuture<String> done =
        CompletableFuture.completedFuture("x");

CompletableFuture<String> value = done.thenApplyAsync(
        text -> Thread.currentThread().getName() + ":" + text,
        direct);
~~~

Nếu thực thi từ main, direct Executor chạy Runnable ngay trong main. Thậm chí một ThreadPoolExecutor được cấu hình CallerRunsPolicy có thể thực thi task trên caller thread khi saturation. Vì vậy, **Async diễn đạt cơ chế gửi task**, chứ không cam kết một thread vật lý mới hay luôn khác thread đăng ký.

## 6. Các phương thức tương ứng

| Non-async | Async mặc định | Async dùng Executor |
|---|---|---|
| thenApply(fn) | thenApplyAsync(fn) | thenApplyAsync(fn, ex) |
| thenAccept(fn) | thenAcceptAsync(fn) | thenAcceptAsync(fn, ex) |
| thenRun(action) | thenRunAsync(action) | thenRunAsync(action, ex) |
| thenCompose(fn) | thenComposeAsync(fn) | thenComposeAsync(fn, ex) |
| thenCombine(other, fn) | thenCombineAsync(other, fn) | thenCombineAsync(other, fn, ex) |
| handle(fn) | handleAsync(fn) | handleAsync(fn, ex) |
| whenComplete(action) | whenCompleteAsync(action) | whenCompleteAsync(action, ex) |

Phải chọn đúng **ngữ nghĩa** trước rồi mới chọn cách scheduling:

- thenApply: biến T thành U, chỉ khi upstream thành công.
- thenAccept: tiêu thụ kết quả T, trả stage Void.
- thenRun: thực hiện Runnable không nhận giá trị T.
- thenCompose: hàm trả CompletionStage<U>, flatten future lồng.
- thenCombine: đợi cả hai upstream hoàn tất bình thường và kết hợp giá trị.
- handle: xử lý cả thành công/lỗi và có thể đổi outcome.
- whenComplete: quan sát kết quả/lỗi, thường giữ outcome ban đầu.

Hậu tố Async không tự thay đổi quy tắc nghiệp vụ của callback, mà thay đổi cách nó được gửi để thực thi.
## 7. Ví dụ chạy được 2 — Executor, pipeline và direct Executor

Tạo file **ExecutorSelectionDemo.java**:

~~~java
import java.util.concurrent.*;

public class ExecutorSelectionDemo {
    private static ExecutorService namedPool(String name) {
        return Executors.newSingleThreadExecutor(r -> new Thread(r, name));
    }

    public static void main(String[] args) {
        ExecutorService pool = namedPool("business-executor");
        try {
            CompletableFuture<String> source = new CompletableFuture<>();
            CompletableFuture<String> chain = source
                    .thenApplyAsync(v -> Thread.currentThread().getName()
                            + ":" + v.toUpperCase(), pool)
                    .thenApply(v -> Thread.currentThread().getName() + "|" + v);
            source.complete("hello");
            System.out.println("chain=" + chain.join());

            Executor direct = Runnable::run;
            String inline = CompletableFuture.completedFuture("x")
                    .thenApplyAsync(v ->
                            Thread.currentThread().getName() + ":" + v, direct)
                    .join();
            System.out.println("direct=" + inline);

            String defaultAsync = CompletableFuture.completedFuture(10)
                    .thenApplyAsync(n -> "result=" + (n + 2))
                    .join();
            System.out.println("defaultAsync=" + defaultAsync);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 ExecutorSelectionDemo.java
java ExecutorSelectionDemo
~~~

Stdout:

~~~text
chain=business-executor|business-executor:HELLO
direct=main:x
defaultAsync=result=12
~~~

**Giải thích:**

1. Stage thenApplyAsync đầu tiên được gửi vào business-executor. Trong demo, nó chạy trên một worker có tên từ ThreadFactory.
2. thenApply **không-async** tiếp theo cũng chạy trong worker đó **trong lần thực thi này**, vì worker làm stage trước hoàn tất. Không xem đây là ràng buộc thread affinity.
3. thenApplyAsync với Executor trực tiếp chạy ngay trong main, cho **direct=main:x**.
4. thenApplyAsync không truyền Executor trả kết quả 12. Demo cố tình **không in tên thread mặc định** vì môi trường JDK/common pool có thể khác nhau.
5. finally gọi shutdown để bảo đảm pool không bị bỏ quên. Trong ứng dụng thực, pool thường do service container hoặc một thành phần cấp cao sở hữu; không tạo và đóng pool riêng cho từng request.

### Chain có thuộc một thread từ đầu đến cuối không?

Không. Một stage non-async có thể tiếp tục trên worker vừa hoàn tất stage trước, nhưng nếu một stage được hoàn tất bởi thread khác, hoặc thêm Async boundary, execution context có thể thay đổi. Một chuỗi nhiều future **không giống một function call đồng bộ trên một thread**. Khi cần phân vùng workload rõ ràng, sử dụng overload Async với Executor ở điểm cần điều khiển.

## 8. supplyAsync, runAsync và luồng tạo công việc

~~~java
// Mảnh mã; loadData và transform là hàm nghiệp vụ tự định nghĩa.
CompletableFuture<String> loaded =
        CompletableFuture.supplyAsync(() -> loadData(), ioExecutor);

CompletableFuture<String> transformed =
        loaded.thenApply(value -> transform(value));
~~~

- supplyAsync chạy Supplier theo executor và hoàn tất với giá trị.
- runAsync chạy Runnable theo executor và hoàn tất CompletableFuture<Void>.
- Tạo future trên main **không** có nghĩa Supplier thực thi trên main.
- Một callback non-async gắn trước khi loaded hoàn tất có thể chạy ngay trên thread hoàn tất Supplier.
- Nếu callback được gắn sau completion, nó có thể chạy inline trên caller đăng ký.
- Nếu transform nặng hoặc blocking, cân nhắc thenApplyAsync(transform, processingExecutor) để không vô tình giữ worker I/O.

Không mặc định một Executor dùng chung phù hợp cho mọi việc. Common pool là tài nguyên toàn JVM được nhiều thư viện và module dùng; những task ngắn CPU-oriented có thể phù hợp, nhưng blocking I/O kéo dài hoặc quá nhiều task chờ có thể làm worker bị khan hiếm. Với I/O đồng bộ có thể chặn thread, dùng executor riêng và giới hạn concurrency/queue; cân nhắc API I/O bất đồng bộ thực sự nếu có.

### Tại sao không tạo Executor cho từng stage?

Việc tạo ExecutorService mới cho mỗi thenApplyAsync hoặc mỗi request có thể gây tăng số thread ngoài kiểm soát và rò rỉ tài nguyên. Executor nên có **lifecycle**, giới hạn tải, chính sách shutdown và cơ chế giám sát rõ. Cần phân biệt công việc **CPU-bound** (xử lý tính toán) với **I/O-bound** (chờ DB/network/file).

## 9. ThreadLocal, MDC và request context không tự đi theo Future

Một continuation thường cần nhiều thứ hơn giá trị T:

- Trace ID, correlation ID hoặc request ID.
- Tenant ID, user context, principal đã xác thực.
- Logging MDC, span/observation tracing context.
- Locale, ZoneId hoặc cấu hình business.
- Transaction/session context.
- Các ThreadLocal do code ứng dụng hoặc framework sở hữu.

**CompletableFuture không hứa tự động chuyển mọi giá trị thread-bound sang thread sẽ thực thi continuation.** ThreadLocal giữ dữ liệu theo từng thread. Khi bạn chuyển sang executor worker, TRACE.get() trên worker có thể là null hoặc một giá trị khác.

~~~java
// Mảnh mã, TRACE là ThreadLocal<String>.
TRACE.set("req-42");
CompletableFuture<String> traced =
        CompletableFuture.completedFuture("task")
                .thenApplyAsync(x -> TRACE.get(), executor);
~~~

Nếu executor dùng một worker riêng, kết quả có thể null. Nếu dùng direct Executor, kết quả có thể là req-42. **Việc sử dụng Async hoặc non-async không tự định nghĩa cơ chế propagation.**

### Vấn đề khi dùng InheritableThreadLocal

InheritableThreadLocal có thể thừa hưởng dữ liệu khi một thread mới được tạo, nhưng worker của thread pool **được tái sử dụng**. Nó có thể được tạo trước request và phục vụ nhiều request khác nhau. Vì vậy, inheritance lúc tạo thread không bảo đảm đúng dữ liệu cho từng task; thậm chí có nguy cơ giữ lại ngữ cảnh của request cũ.

Trong ứng dụng đa tenant, sai request context không chỉ làm log khó theo dõi mà còn có thể dẫn đến lỗi cô lập tài nguyên hoặc kiểm soát quyền. Không đọc tenant/principal từ một ThreadLocal tùy ý khi đang chạy continuation trên pool tái sử dụng.

## 10. Truyền ngữ cảnh an toàn: tham số bất biến hoặc snapshot/restore

**Ưu tiên** truyền rõ những dữ liệu business cần dùng qua tham số:

~~~java
// Mảnh mã, cần định nghĩa hàm process ở ứng dụng thực.
record RequestContext(String traceId, String tenantId) {}

RequestContext context = new RequestContext("req-42", "tenant-A");
CompletableFuture<String> next =
        source.thenApplyAsync(v -> process(v, context), executor);
~~~

Một value object immutable làm phụ thuộc trở nên tường minh và dễ test, không yêu cầu callback chạy trên thread cụ thể.

**Nếu framework cần ThreadLocal hoặc MDC**, phải capture ở đúng thời điểm, thiết lập context tạm thời trên worker và restore/clear trong finally:

~~~java
// Mảnh mã, TRACE là ThreadLocal<String>, useTrace là hàm nghiệp vụ.
String snapshot = TRACE.get();

CompletableFuture<String> next = source.thenApplyAsync(v -> {
    String previous = TRACE.get();
    try {
        if (snapshot == null) TRACE.remove();
        else TRACE.set(snapshot);
        return useTrace(v);
    } finally {
        if (previous == null) TRACE.remove();
        else TRACE.set(previous);
    }
}, executor);
~~~

Tại sao restore/clear bắt buộc?

- Thread pool tái sử dụng worker cho request khác.
- Nếu callback ném exception mà không finally, context có thể còn nằm trên worker.
- Nếu task đã có context trước đó, cần trả nó về đúng trạng thái ban đầu thay vì xóa tùy tiện.
- Phải capture context đúng request, không lấy một object mutable có thể bị thay đổi từ thread khác.

### Không copy transaction context tùy tiện

Transaction, JDBC connection, security/session context hoặc request-scoped object có thể có lifecycle và thread-bound resource riêng. Copy một ThreadLocal không biến chúng thành thread-safe và không bảo đảm transaction còn hợp lệ. Hãy tuân theo hợp đồng của framework; nếu dùng thư viện hỗ trợ context propagation đang được duy trì, kích hoạt nó ở boundary đúng.

## 11. Ví dụ chạy được 3 — ThreadLocal trên worker và khôi phục context

Tạo file **ThreadLocalContextDemo.java**:

~~~java
import java.util.concurrent.*;

public class ThreadLocalContextDemo {
    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

    private static String withTrace(String snapshot, java.util.function.Supplier<String> work) {
        String previous = TRACE.get();
        try {
            if (snapshot == null) TRACE.remove();
            else TRACE.set(snapshot);
            return work.get();
        } finally {
            if (previous == null) TRACE.remove();
            else TRACE.set(previous);
        }
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "context-worker"));
        try {
            TRACE.set("req-42");
            String snapshot = TRACE.get();
            String without = CompletableFuture.completedFuture("task")
                    .thenApplyAsync(v -> String.valueOf(TRACE.get()), pool).join();
            String with = CompletableFuture.completedFuture("task")
                    .thenApplyAsync(v -> withTrace(snapshot, () -> TRACE.get()), pool)
                    .join();
            String after = CompletableFuture.completedFuture("task")
                    .thenApplyAsync(v -> String.valueOf(TRACE.get()), pool).join();

            System.out.println("caller=" + TRACE.get());
            System.out.println("without=" + without);
            System.out.println("with=" + with);
            System.out.println("after=" + after);
        } finally {
            TRACE.remove();
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 ThreadLocalContextDemo.java
java ThreadLocalContextDemo
~~~

Stdout:

~~~text
caller=req-42
without=null
with=req-42
after=null
~~~

**Phân tích:** Main có req-42. Worker context-worker là thread khác nên không tự có TRACE của main. Callback được bọc bằng withTrace chụp snapshot req-42 và dùng nó tạm thời; finally restore giá trị cũ, nên callback sau thấy null. Worker không sửa ThreadLocal của main. Đây là demo với một ThreadLocal đơn giản; MDC, security context và tracing context thực tế cần dùng propagation phù hợp framework và không tự “copy tất cả ThreadLocal”.

### Submission context khác execution context

- **Registration/submission context**: môi trường đang có khi callback được đăng ký hoặc gửi tới executor.
- **Execution context**: môi trường đang có ở thread thật sự chạy callback.
- **Business context**: dữ liệu nghiệp vụ của request, nên tồn tại ổn định bất kể scheduler.

Hai context đầu có thể khác nhau. Không dựa vào suy luận “non-async chắc chắn có context, Async chắc chắn không có context”; không có lời hứa đó trong contract của CompletableFuture.
## 12. Async boundary: có thể xếp hàng chứ không chạy ngay

Một stage upstream đã hoàn tất không có nghĩa continuation Async đã chạy. Nếu Executor đang bận, continuation có thể chờ trong queue.

~~~java
// Mảnh mã.
CompletableFuture<String> queued =
        CompletableFuture.completedFuture("A")
                .thenApplyAsync(String::toLowerCase, executor);
~~~

Nếu executor chỉ có một worker và worker đang bị chặn, queued không thể chạy trước khi worker trống. Vì vậy:

- **Upstream complete**: dữ liệu đầu vào đã sẵn sàng.
- **Continuation scheduled**: công việc đã được chuyển đến Executor theo chính sách của Executor.
- **Continuation executing**: worker/caller bắt đầu chạy lambda.
- **Dependent stage complete**: lambda kết thúc bình thường hoặc bất thường, giá trị/lỗi được công bố.

Các thời điểm này không nhất thiết trùng nhau. Thời gian chờ queue là một phần của **end-to-end latency**. Nếu đo chỉ thời gian trong callback, bạn bỏ sót latency trong queue.

### Async không bảo đảm làm được ngay

Executor có thể bận, giới hạn queue, từ chối task hoặc dùng policy chạy caller. Cần định nghĩa chính sách khi quá tải, đặc biệt cho API có SLA. Đừng dùng isDone ngay sau khi tạo stage để kết luận hệ thống “chạy không được”; trạng thái pending có thể bình thường.

## 13. Ví dụ chạy được 4 — chờ trong queue của single-thread Executor

Tạo file **QueueHandoffDemo.java**:

~~~java
import java.util.concurrent.*;

public class QueueHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "queue-worker"));
        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            CompletableFuture<Void> blocking = CompletableFuture.runAsync(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
            }, pool);
            running.await();
            CompletableFuture<String> queued = CompletableFuture.completedFuture("A")
                    .thenApplyAsync(v -> Thread.currentThread().getName() + ":" + v, pool);
            System.out.println("queuedDoneBeforeRelease=" + queued.isDone());
            release.countDown();
            System.out.println("queuedValue=" + queued.join());
            blocking.join();
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 QueueHandoffDemo.java
java QueueHandoffDemo
~~~

Stdout:

~~~text
queuedDoneBeforeRelease=false
queuedValue=queue-worker:A
~~~

**Vì sao stdout xác định trong ví dụ này?**

1. Single-thread Executor chỉ có một worker.
2. Task đầu bắt đầu chạy, báo running và chờ release.
3. Main chờ running.await() để chắc chắn worker đã chiếm dụng trước khi đăng ký queued.
4. queued được đưa vào chính pool đang bận, nên chưa hoàn tất trước khi release.
5. Sau release, worker xử lý queued và trả queue-worker:A.
6. finally luôn release latch trước shutdown để tránh kẹt worker khi có exception.

CountDownLatch giúp kiểm soát ordering trong test, thay vì dùng Thread.sleep và hy vọng task đã chạy đúng lúc. Không cố tình block worker vô hạn trong ứng dụng thật; cần queue capacity, timeout và backpressure phù hợp.

## 14. thenCompose: inner stage có thể hoàn tất trong context khác

thenCompose được dùng khi một function trả CompletionStage<U>:

~~~java
// Mảnh mã; fetchAsync trả CompletionStage<Data>.
CompletableFuture<Result> result =
        source.thenCompose(id -> fetchAsync(id))
              .thenApply(data -> transform(data));
~~~

Nếu source hoàn tất trong worker A, function của thenCompose có thể chạy trong worker A. Nhưng inner future do fetchAsync trả về có thể hoàn tất trong worker B. thenApply kế tiếp, nếu non-async, có thể được kích hoạt bởi completion ở worker B. **thenCompose không tự bảo đảm tất cả callback ở cùng thread**, cũng không tự cấp một executor chung cho inner stage.

Nếu muốn transform chạy theo policy riêng, dùng thenApplyAsync(..., processorExecutor).

### thenApply tạo future lồng nếu hàm trả future

~~~java
// Mảnh mã:
CompletableFuture<CompletableFuture<Integer>> nested =
        source.thenApply(n ->
                CompletableFuture.completedFuture(n * 10));

CompletableFuture<Integer> flattened =
        source.thenCompose(n ->
                CompletableFuture.completedFuture(n * 10));
~~~

Cả hai có thể mang cùng giá trị sau cùng nhưng **khác kiểu**. Với nested, bạn cần theo dõi cả outer và inner future để biết kết quả; với thenCompose, stage kết quả đã “flatten” inner stage. Sự khác nhau này liên quan tới **completion dependency**, không phải nghĩa “thenCompose chạy trên thread khác”.

## 15. thenCombine và các stage nhiều nguồn

thenCombine cần cả hai upstream stage hoàn tất bình thường mới chạy hàm kết hợp:

~~~java
// Mảnh mã:
CompletableFuture<Integer> combined =
        first.thenCombine(second, Integer::sum);
~~~

Nếu hai upstream được hoàn tất bởi các worker khác nhau, callback non-async có thể được thực thi bởi thread completion phù hợp theo trạng thái phụ thuộc; nó không phải “luôn chạy trên executor của first” hoặc “luôn chạy trên worker của second”. Nếu cả hai đã hoàn tất trước khi đăng ký, nó có thể chạy inline trong caller đăng ký.

Muốn chọn Executor cho hàm kết hợp, dùng **thenCombineAsync(second, fn, executor)**.

### allOf chỉ chờ đúng các future được truyền vào

~~~java
// Mảnh mã.
CompletableFuture<String> root = CompletableFuture.completedFuture("x");
CompletableFuture<Integer> branch =
        root.thenApplyAsync(String::length, executor);

CompletableFuture.allOf(root);   // Chỉ root.
CompletableFuture.allOf(branch); // Chờ stage branch.
~~~

Lệnh allOf(root) **không tự chờ** dependent branch Async. Một future đầu hoàn tất không có nghĩa toàn bộ đồ thị phụ thuộc hoàn tất. Khi cần chờ tác vụ có side effect hoặc tính toán cuối, đưa đúng future đại diện cho bước đó vào allOf và xử lý kết quả/lỗi của nó.

### Đừng dựa vào thứ tự nhiều dependent callback

Hai nhánh cùng phụ thuộc một source:

~~~java
// Mảnh mã:
CompletableFuture<Integer> a = source.thenApply(x -> x + 1);
CompletableFuture<Integer> b = source.thenApply(x -> x * 2);
~~~

Không nên giả định a luôn được gọi trước b chỉ vì a được đăng ký trước. Khi nghiệp vụ cần **tuần tự**, tạo một chain có dependency thực sự: source.thenApply(...).thenApply(...). Khi nghiệp vụ cần tính toán độc lập, fan-out có thể phù hợp, nhưng phải chờ tất cả các nhánh liên quan và xử lý lỗi.

## 16. Ví dụ chạy được 5 — compose, combine và fan-out

Tạo file **CompositionAndFanoutDemo.java**:

~~~java
import java.util.concurrent.*;

public class CompositionAndFanoutDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "combine-worker"));
        try {
            CompletableFuture<Integer> source = CompletableFuture.completedFuture(3);
            CompletableFuture<CompletableFuture<Integer>> nested =
                    source.thenApply(n -> CompletableFuture.completedFuture(n * 10));
            CompletableFuture<Integer> flat =
                    source.thenCompose(n -> CompletableFuture.completedFuture(n * 10));
            CompletableFuture<String> combined = flat.thenCombineAsync(
                    CompletableFuture.completedFuture(7),
                    (a, b) -> Thread.currentThread().getName() + ":" + (a + b),
                    pool);
            CompletableFuture<Integer> plusOne = source.thenApply(n -> n + 1);
            CompletableFuture<Integer> timesTwo = source.thenApply(n -> n * 2);
            CompletableFuture.allOf(nested, flat, combined, plusOne, timesTwo).join();

            System.out.println("nested=" + nested.join().join());
            System.out.println("flat=" + flat.join());
            System.out.println("combined=" + combined.join());
            System.out.println("plusOne=" + plusOne.join());
            System.out.println("timesTwo=" + timesTwo.join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 CompositionAndFanoutDemo.java
java CompositionAndFanoutDemo
~~~

Stdout:

~~~text
nested=30
flat=30
combined=combine-worker:37
plusOne=4
timesTwo=6
~~~

**Giải thích:**

1. thenApply với function trả CompletableFuture tạo nested future; nested.join().join() giải hai lớp.
2. thenCompose trả flattened stage; flat.join() trả 30.
3. thenCombineAsync với executor riêng chạy hàm cộng trên combine-worker trong ví dụ, tạo chuỗi combine-worker:37.
4. Các nhánh plusOne và timesTwo độc lập, cho 4 và 6; không dùng thứ tự thực thi làm một điều kiện logic.
5. allOf chờ chính các future đã liệt kê, gồm dependent futures quan trọng.
6. Nếu một branch hoàn tất bất thường, allOf cũng có thể hoàn tất bất thường; muốn biết lỗi từng nhánh, phải theo dõi outcome của nhánh đó.

## 17. Khi upstream thất bại thì callback nào chạy?

Một CompletableFuture có thể:

- Hoàn tất bình thường với một giá trị T, kể cả null theo contract.
- Hoàn tất bất thường vì một Throwable.
- Bị cancel; đối với CompletableFuture, cancellation là một dạng exceptional completion.

Các continuation xử lý outcome khác nhau:

| Callback | Khi upstream bình thường | Khi upstream lỗi | Hành động chính |
|---|---|---|---|
| thenApply(fn) | Gọi fn | Không gọi fn | Map dữ liệu |
| thenAccept(fn) | Gọi fn | Không gọi fn | Tiêu thụ giá trị |
| thenRun(action) | Chạy action | Không chạy action | Chạy tác vụ không có input |
| exceptionally(fn) | Không cần fallback | Gọi fn phục hồi lỗi | Trả T thay thế |
| handle(fn) | Gọi fn với value/error | Gọi fn với value/error | Biến đổi outcome |
| whenComplete(action) | Quan sát value | Quan sát error | Side effect quan sát |

### exceptionally: phục hồi lỗi

~~~java
// Mảnh mã:
CompletableFuture<Integer> safe =
        source.exceptionally(ex -> -1);
~~~

Nếu source thất bại, safe có thể hoàn tất bình thường với -1. Không được dùng fallback “giá trị thành công” để che các lỗi bắt buộc phải báo ở biên hệ thống, nhất là lỗi bảo mật hoặc sai dữ liệu.

### handle: xử lý cả hai nhánh và trả kết quả mới

~~~java
// Mảnh mã.
CompletableFuture<String> label =
        source.handle((value, error) ->
                error == null ? "success:" + value : "failure");
~~~

handle có thể trả một kiểu mới U và chuyển cả kết quả thành công hoặc bất thường sang outcome khác.

### whenComplete: quan sát kết quả

~~~java
// Mảnh mã minh họa, logCompletion là hàm nghiệp vụ.
CompletableFuture<Integer> observed =
        source.whenComplete((value, error) ->
                logCompletion(value, error));
~~~

whenComplete thường giữ nguyên kết quả/lỗi upstream; nó **không** được thiết kế làm công cụ phục hồi outcome như handle. Nếu action quan sát tự ném exception, JDK có các quy tắc ưu tiên exception; tốt nhất bảo đảm callback quan sát không vô tình làm hỏng pipeline.

### Context và thread của các callback xử lý lỗi

- exceptionally, handle, whenComplete không-async chịu nguyên tắc thread phụ thuộc completion.
- handleAsync và whenCompleteAsync cho phép gửi việc tới default async facility hoặc Executor rõ ràng.
- exceptionallyAsync được bổ sung từ **Java 12**. Nếu cần tương thích mã nguồn Java 8, không dùng nó mà không đặt yêu cầu phiên bản cụ thể.

**Lưu ý:** Chọn bản Async không thay thế cho việc xử lý exception. Một callback có thể chính nó ném lỗi, làm dependent stage hoàn tất bất thường; cần theo dõi future trả về.
## 18. Ví dụ chạy được 6 — success-only, exceptionally, handle và whenComplete

Tạo file **OutcomeStageDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class OutcomeStageDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        AtomicBoolean successCallbackRan = new AtomicBoolean(false);
        AtomicBoolean sawError = new AtomicBoolean(false);

        CompletableFuture<Integer> successOnly = source.thenApply(n -> {
            successCallbackRan.set(true);
            return n * 2;
        });
        CompletableFuture<Integer> recovered = source.exceptionally(ex -> -1);
        CompletableFuture<String> handled = source.handle((v, ex) ->
                ex == null ? "ok:" + v : "error:handled");
        CompletableFuture<Integer> observed = source.whenComplete(
                (v, ex) -> sawError.set(ex != null));

        source.completeExceptionally(new IllegalArgumentException("bad"));
        System.out.println("successCallbackRan=" + successCallbackRan.get());
        System.out.println("successOnlyExceptional=" + successOnly.isCompletedExceptionally());
        System.out.println("recovered=" + recovered.join());
        System.out.println("handled=" + handled.join());
        System.out.println("whenCompleteSawError=" + sawError.get());
        System.out.println("observedExceptional=" + observed.isCompletedExceptionally());
    }
}
~~~

Chạy:

~~~text
javac --release 17 OutcomeStageDemo.java
java OutcomeStageDemo
~~~

Stdout:

~~~text
successCallbackRan=false
successOnlyExceptional=true
recovered=-1
handled=error:handled
whenCompleteSawError=true
observedExceptional=true
~~~

**Đọc kết quả:**

- source được completeExceptionally.
- Callback thenApply chỉ dành cho thành công nên không chạy, và successOnly được đánh dấu hoàn tất bất thường.
- exceptionally phục hồi lỗi bằng giá trị -1.
- handle chuyển trạng thái lỗi thành chuỗi error:handled.
- whenComplete quan sát exception nhưng observed vẫn hoàn tất bất thường.
- Các callback được đăng ký trước completion, nhưng không nên dùng thread identity của một phép thử đơn lẻ làm cam kết production.

### join, get và cách nhận biết lỗi

- **join()** trả kết quả, hoặc ném CompletionException (unchecked) với lỗi thông thường; cancellation có thể ném CancellationException.
- **get()** có các checked exception như InterruptedException và ExecutionException.
- Với exception wrapper, cần quan sát **cause** để biết lỗi gốc, tránh chỉ ghi tên wrapper.
- Nếu bạn tạo dependent future rồi **bỏ qua** nó, lỗi trong callback có thể không được xử lý ở ranh giới chương trình. Trả về hoặc giám sát **final future** của pipeline.

### Cancel không nhất thiết interrupt công việc

Với CompletableFuture, cancel(boolean mayInterruptIfRunning) xử lý bằng exceptional completion. Theo JavaDoc, tham số mayInterruptIfRunning **không được sử dụng để điều khiển xử lý** của CompletableFuture. Do đó **cancel(true) không bảo đảm ngắt thread** đang thực thi một Supplier hoặc lệnh I/O. Muốn dừng công việc thật, cần cancellation cooperation, timeout của I/O hoặc cơ chế hủy được framework/nguồn công việc hỗ trợ.

## 19. Blocking I/O và deadlock trong Executor

Một rủi ro nghiêm trọng xuất hiện khi một worker của pool đơn luồng gọi join để chờ tác vụ khác **được gửi tới chính pool đó**:

~~~java
// PHẢN VÍ DỤ: có thể deadlock với pool một thread.
CompletableFuture<String> outer =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<String> inner =
                    CompletableFuture.supplyAsync(
                            () -> "ok", singleThreadExecutor);
            return inner.join();
        }, singleThreadExecutor);
~~~

Nếu outer chiếm worker duy nhất và inner phải xếp hàng, inner không thể chạy cho tới khi worker trống; outer lại không nhả worker vì đang chờ inner. Đây là vòng chờ tài nguyên.

**Giải pháp:** Không block trong callback nếu có thể nối future bằng thenCompose. Để pipeline mô tả mối phụ thuộc thay vì chiếm worker khi đợi:

~~~java
// Mảnh mã, không gọi join từ worker để chờ việc cùng pool.
CompletableFuture<String> flattened =
        CompletableFuture.completedFuture("start")
                .thenCompose(x ->
                        CompletableFuture.supplyAsync(
                                () -> x + "-ok", singleThreadExecutor));
~~~

Cũng cần tránh blocking không cần thiết trong common pool, event loop, request handler hoặc pool hữu hạn. Một số cơ chế ForkJoinPool có managed blocking, nhưng không nên mặc định mọi blocking I/O đều được tự nhận diện hoặc bù worker một cách đủ an toàn.

**join không phải lúc nào cũng sai.** Ở biên CLI/test, khi caller thực sự cần chờ final result, join có thể phù hợp. Điều nguy hiểm là block **chính tài nguyên** cần thiết để hoàn tất kết quả đang được chờ.

## 20. Chọn Executor phù hợp workload

| Công việc | Cách nghĩ về Executor | Rủi ro cần kiểm soát |
|---|---|---|
| Map dữ liệu nhẹ, thuần túy | Non-async có thể đủ | Callback có thể chạy trên thread hoàn tất |
| CPU-bound nặng | Pool có concurrency phù hợp CPU | Quá nhiều runnable, CPU contention |
| Blocking JDBC/HTTP/file | Pool I/O được giới hạn hoặc I/O async thực sự | Worker bị block, queue bão hòa |
| Truy cập tài nguyên chung có rate limit | Executor/bulkhead giới hạn đồng thời | Quá tải dịch vụ ngoài |
| Logging/tracing callback | Không làm side effect blocking quá lâu | Context thiếu, logging tự ném lỗi |
| Request/transaction-sensitive | Truyền context rõ, boundary framework | Sai security/tenant, session hết hiệu lực |
| Lịch có timeout | Timeout ở nguồn I/O và lifecycle rõ | Future timeout nhưng công việc thật vẫn chạy |

**Common pool không phải lựa chọn sai mặc định.** Nó phù hợp một số tác vụ ngắn và CPU-oriented. Nhưng tài nguyên này được chia sẻ trong JVM; đẩy blocking I/O dài lên đó có thể khiến các pipeline khác bị ảnh hưởng. Dựa trên đo lường latency/queue/saturation/throughput, không dựa trên việc tên phương thức có Async.

Trong Java 21+, ứng dụng có thêm khả năng dùng virtual-thread executor, nhưng nguyên tắc **completion stage khác execution context** và yêu cầu truyền context an toàn vẫn còn nguyên. Bài không yêu cầu API virtual threads để hiểu CompletableFuture từ Java 8.

## 21. Những lỗi thường gặp

### 21.1. Cho rằng thenApply luôn chạy trên main

Sai. Nếu worker hoàn tất source, callback non-async có thể chạy ngay trên worker đó. Nếu stage đã hoàn tất trước khi đăng ký, callback có thể chạy inline từ caller đăng ký.

### 21.2. Cho rằng thenApply luôn chạy trên thread hoàn tất source

Sai. Contract cho phép caller completion khác; ở timing khác, callback có thể chạy từ thread đăng ký. Không xây dựng thread affinity ngầm.

### 21.3. Cho rằng Async luôn tạo thread mới

Sai. Executor có thể tái sử dụng worker hoặc chạy inline. Runnable::run là ví dụ rõ ràng nhất.

### 21.4. Cho rằng mọi thenApplyAsync đều ở common pool

Sai. Bản có Executor tham số dùng Executor đó. Các subclass có thể override defaultExecutor cho instance methods từ Java 9.

### 21.5. Cho rằng toàn bộ chain luôn ở một worker

Sai. thenCompose có thể phụ thuộc inner stage hoàn tất trên pool khác; Async boundary có thể đổi worker; non-async không có thread affinity cố định.

### 21.6. Chặn request thread hoặc completion thread bằng callback nặng

Non-async action có thể chạy ngay khi complete được gọi. Callback blocking có thể làm upstream chậm và gây starvation.

### 21.7. Gọi join trong worker duy nhất cần để tạo kết quả

Có thể deadlock. Dùng thenCompose hoặc thiết kế tài nguyên để tránh vòng đợi.

### 21.8. Đọc ThreadLocal/MDC như ngữ cảnh cố định của request

Sai khi continuation đổi thread. Truyền context bất biến hoặc propagation có snapshot/restore.

### 21.9. Không dọn ThreadLocal ở worker tái sử dụng

Dễ lẫn dữ liệu request/tenant. Dùng try/finally và làm sạch/khôi phục context đúng.

### 21.10. Copy transaction thread-bound một cách máy móc

Không đủ để chuyển JDBC transaction, session hoặc context bảo mật. Tuân thủ lifecycle và framework chính thức.

### 21.11. Dựa vào thứ tự đăng ký dependent callbacks

Không có bảo đảm tổng quát về thứ tự callback đồng cấp. Dùng dependency chain nếu cần tuần tự.

### 21.12. Coi source.isDone() nghĩa là mọi side effect đã xong

Phải chờ dependent future tương ứng, đặc biệt khi có Async queue, thenCombine hoặc thenCompose.

### 21.13. Bỏ rơi future của callback

Lỗi callback có thể chỉ được ghi trong dependent future; nếu không theo dõi, chương trình mất observability. Giữ final future và xử lý lỗi.

### 21.14. Nhầm exceptionally, handle và whenComplete

exceptionally phục hồi lỗi; handle chuyển đổi cả success/error; whenComplete quan sát outcome và thông thường không phục hồi lỗi.

### 21.15. Nghĩ cancel(true) chắc chắn interrupt computation

Không có bảo đảm đó với CompletableFuture. Cần hủy hợp tác và timeout I/O thật.

### 21.16. Tạo pool mới mỗi request rồi không shutdown

Gây rò rỉ thread và memory. Quản lý lifecycle theo service/container.

### 21.17. Dùng Thread.sleep để test race

Sleep phụ thuộc máy/CI; không bảo đảm thứ tự. CountDownLatch hoặc future hoàn tất có chủ đích giúp kiểm thử xác định.

### 21.18. Quên saturation và rejection policy

Executor có thể bị đầy queue hoặc từ chối task. Cần xử lý lỗi và đặt backpressure/giới hạn đầu vào theo SLA, không chỉ thêm thenApplyAsync.

## 22. Checklist đưa vào production

1. Callback nào cần chạy sau thành công, callback nào cần cả lỗi?
2. Có dùng non-async chỉ cho action ngắn, không blocking khi cần bảo vệ completion thread?
3. Những chỗ cần tách workload đã dùng Async với Executor được quản lý?
4. Pool có giới hạn worker, queue, timeout và rejection policy phù hợp?
5. Có truyền immutable request/tenant/trace context rõ ràng?
6. Nếu dùng ThreadLocal/MDC, đã capture đúng và restore/clear trong finally?
7. Có loại bỏ join/get trong worker cần để tạo kết quả được chờ?
8. Có theo dõi final dependent future, không chỉ root?
9. Có chờ đúng nhánh bằng allOf hoặc stage phụ thuộc?
10. Có phân biệt thenCompose với thenApply trả future lồng?
11. Có test trước/sau completion, success/failure/cancellation?
12. Có tránh phụ thuộc thứ tự callback đồng cấp hoặc tên thread tình cờ?
13. Có dùng latch/test executor thay vì sleep để điều khiển timing?
14. Có phân biệt thời gian queue và thời gian thực thi khi đo latency?
15. Có shutdown Executor theo owner và giám sát số task bị từ chối?

## 23. Câu hỏi ôn tập

**Câu 1:** thenApply chạy ở thread nào?

*Đáp án:* Không cố định. Nó có thể chạy trong thread hoàn tất stage hoặc một caller completion khác. Khi đăng ký sau completion, nó có thể chạy ngay ở thread đăng ký.

**Câu 2:** thenApplyAsync không có Executor dùng gì?

*Đáp án:* Với CompletableFuture chuẩn, default async facility thường là ForkJoinPool.commonPool; có fallback tạo thread khi common pool không hỗ trợ parallelism ít nhất hai.

**Câu 3:** Async có luôn chạy ở thread khác không?

*Đáp án:* Không. Direct Executor hoặc CallerRunsPolicy có thể chạy ngay trong caller thread.

**Câu 4:** Tại sao không dùng ThreadLocal để quyết định tenant trong continuation?

*Đáp án:* Continuation có thể chuyển thread, làm giá trị null hoặc sai request. Cần truyền context được xác thực như dữ liệu hoặc propagation được quản lý.

**Câu 5:** Dùng phương thức nào nếu callback trả CompletionStage?

*Đáp án:* thenCompose để flatten future lồng.

**Câu 6:** thenCombine non-async có luôn ở executor của first không?

*Đáp án:* Không. Nó phụ thuộc các completion và không có thread affinity cố định.

**Câu 7:** allOf(root) có chờ root.thenApplyAsync(...)? 

*Đáp án:* Không. Phải đưa dependent future vào allOf nếu muốn chờ nó.

**Câu 8:** Khi source lỗi, callback thenApply có chạy không?

*Đáp án:* Không. Dependent success-only stage hoàn tất bất thường.

**Câu 9:** Khác nhau giữa exceptionally và whenComplete?

*Đáp án:* exceptionally có thể phục hồi lỗi thành giá trị; whenComplete chủ yếu quan sát outcome và thông thường giữ lỗi ban đầu.

**Câu 10:** Gọi cancel(true) có luôn interrupt Supplier không?

*Đáp án:* Không. CompletableFuture.cancel là exceptional completion, không bảo đảm interruption của công việc nguồn.

**Câu 11:** Vì sao join trên single-thread executor có thể deadlock?

*Đáp án:* Worker duy nhất bị chặn chờ task khác cũng phải chạy trên worker đó.

**Câu 12:** Làm sao test một callback bị queue trong Executor?

*Đáp án:* Dùng single-thread executor và CountDownLatch giữ worker bận, đăng ký continuation Async, kiểm tra pending trước khi release; không dùng sleep để phỏng đoán.

**Câu 13:** Non-async có luôn nhanh hơn Async không?

*Đáp án:* Không có câu trả lời chung. Non-async bớt overhead scheduling trong một số trường hợp nhưng có thể giữ completion thread lâu, còn Async có queue/dispatch overhead. Phải đo workload thực.

**Câu 14:** Có nên tạo ExecutorService cho từng request?

*Đáp án:* Thông thường không. Nên dùng pool có lifecycle và giới hạn tải được quản lý; chỉ tạo pool riêng khi có lý do rõ ràng và đóng đúng.

**Câu 15:** Khi nào cần biến một nhiều-branch graph thành chuỗi tuần tự?

*Đáp án:* Khi các side effect hoặc phép tính có quan hệ thứ tự bắt buộc. Hãy thể hiện thứ tự bằng dependent chain, không dựa vào thứ tự đăng ký callbacks.

## 24. Áp dụng trong kiến trúc thực tế

**Web/API server:** Đừng block event-loop/request thread bằng join nếu framework đã có mô hình non-blocking. Bảo vệ context bảo mật và tenant. Với JDBC/HTTP synchronous, phải cân nhắc riêng blocking pool và concurrency.

**Data processing:** Sử dụng thenApply cho bước map nhẹ, thenApplyAsync(..., executor) khi bước nặng cần cô lập. Theo dõi queue và saturation, không chỉ thời gian tính toán.

**Logging/tracing:** Chụp trace ID đúng boundary, đưa qua immutable context hoặc propagation của thư viện đang được bảo trì, restore/clear MDC trong worker pool. Logging callback không nên làm pipeline thất bại ngoài ý muốn.

**Batch/CLI:** join final future ở biên để đợi kết quả là hợp lý nếu đã xử lý exception và shutdown pool; không đặt join chờ cùng pool bên trong worker.

**Multi-tenant:** Tenant context cần đi cùng request đã xác thực, không tin một ThreadLocal có thể bị tái sử dụng hoặc thread-hopping làm sai.

## Tài liệu Oracle JavaDoc hiện hành

- Java SE 25 — CompletableFuture và chính sách non-async/async, cancel: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 25 — CompletionStage và ý nghĩa các dependent stages: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html
- Java SE 25 — Executor, contract execute(Runnable): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 25 — ExecutorService, shutdown và lifecycle: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 25 — ForkJoinPool.commonPool: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- Java SE 25 — ThreadLocal: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 25 — CountDownLatch: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 25 — ThreadPoolExecutor và CallerRunsPolicy: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 25 — CompletionException: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionException.html

**Kết luận:** CompletableFuture mô tả kết quả và quan hệ phụ thuộc, không có thread sở hữu cố định. **Non-async** action có thể được chạy bởi thread hoàn tất stage hoặc caller completion khác; **Async** action được gửi qua default facility hoặc Executor được chọn, nhưng không bắt buộc một thread vật lý khác. **ThreadLocal/MDC/security context không tự đi theo pipeline**; cần dữ liệu bất biến hoặc propagation có kiểm soát. Chọn Executor theo workload, tránh blocking/deadlock, theo dõi đúng dependent future và kiểm thử hành vi concurrency bằng các điểm đồng bộ xác định.