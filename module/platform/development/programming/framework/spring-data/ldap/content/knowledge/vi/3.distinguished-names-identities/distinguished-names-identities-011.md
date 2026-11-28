# Thiết kế quy tắc đặt DN để hạn chế đổi tên và di chuyển

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Distinguished Name (DN)**, Relative Distinguished Name (RDN), vị trí trong DIT và định danh bền vững của một đối tượng.
2. Chọn naming attribute và cấu trúc OU ít thay đổi khi người dùng đổi tên, đổi email, chuyển phòng ban hoặc thay đổi vai trò.
3. Thiết kế RDN dựa trên khóa ổn định, đồng thời giữ tên hiển thị và thông tin nghiệp vụ trong các attribute có thể cập nhật.
4. Xây dựng naming contract có quy tắc uniqueness, schema, escaping, casing và vòng đời rõ ràng.
5. Hiểu ảnh hưởng của Modify DN tới DN đầy đủ, thuộc tính RDN, group membership, cache và các hệ thống tham chiếu.
6. Dùng `LdapNameBuilder`, `LdapName` và Spring Data LDAP repository để tạo, lưu và tìm entry an toàn.
7. Phân biệt khả năng tự duy trì referential integrity của từng LDAP server với hành vi chuẩn của LDAP.
8. Lập kế hoạch chuyển đổi naming convention và kiểm thử rename/move mà không làm mất identity hoặc quan hệ dữ liệu.

Bài thuộc chương **DN và định danh** của module `SPRING_DATA_LDAP`. Module giúp ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP repository, ánh xạ entry phân cấp sang object Java, làm việc với DN, `objectClass`, schema, repository/`LdapTemplate`, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Một quy tắc đặt DN tốt giúp directory dễ đọc và dễ quản trị. Quan trọng hơn, nó hạn chế việc một thay đổi nghiệp vụ bình thường buộc ứng dụng phải đổi địa chỉ của entry, cập nhật hàng loạt tham chiếu và làm mới cache.

## 1. DN là địa chỉ trong cây directory, không phải identity bất biến

LDAP lưu entry trong Directory Information Tree (DIT). Mỗi entry có một DN xác định vị trí của nó trong cây.

Ví dụ:

```text
uid=alice,ou=people,dc=example,dc=org
```

DN này gồm:

| Thành phần | Vai trò |
| --- | --- |
| `uid=alice` | RDN của entry user |
| `ou=people` | RDN của container cha |
| `dc=example` | Thành phần của naming context |
| `dc=org` | Thành phần gốc còn lại của DN |

Trong biểu diễn DN chuẩn, RDN bên trái là thành phần gần entry nhất; các RDN tiếp theo lần lượt xác định cha và tổ tiên.

### 1.1. RDN và DN đầy đủ

- **RDN (Relative Distinguished Name):** tên phân biệt entry trong phạm vi parent trực tiếp.
- **DN (Distinguished Name):** chuỗi RDN từ entry tới naming context/root của cây.
- **Parent DN:** DN của entry cha trực tiếp.
- **Naming context:** phần cây mà một directory server chịu trách nhiệm phục vụ như một đơn vị dữ liệu.

Ví dụ hai user có thể có cùng `uid` nếu nằm dưới hai parent khác nhau:

```text
uid=alice,ou=employees,dc=example,dc=org
uid=alice,ou=contractors,dc=example,dc=org
```

Hai DN đầy đủ khác nhau. Tuy nhiên, nếu hệ thống cần một khóa duy nhất trên toàn tổ chức, chỉ bảo đảm uniqueness trong một OU là chưa đủ.

### 1.2. DN có thể đổi khi đổi tên hoặc di chuyển

Giả sử user đổi tên hiển thị từ Alice sang Alicia:

```text
Trước:
cn=Alice Nguyen,ou=people,dc=example,dc=org

Sau:
cn=Alicia Nguyen,ou=people,dc=example,dc=org
```

Nếu `cn` được dùng làm RDN, DN thay đổi theo tên hiển thị.

Tương tự, nếu user chuyển từ OU `employees` sang `alumni`:

```text
Trước:
uid=acct-7f31,ou=employees,dc=example,dc=org

Sau:
uid=acct-7f31,ou=alumni,dc=example,dc=org
```

RDN không đổi nhưng DN đầy đủ vẫn đổi vì parent DN thay đổi.

Đây là điểm quan trọng khi thiết kế: **RDN ổn định chỉ tránh rename ở phần tên entry; nó không làm DN bất biến nếu parent container còn thay đổi.**

### 1.3. Phân biệt bốn loại tên/định danh

| Khái niệm | Ví dụ | Có thể thay đổi? | Dùng làm gì? |
| --- | --- | --- | --- |
| DN | `uid=acct-7f31,ou=people,...` | Có, khi rename/move | Địa chỉ entry trong DIT |
| RDN | `uid=acct-7f31` | Có, khi rename | Tên entry dưới parent |
| Tên nghiệp vụ/đăng nhập | `alice`, `alice@example.org` | Có thể đổi theo policy | Login, giao tiếp, hiển thị |
| Stable identity | UUID/ID bất biến | Không đổi trong vòng đời identity | Liên kết dữ liệu, audit, cache key |

Không nên dùng DN làm primary key lâu dài trong database ứng dụng, event, URL công khai hoặc cache key nếu đối tượng có thể đổi tên/di chuyển.

### 1.4. @Id trong Spring Data LDAP không biến DN thành ID bất biến

Một entity thường dùng DN làm ID:

```java
@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "mail")
    private String email;
}
```

`@Id Name dn` là địa chỉ để Spring Data LDAP tìm entry. Khi entry được move, DN mới sẽ khác; object đã load hoặc cache cũ không tự biến thành địa chỉ mới.

Nếu ứng dụng cần tìm lại cùng một người sau rename/move, hãy lưu thêm stable identity như `uid` bất biến theo naming contract, `appPersonId`, `entryUUID` hoặc `objectGUID` tùy directory.

## 2. Những quy tắc đặt DN dễ gây tốn kém khi thay đổi

Một naming convention thường gây nhiều lần rename/move khi đưa các thuộc tính nghiệp vụ có khả năng thay đổi vào RDN hoặc parent OU.

### 2.1. Dùng tên hiển thị làm RDN

Ví dụ:

```text
cn=Alice Nguyen,ou=people,dc=example,dc=org
```

`cn` thường là common name/tên hiển thị. Tên có thể thay đổi do kết hôn, sửa chính tả, thay đổi cách viết hoặc yêu cầu đồng bộ từ hệ thống nhân sự.

Nếu DN dựa trên `cn`, mỗi lần sửa tên có thể kéo theo:

- Modify DN.
- Cập nhật các thuộc tính tham chiếu lưu DN.
- Làm mới cache chứa DN cũ.
- Đồng bộ lại các hệ thống lưu DN.
- Kiểm tra lại quyền và policy dựa trên DN.
- Cập nhật audit/integration nếu chúng dùng DN như định danh.

### 2.2. Dùng email hoặc UPN làm RDN

Ví dụ:

```text
mail=alice@example.org,ou=people,dc=example,dc=org
```

Email và UPN thường được xem là tên đăng nhập tiện lợi, nhưng chúng có thể đổi khi đổi họ tên, đổi domain email, chuyển công ty/tenant, hợp nhất domain hoặc thay đổi chính sách định danh.

Nếu email nằm trong RDN, đổi email cũng đồng nghĩa đổi DN. Hãy giữ email trong attribute riêng và chỉ dùng làm RDN khi tổ chức cam kết nó bất biến trong suốt vòng đời entry.

### 2.3. Đưa phòng ban, chức danh hoặc địa điểm vào OU

Ví dụ:

```text
cn=Alice,ou=Engineering,ou=HoChiMinh,ou=Employees,dc=example,dc=org
```

Cách này khiến thay đổi tổ chức kéo theo move entry:

- Alice chuyển Engineering sang Platform.
- Alice chuyển từ TP.HCM sang Hà Nội.
- Nhóm Engineering được tách thành hai đơn vị.
- Nhân viên chuyển sang contractor nhưng vẫn là cùng identity.

Nếu OU phản ánh cấu trúc tổ chức thay đổi thường xuyên, DN trở thành bản sao của sơ đồ tổ chức và cần được cập nhật liên tục.

### 2.4. Dùng tên nhóm làm DN trong khi nhóm đổi tên thường xuyên

Ví dụ:

```text
cn=Engineering,ou=groups,dc=example,dc=org
```

Nếu nhóm đổi tên thành Platform Engineering, DN thay đổi và mọi tham chiếu tới group có thể bị ảnh hưởng.

Nên phân biệt:

- Stable group identity: mã nhóm không đổi.
- Group display name: tên hiển thị có thể thay đổi.
- Description/department/owner: thông tin nghiệp vụ cập nhật độc lập.

### 2.5. Dùng dữ liệu cá nhân hoặc bí mật trong DN

DN có thể xuất hiện trong log, audit, referral, error message, URL hoặc trace. Không nên đặt các thông tin như số căn cước, ngày sinh, số điện thoại cá nhân hoặc dữ liệu bí mật vào RDN.

Một opaque identifier ngẫu nhiên/khó đoán thường giảm rò rỉ thông tin và tránh phải đổi DN khi thông tin cá nhân được sửa.

## 3. Thiết kế RDN dựa trên stable key

Mục tiêu là chọn một giá trị:

- Duy nhất trong phạm vi cần thiết.
- Không thay đổi khi tên, email, phòng ban hoặc chức vụ thay đổi.
- Không được tái sử dụng cho identity khác.
- Được kiểm soát bởi một hệ thống cấp phát có thẩm quyền.
- Phù hợp với schema và matching rule của directory.
- Không chứa dữ liệu nhạy cảm không cần thiết.

### 3.1. Ví dụ dùng uid làm khóa tài khoản bất biến

Nếu tổ chức định nghĩa `uid` là mã tài khoản nội bộ bất biến, có thể đặt:

```ldif
dn: uid=acct-7f31a2,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: acct-7f31a2
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

Khi Alice đổi tên hoặc email:

```ldif
dn: uid=acct-7f31a2,ou=people,dc=example,dc=org
changetype: modify
replace: cn
cn: Alicia Nguyen
-
replace: mail
mail: alicia@example.org
```

DN vẫn giữ nguyên vì RDN dùng `uid=acct-7f31a2`, không phụ thuộc `cn` hay `mail`.

**Điều kiện:** `uid` trong ví dụ này được tổ chức cam kết là khóa nội bộ bất biến. Trong nhiều hệ thống, `uid` chính là username có thể đổi; nếu vậy, không nên áp dụng ví dụ này mà không thay đổi naming contract.

### 3.2. Dùng custom stable ID khi thuộc tính chuẩn không phù hợp

Nếu `uid` phải phản ánh username, có thể định nghĩa attribute riêng như `appPersonId` theo schema của tổ chức:

```ldif
dn: appPersonId=01J9Q7M2R4K8,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: appPerson
appPersonId: 01J9Q7M2R4K8
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
```

`appPerson` ở đây là auxiliary object class minh họa do tổ chức định nghĩa để cho phép `appPersonId`. Trước khi dùng, cần triển khai schema attribute/objectClass trên mọi server/replica liên quan và xác nhận naming attribute được phép theo schema.

Khi Alice đổi username:

```ldif
dn: appPersonId=01J9Q7M2R4K8,ou=people,dc=example,dc=org
changetype: modify
replace: uid
uid: alicia
```

DN không thay đổi.

Không tự tạo custom schema chỉ để né một lần rename. Hãy đánh giá khả năng tương thích với các ứng dụng LDAP khác, provisioning, replication, backup/restore và công cụ quản trị.

### 3.3. Định danh do server cấp và định danh do ứng dụng cấp

Một số directory cung cấp operational identifier ổn định:

| Directory/loại thuộc tính | Vai trò | Có nên dùng trực tiếp làm RDN? |
| --- | --- | --- |
| Active Directory `objectGUID` | GUID server cấp, không đổi khi object rename/move trong AD DS | Thường dùng để nhận diện/tham chiếu; không giả định có thể dùng làm naming attribute |
| OpenLDAP `entryUUID` | Operational identifier server cấp cho entry | Dùng làm stable lookup key; không phải user-modifiable naming attribute thông thường |
| `appPersonId` do ứng dụng cấp | Khóa bền vững do ứng dụng kiểm soát | Có thể dùng làm RDN nếu schema cho phép và contract được triển khai nhất quán |
| `uid` bất biến theo quy ước tổ chức | Khóa tài khoản | Có thể dùng làm RDN nếu không phải login name có thể đổi |

**Không nhầm stable identifier với naming attribute.** Một thuộc tính có thể bất biến nhưng là operational attribute do server quản lý, không được client tự ghi hoặc không được schema cho phép làm RDN.

### 3.4. Stable ID phải không tái sử dụng

Nếu user nghỉ việc rồi một người khác nhận lại cùng `uid`, ứng dụng lưu `uid` làm foreign key có thể liên kết nhầm lịch sử của hai người.

Quy tắc nên nêu rõ:

- Stable ID chỉ cấp một lần.
- Không tái sử dụng sau delete/disable.
- Rehire là cùng identity hay identity mới phải có policy rõ.
- Nếu dữ liệu được restore/migrate, giữ nguyên ID của cùng identity.
- Nếu merge hai identity, có mapping/audit về ID cũ và ID chuẩn mới.

### 3.5. Stable ID trong group

Group cũng có thể đổi tên hoặc owner. Có thể dùng mã nhóm ổn định trong RDN và tên hiển thị trong attribute:

```ldif
dn: cn=grp-01J8D2,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: grp-01J8D2
description: Platform Engineering
member: uid=acct-7f31a2,ou=people,dc=example,dc=org
```

Trong ví dụ, `cn` vừa là naming attribute vừa là giá trị bắt buộc của `groupOfNames`, nhưng giá trị của nó là mã nhóm ổn định. Tên thân thiện nằm trong `description` (hoặc attribute hiển thị phù hợp schema).

Nếu ứng dụng cần `displayName` riêng, phải kiểm tra schema/server hỗ trợ attribute đó; không giả định mọi directory đều có cùng custom attribute.

## 4. Thiết kế hierarchy OU ít thay đổi

Ngay cả khi RDN của user ổn định, thay đổi parent OU vẫn làm DN thay đổi. Vì vậy cần thiết kế cả phần cây phía trên.

### 4.1. Tạo container theo ranh giới vòng đời và quản trị ổn định

Một cấu trúc cơ bản:

```text
dc=example,dc=org
├── ou=people
├── ou=groups
├── ou=service-accounts
└── ou=devices
```

Các OU trên phân loại theo loại entry tương đối ổn định. Một user đổi phòng ban vẫn ở `ou=people`; một group đổi tên vẫn ở `ou=groups`.

Ví dụ:

```text
uid=acct-7f31a2,ou=people,dc=example,dc=org
uid=acct-9b28c1,ou=people,dc=example,dc=org
cn=grp-01J8D2,ou=groups,dc=example,dc=org
```

Phòng ban, vị trí, manager, cost center hoặc trạng thái nhân sự được biểu diễn bằng attribute và group membership.

### 4.2. Khi nào nên chia OU theo tenant, region hoặc lifecycle?

Có thể dùng hierarchy sâu hơn nếu nó phản ánh một ranh giới ổn định có ý nghĩa vận hành:

| Ranh giới | Khi nào phù hợp | Rủi ro |
| --- | --- | --- |
| Tenant | Tenant là đơn vị dữ liệu/lifecycle độc lập, ít đổi | Chuyển tenant làm DN đổi |
| Region | Có yêu cầu residency, replication hoặc admin boundary ổn định | Tái tổ chức vùng làm nhiều entry phải move |
| Loại identity | People, groups, devices, service accounts có policy khác nhau | Thay đổi phân loại có thể làm move |
| Department | Chỉ khi OU là boundary quản trị bền vững | Cơ cấu tổ chức đổi thường xuyên |
| Manager/team | Hiếm khi phù hợp làm parent OU | Một lần chuyển nhóm làm đổi DN nhiều |

Đừng chọn hierarchy chỉ vì nó giống sơ đồ tổ chức hiện tại. Hãy hỏi: **nếu đơn vị này đổi tên, sáp nhập hoặc tách ra, có thật sự cần di chuyển entry trong directory không?**

### 4.3. Không mã hóa toàn bộ cây tổ chức vào DN

Thay vì:

```text
uid=acct-7f31,
ou=platform,
ou=engineering,
ou=technology,
ou=ho-chi-minh,
ou=employees,
dc=example,dc=org
```

Hãy cân nhắc:

```text
uid=acct-7f31,ou=people,dc=example,dc=org
```

và giữ thông tin tổ chức dưới dạng attribute:

```ldif
departmentNumber: D042
departmentName: Platform Engineering
l: Ho Chi Minh City
employeeType: permanent
manager: uid=acct-91b2,ou=people,dc=example,dc=org
```

`manager` trong ví dụ là một DN reference nên vẫn có thể đổi khi manager move. Nếu ứng dụng cần tham chiếu bền vững, lưu stable manager ID ở nguồn authoritative và resolve ra DN hiện tại khi ghi LDAP.

### 4.4. Parent container cũng cần stable naming

Không nên đặt `ou=2026-hiring` nếu entry sẽ ở lại directory sau khi chiến dịch tuyển dụng kết thúc. Một container phản ánh chiến dịch hoặc nhóm dự án có thể phải move hàng loạt entry khi lifecycle kết thúc.

Container nên phản ánh **ranh giới lưu trữ/quản trị dài hạn**, còn chiến dịch, dự án và trạng thái vòng đời nên là attribute hoặc membership.

## 5. Viết naming contract trước khi tạo entry

Naming convention không chỉ là mẫu chuỗi DN. Nó là hợp đồng giữa ứng dụng, schema, administrator, provisioning và các hệ thống tích hợp.

### 5.1. Các nội dung contract cần xác định

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| Stable identity | Khóa nào nhận diện cùng một đối tượng qua rename/move? |
| RDN attribute | Attribute nào tạo RDN? Có được schema cho phép không? |
| Uniqueness scope | ID duy nhất trong OU, naming context, tenant hay toàn forest? |
| Immutability | Actor nào được phép đổi khóa? Có bao giờ được đổi không? |
| Reuse policy | ID có được tái sử dụng sau delete/disable không? |
| Parent hierarchy | Entry nằm trong container nào và container đó có ổn định không? |
| Attribute lifecycle | `cn`, `mail`, `uid`, department và manager thay đổi thế nào? |
| Case/matching | Server dùng equality matching rule nào? |
| Encoding | Unicode, dấu cách, ký tự đặc biệt được xử lý ra sao? |
| Move policy | Entry có được chuyển parent không? Trong cùng naming context hay không? |
| References | Group, manager và ứng dụng ngoài cập nhật DN thế nào? |
| Ownership | Hệ thống nào là nguồn authoritative của stable ID và parent DN? |

### 5.2. Chọn một naming attribute đơn giản

RDN có thể gồm nhiều AVA, ví dụ:

```text
ou=people+cn=Directory Users,dc=example,dc=org
```

Multi-valued RDN hợp lệ theo LDAP nhưng thường làm naming contract khó quản lý hơn. Với ứng dụng nghiệp vụ, ưu tiên một naming attribute duy nhất, có stable key rõ ràng và quy tắc uniqueness dễ kiểm tra.

### 5.3. Kiểm tra schema trước khi chốt naming attribute

Khi chọn attribute làm RDN, cần xác minh:

- Attribute type có được khai báo trong schema không?
- Object class của entry cho phép attribute đó không?
- Attribute có syntax phù hợp với giá trị ID không?
- Equality matching rule có rõ ràng không?
- Attribute có phải operational/no-user-modification không?
- Attribute có thể được ghi trong Add/Modify DN không?
- Schema và các server/replica trong topology có cùng version không?

Không dùng `entryUUID`, `objectGUID`, `createTimestamp` hoặc operational attribute khác làm RDN chỉ vì chúng ổn định. Những thuộc tính server-managed có thể không cho client sử dụng làm naming attribute.

### 5.4. Quy tắc uniqueness và collision

Nếu RDN dùng `uid`, `appPersonId` hoặc `cn`, xác định:

- Có cần uniqueness toàn naming context không?
- Có nhiều OU chứa cùng giá trị không?
- Khi hai worker tạo cùng ID, ai xử lý collision?
- Có cần kiểm tra trước khi Add hay dựa vào Add result code?
- Khi restore từ backup, ID có thể bị trùng không?

Một search kiểm tra trước khi Add không loại bỏ race condition. Server vẫn là nơi quyết định DN đã tồn tại hay chưa; ứng dụng cần xử lý `entryAlreadyExists` và phân biệt duplicate hợp lệ với identity conflict.

### 5.5. Chuẩn hóa giá trị naming

Đặt quy tắc rõ cho chữ hoa/chữ thường, Unicode normalization nếu ứng dụng cần một dạng thống nhất, dấu cách đầu/cuối, ký tự không hợp lệ theo schema, chiều dài tối đa và prefix/suffix của ID.

Không tự viết quy tắc so sánh DN bằng lowercase toàn chuỗi. DN equality phụ thuộc matching rule của từng attribute type; biểu diễn chuỗi khác nhau có thể vẫn biểu thị cùng DN.

## 6. Escaping DN và xây dựng DN an toàn trong Java

Một DN string có dấu phẩy phân tách RDN. Nếu giá trị RDN cũng chứa dấu phẩy, dấu cộng, dấu nháy hoặc dấu gạch chéo ngược, nó phải được escape theo RFC 4514.

Ví dụ giá trị common name:

```text
CN=Nguyen, Alice
```

Nếu nối chuỗi thủ công, dấu phẩy trong tên có thể bị hiểu là ranh giới RDN. Biểu diễn escaped đúng:

```text
cn=Nguyen\, Alice,ou=people,dc=example,dc=org
```

### 6.1. Các ký tự cần chú ý

RFC 4514 quy định escaping cho các trường hợp như:

- Dấu cách ở đầu hoặc cuối value.
- Dấu `#` ở đầu value.
- Các ký tự `"`, `+`, `,`, `;`, `<`, `>`, `\`.
- Null byte.

Không tự thay thế một vài ký tự bằng regex rồi cho rằng DN đã an toàn. Dùng thư viện xử lý RDN/DN để encode đúng.

### 6.2. Dùng LdapNameBuilder

Spring LDAP cung cấp `LdapNameBuilder` để tạo `LdapName`:

```java
import javax.naming.Name;

import org.springframework.ldap.support.LdapNameBuilder;

String stableUid = "acct-7f31a2";

Name personDn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", stableUid)
    .build();

System.out.println(personDn);
```

Kết quả có dạng:

```text
uid=acct-7f31a2,ou=people,dc=example,dc=org
```

`LdapNameBuilder` thêm thành phần mới vào đầu DN đã xây dựng. Bắt đầu từ base DN, thêm OU rồi thêm RDN của entry sẽ tạo đúng thứ tự leaf-to-root.

### 6.3. Giá trị có dấu phẩy vẫn được xử lý như một RDN value

```java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name unusualName = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("cn", "Nguyen, Alice")
    .build();

System.out.println(unusualName);
```

Builder tạo RDN và escape value phù hợp. Không tự nối:

```java
// Không nên: giá trị có dấu phẩy có thể làm hỏng cấu trúc DN.
String dn = "cn=" + displayName + ",ou=people,dc=example,dc=org";
```

Nếu dữ liệu đầu vào đến từ user, hãy validate theo business contract và dùng builder; escaping không thay thế authorization hoặc validation.

### 6.4. Parse DN cũ bằng LdapName

Khi cần phân tích DN từ LDAP:

```java
import javax.naming.ldap.LdapName;

LdapName currentDn = new LdapName(
    "uid=acct-7f31a2,ou=people,dc=example,dc=org"
);

```

`LdapName` lưu cấu trúc DN thay vì coi nó là một chuỗi tùy ý. Tuy vậy, không dùng `toString().equals(...)` làm kiểm tra identity toàn cục. Khi cần nhận diện cùng đối tượng, tra stable ID trong directory hoặc hệ thống authoritative.

## 7. Tìm entry bằng stable identity thay vì giữ DN cũ

Ứng dụng nên có một hàm phân giải stable ID sang DN hiện tại.

### 7.1. Repository query theo thuộc tính bất biến

Nếu `uid` được quy định là stable key:

```java
import java.util.Optional;

import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    Optional<PersonEntry> findByUid(String uid);
}
```

Caller có thể tìm theo `uid` thay vì lưu DN ở nhiều nơi:

```java
PersonEntry person = personRepository.findByUid("acct-7f31a2")
    .orElseThrow(() -> new PersonNotFoundException("acct-7f31a2"));

Name currentDn = person.getDn();
```

Tên method derived query phụ thuộc property/attribute mapping của entity. Nếu dùng custom stable ID, mapping property tương ứng và kiểm tra query được tạo đúng theo schema.

### 7.2. Phân giải bằng LdapTemplate

Có thể tìm DN theo stable attribute:

```java
import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public Name findPersonRelativeDnByUid(LdapTemplate ldapTemplate, String uid) {
    LdapQuery search = query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(uid);

    List<Name> dns = ldapTemplate.search(
        search,
        (ContextMapper<Name>) context -> context.getDn()
    );

    if (dns.size() != 1) {
        throw new IllegalStateException(
            "Expected exactly one person for stable uid"
        );
    }

    return dns.get(0);
}
```

`ContextMapper` trả về DN tương đối với base của `ContextSource`. Nếu caller cần DN đầy đủ, hãy ghép relative DN với base đã cấu hình bằng API `LdapName`, không nối chuỗi. Spring LDAP query builder xử lý giá trị filter như một giá trị assertion. Không nối `uid` từ user input trực tiếp vào filter string. Ứng dụng cũng cần kiểm tra kết quả duy nhất theo contract; nếu có nhiều entry thì đó là data integrity issue cần xử lý.

### 7.3. Không cache DN vô thời hạn

Nếu cache:

```text
personId -> uid=acct-7f31a2,ou=people,dc=example,dc=org
```

thì sau move, mapping trên có thể cũ. Có thể cache DN trong thời gian ngắn nếu có chiến lược invalidation/refresh, nhưng stable ID vẫn phải là cache key.

Các lựa chọn:

- Resolve DN khi cần ghi hoặc khi thao tác nhạy cảm.
- Invalidate mapping sau rename/move event.
- Dùng TTL ngắn và xử lý `noSuchObject` bằng cách resolve lại stable ID.
- Lưu current DN như một cacheable locator, không dùng làm identity.
- Không dùng DN cũ trong authorization decision nếu entry có thể đã move hoặc identity đã bị tái sử dụng.

## 8. Group membership và các tham chiếu lưu DN

Một trong những chi phí lớn nhất khi thay đổi DN là những entry khác có thể lưu DN đó làm giá trị.

Ví dụ group:

```ldif
dn: cn=grp-01J8D2,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: grp-01J8D2
description: Platform Engineering
member: uid=acct-7f31a2,ou=people,dc=example,dc=org
```

Nếu user được move sang parent khác, giá trị `member` có thể cần cập nhật theo DN mới.

### 8.1. LDAP protocol không bảo đảm mọi DN reference tự đổi

Modify DN đổi tên hoặc vị trí entry được chỉ định. Nó không có nghĩa mọi ứng dụng, cache, database hoặc mọi attribute DN-valued trong toàn directory đều tự được cập nhật.

Tùy server và cấu hình:

- Có thể có cơ chế referential integrity tự cập nhật attribute tham chiếu.
- Có thể cần ứng dụng hoặc provisioning service cập nhật reference.
- Có thể có backlink/linked attribute do server quản lý.
- Có thể có dữ liệu tham chiếu ngoài directory mà server không biết.

Đừng giả định một hành vi OpenLDAP cũng đúng với Active Directory hoặc LDAP appliance khác.

### 8.2. OpenLDAP refint overlay là một ví dụ server-specific

OpenLDAP có `refint` overlay để duy trì một số attribute tham chiếu chứa DN. Khi entry bị rename hoặc delete, overlay có thể tìm các giá trị DN trỏ tới entry đó và cập nhật/xóa reference.

Ví dụ cấu hình:

```text
overlay refint
refint_attributes member manager
```

Các attribute được cấu hình phải có distinguishedName syntax. `refint` là tính năng phải được administrator cấu hình và kiểm thử; nó không phải hành vi tự động của mọi LDAP server.

Một số schema như `groupOfNames` yêu cầu ít nhất một `member`. Nếu việc xóa reference làm mất giá trị cuối cùng, cần cấu hình/policy phù hợp, ví dụ `refint_nothing`, thay vì giả định group có thể rỗng.

### 8.3. Active Directory có stable objectGUID

Trong Active Directory Domain Services, `objectGUID` là identifier do server cấp và không đổi khi object được rename hoặc move. Microsoft khuyến nghị ứng dụng lưu reference tới object bằng `objectGUID` thay vì DN nếu reference phải sống qua rename/move.

Tuy nhiên:

- `objectGUID` là identifier server-managed, không phải naming attribute để ứng dụng tự gán.
- DN vẫn cần thiết cho nhiều LDAP operation.
- Khi cần thao tác theo DN, ứng dụng phải resolve objectGUID sang DN hiện tại theo API/LDAP query phù hợp.
- Các directory khác có thể có identifier khác; không giả định `objectGUID` tồn tại ở OpenLDAP.

### 8.4. Không dùng group DN hoặc member DN làm business key

Ở tầng database/event, ưu tiên lưu:

```text
groupId: grp-01J8D2
personId: acct-7f31a2
membershipState: PRESENT
```

Khi ghi vào LDAP, resolve stable identity thành DN hiện tại rồi đặt vào `member`. Điều này tách business relationship khỏi địa chỉ hiện tại của entry.

Nếu nguồn authoritative là LDAP, cần có chiến lược tìm stable ID và đồng bộ lại các DN references sau rename/move. Nếu nhiều hệ thống cùng ghi membership, xác định rõ owner và conflict policy.

## 9. Rename và move theo LDAP Modify DN

LDAPv3 định nghĩa Modify DN operation để:

- Đổi RDN của entry.
- Move entry sang parent mới.
- Move một subtree tới vị trí mới.

Request có các trường:

| Trường | Vai trò |
| --- | --- |
| `entry` | DN hiện tại của entry cần thay đổi |
| `newrdn` | RDN mới |
| `deleteoldrdn` | Có giữ lại giá trị RDN cũ như attribute bình thường hay không |
| `newSuperior` | Parent DN mới nếu thực hiện move |

### 9.1. Rename RDN

Ví dụ đổi RDN:

```text
Trước:
cn=Alice Nguyen,ou=people,dc=example,dc=org

newrdn:
cn=Alicia Nguyen

Sau:
cn=Alicia Nguyen,ou=people,dc=example,dc=org
```

`newrdn` là RDN, không phải DN đầy đủ.

Nếu `deleteoldrdn=TRUE`, giá trị attribute tạo thành RDN cũ (nếu không còn được dùng bởi RDN mới) sẽ bị xóa khỏi entry. Nếu `FALSE`, giá trị cũ được giữ lại như attribute bình thường.

Ví dụ entry có `cn: Alice Nguyen` và rename sang `cn=Alicia Nguyen`:

- `deleteoldrdn=TRUE`: giá trị `cn: Alice Nguyen` cũ bị loại bỏ nếu không còn là thành phần RDN mới.
- `deleteoldrdn=FALSE`: `cn: Alice Nguyen` có thể được giữ như một giá trị `cn` không còn phân biệt entry.

### 9.2. Move sang parent mới

Ví dụ move user:

```text
DN hiện tại:
uid=acct-7f31a2,ou=people,dc=example,dc=org

Parent mới:
ou=alumni,dc=example,dc=org

DN sau:
uid=acct-7f31a2,ou=alumni,dc=example,dc=org
```

Parent mới phải tồn tại. Server kiểm tra schema và các ràng buộc dữ liệu. LDAP client không nên giả định có thể move tùy ý giữa mọi naming context hoặc giữa các server.

### 9.3. Move và rename cùng lúc

Modify DN có thể đổi RDN và parent trong cùng operation:

```ldif
dn: cn=Alice Nguyen,ou=people,dc=example,dc=org
changetype: modrdn
newrdn: cn=Alicia Nguyen
deleteoldrdn: 1
newsuperior: ou=alumni,dc=example,dc=org
```

Đây là LDIF minh họa Modify DN. Khả năng hỗ trợ move subtree và giới hạn naming context phụ thuộc server.

### 9.4. Không dùng Modify thông thường để xóa giá trị RDN

LDAP Modify không được dùng để xóa distinguished value đang tạo RDN. Muốn rename, dùng Modify DN operation.

Vì vậy, khi entity có `@Id Name dn` và naming attribute nằm trong RDN, một update bình thường cho attribute đó không tương đương với đổi DN. Phải thực hiện rename đúng operation, cập nhật object state và resolve DN mới sau đó.

### 9.5. Không giả định move giữa naming context/server luôn được hỗ trợ

RFC 4511 yêu cầu `newSuperior` tồn tại và nêu rõ client không được kỳ vọng thực hiện mọi kiểu move tùy ý giữa naming context hoặc server. Một số sản phẩm có hỗ trợ mở rộng, nhưng phải kiểm tra riêng.

Nếu cần chuyển dữ liệu giữa hai naming context/server:

1. Xác định stable identity.
2. Export entry và các subordinate cần thiết.
3. Tạo entry ở đích theo schema đích.
4. Xác minh attribute, ACL và membership.
5. Cập nhật các reference theo policy.
6. Chuyển traffic/consumer sang DN mới.
7. Xóa entry cũ sau khi đối soát và có phương án rollback.

Đây là migration workflow nhiều bước, không nên xem như một lệnh rename đơn giản.

## 10. Ví dụ Spring LDAP cho một thao tác move có kiểm soát

Spring LDAP cung cấp API `rename(Name oldDn, Name newDn)` trên `LdapTemplate`. API nhận DN cũ và DN đầy đủ mới.

Ví dụ minh họa:

```java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder
    .newInstance("ou=people")
    .add("uid", "acct-7f31a2")
    .build();

Name newDn = LdapNameBuilder
    .newInstance("ou=alumni")
    .add("uid", "acct-7f31a2")
    .build();

ldapTemplate.rename(oldDn, newDn);
```

Trước khi gọi:

- Xác minh `oldDn` thuộc đúng stable identity.
- Xác minh parent của `newDn` tồn tại.
- Xác minh caller có quyền rename/move.
- Xác minh không có entry đích bị chiếm.
- Xác minh move không vượt naming context/server boundary.
- Xác định cách cập nhật `member`, `manager` và các DN-valued references.
- Chuẩn bị refresh cache và phát event sau khi server xác nhận thành công.

Ví dụ này giả định `ContextSource` đã cấu hình base là `dc=example,dc=org`, vì vậy hai `Name` truyền vào là DN tương đối với base đó. Nếu `ContextSource` không khai báo base, hãy dùng DN đầy đủ cho cả `oldDn` và `newDn`.

## 11. Quy tắc đặt DN khuyến nghị

Có thể dùng checklist sau khi thiết kế naming convention cho một directory mới.

### 11.1. Quy tắc cho user/person

- RDN dùng stable key do tổ chức cấp, không dùng tên hiển thị.
- Nếu `uid` là login name có thể đổi, không coi nó là stable key.
- Email, UPN, display name, department, location và manager là attribute có thể thay đổi.
- Parent OU nên là container ổn định như `ou=people`.
- Stable ID không tái sử dụng cho người khác.
- Nếu directory cung cấp `entryUUID`/`objectGUID`, lưu nó như stable identifier theo khả năng sản phẩm.

### 11.2. Quy tắc cho group

- Group có stable ID riêng.
- Tên hiển thị và mô tả nhóm nằm trong attribute phù hợp.
- Parent OU là container `ou=groups` hoặc boundary ổn định.
- Membership được lưu theo schema/attribute của directory.
- Khi group rename, cập nhật reference và cache theo policy.

### 11.3. Quy tắc cho service account

- Dùng mã service/client ổn định, ví dụ `svcId=payments-api` hoặc `uid=svc-payments-01`.
- Không dùng hostname/pod name có thể thay đổi làm RDN.
- Không dùng secret/password/token trong DN.
- Service account nên nằm trong container ổn định như `ou=service-accounts`.
- Quyền ACL gắn với stable identity và scope rõ ràng.

### 11.4. Quy tắc cho OU/container

- Đặt tên theo boundary lưu trữ, quản trị hoặc replication ổn định.
- Tránh encode tên phòng ban, dự án, chiến dịch tuyển dụng nếu chúng thay đổi thường xuyên.
- Giữ naming context gọn và có kế hoạch partition/replication.
- Nếu cần tách OU, thiết kế migration và cập nhật DN references trước khi triển khai.
- Không tạo nhiều tầng chỉ để mô phỏng sơ đồ tổ chức.

### 11.5. Naming convention mẫu

| Loại entry | RDN đề xuất | Parent ổn định | Thông tin thay đổi lưu ở |
| --- | --- | --- | --- |
| Person | `uid=acct-7f31a2` (nếu uid bất biến) | `ou=people` | `cn`, `mail`, `departmentNumber`, `l` |
| Group | `cn=grp-01J8D2` | `ou=groups` | `description`, display name, owner |
| Service account | `uid=svc-payments-01` | `ou=service-accounts` | description, owner, environment |
| Device | `deviceId=dev-83af` (nếu schema cho phép) | `ou=devices` | hostname, IP, location |
| Tenant | `ou=tenant-4d21` nếu là boundary ổn định | Naming context được thiết kế riêng | tenant display name, contact |

Đây là convention minh họa; tên attribute và object class phải phù hợp schema của directory triển khai.

## 12. Chuyển đổi từ naming convention cũ

Nếu hệ thống đã dùng DN dựa trên tên hoặc phòng ban, không nên đổi hàng loạt trực tiếp trong production.

### Bước 1: Kiểm kê DN và dependency

Tìm các nơi đang lưu hoặc dùng DN:

- `@Id Name dn` trong entity/cache.
- Database foreign key hoặc cột DN.
- Group `member`, `uniqueMember`, `manager` và attribute DN-valued.
- Event payload, queue message, search index.
- ACL/ACI hoặc policy có target DN.
- Application config, provisioning script, scheduled job.
- Monitoring/audit và các hệ thống tích hợp.

Ghi rõ hệ thống nào là owner của từng reference.

### Bước 2: Chọn stable identity và bổ sung trước

- Chọn ID có uniqueness và reuse policy rõ.
- Bổ sung attribute vào schema/entry nếu cần.
- Backfill stable ID cho entry cũ.
- Kiểm tra collision và giá trị thiếu.
- Chặn provisioning tạo entry mới không có stable ID.
- Giữ mapping stable ID → current DN.

### Bước 3: Cập nhật consumer trước khi move

Consumer nên nhận stable ID hoặc resolve DN hiện tại. Nếu consumer vẫn lưu DN cũ, đổi DN trước khi cập nhật consumer có thể làm workflow bị gián đoạn.

Một chiến lược thường dùng:

1. Deploy code có thể đọc stable ID và DN cũ.
2. Backfill mapping.
3. Chuyển consumer sang stable ID.
4. Theo dõi các request vẫn dùng DN cũ.
5. Chỉ sau khi usage giảm về mức chấp nhận được mới bắt đầu rename/move.

### Bước 4: Thực hiện migration theo batch nhỏ

Với từng entry:

1. Resolve stable ID → current DN.
2. Tính DN đích từ naming contract.
3. Kiểm tra parent DN đích tồn tại.
4. Kiểm tra DN đích chưa bị chiếm.
5. Thực hiện Modify DN hoặc migration workflow phù hợp.
6. Đọc lại entry theo stable ID.
7. Xác minh attribute RDN và parent.
8. Kiểm tra group/manager references.
9. Invalidate cache và phát event với stable ID.
10. Ghi audit kết quả.

Không chạy một script move hàng nghìn entry trước khi kiểm thử trên bản sao directory có schema/ACL tương tự.

### Bước 5: Xử lý tham chiếu và rollback

- Kiểm tra referential integrity overlay hoặc linked attribute semantics.
- Đối soát mọi DN reference do ứng dụng quản lý.
- Giữ mapping DN cũ → stable ID → DN mới trong thời gian chuyển đổi.
- Nếu một bước thất bại, dừng batch và xác định entry nào đã move.
- Rollback phải dùng stable ID để nhận diện entry; không chỉ gọi rename ngược theo DN cũ vì DN đó có thể đã được tái sử dụng.
- Không xóa entry cũ trong migration cross-context trước khi xác nhận dữ liệu đích đầy đủ.

## 13. Kiểm thử naming convention và rename/move

Một naming convention cần test ở cả mức Java và LDAP server.

### 13.1. Kiểm thử cấu trúc DN

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Stable ID bình thường | DN đúng parent/RDN |
| Value có dấu phẩy | Builder escape đúng |
| Value có dấu cộng/nháy/backslash | DN parse lại đúng cấu trúc |
| Unicode | DN lưu/đọc nhất quán theo encoding |
| Space đầu/cuối | Escaping đúng theo RFC 4514 |
| `#` đầu value | Escape đúng |
| Duplicate RDN dưới cùng parent | Server từ chối entry collision |
| Cùng RDN ở parent khác | Cho phép nếu naming scope và business contract cho phép |
| Attribute không có trong schema | Add/Modify DN thất bại theo schema |
| Operational attribute làm RDN | Server từ chối nếu không được phép sửa/đặt làm naming value |

### 13.2. Kiểm thử thay đổi nghiệp vụ

| Thay đổi | DN có nên đổi theo convention ổn định? |
| --- | --- |
| Đổi `cn`/display name | Không |
| Đổi email | Không |
| Đổi UPN/login alias | Không, nếu alias không phải stable key |
| Đổi department | Không, nếu OU không encode department |
| Đổi manager | Không |
| Đổi group display name | Không |
| Chuyển trạng thái employee → alumni | Chỉ đổi nếu policy yêu cầu move parent; cần migration/reference plan |
| Chuyển tenant | Có thể đổi nếu tenant là naming boundary; cần migration rõ |
| Rotate service credential | Không |
| Đổi hostname/device IP | Không nếu RDN dùng device stable ID |

### 13.3. Kiểm thử Modify DN

- Rename RDN và xác minh `deleteoldrdn` đúng.
- Move parent và xác minh DN mới.
- Move subtree có subordinate entry.
- Parent đích không tồn tại.
- DN đích đã tồn tại.
- Caller không có quyền rename.
- Move giữa naming context/server không được hỗ trợ.
- Schema không cho phép naming attribute mới.
- `member`, `manager` hoặc reference khác sau rename.
- Cache/entity đã load trước rename có được refresh không.
- Client dùng DN cũ sau rename nhận lỗi gì và có thể resolve lại bằng stable ID không.

### 13.4. Kiểm thử server-specific referential integrity

Nếu dùng OpenLDAP `refint`:

- Cấu hình `refint_attributes` cho đúng attribute có distinguishedName syntax.
- Rename user và xác minh `member`/`manager` được cập nhật.
- Delete user và xác minh reference được xóa.
- Kiểm tra `groupOfNames` khi member cuối cùng bị xóa.
- Xác minh overlay có chạy trên database/backend liên quan.

Nếu dùng Active Directory hoặc directory khác:

- Test linked attributes/backlink theo đúng server.
- Test rename/move trong cùng domain và các boundary được hỗ trợ.
- Kiểm tra `objectGUID` giữ nguyên qua rename/move.
- Không suy ra behavior từ OpenLDAP test fixture.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đổi họ tên làm repository không tìm thấy entry | `cn` là RDN nên DN đã đổi | Tìm theo stable ID, resolve DN mới |
| Chuyển phòng ban làm nhiều service lỗi | Department được encode trong OU | Dùng OU ổn định, department là attribute |
| Group membership trỏ DN cũ | Server không tự cập nhật reference hoặc overlay chưa cấu hình | Dùng referential integrity phù hợp và đối soát |
| `NoSuchObject` sau move | Consumer dùng DN cũ | Resolve current DN bằng stable identity |
| `entryAlreadyExists` khi rename | RDN/parent đích đã có entry | Kiểm tra collision, không ghi đè |
| `notAllowedOnRDN` khi modify | Cố xóa distinguished value bằng Modify | Dùng Modify DN |
| `invalidDNSyntax` | Nối chuỗi DN, thiếu escaping | Dùng `LdapNameBuilder`/`LdapName` |
| DN có ký tự Unicode bị sai | Encoding/escaping hoặc client xử lý chuỗi sai | Test RFC 4514 và UTF-8 |
| Stable ID bị trùng | Không có uniqueness scope hoặc cấp phát tập trung | Enforce uniqueness và collision handling |
| Entry cũ và mới cùng tồn tại sau migration | Chuyển cross-context theo nhiều bước | Dùng migration journal, stable ID và reconciliation |
| Cache trả DN cũ | Cache key là DN hoặc invalidation thiếu | Cache theo stable ID, refresh current DN |
| `entryUUID` không thể dùng làm RDN | Operational attribute không phải user-modifiable naming attribute | Giữ nó làm lookup key, dùng naming attribute được schema cho phép |
| Move subtree thất bại | Parent mới không tồn tại hoặc server không hỗ trợ boundary | Kiểm tra `newSuperior`, naming context và product support |

## 15. Bài thực hành

Một ứng dụng đang lưu user theo DN:

```text
cn=Alice Nguyen,ou=Engineering,ou=HoChiMinh,dc=example,dc=org
```

Database ứng dụng, group membership và cache đều lưu DN này. Alice đổi tên thành Alicia, sau đó chuyển sang phòng ban Platform ở Hà Nội.

**Câu A.** Có bao nhiêu phần của DN thay đổi trong hai sự kiện này?

**Câu B.** Vì sao `cn` và OU theo department/location làm tăng chi phí vận hành?

**Câu C.** Hãy đề xuất một stable ID và DN mới ít phụ thuộc thông tin nghiệp vụ.

**Câu D.** Nếu dùng `entryUUID` hoặc `objectGUID`, có thể mặc định đặt nó làm RDN không? Vì sao?

**Câu E.** Khi move entry, vì sao chỉ đổi DN của user chưa chắc đã đủ?

**Câu F.** `deleteoldrdn=TRUE` và `FALSE` khác nhau thế nào?

**Câu G.** Vì sao không thể dùng LDAP Modify thông thường để xóa giá trị đang tạo RDN?

**Câu H.** RFC 4511 có bảo đảm client move entry tùy ý giữa hai naming context/server không?

**Câu I.** Nếu ứng dụng cache `DN → profile`, cần thay đổi cache key/refresh strategy thế nào?

**Câu J.** Khi migration cross-context bị lỗi giữa chừng, vì sao cần stable ID và migration journal?

### Gợi ý đáp án

- **A:** Đổi tên làm thay đổi RDN nếu dùng `cn`; chuyển phòng ban/vị trí làm thay đổi parent OU. Cả hai có thể làm DN đầy đủ đổi.
- **B:** Thông tin đó thường thay đổi; mỗi lần đổi kéo theo Modify DN, reference updates, cache invalidation và consumer migration.
- **C:** Dùng mã bất biến như `uid=acct-7f31a2,ou=people,dc=example,dc=org`; giữ `cn`, email, department và location trong attribute.
- **D:** Không. `entryUUID`/`objectGUID` thường là operational/server-managed identifier; phải kiểm tra schema và khả năng naming. Dùng chúng làm stable lookup key là phù hợp hơn.
- **E:** Các attribute như `member`/`manager`, database, cache và hệ thống ngoài có thể vẫn lưu DN cũ.
- **F:** TRUE xóa giá trị RDN cũ nếu không còn thuộc RDN mới; FALSE giữ giá trị cũ như attribute bình thường.
- **G:** LDAP không cho Modify xóa distinguished value; cần Modify DN operation.
- **H:** Không. RFC nói không được kỳ vọng arbitrary moves giữa naming context/server; parent mới phải tồn tại và server phải hỗ trợ.
- **I:** Dùng stable ID làm cache key, DN là locator có thể refresh/invalidate.
- **J:** Có thể entry đã được tạo/move một phần; journal giúp nhận diện từng identity và resume/rollback có kiểm soát.

## 16. Ghi nhớ cốt lõi

- **DN là địa chỉ trong DIT; stable identity là khóa nhận diện đối tượng.** Đừng dùng DN làm business primary key nếu entry có thể rename/move.
- Chọn RDN dựa trên stable key do tổ chức cấp; chỉ dùng `uid` nếu nó thực sự bất biến theo contract.
- Tên hiển thị, email, UPN, phòng ban, chức danh và vị trí thường nên là attribute có thể thay đổi.
- Thiết kế parent OU theo boundary quản trị/lifecycle ổn định; đừng mã hóa toàn bộ sơ đồ tổ chức vào DN.
- `entryUUID` và `objectGUID` có thể làm stable identifier theo server, nhưng không mặc định là naming attribute.
- Dùng `LdapNameBuilder` thay vì nối chuỗi DN; kiểm thử escaping theo RFC 4514.
- Rename/move dùng Modify DN; hiểu `newrdn`, `deleteoldrdn`, `newSuperior` và giới hạn naming context/server.
- Kiểm tra mọi DN-valued reference, group membership, cache và consumer sau rename/move.
- Dùng server-specific referential integrity như OpenLDAP `refint` khi phù hợp, nhưng luôn kiểm thử trên directory thực tế.
- Khi migration naming convention, triển khai stable ID và cập nhật consumer trước; move theo batch có journal, audit và reconciliation.

## Tài liệu tham khảo

1. [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html) — DIT, Modify DN, `newrdn`, `deleteoldrdn`, `newSuperior` và giới hạn move.
2. [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html) — cú pháp DN, RDN và escaping.
3. [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html) — schema, attribute type, object class và naming context.
4. [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517.html) — syntax và matching rules cho attribute value.
5. [Spring LDAP — LdapNameBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/support/LdapNameBuilder.html) — tạo LdapName/RDN và thứ tự thành phần.
6. [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — ContextSource, LdapTemplate, rename và directory operations.
7. [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository abstraction và Object-Directory Mapping.
8. [Microsoft — Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities) — DN thay đổi theo rename/move, objectGUID ổn định.
9. [Microsoft — Using objectGUID to Bind to an Object](https://learn.microsoft.com/en-us/windows/win32/ad/using-objectguid-to-bind-to-an-object) — dùng GUID để nhận diện/bind object sau rename/move.
10. [OpenLDAP Administrator's Guide — Referential Integrity Overlay](https://www.openldap.org/doc/admin26/overlays.html) — `refint`, `refint_attributes` và cập nhật DN references.
11. [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519.html) — các attribute chuẩn như `uid`, `cn`, `member` và `groupOfNames`.
12. [RFC 4530 — LDAP entryUUID Operational Attribute](https://www.rfc-editor.org/rfc/rfc4530.html) — `entryUUID` là UUID do server cấp, operational, không cho user sửa và bất biến qua rename.
