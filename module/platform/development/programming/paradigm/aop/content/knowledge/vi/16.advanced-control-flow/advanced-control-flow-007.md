# Luồng bất đồng bộ, callback và giới hạn suy diễn quan hệ gọi trong AOP

> **Mục tiêu học tập:** Hiểu điểm khác nhau giữa lời gọi đồng bộ, tác vụ bất đồng bộ, callback, continuation và luồng điều khiển động trong Aspect-Oriented Programming (AOP). Phân biệt **đăng ký callback** với **thực thi callback**, **method trả Future** với **công việc hoàn tất**, **quan hệ call-stack** với **quan hệ nhân quả logic**. Nhận ra giới hạn của pointcut dựa trên control flow khi chuyển thread; biết dùng metadata tương quan tường minh, dọn context, xử lý lỗi và kiểm thử. Bài nói về các khái niệm Aspect cơ bản/nâng cao nói chung, không gắn với một framework AOP cụ thể. Hai chương trình Java 17 độc lập có lệnh chạy và đầu ra xác định.

## 1. Vì sao bất đồng bộ thay đổi cách hiểu “ai gọi ai”?

Trong một call stack đồng bộ, khi A gọi B, có thể quan sát:

~~~text
A enters
    B enters
    B returns
A returns
~~~

Trong mô hình bất đồng bộ:

~~~text
Thread T1:
    A submits task
    A returns

Thread T2:
    task starts later
    task performs B
    task completes

Some callback:
    observes completion
~~~

B vẫn có thể thuộc cùng yêu cầu logic với A, nhưng lúc B thực thi, **stack frame của A có thể đã biến mất**. Việc A đã gửi task không chứng minh B đang chạy dưới dynamic call stack của A.

Vì vậy phải tách ba câu hỏi: **ai lập lịch công việc**, **ai đang thực thi trên thread hiện tại**, và **quan hệ logic/nhân quả giữa hai bước được biểu diễn ra sao**.

## 2. Các khái niệm AOP nền tảng

**Join point** là một loại điểm/sự kiện trong mô hình thực thi mà công cụ có thể nhận diện. **Pointcut** là điều kiện chọn điểm. **Advice** là hành vi bổ sung tại điểm được chọn. **Weaving hoặc interception** là cơ chế kết hợp advice với chương trình.

Một số mô hình có pointcut dựa trên **dynamic control flow**: chọn những join point nằm trong phạm vi hoạt động động của một join point khác. Điều đó không tự đồng nghĩa logical flow qua nhiều thread.

Không phải mọi công cụ AOP đều hỗ trợ callback registration, callback execution, task submission, constructor, field access hoặc method call với cùng độ bao phủ. Phải kiểm tra **join point model** và **runtime path** trước khi kết luận một event có thể được advice quan sát.

## 3. Bốn loại quan hệ cần phân biệt

| Quan hệ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Synchronous call** | Lời gọi trong call stack hiện tại | handle gọi validate |
| **Submission** | Đưa công việc vào hệ lập lịch | executor.submit |
| **Completion dependency** | Stage sau phụ thuộc sự hoàn tất của stage trước | thenApply sau supplyAsync |
| **Logical correlation** | Hai hoạt động được gắn cùng ngữ cảnh yêu cầu | cùng traceId |

Cùng traceId **không chứng minh** hai hoạt động có quan hệ caller/callee trực tiếp. Completion dependency **không chứng minh** callback cùng stack với method đăng ký nó.

Một sơ đồ AOP đúng cần xác định **mỗi loại quan hệ dựa trên dữ kiện nào**, không gộp tất cả thành “flow”.

## 4. Đồng bộ: phạm vi cflow còn trên stack

Sơ đồ:

~~~text
process()
   validate()
      check()
   load()
process() returns
~~~

Nếu công cụ AOP có control-flow pointcut, các join point của validate, check hoặc load có thể được chọn theo phạm vi process **khi process đang hoạt động**, theo chính xác định nghĩa của công cụ.

Các lưu ý:

- Pointcut theo control flow là điều kiện **động**, không chỉ nhìn biểu đồ gọi tĩnh.
- Các nhánh không được thực thi không tạo join point runtime tương ứng.
- Recursive/nested calls có nhiều invocation của cùng method.
- Một around advice phía ngoài có thể short-circuit khiến điểm phía trong không xuất hiện.
- Một số mô hình phân biệt tính cả điểm mở đầu control flow với chỉ tính các điểm phía dưới, thường bằng các biểu thức như cflow/cflowbelow.

Tên và ngữ nghĩa các biểu thức đó **không phải API chung của mọi AOP runtime**.

## 5. Chuyển thread: cflow không mặc nhiên đi theo task

Khi A submit Runnable rồi return:

~~~text
T1 stack: A → executor.submit(...) → return
T2 stack: workerLoop → task.run() → work()
~~~

Task chạy trên T2 có **call stack khác**. Một pointcut quan sát động cflow của A trên T1 không tự mở rộng sang T2 chỉ vì task đã được A tạo.

Một engine có thể có extension hỗ trợ ngữ cảnh bất đồng bộ, nhưng phải xem hợp đồng của extension. Nếu không, cần một **correlation/scope propagation** rõ ràng, độc lập với ngữ nghĩa call stack.

**Logical request lifetime có thể dài hơn lifetime của từng method invocation hoặc từng thread.**

## 6. Method call khác method execution

Trong code bất đồng bộ có những sự kiện khác nhau:

~~~text
Caller calls executor.submit(task)
Executor processes submission
Worker later calls task.run()
Task executes work()
~~~

Nếu mô hình hỗ trợ cả method call và method execution, mỗi sự kiện có thể có join point riêng. Một aspect trên **method call của submit** không tự động là aspect trên **method execution của run**.

Một proxy bao executor có thể quan sát việc submit nhưng không chắc quan sát code bên trong Runnable. Một cơ chế weaving method execution có thể quan sát task.run khi bytecode ấy đã được dệt, nhưng vẫn không tự suy ra request cha từ thread khác.

Do đó **độ bao phủ can thiệp** và **gắn quan hệ nhân quả** là hai bài toán độc lập.

## 7. Callback registration khác callback execution

Xét:

~~~text
future.thenApply(callback)   // registration
...
callback.apply(value)        // execution
~~~

Registration không đồng nghĩa execution. Callback có thể chạy sau, trên thread khác, hoặc nhánh callback kiểu success có thể không chạy nếu upstream future hoàn tất exceptionally.

Khi viết advice, hỏi:

1. Đang chọn lời gọi API đăng ký callback?
2. Đang chọn method execution của callback?
3. Đang chọn event future hoàn tất?
4. Đang chọn kết quả cuối của cả chuỗi?

Bốn event này không thể tự thay nhau. Một log “callback registered” không chứng minh callback đã chạy, càng không chứng minh nó đã thành công.

## 8. Callback không bảo đảm luôn có thread mới

Với CompletableFuture, các dependent actions dạng không Async có thể chạy trên một thread tham gia completion hoặc thực hiện dependent registration theo hợp đồng API. Những dạng Async sử dụng facility/executor được xác định.

Đừng suy rằng:

- thenApply luôn chạy trên thread đăng ký.
- thenApplyAsync luôn mở thread mới cho từng callback.
- Callback nào đăng ký trước chắc chắn thực thi trước.
- Một callback đang chạy có cùng ThreadLocal context với caller.
- Callback được đăng ký một lần thì phần thân chắc chắn được vào một lần trong mọi kết quả completion.

Hãy dùng executor và ranh giới completion thật để xác định điều được phép kết luận.

## 9. Method trả Future chưa phải task hoàn tất

Một operation có thể:

~~~text
submitAsync()
    schedules task
    returns CompletableFuture immediately

later:
    task starts
    task finishes
    future completes
~~~

Advice quanh method submitAsync có thể thấy **normal return** ngay khi trả handle. Nếu task sau đó ném exception, một after-throwing advice chỉ quanh method submitAsync không nhất thiết thấy lỗi ấy.

Cần phân biệt:

- **Submission latency:** thời gian caller thực hiện lời gọi lập lịch.
- **Execution duration:** thời gian worker thực sự chạy task.
- **End-to-end latency:** thời gian từ root boundary tới logical completion đã định nghĩa.

Không đặt tên metric end-to-end nếu advice chỉ đo tới lúc method trả Future.

## 10. ThreadLocal không tự là context của request async

Java ThreadLocal gắn giá trị với **thread hiện tại**. Nếu caller T1 set requestId=R1 rồi submit task cho T2, ThreadLocal thường trên T2 không tự có R1.

~~~text
T1: context=R1
    submit task

T2: context may be absent
    execute task
~~~

T2 còn có thể mang **stale context từ task trước** nếu code quên cleanup trên thread pool.

Vì vậy cần:

- Capture một snapshot được phép ở ranh giới submit.
- Truyền tường minh snapshot tới task/callback.
- Worker tự cài scope trên thread thực thi.
- Worker dọn scope trong finally hoặc cơ chế tương đương khi hoàn tất.
- Không cố remove entry của worker từ caller thread.

Correlation ID được sao chép đúng không đồng nghĩa dynamic cflow pointcut đã mở rộng qua thread.

## 11. Ví dụ Java 17 số 1: giới hạn ThreadLocal qua executor

Chương trình dùng một executor có một worker, để thứ tự output xác định. Nó cho thấy lời gọi đồng bộ thấy context, task không bọc không tự thấy, task có snapshot cài context đúng rồi remove.

Đây là Java thuần, **không phải một engine weaving**.

Lưu **AsyncBoundaryDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncBoundaryDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static void synchronousWork() {
        System.out.println("[sync] context=" + CONTEXT.get());
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            CONTEXT.set("REQ-1");
            try {
                System.out.println("[main] context=" + CONTEXT.get());
                synchronousWork();

                executor.submit(() ->
                    System.out.println("[worker-unwrapped] context="
                            + CONTEXT.get())
                ).get();

                String snapshot = CONTEXT.get();
                executor.submit(() -> {
                    CONTEXT.set(snapshot);
                    try {
                        System.out.println("[worker-wrapped] context="
                                + CONTEXT.get());
                    } finally {
                        CONTEXT.remove();
                        System.out.println("[worker-wrapped] cleared="
                                + CONTEXT.get());
                    }
                }).get();

                System.out.println("[main] after-submit="
                        + CONTEXT.get());
            } finally {
                CONTEXT.remove();
                System.out.println("[main] cleared=" + CONTEXT.get());
            }
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy bằng JDK 17:

~~~bash
javac AsyncBoundaryDemo.java
java AsyncBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
[main] context=REQ-1
[sync] context=REQ-1
[worker-unwrapped] context=null
[worker-wrapped] context=REQ-1
[worker-wrapped] cleared=null
[main] after-submit=REQ-1
[main] cleared=null
~~~

### 11.1. Đọc kết quả

Lời gọi synchronousWork dùng **cùng main thread** nên thấy REQ-1. Task unwrapped chạy trên worker khác nên không có ThreadLocal của main. Task wrapped được truyền snapshot qua lambda và chủ động set trên worker.

Worker remove không ảnh hưởng ThreadLocal entry của main, vì mỗi thread có binding riêng. Main remove trong finally của chính nó.

### 11.2. Giới hạn của demo

Task wrapped dùng set/remove đơn giản vì worker ban đầu không có context cha hợp lệ. Nếu nested scope có previous context, cần **restore previous**, không remove mù quáng.

Ví dụ chỉ truyền một String không nhạy cảm. Trong thực tế, snapshot nên bất biến, nhỏ và chỉ gồm dữ liệu được phép. Context logic cần lifecycle riêng nếu task sống lâu hơn request ban đầu.

## 12. Root scope và nested scope không được dọn giống nhau

Một scope gốc:

~~~text
before: no context
enter A
execute
close A: remove
~~~

Một scope lồng:

~~~text
enter A
    enter B
    close B: restore A
close A: remove
~~~

Nếu mọi advice luôn remove ở cuối, inner B có thể phá context của A trong cùng call stack.

Một scope abstraction nên lưu:

1. Previous value trước khi enter.
2. Owner thread.
3. Installed value.
4. Trạng thái đã đóng.
5. Quy tắc close LIFO.

**ThreadLocal.remove từ thread khác chỉ tác động tới thread đang gọi**, không dọn hộ worker. Với async, mỗi execution boundary nên tự open/close scope.

## 13. InheritableThreadLocal không giải quyết per-task propagation

InheritableThreadLocal có khả năng khởi tạo giá trị cho thread con khi thread được tạo. Thread pool lại thường giữ worker sống lâu và giao rất nhiều task sau đó.

Một value được kế thừa lúc tạo worker **không đại diện chắc chắn cho request hiện tại** khi worker chạy task thứ mười nghìn.

Không xem InheritableThreadLocal là cơ chế truyền ngữ cảnh cho mỗi submit mặc định. Cần kiểm tra thời điểm tạo thread, ranh giới task, capture, cleanup và nguồn dữ liệu.

## 14. CompletableFuture có nhiều ranh giới completion

Một chuỗi:

~~~text
Caller registers supplier
    |
supplyAsync returns future F
    |
Worker executes supplier
    |
F completes normally or exceptionally
    |
dependent callback becomes eligible
    |
callback executes
    |
downstream future G completes
~~~

Điều quan trọng:

- F trả về caller trước khi F hoàn tất là điều bình thường.
- Callback được **đăng ký** không có nghĩa đã chạy.
- Một nhánh success callback có thể không thực thi khi F exceptional.
- Callback có thể tự lỗi, khiến G exceptional dù F normal.
- Callback recovery có thể khiến G normal dù F exceptional.
- G có outcome riêng, không chỉ là “một log bổ sung” của F.

Để đo logical request, phải chọn đúng future/stage đại diện cho ranh giới completion cần quan sát.

## 15. TraceId, spanId và parent không tự suy ra từ stack khác thread

Một mô hình quan sát có thể có:

~~~text
traceId = T-1
root span = R
task span = A, parent=R
callback span = C, parent=A
~~~

Các quan hệ parent được **mô hình hóa tường minh**, không tự xuất hiện từ việc task có cùng traceId.

Hai events cùng traceId chỉ chứng minh chúng được gắn cùng mã tương quan trong dữ liệu. Từ đó không tự suy:

- Event thứ nhất gọi trực tiếp event thứ hai.
- Chúng chạy trên cùng thread.
- Chúng thuộc cùng dynamic control flow pointcut.
- Chúng có quan hệ parent-child.
- Cả hai thành công.
- Metadata có nguồn tin cậy.

Với fan-in, một event có thể phụ thuộc nhiều nguồn và cần **links** hoặc mô hình dependency khác thay vì gán bừa một parent duy nhất.

## 16. Ví dụ Java 17 số 2: callback và causal metadata tường minh

Ví dụ dùng record bất biến mang traceId/spanId/parentSpanId qua các stage, rồi minh họa exceptional completion và recovery.

Lưu **AsyncCallbackTraceDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncCallbackTraceDemo {
    record Trace(String traceId, String spanId, String parentSpanId) {}

    record StepResult(String value, Trace trace) {}

    static String describe(Trace t) {
        return "trace=" + t.traceId()
                + " span=" + t.spanId()
                + " parent=" + t.parentSpanId();
    }

    static Throwable unwrap(Throwable error) {
        if (error instanceof CompletionException
                && error.getCause() != null) {
            return error.getCause();
        }
        return error;
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Trace root = new Trace("T-1", "root", "-");
            System.out.println("[caller] " + describe(root));

            CompletableFuture<StepResult> task =
                    CompletableFuture.supplyAsync(() -> {
                        Trace child = new Trace("T-1", "task", "root");
                        System.out.println("[task] " + describe(child));
                        return new StepResult("OK", child);
                    }, executor);

            CompletableFuture<String> callback =
                    task.thenApplyAsync(result -> {
                        Trace next = new Trace(
                                result.trace().traceId(),
                                "callback", result.trace().spanId());
                        System.out.println("[callback] "
                                + describe(next));
                        return result.value() + "-DONE";
                    }, executor);

            System.out.println("[caller] result=" + callback.join());

            CompletableFuture<String> failed =
                    CompletableFuture.supplyAsync(() -> {
                        System.out.println("[failed-task] execute");
                        throw new IllegalStateException("boom");
                    }, executor);

            CompletableFuture<String> recovered =
                    failed.handleAsync((value, error) -> {
                        if (error != null) {
                            Throwable cause = unwrap(error);
                            System.out.println("[error-callback] "
                                    + cause.getClass().getSimpleName()
                                    + ": " + cause.getMessage());
                            return "RECOVERED";
                        }
                        return value;
                    }, executor);

            System.out.println("[caller] error-result="
                    + recovered.join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac AsyncCallbackTraceDemo.java
java AsyncCallbackTraceDemo
~~~

**Stdout chính xác:**

~~~text
[caller] trace=T-1 span=root parent=-
[task] trace=T-1 span=task parent=root
[callback] trace=T-1 span=callback parent=task
[caller] result=OK-DONE
[failed-task] execute
[error-callback] IllegalStateException: boom
[caller] error-result=RECOVERED
~~~

### 16.1. Cha–con là metadata đã thiết kế

Task có parent=root **vì code đặt vậy**; callback có parent=task **vì StepResult đưa metadata từ task sang callback**. Không có thao tác suy từ call stack của main sang worker.

Đây là ví dụ về cách xây một **correlation model có chủ đích**, chứ không chứng minh mọi async callback phải là span con của future supplier.

### 16.2. Vì sao error callback thấy boom?

Supplier thất bại, failed future hoàn tất exceptionally. handleAsync nhận error, unwrap một lớp CompletionException nếu có và ghi IllegalStateException: boom.

Sau khi handleAsync trả RECOVERED, **downstream future hoàn tất bình thường**. Điều này không làm task gốc “chưa từng thất bại”.

Nên phân biệt **attempt failure** với **recovered final outcome**.

### 16.3. Vì sao stdout ổn định?

Single-thread executor thực thi các task được xếp lịch; caller join vào downstream future trước khi lập lịch nhánh lỗi. Do đó thứ tự các dòng trong ví dụ được xác định mà không cần đoán thread scheduling.

Không suy từ điều này rằng callback của mọi thư viện hoặc các tác vụ trên nhiều worker luôn có cùng thứ tự.

## 17. CompletionException và ExecutionException

Trong Java, lời gọi CompletableFuture.join có thể ném CompletionException bao lỗi gốc. Future.get có thể ném ExecutionException cùng các checked exceptions khác theo API.

Nếu một advice chỉ log lớp wrapper, người đọc có thể không biết lỗi thực sự bắt đầu ở task hay callback nào.

Cần kiểm tra **cause chain** phù hợp, nhưng cũng phải biết exception mới có thể được tạo ở callback và trở thành nguyên nhân của downstream failure.

Đừng dùng việc outer method trả bình thường để kết luận không có async exception. **Exception của task thường được lưu ở future hoặc truyền qua completion callback**, không nhất thiết thoát qua stack của caller khi submit.

## 18. Recovery và observability phải phân biệt ranh giới

Giả sử một task ném IOException E; callback recovery đọc lỗi rồi trả fallback.

~~~text
Task A: FAILED(E)
    |
Recovery callback: returns FALLBACK
    |
Request result stage: NORMAL(FALLBACK)
~~~

Một observer của task có thể ghi failed, trong khi một observer của stage cuối ghi recovered success. Hai kết luận không mâu thuẫn nếu được đặt tên rõ.

Tuy nhiên, fallback phải có nghĩa nghiệp vụ. Một callback không được “nuốt lỗi” chỉ vì muốn giảm số log nếu caller cần exception để rollback, retry hoặc báo lỗi.

## 19. Fan-out tạo nhiều nhánh không có caller trực tiếp

Một request có thể submit hai tasks độc lập:

~~~text
            Request R
             /     \
          Task A   Task B
             \     /
             Combine
~~~

Task A không nhất thiết gọi Task B. Dù log A xuất hiện trước log B, thứ tự log chưa chứng minh quan hệ trực tiếp.

Bước Combine phụ thuộc cả A và B, vì vậy một mô hình chỉ cho một parent không biểu diễn đủ mọi dependency. Có thể dùng links hoặc một causal graph phù hợp.

Không dùng timestamp đơn lẻ để tự phát minh causal edge: scheduling, buffering, clock accuracy và đồng bộ hóa đều ảnh hưởng thứ tự quan sát.

## 20. Fan-in, allOf và điều kiện hoàn tất

Khi nhiều futures được kết hợp, phải phân biệt:

- Từng task đã **bắt đầu** chưa.
- Từng future đã **hoàn tất** chưa.
- Kết quả normal hay exceptional.
- Bước aggregate có thật sự chạy không.
- Aggregate có chỉ chạy khi các dependency normal?
- Caller chờ future nào: một nhánh hay kết quả tổng hợp?

Một advice quan sát submit của Task A chưa đủ chứng minh Task B đã hoàn tất, và cũng chưa đủ để đánh dấu request end-to-end thành công.

Nếu aggregate future exceptional, kiểm tra nguyên nhân từ dependency hoặc callback thay vì gán lỗi cho method submit.

## 21. Multiple callbacks không mặc nhiên là một chuỗi

Một future có thể có callback A, B, C **đăng ký độc lập**. Chúng có thể là ba dependent actions trên cùng upstream stage, không phải A gọi B rồi B gọi C.

~~~text
Future F
  +-- callback A
  +-- callback B
  +-- callback C
~~~

Đừng lập parent span theo thứ tự log A, B, C rồi suy chuỗi A→B→C. Nếu chúng là sibling dependencies, model phải phản ánh mối quan hệ ấy.

Một callback object được đăng ký tại nhiều nơi cũng khác với **một lần execution cụ thể** của callback.

## 22. Retry có thể tạo nhiều task attempts

Một logical request R có thể:

~~~text
R
 +-- Attempt 1: throws E
 +-- Attempt 2: returns OK
 +-- Final outcome: OK
~~~

Nếu metric đếm request và metric đếm task attempts, hai số có thể khác.

Một around advice bên ngoài retry có thể chạy một lần, trong khi advice bên trong retry được vào nhiều lần. Với retry bất đồng bộ, các attempts có thể chạy trên những thread khác nhau và có future riêng.

Một attempt thất bại không chứng minh mọi side effect của nó đã được hoàn tác. Retry cần chính sách idempotency và exception classification rõ.

## 23. Timeout và cancellation không chứng minh task đã dừng

Caller có thể timeout tại T1, nhưng task vẫn chạy tới T2.

~~~text
Caller stops waiting at T1
Worker finishes at T2
T1 precedes T2
~~~

Không được suy khi Future.cancel được gọi thì mọi join point của task đã ngừng xuất hiện ngay.

Nếu policy dùng ThreadLocal cho worker, cleanup phải được thực hiện khi **worker scope thực sự kết thúc**, không phải bằng ThreadLocal.remove từ caller thread.

Tracing nên phân biệt các event như cancel_requested, task_cancelled và task_completed_after_timeout nếu phù hợp.

## 24. Happens-before không phải call-stack ancestry

Một số API đồng bộ Java có **memory consistency guarantees**; ví dụ Future.get trong ExecutorService giúp quan sát kết quả/tác dụng bộ nhớ sau khi task hoàn tất theo hợp đồng.

Nhưng:

- **Happens-before** là quan hệ trong Java Memory Model.
- **Completion dependency** là quan hệ giữa stages theo API.
- **Stack ancestry** là quan hệ caller/callee đang hoạt động.
- **Trace parent/link** là mô hình quan sát được thiết kế.

Chúng không tự thay nhau. Một task có thể có một kết quả được công bố an toàn cho caller mà không bao giờ nằm trên cùng call stack với caller.

## 25. Proxy/weaving và callback coverage

Một proxy chặn executor.submit có thể chỉ quan sát **submission**. Nếu task.run không đi qua proxy, advice của proxy trên submit không tự ghi nhận execution trong task.

Một bytecode weaving engine có thể quan sát task.run nếu class và loại method execution được hỗ trợ, nhưng điều đó vẫn chưa cho biết **request logic nào đã tạo task**.

Đặc biệt, self-invocation, method final/static/private và class loading có thể ảnh hưởng một số cơ chế proxy hoặc weaving khác nhau. Không áp dụng một quy tắc duy nhất cho mọi engine.

Cần kiểm thử **đường gọi thật**, không chỉ biểu thức pointcut.

## 26. Security và dữ liệu context

Trace context có thể chứa actor hoặc tenant. Một snapshot đưa sang worker phải được kiểm duyệt:

- Không tự sao chép token, cookie hoặc raw payload khi không cần.
- Actor/tenant phải đến từ nguồn được xác thực.
- Không dùng traceId trùng như chứng cứ authorization.
- Không giữ object graph lớn qua future có lifetime dài.
- Không dùng static mutable currentRequest trong aspect singleton.
- Không để request B nhận stale context của A vì thread pool reuse.
- Không đưa requestId của từng event vào metrics label có cardinality vô hạn.

Record bất biến giúp giảm rủi ro shared mutation nhưng **không tự bảo đảm nguồn metadata đáng tin**.

## 27. Ma trận kiểm thử bắt buộc

| Tình huống | Điều kiểm tra |
|---|---|
| Đồng bộ A gọi B | Stack relation đúng tại runtime |
| A submit task rồi return | Task execution khác submission |
| Method trả Future | Không đồng nhất với task completed |
| Callback registration | Không đếm như callback execution |
| Worker ThreadLocal mặc định | Không tự copy context caller |
| Task wrapper có snapshot | Worker thấy context đúng |
| Worker finally cleanup | Task tiếp theo không thấy stale context |
| Callback đã đăng ký trên future thất bại | Success transform không bị đánh dấu đã chạy |
| handle recovery | Upstream failed, downstream normal |
| Callback tự ném lỗi | Downstream future exceptional |
| Fan-out A/B | Không bịa A là parent B |
| Fan-in aggregate | Quan hệ nhiều dependencies được biểu diễn |
| Retry hai attempts | Request count khác attempt count |
| Timeout trước task stop | Không ghi task hoàn tất sai |
| Callback trên executor khác | Scope mở/đóng đúng thread |
| Direct target call | Không mặc định đi qua proxy |
| Data context nhạy cảm | Snapshot tối thiểu, nguồn đáng tin |
| Nested context | Restore previous đúng LIFO |

Với concurrent tests, tránh assert một total order chưa được API bảo đảm. Hãy assert **quan hệ thực sự được bảo đảm** và những dữ liệu có ý nghĩa nghiệp vụ.

## 28. Quy trình chẩn đoán khi quan hệ gọi sai

1. Xác định event là call, execution, submit, registration, callback invocation hay completion.
2. Kiểm tra loại join point được engine hỗ trợ.
3. Xác minh call đi qua proxy hoặc bytecode đã được dệt.
4. Xác định thread nào đang chạy từng event.
5. Xác định future/stage nào là upstream/downstream.
6. Kiểm tra callback được đăng ký lúc nào và có thực sự chạy không.
7. Kiểm tra executor và dạng callback Async/non-Async.
8. Tìm nơi capture và propagate context.
9. Kiểm tra scope cleanup và stale ThreadLocal.
10. Phân biệt traceId với spanId và parent/link.
11. Kiểm tra fan-out/fan-in và nhiều dependencies.
12. Phân biệt attempt failure với final outcome.
13. Xem exception cause và completion wrapper.
14. Kiểm tra cancellation/timeout khi task vẫn chạy.
15. Tạo test tái hiện có executor/scope rõ ràng.

Không chỉ sửa thứ tự logging cho “đúng” nếu metadata về causal edges vẫn sai.

## 29. Những ngộ nhận thường gặp

**Ngộ nhận 1:** callback đăng ký đồng nghĩa callback chạy.

**Ngộ nhận 2:** method trả Future nghĩa là task xong.

**Ngộ nhận 3:** dynamic control flow của caller tự kéo dài qua thread pool.

**Ngộ nhận 4:** ThreadLocal tự mang context tới worker.

**Ngộ nhận 5:** InheritableThreadLocal tự truyền đúng value cho từng task trong pool.

**Ngộ nhận 6:** cùng traceId chứng minh trực tiếp caller/callee.

**Ngộ nhận 7:** log A trước B chứng minh A tạo B.

**Ngộ nhận 8:** mọi callbacks của một future có parent là callback trước.

**Ngộ nhận 9:** chỉ cần chặn submit thì đã đo task execution duration.

**Ngộ nhận 10:** after-returning của method submit chứng minh logical work succeeded.

**Ngộ nhận 11:** after-throwing quanh submit tự thấy exception task ném sau này.

**Ngộ nhận 12:** retry chỉ lặp business, không lặp advice bên trong.

**Ngộ nhận 13:** Future.cancel chắc chắn ngừng task lập tức.

**Ngộ nhận 14:** quan hệ happens-before tự định nghĩa trace parent.

**Ngộ nhận 15:** task.run được weave tự có parent request metadata.

Các lỗi này có chung gốc: **đồng nhất các boundary khác nhau**.

## 30. Checklist thiết kế advice cho hệ bất đồng bộ

- [ ] Đã định nghĩa event mình cần quan sát chính xác chưa?
- [ ] Pointcut chỉ chọn loại join point được công cụ hỗ trợ?
- [ ] Có phân biệt submit với task start và completion?
- [ ] Có phân biệt callback registration với execution?
- [ ] Có phân biệt method return với Future completion?
- [ ] Có dùng dynamic cflow đúng giới hạn, không suy xuyên thread tùy ý?
- [ ] Có snapshot context được tạo và truyền tại boundary đúng?
- [ ] Worker tự mở và dọn context đúng thread?
- [ ] Nested context restore previous đúng LIFO?
- [ ] Có phân biệt parent với link và correlation?
- [ ] Fan-out/fan-in được mô hình hóa đúng dependencies?
- [ ] Recovery và retry được tính đúng theo attempts/outcomes?
- [ ] Có theo dõi exceptional completion và cause?
- [ ] Timeout/cancel không bị coi là task stop tức thời?
- [ ] Không ghi dữ liệu nhạy cảm hoặc raw context quá mức?
- [ ] Tests không giả định thread scheduling/order vô căn cứ?
- [ ] Có integration test về proxy/weaving coverage thực tế?

## 31. Bài tập tự kiểm tra

### Câu 1: cflow và executor

A submit task rồi return. Task chạy trên thread khác sau đó. Có mặc định task thuộc dynamic cflow đang hoạt động của A không?

**Đáp án:** không. Scheduling relation và call-stack extent là hai khái niệm khác nhau.

### Câu 2: Callback

Log cho thấy đã đăng ký thenApply nhưng future upstream hoàn tất exceptionally. Có chứng minh transform chạy không?

**Đáp án:** không. Callback normal thường không được vào trên exceptional path.

### Câu 3: Method return

Advice quanh submitWork thấy return Future bình thường. Có chắc work đã xong?

**Đáp án:** không. Task có thể chạy sau và thất bại.

### Câu 4: TraceId

A và B có traceId=T1. Có chắc A trực tiếp gọi B?

**Đáp án:** không. Cần parent/link hoặc causal edge có bằng chứng.

### Câu 5: ThreadLocal

Caller set context=R1, worker dùng cùng ThreadLocal key. Worker có tự nhận R1 không?

**Đáp án:** ThreadLocal thường không tự chuyển value qua thread. Cần propagation thích hợp.

### Câu 6: Fan-in

Một callback kết hợp hai futures A/B. Có phải callback chỉ cần parent=A vì A log trước B?

**Đáp án:** không. Nó phụ thuộc cả hai; có thể cần links/graph dependencies.

### Câu 7: Recovery

Task ném lỗi, handle callback trả RECOVERED. Có phải task thành công?

**Đáp án:** không. Upstream thất bại, downstream được phục hồi.

### Câu 8: Retry

Một request retry ba attempts. Số request và số attempts có cần bằng nhau?

**Đáp án:** không.

### Câu 9: Timeout

Caller timeout trước khi worker dừng. Có thể đánh dấu task hoàn tất ngay lúc caller timeout không?

**Đáp án:** không nếu metric định nghĩa task actual completion.

### Câu 10: Proxy

Proxy chặn submit nhưng callback thực thi bên ngoài proxy. Advice trên submit có tự đo callback execution không?

**Đáp án:** không. Cần instrumentation đúng boundary thực thi.

### Câu 11: Happens-before

Một Future.get hoàn tất và có memory guarantee. Có tự chứng minh worker đang nằm trên stack của caller không?

**Đáp án:** không. Memory ordering khác call-stack ancestry.

### Câu 12: Cleanup

Task A để ThreadLocal=R1 trên pool worker. Task B chạy sau. Nguy cơ gì?

**Đáp án:** B có thể dùng stale context R1. Cần finally/Scope cleanup trên worker.

## 32. Tổng kết

**Luồng bất đồng bộ, callback và continuation làm thay đổi cách diễn giải quan hệ gọi**: logical request có thể tiếp tục sau khi method caller đã trả và trên các thread khác nhau. Không nên lấy quan hệ call stack trong một thread để suy mọi causal edge của tác vụ đã lập lịch.

Các nguyên tắc chính:

- **Registration, execution và completion là ba ranh giới khác nhau.**
- **Method trả Future không đồng nghĩa Future đã hoàn tất.**
- **Dynamic cflow không mặc định đi theo async task qua thread.**
- **ThreadLocal cần propagation và cleanup rõ trên mỗi execution boundary.**
- **TraceId chung chỉ là correlation, không tự chứng minh parent–child.**
- **Fan-out/fan-in tạo graph dependencies, không phải luôn một cây caller/callee.**
- **Retry, recovery, exception, cancellation và timeout khiến outcome của từng tầng khác nhau.**
- **Pointcut/weaving coverage và metadata nhân quả phải được xác minh riêng.**
- **Kiểm thử nên chứng minh event boundary, task count, callback execution, cause và scope isolation**, không chỉ có hai dòng log cùng một requestId.

**Câu hỏi quan trọng trước khi viết một async aspect:** *Tôi đang quan sát lời gọi đồng bộ, sự kiện lập lịch, task execution, callback invocation hay logical completion — và bằng chứng nào cho phép tôi nối sự kiện này với phần còn lại của công việc?*
