# Đăng ký PermissionEvaluator với MethodSecurityExpressionHandler

## 1. Mục tiêu và bối cảnh

Trong Spring Security, kiểm tra vai trò bằng `hasRole('ADMIN')` hay authority bằng `hasAuthority('DOC_READ')` chỉ cho biết người dùng mang quyền ở mức tổng quát. Một hệ thống tài liệu còn phải trả lời câu hỏi chi tiết hơn: **Alice có quyền đọc tài liệu #17 hay không?** Quyết định đó thường phụ thuộc người gọi, chủ sở hữu, tenant, trạng thái và quy tắc nghiệp vụ.

`PermissionEvaluator` là một điểm mở rộng của Spring Security dành cho **biểu thức quyền theo đối tượng**. Nó cho phép `hasPermission(...)` trong `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` hoặc `@PostFilter` chuyển việc kiểm tra về mã Java của ứng dụng.

Để Spring Security Method Security thật sự dùng evaluator tùy chỉnh, bạn cần **đăng ký nó trong `MethodSecurityExpressionHandler`** — thường là `DefaultMethodSecurityExpressionHandler` — bằng `setPermissionEvaluator(...)`, đồng thời bật `@EnableMethodSecurity`. Việc chỉ khai báo một class `implements PermissionEvaluator` rồi gọi `hasPermission` trong annotation **không đủ để chứng minh** expression handler đang sử dụng class đó.

Sau bài này, bạn có thể:

1. Phân biệt giao diện `PermissionEvaluator` với `MethodSecurityExpressionHandler` và Spring AOP method-security interceptor.
2. Triển khai đúng **hai overload** của `hasPermission`: dạng đối tượng và dạng ID + loại đối tượng.
3. Cấu hình `@Bean static MethodSecurityExpressionHandler` với `setPermissionEvaluator` trong Spring Security 6.x.
4. Viết chính xác biểu thức `hasPermission(#document, 'READ')` và `hasPermission(#id, 'DOCUMENT', 'READ')`.
5. Tạo kiểm thử Spring/JUnit chứng minh evaluator được gọi, quyền được cấp/từ chối, `@PreAuthorize` chặn trước thân phương thức và `@PostAuthorize` chặn sau thân phương thức.
6. Phát hiện lỗi thông dụng: thiếu handler, sai tên tham số, thiếu proxy, nhầm chuỗi loại tài nguyên, xử lý null không an toàn, và policy tin dữ liệu do client cung cấp.

**Môi trường minh họa:** Java 17+, Spring Security 6.5.x, Spring Framework 6.2.x, JUnit 5 và Spring Test; dự án Gradle thử nghiệm dùng BOM Spring Boot 3.5.0 để quản lý dependency. Nội dung tập trung vào **method security của Spring bean**; `hasPermission` trong HTTP authorization cần cấu hình riêng khi có yêu cầu.

## 2. Luồng từ annotation đến PermissionEvaluator

Ví dụ một service:

```java
@PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là **mảnh mã minh họa**, phụ thuộc một `repository` thực tế. Với `@EnableMethodSecurity` và lời gọi qua Spring proxy, luồng ý tưởng là:

```text
Controller / service khác / test
           |
           v
Bean proxy của Spring
           |
           v
AuthorizationManagerBeforeMethodInterceptor
           |
           v
PreAuthorizeAuthorizationManager
           |
           v
MethodSecurityExpressionHandler
   tạo EvaluationContext và root cho SpEL
           |
           v
hasPermission(#id, 'DOCUMENT', 'READ')
           |
           v
PermissionEvaluator.hasPermission(
    authentication, id, "DOCUMENT", "READ")
           |
        +--+---------------------+
        |                        |
      true                     false
        |                        |
        v                        v
  Thân method chạy      AccessDeniedException
                         method chưa chạy
```

Đọc sơ đồ từ ngoài vào trong: `@EnableMethodSecurity` cho phép Spring đăng ký advisor/interceptor; `DefaultMethodSecurityExpressionHandler` giúp SpEL hiểu những biểu thức bảo mật như `hasPermission`; còn `PermissionEvaluator` **chỉ thực hiện quyết định quyền cụ thể**.

| Thành phần | Trách nhiệm | Điều không tự làm |
| --- | --- | --- |
| `@EnableMethodSecurity` | Bật method authorization infrastructure | Không tự suy ra policy cho từng document |
| Spring AOP proxy | Chuyển lời gọi qua interceptor | Không intercept `this.method()` trong proxy mode thông thường |
| `PreAuthorizeAuthorizationManager` / `PostAuthorizeAuthorizationManager` | Đánh giá annotation pre/post tương ứng | Không mặc nhiên thay logic `hasPermission` bằng policy ứng dụng |
| `MethodSecurityExpressionHandler` | Tạo context SpEL cho method và root bảo mật | Không thay thế quyết định owner/tenant |
| `PermissionEvaluator` | Trả `boolean` cho một permission theo đối tượng hoặc ID | Không tự thay đổi tập quyền người dùng, query database hay tạo ACL |
| `@PreAuthorize` / `@PostAuthorize` | Chọn **thời điểm** kiểm tra trước/sau method | Không tự lọc từng phần tử khỏi collection |

Một service có thể dùng cùng evaluator trong `@PreAuthorize`, `@PostAuthorize` hoặc biểu thức lọc dữ liệu. Tuy nhiên, **thời điểm thực thi khác nhau**: với `@PostAuthorize`, thân method đã chạy rồi; evaluator không thể hoàn tác tác dụng phụ xảy ra trước đó.

## 3. Hai chữ ký cần triển khai chính xác

Interface `org.springframework.security.access.PermissionEvaluator` có hai phương thức:

```java
public interface PermissionEvaluator {

    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        java.io.Serializable targetId,
        String targetType,
        Object permission
    );
}
```

Bảng ánh xạ giữa SpEL và overload:

| Biểu thức Spring Security | Chữ ký Java được gọi | Khi nào phù hợp |
| --- | --- | --- |
| `hasPermission(#document, 'READ')` | `hasPermission(Authentication, Object, Object)` | Đã có đối tượng domain đáng tin và muốn kiểm tra trực tiếp |
| `hasPermission(returnObject, 'READ')` | `hasPermission(Authentication, Object, Object)` | Kiểm tra đối tượng **sau** khi service trả về |
| `hasPermission(#id, 'DOCUMENT', 'READ')` | `hasPermission(Authentication, Serializable, String, Object)` | Chỉ có ID; evaluator tự tìm metadata/chủ sở hữu phù hợp |
| `hasPermission(filterObject, 'READ')` | `hasPermission(Authentication, Object, Object)` | Kiểm tra từng phần tử trong `@PreFilter`/`@PostFilter` |

**Giải nghĩa các đối số:**

- `authentication` là danh tính đang được kiểm tra, thường chứa `getName()`, `getPrincipal()`, `getAuthorities()`. Dùng `Authentication` **được framework truyền tới**, không lấy username tùy ý từ request.
- `targetDomainObject` là một đối tượng thực; có thể là `null`. Theo hợp đồng `PermissionEvaluator`, một target null thường phải trả `false`.
- `targetId` phải là `Serializable`, ví dụ `Long`, `UUID`, `String` tùy hệ thống. Đây là **ID**, không phải entity.
- `targetType` là chuỗi loại domain được cung cấp bởi biểu thức, ví dụ `"DOCUMENT"`. Spring Security **không tự biến** mọi chuỗi này thành entity class hoặc repository; evaluator phải tự diễn giải.
- `permission` là kiểu `Object`; trong ví dụ là chuỗi `"READ"` hoặc `"WRITE"`. Nếu dùng enum/bitmask/ACL permission object, hãy kiểm tra kiểu cụ thể thay vì ép chuỗi vô điều kiện.
- Kết quả `true` là allow, `false` là deny. Một lỗi I/O hoặc lỗi database không nên bị che giấu bằng việc trả `true`; thiết kế xử lý lỗi và auditing riêng.

**Khác biệt chữ ký là điểm dễ sai nhất:** dạng có **hai tham số trong SpEL** `hasPermission(target, permission)` gọi overload theo đối tượng; dạng có **ba tham số trong SpEL** `hasPermission(id, type, permission)` gọi overload theo ID. Hai hàm Java đều nhận `Authentication` làm đối số đầu tiên, do Spring cung cấp, nên số tham số của SpEL ít hơn số tham số Java một đơn vị.

## 4. Đăng ký evaluator vào expression handler

### 4.1. Cấu hình Spring Security 6.x được khuyến nghị

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodPermissionConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Đây là **class cấu hình minh họa**: một bean `PermissionEvaluator` phải tồn tại trong context, ví dụ do bạn khai báo `@Bean` hoặc `@Component`. Với Spring Security 6.x, tài liệu dùng **`static @Bean`** cho `MethodSecurityExpressionHandler` để Spring công bố handler đủ sớm trước khi cấu hình method-security infrastructure được khởi tạo.

Điều quan trọng là **type bean** `MethodSecurityExpressionHandler` và lời gọi `handler.setPermissionEvaluator(evaluator)`. Bạn không cần tự đăng ký lại các `@PreAuthorize`/`@PostAuthorize` interceptor mặc định khi `@EnableMethodSecurity` đã bật. Đừng vô tình dùng `@EnableMethodSecurity(prePostEnabled = false)` nếu bài đang trông chờ annotation pre/post hoạt động.

Nếu dự án đã có một custom `MethodSecurityExpressionHandler` cho `RoleHierarchy`, `ParameterNameDiscoverer`, `TrustResolver` hay parser, hãy **cấu hình chính bean handler hiện có** để bổ sung `PermissionEvaluator`; tránh tạo hai handler cạnh tranh mà không rõ bean nào được sử dụng.

### 4.2. Đăng ký bằng XML (khi dự án đang dùng XML)

Với hạ tầng method security kiểu XML, có thể cấu hình một `MethodSecurityExpressionHandler` bean và cho namespace method-security tham chiếu nó:

```xml
<sec:method-security>
    <sec:expression-handler ref="myMethodExpressionHandler"/>
</sec:method-security>

<bean id="myMethodExpressionHandler"
      class="org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler">
    <property name="permissionEvaluator" ref="myPermissionEvaluator"/>
</bean>

<bean id="myPermissionEvaluator" class="demo.DocumentPermissionEvaluator"/>
```

Đoạn XML này **chỉ minh họa phần wiring**, giả định đã khai báo đúng namespace `sec`, `beans` và có class `demo.DocumentPermissionEvaluator` với constructor phù hợp. Trong ứng dụng thuần Java config, hãy ưu tiên ví dụ `@Bean` ở trên.

### 4.3. Không nhầm với web security expression handler

`MethodSecurityExpressionHandler` áp dụng cho annotation **trên method** được bảo vệ bởi Spring Method Security. Nó không tự cấu hình mọi `hasPermission` trong HTTP rule của `HttpSecurity` hoặc trong message/reactive security. Spring Security hiện đại ưu tiên `AuthorizationManager` cho HTTP authorization, có điểm mở rộng riêng. Đừng dùng thành công của một `@PreAuthorize` test để khẳng định endpoint đã được bảo vệ đầy đủ.

## 5. Ví dụ Java 17+: permission theo tài liệu, từ cấu hình đến test

Ví dụ sau cố ý dùng một kho dữ liệu tĩnh bất biến trong test để dễ phân biệt hai overload, không cần database hoặc web server. Trong hệ thống thật, evaluator theo ID phải truy vấn repository/policy trên dữ liệu phía server, có kiểm soát tenant và performance.

### 5.1. Bố cục dự án Gradle

```text
permission-evaluator-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/PermissionEvaluatorRegistrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'permission-evaluator-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Chỉ có mã test trong project, nên các dependency trên `testImplementation` là đủ. Khi tích hợp vào ứng dụng thật, `spring-boot-starter-security` và evaluator implementation thuộc `implementation`; phụ thuộc test vẫn ở cấu hình test.

### 5.2. Một tệp Java test hoàn chỉnh

Tạo `src/test/java/demo/PermissionEvaluatorRegistrationTest.java`:

```java
package demo;

import java.io.Serializable;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(PermissionEvaluatorRegistrationTest.Config.class)
@WithMockUser(username = "alice")
public class PermissionEvaluatorRegistrationTest {

    private static final Map<Long, Document> STORE = Map.of(
        1L, new Document(1L, "alice"),
        2L, new Document(2L, "bob")
    );

    @Autowired DocumentService service;
    @Autowired DocumentPermissionEvaluator evaluator;
    @Autowired Probe probe;

    @BeforeEach
    void resetCounters() {
        probe.reset();
        evaluator.reset();
    }

    public record Document(Long id, String owner) { }

    public static class Probe {
        private final AtomicInteger executions = new AtomicInteger();

        void mark() { executions.incrementAndGet(); }
        int count() { return executions.get(); }
        void reset() { executions.set(0); }
    }

    // Policy tập trung: chỉ READ trên Document có owner là principal,
    // đồng thời xác nhận đối tượng khớp bản ghi tin cậy trong STORE.
    public static class DocumentPermissionEvaluator
            implements PermissionEvaluator {

        private final AtomicInteger objectCalls = new AtomicInteger();
        private final AtomicInteger idCalls = new AtomicInteger();

        @Override
        public boolean hasPermission(Authentication auth,
                                     Object target,
                                     Object permission) {
            objectCalls.incrementAndGet();

            if (!validUser(auth) || !"READ".equals(permission)
                    || !(target instanceof Document document)) {
                return false;
            }

            Document persisted = STORE.get(document.id());
            return persisted != null
                && persisted.equals(document)
                && persisted.owner().equals(auth.getName());
        }

        @Override
        public boolean hasPermission(Authentication auth,
                                     Serializable targetId,
                                     String targetType,
                                     Object permission) {
            idCalls.incrementAndGet();

            if (!validUser(auth)
                    || !"DOCUMENT".equals(targetType)
                    || !"READ".equals(permission)
                    || !(targetId instanceof Long id)) {
                return false;
            }

            Document persisted = STORE.get(id);
            return persisted != null
                && persisted.owner().equals(auth.getName());
        }

        private static boolean validUser(Authentication auth) {
            return auth != null && auth.isAuthenticated();
        }

        int objectCalls() { return objectCalls.get(); }
        int idCalls() { return idCalls.get(); }

        void reset() {
            objectCalls.set(0);
            idCalls.set(0);
        }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @PreAuthorize("hasPermission(#document, 'READ')")
        public String describe(@P("document") Document document) {
            probe.mark();
            return document.id() + ":" + document.owner();
        }

        @PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
        public String readById(@P("id") Long id) {
            probe.mark();
            Document document = STORE.get(id);
            return document == null ? "MISSING" : document.id().toString();
        }

        @PreAuthorize("hasPermission(#id, 'INVOICE', 'READ')")
        public String unsupportedType(@P("id") Long id) {
            probe.mark();
            return "UNEXPECTED";
        }

        @PreAuthorize("hasPermission(#document, 'WRITE')")
        public String unsupportedPermission(@P("document") Document document) {
            probe.mark();
            return "UNEXPECTED";
        }

        @PostAuthorize(
            "returnObject != null and hasPermission(returnObject, 'READ')"
        )
        public Document readAfter(Long id) {
            probe.mark();
            return STORE.get(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {

        @Bean
        static DocumentPermissionEvaluator permissionEvaluator() {
            return new DocumentPermissionEvaluator();
        }

        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
                DocumentPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DocumentService documentService(Probe probe) {
            return new DocumentService(probe);
        }
    }

    @Test
    void serviceReallyIsProxied() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void objectOverloadAllowsAliceDocument() {
        assertThat(service.describe(STORE.get(1L)))
            .isEqualTo("1:alice");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isZero();
    }

    @Test
    void objectOverloadDeniesBobsDocumentBeforeBody() {
        assertThatThrownBy(() -> service.describe(STORE.get(2L)))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void idOverloadAllowsAliceDocument() {
        assertThat(service.readById(1L)).isEqualTo("1");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isZero();
    }

    @Test
    void idOverloadDeniesBobsDocumentBeforeBody() {
        assertThatThrownBy(() -> service.readById(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }

    @Test
    void missingDocumentIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.readById(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void unsupportedTargetTypeIsDenied() {
        assertThatThrownBy(() -> service.unsupportedType(1L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }

    @Test
    void unsupportedPermissionIsDenied() {
        assertThatThrownBy(() -> service.unsupportedPermission(STORE.get(1L)))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeAllowsOwnedReturnObject() {
        assertThat(service.readAfter(1L)).isEqualTo(STORE.get(1L));
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeDeniesOtherOwnerAfterBody() {
        assertThatThrownBy(() -> service.readAfter(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.objectCalls()).isEqualTo(1);
    }

    @Test
    void postAuthorizeRejectsNullReturnObject() {
        assertThatThrownBy(() -> service.readAfter(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
        // SpEL 'and' short-circuit: evaluator không nhận null.
        assertThat(evaluator.objectCalls()).isZero();
    }

    @Test
    @WithMockUser(username = "bob")
    void anotherPrincipalCanReadHisDocumentById() {
        assertThat(service.readById(2L)).isEqualTo("2");
        assertThat(probe.count()).isEqualTo(1);
        assertThat(evaluator.idCalls()).isEqualTo(1);
    }
}
```

**Vì sao ví dụ thể hiện việc đăng ký evaluator, thay vì chỉ minh họa một hàm boolean?**

- `@EnableMethodSecurity` thực sự bật advisor đọc `@PreAuthorize` và `@PostAuthorize`.
- `@Bean static MethodSecurityExpressionHandler` cấu hình `DefaultMethodSecurityExpressionHandler` bằng **chính `DocumentPermissionEvaluator`** đang được inject vào test.
- `DocumentPermissionEvaluator.objectCalls` và `idCalls` đếm số lần framework gọi từng overload; các assert đối chiếu đúng overload với đúng cú pháp SpEL.
- `Probe` xác nhận thứ tự nghiệp vụ: **pre deny** khiến `probe.count() == 0`, **post deny** xảy ra sau khi body chạy nên `probe.count() == 1`.
- Cấu hình static giúp handler được đăng ký sớm; `@P("id")`, `@P("document")` giúp tên tham số SpEL ổn định mà không cần dựa vào flag `-parameters`.
- Dữ liệu `STORE` bất biến là **server-side fixture**; overload theo đối tượng xác minh bản ghi đưa vào khớp dữ liệu được tin cậy trước khi so owner. Đây là ví dụ nhỏ để hiểu cơ chế, không phải policy lưu trữ thông tin user/permission cho production.
- `@WithMockUser(username = "alice")` tạo `Authentication` dùng trong test; trường hợp Bob ghi đè principal, chứng minh policy không hardcode Alice.
- Vì không có web server, test chỉ kiểm tra `AccessDeniedException`, không tự khẳng định HTTP 403. Ở ứng dụng có servlet filter chain, exception translation quyết định response theo cấu hình.

### 5.3. Chạy dự án và kỳ vọng

Tại thư mục có `build.gradle`:

```bash
gradle test --tests demo.PermissionEvaluatorRegistrationTest
```

Khi có Gradle Wrapper, chạy `./gradlew test --tests demo.PermissionEvaluatorRegistrationTest` trên Linux/macOS hoặc `gradlew.bat test --tests demo.PermissionEvaluatorRegistrationTest` trên Windows.

**Kỳ vọng cấu hình đã đúng:** **12 test thành công**, Gradle báo `BUILD SUCCESSFUL`. Đây là **kết quả dự kiến dựa trên mã minh họa**, không phải stdout thu từ một lần chạy thực tế. Xem chi tiết tại `build/reports/tests/test/index.html` và kiểm tra version dependency thực đang được resolve.

Ma trận kết quả trọng tâm:

| Tình huống | Overload evaluator | Phần thân method chạy? | Kết quả |
| --- | --- | --- | --- |
| Alice đọc object thuộc Alice | Object | Có, 1 lần | Allow |
| Alice đọc object thuộc Bob | Object | Không | Deny |
| Alice đọc ID 1 | ID + type | Có, 1 lần | Allow |
| Alice đọc ID 2 | ID + type | Không | Deny |
| ID không tồn tại | ID + type | Không | Deny |
| Target type `INVOICE` không hỗ trợ | ID + type | Không | Deny |
| Permission `WRITE` không hỗ trợ | Object | Không | Deny |
| After nhận object của Alice | Object | Có, 1 lần | Allow |
| After nhận object của Bob | Object | Có, 1 lần | Deny sau body |
| After nhận `null` | Không gọi evaluator vì biểu thức guard | Có, 1 lần | Deny |
| Bob đọc ID 2 | ID + type | Có, 1 lần | Allow |

Test `serviceReallyIsProxied` là kiểm tra hạ tầng bổ sung. Nó không đủ nếu đứng một mình: proxy tồn tại chưa bảo đảm `PermissionEvaluator` phù hợp đã được cài; counter tests chứng minh **handler thực tế đang sử dụng evaluator bạn đăng ký**.

## 6. Điều chỉnh biểu thức cho các tình huống thông dụng

### 6.1. Kiểm tra đối tượng đầu vào

```java
@PreAuthorize("hasPermission(#document, 'READ')")
public void inspect(@P("document") Document document) {
    // Chỉ chạy nếu evaluator cho READ đối với document.
}
```

Ở đây `#document` là biến tham số trong SpEL, không phải string literal `'document'`. Cần `@P` hoặc cơ chế phát hiện tên tham số thích hợp; dùng `-parameters` khi build Java là một phương án.

**Cảnh báo trust boundary:** Nếu `document` đến trực tiếp từ JSON do client tự gửi, client có thể giả mạo trường `owner`. Mẫu an toàn hơn thường nhận `id` và để evaluator/repository tra quyền trên **bản ghi thực** phía server. Ví dụ test ở trên vẫn đối chiếu object với `STORE` để minh họa chính xác điểm này.

### 6.2. Kiểm tra theo ID + loại tài nguyên

```java
@PreAuthorize("hasPermission(#id, 'DOCUMENT', 'READ')")
public Document find(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là **đoạn code phụ thuộc repository**, không phải chương trình độc lập. Overload ID nhận `targetId` kiểu `Serializable`, `targetType` là string do bạn đặt (ở đây `"DOCUMENT"`) và permission string. Nếu biểu thức dùng `'Document'` nhưng evaluator chỉ hỗ trợ `'DOCUMENT'`, policy ví dụ sẽ deny. Hãy chuẩn hóa type/permission thành tên có chủ đích và kiểm tra bằng test.

Nếu dùng đa tenant, truy vấn nên dựa trên **ID và tenant** đã được xác thực; chỉ kiểm tra owner string không đủ với dữ liệu có thể trùng ID giữa tenant. Trong hệ thống lớn, tối ưu số lần tra quyền và cân nhắc cache có khóa theo principal, tenant, permission và vòng đời thay đổi dữ liệu.

### 6.3. Kiểm tra dữ liệu trả về

```java
@PostAuthorize("returnObject != null and hasPermission(returnObject, 'READ')")
public Document read(@P("id") Long id) {
    return repository.findById(id).orElse(null);
}
```

`returnObject` là giá trị trả về; SpEL `and` short-circuit bảo đảm không gọi evaluator khi result null. Ở đây **null bị từ chối** theo policy ví dụ. Ứng dụng có thể muốn tách `null` thành 404/không tìm thấy, hoặc coi null không nhạy cảm và cho phép; đó là **quy tắc nghiệp vụ**, không phải bắt buộc của PermissionEvaluator.

Với `@PostAuthorize`, service **đã chạy** trước khi denied; không dùng after check làm biện pháp duy nhất để ngăn thanh toán, xóa dữ liệu, phát event hoặc ghi log nhạy cảm.

### 6.4. Lọc từng phần tử collection

Nếu cần lọc collection, có thể dùng:

```java
@PostFilter("hasPermission(filterObject, 'READ')")
public java.util.List<Document> findAll() {
    return new java.util.ArrayList<>(repository.findAll());
}
```

`filterObject` lần lượt là phần tử hiện tại, nên evaluator dạng object được gọi **mỗi phần tử**. Đoạn mã phụ thuộc `repository` và chỉ minh họa. Với `@PreFilter`, chú ý collection mutable vì interceptor có thể cần xóa phần tử. `@PostFilter` có thể dẫn đến N+1 lần kiểm tra quyền và sai pagination do lọc sau khi truy vấn; dữ liệu lớn thường cần ràng buộc ngay tại query.

### 6.5. Phối hợp quyền vai trò và quyền đối tượng

```java
@PreAuthorize(
    "hasAuthority('DOCUMENT_VIEW') and hasPermission(#id, 'DOCUMENT', 'READ')"
)
public Document read(@P("id") Long id) {
    return repository.findById(id).orElseThrow();
}
```

`hasAuthority` kiểm tra quyền tổng quát; `hasPermission` kiểm tra đúng tài nguyên. Biểu thức `and` có thể short-circuit, nên evaluator không nhất thiết được gọi khi authority chung đã không đạt. Kết quả nên được test theo **bốn tổ hợp**: có/không có authority, có/không có object permission.

## 7. Nếu đã dùng Spring Security ACL thì sao?

Spring Security cung cấp `AclPermissionEvaluator` để đánh giá ACL của domain object. Tư tưởng wiring vẫn giống:

```java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        AclPermissionEvaluator aclPermissionEvaluator) {
    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(aclPermissionEvaluator);
    return handler;
}
```

Đây là **đoạn cấu hình thành phần**, chỉ hoạt động khi dự án đã thiết lập `AclService`, ACL cache/lookup strategy, permission granting và các cấu trúc dữ liệu cần thiết. Chỉ khai báo `AclPermissionEvaluator` hoặc `spring-security-acl` dependency mà chưa có nơi lưu ACL, không có nghĩa đối tượng đã được phân quyền.

Một evaluator domain tùy chỉnh phù hợp khi policy tập trung vào owner/tenant/trạng thái và nguồn dữ liệu nghiệp vụ. `AclPermissionEvaluator` phù hợp khi ứng dụng thực sự quản lý các **access control entry** theo từng object/SID/permission. Cả hai đều đi qua `hasPermission` khi đã được nối với expression handler.

## 8. Các lỗi hay gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `hasPermission` luôn trả false dù custom evaluator trả true trong unit test | Expression handler dùng `DenyAllPermissionEvaluator` mặc định hoặc chưa được nối evaluator | Đăng ký `MethodSecurityExpressionHandler` có `setPermissionEvaluator`; test counter thực sự tăng |
| Không thấy annotation hoạt động | Thiếu `@EnableMethodSecurity`, test dùng `new Service()` hoặc self-invocation | Inject Spring-managed bean và có test deny trước body |
| Bean evaluator tồn tại nhưng Spring không dùng | Chỉ có `@Component PermissionEvaluator`, bean handler khác được chọn, đăng ký muộn | Kiểm tra bean `MethodSecurityExpressionHandler`, ưu tiên `static @Bean` và wiring rõ ràng |
| `#id` thành null/sai dữ liệu | Bytecode không có parameter names, sai `@P` hoặc sai chữ hoa/thường | Dùng `@P("id")` hoặc biên dịch với `-parameters` |
| Overload không đúng | Viết `hasPermission(#id, 'READ')` trong khi muốn type-specific lookup | Dùng ba đối số `hasPermission(#id, 'DOCUMENT', 'READ')` |
| Deny mọi loại đối tượng | `targetType` trong SpEL khác chuỗi evaluator chấp nhận | Chuẩn hóa type và assert cả case unsupported |
| `ClassCastException` / `NullPointerException` | Ép kiểu target/permission mà không kiểm tra, result null | Dùng `instanceof`, guard null và fail closed |
| Object từ client tự đổi `owner` để qua policy | Tin thuộc tính trong request body | Tra bản ghi đáng tin theo ID/tenant, không chỉ nhìn DTO |
| Post authorize denied nhưng database đã bị ghi | Method đã chạy trước after check | Chặn side effect bằng before/policy/transaction boundary thích hợp |
| Lọc list lớn chậm | `@PostFilter` gọi evaluator nhiều lần, query mỗi phần tử | Lọc ngay tại repository/query, batch/cache theo thiết kế bảo mật |
| Kỳ vọng HTTP rule áp dụng evaluator của method | Cấu hình nhầm giữa web và method security | Kiểm tra đúng `MethodSecurityExpressionHandler` và HTTP authorization subsystem |
| Quên test user khác | Policy ngầm hardcode Alice hoặc cache sai | Test Bob, tenant khác, null, invalid permission và thay đổi quyền |

### Checklist debug thực tế

1. Kiểm tra `@EnableMethodSecurity` được bật ở Spring context nơi bean chạy, annotation nằm trên method có thể được proxy intercept.
2. Đảm bảo lời gọi tới method đi qua **Spring bean proxy**, không phải `new` hay `this.method()`.
3. Xác nhận chỉ **một handler chính** được dùng cho annotation: bean type `MethodSecurityExpressionHandler`, `setPermissionEvaluator(...)` đã nhận evaluator đúng.
4. Với biểu thức dùng tham số, xác nhận `#id`/`#document` được phát hiện bằng `@P` hoặc `-parameters`, không phải string không có `#`.
5. Test hai overload riêng và ghi nhận bằng counter/log an toàn; không ghi dữ liệu nhạy cảm vào log.
6. Test cả positive và negative: Alice đọc tài liệu Alice, Alice bị từ chối tài liệu Bob, Bob được đọc tài liệu Bob, permission/type unsupported bị từ chối.
7. Với `@PostAuthorize`, kiểm tra method body đã chạy trước deny và xử lý side effect phù hợp.
8. Với môi trường nhiều tenant, bổ sung tenant scope, quyền thay đổi theo thời gian và caching phù hợp.
9. Khi nâng cấp framework, đối chiếu API của `PermissionEvaluator`, expression handler và cấu hình Method Security theo version thực tế.

## 9. Một số quyết định thiết kế để áp dụng an toàn

**Chọn nguồn sự thật đáng tin:** Một evaluator có thể nhận `Document` qua SpEL, nhưng dữ liệu domain được nhận từ client chỉ là **input**, chưa phải sự thật. Khi cần kiểm tra owner/tenant, đọc metadata thật từ repository hoặc dùng object được load từ data layer có scope xác thực; tránh chấp nhận bất kỳ object nào chỉ vì thuộc tính `owner` trùng tên đăng nhập.

**Đặt tên permission rõ ràng:** Chọn một bộ tên nhất quán như `READ`, `WRITE`, `DELETE`, hoặc enum phù hợp. Đừng giả định Spring tự hiểu `'READ'` là `BasePermission.READ` của ACL: đó là trách nhiệm của evaluator hoặc hệ thống ACL. Nếu dùng role/authority chung, viết thêm `hasAuthority` hoặc tích hợp vào policy.

**Kiểm tra hiệu năng:** Dạng `hasPermission(filterObject, ...)` có thể gọi evaluator nhiều lần cho một danh sách; dạng `hasPermission(id, ...)` có thể dẫn đến một truy vấn cho mỗi request. Dùng query scoped by principal/tenant, cache có invalidation rõ ràng, hoặc policy batch khi có nhu cầu thực. Không cache kết quả quyền toàn cục theo mỗi ID mà quên principal.

**Giữ fail closed:** Null, target type không biết, permission sai và tài nguyên không tồn tại nên có kết quả từ chối rõ ràng trừ khi hợp đồng nghiệp vụ yêu cầu điều khác. Lỗi storage/authentication không được mặc định thành allow. Đảm bảo quyền được kiểm tra ở mọi luồng gọi quan trọng, kể cả scheduled jobs và batch ngoài HTTP.

**Tách riêng kiểm thử đăng ký và kiểm thử policy:** Unit test gọi `new DocumentPermissionEvaluator().hasPermission(...)` chỉ kiểm tra thuật toán Java; nó **không** chứng minh Spring đã nối evaluator vào SpEL. Tích hợp context, annotation và proxy như ví dụ mới chứng minh wiring. Trong test production, kiểm tra thêm database ownership, quyền động, transaction và các giá trị null theo yêu cầu ứng dụng.

## 10. Bài tập luyện tập

1. **Thêm WRITE:** mở rộng evaluator cho `WRITE` với quy tắc ví dụ Alice là chủ sở hữu và tài liệu chưa locked; thêm test allow/deny. Đừng chỉ đổi chuỗi `READ` trong annotation mà giữ evaluator cũ.
2. **Tên tham số:** bỏ `@P("id")`, biên dịch Java với `-parameters`, rồi xác minh `#id` được resolve. Thử sai tên `#documentId` và giải thích vì sao biểu thức không lấy đúng giá trị.
3. **Đổi principal:** thêm record thuộc Carol và `@WithMockUser(username="carol")`; xác minh đúng record được phép, Bob/Alice không đọc nhầm.
4. **Đầu vào giả mạo:** tạo một `Document(1L, "bob")` bằng client dù document #1 trong `STORE` thuộc Alice. Xác minh overload object từ chối vì không khớp bản ghi server.
5. **Policy sau method:** thay `returnObject != null and ...` bằng chính sách coi null là “không tìm thấy” và cho phép trả `null`; cập nhật test cho đúng hợp đồng API, không giả vờ đó là lỗi quyền.
6. **ACL thực tế:** nếu ứng dụng có hệ thống ACL, thay evaluator domain bằng `AclPermissionEvaluator`, đăng ký cùng handler và xây integration test với một ACL grant và một ACL deny thật.

## 11. Ghi nhớ

- `PermissionEvaluator` là điểm mở rộng cho `hasPermission` theo **đối tượng cụ thể** hoặc **ID + loại tài nguyên**.
- Cần bật `@EnableMethodSecurity` và đăng ký `DefaultMethodSecurityExpressionHandler` có `setPermissionEvaluator(...)`; Spring Security 6.x khuyến nghị khai báo handler bằng **`static @Bean`**.
- `hasPermission(target, permission)` gọi overload đối tượng; `hasPermission(id, type, permission)` gọi overload theo ID. Authentication được Spring bổ sung cho cả hai.
- `@PreAuthorize` kiểm tra **trước body**; `@PostAuthorize` kiểm tra **sau body** và không hoàn tác side effect.
- Hãy test **wiring thực tế qua proxy**: cả allow/deny, đúng overload, đúng principal, null, type/permission không hỗ trợ và dữ liệu tin cậy.
- Với dữ liệu có tenant/ownership, kiểm tra dựa trên nguồn server-side thay vì tin DTO tự khai. Expression handler chỉ **chuyển tiếp policy**, không bảo đảm bản thân policy là đúng.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, method expressions, `@P`, custom handler: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Domain Object Security / Using the PermissionEvaluator, mẫu `setPermissionEvaluator`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 API — `PermissionEvaluator` và hai overload: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html
- Spring Security 6.5 API — `DefaultMethodSecurityExpressionHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html
