# Các tình huống tra cứu danh bạ, quản lý tài khoản và tra cứu nhóm với Spring Data LDAP

## 1. Bức tranh chung: LDAP phục vụ những bài toán nào?

**LDAP (Lightweight Directory Access Protocol)** là giao thức truy cập một **dịch vụ thư mục**: dữ liệu được tổ chức dưới dạng các *entry* có **Distinguished Name (DN)**, thuộc tính và `objectClass`, theo cấu trúc cây. Nhiều tổ chức dùng directory để lưu thông tin nhân viên, tài khoản, nhóm và các thuộc tính phục vụ xác thực hoặc phân quyền.

**Spring Data LDAP** đưa dữ liệu directory vào ứng dụng Java thông qua **repository** và khả năng ánh xạ entry thành đối tượng (**Object-Directory Mapping – ODM**) của Spring LDAP. Khi cần truy vấn hoặc thay đổi có kiểm soát ở mức thấp hơn, ứng dụng dùng **`LdapTemplate`**. Các thành phần này không biến LDAP thành cơ sở dữ liệu quan hệ; chúng giúp Java thao tác với **entry, DN, schema và filter của LDAP** bằng API phù hợp.

Ba nhóm tình huống thường gặp:

1. **Tra cứu danh bạ:** tìm người theo `uid`, tên, email hoặc phòng ban; lấy danh sách nhân viên và thông tin liên hệ.
2. **Quản lý tài khoản:** cấp phát entry, cập nhật thuộc tính, chuyển OU, vô hiệu hóa hoặc thu hồi tài khoản theo quy trình tổ chức.
3. **Tra cứu nhóm:** tìm các nhóm một người thuộc về, hiển thị thành viên nhóm, xác minh quyền dựa trên nhóm theo chính sách của ứng dụng.

Cả ba cùng dùng LDAP, nhưng **yêu cầu quyền truy cập, độ nhất quán, cách tìm kiếm và rủi ro khi ghi dữ liệu rất khác nhau**.

| Nghiệp vụ | Thao tác LDAP chính | Điểm phải lưu ý |
| --- | --- | --- |
| Tìm một nhân viên | Search theo filter hoặc Lookup theo DN | `uid` không luôn duy nhất trên toàn directory; ACL có thể che thuộc tính |
| Tìm nhân viên theo tên | Search với equality/substring filter | Escape input, tránh truy vấn quá rộng |
| Hiển thị danh bạ | Search theo base/scope, chọn thuộc tính | Size/time limits, trang kết quả và dữ liệu nhạy cảm |
| Tạo người dùng | Add/bind entry | Parent DN, `objectClass`, thuộc tính bắt buộc, quyền ghi |
| Sửa email/phòng ban | Modify | Chỉ sửa thuộc tính được phép; xử lý ghi đồng thời |
| Đổi tên/chuyển OU | ModifyDN/rename | **DN thay đổi**; phải xem tham chiếu từ nhóm và hệ thống khác |
| Tạm ngừng tài khoản | Chính sách/dữ liệu riêng của directory | Không có một attribute vô hiệu hóa chung cho mọi server |
| Xem thành viên nhóm | Lookup/Search nhóm và đọc `member`/`uniqueMember` | Giá trị thành viên thường là DN đầy đủ |
| Kiểm tra một người thuộc nhóm | Compare/Search theo thuộc tính nhóm hoặc cơ chế vendor | Nhóm lồng nhau, dynamic group, replication, ACL |

> **Ý chính:** DN cho biết một entry ở đâu trong cây; filter tìm entry theo thuộc tính; `objectClass` và schema quy định dữ liệu hợp lệ; bind identity cùng ACL quyết định ứng dụng được đọc và sửa điều gì.

## 2. Mô hình thư mục dùng xuyên suốt bài học

Giả sử một tổ chức có directory như sau:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   │   ├── objectClass: inetOrgPerson
│   │   ├── uid: alice
│   │   ├── cn: Alice Nguyen
│   │   ├── sn: Nguyen
│   │   └── mail: alice@example.org
│   └── uid=bob
│       ├── uid: bob
│       ├── cn: Bob Tran
│       └── sn: Tran
├── ou=groups
│   ├── cn=reviewers
│   │   └── uniqueMember: uid=alice,ou=people,dc=example,dc=org
│   └── cn=developers
└── ou=service-accounts
    └── uid=app-reader
~~~

Các DN đầy đủ ví dụ:

~~~text
uid=alice,ou=people,dc=example,dc=org
cn=reviewers,ou=groups,dc=example,dc=org
uid=app-reader,ou=service-accounts,dc=example,dc=org
~~~

Trong đó:

- `dc=example,dc=org` là **naming context** (cũng thường được dùng làm base DN của client).
- `ou=people`, `ou=groups` là các nhánh tổ chức.
- `uid=alice` là **Relative Distinguished Name (RDN)** của Alice dưới `ou=people`.
- `cn=reviewers` là RDN của một entry nhóm, **không phải danh sách role được Spring tự cấp**.
- `uniqueMember` chứa **DN của một entry khác**. Đây là giá trị thuộc tính trên nhóm, khác với DN định danh chính entry nhóm.

Đối với ứng dụng có `ContextSource.base = dc=example,dc=org`, nhiều thao tác của `LdapTemplate` dùng DN **tương đối**:

~~~text
uid=alice,ou=people
cn=reviewers,ou=groups
~~~

Nhưng một thuộc tính tham chiếu DN như `uniqueMember` thường mang **DN đầy đủ**, bao gồm cả suffix. Việc trộn hai dạng này mà không có quy ước là nguồn lỗi tra cứu nhóm phổ biến.

### 2.1. Schema quyết định cách lưu dữ liệu

`inetOrgPerson` thường dùng để mô hình hóa người dùng; nó kế thừa các lớp như `person` và `organizationalPerson`. Theo schema thông thường, `cn` và `sn` là những thuộc tính quan trọng/bắt buộc của `person`; `mail`, `telephoneNumber`, `title` có thể được dùng nếu schema cho phép.

Nhóm có thể là:

- `groupOfNames` với thuộc tính `member`.
- `groupOfUniqueNames` với thuộc tính `uniqueMember`.
- Một loại nhóm của Active Directory hoặc vendor khác, với cách biểu diễn và quy tắc riêng.

Không giả định mọi directory đều có cùng `objectClass`, quyền hay tên attribute. Đặc biệt, `memberOf` không phải thuộc tính ngược được mọi LDAP server tự cung cấp theo cùng cách.

## 3. Kiến trúc Spring Data LDAP trong ứng dụng

~~~mermaid
flowchart TD
    A["Web/API, batch hoặc nghiệp vụ"] --> B["Application service"]
    B --> C["LdapRepository và ODM"]
    B --> D["LdapTemplate và filter builder"]
    C --> E["Spring LDAP ContextSource"]
    D --> E
    E --> F["LDAPv3 qua LDAPS / StartTLS"]
    F --> G["Directory server: DN, schema, ACL"]
    G --> H["People, Groups, Service Accounts"]
~~~

Phân biệt vai trò:

| Thành phần | Dùng khi nào? |
| --- | --- |
| **`LdapRepository<T>`** | CRUD entity theo DN, các truy vấn đơn giản từ tên phương thức hoặc `@Query` |
| **ODM annotations** (`@Entry`, `@Id`, `@Attribute`) | Chuyển entry có `objectClass`/thuộc tính LDAP thành object Java |
| **`LdapTemplate`** | Search theo base/scope/filter cụ thể, đọc raw attributes, Modify/rename hoặc xử lý các control nâng cao |
| **`ContextSource` / `LdapContextSource`** | Cấu hình endpoint, base DN, bind identity, TLS và cách lấy kết nối |
| **LDAP server** | Áp dụng schema, matching rules, ACL, hạn chế kích thước/thời gian và chính sách account |

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Đây là cấu hình minh họa, không phải lời khuyên lưu mật khẩu vào file. `spring.ldap.base` chỉ đặt **base của client**; nó không tạo OU hoặc entry ở server. Endpoint phải phục vụ đúng directory và **TLS certificate của server phải được client Java tin cậy, khớp hostname**.

Phụ thuộc điển hình với Spring Boot:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Trong dự án thật, quản lý phiên bản theo Spring Boot BOM và bảo đảm các bean `ContextSource`, `LdapTemplate`, repository scanning được cấu hình phù hợp.

## 4. Tình huống 1: tra cứu nhân viên theo mã định danh

Một hệ thống nội bộ cần hiển thị hồ sơ nhân viên từ `uid` người dùng nhập. Có hai chiến lược.

### 4.1. Đã biết đúng DN: Lookup theo DN

Nếu ứng dụng đã biết Alice nằm dưới `ou=people`, DN tương đối có thể là:

~~~text
uid=alice,ou=people
~~~

Spring LDAP có thể đọc trực tiếp các thuộc tính:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryLookupService {

    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public record PersonContact(String uid, String name, String email) {}

    public PersonContact loadPerson(String inputUid) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", inputUid)
            .build();

        return ldapTemplate.lookup(
            relativeDn,
            new String[] { "uid", "cn", "mail" },
            attrs -> new PersonContact(
                String.valueOf(attrs.get("uid").get()),
                String.valueOf(attrs.get("cn").get()),
                attrs.get("mail") == null
                    ? null
                    : String.valueOf(attrs.get("mail").get())
            )
        );
    }
}
~~~

Trong ví dụ, `LdapNameBuilder` giúp escape giá trị **DN** đúng cú pháp nếu `inputUid` chứa ký tự đặc biệt. Việc escape không thay thế kiểm soát nghiệp vụ: cần xác nhận UID hợp lệ, giới hạn nhánh và quyền yêu cầu.

Cần lưu ý:

- Nếu DN không tồn tại, lookup có thể ném exception như `NameNotFoundException`/`DataAccessException` được Spring chuyển đổi, chứ không phải luôn trả `null`.
- `mail` có thể vắng mặt do dữ liệu tùy chọn hoặc ACL; mapper phải xử lý.
- Nếu muốn API trả `Optional.empty()` cho trường hợp DN không tồn tại, service có thể xử lý riêng lỗi “không tìm thấy”; **không nuốt lỗi mạng/TLS/bind**.
- Lookup theo DN là chọn **một vị trí cụ thể**, không phải tìm UID trên nhiều OU.

### 4.2. Chỉ biết thuộc tính `uid`: Search bằng filter an toàn

Khi nhân viên có thể ở `ou=people`, `ou=contractors` hoặc các nhánh khác, cần Search thay vì dựng một DN cố định.

~~~java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String inputUid) {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("cn")
            .countLimit(20)
            .timeLimit(3000)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(inputUid);

        return ldapTemplate.search(
            q,
            attrs -> String.valueOf(attrs.get("cn").get())
        );
    }
}
~~~

`.is(inputUid)` xử lý input như **giá trị của filter**, không phải một đoạn filter được phép chèn thêm dấu ngoặc/toán tử. Tên attribute và base được **ứng dụng quyết định**.

Một cách làm nguy hiểm:

~~~java
// Không dùng với dữ liệu chưa tin cậy.
String filter = "(&(objectClass=inetOrgPerson)(uid=" + inputUid + "))";
~~~

Nếu input có các ký tự đặc biệt như `*`, `(`, `)` hoặc `\`, filter có thể đổi nghĩa, truy vấn rộng hơn hoặc sai cú pháp. Dùng `LdapQueryBuilder`, `EqualsFilter` hoặc cơ chế bind parameter được mã hóa đúng.

**`uid` không nhất thiết duy nhất toàn directory.** Với Search nhiều OU, có thể có hai entry cùng UID; hợp đồng nghiệp vụ phải xác định đây là lỗi dữ liệu, hay cần phân biệt bằng **DN đầy đủ**, employee ID hoặc một định danh ổn định được tổ chức quản lý.

## 5. Tình huống 2: danh bạ cho giao diện tìm kiếm

Một trang danh bạ nội bộ thường cho phép:

- Tìm theo tên, email, phòng ban hoặc một số tiêu chí được duyệt.
- Hiển thị danh sách rút gọn: tên, email công việc, bộ phận.
- Mở chi tiết khi người dùng có quyền.
- Chỉ hiển thị những trường được LDAP ACL và chính sách sản phẩm cho phép.

### 5.1. Exact match, prefix và substring không giống nhau

| Mục tiêu người dùng | Ngữ nghĩa LDAP | Ví dụ ý tưởng |
| --- | --- | --- |
| Tìm UID bằng `alice` | Equality | `(uid=alice)` |
| Tên bắt đầu bằng `Ali` | Substring prefix | `(cn=Ali*)` |
| Tên chứa `Nguyen` | Substring contains | `(cn=*Nguyen*)` |
| Tên đúng chuỗi `A*B` | Dấu sao là dữ liệu literal | `(cn=A\2aB)` |
| Liệt kê entry có `mail` | Presence | `(mail=*)` |

**Wildcard `*` do ứng dụng chủ ý đặt** trong substring filter phải được phân biệt với dấu `*` mà người dùng nhập dưới dạng **dữ liệu**. Với đầu vào người dùng, ưu tiên filter builder hoặc phương thức repository mã hóa tham số, không nối chuỗi LDAP filter.

Tìm kiếm theo một ký tự hoặc theo cả cây directory có thể rất tốn tài nguyên dù filter hợp lệ về cú pháp. Cần:

1. Hạn chế base DN và scope.
2. Giới hạn số kết quả, thời gian tìm kiếm và lượng dữ liệu trả về.
3. Không mặc định tải ảnh nhị phân `jpegPhoto` hay toàn bộ thuộc tính nhạy cảm.
4. Theo dõi kết quả bị cắt do size/time limit; không mô tả một tập kết quả chưa đầy đủ là “đã tìm hết”.
5. Dùng paging/control theo khả năng server khi danh sách lớn, không tự coi `Pageable` của repository có hành vi giống JPA.

### 5.2. Chọn cách tổ chức endpoint

Ví dụ một API ứng dụng:

~~~text
GET /directory/people?uid=alice
GET /directory/people?name=Ali&mode=PREFIX
GET /directory/people/{personId}
~~~

Đây là API HTTP do **ứng dụng tự thiết kế**, không phải endpoint có sẵn của Spring Data LDAP. Nếu dùng `personId` ổn định cho frontend, không nên bắt buộc lộ DN tùy ý của directory ra ngoài. Ứng dụng có thể ánh xạ một mã nhân viên ổn định sang DN hiện tại.

Không đưa tùy ý toàn bộ filter LDAP từ request vào `LdapTemplate`. API nên nhận các tham số nghiệp vụ đã được giới hạn, sau đó dịch sang filter có cấu trúc rõ ràng.

## 6. Tình huống 3: quản lý vòng đời tài khoản

Tra cứu danh bạ chủ yếu là **đọc**; quản lý tài khoản làm thay đổi state của directory và có thể ảnh hưởng xác thực/quyền truy cập thực tế. Vì vậy cần phân tách tài khoản dịch vụ và quy trình vận hành.

Một vòng đời đơn giản:

~~~mermaid
flowchart TD
    A["Yêu cầu cấp tài khoản"] --> B["Kiểm tra dữ liệu và quyền"]
    B --> C["Tạo entry đúng DN/schema"]
    C --> D["Kiểm tra bind/trạng thái theo chính sách"]
    D --> E["Cập nhật thuộc tính, OU hoặc nhóm"]
    E --> F{"Thay đổi nhân sự?"}
    F -->|Chuyển bộ phận| G["Đổi thuộc tính, nhóm hoặc DN nếu cần"]
    F -->|Nghỉ việc| H["Vô hiệu hóa theo cơ chế server"]
    G --> E
    H --> I["Thu hồi nhóm/phiên/quyền liên quan"]
    I --> J["Lưu giữ hoặc xóa theo chính sách"]
~~~

Các bước nghiệp vụ cần **được định nghĩa rõ**; LDAP protocol không cung cấp sẵn một workflow HR hoàn chỉnh.

### 6.1. Cấp phát entry (Add)

Giả sử parent `ou=people,dc=example,dc=org` đã có, và tài khoản dịch vụ được quyền tạo đúng loại entry. `LdapTemplate.bind(...)` có thể dùng để thêm một entry với các thuộc tính bắt buộc:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class AccountProvisioningService {

    private final LdapTemplate ldapTemplate;

    public AccountProvisioningService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name createPerson(String uid, String cn, String sn) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        BasicAttributes attrs = new BasicAttributes(true);
        BasicAttribute objectClasses = new BasicAttribute("objectClass");
        objectClasses.add("top");
        objectClasses.add("person");
        objectClasses.add("organizationalPerson");
        objectClasses.add("inetOrgPerson");

        attrs.put(objectClasses);
        attrs.put("uid", uid);
        attrs.put("cn", cn);
        attrs.put("sn", sn);

        ldapTemplate.bind(dn, null, attrs);
        return dn;
    }
}
~~~

**Các giả định cần kiểm tra:**

- Directory hỗ trợ các `objectClass` và thuộc tính này.
- `cn`, `sn` đáp ứng schema; parent OU tồn tại.
- `uid` đã được xác minh về định dạng và tính duy nhất trong **phạm vi nghiệp vụ**, không chỉ escape DN.
- Tài khoản bind được cấp đúng quyền **add** trên OU này.
- `bind(...)` ở đây là **thao tác thêm entry của `LdapTemplate`**, khác với *LDAP authentication bind* dùng DN/password để đăng nhập.
- Việc thêm entry **không đồng nghĩa người dùng đã có thể đăng nhập**: mật khẩu, chính sách tài khoản, cơ chế auth và trạng thái kích hoạt phụ thuộc directory.

Nếu DN đã tồn tại, Add thường bị từ chối với lỗi tương ứng; không mặc định đây là upsert. Tránh “tìm thấy thì bỏ qua” mà không so state, vì entry có thể tồn tại nhưng thiếu thuộc tính cần thiết.

### 6.2. Đọc và cập nhật qua repository

Với Spring LDAP ODM, entity thường có:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
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

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String value) { this.commonName = value; }

    public String getSurname() { return surname; }
    public void setSurname(String value) { this.surname = value; }

    public String getEmail() { return email; }
    public void setEmail(String value) { this.email = value; }
}
~~~

Repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    // Các method query theo thuộc tính có thể bổ sung tại đây.
}
~~~

Đọc và cập nhật email:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public PersonEntry changeEmail(
        PersonRepository repository,
        String uid,
        String email) {

    Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", uid)
        .build();

    PersonEntry entry = repository.findById(dn)
        .orElseThrow(() -> new IllegalArgumentException(
            "Không tìm thấy tài khoản"
        ));

    entry.setEmail(email);
    return repository.save(entry);
}
~~~

Đây là phương thức minh họa đặt trong lớp service và nhận `repository` làm tham số để tập trung vào nghiệp vụ.

Cần hiểu đúng hợp đồng của `save`:

- Entity có DN và đã được đọc từ directory thường được **cập nhật**, không phải tự động thêm một bản ghi mới.
- Entity chưa có DN cần mapping tạo DN phù hợp (ví dụ `@DnAttribute`), không được giả định repository phát sinh ID số như JPA.
- Đọc rồi `save` không mặc định bảo đảm **optimistic locking**, khóa lâu dài hay toàn bộ thao tác là transaction ACID.
- Nếu một object chỉ được nạp vài thuộc tính rồi `save` toàn bộ, có thể ghi đè hoặc làm mất state không mong muốn. Khi cần sửa đúng một thuộc tính, `LdapTemplate.modifyAttributes(...)` có thể phù hợp hơn.

### 6.3. Cập nhật đúng một thuộc tính

Một thao tác Modify chỉ nhắm `mail` có thể diễn đạt bằng:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public void replaceEmail(
        LdapTemplate ldapTemplate,
        Name relativeUserDn,
        String newMail) {

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newMail)
        )
    };

    ldapTemplate.modifyAttributes(relativeUserDn, changes);
}
~~~

Ở đây `relativeUserDn` phải là DN đúng trong phạm vi `ContextSource` và được tạo/xác minh an toàn. `REPLACE_ATTRIBUTE` thay giá trị của thuộc tính đó; các quyền Modify và quy tắc schema vẫn được LDAP server kiểm tra. Không dùng đoạn này để sửa thuộc tính quản trị hoặc trạng thái account mà không hiểu cơ chế vendor.

### 6.4. Chuyển OU hoặc đổi RDN

Khi Alice chuyển sang nhánh khác:

~~~text
Trước: uid=alice,ou=people,dc=example,dc=org
Sau:   uid=alice,ou=contractors,dc=example,dc=org
~~~

Đây là thao tác **ModifyDN/rename**, không đơn thuần sửa một trường `department`. Spring LDAP hỗ trợ:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.springframework.ldap.core.LdapTemplate;

Name oldDn = new LdapName("uid=alice,ou=people");
Name newDn = new LdapName("uid=alice,ou=contractors");

ldapTemplate.rename(oldDn, newDn);
~~~

Việc chuyển giữa nhánh hoặc partition có thể bị server hạn chế. Cần kiểm tra OU đích, quyền, schema và **tham chiếu DN từ nhóm**, hệ thống khác hoặc ứng dụng. Không mặc định LDAP server sẽ sửa tất cả các `member`/`uniqueMember` hay dữ liệu bên ngoài sau rename.

### 6.5. Vô hiệu hóa và xóa tài khoản

Không có một thuộc tính “disable account” chuẩn chung cho **mọi** LDAP directory. Ví dụ:

- Một hệ thống có **policy riêng** hoặc thuộc tính đặc thù để ngăn xác thực.
- Active Directory dùng các thuộc tính và quy tắc riêng như `userAccountControl`.
- Một số directory dùng **password policy**, trạng thái khóa hoặc quy trình quản lý danh tính bên ngoài.

Vì thế, đừng viết một thao tác `@Attribute(name="disabled")` và giả định nó có hiệu lực ở mọi LDAP server. Quy trình vô hiệu hóa cần được xác nhận với nhóm vận hành directory và kiểm thử **đăng nhập/bind theo phương thức thực tế**.

**Xóa** entry là một quyết định riêng, có thể ảnh hưởng lịch sử, nhóm, audit và hệ thống tích hợp. Một lệnh `repository.deleteById(dn)` hoặc `ldapTemplate.unbind(dn)` không mang theo cơ chế cascade của JPA; các entry tham chiếu tới DN đó có thể cần được xử lý theo quy trình hoặc cơ chế referential integrity của server.

## 7. Tình huống 4: tra cứu các nhóm của một người

Trong nhiều ứng dụng, chức năng cần trả lời câu hỏi:

> Alice có thuộc nhóm `reviewers` không? Alice thuộc những nhóm nào?

Câu hỏi này chỉ có nghĩa đầy đủ khi ta biết **mô hình nhóm của directory**.

### 7.1. Nhóm lưu DN của thành viên

Ví dụ:

~~~ldif
dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

`uniqueMember` chứa DN **đầy đủ** của Alice. Nếu schema dùng `groupOfNames`, thuộc tính tương ứng thường là `member`, không phải `uniqueMember`.

Có thể đọc trực tiếp thành viên một nhóm bằng `LdapTemplate.lookup`:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.LdapTemplate;

public List<String> listDirectMemberDns(LdapTemplate ldapTemplate) {
    return ldapTemplate.lookup(
        "cn=reviewers,ou=groups",
        new String[] { "uniqueMember" },
        attrs -> {
            List<String> members = new ArrayList<>();
            Attribute values = attrs.get("uniqueMember");
            if (values == null) {
                return members;
            }

            for (int i = 0; i < values.size(); i++) {
                members.add(String.valueOf(values.get(i)));
            }

            return members;
        }
    );
}
~~~

Hàm trên đọc **thành viên trực tiếp được lưu trên entry nhóm**, không tự mở rộng nested groups hay dynamic membership. Các giá trị cần được giữ như **DN**, không coi `uniqueMember` là danh sách `uid` đơn giản. Khi ứng dụng cần hiển thị tên của từng thành viên, có thể tra theo DN tương ứng và xử lý member đã bị xóa/đổi DN.

**Không đọc `get()` duy nhất** rồi cho rằng thuộc tính nhóm chỉ có một thành viên. `uniqueMember` thường là **đa trị**.

### 7.2. Tìm các nhóm chứa DN của Alice

Khi biết DN đầy đủ:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Có thể tìm những nhóm trực tiếp chứa DN đó:

~~~java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public List<String> findDirectGroupNames(
        LdapTemplate ldapTemplate,
        String fullUserDn) {

    LdapQuery ldapQuery = query()
        .base("ou=groups")
        .searchScope(SearchScope.SUBTREE)
        .attributes("cn")
        .countLimit(200)
        .timeLimit(3000)
        .where("objectClass").is("groupOfUniqueNames")
        .and("uniqueMember").is(fullUserDn);

    return ldapTemplate.search(
        ldapQuery,
        attrs -> String.valueOf(attrs.get("cn").get())
    );
}
~~~

`.is(fullUserDn)` đưa DN vào **giá trị filter được escape** theo cơ chế builder. Tuy nhiên, ứng dụng vẫn phải xác định **định danh người dùng** từ nguồn đáng tin, không cho caller tự chọn DN nào để hỏi về quyền truy cập của người khác mà không được phân quyền.

**Phạm vi tìm kiếm:** kết quả chỉ gồm các nhóm phù hợp dưới `ou=groups` với `objectClass=groupOfUniqueNames`. Nếu directory có nhóm ở OU khác, có nhiều loại objectClass hoặc một cơ chế membership không lưu trực tiếp DN trong `uniqueMember`, truy vấn này **không phải danh sách nhóm đầy đủ**.

### 7.3. `memberOf` không phải lời giải phổ quát

Một số directory cung cấp thuộc tính **`memberOf`** ở entry người dùng, phản chiếu các nhóm có chứa họ. Nhưng:

- Đây không phải lời hứa phổ quát của giao thức LDAP rằng mọi server đều trả `memberOf`.
- Nó có thể cần module/overlay/cấu hình riêng hoặc chỉ phản ánh một số kiểu nhóm.
- ACL có thể che giá trị; loại group, nested group hoặc referral có thể tạo khác biệt.
- Dữ liệu phản chiếu hoặc index có thể trễ so với thao tác Modify thực.

Khi chưa rõ directory, hãy bắt đầu từ **schema nhóm đang dùng** và kiểm tra bằng dữ liệu thật, không mặc định `PersonEntry` lúc nào cũng có field `memberOf`.

## 8. Thành viên nhóm có đồng nghĩa với quyền truy cập ứng dụng không?

**Không tự động.** Có ít nhất ba khái niệm cần tách:

1. **Directory membership:** LDAP server nói entry người dùng có được lưu trong nhóm hay không.
2. **Authentication:** người dùng có thực sự chứng minh được danh tính bằng phương thức đăng nhập được hệ thống cho phép hay không.
3. **Authorization:** ứng dụng quy đổi nhóm/thông tin danh tính thành những **quyền cụ thể** nào đối với tài nguyên hoặc thao tác.

Ví dụ:

~~~text
LDAP group DN:
cn=reviewers,ou=groups,dc=example,dc=org

Business policy:
Nếu người dùng đã được xác thực,
và được kiểm tra là thành viên trực tiếp của reviewers,
thì có quyền xem màn hình kiểm duyệt.
~~~

Chính sách trên do **ứng dụng** quyết định. Không được suy ra rằng bất kỳ ai đọc được DN nhóm thì tự động có quyền hệ thống, hoặc rằng người dùng có DN tương ứng với một entry LDAP là đã đăng nhập hợp lệ.

### 8.1. Nhóm lồng nhau và nhóm động

Ví dụ một nhóm có thể chứa một **DN của nhóm khác**:

~~~text
cn=engineering,ou=groups,...  -> uniqueMember: cn=developers,ou=groups,...
cn=developers,ou=groups,...   -> uniqueMember: uid=alice,ou=people,...
~~~

Tìm nhóm trực tiếp của Alice chỉ nhận `developers`, chưa chắc nhận `engineering`. Nếu muốn **nested membership**, ứng dụng phải áp dụng cơ chế được directory hỗ trợ hoặc thuật toán duyệt có:

- Giới hạn **độ sâu** và số nhóm để không lặp vô hạn.
- Tập DN đã thăm (*visited*) để xử lý vòng lặp.
- Quy tắc cho loại nhóm, schema và ACL.
- Cách xử lý group member không còn tồn tại.
- Chính sách nhất quán nếu membership thay đổi khi đang duyệt.

Một số directory cung cấp toán tử hoặc cơ chế transitive membership đặc thù; không coi đó là tính năng chuẩn của mọi LDAP server. Với nhóm động, thành viên có thể được suy từ filter/URL thay vì lưu sẵn trong `member`/`uniqueMember`, nên cần một đường xử lý khác.

### 8.2. Tránh cấp quyền dựa trên dữ liệu chưa được xác minh

Nếu hệ thống nhận `userDn` từ HTTP query rồi hỏi “DN này có ở nhóm reviewers không?”, người dùng có thể thử DN của người khác. Với một API cấp quyền, **định danh được kiểm tra phải đến từ phiên xác thực/tokens đã được xác minh**, sau đó mới đối chiếu membership và chính sách.

Các bước khuyến nghị:

~~~mermaid
flowchart TD
    A["Request đã xác thực"] --> B["Lấy user identity đáng tin"]
    B --> C["Xác định DN tương ứng trong directory"]
    C --> D["Tra cứu membership theo schema/ACL"]
    D --> E["Áp dụng chính sách role/permission của ứng dụng"]
    E --> F{"Đủ điều kiện?"}
    F -->|Có| G["Cho phép nghiệp vụ cụ thể"]
    F -->|Không / không chắc chắn| H["Từ chối hoặc xử lý lỗi an toàn"]
~~~

Nếu LDAP tạm thời không khả dụng, không được âm thầm coi “không kiểm tra được membership” là “đã có quyền”. Quy tắc lỗi an toàn phụ thuộc yêu cầu availability và security, nhưng với quyết định cấp quyền nhạy cảm nên **fail closed** hoặc dùng cache đáng tin cậy có TTL/chính sách rõ ràng.

## 9. Tình huống 5: thêm hoặc xóa một người khỏi nhóm

Một ứng dụng quản lý nhóm cần cập nhật **entry nhóm**, không chỉ thay đổi thuộc tính trong `PersonEntry`.

Giả sử `cn=reviewers` thuộc `groupOfUniqueNames`. Thêm một DN vào danh sách `uniqueMember`:

~~~java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public void addDirectMember(
        LdapTemplate ldapTemplate,
        String fullUserDn) {

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("uniqueMember", fullUserDn)
        )
    };

    ldapTemplate.modifyAttributes(
        "cn=reviewers,ou=groups",
        changes
    );
}
~~~

Muốn xóa một giá trị cụ thể, thường dùng `DirContext.REMOVE_ATTRIBUTE` cùng một `BasicAttribute("uniqueMember", fullUserDn)` trong `ModificationItem`.

Các lưu ý:

- Cần quyền **modify** trên entry và attribute nhóm; quyền đọc nhóm không đủ.
- Giá trị thành viên phải theo schema, thường là **DN đầy đủ** và entry/nhóm hợp lệ theo chính sách.
- Nếu thành viên đã có trong tập thuộc tính đa trị, server có thể trả lỗi loại `attributeOrValueExists`.
- Nhóm `groupOfUniqueNames` thường yêu cầu `uniqueMember` không rỗng; xóa **thành viên cuối** có thể bị schema từ chối.
- Thêm thành viên và cập nhật hồ sơ người dùng là **hai thao tác trên hai entry**; không tự động là một transaction nguyên tử.
- Khi ghi vào một replica/node, đọc từ node khác ngay sau đó có thể chưa thấy thay đổi nếu replication là bất đồng bộ.

Không sử dụng tài khoản read-only cho thao tác này, và không cấp quyền sửa **mọi nhóm** nếu nghiệp vụ chỉ quản lý một tập nhóm cụ thể.

## 10. Dữ liệu lớn, độ trễ và tính nhất quán

LDAP server được tối ưu cho các kiểu tra cứu thư mục thường gặp, nhưng kết quả phụ thuộc index, schema, filter, kích thước directory và chính sách server.

### 10.1. Bài toán danh bạ lớn

Khi `ou=people` chứa hàng chục nghìn entry:

- Tránh `repository.findAll()` vô điều kiện cho màn hình danh sách.
- Xác định filter đủ hẹp, scope phù hợp và các thuộc tính cần trả.
- Tôn trọng **server size/time/admin limits**; không coi danh sách bị cắt là toàn bộ directory.
- Nếu cần quét nhiều entry, dùng **Simple Paged Results Control** (RFC 2696) khi server hỗ trợ, với cookie được tiếp tục đúng cách. Nó không tương đương SQL `OFFSET/LIMIT`.
- Với `LdapTemplate`, kiểm soát số lượng request và tài nguyên; cookie phân trang có thể gắn với kết nối LDAP hoặc trạng thái server.

Phân trang không tự bảo đảm snapshot. Trong lúc ứng dụng duyệt nhiều trang, nhân viên có thể được thêm, xóa hoặc chuyển OU; một entry có thể bị lặp/bỏ sót tùy server và thời điểm.

### 10.2. Cập nhật tài khoản và nhóm là nhiều thao tác

Ví dụ quy trình onboarding:

1. Tạo entry Alice.
2. Đặt một số thuộc tính theo chính sách.
3. Thêm Alice vào nhóm `developers`.
4. Đồng bộ ứng dụng/hệ thống khác.

Nếu bước 3 thất bại, bước 1 và 2 có thể **đã thành công**. Vì vậy ứng dụng cần:

- Có ID yêu cầu/onboarding event để **đối soát** trạng thái.
- Thiết kế thao tác có thể lặp lại có kiểm soát; phân biệt “đã tồn tại đúng state” với lỗi.
- Ghi audit không chứa mật khẩu, dữ liệu nhạy cảm.
- Có retry với phân loại lỗi phù hợp, tránh tạo entry trùng hoặc thêm membership trùng.
- Có quy trình bù trừ/quarantine/manual review cho trạng thái dở dang.

Không cho rằng `@Transactional` của Spring luôn biến nhiều LDAP entry thành giao dịch ACID phía directory. Khả năng transaction thực tế tùy server và cơ chế hỗ trợ.

### 10.3. Caching danh bạ và membership

Cache danh bạ giúp giảm truy vấn lặp lại nhưng có rủi ro:

| Dữ liệu được cache | Lợi ích | Rủi ro chính |
| --- | --- | --- |
| Tên/email công việc | Tăng tốc giao diện | Thông tin đổi hoặc account bị xóa vẫn được hiển thị |
| DN của người dùng | Tránh search lặp lại | DN thay đổi khi rename/chuyển OU |
| Danh sách thành viên nhóm | Giảm truy vấn quyền | Quyền đã thu hồi nhưng cache vẫn cho phép |
| Kết quả “không tìm thấy” | Tránh lookup tốn tài nguyên | Account mới chưa xuất hiện cho đến khi cache hết hạn |

TTL và cơ chế invalidation phải theo **mức nhạy cảm của từng quyết định**. Với nhóm dùng để cấp quyền quan trọng, cache cũ có thể dẫn đến cấp quyền sau khi đã thu hồi; nên xác định TTL ngắn hoặc cơ chế sự kiện phù hợp và có test.

## 11. Bảo mật kết nối, danh tính và quyền thao tác

Một ứng dụng truy cập LDAP cần phân biệt **bind account của chính ứng dụng** với **tài khoản người dùng cuối**.

- **Service bind account:** ứng dụng dùng để tìm/đọc (và nếu được phép, sửa) entry. Quyền của account này nên **tối thiểu**, giới hạn trên OU và attribute cần dùng.
- **End-user authentication:** nếu ứng dụng dùng LDAP để xác thực, phải có quy trình bảo mật riêng (ví dụ xác minh bind theo chính sách, hoặc tích hợp hệ thống IAM). Không “xác thực” bằng việc thấy entry tồn tại.
- **Application roles:** phải là **kết quả của chính sách phân quyền**, không chỉ một chuỗi `cn` từ LDAP.

### Một số nguyên tắc thực hành

1. Dùng **LDAPS** hoặc **StartTLS** khi gửi credential/dữ liệu nhạy cảm; xác minh CA chain và hostname, không dùng trust-all.
2. Giữ password/secret trong secret store, không commit trong `application.yml` và không log bind password.
3. Với truy vấn theo input, dùng `LdapQueryBuilder`, `EqualsFilter` hoặc query binding đúng; **escape filter khác escape DN**.
4. Không nhận DN/LDAP filter tùy ý từ caller rồi thực hiện Modify/Delete nếu chưa xác minh quyền và giới hạn nhánh.
5. Chỉ trả về thuộc tính cần cho nghiệp vụ, tôn trọng ACL và chính sách bảo vệ dữ liệu cá nhân.
6. Khi directory unreachable hoặc trả lỗi quyền, không gộp lỗi thành “người dùng không tồn tại” hoặc “đã có quyền”.
7. Kiểm tra `memberOf`, nested group, controls và account-state attribute theo **tài liệu server thực tế**, không dựa vào giả định chung.
8. Theo dõi timeout, tỷ lệ lỗi TLS/bind/search, latency, server limits và hoạt động thay đổi membership.

## 12. Ví dụ quy trình end-to-end

Một hệ thống nội bộ có hai màn hình: **Danh bạ nhân viên** và **Duyệt yêu cầu**.

### Luồng A — tra cứu danh bạ

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant API as Directory API
    participant LDAP as LDAP server
    U->>API: Tìm tên "Ali"
    API->>API: Kiểm tra input, mode PREFIX, giới hạn kết quả
    API->>LDAP: Search base=ou=people, filter an toàn
    LDAP-->>API: Entry + thuộc tính được ACL cho phép
    API->>API: Ánh xạ PersonEntry/DTO
    API-->>U: Tên, email và thông tin được phép
~~~

Những điều cần làm rõ trong thiết kế:

- Người dùng không gửi LDAP filter trực tiếp.
- Server có thể không trả `mail`; DTO không được tự suy đoán email.
- Nếu vượt giới hạn kết quả, API phải báo trạng thái phù hợp hoặc cung cấp cơ chế tiếp tục.
- Tra cứu danh bạ không tự cấp quyền chỉnh sửa tài khoản.

### Luồng B — kiểm tra quyền duyệt

~~~mermaid
sequenceDiagram
    participant U as Người dùng đã xác thực
    participant API as Authorization service
    participant LDAP as LDAP server
    U->>API: Yêu cầu duyệt công việc
    API->>API: Lấy identity đáng tin từ phiên xác thực
    API->>LDAP: Xác định DN hiện tại của user
    LDAP-->>API: DN + trạng thái hiện có
    API->>LDAP: Kiểm tra membership trong reviewers
    LDAP-->>API: Kết quả theo ACL và schema nhóm
    API->>API: Áp dụng policy của ứng dụng
    API-->>U: Cho phép hoặc từ chối
~~~

Với một hệ thống dùng nhóm lồng nhau, bước tra cứu membership phải xét chính sách nested-group được hỗ trợ. Với hệ thống có quyền nhạy cảm, cần hành vi an toàn khi LDAP timeout hoặc kết quả không xác định.

### Luồng C — onboarding người dùng

~~~text
Yêu cầu HR đã duyệt
  |
  +--> Xác minh UID / DN / parent OU / schema
  |
  +--> Add person entry (hoặc nhận diện entry đã tồn tại)
  |
  +--> Đặt thuộc tính/trạng thái theo chính sách IAM
  |
  +--> Modify group membership theo quyền được cấp
  |
  +--> Đọc lại và đối soát kết quả
  |
  +--> Ghi audit + đánh dấu hoàn tất / cần bù trừ
~~~

Khi lỗi ở bước membership, không xóa entry tùy tiện nếu tài khoản đã được một hệ thống khác sử dụng. Quy trình bù trừ phải theo chính sách onboarding và khả năng quan sát trạng thái thực.

## 13. Kiểm thử: làm sao biết từng tình huống hoạt động?

Để kiểm chứng Spring Data LDAP, nên dùng **directory thử nghiệm thật**: embedded LDAP hoặc container, với LDIF fixture và schema/ACL phù hợp. Mock repository có ích cho business logic nhưng không chứng minh filter escaping, schema hay Modify của server.

### 13.1. Bộ dữ liệu LDIF minh họa

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: reviewers
uniqueMember: uid=alice,ou=people,dc=example,dc=org
~~~

LDIF này chỉ dùng cho **directory test sạch**. Nếu image đã tạo root `dc=example,dc=org`, phải bỏ record root để tránh `entryAlreadyExists`. Parent DN cần tồn tại trước child; sơ đồ LDIF sử dụng `ou=people`, `ou=groups` làm parent cho user và group.

### 13.2. Ma trận integration test

| Ca kiểm thử | Cách thực hiện | Điều cần xác minh |
| --- | --- | --- |
| Tra cứu DN chính xác | Lookup `uid=alice,ou=people` | Trả đúng `uid`, `cn`, `mail` |
| Search theo UID | Filter equality có input `alice` | Trả Alice, không lẫn Bob |
| Input đặc biệt | `uid`/`cn` có `*`, `(`, `)` | Filter được escape; không mở rộng truy vấn |
| Search sai base | Dùng OU không tồn tại | Báo lỗi đúng tầng, không hiểu là entry thiếu |
| Thiếu quyền đọc `mail` | Bind account hạn chế | Không để lộ `mail`; mapper xử lý vắng mặt |
| Tạo entry hợp lệ | Add `inetOrgPerson` với đủ `cn`, `sn` | Server chấp nhận, đọc lại đúng DN |
| Tạo DN trùng | Add lại cùng DN | Bị server từ chối; entry gốc không ghi đè |
| Sửa `mail` | Modify/Save trong OU thử | Đọc lại đúng email, DN không đổi |
| Chuyển OU | Rename trên server có hỗ trợ | DN mới xuất hiện; kiểm tra tham chiếu nhóm |
| Xem nhóm | Lookup `cn=reviewers` | `uniqueMember` chứa DN của Alice |
| Tìm nhóm của Alice | Search `uniqueMember=fullDN` | Trả đúng nhóm trực tiếp |
| Nhóm lồng nhau | Tạo hai nhóm có quan hệ | Chỉ coi nested membership được hỗ trợ nếu đã kiểm thử |
| Thu hồi membership | Remove `uniqueMember` ở dữ liệu thử | Quyền ứng dụng được cập nhật theo policy/cache |
| Hỏng kết nối LDAP | Tắt endpoint hoặc sai TLS | Không giả lỗi mạng thành “không có quyền” |
| Replication/cache | Đọc ngay sau update ở node khác | Không suy ra nhất quán tức thời |

Với test dữ liệu ghi/xóa, dùng OU riêng hoặc DN riêng theo từng test, cleanup có kiểm soát và không dùng account production. Các thuộc tính password/trạng thái login đặc thù phải được test bằng cơ chế directory thực tế, không chỉ inspect một field LDAP.

## 14. Các lỗi hiểu nhầm hay gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “UID là khóa chính toàn cục” | Lẫn hai entry ở hai OU | DN xác định entry; UID có phạm vi/uniqueness theo chính sách |
| “Base DN trong Spring tạo OU” | `noSuchObject` | Base là cấu hình client; server cần có entry |
| “Tìm thấy account là xác thực thành công” | Lỗ hổng xác thực | Phải kiểm tra danh tính bằng cơ chế auth hợp lệ |
| “Có group DN là có quyền” | Cấp quyền sai | Membership và authorization là hai bước khác nhau |
| “`memberOf` luôn tồn tại” | Tra cứu nhóm rỗng bất ngờ | Phụ thuộc directory/schema/plugin/vendor |
| “Mọi nhóm đều dùng `member`” | Search bỏ sót group | Có `uniqueMember`, loại nhóm khác hoặc dynamic group |
| “Group lookup tự tính nhóm lồng nhau” | Bỏ sót quyền hoặc cấp nhầm | Phải định nghĩa và kiểm thử transitive membership |
| “Repository giống JPA” | Giả định upsert/transaction/sort/paging sai | LDAP có DN, schema, control và giới hạn riêng |
| “Đổi UID chỉ là sửa text” | Mất tham chiếu DN | RDN/ModifyDN có thể thay đổi danh tính vị trí |
| “Xóa người dùng xóa mọi membership” | Dữ liệu nhóm mồ côi | Referential integrity phụ thuộc server/cấu hình |
| “Search rỗng nghĩa là không có entry” | Che lỗi ACL/replication/query | Cần xét quyền, base, scope, filter và server |
| “Có thể nối chuỗi filter từ HTTP input” | LDAP injection | Dùng filter builder/binding và escape giá trị |
| “Cache nhóm không ảnh hưởng bảo mật” | Quyền đã thu hồi vẫn còn | Có TTL/invalidation và chính sách fail closed |

## 15. Câu hỏi tự kiểm tra

1. Ba tình huống **tra cứu danh bạ**, **quản lý tài khoản** và **tra cứu nhóm** khác nhau về thao tác LDAP và quyền bind như thế nào?
2. Vì sao `uid=alice` không nhất thiết đủ xác định một entry? Khi nào phải dùng DN đầy đủ?
3. Nếu `ContextSource.base=dc=example,dc=org`, vì sao `LdapTemplate.lookup("uid=alice,ou=people")` có thể đúng?
4. Tại sao khi input chưa tin cậy, `.where("uid").is(input)` an toàn hơn nối chuỗi filter?
5. Khi nào nên dùng repository, khi nào cần `LdapTemplate`?
6. Vì sao tạo một `inetOrgPerson` cần lưu ý `cn`, `sn`, `objectClass` và parent OU?
7. Vì sao Add entry chưa đủ để kết luận tài khoản mới có thể đăng nhập?
8. Rename người dùng từ `ou=people` sang `ou=contractors` ảnh hưởng thế nào tới DN trong `uniqueMember`?
9. Vì sao `memberOf` không phải lời giải tra cứu nhóm áp dụng được cho mọi server LDAP?
10. Nhóm `groupOfNames` khác `groupOfUniqueNames` ở thuộc tính danh sách thành viên thường dùng như thế nào?
11. Khi kiểm tra quyền, vì sao cần tách authentication, membership và authorization?
12. Vì sao `saveAll` hoặc thao tác sửa user rồi sửa group không có bảo đảm transaction nhiều entry mặc định?
13. Khi danh bạ có 100.000 entry, cần thay đổi chiến lược Search và API trả kết quả ra sao?
14. Trong một API phân quyền, nếu LDAP timeout thì vì sao không nên coi người dùng đương nhiên được phép?
15. Hãy mô tả một integration test chứng minh Alice thuộc nhóm `reviewers`, rồi bị thu hồi membership và không còn đủ điều kiện duyệt.

## 16. Tổng kết

**LDAP có thể đồng thời phục vụ tra cứu danh bạ, quản lý tài khoản và tra cứu nhóm**, nhưng cách triển khai mỗi nhu cầu không giống nhau. Spring Data LDAP giúp ứng dụng Java thao tác với entry qua `LdapRepository` và ODM, còn `LdapTemplate` phù hợp khi cần Search, Modify, rename hay đọc thuộc tính nhóm cụ thể.

Để thiết kế đúng, cần luôn giữ mối liên hệ giữa **DN – schema/objectClass – filter – bind identity/ACL – nghiệp vụ**. Với danh bạ, trọng tâm là tìm kiếm chính xác, bảo vệ dữ liệu và kiểm soát tài nguyên. Với tài khoản, trọng tâm là quyền ghi, trạng thái theo directory và tính nhất quán giữa nhiều bước. Với nhóm, trọng tâm là mô hình `member`/`uniqueMember`, xử lý nhóm lồng nhau và quy đổi membership sang quyền truy cập của ứng dụng.

Cuối cùng, một test LDAP thành công chỉ khẳng định hành vi đã thử trên **server/schema/ACL tương ứng**. Khi tích hợp Active Directory, OpenLDAP hay directory khác, cần xác minh các khác biệt về thuộc tính, account policy và nhóm thay vì giả định tất cả đều triển khai giống nhau.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519).
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/).
- [Spring LDAP Reference — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
