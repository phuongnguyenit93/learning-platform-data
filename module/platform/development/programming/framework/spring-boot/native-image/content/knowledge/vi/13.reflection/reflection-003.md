# Đăng ký kiểu và thành viên cần truy cập qua RuntimeHints

## 1. Vì sao phải đăng ký reflection?

Java reflection cho phép chương trình khám phá và thao tác với class, constructor, method, field khi chạy. Spring Framework và nhiều thư viện sử dụng reflection để tạo object, binding dữ liệu, serialize JSON, đọc annotation hoặc gọi thành phần được chọn từ cấu hình.

Trên JVM, các lớp có trong classpath thường có thể được nạp và truy cập bằng reflection khi quyền truy cập cho phép. GraalVM Native Image lại phân tích reachability ở build time theo mô hình closed-world. Nếu đích reflection chỉ được xác định từ tên chuỗi, metadata bên ngoài hoặc một nhánh ít được gọi, công cụ có thể không nhận ra class/member cần giữ lại.

Spring AOT cung cấp **RuntimeHints** để khai báo trước các khả năng runtime. Với reflection, API `hints.reflection()` cho phép đăng ký type và member mà ứng dụng sẽ truy cập. Những khai báo này được Spring AOT thu thập và chuyển thành metadata phù hợp cho Native Image.

Bài học này hướng dẫn xác định đúng class/member, đăng ký bằng RuntimeHints, gắn registrar vào ApplicationContext và kiểm thử trên executable native. Mục tiêu là cung cấp đủ metadata cho đường đi thực tế mà không mở reflection rộng hơn nhu cầu.

## 2. ReflectionHints và RuntimeHintsRegistrar

Các API chính nằm trong package `org.springframework.aot.hint`:

| API | Trách nhiệm |
|---|---|
| `RuntimeHints` | Tập hợp khai báo reflection, resource, proxy, serialization và JNI |
| `ReflectionHints` | Đăng ký class và member được truy cập qua Java reflection |
| `MemberCategory` | Chọn nhóm constructor, method hoặc field cần hỗ trợ |
| `ExecutableMode` | Mô tả cách sử dụng executable member, ví dụ invoke hoặc introspect |
| `RuntimeHintsRegistrar` | Điểm mở rộng để khai báo hints trong Spring AOT |
| `@ImportRuntimeHints` | Liên kết registrar với cấu hình Spring |

Một registrar tối thiểu:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class ApplicationReflectionHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        // Đăng ký type/member cần reflection ở đây
    }
}
```

Để Spring AOT phát hiện registrar, gắn nó vào cấu hình thuộc ApplicationContext:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationReflectionHints.class)
class NativeConfiguration {
}
```

Registrar chạy trong giai đoạn chuẩn bị AOT. Tạo một đối tượng RuntimeHints trong code nghiệp vụ lúc runtime không làm thay đổi metadata của native executable đã biên dịch.

## 3. Xác định chính xác reflection contract trước khi khai báo

Trước khi viết hints, cần đọc đường đi sử dụng reflection và lập danh sách member cụ thể. Ví dụ một thư viện cũ nhận tên class từ cấu hình rồi tạo đối tượng:

```java
String className = settings.getProperty("invoice.handler");
Class<?> type = Class.forName(className);
Object handler = type.getDeclaredConstructor().newInstance();

Method method = type.getDeclaredMethod("handle", Invoice.class);
method.invoke(handler, invoice);
```

Contract cần hỗ trợ gồm:

- Class đích được nạp bằng tên.
- Constructor không tham số được gọi bằng reflection.
- Method `handle(Invoice)` được gọi bằng reflection.
- Nếu thư viện truy cập field trực tiếp, field đó cũng cần được xem xét riêng.

Đừng đăng ký tất cả member của package chỉ vì chưa biết chính xác thư viện dùng gì. Xác định các class có thể được chọn từ cấu hình, chữ ký constructor/method và cách thư viện truy cập chúng. Nếu class name có thể là nhiều giá trị, cần đăng ký từng class trong tập được hỗ trợ hoặc thiết kế registry tĩnh để tập đích được biết rõ.

## 4. Đăng ký một type và constructor

Giả sử ứng dụng có class:

```java
package com.example.invoice;

public final class InvoiceHandler {

    public InvoiceHandler() {
    }

    public void handle(Invoice invoice) {
        // Xử lý hóa đơn
    }
}
```

Nếu code chỉ cần gọi constructor public bằng reflection, đăng ký category tương ứng:

```java
hints.reflection().registerType(
        InvoiceHandler.class,
        MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
);
```

Nếu cần gọi constructor được khai báo nhưng không public, xem xét `INVOKE_DECLARED_CONSTRUCTORS` và quyền truy cập Java thực tế. Category declared không tự động có nghĩa mọi hạn chế module/access của Java đều bị bỏ qua.

Nếu chỉ cần một constructor cụ thể, có thể đăng ký executable member thay vì cả nhóm:

```java
hints.reflection().registerConstructor(
        InvoiceHandler.class.getDeclaredConstructor(),
        ExecutableMode.INVOKE
);
```

Cách cụ thể này cần xử lý `NoSuchMethodException`. Nó giúp tài liệu hóa rõ constructor mà thư viện sử dụng và tránh giữ các constructor không cần thiết.

## 5. Đăng ký method cần gọi

Nếu thư viện gọi `handle(Invoice)` bằng `Method.invoke`, có thể đăng ký method cụ thể:

```java
hints.reflection().registerMethod(
        InvoiceHandler.class.getDeclaredMethod(
                "handle", Invoice.class),
        ExecutableMode.INVOKE
);
```

Đăng ký theo method cụ thể yêu cầu đúng tên và đúng kiểu tham số. Nếu method overload, mỗi signature là một member riêng. Nếu code dùng method kế thừa từ superclass, cần xác định member nằm trên type nào và đăng ký phù hợp; `getDeclaredMethod` chỉ tìm method được khai báo trực tiếp trên class.

Khi nhiều public method trên class cần gọi reflectively, có thể dùng:

```java
hints.reflection().registerType(
        InvoiceHandler.class,
        MemberCategory.INVOKE_PUBLIC_METHODS
);
```

Chọn giữa category và member cụ thể theo contract: category tiện khi thực sự cần nhiều member cùng nhóm; đăng ký cụ thể dễ review khi chỉ dùng một vài method.

## 6. Đăng ký field

Một số thư viện mapper hoặc serializer truy cập field trực tiếp thay vì getter/setter. Ví dụ:

```java
Field code = Invoice.class.getDeclaredField("code");
code.setAccessible(true);
code.set(invoice, "INV-2026-01");
```

Nếu cần truy cập field được khai báo trên class, có thể dùng category:

```java
hints.reflection().registerType(
        Invoice.class,
        MemberCategory.DECLARED_FIELDS
);
```

Hoặc đăng ký field cụ thể:

```java
hints.reflection().registerField(
        Invoice.class.getDeclaredField("code"));
```

Đăng ký field không đồng nghĩa constructor và method cũng được phép gọi. Phải phân biệt:
- Introspection: đọc metadata tên/kiểu/modifier.
- Field access: đọc hoặc ghi giá trị.
- Invocation: gọi method hoặc constructor.

Nếu thư viện chỉ dùng getter/setter, không cần mở field chỉ vì field đó tồn tại.

## 7. Public member và declared member

Java reflection cung cấp các API khác nhau:

| API reflection | Phạm vi |
|---|---|
| `getMethods()` | Public methods của class và các method public kế thừa |
| `getDeclaredMethods()` | Method khai báo trực tiếp trên class, gồm cả non-public |
| `getFields()` | Public fields, có thể gồm field kế thừa |
| `getDeclaredFields()` | Field khai báo trực tiếp trên class |
| `getConstructor(...)` | Public constructor có signature tương ứng |
| `getDeclaredConstructor(...)` | Constructor được khai báo trên class, gồm cả non-public |

Ví dụ:

```java
class BaseHandler {
    public void validate() {}
}

class InvoiceHandler extends BaseHandler {
    private String code;

    public void handle(Invoice invoice) {}
}
```

`InvoiceHandler.class.getMethods()` có thể thấy `validate()` kế thừa, còn `getDeclaredMethods()` chỉ trả các method khai báo trên `InvoiceHandler`. Do đó, đăng ký `INVOKE_DECLARED_METHODS` cho subclass không nên được hiểu là tự động đăng ký mọi method của superclass.

Nếu code gọi `validate()` qua reflection, hãy kiểm tra type/member thực tế được tra cứu và đăng ký trên `BaseHandler` khi cần.

## 8. Introspection và invocation là hai yêu cầu khác nhau

Một framework có thể chỉ liệt kê method để đọc annotation, tên và kiểu tham số; framework khác có thể gọi method bằng reflection. Hai hành vi này đòi hỏi metadata khác nhau.

| Hành vi | Hints cần xem xét |
|---|---|
| Đọc metadata method | `INTROSPECT_PUBLIC_METHODS` hoặc `INTROSPECT_DECLARED_METHODS` |
| Gọi method | `INVOKE_PUBLIC_METHODS` hoặc `INVOKE_DECLARED_METHODS` |
| Đọc metadata constructor | Category introspection constructor |
| Tạo object bằng reflection | Category invocation constructor hoặc đăng ký constructor cụ thể |
| Đọc/ghi field | Field category hoặc đăng ký field cụ thể |

Không phải cứ đăng ký introspection là method có thể được gọi. Ngược lại, đăng ký invocation không nên được hiểu là cho phép mọi dạng introspection. Nếu code vừa đọc metadata vừa invoke, đăng ký cả khả năng cần thiết.

Tên enum và semantics phải được kiểm tra theo phiên bản Spring Framework trong dự án. Khi sử dụng category rộng, xem xét liệu type hierarchy hoặc member kế thừa có cần hints riêng hay không.

## 9. Registrar hoàn chỉnh cho một class

Ví dụ dưới đây đăng ký constructor và method cụ thể:

```java
package com.example.invoice;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class InvoiceHandlerHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        try {
            hints.reflection().registerConstructor(
                    InvoiceHandler.class.getDeclaredConstructor(),
                    ExecutableMode.INVOKE
            );

            hints.reflection().registerMethod(
                    InvoiceHandler.class.getDeclaredMethod(
                            "handle", Invoice.class),
                    ExecutableMode.INVOKE
            );
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                    "InvoiceHandler reflection contract changed", ex);
        }
    }
}
```

Đăng ký registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceHandlerHints.class)
class InvoiceNativeConfiguration {
}
```

Nếu constructor/method bị đổi tên hoặc signature trong quá trình refactor, registrar sẽ thất bại ngay ở bước AOT thay vì chờ đến một request hiếm gặp ở production. Đây là lợi ích quan trọng của việc khai báo reflection contract tập trung.

## 10. Đăng ký nhiều implementation có thể được chọn

Nếu cấu hình runtime cho phép chọn một trong nhiều handler, tập class cần được xác định khi build:

```java
final class HandlerHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        registerHandler(hints, StandardInvoiceHandler.class);
        registerHandler(hints, PriorityInvoiceHandler.class);
    }

    private void registerHandler(
            RuntimeHints hints, Class<?> type) {
        hints.reflection().registerType(
                type,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Ví dụ giả định cả hai handler đều có constructor và public methods cần dùng. Trong ứng dụng thật, hãy đăng ký đúng member trên từng class. Nếu implementation được nạp từ plugin Java mới sau khi native image phát hành, việc thêm JAR vào classpath không làm binary tự biên dịch class mới; cần build lại image hoặc thay đổi kiến trúc plugin.

## 11. RuntimeHintsPredicates: kiểm thử metadata đã khai báo

Có thể viết unit test xác nhận registrar thêm hint mong đợi:

```java
@Test
void registersInvoiceHandlerConstructor() throws Exception {
    RuntimeHints hints = new RuntimeHints();

    new InvoiceHandlerHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onConstructor(
                    InvoiceHandler.class.getDeclaredConstructor())
            .test(hints))
            .isTrue();
}
```

Test cần JUnit, AssertJ và Spring AOT hint test support. Predicate API có thể khác giữa các version; kiểm tra package/Javadoc dự án. Có thể viết thêm predicate cho method hoặc field cụ thể.

Unit test chứng minh registrar tạo đúng metadata trong đối tượng RuntimeHints. Nó chưa chứng minh registrar đã được Spring AOT phát hiện hoặc native executable thực sự chạy được. Vì vậy cần kiểm tra cả hai lớp:

1. Unit test registrar.
2. AOT build xác nhận registrar được thu thập.
3. Native integration test hoặc chạy executable thực tế trên đường đi reflection.

## 12. Khi nào dùng RuntimeHintsRegistrar, khi nào dùng metadata thư viện?

Một số dependency đã cung cấp reachability metadata hoặc Spring RuntimeHints riêng. Trước khi viết hints trùng lặp, kiểm tra thư viện đang dùng có hỗ trợ GraalVM Native Image hay chưa.

Ưu tiên theo thứ tự:

- Dùng hints do Spring Framework/Spring Boot hoặc thư viện dependency cung cấp.
- Dùng `RuntimeHintsRegistrar` cho reflection contract riêng của ứng dụng.
- Dùng metadata GraalVM trực tiếp khi cần khai báo mà abstraction Spring không biểu diễn đủ, theo định dạng được phiên bản Native Image hỗ trợ.

Không chỉnh generated metadata trực tiếp sau khi AOT. Hãy sửa registrar hoặc nguồn metadata, rồi build lại để thay đổi được áp dụng có thể tái lập.

## 13. Chẩn đoán lỗi reflection trong native executable

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassNotFoundException` | Class được chọn động không có trong image | Đăng ký type/metadata, kiểm tra tên class |
| `NoSuchMethodException` | Sai signature hoặc method/constructor không được mô tả | Đối chiếu tên, parameter types và registrar |
| `IllegalAccessException` | Member không có quyền truy cập phù hợp | Kiểm tra public/declared và access hints |
| Method có thể tìm thấy nhưng không invoke được | Chỉ đăng ký introspection | Bổ sung invocation hint |
| Field mapper lỗi | Thư viện truy cập field trực tiếp nhưng chỉ đăng ký method | Đăng ký field access phù hợp |
| Chỉ lỗi với implementation phụ | Class phụ không được đăng ký | Bổ sung type/member cho mọi lựa chọn hợp lệ |
| JVM chạy, native lỗi | Reflection target không được reachability analysis nhận diện | Kiểm tra runtime hints và test executable |

Không phải mọi lỗi reflection đều do thiếu hints. Tên class sai, classloader khác, module access, bug thư viện hoặc thay đổi signature cũng có thể gây lỗi. Đọc exception và xác định member thực sự được truy cập trước khi mở rộng metadata.

## 14. Quy trình thực hành: đăng ký reflection cho handler động

**Bối cảnh:** một ứng dụng Spring Boot có cấu hình chọn handler theo tên implementation. Thư viện legacy tạo handler và gọi method bằng reflection.

**Bước 1 — Xác định tập handler.** Liệt kê tất cả class hợp lệ và constructor/method mà thư viện sử dụng.

**Bước 2 — Viết RuntimeHintsRegistrar.** Đăng ký constructor và method cần thiết cho từng class; dùng category khi nhiều member cùng nhóm thực sự cần thiết.

**Bước 3 — Import registrar.** Gắn `@ImportRuntimeHints` vào configuration thuộc ApplicationContext.

**Bước 4 — Viết unit test.** Dùng RuntimeHintsPredicates xác nhận constructor/method có trong RuntimeHints.

**Bước 5 — Chạy Spring AOT và native build.** Quan sát log, xác minh hints được thu thập và tạo executable.

**Bước 6 — Kiểm thử tất cả handler.** Chạy executable với từng lựa chọn cấu hình, kiểm tra kết quả và nhánh lỗi.

**Bước 7 — Ghi nhận phạm vi.** Lưu danh sách class/member, lý do cần reflection và test tương ứng để lần refactor sau có thể cập nhật metadata.

Tiêu chí hoàn thành: mọi implementation hợp lệ chạy được trên native, member được đăng ký đúng thao tác, test registrar pass và không cần mở toàn bộ reflection của package.

## 15. Kết luận

`RuntimeHints` cho phép Spring AOT khai báo class và member cần truy cập bằng reflection trước khi GraalVM Native Image biên dịch executable. Chọn đúng type, constructor, method và field; phân biệt public với declared, member kế thừa và introspection với invocation; sau đó gắn registrar vào ApplicationContext và kiểm thử metadata.

Với Spring Boot Native Image, hãy xem reflection contract như một phần của cấu hình build có thể kiểm soát. Đăng ký phạm vi nhỏ nhất đáp ứng đường đi thực tế, tận dụng metadata sẵn có của thư viện và xác minh bằng native executable. Cách làm này giúp giảm lỗi chỉ xuất hiện ở runtime và giữ cho cấu hình AOT dễ bảo trì.
