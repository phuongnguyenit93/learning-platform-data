# Phân biệt tầng truy cập dữ liệu với tầng xác thực và phân quyền

Trong ứng dụng Java sử dụng **Spring Data LDAP**, dịch vụ thư mục LDAP có thể vừa là nơi lưu hồ sơ người dùng vừa là nguồn kiểm tra tài khoản đăng nhập. Tuy cùng giao tiếp với một directory server, **truy cập dữ liệu**, **xác thực** và **phân quyền** là ba trách nhiệm khác nhau. Việc tách chúng rõ ràng giúp ứng dụng tránh nhầm lẫn giữa “tìm thấy một entry” với “người đó đã đăng nhập”, hoặc giữa “kết nối LDAP thành công” với “người dùng được phép xem dữ liệu”.

Bài này thuộc chủ đề **Spring Security** trong module `SPRING_DATA_LDAP`: tập trung vào ranh giới trách nhiệm giữa mô hình repository/`LdapTemplate`, phép kiểm tra danh tính và các quyết định cấp quyền. Kiến thức về DN, `objectClass`, schema, filter, CRUD và bảo mật kết nối được đặt vào bối cảnh một ứng dụng HTTP thực tế.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Chỉ ra thành phần nào **đọc/ghi entry LDAP**, thành phần nào **chứng thực thông tin đăng nhập**, và thành phần nào **cho phép hoặc từ chối một thao tác**.
- Phân biệt **DN của tài khoản dịch vụ dùng kết nối LDAP**, **DN của người dùng đăng nhập**, **DN của entry dữ liệu** và **authority/role của phiên đăng nhập**.
- Đọc luồng xử lý HTTP qua `SecurityFilterChain`, LDAP authentication provider, `SecurityContext` và repository.
- Cấu hình ví dụ Spring Boot + Spring Security + Spring Data LDAP theo cách giữ riêng xác thực và truy cập dữ liệu.
- Giải thích các tình huống trả về HTTP `401`, HTTP `403`, thiếu quyền LDAP và vì sao tìm kiếm thành công không đồng nghĩa đã xác thực.

## 2. Ba tầng thực sự làm gì?

| Tầng | Câu hỏi cần trả lời | Thành phần Spring thường gặp | Kết quả |
| --- | --- | --- | --- |
| **Truy cập dữ liệu (data access)** | “Đọc, tìm kiếm, tạo hoặc cập nhật entry nào trong cây LDAP?” | Spring Data LDAP `LdapRepository`, Spring LDAP `LdapTemplate`, `LdapContextSource`, entity `@Entry` | Entry, thuộc tính, danh sách kết quả hoặc lỗi LDAP. |
| **Xác thực (authentication)** | “Bên gửi request có thật sự là danh tính mà họ khai báo?” | Spring Security `AuthenticationManager`, LDAP authentication provider, bind authentication | Một `Authentication` hợp lệ hoặc lỗi xác thực. |
| **Phân quyền (authorization)** | “Danh tính đã xác thực có quyền làm hành động này không?” | `SecurityFilterChain`, `authorizeHttpRequests`, `@PreAuthorize`, `GrantedAuthority` | Cho phép hoặc từ chối truy cập tài nguyên/thao tác. |

Ba tầng liên hệ nhưng không thay thế cho nhau:

- `personRepository.findByUid("lan")` trả về entry chứng tỏ **đã tìm thấy dữ liệu**; nó không chứng minh người đang gọi API là `lan`.
- LDAP bind bằng mật khẩu hợp lệ chứng tỏ directory **chấp nhận một danh tính**; việc đó chưa chứng tỏ danh tính ấy được phép gọi `DELETE /api/people/lan`.
- `hasRole("ADMIN")` kiểm tra quyền trong Spring Security; nó không tự cấp cho tài khoản kết nối LDAP quyền ghi mà directory server chưa cho phép.

Khi nói “Spring Security tích hợp LDAP”, LDAP có thể đóng vai trò **nguồn xác thực và nhóm quyền**. Khi nói “Spring Data LDAP tích hợp LDAP”, LDAP đóng vai trò **nguồn dữ liệu có cấu trúc phân cấp**. Hai vai trò có thể dùng cùng máy chủ và schema, nhưng thực hiện các tác vụ khác nhau.

## 3. Ba loại danh tính và hai cơ chế kiểm soát quyền

Giả sử directory ví dụ có cây:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=lan
├── ou=groups
│   └── cn=DIRECTORY_READER
└── ou=services
    └── cn=app-reader
~~~

Các giá trị cần phân biệt:

| Giá trị | Ví dụ | Dùng khi nào? |
| --- | --- | --- |
| **DN tài khoản dịch vụ (service/bind DN)** | `cn=app-reader,ou=services,dc=example,dc=org` | Ứng dụng tự bind để tìm kiếm, đọc entry và thao tác qua repository/`LdapTemplate`. |
| **DN của người dùng đăng nhập** | `uid=lan,ou=people,dc=example,dc=org` | Spring Security dùng trong phép bind xác thực người dùng `lan`. |
| **DN của entry dữ liệu** | `uid=lan,ou=people,dc=example,dc=org` | Định danh entry khi tìm kiếm/cập nhật trong LDAP; có thể trùng DN tài khoản đăng nhập nhưng bản thân DN không chứng minh danh tính. |
| **Authority của người dùng** | `ROLE_DIRECTORY_READER` | Spring Security dùng để quyết định có cho phép gọi API hoặc phương thức hay không. |

**Quyền ở ứng dụng** và **ACL ở máy chủ LDAP** là hai lớp thực thi riêng:

1. Spring Security kiểm tra request của người dùng HTTP, ví dụ `lan` có authority `ROLE_DIRECTORY_READER` trước khi được phép gọi endpoint đọc hồ sơ.
2. LDAP server kiểm tra ACL tương ứng với **danh tính thực sự đang bind trên kết nối LDAP**, ví dụ `cn=app-reader,...` có được đọc thuộc tính `cn` của entry hay không.

Vì `LdapTemplate`/repository thông thường sử dụng `LdapContextSource` cấu hình tài khoản dịch vụ, directory server sẽ áp dụng ACL của **tài khoản dịch vụ** cho thao tác dữ liệu đó. Spring Security **không tự động truyền danh tính của từng request** sang tất cả các thao tác LDAP. Muốn thực hiện truy cập LDAP thay mặt người dùng cuối cần thiết kế và cấu hình riêng, kể cả cách quản lý credential và connection context.

## 4. Luồng từ HTTP request đến LDAP

~~~mermaid
flowchart TD
    A["Client gửi HTTP request"] --> B["Spring Security: SecurityFilterChain"]
    B --> C{"Đã xác thực?"}
    C -- "Chưa" --> D["AuthenticationManager"]
    D --> E["Tìm DN user và bind xác thực bằng LDAP"]
    E --> F{"Directory chấp nhận?"}
    F -- "Không" --> G["HTTP 401 / cơ chế đăng nhập tương ứng"]
    F -- "Có" --> H["Authentication + GrantedAuthority"]
    H --> I["Kiểm tra quy tắc phân quyền"]
    C -- "Có" --> I
    I --> J{"Có quyền?"}
    J -- "Không" --> K["HTTP 403"]
    J -- "Có" --> L["Controller / Service"]
    L --> M["Spring Data LDAP: Repository / LdapTemplate"]
    M --> N["Kết nối LDAP bằng bind DN dịch vụ"]
    N --> O["LDAP server kiểm tra ACL và xử lý entry"]
    O --> P["Trả dữ liệu hoặc lỗi LDAP"]
~~~

Sơ đồ minh họa một ứng dụng dùng Spring Security cho HTTP và một tài khoản riêng cho data access. Với HTTP Basic, Spring Security có thể xác thực thông tin Basic trên nhiều request; với session, OAuth2 hoặc JWT, cách thiết lập `Authentication` khác nhau. **Điểm chung** là trước khi gọi dịch vụ nghiệp vụ, Spring Security phải quyết định request có được phép hay không.

### Phân biệt hai thao tác bind

**Bind phục vụ xác thực người dùng:** Spring Security nhận tên đăng nhập và mật khẩu do người dùng cung cấp, tìm hoặc xây DN của người dùng theo schema rồi thử bind dưới danh tính đó. Server chấp nhận bind thì xác thực thành công. Tùy cấu hình, việc *tìm DN* có thể cần một tài khoản dịch vụ có quyền tìm kiếm.

**Bind phục vụ đọc dữ liệu:** `LdapRepository`/`LdapTemplate` thường dùng một `ContextSource` cấu hình sẵn tài khoản dịch vụ. Thao tác `findByUid("lan")` sẽ tìm entry bằng filter LDAP, không kiểm tra mật khẩu đăng nhập của `lan`. Nếu ứng dụng cho phép sửa entry, ACL của tài khoản đang bind vẫn phải cho phép ghi.

Không lưu hoặc đọc thuộc tính `userPassword` rồi tự so sánh chuỗi để “đăng nhập”. Hãy dùng cơ chế xác thực LDAP của Spring Security phù hợp với directory. Ngoài bind authentication, Spring Security còn hỗ trợ hướng password comparison khi có yêu cầu cụ thể, nhưng phải hiểu schema, định dạng hash, chính sách directory và cách bảo vệ secret.

## 5. Ví dụ: Spring Boot 3.x, Spring Security 6.x và Spring Data LDAP

Ví dụ sau dùng schema minh họa với `inetOrgPerson` ở `ou=people` và `groupOfUniqueNames` ở `ou=groups`. Quy tắc nghiệp vụ: chỉ người dùng thuộc nhóm `DIRECTORY_READER` mới được gọi endpoint đọc hồ sơ. Cần điều chỉnh tên thuộc tính, DN và nhóm nếu dùng Active Directory hoặc một LDAP server có schema khác.

### 5.1. Khai báo dependency

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-ldap")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

`spring-boot-starter-data-ldap` cung cấp các thành phần truy cập LDAP, `spring-security-ldap` cung cấp tích hợp authentication LDAP; Spring Boot quản lý phiên bản phụ thuộc tương thích. Trong ứng dụng thật cần dùng các phiên bản hỗ trợ và đối chiếu tài liệu của đúng phiên bản đang triển khai.

### 5.2. Cấu hình connection source chung

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ biến môi trường:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=app-reader,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret-do-moi-truong-cap>
~~~

`spring.ldap.base` là gốc cho các thao tác LDAP có DN tương đối; `spring.ldap.username` và `spring.ldap.password` là danh tính/mật khẩu dịch vụ phục vụ kết nối. **Chúng không phải tên đăng nhập và mật khẩu của người dùng HTTP**. Directory phải có các entry, nhánh và ACL tương ứng thì ví dụ mới chạy được. Không commit secret vào mã nguồn.

Trong production, dùng kết nối được mã hóa và xác minh chứng chỉ máy chủ. `ldaps://` thiết lập TLS từ đầu; `ldap://` **không tự động có StartTLS** nếu không cấu hình chiến lược kết nối riêng.

### 5.3. Xác thực người dùng bằng bind và ánh xạ nhóm thành quyền

Ở ví dụ này, một người dùng đăng nhập bằng `uid`. Spring Security tìm entry dưới `ou=people`, thử bind bằng mật khẩu vừa nhập, rồi tìm nhóm trong `ou=groups`. Nhóm có `cn=DIRECTORY_READER` và thuộc tính `uniqueMember` chứa DN đầy đủ của người dùng sẽ được ánh xạ thành `ROLE_DIRECTORY_READER`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class DirectorySecurityConfiguration {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");

        var groups = new DefaultLdapAuthoritiesPopulator(
            contextSource, "ou=groups");
        groups.setGroupSearchFilter("(uniqueMember={0})");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);
        factory.setLdapAuthoritiesPopulator(groups);

        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager ldapAuthenticationManager)
            throws Exception {
        http.authenticationManager(ldapAuthenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/people/**")
                    .hasRole("DIRECTORY_READER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Đọc từng phần:**

1. `setUserSearchBase("ou=people")` và `setUserSearchFilter("(uid={0})")` xác định cách tìm DN của user để thử bind. `{0}` là tham số tên đăng nhập được xử lý bởi cơ chế filter của Spring Security LDAP; không tự nối đầu vào người dùng vào một filter thô.
2. `DefaultLdapAuthoritiesPopulator` tìm nhóm theo `uniqueMember` và lấy `cn`. Với `cn=DIRECTORY_READER`, tiền tố `ROLE_` tạo `ROLE_DIRECTORY_READER`, phù hợp quy tắc `hasRole("DIRECTORY_READER")`.
3. `http.authenticationManager(...)` gắn cơ chế LDAP authentication cho chuỗi bảo mật ví dụ.
4. `httpBasic(...)` kích hoạt HTTP Basic để dễ thực hành; hệ thống thật phải bảo vệ mọi request bằng HTTPS và chọn hình thức đăng nhập phù hợp.
5. `anyRequest().denyAll()` chặn các endpoint chưa được khai báo. Một user xác thực hợp lệ nhưng không thuộc nhóm đúng sẽ bị từ chối endpoint `/api/people/**`.

Ví dụ giả định entry nhóm có `objectClass=groupOfUniqueNames`, `cn=DIRECTORY_READER` và `uniqueMember=uid=lan,ou=people,dc=example,dc=org`. Nếu directory dùng `member`, `memberOf`, `sAMAccountName` hoặc chiến lược nested groups khác, cần thay cách tìm nhóm/ánh xạ quyền cho đúng schema. **Không suy vai trò ADMIN từ tên DN hoặc sự tồn tại của entry.**

### 5.4. Truy cập dữ liệu bằng repository sau khi được phép

Entity thuộc tầng truy cập dữ liệu:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
}
~~~

Repository:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Service có kiểm soát quyền ở mức phương thức, đồng thời chỉ trả về những thuộc tính cần cho API:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

public record PersonView(String uid, String commonName) {}

@Service
public class PeopleService {
    private final PersonRepository repository;

    public PeopleService(PersonRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasRole('DIRECTORY_READER')")
    public PersonView findByUid(String uid) {
        PersonEntry person = repository.findByUid(uid)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Không tìm thấy người dùng"));
        return new PersonView(person.getUid(), person.getCommonName());
    }
}
~~~

Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/people")
public class PeopleController {
    private final PeopleService service;

    public PeopleController(PeopleService service) {
        this.service = service;
    }

    @GetMapping("/{uid}")
    public PersonView byUid(@PathVariable String uid) {
        return service.findByUid(uid);
    }
}
~~~

Ở đây, `SecurityFilterChain` bảo vệ URL và `@PreAuthorize` bảo vệ phương thức service. `@EnableMethodSecurity` kích hoạt cơ chế kiểm tra quyền cho phương thức được gọi qua Spring proxy. Với lời gọi nội bộ giữa các phương thức trong cùng một đối tượng (*self-invocation*), proxy có thể bị bỏ qua; hãy đặt kiểm tra quyền tại ranh giới service thích hợp.

Hàm `repository.findByUid(uid)` vẫn là **truy vấn dữ liệu**, không phải hàm đăng nhập. Với `spring.ldap.base=dc=example,dc=org`, base `ou=people` của entity là đường dẫn tương đối. Spring Data LDAP ánh xạ DN và các thuộc tính theo schema; annotation `@Id` ở đây là `org.springframework.ldap.odm.annotations.Id`.

> **Lưu ý về đoạn mã:** Để trình bày mỗi class độc lập, ví dụ đặt `PersonView`, `PeopleService`, `PersonEntry`, `PersonRepository`, `PeopleController` và `DirectorySecurityConfiguration` ở các đoạn mã riêng. Khi triển khai, đặt mỗi public type vào file Java tương ứng, cùng package hoặc tổ chức package có imports và component scan phù hợp. Cấu hình Spring Security và LDAP cũng cần điều chỉnh theo phiên bản dependency và schema cụ thể.

### 5.5. Nếu cần truy vấn phức tạp bằng `LdapTemplate`

`LdapTemplate` vẫn thuộc tầng dữ liệu. Chẳng hạn muốn tìm những entry người dùng có `uid` do client truyền vào:

~~~java
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(uid);
~~~

Truy vấn có kiểm soát escaping cho giá trị filter; để tránh LDAP filter injection, không tạo chuỗi `"(uid=" + uid + ")"` từ input không tin cậy. Khi dựng DN có dữ liệu động, dùng `LdapNameBuilder` hoặc API DN tương đương để xử lý ký tự đặc biệt. **Filter an toàn chỉ bảo vệ cú pháp truy vấn; nó không thay thế kiểm tra quyền truy cập dữ liệu.**

## 6. Authentication, authorization và LDAP ACL trong một tình huống

Giả sử có ba người:

- **Lan:** mật khẩu LDAP đúng, thuộc nhóm `DIRECTORY_READER`.
- **Minh:** mật khẩu LDAP đúng, không thuộc nhóm `DIRECTORY_READER`.
- **Khách lạ:** không cung cấp thông tin đăng nhập hợp lệ.

Tất cả cùng gọi `GET /api/people/lan`. Khi cấu hình ở mục 5 hoạt động đúng:

| Người gọi | Xác thực (LDAP bind) | Phân quyền Spring Security | Truy vấn repository | Kết quả |
| --- | --- | --- | --- | --- |
| Lan | Thành công | Có `ROLE_DIRECTORY_READER` | Chạy với danh tính kết nối dữ liệu của ứng dụng | Trả dữ liệu nếu entry tồn tại và ACL cho phép. |
| Minh | Thành công | Thiếu `ROLE_DIRECTORY_READER` | Không chạy | HTTP `403 Forbidden`. |
| Khách lạ | Thất bại hoặc chưa có | Không có `Authentication` hợp lệ | Không chạy | HTTP `401 Unauthorized` với HTTP Basic. |

Nếu Lan được phép đi qua Spring Security nhưng tài khoản `app-reader` không có ACL đọc `ou=people`, thao tác LDAP **vẫn có thể thất bại** hoặc bị che kết quả tùy server. Ngược lại, cho dù `app-reader` có quyền đọc cả directory, Minh vẫn phải bị chặn ở tầng Spring Security trước khi repository chạy.

**Hai lớp quyền phải cùng đúng:** quyền ứng dụng cho phép *ai được dùng chức năng*; ACL directory cho phép *danh tính LDAP nào được thao tác lên entry/thuộc tính*. Đối với dữ liệu nhạy cảm, cần thêm chính sách nghiệp vụ theo đối tượng, ví dụ user chỉ xem hồ sơ của chính mình. Chỉ kiểm tra `hasRole("DIRECTORY_READER")` chưa đủ cho yêu cầu đó.

## 7. Các nhầm lẫn thường gặp

| Cách làm dễ gây lỗi | Vì sao sai hoặc thiếu? | Hướng xử lý |
| --- | --- | --- |
| “Tìm thấy `uid=lan` tức là Lan đã đăng nhập.” | Repository chỉ chứng minh entry tồn tại. | Xác thực mật khẩu hoặc phương thức đăng nhập bằng Spring Security. |
| “Đã bind được bằng `app-reader`, mọi user đều có thể gọi API.” | Bind của tài khoản dịch vụ không chứng thực người gọi HTTP. | Thiết lập `SecurityFilterChain` và yêu cầu authentication ở endpoint. |
| “Directory có nhóm ADMIN thì tự động có role ADMIN.” | Spring Security cần cách tra cứu/ánh xạ group sang `GrantedAuthority`. | Cấu hình group search và role mapping; kiểm thử bằng tài khoản thật. |
| “Đã kiểm tra URL nên không cần kiểm tra service.” | Một service có thể được gọi từ nhiều điểm, không chỉ qua controller ban đầu. | Bảo vệ ở ranh giới nghiệp vụ bằng `@PreAuthorize`/cơ chế authorization thích hợp. |
| “User đã đăng nhập nên repository tự truy vấn bằng DN của user đó.” | Repository thường dùng `ContextSource` ứng dụng và DN tài khoản dịch vụ. | Xác định danh tính LDAP của từng thao tác; không giả định có credential delegation. |
| “Bật `ldap://` đủ an toàn cho mật khẩu.” | LDAP plain-text connection không tự mã hóa. | Dùng LDAPS hoặc StartTLS cấu hình và xác minh chứng chỉ. |
| “Nối chuỗi filter là đủ vì đã kiểm tra role.” | Input có thể làm đổi logic LDAP filter. | Dùng query builder/escaping đúng chuẩn và kiểm tra tham số. |
| “Chỉ cần phân quyền ở ứng dụng để kiểm soát CRUD.” | Tài khoản bind có thể có quyền LDAP quá rộng, làm tăng mức độ ảnh hưởng nếu ứng dụng lỗi. | Giới hạn ACL theo nhánh, thuộc tính và thao tác cần thiết. |

### Những điểm cần quyết định khi thiết kế thật

**Nguồn quyền:** Có thể lấy group từ LDAP, một hệ thống RBAC trong database riêng, hoặc token từ identity provider. Không nhất thiết mọi quyền ứng dụng đều là nhóm LDAP. Nếu dùng nhóm LDAP, phải xử lý trường hợp nhóm lồng nhau, nhóm đổi tên, tài khoản bị khóa và thời điểm quyền được làm mới.

**Định danh ổn định:** `uid`, `cn`, email và DN có thể thay đổi tùy chính sách tổ chức. Không dùng giá trị có thể thay đổi làm khóa bất biến xuyên hệ thống nếu chưa có quy ước rõ ràng.

**Quyền theo đối tượng:** `hasRole("DIRECTORY_READER")` cho phép một chức năng ở mức vai trò, nhưng không tự giới hạn người dùng được đọc entry nào. Nếu có chính sách “chỉ xem hồ sơ của mình”, cần so sánh principal đã xác thực với danh tính sở hữu tài nguyên trong service hoặc policy layer.

**Ghi dữ liệu:** Với chức năng tạo/sửa/xóa entry, phải đồng thời có authorization thích hợp ở ứng dụng, validate dữ liệu theo schema và ACL ghi tối thiểu cho tài khoản kết nối. Không cho phép ghi password hoặc thay đổi nhóm quyền qua endpoint CRUD chung chỉ vì entity có các thuộc tính đó.

**Phiên và CSRF:** HTTP Basic trong ví dụ phù hợp để minh họa phép xác thực. Nếu ứng dụng dùng cookie/session, thiết kế bảo vệ CSRF cho thao tác thay đổi trạng thái; đừng tắt CSRF theo thói quen. Với API token hoặc cơ chế xác thực khác, cần đánh giá đúng mô hình rủi ro trước khi điều chỉnh.

## 8. Cách kiểm chứng từng tầng

Để phân tích lỗi, kiểm tra theo thứ tự **kết nối LDAP → bind tài khoản dịch vụ → tìm user → bind bằng user → tìm group/authority → kiểm tra route/service → truy vấn dữ liệu → ACL LDAP**.

### 8.1. Kiểm tra directory độc lập

Với OpenLDAP client, thử tài khoản dịch vụ bằng `ldapsearch`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn uid cn
~~~

Sau đó kiểm tra nhóm của entry `lan`:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(uniqueMember=uid=lan,ou=people,dc=example,dc=org)" dn cn
~~~

Tham số `-W` yêu cầu nhập mật khẩu tương tác. Hai lệnh trên kiểm tra **khả năng đọc bằng tài khoản dịch vụ**, không xác thực mật khẩu của `lan`. Để kiểm tra user bind, dùng công cụ LDAP với DN của `lan` và nhập **mật khẩu thật của Lan** qua prompt trong môi trường kiểm thử được cấp phép.

### 8.2. Kiểm tra hành vi HTTP

Nếu ứng dụng thực hành chạy qua HTTPS:

~~~bash
# curl sẽ hỏi mật khẩu qua prompt:
curl -i --user lan https://localhost:8443/api/people/lan
~~~

Chạy cùng endpoint bằng tài khoản có mật khẩu sai, tài khoản đúng mật khẩu nhưng không thuộc group, và tài khoản hợp lệ có quyền. Trường hợp sai mật khẩu thường nhận `401`; thiếu quyền nhận `403`; có quyền nhưng entry cần tìm không tồn tại nhận `404` theo code ví dụ. Nếu thao tác dữ liệu có lỗi, kết quả còn phụ thuộc cách ứng dụng ánh xạ exception sang HTTP status.

| Dấu hiệu | Tầng cần kiểm tra trước |
| --- | --- |
| `SSLHandshakeException`, connection refused, timeout | URL, mạng, TLS, truststore của JVM. |
| LDAP result code `49` khi bind | DN/username, mật khẩu, trạng thái tài khoản và chính sách directory. |
| User tồn tại nhưng login vẫn `401` | User search base/filter, bind authentication và dữ liệu credential. |
| Login thành công nhưng `403` | Cấu hình route/method, group search, ánh xạ role, chính sách nghiệp vụ. |
| Repository trả về rỗng | Base DN, `@Entry(base=...)`, filter, schema, ACL đọc. |
| LDAP result code `50` | Quyền LDAP của danh tính bind trên thao tác/entry/thuộc tính. |
| Có quyền API nhưng sửa entry thất bại | Schema LDAP, DN đích, quyền ghi của service account, ràng buộc server. |

Lỗi `401`/`403` là **phản hồi HTTP**, còn mã `49`/`50` là **LDAP result code**; không nên đồng nhất chúng. Directory có thể cố ý ẩn sự tồn tại của entry theo ACL hoặc trả lỗi khác nhau theo triển khai.

### 8.3. Kiểm thử tích hợp thực tế

Nên có directory thử nghiệm với dữ liệu xác định trước và những trường hợp ít nhất: user đúng mật khẩu/có group; user đúng mật khẩu/không có group; sai mật khẩu; user không tồn tại; tài khoản dịch vụ thiếu quyền đọc; entry sai schema; người dùng nhập ký tự đặc biệt vào `uid`. Test cả việc **không gọi repository** khi authorization từ chối và **không lộ mật khẩu, DN nội bộ hoặc stack trace** qua phản hồi API.

## 9. Bài tập ứng dụng

Một hệ thống nhân sự dùng LDAP lưu hồ sơ tại `ou=employees,dc=company,dc=internal`. Tài khoản kết nối dữ liệu là `cn=hr-reader,ou=services,dc=company,dc=internal`. Người dùng đăng nhập bằng `uid`; nhóm `HR_VIEWER` có quyền xem danh bạ và `HR_EDITOR` được phép sửa số điện thoại.

**Yêu cầu:**

1. Xác định thành phần chịu trách nhiệm khi hệ thống kiểm tra mật khẩu của `uid=mai`, khi đọc thuộc tính `telephoneNumber` và khi quyết định ai được gọi `PATCH /api/employees/mai`.
2. Nếu user `mai` đăng nhập thành công nhưng không thuộc `HR_EDITOR`, việc `hr-reader` có quyền ghi trong LDAP có khiến yêu cầu PATCH được phép hay không? Giải thích.
3. Nếu `mai` thuộc `HR_EDITOR` nhưng tài khoản dịch vụ chỉ có ACL đọc, thao tác PATCH xảy ra điều gì?
4. Vì sao không thể thay `@PreAuthorize("hasRole('HR_EDITOR')")` bằng truy vấn `repository.findByUid("mai")`?
5. Nêu cách ngăn một `HR_VIEWER` xem số điện thoại bí mật của người khác nếu vai trò chung chỉ cho phép xem hồ sơ cơ bản.

**Gợi ý đáp án:** Spring Security LDAP authentication kiểm tra credential; repository/`LdapTemplate` đọc hoặc ghi `telephoneNumber`; Spring Security và chính sách nghiệp vụ quyết định quyền PATCH. User không có `HR_EDITOR` phải bị chặn ở tầng ứng dụng ngay cả khi bind DN dịch vụ có quyền ghi. User có `HR_EDITOR` nhưng dịch vụ không có ACL ghi thì LDAP server vẫn chặn thao tác. `findByUid` chỉ trả dữ liệu, không xác thực hoặc phân quyền. Đối với dữ liệu nhạy cảm, cần thêm kiểm tra chủ sở hữu/quan hệ tổ chức và chỉ trả về các thuộc tính được phép.

## 10. Ghi nhớ

**Spring Data LDAP** trả lời: *ứng dụng thao tác với entry nào, bằng truy vấn và kết nối nào?*

**Spring Security Authentication** trả lời: *người gọi có thực sự là danh tính đang khai báo không?*

**Spring Security Authorization** trả lời: *danh tính đó được làm gì trong ứng dụng?*

**LDAP ACL** trả lời: *danh tính đang bind với directory được phép thao tác gì trên các entry và thuộc tính?*

Khi thiết kế một hệ thống LDAP an toàn, hãy kiểm tra đủ cả **danh tính người dùng HTTP**, **quyền ứng dụng**, **danh tính kết nối LDAP** và **ACL của directory**. Không suy ra quyền hay kết quả xác thực chỉ từ sự tồn tại của entry, DN hoặc sự thành công của một truy vấn repository.

### Tài liệu tham khảo

- [Spring Security Reference — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data LDAP Reference — Repositories](https://docs.spring.io/spring-data/ldap/reference/ldap/repositories.html)
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
