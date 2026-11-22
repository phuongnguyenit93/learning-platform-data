# Giữ và khôi phục ngữ cảnh quan sát trong xử lý bất đồng bộ (AOP)

## 1. Mục tiêu và phạm vi

Khi một lời gọi được quan sát bằng **Aspect-Oriented Programming (AOP)** chuyển công việc sang một luồng hoặc tác vụ khác, thông tin dùng để liên kết log, trace và phép đo rất dễ bị mất, dùng nhầm hoặc tồn tại quá lâu. Bài này trình bày cách **chụp (capture), truyền (propagate), gắn (install), khôi phục (restore) và kết thúc (finish)** ngữ cảnh quan sát qua các ranh giới bất đồng bộ.

Sau bài học, bạn có thể:

- Giải thích vì sao advice bao quanh một lời gọi không tự động bao quanh toàn bộ thời gian chạy bất đồng bộ.
- Truyền ngữ cảnh đúng cách qua executor, tác vụ và callback; tránh lẫn ngữ cảnh giữa những request dùng chung luồng.
- Phân biệt **khôi phục trạng thái cục bộ của luồng** với **kết thúc span hoặc observation**.
- Thiết kế advice ghi nhận kết quả khi tác vụ *thực sự hoàn tất*, bao gồm lỗi và hủy.
- Kiểm tra tính đúng đắn và rủi ro về hiệu năng, bảo mật của việc lan truyền ngữ cảnh.

Đây là AOP ở mức khái niệm và kỹ thuật chung. Ví dụ chạy bằng Java 17, sử dụng JDK dynamic proxy làm cơ chế chặn lời gọi; mô hình có thể áp dụng tương tự cho các kiểu weaving/interception khác nếu chúng hỗ trợ join point tương ứng.

## 2. Ngữ cảnh quan sát là gì?

**Ngữ cảnh quan sát (observation context)** là tập dữ liệu đi kèm một đơn vị công việc để các tín hiệu quan sát có thể được liên kết với nhau. Một ngữ cảnh thường chứa:

| Thành phần | Vai trò |
|---|---|
| Trace ID | Liên kết các span thuộc cùng một hành trình xử lý |
| Span ID và parent span ID | Biểu diễn quan hệ cha–con giữa các bước |
| Correlation/request ID | Ghép các dòng log hoặc sự kiện có liên quan |
| Baggage/thuộc tính truyền kèm | Mang một số thông tin cần thiết giữa các ranh giới, có kiểm soát |
| Trạng thái lấy mẫu và các cờ trace | Hỗ trợ quyết định thu thập dữ liệu quan sát |

**Ngữ cảnh** khác với **span**: ngữ cảnh mang danh tính và quan hệ cần thiết để tiếp tục công việc; span là bản ghi một hoạt động có thời điểm bắt đầu/kết thúc, trạng thái, thuộc tính và sự kiện. Một span có thể kết thúc trong khi bản chụp ngữ cảnh vẫn tồn tại ở nơi khác; giữ bản chụp không có nghĩa là span còn chạy.

**Ngữ cảnh** cũng khác với nơi lưu trữ nó. Một `ThreadLocal` hoặc ngữ cảnh log kiểu MDC chỉ là cách đặt dữ liệu vào *luồng hiện tại*; nó không tự gửi dữ liệu sang luồng khác. Trong hệ thống phân tán, sự truyền tiếp thường dùng các trường của giao thức, chẳng hạn `traceparent` và `tracestate` theo W3C Trace Context; đó là ranh giới mạng, khác với việc chuyển task trong cùng JVM.

Không nên mặc định mang theo cả đối tượng request, dữ liệu cá nhân, token hoặc quyền truy cập. Dữ liệu phục vụ quan sát cần tối thiểu, bất biến khi có thể, và có chính sách vòng đời rõ ràng.

## 3. Vì sao advice đồng bộ chưa đủ?

Xét một phương thức:

```java
CompletableFuture<Result> loadAsync(String id);
```

Một `around advice` thông thường thực hiện:

1. Ghi nhận thời điểm bắt đầu.
2. Gọi `proceed()` (hoặc phương thức đích qua interceptor).
3. Nhận ngay một `CompletableFuture<Result>` **chưa hoàn tất**.
4. Chạy `finally` và trả kết quả là future.
5. Sau đó, ở một luồng khác, tác vụ mới thành công hoặc thất bại.

Nếu đóng span ngay tại bước 4, phép đo phản ánh **thời gian lập lịch/trả future**, không phản ánh **thời gian hoàn tất tác vụ**. Nếu chỉ đặt trace ID vào `ThreadLocal` trước bước 2, bước 5 trên một worker thread chưa chắc thấy trace ID. Hai vấn đề độc lập cần xử lý:

- **Vấn đề truyền ngữ cảnh:** công việc ở phía sau ranh giới có đúng trace/span cha hay không?
- **Vấn đề vòng đời quan sát:** hoạt động được kết thúc lúc trả future hay lúc future hoàn tất?

Dòng thời gian:

```text
Luồng gọi:    [advice mở] -- [proceed -> trả future] -- [advice trả] ---- ...
                                             |
Executor:                                     +--> [task chạy] --> [complete]
Callback:                                                        +--> [record/end]
```

Ở lời gọi đồng bộ, `finally` thường có thể kết thúc observation. Ở lời gọi trả về một kết quả bất đồng bộ, advice cần gắn cơ chế hoàn tất thích hợp, đồng thời vẫn dọn sạch ngữ cảnh đã gắn lên luồng gọi ngay khi rời khỏi lời gọi.

## 4. Quy tắc bất biến: capture → install → execute → restore

Tại mỗi ranh giới bất đồng bộ, thực hiện bốn bước:

1. **Capture:** chụp ngữ cảnh của công việc *tại thời điểm đăng ký/gửi việc*, trước khi rời luồng gọi. Một bản chụp bất biến thường an toàn hơn tham chiếu tới đối tượng trạng thái có thể bị sửa.
2. **Install:** trên luồng thực thi, lưu ngữ cảnh đang có ở luồng ấy và gắn bản chụp vào phạm vi chạy tác vụ.
3. **Execute:** chạy công việc, phát log/tạo span con hoặc thu thập sự kiện theo ngữ cảnh vừa gắn.
4. **Restore:** trong `finally`, trả ngữ cảnh trước đó về đúng trạng thái; nếu trước đó không có thì xóa giá trị của luồng.

Bất biến quan trọng:

> Sau khi task hoặc callback kết thúc (thành công hay ném lỗi), luồng thực thi phải có **đúng ngữ cảnh nó có trước lúc install**.

Vì vậy, **restore không có nghĩa là luôn gọi remove**: khi các scope lồng nhau, xóa thẳng sẽ làm mất ngữ cảnh bên ngoài. Ngược lại, chỉ `set` mà không restore sẽ để ngữ cảnh request A rò sang request B trên cùng worker của thread pool.

Đối với một luồng nhận nhiều tác vụ, mỗi lần submit phải có **snapshot riêng**. Chụp một lần khi tạo executor, rồi dùng lại mãi, sẽ làm mọi tác vụ kế tiếp nhận cùng ngữ cảnh cũ.

## 5. Ví dụ Java 17 hoàn chỉnh: proxy AOP và executor có truyền ngữ cảnh

Ví dụ sau dùng:

- `Context`: giá trị quan sát bất biến (trace ID, span ID).
- `install(...)`/`Scope`: lưu–gắn–khôi phục ngữ cảnh, kể cả khi có lỗi.
- `contextAware(...)`: bộ trang trí `Executor`, chụp ngữ cảnh khi submit và gắn lại khi worker chạy.
- `traced(...)`: interceptor dạng dynamic proxy. Nó gắn ngữ cảnh con khi gọi phương thức và dùng `whenComplete` để ghi nhận **lúc future hoàn tất**.

Lưu nguyên mã vào **AsyncObservationDemo.java**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncObservationDemo {
    record Context(String traceId, String spanId) {}

    private static final ThreadLocal<Context> CURRENT = new ThreadLocal<>();

    @FunctionalInterface
    interface Scope extends AutoCloseable {
        @Override void close();
    }

    static Scope install(Context next) {
        Context previous = CURRENT.get();
        if (next == null) CURRENT.remove();
        else CURRENT.set(next);
        return () -> {
            if (previous == null) CURRENT.remove();
            else CURRENT.set(previous);
        };
    }

    static Executor contextAware(Executor delegate) {
        return command -> {
            Context captured = CURRENT.get(); // chụp lúc submit
            delegate.execute(() -> {
                try (Scope ignored = install(captured)) {
                    command.run();
                }
            });
        };
    }

    interface Job {
        CompletableFuture<String> execute(String text);
    }

    static final class JobImpl implements Job {
        private final Executor executor;

        JobImpl(Executor executor) { this.executor = executor; }

        @Override
        public CompletableFuture<String> execute(String text) {
            return CompletableFuture.supplyAsync(() -> {
                Context context = CURRENT.get();
                String trace = context == null ? "missing" : context.traceId();
                return text.toUpperCase(Locale.ROOT) + " | " + trace;
            }, executor);
        }
    }

    static Job traced(Job target, AtomicReference<String> completed) {
        return (Job) Proxy.newProxyInstance(
            Job.class.getClassLoader(),
            new Class<?>[] { Job.class },
            (proxy, method, args) -> {
                Context parent = CURRENT.get();
                Context child = new Context(
                    parent == null ? "new-trace" : parent.traceId(), "work-1");
                try (Scope ignored = install(child)) {
                    final CompletableFuture<?> future;
                    try {
                        future = (CompletableFuture<?>) method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        completed.set("complete | " + CURRENT.get().traceId() + " | error");
                        throw ex.getCause();
                    }
                    return future.whenComplete((value, error) -> {
                        try (Scope completionScope = install(child)) {
                            completed.set("complete | " + CURRENT.get().traceId()
                                    + " | " + (error == null ? "ok" : "error"));
                        }
                    });
                }
            });
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(1);
        try {
            AtomicReference<String> completed = new AtomicReference<>();
            Job service = traced(new JobImpl(contextAware(pool)), completed);
            try (Scope requestScope = install(new Context("trace-42", "request-1"))) {
                System.out.println(service.execute("hello").join());
                System.out.println(completed.get());
                System.out.println(CURRENT.get().spanId());
            }
            System.out.println(CURRENT.get() == null);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AsyncObservationDemo.java
java AsyncObservationDemo
```

Kết quả chuẩn:

```text
HELLO | trace-42
complete | trace-42 | ok
request-1
true
```

Diễn giải:

- `trace-42` được chụp trong `contextAware` khi `supplyAsync` gửi việc, nên worker đọc đúng trace ID.
- Khi `traced` rời `proceed` và trả future, scope của luồng gọi trở lại `request-1`; nó không giữ `work-1` treo trên luồng gọi trong thời gian chờ.
- Callback `whenComplete` cài lại ngữ cảnh của hoạt động để ghi kết quả rồi khôi phục giá trị vốn có trên luồng callback.
- `join()` chờ future *đã được gắn callback hoàn tất*, nên dòng `complete ...` đã được ghi trước khi in.
- Sau khi đóng `requestScope`, `CURRENT` của main không còn dữ liệu (`true`).

**Giới hạn cố ý của demo:** `work-1` và `new-trace` là mã cố định để dễ theo dõi; trong thực tế cần sinh ID phù hợp và duy nhất. `AtomicReference` mô phỏng bộ ghi trạng thái chứ không phải hệ thống trace thực; một interceptor tổng quát phải xét nhiều kiểu phương thức, lời gọi `Object`, giá trị trả về khác `CompletableFuture`, lỗi trong phép ghi quan sát và các chính sách hủy. Ví dụ này minh họa một phương thức của giao diện `Job`, không phải bộ AOP production.

## 6. Bao phủ các ranh giới bất đồng bộ phổ biến

### 6.1. Executor, Runnable và Callable

Đối với `Executor.execute(Runnable)`, wrapper ở ví dụ là điểm chèn phù hợp: chụp lúc gửi tác vụ, gắn lúc thực thi, khôi phục khi xong. Với `ExecutorService.submit(Callable<T>)`, nguyên tắc tương tự, nhưng wrapper phải trả kết quả và ném lại ngoại lệ từ `call()`:

```java
// Đoạn minh họa đặt trong lớp đã có CURRENT, Context và Scope.
static <T> java.util.concurrent.Callable<T> wrap(
        java.util.concurrent.Callable<T> task) {
    Context captured = CURRENT.get();
    return () -> {
        try (Scope ignored = install(captured)) {
            return task.call();
        }
    };
}
```

Lưu ý: không chỉ bọc phần `submit` ở luồng gọi; việc cần làm là bọc **thân tác vụ** sẽ chạy ở luồng nhận. Khi một task tiếp tục sinh task con, task con phải chụp ngữ cảnh của nơi nó được sinh ra.

### 6.2. CompletableFuture và chuỗi callback

Một chuỗi gồm `supplyAsync`, `thenApply`, `thenCompose`, `handle`, `whenComplete` có thể chạy qua nhiều ranh giới:

- Các phương thức *Async* có executor tường minh có thể dùng executor được trang trí. Không khai báo executor thường dẫn đến việc chạy trên cơ chế thực thi mặc định; không nên giả định có ngữ cảnh đã được gắn.
- Callback **không có hậu tố Async** có thể chạy trên luồng hoàn thành stage trước đó hoặc ngay tại luồng đăng ký khi stage đã hoàn tất. Không thể đoán luồng callback chỉ từ tên phương thức.
- Nếu cần bảo đảm callback nhận ngữ cảnh **tại lúc đăng ký**, hãy chụp và bọc **chính callback**. Đây là điểm khác với chỉ bọc executor, vì người submit thực tế có thể là luồng hoàn thành khác ngữ cảnh.

Ví dụ hàm bọc callback, dùng chung các thành phần của lớp demo:

```java
static <T, R> java.util.function.Function<T, R> wrap(
        java.util.function.Function<T, R> callback) {
    Context captured = CURRENT.get(); // thời điểm đăng ký callback
    return value -> {
        try (Scope ignored = install(captured)) {
            return callback.apply(value);
        }
    };
}

// Ví dụ sử dụng bên trong phạm vi có ngữ cảnh:
// CompletableFuture<String> normalized =
//     source.thenApply(wrap(value -> value.trim()));
```

Nếu callback trả về một `CompletionStage` khác (ví dụ `thenCompose`), gắn ngữ cảnh vào lúc gọi callback **không bảo đảm** công việc sâu bên trong stage mới được truyền tiếp. Các ranh giới do stage đó sử dụng vẫn phải có cơ chế propagation riêng.

### 6.3. Queue, event loop và bộ lập lịch

Với hàng đợi, cơ chế enqueue/dequeue có thể diễn ra trên hai luồng khác nhau. Chụp ngữ cảnh vào một envelope chứa task/message ở lúc enqueue, gắn quanh handler khi dequeue, rồi restore. Tác vụ định kỳ cần một chính sách riêng: kế thừa ngữ cảnh lúc đăng ký lịch hay bắt đầu trace mới cho mỗi lần kích hoạt? Không tự mặc định mang trace của request ban đầu vào một công việc sẽ lặp nhiều giờ.

Trong event loop, thời gian giữ scope phải ngắn và đúng đoạn thực sự chạy. Không giữ `ThreadLocal` của request qua một thao tác `await` giả định; khi event loop xử lý nhiều request xen kẽ, dữ liệu của một request có thể lây sang request khác.

### 6.4. Qua mạng và tiến trình

Truyền ngữ cảnh nội bộ JVM không tự tạo ra header mạng. Tại phía gửi, serialize các trường propagation được cho phép; tại phía nhận, parse và validate chúng, tạo ngữ cảnh cục bộ phù hợp rồi chạy handler trong scope. Trace ID và quan hệ span có thể nối tiếp xuyên tiến trình, nhưng **ngữ cảnh bảo mật/ủy quyền không nên được tin chỉ vì có mặt trong trace header**. Cần giới hạn kích thước, định dạng và mức độ tin cậy của baggage từ bên ngoài.

## 7. Thiết kế advice theo vòng đời bất đồng bộ

Một around advice quan sát thường có hai phạm vi khác nhau:

**Phạm vi gắn ngữ cảnh trên luồng gọi:** bắt đầu trước khi gọi phương thức đích và đóng trong `finally`/try-with-resources, bất kể phương thức trả đồng bộ, trả future hay ném lỗi ngay.

**Vòng đời observation/span:** bắt đầu tại lúc chặn lời gọi; đối với thao tác trả kết quả bất đồng bộ, kết thúc khi completion tương ứng báo thành công, lỗi hoặc hủy theo hợp đồng của kiểu trả về.

Một khung tư duy:

```text
around(joinPoint):
    parent = currentContext()
    span = startChildObservation(parent)
    try with install(span.context):
        try:
            result = proceed()
        catch immediateError:
            recordFailureAndEnd(span, immediateError)
            throw immediateError

        if result is supportedAsyncHandle:
            return observeCompletion(result, span)  // callback kết thúc span
        else:
            recordSuccessAndEnd(span)
            return result
    finally:
        restoreCallerThreadContext()
```

Đây là **pseudocode**, không phải Java hoàn chỉnh. Trong triển khai thực, tránh ghi kết thúc hai lần khi có đua tranh giữa callback hoàn thành, hủy và timeout. Một bộ ghi kết thúc span nên được bảo vệ bằng trạng thái hoàn tất một lần (ví dụ `AtomicBoolean.compareAndSet(false, true)`), nếu nhiều con đường có thể gọi `end`.

**Lưu ý về kiểu trả về:** gắn `whenComplete` sinh ra một stage *mới*; nếu hợp đồng yêu cầu đúng instance future gốc, cách gắn lời quan sát có thể phải khác. Đối với `CompletionStage`, không được giả định mọi implementation có thể ép về `CompletableFuture`. Đối với publisher/stream lười, thời điểm gọi phương thức có thể chỉ tạo mô tả pipeline: quan sát cần theo **subscription, signal, termination và cancel**, tùy hợp đồng, thay vì đóng tại lúc trả publisher.

**Lỗi và hủy:** phân biệt ba tình huống: (1) `proceed` ném lỗi ngay, (2) future hoàn thành exceptionally, (3) future bị cancel. Trong `CompletableFuture`, hủy được biểu diễn bằng hoàn thành ngoại lệ với `CancellationException`; callback nên phân loại rõ trạng thái hủy nếu công cụ quan sát cần một nhãn riêng. `whenComplete` có thể gặp `CompletionException` ở các tầng bao, vì vậy chỉ unwrap khi đã hiểu hợp đồng và vẫn phải giữ nguyên nguyên nhân phục vụ chẩn đoán.

**Lỗi của chính interceptor:** lỗi khi xuất log/metric/trace không nên làm một tính toán nghiệp vụ đang thành công trở thành thất bại ngoài ý muốn. Chọn chính sách rõ ràng (cách ly lỗi telemetry, ghi nhận ở kênh chẩn đoán khác và không che lỗi gốc); luôn restore ngữ cảnh, kể cả khi recorder lỗi.

## 8. Những lỗi thường gặp và cách nhận diện

| Dấu hiệu | Nguyên nhân điển hình | Cách sửa |
|---|---|---|
| Log trong worker thiếu trace ID | Chỉ gắn `ThreadLocal` ở luồng gọi | Chụp lúc submit/đăng ký và cài lại quanh task hoặc callback |
| Request B mang trace ID của A | Không restore/clear ngữ cảnh ở worker tái sử dụng | Lưu ngữ cảnh cũ, restore trong `finally` |
| Span kết thúc quá sớm | Advice đo tới lúc trả future | Quan sát completion của thao tác bất đồng bộ |
| Span không bao giờ kết thúc | Chỉ nghe success, bỏ qua exceptional/cancel | Gắn handler cho mọi trạng thái kết thúc có liên quan |
| Callback đọc sai parent span | Chỉ bọc executor, snapshot được lấy trên luồng hoàn thành | Chụp ngữ cảnh tại lúc đăng ký callback nếu đó là ngữ nghĩa mong muốn |
| Scope ngoài biến mất sau callback lồng nhau | Luôn `remove()` khi đóng scope | Restore giá trị trước lúc install |
| Tăng memory/cost đáng kể | Chụp đối tượng request lớn, gắn thuộc tính quá nhiều | Snapshot tối thiểu, bất biến; giới hạn cardinality và baggage |
| Method nội bộ không được quan sát | Một cơ chế proxy chỉ intercept lời gọi đi **qua proxy** | Xác định rõ phạm vi join point, đường gọi nội bộ và khả năng weaving |

`InheritableThreadLocal` không phải lời giải phổ quát cho thread pool: nó kế thừa trạng thái khi **tạo thread**, không phản ánh ngữ cảnh của từng lần submit, có thể giữ dữ liệu cũ lâu dài. Không dựa vào kế thừa ngầm để thay cho propagation có kiểm soát. Với virtual thread, vẫn cần xét ngữ cảnh tại nơi task được tạo và tất cả callback/luồng chuyển tiếp; khác biệt mô hình thread không tự giải quyết vòng đời span.

## 9. Kiểm thử hành vi quan sát

Nên kiểm thử bằng các tình huống có khả năng bắt lỗi ngữ cảnh, thay vì chỉ kiểm tra output nghiệp vụ:

1. **Luồng worker tái sử dụng:** dùng pool một luồng, lần lượt xử lý request A và B với trace khác nhau; B tuyệt đối không thấy trace của A.
2. **Task lỗi:** body ném ngoại lệ; kiểm tra ngoại lệ gốc vẫn được trả, completion được ghi là lỗi, ngữ cảnh worker được restore.
3. **Callback hoàn thành ngay:** stage đã hoàn tất trước khi đăng ký callback; callback có thể chạy ngay trên luồng đăng ký nhưng phải thấy đúng snapshot.
4. **Scope lồng nhau:** cài parent rồi child; đóng child phải trở lại parent, đóng parent phải trở lại trạng thái ban đầu.
5. **Fan-out/fan-in:** một lời gọi sinh nhiều nhánh song song; mọi nhánh cùng trace nhưng có span ID riêng; mỗi nhánh kết thúc độc lập và không ảnh hưởng nhau.
6. **Hủy và timeout:** xác nhận span/observation có trạng thái đúng theo hợp đồng và không bị end hai lần.
7. **Không có ngữ cảnh ban đầu:** tác vụ không kế thừa ngẫu nhiên dữ liệu từ worker; chính sách tạo root trace hoặc không tạo trace cần rõ ràng.
8. **Lỗi telemetry:** giả lập recorder ném lỗi; ngữ cảnh vẫn được dọn sạch, kết quả nghiệp vụ giữ đúng chính sách đã chọn.

Trong kiểm thử có cạnh tranh, nên dùng `CountDownLatch` hoặc barrier điều khiển thứ tự chạy, tránh dùng `Thread.sleep` làm bằng chứng chắc chắn. Đối chiếu trace ID/span ID và trạng thái scope trực tiếp tại mỗi điểm chặn thay vì chỉ suy từ vị trí log.

## 10. Hiệu năng và quyết định thiết kế

Propagation tạo chi phí capture, phân bổ wrapper, install/restore và thao tác với bộ ghi quan sát. Với tác vụ rất nhỏ, chi phí này có thể thấy rõ; hãy đo bằng workload thực tế trước khi tối ưu. Không truyền mọi thuộc tính và không sinh span con cho mọi phép biến đổi vụn vặt: xác định granularity theo giá trị chẩn đoán.

Cần xác định **ranh giới mà instrumentation sở hữu**: bọc tại executor, tại API đăng ký callback, tại message handler, hoặc phối hợp nhiều nơi. Bọc hai lần cùng một ranh giới có thể tạo scope thừa hoặc span trùng; ngược lại, chỉ bọc lời gọi vào phương thức ban đầu sẽ bỏ sót các continuation phát sinh phía sau.

Một chính sách tốt cần trả lời rõ:

- Snapshot lấy ở thời điểm **gọi**, **submit**, **đăng ký callback**, hay **subscription**?
- Span đại diện thời gian xếp hàng cộng thực thi, chỉ thời gian thực thi, hay toàn bộ kết quả end-to-end?
- Khi parent span đã kết thúc mà child vẫn chạy, quan hệ được biểu diễn thế nào?
- Ai sở hữu việc kết thúc observation, và làm sao bảo đảm kết thúc đúng một lần?
- Ngữ cảnh nào được truyền qua mạng và thuộc tính nào phải loại bỏ vì nhạy cảm hoặc quá nhiều giá trị khác nhau?

## 11. Ghi nhớ

**AOP quan sát một lời gọi không đồng nghĩa với quan sát trọn công việc bất đồng bộ.** Để trace và log đáng tin, phải truyền snapshot qua đúng ranh giới thực thi; để tránh rò ngữ cảnh, phải khôi phục trạng thái cũ của từng luồng trong `finally`; để đo đúng vòng đời, phải chờ tín hiệu hoàn tất thích hợp và ghi nhận success, error hoặc cancel. Ba thao tác **propagate, restore, finish** bổ sung cho nhau, nhưng không thể thay thế nhau.
