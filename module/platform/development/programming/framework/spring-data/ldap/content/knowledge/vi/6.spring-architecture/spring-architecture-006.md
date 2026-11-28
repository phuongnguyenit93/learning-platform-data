# ObjectDirectoryMapper và cơ chế ánh xạ ODM

Trong **Spring Data LDAP**, một LDAP entry không phải là một hàng trong bảng SQL. Entry có **Distinguished Name (DN)** để định vị trong cây thư mục, nhiều thuộc tính có thể đa trị, và một hay nhiều `objectClass` quy định cấu trúc hợp lệ. Để lập trình viên không phải tự đọc từng `javax.naming.directory.Attribute` cho mọi truy vấn, Spring LDAP cung cấp **Object–Directory Mapping (ODM)**: cơ chế chuyển đổi giữa LDAP entry và đối tượng Java. Thành phần trung tâm của cơ chế này được gọi là **`ObjectDirectoryMapper`**.

Trong chương **Kiến trúc Spring**, bài học này giải thích vị trí, trách nhiệm và luồng xử lý của `ObjectDirectoryMapper`; cách kết hợp `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`; quan hệ với `LdapTemplate` và `LdapRepository`; sự khác biệt giữa ODM và `AttributesMapper`/`ContextMapper`; và những vấn đề cần kiểm thử liên quan DN, schema, CRUD, LDAP filter, quyền truy cập và bảo mật kết nối.

**Ý chính:** ODM giúp **ánh xạ dữ liệu**, chứ không tạo LDAP schema, không tự xác định quyền truy cập, không sinh DN tùy ý, không giải quyết đồng bộ hoặc cho phép ứng dụng xem entry ngoài phạm vi directory.

## 1. Bắt đầu từ một LDAP entry thật

Giả sử một directory phục vụ naming context `dc=example,dc=org` với các nhánh:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001
│   └── uid=u1002
├── ou=groups
│   └── cn=developers
└── ou=service-accounts
    └── cn=svc-reader
```

Một entry theo LDIF:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an.nguyen@example.org
telephoneNumber: +84-28-0000-1234
```

Entry này có những đặc điểm mà Java object cần mô tả đúng:

- **`dn`** là tên phân biệt hiện tại: `uid=u1001,ou=people,dc=example,dc=org`.
- **RDN** `uid=u1001` là thành phần tên đặt dưới parent `ou=people`.
- **`objectClass`** là thuộc tính đa trị; ở ví dụ này các class có quan hệ kế thừa theo schema thông dụng.
- **`uid`, `cn`, `sn`, `mail`** là thuộc tính LDAP, không phải các cột trong bảng quan hệ.
- **Schema** quyết định thuộc tính bắt buộc, thuộc tính tùy chọn, kiểu giá trị và matching rule.
- Các thao tác đọc/ghi còn bị giới hạn bởi **ACL** và quyền của tài khoản đã bind với server.

Khi cần biến entry này thành một `DirectoryPerson`, ta có hai cách: tự ánh xạ bằng mapper thủ công hoặc để cơ chế ODM dựa trên annotation làm phần lớn công việc.

## 2. ODM giải quyết vấn đề gì?

Một ứng dụng có thể gọi `LdapTemplate.search(...)` và tự lấy dữ liệu từ `Attributes`:

```java
AttributesMapper<PersonView> mapper = attributes ->
        new PersonView(
                (String) attributes.get("uid").get(),
                (String) attributes.get("cn").get());
```

Cách này phù hợp nếu chỉ cần **DTO nhỏ**. Tuy nhiên, khi ứng dụng có nhiều query, thao tác CRUD và hàng chục thuộc tính, việc lặp lại mã đọc từng attribute gây ra các vấn đề:

1. Tên property Java có thể khác tên LDAP: `commonName` ↔ `cn`, `surname` ↔ `sn`.
2. Cần giữ DN của entry mà không nhầm DN với thuộc tính `uid`.
3. Mỗi mapping phải xử lý thuộc tính thiếu, đa trị và kiểu giá trị.
4. Các thao tác tạo/sửa entry cần chuyển field của object ngược thành các thuộc tính LDAP hợp lệ.
5. Dễ có sai lệch giữa cách ánh xạ khi đọc với khi ghi.

**ODM** tập trung phần mô tả mapping vào entity có annotation, để cùng một hợp đồng mapping được dùng nhất quán trong nhiều đường truy cập.

### ODM khác ORM như thế nào?

| Khía cạnh | ORM/JPA | LDAP ODM |
|---|---|---|
| Nguồn dữ liệu | Bảng, hàng, cột, quan hệ SQL | Directory Information Tree (DIT), entry, attribute |
| Địa chỉ của object | Thường là primary key | **DN**, có thể thay đổi khi move/rename |
| Mô tả kiểu bản ghi | Entity/table/column | `objectClass` và LDAP schema |
| Quan hệ | Foreign key, join, cascade | DN tham chiếu, member/group, cấu trúc phân cấp |
| Ngôn ngữ truy vấn | SQL/JPQL/Criteria | LDAP search filter + base DN + scope |
| Ghi dữ liệu | INSERT/UPDATE/DELETE SQL | LDAP add/modify/delete/modifyDN |
| Bảo mật truy cập | Cơ chế database + ứng dụng | LDAP bind, ACL, TLS + ứng dụng |

**Không coi `@Entry` là `@Table` đổi tên.** Một cây LDAP có thể chứa nhiều naming context, các entry không nhất thiết cùng bộ thuộc tính, và không có cơ chế join/cascade JPA tương đương được ODM tự động cung cấp.

## 3. `ObjectDirectoryMapper` đứng ở đâu trong kiến trúc Spring LDAP?

Về mặt trách nhiệm, `ObjectDirectoryMapper` là thành phần **chuyển đổi giữa LDAP entry và Java object dựa trên metadata ODM**. Trong các bản Spring LDAP có hỗ trợ ODM, thư viện cung cấp implementation mặc định để đọc annotation trên class/entity và thực hiện mapping.

Sơ đồ khái niệm:

```text
                  Business Service
                       │
           ┌───────────┴───────────┐
           │                       │
   LdapRepository<T>          LdapTemplate
           │                       │
           └───────────┬───────────┘
                       │
                ODM operations
                       │
               ObjectDirectoryMapper
           annotation metadata / conversion
                       │
              DirContextOperations
                DN + Attributes
                       │
               ContextSource / JNDI
                       │
        LDAP server (schema + ACL + TLS)
```

Sơ đồ diễn tả **luồng trách nhiệm**, không khẳng định mọi lời gọi repository hay mọi thao tác của `LdapTemplate` đều đi qua `ObjectDirectoryMapper`. Chẳng hạn:

- `ldapTemplate.findByDn(dn, DirectoryPerson.class)` và các thao tác ODM sẽ dùng mapping của entity.
- `ldapTemplate.lookup(dn, AttributesMapper<T>)` dùng **mapper được truyền vào** để tạo DTO, không tự lấy `@Entry` của entity bất kỳ.
- `ldapTemplate.search(query, ContextMapper<T>)` dùng `ContextMapper` do ứng dụng cung cấp.
- `LdapRepository` cung cấp tầng repository dựa trên mapping và các thao tác LDAP tương ứng, nhưng vẫn phụ thuộc `ContextSource` và cấu hình truy vấn.

### Nhiệm vụ và giới hạn của ObjectDirectoryMapper

| Thực hiện | Không tự thực hiện |
|---|---|
| Đọc annotation ODM trên entity được hỗ trợ | Tạo/sửa LDAP schema |
| Liên kết tên LDAP attribute với Java property | Quyết định user HTTP nào được xem dữ liệu |
| Chuyển DN vào property `@Id` | Cấp DN từ sequence SQL hoặc bảo đảm DN không đổi |
| Ánh xạ giá trị thuộc tính hợp lệ sang field Java | Giải quyết mọi khác biệt schema giữa OpenLDAP/AD |
| Hỗ trợ ánh xạ đối tượng thành dữ liệu LDAP để ghi | Tự bảo đảm transaction xuyên nhiều LDAP entry |
| Tái sử dụng metadata mapping qua các thao tác ODM | Thương lượng TLS hoặc quyết định credential bind |

Trong ứng dụng thông thường, lập trình viên **không cần gọi trực tiếp phương thức nội bộ của `ObjectDirectoryMapper`**. Điều quan trọng là khai báo entity đúng và chọn các API ODM của Spring LDAP; khi cần hành vi riêng, phải kiểm tra extension point và contract đúng theo phiên bản thư viện đang dùng.

## 4. Khai báo một entity ODM hoàn chỉnh

Dưới đây là class Java minh họa cho entry `inetOrgPerson` ở `ou=people`:

```java
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
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {
        // Constructor không tham số cho ODM.
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
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getGivenName() { return givenName; }
    public void setGivenName(String givenName) {
        this.givenName = givenName;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Ý nghĩa annotation:

| Annotation | Tác dụng |
|---|---|
| `@Entry(base = ...)` | Nêu base tương đối trong cấu hình ODM, phù hợp cây directory mục tiêu |
| `@Entry(objectClasses = ...)` | Mô tả các `objectClass` tương ứng của entry |
| `@Id` trên `Name dn` | Nhận dạng DN của entry trong mapping |
| `@Attribute(name = "uid")` | Liên kết LDAP attribute `uid` với Java field `uid` |
| `@Attribute(name = "cn")` | Liên kết LDAP `cn` với field `commonName` |
| `@Attribute(name = "mail")` | Liên kết LDAP `mail` với field `email` |

**Hai loại ánh xạ khác nhau:** `@Id` chứa **DN**, còn `@Attribute` chứa **giá trị thuộc tính**. `uid` có thể là một phần RDN nhưng chỉ giá trị `u1001` không đủ thay cho `uid=u1001,ou=people` trong một context base cụ thể.

### `javax.naming.Name` không phải `jakarta.persistence.Id`

JNDI `javax.naming.Name` là kiểu của **Java SE**, vẫn được dùng khi ứng dụng chuyển sang Spring Framework 6 / Spring Boot 3. Hãy import `org.springframework.ldap.odm.annotations.Id` thay vì `jakarta.persistence.Id`. Đừng dùng một entity JPA rồi mong Spring LDAP tự hiểu các annotation JPA thành LDAP attributes.

## 5. Từ LDAP entry sang Java object: chiều đọc

Xét entry đầu bài và entity `DirectoryPerson`. Khi một thao tác ODM yêu cầu tìm entry:

1. **`ContextSource`** cung cấp một context JNDI đã cấu hình endpoint, base và danh tính bind.
2. **`LdapTemplate`** thực hiện search/lookup theo DN, search scope và filter cần thiết.
3. Directory trả về DN và các LDAP attributes được cho phép.
4. **ODM/ObjectDirectoryMapper** chọn metadata của `DirectoryPerson`, tạo instance và điền các property từ thuộc tính trả về.
5. Field `@Id Name dn` được đặt theo DN mà tầng mapping quản lý; tên tương đối hay cách biểu diễn phải được đối chiếu với context base thực tế.
6. Kết quả là object Java mà service có thể sử dụng theo contract của ứng dụng.

Minh họa ánh xạ:

```text
LDAP result                                 Java DirectoryPerson
--------------------------------           --------------------------
dn: uid=u1001,ou=people,...         -----> dn: Name("uid=u1001,ou=people")
uid: u1001                           -----> uid: "u1001"
cn: An Nguyen                        -----> commonName: "An Nguyen"
sn: Nguyen                           -----> surname: "Nguyen"
givenName: An                        -----> givenName: "An"
mail: an.nguyen@example.org          -----> email: "an.nguyen@example.org"
```

Ví dụ giả định `LdapContextSource` dùng base `dc=example,dc=org`. Vì thế `Name` dùng trong API thường là DN **tương đối với context base**: `uid=u1001,ou=people`. Đừng tự ghép thêm `dc=example,dc=org` nếu API đang mong DN tương đối; cũng không nên cho rằng một `@Id` luôn là DN tuyệt đối trên mọi cấu hình.

### Lookup bằng `LdapTemplate.findByDn`

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryPersonReader {
    private final LdapTemplate ldapTemplate;

    public DirectoryPersonReader(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryPerson findKnownPerson(String uid) {
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        return ldapTemplate.findByDn(
                relativeDn, DirectoryPerson.class);
    }
}
```

`LdapNameBuilder` tạo DN từ các thành phần, escape RDN đúng cú pháp. Với input chứa dấu phẩy, tự nối chuỗi kiểu `"uid=" + uid + ",ou=people"` có thể làm hỏng DN. **Escape DN không giống escape LDAP filter**, và cũng không thay thế kiểm tra quyền người gọi.

Nếu entry không tồn tại, LDAP API có thể ném exception hoặc trả giá trị không tìm thấy tùy thao tác; service phải phân biệt **not found**, lỗi ACL, authentication và timeout. Không gộp mọi exception thành `null`.

## 6. Truy vấn theo thuộc tính: ODM vẫn cần base và LDAP filter

Không phải lúc nào ứng dụng cũng biết DN hiện tại. Một người có thể chuyển OU hoặc được đổi RDN. Khi chỉ biết `uid`, cần **search theo thuộc tính trong phạm vi được phép**.

Ví dụ đọc các `DirectoryPerson` theo `uid` bằng Spring LDAP ODM:

```java
import java.util.List;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryPeopleSearch {
    private final LdapTemplate ldapTemplate;

    public DirectoryPeopleSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<DirectoryPerson> byUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        LdapQuery q = query()
                .base("ou=people")
                .where("uid").is(uid);

        return ldapTemplate.find(q, DirectoryPerson.class);
    }
}
```

Ở đây có **hai cơ chế cùng hoạt động**:

- `query().base("ou=people").where("uid").is(uid)` mô tả **phạm vi và LDAP filter**; API builder hỗ trợ escape giá trị trong filter.
- `find(q, DirectoryPerson.class)` yêu cầu **ODM** ánh xạ những entry tìm được thành `DirectoryPerson`.

`ObjectDirectoryMapper` **không tự quyết định search base hoặc filter nghiệp vụ**. Tầng query vẫn cần bảo đảm danh tính, quyền, search scope và giới hạn số lượng. Truy vấn cùng `uid` ở hai OU khác nhau có thể trả nhiều entry, do đó không mặc định `uid` duy nhất trên mọi naming context.

## 7. `LdapRepository` sử dụng metadata ODM ra sao?

`LdapRepository` cung cấp tầng abstraction thân thiện hơn cho các truy vấn lặp lại. Nó sử dụng metadata của entity, các cơ chế truy vấn và thao tác LDAP tương ứng; ý nghĩa ánh xạ vẫn gắn với `@Entry`, `@Id` và `@Attribute`.

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurname(String surname);

    List<DirectoryPerson> findByUid(String uid);
}
```

Cách gọi:

```java
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name id = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "u1001")
        .build();

// Tìm theo DN:
var byDn = repository.findById(id);

// Tìm theo LDAP attribute được @Attribute mapping:
List<DirectoryPerson> byUid = repository.findByUid("u1001");
```

| API | Dữ liệu đầu vào | Mục đích |
|---|---|---|
| `findById(Name)` | DN của entry | Định vị đúng entry hiện tại |
| `findByUid(String)` | Giá trị thuộc tính `uid` | Search theo điều kiện thuộc tính |
| `findBySurname(String)` | Giá trị property `surname` | Mapping tới LDAP attribute `sn` |
| `LdapTemplate.find(query, type)` | Base, filter, scope | Search động và map bằng ODM |

Tập keyword của **query derivation** phụ thuộc phiên bản Spring Data LDAP, không nên tự suy rằng mọi keyword/biểu thức của Spring Data JPA đều hoạt động giống hệt. Với filter phức tạp, nhóm AND/OR/NOT hoặc kiểm soát search scope đặc thù, `LdapTemplate` và filter builder thường làm ý đồ rõ hơn.

**Repository không “đứng ngoài” cấu hình kết nối:** repository vẫn truy cập LDAP thông qua infrastructure do ứng dụng cấu hình. Nếu ứng dụng có nhiều `LdapTemplate` hoặc `ContextSource` (ví dụ đọc/ghi tách biệt), cần xác minh repository factory thực sự sử dụng bean nào; chú thích entity không quyết định tài khoản bind.

## 8. So sánh `ObjectDirectoryMapper` với `AttributesMapper` và `ContextMapper`

Cùng là “mapper”, nhưng chúng phục vụ **các mức abstraction khác nhau**.

| Công cụ | Input | Output/mục tiêu | Phù hợp khi |
|---|---|---|---|
| **ODM/ObjectDirectoryMapper** | LDAP entry, DN và metadata của class `@Entry` | Entity Java được ánh xạ tự động, và hỗ trợ chiều ghi | Có entity dùng nhiều lần qua repository/ODM |
| **`AttributesMapper<T>`** | `javax.naming.directory.Attributes` | DTO hoặc giá trị tùy ứng dụng | Chỉ cần vài thuộc tính, không cần toàn entity |
| **`ContextMapper<T>`** | Context entry, thường là `DirContextOperations` | DTO linh hoạt, có thể đọc DN và metadata context | Cần DN hoặc thông tin entry ngoài attributes thông thường |

Ví dụ `AttributesMapper`:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public record PersonSummary(String uid, String commonName) {}

LdapQuery q = query()
        .base("ou=people")
        .where("uid").is("u1001");

AttributesMapper<PersonSummary> mapper = attrs ->
        new PersonSummary(
                (String) attrs.get("uid").get(),
                (String) attrs.get("cn").get());

List<PersonSummary> results =
        ldapTemplate.search(q, mapper);
```

Đây là **đoạn minh họa đặt bên trong một method có sẵn biến `ldapTemplate`**, không phải một Java source file hoàn chỉnh. Với LDAP attribute tùy chọn cần kiểm tra `attrs.get(...) == null`, và giá trị nhị phân/đa trị phải được xử lý theo schema.

Ví dụ `ContextMapper` để lấy tên:

```java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<String> nameMapper = context -> {
    DirContextOperations entry =
            (DirContextOperations) context;
    return entry.getDn().toString();
};
```

**Lựa chọn thực tế:**

- Nếu muốn một domain object được truy vấn và cập nhật bằng các API ODM, dùng `@Entry` + `ObjectDirectoryMapper` qua `LdapTemplate`/repository.
- Nếu endpoint chỉ trả 2–3 field từ một LDAP search, một `AttributesMapper` rõ ràng có thể gọn và giảm dữ liệu giữ trong bộ nhớ.
- Nếu cần tên DN/current context để đối chiếu hoặc xuất dữ liệu, xem xét `ContextMapper`.
- Đừng ánh xạ cả entity có nhiều thuộc tính nhạy cảm khi API chỉ cần `uid` và `cn`; giới hạn **requested attributes** và DTO ở tầng truy vấn.

## 9. Chiều ngược: từ entity Java thành dữ liệu LDAP để ghi

ODM không chỉ dành cho đọc. Với các API hỗ trợ ghi entity, Spring LDAP sử dụng metadata để chuyển dữ liệu trên Java object thành LDAP attributes/entry operations tương ứng.

Luồng khái niệm:

```text
Java DirectoryPerson
    │
    ├── @Id Name dn
    ├── @Attribute uid, cn, sn, mail, ...
    └── @Entry objectClasses
          │
          ▼
   ODM mapping / conversion
          │
          ▼
 LDAP add / modify (tùy API)
          │
          ▼
  LDAP server kiểm tra
  schema + ACL + DN + quyền ghi
```

Ví dụ chuẩn bị một entry mới:

```java
DirectoryPerson person = new DirectoryPerson();
person.setDn(LdapNameBuilder.newInstance("ou=people")
        .add("uid", "u1003")
        .build());
person.setUid("u1003");
person.setCommonName("Chi Le");
person.setSurname("Le");
person.setGivenName("Chi");
person.setEmail("chi.le@example.org");
```

Đây mới là **dữ liệu đầu vào**, chưa phải thao tác tạo entry. Trong môi trường được phép ghi, các phương thức ODM như `ldapTemplate.create(person)` / `ldapTemplate.update(person)` (khi được phiên bản Spring LDAP hỗ trợ) hoặc thao tác của repository có thể sử dụng mapping để gửi request. Nhưng **phải kiểm tra contract cụ thể của từng method** để biết cách xác định create/update và thuộc tính nào được thay thế.

### Các điều kiện mà ObjectDirectoryMapper không thể bỏ qua

1. **Parent DN phải tồn tại:** `ou=people,dc=example,dc=org` phải có sẵn.
2. **Entry DN không được va chạm:** add không âm thầm ghi đè entry đã có.
3. **Object classes hợp lệ:** server kiểm tra schema và thuộc tính MUST/MAY.
4. **Bind account đủ quyền:** reader không được tạo hoặc sửa entry chỉ vì entity đã được mapping.
5. **Giá trị phải đúng kiểu:** binary, đa trị, syntax đặc thù AD, thứ tự và cấu trúc liên kết.
6. **DN được chọn theo nghiệp vụ:** ODM không tự tạo UID từ database sequence.

Với các thay đổi nhỏ, ví dụ chỉ sửa `mail`, có thể chọn **`LdapTemplate.modifyAttributes`** với `ModificationItem` thay vì cập nhật nguyên entity, để tránh việc vô tình thay những thuộc tính không nằm trong phạm vi nghiệp vụ.

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "u1001")
        .build();

ModificationItem replaceMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "an.new@example.org"));

// Chỉ chạy trong workflow ghi đã được xác thực và phân quyền.
// writeLdapTemplate.modifyAttributes(
//         dn, new ModificationItem[] { replaceMail });
```

**Không có “dirty checking JPA” tự động áp dụng cho mọi object LDAP.** Trước khi gọi update, cần hiểu API đang thực hiện **LDAP modify operation** nào, danh sách thuộc tính bị thay đổi và cách xử lý null/collection. Không dựa vào việc sửa field Java rồi đợi một transaction ORM tự flush thay đổi.

## 10. `@DnAttribute` và việc dựng DN từ property

Khi entry sử dụng RDN `uid=u1001`, giá trị thuộc tính `uid` có quan hệ với tên entry. ODM có annotation `@DnAttribute` để mô tả quan hệ này trong các mapping phù hợp.

```java
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;

// Bên trong class có @Entry và @Id Name dn:
@Attribute(name = "uid")
@DnAttribute(value = "uid")
private String uid;
```

Cần phân biệt:

- `@Id Name dn` lưu **tên của toàn entry** theo quy ước context.
- `@DnAttribute` mô tả property có giá trị liên quan tới một **RDN component**.
- `@Attribute` mô tả ánh xạ sang LDAP attribute có tên tương ứng.

`@DnAttribute` có thể hữu ích khi ODM cần dựng DN cho entry mới từ các property được đánh dấu. Tuy vậy nó **không** thay thế `@Id`, không tự đảm bảo UID duy nhất và không phải lý do để ánh xạ mọi field thành DN component.

Khi DN có nhiều RDN cùng attribute type hoặc khi schema/server sử dụng `CN=...` thay vì `UID=...` (thường gặp ở AD), cần xác định đúng vị trí của thành phần DN và kiểm thử mapping theo tài liệu phiên bản Spring LDAP cụ thể.

## 11. Thuộc tính đa trị, kiểu nhị phân và giá trị không có

LDAP entry có thể có một hay nhiều giá trị cho cùng attribute. Ví dụ nhóm:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=u1001,ou=people,dc=example,dc=org
member: uid=u1002,ou=people,dc=example,dc=org
```

Với các mapping ODM, **collection** cần biểu diễn đúng thuộc tính đa trị; không lấy giá trị đầu tiên rồi làm mất các giá trị còn lại. Mô hình minh họa:

```java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "member")
    private Set<String> memberDns;

    public DirectoryGroup() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public Set<String> getMemberDns() { return memberDns; }
    public void setMemberDns(Set<String> memberDns) {
        this.memberDns = memberDns;
    }
}
```

Ví dụ trên giả định mapping tập giá trị `member` sang collection được **phiên bản ODM hỗ trợ** và directory cho phép đọc membership. Tùy loại dữ liệu và yêu cầu cập nhật, cần xác minh kiểu phần tử phù hợp, cách xử lý null/empty, và liệu server kiểm tra DN membership thế nào.

### Ba tình huống dễ sai

**1. Thuộc tính vắng mặt:** `mail` là optional ở nhiều schema. Nếu entry không có `mail` hoặc ACL che thuộc tính, field Java có thể không có giá trị. Không mặc định một string rỗng và một thuộc tính không tồn tại có ý nghĩa giống nhau khi ghi lại.

**2. Thuộc tính đa trị:** nhóm có nhiều `member`. Tầng mapping và cập nhật phải giữ semantics của **set giá trị**, tránh tình huống ghi một giá trị mới nhưng xóa nhầm phần tử khác.

**3. Nhị phân:** `objectGUID` của Active Directory và một số thuộc tính ảnh/chứng chỉ thường trả dạng byte array hoặc dữ liệu đặc thù. **Đừng ép tất cả attribute sang `String`**; việc hiển thị binary thành chuỗi và ghi lại có thể làm hỏng dữ liệu. Nếu cần converter riêng, kiểm tra cơ chế hỗ trợ/extension point của phiên bản thư viện.

## 12. ODM không tự ánh xạ quan hệ như JPA

Với nhóm `cn=developers`, các giá trị `member` chứa **DN tham chiếu**. ODM có thể giúp ánh xạ chúng vào field Java, nhưng **không tự tải mọi `DirectoryPerson` tương ứng như một quan hệ `@OneToMany` JPA**.

```text
DirectoryGroup.memberDns
    ├── "uid=u1001,ou=people,dc=example,dc=org"
    └── "uid=u1002,ou=people,dc=example,dc=org"
         │
         ▼
  Nếu cần Person object:
  ứng dụng chủ động lookup/search
  theo phạm vi + ACL được phép
```

Các vấn đề ứng dụng phải tự xử lý:

- **DN được đổi khi move/rename:** thuộc tính tham chiếu có thể cần kiểm tra cập nhật theo cơ chế server.
- **Nhóm lồng nhau:** cần thuật toán và giới hạn độ sâu nếu nghiệp vụ yêu cầu mở rộng group membership.
- **ACL:** đọc được group không đồng nghĩa đọc được mọi thuộc tính của member.
- **Hiệu năng:** lặp lookup từng member có thể tạo N+1 LDAP operations; cần đo và tối ưu theo server.
- **Tránh chu kỳ:** quan hệ nhóm lồng nhau có thể tạo đồ thị, không phải cây object Java tự động an toàn.
- **Ràng buộc schema:** một số group objectClass yêu cầu tối thiểu một member; quy tắc xóa/cập nhật không giống một bảng join SQL.

## 13. DN, rename/move và vòng đời của entity

Một trong những khác biệt lớn nhất giữa ODM và ORM là `@Id Name` giữ **DN có thể thay đổi** khi entry được đổi RDN hoặc di chuyển.

```text
Trước: uid=u1001,ou=people,dc=example,dc=org
Sau:   uid=u1001,ou=contractors,dc=example,dc=org
```

Khi người dùng chuyển OU, entry có thể vẫn đại diện cho cùng một người, nhưng:

- `DirectoryPerson.getDn()` đã tải trước đó có thể giữ DN cũ.
- `repository.findById(oldDn)` không còn tìm được entry hiện tại.
- Caches và dữ liệu đích keyed bằng DN có thể tạo duplicate hoặc orphan.
- Nếu ứng dụng đang tìm riêng dưới `ou=people`, entry sau move đã **ra khỏi phạm vi**, dù tồn tại ở nhánh khác.

**Không đổi trường `dn` trên Java object rồi mặc định `save()` sẽ thực hiện LDAP modifyDN/rename.** Đổi vị trí entry cần workflow riêng, kiểm tra quyền, DN đích và API rename thích hợp (ví dụ `LdapTemplate.rename`), sau đó đọc lại để xác minh.

Trong bài toán đồng bộ danh tính, cân nhắc khóa liên kết **ổn định hơn DN** khi server cung cấp, ví dụ `entryUUID` ở một số LDAP directory hoặc `objectGUID` ở AD. Ngữ nghĩa vòng đời/migration của các ID này phụ thuộc sản phẩm; không tự coi một ID server là toàn cục bất biến trong mọi thao tác.

## 14. Mapping, search scope và LDAP filter là các lớp khác nhau

Giả sử có entity mapping `@Entry(base = "ou=people")` nhưng hệ thống đang tìm dưới sai suffix. ODM vẫn có thể đúng **hoàn toàn** trong khi truy vấn không tìm thấy entry. Khi chẩn đoán cần tách:

| Lớp | Câu hỏi |
|---|---|
| Endpoint | Đang kết nối tới LDAP server/domain controller nào? |
| Naming context | Server phục vụ suffix/partition chứa entry không? |
| Context base | `LdapContextSource.setBase(...)` có đúng không? |
| Search base/scope | Truy vấn có bắt đầu ở OU đúng, tìm sâu tới mức cần không? |
| Filter | Điều kiện `uid`/`objectClass`/AND/OR có thực sự khớp? |
| ACL | Principal bind có quyền thấy entry/attribute không? |
| Schema | Attribute có tên, kiểu, object class phù hợp không? |
| ODM mapping | Field `@Attribute`/`@Id` có khớp kết quả search không? |

**LDAP filter phải được escape theo giá trị:** dùng `LdapQueryBuilder` hoặc `EqualsFilter` cho user input; đừng xây chuỗi kiểu `"(uid=" + input + ")"`. **DN phải được escape theo RDN:** dùng `LdapNameBuilder` thay vì nối chuỗi.

Giới hạn query cũng quan trọng. Ngay cả khi entity chỉ có bốn field, một search với base quá rộng và filter `(objectClass=*)` vẫn có thể đọc nhiều entry. ODM không tự giới hạn mức sử dụng tài nguyên.

## 15. Bảo mật khi dùng ODM và repository

ODM không tạo bảo mật nếu tầng kết nối và phân quyền chưa được thiết kế đúng. Với ứng dụng Spring Data LDAP:

1. **LDAPS hoặc StartTLS:** xác minh chuỗi chứng chỉ và hostname; không fallback SIMPLE bind qua cleartext.
2. **Tài khoản bind tối thiểu:** search service sử dụng tài khoản chỉ đọc các entry/attribute được phép; nghiệp vụ write dùng danh tính khác với quyền hẹp khi cần.
3. **Service authorization:** controller không được trực tiếp expose `repository.save` hoặc `delete` theo request tự do; kiểm tra ai được xem/sửa entry nào.
4. **Mapping thuộc tính cần thiết:** không yêu cầu hoặc trả về password hash, token, SID, ACL và dữ liệu cá nhân không cần dùng.
5. **Chống LDAP injection:** dùng filter builder và DN builder; không cho client tự gửi raw filter, raw base DN hoặc tên thuộc tính nhạy cảm.
6. **Kiểm soát logging:** log loại operation, thời gian, mã lỗi và correlation ID; hạn chế log toàn bộ DN và giá trị email.
7. **Audit thao tác ghi:** ghi nhận chủ thể, trường được sửa, kết quả LDAP và lý do nghiệp vụ, có che thông tin riêng tư.
8. **Khác biệt server:** AD, OpenLDAP và các directory khác có object class, attribute, permission và quy tắc password riêng; annotation không xóa khác biệt đó.

Nếu `LdapTemplate.find(...)` thành công nhưng field `email` rỗng, không được tự kết luận mapper lỗi: có thể thuộc tính thực sự thiếu hoặc bị ACL che. Cần xác minh bằng tài khoản thử nghiệm được phép và schema của directory.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần xem xét | Cách xử lý |
|---|---|---|
| `@Id` được khai báo bằng `String` | ODM mong DN kiểu `javax.naming.Name` | Đổi sang `Name`, import đúng Spring LDAP `Id` |
| Field `commonName` không có dữ liệu | Quên `@Attribute(name="cn")` hoặc ACL che `cn` | Đối chiếu tên LDAP thực, schema và ACL |
| Entity map được nhưng `findById` trả rỗng | DN tương đối sai hoặc entry đã đổi OU | So DN hiện tại với context base và `@Entry` |
| Lỗi khi lưu entry mới | Parent không tồn tại, DN trùng, thiếu `sn`/`cn` | Kiểm tra schema, OU và quyền add |
| `update` làm thay đổi nhiều field hơn dự kiến | Hiểu sai semantics cập nhật của API | Dùng modifyAttributes có allowlist cho patch hẹp |
| `mail` null | Thuộc tính optional/ACL | Thiết kế field tùy chọn; không ghi lại null tùy tiện |
| Nhóm mất member | Ánh xạ/ghi đa trị sai | Kiểm tra collection và thao tác add/remove value |
| Binary attribute bị hỏng | Ép `byte[]` thành `String` | Sử dụng kiểu/converter phù hợp |
| Rename sinh entry trùng | Đổi `@Id` rồi save thay vì rename | Dùng workflow modifyDN/rename |
| Repository dùng bind account khác dự tính | Nhiều ContextSource/LdapTemplate không cấu hình rõ | Kiểm tra wiring và test ACL |
| Tài khoản có ở server nhưng search không thấy | Base/scope/filter sai hoặc quyền không đủ | Kiểm tra RootDSE, DN, scope và search log |
| LDAPS/StartTLS lỗi | Truststore, hostname, handshake hoặc policy | Xử lý ở tầng transport, không đổ lỗi cho ODM |

Khi debug, ưu tiên kiểm tra **entry LDAP gốc và cấu hình truy vấn**, rồi mới kết luận vấn đề nằm ở mapper. Một lỗi schema hoặc ACL cần thông báo phù hợp, không che thành “đối tượng không tồn tại”.

## 17. Kiểm thử ODM từ unit test tới directory thực

### 17.1. Kiểm thử DN builder

Để tránh sai DN trước khi mapping:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class DirectoryDnTest {

    @Test
    void buildsRelativeUserDn() throws Exception {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "u1001")
                .build();

        assertEquals(new LdapName("uid=u1001,ou=people"), dn);
    }

    @Test
    void escapesCommaInRdnValue() throws Exception {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "team,east")
                .build();

        assertEquals(
                new LdapName("uid=team\\,east,ou=people"),
                dn);
    }
}
```

Unit test này chỉ kiểm tra DN parsing/escaping. Nó chưa chứng minh ODM tạo entity thành công hoặc directory có ACL đúng.

### 17.2. Kiểm thử với directory

Tạo directory thử nghiệm với schema hỗ trợ `inetOrgPerson`, entry `uid=u1001` trong `ou=people` và tài khoản bind có quyền đọc. Ma trận kiểm thử:

| Test | Kỳ vọng |
|---|---|
| `findByDn` đúng DN | Trả `DirectoryPerson` với `@Id` và attributes tương ứng |
| `repository.findById` | Trả đúng entity hoặc không thấy theo DN hiện tại |
| `find(query, DirectoryPerson.class)` | Ánh xạ nhiều entry trong base/filter phù hợp |
| Property Java đổi tên | `@Attribute(name="cn")` vẫn đọc đúng LDAP `cn` |
| Thiếu `mail` | Mapper xử lý field tùy chọn |
| Có nhiều `member` | Mapping không làm mất các giá trị đa trị |
| DN có dấu phẩy | Parser và builder xử lý đúng RDN |
| DN trùng UID khác OU | Không nhầm hai entry thành một |
| Rename/move | ID cũ hết hiệu lực, DN mới phản ánh đúng |
| Entry vi phạm schema khi ghi | Server từ chối; ứng dụng phân loại lỗi |
| Reader thử ghi | LDAP ACL từ chối, dù service có object hợp lệ |
| TLS/hostname không hợp lệ | Không kết nối, không fallback cleartext |

**Không chỉ dùng mock `LdapTemplate`.** Mock chứng minh logic service nhưng không chứng minh schema LDAP, entry thực, kết quả ODM mapping hay ACL. Với test ghi, chỉ dùng account và dữ liệu giả lập được phép; sau mỗi thao tác phải đọc lại entry và dọn dữ liệu test theo quy trình an toàn.

### 17.3. Đối chiếu mapping theo từng thuộc tính

Khi test thất bại, thu hẹp bằng một entry đã biết:

1. Dùng client LDAP đáng tin để đọc đúng DN/base và thuộc tính cần thiết.
2. Kiểm tra `objectClass` và các thuộc tính bắt buộc tồn tại.
3. Dùng `LdapTemplate.lookup(dn, AttributesMapper)` để xem mapper thủ công có đọc được giá trị không.
4. Thử `LdapTemplate.findByDn(dn, Entity.class)` với cùng context.
5. So trường nào lệch (DN, name, kiểu, null, collection, converter), sau đó sửa mapping.
6. Thử repository khi ODM qua `LdapTemplate` đã đúng để tách lỗi repository wiring/query derivation.

Trình tự này giúp biết lỗi nằm ở **server/schema**, **search/context**, **ODM metadata** hay **repository configuration**.

## 18. Hiệu năng và thiết kế entity lâu dài

ODM giảm mã lặp, nhưng **không làm LDAP search tự nhanh hơn**. Tốc độ chịu ảnh hưởng của:

- Search base, scope, filter và index thuộc tính trên directory server.
- Số entry tìm được, số thuộc tính được trả về và kích thước thuộc tính đa trị/binary.
- Số lần kết nối, bind, TLS handshake, pooling và timeout.
- Việc service truy vấn bổ sung để lấy member DN hoặc nhóm.
- Khối lượng ánh xạ object khi trả nhiều entry.

Nếu một REST API chỉ cần tên và UID để hiển thị danh sách, thường không cần tải cả membership, certificate hoặc hàng trăm attributes vào entity rồi trả ra response. Có thể dùng **DTO mapper** và giới hạn requested attributes thay vì ODM đầy đủ.

**Không giả định mapping quan hệ tự động:** nếu mỗi user lại lookup thêm 10 nhóm, số LDAP operations có thể tăng tuyến tính. Đo độ trễ ở từng tầng, số request thực, pool wait và server search time; không tối ưu bằng việc chỉ tăng số kết nối.

Với nhiều loại entry (user, group, service account), nên tạo **entity mapping riêng** và chỉ gán `@Entry` cho schema chính xác. Không tạo một entity khổng lồ cố chứa mọi objectClass rồi phụ thuộc vào null để phân loại trong runtime.

## 19. Bài tập thực hành

Một hệ thống có hai entry:

```text
uid=u1001,ou=people,dc=example,dc=org
cn=Developers,ou=groups,dc=example,dc=org
```

Entry user có `objectClass=inetOrgPerson`, `uid=u1001`, `cn=An Nguyen`, `sn=Nguyen`; group có `objectClass=groupOfNames`, `cn=Developers` và hai giá trị `member`. Context base của Spring LDAP là `dc=example,dc=org`.

Hãy trả lời:

1. `ObjectDirectoryMapper` chịu trách nhiệm gì trong chiều đọc entity, và thành phần nào thực hiện LDAP search?
2. Tại sao field `@Id` phải là `Name` thay vì giá trị `uid`?
3. Nên dùng `@Entry` và `@Attribute` thế nào để Java property `commonName` đọc được LDAP `cn`?
4. Khi chỉ cần DTO `uid` + `cn`, dùng `AttributesMapper` có lợi gì so với tạo entity ODM đầy đủ?
5. Dùng `LdapTemplate.findByDn` và `LdapTemplate.search(query, mapper)` khác nhau ra sao?
6. Vì sao `repository.findByUid("u1001")` không đồng nghĩa `findById(...)`?
7. Nếu user chuyển sang `ou=contractors`, điều gì xảy ra với DN đã lưu và tác vụ sync?
8. Nếu group chứa nhiều `member`, phải chọn kiểu Java và kiểm thử như thế nào để không mất giá trị?
9. Nếu cập nhật một field `mail`, vì sao có thể cần `modifyAttributes` thay vì cập nhật cả entity?
10. Khi mapper “không thấy mail”, làm sao phân biệt thiếu thuộc tính, ACL và mapping lỗi?

**Gợi ý tự đối chiếu:** `ObjectDirectoryMapper` phụ trách **chuyển đổi dữ liệu** theo annotation; `LdapTemplate` và hạ tầng JNDI thực hiện thao tác LDAP. DN là địa chỉ entry; `uid` chỉ là thuộc tính nghiệp vụ. `AttributesMapper` phù hợp DTO nhỏ, ODM phù hợp entity dùng lặp lại. Update và rename là các thao tác LDAP khác nhau. Với dữ liệu tùy chọn/đa trị, cần kiểm chứng schema và quyền thật.

## 20. Checklist và tổng kết

Trước khi đưa một entity ODM vào ứng dụng Spring Data LDAP, kiểm tra:

- [ ] Phân biệt rõ **`ObjectDirectoryMapper`**, `LdapTemplate`, `LdapRepository`, `ContextSource` và LDAP server.
- [ ] Entity có `@Entry` và `@Id Name`; import đúng `org.springframework.ldap.odm.annotations`.
- [ ] Các field dùng `@Attribute(name=...)` khớp tên LDAP thực và schema.
- [ ] `@DnAttribute` chỉ dùng khi property thực sự liên quan RDN theo contract ODM.
- [ ] Hiểu **DN tương đối** theo context base và ảnh hưởng khi đổi RDN/OU.
- [ ] Chọn ODM hay `AttributesMapper`/`ContextMapper` phù hợp lượng dữ liệu và thao tác.
- [ ] Thuộc tính vắng mặt, đa trị, binary được ánh xạ và kiểm thử đúng kiểu.
- [ ] Search có base/filter/scope an toàn; dùng LDAP filter builder/DN builder thay vì nối chuỗi input.
- [ ] Ghi dữ liệu theo schema, ACL và workflow nghiệp vụ; không giả định JPA dirty checking.
- [ ] Có tài khoản LDAP quyền tối thiểu, kết nối LDAPS/StartTLS xác minh chứng chỉ và audit thao tác ghi.
- [ ] Đã test với directory, gồm findByDn, repository, rename, thuộc tính thiếu, ACL và lỗi TLS.
- [ ] Có metric để phân biệt chi phí search LDAP với chi phí mapping object.

**Kết luận:** `ObjectDirectoryMapper` là mắt xích giúp Spring LDAP biến một LDAP entry có DN, `objectClass` và nhiều attributes thành Java entity theo metadata ODM, và hỗ trợ chiều ngược khi ghi. Nó hoạt động cùng `LdapTemplate` và repository chứ **không thay thế** tầng truy vấn, kết nối, schema hay ACL. Hiểu ranh giới này giúp xây ứng dụng Spring Data LDAP dễ bảo trì, dùng đúng mapping, an toàn khi CRUD và chẩn đoán lỗi chính xác hơn.
