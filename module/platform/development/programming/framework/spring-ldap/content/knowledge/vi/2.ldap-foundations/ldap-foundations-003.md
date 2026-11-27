# Attribute, attribute value và multi-valued attribute trong LDAP

Trong LDAP, một **entry** đại diện cho một đối tượng trong cây thư mục, chẳng hạn người dùng, nhóm hoặc đơn vị tổ chức. Entry được nhận diện bằng **Distinguished Name (DN)** và chứa các **attribute** (thuộc tính). Mỗi attribute có một tên/kiểu thuộc tính và một hoặc nhiều **attribute value** (giá trị). Hiểu đúng cấu trúc này là nền tảng để đọc, tìm kiếm và cập nhật dữ liệu bằng Spring LDAP.

Sau bài học, bạn có thể:

- Phân biệt entry, DN, attribute type, attribute value và attribute nhiều giá trị.
- Đọc các thuộc tính được biểu diễn trong LDIF, kể cả khi một tên thuộc tính xuất hiện nhiều lần.
- Giải thích vì sao schema, syntax, matching rule và ràng buộc `SINGLE-VALUE` ảnh hưởng đến dữ liệu được phép lưu.
- Tìm kiếm entry theo một giá trị trong attribute nhiều giá trị; đọc và cập nhật những giá trị đó qua `LdapTemplate`.
- Tránh các lỗi thường gặp về thứ tự giá trị, xóa nhầm dữ liệu, so sánh chuỗi và dữ liệu nhị phân.

## 1. Entry, attribute và value liên hệ với nhau thế nào?

Hình dung một entry là hồ sơ nhân viên trong danh bạ:

```text
Entry: uid=lan,ou=people,dc=example,dc=org
  uid         -> {"lan"}
  cn          -> {"Lan Nguyen", "Nguyen Thi Lan"}
  sn          -> {"Nguyen"}
  mail        -> {"lan@example.org", "lan.work@example.org"}
  objectClass -> {"top", "person", "organizationalPerson", "inetOrgPerson"}
```

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Entry** | Một bản ghi trong cây thư mục LDAP | Hồ sơ của người dùng `lan` |
| **DN (Distinguished Name)** | Đường tên phân biệt dùng để định vị entry | `uid=lan,ou=people,dc=example,dc=org` |
| **Attribute type** | Loại thuộc tính được định nghĩa trong schema; thường dùng tên ngắn như `cn`, `mail` | `mail` |
| **Attribute value** | Một giá trị của attribute, có kiểu dữ liệu theo syntax của thuộc tính | `lan@example.org` |
| **Multi-valued attribute** | Một attribute mang nhiều giá trị riêng biệt trong cùng entry | `mail` có hai địa chỉ |
| **Single-valued attribute** | Một loại thuộc tính được schema giới hạn tối đa một giá trị | `employeeNumber` trong schema chuẩn thường dùng |

Trong ví dụ, `cn` là **một attribute với hai value**, không phải hai attribute độc lập cùng tên. `objectClass` cũng là attribute nhiều giá trị: các giá trị của nó cho biết entry tuân theo những lớp đối tượng nào.

**Phân biệt DN với dữ liệu thuộc tính:** `dn: uid=lan,ou=people,...` xác định vị trí/tên của entry; `uid: lan` là một thuộc tính của entry. Phần `uid=lan` trong DN là một Relative Distinguished Name (RDN). Giá trị dùng trong RDN phải phù hợp với thuộc tính đặt tên của entry, vì vậy không thể tùy tiện xóa giá trị đó như một giá trị thông thường.

## 2. Biểu diễn attribute trong LDIF

LDAP Data Interchange Format (**LDIF**) là định dạng văn bản để biểu diễn các entry và thay đổi LDAP. Một entry có thể được viết như sau:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
mail: lan.work@example.org
telephoneNumber: +84 28 1234 5678
```

Đọc ví dụ theo các quy tắc:

1. `dn` bắt đầu entry và xác định DN; các dòng tiếp theo biểu diễn attribute/value.
2. Dòng `mail: ...` được lặp lại hai lần nghĩa là attribute `mail` có **hai giá trị**. Đây là cách thể hiện nhiều giá trị trong LDIF, không phải ghép thành một chuỗi phân cách bằng dấu phẩy.
3. `cn` có hai giá trị tên hiển thị; `sn` trong entry mẫu chỉ có một giá trị. Việc **hiện có một giá trị** không tự chứng minh loại thuộc tính đó được schema đánh dấu `SINGLE-VALUE`.
4. Các dòng `objectClass` biểu diễn các giá trị của cùng một attribute `objectClass`.

LDIF còn có dạng `attribute:: BASE64` khi giá trị cần được biểu diễn bằng Base64, chẳng hạn dữ liệu nhị phân hoặc văn bản không phù hợp với dạng LDIF thuần. **Base64 là cách mã hóa biểu diễn, không phải cơ chế mã hóa bảo mật.** Khi đọc LDIF, không nên mặc định tất cả giá trị đều là chuỗi ASCII đơn giản.

## 3. Schema quyết định attribute được chứa giá trị gì

LDAP không xem mọi thuộc tính là những cặp `key → string` tùy ý. **Schema** định nghĩa loại thuộc tính và loại entry, trong đó có:

- **Attribute type:** tên hoặc OID, chẳng hạn `cn` hay `mail`.
- **Syntax:** dạng dữ liệu được chấp nhận, ví dụ chuỗi văn bản, số theo cú pháp chuyên biệt, DN hoặc dữ liệu nhị phân.
- **Matching rule:** cách máy chủ so sánh giá trị khi lọc và kiểm tra bằng nhau, chẳng hạn so sánh không phân biệt hoa/thường đối với một số thuộc tính văn bản.
- **`SINGLE-VALUE`:** nếu có thì một entry chỉ được phép có tối đa một giá trị của loại thuộc tính đó; nếu không có thì có thể chứa nhiều giá trị, miễn các ràng buộc khác cho phép.
- **Object class:** quy định nhóm thuộc tính **bắt buộc** (`MUST`) và **được phép** (`MAY`) trên entry thuộc lớp đó.

Hai câu hỏi về schema cần được tách rõ:

| Câu hỏi | Ràng buộc liên quan |
| --- | --- |
| Entry thuộc loại này **có được khai báo** `mail` không? | `MUST` / `MAY` của object class |
| Nếu có `mail`, **được lưu bao nhiêu giá trị**? | Ràng buộc `SINGLE-VALUE` của attribute type và chính sách máy chủ |

Chẳng hạn, entry `inetOrgPerson` thường cho phép lưu `mail`, trong khi các thuộc tính `cn` và `sn` được yêu cầu thông qua lớp cha `person`. Việc `cn` là thuộc tính bắt buộc không có nghĩa nó chỉ chứa được một tên.

**Schema và cấu hình máy chủ là nguồn quyết định cuối cùng.** Không nên suy ra một thuộc tính chắc chắn có một hay nhiều giá trị chỉ từ tên, giao diện quản trị hoặc một entry mẫu. Những triển khai khác nhau có thể có schema mở rộng hoặc quy tắc nghiệp vụ riêng.

## 4. Multi-valued attribute là một tập giá trị

Với LDAP, nhiều giá trị của một attribute thông thường được hiểu theo **ngữ nghĩa tập hợp**:

```text
mail = {
  "lan@example.org",
  "lan.work@example.org"
}
```

Ba hệ quả thực tế rất quan trọng:

**Không có thứ tự ổn định.** Thứ tự các dòng trong LDIF hay thứ tự phần tử do API trả về không phải thứ tự ưu tiên được LDAP bảo đảm. Đừng chọn `getStringAttribute("mail")` rồi mặc định đó là “email chính” nếu `mail` có nhiều giá trị. Nếu cần email chính, hãy thiết kế quy tắc nghiệp vụ hoặc thuộc tính riêng được schema cho phép.

**Không chấp nhận những giá trị trùng nhau theo matching rule.** Khi thêm một giá trị đã tồn tại về mặt so sánh LDAP, máy chủ có thể trả lỗi `attributeOrValueExists`. Ví dụ với attribute dùng quy tắc so sánh không phân biệt chữ hoa/chữ thường, `Lan Nguyen` và `LAN NGUYEN` có thể được xem là cùng giá trị. Điều này phụ thuộc matching rule của từng attribute; không áp dụng một cách so sánh chuỗi cho mọi thuộc tính.

**Thiếu attribute khác với một chuỗi rỗng.** Một entry có thể không chứa `mail`. Đây không phải cùng trạng thái với một `mail` có giá trị rỗng; giá trị rỗng có được chấp nhận hay không còn phụ thuộc syntax và schema. Khi không còn giá trị nào, thông thường attribute được xóa khỏi entry.

Một thuộc tính nhiều giá trị cũng **không** có nghĩa là “mỗi value là một object con”. Ví dụ hai địa chỉ email chỉ là hai giá trị thuộc tính của cùng entry. Nếu mỗi địa chỉ cần nhiều thông tin riêng như loại, trạng thái xác minh hay thời gian hiệu lực, cấu trúc LDAP/schema phải được thiết kế phù hợp.

## 5. Tìm kiếm theo một giá trị trong tập

Giả sử `mail` có hai địa chỉ như ví dụ. Bộ lọc LDAP:

```ldap
(mail=lan.work@example.org)
```

sẽ khớp entry nếu **có ít nhất một** giá trị `mail` đáp ứng phép so khớp của attribute. Không cần viết bộ lọc riêng để “duyệt từng phần tử”. Các ví dụ khác:

| Bộ lọc | Ý nghĩa |
| --- | --- |
| `(mail=lan@example.org)` | Tìm entry có giá trị `mail` tương ứng |
| `(mail=*)` | Tìm entry có attribute `mail` |
| `(&(objectClass=inetOrgPerson)(mail=lan@example.org))` | Chỉ lấy những entry phù hợp cả hai điều kiện |

Để khớp **một trong hai** địa chỉ, dùng bộ lọc OR với ký tự `|`:

```ldap
(|(mail=lan@example.org)(mail=lan.work@example.org))
```

> Lưu ý: Kết quả so khớp còn phụ thuộc matching rule, quyền truy cập và cấu hình tìm kiếm của máy chủ. Ví dụ trên dùng các giá trị cố định; với đầu vào người dùng, cần dùng API xây dựng filter an toàn để xử lý các ký tự đặc biệt trong LDAP filter.

## 6. Đọc đầy đủ các giá trị bằng Spring LDAP

Trong Spring LDAP, `LdapTemplate` giúp tìm kiếm entry; `DirContextOperations` cung cấp các phương thức đọc attribute. Ví dụ sau giả định `LdapTemplate` đã được cấu hình với `ContextSource` và base DN `dc=example,dc=org`:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<List<String>> findEmailValuesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (ContextMapper<List<String>>) context -> {
                DirContextOperations entry = (DirContextOperations) context;
                String[] mails = entry.getStringAttributes("mail");
                return mails == null
                    ? Collections.emptyList()
                    : Arrays.asList(mails);
            }
        );
    }
}
```

Giải thích:

- `query().base("ou=people")` tìm dưới nhánh người dùng, tương đối với base DN đã cấu hình. `where("uid").is(uid)` xây dựng điều kiện theo giá trị đầu vào thông qua query builder.
- `getStringAttributes("mail")` đọc **tất cả** giá trị của attribute dạng chuỗi. Phương thức này phù hợp với `mail`; không dùng nó để diễn giải thuộc tính nhị phân như `jpegPhoto`.
- Nếu `mail` vắng mặt, ví dụ trả về danh sách rỗng cho entry đó. Đừng giả định attribute tùy chọn luôn tồn tại.
- Kết quả ngoài cùng là `List<List<String>>` vì tìm kiếm có thể trả nhiều entry; mỗi danh sách bên trong là tập các email của **một entry**. Không dựa vào thứ tự các email trong danh sách.

Với các thuộc tính nhị phân, cần dùng API truy cập giá trị đúng kiểu (chẳng hạn `byte[]`), thay vì ép tất cả về `String`. Khi ánh xạ sang DTO, hãy thể hiện rõ trường một giá trị và trường nhiều giá trị (ví dụ `String` so với `List<String>`).

## 7. Thêm, xóa và thay thế value: hiểu đúng phạm vi cập nhật

Các thao tác cập nhật thuộc tính của JNDI cũng được sử dụng qua `LdapTemplate`. Khi entry đã có hai giá trị `mail`, bạn có thể thêm **một giá trị mới**:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.support.LdapUtils;

ldapTemplate.modifyAttributes(
    LdapUtils.newLdapName("uid=lan,ou=people"),
    new ModificationItem[] {
        new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("mail", "lan.alt@example.org")
        )
    }
);
```

Đoạn code dùng DN **tương đối** với base DN `dc=example,dc=org` đã cấu hình. Điều kiện tiên quyết là schema cho phép thêm giá trị và tài khoản kết nối có quyền sửa entry.

Nếu chỉ muốn bỏ một giá trị xác định:

```java
ldapTemplate.modifyAttributes(
    LdapUtils.newLdapName("uid=lan,ou=people"),
    new ModificationItem[] {
        new ModificationItem(
            DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("mail", "lan.work@example.org")
        )
    }
);
```

Phân biệt ba loại sửa đổi:

| Thao tác JNDI | Tác động mong đợi |
| --- | --- |
| `ADD_ATTRIBUTE` với một value | Thêm value vào attribute nếu hợp lệ và chưa trùng |
| `REMOVE_ATTRIBUTE` với value cụ thể | Xóa đúng value được chỉ định |
| `REPLACE_ATTRIBUTE` | Thay **toàn bộ tập giá trị** của attribute bằng những giá trị cung cấp |

**Cẩn thận với `REPLACE_ATTRIBUTE`:** nếu ban đầu có hai email và chỉ truyền một email, email còn lại sẽ bị mất khỏi attribute. Tương tự, thao tác xóa attribute mà **không chỉ ra value cụ thể** có thể xóa toàn bộ attribute. Hãy xác định rõ yêu cầu là “thêm một phần tử”, “bỏ một phần tử” hay “thay toàn bộ tập”.

Trên môi trường thật, ghi LDAP nên đi qua kết nối TLS bảo vệ thông tin đăng nhập và dữ liệu; bind account chỉ được cấp quyền cần thiết. Nếu máy chủ trả lỗi `attributeOrValueExists`, `constraintViolation`, `objectClassViolation` hoặc `insufficientAccessRights`, cần kiểm tra giá trị hiện có, schema và ACL tương ứng, không tự động ghi đè dữ liệu để bỏ qua lỗi.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hai dòng `mail` trong LDIF là hai attribute khác nhau | Chúng là hai value của cùng attribute `mail` |
| Attribute xuất hiện một lần nghĩa là `SINGLE-VALUE` | Cardinality do schema quyết định, không suy ra từ dữ liệu hiện tại |
| Giá trị đầu tiên là giá trị chính | Multi-valued attribute không bảo đảm thứ tự |
| Có thể phân tách chuỗi `mail` bằng dấu phẩy để tạo nhiều email | Mỗi email là một value độc lập; dấu phẩy chỉ là ký tự trong một chuỗi nếu syntax cho phép |
| So sánh các value luôn phân biệt hoa/thường | Quy tắc so sánh do matching rule quyết định |
| `REPLACE_ATTRIBUTE` chỉ thay một phần tử | Nó có thể thay toàn bộ tập giá trị, làm mất các value khác |
| Mọi attribute đều là chuỗi | LDAP có nhiều syntax, bao gồm cả giá trị nhị phân |
| Có thể xóa `uid: lan` dù RDN đang là `uid=lan` | Thuộc tính/giá trị đặt tên liên quan đến DN; đổi tên entry phải dùng thao tác phù hợp |

## 9. Bài thực hành tự kiểm tra

Cho entry LDIF:

```ldif
dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Minh Tran
cn: Tran Van Minh
sn: Tran
mail: minh@example.org
mail: minh.team@example.org
```

Hãy thử trả lời trước khi xem gợi ý:

1. Entry này có bao nhiêu **giá trị** `cn` và bao nhiêu giá trị `mail`? Có bao nhiêu attribute type khác nhau?
2. Bộ lọc `(mail=minh.team@example.org)` có thể khớp entry không? Tại sao?
3. Nếu cập nhật `mail` bằng `REPLACE_ATTRIBUTE` chỉ gồm `minh.new@example.org`, giá trị `minh@example.org` còn không?
4. Có thể kết luận `uid` là loại attribute `SINGLE-VALUE` chỉ từ entry trên không?
5. Trong Spring LDAP, vì sao nên đọc `mail` bằng `getStringAttributes`?

**Đáp án và giải thích:**

1. `cn` có 2 value; `mail` có 2 value. Có 5 attribute type: `objectClass`, `uid`, `cn`, `sn`, `mail`. `dn` là tên phân biệt trong LDIF, không tính như attribute thường của entry.
2. Có, vì giá trị được tìm là một phần tử trong tập giá trị `mail`, giả sử máy chủ cho phép truy cập và matching rule phù hợp.
3. Không. Thay thế toàn bộ `mail` bằng tập mới chỉ chứa `minh.new@example.org` sẽ loại bỏ cả hai email cũ.
4. Không. Phải xem định nghĩa attribute type trong schema.
5. Vì `mail` có thể có nhiều value; đọc một giá trị sẽ bỏ sót dữ liệu và không có bảo đảm value nào đứng đầu.

## 10. Ghi nhớ và tài liệu tham khảo

Một entry LDAP được nhận diện bằng DN và chứa các attribute. **Attribute type** mô tả ý nghĩa, kiểu và quy tắc của thuộc tính; **attribute value** là từng giá trị cụ thể. Attribute nhiều giá trị chứa một tập các value, không có thứ tự được bảo đảm. Schema quyết định thuộc tính nào được phép có trên entry, cách so sánh giá trị và liệu thuộc tính bị giới hạn bởi `SINGLE-VALUE` hay không.

Khi sử dụng Spring LDAP, hãy đọc đầy đủ giá trị bằng API phù hợp, xây bộ lọc qua query builder, và phân biệt rõ thao tác **thêm một value**, **xóa một value** với **thay toàn bộ attribute**. Đây là cơ sở cho các bài tiếp theo về schema, filter, tìm kiếm, ODM và xử lý entry an toàn.

Tìm hiểu thêm:

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute, schema và attribute type.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): syntax và quy tắc so khớp.
- [RFC 2849 — LDAP Data Interchange Format](https://www.rfc-editor.org/rfc/rfc2849): biểu diễn LDIF.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, truy vấn và ánh xạ dữ liệu.
