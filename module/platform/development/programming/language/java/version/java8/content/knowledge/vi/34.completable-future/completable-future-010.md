# Giữ chuỗi bất đồng bộ dễ quan sát và không chặn vô ích với CompletableFuture

`CompletableFuture<T>` là API Java 8 cho phép biểu diễn một **kết quả sẽ có trong tương lai** và thiết lập các **bước xử lý phụ thuộc vào kết quả ấy**. Nó hiện vẫn được hỗ trợ và là công cụ hữu ích để phối hợp các tác vụ bất đồng bộ. Tuy nhiên, chỉ dùng `supplyAsync` hoặc trả về một `CompletableFuture` chưa đủ làm một hệ thống thực sự hiệu quả: nếu một stage gọi `join()` để chờ stage tiếp theo, các worker vẫn bị giữ chỉ để đợi. Nếu một stage thất bại mà không có log, trace ID, timeout hoặc metrics, chuỗi xử lý sẽ khó quan sát trong production.

Nguyên tắc xuyên suốt:

> **Biểu diễn phụ thuộc bằng chain, giữ trạng thái lỗi xuyên suốt, quan sát từng ranh giới quan trọng, và chỉ chặn ở ranh giới đồng bộ thật sự cần kết quả.**

Bài học giới thiệu mô hình CompletableFuture/CompletionStage; `thenApply`, `thenCompose`, `thenCombine`; quan sát bằng `whenComplete`, `handle`, `exceptionally`; executor; propagation của trace context; timeouts, cancellation, retry, backpressure, kiểm thử, cùng ví dụ Java độc lập có thể chạy trên JDK 17+. Chỉ sử dụng kiến thức **vẫn áp dụng trong Java hiện hành**. Các API bổ sung sau Java 8 được ghi rõ phiên bản bắt đầu.

## 1. CompletableFuture là đồ thị completion, không chỉ là thread chạy nền

Một chuỗi CompletableFuture mô tả **điều kiện để các stage được hoàn thành**. Khi một stage thành công, callback phụ thuộc thành công có thể chạy; khi stage lỗi, nhánh bình thường có thể bị bỏ qua và lỗi lan sang kết quả phụ thuộc.

~~~text
RequestContext(traceId)
  |
  +--> fetchUserAsync -------------> fetchGreetingAsync ---+
  |                                                       |
  +--> fetchPlanAsync ------------------------------------+--> combine
                                                               |
                                                               v
                                                            format
                                                               |
                                                               v
                                                          observe final
                                                               |
                                                               v
                                                      return CompletionStage
~~~

- `fetchUserAsync` và `fetchPlanAsync` không phụ thuộc nhau, nên có thể khởi động cùng lúc.
- `fetchGreetingAsync` cần dữ liệu user, vì vậy được nối bằng `thenCompose` sau user.
- `combine` chỉ xử lý khi cả greeting và plan hoàn thành bình thường.
- `observe final` có thể ghi trạng thái và thời gian mà không thay kết quả.
- Service có thể **trả stage cuối** để caller tiếp tục, không buộc một thread chờ.

Không nên coi mỗi mũi tên trong sơ đồ là một thread. Callback của CompletableFuture có thể chạy trên thread hoàn tất stage, thread tham gia completion hoặc executor do ứng dụng chọn. Mô hình là **phụ thuộc và hoàn tất**, không phải một bản đồ thread cố định.

### 1.1. Đảm bảo cần nhớ

1. Đăng ký callback qua `thenXxx` thường **không bắt caller chờ** stage trước hoàn tất.
2. Khi stage kết thúc, kết quả có thể là **bình thường, exceptional hoặc cancelled**; lỗi không biến mất chỉ vì một bước sau không được gọi.
3. Một stage trả `CompletableFuture<T>` có thể đã hoàn thành ngay, hoàn thành sau hoặc không bao giờ hoàn thành nếu không có nguồn completion.
4. `join` và `get` **có thể chặn thread đang gọi** nếu chưa có kết quả.
5. Gắn thêm callback không tự làm một thư viện blocking I/O thành network I/O không chặn.

## 2. Chọn kiểu public API và công cụ tương ứng

`CompletableFuture<T>` triển khai cả `Future<T>` và `CompletionStage<T>`. `CompletionStage` tập trung vào **ghép tiếp xử lý**; `CompletableFuture` còn có công cụ hoàn thành thủ công, kiểm trạng thái và phương thức kiểu Future.

| Thành phần | Ý nghĩa | Khi nào phù hợp |
|---|---|---|
| `CompletionStage<T>` | Giao diện cho chuỗi phụ thuộc | API muốn caller ghép xử lý mà không tự quản lý completion |
| `CompletableFuture<T>` | CompletionStage + Future có thể complete | Tạo stage, bridge callback, kiểm soát timeout |
| `supplyAsync(supplier, executor)` | Chạy supplier qua executor | Tác vụ có giá trị trả về |
| `runAsync(runnable, executor)` | Chạy action qua executor | Công việc hoàn thành kiểu Void |
| `completedFuture(value)` | Future đã có giá trị | Cache hit, test và kết quả tức thời |
| `failedFuture(error)` | Future lỗi ngay (Java 9+) | Giữ lỗi trong hợp đồng async |
| `thenApply` | Biến một giá trị thành giá trị khác | Map/format/validate nhanh |
| `thenCompose` | Nối một hàm trả stage rồi làm phẳng | Fetch phụ thuộc dữ liệu trước |
| `thenCombine` | Kết hợp hai kết quả | Fan-in hai công việc độc lập |
| `whenComplete` | Quan sát success/error | Metrics, tracing, log |
| `handle` | Chuyển outcome thành giá trị mới | Mapping lỗi và policy kết quả |
| `exceptionally` | Recovery khi lỗi bằng giá trị | Fallback rõ ràng |

Với service public API, `CompletionStage<Result>` thường mô tả đúng intent hơn khi caller chỉ cần chain. Tuy nhiên **không dùng kiểu interface này làm lớp bảo mật tuyệt đối**: `toCompletableFuture()` cho phép caller lấy CompletableFuture tương ứng, behavior phụ thuộc implementation. Các API `minimalCompletionStage()` và `copy()` có từ Java 9 có thể hạn chế khả năng sửa future gốc trong một số tình huống.

Nếu caller phải gọi `orTimeout` hoặc kiểm các trạng thái `Future`, trả `CompletableFuture` có thể hợp lý. Hợp đồng cần nêu rõ **ai sở hữu completion, timeout và cancellation**.

## 3. thenApply và thenCompose: khác nhau tại ranh giới async

`thenApply` được dùng khi hàm xử lý **tạo ngay một giá trị** từ kết quả đã có:

~~~java
CompletableFuture<String> name = userFuture
        .thenApply(user -> user.name().trim().toUpperCase());
~~~

Đây là **mảnh code** với `userFuture` và kiểu `User` do ứng dụng định nghĩa. Nếu chỉ trim và format chuỗi, callback ngắn, không cần tạo thêm task chạy nền.

Ngược lại, nếu hàm phụ thuộc **trả về một future khác**, dùng `thenCompose` để làm phẳng.

### 3.1. Phản ví dụ: join trong callback

~~~java
CompletableFuture<UserView> bad = findUserAsync(id)
        .thenApply(user -> {
            Details details = loadDetailsAsync(user).join();
            return new UserView(user, details);
        });
~~~

Đây là **mảnh code minh họa cách làm nên tránh**; các kiểu/hàm ứng dụng chưa được khai báo ở đây. Vấn đề không nằm ở `UserView` mà ở `join()` bên trong callback. Nếu future details chưa có kết quả, callback giữ thread chỉ để đợi, gây:

- Lãng phí worker và tăng thời gian chiếm executor.
- Tăng nguy cơ starvation/deadlock khi stage con dùng cùng một pool ít worker.
- Làm duration của callback trộn giữa thời gian xử lý và thời gian chờ.
- Khó phân tích latency và dễ gây tắc nghẽn khi tải cao.

Sửa thành:

~~~java
CompletionStage<UserView> good = findUserAsync(id)
        .thenCompose(user ->
                loadDetailsAsync(user).thenApply(
                        details -> new UserView(user, details)));
~~~

`thenCompose` nối kết quả stage con mà không cần một callback ngồi chờ nó.

### 3.2. Nested future là một dấu hiệu đáng chú ý

~~~java
CompletableFuture<CompletableFuture<Details>> nested =
        findUserAsync(id)
                .thenApply(user -> loadDetailsAsync(user));

CompletableFuture<Details> flat =
        findUserAsync(id)
                .thenCompose(user -> loadDetailsAsync(user));
~~~

Nếu `loadDetailsAsync` trả `CompletableFuture<Details>`, biến đầu là future chứa **một future khác**. Nó có thể hoàn tất khi inner future vừa được tạo, chưa phải khi `Details` có dữ liệu. Biến thứ hai mới là stage hoàn thành khi Details đã thực sự sẵn sàng.

**Quy tắc đọc:** bước sau trả giá trị trực tiếp → `thenApply`; bước sau trả `CompletionStage` → `thenCompose`. Không dùng `join` để ép stage thứ hai thành giá trị trực tiếp.

### 3.3. Đừng lạm dụng các overload Async

`thenApplyAsync(fn, executor)` hữu ích nếu phép biến đổi nặng CPU hoặc cần cách ly scheduling. Nhưng với `String::trim`, tạo thêm một task thường không đem lại lợi ích. `thenComposeAsync(fn, executor)` lên lịch **hàm tạo stage con**; bản thân stage mà hàm trả về vẫn chịu cơ chế thực thi riêng của nó.

Không có bảo đảm một stage Async luôn chạy trên **thread mới** hoặc cùng tên thread; executor có thể tái sử dụng worker. Chọn overload theo công việc thật, không theo suy nghĩ “càng nhiều Async càng tốt”.

## 4. Công việc độc lập: thenCombine và allOf

Nếu cần user và plan độc lập:

~~~java
CompletableFuture<User> user = loadUserAsync(id);
CompletableFuture<Plan> plan = loadPlanAsync(id);

CompletableFuture<View> view = user.thenCombine(
        plan, (u, p) -> new View(u, p));
~~~

Đây là mảnh code với hai API giả định. Hai lời gọi đã được khởi tạo; `thenCombine` **không block thread caller** và chỉ tính toán khi cả hai kết quả thành công.

Không viết:

~~~java
User u = loadUserAsync(id).join();
Plan p = loadPlanAsync(id).join();
return new View(u, p);
~~~

Cách này chờ user trước rồi mới bắt đầu plan, bỏ mất khả năng chạy đồng thời và tạo điểm chặn ở caller.

### 4.1. allOf: hoàn tất tất cả, không tập hợp giá trị

`CompletableFuture.allOf(a, b, ...)` trả `CompletableFuture<Void>`, hoàn thành khi các future được cho đều hoàn tất, và hoàn thành bất thường khi một hoặc nhiều nhánh lỗi theo quy tắc API.

~~~java
CompletableFuture<String> a = callAAsync();
CompletableFuture<Integer> b = callBAsync();

CompletableFuture<Summary> result =
        CompletableFuture.allOf(a, b)
                .thenApply(ignored ->
                        new Summary(a.join(), b.join()));
~~~

Đây là mảnh minh họa. `join` trong `thenApply` ở **trường hợp rất cụ thể này** không cần chờ vì callback chỉ được gọi sau khi `allOf` hoàn thành bình thường, nghĩa là a và b đã hoàn tất. Tuy nhiên, với **hai future có kiểu rõ**, `thenCombine` dễ đọc hơn và giảm nhầm lẫn về chặn.

Không suy ra `allOf` tự hủy các future còn lại khi một nhánh lỗi. Cần chính sách cancellation riêng nếu việc hủy có ý nghĩa nghiệp vụ và tài nguyên.

### 4.2. anyOf không phải nhánh thành công đầu tiên

`anyOf` hoàn thành theo **future hoàn tất đầu tiên**, có thể là bình thường hoặc exception. Nó trả `CompletableFuture<Object>`, không tự cancel các nhánh thua. Nếu mục tiêu là “lấy response thành công đầu tiên từ nhiều replica”, cần giải quyết lỗi từng nhánh, policy hợp nhất và tài nguyên còn chạy; `anyOf` đơn thuần chưa đủ.

## 5. Dễ quan sát có nghĩa là trả lời được câu hỏi vận hành

Một chuỗi bất đồng bộ trong production nên cho phép trả lời:

- Request nào bị chậm? **Trace ID** nào liên kết các stage?
- Stage nào lỗi, và lỗi có được phục hồi bằng fallback không?
- Chậm tại queue của executor, tại I/O thật hay do xử lý kết quả?
- Có bao nhiêu request đang in-flight; bao nhiêu timeout/cancel?
- Thời gian p95/p99 của stage nào tăng trước?
- Retry có đang đẩy dependency vào quá tải?
- Future nào được tạo nhưng không bao giờ được complete?

Tốt nhất dùng **tên stage ổn định theo nghiệp vụ**: `lookupUser`, `loadProfile`, `loadPlan`, `buildResponse`, không chỉ `stage1`/`stage2`.

### 5.1. Các tín hiệu thường dùng

| Tín hiệu | Nên ghi | Lưu ý |
|---|---|---|
| Structured log | traceId, stage, outcome, error type | Không log token/PII mặc định |
| Distributed tracing | Span cho công việc, quan hệ cha/con | Propagate context qua async |
| Metrics counter | Success, error, timeout, cancellation | Nhãn stage/dependency có tập giá trị hữu hạn |
| Latency histogram | Duration của stage và pipeline | Xem p95/p99, không chỉ average |
| Executor metrics | Active count, queue depth, rejected tasks | Phân biệt thiếu worker với dependency chậm |
| Recovery metrics | fallback.used, retry.attempt | Normal completion cuối có thể là degraded result |

**Không dùng từng traceId làm label metric có cardinality rất cao.** Mỗi request sẽ tạo một tập time-series mới, làm tăng tài nguyên giám sát. TraceId nên thuộc log/trace; metric thường dùng stage, operation, dependency, outcome.

### 5.2. Dùng whenComplete để quan sát success và failure

~~~java
CompletableFuture<Result> monitored =
        original.whenComplete((value, error) -> {
            if (error == null) {
                metrics.increment("stage.ok");
            } else {
                metrics.increment("stage.failed");
                logSafeError(error);
            }
        });
~~~

Đây là **mảnh minh họa**; các tên `Result`, `original`, `metrics`, `logSafeError` được định nghĩa bởi ứng dụng. `whenComplete` chạy khi stage hoàn thành bình thường hoặc lỗi. Nếu callback không ném exception, stage được trả về giữ **cùng giá trị hoặc cùng trạng thái lỗi**.

Tuy nhiên, callback observability tự ném exception có thể khiến stage trả về lỗi hoặc ảnh hưởng lỗi theo quy tắc `CompletionStage.whenComplete`. Vì vậy:

1. Log và metrics phải ngắn, thread-safe, an toàn trước lỗi của sink.
2. Không gọi HTTP telemetry đồng bộ hoặc `join` trong callback.
3. Không sửa kết quả nghiệp vụ bằng `whenComplete`; dùng `handle`/`exceptionally` nếu phải thay đổi.
4. Không mặc định callback chạy trên thread request; non-Async action có thể chạy trên thread hoàn tất stage hoặc caller tham gia completion.

### 5.3. Quan sát lỗi trước khi fallback

~~~java
CompletableFuture<String> result = fetchAsync()
        .whenComplete((value, error) -> {
            if (error != null) reportError(error);
        })
        .exceptionally(error -> "fallback");
~~~

Đây là **mảnh code với API ứng dụng giả định**. Lỗi fetch được ghi nhận trước khi `exceptionally` tạo ra **kết quả bình thường thay thế**. Nếu chỉ gắn log sau `exceptionally`, dashboard có thể ghi stage cuối thành công và **không thấy lỗi upstream**.

Một request có fallback thành công thường nên có hai tín hiệu:

- **Upstream failure:** dependency thật sự lỗi.
- **Degraded/recovered result:** caller có thể nhận kết quả thay thế đúng chính sách.

Không báo upstream thành công chỉ vì future cuối không còn exception.

## 6. Đo độ trễ đúng: quan sát completion chứ không log ngẫu nhiên

Có thể đo từ lúc đăng ký stage đến khi hoàn tất:

~~~java
long began = System.nanoTime();

CompletableFuture<T> observed = future.whenComplete(
        (value, error) -> {
            long duration = System.nanoTime() - began;
            recordStageLatency(duration);
        });
~~~

Đây là **mảnh minh họa** có `T`, `future` và `recordStageLatency` do code bao quanh định nghĩa. `System.nanoTime()` thích hợp đo **duration trong một JVM**, không phải timestamp UTC cho log xuyên máy.

Thời lượng đo từ lúc đăng ký có thể bao gồm **queue wait, thời gian chờ dependency và thời gian thực thi**, tùy nguồn future. Nếu cần phân biệt nguyên nhân:

~~~text
time enqueued -> time worker starts -> time I/O ends
       queue wait       execution / I/O
             \              /
               total latency
~~~

Đừng thấy một stage kéo dài 500 ms rồi mặc định CPU xử lý 500 ms. Có thể nó nằm trong queue 450 ms và thực thi 50 ms.

### 6.1. Quan sát phải nhẹ

Nếu pipeline xử lý nhiều request/giây và mỗi request có nhiều stage, gửi log đồng bộ cho từng stage có thể tự tạo nút nghẽn. Sử dụng structured logging, sampling trace, async exporter, giới hạn queue telemetry và cách xử lý khi collector không truy cập được.

Nếu callback metrics vô tình ném lỗi, **tránh để observability phá kết quả nghiệp vụ**. Tùy chính sách, có thể bảo vệ riêng instrumentation hoặc tách cơ chế export ra khỏi đường nóng, đồng thời vẫn ghi nhận tín hiệu exporter bị lỗi.

### 6.2. Tình trạng lỗi phải được phân loại

Đừng chỉ lưu boolean `isCompletedExceptionally()`. Hãy phân biệt:

- `success`: stage hoàn thành bình thường.
- `dependency failure`: một API lỗi thật.
- `timeout`: deadline đã đến, có thể không đồng nghĩa I/O đã dừng.
- `cancelled`: caller không còn cần kết quả.
- `recovered`: fallback biến lỗi thành kết quả đã được chấp nhận.

Một value `null` vẫn có thể là **normal completion**. Trong `whenComplete`, dùng `error == null` để kiểm trạng thái, không dùng `value == null` làm dấu hiệu chắc chắn của lỗi.

## 7. Trace context qua executor và ThreadLocal

MDC/logging context và `ThreadLocal` thường gắn với **thread**. Khi CompletionStage đổi executor hoặc callback chạy ở một thread khác, dữ liệu ThreadLocal **không tự được đảm bảo** lan truyền.

Cách an toàn, rõ nghĩa: truyền một **immutable context** theo chữ ký hàm:

~~~java
record RequestContext(String traceId, String tenantId) {}

CompletionStage<UserView> loadView(
        RequestContext ctx, Executor executor) {
    return fetchAsync(ctx, executor)
            .thenCompose(user ->
                    enrichAsync(ctx, user, executor));
}
~~~

Đây là mảnh minh họa JDK17+, với `UserView` và hàm fetch/enrich do ứng dụng định nghĩa. Nếu dùng OpenTelemetry hay tracing framework, chọn **context propagation API chính thức** của thư viện để capture/restore context khi đi qua executor.

### 7.1. Khi bắt buộc dùng MDC

Quy tắc an toàn:

~~~text
caller captures context
  -> schedule callback with context
  -> worker restores context
  -> execute callback
  -> finally restore previous context / clear
~~~

Executor tái sử dụng thread; nếu quên clear, log request sau có thể bị gắn trace của request trước. Không tự chế global mutable context chung cho mọi request. Tránh giữ nguyên request object nặng trong closure chạy lâu vì dễ tăng memory retention.

### 7.2. Tách dữ liệu nhạy cảm khỏi trace

Trace ID, stage name và error type thường đủ cho correlation. Không ghi toàn bộ User, mật khẩu, token, email hoặc request body vào metric/log. Nếu phải có ID nghiệp vụ, kiểm quyền truy cập và chính sách bảo vệ dữ liệu theo hệ thống.

## 8. Executor: chọn đúng tài nguyên cho đúng công việc

`CompletableFuture.supplyAsync(supplier)` không truyền executor và nhiều overload `Async` mặc định thường dùng `ForkJoinPool.commonPool()` của CompletableFuture cơ bản, với các điều kiện/ngoại lệ được tài liệu hóa. Đây là nơi tiện cho task CPU ngắn nhưng **không mặc định thích hợp cho blocking I/O dài**.

~~~java
ExecutorService ioExecutor =
        Executors.newFixedThreadPool(12);

CompletableFuture<Data> future =
        CompletableFuture.supplyAsync(
                () -> blockingRemoteCall(), ioExecutor);
~~~

Mảnh minh họa với `Data` và `blockingRemoteCall` do ứng dụng định nghĩa. Caller có thể tiếp tục, nhưng **một worker vẫn có thể chờ I/O**. Điều đó khác với HTTP client/driver async thật sự, nơi I/O và completion có thể dùng tài nguyên theo mô hình khác.

### 8.1. Async và non-Async

| Phương thức | Khi nào chạy callback? | Cần lưu ý |
|---|---|---|
| `thenApply(fn)` | Khi stage trước thành công; có thể trên completing thread | Đừng chặn lâu |
| `thenApplyAsync(fn)` | Async facility mặc định | Có thêm scheduling overhead |
| `thenApplyAsync(fn, executor)` | Executor do caller chọn | Có thể dùng tách CPU pool |
| `thenCompose(fn)` | Callback tạo dependent stage | Không cần join con |
| `thenComposeAsync(fn, executor)` | Lên lịch callback tạo stage con | Stage con có cơ chế riêng |
| `whenComplete(fn)` | Khi hoàn tất bình thường/lỗi | Quan sát nhanh, không ném exception |
| `whenCompleteAsync(fn, executor)` | Quan sát thông qua executor | Không dùng pool đã nghẽn cho telemetry quan trọng |

**Async không hứa thread mới.** Executor có thể chạy trên một worker đã tái sử dụng, chờ queue hoặc từ chối task khi quá tải. Vì vậy không viết test yêu cầu callback chạy trên tên thread cụ thể nếu hợp đồng không nói vậy.

### 8.2. Deadlock/starvation do join trong pool nhỏ

Phản ví dụ **không nên chạy**:

~~~java
ExecutorService one = Executors.newSingleThreadExecutor();

CompletableFuture<String> stuck =
        CompletableFuture.supplyAsync(() -> {
            return CompletableFuture.supplyAsync(
                    () -> "ready", one).join();
        }, one);
~~~

Worker duy nhất đang chờ inner future; inner task lại ở queue của chính worker đó. Kết quả có thể **không bao giờ hoàn tất** do tự làm cạn worker. Cách sửa là **ghép bằng thenCompose** và tránh chặn worker, hoặc thiết kế lại nguồn công việc.

### 8.3. Fixed thread pool không tự giải quyết quá tải

`Executors.newFixedThreadPool(n)` thường dùng queue để chứa công việc vượt số worker. Nếu tốc độ yêu cầu lớn hơn tốc độ xử lý, queue và memory có thể tăng. Cần thêm **bounded queue, admission control, bulkhead, rate limit hoặc backpressure** tùy kiến trúc.

`CallerRunsPolicy` có thể chạy task trên chính caller khi pool đầy, là một cách tạo áp lực ngược nhưng cũng có thể **chặn event-loop/request thread**; không chọn ngầm mà chưa phân tích.

Đóng executor theo vòng đời ứng dụng, **không** tạo pool mới cho mỗi request. Nếu đang dùng virtual threads trên JDK21+, đó là một lựa chọn khác cho blocking I/O theo kiến trúc tương ứng, không phải lý do để coi CompletableFuture lỗi thời.

## 9. Xử lý lỗi: whenComplete, handle, exceptionally

| Toán tử | Chạy khi | Có nên thay giá trị? |
|---|---|---|
| `whenComplete((v,e)->...)` | Success và failure | Không, dành cho quan sát |
| `handle((v,e)->newV)` | Success và failure | Có, trả output mới |
| `exceptionally(e->fallback)` | Failure | Có, phục hồi bằng giá trị |
| `exceptionallyCompose(e->otherStage)` | Failure, Java12+ | Có, phục hồi bằng stage bất đồng bộ |
| `thenApply(fn)` | Success | Biến giá trị, không xử lý lỗi upstream |

Lỗi trong `supplyAsync` làm future hoàn thành exceptionally. Callback `thenApply`/`thenCompose` phụ thuộc thành công không chạy khi không có giá trị thành công; lỗi được lan truyền theo contract.

### 9.1. CompletionException và lỗi gốc

`join()` có thể ném unchecked `CompletionException` cho lỗi tính toán; `get()` có thể ném checked `ExecutionException` và `InterruptedException` khi chờ. Caller cần hiểu cause, không kiểm string message để quyết định retry/validation.

~~~java
.exceptionally(error -> {
    Throwable cause = error;
    while (cause instanceof CompletionException
            && cause.getCause() != null) {
        cause = cause.getCause();
    }
    if (cause instanceof KnownMissingDataException) {
        return safeFallback();
    }
    throw new CompletionException(cause);
})
~~~

Đây là **mảnh minh họa**, các kiểu `KnownMissingDataException` và `safeFallback` thuộc ứng dụng. Chính sách đúng: chỉ fallback cho lỗi **được xác định là có thể phục hồi**; đừng nuốt mọi bug, lỗi quyền truy cập hay validation thành thành công giả.

### 9.2. Async fallback không nên join

Không nên:

~~~java
.exceptionally(error -> backupServiceAsync().join())
~~~

Hãy dùng API hiện hành từ Java 12:

~~~java
CompletableFuture<Data> recovered = primaryAsync()
        .exceptionallyCompose(error -> backupServiceAsync());
~~~

Đây là mảnh code với những hàm/kiểu do ứng dụng cung cấp. `exceptionallyCompose` làm phẳng stage fallback như `thenCompose` nhưng dành cho nhánh exception; không giữ worker chờ kết quả.

Khi bắt buộc hỗ trợ Java 8, có thể mô hình hóa async recovery qua `handle` trả stage rồi `thenCompose`. Tuy nhiên nếu dự án đang chạy JDK17+, `exceptionallyCompose` rõ nghĩa và vẫn được hỗ trợ.

### 9.3. Retry cũng là một chuỗi phụ thuộc

~~~java
CompletionStage<Response> result = primaryAsync()
        .exceptionallyCompose(error -> {
            if (isTransient(error)) {
                return secondaryAttemptAsync();
            }
            return CompletableFuture.failedFuture(error);
        });
~~~

Đây là **mảnh Java 17+ minh họa một lần retry**, với các hàm/kiểu được định nghĩa bởi ứng dụng. Trong production, thêm backoff có jitter, số lần thử tối đa, deadline tổng, kiểm idempotency và metric attempt. Không retry mọi exception; đặc biệt API ghi dữ liệu phải có cơ chế tránh ghi trùng.

`CompletableFuture.delayedExecutor(...)` (Java 9+) hoặc scheduler của framework có thể lên lịch retry sau khoảng chờ mà không dùng `Thread.sleep` để chiếm worker.

## 10. Timeout trên stage khác chặn caller chờ timeout

Từ Java 9, CompletableFuture có:

~~~java
CompletableFuture<Response> timed =
        remoteAsync().orTimeout(
                800, TimeUnit.MILLISECONDS);
~~~

`orTimeout` thiết lập future hoàn thành lỗi `TimeoutException` nếu không có kết quả đúng hạn; **trả lại chính CompletableFuture nhận lời gọi**. Nó **không phải** lời gọi chặn caller đợi 800 ms.

~~~java
CompletableFuture<Response> fallback =
        remoteAsync().completeOnTimeout(
                safeDefault(), 800, TimeUnit.MILLISECONDS);
~~~

`completeOnTimeout` hoàn thành **chính future** bằng giá trị mặc định nếu chưa xong. Chỉ dùng khi fallback đáp ứng hợp đồng nghiệp vụ.

**Cảnh báo:** vì hai phương thức thay đổi chính future nhận lời gọi, thêm timeout vào một future dùng chung có thể tác động nhiều consumer khác nhau. Nếu cần chính sách deadline độc lập, tạo dependent stage/copy phù hợp và quản lý ownership rõ ràng.

### 10.1. Timeout không đảm bảo hủy I/O

Future có thể hoàn tất lỗi `TimeoutException`, nhưng request mạng/database bên dưới vẫn chạy và vẫn chiếm worker. Cần timeout ở **client/driver** và deadline ở **pipeline** nếu nhiệm vụ yêu cầu. Nếu một request đã timeout nhưng underlying task vẫn tiếp tục, phải có chính sách xử lý tài nguyên, log late completion và concurrency budget.

Khác với `orTimeout`:

~~~java
Response response = remoteAsync().get(
        800, TimeUnit.MILLISECONDS);
~~~

`get(timeout)` **chặn thread hiện tại** trong khi chờ, rồi ném `TimeoutException` nếu chưa xong. Nó có thể phù hợp ở **ranh giới đồng bộ đã kiểm soát**, nhưng không nên đặt trong request event loop hoặc callback đang cần giữ thông lượng async.

### 10.2. Deadline tổng và timeout từng dependency

Nếu gọi A rồi B rồi C nối tiếp, mỗi bước timeout 2 giây có thể khiến toàn request kéo dài gần 6 giây trước fallback. Nếu SLA tổng là 2 giây, cần có **deadline tổng**, truyền ngân sách còn lại hoặc một stage cuối có chính sách timeout rõ. Kết hợp với driver timeout để hạn chế tài nguyên vẫn chạy sau khi caller bỏ cuộc.

Một `orTimeout` ở stage cuối chỉ đảm bảo outcome của stage ấy đổi khi tới hạn, không thay thế deadline propagation hoặc cleanup phía dưới.

## 11. Cancel không đồng nghĩa interrupt task thực

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
boolean cancelled = pending.cancel(true);
~~~

Với CompletableFuture, `cancel(mayInterruptIfRunning)` khiến future hoàn thành như `CancellationException` nếu hủy thắng cuộc đua completion; tham số `mayInterruptIfRunning` **không có tác dụng điều khiển task** theo tài liệu, vì CompletableFuture không trực tiếp quản lý phép tính làm nó hoàn thành.

Đừng giả định `cancel(true)` làm underlying HTTP call, JDBC query hay tất cả stage upstream bị ngắt. Nếu library có API cancel thật, kết nối request cancellation với API ấy và quản lý cleanup chủ động.

### 11.1. Không tự động hủy các nhánh thua

- Hủy dependent stage không hứa hủy upstream.
- Hủy `allOf` không hứa hủy tất cả futures thành phần.
- `anyOf` hoàn thành không tự cancel những nhánh chưa xong.
- Timeout trên một stage không phải giao thức hủy I/O.

Cần một policy rõ về **ai sở hữu task, khi nào caller không cần kết quả, làm sao ngừng thực thi thật và làm sao không báo success muộn thành success của request đã kết thúc**.

## 12. Chương trình Java hoàn chỉnh: chuỗi không chặn và dễ quan sát

Lưu thành file **`ObservableFutureDemo.java`**, biên dịch với **JDK 17+**. Chương trình chỉ cần JDK, không cần thư viện ngoài. Nó dùng:

1. Hai công việc độc lập: lookup User và lấy plan.
2. `thenCompose` để tạo lời chào khi đã biết user.
3. `thenCombine` để ghép kết quả.
4. Helper `observed` gắn traceId/tên stage, lưu status và latency bằng `ConcurrentHashMap` trong `whenComplete`.
5. Một nhánh lỗi được ghi nhận trước khi `exceptionally` trả fallback.
6. `join()` chỉ tại **outer CLI boundary** để in ra stdout; không gọi join bên trong stage.
7. Đóng executor khi xong, tránh rò worker.

~~~java
import java.util.*;
import java.util.concurrent.*;

public class ObservableFutureDemo {
    record Request(String traceId, int userId) {}
    record User(int id, String name) {}

    private static final Map<String, String> status =
            new ConcurrentHashMap<>();
    private static final Map<String, Long> latencyNanos =
            new ConcurrentHashMap<>();

    private static <T> CompletableFuture<T> observed(
            String traceId, String stage, CompletableFuture<T> future) {
        long startedAt = System.nanoTime();
        return future.whenComplete((value, error) -> {
            long duration = Math.max(0L,
                    System.nanoTime() - startedAt);
            String key = traceId + "/" + stage;
            status.put(key, error == null ? "ok" : "failed");
            latencyNanos.put(key, duration);
        });
    }

    private static CompletableFuture<User> findUser(
            int id, Executor executor) {
        return CompletableFuture.supplyAsync(() -> {
            if (id < 0) {
                throw new IllegalArgumentException("invalid user id");
            }
            return new User(id, "Lan");
        }, executor);
    }

    private static CompletableFuture<String> greeting(
            User user, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> "Hello " + user.name(), executor);
    }

    private static CompletableFuture<String> plan(Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> "basic", executor);
    }

    private static CompletableFuture<String> run(
            Request request, Executor executor) {
        CompletableFuture<User> user =
                observed(request.traceId(), "lookup",
                        findUser(request.userId(), executor));

        CompletableFuture<String> hello = user.thenCompose(
                u -> observed(request.traceId(), "greeting",
                        greeting(u, executor)));

        CompletableFuture<String> servicePlan =
                observed(request.traceId(), "plan", plan(executor));

        CompletableFuture<String> combined =
                observed(request.traceId(), "combine",
                        hello.thenCombine(servicePlan,
                                (h, p) -> h + " / " + p));

        return observed(request.traceId(), "result",
                combined.thenApply(String::toUpperCase));
    }

    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            Request request = new Request("REQ-42", 42);
            CompletableFuture<String> good = run(request, executor);

            CompletableFuture<String> bad =
                    observed("REQ-FAIL", "lookup",
                            findUser(-1, executor))
                    .thenCompose(user -> greeting(user, executor))
                    .whenComplete((value, error) ->
                            status.put("REQ-FAIL/pipeline",
                                    error == null ? "ok" : "failed"))
                    .exceptionally(error -> {
                        status.put("REQ-FAIL/recovery", "used");
                        return "UNAVAILABLE";
                    });

            System.out.println("Success: " + good.join());
            System.out.println("Stages: "
                    + String.join(", ",
                            "lookup=" + status.get("REQ-42/lookup"),
                            "greeting=" + status.get("REQ-42/greeting"),
                            "plan=" + status.get("REQ-42/plan"),
                            "combine=" + status.get("REQ-42/combine"),
                            "result=" + status.get("REQ-42/result")));
            System.out.println("Failure fallback: " + bad.join());
            System.out.println("Failure observed: "
                    + status.get("REQ-FAIL/pipeline"));
            System.out.println("Recovery used: "
                    + status.get("REQ-FAIL/recovery"));

            CompletableFuture<String> ready =
                    CompletableFuture.completedFuture("READY");
            System.out.println("Completed future: " + ready.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ObservableFutureDemo.java
java ObservableFutureDemo
~~~

Stdout đã được xác minh:

~~~text
Success: HELLO LAN / BASIC
Stages: lookup=ok, greeting=ok, plan=ok, combine=ok, result=ok
Failure fallback: UNAVAILABLE
Failure observed: failed
Recovery used: used
Completed future: READY
~~~

### 12.1. Giải thích các dòng

- `Success: HELLO LAN / BASIC`: lookup và plan đã ghép thành công, sau đó format.
- `Stages: lookup=ok, greeting=ok, plan=ok, combine=ok, result=ok`: các stage đều được ghi trạng thái. Không suy ra **thứ tự chạy thread** từ thứ tự text, vì text được in sau future hoàn thành.
- `Failure fallback: UNAVAILABLE`: kết quả thay thế chỉ áp dụng ở nhánh thử lỗi.
- `Failure observed: failed`: pipeline trước fallback đã ghi lỗi.
- `Recovery used: used`: một metric riêng giúp phân biệt phục hồi với không có lỗi.
- `Completed future: READY`: khi đã có dữ liệu thì có thể trả completedFuture, không cần tạo thread vô ích.

`latencyNanos` được ghi nhưng không in: con số thời gian thực tế không ổn định giữa CPU, số worker và scheduler, không nên đưa vào expected stdout. Trong production, xuất nó dưới dạng histogram với đơn vị rõ ràng và kiểm cardinality.

### 12.2. Điều kiện trước và sau whenComplete

`whenComplete` trả stage phụ thuộc và callback phải hoàn tất trước stage mới được coi là hoàn thành. Trong ví dụ, helper chỉ cập nhật map thread-safe, không ném lỗi và không gửi telemetry đồng bộ; vì vậy status/latency của các stage dẫn đến result đã được đặt khi `good.join()` trả. Điều đó **không** có nghĩa một dịch vụ xuất telemetry bên ngoài đã flush xong — nếu export async, cần lifecycle và shutdown policy riêng.

### 12.3. Lỗi thử nghiệm được xử lý thế nào?

`findUser(-1, executor)` chủ ý ném `IllegalArgumentException`. `thenCompose` phụ thuộc thành công không chạy greeting; `whenComplete` ghi `failed`, rồi `exceptionally` trả `UNAVAILABLE`. Trong sản phẩm thật, fallback cho ID âm có thể **không phải chính sách hợp lý**; demo chỉ nhằm thể hiện thứ tự quan sát và phục hồi. Đừng dùng `exceptionally` bắt mọi lỗi rồi trả thành công không điều kiện.

## 13. Test completion semantics thay vì dùng Thread.sleep

| Ca kiểm thử | Điều cần kiểm |
|---|---|
| `thenApply` sau source thành công | Biến đổi giá trị đúng |
| `thenCompose` với stage con chưa xong | Future cuối vẫn pending |
| `thenCombine` với hai source độc lập | Chỉ trả result khi cả hai thành công |
| Một source lỗi | Dependent stage nhận exceptional completion |
| `whenComplete` không ném lỗi | Giữ nguyên success/failure, đồng thời ghi metric |
| `exceptionally` | Chỉ phục hồi ở nhánh lỗi |
| Fallback xảy ra | Upstream failure metric vẫn được ghi |
| `orTimeout` | Future có outcome timeout phù hợp |
| `completeOnTimeout` | Trả giá trị mặc định khi chưa xong |
| `cancel` | Hủy future, không tự suy ra worker bị interrupt |
| Trace ID qua nhiều executor | Không lẫn ID giữa request |
| Pool bão hòa | Chính sách reject/backpressure rõ |
| Shutdown | Không rò executor/client |
| Retry | Tối đa số lần định trước, không retry lỗi vĩnh viễn |

### 13.1. Test thenCompose bằng future được điều khiển

~~~java
CompletableFuture<String> outer = new CompletableFuture<>();
CompletableFuture<String> inner = new CompletableFuture<>();

CompletableFuture<String> flat =
        outer.thenCompose(value -> inner);

outer.complete("ready");

if (flat.isDone()) {
    throw new AssertionError("Inner stage not complete");
}

inner.complete("done");

if (!"done".equals(flat.join())) {
    throw new AssertionError("Unexpected result");
}
~~~

Đây là đoạn Java chạy trong một phương thức với `import java.util.concurrent.*;`. Nó kiểm **quan hệ hoàn tất** mà không cần sleep hay đoán thời gian scheduler. `join` ở đây là assertion trên future đã được hoàn thành thủ công, không phải blocker nghiệp vụ ở giữa pipeline.

### 13.2. Test lỗi xác định

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> recovered =
        source.exceptionally(error -> "fallback");

source.completeExceptionally(
        new IllegalStateException("expected"));

if (!"fallback".equals(recovered.join())) {
    throw new AssertionError("Wrong recovery");
}
~~~

Test này không cần chạy backend thật hoặc đợi timeout; nó làm rõ nhánh exceptional. Với test timeout, nên dùng scheduler/clock có thể điều khiển hoặc test integration có thời hạn được cấu hình, thay vì viết `Thread.sleep(1000)` rồi trông đợi CI luôn xử lý đúng thời điểm.

### 13.3. Test không nên kiểm điều gì?

Không hardcode tên thread của callback thường, không bắt hai nhánh độc lập hoàn thành đúng một thứ tự, không dựa vào log tiếng Anh của exception JDK, và không assert latency nano chính xác. Chỉ assert **giá trị, trạng thái, trace ID, số lần fallback và bất biến tài nguyên** đã được đặc tả.

## 14. Thiết kế API service và ranh giới chờ

Một API dịch vụ có thể dùng:

~~~java
interface ProfileService {
    CompletionStage<UserView> loadView(
            String userId, RequestContext context);
}
~~~

Mảnh interface minh họa với các kiểu ứng dụng. Lợi ích của việc **trả CompletionStage cuối** là tầng gọi có thể tiếp tục chain hoặc đưa stage vào HTTP framework hỗ trợ xử lý bất đồng bộ.

Nếu framework hỗ trợ `CompletionStage<Response>`, handler nên làm tương tự:

~~~java
return service.loadView(id, context)
        .thenApply(this::mapResponse);
~~~

Đây là ví dụ trong một method controller có `service`, `mapResponse` và các biến đã được cung cấp. Không thay bằng `return service.loadView(...).toCompletableFuture().join()` trên request/event-loop thread.

### 14.1. Khi nào join/get là chấp nhận được?

- **CLI** cần in kết quả cuối và chờ hoàn tất trước khi thoát.
- **Adapter đồng bộ** không có cách biểu diễn kết quả future, được chạy ở thread/pool có thể chờ và có timeout.
- **Unit test** đồng bộ đã kiểm soát completion của source.
- **Sau allOf thành công**, join trên các future đã hoàn thành chỉ để đọc value (không còn wait), dù thenCombine thường dễ hiểu hơn.

Không chặn trong `thenApply`/`whenComplete` hoặc event loop nếu có lựa chọn chain không chặn. Cụm từ “không bao giờ dùng join” là quá cực đoan; đúng hơn là **không giữ thread chờ một future chưa hoàn tất khi có thể diễn đạt bằng quan hệ phụ thuộc**.

### 14.2. Future chưa đủ cho streaming có backpressure

`CompletableFuture` phù hợp một **kết quả cuối cùng** hoặc đồ thị kết quả hữu hạn. Với nhiều phần tử liên tục và nhu cầu backpressure, xem xét `Flow.Publisher` hoặc thư viện reactive thích hợp. Java 21+ có virtual threads như một lựa chọn kiến trúc cho blocking I/O; nó không làm CompletableFuture trở nên lỗi thời. Chọn mô hình theo thư viện I/O, độ phức tạp, tài nguyên và khả năng vận hành.

## 15. Checklist review một chuỗi bất đồng bộ

Trước khi merge, đặt câu hỏi:

1. Phương thức public có trả **stage thực sự đại diện công việc cuối** không?
2. Có `join`, `get` hoặc `Thread.sleep` nằm trong callback/stage không?
3. Các công việc độc lập có được khởi tạo trước rồi ghép không?
4. Có dùng `thenCompose` khi callback trả CompletionStage không?
5. Có stage fire-and-forget thực chất là bắt buộc phải xong trước success không?
6. Có traceId/correlation ID và tên stage ổn định không?
7. `whenComplete` có làm I/O blocking hoặc ném lỗi ngoài ý muốn không?
8. Lỗi upstream có được quan sát trước fallback không?
9. Fallback có thực sự an toàn cho loại lỗi đã xảy ra không?
10. Timeout là deadline tổng hay chỉ từng dependency, và I/O bên dưới có timeout riêng không?
11. Cancellation có được nối tới underlying request cần hủy thật không?
12. Executor có đủ cách ly và giới hạn queue/in-flight không?
13. Có loại bỏ thông tin nhạy cảm khỏi log, và metric label có cardinality hợp lý không?
14. Có giới hạn retry, backoff/jitter và idempotency nếu ghi dữ liệu không?
15. Test có bao phủ success/error/timeout/cancel và shutdown không?

Một review tốt nhìn thấy **đồ thị phụ thuộc lẫn đồ thị lỗi**, không chỉ quan tâm chuỗi cuối trả giá trị đúng trên đường happy path.

## 16. Các lỗi phổ biến và cách sửa

**Lỗi 1 — `thenApply(...join())`:** giữ worker đợi stage con; chuyển sang `thenCompose`.

**Lỗi 2 — `thenApply` trả future lồng:** output là future chứa future, chưa chờ công việc con; dùng `thenCompose` để flatten.

**Lỗi 3 — Chạy tuần tự các task độc lập:** join sau task thứ nhất mới gọi task thứ hai; khởi tạo cả hai rồi `thenCombine`.

**Lỗi 4 — Dùng `Async` ở mọi callback:** thêm overhead và làm khó theo dõi executor; chỉ dùng khi có lý do scheduling.

**Lỗi 5 — Nghĩ callback luôn chạy trên request thread:** thread thực thi phụ thuộc cách stage hoàn thành và executor.

**Lỗi 6 — Đưa I/O blocking vào commonPool:** có thể gây starvation; chọn thư viện I/O async hoặc executor riêng có ngân sách.

**Lỗi 7 — Coi `supplyAsync` bao toàn bộ I/O là nonblocking:** caller không chờ nhưng worker vẫn có thể bị chặn.

**Lỗi 8 — Tạo future không ai complete:** request treo; bridge callback cần đường success, error, timeout và hủy.

**Lỗi 9 — Chỉ log sau fallback:** upstream failure bị che; log/metric lỗi trước `exceptionally`.

**Lỗi 10 — Dùng `whenComplete` để đổi giá trị:** đây là hook quan sát; dùng `handle` hoặc `exceptionally` cho transformation/recovery.

**Lỗi 11 — Để telemetry ném exception:** kết quả nghiệp vụ có thể bị ảnh hưởng; xây observability nhẹ và an toàn.

**Lỗi 12 — Dùng `value == null` để xác định lỗi:** normal completion có thể có null; dùng error.

**Lỗi 13 — Không propagate context:** log các thread không thể nối với cùng request; truyền context hoặc dùng propagator.

**Lỗi 14 — Dùng từng traceId làm metric label:** time-series bùng nổ cardinality; traceId ở log/trace.

**Lỗi 15 — Dùng `nanoTime` làm timestamp UTC:** nó chỉ thích hợp tính khoảng thời gian tương đối trong JVM.

**Lỗi 16 — Coi `orTimeout` là hủy I/O:** timeout chỉ thay outcome của future, không chắc dừng underlying operation.

**Lỗi 17 — Dùng `orTimeout` trên shared future mà không xét ownership:** có thể thay kết quả của các consumer khác vì mutate chính future.

**Lỗi 18 — Dùng `cancel(true)` như lệnh interrupt chắc chắn:** CompletableFuture không trực tiếp quản lý tác vụ.

**Lỗi 19 — `anyOf` tưởng là success đầu tiên:** thực tế là completion đầu tiên, kể cả lỗi.

**Lỗi 20 — Retry vô hạn:** có thể đè dependency; giới hạn, backoff, deadline và idempotency.

**Lỗi 21 — Pool cố định nhưng queue vô hạn:** quá tải vẫn tăng memory; cần bounded concurrency/backpressure.

**Lỗi 22 — Không đóng executor và client:** leak tài nguyên, CLI/test có thể không kết thúc.

**Lỗi 23 — Test thứ tự thread và nano chính xác:** scheduling không phải contract; test kết quả và completion.

**Lỗi 24 — Gọi `get(timeout)` trong event loop:** nó vẫn chặn caller; dùng async deadline/return stage.

## 17. Bài tập tự luyện

1. Vì sao `thenApply(user -> fetchAsync(user).join())` là anti-pattern? Viết lại bằng `thenCompose`.
2. Khi callback trả `CompletableFuture<Details>`, `thenApply` tạo kiểu nested gì?
3. Hai nguồn user và plan độc lập: dùng phép nào để ghép mà không gọi join?
4. Khi source lỗi, callback `thenApply` phụ thuộc thành công có chạy không?
5. Vì sao `whenComplete` nên được đặt trước `exceptionally` khi cần metric lỗi upstream?
6. `whenComplete` có thể làm dependent stage lỗi mới khi nào?
7. Tại sao ThreadLocal/MDC không tự được bảo đảm qua các executor?
8. `supplyAsync(() -> blockingDbCall())` có thật sự làm worker không chặn I/O?
9. `thenApplyAsync` có tạo một thread mới riêng cho mỗi callback không?
10. Phân biệt `orTimeout` và `get(timeout)` về hành vi chặn.
11. `orTimeout` có bảo đảm underlying HTTP request bị hủy không?
12. `cancel(true)` có đảm bảo interrupt worker của CompletableFuture không?
13. `allOf` có trả List kết quả không?
14. `anyOf` có bảo đảm kết quả thành công đầu tiên không?
15. Khi nào `join` là chấp nhận được?
16. Dashboard nên biểu diễn thế nào một dependency lỗi nhưng fallback đã phục hồi?
17. Vì sao API ghi dữ liệu cần idempotency khi retry?
18. Queue của pool lớn dần phải bổ sung cơ chế tài nguyên gì?
19. Vì sao không dùng traceId làm nhãn metric?
20. Nếu auditAsync trả CompletionStage và bắt buộc thành công trước response, cần ghép thế nào?

**Gợi ý đáp án:** (1) Giữ worker chờ, dùng `thenCompose(user -> fetchAsync(user))`. (2) `CompletableFuture<CompletableFuture<Details>>`. (3) `thenCombine`. (4) Không. (5) Để ghi failure trước khi fallback làm output normal. (6) Khi callback quan sát tự ném exception. (7) ThreadLocal theo thread, không theo request. (8) Không, worker vẫn có thể chặn. (9) Không, executor tái sử dụng worker. (10) `get(timeout)` chặn, `orTimeout` thay completion theo deadline. (11) Không. (12) Không. (13) Không, `CompletableFuture<Void>`. (14) Không, completion đầu tiên có thể lỗi. (15) Ranh giới đồng bộ như CLI/test đã kiểm soát. (16) Upstream failure + recovery/degraded metric riêng. (17) Tránh ghi trùng. (18) Bound queue, admission control, backpressure. (19) Cardinality quá cao. (20) `thenCompose(result -> auditAsync(result))`.

## Tổng kết

`CompletableFuture` mô tả các **quan hệ hoàn tất**. Giữ pipeline không chặn vô ích bằng `thenCompose` cho tác vụ async phụ thuộc, `thenCombine` cho tác vụ độc lập, và **trả stage cuối** đến tầng async thay vì gọi `join` giữa chuỗi. Gắn `whenComplete` để quan sát success/error, giữ trace context tường minh, phân biệt lỗi thật với fallback, theo dõi latency và tài nguyên executor. Timeout và cancel trên CompletableFuture **không tự dừng I/O**; retry cần hạn mức và deadline. Cách thiết kế này giúp pipeline vừa đúng về ngữ nghĩa, vừa dễ chẩn đoán, đồng thời tránh giữ thread chỉ để đợi một kết quả đã được biểu diễn bằng future.

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 27 — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 27 — CompletionStage](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 27 — ForkJoinPool](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Oracle Java SE 27 — TimeUnit](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html)
- [Oracle Java SE 27 — java.util.concurrent](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/package-summary.html)
