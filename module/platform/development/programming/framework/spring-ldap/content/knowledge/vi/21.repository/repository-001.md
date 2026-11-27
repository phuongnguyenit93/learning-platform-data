# Spring Data LDAP Repository và quan hệ với Spring LDAP Core

Trong ứng dụng Java, tầng truy cập dữ liệu thường có những interface như `PersonRepository` với các phương thức `findById`, `save` và `deleteById`. Spring Data LDAP đưa mô hình **Repository** quen thuộc đó đến LDAP directory. Tuy nhiên, nó **không tạo một cơ sở dữ liệu mới** và không thay thế các quy tắc của LDAP. Bên dưới repository vẫn là Spring LDAP Core, **Object-Directory Mapping (ODM)**, `LdapTemplate`/`LdapOperations`, `ContextSource` và cuối cùng là các thao tác LDAP được server xử lý.

Bài thuộc chương **Repository** của **SPRING_LDAP**. Người học sẽ phân biệt các tầng công nghệ, tạo một entity ODM và một `LdapRepository<T>`, cấu hình `@EnableLdapRepositories`, viết truy vấn qua method name và `LdapQuery`, hiểu cách xử lý DN và `save(...)`, đồng thời nhận ra các việc vẫn nên dùng `LdapTemplate` hoặc `LdapClient`: sửa một giá trị đa trị, controls, paging/sorting do server thực thi, rename/move và xử lý lỗi chi tiết. Bài cũng đề cập schema, filter escaping, xác thực, TLS, phân quyền, unit test và integration test.

## 1. Ba tầng: Spring LDAP Core, ODM và Spring Data Repository

~~~mermaid
flowchart TD
    A["Controller / nghiệp vụ"] --> B["PersonRepository (Spring Data LDAP)"]
    A --> C["LdapTemplate / LdapClient (Spring LDAP Core)"]
    B --> D["Repository proxy + SimpleLdapRepository"]
    D --> E["ODM ObjectDirectoryMapper"]
    D --> C
    C --> F["ContextSource / JNDI connection"]
    F --> G[("LDAP server: DIT, schema, ACL, search, modify")]
~~~

Bức tranh trên thể hiện **quan hệ bổ sung**, không phải ba công nghệ thay thế hoàn toàn lẫn nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Spring LDAP Core** | Quản lý kết nối/context, tìm kiếm và các thao tác LDAP ở mức chi tiết | `LdapTemplate.search(...)`, `modifyAttributes(...)`, `rename(...)` |
| **Spring LDAP ODM** | Ánh xạ entry/attribute/DN vào đối tượng Java bằng annotation | `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` |
| **Spring Data LDAP Repository** | Sinh implementation cho interface repository, cung cấp CRUD và query methods trên entity ODM | `LdapRepository<PersonEntry>`, `findById(Name)` |
| **ContextSource** | Cung cấp kết nối, URL, base DN và danh tính bind | `LdapContextSource` |
| **LDAP server** | Lưu Directory Information Tree, áp schema, matching rules, ACL và trả mã kết quả | LDAP Search, Add, Modify, Delete, Modify DN |

Theo API hiện đại, implementation nền `SimpleLdapRepository<T>` được xây dựng với `LdapOperations`, `ObjectDirectoryMapper` và kiểu entity. Như vậy **repository đứng trên Core và ODM**, không phải truy vấn LDAP bằng một giao thức mới.

### Khi nào thích hợp dùng repository?

- Service cần đọc một entry theo DN, tìm danh sách theo thuộc tính hoặc lưu entity ODM với CRUD phổ biến.
- Đội phát triển muốn tách interface truy cập dữ liệu khỏi các chi tiết mapper và dùng dependency injection.
- Truy vấn có thể được mô tả ngắn gọn bằng tên phương thức hoặc `LdapQuery`.
- Domain có cách biểu diễn entry và DN ổn định, được khai báo rõ bằng annotation ODM.

### Khi nào cần quay về Core?

- Muốn điều khiển trực tiếp `ModificationItem` để thêm/xóa **một giá trị** trong attribute đa trị.
- Muốn gửi Server-Side Sort, Paged Results, VLV hoặc các LDAP controls có yêu cầu kết nối/cookie cụ thể.
- Muốn sử dụng `SearchControls`, referral, timeout hoặc projection theo cách không phù hợp với repository API.
- Thực hiện rename/move, cập nhật membership hoặc xử lý tình huống ghi đồng thời cần semantics tường minh.
- Cần thao tác rất đặc biệt với `DirContextAdapter`, `DirContextOperations` hoặc callback JNDI.

**Không có quy tắc “dùng repository thì cấm dùng `LdapTemplate`”.** Cùng một service có thể dùng repository cho tra cứu phổ biến và Core cho thao tác đặc thù, miễn là cả hai dùng cùng cấu hình directory/ACL phù hợp.

## 2. Cây LDAP và DN là nền tảng của Repository

Giả sử LDAP server có:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── uid=chi
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-reader
~~~

Entry ví dụ:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

Trong ứng dụng cấu hình `ContextSource.base=dc=example,dc=org`, DN đưa vào nhiều API Spring LDAP có dạng **tương đối với base**:

~~~text
uid=an,ou=people
~~~

Nó tương ứng DN đầy đủ trên server:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Ba định danh dễ bị nhầm:

| Định danh | Ví dụ | Bảo đảm |
| --- | --- | --- |
| **DN** | `uid=an,ou=people,dc=example,dc=org` | Một entry có tên duy nhất tại vị trí đó; **có thể đổi** do rename/move |
| **UID attribute** | `uid: an` | Có thể không duy nhất giữa nhiều OU nếu directory không áp chính sách bổ sung |
| **ID bất biến của nghiệp vụ/server** | `employeeNumber: E104` hoặc một ID server hỗ trợ | Chỉ bất biến/duy nhất khi được hệ thống bảo đảm |

**`findById` của LDAP repository tra cứu theo DN**, không phải `uid`. DN không tự trở thành khóa bất biến kiểu JPA chỉ vì có tên annotation `@Id`.

## 3. Các giới hạn đặc thù phải biết trước khi viết code

Spring Data LDAP không hoàn toàn giống Spring Data JPA:

| Khả năng hoặc giả định | Spring Data LDAP |
| --- | --- |
| `@Entity` của JPA | Không dùng để map LDAP; cần **annotation ODM của Spring LDAP** |
| `@Id` kiểu `Long` | **Sai** với entity LDAP; dùng `javax.naming.Name` |
| `LdapRepository<T, ID>` | **Sai về số tham số kiểu**; interface LDAP chỉ nhận **`T`** |
| `LdapRepository<T>` | Đúng; ID mặc định là `Name` |
| `findById(Name)`, `save(T)`, `deleteById(Name)` | Có theo API repository |
| `findAll(LdapQuery)`, `findOne(LdapQuery)` | Có trên **`LdapRepository<T>`** |
| Derived query như `findByUid(String)` | Được hỗ trợ theo property của entity và mapping LDAP |
| `Pageable`/`Page<T>`/`Sort` trên repository | **Không được hỗ trợ như các repository của database khác** |
| Transaction JPA, lazy relationships, cascade | Không tự có semantics ORM đa bảng/đa entry |
| `save(...)` bảo đảm upsert nguyên tử | **Không**; phụ thuộc xác định mới/cũ và thao tác LDAP |
| Tạo entry tại DN trùng | Server có thể trả `entryAlreadyExists (68)` |
| Thực thi query | LDAP server áp search base, scope, schema, matching rule và ACL |

Theo tài liệu chính thức, **LDAP repositories không hỗ trợ paging và sorting theo abstraction của Spring Data** do đặc thù giao thức. Nếu cần hai chức năng này, triển khai riêng với LDAP controls và xác minh khả năng server thay vì thêm `Pageable` vào repository method rồi kỳ vọng tương tự JPA.

## 4. Khai báo entity bằng annotation ODM của Spring LDAP

Repository chỉ hỗ trợ entity đã được định nghĩa theo **Spring LDAP ODM**. Ví dụ:

~~~java
package com.example.directory.model;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
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
    @DnAttribute(value = "uid", index = 0)
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

Vai trò từng annotation:

- **`@Entry`** mô tả các LDAP object classes và base cho entity.
- **`@Id`** là **DN của entry**, phải gắn với field kiểu `javax.naming.Name` hoặc kiểu con hợp lệ.
- **`@Attribute`** ánh xạ field sang LDAP attribute, ví dụ `commonName` → `cn`.
- **`@DnAttribute(index=0)`** cho phép ODM tính DN mới theo giá trị `uid` và `@Entry.base` khi trường `dn` ban đầu rỗng.
- **Không dùng `org.springframework.data.annotation.Id`** hoặc `jakarta.persistence.Id` trong entity ODM. Spring LDAP dùng hệ annotation riêng.
- `@DnAttribute` **không tự loại field khỏi mapping thuộc tính**; `@Attribute` giúp khai báo tên attribute tường minh.

Với `uid="an"` và `@Entry.base="ou=people"`, DN do ODM tính trong ví dụ là:

~~~text
uid=an,ou=people
~~~

Nếu `ContextSource.base=dc=example,dc=org`, entry tương ứng được lưu tại:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

**Không lặp suffix của ContextSource trong `@Entry.base`** khi ví dụ này đang dùng base tương đối. Nếu dự án có sơ đồ DIT khác, cần xác định cách tính DN trên phiên bản thư viện đang dùng.

### Vì sao ví dụ dùng `@DnAttribute`?

Cách tạo thông qua repository có thể dựa vào việc xác định entity mới từ DN/ID. Với entity mới, để `@Id=null` và cung cấp `uid` + `@DnAttribute(index=0)` cho ODM tính DN là một cách nhất quán. Nếu tự điền DN cho một entity chưa tồn tại rồi gọi `save(...)`, một số implementation có thể **xem entity là đã tồn tại** và chọn đường update; vì thế không nên coi `save(...)` là Add hay upsert bất kể trạng thái.

Nếu muốn **create-only với DN tự dựng tường minh**, có thể dùng `LdapTemplate.create(entity)` và bắt lỗi trùng DN theo hợp đồng nghiệp vụ; hoặc dùng chiến lược entity mới được repository hỗ trợ và đã kiểm thử.

## 5. Tạo interface Repository đúng kiểu

Chỉ cần khai báo interface:

~~~java
package com.example.directory.repository;

import java.util.List;

import com.example.directory.model.PersonEntry;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    List<PersonEntry> findByCommonName(String commonName);
}
~~~

Spring Data tạo implementation cho interface này khi cấu hình repository scanning đã bật. Không cần tự viết `PersonRepositoryImpl` chỉ để triển khai `findById` hoặc một derived query đơn giản.

**Chú ý kiểu generic:** cách viết sau **sai** vì `LdapRepository` chỉ có một tham số kiểu:

~~~java
// SAI:
// public interface PersonRepository
//         extends LdapRepository<PersonEntry, String> {}

// SAI:
// public interface PersonRepository
//         extends LdapRepository<PersonEntry, Name> {}
~~~

Cách đúng:

~~~java
public interface PersonRepository extends LdapRepository<PersonEntry> {
    // ID được cố định là javax.naming.Name.
}
~~~

Theo API hiện hành, `LdapRepository<T>` kế thừa `ListCrudRepository<T, Name>`, vì vậy có các phương thức như `save`, `findById`, `existsById`, `findAll`, `deleteById`; cùng hai overload đặc thù:

~~~java
List<PersonEntry> findAll(LdapQuery query);
Optional<PersonEntry> findOne(LdapQuery query);
~~~

Hai dòng cuối minh họa kiểu trả về trên `PersonRepository`; chúng được **kế thừa từ `LdapRepository`**, không cần viết lại.

### Derived query dùng tên field Java

Ví dụ `findByCommonName("Nguyen Van An")` biểu đạt ràng buộc theo property Java `commonName`. ODM biết field này ứng với LDAP attribute `cn` nhờ:

~~~java
@Attribute(name = "cn")
private String commonName;
~~~

Tương tự `findByUid("an")` tìm theo attribute `uid`. **Không nhầm với `findById`**: `findById` là phương thức cơ sở nhắm vào trường DN ở `@Id`.

Cần lưu ý kết quả `findByUid(...)` có thể có nhiều entry ở các nhánh khác nhau nếu phạm vi truy vấn và chính sách uniqueness cho phép. Vì vậy ví dụ dùng kiểu `List<PersonEntry>` thay vì mặc định đòi đúng một kết quả.

## 6. Kích hoạt repository và cấu hình kết nối

Với Spring Boot có module dữ liệu LDAP, cách thông dụng là khai báo starter phù hợp với dòng Spring Boot đang dùng (ví dụ `spring-boot-starter-data-ldap`), để dependency management của dự án chọn các phiên bản Spring LDAP Core/Spring Data LDAP tương thích.

Ví dụ cấu hình ứng dụng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

`LDAP_BIND_PASSWORD` phải đến từ môi trường/secret manager đã kiểm soát. Cấu hình chỉ minh họa; không lưu mật khẩu thật trong repository và không vô hiệu hóa hostname/certificate verification để “giải quyết” lỗi TLS.

Bật repository scanning:

~~~java
package com.example.directory.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository"
)
public class LdapRepositoryConfig {
}
~~~

Với Spring Boot, cấu hình `ContextSource` và `LdapTemplate` có thể được auto-configure khi các dependency phù hợp có mặt. Nếu ứng dụng tự khai báo bean thay thế, cần xác định repository thực sự được nối với đúng `LdapTemplate`.

Ví dụ cấu hình Java tường minh khi đã có `ContextSource`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;

@Configuration
public class LdapTemplateConfig {

    @Bean("ldapTemplate")
    public LdapTemplate ldapTemplate(ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

**Không tự khai báo đồng thời hai bean cùng tên `ldapTemplate`** khi Spring Boot đã tạo một bean phù hợp; đoạn Java chỉ là ví dụ nếu dự án cần cấu hình tường minh.

Mặc định, cấu hình repository tìm bean `LdapTemplate` tên `ldapTemplate`. Khi có nhiều directory:

~~~java
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository",
    ldapTemplateRef = "peopleLdapTemplate"
)
~~~

Hãy đảm bảo bean `peopleLdapTemplate` kết nối đúng directory, có `ContextSource.base` và quyền phù hợp. Cùng một `Name` tương đối có thể trỏ sang entry khác nếu đổi `ContextSource`.

### Repository không tự cấu hình bảo mật

`@EnableLdapRepositories` chỉ kích hoạt cơ chế tạo repository beans. Nó **không xác thực người dùng cuối thay ứng dụng**, không bắt buộc TLS và không cấp ACL trên LDAP server. Những việc này thuộc cấu hình kết nối, Spring Security và chính sách của server.

## 7. Gọi CRUD Repository trong service

Ví dụ service sử dụng `PersonRepository`:

~~~java
package com.example.directory.service;

import java.util.List;
import java.util.Optional;

import javax.naming.Name;

import com.example.directory.model.PersonEntry;
import com.example.directory.repository.PersonRepository;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    private final PersonRepository repository;

    public PersonDirectoryService(PersonRepository repository) {
        this.repository = repository;
    }

    public Optional<PersonEntry> findByDn(String uid) {
        Name dn = personDn(uid);
        return repository.findById(dn);
    }

    public List<PersonEntry> findByUid(String uid) {
        validateUid(uid);
        return repository.findByUid(uid);
    }

    public PersonEntry createPerson(
            String uid, String name, String surname) {
        validateUid(uid);
        if (name == null || name.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("cn/sn are required");
        }

        PersonEntry person = new PersonEntry();
        // @Id vẫn null: ODM tính DN từ @DnAttribute(index=0).
        person.setUid(uid);
        person.setCommonName(name);
        person.setSurname(surname);

        return repository.save(person);
    }

    public void deleteByDn(String uid) {
        repository.deleteById(personDn(uid));
    }

    private static Name personDn(String uid) {
        validateUid(uid);
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

Giải thích:

1. `findById(personDn(uid))` nhắm vào DN **tương đối với ContextSource.base** chứ không phải chuỗi UID đơn.
2. `findByUid(uid)` là query theo attribute và có thể trả nhiều entry.
3. `createPerson` để `@Id=null` để đường `save` nhận diện entity mới và ODM tính DN từ `@DnAttribute`. **Cần kiểm thử trên phiên bản Spring Data LDAP thực tế** vì chi tiết chiến lược xác định mới/cũ có thể phụ thuộc implementation/entity.
4. `deleteById` là lệnh có tác động lên LDAP server, không nên gọi từ endpoint khi chưa kiểm tra người dùng có quyền xóa chủ thể đó.
5. `LdapNameBuilder` giúp escape RDN đúng cú pháp; không thay thế validation và ACL.
6. Service mới chỉ minh họa ba nghiệp vụ. Trong ứng dụng thật cần contract xử lý conflict, lỗi kết nối, audit và chống truy cập ngoài OU.

**Không dùng `repository.deleteAll()` như một thao tác dọn dữ liệu thử nghiệm.** Nó có thể tác động đến rất nhiều entry trong vùng được repository quản lý, và LDAP server có thể không cho xóa entry không rỗng.

## 8. Truy vấn: method name, `LdapQuery` và `@Query`

Repository LDAP có nhiều cấp diễn đạt query. Chọn cấp đơn giản nhất nhưng vẫn minh bạch về filter/base/scope.

### 8.1. Derived query

~~~java
List<PersonEntry> findByUid(String uid);

List<PersonEntry> findByCommonName(String commonName);
~~~

Spring Data phân tích tên phương thức và tạo truy vấn theo thuộc tính đã ánh xạ. Với các operator như `And`, `Or`, `StartingWith` hoặc `Containing`, chỉ dùng những từ khóa được hỗ trợ bởi phiên bản đang dùng và kiểm thử filter thực tế trên directory.

**Không nối input thẳng vào chuỗi filter**. Dữ liệu do người dùng đưa vào phải được escape theo quy tắc LDAP filter, không phải DN string.

### 8.2. `LdapQueryBuilder` cho truy vấn linh hoạt

~~~java
import java.util.List;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<PersonEntry> findByExactMail(String exactMail) {
    if (exactMail == null || exactMail.isBlank()) {
        throw new IllegalArgumentException("mail is required");
    }

    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("mail").is(exactMail);

    return repository.findAll(query);
}
~~~

Đây là một method đặt trong service có field `repository`; `.is(exactMail)` tìm **giá trị email chính xác**, không phải wildcard tìm mọi địa chỉ thuộc một domain. Khi cần tìm theo domain, phải xác định filter, wildcard và quy tắc escaping riêng.

`LdapRepository<T>` hỗ trợ `findAll(LdapQuery)` và `findOne(LdapQuery)`; interface `CrudRepository<T,Name>` chung **không** khai báo hai overload này.

### 8.3. `@Query` khai báo filter tĩnh có tham số

Khi filter phức tạp nhưng cố định, có thể dùng annotation repository:

~~~java
import java.util.List;

import com.example.directory.model.PersonEntry;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    @Query("(&(objectClass=inetOrgPerson)(mail=?0))")
    List<PersonEntry> findWithMail(String email);
}
~~~

`?0` là tham số thứ nhất, được Spring Data LDAP bind/encode theo cơ chế query string của nó. Dùng `@Query` cho **filter tĩnh**; không để caller gửi nguyên chuỗi filter chưa kiểm soát qua HTTP API.

**Cẩn trọng với SpEL trong `@Query`:** tài liệu Spring Data LDAP cảnh báo các biểu thức giá trị có thể **không tự được escape như parameter thông thường**. Nếu dùng SpEL cho dữ liệu người dùng, phải đánh giá và escape đúng theo ngữ cảnh. Trong phần lớn service CRUD, ưu tiên builder hoặc query parameter chuẩn để tránh LDAP filter injection.

### Ba cách tìm không giống nhau

| Cách | Đặc điểm | Khi dùng |
| --- | --- | --- |
| `repository.findById(Name)` | Tra cứu **DN cụ thể** | Biết tên/vị trí entry |
| `repository.findByUid(String)` | Search theo attribute `uid` | Chỉ biết UID hoặc có thể nhiều OU |
| `repository.findAll(LdapQuery)` | Query tường minh có filter và base | Bộ lọc động có kiểm soát |
| `LdapTemplate.search(...)` | Cấu hình search controls, mapper, processor | Truy vấn/controls nâng cao |
## 9. `save(...)` không phải một lệnh SQL UPSERT

Từ góc nhìn ứng dụng, `repository.save(person)` rất ngắn. Nhưng cách ánh xạ nó sang LDAP **phụ thuộc trạng thái entity**:

~~~mermaid
flowchart TD
    A["repository.save(entity)"] --> B{"Entity được xác định mới?"}
    B -->|Có| C["ODM tính DN từ @DnAttribute nếu cần"]
    C --> D["LDAP Add/create"]
    B -->|Không| E["ODM update theo DN/entity"]
    D --> F{"Schema / ACL / DN hợp lệ?"}
    E --> F
    F -->|Có| G["Trả entity"]
    F -->|Không| H["Exception / lỗi LDAP"]
~~~

Ở implementation repository thông dụng, cách phát hiện “mới” có thể dựa trên việc `@Id` đã có giá trị hay chưa; một entity thực hiện giao diện quản lý trạng thái riêng cũng có thể ảnh hưởng đường xử lý. Vì vậy phải **kiểm tra hành vi ở phiên bản Spring Data LDAP của dự án** và kiểm thử thao tác ghi thực.

| Trạng thái | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Entity mới: `dn=null`, `uid` có giá trị và `@DnAttribute(index=0)` đúng | ODM tính DN; đường tạo entry được thực hiện |
| Entity mới nhưng service **gán DN ngay từ đầu** | Repository có thể nhận diện là entity cũ; không mặc định lệnh Add |
| Entity đã đọc từ repository: `dn != null` | Save thường đi theo đường cập nhật |
| DN đích đã được người khác tạo | LDAP Add có thể trả `entryAlreadyExists (68)` |
| DN đích bị xóa trước khi update | LDAP Modify/Update có thể trả `noSuchObject (32)` |
| Network timeout trong lúc ghi | Không biết chắc server đã xử lý hay chưa |

**Bài học:** `save(...)` là **abstraction CRUD**, không phải cam kết “nếu chưa có thì thêm, nếu có thì cập nhật” nguyên tử theo mọi tình huống. Một request chỉ muốn tạo tài khoản phải xử lý xung đột DN có chủ đích; không âm thầm ghi đè dữ liệu tồn tại khi save thất bại.

### Cập nhật một thuộc tính thông thường

Ví dụ:

~~~java
import javax.naming.Name;
import java.util.NoSuchElementException;

import com.example.directory.model.PersonEntry;
import com.example.directory.repository.PersonRepository;

public void updateEmail(Name dn, String newEmail) {
    if (newEmail == null || newEmail.isBlank()
            || newEmail.length() > 254) {
        throw new IllegalArgumentException("Invalid email");
    }

    PersonEntry person = repository.findById(dn)
            .orElseThrow(() ->
                    new NoSuchElementException("Person not found"));

    person.setEmail(newEmail);
    repository.save(person);
}
~~~

Đây là phương thức mẫu đặt trong service có field `repository`. Với entry đã đọc, `@Id` đã được ánh xạ. Dù vậy, ODM update có thể chịu ảnh hưởng mapping fields và schema, nên khi có attribute do nhiều hệ thống cùng quản lý, cần kiểm thử liệu thao tác cập nhật có giữ nguyên dữ liệu không thuộc trách nhiệm ứng dụng hay không.

Nếu chỉ muốn thêm **một** giá trị điện thoại, đặt lại toàn bộ array trên entity rồi save có thể nguy hiểm. Cách biểu diễn một lệnh LDAP Modify rõ ràng hơn được nêu ở phần sau.

### Tránh đổi UID/DN bằng một setter đơn giản

Nếu `uid` được đánh dấu `@DnAttribute(index=0)`, thay `person.setUid("an2")` trên entity có thể làm DN được tính khác DN đang lưu trong `@Id`. Trong ODM, cập nhật một field tham gia DN có thể dẫn tới hành vi move/recreate tùy thư viện và cách mapping; không coi đó là một Modify attribute vô hại.

Đổi username, RDN hoặc OU cần quy trình riêng: kiểm tra DN mới chưa trùng, phân quyền ở OU cũ/mới, schema, tham chiếu nhóm, chính sách `deleteOldRDN` và trạng thái khi lỗi giữa chừng. Dùng Core `LdapTemplate.rename(oldDn,newDn)` hoặc API phù hợp đã được kiểm thử khi nghiệp vụ thực sự muốn rename/move.

## 10. Khi cần chi tiết LDAP: dùng Core bổ sung cho repository

Giả sử một nhóm có thuộc tính đa trị:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Ứng dụng muốn thêm Chi vào nhóm, **không được xóa** An và Bình. Trong trường hợp đó, gửi LDAP Modify để **ADD đúng một giá trị** có ngữ nghĩa rõ ràng hơn thay toàn bộ `member` bằng một danh sách cũ.

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class GroupMemberWriter {
    private final LdapTemplate ldapTemplate;

    public GroupMemberWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void addMember(String groupCn, String personUid) {
        if (groupCn == null || groupCn.isBlank()
                || personUid == null || personUid.isBlank()) {
            throw new IllegalArgumentException("Invalid identifier");
        }

        // DN entry cần sửa: tương đối với ContextSource.base.
        Name groupDn = LdapNameBuilder.newInstance("ou=groups")
                .add("cn", groupCn)
                .build();

        // Giá trị của thuộc tính member: DN đầy đủ trên server.
        Name memberDn = LdapNameBuilder.newInstance(
                        "ou=people,dc=example,dc=org")
                .add("uid", personUid)
                .build();

        ModificationItem addOne = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", memberDn.toString()));

        ldapTemplate.modifyAttributes(
                groupDn,
                new ModificationItem[]{addOne});
    }
}
~~~

**Khác biệt quan trọng:**

- Repository phù hợp để tìm entity `PersonEntry` theo DN hoặc thuộc tính.
- Core có thể gửi đúng lệnh **ADD một giá trị** `member`.
- Lệnh MODIFY trên server **không phải** `repository.save(group)` với tập `member` được thay toàn bộ.
- Giá trị `member` là **DN đầy đủ** theo schema trong ví dụ; không được lẫn với `groupDn` tương đối khi `ContextSource.base` đã cấu hình.
- Cần kiểm tra **quyền nghiệp vụ** của caller, ACL LDAP, người dùng đích có hợp lệ không và điều kiện `groupOfNames` không cho phép thiếu giá trị `member` bắt buộc.
- Trong đa môi trường, không hardcode suffix `dc=example,dc=org` cho thành viên. Lấy naming context từ cấu hình được quản trị.

Đây là trường hợp hai lớp công nghệ **hợp tác**, không phải mâu thuẫn. Một service có thể inject cả `PersonRepository` và `LdapTemplate`:

~~~java
@Service
public class DirectoryAccessService {
    private final PersonRepository people;
    private final LdapTemplate ldapTemplate;

    public DirectoryAccessService(
            PersonRepository people,
            LdapTemplate ldapTemplate) {
        this.people = people;
        this.ldapTemplate = ldapTemplate;
    }

    // Dùng people để tra cứu ODM.
    // Dùng ldapTemplate cho các operation LDAP cần kiểm soát chi tiết.
}
~~~

## 11. Paging và sorting: giới hạn rõ ràng của LDAP Repository

Trong Spring Data JPA, nhiều người quen:

~~~java
// Ví dụ kỳ vọng SAI cho Spring Data LDAP Repository:
//
// Page<PersonEntry> findAll(Pageable pageable);
// List<PersonEntry> findAll(Sort sort);
~~~

Theo tài liệu chính thức của Spring LDAP, abstraction **LDAP Repository không hỗ trợ paging và sorting** như các store khác. Không thêm `PagingAndSortingRepository` rồi giả định Spring Data LDAP tự gửi LDAP Paged Results và Server-Side Sort.

Các cơ chế LDAP thực tế là:

| Cơ chế LDAP | OID | Mục đích |
| --- | --- | --- |
| Simple Paged Results, RFC 2696 | `1.2.840.113556.1.4.319` | Duyệt tuần tự nhiều trang bằng cookie |
| Server-Side Sort, RFC 2891 (request) | `1.2.840.113556.1.4.473` | Server sắp xếp tập kết quả |
| Virtual List View (VLV, request) | `2.16.840.1.113730.3.4.9` | Chọn cửa sổ theo vị trí trong tập đã sort, nếu server hỗ trợ |

Muốn sử dụng chúng, xem các processor tương ứng trong **Spring LDAP Core** như:

~~~java
org.springframework.ldap.control.PagedResultsDirContextProcessor
org.springframework.ldap.control.SortControlDirContextProcessor
org.springframework.ldap.control.VirtualListViewControlAggregateDirContextProcessor
~~~

Ở phiên bản Spring LDAP mới hơn, có các lớp `ControlExchangeDirContextProcessor` thay thế một số API cũ; cần kiểm tra version để chọn class đúng. Dùng `LdapTemplate.search(...)` với `DirContextProcessor` và kiểm tra **response control**, không chỉ xem danh sách kết quả.

### Cookie paging không tự đảm bảo snapshot

Khi ứng dụng đọc trang 1 rồi trang 2, một entry có thể được thêm, xóa hoặc đổi sort key giữa hai request. **RFC 2696 không mặc định cung cấp snapshot bất biến**, nên có thể thấy ID trùng hoặc thiếu. Khi test đồng bộ cần xác định ID ổn định, trạng thái tập dữ liệu và chính sách reconciliation.

Một số triển khai paging qua Spring LDAP còn yêu cầu giữ **cùng underlying LDAP connection** cho một chuỗi request. Thiết kế Core cần duy trì context tương ứng và xử lý timeout/cookie hết hạn; repository không tự giải quyết chuyện đó.

## 12. Repository query không thay thế search base, scope và LDAP filter

Một repository method rất ngắn:

~~~java
List<PersonEntry> findByUid(String uid);
~~~

Nhưng LDAP server vẫn thực hiện tìm kiếm theo:

- **Base:** nhánh được ORM/ODM/query xác định, kết hợp `ContextSource.base`.
- **Scope:** chỉ entry base, một cấp hoặc cả subtree tùy cấu hình query/implementation.
- **Filter:** điều kiện `uid` và object class được mapping.
- **Requested attributes:** dữ liệu mapper cần để dựng entity.
- **ACL:** quyền của tài khoản bind quyết định entry và attribute có thể đọc.
- **Schema/matching rules:** quyết định giá trị có khớp hay không.

### Tránh nhầm tên property với attribute

~~~java
@Attribute(name = "cn")
private String commonName;
~~~

Với field này:

~~~java
List<PersonEntry> findByCommonName(String name);
~~~

Tên derived query là **`CommonName`** từ Java field; mapping LDAP chỉ ra rằng attribute tương ứng là `cn`. Không viết `findByCn(...)` nếu entity thực tế **không có** property `cn` và mong framework tự đoán tên attribute.

### Tránh wildcard và SpEL không được kiểm soát

Một endpoint search không nên nhận chuỗi raw:

~~~java
// Không làm:
String filter = "(uid=" + input + ")";
ldapTemplate.search(..., filter, ...);
~~~

Filter có cú pháp riêng; các ký tự `*`, `(`, `)`, `\` và NUL trong giá trị cần escape đúng theo RFC 4515. Với query động, dùng `LdapQueryBuilder`:

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(input);
List<PersonEntry> results = repository.findAll(query);
~~~

Đây là **escaping cho filter**, không phải escaping của DN. Nếu dựng DN từ input, dùng `LdapNameBuilder`. Cả hai loại escaping đều không thay cho kiểm tra caller có quyền truy cập hoặc đổi dữ liệu.

## 13. Giới hạn ORM: schema, ACL, transaction và referential integrity

Repository abstraction làm code Java ngắn hơn nhưng **không làm LDAP trở thành relational database**.

| Chủ đề | Ràng buộc khi dùng LDAP Repository |
| --- | --- |
| Object class và MUST/MAY | LDAP server từ chối entry thiếu `cn`/`sn` hoặc attribute không hợp schema |
| DN unique | DN đích phải chưa được dùng nếu thao tác là Add |
| UID unique toàn tổ chức | Không tự được bảo đảm nếu nhiều OU dùng chung UID |
| Referential integrity | Nhóm có `member` là DN; rename người dùng không luôn tự cập nhật nhóm |
| Transaction đa entry | Một chuỗi `save`/`delete` không tự rollback giống JPA transaction |
| Optimistic locking/version | Không giả định có `@Version` semantics như JPA |
| Lazy loading/relations | Không tự có một graph ORM với cascade kiểu SQL |
| Multi-valued attributes | Không phải một cột String; thay tập giá trị có thể xóa giá trị khác |
| Server controls | VLV/SSS/paging không phải phương thức repository chuẩn |
| Exception mapping | Spring LDAP có các exception được chuyển từ JNDI/LDAP result codes |
| Tính nhất quán đồng thời | Search trước rồi save không loại bỏ TOCTOU, timeout có thể để lại kết quả chưa rõ |

**Ví dụ race:** hai request đều kiểm tra `existsById(dn)==false`, rồi cùng tạo. Không có bảo đảm cả hai sẽ thành công vì LDAP Add trên DN chỉ tạo được một entry. Do đó **phải bắt conflict tại thao tác ghi**, không coi `existsById` là khóa.

### Không gọi `deleteAll()` tùy tiện

LDAP là thư mục vận hành nhiều hệ thống khác nhau. Xóa toàn bộ entry trong phạm vi repository có thể ảnh hưởng đăng nhập, nhóm và tích hợp. Những API như `deleteAll` là **lệnh ghi nguy hiểm trong production**; cần giới hạn quyền tài khoản, áp dụng kiểm tra nghiệp vụ và chỉ xóa các DN đã được phê duyệt.

## 14. Bảo mật: kết nối, quyền và dữ liệu cần bảo vệ

Một cấu hình repository hoạt động không chứng minh nó an toàn. Cần đồng thời kiểm tra:

1. **LDAPS hoặc StartTLS**: xác thực certificate chain, hostname, CA; không tắt TLS verification để chạy được môi trường thử.
2. **Bind DN và secret**: ứng dụng kết nối bằng danh tính dịch vụ được cấp đúng quyền. Không hardcode mật khẩu, không in secret vào log.
3. **LDAP ACL**: tài khoản chỉ đọc không có quyền add/modify/delete; tài khoản cập nhật chỉ được ghi trong nhánh nghiệp vụ.
4. **Quyền người gọi**: controller/service phải xác minh ai được đọc/sửa UID nào; không chỉ tin rằng repository có thể truy cập.
5. **DN scope**: không cho request đưa raw DN bất kỳ dẫn tới sửa service account hoặc OU ngoài phạm vi.
6. **Filter an toàn**: dùng builder/bound parameter, không nối chuỗi filter từ input.
7. **Giới hạn search**: tránh gọi `findAll()` không điều kiện trên directory lớn; giới hạn base, filter, time/size theo nhu cầu.
8. **Bảo vệ dữ liệu**: không log toàn bộ entity chứa email, phone hoặc DN nhạy cảm ở mọi lỗi.
9. **Pooling**: kiểm tra life cycle và không trộn identity của các user khi dùng kết nối có trạng thái.
10. **Rotate secret**: xác minh cách context source và pool nhận credential mới.

### Cẩn thận với user enumeration

Nếu API trả chi tiết “UID an đã tồn tại” cho mọi người gọi, nó có thể giúp đối tượng không được phép dò tài khoản. Đôi khi cần thông báo chung phù hợp chính sách, dù nội bộ phân biệt `entryAlreadyExists` với `noSuchObject` hoặc thiếu quyền.

## 15. Phân loại lỗi thay vì trả một trạng thái chung

| Lỗi/sự cố | Mã LDAP điển hình | Ý nghĩa cho service |
| --- | --- | --- |
| DN đã tồn tại khi tạo | `entryAlreadyExists (68)` | Conflict, không tự overwrite |
| DN không có khi update/lookup | `noSuchObject (32)` | Not found hoặc concurrent deletion |
| Thiếu quyền | `insufficientAccessRights (50)` | Chặn thao tác, điều tra ACL |
| Sai object class/MUST | `objectClassViolation (65)` | Sửa mapping và schema |
| Sai attribute syntax | `invalidAttributeSyntax (21)` | Kiểm tra validation |
| Constraint violation | `constraintViolation (19)` | Kiểm tra SINGLE-VALUE, policy |
| Bind credential sai | `invalidCredentials (49)` | Kiểm tra secret và danh tính kết nối |
| Connection/TLS timeout | Không có phản hồi chắc chắn | Có thể ghi đã xảy ra; xác minh trước retry |
| Query trả hơn một entry khi đòi đúng một | Spring `IncorrectResultSizeDataAccessException` | Xác định uniqueness/scope, không tự lấy phần tử đầu |
| Server hết thời gian hoặc vượt giới hạn | `timeLimitExceeded (3)`, `adminLimitExceeded (11)` | Giảm base/filter hoặc đổi chiến lược truy vấn |

Ví dụ một service không nên làm:

~~~java
try {
    return repository.save(person);
} catch (Exception ex) {
    // SAI: timeout, ACL, schema và duplicate bị che chung.
    throw new IllegalStateException("User already exists");
}
~~~

Cần bắt những exception cụ thể phù hợp phiên bản Spring LDAP và hợp đồng nghiệp vụ. Với lỗi ghi sau timeout, kết quả có thể **không xác định**: server có thể đã ghi dù client không nhận được response. Không retry mù rồi coi lỗi trùng DN ở lần sau là chứng minh lần đầu thất bại.

## 16. Unit test: kiểm tra logic service, không giả định đã test LDAP

Unit test có thể dùng Mockito để kiểm tra service dựng đúng DN và gọi repository với input hợp lệ.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class PersonDirectoryServiceTest {

    @Test
    void findByDnUsesRelativeName() {
        PersonRepository repository = mock(PersonRepository.class);
        PersonDirectoryService service =
                new PersonDirectoryService(repository);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an")
                .build();

        PersonEntry person = new PersonEntry();
        person.setDn(dn);
        person.setUid("an");

        when(repository.findById(dn))
                .thenReturn(Optional.of(person));

        Optional<PersonEntry> result = service.findByDn("an");

        assertTrue(result.isPresent());
        assertEquals("an", result.orElseThrow().getUid());
        verify(repository).findById(dn);
        verifyNoMoreInteractions(repository);
    }

    @Test
    void newPersonHasNullIdBeforeRepositorySave() {
        PersonRepository repository = mock(PersonRepository.class);
        PersonDirectoryService service =
                new PersonDirectoryService(repository);

        service.createPerson("lan", "Le Thi Lan", "Le");

        var entity = org.mockito.ArgumentCaptor
                .forClass(PersonEntry.class);
        verify(repository).save(entity.capture());

        assertNull(entity.getValue().getDn());
        assertEquals("lan", entity.getValue().getUid());
        assertEquals("Le Thi Lan",
                entity.getValue().getCommonName());
        assertEquals("Le", entity.getValue().getSurname());
    }

    @Test
    void invalidUidDoesNotCallRepository() {
        PersonRepository repository = mock(PersonRepository.class);
        PersonDirectoryService service =
                new PersonDirectoryService(repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.createPerson("", "Lan", "Le"));

        verifyNoInteractions(repository);
    }
}
~~~

**Giới hạn của mock:** Mockito chỉ xác minh code của service. Nó **không** tạo proxy repository, phân tích derived query, ánh xạ ODM, xử lý TLS, kiểm tra schema hoặc LDAP ACL. Đặc biệt, test `dn=null` trước `save` **không chứng minh** ODM sẽ tính đúng DN trên server.

Muốn kiểm tra cơ chế thực sự của repository, dùng integration test với Spring context và LDAP test server phù hợp.

## 17. Integration test: đối chiếu Repository với Core

Dùng một LDAP server lab với namespace đã được cấp, ví dụ:

~~~text
ContextSource.base = dc=lab,dc=example,dc=org
OU                  = ou=people
Tài khoản test      = cn=app-writer,ou=services,dc=lab,dc=example,dc=org
DN entry test       = uid=lab-001,ou=people,dc=lab,dc=example,dc=org
~~~

Server lab cần schema phù hợp `inetOrgPerson`, kết nối LDAPS/StartTLS tin cậy và quyền create/read/update/delete chỉ trong OU lab. Không ghi vào directory sản xuất.

### Kịch bản A — tạo entity, đọc lại theo DN

1. Tạo `PersonEntry` mới với `dn=null`, `uid="lab-" + randomId`, `cn` và `sn` hợp lệ.
2. Gọi `repository.save(person)` trong Spring context thật.
3. Xác nhận `person.getDn()` được tính theo `uid=...,ou=people`.
4. Gọi `repository.findById(person.getDn())` để đọc lại.
5. Dùng `LdapTemplate.lookupContext(person.getDn())` để đối chiếu `uid`, `cn`, `sn` và DN từ Core.
6. Chỉ xóa entry test do chính test tạo, bảo đảm cleanup dùng DN hiện hành.

Ví dụ khung integration test (chỉ chạy khi đã cấu hình LDAP lab):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

@SpringBootTest
class PersonRepositoryIntegrationTest {

    @Autowired PersonRepository repository;
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void saveAndCoreLookupReferToSameEntry() {
        String uid = "lab-" + UUID.randomUUID()
                .toString().replace("-", "");

        PersonEntry person = new PersonEntry();
        person.setUid(uid);
        person.setCommonName("Lab Person");
        person.setSurname("Person");

        Name createdDn = null;
        try {
            PersonEntry saved = repository.save(person);
            createdDn = saved.getDn();
            assertNotNull(createdDn);

            PersonEntry reloaded = repository.findById(createdDn)
                    .orElseThrow();

            assertEquals(uid, reloaded.getUid());

            DirContextOperations viaCore =
                    ldapTemplate.lookupContext(createdDn);
            assertEquals(uid,
                    viaCore.getStringAttribute("uid"));
        } finally {
            if (createdDn != null) {
                repository.deleteById(createdDn);
            }
        }
    }
}
~~~

Đây là **khung minh họa**: chỉ dùng trên directory lab, phải chắc OU được cấp và lệnh cleanup chỉ tác động đúng entry test. Khi `save` thành công nhưng trả về lỗi sau khi server đã ghi, một cleanup chỉ dựa vào `createdDn != null` có thể chưa đủ; test hạ tầng thực cần cơ chế đối chiếu UID/định danh và dọn dữ liệu chưa chắc kết quả.

### Kịch bản B — truy vấn theo attribute

- Tạo hai entry có `cn` giống nhau nhưng UID khác nhau.
- Gọi `repository.findByCommonName(...)` và xác nhận trả cả hai.
- Gọi `findById(dn)` để đối chiếu rằng mỗi entry có DN riêng.
- Với input chứa dấu `*`/`(`/`)`, kiểm tra filter builder/binding không thay đổi ý nghĩa tìm kiếm.

### Kịch bản C — xác nhận lỗi

| Tình huống | Kỳ vọng |
| --- | --- |
| Thử tạo trùng DN | Conflict phù hợp, không tự overwrite |
| Account read-only gọi `save` | LDAP ACL từ chối |
| Thiếu `cn` hoặc `sn` | Server áp schema, operation lỗi |
| Tìm UID trong nhiều OU | Không giả định một kết quả duy nhất |
| Entity thiếu `@Id` đúng package | ODM/repository không hoạt động như mong muốn |
| `@DnAttribute(index)` khai báo sai | DN tính sai hoặc mapping không hợp lệ |
| Thay UID làm đổi RDN | Không coi là update attribute thông thường |
| Request bị timeout sau gửi Add | Không retry vô điều kiện |
| Gọi `findAll()` trên OU lớn | Đánh giá size/time/admin limit, không coi là paging |

### Kịch bản D — chứng minh Core có khả năng riêng

1. Tạo entry nhóm trong OU lab có hai thành viên.
2. Dùng `LdapTemplate.modifyAttributes(...)` gửi **ADD một** giá trị `member`.
3. Đọc lại bằng Core, xác nhận cả hai giá trị cũ **và** giá trị mới còn tồn tại.
4. Không dùng `repository.save(group)` để thay cả tập giá trị từ snapshot cũ khi chỉ muốn thêm một thành viên.

**Phân biệt hai cấp test:** unit test kiểm tra đường gọi và validation; integration test kiểm tra ODM, repository proxy, kết nối LDAP, schema, ACL và kết quả thật trên server.

## 18. Bài thực hành: chọn đúng tầng truy cập LDAP

Giả sử ứng dụng quản lý nhân viên có `ContextSource.base=dc=example,dc=org`, entity `PersonEntry` và repository:

~~~java
public interface PersonRepository
        extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

### Câu hỏi

1. `LdapRepository<PersonEntry, String>` có phải cách khai báo đúng không?
2. Trong LDAP repository, `findById` nhận kiểu nào?
3. Annotation `@Id` của entity cần thuộc package nào?
4. Muốn tìm mọi entry có `uid=an`, dùng `findById("an")` hay `findByUid("an")`?
5. Nếu cùng UID xuất hiện ở hai OU, `findByUid` có thể trả bao nhiêu entry?
6. Entity mới có `@DnAttribute(index=0)` và `@Id=null`: `save` có thể làm gì?
7. Vì sao gán DN ngay từ đầu rồi gọi `save` không được mặc định xem là Add?
8. Muốn thêm một giá trị `member` vào nhóm mà không xóa thành viên khác, nên dùng API nào?
9. Repository LDAP có hỗ trợ `Page<PersonEntry> findAll(Pageable)` như JPA không?
10. `findAll(LdapQuery)` là API của `CrudRepository` chung hay `LdapRepository`?
11. `@EnableLdapRepositories` có tự bảo đảm LDAP đã bật TLS và ACL hợp lệ không?
12. Vì sao test Mockito thành công chưa chứng minh repository proxy và LDAP schema đúng?

### Đáp án có giải thích

| Câu | Đáp án |
| --- | --- |
| 1 | Không; `LdapRepository` chỉ có một type parameter: `LdapRepository<PersonEntry>` |
| 2 | `javax.naming.Name` — DN, không phải UID thuần |
| 3 | `org.springframework.ldap.odm.annotations.Id` |
| 4 | `findByUid("an")` tìm theo attribute; `findById` cần DN |
| 5 | Có thể nhiều entry nếu scope và chính sách server cho phép |
| 6 | ODM có thể tính DN và repository đi theo đường tạo entry, nếu mapping hợp lệ |
| 7 | Implementation thường dựa trạng thái ID/mới-cũ; một DN đã gán có thể khiến save chọn update |
| 8 | `LdapTemplate.modifyAttributes(Name, ModificationItem[])` với `ADD_ATTRIBUTE` cho giá trị cụ thể |
| 9 | Không theo abstraction Spring Data repository LDAP hiện hành; dùng LDAP controls qua Core |
| 10 | Overload đặc thù của `LdapRepository<T>` |
| 11 | Không; phải cấu hình `ContextSource`, TLS, secret, service bind, LDAP ACL và quyền caller |
| 12 | Mock không chạy ODM mapping, query derivation, LDAP server, schema hoặc ACL |

### Bài tập lựa chọn kiến trúc

Chọn **Repository**, **Core**, hoặc **kết hợp**:

| Yêu cầu | Hướng phù hợp |
| --- | --- |
| Tra cứu một person theo DN cụ thể | Repository `findById` |
| Tìm người có UID cho trước | Repository derived query hoặc `LdapQuery` |
| Xây filter động theo nhiều tiêu chí | Repository `findAll(LdapQuery)` hoặc Core |
| Thêm đúng một member DN vào nhóm | Core `modifyAttributes` với ADD một giá trị |
| Search 100.000 entry theo trang và sort phía server | Core với Paged Results + Sort controls đã kiểm chứng |
| Rename user từ OU A sang OU B | Core rename/move với schema/ACL và kế hoạch tham chiếu |
| Đọc ODM entity rồi cập nhật email phổ biến | Repository `findById` + `save`, sau kiểm tra quyền |
| Đảm bảo TLS, audit, phân quyền | Kiến trúc và cấu hình tổng thể; không một repository method nào tự thay thế được |

## 19. Checklist ứng dụng Repository vào sản phẩm

- [ ] Hiểu kiến trúc **Spring Data LDAP Repository → ODM/Core → ContextSource → LDAP server**.
- [ ] Entity dùng `@Entry`, `org.springframework.ldap.odm.annotations.Id` với field kiểu `Name` và mapping attributes hợp lệ.
- [ ] Interface khai báo **`LdapRepository<T>`** một type parameter, không dùng kiểu ID `String`.
- [ ] Bật repository scanning bằng `@EnableLdapRepositories` hoặc cấu hình phù hợp.
- [ ] Kiểm tra repository dùng đúng bean `ldapTemplate`, ContextSource, URL, base DN và bind identity.
- [ ] Phân biệt query theo DN/`findById` và query theo attribute/`findByUid`.
- [ ] Với entity mới, biết chiến lược tính DN và `save` phát hiện mới/cũ; có integration test.
- [ ] Không mặc định `save` là atomic upsert và không đổi field RDN thiếu kiểm soát.
- [ ] Biết **LDAP Repository không hỗ trợ paging/sorting** như JPA; dùng controls qua Core khi cần.
- [ ] Dùng `LdapTemplate` hoặc `LdapClient` cho thao tác đặc thù, nhất là modify giá trị đa trị và rename.
- [ ] Dùng DN builder và filter builder đúng ngữ cảnh; không ghép chuỗi input nguy hiểm.
- [ ] Thực thi quyền nghiệp vụ, ACL LDAP, LDAPS/StartTLS, kiểm tra chứng chỉ và secret management.
- [ ] Không gọi `findAll`/`deleteAll` trên phạm vi lớn khi chưa đánh giá giới hạn và tác động.
- [ ] Có unit test service, integration test Spring repository/ODM/Core trên LDAP lab.
- [ ] Xử lý conflict, missing DN, schema errors, ACL failures và timeout không chắc kết quả.

## 20. Những điểm cần ghi nhớ

- **Spring Data LDAP Repository là lớp trừu tượng đặt trên Spring LDAP Core và ODM**, giúp giảm mã CRUD/query phổ biến, không thay đổi semantics của LDAP server.
- **`LdapRepository<T>` dùng DN kiểu `javax.naming.Name` làm ID**. Entity phải dùng annotation ODM của Spring LDAP, không phải JPA hoặc Spring Data `@Id`.
- **`@EnableLdapRepositories`** kích hoạt repository scanning; repository dùng `LdapTemplate`/`ContextSource` được cấu hình để truy cập directory.
- **`findById` là tra cứu DN; `findByUid` là tìm theo thuộc tính**, có thể trả nhiều entry nếu UID không được bảo đảm duy nhất theo scope.
- **`save(...)` không phải upsert tự động**. DN null, `@DnAttribute` và cơ chế phát hiện entity mới có ảnh hưởng lớn đến thao tác Add/Update.
- **Repository LDAP không hỗ trợ paging/sorting kiểu Spring Data**. Với Paged Results, Server-Side Sort, VLV, Modify DN hoặc sửa giá trị đa trị, thường phải dùng Core.
- **Schema, ACL, TLS, DN, filter escaping, timeout và concurrency vẫn là trách nhiệm của ứng dụng/server** dù repository interface rất ngắn.
- **Kiểm thử cả hai tầng**: mock để xác minh logic nghiệp vụ, LDAP lab để xác minh repository proxy, ODM mapping, ACL và dữ liệu thật.

### Tài liệu tham khảo

- [Spring LDAP — Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html)
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html)
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Data LDAP — EnableLdapRepositories API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html)
- [Spring Boot — LDAP Auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 2696 — Simple Paged Results](https://www.rfc-editor.org/rfc/rfc2696)
- [RFC 2891 — Server Side Sorting](https://www.rfc-editor.org/rfc/rfc2891)

