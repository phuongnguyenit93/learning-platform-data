# UserDetailsContextMapper và principal từ thuộc tính directory (LDAP / Active Directory)

## 1. Từ LDAP entry đến principal của Spring Security

Trong doanh nghiệp, danh tính người dùng có thể nằm trong **LDAP directory** hoặc **Microsoft Active Directory (AD)**. Một bản ghi directory có các thuộc tính như tên đăng nhập, tên hiển thị, email, đơn vị, distinguished name (DN) và thông tin nhóm. Sau khi người dùng được xác thực, ứng dụng Spring Security cần biến dữ liệu đó thành **principal** phù hợp để mã nghiệp vụ sử dụng.

`UserDetailsContextMapper` là điểm mở rộng giúp thực hiện phép biến đổi:

```text
Username + mật khẩu người dùng gửi
        |
        v
LDAP AuthenticationProvider / AD AuthenticationProvider
        |
        | 1. Bind / kiểm tra thông tin xác thực với directory
        | 2. Đọc LDAP entry và lấy GrantedAuthority
        v
DirContextOperations + username + authorities
        |
        | 3. UserDetailsContextMapper.mapUserFromContext(...)
        v
UserDetails (principal của Authentication)
        |
        v
SecurityContext --> ứng dụng đọc principal / authorities
```

**Phân biệt ba trách nhiệm quan trọng:**

- **Authentication**: LDAP bind, LDAP password comparison hoặc cơ chế riêng của AD xác minh credential. Mapper không kiểm tra mật khẩu.
- **Authority loading**: `LdapAuthoritiesPopulator`, bộ nạp quyền của AD hoặc cấu hình tương ứng tính danh sách `GrantedAuthority`.
- **Principal mapping**: `UserDetailsContextMapper` quyết định dạng `UserDetails` và các thông tin directory có thể sử dụng sau đăng nhập.

Do đó `UserDetailsContextMapper` **không phải `UserDetailsService`**, cũng không phải một cơ chế cấp quyền mặc định. Spring Security LDAP bind thường không đọc được mật khẩu từ directory để ứng dụng tự so khớp như `DaoAuthenticationProvider`.

## 2. Giao diện UserDetailsContextMapper

Package: `org.springframework.security.ldap.userdetails.UserDetailsContextMapper`.

```java
public interface UserDetailsContextMapper {

    UserDetails mapUserFromContext(
            DirContextOperations ctx,
            String username,
            Collection<? extends GrantedAuthority> authorities);

    void mapUserToContext(
            UserDetails user,
            DirContextAdapter ctx);
}
```

Đoạn trên trình bày chữ ký API, không phải file Java độc lập; các kiểu lần lượt thuộc `org.springframework.ldap.core`, `org.springframework.security.core` và `org.springframework.security.core.userdetails`.

**`mapUserFromContext(...)`**:

1. `ctx`: biểu diễn entry đã truy xuất từ directory. Đọc thuộc tính bằng `getStringAttribute("mail")`, `getStringAttributes("memberOf")`, `getObjectAttribute(...)`, v.v.
2. `username`: tên đăng nhập được truyền đến provider/mapper. Đây không nhất thiết là khóa định danh vĩnh viễn của một người; tên có thể được chuẩn hóa hoặc đổi theo chính sách directory.
3. `authorities`: quyền đã được thành phần nạp quyền cung cấp. Nên bảo toàn hoặc lọc theo chính sách rõ ràng; không tự nâng quyền từ trường mô tả thiếu kiểm soát.
4. Kết quả: một `UserDetails`; Spring Security LDAP provider có thể đặt object này vào `Authentication.getPrincipal()` sau khi xác thực thành công.

**`mapUserToContext(...)`** là chiều ngược lại: điền thuộc tính từ một `UserDetails` vào `DirContextAdapter`, thường liên quan đến quản lý user như `LdapUserDetailsManager`. **Đăng nhập bằng LDAP không tự động gọi method này để ghi người dùng về directory.** Nếu mapper chỉ hỗ trợ xác thực và cố ý không hỗ trợ chỉnh sửa directory, nên báo lỗi rõ ràng khi method này bị gọi; đừng âm thầm ghi sai thuộc tính.

Các mapper Spring Security cung cấp sẵn gồm `LdapUserDetailsMapper`, `InetOrgPersonContextMapper` và `PersonContextMapper`. Hãy ưu tiên những kiểu sẵn có khi không cần thuộc tính riêng; chỉ viết custom mapper nếu mô hình principal của ứng dụng đòi hỏi thêm trường hoặc quy tắc rõ ràng.

## 3. Các thuộc tính directory thường ánh xạ vào principal

Tên thuộc tính phụ thuộc schema LDAP/AD của tổ chức; cùng một ý nghĩa có thể có tên khác nhau.

| Thuộc tính | Thường gặp ở đâu | Cách dùng trong principal | Lưu ý |
| --- | --- | --- | --- |
| `uid` | LDAP, `inetOrgPerson` | Tên đăng nhập cục bộ | Không mặc định có trong AD; có thể đổi tên |
| `cn` | LDAP/AD | Common name, tên của entry | Không đảm bảo duy nhất trên toàn hệ thống |
| `displayName` | LDAP/AD | Tên hiển thị trong giao diện | Chỉ là metadata, không cấp quyền |
| `givenName`, `sn` | LDAP/AD | Tên và họ | Có thể thiếu hoặc nhiều cách định dạng |
| `mail` | LDAP/AD | Email để hiển thị/liên hệ | Có thể null, thay đổi hoặc không duy nhất |
| `department` / `departmentNumber` | Tùy schema | Thông tin bộ phận | Định nghĩa tổ chức cụ thể, không tự suy thành role |
| `sAMAccountName` | AD | Tên đăng nhập kiểu tương thích Windows | Thường chỉ duy nhất trong một domain |
| `userPrincipalName` | AD | Tên đăng nhập dạng `user@domain` | Định dạng giống email nhưng không nhất thiết là email |
| `memberOf` | LDAP/AD tùy schema | Dữ liệu quan hệ nhóm | Đa trị; có thể chưa biểu diễn toàn bộ nhóm lồng nhau |
| DN / `distinguishedName` | LDAP/AD | Vị trí entry trong cây directory | DN có thể đổi khi di chuyển/rename entry |
| `objectGUID` hoặc `objectSid` | AD | Định danh phục vụ liên kết hệ thống khi phù hợp | Có biểu diễn nhị phân/đặc thù, không ép thẳng thành chuỗi UTF-8 |

Ví dụ entry LDAP (dữ liệu minh họa):

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Pham
sn: Pham
givenName: Lan
displayName: Lan Pham
mail: lan@example.org
departmentNumber: 42
```

Kết quả có thể là một principal chứa:

```text
username    = lan
displayName = Lan Pham
email       = lan@example.org
authorities = [ROLE_READER]
```

Trong đó `ROLE_READER` là quyền **được provider/policy cấp**, không suy ra từ `mail` hay `departmentNumber` trong mẫu.

### Đọc thuộc tính bằng Spring LDAP

`DirContextOperations.getStringAttribute(name)` trả về một giá trị chuỗi đầu tiên hoặc `null` khi không có. Với thuộc tính đa trị như `memberOf`, sử dụng `getStringAttributes(name)` nếu cần toàn bộ các giá trị; kết quả có thể là `null` khi thuộc tính không tồn tại. Giá trị nhị phân như một số dạng ID trong AD cần API và phép chuyển đổi phù hợp.

`getDn()` của `DirContextAdapter` thể hiện DN **tương đối so với base**; khi cần tên namespace đầy đủ, xem `getNameInNamespace()` và ngữ cảnh lookup thực tế. Tránh ghép chuỗi DN thủ công làm khóa principal. Các trường thường cần optional/null-handling vì quyền truy cập LDAP, schema và bộ lọc truy vấn có thể làm thiếu thuộc tính.

## 4. Ví dụ Java 17+ hoàn chỉnh: map entry directory thành custom principal

Ví dụ này **không cần LDAP server**. Ta tạo `DirContextAdapter` giả lập dữ liệu đã được đọc, truyền danh sách authorities có sẵn rồi quan sát `UserDetails` được tạo ra. Như vậy có thể kiểm thử chính xác logic mapper mà không phụ thuộc mạng hoặc AD.

Tạo project Gradle tối giản:

```groovy
// build.gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-ldap:6.5.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.DirectoryMapperDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Security LDAP mang các dependency cần thiết cho mapper và Spring LDAP. Với ứng dụng Spring Boot thực tế, hãy dùng BOM/version management tương ứng của Boot thay vì tự ghép nhiều phiên bản Spring khác nhau.

Tạo file `src/main/java/demo/DirectoryMapperDemo.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.ldap.userdetails.UserDetailsContextMapper;

public final class DirectoryMapperDemo {

    private DirectoryMapperDemo() {}

    // Principal bất biến: dữ liệu ứng dụng cần sau khi LDAP xác thực xong.
    public record DirectoryPrincipal(
            String username,
            String displayName,
            String email,
            Collection<? extends GrantedAuthority> permissions
    ) implements UserDetails {

        public DirectoryPrincipal {
            Objects.requireNonNull(username, "username");
            Objects.requireNonNull(permissions, "permissions");
            permissions = List.copyOf(permissions);
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return permissions;
        }

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return null; // Đã xác thực bằng LDAP bind; không lưu password vào principal.
        }

        @Override
        public boolean isAccountNonExpired() {
            return true;
        }

        @Override
        public boolean isAccountNonLocked() {
            return true;
        }

        @Override
        public boolean isCredentialsNonExpired() {
            return true;
        }

        @Override
        public boolean isEnabled() {
            return true;
        }
    }

    // Chỉ ánh xạ dữ liệu đọc sau xác thực; không thực hiện cập nhật LDAP.
    public static final class DirectoryUserMapper implements UserDetailsContextMapper {

        @Override
        public UserDetails mapUserFromContext(
                DirContextOperations ctx,
                String username,
                Collection<? extends GrantedAuthority> authorities) {

            Objects.requireNonNull(ctx, "ctx");
            Objects.requireNonNull(username, "username");
            Objects.requireNonNull(authorities, "authorities");
            if (username.isBlank()) {
                throw new IllegalArgumentException("Missing login username");
            }

            String displayName = valueOr(
                    ctx.getStringAttribute("displayName"), username);
            String email = valueOr(ctx.getStringAttribute("mail"), "");

            // Giữ danh sách quyền đã được provider chuẩn bị;
            // tuyệt đối không tự cấp ADMIN dựa vào thuộc tính hiển thị.
            return new DirectoryPrincipal(username, displayName, email, authorities);
        }

        @Override
        public void mapUserToContext(UserDetails user, DirContextAdapter ctx) {
            throw new UnsupportedOperationException(
                    "Read-only authentication mapper");
        }

        private static String valueOr(String value, String fallback) {
            return value == null || value.isBlank() ? fallback : value.trim();
        }
    }

    public static void main(String[] args) {
        var entry = new DirContextAdapter(
                "uid=lan,ou=people,dc=example,dc=org");
        entry.setAttributeValue("uid", "lan");
        entry.setAttributeValue("displayName", "Lan Pham");
        entry.setAttributeValue("mail", "lan@example.org");

        var authorities = List.of(
                new SimpleGrantedAuthority("ROLE_READER"));

        var mapper = new DirectoryUserMapper();
        var user = (DirectoryPrincipal)
                mapper.mapUserFromContext(entry, "lan", authorities);

        System.out.println("username=" + user.getUsername());
        System.out.println("displayName=" + user.displayName());
        System.out.println("email=" + user.email());
        System.out.println("authorities=" + user.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority).toList());
    }
}
```

Từ thư mục có `build.gradle`, chạy `gradle run` (hoặc `./gradlew run` / `gradlew.bat run` nếu dự án có Gradle Wrapper). Phần **stdout của chương trình** là:

```text
username=lan
displayName=Lan Pham
email=lan@example.org
authorities=[ROLE_READER]
```

Đây là kết quả xác định từ dữ liệu mẫu và các lệnh `println`; Gradle có thể hiển thị thêm log build ngoài stdout của chương trình.

**Giải thích những quyết định trong ví dụ:**

- Dùng `username` đã được mapper nhận thay vì ép `displayName` thành login. Hệ thống thật cần chính sách canonical username và stable ID rõ ràng.
- `getPassword()` trả `null` vì ví dụ dùng cơ chế **LDAP bind** và không đọc password. Đừng tái sử dụng principal này với `DaoAuthenticationProvider` vốn cần password từ `UserDetails` để kiểm tra.
- Quyền trong `permissions` được sao chép bất biến, tránh code ngoài vô tình thay danh sách quyền sau khi tạo.
- Bốn cờ trạng thái tài khoản đang cố định `true` **chỉ để cô lập việc học mapping**; trong ứng dụng thật, chính sách vô hiệu hóa/khóa/hết hạn phải được xác định từ directory và provider, không dựa vào các giá trị giả định này.
- `mapUserToContext` từ chối ghi rõ ràng. Nếu ứng dụng thực sự có chức năng cập nhật LDAP, cần mapper ghi có whitelist thuộc tính, phân quyền và kiểm thử riêng.
- Các trường bổ sung như email và display name có thể dùng để hiển thị; không được lấy làm bằng chứng định danh hoặc lý do tự cấp quyền.

## 5. Test các trường thiếu, quyền và chế độ chỉ đọc

Tạo file `src/test/java/demo/DirectoryMapperDemoTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class DirectoryMapperDemoTest {

    private final DirectoryMapperDemo.DirectoryUserMapper mapper =
            new DirectoryMapperDemo.DirectoryUserMapper();

    @Test
    void mapsExpectedAttributesAndPreservesAuthorities() {
        var entry = new DirContextAdapter();
        entry.setAttributeValue("displayName", "  Lan Pham  ");
        entry.setAttributeValue("mail", "lan@example.org");

        var user = (DirectoryMapperDemo.DirectoryPrincipal)
                mapper.mapUserFromContext(entry, "lan",
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        assertEquals("lan", user.getUsername());
        assertEquals("Lan Pham", user.displayName());
        assertEquals("lan@example.org", user.email());
        assertEquals("ROLE_READER",
                user.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void missingOptionalAttributesDoNotCreateFakeIdentity() {
        var user = (DirectoryMapperDemo.DirectoryPrincipal)
                mapper.mapUserFromContext(new DirContextAdapter(), "lan", List.of());

        assertEquals("lan", user.getUsername());
        assertEquals("lan", user.displayName());
        assertEquals("", user.email());
        assertTrue(user.getAuthorities().isEmpty());
    }

    @Test
    void writeBackIsExplicitlyUnsupported() {
        var user = mapper.mapUserFromContext(
                new DirContextAdapter(), "lan", List.of());

        assertThrows(UnsupportedOperationException.class,
                () -> mapper.mapUserToContext(user, new DirContextAdapter()));
    }
}
```

Chạy `gradle test` hoặc `./gradlew test` khi có wrapper. Ba test lần lượt xác nhận ánh xạ thuộc tính, fallback khi dữ liệu thiếu và việc không cho ghi directory. **Lưu ý:** đây là unit test mapper, chưa phải integration test xác thực LDAP/AD thực; nó không kiểm chứng TLS, bind, lookup group hay trạng thái tài khoản trong server.

## 6. Gắn mapper vào Spring Security LDAP hoặc AD

Mapper chỉ được dùng trong quy trình đăng nhập thật khi được gắn vào đúng `AuthenticationProvider` hoặc factory tạo `AuthenticationManager`.

### 6.1. LDAP bind dùng LdapBindAuthenticationManagerFactory

Với Spring Security 6.x, factory này có `setUserDetailsContextMapper(...)` kế thừa từ `AbstractLdapAuthenticationManagerFactory`.

```java
// Mảnh cấu hình bên trong một @Configuration của ứng dụng Spring MVC:
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {

    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    factory.setUserDetailsContextMapper(
            new DirectoryMapperDemo.DirectoryUserMapper());

    return factory.createAuthenticationManager();
}
```

Imports liên quan:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
```

Đoạn này **chỉ là mảnh tích hợp**, cần một `BaseLdapPathContextSource` được cấu hình URL/base DN, tài khoản truy vấn (nếu cần), TLS và một Spring Security filter chain sử dụng authentication manager đúng cách. `(uid={0})` chỉ có ý nghĩa nếu directory thực dùng `uid`; AD thường dùng thuộc tính tìm kiếm khác. Cần cấu hình `LdapAuthoritiesPopulator` nếu ứng dụng lấy quyền từ nhóm và không chấp nhận chỉ có danh tính mà không có roles.

**Luồng kết quả:** sau khi `BindAuthenticator` xác thực và lấy dữ liệu user, factory/provider gọi mapper; `Authentication.getPrincipal()` là `DirectoryPrincipal` nếu cấu hình và xác thực thành công.

### 6.2. Với Active Directory

```java
// Ví dụ đặt trong @Configuration đã có DirectoryUserMapper:
@Bean
ActiveDirectoryLdapAuthenticationProvider adProvider() {
    var provider = new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org", "ldaps://ad.corp.example.org:636/");
    provider.setUserDetailsContextMapper(
            new DirectoryMapperDemo.DirectoryUserMapper());
    return provider;
}
```

Import: `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`.

AD provider có quy ước đăng nhập kiểu `userPrincipalName` (`user@domain`) và thường lấy authorities từ `memberOf`. Việc đổi mapper **không thay cơ chế bind**, cũng không tự động bảo đảm nested group hay quyền miền liên kết đều được suy ra; nếu cần, cấu hình authority populator/mapper và test với dữ liệu thực. URL/domain trên đây là ví dụ và không thể dùng để đăng nhập nếu không có AD thực.

## 7. Đọc principal ở tầng ứng dụng

Sau khi HTTP request đã được xác thực, mã controller trong **Spring MVC/Servlet** có thể lấy principal qua `@AuthenticationPrincipal` hoặc từ `Authentication`. Khi provider sử dụng custom mapper ở trên, kiểu runtime thường là `DirectoryPrincipal`.

```java
// Mảnh handler minh họa, chỉ hoạt động khi hệ thống đã cấu hình LDAP provider.
@GetMapping("/me")
public Map<String, String> me(
        @AuthenticationPrincipal DirectoryMapperDemo.DirectoryPrincipal principal) {
    return Map.of(
            "username", principal.getUsername(),
            "displayName", principal.displayName(),
            "email", principal.email());
}
```

Imports cho mảnh code này: `java.util.Map`, `org.springframework.web.bind.annotation.GetMapping`, `org.springframework.security.core.annotation.AuthenticationPrincipal`. Vì ví dụ mapping chuyển missing email thành chuỗi rỗng, `Map.of` không nhận giá trị null. Trong ứng dụng thật, giới hạn field nào được trả ra API theo quyền và mục đích sử dụng; tránh lộ DN, nhóm nội bộ hoặc dữ liệu nhân sự không cần thiết.

Đừng ép toàn bộ `Authentication.getPrincipal()` về custom class nếu ứng dụng có nhiều cơ chế login; khi có JWT/OIDC hay anonymous, kiểu principal có thể khác. Với `@AuthenticationPrincipal`, hãy giới hạn handler bằng security chain/chính sách tương ứng hoặc xử lý kiểu một cách an toàn.

**Về WebFlux:** Spring Security LDAP provider/JNDI thường dùng API đồng bộ. Không tự gọi LDAP blocking trực tiếp trong event loop WebFlux; nếu cần reactive authentication phải có thiết kế chuyển thực thi blocking phù hợp và quản lý context/security nhất quán. Mapper vẫn là khái niệm của mô-đun Spring Security LDAP, không tự biến việc lookup LDAP thành `Mono` hay `ReactiveUserDetailsService`.

## 8. Khi nào không cần custom mapper?

| Nhu cầu | Phương án |
| --- | --- |
| Chỉ cần username và authorities theo LDAP | Xem `LdapUserDetailsMapper` mặc định của provider |
| Cần principal theo `inetOrgPerson` như tên, địa chỉ, email | Xem `InetOrgPersonContextMapper` |
| Schema tương thích `person` | Xem `PersonContextMapper` |
| Cần trường nhân sự riêng, stable internal ID hoặc hạn chế dữ liệu nhạy cảm | Custom `UserDetailsContextMapper` được kiểm thử rõ |
| Chỉ muốn thêm/bớt role mà vẫn giữ kiểu principal hiện tại | Cấu hình `LdapAuthoritiesPopulator` / `GrantedAuthoritiesMapper`; chưa chắc cần đổi principal mapper |
| Muốn sửa tài khoản trong LDAP | Cân nhắc `LdapUserDetailsManager` và mapping hai chiều; bảo vệ quyền ghi tách biệt |

`LdapUserDetailsMapper` có các tùy chọn như `setPasswordAttributeName`, `setRoleAttributes`, `setRolePrefix` và `setConvertToUpperCase`; chúng hữu ích nếu schema và chính sách vai trò phù hợp. Tuy nhiên, **không đọc hay giữ mật khẩu chỉ để làm phong phú principal** khi đang dùng LDAP bind.

## 9. Lỗi phổ biến và cách phân tích

**Lỗi 1 — Mapper không chạy dù đã khai báo `@Bean`.** Khai báo bean không đồng nghĩa mọi LDAP provider tự sử dụng bean đó. Cần kiểm tra cấu hình có gọi `setUserDetailsContextMapper(...)`, LDAP provider/factory được wiring vào authentication manager đúng cách, và request dùng đúng filter chain.

**Lỗi 2 — Mapper được gọi nhưng `mail`, `displayName` đều null.** Kiểm tra schema, bộ lọc user search, quyền đọc thuộc tính và `attributesToReturn` của quá trình lookup. AD có thể dùng thuộc tính tên khác. Nếu thiếu thông tin tùy chọn, áp dụng fallback an toàn; không đoán giá trị email từ login mà không có quy tắc xác thực.

**Lỗi 3 — Principal mất role sau khi map.** Thông số `authorities` là danh sách được cấp bởi thành phần lấy quyền; nếu custom mapper bỏ qua nó, ứng dụng có thể gặp 403 dù xác thực thành công. Không sửa lỗi bằng cách gán `ROLE_ADMIN` mặc định. Kiểm tra group search/authority loading và ràng buộc role.

**Lỗi 4 — Mapping `memberOf` thành một role bằng `getStringAttribute`.** Thuộc tính nhóm có thể đa trị và chứa DN, không phải trực tiếp tên quyền Spring. Cần xử lý nhiều giá trị, nested group theo yêu cầu, quy tắc mapping được kiểm soát và kiểm thử trường hợp group lạ hoặc group không còn tồn tại.

**Lỗi 5 — Dùng email, `cn` hoặc tên hiển thị làm khóa user vĩnh viễn.** Chúng có thể đổi, trùng hoặc bị cập nhật bởi quy trình nhân sự. Với AD, định danh chuyên dùng như GUID/SID có kiểu biểu diễn đặc biệt; việc lựa chọn khóa phải nhất quán với phạm vi domain/forest, quy tắc liên kết tài khoản và yêu cầu bảo mật.

**Lỗi 6 — Tự kiểm tra password trong mapper.** `UserDetailsContextMapper` là bước tạo principal từ entry đã lấy; không đọc password người dùng hay `userPassword` để so khớp lần nữa. Điều này cũng tránh lộ hashed secret, plain password hoặc credential được trao sai chỗ.

**Lỗi 7 — Đánh đồng trạng thái tài khoản với các cờ `true` trong demo.** Active Directory có account disabled, expired, locked, và lỗi bind/sub-error riêng. Ứng dụng thật phải dựa vào provider/chính sách directory được kiểm chứng; không coi việc mapper trả `isEnabled() == true` là bằng chứng AD account hợp lệ.

**Lỗi 8 — Muốn cập nhật LDAP nhưng mapper chỉ có chiều đọc.** `mapUserToContext` trong ví dụ cố ý ném `UnsupportedOperationException`. Nếu có nghiệp vụ quản lý user, xác định rõ thuộc tính được phép ghi, giao dịch/cơ chế rollback cần thiết, quyền service account và bảo vệ dữ liệu.

**Lỗi 9 — Xuất toàn bộ directory entry ra response hoặc log.** Entry có thể chứa email, số điện thoại, thuộc tính tổ chức và thông tin nhóm. Chỉ map các trường phục vụ nghiệp vụ đã được phép; không đưa credential/secret hoặc raw directory attributes vào log.

**Lỗi 10 — LDAP chạy qua kết nối không an toàn.** Cần LDAPS hoặc StartTLS phù hợp, xác thực chứng chỉ server, kiểm soát timeout/referral và phân quyền tài khoản bind. Mapper đúng chưa đủ để bảo vệ dữ liệu xác thực khi truyền qua mạng.

## 10. Quy trình thiết kế mapper trong dự án thật

1. Xác định schema LDAP/AD và **nguồn tin cậy** cho username, stable ID, tên hiển thị, email, account status, group membership.
2. Quyết định ứng dụng cần lưu những thuộc tính nào trong principal, mục đích sử dụng và mức độ nhạy cảm; tránh mang toàn bộ entry vào session/token.
3. Chọn `LdapUserDetailsMapper`/`InetOrgPersonContextMapper` có sẵn, chỉ viết custom mapper khi thật sự có hợp đồng khác.
4. Cấu hình provider/factory gọi mapper, đồng thời giữ cơ chế bind và nạp authorities phù hợp. Định nghĩa rõ đơn vị kiểm soát mapping nhóm → Spring roles.
5. Kiểm thử mapper độc lập với dữ liệu đầy đủ, thiếu, đa trị, đổi tên và quyền rỗng. Không tạo role từ thuộc tính thiếu tin cậy.
6. Kiểm thử tích hợp với directory thử nghiệm: đăng nhập hợp lệ/thất bại, locked/disabled account, quyền đọc attribute, membership thay đổi, session/cache, và API trả về thông tin được phép.
7. Với nhu cầu viết ngược LDAP, xây chức năng quản lý và kiểm soát quyền riêng; không để đường xác thực vô tình thực hiện thay đổi directory.

### Tài liệu chính thức

- Spring Security 6.5 — LDAP Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html
- `UserDetailsContextMapper` và các mapper có sẵn: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/ldap/userdetails/package-summary.html
- `LdapUserDetailsMapper` (API): https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/ldap/userdetails/LdapUserDetailsMapper.html
- `AbstractLdapAuthenticationManagerFactory` (API): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- `ActiveDirectoryLdapAuthenticationProvider` (API): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring LDAP — `DirContextAdapter` (API): https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html
