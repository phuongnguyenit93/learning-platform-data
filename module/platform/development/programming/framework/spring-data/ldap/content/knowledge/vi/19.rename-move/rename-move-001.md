# Đổi RDN và di chuyển entry bằng rename

> **Chương:** Đổi tên và di chuyển  
> **Phạm vi:** Spring Data LDAP — quản lý entry phân cấp trong directory thông qua Spring LDAP `LdapTemplate` và mô hình repository.

Trong LDAP, một entry có **Distinguished Name (DN)** để định danh vị trí trong cây thư mục. Khi đổi giá trị đặt tên ở đầu DN hoặc chuyển entry sang một nhánh khác, ứng dụng cần thực hiện thao tác **rename / ModifyDN**. Chỉ sửa các thuộc tính Java rồi gọi `save(...)` không đồng nghĩa với việc directory server sẽ đổi DN.

Ví dụ, hệ thống quản lý nhân sự có thể cần:

- Đổi mã đăng nhập của nhân viên từ `lan` thành `lan.nguyen`.
- Chuyển hồ sơ từ nhánh nhân viên đang làm việc `ou=people` sang nhánh lưu trữ `ou=alumni`.
- Đổi cả tên entry và nhánh cha trong **một yêu cầu ModifyDN**, nếu server hỗ trợ.

Bài học giải thích những thay đổi này trên mô hình LDAP, cách thực hiện bằng `LdapTemplate.rename(...)`, các ràng buộc schema/quyền và phương pháp kiểm thử an toàn.

## 1. Ôn lại DN, RDN và vị trí entry

Xét cây thư mục:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=lan
└── ou=alumni
~~~

DN đầy đủ của nhân viên:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| **DN** | `uid=lan,ou=people,dc=example,dc=org` | Tên phân biệt đầy đủ của entry |
| **RDN** | `uid=lan` | Tên tương đối của entry so với cha trực tiếp |
| **Parent DN** | `ou=people,dc=example,dc=org` | Entry cha chứa entry hiện tại |
| **Base DN** | `dc=example,dc=org` | Phạm vi gốc thường dùng trong cấu hình kết nối của ứng dụng |

DN được cấu tạo từ các RDN. Thành phần ở phía trái trong cách hiển thị LDAP thông dụng là RDN của chính entry; các thành phần phía sau mô tả các entry cha.

**Đổi RDN** làm thay đổi cách entry được đặt tên trong cùng nhánh. **Di chuyển** làm thay đổi parent DN. Hai thay đổi có thể được yêu cầu cùng lúc:

| Thao tác | DN trước | DN sau |
|---|---|---|
| Đổi RDN | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan.nguyen,ou=people,dc=example,dc=org` |
| Di chuyển | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan,ou=alumni,dc=example,dc=org` |
| Đổi RDN và di chuyển | `uid=lan,ou=people,dc=example,dc=org` | `uid=lan.nguyen,ou=alumni,dc=example,dc=org` |

Đổi tên thuộc tính hiển thị, chẳng hạn `displayName`, là một **Modify** thông thường nếu thuộc tính đó không tham gia RDN. Ngược lại, đổi giá trị `uid` đang dùng trong `uid=lan` phải xem xét **ModifyDN**, để DN và thuộc tính đặt tên không trở nên không nhất quán.

## 2. LDAP ModifyDN hoạt động như thế nào?

Ở mức giao thức, thao tác cần dùng là **Modify DN** (thường được gọi `ModifyDN` hoặc `ModifyRDN`). Yêu cầu có các thành phần quan trọng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `entry` | DN hiện tại của entry cần sửa tên/vị trí | `uid=lan,ou=people,dc=example,dc=org` |
| `newRDN` | RDN mới bắt buộc trong yêu cầu | `uid=lan.nguyen` |
| `deleteOldRDN` | Có xóa giá trị thuộc tính tạo RDN cũ hay giữ lại | `TRUE` / `FALSE` |
| `newSuperior` | DN của entry cha mới, nếu chuyển nhánh | `ou=alumni,dc=example,dc=org` |

Khi chỉ đổi RDN, `newSuperior` không được cung cấp và parent DN được giữ nguyên. Khi chỉ di chuyển, `newRDN` vẫn xuất hiện nhưng có thể giữ cùng giá trị với RDN hiện tại.

**Điểm dễ nhầm về `deleteOldRDN`:** đây là quyết định giữ hay loại bỏ **giá trị thuộc tính tạo RDN cũ trong entry**, không phải xóa entry cũ hay quyết định có đổi DN hay không.

Ví dụ từ `uid=lan` sang `uid=lan.nguyen`:

- Với `deleteOldRDN=TRUE`, server có thể loại `uid: lan` và thêm/giữ `uid: lan.nguyen` theo quy tắc LDAP.
- Với `deleteOldRDN=FALSE`, server giữ giá trị `uid: lan`; thuộc tính `uid` có thể có thêm `lan.nguyen` nếu schema cho phép nhiều giá trị.
- Với thuộc tính đặt tên dạng một giá trị hoặc ràng buộc chặt hơn, kết quả có thể bị từ chối nếu không hợp lệ theo schema.

Ở tầng Spring LDAP, `LdapTemplate.rename(oldDn, newDn)` truyền ý định đổi DN cho tầng JNDI/provider. API này không có tham số `deleteOldRDN` trực tiếp; nếu nghiệp vụ cần kiểm soát chính xác cách giữ/xóa giá trị RDN, hãy xem khả năng cấu hình của JNDI provider và kiểm chứng bằng thử nghiệm với server thật. Không dựa vào giả định rằng mọi server xử lý cờ này giống nhau.

### Minh họa trong LDIF

Đổi RDN, vẫn nằm trong `ou=people`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
changetype: modrdn
newrdn: uid=lan.nguyen
deleteoldrdn: 1
~~~

Di chuyển entry vừa đổi tên sang `ou=alumni`:

~~~ldif
dn: uid=lan.nguyen,ou=people,dc=example,dc=org
changetype: moddn
newrdn: uid=lan.nguyen
deleteoldrdn: 1
newsuperior: ou=alumni,dc=example,dc=org
~~~

Đây là các **change record** LDIF minh họa yêu cầu đổi tên/di chuyển, không phải định nghĩa entry mới. `modrdn` và `moddn` đều biểu diễn loại thay đổi liên quan đến ModifyDN; `newsuperior` xác định cha mới khi có chuyển nhánh.

## 3. Các điều kiện phải kiểm tra trước khi rename

Trước khi gửi ModifyDN, hãy xem xét:

1. **Entry nguồn tồn tại:** DN cũ phải xác định đúng một entry có thể truy cập.
2. **Parent đích tồn tại:** ví dụ `ou=alumni,dc=example,dc=org` phải là một entry hợp lệ và có thể chứa entry được chuyển đến.
3. **DN đích không xung đột:** thường không thể chuyển thành một DN đã được dùng bởi entry khác. Các RDN của các entry con trực tiếp trong cùng parent phải phân biệt.
4. **RDN mới hợp lệ:** attribute type dùng để đặt tên phải được schema của entry cho phép; việc đổi giá trị không được làm entry vi phạm `MUST` hoặc các ràng buộc schema.
5. **Quyền truy cập đầy đủ:** tài khoản bind cần các quyền liên quan đến việc đổi tên, sửa thuộc tính đặt tên, xóa/đưa entry ra khỏi nhánh cũ và tạo/đặt entry tại nhánh mới theo mô hình ACL của server.
6. **Server cho phép di chuyển đó:** không phải mọi directory hỗ trợ di chuyển giữa mọi naming context hoặc backend; một số không cho rename entry đang có con.
7. **Phụ thuộc khác được xem xét:** nhóm, quản lý hoặc hệ thống ngoài có thể đang lưu DN cũ. Việc đổi DN không tự động bảo đảm các tham chiếu này được cập nhật.

**Phân biệt hai kiểu trùng lặp:** nếu một entry có cùng `uid` ở hai nhánh khác nhau, các DN vẫn khác nhau. Schema chuẩn không mặc định áp đặt `uid` duy nhất trên mọi nhánh. Nhưng việc chuyển hai entry đến **cùng DN đích** sẽ xung đột.

### Entry có con và ảnh hưởng đến nhánh con

Giả sử cần đổi:

~~~text
ou=engineering,dc=example,dc=org
├── uid=lan
└── uid=binh
~~~

thành:

~~~text
ou=product-engineering,dc=example,dc=org
├── uid=lan
└── uid=binh
~~~

Đây có thể là **rename subtree**, kéo theo thay đổi DN của các entry con. Khả năng hỗ trợ, giới hạn và hành vi phụ thuộc directory server, backend, chính sách ACL và quy tắc cây. Không nên coi việc gọi `rename(...)` trên một nhánh có con là an toàn/khả dụng ở mọi LDAP server. Kiểm thử riêng trường hợp này trước khi triển khai.

## 4. Spring LDAP: đổi RDN bằng LdapTemplate.rename

**Spring Data LDAP** cung cấp khả năng ánh xạ entry với entity Java và làm việc qua `LdapRepository`. Đối với thao tác đổi DN, Spring LDAP `LdapTemplate` có API riêng:

~~~java
void rename(Name oldDn, Name newDn);
~~~

Có thể dùng tên được biểu diễn bằng chuỗi ở các overload tương ứng, nhưng tạo DN qua `LdapNameBuilder` giúp xử lý escaping của giá trị RDN đúng cách.

### Cấu hình base DN

Giả sử Spring Boot cấu hình:

~~~properties
spring.ldap.urls=ldaps://ldap.example.org:636
spring.ldap.base=dc=example,dc=org
~~~

Khi `ContextSource` đã có base DN `dc=example,dc=org`, các DN truyền cho `LdapTemplate` trong ví dụ sau là **DN tương đối với base đó**:

~~~text
uid=lan,ou=people
uid=lan.nguyen,ou=people
~~~

Không tự thêm `dc=example,dc=org` lần nữa vào các DN tương đối, vì có thể khiến server nhận đường dẫn sai. Nếu `ContextSource` không cấu hình base DN, ứng dụng cần sử dụng DN theo phạm vi kết nối thực tế. Cách xử lý DN phải thống nhất giữa cấu hình và mã nguồn.

### Ví dụ service đổi RDN

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonDnService {

    private final LdapTemplate ldapTemplate;

    public PersonDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void renameUid(String oldUid, String newUid) {
        Name oldDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", oldUid)
                .build();

        Name newDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", newUid)
                .build();

        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

Với lời gọi:

~~~java
personDnService.renameUid("lan", "lan.nguyen");
~~~

DN tương đối chuyển từ `uid=lan,ou=people` sang `uid=lan.nguyen,ou=people`. Hai DN dùng cùng parent, nên mục đích ở đây chỉ là đổi RDN.

**Điều gì xảy ra với entry?** Server xử lý yêu cầu đổi DN, cập nhật thuộc tính đặt tên theo ngữ nghĩa ModifyDN và kiểm tra các ràng buộc. Entry được định danh tại DN mới nếu thành công. Không cần đọc toàn bộ entry rồi xóa entry cũ và tạo entry mới để mô phỏng thao tác đổi tên.

**Vì sao dùng `LdapNameBuilder`?** Một giá trị mã người dùng có thể chứa dấu phẩy, dấu bằng hoặc ký tự đặc biệt trong cú pháp DN. Nếu nối chuỗi thủ công:

~~~java
// Tránh:
String dn = "uid=" + input + ",ou=people";
~~~

người dùng có thể vô tình hoặc cố ý làm DN bị phân tích thành nhiều thành phần. `LdapNameBuilder.add("uid", input)` xây dựng RDN bằng API xử lý escape DN. Đối với truy vấn LDAP filter, cần sử dụng **cơ chế escape filter riêng**; escaping DN và escaping filter là hai quy tắc khác nhau.

## 5. Di chuyển entry sang parent khác bằng rename

Di chuyển trong LDAP là thay đổi DN đích để sử dụng parent mới. Ví dụ chuyển người đã nghỉ việc từ nhánh nhân sự `ou=people` sang `ou=alumni`, giữ nguyên RDN `uid=lan`:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class PersonMoveService {

    private final LdapTemplate ldapTemplate;

    public PersonMoveService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveToAlumni(String uid) {
        Name sourceDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        Name targetDn = LdapNameBuilder.newInstance("ou=alumni")
                .add("uid", uid)
                .build();

        ldapTemplate.rename(sourceDn, targetDn);
    }

    public void renameAndMove(
            String oldUid, String newUid) {
        Name sourceDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", oldUid)
                .build();

        Name targetDn = LdapNameBuilder.newInstance("ou=alumni")
                .add("uid", newUid)
                .build();

        ldapTemplate.rename(sourceDn, targetDn);
    }
}
~~~

Hai phương thức minh họa:

- `moveToAlumni("lan")`: thay đổi parent `ou=people` → `ou=alumni`, giữ RDN `uid=lan`.
- `renameAndMove("lan", "lan.nguyen")`: đổi cả RDN và parent trong một lần gọi `rename`.

**Giới hạn quan trọng:** việc truyền DN mới có parent khác chỉ thành công khi provider và server hỗ trợ thao tác tương ứng, parent mới hợp lệ và đủ quyền. Di chuyển giữa các naming context, các backend khác nhau hoặc các directory server khác nhau có thể bị từ chối. `rename` không phải API sao chép entry giữa hai máy chủ LDAP.

### Sơ đồ luồng thao tác

~~~mermaid
flowchart TD
    A["Ứng dụng nhận yêu cầu đổi mã / chuyển nhánh"] --> B["Xây dựng oldDn và newDn bằng LdapNameBuilder"]
    B --> C["LdapTemplate.rename(oldDn, newDn)"]
    C --> D["JNDI / LDAP ModifyDN"]
    D --> E{"Directory server chấp nhận?"}
    E -->|Có| F["Entry có DN mới"]
    E -->|Không| G["Trả lỗi LDAP, entry chưa được đổi theo yêu cầu"]
    F --> H["Đọc lại DN mới và kiểm tra tham chiếu liên quan"]
~~~

## 6. Ảnh hưởng tới Entity và LdapRepository

Trong mô hình đối tượng, DN thường được ánh xạ qua `@Id`:

~~~java
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
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;
}
~~~

Sau khi gọi `LdapTemplate.rename(oldDn, newDn)`, cần nhớ:

1. **DN là danh tính trong directory:** kết quả tìm theo DN cũ có thể không còn entry; cần tìm theo DN mới.
2. **Đối tượng Java đã tải trước đó không được tự làm mới:** trường `@Id` của object đang nằm trong bộ nhớ có thể vẫn mang DN cũ. Hãy tải lại entry hoặc điều chỉnh trạng thái object theo luồng ứng dụng.
3. **Repository có base tĩnh có thể không nhìn thấy entry đã chuyển đi:** entity với `@Entry(base = "ou=people")` được thiết kế cho nhánh người dùng đó. Khi entry chuyển sang `ou=alumni`, cần entity/repository hoặc phạm vi truy vấn phù hợp nếu còn muốn thao tác trên entry tại nhánh mới.
4. **Không xem việc thay `@Id` rồi `repository.save(...)` là cách chuẩn để đổi tên:** `save` phục vụ ghi/thay đổi entity theo mapping; ý định đổi DN cần thao tác rename tường minh để tránh hành vi thêm mới, lỗi tồn tại DN hoặc thay đổi sai entry.
5. **Tham chiếu DN trong entry khác không mặc định được sửa:** `member` của nhóm hoặc `manager` của người dùng có thể chứa DN cũ. Directory có thể có tính năng tham chiếu tự động, nhưng ứng dụng phải xác minh điều đó.

Nếu chức năng cho phép nhiều nhánh, cần xác định rõ repository nào quản lý entry ở nhánh nào. Việc đổi base của `@Entry` hoặc sửa entity Java không tự di chuyển bản ghi trên server.

### Kiểm tra kết quả sau rename

Ví dụ đọc lại thuộc tính `uid` tại DN đích:

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

// targetDn được xây dựng trước đó bằng LdapNameBuilder.
String uidAtTarget = ldapTemplate.lookup(
        targetDn,
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
);
~~~

Mẫu này phù hợp khi entry ở DN mới có thuộc tính `uid`. Trong code production, cần xử lý tình huống attribute không được trả về do quyền truy cập hoặc không tồn tại. Nên xác minh cả entry không còn ở DN cũ (nếu không phải thao tác tạo bản sao), đồng thời kiểm tra các giá trị RDN thực tế nếu nghiệp vụ phụ thuộc vào chúng.

## 7. Rename khác Modify, Delete/Add và thay thế dữ liệu

| Cách làm | Dùng khi nào | Hệ quả cần chú ý |
|---|---|---|
| `ldapTemplate.rename(oldDn, newDn)` | Đổi RDN, đổi parent hoặc cả hai trong cùng directory, khi server hỗ trợ | Giữ thao tác theo ngữ nghĩa ModifyDN; DN có thể thay đổi đối với mọi tham chiếu |
| `ldapTemplate.modifyAttributes(...)` | Sửa giá trị thuộc tính không phải mục tiêu đổi DN | Không dùng thay cho ModifyDN để định danh entry sang DN khác |
| Xóa entry cũ rồi tạo entry mới | Chỉ khi có yêu cầu di chuyển/sao chép dữ liệu đặc thù và không thể dùng ModifyDN | Có nguy cơ mất thuộc tính do server quản lý, quyền, lịch sử, tham chiếu và xảy ra lỗi giữa hai bước |
| Thay `@Id` trên Java entity rồi `save(...)` | Không nên xem là chiến lược đổi DN | Mapping repository không bảo đảm thực hiện thao tác ModifyDN như dự định |
| Sao chép qua hai directory server | Cần thiết kế đồng bộ/migration riêng | Một ModifyDN không chuyển được dữ liệu tùy ý qua các server |

**Ví dụ:** nếu nhân viên đổi họ hiển thị nhưng DN vẫn là `uid=lan,ou=people,...`, thường chỉ cần Modify `sn`/`cn`. Nếu hệ thống quyết định tên entry phải là `uid=lan.nguyen`, cần ModifyDN. Trường hợp đổi cả thông tin hồ sơ và DN đòi hỏi định nghĩa thứ tự, xử lý lỗi từng bước và tính nhất quán dữ liệu.

Một thao tác ModifyDN thành công là một yêu cầu riêng được server xử lý. Chuỗi thao tác `Modify + ModifyDN + cập nhật tham chiếu` không mặc nhiên có transaction nguyên khối trong mọi LDAP directory. Cần thiết kế retry, đối soát và phục hồi khi quy trình gồm nhiều bước.

## 8. Các lỗi thường gặp và cách chẩn đoán

Server có thể trả về mã kết quả LDAP; Spring LDAP/JNDI chuyển các lỗi đó thành exception trong ứng dụng. Tên exception cụ thể phụ thuộc phiên bản thư viện và lớp chuyển đổi lỗi, vì vậy hãy ghi nhận **mã LDAP và chẩn đoán từ server** khi điều tra.

| Mã LDAP | Tình huống điển hình | Cách xử lý |
|---|---|---|
| `noSuchObject (32)` | DN nguồn hoặc parent cần thiết không tồn tại | Kiểm tra DN tương đối với base và entry cha |
| `invalidDNSyntax (34)` | DN/RDN sai cú pháp | Dùng `LdapNameBuilder`; kiểm tra escaping |
| `insufficientAccessRights (50)` | Tài khoản thiếu quyền đổi tên hoặc di chuyển | Kiểm tra ACL ở nguồn, đích và thuộc tính liên quan |
| `unwillingToPerform (53)` | Server/chính sách từ chối thao tác | Kiểm tra hạn chế backend, subtree, chính sách và log |
| `namingViolation (64)` | Quy tắc đặt tên hoặc DIT không cho phép DN mới | Xem ràng buộc tên và vị trí entry |
| `objectClassViolation (65)` | Entry sau khi thay RDN không hợp lệ theo schema | Xem attribute đặt tên, `MUST`/`MAY` |
| `notAllowedOnNonLeaf (66)` | Server không cho thao tác liên quan entry đang có con | Xác minh hỗ trợ rename subtree và chính sách |
| `entryAlreadyExists (68)` | DN đích đã có entry | Chọn DN khác hoặc xử lý xung đột |
| `affectsMultipleDSAs (71)` | Thao tác đụng giới hạn giữa các naming context/DSA | Thiết kế migration riêng hoặc chọn đích hỗ trợ |

Mã lỗi liệt kê là các khả năng thường gặp, **không phải ánh xạ một–một bắt buộc**. Cùng một tình huống có thể dẫn đến mã khác tùy triển khai directory server.

**Chẩn đoán theo thứ tự thực tế:**

1. Log DN nguồn và DN đích theo định dạng đã xử lý an toàn, tránh ghi thông tin nhạy cảm không cần thiết.
2. Xác nhận context base và các DN tương đối.
3. Kiểm tra sự tồn tại của nguồn, parent đích và đích trùng tên.
4. Kiểm tra quyền bind và cấu hình schema.
5. Kiểm tra server có cho ModifyDN với parent mới, entry có con hoặc naming context đang xét không.
6. Nếu đổi DN thành công nhưng ứng dụng không tìm thấy entry, kiểm tra lại base/scope của repository và bộ nhớ đệm đang giữ DN cũ.

Không nên tự động chuyển sang Delete/Add ngay khi gặp lỗi rename. Cần phân loại nguyên nhân, vì cách này có thể làm mất dữ liệu hoặc tạo trạng thái dở dang.

## 9. Bảo mật khi đổi tên và di chuyển

Bảo mật rename trong LDAP liên quan cả đường truyền, danh tính gọi API và các giới hạn dữ liệu:

- **Kết nối được bảo vệ:** dùng LDAPS hoặc StartTLS với cấu hình xác thực chứng chỉ đúng; không gửi mật khẩu bind hoặc thông tin nhạy cảm qua kết nối không bảo vệ.
- **Đặc quyền tối thiểu:** cấp quyền đổi tên/di chuyển đúng nhánh cho service account, không dùng tài khoản quản trị directory cho mọi thao tác ứng dụng.
- **Kiểm soát đích được phép:** ví dụ tính năng “chuyển nhân sự sang alumni” chỉ cho chuyển giữa các OU đã định nghĩa; không chấp nhận DN đích bất kỳ do người dùng gửi.
- **Xây dựng DN bằng API:** ghép DN từ giá trị RDN đã được xử lý bằng `LdapNameBuilder`; kiểm tra cấu trúc DN đích thực sự nằm trong nhánh cho phép.
- **Kiểm soát thay đổi:** log sự kiện đổi DN với chủ thể, thời điểm, DN nguồn/đích và kết quả phù hợp với chính sách bảo mật; không log mật khẩu hoặc bí mật trong thuộc tính.
- **Tham chiếu và quyền sau di chuyển:** entry chuyển sang OU mới có thể chịu ACL và chính sách khác; cần kiểm tra khả năng đọc/ghi sau khi đổi vị trí.

Đặc biệt, **escaping DN không thay thế authorization**. Người dùng có thể đưa một giá trị hợp lệ về cú pháp nhưng không được phép đặt entry vào nhánh hoặc tên đó. Cả ứng dụng và server phải thực thi quyền phù hợp.

## 10. Kiểm thử tích hợp với directory

Bài học cần được kiểm chứng trên directory có **schema, cấu trúc nhánh và chính sách ACL tương đương môi trường triển khai**. Có thể dùng LDAP server phục vụ integration test, nhưng phải bật/đảm bảo kiểm tra schema nếu muốn xác nhận các ràng buộc đó.

### Kịch bản gợi ý

| Kịch bản | Thiết lập | Kỳ vọng |
|---|---|---|
| Đổi RDN thành công | `uid=lan` có sẵn, `uid=lan.nguyen` chưa tồn tại | Entry đọc được bằng DN mới; DN cũ không còn tìm thấy |
| Di chuyển thành công | Parent `ou=alumni` tồn tại, server cho phép | Entry chuyển từ `ou=people` sang `ou=alumni` |
| Đổi RDN đồng thời di chuyển | RDN và parent đều thay đổi | Entry đến DN đích mong muốn sau một yêu cầu |
| DN đích trùng | Đã có entry tại DN đích | Server từ chối, không ghi đè entry đích |
| Parent đích không tồn tại | `ou=missing` chưa được tạo | Server từ chối thao tác |
| Thiếu quyền | Bind bằng tài khoản không đủ quyền | Server từ chối, không đổi vị trí entry |
| Giá trị RDN có ký tự đặc biệt | Ví dụ dấu phẩy, dấu bằng, khoảng trắng | DN được escape và phân tích thành một RDN đúng |
| Đổi giá trị RDN cũ | Theo dõi các giá trị `uid` sau rename | Xác nhận hành vi giữ/xóa giá trị RDN cũ phù hợp server |
| Entry đang có con | Rename nhánh có nhiều entry con | Xác nhận server có hỗ trợ và tất cả DN con được xử lý như kỳ vọng |
| Tham chiếu từ nhóm | `member` trỏ tới DN cũ | Xác nhận quy tắc cập nhật tham chiếu hoặc bước sửa liên quan |
| Repository có base cố định | Di chuyển khỏi `ou=people` | Xác nhận truy vấn cũ không còn bao phủ entry ở nhánh mới |

### Quy trình kiểm thử đổi RDN

1. Tạo nhánh và entry mẫu có schema hợp lệ, ví dụ `inetOrgPerson` với các thuộc tính bắt buộc `cn` và `sn`.
2. Kiểm tra DN nguồn hiện diện trước khi gọi service.
3. Gọi `personDnService.renameUid("lan", "lan.nguyen")`.
4. Dùng `ldapTemplate.lookup(...)` hoặc truy vấn base-scope để đọc entry tại DN mới.
5. Xác nhận DN cũ không còn định danh entry; kiểm tra `uid` và các thuộc tính nghiệp vụ vẫn đúng.
6. Dọn dữ liệu test theo DN mới và bảo đảm lần chạy kế tiếp độc lập với kết quả trước đó.

Với trường hợp di chuyển, nên kiểm tra thêm **nhánh nguồn không còn entry**, **nhánh đích có entry** và **tham chiếu từ entry khác** có được điều chỉnh hay không.

### Kịch bản vận hành nhiều bước

Giả sử quy trình nghỉ việc vừa di chuyển nhân viên sang `ou=alumni` vừa gỡ khỏi các nhóm:

~~~text
1. Xác minh entry nguồn, parent đích, các group liên quan
2. Thực hiện ModifyDN
3. Xác minh entry tại DN mới
4. Cập nhật thuộc tính member/manager còn trỏ DN cũ nếu cần
5. Xác minh toàn bộ hệ thống và ghi nhận kết quả
~~~

Đây là quy trình nghiệp vụ gồm nhiều yêu cầu, không tự nhiên là một transaction duy nhất. Cần xác định cách khôi phục/tiếp tục nếu bước 4 thất bại sau khi bước 2 đã thành công. Khi cho phép retry, hãy kiểm tra **trạng thái thực tế của DN nguồn và DN đích trước khi gửi lại** để tránh coi một lần rename thành công trước đó là lỗi dữ liệu.

## 11. Câu hỏi tự kiểm tra

1. Với DN `uid=lan,ou=people,dc=example,dc=org`, đâu là RDN và parent DN?
2. Khi di chuyển từ `ou=people` sang `ou=alumni` nhưng giữ nguyên `uid`, phần nào của DN thay đổi?
3. Vì sao sửa `@Id` trên entity rồi gọi `save(...)` không phải chiến lược bảo đảm đổi DN?
4. `deleteOldRDN` ảnh hưởng đến giá trị thuộc tính đặt tên như thế nào?
5. Vì sao entry vừa di chuyển có thể không còn xuất hiện trong repository với `@Entry(base = "ou=people")`?
6. Nếu `member` trong một nhóm vẫn tham chiếu DN cũ sau rename, cần kiểm tra tính năng hoặc quy trình nào?
7. Đâu là khác biệt giữa escape giá trị trong **DN** và escape đầu vào trong **LDAP filter**?

## 12. Kết luận và tài liệu tham khảo

**Đổi RDN và di chuyển entry là thay đổi danh tính/vị trí trong cây LDAP.** Thao tác cơ bản là ModifyDN, được Spring LDAP cung cấp ở tầng ứng dụng qua `LdapTemplate.rename(oldDn, newDn)`. Trước khi thực hiện, phải xác minh DN nguồn, parent đích, xung đột DN, schema, ACL và giới hạn của server. Sau khi thực hiện, phải đọc lại entry tại DN mới và kiểm tra các tham chiếu DN liên quan.

Tài liệu kỹ thuật để tra cứu thêm:

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): định nghĩa thao tác ModifyDN, `newrdn`, `deleteoldrdn` và `newSuperior`.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): mô hình DN/RDN, entry, object class và DIT.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cách biểu diễn và escape DN dưới dạng chuỗi.
- [RFC 2849 — LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849): cú pháp `modrdn`, `moddn` và `newsuperior` trong LDIF change record.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, thao tác LDAP và các tiện ích tạo DN.
