# ActiveDirectoryLdapAuthenticationProvider và đặc điểm đăng nhập Active Directory (AD)

## 1. Mục tiêu và bối cảnh

`ActiveDirectoryLdapAuthenticationProvider` là `AuthenticationProvider` chuyên biệt của **Spring Security LDAP** để xác thực tài khoản trong **Microsoft Active Directory Domain Services (AD DS)** qua LDAP. Nó phù hợp khi ứng dụng Spring cần nhận username/password từ người dùng và nhờ domain controller (DC) kiểm tra thông tin đăng nhập.

Sau bài này, bạn có thể:

- Giải thích vì sao đăng nhập AD thường dùng `user@domain` (UPN), khác cách bind bằng DN ở LDAP tổng quát.
- Hiểu đầy đủ luồng **bind vào AD → tìm đối tượng user → lấy authorities → Spring Security ra quyết định truy cập**.
- Cấu hình provider trong Spring Security cho một ứng dụng Spring Boot chạy Java 17+.
- Nhận biết các thông số `domain`, `url`, `rootDn`, `searchFilter`; xử lý các trường hợp UPN và `sAMAccountName` không khớp.
- Phân biệt mật khẩu sai, tài khoản bị vô hiệu hóa/khóa, quyền nhóm không đủ và lỗi kết nối LDAP; biết cách bảo vệ thông tin đăng nhập và kết nối TLS.

**Phạm vi:** ví dụ tập trung vào **Spring MVC/Servlet và username/password LDAP bind đến AD DS**. Việc kết nối thành công với AD không tự tạo SSO bằng Kerberos, đăng nhập Windows tích hợp, MFA hay đăng nhập Microsoft Entra ID qua OAuth 2.0/OpenID Connect. Các cơ chế đó có giao thức và cấu hình khác.

## 2. Thuật ngữ AD cần nắm

| Thuật ngữ | Ý nghĩa và ví dụ |
| --- | --- |
| **AD DS** | Dịch vụ thư mục quản lý tài khoản, máy tính, nhóm và chính sách của domain Windows. |
| **Domain Controller (DC)** | Máy chủ cung cấp dịch vụ thư mục và tiếp nhận yêu cầu LDAP; ví dụ `dc1.corp.example.com`. |
| **LDAP / LDAPS** | Giao thức truy cập thư mục; LDAP thường dùng cổng 389, LDAPS (LDAP qua TLS) thường dùng cổng 636. |
| **UPN / `userPrincipalName`** | Tên kiểu `alice@corp.example.com`; thường dùng để đăng nhập AD. Hậu tố UPN có thể khác DNS domain thực tế. |
| **`sAMAccountName`** | Tên đăng nhập kiểu cũ trong một domain, ví dụ `alice`; không đồng nghĩa với UPN. |
| **DN (Distinguished Name)** | Địa chỉ của entry trong cây LDAP, ví dụ `CN=Alice,OU=People,DC=corp,DC=example,DC=com`. |
| **Base DN / root DN** | Gốc để tìm entry, ví dụ `DC=corp,DC=example,DC=com`; không phải mật khẩu hoặc DN đăng nhập. |
| **`memberOf`** | Thuộc tính trên user liệt kê nhiều nhóm AD mà user trực tiếp là thành viên; thông tin đầu vào thường dùng để xây authorities. |
| **`GrantedAuthority`** | Quyền/nhóm đã được đưa vào `Authentication` để các rule của Spring Security kiểm tra. |

Giả sử AD của công ty có domain `corp.example.com` và user `alice`:

~~~text
Người dùng nhập:                  alice / <mật khẩu>
UPN dùng để LDAP bind:           alice@corp.example.com
LDAP URL:                        ldaps://dc1.corp.example.com:636/
Search root mặc định:            DC=corp,DC=example,DC=com
User entry có thể có DN:         CN=Alice,OU=People,DC=corp,DC=example,DC=com
Một giá trị memberOf ví dụ:      CN=AppUsers,OU=Groups,DC=corp,DC=example,DC=com
~~~

**Lưu ý:** dấu `@` trong UPN không biến UPN thành địa chỉ email, dù hai giá trị thường giống nhau. AD có thể đặt hậu tố UPN tùy chỉnh. Chuỗi `CORP\alice` là định dạng tên domain kiểu cũ; không nên mặc định rằng provider sẽ tự chuẩn hóa nó sang UPN phù hợp.

## 3. Vai trò của ActiveDirectoryLdapAuthenticationProvider

Class đầy đủ:

~~~java
org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider
~~~

Class là một implementation của `AuthenticationProvider`, kế thừa `AbstractLdapAuthenticationProvider` và làm việc với luồng xác thực **Servlet** thông thường.

Khi người dùng đăng nhập qua HTTP Basic hoặc form login, Spring Security thường tạo `UsernamePasswordAuthenticationToken` chưa xác thực. `AuthenticationManager` (thường là `ProviderManager`) ủy quyền cho provider phù hợp để xác minh.

~~~text
Client gửi username/password
         │
         ▼
Spring Security Filter (Basic/Form)
         │
         ▼
AuthenticationManager / ProviderManager
         │
         ▼
ActiveDirectoryLdapAuthenticationProvider
         │
         ├─ (1) Ghép username với domain khi cần
         │       alice → alice@corp.example.com
         │
         ├─ (2) LDAP simple bind tới DC bằng UPN + password
         │       Bind thất bại → AuthenticationException
         │
         ├─ (3) Bind thành công → tìm user bằng LDAP searchFilter
         │       Không tìm được entry → xác thực vẫn thất bại
         │
         └─ (4) Đọc thông tin user và authorities
                 │
                 ▼
           Authentication đã xác thực
                 │
                 ▼
        SecurityContext và authorization
                 │
                 ▼
             HTTP response
~~~

Điểm đáng nhớ:

1. Provider **thử bind bằng chính username/password** mà người dùng nhập. Nó không tải password từ AD để so sánh với `PasswordEncoder` của ứng dụng.
2. Sau bind, provider thực hiện tìm kiếm LDAP để xác định entry và lấy dữ liệu cho principal/authorities. **Bind thành công chưa đảm bảo toàn bộ quy trình thành công** nếu search filter hoặc search root sai.
3. LDAP group mapping tạo `GrantedAuthority`. Quyết định được phép gọi `/admin` hay không thuộc **authorization** như `hasRole`/`hasAuthority`, không thuộc bước kiểm chứng password.
4. Xác thực bằng LDAP bind không giống Kerberos SSO hay token OAuth. Với HTTP Basic, client có thể phải gửi credentials lại mỗi request; với form login thường có cơ chế phiên tùy cấu hình.

## 4. Constructor, tham số và mặc định thực tế

Hai constructor chính:

~~~java
new ActiveDirectoryLdapAuthenticationProvider(domain, url);

new ActiveDirectoryLdapAuthenticationProvider(domain, url, rootDn);
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| `domain` | Hậu tố gắn vào username khi cần tạo principal bind. Ví dụ `corp.example.com`. Có thể null/rỗng nếu username đã chứa hậu tố UPN phù hợp. |
| `url` | LDAP URL của DC, ví dụ `ldaps://dc1.corp.example.com:636/`. Có thể cấu hình nhiều URL theo định dạng JNDI được hỗ trợ. |
| `rootDn` | Gốc tìm kiếm user. Nếu dùng constructor 2 tham số với domain `corp.example.com`, provider suy ra `dc=corp,dc=example,dc=com`. Constructor 3 tham số cho phép chỉ định gốc khác. |

Các hành vi quan trọng:

- Với `domain="corp.example.com"`, input `alice` được chuyển thành principal `alice@corp.example.com` để bind và làm giá trị thay thế `{0}` trong search filter.
- Nếu input đã kết thúc bằng domain được cấu hình (không phân biệt hoa/thường theo logic của provider), provider dùng chính chuỗi đó làm principal.
- Nếu `domain` không cấu hình, người dùng phải cung cấp principal có đủ hậu tố để provider có thể bind/tính search root; nếu search root được chỉ định riêng thì vẫn cần một principal mà AD chấp nhận.
- Provider không tự tìm server AD qua DNS SRV chỉ nhờ domain trong constructor. Cần chỉ định LDAP URL phù hợp với môi trường và kế hoạch dự phòng DC.

**Không đánh đồng ba giá trị:** DNS domain `corp.example.com`, hậu tố UPN như `example.org`, và LDAP search root `DC=corp,DC=example,DC=com` có thể khác nhau trong thực tế. Cấu hình phải phản ánh đúng domain/forest và dữ liệu directory.

### 4.1. Search filter mặc định

Giá trị mặc định:

~~~ldap
(&(objectClass=user)(userPrincipalName={0}))
~~~

Placeholder của `setSearchFilter`:

- `{0}`: principal kiểu `username@domain` được provider xây dựng.
- `{1}`: username **nguyên văn** nhận từ yêu cầu xác thực.

Ví dụ nếu giao diện luôn nhận tài khoản ngắn `alice` và AD dùng `sAMAccountName` để tìm user, có thể đổi:

~~~java
provider.setSearchFilter(
    "(&(objectClass=user)(sAMAccountName={1}))"
);
~~~

Đây là **một đoạn cấu hình** trong bean provider, không phải chương trình độc lập. Dù search bằng `sAMAccountName`, bước LDAP bind vẫn dùng principal mà provider đã dựng. Nếu người dùng nhập `alice@corp.example.com` thì `{1}` là toàn bộ `alice@corp.example.com`, không tự cắt còn `alice`. Hãy quyết định định dạng username ở UI/API trước khi chọn filter.

Tránh tự nối chuỗi username vào LDAP filter. Dùng placeholder của API để tham số được xử lý đúng và giảm rủi ro LDAP injection. Search filter phải trả đúng **một user**; filter quá rộng gây kết quả mơ hồ và lỗi xác thực.

### 4.2. Thông tin nhóm và authorities

Theo mặc định, provider lấy authorities dựa trên thuộc tính `memberOf` trong entry người dùng; trên Spring Security 6.3+ có thể thay chiến lược bằng `setAuthoritiesPopulator(...)`. Ngoài ra có thể ánh xạ authorities theo nhu cầu ứng dụng qua cơ chế mapper tương ứng.

Ví dụ AD ghi:

~~~text
memberOf: CN=AppReaders,OU=Groups,DC=corp,DC=example,DC=com
memberOf: CN=SupportTeam,OU=Groups,DC=corp,DC=example,DC=com
~~~

Framework sẽ chuyển dữ liệu nhóm sang các `GrantedAuthority` theo chiến lược đang cấu hình. **Hãy quan sát chuỗi authority thực tế** trước khi viết rule `hasAuthority("...")` hoặc `hasRole("...")`; không suy đoán role từ tên nhóm trên giao diện.

Đặc biệt:

- `memberOf` thường phản ánh **nhóm trực tiếp**; không nên giả định nó tự mở rộng mọi cấp nested group.
- Nhóm chính (primary group) của user có thể không hiện trong `memberOf` như các nhóm thông thường.
- Nếu yêu cầu quyền theo nhóm lồng nhau hoặc nhiều domain/forest, cần thiết kế group lookup/mapping phù hợp và kiểm thử với cấu trúc AD thật.
- `hasRole("ADMIN")` thường kiểm tra authority có tiền tố `ROLE_`; `hasAuthority("ROLE_ADMIN")` so khớp nguyên chuỗi. Chuỗi phải tương ứng với kết quả mapping của ứng dụng.

## 5. Cấu hình Spring Boot hoàn chỉnh (Java 17+, Spring Security 6.x)

Ví dụ dùng **Spring Boot 3.5.x / Java 17+** cho một ứng dụng **Spring MVC/Servlet**. Ứng dụng cung cấp `GET /public` (không yêu cầu đăng nhập) và `GET /me` (đòi hỏi AD authentication qua HTTP Basic).

Đây là một cấu hình **có thể biên dịch và chạy** khi Maven và JDK phù hợp đã cài. Để đăng nhập thành công còn phải có AD DS đang hoạt động, user thật, DNS/network và chứng thư TLS được JVM tin cậy. Tên domain và DC bên dưới là dữ liệu minh họa, không phải máy chủ công khai.

### 5.1. Phụ thuộc Maven

Tạo project Java 17, Maven, Spring Boot 3.5.x trên Spring Initializr với `Spring Web` và `Spring Security`. Thêm Spring LDAP và Spring Security LDAP vào `pom.xml` (nếu đã có dependency trùng, không thêm lần nữa):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-ldap</artifactId>
</dependency>
~~~

Dùng BOM/dependency management do Spring Boot cung cấp để các phiên bản tương thích nhau; không tự gán phiên bản Spring Security độc lập với Boot. Class AD provider nằm trong `spring-security-ldap`, không nằm trong mỗi `spring-boot-starter-security`.

### 5.2. Thuộc tính kết nối

Tạo tệp `src/main/resources/application.properties`:

~~~properties
app.ad.domain=corp.example.com
app.ad.url=ldaps://dc1.corp.example.com:636/
server.port=8080
~~~

Thay domain/DC bằng các giá trị thực do quản trị AD cung cấp. Provider đọc các thuộc tính `app.ad.*` qua `@Value` trong mã bên dưới; đặt `spring.ldap.urls` riêng lẻ **không tự thay thế** các constructor argument đã truyền cho provider này.

### 5.3. Lớp ứng dụng và SecurityFilterChain

Tạo tệp `src/main/java/demo/ad/AdLoginDemoApplication.java`:

~~~java
package demo.ad;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AdLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdLoginDemoApplication.class, args);
    }

    @Bean
    ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider(
            @Value("${app.ad.domain}") String domain,
            @Value("${app.ad.url}") String ldapUrl) {

        var provider = new ActiveDirectoryLdapAuthenticationProvider(
                domain, ldapUrl);

        provider.setConvertSubErrorCodesToExceptions(true);
        provider.setContextEnvironmentProperties(Map.of(
                "com.sun.jndi.ldap.connect.timeout", "5000",
                "com.sun.jndi.ldap.read.timeout", "5000"
        ));
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            ActiveDirectoryLdapAuthenticationProvider adProvider)
            throws Exception {

        http
            .authenticationProvider(adProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class ExampleApi {

        @GetMapping("/public")
        String publicEndpoint() {
            return "Service running";
        }

        @GetMapping("/me")
        Map<String, Object> currentUser(Authentication authentication) {
            return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            );
        }
    }
}
~~~

**Giải thích mã:**

1. `adAuthenticationProvider` tạo provider với domain và LDAP URL. `setConvertSubErrorCodesToExceptions(true)` bật việc chuyển một số AD sub-error code thành exception riêng để phía server có thể phân biệt nguyên nhân. Hai thuộc tính JNDI cấu hình timeout kết nối/đọc (mili-giây) để tránh chờ vô hạn do mạng.
2. `filterChain` **đăng ký provider trực tiếp** với `HttpSecurity`, cho phép `/public` và yêu cầu xác thực cho URL khác. `httpBasic` nhận HTTP Basic credentials và chuyển cho hệ thống `AuthenticationManager`. Đăng ký rõ ràng tránh phụ thuộc việc Spring Boot có tự phát hiện bean provider trong từng cấu hình hay không.
3. `/me` trả về tên principal cùng danh sách authorities để học cách AD group mapping xuất hiện ở ứng dụng. Trong ứng dụng sản xuất, chỉ công khai dữ liệu này cho người dùng hoặc đội vận hành được phép; không tự tạo API tiết lộ toàn bộ nhóm nội bộ.
4. `HttpStatus` không được dùng trong ví dụ, có thể bỏ import; kết quả HTTP được Spring Security và Spring MVC quyết định. Chính LDAP provider xác minh credentials, còn controller chỉ chạy khi xác thực thành công.

> Ví dụ dùng HTTP Basic để nhìn rõ cơ chế AD bind. Nếu triển khai cho người dùng thật, ứng dụng phải dùng **HTTPS từ client đến ứng dụng**, **LDAPS/TLS từ ứng dụng đến DC**, kiểm soát timeout và log; không gửi password qua HTTP công khai.

### 5.4. Chạy ứng dụng và kiểm tra

Trong thư mục chứa `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

Có Maven Wrapper thì dùng `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`).

Kiểm tra route công khai:

~~~bash
curl -i http://127.0.0.1:8080/public
~~~

**Kết quả mong đợi:** HTTP `200 OK`, body:

~~~text
Service running
~~~

Kiểm tra route bảo vệ khi chưa gửi Basic credentials:

~~~bash
curl -i http://127.0.0.1:8080/me
~~~

**Kết quả mong đợi:** HTTP `401 Unauthorized` kèm `WWW-Authenticate: Basic ...` (nội dung chi tiết header do framework quyết định).

Kiểm tra AD login trên **máy phát triển**, dùng username thuộc AD đã cấu hình. Với `curl -u alice`, curl sẽ hỏi password tương tác để không cần viết password vào lịch sử lệnh:

~~~bash
curl -i -u alice http://127.0.0.1:8080/me
~~~

Trên Windows PowerShell dùng `curl.exe` để tránh alias của `Invoke-WebRequest`. Nếu account/password chính xác, kết nối TLS đến DC hoạt động và search user thành công, mong đợi HTTP `200 OK` và JSON có trường `name`, `authorities`; **giá trị cụ thể phụ thuộc user và các nhóm AD thật**. Nếu credentials sai, thường là HTTP `401 Unauthorized`, do entry point của HTTP Basic tạo phản hồi.

**Không đưa password vào lệnh** như `curl -u alice:myPassword` trên máy dùng chung và không gửi HTTP Basic qua mạng bên ngoài loopback khi chưa bật HTTPS.

### 5.5. Thử quyền theo nhóm

Sau khi xem danh sách `authorities` thực tế ở `/me`, bạn có thể thêm một rule trước `anyRequest()`:

~~~java
.requestMatchers("/admin/**").hasAuthority("TEN_AUTHORITY_THUC_TE")
~~~

Đây chỉ là **đoạn cấu hình minh họa**; thay tên authority bằng kết quả đã xác nhận trong AD và mapper. Nếu xác thực thành công nhưng thiếu quyền, yêu cầu thường nhận HTTP `403 Forbidden`. Đây là **authorization failure**, khác với LDAP bind thất bại dẫn tới `401`.

## 6. Cơ chế xử lý lỗi Active Directory

AD có thể trả LDAP error `49` (invalid credentials) kèm **sub-error code** trong thông điệp của LDAP bind. Provider có khả năng phân loại một số mã để log và (khi bật) chuyển thành exception của Spring Security:

| AD sub-code (hex) | Tình huống thường gặp | Exception khi bật chuyển đổi |
| --- | --- | --- |
| `525` | Không tìm thấy user | `BadCredentialsException` |
| `52e` | Password/credentials không đúng | `BadCredentialsException` |
| `530` | Đăng nhập bị hạn chế bởi thời gian | `BadCredentialsException` |
| `532` | Password hết hạn | `CredentialsExpiredException` |
| `533` | Tài khoản bị vô hiệu hóa | `DisabledException` |
| `701` | Tài khoản hết hạn | `AccountExpiredException` |
| `773` | Tài khoản phải đổi/reset password | `BadCredentialsException` trong ánh xạ mặc định |
| `775` | Tài khoản bị khóa | `LockedException` |

Các mã trên là **hexadecimal AD diagnostic**, không phải mã HTTP. Ánh xạ exception kể trên theo cách hiện thực của `ActiveDirectoryLdapAuthenticationProvider` trong dòng Spring Security 6.x; không phải mọi mã đều có một exception riêng. Khi `convertSubErrorCodesToExceptions=false` (mặc định), bind bị từ chối thường được biểu diễn bằng `BadCredentialsException`. Mã trả về còn phụ thuộc cấu hình AD, phiên bản DC và thông điệp thực tế; không thể đảm bảo lúc nào cũng có sub-code parse được.

Vì sao không nên trả chi tiết lỗi cho người đăng nhập?

- Thông báo `user không tồn tại` hoặc `account bị khóa` cho mọi client có thể làm lộ trạng thái tài khoản.
- Giao diện public thường nên trả thông điệp chung kiểu “Thông tin đăng nhập không hợp lệ”; phía server ghi nhật ký và thống kê có phân quyền.
- Quá nhiều lần đăng nhập sai có thể khiến tài khoản AD bị khóa theo policy. Hãy thêm rate limiting và giảm các retry tự động không cần thiết.

**Lỗi hệ thống khác lỗi credentials:** hết thời gian chờ mạng, DC không truy cập được, lỗi chứng thư TLS và search root/filter sai phải được điều tra riêng. Không tự kết luận mọi `BadCredentialsException` đồng nghĩa password nhập sai, bởi search sau bind cũng có thể thất bại.

## 7. Các tình huống cấu hình AD phổ biến

### 7.1. Đăng nhập bằng username ngắn

Ứng dụng chỉ chấp nhận `alice`, domain là `corp.example.com`; constructor 2 tham số thường đủ:

~~~java
var provider = new ActiveDirectoryLdapAuthenticationProvider(
    "corp.example.com",
    "ldaps://dc1.corp.example.com:636/"
);
~~~

Với filter mặc định, provider bind dưới tên `alice@corp.example.com` và tìm user có `userPrincipalName` tương ứng.

### 7.2. AD dùng sAMAccountName hoặc UPN không khớp

Một số môi trường có `userPrincipalName` khác quy ước `username@domain`. Nếu bind bằng principal do provider tạo vẫn được AD chấp nhận nhưng search theo UPN không thấy entry, filter có thể đổi sang `sAMAccountName`:

~~~java
provider.setSearchFilter(
    "(&(objectClass=user)(sAMAccountName={1}))"
);
~~~

Điều kiện: UI cung cấp username ngắn phù hợp với `sAMAccountName`. Việc đổi filter chỉ thay **bước tra cứu entry**, không sửa nguyên tắc tạo principal của **bước bind**. Nếu bind không đúng do hậu tố UPN khác domain, hãy làm rõ định dạng login và cấu hình domain/root DN trước.

### 7.3. Cần search root khác domain mặc định

Nếu LDAP base của môi trường là `DC=example,DC=org`, hãy chỉ định rõ:

~~~java
var provider = new ActiveDirectoryLdapAuthenticationProvider(
    "corp.example.com",
    "ldaps://dc1.corp.example.com:636/",
    "DC=example,DC=org"
);
~~~

Đây là cấu hình **minh họa**, chỉ hợp lệ khi root DN thực tế chứa user cần tìm và AD/DC cho phép tra cứu theo base đó. Root DN không thay đổi domain dùng cho bind.

### 7.4. Nhiều DC, nhiều domain hoặc forest

Một domain thường có nhiều DC. URL cần theo định dạng JNDI hỗ trợ và phải được kiểm chứng với cơ chế dự phòng thực tế; tránh giả định provider tự khám phá tất cả DC. Khi tổ chức có nhiều domain hoặc forest, xác định rõ UPN suffix, trust, root DN/search scope, và từng yêu cầu cấp quyền; đôi khi cần nhiều provider hoặc một chiến lược định tuyến tài khoản được thiết kế riêng.

### 7.5. Group lồng nhau

User có thể nằm trong nhóm A, nhóm A thuộc B. Nếu ứng dụng chỉ đọc `memberOf` trực tiếp, việc user “có B” theo chính sách AD không có nghĩa `GrantedAuthority` cho B luôn xuất hiện. Cần kiểm tra quyền thực tế và, nếu bắt buộc, triển khai truy vấn/giải nhóm có xét nested membership theo mô hình AD, thay vì nới lỏng các rule bảo mật để “chạy được”.

## 8. Lưu ý bảo mật và vận hành

**Bảo vệ credentials khi truyền tải.** LDAP bind dạng simple có gửi credentials tới DC. Ưu tiên `ldaps://...:636/` hoặc kênh TLS được tổ chức xác nhận. JVM phải tin cậy CA phát hành chứng thư của DC; không tắt kiểm chứng chứng thư để “sửa lỗi”. HTTPS của client→app và LDAPS của app→DC là **hai kênh khác nhau**, phải bảo vệ cả hai.

**Không lưu password AD trong DB ứng dụng.** Provider dùng password để xác minh online, không cần copy mật khẩu, ghi ra log hoặc hash lưu song song. Dùng `PasswordEncoder` cho local users là một bài toán khác.

**Giới hạn truy cập và lỗi hạ tầng.** Cấu hình timeout, giám sát trạng thái DC, cảnh báo tỷ lệ bind lỗi, DNS/TLS, và kế hoạch failover. Không retry sai mật khẩu liên tục vì có thể khóa account theo chính sách AD.

**Giới hạn thông tin lộ ra ngoài.** Không trả stack trace, raw AD diagnostic, DN đầy đủ hoặc danh sách nhóm nhạy cảm cho client công khai. Audit cần phân quyền, che dữ liệu nhạy cảm và quy định retention.

**Cơ chế authorization rõ ràng.** Đăng nhập thành công chỉ chứng minh identity. Gắn quyền ứng dụng vào nhóm AD đúng cách; dùng nguyên tắc ít quyền nhất, kiểm tra nested/primary groups, và rà soát quyền khi chuyển nhóm hoặc vô hiệu hóa user.

**MFA, SSO, Entra ID.** LDAP bind chỉ làm xác thực username/password với AD DS theo khả năng mà domain cho phép. Muốn SSO theo trình duyệt, Kerberos, SAML hoặc OIDC/Microsoft Entra ID phải dùng giao thức và tích hợp tương ứng; không kỳ vọng `ActiveDirectoryLdapAuthenticationProvider` tự cung cấp các chức năng đó.

## 9. Chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| 401 cho tất cả user | URL/DC sai, bind bị từ chối, domain/UPN khác cấu hình | Kiểm tra network/TLS, danh tính có thể bind, UPN và AD log |
| Bind hợp lệ nhưng xác thực vẫn lỗi | Search filter không khớp, root DN sai, user không đọc được | Kiểm tra filter mặc định, `{0}`/`{1}`, base và quyền đọc directory |
| Có 200 từ `/me` nhưng route quản trị trả 403 | Authorities không khớp policy, nested group hoặc primary group không được map | Quan sát authorities thực tế và logic `hasRole`/`hasAuthority` |
| `SSLHandshakeException`, lỗi certificate | DC certificate/CA/hostname không được JVM tin cậy | Xác minh chain, DNS, JVM truststore; không disable TLS |
| Kết nối chậm hoặc timeout | DNS, firewall, DC quá tải, routing, timeout JNDI | Kiểm tra port 636, thời gian kết nối/đọc và DC health |
| Account bị lock sau thử nhiều lần | Nhiều request dùng password cũ, retry/login loop | Xem AD lockout policy, nhật ký application và client |
| Input `CORP\alice` thất bại | Provider không được cấu hình để chuyển cú pháp NetBIOS sang UPN thích hợp | Chuẩn hóa login có kiểm chứng hoặc dùng UPN đúng |
| “Mọi người đều đăng nhập được vào /admin” | Policy đang chỉ có `authenticated()` | Thêm rule authorization theo authority được xác minh |

**Quy trình chẩn đoán hữu ích:** kiểm tra trước truy cập mạng và TLS tới DC; sau đó kiểm tra principal dùng để bind; tiếp theo kiểm tra search filter/base; cuối cùng xem authorities và policy. Các bước diễn ra theo đúng thứ tự xử lý của provider, giúp tránh nhầm lỗi xác thực với lỗi cấp quyền.

## 10. Phân biệt với các lựa chọn khác của Spring Security

| Giải pháp | Khi phù hợp |
| --- | --- |
| `ActiveDirectoryLdapAuthenticationProvider` | Ứng dụng Servlet cần bind credentials với AD DS và dùng convention UPN/`memberOf` của AD. |
| `LdapAuthenticationProvider` + `BindAuthenticator` | LDAP tổng quát hoặc khi muốn tự xác định DN pattern, search/role populator chi tiết. |
| In-memory/JDBC UserDetailsService | Tài khoản do chính ứng dụng quản lý, không cần hỏi AD. |
| Kerberos/SPNEGO | Tình huống xác thực doanh nghiệp tích hợp Windows/SSO bằng Kerberos. |
| OAuth2 Login/OIDC hoặc SAML với IdP | Federated login/SSO, gồm tích hợp IdP hiện đại như Microsoft Entra ID. |

Class AD ở bài này là một `AuthenticationProvider` **đồng bộ** (LDAP/JNDI). Trong ứng dụng **Spring WebFlux/reactive**, không tự đưa thao tác bind blocking lên event-loop; cần phương án tích hợp xử lý blocking đúng cách hoặc thiết kế xác thực phù hợp reactive. Đừng nhầm nó với một `ReactiveAuthenticationManager`.

## 11. Câu hỏi tự kiểm tra

1. Vì sao username `alice` có thể được bind dưới tên `alice@corp.example.com`?
2. Sau khi bind thành công, vì sao provider vẫn cần search user và có thể trả lỗi?
3. Filter mặc định khác thế nào so với filter `(sAMAccountName={1})`?
4. `memberOf` cung cấp thông tin gì, và tại sao nested group có thể gây sai lệch quyền?
5. Trường hợp nào trả 401, trường hợp nào thường trả 403?
6. Vì sao lỗi `532` và `775` có thể xuất hiện dưới exception khác nhau khi bật chuyển mã AD?
7. Vì sao dùng LDAPS chưa đủ nếu đường truyền client→ứng dụng vẫn dùng HTTP?
8. Tại sao đăng nhập thành công vào AD không tự biến ứng dụng thành hệ thống SSO Windows?

## 12. Tài liệu chính thức để tra cứu

- [Spring Security — LDAP Authentication (mục Active Directory)](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security — ActiveDirectoryLdapAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html)
- [Spring Security — DefaultActiveDirectoryAuthoritiesPopulator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/DefaultActiveDirectoryAuthoritiesPopulator.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Microsoft Learn — LDAP channel binding in Active Directory](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding)
