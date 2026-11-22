# Tham số hóa meta-annotation trong Spring Security: chọn giải pháp theo phiên bản

## 1. Bài toán và kết quả cần đạt

Khi nhiều service cùng áp dụng một quy tắc, viết lặp `@PreAuthorize("hasRole('ADMIN')")` hoặc `@PreAuthorize("hasAuthority('report:read')")` ở hàng chục phương thức làm chính sách khó đọc và khó thay đổi. **Meta-annotation** cho phép đặt annotation của Spring Security lên một annotation do dự án định nghĩa, sau đó áp dụng annotation nghiệp vụ lên service.

Bước tiếp theo là **tham số hóa meta-annotation**: thay vì tạo riêng `@CanReadReports`, `@CanEditReports`, `@IsAdmin`, ta muốn khai báo `@RequiresRole("ADMIN")` hoặc `@RequiresAuthority("report:read")` và dùng các giá trị đó trong biểu thức SpEL. Khả năng **thay thế placeholder trong annotation biểu thức** có khác biệt đáng kể giữa các thế hệ Spring Security. Do đó câu hỏi đầu tiên là: **đang chạy phiên bản nào và đã bật template processing chưa?**

Sau bài học, bạn sẽ biết cách:
- Tạo một meta-annotation cố định hoạt động không cần template.
- Tạo meta-annotation tham số hóa qua `{value}`, `{role}` và mảng `{roles}` trên phiên bản có hỗ trợ.
- Bật `AnnotationTemplateExpressionDefaults` ở Spring Security 6.4–6.5, đồng thời hiểu thay đổi mặc định ở Spring Security 7.
- Phân biệt **tham số annotation** với **tham số phương thức** (`#owner`), tránh lỗi quote trong SpEL và kiểm thử chính xác hành vi cho phép/từ chối.
- Có đường lui an toàn cho ứng dụng phiên bản cũ và lưu ý khi nâng cấp.

**Phạm vi:** Spring Security Method Security (chủ yếu `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`) trong ứng dụng Spring dùng Java 17+. Đây không phải cú pháp Java “thay đổi annotation lúc runtime”; mọi giá trị ghi trong annotation vẫn phải tuân theo quy tắc compile-time của Java.

## 2. Meta-annotation cố định và meta-annotation có template

### 2.1. Meta-annotation cố định: cách cơ bản

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface IsAdmin {
}
```

Đoạn này là nội dung file `IsAdmin.java` riêng biệt; muốn chạy cần đặt trong package của ứng dụng và bật Method Security. Sau đó service có thể viết:

```java
@IsAdmin
public String getSystemReport() {
    return "system-report";
}
```

**Ở dạng cố định, không có placeholder**: Spring Security phát hiện `@PreAuthorize` nằm trên annotation tùy biến và đánh giá chính sách `hasRole('ADMIN')`. Đây là lựa chọn dễ hiểu, phù hợp cả khi đang dùng phiên bản chưa có chức năng template expression. Nó giúp đặt tên theo nghiệp vụ nhưng không truyền role khác nhau qua một annotation.

### 2.2. Meta-annotation tham số hóa: có placeholder

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

Ví dụ khai báo:

```java
@RequiresRole("ADMIN")
public String getSystemReport() {
    return "system-report";
}
```

Khi **annotation template resolution đã được bật hoặc là mặc định của phiên bản**, thuộc tính `value = "ADMIN"` thay vào placeholder `{value}`. Biểu thức cuối cùng tương đương:

```text
hasRole('ADMIN')
```

Điểm quan trọng: Java không tự hiểu `{value}`. Đó là **quy ước template của Spring Security**. Nếu không có hỗ trợ/xử lý template phù hợp, chuỗi có thể vẫn là `hasRole('{value}')` hoặc gây lỗi tùy expression/configuration: chính sách sẽ không hoạt động như bạn dự kiến.

### 2.3. Hai lớp tham số khác nhau

Xét mẫu:

```java
@PreAuthorize(
    "hasRole('{role}') or #owner == authentication.name"
)
public @interface OwnerOrRole {
    String role();
}
```

Sử dụng:

```java
@OwnerOrRole(role = "SUPPORT")
public String read(@P("owner") String owner) {
    return "report:" + owner;
}
```

Đây là **các đoạn minh họa**, cần imports `@P`, `@PreAuthorize` và `@Target`/`@Retention` để thành một file Java hợp lệ. Tại thời điểm chuẩn bị metadata của annotation, template giải `{role}` thành `SUPPORT`. Khi người dùng thực sự gọi phương thức, SpEL mới đối chiếu biến invocation `#owner` với `authentication.name`.

| Cú pháp | Dữ liệu đến từ đâu? | Khi nào xác định? |
|---|---|---|
| `{role}` | Thuộc tính `role()` của annotation `@OwnerOrRole` | Khi framework tạo/đọc security metadata và resolve template |
| `{value}` | Thuộc tính `value()` của annotation tùy biến | Khi resolve template |
| `#owner` | Tham số `owner` của method đang được gọi | Khi đánh giá SpEL cho **từng lần gọi** |
| `authentication.name` | `Authentication` trong security context | Khi đánh giá quyền cho lời gọi |
| `@policy.canRead(#id)` | Spring bean tên `policy` và biến `#id` | Khi đánh giá SpEL |

Không đưa dữ liệu người dùng lên annotation như một biểu thức được sinh động ở runtime. Đối với dữ liệu thay đổi theo request, dùng `#methodArg`, `authentication` và bean policy thay vì cố tìm cách sửa `{value}`.

## 3. Ma trận khả năng theo Spring Security

| Dòng phiên bản | Meta-annotation **cố định** | Tham số hóa template | Cấu hình đề xuất |
|---|---|---|---|
| Spring Security trước 6.3 | Có cơ chế meta-annotation cho Method Security | Không mặc nhiên giả định có API template mới | Dùng annotation cố định hoặc SpEL gọi bean policy |
| Spring Security 6.3 | Có | Có API đời đầu `PrePostTemplateDefaults` (ra đời từ 6.3); khác API mới | Nếu không nâng cấp, kiểm tra tài liệu **đúng patch version** và cấu hình riêng của phiên bản; tránh sao chép API 6.4 |
| Spring Security **6.4–6.5** | Có | Có `AnnotationTemplateExpressionDefaults` (ra đời từ 6.4); **cần chủ động bật** theo hướng dẫn bản 6.x | Đăng ký bean `static AnnotationTemplateExpressionDefaults` |
| Spring Security **7.x** | Có | `AnnotationTemplateExpressionDefaults` được đưa vào mặc định theo hướng dẫn migration sang 7 | Không cần bean chỉ để bật templating; vẫn có thể đăng ký bean để tùy chỉnh hành vi |

**Quy tắc triển khai:** Kiểm tra Spring Security thực tế trên classpath (thường được Spring Boot quản lý), không suy từ duy nhất version Java. Cách chắc chắn nhất là đọc cây dependency và chạy integration test trên đúng phiên bản deploy.

Ở Spring Security 6.4, `org.springframework.security.authorization.method.PrePostTemplateDefaults` đã bị đánh dấu deprecated để ưu tiên API chung `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults`. Không dùng API cũ làm lựa chọn mặc định cho mã mới vì nó làm đường nâng cấp kém rõ ràng. **Các phiên bản khác nhau có thể triển khai cơ chế quét annotation khác nhau**: những kết luận về “cần bean hay không” phải được xác minh bằng dependency và test chứ không suy luận từ tên annotation.

### 3.1. Bật template trong Spring Security 6.4–6.5

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

Phương thức `@Bean` được khai báo **`static`** đúng với ví dụ chính thức để framework nhận cấu hình sớm trong quá trình dựng infrastructure Method Security. `@EnableMethodSecurity` vẫn bắt buộc để bật các interceptor method-level trong ứng dụng Spring Boot 3.x; chỉ cài dependency `spring-boot-starter-security` không đủ.

API `AnnotationTemplateExpressionDefaults` có từ Spring Security 6.4. Nếu IDE báo `Cannot resolve symbol AnnotationTemplateExpressionDefaults`, thường là bạn đang dùng Spring Security cũ hơn hoặc dependency version bị ghi đè. Đừng “sửa” bằng cách import package không đúng; hãy kiểm tra dependency và hỗ trợ từng dòng phiên bản.

### 3.2. Với Spring Security 7

Trong hướng dẫn migration 6.5 → 7, Spring Security nêu `AnnotationTemplateExpressionDefaults` được cung cấp mặc định. Với ứng dụng dùng Spring Security 7, meta-annotation template có thể hoạt động ngay sau khi bật Method Security. Bạn vẫn nên giữ bài test cho từng annotation sau khi nâng cấp và xác nhận cấu hình template custom còn được áp dụng.

**Đừng áp dụng ví dụ build Spring Boot 3.5 bên dưới cho Spring Security 7 bằng cách ép version riêng lẻ.** Spring Security 7 thuộc thế hệ Spring Framework/Spring Boot mới hơn; muốn kiểm thử 7.x hãy chọn Spring Boot 4.x tương thích, đọc migration guide và kiểm tra lại dependencies. Bài chạy đầy đủ trong phần 5 chủ đích dùng Spring Boot 3.5 / Spring Security 6.5 với bean bật template rõ ràng để tránh phụ thuộc vào thay đổi mặc định giữa phiên bản.

### 3.3. Tùy chọn xử lý placeholder không xác định

`AnnotationTemplateExpressionDefaults` hỗ trợ:

```java
AnnotationTemplateExpressionDefaults defaults =
    new AnnotationTemplateExpressionDefaults();
defaults.setIgnoreUnknown(false);
```

Đây là **đoạn cấu hình rời**, không phải một class Java độc lập. Mặc định của `ignoreUnknown` là `true`; đặt `false` khiến placeholder không được nhận diện bị báo lỗi khi resolve template, hữu ích để bắt lỗi gõ nhầm như `{rol}` thay vì `{role}`. Cấu hình chặt có thể không phù hợp với biểu thức sử dụng dấu ngoặc nhọn vì mục đích khác, nên thử trên toàn bộ annotation dự án trước khi bật đồng loạt. Không coi “bỏ qua placeholder lạ” là bằng chứng một biểu thức vẫn có chính sách đúng; phải test trạng thái quyền thực tế.

## 4. Cú pháp thay thế placeholder và quy tắc dấu nháy

### 4.1. Một String: dấu nháy nằm trong expression

```java
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresAuthority {
    String value();
}
```

`@RequiresAuthority("report:read")` được resolve thành:

```text
hasAuthority('report:read')
```

`hasAuthority` so khớp **chính xác** `GrantedAuthority`. `hasRole('ADMIN')` mặc định tương ứng `ROLE_ADMIN`; đừng dùng lẫn hai khái niệm khi cấu hình role prefix đã thay đổi.

### 4.2. Mảng String: dấu nháy nằm trong giá trị annotation

Mẫu chính thức cho mảng role:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

Cách dùng:

```java
@HasAnyRole(roles = {"'ANALYST'", "'ADMIN'"})
public String readSharedReport() {
    return "shared";
}
```

Sau khi resolve:

```text
hasAnyRole('ANALYST', 'ADMIN')
```

Đây là điểm dễ sai: **mảng annotation dùng các string chứa sẵn dấu nháy đơn** để tạo đối số chuỗi hợp lệ cho SpEL. Nếu viết `@HasAnyRole(roles = {"ANALYST", "ADMIN"})` với template `hasAnyRole({roles})`, biểu thức có thể thành `hasAnyRole(ANALYST, ADMIN)`, không còn là literal chuỗi mong muốn. Không thay template thành `hasAnyRole('{roles}')` vì cả mảng bị đặt trong một cặp nháy, cũng sai về ngữ nghĩa đối số.

Với một hoặc hai role cố định dùng lặp lại nhiều lần, hãy cân nhắc meta-annotation chuyên biệt như `@CanReadSharedReport` nếu cú pháp String[] có quote khiến code khó đọc.

### 4.3. Nhiều thuộc tính annotation, nhiều biến method

```java
@PreAuthorize(
    "hasAuthority('{authority}') and #tenantId == authentication.name"
)
public @interface HasTenantAuthority {
    String authority();
}
```

Áp dụng:

```java
@HasTenantAuthority(authority = "tenant:read")
public String readTenant(@P("tenantId") String tenantId) {
    return "tenant:" + tenantId;
}
```

Đây là **các đoạn minh họa cần đặt vào annotation/service phù hợp**; chúng không thay thế kiểm tra membership trong hệ thống tenant thực tế. Ví dụ chỉ có ý nghĩa nếu định danh `authentication.name` thực sự bằng `tenantId`, một mô hình hiếm và không nên ngầm giả định trong ứng dụng đa tenant. Trên hệ thống thật, nên truyền `#tenantId` và `authentication` cho bean policy để đối chiếu membership hoặc đưa tenant vào truy vấn dữ liệu.

`@P("tenantId")` (hoặc biên dịch với `-parameters`) giúp `#tenantId` được Spring Security nhận diện. Cú pháp `{authority}` không phải biến invocation: đây là thuộc tính được định nghĩa bởi annotation tại chỗ.

### 4.4. Những tình huống phải chú ý

- **Chuỗi sau thay thế phải là SpEL hợp lệ.** Placeholder resolution chỉ thay ký tự, không tự biến một role thành cấu trúc expression phù hợp trong mọi ngữ cảnh.
- **Giá trị thuộc tính annotation là mã chính sách tin cậy**, do developer viết. Không nối dữ liệu request/user thành biểu thức SpEL rồi evaluate; có thể tạo lỗi kiểm tra quyền hoặc injection.
- **Dấu nháy, dấu gạch chéo và ký tự đặc biệt** có thể thay đổi parsing. Nếu role/authority chứa ký tự phức tạp, dùng policy bean hoặc test các literal đúng chuẩn thay vì ghép expression tùy tiện.
- **Không truyền trực tiếp một annotation value như argument runtime**: `@RequiresRole(userChosenRole)` không biên dịch nếu `userChosenRole` là biến tính lúc chạy.
- **Không khai báo hai `@PreAuthorize` trên cùng một method** để mô tả hai chính sách riêng: Spring Security không hỗ trợ lặp cùng annotation như vậy. Gộp điều kiện bằng `and`/`or`, tạo annotation nghiệp vụ một chính sách, hoặc ủy quyền cho bean.
- **Target/Retention** cần phù hợp: `@Target(METHOD/TYPE)` để gắn lên method/class; `@Retention(RUNTIME)` để framework nhận diện annotation ở runtime.

## 5. Ví dụ tích hợp chạy được: Spring Boot 3.5.6 + Java 17

Phần này tạo ứng dụng không cần HTTP server hoặc database; Method Security hoạt động trên service bean, và JUnit test dùng `@WithMockUser` để đặt Authentication. **Chúng ta dùng Spring Boot 3.5.6 (phát hành 18/09/2025) và Spring Security 6.5.x do Boot quản lý**, không ép version Spring Security khác.

Cây file:

```text
meta-annotation-demo/
  pom.xml
  src/main/java/com/example/metasec/MetaAnnotationApplication.java
  src/main/java/com/example/metasec/security/MethodSecurityConfig.java
  src/main/java/com/example/metasec/security/RequiresRole.java
  src/main/java/com/example/metasec/security/HasAnyRole.java
  src/main/java/com/example/metasec/security/OwnerOrRole.java
  src/main/java/com/example/metasec/ReportService.java
  src/test/java/com/example/metasec/ReportServiceTest.java
```

### 5.1. Cấu hình Maven: pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>meta-annotation-demo</artifactId>
    <version>1.0.0</version>
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

### 5.2. Ứng dụng và cấu hình bật template

**`src/main/java/com/example/metasec/MetaAnnotationApplication.java`**

```java
package com.example.metasec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetaAnnotationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetaAnnotationApplication.class, args);
    }
}
```

**`src/main/java/com/example/metasec/security/MethodSecurityConfig.java`**

```java
package com.example.metasec.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

Bean template ở đây là bước cần chú ý trên dòng 6.4–6.5. Class cấu hình được Spring Boot tự quét vì nằm dưới package gốc `com.example.metasec`. Nếu đặt package bên ngoài phạm vi component scan thì cấu hình có thể không được nạp.

### 5.3. Ba meta-annotation tùy biến

**`src/main/java/com/example/metasec/security/RequiresRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

**`src/main/java/com/example/metasec/security/HasAnyRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

**`src/main/java/com/example/metasec/security/OwnerOrRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "isAuthenticated() and (#owner == authentication.name or hasRole('{role}'))"
)
public @interface OwnerOrRole {
    String role();
}
```

Các annotation này minh họa ba dạng: một `String value`, một `String[]`, và sự kết hợp giữa thuộc tính template với biến method runtime. Với mặc định `ROLE_`, `@RequiresRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`.

### 5.4. Service sử dụng annotation

**`src/main/java/com/example/metasec/ReportService.java`**

```java
package com.example.metasec;

import com.example.metasec.security.HasAnyRole;
import com.example.metasec.security.OwnerOrRole;
import com.example.metasec.security.RequiresRole;
import org.springframework.security.access.method.P;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @RequiresRole("ADMIN")
    public String adminReport() {
        return "admin-report";
    }

    @HasAnyRole(roles = {"'ANALYST'", "'ADMIN'"})
    public String sharedReport() {
        return "shared-report";
    }

    @OwnerOrRole(role = "SUPPORT")
    public String readOwnerReport(@P("owner") String owner) {
        return "report:" + owner;
    }
}
```

Đối với `readOwnerReport("alice")`: người dùng `alice` có thể đọc do owner trùng, còn người dùng `bob` được cấp `ROLE_SUPPORT` có thể đọc theo nhánh hỗ trợ. Người dùng `bob` chỉ có `ROLE_VIEWER` sẽ bị chặn. Đây là **chính sách ví dụ**: nếu hệ thống nhiều tenant, cần thêm điều kiện tenant hoặc bean policy, không mặc nhiên xem support có quyền trên mọi tenant.

### 5.5. Tám kiểm thử tích hợp

**`src/test/java/com/example/metasec/ReportServiceTest.java`**

```java
package com.example.metasec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportServiceTest {
    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminCanReadAdminReport() {
        assertEquals("admin-report", reports.adminReport());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "VIEWER")
    void viewerCannotReadAdminReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.adminReport()
        );
    }

    @Test
    @WithMockUser(username = "analyst", roles = "ANALYST")
    void analystCanReadSharedReport() {
        assertEquals("shared-report", reports.sharedReport());
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminCanReadSharedReport() {
        assertEquals("shared-report", reports.sharedReport());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "VIEWER")
    void viewerCannotReadSharedReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.sharedReport()
        );
    }

    @Test
    @WithMockUser(username = "alice", roles = "VIEWER")
    void ownerCanReadOwnReport() {
        assertEquals("report:alice", reports.readOwnerReport("alice"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "SUPPORT")
    void supportCanReadAnotherOwnersReport() {
        assertEquals("report:alice", reports.readOwnerReport("alice"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "VIEWER")
    void otherViewerCannotReadOwnersReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readOwnerReport("alice")
        );
    }
}
```

Tại thư mục `meta-annotation-demo`, chạy:

```bash
mvn test
```

**Kết quả kỳ vọng (không phải log đã chạy thực tế):** `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. Dòng log và thứ tự test có thể khác tùy Maven/Surefire. Kết quả quyền minh họa là:

| Lời gọi | User / authority | Kỳ vọng |
|---|---|---|
| `adminReport()` | `ROLE_ADMIN` | Trả `admin-report` |
| `adminReport()` | `ROLE_VIEWER` | `AccessDeniedException` |
| `sharedReport()` | `ROLE_ANALYST` hoặc `ROLE_ADMIN` | Trả `shared-report` |
| `sharedReport()` | `ROLE_VIEWER` | `AccessDeniedException` |
| `readOwnerReport("alice")` | `alice` / `ROLE_VIEWER` | Trả `report:alice` |
| `readOwnerReport("alice")` | `bob` / `ROLE_SUPPORT` | Trả `report:alice` |
| `readOwnerReport("alice")` | `bob` / `ROLE_VIEWER` | `AccessDeniedException` |

Test dùng bean `ReportService` từ `@SpringBootTest` để interceptor thật được áp dụng. Tự `new ReportService()` hoặc gọi `this.adminReport()` nội bộ có thể bỏ qua Spring AOP proxy và đánh mất kiểm tra quyền. Khi chạy, cần Java 17+ và Maven/IDE có thể tải các dependencies phù hợp.

## 6. Nếu dự án chưa hỗ trợ template: cách triển khai tương đương

Không nhất thiết nâng cấp chỉ để đổi hai chữ annotation. Có hai phương án an toàn.

### 6.1. Tạo annotation cố định theo nghiệp vụ

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('report:read')")
public @interface CanReadReport {
}
```

```java
@CanReadReport
public Report readReport(long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là **các mẫu tích hợp**, cần imports annotation, kiểu `Report`, repository và service. Nếu chỉ có một số chính sách ổn định, các tên domain như `@CanReadReport` thường còn rõ hơn `@RequiresAuthority("report:read")`.

### 6.2. Đưa biến động vào bean chính sách Java

```java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report readReport(@P("reportId") long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

Đây là mẫu tích hợp: `reportPolicy` cần là Spring bean có method nhận `Authentication` và id; `Report`, repository và imports phải có trong ứng dụng. Bean thực hiện truy vấn quyền/tenant/ACL và đưa ra quyết định dựa trên dữ liệu runtime. Lợi ích: tách riêng logic nghiệp vụ, dễ unit test, không phụ thuộc vào engine thay thế `{value}`.

Với ứng dụng xử lý nhiều tenant hoặc phải kiểm tra quyền ở mức record, bean policy hoặc truy vấn dữ liệu áp dụng ACL thường quan trọng hơn việc tối giản annotation.

## 7. Tương thích nâng cấp từ 6.3/6.4/6.5 lên 7

Một lộ trình thực tế:

1. **Lấy đúng version** từ `mvn dependency:tree` hoặc dependency report của Gradle; xác định bản Spring Security do BOM/Boot đang quản lý. Đừng chỉ nhìn `@EnableMethodSecurity` trong source.
2. **Ghi rõ hợp đồng security**: annotation nào được gắn ở đâu, giá trị nào được thay, role prefix là gì, các trường hợp allow/deny.
3. **Ở 6.4–6.5**, đăng ký `static @Bean AnnotationTemplateExpressionDefaults` và chạy test. Nếu đang ở 6.3 dùng `PrePostTemplateDefaults`, chuẩn bị chuyển sang API mới khi nâng Spring Security.
4. **Ở 7.x**, templating có mặc định theo migration guide; loại bỏ bean chỉ khi không có tùy chỉnh cần duy trì, đồng thời giữ toàn bộ test quyền.
5. **Nếu có advisor tùy biến**, xem cơ chế gắn template defaults trực tiếp qua `setTemplateDefaults(new AnnotationTemplateExpressionDefaults())` và kiểm tra migration tương ứng; bean toàn cục không thay thế được mọi cấu hình tự xây một cách thần kỳ.
6. **Kiểm thử negative path**: user thiếu role, role chỉ tương tự tên (`ADMINISTRATOR` không phải `ADMIN`), placeholder sai, array quên quote, method gọi nội bộ qua `this`, tên param không nhận diện.
7. **Kiểm tra prod behavior** với dữ liệu thực, đặc biệt role mapping của JWT/OIDC, authority mapping, tenant membership và entry point gọi service.

Một cấu hình có tính phòng vệ hơn (tùy chọn ở 6.4+):

```java
@Bean
static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
    AnnotationTemplateExpressionDefaults defaults =
        new AnnotationTemplateExpressionDefaults();
    defaults.setIgnoreUnknown(false);
    return defaults;
}
```

Đoạn này dùng để **thay thế** bean cùng tên trong ví dụ trên, không khai báo thêm bean thứ hai. Khi placeholder sai, cấu hình chặt giúp phát hiện thay vì để template lạ trôi qua. Hãy thử với tất cả biểu thức trong ứng dụng trước khi dùng vì các dấu ngoặc nhọn không nhằm templating cũng có thể bị ảnh hưởng.

### 7.1. Lệnh xem dependency

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Lệnh này không bảo đảm chỉ hiện một dòng; nó liệt kê các module Security và version thực tế trong dependency tree. Với Gradle, có thể dùng `./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath` (trên Windows thay bằng `gradlew.bat`). Chạy với đúng project và cấu hình dependency đang deploy.

## 8. Các lỗi điển hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
|---|---|---|
| `@RequiresRole("ADMIN")` không thực thi quyền | Chưa bật `@EnableMethodSecurity`, self-invocation, bean không do Spring tạo | Kiểm tra AOP interceptor, gọi qua Spring bean, viết test deny |
| SpEL chứa nguyên `{value}` | Phiên bản chưa hỗ trợ hoặc chưa bật template trên 6.4–6.5 | Kiểm tra version, đăng ký defaults bean |
| `Cannot resolve symbol AnnotationTemplateExpressionDefaults` | Module Spring Security cũ hơn 6.4 hoặc version xung đột | Kiểm tra BOM/dependency tree; không copy sai package |
| `hasAnyRole` báo lỗi hoặc từ chối trái kỳ vọng | String[] không chứa dấu nháy literal trong từng phần tử | Dùng `{"'ANALYST'", "'ADMIN'"}` với `hasAnyRole({roles})` |
| `hasRole('ADMIN')` từ chối dù có `ADMIN` | Authority thực tế là `ADMIN` thay vì `ROLE_ADMIN` theo cấu hình mặc định | Dùng `hasAuthority('ADMIN')` hoặc chuẩn hóa role mapping |
| `#owner` không được nhận diện | Thiếu metadata tên param; gọi sai tên | Dùng `@P("owner")` hoặc biên dịch `-parameters` |
| Lỗi lúc khởi tạo bean/advisor | Placeholder không tồn tại, expression sai, xung đột nhiều annotation | Bật `setIgnoreUnknown(false)` khi phù hợp; test startup |
| Annotation đặt ở interface nhưng không áp dụng như dự kiến | Cấu hình proxy/interface/inheritance hoặc annotation ambiguity | Chạy integration test đúng kiểu proxy, kiểm tra nơi đặt annotation |
| Nhiều meta-annotation dẫn tới ambiguity | Cùng một method có nhiều ứng viên `@PreAuthorize` | Gom thành một chính sách, tránh annotation lặp |
| Lọc/đọc dữ liệu rò rỉ qua đường khác | Chỉ gắn quyền ở một service/endpoint, đường khác bypass | Đặt policy tại ranh giới service/data hợp lý, kiểm thử các đường truy cập |

**Chú ý nghiệp vụ:** Quy tắc hậu kiểm như `@PostAuthorize` có thể quyết định từ chối **sau khi** method đã tạo kết quả; không dùng nó để bảo vệ mutation đã thực hiện. Phần lớn quyền cho hành động có tác dụng phụ nên kiểm tra trước khi chạy bằng `@PreAuthorize` hoặc kiểm tra quyền tại tầng nghiệp vụ.

## 9. Checklist áp dụng

- [ ] Biết rõ version Spring Security và phiên bản Spring Boot tương thích.
- [ ] Phân biệt **meta-annotation cố định** với meta-annotation có `{placeholder}`.
- [ ] Với 6.4–6.5, có bean `static AnnotationTemplateExpressionDefaults`; với 7.x đã kiểm tra thay đổi mặc định.
- [ ] `@EnableMethodSecurity` đã bật và security annotation được Spring AOP phát hiện.
- [ ] Annotation có `@Target`, `@Retention(RUNTIME)` và attribute phù hợp.
- [ ] Chuỗi SpEL sau substitution đúng cú pháp; đặc biệt kiểm tra quote với String[].
- [ ] Không trộn nhầm `{annotationAttribute}` và `#methodArgument`.
- [ ] Role và authority mapping được test bằng allow/deny thực tế.
- [ ] Không có đường gọi bypass proxy (self-invocation) và không có chính sách lặp mơ hồ.
- [ ] Phần mềm dùng Java 17+ được kiểm thử bằng `mvn test` trên dependency tree đúng môi trường.
- [ ] Với chính sách phức tạp, ưu tiên bean policy hoặc query có điều kiện quyền thay cho biểu thức dài khó audit.

## 10. Tài liệu chính thức

- [Spring Security 6.5 — Method Security: Using Meta Annotations & Templating](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Migration to 7: Authorization Changes](https://docs.spring.io/spring-security/reference/6.5/migration-7/authorization.html)
- [Spring Security — AnnotationTemplateExpressionDefaults API (Since 6.4)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html)
- [Spring Security 6.5 — PrePostTemplateDefaults (deprecated)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PrePostTemplateDefaults.html)
- [Spring Boot 3.5.6 release](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/)

**Điểm mấu chốt:** Một meta-annotation cố định giúp đặt tên chính sách nhất quán; một meta-annotation có template giúp truyền role/authority theo cấu hình annotation. Tính đúng đắn của giải pháp tham số hóa phụ thuộc **version thực tế, cấu hình template và kết quả biểu thức SpEL**, nên bài test cho phép và từ chối ở ranh giới method là phần không thể thiếu.