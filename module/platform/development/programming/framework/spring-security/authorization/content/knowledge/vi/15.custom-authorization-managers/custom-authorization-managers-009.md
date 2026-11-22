# Pointcut tùy chỉnh và phạm vi phương thức được áp dụng trong Spring Security

## 1. Bài toán: chính sách đúng nhưng áp dụng nhầm phương thức

Giả sử hệ thống có các service:

- `ArchiveService.archive(id)`: thao tác lưu trữ tài liệu, yêu cầu authority `DOC_ARCHIVE`.
- `ArchiveService.preview(id)`: chỉ tạo bản xem trước, không phải thao tác lưu trữ.
- `OtherService.archive(id)`: phương thức trùng tên nhưng thuộc nghiệp vụ khác.

Yêu cầu là **chỉ chặn đúng `ArchiveService.archive(...)`**. Nếu pointcut quá rộng như `execution(* *..*.archive(..))`, có thể vô tình chặn cả `OtherService.archive(...)`. Nếu pointcut quá hẹp hoặc viết sai package/chữ ký, `ArchiveService.archive(...)` có thể **không bị chặn**, tạo lỗ hổng nếu ứng dụng dựa duy nhất vào advisor này.

Trong Spring Security, một `AuthorizationManager<MethodInvocation>` chịu trách nhiệm **quyết định cấp/từ chối quyền**. Còn **Spring AOP `Pointcut`** quyết định **phương thức nào sẽ đi qua `AuthorizationManagerBeforeMethodInterceptor`**. Hai trách nhiệm phải được thiết kế và kiểm thử độc lập.

Bài học này giúp bạn:

1. Hiểu điểm nối `Pointcut → Advisor → AuthorizationManager → method`.
2. Viết pointcut theo package, class, method, tham số, annotation hoặc bean.
3. Phân biệt phạm vi dự kiến với phạm vi **thực tế được proxy**.
4. Dùng pointcut đủ chặt để tránh bắt nhầm, đồng thời tránh bỏ sót phương thức cần bảo vệ.
5. Đăng ký custom method-security advisor đúng cách; hiểu tác động khi có `@PreAuthorize`, transaction và các advisor khác.
6. Viết kiểm thử bao gồm **positive coverage, negative coverage** và những đường gọi bypass AOP.

### Hai lỗi đối xứng cần tránh

| Lỗi | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Under-matching** | Pointcut nhắm `ArchiveService.approve(..)` trong khi method là `archive(..)` | Method cần chặn có thể chạy mà không qua advisor |
| **Over-matching** | Pointcut `execution(* demo..*Service.*(..))` | Các method không thuộc chính sách cũng bị deny, kể cả public/read-only |

Đừng chỉ viết một test “người không có quyền bị chặn”. Cần thêm test “method không thuộc pointcut **vẫn chạy đúng**” và test chứng minh **mọi method nhạy cảm đều được pointcut bao phủ**.

## 2. Kiến trúc: pointcut là phạm vi, manager là quyết định

Luồng trước lời gọi trong proxy mode:

```text
Caller
  |
  v
Spring-managed proxy
  |
  v
Advisor có Pointcut
  |
  +-- KHÔNG KHỚP ---------> gọi target method bình thường
  |
  +-- KHỚP
        |
        v
  AuthorizationManagerBeforeMethodInterceptor
        |
        v
  AuthorizationManager<MethodInvocation>
        |
        +-- GRANT ---------> gọi target method
        |
        +-- DENY ----------> AccessDeniedException
```

`Pointcut` chọn **join point** phù hợp. Trong Spring AOP thông thường, join point là **lần thực thi phương thức của Spring bean qua proxy**. `AuthorizationManager` nhận `Supplier<Authentication>` và `MethodInvocation` để quyết định cho phép hay không; nó có thể kiểm tra authority, tenant, dữ liệu tham số và chính sách nghiệp vụ.

Đừng đánh đồng với web request matcher:

| Phần | Chọn cái gì? | Đối tượng đầu vào |
| --- | --- | --- |
| `requestMatchers("/api/orders/**")` | HTTP request đi qua filter chain | Đường dẫn/phương thức HTTP |
| Spring AOP `Pointcut` | Method invocation đi qua AOP proxy | Class, method, signature, annotation, bean... |
| `AuthorizationManager<RequestAuthorizationContext>` | Quyết định quyền trên HTTP request đã match | Request và biến path |
| `AuthorizationManager<MethodInvocation>` | Quyết định quyền trên lời gọi service đã match | Caller identity, target, arguments |

Một HTTP endpoint có thể gọi nhiều service. Một service có thể được gọi từ HTTP, scheduler hoặc message consumer. Custom method-security pointcut bảo vệ **phương thức đi qua proxy** từ các entry point ấy, không bị ràng buộc vào một URL cụ thể.

### Điểm cần nhớ về `@EnableMethodSecurity`

Với Spring Security 6.x, cấu hình:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

bật những advisor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` theo cấu hình mặc định. **`spring-boot-starter-security` một mình không tự bật method-level authorization.** Một custom `Advisor` có pointcut riêng có thể được đăng ký cùng các advisor mặc định; đây là mở rộng **bổ sung** nếu bạn không chủ động tắt các advisor hiện có.

## 3. `Pointcut` có thể kiểm tra những yếu tố nào?

Spring AOP cung cấp `Pointcut` với **ClassFilter** và **MethodMatcher**. ClassFilter giúp loại trước các type không nằm trong phạm vi; MethodMatcher xét method/signature, đôi khi cần thông tin runtime tùy pointcut.

Với biểu thức AspectJ trong Spring AOP, các designator phổ biến:

| Cú pháp | Ý nghĩa | Trường hợp phù hợp |
| --- | --- | --- |
| `execution(...)` | Khớp thực thi method theo tên, kiểu, tham số, visibility | Chọn service/method rất rõ |
| `within(typePattern)` | Giới hạn các method khai báo trong nhóm type/package | Khoanh vùng một module |
| `@annotation(MyAnnotation)` | Method mang annotation phù hợp | Chính sách đánh dấu rõ theo method |
| `@within(MyAnnotation)` | Method trong các type có annotation phù hợp | Chính sách gắn theo class |
| `target(SomeType)` | Target object có type phù hợp | Dựa theo loại target |
| `this(SomeType)` | Proxy có type phù hợp | Cần hiểu JDK/CGLIB proxy |
| `args(TypePattern)` | Kiểm tra kiểu đối số khi gọi | Trường hợp cần match theo runtime types |
| `bean(namePattern)` | Khớp tên Spring bean; extension của Spring AOP | Dựa vào quy ước tên bean |

Spring AOP không hỗ trợ toàn bộ cú pháp pointcut của AspectJ weaving. Những designator như `call`, `get`, `set`, `withincode` hoặc `cflow` **không phải** công cụ để bắt tùy ý method call/field access trong Spring AOP proxy mode. Muốn chặn trực tiếp lời gọi nội bộ hoặc truy cập field, cần xem mô hình AspectJ weaving khác với Spring proxy.

### Cú pháp `execution`

Một pattern thường gặp:

```text
execution(modifiers-pattern? return-type declaring-type?.method-name(parameters))
```

Ví dụ:

```java
// Chọn mọi public method của service trong package và các package con.
"execution(public * com.acme.billing..*Service.*(..))"

// Chọn method tên archive thuộc class cụ thể, mọi overload.
"execution(public * com.acme.docs.ArchiveService.archive(..))"

// Chọn một chữ ký nhận đúng một đối số long primitive.
"execution(public * com.acme.docs.ArchiveService.archive(long))"

// Chọn method bắt đầu với approve trong service của module.
"execution(public * com.acme.billing..*Service.approve*(..))"

// Chỉ method có annotation đã định nghĩa ở ứng dụng.
"@annotation(com.acme.security.RequiresApproval)"
```

Các dòng trên là **chuỗi biểu thức pointcut**, không phải thân class Java độc lập. `*` có thể match một phần tên/kiểu; `..` trong tham số `(..)` khớp số lượng và loại đối số bất kỳ; `..` trong type pattern cho phép đi qua các package con. `()` chỉ khớp method không có đối số, `(long)` chỉ khớp đúng kiểu primitive `long`. `Long` và `long` **khác nhau** trong signature.

Trong `execution(public * com.acme.docs.ArchiveService.archive(..))`:

- `public`: chỉ chọn method public.
- `*` đầu tiên: return type bất kỳ.
- `com.acme.docs.ArchiveService`: declaring type mong muốn.
- `archive`: đúng tên method.
- `(..)`: mọi số lượng và kiểu đối số; **có thể match nhiều overload**.

Nếu policy đọc tham số đầu là ID `long`, việc chọn `archive(..)` rồi **thêm một overload nhận DTO** có thể làm manager parse sai hoặc deny sai. Nên cân nhắc pattern chữ ký hẹp hơn, hoặc kiểm tra dữ liệu đầu vào đầy đủ trong manager và có regression test sau khi thay đổi chữ ký.

## 4. Viết pointcut sao cho đúng phạm vi

### 4.1. Giới hạn theo package

```java
"execution(public * com.example.learning.authorization.service..*.*(..))"
```

Ý định: áp dụng cho public method thuộc namespace service đã chọn và các package con. Rủi ro: nếu đặt cả truy vấn chỉ đọc, health-check hoặc helper vào namespace ấy, manager có thể vô tình deny các method không cần bảo vệ. Nếu dự án di chuyển package, pointcut có thể bỏ sót.

### 4.2. Giới hạn theo class/method

```java
"execution(public * com.example.learning.authorization.ArchiveService.archive(..))"
```

Ý định: bảo vệ nghiệp vụ `archive` trên type cụ thể. Đây là lựa chọn thích hợp khi phạm vi có ít service ổn định. Rủi ro: đổi tên class/method hoặc thêm dịch vụ khác với cùng trách nhiệm có thể khiến rule không bao phủ đối tượng mới.

### 4.3. Kết hợp AND/OR

```java
"within(com.acme.billing..*) && execution(public * *.approve(..))"
```

Chỉ áp dụng khi **cả hai** điều kiện cùng đúng. Dùng `||` khi muốn nhiều tập method nhận cùng chính sách:

```java
"execution(public * com.acme.billing.InvoiceService.approve(..))"
    + " || "
    + "execution(public * com.acme.billing.PaymentService.release(..))"
```

Trước khi dùng `!` (phủ định), đánh giá toàn bộ đường gọi và các method tương lai. Một biểu thức `!within(..internal..)` thiếu ranh giới allowlist có thể áp dụng tới **rất nhiều** bean không chủ đích. Giới hạn theo module/package trước, sau đó mới thêm điều kiện loại trừ.

### 4.4. Giới hạn theo annotation

```java
"@annotation(com.acme.security.RequiresArchivePermission)"
```

Phù hợp khi muốn một dấu hiệu rõ ràng trong mã: mỗi method có annotation ấy phải qua policy. Cần khai báo annotation runtime retention, đúng target, và test với method trên interface/implementation. Không mặc định các meta-annotation, annotation thừa kế hoặc proxy mode được match giống cơ chế tìm `@PreAuthorize` của Spring Security.

### 4.5. Giới hạn theo tên bean

```java
"bean(document*Service) && execution(public * *.archive(..))"
```

`bean(...)` là designator **riêng của Spring AOP**, xét tên instance bean. Nó có thể hữu ích khi cùng một class được đăng ký với nhiều tên bean nhưng chỉ một instance cần chính sách khác. Hãy test tên bean thực tế trong `ApplicationContext` và hiểu rằng đổi tên bean có thể làm phạm vi thay đổi. Cách này không tương đương với AspectJ bytecode weaving.

### 4.6. `@annotation` so với pointcut có class name cứng

| Tiêu chí | Theo class/method signature | Theo annotation |
| --- | --- | --- |
| Rule đặt ở đâu? | Chủ yếu trong config | Dấu hiệu trên method và policy trong config |
| Đổi tên method/class | Dễ cần sửa biểu thức | Annotation có thể đi theo method |
| Rủi ro quên bảo vệ method mới | Cao nếu không cập nhật pattern | Cao nếu quên gắn annotation |
| Có thể kiểm tra phạm vi bằng grep/test? | Có | Có |
| Policy áp dụng theo convention không annotation | Rất phù hợp | Không cần thiết |
| Ảnh hưởng của proxy/interface/meta-annotation | Phải test | Cũng phải test |

Không có một cách luôn đúng. Chọn cách ít gây **bỏ sót nguy hiểm** nhất trong quy trình code review và kiến trúc nhóm.

## 5. Đăng ký pointcut với `AuthorizationManagerBeforeMethodInterceptor`

Spring Security cung cấp constructor:

```java
new AuthorizationManagerBeforeMethodInterceptor(
        Pointcut pointcut,
        AuthorizationManager<MethodInvocation> manager);
```

`AuthorizationManagerBeforeMethodInterceptor` là một Spring AOP advisor/interceptor. Khi `Pointcut` match lời gọi, interceptor lấy `Authentication` rồi hỏi manager có cho phép thực thi hay không. Nếu deny, thông thường `AccessDeniedException` được ném và thân method không chạy.

Ví dụ gắn authority chuẩn vào một method mà không cần tự triển khai thuật toán permission:

```java
@Configuration
@EnableMethodSecurity
class ArchiveSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor archivePointcutAdvisor() {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();

        pointcut.setExpression(
                "execution(public * demo.ArchiveService.archive(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut,
                AuthorityAuthorizationManager.hasAuthority("DOC_ARCHIVE")
        );
    }
}
```

Imports:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Đây là **đoạn tích hợp** cho ứng dụng có class `demo.ArchiveService`. Trong ví dụ chạy hoàn chỉnh ở phần 8, các lớp và file đều được cung cấp.

Điểm quan trọng:

- `@Bean` đăng ký advisor vào context; `@Role(ROLE_INFRASTRUCTURE)` đánh dấu vai trò hạ tầng; `static` giúp khai báo advisor sớm trong giai đoạn tạo bean.
- `AspectJExpressionPointcut` làm rõ tập method; expression literal phải khớp **package và chữ ký thực tế**.
- `AuthorityAuthorizationManager.hasAuthority(...)` nhận `MethodInvocation` theo generic type suy ra ở constructor; không cần tự kiểm tra authorities bằng vòng lặp Java.
- Đăng ký advisor trên **không mặc định tắt** những advisor `@PreAuthorize`/`@PostAuthorize` có sẵn.
- Cần Spring AOP proxy support và, khi dùng biểu thức AspectJ, dependency AspectJ parser/weaver thích hợp (ví dụ `spring-boot-starter-aop` trong demo).
- Method được chặn phải đi qua Spring-managed proxy; chỉ có `@Service` trên class chưa đủ nếu caller cố tình gọi instance tạo bằng `new`.

## 6. Pointcut tự viết khác gì annotation `@PreAuthorize`?

Annotation:

```java
@Service
class ArchiveService {

    @PreAuthorize("hasAuthority('DOC_ARCHIVE')")
    public void archive(long id) {
        // ...
    }
}
```

Tại đây Spring Security có **pointcut tích hợp sẵn** nhận ra `@PreAuthorize`. Không cần custom advisor để kiểm tra authority đơn giản. Custom pointcut hữu ích khi muốn một **chính sách dùng chung trên hàng loạt method theo convention**, tránh lặp annotation, hoặc cần một manager Java áp dụng trên pointcut được xác định tập trung.

So sánh:

| Cách tiếp cận | Khi nên dùng |
| --- | --- |
| `@PreAuthorize` trên method/class | Chính sách hiện rõ nơi viết nghiệp vụ; điều kiện SpEL ngắn, dễ review |
| Bean policy trong `@PreAuthorize("@policy...")` | Logic quyền phức tạp nhưng ranh giới vẫn rõ bằng annotation |
| Custom advisor với `Pointcut` + `AuthorityAuthorizationManager` | Áp dụng một authority policy cho nhiều method theo quy ước/tên/package |
| Custom advisor với `Pointcut` + `AuthorizationManager<MethodInvocation>` riêng | Cùng policy Java tùy biến được áp dụng cho tập method xác định rõ |
| Tự thay toàn bộ interceptor mặc định | Khi thật sự cần thay ngữ nghĩa ở cấp hạ tầng, phải xem tác động toàn ứng dụng |

Nếu một method match cả custom advisor và `@PreAuthorize`, các kiểm tra có thể **cùng được thực thi**; đừng giả định custom advisor thay thế annotation hoặc tạo một nhánh OR ngầm. Cần xác định rõ việc chồng nhiều chính sách là mong muốn (thông thường đều phải grant khi các advice thực thi) và kiểm thử thứ tự.

## 7. Phạm vi pointcut và phạm vi proxy là hai lớp điều kiện

Một biểu thức đúng chưa đủ để method được chặn. Phải có **lời gọi đi qua proxy có advisor tương ứng**.

```text
Phạm vi mong muốn (business)
       ∩
Phạm vi Pointcut thực tế match
       ∩
Các method/lời gọi có thể AOP intercept
       =
Những lời gọi thật sự được custom manager kiểm tra
```

Ví dụ các đường gọi:

```java
ArchiveService bean = context.getBean(ArchiveService.class);
bean.archive(42L);          // Qua proxy: custom advisor có thể chặn.

ArchiveService direct = new ArchiveService();
direct.archive(42L);        // Không qua Spring proxy: advisor không chạy.
```

Đây là đoạn minh họa tham chiếu; class, ApplicationContext và cấu hình bean phải có sẵn để chạy. Trường hợp self-invocation:

```java
@Service
class ArchiveService {

    public String runInternally(long id) {
        return this.archive(id);   // Gọi nội bộ vào target, bypass proxy.
    }

    public String archive(long id) {
        return "archived-" + id;
    }
}
```

Dù `runInternally` được gọi trên một Spring proxy, khi execution đã vào target, `this.archive(id)` **không tự quay lại proxy**. Advisor bảo vệ `archive` không được thực thi trên đường gọi nội bộ đó trong proxy mode.

### JDK proxy, CGLIB và visibility

- JDK dynamic proxy chủ yếu đưa ra interface methods; caller nên giữ interface reference.
- Class-based (CGLIB) proxy có thể intercept các method phù hợp trên class; nhưng `final class` không thể subclass, `final method` không thể override, `private method` không thể được intercept theo cách này.
- Method security và transaction thường được đặt tại **public service boundary** vì dễ dự đoán hành vi trên cả hai loại proxy.
- Annotation đặt ở interface hay implementation có thể ảnh hưởng việc một custom `@annotation` pointcut match thực tế; test type cụ thể và proxy strategy, đừng chỉ nhìn source.
- Khi một class/method đổi thành `final` (thường gặp khi dùng Kotlin không mở class), kiểm tra lại cơ chế proxy.

Không giải quyết thiếu coverage bằng cách viết pointcut `execution(* *(..))` quá rộng. Sửa nguyên nhân: đăng ký đúng bean, đường gọi qua proxy, pointcut match đúng target, và bảo vệ ranh giới nghiệp vụ.

## 8. Ví dụ Java 17/Spring Boot hoàn chỉnh, chạy được

Demo này dùng **Spring Boot 3.5.16** (Spring Security 6.x) và Java 17; phiên bản 3.5.16 có trên Maven Central nhưng đã kết thúc hỗ trợ OSS của dòng 3.5.x. Với sản phẩm thực tế, hãy chọn nhánh Boot/Security còn hỗ trợ và kiểm tra các API tương ứng.

Mục tiêu demo:

1. Không gắn `@PreAuthorize` lên `ArchiveService.archive`.
2. Dùng **custom pointcut** bắt đúng `demo.ArchiveService.archive(..)`.
3. Chặn người thiếu `DOC_ARCHIVE` qua proxy.
4. Cho phép người đủ `DOC_ARCHIVE`.
5. Chứng minh `preview` và `OtherService.archive` nằm ngoài phạm vi pointcut.
6. Chứng minh lời gọi qua instance `new` và self-invocation bypass advisor.

### 8.1. Cấu trúc thư mục

```text
pointcut-scope-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── PointcutScopeApplication.java
    │   ├── ArchiveService.java
    │   └── OtherService.java
    └── test/java/demo/
        └── PointcutScopeTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>pointcut-scope-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
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

`spring-boot-starter-aop` cung cấp AOP/AspectJ weaving library cần cho biểu thức `AspectJExpressionPointcut`. Demo chạy bằng `CommandLineRunner` và không mở web server.

### 8.3. `ArchiveService.java`

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ArchiveService {

    public String archive(long id) {
        return "archived-" + id;
    }

    public String preview(long id) {
        return "preview-" + id;
    }

    public String internalArchive(long id) {
        return this.archive(id);
    }
}
```

Không có annotation method security tại `archive`. Chính `Pointcut` sẽ xác định method đó có bị chặn hay không.

### 8.4. `OtherService.java`

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OtherService {

    public String archive(long id) {
        return "other-" + id;
    }
}
```

Service này có method cùng tên `archive` để kiểm tra **điểm ngoài phạm vi**. Nếu người thiếu quyền gọi `OtherService.archive` cũng bị từ chối, nghĩa là pointcut của demo đã viết quá rộng.

### 8.5. `PointcutScopeApplication.java`

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PointcutScopeApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PointcutScopeApplication.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner chạy trước khi SpringApplication.run trả về.
        }
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor archiveAdvisor() {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public * demo.ArchiveService.archive(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut,
                AuthorityAuthorizationManager.hasAuthority("DOC_ARCHIVE"));
    }

    @Bean
    CommandLineRunner runDemo(
            ArchiveService managedArchive,
            OtherService otherService) {

        return args -> {
            try {
                System.out.println("archive proxied: "
                        + AopUtils.isAopProxy(managedArchive));

                authenticate("reader", "DOC_READ");

                try {
                    System.out.println("reader archive: "
                            + managedArchive.archive(42L));
                } catch (AccessDeniedException denied) {
                    System.out.println("reader archive: DENIED");
                }

                System.out.println("reader preview: "
                        + managedArchive.preview(42L));
                System.out.println("reader other: "
                        + otherService.archive(42L));
                System.out.println("reader new: "
                        + new ArchiveService().archive(42L));
                System.out.println("reader self: "
                        + managedArchive.internalArchive(42L));

                authenticate("archiver", "DOC_ARCHIVE");
                System.out.println("archiver archive: "
                        + managedArchive.archive(42L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String name, String authority) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        name,
                        "not-a-real-credential",
                        List.of(new SimpleGrantedAuthority(authority))));
        SecurityContextHolder.setContext(context);
    }
}
```

Các bước quan trọng:

- Spring Boot tạo bean và auto-proxy phù hợp. `archiveAdvisor` là Spring infrastructure bean; `pointcut` kiểm tra signature của service.
- `AuthorityAuthorizationManager` kiểm tra authority `DOC_ARCHIVE`, **không dùng role prefix `ROLE_`**.
- `CommandLineRunner` nhận `ArchiveService` và `OtherService` bằng constructor/method injection. Lời gọi `managedArchive.archive` đi qua Spring proxy.
- `new ArchiveService().archive` chỉ là lời gọi Java trực tiếp nên **không qua AOP advice**.
- `managedArchive.internalArchive` đi qua proxy cho method `internalArchive`, nhưng method ấy **không nằm trong pointcut**. Sau khi vào target, lời gọi `this.archive` cũng bypass proxy.
- `SecurityContextHolder` được đặt thủ công chỉ để tạo demo dễ hiểu. Ứng dụng thực phải dùng cơ chế xác thực chính thống; không xem cách đặt context này là login handler production.

### 8.6. Chạy và đọc kết quả

Yêu cầu JDK 17+, Maven và tải được dependency tương ứng. Tại thư mục có `pom.xml`:

```bash
mvn -q -DskipTests clean package
java -jar target/pointcut-scope-demo-1.0.0.jar
```

Những dòng do ứng dụng in ra (bỏ qua thông điệp JVM/tooling có thể xuất hiện tùy môi trường):

```text
archive proxied: true
reader archive: DENIED
reader preview: preview-42
reader other: other-42
reader new: archived-42
reader self: archived-42
archiver archive: archived-42
```

Giải thích:

| Dòng | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `archive proxied` | `true` | Spring trả về proxy cho `ArchiveService` vì có advisor khớp |
| `reader archive` | DENIED | Method `ArchiveService.archive` nằm trong pointcut, thiếu `DOC_ARCHIVE` |
| `reader preview` | Thành công | Method `preview` cùng class nhưng **nằm ngoài pointcut** |
| `reader other` | Thành công | `OtherService.archive` có cùng tên method nhưng khác type, **nằm ngoài pointcut** |
| `reader new` | Thành công | Instance `new` không qua proxy; đây là lỗi nếu ứng dụng dùng nó làm service bảo vệ |
| `reader self` | Thành công | `this.archive` bypass proxy; đây là lỗi thiết kế nếu internal path phải bảo vệ |
| `archiver archive` | Thành công | Method match pointcut và manager grant authority |

**Quan trọng:** `preview` và `OtherService.archive` thành công ở demo chỉ chứng minh phạm vi custom advisor. Trong production, hai method ấy vẫn cần các quy tắc thích hợp của chính chúng nếu chứa dữ liệu nhạy cảm. Không được suy diễn “nằm ngoài pointcut này” đồng nghĩa “tự động an toàn”.

## 9. Kiểm thử phạm vi đúng cách: cả trong và ngoài pointcut

Một test chỉ assert “reader bị chặn ở `archive`” là **chưa đủ**. Nếu pointcut bắt nhầm toàn bộ package, test ấy vẫn xanh, còn các method khác có thể bị vô hiệu hóa.

Tạo `src/test/java/demo/PointcutScopeTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class PointcutScopeTest {

    @Autowired ArchiveService archive;
    @Autowired OtherService other;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void deniesTargetMethodForReader() {
        assertThrows(AccessDeniedException.class,
                () -> archive.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_ARCHIVE")
    void allowsTargetMethodForArchiver() {
        assertEquals("archived-42", archive.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void excludesOtherMethodsAndOtherTypes() {
        assertEquals("preview-42", archive.preview(42L));
        assertEquals("other-42", other.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void showsSelfInvocationBypassInProxyMode() {
        assertEquals("archived-42", archive.internalArchive(42L));
    }
}
```

Lệnh kiểm thử:

```bash
mvn -q test
```

Test thứ tư **cố ý chứng minh một đường bypass**, không phải một tiêu chí bảo mật tốt. Khi ứng dụng thật có method nội bộ cần bảo vệ, sửa thiết kế bằng cách tách boundary sang Spring bean khác, rồi đổi test từ “bypass” thành **“deny đúng quyền”**.

Bộ test chứng minh:

1. Pointcut **có match** method đích và manager deny đúng.
2. Manager grant đúng với quyền hợp lệ.
3. Pointcut **không match** hai method khác.
4. Spring proxy có giới hạn khi caller gọi `this.archive`.

### Test âm tính khi đổi tên/overload

Nếu một phiên bản sau thêm:

```java
public String archive(String id) {
    return "archived-" + id;
}
```

Biểu thức `archive(..)` sẽ bao phủ **cả hai overload**. Nếu chỉ muốn method với `long`, sửa thành:

```java
"execution(public * demo.ArchiveService.archive(long))"
```

Sau đó test cả hai overload: `archive(long)` phải bị deny với reader; `archive(String)` có được phép hay không phải theo chính sách **được quyết định trước**, không mặc định bỏ qua vì chỉ là overload.

Ngược lại, nếu dev đổi tên `archive` thành `archiveDocument`, pointcut cũ có thể không match nữa; nếu không có advisor khác, reader sẽ có thể gọi. Để tránh fail-open khi refactor, có thể dùng annotation policy rõ ràng và test coverage, hoặc các test phản ánh đầy đủ danh mục method nhạy cảm.

## 10. Chọn điểm mở rộng: expression, annotation hay `Pointcut`?

### Trường hợp 1 — Chỉ vài method cần policy nghiệp vụ

Có thể chỉ cần:

```java
@PreAuthorize("hasAuthority('DOC_ARCHIVE') and "
            + "@archivePolicy.canArchive(authentication, #p0)")
public void archive(long id) {
    // ...
}
```

Policy ở bean Java, dễ unit test. Không cần custom `Advisor` chỉ để xử lý một luật trên một method.

### Trường hợp 2 — Cả một nhóm method cần một authority chung

Ví dụ service module billing có quy ước “public method bắt đầu bằng `approve` đều cần `BILLING_APPROVE`”. Custom pointcut:

```java
"execution(public * com.acme.billing..*Service.approve*(..))"
```

Có thể giảm việc lặp annotation ở nhiều class, nhưng phải có test chứng minh danh sách method thực tế được bảo vệ.

### Trường hợp 3 — Chính sách tái sử dụng cho một tập method không đồng nhất

Dùng annotation marker do dự án kiểm soát:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresArchivePermission {
}
```

Đây là đoạn khai báo annotation Java với imports `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, `ElementType`; package/tên annotation do dự án xác định. Method được đánh dấu:

```java
@RequiresArchivePermission
public void archive(long id) {
    // ...
}
```

Pointcut:

```java
"@annotation(com.acme.security.RequiresArchivePermission)"
```

**Nhận diện khác biệt:** marker riêng cho custom pointcut không tự hoạt động như Spring Security `@PreAuthorize` nếu không có advisor. Với annotation dự định thay thế `@PreAuthorize`, bảo đảm chính custom manager xử lý tất cả thuộc tính của annotation (nếu annotation có tham số) và test phương thức trên class/interface.

### Trường hợp 4 — Rule cần kiểm tra tham số trong `MethodInvocation`

Pointcut chỉ chọn method; quyền dựa trên ID/tenant được tính **bên trong manager**:

```java
public final class ArchivePolicyManager
        implements AuthorizationManager<MethodInvocation> {

    private final ArchivePolicy policy;

    public ArchivePolicyManager(ArchivePolicy policy) {
        this.policy = policy;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authenticationSupplier,
            MethodInvocation invocation) {

        Object[] arguments = invocation.getArguments();
        if (arguments.length != 1
                || !(arguments[0] instanceof Long documentId)
                || documentId <= 0) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authenticationSupplier.get();
        boolean allowed = auth != null
                && auth.isAuthenticated()
                && policy.canArchive(auth, documentId);
        return new AuthorizationDecision(allowed);
    }
}
```

Imports tối thiểu:

```java
import java.util.function.Supplier;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

`ArchivePolicy` do ứng dụng triển khai, lấy tenant/owner/trạng thái tài liệu từ dữ liệu đáng tin cậy. Đây là **đoạn tích hợp chưa độc lập**; không có bean/repository `ArchivePolicy` trong demo ở mục 8.

Điểm quan trọng: manager không được phép giả định mọi overload method có signature giống nhau nếu pointcut `archive(..)` bao phủ nhiều kiểu. Trả DENY cho cấu trúc tham số không được hỗ trợ, hoặc thu hẹp pointcut, không silently grant.

## 11. Phạm vi class/bean và việc thay đổi cấu trúc dự án

### 11.1. Thay đổi package

Pointcut:

```java
"execution(public * com.acme.orders..*Service.*(..))"
```

Khi service được chuyển từ `com.acme.orders` sang `com.acme.payment`, method có thể ra khỏi pointcut. Nếu policy dựa trên package, **rename/move là thay đổi bảo mật**, cần review và regression test.

### 11.2. Interface và implementation

Nếu service có `DocumentOperations` interface và class `DocumentServiceImpl`, pointcut nhắm vào tên concrete class có thể hành xử khác tùy JDK proxy/class proxy và cách Spring xác định method. Giới hạn theo interface signature có thể rõ ràng hơn khi hệ thống chủ động dùng JDK proxy. Ngược lại, với class-based proxy bạn có thể chọn implementation method. Không giả định mọi proxy strategy sẽ match một `@annotation`/`execution` giống nhau; test với cấu hình thật.

### 11.3. Default method, inherited method và bridge method

Java interface default methods, inheritance/generic bridge methods và overloaded methods có thể làm signature thực tế phức tạp hơn source. Spring AOP và Spring Security có cơ chế tìm method/annotation phù hợp, nhưng **custom pointcut là do bạn viết**, nên phải kiểm thử hành vi cụ thể thay vì suy diễn. Nếu được, đặt ranh giới bảo mật ở public service method ổn định, tránh dựa vào tên method do compiler sinh ra.

### 11.4. Cấu hình nhiều context

Nếu có parent/child `ApplicationContext` hoặc nhiều security/filter contexts, advisor phải được đăng ký trong context quản lý **bean target cần bảo vệ**. Một advisor bean tồn tại trong ứng dụng không đảm bảo nó được áp dụng cho mọi bean thuộc context khác. Kiểm tra kết quả proxy của bean thật ở nơi nó được tạo.

## 12. Khi nhiều advisor cùng match một method

Giả sử:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@Transactional
public void archive(long id) {
    // ...
}
```

và custom advisor yêu cầu `DOC_ARCHIVE` cũng match method đó. Khi các interceptor tương ứng đều chạy, caller có thể cần **cả hai quyền**, tùy chính sách và hành vi từng manager. Không mặc định custom advisor “ghi đè” `@PreAuthorize` hoặc `@Transactional`.

Thứ tự trong chain có ý nghĩa:

- `AuthorizationManagerBeforeMethodInterceptor` kiểm tra **trước khi vào target method** khi đến lượt nó trong chain.
- Transaction interceptor có thể mở transaction trước hoặc sau security interceptor tùy order/cấu hình.
- `@PostAuthorize` chạy sau method; dùng để bảo vệ dữ liệu đọc trả về, không thể mặc nhiên hoàn tác side effect đã ghi.
- Một method có thể có nhiều security advisors, và mỗi advisor có thể từ chối tại một điểm khác nhau.

`AuthorizationManagerBeforeMethodInterceptor` hỗ trợ `setOrder(int)`. Spring Security cũng cung cấp `AuthorizationInterceptorsOrder` để định vị advisor so với các annotation interceptors của framework; chẳng hạn giá trị thông dụng ở Spring Security 6.5 là `PRE_FILTER` gần 100 và `PRE_AUTHORIZE` gần 200. Không dựa vào một số nguyên ngẫu nhiên khi chính sách phụ thuộc thứ tự; hãy tham khảo API version và **test thứ tự thực tế** của transaction/security.

Khi muốn **chỉ có custom policy thay cho `@PreAuthorize` mặc định**, Spring Security có cơ chế `@EnableMethodSecurity(prePostEnabled = false)` rồi đăng ký lại advisor riêng phù hợp. Tuy nhiên thao tác đó ảnh hưởng toàn bộ ứng dụng: `@PreAuthorize`/`@PostAuthorize` có thể không còn được xử lý theo cấu hình cũ. Không dùng để giải quyết một rule đơn lẻ nếu không review hết các method.

## 13. Chính sách an toàn: không để pointcut rơi vào trạng thái fail-open

Một pointcut sai có thể khiến code **không được kiểm tra** chứ không phải nhận DENY. Đây là khác biệt quan trọng so với manager trả `AuthorizationDecision(false)`: nếu interceptor chưa hề chạy, manager không có cơ hội từ chối.

Vì vậy, fail-closed cần được thiết kế **ở cả hai tầng**:

1. **Tầng pointcut:** danh sách method cần bảo vệ phải được bao phủ, có test theo hành vi khi gọi proxy và test phát hiện refactor/rename.
2. **Tầng manager:** khi đã match, thiếu identity/ID/tenant/permission hoặc backend policy không xác nhận được thì trả deny hoặc lỗi hệ thống phù hợp, không grant.

Ví dụ điều kiện manager kiểm tra owner từ request:

```java
// Sai: dữ liệu client có thể tự tạo.
String owner = request.getHeader("X-Owner");

// Đúng hướng: lấy subject từ Authentication và owner/tenant từ DB tin cậy.
```

Đây là mô tả chính sách, không phải ứng dụng hoàn chỉnh. Trong method manager, đối tượng `MethodInvocation` thường đã có arguments; vẫn phải đối chiếu resource ownership và tenant phía server.

### Xử lý tài nguyên thay đổi đồng thời

Nếu manager đọc quyền tại T1 rồi method ghi dữ liệu tại T2, owner/tenant/version có thể thay đổi giữa hai thời điểm. Custom pointcut không giải quyết race condition đó. Với lệnh ghi quan trọng, cần transaction, conditional updates, optimistic locking hoặc pessimistic locking theo consistency contract. `@Transactional` không tự động đảm bảo owner không thay đổi nếu không có cách ly/kiểm soát phù hợp.

## 14. Những lỗi thường gặp

**Lỗi 1 — Dùng package wildcard quá rộng.** Một pattern bảo vệ “mọi public method trong `..service..`” có thể chặn cả truy vấn vô hại, jobs nền, health-related hooks. Hãy thu hẹp bằng tên class/method hoặc marker annotation và test danh sách excluded.

**Lỗi 2 — Quên cập nhật pointcut sau khi đổi package hoặc method name.** Nếu method thoát khỏi pointcut, không có `AccessDeniedException`; method tiếp tục chạy. Bắt buộc có integration test cho từng boundary quan trọng.

**Lỗi 3 — Chỉ unit-test `AuthorizationManager`.** Unit test manager chứng minh điều kiện grant/deny, nhưng không chứng minh pointcut **có match**. Cần test gọi Spring bean qua proxy.

**Lỗi 4 — Chỉ test các method phải bị chặn.** Pointcut bắt nhầm cả method ngoài scope vẫn vượt qua mọi test deny. Bổ sung **negative scope tests** cho method cùng class, cùng tên ở class khác, package con, overload.

**Lỗi 5 — Nghĩ `@Service` trên class là đủ.** Nếu method được gọi qua instance `new` hoặc `this.method()`, Spring proxy mode không tự intercept. Đưa call qua bean proxy, tách service boundary khi cần.

**Lỗi 6 — Dùng `call(...)` hoặc `get(...)` trong Spring proxy AOP.** Đây là pointcut designator của AspectJ weaving, không phải Spring AOP runtime thông thường; biểu thức có thể không hợp lệ. Dùng `execution(...)` cho method execution.

**Lỗi 7 — Đặt annotation marker chỉ ở interface và không kiểm thử.** Custom `@annotation` pointcut có thể nhìn signature khác do proxy/implementation; phải test thực tế với interface proxy strategy và cách annotation được resolve.

**Lỗi 8 — Viết `archive(..)` nhưng manager chỉ hiểu `long`.** Overload mới có thể match rồi bị deny sai; hoặc bị bỏ qua nếu sửa pointcut. Cần thống nhất signature và policy.

**Lỗi 9 — Trả allow khi không đọc được tenant/owner.** Nếu manager đã được gọi, lỗi dữ liệu phải deny hoặc ném lỗi hệ thống rõ ràng theo API contract, không lấy thiếu dữ liệu làm quyền.

**Lỗi 10 — Gắn custom advisor và giữ `@PreAuthorize` mà không biết có hai kiểm tra.** Có thể tạo điều kiện nghiêm hơn dự kiến hoặc thứ tự không mong muốn. Viết test các cặp authority có/không.

**Lỗi 11 — Thấy `AopUtils.isAopProxy(bean) == true` rồi kết luận đủ bảo vệ.** Proxy có thể tồn tại do transaction, cache hoặc advisor khác; cần test method đúng pointcut, không chỉ test proxy flag.

**Lỗi 12 — Nhầm method pointcut với HTTP matcher.** Một URL match không bảo vệ lời gọi đến service từ scheduler. Một custom method advisor không tự bảo vệ HTTP route nếu controller có đường đi khác bypass method đó.

## 15. Ma trận kiểm thử phạm vi và quyền

Một thiết kế pointcut tốt có **bản đồ kỳ vọng** cho mỗi nhóm method.

| Lời gọi | Match pointcut? | Caller thiếu `DOC_ARCHIVE` | Caller có `DOC_ARCHIVE` |
| --- | --- | --- | --- |
| `beanArchive.archive(42)` | Có | DENY | ALLOW |
| `beanArchive.preview(42)` | Không | Không bị **advisor này** chặn | Không bị **advisor này** chặn |
| `beanOther.archive(42)` | Không | Không bị **advisor này** chặn | Không bị **advisor này** chặn |
| `new ArchiveService().archive(42)` | Không đi qua proxy | Không bị chặn bởi Spring AOP | Không bị chặn bởi Spring AOP |
| `beanArchive.internalArchive(42)` gọi `this.archive` | Internal call bypass | Không bị chặn bởi advisor của `archive` | Không bị chặn bởi advisor của `archive` |
| `ArchiveService.archive(String)` (overload nếu bổ sung) | Có với `(..)`; không với `(long)` | Tùy pointcut và manager | Tùy pointcut và manager |
| `ArchiveService` chuyển sang package khác | Có thể không | Nguy cơ fail-open | Test phải cảnh báo |
| `ArchiveService.archive` bị đổi thành `final` khi dùng CGLIB | Có thể không intercept | Nguy cơ fail-open | Test phải cảnh báo |
| Method có thêm `@PreAuthorize` | Có thể chịu thêm advisor | Các kiểm tra phải được xét cùng nhau | Không tự tạo OR |

Các test trọng tâm:

1. **Functional allow/deny**: manager xử lý đúng authority/tenant/owner khi có lời gọi đến method trong scope.
2. **Coverage test**: tất cả method nhạy cảm có trong phạm vi pointcut qua Spring proxy.
3. **Exclusion test**: những method ngoài scope không bị advisor mới chặn ngoài ý muốn.
4. **Refactor test**: rename/move/overload hoặc thêm service mới không làm mất coverage.
5. **Composition test**: khi chồng annotation, transaction và custom advisor, hành vi đúng quyền và rollback vẫn nhất quán.
6. **Bypass test**: phát hiện tự `new`/self-invocation ở những đường gọi phải bảo vệ, rồi sửa thiết kế chứ không giữ bypass như tính năng.

Khi kiểm tra phạm vi, hãy assert **hiệu ứng nghiệp vụ thật** hoặc counter gọi method cùng exception; chỉ kiểm tra log interceptor hoặc “proxy = true” là chưa đủ.

## 16. Khắc phục khi pointcut không hoạt động

Điều tra theo thứ tự giảm thời gian tìm lỗi:

1. **Bean target có được Spring tạo không?** Kiểm tra component scan, `@Bean`, đúng `ApplicationContext`; loại bỏ `new` tự tạo ngoài container.
2. **Custom `Advisor` có thực sự được đăng ký không?** Kiểm tra config được scan, `@Bean` có tạo thành công, dependency và role infrastructure.
3. **Pointcut có match class/method cần chặn không?** So lại full package, tên method, visibility, signature/overload, method trên interface vs implementation.
4. **Lời gọi có đi qua proxy không?** Kiểm tra self-invocation, method `final`/`private`, proxy JDK/CGLIB, bean scope.
5. **Manager đã chạy nhưng grant sai?** Kiểm tra `Authentication`, role/authority prefix, tenant, argument mapping và fail-closed.
6. **Có advisor khác tác động không?** Kiểm tra `@PreAuthorize`, transaction, cache, order và các bean advisor khác.
7. **Test qua entry point thực tế**: API, scheduled job, message handler hoặc service bean; test deny và excluded scope riêng.

Khi debug, có thể dùng:

```java
boolean proxied = AopUtils.isAopProxy(serviceBean);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(serviceBean);
boolean cglibProxy = AopUtils.isCglibProxy(serviceBean);
```

Đây là đoạn tích hợp; `serviceBean` phải là tham chiếu nhận từ Spring. `AopUtils` thuộc `org.springframework.aop.support`. Nếu cần soi advisor chain, có thể inspect những advisor trên đối tượng `Advised` (khi proxy hỗ trợ), nhưng không coi việc một advisor xuất hiện là bằng chứng method đã được intercept: cần xác minh match và hành vi runtime.

Không log access token, mật khẩu hoặc toàn bộ principal để debug pointcut; log method signature, policy name, resource ID đã giới hạn và kết quả quyền phù hợp chính sách audit.

## 17. Checklist khi đưa custom pointcut vào production

- [ ] Phân biệt rõ **tập method dự kiến** và **tập method pointcut match được**.
- [ ] Đã chọn đúng `MethodInvocation` manager cho method security, không dùng lẫn HTTP request manager.
- [ ] Pattern có ranh giới package/class/method/annotation phù hợp; tránh wildcard rộng thiếu lý do.
- [ ] Đã hiểu `execution(public * Type.method(..))` có thể match mọi overload.
- [ ] Đã đăng ký `Advisor` đúng Spring context, bằng bean được nhận diện sớm.
- [ ] `@EnableMethodSecurity` và Spring AOP/AspectJ dependencies cần thiết có hiệu lực.
- [ ] Các method nhạy cảm được gọi qua Spring-managed proxy; không có đường bypass tự `new`/`this.method()`.
- [ ] Đã kiểm tra JDK/CGLIB, interface/implementation annotations, `final` và method visibility.
- [ ] Manager deny khi thiếu identity/quyền/resource; không grant do lỗi parse/lookup.
- [ ] Cấu hình nhiều advisor/transaction có test thứ tự và điều kiện chồng nhau.
- [ ] Có integration test cho **allow, deny, in-scope, out-of-scope** và rename/move/overload.
- [ ] Với thao tác ghi, consistency, transaction và race condition được xử lý ngoài pointcut.
- [ ] Review an toàn cho mỗi refactor package/class/method; test bắt được coverage bị mất.
- [ ] Debug/audit không làm lộ dữ liệu xác thực.

**Nguyên tắc ghi nhớ:** `Pointcut` trả lời **“lời gọi phương thức nào phải được kiểm tra?”**; `AuthorizationManager` trả lời **“lời gọi đó có được thực hiện không?”**. Với custom method-security policy, một trong hai phần sai đều có thể tạo lỗi bảo mật hoặc làm hỏng nghiệp vụ. Hãy kiểm thử **cả hai chiều của phạm vi** và kiểm tra đường gọi thực sự đi qua Spring proxy.

## Tài liệu tham khảo

- [Spring Security 6.5 — Method Security: Matching Methods with Custom Pointcuts](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — AuthorizationManagerBeforeMethodInterceptor JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Proxying Mechanisms and Self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)
