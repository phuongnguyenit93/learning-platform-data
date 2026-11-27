# DirContextOperations và DirContextAdapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `DirContextOperations`, `DirContextAdapter` của Spring LDAP với `javax.naming.directory.DirContext` của JNDI.
- Giải thích vì sao `ContextMapper` nhận một đối tượng đại diện entry, trong khi `AttributesMapper` chỉ nhận tập thuộc tính.
- Dùng `getDn()`, `getStringAttribute(...)`, `getStringAttributes(...)` và `getAttributes()` để ánh xạ dữ liệu directory thành DTO.
- Thao tác thêm, thay thế, xóa giá trị bằng `setAttributeValue(...)`, `setAttributeValues(...)`, `addAttributeValue(...)` và `removeAttributeValue(...)`, đồng thời hiểu rằng thay đổi trên adapter **chưa tự động ghi lên LDAP server**.
- Phân biệt adapter được tạo để **bind entry mới** với adapter nhận từ `lookupContext(...)` để **modify entry hiện có**.
- Thiết kế và kiểm thử việc xử lý DN, attribute đa giá trị, schema, lỗi, ACL, TLS và concurrent requests an toàn.

Bài thuộc chương **Mapping kết quả** của module **SPRING_LDAP**. Spring LDAP hỗ trợ làm việc với DN, schema, filter, tìm kiếm, `LdapTemplate`, `LdapClient` và ODM. Trong những thao tác đó, hai kiểu `DirContextOperations` và `DirContextAdapter` đặc biệt hữu ích khi ứng dụng cần **vừa đọc thông tin entry, vừa biết DN, vừa có khả năng sửa thuộc tính** mà không phải tự quản lý JNDI `DirContext` trong mỗi service.

## 1. Bối cảnh: từ LDAP entry sang đối tượng Java

Giả sử LDAP directory có entry nhân viên:

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
~~~

Ứng dụng muốn đọc entry thành:

~~~java
public record EmployeeView(
    String dn,
    String uid,
    String commonName,
    String email
) {}
~~~

Và muốn hỗ trợ chỉnh `telephoneNumber` khi nhân viên cập nhật hồ sơ.

Có hai nhu cầu không hoàn toàn giống nhau:

1. **Chuyển kết quả tìm kiếm thành DTO** cho màn hình: đọc các thuộc tính và có thể cần DN.
2. **Chỉnh sửa entry rồi ghi lại**: lấy trạng thái hiện có, thay đổi một vài attribute và gửi các modification thích hợp cho server.

`DirContextOperations` giúp viết code chung cho hai nhu cầu này; `DirContextAdapter` cung cấp implementation để làm việc với DN và thuộc tính trong bộ nhớ, gồm khả năng biểu diễn các thay đổi cần gửi tới LDAP.

## 2. Ba khái niệm tên gần giống nhưng trách nhiệm khác nhau

| Thành phần | Package | Bản chất | Vai trò |
| --- | --- | --- | --- |
| `DirContext` | `javax.naming.directory` | Interface của JNDI | Thao tác với dịch vụ directory thông qua context/provider |
| `DirContextOperations` | `org.springframework.ldap.core` | Interface của Spring LDAP | Đọc/ghi thuộc tính của entry, truy cập DN và thông tin cần cho thao tác update |
| `DirContextAdapter` | `org.springframework.ldap.core` | Class triển khai `DirContextOperations` | Giữ dữ liệu entry trong bộ nhớ, cung cấp getter/setter, hỗ trợ theo dõi modification |
| `ContextMapper<T>` | `org.springframework.ldap.core` | Callback ánh xạ | Chuyển một object context của kết quả search thành kiểu `T` |
| `AttributesMapper<T>` | `org.springframework.ldap.core` | Callback ánh xạ | Chuyển `Attributes` thành kiểu `T` mà không yêu cầu làm việc trực tiếp với context |
| `LdapTemplate` | `org.springframework.ldap.core` | API truy cập LDAP | Search, lookup, bind, modify, rename, unbind và quản lý context |

**Không nên đánh đồng `DirContextAdapter` với một kết nối LDAP đang mở.** Adapter là đối tượng biểu diễn dữ liệu/context của entry ở phía ứng dụng. Nó không tự thực hiện network request khi bạn gọi một setter.

~~~mermaid
flowchart TD
    U["Service nghiệp vụ"]
    T["LdapTemplate"]
    CS["ContextSource"]
    J["JNDI LDAP provider<br/>DirContext"]
    LDAP[("LDAP server")]
    M{"Kết quả được ánh xạ bằng?"}
    AM["AttributesMapper<br/>Attributes → DTO"]
    CM["ContextMapper<br/>DirContextOperations → DTO"]
    A["DirContextAdapter<br/>get/set attributes, DN, modifications"]
    U --> T --> CS --> J --> LDAP
    LDAP --> J --> T --> M
    M --> AM --> U
    M --> CM --> A --> U
~~~

Sơ đồ chỉ mô tả lớp trách nhiệm. Provider và Spring LDAP có thể dùng các class nội bộ, caching hoặc callback khác nhau tùy operation và phiên bản.

## 3. `DirContextOperations` là hợp đồng làm việc với một entry

`DirContextOperations` cung cấp các thao tác thuận tiện với dữ liệu thuộc tính và DN. Nhóm phương thức thường gặp:

| Nhóm | Phương thức tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| DN | `getDn()` | Lấy tên (DN) mà adapter đang biểu diễn trong ngữ cảnh Spring LDAP |
| Đọc giá trị đơn | `getStringAttribute("cn")` | Lấy một giá trị chuỗi |
| Đọc nhiều giá trị | `getStringAttributes("member")` | Lấy các giá trị chuỗi dạng mảng |
| Đọc dữ liệu gốc | `getAttributes()` | Truy cập JNDI `Attributes` của entry |
| Đặt giá trị | `setAttributeValue("cn", value)` | Đặt giá trị attribute |
| Đặt tập giá trị | `setAttributeValues("member", values)` | Đặt tập giá trị mới |
| Thêm một giá trị | `addAttributeValue("member", value)` | Bổ sung giá trị thuộc attribute |
| Xóa một giá trị | `removeAttributeValue("member", value)` | Loại một giá trị khỏi attribute |
| Theo dõi cập nhật | `getModificationItems()` | Trả các `ModificationItem` cho các thay đổi được ghi nhận |

Không phải mọi attribute đều là chuỗi hoặc có một giá trị. `jpegPhoto` có thể là dữ liệu nhị phân; `member` của một nhóm có thể gồm nhiều DN. Đối tượng `DirContextOperations` giúp truy cập dữ liệu, nhưng **schema LDAP vẫn quyết định** syntax, objectClass và số lượng giá trị được phép.

### 3.1. Interface không định nghĩa một mô hình entity nghiệp vụ

Một entry LDAP có:

~~~text
cn = Nguyen Lan
uid = lan
mail = lan@example.org
~~~

không có nghĩa Java tự biết phải tạo `EmployeeView` hay `EmployeeEntity`. `DirContextOperations` vẫn là **một lớp truy cập dữ liệu entry**, không phải DTO đã được định kiểu theo nghiệp vụ.

Bạn quyết định mapping thành DTO qua `ContextMapper`:

~~~java
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;

ContextMapper<EmployeeView> mapper = context -> {
    DirContextOperations entry = (DirContextOperations) context;
    return new EmployeeView(
        entry.getDn().toString(),
        entry.getStringAttribute("uid"),
        entry.getStringAttribute("cn"),
        entry.getStringAttribute("mail")
    );
};
~~~

Ví dụ này giả định `EmployeeView` đã được khai báo như mục 1. Giá trị trả về từ `getDn()` cần được hiểu đúng theo base DN của Spring LDAP, sẽ giải thích ở phần sau.

### 3.2. `DirContextOperations` không thay thế LDAP bind authentication

Đọc được `uid` hoặc `cn` nghĩa là một entry có thể được truy vấn. Điều đó không chứng minh người dùng biết mật khẩu hoặc có quyền vào ứng dụng.

Khi cần xác thực, dùng LDAP bind qua cơ chế xác thực phù hợp (thường là Spring Security LDAP). Với phân quyền, ánh xạ group/authority và kiểm tra chính sách ứng dụng. Không tự gán quyền dựa trên việc một `DirContextAdapter` chứa thuộc tính tên nhóm.

## 4. `DirContextAdapter` là triển khai tiện dụng

`DirContextAdapter` là implementation thường gặp của `DirContextOperations`. Nó có thể được sử dụng theo hai luồng khác nhau:

1. **Đọc entry hiện có:** Spring LDAP tạo hoặc cung cấp adapter khi `lookupContext(...)` hoặc `ContextMapper` chạy.
2. **Tạo entry mới:** ứng dụng khởi tạo `new DirContextAdapter(dn)`, gán các thuộc tính cần thiết rồi yêu cầu `LdapTemplate.bind(...)`.

Trong cả hai trường hợp, một lời gọi `setAttributeValue(...)` **không tự gửi LDAP ModifyRequest**. Bạn phải gọi operation tương ứng trên `LdapTemplate` để thực sự ghi dữ liệu.

~~~mermaid
flowchart TD
    S{"Nhu cầu?"}
    New["Tạo entry mới"]
    Existing["Sửa entry hiện có"]
    N["new DirContextAdapter(dn)"]
    L["ldapTemplate.lookupContext(dn)"]
    Set["Đặt thuộc tính trên adapter"]
    Update["Thay đổi các thuộc tính cần sửa"]
    Bind["ldapTemplate.bind(adapter)"]
    Modify["ldapTemplate.modifyAttributes(adapter)"]
    Server[("LDAP server<br/>schema + ACL")]
    S --> New --> N --> Set --> Bind --> Server
    S --> Existing --> L --> Update --> Modify --> Server
~~~

Phải phân biệt hai trạng thái này: **bind** tạo entry mới; **modify** cập nhật entry có sẵn. Dùng sai operation có thể gây lỗi entry tồn tại/không tồn tại hoặc vi phạm schema.

### 4.1. Trạng thái trong bộ nhớ không phải trạng thái trên server

Giả sử bạn đã có:

~~~java
DirContextOperations entry = ldapTemplate.lookupContext(dn);
entry.setAttributeValue("telephoneNumber", "+84 28 5555 0101");
~~~

Ngay sau dòng setter, giá trị trong adapter đã đổi; **LDAP server chưa nhất thiết được cập nhật**. Phải gọi:

~~~java
ldapTemplate.modifyAttributes(entry);
~~~

Nếu bind/modify thất bại vì thiếu quyền, sai schema hoặc mất kết nối, không nên cho rằng dữ liệu trên server đã được lưu. Đối với quy trình quan trọng, có thể đọc lại entry sau thao tác để xác minh kết quả và xử lý concurrency.

## 5. Ánh xạ kết quả tìm kiếm bằng `ContextMapper`

Xét nhu cầu tìm nhân viên theo `uid`. Chúng ta muốn lấy `uid`, `cn`, `mail` và DN của entry để phục vụ thao tác cập nhật sau này.

### 5.1. Cấu hình kết nối minh họa

Một ứng dụng Spring Boot sử dụng Spring LDAP có thể cấu hình:

~~~yaml
spring:
  ldap:
    urls:
      - ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    # Lấy spring.ldap.password từ secret manager hoặc environment.
~~~

Giả định `ContextSource.base` là `dc=example,dc=org`. Search base `ou=people` dưới đây là tên **tương đối** với base đó.

Tài khoản reader cần quyền search và quyền đọc các attribute được yêu cầu. LDAPS/StartTLS phải xác minh certificate và hostname; không vô hiệu hóa kiểm tra TLS chỉ để ví dụ chạy được.

### 5.2. Service tìm nhân viên với ContextMapper

~~~java
import java.util.List;
import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.stereotype.Service;

@Service
public class EmployeeResultService {

    public record EmployeeView(
        String dn,
        String uid,
        String fullName,
        String email
    ) {}

    private final LdapTemplate ldapTemplate;

    public EmployeeResultService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<EmployeeView> findByUid(String uid) {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
        controls.setReturningAttributes(
            new String[] {"uid", "cn", "mail"}
        );
        controls.setCountLimit(50);
        controls.setTimeLimit(2_000);

        String filter = new EqualsFilter("uid", uid).encode();

        return ldapTemplate.search(
            "ou=people",
            filter,
            controls,
            (ContextMapper<EmployeeView>) context -> {
                DirContextOperations entry =
                    (DirContextOperations) context;

                return new EmployeeView(
                    entry.getDn().toString(),
                    entry.getStringAttribute("uid"),
                    entry.getStringAttribute("cn"),
                    entry.getStringAttribute("mail")
                );
            }
        );
    }
}
~~~

Trong ví dụ:

- `EqualsFilter` encode username là **giá trị literal** của LDAP filter; ký tự `*` trong `uid` không tự biến thành wildcard.
- `SUBTREE_SCOPE` bao phủ những người dùng nằm trong OU lồng nhau dưới `ou=people`.
- `setReturningAttributes(...)` yêu cầu đúng các trường được mapper sử dụng.
- `DirContextOperations` cung cấp cả DN lẫn getter thuận tiện cho các attribute.
- Kiểu trả là `List`, vì việc thuộc tính được gọi tên `uid` không tự bảo đảm uniqueness toàn directory.

Nếu nghiệp vụ cần đúng một user, cần kiểm tra kết quả duy nhất và chính sách uniqueness; không tự lấy entry đầu tiên trong danh sách.

### 5.3. `getDn()` là DN nào?

Đây là chi tiết rất quan trọng khi làm việc với Spring LDAP.

Giả sử entry đầy đủ là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Và `ContextSource` dùng base:

~~~text
dc=example,dc=org
~~~

Trong các thao tác Spring LDAP hoạt động với DN tương đối, `entry.getDn()` thường biểu diễn DN tương đối với base/ngữ cảnh mà Spring LDAP đang sử dụng, ví dụ:

~~~text
uid=lan,ou=people
~~~

**Không mặc định `getDn().toString()` là full DN từ root LDAP server** trong mọi API và mọi cấu hình. Nếu cần xuất DN làm external identifier, hãy:

1. Xác định base DN của `ContextSource` hoặc tên đầy đủ mà API cung cấp.
2. Làm rõ trong DTO trường `dn` là relative DN hay absolute/full DN.
3. Dùng các API thao tác `Name`/`LdapName` phù hợp để giữ cấu trúc và escape DN.
4. Kiểm thử với OU lồng nhau, nhiều base và các ký tự đặc biệt trong RDN.

DN có thể thay đổi khi entry được rename/move. Không coi DN là khóa bất biến nếu nghiệp vụ cho phép đổi RDN hoặc di chuyển OU.

## 6. `AttributesMapper` và `ContextMapper` khác nhau thế nào?

Spring LDAP cung cấp hai mapper phổ biến khi tìm kiếm:

| Tiêu chí | `AttributesMapper<T>` | `ContextMapper<T>` |
| --- | --- | --- |
| Đầu vào callback | `javax.naming.directory.Attributes` | Một object context, thường ép thành `DirContextOperations` |
| Đọc giá trị thông thường | `attrs.get("cn").get()` | `entry.getStringAttribute("cn")` |
| Đọc nhiều giá trị | `Attribute.getAll()` hoặc xử lý `Attribute` | `getStringAttributes("member")` và API tiện ích |
| Lấy DN trong callback | Không có DN trực tiếp trong `Attributes` | Có thể dùng `getDn()` |
| Phù hợp với | DTO nhỏ, chỉ cần thuộc tính | Mapping cần DN/context hoặc muốn dùng getter của adapter |
| Ghi dữ liệu | Chỉ mapping, không tự lưu | Có thể biểu diễn thay đổi qua adapter; vẫn phải gọi operation ghi |

### 6.1. Nếu chỉ cần các attribute, đừng làm phức tạp hóa

Ví dụ đọc tên:

~~~java
List<String> names = ldapTemplate.search(
    "ou=people",
    "(objectClass=inetOrgPerson)",
    (AttributesMapper<String>) attrs -> {
        var cn = attrs.get("cn");
        return cn == null ? null : (String) cn.get();
    }
);
~~~

Ở đây `AttributesMapper` đơn giản và đủ dùng. Dùng `ContextMapper` **không mặc định nhanh hơn** hoặc an toàn hơn; nó hữu ích khi bạn cần thêm khả năng thao tác với DN/context.

Nếu một mapper có thể trả `null`, lớp gọi phải có chính sách xử lý: bỏ qua, thể hiện field vắng mặt hay báo lỗi. Không giả định mọi entry luôn có mọi attribute tùy chọn.

### 6.2. Nếu cần DN, ContextMapper rõ ràng hơn

~~~java
(ContextMapper<String>) ctx -> {
    DirContextOperations entry = (DirContextOperations) ctx;
    return entry.getDn().toString();
}
~~~

Đừng cố lấy DN bằng cách tìm `"dn"` trong `Attributes` rồi ép thành chuỗi nếu server không cung cấp attribute đó. **DN là tên của entry**, không phải một user attribute phổ quát tên `dn`.

## 7. Đọc thuộc tính an toàn: thiếu, đơn giá trị và đa giá trị

LDAP schema phân biệt **attribute type**, syntax, single-valued/multi-valued, operational attributes và các matching rule. Adapter cung cấp các API dễ gọi nhưng không tự loại bỏ những quy tắc này.

### 7.1. Đọc thuộc tính có thể vắng mặt

~~~java
String email = entry.getStringAttribute("mail");
~~~

`mail` có thể vắng mặt, không được đọc do ACL hoặc không nằm trong tập returning attributes. Vì thế cần xác định dữ liệu này là **bắt buộc hay tùy chọn** đối với DTO.

Ví dụ:

~~~java
String uid = entry.getStringAttribute("uid");
if (uid == null || uid.isBlank()) {
    throw new IllegalStateException(
        "LDAP entry không có uid theo hợp đồng của ứng dụng"
    );
}

String mail = entry.getStringAttribute("mail"); // Có thể null.
~~~

Không “bịa” email hoặc UID từ DN nếu nghiệp vụ không định nghĩa quy tắc chuyển đổi đó.

### 7.2. Đọc thuộc tính nhiều giá trị

Entry nhóm có thể chứa:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=engineering,ou=people,dc=example,dc=org
~~~

Để đọc các giá trị:

~~~java
import java.util.Arrays;
import java.util.List;

String[] members = entry.getStringAttributes("member");

List<String> memberDns = members == null
    ? List.of()
    : Arrays.asList(members);
~~~

Lấy một giá trị bằng `getStringAttribute("member")` có thể bỏ sót các thành viên khác. Thứ tự của một attribute nhiều giá trị **không mặc nhiên mang ý nghĩa nghiệp vụ**; không dựa vào phần tử đầu là “quản trị viên” hay “chủ nhóm” nếu schema không bảo đảm.

Ngoài ra, membership theo DN cần được so sánh bằng ngữ nghĩa DN/matching rule phù hợp, không đơn thuần `String.equalsIgnoreCase(...)`.

### 7.3. Không ép mọi attribute thành String

Một số attribute có thể chứa `byte[]`, ví dụ ảnh hoặc dữ liệu chứng chỉ. `getStringAttribute(...)` phù hợp khi schema và provider trả giá trị chuỗi. Nếu cần binary, hãy đọc từ `Attributes`/`Attribute` theo kiểu phù hợp và kiểm tra kiểu trước khi ép.

~~~java
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

Attributes attrs = entry.getAttributes();
Attribute jpeg = attrs.get("jpegPhoto");

if (jpeg != null && jpeg.size() > 0) {
    Object raw = jpeg.get();
    if (raw instanceof byte[] bytes) {
        // Dùng bytes theo hợp đồng nghiệp vụ.
    } else {
        throw new IllegalStateException(
            "Giá trị jpegPhoto không đúng kiểu mong đợi"
        );
    }
}
~~~

Trong production, hạn chế kích thước ảnh/binary và tránh kéo dữ liệu lớn trong một query danh sách thông thường. Code trên minh họa việc kiểm tra kiểu giá trị, không xử lý ảnh hoàn chỉnh.

### 7.4. Attribute có option và operational attribute

Trong LDAP, tên attribute có thể có option, ví dụ `cn;lang-vi` và `cn;lang-en`. Không tự bỏ phần option rồi coi chúng hoàn toàn tương đương.

Các operational attributes như `entryUUID` hoặc timestamp do server quản lý có thể **không nằm trong tập thuộc tính trả về mặc định**. Nếu cần chúng, phải yêu cầu đúng attribute, kiểm tra quyền và khả năng hỗ trợ của server. Không sửa operational attribute do server quản lý như thể là trường DTO tùy ý.

## 8. Tạo một entry mới với DirContextAdapter

Khi muốn **tạo** entry, bạn có thể tạo adapter rỗng gắn với DN mới, sau đó đặt attributes cần thiết.

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void createPerson(
        LdapTemplate ldapTemplate,
        String uid,
        String fullName,
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
    entry.setAttributeValue("cn", fullName);
    entry.setAttributeValue("sn", surname);

    ldapTemplate.bind(entry);
}
~~~

Đoạn code làm các việc:

1. Dùng `LdapNameBuilder` tạo DN có cấu trúc, tránh ghép `"uid=" + uid + ",ou=people"`.
2. Tạo `DirContextAdapter` đại diện entry **chưa tồn tại**.
3. Đặt `objectClass` và các attribute hợp lệ theo schema minh họa.
4. Gọi `ldapTemplate.bind(entry)` để gửi thao tác tạo entry tới LDAP server.

Không gọi `ldapTemplate.modifyAttributes(entry)` nếu entry chưa tồn tại, và không gọi `bind(...)` với DN đã tồn tại rồi kỳ vọng nó trở thành phép cập nhật.

**Schema vẫn là bắt buộc:** với `inetOrgPerson` thông dụng, `cn` và `sn` là các trường quan trọng trong chuỗi objectClass liên quan. Directory cụ thể có thể yêu cầu thêm thuộc tính, giới hạn nơi được phép tạo entry hoặc sử dụng quy tắc naming khác.

### 8.1. Adapter không phải một transaction

Giả sử sau khi tạo nhân viên, ứng dụng tiếp tục thêm DN của họ vào group. Đây là hai thao tác LDAP có thể thất bại riêng. `DirContextAdapter` không tạo giao dịch ACID nhiều entry. Cần thiết kế kiểm tra trước, xử lý lỗi một phần và hành động bù trừ/idempotent phù hợp với nghiệp vụ.

## 9. Cập nhật entry hiện có bằng lookupContext và modifyAttributes

Đây là tình huống thể hiện rõ lợi ích của `DirContextOperations`/`DirContextAdapter`: lấy entry hiện tại, sửa vài attribute rồi yêu cầu template gửi những thay đổi.

### 9.1. Ví dụ sửa số điện thoại

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void updatePhone(
        LdapTemplate ldapTemplate,
        String uid,
        String newPhone) {

    Name dn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", uid)
        .build();

    DirContextOperations entry = ldapTemplate.lookupContext(dn);

    entry.setAttributeValue("telephoneNumber", newPhone);

    ldapTemplate.modifyAttributes(entry);
}
~~~

Các bước diễn ra:

- `lookupContext(dn)` đọc entry và nhận `DirContextOperations` để thao tác.
- Setter thay đổi **dữ liệu trong adapter**.
- `modifyAttributes(entry)` thực hiện cập nhật qua LDAP, dựa trên những modification đã được adapter theo dõi.
- Server xác nhận hoặc từ chối thao tác theo schema, ACL, trạng thái kết nối và chính sách của nó.

Nếu `uid` không thực sự nằm trực tiếp dưới `ou=people`, DN do code xây sẽ sai. Khi nhân viên được phân theo OU, hãy **search ra DN thực** trước, rồi dùng DN đó cho update; đừng suy vị trí entry từ một username tùy ý.

### 9.2. Đọc trước, thay đổi sau: tránh ghi đè cả entry

Không nên đọc một DTO chỉ có `cn` và `mail` rồi tạo lại một adapter với **chỉ hai thuộc tính đó**, sau đó kỳ vọng nó sẽ thay đổi đúng hai trường trên một entry hiện có. Dữ liệu khác (như `member` hoặc attributes do server quản lý) cần được giữ nguyên.

Luồng `lookupContext → setAttributeValue → modifyAttributes` hỗ trợ biểu đạt cập nhật có chọn lọc. Tuy nhiên đây **không phải** một cơ chế quản lý phiên bản/concurrency tự động; nếu hai request đồng thời đọc cùng entry và sửa cùng field, thao tác đến sau có thể ghi đè giá trị được ghi trước.

### 9.3. Trường hợp giá trị chưa thay đổi

Adapter có cơ chế theo dõi sự khác biệt giữa trạng thái ban đầu và trạng thái mong muốn trong luồng update. Nếu bạn đặt lại đúng giá trị đã có, có thể không cần gửi một modification mới, tùy kiểu giá trị và cách adapter xác định thay đổi.

Không dùng `String.equals(...)` hoặc so sánh byte tùy ý làm chuẩn chung để quyết định hai giá trị LDAP có tương đương hay không. Equality matching rule của server phụ thuộc schema; đặc biệt với DN và chuỗi Unicode, phép so phía Java và so phía server có thể không tương đương.

## 10. Theo dõi thay đổi và `getModificationItems()`

JNDI biểu diễn sửa thuộc tính bằng `javax.naming.directory.ModificationItem` với các thao tác như:

- `DirContext.ADD_ATTRIBUTE`
- `DirContext.REPLACE_ATTRIBUTE`
- `DirContext.REMOVE_ATTRIBUTE`

`DirContextAdapter` có thể gom các thay đổi được thực hiện qua API getter/setter vào các `ModificationItem` mà `LdapTemplate` sử dụng khi modify.

### 10.1. Ví dụ xem ý nghĩa của modification

~~~java
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

DirContextOperations entry = ldapTemplate.lookupContext(dn);

entry.setAttributeValue(
    "telephoneNumber", "+84 28 5555 0101"
);

ModificationItem[] changes = entry.getModificationItems();

for (ModificationItem change : changes) {
    int operation = change.getModificationOp();

    if (operation == DirContext.REPLACE_ATTRIBUTE) {
        // Thay giá trị attribute.
    } else if (operation == DirContext.ADD_ATTRIBUTE) {
        // Thêm giá trị/attribute.
    } else if (operation == DirContext.REMOVE_ATTRIBUTE) {
        // Xóa giá trị/attribute.
    }
}
~~~

Mã trên chỉ minh họa **inspection** ở phía Java. Trong production không nên log nguyên toàn bộ `ModificationItem` nếu nó chứa thông tin nhạy cảm. Và cần hiểu rằng kết quả phụ thuộc state/update mode của adapter, các thay đổi đã làm và quy tắc nội bộ của thư viện.

### 10.2. Không tự đồng bộ bộ nhớ với server bằng cách suy đoán

Nếu gọi `setAttributeValue(...)` rồi chỉ xem `getModificationItems()`, đó vẫn là thao tác trên object trong bộ nhớ. Phải gọi `ldapTemplate.modifyAttributes(entry)` để ghi.

Nếu thao tác ghi thất bại, **không** được khẳng định entry trên server đã đổi. Nếu cần kết luận chắc chắn, hãy xử lý exception rồi đọc lại theo yêu cầu nghiệp vụ, chú ý khả năng replication delay và đọc từ server khác.

### 10.3. Tránh nhầm update mode và new-entry mode

Một adapter mới tạo để bind và một adapter vừa đọc từ LDAP để cập nhật có **ngữ cảnh khác nhau**. Đối với cập nhật, ưu tiên lấy từ `lookupContext(...)` để adapter có trạng thái hiện tại cần thiết cho diff tracking.

Không lấy code tạo entry mới rồi đưa thẳng vào `modifyAttributes(...)` mà không hiểu các modification sẽ được tạo ra thế nào. Các cơ chế theo dõi thay đổi và mode nội bộ có thể ảnh hưởng kết quả.

## 11. Thay đổi thuộc tính đa giá trị mà không xóa nhầm thành viên

Entry nhóm có thể chứa:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Nếu bạn chỉ muốn thêm một thành viên `uid=hoa,...`, không nên thay toàn bộ `member` bằng mảng chỉ có một phần tử mới:

~~~java
// Không dùng nếu chỉ muốn bổ sung một thành viên:
entry.setAttributeValues(
    "member",
    new String[] {newMemberDn}
);
~~~

Cách này mô tả một **tập giá trị mới**, có thể khiến các giá trị cũ bị loại bỏ sau khi ghi.

Hãy dùng phương thức tương ứng với ý nghĩa thay đổi:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public void addDirectMember(
        LdapTemplate ldapTemplate,
        String memberFullDn) {

    Name groupDn = LdapNameBuilder
        .newInstance("ou=groups")
        .add("cn", "developers")
        .build();

    DirContextOperations group =
        ldapTemplate.lookupContext(groupDn);

    group.addAttributeValue("member", memberFullDn);

    ldapTemplate.modifyAttributes(group);
}
~~~

Điểm cần chú ý:

- `memberFullDn` ở đây là **DN đầy đủ** theo schema DN-valued attribute của group, không phải tên hiển thị của nhân viên.
- `groupDn` là DN của group **tương đối với base cấu hình** trong ví dụ.
- `addAttributeValue(...)` biểu thị ý định thêm giá trị; server vẫn có thể từ chối vì ACL, không hỗ trợ attribute, duplicate theo matching rule hoặc ràng buộc khác.
- Đây là **membership trực tiếp** của một group. Nested groups, dynamic groups và authorization policy không tự được giải quyết.
- Nếu cần loại bỏ một member, dùng `removeAttributeValue("member", memberFullDn)` rồi `modifyAttributes(...)` theo chính sách nghiệp vụ.

### 11.1. Số lượng giá trị và objectClass

Một số group schema như `groupOfNames` có những ràng buộc riêng, chẳng hạn yêu cầu ít nhất một giá trị `member` theo schema thường dùng. Vì vậy thao tác xóa thành viên cuối có thể bị server từ chối. Không tạo “nhóm rỗng” hoặc xóa toàn bộ attribute mà không xem schema của directory đích.

### 11.2. Thứ tự và phép so DN

LDAP multi-valued attributes thông thường không phải danh sách có thứ tự nghiệp vụ. Nếu bạn nhận được hai DN khác biểu diễn về chữ hoa, escape hoặc thứ tự attribute trong multi-valued RDN, đừng tự dùng `String.equalsIgnoreCase` để quyết định chúng là cùng một entry. Sự tương đương của DN cần theo ngữ nghĩa DN và matching rule của server.

## 12. Thay đổi DN khác thay đổi attribute

Entry được xác định bởi DN:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Nếu ứng dụng đổi `uid` hoặc chuyển entry sang `ou=engineering`, đó có thể là **thay đổi RDN/DN**, không chỉ là thay giá trị một attribute.

- `setAttributeValue("cn", "...")` thay đổi giá trị `cn` (nếu được phép), không tự rename entry.
- `setAttributeValue("uid", "...")` không tự động đổi RDN đang dùng để đặt tên entry.
- `ldapTemplate.rename(oldDn, newDn)` mô tả thao tác rename/move trong phạm vi server và API hỗ trợ.
- Việc đổi DN có thể ảnh hưởng tham chiếu `member`, liên kết nghiệp vụ hoặc cache của ứng dụng.

Khi dùng `DirContextAdapter`, luôn phân biệt **DN của object** với **các thuộc tính bên trong object**. Không coi việc sửa field `uid` trong Java như việc thay toàn bộ đường dẫn LDAP.

## 13. Những ràng buộc của schema, ACL và matching rule

Adapter có thể cho phép bạn gọi một setter về mặt Java, nhưng **server** mới quyết định modification có hợp lệ không.

| Tình huống | Vì sao server có thể từ chối? |
| --- | --- |
| Đặt `objectClass` hoặc loại attribute không được schema cho phép | Vi phạm schema hoặc quy tắc objectClass |
| Xóa `sn` bắt buộc của `person` | Vi phạm thuộc tính bắt buộc |
| Thêm giá trị thứ hai vào attribute `SINGLE-VALUE` | Vi phạm ràng buộc số lượng giá trị |
| Thay `entryUUID` hoặc timestamp do server quản lý | Operational attribute có chính sách riêng |
| Sửa entry bằng service account chỉ được đọc | ACL không cho modify |
| Thêm giá trị `member` không hợp lệ | DN syntax hoặc membership schema không phù hợp |
| Tạo entry trùng DN | Entry đã tồn tại |
| Thay DN khi server không cho phép move/rename | Vi phạm policy hoặc capability của server |

### 13.1. Tên thuộc tính và giá trị có cách so khác nhau

Tên attribute type như `cn` và `CN` được nhận diện không phân biệt hoa/thường. Nhưng giá trị của một attribute có so khớp case-sensitive hay không phụ thuộc `EQUALITY`/`SUBSTR` matching rules.

Đối với `member` có syntax DN, so sánh giá trị khác so một chuỗi bình thường. Tránh logic ép lower-case/trim tất cả dữ liệu trước khi ghi hoặc xác định thay đổi; điều đó có thể làm mất thông tin hợp lệ.

### 13.2. ACL không phải validation ở phía client

Một DTO có annotation validation trong Java không thay thế LDAP schema và quyền server. Dù code mapper/setter chấp nhận `telephoneNumber` mới, LDAP server có thể từ chối sửa do ACL. Ứng dụng phải hiển thị lỗi phù hợp, không tự coi thao tác đã thành công vì object trong memory đã đổi.

## 14. Tính nhất quán và concurrent updates

`DirContextAdapter` lưu trạng thái cần để mô tả các thay đổi ở phía client, nhưng **không tự cung cấp optimistic locking, transaction nhiều entry hoặc cơ chế giải quyết mọi race condition**.

Xét hai request:

~~~text
T0: Request A lookup entry, telephoneNumber = 100
T1: Request B lookup cùng entry, telephoneNumber = 100
T2: Request A set telephoneNumber = 200; modify thành công
T3: Request B set telephoneNumber = 300; modify thành công
Kết quả cuối: 300 (theo thứ tự thực thi minh họa)
~~~

Việc các adapter ban đầu có trạng thái giống nhau **không** khiến LDAP tự phát hiện “A đã thay đổi trước B”. Với cùng attribute, ghi sau có thể ghi đè giá trị trước.

Nếu yêu cầu nghiệp vụ cần tránh lost update, cân nhắc:

- Thiết kế update theo **mức attribute/value** thay vì luôn replace toàn bộ entry.
- Đọc lại sau khi cập nhật, với nhận thức rằng readback không loại bỏ được mọi race.
- Tìm hiểu LDAP assertion control, pre-read/post-read controls hoặc cơ chế concurrency được **server và client hỗ trợ**.
- Nếu dùng `modifyTimestamp`/`entryUUID`, cần hiểu chúng là operational attributes; không giả định mọi server có cùng behavior hoặc đây là version number có thể dùng trực tiếp.
- Thiết kế idempotency và xử lý conflict ở tầng nghiệp vụ.

Trong các hệ thống nhiều server/replication, đọc ngay sau ghi còn có thể chịu replication delay nếu request đi qua một replica khác.

## 15. Kết hợp với LdapTemplate, LdapClient, ODM và Spring Security

| Công cụ | Vai trò | Khi nào nên dùng |
| --- | --- | --- |
| `LdapTemplate` | Thực thi search, lookupContext, bind, modify, rename, unbind | Cần thao tác directory trực tiếp với callback và adapter |
| `DirContextOperations` | Giao diện đọc/sửa dữ liệu entry ở phía Java | Cần getter/setter, DN và modification state |
| `DirContextAdapter` | Triển khai `DirContextOperations` | Muốn tự dựng entry mới hoặc làm việc với adapter được template tạo |
| `AttributesMapper` | Ánh xạ `Attributes` thành DTO | Chỉ cần dữ liệu thuộc tính, không cần DN |
| `ContextMapper` | Ánh xạ context thành DTO | Cần DN hoặc tiện ích `DirContextOperations` |
| `LdapClient` | API fluent cho một số thao tác LDAP | Muốn cú pháp truy vấn/thao tác khác; vẫn phải hiểu mapping/LDAP |
| Spring LDAP ODM | Ánh xạ entity qua `@Entry`, `@Attribute`, `@Id` | Mô hình entry ổn định, dùng đi dùng lại |
| Spring Data LDAP | Repository dựa trên ODM | Truy cập entry theo mô hình repository |
| Spring Security LDAP | Bind authentication, tìm groups/authorities | Xác thực và phân quyền ứng dụng |

Đừng tự triển khai authentication chỉ bằng cách đọc `userPassword` qua `getStringAttribute("userPassword")` rồi so mật khẩu. Dùng LDAP bind hoặc Spring Security LDAP phù hợp; kết quả mapping entry không chứng minh danh tính.

### 15.1. Tại sao cần cả Adapter nếu đã có ODM?

ODM phù hợp khi một objectClass tương ứng một entity Java ổn định. `DirContextAdapter`/`DirContextOperations` phù hợp khi:

- Cần làm việc với các attribute không đồng nhất giữa nhiều objectClass.
- Cần kiểm soát DN/context hoặc update một subset các attributes.
- Cần xử lý multi-valued attribute và sửa trực tiếp bằng thao tác LDAP.
- Cần mapper tùy biến cho DTO phục vụ một API cụ thể.

Hai lựa chọn không loại trừ nhau; nhưng không nên ánh xạ quá nhiều tầng nếu chỉ đọc một vài thuộc tính.

## 16. Hiệu năng: mapper không sửa được truy vấn quá rộng

Việc dùng `ContextMapper` hoặc `DirContextAdapter` không bảo đảm search nhanh. Chi phí thường phụ thuộc:

1. **Search base và scope:** tìm dưới `ou=people` thay vì toàn directory nếu chỉ cần nhân viên.
2. **Filter và index:** equality trên `uid` thường khác substring `(cn=*an*)`; chỉ mục là trách nhiệm server.
3. **Attributes trả về:** không tải ảnh hoặc certificate nếu UI chỉ cần `cn`/`mail`.
4. **Số entry:** hàng nghìn adapter/DTO chiếm bộ nhớ và CPU mapping.
5. **Kết nối:** TLS, mạng, pooling và concurrent requests ảnh hưởng độ trễ.
6. **Cập nhật:** read-modify-write tạo thêm network round trips, cần thiết kế theo tần suất ghi.

Dùng `SearchControls` để kiểm soát scope, returning attributes, count limit và time limit. Nhưng giới hạn số kết quả trả về **không** bảo đảm server chỉ phải kiểm tra bằng ấy entry.

Đối với danh sách lớn, cân nhắc paging nếu server/client hỗ trợ. Paging không thay thế filter chọn lọc và index phù hợp.

## 17. Bảo mật khi đọc/sửa bằng adapter

### 17.1. Nguyên tắc tối thiểu quyền

Một service chỉ hiển thị hồ sơ nên dùng tài khoản bind chỉ đọc. Service thay đổi điện thoại/nhóm cần quyền ghi cho **đúng những attribute và OU cần thiết**.

Không cho client HTTP gửi trực tiếp tên attribute bất kỳ rồi gọi `setAttributeValue(inputName, inputValue)`: điều đó có thể trở thành cơ chế sửa các trường không được phép, kể cả khi server ACL còn một số lỗ hổng cấu hình.

**Whitelist** những field nghiệp vụ được phép sửa, validation giá trị, authorization của người gọi API, rồi mới gọi template. LDAP ACL là một lớp bảo vệ khác, không thay thế authorization ứng dụng.

### 17.2. DN và filter phải được xây đúng cách

- Dùng `LdapNameBuilder` khi tạo DN/RDN từ giá trị đầu vào.
- Dùng `EqualsFilter` hoặc `LdapQueryBuilder` để encode các giá trị trong filter.
- Không ghép raw username thành `"(uid=" + username + ")"`.
- Không coi escape DN tương đương escape LDAP filter.
- Không tin một DN bất kỳ trong request nếu nghiệp vụ chưa xác minh người gọi được sửa entry đó.

### 17.3. TLS, secrets và pooling

Dùng LDAPS hoặc StartTLS với certificate chain và hostname được xác minh. Bảo vệ service bind password trong secret manager hoặc external configuration, không đưa vào Git/log.

Nếu có connection pooling, cần bảo đảm không tái sử dụng context sai danh tính giữa các request; đặc biệt cẩn trọng khi cùng ứng dụng vừa search bằng service account vừa bind để xác thực người dùng.

### 17.4. Không log toàn bộ adapter

`DirContextOperations` có thể chứa rất nhiều attributes, kể cả dữ liệu cá nhân, membership hoặc thông tin không nên đưa vào log. Khi quan sát sự cố, ưu tiên log tên operation, thời gian, trạng thái và mã lỗi, giảm thiểu DN/email và tuyệt đối không ghi password hoặc thông tin xác thực.

## 18. Xử lý lỗi và kiểm tra trạng thái thực

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Lookup DN không tồn tại | Không có entry để map/sửa | Báo “not found” theo chính sách |
| Search trả nhiều entry khi kỳ vọng một | Không xác định đúng object | Kiểm tra uniqueness/base/filter |
| Thiếu thuộc tính do ACL | Getter trả null/không đủ dữ liệu | Không suy rằng entry không tồn tại |
| Thêm entry trùng DN | Bind bị từ chối | Phân loại lỗi trùng, không tự overwrite |
| Sửa thuộc tính schema cấm | Modify thất bại | Kiểm tra objectClass/syntax/single-value |
| Tài khoản không có quyền write | Modify bị từ chối | Kiểm tra ACL và danh tính bind |
| DN bị đổi sau lookup | Update nhắm vào tên cũ | Xử lý rename/concurrency |
| TLS/connection timeout | Operation lỗi giữa chừng | Không giả định ghi thành công; xác minh nếu cần |
| Attribute kiểu binary nhưng ép String | Lỗi kiểu/giải mã | Map đúng theo schema |
| Multi-valued set bị thay toàn bộ | Mất các giá trị trước đó | Dùng add/remove đúng ý định |

Spring LDAP chuyển đổi nhiều `NamingException` của JNDI sang các exception tương ứng để code service dễ xử lý. Tuy vậy, không nên nuốt mọi exception rồi trả “không có user” hoặc “đã lưu thành công”. Trường hợp lỗi kết nối lúc modify đặc biệt cần được xử lý thận trọng: có thể chưa biết server đã áp dụng modification hay chưa.

### 18.1. Đừng giả định readback ngay lập tức là mọi replica đã cập nhật

Khi có nhiều LDAP server hoặc replication, một lần đọc từ replica khác có thể chưa thấy thay đổi. Nếu nghiệp vụ cần nhất quán mạnh, cần hiểu kiến trúc directory và chính sách đọc/ghi; adapter không quyết định được điều đó.

## 19. Kiểm thử: từ adapter thuần đến LDAP server

### 19.1. Unit test cho việc dựng entry mới

Không cần server để kiểm tra rằng Java code đã đặt thuộc tính vào adapter:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

Name dn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", "lan")
    .build();

DirContextAdapter adapter = new DirContextAdapter(dn);
adapter.setAttributeValues(
    "objectClass",
    new String[] {"top", "person", "inetOrgPerson"}
);
adapter.setAttributeValue("cn", "Nguyen Lan");
adapter.setAttributeValue("sn", "Nguyen");

String name = adapter.getStringAttribute("cn");
if (!"Nguyen Lan".equals(name)) {
    throw new AssertionError("Mapping sai cn");
}
~~~

Đây chỉ là **unit test hành vi của adapter**. Nó không chứng minh LDAP server cho phép bind entry, objectClass hợp lệ trong mọi triển khai hoặc ACL đã đúng.

Nếu test cần phản ánh hierarchy của `inetOrgPerson`, hãy bổ sung đầy đủ chuỗi objectClass mà schema test server yêu cầu, ví dụ `organizationalPerson`.

### 19.2. Unit test mapper với dữ liệu giả

Với `AttributesMapper`, `BasicAttributes` của JNDI có thể hỗ trợ tạo dữ liệu test:

~~~java
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttributes;

Attributes attrs = new BasicAttributes(true);
attrs.put("uid", "lan");
attrs.put("cn", "Nguyen Lan");

String uid = (String) attrs.get("UID").get();
System.out.println(uid); // lan
~~~

`BasicAttributes(true)` chỉ điều khiển cách collection Java tra tên attribute ID không phân biệt case. Nó không thay đổi LDAP equality matching rule trên server.

### 19.3. Integration test bắt buộc cho luồng ghi

Dùng LDAP test server (embedded hoặc staging cô lập) có schema/ACL phù hợp. Một bộ test đáng có:

| Ca kiểm thử | Mục tiêu |
| --- | --- |
| Tạo entry với `DirContextAdapter` + `bind` | Server lưu đúng DN/objectClass/attributes |
| `lookupContext` + `setAttributeValue` + `modifyAttributes` | Ghi đúng trường được sửa, không ghi nhầm trường khác |
| Chỉ gọi setter, không gọi modify | Xác nhận dữ liệu **chưa được lưu** |
| `addAttributeValue("member", ...)` | Thêm member không xóa member cũ |
| `removeAttributeValue("member", ...)` | Xóa đúng một giá trị theo ngữ nghĩa server |
| `setAttributeValues("member", ...)` | Kiểm tra ý nghĩa replace toàn bộ tập giá trị |
| Attribute thiếu hoặc binary | Mapping xử lý null/kiểu đúng |
| Entry nằm trong OU lồng nhau | DN tương đối/base và search scope đúng |
| Username có dấu phẩy/dấu cộng/backslash | DN builder escape đúng |
| Account chỉ đọc cố modify | Server từ chối và app báo lỗi phù hợp |
| Sửa `sn`/objectClass trái schema | Không bỏ qua lỗi schema |
| Hai cập nhật đồng thời | Kiểm chứng lost update và giải pháp concurrency nếu cần |
| LDAPS/StartTLS/truststore sai | Không fallback về plaintext |
| Server timeout/mất kết nối | Không kết luận bừa trạng thái dữ liệu |

### 19.4. Kiểm thử chức năng và hiệu năng là hai phạm vi khác nhau

- Unit test mapper xác minh chuyển đổi trong Java, **không** xác minh schema/ACL server.
- Integration test LDAP xác minh thao tác thực, DN, permissions và kết quả.
- Test hiệu năng phải sử dụng dữ liệu và tải đủ đại diện; thời gian thao tác phụ thuộc index, mạng, TLS, số entry và server.

Không đưa ra benchmark giả định kiểu “dùng `DirContextAdapter` nhanh gấp hai lần `AttributesMapper`”. Chọn abstraction trước hết theo **đúng nhu cầu DN, attribute và update**; đo hiệu năng thực tế nếu cần tối ưu.

## 20. Bài tập vận dụng

**Bối cảnh:** hệ thống nhân sự có các entry dưới `ou=people,dc=example,dc=org`, một số người ở `ou=engineering`. Có group `cn=developers,ou=groups,dc=example,dc=org`. Ứng dụng cần hiển thị hồ sơ, sửa điện thoại và thêm nhân viên vào group.

Hãy trả lời:

1. Vì sao `AttributesMapper` đủ cho DTO chỉ có `uid` và `cn` nhưng `ContextMapper` hữu ích nếu cần DN?
2. Có thể gọi `entry.setAttributeValue("telephoneNumber", value)` rồi trả HTTP 200 mà không gọi `modifyAttributes` không?
3. Với `ContextSource.base = dc=example,dc=org`, DN tương đối của `uid=lan,ou=people,dc=example,dc=org` là gì?
4. Vì sao dùng `getStringAttribute("member")` để lấy membership có thể sai?
5. Khi chỉ cần thêm một member, vì sao `setAttributeValues("member", new String[]{newDn})` có thể nguy hiểm?
6. Cách nào để thêm entry mới bằng adapter? Khác gì luồng sửa entry hiện có?
7. Nếu hai request cùng sửa `telephoneNumber`, adapter có tự phát hiện lost update không?
8. Khi một setter chạy thành công nhưng LDAP server từ chối modify, trạng thái nào đã đổi và trạng thái nào chưa chắc đã đổi?
9. Vì sao không được lấy DN client gửi rồi cho phép sửa mọi attribute?
10. `DirContextAdapter` có phải một JNDI `DirContext` đang giữ socket không?
11. Nếu cần xác thực username/password, có nên đọc `userPassword` qua adapter rồi tự so sánh không?
12. Làm sao kiểm tra kết quả mapping trên server thật khi tài khoản bind không có quyền đọc `mail`?

**Gợi ý đáp án:**

1. `AttributesMapper` có thuộc tính; `ContextMapper` nhận `DirContextOperations` và có thể dùng `getDn()`.
2. Không; setter chỉ sửa object trong bộ nhớ, phải gọi thao tác ghi.
3. `uid=lan,ou=people` (theo ngữ cảnh Spring LDAP tương đối đã mô tả).
4. Attribute `member` có thể có nhiều giá trị.
5. Nó mô tả tập giá trị mới và có thể thay thế các thành viên trước đó.
6. Tạo `new DirContextAdapter(dn)`, đặt objectClass/attributes và `ldapTemplate.bind(adapter)`; sửa entry cần `lookupContext` rồi `modifyAttributes`.
7. Không; phải thiết kế concurrency riêng.
8. Adapter đã đổi; server có thể chưa đổi hoặc trạng thái cần xác minh sau lỗi mạng.
9. Cần authorization, whitelist attribute và DN validation, kết hợp ACL server.
10. Không; đó là object đại diện dữ liệu entry phía Java.
11. Không; dùng LDAP bind/Spring Security LDAP.
12. Dùng integration test với ACL tương ứng, kiểm tra optional field và kết quả getter, không tự giả định dữ liệu thiếu nghĩa là entry thiếu.

## 21. Checklist khi triển khai

- [ ] Chọn `AttributesMapper` khi chỉ cần attributes; chọn `ContextMapper` khi cần DN/context.
- [ ] Phân biệt rõ `DirContextOperations`, `DirContextAdapter` và JNDI `DirContext`.
- [ ] Xác định full DN và relative DN theo `ContextSource.base`.
- [ ] Dùng `LdapNameBuilder` cho DN và filter builder cho dữ liệu lọc.
- [ ] Không giả định mọi attribute có một giá trị hoặc kiểu `String`.
- [ ] Kiểm tra optional attributes, ACL và returning attributes.
- [ ] Khi tạo entry, dùng adapter mới và `bind`; khi sửa, dùng lookup + set + modify.
- [ ] Ghi nhớ setter trên adapter **không tự gửi thay đổi** lên server.
- [ ] Dùng add/remove cho thay đổi một giá trị trong tập multi-valued khi phù hợp.
- [ ] Tránh ghi đè toàn bộ group membership ngoài ý định.
- [ ] Xem schema và matching rules trước khi thay attribute hoặc so giá trị.
- [ ] Có chiến lược concurrency, retry/idempotency và xử lý lỗi ghi không chắc chắn.
- [ ] Giới hạn quyền bind, xác minh TLS và bảo vệ secrets.
- [ ] Không log toàn bộ adapter hoặc credentials.
- [ ] Viết unit test mapper/adapter và integration test với LDAP server có schema, ACL, DN thực tế.

## 22. Tóm tắt

**`DirContextOperations` là giao diện Spring LDAP cho việc làm việc với dữ liệu một entry, bao gồm DN, getters/setters thuộc tính và thông tin thay đổi. `DirContextAdapter` là implementation phổ biến có thể được Spring tạo ra khi tìm kiếm/lookup hoặc do ứng dụng tự tạo để thêm entry.**

Nếu chỉ cần dữ liệu để hiển thị, `AttributesMapper` có thể đủ. Nếu cần DN hoặc phương thức tiện ích của adapter, dùng `ContextMapper`. Khi **cập nhật**, lấy `DirContextOperations` từ `lookupContext(...)`, sửa các thuộc tính mong muốn và gọi `ldapTemplate.modifyAttributes(entry)`; khi **tạo entry**, tạo `DirContextAdapter(dn)`, đặt objectClass/attributes rồi gọi `ldapTemplate.bind(entry)`.

Adapter giúp code biểu đạt thay đổi rõ ràng, nhưng không thay schema, LDAP ACL, matching rules, kết nối TLS, xác thực hay giải quyết cập nhật đồng thời. Những ràng buộc này vẫn cần được thiết kế và kiểm thử ở từng tầng hệ thống.

### Tài liệu tham khảo

- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/)
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP — Updating](https://docs.spring.io/spring-ldap/reference/using.html)
- [Spring LDAP Javadoc — DirContextOperations](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextOperations.html)
- [Spring LDAP Javadoc — DirContextAdapter](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/DirContextAdapter.html)
- [Spring LDAP Javadoc — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html)
- [Java SE — javax.naming.directory.DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html)
- [Java SE — ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html)
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511)
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517)
