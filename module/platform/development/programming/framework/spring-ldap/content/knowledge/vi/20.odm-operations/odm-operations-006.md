# Chuyển đổi giữa object model và directory model trong Spring LDAP ODM

Một hệ thống quản lý nhân sự thường làm việc với đối tượng Java như `Employee` hoặc `DirectoryUser`, trong khi LDAP lưu thông tin dưới dạng **entry**, được xác định bằng **Distinguished Name (DN)** và tập các **attribute**. Nếu mỗi lần đọc hoặc cập nhật người dùng đều phải thao tác trực tiếp với `javax.naming.directory.Attributes`, code nghiệp vụ sẽ phụ thuộc nhiều vào cấu trúc directory.

**Object-Directory Mapping (ODM)** của **Spring LDAP** giúp chuyển dữ liệu theo hai chiều: **LDAP entry → Java object** khi đọc và **Java object → LDAP entry/attribute modifications** khi tạo hoặc cập nhật. Bài học thuộc chương **ODM operations**, giải thích hợp đồng chuyển đổi, cách xây entity, cách gọi `LdapTemplate`, những dữ liệu có thể mất hoặc biến đổi khi round-trip và cách kiểm tra kết quả an toàn.

## 1. Hai mô hình dữ liệu và luồng chuyển đổi

Xét entry LDAP biểu diễn người dùng:

```ldif
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
telephoneNumber: +84-90-123-4567
```

**Directory model** biểu diễn dữ liệu theo DN, object class, schema, tên attribute và các giá trị LDAP (có thể đơn trị, đa trị, nhị phân). **Object model** biểu diễn dữ liệu theo class Java, field và các kiểu dữ liệu như `String`, `Set<String>` hoặc `Name`.

| Directory model | Object model | Ý nghĩa |
| --- | --- | --- |
| `dn: uid=lan,ou=people,dc=example,dc=org` | `Name dn` được đánh dấu `@Id` | Địa chỉ của entry trong cây LDAP |
| `uid: lan` | `String uid` | Định danh người dùng |
| `cn: Lan Nguyen` | `String commonName` | Tên chung; tên field Java có thể khác tên thuộc tính |
| `sn: Nguyen` | `String surname` | Họ |
| `mail: lan@example.org` | `String email` | Email trong ví dụ là một giá trị |
| Hai dòng `telephoneNumber` | `Set<String> phoneNumbers` | Một attribute LDAP có nhiều giá trị |
| Các dòng `objectClass` | `@Entry(objectClasses = {...})` | Metadata về những object class mà entity quản lý |

```text
                         CHIỀU ĐỌC
   LDAP entry (DN, objectClass, attributes)
                       │
                       ▼
          LdapTemplate.findByDn/find
                       │
                       ▼
              ObjectDirectoryMapper
                       │
                       ▼
               Java ODM entity
                       │
             (có thể map tiếp)
                       ▼
                Domain DTO/API

                         CHIỀU GHI
   Java ODM entity có @Id và các field mapped
                       │
                       ▼
              ObjectDirectoryMapper
                       │
                       ▼
            LdapTemplate.create/update
                       │
                       ▼
     LDAP bind / modify attributes trên server
```

ODM tập trung ánh xạ **entry ↔ entity**. Việc tạo DTO riêng cho API là lựa chọn thiết kế ở tầng ứng dụng; không phải chức năng bắt buộc của ODM.

## 2. ObjectDirectoryMapper và các annotation quyết định chuyển đổi

`LdapTemplate` sử dụng thành phần `ObjectDirectoryMapper`, mặc định có thể khởi tạo mà không cần cấu hình thêm. Hai phương thức của interface này mô tả rõ hai hướng ánh xạ:

- `mapFromLdapDataEntry(..., Class<T>)`: biến biểu diễn entry của directory thành một đối tượng Java.
- `mapToLdapDataEntry(Object entry, ...)`: ghi các field của Java object vào biểu diễn entry để thực hiện thao tác LDAP.

Thông thường, **ứng dụng gọi các API ODM của `LdapTemplate`**, còn `ObjectDirectoryMapper` được dùng ở bên trong. Không cần tự gọi hai phương thức thấp cấp này trong một repository thông thường.

Các annotation thuộc package `org.springframework.ldap.odm.annotations`:

| Annotation | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| `@Entry` | Class | Khai báo entity LDAP và các `objectClass` mà class quản lý; bắt buộc. |
| `@Id` | Field kiểu `javax.naming.Name` | Chỉ DN của entry; bắt buộc. |
| `@Attribute(name = "...")` | Field | Chỉ định tên attribute LDAP tương ứng với field Java. |
| `@DnAttribute(value = "...", index = ...)` | Field kiểu `String` | Lấy thành phần DN; khi đủ `index` có thể giúp tính DN từ các field. |
| `@Transient` | Field | Loại field khỏi ánh xạ attribute LDAP. |

Nếu một field không có `@Attribute`, Spring LDAP ODM **thường vẫn ánh xạ field đó sang attribute LDAP cùng tên**, trừ khi nó được loại bằng `@Transient` hoặc có annotation điều chỉnh. Điều này khác kỳ vọng “field không đánh dấu sẽ tự bị bỏ qua” ở một số framework khác.

`@Entry` còn có thể khai báo `base = "ou=people"` để xác định nhánh gốc của loại entity. Trong ví dụ chính, chúng ta **không đặt `@Entry.base`** và chủ động cung cấp DN tương đối với base của `ContextSource`, giúp tránh nhập nhằng giữa các cấp DN.

## 3. Xây một Java entity đại diện LDAP entry

Giả sử ứng dụng đã cấu hình `ContextSource` với base DN `dc=example,dc=org`. Định nghĩa entity Java sau dùng `@Attribute` để quy định rõ các tên LDAP; field `uiLabel` chỉ tồn tại trong ứng dụng:

```java
import java.util.LinkedHashSet;
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class DirectoryUser {

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

    @Attribute(name = "telephoneNumber")
    private Set<String> phoneNumbers = new LinkedHashSet<>();

    @Transient
    private String uiLabel;

    public DirectoryUser() {
        // Constructor không tham số để ODM khởi tạo entity.
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

    public Set<String> getPhoneNumbers() { return phoneNumbers; }
    public void setPhoneNumbers(Set<String> phoneNumbers) {
        this.phoneNumbers = phoneNumbers == null
                ? new LinkedHashSet<>()
                : new LinkedHashSet<>(phoneNumbers);
    }

    public String getUiLabel() { return uiLabel; }
    public void computeUiLabel() {
        uiLabel = commonName == null ? uid
                : commonName + " (" + uid + ")";
    }
}
```

Cách ánh xạ ở đây có một số chủ ý:

1. `@Id` gắn với `Name`; DN không được lưu như một attribute `dn` bên trong entry.
2. `commonName` và `surname` là tên field thuận tiện trong Java, nhưng vẫn đọc/ghi các attribute LDAP `cn` và `sn`.
3. `phoneNumbers` dùng `Set<String>` vì các giá trị đa trị LDAP thường không có thứ tự có ý nghĩa. Không dựa vào phần tử “đầu tiên” để xác định số điện thoại chính.
4. `uiLabel` được đánh dấu `@Transient`, nên không phải attribute LDAP. ODM cũng **không tự gọi** `computeUiLabel()` sau mỗi lần đọc.
5. Entity có constructor không tham số và các field có thể được ODM khởi tạo khi map dữ liệu.

Thứ tự của `Set` trong object Java hay khi nhận từ LDAP không phải hợp đồng sắp xếp. Với các thuộc tính nhị phân, cần kiểu dữ liệu và cấu hình chuyển đổi phù hợp, không chuyển ảnh hoặc chứng chỉ sang chuỗi một cách tùy tiện.

## 4. Chiều đọc: directory model → object model

### 4.1. Tra cứu một entry theo DN

`LdapTemplate.findByDn(Name dn, Class<T> clazz)` nhận DN và class có metadata ODM, đọc entry, rồi trả về Java entity.

```java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryUserService {
    private final LdapTemplate ldapTemplate;

    public DirectoryUserService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryUser loadUser(String uid) {
        if (uid == null || uid.trim().isEmpty()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name relativeDn = LdapNameBuilder.newInstance()
                .add("ou", "people")
                .add("uid", uid)
                .build();

        DirectoryUser user =
                ldapTemplate.findByDn(relativeDn, DirectoryUser.class);

        user.computeUiLabel();
        return user;
    }
}
```

Với `ContextSource` có base `dc=example,dc=org`, đối tượng `relativeDn` tương ứng `uid=lan,ou=people`. DN thực trên directory là `uid=lan,ou=people,dc=example,dc=org`; tránh thêm base DN hai lần.

Quá trình đọc diễn ra theo thứ tự khái niệm:

1. `LdapTemplate` lookup entry theo DN với quyền bind hiện tại.
2. `ObjectDirectoryMapper` dùng metadata `@Entry`, `@Id` và `@Attribute` để chọn và chuyển các giá trị được trả về.
3. ODM tạo `DirectoryUser`; các field đơn trị, đa trị và `dn` nhận dữ liệu tương ứng.
4. `uiLabel` không lấy từ LDAP vì có `@Transient`. Service chủ động tính dữ liệu dẫn xuất sau khi đọc.

Nếu DN không tồn tại, `findByDn` không thể tự tạo entity mới; ứng dụng phải xử lý ngoại lệ LDAP tương ứng. Một field đọc ra là `null` cũng chưa đủ kết luận attribute đó không tồn tại trên server: nó có thể bị thiếu trong dữ liệu trả về hoặc bị ACL hạn chế.

### 4.2. Tìm nhiều entry với find

Khi chưa biết DN nhưng biết filter, sử dụng `LdapTemplate.find(LdapQuery, Class<T>)`:

```java
import java.util.List;

import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

// Đặt trong DirectoryUserService, có sẵn ldapTemplate:
public List<DirectoryUser> findBySurname(String lastName) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .countLimit(100)
            .timeLimit(3_000)
            .where("sn").is(lastName);

    List<DirectoryUser> results =
            ldapTemplate.find(query, DirectoryUser.class);

    results.forEach(DirectoryUser::computeUiLabel);
    return results;
}
```

ODM bổ sung điều kiện phù hợp với `@Entry.objectClasses` bên cạnh filter của query, giúp chỉ nhận những entry có cấu trúc tương thích. `countLimit` và `timeLimit` giới hạn chi phí truy vấn; danh sách 100 phần tử **không chứng minh** LDAP chỉ có 100 entry. Khi cần đủ toàn bộ entry, cần xử lý quota server, size/time limit và phân trang phù hợp.

So với `ldapTemplate.search(query, ContextMapper<T>)`: phương thức `find(query, DirectoryUser.class)` dùng ODM để tự xây đối tượng theo annotation. `ContextMapper` phù hợp khi muốn điều khiển cách map của từng context bằng code thay vì metadata ODM.

## 5. Chiều ghi: object model → directory model

Khi ứng dụng tạo hoặc thay đổi entity, `ObjectDirectoryMapper` chuyển dữ liệu từ field Java về DN và các attribute LDAP. `LdapTemplate` cung cấp ba thao tác thường dùng:

| Lệnh ODM | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `create(entry)` | Tạo một entry LDAP mới từ object Java | DN phải xác định được, schema phải cho phép, DN chưa tồn tại. |
| `update(entry)` | Đọc trạng thái hiện tại và áp dụng những thay đổi attribute do mapper tính | Không nên giả định có transaction với các hệ thống khác. |
| `delete(entry)` | Xóa entry được đại diện bởi object | Có thể bị từ chối bởi ACL, DN không tồn tại hoặc ràng buộc non-leaf. |

### 5.1. Tạo entry mới bằng create

Ví dụ thêm phương thức sau vào `DirectoryUserService`:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import javax.naming.Name;

// Giả sử "ou=people" đã tồn tại và server cho phép tạo inetOrgPerson.
public DirectoryUser createLan() {
    Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "lan")
            .build();

    DirectoryUser user = new DirectoryUser();
    user.setDn(dn);
    user.setUid("lan");
    user.setCommonName("Lan Nguyen");
    user.setSurname("Nguyen");
    user.setEmail("lan@example.org");
    user.setPhoneNumbers(new LinkedHashSet<>(Arrays.asList(
            "+84-28-1234-5678", "+84-90-123-4567")));

    ldapTemplate.create(user);
    return user;
}
```

Nếu DN `uid=lan,ou=people` đã tồn tại, create **phải bị từ chối**, ứng dụng cần báo xung đột thay vì cố ghi đè entry. Ngoài ra, `objectClass` do `@Entry` khai báo phải thỏa schema server, các trường bắt buộc như `cn` và `sn` phải có giá trị hợp lệ, và tài khoản LDAP phải được phép tạo entry dưới `ou=people`.

Ở chiều ghi, mapper sử dụng `uid`, `cn`, `sn`, `mail`, `telephoneNumber`; `uiLabel` **không tạo attribute LDAP**. Việc entity có giá trị Java cho `uiLabel` không làm field đó được persist.

Khi `@Id` chưa được gán, ODM có thể tính DN từ các field đánh dấu `@DnAttribute` nếu metadata cung cấp đủ index và base. Ví dụ hiện tại **chủ động gán DN** qua `LdapNameBuilder` nên không phụ thuộc cơ chế tự tính này.

### 5.2. Cập nhật entry hiện có bằng update

```java
// Đặt trong DirectoryUserService:
public void changeEmail(String uid, String newEmail) {
    DirectoryUser user = loadUser(uid);
    user.setEmail(newEmail);
    ldapTemplate.update(user);
}
```

Với một entry giữ nguyên DN, `LdapTemplate.update` đọc dữ liệu đang có ở directory, so sánh với object được ánh xạ rồi thực hiện sửa đổi attribute cần thiết. Đây là **cập nhật qua ODM**, khác với nối thủ công một danh sách `ModificationItem`.

Không nên xem toàn bộ Java object là một bản sao hoàn hảo của LDAP entry:

- Các field có `@Transient` không được ghi vào LDAP.
- Các attribute không được ánh xạ có thể không xuất hiện trong object nhưng vẫn tồn tại trên server; điều gì bị thay đổi còn phụ thuộc metadata và thuật toán cập nhật.
- Nếu gán `null` hoặc tập rỗng cho field đã được ánh xạ, mapper có thể diễn giải như yêu cầu bỏ giá trị attribute; schema có thể từ chối nếu attribute bắt buộc.
- Các giá trị đa trị thường được xem theo ngữ nghĩa tập hợp, không theo thứ tự xuất hiện trong file LDIF.

**DN cần đặc biệt thận trọng.** Nếu entity sử dụng `@DnAttribute(index = ...)` để tính DN và các thành phần tên bị đổi, `update` có thể dẫn đến thao tác di chuyển/đổi DN thay vì chỉ sửa thuộc tính. Cơ chế và mức an toàn của thay đổi DN phụ thuộc phiên bản và LDAP server; không thực hiện như một “chỉnh sửa field bình thường” khi chưa thiết kế rõ yêu cầu đổi tên.

## 6. Đọc lại entry để kiểm tra chuyển đổi

Một cách xác minh an toàn trong môi trường thử nghiệm là **create/update rồi đọc lại từ LDAP**, thay vì chỉ kiểm tra object Java đang giữ trong bộ nhớ.

```java
import org.springframework.ldap.core.DirContextOperations;

// Giả sử user vừa được tạo hoặc cập nhật thành công:
Name dn = LdapNameBuilder.newInstance()
        .add("ou", "people")
        .add("uid", "lan")
        .build();

DirectoryUser readAsObject =
        ldapTemplate.findByDn(dn, DirectoryUser.class);

DirContextOperations readAsDirectory =
        ldapTemplate.lookupContext(dn);

System.out.println("Object uid = " + readAsObject.getUid());
System.out.println("LDAP uid   = "
        + readAsDirectory.getStringAttribute("uid"));
System.out.println("LDAP cn    = "
        + readAsDirectory.getStringAttribute("cn"));
System.out.println("LDAP mail  = "
        + readAsDirectory.getStringAttribute("mail"));
```

Đoạn này minh họa hai góc nhìn **của cùng entry**: API ODM trả `DirectoryUser`, còn `lookupContext` trả `DirContextOperations` để kiểm tra attribute thô. Đừng đưa phép lookup này vào mọi request sản xuất nếu nó chỉ phục vụ thử nghiệm hoặc chẩn đoán.

Với `telephoneNumber`, dùng `getStringAttributes("telephoneNumber")` khi đọc phía directory và so sánh **tập giá trị**, tránh so sánh theo vị trí mảng. Với field `uiLabel` có `@Transient`, không kỳ vọng có attribute `uiLabel` trên server chỉ vì ứng dụng tính được giá trị đó.

## 7. Object model ODM và domain DTO là hai lớp có thể tách riêng

Một `DirectoryUser` gắn annotation ODM vẫn hiểu cấu trúc LDAP: nó có `@Id`, `@Attribute` và field mang dữ liệu directory. Tầng API có thể muốn một model riêng chỉ gồm dữ liệu cần công bố, ví dụ:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class UserProfile {
    private final String username;
    private final String fullName;
    private final String email;
    private final List<String> phones;

    public UserProfile(
            String username,
            String fullName,
            String email,
            List<String> phones) {
        this.username = username;
        this.fullName = fullName;
        this.email = email;
        this.phones = Collections.unmodifiableList(
                new ArrayList<>(phones));
    }

    public String getUsername() { return username; }
    public String getFullName() { return fullName; }
    public String getEmail() { return email; }
    public List<String> getPhones() { return phones; }
}
```

Ánh xạ entity ODM sang DTO được thực hiện rõ ràng ở tầng ứng dụng:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Set;

public final class UserProfileMapper {
    private UserProfileMapper() {
    }

    public static UserProfile fromDirectoryUser(DirectoryUser user) {
        Set<String> phones = user.getPhoneNumbers();
        return new UserProfile(
                user.getUid(),
                user.getCommonName(),
                user.getEmail(),
                phones == null
                        ? Collections.emptyList()
                        : new ArrayList<>(phones));
    }
}
```

Với cách tách này:

- Entity ODM diễn đạt dữ liệu và các quy tắc mapping của **LDAP schema**.
- DTO diễn đạt dữ liệu mà API hoặc giao diện muốn hiển thị.
- Không bắt buộc trả nguyên DN hoặc tất cả attribute LDAP ra API.
- Nếu cần biến đổi ngược từ yêu cầu cập nhật DTO sang entity ODM, service nên nạp entry hiện có rồi chỉ áp dụng các field được phép sửa; đừng lấy mọi field từ request để ghi đè lên directory.

Ví dụ phần cập nhật ngược:

```java
// Với user là DirectoryUser đã nạp và validatedEmail đã được kiểm tra:
user.setEmail(validatedEmail);
ldapTemplate.update(user);
```

Ở đây `validatedEmail` là dữ liệu đã được tầng API/service kiểm tra theo quy tắc ứng dụng. Ghi dữ liệu từ request trực tiếp vào mọi field ODM có thể dẫn đến thay đổi DN, quyền hoặc thuộc tính ngoài dự kiến.

## 8. Những chỗ dữ liệu dễ thay đổi khi round-trip

**Round-trip** là quá trình đọc entry LDAP thành Java object, có thể thay đổi object, rồi ghi lại thành entry. Chuyển đổi hai chiều giúp giảm code thủ công, nhưng **không bảo đảm phép biến đổi là hai hàm đảo hoàn hảo**.

| Trường hợp | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Attribute LDAP đơn trị nhưng Java field là kiểu không phù hợp | Mapper không chuyển được hoặc bị mất thông tin | Chọn kiểu Java tương thích schema, kiểm thử conversion. |
| Attribute LDAP đa trị | Thứ tự giá trị không được đảm bảo | Dùng `Set`/collection phù hợp, so sánh tập hợp. |
| Attribute không có trong entry hoặc không được quyền đọc | Field Java có thể là `null` hoặc collection không có giá trị | Phân biệt trường bắt buộc/tùy chọn và quyền đọc. |
| Attribute nhị phân, ví dụ `jpegPhoto` | Ép sang `String` có thể làm hỏng dữ liệu | Dùng kiểu nhị phân và cấu hình chuyển đổi phù hợp. |
| `@Transient` | Field chỉ thuộc Java, không persist | Tính lại sau khi đọc; không dùng làm nguồn dữ liệu directory. |
| DN lấy từ `@Id` | DN không phải attribute bình thường | Xây bằng `LdapNameBuilder`, tránh nối chuỗi tùy tiện. |
| DN được tính từ `@DnAttribute` | Đổi field có thể gây rename/move | Tách rõ nghiệp vụ đổi DN khỏi cập nhật thuộc tính. |
| Server có operational attribute hoặc chuẩn hóa giá trị | Giá trị thô có thể khác đầu vào | Đọc lại và so sánh theo đúng ý nghĩa schema. |
| Bị giới hạn thời gian/số entry khi search | Danh sách Java có thể không đầy đủ | Xử lý size/time limit, dùng paging khi cần. |

### 8.1. String, Collection, Name và dữ liệu nhị phân

Các kiểu hay dùng:

- `String` phù hợp với nhiều thuộc tính văn bản đơn trị.
- `Set<String>` hoặc collection phù hợp cho thuộc tính đa trị; không giả định thứ tự.
- `javax.naming.Name` phù hợp với DN, kể cả khi DN nằm trong thuộc tính nhiều giá trị của nhóm LDAP. Spring LDAP ODM có hỗ trợ ánh xạ `Set<Name>` trong ví dụ nhóm của tài liệu chính thức.
- `byte[]` hoặc kiểu nhị phân tương ứng nên dùng cho ảnh/chứng chỉ, kết hợp type conversion thích hợp.

Schema LDAP quyết định thuộc tính nào được phép đơn trị hoặc đa trị. Ví dụ một số directory cho phép `mail` có nhiều giá trị; mapping `String email` của bài chỉ phù hợp khi nghiệp vụ thống nhất cách chọn một giá trị.

### 8.2. Chuyển kiểu tùy biến

Nếu entity có field nghiệp vụ phức tạp như enum, định dạng ngày giờ đặc thù hoặc giá trị nhị phân chuyên biệt, kiểu mặc định có thể chưa đủ. `ObjectDirectoryMapper` hỗ trợ `ConversionService` của Spring để thêm các `Converter` theo hai chiều.

Tài liệu Spring LDAP hiện hành có hai hướng cấu hình:

1. Trong **Spring Boot**, các `Converter` được khai báo thành bean có thể được `ObjectDirectoryMapper` do Boot cung cấp nhận diện.
2. Khi **không dùng Boot**, có thể import `ObjectDirectoryMapperConfiguration` để cung cấp bean `ObjectDirectoryMapper`, sau đó truyền vào `LdapTemplate` qua `setObjectDirectoryMapper(...)`.

Điều này cho phép quy định chuyển đổi từ định dạng LDAP sang kiểu Java và ngược lại, nhưng phải kiểm tra **cả hai chiều** nếu ứng dụng sẽ vừa đọc vừa ghi. Không giả định mọi enum hoặc kiểu Java tùy biến đều được tự động chuyển thành attribute LDAP hợp lệ.

## 9. Lỗi cần phân biệt ở hai chiều chuyển đổi

| Tình huống | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `findByDn` không tìm thấy entry | DN sai, base khác hoặc entry không tồn tại | Kiểm tra DN tương đối và ngữ cảnh; xử lý lỗi không tìm thấy. |
| `find` trả ít kết quả hơn dự kiến | Search filter, ACL, quota hoặc hạn mức | Rà filter, search scope, size/time limit. |
| Field đọc thành `null` | Attribute thiếu, bị ẩn hoặc mapping tên sai | Kiểm tra `@Attribute`, schema và quyền đọc. |
| `create` bị từ chối vì DN đích đã có | Xung đột tên | Không xóa/ghi đè entry đích; chọn DN khác. |
| `create/update` lỗi schema | Thiếu attribute bắt buộc hoặc kiểu dữ liệu sai | Kiểm tra `objectClass`, `cn`, `sn` và các ràng buộc máy chủ. |
| `update` thay đổi ngoài ý muốn | Mapping quá rộng, setter ghi nhầm field, hoặc DN được tính lại | Tách DTO đầu vào, chỉ cho sửa field cần thiết, kiểm thử readback. |
| ODM báo lỗi conversion | Không có chuyển kiểu phù hợp | Chọn kiểu Java đúng hoặc đăng ký `Converter`. |
| Lỗi xác thực/ACL/TLS | Cấu hình bảo mật hoặc quyền không phù hợp | Xử lý tại tầng kết nối và phân quyền; không xem là lỗi mapping thuần túy. |

**Không log toàn bộ entry** nếu chứa email, số điện thoại, nhóm quyền hoặc thông tin nhạy cảm. Đặc biệt, không đưa mật khẩu hay credential bind vào domain DTO chỉ để tiện xử lý. Khi cần xác thực người dùng, hãy sử dụng luồng bind/authentication phù hợp thay vì so sánh giá trị mật khẩu đọc từ LDAP.

## 10. Kiểm thử chuyển đổi theo cả hai chiều

Để kiểm tra phép ánh xạ một cách đáng tin cậy, nên dùng LDAP server thử nghiệm với schema phù hợp. Unit test chỉ kiểm tra DTO mapper Java chưa xác nhận được hành vi persistence của ODM trên directory.

### 10.1. Bài thực hành

Giả sử server thử nghiệm có base `dc=example,dc=org` và nhánh `ou=people`, tài khoản bind có quyền đọc/ghi entry thử nghiệm:

1. **Đọc:** Tạo entry bằng LDIF ở phần 1 (hoặc chuẩn bị entry tương đương), gọi `findByDn` và kiểm tra `uid`, `commonName`, `surname`, `email` cùng tập `phoneNumbers`.
2. **Ánh xạ DTO:** Gọi `UserProfileMapper.fromDirectoryUser(user)`, xác nhận các trường cần hiển thị được đưa sang `UserProfile`; không có DN trong DTO.
3. **Tạo:** Sử dụng `create` cho một `uid` thử nghiệm chưa tồn tại; dùng `lookupContext` kiểm tra các LDAP attribute do mapper ghi.
4. **Cập nhật:** Đổi `email` trong object, gọi `update`, rồi đọc lại từ LDAP bằng một lần `findByDn` mới để xác nhận.
5. **Đa trị:** Thêm và bỏ một số điện thoại; so sánh **tập giá trị** giữa object và directory sau khi ghi, không so sánh thứ tự.
6. **Transient:** Đặt `uiLabel` bằng `computeUiLabel()`, gọi `update` và kiểm tra ODM không tạo attribute `uiLabel` từ field này.
7. **Lỗi:** Thử tạo cùng một DN hai lần; kiểm tra ứng dụng phân loại conflict, không làm hỏng entry đã tồn tại.
8. **Quyền:** Thử tài khoản chỉ được đọc; xác minh thao tác ghi bị từ chối và được xử lý đúng, không tự nâng quyền.
9. **Khôi phục:** Xóa hoặc hoàn nguyên entry thử nghiệm theo quy trình môi trường, tránh thao tác trên dữ liệu sản xuất.

### 10.2. Ma trận kỳ vọng

| Thao tác | Directory model | Object model |
| --- | --- | --- |
| `findByDn` | Entry có DN và thuộc tính phù hợp | Entity được gán `dn` và các field ánh xạ |
| `find(query, clazz)` | Nhiều entry thỏa filter và object class | `List<DirectoryUser>` |
| `create(entity)` | Entry mới cùng `objectClass` và các field mapped | Object vẫn là object Java đã cung cấp |
| `update(entity)` | Các attribute được sửa theo mapping và trạng thái hiện tại | Object được dùng làm đầu vào ghi |
| `@Transient` | Không thêm attribute tương ứng từ field dẫn xuất | Field có thể được tính trong bộ nhớ |
| Lookup lại sau update | Giá trị đang được server lưu | Entity mới phản ánh dữ liệu đọc được ở thời điểm đó |

Nếu ứng dụng dùng dữ liệu quan trọng, hãy bổ sung test về giá trị rỗng, schema constraints, multi-valued attributes và thay đổi đồng thời. Một lần `create/update` trả về thành công **không đồng nghĩa** các hệ thống khác đang lưu DN hoặc cache LDAP đã được đồng bộ ngay tức thì.

## 11. Câu hỏi tự kiểm tra

1. Vai trò của `ObjectDirectoryMapper` khác vai trò của `LdapTemplate` ở đâu?
2. Vì sao `@Entry` và `@Id` là metadata bắt buộc của một ODM entity?
3. Với Java field `commonName`, dùng annotation gì để đọc/ghi attribute LDAP `cn`?
4. Tại sao `@Transient` không tự tính lại một nhãn hiển thị sau `findByDn`?
5. Nếu dùng `Set<String>` cho `telephoneNumber`, vì sao không nên kiểm tra theo vị trí của các phần tử?
6. Khi nào `update(entity)` có thể liên quan tới thay đổi DN thay vì chỉ sửa attribute?
7. Vì sao cần đọc lại từ directory sau khi `create` hoặc `update` trong một integration test?
8. Nếu API chỉ cho người dùng đổi email, vì sao nên map request vào field email của entity đã tải thay vì nhận một entity ODM nguyên vẹn từ client?
9. Một phép chuyển đổi thành công có bảo đảm LDAP search đã trả đủ mọi entry hay không?

## 12. Ghi nhớ

- **Chiều đọc:** `LdapTemplate.findByDn/find` sử dụng ODM để chuyển LDAP entry thành Java entity dựa trên `@Entry`, `@Id`, `@Attribute` và các annotation liên quan.
- **Chiều ghi:** `LdapTemplate.create/update` chuyển entity thành thao tác tạo entry hoặc sửa attribute trong LDAP, chịu ràng buộc schema, ACL và trạng thái của server.
- `ObjectDirectoryMapper` thực hiện logic ánh xạ bên trong; nên thao tác qua `LdapTemplate` trong đa số ứng dụng.
- Phân biệt **DN** với attribute thông thường, dữ liệu đơn trị với đa trị, và field được persist với `@Transient`.
- **Round-trip không nhất thiết giữ nguyên mọi chi tiết**: cần xem quyền truy cập, kiểu dữ liệu, giá trị rỗng, ordering, operational attributes và thay đổi đồng thời.
- Với API hướng nghiệp vụ, có thể chuyển ODM entity sang DTO riêng để kiểm soát dữ liệu công khai và các field được phép cập nhật.

## Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring LDAP Javadoc — ObjectDirectoryMapper](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/core/ObjectDirectoryMapper.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html)
- [Spring LDAP Javadoc — LdapOperations](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html)
- [Spring LDAP Javadoc — DnAttribute](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/DnAttribute.html)
- [Spring LDAP Reference — Simplifying Attribute Access with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html)
