# Chụp ngữ cảnh ở bên gửi rồi khôi phục trạng thái cũ bằng `try-finally`

**Module:** Spring Framework - concurrency  
**Nhóm:** Ngữ cảnh thực thi  
**Chủ đề:** Chụp ngữ cảnh ở bên gửi rồi khôi phục trạng thái cũ bằng `try-finally`.

## 1. Vấn đề: một request đi qua nhiều thread nhưng ngữ cảnh không tự đi theo

Trong ứng dụng Spring, request HTTP ban đầu thường có những thông tin phục vụ xử lý và quan sát: `traceId`, `requestId`, tên tenant, locale hoặc một ngữ cảnh bảo mật. Một số thư viện lưu thông tin này trong `ThreadLocal` hay MDC (Mapped Diagnostic Context) để không phải truyền thủ công vào mọi phương thức ghi log.

Ví dụ một request có `traceId=REQ-A` rồi gọi phương thức `@Async`:

```text
Servlet thread: http-nio-8080-exec-1
   MDC.traceId = REQ-A
           |
           | executor.execute(task)
           v
Thread pool worker: business-1
   MDC.traceId = ?     <- không tự động giống thread gửi
```

**`ThreadLocal` gắn dữ liệu với thread, không gắn với logical request hoặc Runnable.** Khi một `Runnable` chuyển từ thread nhận request sang thread trong pool, giá trị `ThreadLocal` của thread gửi không tự được sao chép sang thread worker. Executor có thể sử dụng lại cùng worker cho hàng nghìn task khác nhau.

Nếu worker từng xử lý request A và để sót `traceId=A`, task B chạy tiếp trên worker đó có thể:

- Ghi log với `traceId` của A dù B đến từ request khác.
- Dùng nhầm ngữ cảnh tenant/người dùng nếu code dựa vào ThreadLocal.
- Làm lệch quan sát lỗi, audit và thống kê request.
- Rò dữ liệu nhạy cảm giữa các logical requests.

Hai yêu cầu cần giải quyết **cùng lúc**:

1. **Truyền đúng snapshot của thread gửi** tại thời điểm task được giao.
2. **Khôi phục chính xác trạng thái thread worker vốn có** sau khi task kết thúc — **kể cả task ném exception**.

Giải pháp là **capture → install → run → restore** với `try-finally`, không phải chỉ gán một giá trị rồi hy vọng pool tự xóa.

## 2. Bốn thời điểm và một bất biến không được vi phạm

Giả sử thread gửi đang có `requestId=A`, worker đang có `requestId=WORKER-BASELINE` do đoạn code bao ngoài cài tạm. Quy trình:

```text
T0: SUBMITTER                         T1: WORKER
    requestId = A                        requestId = WORKER-BASELINE
         |
    capture snapshot = A
         |
    executor.execute(wrappedTask) ----------->
                                              previous = WORKER-BASELINE
                                              try {
                                                  install(A)
                                                  delegate.run()
                                              } finally {
                                                  restore(WORKER-BASELINE)
                                              }
                                          -> requestId = WORKER-BASELINE
```

**Bất biến quan trọng:** sau khi callback hoàn tất (thành công hoặc thất bại), ngữ cảnh thread chạy phải quay về **đúng trạng thái trước khi callback bắt đầu**, không phải về một hằng số hay về snapshot của request trước.

| Thời điểm | Thread thực hiện | Hành động |
| --- | --- | --- |
| T0 — tạo wrapper / giao task | Thread **gửi** | Đọc/copy các giá trị cần truyền; không đợi tới worker |
| T1 — bắt đầu `run()` | Thread **thực thi** | Đọc trạng thái hiện tại của worker và lưu vào `previous` |
| T2 — trước khi gọi business work | Thread thực thi | Cài snapshot từ bên gửi; nếu snapshot không có giá trị thì **xóa** giá trị cũ |
| T3 — trong `finally` | Thread thực thi | Khôi phục `previous` — kể cả business work lỗi, có lệnh `return`, hoặc decorator lồng nhau |

### Vì sao phải snapshot **trước khi đưa vào queue**?

Một task có thể chờ hàng giây trước khi worker lấy ra. Trong thời gian đó, HTTP thread có thể:

- Đổi `traceId` để xử lý một đoạn khác.
- Xóa MDC khi hoàn tất request.
- Bị servlet container tái sử dụng cho request tiếp theo.

Nếu wrapper chụp giá trị **bên trong `run()`**, nó sẽ đọc ngữ cảnh **của worker tại thời điểm chạy**, không phải của request khi submit. Phải chụp trong `execute(...)`, `decorate(...)` hoặc tại callsite ở **thread gửi**.

## 3. Mẫu Java tối thiểu, đúng thứ tự

Một wrapper cơ bản cho `ThreadLocal<String>`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void setOrRemove(String value) {
    if (value == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(value);
    }
}

static Runnable wrapWithCurrentContext(Runnable delegate) {
    String captured = REQUEST_ID.get(); // Thread gửi: CHỤP NGAY.
    return () -> {
        String previous = REQUEST_ID.get(); // Thread chạy: LƯU NGỮ CẢNH CŨ.
        try {
            setOrRemove(captured);       // Cài snapshot, kể cả null.
            delegate.run();             // Chạy nghiệp vụ.
        } finally {
            setOrRemove(previous);       // Phục hồi chính xác.
        }
    };
}
```

Đây là **đoạn thành viên minh họa**, cần đặt trong class có import phù hợp. Nếu dùng:

```java
executor.execute(wrapWithCurrentContext(() -> process()));
```

`process()` và `executor` phải được ứng dụng định nghĩa. **Điểm quan trọng:** `wrapWithCurrentContext()` được gọi tại thread submitter trước `executor.execute`, và `delegate.run()` chỉ được gọi **một lần** trong wrapper.

`ThreadLocal.remove()` tốt hơn `ThreadLocal.set(null)` khi muốn bỏ hẳn binding. Nếu `previous == null`, ta **remove** trong `finally`; nếu trước đó worker có giá trị khác null, phải **set lại giá trị đó**, không chỉ `remove()` một cách vô điều kiện.

Một số thư viện cho phép snapshot chứa nhiều trường, nhưng nguyên tắc vẫn như nhau: snapshot bất biến hoặc sao chép phòng vệ tại thời điểm gửi; lưu **toàn bộ trạng thái cần phục hồi** tại thời điểm chạy; dọn/khôi phục qua `finally`.

## 4. Vì sao chỉ `remove()` trong `finally` có thể sai?

Mẫu thường thấy:

```java
Runnable wrapped = () -> {
    REQUEST_ID.set(capturedId);
    try {
        businessWork();
    } finally {
        REQUEST_ID.remove();
    }
};
```

Đây là đoạn minh họa, `capturedId` và `businessWork()` do ứng dụng cung cấp. Mẫu này có thể đủ trong **một** hệ thống mà worker luôn bắt đầu với trạng thái trống và không có wrapper lồng nhau, nhưng **không phục hồi đúng trạng thái cũ**.

Ví dụ:

1. Task ngoài cài `requestId=A`.
2. Một component trong task ngoài gọi executor chạy **trực tiếp trên cùng thread** (`Runnable::run`) hoặc `CallerRunsPolicy`, tạo task trong với `requestId=B`.
3. Task trong kết thúc và gọi `remove()`.
4. Task ngoài tiếp tục chạy, nhưng `requestId=A` đã **bị xóa**.

```text
Ngoài:  previous=null -> set A
    Trong: previous=A -> set B -> finally restore A   [đúng]
Ngoài:  vẫn thấy A -> finally restore null
```

Dùng `try-finally` **restore previous**, không chỉ cleanup thành “trống”, để composable với nested decorators và executor có thể chạy inline. Với worker mới hoàn toàn trống, `previous=null`, kết quả cuối vẫn là `remove()`, nhưng nguyên tắc tổng quát hơn giúp không phá context của code bao ngoài.

### `CallerRunsPolicy` làm vấn đề này trở nên thực tế

Khi pool đầy, `ThreadPoolExecutor.CallerRunsPolicy` có thể chạy task **ngay trên thread đang submit**, nếu executor chưa shutdown. `try-finally` phải khôi phục ngữ cảnh của **thread đó**, dù nó vốn là servlet/request thread chứ không phải worker cố định. Đừng viết decorator giả định mọi task luôn chạy trên một thread mới và luôn có `ThreadLocal` trống.

## 5. Vì sao snapshot cần được copy, không chỉ giữ một tham chiếu?

Với giá trị bất biến như `String requestId`, việc lưu tham chiếu tới `String` là đủ. Nhưng một `ThreadLocal<Map<String,String>>` chứa **đối tượng mutable** có thể bị thread gửi sửa sau khi submit:

```java
Map<String, String> captured = currentMap; // Chỉ copy tham chiếu!
executor.execute(() -> use(captured));
currentMap.put("tenant", "another-tenant");
```

Đây là đoạn minh họa (`currentMap`, `executor`, `use` phải tồn tại). Worker có thể nhìn thấy dữ liệu bị đổi muộn, thậm chí có race khi nhiều thread đọc/ghi `HashMap` không an toàn.

Khi cần snapshot:

```java
Map<String, String> captured =
        currentMap == null ? Map.of() : Map.copyOf(currentMap);
```

Đây là đoạn minh họa Java 17; `Map.copyOf` tạo bản map không cho sửa bằng API map nhưng **chỉ copy nông**: nếu value là object mutable thì value đó vẫn dùng chung tham chiếu. `Map.copyOf` cũng không chấp nhận key/value null. Với cấu trúc lồng nhau, phải xác định copy sâu ở các phần cần thiết hoặc chuyển sang một DTO bất biến đã được validate.

**Đừng snapshot cả object HTTP request, session, JDBC connection, entity manager, transaction hay credential nhạy cảm** chỉ để tiện. Nên truyền **giá trị tối thiểu**, ví dụ `correlationId`, tenant ID được xác thực và các tham số nghiệp vụ cần thiết.

### Snapshot khác với “ngữ cảnh luôn cập nhật”

Context propagation dùng **giá trị tại thời điểm submit**; nếu thread gửi đổi `traceId` sau đó, task đã xếp queue vẫn dùng snapshot cũ. Đó là tính chất được mong muốn để log thuộc về đúng request ban đầu.

## 6. Java 17 chạy độc lập: chụp đúng lúc submit, thử lỗi và phục hồi cả worker/caller

Chương trình dưới đây không cần Spring, cho phép kiểm chứng **chính xác** ý nghĩa của `try-finally`. Nó dùng một single-thread executor để chứng minh thread được tái sử dụng. `CountDownLatch` giữ worker trong khi thread gửi đổi context, nên test không dựa vào `Thread.sleep` hay đoán scheduling.

Mục tiêu:

- Chụp `request-A` **trước khi task chạy**, dù caller đổi thành `changed-after-submit`.
- Task của request B thấy `request-B` chứ không thấy A.
- Nếu thread gửi **không có context**, task phải thấy `null`, dù worker có sẵn `worker-baseline`.
- Task ném lỗi vẫn khiến worker trở về context ban đầu.
- Executor chạy inline (`Runnable::run`) cũng phải phục hồi context của **caller** sau khi callback sửa ThreadLocal.
- `FutureTask` giữ exception cho `Future.get`, trong khi `finally` của wrapper vẫn chạy.

Lưu toàn bộ vào **`ContextSnapshotDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class ContextSnapshotDemo {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static void setOrRemove(String value) {
        if (value == null) {
            REQUEST_ID.remove();
        } else {
            REQUEST_ID.set(value);
        }
    }

    static final class SnapshotExecutor implements Executor {
        private final Executor delegate;

        SnapshotExecutor(Executor delegate) {
            this.delegate = delegate;
        }

        @Override
        public void execute(Runnable task) {
            // CHỤP trong thread submitter, trước khi đưa task vào queue.
            String captured = REQUEST_ID.get();

            delegate.execute(() -> {
                // LƯU trong thread thực sự chạy task.
                String previous = REQUEST_ID.get();
                try {
                    setOrRemove(captured);
                    task.run();
                } finally {
                    setOrRemove(previous);
                }
            });
        }
    }

    static <T> Future<T> submit(Executor executor, Callable<T> work) {
        FutureTask<T> future = new FutureTask<>(work);
        executor.execute(future);
        return future;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            // Thiết lập context cũ trên thread worker để kiểm tra phục hồi.
            raw.submit(() -> setOrRemove("worker-baseline")).get();

            SnapshotExecutor propagated = new SnapshotExecutor(raw);

            // Giữ worker bận để task A chắc chắn còn trong queue.
            raw.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker not started");
            }

            setOrRemove("request-A");
            Future<String> first = submit(propagated, REQUEST_ID::get);

            // Đổi context SAU khi submit nhưng TRƯỚC khi task A chạy.
            setOrRemove("changed-after-submit");
            release.countDown();

            System.out.println("snapshotAtSubmit=" + first.get());

            setOrRemove("request-B");
            System.out.println("secondRequest=" +
                    submit(propagated, REQUEST_ID::get).get());

            // Snapshot null phải xóa tạm context của worker.
            setOrRemove(null);
            System.out.println("missingSnapshot=" +
                    submit(propagated, () ->
                            REQUEST_ID.get() == null
                                    ? "<none>" : REQUEST_ID.get()).get());

            setOrRemove("request-error");
            Future<String> failure = submit(propagated, () -> {
                throw new IllegalStateException("boom");
            });
            try {
                failure.get();
            } catch (ExecutionException ex) {
                System.out.println("failure=" +
                        ex.getCause().getClass().getSimpleName());
            }

            // Kiểm tra cùng mẫu decorator khi chạy ngay trên caller.
            setOrRemove("caller-before-inline");
            SnapshotExecutor direct =
                    new SnapshotExecutor(Runnable::run);
            direct.execute(() -> setOrRemove("temporary-in-task"));

            System.out.println("callerAfterInline=" + REQUEST_ID.get());
            setOrRemove(null);

            // Đọc trực tiếp từ raw executor để xác nhận phục hồi worker.
            String restoredWorker = raw.submit(
                    (Callable<String>) REQUEST_ID::get).get();
            System.out.println("workerAfterAll=" + restoredWorker);
        } finally {
            release.countDown();
            setOrRemove(null);
            raw.shutdown();
            if (!raw.awaitTermination(5, TimeUnit.SECONDS)) {
                raw.shutdownNow();
            }
        }
    }
}
```

Chạy tại thư mục chứa file bằng Java 17+:

```bash
javac ContextSnapshotDemo.java
java ContextSnapshotDemo
```

**Stdout của chương trình khi hoàn tất bình thường:**

```text
snapshotAtSubmit=request-A
secondRequest=request-B
missingSnapshot=<none>
failure=IllegalStateException
callerAfterInline=caller-before-inline
workerAfterAll=worker-baseline
```

Giải thích:

1. `snapshotAtSubmit=request-A` dù `REQUEST_ID` phía gửi đã đổi trước khi worker được thả. Wrapper chụp ở lúc `execute`, không phải khi chạy.
2. `secondRequest=request-B`: task B không thừa hưởng A hay baseline từ lần worker dùng trước.
3. `missingSnapshot=<none>`: wrapper xử lý snapshot null bằng `remove`, tránh đọc giá trị cũ `worker-baseline` đang có trên worker.
4. `failure=IllegalStateException`: `FutureTask` ghi nhận ngoại lệ, còn wrapper vẫn chạy `finally`.
5. `callerAfterInline=caller-before-inline`: executor `Runnable::run` làm callback chạy ngay trên caller; khôi phục `previous` bảo vệ request context dù callback gán giá trị khác.
6. `workerAfterAll=worker-baseline`: sau A, B, task trống và task lỗi, worker vẫn có đúng context trước khi các wrapper bắt đầu. Không rò A/B vào lần sử dụng tiếp theo.

**Giới hạn:** demo cố ý đặt một `ThreadLocal` trong worker để kiểm chứng cơ chế. Trong production, nên để worker sau mỗi task ở trạng thái phù hợp, thường là **trống**. Việc lưu `worker-baseline` trong pool ở đây không phải khuyến nghị thiết kế ứng dụng thật.

## 7. `TaskDecorator` trong Spring: capture ở `decorate`, restore trong `run`

Spring cung cấp `org.springframework.core.task.TaskDecorator` để bọc callback trước khi executor chạy task. Cách viết tương tự wrapper JDK:

```java
import org.springframework.core.task.TaskDecorator;

public final class RequestIdTaskDecorator implements TaskDecorator {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    @Override
    public Runnable decorate(Runnable callback) {
        String captured = REQUEST_ID.get(); // Thread GỬI.
        return () -> {
            String previous = REQUEST_ID.get(); // Thread CHẠY.
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                callback.run();
            } finally {
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    }
}
```

Đây là **một class Java đầy đủ về cấu trúc**, nhưng ứng dụng muốn sử dụng cùng `REQUEST_ID` phải có API để set/get tại thread gửi; ví dụ đơn giản này giấu trường `private` nhằm tập trung vào thuật toán. Phần tiếp theo dùng MDC, là API có sẵn cho ứng dụng Spring Boot.

Kết nối với một executor Spring:

```java
@Bean("businessExecutor")
public ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("business-");
    executor.setTaskDecorator(new RequestIdTaskDecorator());
    return executor;
}
```

Đây là **đoạn method cấu hình minh họa**, cần import `@Bean`, `ThreadPoolTaskExecutor` và đặt trong class cấu hình. Không gọi `initialize()` thủ công nếu `ThreadPoolTaskExecutor` thực sự được đăng ký thành Spring bean; Spring quản lý lifecycle thông thường.

**Hai nhầm lẫn cần tránh:**

- `decorate()` chạy ở **ranh giới giao task**; giá trị lấy trong `decorate` mới là snapshot từ thread gửi. Nếu `decorate` chỉ trả một lambda và lambda mới gọi `ThreadLocal.get()` để “capture”, bạn đã quá muộn.
- `TaskDecorator` có thể bọc **execution callback nội bộ** như `FutureTask`, không nhất thiết là `Runnable`/`Callable` ban đầu. Với `submit`, exception có thể được `FutureTask` giữ lại thay vì thoát ra khỏi `callback.run()`. Vì vậy `try-finally` chắc chắn có ích để cleanup, nhưng `catch` trong decorator **không** phải cơ chế bắt mọi lỗi business. Phải quan sát `Future.get`, `CompletableFuture.whenComplete` hoặc error handler thích hợp.

## 8. Copy và phục hồi toàn bộ MDC thay vì chỉ một key

Trong ứng dụng dùng SLF4J/Logback, MDC giúp gắn các cặp `traceId`, `requestId`, `tenant` với log của thread. Khi truyền MDC sang executor, có thể copy toàn bộ map tại thời điểm gửi và **khôi phục toàn bộ map trước đó của worker**.

Một `TaskDecorator` đúng:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcSnapshotTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable callback) {
        // T0: snapshot ngay tại thread gửi.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // T1: lưu map hiện tại của thread sẽ chạy callback.
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                // T2: cài snapshot, kể cả khi submitter không có MDC.
                restore(captured);
                callback.run();
            } finally {
                // T3: phục hồi đúng trạng thái trước callback.
                restore(previous);
            }
        };
    }

    private static void restore(Map<String, String> map) {
        if (map == null || map.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(map);
        }
    }
}
```

Điểm cần chú ý:

- `MDC.getCopyOfContextMap()` cung cấp bản **copy** của context map khi backend MDC hỗ trợ. Không lưu `MDC` như một singleton mutable map dùng chung giữa thread.
- Khi snapshot là `null` hoặc rỗng, `MDC.clear()` trên worker **trước** khi chạy callback; nếu không, log có thể mang dấu vết task trước.
- `previous` được lấy **sau khi worker bắt đầu**, ngay trước khi cài snapshot, và được khôi phục trong `finally`; cách này cho phép wrapper lồng nhau hoặc chạy trực tiếp cùng thread.
- `MDC.setContextMap` thay thế context map hiện tại theo backend hỗ trợ. Đừng chỉ gọi `MDC.put("traceId", captured)` rồi bỏ nguyên các key `tenant`/`user` còn sót ở worker.
- Không log hoặc propagate tự động các giá trị nhạy cảm như access token, mật khẩu, session cookie. Chỉ đưa vào MDC những trường được chính sách bảo mật cho phép.
- Nếu ứng dụng dùng một logging backend không có MDC đúng nghĩa, hãy kiểm tra khả năng hỗ trợ thực tế. Ví dụ Spring Boot bên dưới dùng Logback qua starter để có MDC hoạt động.

### Vì sao khôi phục **map trước** chứ không `MDC.clear()` cuối cùng?

Giả sử task A đang chạy với map `{traceId=A, spanId=1}`, rồi gọi một callback B trực tiếp trên **cùng thread** với `{traceId=B, spanId=2}`. Nếu B kết thúc bằng `MDC.clear()`, A mất toàn bộ thông tin. Nếu B lưu `previous={traceId=A,spanId=1}` rồi `MDC.setContextMap(previous)` trong `finally`, A tiếp tục với map vốn có.

Điều này đặc biệt quan trọng khi executor dùng `CallerRunsPolicy`, test dùng `Runnable::run`, hoặc thư viện có callback lồng nhau chạy trên completion thread.

## 9. Ví dụ Spring Boot chạy được: MDC qua `@Async` với thread pool tái sử dụng

Ví dụ **Java 17+**, **Spring Boot 3.5.7** (Spring Framework 6.2.x), Maven. Chương trình không mở HTTP server; nó mô phỏng ba request khác nhau trên main thread, gọi một Spring `@Async` service qua proxy, rồi kiểm tra kết quả MDC trên worker:

1. Request A gửi với `traceId=req-A`, sau đó caller đổi sang `req-B`.
2. Request B gửi với `traceId=req-B`.
3. Caller xóa MDC; task thứ ba phải thấy `<none>`, không được thấy A hoặc B.
4. Method `@Async` ném lỗi; caller thấy exceptional Future. Decorator vẫn khôi phục MDC dù lỗi.

### 9.1. Cấu trúc dự án

```text
mdc-async-demo/
├── pom.xml
└── src/main/java/com/example/mdcdemo/
    ├── MdcAsyncApplication.java
    ├── AsyncConfiguration.java
    ├── MdcTaskDecorator.java
    └── ContextService.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mdc-async-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot starter này kéo theo các thành phần AOP, Spring Context và logging backend mặc định đủ cho ví dụ `MDC`. Không cần cấu hình `@WebMvcTest` hoặc servlet container để thực hành `@Async`.

### 9.3. `src/main/java/com/example/mdcdemo/MdcTaskDecorator.java`

```java
package com.example.mdcdemo;

import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable callback) {
        final Map<String, String> snapshot = MDC.getCopyOfContextMap();

        return () -> {
            final Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                restore(snapshot);
                callback.run();
            } finally {
                restore(previous);
            }
        };
    }

    private static void restore(Map<String, String> context) {
        if (context == null || context.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
```

### 9.4. `src/main/java/com/example/mdcdemo/AsyncConfiguration.java`

```java
package com.example.mdcdemo;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("context-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }
}
```

Một worker duy nhất được dùng để dễ chứng minh **tái sử dụng thread**. Trong production, phải sizing core/max/queue theo tải thực và deadline; không lấy giá trị `1/1/8` của ví dụ làm mặc định.

### 9.5. `src/main/java/com/example/mdcdemo/ContextService.java`

```java
package com.example.mdcdemo;

import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ContextService {

    @Async("contextExecutor")
    public CompletableFuture<String> readTrace() {
        String traceId = MDC.get("traceId");
        return CompletableFuture.completedFuture(
                traceId == null ? "<none>" : traceId);
    }

    @Async("contextExecutor")
    public CompletableFuture<String> fail() {
        throw new IllegalStateException("demo failure");
    }
}
```

`readTrace()` thực thi trên worker do Spring proxy chọn. Trong body, `CompletableFuture.completedFuture(...)` **không** tạo task bất đồng bộ thứ hai. Với Spring, Future từ proxy cho caller có thể khác object Future tạm do method đích tạo. `fail()` ném ngoại lệ trong worker, Future phía caller hoàn thành ngoại lệ; error handler dành cho `@Async void` không phải nơi xử lý lỗi này.

### 9.6. `src/main/java/com/example/mdcdemo/MdcAsyncApplication.java`

```java
package com.example.mdcdemo;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.slf4j.MDC;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class MdcAsyncApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app = new SpringApplication(MdcAsyncApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            ContextService service = context.getBean(ContextService.class);

            MDC.put("traceId", "req-A");
            var first = service.readTrace();

            // Sau submit A, caller đổi MDC; worker vẫn dùng snapshot A.
            MDC.put("traceId", "req-B");
            System.out.println("first=" +
                    first.get(5, TimeUnit.SECONDS));
            System.out.println("second=" +
                    service.readTrace().get(5, TimeUnit.SECONDS));

            MDC.clear();
            System.out.println("empty=" +
                    service.readTrace().get(5, TimeUnit.SECONDS));

            try {
                service.fail().get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("futureError=" +
                        ex.getCause().getClass().getSimpleName());
            }
        } finally {
            MDC.clear();
        }
    }
}
```

Tại thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Bốn dòng do `System.out` chủ động in khi hoàn tất bình thường:**

```text
first=req-A
second=req-B
empty=<none>
futureError=IllegalStateException
```

Build tool hoặc môi trường có thể in thêm thông tin của chúng. Ví dụ tắt banner/root logging để tập trung vào output, nhưng không phụ thuộc tên thread để quyết định logic nghiệp vụ.

Giải thích cơ chế:

- `first=req-A`: `TaskDecorator.decorate()` chụp MDC trước khi Spring đặt task vào queue, do đó caller đổi thành `req-B` không làm thay đổi snapshot của A.
- `second=req-B`: task thứ hai được submit sau khi caller đặt B, do đó worker nhận B dù cùng một thread đã xử lý A.
- `empty=<none>`: khi submitter không có MDC, decorator **xóa tạm MDC trên worker** thay vì để lại trace từ task trước.
- `futureError=IllegalStateException`: task thất bại nhưng Future phản ánh lỗi. Decorator chạy `finally` để phục hồi MDC của worker, kể cả khi callback thực thi không phát exception ra ngoài do wrapper Future.

Không thể suy ra “đã chứng minh durable job” từ ví dụ: tất cả task vẫn nằm trong bộ nhớ JVM. Muốn job tiếp tục sau restart, cần DB/queue/broker và thiết kế recovery riêng.

## 10. `ContextPropagatingTaskDecorator` của Spring 6.1+: khi nào dùng thay wrapper tự viết?

Spring Framework 6.1+ có `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. Nó tích hợp cơ chế **Micrometer Context Propagation** để chụp/cài lại một số context được đăng ký, đặc biệt hữu ích cho logging/observation context.

Ví dụ định hướng:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

Đây là **đoạn minh họa**, còn cần cấu hình pool và lifecycle. Trong Spring Boot production, thường đăng ký executor thành bean; phụ thuộc Micrometer/context-propagation và các `ThreadLocalAccessor`/context accessor cần được cấu hình phù hợp với context bạn thực sự muốn truyền.

**Không hiểu nhầm** rằng thêm một `ContextPropagatingTaskDecorator` sẽ tự copy **mọi** `ThreadLocal` tùy biến hoặc mọi đối tượng trong request. Chỉ các context có cơ chế/accessor phù hợp mới được chụp và khôi phục. Cần kiểm thử thực tế với trace/MDC của stack hiện dùng; tùy backend và tích hợp, có thể cần dependency hoặc configuration bổ sung.

Một decorator tự viết như `MdcTaskDecorator` có thể hợp lý cho một nhu cầu **cụ thể, đơn giản** và được kiểm thử rõ. Với stack observability phong phú, ưu tiên tích hợp chính thức có context snapshot/accessors hơn là tự nhân bản mỗi loại context bằng code rời rạc.

Lưu ý hiệu năng: capture/restore context có chi phí phân bổ object/copy map. Đặc biệt với hàng triệu task cực nhỏ, hãy đo overhead và quyết định có cần truyền đầy đủ hay chỉ một vài trường tối thiểu.

## 11. Spring Security: không sao chép `SecurityContext` như một Map bình thường

`SecurityContextHolder` theo cấu hình phổ biến dựa trên `ThreadLocal`. Một task `@Async` không tự nhiên có cùng authentication như request thread, và việc mất context có thể làm downstream authorization hoặc audit sai.

Spring Security cung cấp các wrapper chuyên dụng:

- `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- `DelegatingSecurityContextTaskExecutor`.
- `DelegatingSecurityContextAsyncTaskExecutor`.

Các lớp này tổ chức việc gắn/cleanup `SecurityContext` quanh task và giúp tích hợp với Spring `TaskExecutor`. Chúng phù hợp hơn việc tự `SecurityContextHolder.setContext(...)` rồi quên restore/clear.

**Các giới hạn bảo mật:**

1. Chỉ truyền authentication cần thiết sau khi xác thực/ủy quyền; **không** “nâng quyền” cho worker vì caller có một role nào đó.
2. `SecurityContext` và authentication có thể chứa mutable object/reference. Không mặc định rằng truyền context là một **deep immutable snapshot**. Nếu cần snapshot không thay đổi, chuyển thành một DTO claim tối thiểu hoặc dùng cơ chế framework phù hợp.
3. Tác vụ chạy lâu sau request có thể giữ thông tin quyền không còn mới. Đối với tác vụ nhạy cảm, cần xác định điểm kiểm tra quyền ở **thời điểm thực thi** và chính sách hết hạn/quyền bị thu hồi.
4. Không lưu access token, session secret hoặc thông tin cá nhân nhạy cảm vào MDC/log chỉ để tiện propagation.
5. Với kết nối hệ thống khác, truyền đúng identity/authorization theo hợp đồng; sao chép `ThreadLocal` không thay thế xác thực hoặc ủy quyền ở downstream.

Ví dụ **minh họa** nếu đã có một bean `AsyncTaskExecutor delegate`:

```java
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

var secured =
        new DelegatingSecurityContextAsyncTaskExecutor(delegate);
```

Đoạn này cần dependency Spring Security và `delegate` đúng kiểu trong context; nó không phải chương trình độc lập. Nên làm rõ wrapper nào đang chịu trách nhiệm snapshot/cleanup, tránh kết hợp nhiều decorator tự viết dễ ghi đè context lẫn nhau.

## 12. Những gì **không** nên propagate: transaction và request resource

### Transaction không phải một map cần copy

Spring transaction thường được liên kết với thread và tài nguyên thực (JDBC connection, transaction manager, entity manager). `@Transactional` đang mở ở thread nhận request **không tự lan** sang worker chỉ vì ta copy trace ID. Cố gắng chuyển `TransactionSynchronizationManager` hoặc cùng một JDBC connection/EntityManager sang thread khác có thể phá tính đúng đắn, lifecycle và an toàn thread.

**Cách đúng:** truyền dữ liệu/ID cần thiết, để worker có **transaction boundary riêng** khi cần thao tác DB. Nếu worker phải chạy sau khi transaction caller commit, thiết kế thời điểm enqueue phù hợp, ví dụ after-commit publication hoặc transactional outbox; không giả lập transaction bằng copy ThreadLocal.

### `RequestContextHolder` và Servlet request

`RequestAttributes` hoặc `HttpServletRequest` là dữ liệu gắn với vòng đời request và container. Một task nền có thể chạy **sau khi response kết thúc**, khi request object đã hết hiệu lực hoặc bị giải phóng/tái sử dụng. Không mang cả request scope sang thread pool và giả định dùng được mãi.

Thay vào đó:

- Chụp các **giá trị nguyên thủy hoặc DTO bất biến** cần thiết khi request còn hợp lệ.
- Xác thực/ủy quyền ngay khi nhận yêu cầu; thiết kế lại kiểm tra quyền khi worker thực thi nếu cần.
- Không giữ session/resource/stream còn phụ thuộc HTTP response vào job dài.
- Có TTL và cơ chế dọn context nếu cần kết nối tới một hệ thống durable job.

### `InheritableThreadLocal` không giải quyết bài toán thread pool

`InheritableThreadLocal` giúp child thread mới có thể thừa hưởng giá trị lúc tạo thread, **không** cung cấp snapshot riêng cho mỗi task trên một worker **đã được tạo và tái sử dụng**. Thread pool tái sử dụng worker có thể giữ giá trị từ lúc worker được khởi tạo, dẫn đến context cũ/sai. Không dùng nó như cách thay thế cơ chế capture/restore per-task.

## 13. Nhiều lần đổi thread: decorator có được áp dụng ở mọi stage không?

Một pipeline gồm `@Async` và `CompletableFuture` có thể đi qua nhiều executor:

```text
HTTP thread (MDC A)
      |
      | @Async("contextExecutor")
      v
Spring contextExecutor worker (MDC A)
      |
      | thenApplyAsync(...) KHÔNG truyền executor
      v
ForkJoinPool.commonPool worker (MDC ???)
```

`TaskDecorator` gắn với **một `ThreadPoolTaskExecutor` cụ thể** chỉ bọc những task được **gửi qua chính executor đó**. Nếu một continuation dùng `thenApplyAsync` không truyền executor, JDK thường dùng common pool; decorator của Spring executor **không tự chạy** trên common pool.

Để chủ động duy trì context ở ranh giới cụ thể:

```java
CompletableFuture<Dto> dtoFuture =
        source.thenApplyAsync(this::mapToDto, contextExecutor);
```

Đoạn minh họa yêu cầu `source`, `mapToDto`, `contextExecutor` có tồn tại. Nếu `contextExecutor` được cấu hình với `MdcTaskDecorator`, việc submit continuation qua nó sẽ capture context **của thread thực sự lên lịch callback** tại thời điểm submit. Nhưng **không** mặc định rằng thread lên lịch callback luôn là HTTP thread ban đầu. Nếu dependency source hoàn tất từ một thread không có MDC, snapshot có thể null. Vì vậy khi cần logical request context đi xuyên **toàn bộ graph**, hãy xét cơ chế `ContextSnapshot`/propagation được framework hỗ trợ và thiết kế điểm tạo từng stage cho đúng.

Các phương thức không có hậu tố `Async` như `thenApply` hoặc `whenComplete` có thể chạy trên thread hoàn thành source hoặc thread đăng ký callback; không cam kết chạy trên worker nào. Đừng dùng MDC như nguồn dữ liệu nghiệp vụ bắt buộc nếu stage có thể được thực thi từ nhiều thread khác nhau; truyền tham số tường minh sẽ chắc chắn hơn.

### Nên ưu tiên truyền dữ liệu nghiệp vụ qua tham số

```java
record WorkContext(String requestId, String tenantId) {}

CompletableFuture<Result> process(WorkContext context, Input input) {
    return service.computeAsync(context, input);
}
```

Đây là **đoạn minh họa**, cần định nghĩa `Result`, `Input` và `service`. Một `record` bất biến với String phù hợp để truyền rõ logical context qua nhiều stage. ThreadLocal/MDC chủ yếu phục vụ tích hợp logging/observability và một số framework API; không thay thế dữ liệu nghiệp vụ được truyền tường minh.

## 14. Ngoại lệ và `FutureTask`: tại sao `try-finally` vẫn đúng dù `catch` không thấy lỗi?

Với executor `submit(Callable<T>)`, task thực tế mà `TaskDecorator` thấy có thể là `FutureTask`. Khi `Callable` ném exception, `FutureTask.run()` thường **bắt và giữ** exception để `Future.get()` phát `ExecutionException`. Wrapper kiểu:

```java
return () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        restore(captured);
        callback.run();
    } catch (Exception ex) {
        logFailure(ex); // Không bảo đảm bắt được lỗi của Callable.
    } finally {
        restore(previous);
    }
};
```

Đây chỉ là đoạn **minh họa**, các biến `captured`, `callback`, `logFailure` và `restore` thuộc ứng dụng. Nếu callback là `FutureTask`, lỗi của `Callable` có thể không thoát khỏi `callback.run()` và `catch` không được kích hoạt. Tuy nhiên `finally` vẫn chạy **khi callback.run() trả về bình thường**, nên restore **vẫn hoạt động**.

Với `CompletableFuture`, lỗi nghiệp vụ thường được biểu diễn bằng exceptional completion. Bên gọi cần:

```java
future.whenComplete((value, failure) -> {
    if (failure != null) {
        metrics.recordFailure(failure);
    }
});
```

Đây là đoạn minh họa có `future` và `metrics` do ứng dụng định nghĩa. Với phương thức `@Async void`, dùng `AsyncUncaughtExceptionHandler` hoặc cơ chế quan sát của ứng dụng. Trách nhiệm **phục hồi context** và **phát hiện lỗi nghiệp vụ** là hai việc khác nhau; đừng để logic cleanup phụ thuộc vào `catch`.

Nếu lỗi xảy ra **trước khi delegate task được nhận** (executor từ chối hoặc shutdown), wrapper chưa chạy thì cũng chưa cài context lên worker; code caller phải xử lý rejection (`TaskRejectedException`/`RejectedExecutionException`) theo hợp đồng. Không hứa đã nhận job khi executor không nhận.

## 15. Nhiều decorator, thứ tự và ownership

Trong một ứng dụng thực tế, một task có thể cần truyền MDC, trace/observation và SecurityContext. Hướng tốt thường là:

1. **Xác định ngữ cảnh thực sự cần** cho mỗi loại task; không copy mọi thứ một cách mù quáng.
2. **Ưu tiên wrapper/TaskDecorator có sẵn của framework** (Micrometer/Spring Security) cho các loại context đã có contract.
3. Nếu nhiều decorator, dùng `CompositeTaskDecorator` hoặc xây một decorator kết hợp có thứ tự rõ; kiểm tra việc chụp/khôi phục khi có nested wrappers.
4. Chỉ một tầng chịu trách nhiệm reset từng loại context, tránh hai decorator cùng ghi đè cùng map mà không biết thứ tự.
5. Với JDK `Executor` tự viết, chọn một adapter/wrapper ở **ranh giới executor** thay vì copy code `set/clear` rải rác trong từng business method.
6. Cần quan sát `TaskRejectedException`, timeout và cancellation ở ranh giới gửi việc; decorator không phải durable queue hay cơ chế retry.

Đặc biệt: nếu bạn dùng `CallerRunsPolicy` hoặc một direct executor trong test, wrapper có thể chạy **ngay trên thread submitter**. Vì vậy `restore previous` trong `finally` bắt buộc phải đúng trong cả mô hình worker độc lập lẫn cùng thread.

## 16. Cách kiểm thử đúng mà không cần `sleep`

Để test context propagation, **đừng** dựa vào việc các worker vô tình hoàn tất theo một thứ tự nào đó. Dùng `CountDownLatch` và `Future.get(timeout)` để chủ động điều khiển:

| Bài kiểm tra | Thiết lập | Điều kiện đúng |
| --- | --- | --- |
| Capture đúng lúc | Giữ worker bằng latch, submit snapshot A, đổi caller sang B, thả worker | Task vẫn thấy A |
| Thread reuse | Pool 1 worker; task A xong rồi task B | B chỉ thấy snapshot B |
| Null snapshot | Caller không có context, worker đã có baseline | Task thấy null, không thấy baseline |
| Restoration | Chụp baseline của worker trước task, đọc lại bằng raw executor sau task | Baseline được giữ nguyên |
| Task thất bại | Task ném exception qua FutureTask | Caller thấy lỗi, worker vẫn được restore |
| Nested / inline | Dùng `Runnable::run`, callback đổi ThreadLocal | Caller vẫn giữ giá trị trước callback |
| CallerRuns | Pool bị đầy, policy chạy callback trên caller | Caller context được khôi phục sau callback |
| Nhiều key MDC | A có `{traceId,tenant}`, B thiếu `tenant` | B không mang `tenant` của A |
| Cấu trúc mutable | Thread gửi thay map sau submit | Snapshot không bị đổi ngoài ý muốn |
| Async graph | `@Async` rồi `thenApplyAsync` qua executor khác | Mọi boundary cần thiết đều có propagation hoặc tham số rõ |

Với JUnit 5, có thể kiểm thử deterministic cho wrapper:

```java
@Test
void inlineExecutionRestoresCaller() {
    ThreadLocal<String> current = new ThreadLocal<>();
    current.set("caller");

    Executor wrapped = task -> {
        String snapshot = current.get();
        Runnable delegated = () -> {
            String previous = current.get();
            try {
                current.set(snapshot);
                task.run();
            } finally {
                if (previous == null) {
                    current.remove();
                } else {
                    current.set(previous);
                }
            }
        };
        delegated.run(); // Direct execution.
    };

    wrapped.execute(() -> current.set("inner"));
    assertEquals("caller", current.get());
    current.remove();
}
```

Đây là **đoạn test minh họa**, cần import `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.assertEquals` và `java.util.concurrent.Executor`, đồng thời dependency JUnit 5. Với một `ThreadLocal` thực dùng chung trong ứng dụng, hãy viết fixture/extension cleanup `afterEach` để test không rò context qua các test khác.

Khi kiểm thử Spring `@Async`, **phải gọi qua Spring proxy từ bean/test context khác**. Gọi `this.asyncMethod()` từ cùng bean bỏ qua async advice theo proxy mode mặc định, khiến test “pass” trên cùng thread nhưng không kiểm chứng propagation thực.

## 17. Các anti-pattern cần nhận diện

| Anti-pattern | Sai ở đâu? | Cách sửa |
| --- | --- | --- |
| Chụp `ThreadLocal.get()` **trong `run()`** | Đọc giá trị của worker, không phải thread gửi | Chụp trước `executor.execute`/trong `decorate` |
| `ThreadLocal.set(snapshot); task.run();` không `finally` | Task lỗi sẽ để sót dữ liệu trên worker | `try-finally` luôn khôi phục previous |
| Cuối task luôn `remove()` | Phá context của wrapper lồng nhau / caller-run | Lưu `previous` trước, restore đúng giá trị cũ |
| Chỉ `put` key mới, không xóa key cũ trong MDC | Key từ request trước tiếp tục tồn tại | Restore **toàn bộ map** hoặc clear khi snapshot rỗng |
| Dùng tham chiếu `HashMap` mutable làm snapshot | Thread gửi sửa map, worker thấy dữ liệu đổi | Copy phòng vệ/DTO bất biến |
| Propagate mọi ThreadLocal tự động | Mang token/session/transaction không nên chuyển | Allowlist context, kiểm tra bảo mật/lifecycle |
| Dùng `InheritableThreadLocal` cho pooled workers | Snapshot ở lúc **tạo thread**, không phải mỗi task | Decorator per-task hoặc tham số tường minh |
| Tưởng `@Async` tự truyền MDC | Worker khác thread, MDC có thể null/sai | Gắn TaskDecorator hoặc tích hợp propagation |
| Dùng `supplyAsync()` không executor sau decorated `@Async` | Callback vào common pool, mất context đã được truyền | Chọn executor tường minh hoặc context snapshot cho stage |
| Gọi `MDC.clear()` trong business method mà không restore | Phá context của caller/nested stage | Wrapper capture/restore trong `finally` |
| Copy `TransactionSynchronizationManager` sang worker | Sai ranh giới transaction và resource | Worker tự mở transaction, truyền dữ liệu cần thiết |
| Chụp `HttpServletRequest` để chạy job lâu | Resource hết vòng đời request | Snapshot DTO bất biến/ID |
| Dựa vào catch của `TaskDecorator` để bắt mọi lỗi Future | `FutureTask` giữ exception bên trong | Quan sát Future và dùng error handler |
| Dùng thread pool không giới hạn và copy context lớn | Tốn memory, backlog và độ trễ | Bounded queue, tối giản snapshot, metrics |
| Truyền cùng một mutable SecurityContext sang nhiều task | Race/quyền không nhất quán | Spring Security wrapper, identity snapshot tối thiểu |
| Quên cleanup trong integration test | Test kế tiếp thừa hưởng MDC/request ID | Teardown/fixture với `finally` hoặc `afterEach` |

## 18. Checklist production và vận hành

Trước khi deploy một cơ chế propagation:

- **Phạm vi:** context nào được phép truyền? `traceId`, `requestId`, locale, tenant, authentication? Cái nào phải đi theo tham số rõ ràng?
- **Thời điểm:** snapshot được tạo ở **submit thread**, không phải worker?
- **Sao chép:** snapshot có độc lập với dữ liệu mutable sau submit không?
- **Cài:** worker có được xóa các key cũ khi snapshot trống không?
- **Phục hồi:** có lưu `previous` **trên thread thực thi**, và `finally` chạy cho cả success/error/cancellation/inline?
- **Nested execution:** chạy trực tiếp hoặc `CallerRunsPolicy` có giữ context của code bao ngoài không?
- **Mọi boundary:** `@Async`, `Executor.submit`, `CompletableFuture.supplyAsync/thenApplyAsync`, scheduled tasks, event listeners có đi qua decorator đúng nơi không?
- **Bảo mật:** tránh copy token, request object, transaction và dữ liệu cá nhân không cần thiết; tái xác thực khi cần.
- **Tài nguyên:** snapshot có nhỏ và TTL hợp lý? Executor có queue giới hạn? Rủi ro memory nếu task backlog lâu?
- **Lỗi:** `Future` completion/error được quan sát riêng, không dựa vào `catch` của decorator; rejection được xử lý tại submit.
- **Khả năng quan sát:** log trace ID ở submit và worker, tỷ lệ task không có trace mong đợi, ngữ cảnh lẫn tenant, queue wait, executor active/queue/rejection.
- **Kiểm thử:** thread reuse, submitter đổi context trước worker chạy, null snapshot, exception, nested, async graph, shutdown và overload.

Một ứng dụng có tracing chuẩn nên ưu tiên cơ chế propagation có sẵn, nhưng vẫn phải hiểu thuật toán capture/install/restore. Khi có lỗi “trace của người A xuất hiện trong tác vụ người B”, nguyên nhân thường là **không clear snapshot rỗng, thiếu restore ở finally, hoặc bọc sai ranh giới executor**.

## 19. Câu hỏi tự kiểm tra

**1.** Vì sao phải lấy `MDC.getCopyOfContextMap()` ở `decorate()` chứ không trong `run()`?  
**Đáp:** `decorate()` diễn ra khi giao task từ thread gửi. `run()` chạy trên worker, có thể nhiều giây sau và có MDC khác. Chụp trong `run()` mất quan hệ với request ban đầu.

**2.** Tại sao trước khi cài snapshot phải lưu `previous` của worker?  
**Đáp:** Để sau task trả lại đúng context mà thread thực thi đã có, kể cả nested wrapper hoặc executor chạy trên caller; chỉ clear có thể phá context của code bao ngoài.

**3.** Caller không có trace, worker còn `traceId=A` từ task trước. Worker nên thấy gì trong task mới?  
**Đáp:** Không có trace (`null`/`<none>`); snapshot rỗng phải **xóa tạm** MDC cũ. Cuối callback khôi phục `previous` theo contract wrapper; ở ứng dụng tốt worker không nên lưu trace rác ngoài mọi task.

**4.** Task ném exception trong worker. `finally` có chạy không?  
**Đáp:** Có khi luồng điều khiển rời `try` bình thường bằng exception, với điều kiện JVM không bị chấm dứt bất thường. Vì vậy restore đặt trong `finally`, không chỉ ở nhánh thành công.

**5.** `FutureTask` giữ exception của `Callable`. `catch` trong decorator luôn bắt lỗi đó chứ?  
**Đáp:** Không. `FutureTask.run()` có thể không ném lỗi ra ngoài; caller phải quan sát `Future.get()`. `finally` vẫn được thực hiện quanh `run()`.

**6.** Một `ThreadLocal<Map>` đang trỏ tới `HashMap`, giữ tham chiếu này trong snapshot có đủ không?  
**Đáp:** Không nếu map được sửa sau submit. Cần copy phòng vệ (và cân nhắc deep copy/immutable values).

**7.** Một `@Async` method gọi `CompletableFuture.supplyAsync()` không truyền executor. Decorator của Spring pool có tự bọc supplier này không?  
**Đáp:** Không. Supplier có thể chạy trên JDK common pool, nằm ngoài decorator của bean Spring. Phải cấu hình từng boundary hoặc truyền context bằng cơ chế phù hợp.

**8.** Có nên copy `@Transactional` context từ HTTP thread sang worker?  
**Đáp:** Không. Transaction và resource có lifecycle/thread binding; worker nên có transaction riêng và truyền dữ liệu/ID rõ ràng.

**9.** `CallerRunsPolicy` khiến task chạy ngay trên thread gửi. Tại sao restore vẫn cần?  
**Đáp:** Task có thể thay đổi `ThreadLocal` của **chính HTTP thread**; `finally` phải trả lại context gốc sau callback.

**10.** `ContextPropagatingTaskDecorator` có tự truyền mọi `ThreadLocal` do ứng dụng tạo không?  
**Đáp:** Không. Cần cơ chế/accessor phù hợp cho context muốn truyền; phải kiểm thử theo stack thực, không giả định một decorator tự hiểu mọi giá trị.

## 20. Ghi nhớ và tài liệu chính thức

**Công thức căn bản của context propagation trên executor:**

```text
SUBMITTER: snapshot = captureCurrentContext()  // chụp trước khi queue
WORKER:    previous = captureCurrentContext()  // lưu trạng thái hiện tại
           try {
               install(snapshot)               // kể cả snapshot rỗng
               runOriginalTask()
           } finally {
               restore(previous)               // không rò, không phá ngữ cảnh ngoài
           }
```

Một wrapper đúng phải chịu được **pool reuse, task lỗi, snapshot null, inline execution, nested context** và nhiều ranh giới `CompletableFuture`. Khi cần bọc context chuyên biệt như SecurityContext/observability, dùng integration chính thức của Spring/Spring Security/Micrometer và kiểm thử hiệu quả thực tế.

**Nguồn tham khảo:**

- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): phạm vi dữ liệu theo thread, `get`, `set`, `remove`.
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng gửi task, executor có thể chạy inline.
- [Spring Framework — `TaskDecorator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html): callback wrapper và giới hạn bắt exception với Future.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): cấu hình `ThreadPoolTaskExecutor.setTaskDecorator` và `@Async`.
- [Spring Framework — `ContextPropagatingTaskDecorator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): Micrometer context capture/restore.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): kết hợp task execution và context propagation.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): wrappers bảo vệ `SecurityContext`.
- [SLF4J — MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): `getCopyOfContextMap`, `setContextMap`, `clear`.