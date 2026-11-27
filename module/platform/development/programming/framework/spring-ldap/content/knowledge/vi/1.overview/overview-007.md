# Ranh giới giữa Spring LDAP core, Spring Data LDAP và Spring Security LDAP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt trách nhiệm của **Spring LDAP core**, **Spring Data LDAP** và **Spring Security LDAP** trong một ứng dụng Java/Spring.
- Chọn `LdapTemplate`, `LdapClient`, LDAP repository hoặc LDAP authentication theo đúng nhu cầu.
- Hiểu vì sao truy vấn thông tin người dùng và xác thực mật khẩu là hai luồng khác nhau, dù cùng truy cập một LDAP server.
- Thiết kế cách dùng chung kết nối, DN, schema và nhóm quyền mà không làm lẫn trách nhiệm của các lớp.

Đây là bài về **ranh giới công cụ** trong hệ sinh thái Spring LDAP. Các kiến thức nền như Distinguished Name (DN), schema, LDAP filter, bind và TLS được dùng để minh họa lựa chọn API.

## 1. Một thư mục LDAP, ba loại nhu cầu

Giả sử công ty lưu danh tính nhân viên trong LDAP:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
~~~

Đây là **entry** có DN duy nhất. Phần `dc=example,dc=org` là **base DN** của thư mục; `ou=people` là nhánh người dùng; `uid=lan` nhận diện entry ở nhánh đó. Các thuộc tính có thể chịu ràng buộc của `objectClass` và schema máy chủ.

Một ứng dụng quản trị nhân sự có thể phát sinh ba yêu cầu độc lập:

1. **Đọc và cập nhật dữ liệu thư mục:** tìm nhân viên theo `uid`, đọc `mail`, sửa `telephoneNumber`, hoặc quản lý thành viên nhóm.
2. **Làm việc với đối tượng nghiệp vụ:** định nghĩa `DirectoryPerson` và gọi `repository.findByUid("lan")`, `save(...)`, `delete(...)`.
3. **Đăng nhập và bảo vệ API:** nhận username/password, yêu cầu máy chủ LDAP xác thực, xác định quyền từ nhóm, kiểm soát endpoint.

Ba yêu cầu này tương ứng với ba lớp khác nhau. Một ứng dụng có thể chỉ cần một lớp hoặc phối hợp cả ba.

## 2. Bản đồ trách nhiệm

| Thành phần | Mục tiêu chính | API điển hình | Trả về hoặc tạo ra | Không tự đảm nhận |
| --- | --- | --- | --- | --- |
| **Spring LDAP core** (`spring-ldap-core`) | Làm việc trực tiếp với entry, DN, filter và thao tác LDAP | `ContextSource`, `LdapTemplate`, `LdapClient`, `LdapQuery`, ODM | Thuộc tính, entry, kết quả tìm kiếm; thao tác bind/search/modify/unbind | Quản lý phiên đăng nhập HTTP và luật truy cập endpoint |
| **Spring Data LDAP** (`spring-data-ldap`) | Truy cập entry qua mô hình entity/repository | `@Entry`, `@Id`, `@Attribute`, `LdapRepository<T>`, `@EnableLdapRepositories` | Entity và các phương thức repository | Xác thực username/password cho Spring Security |
| **Spring Security LDAP** (`spring-security-ldap`) | Tích hợp xác thực LDAP vào cơ chế bảo mật Spring | `LdapBindAuthenticationManagerFactory`, `LdapAuthenticator`, LDAP authorities | `Authentication` và quyền được Spring Security sử dụng | Cung cấp repository CRUD tổng quát để quản lý toàn bộ directory |

~~~mermaid
flowchart TB
    App["Ứng dụng Spring"]
    Core["Spring LDAP core<br/>ContextSource · LdapTemplate · LdapClient · ODM"]
    Data["Spring Data LDAP<br/>Entity · LdapRepository"]
    Security["Spring Security LDAP<br/>LDAP Authentication · Authorities"]
    Directory[("LDAP server<br/>Entries · Schema · Groups")]
    App -->|"Tra cứu / cập nhật trực tiếp"| Core
    App -->|"Làm việc với entity"| Data
    App -->|"Đăng nhập / phân quyền"| Security
    Data -->|"Sử dụng Spring LDAP"| Core
    Security -->|"Tận dụng cơ sở Spring LDAP"| Core
    Core -->|"LDAP protocol"| Directory
~~~

**Hai điểm cần nhớ:**

- **ODM không thuộc riêng Spring Data LDAP.** Các annotation như `org.springframework.ldap.odm.annotations.Entry` và `Id` được cung cấp bởi Spring LDAP. Spring Data LDAP xây cơ chế repository trên mapping đó.
- **Spring Security LDAP không phải Spring Data LDAP dành cho mật khẩu.** Nó xác thực và cung cấp danh tính/quyền cho bộ lọc bảo mật, không bắt buộc phải đi qua `LdapRepository`.

## 3. Spring LDAP core: điều khiển thao tác trên directory

Spring LDAP core bọc các chi tiết JNDI thường gây lặp mã: mở/đóng context, chạy tìm kiếm, ánh xạ thuộc tính và chuyển đổi ngoại lệ. Bạn vẫn tư duy theo **DN, filter, search base, attributes, entry và phép thay đổi**.

### 3.1. ContextSource là điểm kết nối chung

`ContextSource` đóng vai trò gần giống `DataSource` của JDBC: nó cung cấp context để thao tác với LDAP. Ví dụ cấu hình trong Spring Boot:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=service,dc=example,dc=org
    # Cấp spring.ldap.password qua secret manager hoặc biến môi trường.
~~~

Với cấu hình này, một thao tác tìm kiếm dưới `ou=people` được hiểu tương đối với base DN đã đặt, nghĩa là phạm vi thực tế là `ou=people,dc=example,dc=org`. DN dùng làm tài khoản bind thường phải là DN đầy đủ. Các thuộc tính cấu hình phải phản ánh đúng directory thực tế và quyền tài khoản dịch vụ.

Spring Boot có thể tự cấu hình các bean tương ứng khi dependencies và cấu hình phù hợp. Với Spring thuần, có thể tự khai báo `LdapContextSource` và tạo `LdapTemplate` từ đó.

### 3.2. LdapTemplate: khi cần nắm rõ câu truy vấn

Ví dụ một dịch vụ tìm tên hiển thị từ `uid`:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNamesByUid(String uid) {
        EqualsFilter filter = new EqualsFilter("uid", uid);
        return ldapTemplate.search(
            "ou=people",
            filter.encode(),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
        );
    }
}
~~~

Ví dụ giả định entry khớp filter đều có thuộc tính `cn`. Trong ứng dụng thực, cần xử lý thuộc tính thiếu, số kết quả bất thường và giới hạn tìm kiếm.

Tại đây, **Spring LDAP core** chịu trách nhiệm thực hiện tìm kiếm và ánh xạ thuộc tính; nó không xác nhận người dùng hiện tại đã đăng nhập. `EqualsFilter` mã hóa giá trị theo cú pháp LDAP filter, tránh lỗi và nguy cơ filter injection do tự nối chuỗi như `"(uid=" + uid + ")"`.

`LdapTemplate` còn phù hợp với thao tác thêm, sửa, xóa entry; truy vấn nhiều điều kiện; tùy biến search scope; cập nhật thuộc tính nhiều giá trị như `member`; hoặc tích hợp hệ thống có schema không thuận lợi cho entity.

### 3.3. LdapClient: cú pháp fluent cho thao tác LDAP

`LdapClient` là API fluent của Spring LDAP core, tập trung vào `bind`, `search`, `modify`, `unbind` và `authenticate`, đồng thời hỗ trợ xử lý kết quả dạng stream. Bạn có thể tạo nó từ cùng `ContextSource`:

~~~java
@Bean
LdapClient ldapClient(ContextSource contextSource) {
    return LdapClient.create(contextSource);
}
~~~

**Ranh giới quan trọng:** `LdapClient` thuận tiện cho thao tác LDAP nhưng hiện không cung cấp ODM như `LdapTemplate`. Nếu cần ánh xạ entity bằng ODM, dùng `LdapTemplate` hoặc repository dựa trên Spring Data LDAP. Hai API core có thể cùng tồn tại.

### 3.4. Core có thể xác thực, nhưng không thay vai trò của Security

`LdapTemplate` và `LdapClient` có chức năng LDAP authentication/bind. Chúng hữu ích trong một số luồng nghiệp vụ đặc biệt, nhưng việc ứng dụng web quản lý `SecurityContext`, session, cấu hình truy cập URL/method, xử lý lỗi xác thực và chuyển nhóm thành quyền thường thuộc **Spring Security**.

## 4. Spring Data LDAP: repository cho entry đã được ánh xạ

Khi phần lớn tác vụ là thao tác với một kiểu entry ổn định, Spring Data LDAP giúp giảm mã lặp nhờ entity và repository.

Ví dụ entity:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // Constructor, getter và setter theo nhu cầu.
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Khi bật `@EnableLdapRepositories` cho package chứa interface trên, Spring Data tạo implementation và sử dụng hạ tầng Spring LDAP để truy cập directory. Ứng dụng có thể sử dụng:

~~~java
List<DirectoryPerson> matches = personRepository.findByUid("lan");
~~~

Lưu ý để tránh áp dụng máy móc tư duy JPA:

- `@Id` là **DN kiểu `javax.naming.Name`**, không phải khóa số tự tăng. Phải nhập đúng `org.springframework.ldap.odm.annotations.Id`, không dùng `org.springframework.data.annotation.Id`.
- `@Entry` chỉ định loại entry và base; `@Attribute` ánh xạ field với thuộc tính LDAP. `@DnAttribute` hỗ trợ ánh xạ thành phần DN khi cần.
- `LdapRepository<DirectoryPerson>` chỉ cần một kiểu generic; ID là `Name` theo cơ chế LDAP repository.
- LDAP không có cùng quan hệ, khóa ngoại, transaction và cơ chế query như RDBMS. Đừng mong `JpaRepository`, JPQL hoặc phép join hoạt động với LDAP.
- LDAP repository **không hỗ trợ paging/sorting theo giao diện Spring Data thông thường**; với tập dữ liệu lớn, cần cân nhắc giới hạn phía server, cơ chế phân trang LDAP cụ thể và API thấp hơn.
- Thao tác `save` hay thay đổi DN phải tôn trọng schema, thuộc tính bắt buộc, quyền ghi và quy tắc đặt tên của server; entity không làm mất các ràng buộc đó.

Chọn Spring Data LDAP khi cần các repository rõ ràng cho `Person`, `Group` hoặc kiểu entry tự định nghĩa. Chọn core trực tiếp khi các truy vấn khó biểu diễn, cần kiểm soát thao tác mức LDAP hoặc dữ liệu thay đổi theo schema.

## 5. Spring Security LDAP: xác thực và lấy quyền để bảo vệ ứng dụng

Đối với một request đăng nhập, câu hỏi chính là: **Máy chủ LDAP có chấp nhận thông tin đăng nhập không, và người dùng được cấp quyền gì trong ứng dụng?**

Luồng LDAP bind authentication thường diễn ra như sau:

1. Ứng dụng nhận username/password qua cơ chế đăng nhập được bảo vệ bằng HTTPS.
2. Spring Security LDAP tìm DN của người dùng (theo mẫu DN hoặc tìm kiếm với filter).
3. LDAP server kiểm tra mật khẩu khi ứng dụng thử **bind bằng danh tính người dùng**.
4. Nếu thành công, ứng dụng tra cứu/mapping nhóm hoặc quyền theo cấu hình.
5. Spring Security tạo `Authentication` đã xác thực để áp dụng luật truy cập, chẳng hạn `hasRole("ADMIN")`.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Web as Spring Security
    participant LDAP as LDAP server
    User->>Web: Username + password (qua HTTPS)
    Web->>LDAP: Tìm DN theo uid (nếu cần)
    LDAP-->>Web: DN của entry
    Web->>LDAP: Bind với DN và password của người dùng
    LDAP-->>Web: Chấp nhận hoặc từ chối
    opt Bind thành công
        Web->>LDAP: Tra cứu groups/roles theo cấu hình
        LDAP-->>Web: Thông tin nhóm
        Web-->>User: Authentication + authorities
    end
~~~

### 5.1. Cấu hình bind authentication

Một cấu hình tiêu biểu, giả sử `ContextSource` có base là `dc=example,dc=org`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {

    LdapBindAuthenticationManagerFactory factory =
        new LdapBindAuthenticationManagerFactory(contextSource);

    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");

    return factory.createAuthenticationManager();
}
~~~

Đây là phần cấu hình authentication manager; ứng dụng còn cần tích hợp nó với cấu hình `SecurityFilterChain` thích hợp và xác định cách lấy/map authorities. Filter `(uid={0})` để factory thay giá trị username bằng cơ chế dành cho LDAP search; tránh tự ghép filter từ input không tin cậy.

Nếu cấu trúc người dùng đồng nhất, có thể dùng `setUserDnPatterns("uid={0},ou=people")` thay cho tìm kiếm. Nếu người dùng nằm ở nhiều OU, dùng search base/filter thường linh hoạt hơn. Với Active Directory, thuộc tính nhận diện và cách bind có thể khác LDAP ví dụ; cần thiết kế theo schema thực tế.

### 5.2. Bind khác password comparison

- **Bind authentication:** máy chủ LDAP trực tiếp kiểm tra thông tin đăng nhập khi client bind dưới DN của người dùng. Ứng dụng không cần lấy thuộc tính `userPassword`.
- **Password comparison:** Spring Security so sánh mật khẩu theo cấu hình, có thể dùng LDAP compare hoặc đọc giá trị phù hợp để kiểm tra. Hành vi phụ thuộc cơ chế lưu mật khẩu, khả năng server và encoder.

Bind thường dễ phù hợp với directory doanh nghiệp. Không tự đọc `userPassword` để so sánh chuỗi, không lưu lại mật khẩu LDAP vào bảng người dùng nội bộ và không giả định server cho phép đọc hash mật khẩu.

### 5.3. Nhóm LDAP không tự động thành quyền ứng dụng

LDAP có thể biểu diễn nhóm bằng `groupOfNames` với thuộc tính `member` chứa DN thành viên, hoặc bằng những cách khác (ví dụ `memberOf` trong một số directory). Để bảo vệ `/admin/**`, ứng dụng phải cấu hình quy tắc xác định membership và ánh xạ sang `GrantedAuthority`/role phù hợp.

**Xác thực thành công không đồng nghĩa được quyền admin.** Kết quả bind trả lời “đúng danh tính hay không”; authorization trả lời “danh tính này được làm gì”. Spring Security quản lý quyết định truy cập theo authorities; LDAP là một nguồn có thể cấp dữ liệu cho quyết định đó.

### 5.4. Security không làm công cụ quản trị directory

Spring Security LDAP không thay Spring Data LDAP hoặc `LdapTemplate` để tạo entry mới, sửa số điện thoại, đổi nhóm hàng loạt hoặc đồng bộ hồ sơ nhân viên. Những tác vụ này nằm ở lớp truy cập directory, phải được cấp quyền nghiệp vụ riêng.

## 6. Khi ba lớp phối hợp trong một hệ thống

Giả sử ứng dụng nhân sự có ba chức năng:

| Chức năng | Chọn công cụ chính | Vì sao |
| --- | --- | --- |
| Nhân viên đăng nhập bằng tài khoản công ty | Spring Security LDAP | Cần xác thực và tích hợp với cơ chế bảo vệ request/method |
| Trang hồ sơ đọc tên, email và số điện thoại | Spring Data LDAP nếu có entity ổn định; Spring LDAP core nếu truy vấn tùy biến | Đây là truy cập dữ liệu, không phải kiểm tra password |
| Quản trị viên thêm người vào nhóm LDAP | Spring LDAP core hoặc Spring Data LDAP theo mô hình entry | Đây là thay đổi nội dung directory, cần ACL ghi cụ thể |
| Tìm theo filter phức tạp, yêu cầu search scope/controls riêng | Spring LDAP core | Cần điều khiển chi tiết thao tác LDAP |
| Kiểm tra người dùng có quyền truy cập endpoint | Spring Security | Cần authorization dựa trên `Authentication` và authorities |
| Đọc danh sách người dùng từ LDAP cho báo cáo định kỳ | Spring Data LDAP hoặc core | Không cần tạo một phiên đăng nhập cho từng entry |

Một thiết kế service có thể phân tách như sau:

~~~text
web/
  SecurityConfiguration       -> Spring Security LDAP
directory/
  DirectoryPersonRepository    -> Spring Data LDAP
  DirectoryGroupService        -> Spring LDAP core
application/
  StaffProfileService          -> gọi repository/group service
~~~

Các service có thể dùng chung địa chỉ server/base DN, nhưng **quyền của tài khoản bind** phải phù hợp từng mục đích. Chẳng hạn, tài khoản phục vụ tra cứu nên chỉ có quyền đọc cần thiết; tác vụ sửa nhóm cần một quyền ghi riêng. Đừng đưa tài khoản quản trị directory rộng quyền vào mọi request chỉ vì dùng chung `ContextSource` tiện hơn.

### Cùng một người dùng, khác nhau ở câu hỏi

Với `uid=lan`:

- `personRepository.findByUid("lan")` hỏi: “Entry có thuộc tính `uid=lan` là gì?” Kết quả có thể trả về ngay cả khi `lan` không đăng nhập hoặc tài khoản đang bị vô hiệu hóa theo chính sách directory.
- LDAP bind authentication hỏi: “Thông tin đăng nhập hiện tại có được server chấp nhận không?”
- `hasRole("HR")` hỏi: “Danh tính đã xác thực này có authority phù hợp với quyền HR trong ứng dụng không?”

Không dùng kết quả tồn tại entry làm bằng chứng xác thực. Cũng không dùng riêng kết quả bind làm bằng chứng người dùng được phép thực hiện mọi nghiệp vụ.

## 7. Chọn cách làm theo tình huống

**Tình huống A — Dịch vụ danh bạ nội bộ.** REST API chỉ trả về `uid`, `cn` và `mail` theo điều kiện tìm kiếm. Bắt đầu bằng `LdapTemplate` hoặc `LdapClient`. Khi có nhiều entity dùng lặp lại và CRUD đơn giản, cân nhắc thêm Spring Data LDAP.

**Tình huống B — Ứng dụng dùng tài khoản công ty để đăng nhập.** Dùng Spring Security LDAP cho authentication và authorities. Chỉ thêm Spring Data LDAP nếu ứng dụng còn phải truy cập entity LDAP như dữ liệu nghiệp vụ. Một ứng dụng chỉ cần LDAP login không nhất thiết phải khai báo repository nào.

**Tình huống C — Cổng quản trị tài khoản.** Sử dụng Spring Security để bảo vệ các thao tác quản trị; dùng core/repository để thao tác entry. Việc user quản trị đã đăng nhập không tự cấp quyền sửa LDAP: server vẫn kiểm tra ACL của kết nối đang thực hiện sửa đổi.

**Tình huống D — Directory nhiều nhánh, schema đặc thù.** Bắt đầu từ core để kiểm soát search base, filter, mapper và lỗi. Có thể bọc phía ngoài bằng một interface nghiệp vụ, sau đó đưa những entry đủ ổn định sang repository nếu có lợi.

## 8. Những lỗi thiết kế và vận hành thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng repository để “kiểm tra password” bằng cách đọc `userPassword` | Sai phân lớp, rủi ro lộ bí mật; nhiều server không cho đọc | Dùng Spring Security LDAP với bind hoặc cơ chế password comparison được cấu hình đúng |
| Nối chuỗi filter trực tiếp từ username | Filter injection, truy vấn sai hoặc vượt phạm vi | Dùng `EqualsFilter`, builder/filter parameter binding; kiểm soát input |
| Nhầm DN tương đối với DN đầy đủ | Tìm không ra entry hoặc bind sai DN | Ghi rõ base DN; phân biệt DN tìm kiếm và DN tài khoản bind |
| Dùng `@Id` của Spring Data Commons hoặc ID kiểu `Long` | Mapping repository không đúng | Dùng ODM `@Id` của Spring LDAP và `javax.naming.Name` |
| Mong paging/sorting của repository hoạt động giống JPA | Giới hạn API, hiệu năng không như kỳ vọng | Tìm kiếm có giới hạn, xem xét khả năng paged results của LDAP server với API phù hợp |
| Coi LDAP group là role ứng dụng mà không mapping | Người dùng đăng nhập được nhưng quyền sai | Xác định search base, loại group, DN thành viên và `GrantedAuthority` mapping |
| Dùng LDAP thường khi gửi mật khẩu | Mật khẩu và thông tin nhạy cảm có thể bị lộ trên đường truyền | Dùng LDAPS/StartTLS, xác thực chứng chỉ và quản lý truststore phù hợp |
| Dùng một tài khoản LDAP quyền cao cho mọi chức năng | Gia tăng phạm vi thiệt hại nếu ứng dụng bị lạm dụng | Chia quyền đọc/ghi theo nhu cầu, bảo vệ secrets, kiểm toán thao tác |
| Gộp lỗi mất kết nối với sai mật khẩu | Khó xử lý sự cố, trải nghiệm đăng nhập không chính xác | Phân biệt lỗi xác thực, kết nối/TLS, timeout và lỗi permission ở lớp vận hành, không để lộ dữ liệu nhạy cảm cho client |

**Lưu ý về TLS và pooling:** LDAPS hoặc StartTLS phải phù hợp cấu hình chứng chỉ và chính sách kết nối của server. Khi pooling, cần xét riêng kết nối tài khoản dịch vụ và những lần bind bằng danh tính người dùng, tránh tái sử dụng context không đúng danh tính. Không bật cơ chế pooling chỉ dựa vào giả định rằng mọi kết nối LDAP là tương đương.

**Lưu ý về kiểm thử:** Với embedded LDAP (ví dụ UnboundID) hoặc môi trường LDAP thử nghiệm, nên có các ca thực sự kiểm tra DN đúng/sai, filter chứa ký tự đặc biệt, thuộc tính thiếu, bind đúng/sai password, quyền nhóm, ACL ghi và lỗi TLS/kết nối. Unit test mock repository không chứng minh được quy tắc schema và ACL của server.

## 9. Tự kiểm tra mức độ hiểu

1. Một API chỉ cần đọc `mail` theo `uid`, không tham gia đăng nhập. Bạn chọn core, Data hay Security? Tại sao?
2. Có nên dùng `personRepository.findByUid(username) != null` làm bằng chứng người dùng đã xác thực? Hãy giải thích sự khác nhau giữa “tồn tại entry” và “bind thành công”.
3. Ứng dụng đã xác thực qua LDAP nhưng nhóm `cn=admins,ou=groups,...` không cho truy cập `/admin`. Cần kiểm tra mapping nào?
4. Vì sao lớp entity LDAP phải dùng `javax.naming.Name` làm ID, và điều gì xảy ra nếu cấu hình base DN bị nhân đôi?
5. Nếu đội vận hành muốn đổi thuộc tính `telephoneNumber` cho một tập người dùng và lưu audit, lớp nào thực hiện thay đổi directory, lớp nào kiểm soát quyền người gọi?

**Gợi ý đáp án:** (1) Core hoặc Data tùy mức cần mapping entity; (2) không, entry lookup không kiểm tra secret; (3) cách truy vấn group và chuyển sang authorities; (4) DN định danh entry theo cây, cấu hình đường dẫn sai sẽ dẫn đến tìm/bind sai; (5) core/Data thực hiện update với ACL phù hợp, Security kiểm soát authorization của API và cần bổ sung audit nghiệp vụ.

## 10. Ghi nhớ để sử dụng đúng

- **Spring LDAP core** = API xử lý LDAP theo DN, filter, entry, thuộc tính và phép thao tác; có cả ODM.
- **Spring Data LDAP** = lớp repository dựa trên ODM để làm việc với entity thuận tiện hơn.
- **Spring Security LDAP** = xác thực thông tin đăng nhập qua LDAP và chuyển kết quả thành danh tính/quyền trong ứng dụng Spring Security.
- Một hệ thống có thể cần cả ba, nhưng lựa chọn được quyết định bởi **tác vụ cụ thể**: quản lý dữ liệu thư mục, truy cập entity, hay đăng nhập/phân quyền.

### Tài liệu tham khảo chính thức

- [Spring LDAP — Configuration, ContextSource, LdapClient và LdapTemplate](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Data LDAP — Configuration và giới hạn của repository](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
