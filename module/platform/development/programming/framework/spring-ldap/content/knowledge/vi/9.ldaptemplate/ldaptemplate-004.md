# Bind, rebind và unbind với LdapTemplate

Trong Spring LDAP, `bind(...)`, `rebind(...)` và `unbind(...)` là ba thao tác cơ bản đối với **entry trong cây thư mục LDAP**: tạo mới, thay thế binding và xóa entry theo Distinguished Name (DN). Chúng bắt nguồn từ cách đặt tên trong JNDI, nên tên `bind` dễ bị nhầm với thao tác **LDAP Bind** dùng để xác thực kết nối.

Bài học thuộc chương **LdapTemplate** của SPRING_LDAP. Người học sẽ chuẩn bị DN và thuộc tính, thêm nhân viên vào thư mục, thay thế và xóa entry, phân biệt cập nhật từng thuộc tính với thay thế binding, xử lý lỗi schema/ACL và kiểm thử ghi trên LDAP server an toàn. Những nguyên tắc về DN, schema và quyền cũng áp dụng nếu ứng dụng chọn `LdapClient` hoặc ODM thay cho `LdapTemplate`.

## 1. Đừng nhầm hai loại “bind”

**LDAP protocol Bind** là thao tác xác thực một danh tính trên kết nối LDAP, thường bằng bind DN và password. Trong khi đó, **`LdapTemplate.bind(...)`** là phương thức Java dùng để thêm một entry vào thư mục.

| API hoặc thao tác | Chức năng | Khi nào dùng? |
| --- | --- | --- |
| LDAP protocol Bind | Xác thực danh tính trên kết nối | Khi ứng dụng kết nối bằng tài khoản dịch vụ hoặc thử xác thực người dùng |
| `LdapTemplate.bind(...)` | Tạo entry tại DN xác định | Tạo nhân viên, nhóm hoặc OU mới |
| `LdapTemplate.rebind(...)` | Thay binding/entry tại tên bằng dữ liệu cung cấp | Chỉ khi muốn và kiểm soát được việc thay thế |
| `LdapTemplate.unbind(...)` | Xóa entry khỏi DIT | Xóa entry được phép, thông thường là leaf entry |
| `LdapTemplate.modifyAttributes(...)` | Sửa attribute có chọn lọc | Đổi email, số điện thoại, thuộc tính trạng thái |
| `LdapTemplate.rename(...)` | Đổi RDN hoặc di chuyển entry theo khả năng server | Đổi tên định danh hoặc OU |

Ví dụ `LdapContextSource` dùng credential của tài khoản `cn=app-writer,ou=services,dc=example,dc=org` để **xác thực kết nối**. Sau đó service gọi `ldapTemplate.bind(newPerson)` để **thêm entry** `uid=binh`; đây là một thao tác nghiệp vụ khác.

Đặc biệt, **không gọi `ldapTemplate.bind(...)` để đăng nhập người dùng**. Muốn xác thực password của người dùng cuối, sử dụng `authenticate(...)`, bind xác thực phù hợp hoặc tích hợp Spring Security LDAP với kết nối TLS.

## 2. Cấu trúc DIT cho các ví dụ

Giả sử server LDAP có cây:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=an
├── ou=groups
│   └── cn=developers
└── ou=services
    └── cn=app-writer
~~~

Entry nhân viên An có dạng:

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

| Khái niệm | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| DN | `uid=an,ou=people,dc=example,dc=org` | Tên đầy đủ định vị entry |
| RDN | `uid=an` | Thành phần tên phân biệt entry với các entry cùng cha |
| Parent | `ou=people,dc=example,dc=org` | Entry cha cần tồn tại trước khi tạo entry con |
| Attributes | `uid`, `cn`, `sn`, `mail` | Dữ liệu của entry |
| Object classes | `person`, `inetOrgPerson`, v.v. | Quy định những thuộc tính bắt buộc/được phép |

Schema LDAP chuẩn thông dụng yêu cầu `cn` và `sn` cho `person`, nên chúng cũng là bắt buộc với `inetOrgPerson` qua chuỗi kế thừa. `mail` thường là tùy chọn. Thuộc tính `uid` ở ví dụ cần có để phản ánh RDN `uid=an`, dù nó không phải MUST theo class `inetOrgPerson` thông thường.

Ta giả sử `LdapContextSource` có base DN `dc=example,dc=org`. Khi gọi `LdapTemplate`, các DN bên dưới được viết **tương đối với base**:

| DN truyền trong Java | DN đầy đủ trên server |
| --- | --- |
| `ou=people` | `ou=people,dc=example,dc=org` |
| `uid=an,ou=people` | `uid=an,ou=people,dc=example,dc=org` |
| `uid=binh,ou=people` | `uid=binh,ou=people,dc=example,dc=org` |

Nếu đã đặt base `dc=example,dc=org`, không nên lặp lại hậu tố này trong DN của thao tác thông thường; nếu không có thể tạo ra một DN sai và gặp `noSuchObject`.

## 3. Vị trí của các phương thức trong Spring LDAP

~~~mermaid
flowchart TD
    A["Service nghiệp vụ"] --> B["LdapTemplate"]
    B --> C["ContextSource / LdapContextSource"]
    C --> D["JNDI DirContext"]
    D --> E[("LDAP server")]
    E --> F{"DN, schema, quyền và chính sách hợp lệ?"}
    F -->|Có| G["Tạo, thay hoặc xóa entry"]
    F -->|Không| H["LDAP result code / exception"]
~~~

`ContextSource` chịu trách nhiệm cấp ngữ cảnh kết nối với URL, base DN và danh tính bind. `LdapTemplate` gọi thao tác JNDI phù hợp, quản lý lấy/trả context và chuyển đổi nhiều loại exception. **LDAP server** vẫn quyết định thao tác có được thực hiện hay không dựa trên ACL, schema, cấu trúc DIT và quy tắc riêng.

Một tài khoản bind chỉ có quyền đọc có thể thực hiện `search` thành công nhưng bị từ chối khi gọi `bind`, `rebind` hoặc `unbind`. Tên gọi `getReadWriteContext()` cũng không tự cấp quyền ghi nếu ACL không cho phép.

## 4. `bind(...)`: tạo entry mới

Khi thêm nhân viên Bình, yêu cầu chuẩn bị:

1. DN mới: `uid=binh,ou=people` tương đối với `ContextSource.base`.
2. Entry cha `ou=people` đã có trên server.
3. `objectClass` phù hợp với schema, chẳng hạn chuỗi `inetOrgPerson`.
4. Có `cn` và `sn` vì chúng là thuộc tính MUST được kế thừa.
5. Có `uid: binh` phù hợp RDN `uid=binh`.
6. Tài khoản dịch vụ có quyền thêm entry tại nhánh đó.

Ví dụ Java:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryPersonWriter {

    private final LdapTemplate ldapTemplate;

    public DirectoryPersonWriter(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void createPerson(
            String uid, String commonName, String surname, String email) {

        Name dn = personDn(uid);

        if (commonName == null || commonName.isBlank()
                || surname == null || surname.isBlank()) {
            throw new IllegalArgumentException("cn and sn are required");
        }

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
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

    private Name personDn(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }

        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }
}
~~~

Giải thích:

- `LdapNameBuilder` tạo DN và escape ký tự đặc biệt của **giá trị RDN**; tránh nối trực tiếp `"uid=" + uid + ",ou=people"`.
- `DirContextAdapter` lưu DN và tập thuộc tính sẽ được gửi khi tạo entry.
- `ldapTemplate.bind(entry)` thể hiện yêu cầu thêm một entry tại DN đó.
- `mail` chỉ được thêm nếu có dữ liệu; schema và chính sách nghiệp vụ có thể bổ sung ràng buộc.
- Validation phía Java giúp báo lỗi sớm; server mới là nơi cuối cùng kiểm tra schema, ACL và naming.

Sau khi tạo thành công, entry có thể có nội dung:

~~~ldif
dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Tran Van Binh
sn: Tran
mail: binh@example.org
~~~

### Nếu DN đã tồn tại thì sao?

Tạo lại một entry có cùng DN thường khiến server trả về `entryAlreadyExists (68)`. `bind(...)` **không mặc nhiên là upsert**. Nếu API nghiệp vụ muốn tạo trùng trả về “đã tồn tại”, hãy xử lý lỗi đó riêng; không tự đổi lỗi tạo trùng thành `rebind(...)` vì việc thay thế có thể ghi đè thuộc tính hợp lệ của entry đã tồn tại.

### Nếu parent chưa tồn tại?

LDAP không tự sinh mọi OU cha. Nếu `ou=people` không tồn tại, việc tạo `uid=binh,ou=people` thường thất bại với mã `noSuchObject (32)`. Cần quản lý cây DIT, tạo parent hợp lệ trước, đồng thời kiểm tra quyền add theo ACL.

## 5. `rebind(...)`: thay thế binding có chủ đích

Khác với `bind` tạo mới, `rebind` là thao tác từ mô hình JNDI nhằm **thay binding tại một tên bằng đối tượng/dữ liệu mới**. Không nên hiểu nó như “sửa đúng một thuộc tính” hoặc “thêm field mà không ảnh hưởng field cũ”.

Ví dụ thay thế dữ liệu nhân viên Bình đã được ứng dụng quản lý đầy đủ (đặt phương thức sau trong lớp đã có `ldapTemplate` và `personDn(...)` từ mục 4):

~~~java
public void replacePerson(
        String uid, String commonName, String surname, String email) {

    Name dn = personDn(uid);
    if (commonName == null || commonName.isBlank()
            || surname == null || surname.isBlank()) {
        throw new IllegalArgumentException("cn and sn are required");
    }

    DirContextAdapter replacement = new DirContextAdapter(dn);
    replacement.setAttributeValues("objectClass", new String[]{
            "top", "person", "organizationalPerson", "inetOrgPerson"
    });
    replacement.setAttributeValue("uid", uid);
    replacement.setAttributeValue("cn", commonName);
    replacement.setAttributeValue("sn", surname);

    if (email != null && !email.isBlank()) {
        replacement.setAttributeValue("mail", email);
    }

    ldapTemplate.rebind(replacement);
}
~~~

Với bài toán thay thế, cần kiểm tra kỹ:

- **Tập thuộc tính gửi lên**: nếu entry còn `telephoneNumber`, `description` hoặc thuộc tính mà dịch vụ khác quản lý, việc chỉ gửi `cn`, `sn`, `mail` có thể làm mất hoặc thay đổi dữ liệu đó tùy ngữ nghĩa rebind của provider/server.
- **Dữ liệu bắt buộc**: schema vẫn yêu cầu các thuộc tính MUST và RDN hợp lệ.
- **Quyền thao tác**: ACL có thể cho sửa một attribute nhưng không cho phép thay thế nội dung entry.
- **Trạng thái entry ban đầu**: ngữ nghĩa JNDI của rebind khác một phép cập nhật có điều kiện “chỉ khi entry tồn tại”; cần kiểm tra hành vi khi DN chưa có với provider và phiên bản cụ thể.
- **Cạnh tranh đồng thời**: giữa lúc ứng dụng đọc và gửi dữ liệu thay thế, một tác vụ khác có thể đã cập nhật entry.

Không có một *LDAP rebind operation* độc lập tương đương chính xác về tên với giao thức LDAP Bind xác thực: `rebind` thuộc cách trừu tượng hóa naming của JNDI/Spring LDAP. Provider có thể thực hiện những thao tác LDAP phù hợp để đạt ngữ nghĩa đó; không tự suy ra tính nguyên tử hoặc tác động phụ của nó trên mọi server.

### Ví dụ nguy cơ ghi đè dữ liệu

Entry hiện có:

~~~text
uid: binh
cn: Tran Van Binh
sn: Tran
mail: binh@example.org
telephoneNumber: +84-28-123456
description: Managed by HR
~~~

Request HTTP chỉ muốn đổi email thành `binh.new@example.org`. Nếu ứng dụng tạo đối tượng replacement chỉ chứa `uid`, `cn`, `sn` và `mail` rồi gọi `rebind(...)`, thì `telephoneNumber` và `description` **có nguy cơ không được bảo toàn**. Với yêu cầu chỉ sửa email, chọn API sửa thuộc tính có phạm vi rõ ràng.

## 6. Sửa thuộc tính bằng `modifyAttributes(...)`

Spring LDAP hỗ trợ đọc entry rồi cập nhật các thuộc tính được thay đổi. Khi chỉ cần sửa một trường, cách này thường phù hợp hơn rebind:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;

// Trong lớp có ldapTemplate và personDn(...) như mục 4:
public void updateEmail(String uid, String newEmail) {
    if (newEmail == null || newEmail.isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    Name dn = personDn(uid);
    DirContextOperations entry = ldapTemplate.lookupContext(dn);
    entry.setAttributeValue("mail", newEmail);
    ldapTemplate.modifyAttributes(entry);
}
~~~

Ý nghĩa từng bước:

1. `lookupContext(dn)` lấy đối tượng context của entry hiện có.
2. `setAttributeValue("mail", ...)` ghi nhận thay đổi trong context.
3. `modifyAttributes(entry)` gửi thay đổi phù hợp đến LDAP server.
4. Các thuộc tính không được thay đổi không phải là mục tiêu của lần cập nhật này.
5. Server vẫn kiểm tra ACL, attribute syntax, tính đơn trị và các ràng buộc khác.

**Lưu ý về đồng thời:** cách đọc rồi sửa không tự động chống tình huống hai request cùng cập nhật. Nếu nghiệp vụ đòi hỏi phát hiện xung đột, cần cơ chế kiểm soát phiên bản/điều kiện theo khả năng LDAP server và hợp đồng cập nhật của ứng dụng.

Không nên nhầm `modifyAttributes` với `rename`. Khi đổi `uid=binh` thành `uid=binh2` hoặc chuyển sang OU khác, DN thay đổi và có thể ảnh hưởng các tham chiếu; hãy sử dụng cơ chế Modify DN hoặc `rename(...)` thích hợp.

## 7. `unbind(...)`: xóa entry

`LdapTemplate.unbind(...)` loại bỏ entry tại DN được chỉ định. Với người dùng Bình:

~~~java
public void deletePerson(String uid) {
    Name dn = personDn(uid); // uid=binh,ou=people
    ldapTemplate.unbind(dn);
}
~~~

Giả sử `ContextSource.base` là `dc=example,dc=org`, thao tác xóa nhắm tới:

~~~text
uid=binh,ou=people,dc=example,dc=org
~~~

Điều kiện thường gặp:

- Entry tồn tại tại DN đó.
- Tài khoản dịch vụ có quyền xóa entry.
- Entry đang là **leaf** (không có con).
- Server không đặt thêm chính sách hoặc ràng buộc ngăn xóa.

### Không xóa trực tiếp container còn con

Nếu cây như sau:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=an
    └── uid=binh
~~~

thì `ldapTemplate.unbind("ou=people")` thông thường bị từ chối vì entry `ou=people` còn có con. LDAP result code thường gặp là `notAllowedOnNonLeaf (66)`.

Không coi xóa OU là một phép xóa đệ quy mặc định. Nếu ứng dụng cần xóa cả nhánh, phải có nghiệp vụ riêng để xác nhận phạm vi, xử lý entry con và bảo vệ dữ liệu. Một số server hỗ trợ cơ chế subtree delete riêng, nhưng không nên mặc định server nào cũng hỗ trợ hoặc cho phép.

### Xóa entry không tự bảo đảm xóa tham chiếu nhóm

Giả sử nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: developers
member: uid=binh,ou=people,dc=example,dc=org
~~~

Việc xóa `uid=binh` không tự đồng nghĩa thuộc tính `member` ở nhóm được làm sạch. Điều đó phụ thuộc cơ chế duy trì tính toàn vẹn tham chiếu mà server được cấu hình. Cần xem ảnh hưởng tới nhóm, policy cấp quyền, audit và các hệ thống lưu DN.

## 8. Chọn API theo yêu cầu nghiệp vụ

| Yêu cầu | Phương thức nên dùng | Vì sao |
| --- | --- | --- |
| Tạo mới một người dùng chưa tồn tại | `bind(...)` | Thêm entry tại DN |
| Chỉ sửa email hoặc số điện thoại | `modifyAttributes(...)` | Cập nhật thuộc tính có chọn lọc |
| Thay toàn bộ binding khi có bộ dữ liệu thay thế được kiểm soát | `rebind(...)` | Diễn đạt ý định thay thế; cần kiểm tra provider |
| Xóa một leaf entry được phép | `unbind(...)` | Xóa theo DN |
| Đổi RDN hoặc chuyển OU | `rename(...)` / Modify DN | Thay tên/vị trí entry |
| Kiểm tra mật khẩu người dùng | `authenticate(...)` hoặc cơ chế LDAP Bind | Xác thực, không phải CRUD entry |

Không có một API “tốt nhất cho mọi trường hợp”. Việc chọn phương thức phải phản ánh **ngữ nghĩa nghiệp vụ** và quyền cụ thể của tài khoản LDAP; đừng sử dụng `rebind` chỉ vì muốn tránh xử lý lỗi entry đã tồn tại.
## 9. Đưa thao tác vào service: kiểm soát DN và dữ liệu

Trong ứng dụng thật, controller không nên tự nhận DN bất kỳ từ request rồi đưa thẳng vào `unbind(...)` hoặc `rebind(...)`. Một tầng service rõ ràng giúp giới hạn thao tác trong nhánh `ou=people` và chuyển đổi tham số nghiệp vụ thành DN hợp lệ.

Ví dụ service kiểm soát ba thao tác chính:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class EmployeeDirectoryService {

    private final LdapTemplate ldapTemplate;

    public EmployeeDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void create(String uid, String cn, String sn) {
        validatePerson(uid, cn, sn);
        ldapTemplate.bind(makeEntry(uid, cn, sn));
    }

    // Chỉ dùng nếu ứng dụng thực sự muốn thay thế binding.
    public void replace(String uid, String cn, String sn) {
        validatePerson(uid, cn, sn);
        ldapTemplate.rebind(makeEntry(uid, cn, sn));
    }

    public void delete(String uid) {
        ldapTemplate.unbind(personDn(uid));
    }

    private static DirContextAdapter makeEntry(
            String uid, String cn, String sn) {

        DirContextAdapter entry = new DirContextAdapter(personDn(uid));
        entry.setAttributeValues("objectClass", new String[]{
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", uid);
        entry.setAttributeValue("cn", cn);
        entry.setAttributeValue("sn", sn);
        return entry;
    }

    private static Name personDn(String uid) {
        if (uid == null || uid.isBlank() || uid.length() > 64) {
            throw new IllegalArgumentException("Invalid uid");
        }
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validatePerson(String uid, String cn, String sn) {
        personDn(uid);
        if (cn == null || cn.isBlank()
                || sn == null || sn.isBlank()) {
            throw new IllegalArgumentException("cn and sn are required");
        }
    }
}
~~~

Code này dùng chung một quy tắc xây DN cho tạo, thay và xóa; một giá trị UID chứa ký tự đặc biệt được xử lý bằng builder hiểu cú pháp DN. Tuy nhiên đây vẫn là **ví dụ giáo dục**: chưa có phân quyền người gọi, chính sách duyệt xóa, quy tắc duy nhất ngoài DN, giới hạn dữ liệu đầy đủ, xử lý lỗi hoặc audit.

Đặc biệt, phương thức `replace(...)` ở đây cố ý tái tạo entry chỉ từ vài trường; **không dùng trực tiếp trên entry production nếu có thêm attributes phải bảo toàn**. Khi chỉ cập nhật `mail` hoặc `telephoneNumber`, dùng `modifyAttributes(...)` như mục 6.

### Bảo vệ dữ liệu khi API nhận input từ người dùng

Một endpoint như `DELETE /directory/people/{uid}` chỉ nên ánh xạ `uid` thành DN nằm trong một OU đã định. Không để client gửi trực tiếp một DN như `cn=app-writer,ou=services,...` để xóa. Ngoài định dạng DN, cần:

- Kiểm tra người gọi có quyền nghiệp vụ xóa người dùng đó hay không.
- Chỉ cho phép thao tác trên đúng nhánh dữ liệu, theo ACL server và quy tắc service.
- Xác định quan hệ với các nhóm LDAP, tài khoản ứng dụng và quy trình nghỉ việc.
- Có audit phù hợp, nhưng không log mật khẩu, secret hoặc các thuộc tính nhạy cảm.
- Với thao tác có tác động lớn, dùng quy trình xác nhận hay phê duyệt của hệ thống.

**Escape DN** khác **escape LDAP filter**: `LdapNameBuilder` dành cho DN/RDN; `LdapQueryBuilder` và filter builder dành cho filter assertion. Một hàm escape không thay thế cho loại còn lại.

## 10. Các lỗi thường gặp và cách xử lý

| Thao tác | Tình huống | LDAP result code điển hình | Cách điều tra |
| --- | --- | --- | --- |
| `bind` | DN đã tồn tại | `entryAlreadyExists (68)` | Kiểm tra quy tắc tạo trùng và DN |
| `bind` | Parent DN không tồn tại | `noSuchObject (32)` | Kiểm tra cấu trúc DIT và base tương đối |
| `bind/rebind` | Thiếu `cn`, `sn` hoặc sai object class | `objectClassViolation (65)` | Kiểm tra `MUST`, `MAY` và kế thừa class |
| `bind/rebind` | Thuộc tính có cú pháp hoặc số giá trị không hợp lệ | `invalidAttributeSyntax (21)` hoặc `constraintViolation (19)` | Xem attribute type/schema server |
| `bind/rebind/unbind` | Bind account không đủ quyền | `insufficientAccessRights (50)` | Kiểm tra ACL và danh tính kết nối |
| `unbind` | Entry còn con | `notAllowedOnNonLeaf (66)` | Xác định các entry con trong nhánh |
| `unbind` | DN không tồn tại | `noSuchObject (32)` | Kiểm tra DN; chọn chính sách 404/idempotent |
| Bất kỳ | Mất kết nối hoặc lỗi TLS | Exception kết nối, timeout, handshake | Kiểm tra server, hostname, TLS, pool |

Đây là các mã lỗi **thường gặp**, không phải cam kết duy nhất: server có thể trả về một lỗi khác khi nhiều ràng buộc đồng thời bị vi phạm hoặc khi ACL cố ý che thông tin tồn tại của entry.

Spring LDAP chuyển nhiều exception từ JNDI sang hệ thống exception của thư viện. Trong xử lý lỗi, ưu tiên loại exception hoặc mã phản hồi đã được xác định, không phụ thuộc vào toàn bộ chuỗi thông báo riêng của một LDAP server.

### Tạo mới và xóa có “idempotent” không?

- Gọi `bind` tạo cùng DN lần đầu có thể thành công; gọi lần hai thường lỗi trùng DN. Vì vậy không mặc định `bind` là thao tác có thể retry vô điều kiện.
- Gọi `unbind` lần đầu có thể xóa thành công; gọi lại có thể lỗi không tồn tại. API nghiệp vụ có thể quy định một yêu cầu xóa lặp trả trạng thái “đã xóa”, nhưng đó là **quyết định của service**, không phải bảo đảm mặc định của LDAP.
- `rebind` có thể ghi lại dữ liệu cũ lên một entry đã được người khác cập nhật; retry không được thiết kế kỹ có nguy cơ mất cập nhật.

Nếu mạng đứt giữa lúc server thực hiện thao tác và client nhận phản hồi, ứng dụng có thể **không biết chắc thao tác đã thành công hay chưa**. Để phục hồi, đọc lại entry bằng quyền phù hợp trước khi quyết định retry. Không giả định chuỗi nhiều thao tác LDAP là giao dịch cơ sở dữ liệu có rollback tự động.

### Khác biệt giữa lỗi bind xác thực và lỗi thêm entry

Một thông báo `invalidCredentials (49)` thường liên quan tới giai đoạn xác thực LDAP khi lấy context; còn `entryAlreadyExists (68)` thường liên quan đến thao tác thêm entry. Cả hai có thể xuất hiện khi service gọi `ldapTemplate.bind(entry)`, nhưng tại **những lớp khác nhau của luồng thực thi**. Hãy phân biệt lỗi kết nối/xác thực trước khi xét schema, DN và quyền của thao tác ghi.

## 11. TLS, pooling và kiểm soát thao tác ghi

Khi `LdapTemplate` chạy `bind/rebind/unbind`, nó lấy context từ `ContextSource`. Tài khoản bind mặc định và mật khẩu phải được quản lý đúng; với simple bind, ứng dụng cần **LDAPS hoặc StartTLS với kiểm tra chứng chỉ** để bảo vệ credential và dữ liệu trao đổi.

Các điểm vận hành:

1. **Credential:** dùng tài khoản ứng dụng riêng có quyền giới hạn. Không hardcode password; lấy từ nguồn bí mật phù hợp.
2. **TLS:** xác minh certificate chain và hostname; không tắt kiểm tra chứng chỉ khi gặp lỗi handshake.
3. **Pooling:** kiểm tra tương thích giữa kiểu bind, TLS/StartTLS và pooling; không trộn context của các danh tính khác nhau.
4. **Rotation:** khi password dịch vụ thay đổi, cần làm mới `ContextSource`/runtime và các kết nối đang dùng credential cũ theo chiến lược hệ thống.
5. **Timeout:** phân biệt timeout kết nối với timeout thao tác; giới hạn retry và giám sát lỗi mạng.
6. **Quyền:** cấp quyền thêm/sửa/xóa cụ thể trên OU cần thiết, thay vì toàn bộ naming context.

Cấu hình `ContextSource.base` giúp biểu diễn DN ngắn gọn, nhưng **không phải hàng rào phân quyền**. LDAP ACL ở server mới là cơ chế quyết định entry nào và attribute nào ứng dụng có thể thay đổi.

## 12. Kiểm thử trên LDAP server dành riêng cho lab

Để kiểm thử thực tế, hãy chuẩn bị một server thử nghiệm có schema và DIT phù hợp, `ou=people` tồn tại và tài khoản thử nghiệm được quyền tạo/xóa entry trong một nhánh giới hạn. Không chạy thử tạo hoặc xóa vào dữ liệu nhân viên thật.

Giả sử `uid=binh,ou=people,dc=example,dc=org` chưa tồn tại:

| Bước | Thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| 1 | `bind` tạo Bình với `uid`, `cn`, `sn` | Entry xuất hiện |
| 2 | `lookup` hoặc `search` xác nhận attributes | Đọc được entry đã tạo |
| 3 | `bind` lại cùng DN | Bị từ chối trùng DN |
| 4 | `modifyAttributes` thêm hoặc đổi `mail` | Chỉ thay thuộc tính theo ý định |
| 5 | `rebind` với bộ dữ liệu thay thế có kiểm soát | Quan sát chính xác tác động lên attributes hiện hữu |
| 6 | `unbind` entry Bình | Xóa thành công nếu entry là leaf và được phép |
| 7 | `unbind` thêm lần nữa | Xử lý lỗi không tồn tại theo chính sách |
| 8 | Thử xóa một OU đang có entry con, trong môi trường lab | Server thường từ chối bằng non-leaf |

Một test có giá trị cần xác minh thêm:

- **DN đúng:** entry nằm dưới `ou=people`; không lặp suffix của `ContextSource.base`.
- **Schema đúng:** `objectClass`, các attribute MUST và RDN có giá trị hợp lệ.
- **ACL đúng:** tài khoản không thể thao tác ngoài nhánh được phép, kể cả khi DN đầu vào hợp cú pháp.
- **Semantics provider:** `rebind` giữ, thay hoặc loại bỏ attributes nào; kiểm tra trên server thật hoặc server kiểm thử tương thích.
- **Xử lý lỗi:** tạo trùng, thiếu parent, sai schema, non-leaf, thiếu quyền và lỗi kết nối được phân biệt rõ.
- **Dọn dữ liệu:** chỉ xóa entry do bài test tạo ra; không dùng xóa subtree rộng để dọn thử nghiệm.

Test mock `LdapTemplate` có thể kiểm tra việc service chọn đúng phương thức, nhưng không xác minh ngữ nghĩa JNDI provider, schema LDAP, ACL và quy tắc server. Với chức năng ghi, nên có integration test trên thư mục thử nghiệm phù hợp để phát hiện những khác biệt đó.

## 13. Bài tập chọn thao tác đúng

Giả sử hệ thống quản lý `uid=an,ou=people,dc=example,dc=org` và nhóm:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: developers
member: uid=an,ou=people,dc=example,dc=org
~~~

Hãy chọn phương thức phù hợp với yêu cầu:

| Yêu cầu | Lựa chọn |
| --- | --- |
| 1. Thêm entry `uid=lan` chưa tồn tại | ? |
| 2. Chỉ thay `mail` của An, giữ các attributes khác | ? |
| 3. Thay toàn bộ binding bằng dữ liệu đã kiểm soát | ? |
| 4. Xóa `uid=an` khi entry là leaf và được phép | ? |
| 5. Đổi RDN từ `uid=an` sang `uid=an2` | ? |
| 6. Xác thực password của An | ? |
| 7. Xóa `ou=people` dù vẫn còn nhiều con | ? |

**Đáp án có giải thích:**

1. **`bind(...)`** để tạo entry mới, chuẩn bị DN, object class, các MUST và quyền add.
2. **`modifyAttributes(...)`** vì chỉ cần thay một attribute.
3. **`rebind(...)`** khi chủ đích thay thế và đã hiểu dữ liệu đầy đủ/ngữ nghĩa provider.
4. **`unbind(...)`** để xóa theo DN sau khi đánh giá ACL và tham chiếu nhóm.
5. **`rename(...)` / Modify DN**, vì đây là thay đổi tên/vị trí chứ không phải rebind thông thường.
6. **`authenticate(...)` hoặc LDAP Bind xác thực; không dùng `LdapTemplate.bind(...)`.**
7. Không dùng unbind thông thường để xóa non-leaf; phải xử lý nhánh và dùng quy trình xóa được kiểm soát khi thực sự cần.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ldapTemplate.bind(entry)` bị từ chối dù ứng dụng đã xác thực bằng tài khoản dịch vụ?

*Đáp án:* Xác thực danh tính là điều kiện riêng; thao tác add còn phụ thuộc ACL, DN, parent và schema.

**Câu 2.** Vì sao `rebind` không phải lựa chọn mặc định để thay email?

*Đáp án:* Nó mang ý định thay binding, có thể tác động đến attributes khác nếu dữ liệu thay thế không đầy đủ. `modifyAttributes` diễn đạt tốt hơn phạm vi sửa.

**Câu 3.** Xóa `uid=an` có bảo đảm xóa DN của An khỏi `member` trong nhóm không?

*Đáp án:* Không thể mặc định. Cần kiểm tra tính năng quản lý tham chiếu và chính sách LDAP server.

**Câu 4.** Lỗi timeout sau khi gửi unbind có chứng minh entry vẫn còn không?

*Đáp án:* Không. Phản hồi có thể bị mất sau khi server đã xóa; phải kiểm tra trạng thái trước khi lặp lại.

**Câu 5.** Vì sao không thể thay `LdapNameBuilder` bằng `LdapQueryBuilder` để tạo DN?

*Đáp án:* DN/RDN và search filter là hai cú pháp khác nhau; mỗi builder xử lý dạng escape và cấu trúc riêng.

## 14. Ghi nhớ

- **`LdapTemplate.bind(...)` tạo entry**, khác với thao tác **LDAP Bind** dùng để xác thực. **`rebind(...)` thay binding**, **`unbind(...)` xóa entry**.
- Khi chỉ cập nhật một vài thuộc tính, **ưu tiên `modifyAttributes(...)`**. Chỉ sử dụng `rebind(...)` khi có ý định thay thế rõ ràng và biết tác động tới attributes.
- DN đưa vào các thao tác thường **tương đối với base của `ContextSource`**. Dùng `LdapNameBuilder` cho RDN động; không lặp suffix hoặc đưa raw DN không được kiểm soát vào API ghi.
- Tạo entry cần parent tồn tại, DN chưa trùng, schema hợp lệ và quyền add. Xóa thường chỉ áp dụng trực tiếp cho **leaf entry** có quyền delete.
- Xác thực và phân quyền là hai lớp khác nhau. Spring LDAP quản lý kết nối/JNDI và exception, còn server kiểm tra schema, ACL và chính sách.
- Dùng kết nối TLS đã xác minh chứng chỉ, quản lý secret và quyền tối thiểu, kiểm thử chức năng ghi trên thư mục lab trước khi vận hành; tránh retry mù khi mất phản hồi.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513)
