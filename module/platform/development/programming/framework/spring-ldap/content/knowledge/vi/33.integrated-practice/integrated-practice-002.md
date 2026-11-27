# Tìm user bằng LdapQueryBuilder và ánh xạ domain object trong Spring LDAP

Trong ứng dụng quản lý nhân sự, người dùng nhập tên tài khoản `lan` để tra cứu thông tin trong LDAP. Backend không nên trả về nguyên một đối tượng LDAP chứa mọi thuộc tính, cũng không nên tự nối `uid` vào chuỗi search filter. Thay vào đó, ứng dụng cần xây **truy vấn có cấu trúc**, chỉ đọc các thuộc tính cần thiết và ánh xạ kết quả sang **domain object** mà phần còn lại của hệ thống có thể sử dụng.

Bài thực hành tổng hợp này dùng **Spring LDAP** để giải quyết trọn vẹn quy trình:

1. Thiết lập `ContextSource` kết nối tới LDAP qua TLS.
2. Tìm một entry người dùng bằng `LdapQueryBuilder` với filter an toàn.
3. Dùng `ContextMapper` và `DirContextOperations` để chuyển entry LDAP thành Java domain object.
4. Kiểm tra kết quả rỗng, một entry hoặc nhiều entry cùng định danh.
5. Viết integration test trên directory thử nghiệm và đưa dữ liệu đã được kiểm soát ra tầng dịch vụ.

Ví dụ giả định LDAP dùng `inetOrgPerson` và thuộc tính đăng nhập `uid`. Với Active Directory hoặc schema riêng, bạn cần thay các attribute và quy tắc tìm kiếm tương ứng. Bài tập tập trung vào **directory lookup và mapping**, không tự coi search thành xác thực mật khẩu.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt **LDAP entry**, **Distinguished Name (DN)** và **domain object** của ứng dụng.
- Tạo filter equality an toàn bằng `LdapQueryBuilder.query().where(...).is(...)`.
- Chọn search base, search scope và danh sách attribute cần đọc.
- Ánh xạ dữ liệu qua `ContextMapper`, xử lý thuộc tính không bắt buộc và lấy DN của entry.
- Tách repository LDAP, domain model và service theo trách nhiệm.
- Phát hiện tên đăng nhập không tồn tại hoặc không duy nhất mà không tự chọn entry đầu tiên.
- Tổ chức kiểm thử kết nối, schema, Unicode, filter injection và các trường hợp thiếu quyền.

## 2. Bài toán và dữ liệu LDAP mẫu

Giả sử một ứng dụng có chức năng “Tra cứu nhân viên” với yêu cầu:

- Đầu vào là `uid`, ví dụ `lan` hoặc `minh`.
- Kết quả gồm định danh, họ tên, email (nếu có) và DN để backend tham chiếu.
- Chỉ tìm dưới `ou=people,dc=example,dc=org`.
- Không trả `userPassword` hay các thuộc tính nhạy cảm.
- Nếu không tìm thấy, trả kết quả rỗng; nếu nhiều entry trùng `uid` trong vùng hợp lệ, **báo lỗi định danh mơ hồ**.
- Dữ liệu do browser nhập không được thay đổi cú pháp filter hoặc search base.

### 2.1. Cấu trúc cây ví dụ

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=contractors
│       └── uid=ngoc
└── ou=system
    └── cn=svc-directory-reader
~~~

LDAP Data Interchange Format (LDIF) minh họa dữ liệu chính:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Le
sn: Le
~~~

Trong dữ liệu mẫu, `mail` của Minh không có. `inetOrgPerson` kế thừa các object class phù hợp và thường dùng `cn`/`sn`; server thật có thể áp thêm schema và ràng buộc riêng. Tạo các entry dưới OU test với tài khoản được cấp phép, không nhập dữ liệu thử nghiệm vào directory production.

### 2.2. Domain object mong muốn

Entry LDAP là một tập hợp attribute, có thể chứa thuộc tính nhiều giá trị, metadata, schema và dữ liệu không thuộc nhu cầu nghiệp vụ. Ứng dụng của ta chỉ cần một **giá trị Java bất biến**:

~~~java
// DirectoryUser.java — Java 17+
public record DirectoryUser(
        String relativeDn,
        String uid,
        String fullName,
        String email
) {}
~~~

| Trường domain | Nguồn từ LDAP | Quy tắc |
|---|---|---|
| `relativeDn` | Metadata DN của entry (`DirContextOperations.getDn()`) | Giữ để backend tham chiếu, không đưa thẳng ra API công khai |
| `uid` | Attribute `uid` | Bắt buộc cho bài tập |
| `fullName` | Attribute `cn` | Bắt buộc cho bài tập |
| `email` | Attribute `mail` | Có thể `null` nếu entry không có `mail` |

Tên `relativeDn` được chọn có chủ ý: `getDn()` của Spring LDAP phản ánh DN ở ngữ cảnh search và thông thường là **DN tương đối với base của `ContextSource`**. Đừng mặc định nó luôn là DN đầy đủ kiểu `uid=lan,ou=people,dc=example,dc=org`. Nếu một chức năng cần DN tuyệt đối để bind hoặc truyền sang hệ thống khác, hãy chuyển đổi bằng API DN phù hợp với cấu hình base thực tế và kiểm thử kết quả; không nối chuỗi DN thủ công.

Domain object không phải LDAP entry có thể ghi ngược tự động, cũng không phải JPA entity. Đây là mô hình dữ liệu **đọc từ directory** để các tầng ứng dụng sử dụng.

## 3. Chuẩn bị Spring Boot và kết nối

### 3.1. Dependency cần thiết

Ví dụ Maven dành cho dự án Spring Boot có Java 17+:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Khi dùng Spring Boot, starter LDAP giúp thiết lập dependency và auto-configuration cho `LdapContextSource`/`LdapTemplate`. Nếu không dùng auto-configuration, ứng dụng cần tự khai báo `ContextSource` và `LdapTemplate` tương ứng.

### 3.2. Ví dụ `application.yml`

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.lab.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ các biến môi trường được cấp cho dịch vụ:

~~~text
LDAP_URL=ldaps://ldap.lab.example.org:636
LDAP_BIND_DN=cn=svc-directory-reader,ou=system,dc=example,dc=org
LDAP_BIND_PASSWORD=(bí mật lấy từ secret manager)
~~~

Ý nghĩa:

1. `spring.ldap.urls` trỏ tới endpoint LDAPS. Java cần có **truststore tin cậy** và xác minh certificate chain/hostname của server.
2. `spring.ldap.base` là DN gốc dùng bởi `ContextSource`. Trong ví dụ, `base("ou=people")` ở query sẽ nằm dưới `dc=example,dc=org`.
3. `spring.ldap.username/password` là credential **tài khoản dịch vụ tra cứu**, không phải mật khẩu của nhân viên đang được tìm.
4. Tài khoản dịch vụ chỉ cần quyền tìm kiếm/đọc `uid`, `cn`, `mail`, metadata DN trong vùng `ou=people` theo ACL, không cần quyền đọc `userPassword` hoặc sửa/xóa entry.

Không hardcode credential trong source code hay commit tài khoản thật. Với LDAP + StartTLS, phải cấu hình chiến lược nâng cấp kết nối **trước khi bind**; URL `ldap://` không tự bảo đảm mã hóa.

## 4. Xây query an toàn với `LdapQueryBuilder`

Một tìm kiếm LDAP có bốn phần quan trọng:

| Thành phần | Cấu hình trong bài | Mục đích |
|---|---|---|
| Search base | `ou=people` | Chỉ xem vùng người dùng |
| Search scope | `SUBTREE` | Bao gồm các entry trong OU con như contractors |
| Filter | `(&(objectClass=inetOrgPerson)(uid=lan))` | Khớp user có object class và uid yêu cầu |
| Requested attributes | `uid`, `cn`, `mail` | Tránh lấy cả entry không cần thiết |

Trong Spring LDAP:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid", "cn", "mail")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(username);
~~~

Ở đây:

- `base` và `searchScope` do backend quyết định, không nhận tùy ý từ request.
- `where(...).is(...)` tạo **equality filter**; username được xem là một giá trị, không phải một đoạn cú pháp filter.
- `attributes(...)` giới hạn dữ liệu được trả về. Các attribute dùng trong filter vẫn cần được LDAP server cho phép đánh giá theo chính sách ACL.
- `SearchScope.SUBTREE` phù hợp ví dụ có OU con. Nếu người dùng chỉ nằm trực tiếp dưới `ou=people`, `ONELEVEL` có thể giảm phạm vi.

### 4.1. Vì sao không nối chuỗi filter?

Đoạn sau **không an toàn** khi username lấy từ client:

~~~java
// KHÔNG LÀM: username là đầu vào không tin cậy.
String filter = "(&(objectClass=inetOrgPerson)(uid="
        + username + "))";
~~~

Nếu username là ký tự `*`, filter trở thành `(&(objectClass=inetOrgPerson)(uid=*))` và điều kiện `uid=*` mang ý nghĩa **thuộc tính tồn tại**, có thể trả nhiều người dùng. Trong khi đó, với `.is(username)`, giá trị `*` được xử lý như dữ liệu literal theo quy tắc escape LDAP filter (RFC 4515), không trở thành wildcard do input.

| Đầu vào | Cách ghép nguy hiểm | Hành vi mong đợi khi dùng equality builder |
|---|---|---|
| `lan` | `(uid=lan)` | Tìm `uid` tương ứng |
| `*` | `(uid=*)` — kiểm tra tồn tại | Tìm literal `*` nếu có, không tìm toàn bộ user |
| `lan*` | `(uid=lan*)` — substring | Tìm literal `lan*`, không tự tìm theo prefix |
| `lan)(uid=*` | Có thể thay đổi/phá cú pháp filter | Các ký tự đặc biệt chỉ là dữ liệu cần escape |

Không tự thay `.is(...)` bằng `.like(...)` khi chức năng cần tìm **một định danh cụ thể**. Wildcard search có thể hợp lý cho màn hình gợi ý tên, nhưng phải là tính năng được thiết kế riêng, có giới hạn phạm vi và số kết quả.

## 5. Ánh xạ LDAP entry thành `DirectoryUser`

Khi chỉ cần giá trị các attribute đơn giản, `AttributesMapper` là lựa chọn gọn. Tuy nhiên, muốn đọc cả **DN metadata** và attribute trong cùng phép search, `ContextMapper` cùng `DirContextOperations` thường thuận tiện hơn.

### 5.1. Ví dụ repository hoàn chỉnh

~~~java
// DirectoryUserRepository.java
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Repository;

@Repository
public class DirectoryUserRepository {

    private final LdapTemplate ldapTemplate;

    public DirectoryUserRepository(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private static final ContextMapper<DirectoryUser> USER_MAPPER =
            context -> {
                DirContextOperations entry =
                        (DirContextOperations) context;

                String uid = entry.getStringAttribute("uid");
                String cn = entry.getStringAttribute("cn");
                String mail = entry.getStringAttribute("mail");

                if (uid == null || cn == null) {
                    throw new IllegalStateException(
                        "LDAP entry missing required uid or cn");
                }

                return new DirectoryUser(
                        entry.getDn().toString(),
                        uid,
                        cn,
                        mail
                );
            };

    public List<DirectoryUser> searchByUid(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid", "cn", "mail")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query, USER_MAPPER);
    }
}
~~~

**Phân tích từng phần:**

1. `DirectoryUserRepository` chỉ chịu trách nhiệm truy vấn LDAP và ánh xạ kết quả; nó không tự xác thực mật khẩu hoặc cấp role.
2. `ContextMapper<DirectoryUser>` nhận context của từng entry trong kết quả search. Với cách ánh xạ của Spring LDAP, đối tượng đó có thể truy cập qua `DirContextOperations`.
3. `getStringAttribute("uid")`, `getStringAttribute("cn")`, `getStringAttribute("mail")` lấy giá trị dạng chuỗi từ LDAP. Nếu schema sử dụng attribute nhiều giá trị, cần phương thức đọc phù hợp thay vì mặc định chỉ một chuỗi.
4. `uid` và `cn` được coi là bắt buộc trong domain của bài tập; nếu thiếu, ném lỗi dữ liệu thay vì tạo một đối tượng không hợp lệ.
5. `mail` là tùy chọn nên `null` được giữ lại. Không tự tạo email giả hoặc mặc định `""` khi nguồn không có.
6. `entry.getDn()` lấy thông tin DN của entry. Giá trị `relativeDn` giữ nguyên để backend sử dụng; không công khai toàn bộ cấu trúc thư mục trong API.
7. `LdapTemplate.search(query, USER_MAPPER)` thực hiện truy vấn rồi map **mỗi entry** thành một `DirectoryUser`. Kết quả là `List<DirectoryUser>`, có thể rỗng hoặc chứa nhiều phần tử.

Ví dụ kết quả logic khi tìm `uid=lan`:

~~~text
DirectoryUser(
  relativeDn = "uid=lan,ou=people",
  uid        = "lan",
  fullName   = "Lan Tran",
  email      = "lan@example.org"
)
~~~

DN trên chỉ minh họa cách biểu diễn tương đối trong cấu hình base hiện tại; giá trị thực cần được xác minh trong integration test theo `ContextSource` và LDAP server đang sử dụng.

### 5.2. Khi nào dùng `AttributesMapper`?

Nếu chỉ lấy một vài thuộc tính và **không cần DN**, `AttributesMapper` phù hợp:

~~~java
import org.springframework.ldap.core.AttributesMapper;

List<String> names = ldapTemplate.search(
        LdapQueryBuilder.query()
            .base("ou=people")
            .where("uid").is("lan"),
        (AttributesMapper<String>) attrs ->
            attrs.get("cn").get().toString()
);
~~~

Đây là ví dụ ngắn; trong ứng dụng thực tế cần xử lý attribute thiếu, giới hạn attributes trả về và ngoại lệ khi schema/ACL không phù hợp. Với domain model chứa cả DN, `ContextMapper` ở phần trên rõ ràng hơn.

### 5.3. Domain object khác LDAP ODM

Spring LDAP còn có **Object-Directory Mapping (ODM)**, cho phép khai báo entity bằng annotation (ví dụ `@Entry`, `@Id`, `@Attribute`) và thao tác với entry dưới dạng object. ODM hữu ích khi ứng dụng cần CRUD nhiều entry theo schema ổn định.

Ở bài tập này, `ContextMapper` được chọn vì:

- Tập trung vào **đọc user** với projection nhỏ.
- Kiểm soát rõ giá trị bắt buộc/tùy chọn.
- Không gắn domain object vào cơ chế lưu hoặc cập nhật LDAP.
- Dễ giải thích dữ liệu được map ở đâu và kiểm thử từng trường.

Đừng coi `DirectoryUser` là entity mà gọi save/update tùy ý; nếu muốn ghi LDAP, hãy thiết kế riêng thao tác với DN, schema, ACL và cơ chế xác nhận thay đổi.

## 6. Tầng service: bảo đảm chỉ có một kết quả

LDAP có thể trả **0, 1 hoặc nhiều entry**. Trong một chức năng tìm một định danh, `results.get(0)` không phải cách xử lý an toàn: nếu hai nhánh khác nhau chứa cùng `uid`, việc lấy phần tử đầu sẽ phụ thuộc vào thứ tự server trả về.

Ví dụ service:

~~~java
// DirectoryUserService.java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class DirectoryUserService {
    private final DirectoryUserRepository repository;

    public DirectoryUserService(DirectoryUserRepository repository) {
        this.repository = repository;
    }

    public Optional<DirectoryUser> findOneByUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            return Optional.empty();
        }

        List<DirectoryUser> matches = repository.searchByUid(uid);

        if (matches.size() > 1) {
            throw new IllegalStateException(
                "Ambiguous uid within configured LDAP search base");
        }

        return matches.stream().findFirst();
    }
}
~~~

Trong bài tập:

| Kết quả LDAP | Kết quả service | Ý nghĩa |
|---|---|---|
| Không có entry | `Optional.empty()` | Không tìm thấy định danh phù hợp |
| Có đúng một entry | `Optional<DirectoryUser>` có giá trị | Trả domain object |
| Có nhiều entry | Ném lỗi dữ liệu mơ hồ | Không chọn entry tùy ý |
| Username `null`, rỗng hoặc quá dài | `Optional.empty()` theo chính sách minh họa | Không gửi query không hợp lệ |
| LDAP timeout / thiếu ACL / TLS lỗi | Ngoại lệ LDAP được truyền lên | Không giả vờ đây chỉ là user không tồn tại |
| Entry thiếu `uid` hoặc `cn` | Lỗi dữ liệu LDAP | Cần kiểm tra schema và dữ liệu test |

Giới hạn 128 ký tự ở đây là **quy tắc ứng dụng minh họa**, không phải giới hạn mặc định của LDAP. Nếu sản phẩm cần phân biệt “đầu vào không hợp lệ” với “không tìm thấy”, thay `Optional.empty()` bằng kiểu kết quả hoặc exception phù hợp ở ranh giới API.

**Quan trọng:** nhiều schema có matching rule không phân biệt chữ hoa/chữ thường cho `uid`, và `uid` chưa chắc duy nhất trong toàn directory. Phải xác định rõ search base và chính sách duy nhất cho chức năng. Nếu cần tìm trên nhiều OU hoặc domain, quy tắc định danh phải được thiết kế trước.

### 6.1. Có nên dùng `countLimit`?

Trong chức năng tìm đúng một user, có thể cân nhắc **server-side size limit** để bảo vệ hệ thống khỏi truy vấn quá rộng. Tuy nhiên:

- Nếu giới hạn một entry, bạn có thể **không phát hiện được trùng định danh**.
- Nếu giới hạn nhỏ, server có thể trả lỗi size-limit hoặc kết quả không đầy đủ tùy server/client.
- Với bài toán xác thực hoặc định danh, nguồn dữ liệu nên bảo đảm uniqueness; giới hạn số kết quả chỉ là hàng rào bổ sung.

Vì vậy ví dụ giữ toàn bộ kết quả trong vùng search được kiểm soát để dễ minh họa ba trường hợp, nhưng production cần thêm giới hạn truy vấn, timeout, index cho `uid` và policy vận hành phù hợp.

## 7. Nếu đưa kết quả ra REST API

Một ứng dụng có thể muốn cung cấp endpoint tra cứu. **Không trả trực tiếp domain object có DN hoặc thuộc tính nội bộ**, mà chuyển sang DTO công khai và áp quyền trước khi đọc:

~~~java
// DirectoryUserView.java
public record DirectoryUserView(
        String uid,
        String fullName,
        String email
) {}
~~~

~~~java
// DirectoryUserController.java — giả định đã bật method security.
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/directory")
public class DirectoryUserController {
    private final DirectoryUserService service;

    public DirectoryUserController(DirectoryUserService service) {
        this.service = service;
    }

    @GetMapping("/users/{uid}")
    @PreAuthorize("hasAuthority('DIRECTORY_READ')")
    public ResponseEntity<DirectoryUserView> find(@PathVariable String uid) {
        return service.findOneByUid(uid)
                .map(user -> ResponseEntity.ok(new DirectoryUserView(
                        user.uid(), user.fullName(), user.email())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Phần HTTP **chỉ là mở rộng** để minh họa việc dùng domain object. Muốn chạy nó cần thêm Spring Web, Spring Security và bật method security (ví dụ `@EnableMethodSecurity`) cùng bộ xác thực cung cấp authority `DIRECTORY_READ` từ nguồn đáng tin cậy. Không coi annotation là đủ khi chưa bật cấu hình. Với dữ liệu nhân sự, cần xác định ai được phép tra cứu từng trường; có thể phải giới hạn kết quả theo phòng ban hoặc chủ sở hữu, chứ không chỉ kiểm tra một role chung.

Phía API nên phân biệt lỗi không tìm thấy (nếu chính sách cho phép) với lỗi kết nối LDAP và lỗi dữ liệu trùng, tránh biến mọi exception thành HTTP 404. Trong endpoint đăng nhập, đôi khi phải dùng phản hồi trung tính để không tiết lộ sự tồn tại của tài khoản.

## 8. Kiểm thử tích hợp với LDAP thật trong môi trường test

Unit test cho `DirectoryUserService` có thể giả lập repository để kiểm tra ba nhánh 0/1/nhiều kết quả. Nhưng muốn chứng minh **query, DN, ACL, matching rule và mapping thực sự đúng**, cần integration test trên directory test có schema và dữ liệu tương ứng.

### 8.1. JUnit 5 kiểm tra luồng end-to-end

Giả sử profile `ldap-it` sử dụng LDAPS và dữ liệu LDIF ở trên. Test chỉ được chạy khi người thực hiện bật biến môi trường `RUN_LDAP_IT=true`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-it")
@EnabledIfEnvironmentVariable(
        named = "RUN_LDAP_IT", matches = "true"
)
class DirectoryUserIntegrationTest {

    @Autowired
    private DirectoryUserService service;

    @Test
    void findsOneUserAndMapsAttributes() {
        DirectoryUser user =
                service.findOneByUid("lan").orElseThrow();

        assertThat(user.uid()).isEqualTo("lan");
        assertThat(user.fullName()).isEqualTo("Lan Tran");
        assertThat(user.email()).isEqualTo("lan@example.org");
        assertThat(user.relativeDn()).contains("uid=lan");
    }

    @Test
    void handlesMissingOptionalEmail() {
        DirectoryUser user =
                service.findOneByUid("minh").orElseThrow();

        assertThat(user.uid()).isEqualTo("minh");
        assertThat(user.email()).isNull();
    }

    @Test
    void doesNotTreatStarAsSearchWildcard() {
        assertThat(service.findOneByUid("*")).isEmpty();
    }

    @Test
    void rejectsBlankUsernameBeforeSearching() {
        assertThat(service.findOneByUid(" ")).isEmpty();
        assertThat(service.findOneByUid(null)).isEmpty();
    }
}
~~~

Test `doesNotTreatStarAsSearchWildcard` giả định directory test **không có** entry mang literal `uid=*`. Ý nghĩa cần kiểm chứng là filter builder không biến dữ liệu `*` thành điều kiện `uid=*` dạng wildcard. Trong môi trường khác, equality filter escaped có thể khớp một entry có UID literal là dấu sao nếu schema và dữ liệu cho phép.

Trên một directory thực, thứ tự và cách biểu diễn DN, matching rule hoặc quyền đọc attribute có thể khác. Hãy kiểm tra schema/ACL trước khi thay assertion để tránh che giấu lỗi cấu hình.

### 8.2. Kiểm thử các ca nâng cao

| Kịch bản | Cách dựng trên LDAP test | Điều cần assert |
|---|---|---|
| Không có user | Tìm `uid=unknown` | `Optional.empty()` |
| Một user hợp lệ | Entry `uid=lan` với `cn` và `mail` | Domain object có đúng trường |
| Thiếu `mail` | Entry `uid=minh` không có mail | `email == null`, không mất user |
| UID chứa `*` hoặc dấu ngoặc | Tạo input đặc biệt, không nối filter | Truy vấn không nới rộng hoặc lỗi parser |
| Hai user cùng `uid` ở hai OU con | Tạo hai DN khác nhau trong phạm vi `SUBTREE` | Service phát hiện nhiều entry và từ chối |
| User ở ngoài `ou=people` | Tạo entry ở OU khác | Không lọt vào kết quả |
| Dùng `ONELEVEL` thay `SUBTREE` | Đặt user dưới OU con | User trong OU con không được tìm thấy |
| Account không được đọc `mail` | ACL chỉ cấp đọc `uid` và `cn` | Domain không lộ mail; xử lý thiếu attr đúng |
| Service bind sai credential | Đổi secret trên môi trường test | Lỗi LDAP connection/auth; không đổi thành “không tìm thấy” |
| Chứng chỉ LDAPS không hợp lệ | Endpoint TLS test kiểm soát | Kết nối bị từ chối; không tắt xác minh |
| Hết thời gian truy vấn | Server/proxy test gây timeout | Lỗi hạ tầng được ghi nhận riêng |

**Cách dựng trùng UID:** LDAP không cho hai entry có cùng DN, nhưng có thể có `uid=lan` ở `ou=employees` và `ou=contractors`. Nếu cả hai nằm dưới vùng `SUBTREE` mà ứng dụng tìm, chúng tạo ra trường hợp **nhiều DN cùng giá trị `uid`**, dù DN của từng entry riêng biệt.

### 8.3. Unit test và integration test khác nhau

- **Unit test repository/service:** kiểm tra quy tắc đầu vào, dữ liệu không duy nhất, mapping logic bằng stub/fixture; chạy nhanh, không cần mạng LDAP.
- **Integration test Spring LDAP:** xác minh `ContextSource`, TLS, base DN, filter, schema, ACL và kết quả thực.
- **HTTP authorization test:** xác minh người dùng có/không có authority được phép truy cập API, độc lập với việc backend sử dụng service account LDAP có quyền search.

Một test với mock `LdapTemplate` không chứng minh LDAP server có đúng dữ liệu, filter được đánh giá theo matching rule nào hay chứng chỉ TLS có hợp lệ.

## 9. Xử lý lỗi có chủ đích

Thao tác tìm user có thể thất bại bởi nhiều nguyên nhân khác nhau:

| Hiện tượng | Ý nghĩa có thể có | Xử lý nên làm |
|---|---|---|
| Search trả danh sách rỗng | Không có entry phù hợp trong vùng/quyền được thấy | Trả rỗng theo hợp đồng API |
| Nhiều entry cùng `uid` | Dữ liệu định danh mơ hồ | Từ chối lựa chọn bất kỳ; sửa chính sách uniqueness |
| Thuộc tính `cn` hoặc `uid` thiếu | Schema dữ liệu không đáp ứng domain model | Ghi lỗi dữ liệu, không tạo object giả |
| `mail` thiếu | Thuộc tính tùy chọn không có | Giữ `null` hoặc dùng `Optional` theo thiết kế |
| Lỗi `invalidCredentials` của service account | Không thể search đúng cách | Kiểm tra tài khoản dịch vụ/secret |
| `insufficientAccessRights` | Không đủ quyền search/read attribute | Rà soát ACL theo nguyên tắc ít quyền nhất |
| Base DN không tồn tại | Search sai vùng dữ liệu | Kiểm tra `spring.ldap.base` và OU |
| Kết nối TLS lỗi | CA/hostname/cert không tin cậy | Sửa TLS; không chuyển sang plaintext |
| Timeout / server unavailable | Lỗi directory hoặc mạng | Retry có giới hạn theo chính sách, log correlation ID |

Không dùng:

~~~java
// KHÔNG NÊN: che lỗi hạ tầng thành "không có user".
try {
    return repository.searchByUid(uid);
} catch (Exception ignored) {
    return java.util.List.of();
}
~~~

Thay vào đó, giữ phân biệt **not found**, **data invalid**, **ambiguous identity** và **LDAP unavailable**. Ở ranh giới API hoặc background job, map những tình huống đó thành phản hồi/đường phục hồi phù hợp. Không ghi credential, hash mật khẩu hoặc toàn bộ entry vào log khi debug.

## 10. Bảo mật và hiệu năng khi triển khai thật

### 10.1. Quyền truy cập LDAP và quyền của ứng dụng

Tài khoản dịch vụ chỉ nên có quyền tìm/đọc thuộc tính đã định nghĩa trong `ou=people`. Nếu backend dùng service account để đọc LDAP, server áp ACL của **service account**, không tự kiểm tra quyền của người dùng HTTP đang yêu cầu tra cứu.

Vì vậy, nếu API trả thông tin nhân viên, Spring Security hoặc tầng nghiệp vụ vẫn phải xác minh ai được xem dữ liệu đó. **LDAP search thành công không đồng nghĩa user HTTP được phép xem entry.**

### 10.2. Không nhầm tra cứu với xác thực

`DirectoryUserService.findOneByUid("lan")` chỉ chứng minh ứng dụng tìm thấy entry. Nó **không chứng minh người gọi biết mật khẩu của Lan**. Với đăng nhập, sử dụng quy trình user bind hoặc Spring Security LDAP phù hợp; từ chối password rỗng và dùng kết quả xác thực để cấp principal/authorities riêng.

### 10.3. Kiểm soát dữ liệu và hiệu năng

- Dùng filter equality và bảo đảm directory có index hợp lý cho `uid` nếu quy mô lớn.
- Giới hạn search base, scope và các attribute trả về; tránh quét toàn cây chỉ để tìm một user.
- Cấu hình size limit, time limit và timeout thích hợp với yêu cầu dịch vụ; xử lý rõ kết quả bị giới hạn.
- Không gọi search liên tục trên mỗi request nếu đã có cache hợp lý, nhưng cache phải có TTL/refresh và chính sách vô hiệu hóa phù hợp với độ mới dữ liệu.
- Nếu tra cứu bằng email, đừng mặc định `mail` là duy nhất; hãy định nghĩa rõ cách xử lý nhiều entry khớp.
- Không log toàn bộ filter chứa thông tin nhạy cảm hoặc kết quả LDAP nếu không cần thiết.
- Dùng LDAPS/StartTLS với CA/hostname verification; kiểm tra pooling không làm lẫn danh tính user-bind với service-bind.
- Với các thuộc tính nhiều giá trị (nhóm, số điện thoại), dùng kiểu collection và mapper phù hợp thay vì lặng lẽ lấy giá trị đầu tiên.

## 11. Bài tập mở rộng

1. **Tra cứu bằng email:** Thêm `searchByMail(String mail)` với `where("mail").is(mail)`. Thử khi hai entry có cùng email và quy định cách xử lý.
2. **Tùy chọn scope:** Tạo hai ca `ONELEVEL` và `SUBTREE` để thấy khác biệt khi user nằm ở OU con.
3. **Bổ sung department:** Thêm một trường tùy chọn `department` vào domain và đọc duy nhất attribute đó; kiểm thử khi attribute vắng.
4. **Kiểm thử duplicate:** Dùng hai DN khác nhau cùng `uid`, xác nhận service không chọn user đầu tiên.
5. **Bảo vệ REST:** Tạo integration test chứng minh user không có `DIRECTORY_READ` bị từ chối dù service account LDAP có quyền search.
6. **Đối chiếu ODM:** Viết cùng bài toán bằng mapping annotation của Spring LDAP ODM, so sánh độ phức tạp khi chỉ đọc và khi cần CRUD.

### Câu hỏi tự kiểm tra

1. Vì sao nên dùng `LdapQueryBuilder` thay vì ghép trực tiếp `username` vào filter?
2. `.attributes("uid","cn","mail")` giải quyết vấn đề gì?
3. Tại sao dùng `ContextMapper` thuận tiện hơn `AttributesMapper` khi cần lấy DN?
4. Nếu `mail` không có nhưng `uid` và `cn` hợp lệ, domain object nên được tạo thế nào?
5. Nếu `SUBTREE` tìm thấy hai DN cùng `uid`, vì sao không nên gọi `results.get(0)`?
6. `getDn()` trả DN ở ngữ cảnh nào, và vì sao không nên mặc định nó luôn là DN tuyệt đối?
7. Nếu lookup trả về entry của Lan, Lan đã đăng nhập thành công chưa?
8. Tại sao backend có quyền đọc LDAP vẫn phải kiểm tra authorization trước khi trả thông tin user cho HTTP client?

**Gợi ý:** (1) Builder escape giá trị literal và giữ filter có cấu trúc. (2) Giới hạn dữ liệu đọc. (3) Context mapper truy cập được metadata DN và attribute. (4) Để `email=null` hoặc biểu diễn optional theo hợp đồng. (5) Tên định danh mơ hồ, thứ tự kết quả không là chính sách. (6) Thường tương đối với context base; phải kiểm tra trước khi dùng ngoài ngữ cảnh. (7) Chưa, search không kiểm tra mật khẩu. (8) LDAP server chỉ thấy quyền của danh tính bind thực hiện search; quyền ứng dụng là một lớp riêng.

## Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, query builder, mapping và ODM.
- [Spring LDAP API — LdapQueryBuilder](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): xây truy vấn bằng builder.
- [Spring LDAP API — DirContextOperations](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html): truy cập DN và thuộc tính từ context.
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp filter và escape ký tự.

## Kết luận

Một bài toán tra cứu user bằng **Spring LDAP** nên đi từ `LdapQueryBuilder` với filter equality an toàn, qua `LdapTemplate.search(...)`, rồi dùng `ContextMapper`/`DirContextOperations` để ánh xạ entry thành **domain object bất biến**. Tách repository khỏi service giúp kiểm soát rõ trường bắt buộc, thuộc tính tùy chọn và tình huống định danh trùng. Khi triển khai, cần giữ đúng search base/scope, giới hạn dữ liệu trả về, bảo vệ kết nối bằng TLS, cấp quyền tối thiểu cho service account và **không nhầm directory lookup với xác thực hoặc phân quyền người dùng**.
