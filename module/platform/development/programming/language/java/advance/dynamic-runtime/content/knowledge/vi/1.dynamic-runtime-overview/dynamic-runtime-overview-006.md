# 1.6. Các đánh đổi về an toàn kiểu, đóng gói, hiệu năng và khả năng bảo trì

## Mục tiêu học tập

Bài này giúp bạn đánh giá khi nào nên sử dụng các cơ chế động của Java, chúng chuyển những kiểm tra nào từ compile time sang runtime, ảnh hưởng ra sao đến tính đóng gói, hiệu năng và bảo trì, cũng như cách hạn chế rủi ro khi triển khai.

Trong module `Java Advance - dynamic-runtime`, “động” có thể là đọc metadata qua reflection, tìm phương thức bằng tên, sử dụng `MethodHandle`, tạo proxy, nạp lớp hoặc sinh/biến đổi bytecode ở runtime. Các cơ chế này phục vụ DI/IoC, ORM, serializer, plugin, AOP, framework và công cụ chẩn đoán. Chúng hữu ích, nhưng không nên được chọn chỉ vì giảm vài dòng mã.

## 1. Tính động không đồng nghĩa với bỏ hệ thống kiểu

Xét ba cách liên kết lời gọi:

1. **Đa hình thông thường:** biến kiểu `PricingRule` gọi `apply(int)`, còn JVM chọn implementation thực tế khi chạy. Compiler vẫn kiểm tra rằng interface khai báo phương thức và đối số đúng kiểu.
2. **Truy cập động qua metadata:** `Class.getMethod(...)`, `Method.invoke(...)`, `MethodHandles.Lookup` hoặc handler của proxy có thể xác định thành viên/đường đi lời gọi lúc chạy. Một tên phương thức viết trong chuỗi có thể sai dù toàn bộ mã nguồn vẫn biên dịch.
3. **Nạp/liên kết mã động:** `ClassLoader`, bytecode generation/instrumentation hoặc cơ chế bytecode `invokedynamic` hỗ trợ tạo/nối hành vi lúc chạy. JVM vẫn áp dụng quy tắc class loading, bytecode verification, linking và access control.

`invokedynamic` là một chỉ thị liên kết call site ở mức bytecode, không phải tên khác của reflection. `MethodHandle` biểu diễn một lời gọi có kiểu `MethodType` xác định; nó có thể được dùng độc lập và cũng tham gia một số cơ chế liên kết động.

Điểm cần đánh giá là **ai kiểm tra hợp đồng và kiểm tra lúc nào**. Java vẫn kiểm tra kiểu khi chạy; tăng mức độ động thường khiến lỗi xuất hiện muộn hơn, khó truy dấu hơn và phụ thuộc nhiều hơn vào test/cấu hình.

## 2. So sánh nhanh các cơ chế

| Lựa chọn | Lợi ích | Giá phải trả |
| --- | --- | --- |
| Gọi trực tiếp, interface, generic, polymorphism | Hợp đồng rõ, compiler/IDE phát hiện nhiều lỗi, dễ refactor | Kiểu/hợp đồng phải được thiết kế trước |
| `ServiceLoader<T>` + SPI interface | Khám phá implementation khi chạy nhưng bên dùng vẫn giao tiếp qua kiểu `T` | Provider/config/version có thể lỗi lúc nạp |
| Reflection (`Method`, `Field`, `Constructor`) | Khám phá/call theo metadata, annotation hoặc cấu hình | Rủi ro tên chuỗi, access, ép kiểu và exception runtime |
| `MethodHandle` / `MethodType` | Kiểu lời gọi tường minh, kết hợp/adapt được; có khả năng JIT tối ưu tùy trường hợp | Lookup/call site vẫn có thể không khớp; mã phức tạp hơn |
| JDK `Proxy` | Chặn/ủy quyền lời gọi theo interface, phù hợp logging/transaction | Handler hoạt động động; khó debug, thêm tầng gọi; chỉ proxy interface |
| Class loading/bytecode generation/instrumentation | Mở rộng runtime, tăng khả năng tùy biến framework | Phức tạp về xác minh, tương thích, bộ nhớ, debug và lifecycle |

**Quy tắc thực dụng:** giữ API nghiệp vụ ở dạng có kiểu tĩnh; đặt phần discovery, reflect hay adapt tại một **boundary nhỏ, có xác minh và có thể kiểm thử**.

## 3. Đánh đổi 1 — An toàn kiểu (type safety)

### 3.1. Dời lỗi từ compiler sang runtime

Với `rule.apply(100)`, compiler kiểm tra phương thức của `PricingRule`, số lượng đối số và kiểu trả về. Nếu đổi chữ ký `apply(int)`, nơi gọi qua interface sẽ được kiểm tra lại khi biên dịch.

Với `clazz.getMethod("apply", int.class)`, chuỗi `"apply"` không được compiler liên kết đến một symbol cụ thể. Đổi tên method nhưng bỏ quên chuỗi này khiến lỗi `NoSuchMethodException` chỉ xuất hiện khi nhánh lookup được chạy.

Reflection thường có những điểm kiểm tra muộn:

- `getMethod` tìm phương thức **public**, kể cả public method kế thừa; `getDeclaredMethod` tìm method được khai báo trên chính class, kể cả non-public, nhưng không tự miễn kiểm tra quyền truy cập.
- `Method.invoke(receiver, args...)` nhận các đối số dạng object và trả về `Object`. Caller phải xét số lượng/kiểu đối số, boxing/unboxing, null và cast kết quả.
- Sai đối tượng nhận/đối số có thể ném `IllegalArgumentException`; không đủ quyền gọi có thể ném `IllegalAccessException`; ép kiểu kết quả sai có thể ném `ClassCastException`; exception do target method ném được bọc trong `InvocationTargetException`.
- Với generic, **type erasure** có thể khiến metadata/kiểu runtime không thể xác nhận đầy đủ giả định như mọi phần tử đều là `String` trong `List<String>`.

`MethodHandle` cải thiện việc mô tả chữ ký qua `MethodType`, nhưng không biến lookup động thành kiểm tra compile time. `invokeExact` yêu cầu kiểu tại call site khớp chính xác với handle và có thể ném `WrongMethodTypeException` nếu lệch; `invoke` cho phép một số chuyển đổi hợp lệ nhưng vẫn cần xác minh hợp đồng.

JDK dynamic proxy giữ kiểu interface ở phía caller, nhưng `InvocationHandler` vẫn nhận `Method` và `Object[]`. Handler có thể trả sai kiểu, chuyển tiếp exception không đúng hoặc làm thất lạc context; checked exception không khai báo trên interface có thể dẫn đến `UndeclaredThrowableException`.

### 3.2. Cách kiểm soát rủi ro kiểu

1. Công bố interface/SPI tại ranh giới nghiệp vụ; giới hạn code phản chiếu trong adapter, factory hoặc lớp infrastructure.
2. Resolve **tên, tham số, kiểu trả về, modifier và quyền truy cập** một lần, rồi kiểm tra tính hợp lệ trước khi dùng ở luồng chính.
3. Dùng `Class<T>` và `Class.cast(...)` ở điểm chuyển object động về kiểu miền, phát lỗi cấu hình rõ ràng thay cho cast rải rác.
4. Validate plugin/provider/config lúc startup khi thích hợp; phát hiện thiếu class/method sớm.
5. Test cả lỗi thiếu symbol, đổi overload/chữ ký, provider không tương thích, target ném exception và đầu vào không đúng kiểu.

**Kết luận về an toàn kiểu:** tính động không phá verifier của JVM; nó chuyển trách nhiệm chứng minh một số giả định từ compiler sang code kiểm tra, test và giám sát runtime.

## 4. Đánh đổi 2 — Đóng gói (encapsulation)

Reflection giúp thư viện ánh xạ field, đọc annotation hoặc khởi tạo object. Nhưng nếu code bên ngoài dựa vào `private field` hay private constructor, một refactor nội bộ có thể làm hỏng tích hợp dù public API không thay đổi.

Ví dụ: serializer đọc trực tiếp field `customerId` thay vì một public contract có thể thất bại nếu field được đổi tên, bỏ đi hoặc chuyển sang representation khác. Framework có lý do chính đáng để làm việc này, nhưng ứng dụng cần xem quyền truy cập sâu là **một phụ thuộc kiến trúc có chủ ý**.

### 4.1. Access control và JPMS trên Java 17+

`setAccessible(true)` không bảo đảm mở được tất cả non-public member. Khi truy cập package thuộc named module không mở phù hợp, việc yêu cầu suppress access checks có thể ném `InaccessibleObjectException`. `MethodHandles.Lookup` cũng tuân thủ quyền truy cập; `privateLookupIn` chỉ hoạt động khi đủ điều kiện truy cập và module cho phép.

Cần phân biệt:

- `exports p`: cung cấp public type/public member trong package `p` cho việc truy cập theo module rules.
- `opens p to some.module`: cho phép deep reflection vào package `p` đối với module được chỉ định; không tự biến nội bộ thành public API compile time.
- `--add-opens`: tùy chọn mở package khi chạy, có ích cho di trú/tương thích nhưng làm deployment phụ thuộc vào cấu hình JVM.

Ví dụ **mang tính minh họa cấu hình module, không phải chương trình Java độc lập**:

```java
module billing.core {
    exports com.example.billing.api;
    opens com.example.billing.model to com.example.serializer;
}
```

Ở đây package API được export, trong khi package model chỉ được mở cho serializer cụ thể. Tên module/package cần tồn tại trong dự án thật. Tránh `open module` hoặc mở rộng rãi `--add-opens ...=ALL-UNNAMED` như cách chữa mặc định khi framework không truy cập được một private member.

### 4.2. Giữ ranh giới rõ ràng

- Ưu tiên public API, constructor/factory, interface hoặc service provider contract trước khi truy cập private.
- Nếu bắt buộc deep reflection, mở đúng package/module và ghi lý do; đưa trường hợp đó vào test nâng phiên bản JDK/framework.
- Không để handler/phương thức gọi động bỏ qua invariant, validation hay authorization của miền nghiệp vụ.
- Classloader và JPMS **không phải sandbox an toàn** để chạy mã plugin không đáng tin; phải kiểm soát nguồn plugin và cách ly phù hợp.

Mở càng sâu để framework tự động hóa, khả năng thay đổi representation nội bộ mà không ảnh hưởng bên ngoài càng giảm.

## 5. Đánh đổi 3 — Hiệu năng (performance)

Không có thứ tự “interface nhanh nhất, handle thứ hai, reflection chậm nhất” đúng trong mọi hoàn cảnh. Chi phí gồm nhiều thành phần:

1. **Discovery/lookup:** nạp class, tìm method, quét annotation, kiểm tra signature, tạo handle/proxy. Nên tách khỏi đường nóng khi có thể.
2. **Invocation:** reflection có thể kèm chuyển đổi đối số/boxing, handler proxy thêm bước chuyển tiếp, handle phụ thuộc loại call site và cách dùng.
3. **JIT và warm-up:** HotSpot có thể tối ưu lời gọi ổn định theo thời gian. `MethodHandle` có khả năng được tối ưu tốt trong một số mẫu, nhưng **không mặc định nhanh hơn `Method.invoke`** khi xét mọi workload và JDK.
4. **Cấp phát/bộ nhớ:** tạo nhiều proxy/class động hoặc giữ metadata/handle trong cache có thể tăng allocation, class metadata và chi phí GC. Cache giữ tham chiếu `Class`/`ClassLoader` quá lâu có thể cản trở class unloading, nhất là hệ thống có hot reload.

Ví dụ, reflective lookup vài lần khi startup thường không quan trọng bằng truy vấn database hay network. Ngược lại, một call động trong vòng lặp xử lý hàng triệu phần tử hoặc đường xử lý p99 latency thấp đáng được profiling.

**Đo đúng cách:** dùng JMH với warm-up, fork và tiêu thụ kết quả hợp lệ cho microbenchmark; dùng profiler/metrics và dữ liệu gần production để xác nhận đường nóng, throughput, allocation, GC, p95/p99. Không dùng một vòng `System.nanoTime()` chưa warm-up để tuyên bố cơ chế nào luôn nhanh hơn.

Thường nên resolve/cache metadata khi khởi tạo, dùng typed dispatch ở đường nóng, tránh tạo proxy/class mới mỗi request. Tuy nhiên phải đặt chính sách cache theo vòng đời classloader/plugin và đo trước/sau thay đổi.

## 6. Ví dụ Java 17+ chạy được: cùng nghiệp vụ, ba cách gọi

Tạo file **`DynamicRuntimeTradeoffs.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class DynamicRuntimeTradeoffs {
    interface PricingRule {
        int apply(int amount);
    }

    public static final class FlatDiscount implements PricingRule {
        public int apply(int amount) {
            return amount - 10;
        }
    }

    public static void main(String[] args) throws Throwable {
        FlatDiscount concrete = new FlatDiscount();
        PricingRule typed = concrete;

        int typedPrice = typed.apply(100);

        Method method = FlatDiscount.class.getMethod("apply", int.class);
        int reflectivePrice = (Integer) method.invoke(concrete, 100);

        MethodHandle handle = MethodHandles.lookup().findVirtual(
                FlatDiscount.class, "apply", MethodType.methodType(int.class, int.class));
        int handlePrice = (int) handle.invokeExact(concrete, 100);

        System.out.println("typed=" + typedPrice);
        System.out.println("reflection=" + reflectivePrice);
        System.out.println("handle=" + handlePrice);

        try {
            FlatDiscount.class.getMethod("aply", int.class);
        } catch (NoSuchMethodException expected) {
            System.out.println("missing=" + expected.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 DynamicRuntimeTradeoffs.java
java DynamicRuntimeTradeoffs
```

Kết quả stdout:

```text
typed=90
reflection=90
handle=90
missing=NoSuchMethodException
```

**Giải thích từng nhánh:**

- `typed.apply(100)` là lời gọi qua interface: Java kiểm tra hợp đồng `PricingRule.apply(int)` tại compile time và chọn implementation lúc chạy.
- `getMethod("apply", int.class)` lookup qua chuỗi và `invoke(...)` trả `Object`, ở đây thực tế là `Integer` được cast/unbox. Viết nhầm tên `"aply"` chỉ phát hiện khi gọi lookup.
- `findVirtual(...)` tạo handle có chữ ký `(FlatDiscount, int) -> int`. Biểu thức `handle.invokeExact(concrete, 100)` nhận biến `concrete` có kiểu tĩnh `FlatDiscount` và trả `int` nên khớp chính xác. Sai kiểu call site có thể gây `WrongMethodTypeException`.
- Cả ba đường đều tạo kết quả `90`. **Ví dụ này minh họa hợp đồng và thời điểm lỗi, không phải benchmark.**
- `main throws Throwable` giúp demo ngắn; code production cần phân biệt lỗi lookup, access, invocation và exception từ nghiệp vụ để log/chuyển đổi phù hợp.

Thử đổi tên `apply` thành `calculate`: compiler/IDE phát hiện nơi gọi có kiểu tĩnh bị sai; các chuỗi tên trong reflection/lookup cần test hoặc kiểm tra cấu hình riêng.

## 7. Đánh đổi 4 — Khả năng bảo trì (maintainability)

Dynamic runtime giúp framework và plugin thay đổi mà không phải hard-code từng implementation. Nhưng nó có chi phí dài hạn:

- **Khó tìm phụ thuộc:** call graph, Find Usages, rename refactor và static analysis có thể bỏ sót tên class/method nằm trong string, annotation, YAML, JSON hoặc mã sinh động.
- **Khó kiểm soát version:** đổi field, constructor, overload, access modifier, module opens hoặc phiên bản dependency có thể khiến runtime mới lỗi dù compiler không phát hiện ở module gọi.
- **Debug phức tạp:** stack trace đi qua `InvocationHandler`, proxy, reflection hay bytecode sinh động; thiếu log context dễ làm lỗi khó tái hiện.
- **Test cần đủ tầng:** unit test cho hợp đồng có kiểu, integration test cho discovery, mapping, module path, nạp provider và exception propagation.
- **Vận hành phức tạp:** quản lý startup scanning, metadata cache, classloader lifecycle, JVM flags và khả năng tương thích khi nâng JDK.

Cách thiết kế dễ bảo trì là gom logic động vào một lớp adapter/registry; document tên cấu hình và cách phát lỗi; kiểm chứng lúc startup; giữ interface/DTO/domain invariant ở phía còn lại. Khi có nhiều provider, định nghĩa contract versioning và test tương thích giữa các phiên bản.

## 8. Tình huống áp dụng và quyết định hợp lý

| Nhu cầu | Ưu tiên ban đầu | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Nghiệp vụ có tập implementation biết tại compile time | Interface, generic, strategy, factory | Hợp đồng rõ, unit test |
| Plugin phát hiện ở runtime | SPI interface + `ServiceLoader` hoặc registry có kiểu | Missing provider, version, classloading và startup validation |
| ORM/serializer/DI phải đọc annotation/field | Reflection trong infrastructure adapter | Access/module, schema và ép kiểu |
| Logging, transaction, interception qua interface | Decorator/interceptor/JDK proxy | Exception propagation, phạm vi intercept và overhead |
| Lời gọi động đã resolve một lần rồi gọi thường xuyên | Cân nhắc cache `MethodHandle` sau khi đo | Exact signature, access, JIT và cache lifecycle |
| Profiler, agent, framework sinh mã | Bytecode generation/instrumentation khi thật sự cần | JVM compatibility, verification, memory, debug và nâng phiên bản |

**Ví dụ kiến trúc plugin:** thay vì để mỗi request đọc tên class từ config rồi `Class.forName` + `getMethod("apply",...)`, định nghĩa `PricingRule`, khám phá provider ở startup, kiểm tra implementation tương thích và lưu registry có kiểu. Request chỉ gọi `PricingRule.apply(...)`. Boundary vẫn động khi đăng ký plugin, còn phần lõi giữ an toàn kiểu, dễ đọc và dễ đo.

## 9. Checklist đánh giá trước khi dùng cơ chế động

1. **Nhu cầu thật:** phải khám phá cấu trúc sau khi chương trình chạy hay chỉ cần interface/strategy/decorator?
2. **Kiểu:** phần nào compiler kiểm tra? Ai chịu trách nhiệm kiểm tra tên, chữ ký, return type, null, cast và exception?
3. **Đóng gói:** dùng public contract được không? Nếu phải deep reflection, `opens` đã hẹp và rõ module đích chưa?
4. **Lỗi sớm:** thiếu class/method, sai provider/config, mismatch signature và lỗi quyền truy cập được phát hiện lúc khởi động hay request đầu tiên?
5. **Hiệu năng:** đã profiling đúng đường nóng và workload chưa? Lookup có tái sử dụng không, cache có làm giữ classloader không?
6. **Bảo trì:** phụ thuộc động có tài liệu, log context, test tích hợp và quy trình nâng JDK/framework không?
7. **Vận hành:** có chỉ số lookup/invoke failure, allocation, startup time, p95/p99 và cấu hình module opens cần thiết không?
8. **An toàn:** mã plugin/class name từ nguồn ngoài có được kiểm soát không? Dynamic adapter có giữ nguyên authorization và invariant không?

## 10. Sai lầm phổ biến

- **“Reflection xóa type safety.”** Sai: JVM vẫn có kiểu và access check; phần kiểm tra chỉ chuyển nhiều hơn sang runtime.
- **“`setAccessible(true)` mở được mọi private member.”** Sai: JPMS có thể chặn strong encapsulation.
- **“`MethodHandle` luôn nhanh hơn reflection.”** Sai: cần xét call site, JIT, warm-up, chi phí lookup và đo đạc thực tế.
- **“JDK Proxy proxy được mọi concrete class.”** Sai: JDK `Proxy` tạo proxy implement interface; proxy concrete class cần cơ chế khác với hạn chế riêng.
- **“Cache càng nhiều càng tốt.”** Sai: cache giữ `Class`/`ClassLoader` có thể giữ lại plugin cũ và tăng memory.
- **“Build thành công thì tích hợp động đúng.”** Sai: string/config/provider/module path phải được integration test và xác minh ở runtime.

## Kết luận

Khả năng động của Java đổi sự linh hoạt và mở rộng lúc chạy lấy **nhiều kiểm tra runtime hơn, phụ thuộc vào nội bộ nhiều hơn, chi phí phải đo và yêu cầu bảo trì cao hơn**. Thiết kế bền vững thường giữ hợp đồng có kiểu tĩnh trong nghiệp vụ, giới hạn phần động vào boundary rõ ràng, kiểm tra lỗi sớm và dựa vào benchmark/profiling thay cho định kiến về hiệu năng.
