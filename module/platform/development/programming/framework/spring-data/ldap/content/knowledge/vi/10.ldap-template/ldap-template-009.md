# Lựa chọn Template hay Repository theo mức kiểm soát cần thiết

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java có thể thao tác với directory bằng hai cách phổ biến: **Spring Data LDAP repository** và **Spring LDAP LdapTemplate**. Cả hai đều giúp làm việc với entry, DN, objectClass và thuộc tính LDAP, nhưng chúng giải quyết những mức nhu cầu khác nhau.

**Repository** phù hợp khi nghiệp vụ xoay quanh một loại entry đã được ánh xạ thành Java object và các thao tác CRUD/truy vấn thông dụng. **LdapTemplate** phù hợp khi cần kiểm soát trực tiếp search base, scope, projection, filter, modification, rename hoặc các chi tiết của LDAP operation.

Bài thuộc chương **LdapTemplate**, tập trung vào cách lựa chọn theo mức kiểm soát cần thiết. Thay vì chỉ ghi nhớ định nghĩa, bạn sẽ xem cùng một use case tìm user bằng hai cách, sau đó mở rộng sang các tình huống cần Template.

Sau bài học, bạn có thể:

- Phân biệt vai trò của **LdapRepository** và **LdapTemplate**.
- Chọn repository cho CRUD và finder đơn giản dựa trên ODM entity.
- Chọn Template khi cần filter phức tạp, search scope, projection, thuộc tính nhiều giá trị hoặc operation đặc thù.
- Hiểu **@Entry, @Id Name, @Attribute** và mối quan hệ giữa DN với ContextSource base.
- Viết cùng một truy vấn theo repository và LdapQueryBuilder.
- Thực hiện lookup, search, modify, rename và delete bằng LdapTemplate.
- Kết hợp Repository và Template trong cùng application mà không nhân đôi business logic.
- Đánh giá bảo mật, hiệu năng, khả năng kiểm thử và giới hạn transaction trước khi chọn cách triển khai.

## 1. Quyết định nhanh: chọn công cụ theo use case

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| CRUD entry theo mô hình Java đã ổn định | **LdapRepository** | API CRUD rõ ràng, ít mã lặp |
| Tìm user theo một thuộc tính như uid hoặc sn | **Repository finder** | Derived query dễ đọc |
| Đọc một entry theo DN đã biết | Cả hai | Repository findById; Template lookup |
| Filter kết hợp nhiều điều kiện | **Repository hoặc LdapTemplate** | LdapRepository có thể nhận LdapQuery; Template phù hợp khi cần kiểm soát search/mapping sâu hơn |
| Chỉ lấy một số thuộc tính để tạo projection | **LdapTemplate** | Kiểm soát attributes được trả về |
| Đọc thuộc tính đa trị hoặc binary | Thường **LdapTemplate** | Làm việc trực tiếp với Attributes/DirContextOperations |
| Sửa một vài thuộc tính theo LDAP Modify | **LdapTemplate** | Chọn ADD/REMOVE/REPLACE rõ ràng |
| Rename hoặc move entry theo DN | **LdapTemplate** | Có operation rename(oldDn, newDn) |
| Dùng LDAP control, paging hoặc thao tác provider-specific | **LdapTemplate** hoặc API chuyên biệt | Cần quyền điều khiển LDAP operation |
| Mô hình hóa nhiều use case CRUD đơn giản | **Repository** | Tập trung vào entity và finder |
| Cần truy vấn linh hoạt nhưng vẫn giữ ODM | **Kết hợp cả hai** | Repository cho luồng phổ thông, Template cho luồng đặc biệt |

**Quy tắc thực dụng:** bắt đầu từ repository khi mô hình entry và truy vấn đơn giản đã diễn đạt đủ use case. Chuyển sang Template khi yêu cầu cần điều khiển rõ operation hoặc dữ liệu trả về. Không chọn Template chỉ vì nó có nhiều API hơn; mỗi đoạn code vẫn cần đúng base DN, filter, ACL và schema.

## 2. Hai lớp abstraction làm việc ở đâu?

~~~mermaid
flowchart TD
    APP["Application service"] --> REPO["Spring Data LDAP<br/>LdapRepository"]
    APP --> TEMPLATE["Spring LDAP<br/>LdapTemplate"]
    REPO --> ODM["ODM mapping<br/>@Entry / @Id / @Attribute"]
    TEMPLATE --> QUERY["LdapQueryBuilder / ContextMapper<br/>Attributes / ModificationItem"]
    ODM --> SOURCE["ContextSource"]
    QUERY --> SOURCE
    SOURCE --> SERVER["LDAP directory<br/>entries, DN, schema, ACL"]
~~~

**LdapRepository** cung cấp abstraction theo entity và repository contract. Entity được ánh xạ bằng Spring LDAP ODM, thường dùng @Entry, @Id và @Attribute. Các finder method giúp biểu đạt truy vấn phổ biến theo property.

**LdapTemplate** cung cấp abstraction thao tác LDAP ở mức thấp hơn. Bạn chọn search base, scope, attributes, filter, mapper và loại modification. Template cũng hỗ trợ các operation như lookup, bind, unbind, modifyAttributes và rename.

Cả hai đều cần cấu hình kết nối directory thông qua **ContextSource**. Chúng không thay thế schema, ACL, naming context hoặc chính sách bảo mật do LDAP server quản lý.

### 2.1. Repository không phải JPA repository

Tên gọi repository có thể khiến bạn liên tưởng đến JPA, nhưng LDAP là directory phân cấp:

- **DN** xác định vị trí entry trong cây; không phải khóa số tự tăng.
- **objectClass** và schema quyết định các attribute bắt buộc/được phép.
- Không có mô hình quan hệ và join như JPA.
- Built-in LdapRepository dùng một generic type cho entity và mặc định ID là javax.naming.Name; DN là ID theo mô hình ODM.
- Spring Data LDAP repository không hỗ trợ paging và sorting theo đặc thù giao thức LDAP.
- Không nên giả định có persistence context, dirty checking hoặc cascade như ORM quan hệ.
- Thay đổi Java object trong bộ nhớ không tự ghi về LDAP; phải gọi operation lưu tương ứng.
- Giao dịch nhiều entry không tự trở thành một transaction ACID chỉ vì code chạy trong @Transactional.

Repository giúp code gọn hơn, nhưng không biến LDAP thành relational database.

## 3. Cấu hình chung và mô hình entry

Ví dụ Spring Boot:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Ví dụ cấu hình ContextSource qua Spring Boot:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Giữ secret trong secret manager hoặc cơ chế cấp secret của môi trường. JVM phải xác minh certificate chain và hostname; không tắt TLS validation để vượt lỗi kết nối.

Kích hoạt quét repository bằng cấu hình Java nếu ứng dụng chưa bật sẵn:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(basePackages = "org.example.directory.persistence")
public class LdapRepositoryConfiguration {
}
~~~

Đồng thời bảo đảm ứng dụng có ContextSource/LdapTemplate bean tương ứng. Khi dùng Spring Boot auto-configuration, kiểm tra bean đã được tạo theo cấu hình; với nhiều directory hoặc nhiều Template, khai báo và gắn repository với đúng Template bằng thuộc tính ldapTemplateRef của @EnableLdapRepositories.

### 3.1. Ánh xạ một người dùng bằng ODM

Giả sử entry:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
~~~

Java entity:

~~~java
package org.example.directory.persistence;

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
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Ý nghĩa:

- **@Entry** khai báo base và objectClass dùng để ánh xạ loại entry.
- **@Id Name dn** giữ DN của entry.
- **@Attribute** ánh xạ property Java sang attribute LDAP tương ứng.

@Entry.base và ContextSource.base phải được phối hợp đúng. DN mà repository/ODM sử dụng phải theo quy ước tương đối/đầy đủ mà cấu hình mapping của ứng dụng yêu cầu; không tự nối suffix dc=example,dc=org hai lần.

## 4. Cách 1 — Repository cho CRUD và finder đơn giản

Khai báo repository:

~~~java
package org.example.directory.persistence;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    List<PersonEntry> findBySn(String surname);
}
~~~

Các finder trên biểu đạt điều kiện theo property của entity. Repository giúp caller không phải tự viết ContextMapper hoặc xử lý Attributes cho mỗi truy vấn thông thường. Khi cần một filter cụ thể hơn nhưng vẫn muốn nhận ODM entity, LdapRepository còn có các phương thức nhận LdapQuery như findAll(query) và findOne(query).

### 4.1. Đọc theo DN

Khi đã có ID/DN theo đúng quy ước ODM:

~~~java
PersonEntry person = personRepository.findById(dn)
        .orElseThrow(UserNotFoundException::new);
~~~

findById dùng DN làm định danh entry. Nó không tìm theo uid trừ khi uid chính là DN mà bạn truyền vào, điều này thường không đúng.

### 4.2. Tìm theo thuộc tính

~~~java
List<PersonEntry> matches = personRepository.findByUid("an");

if (matches.isEmpty()) {
    throw new UserNotFoundException();
}
if (matches.size() != 1) {
    throw new AmbiguousDirectoryIdentityException();
}

PersonEntry person = matches.get(0);
~~~

Không gọi get(0) mà bỏ qua uniqueness. LDAP schema không mặc định bảo đảm uid duy nhất trên toàn directory; quy tắc này còn phụ thuộc search base, tenant, naming context và policy.

### 4.3. Ghi và xóa entry

Repository có thể dùng cho các thao tác CRUD thông dụng:

~~~java
// Tạo hoặc lưu entity theo semantics của repository/ODM
// person là PersonEntry đã được tạo, gán DN và validate theo schema.
PersonEntry saved = personRepository.save(person);

// Đọc lại theo DN
PersonEntry loaded = personRepository.findById(saved.getDn())
        .orElseThrow(UserNotFoundException::new);

// Xóa entry đã xác định
personRepository.delete(loaded);
~~~

Đảm bảo entity có DN hợp lệ và các thuộc tính đáp ứng schema server, ví dụ inetOrgPerson cần cn và sn. Hành vi lưu một entry đã tồn tại, bind/rebind và xử lý xung đột phụ thuộc implementation/version và trạng thái DN; hãy kiểm thử rõ create/update/conflict với server đích.

**Repository không cung cấp dirty checking.** Sau khi sửa field trên loaded, thay đổi chỉ nằm trong object Java cho đến khi bạn gọi save hoặc một operation ghi rõ ràng. Không giả định chỉ cần mutate entity là LDAP tự cập nhật.

### 4.4. Khi repository là lựa chọn tốt

Chọn repository nếu:

- Mỗi use case làm việc với một loại entry đã có ODM mapping.
- CRUD là thao tác chính.
- Finder dựa trên một số property ổn định và dễ đọc.
- Ứng dụng không cần tùy chỉnh nhiều LDAP control hoặc response projection.
- Bạn muốn service tập trung vào nghiệp vụ thay vì chi tiết JNDI.

## 5. Cách 2 — LdapTemplate cho truy vấn cần kiểm soát

Khi cần kiểm soát search base, scope, filter và danh sách attribute trả về, dùng **LdapQueryBuilder** cùng **LdapTemplate**.

### 5.1. Tìm cùng user theo uid

~~~java
package org.example.directory.service;

import java.util.List;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonSummary> findByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        return ldapTemplate.search(
                query()
                    .base("ou=people")
                    .searchScope(SearchScope.SUBTREE)
                    .attributes("uid", "cn")
                    .countLimit(100)
                    .timeLimit(2000)
                    .where("objectClass").is("inetOrgPerson")
                    .and("uid").is(uid),
                (ContextMapper<PersonSummary>) raw -> {
                    DirContextOperations entry =
                            (DirContextOperations) raw;
                    return new PersonSummary(
                            entry.getStringAttribute("uid"),
                            entry.getStringAttribute("cn"));
                });
    }

    public record PersonSummary(String uid, String commonName) {}
}
~~~

Truy vấn có các phần rõ ràng:

- **base("ou=people")**: search base tương đối với base của ContextSource.
- **searchScope(SUBTREE)**: tìm trong nhánh people và các OU con.
- **attributes("uid", "cn")**: chỉ yêu cầu projection cần thiết.
- **countLimit** và **timeLimit**: giới hạn tài nguyên cho truy vấn.
- **where(...).and(...)**: xây filter bằng query builder, không nối chuỗi input vào raw filter.
- **ContextMapper**: chuyển mỗi kết quả sang projection Java mong muốn.

### 5.2. So sánh hai cách tìm cùng một user

| Tiêu chí | Repository | LdapTemplate |
| --- | --- | --- |
| Điều kiện tìm | findByUid(uid) | where("uid").is(uid) |
| Base DN | Theo ODM/repository mapping | Chỉ định rõ bằng .base(...) |
| Scope | Theo semantics finder/repository | Chọn OBJECT/ONELEVEL/SUBTREE |
| Projection | Trả entity ODM đã map | Chỉ định attribute và mapper |
| Kiểu kết quả | PersonEntry | DTO/projection tùy chọn |
| Mã lặp | Ít | Nhiều hơn, nhưng kiểm soát cao |
| Filter phức tạp | Finder hoặc findAll/findOne với LdapQuery; trả entity ODM | Query builder với mapper/projection tùy ý |

Nếu chỉ cần tìm uid và trả entity, repository thường dễ bảo trì hơn. Nếu chỉ cần uid và cn, không cần toàn bộ entity, hoặc cần scope khác, Template thường diễn đạt chính xác hơn.

### 5.3. Dùng LdapQuery với Repository khi vẫn muốn trả ODM entity

Không phải filter có nhiều điều kiện nào cũng bắt buộc chuyển sang Template. Nếu kết quả vẫn là entity ODM, có thể tạo LdapQuery rồi đưa vào repository:

~~~java
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);

List<PersonEntry> matches = personRepository.findAll(ldapQuery);
~~~

Nếu nghiệp vụ yêu cầu đúng một entry:

~~~java
PersonEntry person = personRepository.findOne(ldapQuery)
        .orElseThrow(UserNotFoundException::new);
~~~

findOne trả Optional và ném lỗi nếu có nhiều hơn một kết quả. Dùng nó khi uniqueness là một invariant của use case; nếu cần xử lý riêng 0/1/nhiều kết quả, dùng findAll và kiểm tra số lượng như phần 4.2.

Repository vẫn trả entity theo ODM mapping. Chọn Template khi bạn cần projection tùy chỉnh, ContextMapper/AttributesMapper, thao tác trực tiếp với Attributes hoặc LDAP control/processor.

## 6. Khi nào cần LdapTemplate thay repository?

### 6.1. Filter nhiều điều kiện

Ví dụ tìm người dùng có objectClass phù hợp, uid bằng một giá trị và mail thuộc domain công ty:

~~~java
List<PersonSearchService.PersonSummary> results = ldapTemplate.search(
        query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid)
            .and("mail").like("*@example.org"),
        (ContextMapper<PersonSearchService.PersonSummary>) raw -> {
            DirContextOperations entry = (DirContextOperations) raw;
            return new PersonSearchService.PersonSummary(
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("cn"));
        });
~~~

Query builder xử lý escaping **giá trị filter** theo cú pháp LDAP filter. Nếu tên attribute hoặc operator được chọn động, phải dùng allowlist; không cho caller truyền tên attribute hoặc biểu thức filter tùy ý.

### 6.2. Khác biệt giữa OBJECT, ONELEVEL và SUBTREE

Với cây:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=an
    ├── uid=binh
    └── ou=contractors
        └── uid=chi
~~~

| Scope | Kết quả khi base là ou=people |
| --- | --- |
| **OBJECT** | Chỉ entry ou=people |
| **ONELEVEL** | Các entry con trực tiếp: An, Binh và OU contractors |
| **SUBTREE** | Toàn bộ descendants, gồm cả Chi trong contractors |

Chọn scope là một phần của hợp đồng truy vấn. ONELEVEL có thể bỏ sót người dùng trong OU lồng nhau; SUBTREE trên suffix rộng có thể tìm cả service account hoặc nhóm ngoài use case.

### 6.3. Projection để giảm dữ liệu

Repository trả ODM entity theo mapping. Với một endpoint chỉ cần username và display name, Template có thể yêu cầu đúng hai attribute:

~~~java
.attributes("uid", "cn")
~~~

Projection giúp giảm dữ liệu truyền qua network và tránh vô tình tải những attribute không cần thiết. Nó không thay thế ACL: service account vẫn cần quyền phù hợp và response API vẫn phải qua DTO/authorization.

### 6.4. Thuộc tính nhiều giá trị

Một LDAP entry có thể chứa:

~~~ldif
mail: an@example.org
mail: an.tran@example.net
telephoneNumber: +84-28-5550-0101
telephoneNumber: +84-90-555-0101
~~~

Khi cần giữ đủ giá trị, LdapTemplate cho phép đọc Attributes hoặc DirContextOperations:

~~~java
String[] emails = entry.getStringAttributes("mail");
String[] phones = entry.getStringAttributes("telephoneNumber");
~~~

Không ánh xạ một attribute đa trị thành String rồi mặc định chỉ giá trị đầu tiên là giá trị chính. Hãy xác định API/domain cần List hay một primary value theo policy.

### 6.5. Cần operation LDAP cụ thể

Các use case sau thường phù hợp với Template:

- Thay một hoặc nhiều attribute bằng modifyAttributes.
- Thêm/xóa một value của multi-valued attribute.
- Rename RDN hoặc move entry bằng rename.
- Bind/unbind entry khi làm việc trực tiếp với Attributes.
- Lookup và map một tập thuộc tính cụ thể.
- Dùng control hoặc processor riêng của Spring LDAP.

## 7. CRUD với LdapTemplate khi cần kiểm soát operation

Repository che bớt phần thao tác directory. Template cho phép bạn chỉ rõ DN, Attributes và LDAP modification.

### 7.1. Tạo entry bằng bind

Ví dụ tạo một người dùng mới:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void createPerson(LdapTemplate ldapTemplate) {
    Name dn = LdapNameBuilder
            .newInstance("ou=people")
            .add("uid", "minh")
            .build();

    Attributes attrs = new BasicAttributes();
    Attribute objectClass = new BasicAttribute("objectClass");
    objectClass.add("top");
    objectClass.add("person");
    objectClass.add("organizationalPerson");
    objectClass.add("inetOrgPerson");
    attrs.put(objectClass);
    attrs.put("uid", "minh");
    attrs.put("cn", "Minh Nguyen");
    attrs.put("sn", "Nguyen");
    attrs.put("mail", "minh@example.org");

    ldapTemplate.bind(dn, null, attrs);
}
~~~

DN trong ví dụ là tương đối với ContextSource base đã cấu hình. Nếu server đã có entry cùng DN, bind sẽ thất bại; không dùng bind như một lệnh ghi đè. Với objectClass inetOrgPerson, các thuộc tính MUST như cn và sn phải có theo schema server.

### 7.2. Đọc entry bằng lookup

Khi đã biết DN, lookup đọc đúng entry:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public PersonSearchService.PersonSummary lookupPerson(
        LdapTemplate ldapTemplate, Name dn) {
    return ldapTemplate.lookup(
            dn,
            new String[]{"uid", "cn"},
            (AttributesMapper<PersonSearchService.PersonSummary>) attrs ->
                    new PersonSearchService.PersonSummary(
                            (String) attrs.get("uid").get(),
                            (String) attrs.get("cn").get()));
}
~~~

**lookup** phù hợp khi DN đã biết. Nếu chỉ biết uid hoặc email, cần search để tìm entry/DN trước. Không tự dựng DN từ username nếu RDN không được bảo đảm trùng username.

### 7.3. Sửa một attribute bằng Modify

Ví dụ thay email:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

public void updateEmail(
        LdapTemplate ldapTemplate, Name dn, String email) {
    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", email))
    };
    ldapTemplate.modifyAttributes(dn, changes);
}
~~~

Các operation thường dùng:

| Operation | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **ADD_ATTRIBUTE** | Thêm attribute hoặc value | Thêm một email vào attribute đa trị |
| **REMOVE_ATTRIBUTE** | Xóa attribute hoặc một value | Gỡ một số điện thoại cũ |
| **REPLACE_ATTRIBUTE** | Thay giá trị hiện có bằng giá trị mới | Cập nhật email chính |

Với attribute đa trị, cần xác định rõ muốn thêm một value hay thay toàn bộ tập value. REPLACE có thể xóa các giá trị khác ngoài ý muốn. Schema và server cũng có thể từ chối xóa giá trị cuối cùng của một attribute bắt buộc.

### 7.4. Xóa entry bằng unbind

~~~java
ldapTemplate.unbind(dn);
~~~

Unbind xóa entry theo DN. Server có thể từ chối nếu entry còn children (non-leaf), ACL không cho phép hoặc policy khác ngăn thao tác. Xóa một entry không đồng nghĩa ứng dụng đã xóa các tham chiếu trong database/cache hoặc mọi group trên server khác.

### 7.5. Rename hoặc move bằng rename

~~~java
Name oldDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", "minh")
        .build();

Name newDn = LdapNameBuilder
        .newInstance("ou=contractors")
        .add("uid", "minh")
        .build();

ldapTemplate.rename(oldDn, newDn);
~~~

Rename có thể thay RDN hoặc parent DN theo quy tắc của operation và server. Nó không tự bảo đảm mọi reference, cache hoặc dữ liệu ở hệ thống khác được cập nhật. Trước khi dùng, kiểm tra naming context, quyền, entry đích, children và referential integrity của directory.

### 7.6. Tương đương ở repository và Template

| Thao tác | Repository | LdapTemplate |
| --- | --- | --- |
| Tạo/lưu entity | save(entity) | bind(dn, object, attributes) |
| Đọc theo DN | findById(dn) | lookup(dn, mapper) |
| Tìm theo property | findByUid(uid) | search(query, mapper) |
| Cập nhật | save(entity) theo ODM semantics | modifyAttributes(dn, changes) |
| Xóa | delete(entity)/deleteById(dn) | unbind(dn) |
| Rename/move | Không phải abstraction chính cho use case này | rename(oldDn, newDn) |

Hai cột không phải lúc nào cũng tương đương hoàn toàn về semantics. Repository thao tác trên entity theo mapping; Template biểu diễn operation LDAP cụ thể. Hãy đọc tài liệu phiên bản đang dùng và kiểm thử create/update/delete/conflict trên server đích.

## 8. Kết hợp Repository và Template trong cùng ứng dụng

Không cần chọn duy nhất một công cụ cho toàn module. Một cách tổ chức thực tế:

| Layer/use case | Công cụ | Ví dụ |
| --- | --- | --- |
| Hồ sơ người dùng CRUD phổ thông | PersonRepository | Tìm theo uid, đọc entity, lưu thay đổi |
| Danh sách gọn cho API | LdapTemplate | Chỉ đọc uid/cn và map summary |
| Tìm kiếm nhiều điều kiện | LdapTemplate | objectClass + uid + trạng thái |
| Cập nhật email đơn giản | Repository hoặc Template | Chọn theo semantics ODM và yêu cầu field-level update |
| Sửa một value của group.member | LdapTemplate | ADD/REMOVE một DN |
| Rename/move user | LdapTemplate | Modify DN rõ ràng |

Ví dụ service có thể dùng repository để tìm entity, rồi dùng Template cho operation cần kiểm soát:

~~~java
import java.util.List;
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;
import org.example.directory.persistence.PersonEntry;
import org.example.directory.persistence.PersonRepository;
import org.example.directory.application.UserNotFoundException;
import org.example.directory.application.AmbiguousDirectoryIdentityException;

@Service
public class DirectoryProfileService {
    private final PersonRepository repository;
    private final LdapTemplate ldapTemplate;

    public DirectoryProfileService(
            PersonRepository repository,
            LdapTemplate ldapTemplate) {
        this.repository = repository;
        this.ldapTemplate = ldapTemplate;
    }

    public void replacePrimaryEmail(String uid, String email) {
        List<PersonEntry> matches = repository.findByUid(uid);
        if (matches.isEmpty()) {
            throw new UserNotFoundException();
        }
        if (matches.size() != 1) {
            throw new AmbiguousDirectoryIdentityException();
        }

        Name dn = matches.get(0).getDn();
        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("mail", email))
        };
        ldapTemplate.modifyAttributes(dn, changes);
    }
}
~~~

Repository chịu trách nhiệm tìm entry theo mô hình; Template chịu trách nhiệm sửa đúng attribute. Business rule, authorization, validation và error mapping vẫn thuộc application service.

**Tránh hai đường ghi không thống nhất.** Nếu một use case dùng repository.save và use case khác dùng modifyAttributes cho cùng một field, hãy định nghĩa rõ semantics và test để tránh hai luồng ghi đè hoặc làm mất multi-value.

## 9. Cây quyết định khi chọn

~~~mermaid
flowchart TD
    A["Bắt đầu từ use case"] --> B{"Đã có ODM entity ổn định?"}
    B -->|Chưa| C["Dùng LdapTemplate<br/>lookup/search và mapper"]
    B -->|Có| D{"CRUD/finder đơn giản đủ dùng?"}
    D -->|Có| E["Dùng LdapRepository"]
    D -->|Không| F{"Cần kiểm soát filter, scope,<br/>projection hoặc LDAP operation?"}
    F -->|Có| G["Dùng LdapTemplate"]
    F -->|Không| H["Kiểm tra khả năng finder<br/>của repository/version"]
    E --> I{"Có use case đặc thù?"}
    G --> I
    H --> I
    I -->|Có| J["Kết hợp Repository + Template"]
    I -->|Không| K["Giữ một abstraction nhất quán"]
~~~

Hãy tự hỏi:

1. Kết quả cần là entity đầy đủ hay projection nhỏ?
2. Search base và scope có cố định theo ODM mapping không?
3. Finder đơn giản có diễn đạt đủ điều kiện không?
4. Có cần sửa một attribute/value cụ thể mà không ghi lại cả entity không?
5. Có cần rename, LDAP control, paging hoặc server-specific behavior không?
6. Có cần kiểm soát số lượng attribute trả về và giới hạn kết quả không?

Nếu câu trả lời cho các câu 4–6 là có, Template thường phù hợp hơn.

## 10. Bảo mật khi dùng cả hai abstraction

Repository không tự động an toàn hơn Template, và Template không tự động nguy hiểm hơn repository. Cả hai cùng thực thi quyền của bind identity và phải tuân theo chính sách directory.

Các nguyên tắc:

- **Filter:** dùng query builder hoặc Filter API; không nối raw input thành filter.
- **Attribute name:** nếu chọn động, dùng allowlist; query builder chủ yếu bảo vệ giá trị, không hợp thức hóa tên attribute tùy ý.
- **DN:** dùng Name/LdapNameBuilder/Rdn; không ghép chuỗi từ dữ liệu client.
- **Search base/scope:** cố định hoặc allowlist theo use case; không để client tìm toàn suffix tùy ý.
- **Projection:** chỉ yêu cầu các attribute cần thiết.
- **ACL:** service account chỉ có quyền đọc/ghi tối thiểu.
- **Credentials:** lấy từ secret manager/environment; không hardcode hoặc log password.
- **TLS:** xác minh CA và hostname khi dùng LDAPS/StartTLS.
- **Authorization:** kiểm tra caller có quyền thao tác user/group đích; service bind quyền rộng không thay thế authorization ở ứng dụng.
- **Error:** không trả raw LDAP diagnostic message, DN nội bộ hoặc stack trace cho client.

Ví dụ không an toàn:

~~~java
import javax.naming.directory.SearchControls;

String filter = "(uid=" + request.getParameter("uid") + ")";
ldapTemplate.search(
        "ou=people",
        filter,
        SearchControls.SUBTREE_SCOPE,
        mapper);
~~~

Ví dụ dùng query builder:

~~~java
ldapTemplate.search(
        query().base("ou=people")
               .where("uid").is(validatedUid),
        mapper);
~~~

Query builder escape giá trị filter; vẫn cần validation nghiệp vụ, giới hạn base/scope và authorization.

## 11. Hiệu năng và khả năng mở rộng

### 11.1. Chỉ đọc những gì cần thiết

Repository thường trả entity theo ODM mapping. Template có thể chỉ yêu cầu:

~~~java
.attributes("uid", "cn")
~~~

Projection giảm lượng dữ liệu đọc, đặc biệt khi entry có binary/photo, certificate hoặc nhiều attribute không cần cho use case.

### 11.2. Giới hạn search

Với Template, đặt search base hẹp, scope phù hợp và count/time limit theo ngân sách của request. Không dùng SUBTREE trên naming context rộng nếu chỉ cần một OU. **Spring Data LDAP repository không hỗ trợ paging/sorting**; khi cần paging LDAP, dùng cơ chế paging/control của Spring LDAP như DirContextProcessor phù hợp với server và phiên bản đang dùng. Đừng tự tải toàn bộ directory vào memory.

### 11.3. Tránh N+1 search

Nếu một group có hàng nghìn member DN, không lookup từng member một cách tuần tự. Cân nhắc batch resolution, search theo nhóm điều kiện, cache có TTL và giới hạn kích thước response. Phải xử lý member DN stale, referral, ACL và các member nằm ở naming context khác.

### 11.4. Không giả định nhiều thao tác là transaction

Một service có thể thực hiện:

1. Search user.
2. Modify user.
3. Modify group membership.
4. Ghi audit vào database.

Các thao tác này không tự tạo transaction ACID xuyên LDAP và database. Nếu bước 3 hoặc 4 thất bại sau bước 2, cần workflow có checkpoint, retry có điều kiện hoặc reconciliation. @Transactional của Spring không tự biến nhiều LDAP operation thành một transaction phân tán.

## 12. Kiểm thử: test abstraction và test server

Nên chia kiểm thử thành các lớp:

| Loại test | Điều cần xác minh | Cách tiếp cận |
| --- | --- | --- |
| Unit test service | Quy tắc chọn repository/Template, xử lý 0/1/nhiều kết quả | Mock repository/Template |
| Repository integration | ODM mapping, finder, CRUD và DN | LDAP server test thật hoặc embedded phù hợp |
| Template integration | Base, scope, filter, projection, modify, rename | Directory test có schema tương ứng |
| Security test | ACL, TLS, bind identity, filter escaping | Cấu hình server test theo quyền |
| Compatibility test | Khác biệt vendor/version | Chạy trên cùng loại server với production |

### 12.1. Test repository finder

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class PersonRepositoryIntegrationTest {
    @Autowired PersonRepository repository;

    @Test
    void findsPersonByUid() {
        List<PersonEntry> results = repository.findByUid("test-user");

        assertEquals(1, results.size());
        assertEquals("test-user", results.get(0).getUid());
    }
}
~~~

Fixture phải được seed trước test và cleanup sau test. Test này xác minh finder trên directory thực tế, không chỉ xác minh method được gọi.

### 12.2. Test Template scope và projection

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class PersonSearchIntegrationTest {
    @Autowired PersonSearchService searchService;

    @Test
    void findsUserWithinConfiguredSubtree() {
        List<PersonSearchService.PersonSummary> results =
                searchService.findByUid("test-user");

        assertEquals(1, results.size());
        assertEquals("test-user", results.get(0).uid());
    }
}
~~~

Để xác minh projection, có thể thêm test fixture với một attribute nhạy cảm và kiểm tra DTO không chứa field đó. Projection ở LDAP query và DTO ở API là hai lớp bảo vệ khác nhau.

### 12.3. Ma trận kiểm thử lựa chọn

| Ca | Repository | LdapTemplate |
| --- | --- | --- |
| Finder đơn giản theo uid | Xác minh derived query và uniqueness | Xác minh filter tương đương |
| Username không tồn tại | Trả empty/not found theo contract | Search trả empty |
| Username trùng | Service phát hiện nhiều kết quả | Search trả nhiều kết quả |
| OU lồng nhau | Kiểm tra base/finder behavior | Kiểm tra OBJECT/ONELEVEL/SUBTREE |
| Attribute nhiều giá trị | ODM collection mapping nếu được cấu hình | Đọc đủ values từ Attributes |
| Attribute không có trong schema | Mapping/ghi bị server từ chối theo schema | Modify bị server từ chối theo schema |
| DN có ký tự đặc biệt | ID Name được map đúng | LdapNameBuilder tạo DN đúng |
| Cập nhật một attribute | Save semantics được xác minh | ModifyAttribute đúng loại |
| Rename/move | Kiểm tra giới hạn abstraction | Rename và đọc lại old/new DN |
| ACL thiếu quyền | Repository trả lỗi phù hợp | Template trả lỗi phù hợp |
| Filter input đặc biệt | Derived finder an toàn theo implementation | Query builder escape giá trị |

Mocking giúp test logic ứng dụng nhưng không chứng minh LDAP server áp dụng schema, ACL, control hoặc semantics rename đúng như production.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Repository không tìm thấy user | Finder search trong base không phù hợp hoặc uid không nằm trong ODM mapping | Kiểm tra @Entry.base, ContextSource base và attribute mapping |
| findById nhận username nhưng không có kết quả | findById cần DN, không phải uid | Dùng finder theo uid hoặc Template search |
| Search Template bỏ sót OU con | Dùng ONELEVEL thay vì SUBTREE | Chọn scope đúng nghiệp vụ |
| Search trả quá nhiều entry | Base DN quá rộng hoặc filter thiếu điều kiện | Thu hẹp base/filter và đặt limit |
| Attribute không được trả về | Projection không yêu cầu hoặc ACL không cho đọc | Kiểm tra attributes(...) và quyền |
| Save ghi đè/mất giá trị | Hiểu sai semantics ODM hoặc multi-value | Test create/update và dùng modifyAttributes khi cần field-level |
| Bind báo entry exists | DN đã có entry | Xử lý conflict; không coi bind là upsert |
| Modify bị schema violation | Thiếu MUST hoặc sai objectClass/syntax | Kiểm tra schema và attributes |
| Rename thất bại | Sai DN/base, DN đích tồn tại, ACL hoặc server restriction | Đọc result code và kiểm tra server policy |
| Chạy nhiều operation nhưng dữ liệu dở dang | Không có transaction đa-entry | Thiết kế journal/reconciliation |
| Raw filter bị injection | Nối chuỗi input vào filter | Dùng LdapQueryBuilder/Filter API |

## 14. Bài tập tự luyện

1. Viết một PersonEntry và PersonRepository có finder findByUid. Nêu những giả định về base DN và uniqueness.
2. Viết cùng truy vấn bằng LdapTemplate với SUBTREE và projection chỉ gồm uid/cn. So sánh số dòng code và quyền kiểm soát.
3. Tìm user theo uid trong hai OU khác nhau. Vì sao cần xử lý kết quả nhiều entry?
4. Dùng lookup khi biết DN và search khi chỉ biết email. So sánh hai operation.
5. Tạo entry inetOrgPerson bằng bind. Những attribute MUST nào cần có theo schema?
6. Cập nhật một giá trị mail bằng modifyAttributes. Khi nào dùng ADD, REMOVE và REPLACE?
7. Chuyển user sang OU khác bằng rename. Cần kiểm tra điều gì về naming context, ACL và DN references?
8. Thiết kế một use case kết hợp repository và Template mà không lặp business logic.
9. Viết integration test chứng minh scope ONELEVEL không tìm thấy user trong OU cháu nhưng SUBTREE tìm được.
10. Giải thích vì sao @Transactional không bảo đảm rollback nhiều LDAP operations.

## 15. Tổng kết

**LdapRepository** phù hợp với CRUD và finder đơn giản trên ODM entity. Nó giúp code theo mô hình entry, giảm phần mapping lặp và làm service dễ đọc. **LdapTemplate** phù hợp khi use case cần kiểm soát rõ search base, scope, filter, projection, multi-valued attributes hoặc LDAP operations như modify, rename và unbind.

Hai abstraction có thể cùng tồn tại trong một application. Hãy dùng repository cho luồng entity-centric phổ thông và Template cho những thao tác cần quyền kiểm soát LDAP rõ ràng. Dù chọn cách nào, ứng dụng vẫn phải quản lý DN, schema, ACL, TLS, filter escaping, giới hạn truy vấn và lỗi directory. Repository không tạo dirty checking hay transaction ACID kiểu JPA; Template cũng không tự làm cho truy vấn an toàn nếu base, filter và quyền không được kiểm soát.

### Tài liệu tham khảo

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — LdapRepository, ODM mapping và query methods.
- [Spring Data LDAP — LDAP Repositories](https://docs.spring.io/spring-data/ldap/reference/ldap.html) — ID kiểu Name, LdapQuery, giới hạn paging/sorting và repository support.
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html) — findAll(LdapQuery), findOne(LdapQuery) và CRUD contract.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, query builder, ContextMapper và LDAP operations.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html) — base, scope, projection, count/time limit và filter criteria của LdapQueryBuilder.
- [Spring LDAP — LdapTemplate Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) — lookup, search, bind, modifyAttributes, rename và unbind.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP Search, Modify, Modify DN và result codes.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — DN, entry, attribute types và objectClass.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — cú pháp và escaping của LDAP filter.
