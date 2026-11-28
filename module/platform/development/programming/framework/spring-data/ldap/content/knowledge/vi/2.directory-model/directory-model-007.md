# Định danh entry bằng DN và phân biệt với tên đăng nhập

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập LDAP directory qua **Spring Data LDAP repository** hoặc **LdapTemplate**. Một entry được đặt ở một vị trí trong cây thư mục, có **distinguished name (DN)**, các **objectClass** và thuộc tính theo schema. Ứng dụng thường còn có một chuỗi mà người dùng nhập để đăng nhập, ví dụ **an**, **an.tran** hoặc **an@example.org**.

Hai thứ này rất dễ bị nhầm: **DN là tên phân biệt của entry trong cây LDAP, còn tên đăng nhập là định danh mà hệ thống chọn để nhận biết người dùng trong quy trình xác thực**. Tên đăng nhập có thể được lưu trong thuộc tính **uid**, **sAMAccountName**, **userPrincipalName** hoặc một thuộc tính khác, tùy LDAP server và chính sách của tổ chức. Chúng **không bắt buộc trùng nhau**.

Bài thuộc chương **Mô hình thư mục**, tập trung vào cách định danh entry bằng DN, sự khác nhau giữa DN và login name, và hậu quả khi đưa hai khái niệm này vào Spring Data LDAP. Sau bài học, bạn có thể:

- Đọc đúng **RDN**, **DN**, **parent DN**, **base DN** và **naming context** trong một cây LDAP.
- Giải thích tại sao **uid=an** trong DN không đồng nghĩa “an” luôn là tài khoản đăng nhập, và tại sao DN có thể bắt đầu bằng **cn** thay vì **uid**.
- Phân biệt **uid**, **cn**, **mail**, **sAMAccountName**, **userPrincipalName (UPN)**, **objectGUID/entryUUID** với DN.
- Chọn đúng cách **lookup theo DN** hoặc **search theo thuộc tính đăng nhập**, thay vì đoán DN từ username.
- Ánh xạ **@Id Name**, **@Entry**, **@Attribute** trong Spring Data LDAP; tìm entry an toàn bằng LdapTemplate.
- Thiết kế luồng xác thực LDAP: **xác định entry ứng với username → xác thực credentials bằng bind an toàn**, không so sánh trực tiếp mật khẩu trong thuộc tính.
- Hiểu vì sao **rename/move entry có thể đổi DN**, nhưng không nhất thiết đổi login name; vì sao một login name có thể không duy nhất toàn directory.
- Kiểm thử DN escaping, LDAP filter escaping, search scope, uniqueness, quyền và kết nối TLS.

## 1. DN định danh entry trong một cây

Ví dụ một directory đơn giản:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=binh
└── ou=groups
    └── cn=backend
~~~

Entry của An có DN đầy đủ:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Đọc DN từ trái sang phải, bắt đầu từ entry cụ thể và lần lượt đi lên các cấp cha:

| Thành phần | Ý nghĩa trong ví dụ | Thuật ngữ |
| --- | --- | --- |
| **uid=an** | Tên của entry An trong phạm vi parent | **Relative Distinguished Name (RDN)** |
| **ou=people** | Entry cha trực tiếp của An | Một RDN của parent |
| **dc=example,dc=org** | Phần suffix đặt tên của directory | **Base/naming context** được cấu hình |
| **uid=an,ou=people,dc=example,dc=org** | Tên phân biệt đầy đủ của An trong naming context | **DN** |

**RDN** thường có dạng **attributeType=value**, chẳng hạn **uid=an**. **DN** nối các RDN theo thứ tự từ entry đi về gốc cây. RDN **uid=an** chưa đủ để định vị entry trên toàn cây: cần biết parent mà nó nằm dưới.

Hai entry có thể dùng cùng RDN ở các parent khác nhau:

~~~text
uid=an,ou=employees,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
~~~

Đây là **hai DN khác nhau**, nên về cấu trúc LDAP là hai entry khác nhau. Trong cùng một parent, hai entry không thể có cùng DN; nhưng LDAP không tự suy từ điều đó rằng thuộc tính **uid** phải duy nhất trên tất cả nhánh.

### 1.1. DN là tên có cấu trúc, không phải đường dẫn filesystem

LDAP DN không giống **/home/people/an**. Thành phần **uid**, **ou**, **dc** là **attribute types** trong LDAP schema, không phải các từ khóa bắt buộc theo một khuôn cây cố định.

Một directory khác có thể đặt tên cho người dùng bằng:

~~~text
cn=An Tran,ou=employees,dc=example,dc=org
~~~

Entry đó vẫn có thể có thuộc tính **uid: an**. Cũng không có quy tắc giao thức nói mọi người dùng phải nằm trong **ou=people** hoặc mọi nhóm phải nằm trong **ou=groups**. Đó là các quy ước quản trị thường gặp và cần phù hợp schema, ACL, ứng dụng.

**DN không phải một thuộc tính thông thường luôn có tên dn.** Trong LDIF, dòng **dn:** chỉ định tên của entry. Nhiều LDAP server còn có thuộc tính operational hoặc thuộc tính riêng của nhà cung cấp biểu diễn DN, nhưng không nên giả định filter **(dn=...)** là cách portable để tìm mọi entry.

### 1.2. DN không phải khóa vĩnh viễn

DN phân biệt entry **tại vị trí hiện tại** của nó. Khi LDAP server cho phép **Modify DN (rename/move)**, DN có thể đổi:

~~~text
Trước:
  uid=an,ou=people,dc=example,dc=org

Sau khi chuyển nhánh:
  uid=an,ou=alumni,dc=example,dc=org
~~~

Entry có thể vẫn là cùng một đối tượng directory theo cơ chế nội bộ của server, nhưng **chuỗi DN đã thay đổi**. Vì vậy DN rất hữu ích để truy cập LDAP hiện tại, nhưng không nên mặc định nó là **business ID bất biến** để lưu lâu dài trong mọi hệ thống.

### 1.3. DN, RDN và base DN khi dùng Spring LDAP

Giả sử **ContextSource** có base:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Khi đó:

| Khái niệm | Giá trị minh họa |
| --- | --- |
| **Server URL** | **ldaps://ldap.example.org:636** |
| **ContextSource base DN** | **dc=example,dc=org** |
| **User DN đầy đủ** | **uid=an,ou=people,dc=example,dc=org** |
| **DN tương đối so với base** | **uid=an,ou=people** |
| **User RDN** | **uid=an** |
| **Bind DN của ứng dụng** | **uid=svc-reader,ou=service-accounts,dc=example,dc=org** |

Trong những ví dụ LdapTemplate bên dưới, **Name** truyền vào lookup thường được tính tương đối với **base DN** đã cấu hình. Đừng truyền cả suffix lần nữa mà vô tình ghép **dc=example,dc=org** hai lần.

**Bind DN của service** là tài khoản ứng dụng dùng để xác thực với directory, không phải base DN và cũng không phải username do người dùng cuối nhập.

## 2. Tên đăng nhập là gì?

**Tên đăng nhập (login name)** là chuỗi mà hệ thống chấp nhận để xác định danh tính của một người cần xác thực. Nó là một phần của **chính sách authentication**, không được định nghĩa duy nhất bởi cấu trúc DN.

Ví dụ người dùng nhập:

~~~text
an
~~~

Tùy thiết kế, hệ thống có thể tìm entry theo:

~~~ldap
(uid=an)
~~~

Một ứng dụng khác cho phép nhập email:

~~~ldap
(mail=an@example.org)
~~~

Một hệ thống Active Directory có thể dùng **sAMAccountName** hoặc **userPrincipalName**; một LDAP server khác lại dùng thuộc tính tùy chỉnh. Việc người dùng nhập **an** không tự tạo ra DN **uid=an,ou=people,dc=example,dc=org**. Ứng dụng chỉ có thể suy DN như vậy nếu **quy ước đặt RDN và vị trí entry được đảm bảo**.

### 2.1. Bảng phân biệt các định danh

| Dữ liệu | Chức năng thường gặp | Có phải DN không? | Những điều không được giả định |
| --- | --- | --- | --- |
| **DN** | Định vị entry trong cây LDAP | **Có** | Bất biến sau rename/move |
| **RDN** | Đặt tên entry trong phạm vi một parent | **Chỉ là phần của DN** | Đủ định vị entry trên toàn directory |
| **uid** | Mã người dùng/định danh tài khoản | **Không; là attribute** | Luôn nằm trong DN, luôn duy nhất toàn cây |
| **cn** | Common name/nhãn người hoặc nhóm | **Không; là attribute** | Luôn là login name hoặc duy nhất |
| **mail** | Địa chỉ email | **Không; là attribute** | Email luôn là khóa đăng nhập hoặc vĩnh viễn |
| **sAMAccountName** | Logon name kiểu cũ của AD | **Không** | Duy nhất toàn forest hoặc bằng RDN |
| **userPrincipalName** | Tên đăng nhập dạng UPN trong AD | **Không** | Luôn bằng email hoặc DNS domain của DN |
| **entryUUID / objectGUID** | Định danh đối tượng do server quản lý, tùy sản phẩm | **Không** | Cùng format, cùng semantics và bất biến qua mọi lần migration |
| **Login name trong UI** | Chuỗi do ứng dụng chấp nhận | **Không nhất thiết** | Chỉ cần nối chuỗi là có ngay DN |

**Không dùng objectGUID hoặc entryUUID như một “công thức DN”.** Các định danh ấy có thể hữu ích làm khóa liên kết ổn định hơn DN cho cùng một directory/server, nhưng cách tồn tại và giữ nguyên qua export/import, migration hoặc xóa rồi tạo lại phải được xác minh riêng.

### 2.2. Một entry có nhiều thuộc tính nhận diện

~~~ldif
dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
givenName: An
mail: an@example.org
~~~

Entry này có:

- **DN**: uid=an,ou=people,dc=example,dc=org.
- **RDN**: uid=an.
- **uid**: an.
- **cn**: An Tran.
- **mail**: an@example.org.

Nếu chính sách đăng nhập dùng uid, tên đăng nhập sẽ là **an**. Nếu chính sách dùng email, tên đăng nhập có thể là **an@example.org**. **DN không đổi chỉ vì ứng dụng đổi trường được chấp nhận làm login name**.

Ngược lại, một directory có thể có entry:

~~~ldif
dn: cn=An Tran,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
~~~

Lúc này **uid** vẫn có thể được dùng làm login name, nhưng **DN bắt đầu bằng cn**, nên lookup **uid=an,ou=people** sẽ không tìm thấy entry đó.

## 3. Schema và cấu trúc tên không xác định phương thức đăng nhập

**objectClass** quyết định tập thuộc tính được phép/bắt buộc theo schema; **DN** định vị entry; **username** do cơ chế authentication của ứng dụng hoặc sản phẩm LDAP quyết định.

| Object class | Vai trò thường gặp | Thuộc tính cần lưu ý |
| --- | --- | --- |
| **domain** | Entry nhánh domain component | **dc** |
| **organizationalUnit** | Entry đơn vị tổ chức | **ou** |
| **person** | Entry về người | **cn**, **sn** bắt buộc |
| **organizationalPerson** | Mở rộng **person** | Kế thừa các yêu cầu của person |
| **inetOrgPerson** | Hồ sơ người dùng mở rộng | Có thể lưu **uid**, **mail**; kế thừa **cn**, **sn** |
| **groupOfNames** | Nhóm thành viên | **cn**, **member** bắt buộc |

Ví dụ hai entry đều là **inetOrgPerson**, nhưng một entry dùng **uid** làm RDN, entry kia dùng **cn**. **objectClass giống nhau không bảo đảm tên RDN giống nhau**.

Mặt khác, entry có RDN **uid=...** không chắc là một tài khoản được phép login: nó có thể là tài khoản dịch vụ, một record dùng làm tham chiếu hoặc entry với chính sách xác thực bị vô hiệu hóa.

Việc login thành công còn phụ thuộc password/credential policy, trạng thái account, ACL và cơ chế authentication của directory. **Không suy ra người dùng có quyền đăng nhập chỉ từ việc tìm thấy (uid=an)**.

## 4. DN có thể thay đổi mà username vẫn giữ nguyên

Ví dụ người dùng An được chuyển từ nhân viên chính thức sang nhánh cựu nhân viên:

~~~text
Old DN: uid=an,ou=employees,dc=example,dc=org
New DN: uid=an,ou=alumni,dc=example,dc=org
Login attribute: uid=an
~~~

Trong mô hình này:

- **DN đổi**, vì entry đổi parent.
- Thuộc tính **uid** có thể vẫn là **an**.
- Nếu ứng dụng hardcode **ou=employees**, lookup theo DN cũ sẽ thất bại.
- Nếu ứng dụng tìm trong một search base bao phủ cả hai nhánh và kiểm tra identity theo policy, nó có thể tìm thấy entry ở DN mới.

Ở chiều ngược lại, một tổ chức có thể đổi login name **an** thành **an.tran** mà không đổi DN, nếu **uid** không được chọn làm RDN và schema/policy cho phép. Nếu **uid chính là RDN**, đổi uid thường cần thao tác **Modify DN/rename** hoặc quy trình đồng bộ giá trị RDN theo quy tắc server, chứ không chỉ cập nhật một Java field.

### 4.1. DN trong tham chiếu nhóm

Một nhóm LDAP **groupOfNames** thường lưu **DN đầy đủ** trong thuộc tính **member**:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=people,dc=example,dc=org
~~~

**member** không lưu login name **an**; nó lưu một **giá trị có cú pháp DN**. Nếu user bị rename/move, server có thể hỗ trợ referential integrity để cập nhật các tham chiếu, hoặc ứng dụng/quản trị viên phải xử lý. **Không mặc định mọi LDAP server tự cập nhật mọi thuộc tính tham chiếu sau rename**.

Trong Spring LDAP, cũng cần phân biệt:

~~~text
LdapTemplate target DN (relative): cn=backend,ou=groups
member attribute value (full DN):  uid=an,ou=people,dc=example,dc=org
~~~

Cắt suffix khỏi **member** chỉ vì LdapTemplate đã cấu hình base sẽ làm sai nội dung tham chiếu.

## 5. Tên đăng nhập có thể không duy nhất theo phạm vi bạn tìm

Ví dụ:

~~~text
uid=an,ou=employees,dc=example,dc=org
uid=an,ou=contractors,dc=example,dc=org
~~~

Hai entry có thể đều mang **uid: an** nhưng DN khác nhau. Truy vấn **(uid=an)** từ **dc=example,dc=org** với scope SUBTREE có thể trả **hai kết quả**.

Nếu ứng dụng dùng uid làm username, phải quy định:

1. Username được coi là duy nhất trong **nhánh nào**?
2. Có thể trùng giữa các tenant, domain hoặc OU không?
3. Nếu tìm thấy 0 entry thì xử lý thế nào?
4. Nếu tìm thấy hơn 1 entry, liệu đó là lỗi cấu hình/chính sách? **Không chọn phần tử đầu tiên một cách tùy ý**.
5. Cơ chế nào đảm bảo uniqueness khi hai worker đồng thời tạo tài khoản (policy directory, constraint/index, quy trình cấp username)?

Một **equality index** cho uid giúp tìm nhanh nhưng **không tự biến uid thành unique attribute toàn directory**. Tương tự, dùng **findByUid** trong repository không bảo đảm sẽ trả đúng một entry nếu directory không có uniqueness constraint phù hợp.

### 5.1. Active Directory: phân biệt UPN, sAMAccountName và DN

Trong Active Directory Domain Services, một người dùng có thể có DN dạng:

~~~text
CN=An Tran,OU=Employees,DC=corp,DC=example,DC=org
~~~

và những thuộc tính liên quan đăng nhập:

~~~text
sAMAccountName: an
userPrincipalName: an@corp.example.org
distinguishedName: CN=An Tran,OU=Employees,DC=corp,DC=example,DC=org
~~~

**sAMAccountName** thường là tên đăng nhập tương thích cơ chế cũ, có phạm vi gắn với domain. **userPrincipalName** có dạng giống email nhưng **không nhất thiết bằng địa chỉ mail**, không nhất thiết có suffix trùng với DN domain. **distinguishedName** là DN của object, không phải cùng loại với hai thuộc tính login trên.

Một số AD authentication API chấp nhận UPN hoặc cú pháp **DOMAIN\\username** làm tên đăng nhập trong những hoàn cảnh nhất định. **Không coi khả năng đó là quy tắc portable của LDAP simple bind**: theo LDAP protocol, bind name thông thường là DN; ứng dụng cần sử dụng API và cách cấu hình phù hợp với directory đích.

**objectGUID** hoặc objectSID có thể hữu ích khi đồng bộ định danh AD, nhưng cách cấp, biểu diễn và ổn định khi migration phải được kiểm chứng riêng. Với OpenLDAP, thuộc tính **entryUUID** có thể đóng vai trò tương tự theo đặc điểm sản phẩm, không đồng nhất format và vòng đời với AD.

## 6. Hai thao tác khác nhau: lookup DN và search username

Khi đã biết **DN hợp lệ của một entry**, lookup trực tiếp:

~~~text
lookup(uid=an,ou=people) -> entry An (nếu DN đúng và tồn tại)
~~~

Khi chỉ có username, phải biết **nó nằm ở attribute nào** rồi tìm:

~~~text
username "an"
  -> search subtree dưới OU đã được chỉ định với filter (uid=an)
  -> nhận entry tương ứng và DN thực tế
  -> xử lý nghiệp vụ hoặc xác thực theo chính sách
~~~

Một filter **(uid=an)** là điều kiện trên **thuộc tính uid**, không phải một lời yêu cầu tìm các DN bắt đầu bằng **uid=an**. Vì vậy query theo uid vẫn tìm được entry có DN bắt đầu bằng **cn=An Tran** nếu entry chứa **uid: an** và thuộc phạm vi search.

| Trường hợp | Cách hợp lý |
| --- | --- |
| Đã biết DN được xác minh | **ldapTemplate.lookup(Name, mapper)** |
| Có username nhưng không rõ DN | **LdapTemplate.search** hoặc repository finder theo đúng login attribute |
| Có UID và biết chắc RDN = uid dưới một parent cố định | Có thể xây DN bằng **LdapNameBuilder**, nhưng giả định phải được hợp đồng directory bảo đảm |
| Directory thay đổi OU theo phòng ban | Search đúng subtree hoặc dùng định danh ổn định kèm cơ chế phân giải DN |
| Cần xác thực password | **LDAP bind xác thực** (hoặc Spring Security LDAP), không chỉ search tìm thấy entry |
| Cần kiểm tra thành viên nhóm | Đọc **member/uniqueMember** theo DN và schema, không so username đơn thuần |

### 6.1. Luồng tìm tên đăng nhập tới DN

~~~mermaid
flowchart TD
    A["Người dùng nhập username"] --> B["Xác định login attribute được phép"]
    B --> C["LDAP search: base, scope, filter an toàn"]
    C --> D{"Số entry tìm được"}
    D -->|0| E["Không tìm thấy / thông điệp chung cho login"]
    D -->|1| F["Entry đã được xác định cùng DN thật"]
    D -->|Nhiều| G["Từ chối ambiguity; kiểm tra uniqueness/policy"]
    F --> H["Nghiệp vụ đọc entry hoặc LDAP bind xác thực"]
    H --> I{"Credentials và policy hợp lệ?"}
    I -->|Có| J["Đăng nhập/đọc dữ liệu thành công"]
    I -->|Không| K["Thất bại xác thực an toàn"]
~~~

Ở luồng login công khai, lỗi **“không có tài khoản”** và **“mật khẩu sai”** thường nên dùng thông điệp chung để hạn chế **account enumeration**. Các trạng thái như tài khoản bị khóa hoặc không đủ điều kiện có thể được phân loại nội bộ mà không phải tiết lộ chi tiết cho mọi client.

## 7. Chuẩn bị Spring Boot và LDAP directory mẫu

Ví dụ Java 17+, Spring Boot 3.x hoặc phiên bản tương thích với Spring Data LDAP được chọn:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Đối với ứng dụng có endpoint HTTP, thêm starter Web và cơ chế bảo mật HTTP phù hợp; chúng không tự xuất hiện chỉ vì đã thêm Spring Data LDAP.

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-reader,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**spring.ldap.base** chỉ định base DN; **spring.ldap.username/password** là credentials của **service account** để ứng dụng có thể tìm entry. Người dùng cuối **không đăng nhập bằng cách cung cấp base DN này**.

Ví dụ dữ liệu cho các bài thực hành chính:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org

dn: cn=Binh Le,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Le
sn: Le
mail: binh@example.org
~~~

Hai entry người dùng cùng loại **inetOrgPerson** nhưng **An có RDN uid**, còn **Binh có RDN cn**. Phần mềm có thể tìm cả hai qua **(uid=...)**, miễn base/scope hợp lệ. Nếu lookup trực tiếp, phải truyền **DN tương đối đúng với entry thực tế**.

**Đừng nạp lại suffix hoặc OU nếu server test đã có chúng.** Dữ liệu ví dụ chỉ dùng trên directory kiểm thử phù hợp với schema và quyền, không thay đổi directory sản xuất.

### 7.1. Vì sao phải dùng LDAPS?

LDAP simple bind với mật khẩu phải được bảo vệ bằng kết nối mã hóa đáng tin cậy (LDAPS hoặc StartTLS đã xác minh CA/hostname). Dùng **ldaps://** không tự đảm bảo đúng nếu ứng dụng cố tình tắt kiểm tra certificate; JVM cần truststore và hostname verification phù hợp. Không ghi mật khẩu thật trong source, shell history hay log.

Tài khoản service nên có quyền **đọc đúng các nhánh/thuộc tính cần thiết**, không phải quyền quản trị toàn directory. Quyền tạo/sửa nhóm và quyền xác thực người dùng cuối cần được thiết kế riêng.

## 8. LdapTemplate: lookup bằng DN, search bằng username

### 8.1. Lookup khi đã có DN đúng

Trong trường hợp chắc chắn entry An có DN tương đối **uid=an,ou=people**:

~~~java
package org.example.directory;

import javax.naming.Name;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public String getCommonNameAtKnownDn(String username) {
        validateUsername(username);

        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", username)
                .build();

        return ldapTemplate.lookup(
                dn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get());
    }

    private static void validateUsername(String username) {
        if (username == null
                || !username.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Tên đăng nhập không hợp lệ");
        }
    }
}
~~~

**Cảnh báo:** phương thức này **giả định naming convention** mà ví dụ đã mô tả: RDN user là **uid** ngay dưới **ou=people**. Với entry Binh có DN **cn=Binh Le,ou=people**, gọi lookup **uid=binh,ou=people** sẽ thất bại dù **uid: binh** tồn tại.

**LdapNameBuilder** xử lý cú pháp DN và escaping. Nó không chứng minh DN được xây là tên thật của user; xác minh naming convention là vấn đề khác.

### 8.2. Search theo thuộc tính, lấy DN thực tế

Khi không thể đoán DN từ username, dùng **LdapQueryBuilder** với **LdapTemplate.search**:

~~~java
package org.example.directory;

import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

record ResolvedDirectoryUser(
        Name relativeDn,
        String uid,
        String commonName) {}

@Service
public class DirectoryIdentityResolver {
    private final LdapTemplate ldapTemplate;

    public DirectoryIdentityResolver(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public ResolvedDirectoryUser resolveByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        List<ResolvedDirectoryUser> matches =
                ldapTemplate.search(
                    query()
                        .base("ou=people")
                        .searchScope(SearchScope.SUBTREE)
                        .attributes("uid", "cn")
                        .countLimit(10)
                        .timeLimit(2000)
                        .where("objectClass").is("inetOrgPerson")
                        .and("uid").is(uid),
                    (ContextMapper<ResolvedDirectoryUser>) raw -> {
                        DirContextOperations entry =
                                (DirContextOperations) raw;
                        return new ResolvedDirectoryUser(
                                entry.getDn(),
                                entry.getStringAttribute("uid"),
                                entry.getStringAttribute("cn"));
                    });

        if (matches.isEmpty()) {
            return null;
        }
        if (matches.size() != 1) {
            // Không được chọn kết quả đầu tiên để xác thực.
            throw new IllegalStateException(
                    "Username không duy nhất trong phạm vi tìm");
        }
        return matches.get(0);
    }
}
~~~

Các điểm quan trọng:

1. **Filter (uid=...)** tìm thuộc tính **uid**, không phụ thuộc RDN là **uid** hay **cn**.
2. **ContextMapper** đọc **getDn()**, giúp giữ DN mà LDAP trả về thay vì dựng nó từ username. Theo cách cấu hình ví dụ, DN của adapter thường là **tương đối với ContextSource base**; phải kiểm tra điều này khi đưa DN sang API khác.
3. **LdapQueryBuilder** escape giá trị filter theo ngữ cảnh LDAP; không nối chuỗi raw input.
4. **SUBTREE** bao phủ OU con trong **ou=people**, nhưng có thể cần kiểm soát phạm vi, chỉ mục và các giới hạn tìm kiếm cho directory lớn.
5. **timeLimit/countLimit** không bảo đảm server sẽ trả tập kết quả đầy đủ. Nếu bị size/time limit hoặc lỗi referral, không được giả vờ đó là một danh sách rỗng hay đúng một kết quả.
6. **Username trùng phải được từ chối** ở bước identity resolution hoặc giải quyết bằng chính sách rõ ràng (tenant/domain/base tương ứng), không chọn tùy ý **matches.get(0)**.

**Ghi chú về API:** trong service production có thể dùng **Optional<ResolvedDirectoryUser>** thay vì trả null khi không tìm thấy. Ví dụ chọn null để tách rõ hai tình huống **không có kết quả** và **không duy nhất** trong luồng giải thích.

### 8.3. Đọc tiếp bằng DN vừa phân giải

Khi đã lấy được **relativeDn** từ kết quả search, không cần dựng lại **uid=...**:

~~~java
ResolvedDirectoryUser resolved = resolver.resolveByUid("binh");
if (resolved == null) {
    throw new IllegalArgumentException("Không tìm thấy người dùng");
}

String displayName = ldapTemplate.lookup(
        resolved.relativeDn(),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get());
~~~

Đoạn code ở đây minh họa logic trong một service đã có **resolver** và **ldapTemplate**. Với fixture mẫu, **resolved.relativeDn()** của Binh tương ứng với **cn=Binh Le,ou=people**, không phải **uid=binh,ou=people**.

Nếu object bị rename **sau khi search nhưng trước lookup**, lookup có thể trả **NameNotFoundException**. Hãy xử lý tình huống race thay vì tin DN đã đọc luôn có hiệu lực vô thời hạn.

## 9. Xác thực: tìm thấy entry chưa có nghĩa đăng nhập thành công

Để đăng nhập bằng LDAP, ứng dụng thường cần hai việc:

1. **Xác định tài khoản** tương ứng với login name theo chính sách, đúng search base và filter.
2. **Xác thực credential** bằng cơ chế LDAP đã được cấu hình an toàn, thường là bind với DN của entry được tìm hoặc một cơ chế được LDAP server hỗ trợ.

**Không làm điều này:**

~~~java
// SAI về bảo mật và tính đúng đắn:
boolean authenticated = !ldapTemplate.search(
        query().base("ou=people").where("uid").is(username),
        (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()).isEmpty();
~~~

Code chỉ chứng minh **có entry mang uid tương ứng**, không chứng minh người dùng biết mật khẩu.

Cũng không nên đọc thuộc tính **userPassword** rồi tự so sánh chuỗi với password người dùng nhập. Directory có thể dùng hash, cơ chế xác thực khác hoặc không cho đọc thuộc tính bí mật; xác thực phải do server thực hiện.

### 9.1. LdapTemplate.authenticate với query

Spring LDAP cung cấp API **authenticate(LdapQuery, String)**, dùng truy vấn để tìm entry rồi xác thực qua LDAP:

~~~java
package org.example.directory;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class LdapLoginService {
    private final LdapTemplate ldapTemplate;
    private final DirectoryIdentityResolver resolver;

    public LdapLoginService(
            LdapTemplate ldapTemplate,
            DirectoryIdentityResolver resolver) {
        this.ldapTemplate = ldapTemplate;
        this.resolver = resolver;
    }

    public boolean checkCredentials(
            String username, String password) {
        if (username == null
                || !username.matches("[A-Za-z0-9._-]{1,64}")) {
            return false;
        }
        // Không để password rỗng biến thành anonymous bind
        // ở những LDAP server có chính sách đặc thù.
        if (password == null || password.isEmpty()) {
            return false;
        }

        // Kiểm tra chính sách username chỉ có một entry.
        // Trong sản phẩm thật có thể có thêm điều kiện tenant/OU.
        ResolvedDirectoryUser user = resolver.resolveByUid(username);
        if (user == null) {
            return false;
        }

        return ldapTemplate.authenticate(
                query()
                    .base("ou=people")
                    .where("uid").is(username),
                password);
    }
}
~~~

**Cần hiểu phạm vi ví dụ:** đoạn này mô tả API xác thực của Spring LDAP, không phải hệ thống đăng nhập production hoàn chỉnh. Việc kiểm tra duy nhất rồi tiếp tục dùng query có **hai thao tác**; nếu directory thay đổi giữa hai lần, vẫn có race condition. Trong hệ thống thật, nên dùng **Spring Security LDAP** và một cấu hình **user search/bind** có giới hạn/uniqueness được đảm bảo, kết hợp policy cho account disabled, locked, group mapping, session/token, rate limiting và audit.

Nếu LDAP server hỗ trợ bind bằng một identifier khác DN (như một số dạng UPN trên AD), đó là **cơ chế đặc thù của server**, không biến username thành DN theo quy tắc LDAP portable. Đừng xây bind DN bằng phép nối chuỗi **"uid=" + username + ",..."** khi naming convention không được xác minh.

### 9.2. Service bind và user bind là hai danh tính khác nhau

| Ngữ cảnh | Đang xác thực ai? | Dùng để làm gì? | Lỗi credential nên hiểu ra sao? |
| --- | --- | --- | --- |
| **Service bind** | Tài khoản dịch vụ từ cấu hình ứng dụng | Tìm kiếm directory, đọc attribute, ghi nếu được cấp quyền | Sai password là **sự cố tích hợp/cấu hình**, không phải lỗi 401 của caller |
| **User bind** | Người dùng đang đăng nhập | Xác minh password/credential theo directory | Thất bại có thể là lỗi xác thực của người dùng; không lộ chi tiết nhạy cảm |

**LDAP result 49 (invalidCredentials)** không tự nói đó là lỗi service bind hay user bind. Ứng dụng phải biết operation đang làm gì để ánh xạ sang kết quả nghiệp vụ/HTTP phù hợp.

### 9.3. Không để search base biến thành quyền truy cập

Base DN **ou=people** giúp giới hạn nơi tìm người dùng nhưng **không tự thay thế ACL**. Nếu service account nhìn thấy nhiều tài khoản hơn yêu cầu, ứng dụng vẫn phải kiểm soát quyền HTTP và giới hạn những thao tác LDAP được phép.

Trong luồng đăng nhập, tránh log raw password, DN đầy đủ, filter chứa dữ liệu cá nhân hoặc thông điệp lỗi của server có thể làm lộ trạng thái tài khoản. Dùng thông điệp chung và correlation ID cho vận hành.

## 10. Spring Data LDAP repository: @Id giữ DN, không giữ username

Khi ánh xạ entry thành object Java, Spring Data LDAP thường dùng **@Id** kiểu **javax.naming.Name** cho DN và **@Attribute** cho login attribute:

~~~java
package org.example.directory.entry;

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
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String username;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUsername() { return username; }
    public void setUsername(String username) {
        this.username = username;
    }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Repository:

~~~java
package org.example.directory.repository;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.example.directory.entry.PersonEntry;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUsername(String username);
}
~~~

**findByUsername** là derived query dựa trên **property Java username**, được **@Attribute(name="uid")** ánh xạ sang thuộc tính LDAP **uid**. Nó **không tra cứu DN theo uid-RDN**. Vì thế repository có thể tìm thấy entry Binh đặt RDN **cn** nhưng chứa thuộc tính **uid: binh**.

**@Id Name dn** biểu diễn danh tính/đường dẫn LDAP để thao tác với entry; nó **không tự bằng property username**. Cũng không dùng generic kiểu JPA **LdapRepository<PersonEntry, Long>**, vì Spring Data LDAP **LdapRepository<T>** đã sử dụng cách định danh DN của LDAP.

### 10.1. Vì sao thường trả List thay vì Optional?

Nếu directory không có ràng buộc uniqueness cho uid trong phạm vi query, có thể có nhiều entry cùng username. Chữ ký:

~~~java
List<PersonEntry> findByUsername(String username);
~~~

giúp ứng dụng phát hiện **0, 1 hoặc nhiều entry**. Trả **Optional<PersonEntry>** phù hợp khi hệ thống đã **bảo đảm** uniqueness ở mức directory/policy và query scope; không chọn Optional chỉ vì muốn tin một login name luôn duy nhất.

### 10.2. Các hạn chế khi dùng DN trong CRUD

Repository **findById** tra theo **DN/Name**; finder **findByUsername** tra theo **LDAP attribute**. Khi đổi RDN hoặc di chuyển entry:

- DN trong **@Id** có thể cần được cập nhật bằng thao tác **Modify DN/rename** phù hợp.
- Không nên gọi một phương thức **save** trên entity đã đổi trường username và kỳ vọng server tự rename entry trong mọi trường hợp.
- Nếu entry đang được nhóm tham chiếu bằng full DN, phải quản lý việc cập nhật tham chiếu theo khả năng server.
- Nếu đồng bộ với database quan hệ, cân nhắc dùng **ID ổn định riêng** (kèm policy) thay vì lưu DN làm khóa bất biến.

**Spring Data LDAP repository không tạo/định nghĩa schema**. Một entry inetOrgPerson vẫn cần **cn**, **sn** và các objectClass hợp lệ; lỗi schema được LDAP server xử lý kể cả khi Java entity có getters/setters hoàn chỉnh.

## 11. Định danh dài hạn: DN, username và stable ID

Trong các hệ thống tích hợp LDAP với ứng dụng khác, cần phân biệt **khóa truy cập LDAP** với **khóa nghiệp vụ của một người**.

| Nhu cầu | Lựa chọn nên cân nhắc | Rủi ro cần quản lý |
| --- | --- | --- |
| Lookup entry vừa search | **DN thật** do directory trả về | Có thể đổi sau rename/move |
| Đăng nhập | **uid/UPN/sAMAccountName** theo chính sách | Có thể trùng, đổi tên, tái sử dụng hoặc khác phạm vi |
| Lưu khóa liên kết trong DB | ID ứng dụng bất biến hoặc **server-managed ID** đã xác minh | Migration, xóa/tạo lại, chuyển directory |
| Group membership | **Full DN** trong **member/uniqueMember**, theo schema | DN của member có thể đổi |
| Đồng bộ đa-directory | **Directory alias + stable identity**/mapping đã quản trị | DN hoặc username giống nhau ở hai server khác nhau |

### 11.1. Một DN có thể tồn tại ở nhiều LDAP server

Giả sử hai LDAP server độc lập đều dùng suffix **dc=example,dc=org** và đều có:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Hai entry này **không mặc nhiên là cùng một người**, vì chúng thuộc hai directory độc lập. Một khóa đồng bộ nên gắn với **directory identity/tenant** và ID của entry theo chính sách, thay vì giả định chỉ chuỗi DN luôn duy nhất trên mọi hệ thống.

### 11.2. Không coi email là khóa bất biến

Địa chỉ **mail** có thể thay đổi khi nhân viên đổi tên, domain hoặc công ty. Một số tổ chức còn cho phép nhiều địa chỉ/alias cho cùng người dùng. Nếu ứng dụng dùng email làm login, phải có chính sách uniqueness, xác minh quyền sở hữu và quy trình đổi email an toàn.

Không tự suy **UPN == mail** trong Active Directory. UPN có thể trông giống email nhưng có mục đích authentication, suffix và chính sách riêng. Cũng không giả định **uid** hay **sAMAccountName** được bảo vệ khỏi tái sử dụng sau khi tài khoản cũ bị xóa.

### 11.3. Rename/move ảnh hưởng đến cache và khóa ngoại

Nếu lưu **DN** trong database, URL hoặc cache:

~~~text
app_user.ldap_dn = uid=an,ou=people,dc=example,dc=org
~~~

thì sau khi directory move entry sang **ou=alumni**, giá trị đã lưu có thể trở thành **stale**. Những lựa chọn khắc phục:

- Lưu **opaque application user ID** và ánh xạ sang directory identity theo một quy trình đồng bộ có version.
- Nếu directory cung cấp ID server-managed có đặc tính ổn định phù hợp, lưu ID đó cùng **directory alias**; giải quyết DN hiện tại khi cần LDAP operation.
- Cập nhật hoặc vô hiệu cache DN khi xử lý rename/move.
- Đọc lại trạng thái khi phát sinh **NameNotFoundException**, tránh kết luận user đã bị xóa ngay khi chỉ có DN cũ.
- Xử lý membership/reference DN theo khả năng directory hoặc logic đồng bộ.

Không có lựa chọn nào loại bỏ hoàn toàn race condition khi LDAP entry có thể bị đổi tên đồng thời. Thiết kế phải cân nhắc snapshot, retry và idempotency trong phạm vi nghiệp vụ.

## 12. DN escaping khác LDAP filter escaping

DN là một **tên phân cấp** theo RFC 4514; filter là **biểu thức tìm kiếm** theo RFC 4515. Chúng dùng cú pháp escaping khác nhau.

### 12.1. Dấu phẩy trong RDN

Nếu tên hiển thị chứa dấu phẩy:

~~~text
cn=Tran\, An,ou=people,dc=example,dc=org
~~~

thì dấu phẩy đã escape thuộc **giá trị cn**; dấu phẩy còn lại phân tách RDN. Không tạo DN bằng phép nối chuỗi:

~~~java
// Không an toàn: input có thể phá vỡ cấu trúc DN.
String unsafeDn =
        "cn=" + userInput + ",ou=people,dc=example,dc=org";
~~~

Hãy dùng API:

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

String displayName = "Tran, An";

Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("cn", displayName)
        .build();
// DN tương đối được escaping đúng theo cú pháp DN.
~~~

**LdapNameBuilder** chỉ giải quyết **cách viết DN**, không chứng minh entry có DN đó tồn tại hoặc user đang được phép nằm dưới parent ấy. Đừng chấp nhận parent DN tùy ý do request đưa vào để thao tác ra ngoài subtree được cấp quyền.

### 12.2. Dấu sao trong LDAP filter

~~~ldap
(uid=an)        # uid so khớp an
(uid=an*)       # uid có tiền tố an
(uid=an\2a)     # uid chứa ký tự * literal ở vị trí cuối
~~~

Dấu sao không escape có ý nghĩa wildcard trong filter. Nếu người dùng nhập giá trị **an*** mà ứng dụng tìm chính xác login name đó, không được dùng nối chuỗi:

~~~java
// SAI: ký tự do người dùng nhập có thể thay đổi ý nghĩa filter.
String unsafeFilter = "(uid=" + userInput + ")";
~~~

Thay bằng:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

ldapTemplate.search(
        query().base("ou=people")
               .where("uid").is(userInput),
        (org.springframework.ldap.core.AttributesMapper<String>)
                attrs -> (String) attrs.get("cn").get());
~~~

**LdapQueryBuilder** thực hiện escaping giá trị filter; còn **tên thuộc tính** phải được ứng dụng chọn cố định hoặc đưa vào allowlist đáng tin cậy. Không cho client gửi tên attribute, filter operator, search base hoặc raw LDAP filter rồi chạy không kiểm soát.

### 12.3. Chuẩn hóa không thay thế kiểm tra uniqueness

DN và các attribute có matching rules do LDAP schema/server quyết định, bao gồm những quy tắc về case folding, khoảng trắng và so khớp chuỗi. **Không dùng phép String.equals của Java để suy tính đồng nhất của hai DN**.

Khi cần làm việc với DN trong code Java, dùng **javax.naming.ldap.LdapName**, **Rdn** hoặc **LdapNameBuilder** thay vì tự split theo dấu phẩy:

~~~java
import javax.naming.ldap.LdapName;

LdapName dn = new LdapName(
        "cn=Tran\\, An,ou=people,dc=example,dc=org");

System.out.println(dn.size()); // Số RDN, không phải số dấu phẩy thô.
~~~

Tuy nhiên, so sánh **LdapName.equals** trong Java cũng không thay thế hoàn toàn matching rules hoặc định danh nội bộ của LDAP server. Khi nghiệp vụ yêu cầu xác định cùng một object qua rename/migration, cần ID/server metadata thích hợp.

## 13. Search scope ảnh hưởng tới kết quả của username

Directory có thể tổ chức hồ sơ người dùng dưới nhiều OU:

~~~text
dc=example,dc=org
└── ou=people
    ├── uid=an
    ├── cn=Binh Le
    └── ou=contractors
        └── uid=chi
~~~

| Base DN cho thao tác search | Scope | Những entry user có thể tìm được |
| --- | --- | --- |
| **ou=people** | **OBJECT** | Chỉ chính entry OU, không phải các user con |
| **ou=people** | **ONELEVEL** | An và Binh, không có Chi ở OU cháu |
| **ou=people** | **SUBTREE** | An, Binh và Chi nếu filter phù hợp |
| **dc=example,dc=org** | **SUBTREE** | Có thể bao gồm cả users, groups, service accounts và các nhánh khác |

**Search base** trong **LdapQueryBuilder** có thể là DN tương đối với base của ContextSource. Nếu đã cấu hình **base=dc=example,dc=org**, ví dụ **query().base("ou=people")** là tìm dưới nhánh people của naming context ấy.

**Tối ưu bằng ONELEVEL có thể làm sai kết quả** khi người dùng được tổ chức theo OU lồng nhau. Ngược lại, SUBTREE từ suffix quá rộng có thể tạo chi phí cao, trả nhiều tài khoản không liên quan hoặc làm username trùng. Hãy chọn base/scope theo **hợp đồng định danh** và kiểm thử với dữ liệu nhiều nhánh.

Tìm từ directory forest hoặc Global Catalog của AD lại có quy tắc riêng về domain naming contexts và thuộc tính được replicate. Đừng coi một truy vấn SUBTREE trên một domain base mặc nhiên tìm được mọi tài khoản của toàn forest.

## 14. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Lookup **uid=binh,ou=people** trả **noSuchObject (32)** | Binh thật sự có RDN **cn=Binh Le** | Search theo **(uid=binh)** để lấy DN đúng |
| Search theo uid trả **0** | Sai search base/scope, thiếu attribute, ACL hoặc uid không tồn tại | Kiểm tra directory tree, filter, objectClass, account quyền |
| Search theo uid trả **nhiều** | uid không unique trong phạm vi; dữ liệu nhiều OU/tenant | Từ chối ambiguity hoặc thu hẹp phạm vi theo policy |
| **NameNotFoundException** sau rename | Cache lưu DN cũ | Resolve lại theo ID/thuộc tính phù hợp, kiểm tra actual state |
| **InvalidNameException / invalidDNSyntax (34)** | DN được nối chuỗi và escaping sai | LdapNameBuilder/Rdn, không dùng raw string |
| Filter tìm quá nhiều user | Wildcard hoặc LDAP injection | Dùng query builder, allowlist, giới hạn kết quả |
| Tìm được user nhưng login vẫn thất bại | Credentials sai, account policy, bind DN không hợp lệ | Phân biệt identity lookup và authentication |
| **invalidCredentials (49)** cho service account | Secret service bind sai hoặc account bị hạn chế | Sửa cấu hình/secret, không yêu cầu HTTP caller đăng nhập lại |
| **insufficientAccessRights (50)** | Service/user bind thiếu quyền trên entry/attribute | Kiểm tra ACL riêng cho đọc và ghi |
| **objectClassViolation (65)** khi tạo entry | Thiếu **cn/sn** hoặc objectClass không hợp schema | Xác minh MUST/MAY và mapping |
| Username là email nhưng search **uid** | Ứng dụng chọn sai login attribute | Cấu hình rõ trường login, kiểm tra uniqueness |
| Dùng UPN trên OpenLDAP không thành công | Giả định cơ chế bind đặc thù AD | Dùng DN thật và auth theo giao thức/server đích |
| Nhiều LDAP server có cùng DN | Đồng nhất nhầm hai directory | Gắn directory alias/tenant và server-managed ID nếu phù hợp |

### 14.1. Ba câu hỏi khi gặp lỗi đăng nhập

1. **Tên đăng nhập được ánh xạ tới attribute nào?** uid, mail, UPN, sAMAccountName hay field riêng?
2. **Entry nào khớp, có chính xác một entry không, và DN thực tế của nó là gì?** Xem search base/scope/objectClass/ACL.
3. **Lỗi xảy ra ở bước tìm người dùng hay bước xác thực credentials?** Phân biệt search không có kết quả, account ambiguity, bind sai, lỗi TLS, LDAP unavailable.

Không thử random thêm/sửa base DN hoặc tắt kiểm tra TLS chỉ để làm đăng nhập chạy. Thay đổi cấu hình cần dựa trên cây directory và chính sách authentication của server.

## 15. Thực hành kiểm thử với LDAP directory

### 15.1. Quan sát DN và uid bằng ldapsearch

Với một LDAP server test hỗ trợ LDAPS, dùng tài khoản service có quyền đọc và nhập mật khẩu tương tác:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=binh))" dn uid cn sn mail
~~~

Ở đây:

- **-b** chọn **search base DN**, không phải tên đăng nhập.
- **-s sub** chọn subtree, bao gồm OU con.
- **(uid=binh)** là điều kiện attribute, không yêu cầu RDN bằng uid.
- **dn** trong output là tên thật của entry được trả về, có thể bắt đầu bằng **cn**.
- **-W** yêu cầu password tương tác; không đặt password thật trong lệnh shell hoặc file Markdown.

Với dữ liệu ở phần 7, kết quả mong đợi gồm một entry Binh có DN **cn=Binh Le,ou=people,dc=example,dc=org**.

### 15.2. Integration test bằng Spring Boot

Khi đã seed fixture và cấu hình ContextSource trỏ đúng LDAP server test:

~~~java
package org.example.directory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DirectoryIdentityIntegrationTest {
    @Autowired DirectoryIdentityResolver resolver;

    @Test
    void uidSearchFindsEntryWhoseRdnIsCn() {
        ResolvedDirectoryUser user =
                resolver.resolveByUid("binh");

        assertNotNull(user);
        assertEquals("binh", user.uid());
        assertEquals("Binh Le", user.commonName());
        assertTrue(
                user.relativeDn().toString().toLowerCase(
                    java.util.Locale.ROOT).startsWith("cn="));
    }
}
~~~

Test này xác minh **search theo attribute uid nhưng DN thật bắt đầu bằng cn**. Nó cần entry Binh từ fixture, tài khoản có quyền đọc và directory phù hợp; không dùng mock thuần để khẳng định LDAP server đã áp dụng schema/ACL.

Một integration test khác nên chuẩn bị **hai entry cùng uid** ở hai OU dưới **ou=people**, rồi xác minh resolver **không chọn phần tử đầu tiên**. Hãy sử dụng fixture riêng để không làm hỏng test xác thực thành công.

### 15.3. Ma trận kiểm thử

| Ca | Thiết lập | Điều cần chứng minh |
| --- | --- | --- |
| **Lookup theo DN** | Entry có RDN uid dưới OU đã biết | Lấy đúng entry khi DN chính xác |
| **Login khác RDN** | Entry có RDN cn, nhưng uid: binh | Search uid tìm đúng DN cn |
| **Trùng uid nhiều OU** | Hai entry uid: an tại parent khác nhau | Resolver báo ambiguity |
| **Chuyển OU** | Rename/move uid=an từ people sang alumni | DN cũ mất hiệu lực; login attribute có thể giữ |
| **Đổi username** | Sửa login attribute theo naming policy | Có thể đổi login mà không đổi DN nếu RDN khác |
| **DN có dấu phẩy** | cn=Tran, An | Builder escaping đúng, không tạo nhầm RDN |
| **Filter có dấu sao literal** | username chứa ký tự **\*** theo policy test | Builder không biến thành wildcard |
| **Sai search base** | Entry nằm ngoài base | Search không thấy dù entry tồn tại |
| **ONELEVEL/SUBTREE** | User trong OU lồng | Scope ảnh hưởng chính xác kết quả |
| **Bind password sai** | Tài khoản test và mật khẩu không đúng | Không đăng nhập; response không tiết lộ account existence |
| **Service bind sai** | Secret kỹ thuật sai | Báo dependency/configuration error, không quy lỗi cho caller |
| **TLS sai CA/hostname** | Certificate test không hợp lệ | Client từ chối kết nối |
| **Account thiếu quyền** | Service account không được đọc OU | Không lộ dữ liệu ngoài ACL |
| **Group membership** | Group có member là full DN | DN tham chiếu đúng trước/sau rename |
| **Schema thiếu sn** | Tạo inetOrgPerson không có sn | Server từ chối theo schema |
| **Hai directory cùng DN** | LDAP test A/B có cùng DN | Không đồng nhất thành một identity chỉ dựa chuỗi DN |

Các ca tạo, move, rename, xóa và gây lỗi TLS/ACL chỉ chạy trên directory **test cô lập**, không thử phá vỡ tài khoản và nhóm production.

## 16. Checklist thiết kế định danh LDAP

1. **Cấu trúc cây:** biết suffix, naming context, base DN và các OU có thể chứa account.
2. **Login policy:** quy định chính xác attribute đăng nhập (**uid**, **UPN** hay cái khác) và phạm vi uniqueness.
3. **DN policy:** xác định RDN thường dùng và trường hợp rename/move; không lấy username làm DN nếu chưa xác minh quy ước.
4. **Java mapping:** @Id **Name** giữ DN; @Attribute ánh xạ login attribute; không lẫn kiểu ID của JPA.
5. **Search:** dùng filter builder, giới hạn base/scope, xử lý rõ 0/1/nhiều kết quả.
6. **Authentication:** không coi search found là authenticated; dùng LDAP bind/Spring Security LDAP với TLS và chính sách account.
7. **Stable identity:** nếu đồng bộ liên hệ dài hạn, đánh giá ID server-managed/ID ứng dụng, directory alias và kế hoạch migration.
8. **Group:** member/uniqueMember là DN tham chiếu, cần xử lý khi DN đổi.
9. **Bảo mật:** service bind chỉ có quyền cần thiết; không log raw credentials/DN nhạy cảm và chống account enumeration.
10. **Kiểm thử:** xác minh nhiều kiểu RDN, nhiều OU, duplicate username, filter escaping, bind, ACL, schema và TLS trên directory tương đương đích.

## 17. Tổng kết và bài tập tự luyện

**DN định danh vị trí một LDAP entry trong cây**. Nó được xây từ các RDN và có thể đổi khi entry bị rename/move. **Tên đăng nhập là dữ liệu/phương thức xác thực do ứng dụng và LDAP server quy định**, có thể lưu trong **uid**, **sAMAccountName**, **userPrincipalName**, **mail** hoặc một thuộc tính khác. Tên đăng nhập không bắt buộc xuất hiện trong DN và không mặc nhiên duy nhất toàn directory.

Trong **SPRING_DATA_LDAP**, khi đã biết DN thật, dùng **LdapTemplate.lookup** hoặc repository **findById(Name)**. Khi chỉ biết login name, **search theo thuộc tính được quy định** để xác định entry/DN đúng, kiểm tra uniqueness, rồi mới thực hiện xác thực LDAP an toàn. **@Id** giữ DN trong ODM, còn **@Attribute** giữ thuộc tính dùng cho nghiệp vụ. Việc tìm thấy một entry không chứng minh người dùng đã xác thực.

**Bài tập:**

1. Với DN **uid=an,ou=people,dc=example,dc=org**, xác định RDN, parent DN, full DN, ContextSource base và DN tương đối khi base là **dc=example,dc=org**.
2. Một entry có DN **cn=Binh Le,ou=people,dc=example,dc=org** và **uid: binh**. Tại sao **findByUsername("binh")** có thể thành công, còn lookup **uid=binh,ou=people** thất bại?
3. So sánh **uid**, **mail**, **sAMAccountName**, **UPN**, **DN**, **entryUUID/objectGUID** theo tính chất định danh, uniqueness và khả năng đổi theo thời gian.
4. Thiết kế chính sách tìm username **an** ở hai OU **employees** và **contractors**. Khi tìm được hai entry, ứng dụng nên xử lý thế nào để tránh đăng nhập nhầm?
5. Khi user chuyển từ **ou=people** sang **ou=alumni**, những dữ liệu nào cần cập nhật hoặc xác minh trong cache, database và **groupOfNames.member**?
6. Viết một ví dụ **LdapTemplate.search** theo uid và trả DN thực tế. Vì sao không nên tự dựng DN từ username?
7. Một API coi **search trả một entry** là đăng nhập thành công. Hãy giải thích lỗi bảo mật và cách sửa bằng LDAP bind/Spring Security LDAP.
8. Hai directory khác nhau có cùng một chuỗi DN. Vì sao ứng dụng đồng bộ không nên coi đó là cùng một người dùng?
9. Cho input chứa dấu phẩy và dấu sao, giải thích **DN escaping** khác **filter escaping** thế nào. API builder nào nên dùng cho mỗi loại?
10. Viết ma trận integration test kiểm tra user có RDN **cn**, user có RDN **uid**, username trùng, search scope lồng OU và user-bind qua LDAPS.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — entry, DN, RDN, attribute types, objectClasses, naming context.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) — cú pháp DN và escaping.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — equality, substring và escaping trong filter.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519) — các thuộc tính uid/cn và lớp person/inetOrgPerson.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513) — xác thực LDAP và yêu cầu bảo vệ kết nối.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, ContextMapper, LdapNameBuilder, authentication và query builder.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ODM, @Entry, @Id Name và repository finder.
- [Spring Security LDAP Reference](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html) — LDAP authentication bằng Spring Security.
- [Microsoft Learn — Active Directory Domain Services](https://learn.microsoft.com/en-us/windows/win32/ad/active-directory-domain-services) — dữ liệu định danh AD DS và những thuộc tính login đặc thù.
