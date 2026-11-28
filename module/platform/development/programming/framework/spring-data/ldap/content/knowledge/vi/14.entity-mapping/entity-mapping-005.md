# Dùng `@Id` với kiểu `javax.naming.Name`

Khi làm việc với **Spring Data LDAP**, ứng dụng Java thường ánh xạ một LDAP entry sang một entity bằng **Object–Directory Mapping (ODM)**. Khác với bảng quan hệ có khóa chính số như `Long id`, mỗi entry LDAP được định vị bằng **Distinguished Name (DN)** trong cây thư mục. Vì vậy, trường đánh dấu `@Id` của entity ODM cần dùng **`javax.naming.Name`** để giữ tên phân biệt của entry, chứ không phải `String` hoặc `Long` theo thói quen dùng JPA.

Bài thuộc chương **Ánh xạ thực thể** tập trung vào cách khai báo, xây dựng, đọc và quản lý `@Id private Name dn`. Người học sẽ hiểu DN/RDN, sự khác biệt giữa identifier và thuộc tính LDAP, quan hệ giữa DN đầy đủ với base của `LdapContextSource`, cách dùng `LdapRepository` và `LdapTemplate`, và những lưu ý về rename/move, schema, phân quyền, TLS và kiểm thử với directory.

## 1. DN là địa chỉ của entry trong cây LDAP

Một directory có thể lưu các entry dưới naming context `dc=example,dc=org`:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=u1001
│   └── uid=u1002
└── ou=groups
    └── cn=developers
```

Một entry người dùng:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Trong ví dụ:

- **`uid=u1001`** là *Relative Distinguished Name* (RDN) của entry đối với entry cha `ou=people`.
- **`ou=people,dc=example,dc=org`** là DN của parent.
- **`uid=u1001,ou=people,dc=example,dc=org`** là DN đầy đủ hiện tại, định vị entry cụ thể trong directory.
- **`uid`** và **`mail`** là các *thuộc tính* có thể được dùng trong LDAP filter; một giá trị `uid=u1001` riêng lẻ **không xác định đầy đủ vị trí** nếu entry có thể nằm ở nhiều OU.

DN không phải “primary key vô hướng” độc lập với cấu trúc dữ liệu. Nếu người dùng chuyển từ `ou=people` sang `ou=contractors`, entry có thể vẫn biểu diễn cùng danh tính nghiệp vụ nhưng **DN đã thay đổi**.

### DN và RDN khác nhau

| Thuật ngữ | Ví dụ | Ý nghĩa |
|---|---|---|
| RDN | `uid=u1001` | Tên của entry dưới đúng parent |
| DN parent | `ou=people,dc=example,dc=org` | Vị trí cha |
| DN đầy đủ | `uid=u1001,ou=people,dc=example,dc=org` | Vị trí duy nhất trong DIT tại thời điểm đó |
| Thuộc tính nghiệp vụ | `uid: u1001` | Giá trị để lọc/đối chiếu, không thay thế DN |
| Naming context/base server | `dc=example,dc=org` | Phạm vi directory được phục vụ trong ví dụ |

Trong một LDAP directory thực tế, uniqueness của thuộc tính `uid` hoặc `mail` phụ thuộc schema/ràng buộc nghiệp vụ và phạm vi. **Không lấy một giá trị thuộc tính chưa bảo đảm duy nhất làm khóa định danh entry toàn hệ thống**.

## 2. Tại sao `@Id` phải là `javax.naming.Name`?

Spring LDAP ODM nhận biết trường `@Id` là thuộc tính Java dùng để chứa **DN của entry**. Kiểu chuẩn cho trường này là **`javax.naming.Name`**, một interface JNDI đại diện cho tên được cấu trúc thành nhiều thành phần; khi xử lý LDAP, implementation thường là **`javax.naming.ldap.LdapName`**.

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Id;

@Id
private Name dn;
```

Ba điểm cần ghi nhớ:

1. **`@Id` không tương ứng với một LDAP attribute thông thường.** DN là địa chỉ của entry, không phải một cặp `uid: ...` mà có thể lưu vào field `Long id`.
2. **`javax.naming.Name` hiểu cấu trúc của tên.** Nó hỗ trợ thao tác thành phần/RDN; điều này tốt hơn việc lưu một chuỗi rồi tự phân tích dấu phẩy hoặc dấu bằng.
3. **`@Id` giúp ODM biết entity nằm ở entry nào** để ánh xạ và thực hiện các thao tác thích hợp. Nó không khiến LDAP tự tạo khóa mới như `IDENTITY` của SQL.

Đặc biệt, **Spring Boot 3 / Spring Framework 6 không biến kiểu này thành `jakarta.naming.Name`**. JNDI `javax.naming` là API của Java SE, khác các namespace Java EE đã đổi sang Jakarta. Khi khai báo entity LDAP, import đúng:

```java
import javax.naming.Name; // đúng cho JNDI LDAP
```

Đừng nhầm với `jakarta.persistence.Id` của JPA. `@Id` ở đây là **`org.springframework.ldap.odm.annotations.Id`**.

| JPA/SQL | Spring LDAP ODM |
|---|---|
| `@jakarta.persistence.Id` | `@org.springframework.ldap.odm.annotations.Id` |
| Thường là `Long`, `UUID`, `String`, ... | **`javax.naming.Name`** cho DN |
| Khóa chính thường không mã hóa đường dẫn bản ghi | DN chứa RDN và nhánh cha |
| Đổi vị trí bản ghi trong bảng không đổi khóa chính | Đổi RDN/OU có thể đổi DN |
| Sinh khóa theo database sequence/identity | DN thường được xác định từ quy tắc đặt tên directory |
| SQL schema và quan hệ | LDAP `objectClass`, attribute schema, DN và ACL |

## 3. Entity ODM đầy đủ với `@Entry`, `@Id` và `@Attribute`

Giả sử ứng dụng chỉ làm việc với `inetOrgPerson` dưới `ou=people`. Một entity minh họa:

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

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Vai trò từng annotation:

| Annotation | Đối tượng áp dụng | Ý nghĩa |
|---|---|---|
| `@Entry` | Class `DirectoryPerson` | Khai báo ODM mapping, base và các object class của entry |
| `@Id` | Field `Name dn` | Lưu DN định danh entry để ODM sử dụng |
| `@Attribute(name = "uid")` | Field `String uid` | Ánh xạ thuộc tính LDAP `uid` |
| `@Attribute(name = "cn")` | Field `String commonName` | Ánh xạ tên LDAP khác với tên property Java |
| `@Attribute(name = "mail")` | Field `String email` | Ánh xạ thuộc tính có thể tùy chọn |

**Không đặt đồng thời `@Id` và `@Attribute(name = "uid")` trên cùng một field để diễn tả hai ý nghĩa khác nhau.** `uid` là thuộc tính, còn DN trong `@Id` là vị trí entry. Nếu ứng dụng cần cả hai, hãy khai báo hai field riêng như ví dụ.

### Schema vẫn thuộc quyền LDAP server

`@Entry(objectClasses = ...)` không tạo schema LDAP. Server mới là nơi kiểm tra:

- Các `objectClass` cấu trúc và quan hệ kế thừa.
- Thuộc tính bắt buộc `MUST` (ví dụ `cn`, `sn` với lớp `person`).
- Thuộc tính được phép `MAY` (ví dụ `mail` tùy schema).
- Kiểu dữ liệu, matching rule và khả năng có nhiều giá trị.
- ACL của tài khoản bind đối với entry và từng thuộc tính.

Có field `@Attribute(name = "mail")` không có nghĩa entry nào cũng có `mail`; code và kiểm thử phải xử lý trường hợp thiếu giá trị.

## 4. `@Id` chứa DN tương đối hay DN đầy đủ?

Khi dùng Spring LDAP, rất dễ nhầm **DN trên LDAP server** với **DN truyền vào thao tác có context base**.

Giả sử Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Với `LdapContextSource` có base `dc=example,dc=org`, nhiều API của `LdapTemplate` và Spring LDAP ODM dùng **DN tương đối so với context base**.

| Thông tin | Giá trị |
|---|---|
| LDAP naming context root | `dc=example,dc=org` |
| Base trong `LdapContextSource` | `dc=example,dc=org` |
| `@Entry(base = "ou=people")` | Nhánh người dùng tương đối |
| DN đầy đủ của user | `uid=u1001,ou=people,dc=example,dc=org` |
| `Name` truyền cho `findByDn` / `findById` | `uid=u1001,ou=people` |

Nếu context base đã là `ou=people,dc=example,dc=org`, giá trị tương đối để truy cập cùng entry chỉ còn `uid=u1001`. Trong trường hợp ánh xạ ODM, **`@Entry(base = ...)` cũng phải được cân nhắc lại** cho nhất quán, tránh tạo truy vấn hoặc DN bị ghép thừa nhánh.

> **Quy ước để thực hành:** trong toàn bộ các ví dụ tiếp theo, context base là `dc=example,dc=org` và DN tương đối của user là `uid=u1001,ou=people`. Đừng lẫn ví dụ này với một ứng dụng đặt context base khác.

Chú ý: cách adapter/ODM quản lý tên trong từng tình huống có thể phụ thuộc base và API được sử dụng. Khi tích hợp với một directory đã tồn tại, **hãy kiểm thử giá trị `getDn()` được ánh xạ và DN dùng khi truy vấn** thay vì chỉ nhìn chuỗi hiển thị trên giao diện quản trị directory.

## 5. Xây `Name` an toàn bằng `LdapNameBuilder`

DN LDAP có cú pháp escape riêng. Một giá trị RDN có thể chứa dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược hoặc khoảng trắng cần xử lý đặc biệt. Vì vậy **không nối DN trực tiếp từ input**:

```java
// Không an toàn khi uid đến từ dữ liệu bên ngoài.
String dn = "uid=" + uid + ",ou=people";
```

Dùng API của Spring LDAP để xây tên:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public final class PersonDns {
    private PersonDns() {}

    public static Name relativeDnForUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid is required");
        }

        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
```

Gọi:

```java
Name dn = PersonDns.relativeDnForUid("u1001");
// Biểu diễn: uid=u1001,ou=people
```

`LdapNameBuilder` coi phần `uid` là **giá trị RDN**, không phải đoạn cấu trúc DN mới. Nó áp dụng escaping đúng cho DN. Nếu có input đặc biệt, ví dụ `team,east`:

```java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "team,east")
        .build();

// DN biểu diễn tương đương: uid=team\,east,ou=people
```

Dấu phẩy thuộc **giá trị UID**, không phải dấu phân tách RDN bổ sung.

### Escaping và phân quyền là hai việc riêng

Sử dụng `LdapNameBuilder` giúp tránh nhầm cú pháp DN, **không chứng minh người gọi được phép truy cập DN đó**. Trong ứng dụng thật còn phải:

- Kiểm tra UID theo quy tắc nghiệp vụ, giới hạn độ dài và ký tự cho phép.
- Xác định OU/tenant từ thông tin đã được xác thực thay vì nhận arbitrary DN từ client.
- Giới hạn quyền tài khoản LDAP bằng ACL.
- Không cho người dùng API tự chọn `ou=admins` hoặc naming context khác nếu chưa được ủy quyền.

**LDAP filter escaping khác DN escaping:** khi tìm theo UID nhưng không biết DN hiện tại, sử dụng `LdapQueryBuilder.where("uid").is(value)` hoặc `EqualsFilter`, không lấy phương thức xây DN thay thế việc xây filter.

## 6. Truy vấn repository bằng chính đối tượng `Name`

Với entity đã khai báo `@Id Name dn`, có thể xây repository:

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

Ở Spring Data LDAP, ID của repository gắn với **DN**, nên truy vấn một entry cụ thể có thể thực hiện:

```java
import java.util.Optional;
import javax.naming.Name;

Name id = PersonDns.relativeDnForUid("u1001");

Optional<DirectoryPerson> maybePerson =
        repository.findById(id);

maybePerson.ifPresent(person -> {
    Name loadedDn = person.getDn();
    System.out.println("Đã tải entry từ DN: " + loadedDn);
});
```

Ý nghĩa:

1. `findById(id)` nhận **`Name`**, không phải `String "u1001"` hoặc `Long 1001L`.
2. Repository dùng metadata ODM của `DirectoryPerson` để ánh xạ thuộc tính LDAP sang object Java.
3. `Optional.empty()` biểu diễn không tìm thấy theo contract repository; lỗi xác thực, timeout, ACL hoặc schema không nên bị tự động gộp thành “entry không tồn tại”.
4. DN có thể đổi khi entry bị move/rename. Một giá trị ID đã lưu từ trước có thể không còn trỏ tới entry hiện tại.

**Lưu ý về repository wiring:** phải có cấu hình repository scanning, `ContextSource` và `LdapTemplate` phù hợp. Nếu ứng dụng có nhiều LDAP context (đọc và ghi), repository phải thực sự dùng đúng template/source; một field `@Id` không tự chọn kết nối hay tài khoản bind.

### `findById` không phải `findByUid`

Hai ý định khác nhau:

| Ý định | Cách truy cập | Cần biết |
|---|---|---|
| Đọc entry theo địa chỉ hiện tại | `repository.findById(Name dn)` | DN chính xác |
| Đọc entry qua ODM mà không cần repository | `ldapTemplate.findByDn(dn, DirectoryPerson.class)` | DN chính xác |
| Tìm theo UID hoặc email khi không biết OU | `LdapTemplate.search(query, mapper)` / query method | Thuộc tính, filter và phạm vi tìm |
| Tìm mọi user theo họ | Repository query hoặc `search` | Search base và filter, có thể nhiều kết quả |

Nếu chỉ biết `uid=u1001` nhưng hệ thống có cả `ou=people` và `ou=contractors`, **không được đoán DN** rồi kết luận user không tồn tại khi lookup ở nhánh đoán thất bại. Cần tìm kiếm trong phạm vi được phép hoặc có bảng ánh xạ đáng tin cậy từ UID sang DN.

## 7. Đọc bằng `LdapTemplate.findByDn` và `lookup`

Spring LDAP cung cấp các thao tác truy cập entry trực tiếp. Với entity ODM:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

public final class PersonLookup {
    private final LdapTemplate ldapTemplate;

    public PersonLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryPerson getAtKnownDn(String uid) {
        Name relativeDn = PersonDns.relativeDnForUid(uid);
        return ldapTemplate.findByDn(
                relativeDn, DirectoryPerson.class);
    }
}
```

`findByDn` dùng mapping của `@Entry`, `@Id` và `@Attribute` để tạo entity. Nếu chỉ cần một vài thuộc tính tạo DTO, `lookup` với mapper có thể đơn giản hơn:

```java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;

Name dn = PersonDns.relativeDnForUid("u1001");

AttributesMapper<String> mapper = attrs -> {
    if (attrs.get("cn") == null) {
        return null;
    }
    return (String) attrs.get("cn").get();
};

String commonName = ldapTemplate.lookup(dn, mapper);
```

Trong ví dụ `lookup`, mapper chỉ nhận `Attributes`, không tự ánh xạ `@Id` hay `@Entry` thành entity. Muốn lấy DN, hãy dùng `Name` đã biết hoặc mapper/context phù hợp; không giả định có trường `dn` trong mọi tập thuộc tính LDAP.

| API | Kiểu kết quả | Sử dụng `@Id`? |
|---|---|---|
| `findByDn(dn, Entity.class)` | Entity ODM | Có |
| `repository.findById(dn)` | `Optional<Entity>` theo repository | Có |
| `lookup(dn, AttributesMapper<T>)` | DTO/giá trị do mapper tạo | Không tự ánh xạ entity |
| `search(query, mapper)` | Danh sách entry/DTO | Dựa trên query/filter, không phải một DN ID đầu vào |

## 8. Entity mới: cần DN hợp lệ trước khi ghi

Khi chuẩn bị tạo một LDAP entry mới, ứng dụng cần xác định **RDN và nhánh cha** trước khi thực hiện thao tác add/create. Không thể dựa vào `@Id` như một trường số tự tăng do database cấp.

Ví dụ chuẩn bị entity:

```java
DirectoryPerson person = new DirectoryPerson();

person.setDn(PersonDns.relativeDnForUid("u1003"));
person.setUid("u1003");
person.setCommonName("Chi Le");
person.setSurname("Le");
person.setEmail("chi.le@example.org");
```

Đây **chỉ là bước chuẩn bị object**, không tự tạo entry trên LDAP server. Tùy API CRUD dùng (`LdapTemplate` ODM, repository hoặc thao tác bind JNDI), bước ghi còn phải xét:

1. **Parent DN tồn tại:** `ou=people,dc=example,dc=org` đã có trên server.
2. **DN chưa bị chiếm:** chưa có entry `uid=u1003` cùng parent.
3. **Schema hợp lệ:** `inetOrgPerson` có các thuộc tính bắt buộc, cấu trúc object class phù hợp.
4. **ACL cho phép:** tài khoản bind có quyền add dưới đúng OU; không dùng tài khoản reader để tạo mới.
5. **Giá trị RDN nhất quán:** nếu RDN là `uid=u1003`, thuộc tính `uid` trên entry phải đáp ứng quy tắc server.
6. **Kết nối an toàn:** LDAPS hoặc StartTLS đã xác minh server; không truyền credentials/entry nhạy cảm qua cleartext.

Các API tạo entity của Spring LDAP có thể có quy ước về DN được dựng từ `@DnAttribute` hoặc từ `@Id` và trạng thái của entity. **Không mặc định `save()` sẽ tự sinh UID, tạo OU cha hay sửa schema.** Hãy kiểm tra contract CRUD của phiên bản đang dùng và thử trên directory riêng trước khi thao tác ghi thật.

### Khi nào cần `@DnAttribute`?

Bên cạnh `@Id`, Spring LDAP ODM cung cấp `@DnAttribute` để liên kết một property với **thành phần của DN** trong các kiểu mapping phù hợp. Ví dụ mang tính minh họa:

```java
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;

// Trong class @Entry đã có field @Id Name dn:
@Attribute(name = "uid")
@DnAttribute(value = "uid")
private String uid;
```

`@DnAttribute` giúp ODM biết giá trị property liên quan tới RDN; với DN chứa nhiều RDN cùng loại, có thể cần xác định vị trí/index theo API phiên bản thư viện. **`@DnAttribute` không thay thế `@Id` và không biến một UID thành DN toàn cục.** Đừng thêm annotation này vào mọi thuộc tính, vì `mail` và `sn` thường không phải thành phần DN của ví dụ.

## 9. Đổi tên hoặc chuyển OU làm thay đổi `@Id`

Nếu entry được chuyển từ:

```text
uid=u1001,ou=people,dc=example,dc=org
```

sang:

```text
uid=u1001,ou=contractors,dc=example,dc=org
```

thì DN đã đổi. Một thực thể Java được tải từ DN cũ và lưu lâu trong cache có thể chứa **`dn` đã lỗi thời**.

Khi cần rename/move và đã có quyền thực hiện, sử dụng thao tác chuyên dụng của LDAP thay vì chỉ sửa thuộc tính Java:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

// Ví dụ với context base = dc=example,dc=org.
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "u1001")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=contractors")
        .add("uid", "u1001")
        .build();

// Chỉ thực hiện khi workflow được phê duyệt và server/ACL hỗ trợ.
// ldapTemplate.rename(oldDn, newDn);
```

Việc đổi DN cần quan tâm:

- **`repository.save()` không phải lệnh rename tổng quát.** Thay field `dn` trong entity không có nghĩa server sẽ tự di chuyển entry đúng như mong muốn.
- **Parent ở đích phải tồn tại** và tài khoản cần đủ quyền đổi tên/di chuyển.
- **Tham chiếu dạng DN** trong các thuộc tính khác (ví dụ `member` của nhóm) có thể cần được kiểm tra lại; một số server có cơ chế cập nhật tham chiếu, một số không.
- **Định danh nghiệp vụ ổn định** có thể cần một thuộc tính riêng, như `entryUUID` ở một số directory hoặc `objectGUID` trong Active Directory (với quy tắc vòng đời riêng).
- **Cache và liên kết lưu DN** phải được làm mới; không cho một thao tác đọc bằng DN cũ trả “tài khoản đã bị xóa” nếu hệ thống thực tế vừa move user.

**Đặc biệt với Active Directory:** user thường có RDN `CN=...` chứ không nhất thiết `UID=...`. Quy tắc `PersonDns.relativeDnForUid` chỉ dùng khi cấu trúc directory thực sự có RDN `uid`. Đừng dùng cùng công thức cho mọi LDAP server.

## 10. `Name` là kiểu có cấu trúc và có thể thay đổi

`javax.naming.Name` là một interface JNDI với những thao tác như `get(int)`, `size()`, `add(...)`, `remove(...)`, `startsWith(...)` và `endsWith(...)`. Triển khai cho LDAP thường là `LdapName`.

```java
import javax.naming.Name;
import javax.naming.ldap.LdapName;

Name dn = new LdapName("uid=u1001,ou=people");

// So sánh hai DN theo parser thay vì nối/cắt chuỗi.
Name sameDn = new LdapName("uid=u1001,ou=people");
boolean same = dn.equals(sameDn); // true
```

Lợi ích của dạng cấu trúc là parser hiểu escaping và các thành phần RDN. Tuy nhiên, **`Name` có phương thức thay đổi nội dung**, ví dụ `add()` hoặc `remove()`. Vì vậy:

- Không dùng cùng một object `Name` có thể bị sửa làm khóa map/cache dùng chung giữa các thread.
- Nếu cần mở rộng DN, tạo **bản mới** từ thông tin đã kiểm tra; đừng âm thầm mutate ID của entity đã tải.
- Khi đưa DN ra DTO/log, hãy ghi rõ đó là **DN đầy đủ** hay **DN tương đối với context base**.
- Không so DN bằng cách cắt chuỗi theo dấu phẩy hoặc đổi chữ hoa/thường tùy ý. So sánh DN trên client cũng **không thay thế** matching rule, alias/referral và định danh thực ở server.

Một ví dụ parse DN có ký tự escape:

```java
import javax.naming.ldap.LdapName;

LdapName escaped = new LdapName(
        "uid=team\\,east,ou=people");

System.out.println(escaped);
// uid=team\,east,ou=people
```

Trong string Java, `\\` biểu diễn **một** ký tự backslash trong giá trị truyền cho `LdapName`. Với trường hợp dựng từ dữ liệu nhập, ưu tiên `LdapNameBuilder` để tránh nhầm số lớp escaping.

## 11. Bảo mật khi nhận DN từ bên ngoài

Một hệ thống có thể nhận HTTP request kiểu `GET /users/{id}`. Nếu `id` là một UID được duyệt, ứng dụng có thể xây DN theo OU cố định rồi lookup. Nhưng nếu client được gửi nguyên chuỗi DN như:

```text
cn=svc-admin,ou=service-accounts,dc=example,dc=org
```

và ứng dụng dùng nó để lookup mà không kiểm tra quyền, client có thể cố truy cập một entry ngoài phạm vi nghiệp vụ.

Thiết kế an toàn nên:

1. **Không nhận DN tùy ý như quyền truy cập.** UID hoặc ID nghiệp vụ phải được kiểm tra và ánh xạ tới nhánh đã duyệt.
2. **Giới hạn search base/OU:** dùng DN builder từ thành phần do ứng dụng kiểm soát.
3. **Áp dụng authorization của người gọi API** trước khi truy vấn hoặc trả thuộc tính.
4. **Sử dụng tài khoản bind chỉ đọc** cho các thao tác lookup/search; cấp ACL tới đúng entry/attribute, không dùng admin cho nhu cầu đọc phổ thông.
5. **Bảo vệ kết nối bằng LDAPS hoặc StartTLS** với xác thực certificate chain/hostname, secret được quản lý phù hợp.
6. **Không log toàn bộ DN/attribute nhạy cảm** nếu không cần; che thông tin cá nhân và tránh đưa giá trị UID/email vào nhãn metric có cardinality cao.

**Escaping DN chỉ giải quyết vấn đề cú pháp**, không thay thế kiểm tra xem DN đó có nằm trong miền được phép và entry đó có thể được trả cho người dùng cuối hay không.

## 12. Lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Entity không map được ID | Dùng `String`/`Long` hoặc sai `@Id` import | Khai báo `javax.naming.Name` và import ODM `Id` |
| `findById` không thấy entry | DN chưa đúng RDN/OU hoặc nhầm relative/full DN | So DN thực với base của context và `@Entry` |
| Lookup báo `NameNotFoundException` | Base sai, entry move/rename, DN bị ghép hai lần | Kiểm tra đường dẫn hiện tại; không tự nâng search ra toàn domain |
| Entity đọc được nhưng `uid` null | Thuộc tính không có, ACL che, mapping `@Attribute` sai | Kiểm tra schema, tên thuộc tính và quyền đọc |
| Tạo entity thất bại | DN trùng, parent thiếu, schema MUST/ACL không thỏa | Đối chiếu server entry/parent và quyền add |
| `save()` không di chuyển entry | Thay `@Id` không phải rename operation | Dùng workflow rename/move có kiểm soát |
| DN có dấu phẩy bị tách sai | Ghép chuỗi từ input không escape | Dùng `LdapNameBuilder` |
| User chuyển OU bị coi là xóa | Ứng dụng lưu DN cũ như ID bất biến | Theo dõi khóa nghiệp vụ ổn định/refresh mapping |
| Bị từ chối dù DN đúng | ACL, bind account, TLS hoặc server policy | Phân loại lỗi authentication/authorization/transport |
| Kết quả repository khác tìm kiếm theo thuộc tính | `findById` cần DN; search dùng filter/scope | Chọn API theo dữ liệu đầu vào thực tế |
| Mô hình AD sai DN | Giả định mọi user có RDN `UID=...` | Xác minh DN/schema thực tế trên AD |

Khi kiểm tra lỗi, ghi nhận **endpoint LDAP, base, OU, loại operation và mã lỗi**; tránh xuất credential hoặc dữ liệu danh tính không cần thiết. Một lỗi tìm kiếm rỗng không chứng minh toàn directory không có entry, và lỗi TLS không nên bị thay thế bằng cơ chế kết nối cleartext.

## 13. Kiểm thử với JUnit và directory thực

Có hai lớp kiểm thử cần tách:

### 13.1. Unit test DN builder

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class PersonDnsTest {

    @Test
    void buildsRelativeDnWithExpectedParent() throws Exception {
        Name id = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "u1001")
                .build();

        assertEquals(new LdapName("uid=u1001,ou=people"), id);
    }

    @Test
    void escapesCommaInRdnValue() throws Exception {
        Name id = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "team,east")
                .build();

        assertEquals(
                new LdapName("uid=team\\,east,ou=people"),
                id);
    }
}
```

Hai test này chứng minh **cách dựng và parse DN**, không xác minh entry có tồn tại hoặc account có quyền truy cập directory. Nếu chính sách UID của ứng dụng không cho phép dấu phẩy, vẫn có thể dùng giá trị đặc biệt trong unit test để kiểm chứng escaping ở tầng thư viện, đồng thời validation nghiệp vụ có quyền từ chối giá trị đó.

### 13.2. Integration test ODM trên LDAP test

Chuẩn bị directory thử nghiệm có `dc=example,dc=org`, `ou=people` và entry `uid=u1001` theo schema phù hợp. Với `ContextSource` đã cấu hình base, thử:

- `repository.findById(new LdapName("uid=u1001,ou=people"))` trả entity đúng.
- `entity.getDn()` chứa tên định vị entry theo quy ước context của thử nghiệm.
- `entity.getUid()`, `getCommonName()` và `getSurname()` khớp thuộc tính LDAP.
- DN không tồn tại trả kết quả không tìm thấy theo API phù hợp.
- DN cùng RDN dưới OU khác không bị nhận nhầm thành entry trong `ou=people`.
- Mô hình thiếu `@Id` hoặc dùng sai kiểu `String` bị phát hiện khi khởi tạo/ánh xạ (trong môi trường test riêng).
- Tài khoản chỉ đọc có thể search/lookup nhưng **không** thực hiện modify ngoài ACL; tránh thử quyền ghi trên dữ liệu production.
- Nếu entry đổi OU, truy vấn DN cũ và DN mới phản ánh đúng thay đổi; cập nhật cache/tham chiếu theo thiết kế.
- Ký tự DN cần escape, thuộc tính tùy chọn thiếu và thuộc tính đa trị được xử lý đúng.
- LDAPS/StartTLS xác minh chứng chỉ, server timeout hoặc lỗi authentication được phân loại đúng.

Khi so kết quả, kiểm tra **DN và thuộc tính cụ thể**, không chỉ số lượng. Một integration test với mock repository sẽ không phát hiện được base DN bị ghép sai hoặc ACL directory ngăn đọc.

### Ma trận kiểm thử ngắn

| Tình huống | Kỳ vọng |
|---|---|
| `@Id Name dn` và RDN hợp lệ | Load đúng entry |
| ID là `String` | Không phù hợp contract ODM |
| Chỉ truyền `uid=u1001` khi context base là domain root | Không tự tìm trong `ou=people` |
| Truyền DN đầy đủ vào API cần DN tương đối | Không âm thầm chấp nhận việc ghép base sai |
| Dấu phẩy trong RDN | Được escape và parse đúng |
| Entry khác OU cùng `uid` | Hai DN không bị nhầm nhau |
| Rename/move entry | DN cũ có thể hết hiệu lực |
| Thiếu `mail` | Entity xử lý thuộc tính tùy chọn |
| Bind account thiếu ACL | Không đọc/ghi vượt quyền |
| TLS/chứng chỉ lỗi | Kết nối thất bại an toàn |

## 14. Bài tập thực hành

Cho LDAP directory có base `dc=example,dc=org` và ba entry:

```text
uid=u1001,ou=people,dc=example,dc=org
uid=u1001,ou=contractors,dc=example,dc=org
cn=An Nguyen,ou=people,dc=corp,dc=example,dc=org
```

Một ứng dụng dùng `LdapContextSource` với base `dc=example,dc=org` và entity `DirectoryPerson` từ phần 3.

Hãy trả lời:

1. Giá trị `Name` tương đối để dùng `findById` cho entry đầu tiên là gì?
2. Chỉ biết `uid=u1001` có đủ chọn entry đầu tiên hay thứ hai không? Vì sao?
3. Entity có `@Id private String uid;` sẽ sai ở chỗ nào?
4. Khi nhận UID chứa dấu phẩy, nên xây DN theo API nào?
5. Có nên gắn `@DnAttribute` cho cả `mail` và `sn` không?
6. Nếu entry đầu tiên chuyển từ `ou=people` sang `ou=contractors`, điều gì xảy ra với `@Id`/cache đã lưu DN cũ?
7. Vì sao entry thứ ba không thể tự giả định có cùng đường đi `uid=...` với hai entry đầu?
8. Nếu account reader đọc được user nhưng không modify được `mail`, đó là lỗi `@Id` hay hành vi ACL đúng?

**Gợi ý đáp án:** ID của entry đầu là `uid=u1001,ou=people`. UID không tự xác định OU. `@Id` phải giữ **`Name` của DN** và khác `@Attribute(name="uid")`. Sử dụng `LdapNameBuilder` để escape RDN; `mail`/`sn` không phải thành phần DN trong ví dụ. Sau move cần xác minh DN mới và làm mới cache/identity mapping. Với hệ thống có RDN `cn=...` hoặc naming context khác, phải dùng đúng DN thực. Quyền read không kèm quyền modify là thiết kế ACL mong muốn.

## 15. Checklist và tổng kết

Trước khi hoàn thành một entity mapping Spring Data LDAP, hãy tự kiểm tra:

- [ ] Entity có `@Entry` và **`@Id` kiểu `javax.naming.Name`**, import đúng annotation Spring LDAP ODM.
- [ ] Phân biệt **DN**, **RDN**, context base và `@Entry(base)` với thuộc tính nghiệp vụ `uid`, `cn`, `mail`.
- [ ] Có quy tắc dựng DN bằng **`LdapNameBuilder`**, không ghép input trực tiếp thành DN.
- [ ] `LdapRepository.findById` nhận **`Name`**; search theo thuộc tính dùng filter builder và phạm vi tìm kiếm phù hợp.
- [ ] Không giả định `save()` tự sinh DN hoặc thay đổi OU; rename/move được xử lý theo workflow riêng.
- [ ] Kiểm tra `objectClass`/schema, thuộc tính thiếu/đa trị và DN đúng với server thực tế (đặc biệt AD).
- [ ] Giới hạn truy cập bằng ACL, phân quyền ứng dụng và LDAPS/StartTLS, không dựa vào escaping như cơ chế phân quyền.
- [ ] Có unit test DN escaping và integration test với directory để xác minh mapping, phạm vi, lỗi, rename và ACL.

**Kết luận:** trong Spring Data LDAP ODM, **`@Id` gắn với `javax.naming.Name` vì định danh của LDAP entry là DN trong cây thư mục**. Sử dụng `Name` đúng cách giúp repository và `LdapTemplate` truy cập entry chính xác, nhưng cần luôn hiểu base DN, RDN, schema, sự thay đổi DN và quyền trên directory. Khi những yếu tố này được thiết kế và kiểm thử nhất quán, việc ánh xạ LDAP entry sang Java object sẽ rõ ràng và an toàn hơn.
