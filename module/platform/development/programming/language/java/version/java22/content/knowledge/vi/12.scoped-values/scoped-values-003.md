# Tạo khóa `ScopedValue` và quy định quyền truy cập khóa trong ứng dụng

`ScopedValue` là cơ chế truyền dữ liệu theo phạm vi thực thi (*dynamic scope*) trong Java. Một thành phần gọi có thể gắn một giá trị với khóa `ScopedValue`, chạy một thao tác trong phạm vi đó, rồi các phương thức được gọi trực tiếp hoặc gián tiếp có thể đọc giá trị qua cùng khóa. Khi thao tác kết thúc, binding tự động được khôi phục hoặc trở về trạng thái chưa được bind.

Scoped Values xuất hiện dưới dạng incubator trong JDK 20, preview từ JDK 21 đến JDK 24 và trở thành API chính thức từ JDK 25 qua JEP 506. Tính đến ngày 25/11/2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất; `ScopedValue` đã ổn định trong cả hai. Bài này chỉ sử dụng cú pháp final: tạo khóa bằng `ScopedValue.newInstance()`, bind bằng `ScopedValue.where(...)` và thực thi qua `Carrier.run(...)` hoặc `Carrier.call(...)`.

## 1. ScopedValue dùng để làm gì?

Trong một request, nhiều lớp có thể cần cùng một số thông tin ngữ cảnh như request ID, tenant, người dùng hiện tại hoặc locale. Nếu truyền các giá trị này qua tham số, mỗi phương thức trung gian phải nhận và chuyển tiếp tham số dù bản thân nó không sử dụng dữ liệu.

`ScopedValue` cho phép truyền dữ liệu theo chuỗi lời gọi mà không phải thêm tham số vào mọi phương thức:

```text
Request handler
      |
      | bind REQUEST_CONTEXT = context
      v
OrderService
      |
      v
PricingService
      |
      v
AuditService  ---> đọc REQUEST_CONTEXT.get()
      |
      v
Kết thúc phạm vi ---> binding tự động được khôi phục
```

Chỉ code có tham chiếu đến đối tượng khóa mới đọc được giá trị. Các phương thức trung gian không cần biết về khóa vẫn có thể gọi tiếp các phương thức sử dụng ngữ cảnh đó.

ScopedValue phù hợp với dữ liệu được truyền một chiều từ caller xuống callee, thường là dữ liệu ngữ cảnh bất biến. Nó không phải một vùng lưu trữ để các phương thức tùy ý thay đổi giá trị cho nhau.

## 2. Tạo khóa ScopedValue

Tạo một khóa bằng phương thức tĩnh `ScopedValue.newInstance()`:

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();
```

Các thành phần quan trọng:

- `ScopedValue<String>` khai báo kiểu dữ liệu được bind với khóa. Trình biên dịch kiểm tra kiểu khi bind và khi đọc.
- `newInstance()` tạo một khóa mới, ban đầu chưa được bind trong mọi thread.
- `static final` giữ một đối tượng khóa ổn định để các phương thức trong class cùng sử dụng.
- Tên hằng viết hoa giúp nhận biết đây là khóa ngữ cảnh dùng chung, không phải giá trị request cụ thể.

Thông thường, tạo khóa một lần trong field `static final` của class quản lý ngữ cảnh. Không tạo khóa mới cho mỗi request: nếu caller và callee giữ hai đối tượng khóa khác nhau thì chúng không truy cập cùng một binding.

Một khóa có thể được bind nhiều lần ở các lần thực thi khác nhau. Đối tượng khóa vẫn giữ nguyên; giá trị và thời gian binding được xác định bởi từng phạm vi thực thi.

## 3. Bind khóa và thực thi trong một phạm vi

API final dùng `ScopedValue.where(key, value)` để tạo một `ScopedValue.Carrier`. Carrier đại diện cho một hoặc nhiều cặp khóa-giá trị. Sau khi cấu hình xong, gọi `run(...)` hoặc `call(...)` để thực thi thao tác với các binding đó.

### 3.1. Dùng `run()` khi không cần kết quả trả về

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

static void handleRequest() {
    ScopedValue.where(REQUEST_ID, "req-42")
            .run(() -> processOrder());
}

static void processOrder() {
    System.out.println("Request: " + REQUEST_ID.get());
}
```

Trong khi `processOrder()` và các phương thức được gọi từ nó đang chạy, `REQUEST_ID.get()` trả về `"req-42"`. Khi lambda truyền vào `run()` hoàn tất, binding được gỡ khỏi phạm vi hiện tại.

Nếu lambda ném exception, binding vẫn được khôi phục. Vì vậy, không cần viết `try/finally` để tự xóa giá trị như khi dùng `ThreadLocal`.

### 3.2. Dùng `call()` khi cần kết quả

`Carrier.call(...)` thực thi một thao tác trả về kết quả:

```java
private static final ScopedValue<String> TENANT_ID =
        ScopedValue.newInstance();

static Invoice createInvoice(String tenantId) throws IOException {
    return ScopedValue.where(TENANT_ID, tenantId)
            .call(() -> invoiceService.create());
}

static final class InvoiceService {
    Invoice create() throws IOException {
        String tenant = TENANT_ID.get();
        return invoiceRepository.insertForTenant(tenant);
    }
}
```

`call()` trả về `Invoice` của thao tác được thực thi. Nếu thao tác ném `IOException`, exception được truyền ngược về caller và binding vẫn kết thúc đúng phạm vi.

Trong ví dụ, `invoiceService` và `invoiceRepository` là dependency do ứng dụng khởi tạo; điểm chính là `InvoiceService.create()` đọc `TENANT_ID` ở sâu trong call chain.

### 3.3. Kết hợp nhiều khóa

Một Carrier có thể tích lũy nhiều mapping trước khi chạy:

```java
private static final ScopedValue<RequestContext> REQUEST =
        ScopedValue.newInstance();

private static final ScopedValue<Locale> LOCALE =
        ScopedValue.newInstance();

static void handle(RequestContext context, Locale locale) {
    ScopedValue.where(REQUEST, context)
            .where(LOCALE, locale)
            .run(() -> renderResponse());
}
```

Trong `renderResponse()` hoặc các phương thức mà nó gọi, có thể đọc cả hai giá trị bằng `REQUEST.get()` và `LOCALE.get()`.

`Carrier` là immutable và thread-safe. Mỗi lần gọi `.where(...)` trả về một Carrier mới với mapping được bổ sung hoặc thay thế; Carrier trước đó không bị sửa. Các binding chỉ có hiệu lực khi gọi `run()` hoặc `call()`, không bắt đầu ngay tại thời điểm tạo Carrier.

## 4. Đọc giá trị và xử lý trường hợp chưa được bind

Một khóa có thể đang ở trạng thái đã bind hoặc chưa bind trong thread hiện tại. Chọn phương thức đọc theo yêu cầu của ứng dụng:

| Phương thức | Hành vi |
| --- | --- |
| `get()` | Trả về giá trị nếu đã bind; ném `NoSuchElementException` nếu chưa bind. |
| `isBound()` | Trả về `true` nếu khóa đang được bind trong thread hiện tại. |
| `orElse(other)` | Trả về giá trị đã bind hoặc giá trị mặc định `other`. |
| `orElseThrow(supplier)` | Trả về giá trị đã bind hoặc ném exception do supplier tạo ra. |

Ví dụ:

```java
static String currentRequestId() {
    return REQUEST_ID.orElse("background-task");
}

static RequestContext requireRequestContext() {
    return REQUEST.orElseThrow(
            () -> new IllegalStateException("Request context is missing")
    );
}
```

Nếu ngữ cảnh bắt buộc phải có, dùng `get()` hoặc `orElseThrow()` để phát hiện việc gọi sai ngoài phạm vi. Nếu ngữ cảnh thực sự tùy chọn, dùng `isBound()` hoặc `orElse(...)` với giá trị mặc định có ý nghĩa.

Không dùng `get()` như thể khóa luôn có giá trị. Một phương thức có thể được gọi từ request handler hoặc từ background job; nếu background job không tạo binding thì `get()` sẽ ném `NoSuchElementException`.

## 5. Quy định quyền truy cập khóa trong ứng dụng

Đối tượng `ScopedValue` vừa là khóa định danh binding vừa là quyền truy cập (*capability*) đối với giá trị. Code có tham chiếu đến khóa có thể đọc giá trị đang bind và có thể tạo một phạm vi lồng để bind lại khóa đó. Vì vậy, phạm vi hiển thị của đối tượng khóa là một quyết định bảo mật và kiến trúc.

### 5.1. Giữ khóa trong field `private static final`

Ví dụ một class quản lý request context:

```java
import java.lang.ScopedValue;
import java.util.Objects;

public final class RequestScope {
    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    private RequestScope() { }

    public static RequestContext current() {
        return CURRENT.orElseThrow(
                () -> new IllegalStateException("No request context is bound")
        );
    }

    static <R, X extends Throwable> R callWith(
            RequestContext context,
            ScopedValue.CallableOp<? extends R, X> action
    ) throws X {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");

        return ScopedValue.where(CURRENT, context).call(action);
    }
}
```

`CURRENT` là `private`, nên class khác không thể lấy trực tiếp khóa. Các thành phần cần đọc chỉ gọi `RequestScope.current()`. Phương thức `callWith(...)` có package access, giới hạn nơi có thể thiết lập binding trong cùng package. Ứng dụng có thể đặt phương thức này ở một request boundary hoặc một module nội bộ được kiểm soát.

`RequestContext` nên là kiểu dữ liệu bất biến, chẳng hạn record:

```java
import java.util.Objects;

public record RequestContext(String requestId, String tenantId) {
    public RequestContext {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(tenantId, "tenantId");
    }
}
```

Một thành phần cùng package có thể dùng boundary `callWith(...)` để chạy một thao tác trong ngữ cảnh request:

```java
Receipt receipt = RequestScope.callWith(
        new RequestContext("req-42", "tenant-7"),
        () -> orderService.createReceipt()
);
```

`orderService` và các service mà nó gọi có thể đọc `RequestScope.current()` mà không phải nhận `RequestContext` qua mọi tầng tham số.

Nếu cần bind từ package khác, hãy cung cấp một phương thức public hẹp có xác thực đầu vào và kiểm tra quyền phù hợp. Không cần công khai đối tượng khóa chỉ để cho phép thành phần khác đọc giá trị.

### 5.2. Chỉ expose dữ liệu cần thiết

Một service chỉ cần tenant ID thì có thể gọi accessor trả về tenant ID thay vì nhận được cả khóa hoặc toàn bộ đối tượng quản lý scope:

```java
import java.util.Objects;

public final class TenantContext {
    private static final ScopedValue<String> TENANT_ID =
            ScopedValue.newInstance();

    private TenantContext() { }

    public static String currentTenantId() {
        return TENANT_ID.orElseThrow(
                () -> new IllegalStateException("Tenant is not bound")
        );
    }

    static void runForTenant(String tenantId, Runnable action) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(action, "action");
        ScopedValue.where(TENANT_ID, tenantId).run(action);
    }
}
```

Code sử dụng `TenantContext.currentTenantId()` có thể đọc tenant hiện tại trong phạm vi hợp lệ. Chỉ code được phép gọi `runForTenant(...)` mới thiết lập được binding qua API của class.

### 5.3. Không trả khóa qua getter công khai

Tránh thiết kế kiểu:

```java
public static ScopedValue<RequestContext> currentKey() {
    return CURRENT;
}
```

Khi trả khóa cho mọi caller, ứng dụng đã chia sẻ capability. Caller có thể đọc binding và tự tạo binding lồng bằng `ScopedValue.where(CURRENT, anotherContext)`. Nếu mục tiêu là chỉ cho phép đọc một phần dữ liệu, hãy trả dữ liệu qua accessor chuyên biệt.

### 5.4. Dùng visibility và module boundary có chủ đích

Một số lựa chọn thường dùng:

| Phạm vi của khóa | Khi phù hợp |
| --- | --- |
| `private static final` | Khóa chỉ thuộc nội bộ một class; lựa chọn an toàn mặc định. |
| Package-private thông qua class quản lý | Nhiều class tin cậy trong cùng package cần phối hợp. |
| Public accessor trả dữ liệu | Thành phần bên ngoài cần đọc giá trị nhưng không cần giữ khóa. |
| Public binding boundary có kiểm tra | Một module khác cần khởi tạo phạm vi; boundary phải xác thực dữ liệu và quyền bind. |

Nếu dùng Java modules, chỉ export package chứa API cần thiết. Giữ package nội bộ chứa key và logic bind không được export giúp giới hạn thành phần có thể truy cập capability. Visibility không thay thế xác thực người dùng hoặc kiểm tra quyền nghiệp vụ; nó chỉ giới hạn code nào có thể truy cập đối tượng khóa và API binding.

## 6. Rebinding trong phạm vi lồng nhau

Một khóa đã được bind có thể được bind lại trong một dynamic scope lồng. Khi phạm vi trong kết thúc, giá trị cũ tự động được khôi phục.

```java
private static final ScopedValue<String> USER =
        ScopedValue.newInstance();

static void demonstrateRebinding() {
    ScopedValue.where(USER, "alice").run(() -> {
        System.out.println(USER.get()); // alice

        ScopedValue.where(USER, "admin-service").run(() -> {
            System.out.println(USER.get()); // admin-service
        });

        System.out.println(USER.get()); // alice
    });

    System.out.println(USER.isBound()); // false
}
```

Binding `"admin-service"` chỉ có hiệu lực trong lambda lồng. Sau khi lambda này kết thúc, binding `"alice"` bên ngoài lại được nhìn thấy. Sau khi lambda ngoài kết thúc, khóa trở về trạng thái chưa bind trong thread đó.

Rebinding hữu ích khi một thao tác cần tạm thời thay đổi ngữ cảnh, chẳng hạn chạy một bước dưới tenant hoặc principal đã được xác thực khác. Chỉ dùng nó ở boundary có chủ đích; tránh thay đổi ngữ cảnh tùy tiện ở sâu trong service vì sẽ làm luồng quyền truy cập khó theo dõi.

## 7. Binding theo thread và chia sẻ qua tác vụ con

Binding của `ScopedValue` gắn với thread đang thực thi `run()` hoặc `call()`. Trong cùng thread, các phương thức được gọi trực tiếp hoặc gián tiếp nhìn thấy binding hiện tại.

Không mặc định rằng một thread bất kỳ hoặc tác vụ gửi vào `ExecutorService` sẽ tự nhận binding của thread gọi. Tài liệu Java SE mô tả cơ chế kế thừa trong trường hợp có cấu trúc: các thread con được tạo bởi `StructuredTaskScope` kế thừa binding được capture khi scope được mở. Phạm vi cha chỉ kết thúc sau khi các tác vụ con trong scope hoàn tất.

**Giới hạn phiên bản tại JDK 27:** `ScopedValue` là API final từ JDK 25, nhưng `StructuredTaskScope` vẫn là preview lần thứ bảy theo JEP 533 trong JDK 27. Vì vậy, không đưa `StructuredTaskScope` vào ví dụ stable hoặc coi việc dùng nó là không cần preview. Nếu thử nghiệm kế thừa binding qua structured concurrency, phải dùng đúng JDK 27 và bật preview ở cả hai bước, ví dụ `javac --release 27 --enable-preview ...` và `java --enable-preview ...`. Các ví dụ `ScopedValue` trong bài này không cần `--enable-preview`.

Khi chia sẻ một giá trị qua các thread con, hãy dùng đối tượng bất biến. Nếu giá trị có trạng thái mutable, mọi truy cập đồng thời phải được đồng bộ phù hợp. `ScopedValue` làm cho binding có phạm vi rõ ràng; nó không tự biến đối tượng được bind thành immutable hoặc thread-safe.

## 8. ScopedValue và ThreadLocal

`ScopedValue` thường phù hợp hơn `ThreadLocal` khi dữ liệu được truyền một chiều từ caller xuống các callee trong một phạm vi thực thi.

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Thiết lập giá trị | Caller bind thông qua `Carrier.run()` hoặc `Carrier.call()`. | Thread có thể gọi `set()` để thay đổi giá trị. |
| Vòng đời | Giới hạn theo dynamic scope; tự khôi phục khi thao tác kết thúc. | Có thể tồn tại đến khi gọi `remove()` hoặc thread kết thúc. |
| Cách truyền dữ liệu | Một chiều từ caller xuống callee. | Có thể đọc/ghi từ nhiều phương thức chạy trên cùng thread. |
| Quyền truy cập | Đối tượng khóa đóng vai trò capability. | Bất kỳ code nào có tham chiếu tới `ThreadLocal` đều có thể gọi `get/set/remove`. |
| Chia sẻ trong concurrency | Có hỗ trợ kế thừa ở structured task scope. | Không tự động truyền giá trị theo cùng hợp đồng structured scope. |

`ThreadLocal` vẫn có trường hợp sử dụng phù hợp, ví dụ trạng thái mutable riêng từng thread hoặc cache gắn với vòng đời thread. Không cần thay mọi `ThreadLocal` bằng `ScopedValue`. Hãy chọn `ScopedValue` khi dữ liệu là ngữ cảnh chỉ đọc, được truyền từ caller xuống các phương thức được gọi trong một phạm vi có giới hạn.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo khóa mới mỗi request | Callee dùng khóa khác nên không đọc được binding của caller. | Tạo một khóa ổn định trong field `static final`. |
| Công khai field khóa | Bất kỳ code nào có khóa đều có thể đọc hoặc bind lại trong scope lồng. | Giữ key `private`, cung cấp accessor và binding boundary có kiểm soát. |
| Gọi `get()` ngoài phạm vi đã bind | Ném `NoSuchElementException`. | Dùng `orElse`, `orElseThrow` hoặc kiểm tra `isBound()` tùy hợp đồng. |
| Nghĩ binding tồn tại mãi trên thread | Có thể thiết kế logic phụ thuộc vào dữ liệu đã hết hạn. | Chỉ đọc trong phạm vi `run/call`; binding tự kết thúc sau callback. |
| Dùng object mutable không đồng bộ | Các thread con có thể tranh chấp dữ liệu. | Ưu tiên record/object immutable hoặc đồng bộ tất cả truy cập. |
| Nghĩ mọi thread mới đều kế thừa binding | Thread/executor thông thường không có hợp đồng kế thừa như StructuredTaskScope. | Truyền context rõ ràng hoặc dùng cơ chế concurrency có cấu trúc với trạng thái preview được xác minh. |
| Dùng API `runWhere()` hoặc `callWhere()` trong code mới | Đây là hình dạng API của các bản preview cũ, không phải cách dùng final. | Dùng `ScopedValue.where(key, value).run(...)` hoặc `.call(...)`. |

## 10. Lịch sử phiên bản và trạng thái hiện hành

Scoped Values trải qua nhiều vòng thử nghiệm trước khi trở thành API chính thức:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| 20 | 429 | Incubator trong module `jdk.incubator.concurrent`. |
| 21 | 446 | Preview lần đầu. |
| 22 | 464 | Preview lần hai. |
| 23 | 481 | Preview lần ba. |
| 24 | 487 | Preview lần bốn; API được làm fluent, dùng `Carrier.run/call`. |
| 25 | 506 | API final, không cần bật preview. |
| 26–27 | — | Tiếp tục là API chính thức; Javadoc JDK 27 ghi `Since: 25`. |

Các đoạn code cũ có thể dùng `ScopedValue.runWhere(...)` hoặc `ScopedValue.callWhere(...)`. Hai phương thức này thuộc các bản preview trước khi API được làm fluent ở JDK 24. Trong code hiện hành, dùng `ScopedValue.where(...).run(...)` và `ScopedValue.where(...).call(...)`.

## Ghi nhớ

- `ScopedValue.newInstance()` tạo khóa có kiểu, ban đầu chưa bind.
- Tạo khóa một lần, thường bằng field `private static final`; không tạo key mới theo từng request.
- `ScopedValue.where(key, value)` tạo Carrier; `.run()` dùng cho thao tác không trả kết quả và `.call()` dùng khi cần kết quả.
- `get()`, `isBound()`, `orElse()` và `orElseThrow()` đọc binding trong thread hiện tại.
- Binding có dynamic scope; tự kết thúc hoặc khôi phục binding trước khi callback kết thúc, kể cả khi có exception.
- Khóa là capability. Giữ khóa private, expose accessor hẹp và kiểm soát nơi được phép bind.
- `ScopedValue` final từ JDK 25 theo JEP 506. Các API preview/incubator trước đó chỉ có ý nghĩa lịch sử.
- Trong JDK 27, `StructuredTaskScope` vẫn preview; không coi inheritance qua API này là tính năng stable của Structured Concurrency.

## Tài liệu tham khảo

- [JEP 506: Scoped Values](https://openjdk.org/jeps/506)
- [JEP 429: Scoped Values (Incubator, JDK 20)](https://openjdk.org/jeps/429)
- [JEP 446: Scoped Values (Preview, JDK 21)](https://openjdk.org/jeps/446)
- [JEP 464: Scoped Values (Second Preview, JDK 22)](https://openjdk.org/jeps/464)
- [JEP 481: Scoped Values (Third Preview, JDK 23)](https://openjdk.org/jeps/481)
- [JEP 487: Scoped Values (Fourth Preview, JDK 24)](https://openjdk.org/jeps/487)
- [JEP 533: Structured Concurrency (Seventh Preview, JDK 27)](https://openjdk.org/jeps/533)
- [Java SE 27 API — `ScopedValue`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html)
- [Java SE 27 API — `ScopedValue.Carrier`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [Java SE 27 API — `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Oracle Java SE 27 Core Libraries — Scoped Values](https://docs.oracle.com/en/java/javase/27/core/scoped-values.html)
