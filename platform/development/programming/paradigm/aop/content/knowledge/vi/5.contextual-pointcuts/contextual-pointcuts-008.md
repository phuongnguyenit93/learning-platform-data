# Giới hạn của ngữ cảnh khi công việc chuyển sang luồng hoặc tác vụ khác

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, pointcut có thể chọn điểm can thiệp dựa vào **ngữ cảnh thực thi** (*execution context*): phương thức đang chạy, đối tượng đích, đối số, luồng điều khiển, thông tin gắn với yêu cầu hoặc trạng thái được công cụ AOP hỗ trợ. Những điều kiện này dễ hiểu trong một chuỗi lời gọi đồng bộ, nhưng phát sinh giới hạn quan trọng khi công việc **được giao cho một thread, executor, callback, future hoặc tác vụ khác**.

**Nguyên tắc trung tâm:** *Ngữ cảnh của lời gọi hiện tại không tự động trở thành ngữ cảnh của công việc chạy ở nơi khác.* Một advice nhìn thấy thông tin tại thời điểm gửi tác vụ không có nghĩa advice ở lúc tác vụ chạy cũng nhìn thấy thông tin đó. Pointcut được đánh giá ở **join point nào, tại thời điểm nào, trên luồng nào**, và dữ liệu nào **được truyền qua ranh giới**, sẽ quyết định kết quả.

Ví dụ: khi một phương thức đang xử lý yêu cầu mang mã `REQ-17`, nó gửi tác vụ tới một thread pool. Một advice ở phương thức gửi có thể thấy `REQ-17`; advice chạy trong worker thread có thể không thấy mã này, dù tác vụ vẫn thuộc cùng yêu cầu về mặt nghiệp vụ. Nếu worker thread được dùng lại, nó còn có thể chứa **ngữ cảnh cũ** nếu người viết không dọn dẹp đúng.

> Bài này phân tích AOP ở mức mô hình tổng quát, gồm cơ bản và nâng cao. Không có cơ chế truyền ngữ cảnh hay ngôn ngữ pointcut nào bắt buộc chung cho mọi công cụ AOP. Ví dụ Java 17+ minh họa giới hạn thực tế bằng API Java SE và một interceptor nhỏ, rồi chỉ rõ điều kiện nào là pointcut logic, điều kiện nào chỉ là guard trong advice.

## 1. Trước tiên: “ngữ cảnh” trong AOP là gì?

**Join point** là điểm có thể được AOP can thiệp, ví dụ một lần gọi hoặc một lần thực thi phương thức, nếu công cụ hỗ trợ. **Pointcut** chọn tập join point; **advice** thực hiện hành vi bổ sung ở đó. Khi nói “pointcut theo ngữ cảnh”, ta muốn lựa chọn dựa trên dữ liệu gắn với một thời điểm/đường thực thi, chứ không chỉ metadata tĩnh như tên lớp và chữ ký.

Có thể phân biệt các nhóm thông tin sau:

| Nhóm ngữ cảnh | Ví dụ | Thay đổi khi chuyển tác vụ? |
| --- | --- | --- |
| **Tĩnh của join point** | Chữ ký `process(String)`, kiểu khai báo | Không tự thay đổi chỉ vì đổi thread, nhưng điểm thực thi mới có thể là phương thức khác |
| **Đối tượng/phương thức** | Target, receiver, method thực chạy | Có thể giữ nếu tham chiếu được truyền; không tự bảo đảm thread safety |
| **Đối số** | `OrderCommand`, mã đơn hàng | Có thể truyền cho tác vụ; dữ liệu mutable có thể đổi trước khi worker đọc |
| **Luồng điều khiển** | Đang nằm trong chuỗi gọi của `checkout()` | Chuỗi stack đồng bộ không tự nối sang thread khác |
| **Thread-local** | Trace ID, mã tương quan, danh tính đã xác thực | Mặc định gắn với thread; thread khác không tự nhìn thấy |
| **Ngữ cảnh tác vụ** | Deadline, cancellation, request context | Chỉ có khi API/runtime truyền hoặc khôi phục có chủ đích |
| **Ngữ cảnh phân tán** | Trace headers, correlation ID trên message | Phải tuần tự hóa/truyền qua ranh giới tiến trình; cần xác thực dữ liệu tin cậy |

Cần phân biệt **thông tin truyền như đối số** với **thông tin ngầm gắn trong môi trường thực thi**. Một hàm nhận `requestId` trực tiếp vẫn có thể biết request ID trên thread khác; nhưng `ThreadLocal.get()` sẽ chỉ truy cập giá trị của thread hiện tại.

### Ngữ cảnh của lời gọi không phải “toàn bộ dữ liệu đang có trong ứng dụng”

Một aspect không tự biết mọi biến local của caller, toàn bộ stack frame hay mọi object đang tồn tại. Nó chỉ thấy những gì **loại join point, API của công cụ và cơ chế truyền ngữ cảnh** cung cấp. Ngay cả với kiểu pointcut dựa trên *control flow*, việc “đang nằm trong luồng gọi” thường có ý nghĩa với chuỗi lời gọi đồng bộ hiện tại, không tự bao trùm công việc được lên lịch cho tương lai.

## 2. Ranh giới quan trọng: call stack, thread và task

Giả sử chương trình đồng bộ:

```text
Thread A
  Controller.handle()
    -> Service.process()
       -> Repository.save()
          -> return
       -> return
    -> return
```

Nếu một cơ chế AOP hỗ trợ lựa chọn theo **luồng điều khiển động** (*control flow*), một join point bên trong `Repository.save()` có thể được xem là nằm trong chuỗi gọi phát sinh từ `Controller.handle()`, tùy semantics của công cụ.

Bây giờ thay lời gọi trực tiếp bằng gửi việc:

```text
Thread A                               Thread B
Controller.handle()
  -> Executor.submit(task)
  <- Future returned
  -> tiếp tục hoặc kết thúc             task.run()
                                          -> Service.process()
                                             -> Repository.save()
```

Giữa hai bên không có **một call stack đồng bộ liên tục**. Thread A chạy lời gọi gửi tác vụ; Thread B chạy `task.run()` tại thời điểm riêng. Dù mục đích nghiệp vụ có quan hệ nhân quả, quan hệ ấy không tự biến thành quan hệ stack của AOP.

Vì vậy, ba khái niệm cần giữ riêng:

- **Call stack:** chuỗi frame lời gọi đang hoạt động trên một thread.
- **Execution context:** dữ liệu và điều kiện quan sát được tại một join point cụ thể.
- **Causal/request context:** thông tin dùng để liên kết những công việc thuộc cùng yêu cầu, có thể vượt qua nhiều thread hoặc tiến trình nếu được truyền rõ.

Một pointcut “đang chạy bên trong chuỗi gọi X” có thể không khớp ở worker, trong khi một điều kiện “request ID đã được chuyển đến worker có tiền tố Y” vẫn có thể khớp nếu runtime AOP hỗ trợ kiểm tra request context đó.

## 3. ThreadLocal giải quyết vấn đề gì và không giải quyết điều gì?

Trong Java, `ThreadLocal<T>` cho phép mỗi thread lưu một giá trị độc lập dưới cùng một biến `ThreadLocal`. Đây là cách giữ ngữ cảnh ngầm mà code trong **cùng thread** có thể đọc mà không phải truyền qua mọi tham số.

Ví dụ khái niệm:

```java
// Mã minh họa, đặt trong một class thích hợp.
static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

TRACE_ID.set("REQ-17");
String currentTrace = TRACE_ID.get(); // "REQ-17" trên thread hiện tại.
TRACE_ID.remove();
```

Điều cần hiểu:

1. Gọi `set` trên Thread A không tự đặt giá trị cho Thread B.
2. `get` trên Thread B có thể trả `null` nếu thread B chưa có giá trị.
3. Với thread pool, **thread B được tái sử dụng** cho nhiều tác vụ. Nếu tác vụ cũ không dọn `ThreadLocal`, tác vụ mới có thể đọc nhầm thông tin cũ.
4. `remove()` xóa binding của thread hiện tại; trong một scope tạm thời có giá trị cũ thì cần **khôi phục đúng giá trị cũ**, không đơn giản xóa vô điều kiện.
5. Lưu một object mutable vào `ThreadLocal` không khiến object ấy tự nhiên thread-safe nếu nó được chia sẻ với các thread khác bằng đường khác.

Vì thế, dùng `ThreadLocal` để hỗ trợ advice không có nghĩa đã giải quyết **context propagation**. Nó mới giải quyết truy cập ngữ cảnh **bên trong một thread**.

### Một câu hỏi kiểm tra nhanh

Nếu `AuditAspect` chọn hành vi dựa trên `TRACE_ID.get() != null`, chuyện gì xảy ra khi gọi cùng phương thức đích từ thread pool? Câu trả lời không phụ thuộc chỉ vào method signature: nó phụ thuộc **thread thực thi có binding đó hay không** tại chính lúc advice được đánh giá.

## 4. Context propagation: cần truyền cái gì qua ranh giới?

**Context propagation** là thao tác **nắm bắt, vận chuyển, khôi phục và dọn dẹp** những phần ngữ cảnh cần thiết khi công việc chuyển sang một môi trường thực thi khác.

Một vòng đời an toàn thường có bốn giai đoạn:

```text
Caller thread                 Task queue                Worker thread
     |                            |                           |
  Capture                      enqueue                  Restore context
  snapshot  --------------------> task ---------------------> enter advice
     |                                                        |
 caller continues                                        run target
                                                              |
                                                        finally restore
                                                        previous context
```

Cần quyết định rõ **chụp ngữ cảnh vào thời điểm nào**: khi tạo `Runnable`, khi `submit`, khi callback được đăng ký, hay lúc một sự kiện được phát đi? Nếu giá trị ngữ cảnh thay đổi giữa các thời điểm, lựa chọn capture sẽ ảnh hưởng kết quả.

**Không nên tự động sao chép toàn bộ biến ThreadLocal của một thread**. Nhiều giá trị không thích hợp để truyền: connection, transaction, resource chỉ có hiệu lực trong một thread, dữ liệu định danh nhạy cảm hoặc đối tượng có trạng thái mutable. Thường cần **snapshot nhỏ, có chủ đích, bất biến**, chỉ mang correlation ID, trace parent, deadline hoặc các thuộc tính được phép dùng.

### Snapshot hay chia sẻ tham chiếu?

Nếu context giữ tham chiếu tới một object mutable, “capture context” có thể chỉ sao chép **tham chiếu**, không phải trạng thái. Caller sửa object sau khi gửi việc, worker có thể thấy nội dung mới hoặc tình trạng race. Một `record` bất biến chứa dữ liệu đơn giản giúp semantics dễ hiểu hơn; với object lồng nhau mutable vẫn phải tạo snapshot thực sự hoặc đảm bảo không bị sửa.

## 5. Ví dụ Java 17+ chạy được: advice mất ngữ cảnh khi vào executor

Ví dụ này mô phỏng một aspect theo ngữ cảnh: khi một lời gọi `perform(...)` đi qua proxy, handler chỉ in dòng advice nếu **ThreadLocal của thread hiện tại** chứa trace ID bắt đầu bằng `REQ-`. Ví dụ có hai đường thực thi: gửi tác vụ thẳng vào executor và gửi tác vụ đã được bọc để truyền context.

Nó sử dụng **Java SE**, không cần framework. Handler là **interception có guard theo context**, không phải một engine hỗ trợ ngôn ngữ pointcut động đầy đủ.

Lưu tệp **`AopContextHandoffDemo.java`** (UTF-8):

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AopContextHandoffDemo {
    record RequestContext(String traceId) { }

    static final ThreadLocal<RequestContext> CURRENT = new ThreadLocal<>();

    interface TaskAction {
        void perform(String label);
    }

    static final class TaskActionImpl implements TaskAction {
        @Override
        public void perform(String label) {
            System.out.println("target " + label + " " + currentTrace());
        }
    }

    static String currentTrace() {
        RequestContext context = CURRENT.get();
        return context == null ? "NONE" : context.traceId();
    }

    static void setContext(RequestContext context) {
        if (context == null) {
            CURRENT.remove();
        } else {
            CURRENT.set(context);
        }
    }

    // Minh họa advice phụ thuộc ngữ cảnh ở chính thread thực thi.
    static TaskAction withAdvice(TaskAction target) {
        return (TaskAction) Proxy.newProxyInstance(
                TaskAction.class.getClassLoader(),
                new Class<?>[] { TaskAction.class },
                (proxy, method, args) -> {
                    RequestContext context = CURRENT.get();
                    if (method.getDeclaringClass() == TaskAction.class
                            && method.getName().equals("perform")
                            && context != null
                            && context.traceId().startsWith("REQ-")) {
                        System.out.println(
                                "advice " + context.traceId() + " " + args[0]);
                    }

                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    }
                });
    }

    // Capture khi tạo wrapper; restore context cũ sau tác vụ.
    static Runnable carryContext(Runnable task) {
        RequestContext captured = CURRENT.get();

        return () -> {
            RequestContext previous = CURRENT.get();
            try {
                setContext(captured);
                task.run();
            } finally {
                setContext(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            setContext(new RequestContext("REQ-17"));
            TaskAction action = withAdvice(new TaskActionImpl());

            System.out.println("caller " + currentTrace());
            action.perform("direct");

            // Không truyền context: worker có ThreadLocal riêng.
            pool.submit(() -> action.perform("no-transfer")).get();

            // Wrapper capture REQ-17 trên caller, restore ở worker.
            pool.submit(carryContext(
                    () -> action.perform("propagated"))).get();

            // Worker được dùng lại, nhưng wrapper đã dọn context.
            pool.submit(() -> action.perform("after")).get();
        } finally {
            setContext(null);
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 AopContextHandoffDemo.java
java AopContextHandoffDemo
```

Đầu ra chuẩn:

```text
caller REQ-17
advice REQ-17 direct
target direct REQ-17
target no-transfer NONE
advice REQ-17 propagated
target propagated REQ-17
target after NONE
```

### Vì sao có đúng những dòng này?

**Lời gọi `direct`:** main thread đã được đặt `REQ-17`. Handler và target đều chạy trong main thread; handler thấy context nên in `advice`, target in cùng trace ID.

**`no-transfer`:** tác vụ được gửi sang single-thread executor. Worker không tự nhận giá trị `ThreadLocal` từ main; handler không thấy context nên không in dòng `advice`. Target in `NONE` dù caller đã có `REQ-17`.

**`propagated`:** `carryContext(...)` được **tạo trên caller**, chụp `REQ-17` vào biến `captured`. Khi worker chạy wrapper, nó đặt context này cho chính thread worker trước khi gọi target. Handler và target đều nhìn thấy `REQ-17`.

**`after`:** wrapper đã chạy `finally` và khôi phục giá trị thread-local trước đó của worker (`null` trong ví dụ). Tác vụ tiếp theo trên cùng worker không thấy ngữ cảnh cũ, nên in `NONE`.

**Vì sao đầu ra ổn định?** `newSingleThreadExecutor()` dùng một worker tại một thời điểm; mỗi `Future.get()` chờ tác vụ trước hoàn tất rồi mới gửi tác vụ tiếp theo. Không in thread ID hoặc thời gian nên không có thành phần đầu ra biến thiên.

### Mô hình pointcut nào được mô phỏng?

Bộ lọc handler có hai lớp:

1. **Tĩnh:** chỉ quan tâm phương thức `TaskAction.perform`.
2. **Động theo môi trường:** chỉ in advice khi `CURRENT.get()` trên thread đang chạy chứa trace ID hợp lệ.

Trong ví dụ, handler vẫn được vào ở `no-transfer` và `after`, nhưng guard quyết định không in. Một công cụ AOP có dynamic pointcut thật có thể quyết định có kích hoạt advice ngay khi xét điểm; các hiệu ứng và overhead cụ thể phụ thuộc engine. Ví dụ không tự biến `ThreadLocal` thành một pointcut có cú pháp chuẩn.

### Điều gì được bảo đảm, điều gì chưa?

Ví dụ bảo đảm **tại đường gọi đi qua proxy** rằng worker có context đúng khi được bọc, và wrapper khôi phục trạng thái cũ khi hoàn tất hoặc ném ngoại lệ. Nó **không** bảo đảm lời gọi trực tiếp target có advice; không truyền dữ liệu qua tiến trình; không tự truyền transaction/resource; không triển khai cancellation/deadline; và không thay thế các biện pháp kiểm tra quyền truy cập.

## 6. Vì sao phải khôi phục context cũ thay vì chỉ remove?

Một worker có thể đã có ngữ cảnh hợp lệ của một *scope bên ngoài*. Nếu wrapper luôn `remove()` trong `finally`, nó sẽ phá mất binding trước đó.

Xét lồng nhau:

```text
Worker đã có context = OUTER
  -> bước chạy tạm cần context = INNER
      -> advice/target bên trong đọc INNER
  <- kết thúc bước chạy tạm
Worker phải trở lại context = OUTER
```

Cách đúng cho một scope tạm là:

1. Lưu giá trị context cũ của thread hiện tại.
2. Đặt giá trị dành cho tác vụ hiện tại.
3. Thực thi nội dung.
4. Trong `finally`, **khôi phục giá trị cũ** (hoặc remove nếu cũ không có).

Một hệ thống thực tế còn cần quản lý scope lồng nhau, ngoại lệ và trạng thái hủy. Gọi `remove()` ở **ranh giới vòng đời cuối cùng** của request/task vẫn quan trọng để thread pool không giữ context của request đã xong.

### Rò rỉ dữ liệu giữa các tác vụ

Nếu một worker chạy request A rồi request B, nhưng context A không được dọn, pointcut dựa trên context có thể áp dụng advice với trace ID của A khi đang xử lý B. Điều này gây sai log/audit, rò dữ liệu, metric giả, hoặc đánh giá nhầm chính sách. Đây là lỗi **cross-task contamination**; nó nghiêm trọng hơn việc “thiếu trace ID”.

Đừng chỉ kiểm thử trường hợp “đã truyền được context”. Phải kiểm tra thêm “sau khi hoàn tất, worker còn giữ sai ngữ cảnh không”.

## 7. InheritableThreadLocal có tự giải quyết được không?

`InheritableThreadLocal` cho phép một **thread mới được tạo** thừa hưởng giá trị từ parent thread khi thread đó được tạo, theo cơ chế Java. Nhưng nó **không phải giải pháp truyền ngữ cảnh tổng quát cho executor**:

- Thread pool thường **tái sử dụng** worker đã được tạo trước khi yêu cầu hiện tại xuất hiện.
- Thread mới thừa hưởng giá trị ở **thời điểm tạo thread**, không tự cập nhật theo từng lần `submit`.
- Giá trị được thừa hưởng có thể là cùng tham chiếu tới object mutable nếu không có cơ chế tạo bản sao thích hợp.
- Quy tắc thừa hưởng của từng loại thread và cách tạo thread có thể có cấu hình/giới hạn khác; không dùng nó để suy đoán mọi tác vụ chắc chắn có context.
- Context được thừa hưởng không mang một ranh giới sống/chết request rõ ràng nếu thiếu cleanup.

Nếu cần propagation qua task pool, hãy dựa vào **contract truyền context ở lúc nộp và lúc chạy tác vụ**, hoặc sử dụng một API runtime có semantics context rõ ràng. Không giả định `InheritableThreadLocal` sẽ tự làm đúng với mọi thread pool.

## 8. ExecutorService: task là đơn vị công việc, thread là nơi chạy

`ExecutorService.submit(...)` nhận một `Runnable` hoặc `Callable`, sau đó lịch làm việc có thể chạy nó trên một thread khác. `Future.get()` giúp caller chờ hoàn tất, nhưng **việc chờ không truyền ThreadLocal** từ caller cho worker.

Một số điểm dễ nhầm:

- `submit` có thể trả về `Future` trước khi tác vụ chạy hoặc hoàn tất.
- Tác vụ có thể nằm trong hàng đợi, nên context ở lúc worker thực thi có thể khác trạng thái caller ở lúc gửi.
- Hai tác vụ của cùng yêu cầu có thể chạy trên hai worker khác nhau.
- Hai yêu cầu khác nhau có thể nối tiếp chạy trên cùng một worker.
- Hủy `Future` hoặc ngắt thread không tự giải quyết việc dọn mọi resource/context nếu mã thiếu `finally`.
- `execute(Runnable)` và `submit(Runnable)` có cách báo lỗi khác nhau ở caller, nhưng đều không có cam kết chung tự truyền mọi context người dùng.

Muốn instrument AOP tại **điểm gửi tác vụ**, một advice có thể bao quanh lời gọi submit và tạo wrapper mang context nếu cơ chế cho phép. Nhưng phải hiểu **điểm gửi** và **điểm chạy** khác nhau. Chỉ đo thời gian ở submit không đồng nghĩa đo thời gian chạy task; chỉ ghi log ở worker không tự liên kết nó với caller.

### Thời điểm capture quan trọng

Giả sử:

```text
t0: traceId = A
t1: tạo wrapper và capture A
t2: caller đổi traceId = B
t3: submit wrapper
t4: worker chạy wrapper
```

Nếu wrapper capture ở `t1`, worker nhìn thấy **A**, bất kể caller đang có B ở `t3`. Nếu yêu cầu là capture tại thời điểm submit, wrapper phải được tạo tương ứng ở `t3`. Không có một thời điểm “tự đúng” trong mọi ứng dụng: contract của hệ thống phải xác định tác vụ thuộc context nào.

## 9. CompletableFuture và callback: nơi chạy không luôn là caller

Với `CompletableFuture` hoặc các API bất đồng bộ tương tự, callback có thể chạy:

- Trên thread hoàn tất stage trước đó.
- Trên thread đăng ký callback trong một số tình huống.
- Trên executor đã cung cấp.
- Trên executor mặc định đối với những biến thể bất đồng bộ, theo hợp đồng API.

Do vậy, **không đặt giả định cứng** rằng callback luôn chạy trên cùng thread từng tạo future.

Ví dụ **minh họa một đoạn độc lập về ý tưởng, không phải chương trình Java hoàn chỉnh**:

```java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> "data", executor);

CompletableFuture<Integer> mapped =
        stage.thenApplyAsync(String::length, executor);
```

Ngay cả khi `supplyAsync` và `thenApplyAsync` dùng cùng executor, callback vẫn có thể thực thi ở một worker đã được dùng cho công việc khác. Context trên caller không tự động được đọc từ `ThreadLocal` của worker.

Nếu cần propagation, có thể bọc **supplier, function, consumer hoặc runnable** bằng các wrapper phù hợp có capture/restore. Phải phân biệt lúc callback được **đăng ký**, lúc nó được **scheduled**, và lúc **chạy**. Đồng thời kiểm thử cả nhánh thành công, ngoại lệ và cancellation.

### Một chuỗi future có nhiều ranh giới

```text
Caller (context A)
  -> submit stage 1
       worker X: stage 1
          -> complete
       worker Y: stage 2 callback
          -> complete
       worker Z: stage 3 callback
```

Dù các stage thuộc cùng pipeline, không có bảo đảm đơn giản rằng `ThreadLocal` của worker X được chuyển sang Y hoặc Z. Một hệ thống context propagation phải xác định cách mang dữ liệu qua **từng ranh giới scheduler/callback**.

### Không nhầm kết thúc lời gọi và hoàn tất tác vụ

Một advice đo thời gian quanh method **trả về `CompletableFuture`** thường kết thúc khi future **được trả về**, không phải khi future **hoàn tất**. Nếu muốn đo end-to-end latency, cần liên kết hoạt động ở thời điểm hoàn tất future với mốc bắt đầu, đồng thời xử lý completion thành công, thất bại và hủy. Việc này không thể suy ra chỉ từ method execution ban đầu.

## 10. Pointcut theo luồng điều khiển động

Một số mô hình AOP cung cấp pointcut dựa trên **dynamic control flow**: chọn join point xảy ra trong luồng gọi của một join point khác. Ví dụ ý tưởng:

```text
Chọn lời gọi Repository.save(...)
nếu nó xảy ra trong luồng điều khiển đồng bộ
bắt đầu từ Checkout.placeOrder(...)
```

Khái niệm *control flow* thường được xác định theo chuỗi lời gọi trên thread hiện tại, tùy DSL và weaving. Nếu `Checkout.placeOrder` **gửi** một tác vụ rồi trở về, worker xử lý `Repository.save` ở stack khác. **Quan hệ “tác vụ do checkout tạo ra” không tự là quan hệ cflow**.

Nếu bài toán cần “mọi tác vụ được bắt nguồn từ checkout”, có thể cần mang một **causal marker** hay request context tường minh tới worker, rồi để advice ở worker lựa chọn theo marker đó nếu engine hỗ trợ. Không tự mở rộng semantics của một pointcut cflow chỉ vì nghiệp vụ có quan hệ nhân quả.

### Control flow khác trace context

- **Control flow:** quan hệ frame/lời gọi tại thời điểm đang chạy.
- **Trace context:** metadata mô tả quan hệ giữa hoạt động, có thể được truyền qua thread/process.
- **Business transaction:** phạm vi commit/rollback, có thể khác với cả hai khái niệm trên.

Một trace span nối tiếp ở worker không chứng minh worker vẫn nằm trong stack của caller hay cùng transaction quản lý tài nguyên. Tách bạch ba loại ngữ cảnh này giúp tránh đặt pointcut hoặc xử lý resource ở sai ranh giới.

## 11. Lời gọi qua proxy và lời gọi nội bộ

Một interceptor dùng **proxy** chỉ quan sát những lời gọi đi qua proxy. Khi worker đã nhận được context đúng, nhưng gọi **trực tiếp target**, advice trên proxy vẫn có thể không chạy.

```text
Thread A -> proxy -> target       [nếu khớp, interceptor có thể chạy]
Thread B -> proxy -> target       [phụ thuộc context của B khi đánh giá]
Thread B ----------> target       [bỏ qua proxy, dù B có context]
target -> this.internalMethod()   [có thể bỏ qua interception qua proxy]
```

Điều này cho thấy **propagation** và **weaving coverage** là hai vấn đề độc lập. Đúng request context không sửa được một đường gọi không đi qua điểm can thiệp; đúng pointcut không làm context tự hiện diện trên worker.

Một kỹ thuật AOP có thể weave trực tiếp bytecode và nhìn thấy những join point mà proxy không chặn được. Tuy nhiên, khả năng can thiệp chính xác ở đâu còn phụ thuộc việc class nào được weave, trình nạp class, phạm vi compile/load và các giới hạn của công cụ.

## 12. Ngữ cảnh đối số và mutable state khi gửi công việc

Không phải mọi “mất ngữ cảnh” đều là ThreadLocal. Giả sử một method nhận `MutableRequest` rồi gửi nó cho worker:

```java
// Minh họa ý tưởng, không phải chương trình Java hoàn chỉnh.
MutableRequest request = ...;
executor.submit(() -> process(request));
request.setPriority("LOW");
```

Worker giữ tham chiếu cùng object. Nếu request bị sửa trong khi worker đọc, giá trị dùng để xét pointcut theo tham số có thể khác giá trị tại lúc submit, thậm chí có race condition. Đây là sự khác biệt giữa:

- **Capture by reference:** giữ object rồi đọc trạng thái vào thời điểm sau.
- **Snapshot bất biến:** chụp các trường được phép truyền tại thời điểm được xác định.
- **Re-read trong worker:** quyết định bằng trạng thái mới nhất với contract và cơ chế đồng bộ phù hợp.

Nếu điều kiện AOP kiểm tra giá trị trước khi gửi, nhưng target kiểm tra lại sau khi nhận, hai bên có thể quan sát hai trạng thái khác nhau (**time-of-check/time-of-use**). Các bất biến nghiệp vụ/bảo mật phải có cơ chế bảo đảm tại ranh giới đáng tin cậy; pointcut không tự khóa object hoặc tạo tính nguyên tử.

## 13. Ngữ cảnh bảo mật và identity cần có ranh giới tin cậy

Dữ liệu như **trace ID** thường là metadata quan sát; dữ liệu **ủy quyền** quyết định ai được làm gì, có ý nghĩa nhạy cảm hơn. Không nên tự động copy một danh tính hoặc “đã xác thực” từ thread hiện tại sang mọi tác vụ rồi coi đó là bằng chứng đủ để thực hiện thao tác.

Khi một tác vụ hoạt động thay mặt người dùng, cần quy định:

- Tác vụ còn được phép dùng danh tính/ủy quyền đó tại thời điểm thực thi không?
- Phạm vi quyền và thời hạn hiệu lực là gì?
- Có cần xác minh lại ở boundary không?
- Nếu chạy qua hàng đợi lâu hoặc process khác, dữ liệu nhận được được xác thực thế nào?
- Có được đưa token, mật khẩu hoặc thông tin cá nhân vào context/log không?

**Propagation không tương đương authorization.** Một marker truyền được tới worker chỉ chứng minh ta đã vận chuyển một giá trị; nó không chứng minh giá trị ấy đáng tin cậy hoặc vẫn có hiệu lực. Không lấy ThreadLocal của caller làm cơ chế bảo mật duy nhất nếu còn đường thực thi khác không được bảo vệ.

## 14. Ngữ cảnh tracing/logging và giới hạn quan sát

Một aspect logging có thể đọc request ID để thêm vào mỗi dòng log. Nếu context không được truyền:

- Log ở caller có `REQ-17`.
- Log ở worker thiếu mã tương quan hoặc nhận nhầm mã của task trước.
- Hệ thống quan sát mất khả năng ghép sự kiện theo cùng yêu cầu.

Khi truyền context, nên chỉ chuyển metadata thực sự cần thiết, theo chính sách:

- Dùng correlation ID hoặc trace ID có định dạng và nguồn đáng tin cậy.
- Giới hạn kích thước context/baggage, tránh tăng payload không kiểm soát.
- Không tự ghi toàn bộ argument, token, session hoặc dữ liệu nhạy cảm.
- Tránh lấy ID người dùng/đơn hàng có cardinality rất lớn làm nhãn metric nếu không có chiến lược phù hợp.
- Dọn context ngay ở ranh giới tác vụ để tránh nhầm dữ liệu giữa các request.

Nếu logging framework dùng một map ngữ cảnh gắn theo thread (ví dụ mô hình *mapped diagnostic context*), quy tắc tương tự ThreadLocal thường được áp dụng: **capture các trường được phép, restore trên worker, rồi cleanup**. Không giả định mọi thư viện logging có cơ chế propagation như nhau.

## 15. Context qua hàng đợi và ranh giới tiến trình

Khi công việc được gửi đến một **message queue, background job hoặc dịch vụ khác**, giá trị ThreadLocal càng không thể tự xuất hiện ở nơi nhận. Cần xác định một **context envelope** hoặc metadata của thông điệp được truyền tường minh.

```text
Process A                               Process B
  request context
      |
      +-- encode allowed metadata
      |
      +--> message / protocol headers ------> decode / validate
                                               |
                                               +--> create local task context
                                               |
                                               +--> invoke target/advice
                                               |
                                               +--> cleanup
```

Các cân nhắc gồm:

1. **Serialization:** chỉ gửi những trường có thể biểu diễn, cần thiết và an toàn.
2. **Versioning:** trường mới/cũ phải có cách xử lý khi sender và receiver dùng phiên bản khác.
3. **Trust:** receiver không tin mù quáng mọi field do nguồn bên ngoài cung cấp.
4. **Lifetime:** deadline và quyền có thể hết hạn khi message nằm trong queue.
5. **Retries:** một message có thể chạy lại, nên hành vi nghiệp vụ cần idempotency hoặc cơ chế loại trùng phù hợp.
6. **Observability:** nối quan hệ nhân quả bằng trace/correlation metadata, không bằng giả định cùng stack/thread.
7. **Privacy:** giới hạn thông tin trong header, tránh để dữ liệu nhạy cảm lan qua nhiều dịch vụ.

Khôi phục context ở Process B là tạo **ngữ cảnh cục bộ mới** từ dữ liệu đã được xác nhận, không phải “khôi phục nguyên xi thread của Process A”.

## 16. Các cơ chế truyền ngữ cảnh phổ biến và sự đánh đổi

| Phương án | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Truyền tham số trực tiếp** | Contract rõ, dễ thấy ở call site và test | Có thể phải truyền qua nhiều lớp; cần thiết kế interface |
| **Snapshot context bất biến** | Giảm race, thuận tiện khi gửi task | Phải xác định thời điểm snapshot và trường được phép |
| **Wrapper quanh Runnable/Callable/callback** | Có thể capture/restore ở đúng boundary | Dễ bỏ sót một nhánh callback/executor nếu áp dụng không đồng bộ |
| **Thread-local có scope rõ** | Tiện cho lời gọi đồng bộ trong cùng thread | Không tự truyền qua task; dễ rò trên thread pool |
| **Runtime API có cơ chế context riêng** | Có thể hỗ trợ phạm vi, propagation và cleanup | Phải tuân thủ contract, không suy đoán có ở mọi API |
| **Metadata của message/protocol** | Đi qua tiến trình/máy khác | Cần serialize, validate, bảo mật và quản lý phiên bản |

AOP có thể giúp áp dụng wrapper ở các ranh giới được chọn hoặc đọc context để quyết định advice. Nhưng **context carrier** thuộc mô hình thực thi; điểm can thiệp chỉ là nơi có thể gắn hành vi ấy. Hãy tránh biến aspect thành nơi bí mật tự sao chép mọi biến của thread.

## 17. Cancellation, timeout và deadline cũng là ngữ cảnh

Ngoài trace ID, một tác vụ có thể cần **deadline**, **cancellation token** hoặc **giới hạn tài nguyên**. Các giá trị này ảnh hưởng điều kiện chạy advice và target, nhưng không nên gói bằng các giả định quá đơn giản.

Ví dụ, nếu caller gửi task rồi timeout:

- Worker có thể chưa bắt đầu hoặc vẫn đang chạy.
- `Future.cancel(true)` là yêu cầu hủy có thể cố gắng ngắt thread; không phải cam kết mọi phép toán dừng ngay.
- Nếu handler cleanup chỉ chạy ở nhánh thành công mà không có `finally`, context có thể tồn tại sau khi công việc thất bại/ngắt.
- Deadline cần được kiểm tra theo thời điểm thích hợp ở worker; capture một boolean “chưa hết hạn” ở caller không chứng minh tác vụ vẫn còn hạn khi bắt đầu.

Một aspect có thể ghi nhận deadline và trạng thái hủy, nhưng hành vi ngắt/hủy thực tế phụ thuộc API và mã thực thi. **Đừng dùng một pointcut theo context để thay thế toàn bộ chính sách hủy hoặc bảo đảm tài nguyên.**

## 18. Khi nào một pointcut theo ngữ cảnh không đáng tin?

Có những câu hỏi giúp phát hiện giả định sai:

- Pointcut có cần **caller stack** nhưng target thực thi ở worker khác không?
- Context có dựa vào **ThreadLocal** mà không có propagation không?
- Worker có được **reuse** cho tác vụ khác và có cleanup nhất quán không?
- Giá trị context được capture ở **đúng thời điểm nghiệp vụ** không?
- Argument là object mutable bị thay đổi sau khi đưa vào queue không?
- Advice có được weave ở **đường gọi thật** hay chỉ được khai báo?
- Một callback có thể chạy trong **executor khác** với executor dự kiến không?
- Có nhánh **exception, cancellation, retry** nào không khôi phục context không?
- Dữ liệu truyền có chứa **danh tính bảo mật** hoặc thông tin nhạy cảm không?
- Công cụ AOP có thật sự hỗ trợ predicate động/cflow ở loại join point đã chọn không?

Nếu một trong các câu trả lời chưa rõ, hãy kiểm thử bằng một boundary thực thay vì suy luận từ một lời gọi đồng bộ đơn giản.

## 19. Quy trình thiết kế một chính sách AOP qua ranh giới async

### Bước 1: Xác định concern

Ví dụ “mọi thao tác lưu tài liệu thuộc yêu cầu X cần log có correlation ID”, hoặc “đo trọn thời gian xử lý tác vụ hậu trường”. Hai mục tiêu này có thể cần các điểm quan sát khác nhau.

### Bước 2: Xác định join point thật

Bạn đang muốn can thiệp vào:

- Lời gọi `submit` từ caller?
- Lúc `Runnable.run` hoặc `Callable.call` bắt đầu?
- Method nghiệp vụ thực thi trong worker?
- Thời điểm một future/callback hoàn tất?
- Ranh giới gửi/nhận message giữa hai process?

Không phải công cụ nào cũng có mọi loại join point. **Một method name trùng nhau không khiến hai ranh giới trở thành một.**

### Bước 3: Liệt kê dữ liệu phải có tại điểm đó

Ví dụ trace ID, operation name và deadline. Với từng trường, chỉ rõ ai sở hữu, capture khi nào, có thể thay đổi không, có thể gửi tới thread/process khác không và có được tin cậy không.

### Bước 4: Chọn cách propagation

Dùng tham số trực tiếp, snapshot bất biến hoặc wrapper được tạo tại đúng boundary. Với nhiều nhánh callback hoặc queue, xác định nơi context tiếp tục được vận chuyển qua mỗi ranh giới.

### Bước 5: Định nghĩa scope và cleanup

Lưu context cũ của worker, set context mới, thực thi, khôi phục trong `finally`; đảm bảo công việc của request mới không đọc nhầm context cũ. Với process khác, xác thực metadata ở đầu nhận.

### Bước 6: Kiểm thử trên đường thực tế

Không chỉ unit test predicate. Phải gọi qua executor/pool/callback/queue thật (hoặc môi trường kiểm thử tương đương) và xác nhận log, pointcut, kết quả, ngoại lệ, cleanup, cancellation.

### Bước 7: Đo overhead

Một wrapper nhẹ có thể phù hợp; sao chép đồ thị object lớn, parse dữ liệu hoặc đồng bộ blocking trong advice mỗi lần submit có thể làm tăng độ trễ. Đo theo tải, số task và mức cạnh tranh thật.

## 20. Ma trận kiểm thử dành cho context-aware pointcut

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Lời gọi đồng bộ cùng thread | Advice nhìn thấy context được set hợp lệ |
| Task gửi sang pool không có carrier | Không ngộ nhận caller ThreadLocal đã truyền |
| Task có carrier | Advice đọc đúng context tại worker |
| Task kế tiếp trên cùng worker | Không rò context từ task trước |
| Scope lồng nhau có giá trị trước đó | Restore về giá trị ban đầu sau scope trong |
| Target ném exception | `finally` vẫn khôi phục context |
| Callback nằm trên executor khác | Context chỉ có khi được tiếp tục truyền đúng |
| Task bị hủy hoặc timeout | Cleanup và trạng thái kết thúc tuân theo contract |
| Argument mutable đổi giữa submit/run | Predicate và target không dùng dữ liệu mâu thuẫn ngoài ý muốn |
| Caller đổi trace ID sau capture | Worker đọc đúng snapshot theo thời điểm đã định |
| Gọi trực tiếp target bỏ qua proxy | Coverage phản ánh đúng giới hạn interception |
| Có nhiều context đồng thời | Không lẫn dữ liệu request giữa worker |
| Message qua process khác | Metadata được serialize/validate và tạo local context |
| Retry tác vụ | Correlation giữ đúng ý nghĩa, side effect nghiệp vụ không bị lặp trái contract |

**Test quan trọng nhất không chỉ là “đã truyền được trace ID”, mà còn là “không có trace ID cũ khi task mới bắt đầu”.**

### Phân biệt ba loại kiểm thử

- **Predicate unit test:** context A/B/null có làm guard hoặc dynamic pointcut cho kết quả đúng không?
- **Integration test:** khi thật sự chuyển thread/callback, carrier và cơ chế AOP có hoạt động ở đường gọi đã thiết kế không?
- **Behavioral test:** target chạy đúng số lần, trả đúng kết quả/ngoại lệ, không bị thay đổi nghiệp vụ trái contract và không rò context.

## 21. Những lỗi phổ biến

1. **Giả định thread mới luôn nhận ThreadLocal của caller.** `ThreadLocal` thông thường gắn riêng với thread.
2. **Dùng InheritableThreadLocal để truyền theo từng submit vào pool.** Thread pool reuse làm giả định này không đáng tin.
3. **Đặt context vào worker nhưng quên `finally`.** Dẫn đến rò thông tin request cũ.
4. **Luôn remove sau scope trong.** Có thể xóa nhầm context hợp lệ ở scope ngoài.
5. **Capture object mutable nhưng gọi nó là snapshot.** Dữ liệu có thể đổi hoặc race trước khi worker đọc.
6. **Tưởng cflow xuyên qua executor.** Quan hệ stack đồng bộ không tự là quan hệ nhân quả giữa các task.
7. **Tưởng future trả về nghĩa là công việc xong.** Nó có thể chỉ đại diện một kết quả sẽ hoàn tất trong tương lai.
8. **Bọc submit nhưng bỏ sót callback.** Ngữ cảnh có thể bị mất ở chặng tiếp theo.
9. **Tưởng propagation sẽ làm proxy chặn mọi lời gọi.** Context đúng không thay thế weaving coverage.
10. **Sao chép authorization mà không xác thực tại boundary.** Có thể dùng quyền đã hết hạn hoặc từ nguồn không đáng tin cậy.
11. **Ghi toàn bộ request context vào log.** Dễ lộ token, PII và tạo metric cardinality rất lớn.
12. **Không kiểm thử task thất bại/cancel/retry.** Cleanup và số lần thực thi có thể khác happy path.
13. **Dùng ngữ cảnh trong thread để suy ra transaction.** Transaction/resource có vòng đời và semantics riêng.
14. **Chọn pointcut theo tên nhưng không tính đến context runtime.** Chữ ký giống nhau không bảo đảm điều kiện của request giống nhau.

## 22. Bài tập tự luyện

1. Chạy `AopContextHandoffDemo.java` và giải thích vì sao `no-transfer` không có dòng `advice` dù main thread đã đặt `REQ-17`.
2. Bỏ khối `finally` trong `carryContext`, chạy lại cùng single-thread executor. Dự đoán và quan sát `after`; từ đó giải thích nguy cơ rò context.
3. Thêm `carryContext` lồng nhau với hai trace ID khác nhau và xác nhận scope bên ngoài được khôi phục chính xác.
4. Thay `RequestContext` bằng một object mutable và sửa giá trị sau khi tạo wrapper; xác định phần nào là snapshot, phần nào vẫn là tham chiếu chia sẻ.
5. Tạo hai task bất đồng bộ nối tiếp bằng `CompletableFuture`. Bọc callback ở từng boundary, rồi chứng minh nếu bỏ một wrapper thì trace có thể mất.
6. Thiết kế một `Callable<T>` wrapper có capture/restore tương đương `Runnable`, không nuốt ngoại lệ và không đổi kiểu kết quả.
7. Thêm nhánh target ném `IllegalArgumentException`. Kiểm tra wrapper luôn restore context, còn handler giữ nguyên ngoại lệ từ target.
8. Phân biệt metric “thời gian `submit`” với metric “thời gian task hoàn tất”. Xác định hai điểm can thiệp/quan sát cần có.
9. Mô phỏng một message từ process A sang B với chỉ ba trường context được phép. Nêu cách B xác thực, khôi phục và cleanup.
10. Viết một bảng kiểm thử có ít nhất ba task của hai request dùng chung một worker, nhằm chứng minh không có cross-task contamination.

**Tự kiểm tra:** Nếu một pointcut thấy `ThreadLocal` trên caller, nó có mặc nhiên thấy cùng giá trị trên worker không? Vì sao `Future.get()` không phải cơ chế propagation? Khi nào nên khôi phục context cũ, khi nào remove? Một dynamic control-flow pointcut có tự mở rộng qua thread khác không? Nếu trace context truyền đúng, lời gọi trực tiếp target có tự chạy advice của proxy không?

## Kết luận

**Ngữ cảnh của AOP luôn gắn với một điểm thực thi cụ thể.** Khi công việc chuyển từ lời gọi đồng bộ sang executor, future, callback, task hoặc tiến trình khác, call stack và trạng thái gắn với thread **không tự đi theo**. Muốn một aspect tiếp tục lựa chọn đúng join point theo ngữ cảnh, cần hiểu semantics của loại pointcut, xác định dữ liệu cần mang theo, truyền có chủ đích bằng contract rõ, khôi phục ở nơi chạy và dọn sạch trong mọi nhánh kết thúc. Đồng thời phải kiểm chứng coverage thực sự của weaving/interception, thời điểm capture, trạng thái mutable và ranh giới bảo mật. Phân biệt các điều này giúp tránh cả **mất ngữ cảnh** lẫn **rò ngữ cảnh giữa các tác vụ**, hai nguồn lỗi đặc biệt khó phát hiện trong hệ thống bất đồng bộ.