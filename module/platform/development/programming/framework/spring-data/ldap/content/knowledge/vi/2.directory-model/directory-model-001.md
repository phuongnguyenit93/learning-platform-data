# Entry và attribute trong một bản ghi LDAP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện một **entry** trong cây thư mục LDAP, đọc được tên phân biệt (**DN**) và các **attribute** của entry.
- Phân biệt **attribute type**, **attribute value**, thuộc tính đơn trị/đa trị và thuộc tính vận hành.
- Giải thích vai trò của `objectClass` và schema đối với dữ liệu được phép lưu.
- Ánh xạ một entry LDAP thành đối tượng Java bằng **Spring Data LDAP**, biết khi nào dùng repository và `LdapTemplate`.

Đây là nền tảng để thực hiện tìm kiếm, cập nhật và quản lý người dùng/nhóm trong ứng dụng Java kết nối dịch vụ thư mục.

## 1. Entry là gì?

**LDAP (Lightweight Directory Access Protocol)** tổ chức dữ liệu thành các **entry** trong **Directory Information Tree (DIT)**. Mỗi entry đại diện cho một đối tượng có tên trong thư mục, chẳng hạn người dùng, phòng ban, nhóm hoặc thiết bị.

Một entry có hai thành phần cần phân biệt:

1. **DN (Distinguished Name)**: tên định danh vị trí của entry trong DIT.
2. **Tập hợp attribute**: những thông tin được lưu cho entry, ví dụ tên, email, số điện thoại và các lớp đối tượng.

Ví dụ cây thư mục:

```text
dc=example,dc=org
└── ou=people
    ├── uid=an.nguyen
    └── uid=lan.tran
```

Entry `uid=an.nguyen` nằm dưới `ou=people`. DN đầy đủ của nó là:

```text
uid=an.nguyen,ou=people,dc=example,dc=org
```

Trong đó, `uid=an.nguyen` là **Relative Distinguished Name (RDN)**, tức phần tên phân biệt entry với các entry cùng cấp. `ou=people` và `dc=example,dc=org` cho biết các cấp cha. DN xác định entry trong cây; giá trị của một attribute riêng lẻ như `uid` hoặc `mail` không mặc nhiên là định danh duy nhất toàn thư mục.

> **Lưu ý:** LDAP không phải cơ sở dữ liệu quan hệ. Entry không tương đương một hàng trong bảng theo nghĩa có khóa chính số nguyên, cột cố định cho mọi bản ghi và quan hệ JOIN. Mô hình dữ liệu tuân theo DIT, các attribute được định nghĩa bởi schema và các quy tắc của dịch vụ thư mục.

## 2. Đọc một entry ở định dạng LDIF

**LDIF (LDAP Data Interchange Format)** là định dạng văn bản thường dùng để biểu diễn, trao đổi hoặc nhập/xuất dữ liệu LDAP. Một entry nhân viên mẫu:

```ldif
dn: uid=an.nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an.nguyen
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an.nguyen@example.org
mail: an.work@example.org
telephoneNumber: +842812345678
description: Tai khoan nhan su minh hoa
```

Đọc ví dụ từ trên xuống:

| Dòng LDIF | Ý nghĩa |
| --- | --- |
| `dn` | Tên của **entry**, không phải một attribute dữ liệu thông thường của entry. |
| `objectClass` | Một **attribute đa trị** thể hiện các lớp đối tượng mà entry thuộc về. |
| `uid` | Mã đăng nhập hoặc định danh ứng dụng; trong ví dụ, đây còn là attribute dùng để đặt RDN. |
| `cn` | `commonName`, tên thường dùng; có thể là đa trị nếu schema cho phép. |
| `sn` | `surname`, họ hoặc tên gia đình theo schema của lớp `person`. |
| `givenName` | Tên gọi. |
| `mail` | Có hai giá trị email; hai dòng vẫn thuộc **một loại attribute**. |
| `telephoneNumber` | Số điện thoại; cách kiểm tra/so khớp phụ thuộc syntax và matching rule. |
| `description` | Thông tin mô tả. |

Đừng nhầm số dòng trong LDIF với số attribute. `mail` xuất hiện hai dòng vì một attribute có hai giá trị; `objectClass` xuất hiện bốn dòng vì cùng lý do. Thứ tự các giá trị của attribute đa trị **không được bảo đảm**; ứng dụng không nên dùng “email đầu tiên” nếu chưa có quy ước riêng.

**RDN và attribute có quan hệ nhưng không đồng nhất.** Ở ví dụ này, RDN là `uid=an.nguyen` và entry cũng có `uid: an.nguyen`. Theo quy tắc đặt tên thông thường của LDAP, giá trị dùng trong RDN phải tương ứng với giá trị attribute của entry. Tuy nhiên, DN là tên trong DIT, còn `uid` vẫn là dữ liệu có thể được truy vấn; thay đổi thành phần tên có thể cần thao tác **rename/ModifyDN** chứ không chỉ thay giá trị attribute.

## 3. Cấu trúc của một attribute

Một attribute trong LDAP gồm **mô tả attribute** (*attribute description*) và **một hoặc nhiều giá trị** (*values*).

```text
mail: an.nguyen@example.org
│     └── value
└──────── attribute description (type: mail)
```

Các thành phần quan trọng:

| Thành phần | Giải thích | Ví dụ |
| --- | --- | --- |
| **Attribute type** | Tên hoặc OID định nghĩa thuộc tính. | `cn`, `uid`, `mail`, `2.5.4.3` |
| **Attribute option** | Phần tùy chọn bổ sung trong mô tả attribute, nếu schema/server hỗ trợ. | `cn;lang-vi` |
| **Value** | Dữ liệu thực tế, phải phù hợp cú pháp của type. | `An Nguyen` |
| **Syntax** | Kiểu dữ liệu LDAP ở mức schema, có thể là chuỗi, số, DN, dữ liệu nhị phân... | Directory String, DN |
| **Matching rule** | Quy tắc so sánh khi tìm kiếm, kiểm tra bằng nhau hoặc sắp xếp nếu được hỗ trợ. | `caseIgnoreMatch` |

### 3.1. Đơn trị và đa trị

- **Single-valued attribute**: schema chỉ cho phép tối đa một giá trị hiện diện trong entry.
- **Multi-valued attribute**: schema cho phép nhiều giá trị cùng loại, ví dụ `mail` trong mẫu hoặc `member` trong nhiều mô hình nhóm.
- **Thiếu attribute** khác với **attribute có chuỗi rỗng**: một attribute không hiện diện không có giá trị; giá trị rỗng có hợp lệ hay không phụ thuộc syntax/schema và máy chủ.

Không thể suy ra “đơn trị” chỉ vì một entry hiện có đúng một dòng `cn`. Hãy tra định nghĩa schema, đặc biệt cờ `SINGLE-VALUE`, trước khi quyết định dùng `String` hay `Set<String>` trong Java.

### 3.2. Tên attribute, chữ hoa/thường và so khớp

Tên attribute như `cn` và `CN` được diễn giải không phân biệt chữ hoa/thường theo mô hình LDAP. Nhưng việc **so sánh giá trị** phụ thuộc matching rule được định nghĩa trong schema: không phải mọi attribute đều so sánh chuỗi theo cùng một cách.

Một type cũng có thể có tên thay thế hoặc OID; ví dụ `cn` thường được định nghĩa bởi OID `2.5.4.3`. Ứng dụng nên dùng tên attribute đã thống nhất với schema, tránh tự đổi chữ hoa/thường hay cắt khoảng trắng của giá trị trước khi biết quy tắc tương ứng.

### 3.3. Chuỗi, DN và dữ liệu nhị phân

Không phải giá trị attribute nào cũng là chuỗi văn bản. Một số thuộc tính như `jpegPhoto` lưu dữ liệu nhị phân; nhiều thuộc tính tham chiếu thành viên nhóm lưu **DN** của entry khác.

Trong LDIF, dữ liệu cần mã hóa có thể xuất hiện với dấu `::` để biểu thị **Base64**:

```text
description:: QW4gTmd1eWVu
```

Đây là cách biểu diễn giá trị trên file LDIF, **không phải** dấu hiệu tạo attribute `description:` khác. Khi ánh xạ sang Java, kiểu `String`, `byte[]`, `Name` hoặc một tập hợp phải phù hợp type, thư viện và cấu hình của LDAP provider.

## 4. Vì sao `objectClass` và schema quan trọng?

Schema quy định attribute nào được phép, attribute nào bắt buộc, cú pháp, cách so khớp và quan hệ kế thừa giữa các object class. Mọi entry LDAP theo mô hình chuẩn có attribute `objectClass`.

Entry mẫu thuộc chuỗi kế thừa:

```text
top (ABSTRACT)
  └── person (STRUCTURAL)
       └── organizationalPerson (STRUCTURAL)
            └── inetOrgPerson (STRUCTURAL)
```

Với `inetOrgPerson`, các attribute **bắt buộc** kế thừa từ `person` bao gồm `cn` và `sn`; các attribute như `uid`, `mail` và `givenName` là những lựa chọn được cho phép theo schema chuẩn. Vì vậy:

- Không thể tạo entry `inetOrgPerson` hợp lệ mà bỏ `cn` hoặc `sn` chỉ vì ứng dụng không dùng đến chúng.
- Có thể không có `mail`; `mail` là thuộc tính tùy chọn, không phải điều kiện để entry tồn tại.
- `uid` được dùng làm RDN trong ví dụ, nhưng schema `inetOrgPerson` **không bắt buộc mọi người dùng phải được đặt tên bằng `uid`**. DN có thể dùng attribute đặt tên khác, tùy quy tắc của directory.
- Máy chủ có thể tự bổ sung các superclass `objectClass` và áp dụng thêm quy tắc schema/quy tắc đặt tên riêng.

Ba loại object class phổ biến là **ABSTRACT** (cơ sở kế thừa), **STRUCTURAL** (loại đối tượng chính) và **AUXILIARY** (bổ sung khả năng/attribute khi được cho phép). Một entry có thể khai báo nhiều giá trị `objectClass` nhưng các lớp structural trong chuỗi kế thừa **không đồng nghĩa** với nhiều loại đối tượng độc lập.

Khi thao tác CRUD qua Spring Data LDAP, lỗi kiểu “object class violation” thường xuất hiện vì thiếu attribute bắt buộc, dùng attribute không được schema chấp nhận hoặc kết hợp object class không hợp lệ. Nên kiểm tra schema trước khi cho rằng đây là lỗi của repository.

## 5. User attribute và operational attribute

Trong LDAP có hai nhóm thông tin thường gặp:

| Nhóm | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **User attribute** | `cn`, `sn`, `uid`, `mail` | Mô tả đối tượng; thường được trả về khi tìm kiếm các attribute thông thường và khi tài khoản có quyền đọc. |
| **Operational attribute** | `createTimestamp`, `modifyTimestamp`, `creatorsName`, `modifiersName` | Phản ánh hoạt động/quản trị thư mục; thường **không được trả về mặc định**, có thể cần yêu cầu đích danh và cần quyền tương ứng. |

Các attribute như `memberOf` còn phụ thuộc đặc điểm máy chủ, overlay hoặc cơ chế đồng bộ; không nên mặc định mọi LDAP server đều cung cấp hoặc có thể ghi trực tiếp. Khi chỉ thấy vài attribute trong kết quả truy vấn, chưa thể kết luận các attribute còn lại không tồn tại: nguyên nhân có thể là phạm vi thuộc tính yêu cầu, quyền truy cập (ACL) hoặc cơ chế vận hành của server.

## 6. Ánh xạ entry sang Java với Spring Data LDAP

Spring Data LDAP cung cấp repository dựa trên **Object-Directory Mapping (ODM)** của Spring LDAP. `@Entry` chỉ định object class và base DN tương đối; `@Id` ánh xạ DN; `@Attribute` ánh xạ tên attribute; `@Transient` bỏ qua trường chỉ dùng trong ứng dụng.

Ví dụ một entity tương ứng với entry LDIF bên trên:

```java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

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
    private String username;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    @Attribute(name = "mail")
    private Set<String> emails;

    @Transient
    private String labelForUi;

    public Name getDn() { return dn; }
    public String getUsername() { return username; }
    public String getFullName() { return fullName; }
    public Set<String> getEmails() { return emails; }

    // Bổ sung constructor/getter/setter cần thiết cho ứng dụng.
}
```

Giải thích các quyết định ánh xạ:

- **`@Entry`** khai báo chuỗi object class mà entity quản lý; `base = "ou=people"` là vùng tìm kiếm/tạo entry liên quan, **tương đối với base DN của `ContextSource`** đã cấu hình.
- **`@Id Name dn`** biểu diễn DN qua `javax.naming.Name`. Đây không phải trường `long id` của JPA; cách hiểu DN tương đối/đầy đủ phụ thuộc cấu hình `ContextSource` và thao tác cụ thể.
- **`@Attribute(name = "uid")`** cho phép tên trường Java là `username` dù attribute LDAP tên `uid`.
- **`Set<String> emails`** biểu diễn các giá trị của `mail` không giả định thứ tự; chọn kiểu collection phù hợp với nhu cầu và khả năng mapping thực tế.
- **`@Transient`** ngăn Spring LDAP cố ghi trường `labelForUi` như một LDAP attribute chưa được schema định nghĩa.

Không phải lúc nào cũng cần `@Attribute`: nếu tên trường Java trùng đúng với tên attribute LDAP, ODM có thể ánh xạ theo tên trường. Tuy nhiên, khai báo rõ tên giúp người đọc đối chiếu Java với schema và giảm nhầm lẫn khi đặt tên theo quy ước khác.

### 6.1. Repository truy cập các entry đã ánh xạ

```java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    // Kế thừa các thao tác repository với khóa định danh là DN (Name).
}
```

`LdapRepository<PersonEntry>` giúp ứng dụng làm việc với entity LDAP. Khóa định danh của repository là `javax.naming.Name`, thay vì kiểu ID số của JPA. Việc đọc/ghi thành công còn phụ thuộc schema, base DN, quyền của tài khoản bind và trạng thái thực tế của directory.

### 6.2. Truy vấn theo attribute bằng `LdapTemplate`

Với truy vấn có điều kiện, Spring LDAP cung cấp `LdapTemplate` và `LdapQueryBuilder`:

```java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// ldapTemplate được Spring cấu hình từ ContextSource.
public PersonEntry findPerson(LdapTemplate ldapTemplate, String username) {
    LdapQuery ldapQuery = query()
        .base("ou=people")
        .where("uid").is(username);

    return ldapTemplate.findOne(ldapQuery, PersonEntry.class);
}
```

Ở đây, `where("uid").is(username)` tìm **entry** dựa trên **giá trị attribute** `uid`; `PersonEntry.class` cho biết kiểu Java được ODM ánh xạ. Phương thức có thể trả về `null` khi không có kết quả; tình huống nhiều kết quả cần xử lý theo hợp đồng API cụ thể.

**Bảo mật:** Hãy dùng query builder hoặc cơ chế tham số hóa của Spring LDAP cho dữ liệu từ bên ngoài. Tránh ghép chuỗi như `"(uid=" + username + ")"` thành LDAP filter, vì ký tự đặc biệt có thể làm thay đổi ý nghĩa truy vấn. Hạn chế base tìm kiếm, quyền tài khoản bind và thuộc tính trả về theo nhu cầu.

## 7. Quan sát entry trực tiếp từ directory

Nếu có một LDAP server minh họa, bạn có thể thử truy vấn chỉ các attribute cần đọc bằng công cụ `ldapsearch` (cú pháp phổ biến trên OpenLDAP client):

```bash
ldapsearch -LLL -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(uid=an.nguyen)" dn objectClass cn sn uid mail
```

- `-H` chọn máy chủ và kết nối LDAPS; cần chứng chỉ TLS đáng tin cậy.
- `-D` và `-W` lần lượt chọn bind DN và yêu cầu nhập mật khẩu qua prompt.
- `-b` xác định base DN để tìm kiếm.
- Chuỗi `"(uid=an.nguyen)"` là **LDAP filter**, còn các tên sau cùng giới hạn danh sách attribute cần trả về.
- `dn` trong kết quả là tên entry; `objectClass`, `cn`, `mail`... là các attribute.

Đường dẫn, tài khoản và dữ liệu trên chỉ là **ví dụ**, không phải dịch vụ đang hoạt động. Khi quan sát kết quả thực tế, lưu ý server có thể ẩn attribute vì ACL hoặc yêu cầu thêm attribute vận hành theo tên cụ thể.

## 8. Những lỗi mô hình dữ liệu thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng `dn` là attribute có thể cập nhật như `mail` | Cập nhật tên không đúng hoặc thất bại | Phân biệt định danh entry với attribute; dùng thao tác đổi DN/rename khi cần. |
| Cho rằng `uid` luôn duy nhất trên toàn hệ thống | Tìm kiếm trùng hoặc ánh xạ sai người dùng | Xác định chính sách uniqueness và phạm vi base DN; dùng DN để định danh entry trong directory. |
| Chỉ lưu một `mail` trong khi LDAP chứa nhiều giá trị | Mất thông tin khi đọc/ghi | Dùng collection khi cần bảo toàn giá trị đa trị; hiểu semantics của thao tác replace. |
| Thiếu `cn` hoặc `sn` cho `inetOrgPerson` | Server từ chối tạo/sửa entry | Tôn trọng các attribute `MUST` kế thừa trong schema. |
| Tự thêm attribute Java tùy ý vào entity | Lỗi schema khi ghi | Ánh xạ attribute được schema cho phép; dùng `@Transient` cho dữ liệu chỉ thuộc ứng dụng. |
| Dựa vào thứ tự các giá trị đa trị | Logic không ổn định | Dùng tiêu chí rõ ràng, không chọn phần tử theo vị trí ngẫu nhiên. |
| Tự ghép LDAP filter từ input | Sai cú pháp hoặc LDAP injection | Dùng `LdapQueryBuilder` với phép so sánh có escaping. |
| Tưởng không thấy `modifyTimestamp` nghĩa là entry không có thông tin sửa đổi | Chẩn đoán sai | Kiểm tra cách yêu cầu operational attribute và ACL của tài khoản đọc. |

## 9. Tình huống kiểm tra hiểu bài

Giả sử nhận được entry:

```ldif
dn: uid=lan.tran,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan.tran
cn: Lan Tran
sn: Tran
mail: lan@example.org
mail: lan.work@example.org
```

**Câu hỏi A.** Entry này có bao nhiêu giá trị `mail`? Có bao nhiêu loại attribute `mail`?

**Câu hỏi B.** Nếu xóa dòng `sn` rồi gửi thao tác tạo entry, điều gì có khả năng xảy ra?

**Câu hỏi C.** Nếu đổi RDN từ `uid=lan.tran` thành `uid=lan.nguyen`, có thể chỉ sửa một trường `username` trong Java rồi coi như đã đổi DN không?

**Gợi ý đáp án:**

- **A:** Hai giá trị thuộc **một** attribute type `mail`.
- **B:** Schema chuẩn của `inetOrgPerson` kế thừa yêu cầu bắt buộc `sn`; server kiểm tra schema thường từ chối entry thiếu giá trị này.
- **C:** Không thể mặc định như vậy. RDN thuộc tên entry; việc đổi tên cần xử lý bằng thao tác đổi DN phù hợp với LDAP và xem xét cập nhật attribute liên quan.

## Ghi nhớ cốt lõi

**Entry** là đơn vị dữ liệu có tên trong DIT; **DN** định vị entry; **attribute** chứa các giá trị; **schema/objectClass** quy định những attribute hợp lệ. Đối với Spring Data LDAP, `@Entry` mô tả lớp và base, `@Id` biểu diễn DN, `@Attribute` biểu diễn dữ liệu và `LdapRepository`/`LdapTemplate` thực hiện truy cập. Hiểu rõ ranh giới này giúp tránh các lỗi phổ biến khi tạo, đọc và cập nhật entry.

## Tài liệu tham khảo

1. [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html), đặc biệt mục 2.2, 2.5, 3.3, 3.4.
2. [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798.html).
3. [Spring LDAP — Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html).
4. [Spring Data LDAP — Usage](https://docs.spring.io/spring-data/ldap/reference/ldap/usage.html).
5. [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html).
