# Kết hợp quyền tĩnh với điều kiện động từ nghiệp vụ trong Spring Security

## 1. Bài toán: có quyền phê duyệt chưa đủ để phê duyệt mọi hồ sơ

Giả sử hệ thống quản lý hóa đơn dùng `Spring Security - authorization`. Nhân viên `alice` có authority `invoice:approve`, nhưng điều đó **không có nghĩa** cô ấy được duyệt mọi hóa đơn. Khi duyệt một hóa đơn, doanh nghiệp đồng thời yêu cầu:

- Người gọi có authority `invoice:approve`.
- Hóa đơn thuộc **cùng tenant** với người duyệt.
- Hóa đơn đang ở trạng thái `PENDING`.
- Tổng tiền hóa đơn không vượt hạn mức duyệt được cấp cho người này.
- Người duyệt **không phải người tạo** hóa đơn (nguyên tắc maker–checker).

Điều kiện đầu tiên là **quyền tĩnh**: một `GrantedAuthority` được cấp từ quá trình xác thực/phân quyền tổ chức. Các điều kiện tiếp theo là **quyền động**: quyết định thay đổi theo người gọi, trạng thái bản ghi, hạn mức, chính sách nghiệp vụ và thời điểm thực hiện.

Bài này hướng dẫn cách kết hợp chúng để **chỉ cho phép thao tác khi cả hai lớp điều kiện đều thỏa**. Trong ngữ cảnh cha **AuthorizationManager tùy chỉnh**, chúng ta sẽ tạo một `AuthorizationManager<MethodInvocation>` kết hợp hai quy tắc bằng `AuthorizationManagers.allOf(...)`, đăng ký một method-security interceptor có pointcut riêng và kiểm thử bằng Spring bean thật. Bài cũng trình bày lựa chọn ngắn gọn với `@PreAuthorize` và cách đóng khoảng hở giữa kiểm tra quyền và cập nhật database.

Mục tiêu sau bài:

1. Phân biệt authority/role với điều kiện nghiệp vụ trên từng tài nguyên.
2. Thiết kế phép kết hợp `STATIC AND DYNAMIC` theo nguyên tắc từ chối mặc định.
3. Hiểu `AuthorizationManager`, `AuthorizationDecision`, `MethodInvocation` và `AuthorizationManagerBeforeMethodInterceptor`.
4. Tạo một annotation nghiệp vụ riêng, kết nối nó với Spring AOP advisor và áp dụng vào service.
5. Chạy Java 17+ / Spring Boot, thấy kết quả cho phép hoặc từ chối của nhiều người dùng và tình huống.
6. Kiểm thử đúng Spring proxy, hạn chế self-invocation, chống giả mạo tenant/owner, xử lý concurrency và thu hồi quyền.

**Phạm vi:** Method Security theo cơ chế Spring AOP proxy trên Spring Security 6.x. Quy tắc web `authorizeHttpRequests(...)`, Spring Security ACL và OAuth2 scopes có liên quan nhưng không thay thế bài toán phê duyệt một bản ghi cụ thể.

## 2. Phân biệt quyền tĩnh, quyền động và các phép kết hợp

### 2.1. Quyền tĩnh là gì?

`Authentication` chứa một danh sách `GrantedAuthority`, ví dụ:

```text
alice:
  invoice:read
  invoice:approve

bob:
  invoice:read

carol:
  invoice:approve
```

Với Spring Security, `hasAuthority('invoice:approve')` tìm chính xác chuỗi authority `invoice:approve`. `hasRole('APPROVER')` trong cấu hình mặc định là cách viết thuận tiện để kiểm tra `ROLE_APPROVER`. Không được nhầm `APPROVER`, `ROLE_APPROVER` và `invoice:approve`: chúng chỉ tương đương nếu ứng dụng có quy tắc ánh xạ rõ ràng.

Authority phản ánh **năng lực chung**, chẳng hạn được phép mở tính năng phê duyệt, tạo báo cáo hay sửa đơn hàng. Nó không tự chứa trạng thái của từng hóa đơn, hạn mức hiện tại hoặc quyền sở hữu trong database.

### 2.2. Quyền động là gì?

Một quy tắc có thể viết dưới dạng hàm:

```text
canApprove(user, invoice, businessPolicy)
    = sameTenant(user, invoice)
      AND invoice.status == PENDING
      AND invoice.amount <= user.approvalLimit
      AND invoice.creator != user
```

Nguồn của `user.approvalLimit` và `invoice.status` phải **đáng tin cậy từ server**. Không coi header `X-Tenant`, trường `createdBy` hay `approvalLimit` trong JSON do client gửi là bằng chứng quyền. Trong ứng dụng thật, các thuộc tính này được xác minh qua token tin cậy kết hợp directory, repository hoặc ACL server.

Quyền động có thể còn phụ thuộc giờ làm việc, quy trình phê duyệt, trạng thái khóa, quota, thuộc nhóm, tenant, địa bàn, cấu hình sản phẩm hay tình trạng hợp đồng. Những điều kiện này nên được đặt trong lớp policy có thể kiểm thử, thay vì rải rác vào controller.

### 2.3. Vì sao là AND, không phải OR?

| Có `invoice:approve`? | Điều kiện nghiệp vụ đạt? | Kết quả |
| --- | --- | --- |
| Không | Không | Từ chối |
| Không | Có | Từ chối |
| Có | Không | Từ chối |
| Có | Có | Cho phép |

Biểu thức đúng:

```text
ALLOW = HAS_AUTHORITY("invoice:approve") AND BUSINESS_RULE_ACCEPTS
```

Nếu dùng `OR`, người có quyền tĩnh sẽ vượt qua mọi ràng buộc tenant/hạn mức/trạng thái, hoặc người không có authority vẫn có thể được phê duyệt chỉ vì hóa đơn phù hợp điều kiện khác. Chỉ dùng `OR` khi chính sách có một nhánh miễn trừ **được định nghĩa và kiểm soát rõ**, ví dụ quyền quản trị đặc biệt đã được đánh giá riêng; không tự thêm ngoại lệ `ADMIN` theo phỏng đoán.

**Mặc định từ chối:** khi thiếu user, target, trạng thái, hạn mức hoặc nguồn policy, kết quả là `false`. Không coi exception đọc dữ liệu là lý do để cấp quyền.

## 3. `AuthorizationManager` nằm ở đâu trong lời gọi?

Spring Security cung cấp interface `AuthorizationManager<T>` để đưa ra quyết định trước hoặc sau một thao tác. Với method security, `T` thường là `MethodInvocation` (trước method) hoặc `MethodInvocationResult` (sau method). Tham số quan trọng gồm:

- `Supplier<Authentication>`: cung cấp danh tính đang thực thi.
- `MethodInvocation`: method đích, target, các tham số và ngữ cảnh lời gọi.
- `AuthorizationDecision`: kết quả cho phép (`true`) hoặc từ chối (`false`), là một dạng `AuthorizationResult`.

Ở Spring Security 6.5, chữ ký `check(Supplier<Authentication>, T)` là phương thức trừu tượng cũ; `authorize(...)` có thể ủy quyền đến nó và được khuyến nghị cho API mới. Khi dùng **lambda `AuthorizationManager<T>`** ở phiên bản này, lambda trả `AuthorizationDecision`. Trong Spring Security 7, `authorize(...)` là chữ ký trừu tượng nên mã triển khai API trực tiếp có khác biệt về chữ ký; phải kiểm tra phiên bản trước khi nâng cấp. Phần ví dụ sau được cố định trên dòng Spring Security 6.x của Spring Boot 3.5.

Luồng thực thi:

```text
Caller -> Spring-managed ApprovalService proxy
                    |
                    v
       AuthorizationManagerBeforeMethodInterceptor
              (pointcut @ApproveInvoice)
                    |
                    v
       AuthorizationManagers.allOf(...)
              /                 \
             v                   v
    Static authorization    Dynamic authorization
    invoice:approve         policy.canApprove(auth, id)
              \                 /
               v               v
           DENY nếu bất kỳ điều kiện nào false
                    |
            granted? +--- no --> AccessDeniedException
                    |
                   yes
                    v
              ApprovalService.approve(id)
                    |
                    v
                  Database
```

**Hai việc khác nhau:** proxy/pointcut quyết định *lúc nào policy được gọi*, còn `AuthorizationManager` quyết định *được phép hay không*. Nếu caller tự tạo service bằng `new` hoặc gọi method nội bộ `this.approve(...)` trong cùng bean, có thể bỏ qua advice của phương thức bảo vệ. Annotation không tự bảo đảm kiểm tra ở mọi lời gọi Java.

## 4. Hai lối triển khai và khi nào chọn

### Cách A: `@PreAuthorize` + bean policy

Nếu chỉ một vài method cần kết hợp quy tắc, có thể viết:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #p0)"
)
public Invoice approve(Long invoiceId) {
    // ...
}
```

`#p0` là tham số thứ nhất. `authentication` được Spring Method Security đưa vào expression context. `@invoicePolicy` là một bean Spring có method `canApprove`. SpEL `and` diễn đạt rõ hai điều kiện đều cần đúng. Cách này dễ đọc và không cần tự tạo advisor.

### Cách B: custom `AuthorizationManager` + annotation riêng

Khi nhiều service dùng cùng một policy, cần Java thuần để kiểm thử, muốn gom nhiều manager và đặt pointcut rõ ràng, có thể dùng:

```java
@ApproveInvoice
public Invoice approve(Long invoiceId) {
    // ...
}
```

Annotation này **chỉ có tác dụng** khi có một advisor được đăng ký để nhận diện nó. Ta tự tạo advisor, kết hợp manager quyền tĩnh của Spring và manager nghiệp vụ.

Bài demo hoàn chỉnh dùng **cách B** để làm rõ bản chất `AuthorizationManager` tùy chỉnh. Cách A là lựa chọn thay thế hợp lệ; không nhất thiết áp dụng đồng thời cả hai lớp kiểm tra trên cùng một method.

## 5. Ví dụ hoàn chỉnh Java 17+: phê duyệt hóa đơn theo authority và chính sách động

Ví dụ dùng Spring Boot **3.5.8** (Java 17; Spring Security 6.5.x), Gradle và dữ liệu giả lập trong bộ nhớ. Không cần HTTP server hay database. Ứng dụng mô phỏng ba user:

| User | Tenant | Hạn mức | Authority |
| --- | --- | --- | --- |
| `alice` | `T1` | 1.000 | `invoice:approve` |
| `bob` | `T1` | 1.000 | `invoice:read` |
| `carol` | `T2` | 1.500 | `invoice:approve` |

Các hóa đơn demo có trạng thái và người tạo khác nhau để kiểm tra cả hai loại điều kiện. Tất cả số tiền trong bài là **đơn vị giả lập**, không có tỷ giá hay quy tắc tiền tệ.

### 5.1. Cấu trúc và dependency

```text
invoice-authorization-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── InvoiceAuthorizationApplication.java
    │   ├── Invoice.java
    │   ├── InvoiceStore.java
    │   ├── ApproverDirectory.java
    │   ├── InvoicePolicy.java
    │   ├── ApproveInvoice.java
    │   ├── InvoiceSecurityConfig.java
    │   └── ApprovalService.java
    └── test/java/demo/
        └── ApprovalServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'invoice-authorization-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` cung cấp Spring Security; `@EnableMethodSecurity` kích hoạt method security trong cấu hình. Đoạn kiểm tra cấp method vẫn dựa trên Spring AOP proxy. Gradle Wrapper không nằm trong danh sách file: có thể tạo Wrapper theo phiên bản Gradle hỗ trợ Spring Boot 3.5 nếu dự án chưa có.

### 5.2. Entity hóa đơn: dữ liệu từ phía server

**`src/main/java/demo/Invoice.java`:**

```java
package demo;

public record Invoice(
        long id,
        String tenant,
        String createdBy,
        long amount,
        State state) {

    public enum State {
        PENDING, APPROVED
    }
}
```

**`src/main/java/demo/InvoiceStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class InvoiceStore {

    private final Map<Long, Invoice> invoices = new ConcurrentHashMap<>();

    public InvoiceStore() {
        invoices.put(101L, new Invoice(
            101L, "T1", "mary", 700L, Invoice.State.PENDING));
        invoices.put(102L, new Invoice(
            102L, "T2", "mary", 500L, Invoice.State.PENDING));
        invoices.put(103L, new Invoice(
            103L, "T1", "mary", 1_500L, Invoice.State.PENDING));
        invoices.put(104L, new Invoice(
            104L, "T1", "mary", 200L, Invoice.State.APPROVED));
        invoices.put(105L, new Invoice(
            105L, "T1", "alice", 200L, Invoice.State.PENDING));
    }

    public Optional<Invoice> find(long id) {
        return Optional.ofNullable(invoices.get(id));
    }

    public Invoice approve(long id) {
        return invoices.compute(id, (key, current) -> {
            if (current == null) {
                throw new NoSuchElementException("Invoice not found: " + id);
            }
            if (current.state() != Invoice.State.PENDING) {
                throw new IllegalStateException("Invoice already processed");
            }
            return new Invoice(
                current.id(), current.tenant(),
                current.createdBy(), current.amount(),
                Invoice.State.APPROVED
            );
        });
    }
}
```

`ConcurrentHashMap.compute` thực hiện thao tác cập nhật một key một cách nguyên tử trong demo, nên không cho phép đổi `APPROVED` thêm lần nữa. **Nó không biến kiểm tra policy trước method thành transaction bảo mật nguyên tử**: trong sản phẩm thật phải bảo đảm quyền và dữ liệu không thay đổi ngoài dự kiến giữa thời điểm kiểm tra và cập nhật.

### 5.3. Danh mục hạn mức do server quản lý

**`src/main/java/demo/ApproverDirectory.java`:**

```java
package demo;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

record ApproverProfile(String tenant, long limit) {
}

@Component
public class ApproverDirectory {

    private final Map<String, ApproverProfile> profiles = Map.of(
        "alice", new ApproverProfile("T1", 1_000L),
        "bob",   new ApproverProfile("T1", 1_000L),
        "carol", new ApproverProfile("T2", 1_500L)
    );

    public Optional<ApproverProfile> find(String username) {
        return Optional.ofNullable(profiles.get(username));
    }
}
```

Bảng này mô phỏng một directory đáng tin cậy. Hạn mức không nằm trong tham số `approve(...)`, nên client không thể tự nâng hạn mức bằng cách chỉnh request body. Trong thực tế cần quản lý dữ liệu directory bằng cơ chế có kiểm soát và cân nhắc thời điểm cache/revoke.

### 5.4. Policy động, tách riêng khỏi controller và service

**`src/main/java/demo/InvoicePolicy.java`:**

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("invoicePolicy")
public class InvoicePolicy {

    private final InvoiceStore store;
    private final ApproverDirectory directory;

    public InvoicePolicy(InvoiceStore store, ApproverDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    public boolean canApprove(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        var profile = directory.find(authentication.getName()).orElse(null);
        var invoice = store.find(id).orElse(null);

        if (profile == null || invoice == null) {
            return false;
        }

        return profile.tenant().equals(invoice.tenant())
            && invoice.state() == Invoice.State.PENDING
            && invoice.amount() <= profile.limit()
            && !authentication.getName().equals(invoice.createdBy());
    }
}
```

`InvoicePolicy` chỉ quyết định **quyền động** theo dữ liệu server. Nó không tự cấp authority. Việc phân tách này giúp test từng phần: authority được kiểm tra ở manager tĩnh, còn ràng buộc tenant, trạng thái, hạn mức và maker–checker được kiểm tra trong policy.

Mọi trường hợp không xác định (không xác thực, profile không tồn tại, hóa đơn không có) đều trả `false`; đây là cách thiết kế **fail closed**. Ở hệ thống thật còn phải kiểm tra những ràng buộc như khóa tài khoản, trạng thái tạm ngừng, delegation, tenant hiện hành và phiên bản ACL khi nghiệp vụ yêu cầu.

### 5.5. Tạo annotation riêng

**`src/main/java/demo/ApproveInvoice.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface ApproveInvoice {
}
```

Annotation có runtime retention để pointcut nhận diện. Nó **chưa tự thực thi** bảo mật; phần tiếp theo phải đăng ký advisor tương ứng.

### 5.6. Kết hợp `AuthorityAuthorizationManager` và manager nghiệp vụ

**`src/main/java/demo/InvoiceSecurityConfig.java`:**

```java
package demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.core.Authentication;

@Configuration
public class InvoiceSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor invoiceApprovalAdvisor(InvoicePolicy policy) {

        // Điều kiện 1: authority cố định từ Authentication.
        AuthorizationManager<MethodInvocation> staticRule =
            AuthorityAuthorizationManager.hasAuthority("invoice:approve");

        // Điều kiện 2: nghiệp vụ động, dựa trên server-side policy.
        AuthorizationManager<MethodInvocation> dynamicRule =
            (authenticationSupplier, invocation) -> {
                Authentication authentication = authenticationSupplier.get();
                Object[] args = invocation.getArguments();

                if (args.length != 1 || !(args[0] instanceof Long id)) {
                    return new AuthorizationDecision(false);
                }

                return new AuthorizationDecision(
                    policy.canApprove(authentication, id)
                );
            };

        // Chỉ cho phép khi CẢ HAI quy tắc cho phép.
        AuthorizationManager<MethodInvocation> combined =
            AuthorizationManagers.allOf(staticRule, dynamicRule);

        // Chỉ intercept public method có @ApproveInvoice.
        return new AuthorizationManagerBeforeMethodInterceptor(
            AnnotationMatchingPointcut.forMethodAnnotation(
                ApproveInvoice.class),
            combined
        );
    }
}
```

**Giải thích từng bước:**

1. `AuthorityAuthorizationManager.hasAuthority("invoice:approve")` đọc `GrantedAuthority` từ `Authentication`; nó không đọc hóa đơn.
2. `dynamicRule` nhận `MethodInvocation`, kiểm tra đúng một tham số `Long`, rồi gọi `InvoicePolicy` để xét dữ liệu thực tế.
3. `AuthorizationManagers.allOf(staticRule, dynamicRule)` kết hợp hai manager theo kiểu **AND**. Cả hai trong ví dụ đều trả quyết định có giá trị rõ ràng, tránh tình huống `null`/abstain mơ hồ.
4. `AnnotationMatchingPointcut.forMethodAnnotation(ApproveInvoice.class)` xác định đúng method cần bảo vệ.
5. `AuthorizationManagerBeforeMethodInterceptor` yêu cầu quyết định cho phép **trước** khi chạy thân method.
6. `@Role(BeanDefinition.ROLE_INFRASTRUCTURE)` đánh dấu advisor là hạ tầng AOP. Nó không tự cấp quyền cho bất kỳ user nào.

Ở Spring Security 6.5, `AuthorizationManager` là functional interface dựa trên `check(...)`; lambda trong code trên là cách viết Java ngắn gọn, tương thích với dòng phiên bản được dùng. Nếu nâng lên Spring Security 7, hãy kiểm tra thay đổi API `authorize(...)` và dependency Spring Framework/Boot tương ứng. Không sao chép mã từ phiên bản khác rồi mặc định rằng mọi chữ ký vẫn giống nhau.

**Không dùng `anyOf` ở đây.** `anyOf` tương ứng OR và sẽ làm chính sách yếu đi. Nếu cần thêm các điều kiện như `isAccountActive` hoặc `isInApprovalWindow`, có thể thêm manager vào `allOf` hoặc tập trung vào policy, nhưng phải giữ được tính testable và quy tắc từ chối mặc định.

**Quan trọng:** advisor trên áp dụng cho method trực tiếp gắn `@ApproveInvoice`. Muốn bảo vệ class, interface, overloaded method hoặc meta-annotation thì phải thiết kế và kiểm thử pointcut tương ứng. Trong demo, annotation nằm trên một public method cụ thể để loại bỏ độ mơ hồ.

### 5.7. Service có một đường phê duyệt được bảo vệ

**`src/main/java/demo/ApprovalService.java`:**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ApprovalService {

    private final InvoiceStore store;

    public ApprovalService(InvoiceStore store) {
        this.store = store;
    }

    @ApproveInvoice
    public Invoice approve(Long id) {
        return store.approve(id);
    }
}
```

Không lặp lại authority check trong Java body vì advisor đã chịu trách nhiệm trước invocation. Tuy vậy, **đường ghi database thật cần ràng buộc trạng thái và quyền một cách nguyên tử** khi có nhiều người dùng cùng thao tác; đoạn service đơn giản chỉ làm rõ thời điểm kiểm tra của Spring Security.

Phương thức `approve` là `public` trong một `@Service` bean. Caller phải nhận bean từ Spring, không `new ApprovalService(...)` và không dựa vào self-invocation.

### 5.8. Bật Method Security, mô phỏng Authentication và chạy

**`src/main/java/demo/InvoiceAuthorizationApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class InvoiceAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvoiceAuthorizationApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(ApprovalService service) {
        return args -> {
            try {
                signInAs("alice", "invoice:approve");

                System.out.println("ALICE_101: "
                    + service.approve(101L).state());

                expectDenied("ALICE_REPEAT_101",
                    () -> service.approve(101L));
                expectDenied("ALICE_CROSS_TENANT_102",
                    () -> service.approve(102L));
                expectDenied("ALICE_OVER_LIMIT_103",
                    () -> service.approve(103L));
                expectDenied("ALICE_ALREADY_APPROVED_104",
                    () -> service.approve(104L));
                expectDenied("ALICE_SELF_APPROVAL_105",
                    () -> service.approve(105L));

                signInAs("bob", "invoice:read");
                expectDenied("BOB_NO_AUTHORITY_105",
                    () -> service.approve(105L));

                signInAs("carol", "invoice:approve");
                System.out.println("CAROL_T2_102: "
                    + service.approve(102L).state());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void signInAs(String username, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        SecurityContextHolder.getContext().setAuthentication(token);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@EnableMethodSecurity` bật các phần method security tiêu chuẩn; advisor tùy chỉnh ở `InvoiceSecurityConfig` được component scanning phát hiện thông qua `@Configuration`. `@Profile("!test")` ngăn scenario runner sửa trạng thái các hóa đơn khi chạy unit/integration test dùng profile `test`.

Trong ví dụ, `UsernamePasswordAuthenticationToken` được tạo thủ công **chỉ để mô phỏng một principal đã xác thực**; đây không phải luồng xác thực HTTP phù hợp cho production. Trong ứng dụng thật, danh tính phải đến từ cơ chế session/JWT/OIDC hoặc authentication provider được kiểm soát, kèm tenant/authority đáng tin cậy.

Chạy ứng dụng tại thư mục có `build.gradle`:

```bash
./gradlew bootRun
```

Trên Windows dùng `.\gradlew.bat bootRun`. Nếu chưa có Wrapper nhưng đã cài Gradle tương thích, có thể chạy `gradle bootRun`.

**Output mong đợi từ riêng những lệnh `System.out.println` của demo**, ngoài log khởi động Spring:

```text
ALICE_101: APPROVED
ALICE_REPEAT_101: DENIED
ALICE_CROSS_TENANT_102: DENIED
ALICE_OVER_LIMIT_103: DENIED
ALICE_ALREADY_APPROVED_104: DENIED
ALICE_SELF_APPROVAL_105: DENIED
BOB_NO_AUTHORITY_105: DENIED
CAROL_T2_102: APPROVED
```

Diễn giải:

- `alice` có authority `invoice:approve`, thuộc tenant `T1`, hạn mức 1.000; hóa đơn `101` là `PENDING`, thuộc `T1`, giá trị 700 và do `mary` tạo: **được duyệt**.
- Duyệt lại `101` không hợp lệ vì trạng thái đã đổi sang `APPROVED`.
- Hóa đơn `102` thuộc tenant khác, `103` vượt hạn mức, `104` đã duyệt và `105` do chính `alice` tạo: **policy động từ chối** dù authority tĩnh hợp lệ.
- `bob` thuộc `T1`, đủ hạn mức cho hóa đơn `105` và không phải người tạo, nhưng chỉ có `invoice:read`: **manager tĩnh từ chối**.
- `carol` có authority đúng, thuộc tenant `T2`, hạn mức 1.500 nên có thể duyệt `102`.

Kết quả minh họa đúng phép **AND**: chỉ hợp lệ khi cả authority và nghiệp vụ cùng đạt.

## 6. Kiểm thử tích hợp: chứng minh hai lớp quyền đều hoạt động

Tạo file **`src/test/java/demo/ApprovalServiceTest.java`**:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ApprovalServiceTest {

    @Autowired
    ApprovalService service;

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void approvesWhenBothStaticAndDynamicRulesPass() {
        assertEquals(
            Invoice.State.APPROVED,
            service.approve(101L).state()
        );

        // Cùng người, cùng authority, nhưng trạng thái đã thay đổi.
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void rejectsTenantLimitStatusAndSelfApprovalViolations() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(102L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(103L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(104L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(105L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "invoice:read")
    void rejectsWhenStaticAuthorityMissing() {
        // Bob có profile T1 và không tạo #105;
        // điều kiện nghiệp vụ có thể đạt nhưng authority thiếu.
        assertThrows(AccessDeniedException.class,
            () -> service.approve(105L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "invoice:approve")
    void allowsApproverInMatchingTenant() {
        assertEquals(
            Invoice.State.APPROVED,
            service.approve(102L).state()
        );
    }

    @Test
    @WithAnonymousUser
    void deniesAnonymousAccess() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }

    @Test
    @WithMockUser(username = "unknown", authorities = "invoice:approve")
    void failsClosedWhenServerProfileMissing() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }
}
```

Chạy:

```bash
./gradlew test
```

`@WithMockUser` và `@WithAnonymousUser` lấy từ `spring-security-test`. Mỗi test gọi `ApprovalService` do Spring inject, nên custom advisor **có cơ hội chặn lời gọi**. `@DirtiesContext` làm mới context sau từng test, tránh trạng thái của `ConcurrentHashMap` ở bài test trước ảnh hưởng bài test sau. Trong code thực tế, có thể thay cách này bằng reset test fixtures để tiết kiệm thời gian.

**Các ca quan trọng nhất**: người đủ authority nhưng sai tenant, người đúng tenant nhưng thiếu authority, người có đủ cả hai, tài nguyên đã chuyển trạng thái, principal không tồn tại trong directory và caller ẩn danh. Chỉ test đường “cho phép” là không chứng minh policy bảo mật được thực thi.

Để kiểm thử sâu hơn, có thể viết unit test trực tiếp cho `InvoicePolicy` với entity và profile đã biết, và test `AuthorizationManager` với `MethodInvocation` giả. Tuy nhiên **integration test qua Spring AOP** vẫn cần thiết để phát hiện lỗi pointcut, bean/proxy và cấu hình.

## 7. Những điểm kỹ thuật phải hiểu khi dùng custom AuthorizationManager

### 7.1. `allOf` chỉ an toàn khi không có quyết định mơ hồ

`AuthorizationManagers.allOf` hợp thành nhiều `AuthorizationManager` theo ngữ nghĩa tất cả cùng cho phép. Một số manager của Spring có thể trả `null` để **abstain**. Các overload/tình huống mọi manager abstain có quy tắc mặc định riêng, nên không nên coi `null` là từ chối trong mọi phiên bản.

Trong ví dụ, manager động **luôn trả `AuthorizationDecision(true/false)`**; manager quyền tĩnh cũng có quyết định rõ. Điều này loại bỏ trường hợp “không kiểm tra gì nhưng vẫn cho phép” do abstain. Nếu dùng nhiều manager tùy chỉnh, nên xác định rõ default-deny khi không có rule phù hợp, kể cả trường hợp không có manager nào hoặc toàn bộ abstain.

### 7.2. Phải áp dụng advisor đúng ranh giới

`@ApproveInvoice` là annotation tùy chỉnh **không phải `@PreAuthorize`**. Nếu chỉ tạo annotation và manager nhưng quên đăng ký `AuthorizationManagerBeforeMethodInterceptor`, method sẽ chạy như Java thông thường. Tương tự, `AnnotationMatchingPointcut` chỉ intercept những method khớp chính sách; **method khác không tự được bảo vệ**.

Với proxy mặc định:

- Gọi `service.approve(id)` qua Spring-managed bean: advisor được xét.
- Tự `new ApprovalService(store)`: không có proxy, bỏ qua advisor.
- Gọi `this.approve(id)` từ method khác trong cùng target: self-invocation có thể bypass.
- `private`/`final` method không phải ranh giới đáng tin cho subclass proxy; nên dùng public service method.
- Khi có JDK interface proxy, caller phải gọi qua interface method mà proxy cung cấp; test pointcut thực tế nếu annotation đặt trên interface.
- Cấu hình `@EnableMethodSecurity` và advisor phải được nạp trong đúng `ApplicationContext`.

Trong thiết kế nhiều service, có thể đặt method phê duyệt trong bean riêng và yêu cầu mọi đường gọi đi qua bean đó.

### 7.3. Không trộn ba loại dữ liệu nguồn

| Dữ liệu | Nguồn nên dùng | Không nên tin |
| --- | --- | --- |
| `Authentication` và authorities | Authentication provider/token đã kiểm chứng | Username hay role client tự gửi trong JSON |
| Tenant và hạn mức người duyệt | Server directory/claims đã xác minh + kiểm tra cập nhật | `X-Tenant` hoặc `limit` không được xác minh |
| Trạng thái/creator/amount hóa đơn | Repository/database server | DTO hóa đơn tự tạo từ request |

Policy phải kiểm tra **cùng bản ghi mà thao tác cập nhật sẽ tác động**. Không đọc quyền của tài liệu `A` rồi vô tình update tài liệu `B`; không tra owner từ DTO mà bỏ qua bản ghi thật.

### 7.4. Phép `AND` không tự bảo đảm atomicity

`@PreAuthorize` hay custom before-method interceptor kiểm tra tại thời điểm trước khi thân method chạy. Trong khoảng giữa **check** và **update**, bản ghi hoặc quyền của người gọi có thể thay đổi. Đây là TOCTOU (*time of check, time of use*).

Ví dụ race:

```text
T1: kiểm tra hóa đơn #101 đang PENDING, hạn mức đủ
T2: thay đổi hạn mức/tenant/owner của #101
T1: cập nhật #101 dựa trên quyết định cũ
```

Trong database quan hệ, một phương án là cập nhật có điều kiện, ràng buộc đúng bản ghi và đúng trạng thái/quyền tại thời điểm ghi:

```sql
UPDATE invoice
SET status = 'APPROVED'
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND status = 'PENDING'
  AND created_by <> :trustedActor
  AND amount <= :trustedApprovalLimit;
```

Đây là **minh họa SQL**, không phải file Java độc lập và cần điều chỉnh theo database/schema. Kiểm tra số hàng bị tác động (`1` nghĩa cập nhật thành công; `0` nghĩa điều kiện không còn thỏa hoặc bản ghi không tồn tại). Nếu policy gồm join/ACL phức tạp, có thể cần transaction, lock, version column hoặc tái kiểm tra quyền với dữ liệu nhất quán. Không dùng `@Transactional` như bằng chứng đủ để giải quyết mọi race nếu isolation không phù hợp.

**Tách trách nhiệm:** method security chặn trước khi vào nghiệp vụ, còn cập nhật DB có điều kiện bảo vệ tính đúng đắn khi dữ liệu thay đổi đồng thời.

### 7.5. Không giả định `Authority` sống mãi

Một authority có thể lấy từ token/JWT còn hiệu lực, còn policy động được lấy từ DB mới nhất. Nếu quyền bị thu hồi sau khi token cấp, những request dùng token cũ có thể vẫn mang authority trước đó đến khi token hết hạn hoặc token bị thu hồi theo cơ chế thích hợp. Với hành động quan trọng, cân nhắc kiểm tra quyền thực từ server, TTL ngắn, revocation hoặc policy version theo yêu cầu của hệ thống.

Mặt khác, không cache mãi kết quả `canApprove` vì trạng thái `PENDING` chuyển thành `APPROVED` ngay sau khi duyệt; nếu cache authorization, phải có khóa chứa user/tenant/resource/action và invalidation khi trạng thái hoặc quyền thay đổi.

### 7.6. Tương tác với cache, async và transaction

Spring Method Security, transaction advice và cache advice có thể cùng áp dụng trên Spring AOP proxy. Thứ tự advisor ảnh hưởng đến lúc nào policy chạy. Một `@Cacheable` bọc ngoài authorization có thể trả cache hit mà không vào thân method hoặc advice bên trong, tùy cấu hình; cần kiểm thử cả đường cache hit.

Với `@Async`, `SecurityContextHolder` dựa trên thread có thể không tự truyền đúng sang thread mới. Nếu có tác vụ async được bảo vệ, dùng cơ chế propagation (`DelegatingSecurityContext...`) và xác định rõ ai là chủ thể được kiểm tra.

Với `@Transactional`, kiểm tra có thể diễn ra trước hoặc trong ranh giới transaction tùy advisor order; đừng tự kết luận rằng policy động và update luôn nằm trong cùng một snapshot dữ liệu chỉ vì có hai annotation.

## 8. Lựa chọn ngắn hơn: cùng policy, dùng `@PreAuthorize` SpEL

Nếu không cần custom annotation/pointcut, có thể giữ `InvoicePolicy` và dùng:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #p0)"
)
public Invoice approve(Long id) {
    return store.approve(id);
}
```

Đây là **đoạn thay thế** method trong `ApprovalService`, không phải một method thứ hai cần thêm vào chương trình demo. Nó cần `@EnableMethodSecurity` và một Spring-managed `InvoicePolicy` bean; không cần tự khai báo advisor `@ApproveInvoice`.

Ưu điểm của SpEL: ngắn, dễ nhận ra chính sách ngay ở method, không cần lớp annotation riêng. Ưu điểm custom AuthorizationManager: phép kết hợp manager có thể dùng lại, logic Java dễ tách/kiểm thử, pointcut hoặc chính sách toàn tầng service có thể được quản lý tập trung.

Không dùng hai annotation `@PreAuthorize` lặp lại trên cùng một method: Spring Security không hỗ trợ lặp cùng annotation để làm phép AND. Hãy dùng **một** SpEL biểu thức có `and` hoặc một composed manager tương ứng.

## 9. Khi nào dùng `hasPermission`, `@PostAuthorize` hoặc chính sách khác?

- `hasPermission(#invoice, 'approve')` hoặc `hasPermission(#id, 'Invoice', 'approve')` phù hợp khi hệ thống có `PermissionEvaluator`/ACL ánh xạ quyền theo đối tượng. Có thể kết hợp với `hasAuthority` hoặc policy nghiệp vụ khác. `hasPermission` không mặc định biết trạng thái/hạn mức riêng.
- `@PreAuthorize` và before-method `AuthorizationManager` phù hợp khi quyết định phải có **trước side effect**, như phê duyệt, xóa hoặc chuyển tiền.
- `@PostAuthorize` phù hợp khi cần đọc kết quả rồi mới đánh giá quyền xem (`returnObject`). Không chỉ dùng hậu kiểm để bảo vệ thao tác đã ghi dữ liệu.
- Web `authorizeHttpRequests(...)` phù hợp để bảo vệ endpoint. Nó không thay thế cấp quyền cho service được gọi từ message listener, scheduler hay đường gọi nội bộ.
- ACL hoặc ABAC policy service có thể cung cấp dữ liệu cho manager động. Tên gọi RBAC (role/authority) và ABAC (attribute/status/tenant) giúp phân loại chính sách nhưng **không buộc ứng dụng phải dùng một framework riêng**.

Chọn công cụ theo điểm cần chặn và độ phức tạp của policy. Trong hệ thống có nhiều tổ chức, nên thiết kế tài nguyên và principal theo tenant trước, không bổ sung tenant check như bản vá muộn.

## 10. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Có authority nên mọi hóa đơn đều được duyệt | Dùng `OR` hoặc chỉ kiểm tra authority | Chuyển sang `allOf`/SpEL `and`, kiểm tra tenant/trạng thái/limit |
| Người không có authority vẫn duyệt được | Advisor không được đăng ký hoặc pointcut không khớp | Kiểm tra `@EnableMethodSecurity`, `@Bean Advisor`, `@ApproveInvoice` và proxy |
| Người dùng bị từ chối mọi hóa đơn | Sai chuỗi authority, profile thiếu, nguồn dữ liệu không khớp | Kiểm tra `GrantedAuthority` và thông tin policy server |
| Tài nguyên không tồn tại nhưng vẫn cho phép | Policy trả true khi `null` hoặc bỏ qua kết quả tra cứu | Trả `false` khi thiếu principal/resource/profile |
| Người khác tenant vẫn được duyệt | Lấy tenant từ client hoặc quên đối chiếu tenant của entity | Dùng tenant đã xác minh và dữ liệu DB |
| Người tạo có thể tự phê duyệt | Quên kiểm tra maker–checker | So sánh user ID đáng tin với `createdBy` của bản ghi thật |
| Hóa đơn đã duyệt vẫn được duyệt lại | Không kiểm tra trạng thái động | Check `PENDING` trước và ràng buộc trong cập nhật |
| Annotation hoạt động ở controller nhưng không ở service nội bộ | Self-invocation hoặc bean được tạo bằng `new` | Gọi qua Spring-managed proxy, tách bean nếu cần |
| Mất quyền nhưng token cũ vẫn duyệt được | Authority sống lâu, không có cơ chế revoke | Xem xét token lifecycle và kiểm tra server-side với hành động nhạy cảm |
| Dữ liệu đổi giữa kiểm tra và cập nhật | TOCTOU/race | Dùng conditional update/lock/version/transaction nhất quán |
| Chạy integration test nhưng rule không được gọi | Test chỉ mock service hoặc không nạp advisor | Dùng `@SpringBootTest` và verify cả allow lẫn deny |
| `allOf` với manager custom cho phép bất ngờ | Manager trả `null`/abstain hoặc cấu hình thiếu rule | Luôn trả quyết định tường minh; xác định default-deny |

Bước chẩn đoán có ích: kiểm tra `AopUtils.isAopProxy(service)`, xác minh method thực sự có `@ApproveInvoice`, kiểm tra `Authentication.getAuthorities()`, log/trace kết quả policy **mà không log nội dung nhạy cảm**, và tạo test một user có quyền cùng một user thiếu quyền trên **cùng một hóa đơn**.

## 11. Bài tập tự kiểm tra

1. **Một người có `invoice:approve` nhưng invoice thuộc tenant khác. Kết quả là gì?**  
   Từ chối: `STATIC=true`, `DYNAMIC=false`, `AND=false`.

2. **Một người cùng tenant, đủ hạn mức nhưng chỉ có `invoice:read`. Kết quả là gì?**  
   Từ chối: policy động có thể đúng nhưng authority tĩnh không đủ.

3. **Vì sao `AuthorizationManagers.anyOf(staticRule, dynamicRule)` không phù hợp?**  
   Vì OR cho phép một nhánh đúng bỏ qua nhánh còn lại, làm yếu chính sách.

4. **`@ApproveInvoice` đã được định nghĩa nhưng quên bean advisor. Điều gì xảy ra?**  
   Annotation không tự kích hoạt kiểm tra quyền. Phải có interceptor/pointcut phù hợp.

5. **Vì sao `InvoicePolicy` không nên đọc `tenant` từ request JSON rồi tin ngay?**  
   Vì client có thể giả mạo tenant; policy cần identity/tenant và dữ liệu entity đáng tin cậy.

6. **`AuthorizationManager<MethodInvocation>` nhận tham số method ở đâu?**  
   `invocation.getArguments()`; cần kiểm tra kiểu, số lượng và `null` trước khi sử dụng.

7. **Nếu `@PreAuthorize` cho phép rồi user khác đổi trạng thái invoice trước khi cập nhật thì sao?**  
   Có khoảng hở TOCTOU. Tầng ghi cần kiểm tra điều kiện ở thời điểm cập nhật, qua transaction/conditional update phù hợp.

8. **`@WithMockUser` test có đủ nếu gọi `new ApprovalService(...)` không?**  
   Không. Cần gọi qua Spring bean/proxy để kiểm thử advisor thực sự.

9. **Policy có nên mặc định cho phép khi directory tạm thời không có dữ liệu?**  
   Không. Nếu không xác nhận được quyền, phải fail closed; xử lý lỗi hạ tầng riêng theo chuẩn của hệ thống.

10. **Khi nào dùng `@PreAuthorize` với bean thay cho custom manager?**  
    Khi biểu thức AND đơn giản, số method không nhiều và không cần quản lý pointcut/manager ở mức framework.

## 12. Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, annotation-based authorization, custom bean trong SpEL, custom AuthorizationManager và interceptor.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority`, `AuthorizationManager` và composition.
- [Spring Security 6.5 — `AuthorizationManager` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): chữ ký `check` và `authorize` cho dòng 6.5.
- [Spring Security — `AuthorizationManagers` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf` và abstain.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): kiểm thử với `@WithMockUser` và Spring test context.
- [Spring Framework — Spring AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn proxy và self-invocation.

**Ghi nhớ:** quyền tĩnh xác định *người gọi được thực hiện loại thao tác nào*; quyền động xác định *người đó có được thực hiện thao tác trên bản ghi này, trong trạng thái hiện tại, theo chính sách hiện tại hay không*. Với phê duyệt hóa đơn, chỉ cấp quyền khi **cả hai đúng**, luôn dùng dữ liệu server đáng tin và bảo vệ ranh giới cập nhật trước thay đổi đồng thời.