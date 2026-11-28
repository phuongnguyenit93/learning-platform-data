# Bản đồ các thành phần: ContextSource, LdapTemplate, ODM và Repository

Khi bắt đầu với **Spring Data LDAP**, một lập trình viên Java thường gặp bốn cái tên xuất hiện gần nhau: `ContextSource`, `LdapTemplate`, **ODM (Object-Directory Mapping)** và `LdapRepository`. Chúng không phải bốn cách kết nối LDAP độc lập. Đây là những **thành phần có trách nhiệm khác nhau**, có thể phối hợp trên cùng một kết nối để ứng dụng tìm kiếm, đọc, ánh xạ và cập nhật entry trong dịch vụ thư mục.

Ví dụ, hệ thống nội bộ cần tìm một nhân viên theo `uid`, hiển thị họ tên và email, đồng thời có một chức năng quản trị sửa số điện thoại. Câu hỏi thiết kế không chỉ là “dùng thư viện gì?” mà là: **ai tạo LDAP context, ai thực hiện search, ai chuyển attribute sang Java object và ai cung cấp các phương thức truy cập dữ liệu cho service?**

Bài **Tổng quan** này vẽ bản đồ những thành phần đó trong module **SPRING_DATA_LDAP**. Bối cảnh module bao gồm repository, ánh xạ entry phân cấp, DN, `objectClass`, schema, truy vấn `LdapTemplate`, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory. Mục tiêu là giúp bạn chọn API đúng vai trò, không nhầm Spring Data LDAP với hệ thống xác thực và cũng không áp dụng máy móc tư duy JPA lên directory.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của `ContextSource`/`LdapContextSource`, `LdapTemplate`, LDAP ODM và `LdapRepository`.
2. Đọc sơ đồ luồng từ controller/service đến LDAP server, kể cả vị trí của JNDI, DN, schema và tài khoản bind.
3. Cấu hình Spring Boot để dùng chung kết nối LDAP cho template và repository.
4. Viết entity `@Entry`, repository và ví dụ truy vấn trực tiếp qua `LdapTemplate`.
5. Phân biệt ánh xạ `AttributesMapper`/`ContextMapper` thủ công với ODM tự ánh xạ entity.
6. Chọn repository, template hoặc kết hợp cả hai theo nhu cầu search, CRUD, filter và phép chiếu dữ liệu.
7. Xác định các điểm cần kiểm soát: base DN, schema/`objectClass`, ACL, TLS, query injection và kiểm thử tích hợp.

## 2. Bản đồ tổng thể

~~~mermaid
flowchart TD
    Client["HTTP client / batch job"] --> Service["Service nghiệp vụ<br/>validation + authorization"]
    Service --> Repo["Spring Data LDAP<br/>LdapRepository"]
    Service --> Template["Spring LDAP<br/>LdapTemplate"]
    Repo --> ODM["LDAP ODM<br/>@Entry, @Id, @Attribute"]
    ODM --> Operations["Spring LDAP operations<br/>mapping + query execution"]
    Operations --> Source["ContextSource<br/>LdapContextSource"]
    Template --> Source
    Source --> JNDI["JNDI / LDAP context"]
    JNDI --> Server["LDAP directory server<br/>DN + attributes + schema + ACL"]
~~~

Sơ đồ mô tả **quan hệ trách nhiệm**, không phải hợp đồng rằng repository luôn thực hiện đúng một chuỗi lời gọi theo thứ tự thể hiện. Trong triển khai, Spring Data LDAP tận dụng các thành phần của Spring LDAP để xây query, ánh xạ ODM và làm việc với directory. `LdapTemplate` là API thao tác LDAP thuận tiện, còn `ContextSource` cung cấp context kết nối cho những thao tác đó.

Một cách dễ nhớ:

| Thành phần | Câu hỏi nó giải quyết | Ví dụ API |
| --- | --- | --- |
| **`ContextSource`** | “Lấy context kết nối đến directory bằng cách nào?” | `LdapContextSource`, URL, base DN, bind DN/credential, môi trường JNDI. |
| **`LdapTemplate`** | “Gửi search, lookup hoặc sửa entry nào?” | `search`, `lookup`, `bind`, `modifyAttributes`, `unbind`. |
| **LDAP ODM** | “Entry LDAP được ánh xạ thành object Java nào?” | `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` khi cần. |
| **`LdapRepository`** | “Service cần các thao tác dữ liệu theo interface nào?” | `findById`, `findAll`, `save`, `delete`, `findByUid`. |

**Lưu ý tên gọi:** `ContextSource` và `LdapTemplate` thuộc **Spring LDAP**; repository và tích hợp Spring Data cho LDAP thuộc **Spring Data LDAP**; annotation ODM dùng từ package `org.springframework.ldap.odm.annotations`. Sử dụng Spring Data LDAP không làm `LdapTemplate` trở nên thừa.

## 3. Tầng directory: dữ liệu nền mà mọi thành phần cùng truy cập

Trước khi đi vào Java, cần biết ứng dụng sẽ đọc gì. LDAP directory lưu entry trong **Directory Information Tree (DIT)**. Mỗi entry có **Distinguished Name (DN)** và các attribute được ràng buộc bởi schema.

Ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Entry người dùng được minh họa bằng LDIF:

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
telephoneNumber: +84-28-1234-5678
~~~

Các thông tin cần phân biệt:

- **DN đầy đủ:** `uid=lan,ou=people,dc=example,dc=org` là tên của entry trong cây.
- **RDN:** `uid=lan` là thành phần tên tương đối với entry cha `ou=people,...`.
- **Attribute:** `uid`, `cn`, `sn`, `mail` và `telephoneNumber` là dữ liệu của entry.
- **`objectClass`:** xác định các lớp schema entry tuân theo; ví dụ `inetOrgPerson` kế thừa những yêu cầu từ các lớp khác.
- **Schema:** quy định các attribute được phép/bắt buộc, cú pháp giá trị và matching rules.
- **ACL:** máy chủ quyết định danh tính đang bind có quyền tìm, đọc, thêm, sửa, xóa entry/attribute hay không.

Không phải mọi LDAP server đều dùng `inetOrgPerson` và `uid`. Active Directory có schema, group/member và thuộc tính đăng nhập đặc thù; ứng dụng cần điều chỉnh cấu hình và mapping theo server thật.

### Ba loại “base” thường bị nhầm

| Khái niệm | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Context base** | `dc=example,dc=org` | Gốc được cấu hình cho `LdapContextSource`/Spring Boot. |
| **Entity base** | `ou=people` | Vị trí tương đối của lớp `@Entry` bên dưới context base. |
| **Search base** | `ou=people` | Nhánh mà một `LdapTemplate.search(...)` cụ thể tìm kiếm. |

Nếu đã đặt `spring.ldap.base=dc=example,dc=org`, truyền `ou=people` vào entity/search là đủ cho nhánh `ou=people,dc=example,dc=org`. Không lặp toàn bộ context base vào các DN tương đối rồi vô tình tạo đường dẫn sai.

## 4. `ContextSource`: nơi bắt đầu kết nối

`org.springframework.ldap.core.ContextSource` là **hợp đồng lấy LDAP context**. Một implementation thông dụng là `org.springframework.ldap.core.support.LdapContextSource`.

Nó liên quan đến:

1. **URL:** máy chủ và giao thức, ví dụ `ldaps://ldap.example.org:636`.
2. **Base DN:** gốc được dùng để xử lý DN tương đối.
3. **Bind identity:** DN/credential của tài khoản ứng dụng được dùng cho những thao tác thông thường.
4. **Môi trường kết nối:** thuộc tính JNDI, timeout và các thiết lập thích hợp khác.

`ContextSource` **không phải repository** và **không thực hiện truy vấn nghiệp vụ thay service**. Nó tạo/cung cấp context để các lớp phía trên giao tiếp với LDAP server thông qua JNDI.

### 4.1. Cấu hình với Spring Boot

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
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

Một tài khoản đọc được cấp quyền tối thiểu có thể có DN `cn=app-reader,ou=services,dc=example,dc=org`. Cấu hình ở trên dùng biến môi trường hoặc secret manager; không ghi mật khẩu thật vào Git.

Với starter và auto-configuration phù hợp, Spring Boot có thể cung cấp `LdapContextSource` và `LdapTemplate` để inject vào service. Nếu ứng dụng tự định nghĩa các bean cùng loại hoặc nhiều directory, cần kiểm tra các điều kiện auto-configuration và dùng `@Qualifier`/wiring rõ ràng thay vì cho rằng mọi bean tự động cùng trỏ đến đúng nguồn.

### 4.2. Điều `ContextSource` không tự bảo đảm

- **TLS:** chỉ URL `ldap://` không tự bật mã hóa. `ldaps://` sử dụng TLS ngay từ đầu; StartTLS cần được cấu hình riêng. Xác minh CA/hostname và kho tin cậy của JVM.
- **Kết nối khả dụng:** server có thể ngừng hoạt động, timeout hoặc trả lỗi bind. `ContextSource` không biến mọi lỗi thành kết quả rỗng.
- **Failover:** cấu hình nhiều URL không bảo đảm một thao tác đang chạy tự chuyển máy chủ hay retry an toàn.
- **Quyền truy cập:** bind thành công không đồng nghĩa tài khoản được đọc hoặc sửa mọi attribute.
- **Transaction xuyên nhiều entry:** LDAP không tự có một transaction kiểu cơ sở dữ liệu quan hệ chỉ vì đã có `ContextSource`.

Ứng dụng cần tách việc xử lý lỗi kết nối, quyền truy cập và logic nghiệp vụ; không đẩy các trách nhiệm đó sang một bean kết nối.

## 5. `LdapTemplate`: thực hiện thao tác LDAP mà không phải viết JNDI lặp lại

`LdapTemplate` triển khai `LdapOperations`, cung cấp API mức cao hơn để làm việc với LDAP. Thay vì tự tạo `DirContext`, quản lý tài nguyên và duyệt `SearchResult` bằng JNDI trong mọi service, bạn sử dụng template và một mapper.

### 5.1. Các nhóm thao tác

| Nhóm | Ví dụ phương thức | Mục đích |
| --- | --- | --- |
| **Search** | `search(query, mapper)` | Tìm entry theo base, filter, scope và ánh xạ từng kết quả. |
| **Lookup** | `lookup(dn, mapper)` | Đọc một entry khi đã biết DN. |
| **Create** | `bind(dn, object, mapper)` hoặc overload thích hợp | Thêm entry mới theo schema/ACL. |
| **Update** | `modifyAttributes(dn, modifications)` | Thêm, thay thế hoặc xóa attribute trên entry đã tồn tại. |
| **Delete** | `unbind(dn)` | Xóa entry theo DN nếu server cho phép. |
| **Rename** | `rename(oldDn, newDn)` | Đổi RDN hoặc tên entry theo khả năng directory. |

Tên phương thức và overload cụ thể phụ thuộc phiên bản Spring LDAP; bảng trình bày **nhóm thao tác**, không phải mọi chữ ký API. Quan trọng hơn, template **không bỏ qua ACL/schema** và không tự kiểm tra authorization HTTP.

### 5.2. Truy vấn trực tiếp qua `LdapTemplate.search`

Ví dụ chỉ cần trả DTO tên hiển thị và email, không cần entity đầy đủ:

~~~java
public record PersonSummary(String uid, String displayName, String email) {}
~~~

~~~java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonLookupService {
    private final LdapTemplate ldapTemplate;

    public PersonLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 128) {
            throw new IllegalArgumentException("uid khong hop le");
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("uid", "cn", "mail")
                .countLimit(20)
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(query,
                (AttributesMapper<PersonSummary>) attrs ->
                        new PersonSummary(
                                optionalString(attrs, "uid"),
                                optionalString(attrs, "cn"),
                                optionalString(attrs, "mail")));
    }

    private static String optionalString(Attributes attrs, String name)
            throws NamingException {
        Attribute attribute = attrs.get(name);
        return attribute == null ? null : (String) attribute.get();
    }
}
~~~

Đọc luồng:

1. Service xác thực định dạng `uid` ở tầng ứng dụng.
2. `LdapQueryBuilder` tạo filter `(&(objectClass=inetOrgPerson)(uid=<giá trị>))`, có escaping cho giá trị `uid`. Không nối filter bằng chuỗi từ input không tin cậy.
3. `base("ou=people")` giới hạn nhánh tìm bên dưới context base.
4. `attributes(...)` chỉ yêu cầu những thuộc tính DTO cần; `countLimit(...)` tránh trả quá nhiều entry.
5. `LdapTemplate` lấy LDAP context từ `ContextSource`, thực hiện tìm kiếm và gọi `AttributesMapper` cho từng entry.
6. Service nhận danh sách `PersonSummary`, không phải một đối tượng “đã xác thực”.

`OptionalString` minh họa việc giữ `null` khi attribute không được trả về. Trong code thực tế, đặt quy tắc rõ cho trường bắt buộc và tùy chọn; thiếu trường có thể do schema, ACL hoặc projection chứ không chỉ vì entry không lưu giá trị.

### 5.3. Khi cần cả DN: `ContextMapper`

`AttributesMapper` chỉ nhận tập attribute. Nếu cần biết DN của entry, có thể dùng `ContextMapper` với `DirContextOperations`:

~~~java
import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.query.LdapQueryBuilder;

List<String> identities = ldapTemplate.search(
        LdapQueryBuilder.query()
                .base("ou=people")
                .where("uid").is("lan"),
        (ContextMapper<String>) source -> {
            DirContextOperations entry = (DirContextOperations) source;
            return entry.getDn() + " | "
                    + entry.getStringAttribute("cn");
        });
~~~

Đoạn này minh họa phần thân phương thức đã có `ldapTemplate`. `entry.getDn()` thường là DN tương đối với context base; không mặc định nó đã là DN đầy đủ `dc=example,dc=org`. Với mapper nhiều bước, có thể dùng `AbstractContextMapper<T>` và override `doMapFromContext(DirContextOperations)` để tránh ép kiểu lặp lại.

**Tóm lại:** `LdapTemplate` trả Java object qua mapper tùy ý, nhưng mapper thủ công **không phải LDAP ODM**. ODM là cách ánh xạ entity bằng metadata/annotation ở phần kế tiếp.

## 6. LDAP ODM: biến một entry thành entity Java

**Object-Directory Mapping (ODM)** là cơ chế ánh xạ giữa entry LDAP và đối tượng Java dựa trên annotation. Nó tương tự ORM ở ý tưởng ánh xạ dữ liệu sang class nhưng **không biến LDAP thành cơ sở dữ liệu quan hệ**.

### 6.1. Các annotation cốt lõi

| Annotation | Trách nhiệm |
| --- | --- |
| `@Entry` | Đánh dấu một class được ánh xạ từ entry, khai báo base tương đối và `objectClasses`. |
| `@Id` | Đánh dấu field DN của entity, thường là `javax.naming.Name`. |
| `@Attribute` | Ánh xạ một field Java tới attribute LDAP, ví dụ `mail`. |
| `@DnAttribute` | Giúp ánh xạ giá trị trong thành phần DN/RDN với field khi mô hình cần. |
| `@Transient` | Đánh dấu field không tham gia ánh xạ directory khi thích hợp. |

Trong Spring LDAP, các annotation thường nằm tại `org.springframework.ldap.odm.annotations`. **`@Id` ở đây không phải `jakarta.persistence.Id` của JPA**; entity LDAP được nhận diện theo DN.

### 6.2. Viết entity `PersonEntry`

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=people",
        objectClasses = {
            "top", "person", "organizationalPerson", "inetOrgPerson"
        })
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

    public PersonEntry() {
        // Constructor không tham số để framework ánh xạ.
    }

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Ở ví dụ này:

- `@Entry(base = "ou=people")` cho framework biết loại entry và vùng ánh xạ.
- `@Id Name dn` thể hiện vị trí định danh entry trong directory, không phải ID tăng tự động.
- `@Attribute(name = "cn")` giải thích tại sao Java field `commonName` lấy dữ liệu từ LDAP attribute `cn`.
- `objectClasses` cần phù hợp schema server. Một entry `inetOrgPerson` có thể phải thỏa các yêu cầu của `person`, bao gồm những attribute bắt buộc như `cn` và `sn`.

**Đọc được entity không có nghĩa có thể ghi entity bất kỳ.** Khi tạo/sửa entry, phải bảo đảm DN đúng, thuộc tính bắt buộc theo schema, quyền của bind account và chính sách nghiệp vụ. Không lưu mật khẩu hoặc operational attributes chỉ để ODM “đủ field”.

### 6.3. Vì sao ODM không phải JPA?

| Khía cạnh | LDAP ODM | JPA/ORM |
| --- | --- | --- |
| Mô hình nguồn | Directory tree: DN, RDN, entry, attribute, `objectClass`. | Bảng quan hệ, khóa chính/ngoại. |
| Định danh | DN mang cấu trúc phân cấp; có thể thay khi rename/move. | Primary key do database quản lý, thường độc lập vị trí. |
| Truy vấn | LDAP search filter + base + scope. | JPQL/SQL, join, aggregate. |
| Ánh xạ | `@Entry`, `@Attribute`, `@Id`. | `@Entity`, `@Column`, `@Id`. |
| Giao dịch | Phụ thuộc thao tác/server LDAP; không mặc định transaction đa entry kiểu RDBMS. | Transaction database theo công nghệ sử dụng. |
| Quyền | LDAP ACL trên entry/attribute và bind identity. | Quyền database, RLS nếu có, cộng chính sách ứng dụng. |

Không thiết kế quan hệ entity LDAP như các bảng có `@OneToMany` rồi mong Spring Data LDAP tự tạo phép join. Quan hệ nhóm–thành viên có thể lưu dưới dạng DN trong attribute và cần truy vấn/phân giải rõ ràng.

## 7. `LdapRepository`: interface dữ liệu trên nền ODM

Spring Data LDAP cho phép định nghĩa interface repository để giảm mã truy cập entry lặp lại:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    Optional<PersonEntry> findByUid(String uid);
}
~~~

Với cấu hình repository scanning thích hợp, Spring Data LDAP cung cấp implementation cho interface này. Service gọi repository chứ không phải tự mở LDAP context:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {
    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public Optional<PersonSummary> findPerson(String uid) {
        return repository.findByUid(uid)
                .map(person -> new PersonSummary(
                        person.getUid(),
                        person.getCommonName(),
                        person.getEmail()));
    }
}
~~~

Lợi ích:

1. Service nhận interface theo mô hình dữ liệu, dễ tập trung logic nghiệp vụ.
2. Phương thức `findByUid` diễn đạt truy vấn theo thuộc tính `uid` của entity.
3. Framework sử dụng metadata ODM để ánh xạ entry LDAP thành `PersonEntry`.
4. Repository có các thao tác cơ bản như tìm theo ID, liệt kê, lưu và xóa tùy API; không phải viết lại các thao tác phổ biến trong mỗi service.

**Giới hạn:** repository không tự quyết định role người dùng HTTP, không mở rộng ACL LDAP và không đảm bảo `uid` là duy nhất trong mọi directory. Nếu `findByUid` được thiết kế trả `Optional<PersonEntry>`, dữ liệu phải đáp ứng kỳ vọng một kết quả; nhiều entry có cùng `uid` trong phạm vi truy vấn là vấn đề mô hình/search base cần xử lý.

### Repository có thay thế `LdapTemplate` không?

Không. Cả hai có thể dùng trong cùng ứng dụng:

- **Repository:** thuận tiện cho entity đã biết và phương thức CRUD/search phổ biến.
- **Template:** hữu ích với query linh hoạt, search base/scope đặc thù, chỉ chọn vài attribute, trả DTO trực tiếp, thao tác `modifyAttributes` chính xác trên một entry.

Chọn theo nhu cầu từng chức năng, không ép mọi truy vấn vào repository và cũng không bỏ repository chỉ vì một số trường hợp cần template.

## 8. Một yêu cầu đi qua các thành phần như thế nào?

Tình huống: API `GET /api/directory/people/lan` cần trả tên và email của Lan.

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP Client
    participant Service as PersonDirectoryService
    participant Repo as PersonRepository
    participant ODM as LDAP ODM
    participant Ops as Spring LDAP operations
    participant CS as LdapContextSource
    participant LDAP as Directory Server
    HTTP->>Service: findPerson("lan")
    Service->>Repo: findByUid("lan")
    Repo->>ODM: Xác định entity + thuộc tính uid
    ODM->>Ops: Xây/thực thi truy vấn LDAP
    Ops->>CS: Lấy LDAP context
    CS->>LDAP: Bind/kết nối khi cần
    Ops->>LDAP: Search dưới base thích hợp
    LDAP-->>Ops: DN + Attributes
    Ops-->>ODM: Entry/kết quả
    ODM-->>Repo: PersonEntry
    Repo-->>Service: Optional<PersonEntry>
    Service-->>HTTP: PersonSummary
~~~

Sơ đồ là **luồng trách nhiệm minh họa**, không khẳng định một lớp nội bộ có tên “Ops” là public API riêng hoặc mỗi request đều mở kết nối mới. Context có thể được tạo/tái sử dụng tùy cấu hình; chi tiết triển khai Spring Data LDAP thay đổi theo phiên bản.

Điều phải bảo đảm ở **service/API**: người gọi được phép xem hồ sơ nào. Một repository tìm được entry bằng tài khoản dịch vụ chỉ chứng minh account đó có khả năng truy vấn dưới ACL của directory.

### Cùng chức năng nhưng dùng template

Nếu `PersonLookupService.findByUid(...)` ở mục 5 trả DTO qua `LdapTemplate`, luồng rút gọn:

~~~text
HTTP → Service (authz, validation)
     → LdapTemplate.search(query, mapper)
     → ContextSource → JNDI → LDAP server
     → AttributesMapper → PersonSummary
~~~

Trường hợp này **không cần đi qua entity ODM hoặc repository**. Đây là lựa chọn có chủ đích cho phép chiếu dữ liệu đơn giản, không phải “repository hoạt động sai”.

## 9. Bản đồ thao tác CRUD và chọn tầng phù hợp

| Nhu cầu nghiệp vụ | Gợi ý API | Tại sao? |
| --- | --- | --- |
| Tìm nhân viên bằng `uid`, kết quả là `PersonEntry`. | `PersonRepository.findByUid(uid)`. | Query theo attribute entity và ODM. |
| Lấy danh sách tên/email, không cần entity đầy đủ. | `LdapTemplate.search(query, AttributesMapper)`. | Chỉ đọc những attribute DTO cần. |
| Đọc entry khi đã biết DN. | `LdapTemplate.lookup(dn, mapper)` hoặc repository find-by-ID phù hợp. | Tránh search theo username nếu DN đã tin cậy. |
| Tạo entry có schema và DN hợp lệ. | Repository `save` cho entity phù hợp hoặc `LdapTemplate.bind`. | Cần objectClass, attribute bắt buộc và quyền tạo. |
| Thay **một** attribute trên entry. | `LdapTemplate.modifyAttributes(dn, changes)`. | Mô tả chính xác ADD/REPLACE/REMOVE, không tải/ghi cả entity. |
| Đổi RDN, di chuyển entry. | API rename/Modify DN tương ứng. | DN là tên cấu trúc, không chỉ là một field string. |
| Xóa entry được cấp quyền. | Repository `delete` hoặc `LdapTemplate.unbind`. | Phải xử lý ACL, entry con và quy trình nghiệp vụ. |
| Truy vấn có filter AND/OR/NOT, scope đặc thù. | `LdapQueryBuilder` + `LdapTemplate`. | Kiểm soát rõ base, filter, scope và projection. |

### Ví dụ cập nhật một thuộc tính với template

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

public void updateDescription(
        LdapTemplate ldapTemplate,
        String uid,
        String newDescription) {

    // Chỉ hợp lệ nếu directory thật có RDN uid ở nhánh people.
    Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

    ModificationItem change = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("description", newDescription));

    ldapTemplate.modifyAttributes(dn, new ModificationItem[] {change});
}
~~~

Code minh họa phần thân service có quyền ghi, trong đó `ldapTemplate` đã sẵn sàng. Ứng dụng thật phải validate input, kiểm tra authorization và không suy DN từ `uid` nếu RDN của user có thể là `cn`. Khi chỉ có tên đăng nhập, hãy search DN thực trước hoặc dùng khóa định danh do hệ thống quản lý.

**Phân biệt `REPLACE_ATTRIBUTE` với `ADD_ATTRIBUTE`:** replace một attribute nhiều giá trị có thể thay **toàn bộ tập giá trị**, không chỉ một phần tử. LDAP server luôn là nơi kiểm tra schema và ACL.

## 10. Đặt bảo mật ở đâu trên bản đồ?

Một ứng dụng an toàn có ít nhất **hai ranh giới quyền**:

~~~text
HTTP request
    |
    v
Spring Security / service authorization:
   người gọi có quyền xem hoặc sửa hồ sơ này không?
    |
    v
Repository hoặc LdapTemplate:
   xây DN, base, filter, projection đúng
    |
    v
ContextSource → LDAP server:
   bind account có ACL đọc/ghi entry/attribute đó không?
~~~

### 10.1. Tài khoản kết nối không phải người dùng HTTP

Trong ví dụ Spring Boot ở mục 4, `spring.ldap.username`/`password` thường là credential của **tài khoản dịch vụ**. Nếu một HTTP user đăng nhập là Lan, `PersonRepository.findByUid("minh")` không tự chuyển LDAP connection thành DN của Lan. Quyền API phải được kiểm tra riêng.

Spring Security LDAP có thể được dùng để **tìm user DN rồi bind để xác thực mật khẩu** và tra nhóm/authority. Đây là phần của luồng authentication/authorization, không phải chức năng mặc định của repository/ODM. Một số ứng dụng dùng OIDC hoặc SAML cho đăng nhập trong khi vẫn dùng Spring Data LDAP chỉ để đọc danh bạ.

### 10.2. Nguyên tắc ít quyền nhất

- Cấu hình **LDAPS** hoặc **StartTLS** đúng với CA/hostname đáng tin cậy; không tắt kiểm tra chứng chỉ để “chạy được”.
- Lưu bind credential qua secret manager/biến môi trường; không log mật khẩu.
- Dùng tài khoản **chỉ đọc** nếu chức năng chỉ search; tách tài khoản ghi cho workflow quản trị khi cần.
- Giới hạn ACL theo OU và attribute cần thiết; một service account có quyền rộng có thể làm rò rỉ dữ liệu qua API nếu service thiếu authorization.
- Chỉ yêu cầu trường cần cho DTO; không trả nguyên `Attributes` cho client.
- Kiểm soát tên attribute, base DN, search scope bằng allowlist/policy server; filter builder chỉ giải quyết escaping **giá trị**, không tự cấp quyền truy vấn.
- Dùng `LdapNameBuilder` cho RDN động; escaping DN khác escaping filter.
- Áp dụng time limit/count limit, phân trang và rate limit phù hợp khi kết quả có thể lớn.

### 10.3. Schema và lifecycle là một phần của bảo mật dữ liệu

Không dùng `save`/`modifyAttributes` để cập nhật tùy ý những operational attributes do server quản lý như `entryUUID`/`objectGUID` hoặc thuộc tính bảo mật chưa được cho phép. Một entry LDAP có thể được rename/move; DN thay đổi nhưng thực thể nghiệp vụ có thể vẫn là cùng người. Nếu đồng bộ sang database riêng, đừng xem email/uid/DN là khóa nội bộ bất biến mà không có bảo đảm quản trị rõ ràng.

## 11. Kiểm thử theo từng tầng

Khi truy vấn trả rỗng hoặc lỗi, đừng đổ ngay cho repository. Hãy xác minh từ dưới lên:

1. **Directory server:** base DN/entry có tồn tại? Schema và các attribute có đúng như giả định?
2. **Kết nối:** URL, TLS/truststore, bind DN/credential có đúng?
3. **ACL:** account có quyền search/đọc các attribute được yêu cầu?
4. **Query:** base, scope, filter và projection có bao phủ entry cần tìm?
5. **Mapping:** `@Entry`/`@Attribute` hoặc mapper có đúng tên field và giá trị nhiều phần tử?
6. **Service/API:** validation, authentication và authorization có làm kết quả bị từ chối đúng mục đích?

### 11.1. Đọc cùng entry bằng `ldapsearch`

Ví dụ dùng OpenLDAP client trên directory thử nghiệm:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=lan))" dn uid cn sn mail
~~~

`-W` yêu cầu nhập mật khẩu tương tác. Đối chiếu kết quả với `PersonRepository.findByUid("lan")` và `LdapTemplate.search(...)`:

- Nếu `ldapsearch` không tìm thấy entry, hãy kiểm tra dữ liệu/schema, base/filter và quyền LDAP trước.
- Nếu `ldapsearch` thành công nhưng ODM bỏ trống `email`, kiểm tra `@Attribute(name = "mail")`, schema và projection.
- Nếu mapper template nhận `null`, kiểm tra thuộc tính có được yêu cầu/trả về và tài khoản bind có quyền đọc không.
- Nếu Java gặp `SSLHandshakeException` nhưng `ldapsearch` chạy được, nhớ rằng JVM và công cụ LDAP có thể dùng truststore khác nhau.
- Nếu HTTP trả `403` dù repository thấy entry, kiểm tra authorization; đó có thể là hành vi bảo mật đúng.

Không thực hiện CRUD trên directory tổ chức nếu không có quyền và kế hoạch kiểm thử, sao lưu/khôi phục phù hợp.

### 11.2. Ma trận kiểm thử kiến trúc

| Test | Tầng cần xác minh | Kỳ vọng |
| --- | --- | --- |
| Sai URL/port LDAP. | `ContextSource`, kết nối. | Lỗi kết nối có thể nhận biết; không chuyển thành “không có user”. |
| Bind DN/secret sai. | Context/bind. | Lỗi xác thực kỹ thuật; không tự thử anonymous bind. |
| `@Entry(base)` sai. | ODM/repository. | Không tìm được entry đúng nhánh hoặc lỗi DN; sửa mapping. |
| `@Attribute(name = "cn")` bị gõ sai. | ODM. | Field không được ánh xạ đúng; phát hiện bằng test dữ liệu. |
| `uid` có ký tự đặc biệt trong filter. | Query builder. | Giá trị được escape; không chèn thêm toán tử LDAP. |
| Search base quá rộng. | Service/query/ACL. | Không để client tự mở rộng; giới hạn theo use case. |
| `mail` vắng hoặc bị ACL ẩn. | Mapping/DTO. | Quy tắc trường optional/bắt buộc được áp dụng có chủ ý. |
| Account chỉ đọc gọi `modifyAttributes`. | LDAP ACL. | Server từ chối thao tác ghi. |
| User HTTP không đủ quyền xem dữ liệu. | Spring Security/service. | Không trả thông tin dù bind account LDAP có thể đọc. |
| Server LDAP mất kết nối giữa search. | Kết nối/lỗi ứng dụng. | Báo lỗi đúng loại, retry có giới hạn nếu thích hợp. |

### 11.3. Unit test và integration test

- **Unit test service:** mock repository/template để kiểm tra validation, DTO mapping và ranh giới quyền ở service.
- **Unit test mapper:** dùng dữ liệu attribute/context giả lập để kiểm tra field thiếu, thuộc tính đa trị và DN.
- **Integration test LDAP:** dùng directory thử nghiệm có schema/ACL/entry phù hợp để xác nhận repository và template thực sự truy vấn giống mong đợi.
- **Integration test bảo mật:** chạy authentication/authorization với các vai trò khác nhau; thử account LDAP chỉ đọc và account được phép ghi.

Một test chỉ mock repository không thể chứng minh TLS, bind DN, schema hoặc LDAP search filter hoạt động đúng với server thật.

## 12. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`ContextSource` chính là client query LDAP.” | Nó cung cấp LDAP context; query thường được triển khai qua `LdapTemplate`/repository. |
| “Có repository thì không bao giờ dùng `LdapTemplate`.” | Template hữu ích cho search linh hoạt, DTO projection, modify và các thao tác đặc thù. |
| “ODM là JPA và DN tương đương ID tự tăng.” | LDAP ODM ánh xạ entry theo DN, schema và attribute; DN có cấu trúc phân cấp. |
| “`@Entry` tự tạo schema LDAP.” | Schema được directory server quản lý; annotation phải tương thích schema có thật. |
| “Một `findByUid` thành công nghĩa là caller đã đăng nhập.” | Tìm entry không phải xác thực; cần Spring Security hoặc cơ chế authentication phù hợp. |
| “Repository có `save` thì tài khoản read-only cũng ghi được.” | LDAP ACL quyết định quyền thực tế; không có quyền thì server từ chối. |
| “Base DN chỉ để trình bày.” | Base DN quyết định không gian tìm kiếm và cách diễn giải DN tương đối. |
| “Escape filter bảo vệ cả DN và thuộc tính tìm kiếm.” | Escaping filter, DN escaping và allowlist attribute/base/scope là các vấn đề riêng. |
| “Một request LDAP thất bại thì chưa có thay đổi nào.” | Nếu lỗi xảy ra sau khi gửi thao tác ghi, phản hồi có thể thất lạc; cần đối soát trước khi retry. |

## 13. Bài tập tổng hợp

Giả sử Spring Boot được cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.company.internal:636
    base: dc=company,dc=internal
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Directory có các entry:

~~~text
dc=company,dc=internal
├── ou=employees
│   └── uid=mai
└── ou=groups
    └── cn=hr-viewers
~~~

Entry `uid=mai` có `objectClass=inetOrgPerson`, `uid=mai`, `cn=Mai Le`, `sn=Le` và `mail=mai@company.internal`. Ứng dụng cần ba chức năng: (A) tìm Mai theo username để hiển thị thẻ thông tin, (B) lọc danh sách nhân viên theo nhiều điều kiện và chỉ lấy tên/email, (C) cập nhật `description` của Mai bằng tài khoản ghi có quyền.

**Yêu cầu:**

1. Chỉ ra **thành phần** chịu trách nhiệm URL, base DN, tài khoản bind và context kết nối.
2. Viết `@Entry(base = "ou=employees", objectClasses = {...})` cho entity Mai, ánh xạ tối thiểu `@Id Name dn`, `uid`, `cn`, `mail` và những trường schema bắt buộc cần cho mô hình.
3. Định nghĩa `LdapRepository<PersonEntry>` có phương thức `findByUid(String uid)`.
4. Chọn repository hay `LdapTemplate` cho chức năng A, B, C; giải thích quyết định.
5. Với `spring.ldap.base=dc=company,dc=internal`, search base tương đối của chức năng B là gì?
6. Nếu người dùng HTTP gửi `uid` chứa dấu ngoặc hoặc dấu sao, nên tạo filter thế nào?
7. Nếu repository tìm thấy Mai nhưng caller HTTP không có quyền đọc hồ sơ HR, tầng nào phải từ chối?
8. Nếu `ldapsearch` trả `mail` nhưng entity Java không có email, cần kiểm tra thành phần nào trước?
9. Vì sao không nên tự tạo entry mới chỉ để sửa một `description` và không nên retry lệnh ghi mù quáng nếu mạng bị ngắt?

**Gợi ý trả lời:**

- (1) `LdapContextSource`/`ContextSource`.
- (2) `@Entry`/`@Id`/`@Attribute` với tên attribute tương ứng schema `inetOrgPerson`; DN là `Name`.
- (3) `interface PersonRepository extends LdapRepository<PersonEntry> { Optional<PersonEntry> findByUid(String uid); }`.
- (4) A phù hợp repository/ODM; B phù hợp `LdapTemplate.search(query, mapper)` để chỉ lấy DTO; C phù hợp `modifyAttributes` với quyền ghi được kiểm soát.
- (5) `ou=employees`.
- (6) Dùng `LdapQueryBuilder.where("uid").is(uid)`, không nối chuỗi filter; tránh cho caller tự chọn tên attribute/base/scope.
- (7) Spring Security/service authorization, bên cạnh LDAP ACL.
- (8) Kiểm tra `@Attribute(name = "mail")`, projection, schema và ACL trên tài khoản context.
- (9) Tạo lại entry có thể phá DN/attribute/quan hệ; write timeout không chứng minh server chưa cập nhật.

## 14. Ghi nhớ

**`ContextSource` cung cấp context kết nối; `LdapTemplate` thực thi thao tác; LDAP ODM ánh xạ entry thành object; `LdapRepository` đưa các thao tác dữ liệu phổ biến lên interface Spring Data.** Các lớp này phối hợp nhưng không thay thế nhau.

Hãy bắt đầu từ **directory thật**: URL, base DN, DN/RDN, `objectClass`, schema và ACL. Dùng repository cho entity và CRUD thường gặp, template cho truy vấn linh hoạt hoặc thay đổi thuộc tính chính xác, và chọn mapper/ODM theo kiểu kết quả cần có. Cuối cùng, đặt validation/authorization ở service, dùng kết nối TLS và secret an toàn, kiểm soát filter/base/scope, rồi xác nhận bằng thử nghiệm với directory.

### Tài liệu tham khảo

- [Spring Data LDAP Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/)
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Boot Reference — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
