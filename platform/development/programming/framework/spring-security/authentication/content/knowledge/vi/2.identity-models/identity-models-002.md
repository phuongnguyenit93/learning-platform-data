# Principal và sự khác biệt với tài khoản nghiệp vụ trong cơ sở dữ liệu

Trong Spring Security, **principal** là biểu diễn danh tính của chủ thể đang được xác thực hoặc đã xác thực. **Tài khoản nghiệp vụ trong cơ sở dữ liệu** (business account / account entity) là bản ghi mà ứng dụng sở hữu để lưu định danh bền vững, trạng thái tài khoản, thông tin hồ sơ và các quan hệ nghiệp vụ. Hai khái niệm có liên hệ nhưng không phải cùng một đối tượng, không luôn có ánh xạ một–một và không nên dùng thay thế tùy tiện.

Bài học thuộc nhóm **Mô hình danh tính** của Spring Security Authentication. Sau bài này, bạn cần tự trả lời được: “Spring Security đang coi ai là người gọi request?”, “Lấy ID tài khoản nội bộ ở đâu?”, “Vì sao không trả nguyên entity làm principal?”, “Nếu tên đăng nhập, quyền hoặc trạng thái tài khoản đổi thì điều gì xảy ra với principal đang lưu trong session/JWT?”.

## 1. Hiểu đúng bốn lớp dữ liệu liên quan

| Khái niệm | Bản chất | Ví dụ | Dùng để làm gì? |
|---|---|---|---|
| **Principal** | Đối tượng/định danh biểu diễn chủ thể đang truy cập trong ngữ cảnh bảo mật | `CurrentActor(accountId, loginName)`, `UserDetails`, `Jwt`, `OidcUser` | Nhận diện người gọi để thực thi security và ứng dụng |
| **Authentication** | Đối tượng Spring Security bao lấy principal, thông tin xác thực, trạng thái và authorities | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` | Ghi nhận request đang được xác thực bởi cơ chế nào và có quyền gì |
| **Account entity / database row** | Dữ liệu lâu dài do hệ thống nghiệp vụ quản lý | `Account(id, email, passwordHash, status, ...)` | Quản lý hồ sơ, credential, trạng thái, quan hệ dữ liệu, lịch sử thay đổi |
| **Profile / response DTO** | Dữ liệu được phép hiển thị cho người dùng hoặc API client | `MyProfileDto(id, displayName, avatarUrl)` | Trả dữ liệu phù hợp mà không lộ thông tin nội bộ |

**Principal không đồng nghĩa với mật khẩu**, cũng không nhất thiết là tên đăng nhập, row của bảng `users`, hoặc user profile trả cho frontend. Principal xác định **ai đang gọi**, còn account entity là một phần mô hình lưu trữ lâu dài mà hệ thống có thể dùng để xác minh, liên kết và quản trị danh tính đó.

Ví dụ: nhân viên được gán `account_id = 9c...` trong bảng `accounts`, đăng nhập bằng email `linh@company.example`. Sau xác thực, Spring Security có thể giữ principal chỉ chứa `accountId`, `loginName` và vài thuộc tính tối thiểu. Email có thể thay đổi; khóa chính `account_id` dùng làm tham chiếu dữ liệu vẫn giữ nguyên. Nếu nhân viên đổi tên hiển thị trong database, principal cũ trong session có thể vẫn có tên cũ cho đến khi được làm mới.

## 2. Principal nằm ở đâu trong Spring Security?

Trong ứng dụng Servlet, Spring Security thường lưu `Authentication` của request trong `SecurityContext`. Có thể truy cập qua `SecurityContextHolder` hoặc được Spring MVC cung cấp trực tiếp cho controller:

~~~text
HTTP request
  -> SecurityFilterChain
  -> Đọc và kiểm tra credential/cookie/bearer token (tùy phương thức)
  -> Authentication đã xác thực
       |- principal: chủ thể vừa được nhận diện
       |- authorities: tập quyền gắn với lần xác thực
       |- credentials: bằng chứng; thường được xóa/không giữ sau xác thực
       '- authenticated: trạng thái của authentication token
  -> SecurityContext của request
  -> Authorization: kiểm tra quyền đối với hành động/tài nguyên
  -> Controller / Service
~~~

`Authentication` thuộc `org.springframework.security.core.Authentication` và có những phương thức quan trọng:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication.getPrincipal();
String name = authentication.getName();
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
boolean authenticated = authentication.isAuthenticated();
~~~

Đoạn trên minh họa API, **không phải chương trình Java chạy độc lập**: cần có `Authentication` trong context và imports tương ứng. Trong ứng dụng thực, nên để Spring đưa principal hoặc authentication vào controller khi có thể; không tự truy cập context ở mọi tầng chỉ vì tiện.

### 2.1. `Authentication.getPrincipal()` trả về kiểu gì?

Không có một kiểu Java duy nhất cho mọi cơ chế xác thực:

| Cơ chế hoặc cấu hình | Principal thường gặp | Cần lưu ý |
|---|---|---|
| Username/password với `DaoAuthenticationProvider` | Đối tượng triển khai `UserDetails`, ví dụ `org.springframework.security.core.userdetails.User` hoặc kiểu custom | Có thể mang username, flags và authorities từ thời điểm load |
| Principal do ứng dụng tự tạo | `CurrentActor`, một record/class chỉ có thuộc tính an toàn | Dễ mang ID tài khoản nội bộ ổn định |
| Resource server xác thực JWT | `Jwt` trong `JwtAuthenticationToken` theo mặc định | Claims lấy từ token đã xác minh; thay đổi database không tự sửa JWT |
| OAuth2 Login / OIDC | `OAuth2User` hoặc `OidcUser` | Thông tin đến từ identity provider; cần liên kết về account nội bộ |
| Xác thực người dùng chưa hoàn thành / anonymous | Có thể là chuỗi, token chưa xác thực hoặc `AnonymousAuthenticationToken` | Không ép kiểu principal trước khi kiểm tra ngữ cảnh hợp lệ |

Với `UsernamePasswordAuthenticationToken`, principal đôi khi có thể là `String`, đặc biệt trong một số cách tự dựng token; **không** mặc định ép kiểu mọi principal sang `UserDetails` hay `AccountEntity`.

### 2.2. `getName()` có phải account ID không?

Không mặc định. `Authentication.getName()` thường lấy tên từ principal theo quy ước của token/provider: với username/password thường là username, với JWT thường là claim `sub` (có thể cấu hình tên claim), và với custom principal là giá trị `getName()` mà ứng dụng định nghĩa. Nó **không mặc nhiên** là primary key của bảng tài khoản nội bộ.

Nếu dùng email/username làm khóa ngoại của đơn hàng, log audit hoặc điều kiện sở hữu, việc đổi email/username có thể phá liên kết. Thiết kế phổ biến là dùng ID nội bộ **ổn định**, ví dụ `UUID accountId`, cho quan hệ nghiệp vụ; giữ email/login name là thuộc tính có thể thay đổi.

### 2.3. Principal khác authorities

Principal nhận diện chủ thể; `GrantedAuthority` mô tả quyền/role gắn với authentication. Chúng có thể thay đổi độc lập. Hai người cùng role `ROLE_USER` vẫn là hai principal khác nhau; một người đổi role không đổi thành người khác. Với session hoặc JWT, authorities có thể là **snapshot** từ lúc đăng nhập/phát token. Nếu cần thu hồi quyền ngay, phải có cơ chế cập nhật, kiểm tra hiện trạng hoặc giới hạn hạn dùng.

## 3. Tài khoản nghiệp vụ trong database là gì?

Một ứng dụng có thể có bảng dữ liệu tương tự:

~~~sql
CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    login_name VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(320) UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    password_hash VARCHAR(255),
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Đây là **sơ đồ minh họa**, không phải schema bắt buộc hoặc DDL dùng nguyên xi cho mọi RDBMS. Thực tế còn có version/lock, unique theo tenant, auditing, liên kết với nhà cung cấp danh tính và chính sách xóa dữ liệu.

- `id`: định danh nội bộ ổn định, làm khóa ngoại cho dữ liệu nghiệp vụ.
- `login_name` / `email`: các thuộc tính để đăng nhập hoặc liên hệ, có thể thay đổi và phải có quy trình xác minh thích hợp.
- `password_hash`: credential lưu an toàn khi hệ thống tự xử lý mật khẩu; có thể vắng mặt nếu chỉ đăng nhập liên kết qua IdP.
- `status`: trạng thái quản lý tài khoản như active, suspended, pending verification; quy tắc cụ thể do miền nghiệp vụ định nghĩa.
- `created_at` và dữ liệu audit: giúp truy vết, quản trị, tuân thủ quy định áp dụng.

Ngoài account, hệ thống có thể có các bảng `person_profiles`, `memberships`, `roles`, `external_identities` hoặc `service_accounts`. Không phải mọi principal có một người dùng con người tương ứng: machine-to-machine token có thể nhận diện dịch vụ; anonymous request không có tài khoản; một người có thể sở hữu nhiều tài khoản theo tenant; một tài khoản nội bộ có thể liên kết nhiều phương thức đăng nhập.

**Vì sao không dùng account entity làm principal?**

1. **Giảm lộ dữ liệu:** Entity có thể chứa password hash, email, số điện thoại, trạng thái riêng, metadata nội bộ. Principal đi qua nhiều lớp ứng dụng; `toString()`, debug log, serialization hoặc lỗi trả dữ liệu có thể làm lộ nội dung không cần thiết.
2. **Giảm phụ thuộc ORM:** Entity JPA có proxy lazy-loading, quan hệ object graph và transaction/persistence context. Giữ nguyên trong session có thể dẫn tới lỗi lazy loading, dữ liệu cũ hoặc ràng buộc serialize khi deploy.
3. **Tách tuổi thọ:** Account row sống qua nhiều lần đăng nhập; principal của một lần xác thực/request có thể là snapshot hữu hạn.
4. **Ổn định contract:** Thay schema DB không bắt buộc thay kiểu security principal hoặc API client.
5. **Hỗ trợ nhiều nguồn danh tính:** Principal từ JWT/OIDC có thể chưa tương ứng ngay với row nội bộ; phải qua bước liên kết hoặc cấp quyền tạo account có kiểm soát.

Điều này **không cấm** triển khai `UserDetails` dựa trên dữ liệu account; quan trọng là chỉ đưa vào security context những thuộc tính cần thiết, tránh đưa thẳng thực thể persistence giàu dữ liệu và quan hệ vào session.

## 4. Ánh xạ principal ↔ account trong các mô hình xác thực

### 4.1. Username/password nội bộ

~~~text
Login name + password
   -> UserDetailsService / AuthenticationProvider
   -> Tra account theo login name trong repository
   -> Kiểm tra password hash và trạng thái được phép login
   -> Tạo Authentication đã xác thực
        principal = CurrentActor(accountId, loginName, ...)
   -> Controller nhận accountId và truy vấn nghiệp vụ theo ID
~~~

`UserDetailsService` có hợp đồng `loadUserByUsername(String)`, thường dùng bởi `DaoAuthenticationProvider` để tải `UserDetails` cho xác thực mật khẩu. Nó không phải service quản lý mọi thao tác nghiệp vụ của account. `UserDetails` là **security projection** hoặc adapter của dữ liệu lưu trữ: framework cần tên, password hash, authorities và một số cờ trạng thái; domain service vẫn có trách nhiệm tạo, cập nhật, xác minh và đóng tài khoản.

Khi muốn principal chỉ gồm ID và thuộc tính an toàn, có thể dùng custom provider/token như ví dụ runnable ở mục 6, hoặc tạo custom `UserDetails` thiết kế cẩn thận và loại bỏ credential khỏi kết quả xác thực.

### 4.2. JWT resource server

~~~text
Authorization: Bearer <JWT>
   -> Giải mã và kiểm tra chữ ký, issuer, audience, thời hạn, ...
   -> Tạo JwtAuthenticationToken (principal thường là Jwt)
   -> Đọc subject/scope đã được kiểm tra
   -> Ánh xạ (issuer, subject) -> accountId nội bộ nếu nghiệp vụ cần
   -> Áp dụng chính sách quyền và trạng thái hiện tại theo yêu cầu
~~~

`sub` chỉ có ý nghĩa trong phạm vi nguồn phát hành; nếu chấp nhận nhiều identity provider, dùng cặp **(issuer, subject)** làm khóa ánh xạ thường an toàn hơn chỉ dùng `sub`. Không lấy email trên JWT làm khóa duy nhất nếu IdP không bảo đảm sự ổn định và xác minh email. Không tạo tài khoản tự động chỉ vì bất kỳ JWT hợp lệ nào đưa ra một email.

JWT có thể chứa `account_id` nếu do một bên phát hành đáng tin cậy và có hợp đồng rõ ràng, nhưng backend vẫn phải xác thực token đầy đủ. Nếu JWT do bên ngoài phát hành không biết ID nội bộ, account mapping là trách nhiệm của ứng dụng.

### 4.3. OAuth2 Login / OIDC

Khi dùng OIDC Login, người dùng có thể đăng nhập ở IdP và ứng dụng nhận `OidcUser` với các claims từ ID token/UserInfo theo giao thức. Mô hình dữ liệu thường là:

~~~text
identity_provider + external_subject
               |
               v
         external_identities
               |
             account_id
               |
               v
           accounts
               |
         domain relations
       (orders, projects, ...)
~~~

Một account nội bộ có thể liên kết nhiều identity như mật khẩu nội bộ và tài khoản công ty, hoặc nhiều IdP; hệ thống phải có quy trình **link/unlink** an toàn, ngăn chiếm tài khoản bằng email trùng tên, xác thực lại khi thay đổi liên kết nhạy cảm và giới hạn quyền tạo liên kết. Claim `sub` của OIDC nhận diện chủ thể theo issuer; claim `email` là một thuộc tính, không phải khóa liên kết toàn cục mặc định.

### 4.4. Multi-tenant và service account

Trong ứng dụng đa tổ chức, đôi khi không đủ chỉ có `accountId`: cùng một người có thể là thành viên ở nhiều tenant với quyền khác nhau. Hãy phân biệt identity toàn cục (account/user id), membership (account id + tenant id) và quyền trong tenant. Tenant do client gửi chỉ là yêu cầu phạm vi, phải được kiểm tra với membership thật; không tin một query parameter `tenantId` để lấy quyền.

Với machine-to-machine, principal có thể là `service-client-42` hoặc `ClientPrincipal`, không có dòng trong bảng `accounts` của người dùng. Vì vậy, code bảo mật không nên ép mọi principal thành `HumanUserEntity`.

## 5. Quy tắc thiết kế: lưu ít trong principal, truy vấn đúng trong domain

Một principal ứng dụng dạng immutable Java record:

~~~java
package example.identity;

import java.security.Principal;
import java.util.UUID;

public record CurrentActor(UUID accountId,
                           String loginName,
                           String displayName)
        implements Principal {

    @Override
    public String getName() {
        return loginName;
    }
}
~~~

Đây là **một lớp biên dịch độc lập** nếu lưu đúng đường dẫn `example/identity/CurrentActor.java` và biên dịch với Java 17+. Nó chỉ là kiểu dữ liệu/contract, chưa tự tạo authentication. Ví dụ đã chủ động không chứa password hash, địa chỉ hay entity JPA. `accountId` dùng cho quan hệ nội bộ, `getName()` dùng tên có thể hiển thị/đọc theo convention của `Principal`.

Trong controller:

~~~java
@GetMapping("/me")
MyProfileDto me(@AuthenticationPrincipal CurrentActor actor) {
    return profileService.loadByAccountId(actor.accountId());
}
~~~

Đây là **đoạn tích hợp minh họa**, giả định đã có `MyProfileDto`, `profileService` và annotation Spring MVC tương ứng; **không phải một chương trình đầy đủ**. `@AuthenticationPrincipal` lấy `Authentication.getPrincipal()` từ security context và hỗ trợ kiểu principal đã được tạo bởi cơ chế xác thực. Nếu authentication là JWT mặc định thì không thể tự động nhận `CurrentActor` bằng cách đổi kiểu tham số: cần cơ chế chuyển đổi/mapping thích hợp.

Tại lớp domain:

- Sử dụng `actor.accountId()` đã được server thiết lập từ một lần xác thực hợp lệ làm cơ sở định danh.
- Nạp account hiện tại từ repository khi nghiệp vụ cần status, profile mới nhất hoặc quyền hiện thời.
- Kiểm tra ownership/tenant trên **tài nguyên thực**, không chỉ dựa vào việc principal có một ID.
- Trả DTO tối thiểu; không trả nguyên `AccountEntity` hoặc `Authentication` vào API nếu không có chủ đích rõ.
- Với dịch vụ nền hoặc tác vụ async, truyền actor/identity cần thiết qua một context rõ ràng; `SecurityContextHolder` trên Servlet mặc định sử dụng `ThreadLocal` và không bảo đảm tự xuất hiện trên thread khác.

## 6. Ví dụ chạy được với Spring Boot 3.3 / Java 17+

Ta xây dựng API nhỏ để thấy rõ:

1. Kho `AccountStore` **mô phỏng** bảng accounts bằng bộ nhớ; mỗi row có ID, login name, display name, password hash, enabled.
2. Provider kiểm tra mật khẩu và account enabled. Khi hợp lệ, provider tạo principal sạch `CurrentActor`.
3. Controller `/me` đọc principal; `/me/live` dùng account ID của principal tra lại row như một dịch vụ nghiệp vụ.
4. Một account bị vô hiệu hóa vẫn tồn tại trong store, nhưng xác thực đăng nhập mới bị từ chối. Đây là bằng chứng cho thấy tồn tại database row không đồng nghĩa có principal hợp lệ.

### 6.1. Cấu trúc dự án và dependencies

~~~text
identity-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/identity/IdentityDemoApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'identity-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
}
~~~

Ví dụ cần JDK 17+, Gradle tương thích với Spring Boot 3.3.x và kết nối tải dependencies khi chạy lần đầu. Không cần database/JPA vì account repository ở đây chỉ là mô phỏng. Ứng dụng thật sẽ thay `AccountStore` bằng persistence/repository và policy tương ứng.

### 6.2. Mã Java đầy đủ

Tạo file `src/main/java/example/identity/IdentityDemoApplication.java`:

~~~java
package example.identity;

import java.security.Principal;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class IdentityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityDemoApplication.class, args);
    }
}

// Một row nghiệp vụ mô phỏng bảng accounts. Không đưa record này
// vào SecurityContext và không trả trực tiếp qua HTTP.
record AccountRow(UUID id, String loginName, String displayName,
                  String passwordHash, boolean enabled) {}

// Principal gọn, không mang password hash hoặc quan hệ JPA.
record CurrentActor(UUID accountId, String loginName,
                    String displayName) implements Principal {
    @Override
    public String getName() {
        return loginName;
    }
}

// Bản demo bộ nhớ; ứng dụng thật dùng repository có ràng buộc và giao dịch.
class AccountStore {
    private final Map<String, AccountRow> byLoginName;

    AccountStore(PasswordEncoder encoder) {
        byLoginName = Map.of(
            "linh", new AccountRow(
                UUID.fromString("00000000-0000-0000-0000-000000000001"),
                "linh", "Linh", encoder.encode("demo-pass"), true),
            "khoa", new AccountRow(
                UUID.fromString("00000000-0000-0000-0000-000000000002"),
                "khoa", "Khoa", encoder.encode("demo-pass"), false)
        );
    }

    Optional<AccountRow> findByLoginName(String loginName) {
        return Optional.ofNullable(byLoginName.get(loginName));
    }

    Optional<AccountRow> findById(UUID id) {
        return byLoginName.values().stream()
                .filter(account -> account.id().equals(id))
                .findFirst();
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder);
    }

    @Bean
    AuthenticationProvider accountAuthenticationProvider(
            AccountStore store, PasswordEncoder encoder) {
        return new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request)
                    throws AuthenticationException {
                AccountRow row = store.findByLoginName(request.getName())
                        .orElseThrow(() ->
                            new BadCredentialsException("Invalid credentials"));

                String password = String.valueOf(request.getCredentials());
                if (!encoder.matches(password, row.passwordHash())) {
                    throw new BadCredentialsException("Invalid credentials");
                }
                if (!row.enabled()) {
                    throw new DisabledException("Account disabled");
                }

                CurrentActor actor = new CurrentActor(
                        row.id(), row.loginName(), row.displayName());
                Collection<? extends GrantedAuthority> authorities =
                        List.of(new SimpleGrantedAuthority("profile:read"));

                return UsernamePasswordAuthenticationToken.authenticated(
                        actor, null, authorities);
            }

            @Override
            public boolean supports(Class<?> authenticationType) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(authenticationType);
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationProvider provider)
            throws Exception {
        return http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityController {
    private final AccountStore store;

    IdentityController(AccountStore store) {
        this.store = store;
    }

    @GetMapping("/public/info")
    String publicInfo() {
        return "PUBLIC";
    }

    @GetMapping("/me")
    Map<String, Object> me(@AuthenticationPrincipal CurrentActor actor) {
        return Map.of(
            "accountId", actor.accountId().toString(),
            "loginName", actor.loginName(),
            "displayName", actor.displayName()
        );
    }

    @GetMapping("/me/live")
    Map<String, Object> meFromAccount(
            @AuthenticationPrincipal CurrentActor actor) {
        // Dùng stable accountId do provider đã xác thực,
        // không lấy accountId do client tự khai báo.
        AccountRow account = store.findById(actor.accountId())
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        return Map.of(
            "accountId", account.id().toString(),
            "loginName", account.loginName(),
            "displayName", account.displayName(),
            "enabled", account.enabled()
        );
    }
}
~~~

**Đọc code theo ranh giới:**

- `AccountRow` chứa dữ liệu persistence, kể cả hash mật khẩu và enabled. Nó không triển khai `Principal`, không phải DTO để trả ra mạng.
- `AccountStore` tra account từ login name khi **xác thực**, sau đó cho phép truy vấn theo UUID khi **nghiệp vụ** cần. Trong hệ thống thật, truy vấn theo ID nên có index/primary key, không scan `values()` như demo.
- `AuthenticationProvider` nhận yêu cầu chưa xác thực, lấy row và kiểm tra password với BCrypt; nó từ chối login của `khoa` vì disabled. Đây là logic xác thực minh họa, không phải quy trình quản lý trạng thái account đầy đủ.
- Sau khi kiểm tra, provider tạo `CurrentActor` chỉ gồm UUID và trường an toàn; token thành công lưu principal đó và authority `profile:read`. Raw password không được chép vào principal mới; credentials của token trả về là `null`.
- `@AuthenticationPrincipal CurrentActor actor` chỉ hoạt động vì provider của ứng dụng thực sự tạo `CurrentActor`. Nếu đổi sang OAuth2/JWT, phải thay bước ánh xạ principal đúng theo provider tương ứng.
- `/me` trả giá trị từ **snapshot trong principal**; `/me/live` trả dữ liệu được nạp lại từ **account store**. Kết quả trùng nhau trong demo nhưng có thể khác sau khi database được cập nhật.
- `provider` là bean được đăng ký tường minh qua `http.authenticationProvider(provider)`. HTTP Basic chỉ để trình bày request/response, không phải lựa chọn mặc định cho app production.

### 6.3. Chạy và quan sát

Tại thư mục `identity-demo`, nếu đã tạo Gradle Wrapper tương thích:

~~~bash
./gradlew bootRun
~~~

Nếu chưa có wrapper, có thể dùng lệnh `gradle bootRun` với Gradle đã cài tương thích, hoặc tạo wrapper trước. Spring Boot mặc định nghe cổng 8080 khi không có cấu hình cổng khác.

Trong terminal Bash khác:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/public/info

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:wrong-password http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u khoa:demo-pass http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:demo-pass http://localhost:8080/me

curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:demo-pass http://localhost:8080/me/live
~~~

Các mã HTTP mong đợi theo thứ tự:

~~~text
200
401
401
401
200
200
~~~

Đọc JSON để kiểm tra ID principal của `linh`:

~~~bash
curl -s -u linh:demo-pass http://localhost:8080/me
~~~

JSON mong đợi có các trường/giá trị sau (thứ tự khóa có thể khác):

~~~json
{
  "accountId": "00000000-0000-0000-0000-000000000001",
  "loginName": "linh",
  "displayName": "Linh"
}
~~~

Lúc này database row vẫn có thể chứa `passwordHash` và cờ `enabled`; `/me` không tiết lộ chúng. Nếu gọi `/me/live`, JSON còn có `"enabled": true` từ account store theo ID nội bộ. Request của `khoa` bị 401 mặc dù row tài khoản của Khoa vẫn tồn tại.

**Giới hạn cố ý của demo:** dữ liệu in-memory và password mẫu; HTTP Basic không có màn hình login hoặc session người dùng theo kiểu browser; không có endpoint cập nhật account, audit, MFA, role/ownership hay token revocation. Không dùng `demo-pass` qua HTTP không mã hóa trên mạng thật; chỉ dùng localhost cho mục đích học. Nếu thêm API ghi có cookie/session, phải xem lại CSRF và các bảo vệ khác theo mô hình xác thực sử dụng.

## 7. Khác biệt giữa dữ liệu hiện thời và snapshot trong principal

Một điểm thường bị bỏ qua: principal không phải một kết nối “live” đến bảng account.

| Sự kiện | Bản ghi database | Principal/session/token đã có | Điều hệ thống phải quyết định |
|---|---|---|---|
| Đổi email/login name | Giá trị mới | Có thể giữ tên cũ | Khi nào cập nhật principal; dùng ID bền vững cho khóa ngoại |
| Đổi tên hiển thị | Profile mới | Có thể hiển thị tên cũ | API nào nạp profile mới, API nào chấp nhận snapshot |
| Thu hồi role | Bảng quyền thay đổi | Authorities có thể còn quyền cũ | Thu hồi/refresh session/token hoặc kiểm tra quyền hiện tại |
| Khóa tài khoản | `enabled=false` hoặc `status=SUSPENDED` | Session/JWT cũ có thể vẫn hợp lệ | Cơ chế chặn request đang dùng credential cũ |
| Xóa/đóng tài khoản | Row có thể bị xóa, soft-delete hoặc ẩn danh | ID cũ có thể còn trong session/log | Chặn truy cập, xử lý dữ liệu mồ côi, audit và lưu giữ |

### 7.1. Session server-side

Nếu dùng session, `SecurityContext` có thể được lưu và phục hồi qua các request theo cấu hình. Không nên mặc định mỗi request đều gọi lại `UserDetailsService` hoặc query account. Cần thiết kế cập nhật/thu hồi session hoặc kiểm tra trạng thái khi nghiệp vụ yêu cầu phản ứng tức thời.

Nếu session được serialize (ví dụ session phân tán), principal cần tương thích với cơ chế serialize và nâng cấp phiên bản của ứng dụng. Nhét nguyên JPA entity, lazy associations hoặc dữ liệu nhạy cảm vào session thường làm tăng chi phí và rủi ro.

### 7.2. JWT tự chứa

Một JWT hợp lệ về chữ ký/thời hạn thường được kiểm tra mà không tự động truy vấn database account ở mỗi request. Nếu role hoặc trạng thái account đổi giữa chừng, JWT cũ không tự cập nhật. Các phương án gồm access token ngắn hạn, thu hồi/denylist, token introspection, security version, hoặc lookup account/permission hiện thời tùy yêu cầu; mỗi phương án có chi phí và độ trễ.

### 7.3. Không coi `isAuthenticated()` là bảo đảm người thật

Spring Security có thể gán `AnonymousAuthenticationToken` cho một request chưa đăng nhập; một số token anonymous vẫn có `isAuthenticated() == true` theo trạng thái token. Phân biệt anonymous với authenticated user bằng chính sách `authenticated()` và security components phù hợp, không chỉ viết `authentication != null && authentication.isAuthenticated()` rồi suy ra có account thật. Nếu app bắt buộc có local account, kiểm tra mapping account riêng.

## 8. An toàn dữ liệu và ranh giới tin cậy

**Điểm tin cậy nằm tại server sau xác thực.** Những giá trị frontend tự truyền như `userId`, `role` hoặc `email` không phải principal chỉ vì trùng với bản ghi trong DB.

Các nguyên tắc thực hành:

1. Không cho client chọn `accountId` dùng để chứng minh “tôi là ai” khi thao tác cho chính mình. Lấy ID từ principal đã được xác thực; với thao tác thay mặt người khác phải kiểm tra quyền rõ ràng.
2. Không dùng `@RequestParam("userId")` hoặc JSON body `{"ownerId": "..."}` để thay cho identity. Chúng có thể là **đối tượng bị yêu cầu tác động**, vẫn cần kiểm tra authorization.
3. Tránh lưu/serialize password, password hash, raw access/refresh token, secret và dữ liệu riêng tư không cần thiết trong principal. Giảm nội dung `toString()` và log; nếu custom `UserDetails` buộc mang password hash trong bước xác thực, cần chính sách xóa credential phù hợp và cẩn thận với cache.
4. Không dùng email làm khóa liên kết IdP vô điều kiện. Cặp `(issuer, subject)` phải được xác minh từ token hợp lệ; quy trình liên kết account có ràng buộc unique và chống account takeover.
5. Không dựa hoàn toàn vào authorities trong principal để truy cập tài nguyên: kiểm tra ownership, tenant, trạng thái object và nguyên tắc least privilege tại server.
6. Không nhúng trực tiếp entity có quan hệ JPA vào `SecurityContext` hoặc API response. Dùng security projection và DTO riêng; kiểm soát dữ liệu cũ trong cache/session.
7. Tránh gọi `SecurityContextHolder` trực tiếp trong mọi domain service. Có thể chuyển `accountId`/`CurrentActor` qua tham số hoặc một facade bảo mật để test đơn giản hơn; đừng mang nguyên security framework vào mọi entity.

## 9. Những lỗi điển hình và cách sửa

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| `(AccountEntity) auth.getPrincipal()` với mọi provider | `ClassCastException` hoặc phụ thuộc sâu vào JPA | Xác định kiểu principal thực, dùng custom projection hoặc mapping adapter |
| Lưu `email` làm foreign key cho đơn hàng | Đổi email phá tham chiếu hoặc chính sách ownership | Dùng stable internal account ID |
| Trả `AccountEntity` trực tiếp từ `/me` | Có thể lộ hash/trạng thái riêng và kéo theo lazy associations | Chỉ trả DTO cho phép |
| Cho frontend gửi `currentUserId` để lấy dữ liệu “của tôi” | Nguy cơ truy cập account của người khác (IDOR) | Lấy subject từ security context và kiểm tra quyền đối tượng |
| Chỉ xét `ROLE_USER` mà không xét tenant | Có thể đọc dữ liệu tenant khác | Kiểm tra membership và ràng buộc tenant tại truy vấn |
| Cho rằng sửa DB role/status thay đổi JWT cũ | Quyền bị thu hồi chậm hoặc sai cam kết | Quy định rõ hạn token, refresh/revocation, lookup hiện tại |
| Dùng `sub` không kèm issuer qua nhiều IdP | Va chạm định danh bên ngoài | Unique theo `(issuer, subject)`, ánh xạ có kiểm soát sang account ID |
| Đọc `SecurityContextHolder` trong async thread và thấy null | Thiếu security context ở luồng khác | Truyền identity tường minh hoặc cơ chế propagation phù hợp |
| Lấy email từ login để tự tạo account không kiểm chứng | Gộp nhầm danh tính/chiếm tài khoản | Xác minh token, email_verified nếu liên quan, link flow bảo mật và chính sách cấp account |

## 10. Tình huống thiết kế và bộ câu hỏi tự kiểm tra

**Tình huống A – Nhân viên đổi email.** Hệ thống có 10.000 đơn hàng trỏ về người tạo. Sau đổi email, quan hệ nghiệp vụ có còn nguyên vẹn? Nếu các bảng dùng `accountId` làm khóa ngoại, có. Nếu dùng email làm định danh lưu trữ, phải xử lý migration/phụ thuộc phức tạp hơn. Đây là lý do phân biệt principal name có thể đổi với account ID ổn định.

**Tình huống B – Người dùng đăng nhập OIDC.** IdP trả ID token có `iss`, `sub`, `email`. Muốn tìm hồ sơ và quyền nội bộ, hệ thống phải kiểm tra token bằng thư viện/giao thức phù hợp, lấy định danh provider, tra bảng `external_identities` để tìm `accountId`. Không lấy email tùy ý làm bằng chứng rằng đây là một account nội bộ đã tồn tại.

**Tình huống C – JWT còn hạn sau khi khóa tài khoản.** Account row đã chuyển sang `SUSPENDED` nhưng API chấp nhận JWT đã cấp. Đâu là sự thật? Cả hai dữ kiện có thể đồng thời đúng: JWT vẫn hợp lệ theo bộ kiểm tra token, database đã đổi. Thiết kế phải định nghĩa cách thực thi khóa theo thời gian thực hoặc trong một khoảng trễ được chấp nhận.

**Tình huống D – Service bot không có user row.** Token `client_credentials` đại diện cho một service. Một controller ép kiểu principal sang `UserDetails` của người sẽ bị lỗi. Nên có phân loại actor và chính sách riêng cho service identity.

### Câu hỏi ôn tập

1. **`Authentication` và `principal` khác nhau thế nào?**  
   `Authentication` là đối tượng bảo mật của framework chứa principal, authorities, credentials/trạng thái; principal chỉ là biểu diễn chủ thể.
2. **Nếu `authentication.getName()` trả `linh@example.com`, có thể dùng ngay làm khóa chính nội bộ?**  
   Không. Nó là tên theo contract của provider/token, có thể thay đổi; ID nội bộ phải được ánh xạ và xác minh.
3. **`UserDetailsService` có trách nhiệm tạo account và reset mật khẩu không?**  
   Theo hợp đồng xác thực, nó dùng để load `UserDetails` theo username; quy trình tạo/đổi/khôi phục account thuộc dịch vụ nghiệp vụ riêng.
4. **Vì sao `/me` và `/me/live` có thể cho tên hiển thị khác nhau?**  
   Principal có thể là snapshot từ thời điểm xác thực; `/me/live` truy vấn account hiện tại.
5. **Khóa account ở DB có tự xóa session và mọi JWT không?**  
   Không. Cần chiến lược thu hồi/kiểm tra trạng thái phù hợp.
6. **Có thể có principal mà không có row `accounts` của con người không?**  
   Có: service account, anonymous, external identity chưa được liên kết, hoặc các dạng actor khác.
7. **API cập nhật đơn hàng có nên lấy owner ID từ request body để quyết định quyền?**  
   Không tin body làm danh tính; xác định actor từ authentication và kiểm tra ownership/tenant của đơn hàng trong domain.

## 11. Checklist áp dụng trong dự án

- Xác định rõ **principal type** cho từng phương thức authentication; API/controller không ép kiểu mù.
- Chọn khóa **accountId nội bộ bất biến** cho dữ liệu nghiệp vụ; thiết kế mapping với external identity có issuer + subject và ràng buộc unique.
- Giữ principal tối thiểu, tránh JPA entity/credential/secret; dùng DTO cho response.
- Thiết kế rõ dữ liệu nào là **snapshot** trong principal/token và dữ liệu nào phải **read live** từ account/permission store.
- Mỗi thao tác nhạy cảm lấy principal từ security context đã xác minh, sau đó kiểm tra quyền trên tài nguyên/tenant tại server.
- Test account bị disabled, đổi quyền trong session, JWT cũ, đổi email, nhiều IdP, service principal và request anonymous.
- Kiểm thử độ nhất quán giữa việc thay đổi trạng thái account với cơ chế thu hồi session/token; không dựa vào giả định tự động cập nhật.

**Ghi nhớ:** **Principal là “ai đang gọi request theo kết quả xác thực?”; account entity là “bản ghi nào hệ thống quản lý lâu dài?”**. Liên kết hai phía bằng định danh bền vững và quy tắc tin cậy rõ ràng. Tách security identity khỏi persistence giúp xử lý đúng đăng nhập, đổi hồ sơ, phân quyền, đa nhà cung cấp danh tính và thu hồi quyền truy cập.

### Tài liệu chính thức để tra cứu

- Spring Security – [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `SecurityContext`, `Authentication`, principal và authorities.
- Spring Security – [UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): hợp đồng load dữ liệu xác thực bằng username/password.
- Spring Security – [Spring MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): truyền principal vào controller bằng `@AuthenticationPrincipal`.
