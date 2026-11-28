# Cấu hình URL, base DN và tài khoản kết nối

Spring Data LDAP giúp ứng dụng Java làm việc với dịch vụ thư mục LDAP qua `LdapTemplate` hoặc repository, ánh xạ các entry phân cấp thành đối tượng Java và thực hiện truy vấn/CRUD. Trước khi viết repository, cần cấu hình **đúng máy chủ**, **đúng gốc tìm kiếm** và **đúng danh tính dùng để kết nối**. Ba nhóm thông tin này độc lập với nhau nhưng cùng quyết định ứng dụng có đọc được directory hay không.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt URL LDAP, `base DN`, DN của entry và `bind DN` của tài khoản dịch vụ.
- Cấu hình `spring.ldap.urls`, `spring.ldap.base`, `spring.ldap.username` và `spring.ldap.password` trong Spring Boot.
- Giải thích vì sao repository/`LdapTemplate` tìm kiếm ở đúng nhánh LDAP, cũng như cách nhận biết cấu hình sai.
- Kiểm tra kết nối, xác thực và quyền truy cập bằng `ldapsearch`; áp dụng TLS, quản lý bí mật và filter an toàn.

## 2. Bốn khái niệm dễ nhầm lẫn

LDAP lưu dữ liệu dưới dạng **entry** có **distinguished name (DN)**. DN mô tả đường dẫn định danh của entry trong cây thư mục; mỗi thành phần như `dc`, `ou`, `uid`, `cn` là một *relative distinguished name* (RDN).

Giả sử directory minh họa có cấu trúc:

~~~text
dc=example,dc=org                       <- gốc dữ liệu
├── ou=people                            <- nhánh người dùng
│   └── uid=lan                          <- một entry người dùng
└── ou=system                            <- nhánh tài khoản dịch vụ
    └── cn=svc-reader                    <- tài khoản để ứng dụng bind
~~~

DN đầy đủ của người dùng `lan` là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **LDAP URL** | `ldaps://ldap.example.org:636` | Địa chỉ máy chủ, giao thức và cổng kết nối. |
| **Base DN** | `dc=example,dc=org` | Gốc tương đối mà các thao tác `LdapTemplate`/repository thường bắt đầu. |
| **DN của entry** | `uid=lan,ou=people,dc=example,dc=org` | Định danh một entry cụ thể trong cây LDAP. |
| **Bind DN** | `cn=svc-reader,ou=system,dc=example,dc=org` | Danh tính mà ứng dụng dùng để xác thực với máy chủ, kèm mật khẩu. |

Ví dụ, nếu `base DN` là `dc=example,dc=org` và truy vấn dùng base tương đối `ou=people`, phạm vi tìm kiếm thực tế là nhánh `ou=people,dc=example,dc=org`. Đặt `base DN` không làm di chuyển entry trong directory.

**Phân biệt quan trọng:** Bind DN có thể thuộc nhánh khác với nơi bạn tìm người dùng. Không dùng `uid=lan,...` làm tài khoản kết nối chỉ vì muốn đọc thông tin của người dùng `lan`. Trong nhiều ứng dụng, một tài khoản dịch vụ riêng có quyền đọc tối thiểu là đủ; nếu bài toán yêu cầu xác thực mật khẩu của từng người dùng, đó là một luồng xác thực riêng.

## 3. Chọn LDAP URL

URL chỉ tới endpoint của directory server:

~~~text
ldap://ldap.example.org:389
ldaps://ldap.example.org:636
ldap://localhost:1389
~~~

- `ldap://` thường dùng cổng **389**. Kết nối này **không tự mã hóa**; muốn mã hóa bằng StartTLS phải cấu hình nâng cấp kết nối riêng và bảo đảm server hỗ trợ.
- `ldaps://` thường dùng cổng **636** và thiết lập TLS ngay khi kết nối. Ứng dụng cần tin cậy chứng chỉ của máy chủ và xác minh hostname.
- Cổng là cấu hình thực tế của server, không bắt buộc phải là cổng mặc định. `localhost:1389` thường là cổng thử nghiệm hoặc cổng được ánh xạ từ container.
- `spring.ldap.urls` có thể khai báo nhiều endpoint trong một cấu hình; không nên xem đó là cơ chế tự động chia tải hay đảm bảo chuyển đổi dự phòng trong mọi trường hợp.

Đối với cấu hình Spring Boot thông thường, đặt **endpoint** trong `urls` và đặt **gốc dữ liệu** trong `base`. Không trộn DN, filter tìm kiếm hoặc mật khẩu vào chuỗi URL máy chủ.

## 4. Cấu hình Spring Boot bằng `application.yml`

Thêm Spring Data LDAP starter (ví dụ Gradle Kotlin DSL):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Sau đó khai báo `src/main/resources/application.yml`:

~~~yaml
spring:
  ldap:
    urls:
      - ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các biến môi trường minh họa cho **một directory thử nghiệm**:

~~~dotenv
LDAP_URL=ldap://localhost:1389
LDAP_BASE_DN=dc=example,dc=org
LDAP_BIND_DN=cn=svc-reader,ou=system,dc=example,dc=org
LDAP_BIND_PASSWORD=<mat-khau-duoc-cap-rieng>
~~~

Đây là **giá trị ví dụ**; chúng chỉ hoạt động nếu directory thực sự có base DN, tài khoản bind và mật khẩu tương ứng. Trong môi trường thật, ưu tiên `ldaps://` hoặc StartTLS đã cấu hình đúng. Cấp biến mật khẩu qua secret manager/cơ chế cấu hình bí mật của môi trường chạy; không commit bí mật vào Git hoặc đưa vào log.

| Thuộc tính | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `spring.ldap.urls` | Một hoặc nhiều URL của server LDAP. | Scheme, hostname, DNS, cổng, firewall và TLS. |
| `spring.ldap.base` | Hậu tố DN làm gốc cho các thao tác LDAP. | Entry gốc tồn tại; nhánh cần tìm nằm dưới gốc này. |
| `spring.ldap.username` | Danh tính dùng để bind. Ví dụ dùng DN đầy đủ. | Đúng tài khoản; dạng định danh được server chấp nhận. |
| `spring.ldap.password` | Mật khẩu của danh tính bind. | Được cấp qua secret; không để trống ngoài ý muốn. |

Spring Boot dùng các thuộc tính trên để tự cấu hình `LdapContextSource` và cung cấp `LdapTemplate`. Nếu repository nằm trong các package được Spring Boot quét tự động, có thể sử dụng repository LDAP mà không cần tự dựng lại kết nối. Khi đặt repository ở package khác, hãy cấu hình quét repository thích hợp, chẳng hạn `@EnableLdapRepositories`.

Bạn cũng có thể dùng `application.properties` tương đương:

~~~properties
spring.ldap.urls=${LDAP_URL}
spring.ldap.base=${LDAP_BASE_DN}
spring.ldap.username=${LDAP_BIND_DN}
spring.ldap.password=${LDAP_BIND_PASSWORD}
~~~

### Chọn `base DN` ở mức nào?

- `dc=example,dc=org`: có thể truy cập các nhánh liên quan nếu ACL của tài khoản bind cho phép.
- `ou=people,dc=example,dc=org`: phù hợp ứng dụng chỉ tìm người dùng trong nhánh này.
- `ou=system,dc=example,dc=org`: thường không phù hợp để tìm `ou=people` vì nhánh người dùng nằm ngoài gốc tìm kiếm.

Chọn một gốc đủ hẹp cho bài toán nhưng bao phủ các entry cần thiết. Nếu đặt `spring.ldap.base=ou=people,dc=example,dc=org`, đừng tiếp tục cộng `ou=people` vào truy vấn/repository vì sẽ tạo đường dẫn tương đối sai.

## 5. Base DN ảnh hưởng đến repository như thế nào?

Với `spring.ldap.base=dc=example,dc=org`, entry `uid=lan,ou=people,dc=example,dc=org` nằm trong nhánh tương đối `ou=people`.

Một entity minh họa:

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

    public Name getDn() { return dn; }
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

Khi gọi `personRepository.findByUid("lan")`, repository ánh xạ các thuộc tính LDAP sang `PersonEntry` và dùng cấu hình kết nối chung. `@Entry(base = "ou=people")` xác định nhánh entity tương đối với gốc đã cấu hình. `@Id` phải là DN kiểu `javax.naming.Name` và dùng annotation `org.springframework.ldap.odm.annotations.Id`; không thay bằng `org.springframework.data.annotation.Id`.

Danh sách `objectClasses` và thuộc tính chỉ là mẫu cho directory dùng schema `inetOrgPerson`. Nếu máy chủ sử dụng Active Directory, schema tùy chỉnh hoặc các object class bổ sung, phải đối chiếu schema thực tế trước khi ánh xạ. `uid` cũng không được bảo đảm là duy nhất trên mọi directory; ứng dụng cần có quy tắc định danh/kiểm tra tính duy nhất phù hợp.

### Cùng kết nối đó với `LdapTemplate`

Khi cần kiểm soát phạm vi và điều kiện tìm kiếm trực tiếp:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("uid").is(uid);

        return ldapTemplate.search(
            query,
            (AttributesMapper<String>) attributes ->
                String.valueOf(attributes.get("cn").get())
        );
    }
}
~~~

`.base("ou=people")` là phần **tương đối** so với `spring.ldap.base`. Khi giá trị `uid` đến từ đầu vào người dùng, dùng API tạo filter như `where("uid").is(uid)` để mã hóa giá trị đúng quy tắc LDAP. Tránh nối chuỗi thành `"(uid=" + uid + ")"` hoặc truyền dữ liệu không tin cậy vào filter thô. Nếu tự xây DN từ dữ liệu động, dùng API dựng `Name`/`LdapNameBuilder` để xử lý ký tự đặc biệt trong RDN.

## 6. Kiểm tra từ mạng đến quyền đọc

Nên xác minh từng tầng: **server có thể truy cập → TLS hợp lệ → bind thành công → base DN tồn tại → tìm thấy entry → đủ quyền đọc thuộc tính**.

Ví dụ dùng công cụ dòng lệnh `ldapsearch` trên máy có OpenLDAP client. Với server LDAPS:

~~~bash
# 1. Kiểm tra entry gốc và xác thực tài khoản dịch vụ
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=svc-reader,ou=system,dc=example,dc=org" -W \
  -b "dc=example,dc=org" -s base \
  "(objectClass=*)" dn

# 2. Tìm một người dùng dưới nhánh thực tế
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=svc-reader,ou=system,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(uid=lan)" dn uid cn
~~~

Tham số `-W` yêu cầu nhập mật khẩu tương tác, tránh để mật khẩu nằm trong lịch sử lệnh hoặc danh sách tiến trình. `-s base` chỉ kiểm tra entry gốc, còn `-s sub` tìm trong toàn bộ cây con. Khi dùng StartTLS trên kết nối `ldap://`, công cụ OpenLDAP thường dùng `-ZZ` để **bắt buộc** nâng cấp TLS; việc này không đồng nghĩa Spring Boot cũng đã được cấu hình StartTLS.

Lưu ý: `ldapsearch` và JVM có thể dùng **kho chứng chỉ tin cậy khác nhau**. Lệnh dòng lệnh thành công không chứng minh Java đã tin cậy chứng chỉ LDAP.

### Ví dụ đọc kết quả

Nếu `ldapsearch` đọc được `uid=lan` trong `ou=people` nhưng `findByUid("lan")` trả về rỗng, kiểm tra `spring.ldap.base`, `@Entry(base=...)`, object class và tên thuộc tính `uid`. Nếu cả lệnh dòng lệnh không bind được, nên xử lý URL/TLS/tài khoản/quyền trước khi sửa code repository.

## 7. Bảo mật kết nối và thông tin xác thực

1. **Mã hóa đường truyền:** dùng LDAPS với chứng chỉ hợp lệ hoặc StartTLS được cấu hình tường minh. `ldap://` đơn thuần không bảo vệ mật khẩu bind khỏi nghe lén trên đường truyền.
2. **Kiểm tra chứng chỉ:** tin cậy CA qua truststore/SSL bundle thích hợp; kiểm tra tên máy chủ. Không tắt xác minh chứng chỉ để “chữa” lỗi kết nối.
3. **Quyền tối thiểu:** dùng tài khoản dịch vụ chỉ được đọc những nhánh/thuộc tính cần thiết. Chỉ cấp quyền ghi khi ứng dụng có yêu cầu CRUD thực tế.
4. **Quản lý bí mật:** nạp mật khẩu từ biến môi trường/secret manager, giới hạn truy cập và vòng đời của secret, không hardcode vào mã nguồn.
5. **Filter và DN an toàn:** dùng query builder cho giá trị filter và builder DN cho dữ liệu động; không dựng filter/DN bằng nối chuỗi trực tiếp.
6. **Giới hạn tài nguyên:** đặt timeout kết nối/đọc phù hợp (có thể dùng các tùy chọn JNDI qua `spring.ldap.base-environment`) và giới hạn phạm vi tìm kiếm, số kết quả theo yêu cầu hệ thống.

Trong các phiên bản Spring Boot có hỗ trợ cấu hình SSL cho LDAP, bạn có thể dùng `spring.ldap.ssl.bundle` cùng URL `ldaps://` để chỉ định trust material. Cơ chế SSL bundle không tự thiết lập StartTLS trên `ldap://`; StartTLS yêu cầu một chiến lược xác thực/kết nối được cấu hình riêng, ví dụ `DirContextAuthenticationStrategy` phù hợp.

## 8. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Connection refused/timeout | Sai hostname, cổng, mạng hoặc firewall. | Đối chiếu `spring.ldap.urls`, DNS, cổng LDAP và đường đi mạng. |
| `SSLHandshakeException` | Không tin cậy CA, chứng chỉ sai hostname/hết hạn hoặc thiếu cấu hình TLS. | Kiểm tra chứng chỉ, truststore của JVM và URL `ldaps://`. |
| LDAP result code **49** (`invalidCredentials`) | Bind DN/tài khoản/mật khẩu không hợp lệ, tài khoản bị khóa/hết hạn tùy server. | Thử bind độc lập bằng `ldapsearch -W`; kiểm tra secret thực sự được inject. |
| LDAP result code **32** (`noSuchObject`) | DN/gốc tìm kiếm không tồn tại hoặc ghép nhánh tương đối sai. | Đọc lại cây DN; kiểm tra `spring.ldap.base` và base trong truy vấn. |
| LDAP result code **50** (`insufficientAccessRights`) | Tài khoản bind thiếu ACL cho thao tác. | Kiểm tra quyền đọc/ghi của tài khoản tại nhánh liên quan. |
| Bind được nhưng query rỗng | Sai nhánh, thuộc tính, filter hoặc object class của entity. | Dùng `ldapsearch` cùng base/filter; đối chiếu schema thực. |
| `InvalidNameException` hoặc DN syntax error | DN sai cấu trúc, ký tự đặc biệt chưa escape. | Kiểm tra DN, dùng `LdapNameBuilder` hoặc `LdapName`. |

Mã lỗi LDAP phản ánh phản hồi từ server; nội dung log và cách phân biệt tình huống cụ thể có thể khác nhau giữa OpenLDAP, Active Directory và các triển khai khác.

## 9. Bài tập thực hành

Giả sử ứng dụng cần đọc hồ sơ nhân sự dưới `ou=staff,dc=company,dc=internal` và tài khoản dịch vụ là `cn=app-reader,ou=services,dc=company,dc=internal`.

1. Cấu hình URL `ldaps://directory.company.internal:636`, base DN và bind DN bằng các biến môi trường.
2. Thiết kế entity `@Entry(base = "ou=staff")` nếu `spring.ldap.base` đặt tại `dc=company,dc=internal`. Nêu DN đầy đủ của entry `uid=an`.
3. Kiểm tra bind và truy vấn người dùng bằng `ldapsearch -W`, rồi chạy một truy vấn `LdapTemplate` hoặc repository.
4. Thử đổi nhầm `spring.ldap.base` thành `ou=services,dc=company,dc=internal`. Giải thích vì sao truy vấn nhân sự không còn tìm đúng nhánh.

**Đáp án gợi ý:** base của ứng dụng là `dc=company,dc=internal`; bind DN là `cn=app-reader,ou=services,dc=company,dc=internal`; DN đầy đủ của `an` là `uid=an,ou=staff,dc=company,dc=internal`. Nếu đổi base sang `ou=services,...`, `ou=staff` không nằm dưới base mới. Mật khẩu bind chỉ được lấy từ secret hợp lệ của môi trường.

## 10. Ghi nhớ

Khi một ứng dụng Spring Data LDAP “không tìm thấy người dùng”, đừng vội sửa repository. Hãy xác nhận theo thứ tự: **LDAP URL → TLS → bind DN/mật khẩu → base DN → nhánh truy vấn → filter/schema → ACL**. Cấu hình đúng ba đầu vào URL, base DN và tài khoản bind là nền tảng để ánh xạ entry, truy vấn và CRUD LDAP hoạt động ổn định.

### Tài liệu tham khảo

- [Spring Boot — Working with NoSQL Technologies, LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
