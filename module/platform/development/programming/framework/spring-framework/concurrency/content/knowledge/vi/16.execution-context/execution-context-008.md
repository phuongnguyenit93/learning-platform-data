# Không giữ toàn bộ đối tượng request sau khi yêu cầu đã kết thúc

> **Module:** Spring Framework – concurrency  
> **Nhóm kiến thức:** Ngữ cảnh thực thi  
> **Nguyên tắc:** Khi gửi công việc ra `ThreadPoolTaskExecutor`, `@Async`, `CompletableFuture` hoặc một hàng đợi, **không giữ tham chiếu tới toàn bộ `HttpServletRequest`/`ServletRequestAttributes` hoặc đối tượng gắn với vòng đời request** nếu công việc có thể tiếp tục sau khi request kết thúc. Hãy **trích xuất đúng những dữ liệu cần thiết tại ranh giới request**, kiểm tra và chuyển thành **snapshot tối thiểu, bất biến**, không chứa request/response/session/container object.

Bài học tập trung vào Java 17, Spring MVC/Servlet và thực thi bất đồng bộ. Cần phân biệt **controller method kết thúc** với **Servlet async request thật sự hoàn thành**: Spring MVC có thể tiếp tục giữ response mở trong một quy trình async hợp lệ. Điều bị cấm về thiết kế ở đây là *lưu lại/đọc lại toàn bộ request ngoài vòng đời hợp lệ*, chứ không phải phủ nhận Servlet async được tiêu chuẩn hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt thời gian sống của `HttpServletRequest`, `HttpServletResponse`, request-scoped bean, tham chiếu tới `ServletRequestAttributes` và context được đặt trong `ThreadLocal`.
2. Nhìn ra các đường giữ tham chiếu **trực tiếp hoặc gián tiếp** qua lambda, anonymous class, `CompletableFuture` callback, `@Async` argument, queue, scheduled task, cache, static map và `TaskDecorator`.
3. Giải thích nguy cơ: đọc dữ liệu đã hết hiệu lực, race/cross-request contamination, giữ object graph/payload quá lâu, rò rỉ dữ liệu, lỗi khi context không còn active.
4. Thiết kế record/DTO bất biến nhỏ gọn với các trường thực sự cần: `actorId`, `tenantId`, `correlationId`, `jobId`, tham số nghiệp vụ đã kiểm tra.
5. Dùng `@Async`/`ThreadPoolTaskExecutor`/`CompletableFuture` trong Spring mà task **chỉ nhận snapshot**, không truy xuất lại raw request khi worker chạy.
6. Phân biệt việc chuyển vài giá trị logging/tracing với việc **truyền cả request attributes**, security context hoặc session qua thread.
7. Xử lý file upload, body stream, cancellation, timeout, retry, shutdown và công việc chạy lâu sau khi response đóng.
8. Viết ví dụ Java 17 và Spring Context có output xác định; kiểm thử bằng latch và assertion có thể tái lập, không phụ thuộc vào garbage collector.

## 2. Request thuộc về ai và sống bao lâu?

Trong Servlet stack, container tạo hoặc quản lý một `HttpServletRequest` tương ứng với quá trình xử lý HTTP. Object này không phải DTO do ứng dụng sở hữu tự do; nó có thể mang hoặc dẫn tới:

- HTTP headers, parameters, cookies, session-related data.
- Các attribute do filter/interceptor/Servlet/Spring thêm vào.
- Stream/body, multipart metadata và wrapper liên quan.
- References đến `ServletContext`, các container wrappers hoặc tài nguyên tạm.
- Thông tin authentication/locale qua các subsystem liên quan đến request.
- Trạng thái async dispatch và response tương ứng.

**Không phải thuộc tính nào cũng chắc chắn tồn tại trên mọi implementation**. Điều cần nhớ là **một tham chiếu tới `HttpServletRequest` có thể giữ lại nhiều đối tượng ngoài ý muốn**. Nó cũng gắn với một *hợp đồng về thời gian sử dụng*, không chỉ vấn đề RAM.

### 2.1. Servlet request đồng bộ

Với request thông thường, Servlet specification giới hạn hiệu lực của request object vào phạm vi `service()` hoặc filter `doFilter()`. Khi xử lý kết thúc và container thu hồi quyền kiểm soát, không được giả định request vẫn dùng được. Container có thể tái sử dụng/recycle object để giảm chi phí cấp phát. Vì vậy, một lambda chạy nền vài giây sau đó gọi `request.getHeader(...)` là **thiết kế sai**, dù ở môi trường local thỉnh thoảng nó vẫn trả về giá trị.

~~~text
Container nhận HTTP request
       |
       v
Filter -> DispatcherServlet -> Controller
       |
       +-- Đọc/kiểm tra request (trong lifecycle hợp lệ)
       |
       +-- Tạo immutable WorkInput với vài scalar fields
       |
       +-- Enqueue work(WorkInput)
       |
       v
HTTP request kết thúc
       |
       +-- Container có thể cleanup/recycle request
       |
       v
Worker chạy muộn
       |
       +-- Chỉ sử dụng WorkInput (không giữ HttpServletRequest)
~~~

**Không làm:** chuyển chính `HttpServletRequest` vào worker với hy vọng nó sống đến khi worker cần.

### 2.2. Ngoại lệ quan trọng: Servlet async request hợp lệ

Servlet API có mô hình bất đồng bộ: `request.startAsync()` trả về `AsyncContext`. Khi async processing thực sự đã được khởi tạo, request/response có **vòng đời async hợp lệ**: request object vẫn có hiệu lực trong thời gian xử lý async cho đến khi `AsyncContext.complete()` (và những chuyển tiếp/timeout theo hợp đồng container).

Trong Spring MVC, các kiểu trả về như `Callable`, `DeferredResult`, `CompletionStage` hoặc `CompletableFuture` được framework tích hợp với Servlet async processing. Controller có thể **trả về trước**, Servlet thread được giải phóng, nhưng logical HTTP request/response **chưa hoàn tất**.

~~~text
Controller method returns CompletableFuture
              |
              v
Spring MVC bắt đầu Servlet async processing
              |
              +-- Request/response thuộc vòng đời async hiện hành
              +-- Container thread ban đầu có thể rời filter chain
              |
              +-- Future completes -> Async dispatch -> write response
              |
              v
Async request completes / timeout / error
              |
              v
Không sử dụng lại request/response của vòng đời đã hoàn tất
~~~

Do vậy, **không đồng nhất** “method controller return” với “request hoàn tất”. Tuy nhiên, việc Servlet async duy trì hiệu lực **không có nghĩa** mọi API trên `HttpServletRequest` đều thread-safe, hoặc bất kỳ worker nào cũng có thể truy cập tùy ý. Tự nộp một `Runnable` vào executor **không tự động** kéo dài vòng đời Servlet request, nếu framework chưa thực sự thiết lập async lifecycle phù hợp.

**Quy tắc thiết kế vẫn nên giữ:** worker nghiệp vụ sử dụng snapshot tối thiểu. Để framework/container kiểm soát request/response; đừng biến sự hiện diện của `AsyncContext` thành lý do lưu trữ raw request ngoài phạm vi.

### 2.3. Đâu là sự kiện “yêu cầu đã kết thúc”?

Với request thường: sau khi Servlet/filter processing thực sự kết thúc theo lifecycle. Với request async: sau khi async handling hoàn tất, bị timeout, lỗi hoặc được complete theo cơ chế framework/container. **Đừng dự đoán bằng một dòng controller `return` duy nhất**.

Các thông tin như request đã được client đóng kết nối, Spring MVC đã hoàn thành response hay asynchronous task nội bộ đã xong là những tín hiệu khác nhau; một task fire-and-forget có thể chạy lâu hơn cả request. Việc client hủy request cũng không đảm bảo Java task bất kỳ sẽ tự bị hủy.

## 3. Vấn đề trọng tâm: giữ một object graph, không chỉ một biến

Giả sử một lambda giữ biến `request`:

~~~java
executor.execute(() -> {
    String tenantId = request.getHeader("X-Tenant-Id");
    generateReport(tenantId);
});
~~~

Đây là **snippet không độc lập**: `executor`, `request` và `generateReport` thuộc ứng dụng.

Có hai vấn đề:

1. **Thời điểm truy cập:** lambda có thể chạy sau khi response hoàn tất, nên `request.getHeader` nằm ngoài lifecycle thích hợp.
2. **Strong reference:** lambda/task phải giữ `request` để có thể chạy sau. Nếu queue dài hoặc future bị giữ trong một map, `request` có thể tiếp tục **reachable** dù request HTTP đã kết thúc, kèm các wrapper, attributes và các đối tượng mà nó dẫn tới.

Một sơ đồ giữ tham chiếu:

~~~text
Singleton / ThreadPoolExecutor
     |
     +-- workQueue
             |
             +-- Runnable / Callable / FutureTask
                       |
                       +-- lambda captured request
                                 |
                                 +-- HttpServletRequest
                                 +-- attributes / wrappers
                                 +-- session-related references
                                 +-- potentially large payload and buffers
~~~

GC không thể thu hồi object graph khi vẫn còn đường tham chiếu mạnh từ các root. Không phải mọi request được capture đều tạo **memory leak vĩnh viễn**: nếu task nhanh chóng hoàn tất và tham chiếu được giải phóng, retention có thể chỉ tạm thời. Nhưng queue kéo dài, scheduler, static cache, unresolved future hoặc worker bất thường có thể biến **retention tạm thời thành vấn đề nghiêm trọng**.

### 3.1. Vì sao queue capacity liên quan trực tiếp?

Giả sử một task vô tình giữ khoảng **1 MiB** dữ liệu từ object graph của request, và queue giữ 5.000 task như vậy. Riêng phần dữ liệu đó có thể bị giữ khoảng **5.000 MiB (xấp xỉ 4,88 GiB)**, chưa tính overhead của objects, futures và thread pools. Đây chỉ là **ví dụ tính toán minh họa**, kích thước object graph thực tế phải đo bằng heap profiler.

Do đó, ngoài việc chỉ giữ snapshot, cần giới hạn `queueCapacity`, số task đang chờ, deadline và chính sách từ chối. Tạo một DTO có chứa toàn bộ body 10 MiB cũng không giải quyết vấn đề memory chỉ bằng việc đổi tên object.

## 4. Những dạng capture trực tiếp và gián tiếp

### 4.1. Lambda bắt biến request

~~~java
CompletableFuture.runAsync(() -> {
    audit(request.getRequestURI());
}, executor);
~~~

Sai khi task có thể chạy sau lifecycle; `CompletableFuture` không tự làm request sống hợp lệ. **Giải pháp:** lấy giá trị cần thiết trước khi schedule:

~~~java
String path = request.getRequestURI(); // Trong request lifecycle.
CompletableFuture.runAsync(
        () -> audit(path),
        executor);
~~~

Đây là **snippet**; `audit` và `executor` là dependency ứng dụng. Hãy chuẩn hóa/giới hạn dữ liệu path trước khi log; URL có thể chứa thông tin nhạy cảm.

### 4.2. Capturing `this` của controller/handler

~~~java
executor.execute(() -> this.processLater());
~~~

Vấn đề không phải mọi capture `this` đều sai: nếu `this` là singleton stateless service, việc tham chiếu service không kéo raw request. Nhưng nếu controller/handler có **field chứa request hiện tại** hoặc object request-scoped, lambda có thể gián tiếp giữ toàn bộ request. Đặc biệt **không lưu request vào field mutable của singleton controller**, vì các request đồng thời sẽ ghi đè lẫn nhau.

Nên giữ controller stateless và truyền argument snapshot vào service.

### 4.3. Anonymous class và inner class

Một anonymous/inner class có thể giữ tham chiếu tới outer instance dù không nhìn rõ trong code. Nếu outer chứa request, session, file stream hoặc mutable holder, task có thể kéo theo cả chuỗi object. Static nested class hoặc record nhỏ có dependency hiển thị rõ là một lựa chọn dễ audit hơn.

### 4.4. CompletableFuture callback

~~~java
future.whenComplete((result, error) -> {
    request.setAttribute("result", result);
});
~~~

Callback có thể chạy trên một thread khác hoặc sau HTTP request đã kết thúc; `request.setAttribute` không phải kênh trả dữ liệu hợp lệ cho job nền. Future/callback cũng có thể giữ tham chiếu đến `request` cho đến khi pipeline hoàn tất.

Tương tự với `thenApply`, `thenCompose`, `handle`, `exceptionally` và `thenCombine`: xem toàn bộ closure được capture, không chỉ lambda đầu tiên.

### 4.5. Task/scheduler/cache giữ request quá lâu

Không lưu các object này vào `@Scheduled` job, `DelayQueue`, message payload, `ConcurrentHashMap` toàn cục, application event dùng executor bất đồng bộ hoặc state singleton. Nếu tác vụ cần tiếp tục sau restart, lưu **dữ liệu nghiệp vụ đã kiểm tra** vào kho bền vững, không serialize request container.

### 4.6. Capture qua `ServletRequestAttributes`

~~~java
RequestAttributes attrs =
        RequestContextHolder.currentRequestAttributes();

executor.execute(() ->
        useAttributesLater(attrs));
~~~

Đây là **snippet có import Spring web**. Với request Servlet thông dụng, `ServletRequestAttributes` thường giữ tham chiếu tới request/response; vì thế capture nó có thể **gián tiếp** giữ toàn bộ request. Ngoài nguy cơ retention, xử lý các attributes đó sau lifecycle có thể lỗi. Không “đóng gói” request vào một wrapper rồi gọi nó là snapshot.

## 5. Đừng nhầm ThreadLocal context với dữ liệu bền cho công việc nền

Trong Spring MVC, `RequestContextHolder` thường công bố `RequestAttributes` qua `ThreadLocal` gắn với thread xử lý hiện tại. Spring Security và logging frameworks cũng có context lưu theo thread. Một worker từ `ThreadPoolTaskExecutor` là thread khác, được **tái sử dụng** cho nhiều task.

Khi rời request thread:

- `RequestContextHolder.getRequestAttributes()` trên worker có thể là `null`; `currentRequestAttributes()` có thể ném lỗi nếu không có context hợp lệ.
- `@RequestScope` bean gắn với HTTP request, không phải bean có thể tùy ý dùng khi không còn request scope. Scoped proxy không tự gia hạn request lifecycle.
- MDC/locale/SecurityContext thường không tự truyền đúng qua mọi kiểu executor; nếu cần, dùng cơ chế propagation rõ ràng.
- Nếu copy toàn bộ `RequestAttributes` sang worker, bạn có thể giữ raw request lâu hơn hoặc truy cập object ngoài lifecycle.
- Nếu không cleanup `ThreadLocal` trên pooled thread, task kế tiếp có thể nhìn thấy correlation/user/tenant của task trước. Đây là vấn đề bảo mật và tính đúng đắn, không chỉ memory leak.

### 5.1. Vì sao InheritableThreadLocal không phải giải pháp cho thread pool?

`RequestContextFilter.setThreadContextInheritable(true)` hoặc cơ chế inheritance tương tự chỉ phù hợp trong điều kiện rất hẹp: child thread được tạo riêng cho request và **không được tái sử dụng**. Spring Javadoc cảnh báo rõ không nên bật inheritance cho thread pool có thể tạo worker mới theo nhu cầu. Một pooled worker có thể kế thừa context của request ngẫu nhiên tại thời điểm thread được tạo rồi tiếp tục tái sử dụng context đó cho những request khác.

**Không bật kế thừa toàn bộ request context chỉ để @Async “nhìn thấy” HttpServletRequest.**

### 5.2. Propagation ≠ snapshot cho job dài hạn

Context propagation là việc mang một số trạng thái xuyên thread theo **phạm vi thực thi**. Nó hữu ích cho tracing/logging trong một chain có vòng đời xác định. Nhưng không nên hiểu là được phép giữ cả `ServletRequestAttributes` trong một task có thể tồn tại hàng phút/hàng giờ sau response.

Spring có `ContextPropagatingTaskDecorator` dựa trên Micrometer Context Propagation cho một số loại context; nếu registry có accessor dành cho request attributes, việc truyền context đó cần được xem xét kỹ theo lifecycle. Đây **không phải** cơ chế biến raw request thành dữ liệu an toàn sau completion.

## 6. Cách đúng: trích xuất snapshot tối thiểu, bất biến

Định nghĩa các giá trị worker **thực sự cần**, không mang toàn bộ “context để cho chắc”.

Ví dụ Java 17:

~~~java
public record JobInput(
        String jobId,
        String actorId,
        String tenantId,
        String correlationId,
        String documentId) {

    public JobInput {
        java.util.Objects.requireNonNull(jobId);
        java.util.Objects.requireNonNull(actorId);
        java.util.Objects.requireNonNull(tenantId);
        java.util.Objects.requireNonNull(correlationId);
        java.util.Objects.requireNonNull(documentId);
    }
}
~~~

Đây là **tệp/record Java 17** có thể dùng trong ứng dụng; khi khai báo `public record JobInput` ở top-level, phải lưu trong **`JobInput.java`**. Nó không có `main` nên không phải demo chạy độc lập.

Các field đều là `String` bất biến nên record này là một **snapshot bất biến về dữ liệu chứa bên trong**. Record chỉ đảm bảo các reference field là `final`; nếu field chứa `List<MutableItem>`, `byte[]` hoặc một entity mutable, record **không tự deep-copy**.

### 6.1. Chọn đúng trường

| Nhu cầu của worker | Nên truyền | Tránh truyền |
| --- | --- | --- |
| Định danh user/actor | `actorId` ổn định, đã xác thực | Raw `Principal`/`Authentication` object, toàn security session nếu không cần |
| Phân biệt tenant | `tenantId` đã validate/authorize | Header `X-Tenant-Id` nguyên văn khi chưa xác minh |
| Liên kết log/tracing | `correlationId` đã chuẩn hóa, hạn chế độ dài | `HttpServletRequest`, tất cả headers/cookies |
| Xử lý đơn/biểu mẫu | `orderId`, `documentId`, DTO đã validate | Cả `@RequestBody` mutable hoặc raw input stream |
| Gửi file lớn | Storage object key/URI nội bộ có ACL | `MultipartFile`/`ServletInputStream` còn gắn vào request |
| Điều khiển deadline | Deadline/timeout đơn giản và có hợp đồng | Container request/response để worker “tự hỏi thời gian” |
| Phục vụ phân quyền | Actor ID và bằng chứng tối thiểu theo policy | Token, password, bearer Authorization header |

Việc chỉ truyền actor ID không tự động cấp quyền cho job. Nếu tác vụ chạy lâu, xử lý quyền thực sự có thể cần **kiểm tra lại tại thời điểm thực thi** vì quyền của user có thể đã thay đổi. Với workload đặc biệt cần identity delegation, dùng contract bảo mật chính thức thay vì cache raw token vô thời hạn.

### 6.2. Snapshot phải được tạo đúng thời điểm

~~~text
HTTP request thread
    |
    +-- Authenticate/authorize user
    +-- Validate payload, headers, tenant
    +-- Extract stable IDs + small fields
    +-- Construct immutable JobInput
    +-- Send JobInput to bounded executor/queue
    |
    v
Request completes

Worker:
    |
    +-- Only JobInput + injected services
    +-- Perform business work with own transaction
    +-- Report success/failure using jobId
~~~

Không tạo snapshot **bên trong worker** bằng cách chờ rồi đọc lại `HttpServletRequest`; hành động đó đã quá muộn. Nếu cần body, đọc/validate **trong lifecycle hợp lệ** và cân nhắc lưu payload cần thiết vào kho bền nếu nó lớn hoặc xử lý lâu.

### 6.3. Immutable collection và array

~~~java
record BatchInput(String tenantId, java.util.List<String> ids) {
    BatchInput {
        ids = java.util.List.copyOf(ids);
    }
}
~~~

Đây là **record snippet**: `List.copyOf` tạo một collection unmodifiable cho tập các `String` bất biến. Nếu phần tử là object mutable, vẫn phải deep-copy nội dung nếu worker cần trạng thái nhất quán. Với `byte[]` cần clone khi nhận/trả để tránh caller sửa mảng sau khi submit. Với `Map<String, Object>` tùy ý, **không** được xem là snapshot bất biến nếu value chứa entity/request object mutable.

## 7. Java 17 chạy độc lập: mô phỏng lifecycle và sửa lỗi

Ví dụ sau **không triển khai Jakarta Servlet**; nó mô phỏng chính xác vấn đề *dùng dữ liệu của request sau khi request đã bị đóng* bằng một object thử nghiệm. Một `CountDownLatch` bảo đảm cả task xấu và tốt chỉ chạy **sau** lúc request giả lập đã hết hiệu lực, vì thế stdout không phụ thuộc may rủi scheduler hay `Thread.sleep`.

Tạo tệp **`RequestLifetimeDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class RequestLifetimeDemo {

    static final class SimulatedRequest {
        private final String requestId;
        private final String tenantId;
        private boolean active = true;

        SimulatedRequest(String requestId, String tenantId) {
            this.requestId = requestId;
            this.tenantId = tenantId;
        }

        synchronized String read(String key) {
            if (!active) {
                throw new IllegalStateException("request already ended");
            }
            return switch (key) {
                case "requestId" -> requestId;
                case "tenantId" -> tenantId;
                default -> throw new IllegalArgumentException(key);
            };
        }

        synchronized void end() {
            active = false;
        }
    }

    record Snapshot(String requestId, String tenantId) { }

    static void await(CountDownLatch gate) {
        try {
            if (!gate.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("gate timeout");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", e);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        CountDownLatch gate = new CountDownLatch(1);
        SimulatedRequest request =
                new SimulatedRequest("req-17", "tenant-A");

        // Snapshot được tạo khi request còn active.
        Snapshot input = new Snapshot(
                request.read("requestId"),
                request.read("tenantId"));

        try {
            // SAI: lambda giữ chính request; sẽ đọc quá muộn.
            CompletableFuture<String> bad =
                    CompletableFuture.supplyAsync(() -> {
                        await(gate);
                        return request.read("requestId");
                    }, worker);

            // ĐÚNG: lambda chỉ giữ hai chuỗi trong snapshot.
            CompletableFuture<String> good =
                    CompletableFuture.supplyAsync(() -> {
                        await(gate);
                        return input.requestId()
                                + "/" + input.tenantId();
                    }, worker);

            request.end();   // Mô phỏng HTTP request hoàn tất.
            gate.countDown();

            try {
                bad.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                Throwable root = e.getCause();
                System.out.println("bad = "
                        + root.getClass().getSimpleName()
                        + ": " + root.getMessage());
            }

            System.out.println("good = "
                    + good.get(5, TimeUnit.SECONDS));
        } finally {
            gate.countDown();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac RequestLifetimeDemo.java
java RequestLifetimeDemo
~~~

**Stdout chính xác khi chạy thành công:**

~~~text
bad = IllegalStateException: request already ended
good = req-17/tenant-A
~~~

### Vì sao ví dụ có output xác định?

1. `request.read(...)` được gọi để tạo `Snapshot` trước `request.end()`, nên lấy được hai scalar fields ổn định.
2. Task “bad” được enqueue trước nhưng chờ `gate`; `main` gọi `request.end()` **trước** `gate.countDown()`.
3. Vì thế khi bad task đọc request, object giả lập luôn đã ở trạng thái ended; `CompletableFuture` lưu `IllegalStateException`, `get(...)` trả `ExecutionException` với cause gốc.
4. Task “good” không truy cập `request`, chỉ đọc record bất biến; nó trả `req-17/tenant-A` sau khi gate mở.
5. `get(timeout)` và `awaitTermination` làm rõ thời điểm chờ; chương trình không dùng `Thread.sleep` hoặc đợi GC.

**Giới hạn mô phỏng:** Servlet container thật có nhiều trạng thái và có `AsyncContext`; việc một container object đọc sau lifecycle có ném `IllegalStateException` hay không **không có bảo đảm giống fake này**. Demo cố chứng minh **mẫu dependency/lifecycle an toàn**, không mô phỏng byte-for-byte cách một container thật recycle request.

## 8. So sánh trực tiếp: từ code dễ lỗi sang code an toàn

### 8.1. Bad: gửi HttpServletRequest vào async service

~~~java
@Service
class BadReportService {
    @Async("reportExecutor")
    public void generate(HttpServletRequest request) {
        // Request có thể đã hết vòng đời vào lúc worker chạy.
        String tenant = request.getHeader("X-Tenant-Id");
        createReport(tenant);
    }
}
~~~

Đây là **snippet minh họa lỗi**, yêu cầu import Spring `@Service`, `@Async`, `HttpServletRequest` và service `createReport`. Cả việc truyền request qua proxy lẫn giữ closure sau đó đều có thể kéo request sang một vòng đời không phù hợp.

### 8.2. Good: tạo snapshot trong controller

~~~java
public record ReportInput(
        String reportId,
        String actorId,
        String tenantId,
        String correlationId) { }

@RestController
class ReportController {
    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @PostMapping("/reports/{reportId}")
    public CompletableFuture<String> start(
            @PathVariable String reportId,
            @RequestHeader("X-Correlation-Id") String correlationId,
            Principal principal) {

        // Ví dụ: tenantId lấy từ identity đã xác thực,
        // KHÔNG tin header tenant tuỳ ý của client.
        String actorId = principal.getName();
        String tenantId = lookupAuthorizedTenant(actorId);
        String traceId = validateCorrelationId(correlationId);

        ReportInput input =
                new ReportInput(reportId, actorId, tenantId, traceId);
        return reports.generate(input);
    }
}
~~~

Đây là **ví dụ Spring MVC tích hợp (không standalone)**. Cần import `CompletableFuture`, `Principal`, annotation MVC, và triển khai `lookupAuthorizedTenant`/`validateCorrelationId` theo security/business contract. `ReportInput` phải được khai báo trong file riêng nếu để `public record` ở top-level. `reports.generate(input)` trả future cho Spring MVC, để framework quản lý async response. Worker không cần request, principal hay session.

Một service tương ứng:

~~~java
@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(ReportInput input) {
        // Có thể bắt đầu sau lúc controller đã return.
        // Sử dụng input đã validate và các bean cần thiết.
        String result = "report-" + input.reportId()
                + "-tenant-" + input.tenantId();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Đây cũng là **snippet Spring**, cần `@EnableAsync`/executor bean và lời gọi qua Spring proxy. Không trả `HttpServletResponse` từ worker hoặc cố sửa request attributes để chuyển kết quả. Ngoại lệ từ method `@Async CompletableFuture` cần được quan sát/đưa về HTTP error mapping phù hợp.

### 8.3. Dữ liệu header chưa chắc đáng tin

`X-Tenant-Id`, `X-User-Id`, `X-Forwarded-For` và `X-Correlation-Id` có thể do client gửi. **Không** biến chúng thành “identity đã xác thực” chỉ vì đã copy từ request sang DTO. Hãy xác thực/chuẩn hóa theo trust boundary: security principal/claims đã verify, policy tenant, allowlisted proxy headers, length/character restrictions cho correlation ID.

Khi dùng `principal.getName()` làm actor ID, phải xét mapping định danh thực tế; không nhất thiết username hiển thị là key bền. Với job dài hạn, có thể dùng internal account ID không thay đổi khi đổi tên tài khoản.

## 9. Spring @Async: boundary dữ liệu và proxy

### 9.1. @Async không lưu giữ request hợp lệ

`@Async` điều phối việc gọi method qua Spring proxy tới một executor. Nó **không** tự kéo dài lifetime của `HttpServletRequest` được truyền vào argument, và không có nghĩa thread worker là thread servlet xử lý ban đầu.

~~~text
HTTP thread:
    validate -> build ReportInput -> asyncBean.generate(input) -> return

Spring proxy:
    submit invocation to executor

Worker thread:
    call generate(ReportInput) -> result / failure
~~~

Nếu method trả `void` và request đã trả HTTP response trước khi worker xong, cần có job ownership/logging/retry/durability riêng. Nếu method trả `CompletableFuture` cho MVC, framework có thể giữ logical async response mở đến khi future hoàn tất. Cả hai trường hợp đều không cần worker giữ raw request.

### 9.2. @Async self-invocation

Trong proxy mode mặc định, gọi `this.generate(input)` từ chính instance có thể bypass `@Async`: công việc sẽ chạy trực tiếp chứ không đi qua proxy. Cần gọi qua bean proxy ở tầng khác. Nhưng kể cả khi “trông như synchronous” trong test, **đừng** chuyển raw request sang async API chỉ vì đường gọi hiện tại chưa async; refactor sau có thể làm lỗi xuất hiện.

### 9.3. Executor bean nên do container quản lý

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class ExecutorConfig {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("report-");
        return pool;
    }
}
~~~

Đây là **snippet cấu hình Spring**, cần import từ `org.springframework.context.annotation`, `org.springframework.scheduling.annotation` và `org.springframework.scheduling.concurrent`. Spring context quản lý khởi tạo và shutdown bean. Queue phải có giới hạn phù hợp; tham số chỉ minh họa, không phải “64 là tối ưu”.

`ThreadPoolTaskExecutor` là **nơi task có thể nằm chờ**. Nếu task capture request, pool queue sẽ kéo dài reference lifetime. Dùng immutable snapshot giải quyết lớp vấn đề ownership; còn queue capacity, timeout, rejection và memory profile giải quyết giới hạn tài nguyên.

## 10. Spring Context Java 17 chạy được: chỉ truyền snapshot vào @Async

Demo tiếp theo **không cần servlet container**, nên không giả vờ rằng `@Async` đang quản lý Servlet request. Nó dùng Spring `AnnotationConfigApplicationContext`, `@EnableAsync` và `ThreadPoolTaskExecutor` để chứng minh cách truyền input đơn giản và tách biệt khỏi request object.

### 10.1. Cấu trúc Maven

~~~text
spring-request-snapshot/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SnapshotSpringDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-request-snapshot</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/SnapshotSpringDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SnapshotSpringDemo {

    public record JobInput(String actorId, String correlationId) { }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("jobExecutor")
        ThreadPoolTaskExecutor jobExecutor() {
            ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
            e.setCorePoolSize(1);
            e.setMaxPoolSize(1);
            e.setQueueCapacity(8);
            e.setThreadNamePrefix("job-");
            return e;
        }

        @Bean
        Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("jobExecutor")
        public CompletableFuture<String> process(JobInput input) {
            return CompletableFuture.completedFuture(
                    input.actorId() + "/" + input.correlationId());
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Worker worker = context.getBean(Worker.class);
            JobInput snapshot = new JobInput("actor-7", "corr-9");
            String result = worker.process(snapshot)
                                  .get(5, TimeUnit.SECONDS);

            System.out.println("job = " + result);
        }
    }
}
~~~

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SnapshotSpringDemo
~~~

**Stdout từ lớp demo khi chạy thành công:**

~~~text
job = actor-7/corr-9
~~~

Mã có đủ `main`, cấu hình bean, Spring async interceptor và đóng context. Không cần `HttpServletRequest` để thực thi worker; input là record gồm hai `String` bất biến. Trong ứng dụng HTTP thật, snapshot phải được tạo sau authentication/validation trong request boundary.

**Giới hạn của demo:** nó không chứng minh Servlet lifecycle vì không có web server. Ví dụ `RequestLifetimeDemo.java` phía trên mô phỏng sai khác thời gian sống; phần controller ở mục 8 minh họa tích hợp Servlet/Spring MVC thật.

## 11. MDC và correlation ID: truyền nhỏ, cleanup đúng

Một worker có thể cần correlation ID để log. Cách an toàn hơn là truyền **một chuỗi đã kiểm tra** vào task, rồi thiết lập MDC trong phạm vi task; dọn trong `finally` vì pooled thread còn dùng cho request/job tiếp theo.

Ví dụ với SLF4J `MDC` (dependency của logging framework, **snippet không standalone**):

~~~java
static Runnable withCorrelation(
        String correlationId, Runnable task) {

    return () -> {
        String previous = MDC.get("correlationId");
        try {
            if (correlationId == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", correlationId);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    };
}
~~~

Tại submission:

~~~java
String correlationId = validateCorrelationId(
        request.getHeader("X-Correlation-Id"));

executor.execute(withCorrelation(
        correlationId,
        () -> processWithId(correlationId)));
~~~

Đây là snippet với `validateCorrelationId`, `processWithId` và `executor` đã tồn tại. Snapshot được lấy trước khi schedule; wrapper **không cần** capture `request`. Ngoài ra, MDC có thể có nhiều key khác nhau; ví dụ chỉ quản lý một key để minh họa. Nếu application truyền nhiều key, cần snapshot nhỏ/được phép và restore từng key có trách nhiệm.

### TaskDecorator cũng cần capture đúng thời điểm

~~~java
executor.setTaskDecorator(delegate -> {
    String correlationId = MDC.get("correlationId");

    return () -> {
        String before = MDC.get("correlationId");
        try {
            if (correlationId == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", correlationId);
            }
            delegate.run();
        } finally {
            if (before == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", before);
            }
        }
    };
});
~~~

Đây là **snippet tích hợp**, giả định `executor` và `MDC` có dependency. `TaskDecorator` được áp vào callback thực thi, nhưng một task được `submit` có thể được bọc bằng `FutureTask`; error handling của decorator **không** phải nơi bảo đảm quan sát mọi exception của `submit`. Mục tiêu đoạn code ở đây chỉ là đưa **một correlation ID** xuyên thread và restore sạch sẽ, không truy cập request trong worker.

**Không** lưu `RequestContextHolder.currentRequestAttributes()` trong decorator rồi đính kèm cho mọi task để “dễ lấy header”. Việc đó có thể giữ request object graph ngoài lifecycle.

## 12. Spring Security: actor ID khác SecurityContext

Spring Security thường dùng `SecurityContextHolder` có context gắn với thread. Một worker tự tạo **không** mặc nhiên nhìn thấy authentication của servlet thread.

Nếu job chỉ cần định danh actor để audit và truy cập những resource có policy riêng, hãy trích xuất **actor ID đã xác thực** ở request boundary rồi cho phép worker kiểm tra quyền theo nghiệp vụ. Đừng chuyền bearer token hoặc principal object tùy ý vào queue dài hạn.

Nếu thật sự cần thực thi trong security context cụ thể, Spring Security cung cấp các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextAsyncTaskExecutor`. Chúng thiết lập/clear security context đúng phạm vi callback theo contract, nhưng:

- Không biến `HttpServletRequest` thành object hợp lệ sau completion.
- Không miễn trừ chính sách token expiry/revocation và quyền thay đổi theo thời gian.
- Không nên snapshot/chia sẻ một `SecurityContext` mutable cho nhiều task rồi sửa nó từ nhiều thread.
- Không nên dùng context propagation như “copy toàn bộ request” cho background job lâu dài.
- Với job bền qua restart, xử lý security bằng internal service identity và authorization policy thích hợp, không dựa trên in-memory thread context của HTTP request cũ.

Các wrapper security là công cụ cho **task-scoped execution context**, không phải giấy phép bỏ qua request lifecycle.

## 13. File upload, request body và stream: trường hợp rất dễ lỗi

### 13.1. Không truyền ServletInputStream ra ngoài request

~~~java
InputStream stream = request.getInputStream();

executor.execute(() -> parseDocument(stream));
~~~

**Snippet không an toàn** nếu stream vẫn phụ thuộc Servlet request hoặc bị container/request processing đóng trước khi worker đọc. Stream cũng không nhất thiết thread-safe và một worker lỗi có thể không đóng tài nguyên đúng lúc.

### 13.2. MultipartFile cũng không mặc nhiên là dữ liệu bền

Trong Spring MVC, `MultipartFile` có thể tham chiếu đến dữ liệu tạm do multipart processing quản lý. Không lưu cả `MultipartFile` hoặc `getInputStream()` vào queue để đọc nhiều phút sau response, vì dữ liệu tạm có thể được cleanup theo request lifecycle.

Với file lớn cần xử lý nền, ví dụ thiết kế hợp lý:

~~~text
HTTP multipart request
      |
      +-- Xác thực/kiểm tra content type, kích thước, quota
      +-- Lưu stream vào durable object storage hoặc vùng staging
      +-- Commit metadata: fileId, ownerId, size, checksum
      +-- Đưa fileId + jobId vào queue (atomic/outbox nếu cần)
      |
      v
Response 202 Accepted (+ jobId)

Background worker:
      |
      +-- Load dữ liệu theo fileId từ storage
      +-- Kiểm tra quyền/quota và tính toàn vẹn
      +-- Xử lý, cập nhật trạng thái
      +-- Dọn dữ liệu staging theo retention policy
~~~

Không cần copy toàn bộ file vào `byte[]` trong RAM để gọi đó là snapshot. Đối với upload cần durability, truyền **reference tới file đã được lưu có hợp đồng retention** hiệu quả và an toàn hơn.

### 13.3. Ví dụ Spring MVC: staging rồi giao job

~~~java
@PostMapping(path = "/imports", consumes = "multipart/form-data")
public ResponseEntity<JobAccepted> upload(
        @RequestParam("file") MultipartFile file,
        Principal principal) throws IOException {

    String ownerId = principal.getName();
    String objectKey = storage.saveValidated(file.getInputStream(),
                                             file.getSize(), ownerId);
    String jobId = jobs.enqueueImport(ownerId, objectKey);

    return ResponseEntity.accepted()
            .body(new JobAccepted(jobId));
}
~~~

Đây là **snippet Spring MVC**: `storage` và `jobs` là các bean ứng dụng cần implement; `JobAccepted` là DTO; cần imports cho `MultipartFile`, `Principal`, `IOException`, `ResponseEntity`. Trong production, phải giới hạn size, xác thực MIME/format độc lập client, cleanup stream và xử lý atomicity giữa save/enqueue. **Bảo đảm `saveValidated` thực sự đã ghi dữ liệu vào storage ổn định trước khi nhận job**. Nếu thao tác thất bại, không trả 202 giả.

Nếu object storage và DB queue không cùng transaction, dùng job state/idempotency/outbox hoặc compensation/cleanup để tránh job trỏ tới file chưa tồn tại hoặc file mồ côi.

## 14. Timeout, cancellation và các việc tiếp tục sau HTTP response

Một task có thể vẫn chạy khi:

- Client đóng kết nối.
- Spring MVC async request timeout.
- Controller trả 202 và đã kết thúc response.
- Downstream chậm hơn deadline HTTP.
- Worker đã nằm trong queue lúc context shutdown.
- Frontend retry tạo ra logical request thứ hai.

Trong tất cả trường hợp, **request object không trở thành nguồn dữ liệu nền bền vững**. Cần thiết kế lifecycle của **job** riêng với lifecycle của **HTTP request**.

### Khi trả CompletableFuture cho Spring MVC

~~~java
@GetMapping("/reports/{id}")
public CompletableFuture<String> report(@PathVariable String id) {
    String reportId = validateId(id);
    return reportService.generateAsync(reportId);
}
~~~

Đây là **Spring MVC snippet**; cần service và validator. Framework có thể giữ async HTTP request tới khi future hoàn thành/timeout/được xử lý theo contract. Worker vẫn chỉ dùng `reportId` chứ không cần `HttpServletRequest`.

### Khi trả 202 rồi thực hiện job nền

Nếu hệ thống có durable job queue:

~~~text
POST /exports
    |
    +-- validate payload, identity
    +-- persist job(input snapshot)
    +-- return 202 + jobId
                 |
                 v
            background worker
                 |
                 +-- status=RUNNING/SUCCEEDED/FAILED
                 +-- GET /jobs/{jobId} để theo dõi
~~~

Ở đây 202 thường chỉ có nghĩa **yêu cầu đã được chấp nhận để xử lý**, không phải công việc hoàn tất. Nếu chỉ gọi `@Async void` rồi trả 202 mà không lưu job trạng thái/queue, application crash có thể làm mất việc.

### Khi cancel

Hủy `CompletableFuture` không có nghĩa underlying network/db action sẽ dừng ngay hoặc rollback side effect. Với task trong executor, cần chủ động gắn cancellation/deadline với job và tài nguyên đang dùng theo API tương ứng. Cleanup chạy ở `finally` của task hoặc lifecycle callback phù hợp, không cố “sửa response” bằng `HttpServletResponse` cũ.

## 15. Request-scoped bean: một góc dễ bỏ sót

~~~java
@Component
@RequestScope
public class RequestMetadata {
    private final String requestId;
    // ...
}
~~~

Đây là **snippet minh họa**, không độc lập. Một bean `@RequestScope` có vòng đời gắn với một HTTP request trong web-aware `ApplicationContext`. Khi code ở worker cố truy cập request-scoped proxy ngoài scope thích hợp, có thể gặp lỗi không có request scope active, ví dụ một `ScopeNotActiveException` hoặc exception gốc bên dưới tùy cấu hình.

Cũng không nên nhận toàn bộ request-scoped bean làm argument của một job chạy sau response. Bean đó có thể giữ request, body hoặc tài nguyên tạm qua các field.

**Nên:** lấy `requestMetadata.getRequestId()` khi request scope còn hợp lệ, copy kết quả `String` vào DTO, rồi truyền DTO cho worker. Nếu bean chứa object mutable, phải xác định ranh giới deep copy và validation.

## 16. Phân biệt dữ liệu, context và quyền truy cập

Ba thứ thường bị trộn lẫn:

1. **Dữ liệu nghiệp vụ:** document ID, order ID, amount, validated options. Cần để worker làm việc. Nên nằm trong immutable DTO hoặc durable job payload.
2. **Thông tin quan sát:** trace ID, correlation ID, locale code, operation ID. Có thể chuyển một tập nhỏ được phép qua thread hoặc task decorator; cleanup sau mỗi task.
3. **Quyền/ngữ cảnh bảo mật:** authentication token, session, security principal, tenant policy, request-specific authorities. Không nên copy mù vào job dài hạn; cần security contract riêng, hết hạn/quyền hiện hành và auditing.

“Snapshot tất cả headers để chắc” là phản ví dụ: sẽ copy cookie, bearer token, proxy headers chưa kiểm chứng và metadata không cần thiết. Một record nhỏ chỉ an toàn nếu **các giá trị trong nó đã được kiểm tra và hợp lệ với thời gian sống của job**.

## 17. Bài toán retry và request đã đóng

Một task đã tách khỏi request có thể bị retry sau vài phút. Nếu nó mang request cũ:

~~~java
scheduler.schedule(
        () -> callPartner(request.getHeader("Authorization")),
        5, TimeUnit.MINUTES);
~~~

Đây là **snippet phản ví dụ**. Sau 5 phút, request đã hết lifecycle; token có thể hết hạn; giữ header Authorization trong callback là retention của bí mật. Không sửa bằng cách bọc request vào `Supplier<HttpServletRequest>` — supplier vẫn có thể giữ tham chiếu hoặc trả context sai.

**Thiết kế đúng hơn**:

- Xác định **logical operation ID** và các scalar parameters được phép.
- Lưu job payload bền vững nếu việc cần tồn tại qua restart.
- Tại lúc thực thi/retry, dùng service credential/authorization thích hợp hoặc refresh token qua cơ chế được bảo mật, không lấy token từ request cũ.
- Dùng cùng idempotency key cho các attempts của một logical operation nếu downstream có side effect.
- Khi job hết TTL/permission, dừng và đánh dấu trạng thái rõ ràng.

### Khi cần hồi cứu HTTP metadata

Nếu cần audit request path, client ID hoặc idempotency key, chuẩn hóa và ghi log/event **trong request boundary**, không giữ raw `HttpServletRequest` để “sau này mở ra xem”. Audit cần retention/access controls chứ không dựa vào container object sống trong RAM.

## 18. Giảm nguy cơ memory retention

Một queue hữu hạn vẫn có thể giữ payload lớn nếu input quá nặng. Các biện pháp cần phối hợp:

1. **Small DTO:** chỉ các ID/scalar cần dùng, không giữ body/session/request.
2. **Bounded executor:** hạn chế worker/queue và có chính sách overload rõ.
3. **Timeout/deadline:** không cho future/task pending vô hạn.
4. **Job ownership:** không để static registry giữ Future hoàn thành mãi không cleanup.
5. **Explicit cleanup:** stream, temp file, storage lease, context restoration.
6. **Metric:** queue depth, waiting time, task age, payload size, heap old-generation, retained objects.
7. **Heap analysis:** dùng heap dump/profiler trong môi trường an toàn để tìm đường tham chiếu từ GC root tới `HttpServletRequest`/`ServletRequestAttributes` khi nghi ngờ.
8. **Data minimization:** không giữ bearer token/cookies/body ở background queues; áp retention/access controls cho job payload.

Không cần chứng minh một request đã được GC để khẳng định code đúng; quan trọng hơn là **không có đường tham chiếu sai cấu trúc**. `System.gc()` và `WeakReference.get()==null` không phải assertion đáng tin trong unit test vì GC không có thời hạn bắt buộc.

## 19. Kiểm thử và QA trong dự án

### 19.1. Test snapshot không phụ thuộc request object

JUnit 5 snippet:

~~~java
JobInput input = new JobInput(
        "job-1", "actor-2", "tenant-3", "corr-4", "doc-5");

assertEquals("tenant-3", input.tenantId());
assertEquals("doc-5", input.documentId());
~~~

Đây là **snippet**, cần record `JobInput` ở mục 6 và các imports JUnit 5. Mục đích là xác minh dữ liệu có kiểu, bất biến và thuộc tính được copy rõ ràng. Test thêm validation không cho phép giá trị rỗng, quá dài hoặc sai định dạng theo policy; code record mẫu chỉ kiểm tra null, chưa thay validator.

### 19.2. Test không truy cập request sau khi lifecycle hoàn tất

Ví dụ `RequestLifetimeDemo` ở mục 7 dùng fake request có trạng thái active và `CountDownLatch`. Trong unit test service, có thể dùng fake/spy request để ném lỗi nếu gọi sau khi method handler kết thúc; assert service chỉ nhận DTO. Không nên dùng `Thread.sleep(1000)` rồi đoán worker chắc chắn đã chạy sau response.

### 19.3. Test Spring MVC async thực sự

Dùng Spring MVC test hoặc integration test với container để xác minh:

- Controller tạo snapshot **trước** khi return.
- `@Async` được kích hoạt qua proxy (không self-invocation).
- Controller trả `CompletableFuture`/`DeferredResult` được framework quản lý; lỗi/timeout được map chính xác.
- Không có code bên worker gọi `RequestContextHolder.currentRequestAttributes()` hoặc bean `@RequestScope` sau khi response đã complete.
- Sau khi async request hoàn tất, không giữ references trong custom scheduler/registry.
- Với file upload, worker nhận storage key; multipart temp file chỉ được dùng trong request lifecycle đúng.
- Khi task bị reject hoặc context shutdown, không mất job status hoặc trả “success” giả.

### 19.4. Test chống lộ context giữa hai task

Sử dụng **một pooled worker** chạy lần lượt hai task với correlation ID khác nhau. Task thứ nhất gắn `traceId="A"` rồi cleanup; task thứ hai phải không thấy A nếu không được cấp context. Kiểm tra `finally` của decorator/MD C wrapper cả khi task ném exception và khi bị cancel. Không dùng thread inheritance để “vá” lỗi.

### 19.5. Test footprint/retained references

Có thể profile dưới load với hàng đợi có giới hạn, đo heap retained size và class histogram trước/sau một loạt request. Không dùng `WeakReference` + ép GC làm tiêu chí pass/fail; thay vào đó, enforce code review/type boundaries “job payload không chứa ServletRequest/ServletResponse/RequestAttributes/MultipartFile/InputStream/Session” và kiểm thử chức năng.

### 19.6. Test phân quyền và bảo mật dữ liệu

- Client giả mạo `X-Tenant-Id` phải không thể chọn tenant khác trong snapshot.
- Input có bearer token/cookie không được sao chép vào job payload/log/trace.
- Job chạy lâu hoặc retry phải dùng policy authorization phù hợp với thời điểm thực thi.
- Người dùng không được đọc kết quả job khác chỉ bằng đoán job ID.
- Storage key không lộ dữ liệu nếu bị lấy trực tiếp; dùng internal ACL hoặc signed URL ngắn hạn theo contract.

## 20. Những ngộ nhận phổ biến

**1. “Controller return nghĩa là Servlet request luôn hoàn tất ngay.”** Sai trong Servlet async được quản lý; có thể vẫn open đến future/async completion.

**2. “Nếu @Async được gọi, container tự giữ HttpServletRequest sống tới lúc task xong.”** Sai. `@Async` và Servlet async request là hai cơ chế khác nhau.

**3. “Giữ request chỉ tốn một pointer.”** Sai về retained object graph: một pointer có thể giữ nhiều attributes, wrappers hoặc dữ liệu.

**4. “Có reference thì request vẫn hợp lệ về mặt API.”** Sai. GC reachability và lifecycle validity là hai tính chất khác nhau.

**5. “Không thấy exception khi đọc request trên worker nghĩa là code an toàn.”** Sai. Có thể là race hoặc container vẫn chưa recycle ở lần test đó.

**6. “Copy ServletRequestAttributes sang thread là snapshot.”** Sai. Nó thường giữ request/response và các attributes gắn với lifecycle.

**7. “Record luôn deep immutable.”** Sai. Record với field là List mutable element hoặc `byte[]` vẫn có dữ liệu thay đổi được.

**8. “Truyền Principal hay Authentication nguyên bản chắc chắn an toàn cho job 1 giờ.”** Không. Cần cân nhắc credential, quyền thay đổi, token expiry, sensitivity và security contract.

**9. “RequestContextHolder tự hoạt động ở mọi @Async worker.”** Sai. ThreadLocal thường không tự di chuyển qua executor thread.

**10. “Bật setThreadContextInheritable(true) là giải pháp tốt cho pool.”** Sai. Spring cảnh báo truyền context vào pooled thread mới tạo có thể làm lộ context qua công việc khác.

**11. “TaskDecorator copy mọi context sẽ không gây retention.”** Sai nếu context chứa `RequestAttributes` hoặc token/objects nặng.

**12. “Giữ MultipartFile rồi xử lý sau response vẫn an toàn.”** Không mặc định. Multipart storage và stream có thể bị cleanup theo request.

**13. “Cứ copy body thành byte[] là xong.”** Không đủ. Nếu body lớn, queue chứa hàng nghìn bản sao có thể làm OOM; dùng staging/object storage.

**14. “Snapshot correlation ID nghĩa là đã xác thực user.”** Sai. Correlation ID chỉ phục vụ observability; auth/tenant phải từ nguồn tin cậy.

**15. “Thread pool chỉ giữ task đang chạy, không giữ queue.”** Sai. Pending Runnable/Callable vẫn giữ closure và dữ liệu đi kèm.

**16. “Request-scoped proxy dùng được ở mọi worker sau HTTP completion.”** Sai. Proxy không kéo dài request scope.

**17. “Return 202 đảm bảo job đã chạy thành công.”** Sai. 202 chỉ nêu yêu cầu được nhận để xử lý theo hợp đồng; cần durable job status nếu business yêu cầu.

**18. “Hủy CompletableFuture là đã hủy luôn I/O hay rollback side effect.”** Sai. Hủy future không thay thế cancellation của underlying resource và nghiệp vụ.

**19. “Dùng WeakReference test là đủ xác nhận không leak.”** Sai: GC nondeterministic; kiểm tra ownership và retained references cấu trúc đáng tin hơn.

**20. “Dọn MDC chỉ khi task thành công.”** Sai. `finally` là bắt buộc để không làm contamination khi worker được tái sử dụng.

## 21. Câu hỏi tự kiểm tra

**Câu 1:** `@Async public void export(HttpServletRequest request)` an toàn vì Spring đã làm bất đồng bộ?

**Đáp án:** không. `@Async` chỉ điều phối method. Request có thể đã hết lifecycle khi worker đọc. Hãy trích xuất `ExportInput` immutable trong controller và truyền object đó.

**Câu 2:** Spring MVC controller trả `CompletableFuture`. Request có chắc hết hiệu lực ngay khi method trả không?

**Đáp án:** không. Spring MVC có cơ chế Servlet async, logical request có thể vẫn còn đến async completion. Nhưng không vì vậy mà nên truyền raw request vào worker ngoài kiểm soát framework.

**Câu 3:** Task đã xong nhưng một static map vẫn giữ `FutureTask` tham chiếu request. Heap có thể còn giữ request không?

**Đáp án:** có thể, nếu FutureTask/callback vẫn có đường tham chiếu mạnh tới object liên quan. Tùy implementation và thời điểm cleanup, retention graph cần được kiểm tra; giải pháp là không capture request và có cleanup registry.

**Câu 4:** `record Input(byte[] raw)` là immutable hoàn toàn?

**Đáp án:** không. Record chỉ cố định reference `raw`, còn phần tử mảng có thể bị sửa. Cần defensive copy nếu thật sự cần dữ liệu và kiểm soát kích thước; tốt hơn dùng storage key cho payload lớn.

**Câu 5:** Có nên truyền cả `ServletRequestAttributes` sang thread khác để gọi `RequestContextHolder`?

**Đáp án:** không như giải pháp chung cho job chạy sau response. Attributes có thể giữ raw request và chỉ hợp lệ trong lifecycle request; chọn snapshot nhỏ hoặc context propagation được quản lý theo lifetime rõ ràng.

**Câu 6:** Multipart file 200 MiB được xử lý 10 phút sau response. Truyền `MultipartFile` vào queue có phù hợp không?

**Đáp án:** không nên. Lưu dữ liệu theo kiểm soát an toàn vào durable storage trong request boundary, chỉ enqueue storage key và job ID.

**Câu 7:** Vì sao không cần GC test để chứng minh input an toàn?

**Đáp án:** vấn đề là dependency/lifetime ownership: DTO không giữ request, worker không truy cập context sau completion, queue có giới hạn. GC timing không xác định, nên `System.gc`/`WeakReference` không bảo đảm test pass đáng tin.

**Câu 8:** Worker có phải sử dụng bearer token cũ của client để gọi downstream sau một giờ?

**Đáp án:** không mặc định. Phải thiết kế credential/delegation có expiry/revocation/authorization và storage bảo mật; tốt hơn là service identity cùng business actor ID được audit theo contract.

**Câu 9:** Một executor dùng `InheritableThreadLocal` để truyền tenant từ request thread vào pooled thread, có rủi ro gì?

**Đáp án:** pooled thread được tạo trong một request có thể giữ tenant/context cũ và phục vụ tác vụ khác sau đó; Spring cảnh báo chính trường hợp này. Dùng propagation theo task và cleanup chặt, không copy nguyên request.

**Câu 10:** Trả 202 ngay sau khi `@Async void` nhận task, tiến trình crash trước khi task chạy. Vì sao người dùng không thể biết trạng thái?

**Đáp án:** công việc chỉ tồn tại trong RAM/queue không bền nếu chưa có job store. Nếu tác vụ cần delivery guarantee, phải lưu intent/job status bền vững trước khi trả accepted.

## 22. Checklist code review/triển khai

- [ ] Không truyền `HttpServletRequest`, `HttpServletResponse`, `ServletRequestAttributes`, `HttpSession` hoặc request-scoped proxy vào background job.
- [ ] Không capture request qua lambda/anonymous class/`this`/callback, scheduler, static cache hoặc queue.
- [ ] Snapshot chỉ có field cần thiết, được validate/authorize, không chứa raw headers/cookies/bearer token.
- [ ] Với record/DTO có collection/mutable value, đã copy hoặc chọn immutable representation phù hợp.
- [ ] Không giữ `MultipartFile`/`ServletInputStream` sau lifecycle; file lớn có storage object key và retention/ACL phù hợp.
- [ ] Hiểu sự khác biệt giữa controller return, Servlet async completion và fire-and-forget `@Async`.
- [ ] Spring `@EnableAsync` và proxy được cấu hình đúng; không lạm dụng self-invocation.
- [ ] `ThreadPoolTaskExecutor` có queue/worker cap, timeout, rejection handling và shutdown.
- [ ] Context/trace propagation chỉ mang dữ liệu cần thiết, cleanup `ThreadLocal/MDC` trong `finally`.
- [ ] Không bật `setThreadContextInheritable(true)` cho pool tái sử dụng.
- [ ] Quyền actor/tenant được xác minh, không tin header chưa xác thực, job dài hạn có policy security riêng.
- [ ] Có deadline/cancellation, không dùng response/request object cũ để hoàn tất job đã tách.
- [ ] Với job lâu dài hoặc phải retry sau crash, lưu payload/intent/status bền vững cùng idempotency.
- [ ] Có metrics queue depth, task age, retained heap, lỗi async, trạng thái job.
- [ ] Test có lifecycle fake/latch, async MVC integration, cross-task MDC, file staging và giả mạo tenant.
- [ ] Không dùng `System.gc()`/`WeakReference` như điều kiện bắt buộc để coi mã đúng.

## 23. Kết luận

**Không giữ toàn bộ object request sau khi request hoàn tất** là nguyên tắc về **lifecycle ownership, tính đúng đắn đồng thời, bảo mật và memory retention**.

Trong request boundary, hãy xác thực, kiểm tra đầu vào, trích xuất **immutable snapshot tối thiểu**, rồi truyền snapshot đến executor hoặc persistent job queue. Worker phải dùng snapshot và các dependency độc lập với Servlet request; không đọc lại request attributes, raw headers, session, stream hay response sau lifecycle.

Spring MVC có Servlet async processing hợp lệ nên **controller return không luôn đồng nghĩa request đã kết thúc**. Dù vậy, `@Async` hay `CompletableFuture` tự nó không cho phép giữ request vô thời hạn. Với context propagation, chỉ chuyển giá trị cần thiết và cleanup theo task. Với job chạy lâu, truyền **job ID/storage key** và quản lý trạng thái bền vững thay vì giữ object container trong RAM.

## Tài liệu tham khảo

- Jakarta Servlet specification — **Lifetime of the Request Object** và asynchronous processing: https://jakarta.ee/specifications/servlet/6.1/jakarta-servlet-spec-6.1
- Spring MVC Reference — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring MVC Reference — Controller Return Values (CompletionStage/CompletableFuture): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework Reference — Bean Scopes (`request` scope): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — `RequestContextHolder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html
- Spring Framework — `RequestContextFilter` Javadoc (InheritableThreadLocal warning): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/RequestContextFilter.html
- Spring Framework — `ContextPropagatingTaskDecorator` (Spring 6.1+): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework Reference — Task Execution / @Async: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Security Reference — Concurrency Support: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework Reference — Multipart Form Data: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
