# Rename entry và thay đổi DN

Khi một nhân viên đổi mã đăng nhập, chuyển đơn vị hoặc một nhóm được đổi tên, ứng dụng có thể cần thay đổi **Distinguished Name (DN)** của một entry trong LDAP. Trong **Spring LDAP**, `LdapTemplate.rename(...)` cung cấp thao tác này, nhưng kết quả không chỉ là “đổi tên hiển thị”: DN là **vị trí của entry trong Directory Information Tree (DIT)**. Đổi DN có thể ảnh hưởng các entry con, quyền truy cập, dữ liệu liên kết bằng DN và hệ thống đang lưu DN như một định danh.

Bài thuộc chương **LdapTemplate** của mô-đun **SPRING_LDAP**. Nội dung tập trung vào cách rename/move entry bằng `LdapTemplate`, cách dựng tên qua `LdapNameBuilder`, ý nghĩa thao tác LDAP **Modify DN**, xử lý lỗi và kiểm thử với thư mục thực tế. Những nguyên tắc này vẫn hữu ích khi dùng `LdapClient` hoặc Object-Directory Mapping (ODM), vì đều dựa trên DN, schema, filter, `ContextSource` và quyền của server.

**Kết quả học tập:**

- Phân biệt đổi **RDN** với chuyển entry sang **parent DN** khác.
- Giải thích bốn trường `entry`, `newrdn`, `deleteoldrdn` và `newSuperior` của LDAP Modify DN theo RFC 4511.
- Dùng `LdapTemplate.rename(Name, Name)` và `rename(String, String)` với DN tương đối đúng `ContextSource.base`.
- Dựng DN chứa ký tự đặc biệt an toàn thay vì nối chuỗi từ input.
- Dự đoán ảnh hưởng của rename đến naming attribute, entry con, nhóm có `member`, ứng dụng lưu DN và thuộc tính `entryUUID`.
- Nhận diện các lỗi `NameNotFoundException`, `NameAlreadyBoundException`, thiếu quyền, vi phạm schema và thao tác không được server hỗ trợ.
- Lập quy trình kiểm thử, ghi nhận trạng thái và xử lý khi mạng đứt giữa thao tác.

## 1. DN, RDN và vị trí của entry

Giả sử cây thư mục:

```text
dc=example,dc=org
├── ou=People
│   ├── uid=an
│   └── uid=binh
├── ou=Alumni
└── ou=Groups
    └── cn=Engineering
```

Một entry người dùng có DN đầy đủ:

```text
uid=an,ou=People,dc=example,dc=org
│      │         └───────── naming context/suffix
│      └─────────────────── parent (ou=People,...)
└────────────────────────── RDN của entry (uid=an)
```

- **DN** xác định đường đi đến entry trong DIT.
- **RDN** (Relative Distinguished Name) xác định entry tương đối với parent trực tiếp.
- **Parent DN** là DN sau khi bỏ RDN ở bên trái.
- **Naming attribute** là attribute dùng trong RDN, chẳng hạn `uid` hoặc `cn`.

Ví dụ thay đổi `uid=an` thành `uid=an.nguyen` có thể làm DN đổi từ:

```text
uid=an,ou=People,dc=example,dc=org
```

sang:

```text
uid=an.nguyen,ou=People,dc=example,dc=org
```

Trong khi đó, chuyển An sang `ou=Alumni` nhưng giữ nguyên RDN làm DN trở thành:

```text
uid=an,ou=Alumni,dc=example,dc=org
```

**Đổi attribute `cn` hay `displayName` không mặc nhiên làm DN đổi.** Nếu entry mang RDN `uid=an`, việc sửa `cn: An Nguyen` thành `cn: An Tran` chỉ thay dữ liệu; DN vẫn là `uid=an,ou=People,...`. Ngược lại, muốn đổi `uid=an` thành `uid=an.nguyen` ở vị trí RDN, nên sử dụng Modify DN/`rename` thay vì chỉ sửa giá trị `uid` một cách tùy tiện.

## 2. Ba kiểu thay đổi DN phổ biến

| Tình huống | DN trước | DN sau | Thay đổi |
| --- | --- | --- | --- |
| **Đổi RDN** | `uid=an,ou=People,...` | `uid=an.nguyen,ou=People,...` | Đổi RDN, parent giữ nguyên |
| **Chuyển entry** | `uid=an,ou=People,...` | `uid=an,ou=Alumni,...` | RDN giữ nguyên, parent đổi |
| **Đổi RDN và chuyển** | `uid=an,ou=People,...` | `uid=an.nguyen,ou=Alumni,...` | RDN và parent đều đổi |

Ký hiệu `...` trong bảng đại diện suffix `dc=example,dc=org`.

Cả ba đều có thể được biểu diễn bằng thao tác **LDAP Modify DN**. Phương thức `LdapTemplate.rename(...)` nhận **DN cũ** và **DN mới**; khi server hỗ trợ, nó có thể thực hiện đổi RDN, chuyển sang parent khác hoặc kết hợp.

### 2.1. Khi nào cần rename/move?

Các tình huống thực tế:

- Đổi mã tài khoản trong RDN khi có quyết định nghiệp vụ phù hợp.
- Chuyển entry từ `ou=Pending` sang `ou=Active` sau khi kích hoạt.
- Chuyển entry từ `ou=People` sang `ou=Alumni` khi thay đổi trạng thái.
- Đổi tên nhóm `cn=DevTeam` thành `cn=Engineering`.
- Đổi tên một OU hoặc nhánh chứa các entry con, **nếu LDAP server hỗ trợ Modify DN trên entry không phải leaf**.

Không phải mọi thay đổi nghiệp vụ đều nên di chuyển entry. Ví dụ phòng ban thay đổi thường có thể biểu diễn bằng attribute `departmentNumber`, trong khi DN vẫn giữ ổn định. Thiết kế DIT càng gắn chặt với dữ liệu biến động, việc rename/move càng dễ kéo theo nhiều tham chiếu cần cập nhật.

## 3. LDAP Modify DN theo RFC 4511

**RFC 4511, mục 4.9** định nghĩa request:

```text
ModifyDNRequest ::= [APPLICATION 12] SEQUENCE {
    entry           LDAPDN,
    newrdn          RelativeLDAPDN,
    deleteoldrdn    BOOLEAN,
    newSuperior     [0] LDAPDN OPTIONAL
}
```

Ý nghĩa từng trường:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `entry` | DN **hiện tại** của entry cần đổi | `uid=an,ou=People,dc=example,dc=org` |
| `newrdn` | RDN **mới**; bắt buộc có, kể cả khi chỉ chuyển parent | `uid=an.nguyen` |
| `deleteoldrdn` | Có xóa giá trị attribute dùng trong RDN cũ không? | `TRUE` |
| `newSuperior` | DN **parent mới**, tùy chọn; bỏ qua nếu giữ nguyên parent | `ou=Alumni,dc=example,dc=org` |

Một request có `newSuperior` vẫn phải chỉ định `newrdn`. Nếu chỉ chuyển entry sang parent mới, giá trị `newrdn` thường **giống RDN cũ**.

### 3.1. Đổi RDN có ảnh hưởng đến attribute không?

Giả sử entry trước khi đổi:

```ldif
dn: uid=an,ou=People,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Nguyen
sn: Nguyen
mail: an@example.org
```

Thực hiện Modify DN sang `uid=an.nguyen,ou=People,dc=example,dc=org` với `deleteoldrdn = TRUE`. Theo RFC 4511, server bổ sung giá trị của RDN mới nếu cần và loại bỏ giá trị RDN cũ **không còn thuộc RDN mới**, miễn kết quả phù hợp schema.

Kết quả thường là:

```ldif
dn: uid=an.nguyen,ou=People,dc=example,dc=org
uid: an.nguyen
cn: An Nguyen
sn: Nguyen
mail: an@example.org
```

Đoạn LDIF này lược bớt `objectClass` để tập trung vào phần thay đổi. `cn`, `sn` và `mail` không tự động đổi vì RDN `uid` thay đổi.

### 3.2. `deleteoldrdn = TRUE` và `FALSE`

| Cấu hình | Với `uid=an` đổi thành `uid=an.nguyen` |
| --- | --- |
| `deleteoldrdn = TRUE` | Bỏ giá trị `uid: an` cũ nếu không còn trong RDN mới; bảo đảm `uid: an.nguyen` tồn tại |
| `deleteoldrdn = FALSE` | Giữ `uid: an` và bổ sung `uid: an.nguyen` nếu cần, khi schema cho phép |

**Đừng hiểu `deleteoldrdn` là xóa entry cũ rồi tạo entry mới.** Đây là cờ điều khiển **giá trị naming attribute** trong cùng thao tác Modify DN, không phải thao tác xóa một entry.

Nếu attribute RDN bị giới hạn `SINGLE-VALUE` hoặc có quy tắc schema đặc biệt, giữ cả giá trị cũ và mới có thể vi phạm schema. Kết quả phụ thuộc chính sách của server và sự hợp lệ của entry sau thay đổi.

### 3.3. Parent mới phải tồn tại

Muốn chuyển sang `ou=Alumni,dc=example,dc=org` thì entry parent `ou=Alumni,...` phải tồn tại. Nếu chưa có parent hoặc tài khoản bind không có quyền trên parent mới, server có thể từ chối Modify DN.

**Không mặc định có thể chuyển entry qua mọi naming context hoặc sang server khác.** RFC 4511 yêu cầu client không kỳ vọng được di chuyển tùy ý qua nhiều server/naming context; LDAP server có thể từ chối thao tác có phạm vi vượt khả năng của nó.

## 4. `LdapTemplate.rename(...)` của Spring LDAP

Theo API `LdapTemplate`, có hai overload thông dụng:

```java
void rename(javax.naming.Name oldDn, javax.naming.Name newDn);
void rename(String oldDn, String newDn);
```

**`oldDn` và `newDn` mô tả vị trí tương đối với base mà `ContextSource` cấu hình** trong các thao tác Spring LDAP thông thường. Ví dụ:

```java
contextSource.setBase("dc=example,dc=org");
```

Khi đó:

| Tham số truyền vào template | DN đầy đủ tương ứng |
| --- | --- |
| `uid=an,ou=People` | `uid=an,ou=People,dc=example,dc=org` |
| `uid=an.nguyen,ou=People` | `uid=an.nguyen,ou=People,dc=example,dc=org` |
| `uid=an,ou=Alumni` | `uid=an,ou=Alumni,dc=example,dc=org` |

Không đưa suffix `dc=example,dc=org` thêm lần nữa nếu template đang hoạt động tương đối với base đó. Nếu cần di chuyển **ra ngoài** base đã cấu hình, hãy xem lại thiết kế `ContextSource` và khả năng server; không coi `rename` là API di chuyển không giới hạn.

### 4.1. Đổi RDN: `uid=an` thành `uid=an.nguyen`

Ví dụ một service sử dụng `LdapTemplate`:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class UserDnService {
    private final LdapTemplate ldapTemplate;

    public UserDnService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private static Name userDn(String organizationalUnit, String uid) {
        return LdapNameBuilder.newInstance()
            .add("ou", organizationalUnit)
            .add("uid", uid)
            .build();
    }

    public void renameUser(String oldUid, String newUid) {
        Name oldDn = userDn("People", oldUid);
        Name newDn = userDn("People", newUid);
        ldapTemplate.rename(oldDn, newDn);
    }

    public void moveUserToAlumni(String uid) {
        Name oldDn = userDn("People", uid);
        Name newDn = userDn("Alumni", uid);
        ldapTemplate.rename(oldDn, newDn);
    }

    public void renameAndMove(String oldUid, String newUid) {
        Name oldDn = userDn("People", oldUid);
        Name newDn = userDn("Alumni", newUid);
        ldapTemplate.rename(oldDn, newDn);
    }
}
```

Với `ContextSource.base = dc=example,dc=org`:

- `renameUser("an", "an.nguyen")` đổi RDN trong cùng `ou=People`.
- `moveUserToAlumni("an")` đổi parent từ People sang Alumni, giữ RDN.
- `renameAndMove("an", "an.nguyen")` đổi đồng thời RDN và parent nếu server cho phép.

**Phương thức `rename` trả về `void`.** Lời gọi hoàn tất mà không ném exception nghĩa là thao tác đã được API báo thành công theo kết quả nhận được, nhưng khi cần cập nhật cache/index nghiệp vụ, ứng dụng vẫn nên xác minh trạng thái và thực hiện các bước đồng bộ tham chiếu thích hợp.

### 4.2. Tại sao nên truyền `Name`?

`LdapNameBuilder` nhận riêng **loại thuộc tính** và **giá trị**, giúp xử lý escaping theo cú pháp DN. Ví dụ người dùng có tên:

```text
Doe, Jane
```

Nếu RDN là `cn` thì DN dạng chuỗi phải biểu diễn dấu phẩy trong giá trị là `\,`:

```text
cn=Doe\, Jane,ou=People,dc=example,dc=org
```

Tạo `Name`:

```java
Name oldDn = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("cn", "Doe, Jane")
    .build();

Name newDn = LdapNameBuilder.newInstance()
    .add("ou", "Alumni")
    .add("cn", "Doe, Jane")
    .build();

ldapTemplate.rename(oldDn, newDn);
```

**Không tự ghép:** `"cn=" + commonName + ",ou=People"`. Giá trị có dấu phẩy, dấu cộng, dấu bằng hoặc dấu gạch chéo ngược có thể làm DN sai. Cũng không escape trước rồi lại đưa giá trị đã escape vào `add(attribute, value)` vì dễ tạo *double escaping*.

DN escaping theo RFC 4514 **khác** LDAP filter escaping theo RFC 4515. `rename` cần DN đích hợp lệ; nếu cần tìm entry trước khi rename, filter tìm kiếm phải được dựng riêng bằng query/filter builder.

### 4.3. String overload phù hợp khi nào?

Nếu cả DN cũ và mới đã là **chuỗi DN hợp lệ** từ nguồn được kiểm soát, có thể dùng:

```java
ldapTemplate.rename(
    "uid=an,ou=People",
    "uid=an.nguyen,ou=People"
);
```

Với giá trị từ người dùng cuối, nên xây từng RDN từ dữ liệu gốc bằng `LdapNameBuilder` và whitelist loại attribute/OU được phép. Không nhận một **DN đích tùy ý** từ request bên ngoài rồi chuyển entry theo nó, vì người dùng có thể yêu cầu di chuyển entry sang vùng không nằm trong nghiệp vụ dự kiến.

## 5. Giữ hay xóa giá trị RDN cũ trong Spring LDAP?

Overload `LdapTemplate.rename(oldDn, newDn)` không nhận trực tiếp tham số Boolean `deleteoldrdn`. Khi template làm việc qua **JNDI LDAP provider của JDK**, hành vi xóa/giữ RDN cũ được điều khiển bằng environment property:

```text
java.naming.ldap.deleteRDN
```

Theo tài liệu Oracle JNDI:

- `"true"`: xóa giá trị của RDN cũ khi thích hợp; đây là **mặc định** của provider.
- `"false"`: giữ lại giá trị RDN cũ như một giá trị attribute, nếu hợp schema.

Có thể thiết lập property khi cấu hình `LdapContextSource`:

```java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://ldap.example.org:636");
source.setBase("dc=example,dc=org");
source.setUserDn("cn=app-writer,ou=ServiceAccounts,dc=example,dc=org");
source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));

// Chỉ dùng khi nghiệp vụ cần giữ RDN cũ và schema cho phép.
source.setBaseEnvironmentProperties(
    Map.of("java.naming.ldap.deleteRDN", "false")
);
```

Ví dụ chỉ cho thấy phần liên quan; bean do Spring quản lý cần được khởi tạo đầy đủ và kết nối TLS phải xác minh chứng chỉ. **Hãy đặt cấu hình có chủ đích**, vì nếu tắt xóa RDN cũ cho toàn `ContextSource`, tất cả thao tác rename qua context đó có thể giữ các giá trị naming attribute cũ.

Giữ giá trị cũ **không** tạo alias DN tự động. Sau đổi `uid=an` sang `uid=an.nguyen`, DN cũ `uid=an,ou=People,...` **không còn là vị trí để lookup entry**, dù attribute `uid` có thể vẫn chứa `an`. Lookup DN cũ và tìm kiếm filter `(uid=an)` là hai thao tác có ý nghĩa khác nhau.

## 6. Thực hiện Modify DN bằng LDIF để đối chiếu

Nếu cần hiểu chính xác server nhận gì, có thể dùng `ldapmodify` cùng LDIF thay đổi tên. Đối chiếu với Spring LDAP giúp chẩn đoán khi `rename` không hoạt động như mong đợi.

### 6.1. Đổi RDN tại chỗ

```ldif
dn: uid=an,ou=People,dc=example,dc=org
changetype: modrdn
newrdn: uid=an.nguyen
deleteoldrdn: 1
```

Nội dung trên yêu cầu chuyển:

```text
uid=an,ou=People,dc=example,dc=org
    → uid=an.nguyen,ou=People,dc=example,dc=org
```

Dòng `deleteoldrdn: 1` yêu cầu bỏ giá trị RDN cũ khi thích hợp; không phải lệnh xóa toàn entry.

### 6.2. Chuyển sang parent khác

Giả sử bước trên đã đổi RDN thành `uid=an.nguyen`. Để chuyển entry sang Alumni:

```ldif
dn: uid=an.nguyen,ou=People,dc=example,dc=org
changetype: modrdn
newrdn: uid=an.nguyen
deleteoldrdn: 1
newsuperior: ou=Alumni,dc=example,dc=org
```

`newrdn` vẫn bắt buộc, dù giá trị RDN không đổi. `newsuperior` chỉ rõ parent mới.

Bạn có thể dùng công cụ dòng lệnh trong môi trường thử nghiệm:

```bash
ldapmodify -x -H "ldaps://ldap.example.org:636" \
  -D "cn=app-writer,ou=ServiceAccounts,dc=example,dc=org" -W \
  -f rename-entry.ldif
```

Trong ví dụ, `rename-entry.ldif` là tệp LDIF **do người thực hành chuẩn bị** chứa một trong hai đoạn trên. Tránh dùng trên dữ liệu production nếu chưa đánh giá ACL, replication và liên kết DN.

### 6.3. Rename không phải `modifyAttributes`

| Thao tác | Ý nghĩa | Ảnh hưởng DN |
| --- | --- | --- |
| `ldapTemplate.rename(oldDn, newDn)` | Yêu cầu đổi tên/di chuyển entry theo LDAP Modify DN | **Có** |
| `ldapTemplate.modifyAttributes(...)` | Sửa giá trị attribute theo LDAP Modify | Không tự đổi DN |
| `ldapTemplate.bind(...)` | Tạo entry mới tại một DN | Tạo DN cho entry mới |
| `ldapTemplate.unbind(...)` | Xóa entry | Entry không còn |
| `ldapTemplate.rebind(...)` | Thay thế entry tại DN theo semantics JNDI | Không phải API rename được khuyến nghị |

**Không giả lập rename bằng xóa entry cũ rồi thêm entry mới** khi server hỗ trợ Modify DN. Cách copy–delete dễ mất metadata/quan hệ, gây khoảng trống dữ liệu, và có thể thất bại giữa hai bước. Modify DN là một thao tác giao thức riêng, dù mọi hệ quả bên ngoài của nó không nhất thiết được cập nhật nguyên tử.

## 7. Đổi DN ảnh hưởng đến entry con như thế nào?

Nếu entry cần rename **có các entry con**, việc đổi DN của nút cha làm **đường đi DN của cả cây con** thay đổi khi server hỗ trợ thao tác đó.

Ví dụ:

```text
Trước:
ou=Engineering,ou=People,dc=example,dc=org
├── uid=an,ou=Engineering,ou=People,dc=example,dc=org
└── uid=binh,ou=Engineering,ou=People,dc=example,dc=org

Sau khi đổi ou=Engineering thành ou=Development:
ou=Development,ou=People,dc=example,dc=org
├── uid=an,ou=Development,ou=People,dc=example,dc=org
└── uid=binh,ou=Development,ou=People,dc=example,dc=org
```

DN của An và Bình thay đổi theo nút cha; các giá trị attribute như `uid` hoặc `mail` không nhất thiết thay đổi.

**Giới hạn thực tế:** một số LDAP server chỉ hỗ trợ Modify DN trên leaf entry hoặc giới hạn chuyển cây con. Một số server từ chối thao tác khi có nhiều entry con, khi vượt phạm vi cơ sở dữ liệu, khi parent mới không phù hợp schema hoặc khi bind account thiếu quyền. Không giả định vì RFC mô tả Modify DN với subtree mà mọi server đều cho phép rename toàn bộ OU tùy ý.

Đối với nhánh lớn, cần tính toán thời gian, replication, hiệu ứng với ACL và tham chiếu ứng dụng. Thử trên **bản sao dữ liệu hoặc môi trường staging** trước khi đổi DN nhánh chứa nhiều người dùng.

## 8. Quan hệ tham chiếu DN sau khi rename

DN có thể xuất hiện như **giá trị của các attribute khác**. Chẳng hạn entry nhóm:

```ldif
dn: cn=Engineering,ou=Groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: Engineering
member: uid=an,ou=People,dc=example,dc=org
member: uid=binh,ou=People,dc=example,dc=org
```

Giả sử An đổi thành `uid=an.nguyen,ou=People,dc=example,dc=org`.

**Rename entry An không nhất thiết tự động cập nhật giá trị `member` của nhóm.** Các server khác nhau có thể cung cấp cơ chế referential integrity, overlay/plugin hoặc logic nghiệp vụ để tự điều chỉnh. Nếu không có cơ chế đó, `member` có thể vẫn trỏ tới DN cũ.

Các nơi cần kiểm tra:

| Nơi lưu tham chiếu | Ví dụ | Rủi ro |
| --- | --- | --- |
| Attribute nhóm | `member`, `uniqueMember` | Membership chứa DN không còn tồn tại |
| Quan hệ quản lý | `manager` | Người quản lý được tham chiếu bằng DN cũ |
| Thuộc tính DN tùy biến | `ownerDn` theo schema tổ chức | Liên kết nghiệp vụ bị đứt |
| Cache ứng dụng | Khóa map là DN | Cache trả bản ghi cũ hoặc miss |
| Hệ thống bên ngoài | DB lưu `ldapDn` | Không lookup được theo DN cũ |
| ACL chứa DN | Quy tắc ACL/schema hoặc chính sách server | Quyền có thể thay đổi ngoài ý muốn |
| Quy trình sync | Bản ghi mapping source–target theo DN | Dễ coi entry được rename là delete + add |

**DN là tên phân biệt theo vị trí, không nhất thiết là khóa định danh bất biến.** Nếu server hỗ trợ `entryUUID` theo RFC 4530, giá trị này có thể giúp theo dõi một entry khi DN thay đổi; tuy nhiên cần hiểu hành vi của server, quá trình import/export và cách đồng bộ giữa môi trường trước khi sử dụng làm khóa xuyên hệ thống.

### 8.1. Kiểm tra nhóm trước và sau rename

Ví dụ, trước thao tác, tìm các nhóm chứa DN cũ:

```text
(&(objectClass=groupOfNames)
  (member=uid=an,ou=People,dc=example,dc=org))
```

Sau rename, xác nhận các tham chiếu đã được cập nhật đúng:

```text
(&(objectClass=groupOfNames)
  (member=uid=an.nguyen,ou=People,dc=example,dc=org))
```

Sử dụng query builder để escape **giá trị filter** chứa DN, đặc biệt khi RDN có dấu phẩy hoặc ký tự đặc biệt. Không tự ghép filter từ DN do người dùng cung cấp.

### 8.2. Một giao dịch nghiệp vụ có nhiều bước

Ví dụ nghiệp vụ đổi `uid` và cập nhật `member` của 10 nhóm:

```text
1. Xác minh entry đích, parent và quyền
2. Ghi nhận các nhóm đang tham chiếu DN cũ
3. Thực hiện Modify DN (rename entry)
4. Cập nhật các attribute member liên quan (nếu server không tự xử lý)
5. Xác nhận lookup theo DN mới và toàn bộ liên kết cần thiết
6. Đồng bộ cache, search index và hệ thống bên ngoài
```

Modify DN **là một thao tác LDAP riêng**. Các thay đổi tham chiếu ở bước 4, cache ở bước 6 thường **không nằm trong một transaction nguyên tử xuyên hệ thống**. Nếu một bước thất bại, ứng dụng cần kế hoạch khôi phục hoặc đối soát; rollback không đơn giản là gọi rename ngược trong mọi tình huống vì có thể xuất hiện thay đổi đồng thời.

## 9. Xác minh trước và sau thao tác

Một quy trình an toàn nên thực hiện những bước kiểm tra có chủ đích.

### 9.1. Trước rename

1. Xác định đúng entry bằng DN cũ; ghi nhận attribute cần thiết và định danh ổn định nếu có.
2. Xác minh DN đích **không bị chiếm** theo chính sách ứng dụng, nhưng vẫn chuẩn bị xử lý xung đột nếu có race condition.
3. Xác minh parent đích tồn tại, thuộc OU được phép và tài khoản bind có quyền thay đổi.
4. Xác minh schema cho naming attribute và các thuộc tính sau rename.
5. Tìm các giá trị attribute tham chiếu DN cũ (ví dụ `member`) và lập kế hoạch cập nhật.
6. Nếu rename cả subtree, kiểm tra khả năng server, quy mô dữ liệu và ảnh hưởng đến replication/ACL.

### 9.2. Sau rename

- Lookup theo **DN mới** và xác nhận entry/attribute cần thiết.
- Lookup theo DN cũ nên không còn chỉ tới entry cũ, trừ khi có cơ chế đặc thù như alias hoặc state khác; không dựa vào riêng kiểm tra này làm bằng chứng toàn diện.
- Đọc lại `uid` hoặc `cn` dùng trong RDN để kiểm tra `deleteoldrdn`.
- Kiểm tra entry con nếu đổi tên nhánh.
- Kiểm tra tham chiếu DN của nhóm và ứng dụng liên quan.
- Ghi audit sự kiện đổi DN với old/new DN được xử lý theo chính sách bảo mật.

### 9.3. Mẫu kiểm tra bằng Spring LDAP

Đoạn code dưới đây minh họa tra cứu entry sau rename:

```java
import javax.naming.Name;
import javax.naming.directory.Attribute;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public String lookupUid(LdapTemplate ldapTemplate, String uid) {
    Name dn = LdapNameBuilder.newInstance()
        .add("ou", "People")
        .add("uid", uid)
        .build();

    return ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attributes -> {
            Attribute value = attributes.get("uid");
            return value == null ? null : String.valueOf(value.get());
        }
    );
}
```

Đây là **kiểm tra dữ liệu quan sát được**. Nếu một replica chưa nhận replication hoặc ACL che attribute, kết quả có thể khác trên các endpoint. Khi cần xác nhận ngay sau rename, chọn endpoint/đường đọc phù hợp với yêu cầu nhất quán.

## 10. Lỗi phổ biến khi rename entry

`LdapTemplate` chuyển nhiều lỗi JNDI thành exception runtime tương ứng trong `org.springframework.ldap`.

| Triệu chứng | Loại lỗi thường gặp | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| DN cũ không tồn tại | `NameNotFoundException` | Sai DN, sai base, entry đã di chuyển, ACL |
| Parent đích chưa tồn tại | `NameNotFoundException` hoặc result code server liên quan | `newSuperior` không tồn tại |
| DN đích đã bị sử dụng | `NameAlreadyBoundException` hoặc lỗi tương ứng từ provider | Xung đột RDN dưới cùng parent |
| DN mới có cú pháp sai | `InvalidNameException` | Chưa escape RDN, nối chuỗi sai |
| Không đủ quyền đổi DN | `NoPermissionException` | Quyền trên entry, parent cũ và parent mới |
| Naming attribute vi phạm schema | `SchemaViolationException` hoặc `InvalidAttributeValueException` | RDN, attribute type, `SINGLE-VALUE`/syntax |
| Server không cho move hoặc rename subtree | `OperationNotSupportedException` hoặc result code khác | Hạn chế của server, non-leaf, khác naming context |
| Kết nối mất trong thao tác | `CommunicationException` | TCP/TLS, server failover, trạng thái chưa chắc chắn |
| Parent đích khiến cây không hợp lệ | Lỗi schema hoặc naming violation | Quy tắc DIT và parent/child của server |

**Không coi mọi thất bại là “DN không tìm thấy”.** Lỗi network, quyền hoặc server không hỗ trợ có cách xử lý khác lỗi dữ liệu đầu vào.

### 10.1. Xử lý xung đột bằng exception cụ thể

Ví dụ:

```java
import javax.naming.Name;
import org.springframework.ldap.NameAlreadyBoundException;
import org.springframework.ldap.NameNotFoundException;
import org.springframework.ldap.NoPermissionException;
import org.springframework.ldap.core.LdapTemplate;

public void renameChecked(
        LdapTemplate ldapTemplate, Name oldDn, Name newDn) {
    try {
        ldapTemplate.rename(oldDn, newDn);
    } catch (NameNotFoundException ex) {
        throw new IllegalArgumentException(
            "Source entry or destination parent is missing", ex);
    } catch (NameAlreadyBoundException ex) {
        throw new IllegalStateException(
            "Destination DN is already occupied", ex);
    } catch (NoPermissionException ex) {
        throw new IllegalStateException(
            "LDAP bind identity cannot rename this entry", ex);
    }
}
```

Đây là minh họa cách phân loại exception, **chưa phải chính sách lỗi HTTP hoàn chỉnh**. Trong ứng dụng thực tế, có thể chuyển thành lỗi nghiệp vụ riêng và ánh xạ response trong controller; không đưa nguyên DN/stack trace hoặc credential ra giao diện công khai.

### 10.2. Lỗi mất kết nối sau khi server có thể đã đổi tên

Giả sử:

```text
Client gửi Modify DN sang server A
Server A thực hiện rename thành công
Mạng ngắt trước khi client nhận ModifyDNResponse
Client nhận CommunicationException
```

Client **không biết chắc** rename đã thực hiện hay chưa. Việc retry ngay trên A hoặc B có thể gặp `NameNotFoundException` ở DN cũ, hoặc replica B chưa có trạng thái mới.

Phải đối chiếu theo DN cũ, DN mới và một định danh ổn định nếu có; xem độ trễ replication và các thay đổi đồng thời. Không tự động retry thao tác ghi vô hạn. Với hệ thống lớn, cần kế hoạch reconcile khi trạng thái chưa xác định.

## 11. ODM và đối tượng Java sau khi đổi DN

Nếu ứng dụng dùng Spring LDAP ODM, một entity có thể mang `@Entry`, `@Id` và `@DnAttribute`. Những annotation này giúp ánh xạ entry sang đối tượng Java, nhưng **không có nghĩa thay đổi một field Java rồi gọi update luôn tạo ra một Modify DN giống `LdapTemplate.rename`**.

Trong một số phiên bản/API, `LdapOperations.update(Object entry)` có thể xử lý DN đã thay đổi theo cách riêng (tài liệu API mô tả đường đi dựa trên unbind/bind cho một số tình huống). Vì vậy, nếu mục đích là **di chuyển/đổi tên entry theo thao tác LDAP Modify DN**, nên dùng API `rename` rõ ràng hoặc xác minh chính xác cách ODM xử lý DN trong phiên bản đang sử dụng.

Sau rename, **đối tượng Java đã load trước đó có thể còn DN cũ** trong trường `@Id`. Hãy làm mới đối tượng, cache hoặc cập nhật trạng thái ứng dụng theo contract, thay vì tiếp tục dùng DN cũ để sửa/xóa.

Các nguyên tắc chung vẫn giữ nguyên: tên phải escape đúng, base phải đúng, server phải cho phép thao tác và tham chiếu DN cần được xử lý theo thiết kế hệ thống.

## 12. Bảo mật và quản trị thay đổi DN

Rename là thao tác **ghi** có khả năng ảnh hưởng rộng, nhất là khi di chuyển người dùng giữa các OU có ACL khác nhau hoặc đổi tên một subtree.

Một số nguyên tắc:

- **Least privilege:** chỉ tài khoản/role được cấp phép mới được rename ở các vùng DIT cần thiết.
- **Validate mục tiêu:** ứng dụng giới hạn các parent DN đích hợp lệ theo nghiệp vụ; không cho request tùy ý chọn `ou=Admins` hay naming context khác.
- **Sử dụng TLS:** LDAPS hoặc StartTLS có kiểm tra chứng chỉ cho các kết nối bind/ghi.
- **Kiểm tra schema trước thay đổi:** RDN mới phải tương thích attribute type/objectClass.
- **Ghi audit:** ai yêu cầu, entry nào, DN cũ/mới, kết quả, correlation ID; tránh ghi credential và dữ liệu nhạy cảm không cần thiết.
- **Kiểm soát replication:** nếu nhiều LDAP server, xác minh thay đổi lan truyền theo yêu cầu và không dùng replica cũ để khẳng định rename thất bại.
- **Tách thao tác dịch vụ:** API đổi tên/di chuyển nên khác API cập nhật profile bình thường để giảm thay đổi DN ngoài ý muốn.

Đổi DN thường không phải thao tác có thể hoàn tác đơn giản nếu quy trình đã cập nhật nhiều hệ thống, thay đổi ACL hoặc các entry liên quan. Trước thay đổi lớn, cần kế hoạch rollback/reconciliation tương ứng.

## 13. Kiểm thử rename thực tế

Các unit test có thể xác minh service dựng đúng `Name` và gọi `ldapTemplate.rename(oldDn, newDn)`. **Integration test** trên server có schema và chính sách gần production mới xác nhận được hành vi đổi RDN, move subtree, ACL và tham chiếu DN.

| Kịch bản | Chuẩn bị | Xác minh |
| --- | --- | --- |
| Đổi RDN trong cùng OU | Tạo entry `uid=test-an` dưới People | DN mới lookup được; DN cũ không còn |
| Chuyển entry sang OU khác | Tạo People/Alumni; entry test dưới People | Parent mới đúng; RDN giữ nguyên |
| Đổi RDN và chuyển | Entry thử nghiệm độc lập | DN đích có cả RDN và parent mong muốn |
| Giữ RDN cũ | Provider/test có `deleteRDN=false`; schema cho phép đa trị | Attribute chứa cả giá trị cũ và mới |
| Xóa RDN cũ | `deleteRDN=true` | Giá trị RDN cũ bị loại nếu không còn cần trong RDN mới |
| DN đích đã tồn tại | Chuẩn bị hai entry có RDN tương ứng | Xung đột được bắt đúng |
| Parent đích không có | Chọn OU chưa tạo | Lỗi phù hợp; entry cũ vẫn có theo kết quả server |
| Thiếu quyền | Bind account chỉ có read | Rename bị từ chối, không làm mất dữ liệu |
| Ký tự đặc biệt trong RDN | Dữ liệu `Doe, Jane` hoặc `Ops+Dev` | `LdapNameBuilder` tạo DN hợp lệ |
| Move non-leaf | Tạo OU thử nghiệm chứa các con | Xác nhận server hỗ trợ và DN hậu duệ đúng |
| Tham chiếu nhóm | Group `member` trỏ DN cũ | Kiểm tra cập nhật tự động hoặc quy trình sửa tham chiếu |
| Mất kết nối giữa rename | Môi trường mô phỏng lỗi được phép | Xác định trạng thái và không retry mù quáng |
| Replication chậm | Đọc trên hai server sau rename | Không nhầm dữ liệu cũ với thao tác thất bại |

**Không chạy các ca làm mất kết nối, di chuyển OU lớn hoặc sửa ACL trên production** ngoài quy trình quản trị được phê duyệt. Với thư mục nhúng phục vụ unit test, nhớ rằng nó có thể không mô phỏng đầy đủ Active Directory/OpenLDAP thực tế.

### 13.1. Kiểm thử DN tương đối trong Java

Ví dụ một đoạn kiểm tra thuần Java/Spring LDAP naming API:

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

// ContextSource.base = dc=example,dc=org
Name oldDn = LdapNameBuilder.newInstance()
    .add("ou", "People")
    .add("uid", "an")
    .build();

Name newDn = LdapNameBuilder.newInstance()
    .add("ou", "Alumni")
    .add("uid", "an.nguyen")
    .build();

// Có thể kiểm tra đối tượng Name trước khi gọi rename.
assert "uid=an,ou=People".equals(oldDn.toString());
assert "uid=an.nguyen,ou=Alumni".equals(newDn.toString());
```

Các assertion này chỉ chứng minh **đường dẫn đã dựng đúng**, không thay thế integration test kiểm tra server đã thực hiện Modify DN.

## 14. Bài tập tình huống

Giả sử `ContextSource.base = dc=example,dc=org`; server có `ou=People`, `ou=Alumni` và `ou=Groups`; tài khoản bind có quyền rename trong vùng thử nghiệm.

**Bài 1.** Entry `uid=an,ou=People,dc=example,dc=org` đổi RDN thành `uid=an.nguyen`. Hãy viết DN đầy đủ mới. Trường `newSuperior` có bắt buộc trong LDAP Modify DN không?

**Bài 2.** Muốn chuyển entry `uid=binh` từ `ou=People` sang `ou=Alumni` mà không đổi RDN, hãy nêu `newrdn` và `newSuperior`.

**Bài 3.** `LdapTemplate.rename(...)` được gọi với base cấu hình ở trên. DN cũ/mới nên truyền là chuỗi nào cho bài 1?

**Bài 4.** Nếu `deleteoldrdn = FALSE` khi đổi `uid=an` thành `uid=an.nguyen`, điều gì có thể xảy ra với attribute `uid`? DN `uid=an,ou=People,...` còn dùng để lookup entry như trước không?

**Bài 5.** Một nhóm có `member: uid=an,ou=People,dc=example,dc=org`. Sau khi đổi DN của An, liệu tham chiếu này chắc chắn tự sửa không? Nêu cách kiểm tra.

**Bài 6.** Một OU có 2.000 entry con được rename. DN của các entry con có thể bị ảnh hưởng ra sao? Có nên mặc định mọi LDAP server đều hỗ trợ thao tác không?

**Bài 7.** Truyền giá trị `cn = "Doe, Jane"` từ request. Vì sao không nên viết `"cn=" + value + ",ou=People"`? API nào giúp dựng DN?

**Bài 8.** Client nhận `CommunicationException` trong lúc đổi DN. Có thể khẳng định rename chưa thành công không? Hướng xử lý nào đúng hơn retry ngay?

### Đáp án gợi ý

1. DN mới: `uid=an.nguyen,ou=People,dc=example,dc=org`. `newSuperior` không bắt buộc khi parent giữ nguyên.
2. `newrdn = uid=binh`; `newSuperior = ou=Alumni,dc=example,dc=org`.
3. Dùng `"uid=an,ou=People"` và `"uid=an.nguyen,ou=People"` hoặc hai đối tượng `Name` tương đương.
4. `uid` có thể giữ cả `an` và `an.nguyen` nếu schema cho phép. DN cũ không tự trở thành alias cho DN mới; lookup theo DN cũ thường không còn truy cập entry đó.
5. **Không chắc.** Phụ thuộc referential integrity của server. Tìm theo DN cũ/mới trong `member`, kiểm tra cơ chế cập nhật và sửa tham chiếu nếu cần.
6. DN của toàn bộ hậu duệ đổi theo OU cha khi server hỗ trợ Modify DN trên non-leaf. Nhiều server có giới hạn; phải thử trong staging và đánh giá tác động.
7. Dấu phẩy thuộc giá trị RDN cần escape. Dùng `LdapNameBuilder.newInstance().add("ou", "People").add("cn", value).build()`.
8. **Không.** Server có thể đã đổi DN và phản hồi bị mất. Cần đối chiếu trạng thái DN cũ, DN mới, định danh ổn định và độ trễ replication trước quyết định tiếp theo.

## 15. Ghi nhớ

- **Đổi DN = LDAP Modify DN**, có thể đổi RDN, parent hoặc cả hai; `LdapTemplate.rename(oldDn, newDn)` cung cấp thao tác này.
- **`newrdn` luôn bắt buộc**, `newSuperior` tùy chọn, `deleteoldrdn` quyết định giữ hoặc bỏ giá trị naming attribute cũ.
- Trong Spring LDAP, DN thao tác thường **tương đối với `ContextSource.base`**. Dùng `LdapNameBuilder` để escape giá trị RDN an toàn.
- Đổi DN của nút cha có thể thay đổi DN hậu duệ, nhưng khả năng rename/move non-leaf **phụ thuộc server**.
- Rename **không tự bảo đảm cập nhật tất cả attribute tham chiếu DN**, cache hoặc cơ sở dữ liệu ngoài LDAP. Cần kế hoạch đối soát.
- **Lỗi mạng trong thao tác ghi có thể để lại trạng thái không chắc chắn**. Không retry mù quáng và không xem một hành vi trên replica chậm là bằng chứng thao tác đã thất bại.
- Xác minh quyền, schema, parent đích, liên kết và kết quả sau rename bằng integration test phù hợp.

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol, mục 4.9 Modify DN](https://www.rfc-editor.org/rfc/rfc4511.html#section-4.9): định nghĩa `entry`, `newrdn`, `deleteoldrdn`, `newSuperior` và giới hạn move.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): DIT, DN, entry, schema và naming.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): cú pháp và escaping DN/RDN.
- [RFC 4530 — LDAP: entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530.html): định danh entry khi server hỗ trợ.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): overload `rename(Name, Name)` và `rename(String, String)`.
- [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html): dựng DN an toàn.
- [Oracle JNDI — More LDAP Operations](https://docs.oracle.com/javase/tutorial/jndi/ldap/rename.html): `Context.rename(...)` và `java.naming.ldap.deleteRDN`.
