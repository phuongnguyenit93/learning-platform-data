# Object class và các thuộc tính bắt buộc hoặc tùy chọn trong LDAP

Khi tạo một người dùng trong LDAP, chúng ta không thể tùy ý gắn mọi thuộc tính vào entry. Máy chủ đối chiếu entry với **schema** để quyết định entry thuộc loại đối tượng nào, phải có những thuộc tính nào và được phép có thêm những thuộc tính nào. Trong ứng dụng Spring LDAP, hiểu đúng quy tắc này giúp tránh lỗi khi gọi `LdapTemplate.bind(...)`, cập nhật entry và ánh xạ dữ liệu từ thư mục.

Sau bài này, bạn có thể:

- Phân biệt `objectClass` với thuộc tính thông thường như `cn`, `sn`, `uid` và `mail`.
- Giải thích `MUST`, `MAY`, `SUP` và ba loại object class: `ABSTRACT`, `STRUCTURAL`, `AUXILIARY`.
- Xác định tập thuộc tính bắt buộc/được phép của một entry có nhiều object class, kể cả các lớp kế thừa.
- Viết LDIF và tạo entry bằng Spring LDAP phù hợp schema; nhận diện lỗi thường gặp và cách kiểm tra schema thực tế.

## 1. Object class là gì?

Trong LDAP, một **entry** là một tập thuộc tính được định danh bởi **DN** (*Distinguished Name*). Mỗi thuộc tính có tên (attribute type) và một hoặc nhiều giá trị nếu schema cho phép. Ví dụ:

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
```

Ở đây:

- `dn` định vị entry trong cây thư mục. Thành phần `uid=an.nguyen` là RDN (*Relative Distinguished Name*) của entry.
- `objectClass` là **thuộc tính nhiều giá trị** liệt kê những lớp đối tượng áp dụng cho entry. Mỗi lớp đóng góp các ràng buộc schema.
- `cn`, `sn`, `uid`, `givenName`, `mail` là những thuộc tính dữ liệu. Từng thuộc tính cũng có định nghĩa schema riêng.
- `ou=people,dc=example,dc=org` là nhánh cha giả định đã tồn tại. Entry `ou=people` có schema của riêng nó, không phải một `inetOrgPerson`.

Một object class không phải lớp Java và cũng không phải một nhóm quyền. Nó là **định nghĩa kiểu entry trong schema LDAP**, thường chứa tên, OID, lớp cha, loại class và danh sách thuộc tính `MUST`/`MAY`. Danh sách `objectClass` còn rất hữu ích để lọc khi tìm kiếm, chẳng hạn `(objectClass=inetOrgPerson)`.

## 2. Ba loại object class

| Loại | Vai trò | Ví dụ | Cách sử dụng |
| --- | --- | --- | --- |
| `ABSTRACT` | Làm lớp gốc để các class khác kế thừa, không trực tiếp xác định kiểu entry cụ thể | `top` | Thường xuất hiện trong chuỗi kế thừa |
| `STRUCTURAL` | Xác định bản chất chính của entry trong cây thư mục | `person`, `organizationalPerson`, `inetOrgPerson`, `organizationalUnit` | Entry thông thường có một **chuỗi** structural class, từ lớp cha đến lớp con cụ thể nhất |
| `AUXILIARY` | Bổ sung đặc tính, thuộc tính hoặc quy tắc cho một entry đã có structural class | `posixAccount` trong schema RFC 2307 | Chỉ thêm nếu server hỗ trợ và schema/quy tắc nội dung cho phép |

Ví dụ, chuỗi kế thừa phổ biến cho người dùng là:

```text
top                         (ABSTRACT)
└── person                  (STRUCTURAL)
    └── organizationalPerson (STRUCTURAL)
        └── inetOrgPerson    (STRUCTURAL)
```

`inetOrgPerson` kế thừa `organizationalPerson`, lớp này kế thừa `person`, và `person` kế thừa `top`. Mặc dù LDIF ví dụ liệt kê bốn giá trị `objectClass`, chúng cùng nằm trên **một nhánh kế thừa structural hợp lệ**. Không thể tùy tiện ghép hai structural class không có quan hệ kế thừa, ví dụ `inetOrgPerson` và `organizationalUnit`, để biến một entry thành cả người dùng lẫn đơn vị tổ chức.

Một lớp auxiliary như `posixAccount` có thể bổ sung những thuộc tính phục vụ tài khoản POSIX vào entry người dùng **khi được schema server chấp nhận**. Không nên thêm object class chỉ để vượt qua kiểm tra thuộc tính; mọi object class đều có thể kéo theo yêu cầu mới.

## 3. `MUST`, `MAY` và `SUP` quyết định điều gì?

Xem một định nghĩa schema rút gọn của object class `person`:

```text
( 2.5.6.6 NAME 'person'
  SUP top STRUCTURAL
  MUST ( sn $ cn )
  MAY ( userPassword $ telephoneNumber $ seeAlso $ description ) )
```

| Thành phần | Ý nghĩa | Hệ quả khi tạo/cập nhật entry |
| --- | --- | --- |
| `NAME 'person'` | Tên có thể dùng khi khai báo `objectClass` | `objectClass: person` |
| `2.5.6.6` | OID định danh duy nhất định nghĩa class | Giúp phân biệt các định nghĩa schema |
| `SUP top` | `person` kế thừa `top` | Nhận các quy tắc của lớp cha |
| `STRUCTURAL` | Đây là một structural class | Góp phần xác định loại cấu trúc của entry |
| `MUST ( sn $ cn )` | Bắt buộc có giá trị cho `sn` và `cn` | Thiếu một trong hai có thể khiến thao tác bị từ chối |
| `MAY ( ... )` | Cho phép các thuộc tính liệt kê xuất hiện | Không cần có chúng nếu ứng dụng không dùng |

Trong cú pháp schema, dấu `$` ngăn cách các tên thuộc tính; nó **không** có nghĩa là phép toán trong Java hoặc LDAP filter.

Điểm quan trọng: **`MAY` nghĩa là được phép, không có nghĩa là mọi thuộc tính không nằm trong `MUST` đều được phép**. Ví dụ, `mail` không có trong `MUST` hoặc `MAY` của riêng `person`. Một entry chỉ dùng `person` sẽ không tự động được phép chứa `mail`; muốn lưu `mail` thường phải dùng một object class phù hợp như `inetOrgPerson`.

### Quy tắc kế thừa

Đối với một entry, server xét object class cụ thể cùng các lớp cha và auxiliary class được phép sử dụng:

- **Thuộc tính bắt buộc hữu hiệu** là hợp các thuộc tính `MUST` được khai báo trên các class áp dụng, bao gồm class kế thừa.
- **Thuộc tính được phép hữu hiệu** gồm tập bắt buộc đó và các thuộc tính `MAY` tương ứng, có thể chịu thêm DIT content rule hoặc quy tắc riêng của server.
- Các thuộc tính vận hành (*operational attributes*) do server quản lý, ví dụ `createTimestamp` hoặc `structuralObjectClass`, có cơ chế riêng; không nên cố gán chúng như dữ liệu người dùng.

Với `inetOrgPerson`, các thuộc tính `cn` và `sn` **vẫn bắt buộc**, dù class này không nhất thiết liệt kê lại chúng trong `MUST`: yêu cầu được kế thừa từ `person`. `mail`, `givenName`, `displayName` và `uid` là những thuộc tính thường được phép có nhưng không mặc nhiên bắt buộc đối với mọi `inetOrgPerson`.

| Object class | Thuộc tính bắt buộc tiêu biểu | Thuộc tính tùy chọn tiêu biểu |
| --- | --- | --- |
| `person` | `cn`, `sn` | `telephoneNumber`, `description` |
| `organizationalPerson` | Kế thừa `cn`, `sn` | `title`, `ou` và các thuộc tính kế thừa |
| `inetOrgPerson` | Kế thừa `cn`, `sn` | `uid`, `mail`, `givenName`, `displayName` và các thuộc tính kế thừa |
| `organizationalUnit` | `ou` | `description`, `telephoneNumber` |
| `groupOfNames` | `cn`, `member` | `description` |

Các dòng trong bảng minh họa những class phổ biến theo schema chuẩn, không phải toàn bộ danh sách thuộc tính. **Schema được cài trên máy chủ là nguồn quyết định**: OpenLDAP, 389 Directory Server, Active Directory và các môi trường tùy biến có thể có class hoặc ràng buộc khác nhau.

### `MUST` chưa phải tất cả các ràng buộc

Một attribute type còn có thể được quy định bởi:

- **Cú pháp** (`SYNTAX`): kiểu dữ liệu/biểu diễn hợp lệ, chẳng hạn giá trị chuỗi, số hoặc DN.
- **Số lượng giá trị** (`SINGLE-VALUE`): thuộc tính có được chứa nhiều giá trị không.
- **Quy tắc so khớp** (`EQUALITY`, `SUBSTR`, `ORDERING`): cách server so sánh, tìm kiếm thuộc tính.
- **Khả năng chỉnh sửa** (`NO-USER-MODIFICATION`) và quy tắc truy cập: ứng dụng có được gán hoặc nhìn thấy thuộc tính không.
- **Naming và DIT**: thuộc tính dùng trong RDN phải tương thích entry; vị trí của entry trong cây còn có thể chịu các ràng buộc DIT của server.

Vì vậy, `mail` thuộc `MAY` không đồng nghĩa mọi giá trị bất kỳ của `mail` đều hợp lệ, và `sn` là `MUST` không có nghĩa mọi người dùng đều được quyền đọc hoặc sửa nó.

## 4. Đọc một LDIF hợp lệ và ba trường hợp sai thường gặp

Ví dụ sau khai báo một người dùng thông dụng. `inetOrgPerson` cho phép lưu `uid` và `mail`; `person` trong chuỗi kế thừa bắt buộc `cn`, `sn`:

```ldif
dn: uid=an.nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an.nguyen
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

**Trường hợp 1 — Thiếu thuộc tính `MUST`:**

```ldif
dn: cn=An Nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
cn: An Nguyen
# Thieu sn
```

Entry vi phạm yêu cầu `sn` của `person`. Thông thường, server trả lỗi **LDAP result code 65 — `objectClassViolation`** khi thêm hoặc cập nhật entry làm hỏng ràng buộc object class.

**Trường hợp 2 — Thuộc tính không được class cho phép:**

```ldif
dn: cn=An Nguyen,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
cn: An Nguyen
sn: Nguyen
mail: an.nguyen@example.org
```

Nếu server chỉ áp dụng các định nghĩa class tương ứng ở đây và không có quy tắc mở rộng cho phép `mail`, entry trên cũng không hợp lệ. Một cách sửa đúng là chọn class thích hợp (chẳng hạn chuỗi `person` → `organizationalPerson` → `inetOrgPerson`) nếu entry thực sự là đối tượng kiểu đó.

**Trường hợp 3 — Thêm auxiliary class nhưng thiếu thuộc tính của nó:**

Một số schema cung cấp `posixAccount` để mô tả tài khoản POSIX, với các thuộc tính bắt buộc như `uid`, `cn`, `uidNumber`, `gidNumber`, `homeDirectory`. Nếu thêm `objectClass: posixAccount` mà không cung cấp đủ các thuộc tính đó, entry có thể bị từ chối, dù đã có đủ `cn` và `sn` cho `inetOrgPerson`. Việc sử dụng class này còn phụ thuộc schema đã nạp và quy tắc áp dụng auxiliary class của server.

Lưu ý: Một số máy chủ có tính năng tự thêm object class cha hoặc giá trị mặc định. Không nên dựa vào hành vi riêng đó khi thiết kế dữ liệu cần di chuyển giữa các directory server.

## 5. Áp dụng với `LdapTemplate` trong Spring LDAP

Spring LDAP cung cấp `DirContextAdapter` để gom các thuộc tính entry và `LdapTemplate` để thực hiện thao tác LDAP. Khi tạo entry, ứng dụng cần cung cấp đúng `objectClass` lẫn thuộc tính bắt buộc. Ví dụ bên dưới giả sử `LdapTemplate` đã được cấu hình qua `ContextSource` có base DN là `dc=example,dc=org`, và nhánh `ou=people` đã tồn tại.

```java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class PersonDirectoryService {
    private final LdapTemplate ldapTemplate;

    public PersonDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson() {
        // DN tương đối so với base DN của ContextSource.
        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "an.nguyen")
                .build();

        DirContextAdapter entry = new DirContextAdapter(relativeDn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });

        entry.setAttributeValue("uid", "an.nguyen");  // dung trong RDN
        entry.setAttributeValue("cn", "An Nguyen");  // MUST cua person
        entry.setAttributeValue("sn", "Nguyen");    // MUST cua person
        entry.setAttributeValue("mail", "an.nguyen@example.org"); // MAY

        ldapTemplate.bind(entry);
    }
}
```

`LdapNameBuilder` xây dựng DN có escape giá trị RDN phù hợp, giúp tránh ghép chuỗi DN thủ công. **Base DN chỉ đặt một lần**: nếu `ContextSource` đã có base `dc=example,dc=org`, đối số dùng với `LdapTemplate` ở ví dụ phải là DN *tương đối* `uid=an.nguyen,ou=people`, không lặp lại `dc=example,dc=org`.

Điều cần kiểm tra trong mã ứng dụng:

1. `objectClass` khớp mục đích của entry; các class structural liên quan bằng kế thừa.
2. Mọi `MUST` của class và lớp cha đều đã có giá trị; mọi attribute khác đều được schema cho phép.
3. Nếu RDN dùng `uid=an.nguyen`, thuộc tính `uid` của entry cũng có giá trị tương ứng.
4. `ContextSource` trỏ đúng server/base DN, dùng tài khoản có quyền tạo entry và kết nối bảo mật theo cấu hình hệ thống.

Nếu cần cập nhật một thuộc tính tùy chọn, có thể đọc entry vào `DirContextOperations`, thay đổi giá trị và gửi các thay đổi qua `modifyAttributes`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "an.nguyen")
        .build();

DirContextOperations entry = ldapTemplate.lookupContext(relativeDn);
entry.setAttributeValue("mail", "an.new@example.org");
ldapTemplate.modifyAttributes(entry);
```

Đoạn cập nhật giả định chạy trong cùng service có biến `ldapTemplate` từ ví dụ trước. Nếu xóa giá trị cuối cùng của `sn`, hoặc đặt thuộc tính không được class cho phép, thao tác cập nhật cũng có thể thất bại vì schema. **Validation phía Java không thay thế kiểm tra của LDAP server**; với schema thay đổi theo môi trường, phản hồi từ server vẫn là căn cứ cuối cùng.

## 6. Kiểm tra schema trên server thực tế

Không nên suy đoán danh sách `MUST`/`MAY` chỉ qua tên class. LDAP cung cấp *subschema subentry* để máy khách tra cứu định nghĩa object class và attribute type. Với công cụ dòng lệnh `ldapsearch`, có thể làm theo hai bước:

```bash
# 1. Tim DN chua schema tu Root DSE (neu server cho phep doc).
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -b "" -s base "(objectClass=*)" subschemaSubentry

# 2. Thay cn=Subschema bang DN nhan duoc o buoc 1.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -b "cn=Subschema" -s base "(objectClass=subschema)" \
  objectClasses attributeTypes
```

Trong kết quả `objectClasses`, tìm định nghĩa `NAME 'inetOrgPerson'` hoặc `NAME 'person'`, rồi lần theo `SUP` để tổng hợp yêu cầu. Trong `attributeTypes`, xem `SYNTAX`, `SINGLE-VALUE` và matching rules của các thuộc tính định dùng. Tên schema DN trong ví dụ có thể khác giữa các server. Máy chủ có thể yêu cầu bind có xác thực/quyền đọc schema; tùy môi trường hãy dùng cơ chế xác thực được cấp và kiểm tra chứng chỉ TLS hợp lệ.

Để kiểm tra một entry cụ thể mà ứng dụng đã có quyền đọc:

```bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -b "uid=an.nguyen,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" objectClass cn sn uid mail
```

Việc không thấy một thuộc tính trong kết quả tìm kiếm **chưa đủ để kết luận thuộc tính không tồn tại**: ACL có thể chặn quyền đọc, hoặc công cụ chỉ đang yêu cầu một tập thuộc tính nhất định. Để chẩn đoán lỗi ghi, cần đối chiếu schema, quyền của tài khoản bind và LDAP result code đi kèm lỗi.

## 7. Các lỗi dễ nhầm và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Thêm `inetOrgPerson` nhưng báo `objectClassViolation` (thường mã 65) | Thiếu `cn` hoặc `sn` kế thừa từ `person` | Tổng hợp `MUST` dọc chuỗi `SUP`; bổ sung giá trị bắt buộc |
| Có `cn`, `sn` nhưng thêm `mail` vẫn thất bại | Class hiện tại không cho phép `mail` | Chọn object class phù hợp với bản chất entry, xem `MAY` trên server |
| Gắn hai class structural không liên quan | Vi phạm quy tắc về structural class của entry | Chọn một nhánh structural hợp lệ; chỉ thêm auxiliary class được phép |
| Thêm `posixAccount` rồi không tạo được entry | Thiếu `uidNumber`, `gidNumber`, `homeDirectory` hoặc các `MUST` khác | Kiểm tra đầy đủ schema của auxiliary class và bổ sung giá trị |
| Gán thuộc tính đã có schema đúng nhưng vẫn bị từ chối | Sai syntax, vượt số giá trị, DN không hợp lệ hoặc không đủ quyền | Đối chiếu `attributeTypes`, DN, quyền truy cập và mã lỗi từ server |
| Dùng đúng DN tuyệt đối nhưng thao tác đến sai vị trí | Đã cấu hình base DN trên `ContextSource` và lại nối base vào DN tương đối | Kiểm tra cách `LdapTemplate` xử lý DN tương đối với base đã cấu hình |

Trong Spring LDAP, lỗi LDAP/JNDI được chuyển thành các ngoại lệ phù hợp của thư viện. Khi xử lý lỗi, hãy ghi nhận ngữ cảnh an toàn như DN, thao tác và mã kết quả LDAP để hỗ trợ chẩn đoán; tránh ghi mật khẩu hoặc giá trị thuộc tính nhạy cảm vào log.

## 8. Tự kiểm tra

**Câu 1.** Một entry `inetOrgPerson` có `cn` và `sn`, nhưng không có `mail`. Nó có vi phạm `MUST` không?

**Đáp án:** Không chỉ vì thiếu `mail`. Trong schema thông dụng, `mail` là `MAY` của `inetOrgPerson`; `cn` và `sn` là `MUST` kế thừa từ `person`. Entry vẫn phải thỏa các quy tắc khác của server, bao gồm thuộc tính đặt tên trong RDN.

**Câu 2.** Một entry chỉ có `objectClass: person`, đủ `cn` và `sn`, được thêm `mail` tùy ý không?

**Đáp án:** Không. Attribute không có trong `MUST` hay `MAY` hữu hiệu của class thì thường bị từ chối. Cần sử dụng schema/class thực sự cho phép `mail`.

**Câu 3.** Đã có entry `inetOrgPerson` hợp lệ; muốn thêm thuộc tính tự định nghĩa `employeeCode` thì chỉ cần gọi `setAttributeValue("employeeCode", ...)`?

**Đáp án:** Chưa đủ. Server cần biết định nghĩa attribute type và phải có object class/DIT content rule cho phép thuộc tính ấy. Thay đổi Java không thể tự mở rộng schema LDAP.

**Câu 4.** Vì sao thêm một auxiliary class có thể làm entry trước đó hợp lệ trở thành không hợp lệ?

**Đáp án:** Auxiliary class có thể đem theo `MUST` mới hoặc bị giới hạn bởi quy tắc schema. Mọi yêu cầu của các class đang áp dụng phải được thỏa đồng thời.

## Ghi nhớ

Hãy bắt đầu từ câu hỏi **entry này thực sự là kiểu đối tượng nào**, chọn một chuỗi structural class phù hợp, rồi lần theo `SUP` để thu thập toàn bộ `MUST` và `MAY`. Trước khi gọi `LdapTemplate.bind(...)` hoặc `modifyAttributes(...)`, xác minh rằng các thuộc tính bắt buộc có đủ giá trị và những thuộc tính khác được schema cho phép. `MAY` là quyền sử dụng thuộc tính, không phải giấy phép bỏ qua cú pháp, quyền truy cập hoặc các quy tắc của directory server.
