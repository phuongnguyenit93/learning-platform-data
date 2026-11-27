# Generated attribute và server-side default

## Mục tiêu học tập

Khi tạo một LDAP entry bằng **Spring LDAP**, ứng dụng thường cung cấp DN, các lớp đối tượng (`objectClass`) và những thuộc tính bắt buộc theo schema. Tuy nhiên, sau khi tạo thành công, entry có thể có thêm các thuộc tính mà client **không gửi trong yêu cầu bind**: thời điểm tạo, người tạo, mã định danh do máy chủ cấp hoặc những giá trị do chính sách của directory tự bổ sung.

Bài học thuộc chương **Bind và tạo entry**, giúp bạn:

1. Phân biệt **generated attribute**, **operational attribute** và **server-side default**.
2. Hiểu vai trò của **schema**, `objectClass`, quyền truy cập (ACL) và cấu hình LDAP server đối với giá trị được sinh.
3. Tạo một entry bằng `LdapTemplate.bind(...)`, sau đó **đọc lại từ máy chủ** để xác định thuộc tính thực tế.
4. Biết cách yêu cầu các operational attribute vốn có thể bị bỏ qua trong kết quả tra cứu mặc định.
5. Thiết kế nghiệp vụ không phụ thuộc mù quáng vào mặc định, không ghi đè thuộc tính máy chủ quản lý và kiểm thử khác biệt giữa các LDAP server.

Các nguyên tắc này vẫn hữu ích nếu ứng dụng dùng `LdapClient`, JNDI hoặc ODM của Spring LDAP: thuộc tính nào tự sinh và khi nào xuất hiện chủ yếu do **dịch vụ thư mục**, không do API Java tự quyết định.

## 1. Hai nhóm dữ liệu khi tạo LDAP entry

Giả sử ứng dụng muốn tạo nhân viên Lan dưới nhánh `ou=people`:

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
~~~

Trong yêu cầu tạo entry, ứng dụng trực tiếp chỉ định các giá trị trên. Nhưng khi đọc lại từ một máy chủ OpenLDAP có hỗ trợ các thuộc tính tương ứng, ta **có thể** nhìn thấy:

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
entryUUID: 779d229c-6d12-103f-914f-a2b3c4d5e6f7
createTimestamp: 20261127032000Z
creatorsName: cn=directory-writer,dc=example,dc=org
~~~

Ba dòng cuối chỉ là **minh họa**; giá trị, thuộc tính thực sự hiện diện và quyền đọc chúng phụ thuộc máy chủ. Chẳng hạn Active Directory sử dụng `objectGUID` làm mã định danh của đối tượng; không thể mặc định mọi hệ thống LDAP đều có `entryUUID` theo cùng cách.

Cách hình dung luồng tạo entry:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring LDAP"] --> B["Tạo DN và Attributes"]
    B --> C["LdapTemplate.bind(...)"]
    C --> D["LDAP server kiểm tra parent, ACL và schema"]
    D --> E{"Yêu cầu hợp lệ?"}
    E -->|Không| F["Trả lỗi: quyền, schema, tên trùng..."]
    E -->|Có| G["Server lưu entry"]
    G --> H["Server tính/sinh thuộc tính theo triển khai và cấu hình"]
    H --> I["Client lookup/search lại, yêu cầu thuộc tính cần thiết"]
~~~

Điểm quan trọng: **`bind(...)` không phải cơ chế để yêu cầu Spring LDAP sinh `entryUUID` hay `createTimestamp`.** Các giá trị đó được quản lý phía server khi tính năng tương ứng tồn tại.

## 2. Phân biệt ba khái niệm

Các thuật ngữ này có quan hệ nhưng không đồng nghĩa.

| Khái niệm | Bản chất | Ví dụ | Ai quyết định giá trị? |
| --- | --- | --- | --- |
| **Generated attribute** (thuộc tính sinh tự động) | Giá trị được gán hoặc tính tự động trong quá trình tạo/cập nhật entry | `entryUUID` trên server hỗ trợ; `objectGUID` trong AD | LDAP server hoặc module mở rộng |
| **Operational attribute** (thuộc tính vận hành) | Nhóm thuộc tính dùng để quản lý directory, được định nghĩa theo schema với `USAGE` thích hợp; thường không trả về khi chỉ yêu cầu thuộc tính người dùng | `createTimestamp`, `creatorsName`, `modifyTimestamp`, `subschemaSubentry` | LDAP server quản lý hoặc cung cấp |
| **Server-side default** (mặc định phía server) | Một giá trị/chính sách mà máy chủ hoặc plugin tự áp dụng khi client không cung cấp | Giá trị gán bởi overlay/plugin, quy tắc khởi tạo tài khoản đặc thù | Cấu hình và khả năng của server |

Một thuộc tính có thể vừa **operational** vừa **generated**. Ngược lại, một server-side default có thể được ghi vào **thuộc tính ứng dụng thông thường**, tùy plugin hoặc chính sách doanh nghiệp.

**LDAP không có quy tắc chung tương đương `DEFAULT` của cột SQL cho mọi attribute.** Schema LDAP chủ yếu mô tả loại thuộc tính, quan hệ objectClass, cú pháp, quy tắc so khớp và các thuộc tính bắt buộc/được phép. Việc một giá trị sẽ tự được điền khi tạo entry là **hành vi cần xác minh trên server đích**.

### 2.1. Thuộc tính máy chủ quản lý thường gặp

| Thuộc tính | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `createTimestamp` | Thời điểm tạo entry do máy chủ ghi nhận | Operational; có thể không trả về nếu không yêu cầu rõ |
| `creatorsName` | DN của danh tính được server ghi nhận là người tạo | Operational; khả năng hiển thị phụ thuộc ACL và server |
| `modifyTimestamp` | Thời điểm sửa đổi được server ghi nhận | Có thể được cập nhật sau mỗi thay đổi; không dùng làm định danh |
| `modifiersName` | Danh tính được server ghi nhận đã sửa entry | Không nhất thiết trùng DN người dùng cuối của ứng dụng |
| `entryUUID` | Mã định danh entry trên các directory hỗ trợ cơ chế tương ứng | Không phổ quát trên mọi LDAP server; không tự cấu hình giá trị |
| `structuralObjectClass` | Lớp structural mà server xác định từ tập `objectClass` | Thuộc tính vận hành/phát sinh theo cách server biểu diễn schema |
| `objectGUID` | Định danh nhị phân của object trên Active Directory | Cách lấy và kiểu dữ liệu khác `entryUUID`; không ép thành chuỗi đơn giản |
| `whenCreated` | Thời điểm tạo trong Active Directory | Thuộc tính cụ thể của AD; không mặc định có trên OpenLDAP |

Một số thuộc tính chỉ tồn tại hoặc có dạng khác ở từng triển khai. Ví dụ `entryUUID` thuộc cơ chế được mô tả trong RFC 4530, trong khi `objectGUID` là thuộc tính đặc trưng của Active Directory. Đừng viết logic dùng trực tiếp tên `entryUUID` cho mọi directory mà không có bước kiểm tra khả năng.

### 2.2. Có phải mọi operational attribute đều bất biến?

Không. `createTimestamp` mô tả thời điểm tạo và thường không đổi; `modifyTimestamp` được quản lý để phản ánh thay đổi theo chính sách server; `modifiersName` có thể đổi sau cập nhật. Nhóm operational không tự đồng nghĩa với **read-only vĩnh viễn**, nhưng nhiều thuộc tính có cờ `NO-USER-MODIFICATION` hoặc được server bảo vệ. Client không nên tự ghi vào chúng nếu không có cơ chế đặc biệt được nhà cung cấp cho phép.

## 3. Schema quyết định những gì khi bind?

Để hiểu mặc định, cần phân biệt **thuộc tính bắt buộc do schema yêu cầu** với **thuộc tính được máy chủ tự sinh**.

Với `inetOrgPerson`, các lớp cha như `person` thường yêu cầu có `cn` và `sn`. Trên ví dụ minh họa, ứng dụng cung cấp:

~~~ldif
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Lan Tran
sn: Tran
uid: lan
~~~

Server kiểm tra xem thuộc tính, objectClass và cấu trúc DN có hợp lệ hay không. Nếu `sn` bắt buộc nhưng client bỏ qua, kết quả thường là **lỗi schema**; không nên mong máy chủ tự điền họ của nhân viên.

Sự khác biệt:

- **`MUST`:** thuộc tính mà entry thuộc objectClass liên quan phải có. Không có nghĩa server sẽ sinh mặc định cho thuộc tính đó.
- **`MAY`:** thuộc tính được cho phép nhưng không bắt buộc. Không có nghĩa server sẽ tạo nó.
- **`NO-USER-MODIFICATION`:** ràng buộc theo schema cho biết user/client thông thường không được tự thay đổi thuộc tính đó.
- **`USAGE directoryOperation`** hoặc kiểu operational tương ứng: phục vụ hoạt động quản lý directory; cách truy xuất có thể khác nhóm user attributes.

Một số entry bắt buộc phải có thuộc tính làm RDN theo quy tắc naming của server. Ví dụ `uid=lan,...` thường cần `uid: lan` trong dữ liệu entry. Trong code tạo entry, **hãy cung cấp rõ ràng** các giá trị bắt buộc và định danh được ứng dụng quản lý.

### Những giá trị không nên trông chờ server tự tạo

| Trường | Có tự sinh theo mặc định LDAP chung không? | Hướng xử lý |
| --- | --- | --- |
| `uid` | Không | Ứng dụng/quy trình cấp danh tính chỉ định một giá trị phù hợp |
| `cn`, `sn` | Không | Cung cấp theo schema và nghiệp vụ |
| `mail` | Không | Cung cấp khi nghiệp vụ yêu cầu, kiểm tra cú pháp và quyền |
| `userPassword` | Không có mặc định LDAP chung | Tạo/cập nhật theo quy trình xác thực được phê duyệt; không giả định password tự phát sinh |
| `uidNumber`, `gidNumber` cho POSIX account | Không có bộ cấp số tự động chuẩn trên mọi server | Dùng chính sách cấp số/phần mở rộng cụ thể; bảo đảm tránh trùng |
| `memberOf` | Không có giá trị mặc định phổ quát | Tùy cơ chế duy trì quan hệ nhóm của server/plugin |
| `createTimestamp` | Thường do server hỗ trợ quản lý | Không tự ghi, đọc lại theo cơ chế operational attributes |

Giữa các server có thể có plugin cấp số, tự tạo thuộc tính, kích hoạt tài khoản hoặc sinh password ngẫu nhiên; đó là **cấu hình sản phẩm**, không phải hành vi mặc định của Spring LDAP.

## 4. Ví dụ: tạo một entry bằng `LdapTemplate.bind(...)`

Giả sử ứng dụng Spring đã cấu hình bean `LdapTemplate` với `ContextSource` có base DN `dc=example,dc=org`. Nhánh `ou=people` đã tồn tại và tài khoản bind có quyền thêm child tại đó.

Ví dụ Java:

~~~java
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonCreationService {

    private final LdapTemplate ldapTemplate;

    public PersonCreationService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name createLan() {
        // DN tương đối với base dc=example,dc=org.
        Name dn = LdapNameBuilder.newInstance()
            .add("ou", "people")
            .add("uid", "lan")
            .build();

        // true: tra cứu tên attribute không phân biệt hoa/thường.
        Attributes attrs = new BasicAttributes(true);

        Attribute objectClass = new BasicAttribute("objectClass");
        objectClass.add("top");
        objectClass.add("person");
        objectClass.add("organizationalPerson");
        objectClass.add("inetOrgPerson");
        attrs.put(objectClass);

        attrs.put("uid", "lan");
        attrs.put("cn", "Lan Tran");
        attrs.put("sn", "Tran");
        attrs.put("mail", "lan@example.org");

        // Không tự put("entryUUID", ...), put("createTimestamp", ...).
        ldapTemplate.bind(dn, null, attrs);

        return dn;
    }
}
~~~

**Phân tích:**

1. `LdapNameBuilder` xây DN có cấu trúc đúng và escape giá trị RDN; không nối trực tiếp đầu vào người dùng thành DN.
2. `Attributes` chứa các dữ liệu mà client muốn lưu và những trường cần đáp ứng schema.
3. `ldapTemplate.bind(dn, null, attrs)` gửi yêu cầu tạo entry đến LDAP server; đối số `null` ở vị trí object tuân theo cách dùng phổ biến khi bind bằng JNDI attributes.
4. LDAP server xác minh parent, DN trùng, objectClass, cú pháp, ACL và các quy tắc bổ sung.
5. Nếu thao tác thành công, server có thể tự tạo hoặc ghi các operational attribute tương ứng; hàm `bind` không trả về một đối tượng chứa toàn bộ giá trị được server sinh.

> **Thận trọng:** Dữ liệu trong ví dụ chỉ thích hợp cho directory thử nghiệm có schema hỗ trợ `inetOrgPerson`. Nó **không** tự kích hoạt tài khoản đăng nhập, không tạo mật khẩu và không chắc đáp ứng mọi chính sách nhân sự hoặc cấu hình Active Directory.

### Tại sao không gửi giá trị generated ngay từ client?

Một cách làm sai thường gặp:

~~~java
// Không làm như vậy cho server-managed attributes:
attrs.put("entryUUID", "my-own-id");
attrs.put("createTimestamp", "20261127000000Z");
ldapTemplate.bind(dn, null, attrs);
~~~

LDAP server có thể từ chối với lỗi **constraint violation**, **schema violation**, **insufficient access** hoặc lỗi cụ thể khác vì thuộc tính do server quản lý và không cho phép user tự đặt. Kể cả khi một server cho phép cách ghi riêng theo quyền quản trị, logic ứng dụng vẫn phải tuân thủ hợp đồng nhà cung cấp và quy trình nhập dữ liệu; không nên coi đó là thao tác bind thông thường.

## 5. Đọc lại thuộc tính được sinh sau khi tạo

Một sai lầm phổ biến là tưởng rằng `attrs` trong ví dụ trên tự được bổ sung `entryUUID` hoặc `createTimestamp` ngay khi `bind` trả về. Thực tế, `attrs` là đối tượng **client đã chuẩn bị**. Để có thông tin server đã lưu, phải **lookup hoặc search lại** entry.

### 5.1. Vì sao lookup mặc định có thể không thấy?

LDAP phân biệt các **user attributes** với **operational attributes**. Theo hành vi LDAP Search thông thường, khi client không nêu rõ thuộc tính cần lấy, server trả về các user attributes được phép đọc, còn nhiều operational attributes **không xuất hiện mặc định**.

Vì vậy, đoạn mã tương tự:

~~~java
// Có thể không thấy createTimestamp, dù server có quản lý nó.
var context = ldapTemplate.lookupContext(dn);
String createdAt = context.getStringAttribute("createTimestamp");
~~~

có thể trả `null`. Giá trị `null` **chưa đủ chứng minh** rằng server không ghi thuộc tính; cần hỏi đúng danh sách attribute, kiểm tra ACL và khả năng server.

### 5.2. Yêu cầu tên operational attribute cụ thể

`LdapTemplate` có overload `lookup` cho phép chỉ định những tên thuộc tính cần trả về:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

// dn là Name đã tạo ở ví dụ trên.
String[] requested = {
    "entryUUID",
    "createTimestamp",
    "creatorsName"
};

AttributesMapper<Map<String, String>> mapper = attrs -> {
    Map<String, String> values = new LinkedHashMap<>();

    for (String attrId : requested) {
        Attribute attr = attrs.get(attrId);
        if (attr != null && attr.size() > 0) {
            // Chỉ áp dụng cho các attribute dạng chuỗi trong ví dụ này.
            values.put(attrId, String.valueOf(attr.get()));
        }
    }

    return values;
};

Map<String, String> generated = ldapTemplate.lookup(
    dn,
    requested,
    mapper
);

// Các giá trị có thể thiếu theo server/ACL:
// generated.get("entryUUID")
// generated.get("createTimestamp")
// generated.get("creatorsName")
~~~

Đoạn mã trên minh họa cách **yêu cầu và đọc**, không khẳng định mỗi server trả đủ ba thuộc tính. Với Active Directory, `objectGUID` là dữ liệu nhị phân, phải yêu cầu và giải mã theo kiểu binary đúng, không dùng mặc định `String.valueOf(attr.get())` để tạo GUID.

**Quy trình đúng:** tạo entry thành công → lookup tên thuộc tính cần thiết → kiểm tra thuộc tính trả về → lưu hoặc sử dụng giá trị server đã sinh. Nếu giá trị không có, trước hết kiểm tra hỗ trợ, ACL và chính sách trả về thuộc tính; không tự phát sinh một `entryUUID` “thay thế” rồi giả vờ đó là mã do directory cấp.

### 5.3. Cơ chế chọn operational attributes bằng `+`

Theo RFC 3673, LDAP có ký hiệu chọn thuộc tính `+` để yêu cầu **tất cả operational attributes** được server cho phép trả về. Trong khi đó, ký hiệu `*` chọn các **user attributes**.

Ví dụ lệnh kiểm tra với công cụ `ldapsearch` trên máy chủ hỗ trợ:

~~~bash
ldapsearch -H ldaps://ldap.example.org \
  -D "cn=directory-reader,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" "*" "+"
~~~

Lệnh yêu cầu cả user attributes và operational attributes mà server cho phép đọc. Không phải mọi directory hoặc client đều hỗ trợ lựa chọn `+` theo cùng cách; trong ứng dụng chạy thật, **yêu cầu rõ thuộc tính cần dùng** thường phù hợp hơn vì giảm dữ liệu truyền và tránh lộ thông tin không cần thiết.

Các tên `+` và `*` ở đây là **selector của LDAP Search**, không phải tên attribute có thể ghi bằng `bind`.

## 6. Server-side default hoạt động như thế nào?

Ngoài thuộc tính do directory quản lý, một số LDAP server còn cho phép cấu hình **giá trị mặc định phía server** bằng plugin, overlay, rule hoặc module riêng.

Giả sử một directory đã cấu hình plugin khởi tạo người dùng mới với quy tắc nghiệp vụ:

~~~text
Khi bind entry inetOrgPerson dưới ou=people:
  nếu thuộc tính employeeType chưa được cung cấp
    → tự đặt employeeType = "internal"
~~~

Nếu server và schema cho phép cấu hình này, sau khi tạo entry và lookup lại có thể thấy:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
employeeType: internal
~~~

**Đây là tình huống giả định để minh họa**, không phải một mặc định chuẩn có sẵn của OpenLDAP, Active Directory hay Spring LDAP. Với server khác, hoàn toàn có thể **không tồn tại** `employeeType` hoặc giá trị do plugin đặt khác.

### Phân biệt ba nơi cung cấp giá trị

~~~mermaid
flowchart LR
    A["Yêu cầu tạo entry"] --> B{"Giá trị do ai quyết định?"}
    B -->|"Client"| C["Gửi trong Attributes của bind"]
    B -->|"Schema yêu cầu"| D["Client cung cấp hoặc server phải có cơ chế hợp lệ"]
    B -->|"Server policy / plugin"| E["Server có thể bổ sung khi xử lý tạo"]
    C --> F["Entry đã lưu"]
    D --> F
    E --> F
    F --> G["Lookup lại để xác minh"]
~~~

Ví dụ đối với trường `employeeType`:

| Cách thực hiện | Kết quả | Hệ quả vận hành |
| --- | --- | --- |
| Ứng dụng gửi `employeeType=internal` | Giá trị xuất phát từ client | Có thể kiểm thử ngay ở lớp ứng dụng, nhưng cần thống nhất giữa các client |
| Server tự gán `employeeType=internal` | Giá trị do policy/plugin khi tạo | Các client dùng chung chính sách, nhưng phụ thuộc cấu hình và phiên bản server |
| Schema chỉ cho phép `employeeType` nhưng không đặt policy | Không có giá trị nếu client bỏ qua | Không phát sinh default chỉ vì attribute là `MAY` |
| Server đánh dấu attribute là bắt buộc nhưng không tự gán | Bind thiếu dữ liệu sẽ thất bại | Client phải gửi giá trị hoặc có rule tạo hợp lệ |

**Không có mặc định nào được đảm bảo chỉ bằng việc sử dụng `LdapTemplate.bind(...)`.** Server-side defaults phải được mô tả bằng tài liệu cấu hình và xác minh bằng kiểm thử với đúng LDAP server mục tiêu.

### 6.1. Thứ tự kiểm tra và chính sách bổ sung

Tùy triển khai, LDAP server có thể kiểm tra schema, gọi plugin, gán giá trị và áp chính sách ở các giai đoạn khác nhau. Không nên viết logic ứng dụng dựa trên giả định cố định về thứ tự nội bộ mà server không công bố.

Một số hệ thống có chính sách chỉ đặt default khi trường vắng mặt, một số ghi đè giá trị client, một số từ chối yêu cầu trái policy. Khi cần tính nhất quán, hãy định nghĩa rõ:

- Khi client **không gửi** attribute, server làm gì?
- Khi client gửi giá trị **khác mặc định**, server cho phép, thay thế hay từ chối?
- Khi người dùng sửa attribute sau khi tạo, default có còn được áp lại không?
- Khi di chuyển entry sang OU khác, policy có phụ thuộc parent DN và tự thay đổi dữ liệu không?
- Quyền đọc/ghi thuộc tính mặc định được áp thế nào?

Cần kiểm thử cả **bind** và **modifyAttributes** vì không phải plugin nào cũng chạy theo cùng một cách ở cả hai thao tác.

## 7. Dùng các giá trị generated trong nghiệp vụ

### 7.1. DN và mã định danh do server cấp

DN có thể đổi khi một entry được **rename** hoặc **move**:

~~~text
uid=lan,ou=people,dc=example,dc=org
          ↓ move
uid=lan,ou=alumni,dc=example,dc=org
~~~

Nếu directory cung cấp mã định danh entry có tính ổn định qua đổi DN, ứng dụng có thể dùng giá trị đó để đối soát. Ví dụ:

- Trên OpenLDAP/các hệ hỗ trợ RFC 4530, dùng `entryUUID` nếu thực sự có, nếu ACL cho phép đọc.
- Trên Active Directory, cân nhắc `objectGUID` với cách xử lý giá trị nhị phân phù hợp.
- Nếu hệ thống không cung cấp định danh tương đương, cần chiến lược nhận diện riêng do ứng dụng và nghiệp vụ xác định.

**Không đồng nhất** `uid`, DN và `entryUUID`: `uid` là thuộc tính được cấp theo chính sách, DN là tên đường dẫn có thể đổi, còn `entryUUID` trên hệ hỗ trợ là mã định danh do server quản lý.

### 7.2. Dấu thời gian tạo và sửa

`createTimestamp` và `modifyTimestamp` thường biểu diễn thời gian theo **LDAP Generalized Time**, chẳng hạn:

~~~text
20261127032000Z
~~~

Giá trị kết thúc bằng `Z` thể hiện UTC trong ví dụ. Cần parse đúng định dạng và biến thể được LDAP/server sử dụng (có thể có phần giây phân số hoặc offset theo cú pháp), rồi mới chuyển sang `Instant` hoặc múi giờ hiển thị.

Không đọc rồi ghi đè lại `createTimestamp` bằng thời gian từ máy ứng dụng. Đồng hồ ứng dụng, đồng hồ directory server, replication và độ trễ đọc có thể khác nhau. Với nghiệp vụ cần “thời điểm giao dịch” của hệ thống ứng dụng, hãy lưu dấu thời gian riêng theo thiết kế thay vì gán lại thuộc tính máy chủ quản lý.

### 7.3. Ai là “người tạo” entry?

`creatorsName` thường ghi nhận **danh tính LDAP mà server nhìn thấy trong thao tác tạo**, ví dụ DN của service account đang bind. Nếu một web app dùng cùng tài khoản dịch vụ cho mọi thao tác, `creatorsName` không nhất thiết chỉ ra nhân viên cuối đã bấm nút “Tạo”.

Vì vậy:

- Không dùng `creatorsName` làm bằng chứng duy nhất về **người dùng cuối** đã yêu cầu tạo dữ liệu.
- Nếu nghiệp vụ cần audit user thật, ghi nhận trong hệ thống audit có kiểm soát, kết hợp thông tin phiên và thao tác.
- Tránh công khai không cần thiết DN tài khoản dịch vụ qua API hoặc log.

## 8. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `createTimestamp` không xuất hiện sau bind | Lookup không yêu cầu operational attributes, server không hỗ trợ hoặc ACL ẩn thuộc tính | Lookup có danh sách attrIds rõ ràng, kiểm tra server/schema/ACL |
| Bind thất bại khi gửi `entryUUID` | Server quản lý thuộc tính, không cho client tự gán | Bỏ thuộc tính khỏi request; đọc lại sau tạo |
| Bind thiếu `sn` bị từ chối | `person` yêu cầu `sn` theo schema | Cung cấp giá trị bắt buộc; không kỳ vọng server tạo mặc định |
| Không thấy `employeeType` được tự điền | Server không cấu hình rule/plugin như dự kiến | Kiểm tra chính sách tại đúng môi trường và thử lookup sau tạo |
| Code chạy trên OpenLDAP nhưng lỗi với AD | Tên/kiểu operational attribute và schema khác | Thiết kế adapter theo provider, không suy diễn tương đương |
| Giá trị `creatorsName` khác nhân viên tạo trên UI | Server ghi service account bind | Dùng audit nghiệp vụ cho danh tính user cuối |
| Tạo cùng DN hai lần | DN đã được dùng, không phải default/generation | Xử lý `NameAlreadyBoundException` và quy tắc định danh |
| Không xem được thuộc tính sau tạo | ACL không cho đọc hoặc replication chưa đồng bộ | Xem quyền read và vị trí máy chủ được truy vấn |
| Tự kiểm tra rồi gọi bind vẫn gặp trùng DN | Entry có thể được tạo bởi client khác giữa hai lệnh | Bắt lỗi ngay tại `bind`; không tin tuyệt đối vào bước check |
| Dữ liệu nhạy cảm lộ qua logging | Log tất cả attribute hoặc phản hồi LDAP | Chỉ log thông tin cần thiết; bảo vệ TLS và quyền truy cập |

### Bắt đúng lỗi khi tạo entry

Một chương trình tạo dữ liệu nên phân biệt lỗi **đã có DN**, **schema không hợp lệ** và **thiếu quyền**. Ví dụ:

~~~java
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.SchemaViolationException;

try {
    ldapTemplate.bind(dn, null, attrs);
} catch (NameAlreadyBoundException ex) {
    // Entry đã có tại DN này; báo xung đột thay vì ghi đè.
} catch (SchemaViolationException ex) {
    // Thiếu objectClass/attribute, hoặc vi phạm schema.
} catch (NoPermissionException ex) {
    // Tài khoản bind không có quyền tạo child ở parent.
}
~~~

Đoạn mã minh họa việc phân loại lỗi; không nên nuốt ngoại lệ rồi báo tạo thành công. Nếu cần triển khai cụ thể, chuyển thành lỗi nghiệp vụ hoặc lỗi vận hành có thông điệp phù hợp.

## 9. Kiểm thử generated attribute và server default

Nên dùng LDAP server thử nghiệm có schema và policy tương ứng với môi trường mục tiêu. Có thể sử dụng một server riêng hoặc test container phù hợp; mục tiêu là **quan sát hành vi thật của server**. Mock `LdapTemplate` chỉ kiểm tra việc ứng dụng gọi API, không chứng minh giá trị được sinh.

| Ca thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Tạo entry tối thiểu hợp lệ | Cung cấp DN, objectClass và các trường MUST | Bind thành công; lookup lại được entry |
| Đọc operational attribute | Server hỗ trợ `createTimestamp` và cho phép đọc | Yêu cầu rõ tên thuộc tính sẽ nhận giá trị tương ứng |
| Lookup mặc định không hiện thuộc tính | Gọi lookup không chọn operational attributes | Không kết luận server không có thuộc tính |
| Định danh do server cấp | Server hỗ trợ `entryUUID` hoặc cơ chế tương đương | Giá trị được tạo và đọc theo đúng provider |
| Chặn client tự ghi attribute vận hành | Cố gửi `createTimestamp` khi bind | Server từ chối theo schema/chính sách, không ghi giá trị giả |
| Thiếu trường bắt buộc | Bỏ `sn` của `person` | Bind thất bại nếu server thực thi schema |
| Có rule default phía server | Bỏ `employeeType` khi bind trên server thử nghiệm đã cấu hình rule | Lookup lại nhận giá trị policy mong đợi |
| Không có rule default | Bỏ `employeeType` trên server không có rule | Không tự xuất hiện giá trị |
| Client gửi giá trị khác default | Tạo với `employeeType=external` | Hành vi đúng như chính sách server đã định nghĩa |
| Update sau tạo | Sửa `mail` hoặc `description` | Kiểm tra `modifyTimestamp` và policy update nếu server hỗ trợ |
| Đổi DN | Move/rename entry đã tạo | Kiểm tra định danh ổn định của server, nếu hỗ trợ |
| Thiếu quyền đọc operational attribute | Bind dưới account có quyền create nhưng quyền read bị hạn chế | Phân biệt trường hợp ACL ẩn với giá trị chưa được sinh |
| Tạo trùng DN | Gọi bind lại cùng DN | Nhận lỗi trùng tên và giữ dữ liệu entry gốc |

### Tình huống thực hành

Một dịch vụ nhân sự muốn tạo tài khoản mới và lưu mã định danh do directory cấp vào database nội bộ. Hãy thiết kế quy trình:

1. Kiểm tra `uid` do ứng dụng cấp và chuẩn bị đầy đủ attribute bắt buộc theo schema.
2. Dựng DN bằng `LdapNameBuilder`, gửi `LdapTemplate.bind(...)` bằng kết nối được bảo vệ qua LDAPS/StartTLS.
3. Khi bind thành công, gọi lookup yêu cầu **đúng thuộc tính định danh server hỗ trợ** (`entryUUID` hoặc loại tương đương).
4. Nếu không nhận được ID, phân loại nguyên nhân: server không hỗ trợ, ACL không cho đọc, dữ liệu chưa sẵn sàng hay cấu hình khác.
5. Lưu mối liên kết giữa ID nội bộ và ID LDAP; đặt quy tắc retry/đối soát khi bind đã thành công nhưng việc lưu database thất bại.
6. Kiểm thử lại quy trình với một account có quyền tối thiểu và không ghi giá trị nhạy cảm trong log.

> Lưu ý về tính nhất quán: LDAP bind và lệnh insert/update database thông thường là **hai hệ thống giao dịch khác nhau**. Không mặc định cả hai sẽ tự rollback cùng lúc. Cần cơ chế đối soát hoặc quy trình bù trừ phù hợp.

## 10. Câu hỏi tự kiểm tra

1. `objectClass` cho phép thuộc tính `mail` (`MAY`). Điều đó có đồng nghĩa server sẽ tự gán `mail` khi client không gửi không?
2. Vì sao lookup mặc định không trả `createTimestamp` chưa đủ để khẳng định thuộc tính chưa được sinh?
3. `entryUUID` và `objectGUID` có phải cùng tên/kiểu dữ liệu trên mọi LDAP server không?
4. Vì sao không nên tự ghi `createTimestamp` vào `BasicAttributes` trước khi gọi `bind`?
5. `creatorsName` có luôn chỉ ra nhân viên cuối cùng thực hiện thao tác trên giao diện web không?
6. Một server tự đặt `employeeType=internal` nhờ plugin. Nếu chuyển sang server khác không có plugin đó, ứng dụng phải làm gì?
7. Sau khi tạo entry thành công, lookup ID thất bại do thiếu quyền. Bạn nên xử lý thế nào để không vô tình tạo thêm entry trùng?
8. Với đồng bộ dữ liệu qua nhiều hệ thống, vì sao cần đối soát sau khi lưu ID do LDAP server cấp?

## 11. Ghi nhớ

Trong **Spring LDAP**, `LdapTemplate.bind(...)` gửi dữ liệu tạo entry đến LDAP server; các thuộc tính **do server sinh hoặc quản lý** phải được xác minh bằng việc đọc lại. Operational attributes như `createTimestamp`, `creatorsName` và `modifyTimestamp` thường không xuất hiện trong kết quả tra cứu mặc định nếu không được yêu cầu. Những thuộc tính định danh như `entryUUID` hay `objectGUID` tùy directory, khác nhau về tên và biểu diễn.

**Schema không tự tạo default cho mọi thuộc tính.** Ứng dụng phải cung cấp dữ liệu bắt buộc, còn server-side default phụ thuộc plugin, chính sách và triển khai cụ thể. Thiết kế vững chắc cần phân biệt giá trị do client gửi, giá trị do server tự gán và thuộc tính operational; xử lý đúng lỗi bind, ACL, khác biệt nhà cung cấp và tình huống kết nối/hệ thống khác không đồng bộ.

## Tài liệu tham khảo

- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): objectClass, schema, operational attributes và các thuộc tính vận hành chuẩn.
- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Add, Search và cách chọn thuộc tính cần trả về.
- [RFC 3673 — LDAP All Operational Attributes](https://www.rfc-editor.org/rfc/rfc3673): selector `+` trong LDAP Search.
- [RFC 4530 — Lightweight Directory Access Protocol (LDAP) entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530): thuộc tính `entryUUID` trên hệ hỗ trợ.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `bind(...)`, `lookup(...)` và `AttributesMapper`.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): cách xây DN bằng `LdapNameBuilder`, làm việc với `ContextSource`.
