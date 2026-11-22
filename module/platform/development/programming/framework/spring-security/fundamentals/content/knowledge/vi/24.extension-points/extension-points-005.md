# Xây chính sách quyền riêng bằng AuthorizationManager

## 1. Vì sao cần chính sách phân quyền riêng?

Một hệ thống thường bắt đầu với vài quy tắc đơn giản: ai đã đăng nhập thì được xem hồ sơ, người có vai trò `ADMIN` được mở trang quản trị. Spring Security hỗ trợ các quy tắc này bằng `authenticated()`, `hasRole(...)` và `hasAuthority(...)`. Nhưng quyền trong nghiệp vụ thực tế thường phụ thuộc **đồng thời vào người đang yêu cầu, tài nguyên cụ thể và bối cảnh của hành động**.

Ví dụ: người dùng chỉ được xem tài liệu khi tài liệu thuộc cùng tổ chức (**tenant**) và người dùng là **chủ sở hữu**; quản trị viên được xem mọi tài liệu **trong chính tenant của mình**, không được vượt sang tenant khác. Quy tắc này khó diễn đạt chỉ bằng `hasRole("USER")`, bởi role không thể trả lời “tài liệu này thuộc ai?” hoặc “tenant của tài liệu có khớp tenant của người yêu cầu không?”.

**`AuthorizationManager<T>`** là điểm mở rộng chuẩn trong Spring Security để viết một quyết định phân quyền dựa trên thông tin nghiệp vụ. Trong ví dụ học tập, ta xây một `AuthorizationManager<RequestAuthorizationContext>` cho từng yêu cầu HTTP Servlet. Nó nhận thông tin về tài khoản đã xác thực và yêu cầu hiện tại, kiểm tra chính sách rồi trả về **cho phép** hoặc **từ chối**.

Câu hỏi của chính sách:

> “Với người dùng **U**, tài liệu **D** và hành động **A**, yêu cầu này có được phép không?”

Quy tắc mẫu:

```text
ALLOW khi:
  có danh tính hợp lệ
  AND tài liệu tồn tại
  AND tenant của người dùng == tenant của tài liệu
  AND (người dùng là chủ sở hữu OR có role ADMIN)

DENY trong mọi trường hợp còn lại.
```

Đây là kiểu **kiểm soát theo thuộc tính (ABAC)** kết hợp role (RBAC) và quyền trên từng đối tượng. `ADMIN` **không tự vượt ranh giới tenant**. Việc xét tenant phải xảy ra **trước** khi cấp quyền theo vai trò.

## 2. Vị trí của AuthorizationManager trong Spring Security

Đối với Spring Security Servlet hiện đại:

1. Yêu cầu đi qua `SecurityFilterChain` được cấu hình.
2. Bộ lọc xác thực (ví dụ HTTP Basic, form login, Bearer token) nhận diện tài khoản và tạo `Authentication` nếu thông tin hợp lệ.
3. `AuthorizationFilter` nhận một `Supplier<Authentication>` và gọi cơ chế phân quyền do `authorizeHttpRequests(...)` cấu hình.
4. Với URL khớp một `requestMatchers(...)` có `access(customAuthorizationManager)`, Spring Security gọi **AuthorizationManager do ta viết**, truyền tài khoản và `RequestAuthorizationContext`.
5. Kết quả `AuthorizationDecision(true)` cho phép tiếp tục tới controller; `AuthorizationDecision(false)` dẫn tới từ chối và xử lý bằng cơ chế ngoại lệ bảo mật.
6. Người chưa xác thực thường được yêu cầu xác thực (ví dụ HTTP Basic trả **401**); người đã xác thực nhưng không đủ quyền thường nhận **403**. Hành vi chính xác phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler` và các bộ lọc xác thực đã cấu hình.

`AuthorizationManager` chỉ **đưa ra quyết định quyền**. Nó không nên tự viết JSON/HTML, chuyển hướng, xử lý mật khẩu hoặc gọi controller. Tách trách nhiệm giúp chính sách dễ đọc, dễ kiểm thử và tái sử dụng.

### Các loại thông tin liên quan

| Thành phần | Vai trò |
| --- | --- |
| `Authentication` | Danh tính từ hệ thống xác thực; `getName()`, `getAuthorities()` và loại principal. |
| `Supplier<Authentication>` | Cung cấp `Authentication` khi cần. Có thể trì hoãn việc lấy danh tính cho những luật không cần đến. |
| `RequestAuthorizationContext` | Bối cảnh HTTP, gồm `getRequest()` và `getVariables()` lấy các tham số được matcher trích từ đường dẫn. |
| `AuthorizationDecision` | Kết quả có `isGranted()` cho biết cho phép hay từ chối. |
| `AuthorizationManager<RequestAuthorizationContext>` | Chính sách riêng được gắn với `.access(manager)` tại mức HTTP request. |
| `AuthorizationFilter` | Gọi cơ chế phân quyền trong chuỗi bộ lọc. |
| `ExceptionTranslationFilter` | Chuyển ngoại lệ từ chối truy cập sang entry point hoặc handler tương ứng khi ngoại lệ nằm trong luồng mà bộ lọc xử lý. |

**Không nên hiểu `Authentication.isAuthenticated()` là đủ để biết đó là người dùng thực.** Với anonymous authentication, Spring Security có thể đặt một `AnonymousAuthenticationToken` có cờ `isAuthenticated() == true`. Chính sách mẫu phải nhận diện và từ chối anonymous riêng.

### Phiên bản API cần chú ý

Trong **Spring Security 6.0–6.3**, phương thức cốt lõi của interface là:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);
```

Từ **Spring Security 6.4**, `check(...)` được đánh dấu deprecated và có phương thức `authorize(...)` trả về `AuthorizationResult`, giúp chuẩn bị cho các phiên bản mới. Với Spring Security **7.x**, triển khai bằng lớp thường cần dùng chữ ký `authorize(...)` tương ứng với phiên bản đang chạy.

Ví dụ bên dưới dùng **lambda** làm `AuthorizationManager<RequestAuthorizationContext>` và trả `new AuthorizationDecision(...)`. Cách viết này bám vào *functional interface*, tránh phải tự ghi đè tên phương thức `check`/`authorize` trong ví dụ về chính sách. Khi sao chép sang dự án, hãy đối chiếu đúng phiên bản Spring Security trong dependency tree; không tùy tiện trộn API 6.x và 7.x.

## 3. Thiết kế chính sách trước khi lập trình

Giả sử ứng dụng có ba tài liệu:

| ID | Tenant | Chủ sở hữu | Nội dung |
| --- | --- | --- | --- |
| `doc-a` | `acme` | `alice` | Tài liệu A |
| `doc-b` | `acme` | `bob` | Tài liệu B |
| `doc-c` | `globex` | `carol` | Tài liệu C |

Tài khoản có quyền theo tenant:

| Tài khoản | Tenant hợp lệ | Authority |
| --- | --- | --- |
| `alice` | `acme` | `ROLE_USER` |
| `bob` | `acme` | `ROLE_USER` |
| `carol` | `globex` | `ROLE_USER` |
| `admin` | `acme` | `ROLE_ADMIN` |

Yêu cầu học tập: `GET /api/documents/{documentId}` chỉ được phép khi **tài liệu tồn tại**, người dùng **thuộc cùng tenant** và người dùng **là chủ tài liệu hoặc ADMIN trong tenant đó**.

Ví dụ:

- `alice` xem `doc-a` → **ALLOW**, cùng tenant và là chủ sở hữu.
- `bob` xem `doc-a` → **DENY**, cùng tenant nhưng không phải chủ, cũng không là admin.
- `admin` xem `doc-a` → **ALLOW**, cùng tenant và có `ROLE_ADMIN`.
- `admin` xem `doc-c` → **DENY**, vì khác tenant dù là admin.
- `carol` xem `doc-c` → **ALLOW**, cùng tenant và là chủ sở hữu.
- Người chưa gửi credentials → **DENY**, cơ chế HTTP Basic yêu cầu đăng nhập.
- Một ID không tồn tại → **DENY** ngay trong chính sách mẫu để tránh vô tình tiết lộ tài liệu; cách biểu diễn 403/404 trong sản phẩm thực tế cần chính sách riêng nhất quán.

Ta sẽ lưu dữ liệu trong bộ nhớ để quan sát kết quả. Ứng dụng thực tế phải lấy tài liệu và quan hệ tenant từ cơ sở dữ liệu hoặc dịch vụ đáng tin cậy, **không tin tenant ID do client tự khai trong query parameter hay header**.

## 4. Ví dụ Java 17+: viết AuthorizationManager cho tài liệu

Ví dụ dành cho **Spring Boot 3.x / Spring Security 6.x, ứng dụng Servlet**. Tạo một dự án bằng Spring Initializr với dependency **Spring Web** và **Spring Security**, sử dụng Java 17 trở lên. Đặt **toàn bộ mã** vào đúng tệp:

```text
src/main/java/demo/authz/DocumentPolicyApplication.java
```

Đây là chương trình Spring Boot độc lập **trong dự án có các thư viện Spring tương ứng**. Lệnh `javac` trần không đủ classpath để biên dịch. Không cần cơ sở dữ liệu hay hệ thống phân quyền ngoài cho ví dụ.

```java
package demo.authz;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DocumentPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentPolicyApplication.class, args);
    }

    public record Doc(
        String id,
        String tenantId,
        String owner,
        String body
    ) {}

    static final class DocumentStore {
        private final Map<String, Doc> documents = Map.of(
            "doc-a",
            new Doc("doc-a", "acme", "alice", "Tai lieu A"),
            "doc-b",
            new Doc("doc-b", "acme", "bob", "Tai lieu B"),
            "doc-c",
            new Doc("doc-c", "globex", "carol", "Tai lieu C")
        );

        Doc find(String id) {
            return documents.get(id);
        }
    }

    static final class TenantDirectory {
        private final Map<String, String> tenants = Map.of(
            "alice", "acme",
            "bob", "acme",
            "carol", "globex",
            "admin", "acme"
        );

        String tenantOf(String username) {
            return tenants.get(username);
        }
    }

    @Bean
    DocumentStore documentStore() {
        return new DocumentStore();
    }

    @Bean
    TenantDirectory tenantDirectory() {
        return new TenantDirectory();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentPolicy(
            DocumentStore documents,
            TenantDirectory tenants) {

        return (authenticationSupplier, context) -> {
            Authentication auth = authenticationSupplier.get();

            // Chưa xác thực hoặc là người dùng anonymous.
            if (auth == null
                    || !auth.isAuthenticated()
                    || auth instanceof AnonymousAuthenticationToken) {
                return new AuthorizationDecision(false);
            }

            // Giá trị được trích từ đường dẫn đã khớp matcher.
            String id = context.getVariables().get("documentId");
            Doc doc = documents.find(id);
            if (doc == null) {
                return new AuthorizationDecision(false);
            }

            // Tenant phải đến từ dữ liệu đáng tin cậy phía máy chủ.
            String userTenant = tenants.tenantOf(auth.getName());
            if (userTenant == null
                    || !userTenant.equals(doc.tenantId())) {
                return new AuthorizationDecision(false);
            }

            boolean owner = doc.owner().equals(auth.getName());
            boolean tenantAdmin = auth.getAuthorities().stream()
                .anyMatch(authority ->
                    "ROLE_ADMIN".equals(authority.getAuthority())
                );

            return new AuthorizationDecision(owner || tenantAdmin);
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> documentPolicy)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/documents/{documentId}"
                ).access(documentPolicy)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    static final class DocumentController {
        private final DocumentStore documents;

        DocumentController(DocumentStore documents) {
            this.documents = documents;
        }

        @GetMapping("/api/documents/{documentId}")
        public Doc getDocument(@PathVariable String documentId) {
            // Chỉ tới đây sau khi manager cho phép.
            // Map bất biến nên tài liệu đã kiểm tra vẫn tồn tại
            // trong ví dụ này.
            return documents.find(documentId);
        }
    }
}
```

### Giải thích mã theo luồng xử lý

**1. `DocumentStore` và `TenantDirectory` mô phỏng dữ liệu đáng tin.** `DocumentStore` trả tài liệu theo ID. `TenantDirectory` ánh xạ một username đã xác thực sang tenant. Khi xây hệ thống thật, có thể thay hai lớp này bằng repository hoặc service có truy vấn phù hợp. Ví dụ cố ý không đọc tenant ID từ query/header do client tự gửi.

**2. `documentPolicy(...)` là một Bean kiểu `AuthorizationManager<RequestAuthorizationContext>`.** Tham số đầu tiên của lambda là `Supplier<Authentication>`; tham số thứ hai chứa yêu cầu HTTP và biến đường dẫn. Chính sách lấy ID bằng:

```java
String id = context.getVariables().get("documentId");
```

Biến `documentId` đến từ chính mẫu `"/api/documents/{documentId}"` đã được đăng ký ở `requestMatchers(...)`. Nếu đổi tên biến ở matcher, phải cập nhật tên lấy từ context; nếu không, `id` sẽ là `null` và chính sách từ chối.

**3. Kiểm tra anonymous trước khi xét quyền.** Ngoài `null` và cờ `isAuthenticated()`, chính sách nhận diện `AnonymousAuthenticationToken`. Nhờ đó người chưa đăng nhập không được vượt qua bước kiểm tra chỉ vì token anonymous có trạng thái “authenticated” ở mức đối tượng Java.

**4. Kiểm tra tenant trước khi cho ADMIN đi qua.** Đây là ranh giới bảo mật quan trọng: một người có `ROLE_ADMIN` chỉ được xem tài liệu của tenant mà mình thuộc về. Việc viết biểu thức `owner || tenantAdmin` *sau* điều kiện tenant tránh lỗi:

```java
// Sai nếu ADMIN không được quyền xuyên tenant:
boolean allowed = isAdmin || (sameTenant && isOwner);

// Đúng với chính sách ví dụ:
boolean allowed = sameTenant && (isAdmin || isOwner);
```

Đoạn trên chỉ minh họa logic; các biến `isAdmin`, `sameTenant` và `isOwner` là biến giả định, không phải phần bổ sung cần dán vào chương trình đã chạy ở trên.

**5. `hasRole("ADMIN")` và `ROLE_ADMIN` có liên quan nhưng không giống chuỗi đầu vào.** `.roles("ADMIN")` tạo authority `ROLE_ADMIN` theo quy ước mặc định. Chính sách dùng `"ROLE_ADMIN".equals(authority.getAuthority())`. Không kiểm tra nhầm `"ADMIN"` nếu authority thật mang tiền tố `ROLE_`.

**6. Gắn chính sách bằng `.access(documentPolicy)`.** Ở đây mọi `GET /api/documents/{documentId}` được quyết định bằng chính sách riêng; `.anyRequest().denyAll()` từ chối các URL hoặc phương thức còn lại. Các rule được xét theo thứ tự, rule cụ thể phải nằm trước fallback.

**7. `httpBasic(...)` lo phần xác thực, không thay chính sách.** Mỗi lần gọi API với tài khoản/mật khẩu, Basic authentication nhận diện người dùng. Khi không có thông tin xác thực, kết quả với Basic thường là **401** kèm `WWW-Authenticate`. Khi đã xác thực nhưng `AuthorizationManager` từ chối, kết quả thường là **403**. Ví dụ giữ mặc định CSRF của Spring Security; các phép thử chỉ dùng HTTP GET, không cần thay đổi CSRF.

## 5. Chạy và xác minh chính sách

Khởi động trong thư mục dự án Gradle đã sinh:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

Nếu dùng Maven, chạy bằng cơ chế của dự án tương ứng (ví dụ `./mvnw spring-boot:run`). Cần cài JDK phù hợp và bảo đảm dependency Spring Security có mặt. Khi chạy từ Windows PowerShell, dùng `curl.exe` nếu muốn cú pháp curl, vì bí danh `curl` của một số bản PowerShell trỏ tới công cụ khác.

Thử từng lệnh:

```bash
curl -i http://localhost:8080/api/documents/doc-a

curl -i -u alice:alice123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u bob:bob123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u admin:admin123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u admin:admin123 \
  http://localhost:8080/api/documents/doc-c

curl -i -u carol:carol123 \
  http://localhost:8080/api/documents/doc-c
```

Dấu `\` ở cuối dòng là ký hiệu nối dòng của shell kiểu Bash. Trong PowerShell, viết mỗi lệnh trên **một dòng** và thay `curl` bằng `curl.exe`.

Bảng kiểm tra kết quả:

| Người gọi | Tài nguyên | Status mong đợi | Lý do |
| --- | --- | --- | --- |
| Anonymous | `doc-a` | **401** với HTTP Basic | Chưa có danh tính được chấp nhận |
| `alice` | `doc-a` | **200** | Cùng tenant, đúng chủ sở hữu |
| `bob` | `doc-a` | **403** | Cùng tenant nhưng không phải chủ/admin |
| `admin` | `doc-a` | **200** | Admin thuộc tenant `acme` |
| `admin` | `doc-c` | **403** | Sai tenant; role ADMIN không mở khóa tenant khác |
| `carol` | `doc-c` | **200** | Cùng tenant, đúng chủ sở hữu |
| `alice` | `doc-missing` | **403** trong ví dụ | ID không tồn tại nên chính sách deny |
| `alice` | `POST /api/documents/doc-a` | **403** hoặc xử lý từ chối phù hợp cấu hình | Phương thức không được rule GET cho phép; nếu thêm POST, phải xem CSRF và handler riêng |

Với `alice` truy cập thành công `doc-a`, body JSON về mặt dữ liệu tương đương:

```json
{
  "id": "doc-a",
  "tenantId": "acme",
  "owner": "alice",
  "body": "Tai lieu A"
}
```

Thứ tự thuộc tính, bộ header, ngày tháng và các header bảo mật do server sinh có thể thay đổi. Điều cần kiểm chứng là **mã HTTP** cùng dữ liệu và đúng phạm vi truy cập. Không nhầm “HTTP 200 có nội dung JSON” với “chính sách chắc chắn đúng”; phải thử cả các trường hợp bị từ chối, đặc biệt là **admin khác tenant**.

### Vì sao ID không tồn tại trả 403 thay vì 404?

Trong bài này, `AuthorizationManager` từ chối ngay khi `DocumentStore` không tìm thấy ID, nên controller chưa được gọi. Cách này có thể giúp hạn chế việc dò tài nguyên qua thông báo lỗi, nhưng không phải mọi sản phẩm đều cần trả 403 cho tài nguyên không tồn tại. Một API có thể thiết kế trả 404 đồng nhất cho “không tồn tại” và “không được phép biết tài nguyên tồn tại”, hoặc trả 403 khi thiếu quyền và 404 khi không tìm thấy, tùy chính sách chống lộ thông tin.

**Không nên quyết định 403/404 bằng cách chuyển mọi lỗi thành `200` với thông báo trong body.** Khi thay đổi chính sách, cần giữ sự thống nhất giữa endpoint và bảo đảm không làm lộ sự tồn tại của tài nguyên giữa các tenant qua status, thời gian phản hồi hoặc nội dung lỗi.

## 6. Quy tắc đánh giá và các sai lầm thường gặp

### 6.1. “Deny by default” và trả quyết định rõ ràng

Chính sách trả `new AuthorizationDecision(false)` ở mọi nhánh không hợp lệ: chưa xác thực, không có tài liệu, không ánh xạ được tenant, sai tenant hoặc thiếu quyền chủ sở hữu/admin. Nó chỉ trả `true` khi tất cả điều kiện bắt buộc đều hợp lệ.

`AuthorizationManager` có thể trả **null** trong một số API/phiên bản khi một manager không đưa ra quyết định (abstain). Không nên dùng `null` như cách diễn đạt “chặn truy cập” trong chính sách nghiệp vụ: việc diễn giải kết quả thiếu quyết định có thể phụ thuộc thành phần phối hợp. Với chính sách quyết định hoàn toàn như bài này, hãy trả **allow hoặc deny** tường minh.

### 6.2. Không tin dữ liệu do client tự khai

Sai:

```java
// MINH HỌA SAI: tenant do caller tự chọn.
String userTenant = request.getHeader("X-Tenant-Id");
boolean allowed = userTenant.equals(document.tenantId());
```

Client có thể tự đặt `X-Tenant-Id` thành tenant khác. Điều kiện tenant trong bài lấy từ ánh xạ gắn với **danh tính đã xác thực**; trong hệ thống thật, ánh xạ này có thể được lấy từ bảng quan hệ thành viên tenant, token claim đã xác minh hoặc cơ chế identity đáng tin khác. Nếu tài khoản thuộc nhiều tenant, cần có **active tenant** được kiểm chứng với danh sách tenant mà tài khoản thực sự được tham gia.

Tương tự, tránh lấy `owner` từ request body làm căn cứ duy nhất cho phép cập nhật tài liệu. Quyền sở hữu phải đến từ bản ghi lưu phía server hoặc nguồn đáng tin.

### 6.3. Không để quyền ADMIN vượt quá phạm vi đã định

Có thể viết nhầm:

```java
// Sai: ROLE_ADMIN thành đặc quyền toàn hệ thống.
return new AuthorizationDecision(
    hasAdminRole || (sameTenant && isOwner)
);
```

Nếu quản trị viên chỉ quản lý một tenant, biểu thức đúng phải là:

```java
return new AuthorizationDecision(
    sameTenant && (hasAdminRole || isOwner)
);
```

Hai đoạn này là ví dụ logic ngắn với biến đã có ý nghĩa; chúng không thay thế code hoàn chỉnh ở mục 4. Quy tắc “admin có vượt tenant không?” phải được xác định ở mô hình quyền ngay từ đầu, không suy từ tên role.

### 6.4. Đừng dùng mỗi xác thực ở tầng URL cho mọi thao tác

Với API **chỉ đọc** trong ví dụ, `AuthorizationManager<RequestAuthorizationContext>` có thể kiểm tra tài liệu qua ID trước khi controller xử lý. Trong ứng dụng thực, khi thêm **PUT/POST/DELETE**, cần đặc biệt lưu ý:

- Quy tắc có thể phụ thuộc dữ liệu thực của hành động: người sở hữu được đọc nhưng không được duyệt, chỉ trưởng nhóm mới được duyệt tài liệu ở trạng thái chờ.
- Đối tượng tài liệu có thể thay đổi sau thời điểm filter kiểm tra (rủi ro **time-of-check/time-of-use**, TOCTOU).
- Các thao tác trong service, background job, message listener hoặc method nội bộ không nhất thiết đi qua đúng URL đã cấu hình.

Đối với thay đổi trạng thái quan trọng, hãy kiểm tra quyền tại **ranh giới nghiệp vụ/service** theo bản ghi và giao dịch phù hợp; có thể dùng **method security** với `@EnableMethodSecurity` và `@PreAuthorize` hoặc `AuthorizationManager<MethodInvocation>`/interceptor phù hợp. Không tự coi một `AuthorizationManager<RequestAuthorizationContext>` cho HTTP request là áp dụng được trực tiếp cho mọi method invocation, vì kiểu bối cảnh khác nhau.

### 6.5. Không trộn xác thực, phân quyền và xử lý lỗi

- **Xác thực** trả lời “đây là ai?”: HTTP Basic, form login, Bearer token, v.v.
- **Phân quyền** trả lời “được phép làm gì trên tài nguyên nào?”: AuthorizationManager.
- **Xử lý phản hồi lỗi** trả lời “trả 401/403 bằng JSON, HTML hay chuyển hướng?”: entry point và access-denied handler.

Nếu muốn API trả Problem Details JSON cho 401/403, hãy cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` tương ứng. Không viết `response.getWriter()` trực tiếp trong `AuthorizationManager` và không đặt HTTP status 403 ngay trong mỗi nhánh của chính sách.

### 6.6. Không giả định mọi 403 đều do manager từ chối

Với phương thức POST/PUT/DELETE trên ứng dụng có CSRF protection, yêu cầu thiếu token có thể bị `CsrfFilter` chặn **trước** controller, ngay cả khi role đúng. Nếu muốn kiểm thử chính sách viết dữ liệu, phải kiểm soát cả cơ chế CSRF tương ứng. Tránh tắt bảo vệ CSRF toàn cục để “cho hết 403”; kể cả HTTP Basic cũng có thể bị trình duyệt tự gửi credentials và cần đánh giá nguy cơ CSRF.

### 6.7. Hiệu năng, lỗi phụ thuộc và kiểm tra lại dữ liệu

Một `AuthorizationManager` có thể gọi database hoặc policy service nhiều lần. Các vấn đề cần xử lý:

- **Chi phí mỗi request**: tránh N+1 query, có chỉ mục theo resource ID và tenant, chỉ lấy các thuộc tính cần phân quyền.
- **Lỗi hệ thống phụ thuộc**: khi policy service không hoạt động, không mặc nhiên cho phép để “ứng dụng không bị gián đoạn”. Thiết kế **fail closed** hoặc cơ chế dự phòng được kiểm chứng.
- **Cache quyền**: nếu sử dụng cache, key phải bao gồm danh tính, tenant, tài nguyên, hành động và phiên bản chính sách khi cần; phải có cơ chế vô hiệu hóa khi quyền hoặc trạng thái tài liệu thay đổi.
- **Audit**: ghi nhận người gọi, hành động, resource ID và kết quả theo nhu cầu hệ thống, nhưng không ghi token, mật khẩu, cookie hoặc dữ liệu bí mật.
- **Đồng bộ dữ liệu**: kiểm tra quyền trên đúng bản ghi và trạng thái tại thời điểm tác động, nhất là khi có giao dịch ghi hoặc thay đổi quyền đồng thời.

## 7. Các cách mở rộng AuthorizationManager

### 7.1. Chọn rule theo URL, method và quyền

Chính sách mẫu dùng:

```java
.requestMatchers(
    HttpMethod.GET,
    "/api/documents/{documentId}"
).access(documentPolicy)
```

Nếu thêm thao tác cập nhật, bạn có thể xây một `AuthorizationManager<RequestAuthorizationContext>` khác cho `PUT`, hoặc làm rõ **action** từ HTTP method rồi đánh giá trong cùng một policy service. Không suy rằng `GET` và `DELETE` có quyền ngang nhau.

Ví dụ khái niệm:

| Hành động | Người có quyền | Điều kiện thêm |
| --- | --- | --- |
| Đọc tài liệu | Chủ sở hữu hoặc tenant admin | Cùng tenant |
| Sửa nội dung | Chủ sở hữu | Cùng tenant, trạng thái còn cho sửa |
| Duyệt tài liệu | Người có authority `DOC_APPROVER` | Cùng tenant, tài liệu đang chờ duyệt |
| Xóa | Tenant admin | Cùng tenant và thỏa quy định giữ dữ liệu |

Đây là **mô hình mở rộng**, chưa được cài trong chương trình GET ở mục 4. Khi triển khai, hãy xác định nguồn sự thật cho role, quyền, trạng thái và hành động.

### 7.2. Tách policy thành dịch vụ kiểm tra dễ kiểm thử

Trong hệ thống lớn, thay vì nhét toàn bộ truy vấn vào manager, có thể đặt logic nghiệp vụ trong một dịch vụ như `DocumentPermissionService`:

```java
// Minh họa chữ ký, không phải một lớp độc lập để biên dịch:
boolean canRead(Authentication auth, String documentId);
boolean canEdit(Authentication auth, String documentId);
```

`AuthorizationManager` trở thành bộ phận kết nối: lấy `Authentication`, lấy `documentId` từ context, gọi `permissionService.canRead(...)` rồi chuyển giá trị boolean thành quyết định. Policy service có thể được kiểm thử với dữ liệu cụ thể mà không cần giả lập đầy đủ Servlet request.

Tuy nhiên, không nên coi method trả về `boolean` là điểm cưỡng chế quyền tự động. **Chỉ nơi đã gắn manager/interceptor hoặc nơi chủ động gọi service và chặn khi false mới thực sự thực thi chính sách.**

### 7.3. Kết hợp điều kiện thay vì dùng một role rất rộng

Spring Security có những `AuthorizationManager` dựng sẵn cho authority, trạng thái xác thực, các điều kiện kết hợp và cơ chế phân quyền theo request/method. Chính sách riêng hữu ích khi có **thuộc tính nghiệp vụ** mà role đơn lẻ không diễn đạt được.

Có thể phối hợp nhiều tầng: kiểm tra `authenticated()` cho một nhóm endpoint, yêu cầu authority cụ thể cho endpoint khác, gắn `access(customManager)` tại URL cần quy tắc chi tiết, rồi gọi kiểm tra nghiệp vụ trong service khi cần. Thứ tự `requestMatchers(...)` quyết định luật nào được chọn: **rule khớp đầu tiên** sẽ được áp dụng, không được xem nhiều rule nối tiếp là phép AND trừ khi bạn chủ động cấu hình phép kết hợp trong manager.

Ví dụ có lỗi:

```java
// KHÔNG có nghĩa "vừa USER vừa thỏa customPolicy".
.requestMatchers("/api/documents/**").hasRole("USER")
.requestMatchers("/api/documents/{documentId}").access(documentPolicy)
```

Vì mẫu `/api/documents/**` có thể khớp trước, rule custom không được xét ở URL đó. Hãy gắn chính sách riêng ở **rule cụ thể trước** hoặc xây một manager thực sự kiểm tra đủ các điều kiện cần thiết. Điều kiện tenant trong chính sách mẫu **không** được thay thế bằng role.

### 7.4. Gọi policy engine ngoài

Với hệ thống nhiều dịch vụ, `AuthorizationManager` cũng có thể làm adapter gọi một policy decision point như một dịch vụ nội bộ hoặc policy engine. Nó gửi đúng danh tính được xác minh, action, resource và các thuộc tính cần thiết rồi chuyển quyết định về allow/deny. Điều này hữu ích khi chính sách được quản trị tập trung, nhưng phải xử lý xác thực giữa dịch vụ, timeout, retry có giới hạn, logging an toàn, cache/invalidation và trường hợp policy engine lỗi.

Không gửi toàn bộ HTTP request chứa credential/token vào một dịch vụ ngoài chỉ để kiểm tra quyền; chỉ truyền các thuộc tính tối thiểu đã xác minh cần thiết theo hợp đồng bảo mật.

## 8. Kiểm thử chính sách theo ma trận quyền

Một phép thử “Alice xem được tài liệu của mình” là chưa đủ. Chính sách cần kiểm tra **cả đường đi được phép và bị từ chối**, đặc biệt những góc dễ lộ dữ liệu giữa tenant.

| Kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Không credentials gọi `doc-a` | 401 (với HTTP Basic đã cấu hình) |
| `alice` gọi `doc-a` | 200 |
| `alice` gọi `doc-b` | 403, cùng tenant nhưng sai chủ |
| `bob` gọi `doc-b` | 200 |
| `admin` gọi `doc-a` và `doc-b` | 200, cùng tenant |
| `admin` gọi `doc-c` | 403, khác tenant |
| `carol` gọi `doc-a` | 403, khác tenant |
| Tài khoản hợp lệ nhưng không có ánh xạ tenant | 403, chính sách deny |
| Tài liệu không tồn tại | Từ chối theo hợp đồng đã chọn; trong ví dụ là 403 |
| POST lên endpoint chỉ cho GET | Không được phép qua chính sách GET; phải đánh giá CSRF và fallback riêng |

Để kiểm thử mức logic, truyền vào manager một `Supplier<Authentication>` và `RequestAuthorizationContext` có request/variables kiểm soát được, sau đó khẳng định `AuthorizationDecision.isGranted()` theo từng trường hợp. Với test tích hợp Servlet, dùng `MockMvc` cùng Spring Security Test hoặc công cụ HTTP thích hợp để xác minh **status thực tế**. Nếu thêm `@PreAuthorize` ở service, kiểm thử riêng lời gọi method và việc xử lý trong transaction.

Một bộ test nên phát hiện ít nhất ba lỗi:

1. **Role bypass tenant**: admin của tenant A xem được tài liệu tenant B.
2. **Đảo điều kiện AND/OR**: người cùng tenant nhưng không phải owner vẫn đọc được chỉ vì đã đăng nhập.
3. **Nhầm anonymous là authenticated**: anonymous được cho qua do chỉ kiểm tra `isAuthenticated()`.

## 9. Checklist khi áp dụng vào dự án thật

1. Viết chính sách bằng ngôn ngữ nghiệp vụ trước: ai, tài nguyên nào, hành động gì, điều kiện và ngoại lệ nào.
2. Xác định nguồn đáng tin cậy của `Authentication`, tenant, owner, role, trạng thái tài liệu; xác định người dùng có thể thuộc nhiều tenant hay không.
3. Chọn điểm cưỡng chế: URL với `AuthorizationManager<RequestAuthorizationContext>`, service với method security, hoặc phối hợp có chủ đích.
4. Chặn mặc định khi thiếu danh tính, không tìm thấy quyền, dữ liệu mơ hồ hoặc policy service không trả được quyết định đáng tin.
5. Gắn policy vào đúng matcher, đúng HTTP method và đúng thứ tự; thử cả request khớp và không khớp.
6. Bảo đảm quyền admin không vượt tenant nếu mô hình không cho phép; dùng authority thực tế thay vì giả định tên role.
7. Với thao tác ghi, kiểm tra lại quyền theo trạng thái hiện tại và giao dịch để tránh TOCTOU.
8. Chuẩn hóa 401/403/404 theo hợp đồng API mà không lộ tài liệu/tenant nhạy cảm.
9. Đưa các trường hợp âm tính, khác tenant, tài khoản bị thu hồi quyền và dữ liệu thay đổi vào test.
10. Theo dõi hiệu năng, audit và lỗi phụ thuộc; kiểm tra phiên bản API `AuthorizationManager` khi nâng Spring Security.

**Cốt lõi:** `AuthorizationManager` là nơi **biến một chính sách nghiệp vụ thành quyết định truy cập**. Chất lượng của chính sách nằm ở việc kiểm tra đúng danh tính, đúng tài nguyên, đúng tenant, đúng hành động và từ chối trong các trường hợp không đủ bằng chứng; việc gắn `.access(...)` chỉ là bước đưa quyết định đó vào pipeline Spring Security.

### Tài liệu chính thức

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.3 — RequestAuthorizationContext API](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
