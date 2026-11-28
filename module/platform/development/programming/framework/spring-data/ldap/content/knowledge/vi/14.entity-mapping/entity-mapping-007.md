# Ánh xạ thành phần DN bằng @DnAttribute

## 1. Bài toán: thông tin định danh nằm trong DN, không chỉ trong attribute

Trong module **SPRING_DATA_LDAP**, một Java entity được ánh xạ tới LDAP entry thông qua Spring Data LDAP repository hoặc Spring LDAP ODM. Entry không được nhận diện bằng khóa số như một hàng SQL, mà bằng **distinguished name (DN)**, ví dụ:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

DN trong ví dụ nói rằng entry có tên tương đối `uid=linh` và nằm trong nhánh `ou=people,dc=example,dc=org`. Ứng dụng thường cần cả:

- DN đầy đủ hoặc DN tương đối để định danh entry cho `findById`, `lookup`, `update` hoặc `delete`.
- Giá trị một **thành phần** của DN, chẳng hạn `linh` từ `uid=linh`, để hiển thị và xử lý nghiệp vụ.
- Khả năng **tự tính DN từ các field Java** khi tạo entry mới, hoặc xác định đường dẫn mới khi thuộc tính tham gia tên bị đổi.

Annotation **`@DnAttribute`** thuộc Spring LDAP ODM giúp ánh xạ những thành phần DN sang các field `String` của entity. Nó khác với `@Attribute` (ánh xạ giá trị attribute trong entry) và khác với `@Id` (giữ **toàn bộ DN** dưới dạng `javax.naming.Name`).

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt DN, RDN, attribute trong entry và attribute-value assertion trong RDN.
2. Giải thích đúng `@Entry.base`, `@Id`, `@Attribute`, `@DnAttribute`, `@Transient`.
3. Ánh xạ một thành phần DN như `uid` thành field `String`.
4. Hiểu `@DnAttribute(value=..., index=...)`, thứ tự index và điều kiện để ODM tự tính DN.
5. Ánh xạ nhiều thành phần như `uid=linh,ou=engineering,...` mà không lặp base DN.
6. Tránh nhầm “đọc giá trị từ DN” với “đọc attribute từ LDAP server”.
7. Phân tích rủi ro của sửa field nằm trong DN: rename, move entry, schema, ACL, tham chiếu và cập nhật đồng thời.
8. Kiểm chứng mapping bằng `LdapTemplate`, repository, `ldapsearch` và integration test.

## 2. DN, RDN và thành phần tên: kiến thức cần nắm

LDAP tổ chức entry thành một cây:

```text
dc=example,dc=org
└── ou=people
    ├── uid=linh
    ├── uid=an
    └── uid=minh
```

DN của Linh:

```text
uid=linh,ou=people,dc=example,dc=org
^^^^^^^^  ^^^^^^^^^  ^^^^^^^^^^^^^^^^^
RDN entry  OU cha      naming context
```

- **DN** là toàn bộ chuỗi tên phân cấp định danh một entry.
- **RDN** (*relative distinguished name*) là một thành phần tên trong đường dẫn, thường như `uid=linh` hoặc `ou=people`.
- **Attribute-value assertion (AVA)** là cặp loại thuộc tính và giá trị bên trong RDN; `uid=linh` có type `uid` và value `linh`.
- **Base DN** là gốc một vùng thao tác; Spring `ContextSource` có thể gắn base này vào DN tương đối khi giao tiếp với server.

### 2.1. DN đầy đủ và DN tương đối với ContextSource

Ví dụ cấu hình:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Khi đó:

| Ngữ cảnh | DN |
| --- | --- |
| DN đầy đủ trên LDAP server | `uid=linh,ou=people,dc=example,dc=org` |
| DN tương đối truyền vào `LdapTemplate` khi đã cấu hình base | `uid=linh,ou=people` |
| `@Entry(base="ou=people")` | Vùng entry tương đối với base của `ContextSource` |
| RDN gần entry nhất | `uid=linh` |
| Giá trị của RDN `uid` | `linh` |

Nếu dùng đầy đủ `dc=example,dc=org` **cả trong `ContextSource.base` lẫn trong đối số DN**, kết nối có thể tìm nhầm đường dẫn `...dc=example,dc=org,dc=example,dc=org`. `@DnAttribute` không tự sửa lỗi cấu hình base sai.

### 2.2. Giá trị trong DN không nhất thiết đồng nhất với attribute đã đọc

Một entry có thể có RDN `uid=linh` và attribute `uid: linh`. Hai chỗ này cùng gắn với loại attribute `uid` nhưng có hai vai trò:

```text
DN:  uid=linh,ou=people,dc=example,dc=org
      |
      +-- phần của tên, dùng để định danh trong cây

ENTRY ATTRIBUTE:
      uid: linh
      cn: Linh Nguyen
      sn: Nguyen
```

Trong LDAP schema thông thường, attribute-value của RDN phải phù hợp dữ liệu entry và các quy tắc đặt tên. Tuy nhiên, về **cơ chế ánh xạ Java**, `@DnAttribute` đọc giá trị từ tên; `@Attribute` đọc attribute mà server trả, chịu ảnh hưởng bởi projection, schema và quyền đọc.

Do đó, một field đọc từ `@DnAttribute("uid")` có thể được populate từ DN ngay cả khi truy vấn không lấy field `uid` từ `Attributes`. Không vì thế mà kết luận service account đọc được mọi attribute.

## 3. Bộ annotation ODM và vai trò từng annotation

Các annotation nằm trong `org.springframework.ldap.odm.annotations`.

| Annotation | Đặt trên | Mục đích | Kiểu/giới hạn |
| --- | --- | --- | --- |
| `@Entry` | Class | Khai báo `objectClasses` và vùng `base` của entity. | Cần cho entity ODM. |
| `@Id` | Field | Chứa DN của entry. | Phải thuộc `javax.naming.Name` hoặc subtype. |
| `@DnAttribute` | Field | Lấy một giá trị thành phần DN; có thể tham gia tính DN. | Field phải là `String` theo Javadoc. |
| `@Attribute` | Field | Ánh xạ field sang một LDAP attribute. | Có tên attribute, tùy chọn syntax/type. |
| `@Transient` | Field | Không ánh xạ field như **LDAP attribute** thông thường. | Có thể kết hợp `@DnAttribute` cho field chỉ tồn tại ở đường dẫn. |

Ví dụ khái niệm:

```java
@Entry(base = "ou=people",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
class DirectoryPerson {
    @Id
    private Name dn; // DN của toàn entry

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid; // giá trị RDN uid, đồng thời là LDAP attribute uid

    @Attribute(name = "cn")
    private String fullName; // giá trị từ attribute cn trong entry
}
```

**Phân biệt trọng tâm:** `@DnAttribute` không phải bản rút gọn của `@Id` và cũng không thay thế `@Attribute` trong mọi trường hợp.

### 3.1. @DnAttribute nhận String, @Id nhận Name

Đúng:

```java
@Id
private Name dn;

@DnAttribute(value = "uid", index = 0)
private String uid;
```

Không đúng:

```java
// SAI: @DnAttribute không hỗ trợ field Name.
@DnAttribute(value = "uid", index = 0)
private Name uidPart;

// SAI: @Id của ODM không dùng String làm kiểu DN.
@Id
private String dn;
```

Với `@DnAttribute`, giá trị field là nội dung của AVA (ví dụ `linh`), **không** phải chuỗi `"uid=linh"` và cũng không phải full DN.

### 3.2. @DnAttribute còn ánh xạ LDAP attribute theo mặc định

Tài liệu Spring LDAP nêu rõ: các field entity được ánh xạ thành LDAP attribute theo tên field **theo mặc định**. Gắn `@DnAttribute` **không tự tắt** ánh xạ thông thường này.

```java
// Vừa đọc thành phần uid từ DN, vừa map attribute uid trong entry.
@DnAttribute(value = "uid", index = 0)
@Attribute(name = "uid")
private String uid;

// Lấy division từ thành phần ou của DN,
// nhưng KHÔNG coi nó là một attribute "division" của entry.
@DnAttribute(value = "ou", index = 0)
@Transient
private String division;
```

Nếu field tên `division` không có `@Transient`, ODM có thể cố ánh xạ attribute `division` của entry dù bạn chỉ muốn dùng RDN `ou=...`. Điều đó có thể tạo dữ liệu thừa hoặc vi phạm schema khi ghi. Ngược lại, với `uid`, nếu entry cần lưu attribute `uid`, không nên đặt `@Transient` mà không xem xét schema và mục đích.

## 4. Ánh xạ một thành phần DN

Giả sử mỗi người dùng nằm trực tiếp dưới `ou=people`:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

Entity Java 17 có thể định nghĩa như sau:

```java
package com.example.directory;

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
public class DirectoryPerson {

    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}

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

### 4.1. Vì sao index=0?

`@Entry.base` đã cố định vị trí `ou=people`. Cần thêm **một** RDN ngoài base để có DN người dùng:

```text
@Entry.base:    ou=people
@DnAttribute:  uid = linh, index = 0

DN tương đối được tính:
    uid=linh,ou=people

DN đầy đủ với ContextSource.base=dc=example,dc=org:
    uid=linh,ou=people,dc=example,dc=org
```

Index dùng cho **cách ODM ghép các thành phần DN tương đối với `@Entry.base`**. Một field có `index=0` nghĩa là thành phần đầu tiên gắn gần `@Entry.base` nhất trong chuỗi được ghép; khi chỉ có một RDN thì đây là vị trí duy nhất cần thiết.

### 4.2. Đọc entity bằng LdapTemplate

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name personDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

DirectoryPerson person =
    ldapTemplate.findByDn(personDn, DirectoryPerson.class);

System.out.println(person.getUid()); // linh
System.out.println(person.getCommonName()); // Linh Nguyen
```

`findByDn` là API ODM của Spring LDAP: nó đọc entry ở DN được chỉ định, map vào class có `@Entry`/`@Id` và populate `uid` từ RDN theo `@DnAttribute`. Nếu DN không có entry hoặc `objectClass` không phù hợp, kết quả/lỗi phải được xử lý theo contract Spring LDAP phiên bản đang chạy.

**Đừng dùng mapper này để cấp quyền:** repository/ODM chỉ ánh xạ dữ liệu, còn tài khoản bind LDAP và ACL của server mới quyết định entry/attribute nào được phép đọc.

## 5. value và index của @DnAttribute

Javadoc `@DnAttribute` có hai phần tử:

```java
String value();          // bắt buộc: tên loại attribute trong DN
int index() default -1;  // tùy chọn: vị trí 0-based trong DN do ODM tính
```

### 5.1. value = tên của thành phần DN

Ví dụ:

```java
@DnAttribute("uid")
private String uid;
```

Với DN `uid=linh,ou=people,dc=example,dc=org`, ODM có thể lấy `linh` cho field `uid` bằng cách tìm RDN mang loại `uid`.

Nếu không khai báo `index`, giá trị mặc định là `-1`. Cách dùng **chỉ value** có ích khi mục đích chính là **đọc một thành phần của DN có sẵn**.

### 5.2. index = vị trí để tự xác định DN

Ví dụ:

```java
@DnAttribute(value = "uid", index = 0)
private String uid;
```

Chỉ số `index` dùng cho **tính toán tự động DN** trong luồng create/update/delete. Theo Javadoc, **tất cả các field có `@DnAttribute` trong cùng entity phải có index được chỉ định** nếu muốn framework tự tính DN từ các thành phần.

Điều này khác với chỉ dùng `@DnAttribute("uid")` để đọc giá trị từ DN. Mặc dù Spring LDAP có thể đọc `uid` với index mặc định `-1`, bạn **không nên dựa vào nó để tạo một entry mới có DN tự suy ra**.

### 5.3. Cẩn thận với ví dụ thiếu value

Trong API hiện hành, `value` là **required element**, còn `index` là optional. Vì vậy:

```java
// ĐÚNG: chỉ định value và index.
@DnAttribute(value = "uid", index = 1)
private String uid;

// KHÔNG biên dịch với Javadoc annotation hiện hành:
// @DnAttribute(index = 1)
// private String uid;
```

Một số ví dụ tài liệu diễn giải index viết tắt `@DnAttribute(index=1)` để minh họa. Khi lập trình thực tế, hãy khai báo **`value` tường minh** theo signature của `@DnAttribute` trong dependency đang dùng.

### 5.4. Khi có index, lấy component theo vị trí

Tài liệu Spring LDAP lưu ý rằng khi khai báo `index`, **việc chọn component để ánh xạ dựa trên index**, không chỉ tìm theo tên trong `value`. Điều này đặc biệt quan trọng nếu DN có nhiều RDN, hoặc một loại RDN lặp lại.

Đừng đặt `value="uid"` nhưng lại trỏ index tới RDN `ou=engineering` rồi kỳ vọng mapper “tự chọn uid cho đúng”. Nên giữ nhất quán **value, field Java, vị trí RDN và tên RDN thực tế** để code dễ đọc, đồng thời viết integration test xác nhận DN được tạo.

## 6. Ánh xạ nhiều thành phần DN

Giả sử nhân viên được chia theo phòng ban:

```text
dc=example,dc=org
└── ou=employees
    ├── ou=engineering
    │   ├── uid=linh
    │   └── uid=an
    └── ou=finance
        └── uid=minh
```

DN đầy đủ của Linh là:

```text
uid=linh,ou=engineering,ou=employees,dc=example,dc=org
^^^^^^^^  ^^^^^^^^^^^^^^  ^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^
index=1      index=0       @Entry.base    ContextSource.base
```

Từ `@Entry.base=ou=employees`, phần RDN ở gần base là `ou=engineering` → `index=0`; RDN phía ngoài cùng là `uid=linh` → `index=1`.

### 6.1. Entity có hai @DnAttribute

```java
package com.example.directory;

import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    base = "ou=employees",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryEmployee {
    @Id
    private Name dn;

    @DnAttribute(value = "ou", index = 0)
    @Transient
    private String division;

    @DnAttribute(value = "uid", index = 1)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public DirectoryEmployee() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getDivision() { return division; }
    public void setDivision(String division) {
        this.division = division;
    }
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
}
```

Tại sao dùng `@Transient` cho `division`?

`division` dùng để lấy giá trị của RDN `ou=engineering`, **không phải** field `division` của entry `inetOrgPerson`. Nếu không `@Transient`, mặc định ODM có thể cố map một LDAP attribute mang tên `division`, trong khi schema của entry chưa chắc cho phép. `@Transient` ở đây ngăn mapping như một attribute thông thường; phần `@DnAttribute` vẫn mô tả cách lấy giá trị từ DN.

### 6.2. Mô phỏng cách ghép DN

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=employees")
    .add("ou", "engineering")
    .add("uid", "linh")
    .build();

System.out.println(relativeDn);
// uid=linh,ou=engineering,ou=employees
```

Đây là cách **tự dựng DN bằng builder** để đối chiếu thứ tự RDN trong entity; nó không phải API bắt buộc phải gọi trong trường hợp ODM đã tự tính đúng DN. Kết quả thực tế khi tạo entry còn tùy `@Entry.base`, `ContextSource.base` và field có đủ chỉ số hay không.

### 6.3. Không nhầm index với vị trí trái sang phải của chuỗi

| Thành phần | Index ODM trong phần DN được tính | Vị trí khi hiển thị DN |
| --- | --- | --- |
| `ou=engineering` | `0` | Ở giữa, ngay bên trái `@Entry.base`. |
| `uid=linh` | `1` | Bên trái `ou=engineering`, gần entry nhất. |
| `ou=employees` | Không thuộc các `@DnAttribute` | Thuộc `@Entry.base`. |
| `dc=example,dc=org` | Không thuộc các `@DnAttribute` | Thuộc `ContextSource.base`. |

Ví dụ này theo cơ chế Spring LDAP được mô tả trong tài liệu ODM, trong đó `index=0` là thành phần đầu tiên được bổ sung sát `@Entry.base`, và các index lớn hơn mở rộng DN về phía entry.

## 7. So sánh @DnAttribute index với getRdn(index) của JNDI

Java `javax.naming.ldap.LdapName` và `Rdn` có API truy cập thành phần DN:

```java
import javax.naming.ldap.LdapName;

LdapName full = new LdapName(
    "uid=linh,ou=engineering,ou=employees,dc=example,dc=org"
);

System.out.println(full.getRdn(0)); // dc=org
System.out.println(full.getRdn(1)); // dc=example
System.out.println(full.getRdn(2)); // ou=employees
System.out.println(full.getRdn(3)); // ou=engineering
System.out.println(full.getRdn(4)); // uid=linh
```

**Chú ý:** `LdapName.getRdn(int)` đánh số RDN trên **toàn bộ DN**, từ **phải sang trái**. Nhưng `@DnAttribute.index` dùng cho **các thành phần DN mà ODM tính tương đối với `@Entry.base`**.

| Phần DN | `LdapName.getRdn(i)` trên full DN | `@DnAttribute.index` của ví dụ |
| --- | --- | --- |
| `dc=org` | 0 | Không tham gia. |
| `dc=example` | 1 | Không tham gia. |
| `ou=employees` | 2 | Trong `@Entry.base`. |
| `ou=engineering` | 3 | 0. |
| `uid=linh` | 4 | 1. |

Vì vậy, **không lấy trực tiếp `getRdn(3)` rồi điền `@DnAttribute(index=3)`**. Index phải gắn với cách entity của bạn tổ chức phần DN **ngoài** base.

## 8. @DnAttribute và @Attribute khi cùng nói về uid

Ví dụ:

```java
@DnAttribute(value = "uid", index = 0)
@Attribute(name = "uid")
private String uid;
```

Field `uid` có hai vai trò:

1. Lấy `linh` từ RDN `uid=linh` của DN.
2. Là thuộc tính `uid` mà entity cần map/ghi theo schema của directory.

Điều này **không** có nghĩa LDAP server sẽ tự động “sao chép” mọi thay đổi từ RDN sang attribute theo cách ứng dụng mong đợi. Khi đổi `uid`, phải xem xét **Modify DN**, schema, quy tắc delete-old-RDN và mapping của framework. Không tự đặt giả định rằng thay field sẽ tạo một RenameRequest thành công ở mọi server.

### 8.1. Dùng @Transient khi field chỉ mô tả vị trí trong cây

```java
@DnAttribute(value = "ou", index = 0)
@Transient
private String division;
```

`division` không nhất thiết là attribute có trong entry. Giá trị này đến từ **đường dẫn entry**. Tài liệu Spring LDAP minh họa việc dùng `@DnAttribute` cùng `@Transient` cho các thành phần như tên công ty/OU nằm trên cây DN.

### 8.2. Mất quyền đọc attribute không đồng nghĩa mất DN

Giả sử account có quyền tìm một entry nhưng không được đọc `mail`. ODM có thể vẫn xác định DN và lấy `uid` từ DN, trong khi `mail` bị thiếu hoặc null. Vì vậy:

- Không suy đoán toàn bộ dữ liệu có đủ chỉ từ việc `@DnAttribute` trả giá trị.
- Không coi `@Attribute` null là bằng chứng attribute không tồn tại; ACL và projection có thể che giá trị.
- Không đưa tên DN/OU nhạy cảm ra HTTP response hoặc log nếu người dùng không có quyền biết.

## 9. Tự tính DN khi tạo mới entry

Điểm mạnh của `@DnAttribute(index=...)` là cho phép ODM tự dựng DN khi tạo entry từ object Java. Theo Spring LDAP, khi **mọi `@DnAttribute` có index**, các giá trị đó kết hợp với `@Entry.base` để xác định DN cho create/update/delete.

### 9.1. Ví dụ tạo DirectoryPerson với một thành phần

```java
DirectoryPerson person = new DirectoryPerson();
person.setUid("minh");
person.setCommonName("Minh Tran");
person.setSurname("Tran");
person.setEmail("minh@example.org");

ldapTemplate.create(person);
```

Với `@Entry(base="ou=people")` và `@DnAttribute(value="uid",index=0)`, DN dự kiến của entry mới (tương đối với `ContextSource.base`) là:

```text
uid=minh,ou=people
```

DN đầy đủ:

```text
uid=minh,ou=people,dc=example,dc=org
```

Để ví dụ hoạt động, directory **phải có** `ou=people` và tài khoản bind phải có quyền tạo entry với đúng object classes, schema `person`/`inetOrgPerson`, các attribute bắt buộc. `@DnAttribute` chỉ giúp **xác định tên**, nó không tự tạo parent OU, không bỏ qua schema và không cấp quyền ghi.

### 9.2. Tạo entity có hai thành phần

```java
DirectoryEmployee employee = new DirectoryEmployee();
employee.setDivision("engineering");
employee.setUid("linh");
employee.setCommonName("Linh Nguyen");
employee.setSurname("Nguyen");

ldapTemplate.create(employee);
```

DN dự kiến:

```text
uid=linh,ou=engineering,ou=employees,dc=example,dc=org
```

Nếu `ou=engineering,ou=employees,dc=example,dc=org` chưa tồn tại, LDAP server thường trả lỗi `noSuchObject`. Nếu entry `uid=linh` đã tồn tại tại chính DN này, tạo mới thường thất bại với `entryAlreadyExists`.

**Lưu ý:** code chỉ dành cho directory test. Trong hệ thống thật, cần kiểm tra uniqueness của UID theo vùng nghiệp vụ, quyền provision, input validation và chống request tạo entry trùng.

### 9.3. Trường hợp chưa đủ index

```java
@DnAttribute("uid")
private String uid;

@DnAttribute(value = "ou", index = 0)
@Transient
private String division;
```

Cấu hình trên có một field `@DnAttribute` **không khai báo index**, vì vậy **không đáp ứng điều kiện all-indexed** được Javadoc đề cập cho tự tính DN. Có thể vẫn dùng để đọc các thành phần từ DN có sẵn, nhưng không nên dựa vào auto-compute cho create/update/delete.

## 10. Truy vấn bằng Spring Data LDAP Repository

Repository hỗ trợ thao tác CRUD với ODM entity:

```java
package com.example.directory;

import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
```

Các method `findById`, `save` và `delete` sử dụng DN theo contract của Spring Data LDAP và ODM. Kiểu ID của `LdapRepository<T>` mặc định là `javax.naming.Name`, không phải `Long`.

### 10.1. Truy vấn theo UID không giống đọc theo DN

```java
Optional<DirectoryPerson> found =
    repository.findByUid("linh");
```

`findByUid` thể hiện truy vấn theo **LDAP attribute `uid`**, phụ thuộc vào filter và search base. Nó không đồng nghĩa trực tiếp với việc đọc entry duy nhất tại `uid=linh,ou=people`.

Nếu UID xuất hiện ở các OU khác nhau, tìm toàn subtree có thể có nhiều kết quả. Với entity có nhiều thành phần DN như `DirectoryEmployee`, cần xác định thêm division/OU hoặc chọn search base hẹp:

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

DirectoryEmployee person = ldapTemplate.findOne(
    query()
        .base("ou=engineering,ou=employees")
        .where("uid").is("linh"),
    DirectoryEmployee.class
);
```

`LdapQueryBuilder` escape giá trị filter theo LDAP; không ghép raw input thành `"(uid=" + uid + ")"`. Nếu cần đọc theo DN đã biết, dùng `findByDn`/`findById` và dựng DN bằng `LdapNameBuilder`.

### 10.2. Ví dụ tìm trực tiếp bằng Name

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder.newInstance("ou=employees")
    .add("ou", "engineering")
    .add("uid", "linh")
    .build();

DirectoryEmployee employee =
    ldapTemplate.findByDn(dn, DirectoryEmployee.class);
```

Ở đây `dn` **không** chứa `dc=example,dc=org` vì `ContextSource` đã có base. Việc khớp `@Entry.base`, `ContextSource.base` và thực tế directory phải được kiểm chứng khi tích hợp.

## 11. Đổi @DnAttribute có thể là rename/move, không chỉ sửa field

Giả sử entity ban đầu:

```text
uid=linh,ou=engineering,ou=employees,dc=example,dc=org
```

Nếu trong object Java:

```java
employee.setUid("linh2");
```

DN mong muốn đổi thành:

```text
uid=linh2,ou=engineering,ou=employees,dc=example,dc=org
```

Nếu đổi:

```java
employee.setDivision("finance");
```

DN mong muốn:

```text
uid=linh,ou=finance,ou=employees,dc=example,dc=org
```

Đây không chỉ là một `ModifyRequest` thay `uid` hay `ou` của entry. Di chuyển hoặc đổi tên entry dùng **Modify DN**/rename semantics và có thể chịu ràng buộc từ parent OU, ACL, schema và server topology.

Tài liệu Spring LDAP ghi rằng khi các thành phần `@DnAttribute` có index, ODM có thể tính DN khi update và **xử lý chuyển entry** nếu giá trị thuộc phần DN thay đổi. Trong mã dự án, phải xác minh behavior của phiên bản Spring LDAP/Spring Data LDAP và server thực tế; không suy từ câu này rằng mọi `repository.save(...)` sẽ luôn xử lý trọn vẹn một workflow di chuyển phức tạp.

### 11.1. Điều gì có thể sai khi di chuyển?

| Rủi ro | Vì sao có thể xảy ra | Biện pháp |
| --- | --- | --- |
| OU đích không tồn tại | Parent DN mới thiếu. | Provision OU theo quy trình trước khi move. |
| Entry đích đã tồn tại | Trùng DN/RDN. | Kiểm tra uniqueness và xử lý conflict. |
| Bind principal không có quyền Modify DN | Read/Modify attribute không bao gồm mọi quyền rename/move. | ACL theo OU/entry, không tự dùng admin. |
| `@Id dn` và các field DN không đồng nhất | Cập nhật field không theo quy trình identity. | Định nghĩa rõ nguồn DN và refresh entity sau thao tác. |
| Group `member` vẫn trỏ DN cũ | LDAP server/product không bảo đảm cập nhật tham chiếu mọi nơi. | Có kế hoạch cập nhật/đối soát reference. |
| Client khác vẫn dùng DN cũ | Rename làm mất đường dẫn cũ. | Thiết kế chuyển đổi và thông báo cho downstream. |
| Đổi RDN không phù hợp schema | Naming attribute thiếu/không hợp lệ. | Kiểm tra `objectClass`, RDN/AVA và rule naming. |
| Move qua naming context/server | Có thể cần quy trình khác, không phải mọi server hỗ trợ. | Kiểm tra topology/referrals và khả năng server. |

### 11.2. Khi cần điều khiển rename rõ ràng

Spring LDAP cung cấp `LdapTemplate.rename(...)` với DN cũ/mới:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

Name newDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh2")
    .build();

ldapTemplate.rename(oldDn, newDn);
```

Đây chỉ là ví dụ **đổi RDN trên directory test**, không phải khuyến nghị đổi UID người dùng production. Phải kiểm tra cách server xử lý giá trị RDN cũ, tham chiếu nhóm và chính sách ACL. Nếu business logic còn cần chỉnh các attribute khác, chúng có thể là **operation riêng**, không có transaction ACID xuyên nhiều request theo mặc định.

### 11.3. Tránh thay đổi danh tính chỉ để sửa nội dung

Nếu người dùng chỉ đổi tên hiển thị, hãy sửa `cn`/`displayName` (tùy schema), **không** mặc định đổi `uid`/DN. Dùng định danh tương đối ổn định cho RDN khi có thể; tác động của rename thường lớn hơn tác động của cập nhật một attribute.

## 12. DN escaping và LDAP filter escaping khác nhau

Tên người dùng hoặc OU có thể chứa dấu phẩy, dấu cộng, dấu bằng, dấu gạch chéo ngược và những ký tự phải escape khi biểu diễn DN.

### 12.1. Dùng LdapNameBuilder thay vì nối chuỗi

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "linh,dev";

Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", uid)
    .build();

System.out.println(dn);
// uid=linh\,dev,ou=people
```

Nếu tự nối:

```java
// SAI: input chứa dấu phẩy có thể bị hiểu là thêm RDN.
String unsafeDn = "uid=" + uid + ",ou=people";
```

Không nên tự escape nhiều lần khi kết hợp `LdapNameBuilder`, `LdapName` và Spring LDAP API; sử dụng đối tượng `Name` xuyên suốt để tránh **double escaping**. Chuỗi hiển thị của `Name` có thể được chuẩn hóa khác với input, nhưng phải biểu diễn **cùng DN**.

### 12.2. Filter builder giải quyết bài toán khác

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

var ldapQuery = query()
    .base("ou=people")
    .where("uid").is(userInput);
```

`LdapQueryBuilder` escape **giá trị LDAP filter** theo RFC 4515; `LdapNameBuilder` escape **DN/RDN** theo RFC 4514. Hai cú pháp không thể thay thế nhau. Không dùng kết quả escape filter để ghép một RDN.

### 12.3. Không tin DN hoặc OU do HTTP client cung cấp

Tránh API cho phép:

```text
POST /directory/entries
{"dn":"uid=someone,ou=admins,dc=example,dc=org", ...}
```

Nếu nghiệp vụ chỉ tạo người dùng ở `ou=people`, service phải xây DN từ **base/OU được phê duyệt**, validate UID và ACL. Không cho HTTP user quyết định tùy ý thư mục, RDN hoặc field `objectClass`. `@DnAttribute` là công cụ mapping, **không phải** cơ chế phân quyền.

## 13. @DnAttribute và schema LDAP

LDAP schema quy định entry được phép có các attribute nào, đâu là `MUST`/`MAY` và loại thuộc tính nào là `SINGLE-VALUE`.

Ví dụ `inetOrgPerson` được kế thừa từ `organizationalPerson` và `person`. Entry thông thường có các `objectClass` cần thiết và phải thỏa thuộc tính bắt buộc của `person` như `cn` và `sn`.

| Ngữ cảnh | Quy tắc cần nhớ |
| --- | --- |
| `@DnAttribute("uid")` | Chỉ mô tả cách map DN; không định nghĩa schema của `uid`. |
| `@Attribute(name="uid")` | Ánh xạ attribute `uid` của entry; server vẫn kiểm tra syntax/schema. |
| `@Entry(objectClasses=...)` | Khai báo class mà ODM dùng cho entity; phải phù hợp entry trên server. |
| `@Transient` trên division | Không ghi một attribute nghiệp vụ `division` chỉ vì nó có trong đường dẫn DN. |
| Đổi `uid`/`cn` tham gia RDN | Có thể cần Modify DN; phải tôn trọng naming schema và xử lý giá trị RDN trên server. |
| Đổi `ou` trong đường dẫn | Có thể là move sang parent OU khác; không tự tạo parent. |

### 13.1. Một RDN nhiều AVA không giống nhiều RDN

Ví dụ:

```text
cn=Linh Nguyen+uid=linh,ou=people,dc=example,dc=org
^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^  ^^^^^^^^^^^^^^^^^
     MỘT RDN             RDN cha     naming context
     gồm hai AVA
```

`cn=Linh Nguyen+uid=linh` có **hai AVA trong cùng một RDN**, khác với:

```text
uid=linh,ou=engineering,ou=employees,dc=example,dc=org
^^^^^^^^  ^^^^^^^^^^^^^^  ^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^
  RDN 1       RDN 2         RDN 3         phần gốc
```

`@DnAttribute.index` diễn đạt **vị trí RDN trong đường dẫn DN được tính**, không phải vị trí của từng AVA bên trong một multi-valued RDN. Với DN có multi-valued RDN hoặc naming rule đặc thù, cần đánh giá giới hạn ODM, sử dụng `javax.naming.ldap.LdapName`/`Rdn` và viết mapper chuyên biệt nếu không thể biểu diễn chính xác.

## 14. Kiểm tra trực tiếp bằng ldapsearch

Trước khi nghi ngờ ODM sai, hãy xem **DN thực** và attribute của entry trong directory thử nghiệm.

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" \
  dn objectClass uid cn sn mail
```

Lệnh này dùng **full DN** trong `ldapsearch -b` vì công cụ kết nối trực tiếp tới server. Khác với `LdapTemplate` đã được cấu hình `ContextSource.base`.

Với cấu trúc nhiều OU:

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=engineering,ou=employees,dc=example,dc=org" \
  -s base "(objectClass=*)" \
  dn uid cn sn
```

Đối chiếu:

1. DN trả về có đúng `uid=...` và các OU như thiết kế không?
2. `@Entry.base` có khớp phần đuôi tương ứng không?
3. `@DnAttribute.index` có được đánh số theo phần RDN **ngoài base** không?
4. `@Id` có kiểu `Name` và bean ODM được khởi tạo hợp lệ không?
5. `objectClass` trên server có khớp `@Entry.objectClasses` không?
6. Tài khoản bind có quyền search/read đúng entry và attribute không?

Không dùng admin bind ở production để “chữa” lỗi mapping. Nếu quyền đọc bị hạn chế, thực hiện đối chiếu bằng tài khoản kiểm thử có thẩm quyền trên directory test.

## 15. Integration test xác minh @DnAttribute

Kiểm thử unit có thể kiểm tra cách builder dựng DN, nhưng **không chứng minh** ODM thật đã ánh xạ theo schema, quyền và base DN của LDAP server. Nên bổ sung integration test trên directory test có fixture cụ thể.

### 15.1. Dữ liệu fixture

Directory test:

```text
dc=example,dc=org
├── ou=people
│   └── uid=linh
└── ou=employees
    ├── ou=engineering
    │   └── uid=an
    └── ou=finance
```

Một fixture cho `DirectoryEmployee`:

```ldif
dn: uid=an,ou=engineering,ou=employees,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
```

Đừng dùng directory production hoặc dữ liệu người thật để thử create/rename. Chỉ dùng test tree và service account quyền tối thiểu.

### 15.2. Test đọc giá trị từ DN

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class DnAttributeMappingIT {

    @Autowired
    private LdapTemplate ldap;

    @Test
    void mapsUidAndDivisionFromDistinguishedName() {
        Name dn = LdapNameBuilder.newInstance("ou=employees")
            .add("ou", "engineering")
            .add("uid", "an")
            .build();

        DirectoryEmployee employee =
            ldap.findByDn(dn, DirectoryEmployee.class);

        assertThat(employee).isNotNull();
        assertThat(employee.getDn()).isNotNull();
        assertThat(employee.getUid()).isEqualTo("an");
        assertThat(employee.getDivision()).isEqualTo("engineering");
        assertThat(employee.getCommonName()).isEqualTo("An Tran");
        assertThat(employee.getSurname()).isEqualTo("Tran");
    }
}
```

Đoạn test giả định test profile cấu hình `ContextSource.base=dc=example,dc=org` và directory có sẵn entry. Cần thực thi trên LDAP server phù hợp trước khi dùng làm điều kiện nghiệm thu; code bài học **chưa được build/chạy** trong giai đoạn biên soạn.

### 15.3. Test tự tính DN khi tạo mới

Để kiểm tra create, tạo UID ngẫu nhiên dưới một OU test cố định, gọi `ldapTemplate.create(entity)` rồi tìm lại bằng DN kỳ vọng:

```java
import java.util.UUID;
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String uid = "lab" + UUID.randomUUID()
    .toString().replace("-", "").substring(0, 10);

DirectoryPerson person = new DirectoryPerson();
person.setUid(uid);
person.setCommonName("Test " + uid);
person.setSurname("Test");

Name expectedDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", uid)
    .build();

boolean created = false;
try {
    ldapTemplate.create(person);
    created = true;
    DirectoryPerson loaded =
        ldapTemplate.findByDn(expectedDn, DirectoryPerson.class);
    // assert loaded != null, loaded.getUid().equals(uid)
} finally {
    if (created) {
        ldapTemplate.unbind(expectedDn);
    }
}
```

Đây là **đoạn minh họa nằm trong method test**, không phải một class Java độc lập. Test cần account có quyền tạo/xóa entry ở `ou=people`, schema hợp lệ và parent OU tồn tại. Khi cleanup gặp lỗi mạng, fixture có thể còn sót lại; môi trường CI cần cơ chế dọn dữ liệu test riêng.

### 15.4. Ma trận test quan trọng

| Bài kiểm tra | Kỳ vọng |
| --- | --- |
| `@DnAttribute("uid")` với DN một thành phần | Lấy đúng value `linh` từ RDN. |
| `@Id Name` | Chứa danh tính DN của entry đã đọc. |
| `@Attribute(name="cn")` | Đọc giá trị LDAP attribute `cn` nếu có quyền. |
| `@DnAttribute(value="ou",index=0) @Transient` | Lấy division từ DN mà không map LDAP attribute `division`. |
| `uid index=1`, `ou index=0` | Ánh xạ đúng `uid=an,ou=engineering,...`. |
| Tạo mới với toàn bộ field indexed | DN tính từ field + `@Entry.base`. |
| Thiếu một `index` | Không dựa vào auto-compute; đánh giá lỗi/contract framework. |
| Sai thứ tự index | Test phải phát hiện DN sai hoặc thất bại khi map. |
| UID chứa dấu phẩy | Builder/ODM xử lý RDN escaping theo contract. |
| Parent OU không tồn tại | Server từ chối tạo entry; không âm thầm sinh parent. |
| Đổi UID/OU | Cần kiểm chứng rename/move và các tham chiếu downstream. |
| Bind account chỉ đọc | Không được create/delete/rename dù mapping đúng. |
| DN ngoài `ContextSource.base` | Không coi là entry hợp lệ trong phạm vi service. |
| Schema thiếu attribute bắt buộc | Tạo/sửa bị server từ chối. |

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Entity trả `uid=null` | Thiếu `@DnAttribute` hoặc DN/RDN không khớp. | Đối chiếu tên RDN, kiểu String và mapping. |
| `@DnAttribute(index=0)` không biên dịch | Thiếu `value` bắt buộc theo annotation. | Dùng `@DnAttribute(value="uid",index=0)`. |
| DN tự tính bị sai vị trí | Đảo `index=0`/`index=1` hoặc hiểu nhầm base. | Vẽ cây và tính thứ tự từ `@Entry.base`. |
| DN bị lặp `dc=example,dc=org` | Đưa full DN vào API đã có `ContextSource.base`. | Dùng DN tương đối đúng contract. |
| Tạo entry bị `noSuchObject` | Parent OU không tồn tại hoặc DN sai. | Kiểm tra cây và OU thực tế. |
| Tạo entry bị `entryAlreadyExists` | DN đích trùng. | Kiểm tra naming/uniqueness, không ghi đè tùy ý. |
| Cập nhật field `division` tạo attribute không mong muốn | Thiếu `@Transient` cho field chỉ dùng làm DN component. | Kết hợp `@DnAttribute` với `@Transient` đúng mục đích. |
| `findByUid` trả nhiều entry | UID không duy nhất trên toàn subtree. | Search base hẹp hoặc tìm theo DN gồm division. |
| Đổi `uid` nhưng nhóm vẫn trỏ tên cũ | Thay DN có thể không cập nhật các DN-valued refs. | Thiết kế đối soát/di chuyển có kiểm soát. |
| `NoPermissionException` | Account bind không có quyền đọc/ghi/rename. | Kiểm tra ACL theo OU/entry, không dùng admin. |
| `SchemaViolationException` | `objectClass`, naming attribute hoặc mandatory field không hợp lệ. | Kiểm tra schema trước khi thử lại. |
| `CommunicationException` | TLS, DNS, timeout, directory unavailable. | Kiểm tra kết nối; không coi user không tồn tại. |
| UID chứa dấu phẩy làm DN lỗi | Ghép chuỗi DN thủ công. | Dùng `LdapNameBuilder`/`LdapName`. |

### 16.1. Cách chẩn đoán theo thứ tự

1. Xem DN đầy đủ của fixture bằng `ldapsearch -s base`.
2. Xác định `ContextSource.base` và `@Entry.base`.
3. Đối chiếu **các RDN nằm ngoài base** với `@DnAttribute.index`.
4. Kiểm tra `value`, kiểu Java `String` và `@Id Name`.
5. Kiểm tra `@Attribute`/`@Transient` để không ghi attribute ngoài ý định.
6. Xác minh `objectClass`/schema và quyền bind account.
7. Thử đọc bằng `LdapTemplate.findByDn` trong directory test.
8. Chỉ sau khi đọc đúng mới thử create/update/rename trên fixture test có cleanup.

## 17. Bảo mật và nguyên tắc thiết kế

### 17.1. Không cho người gọi chỉ định OU tùy ý

`@DnAttribute` có thể khiến field `division` trở thành **phần vị trí của entry**. Nếu HTTP client được phép đặt `division="admins"` và ứng dụng dùng admin bind, code có thể tạo hoặc chuyển entry sang vùng nhạy cảm. Để tránh:

- Áp dụng allowlist OU theo nghiệp vụ và quyền của caller.
- Không chấp nhận full DN do người dùng HTTP tự đặt nếu use case không yêu cầu.
- Hạn chế LDAP bind account theo subtree/entry/operation; API validation không thay ACL.
- Phân biệt quyền đọc hồ sơ với quyền **Modify DN**.
- Ghi audit các thao tác create/rename/move theo request ID và actor được xác thực.

### 17.2. Giữ DN và thông tin cá nhân khỏi log công khai

DN có thể tiết lộ UID, nhóm, bộ phận hay cấu trúc tổ chức. Khi chẩn đoán, log có kiểm soát theo nguyên tắc dữ liệu tối thiểu, tránh công khai secret, full DN nhạy cảm hoặc raw LDAP diagnostic messages.

### 17.3. TLS, truststore và referral

Sử dụng LDAPS/StartTLS với xác minh chứng chỉ và hostname. Nếu directory dùng referral hoặc truy vấn nhiều server, phải kiểm tra riêng TLS, truststore và credential trên endpoint được giới thiệu. `@DnAttribute` không tự giải quyết chính sách referral hay mapping giữa naming contexts khác nhau.

## 18. Bài tập thực hành

1. Cho DN `uid=linh,ou=people,dc=example,dc=org` và `@Entry.base="ou=people"`. Hãy viết `@DnAttribute` phù hợp để map `uid`, đồng thời giải thích `@Id` khác gì.
2. Vì sao `@DnAttribute("uid")` có thể đọc `linh` nhưng chưa đáp ứng điều kiện để ODM tự tính DN khi tạo entry?
3. Cho DN `uid=an,ou=engineering,ou=employees,dc=example,dc=org`. Hãy điền `index` cho `uid` và `division` nếu `@Entry.base="ou=employees"`. Vẽ sơ đồ thứ tự thành phần.
4. Một field `division` chỉ xuất hiện trong `ou=engineering` của DN, không phải LDAP attribute. Hãy phối hợp `@DnAttribute` với annotation nào để tránh ghi attribute `division`?
5. Cho Java `LdapName` của DN trên. Liệt kê `getRdn(0..4)` và phân biệt với `@DnAttribute.index`.
6. Một entity có `@Id private String dn` và `@DnAttribute private Name uid`. Chỉ ra hai lỗi kiểu dữ liệu và sửa lại.
7. Viết method Spring Data LDAP repository tìm user theo `uid`; giải thích vì sao không được mặc định `findByUid` luôn cho một entry khi có nhiều OU.
8. Dùng `LdapNameBuilder` tạo DN với UID `"linh,dev"`. Vì sao nối chuỗi `"uid=" + uid` là không an toàn?
9. Tạo integration test đọc một user ở `uid=an,ou=engineering,ou=employees` rồi assert field `uid` và `division` được map đúng.
10. Thiết kế test create một entry với `index=0` và `index=1`, tìm lại bằng DN dự kiến và dọn fixture an toàn.
11. Khi đổi `division=engineering` thành `finance`, bước nào ngoài sửa một attribute có thể cần thiết? Phân tích ACL, parent OU, group refs và server topology.
12. Giải thích tại sao `@Transient` trên field dùng trong DN không có nghĩa field đó bị bỏ qua hoàn toàn khi parse `@DnAttribute`.

### Checklist

- [ ] Hiểu DN, RDN và AVA của LDAP.
- [ ] `@Id` dùng `Name`; `@DnAttribute` dùng `String`.
- [ ] Khai báo `value` của `@DnAttribute` đúng với thành phần mong muốn.
- [ ] Khi muốn tự tính DN, mọi field `@DnAttribute` có `index` phù hợp.
- [ ] Hiểu `index=0` gần `@Entry.base` và các index lớn hơn mở rộng sang trái.
- [ ] Phân biệt `@Entry.base` với `ContextSource.base` để không lặp base.
- [ ] Dùng `@Transient` nếu field chỉ mô tả đường dẫn, không phải LDAP attribute.
- [ ] Không nhầm ánh xạ DN với `@Attribute`/LDAP search filter.
- [ ] Dùng `LdapNameBuilder` và `LdapQueryBuilder` để escape an toàn.
- [ ] Xác minh schema, quyền read/create/Modify DN và sự tồn tại OU đích.
- [ ] Có integration test mapping một/nhiều RDN, create và rename/move.
- [ ] Không đổi DN của người dùng production như một cập nhật field bình thường.

## 19. Tài liệu tham khảo

- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): `@Entry`, `@Id`, `@DnAttribute`, `@Attribute`, `@Transient`, auto-compute DN và move entity.
- [Spring LDAP Javadoc — DnAttribute](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/DnAttribute.html): `value` bắt buộc, `index` mặc định `-1` và yêu cầu all-indexed để tự tính DN.
- [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html): repository và ODM entities.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories`, `LdapRepository<T>` và kiểu ID `Name`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `findByDn`, `findOne`, `create`, `update`, `rename`.
- [Java SE 17 — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html): cách đánh số RDN của JNDI, `getRdn` và parse DN.
- [Java SE 17 — Rdn](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html): AVA và multi-valued RDN.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): biểu diễn và escape DN.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, DN, schema và naming rules.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Modify DN, Bind và LDAP result codes.
- [RFC 4515 — LDAP Search Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515): escape filter khác escape DN.
