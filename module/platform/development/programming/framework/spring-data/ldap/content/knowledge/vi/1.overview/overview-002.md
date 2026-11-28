# LDAP là gì và vì sao ứng dụng cần truy cập dịch vụ thư mục

Khi một tổ chức có hàng nghìn nhân viên, thiết bị, nhóm và ứng dụng, câu hỏi “**người dùng này là ai, thuộc bộ phận nào, thuộc nhóm nào và tìm thông tin của họ ở đâu?**” xuất hiện trong nhiều hệ thống. Mỗi ứng dụng tự lưu bản sao riêng của danh bạ sẽ nhanh chóng gặp vấn đề: dữ liệu không nhất quán, cập nhật chậm, khó quản lý tài khoản nghỉ việc và khó áp dụng quy tắc truy cập chung.

**LDAP (Lightweight Directory Access Protocol)** là một giao thức chuẩn để **truy cập và quản lý thông tin trong dịch vụ thư mục**. Ứng dụng dùng LDAP để tìm entry, đọc thuộc tính, kiểm tra một số thông tin định danh và, khi được cấp quyền, tạo hoặc cập nhật dữ liệu trong directory. Trong Java, **Spring Data LDAP** giúp thực hiện các thao tác đó qua `LdapRepository`, `LdapTemplate` và cơ chế ánh xạ entry LDAP thành đối tượng Java.

Bài **Tổng quan** này làm rõ LDAP phục vụ bài toán nào, dữ liệu thư mục khác cơ sở dữ liệu thông thường ở điểm nào, và tại sao ứng dụng Spring cần kết nối đến directory. Những chủ đề chuyên sâu như DN, `objectClass`, schema, filter, CRUD, TLS và kiểm thử sẽ được giới thiệu qua ví dụ đủ để hiểu toàn cảnh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng bản chất của LDAP và phân biệt **giao thức**, **directory server** và **Spring Data LDAP**.
2. Đọc một cây thư mục đơn giản, hiểu entry, DN, RDN, attribute, `objectClass` và schema.
3. Nêu các thao tác LDAP chính: bind, search, compare, add, modify, delete và modify DN.
4. Chỉ ra các tình huống ứng dụng cần truy cập directory, cũng như khi nào một cơ sở dữ liệu nghiệp vụ phù hợp hơn.
5. Mô tả luồng Spring Boot → `LdapTemplate`/repository → LDAP server và những điểm cần bảo mật, kiểm thử.

## 2. LDAP là giao thức, directory là dịch vụ lưu dữ liệu

Trong thuật ngữ kỹ thuật, cần tách ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **LDAP** | Giao thức mà client dùng để giao tiếp với máy chủ thư mục: xác thực bind, tìm kiếm và thay đổi entry. | LDAPv3, yêu cầu `SearchRequest`. |
| **Directory server/service** | Hệ thống lưu cây entry, thực hiện schema và ACL, xử lý yêu cầu LDAP. | OpenLDAP, 389 Directory Server, Microsoft Active Directory Domain Services. |
| **Spring Data LDAP** | Thư viện Java trừu tượng hóa việc truy cập entry LDAP thành template/repository và ánh xạ object. | `LdapTemplate`, `LdapRepository`, `@Entry`. |

Nói “lưu dữ liệu **trong LDAP**” là cách nói tắt thường gặp; chính xác hơn là dữ liệu nằm **trong một directory server có giao diện LDAP**. LDAP không định nghĩa một sản phẩm cụ thể và cũng không bắt mọi triển khai phải hỗ trợ cùng schema, thuộc tính hoặc quy tắc phân quyền.

Directory tối ưu cho những dữ liệu **được tra cứu nhiều, thay đổi tương đối ít và có cấu trúc phân cấp**: danh bạ người dùng, nhóm, đơn vị tổ chức, thông tin thiết bị, tài khoản dịch vụ, một số thuộc tính định danh. Nó đặc biệt hữu ích khi nhiều ứng dụng cần dùng chung nguồn thông tin.

Ví dụ, cùng một tài khoản nhân viên có thể được ứng dụng danh bạ, công cụ nội bộ, cổng quản trị và dịch vụ đăng nhập tra cứu qua directory thay vì mỗi ứng dụng tự tạo một bản sao thiếu đồng bộ.

### LDAP không đồng nghĩa với dịch vụ đăng nhập

LDAP có thao tác **bind**, có thể được sử dụng để kiểm tra thông tin xác thực. Tuy nhiên, một directory cũng có thể chỉ là **nguồn dữ liệu** mà ứng dụng truy vấn bằng tài khoản dịch vụ. Ngược lại, một hệ thống đăng nhập hiện đại có thể sử dụng OpenID Connect, SAML hoặc các phương thức khác thay vì cho ứng dụng truy cập LDAP trực tiếp.

Khả năng **tìm thấy entry người dùng** không chứng minh người gửi request là chủ sở hữu của entry đó. Và **bind thành công** chưa có nghĩa là được phép gọi mọi API nghiệp vụ: ứng dụng vẫn cần kiểm tra phân quyền.

## 3. Mô hình dữ liệu: cây thư mục thay vì bảng quan hệ

Một directory chứa nhiều **entry**, sắp xếp theo cấu trúc cây gọi là **Directory Information Tree (DIT)**. Mỗi entry có một tên định danh phân biệt (**Distinguished Name – DN**) và một tập thuộc tính.

Ví dụ directory giả định của công ty:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   ├── cn=developers
│   └── cn=hr-readers
└── ou=services
    └── cn=directory-reader
~~~

Hình vẽ viết ngắn tên ở từng nút. DN **đầy đủ** của nhân viên Lan là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Ý nghĩa các phần:

- `dc=example,dc=org`: gốc directory ứng với tên miền ví dụ; `dc` là *domain component*.
- `ou=people`: nhánh đơn vị tổ chức (*organizational unit*) chứa người dùng.
- `uid=lan`: *relative distinguished name* (RDN) của entry Lan, tương đối với entry cha.
- Dấu phẩy trong DN ghép RDN theo hướng từ **entry cụ thể nhất** tới **gốc**.

Mỗi entry có DN duy nhất trong không gian đặt tên liên quan. **`uid` không tự động duy nhất trong toàn directory** nếu schema/quy định tổ chức không bảo đảm điều đó; DN mới là đường dẫn định danh. Khi di chuyển entry sang nhánh khác hoặc đổi RDN, DN đầy đủ có thể thay đổi.

### Entry, attribute và giá trị

Một entry người dùng có thể chứa:

| Attribute | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `uid` | `lan` | Tên định danh ứng dụng thường dùng để tra cứu. |
| `cn` | `Lan Nguyen` | Tên hiển thị (*common name*). |
| `sn` | `Nguyen` | Họ (*surname*). |
| `mail` | `lan@example.org` | Địa chỉ email. |
| `ou` | `Engineering` | Bộ phận; việc có lưu trên entry hay không tùy schema. |
| `objectClass` | `top`, `person`, `organizationalPerson`, `inetOrgPerson` | Các lớp schema mà entry tuân thủ. |

LDAP hỗ trợ cả thuộc tính **một giá trị** và **nhiều giá trị**, tùy định nghĩa schema. Ví dụ một entry có thể có nhiều `telephoneNumber` hoặc nhiều giá trị cho một thuộc tính nhóm. Không nên suy từ tên attribute rằng mọi directory đều dùng cùng cú pháp hoặc ràng buộc.

### `objectClass` và schema quyết định entry hợp lệ

Trong directory, **schema** định nghĩa các loại attribute, cú pháp giá trị, quy tắc so khớp và các `objectClass`. Mỗi `objectClass` xác định tập thuộc tính bắt buộc (*MUST*) và tùy chọn (*MAY*), có thể kế thừa từ lớp khác. Một lớp có thể là *structural*, *auxiliary* hoặc *abstract* theo mô hình schema LDAP.

Với `inetOrgPerson`, các lớp trong chuỗi kế thừa thường gồm `top`, `person`, `organizationalPerson` và `inetOrgPerson`. Thuộc tính `cn` và `sn` là những yêu cầu cơ bản của `person`; các thuộc tính như `uid`, `mail` có thể dùng theo schema của triển khai. Không phải mọi entry đăng nhập đều dùng `inetOrgPerson`; Active Directory có mô hình class/attribute riêng.

Ví dụ một entry biểu diễn bằng **LDIF (LDAP Data Interchange Format)**:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
~~~

LDIF là **định dạng trao đổi dữ liệu dạng văn bản**, không phải giao thức truy vấn. Khi nhập LDIF vào directory thật, entry cha phải tồn tại, schema phải phù hợp và tài khoản kết nối phải có quyền tạo entry. Dữ liệu trên chỉ là minh họa, không phải thông tin của người dùng thật.

## 4. Các thao tác LDAP giải quyết bài toán gì?

Ứng dụng tương tác với directory bằng các thao tác ở mức giao thức, sau đó server áp dụng schema và quy tắc truy cập.

| Thao tác | Mục đích | Ví dụ nghiệp vụ |
| --- | --- | --- |
| **Bind** | Thiết lập danh tính xác thực trên kết nối LDAP. | Tài khoản dịch vụ đăng nhập để tra cứu; thử bind bằng DN người dùng để xác minh mật khẩu. |
| **Search** | Tìm entry trong một nhánh với bộ lọc và chọn thuộc tính cần nhận. | Tìm `uid=lan` trong `ou=people` và lấy `cn`, `mail`. |
| **Compare** | Hỏi server một thuộc tính có khớp với giá trị đưa vào hay không. | Kiểm tra một điều kiện so khớp được server hỗ trợ. |
| **Add** | Tạo entry mới dưới một DN. | Cấp phát hồ sơ nhân viên mới. |
| **Modify** | Thêm/xóa/thay thế giá trị thuộc tính trên entry. | Cập nhật tên hiển thị hoặc số điện thoại. |
| **Delete** | Xóa entry, tùy các ràng buộc server. | Xóa entry thử nghiệm khi không còn sử dụng. |
| **Modify DN** | Đổi RDN và/hoặc di chuyển entry theo khả năng server. | Thay đổi nhánh quản lý của một entry. |

Trong ứng dụng Spring Data LDAP, các thao tác **read/search** và **CRUD** xuất hiện qua API repository hoặc `LdapTemplate`. Không phải ứng dụng nào cũng nên có quyền ghi; nhiều trường hợp chỉ cần tài khoản đọc giới hạn là đủ.

### Search được xác định bởi ba yếu tố

Một truy vấn LDAP không đơn giản là “SELECT từ bảng”. Nó có ít nhất ba yếu tố quan trọng:

1. **Search base DN:** bắt đầu tìm ở nhánh nào, ví dụ `ou=people,dc=example,dc=org`.
2. **Search scope:** chỉ entry gốc (`base`), các entry con ngay dưới (`one-level`), hoặc cả cây con (`subtree`).
3. **Search filter:** điều kiện so khớp thuộc tính, ví dụ `(uid=lan)` hoặc `(&(objectClass=inetOrgPerson)(ou=Engineering))`.

Có thể giới hạn những thuộc tính trả về (chỉ lấy `cn`, `mail`) và giới hạn số kết quả/thời gian. Search scope và filter quyết định tính đúng đắn cũng như hiệu năng, nhất là khi tổ chức có hàng trăm nghìn entry.

~~~text
Base:   ou=people,dc=example,dc=org
Scope:  subtree
Filter: (&(objectClass=inetOrgPerson)(uid=lan))
Return: dn, cn, mail
~~~

Filter LDAP có cú pháp riêng: `&` là AND, `|` là OR, `!` là NOT. Ví dụ `(uid=*)` tìm entry có thuộc tính `uid`; đó không phải truy vấn tìm giá trị `uid` bằng ký tự “*”. Với dữ liệu người dùng nhập, phải **escape giá trị filter** theo quy tắc LDAP để tránh thay đổi nghĩa của truy vấn.

## 5. Vì sao ứng dụng cần truy cập dịch vụ thư mục?

### 5.1. Danh bạ tập trung, dữ liệu nhất quán hơn

Một ứng dụng nội bộ cần hiển thị thông tin liên hệ cho đồng nghiệp. Thay vì tự yêu cầu nhân viên nhập lại họ tên, email, bộ phận và trạng thái tài khoản, ứng dụng có thể tra cứu entry trong directory.

**Tình huống:** Khi nhân viên chuyển từ Engineering sang Support, thay đổi được cập nhật tại nguồn quản lý directory; các ứng dụng tra cứu sau đó có thể thấy giá trị mới theo chính sách đồng bộ/đọc của hệ thống. Thực tế, nguồn dữ liệu gốc có thể là HRIS, directory là bản sao đồng bộ hoặc một dịch vụ trung gian. Không mặc định rằng LDAP luôn là nguồn chân lý cuối cùng của mọi thuộc tính.

### 5.2. Tra cứu nhóm và thành viên để hỗ trợ phân quyền

Ứng dụng có thể cần biết người dùng thuộc nhóm nào, ví dụ `cn=developers` hoặc `cn=hr-readers`. Directory có thể lưu quan hệ nhóm–thành viên bằng các thuộc tính như `member`, `uniqueMember` hoặc cơ chế đặc thù của server.

Việc tìm thấy membership **chỉ cung cấp thông tin đầu vào cho chính sách phân quyền**. Ứng dụng phải ánh xạ group tới authority/role và kiểm tra thao tác tương ứng; không nên coi cứ tồn tại nhóm là được toàn quyền. Với Active Directory, nested group và cách tính membership có thể đòi hỏi cơ chế truy vấn riêng.

### 5.3. Hỗ trợ xác thực khi thiết kế hệ thống đăng nhập

Một số hệ thống dùng **LDAP bind authentication**: tìm DN của người dùng theo tên đăng nhập, thử bind bằng mật khẩu do người dùng cung cấp, và để directory quyết định credential có hợp lệ hay không. Một số kiến trúc khác sử dụng identity provider trung tâm giao tiếp với directory; ứng dụng nhận token qua OpenID Connect thay vì trực tiếp biết mật khẩu LDAP.

**Điều cần nhớ:** Spring Data LDAP chủ yếu xử lý **truy cập entry**. Nếu muốn bảo vệ endpoint HTTP, quản lý phiên đăng nhập, tạo principal và kiểm tra role, dùng cơ chế xác thực/phân quyền phù hợp của **Spring Security**. Query `findByUid("lan")` chỉ cho biết entry tồn tại, không xác thực người gửi request.

### 5.4. Cấp phát, cập nhật và quản lý vòng đời tài khoản

Công cụ quản trị có thể tạo entry khi có nhân viên mới, cập nhật thuộc tính, quản lý trạng thái hoặc nhóm, và xóa hoặc vô hiệu hóa tài khoản khi người dùng nghỉ việc. Những thao tác này thường cần:

- Quy trình phê duyệt, kiểm tra dữ liệu và audit.
- Quyền ghi LDAP được cấp rất hẹp, phù hợp với đúng nhánh và loại thao tác.
- Kiểm tra schema và ràng buộc của directory.
- Chiến lược xử lý lỗi và đồng bộ giữa directory với hệ thống nguồn.

Không nên mở quyền CRUD chung cho mọi người dùng chỉ vì repository cung cấp phương thức `save` hoặc `delete`.

### 5.5. Tích hợp những hệ thống có directory sẵn

Nhiều doanh nghiệp dùng directory lâu năm để quản lý danh tính, thiết bị và nhóm. Khi xây ứng dụng Java mới, LDAP là một cách tích hợp trực tiếp với cấu trúc hiện hữu thay vì tạo hệ thống tài khoản song song. Khả năng tương tác này là một lý do thực tế để chọn Spring Data LDAP cho các ứng dụng quản trị và tra cứu.

## 6. LDAP khác cơ sở dữ liệu quan hệ như thế nào?

LDAP directory và cơ sở dữ liệu quan hệ đều có thể lưu thông tin, nhưng được thiết kế với những kỳ vọng sử dụng khác nhau.

| Tiêu chí | Directory qua LDAP | Cơ sở dữ liệu quan hệ |
| --- | --- | --- |
| Mô hình | Entry trong cây DN, thuộc tính theo schema LDAP. | Bảng, hàng, cột và quan hệ khóa. |
| Truy vấn | Search base, scope, filter LDAP, danh sách thuộc tính. | SQL, join, aggregate, transaction. |
| Trường hợp điển hình | Danh bạ, người dùng, nhóm, tra cứu định danh. | Đơn hàng, thanh toán, giao dịch, báo cáo, dữ liệu nghiệp vụ. |
| Thay đổi | Có Add/Modify/Delete nhưng nhiều hệ thống chủ yếu phục vụ đọc. | Thường hỗ trợ nghiệp vụ ghi và giao dịch phức tạp. |
| Tính nhất quán và transaction | Phụ thuộc triển khai LDAP, replication và thao tác; không mặc định có transaction đa entry kiểu RDBMS. | Thường có transaction ACID theo khả năng cơ sở dữ liệu. |
| Phân quyền | ACL server trên entry/attribute cộng chính sách ứng dụng. | Quyền database trên schema/table/row cộng chính sách ứng dụng. |

Ví dụ, dữ liệu `uid=lan` và nhóm `developers` là ứng viên hợp lý để tra cứu trong directory. Nhưng **đơn hàng, giỏ hàng, lịch sử giao dịch và báo cáo tổng hợp** thường nên ở database nghiệp vụ. Không dùng LDAP làm nơi lưu mọi dữ liệu chỉ vì ứng dụng đã có kết nối LDAP.

Một kiến trúc thực tế có thể sử dụng **LDAP cho danh tính/danh bạ**, **Spring Security cho truy cập API**, và **PostgreSQL/MySQL cho dữ liệu nghiệp vụ**. Một số hệ thống còn dùng cache hoặc service trung gian; khi đó phải quy định rõ thời gian làm mới và cách xử lý dữ liệu cũ.

## 7. Spring Data LDAP giúp gì cho ứng dụng Java?

Không có lớp trừu tượng, ứng dụng Java có thể làm việc trực tiếp với **JNDI** và các API LDAP mức thấp: tạo connection/context, xây filter, tìm entry rồi đọc attribute. Spring LDAP cung cấp `LdapTemplate` để giảm phần mã lặp; Spring Data LDAP bổ sung mô hình **entity + repository** để truy cập entry gần với cách lập trình Spring Data.

~~~mermaid
flowchart LR
    A["Controller / Service Java"] --> B["Spring Data LDAP: LdapRepository"]
    A --> C["Spring LDAP: LdapTemplate"]
    B --> D["LdapContextSource"]
    C --> D
    D --> E["LDAP server"]
    E --> F["DIT: users, groups, devices"]
~~~

Trong sơ đồ, `LdapContextSource` quản lý thông tin kết nối: URL, base DN và danh tính bind. Repository và template là **hai cách truy cập dữ liệu cùng giao thức LDAP**; cái nào phù hợp tùy bài toán.

### 7.1. Cấu hình kết nối trong Spring Boot

Thêm starter vào dự án Spring Boot (ví dụ Gradle Kotlin DSL):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: ${LDAP_BASE_DN:dc=example,dc=org}
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Ba nhóm giá trị quyết định kết nối:

- **URL:** `ldaps://ldap.example.org:636` chỉ tới máy chủ, giao thức và cổng.
- **Base DN:** `dc=example,dc=org` là gốc mặc định cho DN tương đối khi ứng dụng thao tác.
- **Bind DN và mật khẩu:** thông tin của tài khoản dịch vụ, ví dụ `cn=directory-reader,ou=services,dc=example,dc=org`, dùng để truy vấn các entry mà ACL cho phép.

Tham số `LDAP_BIND_PASSWORD` phải được cấp từ môi trường triển khai hoặc secret manager, không lưu mật khẩu thật trong Git. Ví dụ chỉ hoạt động khi server, schema, tài khoản và quyền tương ứng đã được chuẩn bị.

**Lưu ý:** URL `ldaps://` sử dụng TLS ngay khi kết nối; URL `ldap://` đơn thuần không đảm bảo mã hóa. StartTLS trên `ldap://` cần chiến lược kết nối/nâng cấp TLS riêng, không tự xuất hiện chỉ nhờ đặt URL.

### 7.2. Ánh xạ entry LDAP thành Java object

Giả sử directory chứa các entry `inetOrgPerson` dưới `ou=people`, có `uid`, `cn`, `sn`. Entity đơn giản:

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

    @Attribute(name = "sn")
    private String surname;

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getSurname() { return surname; }
}
~~~

**Đọc ý nghĩa:**

- `@Entry` cho biết class tương ứng với loại entry nào và nằm dưới nhánh tương đối nào.
- `@Id` được khai báo bằng `org.springframework.ldap.odm.annotations.Id` trên thuộc tính DN kiểu `javax.naming.Name`, không phải annotation JPA.
- `@Attribute` ánh xạ attribute LDAP với field Java.
- Nếu `spring.ldap.base=dc=example,dc=org`, `@Entry(base = "ou=people")` định vị nhánh `ou=people,dc=example,dc=org`.

Entity phải phù hợp schema thực của directory. Đối với Active Directory, không nên mặc định một entry user có đầy đủ object class và thuộc tính theo ví dụ `inetOrgPerson` trên.

### 7.3. Tra cứu bằng repository

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    Optional<PersonEntry> findByUid(String uid);
}
~~~

Trong service:

~~~java
import org.springframework.stereotype.Service;
import java.util.Optional;

@Service
public class PeopleDirectoryService {
    private final PersonRepository people;

    public PeopleDirectoryService(PersonRepository people) {
        this.people = people;
    }

    public Optional<String> displayNameOf(String uid) {
        return people.findByUid(uid).map(PersonEntry::getCommonName);
    }
}
~~~

Ứng dụng có thể gọi `displayNameOf("lan")` để lấy tên hiển thị. Tìm thấy entry **không có nghĩa** người gọi đã chứng minh danh tính `lan`. Nếu kết quả được đưa ra API, phải kiểm tra authentication/authorization ở tầng ứng dụng phù hợp trước khi cho phép đọc.

### 7.4. Truy vấn linh hoạt bằng `LdapTemplate`

Khi cần chỉ rõ filter và phạm vi tìm kiếm, `LdapTemplate` cho phép điều khiển truy vấn:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PeopleSearchService {
    private final LdapTemplate ldap;

    public PeopleSearchService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<String> searchNames(String uid) {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("uid").is(uid);

        return ldap.search(
            query,
            (AttributesMapper<String>) attrs ->
                String.valueOf(attrs.get("cn").get())
        );
    }
}
~~~

`where("uid").is(uid)` xây filter và xử lý escape giá trị phù hợp. Tránh ghép trực tiếp đầu vào không tin cậy thành `"(uid=" + uid + ")"` vì có thể gây **LDAP filter injection**. Khi xây DN từ giá trị động, dùng API DN như `LdapNameBuilder` để escape RDN; escaping cho **filter** và escaping cho **DN** là hai vấn đề khác nhau.

Repository phù hợp CRUD/truy vấn phổ biến theo mô hình entity; `LdapTemplate` linh hoạt hơn với những truy vấn cần tùy biến. Cả hai đều phải tuân theo schema, base DN, ACL, filter và các giới hạn của server.

## 8. Tài khoản kết nối, xác thực người dùng và quyền truy cập

Mô hình phổ biến sử dụng **tài khoản dịch vụ chỉ đọc** cho các truy vấn dữ liệu:

~~~text
Client HTTP
    |
    v
Ứng dụng Spring (kiểm tra quyền request)
    |
    +-- Repository / LdapTemplate
          |
          +-- bind: cn=directory-reader,ou=services,dc=example,dc=org
          |
          +-- search: ou=people,dc=example,dc=org
                |
                +-- LDAP server kiểm tra ACL của tài khoản đang bind
~~~

LDAP server kiểm tra quyền thao tác theo **danh tính đang bind**. Một user `lan` đã đăng nhập ứng dụng **không tự động** khiến mọi thao tác repository chạy bằng DN của `lan`. Trong hệ thống thực, phải bảo vệ cả hai lớp:

1. **Phân quyền tại ứng dụng:** người gọi HTTP được phép xem/sửa thông tin nào?
2. **ACL tại directory:** tài khoản LDAP trên kết nối được phép đọc/sửa entry và attribute nào?

Nếu cần LDAP để kiểm tra mật khẩu người dùng, kiến trúc thường sử dụng thành phần xác thực phù hợp như **Spring Security LDAP authentication**. Không tự đọc `userPassword` rồi so sánh bằng chuỗi; nhiều server không cho đọc thuộc tính này và có chính sách lưu mật khẩu/khóa tài khoản riêng.

### Thực hành an toàn ngay từ đầu

- **Mã hóa giao tiếp:** ưu tiên LDAPS với chứng chỉ hợp lệ hoặc StartTLS được cấu hình tường minh; xác minh hostname và tin cậy CA phù hợp.
- **Quản lý secret:** dùng biến môi trường/secret manager, giới hạn quyền đọc; không ghi mật khẩu vào log, file ví dụ commit hay tham số lệnh chứa password.
- **Quyền tối thiểu:** chỉ cấp cho tài khoản dịch vụ những thao tác, nhánh và thuộc tính cần thiết; cân nhắc tài khoản riêng cho đọc và ghi.
- **Query an toàn:** dùng query builder và API dựng DN, tránh nối trực tiếp chuỗi filter/DN từ input không tin cậy.
- **Kiểm soát tải:** xác định search base hẹp, giới hạn kết quả/thời gian, dùng phân trang hoặc API phù hợp khi cần đọc tập dữ liệu lớn.
- **Bảo vệ dữ liệu cá nhân:** chỉ trả về thuộc tính cần thiết cho nghiệp vụ, kiểm tra quyền ở API/service, không mặc định mọi attribute directory đều công khai.

## 9. Kiểm chứng directory độc lập trước khi viết code

Để xác minh môi trường, có thể dùng tiện ích dòng lệnh `ldapsearch` của OpenLDAP client. Ví dụ với directory thử nghiệm:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=directory-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn mail
~~~

Ý nghĩa:

- `-H` đặt URL server; `-D` cung cấp bind DN của tài khoản dịch vụ.
- `-W` yêu cầu nhập mật khẩu qua prompt; tránh đưa mật khẩu trực tiếp vào command.
- `-b` chọn search base; `-s sub` tìm toàn bộ cây con.
- Tham số filter giới hạn kết quả; phần cuối yêu cầu server trả các attribute `dn`, `uid`, `cn`, `mail` khi được phép.

Nếu kết quả tìm thấy:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
uid: lan
cn: Lan Nguyen
mail: lan@example.org
~~~

thì bạn đã chứng minh **tài khoản dịch vụ truy cập được entry đó với base/filter đã chọn**. Đây **chưa phải** kiểm chứng mật khẩu đăng nhập của `lan` và cũng chưa chứng minh Spring Security cho phép một người gọi API xem dữ liệu.

Để thử truy vấn một cách an toàn, dùng directory thử nghiệm có quyền rõ ràng. Tránh chạy Add/Modify/Delete trên directory tổ chức nếu không có quy trình phê duyệt và dữ liệu thử nghiệm độc lập.

### Những lỗi đầu tiên nên kiểm tra

| Triệu chứng | Khả năng cần xem xét | Kiểm tra ưu tiên |
| --- | --- | --- |
| Không kết nối được | Sai host, cổng, DNS, firewall hoặc server ngừng hoạt động. | URL/cổng LDAP, kết nối mạng. |
| `SSLHandshakeException` | Truststore/CA, chứng chỉ máy chủ hoặc hostname không hợp lệ. | Cấu hình TLS và kho CA của JVM. |
| LDAP result code `49` | Bind DN, mật khẩu, chính sách tài khoản. | Bind độc lập bằng `ldapsearch -W`. |
| LDAP result code `32` | Base DN hoặc DN đích không tồn tại/không đúng nhánh. | Xác minh cây DN, base tương đối. |
| LDAP result code `50` | Danh tính bind không đủ quyền. | ACL của server trên nhánh/attribute/thao tác. |
| Query hợp lệ nhưng rỗng | Search base, scope, filter, schema hoặc ACL ẩn dữ liệu. | Dùng cùng base/filter với `ldapsearch`; kiểm tra thuộc tính. |
| Dữ liệu Java thiếu field | Tên attribute sai, ACL ẩn thuộc tính hoặc ánh xạ entity không khớp schema. | Đọc kết quả LDIF và cấu hình `@Attribute`. |

LDAP có nhiều triển khai và chính sách khác nhau; cùng một sự cố có thể xuất hiện với thông báo lỗi không hoàn toàn giống nhau. Việc `ldapsearch` thành công cũng chưa đảm bảo JVM đã tin cậy cùng chứng chỉ LDAP, vì hai công cụ có thể sử dụng kho trust khác nhau.

## 10. Khi nào nên và không nên cho ứng dụng kết nối LDAP trực tiếp?

**Nên cân nhắc truy cập LDAP trực tiếp khi:** ứng dụng nội bộ cần đọc các entry, attribute hoặc nhóm từ directory sẵn có; cần quy trình quản trị entry được cấp quyền rõ ràng; hoặc muốn tích hợp repository Java để tìm kiếm theo DN và filter LDAP.

**Nên cân nhắc một service trung gian hoặc hệ thống khác khi:** ứng dụng công khai không được phép kết nối trực tiếp mạng nội bộ, có nhiều nguồn directory cần hợp nhất, phải áp dụng quy tắc dữ liệu phức tạp, hoặc chỉ cần “đăng nhập một lần” mà identity provider đã hỗ trợ OIDC/SAML. Với dữ liệu giao dịch cần quan hệ nhiều bảng, join và transaction, cơ sở dữ liệu nghiệp vụ thường phù hợp hơn.

Truy cập trực tiếp đồng nghĩa ứng dụng phải quản lý cấu hình kết nối, timeout, secret, TLS, ACL và việc thay đổi schema của directory. Một API trung gian có thể tập trung những trách nhiệm đó, nhưng cũng cần thiết kế phân quyền và độ tin cậy riêng.

## 11. Bài tập tình huống

Một công ty có directory dưới `dc=company,dc=internal`, gồm ba nhánh:

~~~text
ou=staff,dc=company,dc=internal
ou=teams,dc=company,dc=internal
ou=services,dc=company,dc=internal
~~~

Ứng dụng nội bộ muốn hiển thị tên/email nhân viên, tra cứu thành viên nhóm, đồng thời cho quản trị viên cập nhật số điện thoại. Tài khoản dịch vụ `cn=directory-reader,ou=services,dc=company,dc=internal` chỉ có quyền đọc.

1. Nêu ba lý do ứng dụng này có thể dùng LDAP thay vì lưu danh bạ riêng.
2. Với entry `uid=an` dưới `ou=staff`, hãy viết DN đầy đủ và chọn search base để tìm entry đó.
3. Nếu dùng `spring.ldap.base=dc=company,dc=internal`, trong `LdapQueryBuilder.query().base(...)` nên truyền giá trị gì để tìm nhân viên?
4. Tài khoản `directory-reader` có thể dùng cho chức năng quản trị sửa số điện thoại không? Cần những điều kiện nào?
5. Nếu repository tìm thấy entry `uid=an`, có thể kết luận người gọi HTTP đã xác thực là `an` không? Giải thích.
6. Nếu người dùng nhập `uid` chứa ký tự đặc biệt trong LDAP filter, API cần xây truy vấn thế nào?

**Gợi ý trả lời:**

1. Có nguồn danh bạ tập trung, tái sử dụng dữ liệu giữa nhiều ứng dụng, có thể dùng dữ liệu nhóm/đơn vị tổ chức hiện có.
2. DN `uid=an,ou=staff,dc=company,dc=internal`; base search có thể là `ou=staff,dc=company,dc=internal` với scope phù hợp.
3. Truyền base tương đối `ou=staff`, vì `dc=company,dc=internal` đã được cấu hình ở `spring.ldap.base`.
4. Chưa đủ: tài khoản chỉ đọc không thể thực hiện ghi. Cần luồng nghiệp vụ được phân quyền ở ứng dụng và một danh tính kết nối được LDAP server cấp ACL ghi đúng phạm vi, cộng kiểm tra schema, audit.
5. Không. Truy vấn chỉ xác nhận dữ liệu tồn tại; xác thực người gọi phải diễn ra qua cơ chế đăng nhập độc lập.
6. Sử dụng query builder như `where("uid").is(uid)` để escape giá trị filter; không nối chuỗi filter từ input.

## 12. Tổng kết kiến thức

LDAP là **giao thức chuẩn để truy cập directory có cấu trúc phân cấp**. Ứng dụng cần LDAP khi muốn tra cứu hoặc quản lý những thông tin dùng chung như người dùng, nhóm và thuộc tính định danh từ một dịch vụ thư mục.

Nắm vững **entry → DN/RDN → attribute/objectClass/schema → bind/search/CRUD → base DN/filter/ACL** sẽ giúp bạn hiểu các thao tác thực tế. **Spring Data LDAP** cung cấp repository và template để đưa các thao tác đó vào ứng dụng Java; còn **Spring Security** đảm nhiệm xác thực/phân quyền HTTP khi bài toán yêu cầu.

Trước khi viết repository, hãy xác nhận directory đang dùng, nhánh DN cần truy cập, schema thực tế, danh tính bind, quyền ACL, kết nối TLS và mục đích dữ liệu. Đó là nền tảng để xây ứng dụng Spring Data LDAP đúng và an toàn.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/)
