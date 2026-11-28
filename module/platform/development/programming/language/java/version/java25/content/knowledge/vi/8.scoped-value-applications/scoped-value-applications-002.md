# Truyền ngữ cảnh qua nhiều lớp dịch vụ với phạm vi ràng buộc rõ ràng

> **Chương:** Ứng dụng ScopedValue
>
> **Phiên bản:** Java 25 — **JEP 506: Scoped Values** đã trở thành API chính thức. Bài thực hành dùng API final của Java 25, tập trung vào request context chỉ đọc trong một luồng gọi dịch vụ. Phần bất đồng bộ phân biệt rõ cơ chế kế thừa được hỗ trợ với những executor/thread boundary cần truyền context tường minh.

## 1. Bài toán: nhiều lớp cần cùng một request context

Một yêu cầu đặt hàng đi qua nhiều tầng:

1. Adapter HTTP nhận request và xác định thông tin tenant từ danh tính đã xác thực.
2. `OrderService` kiểm tra đơn hàng và gọi `InventoryService`.
3. `InventoryService` ghi nhận hoạt động và gọi tiếp `WarehouseService`.
4. Các tầng sâu cần correlation ID, tenant và locale để ghi log, chọn quy tắc nghiệp vụ hoặc tạo thông báo.

Nếu truyền ba tham số context qua từng method, nhiều chữ ký sẽ dài dù method không thực sự xử lý context. Nếu đặt chúng vào biến toàn cục có thể thay đổi, request đồng thời có nguy cơ đọc nhầm dữ liệu. `ScopedValue` giải quyết một trường hợp cụ thể: **truyền một giá trị theo chiều đọc xuống các lời gọi lồng nhau, trong một phạm vi thực thi có điểm bắt đầu và kết thúc rõ ràng**.

### Mục tiêu thực hành

Sau bài học, bạn có thể:

- Tạo một `ScopedValue` làm key cho context dùng chung trong một module.
- Bind context ở ranh giới request bằng `ScopedValue.where(...).run(...)`.
- Đọc context ở nhiều lớp dịch vụ mà không thêm tham số vào mọi method.
- Xử lý trường hợp chưa có binding và bảo đảm binding được khôi phục sau exception.
- Dùng nested scope để thay context tạm thời rồi quay lại context bên ngoài.
- Chủ động bind lại context khi gửi tác vụ tới executor bất đồng bộ.
- Phân biệt `ScopedValue` với `ThreadLocal`, framework context và dữ liệu truyền qua mạng.

## 2. ScopedValue là gì và dùng khi nào?

`ScopedValue<T>` là một key cho phép chia sẻ một giá trị tới các method được gọi trực tiếp hoặc gián tiếp trong **dynamic scope**. Ta tạo key, bind key với value trong một operation, rồi các method chạy trong operation đó có thể gọi `get()` để đọc giá trị.

~~~java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

void handleRequest() {
    ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
        serviceA();
    });
}

void serviceA() {
    serviceB();
}

void serviceB() {
    System.out.println(REQUEST_ID.get()); // req-42
}
~~~

Trong ví dụ, `serviceA()` và `serviceB()` không nhận `requestId` qua tham số, nhưng vẫn đọc được binding do caller thiết lập. Khi operation kết thúc, binding trở về trạng thái trước đó. Nếu có exception thoát khỏi operation, việc khôi phục scope vẫn diễn ra.

### Những đặc tính cần nhớ

| Đặc tính | Ý nghĩa thực tế |
| --- | --- |
| **Dynamic scope** | Giá trị có hiệu lực trong lúc operation được bind đang chạy và các lời gọi lồng nhau của nó. |
| **One-way transmission** | Caller thiết lập; callee đọc. Callee không có API để ghi đè binding hiện tại trong cùng scope. |
| **Per-thread binding** | Mỗi thread có binding riêng. Không phải biến toàn cục tự động chia sẻ cho mọi thread. |
| **Nested rebinding** | Có thể bind lại cùng key trong một scope con; khi scope con kết thúc, binding cũ được khôi phục. |
| **Automatic cleanup** | Không cần gọi `remove()` sau mỗi request; `run()`/`call()` quản lý vòng đời binding. |
| **Final API từ Java 25** | Dùng được mà không cần bật preview. |

`ScopedValue` không phải nơi lưu trạng thái có thể thay đổi qua nhiều tầng. Giá trị nên là object bất biến; nếu cần thay đổi trạng thái nghiệp vụ, hãy dùng service, repository hoặc object quản lý state có hợp đồng rõ ràng.

## 3. Thiết kế context: gom các giá trị liên quan vào một record

Một request có thể cần correlation ID, tenant và locale. Thay vì tạo ba `ScopedValue` riêng, ta gom chúng vào một record:

~~~java
// File: RequestContext.java
package com.example.orders.context;

import java.util.Locale;
import java.util.Objects;

public record RequestContext(
        String correlationId,
        String tenantId,
        Locale locale) {

    public RequestContext {
        correlationId = requireText(correlationId, "correlationId");
        tenantId = requireText(tenantId, "tenantId");
        locale = Objects.requireNonNull(locale, "locale");
    }

    private static String requireText(String value, String name) {
        Objects.requireNonNull(value, name);
        if (value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }
}
~~~

`record` giúp cấu trúc dữ liệu ngắn gọn và các component là `final`. Tuy nhiên record chỉ bất biến nông: nếu thêm `List`, `Map` hoặc object mutable, hãy sao chép phòng vệ và dùng collection bất biến trước khi bind.

**Chọn dữ liệu tối thiểu:** correlation ID, tenant đã xác thực và locale là ví dụ dễ quan sát. Không đưa password, bearer token, session secret hoặc toàn bộ HTTP request vào context. Tenant ID phải đến từ kết quả xác thực/ủy quyền ở server; không tin một header tùy ý do client gửi.

## 4. Đóng gói key và API truy cập context

Ta tạo một lớp duy nhất quản lý key. `ScopedValue` được giữ `private static final` để code bên ngoài không thể tự bind hoặc truy cập key trực tiếp:

~~~java
// File: RequestContexts.java
package com.example.orders.context;

import java.lang.ScopedValue;
import java.util.Objects;
import java.util.Optional;

public final class RequestContexts {

    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    private RequestContexts() {
    }

    public static void runWith(RequestContext context, Runnable operation) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(operation, "operation");

        ScopedValue.where(CURRENT, context).run(operation);
    }

    public static RequestContext current() {
        return CURRENT.orElseThrow(
                () -> new IllegalStateException("No request context is bound"));
    }

    public static Optional<RequestContext> find() {
        return CURRENT.isBound()
                ? Optional.of(CURRENT.get())
                : Optional.empty();
    }
}
~~~

### Vì sao không public key?

Một `ScopedValue` cũng là một **capability**: code có reference tới key có thể đọc value khi key được bind. Vì vậy:

- Giữ key `private` trong class sở hữu context.
- Chỉ cung cấp các accessor cần thiết như `current()` hoặc `find()`.
- Xem `runWith` là API dành cho adapter ở ranh giới request/job; giới hạn nơi gọi bằng package/module boundary của ứng dụng. Không expose raw key hoặc mở binder cho mọi consumer.
- Nếu một module chỉ cần correlation ID, cân nhắc expose accessor hẹp thay vì toàn bộ object chứa thông tin nhạy cảm.

`runWith` kiểm tra context và operation trước khi bind. Trong ví dụ, method này là `public` để adapter ở package khác gọi được; codebase thực tế nên giới hạn quyền gọi nó cho lớp boundary tin cậy. `current()` thể hiện rõ hợp đồng bắt buộc phải có context; `find()` dùng khi cùng một service có thể được gọi ngoài request, ví dụ từ batch hoặc tác vụ quản trị.

## 5. Truyền context qua nhiều lớp dịch vụ

Ta dùng ba lớp: adapter tạo context, `OrderService` xử lý đơn và `InventoryService` đọc cùng context. Ví dụ dùng Java thuần để tập trung vào ngữ nghĩa của JDK; các annotation Spring hoặc Jakarta có thể được thêm ở lớp adapter trong ứng dụng thật.

### 5.1. Các service

~~~java
// File: WarehouseService.java
package com.example.orders.service;

import com.example.orders.context.RequestContexts;

public class WarehouseService {

    public void checkAvailability(String sku, int quantity) {
        var context = RequestContexts.current();

        System.out.printf(
                "warehouse check: request=%s tenant=%s sku=%s quantity=%d%n",
                context.correlationId(),
                context.tenantId(),
                sku,
                quantity);
    }
}
~~~

~~~java
// File: InventoryService.java
package com.example.orders.service;

import com.example.orders.context.RequestContexts;

public class InventoryService {

    private final WarehouseService warehouse;

    public InventoryService(WarehouseService warehouse) {
        this.warehouse = warehouse;
    }

    public void reserve(String sku, int quantity) {
        var context = RequestContexts.current();

        System.out.printf(
                "inventory reserve: request=%s locale=%s%n",
                context.correlationId(),
                context.locale());

        warehouse.checkAvailability(sku, quantity);
    }
}
~~~

~~~java
// File: OrderService.java
package com.example.orders.service;

import com.example.orders.context.RequestContexts;

public class OrderService {

    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    public void placeOrder(String sku, int quantity) {
        var context = RequestContexts.current();

        System.out.printf(
                "order accepted: request=%s tenant=%s%n",
                context.correlationId(),
                context.tenantId());

        inventory.reserve(sku, quantity);
    }
}
~~~

Các service không nhận `RequestContext` qua constructor hay tham số của từng method. Chúng đọc context đang có hiệu lực. Trong hệ thống thật, chỉ dùng cách này cho **context xuyên tầng có vòng đời rõ ràng**; các dữ liệu ảnh hưởng trực tiếp đến kết quả nghiệp vụ vẫn nên là tham số tường minh.

### 5.2. Bind tại ranh giới request

~~~java
// File: CheckoutEndpoint.java
package com.example.orders.web;

import com.example.orders.context.RequestContext;
import com.example.orders.context.RequestContexts;
import com.example.orders.service.OrderService;

import java.util.Locale;

public class CheckoutEndpoint {

    private final OrderService orders;

    public CheckoutEndpoint(OrderService orders) {
        this.orders = orders;
    }

    public void handle(
            String correlationId,
            String authenticatedTenantId,
            String sku,
            int quantity) {

        var context = new RequestContext(
                correlationId,
                authenticatedTenantId,
                Locale.forLanguageTag("vi-VN"));

        RequestContexts.runWith(
                context,
                () -> orders.placeOrder(sku, quantity));
    }
}
~~~

`authenticatedTenantId` trong ví dụ tượng trưng cho tenant đã được xác minh bởi lớp authentication/authorization. Nếu lấy từ HTTP header, phải đối chiếu với danh tính đã xác thực trước khi tạo context. Correlation ID cũng cần được giới hạn độ dài và kiểm tra ký tự để tránh log injection.

Luồng thực thi:

~~~mermaid
sequenceDiagram
    participant H as HTTP Adapter
    participant C as RequestContexts
    participant O as OrderService
    participant I as InventoryService
    participant W as WarehouseService
    H->>C: runWith(context, operation)
    C->>O: placeOrder(...)
    O->>C: current()
    C-->>O: RequestContext
    O->>I: reserve(...)
    I->>C: current()
    C-->>I: RequestContext
    I->>W: checkAvailability(...)
    W->>C: current()
    C-->>W: RequestContext
    W-->>H: Hoàn tất lời gọi
    Note over C,H: Khi operation kết thúc, binding được khôi phục
~~~

Vì các method chạy đồng bộ trên cùng thread, binding có hiệu lực xuyên suốt chuỗi gọi. Không cần truyền context bằng tham số qua từng tầng.

## 6. Đọc an toàn khi có thể không tồn tại context

`ScopedValue.get()` ném `NoSuchElementException` nếu key chưa được bind trên thread hiện tại. Đó là hành vi phù hợp khi context là điều kiện bắt buộc, nhưng một service có thể còn được gọi từ batch, test hoặc command line.

Ba cách đọc phổ biến:

~~~java
// Bắt buộc phải có context:
RequestContext required = RequestContexts.current();

// Kiểm tra trước khi dùng:
var optional = RequestContexts.find();
if (optional.isPresent()) {
    audit(optional.get().correlationId());
}

// Hoặc dùng giá trị thay thế:
String requestId = RequestContexts.find()
        .map(RequestContext::correlationId)
        .orElse("system-task");
~~~

Ở cấp API trực tiếp, `ScopedValue` cung cấp:

| Method | Kết quả |
| --- | --- |
| `get()` | Trả value hiện tại; ném `NoSuchElementException` nếu chưa bind. |
| `isBound()` | Cho biết key có đang được bind trên thread hiện tại không. |
| `orElse(other)` | Trả value hoặc giá trị dự phòng. |
| `orElseThrow(supplier)` | Trả value hoặc ném exception do supplier tạo ra. |

Không nên dùng fallback im lặng cho context bảo mật. Nếu tenant hoặc principal là bắt buộc, thiếu binding phải làm request thất bại rõ ràng thay vì gán tenant mặc định.

## 7. Nested scope: thay context tạm thời rồi khôi phục

Một lời gọi lồng nhau có thể cần một context khác, ví dụ một tác vụ nội bộ cần correlation ID con để tách log. `ScopedValue` hỗ trợ **rebinding**:

~~~java
var outer = new RequestContext("req-100", "tenant-a", Locale.forLanguageTag("vi-VN"));
var inner = new RequestContext("req-100-audit", "tenant-a", Locale.forLanguageTag("vi-VN"));

RequestContexts.runWith(outer, () -> {
    System.out.println(RequestContexts.current().correlationId());
    // req-100

    RequestContexts.runWith(inner, () -> {
        System.out.println(RequestContexts.current().correlationId());
        // req-100-audit
    });

    System.out.println(RequestContexts.current().correlationId());
    // req-100: binding ngoài được khôi phục
});
~~~

Scope trong cùng thread được xếp lồng nhau. Khi operation trong cùng scope kết thúc, binding trước đó trở lại. Cơ chế này tránh phải lưu value cũ, gán value mới rồi nhớ khôi phục thủ công.

**Không dùng nested scope để thay đổi danh tính hoặc tenant một cách tùy tiện.** Nếu chuyển tenant, phải có bước xác thực/ủy quyền độc lập; rebinding chỉ là cơ chế phạm vi của Java, không phải cơ chế cấp quyền.

## 8. Cleanup khi return hoặc exception

`ScopedValue.where(key, value).run(operation)` quản lý vòng đời binding. Khi operation kết thúc bình thường hoặc ném exception, binding sẽ trở về trạng thái trước khi gọi.

~~~java
var context = new RequestContext(
        "req-exception",
        "tenant-a",
        Locale.forLanguageTag("vi-VN"));

try {
    RequestContexts.runWith(context, () -> {
        if (RequestContexts.find().isEmpty()) {
            throw new IllegalStateException("Context should be bound");
        }
        throw new IllegalArgumentException("Simulated failure");
    });
} catch (IllegalArgumentException expected) {
    System.out.println("Request failed as expected");
}

System.out.println(RequestContexts.find().isEmpty()); // true
~~~

Nếu `runWith` được gọi bên trong một scope khác, sau exception binding bên ngoài vẫn được khôi phục. Vì vậy không cần `finally { CURRENT.remove(); }` như một số cách quản lý `ThreadLocal`.

Tuy nhiên, cleanup của binding **không hoàn tác side effect nghiệp vụ**. Database transaction, message publication, file write và HTTP call vẫn cần transaction/compensation/retry riêng.

## 9. ScopedValue và bất đồng bộ: không tự lan sang mọi executor

Đây là giới hạn phải hiểu trước khi áp dụng vào dịch vụ thực:

- Binding của `ScopedValue` là **per-thread**.
- Các lời gọi đồng bộ trên cùng thread nhìn thấy binding hiện tại.
- Không mặc định rằng `ExecutorService`, `CompletableFuture`, callback của thư viện hoặc thread pool bất kỳ tự động kế thừa binding.
- `StructuredTaskScope` có cơ chế kế thừa scoped-value bindings cho các subtask, nhưng trong **JDK 25, Structured Concurrency vẫn là preview API**. Không dùng nó như API final của Java 25 nếu yêu cầu sản phẩm chỉ chấp nhận tính năng ổn định.

### 9.1. Truyền context tường minh khi submit task

Nếu gửi công việc tới executor thông thường, lấy context khi đang ở trong scope và bind lại bên trong task:

~~~java
RequestContext captured = RequestContexts.current();

executor.execute(() ->
        RequestContexts.runWith(
                captured,
                () -> invoiceService.generate(invoiceId)));
~~~

`captured` là record bất biến nên có thể chia sẻ an toàn. Task chạy trên worker thread sẽ có scope riêng; khi task kết thúc, binding trên worker thread được khôi phục. Không giữ `ScopedValue` binding sống ngoài vòng đời task.

Với `CompletableFuture`, có thể bọc tương tự:

~~~java
RequestContext captured = RequestContexts.current();

CompletableFuture<Void> future = CompletableFuture.runAsync(
        () -> RequestContexts.runWith(
                captured,
                () -> reportService.refresh(reportId)),
        executor);
~~~

Đây là **propagation tường minh**: tại ranh giới submit task, ta chụp immutable context rồi tạo binding trong worker. Nó dễ đọc và có thể kiểm thử hơn việc giả định mọi async framework đều hiểu `ScopedValue`.

### 9.2. Virtual threads không có nghĩa mọi task tự nhận context

Virtual threads là tính năng final từ Java 21 và vẫn hữu ích trong Java 25. `ScopedValue` được thiết kế để hoạt động tốt với mô hình thread nhẹ, nhưng điều đó **không có nghĩa mọi thread/virtual thread được tạo tùy ý đều tự kế thừa mọi binding**.

Khi tạo thread độc lập hoặc gửi tác vụ qua executor, hãy xác minh contract của cơ chế concurrency đang dùng. Nếu không có cơ chế inheritance được hỗ trợ, bind lại context tường minh trong task như ví dụ trên.

### 9.3. StructuredTaskScope trong Java 25 là preview

Java SE 25 API mô tả việc tạo `StructuredTaskScope` sẽ chụp scoped-value bindings hiện tại; các subtask được fork trong scope kế thừa binding đó. Tuy nhiên, `StructuredTaskScope` vẫn là **preview trong Java 25**. Nếu thử nghiệm, phải bật preview đúng release ở cả compile và runtime, đồng thời chấp nhận API có thể thay đổi.

~~~java
// Minh họa ý tưởng, KHÔNG phải code production dùng API final Java 25.
// StructuredTaskScope là preview trong JDK 25.
//
// ScopedValue.where(CURRENT, context).run(() -> {
//     try (var scope = StructuredTaskScope.open()) {
//         var first = scope.fork(() -> serviceA());
//         var second = scope.fork(() -> serviceB());
//         scope.join();
//         // Đọc kết quả theo API preview của đúng JDK.
//     }
// });
~~~

Nếu dự án không chấp nhận preview, dùng executor đã có và propagation tường minh, hoặc chờ phiên bản JDK mà Structured Concurrency trở thành final rồi đánh giá lại.

## 10. So sánh ScopedValue với ThreadLocal

`ThreadLocal` vẫn là API Java hợp lệ; nó không bị deprecated chỉ vì `ScopedValue` ra đời. Hai cơ chế giải quyết những nhu cầu khác nhau:

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Mục đích chính | Truyền dữ liệu theo chiều đọc trong dynamic scope | Lưu trạng thái gắn với từng thread |
| Cập nhật từ callee | Không có thao tác set binding hiện tại; muốn thay đổi phải tạo scope lồng nhau qua carrier | Có thể `set()` từ bất kỳ code nào có key |
| Vòng đời | Gắn với `run()`/`call()`, tự khôi phục khi thoát scope | Có thể kéo dài theo thread cho tới khi thay đổi/remove |
| Nested context | Có rebinding và tự khôi phục binding trước | Phải tự lưu/khôi phục nếu muốn nesting an toàn |
| Chia sẻ với structured child tasks | Có hỗ trợ theo cơ chế `StructuredTaskScope` | `InheritableThreadLocal` có quy tắc riêng và chi phí copy; executor reuse dễ gây bất ngờ |
| Dữ liệu phù hợp | Context bất biến: correlation, locale, tenant đã xác thực | Trạng thái mutable thực sự cần gắn với thread hoặc thư viện có contract ThreadLocal |

**Không thay toàn bộ `ThreadLocal` bằng `ScopedValue` một cách cơ học.** Nếu thư viện yêu cầu trạng thái mutable theo thread, hoặc framework quản lý ThreadLocal nội bộ với lifecycle riêng, hãy theo contract của thư viện. Chọn `ScopedValue` khi bài toán là “caller bind một context, callee đọc, scope kết thúc thì tự khôi phục”.

## 11. Tích hợp framework và ranh giới hệ thống

### 11.1. Không thay thế security context hoặc tracing context tự động

Một ứng dụng Spring/Jakarta có thể đã dùng cơ chế quản lý request, security principal, transaction, logging MDC hoặc tracing context. `ScopedValue` của JDK không tự động đồng bộ với những abstraction này.

- **Authentication/authorization:** tiếp tục dùng cơ chế bảo mật của framework; chỉ đưa thông tin bất biến tối thiểu vào context khi có lý do rõ ràng.
- **Tracing:** dùng instrumentation/propagation của tracing framework để truyền trace context qua HTTP/RPC; `ScopedValue` không tự tạo `traceparent`.
- **Transaction:** không đưa `EntityManager`, JDBC connection hoặc transaction object mutable vào context như cách thay thế transaction manager.
- **Logging MDC:** nếu muốn correlation ID xuất hiện trong log, tích hợp với logging framework và bảo đảm cleanup; binding `ScopedValue` không tự ghi MDC.

Nếu một framework phiên bản mới cung cấp integration chính thức với `ScopedValue`, dùng theo tài liệu của đúng phiên bản. Nếu không, adapter tại ranh giới request/task có thể đọc context và bind lại có chủ đích.

### 11.2. ScopedValue không truyền qua mạng

Scope chỉ tồn tại trong tiến trình Java và các thread/task có cơ chế kế thừa phù hợp. Khi gọi một service khác qua HTTP, gRPC hoặc message broker, phải serialize các metadata được phép truyền vào protocol/header và xác thực lại tại service nhận.

Không serialize nguyên object `RequestContext` theo mặc định. Chỉ truyền trường cần thiết, dùng chuẩn tương ứng (ví dụ W3C Trace Context cho tracing) và không tin dữ liệu tenant/principal chỉ vì nó đến trong header.

## 12. Kiểm thử behavior của scope

Các test quan trọng không chỉ kiểm tra `get()` trả đúng value, mà còn xác nhận binding không rò sang operation tiếp theo.

Ví dụ JUnit 5:

~~~java
// File: RequestContextsTest.java
package com.example.orders.context;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;
import org.junit.jupiter.api.Test;

class RequestContextsTest {

    private RequestContext context(String id) {
        return new RequestContext(id, "tenant-a", Locale.forLanguageTag("vi-VN"));
    }

    @Test
    void bindsValueForTheWholeOperation() {
        RequestContexts.runWith(context("req-1"), () ->
                assertEquals("req-1",
                        RequestContexts.current().correlationId()));

        assertTrue(RequestContexts.find().isEmpty());
    }

    @Test
    void restoresOuterBindingAfterNestedScope() {
        RequestContexts.runWith(context("outer"), () -> {
            assertEquals("outer",
                    RequestContexts.current().correlationId());

            RequestContexts.runWith(context("inner"), () ->
                    assertEquals("inner",
                            RequestContexts.current().correlationId()));

            assertEquals("outer",
                    RequestContexts.current().correlationId());
        });
    }

    @Test
    void clearsBindingWhenOperationThrows() {
        assertThrows(IllegalArgumentException.class, () ->
                RequestContexts.runWith(context("req-fail"), () -> {
                    assertTrue(RequestContexts.find().isPresent());
                    throw new IllegalArgumentException("expected");
                }));

        assertTrue(RequestContexts.find().isEmpty());
    }

    @Test
    void requiredContextFailsWhenNotBound() {
        assertThrows(IllegalStateException.class,
                RequestContexts::current);
    }
}
~~~

### Kiểm thử propagation qua executor

Một integration test có thể tạo executor một thread, submit task từ bên trong scope và xác nhận worker đọc được context sau khi bind lại:

~~~java
var executor = Executors.newSingleThreadExecutor();
try {
    RequestContexts.runWith(context("req-async"), () -> {
        var captured = RequestContexts.current();
        var result = CompletableFuture.supplyAsync(() -> {
            var value = new AtomicReference<String>();
            RequestContexts.runWith(captured,
                    () -> value.set(RequestContexts.current().correlationId()));
            return value.get();
        }, executor);

        assertEquals("req-async", result.join());
    });
} finally {
    executor.shutdown();
}
~~~

Test này chứng minh **wrapper propagation do ứng dụng viết**, không chứng minh executor tự kế thừa scope. Trong test thực tế, ưu tiên `try/finally` hoặc try-with-resources phù hợp để đóng executor và đặt timeout tránh treo CI.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchElementException` từ `get()` | Method được gọi ngoài scope hoặc trên thread chưa bind | Bind ở entry point; dùng `isBound`/`orElse` cho luồng không bắt buộc context. |
| Context đúng ở controller nhưng mất ở executor | Binding theo thread, task chạy trên worker khác | Chụp immutable context và bind lại bên trong task. |
| Request sau đọc nhầm context request trước | Thường là lỗi quản lý state khác, ví dụ `ThreadLocal` không cleanup; `ScopedValue` scope chuẩn tự khôi phục | Kiểm tra mọi code có `ThreadLocal`, static mutable state và adapter async. |
| Nested operation làm mất context ngoài | Tự quản lý stack hoặc bind ở sai phạm vi | Dùng nested `ScopedValue.where(...).run(...)`; không tự set/remove. |
| Context có thể bị thay đổi từ tầng sâu | Value được bind là object mutable | Dùng record/immutable value, defensive copy collection và tránh expose mutable object. |
| Quá nhiều `ScopedValue` key | Tách từng field context thành nhiều binding | Gom các giá trị liên quan vào một immutable record; chỉ tạo key cần thiết. |
| Framework security/MDC không có dữ liệu | Framework không tự tích hợp với key riêng của ứng dụng | Cấu hình adapter/integration theo tài liệu framework; không giả định tự động. |
| Remote service không nhận correlation | ScopedValue chỉ nằm trong JVM hiện tại | Propagate metadata qua protocol/header đã được chuẩn hóa và xác thực. |
| Code dùng `StructuredTaskScope` không biên dịch mặc định | API này còn preview trong JDK 25 | Chỉ dùng trong PoC có preview flags; sản phẩm ổn định dùng cơ chế đã final. |

## 14. Tiêu chí chọn và vận hành trong codebase

`ScopedValue` phù hợp khi tất cả điều kiện sau phần lớn đúng:

1. Dữ liệu là context **đọc nhiều, thay đổi rất ít hoặc không thay đổi** trong một operation.
2. Có ranh giới rõ để bind (request, job, transaction orchestration) và scope không vượt quá vòng đời operation.
3. Nhiều tầng cần đọc cùng dữ liệu, còn truyền tham số sẽ làm phình chữ ký mà không tăng độ rõ nghĩa.
4. Có quy tắc rõ cho tác vụ async: cơ chế inheritance được hỗ trợ hoặc explicit rebinding.
5. Key được đóng gói, dữ liệu tối thiểu và không chứa secret ngoài nhu cầu.

Không nên dùng nó cho:

- Trạng thái cần ghi/sửa từ nhiều tầng.
- Cache dùng chung, application configuration hoặc dữ liệu tồn tại qua nhiều request.
- Entity/transaction/session object có vòng đời riêng.
- Dữ liệu phải truyền qua mạng mà không có protocol serialization.
- Thay thế framework context khi chưa có integration chính thức.

### Checklist trước khi đưa vào production

- [ ] Dùng JDK 25+; `ScopedValue` là API final, không bật `--enable-preview`.
- [ ] Khai báo key `private static final` trong lớp sở hữu context.
- [ ] Bind tại ranh giới rõ ràng bằng `where(...).run(...)` hoặc `call(...)`.
- [ ] Value là immutable (hoặc mọi truy cập được đồng bộ đúng cách).
- [ ] Có hành vi rõ khi context không tồn tại.
- [ ] Test normal return, exception, nested scope và trường hợp không bind.
- [ ] Với executor/async, đã bind lại context trong worker hoặc dùng cơ chế inheritance được hỗ trợ.
- [ ] Không giả định virtual thread hoặc executor tùy ý tự động nhận binding.
- [ ] Không nhầm `StructuredTaskScope` preview trong Java 25 với API final.
- [ ] Không đưa secret, token hoặc PII không cần thiết vào context/log.
- [ ] Không thay thế transaction, security, tracing, MDC hoặc context của framework một cách cơ học.
- [ ] Đã đo workload nếu mục tiêu là cải thiện hiệu năng; không mặc định `ScopedValue` luôn nhanh hơn trong mọi tình huống.

## 15. Bài tập thực hành

### Bài A — Truyền context qua ba tầng

Tạo `RequestContext` gồm `correlationId`, `tenantId`, `Locale`. Tạo ba lớp `OrderService`, `InventoryService`, `WarehouseService`. Bind context ở một adapter và đọc nó ở cả ba lớp.

**Điều kiện đạt:** không truyền ba trường context qua tham số từng method; `tenantId` phải là giá trị đã xác thực; sau operation, `RequestContexts.find()` không còn binding.

### Bài B — Nested rebinding

Bind context `req-parent`, tạo scope con `req-child`, rồi đọc context sau khi scope con hoàn tất.

**Điều kiện đạt:** trong scope con đọc `req-child`; sau khi trở về đọc `req-parent`.

### Bài C — Exception cleanup

Ném một exception bên trong `runWith`. Bắt exception ở caller và xác minh không còn binding của operation vừa kết thúc.

**Điều kiện đạt:** exception vẫn được truyền về caller và scope được khôi phục tự động.

### Bài D — Async executor

Gửi một tác vụ tới `ExecutorService` từ trong request scope. Thử hai phiên bản: không bind lại context và bind lại bằng immutable context đã capture.

**Điều kiện đạt:** giải thích vì sao không nên dựa vào tự động inheritance của executor; phiên bản explicit propagation đọc đúng correlation ID và không để binding rò sang task tiếp theo.

### Bài E — Ranh giới framework

Trong ứng dụng Spring, xác định nơi framework tạo request context, nơi security principal được xác thực và nơi tracing context được propagate. Thiết kế adapter chỉ đưa các giá trị tối thiểu vào `ScopedValue`.

**Điều kiện đạt:** không thay `SecurityContext`, transaction manager hoặc W3C trace propagation bằng một key `ScopedValue` tự tạo.

## 16. Tài liệu chính thức

1. [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): mục tiêu, phạm vi và việc đưa Scoped Values thành tính năng chính thức trong JDK 25.
2. [Java SE 25 — ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): `newInstance`, `where`, `get`, `isBound`, `orElse`, `orElseThrow`, nested rebinding và thread semantics.
3. [Java SE 25 — ScopedValue.Carrier API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): `run`, `call`, ghép nhiều binding và việc khôi phục binding sau operation.
4. [Java SE 25 — StructuredTaskScope API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): cơ chế kế thừa scoped-value bindings trong structured subtasks; API vẫn preview trong Java 25.
5. [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads đã final từ Java 21; phân biệt vòng đời thread với cơ chế truyền context.
6. [Java SE 25 — ThreadLocal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html): đối chiếu khi cần trạng thái mutable gắn với thread.

**Ghi nhớ:** `ScopedValue` không phải biến global mới. Nó là một **binding chỉ đọc, có phạm vi động và vòng đời tự khôi phục**. Hãy bind một context immutable tại entry point, đọc ở các tầng dịch vụ, tạo nested scope khi cần và chủ động xử lý ranh giới async. Đây là cách giữ request context rõ ràng mà không biến mọi method thành nơi truyền hoặc quản lý state thủ công.
