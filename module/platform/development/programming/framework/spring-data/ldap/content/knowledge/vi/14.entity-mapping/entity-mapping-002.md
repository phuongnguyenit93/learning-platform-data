# Chọn đúng annotation ODM trong `org.springframework.ldap.odm.annotations`

Trong **Spring Data LDAP**, một entry của dịch vụ thư mục được biểu diễn thành đối tượng Java thông qua **Object-Directory Mapping (ODM)** của Spring LDAP. Để đọc, tìm kiếm và cập nhật dữ liệu bằng `LdapRepository` hoặc `LdapTemplate`, lập trình viên cần khai báo chính xác **kiểu entry**, **DN định danh**, **thuộc tính LDAP**, và những field chỉ dùng trong ứng dụng.

Các annotation này có tên gần giống annotation của JPA hoặc Spring Data nói chung, nhưng mang ý nghĩa riêng của LDAP. Chọn sai annotation có thể khiến repository không nhận diện entity, dựng sai DN, ghi nhầm thuộc tính, hoặc gửi dữ liệu không phù hợp schema lên directory.

Sau bài học, bạn sẽ có thể:

- Xác định đúng lúc dùng `@Entry`, `@Id`, `@Attribute`, `@DnAttribute` và `@Transient`.
- Phân biệt ánh xạ **DN/RDN** với ánh xạ **giá trị thuộc tính** của entry.
- Hiểu ánh xạ field mặc định, `@Attribute(readonly = true)`, thuộc tính nhiều giá trị và kiểu binary.
- Dựng entity cho Spring Data LDAP repository, tránh nhầm annotation từ JPA/Spring Data Commons.
- Nhận biết lỗi khi schema, `objectClass`, search base hoặc thông tin DN không khớp và kiểm thử entity với directory thật.

## 1. ODM đứng ở đâu trong Spring Data LDAP?

Giả sử directory có entry sau:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
```

`dn` định danh vị trí của entry trong **DIT (Directory Information Tree)**. `objectClass` khai báo các lớp trong schema mà entry tuân theo; những thuộc tính như `uid`, `cn`, `sn`, `mail` là dữ liệu thực của entry. Khi ứng dụng gọi `LdapTemplate` để tìm entry hoặc một phương thức `LdapRepository` để đọc đối tượng, Spring LDAP phải biết field Java nào tương ứng với các thành phần này.

```text
Directory (LDAP)                           Java (Spring LDAP ODM)
-----------------------------------        ---------------------------------
dn: uid=lan,ou=people,...          <----->  @Id Name dn
RDN: uid=lan                       <----->  @DnAttribute("uid") String uid
objectClass: inetOrgPerson, ...    <----->  @Entry(objectClasses={...})
cn: Nguyen Thi Lan                 <----->  @Attribute(name="cn") String fullName
mail: lan@example.org             <----->  @Attribute(name="mail") Set<String> mails
                                           @Transient String displayLabel (không lưu)
```

ODM khác ORM cho cơ sở dữ liệu quan hệ: **LDAP không có bảng hay khóa chính số tự tăng**. Entry được định danh bằng **DN**; tên tương đối **RDN** (ví dụ `uid=lan`) chỉ là một phần của DN. Schema LDAP còn quyết định những attribute nào có thể xuất hiện trên entry và hình thức giá trị của chúng.

## 2. Năm annotation trong `org.springframework.ldap.odm.annotations`

Đây là các annotation ánh xạ cốt lõi của Spring LDAP ODM. `@Entry` và `@Id` là bắt buộc cho một class được ODM quản lý; những annotation còn lại được dùng khi cần điều chỉnh ánh xạ field.

| Annotation | Đặt tại | Dùng khi nào | Điểm dễ nhầm |
| --- | --- | --- | --- |
| `@Entry` | Class | Khai báo các LDAP `objectClass` và base DN tương đối cho kiểu entry | Không phải `@Entity` của JPA; `objectClasses` phải phù hợp schema |
| `@Id` | Field kiểu `javax.naming.Name` | Lưu **DN** của toàn entry | Không phải `String uid`, không phải `org.springframework.data.annotation.Id` |
| `@Attribute` | Field | Đặt tên LDAP attribute khác tên Java hoặc khai báo binary, syntax, readonly | Nhiều field vẫn được ánh xạ theo tên mặc định dù không ghi `@Attribute` |
| `@DnAttribute` | Field kiểu `String` | Lấy giá trị RDN từ DN; tùy `index`, cho phép dựng DN từ các field | Không tự loại field khỏi ánh xạ LDAP attribute |
| `@Transient` | Field | Không đọc/ghi field như LDAP attribute | Có thể kết hợp với `@DnAttribute` để chỉ lấy giá trị từ DN |

Các import quan trọng:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Transient;
```

Tên gói là `org.springframework.ldap.odm.annotations`, ngay cả khi ứng dụng đang sử dụng **Spring Data LDAP repositories**. Các annotation từ `jakarta.persistence` hoặc `org.springframework.data.annotation` không thay thế được cơ chế ánh xạ ODM của Spring LDAP.

## 3. `@Entry`: khai báo loại entry và vùng gốc

```java
@Entry(
    base = "ou=people",
    objectClasses = { "top", "person", "organizationalPerson", "inetOrgPerson" }
)
public class Person {
    // Các field ODM...
}
```

`@Entry` đặt trên class Java và có hai thành phần chính:

- **`objectClasses` (bắt buộc):** danh sách các LDAP object class của entry được ánh xạ. Chọn các lớp thực tế cần cho các thuộc tính mà entity quản lý, kể cả các lớp kế thừa liên quan. Khi **tạo** entry mới, ODM dùng danh sách được khai báo để ghi `objectClass`; vì vậy danh sách thiếu lớp có thể gây lỗi schema hoặc không phản ánh đúng entity.
- **`base` (không bắt buộc, mặc định rỗng):** DN của nhánh gốc dành cho kiểu entity. Ví dụ `ou=people` thường được diễn giải tương đối so với base DN cấu hình trong `ContextSource` (chẳng hạn `dc=example,dc=org`).

**`base` không phải RDN của chính người dùng.** Với `@Entry(base = "ou=people")`, DN của Lan vẫn cần phần `uid=lan` để tạo thành `uid=lan,ou=people,...`.

`objectClass` không chỉ là nhãn tùy ý. Schema của `inetOrgPerson` kế thừa từ `organizationalPerson` và `person`; ví dụ ở trên khai báo trọn bộ các class xuất hiện trong entry. Việc gắn thêm thuộc tính không được cho phép bởi các class đã khai báo có thể làm server từ chối thao tác `create`/`update`. Đối chiếu schema directory trước khi chọn class, nhất là với schema riêng của doanh nghiệp.

## 4. `@Id`: ánh xạ DN, không phải một attribute thông thường

```java
@Id
private Name dn;
```

`@Id` xác định field mang **Distinguished Name** của entry và phải áp dụng lên kiểu `javax.naming.Name` (chẳng hạn đối tượng `LdapName`). Ví dụ:

```text
DN của Lan:
uid=lan,ou=people,dc=example,dc=org

RDN của Lan:
uid=lan

Giá trị thuộc tính uid:
lan
```

Ba giá trị này khác nhau. `uid` thường được chọn làm RDN, nhưng `uid=lan` có thể xuất hiện dưới nhiều OU khác nhau; **DN đầy đủ** mới định danh vị trí entry trong DIT.

### Chọn đúng `@Id` khi viết repository

```java
import javax.naming.Name;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    // Thêm các phương thức tìm kiếm khi cần.
}
```

`LdapRepository` của Spring Data LDAP có **một tham số kiểu entity**; kiểu ID được cố định theo `Name`. Không viết `LdapRepository<Person, Long>` như repository cho cơ sở dữ liệu quan hệ và không đánh dấu field `String uid` bằng `@Id`.

### Đừng ghép DN bằng chuỗi tùy ý

Khi cần dựng DN từ input, nên dùng API dành cho DN để xử lý các ký tự đặc biệt:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name personDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", userUid)
        .build();
```

Đoạn trên tạo **DN tương đối** với base của `ContextSource` nếu ứng dụng được cấu hình như ví dụ. Quy tắc escape DN (RFC 4514) **khác** escape giá trị search filter (RFC 4515), vì vậy không dùng thao tác escape của filter để ghép một DN.

## 5. `@Attribute`: ánh xạ giá trị attribute của entry

Theo mặc định, **các field hợp lệ trên entity ODM được ánh xạ sang LDAP attribute có cùng tên field** nếu không dùng annotation thay đổi điều đó. Đây là một điểm rất dễ bỏ sót khi lập trình viên quen JPA và cho rằng chỉ field có annotation mới được lưu.

Ví dụ:

```java
// Field Java tên "description" -> LDAP attribute "description" theo mặc định.
private String description;

// Tên field khác tên LDAP attribute: cần khai báo ánh xạ.
@Attribute(name = "cn")
private String fullName;

@Attribute(name = "mail")
private Set<String> emailAddresses;
```

Nếu `fullName` không có `@Attribute(name = "cn")`, ODM sẽ cố ánh xạ theo tên `fullName`, trong khi schema `inetOrgPerson` thường dùng `cn`. Hậu quả có thể là đọc không có dữ liệu, tạo hoặc cập nhật entry sai attribute và bị server từ chối.

### 5.1. Các thuộc tính cấu hình của `@Attribute`

| Thuộc tính | Tác dụng | Trường hợp dùng |
| --- | --- | --- |
| `name` | Tên LDAP attribute cần ánh xạ; để trống sẽ dùng tên field Java | `@Attribute(name = "cn")` cho `fullName` |
| `readonly` | Đọc giá trị nhưng không ghi lại attribute khi persist | Thuộc tính hoạt động chỉ đọc như `modifyTimestamp` |
| `type` | Khai báo LDAP/JNDI trả về chuỗi (`STRING`) hay byte (`BINARY`) | `jpegPhoto`, dữ liệu nhị phân |
| `syntax` | Chuỗi OID syntax LDAP phục vụ xác định phép chuyển đổi kiểu khi cần | Trường hợp converter yêu cầu syntax cụ thể |

Ví dụ về thuộc tính chỉ đọc:

```java
@Attribute(name = "modifyTimestamp", readonly = true)
private String lastModifiedAt;
```

`readonly = true` dùng khi entity cần **nhận** giá trị từ LDAP nhưng không gửi lại giá trị đó trong thao tác ghi. Một số thuộc tính vận hành như `modifyTimestamp` có thể không được LDAP server trả về trong truy vấn thông thường, nên cần yêu cầu thuộc tính phù hợp và kiểm tra quyền đọc; gắn annotation không tự tạo ra giá trị.

Ví dụ về dữ liệu nhị phân:

```java
@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
private byte[] jpegPhoto;
```

Kiểu dữ liệu Java và syntax trong schema phải tương thích. `Type.BINARY` thể hiện cách JNDI xử lý giá trị; không tự chuyển một thuộc tính vốn chỉ cho phép chuỗi thành binary. Nếu cần kiểu dữ liệu phức tạp hoặc chuyển đổi riêng, sử dụng `ConversionService`/converter được Spring LDAP hỗ trợ và xác minh trên directory thật.

### 5.2. Thuộc tính nhiều giá trị

LDAP attribute có thể chứa nhiều giá trị, nên Java entity có thể dùng kiểu collection phù hợp:

```java
@Attribute(name = "mail")
private Set<String> emailAddresses;
```

Với các thuộc tính là DN tham chiếu, Spring LDAP ODM hỗ trợ những collection chứa `javax.naming.Name`. Chẳng hạn entry nhóm theo schema `groupOfUniqueNames` có thể ánh xạ `uniqueMember` thành `Set<Name>`:

```java
@Attribute(name = "uniqueMember")
private Set<Name> memberDns;
```

Hãy kiểm tra schema của attribute: một field Java có kiểu `Set` không làm cho một LDAP attribute đơn trị (*SINGLE-VALUE*) trở thành đa trị. Đồng thời, các thuộc tính nhiều giá trị thường không bảo đảm thứ tự nghiệp vụ; nếu cần thứ tự, phải có mô hình lưu trữ khác được schema hỗ trợ.

## 6. `@DnAttribute`: lấy và tạo các thành phần RDN

`@DnAttribute` liên kết một field Java kiểu **`String`** với một thành phần của **DN**. Nó khác `@Id` ở chỗ `@Id` là toàn bộ DN, còn `@DnAttribute` chỉ là một giá trị trong RDN.

```java
@DnAttribute(value = "uid", index = 0)
private String uid;
```

Với `@Entry(base = "ou=people")`, DN của Lan là `uid=lan,ou=people,dc=example,dc=org`. Field `uid` được đọc từ RDN `uid=lan`, và `index = 0` cho phép ODM sử dụng field này để tính DN trong những thao tác tạo hoặc cập nhật, khi các thành phần cần thiết đã khai báo đầy đủ.

Một điểm then chốt: **`@DnAttribute` không tự vô hiệu ánh xạ attribute bình thường**. Nếu class có field `String uid` gắn `@DnAttribute`, field đó thông thường cũng được ánh xạ vào LDAP attribute `uid`. Điều này thích hợp khi RDN của entry cũng phải hiện diện dưới dạng attribute. Nếu muốn field **chỉ dùng để cấu thành DN**, kết hợp `@DnAttribute` với `@Transient`.

### 6.1. Dùng `index` đúng theo vị trí DN

Ví dụ DN của Lan nằm trong OU bộ phận:

```text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
```

Nếu `@Entry(base = "ou=people")`, các thành phần còn lại được ánh xạ như sau:

```java
@DnAttribute(value = "ou", index = 0)
@Transient
private String department;

@DnAttribute(value = "uid", index = 1)
private String uid;
```

`index = 0` ở ví dụ này chỉ RDN **gần base nhất** (`ou=engineering`), còn `index = 1` chỉ RDN nằm ngoài nó (`uid=lan`). Với tất cả field `@DnAttribute` cần thiết đều có `index`, ODM có thông tin để tính DN cho create/update; nếu field tạo DN thay đổi, thao tác cập nhật có thể liên quan đến đổi tên hoặc chuyển vị trí entry trong DIT.

**Điều kiện quan trọng:** entry cha `ou=engineering,ou=people,...` phải tồn tại; thao tác chuyển vị trí cần quyền và hỗ trợ của LDAP server. Không tự coi việc sửa `department` là thay đổi một thuộc tính văn bản thông thường.

### 6.2. `@DnAttribute` không có `index` dùng để đọc thành phần DN

```java
@DnAttribute("uid")
private String uid;
```

Lối viết này có thể dùng để lấy `uid` từ DN của entry tìm được. Khi cần ODM **tự tính DN mới**, phải chỉ định `index` cho **mọi field `@DnAttribute`** liên quan theo hợp đồng API. Nếu không chủ động tính DN bằng các annotation, bạn có thể cung cấp `@Id Name dn` tường minh.

## 7. `@Transient`: field không lưu như LDAP attribute

`@Transient` của Spring LDAP được đặt lên những field chỉ phục vụ hiển thị, tính toán hoặc giữ dữ liệu trung gian của ứng dụng:

```java
@Transient
private String displayLabel;
```

Trường hợp kết hợp đáng nhớ:

```java
@DnAttribute(value = "ou", index = 0)
@Transient
private String departmentFromDn;
```

Field `departmentFromDn` vẫn có thể được đọc từ DN, nhưng **không** được ánh xạ thành LDAP attribute `departmentFromDn`. Sự khác biệt này hữu ích khi DIT đã chứa thông tin vị trí trong RDN, còn schema của entry không cho phép lưu thuộc tính tương ứng trên chính entry con.

Đừng nhầm `org.springframework.ldap.odm.annotations.Transient` với `jakarta.persistence.Transient`, `org.springframework.data.annotation.Transient` hoặc từ khóa Java `transient`: chúng phục vụ các framework/cơ chế khác. Trong entity LDAP, cần dùng đúng annotation của Spring LDAP ODM.

## 8. Ví dụ entity hoàn chỉnh: ánh xạ `inetOrgPerson`

Giả sử `LdapContextSource` có base `dc=example,dc=org`; người dùng nằm trực tiếp dưới `ou=people`. Entity dưới đây biểu diễn entry Lan với các annotation cần thiết:

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {

    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private Set<String> emailAddresses;

    @Attribute(name = "modifyTimestamp", readonly = true)
    private String lastModifiedAt;

    @Transient
    private String displayLabel;

    public Person() {
    }

    // Bổ sung getter/setter cho các field theo quy ước mã nguồn của dự án.
}
```

**Giải thích:**

| Field | Nguồn dữ liệu hoặc vai trò |
| --- | --- |
| `dn` | Toàn bộ DN LDAP, gắn với `@Id` |
| `uid` | RDN `uid=...`; đồng thời là thuộc tính LDAP `uid` theo ánh xạ mặc định |
| `fullName` | LDAP attribute `cn`, được đổi tên bằng `@Attribute` |
| `surname` | LDAP attribute `sn` bắt buộc theo lớp `person` |
| `emailAddresses` | Các giá trị thuộc tính `mail` nếu entry có |
| `lastModifiedAt` | Giá trị `modifyTimestamp` nếu server trả về, không được ghi ngược |
| `displayLabel` | Field chỉ dùng trong ứng dụng, không persist lên LDAP |

Ví dụ giả định `ou=people,dc=example,dc=org` đã tồn tại, tài khoản ứng dụng được cấp quyền phù hợp, các thuộc tính đáp ứng schema và `uid` là giá trị RDN hợp lệ. Khi tạo entry thực tế, cần có giá trị `cn`, `sn` và những thuộc tính bắt buộc khác theo schema triển khai.

### 8.1. Kết nối entity với repository

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {
    List<Person> findByUid(String uid);
}
```

Phương thức `findByUid` tìm theo **LDAP attribute** được ánh xạ từ field `uid`. Nó không thay thế truy vấn theo DN và không bảo đảm `uid` duy nhất trên toàn bộ DIT; hai nhánh con khác nhau có thể cùng giá trị `uid` nếu directory và chính sách nghiệp vụ cho phép. Dùng `List<Person>` khi ứng dụng không có ràng buộc duy nhất rõ ràng.

### 8.2. Truy xuất ODM bằng `LdapTemplate`

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Person lan = ldapTemplate.findByDn(relativeDn, Person.class);
```

Ở ví dụ này, `ldapTemplate` là bean đã được cấu hình kết nối tới directory. DN truyền cho `findByDn` được xây tương đối theo base của `ContextSource` đã giả định; phải kiểm tra quy tắc base trong cấu hình thực tế để tránh lặp `dc=example,dc=org` hai lần. `findByDn` dùng **DN** để xác định entry; repository `findByUid` dùng **attribute** để tìm.

Ngoài việc đọc, ODM còn hỗ trợ các thao tác `create`, `update`, `delete` thông qua `LdapTemplate` và các thao tác repository phù hợp. Annotation quyết định thông tin ánh xạ; server vẫn kiểm tra schema, DN cha, quyền ghi và ràng buộc toàn vẹn.

## 9. Chọn annotation theo tình huống

| Yêu cầu | Annotation hoặc cách viết | Vì sao |
| --- | --- | --- |
| Khai báo entity thuộc schema `inetOrgPerson` | `@Entry(objectClasses = {...})` | ODM nhận biết loại entry và các class cần ghi |
| Đặt vùng lưu user dưới OU cố định | `@Entry(base = "ou=people", ...)` | Xác định nhánh gốc cho entity |
| Lưu tên phân biệt của entry | `@Id Name dn` | DN là ID của LDAP entity |
| `fullName` trong Java tương ứng `cn` ở LDAP | `@Attribute(name = "cn")` | Tên field và tên thuộc tính khác nhau |
| Field Java và LDAP attribute cùng tên | Có thể không cần `@Attribute` | ODM có ánh xạ mặc định theo tên field |
| Đọc thời điểm sửa do server quản lý | `@Attribute(name = "modifyTimestamp", readonly = true)` | Không gửi lại giá trị vận hành khi persist |
| Ánh xạ ảnh theo dạng byte | `@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)` | JNDI cần xử lý giá trị dạng nhị phân |
| Đọc `uid` từ RDN và tính DN khi tạo entry | `@DnAttribute(value = "uid", index = 0)` | Liên kết giá trị field với RDN |
| Lấy OU từ DN nhưng không ghi nó như thuộc tính của người dùng | `@DnAttribute(value = "ou", index = 0)` + `@Transient` | Tách dữ liệu định danh với attribute |
| Chỉ giữ chuỗi hiển thị cho giao diện | `@Transient` | Bỏ field ra khỏi ánh xạ LDAP |

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Repository không xử lý entity đúng | Dùng `@Entity`/`@Id` của JPA hoặc Spring Data Commons | Kiểm tra import từ `org.springframework.ldap.odm.annotations` |
| Không tìm được entry theo ID | `@Id` đặt trên `String uid` hoặc DN thiếu/nhân đôi base | Dùng `Name` và xác minh DN tương đối với `ContextSource` |
| `fullName` không có giá trị | Field không khai báo `@Attribute(name = "cn")` | Kiểm tra tên attribute thực trong directory |
| Server báo schema violation khi tạo entry | `@Entry.objectClasses` thiếu lớp hoặc entity thiếu thuộc tính MUST | Đọc objectClass/schema và dữ liệu trước khi ghi |
| Update cố ghi thuộc tính vận hành | Field `modifyTimestamp` không đánh dấu `readonly` | Dùng `@Attribute(readonly = true)` nếu cần đọc |
| Field giao diện bị lưu thành LDAP attribute | Quên `@Transient`; ODM tự ánh xạ field theo tên | Đánh dấu các field không persist |
| `@DnAttribute` đưa thêm attribute lạ vào entry | Nghĩ rằng nó chỉ lấy thông tin từ DN | Phối hợp `@Transient` khi field chỉ nằm trong DN |
| Tính DN sai vị trí OU và UID | Gán `index` ngược hoặc thiếu `index` trên một số field DN | Kiểm tra thứ tự RDN so với `@Entry.base` |
| Chuyển entry khiến tham chiếu nhóm hỏng | Giá trị RDN thay đổi, DN cũ còn ở `member`/`uniqueMember` | Kiểm tra Modify DN, ACL, các tham chiếu và chính sách server |
| Dữ liệu binary/đa trị không ánh xạ đúng | Java type hoặc `@Attribute.type` không phù hợp schema | Kiểm tra LDAP syntax, kiểu JNDI và converter |

## 11. Kiểm thử ánh xạ với directory

Annotation đúng cú pháp Java chưa đảm bảo entry hợp lệ. Nên kiểm thử bằng LDAP server phục vụ phát triển hoặc directory test với schema tương đương môi trường chạy thật:

1. **Đọc entry có sẵn:** tạo một entry `inetOrgPerson` với DN, `uid`, `cn`, `sn`, `mail`; dùng `findByDn` hoặc repository để xác minh từng field.
2. **Đối chiếu DN và RDN:** kiểm tra `@Id` chứa DN mong đợi và `@DnAttribute("uid")` nhận đúng `uid` từ RDN.
3. **Kiểm tra field đổi tên:** xác minh `fullName` nhận dữ liệu từ `cn`; thêm một field không annotate vào entity thử nghiệm để hiểu cơ chế ánh xạ mặc định.
4. **Kiểm tra `@Transient`:** thay đổi `displayLabel`, gọi cập nhật trên entry thử nghiệm và xác minh directory không tạo attribute cùng tên.
5. **Kiểm tra readonly:** thử đọc `modifyTimestamp` khi directory cho phép; xác minh thao tác update không gửi lại thuộc tính server quản lý.
6. **Kiểm tra tạo entry:** khởi tạo object có `uid`, `cn`, `sn` và DN được chỉ rõ hoặc tính theo `@DnAttribute(index=...)`; xác minh entry được tạo trong OU mong đợi.
7. **Kiểm tra thay đổi RDN:** chỉ trong nhánh test, thử đổi giá trị tạo DN, xác minh DN mới, quyền đổi tên và các tham chiếu DN nếu có.
8. **Kiểm tra schema và lỗi:** cố tình bỏ thuộc tính bắt buộc trong một test độc lập để thấy lỗi từ directory; không dựa vào annotation để tự bỏ qua schema.

Nếu môi trường sử dụng chứng chỉ TLS và tài khoản dịch vụ, hãy giữ kết nối LDAP an toàn, cấp quyền tối thiểu cho bài thử và dùng dữ liệu giả. Khi tìm kiếm bằng filter dựa trên input, nên dùng `LdapQueryBuilder`/filter builder thay vì nối chuỗi để tránh LDAP injection; annotation ODM **không tự bảo vệ** mọi biểu thức filter được ứng dụng tự xây dựng.

## 12. Câu hỏi tự luyện

**Câu 1.** Class `Person` có `@Entry` và field `String uid` được đánh dấu bằng `org.springframework.data.annotation.Id`. Entity đã đúng chuẩn LDAP ODM chưa?

*Gợi ý:* Chưa. Cần `org.springframework.ldap.odm.annotations.Id` trên field kiểu `Name` chứa DN; field `uid` riêng dùng cho RDN/attribute.

**Câu 2.** Tại sao `@DnAttribute("ou")` trên field `department` có thể gây lỗi ghi attribute dù mục tiêu chỉ là đọc OU từ DN?

*Gợi ý:* Field vẫn được ODM ánh xạ theo tên thành LDAP attribute. Dùng thêm `@Transient` nếu nó chỉ phản ánh thành phần DN và schema entry không có `department`.

**Câu 3.** Field Java `fullName` phải ánh xạ vào LDAP `cn`. Nên chọn annotation nào?

*Gợi ý:* `@Attribute(name = "cn")`.

**Câu 4.** Với `@Entry(base = "ou=people")`, DN mong muốn là `uid=lan,ou=engineering,ou=people,dc=example,dc=org`. Chọn `index` như thế nào?

*Gợi ý:* `@DnAttribute(value = "ou", index = 0)` cho `engineering`; `@DnAttribute(value = "uid", index = 1)` cho `lan`. Hai thành phần phải được khai báo đầy đủ nếu muốn ODM tự tính DN.

**Câu 5.** Một attribute `modifyTimestamp` cần đọc để hiển thị nhưng server không cho sửa. Nên làm gì?

*Gợi ý:* Dùng `@Attribute(name = "modifyTimestamp", readonly = true)`; xác minh quyền đọc và cách yêu cầu operational attributes của server.

## 13. Ghi nhớ

- **`@Entry` + `@Id`** là nền tảng: một annotation nhận diện kiểu entry và base, một annotation giữ DN bằng `Name`.
- **`@Attribute`** ánh xạ giá trị thuộc tính; field không gắn annotation vẫn có thể được ánh xạ mặc định theo tên.
- **`@DnAttribute`** liên kết field `String` với RDN; khi cần tự tính DN, dùng `index` đầy đủ và đúng thứ tự.
- **`@Transient`** loại field khỏi ánh xạ attribute; kết hợp được với `@DnAttribute` để giữ thông tin DN mà không ghi thuộc tính.
- Spring Data LDAP repository phải sử dụng **annotation ODM của Spring LDAP**. Schema, quyền truy cập, search base và kiểm thử thực tế vẫn quyết định thao tác LDAP có thành công hay không.

**Tài liệu tham khảo:**

- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP API — Package `org.springframework.ldap.odm.annotations`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/package-summary.html)
- [Spring LDAP API — `DnAttribute`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/DnAttribute.html)
- [Spring LDAP API — `Attribute`](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.html)
- [Spring Data LDAP Reference — Configuration and Repositories](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- RFC 4512 (*LDAP Directory Information Models*); RFC 4514 (*String Representation of Distinguished Names*).
