# Phân biệt thuộc tính vắng mặt với giá trị rỗng trong bộ lọc LDAP

Một màn hình quản trị cần liệt kê nhân viên **chưa có email** trong LDAP. Lập trình viên viết bộ lọc `(mail=)` vì quen với cách so sánh chuỗi rỗng trong Java hoặc SQL. Truy vấn không trả kết quả như mong đợi, dù directory thực sự có nhiều entry chưa khai báo `mail`.

Vấn đề nằm ở một khác biệt cơ bản: **thuộc tính LDAP vắng mặt** và **thuộc tính có giá trị chuỗi rỗng** không phải cùng một trạng thái. Trong ngôn ngữ LDAP filter, `(mail=*)` hỏi “entry có thuộc tính `mail` hay không”, `(!(mail=*))` hỏi điều ngược lại, còn `(mail=)` là một *equality assertion* với giá trị dài **0 ký tự**. Khả năng lưu và so khớp một giá trị như vậy còn phụ thuộc syntax, matching rule và LDAP server.

Bài thuộc chương **Bộ lọc** của module `SPRING_DATA_LDAP`: Java truy cập directory qua Spring Data LDAP repository và `LdapTemplate`, ánh xạ entry theo DN, `objectClass` và schema, thực hiện CRUD, filter an toàn, kết nối bảo mật và kiểm thử với directory. Mục tiêu là hiểu đúng sự khác biệt ở ba tầng: **dữ liệu thực trên LDAP**, **biểu thức filter được server đánh giá** và **giá trị `null`/`""`/chuỗi trắng trong ứng dụng Java**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích nghĩa của `(mail=*)`, `(!(mail=*))`, `(mail=)` và `(mail= )` mà không đánh đồng chúng.
- Hiểu sự khác nhau giữa **LDAP attribute không tồn tại trong entry**, **giá trị dài 0** và **giá trị chỉ gồm khoảng trắng**.
- Biết vì sao schema `Directory String` không cho phép chuỗi độ dài 0, trong khi các cú pháp khác có thể có quy tắc khác.
- Dùng `LdapQueryBuilder.where("mail").isPresent()` và filter phủ định trong `LdapTemplate.search(...)` để truy vấn chính xác.
- Phân biệt thuộc tính **không được trả về trong SearchResult** với thuộc tính **không tồn tại trên server**.
- Kiểm tra `javax.naming.directory.Attributes` và `Attribute` an toàn, tránh gọi `get()` trên giá trị `null` hoặc collection rỗng.
- Thiết kế thao tác xóa thuộc tính tùy chọn bằng LDAP Modify, không xem việc ghi `""` là cách xóa mặc định.
- Tạo unit test và integration test kiểm tra presence, absence, attribute projection, ACL và filter encoding.
- Tránh LDAP injection khi dữ liệu tìm kiếm đến từ request của người dùng.

## 2. Phân biệt ba trạng thái trước khi viết filter

Hãy xét ba hồ sơ nhân viên giả định:

```text
Entry Lan:
  uid: lan
  mail: lan@example.org

Entry Minh:
  uid: minh
  (không có thuộc tính mail)

Entry Hoa:
  uid: hoa
  mail: hoa@example.org
```

Từ góc nhìn directory:

| Trạng thái | Diễn giải | Ví dụ |
|---|---|---|
| **Present** | Entry có attribute `mail` với ít nhất một giá trị được lưu | `mail: lan@example.org` |
| **Absent** | Entry **không có** attribute `mail` | Hồ sơ Minh |
| **Empty value** | Attribute được lưu với giá trị chuỗi độ dài 0, nếu schema/server cho phép | `mail:` trong ý nghĩa giá trị LDIF dài 0, **không giả định server chấp nhận** |

Còn “chỉ có khoảng trắng” là một trường hợp **giá trị không rỗng** về mặt ký tự:

```text
""
→ Độ dài Java: 0

"   "
→ Độ dài Java: 3

"lan@example.org"
→ Độ dài Java: 15
```

Một thuộc tính có giá trị `"   "` không giống thuộc tính vắng mặt, cũng không giống giá trị `""`. Nhưng LDAP matching rule có thể áp dụng chuẩn hóa khoảng trắng; **không nên kết luận cách so khớp chỉ từ độ dài Java** mà chưa xem schema.

### 2.1. Thuộc tính LDAP không phải cột SQL

Với SQL, người học có thể quen:

```sql
mail IS NULL
mail = ''
```

LDAP không có toán tử filter `IS NULL` tương đương trực tiếp. Một attribute tùy chọn có thể **không tồn tại** trên entry, và phép **presence** là cấu trúc riêng trong LDAP filter. Vì vậy:

- SQL `IS NULL` không được dịch máy móc thành `(mail=)`.
- Một chuỗi rỗng trong biểu mẫu HTML/JSON không tự chứng minh server có thuộc tính với giá trị rỗng.
- Trong LDAP, truy vấn “không có attribute `mail`” thường cần `(!(mail=*))`.

## 3. LDAP filter: presence khác equality

RFC 4515 mô tả cú pháp chuỗi LDAP search filter, còn RFC 4511 định nghĩa các dạng filter và cách directory đánh giá.

| Filter | Loại filter | Ý nghĩa |
|---|---|---|
| `(mail=*)` | **Presence** | Thuộc tính `mail` có mặt trong entry. |
| `(!(mail=*))` | **NOT presence** | Thuộc tính `mail` không có mặt, theo kết quả đánh giá của directory. |
| `(mail=)` | **Equality** | Giá trị `mail` so khớp với assertion value **rỗng**, nếu hợp lệ và so khớp được. |
| `(mail= )` | **Equality** | Assertion value chứa **một ký tự khoảng trắng**. |
| `(mail=lan@example.org)` | **Equality** | So khớp `mail` với email cụ thể. |
| `(mail=lan*)` | **Substring** | `mail` bắt đầu bằng `lan` theo matching rule tương ứng. |
| `(mail=\2a)` | **Equality** | Tìm giá trị chứa dấu `*` theo biểu diễn escaped, không phải presence. |

Đặc biệt:

```text
(mail=*)    ≠   (mail=)    ≠   (!(mail=*))
```

**Vì sao có thể dễ nhầm?** Cả `*` và chuỗi rỗng đều được viết gần dấu `=`, nhưng `*` trong `(mail=*)` là **ký hiệu filter presence**, không phải một chuỗi Java và không phải yêu cầu “email có nội dung bất kỳ nhưng phải khác rỗng”.

### 3.1. Khi mail vắng mặt

Nếu một entry không có `mail`:

- `(mail=*)` thường đánh giá **FALSE**.
- `(!(mail=*))` thường đánh giá **TRUE**.
- `(mail=)` không tự trở thành phép “is missing”; nó vẫn là phép so khớp equality với assertion value độ dài 0.

LDAP không dùng cách `null == ""`. Muốn lọc theo absence, dùng filter hiện diện được phủ định.

### 3.2. Khi mail có giá trị rỗng thật

Nếu server thực sự lưu được một `mail` với giá trị độ dài 0 theo schema/matching rule của nó:

- Attribute **vẫn có mặt**, nên `(mail=*)` là dạng filter dùng để kiểm tra sự hiện diện.
- `(!(mail=*))` không có nghĩa “giá trị rỗng”; nó kiểm tra **không có attribute**.
- `(mail=)` chỉ có thể khớp nếu server chấp nhận phép so sánh assertion value rỗng và matching rule của attribute xác định kết quả phù hợp.

**Không nên hứa rằng `(mail=)` chắc chắn tìm ra một entry có giá trị rỗng trên mọi directory.** Khả năng chứa giá trị rỗng, cách đánh giá filter và kết quả lỗi phụ thuộc kiểu dữ liệu LDAP và triển khai server.

### 3.3. Phủ định filter không phải phép suy luận “người dùng đã xác nhận không có email”

Filter `(!(mail=*))` đánh giá trạng thái thuộc tính trên những entry mà server xét trong search base/scope, với ACL và cơ chế ba giá trị logic LDAP. Nó **không** chứng minh một nhân viên ngoài đời không có địa chỉ email.

Có thể entry chưa được đồng bộ, server đang đọc replica cũ, account không có quyền xem, hoặc ứng dụng chọn nhầm nhánh LDAP. Kết quả filter là sự thật **trong phạm vi đánh giá của directory**, không phải kết luận nghiệp vụ toàn cục.

## 4. Tại sao (mail=) có thể hợp cú pháp nhưng không khớp?

RFC 4515 cho phép *assertion value* có độ dài 0 trong **biểu diễn chuỗi** của filter. Vì vậy `(mail=)` không phải tự động là một filter sai cú pháp.

Nhưng có hai bước khác nhau:

1. **Parse filter:** cú pháp của `(mail=)` biểu diễn một equality assertion rỗng.
2. **Evaluate filter:** server sử dụng attribute type, syntax và equality matching rule để đánh giá assertion đó.

Việc cú pháp filter cho phép một assertion rỗng **không có nghĩa mọi LDAP attribute đều được lưu hoặc so khớp với giá trị rỗng**.

### 4.1. Schema quyết định giá trị nào hợp lệ

RFC 4517 phân biệt các kiểu dữ liệu string. Ví dụ:

| LDAP syntax | Quy tắc về độ dài 0 trong RFC 4517 | Ghi chú |
|---|---|---|
| **Directory String** | **Không cho phép** chuỗi 0 ký tự | Giá trị phải có từ một ký tự trở lên. |
| **IA5 String** | Có thể có 0, 1 hoặc nhiều ký tự IA5 | Việc server chấp nhận và matching rule vẫn phụ thuộc attribute/schema/policy. |
| Các syntax khác | Có quy định riêng | Không áp quy tắc của Java `String` cho mọi attribute. |

Trong schema RFC 4519, thuộc tính `mail` sử dụng **IA5 String** cùng các quy tắc so khớp thích hợp. Điều đó giải thích vì sao không nên tuyên bố “LDAP tuyệt đối cấm mọi giá trị rỗng” hay “mọi LDAP server chắc chắn cho lưu mail rỗng”. Quy tắc hiệu lực phải được kiểm tra trên **schema và server cụ thể**.

Với `cn`, `sn` hoặc một attribute dùng Directory String, giá trị rỗng không hợp lệ theo syntax chuẩn. Một entry có `objectClass=person` còn có các required attributes như `cn` và `sn`, vì vậy không thể xóa chúng tùy tiện.

### 4.2. Matching rule cũng quan trọng

Các rule như `caseIgnoreMatch`, `caseIgnoreIA5Match` hoặc rule riêng của server quyết định cách chuẩn hóa và so sánh giá trị. Chúng có thể xử lý hoa/thường và khoảng trắng khác với `String.equals(...)` của Java.

Vì vậy, bốn câu hỏi phải tách biệt:

- Filter `(mail=)` có parse được không?
- Attribute `mail` có thể lưu chuỗi dài 0 không?
- Equality matching rule có chấp nhận assertion value rỗng không?
- Dữ liệu trên server có thực sự chứa giá trị tương ứng không?

Một kết quả search rỗng **không tự trả lời cả bốn câu hỏi**.

## 5. LDAP dùng logic TRUE, FALSE và Undefined

RFC 4511 yêu cầu LDAP filter được đánh giá theo **logic ba giá trị**:

```text
TRUE       → Entry có thể được trả về, tùy ACL và các điều kiện khác.
FALSE      → Entry không khớp.
Undefined  → Entry không được coi là khớp.
```

Ví dụ với phép phủ định:

| Kết quả của `(mail=*)` | Kết quả `(!(mail=*))` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| Undefined | Undefined |

`Undefined` có thể xuất hiện khi server không xác định được kết quả theo một số điều kiện về schema, matching rule hoặc quyền. Vì vậy, đừng diễn giải `NOT` theo cách Boolean hai giá trị của Java rồi khẳng định mọi entry không khớp presence sẽ đều xuất hiện trong kết quả phủ định.

### 5.1. Kết quả filter là kết quả trên server

Với filter:

```text
(&(objectClass=inetOrgPerson)(!(mail=*)))
```

LDAP server tìm trong vùng cây được yêu cầu các entry:

1. Có object class phù hợp.
2. Thỏa điều kiện phủ định presence `mail`.
3. Được phép xuất hiện trong kết quả theo quy định server/ACL.

Không có cơ chế ngầm để client lấy toàn bộ nhân viên rồi chạy `person.getMail() == null`. Bộ lọc được **directory đánh giá** trước khi `LdapTemplate` nhận danh sách kết quả.

## 6. Fixture LDAP để kiểm chứng presence và absence

Tạo một directory kiểm thử riêng với ba người:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
sn: Tran

dn: uid=hoa,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: hoa
cn: Hoa Le
sn: Le
mail: hoa@example.org
```

Lưu ý **entry Minh không có dòng `mail`**. Không thay nó bằng dòng:

```ldif
mail:
```

và tự giả định tương đương. Trong LDIF, dòng có dấu `:` nhưng không có giá trị có thể biểu diễn dữ liệu độ dài 0; server có thể chấp nhận hoặc từ chối theo schema. Mục tiêu test presence/absence là tạo **thuộc tính thật sự vắng mặt**, nên cách chắc chắn nhất là **không đưa attribute đó vào entry**.

Dữ liệu dự kiến:

| UID | Mail trong entry | `(mail=*)` | `(!(mail=*))` |
|---|---|---|---|
| `lan` | `lan@example.org` | Khớp | Không khớp |
| `minh` | Không có attribute | Không khớp | Khớp |
| `hoa` | `hoa@example.org` | Khớp | Không khớp |

Bảng này giả định search thực hiện trên server thử nghiệm có schema/ACL phù hợp và tất cả entry nằm trong phạm vi query. Kết quả **`(mail=)` không được đưa vào bảng như một phép kiểm tra absence**.

## 7. Base DN và search scope vẫn ảnh hưởng đến kết quả

Ngay cả filter đúng, search cũng có thể trả thiếu nếu phạm vi cây không bao gồm entry.

Giả sử Spring Boot cấu hình:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
```

Với `ContextSource` base `dc=example,dc=org`, search base `ou=people` trỏ tới:

```text
ou=people,dc=example,dc=org
```

Nếu ứng dụng vô tình search dưới `ou=groups`, nó không thấy Lan/Minh/Hoa dù filter có chính xác. Nếu chỉ dùng scope `ONELEVEL`, search sẽ không đi vào các nhánh con sâu hơn của `ou=people`. `SUBTREE` bao gồm base và các cấp con.

Công thức khái niệm:

```text
Kết quả =
  entry nằm trong base + scope
  AND filter đánh giá TRUE
  AND server/ACL cho phép trả entry
```

**Phân biệt “không có thuộc tính” với “entry không nằm trong vùng tìm kiếm”.** Một truy vấn rỗng chưa chứng minh absence hay existence của email trên toàn directory.

## 8. Dùng LdapQueryBuilder để tìm thuộc tính hiện diện

Spring LDAP cung cấp `LdapQueryBuilder` với method `isPresent()`. Ví dụ tìm người **có thuộc tính `mail`**:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PersonFilterService {

    private final LdapTemplate ldapTemplate;

    public PersonFilterService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> peopleHavingMailAttribute() {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid")
            .where("objectClass").is("inetOrgPerson")
            .and("mail").isPresent();

        return ldapTemplate.search(
            q,
            (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
        );
    }
}
```

Trong đoạn code:

1. `base("ou=people")` chọn nhánh dữ liệu; với `spring.ldap.base` ở trên, đây là DN tương đối.
2. `SUBTREE` tìm trong toàn bộ cây con.
3. `where("objectClass").is("inetOrgPerson")` chỉ lấy entry người đúng schema.
4. `and("mail").isPresent()` yêu cầu attribute `mail` **có mặt**.
5. `attributes("uid")` chỉ yêu cầu trả `uid` vì mapper không cần đọc mail.

Kết quả dự kiến từ fixture là `["lan", "hoa"]`, không phụ thuộc thứ tự trả về. Hai người này được chọn **do filter ở server**, không phải do Java kiểm tra `mail` sau khi nhận dữ liệu.

**Điểm cực kỳ quan trọng:** mapper ở trên có thể không thấy `attrs.get("mail")`, vì chính query đã yêu cầu **chỉ trả `uid`**. Dù server lọc bằng `mail`, thuộc tính `mail` không nhất thiết có mặt trong dữ liệu kết quả của client.

## 9. Tìm entry không có attribute với NOT presence

Muốn tìm nhân viên **chưa có thuộc tính mail**:

```text
(&(objectClass=inetOrgPerson)(!(mail=*)))
```

Trong `LdapQueryBuilder` có thể dùng một filter **cố định**, không chứa dữ liệu người dùng:

```java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class MissingMailService {

    private final LdapTemplate ldapTemplate;

    public MissingMailService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> peopleWithoutMailAttribute() {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid")
            .filter("(&(objectClass=inetOrgPerson)(!(mail=*)))");

        return ldapTemplate.search(
            q,
            (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
        );
    }
}
```

Trên fixture, kết quả là `["minh"]`.

### 9.1. Không trộn hai kiểu xây filter trên cùng builder

`LdapQueryBuilder` hỗ trợ hai cách chọn điều kiện:

- Điều kiện cấu trúc: `where(...).is(...)`, `and(...).isPresent()`.
- Filter tường minh: `filter(String)` hoặc `filter(String, Object...)`.

Không trộn `filter(...)` với `where(...)` trên cùng query builder sau khi đã đặt một trong hai dạng; API sẽ từ chối cấu hình không hợp lệ. Với biểu thức cố định trên, `filter("(&(objectClass=inetOrgPerson)(!(mail=*)))")` là phù hợp.

Cũng có thể biểu diễn phủ định bằng API condition của Spring LDAP, chẳng hạn `where("mail").not().isPresent()` tùy phiên bản; hãy kiểm tra API phù hợp và **test filter cuối cùng** thay vì ghép chuỗi tùy tiện.

### 9.2. Nếu muốn kiểm tra một attribute khác

Chỉ cần thay tên attribute **cố định** trong filter:

```text
(!(telephoneNumber=*))
(!(description=*))
(!(employeeNumber=*))
```

Nhưng attribute đó phải được schema hỗ trợ, và query phải tìm đúng vùng entry. Với các thuộc tính bắt buộc như `cn`/`sn` của `person`, việc tìm entry thiếu thuộc tính có thể là bài kiểm tra chất lượng dữ liệu hoặc schema không đúng, không phải một tình huống bình thường như `mail` tùy chọn.

## 10. Vì sao (mail=) không thay thế isPresent() hay NOT presence?

Giả sử người dùng nhập ô email trống và ứng dụng tạo query:

```java
String input = "";
LdapQuery q = query()
    .base("ou=people")
    .where("mail").is(input);
```

`where("mail").is(input)` diễn đạt **equality**. Khi `input=""`, nó không biến thành `where("mail").not().isPresent()`.

Nếu ứng dụng thực sự muốn “lọc hồ sơ chưa khai báo email”, phải **chọn filter presence/absence theo ý định nghiệp vụ**, không lấy tình trạng input rỗng làm một điều kiện equality.

Một controller tìm kiếm có thể phân biệt:

| Trạng thái request | Ý định có thể thiết kế | Filter |
|---|---|---|
| Không truyền tiêu chí email | Không áp dụng điều kiện theo email | Chỉ dùng các điều kiện khác. |
| `mailStatus=PRESENT` | Tìm entry có thuộc tính email | `(mail=*)` |
| `mailStatus=ABSENT` | Tìm entry thiếu thuộc tính email | `(!(mail=*))` |
| `mail=lan@example.org` | Tìm email cụ thể | Equality với giá trị đã encode. |
| `mail=""` | Input rỗng chưa rõ ý định | Validate/định nghĩa API rõ ràng; không tự dịch thành absence. |

Không dùng `(mail=)` làm cách “tìm email null” chỉ vì thấy giống `mail = ''` trong SQL. Một biểu thức equality rỗng còn có thể không khớp gì hoặc gặp vấn đề so khớp tùy directory.

## 11. Java null, empty và blank không tự phản ánh trạng thái LDAP

Ở tầng Java:

```java
String absentInObject = null;
String emptyText = "";
String spaces = "   ";

System.out.println(emptyText.isEmpty()); // true
System.out.println(spaces.isEmpty());    // false
System.out.println(spaces.isBlank());    // true
```

Các phép kiểm tra này nói về **giá trị Java**, không phải trực tiếp về entry đang lưu trên LDAP.

| Kiểm tra Java | Nó cho biết điều gì? | Điều nó không chứng minh |
|---|---|---|
| `value == null` | Field Java chưa có giá trị. | LDAP server thật sự không có attribute. |
| `value.isEmpty()` | Chuỗi có 0 ký tự. | Attribute LDAP vắng mặt. |
| `value.isBlank()` | Chuỗi không có ký tự ngoài whitespace. | Matching rule LDAP coi giá trị là rỗng. |
| `attrs.get("mail") == null` | Thuộc tính không được cung cấp trong `Attributes` nhận về. | Directory không lưu `mail`. |
| `attribute.size() == 0` | JNDI `Attribute` object hiện có 0 value. | Server đã lưu một attribute rỗng hợp lệ. |
| `list.isEmpty()` sau search | Không có entry nào được trả về cho query. | Không có người hoặc không có email trong toàn directory. |

### 11.1. Vì sao attrs.get("mail") có thể null dù mail tồn tại?

Có ít nhất ba lý do:

1. **Projection:** query chỉ yêu cầu `uid` và `cn`, không yêu cầu `mail`.
2. **ACL:** service account có thể không được đọc thuộc tính `mail`.
3. **Thực sự vắng mặt:** entry không có `mail` trên server.

Một trường hợp nữa là kết quả từ cache/mapping đã qua xử lý hoặc replica có dữ liệu khác. Vì vậy, `attrs.get("mail")==null` không đủ để suy ra **absence thực tế**.

### 11.2. Không nhầm SearchResult với kết quả lọc

LDAP server có thể dùng `mail` để **đánh giá filter** nhưng vẫn không trả giá trị `mail` cho client vì client không yêu cầu attribute đó.

```text
Filter:             (mail=*)
Requested attrs:    uid, cn

Server may return:
  uid=lan
  cn=Lan Nguyen

Mapper:
  attrs.get("mail") == null
```

Đây không phải mâu thuẫn. **Điều kiện lọc** và **danh sách thuộc tính được trả về** là hai phần khác nhau của LDAP SearchRequest.

## 12. Đọc JNDI Attributes an toàn

Thay vì gọi `attrs.get("mail").get().toString()` ngay lập tức, hãy kiểm tra object và số giá trị. Với attribute có nhiều giá trị, không nên mặc định chỉ tồn tại một value.

Ví dụ một mapper giữ lại thông tin quan sát được từ kết quả:

```java
import java.util.ArrayList;
import java.util.List;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import org.springframework.ldap.core.AttributesMapper;

record MailObservation(
    String uid,
    boolean attributeReturned,
    List<String> values
) {
    public boolean hasReturnedValue() {
        return attributeReturned && !values.isEmpty();
    }
}

public class MailObservationMapper
        implements AttributesMapper<MailObservation> {

    @Override
    public MailObservation mapFromAttributes(Attributes attrs)
            throws NamingException {

        Attribute uidAttr = attrs.get("uid");
        String uid = uidAttr == null
            ? null
            : uidAttr.get().toString();

        Attribute mailAttr = attrs.get("mail");
        if (mailAttr == null) {
            return new MailObservation(uid, false, List.of());
        }

        List<String> values = new ArrayList<>();
        NamingEnumeration<?> it = mailAttr.getAll();
        try {
            while (it.hasMore()) {
                Object item = it.next();
                values.add(String.valueOf(item));
            }
        } finally {
            it.close();
        }

        return new MailObservation(
            uid, true, List.copyOf(values)
        );
    }
}
```

Điểm quan trọng:

- `attributeReturned=false` chỉ có nghĩa `mail` **không xuất hiện trong kết quả JNDI**, không kết luận nguyên nhân.
- `values.isEmpty()` có thể xảy ra với một `BasicAttribute` trống trong memory hoặc dữ liệu đặc biệt; **đừng giả định LDAP server lưu giá trị 0 ký tự** từ đó.
- `List<String>` trong ví dụ phù hợp với attribute email có dạng string. Với attribute nhị phân, phải xử lý `byte[]` đúng cách, không dùng `String.valueOf(...)` như một decoder.
- Giá trị chuỗi `""` khác với `List.of()`: danh sách có thể chứa **một phần tử rỗng** nếu nguồn dữ liệu cho phép.
- Mapper cần kiểm soát lỗi khi `uid` cũng không được trả về, ví dụ thiếu projection/ACL.

### 12.1. Gọi LdapTemplate với attributes rõ ràng

```java
import java.util.List;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class MailInspectionService {

    private final LdapTemplate ldap;

    public MailInspectionService(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<MailObservation> inspectPeople() {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid", "mail")
            .where("objectClass").is("inetOrgPerson");

        return ldap.search(q, new MailObservationMapper());
    }
}
```

Ngay cả khi request có `attributes("uid","mail")`, ACL có thể không cho phép xem một hoặc cả hai attribute. Nên coi dữ liệu **không được trả về** là “chưa biết lý do” nếu yêu cầu nghiệp vụ cần chứng minh trạng thái trên server.

## 13. ODM entity: @Attribute mail có null nghĩa là gì?

Spring Data LDAP repository có thể ánh xạ entry thành entity Java:

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
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String mail;

    // Constructor không tham số và getter/setter được lược bớt.
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
```

Nếu entity trả về có `person.getMail()==null`, chưa thể chứng minh chắc chắn attribute không tồn tại trên directory. Query repository, chính sách attribute loading, ACL hoặc mapper có thể tác động giá trị Java.

**Hệ quả khi cập nhật:**

- Không nên đọc một entity thiếu `mail` do ACL/projection rồi lưu lại, mặc định tin rằng nó đúng là “không có mail”.
- Không dùng `getMail().isEmpty()` khi `getMail()` có thể `null`.
- Không dùng Java `null` và `""` làm hai “chế độ LDAP” nếu service chưa quy định ý nghĩa của chúng.
- Nếu muốn kiểm tra **trạng thái vắng mặt trên server**, hãy dùng filter presence/absence có base/ACL phù hợp và/hoặc lookup theo DN với account có quyền kiểm tra.

### 13.1. Tại sao repository derived query cần được kiểm chứng?

Có thể Spring Data LDAP hỗ trợ các phương thức query dựa trên tên property, nhưng không nên suy từ cú pháp của JPA/SQL như `findByMailIsNull` rằng LDAP chắc chắn thực hiện cùng ngữ nghĩa. Nếu nghiệp vụ đòi phân biệt presence và absence chuẩn xác, ưu tiên **`LdapQueryBuilder` / `LdapTemplate`** hoặc annotation query LDAP được kiểm chứng rõ, kèm integration test thực.

## 14. Xóa thuộc tính khác với ghi chuỗi rỗng

Giả sử nghiệp vụ yêu cầu **xóa email khỏi hồ sơ Minh hoặc Lan**. Nếu `mail` là attribute **tùy chọn** và server cho phép xóa theo ACL/schema, hãy gửi một LDAP Modify phù hợp thay vì lưu chuỗi rỗng rồi hy vọng server tự diễn giải thành “không có”.

Ví dụ xóa **toàn bộ attribute `mail`** của một entry:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.LdapTemplate;

public class PersonMailWriter {

    private final LdapTemplate ldap;

    public PersonMailWriter(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public void removeMailAttribute(Name personRelativeDn) {
        ModificationItem remove = new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("mail")
        );

        ldap.modifyAttributes(
            personRelativeDn,
            new ModificationItem[] { remove }
        );
    }
}
```

**Chú ý semantics của LDAP Modify:**

- `REMOVE_ATTRIBUTE` với `BasicAttribute("mail")` **không có value cụ thể** yêu cầu xóa **toàn bộ attribute**.
- `REMOVE_ATTRIBUTE` với `BasicAttribute("member", someDn)` xóa **một giá trị** cụ thể của thuộc tính đa trị `member` (khi tồn tại), không xóa các giá trị khác.
- `REPLACE_ATTRIBUTE` với giá trị `""` là một hành động khác: nó yêu cầu đặt một giá trị rỗng; server có thể từ chối vì syntax/schema.
- Nếu `mail` đã vắng mặt, yêu cầu delete có thể trả LDAP result code `16 – noSuchAttribute`. Một API “ensure absent” có thể có chính sách riêng, nhưng không được nuốt mọi lỗi và coi thành công.
- Nếu attribute bắt buộc theo schema, xóa attribute có thể bị từ chối với `65 – objectClassViolation`.

### 14.1. Không dùng null trong DTO làm quyết định xóa tự động

API PATCH có ba trường hợp cần phân biệt:

```json
{}
```

```json
{"mail": null}
```

```json
{"mail": ""}
```

Đây là **ba payload khác nhau**:

| Request | Một hợp đồng API có thể chọn | Thao tác LDAP nếu lựa chọn được xác nhận |
|---|---|---|
| Không có key `mail` | Không thay đổi email | Không gửi LDAP Modify cho `mail`. |
| Key `mail` có `null` | Yêu cầu xóa thuộc tính mail | `REMOVE_ATTRIBUTE` không kèm value, khi hợp lệ. |
| Key `mail` có `""` | Từ chối vì email không hợp lệ, hoặc quy ước xóa **nếu API nói rõ** | Không tự suy đoán. |
| Key `mail` có giá trị hợp lệ | Đặt email mới | `REPLACE_ATTRIBUTE` với giá trị đã validate. |

Việc chọn ý nghĩa của `null` là **thiết kế API**, không phải quy tắc phổ quát của JSON/PATCH. Nếu dùng Java DTO chỉ có `String mail`, bạn có thể đánh mất thông tin “key không có” so với “key có null”. Cần kiểu trạng thái/kiểm tra field hiện diện để giữ được ba tình huống.

### 14.2. Một ví dụ xử lý request với Jackson JsonNode

Trong ứng dụng Spring Boot có Jackson, handler có thể tách semantics trước khi gọi repository/`LdapTemplate`:

```java
import com.fasterxml.jackson.databind.JsonNode;

public class MailPatchInterpreter {

    public enum Action { NO_CHANGE, REMOVE, SET }

    public record Decision(Action action, String newMail) {}

    public Decision interpret(JsonNode body) {
        if (!body.has("mail")) {
            return new Decision(Action.NO_CHANGE, null);
        }

        JsonNode mailNode = body.get("mail");
        if (mailNode.isNull()) {
            return new Decision(Action.REMOVE, null);
        }

        if (!mailNode.isTextual()) {
            throw new IllegalArgumentException(
                "mail must be a string or null"
            );
        }

        String value = mailNode.asText();
        if (value.isBlank()) {
            throw new IllegalArgumentException(
                "mail must not be blank"
            );
        }

        // Validation email thực tế nên chặt hơn ví dụ này.
        return new Decision(Action.SET, value);
    }
}
```

Đây là ví dụ **phân loại ý định**, không phải controller hoàn chỉnh và không thay thế validation email hoặc kiểm soát quyền. Tầng ghi sẽ chọn REMOVE/REPLACE tùy `Decision` và chỉ cho phép sửa DN đã được xác minh.

## 15. So sánh quan sát client và điều kiện server

Đôi lúc người học muốn tìm “entry không có mail” bằng cách load mọi `PersonEntry` rồi lọc Java:

```java
people.stream()
    .filter(p -> p.getMail() == null)
    .toList();
```

Cách này có thể phục vụ xử lý **dữ liệu Java đã load**, nhưng không tương đương filter LDAP `(!(mail=*))` vì:

1. `getMail()==null` có thể xuất phát từ projection/ACL/mapping, không nhất thiết là absence trên server.
2. `people` có thể đã bị giới hạn số entry hoặc không bao gồm toàn bộ search base.
3. Query LDAP có thể đánh giá filter bằng matching rule và chính sách quyền, khác xử lý Java.
4. Load toàn bộ rồi lọc client gây tốn băng thông/bộ nhớ nếu directory lớn.
5. Replica và cache có thể khiến Java quan sát dữ liệu khác thời điểm với server ghi.

Khi muốn tìm thuộc tính absent theo LDAP, dùng **server-side filter** và xác định phạm vi, quyền cũng như thông tin trả về rõ ràng.

## 16. Tìm kiếm an toàn: không ghép filter bằng chuỗi từ input

Một lỗi bảo mật đi kèm bài toán null/empty là nối trực tiếp giá trị tìm kiếm:

```java
// KHÔNG AN TOÀN nếu userInput đến từ request:
String unsafe = "(mail=" + userInput + ")";
```

Khi input chứa `*`, `(`, `)`, backslash hoặc byte null, chuỗi filter có thể thay đổi ý nghĩa hoặc sai cú pháp.

Ví dụ:

- Input `"*"` thành `(mail=*)`: **presence**, không phải equality với ký tự `*`.
- Input `"lan*"` thành `(mail=lan*)`: **substring**, không phải giá trị literal chứa dấu `*`.
- Input trống `""` thành `(mail=)`: **equality rỗng**, không phải absence.

### 16.1. Dùng query builder để truyền giá trị

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

LdapQuery exactMail = query()
    .base("ou=people")
    .where("mail").is(userInput);
```

Builder encode giá trị cho equality filter, bảo vệ những ký tự đặc biệt theo API. Nó **không** tự biến input trống thành điều kiện tìm attribute vắng mặt. Ứng dụng vẫn phải xác định trước input trống có được cho phép hay không.

### 16.2. Filter format với parameter binding

```java
LdapQuery q = query()
    .base("ou=people")
    .filter(
        "(&(objectClass=inetOrgPerson)(mail={0}))",
        userInput
    );
```

Các parameter được Spring LDAP encode đúng cho LDAP filter. Không thay `{0}` bằng phép nối chuỗi thủ công.

Còn filter absence:

```java
LdapQuery missing = query()
    .base("ou=people")
    .filter("(&(objectClass=inetOrgPerson)(!(mail=*)))");
```

là **filter tĩnh**, không nhận dữ liệu từ người dùng, nên có thể viết tường minh. Nên dùng enum/trạng thái server-side được allowlist khi client cần chọn `PRESENT` hoặc `ABSENT`, thay vì để client gửi raw LDAP filter.

### 16.3. Phân biệt filter escaping và DN escaping

Cú pháp LDAP filter theo RFC 4515 khác cú pháp DN theo RFC 4514. Nếu API nhận mã nhân viên để lookup, hãy dùng `LdapNameBuilder` tạo DN và query builder encode assertion value tương ứng; không thể dùng một hàm escape chung thay thế cả hai.

## 17. Bảng chẩn đoán khi tìm thuộc tính vắng mặt sai kết quả

| Triệu chứng | Khả năng nguyên nhân | Hướng điều tra |
|---|---|---|
| `(mail=)` không tìm ra Minh | Minh **không có** `mail`; filter đang là equality rỗng | Dùng `(!(mail=*))` cho absence. |
| `(mail=*)` trả Lan/Hoa nhưng mapper `attrs.get("mail")==null` | Chỉ yêu cầu trả `uid`/`cn` | Thêm `mail` vào attributes to return; xem ACL. |
| Query `(!(mail=*))` không trả người dự kiến | Sai base, scope hoặc điều kiện khác/ACL | Kiểm tra search base, objectClass, bộ lọc và quyền. |
| Ghi `mail:` vào LDIF bị từ chối | Schema hoặc server không chấp nhận giá trị rỗng | Dùng **absence thật** để test; không ép server nhận empty. |
| Java `mail.isEmpty()` báo NullPointerException | Field Java `mail=null` | Kiểm tra `null` trước; phân biệt chưa trả attr và vắng mặt. |
| Java `mail.isBlank()` trả true cho whitespace | Chuỗi có ký tự trắng, không phải 0 ký tự | Validate dữ liệu nghiệp vụ, kiểm tra matching rule LDAP. |
| PATCH trống làm mất email | DTO mất phân biệt key omitted và key null | Dùng explicit patch state trước khi gửi LDAP Modify. |
| Delete email trả `noSuchAttribute` | Attribute đã vắng hoặc yêu cầu xóa value không tồn tại | Chỉ coi “đã vắng” là đạt mục tiêu khi đúng hợp đồng. |
| Delete email trả `objectClassViolation` | Attribute bắt buộc theo schema | Không xóa; điều chỉnh nghiệp vụ/schema đúng quyền. |
| Không đọc được email dù tồn tại | ACL ẩn attribute hoặc client kết nối sai node | Đối chiếu danh tính bind, endpoint và attribute selection. |
| Search quá chậm | Base rộng, scope sâu, thiếu index, lọc client | Thu hẹp base/scope, dùng server-side filter và xem index. |

### 17.1. Những tín hiệu lỗi không nên đánh đồng

- `NameNotFoundException` / LDAP `32`: **DN/base không tồn tại**, không phải mail absent.
- `NoSuchAttributeException` / LDAP `16`: thao tác Modify/attribute không tìm thấy theo ngữ cảnh.
- `SchemaViolationException` / LDAP `65`: thao tác vi phạm schema.
- `NoPermissionException` / LDAP `50`: thiếu quyền.
- `CommunicationException` hoặc nguyên nhân TLS: request chưa chắc đã được server thực hiện.
- `AuthenticationException` / LDAP `49`: tài khoản bind bị từ chối.

Một search không có kết quả và một search ném exception là hai tình huống khác nhau; đừng trả “chưa có email” nếu hệ thống không kết nối LDAP được.

## 18. Kiểm thử unit: null và zero-length trong JNDI

Unit test của mapper nên bao phủ **thuộc tính không có trong `Attributes`** và **attribute object có zero value**. Test dưới dùng JUnit 5 và `BasicAttributes`; nó không chứng minh server sẽ lưu được giá trị rỗng.

```java
import static org.assertj.core.api.Assertions.assertThat;

import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.junit.jupiter.api.Test;

class MailObservationMapperTest {

    private final MailObservationMapper mapper =
        new MailObservationMapper();

    @Test
    void missingAttributeIsNotReturned() throws Exception {
        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "minh");

        MailObservation result =
            mapper.mapFromAttributes(attrs);

        assertThat(result.uid()).isEqualTo("minh");
        assertThat(result.attributeReturned()).isFalse();
        assertThat(result.values()).isEmpty();
    }

    @Test
    void emptyAttributeObjectIsDifferentFromMissingObject()
            throws Exception {

        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "test");
        attrs.put(new BasicAttribute("mail")); // Không có value.

        MailObservation result =
            mapper.mapFromAttributes(attrs);

        assertThat(result.attributeReturned()).isTrue();
        assertThat(result.values()).isEmpty();
    }

    @Test
    void emptyStringValueIsStillOneValueInJndiBuffer()
            throws Exception {

        BasicAttributes attrs = new BasicAttributes(true);
        attrs.put("uid", "test");
        attrs.put("mail", "");

        MailObservation result =
            mapper.mapFromAttributes(attrs);

        assertThat(result.attributeReturned()).isTrue();
        assertThat(result.values()).containsExactly("");
    }
}
```

**Ý nghĩa của ba test:**

1. `attrs.get("mail") == null`: không có attribute object trong dữ liệu nhận về.
2. `new BasicAttribute("mail")`: attribute object tồn tại trong Java nhưng có **0 giá trị**.
3. `attrs.put("mail", "")`: attribute object có **1 giá trị dài 0**.

Đây là ba cấu trúc dữ liệu **JNDI trong bộ nhớ**, không phải ba trạng thái chắc chắn tồn tại được trên directory LDAP. Muốn biết server chấp nhận gì, cần integration test với schema và LDAP server thật.

## 19. Kiểm thử tích hợp: search presence/absence trên directory

### 19.1. Chuẩn bị

Chạy LDAP server riêng (embedded/container), nạp fixture ở mục 6, kết nối bằng tài khoản test có quyền đọc các entry và `mail` dưới `ou=people`. Trong Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-ldap</artifactId>
</dependency>
```

Profile `ldap-test` phải trỏ tới đúng directory thử nghiệm. Không dùng directory production để tự ý tạo/sửa giá trị rỗng hoặc thử ACL.

### 19.2. Integration test lọc hai tập khác nhau

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;
import org.springframework.test.context.ActiveProfiles;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@SpringBootTest
@ActiveProfiles("ldap-test")
class MailPresenceIntegrationTest {

    @Autowired
    private LdapTemplate ldap;

    private List<String> uids(LdapQuery q) {
        return ldap.search(
            q,
            (AttributesMapper<String>) attrs ->
                attrs.get("uid").get().toString()
        );
    }

    @Test
    void presentFilterFindsOnlyPeopleWithMail() {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid")
            .where("objectClass").is("inetOrgPerson")
            .and("mail").isPresent();

        assertThat(uids(q))
            .containsExactlyInAnyOrder("lan", "hoa");
    }

    @Test
    void notPresentFilterFindsOnlyPeopleWithoutMail() {
        LdapQuery q = query()
            .base("ou=people")
            .searchScope(SearchScope.SUBTREE)
            .attributes("uid")
            .filter("(&(objectClass=inetOrgPerson)(!(mail=*)))");

        assertThat(uids(q))
            .containsExactly("minh");
    }
}
```

Dùng `containsExactlyInAnyOrder` khi không có thứ tự được bảo đảm. Với test chỉ có một kết quả, `containsExactly` phù hợp. Các kết quả này chỉ đúng nếu fixture, schema, ACL, base DN và dữ liệu thực đã được kiểm soát.

### 19.3. Test projection: mail tồn tại nhưng không được trả về

Một test cần thiết khác xác minh **attribute projection**:

```java
@Test
void notRequestedAttributeDoesNotAppearInReturnedAttributes() {
    LdapQuery q = query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .attributes("uid") // Không yêu cầu mail.
        .where("uid").is("lan");

    List<Boolean> returnedMail = ldap.search(
        q,
        (AttributesMapper<Boolean>) attrs ->
            attrs.get("mail") != null
    );

    assertThat(returnedMail).containsExactly(false);
}
```

Ở đây filter chọn đúng Lan, directory lưu `mail`, nhưng mapper **không nhìn thấy `mail`** do projection. Đó là minh chứng trực tiếp rằng `attrs.get("mail")==null` không tương đương “attribute không tồn tại”.

Đặt test này vào cùng class integration, dùng bean `ldap` và import `AttributesMapper` đã có.

### 19.4. Test zero-length value phải tách riêng

Nếu bạn muốn thử nhập một giá trị rỗng thực sự:

1. Chọn attribute và syntax mà server mục tiêu **cho phép** giá trị 0 ký tự.
2. Tạo một entry test riêng và thử LDAP Add/Modify với value độ dài 0.
3. Nếu server từ chối, ghi nhận result code/schema, **không sửa fixture presence/absence để ép đạt**.
4. Nếu server chấp nhận, tìm `(attr=*)`, `(attr=)` và đọc lại giá trị để quan sát hành vi matching.
5. Kiểm tra cả ACL và cách client/JNDI biểu diễn kết quả; không giả định mọi server tương đương.

**Không gộp test zero-length với test absence cơ bản**, vì nó phụ thuộc đặc tính server và schema. Unit test Java ở mục 18 không thay thế bước này.

### 19.5. Test với ACL hạn chế

Dùng một service account chỉ đọc `uid` mà không được đọc `mail`, sau đó chạy:

- Search không yêu cầu mail và chỉ đọc `uid`.
- Search yêu cầu cả `uid` lẫn `mail`.
- Filter presence và NOT presence.

Ghi lại kết quả cụ thể trên server; phân biệt giữa **được match bởi filter**, **entry được trả**, **attribute được trả** và **lỗi quyền**. Không suy ra mọi directory áp dụng ACL giống nhau với filter presence.

## 20. Dùng ldapsearch để đối chiếu độc lập

Khi có công cụ `ldapsearch` trong môi trường kiểm thử, bạn có thể đối chiếu filter ngoài ứng dụng Java.

Ví dụ kết nối LDAPS tới server giả định:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=svc-reader,ou=service-accounts,dc=example,dc=org' \
  -W \
  -b 'ou=people,dc=example,dc=org' \
  -s sub \
  '(&(objectClass=inetOrgPerson)(mail=*))' \
  dn uid mail
```

Để tìm entry **không có mail**:

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=svc-reader,ou=service-accounts,dc=example,dc=org' \
  -W \
  -b 'ou=people,dc=example,dc=org' \
  -s sub \
  '(&(objectClass=inetOrgPerson)(!(mail=*)))' \
  dn uid
```

Tham số `-W` yêu cầu nhập mật khẩu tương tác, tránh đặt mật khẩu vào command history. Tên host/port/DN là **ví dụ**, không phải hệ thống thật.

Lưu ý:

- Client phải được cấu hình **trust CA và xác minh TLS server** đúng; không tắt certificate validation để chạy lệnh nhanh.
- Nếu CLI và Spring trả kết quả khác, đối chiếu **cùng endpoint, cùng bind identity, cùng base/scope/filter, cùng attribute selection và cùng thời điểm dữ liệu**.
- Nếu LDAP có replica, việc kết nối hai node khác nhau có thể cho kết quả khác do replication lag.
- Không dùng CLI để thay thế kiểm soát truy cập; người chạy test chỉ dùng account được cấp phép.

## 21. Những lỗi tư duy thường gặp

**“`(mail=)` nghĩa là mail không tồn tại.”** Sai. Đây là equality assertion có giá trị độ dài 0; muốn absence dùng `(!(mail=*))`.

**“`(mail=*)` chỉ tìm mail không rỗng.”** Chưa chính xác. Nó kiểm tra **presence**, không áp đặt một điều kiện `String.isEmpty()` ở Java. Có giá trị rỗng thực sự hợp lệ hay không còn phụ thuộc schema.

**“LDAP cấm mọi chuỗi rỗng.”** Sai khi nói cho mọi syntax. RFC 4517 cấm giá trị zero-length của Directory String nhưng mô tả IA5 String với quy tắc khác.

**“`attrs.get("mail")==null` chứng minh mail absent.”** Sai. Có thể query không yêu cầu mail hoặc ACL không cho trả.

**“Đọc entity có `mail=null` nghĩa là user chắc chắn chưa có email.”** Chưa đủ. Cần xác nhận nguồn, projection, ACL và trạng thái directory.

**“Một BasicAttribute không có value chứng minh LDAP lưu attribute rỗng.”** Sai. JNDI object trong bộ nhớ không đồng nghĩa trạng thái lưu trữ hợp lệ trên server.

**“Muốn xóa email thì set `""` rồi save.”** Không nên giả định. Với attribute tùy chọn, dùng Modify xóa attribute theo hợp đồng nghiệp vụ và schema.

**“Một PATCH body không có mail và mail=null giống nhau.”** Không nhất thiết; nếu DTO làm mất phân biệt, nguy cơ xóa sai dữ liệu.

**“Bộ lọc phủ định luôn trả mọi entry còn lại.”** Không tuyệt đối, vì LDAP có logic `Undefined`, ACL, base/scope và giới hạn kết quả.

**“Có dấu `*` là filter vẫn an toàn.”** Không đúng với user input nối chuỗi; cần query builder hoặc parameter encoding để chống LDAP injection.

## 22. Bài tập thực hành

### Bài 1 – Phân loại filter

Với ba entry Lan, Minh, Hoa trong fixture, dự đoán kết quả của:

1. `(mail=*)`
2. `(!(mail=*))`
3. `(mail=)`
4. `(&(objectClass=inetOrgPerson)(!(mail=*)))`

Giải thích vì sao câu 3 không có kết quả cố định nếu không biết schema/matching rule và dữ liệu zero-length trên server.

### Bài 2 – Phân biệt null, empty, blank

Cho:

```java
String a = null;
String b = "";
String c = "  ";
```

Hãy liệt kê kết quả hợp lệ của `isEmpty()` và `isBlank()` khi có guard `null`. Sau đó giải thích vì sao không thể ánh xạ trực tiếp ba trạng thái này thành “LDAP attribute absent/present” mà không biết cách mapper và query hoạt động.

### Bài 3 – Viết LdapQueryBuilder

Viết hai query dưới base `ou=people`, scope `SUBTREE`, đối tượng `inetOrgPerson`:

- Người có `telephoneNumber`.
- Người không có `telephoneNumber`.

Tránh trộn `where(...)` với `filter(...)` trên cùng builder. Kiểm tra kết quả trên fixture có một người có điện thoại và một người thiếu điện thoại.

### Bài 4 – Projection và ACL

Một query có filter `(mail=*)` nhưng `attributes("uid")`. Sau khi search, mapper nhận `attrs.get("mail")==null`. Vì sao không nên báo cáo “hồ sơ không có mail”? Làm thế nào để kiểm tra ACL và attribute selection có đúng?

### Bài 5 – Xóa attribute tùy chọn

Viết `ModificationItem` xóa **toàn bộ** thuộc tính `mail`. So sánh với `REPLACE_ATTRIBUTE("mail", "")` và `REMOVE_ATTRIBUTE("member", someDn)`. Nêu lỗi có thể gặp nếu attribute đã vắng mặt hoặc schema yêu cầu attribute bắt buộc.

### Bài 6 – Đảm bảo an toàn filter

Một API nhận `email` từ người dùng. Nếu input là `"*"`, `"a*"` hoặc chuỗi rỗng, phép nối filter `"(mail=" + email + ")"` dẫn đến điều gì? Viết lại bằng `where("mail").is(email)` và thêm validation đầu vào; thiết kế test xác nhận literal wildcard được encode.

### Bài 7 – Thiết kế PATCH tri-state

API PATCH hồ sơ người dùng có thể nhận key `mail` bị bỏ qua, bằng `null` hoặc bằng chuỗi hợp lệ. Định nghĩa enum ý định `NO_CHANGE`, `REMOVE`, `SET`. Hãy viết mapper request → thao tác LDAP để tránh biến field bị bỏ qua thành lệnh xóa.

### Bài 8 – Đánh giá zero-length trên server thật

Chọn directory và attribute có quy tắc syntax rõ ràng. Kiểm tra server có chấp nhận một value 0 ký tự không, có trả nó trong `SearchResult` không, và `(attr=*)`/`(attr=)` hoạt động thế nào. Ghi rõ phiên bản directory, schema, bind identity, ACL và kết quả thay vì suy luận từ unit test JNDI.

## 23. Checklist trước khi dùng filter vào nghiệp vụ

| Câu hỏi kiểm tra | Tiêu chí đúng |
|---|---|
| Muốn “có thuộc tính” hay “giá trị bằng X”? | Dùng đúng presence hoặc equality. |
| Muốn “không có thuộc tính”? | Dùng `(!(attr=*))`, không dùng `(attr=)`. |
| Có cần hỗ trợ giá trị zero-length? | Xác minh syntax, matching rule và server. |
| Có nhầm chuỗi trắng với chuỗi rỗng? | Xác định quy tắc validation và chuẩn hóa. |
| Search base/scope đã đủ? | Không bỏ sót OU hoặc naming context liên quan. |
| Filter kết hợp objectClass đúng? | Chỉ xét loại entry nghiệp vụ cần tìm. |
| User input có được encode? | Dùng builder/parameter binding; không nối raw filter. |
| Attribute có được request trả về? | Kiểm tra `attributes(...)`/SearchControls. |
| Bind account có đủ quyền? | ACL cho phép tìm/đọc attribute phù hợp. |
| Java mapper có xử lý null và zero value? | Không dereference `Attribute` khi thiếu. |
| API PATCH có phân biệt omitted/null/empty? | Không vô tình xóa hoặc ghi giá trị rỗng. |
| Test đã chạy trên directory thật? | Fixture và account test kiểm chứng presence/absence. |
| Có kiểm tra replica/cache? | Không kết luận từ dữ liệu stale. |
| Có xử lý exception riêng với empty result? | Không biến lỗi LDAP thành “thiếu email”. |

## 24. Kết luận và tài liệu tham khảo

**Thuộc tính vắng mặt** và **giá trị rỗng** khác nhau ở cả LDAP, Java và API nghiệp vụ. `(mail=*)` là **presence filter**, `(!(mail=*))` là **phủ định presence**, còn `(mail=)` là **equality assertion với giá trị dài 0**, không phải cách viết của `IS NULL`. Việc giá trị zero-length có hợp lệ hay so khớp được hay không phụ thuộc schema/matching rule/server.

Trong Spring Data LDAP, dùng `LdapQueryBuilder` và `LdapTemplate` để filter trên server, đồng thời xử lý `Attributes` và ODM mapping cẩn thận: một field `null` ở client có thể do projection/ACL, không nhất thiết vì attribute thực sự vắng mặt. Với thao tác xóa attribute tùy chọn, thiết kế LDAP Modify rõ ràng thay vì đặt `""` theo thói quen. Kiểm thử integration với directory riêng là cách bảo đảm kết luận đúng trong môi trường mục tiêu.

Các tài liệu chính thức để đối chiếu:

- [RFC 4515 – LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4511 – LDAP Protocol, filter three-valued logic](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4517 – LDAP Syntaxes: Directory String và IA5 String](https://www.rfc-editor.org/rfc/rfc4517)
- [RFC 4519 – LDAP Schema for User Applications, mail attribute](https://www.rfc-editor.org/rfc/rfc4519)
- [Spring LDAP – Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP – LdapQueryBuilder API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP – LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Spring Data LDAP – Reference](https://docs.spring.io/spring-data/ldap/reference/)
