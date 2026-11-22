# Kiểm thử tác vụ bất đồng bộ và ngữ cảnh được truyền trong Aspect (AOP)

## 1. Vì sao kiểm thử bất đồng bộ khác kiểm thử advice đồng bộ?

Trong **Aspect-Oriented Programming (AOP)**, aspect mô-đun hóa những hành vi cắt ngang như tracing, audit, metric, kiểm soát quyền và một số chính sách thời gian thực thi. Pointcut chọn join point; advice được kích hoạt ở thời điểm mà cơ chế AOP thực sự chặn được, chẳng hạn **method execution** hay **method call**.

Với một phương thức đồng bộ, lời gọi có thể kết thúc khi kết quả trả về hoặc exception được ném. Nhưng một phương thức bất đồng bộ có thể **trả một handle trước khi tác vụ hoàn thành**:

~~~text
Caller thread                  Worker thread
     |                               |
     |-- processAsync() ------------>|
     |<-- CompletionStage ---------- |
     |                               |-- thực thi nghiệp vụ
     |                               |-- trả giá trị / phát lỗi
     |<------ completion signal -----|
~~~

Nếu around advice chỉ bao quanh `processAsync()`, thời điểm `after returning` có thể chỉ là lúc **trả stage/future**, không phải lúc công việc nền đã thành công. Một lời gọi trả handle nhanh rồi xử lý lỗi sau 5 giây **không phải thao tác nghiệp vụ thành công** chỉ vì method đã return bình thường.

Ngoài thời gian, **ngữ cảnh** (context) như trace ID, correlation ID, principal đã xác thực, tenant, locale, deadline hoặc policy snapshot có thể bị mất, dùng nhầm hoặc rò khi chuyển giữa các thread. Một aspect dùng `ThreadLocal` trên caller thread không mặc nhiên có dữ liệu ấy trên worker thread.

**Mục tiêu kiểm thử**: xác nhận aspect chọn đúng join point; bảo toàn ngữ nghĩa nghiệp vụ khi có success/error/cancel/timeout; context được capture/propagate/restore/cleanup đúng ranh giới; metric/log/trace gắn đúng operation; không phát hai sự kiện kết thúc, không chặn worker và không rò context giữa những request tái sử dụng thread.

Bài này tập trung **AOP tổng quát từ cơ bản đến nâng cao**, không phụ thuộc một framework AOP cụ thể. Ví dụ Java 17+ dùng JDK dynamic proxy làm điểm chặn minh họa around advice; các nguyên tắc kiểm thử vẫn cần áp dụng với weaving/interceptor/decorator theo đúng tập join point thực tế của công cụ.

## 2. Bốn vòng đời cần phân biệt

Không nên gom mọi mốc thời gian thành một biến `finished`.

| Vòng đời | Bắt đầu | Mốc kết thúc | Điều cần đo |
| --- | --- | --- | --- |
| **Method invocation** | Caller đi vào join point | Method trả về stage/handle hoặc ném lỗi ngay | Thời gian chuẩn bị/schedule, lỗi đồng bộ |
| **Logical operation** | API nhận yêu cầu xử lý | Kết quả logic được xác định: success, failed, cancelled, timed-out, unknown | Trạng thái mà caller thấy |
| **Physical worker** | Task thực sự được worker nhận/chạy | Worker dừng và dọn tài nguyên | CPU/I/O/resource, cooperative cancellation |
| **Observation/export** | Advice ghi nhận event | Telemetry được xác nhận theo hợp đồng | Độ trễ xuất metric/span, dropped/export failures |

Ví dụ, caller hết hạn chờ ở `t=100 ms` nhưng worker gọi API từ xa vẫn tiếp tục đến `t=900 ms`. Nếu advice gắn nhãn “worker cancelled” tại `t=100 ms` thì sai: **hết hạn chờ** có thể chỉ là quyền chờ của caller, không chứng minh side effect đã dừng.

Một stage có thể kết thúc bằng `CompletionException` bao một nguyên nhân nghiệp vụ; một lần cancel có thể là exceptional completion của handle, trong khi cơ chế hủy vật lý được quản lý ở nơi khác. Hợp đồng phải nêu rõ **đang kiểm thử lớp nào** và **đếm terminal event của lớp nào**.

### 2.1. Những câu hỏi test phải trả lời

1. Aspect nhìn thấy điểm bắt đầu nào: invocation, submit, worker-start hay completion?
2. Khi method trả `CompletionStage`, advice có quan sát **kết quả cuối** hay chỉ quan sát object handle?
3. Context được lấy từ đâu, tại thời điểm nào, và có phải nguồn tin cậy không?
4. Callback completion chạy trên thread nào? Nếu chạy ngay trên thread gọi thì có kết quả khác không?
5. Có đường error synchronous trước khi tạo future, và đường error asynchronous sau khi future được trả?
6. Nếu timeout/cancel xảy ra, ai sở hữu resource, worker và cleanup?
7. Khi completion đua với timeout, điểm xác nhận terminal outcome có được thực hiện đúng một lần không?
8. Nếu exporter lỗi, result/exception gốc có bị thay đổi không?
9. Thread pool tái sử dụng thread có mang nhầm context của request trước không?
10. Tập join point được lựa chọn có bao trùm callback/worker thật hay chỉ API submit?

## 3. Context propagation là gì?

Một **context** là tập metadata có ý nghĩa đối với một logical operation. Thường gặp:

- **Trace ID / span context:** liên kết những đoạn công việc có quan hệ nhân quả.
- **Correlation / operation ID:** đối chiếu một request xuyên qua các bước.
- **Principal và tenant:** danh tính/scope đã được xác thực, nếu policy cho phép truyền.
- **Deadline/budget:** mốc hết hạn hoặc ngân sách thời gian còn lại.
- **Locale/time zone:** quy tắc biểu diễn nội dung.
- **Audit metadata:** nguồn lệnh và thông tin cần thiết để chứng minh hành vi.

Context **không phải** tập toàn bộ request body, access token, password hay đối tượng nghiệp vụ. Chỉ capture trường tối thiểu cần thiết, có quy tắc bảo mật và vòng đời rõ; tránh giữ reference lớn trong closure.

### 3.1. Ba thao tác không được thiếu

**Capture:** chụp đúng snapshot context tại ranh giới submit, khi caller còn nắm context hợp lệ.

**Install/propagate:** thiết lập context cho worker/callback trong phạm vi tác vụ; nếu caller không có context, chính sách phải là xóa/thiết lập rỗng hoặc báo lỗi rõ, **không kế thừa giá trị của request trước**.

**Restore/cleanup:** luôn phục hồi context trước đó bằng `finally`, kể cả task ném exception. Với executor dùng lại thread, bỏ qua bước này có thể gây **rò correlation ID hoặc tenant giữa hai tác vụ**.

~~~text
caller: ctx=A
    |
    +-- capture(A) --> enqueue --> worker: old ctx=X
                                      |
                                 install(A)
                                      |
                                task success/error
                                      |
                                  finally
                                      |
                                  restore(X)
~~~

Việc restore giá trị cũ, không chỉ `remove()` vô điều kiện, giúp giữ hành vi đúng khi một tác vụ chạy lồng trong một context hiện có. Nếu old context là `null`, việc `ThreadLocal.remove()` phù hợp hơn `set(null)` ở nhiều cấu trúc lưu context.

### 3.2. `ThreadLocal` không tự vượt thread

Trong Java, `ThreadLocal` lưu dữ liệu theo thread. Gán giá trị trên caller thread không khiến thread pool worker nhìn thấy cùng giá trị. `InheritableThreadLocal` không phải một giải pháp tổng quát cho pool: thread thường được tạo một lần rồi tái sử dụng, nên dữ liệu được thừa hưởng khi tạo thread có thể lỗi thời hoặc lộ sang request khác.

Callback của `CompletableFuture` cũng có thể chạy trên thread hoàn tất stage, thread đăng ký callback (khi stage đã hoàn tất), hoặc executor được chỉ định với biến thể `Async`. **Không kiểm thử bằng giả định một callback nhất định luôn chạy trên một thread xác định** nếu API không cam kết.

### 3.3. Context cần được định nghĩa theo hợp đồng

| Thuộc tính | Điều phải công bố | Ví dụ test |
| --- | --- | --- |
| Nguồn | Caller identity tin cậy hay header tùy ý? | Header giả không đổi principal xác thực |
| Snapshot | Capture ở submit hay lúc worker bắt đầu? | Caller đổi ctx sau submit, worker vẫn thấy snapshot |
| Truyền | Qua executor wrapper, callback hay tham số tường minh? | Nested async task nhận đúng trace |
| Isolation | Giữa request và tenant | A kết thúc, B không thấy context A |
| Restoration | Cleanup cuối tác vụ | Thread pool tái sử dụng có ctx rỗng |
| Retention | Context có giữ dữ liệu nhạy cảm không? | Không log token/secret; closure không giữ full request |
| Deadline | Mốc tuyệt đối hay duration mới? | Không vô tình reset timeout khi qua tầng |
| Error semantics | Không có context sẽ ra sao? | Theo contract, không âm thầm gán identity giả |

Đặc biệt với **principal/authorization**, propagation không tự đồng nghĩa “được phép”. Quyền có thể bị thu hồi trong lúc queue chờ; chính sách phải quy định kiểm tra ở submit, execution hay cả hai, và những nguồn dữ liệu tin cậy cần kiểm tra lại.

## 4. Thiết kế một ma trận kiểm thử bất đồng bộ

| Kịch bản | Context kỳ vọng | Outcome kỳ vọng | Điều không được xảy ra |
| --- | --- | --- | --- |
| Submit và hoàn tất bình thường | Snapshot của caller tại lúc submit | Một success event | Log success trước khi task thực sự xong |
| Tác vụ ném exception | Context vẫn đúng khi chạy/callback | Một failure event và lỗi gốc | Nuốt lỗi thành success |
| Method ném trước khi trả future | Context caller còn đúng | Failure đồng bộ theo API | Chờ một callback sẽ không bao giờ đến |
| Callback chạy trên thread khác | Context được truyền tường minh | Event đúng trace/operation | Dùng `ThreadLocal` trống hay từ request khác |
| Future đã hoàn tất trước khi gắn callback | Snapshot/metadata vẫn tồn tại | Callback quan sát đúng một lần | Giả định callback luôn chạy async |
| Caller timeout nhưng worker chưa dừng | Đúng context cho mỗi vòng đời | Caller timeout và worker còn có thể đang chạy | Ghi “worker stopped” giả |
| Hủy future | Theo contract propagation | Handle biểu thị cancelled | Tự cho rằng `cancel(true)` chắc chắn interrupt mọi worker |
| Completion đua timeout | Tính một terminal outcome cho logical operation | Một winner theo atomic state | Hai lần đóng span/metric |
| Executor từ chối submit | Caller context nguyên vẹn | Rejection đồng bộ/exceptional theo API | Rò context hoặc bỏ sót counter |
| Thread được tái sử dụng | Request B thấy B hoặc rỗng | Mỗi tác vụ độc lập | Request B thấy principal/tenant A |
| Async fan-out/fan-in | Context con đúng và có parent | Tổng hợp kết quả theo policy | Một nhánh lỗi làm mất cleanup nhánh khác |
| Exporter telemetry ném lỗi | Business outcome giữ nguyên theo contract | Lỗi quan sát được thống kê riêng | Thay lỗi nghiệp vụ bằng lỗi exporter |

Với mọi hàng, nêu **join point được advice chặn** và **đơn vị đo**. Việc test chỉ đếm số dòng log có thể bị nhiễu bởi sampling hoặc queue exporter: dùng một recorder không loại bỏ sự kiện trong môi trường kiểm thử.

## 5. Tách ba tầng test

### 5.1. Unit test logic advice

Cho một target giả trả future điều khiển được:

- Counter invocation tăng ngay tại method call.
- Counter terminal success/failure chỉ tăng khi stage hoàn tất.
- `proceed`/lời gọi mục tiêu chỉ diễn ra một lần trừ khi có policy retry tường minh.
- Giá trị trả về và nguyên nhân lỗi không bị đổi ngoài hợp đồng.
- Callback observer chỉ tác động telemetry và cleanup.
- Khi future chưa hoàn tất, không được báo success sớm.

Không cần thread thật cho mọi test. Một `CompletableFuture` tạo thủ công rồi gọi `complete`/`completeExceptionally` giúp điều khiển chính xác từng trạng thái.

### 5.2. Integration test executor và context

Dùng một executor thực có thread tái sử dụng; chụp context A, chạy request A, dọn context; tiếp tục context B, chạy B. Kiểm tra:

- B không thấy A.
- Dù A ném lỗi, thread được restore.
- Callback sau completion mang đúng correlation ID nhờ capture tường minh.
- Nếu tầng giữa tiếp tục `supplyAsync` hoặc `thenApplyAsync`, mỗi ranh giới cần propagation thích hợp.
- Shutdown hoặc rejection không làm task bị mất dấu mà không có trạng thái.

### 5.3. Integration test weaving/interception

Chạy với chính cơ chế AOP của ứng dụng:

- Pointcut chặn đúng **method execution/call** mong muốn.
- Với proxy, self-call có thể không đi qua wrapper; với execution weaving, nếu method được weave, self-call có thể vẫn được chặn.
- Nếu advice chỉ chạy quanh method trả future, test phải chứng minh callback quan sát terminal completion.
- Các lời gọi được tạo trong worker/executor có được chặn hay không phụ thuộc phạm vi weave và class loader.
- Cấu hình load-time weaving hoặc compiler khác có thể làm method không được chặn, dù logic unit advice vẫn xanh.

**Đừng lấy một bài test unit thành bằng chứng rằng mọi thread, mọi class và mọi class loader trong production đều đi qua aspect.**

## 6. Ví dụ Java 17+: truyền context và quan sát completion thật

Ví dụ chạy độc lập dùng:

1. `ThreadLocal<RequestContext>` để biểu diễn context theo thread.
2. `ContextExecutor` để capture tại `execute`, install khi worker chạy, restore bằng `finally`.
3. `TaskApi` trả `CompletionStage<String>` và thực thi nghiệp vụ bất đồng bộ trên worker.
4. `ObservingAdvice` dùng JDK dynamic proxy để chặn invocation, ghi completion callback và phân biệt success/error.
5. Một thread pool một worker được tái sử dụng để kiểm tra không rò context.

**Giới hạn của demo:** principal/trace ID là giá trị giả dùng trong test; hệ thống thật phải lấy từ nguồn xác thực tin cậy. Đây là một mô hình around advice cơ bản, không phải thư viện truyền context cho mọi loại scheduler/executor.

### 6.1. Mã hoàn chỉnh: `AsyncContextAspectDemo.java`

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncContextAspectDemo {
    record RequestContext(String traceId, String actor) { }

    private static final ThreadLocal<RequestContext> CONTEXT =
            new ThreadLocal<>();

    interface TaskApi {
        CompletionStage<String> handle(String command);
    }

    static final class ContextExecutor implements Executor {
        private final Executor delegate;

        ContextExecutor(Executor delegate) {
            this.delegate = delegate;
        }

        @Override
        public void execute(Runnable command) {
            RequestContext captured = CONTEXT.get();

            delegate.execute(() -> {
                RequestContext previous = CONTEXT.get();
                try {
                    if (captured == null) {
                        CONTEXT.remove();
                    } else {
                        CONTEXT.set(captured);
                    }
                    command.run();
                } finally {
                    if (previous == null) {
                        CONTEXT.remove();
                    } else {
                        CONTEXT.set(previous);
                    }
                }
            });
        }
    }

    static final class TaskService implements TaskApi {
        private final Executor executor;

        TaskService(Executor executor) {
            this.executor = executor;
        }

        @Override
        public CompletionStage<String> handle(String command) {
            return CompletableFuture.supplyAsync(() -> {
                RequestContext context = CONTEXT.get();
                if (context == null) {
                    throw new IllegalStateException("context missing");
                }

                System.out.println("worker trace=" + context.traceId()
                        + " actor=" + context.actor());

                if ("bad".equals(command)) {
                    throw new IllegalArgumentException("bad request");
                }
                return "accepted:" + command;
            }, executor);
        }
    }

    static final class ObservingAdvice implements InvocationHandler {
        private final TaskApi target;
        private final AtomicInteger successes = new AtomicInteger();
        private final AtomicInteger failures = new AtomicInteger();

        ObservingAdvice(TaskApi target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            RequestContext snapshot = CONTEXT.get();

            final Object value;
            try {
                value = method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                // Loi xay ra truoc khi target tra future.
                throw ex.getCause();
            }

            @SuppressWarnings("unchecked")
            CompletionStage<String> stage = (CompletionStage<String>) value;

            // Tra stage sau callback: join cua stage nay doi observer xong.
            return stage.whenComplete((result, error) -> {
                try {
                    String trace = snapshot == null
                            ? "none" : snapshot.traceId();
                    if (error == null) {
                        successes.incrementAndGet();
                        System.out.println("observe trace=" + trace
                                + " outcome=ok");
                    } else {
                        failures.incrementAndGet();
                        System.out.println("observe trace=" + trace
                                + " outcome=error");
                    }
                } catch (RuntimeException observationFailure) {
                    // Loi telemetry khong duoc thay doi ket qua nghiep vu.
                }
            });
        }

        String summary() {
            return "successes=" + successes.get()
                    + " failures=" + failures.get();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();

        try {
            // Khoi tao worker va chung minh ThreadLocal khong tu truyen.
            CONTEXT.set(new RequestContext("t-0", "setup"));
            RequestContext unwrapped = raw.submit(CONTEXT::get).get();
            System.out.println("unwrapped context=" + unwrapped);
            CONTEXT.remove();

            TaskService target = new TaskService(new ContextExecutor(raw));
            ObservingAdvice advice = new ObservingAdvice(target);
            TaskApi observed = (TaskApi) Proxy.newProxyInstance(
                    TaskApi.class.getClassLoader(),
                    new Class<?>[] { TaskApi.class },
                    advice);

            CONTEXT.set(new RequestContext("t-1", "alice"));
            CompletionStage<String> ok = observed.handle("ok");
            CONTEXT.remove();
            System.out.println("caller=" + ok.toCompletableFuture().join());

            CONTEXT.set(new RequestContext("t-2", "bob"));
            CompletionStage<String> bad = observed.handle("bad");
            CONTEXT.remove();

            try {
                bad.toCompletableFuture().join();
            } catch (CompletionException ex) {
                System.out.println("caller error="
                        + ex.getCause().getMessage());
            }

            boolean cleared = raw.submit(() -> CONTEXT.get() == null).get();
            System.out.println("worker context cleared=" + cleared);
            System.out.println("observed " + advice.summary());
        } finally {
            CONTEXT.remove();
            raw.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AsyncContextAspectDemo.java
java AsyncContextAspectDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
unwrapped context=null
worker trace=t-1 actor=alice
observe trace=t-1 outcome=ok
caller=accepted:ok
worker trace=t-2 actor=bob
observe trace=t-2 outcome=error
caller error=bad request
worker context cleared=true
observed successes=1 failures=1
~~~

Tại sao output có tính xác định trong demo:

- `raw` là pool một worker; từng lời gọi được `join` trước khi gửi lời gọi tiếp.
- Callback `whenComplete` nằm trong stage được trả cho caller, nên khi `join` của stage dẫn xuất hoàn tất, callback đã chạy.
- Dù stage nghiệp vụ hoàn tất cực nhanh trước khi advice đăng ký callback, `whenComplete` vẫn chạy khi đăng ký; callback dùng **snapshot tường minh** thay vì đọc `ThreadLocal` của thread bất kỳ.
- Test `raw.submit(() -> CONTEXT.get() == null)` chạy trên cùng worker sau hai tác vụ, xác minh bước restore đã dọn context.
- Với đường lỗi, `CompletionException` là wrapper phát sinh khi `join`; test kiểm tra nguyên nhân `IllegalArgumentException`, không đổi lỗi nghiệp vụ thành success.

**Hai lưu ý production rất quan trọng:**

1. Advice đang trả một **stage dẫn xuất** từ `whenComplete`, không trả cùng object handle gốc. Cách này giúp xác nhận callback đã chạy trước khi caller thấy completion, nhưng có thể thay đổi semantics của **cancellation**, identity và propagation. Muốn bảo toàn chính xác hợp đồng `Future`/`CompletionStage`, phải quyết định rõ có được bọc stage hay chỉ gắn observer lên stage gốc. Không ngầm giả định `cancel(true)` trên stage dẫn xuất sẽ dừng upstream worker.
2. Callback trong `whenComplete` có thể chạy trên worker thread hoặc ngay trên thread gọi nếu stage đã hoàn tất. Callback làm I/O/serialize nặng sẽ ảnh hưởng latency. Demo chỉ dùng `println`; trong hệ thống thật nên có sink/queue hữu hạn và kiểm soát lỗi telemetry. `catch RuntimeException` chỉ bao vùng quan sát, không nuốt lỗi nghiệp vụ.

Demo `TaskService` chỉ minh họa **một bước submit**. Nếu worker tạo một nhiệm vụ mới ở executor khác, context cần được capture/propagate tại **ranh giới mới**; wrapper ở executor đầu không làm `ThreadLocal` tự lan truyền qua mọi scheduler.

## 7. Kiểm thử không truyền context và truyền sai context

Một bài test chỉ thấy request A chạy đúng chưa bảo đảm không rò dữ liệu.

### 7.1. Negative test: bỏ wrapper

Nếu thay `new ContextExecutor(raw)` bằng `raw` khi tạo `TaskService`, worker thường đọc `CONTEXT.get() == null`, dẫn đến exception “context missing”. Hành vi ấy cho thấy context không tự vượt ranh giới thread.

Không viết production code tự động thay `null` bằng principal mặc định có quyền cao. Nếu context là bắt buộc, hệ thống phải fail theo contract hoặc nhận context đúng từ một đường tin cậy.

### 7.2. Two-request isolation test

Một phép kiểm chứng mạnh cho thread pool tái sử dụng:

~~~text
A: caller ctx trace-A, tenant-A
  -> worker nhận trace-A/tenant-A
  -> task throws
  -> finally restore previous context

B: caller ctx trace-B, tenant-B
  -> worker nhận trace-B/tenant-B
  -> task succeeds
  -> finally restore previous context

C: task không có context
  -> worker không được thấy A hay B
~~~

Case A phải cố ý ném lỗi **bên trong worker**, vì leak thường xảy ra khi logic exception bỏ qua cleanup. Cần chạy tất cả case trên cùng một worker hoặc điều phối pool để chắc chắn thread cũ thực sự được dùng lại. Với pool nhiều thread, một test ngẫu nhiên chưa chắc chạy đúng thread từng giữ context cũ.

### 7.3. Capture theo snapshot chứ không tham chiếu mutable request

Nếu closure giữ tham chiếu tới một object context mutable, caller sửa tenant/trace ID sau submit có thể thay đổi ý nghĩa operation đang queue. Ưu tiên immutable record/value object; nếu metadata phức tạp, snapshot phải thật sự tách khỏi dữ liệu mutable.

Nếu contract đòi context sống và tự cập nhật (chẳng hạn quyền bị thu hồi), đó là một vấn đề khác: cần **policy revalidation**, không giải quyết bằng cách chia sẻ mutable context không đồng bộ giữa thread.

## 8. Callback đã hoàn tất trước khi được gắn

Một race phổ biến:

~~~text
Thread A: method trả CompletionStage
Thread B: stage complete ngay lập tức
Thread A: advice gắn whenComplete(...)
~~~

Các toán tử `CompletionStage.whenComplete` vẫn quan sát stage đã hoàn tất; callback có thể chạy đồng bộ trên thread đang đăng ký. Vì vậy test phải bao phủ cả:

- **Pending stage:** advice đăng ký trước, test sau đó gọi `complete(...)`.
- **Already completed:** target trả `CompletableFuture.completedFuture(value)`.
- **Already exceptionally completed:** target trả stage đã lỗi.
- **Completion đồng thời với registration:** callback được tính đúng một lần bất kể bên nào thắng race.

Điều không được làm là kiểm tra `if (!stage.isDone())` rồi mới đăng ký callback; stage có thể hoàn tất ngay sau bước kiểm tra và trước đăng ký. Đăng ký callback trực tiếp qua API đã có cơ chế xử lý race phù hợp.

Nếu callback mở span mới từ `ThreadLocal`, test sẽ lộ việc context không tồn tại khi callback chạy trên thread không mong muốn. Một cách ổn định là **capture metadata cần thiết ngay trong advice** và truyền vào callback; nếu cần thiết lập ThreadLocal cho code trong callback, thực hiện scoped install/restore bằng `try/finally`.

## 9. Timeout, cancellation và completion là các sự kiện khác nhau

### 9.1. Timeout của caller không chứng minh worker dừng

Giả sử một lệnh gọi thanh toán đã được gửi tới hệ thống bên ngoài. Caller timeout có thể xảy ra sau khi bên ngoài đã thực hiện side effect nhưng trước khi phản hồi quay lại. Một aspect ghi “giao dịch chắc chắn thất bại và được rollback” ở mốc timeout có thể làm caller retry sai và nhân đôi side effect.

Kiểm thử phải phân biệt:

- **Deadline reached:** ngân sách chờ đã hết.
- **Logical operation timed out:** API đánh dấu kết quả là timeout.
- **Cancellation requested:** có tín hiệu yêu cầu hủy.
- **Worker observed cancellation:** worker đã đọc tín hiệu.
- **Worker physically stopped:** mã chạy nền thực sự ngừng và cleanup xong.
- **Outcome unknown:** chưa đủ bằng chứng để khẳng định side effect thành công/thất bại.

`CompletableFuture.cancel(boolean)` là một cơ chế biểu diễn cancellation của future. Với `CompletableFuture` chuẩn, tham số `mayInterruptIfRunning` **không biến cancellation thành bảo đảm interrupt worker**. Hành vi ngắt/dừng tùy cơ chế thực thi và chính sách hợp tác của task.

### 9.2. Ví dụ Java 17+ thứ hai: kiểm thử terminal winner có kiểm soát

Ví dụ tiếp theo **không giả lập một thread worker thực đang chạy**. Nó dùng hai future độc lập làm mô hình cho “kết quả mà caller quan sát” và “kết quả công việc vật lý” để kiểm chứng sự khác biệt và bảo đảm chỉ một lần hoàn tất logical handle.

Tạo file `AsyncTerminalStateDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncTerminalStateDemo {
    public static void main(String[] args) {
        CompletableFuture<String> caller = new CompletableFuture<>();
        CompletableFuture<String> worker = new CompletableFuture<>();
        AtomicInteger terminalEvents = new AtomicInteger();

        caller.whenComplete((value, error) ->
                terminalEvents.incrementAndGet());

        boolean timeoutWon = caller.completeExceptionally(
                new TimeoutException("deadline"));
        boolean lateResultAccepted = caller.complete("too late");

        System.out.println("timeout won=" + timeoutWon);
        System.out.println("late caller result accepted=" + lateResultAccepted);
        System.out.println("logical terminal events=" + terminalEvents.get());
        System.out.println("worker done at timeout=" + worker.isDone());

        worker.complete("late worker result");
        System.out.println("worker result=" + worker.join());

        CompletableFuture<String> cancelHandle = new CompletableFuture<>();
        boolean cancelAccepted = cancelHandle.cancel(true);
        System.out.println("cancel accepted=" + cancelAccepted);
        System.out.println("cancelled flag=" + cancelHandle.isCancelled());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AsyncTerminalStateDemo.java
java AsyncTerminalStateDemo
~~~

**Stdout chính xác:**

~~~text
timeout won=true
late caller result accepted=false
logical terminal events=1
worker done at timeout=false
worker result=late worker result
cancel accepted=true
cancelled flag=true
~~~

Điểm cần rút ra:

- `completeExceptionally` thắng trạng thái của future caller; `complete("too late")` không thể ghi đè một completion đã quyết định.
- `whenComplete` ghi nhận **một terminal completion** ở caller future.
- Worker future riêng vẫn chưa hoàn tất tại mốc caller timeout, sau đó có thể hoàn tất với kết quả muộn. Đây là mô hình hóa trạng thái, **không phải bằng chứng có worker thread hay I/O đã chạy**.
- `cancel(true)` thay đổi trạng thái của handle trong ví dụ; không chứng minh worker thực tế đã bị ngắt.

Đối với một implementation thực, phải kiểm thử riêng **cầu nối giữa logical timeout/cancel và tín hiệu hủy vật lý** bằng executor, cancellation token, interrupt handling, tài nguyên I/O và cleanup được quản lý.

## 10. Xử lý race giữa success, failure, timeout và cancellation

Khi nhiều nguồn có thể báo terminal outcome, test nên kiểm tra quy tắc **single-winner**:

~~~text
          PENDING
         /   |   \
     SUCCESS ERROR TIMEOUT
         \   |   /
       one terminal decision
             |
       close metrics/span ONCE
~~~

Sơ đồ giản lược không khẳng định mọi hệ thống chỉ có ba trạng thái; có thể có `CANCELLED`, `REJECTED` hoặc `UNKNOWN`. Một triển khai thường dùng **state machine** và thao tác atomic như `compareAndSet` để chọn đúng một lần kết thúc logical operation.

Mã giả minh họa:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
if (state.compareAndSet(PENDING, TERMINAL)) {
    publishLogicalOutcome(outcome);
    closeLogicalSpan();
}
~~~

Nếu timeout đã được công nhận, một success đến muộn không được tạo một logical terminal event thứ hai. Tuy vậy, hệ thống vẫn cần theo dõi **physical late completion** hoặc reconciliation riêng nếu side effect có ý nghĩa.

Kiểm thử nên điều phối hai nhánh đua có chủ đích bằng `CountDownLatch`/`Phaser`, chạy nhiều vòng và assert: chỉ một winner, một event logical, không leak resource. Đừng dùng `Thread.sleep` rồi cho rằng hai thread chắc chắn chạy theo thứ tự dự đoán.

### 10.1. Những case race quan trọng

| Race | Kỳ vọng cần xác minh |
| --- | --- |
| Success và timeout cùng lúc | Một logical terminal outcome; late outcome xử lý theo policy |
| Failure và cancellation cùng lúc | Không xuất cả “success” lẫn “cancelled” cho cùng logical operation |
| Cancellation trước submit | Không cấp context/resource khi không còn việc cần chạy |
| Cancellation sau submit, trước worker-start | Tác vụ được bỏ hoặc nhận cancel theo executor contract |
| Cancellation khi worker đang cleanup | Không đóng tài nguyên hai lần; cleanup an toàn và idempotent |
| Timeout rồi caller retry | Idempotency/budget không cho nhân side effect ngoài hợp đồng |
| Completion rồi callback đăng ký muộn | Observer vẫn nhìn thấy terminal outcome một lần |
| Callback telemetry bị lỗi | Không làm thay đổi outcome nghiệp vụ theo hợp đồng |

Nếu API cung cấp `orTimeout` hoặc `completeOnTimeout`, phải kiểm tra **future nào được sửa/hoàn tất** và **worker có còn chạy không**. Không suy luận trực tiếp về rollback hay interrupt từ tên một toán tử thời gian.

## 11. Context propagation khi có chuỗi stage và fan-out/fan-in

### 11.1. Stage chains

Xét:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
CompletionStage<Result> stage = loadAsync(id)
    .thenApply(this::validate)
    .thenApplyAsync(this::enrich, anotherExecutor)
    .thenCompose(this::writeAsync);
~~~

Các bước có thể chạy trên nhiều thread hoặc executor. Nếu `validate` dựa vào `ThreadLocal` của worker trước đó, còn `enrich` chuyển qua executor mới, context có thể mất. Kiểm thử phải đánh dấu từng bước bằng trace ID và caller context snapshot, rồi xác nhận ranh giới nào có trách nhiệm capture/restore.

Đừng gọi `ThreadLocal.get()` ở callback và cho rằng nó luôn thấy context của request khi callback được đăng ký. Với `thenApply` không có `Async`, callback có thể chạy ở thread hoàn tất stage trước; nếu stage đã hoàn tất, callback có thể được thực thi ngay khi đăng ký. Hợp đồng context của callback phải độc lập với giả định lịch chạy.

### 11.2. Fan-out / fan-in

Một operation có thể gửi hai tác vụ con và đợi tổng hợp:

~~~text
              parent trace
                  |
              submit work
               /       \
         child A       child B
               \       /
                aggregate
                   |
              terminal result
~~~

Test cần:

- Cả child A/B nhận đúng parent trace nhưng có identity/span con riêng nếu chính sách tracing yêu cầu.
- B có lỗi không làm dọn resource của A sai, kể cả khi policy cancel các nhánh còn lại.
- Parent hoàn tất theo chính sách tập hợp (all-success, partial-success, fail-fast, quorum...); không giả định một policy mặc định cho mọi use case.
- Quá hạn của parent không tự động chứng minh cả child đã dừng.
- Khi một child chậm hoặc bị hủy, context của nó phải được restore khi worker thực sự hoàn tất.
- Event của child được liên kết đúng correlation ID mà không dùng mutable global context.

Nếu dùng `CompletableFuture.allOf`, phải hiểu rằng aggregate future chỉ cung cấp thông tin tổng hợp theo semantics API; không tự hủy mọi child còn lại. Muốn cooperative cancellation, cần thiết kế và test đường truyền yêu cầu hủy riêng.

## 12. Kiểm thử lỗi đồng bộ và lỗi bất đồng bộ

Hai đường lỗi khác nhau:

**Lỗi đồng bộ khi tạo stage:** `TaskApi.handle()` ném ngay do input không hợp lệ, thiếu executor hoặc lỗi submit. Around advice nhìn thấy exception tại method execution. Nếu advice chỉ xử lý `stage.whenComplete` sau khi method return, đường này sẽ không có stage để gắn callback.

**Lỗi bất đồng bộ khi worker hoàn tất:** method đã trả stage; worker ném, future hoàn tất exceptionally. Advice không thể dựa vào `catch` quanh riêng lời gọi method để thấy lỗi này. Nó phải quan sát stage completion hoặc ranh giới worker thực.

Test phải xác minh counters phân biệt:

- `invocations_total`: mọi lời gọi đi vào pointcut.
- `submission_failures_total`: lỗi ngay lúc chuẩn bị/submit (nếu API phân biệt).
- `operations_succeeded_total`: logical operation thành công.
- `operations_failed_total`: logical operation lỗi.
- `operations_timed_out_total` và `operations_cancelled_total`: theo state machine có semantics riêng.
- `physical_workers_stopped_total`: chỉ tăng khi worker thực sự dừng nếu cần đo.

Không cộng các counter trên như thể tất cả đều là tập rời nhau nếu có thao tác đồng thời vừa timeout logical vừa worker kết thúc muộn. Hãy chọn đơn vị đo, định nghĩa mutually-exclusive terminal labels và dùng nhãn/cardinality thấp.

### 12.1. Truyền exception đúng nghĩa

`CompletableFuture.join()` thường ném `CompletionException` khi future hoàn tất exceptionally; `get()` có thể dùng `ExecutionException`. Advice/metric cần phân biệt wrapper với **root cause** để ghi mã lỗi có ý nghĩa, nhưng không được làm mất stack/cause khi truyền lỗi cho caller.

Không chuyển `CancellationException` thành lỗi nghiệp vụ “invalid input”. Không ghi exception message không kiểm soát vì nó có thể chứa secret. Với `whenComplete`, một observer ném exception có thể làm stage dẫn xuất hoàn tất khác với điều mong muốn; hãy test việc exporter hỏng và bảo toàn outcome theo thiết kế.

## 13. Ownership, cleanup và chống rò context

Khi một aspect thêm callback, context wrapper hoặc deadline scheduler, nó cũng có trách nhiệm quản lý tài nguyên **do chính nó tạo ra**.

| Tài nguyên | Chủ sở hữu khả dĩ | Cách test cleanup |
| --- | --- | --- |
| ThreadLocal context được install bởi wrapper | Wrapper/scope helper | Sau success/error/cancel, worker thấy giá trị cũ hoặc null |
| Span logical operation | Observer lifecycle | Span đóng một lần đúng terminal outcome |
| Scheduled timeout handle | Deadline owner | Hủy timer khi operation đã kết thúc, không tích tụ |
| CompletableFuture listener/closure | Stage/observer | Không giữ full request/payload lớn vô hạn |
| Database connection | Worker/transaction boundary | Chỉ đóng khi resource không còn được dùng, không ở caller timeout giả |
| Executor/task queue | Service runtime | Shutdown/reject/bounded queue theo chính sách |
| Physical cancellation token | Worker owner | Signal được nhận, task cleanup hoàn tất hoặc bị đánh dấu còn chạy |

Không được đóng connection tại `finally` của advice bao quanh method trả stage nếu worker vẫn đang sử dụng connection đó. Tương tự, một callback chạy khi caller timeout không thể tùy tiện giải phóng buffer mà worker vẫn đọc.

### 13.1. Bẫy restore context

Sai:

~~~java
// Minh họa anti-pattern, không phải chương trình độc lập.
CONTEXT.set(captured);
command.run();
CONTEXT.remove(); // Bỏ qua nếu command ném exception.
~~~

Đúng về cấu trúc:

~~~java
// Minh họa cấu trúc, cần khai báo CONTEXT/captured/command.
Context previous = CONTEXT.get();
try {
    CONTEXT.set(captured);
    command.run();
} finally {
    if (previous == null) CONTEXT.remove();
    else CONTEXT.set(previous);
}
~~~

Khi `captured == null`, một helper tổng quát có thể dùng `remove()` thay vì `set(null)`. Test cả trường hợp `previous` có giá trị khi tác vụ chạy lồng nhau, không chỉ thread trống.

## 14. Kiểm thử bằng fake clock, latch và recorder

Các test phụ thuộc `sleep(50)`, timeout 100 ms và “hy vọng callback đã chạy” thường flaky trong CI. Một phương án tốt hơn:

1. **Fake clock / injected ticker:** điều khiển deadline mà không chờ thời gian thật. Với thời lượng trong một tiến trình, dùng nguồn đồng hồ đơn điệu như `System.nanoTime()` hoặc ticker trừu tượng.
2. **Manual executor:** gom `Runnable` vào queue, cho test quyết định khi nào chạy; hữu ích để kiểm tra capture-at-submit, cleanup và rejection.
3. **Controllable future:** giữ `CompletableFuture` pending, rồi chủ động `complete`/`completeExceptionally`/`cancel` ở đúng thời điểm.
4. **Latch/barrier:** với integration test có thread thật, dừng worker ở một mốc xác định để tạo race.
5. **Deterministic recorder:** ghi event (operation ID, thread, lifecycle, outcome), không lọc/sampling.
6. **Fake telemetry sink:** cố ý ném lỗi, chặn, trả chậm hoặc đầy queue để kiểm tra isolation với nghiệp vụ.
7. **Constrained executor:** dùng một worker để xác minh tái sử dụng thread, nhiều worker để kiểm tra concurrent isolation.

Một trình tự test capture-at-submit không dùng sleep:

~~~text
1. Khóa manual executor ở trạng thái chưa chạy task.
2. Caller thiết lập context A và submit.
3. Caller đổi sang context B hoặc xóa context.
4. Cho manual executor chạy task đã xếp.
5. Assert task thấy snapshot A.
6. Assert context caller và executor được restore đúng.
~~~

Một trình tự test timeout-vs-success:

~~~text
1. Tạo pending operation và recorder đếm terminal events.
2. Dùng barrier giữ worker trước điểm complete.
3. Kích hoạt timeout bằng fake scheduler.
4. Thả worker để complete success muộn.
5. Assert chỉ một logical terminal event, nhưng physical event
   có thể xảy ra sau; không rò resource.
6. Đảo thứ tự: success trước, timeout đến muộn.
7. Lặp dưới nhiều interleaving, không dựa vào sleep.
~~~

**Chú ý:** các mô hình trên là kế hoạch test, không phải code chạy độc lập. Các API như fake scheduler/manual executor là abstraction bạn cần tự cung cấp hoặc chọn từ bộ công cụ test; JDK không tự có một fake clock dùng chung cho mọi scheduler.

## 15. Khía cạnh bảo mật của context propagation

### 15.1. Context không phải giấy ủy quyền vĩnh viễn

Nếu một background task được submit khi principal có quyền, nhưng quyền bị thu hồi trước khi worker thực thi, quyết định nào có hiệu lực? Không có đáp án chung cho mọi nghiệp vụ.

Hợp đồng có thể chọn:

- **Authorization tại submit:** cho phép task thực thi với quyền được xác nhận ở thời điểm chấp nhận lệnh, nếu mô hình nghiệp vụ cho phép.
- **Authorization tại execution:** kiểm tra lại quyền tại lúc worker thực sự truy cập tài nguyên.
- **Hai tầng kiểm tra:** lọc từ sớm rồi xác thực resource/tenant và trạng thái hiện tại ở operation boundary.

Aspect propagation chỉ chuyển context; **authorization policy** và nguồn quyền tin cậy phải được kiểm thử riêng. Không tự cấp default admin khi worker không có principal.

### 15.2. Không rò tenant qua thread pool

Một worker xử lý dữ liệu tenant A rồi tenant B là tình huống nhạy cảm hơn mất trace ID. Nếu `ThreadLocal<TenantContext>` không được reset, câu truy vấn tiếp theo có thể thực thi dưới tenant sai.

Test phải ép **A -> B -> request không context** trên cùng thread, bao gồm A thất bại. Đối với dữ liệu thực, thêm kiểm tra quyền ở tầng tin cậy/datastore; chỉ dựa vào ThreadLocal ở aspect dễ bị bypass bởi code không qua wrapper.

### 15.3. Tránh context chứa secret

Không đẩy access token thô hoặc toàn bộ request object vào closure/future sống lâu chỉ để log correlation ID. Context nên nhỏ, bất biến, chỉ chứa metadata cần thiết với chính sách retention và logging rõ ràng. Nếu principal được truyền, bảo đảm người đọc telemetry không nhận thông tin quá phạm vi.

## 16. Advice order, retry và context trong một logical operation

Một hệ thống có thể áp nhiều aspect:

~~~text
Tracing -> Retry -> Context -> Task
~~~

hoặc:

~~~text
Retry -> Tracing -> Context -> Task
~~~

Thứ tự quyết định:

- Trace đại diện **một logical operation** hay **mỗi attempt**.
- Deadline bị reset trên mỗi attempt hay là một ngân sách tuyệt đối chung.
- Context được capture một lần hay từng attempt.
- Metrics đếm logical calls, attempts, failures hay cancellations.
- Callback ở nhánh nào có quyền kết thúc span và khi nào.

Với retry của tác vụ bất đồng bộ, **mỗi attempt có thể hoàn tất ở thời điểm khác nhau**. Nếu attempt 1 bị timeout nhưng worker vẫn chạy, attempt 2 có thể nhân side effect. Việc dùng context giống nhau không tự bảo đảm idempotency; cần idempotency key và contract operation phù hợp.

Một integration test cần chủ động làm attempt 1 chậm, khởi chạy attempt 2 theo policy, rồi hoàn tất attempt 1 muộn. Kiểm tra rằng chỉ một logical terminal outcome được công bố, metric attempts phản ánh số lần chạy thật và side effect không bị lặp trái hợp đồng.

## 17. Kiểm tra tính đúng của pointcut bất đồng bộ

Một pointcut có thể chọn method `enqueue(...)`, `submit(...)` hoặc `process(...)`; chúng có semantics khác nhau. Nếu aspect “đo toàn bộ xử lý” nhưng pointcut chỉ chặn `enqueue`, nó sẽ chỉ đo thời gian đưa task vào queue.

Hãy lập bảng cho từng boundary:

| Join point / method | Mục đích | Kỳ vọng |
| --- | --- | --- |
| `submitTask` | Đo thời gian tiếp nhận | Trả handle được ghi nhận, không ghi business success |
| `worker.executeTask` | Đo thời gian physical execution | Worker-start/worker-stop đúng thread |
| `CompletionStage` terminal callback | Đo logical outcome | Success/error/cancel theo contract |
| `executor.execute` | Capture/install context khi submit | Không giữ nhầm context |
| `thenApplyAsync`/nested submit | Propagate sang executor mới | Context đúng tại callback tiếp theo |
| `timeout watcher` | Phát deadline state | Không đóng tài nguyên vật lý quá sớm |

Với AOP dựa trên proxy, lời gọi nội bộ trực tiếp có thể bypass. Với weaving tại method execution, self-call vào method đã weave vẫn có thể kích hoạt advice. Nhưng cả hai **không tự chặn một callback của thư viện khác** nếu điểm đó ngoài phạm vi instrumentation. Kiểm thử theo cơ chế thực tế, không giả định advice có mặt ở mọi đường chạy.

Một câu hỏi quan trọng: “Sau khi `processAsync` trả future, aspect còn giữ được context để quan sát completion không?” Nếu không, callback có thể không gắn được đúng operation. Test bằng cách xóa context caller ngay sau submit và hoàn tất task về sau.

## 18. Metric, tracing và audit phải có định nghĩa riêng

Đối với một trace:

- **Span invocation:** bắt đầu tại method entry, kết thúc lúc trả handle.
- **Span logical operation:** bắt đầu tại yêu cầu và kết thúc theo logical terminal outcome.
- **Span worker:** theo vòng đời vật lý của task.
- **Span attempt:** một lần thử của retry policy.

Không nên tạo một span duy nhất rồi đánh dấu success tại mọi mốc. Nếu span logic đã đóng do timeout, worker muộn có thể phát span/metric **physical late completion** riêng, không mở lại span đã đóng.

Đối với metric:

~~~text
async_calls_total               -> số lời gọi nhận được
async_submit_failures_total     -> lỗi ở bước submit
async_logical_completed_total   -> logical outcome theo nhãn
async_worker_finished_total     -> worker thực sự hoàn tất
async_context_missing_total     -> thiếu context tại boundary cần có
async_observer_failures_total   -> lỗi telemetry/export riêng
~~~

Không có nghĩa tất cả metric đều cần thiết; chọn những metric giúp trả lời câu hỏi vận hành cụ thể và có cardinality thấp. Đừng gắn trace ID hay principal vào labels metric có thể bùng nổ số chuỗi thời gian.

Nếu **audit event** có yêu cầu bảo đảm đầy đủ và bền vững, không thay bằng log debug có sampling hoặc callback dễ bị bỏ khi tiến trình chết. Việc audit thành công hay thất bại có thể ảnh hưởng hợp đồng nghiệp vụ theo chính sách riêng; đừng áp cùng quy tắc “telemetry error bị bỏ” một cách mù quáng.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa/test |
| --- | --- | --- |
| `after returning` đồng nghĩa nghiệp vụ xong | Báo success trước async failure | Test stage pending và completion |
| `ThreadLocal` tự lan qua executor | Worker thiếu/mang sai context | Test raw executor vs context wrapper |
| Không restore trong `finally` | Leak tenant/trace khi tái sử dụng thread | Test A lỗi rồi B chạy cùng worker |
| Callback luôn chạy trên worker | Flaky hoặc mất context nếu stage đã complete | Test pending/already-completed stage |
| Future timeout nghĩa worker dừng | Giải phóng resource sớm, side effect muộn | Test logical vs physical lifecycle |
| `cancel(true)` chắc chắn interrupt worker | Báo hủy sai | Kiểm tra cơ chế cancellation thực |
| Dùng `sleep` để tạo race | Test không ổn định | Manual executor, latch, fake scheduler |
| Dùng một boolean không atomic cho terminal state | Double metric/span close khi đua | Atomic transition và test interleavings |
| Advice trả stage dẫn xuất mà không xét cancel | Khác contract Future gốc | Test identity/cancel propagation |
| Callback observer ném lỗi | Có thể thay outcome stage dẫn xuất | Bắt lỗi telemetry trong vùng hẹp |
| Dùng context mutable chia sẻ | Request đổi context sau submit ảnh hưởng worker | Immutable snapshot và test thay sau submit |
| Mọi async step dùng cùng executor ngầm | Mất context ở nested stage | Test từng submit/thenApplyAsync boundary |
| Log toàn bộ context | Rò principal/token/secret | Allowlist/redaction, test negative |
| Retry lệnh ghi sau timeout không rõ trạng thái | Nhân đôi side effect | Test idempotency và late completion |
| Chỉ test advice nhưng không test weaving | Worker/callback không được chặn ngoài ý định | Integration test artifact/runtime thật |
| Counter lỗi đồng bộ = lỗi async | Sai error rate và thời gian | Tách submission failure và terminal failure |

## 20. Checklist kiểm thử trước khi phát hành

1. **Chọn join point đúng:** đang chặn method entry/return, task start, hay terminal completion? Có đường bypass không?
2. **Nêu rõ completion contract:** result, exception, timeout, cancellation và unknown outcome được định nghĩa thế nào?
3. **Capture-at-submit:** context được chụp đúng lúc và bất biến trong lúc queue chờ?
4. **Propagation đủ mọi boundary:** executor đầu, nested executor, callback async, scheduled job và fan-out/fan-in?
5. **Cleanup bảo đảm:** có `finally`, restore previous, test reuse thread cả success/error/cancel?
6. **Context bảo mật:** principal/tenant đáng tin, không có default privilege và không ghi dữ liệu nhạy cảm?
7. **Observer đúng mốc:** counter logical outcome chỉ tăng khi completion, không phải lúc trả handle?
8. **Already-completed stage:** callback gắn muộn vẫn chạy đúng một lần và không lệ thuộc thread cụ thể?
9. **Race được kiểm soát:** completion vs timeout/cancel có single-winner, không double-close?
10. **Timeout khác dừng vật lý:** tài nguyên chỉ dọn khi owner/worker không còn dùng, có kiểm thử late completion?
11. **Exception nguyên vẹn:** synchronous rejection, asynchronous failure, CompletionException/cancellation phân loại rõ?
12. **Result stage semantics:** nếu thay stage gốc bằng derived stage, cancellation/identity và propagation có phù hợp API contract?
13. **Tải và lỗi telemetry:** exporter chậm/hỏng không làm phá business outcome, queue có giới hạn?
14. **Composition:** retry, transaction, tracing và context advice có thứ tự đã được kiểm thử?
15. **CI ổn định:** fake clock, manual executor, latch và recorder; không dùng sleep ngẫu nhiên?
16. **Kiểm thử runtime thực:** đúng classpath, weaving/proxy, class loader, async executor và cấu hình deploy?

**Kết luận:** kiểm thử aspect bất đồng bộ không chỉ là xác nhận “advice có chạy”. Phải chứng minh **điểm bắt đầu/hoàn tất được hiểu đúng, context được capture và restore qua mọi ranh giới thực thi, lỗi/hủy/timeout không bị đánh đồng, và nhiều sự kiện đua nhau không gây mất dữ liệu hay đóng tài nguyên hai lần**. Một bộ test có điều khiển state/future/executor sẽ phát hiện các lỗi ấy đáng tin hơn các test chỉ dựa vào log và thời gian ngủ.
