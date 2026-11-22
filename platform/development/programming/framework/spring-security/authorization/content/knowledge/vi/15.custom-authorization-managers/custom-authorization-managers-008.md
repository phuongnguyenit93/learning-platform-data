# AuthorizationManagerBeforeMethodInterceptor và AuthorizationManagerAfterMethodInterceptor

## 1. Mục tiêu bài học

Trong Spring Security Method Security, hai interceptor **`AuthorizationManagerBeforeMethodInterceptor`** và **`AuthorizationManagerAfterMethodInterceptor`** nối logic quyết định quyền (`AuthorizationManager`) với các lời gọi phương thức của Spring AOP.

- **Before**: quyết định người gọi có được phép **thực thi phương thức** hay không, trước khi thân phương thức bắt đầu.
- **After**: quyết định người gọi có được phép **nhận kết quả trả về** hay không, sau khi thân phương thức đã chạy.

Đây là cơ chế nền tảng để triển khai `@PreAuthorize` và `@PostAuthorize`, đồng thời có thể dùng trực tiếp với **AuthorizationManager tùy chỉnh** và **Pointcut tùy chỉnh**.

Sau khi đọc, bạn có thể:

1. Giải thích luồng AOP, đối tượng đầu vào và kết quả của từng interceptor.
2. Phân biệt `MethodInvocation` với `MethodInvocationResult`.
3. Hiểu các factory method `preAuthorize(...)` / `postAuthorize(...)`, cũng như constructor nhận `Pointcut`.
4. Đăng ký `Advisor` riêng, tránh chồng chéo vô ý với interceptor mặc định.
5. Viết `AuthorizationManager` bằng Java thay vì SpEL, kiểm tra đúng trước/sau và xử lý dữ liệu `null`.
6. Test Spring bean/proxy để chứng minh **before deny không chạy body**, còn **after deny xảy ra sau body**.

**Phạm vi:** Spring Security 6.5.x, Spring Framework 6.2.x, Java 17+, Spring AOP proxy thông thường. API 7.x có những thay đổi nhỏ về giao diện `AuthorizationManager`; cần đối chiếu Javadoc của đúng phiên bản khi nâng cấp. Các ví dụ chủ yếu dùng method security đồng bộ trên Spring-managed bean, không áp dụng trực tiếp cho reactive method security.

## 2. Hai thời điểm kiểm soát trên cùng một lời gọi

Giả sử service có một phương thức đọc tài liệu được bảo vệ cả đầu vào lẫn đầu ra:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document findDocument(String id) {
    return repository.findDocument(id);
}
```

Đây là **đoạn mã minh họa**, không phải chương trình Java độc lập. Với `@EnableMethodSecurity` và lời gọi đi qua Spring proxy, luồng khái niệm là:

```text
Caller
   |
   v
Spring AOP proxy
   |
   v
BeforeMethodInterceptor
   |-- Pointcut khớp @PreAuthorize?
   |-- AuthorizationManager<MethodInvocation>
   |-- DENY --> AccessDeniedException (không gọi method body)
   |
   | ALLOW
   v
Service.findDocument(id)  --> Document kết quả
   |
   v
AfterMethodInterceptor
   |-- Pointcut khớp @PostAuthorize?
   |-- AuthorizationManager<MethodInvocationResult>
   |-- DENY --> AccessDeniedException (không trả Document cho caller)
   |
   | ALLOW
   v
Caller nhận Document
```

Cả hai thường là `Advisor` của Spring AOP: advisor gồm **Pointcut** để chọn phương thức và **Advice/MethodInterceptor** để thực thi việc kiểm tra.

**Điểm then chốt:** after interceptor chạy sau thân phương thức và có quyền xem kết quả; nó **không hoàn tác** truy vấn, thay đổi dữ liệu hoặc tác dụng phụ mà thân phương thức đã thực hiện. Chính sách chặn thao tác ghi phải được kiểm tra **trước** khi có side effect, không chỉ dựa vào after authorization.

## 3. Bảng so sánh chính xác

| Tiêu chí | `AuthorizationManagerBeforeMethodInterceptor` | `AuthorizationManagerAfterMethodInterceptor` |
| --- | --- | --- |
| Thời điểm | Trước khi gọi thân method | Sau khi method đã trả kết quả, trước khi trả cho caller |
| Dữ liệu manager kiểm tra | `MethodInvocation` | `MethodInvocationResult` |
| Generic quan trọng | `AuthorizationManager<MethodInvocation>` | `AuthorizationManager<MethodInvocationResult>` |
| Dữ liệu có thể đọc | Method, target, arguments | MethodInvocation **và** kết quả qua `getResult()` |
| Factory thông dụng | `preAuthorize()`, `preAuthorize(manager)` | `postAuthorize()`, `postAuthorize(manager)` |
| Annotation mặc định liên quan | `@PreAuthorize` | `@PostAuthorize` |
| Từ chối quyền | Không chạy body; thường ném `AccessDeniedException` | Body đã chạy; kết quả bị giữ lại; thường ném `AccessDeniedException` |
| Phù hợp | Quyền chạy lệnh, quyền truy cập ID, role, tenant trước thao tác | Kiểm tra owner/tenant/trạng thái trên **kết quả đã tải** |
| Không phải | `@PreFilter` tự động lọc collection | `@PostFilter` tự động lọc từng phần tử collection |

`MethodInvocation` (AOP Alliance) cho phép gọi `getMethod()`, `getArguments()`, `getThis()`. Nó **chưa** có kết quả trả về tại thời điểm before. Ngược lại, `MethodInvocationResult` của Spring Security chứa `getMethodInvocation()` và `getResult()`; kết quả có thể là `null` và cần chính sách xử lý rõ ràng.

Đặc biệt, **`@PostAuthorize` kiểm tra toàn bộ giá trị trả về**, không tự xóa từng phần tử khỏi danh sách. Lọc collection theo từng phần tử là nhiệm vụ khác của `@PostFilter` và `PostFilterAuthorizationMethodInterceptor`.

## 4. Các interceptor mặc định do Spring Security tạo

Bật method security trong cấu hình:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {
}
```

Khi đó Spring Security cung cấp hạ tầng advisor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` theo thiết lập mặc định. Có thể hình dung tương đương phần before/after như sau:

```java
// Minh họa advisor tương đương, KHÔNG thêm trùng khi đã dùng
// @EnableMethodSecurity với prePostEnabled = true.
Advisor pre = AuthorizationManagerBeforeMethodInterceptor.preAuthorize();
Advisor post = AuthorizationManagerAfterMethodInterceptor.postAuthorize();
```

Ở cấu hình chuẩn, `preAuthorize()` dùng `PreAuthorizeAuthorizationManager` để đánh giá biểu thức từ `@PreAuthorize` qua `MethodSecurityExpressionHandler`. Tương tự, `postAuthorize()` dùng `PostAuthorizeAuthorizationManager` để đánh giá `@PostAuthorize` với `returnObject`.

Các annotation khác có interceptor chuyên biệt hoặc factory riêng:

| Annotation | Bộ xử lý mặc định |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor.preAuthorize(...)` |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor.postAuthorize(...)` |
| `@Secured` (cần `securedEnabled = true`) | `AuthorizationManagerBeforeMethodInterceptor.secured(...)` |
| JSR-250 như `@RolesAllowed` (cần `jsr250Enabled = true`) | `AuthorizationManagerBeforeMethodInterceptor.jsr250(...)` |
| `@PreFilter` / `@PostFilter` | `PreFilterAuthorizationMethodInterceptor` / `PostFilterAuthorizationMethodInterceptor` |

Không viết code giả định rằng `AuthorizationManagerBeforeMethodInterceptor.preFilter()` và `AuthorizationManagerAfterMethodInterceptor.postFilter()` là API để đăng ký filter cho mọi phiên bản: Spring Security có các **lớp filter interceptor riêng**.

### 4.1. Khi thay thế manager của annotation mặc định

Nếu muốn thay logic authorization cho `@PreAuthorize` và `@PostAuthorize` bằng code Java, tài liệu chính thức hướng dẫn **tắt cấu hình pre/post mặc định**, rồi khai báo advisor do mình kiểm soát:

```java
@Configuration
@EnableMethodSecurity(prePostEnabled = false)
class CustomMethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor customBefore(
            AuthorizationManager<MethodInvocation> beforeManager) {
        return AuthorizationManagerBeforeMethodInterceptor
            .preAuthorize(beforeManager);
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor customAfter(
            AuthorizationManager<MethodInvocationResult> afterManager) {
        return AuthorizationManagerAfterMethodInterceptor
            .postAuthorize(afterManager);
    }
}
```

**Đây là ví dụ cấu hình minh họa**, cần cung cấp đúng hai bean `beforeManager` và `afterManager`, imports tương ứng. Các factory `preAuthorize(manager)` / `postAuthorize(manager)` dùng **pointcut của annotation tương ứng**. Khi đưa manager tùy chỉnh vào thay manager SpEL mặc định, **không giả định chuỗi biểu thức trên annotation còn được Spring tự đánh giá**: manager do bạn viết quyết định chính sách thực tế. Cần giữ hoặc di chuyển điều kiện cũ một cách có chủ đích.

Nếu mục tiêu chỉ là bổ sung chính sách cho **một nhóm method riêng**, có thể giữ `@EnableMethodSecurity` bình thường, tạo **custom pointcut** hẹp và thêm advisor riêng. Khi một phương thức khớp nhiều advisor, các quyết định sẽ phối hợp theo chuỗi; phải hiểu rule nào từ chối và thứ tự advice để tránh kết quả bất ngờ.

## 5. Custom Pointcut: gắn hai interceptor vào một annotation nghiệp vụ

Một mẫu thiết kế dễ kiểm chứng là tạo annotation `@DocumentRead` cho những method trả một `Document`, rồi đăng ký:

- Before manager: kiểm tra người gọi có authority `DOC_READ`.
- After manager: nếu method đã chạy, chỉ trả `Document` khi `owner` trùng principal.
- Hai advisor sử dụng cùng `AnnotationMatchingPointcut.forMethodAnnotation(DocumentRead.class)`.

Bằng cách này, mã Java của policy là nguồn sự thật của các quyết định, không phụ thuộc chuỗi SpEL hoặc tên tham số được phát hiện qua reflection.

### 5.1. Build Gradle tự đủ cho ví dụ

Tạo project thử nhỏ:

```text
interceptors-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/InterceptorMethodSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'interceptors-demo'
```

`build.gradle` (Java 17, BOM Spring Boot 3.5.0 quản lý Spring Security 6.5.x):

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

Toàn bộ ví dụ đặt ở `src/test/java`, vì vậy dependency test là đủ. Trong ứng dụng thực, đưa Spring Security starter vào `implementation`, thêm dependency test theo lifecycle dự án và dùng BOM version đã được dự án quản lý. Không trộn thủ công các version Spring Security/Spring Framework không tương thích.

### 5.2. Java class đầy đủ, có sáu test

Tạo `src/test/java/demo/InterceptorMethodSecurityTest.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.concurrent.atomic.AtomicInteger;

import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerAfterMethodInterceptor;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(InterceptorMethodSecurityTest.Config.class)
@WithMockUser(username = "alice", authorities = "DOC_READ")
public class InterceptorMethodSecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    Probe probe;

    @BeforeEach
    void clearProbe() {
        probe.reset();
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface DocumentRead {
    }

    public record Document(String id, String owner) {
    }

    public static class Probe {
        private final AtomicInteger calls = new AtomicInteger();

        void recordCall() {
            calls.incrementAndGet();
        }

        int calls() {
            return calls.get();
        }

        void reset() {
            calls.set(0);
        }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @DocumentRead
        public Document read(String id) {
            probe.recordCall();
            return switch (id) {
                case "A" -> new Document("A", "alice");
                case "B" -> new Document("B", "bob");
                default -> null;
            };
        }

        public String ping() {
            return "pong";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity(prePostEnabled = false)
    public static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DocumentService service(Probe probe) {
            return new DocumentService(probe);
        }

        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor beforeDocumentRead() {
            AuthorizationManager<MethodInvocation> manager =
                (authenticationSupplier, invocation) -> {
                    Authentication authentication = authenticationSupplier.get();
                    boolean granted = authentication != null
                        && authentication.isAuthenticated()
                        && authentication.getAuthorities().stream()
                            .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));
                    return new AuthorizationDecision(granted);
                };

            return new AuthorizationManagerBeforeMethodInterceptor(
                AnnotationMatchingPointcut.forMethodAnnotation(
                    DocumentRead.class),
                manager
            );
        }

        @Bean
        @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
        static Advisor afterDocumentRead() {
            AuthorizationManager<MethodInvocationResult> manager =
                (authenticationSupplier, invocationResult) -> {
                    Authentication authentication = authenticationSupplier.get();
                    Object value = invocationResult.getResult();
                    boolean granted = authentication != null
                        && authentication.isAuthenticated()
                        && value instanceof Document document
                        && document.owner().equals(authentication.getName());
                    return new AuthorizationDecision(granted);
                };

            return new AuthorizationManagerAfterMethodInterceptor(
                AnnotationMatchingPointcut.forMethodAnnotation(
                    DocumentRead.class),
                manager
            );
        }
    }

    @Test
    void aliceCanReadHerDocument() {
        assertThat(service.read("A"))
            .isEqualTo(new Document("A", "alice"));
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void bobCanReadHisDocument() {
        assertThat(service.read("B"))
            .isEqualTo(new Document("B", "bob"));
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void missingAuthorityIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.read("A"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isZero();
    }

    @Test
    void wrongOwnerIsDeniedAfterBody() {
        assertThatThrownBy(() -> service.read("B"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    void nullResultIsDeniedAfterBody() {
        assertThatThrownBy(() -> service.read("missing"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.calls()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "guest", authorities = "OTHER")
    void methodOutsidePointcutIsNotCheckedByTheseAdvisors() {
        assertThat(service.ping()).isEqualTo("pong");
        assertThat(probe.calls()).isZero();
    }
}
```

**Giải thích các điểm thiết kế trong test:**

1. `@SpringJUnitConfig` tạo Spring ApplicationContext; `@EnableMethodSecurity(prePostEnabled = false)` vẫn kích hoạt hạ tầng AOP nhưng tắt các advisor `@PreAuthorize`/`@PostAuthorize` mặc định. Hai advisor riêng được đăng ký bằng `@Bean` có role `ROLE_INFRASTRUCTURE`.
2. `@DocumentRead` chỉ đánh dấu method cần áp dụng hai rule. `AnnotationMatchingPointcut` kiểm tra annotation ở **method**; method `ping()` nằm ngoài pointcut này.
3. Before manager dùng `AuthorizationManager<MethodInvocation>`; ở ví dụ, chỉ cần authority trong `Authentication`. Với policy phức tạp, có thể đọc `invocation.getArguments()`, `getMethod()` và `getThis()` để áp dụng luật theo ID, tenant, target.
4. After manager dùng `AuthorizationManager<MethodInvocationResult>`; `getResult()` chính là đối tượng `Document` được method trả về. Điều kiện `instanceof Document` tự bảo vệ trường hợp `null` hoặc kiểu không mong đợi, quyết định fail closed.
5. `Probe` là bean riêng để đếm **số lần method body thực thi**. Không đọc field của proxy CGLIB như thể đó luôn là state của target. Before deny cho số lần = 0; after deny cho số lần = 1.
6. Annotation `@WithMockUser` trên test class tạo Alice có authority `DOC_READ`. Test Bob, guest, và test thiếu quyền ghi đè principal/authority riêng. Giá trị `DOC_READ` là **authority chính xác**, không tự mang tiền tố `ROLE_`.
7. Trong Spring Security 6.5, `AuthorizationManager` vẫn là functional interface với method `check(...)` trừu tượng (dù đã đánh dấu deprecated), còn `authorize(...)` mặc định gọi vào đó. Vì thế lambda trả `AuthorizationDecision` chạy phù hợp với 6.5. Nếu chuyển sang Spring Security 7.x hoặc API khác, đối chiếu lại method trừu tượng và chữ ký generic theo version.

### 5.3. Lệnh chạy và kỳ vọng có thể kiểm chứng

Từ thư mục project có `build.gradle`:

```bash
gradle test --tests demo.InterceptorMethodSecurityTest
```

Nếu đã có Gradle Wrapper, dùng `./gradlew test --tests demo.InterceptorMethodSecurityTest` (Linux/macOS) hoặc `gradlew.bat test --tests demo.InterceptorMethodSecurityTest` (Windows).

Khi dependency, method security và Spring proxy được cấu hình đúng, kỳ vọng **sáu test thành công** và Gradle kết thúc bằng `BUILD SUCCESSFUL`. Đây là mô tả **expected behavior**, không phải bản sao stdout từ một lượt chạy thực tế.

| Test | Before | Body | After | Kết quả caller |
| --- | --- | --- | --- | --- |
| Alice đọc A/Alice | Allow | Chạy 1 lần | Allow | Nhận A |
| Bob đọc B/Bob | Allow | Chạy 1 lần | Allow | Nhận B |
| Alice thiếu `DOC_READ` | Deny | **Không chạy** | Không đến lượt | `AccessDeniedException` |
| Alice đọc B/Bob | Allow | Chạy 1 lần | **Deny** | `AccessDeniedException` |
| Alice đọc ID không tồn tại | Allow | Chạy 1 lần, trả `null` | **Deny** theo policy ví dụ | `AccessDeniedException` |
| Guest gọi `ping()` | Không match | Chạy | Không match | `"pong"` |

Test cuối chỉ chứng minh **hai custom advisor không áp dụng** cho phương thức không có annotation, không có nghĩa mọi người đều nên được gọi nó trong ứng dụng thật. Quyền HTTP, lớp service và nguyên tắc mặc định từ chối vẫn cần được thiết kế riêng.

## 6. Quan sát input và output ở Java manager

### Before: `MethodInvocation`

Một manager tùy chỉnh thường dùng tham số của method để kiểm tra tài nguyên trước khi xử lý:

```java
AuthorizationManager<MethodInvocation> byDocumentId =
    (authentication, invocation) -> {
        Object[] arguments = invocation.getArguments();
        String methodName = invocation.getMethod().getName();
        // Kiểm tra hợp đồng kiểu đối số của đúng method/pointcut.
        // Policy tùy chỉnh quyết định trên dữ liệu đáng tin phía server.
        return new AuthorizationDecision(
            "read".equals(methodName) && arguments.length == 1
        );
    };
```

**Đây chỉ là đoạn minh họa**, không phải quy tắc authorization đầy đủ: mã này không kiểm tra user hoặc owner và **không được dùng làm policy production**. Trong ứng dụng thật, cần kiểm tra `authentication.get()` và quyền đối với ID/tenant dựa trên dữ liệu đã xác minh; không tin `owner` do client gửi.

### After: `MethodInvocationResult`

Sau khi method hoàn thành, manager có thể kiểm tra `result.getResult()` và nếu cần truy ngược method:

```java
AuthorizationManager<MethodInvocationResult> ownerCheck =
    (authentication, invocationResult) -> {
        Object returned = invocationResult.getResult();
        boolean allowed = returned instanceof Document document
            && document.owner().equals(authentication.get().getName());
        return new AuthorizationDecision(allowed);
    };
```

Trong ví dụ, `Document` là record của bài; đoạn này dùng khi đã biết authentication có sẵn. Nếu phải hỗ trợ unauthenticated/anonymous hoặc dữ liệu `null`, hãy xử lý rõ ràng. `getMethodInvocation()` cho phép đối chiếu method/args khi cần.

Cách thiết kế tốt: **before kiểm tra quyền yêu cầu thao tác** (đặc biệt khi có side effect), **after kiểm tra chi tiết dữ liệu trả về**. Không đưa toàn bộ policy vào after nếu dữ liệu bí mật đã bị ghi vào log hay side effect trước khi after kiểm tra.

## 7. Pointcut và vòng đời `Advisor`

Hai interceptor đều có constructor nhận:

```java
new AuthorizationManagerBeforeMethodInterceptor(
    pointcut, beforeManager);

new AuthorizationManagerAfterMethodInterceptor(
    pointcut, afterManager);
```

- `pointcut`: xác định class/method cần kiểm soát, ví dụ `AnnotationMatchingPointcut` cho custom annotation hoặc `AspectJExpressionPointcut` cho nhóm service.
- `beforeManager`: phải là `AuthorizationManager<MethodInvocation>`.
- `afterManager`: phải là `AuthorizationManager<MethodInvocationResult>`.

Đây là API của **Spring AOP proxy**, không phải tuyên bố đã bật AspectJ bytecode weaving. `AspectJExpressionPointcut` dùng cú pháp biểu thức AspectJ nhưng vẫn có thể chỉ áp dụng theo proxy.

Với các annotation mặc định, có thể dùng factory `preAuthorize(...)` và `postAuthorize(...)` để Spring chọn pointcut dựa trên `@PreAuthorize`/`@PostAuthorize`. Với annotation riêng, constructor + pointcut làm mục tiêu rõ ràng hơn và tránh giả định SpEL vẫn được chạy sau khi manager đã bị thay.

**Thứ tự:** `AuthorizationInterceptorsOrder` có các mốc sắp xếp advisor Method Security. Nếu bạn có nhiều advisor, transaction hay logging, hãy cấu hình `setOrder(int)` khi thực sự cần và viết integration test xác minh call order; không dùng con số order tự đoán như hợp đồng cố định giữa mọi framework version.

**Trùng advisor:** `@EnableMethodSecurity` mặc định đã đăng ký before/after cho pre/post annotations. Nếu bạn tự thêm hai advisor khác dùng **cùng pointcut** mà không tắt hoặc kiểm soát default, một lời gọi có thể bị kiểm tra nhiều lần. Nếu hai rule độc lập, hãy mô tả chúng như điều kiện tích lũy và viết test cả trường hợp một rule allow, rule kia deny; nếu đang **thay thế**, dùng `prePostEnabled = false` với các advisor thay thế đã khai báo.

## 8. Quyết định quyền: allow, deny, abstain và exception

Trong Spring Security 6.5, manager trả về `AuthorizationDecision` hoặc các `AuthorizationResult` phù hợp:

```java
return new AuthorizationDecision(true);  // Allow
return new AuthorizationDecision(false); // Deny
```

Giá trị `null` trong contract manager nghĩa là **abstain/không đưa quyết định** ở những API hỗ trợ, **không đồng nghĩa deny**. Với một ranh giới nhạy cảm mà bạn sở hữu, thiết kế **explicit allow hoặc explicit deny** theo policy; không dựa vào `null` để fail closed.

Khi manager trả deny, hành vi thông thường của các interceptor là phát sinh `AccessDeniedException` (hoặc subtype `AuthorizationDeniedException` ở version hỗ trợ) và có thể phát sự kiện authorization nếu event publisher được cấu hình. Trong HTTP stack, Spring Security có thể chuyển exception thành 403 đối với người đã xác thực nhưng thiếu quyền, tùy `ExceptionTranslationFilter`, entry point và exception handling. Khi gọi service từ batch/scheduler hoặc test không có HTTP request, caller phải tự xử lý exception theo hợp đồng ứng dụng.

Không trả `true` mặc định khi thiếu dữ liệu authentication, sai kiểu result hoặc lỗi truy vấn policy. Các lỗi kỹ thuật nên được phân loại, log an toàn và test rõ ràng; không vô tình biến failure thành truy cập được phép.

## 9. Các bẫy đặc trưng

### 9.1. Test gọi thẳng `new Service()`

Spring AOP interceptor không chạy trên một instance do test tự tạo mà không qua proxy. Dùng `@SpringJUnitConfig`/Spring Boot Test, inject bean, rồi viết test một user bị deny **trước body** và một user bị deny **sau body**. Khi chỉ test case allow, việc thiếu proxy có thể không được phát hiện.

### 9.2. Self-invocation

`this.read(id)` gọi bên trong cùng target có thể bỏ qua interceptor trên `read` ở proxy mode. Cần đưa boundary được bảo vệ sang một bean khác hoặc dùng cơ chế được thiết kế có chủ đích, rồi kiểm thử đường gọi thật. Đừng cho rằng `@EnableMethodSecurity` hay chuyển JDK proxy sang CGLIB sẽ tự bảo vệ self-call.

### 9.3. `@PostAuthorize` không lọc danh sách

After manager thường đưa **một quyết định cho toàn giá trị trả về**. Nếu method trả `List<Document>`, việc `result.getResult()` là `List` không tự tạo ra `filterObject` hay lọc từng phần tử. Chọn `@PostFilter`/data-layer query cho lọc phần tử; với dữ liệu nhiều tenant hoặc phân trang, ưu tiên ràng buộc quyền ngay trong query.

### 9.4. After denial đã muộn cho thao tác ghi

Một phương thức có thể đã gọi repository, phát event hoặc gửi email rồi mới bị after manager từ chối trả result. Nếu policy nhằm cấm thao tác, đặt before rule hoặc policy check ở ranh giới transaction thích hợp. Đừng giả định exception sau cùng tự hoàn tác mọi side effect. Khi kết hợp `@Transactional`, xem xét order và rollback bằng kiểm thử database thực.

### 9.5. Null và kiểu kết quả

`MethodInvocationResult.getResult()` có thể là `null`. Kiểm tra kiểu với `instanceof` trước khi ép kiểu hoặc truy cập trường. Nếu method định nghĩa “không tìm thấy trả null” và sản phẩm muốn trả 404 thay vì deny, chính sách after phải phân biệt null hợp lệ với dữ liệu trái quyền; ví dụ trong bài cố ý **deny null** để bộc lộ chính sách fail closed.

### 9.6. Tên vai trò, tenant và dữ liệu không đáng tin

`hasRole("ADMIN")` thường đối chiếu `ROLE_ADMIN`, còn kiểm tra một authority literal `DOC_READ` phải khớp tên đúng. Với quyền theo tenant, kiểm tra ID/owner dựa trên bản ghi đáng tin phía server; không chỉ nhìn chuỗi `owner` do client đưa lên. Các luật phức tạp nên nằm trong policy service độc lập để có thể kiểm thử theo từng trường hợp.

### 9.7. Sync khác reactive

Hai class trong bài nhận `MethodInvocation`/ `MethodInvocationResult` đồng bộ. Reactive method security có các interceptor và manager **reactive** riêng, ví dụ `AuthorizationManagerBeforeReactiveMethodInterceptor` và `ReactiveAuthorizationManager`. Không áp dụng trực tiếp code đồng bộ cho `Mono`/`Flux` mà chưa xét thời điểm publisher phát tín hiệu, context và quyền.

### 9.8. Giao diện API theo phiên bản

Spring Security 6.5 còn có `check(Supplier<Authentication>, T)` trừu tượng đã deprecated và `authorize(...)` default; ví dụ ở đây dùng lambda tạo `AuthorizationDecision` tương thích 6.5. Các bản mới có thể chuyển trọng tâm sang `authorize(...)` như abstract method và sử dụng `AuthorizationResult`. Cần xem API đúng version trước khi copy một implementation `implements AuthorizationManager<...>` có `@Override`.

## 10. Quy trình chẩn đoán nếu interceptor không chạy

1. **Xác nhận cấu hình:** Có `@EnableMethodSecurity`, có đúng bean `Advisor`, có định dạng `@Bean @Role(ROLE_INFRASTRUCTURE)` thích hợp và không tắt toàn bộ advisor đang cần?
2. **Kiểm tra pointcut:** Class/method có annotation đúng `@Retention(RUNTIME)`, visibility được proxy intercept và không bị lệch giữa interface/implementation? Với pointcut expression, kiểm tra pattern thực sự match.
3. **Kiểm tra đường gọi:** Lời gọi qua Spring-injected bean hay `this.method()`/instance `new`?
4. **Kiểm tra AuthorizationManager:** Before có nhận `MethodInvocation` đúng method/args? After có thấy `MethodInvocationResult.getResult()` thực tế? `authentication.get()` có principal/authorities mong muốn?
5. **Kiểm tra deny:** Test user thiếu authority khẳng định **body không chạy**; test owner không khớp khẳng định **body chạy nhưng caller không nhận result**.
6. **Kiểm tra chồng policy:** Có default `@PreAuthorize`/`@PostAuthorize` advisor và custom advisor dùng chung pointcut không? Nếu có, kết quả của từng advisor được phối hợp như thế nào?
7. **Kiểm tra transaction/HTTP:** Exception được xử lý ở service, controller, exception translator hay scheduler? Có side effect trước after denial không?
8. **Kiểm tra bản nâng cấp:** Generic signature, `AuthorizationDecision`/`AuthorizationResult`, `check`/`authorize`, role naming và các thay đổi trong Spring Security version thực tế.

## 11. Bài tập củng cố

**Bài tập A — đổi policy before:** Thay `DOC_READ` bằng `DOC_AUDIT` trong before manager, giữ test principal chỉ có `DOC_READ` và quan sát method body không chạy. Sửa fixture authority rồi chạy lại.

**Bài tập B — after với tenant:** Mở rộng `Document` thành `Document(String id, String owner, String tenant)`; after manager so sánh tenant trong identity đáng tin với tenant bản ghi. Test trường hợp owner trùng nhưng tenant khác phải deny.

**Bài tập C — pointcut khác:** Thêm method `readSummary()` không có `@DocumentRead`; chứng minh custom advisor không áp dụng. Sau đó đánh dấu method và bảo đảm kiểu kết quả phù hợp policy (không ép mọi result thành `Document`).

**Bài tập D — kiểm thử side effect:** Thay `Probe` bằng một repository fake đếm số lần đọc/ghi. Test before deny không được gọi repository, còn after deny đã gọi đọc trước khi bị chặn. Giải thích vì sao không dùng after rule làm chốt duy nhất trước thao tác ghi.

**Bài tập E — thay thế annotation mặc định:** Dùng `@EnableMethodSecurity(prePostEnabled = false)` với factory `preAuthorize(customManager)` và `postAuthorize(customManager)`, thêm test chứng minh các biểu thức `@PreAuthorize`/`@PostAuthorize` không được tự đánh giá nếu manager mới không diễn giải chúng. Quyết định rõ phương án giữ SpEL hay chuyển toàn bộ policy sang Java.

## 12. Ghi nhớ

- **Before interceptor** = kiểm tra quyền **trước body**, nhận `AuthorizationManager<MethodInvocation>`.
- **After interceptor** = kiểm tra **kết quả sau body**, nhận `AuthorizationManager<MethodInvocationResult>` với `getResult()`.
- **Pointcut chọn phạm vi**, `AuthorizationManager` đưa quyết định; cấu hình advisor phải được Spring AOP đăng ký đúng.
- `@EnableMethodSecurity` đã bật các advisor mặc định; khi **thay thế** chúng, kiểm soát `prePostEnabled` để tránh trùng hoặc mất kiểm tra.
- **After authorization không phải filtering** và không hoàn tác side effect.
- Hãy test tối thiểu **allow**, **before deny/body không chạy**, **after deny/body đã chạy**, **null result**, **method ngoài pointcut** và **principal khác** qua Spring proxy.

## Tham khảo chính thức

- Spring Security 6.5 — Method Security, custom AuthorizationManager, advisor/pointcut và luồng pre/post: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — AuthorizationManagerBeforeMethodInterceptor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html
- Spring Security 6.5 API — AuthorizationManagerAfterMethodInterceptor: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html
- Spring Security API — MethodInvocationResult: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/MethodInvocationResult.html
- Spring Framework — AnnotationMatchingPointcut: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html
