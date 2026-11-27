# Đọc object bằng LdapTemplate và ODM mapping

## Mục tiêu học tập

**Spring LDAP** cho phép thao tác thư mục ở hai mức: làm việc trực tiếp với DN và các LDAP attribute, hoặc **ánh xạ một LDAP entry thành một object Java** bằng Object-Directory Mapping (**ODM**). Trong chương **ODM operations**, bài này tập trung vào cách **đọc object** thông qua `LdapTemplate` và các annotation ODM.

Sau bài học, bạn có thể:

1. Giải thích luồng **LDAP entry → LDAP attributes → ODM mapping → Java object** và phân biệt nó với JPA/JDBC.
2. Định nghĩa class ODM với `@Entry`, `@Id`, `@Attribute`; biết vai trò của DN, objectClass và tên attribute trong schema.
3. Dùng `LdapTemplate.findByDn(...)` để tải một object từ DN và `LdapTemplate.find(...)` để tìm nhiều object bằng filter.
4. Xử lý attribute bị thiếu, nhiều giá trị, tên Java khác tên LDAP và kiểu dữ liệu cần chuyển đổi.
5. Phân biệt lỗi **không có entry**, **mapping không hợp lệ**, **thiếu quyền** và **kết nối LDAP**; kiểm thử trên LDAP server phù hợp.

Nội dung sử dụng `ContextSource`, `LdapTemplate` và ODM của Spring LDAP. Các nguyên tắc về DN, schema, filter và TLS tiếp tục áp dụng khi ứng dụng dùng `LdapClient` hoặc JNDI; tuy nhiên, các API ODM được giới thiệu ở đây thuộc riêng Spring LDAP.

## 1. Vì sao cần ODM khi đọc LDAP?

Giả sử thư mục có entry nhân viên:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
telephoneNumber: +84 90 111 2222
telephoneNumber: +84 28 3822 0000
~~~

Không dùng ODM, ứng dụng có thể đọc từng thuộc tính:

~~~java
DirContextOperations ctx = ldapTemplate.lookupContext(dn);

String fullName = ctx.getStringAttribute("cn");
String email = ctx.getStringAttribute("mail");
String[] phones = ctx.getStringAttributes("telephoneNumber");
~~~

Cách này phù hợp cho thao tác linh hoạt, nhưng khi một hệ thống liên tục phải ánh xạ nhiều entry thành object nghiệp vụ, các dòng đọc bằng tên chuỗi dễ lặp lại. ODM cho phép định nghĩa **class Java và quy tắc ánh xạ** một lần, sau đó dùng `LdapTemplate` tải object đã được điền dữ liệu.

Ví dụ mục tiêu:

~~~java
DirectoryPerson person =
    ldapTemplate.findByDn(dn, DirectoryPerson.class);

System.out.println(person.getFullName());
~~~

Ở đây, `getFullName()` là getter của Java object. Nó được điền từ LDAP attribute `cn` thông qua annotation, không yêu cầu Java property phải mang đúng tên `cn`.

### Luồng đọc object

~~~mermaid
flowchart LR
    A["DN hoặc LDAP filter"] --> B["LdapTemplate"]
    B --> C["ContextSource / LDAP server"]
    C --> D["LDAP entry và Attributes"]
    D --> E["Spring LDAP ODM mapper"]
    E --> F["@Entry / @Id / @Attribute"]
    F --> G["DirectoryPerson"]
    G --> H["Service / API"]
~~~

**ODM không thay thế LDAP server.** Việc xác thực, kiểm tra quyền đọc, search scope, filter, TLS và giới hạn truy vấn vẫn do `ContextSource`, `LdapTemplate` và LDAP server quyết định. ODM chủ yếu giải quyết **cách biểu diễn entry dưới dạng object Java**.

## 2. Những annotation ODM cần biết

Spring LDAP ODM định nghĩa annotation trong package `org.springframework.ldap.odm.annotations`.

| Annotation | Vai trò | Ví dụ |
| --- | --- | --- |
| `@Entry` | Đánh dấu class đại diện cho LDAP entry; khai báo objectClasses và có thể khai báo base DN | `@Entry(base = "ou=people", objectClasses = {"inetOrgPerson", ...})` |
| `@Id` | Đánh dấu field chứa DN của entry, thường có kiểu `javax.naming.Name` | `@Id private Name dn;` |
| `@Attribute` | Liên kết field Java với tên LDAP attribute | `@Attribute(name = "cn") private String fullName;` |
| `@DnAttribute` | Liên kết field với thành phần RDN để hỗ trợ xử lý tên theo mô hình ODM | Dùng khi mô hình cần lấy/xây dựng một thành phần DN |
| `@Transient` | Loại field khỏi việc ánh xạ dữ liệu LDAP | Dành cho dữ liệu tính toán chỉ có trong Java |

Các annotation được đọc bởi cơ chế mapping của Spring LDAP; chúng **không** tạo objectClass mới trong server hoặc tự sửa schema.

### 2.1. Class Java đại diện cho entry

Định nghĩa đầy đủ một kiểu object:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    // Tên field Java khác tên attribute LDAP.
    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "telephoneNumber")
    private String[] phoneNumbers;

    public DirectoryPerson() {
        // ODM cần có khả năng khởi tạo đối tượng.
    }

    public Name getDn() {
        return dn;
    }

    public String getUid() {
        return uid;
    }

    public String getFullName() {
        return fullName;
    }

    public String getSurname() {
        return surname;
    }

    public String getEmail() {
        return email;
    }

    public String[] getPhoneNumbers() {
        return phoneNumbers;
    }
}
~~~

Các điểm cần nhớ:

- `@Entry` khai báo class được ánh xạ từ loại entry tương ứng. `objectClasses` phải phù hợp với schema và dữ liệu thật của thư mục; ví dụ ở đây dành cho `inetOrgPerson`, không dùng mặc định cho mọi loại account.
- `@Id` là **DN**, ví dụ `uid=lan,ou=people,dc=example,dc=org`. DN là tên/vị trí trong cây, không phải một id số tự tăng như trong SQL.
- `@Attribute(name = "cn")` cho phép Java gọi field là `fullName`, còn dữ liệu đến từ attribute `cn`.
- `telephoneNumber` có thể có nhiều giá trị. Mẫu này dùng `String[]` để biểu diễn, nhưng **thứ tự** các giá trị trong LDAP không mang ý nghĩa ưu tiên trừ khi nghiệp vụ định nghĩa riêng.
- Constructor không tham số và khả năng truy cập field theo quy tắc ODM cần được bảo đảm. Trong thực tế, có thể bổ sung setter/validation theo nhu cầu domain model.

**Lưu ý:** DN và thuộc tính `uid` liên quan nhưng không đồng nhất. `@Id` đọc tên entry, còn `@Attribute(name = "uid")` đọc attribute `uid` từ dữ liệu đã được server trả về. Khi chuyển entry sang OU khác, DN có thể thay đổi trong khi `uid` không đổi.

### 2.2. Base DN có hai tầng cần phân biệt

Ví dụ sử dụng:

~~~text
ContextSource base: dc=example,dc=org
@Entry base:       ou=people
DN tương đối:      uid=lan,ou=people
DN đầy đủ:         uid=lan,ou=people,dc=example,dc=org
~~~

- `ContextSource.base` xác định **vùng tên tương đối** mà `LdapTemplate` thường làm việc.
- `@Entry(base = "ou=people")` mô tả vị trí cơ sở của kiểu object trong mapping.
- Đối số DN truyền cho thao tác cụ thể phải theo **quy ước của API đang dùng và ContextSource**; trong ví dụ `findByDn` dưới đây, DN bao gồm `ou=people` nhưng không nhân đôi base `dc=example,dc=org`.

Không tự nối chuỗi DN từ dữ liệu người dùng. Dùng `LdapNameBuilder` để escape RDN phù hợp và kiểm tra người dùng được phép đọc đối tượng đích.

## 3. Đọc một object bằng `findByDn`

`LdapTemplate.findByDn(Name dn, Class<T> clazz)` là cách ngắn gọn để đọc một entry **đã biết DN** thành object của class ODM.

Ví dụ service:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryPersonService {

    private final LdapTemplate ldapTemplate;

    public DirectoryPersonService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryPerson findLan() {
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "lan")
            .build();

        return ldapTemplate.findByDn(dn, DirectoryPerson.class);
    }
}
~~~

**Ý nghĩa từng bước:**

1. `LdapNameBuilder` tạo DN tương đối `uid=lan,ou=people` một cách an toàn.
2. `LdapTemplate` dùng `ContextSource` để truy cập LDAP server, tra cứu entry đích.
3. Mapper ODM đọc các thuộc tính liên quan và tạo một `DirectoryPerson`.
4. `@Id` nhận DN; các field có `@Attribute` nhận giá trị tương ứng nếu server trả về và quyền đọc cho phép.

Dữ liệu sử dụng được sau khi đọc:

~~~java
DirectoryPerson person = service.findLan();

System.out.println(person.getUid());      // lan
System.out.println(person.getFullName()); // Lan Tran
System.out.println(person.getEmail());    // lan@example.org

String[] phones = person.getPhoneNumbers();
if (phones != null) {
    for (String phone : phones) {
        System.out.println(phone);
    }
}
~~~

Đây là ví dụ chức năng, không khuyến khích log dữ liệu định danh hay số điện thoại của người dùng trên hệ thống sản xuất. Trong ứng dụng thật, map object sang DTO chỉ chứa dữ liệu API thực sự cần.

### 3.1. Ưu tiên `findByDn` khi nào?

- Bạn **đã biết DN chính xác** từ workflow hoặc dữ liệu trước đó.
- Cần lấy **một entry** chứ không cần tìm kiếm trên toàn subtree.
- DN vẫn còn hợp lệ, phù hợp `ContextSource.base` và entry thuộc loại objectClass mà mapper chấp nhận.

Nếu chỉ biết `uid` nhưng chưa biết entry nằm ở OU nào, đừng tự đoán DN. Hãy tìm kiếm với filter an toàn trong base và scope đúng.

### 3.2. Entry không tồn tại

Khi DN sai hoặc entry đã bị xóa/move, `findByDn` có thể trả lỗi tìm tên từ LDAP (thường là `org.springframework.ldap.NameNotFoundException` theo cách triển khai lookup của phiên bản sử dụng).

Nếu nghiệp vụ muốn biểu diễn “có hoặc không có”, có thể chuẩn hóa ở repository:

~~~java
import java.util.Optional;
import javax.naming.Name;

import org.springframework.ldap.NameNotFoundException;

public Optional<DirectoryPerson> findOptionalByDn(Name dn) {
    try {
        return Optional.ofNullable(
            ldapTemplate.findByDn(dn, DirectoryPerson.class)
        );
    } catch (NameNotFoundException ex) {
        return Optional.empty();
    }
}
~~~

Đây là đoạn minh họa trong repository/service có field `ldapTemplate`. Chỉ dùng `Optional.empty()` để biểu diễn **entry không tìm thấy**, không bắt chung lỗi quyền, schema, mapper hoặc kết nối rồi coi như người dùng không tồn tại.

Quan trọng hơn, lỗi không tìm thấy cũng có thể do **base DN hoặc parent OU sai**, vì vậy cần kiểm tra cấu hình trước khi chuyển trực tiếp thành HTTP 404 cho người dùng cuối.

## 4. Tìm nhiều object bằng filter với `find`

Khi DN không biết trước, `LdapTemplate.find(LdapQuery query, Class<T> clazz)` có thể thực hiện LDAP Search và ánh xạ các entry phù hợp thành danh sách object.

Ví dụ truy vấn theo `uid`:

~~~java
import java.util.List;

import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;

public List<DirectoryPerson> findByUid(String uid) {
    LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("uid").is(uid);

    return ldapTemplate.find(query, DirectoryPerson.class);
}
~~~

Kết quả là `List<DirectoryPerson>`; nếu search base tồn tại nhưng không entry nào khớp filter, kết quả tìm kiếm thông thường là danh sách rỗng. Không phải `NameNotFoundException` chỉ vì **filter không khớp**.

Giải thích:

- `base("ou=people")` giới hạn vùng tìm kiếm tương đối với `ContextSource.base`.
- `where("uid").is(uid)` xây filter từ API của Spring LDAP, tránh ghép trực tiếp chuỗi lọc do người dùng cung cấp.
- `find(...)` thực hiện search qua LDAP server và ánh xạ các entry tìm thấy bằng annotation ODM.
- Kết quả có thể chứa nhiều entry nếu `uid` không được bảo đảm duy nhất trong vùng tìm kiếm; schema LDAP không tự bảo đảm một thuộc tính `uid` là khóa duy nhất cho toàn bộ subtree.

Nếu cần đúng một object, có thể dùng `findOne(...)` theo API phiên bản hỗ trợ, nhưng phải **xác định quy tắc khi có 0 hoặc nhiều kết quả**, rồi kiểm thử. Không nên chỉ lấy `results.get(0)` và coi đó là người duy nhất: LDAP Search không bảo đảm thứ tự khi không có sort control.

### 4.1. DN và filter dùng cách escape khác nhau

Hai trường hợp sau **khác về cú pháp và mục đích**:

~~~java
// Khi biết DN, escape theo cấu trúc tên LDAP.
Name dn = LdapNameBuilder.newInstance()
    .add("ou", "people")
    .add("uid", uid)
    .build();

// Khi tìm kiếm, dùng bộ dựng LDAP filter của Spring LDAP.
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .where("uid").is(uid);
~~~

Không tự ghép:

~~~java
// Tránh cách xây filter với input không tin cậy:
String unsafeFilter = "(uid=" + uid + ")";
~~~

Nếu `uid` chứa ký tự có ý nghĩa đặc biệt trong LDAP filter, nối chuỗi có thể tạo sai filter hoặc gây LDAP injection. Bộ dựng DN giải quyết **escaping tên**, còn bộ dựng filter giải quyết **escaping biểu thức lọc**.

### 4.2. Scope và giới hạn tìm kiếm

Khi tìm kiếm nhiều object, hãy xác định search scope: chỉ chính entry base, một cấp con, hay toàn bộ subtree. Với dữ liệu nhiều tầng, scope ảnh hưởng đến số entry tìm thấy và thời gian xử lý.

Nếu toàn bộ directory có hàng chục nghìn entry, `find(...)` trả về `List<T>` có thể tiêu tốn bộ nhớ. Cần giới hạn phạm vi, chỉ tải những thuộc tính cần thiết, hoặc sử dụng API search cùng cơ chế phân trang (RFC 2696) khi bài toán thực sự yêu cầu xử lý khối lượng lớn. **ODM mapping không tự động biến mọi tìm kiếm thành phân trang**.

## 5. So sánh ODM với cách đọc bằng `lookupContext` và mapper

Spring LDAP hỗ trợ nhiều mức trừu tượng. Việc chọn đúng API giúp tránh code phức tạp không cần thiết.

| Cách đọc | Kết quả | Khi phù hợp | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `ldapTemplate.lookupContext(dn)` | `DirContextOperations` | Xem/sửa trực tiếp attribute của một DN | Tự gọi getter cho từng attribute |
| `ldapTemplate.lookup(dn, mapper)` | Đối tượng do `ContextMapper`/`AttributesMapper` tạo | Mapping tùy biến theo truy vấn | Phải tự viết mapper |
| `ldapTemplate.search(..., mapper)` | Danh sách kết quả đã map | Tìm kiếm có filter, map dữ liệu linh hoạt | Mapper thường do ứng dụng định nghĩa |
| `ldapTemplate.findByDn(dn, clazz)` | Object ODM của một DN | Class đã khai báo annotation đầy đủ | Phụ thuộc cấu trúc mapping của class |
| `ldapTemplate.find(query, clazz)` | `List<T>` ODM | Search theo filter và trả object typed | Cần quản lý scope, số kết quả, ngoại lệ |

So sánh trực tiếp:

~~~java
// 1. Đọc trực tiếp attribute.
DirContextOperations entry = ldapTemplate.lookupContext(dn);
String name = entry.getStringAttribute("cn");

// 2. Đọc bằng ODM.
DirectoryPerson person =
    ldapTemplate.findByDn(dn, DirectoryPerson.class);
String nameFromObject = person.getFullName();
~~~

Trong cách ODM, ánh xạ `cn → fullName` được định nghĩa một lần trong class. Nhưng nếu query chỉ cần đúng một hoặc hai thuộc tính hoặc dữ liệu LDAP không khớp với domain model, `AttributesMapper`/`ContextMapper` có thể đơn giản và dễ kiểm soát hơn.

**Không đồng nhất ODM với JPA.** Spring LDAP ODM không mặc nhiên cung cấp persistence context, lazy-loading quan hệ, transaction kiểu RDBMS hoặc tự phát hiện/sync mọi thay đổi object. Việc cập nhật LDAP, nếu cần, phải dùng API được hỗ trợ như `ldapTemplate.update(...)` hoặc `modifyAttributes(...)` và tuân thủ schema/ACL.

## 6. Những trường hợp mapping phải xử lý cẩn thận

### 6.1. Attribute LDAP không có hoặc không được phép đọc

Nếu `mail` không tồn tại, field `email` của object có thể là `null` tùy loại field/mapper. Nếu ACL ẩn thuộc tính này, kết quả cũng có thể không cung cấp nó.

Đừng kết luận “không có email” chỉ vì `getEmail() == null` nếu nghiệp vụ cần phân biệt **chưa gán**, **không được phép đọc** và **mapping thiếu trường**. Tình huống này khác với entry không tồn tại.

### 6.2. LDAP attribute nhiều giá trị

Với:

~~~ldif
telephoneNumber: +84 90 111 2222
telephoneNumber: +84 28 3822 0000
~~~

field `String[] phoneNumbers` có thể nhận nhiều giá trị nếu mapper và schema phù hợp. Không dựa vào `phoneNumbers[0]` làm “số chính”: LDAP attribute nhiều giá trị không xác định thứ tự theo ý nghĩa nghiệp vụ.

Nếu cần phân biệt số chính và phụ, thiết kế thuộc tính riêng hoặc quy tắc xử lý rõ ràng; việc ODM đọc vào mảng không tạo thứ tự tự nhiên.

### 6.3. Chuyển đổi kiểu dữ liệu và binary attribute

LDAP có nhiều syntax: chuỗi, boolean, số, thời gian, octet string... Không phải mọi attribute đều có thể ép sang `String`.

Ví dụ `jpegPhoto` thường chứa dữ liệu nhị phân. Nếu ánh xạ một field `byte[]` hoặc converter tương ứng, phải xác minh server trả đúng dạng dữ liệu và Spring LDAP ODM hỗ trợ mapping theo cấu hình. Không chuyển `byte[]` thành chuỗi bằng `toString()` rồi coi đó là nội dung ảnh.

Tương tự, `createTimestamp`, `entryUUID` hoặc các operational attribute chỉ xuất hiện khi server hỗ trợ và client yêu cầu đúng tên với ACL phù hợp; annotation `@Attribute` không tự cấp quyền truy cập hay buộc server trả về attribute vận hành.

### 6.4. ObjectClass và schema

`@Entry(objectClasses = ...)` xác định kiểu entry mà class ODM đại diện. Nó không tự tạo các `objectClass` ấy trong directory khi chỉ **đọc** dữ liệu.

Nếu object thật dùng lớp `organizationalUnit` thay vì `inetOrgPerson`, class `DirectoryPerson` không phải mô hình phù hợp. Cần xác định class cho từng loại entry và đối chiếu schema, tránh gom mọi object vào một kiểu Java rồi đọc nhầm trường.

Với `@Attribute(name = "cn")`, khác biệt tên `cn`/`fullName` đã được khai báo rõ. Nếu bỏ annotation cho trường có tên không trùng LDAP attribute, đừng kỳ vọng ODM tự hiểu quy ước nghiệp vụ của ứng dụng.

### 6.5. DN thay đổi sau rename/move

Khi một entry được rename hoặc move từ:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

sang:

~~~text
uid=lan,ou=alumni,dc=example,dc=org
~~~

thì DN cũ không còn trỏ tới entry đó. Object được đọc trước khi di chuyển có thể giữ `dn` cũ; không dùng nó làm bằng chứng vị trí hiện tại. Sau thao tác thành công, đọc lại theo DN mới hoặc điều chỉnh model theo API/luồng nghiệp vụ đã thiết kế.

Các directory có thể cung cấp định danh ổn định hơn DN (như `entryUUID` hoặc `objectGUID` trên server tương ứng), nhưng không mặc định các attribute này luôn tồn tại hay tự được ODM ánh xạ.

## 7. Xử lý lỗi khi đọc bằng ODM

Dùng ODM vẫn là một thao tác LDAP. Phân loại lỗi ở tầng repository/service giúp tránh biến lỗi hạ tầng thành “không tìm thấy nhân viên”.

| Tình huống | Biểu hiện thường gặp | Hành động phù hợp |
| --- | --- | --- |
| DN không tồn tại | `NameNotFoundException` khi lookup theo DN, tùy API | Trả trạng thái Not Found sau khi xác minh base và parent |
| Search filter không khớp | `List<T>` rỗng từ `find(...)` | Xử lý kết quả rỗng theo hợp đồng nghiệp vụ |
| Thuộc tính thiếu hoặc bị ACL ẩn | Field Java có thể `null`/giá trị mặc định | Kiểm tra dữ liệu, mapping và ACL |
| ObjectClass/schema không phù hợp | Mapper không nhận dạng hoặc không ánh xạ như mong đợi | Xác minh `@Entry` và objectClass thực tế |
| Kiểu trường không tương thích | Lỗi chuyển đổi/mapping | Chỉnh type/converter theo LDAP syntax |
| Tài khoản bind thiếu quyền | Lỗi quyền/không thể đọc entry hoặc trường | Xem ACL và quyền truy cập, không coi như kết quả rỗng |
| DN/base không đúng | Lỗi tìm tên hoặc kết quả sai nhánh | Xem `ContextSource.base`, OU và cách dựng DN |
| LDAP không sẵn sàng, timeout, lỗi TLS | Ngoại lệ kết nối hoặc giao thức | Phân loại lỗi hạ tầng và xác minh cấu hình bảo mật |

Không nên viết:

~~~java
// Sai: lỗi quyền, kết nối và mapper đều bị coi là "không có dữ liệu".
try {
    return ldapTemplate.findByDn(dn, DirectoryPerson.class);
} catch (Exception ignored) {
    return null;
}
~~~

Một cách xử lý tốt hơn là bắt **đúng loại ngoại lệ được phép chuyển thành trạng thái nghiệp vụ**, còn các lỗi khác tiếp tục được đưa lên tầng xử lý lỗi có giám sát. Khi log, tránh ghi mật khẩu, thông tin cá nhân nhạy cảm, chuỗi kết nối có credentials hoặc toàn bộ LDAP attributes.

## 8. Quy trình thiết kế repository ODM an toàn

Đối với ứng dụng quản lý nhân sự đọc hồ sơ qua LDAP, một quy trình hợp lý gồm:

1. **Định nghĩa schema đích:** xác định objectClass, các attribute bắt buộc/được phép, kiểu dữ liệu và naming convention.
2. **Chọn mapping nhỏ, rõ ràng:** tạo `@Entry` và `@Attribute` cho những trường thực sự sử dụng, khai báo `@Id` phù hợp.
3. **Cấu hình `ContextSource`:** chọn LDAP URL, base DN, tài khoản đọc tối thiểu; bật LDAPS hoặc StartTLS và kiểm tra chứng chỉ.
4. **Chọn chiến lược truy vấn:** dùng `findByDn` khi có DN; dùng `find` với filter/nhánh tìm kiếm an toàn khi chỉ biết thuộc tính.
5. **Giới hạn dữ liệu trả về:** tránh query toàn subtree không cần thiết, cân nhắc giới hạn kết quả/phân trang nếu có dữ liệu lớn.
6. **Chuẩn hóa kết quả:** phân biệt một object, danh sách rỗng, thuộc tính `null` và lỗi LDAP.
7. **Map sang DTO đầu ra:** không tự trả nguyên object LDAP chứa DN và các attribute nhạy cảm ra API công khai.
8. **Kiểm thử trên server đúng chính sách:** xác minh schema, ACL, operational attributes, encoding và hành vi khi entry không tồn tại.

Không để DTO/ODM object tồn tại lâu rồi mặc định nó luôn phản ánh trạng thái mới của LDAP; đây là dữ liệu đọc tại một thời điểm. Nếu cần dữ liệu mới sau cập nhật, nên chủ động đọc lại.

## 9. Kiểm thử tích hợp đọc object bằng ODM

Chuẩn bị một LDAP test server với base `dc=example,dc=org`, OU `ou=people` và schema hỗ trợ `inetOrgPerson`. Khởi tạo dữ liệu trước từng ca để tránh kết quả phụ thuộc dữ liệu tồn dư.

| Ca thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Đọc một entry hợp lệ | Tạo `uid=lan,ou=people` với `cn`, `sn`, `mail` | `findByDn` trả `DirectoryPerson` có các field đúng |
| Tên field khác attribute | `cn=Lan Tran`, field Java tên `fullName` | `getFullName()` nhận `Lan Tran` |
| Đọc DN | Đọc object có `@Id Name dn` | DN được ánh xạ theo ngữ cảnh library/base phù hợp |
| Attribute tùy chọn bị thiếu | Không cung cấp `mail` | Object vẫn được đọc, field tùy chọn được xử lý an toàn |
| Attribute nhiều giá trị | Có hai số `telephoneNumber` | Đọc đủ tập giá trị, không dựa vào thứ tự |
| DN không tồn tại | Không tạo `uid=unknown` | Trạng thái vắng mặt được phân loại; không coi là lỗi mapper |
| Search filter không khớp | Search `uid=unknown` trên OU hợp lệ | `find(...)` trả danh sách rỗng |
| Search filter hợp lệ | Search `uid=lan` bằng builder | Lấy đúng object và không nối input trực tiếp vào filter |
| Thiếu quyền đọc | Bind bằng tài khoản không được đọc một số attribute | Thể hiện giới hạn ACL, không “bịa” giá trị |
| Sai objectClass | Đọc entry kiểu OU qua `DirectoryPerson` | Không giả định mapper phù hợp với mọi loại entry |
| Attribute có binary data | Đọc kiểu attribute nhị phân trên class phù hợp | Không ép binary thành String tùy tiện |
| Tải nhiều kết quả | Nhiều entry dưới OU | Xem giới hạn search, bộ nhớ và chính sách phân trang |
| Move entry | Đổi parent của Lan sau lần đọc đầu | Lookup DN mới đúng; object cũ không tự cập nhật DN |

Một kiểm thử mock chỉ khẳng định các phương thức Java được gọi; nó không xác nhận LDAP server trả dữ liệu theo schema, filter và quyền thật. Vì vậy cần ít nhất những ca tích hợp quan trọng chạy với server mà hệ thống hỗ trợ.

### Bài tập thực hành

Cho dữ liệu:

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Le
sn: Le
~~~

Hãy:

1. Tạo class ODM có `@Entry`, `@Id`, `@Attribute` để đọc `dn`, `uid`, `cn`, `sn`, `mail`; tên Java của `cn` phải là `fullName`.
2. Dựng DN để đọc An bằng `findByDn(...)`. Giải thích DN nào tương đối với base.
3. Dùng `LdapQueryBuilder` tìm Binh theo `uid` và giải thích vì sao kết quả là một danh sách.
4. Kiểm tra `email` của Binh khi entry không có `mail`; phân biệt với trường hợp không tìm thấy cả entry.
5. Thêm hai giá trị `telephoneNumber` cho An và đọc đủ các giá trị mà không phụ thuộc thứ tự.
6. Giả sử `uid=an` được chuyển sang `ou=alumni`. Điều gì xảy ra nếu repository tiếp tục gọi `findByDn` bằng DN cũ?
7. Cho một tài khoản bind chỉ đọc được `cn`, `sn`. Bạn cần thay đổi kiểm thử/mapping thế nào để kết quả đúng và không lộ dữ liệu ngoài quyền?

## 10. Ghi nhớ

**Spring LDAP ODM** chuyển LDAP entry thành object Java thông qua annotation mapping. Với một DN đã biết, sử dụng `LdapTemplate.findByDn(dn, DirectoryPerson.class)`; khi cần tìm kiếm bằng attribute, dùng `LdapTemplate.find(query, DirectoryPerson.class)` và một LDAP filter được dựng an toàn.

`@Entry` mô tả loại entry, `@Id` biểu diễn DN, còn `@Attribute` nối tên LDAP attribute với field Java. ODM giúp giảm mã ánh xạ thủ công, nhưng **không bỏ qua** yêu cầu schema, base DN, ACL, giới hạn kết nối hoặc quy tắc nhiều giá trị của LDAP. Kết quả đọc cần được kiểm tra, phân loại lỗi và ánh xạ thành dữ liệu nghiệp vụ phù hợp trước khi sử dụng.

## Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): phần Object-Directory Mapping, `LdapTemplate` và cấu hình `ContextSource`.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): các thao tác tìm kiếm và ánh xạ object.
- [Spring LDAP — Entry annotation](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Entry.html): thông tin `@Entry` và objectClass.
- [Spring LDAP — Attribute annotation](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/odm/annotations/Attribute.html): định nghĩa cách gắn field Java với LDAP attribute.
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html): tạo base và filter cho truy vấn.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): schema, objectClass và cấu trúc entry.
