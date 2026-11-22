# Kết hợp marker tường minh với giới hạn phạm vi

## 1. Vì sao chỉ dùng marker hoặc chỉ dùng phạm vi thường chưa đủ?

Trong **Aspect-Oriented Programming (AOP)**, một **pointcut** xác định tập **join point** mà advice có thể can thiệp. Với những cơ chế AOP cho phép chọn điểm dựa trên annotation/metadata, ta có thể đánh dấu trực tiếp một method hoặc type bằng một **marker** để nói rằng chúng thuộc một concern. Đồng thời, ta có thể giới hạn phạm vi chọn theo module, package, type role, API boundary, component hoặc ngữ cảnh thực thi.

Hai chiều này giải quyết **hai câu hỏi khác nhau**:

- **Marker tường minh:** “Điểm này được người sở hữu code tuyên bố thuộc concern nào?” Ví dụ `@ObservedOperation` biểu thị một operation cần metrics/tracing.
- **Giới hạn phạm vi (scope restriction):** “Aspect này được phép hoặc được thiết kế hoạt động ở khu vực nào của chương trình?” Ví dụ chỉ trong một module công khai, các API thuộc role giao dịch, hoặc các objects thuộc trust boundary xác định.

Nếu chỉ chọn theo marker, một method debug hoặc helper nội bộ vô tình gắn annotation giống method nghiệp vụ có thể bị advice xử lý, khiến logging quá nhiều, rò dữ liệu hoặc retry sai. Nếu chỉ chọn theo package/role, aspect có thể chạm tới mọi method trong vùng, kể cả health check, getter, helper, hoặc lệnh có semantics hoàn toàn khác. **Kết hợp cả hai** cho phép biểu diễn chính sách rõ hơn.

> **Quy tắc tư duy:** `SELECT = MARKED && IN_SCOPE && SUPPORTED_JOIN_POINT && NOT_EXCLUDED`. Mỗi điều kiện là một phần của hợp đồng selection, không phải một lời đảm bảo rằng method chắc chắn đã được intercept hoặc policy nghiệp vụ đã đúng.

Ví dụ về tập được chọn:

| Join point | Có `@ObservedOperation`? | Thuộc scope công bố? | Có được chọn? |
| --- | --- | --- | --- |
| `BillingApi.charge()` | Có | Có | **Có**, nếu join point được công cụ hỗ trợ. |
| `BillingApi.health()` | Không | Có | Không. |
| `InternalMaintenance.cleanup()` | Có | Không | Không. |
| `OtherService.ping()` | Không | Không | Không. |

### Sau bài học bạn có thể

1. Phân biệt marker annotation, type-level scope, package/module scope, call/execution join point và runtime contextual filter.
2. Viết mô hình logic cho các điều kiện **AND / OR / NOT** mà không mắc lỗi precedence.
3. Hiểu `@Retention`, `@Target`, vị trí annotation trong interface/class và giới hạn `@Inherited`.
4. Thiết kế explicit positive selection đi kèm giới hạn domain/module, tránh overmatching từ wildcard.
5. Tránh bỏ sót do selector thiếu metadata, do proxy bypass hoặc do scope di chuyển theo refactor.
6. Phân tích trade-off: interface role vs package; declaration scope vs runtime scope; annotation trên API vs implementation.
7. Bảo vệ security, retry, caching và audit trước những thay đổi ngoài ý muốn của matched set.
8. Chạy ví dụ Java 17 dùng JDK dynamic proxy, với ba trường hợp **đủ cả hai điều kiện / chỉ scope / chỉ marker**.
9. Lập positive/negative coverage tests, test error paths, nested flows và async để chứng minh sự đúng đắn.
10. Có checklist để review việc thêm, xóa, đổi marker hoặc di chuyển một class sang scope khác.

**Phạm vi bài:** Những nguyên lý Aspect/AOP cơ bản và nâng cao nói chung. Cú pháp pointcut, annotation lookup và giới hạn join-point kinds phụ thuộc công cụ; các sơ đồ matcher dưới đây là **giả mã khái niệm** trừ khi được ghi là Java 17 chạy được.

## 2. Mô hình toán học cho selection: giao giữa hai tập

Gọi:
- \(J\): tập join points mà công cụ AOP có thể thấy.
- \(M\): tập join points có marker theo **metadata lookup rule** đã chọn.
- \(S\): tập join points trong phạm vi được phép.
- \(E\): tập join points cần loại trừ tường minh.
- \(C\): tập join points có thể thực sự được can thiệp trên những đường gọi hiện có.

Tập dự kiến:

\[
P = J \cap M \cap S \setminus E
\]

Tập **thực tế advice nhận** còn phụ thuộc cơ chế interception:

\[
A = P \cap C
\]

Với một proxy, `C` thường bao gồm các invocations đi **qua đúng proxy**, không tự gồm direct target calls và self-invocation. Với một cơ chế weaving, `C` lại chịu phạm vi class/join-point weaving và runtime artifact.

Điều kiện `MARKED && IN_SCOPE` vẫn chỉ là **mô hình selection**; nó không tự bảo đảm mọi caller đều qua aspect.

### 2.1. Marker là positive intent

Marker có thể là annotation đặt trên method/type, một named role đã được công bố, hay metadata được quản trị. Trong ví dụ Java, marker là annotation thật để minh họa tính tường minh:
 
~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ObservedOperation { }
~~~

Đây là **đoạn minh họa**; cần imports và enclosing context để biên dịch. Khi compiler thấy marker trên declaration, người đọc source có thể hiểu rằng operation này được chọn cho observability theo convention của dự án.

### 2.2. Scope là một ranh giới độc lập

Scope không nên được hiểu mơ hồ là “mọi thứ có cùng marker”. Nó có thể là:
- Một API/interface role ổn định.
- Một module đã được xác nhận theo ownership.
- Một package boundary thực sự được enforce.
- Một set của các target types.
- Một tập join-point kinds có ý nghĩa (execution thay vì call).
- Một dynamic control flow được hỗ trợ bởi engine.
- Một policy chỉ được phép áp ở một nơi tin cậy.

Một type có marker vẫn có thể **ngoài scope**. Ngược lại, một method trong scope vẫn bị loại nếu không đánh dấu.

### 2.3. Exclusion không nên thay cho positive boundary

Có thể định nghĩa một danh sách rất dài `NOT helper && NOT logger && NOT health && ...`. Nhưng nếu positive selector là “mọi method trong application”, một component mới có thể vô tình bị chọn trước khi được xem xét. Dùng **positive intent + scope đủ hẹp**, rồi thêm exclusions cho những ngoại lệ đã được xác định.

## 3. Những đơn vị phạm vi thường dùng

| Phạm vi | Ví dụ | Ưu điểm | Cẩn trọng |
| --- | --- | --- | --- |
| **API interface** | `BillingApi`. | Compile-time role rõ, đổi implementation không nhất thiết đổi scope. | Proxy/execution matching và inherited metadata phải kiểm tra. |
| **Type annotation** | `@BusinessBoundary` trên interface/class. | Chủ đích explicit; di chuyển package ít ảnh hưởng. | Annotation cũng cần governance. |
| **Module** | Chỉ thuộc module nghiệp vụ được công bố. | Phù hợp ownership/deployment. | Module graph, classloading, exports/opens. |
| **Package** | `com.example.billing.api`. | Dễ diễn đạt khi package thật là architecture boundary. | Rename/move và overmatching. |
| **Subtype relationship** | Implement một role interface. | Tập trung vào capability. | Có thể quá rộng nếu interface đa mục đích. |
| **Join-point kind** | Chỉ method execution. | Ngăn nhầm call với execution hoặc field access. | Engine support khác nhau. |
| **Dynamic context** | Bên trong logical `checkout()` flow. | Gắn với operation đang diễn ra. | Async, nesting, ThreadLocal/context propagation. |
| **Tenant/request policy** | Tenant được xác thực ở trusted entrypoint. | Context-aware. | Không lấy security context từ untrusted marker/headers. |

### 3.1. Type-level scope không đồng nghĩa per-instance aspect scope

Một type được đánh dấu `@BusinessBoundary` nghĩa là selector nhận diện một **loại API**; nó không có nghĩa mỗi object của type tạo ra một aspect instance mới. Việc aspect state là singleton/per-target/per-flow/per-invocation là **instantiation model** độc lập.

### 3.2. Package scope cần bằng chứng kiến trúc

`com.example.billing.*` có thể là chính sách hợp lý nếu package được quản trị như boundary và có architecture tests. Nhưng nếu package chỉ là nơi tiện để lưu file, dùng nó làm security/audit boundary có thể giòn. Khi class bị di chuyển, cần regression test chứng minh matched set không đổi hoặc đổi có chủ đích.

### 3.3. Module scope khác Java package name

Java module system có thể kiểm soát exports/opens, còn package là namespace. Một matcher nhìn package có thể vẫn nhận tên type, nhưng reflection/bytecode weaving có thể chịu module access limitations. **“Khớp tên”** và **“có thể thực thi advice”** là hai điều khác nhau.

## 4. Marker tường minh là một contract, không phải phép màu

Một marker `@ObservedOperation` trả lời “developer **muốn** operation này được đo”. Nó không tự nói:
- Method có an toàn để retry không?
- Có được phép ghi toàn bộ arguments không?
- Authorization đã thực sự diễn ra ở trusted boundary chưa?
- Method là synchronous hay async?
- Một call qua proxy có đi tới method được marked không?
- Annotations có được đặt đúng nơi engine lookup không?
- Log sink fail thì có được làm business call fail không?

### 4.1. Marker nên có một ý nghĩa hẹp

Nếu marker `@Managed` đồng thời bật tracing, cache, retry, masking, transaction và audit, thêm annotation tại một method mới có thể kích hoạt rất nhiều side effects. Hãy ưu tiên một vocabulary riêng cho từng policy:
- `@ObservedOperation`: observation.
- `@AuditedMutation`: event audit theo hợp đồng.
- `@RetryAllowed`: chỉ khi operation được xác nhận idempotent/eligible.
- `@Sensitive`: policy xử lý thông tin cần masking.

Những tên trên là ví dụ thiết kế, không phải API chuẩn AOP. Marker **phải có documentation và tests** cho semantics cụ thể.

### 4.2. Marker có thể là class-level hoặc method-level

- **Class-level:** mọi operations của một type có thể được xem là candidates. Dễ quản trị theo role nhưng có nguy cơ quá rộng.
- **Method-level:** developer chọn từng operation. Granular hơn nhưng có rủi ro quên đánh dấu.
- **Parameter-level:** hữu ích cho masking/binding argument metadata, nhưng không tự có nghĩa cả method được chọn.
- **Type-use annotation:** mô tả kiểu sử dụng tại vị trí hợp lệ, không nhất thiết là một join-point selector.

Nếu muốn cả type và method xác nhận, có thể dùng hai markers: ví dụ `@BusinessBoundary` ở interface, `@ObservedOperation` ở method. Đây chính là mẫu **AND** trong bài.

### 4.3. Marker thiếu có phải fail-closed?

Phụ thuộc concern:
- Metrics optional: thiếu marker có thể chỉ dẫn tới không đo, nhưng phải phát hiện bằng coverage test.
- Audit bắt buộc: thiếu marker có thể là vi phạm hợp đồng nghiêm trọng; cần lint/test hoặc đặt enforcement ở trusted owner.
- Authorization: tuyệt đối không coi sự có mặt của marker là **toàn bộ** trust boundary. Caller có thể đi đường bypass interceptor.

Marker mang **intent**, không thay domain/security invariants.

## 5. Java annotation: Retention, Target, Inherited và metadata lookup

Khi chọn theo **marker AND phạm vi**, không chỉ hỏi “có annotation không?” mà phải định nghĩa rõ **marker nằm ở đâu** và **scope được đánh giá trên type nào**. Nếu hai phép tra cứu dùng hai declaration khác nhau, phép giao `M ∩ S` có thể chọn sai tập join point.

| Quy tắc | Câu hỏi cần quyết định cho phép giao marker/scope |
| --- | --- |
| `RetentionPolicy` | Matcher chạy bằng reflection (`RUNTIME`) hay dùng source/classfile ở bước weaving? |
| `@Target` | Marker đặt trên method, type hay parameter? Scope marker có cùng cấp với operation marker không? |
| `@Inherited` | Có dựa vào superclass type không? **Không** tự thừa kế method/interface annotations. |
| Method lookup | Proxy cung cấp `Method` trên interface hay execution matcher thấy implementation method? |
| Repeatable/meta markers | Consumer có chủ động unpack repeatable annotations và tìm meta-annotations không? |

Ví dụ, nếu `@ObservedOperation` đặt ở **interface method** nhưng matcher chỉ kiểm `implementationMethod.isAnnotationPresent(...)`, giá trị “marker” có thể false dù use case được đánh dấu đúng contract. Cần quy định và test **interface → implementation lookup** theo chiều đã chọn; Java reflection không tự merge một bộ annotation duy nhất của mọi interface, superclass và override. Tương tự, một type-level scope marker đặt trên interface không tự thành annotation trên concrete implementation.

**Thiết kế thực tế:** chốt method đang xét, resolve marker + scope thành hai giá trị Boolean theo cùng một chính sách metadata, sau đó áp `AND` (và exclusions) có kiểm thử. Không đánh đồng annotation hợp lệ với **coverage** của AOP engine; dù điều kiện đúng, lời gọi direct target vẫn có thể bypass một delegation proxy.

## 6. Kết hợp Boolean: AND, OR, NOT cho pointcut

Mô hình:

~~~text
# Giả mã, không phải cú pháp chuẩn của một AOP engine.
select(
    isMethodExecution
    AND hasMarker(ObservedOperation)
    AND inScope(BusinessBoundary)
    AND NOT isInfrastructureMethod
)
~~~

### 6.1. Các trường hợp sử dụng

- **AND:** chỉ chọn method được annotated **và** thuộc approved boundary.
- **OR:** chấp nhận một trong các scopes đã được công bố, ví dụ `BillingApi OR ShippingApi`.
- **NOT:** loại một method/role đặc biệt, ví dụ `healthCheck` hoặc `TelemetryExporter`.
- **Context predicate:** chỉ kích hoạt khi có một flow context hợp lệ, theo khả năng engine.

### 6.2. Dấu ngoặc rất quan trọng

Hai công thức này không tương đương:

~~~text
(MARKED AND BILLING) OR SHIPPING

MARKED AND (BILLING OR SHIPPING)
~~~

Công thức đầu **chọn mọi method trong SHIPPING** dù không marked; công thức thứ hai đòi marker ở cả hai scopes. Một selector bị sai thứ tự `AND/OR` có thể gây **overmatching** nghiêm trọng.

Vì cú pháp và precedence của các pointcut languages khác nhau, hãy dùng grouping tường minh và viết tests cho cả positive/negative cases, không rely vào trí nhớ về precedence.

### 6.3. Overmatching và undermatching đều nguy hiểm

- **Overmatching:** một retry advice áp vào command không idempotent; logging đọc secrets; transaction scope mở sai.
- **Undermatching:** telemetry thiếu, audit bắt buộc không được emit, authorization policy bị bypass nếu đây là nơi duy nhất enforce.
- **Matching sai đơn vị:** metrics tưởng đo một logical operation nhưng thực tế đếm helper attempts; async task success bị ghi khi method return stage.

Định nghĩa **đơn vị quan sát** trước khi hoàn thiện selector.

## 7. Ví dụ Java 17 runnable: method marker AND interface scope

Ví dụ này cho thấy cách tổ hợp hai dấu hiệu selection trên **JDK dynamic proxy**. Nó là ví dụ về **AOP-like interception** trong Java thuần, không mô phỏng mọi kiểu weaving.

Điều kiện để ghi `ADVICE` là:
1. Interface view truyền vào proxy có `@BusinessArea` ở **type level**.
2. Interface method có `@ObservedOperation` ở **method level**.

Chúng ta chuẩn bị ba test cases:
- `BillingApi.charge`: **marker có + scope có**, được quan sát.
- `BillingApi.health`: **marker không + scope có**, không được quan sát.
- `InternalApi.cleanup`: **marker có + scope không**, không được quan sát.

Thêm một lỗi target `charge("BAD")` để kiểm tra marker logic vẫn áp trên failure path và handler truyền lại exception gốc.

Tạo file **`MarkerScopeDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class MarkerScopeDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface BusinessArea { }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface ObservedOperation { }

    @BusinessArea
    public interface BillingApi {
        @ObservedOperation
        String charge(String id);

        String health();
    }

    public interface InternalApi {
        @ObservedOperation
        String cleanup(String id);
    }

    static final class BillingTarget implements BillingApi {
        @Override
        public String charge(String id) {
            System.out.println("TARGET charge " + id);
            if ("BAD".equals(id)) {
                throw new IllegalArgumentException("bad id");
            }
            return "PAID:" + id;
        }

        @Override
        public String health() {
            System.out.println("TARGET health");
            return "UP";
        }
    }

    static final class InternalTarget implements InternalApi {
        @Override
        public String cleanup(String id) {
            System.out.println("TARGET cleanup " + id);
            return "CLEAN:" + id;
        }
    }

    static <T> T observed(
            Class<T> view,
            T target,
            AtomicInteger selectedCount) {
        if (!view.isInterface() || !view.isInstance(target)) {
            throw new IllegalArgumentException("invalid interface view");
        }

        boolean inScope = view.isAnnotationPresent(BusinessArea.class);

        Object proxy = Proxy.newProxyInstance(
                view.getClassLoader(),
                new Class<?>[] { view },
                (proxyObject, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "equals" -> proxyObject == arguments[0];
                            case "hashCode" ->
                                    System.identityHashCode(proxyObject);
                            case "toString" -> "MarkerScopeProxy";
                            default -> throw new UnsupportedOperationException(
                                    method.getName());
                        };
                    }

                    boolean selected = inScope
                            && method.isAnnotationPresent(
                                    ObservedOperation.class);

                    if (selected) {
                        selectedCount.incrementAndGet();
                        System.out.println(
                                "ADVICE before " + method.getName());
                    }

                    try {
                        Object result = method.invoke(target, arguments);
                        if (selected) {
                            System.out.println(
                                    "ADVICE after " + method.getName());
                        }
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable cause = wrapped.getCause();
                        if (selected) {
                            System.out.println(
                                    "ADVICE error " + method.getName()
                                    + " "
                                    + cause.getClass().getSimpleName());
                        }
                        throw cause;
                    }
                }
        );

        return view.cast(proxy);
    }

    public static void main(String[] args) {
        AtomicInteger matches = new AtomicInteger();
        BillingApi billing =
                observed(BillingApi.class, new BillingTarget(), matches);
        InternalApi internal =
                observed(InternalApi.class, new InternalTarget(), matches);

        System.out.println("CHARGE=" + billing.charge("A"));
        System.out.println("HEALTH=" + billing.health());
        System.out.println("INTERNAL=" + internal.cleanup("X"));

        try {
            billing.charge("BAD");
        } catch (IllegalArgumentException failure) {
            System.out.println("ERROR=" + failure.getMessage());
        }

        System.out.println("SELECTED=" + matches.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac MarkerScopeDemo.java
java MarkerScopeDemo
~~~

**Stdout kỳ vọng, đúng thứ tự:**

~~~text
ADVICE before charge
TARGET charge A
ADVICE after charge
CHARGE=PAID:A
TARGET health
HEALTH=UP
TARGET cleanup X
INTERNAL=CLEAN:X
ADVICE before charge
TARGET charge BAD
ADVICE error charge IllegalArgumentException
ERROR=bad id
SELECTED=2
~~~

### 7.1. Vì sao `charge("A")` được chọn?

`observed(BillingApi.class,...)` xác nhận `BillingApi` có `@BusinessArea` nên `inScope=true`. Khi client gọi `billing.charge("A")`, JDK proxy handler nhận interface `Method` có `@ObservedOperation`, nên `selected=true`. Handler tăng `matches`, in dòng before, gọi target, rồi in after. Caller nhận đúng `PAID:A`.

Không có điều kiện nào dựa vào tên package/concrete class `BillingTarget`; đối tượng mới implement `BillingApi` có thể đi qua cùng policy của factory nếu giữ hợp đồng interface ấy.

### 7.2. Vì sao `health()` bị loại dù cùng scope?

`BillingApi` ở trong scope, nhưng method `health` **không có marker**. `inScope && marked` là false. Proxy vẫn **delegate bình thường** tới target, in `TARGET health`, nhưng không có dòng advice. Đây là negative case chứng minh **scope đơn lẻ không đủ**.

### 7.3. Vì sao `cleanup()` bị loại dù có marker?

`InternalApi.cleanup` có marker, nhưng `InternalApi` **không** có `@BusinessArea`. Vì thế `inScope=false`; dù method được annotated, `selected=false`. Target vẫn chạy, nhưng không có instrumentation. Đây là negative case chứng minh **marker đơn lẻ không đủ**.

### 7.4. Vì sao `SELECTED=2`?

Có hai invocations được chọn: `billing.charge("A")` và `billing.charge("BAD")`. `health()` và `internal.cleanup()` không được chọn. Bộ đếm tăng **trước** khi gọi target, nên nó phản ánh **attempted selected calls**, không phải số lần thành công.

Muốn phân biệt success và failure, dùng counters riêng trong đường return/throw, đặt policy đo rõ theo business logic.

### 7.5. Lỗi từ target có còn nguyên loại không?

Khi target ném `IllegalArgumentException("bad id")`, reflective `Method.invoke` bọc exception trong `InvocationTargetException`. Handler lấy cause, in log failure rồi `throw cause`, nên caller bắt được `IllegalArgumentException`. Điều kiện selection không thay hợp đồng lỗi của target.

### 7.6. Code này giới hạn được điều gì?

Nó giới hạn **instrumentation ở interface proxy boundary**, không thay class `BillingTarget` hay `InternalTarget`. Nếu caller giữ target và gọi trực tiếp, handler không chạy. Nếu target tự gọi `this.charge(...)`, invocation ấy cũng không bắt buộc đi qua proxy. Nó không dùng bytecode weaving hay pointcut DSL của một AOP engine.

### 7.7. Những giả định quan trọng của demo

- Chỉ có một interface trong mỗi proxy, nên method-resolution không có ambiguity do duplicated methods từ nhiều interfaces.
- Annotation lookup cố ý chỉ đọc **declaration trên interface** được pass vào `observed`, không merge implementation annotations.
- `BillingApi` và `InternalApi` là public nested interfaces, `@BusinessArea` và `@ObservedOperation` có runtime retention.
- `Object.equals/hashCode/toString` được xử lý theo **identity của proxy**; đó là một policy ví dụ, không đồng nghĩa target/proxy có cùng identity.
- `selectedCount` dùng `AtomicInteger`, phù hợp aggregate count nếu nhiều threads gọi proxy. Target tự nó vẫn có thể không thread-safe trong tình huống khác.
- `method.invoke` còn có thể ném một số lỗi khác ngoài `InvocationTargetException`, ví dụ lỗi access/argument setup; code tập trung vào exceptions từ business target.
- Code không tự enforce authorization, audit persistence, retries, transactions hoặc async completion.
- Một marker type không tự trở thành một aspect instance scope; `inScope` là Boolean captured trong factory per view, không phải task context.
- Không chứng minh mọi engine có cùng annotation inheritance hoặc pointcut syntax.

## 8. Thiết kế ranh giới theo interface vs theo package

Ở ví dụ, scope là marker trên `BillingApi`. Một dự án khác có thể giới hạn theo package hoặc module đã được kiến trúc hóa:

~~~text
# Giả mã
hasMethodMarker(ObservedOperation)
AND declaredInModule("billing-api")
AND isSupportedMethodExecution()
~~~

Nếu concern áp vào nhiều modules, có thể dùng:

~~~text
hasMethodMarker(ObservedOperation)
AND (
    implementsRole(BillingOperation)
    OR implementsRole(ShippingOperation)
)
AND NOT isTelemetryInfrastructure()
~~~

### 8.1. Khi package-based scope hợp lý

Nếu `com.acme.billing.api` là namespace được review như public boundary, có architecture tests ngăn implementation code lọt vào, scope theo package có thể có ý nghĩa bền vững. Nhưng cần:
- Quy tắc package ownership rõ.
- Test rename/move.
- Kiểm include/exclude trên subpackages.
- Không coi package matching là authorization boundary.
- Lưu ý class/module loader khi runtime introspection.

### 8.2. Khi interface-based scope hợp lý

Nếu nhiều concrete implementations thay đổi thường xuyên nhưng cùng một `BillingApi`, type role được compiler kiểm có thể ổn định hơn tên implementation package. Mark `BillingApi` thay vì từng concrete class giúp tách semantic intent khỏi công cụ xây dựng implementation.

### 8.3. Khi type marker trên implementation phù hợp

Nếu concern chỉ áp vào một số implementation dù chúng cùng interface, marker trên **implementation class** có thể phù hợp. Nhưng selection rule phải tra class của target một cách tường minh; nếu handler chỉ xét `view.isAnnotationPresent`, annotation trên implementation không được tự nhìn thấy.

Không có “annotation ở mọi nơi đều tự merge”; cần chọn **source of truth**.

### 8.4. Không suy equality của các scopes

Một object có thể implements `BillingApi` nhưng được dùng bên ngoài workflow billing. Type scope dựa interface sẽ vẫn chọn nó trong mọi proxy call tương ứng. Nếu policy thực sự phụ thuộc **dynamic context**, thêm một điều kiện context có vòng đời rõ, không hi vọng type annotation tự phản ánh caller đang chạy trong flow nào.

## 9. Phân biệt static scope và runtime context scope

**Static scope** thường là điều kiện về khai báo/type/module/package, có thể được quyết định khi build/load hoặc proxy creation. **Dynamic scope** dựa vào execution context như active business flow, principal đã xác thực hoặc trạng thái runtime.

Ví dụ:

~~~text
# Giả mã
methodMarked(ObservedOperation)
AND inOwnedBillingModule()
AND inControlFlow(CheckoutOperation)
~~~

Ở đây:
1. Marker biểu thị một operation có thể được quan sát.
2. Module/type scope chặn những code không thuộc billing.
3. Dynamic flow predicate cho phép chỉ những lần gọi nằm trong checkout scope.

### 9.1. Dynamic scope có thể vượt thread boundaries?

Một synchronous control-flow scope dựa call stack không nhất thiết tự sống qua `CompletableFuture` và executor. Nếu một logical request tiếp tục ở thread khác, phải có explicit context propagation hoặc tính năng của engine được thiết kế cho async.

### 9.2. ThreadLocal không đồng nghĩa logical request

Nếu dùng `ThreadLocal` lưu current flow, cần restore/remove bằng `try/finally`; thread pool có thể reuse thread cho request khác. Với nested contexts, chỉ `remove()` ở inner scope có thể làm mất outer context; dùng stack hoặc lưu previous value. Với async tasks, capture immutable snapshot và restore ở worker.

### 9.3. Dynamic runtime predicate có race không?

Nếu policy phụ thuộc mutable shared state như `currentTenant` trong singleton aspect, hai requests có thể ghi đè. Dữ liệu từng invocation phải đúng scope; bảo mật/authorization cần trusted source. Đừng đưa input chưa xác thực vào context rồi coi nó là bằng chứng quyền.

### 9.4. Đo đúng thời điểm

Một around advice chọn method `submitAsync` có thể return `CompletionStage` ngay. Điều kiện match quyết định một **method invocation**, không tự nghĩa completion của stage đã thành công. Nếu concern cần đo task outcome, phải hook completion theo hợp đồng và xử lý cancellation/error/ownership phù hợp.

## 10. Join-point kind: cần giới hạn cả loại điểm được can thiệp

Marker và scope không đủ nếu chúng chọn sai **loại join point**.

Một số mô hình AOP phân biệt:
- **Call:** điểm mã gọi method.
- **Execution:** điểm method body thực hiện.
- **Constructor/initialization:** theo khả năng engine.
- **Field get/set:** theo khả năng engine.
- **Handler/exception-related:** theo khả năng engine.

Nếu marker ở method, nó được dùng để chọn **call** hay **execution**? Một engine có thể nhìn interface method tại proxy call; một weaver có thể nhìn implementation execution; một reflection-based interception có metadata khác.

### 10.1. Bao gồm root hay descendants?

Nếu marker chỉ ở root `checkout()`, chọn call/execution của root khác chọn mọi methods trong dynamic flow bên dưới root. Điều kiện `within checkout cflow` cần support riêng, không phải annotation `@ObservedOperation` tự làm mọi descendants mang marker.

### 10.2. Không match ngoài supported set

Nếu một selector trông đúng nhưng engine không intercept `private`, `static`, `final`, constructors hoặc direct field reads theo mô hình hiện tại, advice không thể tự chạy ở đó. Thay đổi marker không biến một join point không được hỗ trợ thành được hỗ trợ.

### 10.3. Proxy và weaving có khả năng khác

JDK interface proxy chỉ xử lý method invocations thông qua proxy interface; source/bytecode weaving có thể thấy những join-point kinds khác tùy engine. Phải dựa vào artifact cuối và documentation của công cụ, không suy từ một demo proxy cho mọi weaving strategy.

## 11. Tránh scope quá rộng: quan sát thôi cũng có chi phí

Một marker trên method nội bộ có thể được copy-paste lên mọi helpers. Nếu scope được khai là cả module, advice có thể được chạy dày đặc:
- Metrics tăng cardinality.
- Logger ghi trùng event hoặc lộ dữ liệu đầu vào.
- Stack traces thêm nhiều frames.
- Trace span tree trở nên nhiễu.
- System I/O và allocation tăng.
- Bất cứ instrumentation error nào có thể ảnh hưởng target nếu không được cô lập.

### 11.1. Positive selection cần theo đơn vị đo

Nếu muốn đếm **logical business operations**, marker nên ở public use-case boundary. Nếu muốn đếm **storage attempts**, marker nên ở attempt boundary. Đừng đặt cả hai cùng một event name mà không phân biệt.

### 11.2. Negative exclusions nên là hợp đồng

Ví dụ một module telemetry có method `exportMetrics()` có marker do dùng chung helper annotations, nhưng aspect logging `exportMetrics()` lại gọi chính exporter có thể recursion. Exclude module/type infrastructure một cách tường minh, hoặc đặt marker semantics đủ hẹp để instrumentation methods không là candidates.

### 11.3. Exclusion theo tên helper có thể giòn

`NOT *Helper` dựa naming convention có thể bỏ nhầm một business operation. Tốt hơn là có interface/tag `InstrumentationInfrastructure` hoặc thuộc tính module ownership được công bố. Nếu vẫn dùng tên/package, quản trị refactor và có negative tests.

## 12. Marker không thay được authorization/security invariant

Một điểm đặc biệt quan trọng: **annotation chỉ là metadata**, không phải chứng chỉ quyền.

Giả sử `@ProtectedOperation` đánh dấu method cần quyền. Nếu implementation có một đường gọi trực tiếp bypass proxy, rule `marker && scope` không bao phủ đường đó. Nếu một developer quên marker, policy có thể không chạy. Nếu dữ liệu tenant nằm trong request header không xác thực, marker không biến giá trị ấy thành trusted principal.

### 12.1. Thiết kế fail-safe boundary

- Đặt security invariant tại trusted entrypoint/domain boundary phù hợp.
- Quản trị tập protected operations bằng static analysis/contract tests.
- Khi một operation mới được thêm, phải xác nhận authorization policy.
- Verify direct-target/internal calls không làm bypass invariant.
- Nếu advice có thể short-circuit, kiểm ordering với cache/fallback.
- Không coi package name hay `@ProtectedOperation` đơn lẻ là proof of authorization.

### 12.2. Scope không đồng nghĩa tenant isolation

Một type `BillingApi` có thể phục vụ nhiều tenants. Type-level scope không biết mỗi caller thuộc tenant nào. Tenant/principal context phải được xác thực và propagate đúng, không lưu vào shared singleton field rồi áp cho mọi invocations.

### 12.3. Audit bắt buộc khác debug logging

Nếu audit là regulatory/business contract phải bền vững, chỉ “advice ghi log khi marker match” chưa đủ. Cần xác định event ghi ở **trước hay sau commit**, durability, error handling, idempotency và outbox/transaction boundary. Pointcut chỉ giúp chọn điểm can thiệp; nó không tự định nghĩa độ tin cậy của event.

## 13. Khi nhiều aspects dùng chung marker và scope

Giả sử `@ObservedOperation` được Trace và Metrics cùng đọc. Đây thường là reuse hợp lý. Nhưng nếu thêm Retry, Cache, Audit và Authorization vào cùng matcher, side effects có thể đổi mạnh.

Một chuỗi advice:

~~~text
Auth(
  Trace(
    Metrics(
      Retry(
        Target
      )
    )
  )
)
~~~

chỉ là sơ đồ minh họa: thứ tự thực do công cụ/hợp đồng quyết định. Với một marker `@Observed` cho mọi tầng, việc thêm một annotation có thể vô tình bật retry cho operation không idempotent.

### 13.1. Tách vocabulary quan sát với biến đổi

- Observer: tracing/metrics/logging; lý tưởng bảo toàn result/error.
- Transformer: cache/fallback/argument normalization; thay outcomes theo policy.
- Executor-control: retry/timeout; có thể tăng số attempts hoặc đổi timing.
- Enforcer: authorization/validation; có thể reject inputs.

Các loại này không nên dùng một marker “bật tất cả” mà thiếu phân biệt eligibility.

### 13.2. Ordering và short-circuit

Với `Auth(Cache(Target))`, authorization có thể chạy trước cache. Với `Cache(Auth(Target))`, một cache hit có thể skip inner authorization. Do đó `MARKED && IN_SCOPE` không đảm bảo **thứ tự** hoặc **độ phủ khi advice short-circuit**.

### 13.3. Return/throw contracts

Một logging advice ở marker/scope đúng nhưng tự throw `IOException` từ log sink hoặc swallow target exception vẫn vi phạm hợp đồng quan sát. Scope đúng chỉ giải quyết **chọn đâu**, không giải quyết **làm gì**.

### 13.4. Logical vs attempt metrics

`Metrics(Retry(Target))` có thể đếm một logical call; `Retry(Metrics(Target))` có thể đếm mỗi attempt. Trong bài demo, `SELECTED=2` là số lần **intercepted marked-in-scope invocations** bao gồm một lỗi, không phải số success.

## 14. Refactor và evolution của annotations/scopes

Giới hạn phạm vi có thể được định nghĩa bằng interface hoặc annotation thay vì tên package, nhưng **contract vẫn tiến hóa**.

### 14.1. Khi đổi tên/move implementation

Nếu scope được neo vào `BillingApi`, một implementation mới vẫn được chọn khi caller dùng đúng interface proxy. Đây là ưu điểm của semantic boundary. Nhưng một implementation method mới không nằm trong interface sẽ không tự được proxy expose.

### 14.2. Khi chuyển marker

Chuyển `@ObservedOperation` từ interface method sang implementation method có thể làm selector cũ mất match. Một migration cần thay metadata-resolution policy hoặc giữ annotation tương thích trong quá trình chuyển.

### 14.3. Khi đổi interface scope

Bỏ `@BusinessArea` khỏi `BillingApi` khiến mọi method marker trong interface này không còn được chọn ở ví dụ. Đây là thay đổi hành vi của instrumentation, không phải một refactor thuần type name.

### 14.4. Khi thêm implementation mới

Một contract test nên tạo implementation thứ hai cùng interface view, xác nhận các method marker vẫn được quan sát. Đổi package/name của implementation không nên vô tình làm mất matched set nếu scope không dựa tên class.

### 14.5. Khi thêm overload

Nếu thêm `charge(ChargeRequest)` mà quên marker, nó không được chọn, dù cùng tên. Điều này có thể đúng hoặc sai tùy contract. Nếu thay pointcut bằng name wildcard để “tự bắt mọi overload”, rủi ro overmatching tăng. Hãy đặt marker trên đúng declaration và test.

### 14.6. Với generic erasure, bridge/synthetic methods

Generics/covariant overrides có thể tạo bridge methods khi biên dịch. Một runtime matcher trên implementation `getDeclaredMethods()` có thể thấy synthetic/bridge methods; một weaver có thể match chúng theo quy tắc khác. Không mặc định một source method tương ứng một join point trong mọi toolchain. Test với generic interface implementations nếu metrics phải không trùng lặp.

## 15. Cấu trúc pointcut tái sử dụng được

Một thiết kế bền vững thường tách **vocabulary** khỏi **implementation pattern**.

### 15.1. Định nghĩa terms

Ví dụ:
- `BusinessBoundary`: API boundary do domain team công bố.
- `ObservedOperation`: operation cần đo.
- `ApprovedModule`: module được công cụ cho phép instrument.
- `InfrastructureExclusion`: telemetry exporter, framework helper và setup paths cần loại.

### 15.2. Biểu diễn thành selector chung

~~~text
# Giả mã
NamedPointcut ObservedBusinessOperation =
    hasMethodMarker(ObservedOperation)
    AND hasTypeRole(BusinessBoundary)
    AND withinApprovedModule()
    AND isSupportedMethodJoinPoint()
    AND NOT isInstrumentationInfrastructure()
~~~

Nhiều advices quan sát có thể reuse named selector, nhưng vẫn phải có **policy riêng** cho logging fields, sampling, counters và lifecycle.

### 15.3. Một named pointcut không chữa được predicate sai

Nếu `withinApprovedModule` hiện thực bằng wildcard `*.impl.*` sai về mặt kiến trúc, đưa nó vào named pointcut chỉ tập trung hóa sự giòn. Dùng architecture tests và owner review để đảm bảo phần “scope” diễn đạt đúng nghĩa.

### 15.4. Quyền sở hữu

Đội domain xác định operation nào là boundary; đội observability có thể quản lý marker semantics; đội platform quản lý engine/toolchain; đội security quản lý trusted authorization. Những owners cần thống nhất **thay đổi marker và scope sẽ tác động tới hệ nào**.

## 16. Thứ tự ưu tiên khi áp dụng giới hạn phạm vi

Một procedure có thể dùng khi review:

1. **Xác định concern:** chọn metrics, audit, retry hay security?
2. **Xác định logical unit:** request, operation, attempt, internal call, async completion?
3. **Chọn marker:** method/type annotation hay explicit role?
4. **Chọn phạm vi:** stable interface, module, package được enforce hoặc dynamic scope.
5. **Chọn join-point kind:** call/execution/other, theo engine hỗ trợ.
6. **Chọn exclusions:** helpers, health, telemetry sinks, nested/recursive calls.
7. **Định nghĩa lookup:** interface method vs implementation, annotation inheritance.
8. **Định nghĩa lifecycle:** advice scope, task scope, context cleanup.
9. **Định nghĩa order:** cache/retry/auth/metric nesting.
10. **Định nghĩa failure policy:** target error transparency, instrumentation failures.
11. **Test positive & negative coverage** trên artifact thực.
12. **Quan sát drift** khi refactor/upgrade.

Đừng đảo thứ tự: bắt đầu bằng một wildcard “match hết” rồi mới suy ra nó đại diện business contract nào thường dẫn đến scope không rõ.

## 17. Ma trận test bắt buộc cho marker kết hợp scope

| Test case | Marker | Scope | Kỳ vọng |
| --- | --- | --- | --- |
| Business operation chuẩn | Có | Có | Được chọn; advice chạy qua đường intercept đúng. |
| Health check trong business interface | Không | Có | Không chọn. |
| Internal helper có annotation | Có | Không | Không chọn. |
| External class không annotation | Không | Không | Không chọn. |
| Thêm implementation cùng interface | Có trên interface method | Có trên interface | Giữ selection khi qua đúng proxy/view. |
| Annotation chỉ nằm trên implementation | Có ở implementation | Tùy | Theo metadata lookup rule đã công bố. |
| Rename package implementation | Không thay marker | Không thay scope semantic | Không đổi intended matches. |
| Chuyển type sang module khác | Có | Thay đổi | Được review, không silently overmatch. |
| Thêm overload chưa marked | Không ở overload | Có | Không chọn trừ policy khác. |
| Generic bridge method | Tùy metadata | Có | Không double count ngoài contract. |
| Direct target call | Có metadata | Có | Xác minh có/không intercept theo mechanism. |
| Self-invocation | Có metadata | Có | Không giả định handler thấy nếu không qua proxy. |
| Around advice skip | Có | Có | Scope/side effects và inner policy đúng. |
| Target throw | Có | Có | Lỗi không bị nuốt; cleanup đúng. |
| Async future fail | Có | Có | Phân biệt method-return và task-completion. |
| Retry nhiều attempts | Có | Có | Metric đo đúng đơn vị attempt/logical call. |
| Nested flow | Có | Có, theo flow | Không trộn context của parent/child. |
| Reused worker thread | Có | Theo task | Context cũ không rò sang request mới. |
| Multiple aspects | Có | Có | Ordering/side effects đúng. |
| Untrusted caller giả marker-like data | Không liên quan Java declaration | Tùy | Không trở thành authorization. |

### 17.1. Positive tests không đủ

Nếu chỉ assert `billing.charge("A")` có log, matcher `selected = inScope || marked` cũng có thể pass positive test. Phải assert cả hai negative cases:
- Có scope nhưng không marker.
- Có marker nhưng không scope.

Điều này phát hiện lỗi **OR thay vì AND** rất hiệu quả.

### 17.2. Error path là một phần của selection contract

Method lỗi vẫn là một selected invocation nếu marker/scope đúng. Nếu counter định nghĩa “attempts”, nó vẫn phải đếm failure. Nếu counter định nghĩa “success”, chỉ đếm bình thường sau target completion. Không nhập nhằng hai semantics.

### 17.3. Test metadata đúng nơi

Dùng reflection/JDK proxy để xác minh interface method annotation khi đó là rule. Nếu engine match implementation method, cần fixture annotation chỉ trên interface, chỉ trên target và trên cả hai để so.

### 17.4. Test scope thực thi

Một selector Boolean tính true không tự chứng minh advice chạy. Integration tests phải gọi qua proxy hoặc woven artifact thực. Nếu security policy bắt buộc, assert cả đường direct target/internals theo trust boundary.

### 17.5. Test tương tác advice chain

Thử một cache hit skip inner advice, một retry ném rồi thành công và một observer throws. Xác minh policy quan trọng không bị bỏ qua, side effects không bị lặp ngoài ý định, exceptions được bảo toàn.

## 18. Performance và chi phí metadata selection

### 18.1. Không thể kết luận annotation matcher luôn chậm

Một số engines resolve pointcut ở compile/load time; một proxy interceptor khác đọc `Method.isAnnotationPresent` tại mỗi invocation; một implementation có thể cache method metadata. Overhead phụ thuộc engine, runtime, số join points, advice body, contention và allocation.

### 18.2. Càng narrow scope, càng giảm noise

Một positive interface scope giới hạn candidates trước khi gọi advice. Điều này có thể giảm log/metric event volume, recursion và cardinality. Nhưng chỉ tối ưu khi **đúng contract**; không cắt bớt operations bắt buộc để làm biểu đồ nhẹ hơn.

### 18.3. Cache annotation metadata khi cần

Nếu custom interceptor đọc annotation nhiều lần, có thể cache `Method -> Descriptor` hoặc thông tin theo interface view. Nhưng lưu `Method/Class` keys trong global strong-reference cache có thể giữ classloaders lâu hơn khi plugin unload. Cần owner/eviction và tránh cache key quá rộng.

### 18.4. Lỗi chính thường ở advice body, không ở predicate

Một advice ghi JSON của toàn bộ payload có thể đắt hơn một annotation lookup. `@ObservedOperation` không nên mặc định nghĩa “log toàn bộ parameters/results”. Áp allowlist fields, sampling, bounded queue và dữ liệu được sanitize.

### 18.5. Metric đo đúng đơn vị

Một method được marker trong scope có thể chạy nhiều lần do retry. Nếu metric tag `logical_operations` nhưng đặt advice bên trong retry, số đếm sai dù selector hoàn toàn đúng. Test unit of measure và advice order.

## 19. Kịch bản thất bại và cách chẩn đoán

### Tình huống A — Marker có mà advice không chạy

Kiểm tra lần lượt:
1. Marker nằm ở interface/implementation đúng lookup site chưa?
2. `@Retention` có phù hợp pha xử lý metadata không?
3. Type/module/package có thuộc scope được allow không?
4. `AND/OR/NOT` có grouping sai không?
5. Join-point kind có được hỗ trợ không?
6. Class/proxy có thật sự được instrument không?
7. Caller có đi trực tiếp target hoặc self-call không?
8. Engine runtime có nạp đúng artifact/configuration không?

### Tình huống B — Advice chạy quá rộng

- Có dùng `OR` thay `AND`?
- Scope quá rộng như `all public methods`?
- Marker type-level có implicit áp mọi methods theo công cụ?
- Một meta-annotation/composed rule match cả methods ngoài ý định?
- Một target implements nhiều interfaces/roles?
- Có nhầm interface `@BusinessArea` với runtime flow điều kiện?
- Exclusion của telemetry/exporter bị thiếu?
- Generated/bridge methods đang double count?

### Tình huống C — Advice hoạt động nhưng nghiệp vụ sai

- Around advice có return/rethrow đúng contract không?
- Log/metrics sink có thể ném exception che lỗi target?
- Retry/cache/fallback được bật bởi marker không phù hợp?
- Nested precedence có làm authorization bị skip?
- Shared context có bị race giữa threads?
- Async completion có bị ghi nhận ở method-return?
- Một policy dựa input tenant chưa xác thực?

Những câu hỏi này phân biệt lỗi **selection**, lỗi **interception coverage** và lỗi **advice behavior**.

## 20. Lộ trình nâng cấp một pointcut giòn

Giả sử hiện tại aspect chọn `com.example.legacy.internal.*.do*`. Muốn đổi sang marker + scope, nên đi có kiểm soát:

### Bước 1 — Inventory và phân loại

Liệt kê các methods hiện được match và tại sao chúng thuộc concern. Phân biệt public operation, helper, event handler, storage attempt. Nếu chỉ có công cụ tính match set, vẫn cần kiểm các **actual invocations**.

### Bước 2 — Xác lập semantic vocabulary

Chọn `@ObservedOperation` cho những operations có ý nghĩa đo. Chọn type/module role `BusinessArea` cho phạm vi được phép. Công bố rằng selection mới là **giao** của hai điều kiện, không phải hợp.

### Bước 3 — Đánh dấu source có review

Gắn marker tại interface method hoặc implementation method theo lookup rule được kiểm. Đánh dấu type/interface scope ở nơi có owner. Đừng tự động mass-annotate mọi method chỉ vì nó từng match wildcard cũ.

### Bước 4 — Viết golden coverage set

Xác nhận:
- Operations bắt buộc có marker và scope.
- Methods ngoài policy bị loại.
- Internal methods không được annotate chỉ để giữ log cũ.
- Trường hợp cùng name/overload/refactor vẫn được xử lý.
- Security/audit mandatory paths có enforcement riêng.

### Bước 5 — So sánh hai selectors ở môi trường test

Chỉ so **read-only match diagnostics** nếu advice gây side effects. Bật cả hai production advices có thể làm duplicate audit, retry hoặc metrics. Review khác biệt match sets theo nghiệp vụ, không chỉ đặt mục tiêu match 100% cũ.

### Bước 6 — Chuyển dần và test runtime

Chạy integration tests trên artifact thật, gồm proxy/weaving, classloaders, interface/implementation metadata, exception paths, async và concurrency. Xác nhận error contracts và ordering vẫn đúng.

### Bước 7 — Theo dõi drift và bỏ wildcard cũ

Sau deployment, theo dõi số selected calls, missing instrumentation, unexpected names, event volume và error changes. Gỡ legacy selector khi đủ bằng chứng, không giữ hai cơ chế trái nghĩa lâu dài.

## 21. Những lỗi thường gặp

**“Có annotation là đủ chọn mọi nơi.”** Không nếu cần giới hạn architecture/trust scope.

**“Nằm trong package đúng là đủ.”** Không nếu chỉ những operations marked mới có nghĩa.

**“Dùng `OR` hay `AND` khác nhau không đáng kể.”** Sai; `OR` có thể mở phạm vi rất rộng.

**“Type-level marker luôn xuất hiện trên method declaration.”** Không; placement và metadata lookup khác nhau.

**“`@Inherited` truyền interface method marker xuống mọi implementation method.”** Không.

**“Runtime reflection thấy mọi annotation dù retention SOURCE.”** Không.

**“Marker đồng nghĩa security authorization đã được thực thi.”** Không; nó chỉ là metadata về intent.

**“Pointcut matcher match tức advice chắc chắn chạy.”** Không; còn proxy/weaving coverage và call path.

**“Một proxy chọn interface method cũng sẽ đọc annotation trên implementation method.”** Không tự động.

**“Đổi package implementation không ảnh hưởng package selector.”** Có thể làm mất match nếu scope hardcode package.

**“Trong scope thì mọi overload đều nên match.”** Không nếu mỗi overload có semantics riêng và marker chỉ áp một declaration.

**“Có annotation thì có thể retry non-idempotent command.”** Không; retry eligibility cần hợp đồng riêng.

**“Annotation scope tự biểu thị per-request state.”** Không; type marker và task context là hai khái niệm.

**“ThreadLocal tự đi theo async logical operation.”** Không; cần propagation.

**“`@Observed` có nghĩa log mọi arguments.”** Không; cần data minimization/privacy policy.

**“Một positive test chứng minh predicate AND đúng.”** Không; cần hai negative cases theo từng điều kiện.

**“Logger lỗi nên biến target success thành failure.”** Chỉ nếu đó là policy được công bố; best-effort observer không nên phá business result.

**“Hai aspects cùng marker có cùng ordering.”** Không; phải khai precedence riêng.

**“Những methods generated/bridge không quan trọng.”** Có thể ảnh hưởng reflection và double count; cần test.

**“Chỉ cần sửa wildcard tên package khi migrate.”** Không; cần định nghĩa scope semantics và ownership.

## 22. Bài tập vận dụng kèm đáp án

### Câu 1 — Marker đúng, scope sai

Một `DebugApi.cleanup()` có `@ObservedOperation` nhưng không thuộc business module. Theo `MARKED && IN_SCOPE`, advice có chạy không?

**Đáp án:** Không, giả sử không có selector bổ sung. Marker là điều kiện cần nhưng chưa đủ.

### Câu 2 — Scope đúng, marker thiếu

`BillingApi.health()` thuộc `@BusinessArea` nhưng không `@ObservedOperation`. Kết quả?

**Đáp án:** Không được chọn. Đây là negative test xác nhận giới hạn không tự kéo tất cả methods vào advice.

### Câu 3 — Sửa AND thành OR

Predicate được đổi thành `MARKED || IN_SCOPE`. Có nguy cơ gì?

**Đáp án:** Mọi method trong scope hoặc mọi method marked ngoài scope có thể được chọn, gây overmatching, metric noise và side effects của policies khác.

### Câu 4 — Annotation interface

Marker nằm trên `BillingApi.charge`, target implementation override không khai annotation. Java reflection trên implementation method có tự tìm marker interface không?

**Đáp án:** Không mặc định. Trong demo handler đọc `Method` ở interface view nên thấy. Engine khác phải có lookup rule tường minh.

### Câu 5 — Thay implementation

Team đổi `OldBillingImpl` thành `NewBillingImpl`, cả hai implement `BillingApi`. Selector trong demo có đổi không?

**Đáp án:** Không nếu vẫn proxy qua cùng interface view; điều kiện dựa `BillingApi` và method annotation, không dựa concrete class.

### Câu 6 — Direct-target call

Một caller giữ `BillingTarget` gốc và gọi `charge`, không qua proxy. Marker và scope đủ chưa?

**Đáp án:** Chưa để handler chạy; đó là lỗi hoặc giới hạn **interception coverage**, không phải predicate.

### Câu 7 — Exception

`billing.charge("BAD")` có marker và scope, target throw. Nếu counter đếm selected attempts, có cộng không?

**Đáp án:** Có. Demo đếm trước invocation, `SELECTED=2` gồm success A và failure BAD.

### Câu 8 — Runtime retention

Một handler dùng `Method.isAnnotationPresent` nhưng annotation khai `@Retention(SOURCE)`. Kỳ vọng có marker ở runtime?

**Đáp án:** Không. Cần runtime retention cho reflection-based selection.

### Câu 9 — Authorization

Một method thiếu marker bảo mật và không match advice, nhưng vẫn xử lý dữ liệu nhạy cảm. Giải pháp có thể là “cho phép” mặc định không?

**Đáp án:** Không mặc định. Cần trusted security enforcement và contract/architecture tests bắt buộc coverage.

### Câu 10 — Async metric

Một selected method trả future pending. Advice after-return ghi success khi nhận future. Nó có đo task completion không?

**Đáp án:** Không; đó chỉ là successful method return-handle. Muốn đo task outcome phải hook completion.

### Câu 11 — `cflow` và type scope

Một join point có marker/type scope nhưng không nằm trong checkout flow hiện hành. Nếu selector còn `AND inFlow(checkout)`, nó có match không?

**Đáp án:** Không. Context predicate là điều kiện thứ ba phải đúng; engine cần hỗ trợ và propagation phù hợp.

### Câu 12 — Named pointcut

Trace và Metrics dùng cùng named pointcut `ObservedBusinessOperation`. Team thêm Retry dùng luôn tên ấy. Điều gì cần review?

**Đáp án:** Marker chỉ mô tả observability, không bảo đảm target idempotent. Retry cần eligibility, attempt/failure policy và ordering riêng.

### Câu 13 — Nhãn log

Một method `charge` được retry ba lần. Advice metric ở trong retry ghi ba events. Đây có phải bug?

**Đáp án:** Nếu metric là **attempts** thì có thể đúng; nếu là **logical charge operations** thì sai. Đặt selector/order theo đơn vị đo.

### Câu 14 — Metadata qua module

Marker và scope đúng, nhưng runtime không truy cập được method do module access constraint. Có nên bỏ qua warning?

**Đáp án:** Không. Matching và ability-to-intercept là hai giai đoạn; cần chỉnh toolchain/boundary hợp lệ hoặc dùng wrapper/API phù hợp.

## 23. Checklist review trước khi triển khai

1. **Intent:** Marker có diễn đạt một concern duy nhất và rõ không?
2. **Placement:** Annotation ở method/interface/class nào?
3. **Retention:** Metadata có sẵn ở pha công cụ dùng không?
4. **Target:** Annotation `@Target` có đúng nơi khai báo không?
5. **Lookup:** Tool đọc interface declaration hay implementation/target?
6. **Type scope:** Có role/API boundary được công bố không?
7. **Module scope:** Package/module có phải architecture boundary thực không?
8. **Dynamic scope:** Có phụ thuộc request/control-flow context và có propagation đúng không?
9. **Logic:** Dùng `AND`, `OR`, `NOT` với grouping tường minh?
10. **Exclusions:** Helpers/exporters/health checks được loại có chủ đích?
11. **Join point:** Call/execution/constructor/field join point nào được hỗ trợ?
12. **Proxy:** Caller có đi qua đúng proxy không?
13. **Weaving:** Binary/classloader artifact thực sự được weave chưa?
14. **Self-invocation:** Internal calls có được chọn không, theo cơ chế nào?
15. **Generics:** Overloads/bridges/synthetic methods có gây mismatch không?
16. **Concurrency:** Shared aspect state có race, visibility hoặc giữ args/results?
17. **Async:** Method return khác task completion, có lifecycle đúng?
18. **Errors:** Result/exception của target có bị masking không?
19. **Ordering:** Retry/cache/auth/metrics có precedence và semantics rõ?
20. **Security:** Trusted enforcement có thể bị bypass do thiếu marker/scope không?
21. **Positive test:** Method marked và in-scope được instrument?
22. **Negative tests:** Marked ngoài scope và unmarked trong scope đều không instrument?
23. **Refactor test:** Đổi class/package implementation không phá intended match?
24. **Migration:** Marker/type/module change có versioning và rollout?
25. **Diagnostics:** Có đo missing/extra selected invocations?
26. **Performance:** Advice overhead, metric cardinality, logging rate và p99 hợp lý?
27. **Privacy:** Không tự log secrets chỉ vì marker tồn tại?
28. **Ownership:** Ai duyệt việc thêm/bỏ marker và scope?
29. **Fallback:** Khi metadata thiếu, policy fail-safe thế nào?
30. **Rollback:** Có thể thu hẹp/disable an toàn khi overmatching phát sinh?

## Kết luận

**Kết hợp marker tường minh với giới hạn phạm vi** giúp pointcut vừa có **ý định rõ ở từng join point**, vừa có **ranh giới áp dụng được quản trị**. Công thức `MARKED && IN_SCOPE` tránh hai sai lầm phổ biến: chọn mọi thứ có cùng annotation ở bất cứ đâu, hoặc chọn mọi operation chỉ vì nó nằm cùng package/type. Khi cần, thêm ràng buộc join-point kind, exclusions và dynamic context theo ngữ nghĩa được công bố.

Tuy nhiên, một selector đúng vẫn chưa chứng minh advice thật sự chạy hoặc an toàn: phải xác minh proxy/weaving coverage, metadata lookup, direct/self calls, order của các aspects, error/result contracts, privacy và security boundary. Java 17 demo dùng ba tình huống đối chứng để chứng minh predicate AND và failure path; còn các hệ thống lớn nên bổ sung **architecture governance, positive/negative coverage tests, refactor tests và runtime integration verification**. Mục tiêu không phải thêm annotation càng nhiều càng tốt, mà là để **mỗi marker có nghĩa**, **mỗi scope có owner** và **mỗi policy chạy đúng nơi, đúng lúc, đúng hợp đồng**.
