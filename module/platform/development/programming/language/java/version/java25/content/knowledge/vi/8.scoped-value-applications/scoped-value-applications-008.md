# Đánh giá chi phí truyền ngữ cảnh và tránh biến ScopedValue thành trạng thái toàn cục

## 1. Bối cảnh và mục tiêu

Bài thuộc chương **Ứng dụng ScopedValue** của module **JAVA_VERSION_JAVA25**. Java 25 có nhiều khả năng cho phát triển Java hiện đại như compact source files, module import declarations, flexible constructor bodies, ScopedValue, API dẫn xuất khóa, AOT cache và quan sát runtime bằng JFR. Ở đây ta tập trung vào JEP 506 — Scoped Values, đã trở thành tính năng chính thức trong Java 25.

ScopedValue giải quyết một vấn đề cụ thể: truyền dữ liệu theo ngữ cảnh qua nhiều lời gọi phương thức mà không phải thêm cùng một tham số vào toàn bộ chuỗi method. Ví dụ, request đi qua HTTP filter, controller, service, pricing, audit và logger; nhiều tầng cần requestId, tenantId hoặc locale để ghi log và định dạng thông báo.

Nếu truyền từng giá trị qua tất cả method, chữ ký sẽ dài. Nếu dùng ThreadLocal hoặc biến static mutable, dữ liệu có thể tồn tại quá phạm vi yêu cầu, khó kiểm soát khi chạy bất đồng bộ và dễ tạo phụ thuộc ẩn.

ScopedValue cung cấp một lựa chọn có **phạm vi động**: bind một giá trị trong thời gian thực thi của một thao tác; những method được gọi trong phạm vi ấy và có quyền truy cập key có thể đọc giá trị. Khi thao tác kết thúc — bình thường hoặc bằng exception — binding được khôi phục về trạng thái trước đó.

**Trạng thái Java 25:** ScopedValue là API chính thức từ JEP 506, không còn preview. Bản thân ScopedValue không cần --enable-preview. Tuy nhiên, StructuredTaskScope dùng để truyền binding sang tác vụ con là preview lần thứ năm trong Java 25 (JEP 505); chỉ phần ví dụ structured concurrency mới cần cờ preview.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt truyền tham số tường minh, ThreadLocal và ScopedValue theo khả năng đọc hiểu, vòng đời và chi phí.
2. Giải thích vì sao một key static final không đồng nghĩa với trạng thái request toàn cục.
3. Tạo context immutable và giới hạn quyền truy cập vào key như một capability.
4. Bind, đọc, kiểm tra trạng thái và rebind ScopedValue trong các phạm vi lồng nhau.
5. Nhận diện giới hạn truyền context qua thread, executor, virtual thread và structured task scope.
6. Thiết kế benchmark JMH công bằng để đánh giá chi phí bind/get/unbind thay vì tuyên bố ScopedValue luôn nhanh hơn.
7. Đọc kết quả benchmark, cache behavior và chi phí cấp request mà không tối ưu dựa trên suy đoán.
8. Tránh đưa mọi dữ liệu nghiệp vụ vào một context ẩn, tránh giữ tham chiếu request trong object sống lâu và tránh làm key thành API công khai toàn hệ thống.

## 2. Hiểu đúng ScopedValue: key tĩnh, binding có thời hạn

### 2.1. Một binding sống trong dynamic scope

Ví dụ cơ bản theo API Java 25:

~~~java
import java.lang.ScopedValue;

class ScopedGreeting {

    private static final ScopedValue<String> NAME =
        ScopedValue.newInstance();

    static void greet() {
        System.out.println("Hello " + NAME.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(NAME, "Duke").run(ScopedGreeting::greet);
    }
}
~~~

Khi chạy, NAME được bind với giá trị "Duke" trong thời gian run thực thi. greet() không nhận tham số name nhưng vẫn đọc được binding thông qua key NAME.

Sau khi run kết thúc, binding quay về trạng thái trước đó. Nếu trước đó NAME chưa được bind, nó trở lại trạng thái unbound. Việc khôi phục xảy ra cả khi run kết thúc bình thường hoặc ném exception.

Một phương thức cần trả kết quả có thể dùng call:

~~~java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

static String createAuditMessage() {
    return "request=" + REQUEST_ID.get();
}

static String audit(String requestId) {
    return ScopedValue.where(REQUEST_ID, requestId)
        .call(ScopedGreeting::createAuditMessage);
}
~~~

run nhận Runnable; call nhận ScopedValue.CallableOp và trả kết quả. Không cần tự viết try/finally để gỡ binding.

### 2.2. Key và value là hai thứ khác nhau

~~~text
private static final ScopedValue<RequestContext> CURRENT
       |
       +-- key/capability dùng để truy cập binding

Trong thread đang thực thi:
  CURRENT -> RequestContext(requestId="r-42", tenant="tenant-a")

Trong thread khác:
  CURRENT có thể chưa được bind hoặc có binding riêng
~~~

- ScopedValue object là **key** định danh một binding.
- Giá trị request cụ thể được gắn với key trong **thread hiện tại** và trong phạm vi thực thi tương ứng.
- Key có thể là static final để các method trong cùng class/nest truy cập thống nhất.
- Key không tự lưu một request context mutable dùng chung cho mọi request.
- Cùng một key có thể có giá trị khác nhau ở hai thread; mỗi thread nhìn binding của chính nó.

Javadoc khuyến nghị xem ScopedValue như **capability**: code giữ key có quyền đọc giá trị khi key được bind. Vì vậy nên giới hạn visibility, thường dùng private static final trong class hoặc nest và cung cấp các method facade có kiểm soát.

### 2.3. Vì sao không phải trạng thái toàn cục?

| Thiết kế | Nơi giữ dữ liệu | Vòng đời | Rủi ro chính |
| --- | --- | --- | --- |
| static volatile RequestContext CURRENT | Một field dùng chung toàn JVM | Không tự kết thúc | Request ghi đè nhau, race condition, dữ liệu rò giữa người dùng |
| ConcurrentHashMap<Thread, Context> | Registry global theo thread | Phải tự dọn | Rò bộ nhớ, stale thread, dọn sai thời điểm |
| ThreadLocal<Context> | Binding theo thread | Có thể kéo dài sau method | Phải remove đúng lúc, thread pool tái sử dụng |
| ScopedValue<Context> | Binding theo thread trong dynamic scope | Tự khôi phục khi run/call kết thúc | Phải giới hạn key, value và phạm vi; không tự truyền qua mọi async boundary |

**Một key static không phải là một value static.** Nếu key là private, immutable và dữ liệu được bind qua where(...).run/call(...), thì mỗi request có binding riêng trong thời gian đã định. Trái lại, một biến static mutable lưu trực tiếp request hiện tại là trạng thái toàn cục và không an toàn khi nhiều request chạy đồng thời.

## 3. Ba cách truyền context và trade-off

### 3.1. Truyền tham số tường minh

~~~java
record RequestContext(String requestId, String tenantId) {}

String buildInvoice(RequestContext context) {
    return pricingService.calculate(context);
}

String calculate(RequestContext context) {
    return auditService.describe(context);
}

String describe(RequestContext context) {
    return "request=" + context.requestId();
}
~~~

**Ưu điểm:**

- Phụ thuộc hiện rõ trong chữ ký method.
- Dễ test unit, dễ gọi từ nhiều nguồn và dễ đọc khi context là dữ liệu nghiệp vụ thực sự cần thiết.
- Không có lookup ngầm hoặc key ẩn.
- Compiler hỗ trợ kiểm tra type và caller phải cung cấp dữ liệu.

**Chi phí:**

- Mỗi tầng trung gian phải nhận và truyền tiếp tham số dù bản thân tầng đó không sử dụng dữ liệu.
- Nhiều loại context có thể làm method signature dài.
- Khi thêm trường vào context hoặc thêm một context mới, có thể phải sửa nhiều method/caller.

Truyền tham số không phải cách lỗi thời. Với dữ liệu là **đầu vào nghiệp vụ trực tiếp** (ví dụ OrderId để tính đơn hàng), truyền tường minh thường vẫn là lựa chọn tốt nhất.

### 3.2. ThreadLocal

~~~java
private static final ThreadLocal<RequestContext> CURRENT =
    new ThreadLocal<>();

static void handle(RequestContext context) {
    CURRENT.set(context);
    try {
        service.process();
    } finally {
        CURRENT.remove();
    }
}

static RequestContext current() {
    return CURRENT.get();
}
~~~

ThreadLocal cũng cho phép method sâu đọc dữ liệu mà không thêm tham số. Tuy nhiên, dữ liệu có vòng đời gắn với thread và **không tự biến mất khi method nghiệp vụ kết thúc**. Nếu quên remove(), thread pool có thể tái sử dụng worker và request tiếp theo nhìn thấy dữ liệu cũ.

ThreadLocal không phải lúc nào cũng sai. Nó vẫn có thể phù hợp với dữ liệu thực sự gắn với thread hoặc tích hợp thư viện cũ cần API này. Nhưng với mục tiêu truyền dữ liệu một chiều từ caller tới callee trong một phạm vi rõ, Javadoc Java 25 khuyến nghị cân nhắc ScopedValue.

### 3.3. ScopedValue

~~~java
private static final ScopedValue<RequestContext> CURRENT =
    ScopedValue.newInstance();

static void handle(RequestContext context) {
    ScopedValue.where(CURRENT, context).run(service::process);
}

static RequestContext current() {
    return CURRENT.get();
}
~~~

CURRENT.get() chỉ thành công khi key đã được bind trong thread hiện tại. Nếu chưa bind, get() ném NoSuchElementException. Có thể dùng isBound(), orElse(...) hoặc orElseThrow(...) khi binding là tùy chọn.

ScopedValue không cung cấp thao tác set tùy ý ở bất kỳ tầng nào. Việc tạo binding được gom tại boundary và tự khôi phục theo dynamic scope. Điều này giảm khả năng một method sâu âm thầm thay đổi context mà caller đã thiết lập.

### 3.4. Bảng chọn theo nhu cầu

| Nhu cầu | Lựa chọn nên cân nhắc trước | Lý do |
| --- | --- | --- |
| Dữ liệu là đầu vào nghiệp vụ bắt buộc của method | Tham số tường minh | Dependency rõ, test dễ |
| Dữ liệu cross-cutting cần đọc ở nhiều tầng, chỉ truyền một chiều | ScopedValue | Scope tự khôi phục, không cần plumbing qua từng chữ ký |
| Tích hợp thư viện cũ phụ thuộc thread-bound state | ThreadLocal có quản lý vòng đời | Tương thích API hiện hữu |
| Dữ liệu cần truyền qua task con trong cấu trúc đồng bộ | ScopedValue + StructuredTaskScope (JDK 25: preview) | Binding được kế thừa theo task scope |
| Dữ liệu cần truyền sang executor/thread pool tùy ý | Context propagation của framework hoặc truyền tường minh | ScopedValue không tự kế thừa qua mọi thread hop |
| Dependency là một phần contract public của service | Tham số hoặc object dependency rõ ràng | Không che giấu yêu cầu nghiệp vụ |

## 4. Tạo RequestContext immutable và giới hạn capability

### 4.1. Định nghĩa record bất biến

~~~java
import java.util.Locale;
import java.util.Objects;

public record RequestContext(
    String requestId,
    String tenantId,
    Locale locale
) {
    public RequestContext {
        requestId = Objects.requireNonNull(requestId, "requestId").strip();
        tenantId = Objects.requireNonNull(tenantId, "tenantId").strip();
        locale = Objects.requireNonNull(locale, "locale");

        if (requestId.isEmpty()) {
            throw new IllegalArgumentException("requestId must not be blank");
        }
        if (tenantId.isEmpty()) {
            throw new IllegalArgumentException("tenantId must not be blank");
        }
    }
}
~~~

Các component trong ví dụ là String và Locale, đều phù hợp làm dữ liệu immutable. Nếu record có Map hoặc List, hãy dùng defensive copy (ví dụ Map.copyOf, List.copyOf) và bảo đảm phần tử cũng immutable. Record tự nó không tạo deep immutability.

### 4.2. Đóng key trong một facade

~~~java
import java.lang.ScopedValue;
import java.util.Objects;

public final class RequestContextScope {

    private static final ScopedValue<RequestContext> CURRENT =
        ScopedValue.newInstance();

    private RequestContextScope() {}

    public static void run(RequestContext context, Runnable action) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");
        ScopedValue.where(CURRENT, context).run(action);
    }

    public static <R, X extends Throwable> R call(
            RequestContext context,
            ScopedValue.CallableOp<? extends R, X> action) throws X {

        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");
        return ScopedValue.where(CURRENT, context).call(action);
    }

    public static RequestContext current() {
        return CURRENT.get();
    }

    public static boolean isBound() {
        return CURRENT.isBound();
    }
}
~~~

Facade giữ key ở chế độ private. Caller có thể thiết lập scope thông qua run hoặc call và đọc context qua current(); caller không thể giữ key để tự ý bind lại ở mọi nơi.

Nếu muốn thu hẹp quyền đọc hơn nữa, có thể đặt facade và các service tiêu thụ trong một package/module có visibility rõ ràng. Không nên public key chỉ để code ở mọi nơi gọi ScopedValue.where(...).

### 4.3. Bind tại boundary, đọc ở tầng sâu

~~~java
import java.util.Locale;

class RequestHandler {

    private final OrderService orderService = new OrderService();

    void handle(String requestId, String tenantId) {
        RequestContext context = new RequestContext(
            requestId,
            tenantId,
            Locale.forLanguageTag("vi-VN")
        );

        RequestContextScope.run(context, () -> orderService.process());
    }
}

class OrderService {

    private final PricingService pricingService = new PricingService();

    void process() {
        RequestContext context = RequestContextScope.current();
        pricingService.calculate();

        System.out.println(
            "request=" + context.requestId()
                + ", tenant=" + context.tenantId()
        );
    }
}

class PricingService {

    void calculate() {
        String requestId = RequestContextScope.current().requestId();
        System.out.println("pricing for " + requestId);
    }
}
~~~

Ví dụ đơn giản hóa dependency construction để tập trung vào scope. Trong ứng dụng Spring thực tế, dùng constructor injection cho OrderService và PricingService; ScopedValue không thay thế DI container.

**Nguyên tắc:** boundary tạo context một lần, các tầng cần thông tin cross-cutting đọc qua facade. Method nghiệp vụ vẫn nhận dữ liệu nghiệp vụ trực tiếp như orderId, amount hoặc pricingPolicy bằng tham số rõ ràng.

## 5. Dynamic scope, nested binding và khôi phục

### 5.1. Binding lồng nhau

Một scope bên trong có thể rebind cùng key với giá trị mới:

~~~java
private static final ScopedValue<String> TENANT =
    ScopedValue.newInstance();

static void demo() {
    ScopedValue.where(TENANT, "tenant-A").run(() -> {
        System.out.println(TENANT.get()); // tenant-A

        ScopedValue.where(TENANT, "tenant-B").run(() -> {
            System.out.println(TENANT.get()); // tenant-B
        });

        System.out.println(TENANT.get()); // tenant-A
    });
}
~~~

Khi scope trong kết thúc, binding trước đó được khôi phục. Đây là lý do nên coi ScopedValue là dữ liệu có phạm vi, không phải một slot global để cập nhật.

### 5.2. Khôi phục khi exception

~~~java
private static final ScopedValue<String> REQUEST =
    ScopedValue.newInstance();

static void failingOperation() {
    ScopedValue.where(REQUEST, "r-100").run(() -> {
        throw new IllegalStateException("boom");
    });
}

static void mainDemo() {
    try {
        failingOperation();
    } catch (IllegalStateException expected) {
        // Binding đã được khôi phục khi run kết thúc.
    }

    if (!REQUEST.isBound()) {
        System.out.println("No request context is bound");
    }
}
~~~

Không cần viết finally { REQUEST.remove(); } như với ThreadLocal. API quản lý vòng đời binding tự động.

### 5.3. Khi nào dùng get, isBound và orElse?

| API | Khi nào dùng |
| --- | --- |
| get() | Context bắt buộc; thiếu binding là lỗi lập trình hoặc lỗi boundary |
| isBound() | Cần phân biệt code đang chạy trong/ngoài request scope |
| orElse(defaultValue) | Có fallback hợp lệ, ví dụ locale mặc định |
| orElseThrow(...) | Muốn exception có ý nghĩa rõ khi context bắt buộc nhưng thiếu |

Không lạm dụng orElse(null) cho context bắt buộc. Nó biến lỗi thiết lập scope thành null phát hiện muộn, khó tìm nguyên nhân.

## 6. Truyền context qua concurrency: giới hạn rất quan trọng

### 6.1. Binding theo thread, không phải theo JVM

Javadoc Java 25 xác định binding là per-thread. Hai thread có thể cùng sử dụng một key nhưng đọc các giá trị khác nhau. Việc bind trong thread A không tự động làm thread B nhìn thấy giá trị đó.

| Cách chuyển thực thi | Có tự kế thừa binding không? | Cách xử lý |
| --- | --- | --- |
| Gọi method đồng bộ trong cùng thread | Có | Dynamic scope tiếp tục có hiệu lực |
| Rebind trong scope lồng nhau cùng thread | Có, giá trị trong và ngoài được khôi phục đúng | Dùng where(...).run/call(...) |
| Thread.startVirtualThread(...) hoặc tạo thread độc lập | Không nên giả định tự kế thừa | Truyền context tường minh hoặc dùng cơ chế structured được hỗ trợ |
| ExecutorService.submit(...) / thread pool | Không tự động truyền binding theo task | Truyền context/wrapper hoặc cơ chế propagation của framework |
| CompletableFuture.supplyAsync(...) | Không tự động bảo đảm kế thừa | Dùng executor/context wrapper phù hợp |
| StructuredTaskScope.fork(...) trong Java 25 | Có kế thừa binding được capture khi mở scope | API StructuredTaskScope của JDK 25 vẫn preview |

Đặc biệt, không nhầm virtual thread với structured task. Việc thread là virtual không có nghĩa mọi binding ScopedValue tự động truyền sang thread đó. Cơ chế kế thừa được Javadoc nêu rõ khi dùng StructuredTaskScope.

### 6.2. StructuredTaskScope trong Java 25 là preview

Ví dụ minh họa:

~~~java
import java.lang.ScopedValue;
import java.util.concurrent.StructuredTaskScope;

private static final ScopedValue<RequestContext> CURRENT =
    ScopedValue.newInstance();

static Report loadDashboard(RequestContext context)
        throws InterruptedException {

    return ScopedValue.where(CURRENT, context).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> loadProfile());
            var permissions = scope.fork(() -> loadPermissions());

            scope.join();

            return new Report(profile.get(), permissions.get());
        }
    });
}
~~~

Khi scope được mở trong lúc CURRENT đang bind, các task được tạo bằng fork kế thừa binding đó. Task con có thể đọc CURRENT.get() mà không phải truyền context qua từng lambda/method.

**Trạng thái JDK 25:** ScopedValue đã final (JEP 506), còn StructuredTaskScope là preview lần thứ năm (JEP 505). Nếu biên dịch và chạy đoạn kết hợp này trên JDK 25:

~~~bash
javac --release 25 --enable-preview -d out DashboardTasks.java
java --enable-preview -cp out DashboardTasks
~~~

Cờ preview chỉ cần vì StructuredTaskScope. Một chương trình chỉ dùng ScopedValue không cần --enable-preview. Kiểm tra JEP/Javadoc của JDK đích trước khi nâng version; không sao chép nguyên API của lần preview trước.

### 6.3. Binding được capture khi mở scope

StructuredTaskScope capture binding hiện tại khi scope được tạo. JDK kiểm tra binding khi fork để bảo đảm task không kế thừa một cấu hình khác với cấu hình đã capture. Điều này giúp vòng đời của binding phù hợp với vòng đời các task con.

Các task trong scope phải kết thúc trước khi scope đóng. Nếu mở scope rồi để task chạy vượt khỏi scope hoặc không chờ đúng lifecycle, ứng dụng sẽ vi phạm cấu trúc concurrency. ScopedValue không phải cơ chế để gửi context vào background job tồn tại lâu hơn request.

### 6.4. Giá trị dùng chung phải immutable hoặc được đồng bộ

Javadoc yêu cầu value được chia sẻ qua thread phải là immutable object hoặc mọi truy cập phải được đồng bộ thích hợp.

Tốt:

~~~java
record RequestContext(String requestId, String tenantId) {}
~~~

Cần thận trọng:

~~~java
record UnsafeContext(
    String requestId,
    java.util.Map<String, String> mutableAttributes
) {}
~~~

Nếu map được giữ mutable và nhiều task con sửa cùng lúc, việc binding tự động kế thừa không biến map thành thread-safe. Dùng Map.copyOf và immutable values, hoặc một thiết kế đồng bộ rõ ràng nếu mutation thực sự cần thiết.

## 7. Đánh giá chi phí: đừng mặc định ScopedValue nhanh hơn

### 7.1. Những khoản chi phí khác nhau

| Cách truyền | Chi phí ở call site / boundary | Chi phí khi đọc | Chi phí vòng đời |
| --- | --- | --- | --- |
| Tham số tường minh | Truyền reference qua từng method | Đọc local/parameter | Không có bind/unbind |
| ThreadLocal | set ở đầu và remove cuối | get theo thread | Phải dọn đúng lúc; có thể giữ dữ liệu quá lâu |
| ScopedValue | Tạo binding/Carrier và vào dynamic scope | get; lần đầu có thể tìm trong enclosing scopes | Tự khôi phục khi scope kết thúc |
| ScopedValue + StructuredTaskScope | Bind context và mở task scope | Child đọc binding đã kế thừa | Có chi phí mở/join/đóng task scope và tạo thread/task |

Chi phí thực tế phụ thuộc:

- Độ sâu call chain và số lần method đọc context.
- Số key đang được bind và cách chúng được dùng luân phiên.
- Tần suất tạo/đóng scope so với số lần get.
- Có tạo value record mới mỗi request hay tái sử dụng value immutable.
- Có fork child task hay chỉ chạy đồng bộ.
- Loại thread, scheduler, executor, JDK build, CPU và tải ứng dụng.
- JIT warmup, allocation rate, GC và phần công việc nghiệp vụ thực tế.

**Không có kết luận tổng quát rằng ScopedValue luôn nhanh hơn truyền tham số.** Truyền tham số thường rất rẻ và có thể được JIT inline/optimize tốt. ScopedValue mang lại lợi ích về cách tổ chức và an toàn vòng đời; lợi ích hiệu năng phải được đo trong workload phù hợp.

### 7.2. Chi tiết cache trong JDK 25

Implementation Note của Javadoc Java 25 cho biết:

1. Lần đầu get() có thể tìm binding trong các scope bao quanh để xác định binding trong cùng.
2. Kết quả được cache trong một **cache nhỏ theo thread**.
3. Các lần get() tiếp theo cho cùng key thường rất nhanh nếu cache hit.
4. Nếu chương trình sử dụng luân phiên quá nhiều ScopedValue keys, cache hit rate có thể thấp và hiệu năng giảm.
5. Thiết kế này giúp việc kế thừa binding qua StructuredTaskScope rất nhanh; về cơ bản chi phí kế thừa gần với sao chép pointer.

Javadoc cũng nêu cache mặc định 16 entries trong reference implementation JDK 25 và một số system property để điều chỉnh. Đây là **implementation detail**, không phải hợp đồng API mà ứng dụng nên dựa vào. Không chỉnh java.lang.ScopedValue.cacheSize hay jdk.preserveScopedValueCache chỉ vì thấy một benchmark nhỏ chậm; trước hết đo số key, cache behavior và mức dùng bộ nhớ trên đúng JDK/vendor.

### 7.3. Gom nhiều giá trị thành một record

Nếu cần truyền nhiều thông tin cross-cutting, Javadoc khuyên cân nhắc một record gom chúng và bind một ScopedValue thay vì bind nhiều key riêng lẻ.

~~~java
record ExecutionContext(
    String requestId,
    String tenantId,
    java.util.Locale locale,
    String correlationId
) {}

private static final ScopedValue<ExecutionContext> CONTEXT =
    ScopedValue.newInstance();
~~~

Sau đó:

~~~java
ScopedValue.where(CONTEXT, context).run(() -> {
    auditService.write();
    pricingService.calculate();
});
~~~

Lợi ích:

- Ít key được bind và dùng luân phiên.
- Một value object có thể validate invariant tập trung.
- Dễ review context contract và test.
- Có thể dùng record immutable với component immutable.

Không biến record thành một túi toàn cục chứa mọi thứ. Chỉ thêm trường khi nó có ý nghĩa cross-cutting, cần thiết cho nhiều tầng và được quản lý rõ về quyền truy cập.

## 8. Benchmark công bằng bằng JMH

### 8.1. Cần đo điều gì?

Thiết kế ba trường hợp tương đương:

1. **Explicit parameter:** truyền cùng một reference qua một chuỗi method trung gian.
2. **ScopedValue:** bind một lần ở boundary, đọc ở tầng cuối bằng get().
3. **ThreadLocal:** set ở boundary, đọc ở tầng cuối, remove trong finally.

Đặt cùng một RequestContext và cùng công việc ở tầng cuối. Không đưa logging, I/O, database, network hoặc object allocation không liên quan vào một phương án mà không đưa vào các phương án còn lại.

### 8.2. Ví dụ benchmark skeleton

Đây là một benchmark JMH minh họa để phát triển thành project benchmark riêng:

~~~java
import java.lang.ScopedValue;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class ContextAccessBenchmark {

    private static final ScopedValue<RequestContext> CURRENT =
        ScopedValue.newInstance();

    private final ThreadLocal<RequestContext> local =
        new ThreadLocal<>();

    private final RequestContext context =
        new RequestContext("r-42", "tenant-a", Locale.ROOT);

    @Benchmark
    public void explicitParameter(Blackhole blackhole) {
        blackhole.consume(explicitLayer1(context));
    }

    @Benchmark
    public void scopedValue(Blackhole blackhole) {
        ScopedValue.where(CURRENT, context)
            .run(() -> blackhole.consume(scopedLayer1()));
    }

    @Benchmark
    public void threadLocal(Blackhole blackhole) {
        local.set(context);
        try {
            blackhole.consume(threadLocalLayer1());
        } finally {
            local.remove();
        }
    }

    private static String explicitLayer1(RequestContext c) {
        return explicitLayer2(c);
    }

    private static String explicitLayer2(RequestContext c) {
        return explicitLayer3(c);
    }

    private static String explicitLayer3(RequestContext c) {
        return c.requestId();
    }

    private static String scopedLayer1() {
        return scopedLayer2();
    }

    private static String scopedLayer2() {
        return scopedLayer3();
    }

    private static String scopedLayer3() {
        return CURRENT.get().requestId();
    }

    private String threadLocalLayer1() {
        return threadLocalLayer2();
    }

    private String threadLocalLayer2() {
        return threadLocalLayer3();
    }

    private String threadLocalLayer3() {
        return local.get().requestId();
    }

    record RequestContext(
        String requestId,
        String tenantId,
        Locale locale
    ) {}
}
~~~

Benchmark này đo **một boundary và một lần đọc sâu** trong ba mô hình. Nó chưa đo một ứng dụng web hoàn chỉnh, chưa đo structured child task, và chưa đại diện cho mọi số lượng key/depth. JIT có thể inline method chain; đó là hành vi tối ưu thực tế cần giữ lại, không nên ngăn inline chỉ để ép kết quả theo giả định.

### 8.3. Cách chạy và lưu bằng chứng

Dùng project JMH độc lập theo hướng dẫn chính thức OpenJDK JMH; không chỉ thêm jmh-core vào project thường rồi bấm Run trong IDE.

Sau khi tạo benchmark project bằng archetype và build executable benchmark JAR:

~~~bash
java -jar target/benchmarks.jar ContextAccessBenchmark -rf json -rff scoped-value-results.json
~~~

Các annotation ví dụ có warmup, measurement và fork. Khi chạy thật, hãy lưu:

- JDK vendor, version/build và JVM flags.
- OS/kernel, CPU model, số core, memory và power mode.
- JMH version, warmup/measurement iterations, fork count, thread count.
- Workload, số lần đọc context, độ sâu call chain và số key.
- Throughput/average time hoặc sample-time distribution tùy câu hỏi.
- Allocation rate, GC behavior nếu benchmark cần so sánh.
- Kết quả raw JSON/CSV, không chỉ chụp màn hình một con số.

**Không đo bằng System.nanoTime() quanh một lần gọi hoặc bằng JUnit test.** Một lần chạy quá ngắn chịu ảnh hưởng JIT compilation, class loading, GC, CPU scheduling và nhiễu nền. JMH được thiết kế cho microbenchmark JVM, có warmup/fork và sinh harness để giảm các sai lệch phổ biến.

### 8.4. Benchmark các kịch bản khác nhau riêng biệt

| Kịch bản | Câu hỏi | Không nên trộn với |
| --- | --- | --- |
| Bind + get + unbind trong một request | Chi phí context scope đồng bộ | Tạo thread mới |
| Nhiều lần get trong cùng scope | Cache behavior và tần suất đọc | I/O/network |
| Nhiều ScopedValue keys dùng luân phiên | Cache hit/miss khi nhiều key | Chỉ một key cố định |
| Truyền context sang child task có cấu trúc | Chi phí scope/fork/join và inheritance | Benchmark một lần get đơn giản |
| ThreadLocal trong thread pool | Chi phí set/get/remove và lỗi cleanup | InheritableThreadLocal tạo thread mới |
| End-to-end HTTP request | Tác động ở mức ứng dụng | Microbenchmark method đơn lẻ |

Nếu benchmark inheritance, so sánh cùng số task và cùng payload. StructuredTaskScope trong JDK 25 là preview nên phải ghi rõ --enable-preview, JDK build và API version trong kết quả. Không kết luận rằng việc kế thừa ScopedValue có chi phí giống việc tạo thread; đó là hai khoản riêng.

## 9. Tránh biến ScopedValue thành trạng thái toàn cục

### 9.1. Những anti-pattern nên tránh

| Anti-pattern | Vấn đề | Cách thiết kế lại |
| --- | --- | --- |
| Public key static ScopedValue dùng khắp ứng dụng | Bất kỳ code nào giữ key đều có thể đọc/rebind; capability bị lan rộng | private static final và facade có giới hạn |
| Một context chứa mọi thứ: request, session, entity, service, token | Context phình to, lẫn dữ liệu mutable và dependency | Chỉ chứa metadata immutable thực sự cross-cutting |
| Lưu request context trong static volatile | Giá trị dùng chung giữa mọi request | Binding ScopedValue trong scope request |
| Dùng ScopedValue để thay mọi tham số method | Dependency nghiệp vụ trở nên ẩn | Chỉ dùng cho implicit cross-cutting data |
| Bind context ở lúc ứng dụng start rồi để suốt đời | Scope quá rộng, không còn ranh giới request rõ | Bind tại từng operation/request boundary |
| Đưa HttpServletRequest hoặc entity JPA mutable vào context | Giữ tài nguyên/request object và state mutable quá lâu | Trích xuất giá trị nhỏ, immutable |
| Capture context vào singleton/background job | Scope kết thúc nhưng object khác vẫn giữ reference | Truyền snapshot có chủ đích hoặc tạo context riêng cho job |
| Dùng một key cho mọi loại dữ liệu không liên quan | Khó review quyền truy cập và invariant | Chia context theo domain/capability có mục đích |

### 9.2. Key private là một capability

~~~java
public final class TenantContext {

    private static final ScopedValue<String> TENANT_ID =
        ScopedValue.newInstance();

    private TenantContext() {}

    public static void runFor(String tenantId, Runnable action) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        ScopedValue.where(TENANT_ID, tenantId.strip()).run(action);
    }

    public static String requireTenantId() {
        return TENANT_ID.get();
    }
}
~~~

Đây là facade minh họa. Trong ứng dụng đa module, đặt nó trong module hạ tầng/context phù hợp và chỉ export API cần thiết. Không export chính key TENANT_ID.

**Giới hạn bảo mật:** key private giúp hạn chế code có thể truy cập qua API Java thông thường, nhưng không biến giá trị thành bí mật mật mã. Context vẫn có thể bị log, trả về từ method hoặc được capture vào closure/object khác. Không dùng ScopedValue làm secret vault, không đưa password/access token vào context nếu không cần và không ghi context nhạy cảm vào log.

### 9.3. Không giữ dữ liệu lâu hơn scope

Ví dụ cần tránh:

~~~java
class GlobalAuditQueue {
    private RequestContext lastSeen; // Trạng thái sống lâu, giữ request gần nhất.

    void submit() {
        lastSeen = RequestContextScope.current();
        // enqueue object này vào worker chạy sau request
    }
}
~~~

Scope của ScopedValue kết thúc không có nghĩa reference đã được copy vào GlobalAuditQueue sẽ tự biến mất. Nếu cần background work, hãy tạo một message/job immutable chỉ chứa những field cần thiết và truyền tường minh sang job. Đừng dựa vào binding request để cấp context cho một công việc có vòng đời dài hơn request.

### 9.4. Không che giấu dependency nghiệp vụ

Ví dụ service sau khó đọc:

~~~java
// Không rõ method cần tenant để làm gì; phụ thuộc bị ẩn.
void charge(Order order) {
    String tenant = TenantContext.requireTenantId();
    // ...
}
~~~

Nếu tenant là điều kiện trực tiếp để xác định quyền sở hữu và tính đúng đắn của nghiệp vụ, cân nhắc:

~~~java
void charge(TenantId tenantId, Order order) {
    // Dependency nghiệp vụ được thể hiện rõ.
}
~~~

ScopedValue có thể hữu ích cho logging, correlation, locale hoặc metadata xuyên nhiều tầng; nhưng không nên dùng để che giấu mọi đầu vào của business logic. Khi tenant ảnh hưởng security boundary, kiểm tra quyền phải có contract rõ ràng và test độc lập.

## 10. Các tình huống thực tế và cách xử lý

### 10.1. Request đồng bộ trong một thread

Tạo context ở HTTP filter/interceptor; bind trong phạm vi gọi chain tiếp theo; service/logging có thể đọc qua facade. Khi chain trả về hoặc ném exception, binding được khôi phục.

Nếu framework gọi callback sau khi scope đã kết thúc, callback đó không thể giả định binding còn tồn tại. Phải kiểm tra đúng vị trí tạo callback và thời điểm thực thi.

### 10.2. Servlet async hoặc executor

Một request có thể rời thread ban đầu khi sử dụng async dispatch, executor hoặc callback. ScopedValue là per-thread và không tự lan qua mọi ranh giới. Hãy sử dụng cơ chế context propagation được framework hỗ trợ hoặc đóng gói snapshot cần thiết vào task. Không lấy kết quả thử nghiệm với StructuredTaskScope để kết luận ExecutorService cũng kế thừa binding.

### 10.3. Reactive pipeline

Reactive pipeline có thể chuyển giữa nhiều thread trong lúc xử lý. ScopedValue không tự trở thành context của Reactor. Với ứng dụng Reactor/WebFlux, sử dụng Reactor Context hoặc cơ chế context propagation tích hợp, rồi chỉ bridge sang ScopedValue tại boundary đồng bộ phù hợp. Đừng gọi CURRENT.get() ở một scheduler thread bất kỳ và mong nó tự thấy request context của thread phát sinh ban đầu.

### 10.4. Virtual threads

Virtual thread vẫn là thread theo ngữ nghĩa binding per-thread. ScopedValue phù hợp với mô hình request/task có phạm vi rõ và có thể giảm nhu cầu dùng ThreadLocal. Nhưng virtual thread không tự đồng nghĩa với structured concurrency; chỉ những tác vụ được tạo trong cấu trúc hỗ trợ kế thừa mới nhận binding theo JDK 25 API.

### 10.5. Background job / message consumer

Một job được xử lý sau khi request đã kết thúc phải có context riêng, ví dụ:

~~~java
record JobContext(String jobId, String tenantId) {}
~~~

Khi worker bắt đầu, tạo một scope mới từ message/job metadata. Không cố dùng binding của request gốc đã đóng. Với message broker, context propagation qua header/message metadata phải được định nghĩa rõ ở contract của producer/consumer.

## 11. Kiểm thử scope, isolation và lỗi thiết kế

Kiểm thử phải xác nhận cả giá trị được đọc đúng và giá trị không bị rò sang scope/thread khác.

### 11.1. Test binding và khôi phục

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.ScopedValue;
import org.junit.jupiter.api.Test;

class ScopedValueTest {

    private static final ScopedValue<String> REQUEST =
        ScopedValue.newInstance();

    @Test
    void bindingIsVisibleOnlyInsideScope() {
        assertFalse(REQUEST.isBound());

        ScopedValue.where(REQUEST, "r-1").run(() -> {
            assertTrue(REQUEST.isBound());
            assertEquals("r-1", REQUEST.get());
        });

        assertFalse(REQUEST.isBound());
    }

    @Test
    void nestedBindingRestoresOuterValue() {
        ScopedValue.where(REQUEST, "outer").run(() -> {
            assertEquals("outer", REQUEST.get());

            ScopedValue.where(REQUEST, "inner").run(() ->
                assertEquals("inner", REQUEST.get())
            );

            assertEquals("outer", REQUEST.get());
        });
    }

    @Test
    void bindingIsRestoredWhenOperationFails() {
        assertThrows(IllegalStateException.class, () ->
            ScopedValue.where(REQUEST, "r-error").run(() -> {
                assertEquals("r-error", REQUEST.get());
                throw new IllegalStateException("expected");
            })
        );

        assertFalse(REQUEST.isBound());
    }

    @Test
    void getOutsideScopeFails() {
        assertThrows(
            java.util.NoSuchElementException.class,
            REQUEST::get
        );
    }
}
~~~

Test này chỉ dùng ScopedValue final trong Java 25, không cần preview flag.

### 11.2. Test cách ly giữa hai thread

Vì binding per-thread, test có thể chạy hai thread với hai giá trị khác nhau. Cần đồng bộ để tránh test dựa vào timing:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.ScopedValue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class ScopedValueThreadIsolationTest {

    private static final ScopedValue<String> REQUEST =
        ScopedValue.newInstance();

    @Test
    void eachThreadReadsItsOwnBinding() throws InterruptedException {
        var ready = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        var resultA = new AtomicReference<String>();
        var resultB = new AtomicReference<String>();

        Thread a = Thread.ofPlatform().start(() ->
            ScopedValue.where(REQUEST, "A").run(() -> {
                ready.countDown();
                await(release);
                resultA.set(REQUEST.get());
            })
        );

        Thread b = Thread.ofPlatform().start(() ->
            ScopedValue.where(REQUEST, "B").run(() -> {
                ready.countDown();
                await(release);
                resultB.set(REQUEST.get());
            })
        );

        ready.await();
        release.countDown();
        a.join();
        b.join();

        assertEquals("A", resultA.get());
        assertEquals("B", resultB.get());
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new RuntimeException(ex);
        }
    }
}
~~~

Thread.ofPlatform() là API Java hiện hành; ví dụ chỉ chứng minh binding không dùng chung giữa hai thread độc lập. Nó **không** chứng minh thread độc lập tự kế thừa context của thread cha.

### 11.3. Kiểm thử StructuredTaskScope (preview)

Trong một test riêng dùng JDK 25 preview, bind context rồi mở StructuredTaskScope và fork một task. Task con đọc cùng binding; sau scope, binding của thread cha vẫn đúng. Test này phải được compile và chạy với --enable-preview vì StructuredTaskScope, không phải vì ScopedValue.

Khi test, không chỉ assert kết quả task con. Hãy kiểm tra:
- Binding được capture khi mở scope.
- Task con thấy đúng context tại thời điểm fork.
- Rebinding lồng nhau trong task con không thay binding của task cha.
- Task scope được join/close theo cấu trúc.
- Giá trị context là immutable hoặc mọi truy cập mutable đã đồng bộ.

### 11.4. Test không rò context sang request tiếp theo

Trong test tích hợp với thread pool, chạy request A và request B trên cùng worker nếu có thể; sau mỗi request xác nhận boundary đã kết thúc và request tiếp theo chỉ thấy binding của chính nó. Nếu code dùng ThreadLocal, test phải xác nhận remove() ở mọi đường thành công và exception. Với ScopedValue, xác nhận run/call kết thúc thì binding được khôi phục.

## 12. Checklist thiết kế và vận hành

### Trước khi thêm ScopedValue

- [ ] Xác định dữ liệu nào thực sự cross-cutting và cần đọc ở nhiều tầng.
- [ ] Giữ tham số tường minh cho dữ liệu nghiệp vụ trực tiếp.
- [ ] Định nghĩa record/context immutable, chỉ có field cần thiết.
- [ ] Đặt key private static final trong facade/module phù hợp.
- [ ] Chọn một boundary bind rõ ràng (request, command hoặc job).
- [ ] Xác định các đường chạy đồng bộ, executor, reactive và structured concurrency.

### Khi triển khai

- [ ] Dùng run hoặc call để tạo dynamic scope.
- [ ] Dùng get cho context bắt buộc; orElse chỉ khi fallback có ý nghĩa.
- [ ] Không công khai key nếu không cần.
- [ ] Không giữ context trong singleton, static mutable field hoặc object sống lâu.
- [ ] Không đưa mutable payload vào binding chia sẻ giữa các task mà thiếu đồng bộ.
- [ ] Không giả định executor, CompletableFuture hay reactive scheduler tự truyền binding.
- [ ] Nếu dùng StructuredTaskScope trên Java 25, ghi nhận API đang preview và cờ build/run tương ứng.

### Khi đánh giá hiệu năng

- [ ] Benchmark explicit parameter, ScopedValue và ThreadLocal với cùng payload/call chain.
- [ ] Đo cả bind/unbind và get; không chỉ đo một lần get.
- [ ] Có warmup, nhiều measurement iterations và forks.
- [ ] Chạy JMH trong môi trường kiểm soát, không dựa vào thời gian JUnit hoặc IDE.
- [ ] Tách benchmark đồng bộ khỏi benchmark fork/join.
- [ ] Ghi JDK build, JVM flags, OS, CPU, JMH config và raw result.
- [ ] Đo workload thật trước khi thay đổi cache/system properties.

## 13. Bài thực hành tổng hợp

**Tình huống:** một ứng dụng order service có các tầng Controller → OrderService → PricingService → AuditService. Mỗi tầng cần biết requestId và tenantId để ghi log, nhưng chỉ OrderService cần orderId để thực hiện nghiệp vụ.

### Phần A — Thiết kế context

1. Tạo RequestContext dạng record với requestId, tenantId và Locale.
2. Validate giá trị bắt buộc; chỉ dùng kiểu immutable.
3. Tạo RequestContextScope với key private static final.
4. Viết method run và call để bind context tại boundary.
5. Tạo một method current() để code trong module đọc context.

**Đạt** khi key không bị public, context không chứa object request/session mutable và không có static field giữ request hiện tại.

### Phần B — So sánh ba cách truyền

1. Viết cùng call chain với tham số RequestContext.
2. Viết lại dùng ThreadLocal với set/get/remove.
3. Viết lại dùng ScopedValue.
4. Giữ logic ở tầng cuối giống nhau và cùng context input.
5. Viết bảng trade-off về chữ ký, cleanup, binding và visibility.

**Đạt** khi giải thích được vì sao explicit parameter vẫn là lựa chọn tốt cho dữ liệu nghiệp vụ, còn ScopedValue hữu ích cho context cross-cutting.

### Phần C — Nested scope và lỗi

1. Bind tenant-A, sau đó rebind tenant-B trong scope lồng nhau.
2. Xác nhận sau khi scope trong kết thúc, giá trị ngoài được khôi phục.
3. Ném exception trong lambda và xác nhận binding được gỡ.
4. Gọi get() ngoài scope và quan sát NoSuchElementException.
5. Chạy hai thread độc lập với hai binding khác nhau.

**Đạt** khi không có test phụ thuộc vào thứ tự scheduler và mọi assertion đều kiểm tra đúng scope.

### Phần D — Đánh giá hiệu năng

1. Tạo JMH benchmark với ba phương án như mục 8.
2. Đo bind/get/unbind và truyền tham số qua cùng số tầng.
3. Chạy warmup/measurement/forks trên JDK 25.
4. Lưu raw result và thông tin máy.
5. Thử tăng số key ScopedValue được dùng luân phiên; quan sát xu hướng cache.
6. Viết kết luận giới hạn: benchmark đo được điều gì và không đại diện cho điều gì.

**Đạt** khi không tuyên bố ScopedValue nhanh hơn nếu số liệu chưa chứng minh, và không so một lần đọc get với toàn bộ chi phí của một request ở phương án khác.

### Phần E — Concurrency và boundary

1. Viết ví dụ StructuredTaskScope trên JDK 25 để hai tác vụ con đọc chung context immutable.
2. Bật preview chỉ cho source/task dùng StructuredTaskScope.
3. Viết ví dụ executor/CompletableFuture riêng và chứng minh binding không tự kế thừa.
4. Thiết kế cách truyền context qua async boundary bằng snapshot hoặc framework propagation.
5. Đóng scope trước khi request boundary kết thúc.

**Đạt** khi phân biệt được ScopedValue final và StructuredTaskScope preview trong Java 25.

## 14. Câu hỏi tự đánh giá

1. ScopedValue là final hay preview trong JDK 25? JEP nào xác nhận trạng thái đó?
2. Vì sao key private static final không đồng nghĩa với việc request value là trạng thái global?
3. Binding ScopedValue có phạm vi theo JVM, theo thread hay theo method call?
4. Điều gì xảy ra khi run hoặc call kết thúc bình thường hoặc bằng exception?
5. get() ngoài binding làm gì? Khi nào dùng isBound hoặc orElse?
6. Vì sao nên xem key như capability và giới hạn visibility?
7. Những dữ liệu nào nên truyền bằng tham số tường minh thay vì ScopedValue?
8. ThreadLocal có thể giữ dữ liệu sau khi method hoàn tất như thế nào? Vì sao thread pool làm lỗi cleanup khó phát hiện?
9. ScopedValue có tự truyền sang mọi thread, executor, CompletableFuture hoặc reactive scheduler không?
10. Trong Java 25, API nào kế thừa ScopedValue binding cho child tasks và trạng thái preview của nó là gì?
11. Vì sao value được chia sẻ sang task con nên immutable hoặc được đồng bộ?
12. Javadoc Java 25 mô tả cache của ScopedValue như thế nào? Vì sao không nên dựa vào số entry mặc định như hợp đồng API?
13. Vì sao gộp nhiều metadata vào một immutable record có thể tốt hơn tạo rất nhiều key?
14. Ba phương án explicit parameter, ThreadLocal và ScopedValue cần được benchmark theo cùng workload ra sao?
15. Vì sao không nên đo hiệu năng bằng một lần gọi System.nanoTime hoặc bằng JUnit?
16. JMH cần warmup, measurement và fork để giảm những sai lệch nào?
17. Một benchmark chỉ đo ScopedValue.get() có đủ để đánh giá chi phí truyền context toàn request không?
18. Vì sao một request context được capture vào singleton vẫn có thể tồn tại sau khi binding kết thúc?
19. Làm thế nào để truyền metadata an toàn cho background job chạy sau request?
20. Những dấu hiệu nào cho thấy ScopedValue đang bị dùng như một global service locator?

## 15. Tài liệu tham khảo

- [Java SE 25 API — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding theo thread, dynamic scope, capability, rebinding, cache và so sánh với ThreadLocal.
- [OpenJDK JEP 506 — Scoped Values](https://openjdk.org/jeps/506): lý do thiết kế và trạng thái final trong Java 25.
- [Java SE 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): kế thừa binding trong task scope; API preview của JDK 25.
- [OpenJDK JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview và mục tiêu structured concurrency trong Java 25.
- [Java SE 25 API — ScopedValue.Carrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): run, call, mapping và khôi phục binding.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): cách tạo project benchmark, warmup, forks, measurement và lưu kết quả.
- [OpenJDK JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): ví dụ và các lưu ý khi viết benchmark JVM.


