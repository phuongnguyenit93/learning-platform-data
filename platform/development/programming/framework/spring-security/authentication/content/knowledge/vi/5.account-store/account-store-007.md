# Đa tổ chức: tìm đúng tài khoản trong phạm vi tenant

Trong một hệ thống nhiều tổ chức (*multi-tenant*), cùng chuỗi `username` hoặc email có thể đại diện cho **những tài khoản khác nhau**. Ví dụ `sam` của tổ chức `acme` và `sam` của tổ chức `boreal` là hai chủ thể riêng, có mật khẩu, trạng thái, quyền và dữ liệu riêng. Nếu bộ máy xác thực chỉ tìm `WHERE username = 'sam'`, ứng dụng có thể lấy sai account, xác thực sai nguồn danh tính, áp dụng nhầm quyền hoặc tạo đường đi truy cập chéo tenant.

Bài học này giải quyết vấn đề **“làm thế nào tìm đúng account trong kho tài khoản theo tenant, rồi ràng buộc tenant đã được xác thực tới các request tiếp theo?”** trong Spring Security. Trọng tâm không phải chỉ thêm cột `tenant_id` vào bảng. Cần xác định tenant nào là *gợi ý để tra cứu trước xác thực*, tenant nào là *định danh đã kiểm chứng*, và mọi câu truy vấn/authorization phía sau có duy trì ranh giới đó hay không.

> Quy tắc nền tảng: **Khóa tra cứu account phải có namespace tenant phù hợp; mật khẩu phải được kiểm với đúng account đã chọn; sau khi xác thực, chỉ dùng tenant/account đã ràng buộc trong principal đáng tin để kiểm quyền và truy vấn tài nguyên.** Tenant ID, subdomain, header hoặc claim chưa kiểm chứng tự thân không cấp quyền.

Nội dung nằm trong nhóm **Kho tài khoản** của *Spring Security - authentication*. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x và H2 để minh họa một thiết kế đăng nhập username/password với khóa login dạng `tenant|username`. Các chiến lược OAuth2/OIDC/JWT được phân biệt rõ nhưng không đánh đồng với luồng password.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **tenant**, **membership**, **account ID**, **login identifier**, **principal**, **issuer** và **authority**.
2. Giải thích vì sao `findByUsername(username)` không an toàn khi username chỉ duy nhất *trong mỗi tenant*; thiết kế composite key, index, unique constraint và query parameter.
3. Tách ba thời điểm: **chọn tenant ứng viên → xác minh credential thuộc account đó → ràng buộc tenant đã xác thực trong principal**.
4. Xây `UserDetailsService` nạp account bằng `(tenant_id, login_name)` và tránh dùng `ThreadLocal`/header tùy ý làm ngữ cảnh tin cậy.
5. Tạo principal chứa account ID ổn định và tenant ID; dùng chúng để lọc tài nguyên và chống *cross-tenant IDOR/BOLA*.
6. Nhận diện nguy cơ từ cache key, chuẩn hóa username, đồng bộ role, đa datasource và issuer JWT.
7. Chạy một ví dụ Spring Boot với cùng username `sam` ở hai tenant và kiểm đủ ca đăng nhập đúng, sai tenant, truy cập tài nguyên chéo và thiếu quyền.

## 2. Khái niệm: một chuỗi đăng nhập không nhất thiết là một danh tính

| Thuật ngữ | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Tenant** | Đơn vị cô lập danh tính/quyền/dữ liệu theo hợp đồng ứng dụng: tổ chức, workspace hoặc khách hàng. | `acme`, `boreal`. |
| **Login identifier** | Giá trị người dùng cung cấp để tìm account trong một namespace. | `sam`, email công việc. |
| **Account** | Một bản ghi định danh có trạng thái, credential verifier và ID ổn định. | Account `101` của Acme, account `202` của Boreal. |
| **Membership** | Quan hệ chủ thể tham gia tenant và quyền tương ứng; có thể là một user có nhiều tenant. | User toàn cục #7 là member của Acme với `READER`, Boreal với `AUDITOR`. |
| **Qualified login key** | Khóa login chỉ rõ namespace + login identifier, dùng trong một chiến lược xác thực cụ thể. | `acme|sam`, `boreal|sam`. |
| **Principal đã xác thực** | Bản định danh do provider xác minh và gắn vào `Authentication`. | `accountId=101, tenantId=acme`. |
| **Authority/role** | Quyền đã được cấp trong phạm vi được xác định. | `orders:read` của Acme. |
| **Issuer (`iss`)** | Bên phát hành token trong OIDC/OAuth2; không đồng nghĩa tenant ID ứng dụng. | `https://idp.example.test/acme`. |

**Hai mô hình dữ liệu cần phân biệt:**

- **Account theo tenant:** cùng người có thể có nhiều account độc lập; primary key có thể là `account_id` toàn cục, unique key là `(tenant_id, login_name)`. Credential và trạng thái có thể khác nhau.
- **Identity toàn cục + membership theo tenant:** chỉ có một identity/user toàn cục, nhưng quyền và vai trò thay đổi theo `tenant_id`. Khi login, ứng dụng có thể xác thực identity toàn cục trước, rồi kiểm membership để chọn tenant hiện hành. Không chọn nhầm membership chỉ vì client tự gửi tenant ID.

Không có một mô hình thích hợp cho mọi hệ thống. **Đề bài “tìm đúng tài khoản trong phạm vi tenant”** yêu cầu xác định chính xác namespace nơi account được tạo và kiểm chứng. Nếu database bảo đảm username unique toàn cục, câu SQL có thể đơn giản hơn; tuy nhiên quyền và tài nguyên vẫn cần tenant scope.

### Ví dụ về lỗi nhập nhằng

```text
Tenant ACME                          Tenant BOREAL
  username: sam                       username: sam
  accountId: 101                      accountId: 202
  passwordHash: hash(A)               passwordHash: hash(B)
  enabled: true                       enabled: true
  roles: READER                       roles: AUDITOR

Sai:   SELECT * FROM accounts WHERE login_name = 'sam'
Đúng: SELECT * FROM accounts
      WHERE tenant_id = :tenant AND login_name = :login
```

Với câu truy vấn sai, kết quả có thể tùy thứ tự record/mapper, hoặc phát sinh lỗi nhiều kết quả. Cả hai đều cho thấy **mô hình tra cứu không đủ xác định danh tính**. Không sửa bằng `LIMIT 1` vì đó chỉ giấu lỗi và khiến lựa chọn account trở nên ngẫu nhiên.

## 3. Ba ranh giới tin cậy của tenant trong xác thực

Trong mô hình login username/password theo tenant, cần phân biệt:

1. **Tenant ứng viên (*candidate tenant*):** giá trị dùng để tìm miền kiểm chứng. Nó có thể được gửi cùng username qua form, URL/subdomain hoặc qualified login key. Ở thời điểm này, **client chưa được xác thực**; giá trị chỉ có thể là đầu vào được kiểm tra định dạng, allowlist và định tuyến hợp lệ.
2. **Tenant được ràng buộc khi xác thực (*authenticated tenant*):** sau khi chọn đúng account bằng composite key và xác minh password/status, provider trả principal có `tenantId` và `accountId` từ bản ghi đáng tin. **Đây là dữ liệu server đã kiểm**.
3. **Tenant dùng cho authorization/data access (*effective tenant*):** với request tiếp theo, service dùng tenant đã xác thực và membership/quyền đã kiểm để giới hạn truy vấn. Nếu user muốn chuyển tổ chức, phải kiểm membership/chuyển ngữ cảnh theo cơ chế tin cậy; không chỉ tin `X-Tenant: other`.

```text
Trước khi authentication
    Client: tenantHint + loginName + password
                      |
                      v
    Validate cú pháp/namespace của tenantHint
    Chọn verifier/user store được cho phép
                      |
                      v
    Query: WHERE tenant_id=? AND login_name=?
                      |
                      v
    AccountRecord từ DB + passwordHash + enabled
                      |
                      v
    PasswordEncoder.matches(password, passwordHash)
                      |
               (thành công?)
                 /         \
               Không        Có
               |           |
            401 chung       v
                      TenantPrincipal:
                       tenantId từ DB
                       accountId từ DB
                       authorities đã được cấp
                             |
                             v
                       SecurityContext
                             |
                             v
                  API/service lấy tenant từ
                  principal, không từ header
                             |
                             v
                  WHERE tenant_id=? AND ...
```

**Tenant hint có thể do client chọn, nhưng không được coi là bằng chứng sở hữu tenant đó.** Một người có thể thử `acme|sam` và `boreal|sam`. Hệ thống phải kiểm **password của account đúng tenant đã chọn**, không chấp nhận password của `acme|sam` rồi tự đổi principal thành `boreal|sam`.

### 3.1 Những nguồn tenant thường gặp và mức tin cậy

| Nguồn | Có thể dùng để làm gì? | Chưa đủ để làm gì? |
| --- | --- | --- |
| Subdomain `acme.example.test` | Xác định ứng viên tenant và branding/routing nếu domain được kiểm soát chặt. | Chứng minh người dùng đã là thành viên Acme. |
| Đường dẫn `/t/acme/login` | Nhận ứng viên tenant trước login. | Cấp quyền Acme sau login mà không kiểm account/membership. |
| Form field `tenantId=acme` | Chọn account trong namespace, có validation. | Tự quyết định principal tenant hoặc authority. |
| Header `X-Tenant: acme` | Gợi ý lựa chọn tenant cho client đáng tin, có thể được kiểm tra. | Làm nguồn quyền cho request bất kỳ từ Internet. |
| `Authentication` đã xác thực | Nguồn ràng buộc `tenantId`, `accountId` và authorities ở tầng ứng dụng. | Cho phép bỏ kiểm object-level authorization. |
| JWT `iss`/tenant claim đã kiểm | Chỉ dẫn issuer/tenant theo hợp đồng đã được trust và signature/audience validation. | Tin mọi `iss`/`tenant` tự khai trong payload chưa verify. |

Ở proxy, `Host`/`X-Forwarded-Host` chỉ có thể là đầu vào định tuyến đáng tin nếu ingress chuẩn hóa và xác thực đường đi; không cho attacker giả mạo forwarded header để vượt chọn tenant. Nếu dùng tenant hint như khóa định tuyến giữa nhiều IdP, **chỉ chọn issuer từ tập tin cậy/tenant registry**, không tự tải cấu hình từ mọi URL do client đưa vào.

## 4. Thiết kế khóa account và ràng buộc database

### 4.1 Khóa primary và unique nên phục vụ các câu hỏi khác nhau

Một schema đơn giản:

```sql
CREATE TABLE tenant_accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    login_name VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,

    CONSTRAINT uq_tenant_login UNIQUE (tenant_id, login_name),
    CONSTRAINT uq_tenant_account UNIQUE (tenant_id, account_id)
);

CREATE TABLE account_authorities (
    tenant_id VARCHAR(32) NOT NULL,
    account_id BIGINT NOT NULL,
    authority VARCHAR(96) NOT NULL,

    CONSTRAINT pk_tenant_authority
        PRIMARY KEY (tenant_id, account_id, authority),
    CONSTRAINT fk_tenant_authority
        FOREIGN KEY (tenant_id, account_id)
        REFERENCES tenant_accounts(tenant_id, account_id)
);

CREATE TABLE tenant_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_account_id BIGINT NOT NULL,
    title VARCHAR(160) NOT NULL,

    CONSTRAINT fk_tenant_order_owner
        FOREIGN KEY (tenant_id, owner_account_id)
        REFERENCES tenant_accounts(tenant_id, account_id)
);
```

Ví dụ này dùng `account_id` **duy nhất toàn hệ thống**. Nếu ID chỉ duy nhất trong từng tenant, primary key phải điều chỉnh, ví dụ `PRIMARY KEY(tenant_id, account_id)`, và mọi FK phải dùng khóa phù hợp. Không giả định mọi ID số đều toàn cục.

**Ý nghĩa của từng ràng buộc:**

- `UNIQUE(tenant_id, login_name)` cho phép `sam` xuất hiện ở hai tenant nhưng không trùng trong cùng một tenant. Đây là bảo đảm database ngay cả khi có hai request tạo account đồng thời.
- `UNIQUE(tenant_id, account_id)` cho phép FK ghép bảo vệ quan hệ tenant/account, tránh chèn authority hay order có `tenant_id` khác với tenant của owner.
- `account_authorities` giữ quyền trong **namespace tenant**, không chỉ lưu `username` mà dễ trùng giữa tổ chức.
- `tenant_orders` giữ cả `tenant_id` và `owner_account_id`, cho phép query kiểm đồng thời tenant và chủ sở hữu; unique/FK giúp bảo vệ bất biến dữ liệu.
- `enabled` là account flag cơ bản. Khóa tài khoản có thời hạn, MFA, account expiry, membership status có thể cần các cột và check riêng; không tự xuất hiện chỉ vì dùng `UserDetails`.

### 4.2 Một câu SQL tìm account phải có đủ tenant

```sql
-- Đúng: prepared statement với cả hai tham số
SELECT account_id, tenant_id, login_name, password_hash, enabled
FROM tenant_accounts
WHERE tenant_id = ? AND login_name = ?;
```

Hai dấu `?` phải được JDBC bind bằng **tenant candidate đã qua validation** và **login identifier**. Không nối input trực tiếp thành SQL. Chính việc `WHERE tenant_id = ?` mới là ranh giới dữ liệu quan trọng, không phải chỉ kiểm tenant ở controller sau khi đã load nhầm account.

Tương tự, lấy authorities bằng account ID **và tenant ID**:

```sql
SELECT authority
FROM account_authorities
WHERE tenant_id = ? AND account_id = ?
ORDER BY authority;
```

Nếu implementation chỉ lọc `WHERE account_id=?` và ID không duy nhất toàn cục hoặc record bị ánh xạ sai, kết quả có thể trộn quyền. Cả hai tham số phải lấy từ **account vừa được truy vấn/kiểm chứng**.

### 4.3 Index, collation và canonicalization

Unique constraint không tự giải quyết mọi lỗi của username:

- `sam` và `Sam` có được coi là cùng login không? Phụ thuộc chính sách và collation DB; xác định một quy tắc canonicalize và dùng nhất quán ở đăng ký/login.
- Email có thể đổi; nếu dùng email làm login key, account ID vẫn phải ổn định. Không dùng email hiển thị làm primary key cho mọi quan hệ nghiệp vụ.
- Unicode normalization, khoảng trắng và ký tự giống nhau dễ bị lợi dụng; hãy quy định rõ danh sách ký tự/normalization trước khi lookup và khi tạo account. Không tự động lowercase mọi tên có ý nghĩa phân biệt chữ hoa nếu policy không cho phép.
- Trong hệ thống có nhiều tenant với naming khác nhau, dùng stable tenant ID đã đăng ký, không lấy tên công ty tự do làm khóa nội bộ.
- Index `(tenant_id, login_name)` phục vụ login lookup; index quan hệ quyền và dữ liệu cũng cần giữ `tenant_id` theo query thực tế.

**Không dùng `SELECT ... WHERE login_name=? LIMIT 1`**, không dùng fallback `tenant_id IS NULL` để “thử user chung” trừ khi có ranh giới thiết kế rất rõ và được kiểm thử. Fallback tài khoản chung có thể là lối đi vòng tenant.

## 5. Đưa tenant vào UserDetailsService: chiến lược nào hợp lý?

`UserDetailsService` tiêu chuẩn chỉ có:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Nó **không nhận riêng tham số `tenantId`**. Do đó nếu login key chưa duy nhất toàn hệ thống, cần một cách chuyển/định tuyến rõ trước khi loader lookup. Các chiến lược phổ biến:

| Chiến lược | Cơ chế | Điều cần chú ý |
| --- | --- | --- |
| **Qualified login key** | Username truyền tới loader là `tenant|username`; loader parse, validate rồi query `(tenant, username)`. | Dễ dùng với `DaoAuthenticationProvider`, nhưng phải định nghĩa delimiter/canonicalization an toàn, không coi chuỗi trước login là principal đã xác thực. |
| **Custom authentication token + provider** | Filter tạo `TenantUsernamePasswordAuthenticationToken` chứa candidate tenant, username, credential; provider nạp account theo composite key. | Kiểm thật credential/status, trả principal trusted; bổ sung filter, handler, context lifecycle đúng cách. |
| **AuthenticationManagerResolver** | Chọn manager/provider theo tenant/issuer được cho phép; mỗi manager dùng kho tài khoản riêng. | Nguồn lựa chọn cần allowlist/trust; tránh open redirect/SSRF hoặc manager tự cấu hình theo issuer tùy ý. |
| **Global identity + membership** | Xác thực identity toàn cục, sau đó kiểm membership và chọn tenant hiện hành bằng nguồn server. | Quyền phải scoped theo membership; chuyển tenant phải được kiểm membership; user không nhất thiết nhập tenant trong password login. |
| **SAML/OIDC identity federation** | Nhận token/assertion từ IdP đáng tin, ánh xạ subject/issuer đến account/membership trong tenant. | Phải verify token/assertion và issuer/audience, không chỉ tin claim `email` có thể trùng. |

Bài thực hành chọn **qualified login key `tenant|username`** vì tương thích với provider username/password tiêu chuẩn mà không cần viết lại authentication filter. Đây là **một phương án có hợp đồng rõ**, không phải yêu cầu toàn bộ hệ thống multi-tenant phải dùng ký tự `|`.

### 5.1 Quy tắc định dạng qualified key

- Tenant ID trong demo: regex `[a-z0-9-]{1,32}`; login name: `[a-z0-9._-]{1,64}`. Ký tự `|` không nằm trong hai tập này nên parse không nhập nhằng.
- Chuỗi `acme|sam` phân tách thành đúng **hai thành phần**; từ chối `acme|sam|other` hoặc thành phần trống.
- Ở production, không tự nhận dạng tenant bằng substring “đến dấu chấm đầu tiên” trong email hoặc domain; cần quy tắc đăng ký và domain verification rõ.
- Trả lỗi authentication chung khi login key sai/người dùng không tồn tại, hạn chế account enumeration; lưu audit an toàn theo policy.
- Nếu login key cần cho các service khác, hãy truyền một **structured principal** (tenantId, accountId), không bắt mọi service parse lại chuỗi.

**Ví dụ tính toán đơn giản:** Input `boreal|sam` → query `tenant_id='boreal' AND login_name='sam'` → nếu password đúng với account Boreal, principal chứa `tenantId='boreal', accountId=202`. Khi request đòi `/api/orders/1001` (order Acme), service query theo `tenantId='boreal'` và **không thấy** order Acme.

## 6. Ví dụ Spring Boot: hai tenant cùng username, không lẫn tài khoản

Ứng dụng demo dùng **Java 17+ / Spring Boot 3.3.13 / Spring Security 6.x**, H2 in-memory, `JdbcTemplate`, `UserDetailsService` và HTTP Basic. Hai account:

| Tenant | Local username | Account ID | Password demo | Authorities |
| --- | --- | --- | --- | --- |
| `acme` | `sam` | `101` | `acme-password` | `orders:read` |
| `boreal` | `sam` | `202` | `boreal-password` | `orders:read`, `reports:read` |

Hai account **cùng login name `sam` nhưng khác password và phạm vi quyền**. Khi gửi HTTP Basic, username đầy đủ là `acme|sam` hoặc `boreal|sam`. Loader kiểm composite key rồi trả `TenantPrincipal` (subclass của `UserDetails` chuẩn) chứa tenant/account xác minh từ DB.

### 6.1 Cấu trúc dự án

```text
tenant-lookup-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/TenantLookupApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

File `settings.gradle`:

```groovy
rootProject.name = 'tenant-lookup-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Phiên bản được ghim cho tính tái lập của ví dụ học tập, **không phải đề xuất dùng một nhánh đã hết hạn hỗ trợ khi xây hệ thống production mới**. Trong dự án thật, chọn nhánh Spring Boot/Spring Security đang được hỗ trợ và kiểm compatibility theo tài liệu tương ứng.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:tenantlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.sql.init.continue-on-error=false
```

H2 ở đây chỉ nằm trong process để học và biến mất khi ứng dụng dừng; user DB `sa` không có password là **chỉ cho môi trường demo cục bộ**. Không dùng cấu hình này để triển khai production hoặc mở H2 console công khai.

File `src/main/resources/schema.sql` là DDL đầy đủ ở mục 4.1, giữ nguyên ba bảng cùng constraints. Nếu copy qua database khác, cần điều chỉnh dialect/migration. Đặc biệt không được xóa unique `(tenant_id, login_name)` hoặc FK tenant/account để chạy “cho dễ”.

### 6.2 Mã Java hoàn chỉnh

File `src/main/java/demo/TenantLookupApplication.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TenantLookupApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantLookupApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    private record AccountRecord(
            long accountId,
            String tenantId,
            String loginName,
            String passwordHash,
            boolean enabled) {
    }

    @Bean
    UserDetailsService userDetailsService(JdbcTemplate jdbc) {
        return qualifiedLogin -> {
            // Chỉ parse tenant ứng viên; chưa coi request là authenticated.
            String[] parts = qualifiedLogin.split("\\|", -1);
            if (parts.length != 2
                    || !parts[0].matches("[a-z0-9-]{1,32}")
                    || !parts[1].matches("[a-z0-9._-]{1,64}")) {
                throw new UsernameNotFoundException("Invalid login");
            }

            AccountRecord account;
            try {
                account = jdbc.queryForObject("""
                        SELECT account_id, tenant_id, login_name,
                               password_hash, enabled
                        FROM tenant_accounts
                        WHERE tenant_id = ? AND login_name = ?
                        """,
                        (rs, rowNum) -> new AccountRecord(
                                rs.getLong("account_id"),
                                rs.getString("tenant_id"),
                                rs.getString("login_name"),
                                rs.getString("password_hash"),
                                rs.getBoolean("enabled")),
                        parts[0], parts[1]);
            } catch (EmptyResultDataAccessException ex) {
                throw new UsernameNotFoundException("Invalid login", ex);
            }

            // Scope authority bằng tenant + account do DB trả về.
            List<GrantedAuthority> authorities = jdbc.query("""
                    SELECT authority
                    FROM account_authorities
                    WHERE tenant_id = ? AND account_id = ?
                    ORDER BY authority
                    """,
                    (rs, rowNum) -> new SimpleGrantedAuthority(
                            rs.getString("authority")),
                    account.tenantId(), account.accountId());

            if (authorities.isEmpty()) {
                throw new UsernameNotFoundException("No assigned authorities");
            }

            // Chỉ account từ DB mới quyết định tenant, accountId và quyền.
            return new TenantPrincipal(
                    qualifiedLogin,
                    account.passwordHash(),
                    account.enabled(),
                    authorities,
                    account.accountId(),
                    account.tenantId(),
                    account.loginName());
        };
    }

    static final class TenantPrincipal extends User {
        private static final long serialVersionUID = 1L;

        private final long accountId;
        private final String tenantId;
        private final String localUsername;

        TenantPrincipal(
                String qualifiedUsername,
                String encodedPassword,
                boolean enabled,
                Collection<? extends GrantedAuthority> authorities,
                long accountId,
                String tenantId,
                String localUsername) {
            super(qualifiedUsername, encodedPassword,
                    enabled, true, true, true, authorities);
            this.accountId = accountId;
            this.tenantId = tenantId;
            this.localUsername = localUsername;
        }

        public long getAccountId() {
            return accountId;
        }

        public String getTenantId() {
            return tenantId;
        }

        public String getLocalUsername() {
            return localUsername;
        }
    }

    @Bean
    ApplicationRunner seedDemo(
            JdbcTemplate jdbc,
            PasswordEncoder encoder) {

        return args -> {
            jdbc.update("""
                    INSERT INTO tenant_accounts
                    (account_id, tenant_id, login_name, password_hash, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    101L, "acme", "sam",
                    encoder.encode("acme-password"), true);

            jdbc.update("""
                    INSERT INTO tenant_accounts
                    (account_id, tenant_id, login_name, password_hash, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    202L, "boreal", "sam",
                    encoder.encode("boreal-password"), true);

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "acme", 101L, "orders:read");

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "boreal", 202L, "orders:read");

            jdbc.update("""
                    INSERT INTO account_authorities
                    (tenant_id, account_id, authority)
                    VALUES (?, ?, ?)
                    """, "boreal", 202L, "reports:read");

            jdbc.update("""
                    INSERT INTO tenant_orders
                    (order_id, tenant_id, owner_account_id, title)
                    VALUES (?, ?, ?, ?)
                    """, 1001L, "acme", 101L, "acme-order");

            jdbc.update("""
                    INSERT INTO tenant_orders
                    (order_id, tenant_id, owner_account_id, title)
                    VALUES (?, ?, ?, ?)
                    """, 2001L, "boreal", 202L, "boreal-order");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/*")
                    .hasAuthority("orders:read")
                .requestMatchers("/api/reports")
                    .hasAuthority("reports:read")
                .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class TenantDemoController {

    private final JdbcTemplate jdbc;

    TenantDemoController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal) {

        return Map.of(
                "tenantId", principal.getTenantId(),
                "accountId", principal.getAccountId(),
                "username", principal.getLocalUsername(),
                "authorities", principal.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/orders/{orderId}")
    ResponseEntity<String> order(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal,
            @PathVariable long orderId) {

        List<String> titles = jdbc.query("""
                SELECT title
                FROM tenant_orders
                WHERE order_id = ?
                  AND tenant_id = ?
                  AND owner_account_id = ?
                """,
                (rs, rowNum) -> rs.getString("title"),
                orderId,
                principal.getTenantId(),
                principal.getAccountId());

        if (titles.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(titles.get(0));
    }

    @GetMapping("/api/reports")
    String reports(
            @AuthenticationPrincipal
            TenantLookupApplication.TenantPrincipal principal) {

        return "reports-for-" + principal.getTenantId();
    }
}
```

Các điểm an toàn trong mã:

- `UserDetailsService` parse candidate từ qualified login, kiểm format rồi truy vấn `WHERE tenant_id = ? AND login_name = ?`; không có fallback global user.
- Bản ghi DB trả về chứa `tenant_id`/`account_id` authoritative. Principal giữ **ID từ DB**, không dùng phần tự khai của client để truy vấn tài nguyên.
- `PasswordEncoder` tạo hash cho từng account lúc seed. `DaoAuthenticationProvider` xác minh password của **account được query đúng tenant**, không thể dùng `acme-password` để đăng nhập `boreal|sam`.
- `TenantPrincipal` mở rộng `User` của Spring Security, vốn có `getPassword()` và `CredentialsContainer`. Instance được tải mới từ DB, không tái dùng hash object đã bị erase trong cache.
- Authorities được lấy từ `account_authorities` với cả tenant và account ID. Không có authority cấp từ body/header.
- `/api/orders/{orderId}` kiểm **tenant + account owner + order ID** trong query; chỉ biết `orderId` không đủ để truy xuất order của người khác.
- `/api/reports` yêu cầu `reports:read`; tenant Acme không được xem reports của Boreal dù cả hai có username `sam`.
- API chỉ trả metadata danh tính cho client đã xác thực; không trả raw password, password hash, JDBC secrets hay đối tượng `UserDetails` đầy đủ.

### 6.3 Chạy

Tạo các file theo cấu trúc mục 6.1 và `schema.sql` ở mục 4.1. Nếu project có Gradle wrapper, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có Gradle wrapper nhưng đã cài Gradle tương thích, chạy `gradle bootRun`. Ứng dụng cần thư viện Spring; vì vậy **không thể chạy một lệnh `javac TenantLookupApplication.java` đơn lẻ**. JDK 17 trở lên là điều kiện của bản demo; cần truy cập Maven Central lúc giải dependency lần đầu.

Mở terminal khác, dùng `curl`; trên PowerShell có thể phải gọi `curl.exe`. Các lệnh dưới chỉ dùng password minh họa cho H2 local (HTTP localhost), không sử dụng plaintext HTTP với credential thật:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/me
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/me

curl -i -u 'acme|sam:boreal-password' http://localhost:8080/api/me
curl -i -u 'boreal|sam:acme-password' http://localhost:8080/api/me

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/orders/1001
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/orders/1001

curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/orders/2001
curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/orders/2001

curl -i -u 'acme|sam:acme-password' http://localhost:8080/api/reports
curl -i -u 'boreal|sam:boreal-password' http://localhost:8080/api/reports
```

Kết quả kỳ vọng, chỉ tính trạng thái và body chính thay vì header container có thể thay đổi:

| Case | Kỳ vọng | Giải thích |
| --- | --- | --- |
| `GET /public` | `200`, body `public` | Endpoint công khai. |
| `GET /api/me` không credential | `401` | Chưa xác thực. |
| `acme|sam` + `acme-password` | `200`, tenant `acme`, accountId `101` | Đúng account, đúng password. |
| `boreal|sam` + `boreal-password` | `200`, tenant `boreal`, accountId `202` | Cùng local username nhưng subject khác. |
| `acme|sam` + `boreal-password` | `401` | Password của Boreal không thể login vào Acme. |
| `boreal|sam` + `acme-password` | `401` | Password của Acme không thể login vào Boreal. |
| Acme gọi order `1001` | `200`, body `acme-order` | Đúng tenant và owner. |
| Boreal gọi order `1001` | `404` | Order Acme không hiện ra trong truy vấn tenant Boreal. |
| Boreal gọi order `2001` | `200`, body `boreal-order` | Đúng tenant Boreal. |
| Acme gọi order `2001` | `404` | Không rò order khác tenant. |
| Acme gọi `/api/reports` | `403` | Có authentication nhưng thiếu `reports:read`. |
| Boreal gọi `/api/reports` | `200`, body `reports-for-boreal` | Có authority phù hợp. |

Ví dụ response `GET /api/me` cho Acme có nội dung tương đương:

```json
{
  "tenantId": "acme",
  "accountId": 101,
  "username": "sam",
  "authorities": ["orders:read"]
}
```

Response Boreal có `tenantId="boreal"`, `accountId=202` và authorities gồm `orders:read` cùng `reports:read`. Thứ tự thuộc tính JSON không được đảm bảo; hãy kiểm giá trị sau parse thay vì so từng byte.

### 6.4 Vì sao ví dụ không dựa vào X-Tenant header?

Nếu client đã đăng nhập với `acme|sam` và gửi `X-Tenant: boreal` ở request sau, controller **không đọc** header đó để đổi identity. Tenant trong principal vẫn là `acme` vì đã được server kiểm và ràng buộc khi login. Việc muốn switch active tenant trong một hệ thống có membership cần một workflow riêng xác minh user thực sự có membership Boreal rồi tạo/đổi effective context đáng tin.

Dữ liệu orders cũng không dùng `WHERE order_id=?` đơn thuần rồi kiểm tenant sau khi đã tải dữ liệu nhạy cảm; query lọc cả tenant và owner **ngay tại điểm truy cập**. Nếu application có admin đọc order của nhiều user cùng tenant, có thể thay predicate owner bằng authorization theo role/action nhưng **tenant boundary vẫn phải được giữ**.

## 7. So sánh cách làm sai và đúng

### 7.1 Chỉ lọc username rồi gán tenant từ request

```java
// SAI: ví dụ anti-pattern, không phải class độc lập.
Account account = repository.findByUsername(username);

// Sai tiếp: tin tenant của client và coi account đã login là thuộc tenant đó.
String tenant = request.getHeader("X-Tenant");
TenantPrincipal principal = makeTrustedPrincipal(
        account, tenant, account.getAuthorities());
```

Lỗi có hai tầng: lookup thiếu tenant, sau đó kết quả bị đổi namespace dựa trên dữ liệu chưa xác thực.

**Đúng:** query `findByTenantIdAndLoginName(tenantCandidate, loginName)`; provider kiểm password và status của account được trả về; kết quả có `principal.tenantId = account.tenantId` lấy từ nguồn tin cậy. Header/route không bao giờ tự cấp authority.

### 7.2 Lấy đúng account nhưng nạp role từ tenant khác

```sql
-- SAI nếu username trùng giữa tenant:
SELECT authority
FROM account_authorities_by_username
WHERE username = ?;

-- ĐÚNG khi quyền được gắn theo composite identity:
SELECT authority
FROM account_authorities
WHERE tenant_id = ? AND account_id = ?;
```

Account lookup và authority lookup phải dùng cùng ranh giới. Nếu chỉ lookup password đúng tenant nhưng load quyền bằng username không scoped, user có thể nhận quyền của người trùng tên ở tenant khác.

### 7.3 Chỉ kiểm tenant trong controller, không trong service/SQL

```java
// SAI: lấy object bằng ID trên toàn bộ DB trước khi xác định scope.
Order order = orderRepository.findById(orderId).orElseThrow();

// Nếu dữ liệu đã qua logger/cache/serializer, kiểm sau là quá muộn.
if (!order.getTenantId().equals(principal.getTenantId())) {
    throw new AccessDeniedException("Forbidden");
}
```

Có trường hợp dùng object-level policy sau load là cần thiết, nhưng không nên thay thế việc **scoping truy vấn ngay khi truy xuất** cho dữ liệu cần cô lập. Với Spring Data/JPA, ưu tiên `findByIdAndTenantId(...)` hoặc specification/query có tenant predicate; nếu cần owner, thêm `ownerAccountId`. Lưu ý JPQL/SQL projection, joins và lazy loading cũng phải không kéo dữ liệu tenant khác vô ý.

### 7.4 Dùng loginName làm cache key toàn cục

```text
SAI: cache["sam"] = Account(acme, #101)
     tiếp theo boreal|sam lấy nhầm bản ghi Acme.

ĐÚNG: cache[(tenantId, canonicalLogin)] = AccountInTenant(...)
      hoặc cache[globallyUniqueAccountId] = ...
```

Cache key phải trùng namespace của nguồn dữ liệu. Khi account disabled, đổi password, đổi role hoặc chuyển tenant, cần invalidate đúng key và phiên/token đã phát theo policy; TTL không tự bảo đảm thu hồi tức thì.

### 7.5 Lấy global JWT subject và bỏ qua issuer/tenant

Một `sub` như `sam` hoặc `123` không mặc nhiên duy nhất trên nhiều IdP. Với JWT/OIDC, định danh bền vững thường phải gắn **issuer + subject** hoặc mapping đã xác thực từ trusted IdP tới account nội bộ, rồi kiểm membership tenant. Không dùng `sub` đơn lẻ làm khóa toàn cục khi có nhiều issuer có thể trùng subject.

## 8. Spring Security multi-tenancy với OAuth2/JWT: khác luồng password ở đâu?

Spring Security Resource Server có hỗ trợ **nhiều chiến lược kiểm bearer token** và cho phép dùng `AuthenticationManagerResolver` chọn manager tại request-time. Với JWT từ nhiều issuer, tài liệu Spring Security hướng dẫn resolver từ **trusted issuers**, không tạo decoder cho arbitrary issuer do attacker gửi.

Cần hai bước độc lập:

1. **Resolve tenant/issuer để chọn verifier** từ registry được tin cậy và hợp đồng cố định.
2. **Validate token**: chữ ký, issuer, audience, hạn (`exp`/`nbf`) và claims phù hợp; sau đó ánh xạ verified identity tới tenant/membership được phép.

Đừng nhầm “đã đọc được `iss` trong JWT” là “đã xác minh issuer”. Payload có thể decode mà chưa kiểm chữ ký. Resolver có thể nhìn claim để chọn verifier nhưng **chỉ chọn từ allowlist của issuers**; sau đó decoder/provider phải kiểm thực sự và reject token không hợp lệ. Nếu cho mọi URL từ token làm issuer, hệ thống dễ gặp giả mạo hoặc SSRF/metadata fetching tùy cấu hình.

Ví dụ cấu hình **minh họa** cho Spring Security 6.x với hai issuer cố định, không phải ứng dụng độc lập:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://login.example.test/issuer-acme",
                "https://login.example.test/issuer-boreal");

http
    .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(resolver));
```

Để dùng đoạn này cần `spring-boot-starter-oauth2-resource-server`, issuer thực tế có metadata/keys hợp lệ, cấu hình validation/audience/claims và mapping account/tenant tương ứng. Phần trên không phải một dòng “bật multi-tenancy là xong”; không thể đưa domain minh họa vào production.

**Định danh cho federation:** `(issuer, subject)` giúp tìm external identity đã verified; một bảng mapping có thể ghi `issuer`, `subject`, `tenant_id`, `account_id`. Nếu có một external identity thuộc nhiều tenant, membership/policy quyết định tenant hiện hành, không phải sự tồn tại của JWT tự cấp mọi quyền ở mọi tenant.

### 8.1 Khi JWT có tenant claim

- Chỉ dùng claim sau chữ ký/issuer/audience validation đầy đủ.
- Quy định issuer nào được phép cấp tenant claim nào; không phải JWT hợp lệ từ issuer X có quyền tự gắn `tenant_id=Y` nếu hợp đồng không cho.
- Nếu role/scope gắn tenant, phải map/validate theo namespace; không dùng global `ROLE_ADMIN` cho mọi tenant nếu thực tế quyền chỉ thuộc một tổ chức.
- Nếu URL/header yêu cầu tenant A nhưng token đã verified gắn tenant B, **reject hoặc kiểm membership/switch workflow được ủy quyền**, không âm thầm đổi effective tenant.
- Một token bị thu hồi hoặc user rời tenant không tự vô hiệu mọi access token tự chứa ngay lập tức nếu hệ thống không có freshness/revocation policy; thiết kế TTL và revalidation phù hợp.

### 8.2 Khi một user thuộc nhiều tổ chức

Trong mô hình *global identity + memberships*:

```text
identity: user_global_id = 7, issuer = trusted-idp
membership:
  (tenant=acme, user=7, role=READER)
  (tenant=boreal, user=7, role=EDITOR)
```

Sau khi xác thực global identity, client có thể gửi yêu cầu chọn `boreal` như một **selection request**; server phải query membership `WHERE user_id=7 AND tenant_id='boreal' AND active=true`. Nếu thành công, effective principal/context mang tenant Boreal với authorities trong membership Boreal; nếu không, từ chối. Việc “được login” không tự mang tất cả role của mọi tenant vào một global permission bag.

## 9. Nhiều datasource hoặc nhiều schema: scoping phải tới tận connection

Có kiến trúc *shared database/shared schema* như demo, nhưng cũng có:

| Mô hình lưu trữ | Lợi thế | Rủi ro/cách bảo vệ |
| --- | --- | --- |
| Shared DB, shared tables có `tenant_id` | Vận hành/migration tập trung. | Mọi query và join phải scoped, unique/index composite; có thể dùng RLS như lớp bảo vệ bổ sung. |
| Shared DB, schema riêng mỗi tenant | Cô lập cấu trúc và truy vấn theo schema. | Schema selection từ dữ liệu đã kiểm, reset connection pool state, migration theo tất cả schema. |
| Database riêng mỗi tenant | Cô lập tài nguyên/sự cố tốt hơn trong một số mô hình. | Tenant → DataSource mapping phải có allowlist/registry, quản lý kết nối, secrets và routing đúng trust boundary. |
| Identity provider riêng mỗi tenant | Domain trust/sso có thể theo tổ chức. | Issuer/certificate/JWKS validation và mapping subject/tenant, không dynamic trust arbitrary URL. |

**Điểm dễ sai với routing datasource:** Nếu gọi `AbstractRoutingDataSource` và chọn `lookupKey` từ `X-Tenant` tùy ý, attacker có thể khiến server hỏi nhầm database tenant khác. Với login chưa xác thực, candidate tenant chỉ nên được dùng để **chọn nguồn verifier ứng viên trong registry được phê duyệt**, và credential phải được kiểm trong chính nguồn đó. Sau login, các request đọc nghiệp vụ chọn DB dựa trên tenant đã verified và quyền membership, không chỉ theo header.

Ngoài ra, việc lưu tenant trong `ThreadLocal` custom cần lifecycle cleanup rất cẩn thận, đặc biệt với thread pooling, async execution, scheduled jobs và event processing. Một tenant context cũ bị rò qua thread tái sử dụng có thể là lỗi an toàn nghiêm trọng. Ưu tiên truyền một `TenantContext` bất biến/explicit từ principal đến service/repository và dùng cơ chế context propagation chính thức khi cần, thay vì giả định request thread là tất cả.

### RLS là lớp bổ sung, không thay login đúng tenant

Với PostgreSQL Row-Level Security hoặc giải pháp tương đương, DB có thể bắt buộc predicate tenant theo session role/configuration. Đây là defense-in-depth hữu ích nhưng cần bảo đảm ứng dụng đặt tenant session variable/DB role từ **principal đã xác thực**, không từ raw header; chú ý connection pool reset state, bypass role, migration user và integration tests. Không coi RLS là lý do bỏ `WHERE tenant_id=?` trong những query mà policy yêu cầu.

## 10. Authorization phải scoped theo tenant, không chỉ theo role

Một role như `ROLE_ADMIN` hoặc authority `orders:read` **chưa đủ** để kết luận có thể truy cập mọi tenant. Quyền có thể có ngữ nghĩa:

- `(tenant=acme, authority=orders:read)`: chỉ đọc orders trong Acme.
- `(tenant=boreal, authority=orders:read)`: chỉ đọc orders trong Boreal.
- Quyền platform operator: có thể kiểm nhiều tenant theo policy quản trị tách biệt, có audit và least privilege.

Đừng chuyển mọi role tenant thành một authority global rồi cho phép `hasRole("ADMIN")` truy cập thông tin tổ chức khác. Trong app demo, `TenantPrincipal` xác định effective tenant và endpoint `/api/orders/{orderId}` lọc tenant+owner ở DB. Đây là **hai lớp kiểm soát bổ sung**: route-level `orders:read` và object-level tenant/owner.

Một người dùng có thể có vai trò `READER` nhưng chỉ được đọc đơn hàng mình sở hữu. Một người có `TENANT_ADMIN` có thể đọc tất cả orders trong tenant mình, nhưng không được đọc tenant khác. Những logic này phải thể hiện tại service/repository/authorization policy, không để UI ẩn nút thay thế.

### 10.1 Chống IDOR/BOLA

Giả sử Alice thuộc Acme biết order ID `2001` thuộc Boreal. Nếu endpoint:

```sql
SELECT * FROM tenant_orders WHERE order_id = ?;
```

thì đoán ID có thể lấy được dữ liệu tenant khác. Đúng hơn, scope theo security context:

```sql
SELECT title
FROM tenant_orders
WHERE order_id = ?
  AND tenant_id = ?
  AND owner_account_id = ?;
```

Đầu vào thứ hai/thứ ba lấy từ verified principal, không từ `?tenant=...` hay `?owner=...` client tự khai. Trả `404` hay `403` khi object không thuộc scope tùy policy chống rò sự tồn tại; **không đưa chi tiết object ra error/log không kiểm soát**.

### 10.2 Chuyển tenant đúng cách

Nếu user được phép làm việc với nhiều tenant, cơ chế switch có thể là:

1. User đã xác thực bằng global identity hoặc subject ổn định.
2. Client yêu cầu chuyển sang tenant T.
3. Server kiểm active membership/permission với subject đó và T.
4. Server cập nhật context/session hoặc cấp token mới **ràng buộc T và authorities của T** theo policy.
5. Mọi request tiếp theo kiểm token/session mới; request với tenant không khớp bị reject hoặc phải đi qua switch flow.
6. Khi membership bị thu hồi, invalidate/refresh sessions/tokens/cache theo yêu cầu độ mới.

Không bao giờ chỉ lưu `activeTenant` do browser chỉnh sửa vào một header/cookie không ký/không bảo vệ rồi cho repository dùng trực tiếp.

## 11. Đăng ký và quản lý account trong nhiều tenant

**Tìm đúng account khi login** chỉ là một phần của vòng đời. Khi tạo/quản lý user:

- Chỉ tạo account trong tenant mà người gọi có quyền quản trị hoặc qua provisioning workflow đã được phê duyệt.
- Database unique `(tenant_id, canonical_login_name)` phải bảo vệ concurrency. `SELECT EXISTS` trước insert không loại bỏ được race condition; cần xử lý unique constraint failure.
- Email có thể là login identifier hoặc kênh khôi phục, nhưng một email có thể tham gia nhiều tenant. Password reset phải chỉ rõ **account/namespace nào** được khôi phục.
- Khi gửi email invitation, ràng buộc token mời với tenant, inviter, user/email, expiry và one-time semantics; không cho token của Acme mở membership Boreal.
- Khi tạo role grant, ghi `tenant_id` cùng `account_id` và người cấp phép; tránh insert `ROLE_ADMIN` chỉ vì request nói cần.
- Khi xóa/disable tenant, xử lý account, memberships, session, tokens, secrets và dữ liệu với policy rõ; không chỉ “xóa prefix tenant trong UI”.
- Backup/restore, import/export và background jobs cũng phải biết tenant; job chạy không có HTTP request không thể lấy tenant từ request header.

**Xung đột tên:** `sam` ở Acme và `sam` ở Boreal không có nghĩa hai account cùng người. Không gộp tài khoản, đồng bộ password hash hoặc chuyển quyền giữa chúng dựa trên username giống nhau.

## 12. Cache và session: giữ nguyên namespace qua nhiều request

### 12.1 Cache key

Cache `UserDetails` nên theo **qualified login key** hoặc khóa account toàn cục thực sự duy nhất, không chỉ `login_name`:

```text
SAI:
  userCache["sam"]  -> Account #101/Acme

ĐÚNG:
  userCache["acme|sam"]   -> Account #101/Acme
  userCache["boreal|sam"] -> Account #202/Boreal

CẦN KIỂM THÊM:
  authorityCache[(tenantId, accountId)]
  membershipCache[(tenantId, globalUserId)]
```

`org.springframework.security.core.userdetails.User` triển khai `CredentialsContainer`; sau thành công, `ProviderManager` có thể erase credentials trên principal. Nếu cùng object `UserDetails` từ cache được tái sử dụng, password hash có thể bị xóa dẫn tới lỗi login lần sau. Cần tách cache verifier và principal copy phù hợp, test tính đúng đắn khi nhiều request. Không tắt erase chỉ để che bug cache.

### 12.2 Session/JWT sau khi tenant hoặc role thay đổi

Một session đã authenticated thường giữ một snapshot principal/authorities. Khi user rời tenant, đổi role hoặc account bị disable, **thay đổi DB không tự đảm bảo mọi session/JWT đang sống lập tức bị từ chối**. Cần quy định:

- Bao lâu là độ trễ tối đa chấp nhận cho việc thu hồi quyền?
- Khi nào bắt buộc revalidate membership/tenant status?
- Session nào cần invalidate, token nào cần revoke và cache key nào cần làm mới?
- Nếu switch tenant, có tách session/token theo tenant không; cách ngăn request cũ bị hiểu theo tenant mới?
- Các API đọc dữ liệu nhạy cảm có kiểm quyền với nguồn cập nhật hơn cache không?

**Không giữ một tenant mutable global variable** trong singleton Spring bean. Nhiều request/tenant chạy đồng thời; dùng instance request-scoped/context đúng cách hoặc explicit parameter lấy từ principal.

### 12.3 Audit log không làm lộ credential

Log có thể gồm `tenantId` đã xác thực, `accountId`, request ID, action, outcome, thời điểm và reason code đã làm sạch. Trước login, tenant hint chỉ nên được ghi nhận theo chính sách chống enumeration/PII; không log password, JWT, bearer token, session cookie hoặc full authentication object có thể chứa secret. Trên hệ thống nhiều tenant, quyền đọc audit log cũng cần tenant scope.

## 13. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách kiểm và sửa |
| --- | --- | --- |
| Hai tenant trùng `sam`, login thỉnh thoảng vào sai account | SQL chỉ có `WHERE username=?` hoặc cache key theo username. | Query composite, unique/index và cache key bao gồm tenant; kiểm principal sau login. |
| Password của tenant A dùng được để vào account tenant B | Code xác thực global username rồi gán tenant từ header mà không kiểm membership. | Xác minh credential với đúng account hoặc global identity + membership workflow riêng. |
| Đăng nhập thành công nhưng trả role tenant khác | Authority query thiếu tenant/account scoping. | Filter quyền theo tenant và account ID từ account đã kiểm. |
| User có quyền `ROLE_ADMIN` ở A nhưng đọc được B | Role toàn cục không scoped trong authorization. | Bắt buộc tenant predicate/object policy, tách platform-admin với tenant-admin. |
| Header `X-Tenant` thay đổi được dữ liệu trả về | API tin header client như tenant đã xác thực. | Chỉ dùng header như hint; authorization dùng verified principal/membership. |
| Subdomain bị giả mạo ảnh hưởng account lookup | Không kiểm `Host`/proxy forwarded headers/tenant registry. | Cố định trusted hosts và ingress rules; validate tenant candidate trước lookup. |
| `JwtIssuerAuthenticationManagerResolver` chấp nhận mọi `iss` | Issuer không allowlist. | Dùng trusted issuer registry và verify JWT đầy đủ; tránh arbitrary metadata URLs. |
| `getPrincipal()` không có tenant/accountId | Chỉ giữ username thuần, thiếu binding. | Custom principal/adapter mang accountId, tenantId từ DB; tránh ép cast sai loại với JWT. |
| Một người có hai tenant nhưng session lẫn quyền | Global role bag hoặc mutable active tenant không kiểm membership. | Context theo tenant, switch workflow + reissue/refresh auth state. |
| Đã disable user nhưng session cũ vẫn hoạt động | Session/JWT còn hiệu lực, cache stale. | Định nghĩa freshness/revocation, invalidate theo tenant/account và test. |
| Câu SQL có tenant predicate nhưng JOIN kéo data tenant khác | JOIN chỉ theo ID không đủ, khóa không global. | JOIN theo composite key, kiểm FK/PK và predicate tenant xuyên suốt query. |
| Admin import account trùng tên tạo bất nhất | Thiếu unique `(tenant_id, login_name)`, race tạo user. | DB constraint + transaction + xử lý conflict. |
| Multi-tenant datasource dùng lại sai schema | Connection pool không reset tenant/schema. | Thiết lập/reset session context đúng transaction/connection lifecycle, integration test. |
| API trả 404 không như kỳ vọng | Filter tenant+owner làm object ngoài scope không xuất hiện. | Phân biệt 404 có chủ đích với query thiếu data; không bỏ tenant predicate chỉ để trả 200. |
| HTTP 403 sau login | Thiếu authority của tenant đang xác thực hoặc object policy từ chối. | Xem authenticated tenant/account/authority (đã làm sạch) và query scope. |

### Trình tự debug an toàn

1. **Đúng chain/filter?** Request đã đi vào cơ chế authentication định dùng hay chưa?
2. **Tenant candidate từ đâu?** Giá trị trước login đã kiểm format, allowlist và namespace chưa?
3. **Đúng lookup?** SQL có **đủ tenant_id + login_name**; tham số được bind; datasource/schema đúng?
4. **Đúng verifier?** Hash lấy từ record thuộc tenant được chọn; `PasswordEncoder.matches` có kiểm đúng raw password?
5. **Đúng kết quả?** Principal sau login chứa tenant/account ID từ server, không tự khai?
6. **Đúng authority?** Roles/memberships được nạp theo tenant/account đã verified?
7. **Đúng data query?** Mọi đọc/ghi đối tượng đã áp tenant + owner/permission scope?
8. **Đúng lifecycle?** Session/JWT/cache có độ mới và thu hồi quyền phù hợp?
9. **Không rò dữ liệu?** Log, trace, error response không chứa password, token, full account record hay PII vượt yêu cầu?

Không log password hoặc raw token để debug. Dùng request ID, account ID nội bộ đã được phép ghi, tên lớp provider, result code và tenant verified khi thích hợp.

## 14. Ma trận kiểm thử cần có

| Bài test | Kết quả mong đợi |
| --- | --- |
| Hai account có cùng `login_name=sam` ở hai tenant | Schema cho phép lưu cả hai, unique không báo conflict. |
| Tạo thêm `sam` lần hai trong cùng tenant Acme | Unique `(tenant_id, login_name)` từ chối. |
| `acme|sam` + password Acme | Authentication thành công với `tenantId=acme`, `accountId=101`. |
| `boreal|sam` + password Boreal | Authentication thành công với `tenantId=boreal`, `accountId=202`. |
| `acme|sam` + password Boreal | HTTP 401; tuyệt đối không fallback sang account Boreal. |
| `boreal|sam` + password Acme | HTTP 401; tuyệt đối không fallback sang account Acme. |
| Qualified key sai định dạng, tenant không tồn tại | Lỗi authentication chung, không leak account existence. |
| Acme đọc order Acme của mình | 200 nếu có `orders:read` và owner đúng. |
| Acme đọc order Boreal `2001` | 404/403 theo chính sách, không lộ dữ liệu. |
| Boreal đọc order Acme `1001` | 404/403 theo chính sách, không lộ dữ liệu. |
| Acme đọc report cần `reports:read` | 403 do thiếu authority. |
| Boreal đọc report | 200 nếu có `reports:read`. |
| Client gửi `X-Tenant: boreal` với auth Acme | Effective principal vẫn là Acme; không tự đổi account/roles. |
| Token JWT issuer không trong allowlist | Bị từ chối, không tạo decoder trust arbitrary issuer. |
| JWT hợp lệ cho issuer A nhưng request yêu cầu tenant B | Chỉ cho phép nếu verified mapping/membership với B; không tự switch. |
| Cache load `sam` từ tenant A rồi từ B | Không collision cache; hash, status và authorities không trộn. |
| Sau revoke membership/role | Session/cache/token phản ánh chính sách thu hồi đúng thời hạn. |
| SQL JOIN theo account ID bị nhập nhằng | Schema/query kiểm composite tenant + account; không trả record sai tenant. |
| JDBC connection pool chuyển tenant | Không rò schema/session context từ request trước. |
| Background job không có HTTP request | Vẫn truyền explicit verified/system-authorized tenant context và scope data. |

**Kiểm thử tốt không chỉ xem 200/401/403.** Cần assert ID account và tenant sau authentication, đọc đúng authority rows, kiểm SQL có tenant predicate và thử truy cập trực tiếp bằng IDs của tenant khác. Với đa datasource, thực hiện integration test trên cơ sở dữ liệu và cấu hình kết nối gần production.

## 15. Bài tập tư duy có lời giải

### Câu 1: Vì sao chỉ có UNIQUE(username) không phù hợp?

Hệ thống cho phép Acme và Boreal đều có account `sam`. Nếu bảng đặt `UNIQUE(login_name)` toàn cục, nó sẽ chặn account thứ hai. Điều kiện đúng là unique theo **namespace thực sự** của login, ví dụ `UNIQUE(tenant_id, login_name)`, cộng canonicalization và index phù hợp.

### Câu 2: Có thể tin tenant từ form login chưa xác thực không?

**Không thể tin nó là membership hay quyền.** Form field có thể dùng làm tenant *ứng viên* để định tuyến lookup, với validation/allowlist. Chỉ sau khi password/credential được kiểm đúng account và trạng thái hợp lệ, server mới tạo principal có tenant ID đáng tin từ account record.

### Câu 3: Một người đăng nhập thành công ở Acme, sau đó sửa `X-Tenant: boreal` để đọc dữ liệu Boreal. API phải làm gì?

**Không đổi effective tenant** chỉ vì header. Với session/token Acme, API phải dùng tenant Acme từ verified principal cho query. Nếu user thực sự có membership Boreal, yêu cầu chuyển tenant phải được xác minh riêng và cấp context phù hợp.

### Câu 4: Đã lọc tenant khi tra user, có cần lọc tenant khi đọc order?

**Có.** Account lookup đúng bảo đảm principal đúng; object authorization và data isolation là bước khác. Một user Acme có thể đoán order ID Boreal. Repository phải dùng tenant/owner scope hoặc policy tương đương để không lộ object.

### Câu 5: User toàn cục #7 là member của Acme và Boreal. Vì sao không ghép role của hai tenant vào một danh sách global?

Vì `ROLE_ADMIN` của Acme có thể bị dùng để truy cập Boreal nếu ứng dụng không ràng buộc role với tenant. Phải kiểm membership và quyền của **tenant hiện hành**, hoặc dùng một biểu diễn quyền có scope rõ ràng và policy đọc đúng scope đó.

### Câu 6: JWT có `iss=https://evil.example`, server tự lấy JWKS từ đó rồi coi hợp lệ. Sai ở đâu?

Issuer chưa được đăng ký là bên tin cậy. Attacker có thể tự phát token ký bằng key của họ rồi yêu cầu server dùng key đó. Resolver phải chỉ chọn issuer từ trusted registry, decoder xác minh issuer/audience/signature/lifetime và mapping tenant theo hợp đồng.

### Câu 7: Cache `UserDetails` đặt key `sam`; có bug gì?

Hai account `acme|sam` và `boreal|sam` đè hoặc lấy nhầm cache entry, dẫn tới dùng sai password hash, account status và authorities. Key phải bao gồm tenant + canonical username hoặc một global account ID thật sự duy nhất.

### Câu 8: Account có `tenant_id=acme` nhưng order row ghi `tenant_id=boreal` và `owner_account_id=101`. Làm sao chặn ngay ở DB?

Dùng FK ghép `(tenant_id, owner_account_id) REFERENCES tenant_accounts(tenant_id, account_id)` và ràng buộc unique tương ứng ở bảng account. Khi đó order không thể tham chiếu owner khác tenant dù code chèn sai.

### Câu 9: Hai tenant dùng hai IdP khác nhau, nhưng JWT `sub` đều bằng `123`. Dùng `sub` làm global account key được không?

Không. Cần ràng buộc issuer và subject đã được verify, hoặc dùng internal account mapping unique, sau đó kiểm tenant membership. `sub` không được giả định duy nhất giữa các issuer.

### Câu 10: Vì sao 404 khi Boreal gọi `/api/orders/1001` trong demo là kết quả có chủ đích?

Vì SQL lấy principal Boreal làm tenant+owner và không thấy order Acme. Trả 404 tránh tiết lộ sự tồn tại đối tượng ngoài scope trong chính sách demo. Nó không có nghĩa order bị xóa khỏi DB.

## 16. Tài liệu chuyên sâu

- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): luồng `UserDetailsService`, `PasswordEncoder`, `AuthenticationManager` cho username/password.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): lựa chọn issuer/token verifier có kiểm soát, `AuthenticationManagerResolver` và trusted issuers.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `AuthenticationProvider` và `SecurityContextHolder`.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): hợp đồng của security view.
- [Spring Security — User class API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html): constructor, authorities, trạng thái, `CredentialsContainer` và chú ý cache.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, kiểm quyền trên mọi request, tránh IDOR/BOLA.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): cô lập dữ liệu, scope/identity/caching trong môi trường multi-tenant.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): khởi tạo H2 bằng `schema.sql` trong môi trường demo.

**Kết luận:** Multi-tenancy là **ranh giới định danh và dữ liệu**, không phải một chuỗi `tenantId` để hiển thị trên UI. Muốn tìm đúng account, truy vấn phải scoped bằng tenant + login identifier; credential được kiểm với account đó; principal giữ tenant/account từ nguồn có thẩm quyền; authorities và mọi resource query tiếp theo dùng scope đã verified. Một sai lệch ở bất kỳ bước nào đều có thể biến việc “hai tổ chức cùng username” thành lỗi truy cập chéo tenant.