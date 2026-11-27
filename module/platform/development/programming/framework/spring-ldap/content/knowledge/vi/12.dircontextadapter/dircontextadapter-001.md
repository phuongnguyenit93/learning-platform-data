# DirContextAdapter giữ DN và attribute thay đổi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `DirContextAdapter` vừa nắm giữ **Distinguished Name (DN)** của một entry vừa cung cấp tập **attributes** để đọc và chỉnh sửa ở phía Java.
- Phân biệt trạng thái **entry mới** với **entry đã đọc từ LDAP**, cũng như trạng thái ban đầu và trạng thái đã thay đổi trong adapter.
- Hiểu cơ chế tạo các `ModificationItem` phục vụ thao tác `ldapTemplate.modifyAttributes(...)` và giới hạn của cơ chế theo dõi thay đổi này.
- Tạo entry bằng `new DirContextAdapter(dn)` và `ldapTemplate.bind(...)`; cập nhật entry bằng `lookupContext(...)`, setter rồi `modifyAttributes(...)`.
- Biết vì sao **sửa attribute không tự đổi DN**, vì sao giá trị đa trị không được cập nhật giống single-value và khi nào cần thao tác LDAP Modify trực tiếp.
- Vận dụng kiến thức về schema, matching rule, ACL, TLS, pooling và kiểm thử Spring LDAP để tránh các lỗi ghi dữ liệu trong thực tế.

Bài thuộc chương **DirContextAdapter** của module **SPRING_LDAP**. Trong quá trình làm việc với dịch vụ thư mục LDAP qua Spring LDAP, từ DN, schema và filter đến `LdapTemplate`, `LdapClient` và ODM, adapter là một mắt xích quan trọng: nó giúp biểu diễn **một entry có tên và thuộc tính**, nhưng không biến các setter Java thành thao tác ghi mạng tự động.

---

## 1. Bài toán: cập nhật một hồ sơ LDAP mà không mất dữ liệu khác

Giả sử directory có entry sau:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Lan
sn: Nguyen
mail: lan@example.org
telephoneNumber: +84 28 1234 5678
description: Member of Platform team
~~~

Một chức năng trong ứng dụng nhân sự chỉ muốn đổi số điện thoại của `lan`. Không nên thay toàn bộ entry chỉ vì một trường thay đổi; làm như vậy có thể ghi đè `mail`, `description` hoặc các giá trị mà tác vụ khác vừa sửa.

Trong Spring LDAP, mẫu thường gặp:

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(dn);

entry.setAttributeValue(
    "telephoneNumber",
    "+84 28 9999 0000"
);

ldapTemplate.modifyAttributes(entry);
~~~

Đoạn code có **ba mốc** khác nhau:

1. `lookupContext` lấy trạng thái của entry từ LDAP và đặt vào object phía ứng dụng.
2. `setAttributeValue` thay đổi **object trong bộ nhớ**, để adapter biết giá trị mong muốn.
3. `modifyAttributes` yêu cầu LDAP server áp dụng các thay đổi được adapter mô tả.

**Mấu chốt:** một setter thành công chưa đồng nghĩa LDAP server đã nhận hoặc chấp nhận cập nhật.

## 2. DN và attributes là hai phần của cùng một entry

LDAP không lưu dữ liệu theo hàng với khóa số nguyên như một bảng SQL thông thường. Mỗi entry được nhận diện bằng **Distinguished Name** và có một tập các attribute tuân thủ schema.

~~~text
DN:
  uid=lan,ou=people,dc=example,dc=org

Attributes:
  objectClass = top, person, organizationalPerson, inetOrgPerson
  uid = lan
  cn = Nguyen Lan
  sn = Nguyen
  mail = lan@example.org
  telephoneNumber = +84 28 1234 5678
~~~

Trong Spring LDAP:

- `DirContextOperations.getDn()` cho biết DN gắn với adapter theo quy ước tên của Spring LDAP.
- `DirContextOperations.getAttributes()` cho phép truy cập biểu diễn `javax.naming.directory.Attributes`.
- Các getter như `getStringAttribute(...)` và `getStringAttributes(...)` hỗ trợ đọc dữ liệu thuận tiện.
- Các setter như `setAttributeValue(...)`, `setAttributeValues(...)` hỗ trợ biểu diễn trạng thái thuộc tính mong muốn.

| Thực thể | Ý nghĩa | Không được nhầm với |
| --- | --- | --- |
| DN | Tên duy nhất của entry trong cây directory ở một thời điểm | Giá trị trường `cn` hoặc `uid` đơn lẻ |
| RDN | Thành phần tên gần nhất, ví dụ `uid=lan` | Tất cả các attribute của entry |
| Attributes | Tập thuộc tính/giá trị của entry | Java bean không cần schema |
| Adapter | Object phía Java giữ DN/attributes và trạng thái thay đổi | Kết nối LDAP đang mở |
| ModificationItem | Mô tả thao tác thêm, thay, xóa một attribute/giá trị | Giao dịch nhiều entry tự động |
| LDAP ModifyRequest | Yêu cầu server cập nhật entry | Lời gọi setter trên adapter |

Một DN có thể chứa RDN với dấu phẩy, dấu cộng, ký tự Unicode hoặc khoảng trắng cần escape. Vì vậy, nên làm việc với `javax.naming.Name` và `LdapNameBuilder`, không nối DN từ chuỗi nhập vào mà không có kiểm soát.

## 3. DirContextOperations và DirContextAdapter khác nhau ở đâu?

Đây là hai kiểu thuộc Spring LDAP core:

~~~java
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.DirContextAdapter;
~~~

- **`DirContextOperations`** là interface cung cấp các thao tác trên biểu diễn entry LDAP.
- **`DirContextAdapter`** là implementation điển hình của interface đó, giữ thông tin DN và attributes cùng khả năng tính các thay đổi cho quá trình cập nhật.

Đừng nhầm với:

~~~java
import javax.naming.directory.DirContext;
~~~

`DirContext` của **JNDI** đại diện cho API truy cập directory ở cấp provider. `DirContextAdapter` **không** phải một kết nối JNDI đầy đủ để bạn gọi search/bind trực tiếp lên server.

### 3.1. Luồng điển hình

~~~mermaid
flowchart TD
    App["Service nghiệp vụ"]
    Template["LdapTemplate"]
    Context["ContextSource / JNDI DirContext"]
    LDAP[("LDAP server")]
    Loaded["DirContextOperations<br/>adapter giữ DN + Attributes"]
    Change["Thay đổi attributes trên adapter"]
    Mods["ModificationItem[]<br/>thêm / thay / xóa"]
    App -->|"lookupContext(dn)"| Template
    Template --> Context --> LDAP
    LDAP --> Loaded --> Change --> Mods
    Mods -->|"modifyAttributes(adapter)"| Template
~~~

Sơ đồ minh họa **dữ liệu và trách nhiệm**, không khẳng định có một request LDAP riêng cho mỗi khối trong sơ đồ. Khi adapter được tạo mới để bind entry, không có bước đọc dữ liệu cũ từ server.

### 3.2. Khi nào dùng interface, khi nào tạo class?

Trong service đọc hoặc sửa entry có sẵn, nên khai báo biến theo interface:

~~~java
DirContextOperations entry =
    ldapTemplate.lookupContext(dn);
~~~

Khi tạo entry mới, có thể chủ động tạo implementation:

~~~java
DirContextAdapter entry = new DirContextAdapter(dn);
~~~

Cách tổ chức này giúp service phụ thuộc vào hợp đồng thao tác khi có thể, còn việc khởi tạo cụ thể chỉ xảy ra khi cần dựng một entry trong bộ nhớ.

## 4. Adapter đang giữ DN theo ngữ cảnh nào?

Giả sử `ContextSource` được cấu hình:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # spring.ldap.password lấy từ secret manager.
~~~

Với full DN:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

một tên tương đối thường dùng với `LdapTemplate` là:

~~~text
uid=lan,ou=people
~~~

Ví dụ tạo `Name` từ các RDN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name relativeDn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", "lan")
    .build();
~~~

Nếu adapter được khởi tạo bằng `relativeDn`, `getDn()` gắn với DN đó. Khi adapter đến từ search hoặc lookup, hãy xác minh **quy ước DN của API và base đã cấu hình**, không tự coi mọi `getDn().toString()` là full DN từ root LDAP server.

### 4.1. Trường DN trong DTO cần nói rõ ý nghĩa

Đối với một REST API, có thể dùng:

~~~java
public record EmployeeView(
    String relativeDn,
    String uid,
    String commonName
) {}
~~~

Tên trường `relativeDn` rõ ràng hơn `dn` khi hệ thống lưu DN tương đối với `ContextSource.base`.

Nếu bắt buộc lưu full DN ngoài ứng dụng, cần ghép/canonicalize tên bằng API DN thích hợp và bảo đảm không nhân đôi `dc=example,dc=org`. DN không phải ID bất biến: rename hoặc chuyển sang OU khác sẽ làm nó thay đổi.

### 4.2. Sửa attribute không phải rename

Giả sử entry có RDN `uid=lan`. Gọi:

~~~java
entry.setAttributeValue("cn", "Nguyen Lan Anh");
~~~

có thể thay tên hiển thị `cn` nếu schema/ACL cho phép, **không** đổi DN.

Ngay cả khi gọi:

~~~java
entry.setAttributeValue("uid", "lan.new");
~~~

thì đó vẫn không phải là một phép rename entry từ `uid=lan,...` sang `uid=lan.new,...`. Để đổi RDN/DN phải sử dụng thao tác đổi tên phù hợp, ví dụ `ldapTemplate.rename(oldDn, newDn)`, và lưu ý quy tắc naming attribute, reference và quyền server.

## 5. Trạng thái adapter: loaded entry khác new entry

Hai cách khởi tạo này có mục đích khác nhau:

| Cách lấy adapter | Tình huống | Operation gửi server |
| --- | --- | --- |
| `new DirContextAdapter(dn)` | Dựng một entry chưa tồn tại | `ldapTemplate.bind(adapter)` |
| `ldapTemplate.lookupContext(dn)` | Đọc entry hiện có trước khi sửa | `ldapTemplate.modifyAttributes(adapter)` |
| `ContextMapper` trong `search(...)` | Ánh xạ entry và DN thành DTO | Thường chỉ đọc; không tự ghi |
| `lookupContext(dn)` để chỉ lấy DN/attributes | Đọc không sửa | Không cần `modifyAttributes` nếu không có thay đổi |

Một adapter **mới** không có nghĩa “bản ghi mới đã tồn tại trên server”. Nó là một object trong bộ nhớ với DN, chứa các thuộc tính mà ứng dụng sẽ cung cấp cho thao tác bind.

Một adapter **đã đọc từ LDAP** có dữ liệu ban đầu để biết phần nào đã được chỉnh sửa. Đây là cơ sở để tạo những `ModificationItem` phù hợp với yêu cầu ghi.

### 5.1. Trạng thái có thể hình dung như thế nào?

~~~text
Khi lookup:
  DN: uid=lan,ou=people
  telephoneNumber (ban đầu): +84 28 1234 5678

Khi setAttributeValue:
  DN: uid=lan,ou=people       (giữ nguyên)
  telephoneNumber (muốn có): +84 28 9999 0000

Khi getModificationItems:
  Dữ liệu cần gửi server:
  REPLACE telephoneNumber = +84 28 9999 0000

Khi modifyAttributes:
  Server kiểm tra ACL/schema và xử lý request
~~~

Đây là mô hình **khái niệm**. Chi tiết cách adapter tính diff, gom operation và so giá trị tùy phiên bản/kiểu attribute; không nên cam kết một setter luôn tạo đúng một `REPLACE_ATTRIBUTE` trong mọi trường hợp.

### 5.2. Ba sự thật phải tách biệt

1. **Đã sửa object Java:** setter chạy xong.
2. **Đã gửi yêu cầu:** `LdapTemplate` gọi thao tác LDAP modify.
3. **Server đã xác nhận và trạng thái đã đạt kỳ vọng:** thao tác trả thành công, hoặc được kiểm tra lại theo yêu cầu nghiệp vụ.

Lỗi kết nối giữa chừng có thể khiến client không chắc request đã được server áp dụng hay chưa. Không được “retry mù” một thao tác thêm giá trị hoặc ghi đè khi cần bảo đảm tính nhất quán.

## 6. Đọc thuộc tính bằng adapter

Giả sử đã có:

~~~java
DirContextOperations entry =
    ldapTemplate.lookupContext(relativeDn);
~~~

Các phương thức đọc thông dụng:

~~~java
String uid = entry.getStringAttribute("uid");
String fullName = entry.getStringAttribute("cn");
String email = entry.getStringAttribute("mail");
~~~

Nếu một attribute không có trong kết quả lookup, bị ACL che hoặc không tồn tại, getter có thể trả `null`. Không giả định mọi entry `inetOrgPerson` đều có `mail`.

### 6.1. Bắt buộc và tùy chọn

~~~java
String uid = entry.getStringAttribute("uid");
if (uid == null || uid.isBlank()) {
    throw new IllegalStateException(
        "Không đọc được uid theo hợp đồng nghiệp vụ"
    );
}

String email = entry.getStringAttribute("mail");
// mail là tùy chọn trong ví dụ; có thể null.
~~~

Trong thực tế cần phân biệt:

- Schema không yêu cầu attribute.
- Server trả attribute khác với loại đang yêu cầu.
- Tài khoản bind không được đọc attribute.
- Truy vấn chỉ yêu cầu một tập returning attributes nên thiếu field cần map.

Đừng kết luận “entry không tồn tại” chỉ vì một getter trả `null`.

### 6.2. Thuộc tính nhiều giá trị

Nhóm LDAP có thể có nhiều `member`:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Để đọc toàn bộ giá trị chuỗi:

~~~java
String[] members = entry.getStringAttributes("member");

if (members != null) {
    for (String memberDn : members) {
        System.out.println(memberDn);
    }
}
~~~

Chỉ gọi `getStringAttribute("member")` sẽ không đại diện đầy đủ cho một attribute nhiều giá trị. Thứ tự các giá trị thường **không có ý nghĩa nghiệp vụ**; không dựa vào giá trị đầu tiên để chọn “nhóm trưởng”.

### 6.3. Kiểu binary

Không phải attribute nào cũng là `String`. Ví dụ `jpegPhoto` có thể là dữ liệu byte; phải đọc theo kiểu phù hợp:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.Attribute;

Attributes attrs = entry.getAttributes();
Attribute photo = attrs.get("jpegPhoto");

if (photo != null && photo.size() > 0) {
    Object raw = photo.get();

    if (raw instanceof byte[] bytes) {
        // Xử lý bytes theo nghiệp vụ, không log nội dung nhị phân.
    }
}
~~~

Ví dụ chỉ minh họa việc **kiểm tra kiểu**. Với file/ảnh lớn, cần thiết kế giới hạn kích thước, caching và không tải attribute nếu UI chỉ cần `uid`, `cn`.

## 7. Thay đổi một attribute đơn trị

Đây là ví dụ cập nhật `telephoneNumber` từ một service:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class EmployeePhoneService {

    private final LdapTemplate ldapTemplate;

    public EmployeePhoneService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changePhone(String uid, String phone) {
        Name dn = LdapNameBuilder
            .newInstance("ou=people")
            .add("uid", uid)
            .build();

        DirContextOperations entry =
            ldapTemplate.lookupContext(dn);

        entry.setAttributeValue("telephoneNumber", phone);

        ldapTemplate.modifyAttributes(entry);
    }
}
~~~

Giả định:

- `ContextSource.base = dc=example,dc=org`.
- Nhân viên nằm **trực tiếp** dưới `ou=people`; nếu có OU con, không thể dựng DN từ `uid` theo cách đơn giản này.
- Attribute được phép thay thế và số điện thoại hợp lệ với schema/ACL.
- Tài khoản bind có quyền ghi lên entry.

**Dữ liệu `uid` do client gửi không đủ để được quyền chỉnh sửa bất kỳ hồ sơ nào.** Trước khi gọi service, ứng dụng phải kiểm tra người gọi có quyền sửa chính nhân viên đó; không dựa vào LDAP ACL như lớp authorization duy nhất.

### 7.1. Khi người dùng nằm trong OU con

Ví dụ:

~~~text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
~~~

Nếu service dựng `uid=lan,ou=people`, lookup sẽ nhắm sai entry. Phải tìm entry bằng filter `uid` đã escape trong search scope hợp lý, lấy DN được server trả về qua `ContextMapper`, rồi thực hiện update với **DN thật**.

Đừng dùng display name `cn` để chọn ngẫu nhiên một user khi có nhiều người trùng tên.

## 8. Từ setter đến ModificationItem

JNDI biểu diễn một phép sửa thông qua:

~~~java
import javax.naming.directory.ModificationItem;
import javax.naming.directory.DirContext;
~~~

Ba loại operation cơ bản:

| Hằng JNDI | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `DirContext.ADD_ATTRIBUTE` | Thêm attribute hoặc giá trị | Thêm một thành viên nhóm |
| `DirContext.REPLACE_ATTRIBUTE` | Thay giá trị attribute theo request | Đổi số điện thoại |
| `DirContext.REMOVE_ATTRIBUTE` | Xóa attribute hoặc một tập giá trị | Gỡ thành viên nhóm |

`DirContextAdapter` hỗ trợ tính `ModificationItem[]` phản ánh thay đổi được ghi nhận trên adapter. Một cách quan sát:

~~~java
import javax.naming.directory.ModificationItem;

DirContextOperations entry =
    ldapTemplate.lookupContext(dn);

entry.setAttributeValue(
    "telephoneNumber",
    "+84 28 9999 0000"
);

ModificationItem[] pending =
    entry.getModificationItems();

System.out.println("Số phần sửa: " + pending.length);

ldapTemplate.modifyAttributes(entry);
~~~

**Không dùng số lượng `pending.length` làm bằng chứng dữ liệu đã được sửa trên server.** Nó chỉ nói lên những modification adapter đề xuất ở phía Java.

### 8.1. So sánh giá trị mới với giá trị cũ

Có ba tình huống hữu ích để tự kiểm tra:

1. Đặt lại cùng giá trị đã đọc: có thể không tạo modification cần thiết nếu adapter nhận diện không đổi.
2. Đặt một giá trị khác: thường tạo thay đổi thích hợp.
3. Xóa hoặc thay một attribute nhiều giá trị: phải hiểu rõ bạn đang loại **một giá trị** hay thay **toàn bộ tập giá trị**.

Hành vi chính xác của phần so sánh/ghi nhận diff tùy API và kiểu dữ liệu; đừng suy rằng adapter và LDAP server dùng cùng một **matching rule** để so các giá trị trong mọi trường hợp. Ví dụ so DN trên server phụ thuộc `distinguishedNameMatch`; Java object có thể chỉ có một kiểu so sánh dữ liệu nội bộ.

### 8.2. Không sửa trực tiếp Attributes rồi kỳ vọng tracking luôn đúng

`getAttributes()` cung cấp một biểu diễn JNDI `Attributes`. Với luồng cập nhật, nên dùng các setter/add/remove của `DirContextOperations` vì đây là API được thiết kế để ghi nhận thay đổi.

Không tự chỉnh sửa những object nội bộ lấy từ `getAttributes()` rồi mặc định `getModificationItems()` sẽ phát hiện mọi thay đổi và bảo toàn snapshot ban đầu trên mọi phiên bản. Nếu cần thao tác trực tiếp với `ModificationItem`, hãy dùng API modify theo hợp đồng JNDI/Spring LDAP.

## 9. Thêm một giá trị và thay cả tập giá trị khác nhau thế nào?

Giả sử group có:

~~~text
member:
  uid=lan,ou=people,dc=example,dc=org
  uid=minh,ou=people,dc=example,dc=org
~~~

Nếu nghiệp vụ chỉ muốn thêm `uid=hoa,...`, dùng:

~~~java
group.addAttributeValue(
    "member",
    "uid=hoa,ou=people,dc=example,dc=org"
);
~~~

Khi đó adapter diễn đạt **ý định thêm** một giá trị. Trong luồng lookup/modify bình thường, Spring LDAP có thể tính các modifications cần thiết dựa trên dữ liệu đã đọc.

Ngược lại:

~~~java
group.setAttributeValues(
    "member",
    new String[] {
        "uid=hoa,ou=people,dc=example,dc=org"
    }
);
~~~

là thao tác mô tả **tập giá trị mong muốn mới**. Nó có thể khiến `lan` và `minh` bị xóa khỏi group khi thay đổi được ghi. Đây là một trong những lỗi nguy hiểm nhất khi mapping một collection của LDAP sang Java.

### 9.1. Ví dụ add/remove group membership qua adapter

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void addMemberToDevelopers(
        LdapTemplate ldapTemplate,
        String memberFullDn) {

    Name groupRelativeDn = LdapNameBuilder
        .newInstance("ou=groups")
        .add("cn", "developers")
        .build();

    DirContextOperations group =
        ldapTemplate.lookupContext(groupRelativeDn);

    group.addAttributeValue("member", memberFullDn);

    ldapTemplate.modifyAttributes(group);
}
~~~

Điểm kiểm soát:

- `groupRelativeDn` là DN của **entry nhóm** tương đối với base cấu hình.
- `memberFullDn` là giá trị attribute `member` chứa **full DN** của người dùng theo schema group.
- Attribute `member` có syntax DN và matching rule thích hợp; một số server có thể từ chối giá trị trùng hoặc sửa thiếu quyền.
- Đây là **thành viên trực tiếp**. Nested groups và dynamic groups có quy tắc riêng.
- Nếu muốn loại một member, dùng `removeAttributeValue("member", memberFullDn)` trên adapter rồi thực hiện modify theo hợp đồng.

### 9.2. Luồng read-modify-write có race condition

Hai request đồng thời có thể cùng đọc nhóm ban đầu, mỗi request thêm một thành viên khác nhau, rồi ghi. Nếu implementation gửi một phép **replace toàn bộ tập giá trị** từ snapshot cũ, thay đổi đến sau có thể làm mất thay đổi đến trước.

Do đó, với nhóm lớn hoặc tần suất ghi cao, nên kiểm tra **LDAP Modify ADD/REMOVE trực tiếp** để yêu cầu thêm/xóa một giá trị ở phía server mà không xây lại cả tập từ client.

Ví dụ tương ứng:

~~~java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

public void addMemberDirectly(
        LdapTemplate ldapTemplate,
        Name groupRelativeDn,
        String memberFullDn) {

    ModificationItem add = new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("member", memberFullDn)
    );

    ldapTemplate.modifyAttributes(
        groupRelativeDn,
        new ModificationItem[] {add}
    );
}
~~~

Cách này diễn đạt rõ yêu cầu **ADD value** thay vì tính lại toàn bộ group membership ở client. Server vẫn có thể từ chối nếu giá trị đã tồn tại, ACL cấm sửa hoặc schema không cho phép.

Đây không phải giải pháp tổng quát cho mọi race condition; với các workflow phụ thuộc điều kiện, cần xem xét cơ chế server hỗ trợ như assertion control hoặc concurrency policy phù hợp.

## 10. Tạo entry mới: adapter giữ DN trước khi LDAP có entry

Khi entry chưa tồn tại, bạn tạo adapter bằng DN dự kiến rồi thêm các thuộc tính bắt buộc.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void createEmployee(
        LdapTemplate ldapTemplate,
        String uid,
        String name,
        String surname) {

    Name dn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", uid)
        .build();

    DirContextAdapter entry = new DirContextAdapter(dn);

    entry.setAttributeValues(
        "objectClass",
        new String[] {
            "top",
            "person",
            "organizationalPerson",
            "inetOrgPerson"
        }
    );

    entry.setAttributeValue("uid", uid);
    entry.setAttributeValue("cn", name);
    entry.setAttributeValue("sn", surname);

    ldapTemplate.bind(entry);
}
~~~

Đoạn code minh họa:

1. `LdapNameBuilder` tạo DN an toàn từ các phần RDN.
2. `DirContextAdapter` giữ **DN dự kiến** và tập attributes cần ghi.
3. `bind(adapter)` là bước yêu cầu LDAP server **tạo entry**.
4. Schema và ACL của server quyết định entry có được tạo hay không.

Giả sử `uid=lan` đã tồn tại ở đúng DN đó, thao tác bind có thể thất bại do entry trùng; template không tự thực hiện “upsert”.

### 10.1. Tên entry và naming attribute

Trong DN `uid=lan,ou=people,...`, `uid` là **naming attribute** ở RDN. Khi tạo entry, hãy cung cấp thuộc tính và giá trị phù hợp với DN và schema.

Không gán DN một đằng nhưng `uid` attribute một nẻo rồi hy vọng server tự sửa. Với server nghiêm ngặt, thiếu hoặc không phù hợp naming attribute có thể làm thao tác bị từ chối.

### 10.2. Schema của inetOrgPerson

Chuỗi objectClass trong ví dụ minh họa một mô hình phổ biến. Server cụ thể có thể yêu cầu thêm thuộc tính, áp quy tắc structural objectClass hoặc giới hạn tên entry/OU được phép tạo.

Bản thân adapter không thực hiện toàn bộ validation theo schema LDAP; nó không tự bảo đảm `objectClass` và `sn` hợp lệ trên server.

## 11. Đọc entry hiện có trước khi sửa

Ví dụ quy trình cập nhật một hồ sơ:

~~~text
(1) Xác định DN hợp lệ
     ↓
(2) lookupContext(dn)
     ↓
(3) Xem attribute hiện có
     ↓
(4) setAttributeValue / addAttributeValue / removeAttributeValue
     ↓
(5) getModificationItems (nếu cần quan sát)
     ↓
(6) modifyAttributes(adapter)
     ↓
(7) Đọc lại nếu nghiệp vụ cần xác minh trạng thái
~~~

Tại bước (2), nên để `LdapTemplate` xây adapter dựa trên entry thật. Đừng lấy một DTO chỉ có hai field rồi tạo `new DirContextAdapter(dn)` để sửa entry hiện hữu theo kiểu “save toàn bộ object”: adapter mới không có cùng snapshot ban đầu với entry được đọc từ server.

### 11.1. Đọc lại khi nào?

Sau khi `modifyAttributes(...)` trả thành công, tùy yêu cầu nghiệp vụ có thể:

- Tin vào kết quả LDAP ModifyResponse trong luồng nhất quán thông thường.
- Đọc lại để đối chiếu các trường nhạy cảm.
- Nếu chạy nhiều LDAP replica, nhận thức rằng đọc từ replica khác có thể chậm thấy thay đổi vì replication delay.
- Xử lý trường hợp request timeout sau khi server đã nhận thay đổi; không tự coi timeout là rollback.

Không đọc lại cho **mọi field của mọi request** chỉ vì “chắc chắn hơn”: đó là thêm network round trip. Xác định theo mức độ quan trọng và chi phí.

## 12. Dữ liệu trong adapter có thể thiếu hoặc chỉ là một snapshot

Một adapter có thể phản ánh **những thuộc tính server đã trả về**, không nhất thiết toàn bộ dữ liệu thực có trong entry.

Ví dụ search chỉ trả:

~~~java
controls.setReturningAttributes(
    new String[] {"uid", "cn"}
);
~~~

Khi đó không thể kỳ vọng mapper/adapter tự có `mail`, `telephoneNumber`, `memberOf` hoặc operational attributes. ACL cũng có thể che bớt thuộc tính.

### 12.1. Tác động tới cập nhật

Nếu bạn định sửa một attribute nhiều giá trị nhưng snapshot không có đầy đủ tập giá trị ban đầu, việc suy ra “giá trị hiện có” có thể sai.

Do đó:

- Khi **read-modify-write**, bảo đảm thao tác lookup cung cấp những attributes cần thiết để sửa.
- Nếu chỉ muốn **ADD/REMOVE một giá trị**, cân nhắc gửi `ModificationItem` trực tiếp để tránh phải đọc/replace cả tập.
- Không suy rằng attribute không được trả về đồng nghĩa nó không tồn tại trên server.
- Đối với operational attributes do server quản lý, không dùng setter để sửa nếu server không cho phép.

### 12.2. Không giữ adapter làm cache lâu dài mà không có kế hoạch

Một adapter được đọc vào lúc T0 là snapshot. Directory có thể thay đổi ở T1 do worker khác hoặc tác vụ quản trị. Nếu giữ adapter trong singleton lâu ngày rồi ghi ở T2, bạn có thể gửi các thay đổi dựa trên dữ liệu cũ.

`DirContextAdapter` không phải bộ máy đồng bộ tự động với LDAP server. Để cache, cần TTL, chiến lược làm mới và xử lý conflict phù hợp.

## 13. Multi-valued và kiểu dữ liệu: không phải Java List thông thường

LDAP multi-valued attributes về mặt schema thường được coi là **tập giá trị không có thứ tự nghiệp vụ**. Từ góc độ ứng dụng:

| Tác vụ | Cách nhìn đúng | Lỗi dễ gặp |
| --- | --- | --- |
| Đọc `member` | Đọc toàn bộ các giá trị | Chỉ lấy `getStringAttribute` |
| Thêm một member | Thêm một giá trị DN | Replace toàn bộ mảng bằng một DN |
| Xóa một member | Loại đúng DN cần xóa | Xóa cả attribute `member` |
| So hai DN | Dùng ngữ nghĩa DN/schema | `equalsIgnoreCase` trên raw string |
| Ghi `jpegPhoto` | Dữ liệu nhị phân | Ép mọi giá trị sang `String` |
| Ghi attribute `SINGLE-VALUE` | Chỉ một giá trị hợp lệ | Đặt mảng chứa nhiều giá trị |

Với `getStringAttributes("member")`, không dùng thứ tự phần tử để quyết định ai có quyền cao nhất. Tên attribute như `cn` không phân biệt hoa/thường, nhưng giá trị phụ thuộc `EQUALITY` matching rule của type đó.

## 14. Kiểm soát đổi DN và đổi RDN

Nếu một nhân viên chuyển phòng ban:

~~~text
Từ:
uid=lan,ou=people,dc=example,dc=org

Sang:
uid=lan,ou=engineering,ou=people,dc=example,dc=org
~~~

đây là thay đổi **DN/entry location**, không phải chỉ thêm `department=Engineering`.

Trong Spring LDAP, bạn có thể cần thao tác `rename(...)` hoặc một luồng di chuyển theo khả năng server. Việc rename/move có thể bị hạn chế bởi server, ACL hoặc làm thay đổi tham chiếu đang lưu ở các entry group.

`setAttributeValue("department", "...")` không khiến adapter tự động đổi `getDn()`. Cần chủ động xác định chính sách thay DN, tên mới và cách cập nhật references.

### 14.1. Không dùng DN làm định danh bền vững nếu DN có thể đổi

Nếu hệ thống lưu DN trong database để tham chiếu người dùng, một lần rename sẽ làm giá trị đó cũ đi. Khi cần định danh ổn định, xem khả năng của LDAP server về các operational identifiers như `entryUUID` hoặc `objectGUID` và chính sách sử dụng chúng. Không coi các attribute đó là có sẵn trên mọi server.

## 15. ContextMapper và AttributesMapper liên quan thế nào?

Trong thao tác search, bạn thường chọn một mapper để chuyển entry thành DTO.

### 15.1. Chỉ cần thuộc tính: AttributesMapper

~~~java
import org.springframework.ldap.core.AttributesMapper;

List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs ->
        (String) attrs.get("cn").get()
);
~~~

`AttributesMapper<T>` nhận `javax.naming.directory.Attributes`; phù hợp nếu không cần DN.

### 15.2. Cần DN: ContextMapper

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

record EmployeeIdentity(
    String relativeDn,
    String uid,
    String commonName
) {}

List<EmployeeIdentity> people = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (ContextMapper<EmployeeIdentity>) ctx -> {
        DirContextOperations entry =
            (DirContextOperations) ctx;

        return new EmployeeIdentity(
            entry.getDn().toString(),
            entry.getStringAttribute("uid"),
            entry.getStringAttribute("cn")
        );
    }
);
~~~

`ContextMapper<T>` cung cấp context phù hợp cho việc đọc DN và các tiện ích của `DirContextOperations`. Nó **không** có nghĩa callback sẽ tự ghi changes nếu bạn gọi setter bên trong. Đối với search phục vụ hiển thị, nên coi mapper là phép chuyển đổi **đọc dữ liệu**, không mutate server.

**Nhớ:** DN không phải một user attribute bắt buộc có tên `dn`. Đừng mong tìm `attrs.get("dn")` sẽ trả tên entry trong mọi directory.

## 16. Đơn vị thay đổi và tính nguyên tử

Một LDAP ModifyRequest cho một entry có thể chứa nhiều modification liên quan. Việc server áp dụng các modification đó tuân theo hợp đồng LDAP và các ràng buộc của server.

Điều này khác với một quy trình có **hai entry**:

1. Tạo employee.
2. Thêm employee vào group.

Hai bước đó không trở thành một transaction nhiều entry chỉ vì cùng dùng `LdapTemplate` hoặc `DirContextAdapter`. Nếu bước 2 thất bại, entry ở bước 1 vẫn có thể tồn tại.

### 16.1. Tránh lost update

Ví dụ hai request đều sửa `telephoneNumber`:

~~~text
T0: Request A đọc phone = 100
T1: Request B đọc phone = 100
T2: A đặt phone = 200, modify thành công
T3: B đặt phone = 300, modify thành công
Kết quả minh họa: 300
~~~

Adapter không tự thực hiện optimistic locking trên cùng entry. Với nghiệp vụ cần tránh ghi đè, cần cơ chế xác minh điều kiện trước khi ghi theo khả năng LDAP server, hoặc một chính sách concurrency của ứng dụng. Có thể nghiên cứu LDAP assertion control nếu server/client hỗ trợ; không giả định API Spring LDAP mặc định triển khai đầy đủ mọi cơ chế đó.

### 16.2. Khi thao tác ADD/REMOVE tốt hơn replace

Nếu nhóm có hàng nghìn member và ứng dụng chỉ thêm một người, việc tải cả nhóm, dựng lại danh sách và REPLACE toàn bộ rất dễ gây tranh chấp và tốn tài nguyên.

Một LDAP Modify ADD/REMOVE cụ thể giúp thể hiện chính xác ý định. Tuy nhiên nó vẫn phải xử lý các trường hợp duplicate, không tồn tại, ACL và quy tắc group objectClass.

## 17. Bảo mật: adapter không tự kiểm tra authorization

### 17.1. Hai lớp quyền khác nhau

- **Quyền ứng dụng:** người gọi API có được sửa `telephoneNumber` của entry này không?
- **LDAP ACL:** tài khoản bind đang kết nối có được thực hiện ModifyRequest cho entry và attribute này không?

Cả hai cần thiết. Một service account có quyền ghi rộng không có nghĩa mọi user đã đăng nhập được sử dụng quyền đó cho bất kỳ DN nào.

Ví dụ thiết kế đúng:

~~~text
HTTP request -> Spring Security authorization
             -> kiểm tra target DN thuộc phạm vi người gọi được sửa
             -> validate newPhone
             -> lookupContext / modifyAttributes
             -> LDAP server kiểm tra ACL + schema
~~~

Không cung cấp endpoint:

~~~text
POST /ldap/edit?dn=<any>&attribute=<any>&value=<any>
~~~

rồi gọi `entry.setAttributeValue(attribute, value)` theo input không được whitelist. Cần hạn chế thuộc tính và entry hợp lệ ở tầng ứng dụng.

### 17.2. Bảo vệ credentials và kết nối

- Dùng LDAPS/StartTLS với certificate chain và hostname được xác minh.
- Không lưu service bind password trong Git hoặc log.
- Không mở “trust all certificates” để bỏ qua lỗi TLS.
- Nếu có pooling, kiểm tra việc tái sử dụng context đúng danh tính; đặc biệt không trộn user bind và service bind tùy tiện.
- Không đọc/ghi `userPassword` qua adapter để tự xây cơ chế login; dùng LDAP bind/Spring Security LDAP phù hợp.

### 17.3. Không log toàn bộ adapter

`DirContextAdapter` có thể chứa email, số điện thoại, membership hoặc dữ liệu nhạy cảm khác. Log toàn bộ entry hay `getModificationItems()` có thể làm lộ những giá trị đó.

Nên log **operation type**, thời điểm, thời lượng, kết quả và mã lỗi theo chính sách bảo mật, chỉ ghi DN hay tên attribute khi có nhu cầu vận hành và quyền phù hợp.

## 18. Lỗi thường gặp

| Tình huống | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| Sửa attribute nhưng server không đổi | Chỉ gọi setter trên adapter | Gọi `modifyAttributes(adapter)` |
| Dùng adapter mới để update entry cũ | Thiếu trạng thái ban đầu, sai mục đích | `lookupContext` rồi sửa |
| Dùng `bind` trên DN đã tồn tại | Bind không phải upsert | Chọn update hoặc xử lý trùng DN |
| Sửa `uid` rồi mong DN tự đổi | Attribute khác tên entry | Dùng thao tác rename/move khi cần |
| `getDn()` bị hiểu là full DN | Bỏ qua `ContextSource.base` | Kiểm tra relative/full DN |
| Thêm member nhưng mất member cũ | `setAttributeValues` thay cả tập | Dùng add/remove theo nghiệp vụ |
| `getStringAttribute("member")` chỉ có một người | Member là đa trị | Đọc `getStringAttributes` |
| Ghi binary như String | Sai syntax/kiểu dữ liệu | Kiểm tra schema và dùng `byte[]` |
| Thay thuộc tính server-managed | Operational attribute không được sửa | Đọc theo đúng API, không modify |
| Cập nhật báo lỗi thiếu quyền | Service bind ACL hạn chế | Kiểm tra quyền và principal |
| Search trả entry nhưng update DN lỗi | DN cũ, rename, entry bị move | Lấy DN thật, xử lý race |
| Test setter pass nhưng test LDAP fail | Adapter không thay schema/server | Integration test với LDAP |
| Timeout được coi là rollback | Không rõ server đã áp dụng hay chưa | Xác minh trạng thái, retry có kiểm soát |
| Coi adapter là transaction đa entry | LDAP không tự gom nhiều entry | Thiết kế idempotency và bù trừ |

## 19. Kiểm thử DirContextAdapter

### 19.1. Unit test dựng một entry trong bộ nhớ

Bạn có thể kiểm tra getter/setter mà không cần kết nối LDAP:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", "lan")
    .build();

DirContextAdapter adapter = new DirContextAdapter(dn);
adapter.setAttributeValue("uid", "lan");
adapter.setAttributeValue("cn", "Nguyen Lan");

if (!"Nguyen Lan".equals(
        adapter.getStringAttribute("cn"))) {
    throw new AssertionError("Mapping không đúng");
}
~~~

Test này chứng minh **dữ liệu Java được đặt đúng trên adapter**. Nó không xác minh schema, ACL hoặc entry đã tồn tại trên LDAP server.

### 19.2. Integration test với LDAP test server

Chuẩn bị directory thử nghiệm (ví dụ embedded LDAP hoặc staging cô lập) có base `dc=example,dc=org`, OU `ou=people` và `ou=groups`. Kiểm thử cả các trường hợp thành công và lỗi:

| Test case | Kỳ vọng |
| --- | --- |
| `new DirContextAdapter` + `bind` | Server tạo entry đúng DN/attributes |
| Chỉ setter trên adapter | Server không thay đổi |
| `lookupContext` + setter + `modifyAttributes` | Trường mục tiêu thay đổi |
| Sửa số điện thoại thành giá trị cũ | Đảm bảo không gây tác động ngoài ý muốn |
| Đọc `getModificationItems()` | Phản ánh trạng thái sửa theo API của thư viện |
| `addAttributeValue("member", ...)` | Không mất các thành viên không liên quan |
| `setAttributeValues("member", ...)` | Phản ánh đúng ý nghĩa thay cả tập giá trị |
| Entry có DN chứa ký tự đặc biệt | DN được xây/tra cứu chính xác |
| User nằm dưới OU con | Không suy sai DN từ username |
| Thiếu `mail` | Mapper xử lý tùy chọn |
| `jpegPhoto` là binary | Không ép sai kiểu |
| Service account chỉ đọc thử modify | Server từ chối |
| Sửa attribute bắt buộc sai schema | Server từ chối |
| Tạo entry trùng DN | Không âm thầm ghi đè |
| Hai request sửa cùng thuộc tính | Phát hiện rủi ro lost update |
| LDAP mất kết nối sau khi gửi | Ứng dụng không báo thành công giả |
| TLS chứng chỉ sai | Không fallback sang LDAP plaintext |

### 19.3. Test phép sửa đa trị

Một bài test quan trọng:

1. Tạo group có `member=Lan` và `member=Minh`.
2. Thêm `Hoa`.
3. Đọc lại group.
4. Xác nhận cả Lan, Minh và Hoa đều còn trong membership.
5. Xóa Minh.
6. Đọc lại và xác nhận còn Lan/Hoa.
7. Thử thêm Hoa lần nữa; ghi nhận chính sách xử lý duplicate của server.

Khi so DN trong assertion test, dùng biểu diễn và ngữ nghĩa phù hợp với LDAP/JNDI, không suy từ thứ tự các giá trị được trả về.

### 19.4. Phân biệt các mức kiểm thử

- **Unit test:** object trong bộ nhớ, mapping và validations.
- **Integration test:** LDAP server, schema, DN, ACL, TLS và ModifyRequest.
- **Performance/concurrency test:** mức tải, số entry/attribute, race conditions và hiệu năng index/pool trên môi trường đại diện.

Không khẳng định adapter “tự động tối ưu số request” nếu chưa đo hoặc chưa xác minh chính xác implementation.

## 20. Bài tập thực hành

**Bối cảnh:** hệ thống quản lý nhân viên dùng `ContextSource.base = dc=example,dc=org`. Nhân viên `lan` ở `ou=people`, nhóm `developers` ở `ou=groups`. Hãy thực hiện các yêu cầu dưới đây với `LdapTemplate` và `DirContextAdapter`.

1. Tạo DN tương đối cho `uid=lan,ou=people` bằng `LdapNameBuilder`.
2. Dùng `lookupContext` lấy entry và in `getDn()` theo đúng ý nghĩa relative DN.
3. Đọc `cn`, `mail`; làm gì nếu `mail` không được trả về?
4. Đặt `telephoneNumber` mới. Dòng code nào thực sự gửi update tới server?
5. Xem `getModificationItems()` trước khi modify. Có thể coi dữ liệu đã được lưu chưa?
6. Thêm DN của `uid=hoa` vào attribute `member` của group. Vì sao không dùng mảng chỉ có Hoa với `setAttributeValues`?
7. Khi một member đã tồn tại, server có thể phản ứng ra sao với LDAP Modify ADD?
8. Nếu muốn chuyển Lan sang `ou=engineering`, chỉ sửa `department` có đủ không?
9. Khi hai request sửa phone cùng lúc, adapter có bảo vệ được lost update không?
10. Nếu service account chỉ có quyền đọc group, việc `addAttributeValue` thành công trong Java có đảm bảo `modifyAttributes` thành công không?
11. Tại sao không thể suy rằng `getStringAttribute("member")` trả toàn bộ thành viên?
12. Với attribute `jpegPhoto`, vì sao phải kiểm tra kiểu trước khi ép sang `String`?

**Gợi ý đáp án:**

1. `LdapNameBuilder.newInstance("ou=people").add("uid", "lan").build()`.
2. `DirContextOperations entry = ldapTemplate.lookupContext(dn)` rồi `entry.getDn()`; xác minh base.
3. Chọn chính sách optional/null và kiểm tra ACL/returning attributes.
4. `ldapTemplate.modifyAttributes(entry)`, không phải setter.
5. Chưa; đó là các thay đổi dự kiến ở phía client.
6. Thay cả mảng có thể xóa member cũ; dùng `addAttributeValue` hoặc Modify ADD trực tiếp.
7. Có thể từ chối giá trị trùng theo schema/matching rule.
8. Không; cần đổi DN/move entry bằng operation phù hợp.
9. Không; cần concurrency policy riêng.
10. Không; server sẽ kiểm tra ACL khi ghi.
11. Vì attribute `member` có thể chứa nhiều DN.
12. Vì LDAP có thuộc tính nhị phân, nên cần map theo schema.

## 21. Checklist trước khi triển khai

- [ ] Phân biệt `DirContextAdapter` với JNDI `DirContext`.
- [ ] Biết rõ adapter được **tạo mới** hay được **đọc từ server**.
- [ ] Làm rõ `getDn()` là relative hay full DN.
- [ ] Dùng `LdapNameBuilder` thay vì tự nối RDN từ input.
- [ ] Không coi setter là thao tác ghi mạng.
- [ ] Dùng `bind` cho entry mới, `modifyAttributes` cho entry hiện có.
- [ ] Biết `getModificationItems()` chỉ phản ánh các thay đổi dự kiến ở phía Java.
- [ ] Không dùng snapshot thiếu thuộc tính để suy trạng thái đầy đủ của server.
- [ ] Phân biệt set toàn bộ tập giá trị và add/remove một giá trị.
- [ ] Kiểm tra schema, single-value/multi-value, binary và operational attributes.
- [ ] Kiểm tra authorization ở ứng dụng và ACL trên LDAP server.
- [ ] Bảo vệ credentials và TLS; không log toàn bộ adapter.
- [ ] Xử lý mất kết nối/timeout mà không kết luận bừa trạng thái đã ghi.
- [ ] Thiết kế concurrency khi nhiều tác vụ cùng sửa entry.
- [ ] Có unit test adapter và integration test với LDAP directory đại diện.

## 22. Tóm tắt

**`DirContextAdapter` giữ DN và attributes của một LDAP entry trong bộ nhớ, đồng thời hỗ trợ ghi nhận những thay đổi do ứng dụng tạo ra để `LdapTemplate` có thể gửi operation thích hợp.** `DirContextOperations` là interface dùng để thao tác trên biểu diễn này.

Có hai quy trình phải luôn phân biệt:

- **Tạo mới:** dựng `new DirContextAdapter(dn)`, đặt `objectClass` và các thuộc tính bắt buộc, rồi gọi `ldapTemplate.bind(adapter)`.
- **Cập nhật:** gọi `ldapTemplate.lookupContext(dn)`, sửa trên adapter rồi gọi `ldapTemplate.modifyAttributes(adapter)`.

DN không tự đổi khi một field trong attributes đổi. Setter không tự lưu lên server. Một tập member không được xem như một field đơn trị. Và adapter không thay thế schema, ACL, authentication, TLS, concurrency control hay việc kiểm thử LDAP trên môi trường đại diện.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP Javadoc — DirContextAdapter](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP Javadoc — DirContextOperations](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Java SE — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Java SE — ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
