# RBAC: phân quyền theo vai trò (Role-Based Access Control)

## 1. Mục tiêu và bối cảnh

Sau bài học, bạn có thể:

1. Giải thích **RBAC** bằng mối quan hệ giữa người dùng, vai trò và quyền; phân biệt **authentication** với **authorization**.
2. Thiết kế ma trận vai trò/quyền cho một ứng dụng có nhiều loại người dùng và xác định nguyên tắc quyền tối thiểu.
3. Hiểu **role** và **`GrantedAuthority`** trong Spring Security; dùng đúng `hasRole`, `hasAnyRole`, `hasAuthority` và tiền tố `ROLE_`.
4. Áp dụng RBAC ở lớp HTTP với `SecurityFilterChain` và ở service bằng `@PreAuthorize`, biết vì sao cần bảo vệ nhiều đường gọi.
5. Chạy một ứng dụng Spring Boot Java 17 có ba vai trò, kiểm tra các trường hợp 200, 401, 403 bằng HTTP và kiểm thử tự động.
6. Nhận ra giới hạn của RBAC, tránh nhầm vai trò với quyền sở hữu dữ liệu, phân quyền theo thuộc tính hoặc trạng thái đối tượng.

**Phạm vi:** kiến thức nền tảng Spring Security với demo Servlet/MVC để dễ quan sát `HttpSecurity`, `SecurityFilterChain` và method security. Spring WebFlux có API security tương ứng nhưng khác stack (`ServerHttpSecurity`, `SecurityWebFilterChain`, `@EnableReactiveMethodSecurity`); không dùng lớp Servlet trong một ứng dụng WebFlux thuần. Nguyên lý RBAC độc lập với stack HTTP.

## 2. RBAC là gì?

**RBAC (Role-Based Access Control)** là mô hình quyết định quyền truy cập dựa trên **vai trò được cấp cho chủ thể** thay vì gán từng quyền trực tiếp cho từng tài khoản.

Ba khái niệm cốt lõi:

- **User/subject (chủ thể):** người dùng hoặc danh tính dịch vụ đang muốn thao tác.
- **Role (vai trò):** nhóm trách nhiệm trong hệ thống, ví dụ `READER`, `EDITOR`, `ADMIN`.
- **Permission (quyền):** khả năng thực hiện một **action** trên một **resource** nhất định, ví dụ `article:read`, `article:create`, `article:delete`.

Mô hình quan hệ:

```text
User  ──được gán──> Role ──được cấp──> Permission
  Lan             EDITOR                  article:read
                                          article:create
                                          article:update

  Minh            READER                  article:read
```

Quyết định cấp quyền trong RBAC điển hình dựa vào việc *người dùng đã xác thực có một vai trò đang được công nhận và vai trò đó được phép thực hiện hành động yêu cầu hay không*. Việc ánh xạ `Role → Permission` thường do chính sách ứng dụng quản lý; một số ứng dụng giản lược bằng việc gắn role trực tiếp lên endpoint.

**Phân biệt hai câu hỏi:**

- **Xác thực (authentication):** “Bạn là ai?” Ví dụ: HTTP Basic, phiên đăng nhập, OAuth2/JWT đã được kiểm chứng. Kết quả thường biểu diễn thành `Authentication`.
- **Phân quyền (authorization):** “Danh tính này được phép làm gì với tài nguyên này?” Ví dụ: user đã đăng nhập nhưng không có quyền xóa bài viết.

RBAC **không thay thế** xác thực. Biết một người tự khai rằng họ là “ADMIN” trong query hoặc header không có nghĩa hệ thống phải công nhận vai trò đó.

## 3. Từ yêu cầu nghiệp vụ tới ma trận quyền

Giả sử một hệ thống bài viết có ba loại người dùng:

| Hành động | READER | EDITOR | ADMIN |
| --- | :---: | :---: | :---: |
| Xem bài viết đã xuất bản | ✅ | ✅ | ✅ |
| Tạo bản nháp | ❌ | ✅ | ✅ |
| Sửa bản nháp | ❌ | ✅ | ✅ |
| Xuất bản bài viết | ❌ | ❌ | ✅ |
| Xóa bài viết bất kỳ | ❌ | ❌ | ✅ |
| Quản lý người dùng | ❌ | ❌ | ✅ |

Đây là **chính sách giả định của ví dụ**, không phải một tiêu chuẩn bắt buộc cho mọi ứng dụng. Cần làm rõ hành động, trạng thái tài nguyên và giới hạn tổ chức trước khi lập ma trận. Đặc biệt, câu “EDITOR được sửa bài” chưa trả lời liệu editor được sửa *bài của người khác* hay bài *đã xuất bản* hay không.

Quy trình thiết kế:

1. Liệt kê **resource**: bài viết, bản nháp, người dùng, báo cáo, cấu hình hệ thống.
2. Liệt kê **action**: `read`, `create`, `update`, `publish`, `delete`, `manage`.
3. Xác định nhóm trách nhiệm thực tế rồi đặt tên role. Đừng tạo một role mới chỉ vì mỗi URL có tên khác.
4. Cấp tập quyền tối thiểu cho từng role (principle of least privilege). Mặc định chức năng mới chưa được cấp quyền.
5. Ghi rõ điều kiện bổ sung như “chỉ bài thuộc chính mình”, “chưa được xuất bản” hoặc “cùng phòng ban”; điều này vượt quá RBAC thuần và cần kiểm tra ở tầng nghiệp vụ.
6. Xác minh chính sách bằng bảng test cho cả trường hợp được phép và bị từ chối.

Một đặc điểm quan trọng: **một user có thể có nhiều vai trò**. Vai trò cũng có thể được tổ chức theo thứ bậc *nếu hệ thống cấu hình role hierarchy*. Việc đặt tên `ADMIN` không tự động làm nó kế thừa `EDITOR` hoặc `READER` trong Spring Security.

### Các biến thể RBAC (đủ để nhận diện)

- **Core RBAC:** quan hệ user-role và role-permission cơ bản.
- **Hierarchical RBAC:** hỗ trợ quan hệ kế thừa vai trò (`ADMIN > EDITOR > READER`), nhưng phải định nghĩa rõ.
- **Constrained RBAC:** bổ sung ràng buộc như tách biệt nhiệm vụ (một người không vừa đề nghị vừa phê duyệt giao dịch).
- **Symmetric RBAC:** quản lý/review quan hệ gán role và permission hai chiều theo mô hình chính sách.

Các biến thể này là cách mô hình hóa; không có nghĩa Spring Security tự động áp dụng toàn bộ khi thêm một annotation `@PreAuthorize`.

## 4. Spring Security biểu diễn role như thế nào?

Sau khi xác thực thành công, Spring Security đặt đối tượng `Authentication` vào `SecurityContext` phù hợp. `Authentication` cung cấp `principal`, trạng thái xác thực và tập `Collection<? extends GrantedAuthority>`.

`GrantedAuthority` biểu diễn **một tên quyền hạn** mà cơ chế phân quyền có thể đối chiếu, ví dụ:

```text
Authentication
  principal = "editor"
  authenticated = true
  authorities = ["ROLE_EDITOR", "article:read", "article:write"]
```

Spring Security không buộc mọi authority đều bắt đầu bằng `ROLE_`. Theo quy ước mặc định, **role là một authority với tiền tố `ROLE_`**; các quyền chi tiết có thể dùng tên riêng như `article:read`.

| Cấu hình/biểu thức | Kiểm tra theo mặc định | Ghi chú |
| --- | --- | --- |
| `hasRole("ADMIN")` | authority `ROLE_ADMIN` | Tự thêm tiền tố role mặc định |
| `hasAnyRole("READER", "EDITOR")` | `ROLE_READER` **hoặc** `ROLE_EDITOR` | Không đòi cả hai |
| `hasAuthority("ROLE_ADMIN")` | chính xác chuỗi `ROLE_ADMIN` | Không tự thêm tiền tố |
| `hasAuthority("article:write")` | chính xác chuỗi `article:write` | Hữu ích cho permission chi tiết |
| `authenticated()` | trạng thái xác thực đáp ứng yêu cầu | Không thay một điều kiện role cụ thể |
| `permitAll()` | cho phép truy cập route | Không tự biến người dùng thành đã xác thực |
| `denyAll()` | từ chối truy cập | Hữu ích cho chính sách mặc định |

**Lỗi phổ biến:** dùng `hasRole("ROLE_ADMIN")` với cơ chế prefix mặc định; hãy truyền `"ADMIN"` vào `hasRole`, hoặc dùng `hasAuthority("ROLE_ADMIN")` nếu muốn đối chiếu đúng chuỗi. Hệ thống có thể tùy biến role prefix; mọi ví dụ ở đây dùng quy ước mặc định.

Khi tạo tài khoản bằng `User.withUsername(...).roles("ADMIN")`, Spring Security chuyển role thành authority `ROLE_ADMIN`. Ngược lại, `.authorities("article:write")` giữ nguyên tên authority đã cung cấp. Không đưa tiền tố `ROLE_` vào tham số của `.roles(...)`.

Một người chỉ có `ROLE_ADMIN` **không tự có** `ROLE_EDITOR`. Nếu chính sách yêu cầu cả hai được sửa bài, có thể:

- Gán thêm các authorities cho admin.
- Cấu hình `RoleHierarchy` rõ ràng.
- Viết điều kiện `hasAnyRole('EDITOR', 'ADMIN')` nếu chỉ cần hai role này cùng được phép.

Cách cuối là **một quy tắc OR cho hành động**, không phải khai báo quan hệ kế thừa.

## 5. Luồng ra quyết định trong Spring Security

Ở ứng dụng Spring MVC (Servlet), luồng thường là:

```text
HTTP request
  ↓
Servlet Filter Chain
  ↓
Spring Security FilterChainProxy / SecurityFilterChain
  ├─ lấy/tạo Authentication qua cơ chế đã cấu hình
  ├─ xác định requestMatcher áp dụng
  └─ kiểm tra rule trong authorizeHttpRequests
       ├─ từ chối → entry point / access-denied handling
       └─ cho đi tiếp
             ↓
          Controller
             ↓
       Spring bean proxy có @PreAuthorize? 
             ├─ từ chối → AccessDeniedException
             └─ cho gọi phương thức nghiệp vụ
                    ↓
                 Response
```

**Vị trí quyết định quyền:** request authorization (bảo vệ đường HTTP) và method authorization (bảo vệ lời gọi tới bean). Cả hai có thể được dùng đồng thời. Một service có thể bị gọi từ controller, scheduled job, message listener hoặc thành phần khác; vì vậy chỉ chặn URL đôi khi chưa đủ cho chính sách nghiệp vụ.

Ở `authorizeHttpRequests`, Spring Security xét các cặp matcher/rule **theo thứ tự khai báo và áp dụng rule đầu tiên phù hợp**. Quy tắc cụ thể phải đặt trước quy tắc bao quát:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/admin").hasRole("ADMIN")
    .requestMatchers("/reports/**").authenticated()
    .anyRequest().denyAll()
)
```

Đây là **fragment** bên trong `HttpSecurity`, không phải file Java độc lập. Nếu đặt `"/reports/**"` lên đầu, request `"/reports/admin"` sẽ khớp quy tắc tổng quát trước, khiến quy tắc `ADMIN` phía sau không được dùng. Không nên dựa vào thứ tự tình cờ để bảo vệ tài nguyên.

**401 và 403:**

- `401 Unauthorized` thường chỉ ra request chưa có xác thực hợp lệ và ứng dụng yêu cầu xác thực; HTTP Basic thường kèm `WWW-Authenticate`.
- `403 Forbidden` thường là request đã được nhận diện nhưng không đạt điều kiện phân quyền.
- Việc chọn response cụ thể còn phụ thuộc cơ chế authentication entry point, access-denied handler, session, token và cấu hình ngoại lệ. `403` cũng có thể do CSRF hoặc quy tắc khác, không phải cứ thấy 403 là sai role.

## 6. Ví dụ Java 17 runnable: RBAC cho khu vực bài viết

Ví dụ cố tình dùng **Spring Boot 3.3.13 (Spring Security 6.x)** và Servlet MVC. Ứng dụng chạy bằng Gradle 8.x và Java 17+. Ba tài khoản demo có đúng một role: `reader`, `editor`, `admin`.

Bốn endpoint GET giúp quan sát quyền mà không cần thay đổi dữ liệu hoặc vô hiệu hóa CSRF:

| Endpoint | Điểm kiểm soát | Quy tắc |
| --- | --- | --- |
| `GET /public` | HTTP security | Ai cũng xem được |
| `GET /articles` | HTTP + service | Phải xác thực; service cho READER/EDITOR/ADMIN |
| `GET /articles/editor` | HTTP + service | Phải xác thực; service cho EDITOR/ADMIN |
| `GET /articles/admin` | HTTP + service | HTTP yêu cầu ADMIN; service cũng yêu cầu ADMIN |

Tất cả endpoint chưa được liệt kê bị chặn bởi `anyRequest().denyAll()`. Bộ lọc HTTP dùng thứ tự matcher rõ ràng; service thực hiện thêm kiểm tra bằng `@PreAuthorize`. Điều này minh họa hai lớp kiểm soát quyền.

### 6.1. Cấu trúc dự án

```text
rbac-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/rbac/
    │   ├── RbacDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ArticleService.java
    │   └── ArticleController.java
    └── test/java/com/example/rbac/
        └── RbacSecurityTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'rbac-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng **một web stack** (`spring-boot-starter-web`) trong ví dụ này. Các phần ví dụ ở những mục sau tạo thành một ứng dụng độc lập; hãy đặt đúng tên file/package, không ghép toàn bộ các class vào một file.

### 6.2. Main application

**`src/main/java/com/example/rbac/RbacDemoApplication.java`**

```java
package com.example.rbac;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RbacDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RbacDemoApplication.class, args);
    }
}
```

### 6.3. Định nghĩa người dùng và quy tắc HTTP

**`src/main/java/com/example/rbac/SecurityConfig.java`**

```java
package com.example.rbac;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/articles/admin").hasRole("ADMIN")
                .requestMatchers("/articles/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor123")
            .roles("EDITOR")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

Giải thích chính xác từng lựa chọn:

1. `@EnableMethodSecurity` kích hoạt kiểm tra `@PreAuthorize` cho các bean Spring; thêm Spring Security dependency **chưa tự bật** method security.
2. `permitAll()` cho phép `/public` không cần tài khoản.
3. `requestMatchers("/articles/admin").hasRole("ADMIN")` được xét **trước** `"/articles/**"` và yêu cầu authority `ROLE_ADMIN`.
4. Các request `/articles...` khác chỉ cần authentication tại lớp HTTP; lớp service sẽ kiểm tra quyền chi tiết.
5. `anyRequest().denyAll()` từ chối endpoint nằm ngoài danh sách (mặc định đóng).
6. `httpBasic(withDefaults())` bật xác thực HTTP Basic, `formLogin(...disable())` loại form login để kết quả curl dễ quan sát. **CSRF vẫn được giữ nguyên**; tất cả thao tác ví dụ là GET an toàn, không thay đổi dữ liệu.
7. `InMemoryUserDetailsManager` phù hợp bài thực hành; production cần nguồn user, lifecycle role và storage phù hợp.
8. `{noop}` cho phép lưu password dạng rõ chỉ để chạy demo; **không dùng trong production**. Production cần mã hóa mật khẩu có salt, secrets được bảo vệ và HTTPS.

**Quan trọng về “ADMIN kế thừa EDITOR”:** ở đây `admin` chỉ có `ROLE_ADMIN`. Admin được gọi trang editor vì service sẽ dùng `hasAnyRole('EDITOR','ADMIN')`, không phải vì hệ thống tự cấp `ROLE_EDITOR`.

### 6.4. Bảo vệ thao tác bằng @PreAuthorize

**`src/main/java/com/example/rbac/ArticleService.java`**

```java
package com.example.rbac;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    @PreAuthorize("hasAnyRole('READER', 'EDITOR', 'ADMIN')")
    public String listFor(String username) {
        return "articles for " + username;
    }

    @PreAuthorize("hasAnyRole('EDITOR', 'ADMIN')")
    public String editorArea() {
        return "editor area";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminArea() {
        return "admin area";
    }
}
```

Lớp service là **Spring-managed bean**. Khi controller gọi qua bean proxy, Spring Security kiểm tra biểu thức **trước** khi thực thi phương thức. Nếu không có quyền, lời gọi bị chặn và không trả giá trị business như một lời gọi thành công.

Đừng dùng ví dụ này để suy ra rằng `@PreAuthorize` sẽ kích hoạt trên mọi lời gọi Java: gọi một method annotated bằng `this.otherMethod()` trong cùng object có thể đi vòng ngoài proxy AOP (self-invocation). Với thiết kế thực tế, tổ chức điểm vào bảo mật qua bean/service được Spring quản lý, kiểm thử trực tiếp hành vi phân quyền và chú ý đến proxying.

### 6.5. Controller chuyển danh tính đã xác thực tới service

**`src/main/java/com/example/rbac/ArticleController.java`**

```java
package com.example.rbac;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {
    private final ArticleService articleService;

    public ArticleController(ArticleService articleService) {
        this.articleService = articleService;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/articles")
    public String list(Authentication authentication) {
        return articleService.listFor(authentication.getName());
    }

    @GetMapping("/articles/editor")
    public String editor() {
        return articleService.editorArea();
    }

    @GetMapping("/articles/admin")
    public String admin() {
        return articleService.adminArea();
    }
}
```

`Authentication` ở endpoint `/articles` được Spring MVC cung cấp từ security context của request đã được phép tiếp tục. Dùng `authentication.getName()` để hiển thị tên danh tính trong demo; không dùng tên này như bằng chứng quyền sở hữu tài nguyên. Service vẫn có kiểm tra `@PreAuthorize` dựa trên authorities.

### 6.6. Chạy và quan sát

Máy cần **JDK 17+ và Gradle 8.x** (hoặc Gradle Wrapper tương thích). Tại thư mục `rbac-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper thì dùng `./gradlew test` và `./gradlew bootRun` trên Linux/macOS, hoặc `gradlew.bat test` và `gradlew.bat bootRun` trên Windows. Vì đây là ứng dụng Spring có dependency ngoài JDK, `javac`/`java` riêng lẻ không tự giải quyết classpath; Gradle biên dịch và chạy Java phù hợp.

Ở một terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/articles
curl -i -u reader:reader123 http://localhost:8080/articles
curl -i -u reader:reader123 http://localhost:8080/articles/editor
curl -i -u editor:editor123 http://localhost:8080/articles/editor
curl -i -u editor:editor123 http://localhost:8080/articles/admin
curl -i -u admin:admin123 http://localhost:8080/articles/admin
curl -i -u admin:admin123 http://localhost:8080/articles/editor
```

**Ma trận kết quả dự kiến (với cấu hình đúng như trên):**

| Ai gọi | `/public` | `/articles` | `/articles/editor` | `/articles/admin` |
| --- | :---: | :---: | :---: | :---: |
| Anonymous | 200 | 401 | 401 | 401 |
| reader | 200 | 200 | 403 | 403 |
| editor | 200 | 200 | 200 | 403 |
| admin | 200 | 200 | 200 | 200 |

Ở endpoint `/articles/admin`, rule URL chặn reader/editor trước khi vào controller. Ở `/articles/editor`, rule URL chỉ yêu cầu authenticated nên reader đi đến lời gọi service, sau đó `@PreAuthorize` từ chối. Cả hai có thể trả 403 nhưng là **hai điểm kiểm tra khác nhau**.

Một số body thành công xác định được từ code:

```text
GET /public                      → public
GET /articles (reader)           → articles for reader
GET /articles/editor (editor)    → editor area
GET /articles/admin (admin)      → admin area
```

Đây là **body**, không phải toàn bộ response wire-format. Status line, headers và nội dung body của trường hợp lỗi có thể thay đổi theo cấu hình HTTP, content negotiation và cơ chế xử lý lỗi; chỉ kỳ vọng các mã trạng thái nêu trong ma trận.

### 6.7. Test phân quyền tự động

**`src/test/java/com/example/rbac/RbacSecurityTest.java`**

```java
package com.example.rbac;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RbacSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadArticles() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", roles = "READER")
    void readerCanListButCannotEdit() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isOk())
            .andExpect(content().string("articles for reader"));

        mvc.perform(get("/articles/editor"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanOpenEditorAreaButNotAdminArea() throws Exception {
        mvc.perform(get("/articles/editor"))
            .andExpect(status().isOk())
            .andExpect(content().string("editor area"));

        mvc.perform(get("/articles/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanOpenBothPrivilegedAreas() throws Exception {
        mvc.perform(get("/articles/editor"))
            .andExpect(status().isOk());

        mvc.perform(get("/articles/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));
    }

    @Test
    @WithMockUser(roles = "OTHER")
    void anyAuthenticatedRoleIsNotEnoughForService() throws Exception {
        mvc.perform(get("/articles"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Kiểm thử trên dùng Spring MVC `MockMvc` và `spring-security-test`. `@WithMockUser(roles = "EDITOR")` tự tạo authority `ROLE_EDITOR` cho **test request**, không đọc tài khoản trong `InMemoryUserDetailsManager`. Vì vậy kiểm thử này xác minh quy tắc authorization, chưa phải một kiểm thử end-to-end cho password store hay luồng HTTP Basic thật. Lệnh `curl` phía trên giúp quan sát trường hợp authentication bằng credentials thực.

Bộ test có ý nghĩa hơn kiểm tra “endpoint có trả 200 không”: nó kiểm tra explicit allow/deny, trạng thái chưa đăng nhập và role không được liệt kê. Khi chính sách thay đổi, cập nhật ma trận nghiệp vụ và test cùng lúc.

## 7. Vai trò, permission chi tiết và kiểm tra theo HTTP method

Các tên role như `EDITOR` tiện cho người học, nhưng hệ thống thực tế thường cần quyền theo hành động. Thay vì đặt rất nhiều URL theo tên role, có thể mô hình hóa authorities chi tiết:

```text
ROLE_READER → article:read
ROLE_EDITOR → article:read, article:create, article:update
ROLE_ADMIN  → article:read, article:create, article:update,
              article:publish, article:delete, user:manage
```

Khi principal đã được cấp authorities tương ứng từ nguồn tin cậy, security có thể kiểm tra trực tiếp:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .hasAuthority("article:read")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAuthority("article:create")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**")
        .hasAuthority("article:delete")
    .anyRequest().denyAll()
)
```

Đây là **fragment cấu hình**, chưa phải chương trình độc lập; cần import `org.springframework.http.HttpMethod` và đặt trong `HttpSecurity`. Các authority `article:*` **không tự sinh ra** từ `.roles("EDITOR")` trong demo phía trên; bạn phải gán/mapping chúng một cách tường minh hoặc cấu hình chính sách tương ứng. Đừng copy fragment này thay demo rồi kỳ vọng ba tài khoản cũ tự có quyền `article:read`.

Với API có mutation, HTTP method là một tín hiệu quan trọng nhưng **chưa đủ**: cần kiểm tra ownership, trạng thái, object ID, tenant, validation, CSRF (nếu trình duyệt gửi cookie/credentials) và chính sách nghiệp vụ. Không tắt CSRF theo thói quen chỉ để làm cho một request POST thử nghiệm trả 200. Với REST API stateless dùng bearer token trong `Authorization` header, có thể có lý do kiến trúc rõ ràng để cấu hình CSRF khác với ứng dụng dựa vào cookie/session; phải đánh giá theo cơ chế xác thực thực tế.

### Role hierarchy có phải mặc định không?

Không. Spring Security hỗ trợ cấu hình role hierarchy, nhưng trong demo trên chỉ tồn tại **ba authority riêng biệt**. Ví dụ biểu diễn thứ bậc mong muốn:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_READER
```

Đây chỉ là **sơ đồ chính sách**, chưa phải cấu hình thực thi. Nếu muốn hierarchy hoạt động, cần khai báo `RoleHierarchy` và đảm bảo bộ phận authorization liên quan thực sự sử dụng hierarchy đó. Nếu hệ thống không có hierarchy, hãy viết điều kiện role rõ ràng hoặc cấp authorities tương ứng. Không giả định tên role có tính kế thừa theo ngôn ngữ tự nhiên.

## 8. RBAC không giải quyết mọi bài toán phân quyền

Một chính sách chỉ theo role có thể quá rộng. Ví dụ cả Lan và Minh đều mang `ROLE_EDITOR`, nhưng một bài viết là bản nháp riêng của Lan. Nếu rule chỉ là `hasRole('EDITOR')`, hệ thống có thể vô tình cho Minh sửa bản nháp của Lan.

Cần phân biệt:

| Câu hỏi | Cơ chế phù hợp |
| --- | --- |
| “Người gọi thuộc nhóm EDITOR không?” | RBAC / role authorization |
| “Người gọi có permission `article:update` không?” | Authority / permission-based authorization |
| “Bài viết này do ai sở hữu?” | Kiểm tra quan hệ user–resource (ownership/ReBAC) |
| “Bài viết đang `DRAFT` hay `PUBLISHED`?” | Kiểm tra trạng thái/thuộc tính resource (ABAC) |
| “User và bài viết có thuộc cùng tenant?” | Tenant boundary + object-level authorization |
| “Người yêu cầu có thể tự phê duyệt thao tác mình vừa tạo không?” | Ràng buộc nghiệp vụ / separation of duties |

Spring Security cho phép phối hợp điều kiện role với điều kiện nghiệp vụ. Ví dụ khái niệm:

```java
@PreAuthorize("hasRole('EDITOR') and @articleAccess.canEdit(#articleId, authentication)")
public void editArticle(long articleId) {
    // cập nhật sau khi đã kiểm tra quyền
}
```

Đây là **fragment minh họa, không độc lập**: cần bean `articleAccess` hiện thực `canEdit(...)`, phương thức phải nằm trong Spring-managed service proxy và kiểm tra trạng thái/tenant/ownership bằng dữ liệu server tin cậy. Kiểm tra quyền và cập nhật cần được thiết kế an toàn trước thay đổi đồng thời; điều kiện ở ngoài transaction có thể không bảo vệ được dữ liệu đã đổi trạng thái ngay sau khi kiểm tra.

**Chống IDOR (Insecure Direct Object Reference):** endpoint `GET /documents/1` an toàn với editor chưa đủ chứng minh `GET /documents/2` cũng được phép cho editor đó. Mỗi request tới object cụ thể cần được kiểm tra tại ranh giới dữ liệu phù hợp.

## 9. Quản lý vòng đời role và nguồn tin cậy

RBAC chỉ đáng tin khi **nguồn gán role đáng tin**:

- Với login nội bộ, gán role từ user store hoặc identity service đã được bảo vệ, không lấy từ JSON body đăng ký công khai.
- Với OAuth2 Resource Server/JWT, token phải được **xác minh chữ ký, issuer, audience, expiry và các ràng buộc cần thiết**. Role/claim từ IdP thường cần bước mapping sang `GrantedAuthority` theo chính sách ứng dụng. Không giả định mọi JWT đều có `ROLE_ADMIN` chỉ vì chứa claim tên `roles`.
- Với đa tenant, vai trò “ADMIN” có thể chỉ có nghĩa trong một tenant; phân quyền phải gắn đúng phạm vi và tài nguyên.
- Khi admin thay đổi role, cần xem xét độ trễ cập nhật ở session, cache hoặc token còn hiệu lực. Role đã bị thu hồi nhưng token vẫn chứa quyền cũ là một rủi ro cần có chiến lược giải quyết.
- Ghi audit log cho thay đổi gán role và các hành động nhạy cảm; không log mật khẩu, token, session cookie hay secrets.
- Phân quyền ở **server**. Ẩn nút “Xóa” ở UI chỉ cải thiện trải nghiệm; client vẫn có thể gửi HTTP request trực tiếp.

Nguyên tắc thực hành: **least privilege**, **default deny**, **separation of duties** và kiểm tra quyền đối với **chính tài nguyên đang thao tác**.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm `hasRole("ROLE_ADMIN")` với `hasRole("ADMIN")` | Sai cú pháp/semantics role prefix mặc định | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Cho rằng ADMIN tự kế thừa EDITOR | Admin có thể bị từ chối, hoặc policy bị hiểu sai | Cấu hình hierarchy thật, cấp đủ authorities, hoặc khai báo `hasAnyRole` rõ ràng |
| Đưa rule `"/**".permitAll()` trước rule nhạy cảm | Matcher đầu khớp mọi thứ, rule phía sau vô hiệu | Đặt rule cụ thể trước, dùng `denyAll` cuối |
| Chỉ bảo vệ controller nhưng service được gọi qua đường khác | Bỏ qua kiểm tra quyền ở nghiệp vụ | Bảo vệ service qua `@PreAuthorize` hoặc authorization manager |
| Gọi method cùng bean bằng `this.secureMethod()` | Có thể đi vòng ngoài AOP proxy | Gọi qua Spring bean proxy, test tình huống thực |
| Chỉ kiểm tra role mà không kiểm tra owner/tenant/state | IDOR, đọc/sửa tài nguyên của người khác | Đánh giá resource cụ thể bằng dữ liệu đáng tin |
| Dùng header `X-Role: ADMIN` của client làm role | Tự nâng quyền | Dựa vào `Authentication` và mapping từ nguồn xác thực được kiểm chứng |
| Nhầm `authenticated()` là cho phép role phù hợp | Mọi user đăng nhập có thể được đi qua lớp HTTP | Dùng rule role/authority rõ ràng và method security |
| Tin rằng mọi 403 đều do sai role | Bỏ sót CSRF hoặc handler khác | Xem filter chain, security logs và nguyên nhân thực |
| Dùng password `{noop}` / in-memory user cho production | Mật khẩu không được bảo vệ, role khó quản lý | Encoder mạnh, kho danh tính và quy trình cấp/thu hồi role |
| Không test role bị từ chối | Dễ có lỗ hổng “ai cũng được” | Test ma trận positive/negative và unknown role |
| Thay role nhưng không xét session/token còn hạn | Quyền cũ có thể sống lâu hơn mong muốn | Thiết kế expiry, refresh, revoke/cache invalidation |

### Checklist khi một request bị từ chối bất ngờ

1. Đăng nhập thành công chưa? `Authentication` có name, trạng thái và authorities nào (chỉ log thông tin đã lược bỏ dữ liệu nhạy cảm)?
2. Authority thực tế là `ROLE_EDITOR` hay `EDITOR`? Rule là `hasRole` hay `hasAuthority`?
3. Request method/path có khớp matcher dự định không? Có rule bao quát đứng trước không?
4. Request bị chặn ở `SecurityFilterChain` hay `@PreAuthorize`? Có CSRF, custom filter hoặc exception handler khác không?
5. Quyết định còn phụ thuộc resource ID, owner, tenant, trạng thái hay policy đang thay đổi không?
6. Có test đại diện cho đúng user-role-action-resource này chưa?

## 11. Câu hỏi luyện tập

**1.** Một user có `ROLE_READER` và `ROLE_EDITOR`, còn `/admin` yêu cầu `hasRole("ADMIN")`. User có được phép không?

*Không.* Cần authority `ROLE_ADMIN` (hoặc một cơ chế phân quyền được cấu hình khác cho phép truy cập); có hai role khác không mặc nhiên suy ra ADMIN.

**2.** Khác biệt giữa `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")`?

*Trong cấu hình role prefix mặc định, chúng cùng kiểm tra sự hiện diện của `ROLE_ADMIN`.* `hasAuthority` so khớp chuỗi tường minh; `hasRole` áp dụng tiền tố role.

**3.** Vì sao `anyRequest().denyAll()` hữu ích?

*Nó khóa các route không được liệt kê*, giảm nguy cơ endpoint mới lộ ra mà chưa có policy. Dù vậy, phải chủ động cho phép những route cần thiết như health/readiness, static assets theo yêu cầu triển khai.

**4.** User đăng nhập và gọi `/articles/editor` nhưng bị 403; có thể vì sao?

*Trong demo, lớp HTTP cho authenticated đi tiếp, còn `@PreAuthorize` của `editorArea()` đòi EDITOR hoặc ADMIN.* Reader không thỏa điều kiện service. Với ứng dụng khác, cần kiểm tra thêm CSRF/filter/rule cụ thể.

**5.** Dùng `@PreAuthorize("hasRole('EDITOR')")` có đủ để cho editor sửa một bài viết bất kỳ không?

*Không.* Nếu yêu cầu chỉ sửa bài do mình sở hữu hoặc còn ở trạng thái draft, cần kiểm tra object/owner/state bằng dữ liệu server.

**6.** Nếu API đăng ký cho phép người dùng gửi `{"role":"ADMIN"}` và lưu trực tiếp, lỗi gì xảy ra?

*Privilege escalation / mass assignment.* Backend phải xác định role được phép cấp, phân tách luồng tự đăng ký và luồng quản trị.

**7.** Một user `ROLE_ADMIN` trong demo có `ROLE_EDITOR` không? Vì sao vẫn vào được `/articles/editor`?

*Không.* Code service kiểm tra `hasAnyRole('EDITOR','ADMIN')` nên `ROLE_ADMIN` thỏa biểu thức OR.

**8.** Kết quả 401 và 403 có đồng nghĩa “server lỗi” không?

*Không.* Cả hai thường là phản hồi có chủ đích của security; 401 liên quan yêu cầu xác thực, 403 liên quan bị từ chối truy cập. Phải xem cấu hình để xác định lý do chính xác.

## 12. Tổng kết

- **RBAC** là mô hình gán quyền thông qua **vai trò**: user → role → permission.
- Trong Spring Security, role thường là **`GrantedAuthority` bắt đầu bằng `ROLE_`**, và `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo quy ước mặc định.
- Phân quyền tại **URL** bằng `SecurityFilterChain` giúp kiểm soát request HTTP; phân quyền tại **method/service** bằng `@EnableMethodSecurity` + `@PreAuthorize` giúp bảo vệ thao tác nghiệp vụ.
- **Thứ tự `requestMatchers` rất quan trọng; dùng chính sách mặc định từ chối** và kiểm thử cả trường hợp được phép lẫn bị từ chối.
- **ADMIN không tự kế thừa role thấp hơn**; hierarchy hoặc permission mapping phải có cấu hình cụ thể.
- RBAC không thay kiểm tra **quyền sở hữu tài nguyên, tenant, trạng thái nghiệp vụ**, và không thay xác thực.
- Với production, role phải đến từ **nguồn tin cậy**, quản lý cấp/thu hồi rõ ràng và không dựa vào UI hay dữ liệu tự khai của client.

## Tài liệu chính thức

- Spring Security — Authorize HTTP Requests (request matchers, role/authority): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing with Spring MVC / MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — `@WithMockUser` và testing method security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Boot 3.3 system requirements (Java 17+, Gradle 7.5+/8.x): https://docs.spring.io/spring-boot/3.3/system-requirements.html
