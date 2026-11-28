# Ràng buộc nhiều khóa và ghi đè giá trị trong phạm vi lồng nhau

## 1. Bài toán và mục tiêu

Trong ứng dụng Java hiện đại, một luồng xử lý thường cần mang theo nhiều thông tin ngữ cảnh: định danh request, tenant hiện tại, chế độ kiểm toán, locale hoặc thông tin phục vụ ghi log. Nếu truyền tất cả thông tin qua mọi tham số phương thức, chữ ký của nhiều lớp trung gian sẽ phình ra; nếu đưa vào biến toàn cục hoặc một ThreadLocal có thể sửa tùy ý, dữ liệu dễ rò rỉ giữa các lần xử lý.

**ScopedValue** là API thuộc **java.lang** được hoàn thiện trong **Java 25 (JEP 506)**. API này cho phép liên kết một khóa với một giá trị trong khoảng thời gian thực thi có cấu trúc, đọc giá trị ở những lời gọi sâu hơn, đồng thời tạm thời **ràng buộc lại (rebind)** khóa trong phạm vi lồng nhau. Khi đoạn xử lý kết thúc bình thường hoặc ném exception, binding mới được tháo và binding trước đó xuất hiện trở lại.

Bài **Ràng buộc nhiều khóa và ghi đè giá trị trong phạm vi lồng nhau**, thuộc chương **ScopedValue** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào hai khả năng có thể dùng ngay:

1. **Kết hợp nhiều khóa** bằng chuỗi **ScopedValue.where(key1, value1).where(key2, value2)...run(...)**.
2. **Ghi đè có thời hạn** một hoặc nhiều khóa bằng lời gọi **run/call lồng nhau**, đồng thời giữ nguyên các khóa khác trong scope bên ngoài.

Sau bài, bạn sẽ phân biệt hai cách ghi đè của **Carrier** và **dynamic scope**, hiểu trường hợp chưa có binding và giá trị null, kiểm thử cơ chế khôi phục khi có lỗi, biết giới hạn khi chuyển sang thread khác và tránh các anti-pattern về bảo mật hoặc state mutable.

**Phạm vi tính tương thích:** các đoạn mã dùng API ScopedValue **đã chính thức có trong Java 25**, không cần **--enable-preview**. Trong Java 25, **Structured Concurrency/StructuredTaskScope** vẫn là preview, nên bài **không yêu cầu** bật tính năng đó và không dùng nó làm nền tảng cho ví dụ chạy được.

## 2. Ba khái niệm cần tách bạch: key, Carrier và dynamic scope

Một **ScopedValue<T>** là **khóa** có kiểu, không phải một hộp lưu giá trị toàn cục. Khóa thường được tạo một lần:

~~~java
private static final ScopedValue<String> TENANT = ScopedValue.newInstance();
private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();
~~~

Không cần import vì **ScopedValue** thuộc **java.lang**. Những khóa **static final** ở đây là danh tính dùng để truy cập binding; chúng không có giá trị mặc định ngay sau khi tạo.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Key** | Đối tượng định danh một giá trị kiểu T trong scope hiện tại. | **ScopedValue<String> TENANT** |
| **Binding** | Quan hệ tạm thời giữa key và value trong một phạm vi thực thi. | TENANT gắn với tenant-a |
| **Carrier** | Tập ánh xạ key → value bất biến, chuẩn bị trước khi chạy đoạn code. | TENANT=tenant-a, REQUEST_ID=req-42 |
| **Dynamic scope** | Đoạn thực thi trực tiếp hoặc gián tiếp bên trong **run/call**; không chỉ giới hạn một cặp dấu ngoặc của lambda. | handleRequest() gọi service() rồi repository() |
| **Rebinding** | Tạo binding mới cho key đã có binding bên ngoài. | TENANT đổi tạm thành tenant-b |
| **Restoration** | Khi scope lồng kết thúc, binding bên ngoài được khôi phục tự động. | TENANT trở lại tenant-a |

~~~mermaid
flowchart TD
    A["Không có binding"] --> B["Carrier: TENANT=a, REQUEST=r1"]
    B --> C["run outer: TENANT=a, REQUEST=r1"]
    C --> D["run inner: TENANT=b; REQUEST vẫn r1"]
    D --> E["inner kết thúc: TENANT=a, REQUEST=r1"]
    E --> F["outer kết thúc: cả hai trở lại trạng thái trước"]
~~~

**Phạm vi động** nghĩa là code được gọi **sâu bên trong** lambda, kể cả qua nhiều service method, vẫn có thể đọc cùng key nếu chạy trong cùng phạm vi thực thi/thread thích hợp. Ngược lại, **Carrier chỉ chứa các ánh xạ chuẩn bị sẵn**, chưa kích hoạt binding cho current thread cho tới khi **run/call** được thực thi.

## 3. Bảng API Java 25 còn áp dụng

| API | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| **ScopedValue.newInstance()** | Tạo một key mới. | Ban đầu chưa được bind trên bất kỳ thread nào. |
| **ScopedValue.where(KEY, value)** | Tạo Carrier có một mapping. | Chưa chạy tác vụ, chưa thay đổi binding hiện hành. |
| **carrier.where(OTHER, value)** | Trả về **Carrier mới** thêm hoặc thay mapping. | Carrier cũ không bị sửa. |
| **carrier.run(Runnable)** | Chạy tác vụ void với toàn bộ mapping được bind. | Tự khôi phục khi chạy xong hoặc throw. |
| **carrier.call(CallableOp)** | Chạy tác vụ trả kết quả; có thể ném checked exception. | Kết quả và exception được truyền ra ngoài. |
| **KEY.get()** | Đọc binding của key trong current thread. | Ném **NoSuchElementException** nếu chưa bind. |
| **KEY.isBound()** | Kiểm tra key có binding ở current thread hay không. | Không đồng nghĩa giá trị khác null. |
| **KEY.orElse(fallback)** | Trả fallback chỉ khi **không có binding**. | Nếu được bind vào null, trả null. |
| **KEY.orElseThrow(supplier)** | Ném exception tùy chọn nếu key chưa bind. | Phù hợp với context bắt buộc. |
| **carrier.get(KEY)** | Đọc mapping bên trong Carrier. | Không phải **KEY.get()** của current scope. |

API tham khảo: [ScopedValue Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html) và [ScopedValue.Carrier Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).

### Hai ý quan trọng về thời điểm

~~~java
ScopedValue<String> key = ScopedValue.newInstance();
ScopedValue.Carrier carrier = ScopedValue.where(key, "ready");

System.out.println(carrier.get(key)); // ready: đọc ánh xạ trong Carrier
System.out.println(key.isBound());    // false: chưa vào dynamic scope

carrier.run(() -> {
    System.out.println(key.get());    // ready: binding có hiệu lực
});

System.out.println(key.isBound());    // false: run đã kết thúc
~~~

Nếu **key.get()** được gọi ở hai dòng ngoài **run**, code sẽ ném **NoSuchElementException**. Việc **Carrier** có mapping **không** làm biến key trở thành bound trên current thread.

## 4. Ràng buộc nhiều khóa trong cùng một Carrier

Khi cần truyền nhiều giá trị độc lập, nối các lần **where** rồi chỉ gọi **run** một lần. Ví dụ một request có tenant, request ID và chế độ xử lý:

~~~java
public final class MultipleKeysDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();
    private static final ScopedValue<Boolean> AUDIT =
            ScopedValue.newInstance();

    static void process() {
        System.out.println("tenant=" + TENANT.get());
        System.out.println("request=" + REQUEST.get());
        System.out.println("audit=" + AUDIT.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-a")
                .where(REQUEST, "req-001")
                .where(AUDIT, true)
                .run(MultipleKeysDemo::process);
    }
}
~~~

Kết quả:

~~~text
tenant=tenant-a
request=req-001
audit=true
~~~

**Phân tích:** **where(TENANT, ...)** ban đầu trả về một **ScopedValue.Carrier**. Các lần **.where(REQUEST, ...)** và **.where(AUDIT, ...)** đều được gọi trên Carrier; cuối cùng **run** gắn **đồng thời cả ba khóa** cho current thread trong quá trình **process** thực thi.

Không cần tạo ba **run** riêng cho ba key. Khi tổ chức code, nên nhóm các key cần hiệu lực cùng một ranh giới request/task vào một Carrier để dễ kiểm thử và theo dõi vòng đời.

### Ràng buộc nhiều khóa rồi trả về kết quả

Nếu xử lý cần trả về giá trị, dùng **call**:

~~~java
public final class MultiKeyCallDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<Integer> LIMIT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        String summary = ScopedValue.where(TENANT, "tenant-a")
                .where(LIMIT, 20)
                .call(() -> TENANT.get() + ":limit=" + LIMIT.get());

        System.out.println(summary); // tenant-a:limit=20
        System.out.println(TENANT.isBound()); // false
        System.out.println(LIMIT.isBound());  // false
    }
}
~~~

**run** nhận **Runnable** (không có giá trị trả về); **call** nhận **ScopedValue.CallableOp** (có giá trị trả về và hỗ trợ exception). Không cần tự tạo biến **ThreadLocal** để chuyển kết quả ra khỏi lambda.

## 5. Hai kiểu ghi đè: mapping trong Carrier và binding trong scope

Đây là phần dễ nhầm lẫn nhất.

### 5.1. Ghi đè mapping trước khi chạy: Carrier.where

~~~java
public final class CarrierOverrideDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.Carrier base = ScopedValue.where(TENANT, "tenant-a")
                .where(REQUEST, "req-01");

        // Tạo Carrier mới; không sửa base.
        ScopedValue.Carrier revised = base.where(TENANT, "tenant-b");

        System.out.println(base.get(TENANT));    // tenant-a
        System.out.println(revised.get(TENANT)); // tenant-b
        System.out.println(revised.get(REQUEST)); // req-01
        System.out.println(TENANT.isBound());     // false

        base.run(() -> System.out.println(TENANT.get()));    // tenant-a
        revised.run(() -> System.out.println(TENANT.get())); // tenant-b
    }
}
~~~

**Nếu một Carrier đã có key TENANT, gọi .where(TENANT, value2) sẽ trả về Carrier mới với mapping TENANT=value2.** Carrier cũ vẫn chứa TENANT=value1. Hai lần **run** trên hai Carrier ở ví dụ trên là **hai scope tuần tự**, không phải scope lồng nhau.

Do **Carrier bất biến và thread-safe**, có thể dùng lại Carrier làm cấu hình đầu vào cho nhiều lần gọi, với điều kiện các value bên trong được quản lý an toàn (đặc biệt nếu value là object mutable). Đừng đồng nhất tính bất biến của Carrier với tính bất biến của mọi object được tham chiếu.

### 5.2. Ghi đè binding đang có: nested run/call

~~~java
public final class NestedOverrideDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-a")
                .where(REQUEST, "req-01")
                .run(() -> {
                    System.out.println("outer=" + TENANT.get());  // tenant-a

                    ScopedValue.where(TENANT, "tenant-b").run(() -> {
                        System.out.println("inner=" + TENANT.get()); // tenant-b
                        System.out.println("req=" + REQUEST.get());  // req-01
                    });

                    System.out.println("restored=" + TENANT.get()); // tenant-a
                });

        System.out.println(TENANT.isBound()); // false
        System.out.println(REQUEST.isBound()); // false
    }
}
~~~

Ở scope trong, **TENANT** được bind lại thành tenant-b. **REQUEST** không bị bind lại nên vẫn đọc được **req-01** từ scope ngoài. Khi scope trong kết thúc, **TENANT** quay lại tenant-a. Khi scope ngoài kết thúc, cả hai key trở thành unbound (vì trước outer không có binding).

**Tính chất phục hồi tự động** là điểm khác biệt quan trọng so với mã sử dụng **ThreadLocal.set()/remove()** thủ công. Không cần một khối **finally** chỉ để khôi phục các binding của ScopedValue; API quản lý vòng đời đó.

## 6. Phạm vi ba tầng và ghi đè một phần tập khóa

Một ứng dụng có thể có nhiều tầng xử lý: request → service → audit. Tầng audit chỉ muốn thay chế độ ghi log và mã request con, nhưng vẫn phải giữ tenant của request gốc.

~~~java
public final class ThreeScopesDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();
    private static final ScopedValue<String> MODE =
            ScopedValue.newInstance();

    static void show(String label) {
        System.out.printf("%s: tenant=%s, request=%s, mode=%s%n",
                label, TENANT.get(), REQUEST.get(), MODE.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-a")
                .where(REQUEST, "req-01")
                .where(MODE, "normal")
                .run(() -> {
                    show("request");

                    ScopedValue.where(MODE, "audit").run(() -> {
                        show("audit");

                        ScopedValue.where(REQUEST, "req-01/audit")
                                .run(() -> show("nested"));

                        show("after nested");
                    });

                    show("after audit");
                });
    }
}
~~~

Kết quả:

~~~text
request: tenant=tenant-a, request=req-01, mode=normal
audit: tenant=tenant-a, request=req-01, mode=audit
nested: tenant=tenant-a, request=req-01/audit, mode=audit
after nested: tenant=tenant-a, request=req-01, mode=audit
after audit: tenant=tenant-a, request=req-01, mode=normal
~~~

Trong mỗi scope, **binding gần nhất** của một key quyết định giá trị được đọc. Ghi đè một key **không xóa** các binding của key khác. Khi kết thúc scope trong, lần lookup tiếp theo tìm về binding ở scope bao ngoài.

### Sơ đồ ngăn xếp binding theo key

~~~text
Trước run:
    TENANT = unbound; REQUEST = unbound; MODE = unbound

Outer run:
    TENANT = tenant-a; REQUEST = req-01; MODE = normal

    Audit run:
        TENANT = tenant-a; REQUEST = req-01; MODE = audit

        Nested run:
            TENANT = tenant-a; REQUEST = req-01/audit; MODE = audit

        Sau nested:
            TENANT = tenant-a; REQUEST = req-01; MODE = audit

Sau audit:
    TENANT = tenant-a; REQUEST = req-01; MODE = normal

Sau outer:
    TENANT = unbound; REQUEST = unbound; MODE = unbound
~~~

Đây là **mô hình tư duy** cho việc lookup binding, không phải mô tả chi tiết cấu trúc bộ nhớ nội bộ JVM. Không cần tự cài một Stack để hiện thực tính năng này.

## 7. Kiểm tra ngoại lệ và khôi phục binding

Vì scope được quản lý tự động, Java khôi phục binding kể cả khi tác vụ bên trong ném exception.

~~~java
public final class ExceptionRestoreDemo {
    private static final ScopedValue<String> USER =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(USER, "outer").run(() -> {
            try {
                ScopedValue.where(USER, "inner").run(() -> {
                    System.out.println(USER.get()); // inner
                    throw new IllegalStateException("Không xử lý được");
                });
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }

            // Exception đã thoát scope trong; binding ngoài còn nguyên.
            System.out.println(USER.get()); // outer
        });

        System.out.println(USER.isBound()); // false
    }
}
~~~

**Điều không thay đổi:** exception vẫn lan truyền theo quy tắc Java, trừ khi code tự bắt. **ScopedValue** không nuốt exception, không rollback database, không hủy I/O đã xảy ra và không biến code thành transaction. Nó chỉ bảo đảm khôi phục **binding động** khi scope kết thúc.

Nếu một đoạn code tạo nested scope và **return** sớm hoặc throw, không cần gọi **KEY.remove()**. Trái lại, giữ một đối tượng **Carrier** ở nơi khác cũng không kéo dài hiệu lực của binding sau khi **run/call** kết thúc.

## 8. Key chưa bound, null và fallback

Một key được tạo bằng **newInstance()** ban đầu chưa có binding trên current thread. Các cách đọc có ý nghĩa khác nhau:

~~~java
import java.util.NoSuchElementException;

public final class UnboundAndNullDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println(TENANT.isBound());       // false
        System.out.println(TENANT.orElse("public")); // public

        try {
            TENANT.get();
        } catch (NoSuchElementException ex) {
            System.out.println("Chưa có tenant trong scope");
        }

        // null là một giá trị được phép bind trong Java 25.
        ScopedValue.where(TENANT, null).run(() -> {
            System.out.println(TENANT.isBound()); // true
            System.out.println(TENANT.get() == null); // true
            System.out.println(TENANT.orElse("public") == null); // true
        });

        System.out.println(TENANT.isBound()); // false
    }
}
~~~

| Trạng thái key | **isBound()** | **get()** | **orElse("fallback")** |
| --- | --- | --- | --- |
| Chưa có binding trong current thread. | false | Ném **NoSuchElementException**. | Trả **fallback**. |
| Bound vào chuỗi **tenant-a**. | true | Trả tenant-a. | Trả tenant-a. |
| Bound vào **null**. | true | Trả null. | Trả null, **không** trả fallback. |

**Khuyến nghị thiết kế:** dù API cho phép binding **null**, hãy hạn chế dùng null trong request context nếu nó khiến code khó phân biệt giữa “đã cố ý bind null” và “chưa có binding”. Với dữ liệu bắt buộc, kiểm tra **Objects.requireNonNull(...)** tại ranh giới và dùng **orElseThrow(...)** để báo lỗi rõ ràng:

~~~java
String tenant = TENANT.orElseThrow(
        () -> new IllegalStateException("Thiếu tenant trong request scope"));
~~~

**orElseThrow** ở đây xử lý **không có binding**. Nếu đã bind null thì trả null; vì vậy vẫn nên từ chối null **trước khi bind** khi ngữ cảnh bắt buộc không được null.

## 9. Ví dụ thực tế: request context và nested override được kiểm soát

Trong ứng dụng web hoặc service, nên tạo một lớp ở **ranh giới request** chịu trách nhiệm xác thực dữ liệu ban đầu rồi bind context cho toàn bộ xử lý đồng bộ. Các lớp phía sâu có thể truy cập context qua accessor, không cần truyền request ID hoặc tenant qua mọi phương thức.

~~~java
import java.util.Objects;

public final class RequestContextDemo {
    record RequestContext(String tenantId, String requestId, boolean audit) {
        RequestContext {
            if (Objects.requireNonNull(tenantId, "tenantId").isBlank()) {
                throw new IllegalArgumentException("tenantId rỗng");
            }
            if (Objects.requireNonNull(requestId, "requestId").isBlank()) {
                throw new IllegalArgumentException("requestId rỗng");
            }
        }
    }

    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    private static void handle() {
        RequestContext ctx = CURRENT.orElseThrow(
                () -> new IllegalStateException("Ngoài request scope"));

        System.out.println(ctx.tenantId() + "/" + ctx.requestId()
                + " audit=" + ctx.audit());
    }

    public static void main(String[] args) {
        RequestContext ctx = new RequestContext("tenant-a", "req-01", false);

        ScopedValue.where(CURRENT, ctx).run(() -> {
            handle(); // tenant-a/req-01 audit=false

            // Chỉ đổi chế độ audit cho một đoạn con.
            RequestContext auditContext =
                    new RequestContext(ctx.tenantId(), ctx.requestId(), true);

            ScopedValue.where(CURRENT, auditContext)
                    .run(RequestContextDemo::handle);

            handle(); // tenant-a/req-01 audit=false
        });
    }
}
~~~

Ví dụ này cho thấy **một ScopedValue chứa một record bất biến** có thể thay cho nhiều key khi các thuộc tính luôn đi cùng nhau. Trong ứng dụng nhiều tenant, **không cho phép bất kỳ code nào tự ghi đè tenant để nâng quyền**: tenant ban đầu phải đến từ thành phần xác thực/ủy quyền đã được tin cậy; chỉ code được phép mới được tạo scope con thay đổi tenant. Dynamic binding không phải cơ chế authorization.

**Record không tự bảo đảm deep immutability** nếu các component chứa List/Map/object mutable. Ví dụ chỉ chứa String và boolean nên có ngữ nghĩa bất biến phù hợp. Với một danh sách vai trò, hãy cân nhắc defensive copy và chỉ công bố giao diện dữ liệu đọc.

### Nên dùng nhiều khóa hay một record?

| Thiết kế | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| **Nhiều ScopedValue riêng** | Các thành phần được thay đổi lồng nhau độc lập, ví dụ REQUEST_ID và AUDIT_MODE. | Nhiều key và binding; phải giữ bất biến tương quan giữa các key khi cần. |
| **Một ScopedValue<RequestContext>** | Các trường thường là một đơn vị ngữ nghĩa và cần thay đồng bộ. | Muốn đổi một trường phải tạo context mới; logic code có thể rõ ràng hơn. |
| **Tham số phương thức tường minh** | Đường truyền dữ liệu ngắn, nghiệp vụ cần thấy dependency rõ trong API. | Chữ ký có thể dài khi context đi xuyên nhiều lớp trung gian. |

Tài liệu JDK lưu ý **ScopedValue** được thiết kế cho **số lượng khóa tương đối nhỏ**. Nếu cần hàng chục trường luôn đi cùng nhau, một **record context** có thể tốt hơn việc tạo hàng chục ScopedValue riêng. Không cần thay tham số tường minh bằng ScopedValue trong mọi hàm; sử dụng đúng những điểm có dynamic context đáng kể.

## 10. Bảo mật và quyền truy cập vào khóa

Một **ScopedValue** có thể được xem như một **capability**: code nào giữ tham chiếu đến key thì có thể đọc binding tương ứng khi nó đang bound. Vì thế, phạm vi **visibility** của key quan trọng:

~~~java
public final class TenantScope {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    private TenantScope() {}

    public static void runForTenant(String tenant, Runnable action) {
        String checked = java.util.Objects
                .requireNonNull(tenant, "tenant").strip();
        if (checked.isEmpty()) {
            throw new IllegalArgumentException("tenant rỗng");
        }
        ScopedValue.where(TENANT, checked).run(action);
    }

    public static String currentTenant() {
        return TENANT.orElseThrow(
                () -> new IllegalStateException("Thiếu tenant scope"));
    }
}
~~~

Code phía ngoài dùng **TenantScope.runForTenant(...)** và **TenantScope.currentTenant()** mà không có quyền trực tiếp lấy key private để tạo binding tùy ý. Tuy nhiên, ai được phép gọi **runForTenant** với tenant nào vẫn phải do hệ xác thực/ủy quyền quyết định. **Không coi việc key private là thay thế cho kiểm tra quyền.**

Những việc nên tránh:

- Để **public static final ScopedValue** mang dữ liệu nhạy cảm nếu không cần công bố key cho mọi nơi.
- Bind **token/password** hoặc PII rồi ghi nguyên ra log/metrics.
- Tin tenant/role do client gửi mà không xác thực, sau đó cấp quyền chỉ vì nó xuất hiện trong ScopedValue.
- Cho phép nested scope thay tenant hoặc quyền truy cập mà không có nghiệp vụ được ủy quyền.
- Tạo scope sống quá lâu và giữ tham chiếu object lớn hoặc state mutable không cần thiết.

## 11. Thread boundary: ScopedValue không phải context propagation tự động cho mọi task

Binding của **ScopedValue là per-thread**. Trong một chuỗi gọi đồng bộ, các method được gọi sâu bên trong **run/call** đọc được binding. Điều này **không** có nghĩa gửi một task sang **ExecutorService**, **CompletableFuture** hoặc **Thread.startVirtualThread(...)** sẽ mặc nhiên mang binding của caller.

Để giữ bài học chạy bằng Java 25 **không cần preview**, ví dụ sau chuyển dữ liệu **tường minh** rồi bind lại trong virtual thread:

~~~java
public final class VirtualThreadBridge {
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST, "req-01").run(() -> {
            // Capture dữ liệu tại ranh giới, không giả định thread tự kế thừa.
            String captured = REQUEST.get();

            Thread worker = Thread.startVirtualThread(() -> {
                ScopedValue.where(REQUEST, captured).run(() ->
                        System.out.println("worker=" + REQUEST.get()));
            });

            try {
                worker.join();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Bị ngắt khi đợi task", ex);
            }
        });
    }
}
~~~

Ví dụ chủ động **capture immutable String** và **rebind** ở phía worker. Với task gửi đi qua queue/network, cách chuyển thông tin phải tuân theo hợp đồng message/header và chính sách bảo mật; ScopedValue trong process **không tự truyền qua HTTP, gRPC hoặc broker**.

### Có chuyện kế thừa ScopedValue giữa thread không?

Có, nhưng chỉ trong những trường hợp **structured** được API hỗ trợ. Trong Java 25, **StructuredTaskScope** thuộc tính năng **Structured Concurrency còn ở trạng thái preview**; khi dùng đúng scope được cấu trúc, các subtasks có thể kế thừa binding phù hợp từ parent scope. **Bài này không sử dụng StructuredTaskScope làm ví dụ mặc định**, vì ghi chú học thuật chỉ yêu cầu kiến thức ổn định và hiện hành.

Không gọi **ThreadLocal.InheritableThreadLocal** hoặc giả định thread pool tự kế thừa ScopedValue; đó là những cơ chế khác nhau. Đối với thư viện/framework dùng context propagation riêng (logging MDC, Micrometer tracing, OpenTelemetry), cần kiểm tra bridge/propagator đúng với framework; **ScopedValue không thay thế tự động tracing context**.

## 12. So sánh với ThreadLocal và lựa chọn API

| Tiêu chí | ScopedValue trong Java 25 | ThreadLocal |
| --- | --- | --- |
| Mục tiêu chính | Truyền dữ liệu theo chiều đọc qua dynamic scope có cấu trúc. | Trạng thái cục bộ của thread, có thể đọc/ghi thay đổi. |
| Tạo binding | **where(...).run/call(...)** | **set(...)** |
| Ghi đè | Scope lồng nhau tạo binding mới và tự phục hồi. | Phải tự lưu/khôi phục giá trị nếu muốn nesting tương đương. |
| Vòng đời | Gắn với thời gian thực thi của run/call. | Có thể tồn tại tới khi remove hoặc thread chấm dứt. |
| Khả năng code phía sâu thay binding | Không có **KEY.set(...)**; cần tạo nested binding. | Bất cứ code có ThreadLocal có thể gọi set. |
| An toàn khi dùng thread pool | Không tự truyền sang task bất kỳ; cần thiết kế ranh giới. | Dễ tồn dư giá trị nếu quên remove trên worker thread tái sử dụng. |
| Giá trị được bind | Có thể là mutable nhưng **nên bất biến**. | Có thể là mutable/được thay theo nhu cầu. |

**ThreadLocal không phải API đã bị xóa hay không còn hợp lệ.** Nó vẫn có chỗ dùng khi cần state mutable gắn với một thread hoặc tích hợp framework hiện có. **ScopedValue** thích hợp hơn cho **ngữ cảnh truyền một chiều, phạm vi giới hạn, nhiều tầng lời gọi**. Không đổi toàn bộ ThreadLocal sang ScopedValue chỉ vì ứng dụng đã nâng lên JDK 25.

### Không dùng ScopedValue làm biến trạng thái chỉnh sửa liên tục

Sai định hướng:

~~~java
// Thiết kế kém: bind một object mutable và sửa nó qua nhiều lớp.
private static final ScopedValue<java.util.Map<String, Object>> STATE =
        ScopedValue.newInstance();
~~~

Giá trị đã bind không bị ngăn sửa **object** nó tham chiếu. Nếu các method thay đổi Map này, việc dùng ScopedValue **không** biến Map thành bất biến hoặc thread-safe. Hãy chuyển sang record immutable, truyền tham số, dùng dữ liệu request đã kiểm tra hoặc chọn công cụ quản lý mutable state thích hợp.

## 13. Kiểm thử với JUnit 5: multi-key, nesting, exception

Các bài test nên xác nhận **giá trị trong từng scope** và **trạng thái sau khi scope kết thúc**, không chỉ kiểm tra output console.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ScopedValueBindingsTest {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();

    @Test
    void bindsMultipleKeysAndRestoresAfterRun() {
        assertFalse(TENANT.isBound());
        assertFalse(REQUEST.isBound());

        ScopedValue.where(TENANT, "a")
                .where(REQUEST, "r1")
                .run(() -> {
                    assertEquals("a", TENANT.get());
                    assertEquals("r1", REQUEST.get());

                    ScopedValue.where(TENANT, "b").run(() -> {
                        assertEquals("b", TENANT.get());
                        assertEquals("r1", REQUEST.get());
                    });

                    assertEquals("a", TENANT.get());
                    assertEquals("r1", REQUEST.get());
                });

        assertFalse(TENANT.isBound());
        assertFalse(REQUEST.isBound());
    }

    @Test
    void carrierWhereIsImmutableAndCanReplaceMapping() {
        ScopedValue.Carrier original =
                ScopedValue.where(TENANT, "a").where(REQUEST, "r1");
        ScopedValue.Carrier changed = original.where(TENANT, "b");

        assertEquals("a", original.get(TENANT));
        assertEquals("b", changed.get(TENANT));
        assertEquals("r1", changed.get(REQUEST));
        assertFalse(TENANT.isBound());
    }

    @Test
    void restoresParentEvenIfChildThrows() {
        ScopedValue.where(TENANT, "outer").run(() -> {
            assertThrows(IllegalArgumentException.class, () ->
                    ScopedValue.where(TENANT, "inner").run(() -> {
                        assertEquals("inner", TENANT.get());
                        throw new IllegalArgumentException("test");
                    }));
            assertEquals("outer", TENANT.get());
        });

        assertFalse(TENANT.isBound());
    }

    @Test
    void callReturnsResultAndScopeEnds() {
        String result = ScopedValue.where(TENANT, "tenant-a")
                .where(REQUEST, "req-1")
                .call(() -> TENANT.get() + ":" + REQUEST.get());

        assertEquals("tenant-a:req-1", result);
        assertFalse(TENANT.isBound());
        assertFalse(REQUEST.isBound());
    }
}
~~~

**Kiểm thử đúng trọng tâm:** khi test Carrier, dùng **carrier.get(KEY)** để đọc mapping, còn trong run/call dùng **KEY.get()** để đọc binding hiện hành. Trộn hai thao tác là nguyên nhân khiến một bài test “pass” dù thực tế chưa bind key.

Các test dùng key static final và chạy trong thread test hiện tại. Nếu chuyển sang integration test với **ExecutorService** hoặc **CompletableFuture**, cần kiểm thử tường minh ranh giới thread; không suy ra propagation thành công chỉ từ bài test tuần tự.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| **NoSuchElementException** từ KEY.get(). | Đọc ngoài scope hoặc key chưa từng được bind. | Đưa lời gọi vào run/call; dùng isBound/orElseThrow cho ngữ cảnh bắt buộc. |
| Tưởng **carrier.get(KEY)** là giá trị của current thread. | Carrier giữ mapping, không phải scope hiện hành. | Phân biệt Carrier.get với ScopedValue.get. |
| **orElse("default")** trả null. | Key đã được bind vào null. | Tránh null cho context bắt buộc; validate khi bind. |
| Gọi **carrier.where(KEY, newValue)** nhưng Carrier cũ không đổi. | Carrier là immutable; where trả Carrier mới. | Lưu biến mới hoặc chain ngay vào run/call. |
| Nested scope kết thúc nhưng KEY vẫn có giá trị cũ. | Đúng thiết kế: binding outer được khôi phục. | Kiểm tra scope cha; không tự gọi remove. |
| Sau outer run KEY không còn bound. | Đúng thiết kế: vòng đời binding đã hết. | Giữ xử lý cần context bên trong run/call. |
| Task trong thread pool không thấy binding. | Binding per-thread, không tự propagate tới task tùy ý. | Capture context và bind lại ở ranh giới hoặc dùng cơ chế structured được hỗ trợ. |
| Đổi role/tenant lồng nhau gây lộ dữ liệu. | Rebinding được gọi không qua kiểm tra quyền. | Hạn chế key/API truy cập, xác thực tenant/role ở trust boundary. |
| Ghi nhận metric/log lẫn request. | Context được bind sai phạm vi hoặc dữ liệu mutable dùng chung. | Bind tại đúng ranh giới request; dùng immutable context; test song song. |
| IDE bảo **ScopedValue là preview**. | JDK/IDE/compiler còn ở bản trước Java 25. | Dùng JDK 25 và language level/release 25; cập nhật IDE/build plugin. |
| Compile báo không có overload **where(...).run**. | Dùng ví dụ API preview cũ hoặc compiler không phải Java 25. | Theo API **ScopedValue.Carrier** Java 25 chính thức. |

### Cách chẩn đoán một nested scope sai

1. Xác minh **java --version** và **javac --version** là JDK 25; nếu dùng Maven/Gradle, kiểm tra toolchain release 25.
2. In **KEY.isBound()** ngay trước outer run, đầu outer run, đầu inner run, sau inner, sau outer.
3. Nếu build dùng **Carrier**, so **carrier.get(KEY)** và **KEY.get()** để tránh nhầm mapping với active binding.
4. Nếu lỗi xuất hiện ở task async, ghi thread name và xác định code đã capture/rebind tại boundary hay chưa.
5. Nếu có exception, kiểm tra binding đã khôi phục đúng sau khi catch; phân biệt exception handling và scope restoration.
6. Nếu dùng context nhiều thuộc tính, kiểm tra tính bất biến và xem có cần gom thành một record không.

## 15. Bài tập tổng hợp

### Bài A — Ràng buộc ba khóa

Tạo key **TENANT (String)**, **REQUEST_ID (String)** và **READ_ONLY (Boolean)**. Bind cả ba trong một Carrier, gọi một phương thức sâu hơn để in ra giá trị. Xác nhận ngoài **run** cả ba key đều unbound.

**Đạt:** có đúng ba mapping, giá trị đọc qua **KEY.get()** trong scope; không còn binding sau run.

### Bài B — Ghi đè một key, giữ hai key khác

Trong outer scope TENANT=a, REQUEST_ID=req-1, READ_ONLY=true, tạo inner scope TENANT=b. Dự đoán REQUEST_ID và READ_ONLY ở inner; kiểm chứng sau inner giá trị TENANT trở lại a.

**Đạt:** chỉ TENANT bị shadow; các key khác kế thừa outer scope.

### Bài C — Carrier bất biến

Tạo **base = where(TENANT, a).where(REQUEST_ID, r1)**; tạo **modified = base.where(TENANT, b)**. Kiểm tra **base.get(TENANT)=a**, **modified.get(TENANT)=b** và **TENANT.isBound()=false** trước khi run.

**Đạt:** phân biệt thay mapping trong Carrier với rebind trong nested dynamic scope.

### Bài D — Lỗi trong scope con

Bind TENANT=outer; ở inner bind TENANT=inner rồi throw exception. Catch ở outer, xác nhận TENANT=outer và bên ngoài outer TENANT unbound.

**Đạt:** không cần thủ công restore; exception vẫn được xử lý riêng.

### Bài E — Giá trị null và key chưa có binding

Test ba trạng thái: unbound, bound với chuỗi hợp lệ và bound với null. So **isBound**, **get**, **orElse** và **orElseThrow**. Chọn chính sách không cho phép bind null trong RequestContext của nhóm.

**Đạt:** không nhầm unbound với bound-null; có validation hợp lý.

### Bài F — Truyền sang virtual thread có chủ đích

Trong outer scope REQUEST_ID=req-1, tạo virtual thread riêng. Đầu tiên quan sát việc không thể mặc định dựa vào binding ở caller; sau đó **capture String** ở caller và **ScopedValue.where(REQUEST_ID, captured).run(...)** tại worker. Đợi worker kết thúc.

**Đạt:** đọc được request ID ở worker bằng cơ chế bind có chủ đích mà không bật preview.

### Bài G — Thiết kế context thực tế

Thiết kế **RequestContext** record gồm tenantId, requestId, auditMode. So phương án ba key riêng với một key **ScopedValue<RequestContext>**, nêu nơi kiểm tra quyền khi rebind tenant.

**Đạt:** giải thích tính nhất quán dữ liệu, vòng đời request, chi phí nhiều key và giới hạn bảo mật.

### Câu hỏi tự kiểm tra

1. Tại sao **ScopedValue.newInstance()** không tạo ngay một giá trị cho mọi thread?
2. **ScopedValue.where(KEY, value)** khác **KEY.get()** ở điểm nào?
3. Nối ba lần **where** trước một **run** có tác dụng gì?
4. **Carrier.where** với key đã có mapping có thay đổi Carrier cũ không?
5. **Nested run** ghi đè TENANT thì REQUEST_ID của outer có mất không?
6. Khi nested run ném exception, binding outer và exception thay đổi như thế nào?
7. **isBound()==true** có đồng nghĩa **get()!=null** không?
8. Khi nào dùng **call** thay cho **run**?
9. Vì sao ScopedValue không tự thay thế MDC, HTTP propagation hoặc mọi ExecutorService task?
10. Vì sao **private static final key** có lợi về bảo mật nhưng chưa thay được xác thực/ủy quyền?
11. Vì sao nhóm có thể ưu tiên một ScopedValue chứa immutable record thay vì hàng chục key?
12. Trong Java 25, cần **--enable-preview** để dùng ScopedValue không? Còn StructuredTaskScope thì sao?

## 16. Công cụ, biên dịch và nguồn tham khảo

**Yêu cầu chạy ví dụ:** JDK **25** (compiler và runtime). Các class có **public** phải được lưu trong tệp trùng tên class, ví dụ **MultipleKeysDemo.java** hoặc **ScopedValueBindingsTest.java**. Ví dụ Java trong bài độc lập theo từng file; không dán nhiều **public class** vào một file.

~~~bash
java --version
javac --version
javac --release 25 MultipleKeysDemo.java
java MultipleKeysDemo
~~~

Không truyền **--enable-preview** cho các ví dụ ScopedValue chính thức trong bài. Nếu compiler cảnh báo preview, kiểm tra lại JDK thực, compiler release và việc copy API từ hướng dẫn Java 21–24 trước khi thêm cờ.

**Nguồn chính thức:**

- [JEP 506 — Scoped Values (final trong Java 25)](https://openjdk.org/jeps/506).
- [ScopedValue — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html).
- [ScopedValue.Carrier — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).
- [Java SE 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): chỉ để hiểu ngoại lệ kế thừa trong structured subtasks; API này **vẫn là preview trong Java 25** và không được dùng trong các ví dụ cơ bản.

**Ghi chú tính hiện hành:** Java 25 đã đưa ScopedValue thành API chính thức. Một số ví dụ cũ trên mạng dùng dạng preview hoặc mô tả Structured Concurrency như API đã ổn định; khi học và áp dụng, cần đối chiếu chính xác tài liệu **Java SE 25** thay vì sao chép nguyên hướng dẫn từ preview trước đây. Không cần di chuyển mọi ThreadLocal đang hoạt động tốt; nên chọn ScopedValue khi thực sự có ngữ cảnh read-mostly, lifetime có cấu trúc và cần nested rebinding.

**Kết quả cần nộp:** một chương trình ràng buộc nhiều khóa, một chương trình nested rebinding thể hiện sự khôi phục, test Carrier bất biến, test exception/null/unbound, ví dụ request context và một checklist ranh giới thread. Các kết quả này chứng minh bạn kiểm soát được binding theo phạm vi động trong Java 25, thay vì biến ScopedValue thành một kho trạng thái toàn cục mới.
