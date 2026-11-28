# Chuyển ngữ cảnh chỉ đọc phù hợp từ ThreadLocal sang ScopedValue

## 1. Mục tiêu: chuyển đúng loại context, không thay ThreadLocal một cách máy móc

Trong ứng dụng Java, nhiều tầng xử lý cần đọc chung một số thông tin của lần thực thi hiện tại: request ID, tenant đã được xác thực, locale, correlation metadata hoặc principal đã được kiểm tra. Nếu truyền các giá trị này qua mọi tham số của mọi phương thức, chữ ký API có thể trở nên dài và lặp lại.

Một cách làm lâu đời là dùng **`ThreadLocal`**: đặt giá trị ở đầu request, để các method phía dưới đọc qua cùng một key, rồi gọi `remove()` khi hoàn tất. Cách này vẫn được Java hỗ trợ và vẫn có use case phù hợp. Nhưng với dữ liệu chỉ cần **truyền một chiều, đọc trong một phạm vi có giới hạn**, Java 25 cung cấp **`ScopedValue`** như một mô hình rõ ràng hơn về vòng đời.

Bài **Chuyển ngữ cảnh chỉ đọc phù hợp từ ThreadLocal sang ScopedValue** thuộc chương **Ứng dụng ScopedValue** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào việc phân loại use case, chuyển đổi boundary, thay đổi cách đọc, xử lý nested scope và kiểm tra các điểm bất đồng bộ.

### Sau bài này, người học có thể

1. Nhận biết ThreadLocal nào đang truyền context chỉ đọc và ThreadLocal nào thật sự giữ trạng thái mutable theo thread.
2. Thay cặp `set()/try/finally/remove()` bằng `ScopedValue.where(...).run(...)` hoặc `call(...)`.
3. Thiết kế một key có phạm vi truy cập phù hợp và một context object bất biến.
4. Xử lý nested context mà không làm mất giá trị của scope bên ngoài.
5. Phân biệt hành vi mặc định của `ThreadLocal.get()` với `ScopedValue.get()` khi chưa có giá trị.
6. Truyền context qua executor một cách tường minh và hiểu giới hạn inheritance của StructuredTaskScope trong Java 25.
7. Tránh thay nhầm ThreadLocal do framework quản lý như MDC, security context hoặc transaction context.
8. Viết test để chứng minh binding được phục hồi, không rò context và không chia sẻ mutable state thiếu đồng bộ.

> **Phạm vi phiên bản:** `ScopedValue` đã là API chính thức trong Java 25 theo **JEP 506**. Ví dụ chính trong bài dùng JDK 25 mà không cần `--enable-preview`. **Structured Concurrency** vẫn ở trạng thái preview trong JDK 25; phần này chỉ giải thích mối liên hệ và không yêu cầu dùng API preview để hoàn thành bài.

## 2. Phân loại ThreadLocal trước khi migration

Không phải mọi `ThreadLocal` đều nên được thay bằng `ScopedValue`. Hãy bắt đầu bằng cách tìm các khai báo:

~~~java
private static final ThreadLocal<?> CURRENT = new ThreadLocal<>();
~~~

Sau đó truy vết ba việc: nơi ghi, nơi đọc và nơi xóa. Đừng chỉ đổi tên API rồi giữ nguyên thiết kế cũ.

| Kiểu sử dụng hiện tại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Context đặt một lần ở boundary, nhiều tầng chỉ đọc | request ID, locale, immutable request metadata | **Ứng viên tốt cho ScopedValue** |
| Context có thể được thay trong một phạm vi lồng nhau có chủ đích | locale override cho một tác vụ con | ScopedValue với nested binding |
| Mutable state riêng của từng thread | formatter/cache/accumulator có lifecycle theo thread | Giữ ThreadLocal hoặc thiết kế lại ownership |
| Giá trị thay đổi nhiều lần bởi các callee | mutable workflow state | Truyền tham số/result hoặc dùng state owner rõ ràng |
| Framework tự quản lý | logging MDC, security context, transaction context | Dùng cơ chế tích hợp của framework; không thay nội bộ tùy tiện |
| Context cần đi qua HTTP/message broker | trace context, correlation metadata liên service | Dùng chuẩn propagation của framework/giao thức |
| Giá trị chỉ có ở một thread lâu dài | cache theo thread hoặc thư viện cũ yêu cầu ThreadLocal | Đánh giá giữ nguyên, giới hạn lifecycle và cleanup |

### 2.1. Dấu hiệu một ThreadLocal phù hợp để chuyển

Một use case thường phù hợp nếu tất cả điều sau đúng:

- Có **một điểm thiết lập** dễ xác định, chẳng hạn request filter hoặc command handler.
- Các phương thức downstream chủ yếu gọi `get()` để đọc.
- Giá trị không cần được thay tùy ý bởi một helper bất kỳ.
- Có thể giới hạn thời gian truy cập bằng một khối xử lý cụ thể.
- Object được bind là immutable hoặc được chia sẻ theo quy tắc đồng bộ hóa rõ ràng.
- Khi công việc kết thúc, context phải hết hiệu lực tự nhiên.

Nếu code hiện tại gọi `set()` ở nhiều tầng, thay đổi giá trị liên tục hoặc dựa vào một cache mutable theo thread, cần thiết kế lại trước khi migration.

## 3. ThreadLocal và ScopedValue khác nhau ở đâu?

### 3.1. Mẫu ThreadLocal quen thuộc

~~~java
public final class LegacyRequestContext {

    private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

    private LegacyRequestContext() {
    }

    public static void runWith(String requestId, Runnable action) {
        REQUEST_ID.set(requestId);
        try {
            action.run();
        } finally {
            REQUEST_ID.remove();
        }
    }

    public static String current() {
        String value = REQUEST_ID.get();
        if (value == null) {
            throw new IllegalStateException("No request context");
        }
        return value;
    }
}
~~~

Cách này hợp lệ, nhưng lifecycle phụ thuộc vào việc mọi đường thoát đều chạy cleanup. Nếu quên `remove()` trong một thread pool, worker có thể giữ lại dữ liệu của request trước đó.

Một điểm nữa: nếu `runWith()` được gọi lồng nhau, việc inner call gọi `remove()` sẽ xóa luôn giá trị outer. Muốn hỗ trợ nested scope đúng, wrapper ThreadLocal phải lưu và phục hồi giá trị cũ.

### 3.2. Mẫu ScopedValue tương ứng

~~~java
public final class RequestContextScope {

    private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

    private RequestContextScope() {
    }

    public static void runWith(String requestId, Runnable action) {
        ScopedValue.where(REQUEST_ID, requestId).run(action);
    }

    public static String current() {
        return REQUEST_ID.orElseThrow(
            () -> new IllegalStateException("No request context"));
    }
}
~~~

Cách sử dụng ở boundary:

~~~java
RequestContextScope.runWith("req-2025-001", () -> {
    orderService.submit();
});
~~~

Ở downstream service:

~~~java
public void submit() {
    String requestId = RequestContextScope.current();
    auditService.record("submit-order", requestId);
}
~~~

Khác biệt chính:

- `ThreadLocal.set()` thay giá trị hiện tại của thread và có thể được gọi ở bất cứ nơi nào giữ reference tới key.
- `ScopedValue.where(key, value).run(action)` tạo một **binding có phạm vi**, chỉ hoạt động trong khi action đang chạy.
- Khi action kết thúc bình thường hoặc ném exception, binding được phục hồi về trạng thái trước đó.
- Không có `ScopedValue.set()` hoặc `remove()` tương ứng; cấu trúc lời gọi xác định thời gian sống của binding.
- `ScopedValue` phù hợp cho **one-way transmission**: caller bind, callee đọc.

### 3.3. Bảng so sánh

| Tiêu chí | ThreadLocal | ScopedValue |
| --- | --- | --- |
| Cách thiết lập | `set(value)` | `where(key, value).run/call(action)` |
| Cách đọc | `get()` | `get()` |
| Thay binding trong cùng phạm vi | Có thể `set()` lại | Không; dùng nested `where` để rebind |
| Kết thúc context | `remove()`/quản lý thủ công | Tự phục hồi khi action kết thúc |
| Mặc định khi chưa có giá trị | `null` hoặc `initialValue()` | `get()` ném `NoSuchElementException` |
| Nested scope | Phải tự lưu/khôi phục giá trị trước | Có sẵn nested rebinding |
| Dữ liệu mutable | Có thể, nhưng phải quản lý ownership | Không bị cấm, nhưng không tự an toàn; ưu tiên immutable |
| Chia sẻ sang StructuredTaskScope | Không phải cơ chế context mặc định của ThreadLocal | Binding được capture và inherit theo structured scope |
| Chia sẻ sang executor bất kỳ | Không tự động trừ khi có cơ chế riêng | Không tự động |
| Mục tiêu điển hình | Per-thread state | Context truyền một chiều trong dynamic scope |

**ThreadLocal không phải API lỗi thời.** Nó vẫn cần thiết trong một số thư viện và use case per-thread mutable. Quyết định migration dựa trên semantics của dữ liệu và lifecycle, không dựa trên việc API nào mới hơn.

## 4. Chuyển từ set/remove sang where/run

Ví dụ có một tác vụ không trả kết quả.

**Trước migration:**

~~~java
private static final ThreadLocal<RequestInfo> CURRENT =
    new ThreadLocal<>();

void handle(RequestInfo requestInfo) {
    CURRENT.set(requestInfo);
    try {
        controller.handle();
    } finally {
        CURRENT.remove();
    }
}
~~~

**Sau migration:**

~~~java
private static final ScopedValue<RequestInfo> CURRENT =
    ScopedValue.newInstance();

void handle(RequestInfo requestInfo) {
    ScopedValue.where(CURRENT, requestInfo).run(
        () -> controller.handle());
}
~~~

Các phương thức phía dưới tiếp tục đọc qua `CURRENT.get()`:

~~~java
void audit() {
    RequestInfo info = CURRENT.get();
    System.out.println(info.requestId());
}
~~~

Điểm quan trọng: binding chỉ có hiệu lực **trong quá trình thực thi lambda và các lời gọi đồng bộ từ nó**. Không lấy giá trị trong lambda rồi lưu reference vào một static field hoặc dùng sau khi scope đã đóng mà vẫn kỳ vọng binding còn hiệu lực.

### 4.1. Khi cần kết quả, dùng call()

`run()` phù hợp với `Runnable`. Nếu muốn nhận kết quả, dùng `call()`:

~~~java
private static final ScopedValue<String> TENANT =
    ScopedValue.newInstance();

String result = ScopedValue.where(TENANT, "tenant-a")
    .call(() -> reportService.generate());
~~~

Trong method có checked exception, xử lý theo chữ ký exception của method gọi hoặc bắt exception tại boundary. Không bọc mọi exception thành một giá trị mặc định chỉ để tránh khai báo throws.

## 5. Xây dựng context object thay vì nhiều ThreadLocal rời rạc

Một codebase cũ có thể chứa:

~~~java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
static final ThreadLocal<String> TENANT_ID = new ThreadLocal<>();
static final ThreadLocal<Locale> LOCALE = new ThreadLocal<>();
static final ThreadLocal<String> ACTOR_ID = new ThreadLocal<>();
~~~

Chuyển máy móc thành bốn `ScopedValue` riêng biệt sẽ tạo nhiều binding và khiến việc xác định context đầy đủ khó hơn. Tài liệu Java 25 cũng khuyến nghị dùng một record để gom nhiều giá trị khi cần truyền chúng cùng nhau.

### 5.1. Tạo immutable record

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public record RequestContext(
        String requestId,
        String tenantId,
        String actorId,
        Locale locale,
        Set<String> authorities,
        Map<String, String> attributes) {

    public RequestContext {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(actorId, "actorId");
        Objects.requireNonNull(locale, "locale");
        authorities = Set.copyOf(
            Objects.requireNonNull(authorities, "authorities"));
        attributes = Map.copyOf(
            Objects.requireNonNull(attributes, "attributes"));
    }
}
~~~

Record có component fields final, còn `Set.copyOf` và `Map.copyOf` tạo collection không sửa được qua API collection. Ở ví dụ này, các phần tử là `String` immutable nên context có cấu trúc an toàn hơn để chia sẻ chỉ đọc.

**Lưu ý:** record không tự đảm bảo immutable sâu nếu component chứa object mutable. Nếu `Map<String, UserProfile>` giữ các `UserProfile` mutable, map không sửa được nhưng object profile vẫn có thể bị thay đổi.

### 5.2. Một key cho toàn bộ request context

~~~java
import java.util.Objects;

public final class RequestContexts {

    private static final ScopedValue<RequestContext> CURRENT =
        ScopedValue.newInstance();

    private RequestContexts() {
    }

    public static void runWith(
            RequestContext context,
            Runnable action) {

        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");

        ScopedValue.where(CURRENT, context).run(action);
    }

    public static RequestContext current() {
        return CURRENT.orElseThrow(
            () -> new IllegalStateException(
                "RequestContext is not bound"));
    }

    public static boolean isBound() {
        return CURRENT.isBound();
    }
}
~~~

Việc giữ key ở dạng `private static final` giúp giới hạn code có quyền bind/rebind trực tiếp. Những nơi khác chỉ được đọc qua API `current()`. Đây là một cách dùng `ScopedValue` như **capability key**: code muốn truy cập giá trị phải có quyền truy cập tới chính key hoặc facade được cung cấp.

### 5.3. Dùng ở request boundary

Ví dụ controller/application entrypoint đã xác thực thông tin request:

~~~java
RequestContext context = new RequestContext(
    requestId,
    authenticatedTenant.id(),
    authenticatedPrincipal.id(),
    locale,
    authenticatedPrincipal.authorities(),
    Map.of("channel", "web"));

RequestContexts.runWith(context, () -> {
    orderApplicationService.submit(command);
});
~~~

`requestId` có thể lấy từ correlation middleware; `tenantId` và `actorId` phải lấy từ **principal đã xác thực/ủy quyền**. Không dùng trực tiếp header tùy ý của client để tạo danh tính hoặc quyền truy cập.

### 5.4. Đọc ở nhiều tầng

~~~java
public final class OrderAuditService {

    public void record(String operation) {
        RequestContext context = RequestContexts.current();

        System.out.printf(
            "request=%s tenant=%s actor=%s operation=%s%n",
            context.requestId(),
            context.tenantId(),
            context.actorId(),
            operation);
    }
}
~~~

Các method không cần thêm ba tham số context nếu đây thực sự là metadata xuyên tầng. Nhưng dữ liệu nghiệp vụ ảnh hưởng kết quả xử lý — như account ID, order ID hoặc số lượng — vẫn nên truyền qua API một cách tường minh.

## 6. Xử lý nested request context

Một số use case hợp lệ cần một context con: chạy tác vụ với locale khác, gắn correlation ID cho một operation con hoặc chuyển sang tenant scope đã được kiểm tra theo một quy tắc rõ ràng.

`ScopedValue` hỗ trợ **nested rebinding**:

~~~java
private static final ScopedValue<String> OPERATION =
    ScopedValue.newInstance();

ScopedValue.where(OPERATION, "request").run(() -> {
    System.out.println(OPERATION.get()); // request

    ScopedValue.where(OPERATION, "audit").run(() -> {
        System.out.println(OPERATION.get()); // audit
    });

    System.out.println(OPERATION.get()); // request
});
~~~

Khi scope con kết thúc, binding bên ngoài được phục hồi tự động.

### 6.1. So sánh với ThreadLocal lồng nhau

Nếu dùng `ThreadLocal` và chỉ `remove()` sau mỗi lần gọi, inner scope sẽ xóa giá trị outer. Muốn xử lý nested scope đúng, phải lưu previous value:

~~~java
static void runWithThreadLocal(
        ThreadLocal<String> key,
        String value,
        Runnable action) {

    String previous = key.get();
    key.set(value);

    try {
        action.run();
    } finally {
        if (previous == null) {
            key.remove();
        } else {
            key.set(previous);
        }
    }
}
~~~

Ví dụ giả định `null` nghĩa là “không có binding”. Nếu hệ thống cho phép giá trị null hoặc dùng `ThreadLocal.withInitial`, cần một cách phân biệt trạng thái ban đầu và giá trị cũ chính xác hơn.

Với `ScopedValue`, không phải viết logic lưu/khôi phục này; cấu trúc nested `where` thể hiện rõ vùng override.

### 6.2. Không dùng nested binding để lách security

Nested context có thể bind một actor/tenant khác về mặt kỹ thuật, nhưng **không chứng minh caller được phép hành động dưới danh tính đó**. Chỉ bind principal đã được kiểm tra bởi security layer, và mọi thay đổi danh tính/ủy quyền phải qua quy trình impersonation/delegation có audit riêng.

## 7. Xử lý context không tồn tại

Một khác biệt dễ gây lỗi khi migration là giá trị trả về lúc chưa bind.

### ThreadLocal

~~~java
private static final ThreadLocal<String> USER =
    new ThreadLocal<>();

String user = USER.get(); // null nếu chưa set
~~~

Nếu dùng `ThreadLocal.withInitial(...)`, `get()` có thể gọi initializer và trả về giá trị mặc định.

### ScopedValue

~~~java
private static final ScopedValue<String> USER =
    ScopedValue.newInstance();

String user = USER.get(); // NoSuchElementException nếu chưa bind
~~~

API Java 25 có các cách đọc rõ nghĩa:

~~~java
String optionalUser = USER.orElse("anonymous");

String requiredUser = USER.orElseThrow(
    () -> new IllegalStateException("User context is required"));
~~~

Hoặc kiểm tra:

~~~java
if (USER.isBound()) {
    process(USER.get());
}
~~~

### Chọn chính sách

| Trường hợp | Cách dùng |
| --- | --- |
| Request context bắt buộc | `orElseThrow(...)` hoặc `get()` và để lỗi thiếu context lộ rõ |
| Metadata tùy chọn | `orElse(defaultValue)` |
| Chỉ chạy logic khi có binding | `isBound()` |
| Trước đây dùng `withInitial` | Khởi tạo context ở boundary hoặc dùng `orElse(...)` nếu default thật sự an toàn |

Không chuyển `ThreadLocal.withInitial(() -> ADMIN)` thành `ScopedValue.orElse(ADMIN)` một cách máy móc. Default quyền cao là lỗi bảo mật. Với principal/tenant, thiếu context thường phải **fail closed**.

### Giá trị null

API `ScopedValue.where(key, value)` cho phép bind `null`; khi đó `isBound()` vẫn có thể là true trong khi `get()` trả về null. Tuy nhiên, context nghiệp vụ nên tránh null vì nó làm mơ hồ giữa “đã bind nhưng không có dữ liệu” và “chưa thiết lập boundary”. Ưu tiên object không null, `Optional` hoặc trạng thái domain tường minh.

## 8. Đưa dữ liệu vào scope mà không làm rò reference mutable

`ScopedValue` cố định binding, không đóng băng object. Khi chuyển context từ ThreadLocal sang ScopedValue, cần kiểm tra **referent** được bind có thực sự phù hợp với mô hình read-only hay không.

### 8.1. Rủi ro với collection mutable

~~~java
var roles = new java.util.ArrayList<String>();
roles.add("reader");

var context = new LegacyContext("req-1", roles);

ScopedValue.where(CONTEXT, context).run(() -> {
    CONTEXT.get().roles().add("admin");
});
~~~

Nếu `LegacyContext.roles()` trả về chính `ArrayList`, callee đã thay đổi context mặc dù không có API để thay binding. Mọi nơi đang giữ cùng reference đều nhìn thấy thay đổi.

### 8.2. Defensive copy tại boundary

~~~java
import java.util.List;
import java.util.Objects;

public record AccessContext(
        String requestId,
        List<String> roles) {

    public AccessContext {
        Objects.requireNonNull(requestId);
        roles = List.copyOf(Objects.requireNonNull(roles));
    }
}
~~~

Bản sao này ngăn caller thêm/xóa phần tử thông qua list gốc sau khi tạo context và ngăn code downstream sửa cấu trúc list trả ra. Nếu các phần tử là object mutable, phải bảo đảm chúng immutable hoặc copy theo chính sách phù hợp.

### 8.3. Quy tắc cho context dùng chung

- Ưu tiên String, primitive wrappers, enum, UUID, Locale và immutable records.
- Với List/Set/Map, tạo snapshot bằng `copyOf` khi boundary cần cô lập cấu trúc.
- Không bind một mutable request bag rồi để nhiều tầng tùy ý `put()`.
- Không chia sẻ một mutable referent giữa nhiều worker nếu chưa có synchronization/ownership rõ.
- Không xem `ScopedValue` là cơ chế transaction hay rollback.

## 9. Context propagation qua async boundary

Một migration dễ bị sai khi ứng dụng chuyển từ xử lý đồng bộ sang executor, callback hoặc virtual thread.

### 9.1. Binding là per-thread

Theo API Java 25, binding `ScopedValue` gắn với thread hiện tại. Một thread khác không tự động có binding chỉ vì nó được tạo trong lúc parent đang ở scope.

Ví dụ minh họa với executor:

~~~java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    ScopedValue.where(REQUEST_ID, "req-async-1").run(() -> {
        Future<Boolean> result = executor.submit(
            REQUEST_ID::isBound);

        try {
            System.out.println(result.get()); // false
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    });
} finally {
    executor.shutdown();
}
~~~

Worker của executor là thread thực thi task độc lập; nó không tự nhận binding từ caller. Không giả định `Thread.ofVirtual().start(...)`, callback của framework hay `CompletableFuture.supplyAsync(...)` đều tự truyền scoped binding.

### 9.2. Cách đơn giản: truyền snapshot và bind lại ở worker

~~~java
RequestContext snapshot = RequestContexts.current();

Future<Receipt> future = executor.submit(() ->
    ScopedValue.where(CURRENT, snapshot).call(
        () -> shippingService.createReceipt()));
~~~

Trong code production, nếu key là `private` bên trong `RequestContexts`, hãy cung cấp method facade như `RequestContexts.callWith(snapshot, action)` để worker bind đúng key mà không phải mở quyền truy cập trực tiếp.

Ví dụ facade:

~~~java
public static <T> T callWith(
        RequestContext context,
        ScopedValue.CallableOp<? extends T, ? extends RuntimeException> action) {

    return ScopedValue.where(CURRENT, context).call(action);
}
~~~

Đoạn facade minh họa kiểu kết quả và exception unchecked; nếu action có checked exception, khai báo generic exception tương ứng theo chữ ký `ScopedValue.CallableOp`/`Carrier.call` của JDK 25 hoặc bắt exception tại boundary. Không nuốt lỗi chỉ để giữ một chữ ký đơn giản.

### 9.3. StructuredTaskScope trong Java 25

`ScopedValue` hỗ trợ inheritance trong **các trường hợp có cấu trúc**. Khi dùng `StructuredTaskScope`, binding hiện hành được capture lúc tạo task scope và được inherit bởi các subtask được fork trong scope đó. Điều này giúp các task con đọc cùng context mà không phải truyền tham số qua từng tầng.

Tuy nhiên, trong **JDK 25, Structured Concurrency vẫn là preview** (JEP 505). Nếu dự án chọn sử dụng, phải quyết định rõ việc bật preview ở compiler/runtime và chấp nhận API preview cho đúng môi trường triển khai. Bài này không dùng nó làm cơ chế bắt buộc cho migration production; giải pháp snapshot + bind lại ở worker có thể áp dụng với API ổn định.

### 9.4. Không truyền nguyên context nhạy cảm vô điều kiện

Trước khi gửi snapshot tới worker, hãy hỏi:

- Task có cần toàn bộ context hay chỉ request ID?
- Principal có còn hợp lệ trong thời gian task chạy?
- Task có thể tồn tại lâu hơn request ban đầu không?
- Có cần truyền trace context qua API tracing thay vì tự mang trace ID?
- Dữ liệu nào cần loại bỏ hoặc redact?
- Retry có thể sử dụng context cũ sau khi quyền truy cập đã thay đổi không?

Context propagation là quyết định **về phạm vi dữ liệu và quyền truy cập**, không chỉ là một thao tác copy object.

## 10. Không thay thế ThreadLocal do framework quản lý một cách tùy tiện

Một ứng dụng Spring Boot hoặc framework khác có thể dùng ThreadLocal ở bên trong để quản lý:

- MDC/logging context;
- transaction synchronization;
- security context;
- tracing context và baggage;
- locale hoặc request attributes;
- framework callback/interceptor lifecycle.

Không nên đổi trực tiếp những ThreadLocal này thành ScopedValue chỉ vì muốn đồng bộ code ứng dụng. Framework có thể có API propagation và cleanup riêng, hoặc còn phụ thuộc ThreadLocal trong phiên bản hiện tại.

### 10.1. Logging MDC

MDC của nhiều logging backend hoạt động dựa trên dữ liệu gắn với thread. Bạn có thể lưu request ID trong immutable RequestContext và khi ghi log đưa field vào structured logging hoặc adapter MDC theo lifecycle của framework.

Không giả định:

~~~java
ScopedValue.where(REQUEST_ID, id).run(() -> {
    logger.info("processing");
});
~~~

sẽ tự động làm `%X{requestId}` xuất hiện trong mọi logger. ScopedValue không tự đồng bộ sang MDC.

### 10.2. Spring Security

Không tự thay `SecurityContextHolder` bằng ScopedValue trong ứng dụng Spring Security. Hãy sử dụng cơ chế security context propagation được framework hỗ trợ và đảm bảo authorization được thực hiện theo principal đã xác thực.

Nếu muốn cung cấp một read-only projection của principal cho code nghiệp vụ, có thể tạo immutable context sau khi security layer đã xác minh danh tính. Projection đó không phải nguồn thẩm quyền thay thế framework.

### 10.3. Transaction và tracing

Transaction context cần tuân theo transaction manager; trace context cần tuân theo Micrometer/OpenTelemetry propagation. `ScopedValue` có thể mang metadata bổ trợ trong một call tree, nhưng không tự tạo transaction, không tự export span và không tự truyền header qua HTTP.

## 11. Tổ chức một migration an toàn theo từng bước

Giả sử ứng dụng có một `ThreadLocal<RequestContext>` được set tại request filter và đọc bởi service/audit layer.

~~~mermaid
flowchart TD
    A[Kiểm kê ThreadLocal và call sites] --> B{Context chỉ đọc trong scope?}
    B -- Không --> C[Giữ ThreadLocal hoặc thiết kế lại state]
    B -- Có --> D[Thiết kế immutable RequestContext]
    D --> E[Tạo ScopedValue key và facade]
    E --> F[Đổi boundary set/remove thành where/run]
    F --> G[Đổi downstream reads và nested scope]
    G --> H[Kiểm tra async/framework integration]
    H --> I[Unit + integration + concurrency tests]
    I --> J[Build, deploy canary và quan sát]
    J --> K[Loại bỏ ThreadLocal cũ sau khi không còn consumer]
~~~

### Bước 1 — kiểm kê mọi nơi dùng key

Tìm:

- Khai báo `ThreadLocal` và `withInitial`.
- Tất cả lời gọi `set()`, `get()`, `remove()`.
- Method nào được gọi đồng bộ, method nào chạy callback/async.
- Nơi lưu lại reference ra ngoài request.
- Tests hoặc thư viện đang phụ thuộc trực tiếp vào key.

Nếu chỉ thấy một `set` và một `remove` không có nghĩa mọi use case đều an toàn; cần kiểm tra toàn bộ call graph và đường exception.

### Bước 2 — phân loại từng giá trị

Tách dữ liệu thành:

- **Context chỉ đọc:** request ID, locale, immutable principal snapshot.
- **Mutable per-thread state:** cache hoặc accumulator.
- **Framework-managed state:** MDC, transaction, security, tracing.
- **Cross-process metadata:** cần serialize/propagate theo protocol.

Chỉ nhóm đầu là ứng viên chuyển trực tiếp.

### Bước 3 — tạo immutable snapshot

Dùng record có constructor kiểm tra null và defensive-copy collection. Không lưu object request mutable, entity đang được Hibernate quản lý hoặc connection vào context chỉ để tiện truy cập.

### Bước 4 — đặt binding ở boundary

Một request boundary chỉ bind một lần, bao quanh đoạn xử lý cần context. Với Servlet Filter/Web framework, hãy đặt boundary ở lifecycle callback tương ứng và bảo đảm phần xử lý đồng bộ thực sự chạy bên trong lambda.

Không bọc một đoạn code quá ngắn nếu các callback thực tế chạy sau khi lambda đã kết thúc.

### Bước 5 — đổi downstream access

Thay `THREAD_LOCAL.get()` bằng facade `RequestContexts.current()`. Tránh để mọi package truy cập key trực tiếp; encapsulation giúp kiểm soát ai có quyền đọc/bind.

### Bước 6 — xác định nested behavior

Nếu code cũ ghi đè context cho operation con, chuyển thành nested binding có mục tiêu. Test rằng khi scope con kết thúc, outer context được phục hồi.

### Bước 7 — xác định async behavior

Với executor/queue không có structured inheritance, chụp snapshot ở nơi được phép và bind lại ở worker. Không chuyển một mutable context object rồi chia sẻ cho nhiều workers.

### Bước 8 — kiểm thử và rollout

Chạy test thiếu context, nested scope, exception, request song song, async worker, retry và framework integration. Triển khai canary, quan sát lỗi “context not bound”, rồi mới xóa ThreadLocal cũ khi không còn consumer.

## 12. Một ví dụ hoàn chỉnh cho command handler

Dưới đây là một ví dụ độc lập dùng Java 25, không cần preview API.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class ScopedCommandDemo {

    record CommandContext(
            String requestId,
            String tenantId,
            Locale locale,
            Map<String, String> metadata) {

        CommandContext {
            Objects.requireNonNull(requestId);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(locale);
            metadata = Map.copyOf(metadata);
        }
    }

    private static final ScopedValue<CommandContext> CURRENT =
        ScopedValue.newInstance();

    static void audit(String action) {
        CommandContext context = CURRENT.orElseThrow(
            () -> new IllegalStateException("Command context missing"));

        System.out.printf(
            "request=%s tenant=%s locale=%s action=%s%n",
            context.requestId(),
            context.tenantId(),
            context.locale(),
            action);
    }

    static void execute(CommandContext context, Runnable command) {
        Objects.requireNonNull(context);
        Objects.requireNonNull(command);

        ScopedValue.where(CURRENT, context).run(command);
    }

    public static void main(String[] args) {
        var context = new CommandContext(
            "req-25-001",
            "tenant-vn",
            Locale.forLanguageTag("vi-VN"),
            Map.of("source", "cli"));

        execute(context, () -> {
            audit("validate");
            audit("persist");
        });

        System.out.println("Bound after execute: " + CURRENT.isBound());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 25 -encoding UTF-8 ScopedCommandDemo.java
java ScopedCommandDemo
~~~

Kết quả:

~~~text
request=req-25-001 tenant=tenant-vn locale=vi_VN action=validate
request=req-25-001 tenant=tenant-vn locale=vi_VN action=persist
Bound after execute: false
~~~

Điểm thiết kế:

- Context được tạo tại boundary, không phải trong từng service.
- Metadata dùng Map snapshot, không cho downstream sửa cấu trúc.
- `audit()` đọc context nhưng không có API để thay binding.
- Sau `execute()`, binding không còn hoạt động.
- Business command vẫn được truyền rõ ràng; ScopedValue chỉ mang metadata xuyên tầng.

## 13. Viết test cho hành vi migration

Các test sau dùng JUnit Jupiter. Mỗi test xác minh một contract cụ thể, không dựa vào thứ tự chạy test hoặc giá trị thread ID.

### 13.1. Không có binding ngoài boundary

~~~java
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class RequestScopeTests {

    private static final ScopedValue<String> REQUEST =
        ScopedValue.newInstance();

    @Test
    void getFailsWhenNoContextIsBound() {
        assertFalse(REQUEST.isBound());
        assertThrows(
            NoSuchElementException.class,
            REQUEST::get);
    }
}
~~~

### 13.2. Binding kết thúc sau thành công và exception

~~~java
@Test
void bindingIsRestoredAfterNormalCompletion() {
    assertFalse(REQUEST.isBound());

    ScopedValue.where(REQUEST, "req-1").run(() ->
        assertEquals("req-1", REQUEST.get()));

    assertFalse(REQUEST.isBound());
}

@Test
void bindingIsRestoredAfterException() {
    assertThrows(IllegalStateException.class, () ->
        ScopedValue.where(REQUEST, "req-error").run(() -> {
            assertEquals("req-error", REQUEST.get());
            throw new IllegalStateException("expected");
        }));

    assertFalse(REQUEST.isBound());
}
~~~

Hai method test này nằm trong cùng class với khai báo `REQUEST` ở phần 13.1. Exception không làm binding tồn tại ngoài scope.

### 13.3. Nested scope phục hồi outer context

~~~java
@Test
void nestedBindingRestoresOuterValue() {
    ScopedValue.where(REQUEST, "outer").run(() -> {
        assertEquals("outer", REQUEST.get());

        ScopedValue.where(REQUEST, "inner").run(() ->
            assertEquals("inner", REQUEST.get()));

        assertEquals("outer", REQUEST.get());
    });

    assertFalse(REQUEST.isBound());
}
~~~

Test này quan trọng khi ThreadLocal cũ có helper tự lưu previous value. Hãy bảo đảm hành vi nested của code mới khớp ý định nghiệp vụ.

### 13.4. Hai thread có binding độc lập

~~~java
@Test
void bindingsArePerThread() throws Exception {
    var executor = java.util.concurrent.Executors
        .newFixedThreadPool(2);

    try {
        var first = executor.submit(() ->
            ScopedValue.where(REQUEST, "A").call(REQUEST::get));

        var second = executor.submit(() ->
            ScopedValue.where(REQUEST, "B").call(REQUEST::get));

        assertEquals("A", first.get());
        assertEquals("B", second.get());
    } finally {
        executor.shutdown();
    }
}
~~~

Mỗi worker tự bind giá trị cho thread của chính nó. Test này **không** kiểm tra inheritance từ thread cha; nó kiểm tra binding độc lập khi task chủ động thiết lập scope.

### 13.5. Executor không tự nhận binding từ caller

~~~java
@Test
void executorTaskDoesNotImplicitlyInheritBinding() throws Exception {
    var executor = java.util.concurrent.Executors
        .newSingleThreadExecutor();

    try {
        ScopedValue.where(REQUEST, "caller").run(() -> {
            var result = executor.submit(REQUEST::isBound);

            try {
                assertFalse(result.get());
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
    } finally {
        executor.shutdown();
    }
}
~~~

Đây là test bảo vệ migration khỏi giả định rằng mọi async task đều nhìn thấy context của caller. Nếu thiết kế yêu cầu context ở worker, hãy truyền snapshot và bind lại rõ ràng rồi viết test tương ứng.

### 13.6. Kiểm tra snapshot không bị caller sửa sau khi bind

~~~java
record TestContext(String requestId, java.util.List<String> roles) {
    TestContext {
        roles = java.util.List.copyOf(roles);
    }
}

private static final ScopedValue<TestContext> CONTEXT =
    ScopedValue.newInstance();

@Test
void snapshotDoesNotTrackMutationsToInputList() {
    var input = new java.util.ArrayList<String>();
    input.add("reader");

    var context = new TestContext("req-1", input);
    input.add("admin");

    ScopedValue.where(CONTEXT, context).run(() ->
        assertEquals(
            java.util.List.of("reader"),
            CONTEXT.get().roles()));
}
~~~

Test này xác minh **defensive copy của context**, không phải tính năng copy tự động của ScopedValue.

## 14. Các vấn đề cần kiểm tra trước khi xóa ThreadLocal

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Có nơi nào vẫn gọi `ThreadLocal.set()` không? | Search toàn bộ source và test, review call sites |
| Có đường thoát nào trước đây bỏ quên `remove()`? | Exception/cancellation tests |
| Nested context có đúng không? | Test outer → inner → outer |
| Context có mutable collection/entity không? | Review type graph và defensive copy |
| Worker async có cần context không? | Explicit snapshot + bind test |
| Framework còn phụ thuộc ThreadLocal cũ không? | Integration tests với framework/version thực tế |
| Context thiếu có xử lý an toàn không? | Test `get()`/`orElseThrow` và security fail-closed |
| Có dữ liệu nhạy cảm bị log/export không? | Structured log/trace review và redaction |
| Có code dùng key trực tiếp ngoài module sở hữu? | Encapsulation/access review |
| ThreadLocal có use case per-thread mutable còn hợp lệ? | Giữ lại có lý do, lifecycle và cleanup rõ |

Không xóa ThreadLocal trước khi tất cả consumer đã chuyển hoặc đã được xác nhận không còn sử dụng. Nếu một thư viện bên ngoài yêu cầu ThreadLocal, có thể giữ một adapter ở integration boundary thay vì duy trì hai nguồn context độc lập trong toàn bộ ứng dụng.

## 15. Những trường hợp nên giữ ThreadLocal

**Giữ ThreadLocal** nếu use case thật sự cần một giá trị mutable hoặc cache riêng theo thread, ví dụ:

- Một thư viện hiện tại yêu cầu ThreadLocal để duy trì trạng thái theo thread và không cung cấp API khác.
- Một cache per-thread được thiết kế có chủ đích, có giới hạn kích thước và lifecycle rõ ràng.
- Một formatter hoặc adapter mutable chỉ được một thread sở hữu và không được chia sẻ ra ngoài.
- Framework quản lý ThreadLocal nội bộ và có contract riêng cho propagation/cleanup.

Tuy nhiên, khi sử dụng thread pools hoặc virtual threads, phải xem lại chi phí/lifecycle của per-thread state. Đừng tạo ThreadLocal cache lớn trên mỗi virtual thread mà không đo memory/behavior thực tế.

**Chuyển sang ScopedValue** nếu use case chỉ là caller bind một context bất biến, các tầng dưới đọc, và phạm vi thực thi xác định được. Đây là sự phù hợp về semantics, không phải một quy tắc bắt buộc thay toàn bộ ThreadLocal trong codebase.

## 16. Các lỗi migration thường gặp

### 16.1. Đổi ThreadLocal thành ScopedValue nhưng vẫn tìm set/remove

ScopedValue không có setter/remove. Hãy chuyển điểm thiết lập sang `where(...).run(...)` hoặc `call(...)`, và để scope kết thúc theo control flow.

### 16.2. Gọi get() ngoài scope

ThreadLocal cũ có thể trả null hoặc initializer default; ScopedValue `get()` ném `NoSuchElementException` nếu unbound. Dùng `orElse`/`orElseThrow` theo chính sách domain.

### 16.3. Dùng nhiều ScopedValue rời rạc cho một context lớn

API được thiết kế cho số lượng scoped keys tương đối nhỏ. Nếu cần truyền nhiều trường cùng nhau, gom vào immutable record rồi bind một key.

### 16.4. Giả định executor tự truyền context

Executor thread không tự nhận binding của caller. Capture immutable snapshot và bind ở worker, hoặc sử dụng cơ chế structured inheritance được hỗ trợ.

### 16.5. Dùng mutable object trong context rồi gọi nó là read-only

Binding chỉ ngăn thay key → value reference trong scope. Nó không khóa object. Dùng immutable record/collection hoặc thiết kế synchronization/ownership rõ ràng.

### 16.6. Thay ThreadLocal của framework

MDC, transaction manager, Spring Security và tracing có lifecycle riêng. Không thay implementation nội bộ; hãy tích hợp ở boundary theo API chính thức của framework.

### 16.7. Cho phép fallback quyền cao khi context thiếu

Không dùng anonymous/default principal có quyền cao. Thiếu security context phải được xử lý theo nguyên tắc fail-closed.

### 16.8. Đưa context qua network bằng ScopedValue

ScopedValue không serialize hoặc tạo HTTP header. Dùng W3C Trace Context, framework propagation hoặc protocol của hệ thống tích hợp.

### 16.9. Đánh giá migration chỉ bằng benchmark

Hiệu năng phụ thuộc workload, số keys, cache, thread model và object graph. Trước tiên chứng minh semantics và correctness; benchmark trên workload thật sau đó.

## 17. Quy ước code review đề xuất

Một nhóm phát triển có thể áp dụng các quy tắc sau:

1. `ScopedValue` chỉ mang **metadata/context read-mostly**; dữ liệu nghiệp vụ thay đổi vẫn đi qua tham số, result, event hoặc persistence.
2. Key nằm trong `private static final` field hoặc một API context được đóng gói.
3. Context là record/value object immutable; collection phải được snapshot.
4. Bind ở boundary rõ ràng, không bind rải rác trong mọi service.
5. Downstream dùng `get()`/`orElseThrow()` để đọc; không có API cập nhật context tùy tiện.
6. Nested override phải có lý do và test phục hồi outer context.
7. Mọi async boundary phải có policy propagation rõ: structured scope được hỗ trợ hoặc explicit snapshot + rebind.
8. Không thay ThreadLocal do framework quản lý khi chưa có hướng dẫn tích hợp.
9. Không log/export secret, token hoặc thông tin cá nhân chỉ vì context dễ truy cập.
10. Không thêm `--enable-preview` cho `ScopedValue` trong JDK 25.

## 18. Bài tập thực hành

### Bài tập A — migration một request ID

Bắt đầu với ThreadLocal request ID có `set()/try/finally/remove()`. Tạo wrapper ScopedValue, bind quanh request handler và đổi các helper downstream sang đọc qua facade.

**Đạt khi:** request ID có mặt trong toàn bộ synchronous call tree và unbound sau khi handler kết thúc cả khi exception.

### Bài tập B — nested context

Tạo operation ngoài dùng tenant A và một sub-operation dùng locale khác. Dùng nested binding cho context con, sau đó xác minh outer context được phục hồi.

**Đạt khi:** không tự lưu/restore reference như cách làm ThreadLocal cũ và có test outer → inner → outer.

### Bài tập C — context record

Gom request ID, tenant, actor, locale và attributes vào một record. Thêm defensive copies cho collections; thử sửa collection đầu vào sau khi tạo record.

**Đạt khi:** context không thay đổi theo collection gốc và code downstream không thể sửa cấu trúc snapshot.

### Bài tập D — async boundary

Dùng một executor cố định. Chứng minh worker không có binding từ caller; sau đó capture snapshot và bind lại trong task.

**Đạt khi:** task có context đúng theo policy và không giữ reference mutable không an toàn.

### Bài tập E — kiểm kê framework

Tìm MDC, security context, transaction và tracing trong ứng dụng. Ghi rõ thành phần nào thuộc ứng dụng, thành phần nào thuộc framework; đề xuất cách tích hợp mà không thay nội bộ ThreadLocal của framework.

**Đạt khi:** có danh sách các ThreadLocal giữ lại và lý do, không đặt mục tiêu xóa sạch ThreadLocal.

### Bài tập F — rollout

Tạo migration PR nhỏ cho một context cụ thể. Chạy unit tests, integration tests, security tests và kiểm tra lỗi thiếu binding; quan sát canary trước khi xóa implementation cũ.

**Đạt khi:** có bằng chứng correctness, rollback plan và không còn consumer nào dùng key ThreadLocal cũ.

### Checklist nghiệm thu

- [ ] Đã kiểm kê nơi khai báo, set, get và remove của ThreadLocal.
- [ ] Chỉ chuyển các context read-only có dynamic scope rõ ràng.
- [ ] Có một ScopedValue key được đóng gói và một boundary bind rõ ràng.
- [ ] Context object immutable hoặc có ownership/synchronization phù hợp.
- [ ] Đã chuyển cách xử lý missing binding và default value.
- [ ] Nested binding phục hồi context ngoài.
- [ ] Async/executor propagation được kiểm thử, không dựa trên giả định.
- [ ] ThreadLocal của framework được xử lý qua integration API.
- [ ] Có test cho exception, request song song, context leakage và security fail-closed.
- [ ] Chỉ xóa ThreadLocal cũ sau khi không còn consumer.

## 19. Tài liệu tham khảo chính thức

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): lý do chọn ScopedValue cho truyền dữ liệu một chiều và trạng thái final trong JDK 25.
- [Java SE 25 API — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): `newInstance`, `where`, `run`, `call`, `get`, `isBound`, `orElse`, nested binding và structured inheritance.
- [Java SE 25 API — ThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html): contract của `get`, `set`, `remove` và `withInitial`.
- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview của Structured Concurrency trong Java 25 và quan hệ với scoped-value inheritance.
- [Java SE 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): cách binding được capture và inherit bởi subtasks trong task scope.

**Kết quả mong đợi:** người học có thể chọn đúng ThreadLocal để migration, thay lifecycle set/remove bằng scoped binding, truyền một immutable context qua call tree và xử lý async boundary có chủ đích. Ứng dụng Java 25 nhờ đó có context rõ phạm vi, giảm rủi ro rò dữ liệu giữa các request và giữ lại ThreadLocal ở những nơi thực sự cần trạng thái per-thread hoặc framework integration.
