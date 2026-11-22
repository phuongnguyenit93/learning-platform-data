# Phân biệt tài khoản nghiệp vụ với principal dùng trong bảo mật

Hãy hình dung ứng dụng quản lý tài liệu có một tài khoản trong cơ sở dữ liệu:

~~~text
accounts
  id            = 101
  login_email   = "mai@example.test"
  display_name  = "Mai Nguyen"
  tenant_id     = "company-a"
  status        = "ACTIVE"
  password_hash = "{bcrypt}..."  (chỉ minh họa định dạng)
~~~

Mai đăng nhập thành công. Khi xử lý `GET /me`, Spring Security cung cấp một **principal** đại diện cho danh tính đã xác thực. Người mới học thường muốn viết `Account account = (Account) authentication.getPrincipal();` rồi dùng trực tiếp tài khoản này để đọc hoặc sửa dữ liệu. Cách nghĩ ấy có thể sai cả về **kiểu Java** lẫn **ranh giới tin cậy và vòng đời dữ liệu**.

**Tài khoản nghiệp vụ (business account)** là đối tượng mà hệ thống quản lý để thực hiện nghiệp vụ: hồ sơ, quan hệ với tổ chức, trạng thái, chủ sở hữu, lịch sử và các ràng buộc dữ liệu. **Principal trong Spring Security** là biểu diễn danh tính gắn với một lần xác thực hoặc request trong **ngữ cảnh bảo mật**; nó có thể là chuỗi tên đăng nhập, `UserDetails`, `Jwt` hoặc kiểu tùy chỉnh.

Hai đối tượng có thể tham chiếu đến **cùng một người hoặc dịch vụ**, nhưng không buộc cùng class, cùng dữ liệu, cùng thời gian tồn tại hay cùng quyền truy cập.

Bài này giúp bạn thiết kế ranh giới rõ ràng giữa **identity trong security** và **account trong domain**, chọn định danh ổn định để ánh xạ, xử lý thay đổi tài khoản/đa tenant, và triển khai ví dụ Java 17+ với Spring Security.

## 1. Bốn khái niệm cần tách khỏi nhau

| Khái niệm | Thuộc trách nhiệm nào? | Dữ liệu tiêu biểu | Điều không thể suy ra |
| --- | --- | --- | --- |
| **Tài khoản nghiệp vụ (`Account`)** | Domain/database và các quy tắc nghiệp vụ | `id`, email, tên hiển thị, tenant, trạng thái, quan hệ, dữ liệu hồ sơ | Có object `Account` tức đã xác thực |
| **Principal** | Định danh trong ngữ cảnh xác thực | Username, ID chủ thể, `UserDetails`, `Jwt`, `OAuth2User`, custom principal | Principal luôn là entity `Account` hoặc luôn có đủ dữ liệu mới nhất |
| **`Authentication`** | Thông tin/yêu cầu/kết quả xác thực trong Spring Security | `principal`, `credentials`, `authorities`, trạng thái, `details` | Được phép đọc tất cả bản ghi |
| **`GrantedAuthority`** | Đầu vào cho phân quyền | `ROLE_USER`, `DOCUMENT_READ`, `SCOPE_profile` | Một authority đồng nghĩa mọi bản ghi của người khác cũng được xem |

Hai cách đặt câu hỏi hữu ích:

- Domain hỏi: **“Tài khoản số 101 thuộc tổ chức nào, trạng thái hiện tại thế nào và có được sửa hồ sơ này không?”**
- Security hỏi: **“Yêu cầu hiện tại được xác thực dưới danh tính nào, bằng cơ chế nào, và có những authorities nào?”**

Cầu nối giữa hai phía thường là **một ID đã được máy chủ xác minh**, ví dụ `accountId=101`, chứ không phải việc ép kiểu ngầm giữa `Authentication` và entity JPA.

## 2. Domain Account là dữ liệu kinh doanh, không phải một token đăng nhập

Một entity/account trong ứng dụng có thể trông như sau:

~~~java
// Mô hình domain đơn giản; chưa phải JPA entity hoàn chỉnh.
public record Account(
        long id,
        String loginEmail,
        String displayName,
        String tenantId,
        boolean enabled) {
}
~~~

Trong hệ thống thật, `Account` còn có thể lưu quan hệ với phòng ban, tổ chức, trạng thái phê duyệt, giới hạn sản phẩm và dấu thời gian cập nhật. Một số hệ thống có bảng tách biệt:

~~~text
users/accounts           -- ID tài khoản, hồ sơ, trạng thái
login_credentials        -- password hash, phương thức đăng nhập
external_identities      -- liên kết issuer + subject từ SSO
memberships              -- user/account thuộc tenant nào
roles/role_assignments   -- quyền theo từng không gian/tổ chức
audit_events             -- ai làm gì, trên tài nguyên nào
~~~

Không có một schema bắt buộc duy nhất. Điều cốt lõi là **domain model được tối ưu cho nghiệp vụ và nguồn dữ liệu có thẩm quyền**, còn principal được tối ưu cho nhận diện chủ thể đã xác thực và truyền **những thông tin tối thiểu** cần thiết trong ngữ cảnh request.

Một `Account` có thể tồn tại khi chưa từng đăng nhập, ví dụ tài khoản được quản trị viên tạo hoặc tài khoản đang chờ kích hoạt. Ngược lại, một `principal` của tài khoản máy, người dùng khách hoặc danh tính bên ngoài có thể chưa ánh xạ tới `Account` nội bộ nếu ứng dụng chưa cho phép tạo/liên kết tài khoản.

**Không nên để class entity quyết định người gọi đã đăng nhập chỉ vì truy vấn tìm thấy bản ghi.** Chức năng tìm tài khoản và chức năng xác thực là hai hoạt động khác nhau.

### Các trạng thái domain dễ gây hiểu nhầm

| Trạng thái tài khoản | Ý nghĩa nghiệp vụ có thể có | Tác động đến xác thực/phân quyền |
| --- | --- | --- |
| `PENDING` | Chưa xác minh email hoặc chờ phê duyệt | Có thể không được đăng nhập hoặc chỉ dùng chức năng giới hạn |
| `ACTIVE` | Đang hoạt động | Vẫn phải xác thực và kiểm tra quyền từng request |
| `SUSPENDED` | Bị tạm khóa theo quy trình kinh doanh | Cần quy tắc chặn đăng nhập và có thể thu hồi phiên/token cũ |
| `DELETED` | Đã bị xóa/vô hiệu hóa | Không cho tiếp tục dùng principal/token cũ để truy cập dữ liệu |
| `INVITED` | Đã mời vào tenant nhưng chưa chấp nhận | Không tự có quyền xem dữ liệu tenant đó |

Tên và ý nghĩa trạng thái là lựa chọn của ứng dụng. Không lấy một enum nghiệp vụ rồi mặc định Spring Security tự hiểu. Phải **ánh xạ trạng thái sang policy xác thực và phân quyền** phù hợp, kể cả các request được gửi trước khi thay đổi trạng thái.

## 3. Principal là gì trong Spring Security?

`Authentication` là interface mở rộng `java.security.Principal` và có các phương thức như `getPrincipal()`, `getAuthorities()`, `getCredentials()`, `getDetails()`, `isAuthenticated()` và `getName()`.

Ví dụ khi đọc:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    Object principal = authentication.getPrincipal();
    String name = authentication.getName();
}
~~~

Đây là **mảnh mã nằm trong ứng dụng Spring Security Servlet**, không phải chương trình Java độc lập; cần import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`.

Ba biến có ý nghĩa khác nhau:

- `authentication`: toàn bộ trạng thái/yêu cầu xác thực trong ngữ cảnh hiện tại.
- `authentication.getPrincipal()`: đối tượng đại diện danh tính của chủ thể, kiểu thực tế phụ thuộc cơ chế.
- `authentication.getName()`: tên nhận diện do `Authentication` triển khai, không bảo đảm là `account.id`, email hiện tại hoặc tên hiển thị.

Trong Spring MVC, có thể dùng `@AuthenticationPrincipal` để inject **đúng principal** làm tham số của controller. Annotation này giải quyết cách truy cập dữ liệu trong request, **không tự truy vấn database và không tự biến JWT thành domain Account**.

### Principal có những kiểu nào?

| Cơ chế xác thực | Principal thường gặp | Lưu ý |
| --- | --- | --- |
| Yêu cầu username/password trước khi kiểm tra | Chuỗi username do người dùng khai | Chưa phải kết quả xác thực đáng tin |
| `DaoAuthenticationProvider` sau xác thực bằng username/password | Một `UserDetails` do `UserDetailsService` trả về | `UserDetails` có thể là lớp `User` mặc định hoặc custom |
| OAuth2/OIDC login | `OAuth2User` hoặc `OidcUser` | Có claims/attributes bên ngoài, tên hiển thị có thể khác ID nội bộ |
| Resource Server xác thực JWT | Mặc định thường là `Jwt` | `getName()` mặc định có thể ánh xạ từ claim `sub` |
| HTTP Basic với custom provider | Kiểu principal của provider | Không được mặc định ép về `UserDetails` |
| Anonymous authentication | Giá trị đại diện anonymous, có thể là chuỗi | Không phải tài khoản thực đã chứng minh danh tính |
| Service-to-service/client credentials | Principal ứng dụng/dịch vụ | Không nhất thiết có người dùng tương ứng trong database |

Đừng viết:

~~~java
// SAI: giả định principal luôn là entity JPA/domain Account.
Account account = (Account) authentication.getPrincipal();
~~~

Trong một hệ thống dùng JWT, `getPrincipal()` có thể là `Jwt`; trong một hệ thống dùng form login, nó có thể là custom `UserDetails`. Cách ép kiểu trên có thể ném `ClassCastException`. Ngay cả khi bạn cố ý nhét `Account` vào principal, điều đó vẫn đòi hỏi thiết kế cẩn thận về tính mới của dữ liệu và bảo vệ thông tin nhạy cảm.

## 4. Ranh giới cần hình dung: nguồn tin cậy, bản chiếu và bản ghi hiện tại

Một kiến trúc dễ kiểm soát là:

~~~text
                Request từ browser/API client
                           |
                           v
              Authentication Mechanism
           (password / JWT / OIDC / mTLS ...)
                           |
                           v
              Authentication được xác minh
                 principal + authorities
                           |
                           v
                Cầu nối identity mapping
     (accountId nội bộ hoặc issuer + subject đã xác minh)
                           |
                           v
               Account repository / service
                  -> bản ghi hiện tại
                  -> membership, tenant, status
                           |
                           v
                 Authorization policy
             (action + resource + context)
                           |
                           v
                 Domain operation / DTO
~~~

Trong sơ đồ, **principal là bản chiếu/phương tiện mang danh tính**, còn repository/service cung cấp thông tin nghiệp vụ mới nhất và có thẩm quyền. Những thuộc tính principal có thể là snapshot được tạo lúc đăng nhập hoặc lúc token phát hành.

Hai ví dụ:

1. Mai đổi email từ `mai@old.test` sang `mai@new.test`. Nếu domain lưu `accountId=101`, quan hệ sở hữu tài liệu vẫn trỏ về 101. Nhưng nếu application dùng email làm khóa owner, việc đổi email dễ làm gãy liên kết.
2. Mai bị rút quyền quản lý tenant A. Session/JWT cấp trước có thể vẫn chứa một authority hoặc claim cũ. Muốn thu hồi quyền nhanh, chính sách phải xem dữ liệu quyền hiện hành, versioning, token/session invalidation hoặc cơ chế kiểm tra lại; không giả định mọi principal tự cập nhật ngay.

**Bản ghi Account là dữ liệu thay đổi được; principal có thể cũ.** Vì thế trong quyết định quan trọng như xuất tiền, xem hồ sơ nhạy cảm, thay đổi quyền, cần kiểm tra chính sách tại thời điểm thao tác, không chỉ tin snapshot lúc login.

## 5. Phân biệt các loại định danh: ID ổn định, username, email, subject

Một người có thể có nhiều tên:

| Giá trị | Ví dụ | Có nên làm khóa nội bộ lâu dài? |
| --- | --- | --- |
| `accountId` do hệ thống cấp | `101` hoặc UUID | **Thường có**, nếu ID bất biến, không tái sử dụng và định danh đúng phạm vi |
| `username` | `mai.nguyen` | Có thể thay đổi; tùy chính sách |
| `email` | `mai@example.test` | **Không nên** coi mặc nhiên bất biến hoặc duy nhất xuyên thời gian |
| `displayName` | `Mai Nguyễn` | Không, chỉ để hiển thị |
| JWT `sub` | `oidc-7f9d...` | Ổn định trong phạm vi issuer nếu IdP bảo đảm; cần ghép với `iss` |
| Tenant/membership ID | `tenant-A`, `membership-42` | Xác định quan hệ ở phạm vi cụ thể; không thay thế account ID |
| Role/authority | `ROLE_USER` | **Không** phải định danh |

**Khuyến nghị thiết kế:** cấp một `accountId` nội bộ bất biến, dùng nó làm khóa ngoại owner/audit và để liên kết external identities. Email, tên hiển thị và role được phép thay đổi độc lập. Với hệ đa tenant, một `accountId` có thể thuộc nhiều tenant, nên quyết định quyền vẫn cần membership và tenant phù hợp.

### Đối với SSO/OIDC, đừng chỉ dựa vào email

Hai token có `sub="123"` nhưng đến từ **hai issuer khác nhau** không mặc nhiên đại diện cùng một danh tính. Một khóa liên kết hợp lý có dạng:

~~~text
external_identity_key = (trustedIssuer, verifiedSubject)

("https://idp-a.example", "123") -> internal accountId=101
("https://idp-b.example", "123") -> internal accountId=709
~~~

Đối với OIDC/JWT, server cần xác minh chữ ký, issuer, audience, hạn sử dụng và các điều kiện bắt buộc trước khi dùng claim để ánh xạ. Không lấy `sub` từ JSON chưa xác minh rồi tự coi là principal hợp lệ. Khi liên kết một danh tính SSO mới với tài khoản cũ, cần quy trình chứng minh quyền sở hữu phù hợp; **không tự động nối hai tài khoản chỉ vì email trùng nhau**.

Email có thể thay đổi, tái cấp hoặc thuộc nhiều không gian người dùng. Khóa `iss + sub` thường thích hợp hơn để nhận diện một subject bên ngoài; ID nội bộ mới dùng để neo vào domain.

## 6. UserDetailsService không phải AccountRepository

Trong xác thực mật khẩu, `DaoAuthenticationProvider` thường gọi `UserDetailsService.loadUserByUsername(username)` để lấy `UserDetails`, sau đó dùng `PasswordEncoder` kiểm tra bằng chứng. `UserDetailsService` là **adapter cho nhu cầu của Spring Security**, không buộc repository nghiệp vụ phải có cùng interface.

Ví dụ mô hình:

~~~text
POST /login với username + password
             |
             v
     DaoAuthenticationProvider
             |
    +--------+----------+
    |                   |
    v                   v
UserDetailsService   PasswordEncoder
    |                 matches(...)
    v
AccountRepository
    |
    v
Account + credential hash + trạng thái đáng tin
    |
    v
Custom AccountPrincipal implements UserDetails
    |
    v
Authentication thành công mang AccountPrincipal
    |
    v
Request tiếp theo dùng accountId -> AccountService -> Account hiện tại
~~~

Cách chia trách nhiệm:

- `AccountRepository`: tìm account, lưu dữ liệu, transaction, quan hệ nghiệp vụ.
- `UserDetailsService`: chuyển dữ liệu xác thực thành một `UserDetails` mà provider hiểu; không trả `null` khi không tìm thấy.
- `PasswordEncoder`: `matches(raw, storedHash)`; mật khẩu thô không được lưu.
- `AuthenticationProvider`: kiểm tra bằng chứng, trạng thái và tạo kết quả đã xác thực.
- `AccountPrincipal` (tên do bạn đặt): chứa **ID nội bộ ổn định** cùng thông tin bảo mật tối thiểu.
- `AccountService`: tải trạng thái và quan hệ nghiệp vụ đang có tại thời điểm sử dụng.
- Authorization policy: kiểm tra action/resource/tenant, không mặc định “đã login là xem mọi thứ”.

Không bắt buộc viết custom `UserDetails` trong mọi ứng dụng. Nếu `UserDetails#getUsername()` chính là ID ổn định theo hợp đồng dự án, có thể ánh xạ từ tên này. Nếu username/email thay đổi, custom principal có `accountId` riêng thường minh bạch hơn.

### Có nên nhét nguyên entity JPA vào principal?

Đôi khi kỹ thuật cho phép, nhưng dễ phát sinh nhiều vấn đề:

1. **Dữ liệu cũ:** principal được giữ trong session/token hoặc cache, trong khi account đã đổi tên, quyền hoặc trạng thái.
2. **Tham chiếu nặng:** entity mang quan hệ JPA/lazy proxies có thể gây `LazyInitializationException` khi sử dụng ngoài transaction.
3. **Rò rỉ dữ liệu:** entity có password hash, email, số điện thoại hoặc thông tin nhạy cảm; việc log/serialize nguyên principal rất nguy hiểm.
4. **Khó phân biệt nguồn dữ liệu:** class nghiệp vụ bị phụ thuộc sâu vào Spring Security, khó tái sử dụng trong batch/job/test.
5. **Vòng đời không khớp:** entity gắn persistence context/transaction, principal có thể tồn tại lâu hơn một request hoặc transaction.
6. **Quyền thay đổi:** snapshot roles/memberships có thể lệch so với dữ liệu hiện hành.

Một DTO principal **nhỏ, có ý nghĩa, không mang entity managed** giúp thiết kế rõ hơn. Nếu principal cần giữ password hash trong giai đoạn xác thực mật khẩu, dùng cơ chế xóa credentials sau xác thực theo framework; không đưa password hash vào JSON response hoặc `toString()` nhật ký.

## 7. Ví dụ đầy đủ: Spring Boot 4.1.2 + Java 17 + custom principal

Ví dụ dưới đây chạy một ứng dụng Servlet đơn giản, có hai tài khoản giả trong bộ nhớ để minh họa. Điểm cần nhìn là **Account domain** và **AccountPrincipal security** được định nghĩa **thành hai kiểu khác nhau**.

- Người dùng `mai@example.test` có `accountId=101`.
- Người dùng `an@example.test` có `accountId=102`.
- HTTP Basic cho phép gửi credentials đến `GET /me` để kiểm tra một cách dễ quan sát.
- `@AuthenticationPrincipal AccountPrincipal` cung cấp account ID **đã qua xác thực**.
- Controller tra `AccountDirectory` để lấy bản ghi nghiệp vụ và chỉ trả `AccountView` an toàn.
- `GET /accounts/{id}` kiểm tra ID được yêu cầu có trùng ID của người gọi hay không; không cho Mai xem hồ sơ của An.

Để học phần identity, ví dụ cố ý dùng tài khoản và mật khẩu **giả** trong memory. Không đưa password demo vào production; ứng dụng thật cần DB, HTTPS, chính sách mật khẩu/session, quản lý quyền và audit phù hợp.

### 7.1. Cấu trúc và phụ thuộc

~~~text
account-identity-demo/
  pom.xml
  src/main/java/com/example/identity/
    IdentityApplication.java
    Account.java
    AccountDirectory.java
    AccountPrincipal.java
    SecurityConfiguration.java
    AccountController.java
~~~

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>account-identity-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Chỉ khóa phiên bản **Spring Boot** ở parent, không tự thêm version `spring-security-core`, `spring-security-web` hoặc Framework. Boot BOM quản lý dependency phù hợp. `spring-boot-starter-webmvc` là starter Web MVC của nhánh Boot 4; trong Boot 3 các tutorial thường dùng `spring-boot-starter-web`.

### 7.2. Lớp chạy ứng dụng

Tạo `src/main/java/com/example/identity/IdentityApplication.java`:

~~~java
package com.example.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
~~~

### 7.3. Account là mô hình domain

Tạo `src/main/java/com/example/identity/Account.java`:

~~~java
package com.example.identity;

public record Account(
        long id,
        String loginEmail,
        String displayName,
        String tenantId,
        String passwordHash,
        boolean enabled) {
}
~~~

Ở ví dụ này `passwordHash` đặt cạnh thông tin account để giảm số file cho bài học. Trong sản phẩm thật, nên cân nhắc tách credential và hồ sơ nghiệp vụ. **Không trả record `Account` trực tiếp qua API** vì nó chứa `passwordHash`.

### 7.4. AccountDirectory là nguồn dữ liệu nghiệp vụ

Tạo `src/main/java/com/example/identity/AccountDirectory.java`:

~~~java
package com.example.identity;

import java.util.Map;
import java.util.Optional;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory {

    private final Map<Long, Account> records;

    public AccountDirectory(PasswordEncoder encoder) {
        this.records = Map.of(
            101L, new Account(
                101L, "mai@example.test", "Mai Nguyen", "company-a",
                encoder.encode("demo-password-mai"), true),
            102L, new Account(
                102L, "an@example.test", "An Tran", "company-a",
                encoder.encode("demo-password-an"), true)
        );
    }

    public Optional<Account> findByEmail(String email) {
        return records.values().stream()
            .filter(account -> account.loginEmail().equals(email))
            .findFirst();
    }

    public Optional<Account> findById(long id) {
        return Optional.ofNullable(records.get(id));
    }
}
~~~

`records` là dữ liệu bất biến trong memory, không phải DB. Hash được tạo bằng `PasswordEncoder` lúc ứng dụng khởi động; mật khẩu chỉ là giá trị giả để thử với HTTP Basic. Trong ứng dụng thật, repository nên có truy vấn riêng theo ID/email và bảo vệ giới hạn tenant.

### 7.5. AccountPrincipal là bản chiếu identity cho Spring Security

Tạo `src/main/java/com/example/identity/AccountPrincipal.java`:

~~~java
package com.example.identity;

import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;

public final class AccountPrincipal extends User {

    private final long accountId;

    public AccountPrincipal(Account account) {
        super(
            account.loginEmail(),
            account.passwordHash(),
            account.enabled(),
            true,
            true,
            true,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        this.accountId = account.id();
    }

    public long accountId() {
        return accountId;
    }
}
~~~

Đây là **kiểu security** kế thừa `User` của Spring Security và có thêm `accountId`, được ánh xạ từ bản ghi domain. Nó không chứa nguyên `Account`, không giữ entity JPA và không cần mang tên hiển thị hoặc tenant trong principal. `User` triển khai `UserDetails` và cơ chế xóa credentials; `ProviderManager` thường xóa dữ liệu nhạy cảm khi tạo kết quả xác thực thành công.

`UserDetails#getUsername()` ở đây là email để phục vụ đăng nhập. **Định danh dùng cho nghiệp vụ là `accountId()`**, không phải email. Khi email thay đổi trong database, liên kết dữ liệu theo `accountId` vẫn có thể ổn định, dù phiên xác thực/username đã lưu cần được làm mới theo chính sách.

### 7.6. Cấu hình xác thực username/password

Tạo `src/main/java/com/example/identity/SecurityConfiguration.java`:

~~~java
package com.example.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountDirectory accounts) {
        return username -> accounts.findByEmail(username)
            .map(AccountPrincipal::new)
            .orElseThrow(() -> new UsernameNotFoundException("Invalid user"));
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong luồng HTTP Basic, Spring Security sử dụng `UserDetailsService` và `PasswordEncoder` tương thích để xác minh mật khẩu. Thành công trả một `Authentication` có principal là `AccountPrincipal` vì provider đọc `UserDetails` được adapter trên tạo ra. Khi mật khẩu sai, không tạo principal tin cậy.

Cấu hình `anyRequest().authenticated()` chỉ kiểm tra **đã xác thực**. Nó không cho phép người dùng A xem bản ghi B; việc đó do controller/service áp dụng chính sách. Ví dụ chỉ có GET endpoints, không làm thao tác ghi nên không cần tắt CSRF.

### 7.7. Controller tra Account hiện tại bằng ID của principal

Tạo `src/main/java/com/example/identity/AccountController.java`:

~~~java
package com.example.identity;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AccountController {

    private final AccountDirectory accounts;

    public AccountController(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    public record AccountView(long id, String displayName, String tenantId) {
    }

    private AccountView view(Account account) {
        return new AccountView(
            account.id(), account.displayName(), account.tenantId());
    }

    @GetMapping("/me")
    public AccountView me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AccountPrincipal principal) {
        Account account = accounts.findById(principal.accountId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
        return view(account);
    }

    @GetMapping("/accounts/{id}")
    public AccountView getAccount(
            @PathVariable long id,
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AccountPrincipal principal) {
        if (principal.accountId() != id) {
            throw new AccessDeniedException("Not allowed to view this account");
        }

        Account account = accounts.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
        return view(account);
    }
}
~~~

Điểm cần quan sát:

1. Tham số `@AuthenticationPrincipal AccountPrincipal` lấy đối tượng principal **sau xác thực**. `errorOnInvalidType=true` giúp phát hiện khi cơ chế xác thực đổi mà method vẫn kỳ vọng kiểu cũ.
2. `principal.accountId()` là định danh nội bộ đã được ánh xạ bởi nguồn xác thực; controller không nhận `accountId` do client tự khai khi quyết định “tôi là ai”.
3. `accounts.findById(...)` lấy đối tượng nghiệp vụ. Điều này tạo một ranh giới rõ ràng giữa **identity snapshot** và **domain record**.
4. `getAccount` so sánh ID của người gọi với ID được yêu cầu. Đăng nhập hợp lệ không làm người dùng xem được mọi account.
5. `AccountView` là DTO an toàn: phản hồi chỉ có `id`, `displayName`, `tenantId`, không chứa `passwordHash`.

Trong hệ thống nhiều tenant, chính sách phải bổ sung kiểm tra membership/tenant và các quyền được cấp. Ví dụ đơn giản hóa về quan hệ sở hữu để tập trung vào cách ánh xạ principal sang account.

### 7.8. Chạy và tự kiểm tra

Với JDK 17 trở lên, Maven phù hợp và quyền tải dependency từ Maven Central:

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Sau khi server chạy trên localhost:8080, dùng terminal khác:

~~~bash
curl -s -o /dev/null -w 'anonymous=%{http_code}\n' http://localhost:8080/me
curl -s -o /dev/null -w 'mai-me=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/me
curl -s -o /dev/null -w 'mai-own=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/accounts/101
curl -s -o /dev/null -w 'mai-other=%{http_code}\n' -u mai@example.test:demo-password-mai http://localhost:8080/accounts/102
curl -s -o /dev/null -w 'an-own=%{http_code}\n' -u an@example.test:demo-password-an http://localhost:8080/accounts/102
~~~

Status kỳ vọng theo cấu hình demo:

~~~text
anonymous=401
mai-me=200
mai-own=200
mai-other=403
an-own=200
~~~

Nếu muốn xem DTO ở `/me`, gọi:

~~~bash
curl -s -u mai@example.test:demo-password-mai http://localhost:8080/me
~~~

Response JSON chứa dữ liệu:

~~~json
{"id":101,"displayName":"Mai Nguyen","tenantId":"company-a"}
~~~

Thứ tự property JSON không phải hợp đồng bảo mật; điều quan trọng là **không có password hash**. Các lệnh trên dùng mật khẩu giả phục vụ local demo; với PowerShell trên Windows hãy dùng `curl.exe` nếu `curl` là alias. Không đưa mật khẩu production vào command line hoặc shell history.

Phân tích kết quả:

- `anonymous=401`: không có thông tin xác thực hợp lệ cho `/me`.
- `mai-me=200`: tài khoản Mai xác thực, principal chứa ID 101; repository trả hồ sơ hiện tại.
- `mai-own=200`: Mai đọc bản ghi ID 101 của chính mình.
- `mai-other=403`: Mai vẫn đăng nhập thành công, nhưng ID tài nguyên 102 không thuộc ID chủ thể 101.
- `an-own=200`: tài khoản An có thể đọc bản ghi 102.

Với các hệ thống thực, cần kiểm tra cả tài khoản không tồn tại, tài khoản bị khóa, đổi email, quyền theo tenant, hành động POST/PATCH/DELETE và trường hợp dữ liệu thay đổi đồng thời.

### 7.9. Vì sao ví dụ này đáng học hơn việc ép kiểu entity?

Ví dụ dạy cách tách các trách nhiệm:

~~~text
HTTP Basic request
   |
   v
DaoAuthenticationProvider + PasswordEncoder
   |
   v
UserDetailsService
   |
   v
AccountDirectory.findByEmail()
   |
   v
AccountPrincipal(accountId=101, username="mai@example.test")
   |
   v
Authentication trong SecurityContext của request
   |
   v
@AuthenticationPrincipal lấy accountId=101
   |
   v
AccountDirectory.findById(101)
   |
   v
AccountView JSON, kiểm tra quyền tài nguyên
~~~

Không có thao tác `(Account) authentication.getPrincipal()`. Tài khoản nghiệp vụ và principal vẫn cùng tham chiếu đến ID 101, nhưng mỗi lớp chỉ chịu trách nhiệm phần của mình.

## 8. Khi không dùng username/password: ánh xạ JWT và OAuth2/OIDC

Với Spring Security Resource Server xác thực JWT hợp lệ, principal **mặc định** có thể là `Jwt`, còn `Authentication#getName()` thường lấy từ `sub`.

Mảnh controller minh họa trong một ứng dụng đã cấu hình JWT Resource Server:

~~~java
@GetMapping("/me")
public AccountView me(@AuthenticationPrincipal Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();

    long internalAccountId =
        identityLinks.findAccountId(issuer, subject);
    return accountService.profileFor(internalAccountId);
}
~~~

Các tên `identityLinks`, `accountService`, `AccountView` là **các thành phần ứng dụng phải tự định nghĩa**; đây không phải class độc lập. Nhớ xử lý `issuer/subject` thiếu hoặc sai kiểu và trạng thái tài khoản. Spring Security phải được cấu hình để **xác minh JWT** trước khi controller tin claims. Không parse token do client gửi bằng một JSON parser rồi dùng trực tiếp.

Luồng có thể là:

~~~text
Bearer token từ client
      |
      v
JwtDecoder xác minh chữ ký, issuer, audience, thời hạn...
      |
      v
JwtAuthenticationToken, principal = Jwt
      |
      v
(issuer, subject) đã xác minh
      |
      v
ExternalIdentityLink -> internal accountId
      |
      v
AccountService -> account hiện tại + memberships
      |
      v
Authorization -> DTO/response
~~~

**Không nhất thiết mọi token đều đại diện một con người.** OAuth2 client credentials có thể xác thực một ứng dụng máy chủ; nếu hệ thống yêu cầu một account người dùng, cần chính sách riêng cho danh tính dịch vụ.

Trong Spring Security mới, có thể tùy biến principal converter cho JWT, hoặc dùng một lớp ứng dụng trung gian ánh xạ identity. Nhưng khi API có thể nhận nhiều cơ chế (password, JWT, SSO), tránh viết controller ép cứng mọi principal về cùng một kiểu trừ khi tất cả provider đều thống nhất hợp đồng đó.

### Có cần tự thay principal trong token không?

Không bắt buộc. Có hai lựa chọn hợp lệ:

- **Giữ principal framework cung cấp** rồi ánh xạ qua một `CurrentAccountResolver` hoặc service thích hợp. Cách này giảm thay đổi ở tầng Security.
- **Tạo principal tùy chỉnh** chứa ID nội bộ và metadata được kiểm soát. Hữu ích nếu nhiều endpoint cần chung hợp đồng; cần cấu hình đúng provider/converter và xử lý an toàn vòng đời.

Không lựa chọn nào tự giải quyết quyền truy cập từng dữ liệu. Quy tắc authorization vẫn phải kiểm tra chủ sở hữu, tenant, trạng thái và action.

## 9. Một người có nhiều account hoặc nhiều tenant

Trong SaaS, một cá nhân đăng nhập qua một identity nhưng có thể sở hữu nhiều tài khoản hoặc vai trò trong nhiều tổ chức. Ví dụ:

~~~text
Identity từ SSO:
  issuer = https://idp.example
  subject = external-777

Internal user/account:
  accountId = 101

Memberships:
  accountId=101, tenant=A, role=EDITOR
  accountId=101, tenant=B, role=VIEWER
~~~

Nếu API nhận `X-Tenant-Id: B`, header đó chỉ là **đích yêu cầu** của client, không phải bằng chứng người gọi thuộc tenant B. Server cần xác nhận account 101 có membership tương ứng rồi kiểm tra hành động được phép trong tenant B.

Một phép kiểm truy cập đúng có dạng:

~~~text
allow(subject, action, resource, context) =
    verifiedAuthentication(subject)
    AND currentAccountIsEnabled(subject.accountId)
    AND belongsToTenant(subject.accountId, resource.tenantId)
    AND hasPermission(subject.accountId, action, resource)
~~~

Phép kiểm này là mô hình để học, không phải một API được Spring Security tự cung cấp. Có thể triển khai bằng service authorization, `AuthorizationManager`, method security hoặc truy vấn dữ liệu được giới hạn quyền.

**Đừng cất “tenant hiện tại” như một chuỗi bất biến trong principal rồi mặc định mọi request sau không thể đổi tenant.** Nếu có chọn tenant hiện hành, lựa chọn đó phải được xác thực theo membership; quyền theo tenant cần được kiểm tra mỗi khi cần. Nếu principal có authorities snapshot, cơ chế thu hồi quyền phải được thiết kế rõ.

## 10. Tài khoản có thể đổi, principal có thể cũ: cách xử lý

| Sự kiện | Domain hiện tại | Principal/token đã cấp trước đó | Cách xử lý |
| --- | --- | --- | --- |
| Đổi tên hiển thị | `displayName` mới | Có thể còn tên cũ | Lấy profile từ domain khi hiển thị; không dùng principal làm hồ sơ duy nhất |
| Đổi email đăng nhập | `loginEmail` mới | `getName()`/username có thể cũ | Dùng account ID ổn định, thiết kế re-authentication hoặc refresh |
| Khóa tài khoản | `enabled=false` | Session/JWT trước đó có thể còn hiệu lực | Thu hồi phiên/token hoặc kiểm tra trạng thái ở operation quan trọng |
| Rút vai trò | Bảng memberships/permissions thay đổi | Authorities cũ có thể còn | Quy tắc cập nhật session/cache/token hoặc đánh giá quyền hiện hành |
| Chuyển tenant | Membership thay đổi | Tenant claim/selected tenant có thể cũ | Kiểm tra quan hệ tenant tại thời điểm thao tác |
| Xóa account | Bản ghi không còn | Token cũ vẫn mang ID | Từ chối và thu hồi/quản lý token; không tự tạo lại account cùng ID |
| Đổi nhà cung cấp SSO | External `iss+sub` khác | Principal cũ thuộc issuer trước | Liên kết identity được xác minh, không chỉ match email |

Không có chiến lược thu hồi chung áp dụng cho mọi kiến trúc. Session ở server có thể bị vô hiệu hóa hoặc cập nhật, còn JWT tự chứa claims có thể còn hợp lệ đến khi hết hạn nếu API không kiểm tra trạng thái/phiên/token version từ nguồn tin cậy. Cần cân bằng latency và yêu cầu thu hồi.

Nếu hệ thống quản lý quyền nhạy cảm, việc “đã login một giờ trước” thường không đủ để tiếp tục thao tác sau khi tài khoản đã bị vô hiệu hóa. Phải thiết kế chính sách cập nhật và kiểm soát tài nguyên phù hợp.

## 11. Phân quyền tài nguyên phải dựa trên identity được xác minh

Giả sử URL có `/accounts/102`. Người gọi có principal `accountId=101`. Đây là **hai vai trò ID khác nhau**:

- `callerAccountId=101`: identity được xác minh ở server.
- `requestedAccountId=102`: ID **tài nguyên** do client yêu cầu.
- Policy trả lời Mai có được đọc 102 không, không suy từ việc URL chứa một số hợp lệ.

Một cách kiểm tra ở service có thể là:

~~~java
// Mảnh logic nghiệp vụ, không phải class Java độc lập.
public AccountView readAccount(long requestedId, long callerId) {
    if (requestedId != callerId && !permissionService.canSupport(callerId)) {
        throw new AccessDeniedException("Not allowed");
    }
    Account account = accountRepository.findById(requestedId)
        .orElseThrow(() -> new NotFoundException("No account"));
    return accountViewMapper.toView(account);
}
~~~

Tên repository, permission service, exception mapper là thành phần riêng của ứng dụng. Nếu có admin hỗ trợ, quyền phải đến từ nguồn đáng tin và có phạm vi rõ (ví dụ cùng tenant), không cho phép mọi `ROLE_ADMIN` xem tất cả tenant một cách mặc định.

**IDOR/BOLA:** nếu server chỉ kiểm tra request có principal rồi lấy bản ghi theo `requestedId`, người dùng có thể đổi ID để truy cập dữ liệu không thuộc quyền. Tính riêng tư phải được bảo vệ ở server dù ID là số, UUID hay một chuỗi khó đoán.

Trong hệ có nhiều endpoint, nên đóng gói policy vào service/authorization component chung. Controller chỉ gọi policy mà không tự viết một phiên bản kiểm tra khác nhau ở mỗi API.

## 12. Principal nên chứa những gì, và không nên chứa gì?

Một custom principal nhỏ thường chỉ cần:

- **Stable subject ID** như `accountId` hoặc `actorId`.
- Username/login identifier nếu cơ chế cần.
- Authorities hoặc metadata xác thực đã được xác minh, theo chính sách cập nhật.
- Một số thuộc tính tối thiểu để xử lý security flow nếu thật sự cần.

Hạn chế đưa vào principal:

- Mật khẩu gốc, token bí mật, private key hoặc session secret.
- Toàn bộ JPA entity graph, lazy collections và quan hệ quá lớn.
- Thông tin cá nhân/chi tiết tài chính không cần cho xác thực.
- Dữ liệu nghiệp vụ thay đổi liên tục mà code mặc định tin là luôn mới.
- Chuỗi quyền do client tự khai, chưa được server/provider kiểm tra.
- Dữ liệu dùng cho phản hồi API mà không có lớp DTO/authorization.

Các `UserDetails` phục vụ password login có thể cần mang **password hash** tạm thời để provider kiểm tra. Đây là ngoại lệ có kiểm soát cho quá trình xác thực, không phải lý do để trả hash ra client. Spring Security khuyến nghị hỗ trợ `CredentialsContainer` khi triển khai `UserDetails` tùy chỉnh nhằm xóa credentials sau khi dùng.

Với `User` của Spring Security, `equals` và `hashCode` có thể dựa trên username; nếu username là email có thể đổi, **đừng dựa vào equals của principal làm phép so sánh chủ sở hữu domain**. Dùng `accountId` bất biến và chính sách rõ ràng.

## 13. Những sai lầm thường gặp

1. **“Account và principal phải là cùng class.”** Không. Domain và Security có hợp đồng và vòng đời khác nhau.
2. **“`authentication.getPrincipal()` luôn trả Account.”** Không. Kiểu phụ thuộc provider/cơ chế xác thực.
3. **“`authentication.getName()` luôn là database primary key.”** Không. Có thể là email, username hoặc claim `sub`.
4. **“Đã có record Account tức đã login.”** Không. Account có thể tồn tại độc lập với Authentication.
5. **“Có principal tức người dùng có đủ quyền.”** Không. Xác thực và phân quyền là hai quyết định khác nhau.
6. **“Lưu email làm owner ID là không sao vì email duy nhất.”** Email có thể đổi hoặc tái sử dụng; thường nên dùng ID bất biến.
7. **“JWT có `email` nên có thể match ngay vào account.”** Phải xác minh token/issuer và có chính sách liên kết danh tính; email không luôn là khóa tin cậy.
8. **“JWT `sub=123` từ mọi issuer là cùng một người.”** Không. Subject phải hiểu trong phạm vi issuer và hợp đồng IdP.
9. **“Đưa nguyên entity JPA vào session principal là cách đơn giản nhất.”** Có thể gây stale data, lazy loading, serialization và rò rỉ dữ liệu.
10. **“Đổi role trong database thì authorities của token cũ tự đổi.”** Không mặc định; cần thiết kế refresh/revocation/re-evaluation.
11. **“Principal có ID hợp lệ nên có thể đọc mọi record mang ID do client gửi.”** Sai. Cần object-level authorization.
12. **“`@AuthenticationPrincipal` tự truy vấn account hiện tại.”** Không; nó lấy `Authentication.getPrincipal()`.
13. **“Account trong session là nguồn dữ liệu mới nhất.”** Không chắc. Session có thể chứa snapshot cũ.
14. **“Cứ cast sang UserDetails là an toàn cho mọi API.”** Không; resource server JWT/OIDC có thể dùng principal kiểu khác.
15. **“Tài khoản bị khóa thì mọi token cũ lập tức vô hiệu.”** Không mặc định; cần thiết kế vòng đời phiên/token.
16. **“Tenant do client gửi chính là tenant tin cậy.”** Không; phải so khớp với membership/quyền hiện hành.
17. **“Đọc entity rồi trả JSON trực tiếp tiện hơn DTO.”** Dễ lộ password hash và trường dữ liệu nhạy cảm.
18. **“Dùng principal ID làm role hoặc authority.”** ID là danh tính; quyền là một tập dữ liệu/chính sách riêng.

## 14. Checklist thiết kế identity mapping

Trước khi đưa ứng dụng vào môi trường nhiều người dùng, cần trả lời:

- [ ] Đã có **account ID nội bộ ổn định** làm khóa owner/audit/membership.
- [ ] Biết rõ kiểu principal của **từng phương thức xác thực** (password, JWT, OAuth2, service account).
- [ ] Có một **identity mapping** đáng tin từ subject đến account ID; không dùng claim chưa được xác minh.
- [ ] Nếu dùng external IdP, xác định danh tính theo issuer + subject phù hợp, có quy trình liên kết account.
- [ ] Cơ chế `UserDetailsService` trả UserDetails thích hợp, không trộn entity domain vào payload ngoài ý muốn.
- [ ] Controller/service lấy account bằng ID đáng tin, trả DTO giới hạn trường.
- [ ] Quy tắc phân quyền xét hành động, tài nguyên, owner và tenant; không chỉ `authenticated()`.
- [ ] Có chiến lược cho email thay đổi, account bị khóa/xóa, role bị thu hồi, membership thay đổi.
- [ ] Session/token không mang thông tin nhạy cảm dư thừa; kiểm soát lưu trữ và lifetime.
- [ ] Kiểm thử cả tài khoản hợp lệ truy cập tài nguyên của người khác, không chỉ anonymous bị chặn.
- [ ] Không mặc định `SecurityContextHolder` ThreadLocal khả dụng trong mọi luồng async/reactive; dùng cơ chế propagation đúng stack.
- [ ] Có log/audit sử dụng ID chủ thể đáng tin, không lưu mật khẩu/token trong nhật ký.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một entity `Account` có ID 101 được tìm thấy trong database. Có nghĩa request hiện tại đã đăng nhập bằng tài khoản 101 không?

*Trả lời:* Không. Phải có kết quả xác thực đáng tin trong `Authentication` và cầu nối identity xác định chính chủ thể ấy.

**Câu 2.** Mai đổi email nhưng tài liệu trước đây gắn `owner_account_id=101`. Có nên đổi toàn bộ khóa owner theo email mới không?

*Trả lời:* Không nếu khóa owner đã là ID nội bộ bất biến. Cập nhật email là thuộc tính account; ID 101 tiếp tục đại diện cùng tài khoản.

**Câu 3.** Khi Spring Security dùng JWT Resource Server, vì sao `(Account) authentication.getPrincipal()` có thể thất bại?

*Trả lời:* Vì principal mặc định có thể là `Jwt`, không phải entity `Account`. Cần ánh xạ từ các claims đã được xác minh tới ID tài khoản.

**Câu 4.** Một tài khoản có `ROLE_USER` và có thể gọi `GET /accounts/{id}`. Điều gì ngăn Mai sửa ID trên URL thành 102?

*Trả lời:* Kiểm soát quyền cấp đối tượng trên server, so sánh account ID đáng tin của người gọi với owner/điều kiện được phép của tài nguyên.

**Câu 5.** Hai IdP có cùng `sub="123"`. Có thể tự coi là một người không?

*Trả lời:* Không. Subject thường có ý nghĩa trong phạm vi issuer; phải xác minh issuer, subject và quy trình liên kết account riêng.

**Câu 6.** Tại sao một principal mang `displayName="Mai"` có thể khác tên mới nhất trong database?

*Trả lời:* Principal là snapshot/biểu diễn tại thời điểm xác thực hoặc phát token; domain record có thể được cập nhật sau đó.

**Câu 7.** Nếu dùng `@AuthenticationPrincipal AccountPrincipal`, nên lấy profile hiện tại ở đâu?

*Trả lời:* Từ `AccountService`/repository bằng `accountId` đã được ánh xạ và xác minh; chỉ trả về DTO có những trường người gọi được phép xem.

**Câu 8.** Có nên đưa `passwordHash` vào response `AccountView` vì nó không phải mật khẩu gốc?

*Trả lời:* Không. Hash mật khẩu vẫn là thông tin nhạy cảm và không phải dữ liệu người dùng cần nhận từ API.

**Câu 9.** Account đã bị suspend nhưng client còn JWT hợp lệ theo chữ ký và hạn dùng. Ứng dụng nên làm gì?

*Trả lời:* Áp dụng chính sách vòng đời tài khoản/thu hồi quyền có chủ ý, chẳng hạn tra trạng thái hiện tại, version/revocation, token thời hạn phù hợp hoặc chặn tại service đối với thao tác nhạy cảm.

**Câu 10.** Với SaaS nhiều tenant, `accountId=101` có thể đọc mọi tài liệu tenant A và B không?

*Trả lời:* Không. Cần xác minh membership và quyền trên chính tenant/tài liệu được yêu cầu, không chỉ biết ID của người gọi.

Nguyên tắc giữ ranh giới rõ ràng là: **principal giúp xác định chủ thể của request; account là hồ sơ nghiệp vụ hiện hành; permission policy quyết định chủ thể đó được làm gì với dữ liệu nào**. Dùng một ID ổn định và một lớp mapping có kiểm soát để nối chúng sẽ dễ mở rộng từ form login sang JWT/SSO và dễ bảo trì hơn khi email, quyền, tenant hoặc trạng thái tài khoản thay đổi.

### Tài liệu đối chiếu

- [Spring Security — Authentication Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/)
- [Spring Security — Spring MVC Integration and @AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Boot — Spring Security Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now)
