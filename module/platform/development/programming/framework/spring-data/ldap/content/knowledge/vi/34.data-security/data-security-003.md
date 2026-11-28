# Kiểm soát tên thuộc tính, base và scope do người dùng cung cấp

Một API tra cứu nhân viên có thể nhận các tham số như `field=uid`, `value=lan`, `base=ou=people` và `scope=subtree`. Những tham số này trông giống dữ liệu tìm kiếm thông thường, nhưng thực tế chúng không có cùng mức độ rủi ro. **Giá trị** `lan` được so khớp với thuộc tính; **tên thuộc tính**, **search base DN** và **search scope** quyết định *truy vấn kiểm tra điều gì, bắt đầu ở đâu và bao phủ những entry nào*. Nếu người dùng có thể tự chọn ba yếu tố cuối mà không qua chính sách ứng dụng, truy vấn có thể vượt sang nhánh tài khoản dịch vụ, nhóm quản trị hoặc đọc lượng dữ liệu lớn ngoài nhu cầu nghiệp vụ.

Trong module **SPRING_DATA_LDAP**, ứng dụng dùng Spring Data LDAP repository hoặc Spring LDAP `LdapTemplate` để tra cứu các entry LDAP phân cấp, ánh xạ `objectClass`/schema thành đối tượng Java và thực hiện CRUD khi được phép. Bài **Bảo mật dữ liệu** này tập trung vào một nguyên tắc: **chỉ nhận dữ liệu đầu vào từ client; cấu trúc truy vấn và ranh giới truy cập do server quyết định**. Query builder giúp escape giá trị filter, còn tên attribute, base DN và scope phải được kiểm soát riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `filter value`, `attribute name`, `search base`, `search scope` và **returning attributes** trong một LDAP search.
2. Giải thích vì sao escape giá trị filter không biến một tên thuộc tính hay base DN tùy ý thành an toàn.
3. Thiết kế allowlist ánh xạ lựa chọn của client sang attribute và nhánh LDAP do ứng dụng định nghĩa.
4. Giới hạn `SearchScope.OBJECT`, `SearchScope.ONELEVEL` và `SearchScope.SUBTREE` theo nghiệp vụ và quyền người gọi.
5. Dùng `LdapQueryBuilder`, `LdapTemplate` và DTO để giới hạn truy vấn cũng như dữ liệu trả ra.
6. Áp dụng authorization, LDAP ACL, timeout, count limit và kiểm thử đầu vào nhằm chống truy vấn vượt nhánh, lộ thuộc tính và quá tải.

## 2. Một truy vấn LDAP gồm những phần nào?

Directory minh họa:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=partners
│   └── uid=hoa
├── ou=groups
│   └── cn=directory-admins
└── ou=services
    └── cn=sync-reader
~~~

Ứng dụng được cấu hình `spring.ldap.base=dc=example,dc=org`. Một yêu cầu tra cứu an toàn có thể được mô tả như sau:

~~~text
Base DN:      ou=people                   (tương đối với dc=example,dc=org)
Scope:        ONELEVEL
Filter:       (&(objectClass=inetOrgPerson)(uid=lan))
Return attrs: uid, cn
Count limit:  50
Time limit:   2000 ms
~~~

| Thành phần | Ý nghĩa | Khi bị client tự điều khiển |
| --- | --- | --- |
| **Giá trị filter** | `lan` trong điều kiện `uid=lan`. | Có thể làm thay đổi biểu thức filter nếu nối chuỗi thiếu escaping. |
| **Tên thuộc tính tìm kiếm** | `uid`, `cn`, `mail`, `objectClass`… | Có thể chuyển sang thuộc tính nhạy cảm, không cần thiết hoặc tên không hợp lệ. |
| **Search base DN** | Nhánh bắt đầu tìm, ví dụ `ou=people`. | Có thể mở rộng sang `dc=example,dc=org` hay nhánh `ou=services`. |
| **Search scope** | Chỉ base, cấp con trực tiếp hoặc toàn bộ cây con. | Có thể mở rộng truy vấn thành quét nhiều OU/tập dữ liệu lớn. |
| **Returning attributes** | Những trường client được yêu cầu server trả về. | Có thể lộ thêm dữ liệu cá nhân, thuộc tính nhóm hoặc metadata. |
| **Filter logic** | Tổ hợp AND/OR, wildcard và các điều kiện. | Có thể thành truy vấn quá rộng hoặc vượt mục đích nghiệp vụ. |

Không có một thao tác escaping đơn lẻ bảo vệ tất cả các thành phần trên. Spring LDAP xử lý escaping **giá trị filter** khi dùng `LdapQueryBuilder.where(...).is(value)`; ứng dụng phải tự xác định danh sách tên thuộc tính, base, scope và các phép toán mà người dùng được chọn.

## 3. Mô hình đe dọa

Giả sử ứng dụng cung cấp endpoint:

~~~http
GET /api/directory/search?field=uid&value=lan&base=ou=people&scope=onelevel
~~~

Một thiết kế thiếu kiểm soát có thể viết:

~~~java
// Ví dụ KHÔNG AN TOÀN: minh họa lỗi thiết kế, không dùng trong ứng dụng.
LdapQuery query = LdapQueryBuilder.query()
        .base(userSuppliedBase)
        .searchScope(userSuppliedScope)
        .where(userSuppliedField)
        .is(userSuppliedValue);
~~~

Ngay cả khi `.is(userSuppliedValue)` escape giá trị, ba tham số còn lại vẫn quyết định cấu trúc truy vấn:

- Client thay `field` thành một thuộc tính nhạy cảm hoặc thuộc tính mà API không được phép dùng để tìm kiếm.
- Client đổi `base` từ `ou=people` thành gốc rộng hơn `dc=example,dc=org` hoặc nhánh `ou=services`.
- Client yêu cầu `SUBTREE` thay cho `ONELEVEL`, tìm cả những nhánh con trước đây không nằm trong phạm vi chức năng.
- Client yêu cầu trả toàn bộ thuộc tính, kể cả những trường mà người dùng HTTP không cần biết.

**LDAP ACL vẫn là lớp bảo vệ độc lập.** Nếu tài khoản dịch vụ bị giới hạn ACL đúng, server có thể ngăn đọc một số entry/thuộc tính. Nhưng không nên xem ACL là lý do để cho phép client tùy ý tạo truy vấn: ứng dụng vẫn phải bảo vệ ranh giới nghiệp vụ, tài nguyên hệ thống và dữ liệu mà tài khoản dịch vụ *có quyền đọc* nhưng người gọi HTTP *không có quyền xem*.

## 4. Phân biệt filter escaping, DN escaping và allowlist

LDAP có những cú pháp riêng biệt:

| Loại dữ liệu | Cách xử lý phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Giá trị trong LDAP search filter | `where("uid").is(input)` hoặc filter builder có escaping theo RFC 4515. | Không làm cho **tên attribute** do client đưa vào trở nên được phép. |
| Giá trị RDN khi tạo DN | `LdapNameBuilder.add("uid", input)` hoặc API `LdapName`. | Không cho phép client tự chọn nhánh DN hay quyền truy cập. |
| Tên attribute, ví dụ `uid` | Tra cứu từ **allowlist** do server định nghĩa. | Một regex kiểm tra ký tự hợp lệ không xác nhận quyền dùng attribute. |
| Base DN | Chọn từ tập DN do server cấu hình và gắn với policy. | DN hợp lệ về cú pháp chưa chắc thuộc vùng được quyền tìm. |
| Search scope | Chọn từ tập giá trị enum/phép ánh xạ do server duyệt. | `SUBTREE` không phù hợp chỉ vì là hằng số hợp lệ của API. |
| Returned attributes | Danh sách cố định theo DTO và quyền người gọi. | `*` hoặc “lấy tất cả” không phải lựa chọn mặc định an toàn. |

Ví dụ, API cho phép tìm `uid` và `cn`. Nếu user gửi `field=userPassword`, tên này có thể đúng cú pháp LDAP attribute description nhưng **không nằm trong yêu cầu nghiệp vụ**. Một regex kiểu `[A-Za-z][A-Za-z0-9-]*` vẫn chấp nhận nó. Vì vậy **allowlist theo nghĩa nghiệp vụ** phải được áp dụng trước khi xây `LdapQuery`.

Việc cố sửa tất cả bằng cách thay ký tự đặc biệt trong một chuỗi tùy ý thường dễ bỏ sót trường hợp DN, filter hoặc attribute options. Tốt hơn là server nhận **mã lựa chọn cấp ứng dụng** (ví dụ `username`, `displayName`), rồi tự ánh xạ sang thành phần LDAP đã kiểm tra.

## 5. Kiểm soát tên thuộc tính tìm kiếm

### 5.1. Dùng mã field cấp API, không công khai toàn bộ schema

Thay vì nhận tên LDAP attribute tự do, API chỉ cho phép:

| Giá trị client được gửi | Attribute LDAP cố định | Ý nghĩa |
| --- | --- | --- |
| `username` | `uid` | Tìm theo tên đăng nhập. |
| `displayName` | `cn` | Tìm theo tên hiển thị chính xác. |

Giá trị `userPassword`, `memberOf`, `objectGUID`, `entryUUID` hay tên không biết đều bị từ chối trong endpoint này. Những thuộc tính đó có thể hợp lệ trong directory, nhưng endpoint tra cứu danh bạ không cần nhận chúng làm điều kiện tùy ý.

Ví dụ enum Java 17+:

~~~java
enum SearchField {
    USERNAME("uid"),
    DISPLAY_NAME("cn");

    private final String ldapAttribute;

    SearchField(String ldapAttribute) {
        this.ldapAttribute = ldapAttribute;
    }

    String ldapAttribute() {
        return ldapAttribute;
    }

    static SearchField fromClient(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Thieu truong tim kiem");
        }
        return switch (raw) {
            case "username" -> USERNAME;
            case "displayName" -> DISPLAY_NAME;
            default -> throw new IllegalArgumentException(
                    "Truong tim kiem khong duoc ho tro");
        };
    }
}
~~~

`SearchField.fromClient(...)` chuyển **chuỗi từ client** thành một tập hằng số tin cậy. Dù giá trị client chứa ký tự đặc biệt, nó không thể trở thành tên attribute vì chỉ hai lựa chọn chính xác được chấp nhận.

Không xem phép ánh xạ này là bước phân quyền duy nhất: nếu một attribute hợp lệ đối với quản trị viên nhưng nhạy cảm với nhân viên thông thường, hãy kiểm tra **role/quyền** tương ứng trước khi cho phép dùng.

### 5.2. Không cho client chọn filter operator tùy ý

Cần kiểm soát cả phép toán. Hai lời gọi này có phạm vi kết quả khác nhau:

~~~text
(uid=lan)          // so khớp theo matching rule của server
(uid=*)            // mọi entry có thuộc tính uid
~~~

Khi dùng `where("uid").is(value)`, một dấu `*` do user nhập là **giá trị literal được escape**, không được tự coi là wildcard. Nếu chức năng thật sự cần tìm theo tiền tố, nên định nghĩa rõ API `startsWith` riêng, validate độ dài tiền tố và giới hạn số kết quả; không chuyển toàn bộ biểu thức filter cho người dùng tùy ý soạn.

Các truy vấn filter tùy ý với AND/OR/NOT lồng nhau, wildcard hoặc substring có thể gây tiết lộ thông tin và tải lớn, ngay cả khi không có injection theo nghĩa cú pháp. Chúng cần một ngôn ngữ truy vấn được giới hạn rất chặt nếu sản phẩm bắt buộc hỗ trợ.

## 6. Kiểm soát search base DN

Với cấu hình `spring.ldap.base=dc=example,dc=org`, các nhánh hợp lệ trong ứng dụng có thể là:

~~~text
ou=people           -> ou=people,dc=example,dc=org
ou=partners         -> ou=partners,dc=example,dc=org
~~~

Thay vì nhận raw DN, client gửi **mã vùng**:

~~~http
GET /api/directory/search?area=people
GET /api/directory/search?area=partners
~~~

Ánh xạ tại server:

~~~java
enum SearchArea {
    PEOPLE("ou=people"),
    PARTNERS("ou=partners");

    private final String relativeBase;

    SearchArea(String relativeBase) {
        this.relativeBase = relativeBase;
    }

    String relativeBase() {
        return relativeBase;
    }

    static SearchArea fromClient(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Thieu vung tim kiem");
        }
        return switch (raw) {
            case "people" -> PEOPLE;
            case "partners" -> PARTNERS;
            default -> throw new IllegalArgumentException(
                    "Vung tim kiem khong duoc ho tro");
        };
    }
}
~~~

Như vậy, không có code nào đưa trực tiếp tham số `area` hay chuỗi DN tùy ý của user vào `.base(...)`. Ngay cả chuỗi giống `dc=example,dc=org` cũng bị từ chối nếu client không gửi đúng mã vùng đã định.

### 6.1. “Base hợp lệ” vẫn chưa có nghĩa “được quyền”

Ví dụ người dùng bình thường chỉ được tra cứu `people`; nhân viên bộ phận đối tác được tra cứu cả `partners`. Server cần kiểm tra role/permission tương ứng **sau khi chuyển mã area, trước khi gọi LDAP**. Nếu không, việc có enum `PARTNERS` vẫn khiến bất kỳ người đăng nhập nào cũng có thể mở vùng đó.

**Phân quyền theo vùng dữ liệu** phải được áp dụng tại service, cùng các quy tắc ownership/tenant khi cần. Nếu vùng phụ thuộc tenant của người gọi, hãy lấy tenant từ principal hoặc mapping server-side đáng tin cậy; không lấy một `tenantId` tùy ý rồi ghép thành DN để bỏ qua phân quyền.

### 6.2. Tại sao parse DN hợp lệ vẫn chưa đủ?

`LdapName`/`LdapNameBuilder` xử lý cấu trúc và escaping của DN, nhưng chúng không biết doanh nghiệp cho phép tìm `ou=services` hay không. Một DN có thể hoàn toàn hợp lệ mà vẫn ngoài phạm vi chức năng. Kiểm tra chuỗi bằng `startsWith("ou=people")` cũng không phải cách xác minh ranh giới DN đáng tin cậy: chuỗi hiển thị có escaping, thứ tự RDN và quy tắc so khớp riêng.

Nếu ứng dụng thật sự cần nhiều base động, hãy dùng **danh sách DN từ cấu hình được kiểm soát** hoặc policy gắn với tenant, parse/so sánh theo API DN và kiểm tra quan hệ nhánh trên dữ liệu tin cậy. Không dùng chuỗi DN do client cung cấp làm nguồn thẩm quyền.

## 7. Kiểm soát search scope

LDAP search có ba phạm vi tiêu biểu:

| Scope | Phạm vi | Ví dụ nếu base là `ou=people` |
| --- | --- | --- |
| `OBJECT` | Chỉ bản thân entry ở base DN. | Chỉ entry `ou=people`, không lấy `uid=lan` bên dưới. |
| `ONELEVEL` | Chỉ các entry con trực tiếp của base, không gồm base. | `uid=lan`, `uid=minh` nếu nằm trực tiếp dưới `ou=people`. |
| `SUBTREE` | Base và toàn bộ entry con ở mọi độ sâu. | Cả người dùng trong các OU con của `ou=people`. |

Ví dụ:

~~~text
ou=people
├── uid=lan                 <- ONELEVEL và SUBTREE
├── uid=minh                <- ONELEVEL và SUBTREE
└── ou=alumni               <- ONELEVEL và SUBTREE
    └── uid=an              <- chỉ SUBTREE, không thuộc ONELEVEL
~~~

`SUBTREE` có thể mở rộng phạm vi kết quả rất lớn. Không cho người dùng tùy ý chọn `SUBTREE` trên một base rộng; nếu chức năng cần tìm sâu, giới hạn base, filter, count/time limit và kiểm tra quyền tương ứng.

Trong API tra cứu nhân viên, server có thể chỉ cho phép hai mã phạm vi:

~~~java
import org.springframework.ldap.query.SearchScope;

enum SearchDepth {
    DIRECT(SearchScope.ONELEVEL),
    NESTED(SearchScope.SUBTREE);

    private final SearchScope scope;

    SearchDepth(SearchScope scope) {
        this.scope = scope;
    }

    SearchScope scope() {
        return scope;
    }

    static SearchDepth fromClient(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Thieu do sau tim kiem");
        }
        return switch (raw) {
            case "direct" -> DIRECT;
            case "nested" -> NESTED;
            default -> throw new IllegalArgumentException(
                    "Pham vi tim kiem khong duoc ho tro");
        };
    }
}
~~~

`OBJECT` vẫn hữu ích khi ứng dụng cần kiểm tra một DN cụ thể, nhưng API tra cứu nhiều người dùng không hỗ trợ mã scope đó vì nó không phù hợp với mục tiêu tìm các entry dưới OU. **Một enum scope hợp lệ trong thư viện chưa tự động là một lựa chọn hợp lệ của API.**

## 8. Ví dụ Spring Boot: endpoint tìm kiếm có kiểm soát

### 8.1. Dependency và kết nối

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các biến môi trường minh họa:

~~~dotenv
LDAP_URL=ldaps://ldap.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=directory-reader,ou=services,dc=example,dc=org
LDAP_BIND_PASSWORD=<secret-cua-moi-truong>
~~~

`LDAP_BIND_DN` là tài khoản dịch vụ, phải được directory cấp **ACL chỉ đọc** những nhánh và thuộc tính cần thiết. Trong production, dùng LDAPS hoặc StartTLS được cấu hình rõ ràng và xác minh chứng chỉ máy chủ. Không dùng tài khoản quản trị LDAP để cho phép mọi phép tra cứu.

### 8.2. DTO đầu ra

Ứng dụng chỉ trả những thuộc tính được thiết kế cho API:

~~~java
public record PersonSummary(
        String uid,
        String displayName) {
}
~~~

Không trả `DirContextOperations`, toàn bộ `Attributes` hoặc entity chứa các trường mà client không được biết. **Danh sách thuộc tính truy vấn và DTO phản hồi phải được kiểm soát độc lập** với lựa chọn `field` của user.

### 8.3. Service ghép các điều kiện an toàn

Các enum `SearchField`, `SearchArea`, `SearchDepth` đã định nghĩa ở trên được đặt cùng package (hoặc khai báo là kiểu phù hợp với cấu trúc project). Service:

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class SafeDirectorySearchService {
    private final LdapTemplate ldapTemplate;

    public SafeDirectorySearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @PreAuthorize("hasAuthority('DIRECTORY_SEARCH')")
    public List<PersonSummary> search(
            String rawField, String value, String rawArea, String rawDepth) {
        SearchField field = SearchField.fromClient(rawField);
        SearchArea area = SearchArea.fromClient(rawArea);
        SearchDepth depth = SearchDepth.fromClient(rawDepth);

        if (value == null || value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException(
                    "Gia tri tim kiem khong hop le");
        }

        Authentication caller =
                SecurityContextHolder.getContext().getAuthentication();

        if (area == SearchArea.PARTNERS &&
                !hasAuthority(caller, "DIRECTORY_PARTNERS_READ")) {
            throw new AccessDeniedException("Khong du quyen xem partners");
        }
        if (depth == SearchDepth.NESTED &&
                !hasAuthority(caller, "DIRECTORY_RECURSIVE_SEARCH")) {
            throw new AccessDeniedException("Khong du quyen tim sau");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base(area.relativeBase())
                .searchScope(depth.scope())
                .attributes("uid", "cn")
                .countLimit(50)
                .timeLimit(2000)
                .where("objectClass").is("inetOrgPerson")
                .and(field.ldapAttribute()).is(value);

        return ldapTemplate.search(
                query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                readString(attrs, "uid"),
                                readString(attrs, "cn")));
    }

    private static boolean hasAuthority(
            Authentication auth, String authority) {
        return auth != null && auth.isAuthenticated()
                && auth.getAuthorities().stream()
                    .anyMatch(a -> authority.equals(a.getAuthority()));
    }

    private static String readString(
            Attributes attrs, String name) throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

**Điểm bảo vệ trong ví dụ:**

1. `fromClient(...)` chấp nhận **chính xác** các mã field/area/depth nằm trong allowlist.
2. `@PreAuthorize` yêu cầu quyền tìm kiếm chung; service kiểm tra thêm quyền tìm trong `partners` và tìm sâu.
3. `.base(area.relativeBase())` dùng DN do ứng dụng định nghĩa. Input raw không được đưa trực tiếp vào DN.
4. `.searchScope(depth.scope())` dùng enum đã được server chọn và giới hạn theo quyền.
5. `.where(...).is(value)` escape **giá trị** do user cung cấp theo cú pháp LDAP filter.
6. `.attributes("uid", "cn")` chỉ yêu cầu hai trường đầu ra đã được duyệt; `countLimit` và `timeLimit` giảm nguy cơ truy vấn quá rộng.
7. `PersonSummary` chỉ có thông tin cần thiết, không lộ các thuộc tính khác của entry.

`readString(...)` cố ý cho phép `null` nếu thuộc tính không được trả về do schema, ACL hoặc projection. Ứng dụng thật cần định nghĩa quy tắc dữ liệu bắt buộc, kiểm soát trường tùy chọn và áp dụng chính sách bảo vệ thông tin cá nhân. Ví dụ dùng `timeLimit(2000)` và `countLimit(50)` để minh họa giới hạn, không bảo đảm mọi server luôn trả kết quả đầy đủ hoặc kết thúc đúng SLA.

### 8.4. Kích hoạt bảo vệ phương thức

Để `@PreAuthorize` được xử lý khi service được gọi qua Spring proxy, cần bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Ứng dụng còn cần cấu hình một cơ chế **authentication** phù hợp (LDAP bind authentication, OIDC hoặc cơ chế khác) để có `Authentication` và các authority chính xác; thêm dependency Spring Security **không tự tạo các quyền** `DIRECTORY_SEARCH`/`DIRECTORY_PARTNERS_READ`/`DIRECTORY_RECURSIVE_SEARCH`. Cần cấu hình authorization cho HTTP endpoint, tránh mở toàn bộ API mặc định.

`@PreAuthorize` chỉ áp dụng khi qua Spring-managed proxy; lời gọi nội bộ (*self-invocation*) có thể bỏ qua proxy. Hãy bố trí kiểm tra quyền tại ranh giới service có thể được gọi từ nhiều controller hoặc tác vụ nội bộ, và kiểm thử những đường gọi thật.

### 8.5. Controller nhận mã lựa chọn, không nhận raw LDAP query

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/directory")
public class DirectorySearchController {
    private final SafeDirectorySearchService service;

    public DirectorySearchController(SafeDirectorySearchService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public List<PersonSummary> search(
            @RequestParam String field,
            @RequestParam String value,
            @RequestParam String area,
            @RequestParam String depth) {
        return service.search(field, value, area, depth);
    }
}
~~~

Ví dụ request hợp lệ:

~~~http
GET /api/directory/search?field=username&value=lan&area=people&depth=direct
~~~

Một người có quyền `DIRECTORY_SEARCH` nhưng không có quyền tìm sâu hoặc đọc đối tác sẽ chỉ tìm được trong nhánh người dùng cấp trực tiếp theo chính sách đã thiết kế. Nếu muốn API có mặc định `area`/`depth`, hãy quy định ở phía server; đừng mặc định root `dc=example,dc=org` hoặc `SUBTREE`.

Đây là **ví dụ về policy ở service**. Trong sản phẩm thực, bạn có thể dùng policy object hoặc authorization manager được kiểm thử tập trung thay vì viết `if` trong từng service, nhưng nguồn dữ liệu đáng tin cậy vẫn phải là principal và cấu hình server.

## 9. Repository và `LdapTemplate`: ranh giới truy vấn nằm ở đâu?

Spring Data LDAP repository rất hữu ích khi truy vấn được định nghĩa cố định bằng method, ví dụ:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Entity `PersonEntry` được ánh xạ bằng `@Entry(base = "ou=people", objectClasses = {...})`, với DN và attribute phù hợp schema. Phương thức `findByUid` tự giới hạn **tên thuộc tính** được chọn trong method: client chỉ cung cấp giá trị `uid`. Đây là điểm thuận lợi của repository đối với các truy vấn đã biết trước.

Tuy nhiên, **repository không tự giải quyết authorization HTTP**. Nếu một endpoint trả về nguyên entity có nhiều attribute, người gọi có thể thấy những trường mà họ không được phép xem. Repository cũng không ngăn người viết code thêm các đường query khác tới nhánh rộng hơn. Hãy tách DTO và kiểm tra quyền ở service.

Với `LdapTemplate`, bạn có thể điều khiển trực tiếp base, scope và projection; vì vậy trách nhiệm kiểm soát các thành phần đó càng rõ ràng. **Không coi `LdapTemplate` có filter builder là đủ an toàn khi API cho phép chọn cấu trúc truy vấn.**

### Khi nào dùng cấu hình base khác?

Nếu toàn bộ module chỉ được phép làm việc dưới `ou=people,dc=example,dc=org`, có thể đặt `spring.ldap.base` ở đúng OU đó. Khi ấy các DN tương đối phải tính lại và API không cần nhận `area`. Đây là lớp giảm phạm vi cấu hình hữu ích, nhưng vẫn phải duy trì ACL server và authorization ứng dụng. Với ứng dụng phải truy cập nhiều OU, giữ base chung và áp dụng allowlist như ví dụ.

## 10. Giới hạn tài nguyên và tránh truy vấn quá rộng

Ngay cả một query hợp cú pháp và hợp quyền cũng có thể tiêu tốn nhiều tài nguyên. Ví dụ `(cn=*)` trên root kèm `SUBTREE` có thể đọc rất nhiều entry.

**Các biện pháp nên kết hợp:**

- **Base hẹp:** chỉ tìm ở OU mà chức năng cần; không lấy directory root làm mặc định.
- **Scope tối thiểu:** dùng `ONELEVEL` khi chỉ cần entry con trực tiếp; cho `SUBTREE` theo quyền và use case cụ thể.
- **Filter cụ thể:** kết hợp `objectClass`/thuộc tính đã chọn và giới hạn loại phép so khớp.
- **Giới hạn kết quả:** đặt count limit ở client/query và cấu hình size limit tại directory server khi thích hợp.
- **Giới hạn thời gian:** time limit của truy vấn, JNDI connect/read timeout và deadline của request HTTP. Các lớp này khác nhau.
- **Chống lạm dụng:** rate limit, quota, authentication, kiểm soát concurrency và giám sát truy vấn chậm.
- **Phân trang có kiểm soát:** khi cần danh sách lớn, dùng cơ chế phân trang tương thích server. Không mặc định tăng count limit vô hạn.

`countLimit(50)` không phải “bằng chứng chỉ có 50 entry tồn tại”; nó có thể **cắt bớt kết quả**. Nếu chức năng dùng danh sách này cho đối soát hoặc cấp phát quyền, phải phân biệt “đầy đủ” với “bị giới hạn”, theo thông tin server và cơ chế phân trang phù hợp.

Giới hạn thời gian ở client có thể không bao quát toàn bộ thời gian DNS, TLS, reconnect, phân trang hoặc response mapping; đo tổng thời gian thực tế với hạ tầng thật.

## 11. Chặn việc trả về thuộc tính không được phép

Không chỉ tên attribute trong filter mới nguy hiểm. Nếu API cho phép tham số:

~~~http
GET /api/directory/search?attributes=*
~~~

hoặc:

~~~java
// KHÔNG AN TOÀN nếu danh sách do client tạo tùy ý.
queryBuilder.attributes(userSuppliedAttributeNames);
~~~

thì một tài khoản dịch vụ có ACL rộng có thể đọc nhiều thuộc tính không dành cho người gọi HTTP. **Tập trả về phải được server quyết định** theo DTO và quyền, ví dụ `uid`/`cn` cho danh bạ và `mail` chỉ khi policy cho phép. LDAP có cú pháp đặc biệt như `*` cho user attributes và `+` cho operational attributes trên các server hỗ trợ; đừng cho client truyền chúng vào projection một cách tùy ý.

Một response DTO nhỏ cũng không thay thế được việc giới hạn projection: nếu query đã tải về thuộc tính nhạy cảm và sau đó mới loại bỏ, ứng dụng vẫn tăng rủi ro lộ qua log, debugger, tracing hoặc lỗi mapper. **Giới hạn ngay tại truy vấn và tiếp tục lọc ở đầu ra**.

Nếu endpoint hỗ trợ nhiều loại DTO, dùng các cấu hình xuất dữ liệu cố định do server định nghĩa, ví dụ:

| Mã kết quả | Thuộc tính yêu cầu | Quyền cần có |
| --- | --- | --- |
| `publicDirectory` | `uid`, `cn` | `DIRECTORY_SEARCH`. |
| `contactDirectory` | `uid`, `cn`, `mail` | Quyền đọc liên hệ bổ sung. |

Không cho client tự gõ tên attribute mới. Trường hợp cần truy cập metadata hệ thống hoặc nhóm LDAP, thiết kế API chuyên biệt với kiểm tra quyền và audit tương ứng.

## 12. Kiểm thử an toàn bằng directory thử nghiệm

### 12.1. Chuẩn bị cây dữ liệu

Tạo dữ liệu thử nghiệm có nhiều nhánh:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   ├── uid=minh
│   └── ou=alumni
│       └── uid=an
├── ou=partners
│   └── uid=hoa
└── ou=services
    └── cn=sync-reader
~~~

Ứng dụng dùng một tài khoản `directory-reader` chỉ có quyền đọc một tập thuộc tính cụ thể, cùng các tài khoản HTTP thử nghiệm:

- **User A:** có `DIRECTORY_SEARCH`.
- **User B:** có thêm `DIRECTORY_RECURSIVE_SEARCH`.
- **User C:** có thêm `DIRECTORY_PARTNERS_READ`.

Điều quan trọng là kiểm tra cả **quyền HTTP** và **ACL LDAP** trên hai lớp riêng biệt. Đừng coi kết quả truy vấn bằng tài khoản bind là kiểm chứng người gọi API đã được phép xem dữ liệu.

### 12.2. Ma trận kiểm thử

| Tình huống | Dữ liệu vào | Kỳ vọng |
| --- | --- | --- |
| Field hợp lệ | `field=username`, `value=lan` | Tạo filter có thuộc tính `uid`, chỉ tìm nhánh cho phép. |
| Field không hỗ trợ | `field=userPassword` | Từ chối đầu vào, không gọi LDAP. |
| Field chứa dấu cú pháp filter | Chuỗi tên thuộc tính lạ gồm dấu ngoặc hoặc `*` | Từ chối theo allowlist, không diễn giải thành filter. |
| Giá trị filter có ký tự đặc biệt | `value=*` hoặc giá trị chứa `(`/`)` | Builder escape như literal; không nới rộng logic filter. |
| Base root được gửi trực tiếp | `area=dc=example,dc=org` | Từ chối: không có trong danh sách mã area. |
| Vùng nhạy cảm không đủ quyền | User A gửi `area=partners` | Từ chối tại authorization trước khi truy vấn. |
| Scope bị giả mạo | `depth=SUBTREE` hoặc `depth=unlimited` | Từ chối vì không phải mã được server hỗ trợ. |
| Tìm sâu không đủ quyền | User A gửi `depth=nested` | HTTP 403 theo chính sách. |
| Tìm sâu có quyền | User B gửi `depth=nested` ở `people` | Có thể thấy entry bên dưới `ou=alumni` trong cùng nhánh, nếu ACL cho phép. |
| Truy vấn quá dài hoặc rỗng | `value` có hơn 128 ký tự hoặc chỉ khoảng trắng | Từ chối theo validation. |
| Yêu cầu thuộc tính nhạy cảm | Client cố thêm `returnAttrs=userPassword` | Bỏ qua/thực hiện policy server, không đưa raw projection vào LDAP. |
| Search bị giới hạn 50 kết quả | Dữ liệu test vượt giới hạn | Không tuyên bố đây là toàn bộ directory; có tín hiệu kết quả bị giới hạn nếu cần nghiệp vụ. |
| LDAP timeout/ACL từ chối | Lỗi mạng/quyền từ server | Báo lỗi hệ thống/quyền đúng loại, không biến thành “không tìm thấy user”. |

### 12.3. Đối chiếu base, scope và filter bằng `ldapsearch`

Với công cụ OpenLDAP client, một truy vấn được kiểm soát có thể được kiểm tra độc lập:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s one \
  "(&(objectClass=inetOrgPerson)(uid=lan))" uid cn
~~~

`-W` yêu cầu nhập mật khẩu qua prompt. `-b` đặt base, `-s one` chọn các entry con trực tiếp. Khi đổi `-s one` thành `-s sub`, kết quả có thể gồm các entry ở OU con; điều đó minh họa vì sao scope là quyết định nghiệp vụ, không chỉ một tham số hiệu năng.

Lệnh trên dùng dữ liệu thử nghiệm với DN, tài khoản và quyền rõ ràng. `ldapsearch` thành công chứng minh server chấp nhận phép đọc bằng **tài khoản dịch vụ**, không chứng minh API đã kiểm tra quyền người dùng HTTP. Kho CA của công cụ dòng lệnh và JVM cũng có thể khác nhau, cần kiểm tra TLS trong chính ứng dụng Java.

### 12.4. Unit test cho allowlist

Vì các enum chuyển mã không phụ thuộc LDAP server, chúng có thể được kiểm thử riêng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.query.SearchScope;

class DirectorySelectionTest {

    @Test
    void acceptsApprovedChoices() {
        assertEquals("uid",
                SearchField.fromClient("username").ldapAttribute());
        assertEquals("ou=people",
                SearchArea.fromClient("people").relativeBase());
        assertEquals(SearchScope.ONELEVEL,
                SearchDepth.fromClient("direct").scope());
    }

    @Test
    void rejectsUnapprovedAttributeBaseAndScope() {
        assertThrows(IllegalArgumentException.class,
                () -> SearchField.fromClient("userPassword"));
        assertThrows(IllegalArgumentException.class,
                () -> SearchArea.fromClient("ou=services"));
        assertThrows(IllegalArgumentException.class,
                () -> SearchDepth.fromClient("SUBTREE"));
    }
}
~~~

Để kiểm chứng toàn bộ ranh giới, cần thêm **integration test** với directory thử nghiệm, Spring Security và ACL thực tế: xác nhận các trường hợp bị từ chối không gọi LDAP, một người dùng không đủ quyền không xem được `partners`, và giới hạn attribute/size/scope đúng như thiết kế. Unit test enum không thay thế kiểm thử truy vấn và phân quyền thực.

## 13. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Sửa như thế nào |
| --- | --- | --- |
| `where(request.field).is(request.value)` | Escape value nhưng để client quyết định attribute. | Map `field` từ allowlist cố định. |
| `base(request.base)` | Client có thể chọn nhánh rộng hơn hoặc nhánh nhạy cảm. | Chọn base từ policy/configuration có kiểm chứng. |
| Chuyển trực tiếp chuỗi `scope` thành enum rồi chấp nhận mọi giá trị. | Dù hợp cú pháp, `SUBTREE` có thể trái chức năng. | Allowlist scope theo endpoint và role. |
| Dùng regex để “xác minh DN/attribute an toàn”. | Cú pháp hợp lệ không quyết định phân quyền; có thể bỏ sót DN đặc biệt. | Server chọn DN/attribute từ cấu hình nghiệp vụ. |
| Chỉ giới hạn response DTO, vẫn query tất cả thuộc tính. | Thuộc tính nhạy cảm vẫn đi qua ứng dụng. | Dùng `attributes(...)` cố định và DTO được duyệt. |
| Chỉ dựa vào LDAP ACL của tài khoản dịch vụ. | ACL không biết quyền riêng của từng caller HTTP nếu truy vấn cùng một bind DN. | Kiểm tra authorization tại service/API và ACL tối thiểu tại directory. |
| Cho phép root + subtree + filter rộng. | Có thể quét lượng dữ liệu lớn, ảnh hưởng hiệu năng và tiết lộ thông tin. | Base hẹp, scope nhỏ, filter cụ thể, count/time/rate limit. |
| Xem kết quả rỗng hoặc bị giới hạn là “không tồn tại”. | Có thể do ACL, timeout, giới hạn server hoặc scope. | Phân biệt không tìm thấy, lỗi, và tập kết quả chưa đầy đủ. |
| Log nguyên request/filter/entry cùng thông tin nhạy cảm. | Lộ PII, DN nội bộ hoặc dữ liệu không được phép. | Giảm dữ liệu log, ẩn bí mật, ghi audit theo chính sách. |

## 14. Bài tập tình huống

Một ứng dụng nội bộ có ba nhóm dữ liệu trong LDAP:

~~~text
dc=company,dc=internal
├── ou=employees
│   ├── uid=mai
│   └── ou=former
│       └── uid=an
├── ou=vendors
│   └── uid=binh
└── ou=services
    └── cn=ldap-backup
~~~

Tài khoản dịch vụ của ứng dụng có thể đọc `uid`, `cn` và `mail` ở `employees` và `vendors`. Người dùng HTTP có quyền `EMPLOYEE_SEARCH`; nhân viên mua hàng có thêm `VENDOR_SEARCH`; quản trị được duyệt có thêm `RECURSIVE_SEARCH`. API nhận `field`, `value`, `area` và `depth`.

**Yêu cầu:**

1. Đề xuất mã field cho tìm theo `uid`/`cn`, mã area cho `employees`/`vendors` và mã depth cho `ONELEVEL`/`SUBTREE`.
2. Chỉ ra lý do không nhận `field` là tên attribute tùy ý hoặc `area` là raw DN.
3. Viết `LdapQueryBuilder` cho user có quyền tìm nhân viên trực tiếp theo `uid=mai`, chỉ trả `uid` và `cn`.
4. Nếu user gửi `value=*`, giải thích vì sao `.is(value)` phải so khớp giá trị literal chứ không mở rộng thành `(uid=*)`.
5. Nếu chỉ có `EMPLOYEE_SEARCH` mà yêu cầu `area=vendors` và `depth=nested`, những kiểm tra nào phải từ chối request?
6. Tại sao `countLimit(50)` không đủ để kết luận directory chỉ có tối đa 50 người dùng?
7. Nếu `ldapsearch` thấy `uid=binh` bằng tài khoản dịch vụ, API có được trả `binh` cho mọi caller HTTP không?
8. Nêu cách kiểm thử trường hợp client cố tìm dưới `ou=services` và trường hợp người dùng chỉ được tìm direct nhưng muốn xem người dùng trong `ou=former`.

**Gợi ý trả lời:**

- Allowlist của API có thể là `username→uid`, `displayName→cn`, `employees→ou=employees`, `vendors→ou=vendors`, `direct→ONELEVEL` và `nested→SUBTREE`; các lựa chọn do server quy định.
- Tên attribute và base hợp cú pháp vẫn có thể làm truy vấn nhạy cảm; filter builder chỉ escape giá trị filter, không tự phân quyền tên field/base/scope.
- Query dùng `.base("ou=employees").searchScope(SearchScope.ONELEVEL).attributes("uid", "cn").where("objectClass").is("inetOrgPerson").and("uid").is("mai")`, với base chung `dc=company,dc=internal`.
- Giá trị `*` từ người dùng được escape trong phép `is`; muốn hỗ trợ wildcard cần use case/phép toán riêng có kiểm soát.
- User cần `VENDOR_SEARCH` để tìm `vendors` và `RECURSIVE_SEARCH` để tìm sâu; không có thì từ chối trước khi đọc LDAP.
- Count limit hạn chế số kết quả trả về; không phải thống kê toàn directory và có thể cắt cụt.
- Tài khoản dịch vụ đọc được không đồng nghĩa mọi caller có quyền xem; cần kiểm tra authorization HTTP và ACL LDAP.
- Test xác nhận area ngoài allowlist bị từ chối, direct scope không trả entry trong OU con, và nested scope chỉ được dùng với authority phù hợp.

## 15. Ghi nhớ

**Tên thuộc tính, base DN, scope và returning attributes đều là cấu trúc truy vấn cần được server kiểm soát.** Hãy cho client chọn từ **mã nghiệp vụ thuộc allowlist**, ánh xạ sang tên attribute/base/scope ở server, rồi kiểm tra quyền của principal trước khi truy vấn. Dùng `LdapQueryBuilder.where(...).is(value)` để escape giá trị filter, `LdapNameBuilder` khi thật sự cần tạo DN từ RDN động, và các giới hạn count/time/rate để tránh lạm dụng.

Spring Data LDAP và `LdapTemplate` hỗ trợ truy cập entry, repository và CRUD, nhưng không thay cho authorization HTTP hoặc ACL của directory. Một API LDAP an toàn cần đủ **giới hạn cấu trúc truy vấn, kiểm tra quyền ứng dụng, ACL tối thiểu, TLS, DTO tối giản và kiểm thử với directory**.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4515 — String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [Spring LDAP — LDAP Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
