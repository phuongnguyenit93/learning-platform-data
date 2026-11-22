# Truyền ngữ cảnh qua executor, callback và tác vụ bất đồng bộ

## 1. Vấn đề: ngữ cảnh không tự đi theo tác vụ

Trong hệ thống plugin và mở rộng lúc chạy, một lời gọi có thể bắt đầu trên thread xử lý request, sau đó đi qua executor, callback hoặc \`CompletableFuture\`. Các thông tin liên quan đến lời gọi—\`requestId\`, tenant, người dùng đã xác thực, trace context, deadline, locale và class loader của plugin—thường được gọi chung là **execution context**.

Java **không tự động sao chép mọi ngữ cảnh của thread gọi sang thread thực thi tác vụ**. Đặc biệt, các giá trị đặt trong \`ThreadLocal\` thuộc về thread, không thuộc về đối tượng \`Runnable\` hay \`CompletableFuture\`. Executor pool còn tái sử dụng thread cho nhiều yêu cầu khác nhau. Vì vậy hai lỗi trái ngược đều có thể xảy ra:

- **Mất ngữ cảnh:** tác vụ bất đồng bộ không còn \`requestId\`, security principal hoặc tenant cần thiết.
- **Rò rỉ ngữ cảnh:** thread pool còn giữ giá trị từ request trước, khiến request sau đọc nhầm dữ liệu, ghi log sai hoặc truy cập sai tenant.

Các giải pháp phải bắt đầu từ việc xác định **ngữ cảnh nào thực sự cần truyền**, ai sở hữu nó, thời điểm capture, nơi cài đặt và khi nào phải khôi phục trạng thái cũ.

## 2. Phân biệt các loại ngữ cảnh

| Ngữ cảnh | Ví dụ | Cách truyền phù hợp |
|---|---|---|
| Business context | \`tenantId\`, \`requestId\`, mã chiến dịch | Tham số tường minh hoặc immutable context |
| Security context | Principal, quyền đã xác thực | Cơ chế propagation được framework hỗ trợ; không tự tin tưởng dữ liệu do plugin gửi |
| Tracing/logging | Trace ID, span, MDC | Instrumentation/context wrapper chuyên dụng |
| Locale/time zone | \`Locale\`, \`ZoneId\` | Truyền tường minh hoặc wrapper có phạm vi |
| Deadline/cancellation | Deadline, cancel token | Đối tượng điều phối được chia sẻ, với chính sách timeout rõ |
| Thread context class loader (TCCL) | Loader nhìn thấy resource/service của plugin | Thiết lập và khôi phục quanh tác vụ khi thật sự cần |

**Execution context không đồng nghĩa với Java \`ThreadContextClassLoader\`**. TCCL chỉ là một loại trạng thái liên quan đến thread, thường ảnh hưởng tới service discovery và resource loading. Cũng không được đánh đồng một context snapshot với transaction: transaction, JDBC connection và nhiều request-scoped object không thể chuyển sang thread khác tùy ý.

## 3. Cách ưu tiên: truyền context tường minh

Một giá trị bất biến mô tả các thông tin cần thiết cho công việc thường là giải pháp dễ kiểm thử và kiểm soát nhất.

\`\`\`java
record RequestContext(String requestId, String tenantId) {}

String process(RequestContext context, String payload) {
    return context.tenantId() + ":" + payload;
}
\`\`\`

Khi gửi tác vụ vào executor:

\`\`\`java
// Đoạn tích hợp; giả định executor, context và payload đã được tạo.
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> process(context, payload),
        executor
    );
\`\`\`

Lambda capture tham chiếu tới \`context\`; dữ liệu cần dùng vẫn có mặt khi task chạy trên thread khác. Để giảm race, context nên là immutable và các trường của nó cũng nên bất biến. Nếu context giữ \`Map\`, \`List\` hay object mutable, record **không tự động làm các object ấy immutable**. Có thể dùng \`Map.copyOf\` hoặc defensive copy.

Lợi ích của truyền tường minh: hợp đồng API thể hiện đúng dependency; ít phụ thuộc vào thread; dễ dùng qua queue, process boundary, test và structured task. Nhược điểm là phải đưa context qua nhiều lời gọi, nên một số framework sử dụng cơ chế context propagation có phạm vi để giảm boilerplate.

**Không truyền tất cả dữ liệu request.** Chỉ mang thông tin thực sự cần thiết, tuân thủ chính sách tối thiểu hóa dữ liệu và không sao chép credential/token sang plugin không được phép.

## 4. ThreadLocal: tiện nhưng có phạm vi theo thread

\`ThreadLocal<T>\` lưu một giá trị riêng cho mỗi thread:

\`\`\`java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
\`\`\`

Khi đặt \`REQUEST_ID.set("req-123")\` trên thread A, task chạy trên thread B thường nhận \`null\`, trừ khi B đã có một giá trị riêng. Với pool tái sử dụng, B còn có thể mang giá trị cũ nếu mã trước đó không \`remove()\`.

**Quy tắc cốt lõi:** nếu tự thiết lập \`ThreadLocal\` trong phạm vi tác vụ, dùng \`try/finally\` để khôi phục hoặc xóa giá trị. Điều này áp dụng kể cả khi callback ném exception.

\`\`\`java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(currentRequestId);
    performWork();
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
\`\`\`

Tại sao khôi phục giá trị cũ thay vì luôn \`remove()\`? Một thread có thể đang thực hiện phạm vi lồng nhau; wrapper bên trong cần trả lại context của caller bên ngoài. Nếu contract khẳng định thread hoàn toàn thuộc về tác vụ và không có nesting, \`remove()\` vẫn là thao tác cần thiết khi kết thúc.

### InheritableThreadLocal không giải quyết executor pool

\`InheritableThreadLocal\` có thể sao chép giá trị khởi tạo sang **thread con tại lúc tạo thread**. Với thread pool, thread có thể đã được tạo từ trước và tái sử dụng; do đó nó **không truyền context theo từng task**. Việc sao chép ngữ cảnh tại thời điểm tạo thread còn có thể làm lộ dữ liệu request ngoài ý muốn. Đừng dùng \`InheritableThreadLocal\` như giải pháp tổng quát cho asynchronous propagation.

## 5. Ví dụ Java 17+ chạy được: capture và restore ngữ cảnh

Ví dụ dưới đây tái hiện việc mất \`ThreadLocal\` khi chuyển sang executor, rồi sử dụng wrapper để truyền \`requestId\` an toàn hơn. Chương trình dùng một worker thread để đầu ra xác định.

Tạo file **\`ContextPropagationDemo.java\`**:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ContextPropagationDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static Runnable wrap(Runnable task) {
        // Capture trên thread gửi tác vụ, trước khi executor thực thi.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            REQUEST_ID.set("req-42");

            Future<?> plain = executor.submit(() ->
                    System.out.println("plain: " + REQUEST_ID.get()));
            plain.get();

            Future<?> wrapped = executor.submit(wrap(() ->
                    System.out.println("wrapped: " + REQUEST_ID.get())));
            wrapped.get();

            Future<?> after = executor.submit(() ->
                    System.out.println("after: " + REQUEST_ID.get()));
            after.get();
        } finally {
            REQUEST_ID.remove();
            executor.shutdown();
        }
    }
}
\`\`\`

Chạy:

\`\`\`bash
javac ContextPropagationDemo.java
java ContextPropagationDemo
\`\`\`

Kết quả:

\`\`\`text
plain: null
wrapped: req-42
after: null
\`\`\`

Ở đây \`wrap\` lấy snapshot của \`REQUEST_ID\` **khi submit task**. Trước khi gọi \`task.run()\`, wrapper tạm gắn context trên worker; trong \`finally\`, nó khôi phục trạng thái worker trước đó. Vì executor dùng một thread và \`Future.get()\` đợi lần lượt, ví dụ cho thấy tác vụ sau không nhận lại \`req-42\`.

Ví dụ chỉ truyền một chuỗi. Trong thực tế nên đóng gói một context có cấu trúc và giới hạn dữ liệu cần copy. Nếu sử dụng thêm MDC, security context hay TCCL, cần tạo wrapper có chính sách rõ cho từng loại và phục hồi tất cả trong \`finally\`.

## 6. Với Callable, Future và CompletableFuture

Một wrapper \`Runnable\` không tự bao phủ \`Callable<T>\` hoặc mọi callback trong pipeline bất đồng bộ.

Ví dụ wrapper cho \`Callable<T>\`:

\`\`\`java
// Đoạn tích hợp; REQUEST_ID là ThreadLocal<String> đã định nghĩa.
static <T> java.util.concurrent.Callable<T> wrapCallable(
        java.util.concurrent.Callable<T> action) {
    String captured = REQUEST_ID.get();
    return () -> {
        String previous = REQUEST_ID.get();
        try {
            if (captured == null) REQUEST_ID.remove();
            else REQUEST_ID.set(captured);
            return action.call();
        } finally {
            if (previous == null) REQUEST_ID.remove();
            else REQUEST_ID.set(previous);
        }
    };
}
\`\`\`

\`CompletableFuture\` cần chú ý **nơi callback thực sự được chạy**:

- \`thenApply\`, \`thenAccept\`, \`whenComplete\` không có hậu tố \`Async\` có thể chạy trên thread hoàn thành stage trước hoặc trên thread đang đăng ký callback nếu stage đã hoàn tất. Không được giả định chúng chạy trên thread của request.
- \`thenApplyAsync\` và các biến thể \`Async\` dùng executor được chỉ định; nếu không chỉ định, hành vi mặc định thường sử dụng \`ForkJoinPool.commonPool()\` theo quy tắc của \`CompletableFuture\`. Không được dựa vào việc thread trong pool ấy có context request.
- Một callback có thể được tạo trong phạm vi context A rồi thực thi khi stage hoàn thành từ thread có context B. Vì thế phải quyết định **capture lúc đăng ký callback**, không lấy tùy tiện \`ThreadLocal\` hiện hành khi callback chạy.

Ví dụ propagation tường minh:

\`\`\`java
// Đoạn tích hợp; context là immutable RequestContext.
CompletableFuture<String> result =
    CompletableFuture.supplyAsync(() -> fetchData(context), executor)
        .thenApplyAsync(data -> transform(context, data), executor)
        .thenApply(data -> format(context, data));
\`\`\`

Mỗi lambda dùng cùng \`context\` thông qua closure. Đây thường là cách rõ ràng hơn việc phụ thuộc vào thread-local qua nhiều stage.

Nếu bắt buộc dùng \`ThreadLocal\`, hãy wrap **từng entry point/callback** cần context; wrap riêng \`Executor.execute\` không đủ nếu các callback không được gửi qua executor đó. Một \`ContextAwareExecutor\` có thể capture tại \`execute(command)\` rồi chuyển task đã wrap tới delegate, nhưng cần kiểm tra xem callback không-\`Async\` có thực sự đi qua wrapper ấy hay không.

## 7. Callback do plugin đăng ký: capture và chủ sở hữu

Khi host cho phép plugin đăng ký callback:

\`\`\`java
eventBus.subscribe("order-created", event -> handle(event));
\`\`\`

Callback có thể chạy rất lâu sau thời điểm đăng ký, trên thread của event bus. Không nên capture toàn bộ context của **request đăng ký** rồi tái dùng mãi mãi cho mọi event. Cần phân biệt hai loại:

1. **Context của plugin/subscription**: định danh plugin, version, capability được cấp và thông tin lifecycle. Có thể được gắn với subscription lâu dài.
2. **Context của từng event/request**: correlation ID, tenant, tracing span và deadline. Phải đi cùng event cụ thể hoặc được tạo khi dispatch.

Một thiết kế dễ kiểm soát là biểu diễn event dưới dạng envelope:

\`\`\`java
// Đoạn minh họa cấu trúc, chưa gồm EventBus.
record EventEnvelope<T>(
    String eventId,
    String tenantId,
    String correlationId,
    T payload
) {}
\`\`\`

Dispatcher chuyển \`EventEnvelope\` vào callback. Trước khi thực thi, host có thể gắn context tương ứng vào logging/tracing framework với scoped lifecycle, sau đó khôi phục trạng thái. Không nhận \`tenantId\` hoặc principal từ plugin chưa tin cậy làm quyền hạn nếu chưa đối chiếu với security policy của host.

Với callback bị hủy đăng ký, cần bảo đảm listener, queue và context snapshot không giữ tham chiếu đến plugin/class loader cũ khiến hot unload không hoàn tất.

## 8. Thread context class loader trong hệ plugin

\`Thread.currentThread().getContextClassLoader()\` (TCCL) là một cơ chế khác với \`ThreadLocal\` do ứng dụng định nghĩa. Một số API/service discovery hoặc thư viện dùng TCCL để tìm class/resource.

Trong plugin system có nhiều class loader, callback chạy trên thread pool của host có thể mang TCCL của host, không phải loader plugin. Khi thực sự cần chạy một đoạn code với TCCL plugin, host có thể đặt TCCL tạm thời và **luôn khôi phục**:

\`\`\`java
// Đoạn tích hợp; pluginLoader và task được xác định bởi host.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    task.run();
} finally {
    thread.setContextClassLoader(previous);
}
\`\`\`

Không đặt TCCL plugin một lần cho thread pool rồi để lại mãi mãi: điều này làm các tác vụ của plugin khác dùng sai loader và có thể giữ plugin loader sau khi đã vô hiệu hóa. Cũng không coi TCCL là biện pháp sandbox; class loader riêng không tạo ra ranh giới bảo mật đáng tin cho mã không tin cậy.

Khi dùng \`ServiceLoader.load(ServiceType.class)\`, TCCL có thể ảnh hưởng đến loader được chọn. Nếu host cần kiểm soát chính xác, cân nhắc overload nhận \`ClassLoader\` hoặc API module-layer tương ứng và đảm bảo API chung được định nghĩa từ loader ổn định.

## 9. Tích hợp logging, tracing và security context

Trong framework thực tế, đừng tự sao chép trạng thái nội bộ tùy tiện. Tận dụng các API được hỗ trợ:

**MDC (Mapped Diagnostic Context).** Nhiều logging framework gắn dữ liệu log vào thread-local. Khi gửi task sang executor, MDC thường không tự truyền. Nếu wrapper sao chép MDC, hãy lấy snapshot tại thời điểm submit, cài snapshot khi chạy và phục hồi snapshot trước đó trong \`finally\`. Cẩn trọng với key chứa dữ liệu cá nhân và không để MDC giữ lại giữa các request.

**Distributed tracing.** Tracing context bao gồm nhiều hơn trace ID: span hierarchy, baggage và quy tắc scope. Sử dụng API/instrumentation context propagation của giải pháp tracing (ví dụ OpenTelemetry) thay vì tạo span ID bằng cách copy một chuỗi. Baggage nên được lọc khi đi qua ranh giới tin cậy.

**Security context.** Với Spring Security hoặc framework tương đương, dùng cơ chế executor/decorator tích hợp được thiết kế để truyền và dọn dẹp security context. Tính xác thực, quyền và thời hạn phải được kiểm tra tại nơi thực thi. Việc copy principal qua thread không tự cấp quyền cho plugin. Không chia sẻ credential mạnh với code không tin cậy chỉ vì thuận tiện truyền context.

**Request-scoped resources.** JDBC transaction, servlet request/response, entity manager và object có vòng đời request thường không an toàn để giữ và chạy lại trên thread khác. Chỉ truyền dữ liệu tối thiểu hoặc mở scope mới theo quy tắc của framework tại nơi thực thi.

## 10. Timeout, cancellation và ngữ cảnh bất đồng bộ

Deadline là thông tin ngữ cảnh có thể truyền bằng giá trị bất biến, ví dụ một \`Instant\` hoặc timeout budget. Nhưng truyền deadline **không tự dừng** task đang chạy. Tác vụ phải hỗ trợ kiểm tra hạn hoặc cơ chế cancellation tương ứng.

Với \`Future.cancel(true)\`, Java chỉ yêu cầu ngắt thread nếu task đang chạy; không bảo đảm task dừng ngay. Với \`CompletableFuture.cancel(...)\`, cơ chế cancel completion không nhất thiết interrupt tiến trình tính toán phía dưới. Vì vậy wrapper context không thể thay thế quy tắc quản lý task, resource, timeout và rollback.

Mô hình tốt gồm:

- Capture deadline/correlation context trước khi dispatch.
- Kiểm tra hạn ở các bước quan trọng và trước khi thực hiện side effect.
- Truyền cancellation signal tới stage và dependency có hỗ trợ.
- Khôi phục \`ThreadLocal\`, MDC và TCCL ngay cả khi timeout, exception hoặc interrupt.
- Đóng tài nguyên và tránh giữ context snapshot lâu hơn vòng đời công việc.

## 11. Những lỗi thường gặp

1. **Dựa vào ThreadLocal trên executor:** \`ThreadLocal.set\` trên thread caller không đảm bảo worker nhìn thấy giá trị.
2. **Không dọn ThreadLocal:** thread pool tái sử dụng khiến dữ liệu request trước rò sang request sau.
3. **Dùng InheritableThreadLocal trong pool:** inheritance diễn ra theo thời điểm tạo thread, không theo thời điểm submit task.
4. **Capture quá sớm:** một callback đăng ký lâu dài giữ \`tenantId\` của request ban đầu.
5. **Capture quá muộn:** lấy ngữ cảnh từ thread đang chạy callback thay vì context của event/request đúng.
6. **Không phân biệt callback Async và non-Async:** callback có thể chạy trên thread bất kỳ hoàn thành stage.
7. **Truyền mutable context dùng chung:** nhiều task cùng sửa map dẫn tới race hoặc nhiễm dữ liệu.
8. **Không phục hồi TCCL/MDC:** tác vụ của plugin sau nhận sai loader hoặc sai trace.
9. **Mang transaction/request object sang thread khác:** phá vỡ lifetime và thread affinity của resource.
10. **Cho plugin không tin cậy quyết định security context:** dữ liệu truyền context bị nhầm thành bằng chứng cấp quyền.
11. **Bỏ qua lifecycle:** task và callback còn sống giữ class loader/plugin đã được thay thế.
12. **Coi propagation là cancellation:** có deadline không có nghĩa tác vụ sẽ tự ngừng.

## 12. Checklist thiết kế

Trước khi đưa một task/callback vào hệ thống mở rộng lúc chạy, trả lời rõ:

- **Cần truyền gì?** \`requestId\`, tenant, trace, locale, deadline, security principal hay TCCL; loại bỏ mọi trường không cần thiết.
- **Nguồn sự thật ở đâu?** Context từ host đã được xác thực hay giá trị do plugin tự khai báo?
- **Capture khi nào?** Lúc submit, đăng ký callback hay dispatch từng event?
- **Cài và dọn ở đâu?** Mọi entry point thread mới và callback nào thực sự cần scope?
- **Thứ tự và lỗi thế nào?** Khi exception, timeout hoặc cancel, state trước đó có luôn được phục hồi?
- **Có chia sẻ mutable state không?** Immutable snapshot, ownership và đồng bộ hóa đã rõ chưa?
- **Plugin bị gỡ thì sao?** Task in-flight, listener, loader và tài nguyên có được drain/đóng đúng không?
- **Đã kiểm thử đường chuyển thread chưa?** Kiểm thử task thường, task lỗi, nhiều request xen kẽ, callback hoàn thành tức thì, hot reload và cleanup.

**Ghi nhớ:** context phải gắn với **công việc cần thực hiện** và ranh giới tin cậy, không mặc định gắn với thread. Ưu tiên **truyền tường minh bằng immutable context**; khi dùng \`ThreadLocal\`, MDC, security context hoặc TCCL, hãy **capture đúng lúc → cài đặt theo phạm vi → khôi phục trong \`finally\`**.
