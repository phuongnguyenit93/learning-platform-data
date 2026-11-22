# Giới hạn phụ thuộc vào tên gói và chữ ký nội bộ

## 1. Vấn đề: pointcut chạy đúng hôm nay nhưng biến mất sau một lần refactor

Trong **Aspect-Oriented Programming (AOP)**, một aspect tập trung hóa hành vi xuyên suốt như tracing, logging, metrics, kiểm soát điều kiện, retry hoặc audit. Để áp dụng advice, một **pointcut** phải xác định đúng các **join point** mà cơ chế AOP hỗ trợ. Với Java, những join point liên quan đến lời gọi/thực thi phương thức thường được mô tả hoặc lọc bằng tên kiểu, tên gói, tên phương thức, modifiers, argument types hay metadata.

Cách nhanh nhất là viết một quy tắc kiểu:

~~~text
Ví dụ giả mã pointcut (không phải cú pháp thống nhất của mọi AOP engine):
    within package com.example.orders.internal
    AND method name startsWith "handle"
    AND first parameter type = com.example.orders.internal.LegacyCommand
~~~

Cấu hình trông tiện, nhưng có những phụ thuộc ẩn:

- Đổi `com.example.orders.internal` thành `com.example.sales.engine` làm selector cũ mất match.
- Đổi helper `handlePayment(...)` thành `runChargeStep(...)` khiến metrics không còn chạy.
- Thay class `LegacyCommand` bằng interface `ChargeRequest` thay đổi signature dù ý nghĩa use case vẫn như cũ.
- Một overload mới có cùng tên `handlePayment` được bổ sung, làm selector quá rộng hoặc sai type.
- Một class khác vô tình đáp ứng wildcard pattern, khiến advice được áp vào nơi không thuộc chính sách.
- Một generated/bridge method làm số join points hay signature quan sát được khác dự tính.
- Một caller gọi thẳng target hoặc một self-call không qua proxy, nên pointcut dù “đúng mẫu” vẫn không được kích hoạt.

Vì thế: **giới hạn phụ thuộc vào tên gói và chữ ký nội bộ** có nghĩa là thiết kế pointcut và abstraction theo **ý nghĩa/capability/hợp đồng ổn định**, thay vì ghép kiến trúc AOP chặt vào chi tiết triển khai dễ đổi.

> **Nguyên tắc trung tâm:** Điểm mà một aspect cần quan sát hoặc áp chính sách nên được xác định bằng **ranh giới nghiệp vụ hoặc kỹ thuật được công bố**, không phải tình cờ nằm ở một package hay mang tên helper nào. Nếu vẫn phải dùng package/signature matching, hãy xem đó là một dependency cần được tài liệu hóa, kiểm tra và bảo trì.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt **semantic boundary** với **lexical/structural selector**.
2. Hiểu coupling do package name, class name, method signature, visibility và call/execution join-point kind.
3. Đánh giá trade-off giữa **annotation marker**, **interface/role-based selection**, **named pointcut composition** và **package patterns**.
4. Phát hiện thay đổi khi rename/move package, overload, generic erasure, bridge method hoặc thêm implementation.
5. Tránh nhầm **điểm được matcher chọn** với **điểm thực sự được engine intercept**.
6. Thiết kế reusable pointcut theo stable vocabulary và áp nguyên tắc ownership/versioning.
7. Hiểu giới hạn của annotation inheritance, interface metadata, runtime reflection và build/weaving.
8. Kiểm soát advice order, result/error contract, security và side effects khi selector mở rộng.
9. Viết **Java 17 runnable demo** chọn interface method bằng annotation thay vì tên class implementation.
10. Lập regression tests để refactor không làm mất hoặc làm tăng ngoài ý muốn độ phủ advice.

Bài thuộc kiến thức AOP cơ bản và nâng cao nói chung. **Không có một cú pháp pointcut duy nhất cho mọi engine**. Các biểu thức so khớp được trình bày dưới dạng giả mã hoặc thiết kế trừu tượng trừ khi ghi rõ đó là Java runnable code.

## 2. Những dạng coupling nào thường phát sinh?

### 2.1. Package coupling

Aspect chọn “mọi method trong `company.application.impl`”. Quy tắc gắn chính sách vào **vị trí lưu source/type trong namespace**. Package có thể được tách theo bounded context, đổi tên, gom module, chuyển từ package `impl` sang `adapter`, hoặc tái cấu trúc mà behavior API vẫn giữ.

**Nguy cơ:** refactor package làm thiếu match; hoặc chuyển thêm class mới vào vùng match khiến advice áp quá rộng.

### 2.2. Concrete-type coupling

Aspect chỉ chọn methods thuộc `LegacyPaymentService`. Sau khi code thay bằng `DefaultPaymentGateway` hoặc hai implementations, policy không tự mở rộng theo vai trò “payment gateway”.

**Nguy cơ:** chính sách được định nghĩa theo concrete class thay vì capability mà contract yêu cầu.

### 2.3. Signature coupling

Aspect phụ thuộc `charge(String,long)`, nhưng API đổi sang `charge(ChargeRequest)`, overload `charge(String,BigDecimal)`, hoặc generic erasure làm cách runtime phản ánh method khác.

**Nguy cơ:** selector trượt khỏi operation gốc hoặc chọn cả những methods mới không đúng ý định.

### 2.4. Internal-helper coupling

Aspect đặt tại private/internal method `preCommit()`. Một lần inline, split, rename hoặc điều chỉnh thuật toán làm method biến mất nhưng *public operation* vẫn hoạt động đúng.

**Nguy cơ:** việc bảo trì implementation vô tình sửa semantics của một concern xuyên suốt.

### 2.5. Call-path/tool coupling

Selector có thể nhắm đúng interface method, nhưng cơ chế interception cụ thể chỉ thấy những lời gọi đi qua proxy. Một call nội bộ `this.work()` có thể không qua handler. Một weaver nhìn method-execution join point lại có phạm vi khác.

**Nguy cơ:** developer nhìn pattern và cho rằng chính sách “bao phủ toàn bộ”, mặc dù interception model không đáp ứng.

### 2.6. Metadata coupling

Đưa `@Observed` vào interface tạo một hợp đồng mới; aspect phụ thuộc vị trí annotation, retention và metadata-resolution policy. Annotation ổn định hơn tên helper trong nhiều trường hợp, nhưng **không miễn phí coupling**. Nó phải có owner, versioning và tests.

## 3. Selector theo cú pháp khác selector theo ý nghĩa

Một **lexical selector** có thể viết bằng các thuộc tính dễ nhìn trong source: namespace, chữ ký, tên class. Một **semantic selector** biểu diễn “operation này thuộc capability X”, “method này là public domain boundary” hoặc “invocation này được đánh dấu cho audit”.

Bảng so sánh:

| Cơ sở chọn điểm | Điều nó thật sự nói | Độ ổn định khi refactor | Rủi ro |
| --- | --- | --- | --- |
| Package `*.impl.*` | Mã hiện nằm trong một vùng namespace. | Thấp nếu package chỉ là chi tiết tổ chức. | Rename/move tạo false negative. |
| Concrete class | Loại runtime/declaration cụ thể. | Thấp khi thay implementation. | Bỏ sót implementations mới. |
| Method name wildcard | Một quy tắc tên. | Trung bình/thấp tùy naming convention. | False positive/negative. |
| Exact method signature | Một declaration chính xác. | Tốt khi signature là published contract. | Dễ vỡ nếu ký hiệu nội bộ thay. |
| Interface/role | Một abstraction được công bố. | Tốt khi interface ổn định. | Phụ thuộc proxy/weaver, override metadata. |
| Annotation/marker | Một ý định được tác giả công bố. | Tốt nếu marker được quản trị. | Missing/overused marker, metadata lookup. |
| Named pointcut | Một khái niệm selection dùng lại. | Tốt nếu định nghĩa trung tâm ổn định. | Định nghĩa bên trong vẫn có thể giòn. |
| Runtime context predicate | Điều kiện dựa flow/arguments/context. | Hữu ích cho semantic policy. | Overhead, context validity, nondeterminism. |

Không phải lúc nào package là sai và annotation là đúng. Nếu chính sách **cố ý áp cho mọi class ở một module boundary**, và package là một phần của kiến trúc được bảo vệ, package matching có thể thích hợp. Nhưng cần khẳng định package boundary là contract, không phải thư mục ngẫu nhiên.

## 4. Đi từ “tên method” đến “hợp đồng được công bố”

Giả sử có business operation `submitOrder`, còn implementation hiện tại gọi các helpers:

~~~text
Public API: OrderSubmission.submit(order)
       |
       +-- DefaultSubmitter.normalizeFields(...)
       +-- DefaultSubmitter.reserveSlots(...)
       +-- DefaultSubmitter.persistInternal(...)
~~~

Nếu concern là **latency của một logical submission**, điểm thích hợp thường là **public use-case boundary** `OrderSubmission.submit`, thay vì `persistInternal`:
- Helper có thể được gọi hai lần hoặc thay thế khi đổi database.
- Helper có thể biến mất sau khi tối ưu.
- Một lần `submit` có thể vẫn phải trả kết quả dù bước persist được gộp.
- Metrics ở helper dễ đếm attempts/thành phần, không phải logical submissions.

Nếu concern lại là **storage-attempt latency**, internal method có thể là điểm đo đúng — nhưng khi đó metric phải được ghi rõ là **storage attempt**, và selection cần owner của storage module bảo trì cùng code nội bộ.

### 4.1. Cùng một workflow có nhiều ranh giới hợp lệ

~~~text
SubmitOrder API
  -> Permission check
  -> Retry policy
       -> Storage attempt
  -> Return receipt
~~~

Một aspect muốn đo **logical call** nên quanh boundary SubmitOrder. Một aspect đo **mỗi retry attempt** nên ở storage-attempt boundary. Không có một pointcut duy nhất đúng cho mọi metric; trước tiên phải xác định đơn vị quan sát.

### 4.2. Tránh chọn điểm chỉ vì có sẵn `public`

Một public method có thể là helper hoặc implementation detail của một library. Một API boundary cũng có thể là interface method do proxy bảo vệ chứ không đồng nghĩa mọi public methods trong package. Chọn điểm theo **hợp đồng và chức năng**, sau đó mới biểu diễn bằng khả năng selector của công cụ.

### 4.3. Stable boundary cần có người sở hữu

Nếu `OrderSubmission.submit` là contract chính thức, một thay đổi breaking signature phải đi qua review/versioning. Điều này khiến pointcut đáng tin hơn nhiều so với `normalizeFields` không có lời hứa ổn định.

## 5. Interface/role-based selection

Một hướng giảm coupling là chọn join points gắn với một **interface hoặc role** ổn định:

~~~java
interface PaymentPort {
    Receipt charge(ChargeRequest request);
}
~~~

Đây là **mã minh họa**, các types `Receipt`/`ChargeRequest` chưa được khai báo, không phải chương trình độc lập.

Nếu `PaymentPort` định nghĩa operation mà AOP cần theo dõi, công cụ có thể chọn method theo:
- Declaration của interface.
- Implementation của interface.
- Những proxy implements interface.
- Annotation metadata đặt trên interface method.

Tuy nhiên, **engine phải cho biết** nó match declaration nào, tại call site hay execution, và metadata được tìm ở đâu.

### 5.1. Lợi ích

- Đổi `LegacyPaymentImpl` thành `ModernPaymentImpl` vẫn giữ role `PaymentPort`.
- Đổi package implementation không nhất thiết sửa interface contract.
- Có thể thêm một implementation mới và dùng cùng concern.
- Compiler có thể giúp kiểm method contract.
- Tests có thể dùng interface-level test fixtures.

### 5.2. Giới hạn

- Một interface quá rộng có thể kéo advice vào operations không phù hợp.
- Một class implements nhiều interfaces; cùng method signature có thể có nhiều nguồn metadata.
- Implementation có thể thêm methods ngoài interface mà selector không chọn.
- Interface annotations không tự được Java reflection kế thừa sang implementation methods.
- Một JDK proxy chỉ có những method được expose bởi interfaces của nó, không tự bao tất cả concrete methods.
- Direct calls hoặc self-invocations có thể bypass proxy.

**Thiết kế đúng:** tách một interface theo capability có ý nghĩa, đặt contract ổn định và test những operations được chọn/không chọn.

## 6. Annotation-based selection: ý định rõ, nhưng phải quản lý metadata

Một marker kiểu:

~~~java
// Minh họa; thiếu các imports và API đầy đủ.
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ObservedOperation { }
~~~

cho phép developer nói rõ “operation này được quan sát”, thay vì “bất kỳ method tên `execute*`”. Khi có nhiều implementations, một marker trên **interface method** có thể trở thành selection contract nếu interceptor nhìn vào interface declaration.

### 6.1. Annotation không tự lan mọi nơi

Với Java reflection:
- `@Retention(RUNTIME)` giúp annotation sẵn ở runtime reflection theo mục tiêu khai báo.
- `@Target(METHOD)` giới hạn nơi annotation được đặt.
- `@Inherited` chỉ có semantics inheritance cho **class-level annotations**, không tự làm method annotations từ interface appear trên implementation method.
- Một `Method` lấy từ interface và một `Method` lấy từ implementation là hai metadata views khác nhau.
- Một AOP engine có thể tìm annotation theo convention riêng, nhưng phải dựa vào tài liệu và tests của engine đó.

Nếu marker đặt trên interface, handler dùng `method.getDeclaringClass()` hoặc `isAnnotationPresent` phải chắc chắn `method` thực sự đại diện interface declaration, không lầm tưởng mọi execution join point nhìn thấy annotation giống nhau.

### 6.2. Annotation vừa là API vừa là policy binding

Một `@ObservedOperation` công bố intent. Khi thêm annotation cho method mới, toàn bộ instrumentation có thể áp dụng; khi xóa annotation, coverage thay đổi. Do đó marker nên được quản lý:
- Đặt tên phản ánh semantics, không phản ánh tên team/package cũ.
- Có owner và documentation.
- Có tests kiểm coverage.
- Review annotation changes như thay đổi behavior.
- Không thêm hàng loạt bằng wildcard mà không hiểu side effects.

### 6.3. Không lạm dụng một marker cho nhiều concerns khác nhau

Nếu cùng marker dùng để enable logging, retry, transaction, authorization và masking, một thay đổi annotation có thể bật cả loạt policies. Tách vocabulary theo ý nghĩa:
- Boundary cho tracing/metric.
- Idempotent operation được phép retry.
- Audited operation theo hợp đồng lưu bền.
- Protected operation theo security policy đáng tin.

Một marker không tự bảo đảm các yêu cầu ấy; annotation chỉ là **tín hiệu selection**, còn policy phải được hiện thực và kiểm thử.

## 7. Named pointcut: trừu tượng hóa việc chọn join point

Nếu nhiều aspects đều dùng cùng một pattern:

~~~text
aspect Trace:
    select methods under package x.y.impl

aspect Metrics:
    select methods under package x.y.impl

aspect Audit:
    select methods under package x.y.impl
~~~

một refactor cần sửa cả ba. Một số engine cho phép định nghĩa **named pointcut** hoặc một abstraction equivalent:

~~~text
pointcut LogicalOperations:
    method matches stable boundary role or explicit marker

Trace:   select LogicalOperations
Metrics: select LogicalOperations
Audit:   select LogicalOperations
~~~

Đây là **giả mã**, không mô tả cú pháp chuẩn. Lợi ích:
- Một nơi quản lý selection contract.
- Các aspects có ngôn ngữ chung về “logical operation”.
- Dễ có tests kiểm matcher.
- Giảm duplicate wildcard patterns.
- Giảm nguy cơ một aspect vẫn bám tên package cũ.

### 7.1. Trừu tượng hóa không làm quy tắc sai thành đúng

Nếu `LogicalOperations` bên trong vẫn đơn giản là `package(*.impl)`, nó vẫn coupling với package; chỉ là coupling được **đóng gói tập trung**. Muốn bền vững, cần review nội dung semantic của matcher.

### 7.2. Tách các role theo cấp độ

Một kiến trúc có thể định nghĩa:
- `BusinessOperation`: logical business API entry.
- `RepositoryAttempt`: một lần truy cập dữ liệu.
- `ExternalCall`: lời gọi tới dependency.
- `AuditedMutation`: operation sửa dữ liệu cần audit.

Các role này hữu ích hơn một pointcut `allMethods` quá rộng. Nếu một operation thuộc hai roles, thứ tự aspects và policy cần được khai rõ.

### 7.3. Named pointcut có lifecycle/version

Nếu hai modules dùng một named selector, đổi định nghĩa có thể đổi logging/metrics/audit đồng thời. Cần integration tests và thông tin về tương thích, không coi nó chỉ là refactor “không đổi hành vi”.

## 8. Java 17 runnable: theo interface marker, không theo tên implementation

Ví dụ này dùng **JDK dynamic proxy** để minh họa một chiến lược selection có mục đích rõ. Nó không khẳng định đây là syntax hoặc thuật toán của mọi AOP engine.

**Ý tưởng:**
- Interface `Gateway` công bố method `execute(String)` có marker `@Boundary`.
- `LegacyEngine` và `RefactoredEngine` có tên class và cách xử lý nội bộ khác nhau nhưng cùng implement `Gateway`.
- Một proxy interceptor đọc annotation của **interface method** mà proxy nhận, không kiểm package hay tên class cụ thể của implementation.
- `ping()` không có marker nên vẫn delegate nhưng không có log advice.
- Khi target ném `IllegalArgumentException`, interceptor gỡ `InvocationTargetException` và rethrow cause.
- Bộ đếm `matched` tính **mọi invocation được đánh dấu** bao gồm cả invocation kết thúc bằng lỗi.

Tạo file **`StableBoundaryDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class StableBoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Boundary { }

    public interface Gateway {
        @Boundary
        String execute(String id);

        String ping();
    }

    static final class LegacyEngine implements Gateway {
        @Override
        public String execute(String id) {
            System.out.println("TARGET legacyHandler " + id);
            if ("BAD".equals(id)) {
                throw new IllegalArgumentException("invalid id");
            }
            return "OK:" + id;
        }

        @Override
        public String ping() {
            System.out.println("TARGET ping");
            return "PONG";
        }
    }

    static final class RefactoredEngine implements Gateway {
        @Override
        public String execute(String id) {
            System.out.println("TARGET renamedPipeline " + id);
            if ("BAD".equals(id)) {
                throw new IllegalArgumentException("invalid id");
            }
            return "OK:" + id;
        }

        @Override
        public String ping() {
            System.out.println("TARGET ping");
            return "PONG";
        }
    }

    static Gateway observe(Gateway target, AtomicInteger matched) {
        return (Gateway) Proxy.newProxyInstance(
                Gateway.class.getClassLoader(),
                new Class<?>[] { Gateway.class },
                (proxy, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "equals" -> proxy == arguments[0];
                            case "hashCode" -> System.identityHashCode(proxy);
                            case "toString" -> "GatewayProxy";
                            default -> throw new UnsupportedOperationException(
                                    method.getName());
                        };
                    }

                    boolean selected = method.isAnnotationPresent(Boundary.class);
                    if (selected) {
                        matched.incrementAndGet();
                        System.out.println("ADVICE before " + method.getName());
                    }

                    try {
                        Object value = method.invoke(target, arguments);
                        if (selected) {
                            System.out.println("ADVICE after " + method.getName());
                        }
                        return value;
                    } catch (InvocationTargetException wrapped) {
                        Throwable cause = wrapped.getCause();
                        if (selected) {
                            System.out.println("ADVICE error " + method.getName()
                                    + " " + cause.getClass().getSimpleName());
                        }
                        throw cause;
                    }
                }
        );
    }

    public static void main(String[] args) {
        AtomicInteger selectedCount = new AtomicInteger();
        Gateway oldVersion = observe(new LegacyEngine(), selectedCount);
        Gateway newVersion = observe(new RefactoredEngine(), selectedCount);

        System.out.println("OLD=" + oldVersion.execute("A"));
        System.out.println("NEW=" + newVersion.execute("B"));
        System.out.println("PING=" + oldVersion.ping());

        try {
            newVersion.execute("BAD");
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR=" + error.getMessage());
        }

        System.out.println("MATCHED=" + selectedCount.get());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac StableBoundaryDemo.java
java StableBoundaryDemo
~~~

**Stdout kỳ vọng:**

~~~text
ADVICE before execute
TARGET legacyHandler A
ADVICE after execute
OLD=OK:A
ADVICE before execute
TARGET renamedPipeline B
ADVICE after execute
NEW=OK:B
TARGET ping
PING=PONG
ADVICE before execute
TARGET renamedPipeline BAD
ADVICE error execute IllegalArgumentException
ERROR=invalid id
MATCHED=3
~~~

### 8.1. Vì sao đổi tên implementation không phá selector?

Handler xét annotation trên `method` được JDK proxy đưa tới: đây là method thuộc interface `Gateway`. Cả hai targets đều implement cùng interface contract nên selector dựa trên `@Boundary` của `execute` vẫn match, bất kể class concrete tên `LegacyEngine` hay `RefactoredEngine`.

Trong demo, hai implementation classes cùng nằm trong một source file; **không mô phỏng refactor package thật**. Tuy nhiên, điều kiện matching không chứa package/tên class implementation, nên một lần đổi tên/refactor hợp lệ giữ interface contract sẽ không cần sửa selector này.

### 8.2. Vì sao `ping()` không xuất hiện ADVICE before/after?

`ping()` không có `@Boundary` tại interface declaration. Handler vẫn gọi target (nên in `TARGET ping`) nhưng không emit instrumentation. Điều này minh họa **positive/negative coverage**: điểm được chọn và điểm không được chọn đều cần test.

### 8.3. Vì sao `MATCHED=3` chứ không phải 2?

Có ba lời gọi `execute`: A thành công, B thành công và BAD ném exception. Bộ đếm tăng khi advice thấy method được chọn, **trước khi gọi target**, nên nó đo số lần attempted boundary invocations, không phải success count.

Nếu muốn đo thành công, tăng counter ở đường `method.invoke` hoàn tất bình thường. Nếu muốn đo cả result/error độc lập, dùng counters riêng.

### 8.4. Lỗi từ target có được giữ nguyên không?

Khi `RefactoredEngine.execute("BAD")` ném `IllegalArgumentException`, `Method.invoke` bọc trong `InvocationTargetException`. Handler lấy `getCause()`, log lỗi rồi ném lại cause. Caller bắt đúng loại `IllegalArgumentException` và thấy message `invalid id`. Chỉ là **instrumentation**, không chuyển lỗi thành value giả.

### 8.5. Giới hạn của ví dụ

- JDK dynamic proxy intercept **các lời gọi đi qua proxy**, không tất cả executions nội bộ của target.
- Interface marker chỉ được đọc trực tiếp từ `Method` mà proxy nhận; method annotation trên concrete implementation không tự bị Java reflection “merge” vào đó.
- `method.getDeclaringClass() == Object.class` xử lý riêng ba Object methods cơ bản với identity semantics của proxy. Đây không phải equality policy phù hợp cho mọi domain.
- Code chạy tuần tự; `AtomicInteger` chỉ minh họa counter an toàn nếu nhiều threads cập nhật, không làm target tự thread-safe.
- Không có annotation processor, aspect compiler, bytecode weaving hay DSL pointcut trong chương trình.
- Không có methods trùng signature giữa nhiều interfaces; nếu có, cần kiểm method-resolution behavior của proxy cụ thể.
- Không chứng minh “mọi operation quan trọng đều đã được annotate”; đó là trách nhiệm thiết kế và coverage tests.
- Không đo transaction commits, async completions hoặc retries; bộ đếm chỉ đo proxy invocation match.

### 8.6. Bài tập mở rộng demo

Thêm một implementation `RemoteEngine` thuộc package/module khác nhưng vẫn implement `Gateway`; tạo proxy bằng cùng factory và xác nhận `execute` được quan sát. Nếu đổi tên helper private bên trong `RemoteEngine`, selector vẫn phải không đổi.

Thử bỏ `@Boundary` khỏi interface method và xác nhận `MATCHED=0` nhưng target methods vẫn chạy. Thử đặt marker **chỉ** trên implementation method và lưu ý proxy matcher trong demo sẽ không match nếu interface method không có marker. Đây là một bài test hữu ích về metadata lookup contract.

## 9. Signature nội bộ: vì sao một lần refactor có thể đổi join-point set?

### 9.1. Rename nội bộ

Method `calculateInternalTotal(Order)` đổi thành `recalculateTotals(Order)`. Nếu selector so exact name, matcher ngừng chọn. Chức năng nghiệp vụ vẫn đúng, nên functional tests không tự phát hiện metrics/audit mất.

### 9.2. Move giữa packages

Method `PaymentHelper.authorize` chuyển từ `legacy.impl` sang `payment.internal`. Một wildcard `within legacy.impl..` mất match. Ngoài ra, package boundary còn ảnh hưởng Java visibility, reflection access và JPMS exports/opens.

### 9.3. Thêm overload

Ví dụ trước có `process(String)`, nay thêm `process(Request)`. Một selector theo tên `process` có thể match cả hai. Nếu chỉ `process(Request)` biểu diễn operation công khai, thì overload cũ có thể trở thành helper, nhưng metrics/audit sẽ bị đếm gấp đôi nếu cả hai cùng chạy.

### 9.4. Thay parameter representation

Đổi `int amountInCents` thành `Money amount` có thể là một refactor làm tốt type safety. Nếu pointcut bám `charge(int)`, nó sẽ trượt dù operation `charge` vẫn tồn tại trong interface mới.

### 9.5. Generic erasure/bridge methods

Java generic APIs có thể sinh **bridge methods** để giữ overriding semantics sau type erasure, tùy compilation. Một matcher dựa reflection vào runtime method set có thể thấy synthetic/bridge entries; một engine AOP có thể có logic riêng để bỏ qua/gộp chúng.

Đừng giả định các methods trông giống nhau ở source tương ứng 1–1 với join points ở bytecode hoặc reflection. Cần test với generic interface implementations, covariant returns và bridge methods khi concern có nguy cơ bị đếm hai lần.

### 9.6. Private/final/static methods

Một số interception models dựa proxy có giới hạn với private, final hoặc static methods; một weaver khác có thể hỗ trợ những join-point kinds khác. Một selector khớp tên private helper chưa chắc là một điểm có thể intercept trong công cụ hiện tại.

**Ranh giới của bài:** nói đúng về Java và cơ chế AOP nói chung; khả năng match/intercept thực tế phải xác minh trên engine/toolchain đã chọn, không suy mọi engine như nhau.

## 10. Binary API khác internal source signature

Một **public interface method** có thể là phần của compatibility contract. Một private helper có thể đổi tên bất kỳ lúc nào khi refactor.

Nhưng “public” không tự có nghĩa stable:
- Một public method có thể nằm trong internal package không cam kết compatibility.
- Một interface public có thể vẫn được xem là internal API của module.
- Một method package-private có thể là architectural boundary được một team quản lý nhưng không phù hợp cross-module use.
- Generated methods và bridge methods có thể public ở bytecode mà không phải API dành cho callers.

Một stable selector cần một **semantic contract** do người quản trị công bố, không chỉ một modifier.

### 10.1. Tạo vocabulary ranh giới

Ví dụ một hệ thống dùng các khái niệm được quản trị:
- `BusinessCommand`
- `QueryBoundary`
- `ExternalDependencyCall`
- `AuditedMutation`
- `RetryableRead`

Mỗi từ cần định nghĩa:
- Những operations nào thuộc nhóm?
- Những operations nào cố ý bị loại?
- Method return-handle hay task-completion có được tính?
- Có đếm internal calls?
- Có cần annotation/interface?
- Ai phê duyệt thêm/bớt?
- Có dùng để bảo mật hay chỉ instrumentation?

### 10.2. Tránh “tập hợp tất cả mọi thứ”

Nếu một pointcut rộng áp tracing+audit+retry+authorization cho mọi method có tên `execute`, một method mới có thể vô tình nhận retry cho lệnh không idempotent. Selector càng rộng, policy càng cần tách role và review.

### 10.3. Contract thay đổi thì selector cũng có thể cần thay

Giới hạn coupling không có nghĩa pointcut **không bao giờ thay đổi**. Nếu published business boundary thật sự đổi (chia use case hoặc đổi semantics), advice placement phải được xem lại một cách có chủ đích. Mục tiêu là **chỉ đổi khi contract đổi**, không đổi vì một helper rename.

## 11. Chọn call hay execution join point có ảnh hưởng lớn

Một số AOP models phân biệt:
- **Call join point:** điểm có lời gọi tới method.
- **Execution join point:** điểm method body được thực thi.
- **Initialization/field/constructor events:** khi engine hỗ trợ.

Nếu muốn đo một logical operation, call/execution có thể cho số occurrences khác nhau:
- Một method được gọi nhiều lần từ các callers.
- Một proxy có thể thấy call qua wrapper nhưng không thấy direct call.
- AOP tại execution có thể thấy invocation nội bộ mà call-site pointcut không chọn.
- Async calls return stage sớm nhưng actual task tiếp tục.
- Retry làm cùng execution xảy ra nhiều lần.

Vì vậy, **ổn định tên method không đủ**; phải chọn **join-point kind** phù hợp với semantics.

### 11.1. Self-invocation

Trong delegating proxy:

~~~text
Caller -> proxy.outer()
             -> target.outer()
                    -> this.inner()
~~~

Handler thường không thấy `inner()` vì target gọi trực tiếp `this.inner()`. Nếu pointcut cho `inner` cần bắt mọi method-executions, proxy-only may be insufficient. Không sửa bằng cách đổi wildcard package; cần xem **interception boundary**.

### 11.2. Aspect weaving có thể quan sát khác proxy

Source/bytecode weaving có thể chèn code tại execution/call sites theo loại join points được engine hỗ trợ. Nhưng weaving scope, classloader và generated artifacts vẫn quyết định độ phủ. Không tuyên bố dệt trực tiếp luôn bao hết mọi đường gọi.

### 11.3. Chọn ranh giới tin cậy

Nếu concern là security/authorization **bắt buộc**, cần bảo vệ ở trusted boundary mà mọi access đi qua. Không dựa độc nhất vào pointcut có thể bị bỏ qua khi caller giữ target gốc hoặc module khác không được weave. Một stable interface marker không tự tạo một security boundary.

## 12. Mở rộng pointcut mà không tạo implicit dependencies mới

### 12.1. Tách matcher và policy

Một lớp chọn join points không nên đồng thời hardcode:
- Business eligibility.
- Authorization.
- Audit sink.
- Retry type filter.
- Exception mapping.

Nếu tất cả chồng vào một wildcard, thay pattern là thay tất cả. Một thiết kế compositional dùng:
- Selection contract: **điểm nào được chọn**.
- Advice: **làm gì tại điểm đó**.
- Policy: **điều kiện nào được phép thay outcome**.
- Ordering: **khung xử lý lồng nhau ra sao**.
- Testing: **khả năng match/intercept/side effects**.

### 12.2. Pointcut composition

Một số engine hỗ trợ kết hợp điều kiện:

~~~text
BusinessBoundary
AND NOT InstrumentationHelpers
AND NOT HealthChecks
AND WithinAllowedDeploymentModule
~~~

Giả mã này cho thấy:
- Positive selector theo role.
- Negative selector loại instrumentation recursion/health checks.
- Deployment scope tránh can thiệp nhầm module.

Khi có một naming convention ổn định cho **module boundary**, điều kiện package/module có thể là một phần nhỏ của composite selector thay vì toàn bộ định nghĩa.

### 12.3. Explicit exclusion thay vì đoán theo tên

Nếu mọi class có hậu tố `Helper` đều bị loại, một business service tên `RiskHelper` có thể bị bỏ sót; nếu dùng `!startsWith("internal")`, dễ bị lệch khi team đổi naming conventions. Khi có thể, dùng typed markers/roles chính thức hoặc metadata của deployment.

### 12.4. Đặt fallback semantics khi metadata thiếu

Nếu một method mới không có annotation, nên:
- Không match và có test phát hiện thiếu coverage?
- Fail build/lint khi published boundary thiếu marker?
- Có quy tắc mặc định match theo interface?

Tùy concern. Không nên để một unannotated method âm thầm vượt policy bảo mật bắt buộc.

## 13. Scope, module và package boundary có thể là hợp đồng thật

Không phải mọi package dependency đều cần loại bỏ. Có thể một module áp chuẩn: “mọi class trong namespace `company.adapters.outbound` là outbound adapter”. Khi đó package là **architecture boundary được enforced**, không đơn thuần source layout.

### 13.1. Điều kiện để package-based policy đáng tin

1. Naming/packaging convention được tài liệu hóa.
2. CI có architecture tests/lint ngăn class sai vùng.
3. Mỗi lần move package được review như đổi behavior.
4. Matcher positive/negative rõ, tránh wildcard quá rộng.
5. Có tests trên compile/runtime artifact thực.
6. Toolchain dùng đúng classloader và module boundaries.
7. Có owner chịu trách nhiệm versioning.
8. Không dùng package như security trust boundary duy nhất.

### 13.2. Java packages và JPMS modules

Package name là không gian tên, còn module descriptors có thể kiểm soát exports/opens và reflective access. Một aspect phụ thuộc reflection vào implementation package có thể bị ảnh hưởng khi modules thay quyền mở, dù matcher theo tên vẫn nghĩ method đúng.

Nếu source/bytecode weaving cần truy cập thành viên không public, phải kiểm công cụ xử lý modules, classloaders và access restrictions thế nào. Không suy rằng regex package hợp lệ làm reflective invocation hợp lệ.

### 13.3. Tái tổ chức module có thể là thay đổi semantics

Nếu team chuyển code từ `internal` sang `public-api` vì chính sách ownership thay đổi, pointcut đáng lẽ được review. Mục tiêu là **không bị vỡ ngoài ý muốn**, chứ không ép selector cố phủ cả các boundary đã thay về nghĩa.

## 14. Annotation và interface cũng có rủi ro về độ ổn định

Một selector dựa trên annotation còn có các giới hạn:

### 14.1. Marker được đặt sai

Một developer annotate private helper thay vì published operation, dẫn đến instrumentation sai đơn vị. Cần coverage tests và documentation.

### 14.2. Marker bị copy-paste

Annotation `@Retryable` có thể bị copy vào một command non-idempotent, dẫn tới side effects nhân đôi. Đặt marker đúng không tự chứng minh policy an toàn; cần kiểm business semantics.

### 14.3. Marker chỉ ở implementation

Nếu proxy interceptor chọn bằng interface method reflection, marker trên implementation method không được tự thấy. Ngược lại, một weaver xét target execution declaration có thể không thấy annotation của interface. Cần định nghĩa **metadata lookup rule** tường minh.

### 14.4. Type hierarchy quá rộng

Một base interface được đặt marker có thể kéo toàn bộ subclasses/implementations vào pointcut khi không phải tất cả operations đều thuộc concern. Tách marker method-level hoặc specialized interface theo use case.

### 14.5. Annotation versioning

Đổi tên marker, package của annotation hoặc `@Retention` có thể là một breaking contract đối với selectors và processors. Một bước relocation cần deprecation/compatibility plan, không chỉ rename IDE.

### 14.6. Dynamic proxies và sealed interfaces

JDK proxies chỉ được tạo với interfaces hợp lệ cho runtime proxy generation; không suy mọi sealed interface đều có thể được proxy implement tùy ý. Nếu runtime class proxy không tạo được, pointcut strategy dựa proxy không giải quyết được boundary. Adapter/explicit composition hoặc cơ chế AOP khác có thể cần thiết, tùy ràng buộc Java.

## 15. Refactoring an toàn cho những pointcut hiện có

Một module lâu năm có thể đã có hàng chục selectors theo `com.old.project.impl..`. Không nhất thiết phải đổi hết sang annotations trong một commit. Có thể chuyển theo lộ trình có bằng chứng.

### Bước 1 — Inventory pointcuts

Liệt kê:
- Pointcut và advice dùng chúng.
- Positive/negative patterns.
- Những classes/methods thực được chọn.
- Concern là metrics, tracing, audit, security hay transformation.
- Những hiệu ứng khi pointcut không match hoặc match thừa.
- Engine/join-point kind/compile vs load time.

Không chỉ đếm patterns; cần hiểu **vì sao** mỗi pattern có mặt.

### Bước 2 — Xác định semantic boundary

Từ danh sách match thực:
- Chúng có cùng domain role không?
- Có một public API/interface stable tương ứng không?
- Một số helper bị match tình cờ không?
- Chúng là logical operations hay internal attempts?
- Có module boundary được governance không?

Định nghĩa một vocabulary hợp đồng trước khi thay selector.

### Bước 3 — Chọn cơ chế biểu đạt

Cân nhắc:
- Interface/role.
- Annotation.
- Named pointcut composition.
- Một module-level boundary thực sự ổn định.
- Một context predicate có validation và lifecycle.
- Instrumentation trực tiếp ở API boundary nếu tool không hỗ trợ semantic selector.

Không nhất thiết chỉ dùng một tiêu chí.

### Bước 4 — Xác lập tập match chuẩn (golden set)

Chạy kiểm thử/inspection để xác định:
- Những join points bắt buộc được match.
- Những join points tuyệt đối không được match.
- Những join points optional.
- Số occurrences kỳ vọng theo workload.
- Những direct-target/internal calls hiện bị bypass.

Golden set là một **specification**, không đơn giản snapshot matcher cũ vì matcher cũ có thể đã sai.

### Bước 5 — So sánh selectors cũ/mới

Trong một môi trường kiểm thử, so coverage:
- Mới thêm matches nào?
- Mới bỏ matches nào?
- Những thay đổi ấy có chủ đích không?
- Advice order và số side effects có đổi không?
- Dynamic binding/cflow có làm tăng overhead?

Tránh bật cả hai advices sản xuất một lúc nếu chúng gây duplicate audit/retry; nếu cần giai đoạn so sánh, dùng read-only match diagnostics.

### Bước 6 — Refactor và chạy regression tests

Thử:
- Rename implementation classes.
- Move implementation packages.
- Thay private helpers.
- Thêm implementation mới.
- Thêm overload.
- Thay generic type/covariant return.
- Direct target vs proxy paths.
- Exception/async/cancellation.
- Module/classloader build variants.

### Bước 7 — Theo dõi deployment

Sau khi phát hành, đo:
- Expected boundary invocations.
- Join point match counts.
- Tỷ lệ missing instrumentation.
- Duplicate events.
- Latency và error changes.
- Policy bypass detection theo thiết kế.

Một selector “ổn định” vẫn cần bảo trì và kiểm tra khi hệ thống phát triển.

## 16. Coverage tests: điều kiện tối thiểu để hạn chế coupling

Việc thay một wildcard bằng annotation chỉ dịch rủi ro từ “rename package” sang “quên marker”. Giải pháp là **test coverage như một hợp đồng**.

### 16.1. Positive tests

Bảo đảm advice chạy:
- Trên interface boundary chính.
- Với implementation cũ/mới.
- Sau khi implementation đổi package.
- Với subclass hoặc proxy hợp lệ.
- Trên cả normal return và exception.
- Với generic/overloaded method theo semantics đã công bố.

### 16.2. Negative tests

Bảo đảm advice **không chạy**:
- Health check/diagnostic method ngoài policy.
- Internal helper chỉ dùng trong implementation.
- Methods khác tên nhưng cùng package.
- Object methods `equals`, `hashCode`, `toString` nếu không thuộc concern.
- Một newly added public helper chưa được đánh dấu.
- Method ở tenant/module không được phép.

### 16.3. Test refactor giả lập

Một contract test có thể tạo hai implementations cùng stable interface nhưng tên class khác nhau, giống demo Java. Với AOP engine thật, có thể tạo test fixtures trong hai packages/module khác nhau và xác nhận selector matched set không đổi.

### 16.4. Test thực sự kích hoạt, không chỉ tính biểu thức

Một metadata matcher có thể trả true cho method, nhưng proxy chưa được tạo/đăng ký hoặc call path đi trực tiếp target. Integration test cần **gọi qua đúng runtime boundary** và assert advice event thực sự được emit.

### 16.5. Test kiểu lỗi, không chỉ số lần log

Nếu logging advice throw trong failure path, nó có thể che lỗi target. Nếu around advice retry làm external command chạy lại, code có thể có đúng match count nhưng sai domain contract. Kiểm cả **result, exception, side effects và order**.

## 17. Runtime discovery, bridge/synthetic và compiler-generated code

### 17.1. Reflection nhận những declarations nào?

`Class.getMethods()` trả public methods gồm inherited public methods. `getDeclaredMethods()` trả methods được khai báo trực tiếp trong class, không bao gồm inherited. Hai API không trả cùng tập.

Một runtime matcher sử dụng một API nhưng tài liệu pointcut mô tả API khác sẽ khó debug. Khi tạo matcher riêng, cần hiểu chính xác metadata source và method identity.

### 17.2. Bridge methods

Generics và covariant overriding có thể sinh bridge methods. `Method.isBridge()` và `Method.isSynthetic()` hỗ trợ kiểm tra metadata khi dùng reflection; nhưng việc loại/gộp bridge methods phải đúng mục tiêu.

Không viết một rule “bỏ tất cả synthetic methods” mà chưa hiểu engine cần thấy chúng để preserve dispatch.

### 17.3. Lambda/generated types

Tên class của lambda, generated proxy, anonymous class hoặc code generation có thể không ổn định/được công bố. Dùng regular expression trên tên runtime classes như một business boundary rất dễ giòn. Quan tâm đến role/interface/metadata ở boundary, không hardcode generated class name.

### 17.4. Build artifact thay source view

Pointcut matching tại bytecode có thể phản ánh compiled descriptors khác source-level generic type names. Nếu tiêu chí phụ thuộc generic parameterization, cần chọn công cụ/metadata hỗ trợ và test hiện thực, không giả định JVM runtime giữ đầy đủ generic type semantics trong mọi dispatch.

## 18. Aspect ordering: giảm coupling ở selector chưa đủ

Một operation có thể đồng thời được chọn bởi:
- Authorization.
- Cache.
- Retry.
- Metrics.
- Trace.
- Audit.

Nếu trừu tượng hóa pointcut khiến chúng cùng match ở một boundary mới, **thứ tự** có thể thay đổi kết quả:

~~~text
Auth(Cache(Target))
versus
Cache(Auth(Target))
~~~

Với một cache short-circuit, authorization nằm bên trong có thể bị bypass nếu cache trả thẳng. Ngược lại, `Metrics(Retry(Target))` và `Retry(Metrics(Target))` đo logical call và per-attempt khác nhau.

Đó là **hệ quả hành vi**, không chỉ chuyện hiệu suất.

### 18.1. Stable matcher không đảm bảo stable ordering

Một selector có thể không đổi sau refactor nhưng aspect registration/precedence có thể thay khi thêm module, đổi build hoặc thay classloader. Khai ordering contract một cách tường minh theo engine và test effective chain.

### 18.2. Overmatching nguy hiểm hơn missing metrics trong một số policy

Nếu một pointcut mở rộng đột ngột chọn mọi methods trong `*.service.*`, một retry aspect có thể lặp thao tác ghi dữ liệu; một logging aspect có thể xuất secrets; một transaction aspect có thể mở/đóng resource sai scope.

Vì vậy cần negative coverage mạnh đặc biệt cho advices **thay outcome hoặc side effects**.

### 18.3. Security cần trusted enforcement

Một permission aspect hoạt động tốt trên proxy có thể không bảo vệ direct calls. Dù selector dựa annotation ổn định, nó không chứng minh mọi entry path đi qua trusted boundary. Authorization cần được thiết kế như một invariant bảo mật, không chỉ như một naming convention.

## 19. Performance: pattern matching và metadata lookup

Một pointcut rộng có thể tăng số join points được instrument, tạo overhead cho:
- Advice invocation.
- Reflection/metadata resolution.
- Context/binding allocation.
- Tracing/metric events.
- Lock contention/aggregation.
- Log I/O và serializing args/results.
- Class loading/weaving work.

### 19.1. Không đoán chi phí chỉ từ loại selector

“Annotation matching luôn chậm hơn package matching” hoặc ngược lại không phải kết luận tổng quát: nhiều engines resolve selectors ở compile/load time hoặc cache metadata. Hiệu năng phụ thuộc pointcut model, caching, JIT, số joins thực và advice body.

### 19.2. Chi phí chính thường nằm ở hành vi advice

Một advice ghi JSON của mọi arguments vào disk có thể tốn nhiều hơn so metadata matcher. Một selector quá rộng có thể khiến logging khối lượng lớn, nhiều secrets hoặc metrics cardinality cao. Tối ưu hóa nên bắt đầu bằng **đúng phạm vi**, rồi đo CPU/allocation/latency.

### 19.3. Cache metadata có rủi ro lifecycle

Nếu tự tạo `Map<Method,Descriptor>`, có thể giữ references tới classes/classloaders lâu hơn khi hot reload/plugin unload. Chọn registry owner/eviction/weak association thích hợp, không biến tối ưu metadata thành memory leak.

### 19.4. Semantic boundary giúp giảm noise

Chọn đúng một public operation thay vì mười internal helpers thường làm traces rõ nghĩa hơn, giảm event volume và giảm rủi ro nhầm metric per-attempt với per-request. Nhưng nếu cần low-level profiling, internal join points vẫn có giá trị khi được bảo trì theo module.

## 20. Ma trận quyết định: package, signature, interface hay annotation?

| Tình huống | Cơ chế nghiêng về | Điều cần kiểm |
| --- | --- | --- |
| Public business API ổn định | Interface/role boundary. | Proxy/weaving coverage, method semantics. |
| Nhiều types không chung hierarchy nhưng cùng concern | Marker annotation hoặc named selection. | Governance/retention/lookup. |
| Internal storage attempts được module owner công bố | Một named internal boundary/signature. | Refactor tests, owner/version. |
| Chỉ chọn operations trong một layer được enforce | Package/module plus architecture checks. | Rename/move review và exclusions. |
| Không thể sửa third-party source | Adapter/instrumentation ở boundary sở hữu. | API availability, deployment/classloader. |
| Privacy/security enforcement bắt buộc | Trusted entrypoint/domain boundary. | Direct calls, bypass, authorization tests. |
| Generated/proxy implementation tên runtime thay đổi | Interface/contract metadata. | Không dựa generated class name. |
| Generic methods bị bridge/erasure | Stable logical method identity. | Synthetic/bridge behavior engine. |
| Async task completion metric | Async completion hook/policy. | Không nhầm method return với task end. |
| Debug profiling tạm theo private helper | Selector nội bộ có vòng đời ngắn. | Không quảng bá thành production contract. |

**Không có một chiến lược thắng mọi ô.** Khi lựa chọn, luôn viết rõ **selector quản trị nghĩa gì**, **ai chịu trách nhiệm bảo trì**, và **cách kiểm thử drift**.

## 21. Lộ trình kiến trúc hóa một module AOP tái sử dụng

### 21.1. Tầng vocabulary

Định nghĩa một số khái niệm ổn định:
- Logical business operation.
- External dependency attempt.
- Auditable mutation.
- Retryable idempotent read.

Các khái niệm này nên được document kèm examples và anti-examples.

### 21.2. Tầng binding contract

Chọn cách biểu diễn:
- Interface method declaration.
- Typed annotation.
- Explicit API wrapper.
- Engine-specific named pointcut.
- Stable module/package boundary (khi được enforce).

Không để business concern phải biết implementation package từng team.

### 21.3. Tầng advice độc lập

Advice nhận context có type/contract phù hợp, không nên hardcode:
- Package prefix của caller.
- Concrete service class.
- Private helper name.
- Generated proxy class name.
- Một thứ tự tự phát giữa các aspects.

Một observer nên trả nguyên result/error trừ khi tài liệu có chính sách transformation. State per-invocation nên giữ local, shared metrics dùng concurrent primitives đúng semantics.

### 21.4. Tầng integration test

Chạy test matrix trên nhiều implementations, packages và refactor fixtures. Có snapshot về những operations matched nhưng tránh snapshot mọi chi tiết generated bytecode không ổn định.

### 21.5. Tầng vận hành

Theo dõi coverage/drift, instrumentation failures, performance và security policy. Khi một interface được thay bằng API version mới, review migration cùng aspects chứ không giả định wildcard sẽ “tự bắt”.

## 22. Các lỗi phổ biến và cách sửa

**“Pointcut match được tất cả methods trong package `impl`, vậy là đủ.”** Không nếu package là chi tiết tổ chức và thay đổi theo refactor. Chọn semantic boundary hoặc enforce package architecture.

**“Đổi tên helper là refactor không thể ảnh hưởng behavior.”** Có thể ảnh hưởng behavior của aspect nếu selector bám tên helper. Viết refactor regression tests.

**“Annotation đã đặt ở interface nên reflection trên implementation luôn thấy.”** Sai về Java method annotation inheritance. Kiểm lookup site.

**“Một interface marker chắc chắn đồng nghĩa method được intercept.”** Không. Proxy creation, weaver scope, call path và join-point kind đều quan trọng.

**“Chỉ cần đổi pointcut sang public methods là ổn.”** Không. Public có thể bao helper, overload hoặc method có semantics khác.

**“Matcher theo method name không thay khi thêm overload.”** Không; thêm overload có thể làm matcher match thêm method.

**“Generic type xuất hiện đầy đủ trong runtime method descriptor.”** Java có erasure và bridge methods; phải xem metadata source/engine.

**“Một pointcut trừu tượng hóa sẽ không còn coupling.”** Không nếu bên trong vẫn là hardcoded package.

**“Thêm annotation chỉ ảnh hưởng logging.”** Có thể ảnh hưởng nhiều advices nếu cùng marker dùng cho retry/audit/security. Tách policy vocabulary.

**“Callback async fail giống method invocation throw.”** Không. Method có thể return stage bình thường và stage fail về sau.

**“Metrics count luôn là success count.”** Không nếu tăng counter trước `proceed()`; đó có thể là attempted invocation count.

**“Đặt authorization trên một proxy nghĩa là mọi method gốc được bảo vệ.”** Không nếu có direct-target/self-invocation bypass.

**“Tăng wildcard scope chỉ khiến hệ thống đo được nhiều hơn.”** Có thể kích hoạt side effects như retries, masking hoặc resource handling trên operations không phù hợp.

**“Class name generated proxy là API bền vững.”** Không. Tránh matching theo generated names.

**“Một test pass sau rename có nghĩa mọi đường đều có instrumentation.”** Không. Cần coverage dương/âm, failure/async/direct calls và integration artifact.

## 23. Bài tập vận dụng kèm đáp án

### Câu 1 — Package refactor

Aspect đo mọi method trong `billing.impl`. Team chuyển implementation sang `billing.engine` nhưng API `BillingPort` giữ nguyên. Vì sao metrics biến mất?

**Đáp án:** Matcher phụ thuộc package path, không phụ thuộc semantic boundary. Chuyển selection sang stable interface/role hoặc có named selector được governance và test trên package rename.

### Câu 2 — Internal helper rename

Một pointcut match `saveInternal`, method bị inline vào `save`. Business behavior không đổi nhưng audit không chạy. Hướng cải thiện?

**Đáp án:** Đặt audit ở operation boundary thật sự (ví dụ public commit/event) hoặc tạo explicit contract cho storage attempt; không dựa internal helper tồn tại mãi.

### Câu 3 — Annotation trên interface

`Gateway.execute` có annotation, implementation override không khai annotation. Java reflection trên implementation method có tự thấy annotation interface không?

**Đáp án:** Không mặc định. Trong demo, handler xét interface `Method` do proxy nhận nên thấy marker. Engine khác phải có metadata lookup rõ.

### Câu 4 — Overload

`process(String)` được đo. Team thêm `process(Request)`; pointcut chỉ match name `process`. Rủi ro?

**Đáp án:** Nó có thể match thêm một operation không thuộc policy hoặc đo hai lần khi overload này gọi overload kia. Test đúng từng signature/role.

### Câu 5 — Bridge methods

Một class generic override method tạo bridge method. Có thể log method twice không?

**Đáp án:** Có thể phụ thuộc engine/matcher. Kiểm sự hiện diện của bridge/synthetic methods và join-point semantics, không giả định một method source chỉ cho một event trong mọi model.

### Câu 6 — Direct target

Một test chỉ gọi service qua proxy thấy advice chạy. Caller khác giữ target gốc, gọi trực tiếp không có advice. Điểm sai ở đâu?

**Đáp án:** Interception coverage/boundary, không phải tên package. Nếu policy bắt buộc, phải kiểm soát đường truy cập ở trusted boundary hoặc dùng cơ chế phù hợp.

### Câu 7 — Retry marker

Một developer copy marker retry sang method ghi tiền không idempotent. Marker-based selector có làm nó an toàn không?

**Đáp án:** Không. Marker chỉ chọn join point; idempotency và allowed failure conditions là domain policy cần được review/test.

### Câu 8 — Package là kiến trúc

Một project enforce mọi outbound adapters trong `app.outbound`, có architecture tests. Có phải pointcut package luôn xấu?

**Đáp án:** Không. Khi package là contract được quản trị, chọn theo package có thể hợp lý. Vẫn cần monitor moves, exclusions và tool scope.

### Câu 9 — Async success

`submitAsync()` trả future pending. Around advice báo success ngay sau `proceed()` return. Nó đã đo đúng task completion chưa?

**Đáp án:** Chưa. Nó chỉ quan sát method return-handle; phải hook terminal outcome nếu metric là task success.

### Câu 10 — Shared named pointcut

Trace, audit và retry đều dùng một named pointcut `OperationBoundary`. Team mở rộng selector để thêm query method. Rủi ro?

**Đáp án:** Cả ba concerns có thể cùng được áp, kể cả retry/audit không mong muốn. Phân tách selection vocabulary hoặc policy predicates và test negative cases.

### Câu 11 — Refactor generic API

API đổi `load(String)` thành `load(Key)`, selector hardcode `String` mất match. Có phải luôn cần giữ `String` để AOP chạy?

**Đáp án:** Không. Pointcut nên thay theo published contract, hoặc chọn role/marker được quản trị. Không giữ API kém type-safe chỉ vì selector cũ.

### Câu 12 — Security và marker

Một method cần authorization nhưng quên `@Protected`. Có thể coi “không match” là cho phép không?

**Đáp án:** Không mặc định; trusted authorization boundary phải bảo vệ invariant. Có thể fail build/lint khi published operations thiếu policy metadata và có integration tests cho bypass paths.

### Câu 13 — Generated class name

Aspect match tên class bắt đầu bằng một prefix do proxy generator tạo. Sau nâng JDK, tên thay. Kết luận?

**Đáp án:** Generated class naming không phải semantic contract. Chọn interface/API boundary hoặc tool-provided metadata ổn định.

### Câu 14 — Metric logical/attempt

Một operation retry ba lần, `Metrics` đặt trong retry. Count=3 có đúng không?

**Đáp án:** Có nếu metric là **attempts**. Sai nếu dashboard gắn nhãn **logical operations**. Thiết kế pointcut và aspect order theo đơn vị đo.

## 24. Checklist thiết kế và review pointcut bền vững

1. **Mục tiêu:** Concern thực sự muốn chọn logical boundary nào?
2. **Abstraction:** Có interface/role/annotation được công bố không?
3. **Ownership:** Ai có quyền đổi contract selector?
4. **Package:** Nếu dùng package matcher, package có phải architecture boundary được enforce không?
5. **Signature:** Có hardcode method/parameter types nội bộ dễ refactor không?
6. **Overloads:** Thêm method cùng tên có làm selector match thừa không?
7. **Generics:** Bridge/synthetic/covariant behavior đã được xét chưa?
8. **Join-point kind:** Call/execution/proxy method invocation loại nào được engine hỗ trợ?
9. **Visibility:** Private/static/final methods có intercept được theo mechanism không?
10. **Metadata:** Annotation nằm trên interface, implementation hay wrapper? Lookup rule là gì?
11. **Retention:** Marker có tồn tại ở compile/load/runtime phase cần thiết không?
12. **Named selector:** Có thể gom selection logic để tái sử dụng mà vẫn giữ semantic contract không?
13. **Positive coverage:** Các operations bắt buộc được chọn chưa?
14. **Negative coverage:** Health/internal helpers/object methods đã được loại đúng chưa?
15. **Direct paths:** Direct target và self-invocation có bypass không?
16. **Ordering:** Retry/cache/security/metrics/audit có thứ tự đúng không?
17. **Errors:** Advice có bảo toàn exception/result không?
18. **Side effects:** Selector mở rộng có nhân số lần target chạy ngoài ý định không?
19. **Async:** Return-handle và task completion có được phân biệt không?
20. **Security:** Policy bắt buộc có nằm ở trusted boundary không?
21. **Concurrency:** Aspect dùng shared state có thread-safe không?
22. **Performance:** Match count, logging overhead, cardinality và p99 có được đo không?
23. **Build:** Compile/weaving/configuration đúng artifact/classloader/module chưa?
24. **Refactor tests:** Rename/move/overload/impl swap có giữ intended coverage không?
25. **Versioning:** Annotation/interface/named pointcut có deprecation/migration plan không?
26. **Documentation:** Những exceptions và rules đặc biệt có được giải thích cho contributors không?
27. **Rollback:** Nếu selector overmatches production, có cách thu hẹp/rollback an toàn không?

## Kết luận

Giới hạn phụ thuộc vào **tên gói và chữ ký nội bộ** là một yêu cầu về **trừu tượng hóa và tái sử dụng AOP**. Thay vì đặt concern vào nơi implementation tình cờ có method tên `doInternal`, hãy xác định một **ranh giới có ý nghĩa và được công bố**: interface role, marker annotation, named pointcut semantic, hoặc một module/package boundary có governance rõ. Khi implementation được đổi tên, chia helper, đổi package hoặc thêm implementation mới, pointcut nên chỉ cần thay nếu **hợp đồng thật sự đổi**, chứ không vỡ vì những refactor vô hại.

Không có kỹ thuật nào miễn phí coupling. Interface/annotation là một hợp đồng mới phải được sở hữu và kiểm thử; package patterns vẫn phù hợp nếu package chính là boundary được enforce; proxy-only interception vẫn có đường bypass; bytecode weaving vẫn chịu phạm vi build/classloader. Muốn aspect vừa **tái sử dụng**, vừa **đáng tin**, hãy kết hợp **semantic selectors + explicit ownership + positive/negative coverage tests + integration checks trên runtime thật**, và luôn giữ return/error, side effects, concurrency cùng security invariants theo hợp đồng đã công bố.
