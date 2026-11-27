# Attribute bắt buộc theo object class trong LDAP

Khi thêm một người dùng hay nhóm bằng Spring LDAP, không thể gửi một tập thuộc tính tùy ý lên LDAP server. **Schema** quy định entry thuộc những *object class* nào, những thuộc tính nào phải hiện diện và những thuộc tính nào được phép xuất hiện. Hiểu **`MUST`** và **`MAY`** là nền tảng để tạo, sửa và mapping entry bằng `LdapTemplate`, `LdapClient` hoặc ODM mà không gặp lỗi schema.

Bài học thuộc phần **Attribute và schema** của SPRING_LDAP. Ví dụ sử dụng `person`, `inetOrgPerson`, `organizationalUnit` và `groupOfNames` quen thuộc; các máy chủ LDAP cụ thể có thể thêm class, thuộc tính, quy tắc DIT và ràng buộc riêng.

## 1. Object class là gì?

Mỗi LDAP entry có **DN** (vị trí trong Directory Information Tree – DIT), tập thuộc tính và thuộc tính đặc biệt `objectClass` nêu các class mà entry thuộc về.

Ví dụ người dùng:

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

| Thành phần | Vai trò |
| --- | --- |
| `dn` | Định danh vị trí entry; thành phần trái nhất `uid=an` là RDN |
| `objectClass` | Tập các class mà entry khai báo |
| `uid` | Thuộc tính định danh trong ví dụ, đồng thời là thuộc tính làm RDN |
| `cn` | Common name, tên thông dụng của người dùng |
| `sn` | Surname, họ theo schema |
| `mail` | Email, thường là thuộc tính tùy chọn |

Một object class được định nghĩa bởi schema với các thành phần như:

- **OID/NAME**: định danh và tên của class.
- **SUP**: class cha (superclass) để kế thừa định nghĩa.
- **ABSTRACT**, **STRUCTURAL**, **AUXILIARY**: phân loại class.
- **MUST**: các *attribute type* bắt buộc.
- **MAY**: các *attribute type* được phép nhưng không bắt buộc.

Trong chuẩn LDAP, schema là hợp đồng được **server** thực thi. Java DTO hoặc annotation không tự thay đổi hợp đồng đó.

## 2. Ý nghĩa chính xác của `MUST` và `MAY`

Định nghĩa giản lược của class `person`:

~~~text
NAME: person
SUP: top
KIND: STRUCTURAL
MUST: cn, sn
MAY: userPassword, telephoneNumber, seeAlso, description
~~~

Đây là cách trình bày khái niệm, không phải chuỗi định nghĩa schema hoàn chỉnh. Trên server, cú pháp schema sử dụng biểu thức object class và OID.

| Khái niệm | Điều kiện đối với một entry | Ví dụ |
| --- | --- | --- |
| **MUST** | Thuộc tính phải tồn tại với ít nhất một giá trị hợp lệ | `person` cần `cn` và `sn` |
| **MAY** | Thuộc tính được phép có hoặc vắng mặt | `person` có thể có `telephoneNumber` |
| Không được class/schema cho phép | Thường không được gửi trong entry | Một thuộc tính tùy biến chưa được khai báo |
| `SINGLE-VALUE` | Thuộc tính có tối đa một giá trị | Tùy định nghĩa của attribute type |
| Thuộc tính đa trị | Có thể có nhiều giá trị nếu schema cho phép | `objectClass`, `member` |

**`MUST` không quy định một giá trị cố định.** `person` phải có `cn` nhưng có thể là “Nguyen Van An” hoặc một tên khác, miễn giá trị đáp ứng cú pháp và ràng buộc của server. **`MAY` không có nghĩa giá trị nào cũng hợp lệ**; thuộc tính tùy chọn vẫn chịu kiểm tra kiểu dữ liệu, số lượng giá trị và chính sách.

Cũng cần phân biệt **schema cho phép** với **quyền truy cập**. `mail` có thể được phép trong schema nhưng chưa có trong entry, hoặc tài khoản hiện tại không được phép đọc/sửa nó. Việc một truy vấn không trả về thuộc tính chưa đủ để kết luận thuộc tính đó vắng mặt.

## 3. `MUST` được kế thừa như thế nào?

Một object class kế thừa yêu cầu từ class cha thông qua `SUP`. Chuỗi class quen thuộc:

~~~mermaid
flowchart TD
  T["top · ABSTRACT<br/>MUST: objectClass"]
  P["person · STRUCTURAL<br/>MUST thêm: cn, sn"]
  O["organizationalPerson · STRUCTURAL<br/>Không thêm MUST"]
  I["inetOrgPerson · STRUCTURAL<br/>Không thêm MUST"]
  T --> P --> O --> I
~~~

Điều đó có nghĩa:

1. `top` yêu cầu `objectClass`.
2. `person` kế thừa `top`, bổ sung `cn` và `sn`.
3. `organizationalPerson` kế thừa `person`, thêm nhiều thuộc tính tùy chọn.
4. `inetOrgPerson` kế thừa `organizationalPerson`, thường cho phép thêm `uid`, `mail`, `givenName` nhưng **không bỏ các MUST của cha**.

Vì vậy, entry `inetOrgPerson` thông thường phải có ít nhất `objectClass`, `cn` và `sn`; không cần `mail` để thỏa mãn tập MUST chuẩn đó.

Tư duy hợp nhất các yêu cầu:

~~~text
MUST hieu luc cua entry =
  MUST tu class hien tai
  + MUST ke thua tu cac superclass
  + MUST tu auxiliary class dang ap dung
  + cac rang buoc bo sung cua schema/DIT neu co
~~~

Phép cộng là hình ảnh minh họa việc **hợp nhất tập ràng buộc**, không phải thuật toán kiểm tra schema đầy đủ của LDAP server.

### `uid` là `MAY`, tại sao ví dụ vẫn phải có?

Với `inetOrgPerson` phổ biến, `uid` là tùy chọn. Tuy nhiên DN ví dụ là:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

RDN `uid=an` yêu cầu entry có giá trị `uid: an` phù hợp với quy tắc đặt tên. Đây là **ràng buộc naming/RDN**, không phải `MUST` do `inetOrgPerson` khai báo.

So sánh:

- **Do object class:** `cn` và `sn` bắt buộc dù DN chọn RDN nào.
- **Do naming:** `uid` cần hiện diện với giá trị đúng khi DN dùng `uid=an`.
- **Do nghiệp vụ:** tổ chức có thể quy định email phải có, ngay cả khi schema xếp `mail` vào `MAY`.

Không suy ra attribute là `MUST` chỉ vì nó nằm trong DN; cũng không được bỏ một attribute đang được DN tham chiếu chỉ vì nó là `MAY`.

## 4. Ví dụ những class LDAP thường dùng

| Object class | Loại | MUST hiệu lực tiêu biểu | Thuộc tính thường tùy chọn |
| --- | --- | --- | --- |
| `organizationalUnit` | STRUCTURAL | `objectClass`, `ou` | `description`, `telephoneNumber` |
| `inetOrgPerson` | STRUCTURAL | `objectClass`, `cn`, `sn` | `uid`, `mail`, `givenName` |
| `groupOfNames` | STRUCTURAL | `objectClass`, `cn`, `member` | `description`, `owner` |

Bảng giới thiệu các ràng buộc quan trọng từ class chuẩn, không phải danh mục mọi thuộc tính được phép trên mọi server.

### A. Organizational Unit

~~~ldif
dn: ou=engineering,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: engineering
description: Engineering department
~~~

`ou` là MUST của `organizationalUnit`. Nếu xóa `ou` khỏi entry trên, vừa mất thuộc tính bắt buộc vừa không còn giá trị tương ứng với RDN `ou=engineering`.

### B. Person

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
~~~

Không có `mail` nhưng vẫn đủ MUST. Nếu bỏ dòng `sn: Nguyen` thì tạo entry thường thất bại, vì `person` yêu cầu `sn` dù `inetOrgPerson` không khai báo lại.

### C. Group

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

`groupOfNames` chuẩn yêu cầu **`cn` và `member`**. Một nhóm không có bất kỳ giá trị `member` nào không đáp ứng MUST của class này. Nếu cần nhóm rỗng, hãy chọn class hay giải pháp được **server hỗ trợ**; không nên thêm thành viên giả để vượt qua ràng buộc.

Một giá trị `member` có cú pháp DN, nhưng việc server kiểm tra đích tham chiếu có tồn tại hay không có thể phụ thuộc cấu hình; không đồng nhất cú pháp DN hợp lệ với kiểm tra tồn tại entry.

## 5. Auxiliary class có thể bổ sung MUST

Ngoài **structural class** mô tả kiểu cấu trúc chính, LDAP có **auxiliary class** để bổ sung thuộc tính. Ví dụ minh họa *giả định*:

~~~text
STRUCTURAL: inetOrgPerson
  MUST hieu luc: objectClass, cn, sn

AUXILIARY: customSecurityProfile
  MUST bo sung: securityLevel

Khi hai class cung ap dung:
  MUST: objectClass, cn, sn, securityLevel
~~~

`customSecurityProfile` và `securityLevel` chỉ là tên giả định, **chưa được định nghĩa trong schema chuẩn**. Không đưa vào server thật nếu chưa tạo/kiểm tra schema.

Về cấu trúc class:

- Một entry thông thường dùng một **chuỗi structural class hợp lệ**, như `person` → `organizationalPerson` → `inetOrgPerson`.
- Không thể ghép tùy tiện hai structural class độc lập, chẳng hạn `inetOrgPerson` và `groupOfNames`, vào cùng một entry.
- Auxiliary class có thể bổ sung cả `MUST` lẫn `MAY`. Việc có được dùng class đó trên một loại entry cụ thể hay không còn có thể phụ thuộc quy tắc nội dung DIT và chính sách server.
- Khi gỡ auxiliary class, cần xem các thuộc tính chỉ được class đó cho phép; việc bỏ class không mặc nhiên xóa mọi thuộc tính liên quan.

**Kết luận thực hành:** phải xem toàn bộ tập `objectClass` và kế thừa của chúng, không chỉ tên class cuối cùng hoặc structural class trực tiếp.

## 6. Object class và attribute type khác nhau ở đâu?

Object class quyết định **thuộc tính nào cần/có thể hiện diện**. *Attribute type* định nghĩa **bản chất của thuộc tính**.

| Thành phần schema | Kiểm soát | Ví dụ ý nghĩa |
| --- | --- | --- |
| Object class `MUST`/`MAY` | Tính bắt buộc/được phép của thuộc tính | `person` cần `sn` |
| Attribute `SYNTAX` | Kiểu dữ liệu | Chuỗi, số, DN, binary… |
| Attribute `SINGLE-VALUE` | Số lượng giá trị tối đa | Một giá trị nếu được khai báo đơn trị |
| Attribute `EQUALITY`/`SUBSTR`/`ORDERING` | Quy tắc so sánh/tìm kiếm | So sánh chuỗi, số, thứ tự |
| Attribute `USAGE`, `NO-USER-MODIFICATION` | Đặc tính thuộc tính vận hành | Thuộc tính do server quản lý |

Một entry **đủ mọi MUST vẫn có thể bị từ chối** vì giá trị sai cú pháp, gán nhiều giá trị cho thuộc tính đơn trị, chứa thuộc tính không được phép, sai DN/RDN hoặc thiếu quyền ghi.

Ví dụ `mail` có thể là MAY theo object class nhưng vẫn phải tuân thủ syntax do server áp dụng. Ngược lại, `member` là MUST của `groupOfNames` và có kiểu giá trị DN; đưa một chuỗi không thể diễn giải thành DN có thể gây lỗi syntax.

## 7. Spring LDAP xử lý các ràng buộc này như thế nào?

~~~mermaid
flowchart TD
  A["Service tạo entry Java"] --> B["Validation nghiệp vụ"]
  B --> C["LdapTemplate / LdapClient / ODM"]
  C --> D["ContextSource: URL, base DN, bind"]
  D --> E["LDAP server"]
  E --> F{"Schema, naming, ACL hợp lệ?"}
  F -->|Có| G["Ghi entry"]
  F -->|Không| H["LDAP error"]
~~~

Ba lớp có trách nhiệm riêng:

- **`ContextSource`** cấp kết nối và thông tin bind; nó không tự điền `MUST` cho entry.
- **`LdapTemplate`/`LdapClient`** chạy lệnh LDAP; các thao tác tạo, sửa, tìm kiếm đi qua server.
- **ODM hoặc mapper** biến entry thành dữ liệu Java; annotation hay trường nullable Java không làm thay đổi schema.
- **LDAP server** là nơi cuối cùng kiểm tra schema, naming, ACL và các chính sách bổ sung.

### Thêm entry với `LdapTemplate`

Giả định `LdapContextSource` đã có base `dc=example,dc=org`; DN ứng dụng xây dựng bên dưới sẽ **tương đối với base đã cấu hình**:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonDirectory {
    private final LdapTemplate ldapTemplate;

    public PersonDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(
            String uid, String commonName, String surname, String email) {

        if (uid == null || uid.isBlank()
                || commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("Missing required person fields");
        }

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[]{
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", commonName);
        entry.setAttributeValue("sn", surname);

        if (email != null && !email.isBlank()) {
            entry.setAttributeValue("mail", email);
        }

        ldapTemplate.bind(entry);
    }
}
~~~

Giải thích từng lựa chọn:

1. `LdapNameBuilder` tạo DN và escape giá trị RDN phù hợp, tránh tự ghép chuỗi từ `uid`.
2. `objectClass` nêu chuỗi class tương thích với `inetOrgPerson`.
3. `cn` và `sn` được đưa vào vì `person` yêu cầu.
4. `uid` được đưa vào để tương ứng RDN `uid=...`.
5. `mail` chỉ ghi khi có dữ liệu vì là thuộc tính tùy chọn trong schema ví dụ.
6. `ldapTemplate.bind(entry)` còn yêu cầu entry chưa tồn tại, parent `ou=people` đã tồn tại và tài khoản bind có quyền ghi. Đủ MUST chưa bảo đảm thao tác thành công.

Code chỉ minh họa schema: trong hệ thống thật, bổ sung kiểm tra quy tắc UID và email, xử lý lỗi, giới hạn quyền, timeout, kết nối LDAPS/StartTLS được kiểm tra chứng chỉ và bảo vệ thông tin xác thực.

### Sửa entry có thể gây thiếu MUST

Giả sử entry đang có:

~~~text
cn: Nguyen Van An
sn: Nguyen
mail: an@example.org
~~~

Nếu gọi `modifyAttributes(...)` và **xóa hẳn `sn`**, entry còn lại không còn thỏa MUST của `person`; server thường từ chối. **Đổi giá trị `sn`** hợp lệ là thao tác khác.

Khi ghi hoặc đồng bộ nhiều trường, cần phân biệt giá trị `null`, chuỗi rỗng và yêu cầu *remove attribute* theo API đang dùng. Đừng thay thế toàn bộ tập thuộc tính chỉ để sửa email nếu thao tác này có thể làm rơi các MUST hiện hữu.

### ODM và sự khác biệt giữa field Java với attribute LDAP

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(base = "ou=people",
       objectClasses = {"top", "person",
                        "organizationalPerson", "inetOrgPerson"})
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

    public DirectoryPerson() {}
    // Getter/setter theo nhu cau.
}
~~~

`@Entry` và `@Attribute` biểu diễn cách mapping. Field `surname` có thể được gán `null` ở Java, nhưng LDAP server vẫn yêu cầu `sn` nếu entry thuộc `person`. ODM không tự bảo đảm mọi object được tạo đều hợp schema. Cần validation ứng dụng để báo lỗi sớm và xử lý lỗi server thực tế, nhất là khi schema hoặc mapping thay đổi.

## 8. Đọc schema thực tế trên server

Không phải mọi thư mục dùng cùng bộ class. Active Directory, OpenLDAP và các hệ thống LDAP khác có thể khác nhau về schema mở rộng, rule đặt tên, attribute type và chính sách.

Để kiểm tra:

1. Đọc thuộc tính vận hành `subschemaSubentry` từ một entry thích hợp trong vùng dữ liệu.
2. Từ DN subschema subentry được trả về, đọc các thuộc tính `objectClasses` và `attributeTypes` nếu được cấp quyền.
3. Tìm định nghĩa class đang dùng, theo `SUP` đến các lớp cha, rồi tổng hợp các `MUST`.
4. Kiểm tra auxiliary class, các ràng buộc nội dung DIT, syntax, cardinality và ACL.
5. Kiểm thử tạo/sửa trên môi trường riêng. Không suy đoán schema của server từ class name hoặc entity Java.

Ví dụ thao tác đọc bằng một công cụ có hỗ trợ `ldapsearch`:

~~~bash
# Tim DN cua subschema subentry duoc cong bo.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" subschemaSubentry

# Thay <SCHEMA_DN> bang gia tri tra ve.
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=service,dc=example,dc=org" -W \
  -b "<SCHEMA_DN>" -s base \
  "(objectClass=*)" objectClasses attributeTypes
~~~

`-W` yêu cầu nhập mật khẩu tương tác, tránh để mật khẩu thật nằm trong lịch sử lệnh. DN, URL và tài khoản ở ví dụ là giả định. Quyền đọc subschema hoặc cách server công bố schema có thể khác nhau.

## 9. Lỗi thường gặp khi thiếu hoặc sai thuộc tính

| Tình huống | LDAP result code thường gặp | Hướng điều tra |
| --- | --- | --- |
| `inetOrgPerson` thiếu `sn` | `objectClassViolation (65)` | Đọc `MUST` của `person` và chuỗi cha |
| Thuộc tính chưa được schema biết | `undefinedAttributeType (17)` | Kiểm tra tên và khai báo attribute type |
| Giá trị không đúng syntax | `invalidAttributeSyntax (21)` | Đọc syntax và dạng giá trị được chấp nhận |
| Giá trị vi phạm giới hạn hoặc đơn trị | Có thể là `constraintViolation (19)` | Kiểm tra attribute type và chính sách |
| Thuộc tính nằm ngoài tập được phép | Thường là `objectClassViolation (65)` | Kiểm tra `MAY`, auxiliary class và schema mở rộng |
| Có đủ MUST nhưng không được ghi | `insufficientAccessRights (50)` | Kiểm tra ACL và danh tính bind |
| Entry cha chưa có | `noSuchObject (32)` | Kiểm tra DN, base và cây DIT |
| DN đã tồn tại | `entryAlreadyExists (68)` | Kiểm tra trùng định danh |

Một lỗi có thể có nhiều điều kiện sai; server thường trả về lỗi được phát hiện trước. Ví dụ bỏ thuộc tính làm RDN có thể nhận lỗi naming thay vì thông báo thiếu MUST. Vì thế **không đồng nhất mọi lỗi `bind` với vi phạm schema**.

Spring LDAP chuyển lỗi LDAP/JNDI sang exception trong thư viện. Khi ghi log để điều tra, lưu loại thao tác, mã lỗi và context cần thiết nhưng không để lộ mật khẩu bind hoặc dữ liệu cá nhân ngoài mục đích.

## 10. Bài thực hành và đáp án

Chuẩn bị thư mục thử nghiệm có các OU `ou=people`, `ou=groups` và tài khoản có quyền ghi giới hạn ở đó. Tạo entry với những biến thể sau:

| Trường hợp | Class | Thuộc tính | Dự kiến xét riêng MUST |
| --- | --- | --- | --- |
| A | `inetOrgPerson` cùng các class cha | `objectClass`, `uid`, `cn`, `sn` | Đạt |
| B | `inetOrgPerson` | Như A nhưng **thiếu `sn`** | Không đạt |
| C | `inetOrgPerson` | Như A nhưng **không có `mail`** | Đạt |
| D | `organizationalUnit` | `objectClass`, `ou` | Đạt |
| E | `organizationalUnit` | Thiếu `ou` | Không đạt |
| F | `groupOfNames` | `objectClass`, `cn`, thiếu `member` | Không đạt |
| G | `groupOfNames` | `objectClass`, `cn`, một `member` DN hợp lệ | Đạt |

Mọi trường hợp phải có DN, parent, quy tắc naming, schema và ACL hợp lệ. “Đạt MUST” là **điều kiện cần**; không tự động bảo đảm thao tác ghi thành công trên mọi server.

**Tự trả lời:**

1. Vì sao `inetOrgPerson` phải có `sn` nếu định nghĩa class này không ghi trực tiếp `MUST sn`?
2. Một entry `inetOrgPerson` thiếu `mail` có luôn sai schema không?
3. `uid` là MAY nhưng DN là `uid=an,...`: có thể bỏ hoàn toàn `uid` không?
4. Auxiliary class bổ sung MUST mới có làm mất MUST kế thừa từ `person` không?
5. Tại sao Java đã kiểm tra field bắt buộc nhưng vẫn có thể bị server từ chối?
6. Đủ MUST rồi thì cần kiểm tra thêm các loại ràng buộc gì?

**Đáp án:**

1. Vì `inetOrgPerson` kế thừa `organizationalPerson` → `person`; `person` yêu cầu `cn` và `sn`.
2. Không; `mail` thường là MAY. Chính sách riêng của hệ thống có thể yêu cầu email.
3. Không đúng với RDN minh họa; `uid: an` cần hiện diện theo quy tắc naming.
4. Không; các yêu cầu được hợp nhất, không thay thế nhau.
5. Vì schema server có thể mở rộng, và server còn kiểm tra DN, syntax, quyền truy cập, quy tắc nội dung.
6. Attribute syntax, số lượng giá trị, tập attribute được phép, class cấu trúc hợp lệ, RDN/parent, ACL và ràng buộc server.

## 11. Điều cần nhớ

- **`MUST`** quy định thuộc tính bắt buộc; **`MAY`** cho phép thuộc tính tùy chọn. Luôn xem **kế thừa từ class cha** và auxiliary class.
- `inetOrgPerson` điển hình cần `cn` và `sn` do kế thừa `person`. `uid` có thể cần vì RDN mặc dù là MAY.
- Kiểm tra MUST không thay thế kiểm tra cú pháp, cardinality, naming, quyền hoặc quy tắc nghiệp vụ.
- Với `ContextSource`, `LdapTemplate`/`LdapClient` và ODM, cần chuẩn bị dữ liệu đúng schema, dùng kết nối TLS và tài khoản có quyền tối thiểu, kiểm thử thao tác ghi trên thư mục riêng.
- Khi khác biệt giữa các server, lấy định nghĩa từ **schema đang được LDAP server công bố** rồi xác minh bằng thử nghiệm được kiểm soát.
