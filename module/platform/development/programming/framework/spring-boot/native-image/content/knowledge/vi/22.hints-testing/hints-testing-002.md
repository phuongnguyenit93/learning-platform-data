# Kiểm thử reflection cho constructor, method và field thực sự dùng

## 1. Vì sao phải kiểm thử từng thao tác reflection?

GraalVM Native Image phân tích ứng dụng tại build time. Các constructor, method hoặc field được truy cập qua Java Reflection có thể không được suy ra đầy đủ từ call graph tĩnh. Spring Runtime Hints mô tả những thành viên mà ứng dụng cần truy cập khi chạy native.

Một test chỉ xác nhận class đã có reflection hint là chưa đủ. Code có thể gọi một constructor cụ thể, invoke một method có chữ ký cụ thể, hoặc đọc và ghi một field riêng. Test cần xác nhận đúng thành viên và đúng kiểu truy cập.

Bài này thuộc chương **Kiểm thử hints** của module **SPRING_BOOT_NATIVE_IMAGE**. Mục tiêu là kiểm tra constructor, method và field mà code thực sự dùng; phân biệt introspection với invocation; phát hiện hint thiếu, sai chữ ký hoặc quá rộng; và xác minh kết quả qua Spring AOT cùng native executable.

## 2. Bắt đầu từ code thực hiện reflection

Giả sử thư viện cần tạo CredentialEnvelope, gọi method chuẩn hóa token và đọc/ghi field token:

```java
package com.example.security;

public class CredentialEnvelope {

    private String token;

    public CredentialEnvelope() {
    }

    public CredentialEnvelope(String token) {
        this.token = token;
    }

    public String normalize(String prefix) {
        return prefix + token.trim();
    }

    public String normalize(String prefix, boolean uppercase) {
        String value = prefix + token.trim();
        return uppercase ? value.toUpperCase() : value;
    }
}
```

Thành phần sử dụng reflection:

```java
package com.example.security;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class CredentialInspector {

    public CredentialEnvelope create(String token) throws Exception {
        Constructor<CredentialEnvelope> constructor =
            CredentialEnvelope.class.getDeclaredConstructor(String.class);
        return constructor.newInstance(token);
    }

    public String normalize(CredentialEnvelope target, String prefix)
            throws Exception {
        Method method = CredentialEnvelope.class.getDeclaredMethod(
            "normalize", String.class
        );
        return (String) method.invoke(target, prefix);
    }

    public String readToken(CredentialEnvelope target) throws Exception {
        Field field = CredentialEnvelope.class.getDeclaredField("token");
        field.setAccessible(true);
        return (String) field.get(target);
    }

    public void replaceToken(CredentialEnvelope target, String value)
            throws Exception {
        Field field = CredentialEnvelope.class.getDeclaredField("token");
        field.setAccessible(true);
        field.set(target, value);
    }
}
```

Tập yêu cầu reflection rút ra từ code:

| Thao tác | Thành viên | Chế độ |
| --- | --- | --- |
| Lấy constructor với tham số String và gọi newInstance | CredentialEnvelope(String) | Invoke |
| Lấy normalize với một tham số String và gọi invoke | normalize(String) | Invoke |
| Lấy field token và gọi get | token | Field access |
| Lấy field token và gọi set | token | Field access để ghi |

Method overload normalize(String, boolean) không được gọi trong ví dụ, nên không cần đăng ký chỉ vì nó cùng tên với method đang dùng.

## 3. Phân biệt introspection và invocation

Spring biểu diễn yêu cầu reflection của constructor và method bằng ExecutableMode:

- INTROSPECT: cần truy vấn metadata, ví dụ lấy thông tin method hoặc constructor.
- INVOKE: cần gọi executable, ví dụ Constructor.newInstance() hoặc Method.invoke().

Ví dụ chỉ introspect một method:

```java
Method method = CredentialEnvelope.class.getDeclaredMethod(
    "normalize", String.class
);

String methodName = method.getName();
Class<?>[] parameterTypes = method.getParameterTypes();
```

Nếu code chỉ truy vấn metadata mà không gọi method, hint INTROSPECT có thể đáp ứng nhu cầu. Nếu code gọi method.invoke(...), cần hint INVOKE. Nếu code vừa truy vấn metadata vừa invoke, hãy mô tả đúng cả hai hoạt động.

Không dùng assertion introspection để thay thế assertion invocation khi code thực sự gọi reflection.

## 4. Đăng ký chính xác constructor, method và field

Một RuntimeHintsRegistrar có thể mô tả ba thành viên được dùng trong ví dụ:

```java
package com.example.security;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class CredentialReflectionHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        try {
            Constructor<CredentialEnvelope> constructor =
                CredentialEnvelope.class.getDeclaredConstructor(String.class);

            Method normalize = CredentialEnvelope.class.getDeclaredMethod(
                "normalize", String.class
            );

            Field token = CredentialEnvelope.class.getDeclaredField("token");

            hints.reflection().registerConstructor(
                constructor, ExecutableMode.INVOKE
            );
            hints.reflection().registerMethod(
                normalize, ExecutableMode.INVOKE
            );
            hints.reflection().registerField(token);
        }
        catch (NoSuchMethodException | NoSuchFieldException ex) {
            throw new IllegalStateException(
                "Reflection member definition changed", ex
            );
        }
    }
}
```

Cách đăng ký này có các đặc điểm:

1. Chọn constructor bằng đúng parameter type String.
2. Chọn method overload bằng đúng parameter type String.
3. Chọn field theo tên token.
4. Dùng INVOKE vì constructor và method được gọi thực sự.
5. Đăng ký field vì code đọc và ghi nó bằng reflection.

Với Spring Framework 6.2.x, registerField(Field) đăng ký field cần truy cập reflection. Cùng một field hint được dùng cho các thao tác Field.get() và Field.set() mà code thực hiện. Hãy chỉ đăng ký field mà thư viện thật sự truy cập; không mở toàn bộ declared fields nếu chỉ cần một vài trường.

### 4.1. Khi nào dùng MemberCategory?

Spring cũng hỗ trợ đăng ký theo nhóm thành viên, ví dụ INVOKE_PUBLIC_CONSTRUCTORS, INVOKE_DECLARED_METHODS hoặc DECLARED_FIELDS:

```java
hints.reflection().registerType(
    CredentialEnvelope.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
    MemberCategory.INVOKE_DECLARED_METHODS,
    MemberCategory.DECLARED_FIELDS
);
```

Đây là phạm vi rộng hơn so với đăng ký một constructor và một method cụ thể. Chỉ dùng nhóm member khi code thật sự cần nhóm đó. Không thêm INVOKE_DECLARED_METHODS chỉ để sửa lỗi của một method duy nhất.

## 5. Kiểm thử constructor bằng RuntimeHintsPredicates

RuntimeHintsPredicates.reflection() có thể kiểm tra một constructor cụ thể. Hãy lấy chính constructor mà code sử dụng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Constructor;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

class CredentialReflectionHintsTests {

    @Test
    void registersConstructorThatIsActuallyInvoked() throws Exception {
        RuntimeHints hints = new RuntimeHints();

        new CredentialReflectionHints().registerHints(
            hints, getClass().getClassLoader()
        );

        Constructor<CredentialEnvelope> constructor =
            CredentialEnvelope.class.getDeclaredConstructor(String.class);

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onConstructor(constructor)
                .invoke()
        ).accepts(hints);
    }
}
```

onConstructor(constructor) chọn đúng constructor; invoke() yêu cầu hint cho phép invocation. Nếu registrar chỉ đăng ký introspection, assertion này phải thất bại.

Có thể kiểm tra constructor khác không được dùng:

```java
Constructor<CredentialEnvelope> noArg =
    CredentialEnvelope.class.getDeclaredConstructor();

assertThat(
    RuntimeHintsPredicates.reflection()
        .onConstructor(noArg)
        .invoke()
).rejects(hints);
```

Ví dụ negative assertion này giả định class có constructor không tham số. Nếu không có, hãy chọn một constructor có thật nhưng không nằm trong tập operation của thư viện.

## 6. Kiểm thử method, kể cả khi có overload

Predicate onMethod(Class, String) phù hợp khi tên method xác định duy nhất một method. Với overload, truyền Method object lấy bằng getDeclaredMethod(...) để tránh test nhầm chữ ký:

```java
@Test
void registersOnlyTheNormalizeOverloadUsedByTheLibrary()
        throws Exception {

    RuntimeHints hints = new RuntimeHints();
    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    Method usedMethod = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class
    );

    Method unusedOverload = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class, boolean.class
    );

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(usedMethod)
            .invoke()
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(unusedOverload)
            .invoke()
    ).rejects(hints);
}
```

Method object mang theo declaring class và parameter types, nên test phân biệt được normalize(String) với normalize(String, boolean).

### 6.1. Kiểm tra introspection riêng

Nếu một thành phần chỉ cần tra cứu method metadata, kiểm tra mode tương ứng:

```java
assertThat(
    RuntimeHintsPredicates.reflection()
        .onMethod(usedMethod)
        .introspect()
).accepts(hints);
```

Không dùng assertion này thay cho invoke() khi code gọi Method.invoke().

## 7. Kiểm thử field access

Với Spring Framework 6.2.x, có thể kiểm tra field bằng onField(Class, String):

```java
@Test
void registersTokenField() {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onField(CredentialEnvelope.class, "token")
    ).accepts(hints);
}
```

Predicate này xác nhận field được đăng ký. Có thể kiểm tra danh sách field hint trực tiếp trên TypeHint:

```java
import org.springframework.aot.hint.TypeHint;

@Test
void tokenFieldIsRegistered() {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    TypeHint typeHint =
        hints.reflection().getTypeHint(CredentialEnvelope.class);

    assertThat(typeHint).isNotNull();

    assertThat(typeHint.fields()
        .anyMatch(field -> field.getName().equals("token")))
        .isTrue();
}
```

Trong ví dụ này, cùng field token được đọc bằng Field.get() và ghi bằng Field.set(). Test kiểm tra field hint có mặt; integration test ở phần sau xác minh cả hai thao tác thực sự chạy được trên native executable.

### 7.1. Field được kế thừa

Nếu field được khai báo trong superclass, hint phải gắn với class thực sự khai báo field đó:

```java
Field inheritedField =
    BaseCredential.class.getDeclaredField("tenantId");

hints.reflection().registerField(
    inheritedField
);
```

Không giả định subclass sở hữu mọi field mà đối tượng có thể truy cập. Field kế thừa vẫn có declaring class riêng.

## 8. Kiểm tra hint chính xác thay vì mở toàn bộ type

Predicate thành công chứng minh operation được hỗ trợ, nhưng chưa tự chứng minh registrar tối thiểu. Nếu registrar dùng MemberCategory.INVOKE_DECLARED_METHODS, predicate của một method không dùng có thể vẫn trả về true vì nhóm hint bao phủ method đó.

Khi muốn giữ phạm vi reflection hẹp:

- Kiểm tra constructor cụ thể.
- Kiểm tra method cụ thể bằng Method object.
- Kiểm tra field cụ thể.
- Kiểm tra field cụ thể thay vì đăng ký toàn bộ fields của type.
- Kiểm tra TypeHint.getMemberCategories() để phát hiện nhóm member rộng ngoài dự kiến.
- Có negative assertion cho một member thật nhưng không được sử dụng.

Ví dụ xác nhận type không mở toàn bộ declared methods:

```java
TypeHint typeHint =
    hints.reflection().getTypeHint(CredentialEnvelope.class);

assertThat(typeHint).isNotNull();
assertThat(typeHint.getMemberCategories())
    .doesNotContain(MemberCategory.INVOKE_DECLARED_METHODS);
```

Nếu dự án chủ ý mở cả nhóm method, assertion này không phù hợp. Khi đó, ghi rõ lý do và kiểm thử rằng phạm vi được mở là một phần của hợp đồng runtime.

Không biến negative assertion thành quy tắc cứng cho mọi thư viện. Có trường hợp serializer hoặc framework cần nhiều member. Điều cần kiểm soát là sự tương xứng giữa phạm vi hint và hành vi thực tế.

## 9. Kiểm thử registrar với RuntimeHintsPredicates

Một test có thể kiểm tra cả ba loại member trong cùng phương thức:

```java
@Test
void registersOnlyTheReflectionOperationsUsed() throws Exception {
    RuntimeHints hints = new RuntimeHints();

    new CredentialReflectionHints().registerHints(
        hints, getClass().getClassLoader()
    );

    Constructor<CredentialEnvelope> constructor =
        CredentialEnvelope.class.getDeclaredConstructor(String.class);

    Method method = CredentialEnvelope.class.getDeclaredMethod(
        "normalize", String.class
    );

    Field field = CredentialEnvelope.class.getDeclaredField("token");

    assertThat(RuntimeHintsPredicates.reflection()
        .onConstructor(constructor).invoke()).accepts(hints);

    assertThat(RuntimeHintsPredicates.reflection()
        .onMethod(method).invoke()).accepts(hints);

    assertThat(RuntimeHintsPredicates.reflection()
        .onField(field)).accepts(hints);
}
```

Các predicate này kiểm tra nội dung RuntimeHints trong bộ nhớ. Chúng hữu ích để unit test registrar, nhưng không chứng minh Spring AOT đã phát hiện registrar hoặc native executable thực sự thực hiện được thao tác.

## 10. Phân biệt ba lớp kiểm thử

| Lớp kiểm thử | Điều cần chứng minh | Cách thực hiện |
| --- | --- | --- |
| Registrar unit test | Constructor/method/field hint được đóng góp đúng | Tạo RuntimeHints, gọi registrar, kiểm tra predicate |
| AOT integration test | Spring phát hiện registrar/annotation và hợp nhất hint | Chạy AOT processing trên ApplicationContext hoặc ứng dụng consumer |
| Native executable test | Operation reflection hoạt động trong binary thực tế | Build native, chạy test/endpoint thực hiện constructor, method và field access |

Một unit test có thể đạt trong khi registrar không được import vào ApplicationContext. Tương tự, AOT metadata có thể được sinh nhưng test native chưa chạm tới method overload hoặc field chỉ được dùng ở một nhánh hiếm.

Vì vậy, native test cần gọi đúng code path mà thư viện hoặc ứng dụng dự định hỗ trợ.

## 11. Chạy test trên native executable

Có thể viết integration test gọi service thực hiện reflection:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(CredentialInspector.class)
class CredentialNativeIntegrationTests {

    @Autowired
    CredentialInspector inspector;

    @Test
    void createsInvokesAndAccessesCredentialReflectively() throws Exception {
        CredentialEnvelope envelope = inspector.create("  abc  ");

        assertThat(inspector.normalize(envelope, "Bearer "))
            .isEqualTo("Bearer abc");

        assertThat(inspector.readToken(envelope))
            .isEqualTo("  abc  ");

        inspector.replaceToken(envelope, "rotated");

        assertThat(inspector.readToken(envelope))
            .isEqualTo("rotated");
    }
}
```

Test này kích hoạt constructor invocation, method invocation, field read và field write. Khi chạy native integration test, cần bảo đảm test thực sự được thực thi trong native executable hoặc test harness native tương ứng. Chạy cùng test trên JVM chỉ xác minh hành vi JVM.

Với Maven hoặc Gradle, cấu hình native test phụ thuộc Native Build Tools và phiên bản plugin. Hãy dùng task/goal native test tương ứng của dự án và kiểm tra log để xác nhận test process là native executable.

### 11.1. Kiểm tra qua HTTP

Nếu reflection được kích hoạt bởi request, hãy gửi request qua ứng dụng native thay vì chỉ gọi service trực tiếp. Cách này còn kiểm tra Spring AOT, dependency injection, HTTP message conversion và code path nghiệp vụ cùng lúc.

Đảm bảo request kích hoạt từng operation. Nếu field chỉ được ghi khi xử lý một loại event hiếm, tạo test riêng cho event đó. Không chỉ kiểm tra endpoint trả HTTP 200 mà không xác nhận kết quả field/method đúng.

## 12. Những cách kiểm thử dễ gây kết luận sai

| Test hoặc cấu hình | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| Chỉ assert onType(MyType.class) | Không chứng minh constructor/method/field cụ thể có hint | Assert từng member thực sự được dùng |
| Chỉ kiểm tra INVOKE_DECLARED_METHODS | Có thể mở mọi method dù chỉ cần một method | Dùng registerMethod với đúng Method |
| Chọn method bằng tên khi có overload | Predicate có thể không xác định duy nhất method | Lấy Method bằng parameter types |
| Chỉ assert constructor introspection | Code thực tế gọi newInstance | Assert invoke() |
| Chỉ assert field hint tồn tại | Chưa chứng minh Field.get() và Field.set() chạy được trên native | Chạy integration test thực hiện cả đọc và ghi field |
| Chỉ test registrar trực tiếp | Chưa chứng minh AOT engine tìm thấy registrar | Thêm AOT integration test |
| Chỉ chạy JVM test | JVM có thể truy cập reflection mà native chưa được đăng ký | Chạy native executable test |
| Dùng setAccessible(true) trong test nhưng không kiểm tra hint | Test JVM không phản ánh native metadata | Kiểm tra field hint và native behavior |
| Chỉ chạy một nhánh request | Có thể bỏ sót member được dùng trong nhánh khác | Bao phủ từng operation và subtype thực tế |

## 13. Khác biệt API predicate giữa Spring Framework 6 và 7

Trong Spring Framework 6.x, các API thường dùng trong bài này là:

```java
RuntimeHintsPredicates.reflection().onConstructor(constructor).invoke();
RuntimeHintsPredicates.reflection().onMethod(method).invoke();
RuntimeHintsPredicates.reflection().onField(type, "fieldName");
```

Spring Framework 7.0 đánh dấu một số predicate cũ là deprecated để chuyển sang tên diễn tả operation rõ hơn:

| Spring Framework 6.x | Spring Framework 7.x |
| --- | --- |
| onConstructor(constructor).invoke() | onConstructorInvocation(constructor) |
| onMethod(method).invoke() | onMethodInvocation(method) |
| onField(type, "name") | onFieldAccess(type, "name") |

Khi viết test, dùng API theo Spring Framework baseline mà dự án đang compile. Không copy test dùng API 7.x vào dự án Spring 6.x hoặc ngược lại mà chưa kiểm tra dependency.

## 14. Bài thực hành: kiểm thử reflection hint tối thiểu

**Bối cảnh:** Thư viện CredentialInspector dùng reflection để tạo CredentialEnvelope(String), gọi normalize(String) và đọc/ghi field token.

**Các bước:**

1. Tạo model CredentialEnvelope với constructor có tham số, hai overload method và field private.
2. Viết code reflection gọi đúng một constructor, một overload method, đọc field và ghi field.
3. Viết registrar chỉ đăng ký các thành viên đó.
4. Viết unit test dùng RuntimeHintsPredicates để kiểm tra constructor invocation.
5. Kiểm tra method invocation bằng Method object lấy với parameter type cụ thể.
6. Kiểm tra field hint bằng RuntimeHintsPredicates và TypeHint.fields().
7. Thêm negative assertion cho overload method không được gọi và constructor không được sử dụng.
8. Kiểm tra type không bị mở rộng sang toàn bộ declared methods nếu không cần.
9. Chạy AOT processing và xác nhận registrar được phát hiện.
10. Build native executable và chạy test kích hoạt đủ constructor, method, field read và field write.

**Tiêu chí đạt:**

- Test chọn đúng constructor theo parameter types.
- Test phân biệt được method overload.
- Test field xác nhận đúng field được đăng ký; native integration test xác nhận cả đọc và ghi nếu code cần hai thao tác.
- INTROSPECT và INVOKE được dùng đúng mục đích.
- Negative assertion phát hiện hint cho member ngoài yêu cầu.
- AOT integration test xác nhận registrar được phát hiện.
- Native executable thực hiện được mọi operation reflection được hỗ trợ.

## 15. Tổng kết

Kiểm thử reflection hints cần bắt đầu từ thao tác thực tế của code. Dùng Constructor và Method object lấy bằng chữ ký đầy đủ để kiểm tra đúng overload; dùng predicate field và TypeHint.fields() để xác nhận field được đăng ký. Phân biệt INTROSPECT với INVOKE, đồng thời tránh mở toàn bộ member category nếu ứng dụng chỉ cần một vài thành viên.

RuntimeHintsPredicates là công cụ unit test cho registrar. Để chứng minh ứng dụng native hoạt động, vẫn cần AOT integration test và native executable test kích hoạt chính xác constructor, method và field mà ứng dụng sử dụng.

