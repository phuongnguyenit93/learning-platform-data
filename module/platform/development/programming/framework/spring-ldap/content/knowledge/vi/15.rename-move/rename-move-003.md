# Move entry sang parent DN khác trong Spring LDAP

Khi tài khoản đổi phòng ban hoặc một nhóm dữ liệu được chuyển sang đơn vị quản lý khác, ứng dụng thường phải **di chuyển entry đến parent DN mới** trong cây LDAP. Thao tác này khác với việc chỉ đổi một attribute: vị trí của entry là một phần của **Distinguished Name (DN)**. Di chuyển đúng cách đòi hỏi hiểu cấu trúc DN, điều kiện hợp lệ của đích, quyền trên các nhánh liên quan và tác động đến những hệ thống đang lưu DN cũ.

Bài học thuộc chương **Rename và move** của **Spring LDAP**. Nội dung tập trung vào cách chuyển entry từ parent này sang parent khác bằng thao tác LDAP **Modify DN**, thể hiện qua `LdapTemplate.rename(...)` hoặc JNDI `DirContext.rename(...)`. Các nguyên tắc này cũng cần nắm khi ứng dụng dùng `LdapClient` hoặc Object-Directory Mapping (ODM). Giả sử máy chủ chứa cây `dc=example,dc=org` và `ContextSource` của Spring LDAP đã được cấu hình với base DN đó.

## 1. Di chuyển entry nghĩa là thay đổi gì?

Giả sử ban đầu người dùng Linh nằm trong nhánh nhân sự đang làm việc:

~~~text
dc=example,dc=org
├── ou=active
│   └── uid=linh
└── ou=alumni
~~~

DN ban đầu là:

~~~text
uid=linh,ou=active,dc=example,dc=org
~~~

Khi Linh chuyển sang nhóm cựu nhân sự, ta muốn cây trở thành:

~~~text
dc=example,dc=org
├── ou=active
└── ou=alumni
    └── uid=linh
~~~

DN mới là:

~~~text
uid=linh,ou=alumni,dc=example,dc=org
~~~

Trong ví dụ này:

- **RDN của entry** vẫn là `uid=linh`.
- **Parent DN cũ** là `ou=active,dc=example,dc=org`.
- **Parent DN mới** là `ou=alumni,dc=example,dc=org`.
- **DN đầy đủ** đổi vì phần đường dẫn chứa parent DN đổi.
- Các attribute nội dung như `cn`, `sn` hoặc `mail` không nhất thiết phải đổi chỉ vì entry chuyển vị trí.

Có thể mô tả ngắn gọn:

~~~text
oldDn = rdn + "," + oldParentDn
newDn = rdn + "," + newParentDn

oldDn: uid=linh,ou=active,dc=example,dc=org
newDn: uid=linh,ou=alumni,dc=example,dc=org
rdn:   uid=linh             (không đổi)
~~~

Đây là **move thuần túy**. Nếu đồng thời thay `uid=linh` thành `uid=linh.nguyen` thì vừa có **rename RDN**, vừa có **move parent**.

### So sánh rename, move và modify attribute

| Nhu cầu | Ví dụ trước → sau | Thao tác phù hợp |
|---|---|---|
| Đổi RDN trong cùng parent | `uid=linh,ou=active` → `uid=linh.nguyen,ou=active` | Modify DN / rename |
| Chuyển parent, giữ RDN | `uid=linh,ou=active` → `uid=linh,ou=alumni` | Modify DN / move |
| Chuyển parent và đổi RDN | `uid=linh,ou=active` → `uid=linh.nguyen,ou=alumni` | Modify DN / rename + move |
| Đổi email, giữ DN | `mail: old@example.org` → `mail: new@example.org` | Modify attribute, không phải move |
| Tạo bản sao ở nhánh mới | Hai entry độc lập sau thao tác | Quy trình sao chép/tạo entry riêng, không phải move |

Lưu ý: các DN rút gọn trong bảng đều được hiểu có hậu tố `dc=example,dc=org`.

**Một entry không phải chỉ là một dòng được chuyển từ bảng này sang bảng khác.** DN vừa biểu diễn tên, vừa đặt entry vào cây. Do đó sau move, bộ phận ứng dụng nào lưu DN cũ có thể phải được cập nhật.

## 2. Cơ chế giao thức: Modify DN và `newSuperior`

LDAPv3 định nghĩa thao tác **Modify DN** (còn gọi *ModifyDN* hoặc *Modify RDN*) để đổi RDN của một entry và, nếu được hỗ trợ, chuyển nó tới parent DN mới.

Những thành phần logic của yêu cầu là:

| Thành phần | Ý nghĩa | Giá trị trong tình huống Linh |
|---|---|---|
| `entry` | DN hiện tại của entry cần đổi | `uid=linh,ou=active,dc=example,dc=org` |
| `newrdn` | RDN mà entry có ở vị trí mới | `uid=linh` |
| `deleteoldrdn` | Cách xử lý các giá trị attribute thuộc RDN cũ khi thay RDN | Boolean theo nghiệp vụ |
| `newSuperior` | DN của parent mới khi yêu cầu chuyển nhánh | `ou=alumni,dc=example,dc=org` |

Trong một **move giữ nguyên RDN**, `newrdn` vẫn là `uid=linh`, còn `newSuperior` thay đổi sang nhánh đích. Ngược lại, chỉ rename trong cùng parent thường không cần chuyển `newSuperior`.

~~~mermaid
flowchart TD
    A["Xác định old DN"] --> B["Chọn new RDN"]
    B --> C["Chọn newSuperior / parent đích"]
    C --> D["Kiểm tra DN, schema, quyền và đích"]
    D --> E["Gửi Modify DN"]
    E --> F{"Máy chủ chấp nhận?"}
    F -->|Có| G["Entry ở DN mới"]
    F -->|Không| H["Giữ nguyên hoặc xác minh trạng thái thực"]
    G --> I["Đối soát tham chiếu và dữ liệu ứng dụng"]
~~~

**Không nên nhầm `newSuperior` với một attribute sẽ được gắn vào entry.** Nó chỉ parent mới trong thao tác giao thức; DN là thông tin đặt tên của cây LDAP, không phải thuộc tính dữ liệu thông thường.

### Vai trò của `deleteOldRdn`

Đối với tình huống **đồng thời đổi RDN**, cần hiểu hiệu ứng lên attribute tạo tên. Ví dụ:

~~~text
oldDn = cn=Nguyen Van Linh,ou=active,dc=example,dc=org
newDn = cn=Tran Mai Linh,ou=alumni,dc=example,dc=org
~~~

- Khi chọn **xóa giá trị RDN cũ**, giá trị `cn: Nguyen Van Linh` dùng làm RDN cũ có thể được bỏ khỏi entry, miễn các ràng buộc schema vẫn được đáp ứng.
- Khi chọn **giữ giá trị RDN cũ**, entry có thể giữ cả tên cũ như một giá trị của attribute `cn` nếu attribute cho phép đa giá trị.
- Giá trị `cn: Tran Mai Linh` của RDN mới phải được bảo đảm tương ứng với tên mới.

Hành vi chi tiết với multi-valued RDN, attribute single-value và schema phụ thuộc quy tắc LDAP và server. Với **move không đổi RDN**, bài toán chính là parent mới; không cần tự sửa `uid` chỉ để thể hiện rằng entry đã chuyển nhánh.

## 3. Điều kiện để chuyển thành công

Một yêu cầu Modify DN chỉ được chấp nhận khi máy chủ, quyền truy cập và dữ liệu đáp ứng các điều kiện phù hợp.

### 3.1. Parent DN mới phải tồn tại

Đích `ou=alumni,dc=example,dc=org` phải tồn tại và nằm trong phạm vi mà máy chủ cho phép di chuyển entry tới. Modify DN không tự tạo parent còn thiếu.

### 3.2. DN mới không được trùng

Nếu đã có entry:

~~~text
uid=linh,ou=alumni,dc=example,dc=org
~~~

thì việc di chuyển Linh từ nhánh khác đến đó có thể bị từ chối với lỗi **`entryAlreadyExists` (68)**. Không thể mặc định LDAP sẽ ghi đè entry đích hoặc “gộp” hai tài khoản.

### 3.3. Schema và quy tắc đặt tên phải phù hợp

Tùy server, cấu trúc parent–child và RDN có thể chịu các ràng buộc schema hoặc chính sách đặt tên, ví dụ quy tắc về loại entry được phép nằm dưới một nhánh. Thay đổi RDN có thể đòi hỏi giữ đúng các giá trị thuộc tính của RDN và những attribute bắt buộc theo object class.

Một entry có `objectClass=inetOrgPerson` vẫn phải đáp ứng schema trước và sau khi move. **Move không tự sửa dữ liệu sai schema**, không chuyển object class từ người sang nhóm hay tổ chức khác.

### 3.4. Quyền phải phù hợp ở cả nguồn và đích

Các ACL của LDAP server có thể yêu cầu quyền liên quan đến entry cần move, parent cũ, parent mới và quyền tạo/xóa con. Tên chính xác của quyền phụ thuộc sản phẩm (chẳng hạn quyền xóa con ở nguồn và thêm con tại đích). Quyền đọc hoặc sửa email chưa chắc đủ cho việc di chuyển entry.

### 3.5. Không phải mọi ranh giới đều hỗ trợ move

Một số máy chủ chỉ cho rename/move trong **cùng naming context, partition hoặc phạm vi quản lý**. Move qua nhiều server hoặc qua ranh giới DSA không nên được kỳ vọng hoạt động như thao tác cùng một cây; có thể gặp lỗi **`affectsMultipleDSAs` (71)** hoặc lỗi riêng.

Ví dụ, chuyển từ `dc=example,dc=org` sang `dc=other,dc=org` không được đảm bảo chỉ bằng cách gọi `rename`. Nếu mục tiêu là đồng bộ giữa hai hệ thống LDAP khác nhau, phải thiết kế quy trình riêng, lưu ý attribute hệ thống, mật khẩu, ACL, tính nhất quán và yêu cầu sao lưu/khôi phục.

## 4. Thực hiện move bằng `LdapTemplate.rename(...)`

Spring LDAP cung cấp `LdapTemplate` để sử dụng JNDI thuận tiện và quản lý context trong phạm vi thao tác. Trong các phiên bản API hỗ trợ chữ ký sau, có thể dùng:

~~~java
ldapTemplate.rename(oldRelativeDn, newRelativeDn);
~~~

Điều quan trọng là **hai DN phải chỉ cùng cây và đúng phạm vi base mà `ContextSource` cấu hình**.

### Ví dụ đầy đủ: chuyển người dùng từ active sang alumni

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class EmployeeDirectory {
    private final LdapTemplate ldapTemplate;

    public EmployeeDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveToAlumni(String uid) {
        // ContextSource đã có base DN: dc=example,dc=org.
        Name oldRelativeDn = LdapNameBuilder.newInstance()
                .add("ou", "active")
                .add("uid", uid)
                .build();

        Name newRelativeDn = LdapNameBuilder.newInstance()
                .add("ou", "alumni")
                .add("uid", uid)
                .build();

        ldapTemplate.rename(oldRelativeDn, newRelativeDn);
    }
}
~~~

Ở ví dụ này:

1. `oldRelativeDn` tương ứng `uid=<uid>,ou=active` so với base của `ContextSource`.
2. `newRelativeDn` tương ứng `uid=<uid>,ou=alumni`.
3. `LdapNameBuilder` dựng DN theo các RDN, hỗ trợ escape giá trị tên; đừng nối thẳng input người dùng để tạo chuỗi DN.
4. `ldapTemplate.rename(oldRelativeDn, newRelativeDn)` yêu cầu thay đổi tên/vị trí entry, thay vì xóa rồi tạo lại.
5. Bean `LdapTemplate` dùng chung được; từng thao tác do Spring LDAP lấy và giải phóng context phù hợp.

**Code minh họa tập trung vào thao tác LDAP.** Ứng dụng thực cần xác thực quyền nghiệp vụ, chỉ cho chuyển giữa các nhánh được duyệt, xác minh trạng thái hiện có và xử lý các hệ thống tham chiếu DN. Chỉ nên dùng LDAPS hoặc StartTLS với xác thực chứng chỉ hợp lệ khi gửi thông tin đăng nhập hay dữ liệu nhạy cảm.

### Khi nào cần kiểm tra DN sau move?

Có thể đọc lại entry tại DN mới và xác minh DN cũ không còn trỏ đến entry trước đó. Ví dụ thao tác tìm theo DN trong repository:

~~~java
import javax.naming.Name;
import org.springframework.ldap.NameNotFoundException;

// Minh họa trong một phương thức đã có ldapTemplate và newRelativeDn.
boolean destinationExists;
try {
    ldapTemplate.lookup(newRelativeDn);
    destinationExists = true;
} catch (NameNotFoundException e) {
    destinationExists = false;
}
~~~

Cách tra cứu này chỉ xác minh entry có thể được đọc theo quyền hiện tại; nếu không thấy, nguyên nhân còn có thể là ACL hoặc trạng thái đồng bộ. Với nghiệp vụ quan trọng, kiểm tra thêm các attribute định danh ổn định nếu server cung cấp (ví dụ `entryUUID` ở hệ thống hỗ trợ, `objectGUID` ở Active Directory), thay vì chỉ so sánh mỗi DN.

Không giả định có một thuộc tính ID bất biến giống nhau trên mọi loại LDAP server.

## 5. Move bằng JNDI trực tiếp và trách nhiệm tài nguyên

Khi không dùng `LdapTemplate`, JNDI có phương thức:

~~~java
ctx.rename(oldName, newName);
~~~

API này thuộc `Context`/`DirContext` và tùy LDAP provider sẽ ánh xạ sang thao tác đổi tên/di chuyển phù hợp.

Ví dụ:

~~~java
import javax.naming.Name;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.ldap.support.LdapUtils;

public final class JndiMoveExample {
    public static void move(
            ContextSource source, String uid) throws NamingException {

        Name oldDn = LdapNameBuilder.newInstance()
                .add("ou", "active")
                .add("uid", uid)
                .build();

        Name newDn = LdapNameBuilder.newInstance()
                .add("ou", "alumni")
                .add("uid", uid)
                .build();

        DirContext ctx = null;
        try {
            ctx = source.getReadWriteContext();
            ctx.rename(oldDn, newDn);
        } finally {
            LdapUtils.closeContext(ctx);
        }
    }
}
~~~

Do tự lấy `DirContext` từ `ContextSource`, mã này phải **đóng/trả context trong `finally`**. Với `LdapTemplate.rename(...)`, framework quản lý vòng đời context của lời gọi, nên không tự đóng context do framework nắm giữ.

Nếu cần controls hoặc thao tác rất riêng của server, cân nhắc API JNDI phù hợp và kiểm tra hợp đồng về kết nối, LDAP controls, TLS và pooling. Đừng giữ một `DirContext` trong singleton để dùng qua nhiều luồng.

## 6. Chuyển một nhánh đang có entry con

Không chỉ tài khoản lá, một **entry cha** cũng có thể là đối tượng cần move. Ví dụ di chuyển toàn bộ bộ phận:

~~~text
Trước:
dc=example,dc=org
├── ou=departments
│   └── ou=engineering
│       ├── uid=an
│       └── uid=binh
└── ou=archive

Sau:
dc=example,dc=org
├── ou=departments
└── ou=archive
    └── ou=engineering
        ├── uid=an
        └── uid=binh
~~~

Nếu server hỗ trợ thao tác move đối với entry không phải lá, **DN của mọi entry con thay đổi theo DN cha**:

~~~text
Trước:
uid=an,ou=engineering,ou=departments,dc=example,dc=org

Sau:
uid=an,ou=engineering,ou=archive,dc=example,dc=org
~~~

Điều này không có nghĩa Java phải tự đọc và ghi lại mọi entry con. Trong thao tác Modify DN được máy chủ hỗ trợ, thay đổi vị trí của nhánh có thể kéo theo việc đổi đường dẫn DN của các entry con ở phía server. **Hỗ trợ thực tế đối với subtree move, giới hạn kích thước, ACL và thao tác qua partition vẫn phụ thuộc server.** Không khẳng định mọi hệ thống LDAP đều cho phép chuyển nhánh lớn bằng một lệnh rename.

Một số tác động cần kiểm tra sau khi chuyển nhánh:

- Ứng dụng dùng DN người dùng làm khóa tra cứu hoặc principal có thể cần lấy lại DN mới.
- Nhóm sử dụng attribute DN như `member`/`uniqueMember` có thể còn tham chiếu tới tên cũ.
- ACL có thể phụ thuộc vị trí trong cây, nên quyền hiệu lực của entry và con thay đổi.
- Alias, referral, cache, đồng bộ directory và hệ thống tích hợp có thể cần cập nhật.
- Search base cũ không còn chứa nhánh đã move; search base mới phải bao phủ vị trí đích.

Đối với cây lớn, nên tính trước số lượng entry bị ảnh hưởng, thống kê các hệ thống tham chiếu, giới hạn thời gian thực thi và xây dựng phương án rollback/khôi phục phù hợp.

## 7. Không dùng copy + delete để thay thế move một cách tùy tiện

Một cách xử lý nghe có vẻ hợp lý là:

1. Đọc entry tại DN cũ.
2. `bind` lại entry với cùng attribute tại DN mới.
3. `unbind` DN cũ.

Tuy nhiên, đó là **hai hoặc nhiều thao tác độc lập**, có rủi ro và ngữ nghĩa khác với Modify DN:

| Vấn đề | Modify DN (khi server hỗ trợ) | Copy + delete |
|---|---|---|
| Ý nghĩa nghiệp vụ | Đổi tên/vị trí cùng một entry | Tạo entry mới rồi xóa entry cũ |
| Danh tính hệ thống | Có thể giữ các định danh nội bộ theo quy định server | Có thể sinh ID/timestamp mới hoặc mất attribute do server quản lý |
| Thuộc tính không đọc được | Server có thể xử lý bên trong | Copy từ kết quả search có thể thiếu các attribute bị ẩn |
| Lỗi giữa chừng | Một yêu cầu đổi tên theo khả năng server | Có thể còn cả hai entry hoặc mất dữ liệu nếu thứ tự lỗi |
| Entry con | Có thể được di chuyển theo nhánh nếu hỗ trợ | Cần sao chép từng entry đúng thứ tự và xử lý quan hệ |
| ACL, mật khẩu, controls | Phụ thuộc chính sách server | Không thể giả định sao chép nguyên vẹn |

Vì vậy, với **cùng directory server và trong phạm vi hỗ trợ**, ưu tiên Modify DN để chuyển vị trí. Với yêu cầu di chuyển giữa các máy chủ hoặc partition không hỗ trợ rename, hãy xây dựng quy trình migration riêng, có xác minh dữ liệu, quyền, định danh, trạng thái trung gian và khôi phục.

## 8. Tác động lên các tham chiếu DN và xác thực

Một entry được chuyển parent có thể giữ nhiều attribute như cũ, nhưng DN mới sẽ tác động đến hệ thống đang liên kết bằng DN.

### Nhóm có attribute `member`

Giả sử nhóm có dữ liệu:

~~~ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=active,dc=example,dc=org
~~~

Sau khi Linh chuyển sang `ou=alumni`, giá trị `member` có thể vẫn mang **DN cũ**. Một số máy chủ có cơ chế *referential integrity* cập nhật tham chiếu khi rename/move, nhưng đây không phải bảo đảm chung cho mọi LDAP server.

Nếu server không xử lý tự động, ứng dụng cần lập kế hoạch sửa attribute nhóm bằng **Modify**, ví dụ thay giá trị `member` cũ bằng DN mới, đồng thời bảo vệ tính nhất quán nếu một bước thất bại. Không mặc định xóa rồi tạo lại nhóm.

### Bind và quyền ứng dụng

Nếu ứng dụng bind trực tiếp bằng DN người dùng, lần xác thực tiếp theo sẽ cần DN hiện hành. Cần cân nhắc:

- Luồng tìm DN người dùng từ một khóa ổn định trước khi bind.
- Làm mới cache lưu DN, principal hoặc ánh xạ thành viên.
- Tìm hiểu ACL ở nhánh đích có thay đổi quyền đọc/ghi/bind hay không.
- Không dùng DN cũ như định danh bất biến trong token, DB hoặc liên kết mà không có cơ chế cập nhật.

Vị trí DN trong cây cũng có thể ảnh hưởng search base. Ví dụ, nếu chỉ tìm dưới `ou=active`, người dùng đã chuyển tới `ou=alumni` có thể không còn được tìm thấy. Điều này **không chứng minh entry đã bị xóa**.

## 9. Các lỗi LDAP thường gặp khi move

| Mã LDAP | Tên kết quả | Điều cần kiểm tra |
|---|---|---|
| **0** | `success` | Move được chấp nhận; tiếp tục đối soát DN và tham chiếu |
| **32** | `noSuchObject` | DN nguồn/parent đích không tồn tại, hoặc không thấy do chính sách máy chủ |
| **34** | `invalidDNSyntax` | DN cũ, RDN mới hoặc parent DN mới sai cú pháp |
| **50** | `insufficientAccessRights` | Quyền trên entry, parent nguồn/đích hoặc ACL liên quan chưa đủ |
| **53** | `unwillingToPerform` | Server từ chối vì chính sách hoặc giới hạn sản phẩm |
| **64** | `namingViolation` | Vi phạm quy tắc đặt tên/vị trí trong DIT |
| **65** | `objectClassViolation` | Schema không cho phép trạng thái entry hoặc quy tắc áp dụng |
| **68** | `entryAlreadyExists` | DN đích đã bị chiếm |
| **71** | `affectsMultipleDSAs` | Yêu cầu tác động qua ranh giới quản lý nhiều DSA |
| **80** | `other` | Lỗi khác; cần thông điệp chẩn đoán và log phía server |

Mã kết quả và cách Spring LDAP ánh xạ sang exception phụ thuộc provider, phiên bản thư viện và máy chủ. Chẳng hạn thiếu quyền đôi khi được máy chủ che bằng lỗi dạng “không tìm thấy”. **Không dùng việc catch mọi exception rồi thử tạo lại entry ở đích**; thao tác đó có thể tạo bản sao ngoài ý muốn.

### Move thất bại sau timeout: nên làm gì?

Sau một timeout, **không biết chắc yêu cầu Modify DN đã được máy chủ áp dụng hay chưa**. Thay vì retry ngay:

1. Kiểm tra DN nguồn còn tồn tại không.
2. Kiểm tra DN đích có tồn tại không.
3. Nếu cả hai xuất hiện, xác minh định danh entry để phát hiện trùng dữ liệu hoặc một entry khác đang chiếm đích.
4. Nếu chỉ còn đích, có thể move đã thành công; tiếp tục đối soát thuộc tính và tham chiếu.
5. Nếu chỉ còn nguồn, đánh giá lỗi và điều kiện trước khi gửi lại.
6. Nếu không thấy cả hai, kiểm tra ACL, search base, replication delay và nhật ký server; không kết luận entry bị mất ngay.

Trong hệ thống có replication, trạng thái nhìn thấy ở các replica khác nhau có thể chưa đồng bộ tức thời. Nên xác định máy chủ nguồn chính hoặc cơ chế nhất quán phù hợp khi kiểm tra sau sự cố.

## 10. Thiết kế API move an toàn trong ứng dụng

Một API nguy hiểm là:

~~~java
public void move(String oldDn, String newDn) {
    ldapTemplate.rename(
            LdapNameBuilder.newInstance(oldDn).build(),
            LdapNameBuilder.newInstance(newDn).build()
    );
}
~~~

Nếu được gọi trực tiếp từ HTTP mà không giới hạn quyền và vị trí, người dùng có thể yêu cầu move sang một nhánh ngoài nghiệp vụ. Bản thân việc parse DN hợp lệ **không đủ** để cho phép thao tác.

Cách thiết kế an toàn hơn là **cho phép chuyển giữa các nhánh cố định**, chỉ nhận khóa người dùng hợp lệ từ lớp gọi đã được phân quyền:

~~~java
public void archiveEmployee(String uid) {
    // Sau khi service đã kiểm tra quyền và trạng thái nghiệp vụ.
    Name oldDn = LdapNameBuilder.newInstance()
            .add("ou", "active")
            .add("uid", uid)
            .build();

    Name newDn = LdapNameBuilder.newInstance()
            .add("ou", "alumni")
            .add("uid", uid)
            .build();

    ldapTemplate.rename(oldDn, newDn);
}
~~~

Ví dụ thứ hai thu hẹp phạm vi thao tác theo thiết kế API. Khi đưa vào production, bổ sung xác thực quyền nghiệp vụ, kiểm tra entry/parent, chính sách trạng thái, audit, xử lý race condition và kiểm soát dữ liệu liên quan.

Nếu phải nhận parent động, hãy parse từng DN bằng API DN chuyên dụng như `LdapName`, xác định đúng quan hệ tổ tiên theo RDN, và so với **allowlist branch** rõ ràng. Kiểm tra hậu tố bằng chuỗi đơn thuần có thể bỏ sót escape hoặc nhầm biểu diễn tương đương của DN.

### Checklist trước và sau khi di chuyển

| Thời điểm | Việc cần xác minh |
|---|---|
| **Trước** | DN nguồn và parent đích tồn tại; định danh mục tiêu đúng; DN mới chưa có entry; schema và ACL phù hợp |
| **Trước** | Move nằm trong phạm vi được phép; đã xác định tác động của thay DN đến nhóm, cache, tài khoản dịch vụ và replica |
| **Trong** | Kết nối có TLS đúng cấu hình; không log mật khẩu; theo dõi kết quả theo từng yêu cầu |
| **Sau** | DN mới truy cập được; DN cũ không còn ở vị trí ban đầu; định danh/attribute cốt lõi vẫn đúng |
| **Sau** | Tham chiếu nhóm và các hệ thống liên quan được xử lý; audit ghi DN cũ, DN mới và kết quả ở mức dữ liệu phù hợp |

Không đưa mật khẩu, thông tin bind hoặc attribute nhạy cảm vào log. DN cũng có thể chứa thông tin cá nhân nên phải tuân theo chính sách log/retention của ứng dụng.

## 11. Kiểm thử move với Spring LDAP

Đối với bài học này, kiểm thử tích hợp trên LDAP server cô lập sẽ phản ánh chính xác khả năng move và ACL hơn một mock chỉ xác minh rằng phương thức `rename(...)` được gọi.

Các kịch bản nên có:

1. **Move entry lá thành công**: tạo hai parent và một entry người dùng, move từ `ou=active` sang `ou=alumni`, xác minh DN cũ không còn và DN mới có entry tương ứng.
2. **Giữ RDN**: so sánh `uid` và các attribute cơ bản trước/sau, đảm bảo không vô tình đổi mã định danh khi chỉ đổi parent.
3. **Đích đã tồn tại**: tạo entry ở DN đích trước, xác minh thao tác bị từ chối và entry ban đầu vẫn nguyên vẹn.
4. **Parent mới không tồn tại**: xác nhận lỗi và ứng dụng không tự tạo parent bất ngờ.
5. **Thiếu quyền**: thử với tài khoản chỉ có quyền đọc hoặc thiếu quyền di chuyển giữa nhánh.
6. **Move nhánh có con**: trên server hỗ trợ, xác minh toàn bộ DN con đổi đúng và dữ liệu liên quan không bị mất.
7. **Vượt naming context**: kiểm tra hành vi cụ thể của sản phẩm; không giả định move qua hai partition thành công.
8. **Input RDN có ký tự đặc biệt**: ví dụ UID chứa dấu phẩy hoặc ký tự cần escape theo chính sách đặt tên; xác minh API dựng DN tạo tên hợp lệ khi schema cho phép.
9. **Timeout/retry**: giả lập mất kết nối sau khi gửi lệnh; xác minh code kiểm tra lại trạng thái thay vì tự động copy hoặc delete.
10. **Tham chiếu và search base**: kiểm tra bộ phận tìm kiếm, nhóm và cache dùng DN sau khi move.

### Bài tập thực hành

Cho cây ban đầu:

~~~text
dc=example,dc=org
├── ou=employees
│   ├── uid=mai
│   └── uid=nam
└── ou=former
~~~

Yêu cầu:

1. Viết DN cũ và DN mới nếu chuyển `uid=mai` sang `ou=former` nhưng vẫn giữ UID.
2. Xác định `entry`, `newrdn` và `newSuperior` tương ứng của Modify DN.
3. Viết ví dụ Java gọi `LdapTemplate.rename(...)` với DN tương đối.
4. Nếu nhóm có `member: uid=mai,ou=employees,dc=example,dc=org`, ứng dụng cần kiểm tra điều gì sau khi move?
5. Nếu có sẵn `uid=mai,ou=former,dc=example,dc=org`, lỗi nào có thể xảy ra?
6. Vì sao không nên thay bằng thao tác bind mới rồi unbind cũ?

**Gợi ý lời giải:**

- DN cũ: `uid=mai,ou=employees,dc=example,dc=org`. DN mới: `uid=mai,ou=former,dc=example,dc=org`.
- `entry` là DN cũ; `newrdn` vẫn là `uid=mai`; `newSuperior` là `ou=former,dc=example,dc=org`.
- Trong Spring LDAP có base `dc=example,dc=org`:

~~~java
Name oldDn = LdapNameBuilder.newInstance()
        .add("ou", "employees")
        .add("uid", "mai")
        .build();

Name newDn = LdapNameBuilder.newInstance()
        .add("ou", "former")
        .add("uid", "mai")
        .build();

ldapTemplate.rename(oldDn, newDn);
~~~

- Kiểm tra `member` có được máy chủ tự cập nhật sang DN mới không; nếu không, thiết kế thao tác Modify trên nhóm.
- DN đích đã bị chiếm có thể gây `entryAlreadyExists (68)`.
- Copy + delete có thể làm thay đổi danh tính hệ thống, mất thuộc tính đặc biệt và tạo trạng thái dở dang khi một bước thất bại.

## 12. Câu hỏi tự kiểm tra

**1. Chuyển một entry sang parent DN mới có bắt buộc phải đổi `uid` không?**

Không. Nếu RDN vẫn là `uid=linh` thì chỉ parent DN thay đổi; DN đầy đủ mới khác DN cũ.

**2. `newSuperior` thuộc về schema attribute của entry hay thuộc về thao tác Modify DN?**

Thuộc về yêu cầu Modify DN. Nó chỉ parent mới; không phải attribute mặc định của entry.

**3. Có thể dùng `LdapTemplate.unbind(...)` rồi `bind(...)` để giả lập move một cách tương đương không?**

Không nên coi là tương đương. Đây là những thao tác tạo/xóa riêng biệt, có rủi ro khác về danh tính, thuộc tính do server quản lý và lỗi giữa chừng.

**4. Di chuyển entry cha có con có chắc chắn được hỗ trợ ở mọi máy chủ LDAP không?**

Không. Hành vi với subtree, partition, ACL và naming context phụ thuộc server. Nếu được hỗ trợ, DN của các entry con thay đổi theo DN parent.

**5. Move thành công có tự cập nhật mọi attribute `member` trên toàn directory không?**

Không có bảo đảm chung. Phải xác minh cơ chế referential integrity thực tế.

**6. Vì sao ứng dụng cần quan tâm đến cache DN sau khi move?**

Vì DN mới được dùng để tra cứu, bind hoặc tham chiếu; cache giữ DN cũ có thể dẫn đến tìm sai vị trí, lỗi đăng nhập hoặc liên kết không còn hiệu lực.

## Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): cấu trúc Modify DN, `newrdn`, `deleteoldrdn` và `newSuperior`.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DN, DIT, entry và các mô hình dữ liệu.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp và escape của DN.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate` và các thao tác ghi dữ liệu thư mục.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): tham khảo chữ ký `rename(...)` theo phiên bản sử dụng.
- [Java SE JNDI Context](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/Context.html): API `rename(...)` cho thao tác JNDI.

## Ghi nhớ

**Move entry sang parent DN khác là thao tác thay đổi DN**, thường thực hiện qua LDAP Modify DN: **`entry`** là DN cũ, **`newrdn`** là tên tương đối ở vị trí mới, còn **`newSuperior`** chỉ parent DN đích. Trong Spring LDAP, có thể gọi `LdapTemplate.rename(oldDn, newDn)` với các DN tương đối đúng base `ContextSource`. Phải đảm bảo parent đích tồn tại, DN mới chưa bị chiếm, schema và ACL cho phép, phạm vi move được server hỗ trợ. Sau khi move, **kiểm tra DN con, nhóm có tham chiếu DN, cache, quyền và luồng xác thực** để toàn bộ ứng dụng tiếp tục hoạt động chính xác.
