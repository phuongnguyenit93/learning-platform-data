# ReflectionHints và mức truy cập MemberCategory

## 1. Vì sao Native Image cần ReflectionHints?

Ứng dụng Java trên JVM thường có thể dùng reflection để tìm class, constructor, method hoặc field trong lúc chạy. Ví dụ, framework có thể đọc annotation, tạo object từ tên class trong cấu hình hoặc gọi getter theo metadata. JVM có thể thực hiện các thao tác này nếu class/member tồn tại và quyền truy cập cho phép.

GraalVM Native Image thực hiện phân tích reachability tại build time theo mô hình closed-world. Công cụ không thể luôn suy ra đích reflection được chọn từ chuỗi runtime hoặc metadata động. Nếu class/member không được mô tả và không được nhận diện tự động, thành phần đó có thể không được giữ lại hoặc không được mở cho thao tác reflection trong executable.

Spring cung cấp **RuntimeHints** để khai báo trước những khả năng runtime cần thiết. Trong đó, **ReflectionHints** mô tả class và member mà ứng dụng hoặc thư viện sẽ truy cập bằng reflection. **MemberCategory** cho phép chọn mức truy cập cần thiết như constructor, method hoặc field.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, hiểu đúng ReflectionHints giúp xử lý tương thích native mà không đăng ký reflection quá rộng. Mục tiêu là giữ đúng class/member cần dùng, giảm lỗi runtime và tránh làm executable giữ lại metadata không cần thiết.

## 2. Reflection khác lời gọi Java thông thường như thế nào?

Lời gọi trực tiếp:

```java
Invoice invoice = new Invoice();
invoice.setCode("INV-001");
```

Compiler nhìn thấy kiểu `Invoice`, constructor và phương thức `setCode` trong bytecode. Reachability analysis thường có thể lần theo các lời gọi tĩnh này.

Lời gọi reflection:

```java
String className = configuration.getProperty("invoice.type");
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
Method setter = type.getMethod("setCode", String.class);
setter.invoke(instance, "INV-001");
```

Ở đây, giá trị `className` có thể chỉ được biết khi ứng dụng chạy. Native Image không thể luôn suy ra class/member nào sẽ được chọn. Nếu reflection target không được đăng ký hoặc tự nhận diện, thao tác có thể thất bại trong executable native dù bản JVM hoạt động.

Không phải mọi reflection đều cần hints. Những trường hợp có đích tĩnh, được Spring AOT hoặc thư viện hỗ trợ sẵn, có thể đã được phân tích và đăng ký tự động. Hãy thêm hints dựa trên lỗi hoặc yêu cầu reflection thực tế.

## 3. RuntimeHints và ReflectionHints nằm ở đâu?

Spring AOT cung cấp API trong package:

```java
org.springframework.aot.hint
```

Các khái niệm chính:

| API | Vai trò |
|---|---|
| `RuntimeHints` | Tập hợp các khai báo khả năng runtime như reflection, resource, proxy và serialization |
| `ReflectionHints` | Đăng ký type, constructor, method và field cần truy cập bằng reflection |
| `MemberCategory` | Nhóm quyền truy cập reflection có thể đăng ký theo class |
| `TypeReference` | Biểu diễn tham chiếu đến kiểu bằng tên/type metadata |
| `RuntimeHintsRegistrar` | Điểm mở rộng để thư viện/ứng dụng đăng ký hints trong Spring AOT |

Một registrar điển hình:

```java
public final class InvoiceRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        // Đăng ký reflection/resource/proxy cần thiết
    }
}
```

Sau đó gắn registrar với cấu hình Spring:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceConfiguration {
}
```

Spring AOT thu thập các hints trong quá trình xử lý ứng dụng. Những thông tin phù hợp được chuyển tới Native Image để phục vụ reachability analysis và tạo executable.

## 4. MemberCategory biểu diễn những quyền nào?

`MemberCategory` là enum mô tả nhóm member mà reflection cần sử dụng. Một số category thường gặp:

| Category | Ý nghĩa khái quát |
|---|---|
| `INVOKE_PUBLIC_CONSTRUCTORS` | Gọi public constructors bằng reflection |
| `INVOKE_DECLARED_CONSTRUCTORS` | Gọi constructors được khai báo trên type, bao gồm constructor không public theo khả năng hỗ trợ |
| `INVOKE_PUBLIC_METHODS` | Gọi public methods bằng reflection |
| `INVOKE_DECLARED_METHODS` | Gọi methods được khai báo trên type |
| `PUBLIC_FIELDS` | Truy cập public fields bằng reflection |
| `DECLARED_FIELDS` | Truy cập fields được khai báo trên type |
| `INTROSPECT_PUBLIC_CONSTRUCTORS` | Phân tích thông tin public constructors |
| `INTROSPECT_DECLARED_CONSTRUCTORS` | Phân tích thông tin declared constructors |
| `INTROSPECT_PUBLIC_METHODS` | Phân tích thông tin public methods |
| `INTROSPECT_DECLARED_METHODS` | Phân tích thông tin declared methods |
| `INTROSPECT_PUBLIC_FIELDS` | Phân tích thông tin public fields |
| `INTROSPECT_DECLARED_FIELDS` | Phân tích thông tin declared fields |
| `UNSAFE_ALLOCATED` | Hỗ trợ cấp phát instance theo cơ chế unsafe được Native Image hỗ trợ |

Tên và semantics chi tiết của enum cần đối chiếu với phiên bản Spring Framework đang dùng. Đặc biệt, nhóm `INTROSPECT_*` chủ yếu cho phép truy vấn metadata; nhóm `INVOKE_*` hoặc field access phục vụ thao tác member. **Có thể introspect một method mà không cần quyền invoke nó**, và ngược lại, nếu code cần cả hai thì đăng ký đúng cả hai khả năng.

Các category ở mức declared thường bao gồm member được khai báo trực tiếp trên type; không nên giả định nó tự động bao phủ mọi member kế thừa từ superclass hoặc interface trong mọi tình huống. Khi cần member cụ thể, đăng ký chính xác member đó hoặc type hierarchy phù hợp.

## 5. Đăng ký theo MemberCategory

Ví dụ một class có constructor public, method public và field được khai báo:

```java
public class Invoice {
    private String code;

    public Invoice() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

Nếu thư viện dùng reflection để gọi constructor và getter/setter, có thể đăng ký:

```java
final class InvoiceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                Invoice.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Đoạn code đăng ký public constructors và public methods của `Invoice`. Nó không cần đăng ký field vì ví dụ truy cập qua getter/setter. Nếu thư viện dùng `Field.setAccessible(true)` để truy cập trực tiếp `code`, phải khai báo field access phù hợp.

Cách này tiện khi một class có nhiều member cùng category cần dùng. Nếu chỉ cần một constructor hoặc method cụ thể, đăng ký member chính xác thường dễ review và ít quyền hơn.

## 6. Đăng ký một constructor hoặc method cụ thể

ReflectionHints cũng cho phép đăng ký executable cụ thể thay vì mở toàn bộ nhóm member.

Ví dụ constructor:

```java
hints.reflection().registerConstructor(
        Invoice.class.getDeclaredConstructor(),
        ExecutableMode.INVOKE
);
```

Ví dụ method:

```java
hints.reflection().registerMethod(
        Invoice.class.getDeclaredMethod("setCode", String.class),
        ExecutableMode.INVOKE
);
```

Cần import `java.lang.reflect.Executable` hoặc dùng enum `org.springframework.aot.hint.ExecutableMode` theo API version tương ứng. `getDeclaredConstructor` và `getDeclaredMethod` có thể ném `NoSuchMethodException`, do đó code registrar cần xử lý exception, ví dụ helper method hoặc `try/catch` chuyển thành lỗi build rõ ràng.

Ví dụ đầy đủ hơn:

```java
final class InvoiceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        try {
            hints.reflection().registerConstructor(
                    Invoice.class.getDeclaredConstructor(),
                    ExecutableMode.INVOKE);

            hints.reflection().registerMethod(
                    Invoice.class.getDeclaredMethod(
                            "setCode", String.class),
                    ExecutableMode.INVOKE);
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                    "Invoice reflection contract changed", ex);
        }
    }
}
```

Đăng ký method theo chữ ký chính xác: tên method, số lượng và kiểu tham số. Nếu method overload, đăng ký sai signature sẽ không bảo đảm method mà code runtime gọi được hỗ trợ.

## 7. Truy cập field: introspection và write/read

Một số thư viện serializer hoặc mapper truy cập field trực tiếp thay vì getter/setter. Ví dụ:

```java
Field codeField = Invoice.class.getDeclaredField("code");
codeField.setAccessible(true);
codeField.set(invoice, "INV-002");
```

Khi đó cần đăng ký field access phù hợp. Với category:

```java
hints.reflection().registerType(
        Invoice.class,
        MemberCategory.DECLARED_FIELDS
);
```

Nếu chỉ cần field cụ thể, dùng API đăng ký field tương ứng của phiên bản Spring Framework, ví dụ:

```java
hints.reflection().registerField(
        Invoice.class.getDeclaredField("code"));
```

Cần xử lý `NoSuchFieldException` trong registrar. Việc đăng ký field không tự động cho phép mọi method reflection trên class; constructor/method cần được khai báo riêng khi sử dụng.

**Phân biệt:**

- Introspection: truy vấn tên, kiểu, modifier hoặc metadata của field.
- Read/write: lấy hoặc thay đổi giá trị field bằng reflection.
- Invocation: gọi method/constructor.

Chỉ đăng ký quyền tương ứng với hành vi thư viện thực sự cần. Đừng mở toàn bộ declared fields và methods nếu chỉ một field cụ thể được dùng.

## 8. Public và declared member khác nhau ra sao?

Trong Java reflection:

- Public members có thể được kế thừa từ superclass hoặc interface.
- Declared members là những member khai báo trực tiếp trong một class/interface, gồm cả private/protected/package-private theo quy tắc reflection.
- `getMethods()` và `getFields()` khác với `getDeclaredMethods()` và `getDeclaredFields()`.

Ví dụ:

```java
class BaseEntity {
    public void validate() {}
    protected String id;
}

class Invoice extends BaseEntity {
    private String code;
    public void submit() {}
}
```

Với `Invoice.class.getMethods()`, reflection có thể thấy `submit()` và `validate()` kế thừa. Với `getDeclaredMethods()`, chỉ những method khai báo trực tiếp trên `Invoice` mới được trả về. Tương tự, `getDeclaredFields()` của Invoice thấy `code`, không thấy field `id` của superclass.

Vì thế, khi đăng ký `INVOKE_DECLARED_METHODS` cho `Invoice`, không nên mặc định rằng method `validate()` của `BaseEntity` cũng đã được đăng ký. Nếu code truy cập member kế thừa, xem xét đăng ký type/member trên superclass tương ứng.

## 9. Introspect không đồng nghĩa invoke

Một framework có thể chỉ đọc metadata để tạo schema hoặc binding, không gọi method/constructor bằng reflection. Ví dụ nó cần liệt kê annotation và parameter type của public method:

```java
for (Method method : Invoice.class.getMethods()) {
    System.out.println(method.getName());
}
```

Trong trường hợp này, category introspection phù hợp hơn category invocation nếu không có thao tác gọi method bằng reflection. Ngược lại, nếu framework gọi `method.invoke(...)`, phải đăng ký quyền invoke tương ứng.

| Hành vi trong code | Nhóm hint cần xem xét |
|---|---|
| Liệt kê method và đọc metadata | `INTROSPECT_*` phù hợp |
| Gọi method qua `Method.invoke` | `INVOKE_*` hoặc đăng ký method cụ thể với `INVOKE` |
| Liệt kê constructors | Constructor introspection |
| Tạo instance bằng `Constructor.newInstance` | Constructor invocation |
| Liệt kê field metadata | Field introspection |
| Đọc/ghi field bằng reflection | Field access category hoặc đăng ký field cụ thể |

API và mức hỗ trợ cụ thể phụ thuộc Spring/GraalVM version. Hãy dùng Native Image tracing/diagnostic output và test để xác nhận; không chỉ suy ra từ tên enum.

## 10. Kết hợp MemberCategory với @ImportRuntimeHints

Một registrar cần được Spring AOT phát hiện. Cách gắn phổ biến:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceHints.class)
class InvoiceConfiguration {

    @Bean
    Invoice invoice() {
        return new Invoice();
    }
}
```

`@ImportRuntimeHints` liên kết registrar với configuration class. Spring AOT gọi registrar trong quá trình thu thập runtime hints. Nếu registrar không được import/đăng ký hoặc configuration class không thuộc context AOT, hint có thể không được tạo.

Một lựa chọn khác là đăng ký registrar theo cơ chế mở rộng mà Spring hỗ trợ cho thư viện. Với ứng dụng thông thường, annotation giúp nhìn rõ cấu hình nào chịu trách nhiệm cung cấp hints.

Không gọi `registerHints` tùy tiện lúc runtime rồi kỳ vọng Native Image cập nhật executable. Hints phải có mặt trong giai đoạn AOT/build trước khi compiler tạo binary.

## 11. Kiểm thử hints bằng RuntimeHintsPredicates

Spring cung cấp tiện ích kiểm tra một RuntimeHints có đăng ký đúng reflection entry hay không. Ví dụ:

```java
@Test
void invoiceConstructorIsRegistered() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceHints().registerHints(hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onConstructor(Invoice.class.getDeclaredConstructor())
            .test(hints)).isTrue();
}
```

Ví dụ cần Spring test support/AssertJ và import các API tương ứng như `RuntimeHints`, `RuntimeHintsPredicates`, JUnit. Predicate cụ thể có thể khác theo phiên bản Spring. Ý tưởng là kiểm tra metadata được đăng ký trong unit test trước khi chạy full native build.

Có thể kiểm tra method hoặc type tương tự. Unit test xác minh registrar khai báo đúng, nhưng **không chứng minh** toàn bộ executable đã chứa metadata và chạy đúng. Vẫn cần native integration test hoặc chạy binary thật để bao phủ code path.

## 12. ReflectionHints và metadata GraalVM

Spring RuntimeHints là API cấp ứng dụng/framework, còn GraalVM Native Image sử dụng reachability metadata để thực hiện phân tích. Spring AOT chuyển các hints đã thu thập sang dạng mà Native Image hiểu.

Một số thư viện phân phối metadata sẵn (reachability metadata) để người dùng không phải tự khai báo từng member. Khi nâng version dependency, metadata có thể được cập nhật theo thư viện. Không nên thêm duplicate hints theo cảm tính; trước tiên kiểm tra thư viện đã hỗ trợ native và metadata đã được nhận diện chưa.

Nếu cần khai báo trực tiếp metadata GraalVM, định dạng/cơ chế được hỗ trợ phụ thuộc GraalVM version và Native Build Tools. Trong dự án Spring Boot, ưu tiên RuntimeHints khi có thể để cấu hình gắn với lifecycle Spring AOT và dễ kiểm thử.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassNotFoundException` trong reflection | Class không reachable hoặc tên class runtime không đúng | Xác định target và đăng ký type/metadata |
| `NoSuchMethodException` | Constructor/method signature không tồn tại hoặc khác với hint | Đối chiếu đúng parameter types và member |
| `IllegalAccessException` | Member không được mở cho thao tác cần thiết | Đăng ký category/member phù hợp và kiểm tra Java access |
| Reflection metadata có nhưng method vẫn không gọi được | Chỉ đăng ký introspection, chưa đăng ký invocation | Thêm `INVOKE` tương ứng |
| Field serializer lỗi | Chỉ đăng ký method/constructor nhưng thư viện truy cập field trực tiếp | Thêm field hint phù hợp |
| Member kế thừa không được hỗ trợ | Chỉ đăng ký declared members của subclass | Đăng ký member trên superclass/interface cần thiết |
| Hints không có trong native output | Registrar chưa được Spring AOT phát hiện | Kiểm tra `@ImportRuntimeHints` và AOT context |
| JVM chạy nhưng native lỗi | JVM reflection linh hoạt hơn closed-world analysis | Native integration test, kiểm tra hints/metadata |

## 14. Bài thực hành: đăng ký tối thiểu cho một DTO

**Bối cảnh:** ứng dụng có thư viện cũ dùng reflection để tạo `Invoice`, gọi `setCode` và đọc `getCode`.

**Bước 1 — Tạo DTO.** Khai báo constructor public và getter/setter.

**Bước 2 — Xác định hành vi reflection.** Đọc code thư viện hoặc stack trace để biết chính xác constructor, method hay field nào được gọi.

**Bước 3 — Viết registrar.** Nếu chỉ gọi constructor, đăng ký constructor; nếu gọi setter/getter, đăng ký đúng methods hoặc public methods category.

**Bước 4 — Import hints.** Gắn registrar qua `@ImportRuntimeHints` vào configuration thuộc ApplicationContext.

**Bước 5 — Viết unit test.** Dùng RuntimeHintsPredicates để xác nhận entry cần thiết có mặt.

**Bước 6 — Build native.** Chạy Spring AOT và GraalVM Native Image, quan sát log nếu compiler cảnh báo reflection metadata.

**Bước 7 — Chạy binary.** Gọi endpoint đi qua thư viện cũ và kiểm tra cả trường hợp thành công/lỗi.

Tiêu chí hoàn thành: chỉ đăng ký những member thực sự được dùng; test hints pass; native executable chạy đúng đường đi reflection; không dựa vào việc JVM test pass để kết luận native đã tương thích.

## 15. Nguyên tắc chọn MemberCategory

Khi quyết định category, hãy trả lời theo thứ tự:

1. Ứng dụng cần **đọc metadata** hay thực hiện hành động?
2. Nếu thực hiện hành động, đó là tạo instance, gọi method hay đọc/ghi field?
3. Member là public hay declared/non-public?
4. Member nằm trên class nào, có kế thừa từ superclass không?
5. Có thể đăng ký một member cụ thể thay vì cả nhóm không?
6. Thư viện đã cung cấp reachability metadata hoặc Spring hints chưa?

Một hint rộng có thể làm nhiều member được giữ lại và tăng metadata cần thiết. Một hint quá hẹp có thể khiến lỗi chỉ xuất hiện ở đường đi hiếm gặp. Chọn phạm vi nhỏ nhất đáp ứng contract thực tế, sau đó xác nhận bằng test native.

## 16. Kết luận

**ReflectionHints** giúp Spring AOT mô tả những class/member cần truy cập bằng reflection trong executable Native Image. **MemberCategory** phân biệt các nhóm thao tác như introspection, constructor/method invocation và field access. Hiểu rõ khác biệt giữa public và declared members, member kế thừa, cũng như giữa introspect và invoke giúp đăng ký đúng quyền cần thiết.

Trong ứng dụng Spring Boot Native Image, hãy ưu tiên RuntimeHints/RuntimeHintsRegistrar, gắn registrar vào Spring AOT, kiểm thử metadata bằng unit test và xác minh bằng native executable. Cách làm này giảm lỗi reflection runtime, giữ cấu hình có chủ đích và tránh mở rộng metadata vượt quá nhu cầu thực tế.
