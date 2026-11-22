# ThreadLocal và dữ liệu gắn với yêu cầu đã kết thúc

Trong ứng dụng Java, ThreadLocal cho phép mỗi thread giữ một giá trị riêng mà không cần truyền giá trị đó qua từng lời gọi phương thức. Cách này thường được dùng để lưu thông tin ngữ cảnh như request ID, người dùng hiện tại, tenant, locale, transaction context hoặc dữ liệu phục vụ logging.

Vấn đề xuất hiện khi thread được tái sử dụng. Trong web server hoặc executor, một worker thread thường xử lý nhiều request hoặc nhiều tác vụ trong suốt vòng đời của tiến trình. Khi request kết thúc, thread vẫn tồn tại để xử lý request tiếp theo. Nếu dữ liệu ThreadLocal không được xóa, request sau có thể nhìn thấy dữ liệu của request trước. Dữ liệu cũ cũng có thể giữ tham chiếu đến object lớn, credential, EntityManager hoặc tài nguyên đã hết hiệu lực.

Với CRaC (Coordinated Restore at Checkpoint), trạng thái của thread và các đối tượng gắn với thread có thể nằm trong trạng thái tiến trình được checkpoint. Nếu tiến trình được checkpoint khi worker đang giữ dữ liệu của một request đã kết thúc nhưng chưa cleanup, trạng thái cũ có thể tiếp tục tồn tại sau restore. Vì vậy, cần quản lý ThreadLocal ngay tại ranh giới kết thúc request hoặc task, đồng thời bảo đảm ứng dụng đã drain công việc và ở trạng thái ổn định trước checkpoint.

## 1. ThreadLocal hoạt động như thế nào?

ThreadLocal<T> là một API của Java cho phép mỗi thread có một giá trị độc lập gắn với cùng một đối tượng ThreadLocal. Khi thread A gọi get(), nó nhận giá trị thuộc thread A; thread B gọi get() trên cùng ThreadLocal thì nhận giá trị riêng của thread B.

Ví dụ:

```java
private static final ThreadLocal<String> CURRENT_USER =
        new ThreadLocal<>();

void handleRequest(String user) {
    CURRENT_USER.set(user);
    try {
        process();
    } finally {
        CURRENT_USER.remove();
    }
}

void process() {
    String user = CURRENT_USER.get();
    System.out.println("Current user: " + user);
}
```

Mỗi thread có thể giữ một giá trị khác nhau:

```text
ThreadLocal object
       |
       +---- Thread A: "alice"
       |
       +---- Thread B: "bob"
       |
       +---- Thread C: "carol"
```

ThreadLocal không tự tạo một thread mới và cũng không tự truyền dữ liệu giữa các thread. Nó chỉ cung cấp một cách truy cập trạng thái gắn với thread đang thực thi.

Các phương thức cơ bản:

| Phương thức | Ý nghĩa |
|---|---|
| set(value) | Đặt giá trị cho thread hiện tại |
| get() | Lấy giá trị của thread hiện tại; có thể gọi initialValue hoặc Supplier nếu chưa có |
| remove() | Xóa giá trị của thread hiện tại khỏi ThreadLocal |
| withInitial(supplier) | Tạo ThreadLocal có hàm khởi tạo giá trị mặc định |

Một đối tượng ThreadLocal thường được khai báo static final để các thành phần trong cùng ứng dụng truy cập cùng một khóa ThreadLocal. Tuy nhiên, điều đó không làm giá trị trở thành dữ liệu dùng chung: mỗi thread vẫn có entry riêng.

## 2. Giá trị ThreadLocal được lưu ở đâu?

Về mặt triển khai của OpenJDK, mỗi đối tượng Thread có một ThreadLocalMap riêng để lưu các entry của những ThreadLocal được thread đó sử dụng. Mỗi entry liên kết một khóa ThreadLocal với giá trị tương ứng.

Có thể hình dung:

```text
Thread A
  ThreadLocalMap
    key: CURRENT_USER  -> value: "alice"
    key: REQUEST_ID    -> value: "req-101"

Thread B
  ThreadLocalMap
    key: CURRENT_USER  -> value: "bob"
    key: REQUEST_ID    -> value: "req-102"
```

Đây là mô tả về cách triển khai phổ biến của OpenJDK; ứng dụng nên dựa vào hợp đồng API ThreadLocal thay vì phụ thuộc vào cấu trúc nội bộ ThreadLocalMap.

Một điểm quan trọng là giá trị được gắn với thread, không gắn với một request cụ thể. Nếu thread còn sống sau khi request kết thúc, giá trị có thể còn tồn tại cho đến khi được thay thế hoặc remove(). ThreadLocal không biết khái niệm request bắt đầu hay kết thúc.

Vì vậy, câu lệnh set() không có nghĩa là giá trị sẽ tự hết hạn khi phương thức xử lý request trả về. Ứng dụng phải chủ động xác định ranh giới cleanup.

## 3. Vì sao thread pool làm lộ lỗi ThreadLocal?

Nếu ứng dụng tạo một thread mới cho mỗi request rồi thread kết thúc ngay sau đó, giá trị ThreadLocal cũng không còn được thread đó giữ khi thread kết thúc. Nhưng server hiện đại thường dùng thread pool để tránh chi phí tạo và hủy thread liên tục.

Một worker thread có thể xử lý lần lượt nhiều request:

```text
Worker-1
   |
   +--> Request A: set user = "alice"
   |       |
   |       +--> request kết thúc
   |
   +--> Request B: get user
   |       |
   |       +--> nếu không remove: có thể thấy "alice"
   |
   +--> Request C
           |
           +--> worker vẫn là cùng một thread
```

Giả sử filter đặt thông tin người dùng vào ThreadLocal khi request bắt đầu nhưng không xóa khi request kết thúc. Khi worker thread được tái sử dụng, request kế tiếp có thể đọc dữ liệu cũ. Đây là lỗi rò rỉ ngữ cảnh (*context leakage*).

Ví dụ lỗi:

```java
private static final ThreadLocal<String> CURRENT_TENANT =
        new ThreadLocal<>();

void handle(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant);
    action.run();

    // Lỗi: không xóa giá trị sau khi request hoàn tất.
}
```

Nếu tenant A được xử lý trước tenant B trên cùng worker và đoạn code B không đặt lại giá trị vì một nhánh xử lý đặc biệt, B có thể nhìn thấy tenant A. Tương tự, nếu một request lỗi trước khi cập nhật ThreadLocal, giá trị còn lại từ request trước có thể bị sử dụng.

Cách sửa tối thiểu:

```java
void handle(String tenant, Runnable action) {
    CURRENT_TENANT.set(tenant);
    try {
        action.run();
    } finally {
        CURRENT_TENANT.remove();
    }
}
```

finally bảo đảm cleanup được thực hiện cả khi action trả về bình thường hoặc ném exception.

## 4. Dữ liệu nào thường được đặt trong ThreadLocal?

ThreadLocal thường được dùng cho dữ liệu chỉ có ý nghĩa trong một luồng thực thi đồng bộ:

- Request ID hoặc correlation ID để liên kết log.
- Security principal hoặc thông tin xác thực của người dùng hiện tại.
- Tenant ID trong ứng dụng multi-tenant.
- Locale, timezone hoặc cấu hình định dạng theo request.
- Context phục vụ tracing và metrics.
- Transaction context hoặc EntityManager proxy do framework quản lý.
- Dữ liệu tạm phục vụ xử lý trong một đơn vị công việc.

Không phải mọi dữ liệu trên đều nên được ứng dụng tự lưu trong ThreadLocal. Framework có thể đã có cơ chế quản lý context riêng. Ví dụ, Spring Security, transaction manager, logging framework và tracing library có thể cung cấp API đặt, lấy và xóa context. Nên dùng API của framework thay vì tạo một ThreadLocal song song chứa cùng dữ liệu.

Cũng cần cân nhắc dữ liệu nhạy cảm. Principal, token, session object hoặc thông tin tenant có thể ảnh hưởng đến quyền truy cập. Nếu dữ liệu bị rò rỉ sang request khác, lỗi có thể trở thành vấn đề bảo mật chứ không chỉ là lỗi hiển thị log.

## 5. remove() quan trọng hơn việc chỉ set(null)

Hai cách sau không hoàn toàn tương đương:

```java
CURRENT_USER.set(null);
```

và:

```java
CURRENT_USER.remove();
```

set(null) đặt giá trị hiện tại thành null nhưng entry của ThreadLocal vẫn có thể tồn tại trong ThreadLocalMap. remove() xóa entry của thread hiện tại.

Với mục đích cleanup sau request, nên gọi remove():

```java
try {
    CURRENT_USER.set(user);
    process();
} finally {
    CURRENT_USER.remove();
}
```

remove() chỉ tác động đến thread đang gọi. Gọi remove() từ một thread quản lý hoặc thread checkpoint không xóa được giá trị trong ThreadLocalMap của các worker thread khác. Đây là lý do cleanup cần diễn ra trên chính thread sở hữu context, thường tại filter/interceptor hoặc task wrapper.

Nếu cần đặt giá trị tạm thời lồng nhau, có thể lưu giá trị trước đó rồi khôi phục nó thay vì luôn remove():

```java
String previous = CURRENT_USER.get();
CURRENT_USER.set(user);
try {
    process();
} finally {
    if (previous == null) {
        CURRENT_USER.remove();
    } else {
        CURRENT_USER.set(previous);
    }
}
```

Mẫu này hữu ích khi một hàm chạy trong context đã có sẵn và cần tạm thay đổi context. Tuy nhiên, cần xác định rõ quy tắc nesting và cách phân biệt “không có giá trị” với “giá trị null” nếu null là một trạng thái hợp lệ trong ứng dụng.

## 6. Cleanup ở ranh giới request

Trong ứng dụng web, ranh giới request là nơi phù hợp để đặt và xóa request context. Một filter hoặc interceptor có thể:

1. Đọc request ID, user hoặc tenant từ request đã được xác thực.
2. Đặt các giá trị cần thiết vào context.
3. Cho phép phần còn lại của pipeline xử lý.
4. Trong finally, xóa toàn bộ context do filter sở hữu.

Ví dụ filter servlet đơn giản:

```java
public final class RequestContextFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        String requestId = resolveRequestId(http);

        RequestContext.setRequestId(requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            RequestContext.clear();
        }
    }

    private String resolveRequestId(HttpServletRequest request) {
        String value = request.getHeader("X-Request-ID");
        return value == null || value.isBlank()
                ? UUID.randomUUID().toString()
                : value;
    }
}
```

Lớp RequestContext cần xóa mọi ThreadLocal mà nó sở hữu:

```java
public final class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();
    private static final ThreadLocal<String> TENANT_ID =
            new ThreadLocal<>();

    private RequestContext() {}

    public static void setRequestId(String value) {
        REQUEST_ID.set(value);
    }

    public static String requestId() {
        return REQUEST_ID.get();
    }

    public static void setTenantId(String value) {
        TENANT_ID.set(value);
    }

    public static String tenantId() {
        return TENANT_ID.get();
    }

    public static void clear() {
        REQUEST_ID.remove();
        TENANT_ID.remove();
    }
}
```

Trong ứng dụng thực tế, filter phải được đặt đúng vị trí trong security chain. Không nên lấy tenant hoặc user từ header chưa được xác thực rồi dùng trực tiếp để quyết định quyền truy cập. Request context chỉ nên chứa dữ liệu đã được xác thực và có nguồn tin cậy.

Nếu dùng Spring MVC, có thể triển khai cleanup trong Filter, HandlerInterceptor hoặc cơ chế context do Spring cung cấp. Chọn một nơi có thể bao phủ cả đường đi bình thường, exception và early return. Đảm bảo cleanup xảy ra sau khi phần xử lý đồng bộ hoàn tất.

## 7. ThreadLocal và logging context (MDC)

Các logging framework thường cung cấp Mapped Diagnostic Context (MDC) để gắn request ID, user ID hoặc correlation ID vào log mà không cần truyền tham số qua mọi lời gọi.

Ví dụ với SLF4J MDC:

```java
try {
    MDC.put("requestId", requestId);
    MDC.put("tenantId", tenantId);

    service.handle();
} finally {
    MDC.clear();
}
```

MDC implementation thường dùng trạng thái gắn với thread hoặc cơ chế context tương đương, vì vậy vẫn cần cleanup khi worker được tái sử dụng. API cụ thể có thể khác giữa logging provider; đọc tài liệu của provider đang chạy.

Không nên chỉ gọi MDC.clear() nếu ứng dụng có context khác được đặt bởi thành phần bên ngoài và cần được khôi phục. Trong trường hợp lồng nhau, có thể lưu MDC context map trước đó rồi khôi phục, hoặc dùng API scoped/closeable mà thư viện cung cấp.

Một lỗi phổ biến là request đồng bộ kết thúc và MDC được dọn đúng, nhưng tác vụ async được gửi sang executor không nhận được context. Ngược lại, nếu tự copy context vào task mà không xóa sau khi task kết thúc, worker có thể mang context của task cũ sang task kế tiếp.

## 8. InheritableThreadLocal không giải quyết context propagation cho thread pool

InheritableThreadLocal cho phép thread con kế thừa giá trị từ thread cha tại thời điểm thread con được tạo. Đây là khác biệt quan trọng so với ThreadLocal thông thường.

Ví dụ:

```java
private static final InheritableThreadLocal<String> USER =
        new InheritableThreadLocal<>();

USER.set("alice");
Thread child = new Thread(() ->
        System.out.println(USER.get()));
child.start();
```

Thread con được tạo trong khi thread cha đang giữ "alice" nên có thể nhận giá trị được kế thừa.

Nhưng thread pool thường tạo worker trước khi request gửi task. Nếu worker đã được tạo từ trước, việc set InheritableThreadLocal khi request bắt đầu không làm worker đó tự nhận giá trị mới. Nếu worker được tạo trong lúc context đang được đặt, nó có thể kế thừa context tại thời điểm tạo rồi giữ giá trị đó lâu hơn request ban đầu.

Vì vậy, InheritableThreadLocal không phải giải pháp tổng quát để truyền context cho task trong executor. Nó có thể tạo ra lỗi khó đoán khi thread được tái sử dụng hoặc tạo mới không đồng bộ với request.

Cũng cần chú ý rằng hành vi mặc định sao chép giá trị không nhất thiết tạo bản sao sâu. Nếu giá trị là một object mutable, thread cha và thread con có thể cùng tham chiếu một object tùy cách childValue() được triển khai.

## 9. Truyền context qua executor một cách tường minh

ThreadLocal chỉ trả về giá trị trên thread hiện tại. Khi chuyển công việc sang executor, task thường chạy trên một thread khác và không tự nhìn thấy ThreadLocal của thread gửi task.

Cách an toàn hơn là chụp context tại thời điểm submit, đặt nó trong worker khi task chạy, rồi khôi phục hoặc xóa context trong finally.

Ví dụ một wrapper đơn giản:

```java
public final class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> TENANT_ID = new ThreadLocal<>();

    private RequestContext() {}

    public record Snapshot(String requestId, String tenantId) {}

    public static Snapshot capture() {
        return new Snapshot(REQUEST_ID.get(), TENANT_ID.get());
    }

    public static void restore(Snapshot snapshot) {
        setOrRemove(REQUEST_ID, snapshot.requestId());
        setOrRemove(TENANT_ID, snapshot.tenantId());
    }

    public static void clear() {
        REQUEST_ID.remove();
        TENANT_ID.remove();
    }

    private static void setOrRemove(
            ThreadLocal<String> local, String value) {
        if (value == null) {
            local.remove();
        } else {
            local.set(value);
        }
    }
}

public final class ContextAwareExecutor {
    private final Executor delegate;

    public ContextAwareExecutor(Executor delegate) {
        this.delegate = delegate;
    }

    public void execute(Runnable task) {
        RequestContext.Snapshot captured = RequestContext.capture();

        delegate.execute(() -> {
            RequestContext.Snapshot previous = RequestContext.capture();

            try {
                RequestContext.restore(captured);
                task.run();
            } finally {
                RequestContext.restore(previous);
            }
        });
    }
}
```

Ví dụ dùng một snapshot bất biến để chụp context ở thread gửi task. Worker lưu snapshot cũ, đặt context được truyền, chạy task rồi khôi phục snapshot cũ trong finally. Ở đây null được xem là không có giá trị và dẫn đến remove(). Trong hệ thống thực tế, nếu null là một giá trị hợp lệ cần phân biệt với trạng thái chưa đặt, snapshot phải lưu thêm cờ presence cho từng trường. Đoạn mã dùng record nên yêu cầu Java 16 trở lên; có thể thay record bằng lớp bất biến nếu dự án dùng JDK cũ hơn.

Các nguyên tắc:

- Chỉ truyền những trường thật sự cần cho task.
- Không truyền request object, EntityManager, Session hoặc transaction object sang thread khác trừ khi framework hỗ trợ rõ ràng.
- Context snapshot nên bất biến để tránh thread gửi và worker cùng sửa dữ liệu.
- Khôi phục context trước khi chạy task.
- Luôn cleanup hoặc khôi phục context cũ trong finally.
- Xử lý trường hợp task bị hủy trước khi bắt đầu hoặc executor từ chối submit.
- Không giữ context của request lâu hơn vòng đời nghiệp vụ của task.

Nếu task tiếp tục chạy sau khi HTTP response đã trả về, nó không còn là phần xử lý đồng bộ của request. Cần xác định dữ liệu nào được phép tồn tại cho công việc nền và thời hạn của dữ liệu đó. Không nên giữ toàn bộ request context chỉ vì task được khởi tạo từ request.

## 10. ThreadLocal trong async, CompletableFuture và reactive pipeline

Với CompletableFuture, callback có thể chạy trên thread của executor khác hoặc common ForkJoinPool. Không thể giả định callback sẽ chạy trên thread đã gọi supplyAsync() hoặc thenApply().

Ví dụ:

```java
CompletableFuture.supplyAsync(() -> loadData())
    .thenApply(data -> enrich(data))
    .thenAccept(result -> save(result));
```

Các stage có thể chạy trên nhiều thread khác nhau tùy executor và trạng thái hoàn thành. ThreadLocal của request ban đầu không tự truyền theo chuỗi stage.

Có thể truyền một context snapshot tường minh vào từng stage hoặc dùng context propagation library/framework được hỗ trợ. Với Spring, Reactor hoặc tracing framework, hãy dùng cơ chế context của chính nền tảng đó. Reactive pipeline có thể chuyển thread nhiều lần; ThreadLocal không phải nơi phù hợp để giữ context reactive xuyên suốt pipeline.

Trong Reactor, Reactor Context được thiết kế để gắn dữ liệu với subscriber sequence thay vì thread vật lý. Việc tích hợp với ThreadLocal/MDC cần dùng hook hoặc bridge được hỗ trợ và phải chú ý cleanup. Không nên tự lấy ThreadLocal trong một operator rồi giả định mọi operator tiếp theo chạy trên cùng thread.

## 11. ThreadLocal giữ tài nguyên và đối tượng lớn

Giá trị ThreadLocal không chỉ là String hoặc request ID. Một số ứng dụng lưu đối tượng lớn hoặc resource vào ThreadLocal, ví dụ:

- EntityManager hoặc Hibernate Session.
- JDBC Connection.
- Request object hoặc security context.
- Buffer lớn hoặc parser state.
- Formatter, serializer hoặc object cache.
- Native handle hoặc wrapper đến tài nguyên hệ điều hành.

Nếu không remove(), worker thread sống lâu có thể giữ các đối tượng đó lâu hơn dự kiến. Điều này có thể gây memory retention hoặc resource leak.

Một số implementation của ThreadLocalMap dùng weak reference cho key ThreadLocal, nhưng value vẫn được giữ mạnh bởi entry cho đến khi entry stale được dọn. Nếu ThreadLocal key không còn được tham chiếu nhưng worker thread vẫn sống, value có thể còn được giữ tạm thời. Cơ chế dọn stale entry là chi tiết triển khai; không nên dùng nó thay cho remove() có chủ đích.

Nếu ThreadLocal giữ JDBC Connection hoặc EntityManager, việc xóa tham chiếu không thay thế việc đóng tài nguyên đúng cách. Cần gọi close/cleanup theo owner trước, sau đó remove ThreadLocal. Không để connection pool hoặc transaction manager mất khả năng quản lý resource chỉ vì reference bị xóa khỏi context.

## 12. ThreadLocal và CRaC checkpoint

Checkpoint lưu trạng thái tiến trình, bao gồm trạng thái thread và bộ nhớ theo cơ chế mà JDK CRaC và nền tảng hỗ trợ. ThreadLocal gắn với thread vì vậy cần được xem xét như một phần trạng thái runtime có thể tồn tại ở thời điểm checkpoint.

Giả sử một worker đã xử lý request A:

```text
Worker-7
  CURRENT_USER = "alice"
  TENANT_ID = "tenant-blue"
  REQUEST_ID = "req-A"
```

Request A kết thúc nhưng cleanup bị bỏ quên. Worker-7 quay về pool chờ task mới. Nếu checkpoint xảy ra lúc này, dữ liệu của request A có thể được lưu cùng trạng thái thread. Sau restore, worker có thể tiếp tục tồn tại với context cũ tùy trạng thái được phục hồi. Request mới có thể đọc nhầm user, tenant hoặc request ID.

Điều này tạo ra ba nhóm rủi ro:

1. **Rò rỉ dữ liệu giữa request:** request mới thấy context của request cũ.
2. **Sai phạm vi bảo mật:** tenant hoặc principal cũ có thể ảnh hưởng đến quyết định truy cập dữ liệu.
3. **Giữ tài nguyên hoặc bộ nhớ:** ThreadLocal có thể giữ EntityManager, connection, request object hoặc buffer không còn cần thiết.

CRaC không tự hiểu rằng một giá trị ThreadLocal thuộc request nào hoặc request đó đã kết thúc. Framework cũng không thể tự cleanup mọi ThreadLocal do ứng dụng và thư viện tự tạo nếu không có integration tương ứng.

Biện pháp chính là cleanup đúng ranh giới request/task ngay từ đầu. Trước checkpoint, ngừng nhận công việc mới và drain các request/task đang chạy để mọi finally block và cleanup hook được thực thi. Sau restore, mở lại ingress khi thread pool và các thành phần context đã ở trạng thái hợp lệ.

## 13. Không thể xóa ThreadLocal của mọi thread bằng một lệnh remove()

ThreadLocal.remove() chỉ xóa entry của thread hiện tại. Nếu checkpoint coordinator chạy trên thread riêng, gọi CURRENT_USER.remove() ở coordinator không xóa giá trị của worker-1, worker-2 hay worker-3.

Không nên cố dùng reflection để truy cập Thread.threadLocals hoặc sửa ThreadLocalMap nội bộ. Cách này phụ thuộc implementation, có thể bị chặn bởi module encapsulation và có nguy cơ phá trạng thái của thư viện.

Thay vào đó:

- Cleanup tại filter/interceptor trên thread xử lý request.
- Bọc task trong executor để đặt và xóa context trên worker thread.
- Dừng ingress và chờ worker hoàn tất task.
- Dùng API cleanup của framework hoặc thư viện đang sở hữu context.
- Với ThreadLocal do ứng dụng quản lý, giữ API clear() tập trung để mọi code path dùng cùng quy tắc.
- Chỉ dùng callback CRaC cho phần lifecycle mà owner có thể kiểm soát và xác minh.

Nếu một thread nền sống liên tục và giữ context theo vòng đời dài hơn một task, hãy thiết kế một lifecycle riêng cho thread đó. Không xóa tùy tiện dữ liệu mà thư viện cần để hoạt động; xác định rõ giá trị nào là context tạm của task và giá trị nào là state lâu dài hợp lệ.

## 14. Dùng CRaC Resource để phối hợp worker và context

CRaC Resource có hai callback chính: beforeCheckpoint(...) và afterRestore(...). Với ThreadLocal, callback không nên cố quét và xóa ThreadLocal của mọi thread. Vai trò phù hợp hơn là điều phối ingress, task lifecycle và worker pool.

Ví dụ dưới đây minh họa coordinator đơn giản. Các phương thức RequestGate và WorkerLifecycle là API giả định do ứng dụng tự xây dựng, không phải API chuẩn của CRaC.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class WorkerCheckpointResource implements Resource {
    private final RequestGate requestGate;
    private final WorkerLifecycle workers;

    public WorkerCheckpointResource(
            RequestGate requestGate,
            WorkerLifecycle workers) {
        this.requestGate = requestGate;
        this.workers = workers;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        requestGate.stopAcceptingNewWork();
        requestGate.awaitInFlightWorkToFinish();
        workers.awaitTasksToDrain();
        workers.verifyTaskContextCleanup();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        workers.restoreOrRestartIfRequired();
        workers.verifyReady();
        requestGate.allowNewWork();
    }

    public interface RequestGate {
        void stopAcceptingNewWork() throws Exception;
        void awaitInFlightWorkToFinish() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface WorkerLifecycle {
        void awaitTasksToDrain() throws Exception;
        void verifyTaskContextCleanup() throws Exception;
        void restoreOrRestartIfRequired() throws Exception;
        void verifyReady() throws Exception;
    }
}
```

Trong ứng dụng thật, cần xác định rõ ai sở hữu executor và thread pool. Có framework quản lý thread pool theo lifecycle riêng; không tự shutdown executor do container quản lý nếu không có hướng dẫn. Có executor có thể tiếp tục dùng sau restore; có executor hoặc thread phụ thuộc môi trường cần khởi tạo lại. Hãy dùng integration được hỗ trợ và kiểm thử đúng bản JDK CRaC.

Phương thức verifyTaskContextCleanup() nên dựa trên cơ chế quan sát do ứng dụng kiểm soát, ví dụ task wrapper ghi nhận context đã được clear hoặc metric số task đang hoạt động. Không nên dựa vào reflection để đọc mọi ThreadLocal nội bộ của JVM.

## 15. Phân biệt context của request với context của thread nền

Một thread nền có thể cần một số thông tin lâu dài, nhưng điều đó không có nghĩa nó nên giữ nguyên request context đã tạo ra nó.

Ví dụ, một worker chuyên xử lý email có thể cần cấu hình SMTP và thông tin service account trong suốt vòng đời. Những giá trị này là cấu hình của worker hoặc ứng dụng. Trong khi đó, request ID, user principal và tenant ID của một request cụ thể chỉ nên tồn tại trong phạm vi công việc được truyền một cách có chủ đích.

Hãy phân loại:

| Dữ liệu | Phạm vi phù hợp | Cleanup hoặc refresh |
|---|---|---|
| Request ID | Một request hoặc tác vụ phát sinh từ request | Xóa khi task kết thúc |
| User principal | Một đơn vị công việc đã xác thực | Xóa khi task kết thúc; chỉ truyền khi có lý do |
| Tenant ID | Một request/job thuộc tenant | Xóa sau task; xác minh quyền trước khi dùng |
| Locale | Một request hoặc job cần định dạng | Xóa sau task |
| Service configuration | Vòng đời ứng dụng/worker | Làm mới theo cơ chế cấu hình |
| Database transaction context | Một transaction | Kết thúc hoặc rollback cùng transaction |
| EntityManager/Session | Một persistence context | Đóng khi đơn vị công việc kết thúc |
| Metrics registry | Vòng đời ứng dụng | Không phải request context |
| Cache cục bộ của worker | Vòng đời worker, có chính sách rõ ràng | Invalidate hoặc tạo lại theo yêu cầu |

Không đặt toàn bộ RequestContext vào thread nền rồi giữ vô thời hạn. Chỉ snapshot những trường thực sự cần thiết và định nghĩa thời hạn của snapshot.

## 16. Virtual thread và ThreadLocal

Virtual thread thay đổi cách Java tổ chức concurrency: nhiều virtual thread có thể được lập lịch trên một số ít carrier thread. ThreadLocal vẫn gắn với virtual thread theo mô hình API, nhưng chi phí và đặc tính bộ nhớ có thể khác so với platform thread.

Một ứng dụng dùng virtual thread không nên mặc định rằng ThreadLocal là miễn phí. Nếu tạo rất nhiều virtual thread và mỗi thread giữ object lớn, tổng bộ nhớ vẫn tăng. Các tài nguyên như JDBC Connection hoặc EntityManager cũng không nên được giữ trong ThreadLocal chỉ vì virtual thread có thể chạy nhiều tác vụ đồng thời.

Một số framework và API hiện đại cung cấp cơ chế context khác, ví dụ ScopedValue ở các phiên bản JDK có hỗ trợ tương ứng. ScopedValue hướng tới dữ liệu được ràng buộc theo phạm vi thực thi và không thể thay đổi tùy ý sau khi bind, nhưng khả năng và trạng thái tính năng phụ thuộc phiên bản Java. Hãy kiểm tra JDK mục tiêu trước khi chọn.

Dù dùng platform thread hay virtual thread, nguyên tắc vẫn là xác định phạm vi context, không để dữ liệu request cũ tồn tại ngoài phạm vi đó và không mang resource không thread-safe sang tác vụ khác.

## 17. Các lỗi thường gặp

**Đặt ThreadLocal nhưng quên remove().** Worker thread được tái sử dụng nên giá trị cũ có thể đi sang request mới. Đặt cleanup trong finally tại ranh giới request/task.

**Chỉ gọi set(null).** Entry có thể vẫn tồn tại. Dùng remove() khi mục tiêu là xóa giá trị khỏi thread hiện tại.

**Gọi remove() trên thread điều phối.** Thao tác chỉ ảnh hưởng thread gọi nó. Cleanup phải chạy trên thread đang sở hữu context.

**Dùng InheritableThreadLocal cho thread pool.** Giá trị được kế thừa khi tạo thread, không phải mỗi lần submit task. Worker được tái sử dụng có thể giữ context cũ.

**Trông chờ ThreadLocal tự truyền qua CompletableFuture.** Callback có thể chạy trên thread khác. Truyền context tường minh hoặc dùng context propagation được hỗ trợ.

**Lưu EntityManager, Session hoặc Connection trong ThreadLocal mà không quản lý lifecycle.** Remove reference không đóng resource. Phải kết thúc transaction và đóng resource đúng owner.

**Xóa context quá sớm.** Nếu cleanup xảy ra trước khi logging, tracing hoặc phần xử lý cuối cùng hoàn tất, log có thể mất correlation ID. Đặt cleanup ở cuối pipeline phù hợp.

**Chỉ cleanup trên đường chạy thành công.** Exception, timeout, cancellation và early return đều có thể bỏ qua cleanup nếu không dùng finally hoặc hook tương đương.

**Dùng một ThreadLocal mutable cho nhiều request async.** Các task có thể sửa chung object context hoặc sử dụng dữ liệu đã lỗi thời. Dùng snapshot bất biến và phạm vi rõ ràng.

**Checkpoint khi task vẫn đang chạy.** finally chưa được thực thi và context có thể còn gắn với worker. Quiesce và drain task trước checkpoint.

**Cố xóa mọi ThreadLocal bằng reflection.** Đây là cách phụ thuộc implementation và có thể phá framework. Cleanup tại owner và lifecycle boundary.

## 18. Quy trình kiểm thử ThreadLocal với CRaC

Kiểm thử cần chứng minh rằng context của request kết thúc không xuất hiện trong request tiếp theo, kể cả sau checkpoint/restore.

### Kiểm thử tái sử dụng cùng worker

1. Dùng một executor chỉ có một worker thread.
2. Submit task A, đặt request ID và tenant ID.
3. Kết thúc task A và chạy cleanup.
4. Submit task B trên cùng executor.
5. Kiểm tra task B không đọc được request ID hoặc tenant ID của task A.
6. Lặp lại khi task A ném exception, bị cancel hoặc timeout.

Dùng một worker giúp bảo đảm hai task chạy trên cùng thread, từ đó tái hiện rõ lỗi stale ThreadLocal.

### Kiểm thử thiếu cleanup

Trong môi trường test riêng, cố ý bỏ remove() trong task A. Cho task B chạy trên cùng worker và xác nhận test phát hiện context cũ. Không đưa lỗi cố ý này vào production.

### Kiểm thử context propagation

Submit một task async từ request có context. Xác nhận chỉ những trường đã chọn được truyền sang worker, và sau task hoàn tất, worker không giữ context đó cho task tiếp theo.

### Kiểm thử checkpoint/restore

1. Khởi chạy ứng dụng bằng JDK CRaC tương thích.
2. Gửi request và xác nhận cleanup đã xảy ra khi request kết thúc.
3. Quiesce ingress và drain executor.
4. Tạo checkpoint ở trạng thái không còn task request hoạt động.
5. Restore tiến trình.
6. Gửi request mới trên worker đã được phục hồi hoặc worker mới.
7. Xác nhận request mới không thấy context cũ và log/tracing mang đúng request ID.
8. Kiểm thử thêm trường hợp callback hoặc task drain thất bại; ứng dụng không được báo ready khi trạng thái worker chưa an toàn.

Các metric có thể theo dõi:

- Số task đang chạy và số task đang chờ.
- Số lần cleanup context được gọi.
- Số lần task kết thúc bằng exception hoặc cancellation.
- Số lỗi phát hiện context cũ trong test.
- Thời gian drain executor trước checkpoint.
- Số lỗi worker hoặc context propagation sau restore.
- Request ID/tenant ID trong log của từng request, theo chính sách bảo vệ dữ liệu.

Không ghi token hoặc dữ liệu nhạy cảm vào log chỉ để xác minh cleanup. Dùng mã giả lập trong test và chỉ log trạng thái có/không có context hoặc một ID kiểm thử an toàn.

## 19. Checklist quản lý ThreadLocal

- [ ] Mỗi ThreadLocal có mục đích và owner rõ ràng chưa?
- [ ] Đã xác định dữ liệu nào là request context và dữ liệu nào là worker/application state chưa?
- [ ] Mọi request/task có set context đều có cleanup trong finally chưa?
- [ ] Cleanup dùng remove() hoặc khôi phục context trước đó đúng theo nesting chưa?
- [ ] Cleanup chạy trên chính thread sở hữu ThreadLocal chưa?
- [ ] Thread pool có wrapper để truyền và xóa context giữa các task không?
- [ ] InheritableThreadLocal có đang bị dùng sai như cơ chế truyền context cho executor không?
- [ ] CompletableFuture/reactive task có context propagation rõ ràng không?
- [ ] ThreadLocal có giữ EntityManager, Session, Connection hoặc object lớn không?
- [ ] Tài nguyên được đóng đúng owner trước khi xóa reference không?
- [ ] Request ingress và worker task có được drain trước checkpoint không?
- [ ] Không dùng reflection để quét ThreadLocalMap nội bộ của thread không?
- [ ] Sau restore, worker và context propagation đã được xác minh trước readiness chưa?
- [ ] Đã kiểm thử request kế tiếp trên cùng worker sau cả success và exception chưa?

## Kết luận

ThreadLocal gắn giá trị với thread, không gắn với vòng đời request. Trong ứng dụng dùng thread pool, worker thread có thể xử lý nhiều request liên tiếp nên dữ liệu cũ sẽ còn tồn tại nếu ứng dụng không cleanup. remove() chỉ tác động đến thread hiện tại; vì vậy cleanup cần được thực hiện trên chính worker ở ranh giới kết thúc request hoặc task.

Với CRaC, trạng thái thread và dữ liệu gắn với thread cần được đưa vào kế hoạch checkpoint. Ứng dụng nên ngừng nhận công việc mới, drain request và task đang chạy, bảo đảm finally và cleanup hook đã hoàn tất rồi mới checkpoint. Sau restore, chỉ mở lại ingress khi worker và các cơ chế context propagation sẵn sàng. Dùng ThreadLocal có phạm vi rõ ràng, cleanup có chủ đích và truyền context tường minh qua async boundary sẽ giúp tránh rò rỉ dữ liệu giữa request, giảm giữ tài nguyên và duy trì tính đúng đắn sau restore.
