# User directory: danh bạ định danh người dùng trong hệ thống IAM

Khi một nhân viên bắt đầu làm việc, tổ chức cần biết **người đó là ai, có tài khoản nào, thuộc bộ phận nào, đang hoạt động hay đã nghỉ và ứng dụng nào phải nhận thay đổi**. Một thành phần thường giúp các dịch vụ tra cứu những thông tin này là **user directory** – danh bạ người dùng. Tuy nhiên, danh bạ không tự động quyết định mọi quyền truy cập hoặc thay thế nguồn nhân sự có thẩm quyền.

Bài học thuộc chương **Directory service** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung vào quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, thay đổi vai trò và thu hồi quyền khi rời tổ chức. Chủ đề liên kết **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và cách giảm quyền truy cập tồn dư.

Trong bài này, **user directory** được hiểu là kho danh bạ có cấu trúc để lưu và tra cứu đối tượng người dùng cùng các thuộc tính và quan hệ của họ. Tùy sản phẩm, nó có thể là thư mục LDAP/Active Directory, thư mục danh tính đám mây hoặc dịch vụ directory thông qua API. Cách lưu, xác thực và đồng bộ thay đổi khác nhau giữa các nền tảng; không nên mặc định mọi user directory đều hỗ trợ LDAP hay cùng một schema.

Sau bài học, người học có thể:

- Giải thích vai trò user directory và phân biệt **hồ sơ nhân sự, danh tính IAM, tài khoản directory, credential, nhóm và quyền**.
- Nhận diện các khái niệm **LDAP entry, distinguished name (DN), relative distinguished name (RDN), attribute, schema, group** và ID bền vững.
- Thiết kế ánh xạ thông tin từ **HRIS → IAM/IGA → directory → IdP/ứng dụng**, hạn chế trùng danh tính và lỗi đồng bộ.
- Mô tả cách directory hỗ trợ Joiner, Mover, Leaver và cách xác minh việc vô hiệu hóa tài khoản tại hệ thống đích.
- Áp dụng nguyên tắc **TLS, least privilege, ACL, audit, replication và reconciliation** để vận hành danh bạ an toàn.

## 1. User directory là gì?

**Directory service** là dịch vụ cung cấp cách lưu, tổ chức và tra cứu thông tin về các đối tượng, ví dụ người dùng, nhóm, thiết bị hoặc dịch vụ. **User directory** là phần tập trung vào **đối tượng người dùng** và các thuộc tính liên quan.

Một bản ghi người dùng có thể chứa:

- **Định danh**: ID nội bộ, mã liên kết HRIS, tên tài khoản, tên hiển thị.
- **Tổ chức**: phòng ban, chức danh, đơn vị, người quản lý.
- **Trạng thái**: tài khoản còn hoạt động, bị vô hiệu hóa hoặc đang chờ kích hoạt.
- **Liên hệ**: email công việc, số điện thoại cần thiết.
- **Quan hệ**: thành viên nhóm, thuộc đơn vị tổ chức hoặc có người quản lý.
- **Metadata vận hành**: thời điểm tạo, lần cập nhật, nguồn đồng bộ và phiên bản.

Một directory thường được tối ưu cho **tra cứu và đọc nhiều**; không đồng nghĩa với hệ thống giao dịch nhân sự hay kho dữ liệu phân tích. Nhiều triển khai cho phép cập nhật bản ghi, nhưng quyền chỉnh sửa và nguồn dữ liệu có thẩm quyền phải được phân định rõ.

### 1.1. Vì sao directory quan trọng đối với IAM?

Tại doanh nghiệp, mỗi ứng dụng tự lưu phòng ban, tên người quản lý, email và trạng thái tài khoản có thể dẫn đến các phiên bản dữ liệu mâu thuẫn. Directory giúp cung cấp **một mô hình thông tin có thể tra cứu theo những quy tắc thống nhất**, đồng thời hỗ trợ xác thực/tích hợp khi công nghệ có khả năng tương ứng.

Ví dụ, khi HRIS xác nhận An chuyển từ phòng Kinh doanh sang Tài chính, directory có thể được cập nhật thuộc tính phòng ban và nhóm tương ứng. IdP hoặc ứng dụng dùng thông tin đó để tính lại chính sách, **nhưng vẫn phải kiểm tra quyền thực tế tại từng ứng dụng**.

**Directory là một thành phần cung cấp dữ liệu và quan hệ danh tính; không phải bằng chứng đầy đủ rằng việc cấp/thu hồi quyền đã hoàn thành.**

## 2. Phân biệt User directory với những thành phần gần nhau

| Thành phần | Trách nhiệm thường gặp | Không nên đồng nhất với |
| --- | --- | --- |
| **HRIS / hệ thống hợp đồng** | Nguồn có thẩm quyền cho sự kiện tuyển dụng, chuyển vị trí, nghỉ việc và nhiều thuộc tính nhân sự. | Directory chỉ lưu tài khoản hiện có. |
| **User directory** | Lưu/tra cứu user entry, thuộc tính, nhóm và trạng thái trong phạm vi sản phẩm. | Mọi quyết định quyền ở từng tài nguyên. |
| **IAM / IGA** | Liên kết danh tính, điều phối vòng đời, phê duyệt, tính quyền mong đợi, rà soát và đối soát. | Một kho LDAP đơn thuần. |
| **IdP** | Xác thực, MFA, chính sách đăng nhập và phát hành kết quả SSO/token. | Thư mục lưu user lúc nào cũng thực hiện xác thực. |
| **SCIM provider/client** | Trao đổi tài nguyên User và Group qua giao thức cấp phát tài khoản. | Giao thức LDAP hoặc đăng nhập SSO. |
| **RBAC / ABAC policy engine** | Quyết định quyền dựa trên role, thuộc tính, tài nguyên và ngữ cảnh. | Nhóm directory tự động cấp mọi quyền trong mọi ứng dụng. |
| **Ứng dụng đích** | Lưu local account, phiên, dữ liệu và thực thi quyền trong phạm vi ứng dụng. | Chỉ cần IdP báo thành công là đã đồng bộ. |

Một sản phẩm thực tế có thể tích hợp nhiều vai trò trong cùng nền tảng. Ví dụ, một dịch vụ danh tính đám mây có cả directory, tính năng IdP và quản lý nhóm. **Khác biệt ở đây là về trách nhiệm**, không nhất thiết phải là những máy chủ độc lập.

### 2.1. Tài khoản khác danh tính, tài khoản khác quan hệ lao động

Trong thiết kế JML nên phân biệt:

1. **Person/subject**: chủ thể được quản lý, có ID ổn định trong miền IAM.
2. **Engagement**: giai đoạn quan hệ Employee, Contractor hoặc loại quan hệ khác, có ngày bắt đầu/kết thúc riêng.
3. **Directory account/user entry**: đối tượng thể hiện chủ thể trong directory cụ thể.
4. **Authenticator/credential**: mật khẩu, passkey, chứng chỉ hoặc bí mật dùng trong xác thực.
5. **Entitlement**: nhóm, role, quyền trực tiếp hoặc quyền API ở hệ thống đích.

Một người có thể có **tài khoản thông thường, tài khoản đặc quyền và tài khoản tại ứng dụng riêng**. Người đó cũng có thể nghỉ việc rồi được tuyển lại với **engagement mới**, trong khi lịch sử danh tính cần được giữ tối thiểu theo chính sách. Vì thế không nên lấy “đã có một user entry” làm bằng chứng quan hệ lao động đang có hiệu lực.

## 3. Cấu trúc LDAP directory: entry, attribute và schema

**LDAP (Lightweight Directory Access Protocol)** là giao thức truy cập dịch vụ directory. Một LDAP directory thường trình bày dữ liệu dưới dạng **cây thông tin thư mục** (*Directory Information Tree – DIT*).

Một **entry** là bản ghi có:

- **Distinguished Name (DN)**: tên phân biệt xác định vị trí entry trong cây directory.
- **Attributes**: tập thuộc tính, mỗi thuộc tính có một hoặc nhiều giá trị tùy schema.
- **Object classes**: những lớp mô tả loại đối tượng và các thuộc tính bắt buộc/được phép.

Ví dụ cấu trúc minh họa:

~~~text
dc=example,dc=test
|
+-- ou=People
|   +-- uid=an.nguyen
|   +-- uid=binh.tran
|
+-- ou=Groups
|   +-- cn=finance-readers
|   +-- cn=operations-editors
|
+-- ou=Services
    +-- uid=svc-reporting
~~~

Các tên OU, UID và CN là **ví dụ**; cây LDAP thực tế có thể được tổ chức rất khác. Directory đám mây có thể không cung cấp cấu trúc DN/DIT cho khách hàng quản lý.

### 3.1. DN và RDN

Ví dụ:

~~~text
dn: uid=an.nguyen,ou=People,dc=example,dc=test
~~~

Trong đó:

- **uid=an.nguyen** là **RDN** của entry trong ví dụ.
- **ou=People** là thành phần tổ chức chứa entry.
- **dc=example,dc=test** mô tả suffix/domain component của cây ví dụ.
- Toàn bộ chuỗi là **DN**, dùng để định vị entry trong directory.

**DN không phải luôn là ID bất biến.** Việc đổi tên RDN hoặc di chuyển entry sang OU khác có thể làm DN thay đổi. Do đó, nếu hệ thống cần liên kết lâu dài tới một danh tính, nên dùng **định danh bền vững do directory/IdP cấp** theo hợp đồng tích hợp, cùng nguồn và namespace rõ ràng.

### 3.2. Object class và các trường người dùng

Ví dụ một entry theo dạng **LDIF (LDAP Data Interchange Format)**; giá trị và cấu trúc chỉ để học:

~~~ldif
dn: uid=an.nguyen,ou=People,dc=example,dc=test
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an.nguyen
cn: Nguyen An
sn: Nguyen
givenName: An
mail: an.nguyen@example.test
employeeNumber: EMP-5812
~~~

LDIF minh họa một kiểu entry LDAP chứ không phải cấu hình phải dùng trong Active Directory hoặc mọi nền tảng. Chữ tiếng Việt và ký tự đặc biệt có thể cần xử lý UTF-8/encoding phù hợp; dữ liệu nhạy cảm không nên đưa vào file mẫu hoặc log không được bảo vệ.

Một số thuộc tính thường gặp:

| Thuộc tính/khái niệm | Ý nghĩa phổ biến | Điều cần thận trọng |
| --- | --- | --- |
| **uid, cn, sn, givenName** | Tên tài khoản/thành phần tên tùy schema. | Không mặc nhiên là khóa bền vững hoặc được định nghĩa giống nhau giữa provider. |
| **mail / userPrincipalName** | Địa chỉ email hoặc tên đăng nhập trong hệ thống cụ thể. | Có thể đổi, bị tái sử dụng hoặc không giống nhau giữa ứng dụng. |
| **employeeNumber** | Mã nhân sự trong một số schema. | Có thể thuộc một engagement; cần namespace và quy tắc tái tuyển dụng. |
| **member / memberOf** | Quan hệ nhóm, tùy schema và sản phẩm. | Một số thuộc tính có thể suy dẫn, chỉ đọc hoặc phản ánh nested groups khác nhau. |
| **manager** | Tham chiếu người quản lý trong schema được hỗ trợ. | Có thể là DN tại directory; phải resolve đúng manager và cập nhật khi DN đổi. |
| **account enabled/disabled** | Trạng thái cho phép xác thực của tài khoản. | Tên trường và ngữ nghĩa khác nhau giữa LDAP server, AD DS và cloud directory. |
| **entryUUID, objectGUID, object ID** | Ví dụ các dạng ID do từng sản phẩm cấp. | Không phải một thuộc tính chuẩn chung của tất cả directory; có thể đổi khi xóa/tạo lại hoặc migration. |

Không nên tạo trường tùy chỉnh chỉ vì cần đồng bộ mà bỏ qua quy tắc schema, sở hữu dữ liệu và bảo vệ thông tin cá nhân.

## 4. LDAP, Active Directory và cloud directory khác nhau thế nào?

| Nền tảng/khái niệm | Khả năng đặc trưng | Lưu ý tích hợp |
| --- | --- | --- |
| **LDAPv3** | Giao thức tra cứu và cập nhật dữ liệu directory theo schema, DN và thao tác LDAP. | Giao thức không tự quy định một sản phẩm IAM, MFA hay SSO đầy đủ. |
| **Microsoft Active Directory Domain Services (AD DS)** | Directory domain, đối tượng user/group/computer, tích hợp Kerberos và các cơ chế domain. | Có LDAP interface nhưng hành vi, schema, SID, objectGUID, domain và chính sách Windows riêng. |
| **OpenLDAP hoặc LDAP server khác** | Directory theo schema và cấu hình máy chủ. | Kiểu group, ACL, replication, password policy phụ thuộc triển khai. |
| **Cloud identity directory** | Quản lý user/group qua portal và API, thường tích hợp IdP/MFA/SSO. | Không mặc định cung cấp LDAP bind. Ví dụ Microsoft Entra ID thường dùng API/SSO; LDAP có thể yêu cầu dịch vụ domain riêng. |
| **SCIM service provider** | API chuẩn hóa quản lý User/Group xuyên hệ thống. | ID tài nguyên và schema SCIM khác DN/entry của LDAP. |

**LDAP bind** có thể là cơ chế một ứng dụng sử dụng để xác thực với LDAP server, nhưng **SSO theo OIDC/SAML** là luồng khác. AD DS có thể dùng Kerberos để xác thực trong domain; không nên suy rằng mọi lần đăng nhập Active Directory đều sử dụng LDAP simple bind.

Vì vậy khi tìm hiểu “User directory của công ty”, cần biết **sản phẩm cụ thể, giao thức giao tiếp và phạm vi thẩm quyền** trước khi thiết kế tích hợp.

## 5. Khóa danh tính và liên kết nhiều hệ thống

Một sai lầm nghiêm trọng là coi **email = identity ID**.

Email có thể đổi do kết hôn, đổi tên miền, tái tuyển dụng; tên tài khoản có thể bị tái cấp. DN có thể đổi khi di chuyển OU. Một directory có thể bị xây dựng lại với ID kỹ thuật mới. IAM cần phân biệt:

| ID | Nơi phát hành | Mục đích |
| --- | --- | --- |
| **subjectId** | IAM nội bộ | Định danh chủ thể ổn định trong phạm vi IAM. |
| **personId / engagementId** | HRIS/nguồn hợp đồng | Liên kết đúng người và giai đoạn làm việc. |
| **directoryObjectId** | Directory cụ thể | Tham chiếu entry/tài khoản trong hệ thống đó. |
| **DN** | LDAP directory | Đường định vị entry, có thể đổi. |
| **issuer + sub** | OIDC IdP | Định danh chủ thể theo issuer ở phía RP. |
| **SCIM id** | SCIM service provider | ID tài nguyên User ở ứng dụng đích. |
| **SCIM externalId** | SCIM client | Mã tham chiếu liên kết do bên cấp phát cung cấp. |

Một bảng liên kết điển hình ở IAM có thể là:

~~~json
{
  "subjectId": "person-1042",
  "source": {
    "system": "hris-primary",
    "personId": "P000842",
    "engagementId": "EMP-5812"
  },
  "directory": {
    "system": "workforce-directory",
    "objectId": "directory-object-781",
    "currentDn": "uid=an.nguyen,ou=People,dc=example,dc=test"
  },
  "idp": {
    "issuer": "https://idp.example.test",
    "subject": "opaque-oidc-sub-1042"
  },
  "target": {
    "applicationId": "expense-portal",
    "scimUserId": "scim-user-8802"
  }
}
~~~

Đây là **schema minh họa**, không phải mẫu chính thức của LDAP, SCIM hoặc OIDC. Liên kết này chỉ được tạo sau khi xác minh đúng người/quan hệ; **không được ghép bản ghi trùng email một cách tự động** nếu nguồn không đủ tin cậy.

### 5.1. Khi đổi tên, chuyển OU hoặc tái tuyển dụng

- **Đổi tên tài khoản/email:** giữ liên kết theo ID bền vững; cập nhật username, DN hoặc thuộc tính cần thiết.
- **Chuyển OU:** cập nhật tham chiếu DN ở các hệ thống sử dụng DN, không tạo danh tính con người mới chỉ vì đổi vị trí cây.
- **Tái tuyển dụng:** xác minh cùng người nếu có bằng chứng, ghi **engagement mới**, tính lại quyền; không tự phục hồi credential và entitlement cũ.
- **Xóa/tạo lại entry:** ID directory có thể thay; cần quy trình nối/migration có kiểm chứng, ngăn chiếm quyền qua tên tài khoản trùng.

## 6. Nguồn có thẩm quyền và ánh xạ thuộc tính

**Directory lưu một bản sao vận hành của nhiều thuộc tính**, nhưng **không mặc nhiên là nguồn có thẩm quyền của tất cả thuộc tính**. Ví dụ:

- **HRIS** có thể sở hữu worker type, ngày bắt đầu, ngày nghỉ, chức danh, bộ phận và direct manager.
- **IAM/IGA** có thể sở hữu subject ID chuẩn, trạng thái vòng đời được tính và lịch sử phê duyệt.
- **Directory/IdP** có thể sở hữu account ID, username, credential state và một số thuộc tính liên lạc.
- **Ứng dụng đích** có thể sở hữu application role, bản ghi nghiệp vụ hoặc quyền do owner ứng dụng phê duyệt.

### 6.1. Bảng ánh xạ HRIS → IAM → Directory

| Dữ liệu HRIS | Thuộc tính chuẩn IAM | Directory / ứng dụng | Quy tắc |
| --- | --- | --- | --- |
| **personKey** | **sourcePersonId** | Custom attribute hoặc correlation store | Namespace nguồn và quy tắc xác minh rõ. |
| **employmentKey** | **engagementId** | employeeNumber hoặc extension phù hợp | Không làm ID con người duy nhất nếu tái tuyển dụng. |
| **fullName** | **displayName** | cn/displayName tùy provider | Giữ Unicode; tên không làm khóa. |
| **deptCode** | **departmentId** | department hoặc mã group liên quan | Chỉ ánh xạ qua bảng mã được phê duyệt. |
| **jobCode** | **jobCode** | custom field, role assignment nếu có | Không tự cấp quyền từ chuỗi tên chức danh. |
| **managerPersonId** | **managerSubjectId** | manager DN/object ID hoặc SCIM manager value | Resolve đúng manager ở hệ thống đích. |
| **startDate** | **startDate / activationAt** | trạng thái chờ hoặc lịch bật tài khoản | Quy đổi ngày theo múi giờ và chính sách. |
| **employmentStatus** | **lifecycleState** | trạng thái user/account có ý nghĩa tương ứng | Không đồng nhất HR status với cờ account ở mọi sản phẩm. |

Khi HRIS và directory mâu thuẫn về bộ phận, phải dùng **ma trận nguồn sở hữu từng thuộc tính**; không lấy giá trị mới nhất theo thời gian nhận để ghi đè tùy tiện.

### 6.2. Trường trống, null và xóa phải được phân biệt

Khi nguồn gửi bản cập nhật một phần, việc **không xuất hiện trường manager** thường không đồng nghĩa yêu cầu xóa manager. Giá trị rỗng hoặc null có ý nghĩa tùy hợp đồng dữ liệu. Với LDAP Modify, SCIM PATCH và API riêng, thao tác xóa thuộc tính có ngữ nghĩa khác nhau. Phải chuẩn hóa quy tắc trước khi đồng bộ, nhất là những thuộc tính có tác động tới RBAC/ABAC.

## 7. Truy vấn và cập nhật directory an toàn

LDAP hỗ trợ các thao tác như **Bind, Search, Compare, Add, Modify, Modify DN và Delete** tùy phân quyền. Đây là thao tác trên tài nguyên directory; không có nghĩa mọi ứng dụng đều được quyền sử dụng tất cả.

### 7.1. Một truy vấn tìm user

Tham số logic minh họa:

~~~text
server: directory.example.test
baseDN: ou=People,dc=example,dc=test
scope: subtree
filter: (uid=an.nguyen)
attributes: uid, cn, mail, employeeNumber
~~~

**Filter LDAP không được ghép trực tiếp từ input người dùng**. Cần sử dụng thư viện tạo filter/escape theo quy tắc chuẩn, giới hạn các thuộc tính có thể truy vấn và thực thi bằng tài khoản chỉ có quyền cần thiết. Điều này giúp giảm rủi ro **LDAP injection** và truy vấn ngoài phạm vi dự định.

Ví dụ trên cố tình không chứa credential, URL chứa mật khẩu hay hướng dẫn đưa bí mật vào dòng lệnh. Khi tích hợp, ứng dụng nên dùng **kết nối TLS được kiểm chứng**, timeout, limit, pagination thích hợp và bộ lọc chỉ lấy những thuộc tính thật sự cần.

### 7.2. LDAP bind không giống SSO

- **LDAP Bind** thiết lập ngữ cảnh xác thực cho kết nối LDAP; một số hệ thống dùng nó để kiểm credential hoặc để service account truy vấn directory.
- **Kerberos** trong AD DS là cơ chế xác thực dựa trên ticket, không đồng nhất với thao tác LDAP Bind.
- **OIDC/SAML SSO** chuyển kết quả xác thực từ IdP tới ứng dụng theo federation, có validation riêng về issuer, audience, chữ ký và thời gian.
- **SCIM** cấp phát/cập nhật User/Group qua HTTP API, không phải phương thức xác thực tương tác của người dùng.

Nếu ứng dụng chỉ có chức năng LDAP Bind bằng mật khẩu, cần đánh giá liệu có nên thay bằng đăng nhập qua IdP với MFA chống phishing. **Không nên gửi mật khẩu người dùng tới nhiều ứng dụng chỉ để tiện tra cứu directory**.

### 7.3. LDAP qua TLS và thông tin xác thực

Với LDAP truyền thống, có thể có cơ chế **LDAPS (LDAP over TLS)** hoặc **StartTLS** trên kết nối LDAP tùy server/client. Điều quan trọng không phải chỉ “có biểu tượng ổ khóa” mà là:

1. Kết nối được mã hóa.
2. Client kiểm chứng chứng chỉ server và tên máy chủ/điểm kết nối thích hợp.
3. Không tự động hạ cấp xuống kết nối không bảo vệ.
4. Không thực hiện simple bind chứa password qua kênh không được bảo vệ.
5. Service credential có quyền tối thiểu, lưu trong kho bí mật phù hợp, có lịch xoay/thu hồi.

Không dùng cấu hình “bỏ kiểm chứng chứng chỉ” để chữa lỗi kết nối production. Nếu lỗi TLS, phải kiểm CA trust, chain, hostname, ngày hiệu lực và cấu hình giao thức.

## 8. Kiến trúc dòng dữ liệu User directory trong IAM

~~~mermaid
flowchart LR
    HR["HRIS / hợp đồng<br/>sự kiện Joiner, Mover, Leaver"] --> IGA["IAM / IGA<br/>identity linking + lifecycle policy"]
    IGA --> DIR["User directory<br/>user entry + group + attributes"]
    DIR --> IDP["IdP<br/>authentication, MFA, SSO"]
    IDP -->|"OIDC / SAML"| APP["Ứng dụng nghiệp vụ"]
    IGA -->|"SCIM / provisioning API"| APP
    DIR -.->|"đồng bộ thuộc tính/nhóm theo thiết kế"| APP
    IGA --> AUD["Audit + reconciliation"]
    DIR --> AUD
    IDP --> AUD
    APP --> AUD
    AUD -->|"Sai khác / tài khoản tồn dư"| IGA
~~~

Đây là một kiến trúc **minh họa**. Trong thực tế, IdP có thể tích hợp directory ngay trong sản phẩm hoặc tự sở hữu đối tượng user; IAM có thể cấp phát cho IdP trước rồi đồng bộ sang directory; có hệ thống hoàn toàn không có LDAP server. Quan trọng là phân định **nguồn dữ liệu, hướng đồng bộ và nơi thực thi quyền**.

### 8.1. “Một nguồn dữ liệu” không có nghĩa một cơ sở dữ liệu duy nhất

Doanh nghiệp có thể duy trì nhiều directory theo pháp nhân, môi trường, địa điểm hoặc loại danh tính. Mô hình cần xác định **source of truth cho từng thuộc tính**, quản lý namespace và tránh vòng đồng bộ.

Ví dụ, nếu IdP cập nhật tên hiển thị vào directory trong khi connector HRIS cũng luôn ghi đè tên, các hệ thống có thể liên tục sửa qua lại. Cần quy tắc **hướng cập nhật một chiều hoặc ưu tiên có kiểm soát**, và cơ chế ghi nguồn/phiên bản.

## 9. Joiner: tạo user entry đúng người và đúng thời điểm

### 9.1. Từ HRIS sang directory

Một Joiner có thể được xử lý theo trình tự:

1. HRIS xác nhận **người mới, ID nhân sự, worker type và Start date**.
2. IAM thực hiện **identity proofing**, kiểm trùng và liên kết đúng subject ID.
3. Kiểm tra mã phòng ban, chức danh, quản lý và trạng thái hồ sơ theo schema.
4. Tạo user entry/account tại directory với **ID bền vững** và thuộc tính cần thiết.
5. Nếu chính sách cho phép **pre-provisioning**, tài khoản có thể tồn tại ở trạng thái chờ, chưa được đăng nhập hoặc chưa có quyền nghiệp vụ.
6. Đến thời điểm kích hoạt và sau khi kiểm lại dữ liệu nguồn, IdP/directory bật account theo chính sách; IAM cấp entitlement được phê duyệt.
7. Đồng bộ SCIM/API tới ứng dụng; xác minh account và quyền thực tế.

### 9.2. Start date không đồng nghĩa createdAt

Giả sử HRIS tạo hồ sơ ngày 20/11 nhưng Start date là 01/12. Directory có thể tạo user entry từ ngày 25/11 để hệ thống chuẩn bị thiết bị/email. **Sự tồn tại của entry không chứng minh nhân viên được phép vào hệ thống từ ngày 25/11**.

Phải phân biệt:

- **recordCreatedAt**: lúc entry được tạo.
- **startDate**: ngày nghiệp vụ quan hệ có hiệu lực.
- **activationAt**: thời điểm kỹ thuật IAM được phép kích hoạt, tính theo múi giờ/chính sách.
- **entitlementEffectiveAt**: thời điểm quyền cụ thể bắt đầu.

Tác vụ kích hoạt cần kiểm lại **phiên bản dữ liệu và trạng thái HRIS hiện hành**, đặc biệt khi Start date bị dời hoặc tuyển dụng bị hủy.

### 9.3. Tránh tạo user trùng

Không kiểm tra trùng chỉ bằng họ tên hoặc email. Dùng ID nguồn cùng namespace và bảng liên kết subject–engagement–directory. Nếu hai bản ghi có dấu hiệu liên quan nhưng không chắc cùng người, chuyển quy trình xác minh thay vì gộp; gộp nhầm có thể đưa credential của người A vào quyền của người B.

## 10. Mover: cập nhật thuộc tính và thu hồi quyền cũ

**Mover** xảy ra khi một người đổi bộ phận, chức danh, manager, vị trí hoặc trách nhiệm nhưng chưa rời tổ chức. Directory có thể nhận thay đổi thông qua HRIS/IGA, tuy nhiên hành động phải phụ thuộc loại thuộc tính và ngày hiệu lực.

### 10.1. Ví dụ chuyển từ Sales sang Finance

| Trạng thái | Trước Mover | Sau Mover |
| --- | --- | --- |
| **subjectId** | person-1042 | Giữ nguyên. |
| **directoryObjectId** | directory-object-781 | Thường giữ nguyên nếu cùng entry/account. |
| **departmentId** | SALES | FINANCE. |
| **managerSubjectId** | person-2010 | person-2088. |
| **Nhóm công việc được duyệt** | sales-reader | finance-reader. |
| **Quyền cần thu hồi** | Chưa phát sinh Mover | sales-reader và quyền trực tiếp không còn phù hợp. |

Một quy trình đúng không chỉ thêm **finance-reader**; phải **loại quyền cũ** nếu quan hệ công việc mới không còn yêu cầu. Nếu chỉ thêm quyền, nhân viên có thể tích lũy quyền (*privilege creep*).

### 10.2. Group và thời điểm có hiệu lực

Khi thay nhóm:

- Directory update có thể hoàn tất trước khi mọi domain controller/replica hoặc IdP cache nhìn thấy thay đổi.
- Quyền tại ứng dụng có thể dựa trên token/claims đã phát hành, chưa cập nhật ngay.
- Một ứng dụng có thể dùng local group mapping hoặc quyền được cấp trực tiếp ngoài directory.
- Chính sách phải biết quyền nào được **cấp mới**, **thu hồi**, và thời điểm phải có hiệu lực.

Với thay manager, một trường directory có thể được cập nhật nhưng tuyến phê duyệt yêu cầu truy cập chưa đổi. Cần xử lý workflow đang chờ, delegation và quyền xem dữ liệu cấp dưới theo quy tắc riêng; **manager DN không tự cấp mọi quyền quản trị**.

## 11. Leaver: disable directory account không đồng nghĩa đã deprovision xong

Khi nguồn có thẩm quyền xác nhận Employee hoặc Contractor hết quan hệ:

1. IAM ghi nhận **subject/engagement** và thời điểm Leaver có hiệu lực.
2. Directory/IdP **vô hiệu hóa xác thực** của tài khoản liên quan theo chính sách.
3. Thu hồi hoặc hạn chế **group, entitlement, tài khoản đặc quyền và credential** không còn hợp lệ.
4. Xử lý **IdP session, ứng dụng có local session, refresh token, PAT, API key, chứng chỉ** theo khả năng từng hệ thống.
5. Truyền trạng thái deprovision qua SCIM/API tới ứng dụng; tránh chỉ dựa vào cờ trong directory.
6. **Đọc lại trạng thái từng đích**, điều tra sai khác và giữ audit trail của yêu cầu, phản hồi và xác minh.
7. Chuyển giao owner của dữ liệu và workload cần duy trì; giữ hồ sơ kiểm toán tối thiểu theo lịch lưu giữ hợp lệ.

### 11.1. Các lỗi Leaver thường gặp

| Tình huống | Vì sao nguy hiểm | Cách kiểm soát |
| --- | --- | --- |
| Directory user bị disabled nhưng ứng dụng còn local password. | Người nghỉ có thể đăng nhập ngoài IdP. | Inventory app, disable local account và kiểm tra thực tế. |
| User bị xóa nhưng token/phiên vẫn có hiệu lực. | Đường truy cập cũ chưa bị chặn. | Thu hồi session/token và kiểm quyền tại API. |
| Xóa entry ngay lập tức làm mất correlation ID. | Khó giải trình lịch sử đăng nhập và phê duyệt. | Lưu tham chiếu tối thiểu trong kho audit có lịch giữ riêng. |
| SCIM connector lỗi nhưng job IAM báo completed. | App account và nhóm cũ còn tồn tại. | Trạng thái từng hệ thống, retry, đối soát sau lệnh. |
| Nhân viên từng sở hữu service account. | Bí mật hoặc quyền máy vẫn tồn tại không owner. | Chuyển owner, rotate credential, review quyền. |
| Restore từ bản backup trước ngày nghỉ. | Tài khoản bị khóa có thể sống lại. | Áp lại sự kiện Leaver/deny access trước khi phục vụ. |

**Directory thường chỉ biết trạng thái user trong phạm vi của chính nó.** Việc không còn entry ở LDAP không tự chứng minh SaaS đã xóa phiên, credential riêng hoặc role cục bộ.

### 11.2. Xóa, disable và lưu giữ dữ liệu

Với Leaver, cần tách **thu hồi quyền ngay theo chính sách** khỏi **xóa hồ sơ**. Một số dữ liệu nhân sự, giao dịch và nhật ký có thể cần lưu trong thời hạn hợp lệ; điều này **không đòi hỏi giữ tài khoản đang hoạt động**. Không nên giữ password verifier hoặc API secret còn dùng được chỉ vì cần audit.

## 12. Directory group, RBAC và ABAC

### 12.1. Nhóm directory không tự đồng nghĩa role nghiệp vụ

Một nhóm như **finance-readers** có thể được IAM ánh xạ thành role đọc báo cáo tại ứng dụng, nhưng chỉ khi có policy và tích hợp phù hợp.

~~~text
HRIS jobCode / departmentId
       |
       v
IAM policy + approvals + effectiveAt
       |
       v
Expected group membership / entitlement
       |
       v
Directory / SCIM / IdP
       |
       v
Ứng dụng ánh xạ role và kiểm quyền tại tài nguyên
~~~

Ứng dụng phải biết nhóm nào được tin, nhóm nào có ý nghĩa phân quyền và ai có quyền sửa membership. **Không để người dùng tự thêm mình vào nhóm đặc quyền** hoặc sửa `departmentId` được dùng cho ABAC.

### 12.2. Nhóm lồng nhau và nhóm động

- **Direct membership:** user được gán trực tiếp vào group.
- **Nested membership:** group chứa một group khác, nếu directory và ứng dụng hỗ trợ.
- **Dynamic membership:** nhóm được tính từ thuộc tính/policy, tùy công nghệ.

Không giả định tất cả API hoặc claim SSO sẽ xử lý nested group giống nhau. Có hệ thống chỉ trả thành viên trực tiếp; có hệ thống mở rộng gián tiếp hoặc giới hạn kích thước claim/token. Cần kiểm tra **effective membership** ở đúng hệ thống thực thi quyền.

### 12.3. ABAC và độ tươi của thuộc tính

Ví dụ giả mã:

~~~text
ALLOW if
    subject.lifecycleState == "ACTIVE"
    AND subject.departmentId == resource.ownerDepartmentId
    AND subject.approvedRole == "READER"
    AND request.action == "read"
~~~

Đây là mô hình **Attribute-Based Access Control (ABAC)** minh họa. Nó chỉ đáng tin khi `departmentId`, trạng thái quan hệ và role được cập nhật từ nguồn có thẩm quyền. Nếu directory đã đổi bộ phận nhưng ứng dụng giữ claim/cache cũ, một quyết định **đúng về logic vẫn có thể sai về dữ liệu đầu vào**.

## 13. Directory và IdP: dữ liệu dùng trong Authentication, MFA, SSO

Một IdP có thể dùng directory làm nguồn user, trực tiếp lưu account trong cloud directory hoặc liên kết qua một connector. Tuy nhiên:

- **Directory lookup** cho biết user entry tồn tại, không nhất thiết chứng minh người dùng đã xác thực.
- **LDAP Bind** là một cơ chế cụ thể, không thay thế mọi hình thức MFA hoặc OIDC/SAML.
- **SSO** phát hành kết quả đăng nhập theo federation, nhưng không tự tạo entitlement ở ứng dụng.
- **SCIM** cấp phát User/Group theo hướng điều phối, nhưng không tự phát hành session.

### 13.1. Ví dụ một lỗi thường bị gọi là “SSO error”

IdP xác thực An thành công, phát OIDC ID token hợp lệ nhưng ứng dụng trả 403. Nguyên nhân có thể do:

1. SCIM chưa tạo local account.
2. Directory membership chưa đồng bộ.
3. Role tại ứng dụng chưa được duyệt.
4. Token chứa claim nhóm cũ.
5. ABAC từ chối hợp lệ vì dữ liệu không thuộc quyền An.

**Không reset mật khẩu hoặc tắt MFA chỉ để sửa lỗi 403.** Cần xác định chính xác lớp lỗi và xác minh quyền mong đợi từ IAM.

### 13.2. Thời hạn token và trạng thái Leaver

Khi directory account bị disabled, IdP có thể chặn đăng nhập mới. Tuy vậy, một application session hoặc self-contained access token đã phát hành trước đó **có thể còn dùng được tới khi hết hạn** nếu resource server không có cơ chế thu hồi/kiểm quyền hiện hành. Vì thế deprovisioning phải đánh giá token, phiên và hệ thống đích, không chỉ trạng thái user directory.

## 14. Service account, privileged identity và thiết bị

Directory có thể lưu không chỉ Employee mà cả **service account, máy tính, nhóm vận hành và tài khoản quản trị**. Tuy cùng là entry, chúng có đặc điểm vòng đời khác nhau.

### 14.1. Service account

Một dịch vụ chạy báo cáo có thể dùng tài khoản máy với credential riêng. Các thuộc tính cần quản trị:

| Thuộc tính | Vai trò |
| --- | --- |
| **principalId / accountId** | Xác định danh tính kỹ thuật. |
| **ownerTeam / technicalOwner** | Người/nhóm chịu trách nhiệm. |
| **applicationId / workloadId** | Dịch vụ hoặc tác vụ nào dùng tài khoản. |
| **environment** | Development, staging hoặc production. |
| **credentialType / rotationPolicy** | Bí mật, chứng chỉ, managed identity và lịch thay/thu hồi. |
| **entitlementScope** | Những hệ thống/tài nguyên được phép truy cập. |
| **lifecycleState / reviewAt** | Dịch vụ còn hoạt động và bao giờ rà soát. |

Không ép service account vào mô hình Employee với ngày sinh, manager nhân sự hoặc hồ sơ HRIS giả. Nếu owner Employee nghỉ việc, phải **chuyển trách nhiệm**, rà soát quyền và rotate credential khi cần; không vô hiệu hóa tùy tiện workload production còn hợp lệ nhưng cũng không cho account vô chủ hoạt động vô hạn.

### 14.2. Tài khoản đặc quyền

Tài khoản admin có thể tồn tại trong cùng directory nhưng nên chịu **quy tắc bảo vệ riêng**: xác thực mạnh, PAM/just-in-time privilege khi phù hợp, theo dõi sử dụng, thời hạn, phân tách nhiệm vụ và kiểm soát reset credential. Người dùng có tài khoản thường bị khóa không bảo đảm mọi tài khoản admin phụ đã bị thu hồi; cần inventory liên kết.

### 14.3. Device directory

Một số directory quản lý computer/device objects. Chúng có thể tham gia chính sách conditional access hoặc quản trị thiết bị; tuy nhiên **thiết bị tồn tại trong directory không đồng nghĩa đang an toàn hoặc được phép truy cập**. Cần kiểm tra trạng thái quản lý, thiết bị và policy theo hệ thống thực thi.

## 15. Đồng bộ, replication và đối soát

Directory enterprise thường có **nhiều bản sao** hoặc connector đồng bộ tới IdP, SaaS và ứng dụng nội bộ. Điều này tạo ra độ trễ, thứ tự sự kiện và khả năng thay đổi thành công một phần.

### 15.1. Các dạng sai lệch cần nhận biết

| Vấn đề | Tình huống | Hướng xử lý |
| --- | --- | --- |
| **Replication lag** | Directory node A có nhóm mới, node B chưa cập nhật. | Đo thời gian hội tụ, dùng đọc lại theo cơ chế provider. |
| **Connector delay** | HRIS đã cập nhật Mover nhưng IdP/SaaS vẫn dùng thuộc tính cũ. | Theo dõi hàng đợi, retry, phiên bản và thời điểm hiệu lực. |
| **Stale event** | Sự kiện manager cũ đến sau sự kiện mới. | Dùng source record version/effective date, không ghi đè mù quáng. |
| **Duplicate event** | Cùng Joiner được gửi nhiều lần. | Idempotency theo event ID và stable person/engagement ID. |
| **Partial failure** | Thêm nhóm mới thành công nhưng xóa nhóm cũ thất bại. | Tách trạng thái từng thao tác và đối soát entitlement thực tế. |
| **Manual drift** | Admin sửa user/group trực tiếp ngoài IAM workflow. | Cảnh báo thay đổi ngoài nguồn có thẩm quyền, reconcile và xử lý ngoại lệ. |
| **Backup restore** | Directory khôi phục về trạng thái trước khi Leaver bị vô hiệu hóa. | Đối soát JML, credential, quyền trước khi mở dịch vụ trở lại. |

### 15.2. Vì sao đọc lại trạng thái quan trọng?

Một tác vụ IAM có thể đã gửi **Modify** tới LDAP server và nhận phản hồi thành công, nhưng:

- Replica khác chưa thấy bản cập nhật.
- IdP đã cache group membership cũ.
- SaaS chưa đồng bộ được qua SCIM.
- Ứng dụng có role trực tiếp ngoài nhóm directory.
- Token/phiên đang dùng chưa phản ánh trạng thái mới.

Vì vậy, trạng thái cần được xác minh ở **hệ thống ra quyết định quyền cuối cùng**, không chỉ ở điểm nhận lệnh đầu tiên.

### 15.3. Mẫu xử lý sự kiện thay đổi danh tính

~~~text
onAuthoritativeLifecycleEvent(event):
    verifySourceSchemaAndAuthorization(event)
    if eventAlreadyProcessed(event.eventId):
        return

    subject = resolveBySourcePersonAndEngagementId(event)
    if subject is ambiguous:
        openManualIdentityReview(event)
        return

    if event.version < subject.latestTrustedVersion:
        recordIgnoredStaleEvent(event)
        return

    normalized = validateAndMapAttributes(event)
    if normalized.hasCriticalErrors:
        quarantineAndAlertDataOwner(event)
        return

    saveCanonicalStateAndProvenance(subject, normalized, event)
    expected = evaluateJmlAndAccessPolicies(subject, event.effectiveAt)
    updateDirectoryAccountAndGroups(expected)
    synchronizeIdpAndTargetApps(expected)
    verifyDirectoryReplicasAndActualTargetAccess(expected)
    recordAuditableResultsAndOpenExceptions(expected)
~~~

Đây là **giả mã kiến trúc**, không phải code thao tác LDAP hoặc SCIM chạy được. Trong sản phẩm thực, cần tách tác vụ lên lịch hiệu lực, kiểm lại trạng thái mới nhất khi đến hạn, kiểm soát giao dịch từng phần, rate limit, retry, backoff và cách xử lý xung đột dữ liệu. Không cho sự kiện cũ bật lại tài khoản Leaver.

## 16. Bảo mật và quyền riêng tư của User directory

Directory là tập trung thông tin tổ chức và đường truy cập danh tính; đọc hoặc sửa sai một entry có thể ảnh hưởng nhiều ứng dụng. Cần bảo vệ cả **dữ liệu**, **credential tích hợp** và **thay đổi quyền**.

### 16.1. Quyền đọc và quyền ghi

- **Least privilege:** ứng dụng chỉ được tra cứu thuộc tính cần thiết; connector có quyền ghi phải giới hạn chính xác OU, object/attribute và thao tác cần dùng.
- **ACL / RBAC quản trị:** phân biệt quyền tạo user, sửa thuộc tính nhân sự, đổi group đặc quyền, reset password và xóa account.
- **Separation of duties:** người phê duyệt đặc quyền không nhất thiết là người có khả năng tự cấp đặc quyền.
- **Privileged access:** quản trị viên dùng credential/phiên đặc quyền được kiểm soát; hạn chế quyền quản trị thường trực khi có cơ chế phù hợp.
- **Không truy cập ẩn danh rộng:** tránh công khai danh sách email, cấu trúc phòng ban hoặc group nhạy cảm nếu không có căn cứ.

### 16.2. Bảo vệ giao tiếp và credential

- Sử dụng TLS với **kiểm chứng chứng chỉ**, tránh simple bind qua kết nối rõ.
- Dùng service principal hoặc tài khoản tích hợp **riêng theo ứng dụng**, không dùng account admin toàn quyền.
- Lưu secret trong kho bí mật và xoay/thu hồi khi owner nghỉ việc, tích hợp đổi hoặc có sự cố.
- Hạn chế truy vấn rộng, áp dụng timeout/pagination và kiểm input để giảm lộ dữ liệu hoặc quá tải.
- Theo dõi đăng nhập lỗi bất thường, truy vấn liệt kê hàng loạt và thay đổi group đặc quyền.

### 16.3. Dữ liệu cá nhân

Directory có thể chứa họ tên, email, điện thoại, vị trí, quan hệ quản lý và thông tin nhân sự; đây là dữ liệu cần bảo vệ theo mục đích và quy định liên quan.

Nên:

1. **Giảm thiểu thuộc tính:** không sao chép hồ sơ y tế, giấy tờ cá nhân hoặc thông tin lương vào directory chỉ để tiện tra cứu.
2. **Giới hạn phạm vi truy cập:** app không cần `manager` hoặc `employeeNumber` thì không tự phát các trường đó.
3. **Ghi vết tra cứu nhạy cảm và thay đổi quyền**, nhưng không lưu mật khẩu/token/private key.
4. **Xác định retention schedule** cho user entry, correlation metadata và audit records khi Leaver.
5. **Kiểm soát bản sao và export**, đặc biệt file LDIF, bản backup directory hoặc log debug.

**Ẩn user khỏi danh sách tìm kiếm không đồng nghĩa đã vô hiệu hóa tài khoản**; disable account cũng không đồng nghĩa dữ liệu cá nhân đã được xóa đúng chính sách.

## 17. Theo dõi sự kiện và kiểm toán directory

Để giải trình một quyết định IAM, cần truy vết **ai tạo/sửa user, từ nguồn nào, thay đổi thuộc tính/nhóm gì, khi nào, và quyền nào tại đích bị ảnh hưởng**.

### 17.1. Các bằng chứng cần có

| Bằng chứng | Nội dung gợi ý | Mục đích |
| --- | --- | --- |
| **Nguồn vòng đời** | HRIS event ID, subject/engagement ID, status, effectiveAt. | Xác định quan hệ có hiệu lực. |
| **Directory object** | Directory ID, DN trước/sau, account status, schema/namespace. | Xác định đúng tài khoản. |
| **Thuộc tính trước/sau** | Department, manager, group membership quan trọng. | Phân tích Mover và quyền cũ. |
| **Policy/approval** | Policy ID/version, approver và lý do thay đổi. | Chứng minh cấp/thu hồi đúng thẩm quyền. |
| **Lệnh cập nhật** | Operation, request ID, service principal/actor, thời gian. | Biết ai hoặc workflow nào thực thi. |
| **Xác minh đích** | IdP, SCIM, local account và entitlement được đọc lại. | Phân biệt sent/acknowledged/verified. |
| **Ngoại lệ và retry** | Target thất bại, owner, hạn xử lý, kết quả đóng. | Ngăn tài khoản/quyền tồn dư. |

Ví dụ một bản ghi audit nội bộ (không chứa bí mật):

~~~json
{
  "eventType": "DIRECTORY_USER_GROUPS_RECONCILED",
  "eventId": "iam-dir-20261123-042",
  "traceId": "mover-person-1042-20261201",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "directoryObjectId": "directory-object-781",
  "sourceSystem": "hris-primary",
  "sourceEventId": "hr-mover-618",
  "action": "RECONCILE_GROUP_MEMBERSHIP",
  "expectedGroups": ["finance-readers"],
  "removedGroups": ["sales-readers"],
  "result": "VERIFIED",
  "policyVersion": "access-map-v7",
  "verifiedAt": "2026-12-01T01:05:00Z"
}
~~~

Đây là **schema minh họa**. Log thật cần phân quyền, bảo vệ sửa/xóa, quản lý thời hạn lưu và chỉ chứa dữ liệu cần thiết. Không lưu password, hash nhạy cảm, token, session cookie hoặc toàn bộ hồ sơ HRIS để “dễ debug”.

### 17.2. Những kết luận phải phân biệt

- **Directory Modify success**: máy chủ nhận thay đổi theo giao thức trong phạm vi đó.
- **Replica reconciled**: những bản sao đã được kiểm tra nhìn thấy trạng thái mong đợi.
- **IdP synchronized**: IdP đã có account/thuộc tính phù hợp.
- **Application provisioned**: ứng dụng có tài khoản/nhóm/role mong đợi.
- **Access effectively revoked**: đường truy cập thuộc phạm vi đã được xác minh không còn quyền, bao gồm các phiên/token cần kiểm soát.

Không đánh đồng năm loại bằng chứng này.

## 18. Case study: Mover và Leaver tại hệ thống có nhiều directory

**Bối cảnh:** doanh nghiệp dùng AD DS cho nhân viên nội bộ, IdP đám mây cho SSO và một SaaS dùng SCIM. Nhân viên An chuyển từ Sales sang Finance ngày 01/12; một tháng sau An nghỉ việc. Đây là tình huống minh họa, không mô tả một sản phẩm cụ thể.

### 18.1. Khi Mover

| Bước | Dữ liệu mong đợi | Rủi ro nếu thiếu |
| --- | --- | --- |
| HRIS phát thay đổi bộ phận có thời điểm hiệu lực. | `departmentId=FINANCE`, manager mới. | IAM xử lý sai ngày hoặc sai người. |
| IAM tính quyền mới và quyền phải thu hồi. | Thêm finance-reader, bỏ sales-reader. | Tích lũy cả hai quyền. |
| Directory cập nhật entry và group. | Account ID giữ nguyên, membership đúng. | DN/username thay đổi dẫn đến liên kết sai. |
| IdP cập nhật claim/nhóm liên quan. | Dữ liệu mới đến nơi xác thực/SSO. | Token cache chứa nhóm cũ. |
| SaaS nhận SCIM cập nhật và đối soát. | Role ứng dụng đúng Finance, không còn Sales. | IdP thành công nhưng app vẫn còn quyền cũ. |

Nếu SaaS trả **403** ở chức năng Finance, phải kiểm **SCIM/role/ABAC** trước khi nghĩ tới việc reset password. Đồng thời phải chứng minh quyền Sales bị thu hồi.

### 18.2. Khi Leaver

| Bước | Kết quả mong đợi | Cần xác minh |
| --- | --- | --- |
| HRIS thông báo kết thúc. | Event Leaver đúng subject/engagement và giờ hiệu lực. | Nguồn đáng tin, ngày giờ và phiên bản. |
| Directory/IdP khóa account. | Không cho đăng nhập mới theo chính sách. | Tài khoản phụ, account admin liên quan. |
| IAM thu hồi entitlement. | Group/role Finance, VPN, SaaS, credential mất hiệu lực. | Không còn quyền trực tiếp, nested groups, PAT. |
| SCIM/API deprovision SaaS. | Local account bị vô hiệu hóa theo cơ chế đích. | Phản hồi và đọc lại trạng thái. |
| Session/token xử lý. | Đường truy cập cũ không còn hiệu lực trong phạm vi. | Cửa sổ tồn dư do cache, token TTL và phiên ứng dụng. |
| Chuyển giao dữ liệu. | Owner hợp lệ nhận tài sản công việc cần giữ. | Không kích hoạt lại user chỉ để truy cập tài liệu. |

**Điểm học được:** cả “AD account disabled” và “SCIM active=false” đều là bằng chứng ở **một lớp**, chưa chứng minh mọi SaaS session hoặc API credential độc lập đã vô hiệu hóa.

## 19. Khắc phục lỗi User directory theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý an toàn |
| --- | --- | --- |
| **User không được tìm thấy** | Base DN/scope/filter sai; đồng bộ Joiner chưa chạy; mapping ID sai. | Kiểm object ID, source event, OU và quyền đọc, không tạo duplicate vội. |
| **LDAP Bind thất bại** | Credential, account state, TLS, policy, endpoint. | Phân loại lỗi tại server, không tắt TLS hoặc dùng admin credential để thử. |
| **User hiện tại directory nhưng SSO lỗi** | IdP đồng bộ trễ, federation config, MFA, local account. | Kiểm từng lớp IdP → SAML/OIDC → app; không kết luận từ LDAP entry. |
| **Nhóm mới không có hiệu lực** | Replica/cache, nested group, connector, app mapping. | Xác minh effective membership tại nơi thực thi. |
| **Nhân viên đổi tên đăng nhập bị tạo tài khoản mới** | Mapping dựa email/UPN/DN thay vì ID ổn định. | Dừng tự gộp, xác minh ID và liên kết account đúng. |
| **Manager mới không xuất hiện** | Manager entry chưa tồn tại ở đích hoặc DN/SCIM ID sai. | Resolve manager theo hệ thống đích, ghi ngoại lệ. |
| **Tài khoản Leaver vẫn dùng được SaaS** | Local account, PAT, session, SCIM lỗi. | Deprovision/thu hồi từng đường, đối soát và xử lý sự cố nếu cần. |
| **Directory trả kết quả khác giữa các server** | Replication lag, routing, lỗi replica. | Kiểm sức khỏe replication, thời gian hội tụ và tính nhất quán. |
| **Truy vấn directory chậm** | Filter không chọn lọc, index, paging hoặc tải cao. | Giới hạn thuộc tính/scope, điều chỉnh query và theo dõi performance. |

Với lỗi xác thực và phân quyền, **không yêu cầu người dùng gửi password, token hoặc private key qua ticket/chat**. Các chỉ số và dấu vết kỹ thuật đã được che thông tin nhạy cảm thường đủ để định vị lớp lỗi.

## 20. Chỉ số đánh giá chất lượng directory trong IAM

| Chỉ số | Cách đo gợi ý | Ý nghĩa |
| --- | --- | --- |
| **Tỷ lệ user có liên kết định danh ổn định** | Directory account được gắn đúng subject/engagement và source ID ÷ tổng user trong phạm vi. | Giảm trùng và gắn nhầm người. |
| **Tỷ lệ Joiner được cấp phát đúng hạn** | Joiner đủ điều kiện có account/nhóm được xác minh ÷ Joiner cần xử lý. | Đo mức sẵn sàng truy cập. |
| **Độ trễ cập nhật Mover** | Từ effectiveAt của nguồn đến lúc directory/IdP/app đạt trạng thái mong đợi. | Giám sát độ tươi thuộc tính và quyền. |
| **Tỷ lệ Leaver vô hiệu hóa đầy đủ** | Account/quyền trên các hệ thống đích đã xác minh thu hồi ÷ account/quyền phải thu hồi. | Phát hiện truy cập tồn dư. |
| **Số account trùng hoặc không có owner** | User entry không giải quyết được tới chủ thể/quan hệ hợp lệ. | Nguy cơ tài khoản mồ côi. |
| **Tỷ lệ thuộc tính quan trọng đúng nguồn** | Department/manager/state khớp nguồn có thẩm quyền ÷ hồ sơ được kiểm tra. | Chất lượng ánh xạ và cập nhật. |
| **Replication lag / connector lag** | Thời gian hội tụ giữa những bản sao/đích liên quan. | Phát hiện dữ liệu cũ gây lỗi xác thực/quyền. |
| **Số sửa group đặc quyền ngoài quy trình** | Sự kiện membership không có policy/approval hợp lệ. | Phát hiện nâng quyền hoặc drift. |
| **Tỷ lệ audit trail đầy đủ** | Thay đổi có nguồn → IAM policy → directory → app verification ÷ tổng thay đổi cần kiểm toán. | Khả năng truy vết. |
| **Số ngoại lệ quá hạn** | Connector lỗi, account sai trạng thái, duplicate và trường hợp chưa xác minh. | Nợ bảo mật và sự cố vận hành. |

Các chỉ số phải nêu **phạm vi directory, ứng dụng, loại tài khoản và phương pháp xác minh**. Không công bố “100% deprovision” khi còn ứng dụng không thể kiểm kê hoặc không có cách xác nhận phiên/token.

## 21. Checklist triển khai User directory

1. Có phân biệt **directory, HRIS, IAM/IGA, IdP, SCIM và quyền của ứng dụng** không?
2. Đã xác định **schema, object class, DN/RDN, namespace, nhóm, thuộc tính bắt buộc** và nguồn có thẩm quyền chưa?
3. Có **stable subject ID** và bảng liên kết từ HRIS/engagement sang directory object, IdP và SCIM user ID không?
4. Có tránh dùng email, displayName hoặc DN làm khóa bất biến duy nhất không?
5. Có quy tắc xử lý **đổi tên, chuyển OU, tái tuyển dụng, trùng người và nhiều engagement** không?
6. Truy vấn LDAP có **TLS, xác minh chứng chỉ, escape filter, least privilege, giới hạn truy vấn** và credential bảo vệ không?
7. Quyền sửa user, manager, group đặc quyền, reset password và xóa account có được phân tách không?
8. **Joiner** được xác minh và kích hoạt đúng Start date/chính sách, không cấp quyền quá sớm không?
9. **Mover** có cập nhật thuộc tính/nhóm đúng thời điểm, **thu hồi quyền cũ** và đối soát app không?
10. **Leaver** có khóa directory/IdP, disable local account, xử lý session/token/API key và giữ audit cần thiết không?
11. Có kiểm nhóm trực tiếp/lồng nhau/động và tác động tới **RBAC/ABAC** ở nơi thực thi quyền không?
12. Service account, tài khoản admin và thiết bị có **owner/chính sách riêng**, không bị xử lý giống Employee một cách máy móc không?
13. Đồng bộ/replication có phát hiện stale event, duplicate, lỗi từng đích và thay đổi thủ công ngoài IAM không?
14. Có quy trình kiểm tra **trạng thái thực tế ở IdP, ứng dụng và API**, thay vì chỉ dựa trên lệnh directory update không?
15. Directory và log có được tối thiểu hóa dữ liệu cá nhân, bảo vệ ACL, backup và lịch lưu giữ không?
16. Có thể truy vết từ sự kiện JML tới **user entry, group, role, API/SSO session và kết quả cuối** mà không lưu credential bí mật không?

**Ghi nhớ:** **User directory là kho cấu trúc và tra cứu dữ liệu tài khoản người dùng, thuộc tính và quan hệ nhóm trong hệ sinh thái IAM**. Muốn quản lý vòng đời an toàn, cần liên kết **đúng chủ thể với đúng bản ghi directory bằng ID ổn định**, xác định nguồn có thẩm quyền, đồng bộ thuộc tính và trạng thái đúng thời điểm, bảo vệ LDAP/API bằng TLS và quyền tối thiểu. **Directory update không đồng nghĩa đã cấp hoặc thu hồi quyền thành công**: Joiner, Mover và Leaver chỉ được xác minh hoàn tất khi IdP, SCIM/ứng dụng và các đường truy cập liên quan phản ánh đúng chính sách, có dấu vết kiểm toán và không còn quyền tồn dư ngoài ý muốn.
