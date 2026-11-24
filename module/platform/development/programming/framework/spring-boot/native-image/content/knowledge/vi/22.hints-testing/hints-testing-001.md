# RuntimeHintsPredicates để xác nhận loại truy cập đã được khai báo

Khi một thư viện Spring cần reflection, đọc resource, Java serialization hoặc tạo JDK proxy trong Native Image, nó phải khai báo các yêu cầu đó bằng **runtime hints**. Viết một `RuntimeHintsRegistrar` mới chỉ là một nửa công việc: cần có test xác nhận registrar thực sự khai báo đúng loại truy cập mà code sẽ dùng.

Spring Framework cung cấp **`RuntimeHintsPredicates`** để kiểm tra `RuntimeHints` bằng các điều kiện có ý nghĩa. Test có thể xác nhận constructor được phép gọi qua reflection, method có invocation hint, resource được đưa vào image, kiểu được đăng ký cho Java serialization hoặc tập interface đã có JDK proxy hint. Các test này chạy nhanh trên JVM, không cần biên dịch native executable.

Bài học này trình bày cách viết registrar, kiểm tra từng nhóm hint, kiểm thử việc Spring phát hiện registrar trong AOT, và mở rộng kiểm thử bằng RuntimeHints Agent. Cuối cùng, bài học phân biệt bằng chứng từ predicate với bằng chứng cần có khi chạy native image thật.

## 1. Vì sao cần kiểm thử runtime hints?

Một hint sai hoặc thiếu có thể chỉ bộc lộ khi native executable chạy một nhánh nghiệp vụ ít được sử dụng. Ví dụ:

- Constructor được khai báo để introspection nhưng code thực sự cần gọi constructor.
- Method có tên đúng nhưng signature tham số sai.
- Resource được đăng ký với pattern không khớp đường dẫn thực tế.
- JDK proxy có đủ interface nhưng thứ tự interface khác với lúc tạo proxy.
- DTO được đăng ký cho reflection binding nhưng code lại dùng Java serialization.
- Registrar có test riêng nhưng không được import hoặc không được phát hiện trong Spring AOT.

Nếu chỉ kiểm tra rằng `registerHints()` đã được gọi, test chưa chứng minh các yêu cầu cần thiết đã được khai báo. `RuntimeHintsPredicates` giúp biến yêu cầu đó thành assertion cụ thể.

~~~mermaid
flowchart TD
    A["RuntimeHintsRegistrar"] --> B["Tạo RuntimeHints"]
    B --> C["RuntimeHintsPredicates"]
    C --> D{"Các predicate đều đạt?"}
    D -->|Không| E["Sửa registrar hoặc test"]
    E --> A
    D -->|Có| F["Kiểm tra Spring AOT phát hiện registrar"]
    F --> G["Chạy native build và runtime test"]
    G --> H{"Đường đi thực tế hoạt động?"}
    H -->|Không| I["Điều tra metadata, resource hoặc code path"]
    I --> A
    H -->|Có| J["Có bằng chứng cho các luồng đã kiểm thử"]
~~~

**Predicate pass xác nhận cấu trúc hint trong đối tượng `RuntimeHints` được kiểm tra.** Nó không tự biên dịch native image, không kiểm tra mọi nhánh runtime và cũng không xác nhận file resource thực sự tồn tại trong artifact nếu test không kiểm tra riêng điều đó.

## 2. RuntimeHints và RuntimeHintsPredicates nằm ở đâu?

`RuntimeHints` thuộc Spring Framework, trong package `org.springframework.aot.hint`. Nó gom các yêu cầu dynamic access cần thiết cho ứng dụng:

| Nhóm | API đăng ký | Ý nghĩa |
|---|---|---|
| Reflection | `hints.reflection()` | Class, constructor, method và field được truy cập qua reflection |
| Resource | `hints.resources()` | File classpath và resource bundle cần có khi chạy |
| Java serialization | `hints.serialization()` | Kiểu được serialize bằng cơ chế Java Object Serialization |
| JDK proxy | `hints.proxies()` | Tập interface cần dùng với `java.lang.reflect.Proxy` |
| JNI | `hints.jni()` | Reflection access cần cho JNI |

`RuntimeHintsPredicates` nằm trong package `org.springframework.aot.hint.predicate`. API này cung cấp bốn nhóm predicate:

~~~java
RuntimeHintsPredicates.reflection()
RuntimeHintsPredicates.resource()
RuntimeHintsPredicates.serialization()
RuntimeHintsPredicates.proxies()
~~~

Các predicate kiểm tra lần lượt reflection, resource, Java serialization và JDK proxy. API `RuntimeHintsPredicates` có từ Spring Framework 6.0, vì vậy có thể sử dụng trong các ứng dụng Spring Boot 3.x trở lên đang dùng Spring Framework 6.x. Hãy để Spring Boot dependency management quản lý phiên bản Spring Framework, tránh tự ghép các module khác minor version.

Lưu ý: `RuntimeHints` có API `jni()`, nhưng `RuntimeHintsPredicates` không cung cấp một factory JNI riêng trong bộ predicate chuẩn này. Với JNI, cần kiểm tra cấu hình phù hợp và chạy test native cho đường gọi thực tế.

## 3. Tách registrar khỏi test

Nên viết registrar thành một lớp có thể khởi tạo trực tiếp trong unit test. Ví dụ ứng dụng có SDK hóa đơn cần:

- Gọi constructor `InvoicePayload(String)` qua reflection.
- Gọi method `normalize()` qua reflection.
- Đọc resource `invoice/templates/invoice-v1.json`.
- Tạo JDK proxy cho `InvoiceGateway` và `Serializable`.
- Dùng Java serialization cho `AuditEvent`.

Ví dụ các kiểu dữ liệu:

~~~java
import java.io.Serializable;
import java.util.Locale;

public final class InvoicePayload {

    private final String invoiceId;

    public InvoicePayload(String invoiceId) {
        this.invoiceId = invoiceId;
    }

    public String normalize() {
        return this.invoiceId.trim().toUpperCase(Locale.ROOT);
    }

    public String debugDump() {
        return this.invoiceId;
    }
}

public interface InvoiceGateway {
    String submit(String invoiceId);
}

public final class AuditEvent implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String invoiceId;

    public AuditEvent(String invoiceId) {
        this.invoiceId = invoiceId;
    }
}
~~~

Resource được đặt tại:

~~~text
src/main/resources/
└── invoice/
    └── templates/
        └── invoice-v1.json
~~~

Đường dẫn trong `registerPattern` và `forResource` là đường dẫn tương đối với classpath root, dùng dấu `/`. Không đưa tiền tố `src/main/resources` vào tên resource.

## 4. Đăng ký các loại hint cần thiết

Registrar minh họa:

~~~java
import java.io.Serializable;
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class InvoiceRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(InvoicePayload.class, typeHint -> {
            typeHint.withMembers(MemberCategory.INVOKE_DECLARED_CONSTRUCTORS);
            typeHint.withMethod(
                "normalize",
                List.of(),
                ExecutableMode.INVOKE
            );
        });

        hints.resources().registerPattern(
            "invoice/templates/invoice-v1.json"
        );

        hints.proxies().registerJdkProxy(
            InvoiceGateway.class,
            Serializable.class
        );

        hints.serialization().registerType(AuditEvent.class);
    }
}
~~~

Mỗi API mô tả đúng một nhu cầu:

- `ExecutableMode.INVOKE` yêu cầu khả năng gọi constructor hoặc method qua reflection.
- `registerPattern` khai báo resource classpath cần có trong image.
- `registerJdkProxy` khai báo một JDK proxy triển khai đúng tập interface.
- `serialization().registerType` dành cho Java Object Serialization.

Không nên đăng ký rộng tất cả method, field hoặc constructor chỉ để test hết lỗi. Hãy khai báo đúng loại truy cập mà code thực sự thực hiện.

## 5. Tạo RuntimeHints trong unit test

Unit test có thể gọi registrar trực tiếp để nhận một đối tượng `RuntimeHints`:

~~~java
RuntimeHints hints = new RuntimeHints();

new InvoiceRuntimeHints().registerHints(
    hints,
    getClass().getClassLoader()
);
~~~

Sau đó dùng các predicate để kiểm tra. Mẫu assertion phổ biến với AssertJ:

~~~java
assertThat(predicate).accepts(hints);
~~~

`predicate` ở đây là một `Predicate<RuntimeHints>` do Spring tạo ra. `accepts` làm test thất bại nếu đối tượng `hints` không thỏa điều kiện.

Cách làm này tách hai vấn đề: registrar tạo dữ liệu gì, và test yêu cầu loại truy cập nào. Khi test thất bại, assertion cho biết loại hint chưa được đăng ký thay vì phải đợi native executable ném lỗi lúc chạy.

## 6. Kiểm tra constructor và method reflection

`RuntimeHintsPredicates.reflection()` tạo predicate cho reflection. Có thể kiểm tra type, constructor, method hoặc field.

Ví dụ kiểm tra constructor và method có quyền invocation:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void registersReflectionInvocationHints() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    Constructor<?> constructor =
        InvoicePayload.class.getDeclaredConstructor(String.class);

    Method normalize =
        InvoicePayload.class.getDeclaredMethod("normalize");

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onConstructor(constructor)
            .invoke()
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(normalize)
            .invoke()
    ).accepts(hints);
}
~~~

Dùng `Constructor` hoặc `Method` đã tìm được giúp test xác định chính xác signature. Với method overloaded, tránh chỉ truyền class và tên method nếu có nhiều method cùng tên; API chọn theo tên đơn giản có thể báo lỗi khi không xác định được một method duy nhất.

Có thể kiểm tra một type đã được đăng ký với member category cụ thể:

~~~java
assertThat(
    RuntimeHintsPredicates.reflection()
        .onType(InvoicePayload.class)
        .withMemberCategory(MemberCategory.INVOKE_DECLARED_CONSTRUCTORS)
).accepts(hints);
~~~

Trong registrar ở mục 4, type hint đã đăng ký `INVOKE_DECLARED_CONSTRUCTORS`, nên assertion này khớp. `withMemberCategories(...)` có thể dùng khi cần xác nhận nhiều category cùng hiện diện; `withAnyMemberCategory(...)` chỉ yêu cầu ít nhất một category trong danh sách.

## 7. Phân biệt introspection và invocation

Reflection có hai nhu cầu khác nhau:

- **Introspection:** tìm hoặc đọc thông tin về member.
- **Invocation:** gọi constructor hoặc method.

`ReflectionHintsPredicates` cho phép chọn rõ chế độ kiểm tra bằng `introspect()` và `invoke()`.

Ví dụ một method chỉ cần được tìm thấy:

~~~java
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;

hints.reflection().registerType(
    InvoicePayload.class,
    typeHint -> typeHint.withMethod(
        "normalize",
        List.of(),
        ExecutableMode.INTROSPECT
    )
);
~~~

Assertion tương ứng:

~~~java
Method method = InvoicePayload.class.getDeclaredMethod("normalize");

assertThat(
    RuntimeHintsPredicates.reflection()
        .onMethod(method)
        .introspect()
).accepts(hints);
~~~

Nếu code gọi `Method.invoke()`, hãy yêu cầu `invoke()`. Một test chỉ kiểm tra introspection có thể pass dù hint không cấp đúng mode invocation mà ứng dụng cần.

Khi constructor/method được đăng ký với cả hai mode, predicate theo mode tương ứng sẽ xác nhận mode đó. Nên kiểm tra mode sát với thao tác runtime để tránh test quá dễ dãi.

## 8. Kiểm tra resource classpath

Resource hint thường bị sai vì nhầm đường dẫn source tree với đường dẫn classpath. Nếu file nằm ở `src/main/resources/invoice/templates/invoice-v1.json`, đường dẫn runtime là `invoice/templates/invoice-v1.json`.

Assertion:

~~~java
@Test
void registersInvoiceTemplate() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("invoice/templates/invoice-v1.json")
    ).accepts(hints);
}
~~~

`forResource` cũng chấp nhận đường dẫn bắt đầu bằng dấu `/`; dấu này được loại bỏ khi kiểm tra. Nếu resource nằm cùng package với một type, có overload nhận type reference và tên tương đối:

~~~java
import org.springframework.aot.hint.TypeReference;

RuntimeHintsPredicates.resource()
    .forResource(TypeReference.of(InvoicePayload.class), "invoice-v1.json");
~~~

Predicate kiểm tra rằng hint có thể bao phủ tên resource. Nó không xác nhận file đã được package vào JAR hoặc file thực sự tồn tại. Có thể kiểm tra thêm resource trên classpath của test:

~~~java
assertThat(
    getClass().getClassLoader()
        .getResource("invoice/templates/invoice-v1.json")
).isNotNull();
~~~

Hai assertion kiểm tra hai điều khác nhau: metadata đã khai báo và file có trong test classpath. Cần cả hai nếu mục tiêu là bảo đảm resource được đóng gói và được phép đưa vào native image.

## 9. Kiểm tra Java serialization

Với Java Object Serialization, dùng `RuntimeHintsPredicates.serialization().onType(...)`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void registersJavaSerializationType() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.serialization()
            .onType(AuditEvent.class)
    ).accepts(hints);
}
~~~

Kiểu được đăng ký phải triển khai `Serializable` khi dùng overload nhận `Class`. Predicate này xác nhận Java serialization hint.

**Không nhầm Java serialization với JSON data binding.** `RuntimeHintsPredicates.serialization()` không kiểm tra Jackson, JSON-B hoặc reflection binding của DTO. Với DTO dùng Jackson, thường cần kiểm tra reflection hints cho constructor, property, field hoặc record component theo cách serializer thực sự sử dụng. Có thể dùng `@RegisterReflectionForBinding` cho trường hợp Spring hỗ trợ hoặc đăng ký reflection hints rõ ràng.

## 10. Kiểm tra JDK dynamic proxy

Proxy predicate xác nhận đúng tập interface được đăng ký:

~~~java
@Test
void registersJdkProxyInterfaces() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.proxies()
            .forInterfaces(
                InvoiceGateway.class,
                Serializable.class
            )
    ).accepts(hints);
}
~~~

**Thứ tự interface có ý nghĩa.** Nếu ứng dụng tạo proxy bằng `Proxy.newProxyInstance` với danh sách interface theo thứ tự `InvoiceGateway`, `Serializable`, test cũng phải kiểm tra đúng thứ tự đó. Đảo thứ tự trong predicate có thể làm test thất bại dù tên các interface giống nhau.

Predicate này kiểm tra JDK interface proxy. Nó không chứng minh một subclass CGLIB hoặc class Byte Buddy sinh động đã được tạo.

## 11. Viết một lớp test đầy đủ cho registrar

Có thể gom các kiểm tra trên vào một test class:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.io.Serializable;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class InvoiceRuntimeHintsTests {

    private RuntimeHints hints;

    @BeforeEach
    void setUp() {
        this.hints = new RuntimeHints();
        new InvoiceRuntimeHints().registerHints(
            this.hints,
            getClass().getClassLoader()
        );
    }

    @Test
    void registersConstructorInvocation() throws Exception {
        Constructor<?> constructor =
            InvoicePayload.class.getDeclaredConstructor(String.class);

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onConstructor(constructor)
                .invoke()
        ).accepts(this.hints);
    }

    @Test
    void registersMethodInvocation() throws Exception {
        Method method =
            InvoicePayload.class.getDeclaredMethod("normalize");

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onMethod(method)
                .invoke()
        ).accepts(this.hints);
    }

    @Test
    void registersResource() {
        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("invoice/templates/invoice-v1.json")
        ).accepts(this.hints);
    }

    @Test
    void registersSerialization() {
        assertThat(
            RuntimeHintsPredicates.serialization()
                .onType(AuditEvent.class)
        ).accepts(this.hints);
    }

    @Test
    void registersProxy() {
        assertThat(
            RuntimeHintsPredicates.proxies()
                .forInterfaces(
                    InvoiceGateway.class,
                    Serializable.class
                )
        ).accepts(this.hints);
    }
}
~~~

Mỗi test có một mục tiêu. Khi một assertion thất bại, có thể khoanh vùng registrar hoặc loại hint cần sửa. Tránh gộp mọi assertion vào một test duy nhất vì lỗi đầu tiên có thể che mất các thiếu sót còn lại.

## 12. Kiểm tra registrar có được Spring AOT phát hiện không

Unit test gọi trực tiếp `registerHints` chưa chứng minh Spring sẽ phát hiện registrar trong ứng dụng. Nếu dùng `@ImportRuntimeHints`, cần kiểm tra đường tích hợp AOT.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceNativeConfiguration {
}
~~~

Có thể dùng `refreshForAotProcessing` để kiểm tra Spring xử lý configuration và thu thập hints:

~~~java
@Test
void importedRegistrarContributesHintsDuringAot() {
    RuntimeHints generatedHints = new RuntimeHints();

    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext()) {

        context.register(InvoiceNativeConfiguration.class);
        context.refreshForAotProcessing(generatedHints);
    }

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("invoice/templates/invoice-v1.json")
    ).accepts(generatedHints);
}
~~~

`refreshForAotProcessing` xử lý cấu hình cho AOT và thu thập đóng góp của registrar. Nó không khởi tạo toàn bộ bean ứng dụng như một lần refresh runtime thông thường. Test này xác nhận đường đăng ký `@ImportRuntimeHints` được phát hiện trong quá trình AOT.

Nếu registrar được đăng ký tĩnh qua `META-INF/spring/aot.factories`, cần kiểm tra file resource đó nằm trong artifact và chạy một AOT test phù hợp. Test gọi trực tiếp registrar không kiểm tra việc discovery qua file factories.

## 13. Kiểm tra cách registrar được gắn với component

Spring khuyến nghị đặt `@ImportRuntimeHints` gần component cần hint. Điều này giúp hints chỉ được đóng góp khi component tương ứng tham gia vào `BeanFactory`.

Ví dụ:

~~~java
@Component
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceClient {
    // Thực hiện các thao tác cần hints.
}
~~~

Nếu registrar được gắn vào một configuration luôn được import, hints có thể được đóng góp ngay cả khi tính năng tương ứng không thực sự được dùng. Với module tùy chọn, cân nhắc gắn registrar vào auto-configuration hoặc component của module đó.

Test nên bao gồm hai tình huống:

- Component/tính năng được bật: các hint cần thiết phải xuất hiện.
- Component/tính năng không được đăng ký: hint gắn riêng với component đó không nên xuất hiện nếu thiết kế yêu cầu phạm vi có điều kiện.

Cách tổ chức này tránh đưa metadata của mọi integration vào mọi biến thể ứng dụng.

## 14. Dùng predicate để kiểm tra registrar có khai báo quá rộng không

Predicate có thể xác nhận sự hiện diện của hint, nhưng không tự quyết định hint có quá rộng hay không. Người viết test cần đặt assertion theo đúng phạm vi thiết kế.

Ví dụ, nếu chỉ cần một method cụ thể, hãy kiểm tra method đó:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void onlyRegistersExpectedMethod() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    Method normalize =
        InvoicePayload.class.getDeclaredMethod("normalize");

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(normalize)
            .invoke()
    ).accepts(hints);

    boolean hasUnexpectedHint =
        RuntimeHintsPredicates.reflection()
            .onMethod(InvoicePayload.class, "debugDump")
            .invoke()
            .test(hints);

    assertThat(hasUnexpectedHint).isFalse();
}
~~~

Không thay bằng assertion tổng quát kiểu “type có một hint reflection nào đó” nếu yêu cầu thực tế là một method cụ thể. Ngược lại, nếu thư viện thực sự dùng toàn bộ public methods theo một contract, kiểm tra member category tương ứng có thể phù hợp hơn.

Dùng assertion phủ định khi phạm vi metadata là một yêu cầu có chủ đích. Không nên kiểm tra rằng mọi member khác đều vắng mặt nếu Spring hoặc dependency có thể hợp lệ đóng góp thêm hint.

## 15. Cách đọc lỗi khi predicate không đạt

Một predicate trả về `false` thường có nghĩa đối tượng `RuntimeHints` không chứa hint phù hợp với yêu cầu kiểm tra. Hãy phân tích theo từng nhóm:

| Assertion thất bại | Kiểm tra trước tiên |
|---|---|
| `onType(...).withMemberCategory(...)` | Registrar có đăng ký đúng type và category không? |
| `onConstructor(...).invoke()` | Constructor signature có đúng và mode có phải `INVOKE` không? |
| `onMethod(...).invoke()` | Method có đúng declaring class, tên, tham số và invocation mode không? |
| `forResource(...)` | Pattern có khớp đường dẫn classpath không? Có nhầm tên file với đường dẫn source không? |
| `serialization().onType(...)` | Kiểu có được đăng ký cho Java serialization hay chỉ có reflection binding hint? |
| `proxies().forInterfaces(...)` | Có thiếu interface hoặc sai thứ tự interface không? |
| AOT integration test không thấy hint | Registrar đã được import/discovery chưa? Configuration có được xử lý trong AOT context không? |

Với method overloaded, lấy đúng `Method` bằng `getDeclaredMethod(name, parameterTypes)` rồi truyền vào `onMethod(Method)`. Cách này tránh nhầm method có cùng tên.

Với resource pattern, kiểm tra cả tên resource thật trên classpath. Predicate chỉ xác nhận metadata có thể bao phủ đường dẫn, không xác nhận file được copy vào artifact.

## 16. RuntimeHintsPredicates và RuntimeHints Agent khác nhau thế nào?

Hai công cụ phục vụ hai cấp kiểm thử:

| Công cụ | Đầu vào | Điều nó chứng minh |
|---|---|---|
| `RuntimeHintsPredicates` | Một đối tượng `RuntimeHints` và điều kiện cụ thể | Hint được khai báo có khớp yêu cầu hay không |
| Spring `RuntimeHintsAgent` | Các lời gọi thực tế được thực thi trong test JVM | Hint được cung cấp có bao phủ những dynamic access đã ghi nhận hay không |
| GraalVM Tracing Agent | Ứng dụng/test chạy trên JVM | Thu thập cấu hình dynamic access đã xuất hiện trong các luồng được chạy |
| Native executable test | Binary native thực tế | Các đường đi được kiểm thử có hoạt động trên native runtime hay không |

`RuntimeHintsPredicates` là lựa chọn phù hợp cho unit test của registrar vì không cần agent và không cần native compilation. Khi cần phát hiện dynamic access mà người viết test chưa nghĩ tới, có thể bổ sung RuntimeHints Agent hoặc GraalVM Tracing Agent.

Không có công cụ nào tự bảo đảm mọi nhánh ứng dụng đã được bao phủ. Chất lượng kiểm thử vẫn phụ thuộc input, profile, cấu hình và luồng nghiệp vụ được chạy.

## 17. Dùng Spring RuntimeHints Agent để phát hiện lời gọi bị bỏ sót

Spring Framework cung cấp `RuntimeHintsAgent` trong module test `org.springframework:spring-core-test`. Agent ghi nhận các method invocation liên quan đến runtime hints khi test thực thi. Sau đó, test có thể so sánh các invocation đã ghi nhận với đối tượng `RuntimeHints`.

Ví dụ dependency Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework:spring-core-test")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Để sử dụng, Java agent phải được nạp vào JVM chạy test theo cấu hình build tool phù hợp. `@EnabledIfRuntimeHintsAgent` cho phép đánh dấu test chỉ chạy khi agent hiện diện.

Mẫu test theo Spring Framework:

~~~java
import java.lang.reflect.Constructor;

final class InvoiceDecoder {

    InvoicePayload decode(String invoiceId) {
        try {
            Constructor<?> constructor =
                InvoicePayload.class.getDeclaredConstructor(String.class);
            return (InvoicePayload) constructor.newInstance(invoiceId);
        }
        catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.test.agent.EnabledIfRuntimeHintsAgent;
import org.springframework.aot.test.agent.RuntimeHintsInvocations;
import org.springframework.aot.test.agent.RuntimeHintsRecorder;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfRuntimeHintsAgent
class InvoiceRuntimeHintsAgentTests {

    @Test
    void recordedInvocationsAreCoveredByHints() {
        RuntimeHints hints = new RuntimeHints();

        new InvoiceRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        RuntimeHintsInvocations invocations =
            RuntimeHintsRecorder.record(() -> {
                InvoiceDecoder decoder = new InvoiceDecoder();
                decoder.decode("sample-payload");
            });

        assertThat(invocations).match(hints);
    }
}
~~~

Ví dụ này giả định `InvoiceDecoder.decode` thực sự thực hiện các thao tác dynamic access cần kiểm tra và package chứa code đó được agent instrument. Khi cấu hình agent, hãy chọn package phù hợp; nếu code ứng dụng không nằm trong phạm vi instrument, invocation có thể không được ghi nhận.

Agent chỉ quan sát những đường đi test đã chạy. Hãy gọi đủ các serializer, resource, proxy và reflection path quan trọng để giảm vùng mù.

## 18. GraalVM Tracing Agent là công cụ bổ sung

GraalVM Tracing Agent chạy cùng ứng dụng trên JVM để ghi lại dynamic access như reflection, resource, JNI, proxy và serialization. Nó có thể xuất các file cấu hình JSON phục vụ native build.

Ví dụ:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-config \
  -jar build/libs/invoice-service.jar
~~~

Chạy các kịch bản test cần thiết, sau đó xem metadata agent sinh ra. So sánh chúng với hints do Spring AOT và thư viện cung cấp.

Tracing Agent và RuntimeHints Agent không thay thế nhau:

- RuntimeHints Agent của Spring hỗ trợ so sánh invocation đã ghi với `RuntimeHints`.
- GraalVM Tracing Agent tạo metadata cấu hình theo định dạng Native Image.
- `RuntimeHintsPredicates` kiểm tra các yêu cầu cụ thể mà test chủ động nêu ra.

Không đưa toàn bộ output agent vào production một cách máy móc. Agent có thể ghi nhận test infrastructure, nhánh không dùng trong production hoặc cấu hình phụ thuộc môi trường.

## 19. Kiểm thử native image sau khi predicate pass

Predicate pass là điều kiện cần cho registrar, nhưng chưa phải bằng chứng cuối cùng. Sau khi test hints đạt, hãy chạy AOT/native build và thực thi đúng các luồng nghiệp vụ:

1. Chạy unit test cho registrar bằng `RuntimeHintsPredicates`.
2. Chạy AOT test để xác nhận Spring phát hiện registrar.
3. Build native executable bằng cấu hình Gradle/Maven của dự án.
4. Khởi chạy executable trên đúng OS/architecture mục tiêu.
5. Gọi đường reflection, đọc resource, tạo proxy hoặc serialization thực tế.
6. Chạy lại với profile và cấu hình production được hỗ trợ.
7. Kiểm tra log missing registration và lỗi runtime.

Ví dụ Gradle với cấu hình GraalVM Native Build Tools thường dùng:

~~~bash
./gradlew processAot
./gradlew nativeCompile
~~~

Với Maven:

~~~bash
./mvnw spring-boot:process-aot
./mvnw -Pnative package
~~~

Các task/goal cụ thể phụ thuộc cấu hình plugin và Spring Boot version. Không phải mọi dự án Maven đều có profile `native` sẵn; kiểm tra cấu hình build của dự án trước khi sử dụng.

## 20. Lưu ý theo phiên bản Spring Framework

`RuntimeHintsPredicates`, `RuntimeHints` và `RuntimeHintsRegistrar` có từ Spring Framework 6.0. Các ứng dụng Spring Boot 3.x thường sử dụng các API này thông qua phiên bản Spring Framework được Boot quản lý.

Một số API kiểm thử bổ sung có thể thay đổi theo phiên bản. Đặc biệt, RuntimeHints Agent/Recorder có trạng thái và cách cấu hình khác nhau giữa các nhánh Spring Framework; tài liệu API Spring Framework 7.x đánh dấu một số API agent/recorder là deprecated để chuyển sang cơ chế báo cáo missing registration của GraalVM.

Khi dự án nâng Spring Framework hoặc GraalVM:

- Kiểm tra API `RuntimeHintsPredicates` và các predicate con trong Javadoc đúng version.
- Kiểm tra Java agent có còn được hỗ trợ theo cách đang cấu hình không.
- Kiểm tra các cờ missing-registration của GraalVM có trong toolchain mục tiêu không.
- Chạy lại unit, AOT và native integration tests.
- Không tự nâng riêng `spring-core` hoặc `spring-core-test` lệch khỏi dependency management của Spring Boot.

## 21. Quy trình kiểm thử hints trong thư viện

Một thư viện tích hợp Spring nên duy trì quy trình sau:

1. Liệt kê các dynamic access mà code thực hiện: reflection, resource, Java serialization, proxy hoặc JNI.
2. Viết `RuntimeHintsRegistrar` hoặc annotation tương ứng để khai báo nhu cầu.
3. Viết unit test gọi registrar và kiểm tra từng yêu cầu bằng `RuntimeHintsPredicates`.
4. Kiểm tra mode reflection cụ thể: introspection hay invocation.
5. Kiểm tra resource path trên classpath và proxy interface theo đúng thứ tự.
6. Viết AOT integration test để xác nhận Spring phát hiện registrar.
7. Dùng RuntimeHints Agent hoặc Tracing Agent khi cần khám phá các đường đi khó thấy.
8. Chạy native executable test cho những luồng có dynamic access.
9. Lặp lại kiểm thử khi nâng dependency, thay đổi DTO, resource, proxy hoặc cấu hình.

Một ma trận kiểm thử nhỏ giúp theo dõi phạm vi:

| Nhóm | Predicate cần dùng | Kiểm thử bổ sung |
|---|---|---|
| Constructor | `reflection().onConstructor(...).invoke()` | Tạo instance qua reflection trên native |
| Method | `reflection().onMethod(...).invoke()` | Gọi method qua reflection trên native |
| Resource | `resource().forResource(...)` | Đọc file classpath trên native |
| Java serialization | `serialization().onType(...)` | Serialize/deserialize payload thật |
| JDK proxy | `proxies().forInterfaces(...)` | Tạo proxy và gọi method trên native |
| JNI | Không có factory JNI riêng trong `RuntimeHintsPredicates` | Chạy native method và callback JNI thật |

## 22. Ghi nhớ

`RuntimeHintsPredicates` là công cụ unit test để xác nhận một đối tượng `RuntimeHints` có khai báo đúng yêu cầu reflection, resource, Java serialization và JDK proxy. Hãy kiểm tra đúng constructor/method signature, mode introspection/invocation, đường dẫn resource và thứ tự interface proxy.

Test nên gọi registrar trực tiếp để kiểm tra nội dung hint, sau đó có thêm AOT integration test để xác nhận Spring thực sự phát hiện registrar. RuntimeHints Agent và GraalVM Tracing Agent có thể giúp tìm các dynamic access chưa được nghĩ tới, nhưng chỉ quan sát các luồng đã chạy.

Cuối cùng, **predicate pass không thay thế native executable test**. Chỉ khi binary native thực sự chạy các luồng reflection, resource, proxy và serialization cần thiết trên môi trường mục tiêu, nhóm phát triển mới có bằng chứng vận hành cho những luồng đã kiểm thử.

### Tài liệu tham khảo

- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework 6.2 — RuntimeHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html
- Spring Framework 6.2 — ReflectionHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ReflectionHintsPredicates.html
- Spring Framework 6.2 — ResourceHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ResourceHintsPredicates.html
- Spring Framework 6.2 — SerializationHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/SerializationHintsPredicates.html
- Spring Framework 6.2 — ProxyHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ProxyHintsPredicates.html

API kiểm thử và cơ chế agent phụ thuộc phiên bản Spring Framework/GraalVM. Hãy pin toolchain, dùng Javadoc đúng phiên bản dự án và chạy lại native tests khi nâng cấp.
