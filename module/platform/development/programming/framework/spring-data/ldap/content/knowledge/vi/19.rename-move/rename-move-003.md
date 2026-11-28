# Điều kiện máy chủ cho phép di chuyển trong hoặc ngoài một nhánh

Trong **Spring Data LDAP**, mỗi entry được định danh bởi **Distinguished Name (DN)** và nằm tại một vị trí cụ thể trong **Directory Information Tree (DIT)**. Khi người dùng chuyển phòng ban, một nhóm được chuyển sang OU khác hoặc cấu trúc thư mục được sắp xếp lại, ứng dụng có thể cần **đổi tên hoặc di chuyển entry**. LDAP có thao tác **Modify DN** cho mục đích này; trong Spring LDAP, thao tác thường được gọi qua `LdapTemplate.rename(oldDn, newDn)`.

Tuy nhiên, một DN đích đúng cú pháp chưa đủ để server đồng ý di chuyển. Kết quả phụ thuộc vào **ranh giới naming context**, server quản lý hai nhánh, quyền của tài khoản, schema/naming rule, sự tồn tại của parent đích và việc server hỗ trợ di chuyển cả subtree. Đây cũng là lý do cùng một lời gọi `rename` có thể thành công giữa hai OU nhưng thất bại khi chuyển sang suffix hoặc LDAP server khác.

Bài học này giúp bạn:

- Phân biệt **đổi RDN**, **chuyển parent trong một naming context**, **chuyển qua naming context khác** và **chuyển qua DSA/server khác**.
- Hiểu điều kiện của LDAP **Modify DN** theo RFC 4511 và tác động của `newSuperior`.
- Kiểm tra parent, DN đích, schema, ACL, subtree và năng lực của máy chủ trước khi di chuyển.
- Dùng `LdapTemplate.rename` với DN tương đối đúng base trong một ứng dụng Spring Data LDAP.
- Thiết kế kiểm chứng và cách xử lý an toàn khi server từ chối hoặc client mất phản hồi.

## 1. Thế nào là một nhánh trong DIT?

Giả sử một LDAP server phục vụ naming context `dc=example,dc=org`:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=staff
│   └── uid=mai
├── ou=contractors
└── ou=groups
    └── cn=backend
```

Ở hình này:

- Entry Lan có **DN** `uid=lan,ou=people,dc=example,dc=org`.
- **RDN** của Lan là `uid=lan`.
- **Parent DN** của Lan là `ou=people,dc=example,dc=org`.
- `ou=people` và `ou=staff` là hai **nhánh** khác nhau trong cùng naming context `dc=example,dc=org`.

Về mặt phân cấp, chuyển Lan từ `ou=people` sang `ou=staff` thay đổi **parent DN**. Chỉ sửa một LDAP attribute `ou` của Lan (nếu entry có attribute đó) **không** di chuyển Lan trong DIT. Muốn thay vị trí tên, cần **Modify DN** hoặc quy trình di chuyển do directory hỗ trợ.

### Ba khái niệm không được đánh đồng

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Nhánh/OU** | `ou=people,dc=example,dc=org` | Một subtree logic trong DIT |
| **Naming context (suffix)** | `dc=example,dc=org` | Gốc của vùng tên mà một DSA công bố hoặc quản lý |
| **DSA (Directory System Agent)** | Một dịch vụ LDAP phục vụ một hoặc nhiều naming context | Máy chủ/đơn vị xử lý các thao tác LDAP cho phần dữ liệu nó quản lý |

Một naming context có thể chứa nhiều OU. Một server có thể công bố **nhiều** naming context; hai địa chỉ LDAP khác nhau có thể trỏ đến hai server hoặc đến cùng một cụm dịch vụ. **Cùng endpoint** không tự chứng minh mọi nhánh đều có thể di chuyển qua nhau; tương tự, hai OU nằm cùng domain component DN không tự bảo đảm cùng backend/DSA thực thi Modify DN.

## 2. Bốn tình huống đổi tên và di chuyển

### 2.1. Đổi RDN, giữ nguyên parent

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan.nguyen,ou=people,dc=example,dc=org
```

Đây là **rename** ở cùng parent: chỉ RDN đổi từ `uid=lan` thành `uid=lan.nguyen`. Server phải cho phép thay đổi tên, RDN mới không trùng với entry khác dưới `ou=people` và entry sau đổi tên vẫn hợp lệ theo schema/naming rule.

### 2.2. Chuyển sang nhánh khác trong cùng naming context

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=staff,dc=example,dc=org
```

Đây là **move**: RDN `uid=lan` giữ nguyên, parent đổi từ `ou=people` sang `ou=staff`. Trong LDAP Modify DN, thay đổi parent được biểu diễn qua **`newSuperior`**. Với các server hỗ trợ và có quyền phù hợp, đây là trường hợp chuyển nhánh thông thường.

**Lưu ý:** mặc dù hai nhánh cùng suffix `dc=example,dc=org`, server vẫn có thể từ chối vì ACL, cấu trúc tên, loại entry hoặc giới hạn di chuyển subtree.

### 2.3. Chuyển sang naming context khác trên cùng endpoint

```text
Trước: uid=lan,ou=people,dc=example,dc=org
Sau:   uid=lan,ou=people,dc=archive,dc=org
```

Hai DN thuộc hai **naming context** khác nhau. Ngay cả khi một server LDAP công bố cả `dc=example,dc=org` và `dc=archive,dc=org`, **không có bảo đảm** nó cho phép một Modify DN di chuyển entry giữa hai vùng tên đó. Hai suffix có thể thuộc các backend khác nhau, chính sách lưu trữ khác nhau hoặc ranh giới quản lý khác nhau.

Để biết có di chuyển được không, phải xác minh khả năng và giới hạn **cụ thể của directory server/phiên bản/cấu hình**. Nếu server không cho phép, ứng dụng cần một quy trình chuyển dữ liệu được thiết kế riêng, không thể giải quyết bằng cách nối DN đích rồi gọi `rename` một cách mù quáng.

### 2.4. Chuyển sang DSA hoặc LDAP server khác

```text
LDAP server A                         LDAP server B
dc=example,dc=org                     dc=partner,dc=org
└── ou=people                          └── ou=people
    └── uid=lan  --(muốn chuyển)-->       └── uid=lan
```

**Modify DN chuẩn là một LDAP operation gửi tới một server**, không phải lệnh giao dịch phân tán tự động chuyển entry giữa hai server. RFC 4511 có result code **`affectsMultipleDSAs (71)`** khi một thao tác ảnh hưởng nhiều DSA mà server không thể thực hiện. Hệ thống cũng có thể trả referral hoặc lỗi khác tùy cấu hình.

Nếu đích do DSA khác quản lý, một phương án thường là **di chuyển dữ liệu theo quy trình kiểm soát**: đọc thuộc tính có thể chuyển, tạo entry ở đích theo schema đích, xác minh, cập nhật tham chiếu và chỉ xử lý entry nguồn khi đã đạt điều kiện nghiệp vụ. Cách làm này **không mặc nhiên nguyên tử** và có thể yêu cầu công cụ quản trị hoặc API riêng của nhà cung cấp.

## 3. Modify DN theo RFC 4511 hoạt động thế nào?

LDAP **ModifyDNRequest** có bốn thành phần quan trọng:

| Trường giao thức | Mục đích | Ví dụ |
| --- | --- | --- |
| `entry` | DN hiện tại cần đổi | `uid=lan,ou=people,dc=example,dc=org` |
| `newrdn` | RDN mới của entry | `uid=lan` hoặc `uid=lan.nguyen` |
| `deleteoldrdn` | Có xóa các giá trị thuộc tính thuộc RDN cũ khi không còn cần cho RDN mới không | `TRUE` / `FALSE` |
| `newSuperior` | DN của **parent đích**, chỉ có khi cần chuyển parent | `ou=staff,dc=example,dc=org` |

Ví dụ **chuyển nhánh và giữ RDN**:

```text
entry        = uid=lan,ou=people,dc=example,dc=org
newrdn       = uid=lan
newSuperior  = ou=staff,dc=example,dc=org
deleteoldrdn = true
```

Ví dụ **đổi RDN trong cùng nhánh**:

```text
entry        = uid=lan,ou=people,dc=example,dc=org
newrdn       = uid=lan.nguyen
newSuperior  = (không gửi; parent giữ nguyên)
deleteoldrdn = true
```

Khi `deleteoldrdn=true`, server cố loại những **giá trị thuộc tính của RDN cũ** không còn cần cho tên mới. Khi `false`, giá trị cũ thường được giữ như giá trị attribute thông thường. Ví dụ, sau rename từ `uid=lan` sang `uid=lan.nguyen` với `false`, `uid` có thể mang cả hai giá trị nếu schema cho phép. Không nên suy ra flag này chỉ là tùy chọn hình thức: nó ảnh hưởng dữ liệu trên entry.

Theo RFC 4511, một Modify DN thành công trên entry có con cũng làm thay đổi DN của **các hậu duệ** tương ứng. Tuy nhiên, server cụ thể có thể **không hỗ trợ một số kiểu đổi tên/di chuyển**, đặc biệt với subtree, ranh giới backend hoặc naming context; vì vậy điều kiện về khả năng của server phải được kiểm tra trước.

### Tách Modify DN khỏi Modify thông thường

| Nhu cầu | Thao tác phù hợp |
| --- | --- |
| Đổi `mail`, `description` hoặc thuộc tính `telephoneNumber` | LDAP **Modify** |
| Đổi `uid` được dùng làm RDN | **Modify DN**, và cân nhắc ảnh hưởng attribute RDN |
| Chuyển entry từ `ou=people` sang `ou=staff` | **Modify DN** với parent mới |
| Tạo entry mới tại DN chưa tồn tại | LDAP **Add** |
| Xóa entry nguồn sau khi di chuyển dữ liệu riêng biệt | LDAP **Delete** trong quy trình đã kiểm soát |

Việc dùng `LdapTemplate.modifyAttributes` để sửa một field `ou` trên entry không thể tự thay đổi parent DN của entry đó.

## 4. Điều kiện 1: Server thực sự quản lý nguồn và đích

Để một Modify DN chạy thành công, server nhận yêu cầu phải có khả năng xử lý **DN nguồn** và **parent đích** trong vùng tên mà nó quản lý, đồng thời hỗ trợ kiểu di chuyển đó.

### 4.1. Xác định naming context của hai DN

**Root DSE** là entry đặc biệt tại DN rỗng `""`. Nhiều directory công bố thuộc tính `namingContexts` để cho biết các suffix mà server phục vụ:

```text
dn: (empty)
namingContexts: dc=example,dc=org
namingContexts: dc=archive,dc=org
```

Có thể dùng công cụ kiểm tra LDAP để đọc Root DSE, ví dụ trong môi trường thử nghiệm cho phép truy cập anonymous:

```bash
ldapsearch -x \
  -H "ldaps://directory.example.org:636" \
  -b "" -s base "(objectClass=*)" namingContexts
```

Nếu server không cho anonymous đọc thông tin này, cần bind bằng tài khoản phù hợp qua kênh bảo mật và theo quy định hệ thống. **Một kết nối `LdapContextSource` có base DN riêng không nhất thiết đọc được Root DSE bằng cách lookup DN rỗng tương đối**, vì DN rỗng khi đó có thể trỏ tới chính base của context. Hãy dùng truy vấn Root DSE với context gốc hoặc công cụ quản trị đúng cách.

**Có cả hai naming context trong kết quả không có nghĩa chuyển giữa chúng được.** Đây chỉ là dấu hiệu server công bố hai vùng tên; khả năng Modify DN xuyên suffix cần kiểm tra tài liệu/khả năng thực tế của directory.

### 4.2. Ranh giới backend, referral và DSA

Một số deployment phân chia directory qua nhiều backend, partition, referral hoặc DSA. Khi chuyển entry:

- Server có thể nhận ra DN đích nhưng **không được phép** chuyển dữ liệu giữa hai backend.
- Server có thể trả **`referral`** để chỉ client tới server khác; referral **không tự thực hiện** một transaction di chuyển giữa hai server.
- Server có thể trả `affectsMultipleDSAs (71)`, `unwillingToPerform (53)` hoặc lỗi phù hợp khác khi việc di chuyển vượt khả năng quản lý.
- Chế độ replication và chính sách đa master của server có thể hạn chế hoặc ảnh hưởng thời điểm những DN mới được quan sát ở các replica.

Vì vậy, câu “hai nhánh nằm trên cùng một host” **chưa đủ** để quyết định có thể `rename` hay không. Phải kiểm tra **phạm vi server quản lý**, **tính năng hỗ trợ** và **cấu hình của backend**.

## 5. Điều kiện 2: DN nguồn, parent đích và vị trí trong cây hợp lệ

### 5.1. Entry nguồn phải tồn tại và đúng DN

LDAP có thể có cùng RDN `uid=lan` ở nhiều nhánh:

```text
uid=lan,ou=people,dc=example,dc=org
uid=lan,ou=contractors,dc=example,dc=org
```

Vì vậy, truy vấn theo `(uid=lan)` **không thay thế** việc xác định chính xác DN nguồn. Trước khi move, xác minh DN đã chọn thực sự là entry mong muốn, nhất là với ứng dụng có nhiều OU hoặc nhiều naming context.

### 5.2. Parent đích phải tồn tại

Chuyển từ `ou=people` sang `ou=staff` đòi hỏi `ou=staff,dc=example,dc=org` tồn tại và cho phép entry con phù hợp. Nếu parent đích không tồn tại, server có thể trả `noSuchObject (32)`.

**Modify DN không tự tạo nhánh cha.** Không thể yêu cầu chuyển Lan tới `ou=new-department,dc=example,dc=org` khi OU đích chưa tồn tại mà kỳ vọng server tạo OU đó hộ.

### 5.3. DN đích phải không va chạm

Nếu `uid=lan,ou=staff,dc=example,dc=org` đã tồn tại, chuyển một entry khác đến đúng DN này thường trả `entryAlreadyExists (68)`. RDN chỉ cần duy nhất **trong cùng parent**, vì thế `uid=lan` tại `ou=people` và `uid=lan` tại `ou=staff` có thể cùng tồn tại trước khi di chuyển.

Không được “giải quyết” xung đột bằng cách xóa entry đích mà không kiểm tra chủ thể dữ liệu và quyền sở hữu; cần quyết định rõ đây là hai đối tượng khác nhau, hợp nhất hay đổi tên theo chính sách nghiệp vụ.

### 5.4. Không tạo chu kỳ cây

Không thể chuyển một entry **vào chính subtree của nó**, bởi kết quả sẽ tạo quan hệ cha–con vòng lặp.

```text
ou=engineering,dc=example,dc=org
└── ou=teams
    └── cn=backend

Sai: chuyển ou=engineering xuống dưới cn=backend
     vì backend vốn là hậu duệ của engineering.
```

Đích không được là chính entry nguồn hoặc hậu duệ của nguồn nếu phép chuyển gây chu kỳ; server có thể trả lỗi như `loopDetect (54)` hoặc lỗi theo triển khai.

## 6. Điều kiện 3: Schema, RDN và cấu trúc DIT phải cho phép

LDAP schema không chỉ quyết định attribute nào được phép xuất hiện mà có thể ràng buộc **tên** và **loại entry** ở vị trí đích. Ví dụ:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
```

Một phép rename hoặc move có thể bị từ chối vì:

- RDN mới dùng attribute không phù hợp naming rule của server.
- Thay `uid=lan` bằng `cn=...` nhưng entry sau đổi tên không đáp ứng schema hoặc giới hạn đặt tên.
- Parent đích chỉ cho phép những loại entry con nhất định theo **name form**, **DIT structure rule** hoặc cấu hình riêng.
- Các attribute RDN sau khi áp dụng `deleteoldrdn` vi phạm thuộc tính bắt buộc/đơn trị hoặc ràng buộc của schema.
- Chính sách nghiệp vụ hay overlay/server plugin không cho phép di chuyển một số entry hệ thống hoặc nhánh được bảo vệ.

Không phải mọi LDAP server đều sử dụng hoặc thực thi cùng một tập DIT structure rules; cần xem schema và cấu hình **server cụ thể**. Một phép di chuyển hợp lệ về cú pháp **không đồng nghĩa** hợp lệ về schema.

| Điều cần kiểm tra | Câu hỏi cụ thể |
| --- | --- |
| `objectClass` | Entity `inetOrgPerson` có được đặt dưới parent đích không? |
| RDN | Có được dùng `uid=...` để đặt tên tại nhánh đích không? |
| Thuộc tính MUST | Sau rename có còn đầy đủ các giá trị bắt buộc không? |
| Định danh ổn định | Có hệ thống ngoài đang lưu DN cũ làm khóa tham chiếu không? |
| Giới hạn parent | Có naming rule hoặc policy riêng cho OU đích không? |

## 7. Điều kiện 4: Quyền thao tác ở cả nơi đi và nơi đến

LDAP server kiểm soát Modify DN bằng **ACL và chính sách riêng**. Tài khoản có quyền đọc source không mặc nhiên được phép move; thậm chí tài khoản sửa attribute `mail` cũng chưa chắc có quyền đổi tên entry.

Với thao tác chuyển parent, server thường cần bảo đảm principal có **quyền thích hợp trên entry/parent nguồn và parent đích**. Một số directory biểu diễn quyền này thành quyền xóa tên cũ và thêm tên mới; một số directory có quyền riêng cho **rename**, **move**, **write DN** hoặc các thuộc tính RDN. Không thể suy ra một công thức ACL chung áp dụng cho mọi server.

Ví dụ, một service account được phép:

```text
READ  ou=people,dc=example,dc=org
WRITE mail của user dưới ou=people
READ  ou=staff,dc=example,dc=org
```

Tài khoản đó **có thể vẫn bị từ chối** khi gọi `rename` để chuyển user sang `ou=staff`, vì chưa có quyền di chuyển/ghi danh sách con ở đích.

Trước khi cấp thêm quyền, xác định nghiệp vụ thực sự cần move hay chỉ cần sửa thuộc tính `department`. Cấp quyền tối thiểu trên các nhánh được phép, kiểm thử riêng tài khoản ứng dụng và tài khoản quản trị, đồng thời sử dụng **LDAPS hoặc StartTLS với kiểm tra chứng chỉ hợp lệ**.

## 8. Điều kiện 5: Server hỗ trợ di chuyển entry có con

### 8.1. Di chuyển một entry lá

Một người dùng `uid=lan` thường là **entry lá**, không có hậu duệ. Chuyển entry này giữa các OU thường đơn giản hơn, miễn các điều kiện DN/schema/quyền/server khác đều đạt.

### 8.2. Di chuyển một subtree

Giả sử:

```text
dc=example,dc=org
└── ou=engineering
    ├── ou=platform
    │   └── uid=an
    └── ou=qa
        └── uid=mai
```

Muốn chuyển `ou=engineering` xuống dưới `ou=departments`:

```text
Trước:
  uid=an,ou=platform,ou=engineering,dc=example,dc=org

Sau:
  uid=an,ou=platform,ou=engineering,ou=departments,dc=example,dc=org
```

Một Modify DN thành công trên gốc subtree sẽ khiến **DN của mọi hậu duệ đổi theo đường tên mới**. Tuy nhiên:

- Directory server có thể **giới hạn** thao tác move với entry không phải lá, di chuyển across partition hoặc số lượng hậu duệ.
- Quyền với source/subtree và đích có thể phức tạp hơn move một entry lá.
- Ứng dụng/cache đang nắm DN của từng entry con phải nhận diện DN mới.
- Những tham chiếu DN ở **bên ngoài** subtree không mặc nhiên được cập nhật.
- Thời điểm replica khác quan sát DN mới phụ thuộc cách directory đồng bộ.

Đừng chuyển một nhánh lớn trực tiếp trên production chỉ vì thao tác với entry lá đã thành công. Cần thử với subtree có độ sâu, kích thước và kiểu entry tương đương, theo dõi giới hạn server và thiết kế cách phục hồi.

## 9. Spring LDAP: di chuyển giữa hai OU cùng naming context

### 9.1. Thiết lập ví dụ

Giả sử ứng dụng cấu hình `LdapContextSource` với:

```text
LDAP URL : ldaps://directory.example.org:636
Base DN  : dc=example,dc=org
Bind DN  : uid=service-writer,ou=services,dc=example,dc=org
```

Hai OU `ou=people` và `ou=staff` đã tồn tại dưới base DN đó; service account có quyền di chuyển phù hợp. Bạn muốn chuyển entry Lan từ `people` sang `staff` nhưng giữ `uid=lan`.

### 9.2. Dùng `LdapTemplate.rename`

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public class DirectoryMoveService {
    private final LdapTemplate ldapTemplate;

    public DirectoryMoveService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveLanToStaff() {
        // Cả hai DN đều tương đối với base dc=example,dc=org.
        Name source = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "lan")
                .build();

        Name target = LdapNameBuilder.newInstance("ou=staff")
                .add("uid", "lan")
                .build();

        ldapTemplate.rename(source, target);
    }
}
```

Đây là một lời gọi dễ đọc, thể hiện ý định **Modify DN** trên directory. Với API JNDI/Spring LDAP, việc đổi DN có thể được chuyển thành Modify DN, nhưng **tên đích, phạm vi base, quyền và khả năng của server vẫn quyết định kết quả**.

`LdapNameBuilder` giúp escape RDN đúng theo cú pháp DN khi `uid` chứa ký tự đặc biệt. Không tạo DN bằng cách nối `"uid=" + input + ",ou=people"`, và không dùng quy tắc escape **LDAP filter** thay cho quy tắc escape **DN**.

### 9.3. Đổi RDN cùng một OU

```java
Name source = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Name target = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan.nguyen")
        .build();

ldapTemplate.rename(source, target);
```

Trong tình huống này, parent không đổi. Sau rename, cần kiểm tra attribute `uid` và chính sách giữ/xóa RDN cũ; `LdapTemplate.rename(Name, Name)` không trình bày `deleteoldrdn` như một tham số trực tiếp. Nếu nghiệp vụ phụ thuộc chặt vào giá trị này, cần xác minh cách JNDI provider và server xử lý hoặc sử dụng API phù hợp có kiểm soát.

### 9.4. Vì sao không đưa DN khác naming context vào ví dụ trên?

Với `ContextSource` đã có base `dc=example,dc=org`, các DN trong lời gọi được hiểu tương đối với base. Một DN thuộc `dc=archive,dc=org` **không** thể chỉ được thay vào `target` như một nhánh con bình thường của base `dc=example,dc=org`.

Nếu hệ thống cần thao tác across naming context, phải xem lại cách tạo context và DN, rồi **xác minh server hỗ trợ chuyển qua vùng tên đó**. Cấu hình đúng DN trong Java là điều kiện cần; nó không làm server tự có khả năng move giữa hai DSA.

## 10. Spring Data LDAP ODM và hệ quả với repository

Giả sử entity được ánh xạ như sau:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class Person {
    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    private String uid;

    @Attribute(name = "cn")
    private String fullName;

    @Attribute(name = "sn")
    private String surname;

    public Person() {}
    // Các getter/setter theo quy ước entity của ứng dụng.
}
```

Ở đây `@Id Name dn` biểu diễn **DN của entry**, còn `@DnAttribute` mô tả giá trị RDN dùng để xác định danh tính/vị trí. Với `@Entry(base = "ou=people")`, entity được thiết kế cho nhánh `people`. Nếu Lan được chuyển sang `staff`, ứng dụng phải xem lại **nơi repository tìm entry và cách ánh xạ entity**, chứ không thể chỉ đổi DN ở server rồi mong mọi repository được cố định trong `people` vẫn tìm thấy Lan.

Trong Spring LDAP ODM, một đường cập nhật entity có thể dựng lại DN từ `@DnAttribute`. Tùy phiên bản/API, khi DN đổi, thao tác update ODM có thể thực hiện **xóa entry cũ và tạo entry mới** thay vì một Modify DN tường minh. Vì thế:

- Nếu nghiệp vụ là đổi tên/di chuyển, **dùng `LdapTemplate.rename` một cách rõ ràng** khi server cho phép Modify DN.
- Sau khi di chuyển, đọc lại entry theo DN mới, cập nhật `@Id Name dn` của object đang giữ và kiểm tra repository/base phù hợp.
- Không coi `repository.save(person)` sau khi sửa một field DN là bảo đảm một phép chuyển nhánh nguyên tử.
- Đối với entity có nhiều OU có thể thay đổi theo nghiệp vụ, cân nhắc thiết kế mapping/search base sao cho không bị bó vào một OU cũ.

Các thuộc tính `objectClass` và schema của entry không tự đổi chỉ vì DN đã đổi. Nếu parent đích yêu cầu loại entry khác, phải thiết kế chuyển đổi dữ liệu và kiểm tra schema cụ thể, không dùng Modify DN như cách bỏ qua ràng buộc.

## 11. Tham chiếu DN, ACL và ảnh hưởng sau di chuyển

Một nhóm có thể chứa:

```ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: backend
member: uid=lan,ou=people,dc=example,dc=org
```

Khi Lan chuyển sang `ou=staff`, giá trị `member` có thể vẫn là **DN cũ**. Một số directory có cơ chế tự cập nhật các tham chiếu DN, nhưng cần được bật/cấu hình và **không có bảo đảm chung** cho mọi server.

Những nơi cần xác minh sau di chuyển:

| Nơi phụ thuộc DN | Hậu quả nếu giữ DN cũ |
| --- | --- |
| `member`/`uniqueMember` ở nhóm | Nhóm tham chiếu tới entry không còn ở DN đó |
| `manager` hoặc attribute DN tham chiếu khác | Quan hệ quản lý/ứng dụng có thể sai |
| ACL được viết theo DN hoặc subtree | Quyền của entry dưới OU mới có thể khác |
| Cache ứng dụng, bản ghi audit, cấu hình đồng bộ | Tra cứu/đồng bộ bằng DN cũ thất bại |
| Repository có `@Entry(base=...)` cố định | Không nhìn thấy entry đã rời khỏi nhánh ban đầu |
| Các replica LDAP | Có thể tạm thời nhìn thấy trạng thái khác nhau trong giai đoạn đồng bộ |

**Quyền truy cập có thể đổi khi entry chuyển parent**, vì nhiều chính sách ACL dựa trên vị trí subtree. Một tài khoản từng có quyền đọc Lan ở `ou=people` có thể không có quyền đọc Lan ở `ou=staff`; ngược lại quyền ghi cũng có thể thay đổi. Không đánh giá move chỉ qua mã kết quả thành công của một request.

## 12. Khi máy chủ không cho phép di chuyển ra ngoài naming context

Giả sử cần chuyển entry từ `dc=example,dc=org` sang `dc=archive,dc=org` nhưng server từ chối Modify DN. Hãy phân biệt **di chuyển danh tính** với **sao chép dữ liệu**:

1. **Xác định phạm vi và mục tiêu:** chuyển một entry hay cả subtree; cần giữ nguyên `uid`, DN, membership và lịch sử hay không?
2. **Đọc schema và cấu hình của đích:** `objectClass`, thuộc tính MUST/MAY, quy tắc RDN và naming context mới có tương thích không?
3. **Chuẩn bị parent và quyền:** các container đích phải tồn tại; tài khoản ghi phải có quyền trên directory đích.
4. **Đánh giá dữ liệu có thể chuyển:** tách thuộc tính ứng dụng với operational attributes do server quản lý (ví dụ `entryUUID`, `modifyTimestamp` nếu có); những attribute như mật khẩu/hash, ACL hay trạng thái tài khoản có thể chịu quy tắc riêng.
5. **Tạo bản ghi ở đích bằng Add theo kế hoạch:** không giả định copy nguyên LDIF là hợp lệ. Cần xử lý trùng DN, mapping, quyền và quá trình nhân bản nếu có.
6. **Xác minh dữ liệu và ứng dụng:** kiểm tra DN mới, nhóm tham chiếu, tìm kiếm theo repository, quyền truy cập, kết nối và kết quả nghiệp vụ.
7. **Chuyển luồng sử dụng và tham chiếu:** cập nhật ứng dụng phụ thuộc DN hoặc quy trình đồng bộ; xác nhận không còn traffic dựa vào DN cũ.
8. **Xử lý nguồn theo chính sách đã duyệt:** chỉ xóa hoặc vô hiệu hóa entry nguồn sau khi đã xác minh việc chuyển và có phương án phục hồi.

Đây là một **workflow nhiều bước**, không phải một Modify DN. Nếu nguồn và đích do hai DSA độc lập quản lý, không được kỳ vọng một transaction LDAP tiêu chuẩn rollback được toàn bộ thao tác Add, cập nhật tham chiếu và Delete. Với dữ liệu xác thực hoặc nhóm phân quyền, nên dùng công cụ/migration API được nhà cung cấp directory hỗ trợ, vì một số thuộc tính không được phép sao chép trực tiếp.

## 13. Chẩn đoán khi `rename` bị từ chối

| LDAP result code thường gặp | Ý nghĩa liên quan đến move | Cần kiểm tra |
| --- | --- | --- |
| `noSuchObject (32)` | DN nguồn hoặc parent đích không được tìm thấy | Base DN, naming context, parent, referral |
| `entryAlreadyExists (68)` | DN đích đã có entry | RDN đích, xung đột với entry khác |
| `insufficientAccessRights (50)` | Không đủ quyền đổi tên/di chuyển | ACL tại source, parent nguồn, parent đích |
| `namingViolation (64)` | RDN hoặc vị trí đặt tên không hợp lệ | Name form, cấu trúc DIT, giá trị RDN |
| `objectClassViolation (65)` | Entry sau move không đáp ứng schema | `objectClass`, thuộc tính bắt buộc, schema đích |
| `notAllowedOnRDN (67)` | Thao tác ảnh hưởng RDN không được phép | Giá trị RDN, ràng buộc của server |
| `notAllowedOnNonLeaf (66)` | Server từ chối thao tác liên quan entry có con | Khả năng/hạn chế khi move subtree |
| `affectsMultipleDSAs (71)` | Thay đổi vượt ranh giới nhiều DSA | Phân vùng dữ liệu, referral, server nguồn/đích |
| `referral (10)` | Server chỉ tới nơi khác xử lý yêu cầu | Ranh giới server và chính sách xử lý referral |
| `unwillingToPerform (53)` | Server từ chối vì policy/giới hạn triển khai | Log server, giới hạn subtree/backend, rule đặc thù |
| `loopDetect (54)` | Có nguy cơ tạo vòng lặp khi tham chiếu/di chuyển | Không đặt parent đích bên trong subtree nguồn |

Các result code trong bảng là **dấu hiệu chẩn đoán**, không phải bảng ánh xạ một-một bắt buộc: server khác nhau có thể từ chối cùng một tình huống bằng mã khác nhau. Spring LDAP/JNDI cũng có thể chuyển mã LDAP thành exception Java. Khi ghi log, chỉ lưu **thông tin DN đủ phục vụ chẩn đoán** theo chính sách dữ liệu của hệ thống; không ghi password hoặc thuộc tính nhạy cảm.

### 13.1. Mất phản hồi không đồng nghĩa chắc chắn thất bại

Giả sử request `rename(oldDn, newDn)` đã gửi tới server nhưng client mất kết nối trước khi nhận response. Không thể suy ra thao tác chưa được áp dụng. Trước khi retry:

- Kiểm tra **DN nguồn** còn tồn tại không.
- Kiểm tra **DN đích** có tồn tại không và có đúng entry dự định không; nếu directory hỗ trợ mã định danh bền vững của entry, dùng nó để đối chiếu.
- Kiểm tra các **DN tham chiếu** đang dùng trong nhóm hoặc ứng dụng.
- Chỉ quyết định retry, phục hồi hoặc điều tra tiếp sau khi hiểu trạng thái hiện tại.

Retry mù quáng có thể khiến lần thứ hai báo `noSuchObject` ở DN cũ hoặc `entryAlreadyExists` ở DN mới, dù lần đầu đã thành công.

## 14. Checklist thực hành với Spring Data LDAP

Trong môi trường LDAP test, tạo trước `ou=people`, `ou=staff` và ba user giả. Sau đó thực hiện lần lượt các bài thử:

| Bài thử | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| 1. Rename cùng parent | `uid=lan` → `uid=lan.nguyen` tại `ou=people` | DN mới tồn tại, DN cũ vắng mặt; attribute RDN theo policy |
| 2. Move entry lá | `uid=lan`: `people` → `staff` | Giữ đúng thuộc tính; chính sách ACL đích được áp dụng |
| 3. Parent không tồn tại | Move tới `ou=missing` | Bị từ chối, không tự tạo parent |
| 4. DN đích trùng | Move tới `uid=mai,ou=staff` đã có | Bị từ chối, không ghi đè entry đích |
| 5. Quyền thiếu | Dùng bind DN chỉ có quyền read | Move bị từ chối theo ACL |
| 6. Rename subtree | Di chuyển OU test có vài hậu duệ | Xác minh tất cả DN con đã đổi nếu server hỗ trợ |
| 7. Move vòng lặp | Đặt gốc subtree dưới hậu duệ của chính nó | Bị từ chối |
| 8. Cross-naming-context | Move qua suffix khác bằng tài khoản test | Ghi nhận server cho phép hay từ chối; không giả định kết quả |
| 9. Mất phản hồi | Giả lập network drop sau khi gửi request | Đọc lại cả old DN/new DN trước khi retry |
| 10. Kiểm tra tham chiếu | Một nhóm `member` trỏ DN nguồn | Xác minh có/không tự cập nhật và quy trình sửa |

Hãy dùng **directory test có dữ liệu giả** và một service account có quyền hạn được kiểm soát. Với những thử nghiệm liên quan subtree hoặc thay đổi DN, nên lưu trạng thái ban đầu để có thể khôi phục; kiểm tra log server khi thông tin lỗi phía client chưa đủ.

## 15. Câu hỏi tự luyện

**Câu 1.** Lan được chuyển từ `uid=lan,ou=people,dc=example,dc=org` sang `uid=lan,ou=staff,dc=example,dc=org`. Đây là rename hay move? Có vượt naming context không?

*Đáp án gợi ý:* Đây là **move giữa hai parent** trong cùng naming context `dc=example,dc=org`. Dùng Modify DN với `newSuperior` là OU đích khi server hỗ trợ và quyền cho phép.

**Câu 2.** Server công bố hai naming context `dc=example,dc=org` và `dc=archive,dc=org` trên cùng endpoint. Có thể khẳng định `rename` xuyên hai suffix sẽ thành công không?

*Đáp án gợi ý:* **Không.** Cần kiểm tra server/backend/DSA và chức năng Modify DN qua naming context. Việc cả hai suffix có trong Root DSE chỉ cho biết chúng được công bố, không bảo đảm move xuyên suffix.

**Câu 3.** Một tài khoản có quyền sửa `mail` của user trong `ou=people` nhưng không có quyền thêm con dưới `ou=staff`. Vì sao `rename` có thể bị từ chối?

*Đáp án gợi ý:* **Modify attribute** và **Modify DN** là hai thao tác khác nhau. Move cần quyền thích hợp tại nguồn và đích theo ACL của server.

**Câu 4.** Khi chuyển `ou=engineering` có hai OU con, những DN hậu duệ nào thay đổi nếu Modify DN thành công?

*Đáp án gợi ý:* DN của **tất cả hậu duệ** sẽ thay đổi phần hậu tố tên theo vị trí mới của `ou=engineering`. Khả năng thực thi và giới hạn thực tế tùy server.

**Câu 5.** Group `cn=backend` còn `member: uid=lan,ou=people,...` sau khi Lan chuyển sang `ou=staff`. Có thể mặc định reference này được cập nhật không?

*Đáp án gợi ý:* **Không.** Cần xác minh plugin/overlay duy trì tham chiếu của directory hoặc cập nhật DN tham chiếu trong quy trình nghiệp vụ.

**Câu 6.** `LdapTemplate.rename` bị timeout trước khi client nhận response. Có nên gọi lại ngay cùng old/new DN?

*Đáp án gợi ý:* Trước tiên **đọc lại DN nguồn và đích**; request đầu có thể đã thành công. Chỉ retry sau khi xác định trạng thái thực tế.

## 16. Ghi nhớ

- **Move trong một OU/cùng naming context** thường có thể thực hiện qua LDAP **Modify DN**, nhưng vẫn cần quyền, schema, parent và khả năng server phù hợp.
- **Move qua naming context** là ranh giới quan trọng: cùng endpoint không bảo đảm một Modify DN xuyên suffix được hỗ trợ; **move qua DSA khác** có thể cần migration workflow riêng.
- Trước khi di chuyển, kiểm tra **DN nguồn, parent đích, xung đột DN, chu kỳ DIT, naming rule, ACL và subtree**.
- Nếu một Modify DN trên subtree được server chấp nhận, **DN của các hậu duệ thay đổi theo**; tham chiếu `member`/`manager` và các ứng dụng lưu DN cần được kiểm tra riêng.
- Trong Spring LDAP, dùng `LdapTemplate.rename` cho ý định đổi DN. Không mặc định đổi `@DnAttribute` rồi `repository.save` tương đương một Modify DN nguyên tử.
- Khi mất phản hồi hoặc gặp lỗi, dựa trên **trạng thái directory sau thao tác** để quyết định khắc phục. Không tự động xóa nguồn nếu chuyển sang vùng tên khác mà chưa xác minh dữ liệu đích.

**Tài liệu tham khảo:**

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): mục Modify DN, các trường `newrdn`, `deleteoldrdn`, `newSuperior` và result codes.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): DIT, naming context, schema và DSA.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN/RDN và quy tắc escape.
- [Spring LDAP Reference Documentation](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, `LdapTemplate`, JNDI và thao tác với DN.
- [Spring Data LDAP Reference Documentation](https://docs.spring.io/spring-data/ldap/reference/): repository và ánh xạ entity ODM.
