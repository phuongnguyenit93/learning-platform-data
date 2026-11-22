# Ngăn lộ dữ liệu nhạy cảm qua context, log và task chạy nền

Context giúp truyền các thông tin cần thiết trong quá trình xử lý một request, chẳng hạn correlation ID, tenant đã được xác thực hoặc tên operation. Nhưng context cũng có thể trở thành đường rò rỉ dữ liệu nếu chứa access token, mật khẩu, session secret hoặc thông tin cá nhân rồi bị sao chép sang thread khác, task chạy nền hay log.

Trong Java 21, `ThreadLocal` và `InheritableThreadLocal` vẫn là API hiện hành, nhưng cần quản lý vòng đời và phạm vi dữ liệu rõ ràng. Với task chạy trên thread pool, phải đặt context trước khi chạy và xóa/khôi phục trong `finally`. Với virtual thread, cần chú ý `InheritableThreadLocal`: virtual thread mới mặc định có thể kế thừa giá trị từ thread tạo nó. Nguyên tắc an toàn là chỉ truyền context tối thiểu, bất biến và đã được cho phép; xác thực quyền truy cập lại ở nơi thực thi; log theo allowlist và không ghi secret.

## 1. Phân biệt context nghiệp vụ, context chẩn đoán và secret

Không phải mọi thông tin gắn với request đều nên được truyền cùng nhau. Hãy tách chúng theo mục đích:

| Nhóm dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Context chẩn đoán | Trace ID, correlation ID, operation name | Có thể truyền qua task và ghi log sau khi kiểm tra định dạng |
| Context định tuyến | Tenant reference, locale, vùng xử lý | Chỉ truyền khi task cần; kiểm tra lại quyền và phạm vi tenant ở nơi thực thi |
| Danh tính đã xác thực | Principal ID hoặc thông tin vai trò | Dùng cơ chế bảo mật của ứng dụng/framework; không xem context thread là bằng chứng xác thực |
| Secret xác thực | Password, bearer token, API key, cookie, session secret | Không đưa vào log hoặc context chung; lấy từ credential provider khi cần và giữ trong phạm vi nhỏ nhất |
| Dữ liệu cá nhân/nhạy cảm | Email, số điện thoại, địa chỉ, dữ liệu tài chính hoặc sức khỏe | Chỉ truyền khi thật sự cần và có căn cứ; tránh đưa vào tên thread, trace tag hoặc log |

Context chẩn đoán nên chứa những giá trị không cấp quyền truy cập. Một trace ID giúp liên kết log nhưng không được dùng như credential. Tương tự, `tenantId` trong ThreadLocal không tự chứng minh caller có quyền truy cập tenant đó; quyền phải được kiểm tra ở ranh giới nghiệp vụ hoặc data access.

Ví dụ định nghĩa một context tối thiểu, bất biến:

```java
record RequestContext(String traceId, String operation, String tenantRef) { }
```

Không thêm access token, password hoặc toàn bộ HTTP header vào record này. Record tự sinh `toString()` có thể đưa mọi component vào chuỗi; vì vậy, ngay cả context không chứa secret cũng nên được log theo từng trường được cho phép thay vì log toàn bộ object.

## 2. ThreadLocal không tự truyền context qua mọi executor

`ThreadLocal<T>` lưu một giá trị riêng theo từng thread. Khi thread A đặt context, thread B không tự nhìn thấy giá trị đó. Khi task được gửi vào một executor, task có thể chạy trên worker đã tồn tại từ trước; context của thread gửi task không tự động chuyển sang worker.

```java
static final ThreadLocal<RequestContext> CURRENT_CONTEXT = new ThreadLocal<>();

static void handleRequest(RequestContext context, ExecutorService executor) {
    CURRENT_CONTEXT.set(context);

    executor.submit(() -> {
        // Không được giả định worker nhìn thấy CURRENT_CONTEXT của caller.
        RequestContext current = CURRENT_CONTEXT.get();
        process(current);
    });
}
```

Đoạn code trên có hai vấn đề: context không được truyền một cách có chủ đích và thread xử lý request không xóa context sau khi hoàn tất. Nếu thread đó được tái sử dụng, dữ liệu cũ có thể còn tồn tại khi xử lý request tiếp theo.

Không nên dựa vào việc executor tình cờ tạo worker mới để context được kế thừa. Worker có thể được tạo trước request, tồn tại lâu và phục vụ nhiều task khác nhau.

## 3. Xóa hoặc khôi phục ThreadLocal trong finally

Với thread pool dùng lại worker, mỗi task phải kết thúc trong trạng thái context sạch. Nếu task lồng nhau có thể thay đổi context tạm thời, hãy lưu giá trị cũ và khôi phục sau khi task kết thúc:

```java
static final ThreadLocal<RequestContext> CURRENT_CONTEXT = new ThreadLocal<>();

static void runWithContext(RequestContext next, Runnable task) {
    RequestContext previous = CURRENT_CONTEXT.get();

    try {
        if (next == null) {
            CURRENT_CONTEXT.remove();
        } else {
            CURRENT_CONTEXT.set(next);
        }

        task.run();
    } finally {
        if (previous == null) {
            CURRENT_CONTEXT.remove();
        } else {
            CURRENT_CONTEXT.set(previous);
        }
    }
}
```

Nếu không cần hỗ trợ context lồng nhau, một task có thể đặt context rồi luôn gọi `remove()` trong `finally`:

```java
static void handle(RequestContext context) {
    CURRENT_CONTEXT.set(context);
    try {
        processRequest();
    } finally {
        CURRENT_CONTEXT.remove();
    }
}
```

Ưu tiên `remove()` khi kết thúc phạm vi. `set(null)` chỉ đặt giá trị thành null; nó không diễn đạt rõ ý định loại bỏ entry khỏi ThreadLocal map như `remove()`.

Không chỉ xóa context ở nhánh thành công. `finally` phải bao phủ cả return, exception và cancellation khiến task thực sự thoát khỏi phần xử lý. Nếu task bị interrupt nhưng code bắt rồi bỏ qua và tiếp tục chạy, `finally` chưa được thực thi cho đến khi task rời khỏi phạm vi đó.

## 4. Truyền context tường minh khi submit task

Khi task cần một phần context của caller, hãy chụp một snapshot tối thiểu tại thời điểm submit và cài đặt snapshot trong phạm vi task. Không sao chép toàn bộ ThreadLocal map hoặc mọi thông tin có trong request.

```java
static Runnable contextual(Runnable task) {
    RequestContext captured = CURRENT_CONTEXT.get();

    return () -> runWithContext(captured, task);
}

static void submitAudit(ExecutorService executor) {
    executor.submit(contextual(() -> {
        RequestContext context = CURRENT_CONTEXT.get();
        writeAuditRecord(context.traceId(), context.operation());
    }));
}
```

Wrapper đảm bảo task chạy với snapshot đã chụp, rồi khôi phục context trước đó của worker. Nếu snapshot là null, `runWithContext` xóa context hiện có trong lúc chạy task; điều này tránh task vô tình sử dụng context còn sót lại từ công việc trước.

Một cách khác là truyền context như tham số thông thường:

```java
RequestContext context = CURRENT_CONTEXT.get();
executor.submit(() -> writeAuditRecord(context));
```

Truyền tham số tường minh thường dễ kiểm tra và dễ test hơn ThreadLocal. Chỉ dùng ThreadLocal khi cần tích hợp với API/framework lấy context ngầm qua thread hiện tại. Dù chọn cách nào, snapshot phải bất biến hoặc được sao chép an toàn; không truyền một `Map` mutable rồi để nhiều task cùng thay đổi.

## 5. InheritableThreadLocal và nguy cơ kế thừa dữ liệu

`InheritableThreadLocal<T>` cho phép thread con kế thừa giá trị từ thread tạo nó. Mặc định, `childValue()` trả lại cùng tham chiếu object của thread cha; nó không tự tạo bản sao sâu. Nếu giá trị là object mutable, thread cha và thread con có thể cùng tham chiếu và thay đổi một object.

Điểm quan trọng là kế thừa xảy ra khi thread được tạo, không phải mỗi lần task được submit vào một worker có sẵn. Với thread pool, điều này có thể dẫn đến hai vấn đề:

- Worker được tạo trong lúc một request có context, giữ giá trị kế thừa đó và tiếp tục tồn tại sau khi request kết thúc.
- Task tiếp theo chạy trên worker có thể nhìn thấy context của thời điểm worker được tạo thay vì context của request submit task hiện tại.

Ví dụ không nên dùng để truyền credential:

```java
static final InheritableThreadLocal<String> AUTH_TOKEN =
        new InheritableThreadLocal<>();
```

Không đặt bearer token, session secret hoặc principal có quyền rộng vào `InheritableThreadLocal` với kỳ vọng nó sẽ tự đồng bộ đúng theo vòng đời task. Cơ chế này không phải context propagation framework và không thực hiện kiểm tra quyền.

## 6. Virtual thread cũng có thể kế thừa InheritableThreadLocal

Virtual thread là thread riêng, không dùng lại như worker platform thread theo mô hình pool truyền thống. Điều này giảm một số nguy cơ rò context do tái sử dụng worker, nhưng không loại bỏ việc context được kế thừa hoặc giữ trong suốt vòng đời virtual thread.

Trong Java 21, builder của thread cho phép bật/tắt việc kế thừa `InheritableThreadLocal`. Mặc định, thread mới kế thừa các giá trị inheritable từ thread tạo nó. Nếu task không cần cơ chế này, có thể tắt khi tạo thread factory:

```java
ThreadFactory factory = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .name("background-", 0)
        .factory();

try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
    executor.submit(this::runBackgroundJob);
}
```

`newThreadPerTaskExecutor(factory)` tạo thread bằng factory đã cấu hình. Với builder trên, virtual thread mới không kế thừa `InheritableThreadLocal` từ thread submit task. Nếu ứng dụng cần truyền trace ID hoặc tenant reference, hãy truyền snapshot đã allowlist bằng tham số hoặc wrapper rõ ràng.

Tắt inheritance không xóa `ThreadLocal` mà task tự đặt, cũng không thay thế cleanup. Nếu task tự gọi `CURRENT_CONTEXT.set(...)`, vẫn phải gọi `remove()` hoặc khôi phục context trong `finally`.

Virtual thread có thể được tạo với số lượng lớn. Đặt object lớn hoặc dữ liệu nhạy cảm vào ThreadLocal trên từng virtual thread có thể làm tăng bộ nhớ và kéo dài thời gian giữ dữ liệu. Chỉ lưu giá trị nhỏ, cần thiết và giới hạn vòng đời của nó.

## 7. Giữ secret ngoài context chung và chỉ lấy khi cần

Nếu một task cần credential để gọi dịch vụ, không chụp token vào context chẩn đoán rồi truyền qua nhiều lớp. Hãy lấy credential từ cơ chế quản lý secret hoặc credential provider tại ranh giới cần sử dụng, giới hạn phạm vi tham chiếu và không log giá trị đó.

```java
static Result callPartner(RequestContext context,
                          CredentialProvider credentials) throws IOException {
    String token = credentials.currentAccessToken();

    return partnerClient.call(
            token,
            context.tenantRef(),
            context.traceId()
    );
}
```

Ví dụ trên chỉ minh họa việc lấy credential ở đúng nơi cần dùng và không đưa token vào context/log. `String` là immutable; bỏ tham chiếu hoặc gán biến về null không xóa nội dung khỏi bộ nhớ và không phải biện pháp zeroization. Hãy dùng thư viện quản lý credential phù hợp; tránh tự triển khai cơ chế xóa secret trong heap nếu chưa có yêu cầu và thiết kế chuyên biệt.

Với task chạy nền, credential có thể hết hạn hoặc bị thu hồi trước thời điểm task thực thi. Không nên dùng một token đã capture từ request ban đầu nếu chính sách yêu cầu xác thực lại. Task cần kiểm tra danh tính/quyền hiện hành hoặc dùng service identity có phạm vi và thời hạn được kiểm soát.

## 8. Log theo allowlist, không serialize toàn bộ context

Log là một nơi rò rỉ dữ liệu phổ biến vì có thể được gửi đến nhiều hệ thống, lưu lâu hơn dữ liệu nghiệp vụ và được nhiều người truy cập. Chỉ ghi những trường đã được phê duyệt cho mục đích vận hành:

- Correlation ID hoặc trace ID đã được xác thực định dạng.
- Tên operation hoặc loại sự kiện không chứa dữ liệu người dùng.
- Kết quả tổng quát, mã lỗi nội bộ hoặc trạng thái thành công/thất bại.
- Tenant reference dạng giả danh nếu thực sự cần để điều tra.

Không ghi:

- Password, access token, refresh token, API key, private key hoặc cookie.
- Authorization header, session secret hoặc toàn bộ request/response body.
- Thông tin thanh toán, dữ liệu cá nhân hoặc dữ liệu sức khỏe nếu không có nhu cầu và chính sách rõ ràng.
- Toàn bộ object context, principal hoặc exception message chưa được kiểm soát.

Ví dụ dùng `System.Logger` với các trường được chọn:

```java
private static final System.Logger LOG =
        System.getLogger(OrderService.class.getName());

static void logOrderResult(RequestContext context, String outcome) {
    LOG.log(System.Logger.Level.INFO,
            "traceId={0} operation={1} outcome={2}",
            context.traceId(), context.operation(), outcome);
}
```

Không viết `LOG.log(INFO, "context=" + context)` nếu context có thể được mở rộng về sau bằng trường nhạy cảm. Hãy giữ allowlist ở từng điểm log để thay đổi model không vô tình làm thay đổi dữ liệu được ghi.

### Làm sạch dữ liệu đầu vào trước khi ghi log

Nếu log một giá trị do người dùng hoặc hệ thống bên ngoài cung cấp, cần kiểm soát ký tự xuống dòng và ký tự điều khiển để tránh log injection. Cũng nên giới hạn độ dài để tránh một trường đầu vào rất lớn làm tăng chi phí lưu trữ.

```java
static String safeLogValue(String value) {
    if (value == null) {
        return "<none>";
    }

    String singleLine = value.replaceAll("[\\r\\n\\p{Cntrl}]", "_");
    return singleLine.length() <= 120
            ? singleLine
            : singleLine.substring(0, 120);
}
```

Làm sạch chuỗi không biến dữ liệu nhạy cảm thành dữ liệu an toàn để log. Trước hết phải quyết định trường đó có được phép ghi hay không; chỉ sau đó mới chuẩn hóa định dạng.

## 9. MDC và context của logging framework

Một số logging framework cung cấp Mapped Diagnostic Context (MDC) để gắn trace ID, tenant reference hoặc operation vào log mà không phải truyền từng tham số đến mọi lời gọi logger. MDC thường dựa trên ThreadLocal hoặc cơ chế context riêng của framework.

Không giả định MDC tự truyền đúng qua mọi executor hoặc mọi virtual thread. Hành vi phụ thuộc framework và phiên bản. Khi dùng MDC:

1. Chỉ đặt các trường đã được allowlist.
2. Capture snapshot khi submit task nếu framework hỗ trợ context propagation.
3. Cài snapshot ở đầu task và clear/restore trong `finally`.
4. Kiểm tra tài liệu của framework cho virtual thread, executor và structured task.
5. Không đưa token hoặc toàn bộ principal vào MDC.

Nếu dùng thư viện context-propagation, hãy cấu hình rõ những context accessor được phép truyền. Không bật truyền tất cả ThreadLocal theo mặc định trong một ứng dụng có nhiều loại dữ liệu.

## 10. Task chạy nền cần context tối thiểu và quyền được kiểm tra lại

Task chạy nền có thể bắt đầu sau khi request ban đầu đã kết thúc. Trong khoảng thời gian đó, user có thể bị khóa, quyền có thể thay đổi, tenant có thể bị vô hiệu hóa hoặc token có thể hết hạn.

Vì vậy, context nền nên chứa dữ liệu định danh công việc và dữ liệu chẩn đoán tối thiểu:

```java
record BackgroundJobContext(
        String jobId,
        String traceId,
        String tenantRef,
        String operation
) { }
```

Khi worker thực thi, tải dữ liệu cần thiết từ kho dữ liệu và kiểm tra quyền hiện hành theo chính sách. Không coi `tenantRef` hoặc `userId` được capture lúc submit là bằng chứng caller vẫn có quyền. Với công việc được ủy quyền, lưu thông tin audit về ai yêu cầu, lúc nào và phạm vi được phê duyệt; dùng service identity có quyền tối thiểu để thực thi.

Không lưu token thô vào queue, database job record, serialized context hoặc message broker. Nếu cần tiếp tục một workflow sau thời gian dài, hãy lưu một tham chiếu an toàn tới credential/authorization policy hoặc yêu cầu hệ thống xác thực lại khi chạy.

## 11. Cleanup khi task lỗi, timeout hoặc bị hủy

Context phải được dọn dẹp giống như stream và connection. Một task nên cài context ở đầu, thực hiện công việc trong phạm vi hẹp và xóa/khôi phục trong `finally`:

```java
static Future<?> submitWithContext(
        ExecutorService executor,
        Runnable task) {

    RequestContext captured = CURRENT_CONTEXT.get();
    return executor.submit(() -> runWithContext(captured, task));
}
```

Nếu task ném exception, `finally` vẫn chạy khi stack unwinds. Nếu task bị interrupt và code thoát đúng cách, context cũng được dọn. Nếu task bắt interrupt rồi tiếp tục chạy hoặc bị kẹt trong API không phản ứng với interrupt, cleanup chưa xảy ra vì task chưa rời phạm vi thực thi.

`Future.cancel(true)` chỉ gửi yêu cầu interrupt; nó không đảm bảo task đã kết thúc. Khi cần đảm bảo không còn context hoặc resource đang được task sử dụng, cần chờ task thực sự kết thúc hoặc dùng một tín hiệu hoàn tất được thiết kế rõ ràng. Không xóa ThreadLocal của thread worker từ thread điều phối; `ThreadLocal.remove()` chỉ tác động đến giá trị gắn với thread đang gọi nó.

## 12. Các lỗi thường gặp và cách phòng tránh

| Lỗi | Rủi ro | Cách phòng tránh |
|---|---|---|
| Đặt token/password vào ThreadLocal dùng chung | Secret bị truy cập hoặc log ngoài phạm vi cần thiết | Không đưa secret vào context chung; lấy credential khi cần |
| Không gọi `remove()` trên worker được tái sử dụng | Context request trước còn lại trong task sau | Cleanup/restore trong `finally` |
| Nghĩ ThreadLocal tự truyền qua executor | Task thiếu context hoặc dùng nhầm context | Truyền tham số hoặc capture snapshot allowlist |
| Dùng InheritableThreadLocal với thread pool | Worker giữ context từ lúc được tạo, không phải từng task | Tránh dùng để truyền request context; wrapper rõ ràng |
| Không kiểm soát kế thừa trên virtual thread | Virtual thread mới nhận context nhạy cảm từ thread tạo | Dùng `inheritInheritableThreadLocals(false)` khi không cần inheritance |
| Log toàn bộ context/principal/exception message | Token, PII hoặc dữ liệu nội bộ xuất hiện trong log | Log theo allowlist và chuẩn hóa dữ liệu ngoài |
| Dùng trace ID như credential | Người biết ID có thể bị cấp quyền ngoài ý muốn | Trace ID chỉ phục vụ correlation; authorization kiểm tra riêng |
| Task nền dùng quyền đã capture từ request cũ | Quyền hết hạn hoặc bị thu hồi vẫn được dùng | Kiểm tra authorization hiện hành khi thực thi |
| Gọi remove() từ thread điều phối để xóa context worker | Không xóa giá trị trên thread worker | Để task tự cleanup trong `finally` |

## 13. Quy trình thiết kế context an toàn

1. Liệt kê trường nào thật sự cần cho xử lý, định tuyến, audit và chẩn đoán.
2. Phân loại dữ liệu nhạy cảm; loại credential và PII không cần thiết khỏi context chung.
3. Tạo context nhỏ, bất biến, có allowlist trường được phép truyền.
4. Truyền context qua tham số hoặc wrapper tại ranh giới async; không giả định ThreadLocal tự lan truyền.
5. Nếu dùng thread pool, cài đặt và khôi phục/xóa context trong `finally` cho từng task.
6. Nếu dùng virtual thread, xem xét việc kế thừa `InheritableThreadLocal`; tắt inheritance khi không cần.
7. Kiểm tra lại authorization và tenant scope khi task nền thực thi; context không thay thế security check.
8. Log các trường được phê duyệt, làm sạch dữ liệu ngoài và không serialize toàn bộ context.
9. Kiểm thử task thành công, exception, timeout, cancellation và hai request chạy liên tiếp trên cùng worker để phát hiện rò context.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 API — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 API — Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
