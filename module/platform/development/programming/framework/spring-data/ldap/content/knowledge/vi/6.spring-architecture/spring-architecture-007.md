# Cách Repository sử dụng hạ tầng Spring LDAP

## 1. Vấn đề kiến trúc: repository LDAP có thật sự tự kết nối directory?

Khi phát triển ứng dụng **Spring Data LDAP**, chúng ta thường khai báo một interface:

~~~java
public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

Sau đó chỉ việc inject và gọi:

~~~java
List<PersonEntry> people = personRepository.findByUid("alice");
~~~

Không có lớp `PersonRepositoryImpl` do lập trình viên viết, nhưng ứng dụng vẫn thực hiện **LDAP Search thật** và trả về đối tượng Java. Cách hoạt động này là kết quả phối hợp giữa **Spring Data repository infrastructure** và **Spring LDAP**:

- **Spring Data LDAP** phân tích interface, xây dựng repository proxy, nhận dạng thao tác CRUD và tạo truy vấn LDAP từ tên phương thức hoặc `@Query`.
- **Spring LDAP** cung cấp `LdapTemplate`/`LdapOperations`, bộ tạo filter, truy cập JNDI và **Object-Directory Mapping (ODM)** để chuyển LDAP entry thành Java object.
- **`ContextSource`** quản lý cách lấy `DirContext`/`LdapContext`, thông tin kết nối, bind identity và base DN.
- **LDAP server** thực thi Search, Add, Modify, Delete, kiểm tra schema, `objectClass` và quyền ACL.

Bài học giải thích đường đi của **một lần gọi repository từ Java tới LDAP server rồi quay trở lại**, cách Spring Boot lắp ráp những thành phần đó, và những giới hạn không thể suy ra từ giao diện repository quen thuộc của Spring Data JPA.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Vẽ được các tầng Spring Data LDAP → Spring LDAP → JNDI → LDAP server.
2. Giải thích vì sao interface `LdapRepository<T>` hoạt động mà không cần tự viết implementation.
3. Phân biệt `LdapRepositoryFactoryBean`, `LdapRepositoryFactory`, `SimpleLdapRepository`, `LdapTemplate`, `ObjectDirectoryMapper` và `LdapContextSource`.
4. Mô tả hành trình của `findById(Name)`, query method và `save(...)`.
5. Cấu hình Spring Boot hoặc `@EnableLdapRepositories` để repository sử dụng đúng `LdapTemplate`.
6. Biết khi nào chuyển xuống `LdapTemplate`, cách kiểm tra filter, DN, schema, ACL và các lỗi tích hợp.
7. Thiết kế integration test chứng minh repository và template cùng truy cập đúng directory.

> **Điểm mấu chốt:** Repository là một **lớp API và thực thi truy vấn** đặt trên Spring LDAP; nó không tự thay thế `LdapTemplate`, LDAP protocol hoặc việc quản trị directory.

## 2. Nhìn toàn bộ kiến trúc từ trên xuống

~~~mermaid
flowchart TD
    A["Controller / Batch / Business Service"] --> B["PersonRepository: interface Java"]
    B --> C["Spring Data repository proxy"]
    C --> D["Query method: tên method / @Query"]
    C --> E["SimpleLdapRepository: CRUD"]
    D --> F["Spring LDAP: LdapOperations / LdapTemplate"]
    E --> F
    F --> G["ODM: ObjectDirectoryMapper"]
    F --> H["ContextSource: LdapContextSource"]
    G --> F
    H --> I["JNDI: DirContext / LdapContext"]
    I --> J["LDAP server: base DN, schema, ACL"]
    J --> K["People / Groups / Other entries"]
~~~

Sơ đồ mô tả **trách nhiệm logic**, không phải một stack trace cố định trong mọi phiên bản. Chẳng hạn CRUD implementation có thể gọi các phương thức ODM của `LdapOperations`, còn query method đi qua phần tạo LDAP query trước khi nhờ Spring LDAP thực thi.

| Tầng | Thành phần tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Ứng dụng | Service, API, job | Quy tắc nghiệp vụ, giới hạn phạm vi tìm kiếm, phân quyền ứng dụng |
| Spring Data Commons | Repository metadata, proxy/factory infrastructure | Phát hiện interface, tạo proxy, phân phối lời gọi method |
| Spring Data LDAP | `LdapRepositoryFactoryBean`, `LdapRepositoryFactory`, `SimpleLdapRepository` | Nối repository vào LDAP operations, CRUD và query derivation |
| Spring LDAP ODM | `@Entry`, `@Id`, `@Attribute`, `ObjectDirectoryMapper` | Ánh xạ DN/attributes của entry thành Java object và ngược lại |
| Spring LDAP core | `LdapOperations`, `LdapTemplate`, `LdapQueryBuilder` | Thực hiện lookup/search/modify, quản lý callback và exception |
| Spring LDAP connection | `ContextSource`, `LdapContextSource` | Tạo LDAP context từ URL, base DN và bind credential |
| JNDI LDAP provider | `DirContext`, `LdapContext`, `Attributes` | Trao đổi các thao tác LDAP với server |
| Directory server | OpenLDAP, Active Directory, UnboundID, ... | Lưu entry và thực thi schema, ACL, matching rules, controls |

Cùng một module có thể dùng **repository cho các thao tác thông dụng** và **`LdapTemplate` cho thao tác cần kiểm soát chi tiết** mà không phải xây hai đường kết nối độc lập. Cả hai nên dùng cùng cấu hình `ContextSource` khi nhắm cùng directory.

## 3. Ranh giới giữa Spring Data LDAP và Spring LDAP

### 3.1. Spring Data LDAP: biến interface thành API truy cập dữ liệu

Spring Data LDAP nhận một interface như:

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
    List<PersonEntry> findByCommonNameStartingWith(String prefix);
}
~~~

Framework xử lý:

1. Đọc **metadata của interface**: entity `PersonEntry`, các phương thức kế thừa, các query methods.
2. Tạo **repository bean/proxy** khi Spring context khởi động.
3. Phân loại method: method CRUD đã có implementation nền, method query cần phân tích tên hoặc annotation.
4. Kết hợp metadata LDAP/ODM để xây yêu cầu truy vấn.
5. Ủy quyền thực thi cho **Spring LDAP operations**.
6. Trả kết quả kiểu `PersonEntry` hoặc collection/`Optional` tùy chữ ký method.

Lợi ích chính là giảm mã lặp và cung cấp API hướng mô hình miền, **không phải** đổi LDAP thành JPA hay JDBC.

### 3.2. Spring LDAP: thực thi LDAP operation

`LdapTemplate` cung cấp các phương thức như:

~~~java
ldapTemplate.lookup(relativeDn, attributesMapper);
ldapTemplate.search(base, filter, attributesMapper);
ldapTemplate.findByDn(relativeDn, PersonEntry.class);
ldapTemplate.create(personEntry);
ldapTemplate.update(personEntry);
ldapTemplate.delete(personEntry);
~~~

Nhóm thứ nhất thao tác với callback/JNDI attributes; nhóm thứ hai áp dụng **ODM mapping**. Ngoài ra còn có API `modifyAttributes`, `rename`, Search controls và xử lý context.

`LdapOperations` là **interface** mà `LdapTemplate` triển khai. Trong hạ tầng repository, phần thực thi mặc định **có thể nhận một `LdapOperations`**, nhờ vậy không cần mỗi repository tự quản lý kết nối hoặc tự map exceptions.

### 3.3. Spring LDAP ODM: không phải JPA entity mapping

Một LDAP entry có:

~~~text
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
~~~

Java class cần metadata từ **Spring LDAP ODM**:

- `@Entry`: base và các `objectClass` mà entity biểu diễn.
- `@Id`: trường **DN** kiểu `javax.naming.Name`.
- `@Attribute`: ánh xạ field Java sang tên LDAP attribute.
- `@DnAttribute`: ánh xạ thành phần của DN sang field khi cần.
- `@Transient`: field không được ánh xạ vào LDAP.

**Không dùng nhầm** `jakarta.persistence.Id`, JPA `@Entity` hoặc `org.springframework.data.annotation.Id` để thay thế các annotation ODM LDAP. Entity LDAP không tự sinh khóa số và không có bảng SQL hay quan hệ khóa ngoại như JPA.

## 4. Khi ứng dụng khởi động: Spring tạo repository bằng cách nào?

### 4.1. Thêm dependency đúng chức năng

Ví dụ Gradle Kotlin DSL dùng Spring Boot:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Starter này gom các thành phần cần cho kết nối Spring LDAP và Spring Data LDAP theo dependency management tương thích của Spring Boot.

Nếu chỉ dùng `spring-ldap-core`, ứng dụng có thể dùng `LdapTemplate`, nhưng **không nên suy rằng repository Spring Data LDAP tự xuất hiện** nếu thiếu dependency và cấu hình kích hoạt repository.

### 4.2. Spring Boot lắp ráp những bean nào?

Ví dụ `application.yml`:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.example.org:636"
    base: "dc=example,dc=org"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Trong ứng dụng đáp ứng điều kiện auto-configuration của phiên bản Boot, framework có thể thiết lập:

~~~text
spring.ldap.* properties
    |
    +--> LdapContextSource / ContextSource
    |       - URL, base DN, bind identity
    |       - cấu hình TLS, môi trường JNDI
    |
    +--> LdapTemplate bean ("ldapTemplate")
            |
            +--> ObjectDirectoryMapper cho ODM
                    |
                    +--> Repository infrastructure dùng LdapTemplate
~~~

Spring Boot còn hỗ trợ **tự động quét repository và entity** trong các package cấu hình thích hợp. Các bean tự khai báo có thể khiến auto-configuration **back off**; không nên dựa vào hai cơ chế tự động/tự cấu hình mà không xác minh bean thực tế.

Cụ thể:

- `spring.ldap.urls` là endpoint LDAP; không phải base DN.
- `spring.ldap.base` là **base DN ở client**; không tạo suffix/OU trên server.
- `spring.ldap.username`/`password` là **danh tính bind của ứng dụng**, không phải tài khoản của người dùng đang được tìm.
- Khi cấu hình `ldaps://`, Java cần tin cậy CA và xác minh hostname của server.
- Giá trị mật khẩu phải được cấp từ secret store hoặc runtime environment, không commit vào Git.

### 4.3. Khi nào cần `@EnableLdapRepositories`?

Nếu repository nằm trong phạm vi package auto-scan, Spring Boot thường đã kích hoạt repository support. Khi cần kiểm soát rõ package hoặc nhiều LDAP context, có thể khai báo:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.directory.repository"
)
public class LdapRepositoryConfiguration {
}
~~~

`@EnableLdapRepositories` yêu cầu Spring **tìm các interface repository phù hợp trong package** và đăng ký bean proxy.

**Chú ý:**

- Đây là cách cấu hình **thay thế hoặc bổ sung có chủ đích** cho phạm vi auto-configuration; tránh đăng ký trùng cùng một repository.
- `basePackages` xác định nơi quét **Java repository interface**, không phải LDAP search base như `ou=people`.
- `@EntityScan` có thể giúp cấu hình phạm vi quét entity khi package không nằm trong cấu hình mặc định; **không** làm LDAP server tự tạo entry.
- Không cần đặt `@Repository` lên mọi interface khi nó đã được hạ tầng Spring Data phát hiện và đăng ký.

### 4.4. Factory, proxy và implementation nền

Trong Spring Data LDAP, những thành phần đáng biết là:

| Thành phần | Vai trò |
| --- | --- |
| `LdapRepositoryFactoryBean` | Spring `FactoryBean` tích hợp đăng ký repository vào container |
| `LdapRepositoryFactory` | Xây dựng repository proxy và lựa chọn phần thực thi cho interface |
| `SimpleLdapRepository<T>` | Implementation nền cho các method CRUD và truy vấn LDAP cụ thể |
| `LdapMappingContext` | Metadata liên quan đến domain class cho hạ tầng Spring Data LDAP |
| `ObjectDirectoryMapper` | ODM mapping giữa annotated Java class và LDAP attributes/DN |
| `LdapOperations` (`LdapTemplate`) | Cung cấp các thao tác LDAP được thực thi và quản lý context |

Theo API hiện hành, `SimpleLdapRepository<T>` có constructor về mặt khái niệm:

~~~java
SimpleLdapRepository(
    LdapOperations ldapOperations,
    ObjectDirectoryMapper odm,
    Class<T> entityType
)
~~~

Đây là **chữ ký framework để giải thích dependency**, không phải code mà ứng dụng cần gọi bằng `new`. Constructor cho thấy repository implementation phụ thuộc vào **Spring LDAP operations, ODM mapper và loại entity**. Một repository interface không phải tự có socket/JNDI riêng cho mỗi method.

`LdapRepositoryFactory` còn giải quyết các query methods và các repository fragments bổ sung khi được cấu hình. Tên class/lớp mở rộng có thể thay đổi theo phiên bản; phần ổn định là **phân chia trách nhiệm** giữa repository infrastructure và Spring LDAP.

## 5. Khai báo entity và repository đầy đủ

### 5.1. Entity với DN và thuộc tính

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

    public PersonEntry() { }

    public Name getDn() { return dn; }
    public void setDn(Name value) { dn = value; }

    public String getUid() { return uid; }
    public void setUid(String value) { uid = value; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String value) {
        commonName = value;
    }

    public String getSurname() { return surname; }
    public void setSurname(String value) {
        surname = value;
    }

    public String getEmail() { return email; }
    public void setEmail(String value) { email = value; }
}
~~~

Ở đây:

- `PersonEntry` mô tả một entry có `objectClass=inetOrgPerson`.
- Trường `dn` là **định danh repository**; không nhất thiết là `uid`.
- `@Attribute(name="cn")` giúp property `commonName` lấy từ LDAP `cn`, thay vì tìm thuộc tính có tên `commonName`.
- `sn` thường là một thuộc tính bắt buộc theo schema của `person`, cần có khi tạo entry mới.
- `@Entry.base="ou=people"` xác định nhánh cho loại entity này, còn `ContextSource.base="dc=example,dc=org"` xác định base chung của client.
- Các field thuộc tính cần được kiểm tra theo schema và quyền đọc thực tế; một field `null` không mặc định là lỗi mapping.

**DN ví dụ:**

~~~text
DN đầy đủ trên server:
  uid=alice,ou=people,dc=example,dc=org

DN thường dùng tương đối với ContextSource base:
  uid=alice,ou=people
~~~

Đừng tự ghép suffix vào DN tương đối nếu API đã đặt base; cũng không dùng `String.split(",")` để xử lý DN có escape. Khi dựng DN từ input, dùng `LdapName`/`LdapNameBuilder` đúng mục đích.

### 5.2. Repository interface

~~~java
import java.util.List;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;

public interface PersonRepository extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);

    List<PersonEntry> findByCommonNameStartingWith(String prefix);

    @Query("(&(objectClass=inetOrgPerson)(mail=?0))")
    List<PersonEntry> findByMailAddress(String mail);
}
~~~

`LdapRepository<T>` nhận **một type parameter** là entity; ID được cố định là `javax.naming.Name`. Đừng viết như JPA `JpaRepository<PersonEntry, Long>`, hoặc giả định `findById("alice")` sẽ tìm theo `uid`.

Ở đây:

- `findByUid` là **derived query**: Spring Data LDAP đọc `Uid` như property Java, rồi xây điều kiện LDAP tương ứng.
- `findByCommonNameStartingWith` biểu diễn ý nghĩa **substring/prefix**; không phải equality.
- `@Query` là filter LDAP tĩnh có placeholder `?0`; tham số trực tiếp được framework **mã hóa** theo quy tắc filter.
- Nếu cần hỗ trợ một `LdapQuery` được xây dựng động trong ứng dụng, `LdapRepository` có các phương thức như `findAll(LdapQuery)` và `findOne(LdapQuery)` bên cạnh CRUD.
- Các kiểu query, tên keyword, escaping, hành vi matching rule phải kiểm chứng theo **version Spring Data LDAP và directory server thực tế**.

## 6. Luồng `findById(Name)`: tra đúng DN qua Spring LDAP

Giả sử service đã inject repository:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import java.util.Optional;

public Optional<PersonEntry> findAlice(PersonRepository repository)
        throws Exception {

    Name id = new LdapName("uid=alice,ou=people");
    return repository.findById(id);
}
~~~

Luồng logic:

~~~mermaid
sequenceDiagram
    participant S as Application service
    participant R as Repository proxy
    participant Impl as SimpleLdapRepository
    participant L as LdapOperations / LdapTemplate
    participant C as ContextSource / JNDI
    participant D as LDAP server
    S->>R: findById(Name)
    R->>Impl: Điều phối CRUD theo metadata entity
    Impl->>L: Lookup/ODM theo DN
    L->>C: Lấy LDAP context
    C->>D: LDAP read tại DN đã xác định
    D-->>C: Entry + attributes hoặc lỗi
    C-->>L: Kết quả JNDI
    L->>L: ObjectDirectoryMapper → PersonEntry
    L-->>Impl: Object hoặc trạng thái không tìm thấy
    Impl-->>R: Optional<PersonEntry>
    R-->>S: Kết quả
~~~

Cần lưu ý:

1. **`findById` tìm theo DN**, không thực hiện search toàn directory theo `uid`.
2. `Name` được hiểu theo quy ước base của `ContextSource`; đối chiếu với DN thực trên server.
3. Schema và `@Entry` quyết định entry có phù hợp entity để ánh xạ không.
4. `ContextSource` quyết định account bind/TLS; repository không tự mở quyền đọc riêng.
5. Spring LDAP thực hiện việc đọc/ánh xạ; không có entity manager hay SQL query.
6. Không phải mọi lỗi được chuyển thành `Optional.empty()`: mất kết nối, bind sai, thiếu quyền hoặc lỗi schema phải được xử lý/quan sát riêng.

Nếu chỉ có giá trị `uid` nhưng **không biết DN chính xác** (người có thể ở nhiều OU), cần dùng `findByUid(...)` hoặc `LdapTemplate.search(...)`, không tự giả định vị trí của entry.

## 7. Luồng query method: từ tên phương thức tới LDAP Search

Lời gọi:

~~~java
List<PersonEntry> people = personRepository.findByUid("alice");
~~~

khác `findById(...)`: framework không có DN cần đọc trực tiếp. Thay vào đó nó tạo **LDAP Search** dựa trên mapping entity và điều kiện của tên method.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant P as Repository proxy
    participant Q as Spring Data LDAP query infrastructure
    participant T as LdapTemplate
    participant J as JNDI
    participant D as LDAP server
    S->>P: findByUid("alice")
    P->>Q: Phân tích method metadata + tham số
    Q->>Q: Xây filter từ property uid
    Q->>T: LDAP Search trong base của entity
    T->>J: Search + context được cấu hình
    J->>D: SearchRequest(base, scope, filter)
    D-->>J: SearchResultEntry + ResultDone
    J-->>T: Attributes, DN
    T->>T: ODM → List<PersonEntry>
    T-->>Q: Các entity phù hợp
    Q-->>P: List<PersonEntry>
    P-->>S: List<PersonEntry>
~~~

Hình thức filter có thể tương tự:

~~~text
(&(objectClass=inetOrgPerson)(uid=alice))
~~~

Đây là **diễn giải để hiểu nguyên lý**, không phải chuỗi filter bắt buộc giống hệt trên mọi version. ODM/repository có thể bổ sung các điều kiện `objectClass` hoặc base khác dựa trên `@Entry`.

### 7.1. Từ property Java sang LDAP attribute

Tên method thường mô tả **property Java**:

~~~java
findByCommonNameStartingWith("Ali")
~~~

Vì field `commonName` có `@Attribute(name="cn")`, query cần nhắm **LDAP attribute `cn`**, không phải thuộc tính tên `commonName`.

Nếu đổi property Java mà không đổi method query hoặc bỏ `@Attribute`, query có thể không được tạo đúng hoặc không còn tìm thấy entry. Kiểm tra cả:

- Java property trong tên method.
- Annotation ODM trên field.
- LDAP schema có thuộc tính được gọi.
- `objectClass` và nhánh search.
- Matching rule của directory.

### 7.2. Parameter binding và LDAP injection

Một anti-pattern:

~~~java
// SAI: Không nối input người dùng thành raw LDAP filter.
String filter = "(uid=" + requestUid + ")";
~~~

Với input có `*`, `(`, `)` hoặc ký tự escape, filter có thể đổi ý nghĩa hoặc trở thành LDAP injection.

Khi dùng query method và direct-bound parameter của `@Query`, Spring Data LDAP có cơ chế encode giá trị. Với truy vấn cấp thấp, dùng `LdapQueryBuilder`/`EqualsFilter`:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery ldapQuery = query()
    .base("ou=people")
    .where("uid").is(requestUid);
~~~

Trong code thực tế cần import `org.springframework.ldap.query.LdapQuery`. `.is(...)` xem tham số như **giá trị equality**, còn `.like(...)` và một số encoder cho phép wildcard theo **ý định truy vấn**. Cần phân biệt dấu `*` là **dữ liệu literal** với wildcard do ứng dụng chủ ý tạo.

Với `@Query`, tránh đưa dữ liệu chưa encode vào **SpEL/property placeholder**; những giá trị đó không được mã hóa tự động giống tham số bind trực tiếp. Không giả định mọi cách tạo query đều có mức an toàn như nhau.

## 8. Luồng CRUD: repository nhờ ODM thực hiện thao tác nào?

`SimpleLdapRepository` triển khai các thao tác quen thuộc như `save`, `findById`, `existsById`, `findAll`, `count`, `deleteById`. Về bản chất, chúng phải được quy về các thao tác LDAP với DN và entry.

| Repository method | Ý nghĩa ở tầng LDAP | Điều cần kiểm tra |
| --- | --- | --- |
| `findById(Name)` | Đọc entry theo DN | Base DN, entry tồn tại, ACL read |
| `findAll()` | Tìm các entry phù hợp entity | Scope, `objectClass`, limits; có thể tốn chi phí lớn |
| `findByUid(...)` | Search với filter theo attribute | Mapping property, escaping, matching rule |
| `existsById(Name)` | Kiểm tra entry có thể được quan sát theo DN | Không đồng nghĩa “không tồn tại” nếu ACL chặn |
| `save(entity)` | Tạo hoặc cập nhật theo trạng thái entity/DN và quy tắc ODM | Schema, RDN, identity, quyền Add/Modify |
| `deleteById(Name)` | Xóa entry theo DN phù hợp | Quyền delete; tham chiếu nhóm/OU không cascade như JPA |
| `saveAll(...)` | Áp dụng lưu nhiều entity theo hợp đồng repository | **Không** tự tạo transaction LDAP nhiều entry |

**`save()` không phải JPA `merge()` với mọi bảo đảm như optimistic locking hay cascade.** Một LDAP entry có vị trí DN cụ thể và thuộc tính ràng buộc schema. Muốn tạo entry mới, entity cần DN đúng hoặc metadata `@DnAttribute` đủ để ODM tính DN; muốn sửa, phải hiểu hành vi cập nhật/định danh của phiên bản đang dùng.

### 8.1. Tạo entry bằng ODM có DN xác định

Ví dụ minh họa một entity mới:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

PersonEntry alice = new PersonEntry();

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "alice")
    .build();

alice.setDn(dn);
alice.setUid("alice");
alice.setCommonName("Alice Nguyen");
alice.setSurname("Nguyen");
alice.setEmail("alice@example.org");

// Thực hiện chỉ trên directory thử nghiệm hoặc nhánh được cấp phép.
PersonEntry stored = personRepository.save(alice);
~~~

Các điều kiện tiên quyết:

- Parent `ou=people,dc=example,dc=org` **đã tồn tại**.
- Server hỗ trợ các lớp `inetOrgPerson`, `person`, ... và nhận thuộc tính theo schema.
- Tài khoản bind có quyền **add** cho entry mới.
- Định danh `uid=alice` chưa bị dùng ở DN mục tiêu.
- Không dùng `save` như cam kết “tạo hoặc ghi đè tùy ý” khi không rõ **entity mới/đã tồn tại**; cần test hợp đồng thực tế và dùng API Add/Update rõ ràng nếu nghiệp vụ yêu cầu.

Nếu cần chỉ sửa một thuộc tính thay vì lưu toàn bộ entity, `LdapTemplate.modifyAttributes(...)` cho phép nhắm đúng attribute.

### 8.2. Sửa một thuộc tính bằng `LdapTemplate`

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public void changeMail(
        LdapTemplate template,
        Name relativeDn,
        String newMail) {

    ModificationItem[] changes = {
        new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newMail)
        )
    };

    template.modifyAttributes(relativeDn, changes);
}
~~~

Ví dụ này cho thấy **repository và template có thể phối hợp**: repository đọc đối tượng miền, còn template xử lý một thao tác Modify cần kiểm soát cụ thể. Không tự sửa entry production trong test.

### 8.3. Không có cascade và transaction JPA mặc định

LDAP operation `Modify` trên **một entry** có thể có bảo đảm nguyên tử ở phía server theo giao thức, nhưng chuỗi thao tác trên **nhiều entry** không tự trở thành một transaction.

Ví dụ:

~~~text
1. Create uid=alice,ou=people
2. Modify cn=developers,ou=groups để thêm Alice
3. Modify cn=reviewers,ou=groups để thêm Alice
~~~

Nếu bước 3 thất bại, hai bước đầu có thể đã thành công. `@Transactional` của Spring dùng cho database không tự biến LDAP thành transaction ACID nhiều entry. Một số cơ chế transaction/compensating transaction có giới hạn riêng và không thay thế cam kết từ server.

Thiết kế phù hợp hơn là phân biệt **trạng thái đích**, thực hiện các thao tác idempotent khi có thể, đối soát sau lỗi và có quy trình bù trừ.

## 9. `ObjectDirectoryMapper` chuyển entry LDAP thành Java object

Khi LDAP server trả một entry, Spring LDAP phải biến:

~~~text
DN = uid=alice,ou=people
objectClass = top, person, organizationalPerson, inetOrgPerson
uid = alice
cn = Alice Nguyen
sn = Nguyen
mail = alice@example.org
~~~

thành:

~~~text
PersonEntry {
    dn = Name("uid=alice,ou=people"),
    uid = "alice",
    commonName = "Alice Nguyen",
    surname = "Nguyen",
    email = "alice@example.org"
}
~~~

`ObjectDirectoryMapper` là thành phần ODM chịu trách nhiệm ánh xạ theo metadata `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`. Spring LDAP còn hỗ trợ `ConversionService` để chuyển dữ liệu không phải chuỗi đơn giản.

### 9.1. DN và thuộc tính không phải cùng loại dữ liệu

- **DN** là tên phân cấp của entry. `@Id Name` không tương đương một LDAP attribute `uid`.
- **`uid`** là một attribute và có thể là thành phần RDN trong DN.
- **`cn`, `sn`, `mail`** là attribute của entry.
- **`objectClass`** mô tả schema và loại entry; nó có thể ảnh hưởng filter, khả năng tạo entry và việc ODM chấp nhận kết quả.

Ví dụ người dùng chuyển OU:

~~~text
Trước: uid=alice,ou=people,dc=example,dc=org
Sau:   uid=alice,ou=contractors,dc=example,dc=org
~~~

Nếu chỉ dùng DN làm khóa cục bộ, ứng dụng có thể coi Alice là hai entry khác nhau. Khi cần nhận diện qua rename, hãy tìm một **stable ID** mà directory mục tiêu cung cấp, ví dụ `entryUUID` hoặc `objectGUID` theo quy tắc vendor, không tự giả định `uid` bất biến toàn cục.

### 9.2. Chuyển kiểu và thuộc tính tùy chọn

LDAP `GeneralizedTime` có thể tới JNDI dưới dạng `String`, còn `jpegPhoto` thường là `byte[]` nếu provider nhận biết thuộc tính nhị phân.

~~~java
@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY
)
private byte[] photo;
~~~

Với converter tùy chỉnh, cần kiểm tra cấu hình `ObjectDirectoryMapper` được chính `LdapTemplate`/repository sử dụng. Việc đăng ký một converter ở chỗ khác không đảm bảo repository đã dùng đúng mapping context trong các cấu hình custom.

Nếu một field không có giá trị:

1. Kiểm tra raw LDAP entry bằng `ldapsearch`.
2. Kiểm tra request đã yêu cầu attribute hay chưa.
3. Kiểm tra quyền bind/ACL.
4. Dùng `LdapTemplate.lookup` với `AttributesMapper` để biết runtime type.
5. Kiểm tra annotation/field type và converter của ODM.
6. Kiểm tra service/DTO có vô ý bỏ field hay không.

Đừng tự biến mọi lỗi đọc binary/timestamp thành `null` vì sẽ che mất nguyên nhân.

## 10. `LdapTemplate` quản lý LDAP context như thế nào?

Đây là phần hạ tầng quan trọng mà repository **được hưởng nhưng không thường hiển thị**.

### 10.1. `ContextSource` tạo kết nối theo bind identity

Trong mô hình phổ biến:

~~~text
LdapTemplate / LdapOperations
       |
       v
ContextSource.getReadOnlyContext()/getReadWriteContext()
       |
       v
JNDI LDAP context đã kết nối và bind
       |
       v
LDAP server áp dụng ACL
~~~

`LdapContextSource` quản lý base DN và môi trường JNDI. Thông tin kết nối thường đến từ `spring.ldap.*` hoặc bean cấu hình riêng.

LDAP **bind** là xác thực danh tính kết nối. Đừng nhầm với method `ldapTemplate.bind(...)` của Spring LDAP dùng để **tạo entry** trong directory. Cùng từ “bind” nhưng nghĩa khác nhau trong ngữ cảnh ứng dụng.

### 10.2. Mẫu Template quản lý tài nguyên và exceptions

Khi gọi một phép Search, `LdapTemplate` chịu trách nhiệm các phần cơ sở hạ tầng thường lặp lại trong JNDI trực tiếp:

1. Lấy context thích hợp từ `ContextSource`.
2. Thiết lập request/search controls nếu cần.
3. Thực hiện JNDI lookup/search/modify.
4. Duyệt `NamingEnumeration` và gọi mapper/callback.
5. Giải phóng resource/context theo vòng đời.
6. Chuyển các lỗi JNDI phù hợp thành **exception hierarchy của Spring LDAP**.

Mã service dùng repository thường **không phải tự `close()` từng `DirContext`**; nhưng ứng dụng phải xử lý timeout, lỗi quyền, kết nối đứt và trường hợp kết quả bị giới hạn.

Lưu ý: ngoại lệ LDAP có thể mang thông tin nhạy cảm. Không ghi bind password, DN/thuộc tính người dùng chưa được phép hoặc dữ liệu binary vào log.

### 10.3. Pooling và reuse connection

Mỗi method repository không nhất thiết tương đương “một TCP connection mới”; cách reuse được quyết định bởi `ContextSource`, pooling, connection factory và cấu hình môi trường.

Việc thêm `PooledContextSource` có thể giảm chi phí kết nối trong một số trường hợp, nhưng cũng làm tăng độ phức tạp:

- Connection không được tái sử dụng khi trạng thái bind/TLS không còn phù hợp.
- Cần health check, timeout, giới hạn pool và cơ chế phát hiện connection chết.
- Paged Results Control có thể cần **cùng LDAP connection** giữa các trang.
- StartTLS và cơ chế xác thực có trạng thái đòi hỏi kiểm tra tương thích với pooling.
- Không nên mở connection pool khi chưa đo latency và nhu cầu thực tế.

**Repository không tự chịu trách nhiệm giải quyết mọi vấn đề vòng đời kết nối.** Cấu hình hạ tầng LDAP phải nhất quán cho tất cả thành phần dùng cùng source.

## 11. Khi nào dùng `LdapTemplate` thay vì chỉ dùng Repository?

Repository hữu ích cho CRUD và những query method có hợp đồng rõ ràng. `LdapTemplate` phù hợp khi nghiệp vụ cần quyền kiểm soát LDAP Search/Modify sâu hơn.

| Yêu cầu | Ưu tiên | Lý do |
| --- | --- | --- |
| Lấy entry bằng DN | Repository `findById(Name)` | API miền đơn giản |
| Tìm theo `uid`, `cn`, `mail` | Derived repository query hoặc `@Query` | Định nghĩa hợp đồng truy vấn sát entity |
| Truy vấn filter phức tạp theo scope/time limit | `LdapTemplate` + `LdapQueryBuilder` | Kiểm soát cụ thể Search |
| Chỉ lấy vài attribute, không map cả entity | `LdapTemplate` + `AttributesMapper` | Giảm dữ liệu và tránh mapping field không cần |
| Chỉ sửa một thuộc tính | `LdapTemplate.modifyAttributes` | Không cần lưu lại toàn bộ entity |
| Rename/Move DN | `LdapTemplate.rename` hoặc ODM API phù hợp | Thao tác LDAP ModifyDN rõ ràng |
| Paged Results Control | `LdapTemplate` + `DirContextProcessor` | Repository LDAP không cung cấp `Pageable` như JPA |
| Server-side sort/controls tùy chọn | API Spring LDAP phù hợp | Cần OID, response controls và khả năng server |
| Xác minh bind/authentication riêng | Thành phần LDAP auth/Spring Security thích hợp | Repository tìm entry **không tự xác thực user** |

Theo tài liệu Spring Data LDAP, **paging và sorting không được hỗ trợ cho LDAP repositories theo kiểu repository phổ thông**. Không mặc định nhận `Page<PersonEntry>` hay `Sort` như khi dùng database SQL.

Khi cần quét tập lớn, xem xét LDAP **Simple Paged Results Control** (RFC 2696) trên server hỗ trợ và dùng `LdapTemplate` với processor tương ứng; cookie paging không phải offset SQL.

## 12. Mẫu phối hợp repository và template trong một service

Ví dụ nghiệp vụ: tìm một người theo UID, rồi chỉ cập nhật `mail` nếu account có quyền. Service có thể dùng cả hai API:

~~~java
import java.util.List;

import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonDirectoryService {

    private final PersonRepository repository;
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(
            PersonRepository repository,
            LdapTemplate ldapTemplate) {
        this.repository = repository;
        this.ldapTemplate = ldapTemplate;
    }

    public List<PersonEntry> findByUid(String uid) {
        return repository.findByUid(uid);
    }

    public void updateMail(Name relativeDn, String newMail) {
        ModificationItem change = new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", newMail)
        );

        ldapTemplate.modifyAttributes(relativeDn, new ModificationItem[]{
            change
        });
    }
}
~~~

Ưu điểm:

- Business service giữ trách nhiệm **xác thực request, phân quyền nghiệp vụ, validate email và kiểm soát DN**.
- Repository thể hiện truy vấn theo model `PersonEntry`.
- Template xử lý Modify chọn lọc tại đúng DN.
- Nếu cả hai dùng cùng `ContextSource`, chúng chia sẻ cấu hình endpoint/base/TLS/bind account.

**Không coi ví dụ là API có thể ghi tùy ý vào production**: phải kiểm tra `relativeDn` thuộc OU được phép, validate `newMail`, tránh caller cung cấp bất kỳ DN nào, và dùng tài khoản có quyền Modify tối thiểu.

### 12.1. Hai cách đọc cùng một entry để đối chiếu

Trong một integration test có Alice:

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

Name aliceDn = new LdapName("uid=alice,ou=people");

PersonEntry fromRepository = repository.findById(aliceDn)
    .orElseThrow();

PersonEntry fromTemplate =
    ldapTemplate.findByDn(aliceDn, PersonEntry.class);

// Cùng DN và cùng schema/ACL: các field cơ bản nên thống nhất.
assertThat(fromRepository.getUid())
    .isEqualTo(fromTemplate.getUid());

assertThat(fromRepository.getCommonName())
    .isEqualTo(fromTemplate.getCommonName());
~~~

Đây là **đoạn đặt trong test** có `repository`, `ldapTemplate` và `assertThat` được khai báo/import tương ứng. Nó giúp kiểm tra tính nhất quán giữa repository infrastructure và Spring LDAP ODM.

Nếu repository trả Alice nhưng `LdapTemplate` đọc server khác, nguyên nhân có thể do **hai context sources**, `@EnableLdapRepositories(ldapTemplateRef=...)` hoặc bean custom, chứ không phải lỗi filter.

## 13. Khi có nhiều LDAP directory hoặc nhiều `LdapTemplate`

Ứng dụng có thể kết nối đồng thời đến:

- Directory nhân viên nội bộ.
- Directory đối tác.
- Một directory thử nghiệm/đồng bộ riêng.

Mỗi directory có thể có **base DN, schema, bind account và TLS khác nhau**. Khi ấy, không nên để Spring tự chọn nhầm `LdapTemplate`.

`@EnableLdapRepositories` có thuộc tính `ldapTemplateRef` để chỉ rõ bean dùng cho nhóm repository:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
    basePackages = "com.example.internal.repository",
    ldapTemplateRef = "internalLdapTemplate"
)
public class InternalLdapRepositoryConfiguration {
}
~~~

Ở đây `internalLdapTemplate` phải là tên **bean `LdapTemplate` đã được cấu hình riêng** cho directory nội bộ. Phần tạo hai `ContextSource` và hai `LdapTemplate` được tách khỏi ví dụ để người học tập trung vào cách repository chọn dependency.

Cần bảo đảm:

1. Không auto-scan cùng interface ở hai cấu hình repository.
2. `ldapTemplateRef` trỏ đúng bean; không chỉ đặt tên đẹp mà bỏ qua bean registration.
3. Entity và repository áp dụng đúng base/schema của directory mục tiêu.
4. Một service không vô tình dùng repository của directory A với template của directory B.
5. Các credential và CA/truststore được quản lý độc lập theo môi trường.
6. Integration test xác nhận kết nối thật tới endpoint dự kiến.

Spring Boot có thể tự cấu hình một `ContextSource` mặc định; khi khai báo thêm custom contexts, cần hiểu điều kiện bean, `@Primary` và `@Qualifier`. Không dùng `@Primary` để che cấu hình mơ hồ khi repository cần rõ directory.

## 14. Ranh giới giao dịch, nhất quán và phân quyền

### 14.1. Repository abstraction không thêm thuộc tính ACID

Một phương thức repository `saveAll(...)` nhìn giống thao tác database, nhưng LDAP có đặc điểm khác:

- DN là vị trí phân cấp; một lần rename/move thay đổi tên entry.
- LDAP Modify của một entry không đồng nghĩa **transaction nhiều entry**.
- Group membership thường lưu ở **entry nhóm**, không nhất thiết ở entry user.
- Dữ liệu cập nhật trên node này có thể xuất hiện chậm trên replica khác.
- Delete user không có cascade thống nhất cho mọi server.
- `@Transactional` Spring trong ứng dụng không tự biến tất cả LDAP thao tác thành một transaction database.

Khi cập nhật user và group trong cùng luồng nghiệp vụ, cần **thao tác có thứ tự, idempotency, audit, đối soát và bù trừ**. Không khẳng định “repository đã lưu thành công” nghĩa là toàn bộ các entry liên quan đã nhất quán.

### 14.2. Repository abstraction không vượt qua schema hoặc ACL

Directory server vẫn áp dụng:

- **Schema:** `objectClass`, MUST/MAY attributes, single/multivalue và syntax.
- **ACL:** quyền search/read/compare/add/modify/delete của bind identity.
- **Naming rules:** parent DN tồn tại, RDN hợp lệ, ràng buộc uniqueness tại DN.
- **Server limits:** số kết quả, thời gian tìm kiếm, control được hỗ trợ.
- **Security:** LDAPS/StartTLS, certificate, bind/account policy.

Ví dụ `repository.save(person)` có thể thất bại vì thiếu `sn` hoặc bind account chỉ có read access. Repository không tự thêm thuộc tính bắt buộc còn thiếu hoặc nâng quyền ghi.

### 14.3. Phân biệt quyền LDAP và quyền ứng dụng

Một service account LDAP có thể đọc được thông tin nhóm `cn=admins`, nhưng điều đó **không đồng nghĩa user gọi API đã được xác thực hoặc được cấp vai trò admin**.

Những tầng cần tách:

~~~text
LDAP bind identity:
  Ứng dụng được phép tìm và sửa entry nào?

End-user authentication:
  Người dùng đã được xác minh danh tính chưa?

Application authorization:
  Người dùng được phép gọi chức năng nào?
~~~

Spring Data LDAP repository **không tự thực hiện toàn bộ authentication/authorization flow**. Khi dùng group membership cho quyền, cần lấy danh tính user từ nguồn đã xác thực, kiểm tra nested groups/ACL theo schema và có chính sách fail-safe khi LDAP không khả dụng.

## 15. Quan sát lỗi: exception xuất hiện ở tầng nào?

Khi một repository method thất bại, có thể đi ngược từ triệu chứng để tìm tầng cần kiểm tra:

| Triệu chứng | Tầng nghi vấn | Kiểm tra |
| --- | --- | --- |
| Spring không inject được `PersonRepository` | Repository registration/scan | Dependency, `@EnableLdapRepositories`, package scan |
| Không thấy bean `ldapTemplate` | Spring LDAP/Boot config | Starter, `ContextSource`, bean definitions và auto-config conditions |
| `NoSuchBeanDefinition` hoặc nhầm template | Bean wiring | `ldapTemplateRef`, `@Qualifier`, số lượng template |
| `findById` rỗng hoặc báo not found | DN/ContextSource base | DN tương đối so với suffix, tồn tại entry, ACL |
| `findByUid` rỗng | Query mapping/filter/scope | `@Entry`, `@Attribute`, filter, search base |
| `cn` raw có nhưng `commonName` null | ODM | `@Attribute(name="cn")`, conversion, projection |
| `objectClassViolation` | LDAP server schema | Thuộc tính MUST, `objectClass`, ràng buộc syntax |
| `invalidCredentials` (LDAP 49) | Bind identity/secret | DN/password, account state, credential rotation |
| `insufficientAccessRights` (LDAP 50) | Server ACL | Quyền của service account theo OU/attribute |
| `CommunicationException` / timeout | Connection/network | URL, firewall, DNS, port, timeout, server readiness |
| TLS/PKIX hoặc hostname verification | Kết nối bảo mật | CA chain, SAN, truststore, LDAPS/StartTLS |
| Query bị cắt hoặc vượt size limit | Search/server limits | Filter rộng, scope, controls, paging |
| Hai thao tác ghi thành công một phần | Consistency/multi-entry | Retry, bù trừ, reconciliation |

Lưu ý một kết quả Search rỗng **không phải lúc nào cũng chứng minh entry không tồn tại**. ACL, base, scope, filter và replication đều có thể ảnh hưởng quan sát. Không bắt mọi exception rồi trả `Optional.empty()` vì sẽ che lỗi hạ tầng.

### Cách debug có cấu trúc

1. Xác nhận Spring đã **đăng ký đúng repository bean**.
2. Kiểm tra repository dùng `LdapTemplate` nào và bean đó dùng `ContextSource` nào.
3. Dùng `ldapsearch` với **cùng endpoint và bind account** để xác minh DN/attribute.
4. Kiểm tra `spring.ldap.base` và DN tương đối có bị lặp suffix không.
5. Nếu Search raw đúng mà entity sai, kiểm tra annotation/ODM mapping.
6. Nếu chỉ lỗi trên một directory, xác minh schema/vendor/ACL và matching rules.
7. Nếu chỉ lỗi trong CI, kiểm tra profile/test server, host/port động và readiness.
8. Chỉ thay đổi cấu hình sau khi xác định được lớp lỗi.

Không log mật khẩu, raw LDAP response chứa dữ liệu nhạy cảm hoặc filter người dùng chưa được xử lý.

## 16. Kiểm thử kiến trúc end-to-end

### 16.1. Vì sao chỉ mock repository là chưa đủ?

Unit test có thể dùng mock `PersonRepository` để kiểm tra business service. Nhưng mock không chứng minh:

- Repository proxy được Spring Data LDAP tạo.
- Method name được diễn dịch thành LDAP filter đúng.
- `LdapTemplate` dùng đúng `ContextSource`.
- `@Entry`, `@Id`, `@Attribute` ánh xạ đúng.
- LDAP server chấp nhận schema và filter.
- Lỗi bind/TLS/ACL hoặc giới hạn Search được xử lý đúng.

Những phần đó cần **integration test với directory thật**: embedded UnboundID hoặc LDAP container có schema/ACL phù hợp.

### 16.2. Một profile embedded LDAP cho test nhanh

Ví dụ `src/test/resources/application-ldap-embedded.yml`:

~~~yaml
spring:
  ldap:
    base: "dc=example,dc=org"
    embedded:
      base-dn: "dc=example,dc=org"
      ldif: "classpath:ldap/fixtures.ldif"
      validation:
        enabled: true
~~~

Dependency test bổ sung:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.unboundid:unboundid-ldapsdk")
}
~~~

Spring Boot có thể khởi động UnboundID in-memory LDAP với **port ngẫu nhiên**, cấu hình client tương ứng và seed dữ liệu LDIF.

Ví dụ LDIF (nếu server/fixture chưa tự tạo root):

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
~~~

Dữ liệu fixture phải tuân thủ schema. Nếu image/server đã tạo root entry, tránh import trùng `dc=example,dc=org`; điều chỉnh bootstrap theo server thực tế.

### 16.3. So sánh repository và template trong JUnit

~~~java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("ldap-embedded")
class PersonRepositoryArchitectureIT {

    @Autowired
    PersonRepository repository;

    @Autowired
    LdapTemplate template;

    @Test
    void repositoryAndTemplateReadSameEntry() throws Exception {
        Name aliceDn = new LdapName("uid=alice,ou=people");

        PersonEntry repositoryResult =
            repository.findById(aliceDn).orElseThrow();

        PersonEntry templateResult =
            template.findByDn(aliceDn, PersonEntry.class);

        assertThat(repositoryResult.getUid()).isEqualTo("alice");
        assertThat(templateResult.getUid()).isEqualTo("alice");

        assertThat(repositoryResult.getCommonName())
            .isEqualTo(templateResult.getCommonName());
    }

    @Test
    void derivedQueryUsesLdapAttributes() {
        var results = repository.findByUid("alice");

        assertThat(results)
            .extracting(PersonEntry::getUid)
            .containsExactly("alice");
    }
}
~~~

Test cần đặt entity/repository trong phạm vi Spring scanning. Nếu test khởi động được context nhưng không tìm thấy entry, cần kiểm tra fixture, base DN, quyền và schema, không vội kết luận repository proxy không hoạt động.

Cũng nên kiểm tra một đường write trên **DN test riêng**, tạo entry → đọc lại bằng repository/template → sửa một attribute → xác minh bằng raw LDAP → xóa và dọn. Không chạy CRUD trên directory production.

### 16.4. Những trường hợp quan trọng khác

| Test | Bằng chứng cần có |
| --- | --- |
| Không tìm thấy DN | Method trả hành vi “không có entry” theo hợp đồng; không che lỗi kết nối |
| Filter chứa `*`, `(`, `)` | Dữ liệu đầu vào không thay đổi cấu trúc filter |
| Repository sai package scan | Context không có bean; sửa phạm vi quét |
| Custom `LdapTemplate` | Repository sử dụng đúng `ldapTemplateRef` |
| Entry thiếu `sn` khi Add | Server kiểm tra schema |
| Account bind chỉ đọc | Repository không có quyền ghi, không nâng đặc quyền |
| Multi-entry workflow thất bại giữa chừng | Hệ thống có retry/đối soát, không giả transaction |
| Danh bạ lớn | Giới hạn Search và cơ chế paging phù hợp |
| SSL/truststore sai | Bị từ chối kết nối; không vô hiệu hóa TLS verification |
| Đổi DN/OU | Hiểu rằng DN là vị trí, cần xử lý tham chiếu và khóa định danh |

## 17. Những ngộ nhận kiến trúc cần tránh

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “Chỉ cần khai báo interface là không cần kết nối LDAP” | Repository vẫn dùng Spring LDAP `LdapTemplate`/`ContextSource` và server thật |
| “Repository có socket riêng không liên quan template” | Hạ tầng repository sử dụng `LdapOperations` và ODM |
| “Spring Data LDAP là lớp thay thế Spring LDAP” | Nó xây repository abstraction **trên** Spring LDAP |
| “`@Entry` là JPA `@Entity`” | ODM LDAP dùng `objectClass`, DN và schema |
| “ID là UID String hoặc số tự tăng” | ID repository LDAP là `javax.naming.Name` |
| “`@EnableLdapRepositories` chọn base DN của directory” | Nó chọn **Java packages để scan repository** |
| “`spring.ldap.base` tạo OU cho server” | Đây là base DN của client, không provision entry |
| “`save` giống `merge` và có cascade” | LDAP update theo DN/entry; không tự có cascade/ACID |
| “Paging/sorting repository giống SQL” | Repository LDAP không hỗ trợ paging/sorting tổng quát như JPA |
| “`findByUid` đã xác thực user” | Nó chỉ Search; authentication là bài toán khác |
| “Kết quả rỗng nghĩa là không có dữ liệu” | Có thể do base/filter/ACL/replica |
| “Tắt TLS để sửa lỗi LDAP” | Phải sửa certificate/truststore/hostname, không bỏ xác thực |
| “Dùng admin bind là dễ nhất” | Vi phạm least privilege, làm che lỗi ACL |
| “Mock repository chứng minh được schema và filter” | Phải integration test với LDAP server thật |

## 18. Câu hỏi tự kiểm tra

1. Thành phần nào tạo repository proxy từ interface `PersonRepository`?
2. `LdapRepositoryFactoryBean` và `LdapRepositoryFactory` có vai trò khác nhau như thế nào?
3. Vì sao `SimpleLdapRepository` cần cả `LdapOperations` và `ObjectDirectoryMapper`?
4. `LdapTemplate` giúp giảm những thao tác JNDI lặp lại nào?
5. `LdapContextSource` quyết định những gì? Nó có kiểm soát ACL phía server không?
6. Vì sao `LdapRepository<PersonEntry>` chỉ cần một generic type parameter?
7. Khi `ContextSource.base="dc=example,dc=org"`, `findById(Name)` nên nhận DN nào cho Alice trong nhánh `ou=people`?
8. `findById(Name)` khác `findByUid(String)` về LDAP operation và cách xác định đối tượng ra sao?
9. Vì sao `findByCommonNameStartingWith` cần `@Attribute(name="cn")` trên property `commonName`?
10. Repository query derivation có tự thêm điều kiện `objectClass` như thế nào theo metadata ODM? Vì sao không nên đoán chuỗi filter chính xác tuyệt đối?
11. Vì sao tham số của `@Query` phải được bind và encode đúng? Khi nào SpEL trở nên nguy hiểm?
12. `@Entry`, `@Id`, `@DnAttribute`, `@Transient` phục vụ những mục đích nào?
13. Khi nào dùng `LdapTemplate.modifyAttributes` tốt hơn `repository.save(...)`?
14. Tại sao `saveAll` không biến ba LDAP Modify thành một transaction ACID?
15. Vì sao `@EnableLdapRepositories(basePackages=...)` không thay đổi LDAP search base?
16. Với hai directory, `ldapTemplateRef` giúp ngăn lỗi kết nối nhầm như thế nào?
17. Tại sao không nên dùng `Pageable` của JPA và kỳ vọng LDAP repository tự xử lý giống SQL?
18. Một test Spring Boot có `PersonRepository` bean nhưng `findByUid("alice")` rỗng: hãy nêu thứ tự kiểm tra.
19. Vì sao quyền search/read LDAP của service account khác quyền authorization trong ứng dụng?
20. Làm sao viết test chứng minh repository và `LdapTemplate` sử dụng cùng directory và cùng ODM mapping?

## 19. Tổng kết

**Spring Data LDAP repository là một abstraction đặt trên Spring LDAP**, không phải một client LDAP độc lập. Spring Data infrastructure tạo proxy từ interface, phân loại CRUD/query methods, dùng `SimpleLdapRepository` và query machinery; còn Spring LDAP đảm nhận `LdapTemplate`/`LdapOperations`, ODM, quản lý context JNDI, giao tiếp LDAP và chuyển đổi lỗi. **Directory server luôn là nơi quyết định schema, ACL, tính hợp lệ DN và khả năng thực thi thao tác.**

Khi đọc `findById(Name)`, cần hiểu đây là lookup theo **DN**. Khi đọc `findByUid(String)`, cần hiểu đây là **Search theo attribute**. Khi gọi `save`, cần hiểu LDAP entry được tạo/sửa theo DN và schema, không phải một JPA row. Khi bài toán vượt khả năng repository (controls, paging, sửa attribute chọn lọc, thao tác DN), dùng `LdapTemplate` trong cùng service và cùng `ContextSource`.

Nắm rõ đường đi **repository proxy → LDAP operations/ODM → ContextSource/JNDI → LDAP server** giúp phát hiện nhanh cấu hình sai bean, base DN, mapping `objectClass`, filter không an toàn, quyền bind và các kỳ vọng sai về transaction. Kiến trúc này là nền tảng để phát triển và kiểm thử các chức năng directory lookup, quản lý tài khoản và nhóm qua Spring Data LDAP một cách chính xác.

### Tài liệu tham khảo

- [Spring Data LDAP — Configuration / EnableLdapRepositories](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html).
- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html).
- [Spring Data LDAP API — LdapRepositoryFactoryBean](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/LdapRepositoryFactoryBean.html).
- [Spring Data LDAP API — LdapRepositoryFactory](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/LdapRepositoryFactory.html).
- [Spring Data LDAP API — SimpleLdapRepository](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/SimpleLdapRepository.html).
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP — Basic Usage và LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring Boot — LDAP Auto-Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html).
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4515 — LDAP Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 2696 — Simple Paged Results Control](https://www.rfc-editor.org/rfc/rfc2696).
