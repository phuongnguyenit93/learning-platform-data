# Ánh xạ thuộc tính bằng @Attribute

Trong **Spring Data LDAP**, ứng dụng Java có thể đọc và cập nhật entry trong directory thông qua repository, hoặc dùng **Spring LDAP Object-Directory Mapping (ODM)** với `LdapTemplate`. Một entry LDAP không phải một hàng SQL: nó có **Distinguished Name (DN)**, tập `objectClass` và các **thuộc tính theo schema**. Khi xây entity Java, cần chỉ rõ trường nào tương ứng với thuộc tính LDAP nào, dữ liệu được trả dưới dạng chuỗi hay nhị phân, thuộc tính nào được phép ghi và khi nào cần bộ chuyển đổi kiểu.

Annotation **`org.springframework.ldap.odm.annotations.Attribute`** phục vụ đúng mục đích đó: mô tả cách ánh xạ một **field Java** sang một **LDAP attribute**. Nó không phải `javax.naming.directory.Attribute` (đối tượng kết quả của JNDI), cũng không phải `@Column` của JPA.

Bài học tập trung vào **`@Attribute`**, trong mối liên hệ vừa đủ với `@Entry`, `@Id`, `@DnAttribute` và `@Transient`. Sau khi học, bạn có thể:

- Ánh xạ đúng tên field Java với tên attribute LDAP, kể cả khi hai tên khác nhau.
- Nắm bốn tùy chọn của annotation: `name`, `type`, `syntax` và `readonly`, cùng giá trị mặc định.
- Biểu diễn giá trị đơn, đa trị, DN tham chiếu và nhị phân bằng kiểu Java thích hợp.
- Phân biệt định danh DN với dữ liệu attribute, tránh sửa DN ngoài ý muốn.
- Tạo, đọc và cập nhật entity bằng `LdapTemplate` hoặc `LdapRepository`.
- Chẩn đoán lỗi chuyển kiểu, thiếu attribute, lỗi schema và quyền truy cập; kiểm thử trên directory thử nghiệm.

## 1. Từ LDAP entry đến Java entity

Giả sử directory phục vụ naming context `dc=example,dc=org` với hai OU:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=mai
└── ou=groups
    └── cn=backend
```

Entry của Lan có thể được biểu diễn bằng LDIF:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
givenName: Thi Lan
mail: lan@example.org
mail: lan.work@example.org
description: Backend engineer
```

Các phần này có vai trò khác nhau:

| Dữ liệu LDAP | Vai trò | Tương ứng ở Java |
| --- | --- | --- |
| `dn: uid=lan,ou=people,...` | Tên phân biệt, xác định vị trí entry trong DIT | Field `@Id Name dn` |
| `objectClass` | Chọn các loại entry và thuộc tính được phép theo schema | `@Entry(objectClasses = {...})` |
| `uid: lan` | Một thuộc tính của entry; đồng thời được dùng làm RDN trong ví dụ | `@Attribute(name = "uid") String uid` |
| `cn: Nguyen Thi Lan` | Common name | `@Attribute(name = "cn") String fullName` |
| `sn: Nguyen` | Surname, bắt buộc với `person` | `@Attribute(name = "sn") String surname` |
| `givenName: Thi Lan` | Given name | `@Attribute(name = "givenName") String givenName` |
| Hai dòng `mail` | Attribute LDAP có nhiều giá trị | `@Attribute(name = "mail") Set<String> emails` |

**`dn` và `uid` không đồng nghĩa.** DN là đường tên có parent, còn `uid` là một giá trị thuộc tính. Hai entry có thể cùng `uid=lan` nhưng ở hai OU khác nhau. Nếu một entity chỉ lưu UID mà bỏ DN, ứng dụng có thể không biết cần cập nhật entry nào.

## 2. Annotation @Attribute thuộc package nào?

Import đúng:

```java
import org.springframework.ldap.odm.annotations.Attribute;
```

Nó là annotation gắn lên **field** của một class có `@Entry`:

```java
@Attribute(name = "cn")
private String fullName;
```

Spring LDAP ODM sẽ liên hệ field `fullName` với attribute **`cn`** của entry. Khi **đọc**, ODM ánh xạ giá trị LDAP sang field Java; khi **tạo/cập nhật**, ODM dùng mapping để xây các attribute cần ghi, trừ những field được cấu hình read-only hoặc bị bỏ qua.

Phân biệt các loại tên dễ trùng:

```java
// Annotation ánh xạ của Spring LDAP ODM:
org.springframework.ldap.odm.annotations.Attribute

// Interface JNDI biểu diễn một attribute ở kết quả tra cứu:
javax.naming.directory.Attribute

// Annotation ORM/JPA, không tự tạo mapping LDAP:
jakarta.persistence.Column
```

Đừng import nhầm rồi dùng code ví dụ: Spring LDAP ODM không dựa vào `@Column(name = "...")` để suy ra tên thuộc tính LDAP.

### 2.1. @Attribute không phải điều kiện bắt buộc cho mọi field

Theo Spring LDAP ODM, **các field không có annotation đặc biệt cũng có thể được ánh xạ theo chính tên field**. Ví dụ:

```java
@Entry(objectClasses = {"top", "person"})
public class SimplePerson {
    @Id
    private Name dn;

    private String description; // LDAP attribute description

    @Attribute(name = "cn")
    private String fullName;    // LDAP attribute cn, không phải fullName
}
```

Trong đoạn minh họa, cần import `javax.naming.Name` và `org.springframework.ldap.odm.annotations.Entry`/`Id`. Class thực tế còn phải phù hợp schema, chẳng hạn bảo đảm `sn` khi tạo entry thuộc `person`.

Đây là điểm khác biệt quan trọng với cách suy luận “không có `@Attribute` thì không được lưu”: **trong Spring LDAP ODM, việc bỏ annotation không nhất thiết có nghĩa bỏ mapping**. Muốn loại field khỏi ánh xạ LDAP, dùng **`@Transient` của Spring LDAP ODM**.

## 3. Bốn tùy chọn của @Attribute

Javadoc của `org.springframework.ldap.odm.annotations.Attribute` định nghĩa bốn element tùy chọn:

| Tùy chọn | Kiểu | Giá trị mặc định | Công dụng |
| --- | --- | --- | --- |
| `name` | `String` | `""` | Tên attribute LDAP; chuỗi rỗng nghĩa là dùng tên field Java |
| `type` | `Attribute.Type` | `STRING` | Cho biết kiểu giá trị JNDI được xem là `String` hay `byte[]` |
| `syntax` | `String` | `""` | OID của LDAP syntax, hỗ trợ lựa chọn converter chính xác hơn |
| `readonly` | `boolean` | `false` | Đọc field khi dữ liệu có sẵn, nhưng **không persist** field này lên LDAP |

Ví dụ cú pháp:

```java
@Attribute(name = "cn")
private String fullName;

@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
private byte[] photo;

@Attribute(name = "modifyTimestamp", readonly = true)
private String modifiedAt;
```

**Không có parameter `value` trong `@Attribute`.** Vì thế, cách viết `@Attribute("cn")` không phải dạng rút gọn hợp lệ; phải dùng `@Attribute(name = "cn")`. Đây là lỗi dễ xảy ra khi chuyển từ những annotation Java khác có element `value()`.

### 3.1. name: ánh xạ theo tên khác nhau

```java
@Attribute(name = "cn")
private String displayName;

@Attribute(name = "givenName")
private String firstName;

@Attribute(name = "sn")
private String surname;
```

LDAP dùng tên chuẩn từ schema; phía Java có thể dùng tên phù hợp nghiệp vụ. Tên `displayName` ở field không tự khiến ODM truy cập LDAP attribute `displayName` khi đã khai báo `name = "cn"`.

Ngược lại:

```java
@Attribute
private String description;
```

và:

```java
@Attribute(name = "description")
private String description;
```

đều ánh xạ tới attribute `description` vì `name` mặc định rỗng. **Chỉ sử dụng tên thật có trong schema**, không tự đặt tên LDAP mới như `employeeNickname` rồi kỳ vọng directory chấp nhận nếu schema chưa hỗ trợ.

### 3.2. type: STRING hoặc BINARY

```java
@Attribute(name = "cn", type = Attribute.Type.STRING)
private String fullName;

@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
private byte[] jpegPhoto;
```

`STRING` là mặc định, còn `BINARY` biểu thị dữ liệu được xử lý như `byte[]` khi JNDI/ODM trao đổi với LDAP. Nó **không chuyển ảnh thành chuỗi**, không phải Base64 và không mã hóa bảo mật. Chi tiết ở mục 7.

### 3.3. syntax: OID biểu diễn LDAP syntax

```java
@Attribute(
    name = "modifyTimestamp",
    syntax = "1.3.6.1.4.1.1466.115.121.1.24",
    readonly = true
)
private String modifiedAt;
```

OID ở ví dụ là LDAP syntax **Generalized Time**. `syntax` phục vụ lựa chọn và độ chính xác của **chuyển đổi giá trị** trong ODM, tùy converter được đăng ký; nó **không thay đổi schema** của server và **không tự động bảo đảm** một field `Instant` bất kỳ được chuyển đúng nếu thiếu converter. Sử dụng `String` trong ví dụ để minh họa an toàn; khi cần thời gian Java, phải dùng converter và parser phù hợp.

### 3.4. readonly: đọc nhưng không ghi

```java
@Attribute(name = "createTimestamp", readonly = true)
private String createdAt;

@Attribute(name = "modifyTimestamp", readonly = true)
private String modifiedAt;
```

Đây là những ví dụ **operational attributes** thường do server duy trì. Khi được trả về, ứng dụng có thể xem chúng qua entity nhưng ODM không cố ghi lại vào LDAP khi persist entity.

**`readonly = true` chỉ là lựa chọn mapping phía client**, không phải ACL, không ngăn Java code gọi setter và không biến toàn bộ entity thành bất biến. Quyền đọc/ghi thực tế vẫn do LDAP server kiểm soát.

## 4. Ví dụ entity đầy đủ với @Attribute

Một class ODM phù hợp với entry `inetOrgPerson`:

```java
import java.util.LinkedHashSet;
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private Set<String> emails = new LinkedHashSet<>();

    @Attribute(name = "description")
    private String description;

    @Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)
    private byte[] photo;

    @Attribute(name = "modifyTimestamp", readonly = true)
    private String modifiedAt;

    @Transient
    private String uiLabel;

    public PersonEntry() {
        // Constructor không tham số cho ODM.
    }

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getGivenName() { return givenName; }
    public void setGivenName(String givenName) { this.givenName = givenName; }

    public Set<String> getEmails() { return emails; }
    public void setEmails(Set<String> emails) {
        this.emails = emails == null
                ? new LinkedHashSet<>()
                : new LinkedHashSet<>(emails);
    }

    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }

    public byte[] getPhoto() {
        return photo == null ? null : photo.clone();
    }
    public void setPhoto(byte[] photo) {
        this.photo = photo == null ? null : photo.clone();
    }

    public String getModifiedAt() { return modifiedAt; }

    public String getUiLabel() { return uiLabel; }
    public void setUiLabel(String uiLabel) { this.uiLabel = uiLabel; }
}
```

Giải thích cấu trúc:

- **`@Entry`** quy định base của nhóm entry và những `objectClass` cần ánh xạ. Khi tạo mới, danh sách class phải phù hợp schema phía server; ví dụ `person` yêu cầu `cn` và `sn`.
- **`@Id Name dn`** giữ DN; không nên thay bằng `Long id` hoặc chỉ `String uid` vì LDAP định danh entry bằng DN.
- **`@Attribute`** liên hệ field với attribute có tên/schema tương ứng.
- **`Set<String> emails`** minh họa một attribute đa trị. Với LDAP attribute thông thường, thứ tự các giá trị không có ý nghĩa; không nên gán vai trò “email chính” dựa trên phần tử đầu tiên.
- **`photo`** phải giữ nguyên bytes, không gọi `new String(photo)`.
- **`modifiedAt`** là dữ liệu server duy trì; `readonly=true` ngăn ODM cố ghi trả lại.
- **`uiLabel`** là trạng thái hiển thị của ứng dụng, không có LDAP attribute tương ứng; `@Transient` làm ODM bỏ qua field này.

Ví dụ trên thiên về giảng dạy: trong ứng dụng thật, các getter/setter, kiểu collection, xử lý `null` và phương pháp sao chép dữ liệu phải được điều chỉnh theo yêu cầu; không tự động biến mọi field thành API được client ghi tùy ý.

## 5. Tên field Java không phải lúc nào cũng bằng tên LDAP

Một vấn đề điển hình là giữa mã nguồn Java và schema LDAP có cách đặt tên khác nhau:

| Java field | LDAP attribute | Khai báo phù hợp |
| --- | --- | --- |
| `fullName` | `cn` | `@Attribute(name = "cn")` |
| `surname` | `sn` | `@Attribute(name = "sn")` |
| `firstName` | `givenName` | `@Attribute(name = "givenName")` |
| `emails` | `mail` | `@Attribute(name = "mail")` |
| `photo` | `jpegPhoto` | `@Attribute(name = "jpegPhoto", type = BINARY)` |
| `description` | `description` | Có thể không dùng annotation hoặc dùng `@Attribute` |
| `modifiedAt` | `modifyTimestamp` | `@Attribute(name = "modifyTimestamp", readonly = true)` |

**Không đoán tên attribute từ nhãn giao diện.** Ví dụ “display name” trong UI có thể lấy từ `cn` hoặc `displayName`; cả hai là tên attribute LDAP khác nhau. Khi code thay `@Attribute(name = "cn")` thành `name = "displayName"`, tức đã đổi **nguồn dữ liệu LDAP**, không chỉ đổi tên thuộc tính phía Java.

### 5.1. Tên không có trong schema

Nếu khai báo:

```java
@Attribute(name = "favoriteProgrammingLanguage")
private String favoriteLanguage;
```

nhưng directory không có attribute type `favoriteProgrammingLanguage` hoặc `objectClass` của entry không cho phép nó, server có thể từ chối Add/Modify với lỗi schema như `undefinedAttributeType` hoặc `objectClassViolation`. Annotation chỉ mô tả mapping phía client; nó **không đăng ký attribute mới vào schema LDAP**.

Với thuộc tính riêng của tổ chức, cần quy trình quản trị schema, OID, matching rule, syntax, quyền và kiểm thử trước khi đưa mapping vào production.

## 6. Dữ liệu đơn trị, đa trị và trường hợp thiếu attribute

### 6.1. Giá trị đơn

```java
@Attribute(name = "cn")
private String fullName;

@Attribute(name = "sn")
private String surname;
```

Các field này biểu diễn một giá trị chuỗi. Một thuộc tính đơn trị theo schema phải có tối đa một giá trị; **Java String không làm server cho phép** sửa một attribute vốn có nhiều giá trị và ngược lại.

Nếu field được đọc ra `null`, chưa chắc entry không có thuộc tính đó: kết quả cũng có thể bị giới hạn bởi ACL hoặc search controls. Với một field bắt buộc như `sn` trong `person`, hãy kiểm tra dữ liệu/schema và quyền nếu bản ghi tải lên thiếu field.

### 6.2. Giá trị đa trị

LDIF:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
mail: lan@example.org
mail: lan.work@example.org
```

Trong Java:

```java
@Attribute(name = "mail")
private Set<String> emails = new LinkedHashSet<>();
```

Nếu cần thêm một email:

```java
PersonEntry person = /* entity vừa được đọc từ LDAP */;
person.getEmails().add("lan.personal@example.org");
ldapTemplate.update(person);
```

Ví dụ giả định đã có biến `ldapTemplate` kiểu `LdapTemplate` và `person` là entity hợp lệ. Khi cập nhật, ODM sẽ tính các thay đổi cần thiết dựa trên field được ánh xạ.

**Không giả định thứ tự giá trị LDAP.** Nếu nghiệp vụ cần phân biệt “email chính” và “email phụ”, schema hoặc quy tắc ứng dụng phải có cách diễn đạt riêng. Dùng phần tử đầu tiên của `Set` hay `Attribute.get()` làm “chính” là không đáng tin.

### 6.3. null, collection rỗng và xóa attribute

Khi tạo entry mới, attribute tùy chọn chưa có giá trị thường có thể được bỏ qua. Nhưng khi **cập nhật**, đặt một field về `null` hoặc collection rỗng có thể làm LDAP attribute bị xóa tùy quy tắc mapping, converter và đường update đang dùng.

Vì vậy, cần phân biệt ba ý định nghiệp vụ:

1. **Không thay đổi** attribute hiện tại.
2. **Đặt** attribute thành tập giá trị mới.
3. **Xóa** attribute hiện có.

Đặc biệt, endpoint kiểu PATCH không nên lấy request thiếu `mail` rồi gọi `entity.setEmails(null)` và `update` một cách vô điều kiện. Nên tải entity, chỉ sửa các field mà request **thực sự yêu cầu thay đổi**, rồi kiểm tra behavior với directory test. Khi cần kiểm soát chính xác ADD/REMOVE/REPLACE từng giá trị, dùng `LdapTemplate.modifyAttributes(...)` hoặc `DirContextOperations` có thể phù hợp hơn update toàn entity.

### 6.4. Giá trị thuộc tính là DN

Các nhóm LDAP thường có attribute chứa **DN của thành viên**, ví dụ:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: backend
uniqueMember: uid=lan,ou=people,dc=example,dc=org
```

Thay vì xem từng DN như chuỗi bất kỳ:

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfUniqueNames"}
)
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "uniqueMember")
    private Set<Name> memberDns;

    public DirectoryGroup() {}
    // Getter/setter và cách dựng DN được lược bớt.
}
```

Spring LDAP ODM có hỗ trợ giá trị `javax.naming.Name` cho attribute DN, giúp tính khác biệt membership theo **so sánh tên phân biệt** thay vì so chuỗi DN thô. Đây là lợi ích thiết thực khi thành viên có cách escape/biểu diễn tên khác nhau nhưng về cấu trúc chỉ cùng một DN.

**Cẩn thận:** `uniqueMember` có syntax/biểu diễn riêng (có thể gồm unique identifier); ví dụ trên dùng trường hợp giá trị đơn giản là DN. Phải kiểm tra schema và dữ liệu thật trước khi chọn `Set<Name>`.

## 7. Ánh xạ dữ liệu nhị phân với type = BINARY

LDAP attribute như `jpegPhoto` hoặc một số dạng certificate không phải văn bản. Với ODM:

```java
@Attribute(
    name = "jpegPhoto",
    type = Attribute.Type.BINARY
)
private byte[] jpegPhoto;
```

JNDI biểu diễn các thuộc tính binary được nhận biết bằng `byte[]`. Khi truy cập theo cách khác, chẳng hạn tự dùng `AttributesMapper` đọc một attribute tùy chỉnh, bạn cũng cần xác minh **JNDI LDAP provider** đang nhận diện attribute đó là binary. Với provider hỗ trợ, một danh sách thuộc tính binary bổ sung có thể được cấu hình qua environment property:

```text
java.naming.ldap.attributes.binary=customBlob objectGUID
```

Đây là ví dụ cho **thuộc tính tùy chỉnh/đặc thù server**, không phải điều kiện bắt buộc cho mọi `jpegPhoto`. `objectGUID` là đặc thù Active Directory, không có ở mọi directory. `@Attribute(type = BINARY)` là mô tả ODM; đừng giả định annotation này tự thay đổi mọi đường đọc JNDI khác đang dùng `ContextSource` riêng.

### 7.1. Không chuyển bytes sang String tùy tiện

```java
byte[] photo = person.getPhoto();

// SAI: JPEG không phải chuỗi UTF-8.
String broken = new String(photo, java.nio.charset.StandardCharsets.UTF_8);

// ĐÚNG khi API thực sự cần biểu diễn bytes thành văn bản có thể hoàn nguyên:
String base64 = java.util.Base64.getEncoder().encodeToString(photo);
```

Base64 là **encoding**, không phải encryption. Nếu API cần trả ảnh JPEG qua HTTP, thông thường có thể trả bytes với media type phù hợp sau khi xác thực định dạng và quyền xem. Không log nội dung binary hoặc Base64 của dữ liệu cá nhân để chẩn đoán.

### 7.2. Byte[] là đối tượng thay đổi được

Nếu entity lưu `byte[]`, một getter trả trực tiếp mảng nội bộ cho phép caller thay nội dung mà không qua setter. Ví dụ `PersonEntry` ở phần 4 trả **bản sao** `photo.clone()`. Khi kiểm tra kết quả, dùng `Arrays.equals(expected, actual)`; không dùng `byte[].equals(...)`, vì đó là so sánh tham chiếu.

Một entity có `jpegPhoto` lớn cũng có thể làm truy vấn danh sách tốn bộ nhớ. Với API danh bạ chỉ cần `cn` và `mail`, có thể dùng `LdapTemplate.search` với các thuộc tính được chọn, rồi tải ảnh riêng theo DN khi được phép. Bảo đảm hạn mức kích thước dữ liệu và kiểm tra file/ảnh có định dạng hợp lệ.

## 8. syntax và chuyển đổi kiểu Java

LDAP schema định nghĩa **attribute syntax**, chẳng hạn Directory String, DN hoặc Generalized Time. Một syntax có **OID**, và element `syntax` của `@Attribute` cho phép ODM đưa thông tin này vào quyết định chuyển đổi.

Ví dụ:

```java
@Attribute(
    name = "modifyTimestamp",
    syntax = "1.3.6.1.4.1.1466.115.121.1.24",
    readonly = true
)
private String modifiedAt;
```

Một giá trị generalized time có thể xuất hiện như:

```text
20261126101530Z
```

**Không coi đó là định dạng ISO 8601 có thể gọi thẳng `Instant.parse(...)`**; LDAP Generalized Time có quy tắc riêng, bao gồm độ chính xác và cách biểu diễn vùng giờ tùy giá trị. Nếu ứng dụng muốn lưu trong field `Instant`, cần một converter/parser có hỗ trợ đầy đủ những giá trị mà server thực tế trả về.

### 8.1. Converter của ODM

Spring LDAP ODM hỗ trợ chuyển đổi type dựa trên các converter và, ở các phiên bản hiện đại, có thể tích hợp **Spring `ConversionService`**. Theo tài liệu, trong ứng dụng Spring Boot có cấu hình ODM tương thích, một `Converter` được đăng ký làm bean có thể được ODM sử dụng.

Sơ đồ ý tưởng:

```text
LDAP modifyTimestamp (Generalized Time string)
             │
             ▼
ODM đọc @Attribute(name, syntax)
             │
             ▼
Converter<String, Instant>  (nếu có hỗ trợ/cấu hình)
             │
             ▼
Java Instant
```

Với dự án không dùng auto-configuration ODM, có thể cấu hình `ObjectDirectoryMapper` rồi gắn vào `LdapTemplate` qua `setObjectDirectoryMapper(...)` theo phiên bản Spring LDAP. Các interface/cách đăng ký converter đã thay đổi qua các phiên bản, nên cần đối chiếu tài liệu version cụ thể.

**Giới hạn của `syntax`:**

- Không tạo attribute/schema mới trên LDAP server.
- Không thay JNDI provider thành trình giải mã mọi kiểu dữ liệu.
- Không mặc định sửa lỗi khi field Java, syntax và dữ liệu thực tế không khớp.
- Không xác minh giá trị có đúng nghiệp vụ hay thuộc phạm vi quyền truy cập hay không.

Khi có lỗi conversion, trước tiên đọc **attribute name**, JNDI type thực tế (String hay byte[]), giá trị được server công bố trong schema và converter đang được đăng ký. Đừng ép một attribute binary thành `String` chỉ để tránh exception.

## 9. readonly: dữ liệu được đọc nhưng server quản lý

Directory có nhiều **operational attributes** không nên được client cập nhật qua entity:

```java
@Attribute(name = "createTimestamp", readonly = true)
private String createdAt;

@Attribute(name = "modifyTimestamp", readonly = true)
private String modifiedAt;
```

`readonly = true` làm field **không được persist trở lại LDAP bởi ODM**. Nhưng có hai lưu ý:

1. **Operational attributes thường không được trả về bởi các search mặc định**, tùy server và yêu cầu thuộc tính của client. Nếu field `modifiedAt` còn `null` dù entry có `modifyTimestamp`, hãy kiểm tra search controls, attribute selection (ví dụ `+` nếu server hỗ trợ), ACL và hoạt động mapping.
2. **Server vẫn là nguồn sự thật.** Chỉnh giá trị `modifiedAt` trong đối tượng Java không biến nó thành giá trị LDAP được ghi; muốn biết thời điểm cập nhật thực tế phải đọc lại sau thao tác.

Nếu một attribute chỉ là read-only về mặt **nghiệp vụ** (ví dụ user thường không được sửa department) nhưng có thể được admin sửa, `readonly=true` trên một entity dùng chung sẽ chặn cả các lần ghi qua ODM của admin. Khi cần phân quyền theo vai trò, lựa chọn chính là **ACL/policy của server và service layer**, không chỉ dựa vào flag annotation.

### 9.1. Khi nào dùng @Transient thay readonly?

| Field | Annotation | Lý do |
| --- | --- | --- |
| `modifiedAt` lấy từ `modifyTimestamp` của LDAP | `@Attribute(readonly = true)` | **Muốn đọc** từ directory nhưng **không ghi** |
| `displayLabel` được nối từ `cn` + `uid` trong Java | `@Transient` | Không có attribute LDAP tương ứng |
| `sessionToken` do ứng dụng tạm giữ | `@Transient` hoặc không giữ trong entity LDAP | Không persist vào directory |
| `fullName` cần đọc và ghi `cn` | `@Attribute(name = "cn")` | Mapping hai chiều |

Đừng coi `@Transient` giống `readonly`: một cái **bỏ qua mapping**; cái kia **đọc mapping nhưng không persist**.

## 10. @Attribute và các annotation liên quan

Một entity ODM hợp lệ có nhiều loại metadata với nhiệm vụ riêng:

| Annotation | Gắn lên | Vai trò | Thường có bắt buộc không? |
| --- | --- | --- | --- |
| `@Entry` | Class | Chỉ ra `objectClass` và tùy chọn base | **Có** cho entity ODM |
| `@Id` | Field kiểu `Name` | Chỉ ra DN của entry | **Có** cho entity ODM |
| `@Attribute` | Field | Ánh xạ attribute name/type/syntax/read-only | Tùy chọn nếu field trùng tên attribute |
| `@DnAttribute` | Field `String` | Ánh xạ thành phần DN/RDN | Khi cần lấy/tính DN từ field |
| `@Transient` | Field | Không persist field như attribute LDAP | Khi field chỉ thuộc ứng dụng |

### 10.1. @DnAttribute không tự thay thế @Attribute

Ví dụ:

```java
@DnAttribute(value = "uid")
@Attribute(name = "uid")
private String uid;
```

Field `uid` vừa thể hiện thành phần RDN vừa biểu diễn attribute LDAP. Nhưng hai khái niệm **không giống nhau**: một giá trị dùng để đặt tên entry và một attribute lưu trong entry.

Theo tài liệu ODM, một field có `@DnAttribute` vẫn có thể **được ánh xạ như attribute LDAP**, trừ khi bạn kết hợp `@Transient` để tránh persist nó như một attribute. Ví dụ một thành phần OU chỉ dùng để tính vị trí trong DN:

```java
@DnAttribute(value = "ou")
@Transient
private String organizationalUnit;
```

Đây là trường hợp minh họa cho field **DN-only**; khi dùng trên entity thực tế phải kiểm tra cấu trúc DN, `@Entry(base=...)`, vị trí index và khả năng tạo/cập nhật DN của phiên bản ODM. Không thêm `@Transient` cho field `uid` nếu nghiệp vụ/schema vẫn cần có attribute `uid` trên entry.

### 10.2. Sửa attribute khác với đổi DN

Nếu đổi `mail` của Lan:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=people,dc=example,dc=org
```

đó thường là **LDAP Modify attribute**.

Nếu đổi `uid=lan` thành `uid=lan.nguyen` trong DN:

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan.nguyen,ou=people,dc=example,dc=org
```

đó là thay đổi định danh **Modify DN**. Một số đường update ODM có thể thực hiện chuỗi thao tác xóa/tạo entry khi DN do `@DnAttribute` tính ra thay đổi, không mặc nhiên tương đương một Modify DN nguyên tử. Với nghiệp vụ rename/move, nên xác định rõ có cần `LdapTemplate.rename(oldDn, newDn)` và cập nhật các DN tham chiếu như `member`/`manager` hay không.

## 11. Tạo, đọc và cập nhật entity bằng LdapTemplate

Giả sử `LdapContextSource` dùng:

```text
LDAP URL    : ldaps://directory.example.org:636
Context base: dc=example,dc=org
Bind DN     : uid=app-writer,ou=services,dc=example,dc=org
```

OU `ou=people,dc=example,dc=org` đã tồn tại, service account có quyền tạo/sửa ở nhánh đó và schema cho phép `inetOrgPerson`. DN truyền cho API trong các ví dụ dưới đây được dựng **tương đối với context base**.

### 11.1. Tạo entry

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonCrudService {
    private final LdapTemplate ldapTemplate;

    public PersonCrudService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name createLan() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        PersonEntry person = new PersonEntry();
        person.setDn(dn);
        person.setUid("lan");
        person.setFullName("Nguyen Thi Lan");
        person.setSurname("Nguyen");
        person.setGivenName("Thi Lan");
        person.setEmails(Set.of("lan@example.org"));
        person.setDescription("Backend engineer");

        ldapTemplate.create(person);
        return dn;
    }
}
```

`LdapTemplate.create(person)` dùng ODM mapping và `@Entry(objectClasses=...)` để tạo entry. Với `ContextSource` đã có base `dc=example,dc=org`, DN `uid=lan,ou=people` cần trỏ đúng vị trí dự kiến; hãy kiểm tra sự nhất quán giữa `@Entry.base`, `@Id` và base context trong project.

**Lưu ý:** ví dụ cố ý không gán `modifyTimestamp` vì field được đánh dấu read-only và server có trách nhiệm điền giá trị này. Phải thử trên directory test vì server có thể áp đặt schema/naming rule hoặc ràng buộc bổ sung.

### 11.2. Đọc bằng DN

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

PersonEntry loaded =
        ldapTemplate.findByDn(dn, PersonEntry.class);

if (loaded != null) {
    System.out.println(loaded.getFullName());
    System.out.println(loaded.getEmails());
}
```

Đoạn code giả định `ldapTemplate` và `dn` đã có trong scope. Cách đọc này đặc biệt phù hợp khi đã biết DN; không cần search theo `uid` chỉ để tìm một entry đã được định danh chính xác.

### 11.3. Đọc bằng filter an toàn

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<PersonEntry> findByUid(LdapTemplate ldapTemplate, String uid) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is(uid);

    return ldapTemplate.find(query, PersonEntry.class);
}
```

`.is(uid)` tạo equality filter và escape input theo cú pháp filter. **Không** dùng `"(&(objectClass=inetOrgPerson)(uid=" + uid + "))"` với giá trị client gửi, vì các ký tự như `*`, `(` và `)` có ý nghĩa đặc biệt trong filter LDAP.

Nếu `@Entry(base = "ou=people")` đã giới hạn loại entity, cần cân nhắc cẩn thận việc chỉ định `.base("ou=people")` để không chọn nhầm search base theo phiên bản/configuration. Trên directory test, xác minh DN kết quả và filter thực tế khi kết hợp query base với mapping base.

### 11.4. Cập nhật một attribute

```java
PersonEntry person =
        ldapTemplate.findByDn(dn, PersonEntry.class);

person.setDescription("Platform engineer");
ldapTemplate.update(person);
```

Việc gọi `update` dùng mapping để so sánh và persist thay đổi theo cách ODM hỗ trợ. **Không coi đây là transaction tổng quát cho nhiều entry.** Nếu một ứng dụng đồng thời cập nhật cùng entry, có thể gặp lost update; quy trình cần chống ghi đè có thể phải dùng assertion/version/controls theo khả năng server.

### 11.5. Repository Spring Data LDAP

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByUid(String uid);
}
```

Repository dùng entity ODM để cung cấp `findById(Name)`, `save(...)`, `deleteById(Name)` và truy vấn derived theo thuộc tính. **Spring Data LDAP không tạo schema, OU hay chỉ mục trên LDAP server** từ annotation như một cơ chế DDL của SQL. Trước khi sử dụng, cần cấu hình kết nối TLS, base, quyền và kiểm thử ánh xạ field thực tế.

## 12. Khi nào nên dùng @Attribute, khi nào dùng AttributesMapper?

`@Attribute` thuộc **mô hình entity ODM**; còn `AttributesMapper<T>` là callback chuyển tập thuộc tính của một kết quả search thành đối tượng Java theo ý muốn:

| Nhu cầu | Giải pháp | Ví dụ |
| --- | --- | --- |
| Quản lý đầy đủ entity `PersonEntry` | ODM + `@Attribute` | `ldapTemplate.create/update(person)` |
| Repository CRUD theo DN | `LdapRepository<PersonEntry>` | `findById`, `save` |
| Chỉ lấy tên và email cho trang danh bạ | `AttributesMapper<Dto>` | Không cần map mọi field của entity |
| Lấy cả DN và dữ liệu để định danh | `ContextMapper<Dto>` | Dùng `DirContextOperations.getNameInNamespace()` |
| Sửa chính xác một giá trị của attribute đa trị | `modifyAttributes` hoặc `DirContextOperations` | ADD/REMOVE một địa chỉ `mail` |
| Đổi tên/di chuyển DN | `LdapTemplate.rename` | Modify DN có chủ đích |

Không nên kéo `jpegPhoto` hoặc toàn bộ attribute nhạy cảm vào một endpoint danh sách chỉ để hiển thị `cn`. LDAP query có thể yêu cầu returned attributes có giới hạn; cách tối ưu cụ thể cần bảo đảm các mapper/entity vẫn có dữ liệu họ thực sự cần.

## 13. Schema, ACL và bảo mật không thể thay bằng annotation

Một `@Attribute(name = "mail")` đúng cú pháp vẫn có thể không đọc/ghi được vì nhiều nguyên nhân.

### 13.1. objectClass và MUST/MAY

Ví dụ `person` có các attribute **bắt buộc** như `cn` và `sn`. `inetOrgPerson` mở rộng những attribute có thể dùng như `uid`, `givenName` và `mail`. Nếu ứng dụng tạo entity thiếu `sn`, server có thể báo **`objectClassViolation (65)`**, bất kể Java field đó được gắn `@Attribute` đúng.

Tương tự, nếu dùng một attribute không được object class/schema cho phép, server sẽ từ chối. **Annotation không làm schema tự mở rộng**.

### 13.2. Quyền đọc khác quyền ghi

Một service account có quyền đọc `mail` chưa chắc có quyền sửa nó. Có thể ACL chỉ cho phép một nhóm quản trị cập nhật `departmentNumber` hoặc `description`. Lỗi `insufficientAccessRights (50)` cần được xử lý như vi phạm/thiếu quyền, không tự động retry bằng bind credential mạnh hơn hoặc vô hiệu kiểm tra bảo mật.

### 13.3. Không ghi dữ liệu nhạy cảm vào log

Tránh log:

- Mật khẩu/bind credential và thuộc tính xác thực.
- Ảnh `jpegPhoto`, chứng chỉ, Base64 của dữ liệu người dùng.
- Full DN, email, thông tin nhóm hoặc bộ attribute nếu chưa có chính sách cho phép.
- Raw LDAP filter chứa input nhạy cảm.

Thay vào đó, log **loại thao tác**, **tên attribute không nhạy cảm**, mã lỗi, thời gian xử lý và correlation ID phù hợp. Luôn dùng LDAPS hoặc StartTLS với xác minh chứng chỉ và hostname đúng cấu hình.

### 13.4. Không coi readonly là phân quyền

`@Attribute(readonly = true)` bảo vệ đường **persist của ODM** khỏi ghi attribute này, nhưng các đoạn code khác dùng `LdapTemplate.modifyAttributes`, JNDI hay công cụ ngoài vẫn có thể thử sửa. **ACL của server là ranh giới bảo mật**, và service layer phải kiểm tra authorization theo nghiệp vụ.

## 14. Lỗi thường gặp khi dùng @Attribute

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Field `fullName` không có dữ liệu | Quên `name = "cn"`, ODM tìm `fullName` theo tên field | Gắn `@Attribute(name = "cn")` |
| `@Attribute("cn")` không biên dịch | Annotation không có element `value()` | Dùng `@Attribute(name = "cn")` |
| Field không annotation vẫn bị persist | ODM mặc định ánh xạ theo tên field | Dùng `@Transient` cho field chỉ thuộc ứng dụng |
| `ClassCastException` từ `jpegPhoto` | Dùng `String`/mặc định STRING cho binary | Dùng `byte[]` và `type = BINARY`, kiểm tra JNDI |
| Custom binary attribute trả `String` | JNDI provider chưa nhận diện tên binary | Kiểm tra schema và `java.naming.ldap.attributes.binary` |
| Collection chỉ giữ một giá trị `mail` | Field được khai báo `String` hoặc mapper lấy một value | Dùng kiểu đa trị phù hợp, kiểm thử |
| `Set` thay đổi thứ tự làm test thất bại | Test giả định LDAP values có thứ tự | So sánh tập giá trị, không so vị trí |
| `modifyTimestamp` luôn `null` | Operational attribute không được search trả về hoặc thiếu ACL | Kiểm tra returned attributes và server |
| Lỗi khi update operational attribute | Field chưa `readonly=true` | Đánh dấu read-only, đọc lại sau cập nhật |
| Field Java là `Instant` nhưng conversion lỗi | Chưa có converter hoặc hiểu sai LDAP syntax | Khai báo syntax đúng, dùng converter/parse được kiểm chứng |
| `objectClassViolation (65)` | Thiếu MUST attribute hoặc attribute không được phép | Kiểm tra `@Entry`, schema, `cn`/`sn` |
| `undefinedAttributeType (17)` | Tên attribute không tồn tại trong schema | Kiểm tra tên chính xác và schema server |
| `noSuchObject (32)` | DN/base hoặc parent sai | Kiểm tra `ContextSource` base, `@Entry.base` và DN |
| `insufficientAccessRights (50)` | Bind principal thiếu quyền | Kiểm tra ACL và service account |
| Sửa `uid` rồi save làm DN đổi không như mong muốn | Nhầm attribute UID với RDN/DN | Kiểm tra `@Id`/`@DnAttribute` và dùng Modify DN khi cần |
| Cập nhật một field làm mất attribute khác | Mapping field thiếu/null, update kiểu toàn entity hoặc dữ liệu stale | Chỉ sửa field dự định; integration test; cân nhắc Modify chính xác |
| Repository không đọc được entity sau move OU | Mapping `@Entry.base` gắn nhánh cũ | Kiểm tra DN mới và thiết kế search base |

## 15. Quy trình kiểm thử ánh xạ @Attribute

Kiểm thử cần hai cấp: **unit test cho khai báo/mã Java** và **integration test trên directory** thực hoặc nhúng có schema phù hợp. Không chỉ mock repository để suy ra server chấp nhận tất cả attribute.

### 15.1. Unit test kiểm tra metadata annotation

Có thể kiểm tra annotation qua Java Reflection mà không cần LDAP server:

```java
import java.lang.reflect.Field;
import org.springframework.ldap.odm.annotations.Attribute;

Field fullNameField = PersonEntry.class
        .getDeclaredField("fullName");
Attribute fullNameMapping =
        fullNameField.getAnnotation(Attribute.class);

if (fullNameMapping == null
        || !"cn".equals(fullNameMapping.name())
        || fullNameMapping.type() != Attribute.Type.STRING) {
    throw new AssertionError("cn mapping is incorrect");
}

Field photoField = PersonEntry.class
        .getDeclaredField("photo");
Attribute photoMapping = photoField.getAnnotation(Attribute.class);
if (photoMapping.type() != Attribute.Type.BINARY) {
    throw new AssertionError("jpegPhoto must be binary");
}

Field modifiedAtField = PersonEntry.class
        .getDeclaredField("modifiedAt");
if (!modifiedAtField.getAnnotation(Attribute.class).readonly()) {
    throw new AssertionError("modifyTimestamp must be read-only");
}
```

Đây là đoạn code trong ngữ cảnh phương thức kiểm thử có thể khai báo `throws ReflectiveOperationException`. Nó xác nhận **annotation metadata**, không kiểm chứng rằng server có `jpegPhoto` hoặc `modifyTimestamp`.

### 15.2. Integration test tạo và đọc entry

Trong directory test, chuẩn bị:

```text
dc=example,dc=org
└── ou=people
    └── uid=lan
```

Các bước:

1. **Tạo entry** `inetOrgPerson` có `uid`, `cn`, `sn` và hai giá trị `mail`.
2. **Đọc bằng ODM** với `findByDn`; kiểm tra `fullName` lấy từ `cn`, `surname` từ `sn` và `emails` chứa **đúng hai phần tử**.
3. **Đọc field thiếu** `description`; kiểm tra code xử lý `null` theo quy ước ứng dụng.
4. **Cập nhật description** rồi đọc lại để xác minh sửa đúng field và không làm mất `cn`, `sn`, `mail`.
5. **Thêm/bớt một email**, kiểm tra giá trị cuối và rằng các email khác còn nguyên.
6. **Kiểm tra read-only**: server trả `modifyTimestamp` khi được yêu cầu; ODM không cố ghi thuộc tính đó khi update.
7. **Kiểm tra ảnh**: ghi/đọc `jpegPhoto` bằng bytes thử nghiệm, so sánh `Arrays.equals(expected, actual)`, không chuyển qua String.
8. **Thử schema lỗi**: bỏ `sn` của entry mới hoặc khai báo attribute không được phép; xác minh server trả lỗi phù hợp.
9. **Thử ACL**: dùng principal chỉ có quyền đọc rồi thử update; ứng dụng phải xử lý lỗi quyền.
10. **Thử DN**: xác minh `@Id Name dn` phản ánh đúng base và entry; thử rename/move trong nhánh test nếu có yêu cầu nghiệp vụ.

### 15.3. Kiểm thử null và tính đồng thời

Đặc biệt thử:

- Request chỉ đổi `description` nhưng **không gửi mail**: mail có bị mất sau mapping/update không?
- Hai client cùng đọc rồi sửa các field khác nhau: một update có ghi đè dữ liệu mới của client còn lại không?
- Attribute nhiều giá trị: thêm email trùng, bỏ email không tồn tại, trạng thái tập rỗng.
- Schema quy định một thuộc tính là **SINGLE-VALUE**: code dùng `Set<String>` hai phần tử có bị server từ chối đúng không?
- Binary field lớn: có giới hạn kích thước/timeout và không tải hàng loạt ảnh không cần thiết không?
- Operational attribute chỉ hiện khi search request yêu cầu đúng tập attribute hoặc server cho phép.

**Không dựa vào một unit test reflection để kết luận ánh xạ đã hoạt động end-to-end.** Unit test giúp bắt lỗi viết annotation; integration test mới kiểm chứng conversion, DIT, schema và ACL.

## 16. Bài tập áp dụng

### Bài 1. Đổi tên field Java mà giữ nguyên LDAP schema

Bạn muốn đổi field `fullName` thành `displayLabel` nhưng vẫn đọc từ `cn`. Nên sửa gì?

*Gợi ý:* Đổi tên field Java và giữ `@Attribute(name = "cn")`. Không đổi LDAP attribute thành `displayLabel` nếu server chỉ có `cn`.

### Bài 2. Ánh xạ nhiều email

Một entry có hai giá trị `mail`. Tại sao `String email` có thể không đáp ứng nghiệp vụ?

*Gợi ý:* Attribute LDAP có thể đa trị; dùng `Set<String> emails` hoặc một kiểu collection được ODM hỗ trợ. Không dựa vào thứ tự của các value.

### Bài 3. Đọc ảnh JPEG

Bạn thấy `jpegPhoto:: ...` trong LDIF. Field Java nên có kiểu nào, annotation nào?

*Gợi ý:* `byte[]` và `@Attribute(name = "jpegPhoto", type = Attribute.Type.BINARY)`. Ký hiệu `::` thuộc cách biểu diễn Base64 của LDIF; không có nghĩa phải gọi `new String(bytes)`.

### Bài 4. Thuộc tính thời gian server quản lý

Muốn hiển thị `modifyTimestamp` nhưng không ghi trả lại khi save entity. Chọn gì?

*Gợi ý:* `@Attribute(name = "modifyTimestamp", readonly = true)`; kiểm tra ACL và returned attributes để đọc được operational attribute.

### Bài 5. syntax và Java Instant

Bạn thêm `syntax` là OID Generalized Time rồi đổi field thành `Instant`. Điều này tự động đủ chưa?

*Gợi ý:* Chưa chắc. Cần converter/phân tích LDAP Generalized Time tương thích, vì OID không tự tạo converter hoặc sửa schema.

### Bài 6. Field phục vụ UI

Field `uiLabel` chỉ dùng để nối tên hiển thị và ID ở trang web. Vì sao nên gắn `@Transient`?

*Gợi ý:* ODM có thể map các field theo tên mặc định; `@Transient` bảo đảm không cố persist `uiLabel` như một LDAP attribute.

### Bài 7. Dữ liệu group theo DN

Group `groupOfUniqueNames` chứa nhiều giá trị `uniqueMember` là DN. Nên dùng `Set<String>` hay `Set<Name>`?

*Gợi ý:* Khi các giá trị thực sự là DN thông thường, `Set<Name>` tận dụng hỗ trợ so sánh DN của ODM, thay vì dùng chuỗi với nhiều cách escape khác nhau; vẫn cần xác minh schema thật.

### Bài 8. Rename

Đổi giá trị `uid` trong Java có tự động và an toàn di chuyển entry từ `uid=lan,...` sang `uid=lan.nguyen,...` không?

*Gợi ý:* Không được mặc định như vậy. RDN/DN là định danh; xem `@Id`/`@DnAttribute` và ưu tiên thao tác Modify DN tường minh nếu nghiệp vụ yêu cầu rename/move nguyên tử.

## 17. Ghi nhớ

- **`@Attribute`** thuộc package **`org.springframework.ldap.odm.annotations`**, gắn vào **field Java** trong entity `@Entry` để mô tả LDAP attribute.
- Bốn element là **`name`**, **`type`**, **`syntax`** và **`readonly`**. Mặc định tương ứng `""`, `STRING`, `""` và `false`.
- Nếu `name` rỗng hoặc không gắn `@Attribute`, Spring LDAP ODM có thể dùng **tên field Java** làm tên attribute. Muốn **bỏ mapping**, dùng `@Transient`.
- `@Attribute(name = "cn")` ánh xạ tên Java bất kỳ sang `cn`; `@Attribute("cn")` **không phải cú pháp annotation hợp lệ**.
- `String` phù hợp dữ liệu chuỗi, `Set<String>` phù hợp thuộc tính đa trị, `Set<Name>` hữu ích cho DN tham chiếu, `byte[]` và `type = BINARY` dùng cho dữ liệu nhị phân.
- `syntax` hỗ trợ converter theo LDAP syntax, **không tự tạo schema/converter**. `readonly=true` làm field không được ODM persist, **không thay thế ACL**.
- `@Id Name dn` là định danh phân cấp; thuộc tính như `uid` không thể thay DN. Đổi DN là bài toán **Modify DN** riêng.
- Mọi ánh xạ phải được kiểm tra với **schema, objectClass, DN/base, ACL, TLS và dữ liệu thật** trên directory test trước khi dùng trong production.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@Attribute`, `@DnAttribute`, `@Transient`, ví dụ entity và group DN.
- [Spring LDAP Javadoc — Attribute](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.html): chi tiết `name`, `type`, `syntax`, `readonly` và giá trị mặc định.
- [Spring LDAP Javadoc — Attribute.Type](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.Type.html): `STRING` và `BINARY`.
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `create`, `findByDn`, `find`, `update` và các thao tác thuộc tính.
- [Spring Data LDAP Javadoc — LdapRepository](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html): repository CRUD theo `Name` và truy vấn LDAP.
- [Spring Data LDAP — Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/): repository, query methods và ánh xạ LDAP.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute type, syntax và schema.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Add, Modify, Delete, Modify DN và result codes.
- [RFC 4514 — LDAP DN Representation](https://www.rfc-editor.org/rfc/rfc4514): DN và RDN.
- [RFC 4515 — LDAP Search Filter Representation](https://www.rfc-editor.org/rfc/rfc4515): filter và escape giá trị đầu vào.
