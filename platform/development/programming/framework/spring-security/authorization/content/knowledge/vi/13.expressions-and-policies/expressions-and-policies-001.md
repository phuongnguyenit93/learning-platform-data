# SecurityExpressionRoot và ngữ cảnh biểu thức bảo mật trong Spring Security

## 1. Bài toán: một biểu thức biết gì về người dùng và tài nguyên?

Giả sử ứng dụng cần quy tắc: “Người sở hữu được đọc hóa đơn của mình; quản trị viên được đọc hóa đơn của mọi người”. Ta có thể gắn lên phương thức service:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
public Invoice readInvoice(@P("owner") String owner) {
    // Tải hóa đơn thuộc owner từ repository.
}
```

Đây là **mẫu chữ ký phương thức** (chưa phải chương trình chạy độc lập). Một biểu thức ngắn dùng được cả `hasRole`, tham số `#owner` và `authentication.name` là nhờ **ngữ cảnh đánh giá biểu thức bảo mật** (*security expression evaluation context*). Trung tâm của ngữ cảnh ấy là **`SecurityExpressionRoot`**: lớp gốc cung cấp những phép kiểm tra quyền và các thuộc tính bảo mật dùng chung khi Spring Security đánh giá SpEL.

Cần phân biệt:

- **Authentication** mô tả danh tính đang được xác thực, `principal` và tập `GrantedAuthority`.
- **SecurityContext** giữ `Authentication` liên quan đến luồng thực thi/ngữ cảnh hiện tại (theo `SecurityContextHolderStrategy`).
- **SecurityExpressionRoot** cung cấp API tiện lợi như `hasAuthority`, `hasRole`, `isAuthenticated`, `authentication` và `principal` để SpEL sử dụng.
- **EvaluationContext** của SpEL bao quanh root object và cung cấp biến tham số, bộ phân giải bean, truy cập thuộc tính/phương thức, bộ chuyển kiểu… tùy cấu hình của Spring Security.
- **AuthorizationManager** / interceptor sử dụng kết quả biểu thức để cho phép hoặc từ chối hành động.

Vì vậy `SecurityExpressionRoot` không phải “người dùng đang đăng nhập”, cũng không tự đóng vai trò là database quyền. Nó là **cầu nối ngữ nghĩa** giữa dữ liệu bảo mật do Spring quản lý và biểu thức ủy quyền do ứng dụng khai báo.

## 2. SecurityExpressionRoot nằm ở đâu trong kiến trúc?

`SecurityExpressionRoot` thuộc package:

```text
org.springframework.security.access.expression.SecurityExpressionRoot
```

Đây là **abstract class**, triển khai hợp đồng `SecurityExpressionOperations`. Trong Spring Security 6.x, những đối tượng root chuyên biệt quan trọng gồm:

| Ngữ cảnh | Root / thành phần liên quan | Dữ liệu đặc thù |
|---|---|---|
| Biểu thức Method Security | `MethodSecurityExpressionRoot` kế thừa `SecurityExpressionRoot`, triển khai `MethodSecurityExpressionOperations` | Tham số phương thức, `returnObject`, `filterObject`, đối tượng được gọi |
| Biểu thức HTTP/web | `WebSecurityExpressionRoot` kế thừa `SecurityExpressionRoot` | Ngữ cảnh request web, nếu dùng bộ đánh giá biểu thức web |
| Các trường hợp khác | Root/evaluation context do cơ chế bảo mật tương ứng cung cấp | Phụ thuộc tích hợp và phiên bản |

**Đặc biệt:** API `authorizeHttpRequests` hiện đại thường dùng `AuthorizationManager` kiểu Java, ví dụ `.hasAuthority("invoice:read")`. Không phải mọi cấu hình HTTP authorization đều khởi tạo hay đánh giá một chuỗi SpEL. Khi chủ động dùng `WebExpressionAuthorizationManager` thì biểu thức web mới là trọng tâm.

Với **Method Security** được bật bằng `@EnableMethodSecurity`, đường đi khái quát là:

```text
Một lời gọi vào Spring bean thông qua AOP proxy
    ↓
AuthorizationManagerBeforeMethodInterceptor (ví dụ: @PreAuthorize)
    ↓
PreAuthorizeAuthorizationManager
    ↓
MethodSecurityExpressionHandler
    ├── Authentication (thường được cung cấp qua Supplier<Authentication>)
    ├── MethodInvocation: method, target, arguments
    └── MethodSecurityEvaluationContext
          ├── root = MethodSecurityExpressionRoot
          ├── biến: #owner, #p0, ...
          └── bean reference: @invoicePolicy
    ↓
Đánh giá SpEL → true / false
    ├── true: cho phép chạy phương thức
    └── false: từ chối; thông thường ném AccessDeniedException
```

Với `@PostAuthorize`, đánh giá diễn ra **sau khi phương thức thực thi**, và `returnObject` đại diện kết quả trả về. Các hậu kiểm không hoàn tác tác dụng phụ đã xảy ra bên trong phương thức.

Một điểm kỹ thuật: cơ chế hiện đại trì hoãn lấy `Authentication` bằng `Supplier<Authentication>` để tránh công việc không cần thiết khi biểu thức như `permitAll` có thể quyết định mà không đọc danh tính. Không nên khởi tạo thủ công `SecurityExpressionRoot` để thay thế cơ chế này.

## 3. Những API mà SecurityExpressionRoot cung cấp

### 3.1. Danh tính và mức xác thực

| Biểu thức | Ý nghĩa và lưu ý |
|---|---|
| `authentication` | Đối tượng `Authentication` đang dùng để xét quyền |
| `principal` | Đối tượng `authentication.principal`, **kiểu cụ thể phụ thuộc cơ chế xác thực** |
| `authentication.name` | Định danh từ `Authentication#getName()`; thường an toàn hơn việc đoán kiểu principal |
| `isAuthenticated()` | Đã xác thực theo `AuthenticationTrustResolver`, không phải anonymous |
| `isAnonymous()` | Đang là anonymous theo trust resolver |
| `isRememberMe()` | Được xác thực qua remember-me (nếu ứng dụng có cơ chế này) |
| `isFullyAuthenticated()` | Đã xác thực đầy đủ, không phải anonymous hoặc remember-me |
| `permitAll` / `permitAll()` | Luôn cho phép |
| `denyAll` / `denyAll()` | Luôn từ chối |

Ví dụ:

```java
@PreAuthorize("isAuthenticated() and authentication.name == #owner")
public String readOwnData(@P("owner") String owner) {
    return "owner=" + owner;
}
```

Đoạn trên minh họa annotation trong Spring-managed service. Giá trị `authentication.name` lấy từ ngữ cảnh bảo mật do framework đưa vào biểu thức; tham số `#owner` đến từ `EvaluationContext` cho invocation hiện tại.

**`principal` không có cấu trúc cố định.** Với đăng nhập sử dụng `UserDetails`, có thể có `principal.username`. Với JWT resource server, principal có thể là `Jwt` với claims. Với `@WithMockUser` trong test, principal mặc định là một `UserDetails` kiểm thử, không tự có `claims`. Chỉ dùng các thuộc tính sau khi xác định kiểu principal thực tế của ứng dụng.

### 3.2. Quyền, role và permission

| Biểu thức | Quy tắc |
|---|---|
| `hasAuthority('invoice:read')` | Cần authority **khớp chính xác** `invoice:read` |
| `hasAnyAuthority('invoice:read', 'invoice:write')` | Cần ít nhất một authority phù hợp |
| `hasRole('ADMIN')` | Theo cấu hình mặc định, kiểm tra authority `ROLE_ADMIN` |
| `hasAnyRole('ADMIN', 'SUPPORT')` | Theo tiền tố role được cấu hình, cần ít nhất một role |
| `hasPermission(#invoice, 'read')` | Chuyển sang `PermissionEvaluator` để kiểm tra quyền trên đối tượng |
| `hasPermission(#id, 'Invoice', 'read')` | Dạng kiểm tra permission qua id và loại đối tượng |

Sự khác biệt thường gây lỗi:

```text
Authentication.authorities = ["ROLE_ADMIN", "invoice:read"]

hasRole('ADMIN')               => true   (mặc định có tiền tố ROLE_)
hasAuthority('ROLE_ADMIN')      => true   (khớp chính xác)
hasAuthority('ADMIN')           => false  (không tự thêm ROLE_)
hasAuthority('invoice:read')    => true
hasRole('invoice:read')         => false  (tìm ROLE_invoice:read mặc định)
```

Đây là **bảng kết quả minh họa** với cấu hình tiền tố mặc định và không có role hierarchy đặc biệt. Tiền tố role có thể được thay đổi (ví dụ bằng `GrantedAuthorityDefaults`) và `RoleHierarchy` có thể làm thay đổi kết quả kiểm tra; đừng hard-code giả định nếu hệ thống đã tùy biến.

`hasPermission(...)` là **điểm mở rộng**, không có nghĩa Spring tự hiểu chủ sở hữu, ACL, tenant hay bảng quyền nghiệp vụ. Cần cấu hình `PermissionEvaluator` thích hợp (và thường có query/bộ nhớ đệm). Nếu chưa làm, lời gọi không mặc nhiên cấp quyền truy cập đối tượng.

## 4. SpEL EvaluationContext: phân biệt root object, biến và bean

Một biểu thức trong `@PreAuthorize` có thể kết hợp nhiều nguồn dữ liệu:

```java
@PreAuthorize("hasAuthority('invoice:approve') and @invoicePolicy.canApprove(authentication, #amount)")
public String approve(@P("amount") long amount) {
    return "approved=" + amount;
}
```

Từ biểu thức trên:

1. `hasAuthority(...)` là **method trên root object**, vì thế không cần ghi `#root.hasAuthority(...)`.
2. `authentication` là **property của root object**.
3. `#amount` là **biến tham số phương thức**, được đăng ký trong evaluation context; ở đây `@P("amount")` bảo đảm tên ổn định.
4. `@invoicePolicy` là **Spring bean tham chiếu từ SpEL**, được giải bởi bean resolver.
5. `and` là toán tử SpEL, dùng phép logic ngắn mạch: nếu vế trái sai thì thường không gọi vế phải.

Các ký hiệu dễ nhầm:

| Ký hiệu | Ý nghĩa |
|---|---|
| `hasRole('ADMIN')` | Gọi phép kiểm tra bảo mật trên root |
| `authentication.name` | Đọc property qua root |
| `#root` | Biến đặc biệt của SpEL trỏ tới root object hiện tại |
| `#this` | Đối tượng đánh giá hiện tại của SpEL; có thể thay đổi khi dùng selection/projection |
| `#owner` | Biến tham số được phát hiện hoặc đăng ký trong evaluation context |
| `#p0` / `#a0` | Tham số phương thức thứ nhất (vị trí 0), hữu ích khi không biết tên biên dịch |
| `@invoicePolicy` | Spring bean tên `invoicePolicy` |
| `returnObject` | Giá trị trả về tổng thể trong hậu kiểm `@PostAuthorize` |
| `filterObject` | Phần tử đang xét trong `@PreFilter` hoặc `@PostFilter` |
| `this` (thuộc tính trong method root) | Tham chiếu đối tượng đích của method invocation; đừng nhầm với biến SpEL `#this` |

Trong ví dụ thông thường, `#root` là một `MethodSecurityExpressionRoot`. Một bean chính sách nâng cao có thể nhận chính đối tượng này qua `@policy.decide(#root)` với tham số `MethodSecurityExpressionOperations`.

**Dấu `#` quan trọng.** `#amount` trỏ tới biến tham số; `amount` đứng một mình sẽ được tìm như property/method của root và có thể báo lỗi. Tương tự `@invoicePolicy` tham chiếu bean; `#invoicePolicy` lại có nghĩa biến tên invoicePolicy, không phải bean.

### 4.1. Cách Spring lấy tên tham số

Dưới Method Security, cách ổn định nhất cho một ví dụ giáo dục là dùng annotation:

```java
import org.springframework.security.access.method.P;

@PreAuthorize("#accountId == authentication.name")
public String inspect(@P("accountId") String accountId) {
    return accountId;
}
```

Đây là phần code đặt **trong class/service**, nên chưa phải chương trình độc lập. Trong dự án thực tế, Spring còn có thể suy ra tên qua metadata `-parameters` khi biên dịch, hoặc các annotation được hỗ trợ như `@Param` của Spring Data. Nếu source không cung cấp thông tin tên, thay `#accountId` bằng `#p0` có thể tránh phụ thuộc vào tên tham số, nhưng ý nghĩa nghiệp vụ thường kém rõ hơn.

### 4.2. Biểu thức nhìn thấy những biến nào ở mỗi giai đoạn?

| Annotation / vị trí | Dữ liệu quan trọng |
|---|---|
| `@PreAuthorize` | Root bảo mật, `Authentication`, method arguments; kiểm tra **trước** khi chạy |
| `@PostAuthorize` | Như trên, **thêm `returnObject`** sau khi method trả kết quả |
| `@PreFilter` | `filterObject` là **từng phần tử đầu vào** của tập được lọc |
| `@PostFilter` | `filterObject` là **từng phần tử kết quả** được lọc sau khi method chạy |
| Web `WebExpressionAuthorizationManager` | Root web với authentication và dữ liệu request phù hợp |

`returnObject` không phải từ khóa bảo mật có mặt ở mọi `@PreAuthorize`. `filterObject` cũng không có nghĩa “cả danh sách”. Nếu kiểm tra từng phần tử hóa đơn sau khi truy vấn, ví dụ:

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Invoice> findAll() {
    return new ArrayList<>(invoiceRepository.findAll());
}
```

Đây là mẫu tích hợp cần có `invoiceRepository`, imports và class `Invoice` trong ứng dụng. Đầu ra phải là collection hỗ trợ loại phần tử trong lúc lọc; `List.of(...)` hoặc collection không thể sửa có thể gây lỗi khi `@PostFilter` cần xóa phần tử. Để xử lý phân trang/khối lượng lớn, nên lọc ngay trong query thay vì tải toàn bộ rồi hậu lọc.

## 5. Ví dụ Java 17 chạy được: kiểm tra root, tham số, bean và kết quả trả về

Ví dụ dùng **Java 17+, Spring Boot 3.5.14 (Spring Security 6.x), Maven và JUnit 5**. Chúng ta mô phỏng ba chính sách:

- `readStatement(owner)`: chỉ chủ sở hữu hoặc người có `ROLE_ADMIN` được đọc.
- `approve(amount)`: cần authority `invoice:approve` **và** được bean chính sách duyệt hạn mức.
- `findInvoice(id)`: chỉ chủ sở hữu hoặc admin nhận được hóa đơn đã tải.

Đặt các file Java theo package `com.example.expression`. Không cần database hay HTTP endpoint cho bài về Method Security này.

### 5.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.14</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-expression-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Application

**`src/main/java/com/example/expression/ExpressionApplication.java`**

```java
package com.example.expression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ExpressionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExpressionApplication.class, args);
    }
}
```

`@EnableMethodSecurity` kích hoạt interceptor cho các annotation như `@PreAuthorize` và `@PostAuthorize`. Spring Boot có auto-configuration cho Security, nhưng không mặc nhiên kích hoạt annotation method security nếu không bật cấu hình tương ứng.

### 5.3. Đối tượng nghiệp vụ và bean chính sách

**`src/main/java/com/example/expression/Invoice.java`**

```java
package com.example.expression;

public record Invoice(long id, String owner) {
    // Property JavaBean dùng cho SpEL: returnObject.owner
    public String getOwner() {
        return owner;
    }
}
```

**`src/main/java/com/example/expression/InvoicePolicy.java`**

```java
package com.example.expression;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("invoicePolicy")
public class InvoicePolicy {
    public boolean canApprove(Authentication authentication, long amount) {
        return authentication != null
            && authentication.isAuthenticated()
            && amount >= 0
            && amount <= 1000;
    }
}
```

Bean `invoicePolicy` chứa logic nghiệp vụ kiểm tra hạn mức. Hạn mức 1000 là **quy tắc mô phỏng**, không phải mặc định của Spring Security. Phương thức nhận `Authentication` để có thể mở rộng xét người dùng, tenant, authority hoặc dữ liệu hồ sơ.

### 5.4. Service được bảo vệ

**`src/main/java/com/example/expression/InvoiceService.java`**

```java
package com.example.expression;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    @PreAuthorize(
        "isAuthenticated() and (hasRole('ADMIN') or #owner == authentication.name)"
    )
    public String readStatement(@P("owner") String owner) {
        return "statement:" + owner;
    }

    @PreAuthorize(
        "hasAuthority('invoice:approve') and "
        + "@invoicePolicy.canApprove(authentication, #amount)"
    )
    public String approve(@P("amount") long amount) {
        return "approved:" + amount;
    }

    @PostAuthorize(
        "returnObject.owner == authentication.name or hasRole('ADMIN')"
    )
    public Invoice findInvoice(long id) {
        return new Invoice(id, id == 7L ? "alice" : "bob");
    }
}
```

Trong Java, các chuỗi annotation `@PreAuthorize` trên được ghép **lúc biên dịch** từ các string literal, nên hợp lệ như một hằng `String`. Nếu thích, có thể viết toàn bộ biểu thức trên một dòng. Không ghép đầu vào không tin cậy thành **mã SpEL** tại runtime.

### 5.5. Kiểm thử với các danh tính và quyền khác nhau

**`src/test/java/com/example/expression/InvoiceServiceTest.java`**

```java
package com.example.expression;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class InvoiceServiceTest {
    @Autowired
    private InvoiceService service;

    @Test
    @WithMockUser(username = "alice")
    void ownerMayReadOwnStatement() {
        assertEquals("statement:alice", service.readStatement("alice"));
    }

    @Test
    @WithMockUser(username = "bob")
    void userCannotReadOtherOwnerStatement() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.readStatement("alice")
        );
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminMayReadOtherOwnerStatement() {
        assertEquals("statement:alice", service.readStatement("alice"));
    }

    @Test
    @WithMockUser(username = "auditor", authorities = "invoice:approve")
    void authorityAndBeanBothApproveWithinLimit() {
        assertEquals("approved:500", service.approve(500));
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(1500)
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeLetsOwnerReceiveResult() {
        assertEquals("alice", service.findInvoice(7L).getOwner());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeDeniesNonOwnerResult() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.findInvoice(8L)
        );
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kỳ vọng:** Maven/JUnit chạy 6 test và **6 test pass** (`Failures: 0, Errors: 0`). Nhật ký Maven có thể thay đổi theo phiên bản và môi trường, vì vậy số test thành công là tiêu chí xác minh thay cho việc giả định stdout cố định.

Phân tích bốn tình huống trọng tâm:
- `alice` đọc `"alice"`: `#owner == authentication.name` đúng.
- `bob` đọc `"alice"`: không có `ROLE_ADMIN`, owner không trùng nên bị từ chối **trước** khi service chạy.
- `admin` đọc `"alice"`: `hasRole('ADMIN')` đúng nhờ `ROLE_ADMIN`.
- `auditor` có authority `invoice:approve` nhưng khoản 1500 vẫn bị từ chối vì `@invoicePolicy.canApprove(...)` trả `false`.
- `alice` gọi `findInvoice(8)`: method đã tạo `Invoice(owner="bob")`, sau đó `returnObject.owner` không khớp nên interceptor từ chối trả kết quả.

Những phép kiểm tra được thực hiện trên **bean do Spring tiêm vào**. Nếu tự khởi tạo `new InvoiceService()` trong test thuần hoặc gọi `this.approve(...)` từ một phương thức khác bên trong cùng bean (self-invocation), AOP advice có thể không chạy.

## 6. Tùy biến chính sách: ưu tiên bean thay vì sửa root trực tiếp

Khi biểu thức chứa nhiều nhánh hoặc truy vấn ACL, đừng chất tất cả nghiệp vụ vào một chuỗi khó kiểm thử. Spring Security cho phép gọi bean trong SpEL:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    return repository.getReferenceById(documentId);
}
```

Đây là **mẫu tích hợp**, giả định đã có `Document`, `repository` và bean `documentAccess`. Bean có thể chứa kiểm tra tenant, project membership và quyền trên record. Nếu kiểm tra tham số qua DB, cân nhắc số truy vấn, cache, race condition và việc đưa điều kiện quyền vào SQL để đảm bảo ranh giới truy cập dữ liệu.

Khi cần truyền toàn bộ root vào bean, có thể dùng `#root`:

```java
@Component("authorizationLogic")
public class AuthorizationLogic {
    public boolean canRead(MethodSecurityExpressionOperations root) {
        return root.hasAuthority("document:read");
    }
}
```

```java
@PreAuthorize("@authorizationLogic.canRead(#root)")
public Document readDocument(long id) {
    return repository.getReferenceById(id);
}
```

Hai đoạn trên là **mẫu tích hợp** (class đầu cần import `org.springframework.stereotype.Component` và `org.springframework.security.access.expression.method.MethodSecurityExpressionOperations`; phần service cần `Document` và `repository`). Khi nhận `#root`, bean có thể dùng `root.getAuthentication()` hoặc các method sẵn có trên `MethodSecurityExpressionOperations`; tuy nhiên cách này làm policy phụ thuộc nhiều hơn vào API Security. Thông thường truyền trực tiếp `authentication` và tham số nghiệp vụ giúp bean rõ ràng hơn.

### Khi thật sự muốn custom SecurityExpressionRoot

Có những hệ thống cũ mở rộng `DefaultMethodSecurityExpressionHandler` và override:

```java
// API tùy biến cũ: minh họa chữ ký, không phải giải pháp đề xuất
createSecurityExpressionRoot(Authentication authentication, MethodInvocation invocation)
```

Với `@EnableMethodSecurity` sử dụng `Supplier<Authentication>`, phương thức trên **không còn là điểm mở rộng phù hợp**: framework gọi `createEvaluationContext(Supplier<Authentication>, MethodInvocation)`. Nếu bắt buộc thay root, phải hiểu rõ `MethodSecurityExpressionOperations`, root delegate, bean registration và việc bảo toàn hành vi `getReturnObject()`, `getFilterObject()`. Cách sửa an toàn hơn cho phần lớn ứng dụng là thêm **bean policy** như trên hoặc định nghĩa `AuthorizationManager` chuyên dụng.

Nếu chỉ cần chỉnh tiền tố role hoặc role hierarchy, hãy dùng cấu hình tương ứng thay vì tạo một subclass `SecurityExpressionRoot` chỉ để xử lý từng phương thức.

## 7. Method Security và HTTP security dùng ngữ cảnh khác nhau

Ví dụ khai báo quyền HTTP hiện đại (đoạn trích bên trong cấu hình `SecurityFilterChain`):

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("report:read")
    .anyRequest().authenticated()
);
```

Đây là **Java DSL** xây các authorization manager; không có chuỗi SpEL cho mỗi matcher. Nếu thật sự cần tái sử dụng chuỗi biểu thức web, Spring Security 6.x có `WebExpressionAuthorizationManager`, ví dụ **mẫu cấu hình**:

```java
.requestMatchers("/reports/**")
.access(new WebExpressionAuthorizationManager("hasAuthority('report:read')"))
```

Khi áp dụng, cần import `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager` và đặt đoạn trên vào chuỗi cấu hình tương ứng. Root web có ngữ cảnh HTTP khác với root method. Không suy luận rằng biến `#owner` của service tự xuất hiện trong biểu thức web, hoặc biến `request` của web tự có sẵn trong mọi `@PreAuthorize`.

Bảo vệ tại request và method có thể kết hợp: HTTP rule quyết định ai vào endpoint, còn method rule kiểm tra owner/tenant/ID cụ thể ngay tại service. Để tránh đường gọi khác bỏ qua luật, phương thức service nhạy cảm nên có quy tắc phù hợp độc lập với URL.

## 8. Sai lầm phổ biến và cách khắc phục

**1. Nhầm `SecurityExpressionRoot` với `SecurityContext`.** Root cung cấp API SpEL; thông tin phiên đăng nhập đến từ `Authentication`. Không sửa root để “thay đổi người đăng nhập”.

**2. Nhầm role và authority.** `hasRole('ADMIN')` mặc định tìm `ROLE_ADMIN`, còn `hasAuthority('ADMIN')` tìm chính xác `ADMIN`. Kiểm tra mapping authority của JWT, LDAP, database hoặc `UserDetailsService` trước khi dùng.

**3. Dùng `principal.claims` cho mọi người dùng.** Kiểu `principal` khác nhau giữa mock user, session login, OAuth2 và JWT. Hãy xác định principal thực tế, hoặc sử dụng `authentication.name` khi chỉ cần user ID chuẩn hóa.

**4. Quên `#` trước tên tham số.** `#invoiceId` là biến invocation; `invoiceId` không có dấu `#` là property tìm trên root. Sử dụng `@P` hoặc compiler flag `-parameters` để chắc chắn tên được phát hiện.

**5. Không bật `@EnableMethodSecurity`.** Annotation vẫn biên dịch nhưng không tự kích hoạt interceptor tương ứng. Kiểm thử có `AccessDeniedException` là bằng chứng thiết thực của advice.

**6. Gọi method nội bộ bằng `this` hoặc tự tạo service với `new`.** Proxy của Spring AOP không nhìn thấy lời gọi self-invocation. Gọi từ bean khác qua Spring-managed proxy và thiết kế service boundary rõ ràng. Với private/final method, kiểm tra hỗ trợ proxy theo kiểu class/interface và cách cấu hình cụ thể.

**7. Tưởng `@PostAuthorize` bảo vệ thao tác ghi.** Nó chạy **sau** method; tài nguyên đã bị sửa trước khi quyền được xét. Kiểm tra quyền trước thao tác nguy hiểm bằng `@PreAuthorize` hoặc chính sách ở transaction/service tương ứng.

**8. Giả định `hasPermission` tự biết ACL.** Phải cung cấp `PermissionEvaluator` và chính sách cụ thể. Cẩn thận truy vấn quyền trong vòng lặp gây N+1.

**9. Ghép dữ liệu đầu vào thành chuỗi SpEL.** Biểu thức annotation nên là code/chính sách đáng tin do developer viết; giá trị người dùng nên đi qua biến `#param`, không được chèn trực tiếp như một phần mã biểu thức.

**10. Dùng biểu thức phức tạp, khó audit.** Chuyển logic nghiệp vụ dài sang bean, viết test cho nhánh allow/deny và theo dõi chính sách fail-closed khi thiếu dữ liệu tenant/owner. Không dựa vào việc che nút ở UI để thay cho authorization server-side.

**11. Không kiểm thử ranh giới khác.** Quy tắc method có thể bị bỏ qua nếu một endpoint khác gọi repository trực tiếp; HTTP authorization không thay thế quyền trên từng record. Bao phủ luồng gọi thật bằng test tích hợp và bảo vệ data access phù hợp.

## 9. Bảng ghi nhớ nhanh

| Thành phần | Cần nhớ |
|---|---|
| `SecurityExpressionRoot` | Base root object cho các phép kiểm tra bảo mật trong SpEL |
| `MethodSecurityExpressionRoot` | Root cho method security, mang ngữ cảnh invocation và hỗ trợ hậu kiểm/lọc |
| `EvaluationContext` | Root + biến `#arg` + `@bean` + khả năng truy cập thuộc tính/phương thức |
| `authentication` / `principal` | Thông tin danh tính, không phải biến do developer tự gán tùy ý |
| `hasRole` / `hasAuthority` | Role có tiền tố mặc định; authority khớp chính xác |
| `#root` / `#this` | Root object / đối tượng đánh giá hiện tại của SpEL |
| `returnObject` / `filterObject` | Kết quả toàn bộ / phần tử trong ngữ cảnh hậu kiểm hoặc lọc |
| `@EnableMethodSecurity` | Bật cơ chế đánh giá biểu thức qua Spring AOP cho method |
| `@bean.method(...)` | Mở rộng chính sách bằng code Java có thể kiểm thử |
| `AuthorizationManager` | Thành phần quyết định allow/deny từ kết quả kiểm tra |

**Nguồn tham khảo chính thức:**
- [Spring Security 6.5 — Method Security: Expressing Authorization with SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)

Nắm được cấu trúc **`Authentication → SecurityExpressionRoot → EvaluationContext → SpEL → AuthorizationManager`** giúp đọc một annotation dài thành các thành phần rõ ràng: đang kiểm tra **ai**, **quyền gì**, **trên tài nguyên nào**, **tại thời điểm nào** và **trong phạm vi nào**.