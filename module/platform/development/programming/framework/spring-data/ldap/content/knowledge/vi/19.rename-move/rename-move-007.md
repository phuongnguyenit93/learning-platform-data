# Giới hạn của cơ chế tự cập nhật tham chiếu theo máy chủ

## Mục tiêu bài học

Trong **SPRING_DATA_LDAP**, ứng dụng Java làm việc với directory qua **LdapTemplate** hoặc **Spring Data LDAP repository**, ánh xạ các entry phân cấp sang object Java theo **DN**, **objectClass** và schema. Khi đổi tên hoặc chuyển một entry sang OU khác, **DN của entry thay đổi**. Nếu entry đó được các nhóm, người quản lý, ứng dụng hoặc hệ thống khác tham chiếu bằng DN cũ, các tham chiếu ấy sẽ ra sao?

Một số LDAP server cung cấp **referential integrity**: khi một entry bị rename, move hoặc delete, server có thể tự cập nhật/xóa một số thuộc tính tham chiếu đến DN cũ. Nhưng **khả năng tự cập nhật phụ thuộc sản phẩm, loại thuộc tính, cấu hình plugin/overlay, naming context, ACL, replication và thời điểm quan sát**. LDAP protocol không bảo đảm rằng *mọi chuỗi có dạng DN trong mọi hệ thống* được tự động sửa.

Bài thuộc chương **Đổi tên và di chuyển**, trực tiếp giải thích **giới hạn của cơ chế tự cập nhật tham chiếu theo máy chủ** và cách ứng dụng Spring Data LDAP xác minh, đối soát hoặc tự sửa những tham chiếu ngoài phạm vi tự động.

Sau bài học, bạn có thể:

- Phân biệt **Modify DN (rename/move)** với **Modify attribute** và việc sửa các *reference attributes*.
- Giải thích vì sao đổi DN không mặc định cập nhật **member**, **uniqueMember**, **manager**, **seeAlso**, **owner**, các trường tùy chỉnh hay khóa ngoại ở hệ thống khác.
- Đánh giá sự khác nhau giữa **OpenLDAP refint overlay**, **Red Hat/389 Directory Server Referential Integrity plugin** và **AD DS linked attributes**.
- Xác định giới hạn của **naming context**, phạm vi tìm tham chiếu, thuộc tính có **DN syntax**, độ trễ cập nhật/replication và nhóm có giá trị bắt buộc.
- Dùng **LdapTemplate.rename(Name, Name)** với DN tương đối; đọc lại entry và kiểm tra group membership sau khi move.
- Biết khi nào cần **đối soát bằng ứng dụng**, không tự sửa hai lần một tham chiếu server đã tự cập nhật.
- Thiết kế kế hoạch migration/reconciliation có idempotency, audit, ACL và kiểm thử tích hợp trên đúng directory đích.

## 1. Tình huống: chuyển người dùng nhưng nhóm vẫn tham chiếu DN cũ

Directory ví dụ:

~~~text
dc=example,dc=org
├── ou=people
│   ├── ou=employees
│   │   └── uid=an
│   └── ou=alumni
└── ou=groups
    └── cn=backend
~~~

Trước khi chuyển An:

~~~ldif
dn: uid=an,ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org

dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

Một thao tác **Modify DN** chuyển An sang:

~~~text
uid=an,ou=alumni,ou=people,dc=example,dc=org
~~~

**Hai trạng thái cần kiểm tra riêng biệt:**

1. Entry An ở DN mới và không còn ở DN cũ — kết quả của thao tác rename/move.
2. Thuộc tính **member** của nhóm backend chứa DN mới thay vì DN cũ — kết quả của cơ chế duy trì tham chiếu, **nếu server hỗ trợ và được cấu hình phù hợp**.

Một server không có cơ chế tự cập nhật có thể cho phép rename thành công nhưng giữ nguyên:

~~~ldif
member: uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

Lúc đó nhóm chứa **dangling reference**: một giá trị DN trỏ tới entry đã đổi tên hoặc không còn ở vị trí cũ.

~~~mermaid
flowchart TD
    A["LDAP Modify DN: oldDn → newDn"] --> B["Entry chuyển tới newDn"]
    B --> C{"Server có duy trì đúng loại tham chiếu?"}
    C -->|Có và trong phạm vi| D["Sửa member/thuộc tính được cấu hình"]
    C -->|Không hoặc ngoài phạm vi| E["DN cũ có thể còn trong nơi tham chiếu"]
    D --> F["Ứng dụng kiểm tra lại"]
    E --> F
    F --> G{"Actual state đúng mong đợi?"}
    G -->|Có| H["Hoàn tất và làm mới cache"]
    G -->|Không| I["Đối soát / sửa có điều kiện / cảnh báo"]
~~~

**Kết luận quan trọng:** “LDAP rename trả success” xác nhận một operation theo giao thức đã được server chấp nhận; **không phải bằng chứng mọi danh sách thành viên, mọi tham chiếu hoặc cache ứng dụng đã đồng bộ**.

## 2. Ba khái niệm khác nhau: vị trí, tham chiếu và định danh người dùng

| Khái niệm | Ví dụ | Bản chất | Ảnh hưởng sau rename/move |
| --- | --- | --- | --- |
| **DN của entry** | uid=an,ou=employees,ou=people,dc=example,dc=org | Tên phân biệt trong cây LDAP | **Thay đổi** theo vị trí/RDN mới |
| **RDN** | uid=an | Tên của entry trong phạm vi parent | Có thể giữ nguyên khi chuyển OU, hoặc thay khi rename |
| **Thuộc tính tham chiếu DN** | member: uid=an,... | Giá trị trong entry **khác** trỏ tới một DN | Chỉ được sửa tự động khi có hỗ trợ/chính sách |
| **Tên đăng nhập** | uid: an | Thuộc tính nghiệp vụ/xác thực | Không nhất thiết thay khi move; không phải DN |
| **ID server-managed** | entryUUID / objectGUID | Định danh do server quản lý, tùy sản phẩm | Có thể giữ nguyên qua rename trong cùng directory, phải kiểm chứng |
| **Dữ liệu tham chiếu ngoài LDAP** | SQL user.ldap_dn, Redis key, message | Bản sao/khóa của ứng dụng khác | LDAP server **không thể tự sửa** |

### 2.1. RDN và DN không phải login name

Một entry có thể có DN **cn=An Tran,ou=people,...** nhưng vẫn chứa **uid: an** hoặc **userPrincipalName: an@corp.example.org**. Trong Active Directory, **sAMAccountName**, **userPrincipalName** và **distinguishedName** là những dữ liệu khác nhau.

Nếu user chuyển OU mà giữ nguyên uid, login theo uid có thể tiếp tục hoạt động **nếu search base/authentication policy còn cho phép**, trong khi cache chứa DN cũ có thể hỏng. Không suy rằng “move user” đồng nghĩa “đổi username” hoặc “đổi mọi reference”.

### 2.2. Không phải mọi chuỗi giống DN đều là thuộc tính DN

Một thuộc tính chuẩn như **member** của **groupOfNames** thường có cú pháp DN. Một thuộc tính tùy chỉnh **legacyMemberText** lại có thể là **Directory String** chứa các ký tự trông giống DN. Server không nhất thiết hiểu nó là tham chiếu, dù giá trị nhìn bằng mắt giống **uid=an,...**.

Tương tự, **memberUid** ở một số schema nhóm kiểu **posixGroup** lưu username (thường là chuỗi), **không phải full DN**. Chuyển user sang OU khác không tự có nghĩa thay memberUid; đổi uid lại là vấn đề khác. Cơ chế refint dựa trên DN không thể sửa mọi dữ liệu không có DN syntax.

## 3. LDAP Modify DN không quy định tự sửa mọi tham chiếu

**RFC 4511** định nghĩa **Modify DN operation** để đổi RDN hoặc chuyển entry tới vị trí mới, khi server và naming context cho phép. Request có **entry**, **newRDN**, **deleteOldRDN** và **newSuperior** (khi dùng chuyển parent). Đây **không phải** LDAP Modify request cho mọi entry liên quan.

Một thao tác rename có thể thay:

~~~text
Old: cn=An Tran,ou=employees,dc=example,dc=org
New: cn=An Nguyen,ou=employees,dc=example,dc=org
~~~

Một thao tác move có thể thay:

~~~text
Old: uid=an,ou=employees,dc=example,dc=org
New: uid=an,ou=alumni,dc=example,dc=org
~~~

Những vấn đề vẫn riêng biệt:

- Có cập nhật **member**, **uniqueMember**, **manager**, **owner**, **seeAlso** không?
- Có xử lý các entry **con** khi đổi tên OU cha theo cách ứng dụng mong đợi không?
- Có cập nhật DN trong group ở **backend khác**, trên **server khác**, một **domain/naming context khác** không?
- Có sửa **LDAP URL**, custom string, các điều kiện nhóm động hoặc DN lưu trong database ứng dụng không?
- Có cập nhật ngay trước response hay qua hàng đợi/post-operation plugin, khiến client tạm thấy giá trị cũ không?

**RFC về Modify DN không áp đặt câu trả lời “có” cho tất cả các câu hỏi ấy.** Đây là chức năng ở tầng directory implementation và cấu hình vận hành.

### 3.1. Đổi DN của entry và sửa reference có thể khác thời điểm

~~~mermaid
sequenceDiagram
    participant App as Spring service
    participant Server as LDAP server
    participant Plugin as Referential integrity
    participant Reader as Client khác
    App->>Server: Modify DN old → new
    Server->>Server: Thay vị trí/tên entry
    Server-->>App: success
    opt Server dùng cập nhật tham chiếu sau operation
        Plugin->>Server: Tìm và sửa reference attrs
        Reader->>Server: Đọc member lúc update chưa hoàn tất
        Server-->>Reader: Có thể thấy DN cũ
    end
    App->>Server: Kiểm tra member sau rename
    Server-->>App: Actual member values
~~~

Sơ đồ diễn tả **một khả năng triển khai có cập nhật sau operation**, không khẳng định mọi server trả response trước khi sửa reference. Một số sản phẩm/cấu hình cập nhật đồng bộ, sản phẩm khác cho phép trì hoãn; replication còn có thể tạo độ trễ giữa các node. **Thời điểm chính xác phải kiểm tra theo server đích.**

## 4. Referential integrity theo từng directory server

| Directory | Cơ chế có liên quan | Giới hạn cần xác minh |
| --- | --- | --- |
| **OpenLDAP slapd** | **slapo-refint overlay** nếu được bật và cấu hình | Chỉ theo dõi những DN-valued attributes và backend/phạm vi được cấu hình; không tự bảo vệ dữ liệu ngoài LDAP |
| **Red Hat / 389 Directory Server** | **Referential Integrity plugin** | Có thể tắt; thuộc tính, scope, thời gian update và replication phụ thuộc cấu hình |
| **Active Directory Domain Services (AD DS)** | **linked attributes** và cơ chế duy trì liên kết đối tượng, ví dụ **member** | Chỉ những mối liên kết được mô hình AD hỗ trợ; không bao phủ mọi custom string, app DB hoặc LDAP bên ngoài |
| **LDAP directory khác** | Chính sách riêng hoặc không có refint | Kiểm tra tài liệu sản phẩm và integration test; không suy từ thao tác Modify DN |

Không lấy hành vi thành công trên server test này để kết luận server production khác sẽ tự cập nhật y hệt. Ngay **cùng một sản phẩm**, bật/tắt overlay, cấu hình attribute list hoặc mô hình replication khác nhau đã có thể làm kết quả thay đổi.

## 5. OpenLDAP: slapo-refint không tự bật trong mọi hệ thống

OpenLDAP cung cấp **Referential Integrity Overlay** để quản lý những attribute chứa DN được chỉ định. Khi một entry bị **modrdn/rename** hoặc **delete**, overlay có thể tìm các reference đến DN đó và cập nhật hoặc xóa giá trị tương ứng.

Một cấu hình theo cú pháp **slapd.conf** để *minh họa ý nghĩa*, không phải lệnh áp thẳng lên production:

~~~text
# Ví dụ cấu hình server-side; không nằm trong application.yml.
overlay refint
refint_attributes member manager owner seeAlso
refint_nothing "cn=refint-placeholder,ou=system,dc=example,dc=org"
~~~

**Lưu ý quan trọng về cấu hình:**

1. **refint_attributes** liệt kê *đích danh* các thuộc tính mà overlay xử lý; không bao trùm mọi attribute một cách tự động. Những attribute này phải có **distinguishedName syntax** phù hợp.
2. **member** của groupOfNames có thể khớp một người dùng sắp được chuyển, nhưng **legacyMemberText** kiểu chuỗi không được sửa chỉ vì chứa văn bản giống DN. **uniqueMember** của groupOfUniqueNames dùng cú pháp **Name And Optional UID**, không đồng nhất với cú pháp **distinguishedName** thuần: đừng đưa nó vào refint_attributes của OpenLDAP nếu chưa kiểm tra hỗ trợ và yêu cầu cú pháp ở phiên bản cụ thể.
3. **refint_nothing** có thể cung cấp DN thay thế khi xóa reference cuối cùng sẽ làm vi phạm schema, chẳng hạn **groupOfNames yêu cầu ít nhất một member**. Đây là **placeholder có hậu quả nghiệp vụ/bảo mật**, không nên sử dụng một principal đang có quyền hoặc DN tùy ý mà không được phê duyệt.
4. Ví dụ chỉ dành để đọc hiểu. Với OpenLDAP sử dụng **cn=config** và backend thực tế, quản trị viên phải cấu hình overlay đúng vị trí, quyền và chính sách replication.
5. Các thay đổi do overlay phát sinh có đặc thù replication: theo tài liệu **slapo-refint(5)**, thay đổi của overlay không mặc định được lan truyền như một thao tác bình thường trong một số mô hình, nên cần đặt chính sách trên các replica/consumer phù hợp. **Không giả định một provider bật overlay là toàn bộ cluster nhất quán.**

### 5.1. Ví dụ với member khi rename

Trước:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

Sau khi đổi An sang nhánh **alumni**, **nếu refint được bật và member thuộc phạm vi được quản lý**, giá trị kỳ vọng:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=alumni,ou=people,dc=example,dc=org
~~~

Nếu overlay **không bật**, **member** có thể còn DN cũ. Nếu đang xóa An chứ không rename, overlay có thể xóa giá trị **member**. Khi đó nếu An là thành viên **cuối**, **groupOfNames** có ràng buộc **MUST member**, khiến hệ thống cần chính sách **refint_nothing**, không được giả định nhóm rỗng hợp lệ.

### 5.2. Chỉ mục và chi phí cập nhật

Overlay phải tìm các entry chứa DN cũ trong các thuộc tính được quản lý. Nếu những thuộc tính này không có index phù hợp, hoặc chứa vô số nhóm/reference, **rename/delete có thể trở thành thao tác tốn tài nguyên**. Chọn index theo workload với sự tham gia của quản trị viên; index giúp tra cứu nhưng cũng có chi phí lưu trữ và cập nhật.

**Tự cập nhật tham chiếu không miễn phí.** Đo latency của rename, lượng entry bị cập nhật, tải backend và thời gian replication, nhất là khi chuyển/xóa một OU chứa nhiều entry.

## 6. Red Hat / 389 Directory Server: plugin có cấu hình riêng

Red Hat Directory Server, dựa trên hệ sinh thái 389 Directory Server, có **Referential Integrity plugin**. Khi được bật, plugin có thể duy trì những reference attributes như **member**, **uniqueMember**, **owner**, **seeAlso** khi entry bị rename/move/delete, theo phiên bản và danh sách thuộc tính đã cấu hình.

Điểm cần kiểm tra ở server đích:

| Nội dung cấu hình | Câu hỏi vận hành |
| --- | --- |
| **Plugin có bật không?** | Môi trường dev/staging/prod có cùng cấu hình không? |
| **Danh sách attributes** | Chỉ member, hay còn uniqueMember, manager hoặc custom DN attributes? |
| **Entry scope và update scope** | Plugin có quan sát entry bị đổi tên và có tìm các nhóm ở OU liên quan không? |
| **Update delay / lịch xử lý** | Mỗi reference được sửa đồng bộ hay có thể xuất hiện trạng thái trung gian? |
| **Replication topology** | Có nhiều suppliers không; plugin được bật và cấu hình trên những node nào? |
| **Index và tải** | Thuộc tính tham chiếu đã có index phù hợp chưa; thao tác move có đột ngột chậm không? |
| **ACL và hoạt động plugin** | Plugin có thực hiện được internal modification và lỗi được ghi nhận/giám sát không? |

Một điểm khác biệt đáng chú ý so với lối suy nghĩ “rename đã trả success là tất cả xong”: tài liệu Red Hat mô tả **post-operation referential integrity** và tùy chọn **trì hoãn cập nhật**. Điều đó có nghĩa một hệ thống có thể quan sát **entry ở DN mới nhưng một số tham chiếu chưa chuyển ngay**, tùy cấu hình. Với môi trường nhiều supplier, chính sách plugin/replication phải được triển khai đồng bộ.

**Không copy cú pháp OpenLDAP** như **overlay refint** vào Red Hat Directory Server: đây là plugin có cách quản lý, tùy chọn và semantics riêng. Hãy xem cấu hình bằng công cụ quản trị thích hợp với đúng phiên bản, thay vì suy từ tên tính năng giống nhau.

## 7. Active Directory: linked attributes không bao phủ mọi tham chiếu

Trong **Active Directory Domain Services (AD DS)**, thuộc tính **member** của group là một **linked reference** đến user/group/contact object. Microsoft mô tả rằng khi một member object được rename hoặc move, AD DS **tự duy trì DN hiển thị ở member**.

Ví dụ:

~~~text
User trước move:
  CN=An Tran,OU=Employees,DC=corp,DC=example,DC=org

User sau move:
  CN=An Tran,OU=Alumni,DC=corp,DC=example,DC=org

Group member:
  DN cũ -> DN mới (theo linked-reference semantics của AD DS)
~~~

Đây là khác biệt quan trọng so với một LDAP server chỉ lưu giá trị DN như một chuỗi/attribute không có refint. Tuy nhiên, **khả năng linked-object không phải dịch vụ sửa mọi bản sao của DN**.

### 7.1. Forward link và backlink

| Thuộc tính / khái niệm | Vai trò |
| --- | --- |
| **member** của group | Forward link chứa liên kết tới các đối tượng thành viên |
| **memberOf** của user | Backlink phản ánh những group memberships tương ứng |
| **primaryGroupID** | Cơ chế primary group riêng trong AD; không nên suy primary group luôn xuất hiện qua memberOf như group thường |
| **manager/directReports** | Các thuộc tính linked reference khác của AD theo schema, khác với chuỗi text tùy chỉnh |
| **distinguishedName** | DN hiện tại của object; thay đổi theo rename/move |
| **objectGUID** | Định danh đối tượng do AD quản lý; không thay thế DN trong mọi LDAP API |

Đối với AD DS, **memberOf** thông thường là backlink được tính/duy trì từ quan hệ membership, không phải thuộc tính đa giá trị mà ứng dụng nên tự tùy ý **REPLACE** để sửa membership. Thay đổi membership thường thực hiện thông qua **group.member** hoặc API quản trị được hỗ trợ.

**Primary group là ngoại lệ quan trọng:** không dùng danh sách **memberOf** đơn thuần để kết luận toàn bộ group membership hiệu lực của user AD. Ngoài primaryGroupID, nested groups, group scope, dynamic authorization và token evaluation cũng có ngữ nghĩa riêng.

### 7.2. Các giới hạn mà linked attributes không giải quyết

- Giá trị **customProfileDn** lưu dạng **Directory String** thay vì linked DN attribute.
- Danh sách DN nằm trong JSON, LDAP URL, mô tả text, Java properties hoặc SQL/Redis cache.
- References trong một **LDAP server độc lập**, ứng dụng SaaS khác hay kho dữ liệu được đồng bộ bất đồng bộ.
- Dữ liệu của AD Domain/Forest khác nếu mối quan hệ không được mô hình dưới dạng liên kết được AD hỗ trợ và quản trị đúng.
- Thành viên nhóm kiểu ứng dụng khác, mapping role dựa trên username hoặc script cố định DN cũ.
- Hệ thống đọc từ replica hoặc Global Catalog có dữ liệu chưa đồng bộ theo yêu cầu quan sát.

**Không tự động sửa group.member trong AD sau mỗi move** chỉ vì một service muốn “chắc ăn”: nếu AD đã duy trì liên kết, thao tác sửa dư có thể trả lỗi giá trị không tồn tại/đã có, xung đột với một tác nhân khác hoặc tạo chi phí không cần thiết. Việc cần làm đầu tiên là **đọc lại và xác minh**.

### 7.3. Di chuyển cross-domain/cross-forest không phải rename thường

Move một object giữa hai OU thuộc cùng naming context thường khác với **cross-domain move** hoặc migration giữa forest. Các thao tác sau có chính sách, công cụ, quyền và giới hạn riêng; một số thao tác không thể biểu diễn như một **LdapTemplate.rename** đơn giản.

Không suy rằng objectGUID, objectSID, DN, ACL, primary group, account logon name và mọi linked reference đều giữ nguyên hoặc được cập nhật tự động sau migration. Với trường hợp này phải có **quy trình AD migration được phê duyệt**, bao gồm mapping định danh và reconciliation, thay vì gọi rename theo suy đoán.

## 8. Ranh giới của cơ chế tự cập nhật

Các tình huống sau giúp phân loại rõ **“server có thể sửa”** và **“không thể kỳ vọng”**.

| Nơi có reference | Ví dụ | Có thể tự cập nhật khi rename? | Điều kiện/hành động |
| --- | --- | --- | --- |
| **Group DN attribute cùng LDAP server** | groupOfNames.member | **Có thể** | Server hỗ trợ refint/linked attribute, scope và attribute được chọn |
| **DN-valued custom attribute** | owner, manager theo schema | **Có thể** | Có DN syntax, thuộc phạm vi refint/linked schema và policy |
| **uniqueMember** | groupOfUniqueNames.uniqueMember | **Phụ thuộc** | Cú pháp Name And Optional UID; kiểm tra sản phẩm/plugin cụ thể |
| **posixGroup.memberUid** | memberUid: an | **Không nên kỳ vọng do đổi DN** | Lưu username thay vì DN; xử lý khi login identifier thay đổi |
| **Thuộc tính text tùy chỉnh** | description: uid=an,... | **Không** theo cơ chế DN thông thường | Ứng dụng quản lý dữ liệu string |
| **LDAP URL hoặc filter string** | ldap:///ou=employees,... | **Không** | Cập nhật cấu hình/URL/filter theo quy tắc riêng |
| **Nhóm động** | memberURL với LDAP filter | **Không đồng nghĩa** rewrite URL | Membership là kết quả tính theo filter; cần test kết quả sau move |
| **Các group ở backend/naming context khác** | member trỏ ra suffix khác | **Không bảo đảm** | Kiểm tra scope, federation, referral, backend và replication |
| **SQL/Redis/search index** | user.ldap_dn | **Không** | Application event, outbox, reconciliation |
| **Cấu hình quyền/ứng dụng ngoài LDAP** | Policy chứa DN cũ | **Không bảo đảm** | Sửa tại hệ thống sở hữu policy đó |
| **Cache client đã đọc DN** | Session lưu oldDn | **Không** | Invalidate/refresh bằng stable ID hoặc directory event |
| **Entry nằm ngoài nơi tài khoản có thể đọc** | Nhánh bảo vệ bằng ACL | **Không quan sát được** qua tài khoản đó | Kiểm tra bằng tài khoản kiểm thử/admin được cấp phép |

### 8.1. Rename một OU có nhiều entry con

Ví dụ:

~~~text
Trước:
  ou=employees,dc=example,dc=org
  uid=an,ou=employees,dc=example,dc=org
  uid=binh,ou=employees,dc=example,dc=org

Sau:
  ou=staff,dc=example,dc=org
  uid=an,ou=staff,dc=example,dc=org
  uid=binh,ou=staff,dc=example,dc=org
~~~

**DN của mọi entry con cũng đổi về mặt đường dẫn** khi ancestor được rename. Nhưng server có tự sửa **tất cả reference trỏ tới descendants** không là câu hỏi riêng, tùy cách plugin/overlay theo dõi rename subtree và phạm vi cấu hình. Một plugin chỉ nhận sự kiện liên quan DN của OU cha có thể không xử lý mọi chuỗi DN con theo cách bạn mong đợi.

**Cần integration test cho cả ancestor và descendant DN**, không chỉ kiểm tra entry OU cha. Trên một số directory, thao tác đổi tên entry có con còn bị giới hạn hoặc yêu cầu bước nghiệp vụ đặc thù.

### 8.2. Xóa entry và ràng buộc member bắt buộc

Nếu nhóm groupOfNames chỉ có một **member**, xóa user đó và xóa luôn reference có thể khiến nhóm không còn **member** — vi phạm objectClass **groupOfNames**. Vì vậy một số server/plugin có chính sách thay thế bằng placeholder hoặc từ chối operation.

Không coi placeholder là “thành viên vô hại” một cách mặc định. Nếu placeholder DN trỏ tới tài khoản có quyền, nó có thể vô tình cấp quyền; nếu placeholder không trỏ tới entry thật, ứng dụng/group sync có thể xử lý không như mong đợi. Thiết kế phải được **quản trị viên directory và chủ sở hữu IAM** phê duyệt.

### 8.3. Lặp lại thao tác có thể gây race

Giả sử rename đã thành công, server tự cập nhật group.member, rồi ứng dụng tiếp tục cố:

~~~text
REMOVE_ATTRIBUTE member=oldDn
ADD_ATTRIBUTE    member=newDn
~~~

Nếu oldDn đã được server xóa, thao tác remove có thể thất bại với **noSuchAttribute (16)**; nếu newDn đã có, thao tác add có thể thất bại với **attributeOrValueExists (20)**. Quan trọng hơn, một client khác có thể thay đổi membership trong lúc bạn đang kiểm tra.

**Vì vậy không chạy “sửa lại tất cả references” một cách vô điều kiện.** Dùng chiến lược **quan sát → so sánh → sửa có điều kiện nếu cần → đọc lại**, giữ nhật ký thao tác và có cơ chế dừng khi gặp dữ liệu không nhất quán.

## 9. Nhận biết và kiểm chứng server có tự sửa reference hay không

Một checklist thực tế cho đội phát triển và quản trị:

1. **Xác định server**: OpenLDAP, AD DS, 389 DS hoặc một sản phẩm LDAP khác, cùng phiên bản và backend.
2. **Liệt kê reference attributes** thật sự dùng: member, uniqueMember, manager, owner, seeAlso, các custom attribute, cache và bên ngoài LDAP.
3. **Kiểm tra schema**: attribute mang DN syntax, NameAndOptionalUID hay Directory String? Phải dùng cách so sánh/phân giải phù hợp.
4. **Xác minh cơ chế**: overlay/plugin có bật không, AD có linked attribute thật không, attribute list và scope là gì?
5. **Tìm giới hạn directory**: rename trong naming context nào, có support move across parent hay không, có referral/backend khác không?
6. **Kiểm tra tài khoản/ACL**: service account có quyền rename, đọc nhóm và kiểm tra kết quả không? Server plugin có quyền internal modification?
7. **Xác minh replication**: sau bao lâu các node khác nhìn thấy DN/reference mới? Đừng kiểm tra ngay tại replica chậm rồi kết luận refint không hoạt động.
8. **Dùng fixture có chủ đích**: user thuộc hai nhóm, nested group, manager, memberUid, một custom string và cache ứng dụng.
9. **Đo hiệu năng**: số reference được sửa, thời gian rename, thời gian đồng bộ, tỷ lệ lỗi và tải tìm kiếm.
10. **Định nghĩa trách nhiệm**: cái gì server sở hữu, cái gì ứng dụng phải cập nhật; không để cả hai cùng ghi một reference mà không có phối hợp.

**Thử trên đúng directory đích** là quan trọng: một OpenLDAP test chưa bật refint không phản ánh AD DS linked attributes; một AD development domain không chứng minh mọi custom attribute trên LDAP production sẽ cập nhật.

## 10. Ví dụ Spring Boot: gọi Modify DN mà không đoán server sẽ sửa nhóm

Các ví dụ tiếp theo dùng Java 17+, Spring Boot với Spring LDAP và một directory test:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-directory,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**Tiền đề:** LDAP server có **ou=people**, hai nhánh **ou=employees** và **ou=alumni**, cùng **ou=groups**. Service account có quyền rename trong hai nhánh và đọc những group có liên quan. JVM xác minh certificate chain và hostname SAN; không bỏ qua TLS validation.

Các DN dùng trong Spring LDAP:

~~~text
ContextSource base:
  dc=example,dc=org

Old DN tương đối:
  uid=an,ou=employees,ou=people

New DN tương đối:
  uid=an,ou=alumni,ou=people

Full DN dùng trong group.member:
  uid=an,ou=alumni,ou=people,dc=example,dc=org
~~~

**Không gửi full DN có thêm suffix lần nữa vào template đã có base**; nhưng **member** lưu DN đầy đủ của user. Đó là hai ngữ cảnh khác nhau.

### 10.1. Đổi DN bằng LdapTemplate.rename

~~~java
package org.example.directory;

import javax.naming.Name;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryMoveService {
    private final LdapTemplate ldapTemplate;

    public DirectoryMoveService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void moveKnownUidFromEmployeesToAlumni(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        // Giả định rõ: mọi user của API này được đặt RDN uid
        // và nằm trực tiếp dưới ou=employees.
        Name oldDn = LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid)
                .build();
        Name newDn = LdapNameBuilder
                .newInstance("ou=alumni,ou=people")
                .add("uid", uid)
                .build();

        // Preflight: kiểm tra đúng entry dự định di chuyển.
        String actualUid = ldapTemplate.lookup(
                oldDn,
                new String[]{"uid"},
                (AttributesMapper<String>) attrs -> {
                    if (attrs.get("uid") == null) {
                        throw new IllegalStateException("Thiếu uid");
                    }
                    return (String) attrs.get("uid").get();
                });

        if (!uid.equalsIgnoreCase(actualUid)) {
            throw new IllegalStateException(
                    "DN cũ không chứa user mong đợi");
        }

        // Gửi LDAP Modify DN, KHÔNG mặc định sửa được group.member.
        ldapTemplate.rename(oldDn, newDn);
    }
}
~~~

**LdapTemplate.rename(Name, Name)** gửi thao tác đổi tên/chuyển entry tại directory; đó không phải “move một Java object” hay một phép cập nhật tất cả references do Spring thực hiện. Cả **oldDn** lẫn **newDn** trong ví dụ là **DN tương đối** theo base của ContextSource. Việc giữ nguyên RDN **uid=an** khi chuyển parent là một lựa chọn nghiệp vụ; ví dụ không giải quyết các entry dùng RDN **cn**.

**Chỉ gọi code này qua một endpoint đã phân quyền**: người gửi request không được tự chọn DN đích tùy ý để di chuyển user sang OU nhạy cảm. Dùng các đích từ allowlist chính sách nghiệp vụ. Preflight chỉ là kiểm tra đầu vào; một client khác vẫn có thể rename/move entry trước khi lời gọi thực tế tới server.

### 10.2. Khi username không trùng RDN hoặc entry nằm trong OU lồng nhau

Nếu directory có entry:

~~~ldif
dn: cn=An Tran,ou=employees,ou=people,dc=example,dc=org
uid: an
cn: An Tran
~~~

thì tự dựng DN **uid=an,ou=employees,...** là sai. Cần **search theo uid**, kiểm tra **0/1/nhiều kết quả**, lấy **DN thật** qua **ContextMapper/DirContextOperations.getDn()**, rồi mới quyết định new DN theo quy tắc giữ RDN hoặc thay RDN được phê duyệt.

~~~java
import java.util.List;
import javax.naming.Name;
import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

List<Name> actualDns = ldapTemplate.search(
        query().base("ou=employees,ou=people")
               .searchScope(SearchScope.SUBTREE)
               .attributes("uid")
               .countLimit(10)
               .timeLimit(2000)
               .where("objectClass").is("inetOrgPerson")
               .and("uid").is("an"),
        (ContextMapper<Name>) ctx ->
                ((DirContextOperations) ctx).getDn());

if (actualDns.size() != 1) {
    throw new IllegalStateException(
            "Không thể phân giải duy nhất DN của user");
}

Name oldRelativeDn = actualDns.get(0);
// oldRelativeDn là DN thực tế; bước xây new DN phải dùng naming
// policy được quản trị, không chỉ lấy username để đoán.
~~~

Đoạn này minh họa phần **identity resolution**. Trong ứng dụng thật, lỗi **size/time limit, partial result, referral** phải được phân loại riêng; nếu query bị cắt kết quả, không được khẳng định **duy nhất** chỉ vì danh sách tạm thời có một entry.

### 10.3. Spring Data LDAP repository sau rename

Repository ánh xạ DN bằng **@Id** kiểu **javax.naming.Name**, không phải username:

~~~java
package org.example.directory;

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
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    public PersonEntry() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }
    public String getSn() { return sn; }
    public void setSn(String sn) { this.sn = sn; }
}
~~~

~~~java
package org.example.directory;

import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

Sau rename, tìm lại theo **findByUid("an")** nếu scope repository bao phủ entry ở nhánh mới, kiểm tra **getDn()** đã phản ánh DN mới. **findById(oldDn)** không tự trở thành **findById(newDn)**.

Không dùng **repository.save(entity)** như một lệnh “rename và tự cập nhật group references”. Hành vi ODM khi thay ID hoặc tính DN mới còn phụ thuộc mapping và phiên bản, có thể bao gồm bind/unbind thay vì một Modify DN đơn giản. Đối với nhu cầu đổi DN rõ ràng, chủ động dùng **LdapTemplate.rename** hoặc API Modify DN được hỗ trợ, rồi đối soát tham chiếu như một công việc riêng.

## 11. Kiểm tra tham chiếu trước và sau move

Ứng dụng không nên đoán server có refint; có thể **lấy snapshot những nhóm đang tham chiếu DN cũ trước khi rename**, rồi kiểm tra sau khi server đã thực thi.

### 11.1. Tìm group có member DN cụ thể

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

@Service
public class GroupReferenceFinder {
    private final LdapTemplate ldapTemplate;

    public GroupReferenceFinder(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Name> findGroupDnsReferencing(String fullMemberDn) {
        if (fullMemberDn == null || fullMemberDn.isBlank()) {
            throw new IllegalArgumentException("DN không hợp lệ");
        }

        return ldapTemplate.search(
            query()
                .base("ou=groups")
                .searchScope(SearchScope.SUBTREE)
                .attributes("cn")
                .countLimit(500)
                .timeLimit(2000)
                .where("objectClass").is("groupOfNames")
                .and("member").is(fullMemberDn),
            (ContextMapper<Name>) ctx ->
                    ((DirContextOperations) ctx).getDn());
    }
}
~~~

**Filter (member=fullDn)** dùng matching rule LDAP cho attribute **member**; các ký tự đặc biệt trong giá trị được query builder escape phù hợp với cú pháp filter. Không tạo filter bằng **"(member=" + requestDn + ")"**.

Các điều kiện quan trọng:

- **fullMemberDn** là **DN đầy đủ**, không phải DN tương đối mà LdapTemplate dùng làm search base.
- **Attributes("cn")** chỉ cần cho ví dụ ánh xạ; **getDn()** của adapter lấy DN group theo quy ước ContextSource.
- **500 kết quả và 2.000 ms** chỉ là giới hạn ví dụ. Đừng tuyên bố tìm đủ mọi nhóm khi server có size/time limit hoặc filter bị cắt; cần paging hoặc chiến lược quét phù hợp.
- **ACL** có thể làm service account không thấy những group ngoài quyền đọc. “Không tìm thấy reference” không chứng minh “toàn directory không có reference”.
- Một group có thể dùng **uniqueMember**, schema tùy chỉnh hoặc thuộc tính khác. Hàm này chỉ tìm **groupOfNames.member** trong **ou=groups**.

### 11.2. Pre/post-check không phải transaction đa-entry

Quy trình:

~~~text
Before:
  expectedGroups = search member=oldFullDn

Rename:
  ldapTemplate.rename(oldRelativeDn, newRelativeDn)

After (có xét độ trễ/replication):
  staleGroups = search member=oldFullDn
  updatedGroups = search member=newFullDn

Đối chiếu từng expectedGroup:
  - có reference newDn, không còn oldDn → đạt kỳ vọng
  - vẫn còn oldDn → cần kiểm tra refint/repair policy
  - không còn cả hai → membership bị mất hoặc query/ACL có vấn đề
  - có cả hai → trạng thái mâu thuẫn, không tự sửa mù
~~~

Để làm đủ, cần giữ **operationId, oldDn, newDn, expectedGroups, directoryAlias và trạng thái quan sát** trong journal nếu workflow kéo dài hoặc phải phục hồi sau crash. Với plugin xử lý bất đồng bộ, sử dụng **bounded retries/backoff** trước khi kết luận thiếu cập nhật; không đợi vô hạn và không thay đổi nhóm trong lúc server plugin đang sửa cùng dữ liệu mà không có cơ chế phối hợp.

### 11.3. Lưu full DN dùng cho tham chiếu

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldFullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("ou", "employees")
        .add("uid", "an")
        .build();

Name newFullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("ou", "alumni")
        .add("uid", "an")
        .build();
~~~

**Name** giúp xử lý cú pháp DN (bao gồm ký tự cần escaping) thay vì ghép chuỗi không kiểm soát. Nếu entry dùng RDN **cn**, ví dụ này không còn đúng; phải dựng từ **DN thật** và naming policy. DN so sánh trong Java nên dùng **LdapName/Rdn** khi phù hợp, nhưng **matching rule thực sự vẫn do server quyết định**.

## 12. Khi server không tự cập nhật: sửa thủ công có điều kiện

Một ứng dụng có thể sở hữu nhóm **groupOfNames** trên một OpenLDAP test không bật refint. Với một nhóm cụ thể, chính sách là:

1. Đọc thuộc tính **member** hiện tại.
2. Nếu oldDN còn và newDN chưa có, yêu cầu **REMOVE oldDN + ADD newDN** trong **một LDAP Modify request** cho group đó.
3. Nếu oldDN không còn và newDN đã có, coi thao tác được xác minh là **đã hoàn thành**, không ghi thêm.
4. Nếu cả hai tồn tại, không tồn tại cả hai hoặc không đọc được member, **không quyết định thay thế một cách mù quáng**.
5. Đọc lại để xác minh trạng thái sau Modify; xử lý race và lỗi mạng.

Ví dụ minh họa ở mức một group (không dùng trực tiếp cho AD linked member):

~~~java
package org.example.directory;

import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberRepairService {
    private final LdapTemplate ldapTemplate;

    public GroupMemberRepairService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public enum Result { ALREADY_UPDATED, REPAIRED, CONFLICT }

    public Result replaceMemberIfStillStale(
            Name groupRelativeDn,
            Name oldFullDn,
            Name newFullDn) {

        // GroupRelativeDn do service tạo từ allowlist OU/groups;
        // không nhận arbitrary DN từ HTTP request.
        DirContextOperations group =
                ldapTemplate.lookupContext(groupRelativeDn);

        String[] values = group.getStringAttributes("member");
        if (values == null || values.length == 0) {
            return Result.CONFLICT; // hoặc attribute bị ACL hạn chế
        }

        String oldValueOnServer =
                findMatchingDn(values, oldFullDn);
        String newValueOnServer =
                findMatchingDn(values, newFullDn);

        if (oldValueOnServer == null && newValueOnServer != null) {
            return Result.ALREADY_UPDATED;
        }
        if (oldValueOnServer == null || newValueOnServer != null) {
            return Result.CONFLICT;
        }

        // LDAP Modify trên 1 entry chứa hai modification;
        // lỗi/noSuchAttribute nếu có ai sửa cùng lúc vẫn có thể xảy ra.
        ModificationItem[] changes = {
            new ModificationItem(
                    DirContext.ADD_ATTRIBUTE,
                    new BasicAttribute("member", newFullDn.toString())),
            new ModificationItem(
                    DirContext.REMOVE_ATTRIBUTE,
                    new BasicAttribute("member", oldValueOnServer))
        };
        ldapTemplate.modifyAttributes(groupRelativeDn, changes);

        // Production: đọc lại group sau thao tác và đối soát;
        // nếu mất response, chuyển OUTCOME_UNKNOWN trước khi retry.
        return Result.REPAIRED;
    }

    private static String findMatchingDn(
            String[] values, Name expected) {
        for (String value : values) {
            try {
                if (new LdapName(value).equals(expected)) {
                    return value;
                }
            } catch (javax.naming.InvalidNameException e) {
                throw new IllegalStateException(
                        "Group có DN member sai cú pháp", e);
            }
        }
        return null;
    }
}
~~~

**Những giới hạn của ví dụ sửa thủ công:**

- **Một LDAP Modify operation trên một group** có xử lý nguyên tử của operation, nhưng việc sửa **nhiều group không trở thành transaction atomic đa-entry**.
- Code chỉ áp dụng cho **groupOfNames.member** với giá trị DN có thể đọc đầy đủ và nhỏ vừa phải; trên AD, một nhóm có lượng member rất lớn có thể cần **ranged retrieval** và quan hệ linked attributes đã được server quản lý — **không dùng lại logic này một cách máy móc**.
- **LdapName.equals** hữu ích để so DN cú pháp Java, nhưng không thay cho matching rule của server và không giải quyết mọi đặc thù server schema.
- Sau preflight, một client khác có thể sửa group trước LDAP Modify; server có thể trả **noSuchAttribute (16)** hoặc **attributeOrValueExists (20)**. Phải phân loại là race/outcome cần đối soát, không catch rồi coi đã sửa xong.
- Nếu server/plugin vẫn tự sửa references, code này có thể **đua ghi với plugin**. Chỉ bật repair trong một vùng/phương thức được xác định có trách nhiệm application-side.
- Return **REPAIRED** trong ví dụ nghĩa là **Modify trả success**, không bảo đảm tất cả replicas/cache đã cập nhật; khi yêu cầu nhất quán chặt, service phải đọc lại và ghi trạng thái xác nhận riêng.

Trong thực tế, một reconciliation job nên lưu từng group đã xử lý, retry giới hạn và bản ghi trạng thái bền vững. **Không dùng Java catch(Exception) rồi xóa cả group.member** như một cách nhanh để vượt lỗi.

## 13. Referential integrity bảo toàn quan hệ, không quyết định quyền truy cập

Một điểm có ý nghĩa bảo mật: **tự cập nhật DN trong group.member có thể giữ nguyên quyền nhóm**. Điều đó đúng về mặt referential integrity nhưng có thể **sai về chính sách tổ chức**.

Ví dụ:

~~~text
Trước:
  An nằm ở ou=employees.
  An là thành viên cn=production-admins.

Yêu cầu nghiệp vụ:
  Chuyển An sang ou=alumni (nghỉ việc).

Server có refint:
  member=oldDn -> member=newDn
  Quan hệ tới nhóm production-admins vẫn còn.
~~~

Trong trường hợp này server đã làm **đúng việc bảo toàn tham chiếu**, nhưng nghiệp vụ có thể yêu cầu **thu hồi quyền**, **vô hiệu hóa tài khoản** và **xóa membership**. Do đó:

- **Move OU** không mặc nhiên đồng nghĩa user bị disable, bị revoke role hoặc không thể bind.
- **Refint tự động** không biết group nào mang ý nghĩa production access, nhóm nào chỉ là mailing list.
- **memberOf** hay nested group membership có thể vẫn có hiệu lực; cần đánh giá quyền thực tế qua cơ chế IAM/AD tương ứng.
- **Không nên tắt refint để làm cách gián tiếp thu hồi quyền.** Dangling references không phải chính sách authorization đáng tin.

Một workflow nghỉ việc nên có các bước nghiệp vụ được phê duyệt: xác minh identity, hạn chế/disable login theo directory hỗ trợ, thu hồi các quyền cần thiết, điều chỉnh nhóm, move entry nếu phù hợp và đối soát session/token ngoài LDAP. Nếu workflow nhiều hệ thống bị lỗi giữa chừng, phải lưu trạng thái và cơ chế recovery; không coi rename đơn lẻ là đã offboard hoàn tất.

### 13.1. Đúng dữ liệu không có nghĩa đúng chính sách

| Quan sát | Đánh giá kỹ thuật | Câu hỏi nghiệp vụ |
| --- | --- | --- |
| Group.member được cập nhật từ DN cũ sang DN mới | Reference không bị đứt | User có còn được phép thuộc nhóm ấy không? |
| Group.member vẫn DN cũ | Reference có thể stale | Cần sửa hay cần gỡ membership hẳn? |
| Không còn member sau rename | Reference có thể đã bị mất | Có làm mất quyền hợp lệ cần giữ không? |
| memberOf thay đổi theo linked attributes | AD đã duy trì backlink | Có primary/nested group quyền chưa được tính không? |
| Login name giữ nguyên sau move | Identity có thể ổn định | Account có cần disable/rotate credentials? |

**Vì vậy yêu cầu chấp nhận phải bao gồm cả hai lớp:** trạng thái liên kết kỹ thuật và chính sách quyền của người dùng.

## 14. Rename/move trong workflow nhiều hệ thống

Một hệ thống thực tế có thể chứa DN trong:

~~~text
LDAP:
  cn=backend.member -> uid=an,ou=employees,dc=example,dc=org

Database:
  account.ldap_dn = uid=an,ou=employees,dc=example,dc=org

Cache:
  userDN:an -> uid=an,ou=employees,dc=example,dc=org

External app:
  policy.subjectDn = uid=an,ou=employees,dc=example,dc=org
~~~

**LDAP server không thể tự sửa database, cache hoặc hệ thống ngoài**. Ứng dụng cần cơ chế điều phối:

~~~mermaid
flowchart TD
    A["Yêu cầu rename/move đã được phê duyệt"] --> B["Ghi journal: operationId, oldDn, newDn"]
    B --> C["Preflight: entry + group refs + ACL"]
    C --> D["LDAP Modify DN"]
    D --> E{"Biết rõ kết quả?"}
    E -->|Success| F["Kiểm tra LDAP entry và refs"]
    E -->|Mất response| G["OUTCOME_UNKNOWN: đọc actual LDAP state"]
    G --> F
    F --> H{"Có thiếu/sai references?"}
    H -->|Không| I["Sửa DB/cache/external links theo owner"]
    H -->|Có| J["Đối soát hoặc repair có điều kiện"]
    J --> I
    I --> K["Xác minh policy và đánh dấu COMPLETED"]
~~~

### 14.1. Journal trạng thái cần lưu gì?

Ví dụ một bản ghi theo workflow do ứng dụng quản lý:

~~~json
{
  "operationId": "e0e90da6-25a1-4f77-83af-fac0964425c4",
  "kind": "MOVE_DIRECTORY_USER",
  "directoryAlias": "people-primary",
  "oldDnRef": "encrypted-ref:old",
  "newDnRef": "encrypted-ref:new",
  "expectedGroupRefs": ["group-ref-01", "group-ref-02"],
  "status": "LDAP_RENAME_APPLIED",
  "referenceRepair": "RECONCILE_PENDING",
  "externalSync": "PENDING",
  "updatedAt": "2026-11-26T00:00:00Z"
}
~~~

Đây chỉ là format minh họa; **Spring LDAP không tự tạo durable journal**. Các **oldDnRef/newDnRef** đại diện dữ liệu được bảo vệ, tránh ghi DN/PII thẳng vào log công khai. Ứng dụng cần thêm idempotency key, optimistic version/CAS, retry budget, lease của worker và thời hạn lưu khi triển khai thật.

### 14.2. Những trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Việc cần làm |
| --- | --- | --- |
| **PREPARED** | Đã lưu kế hoạch và preflight | Gửi Modify DN |
| **LDAP_RENAME_APPLYING** | Đã gửi hoặc chuẩn bị gửi request | Chờ response/kiểm tra actual state |
| **LDAP_RENAME_APPLIED** | Xác minh entry đã đến DN mới | Kiểm tra references |
| **OUTCOME_UNKNOWN** | Không biết rename có được server áp dụng chưa | Đọc old/new DN và ID server-managed |
| **REFERENCES_RECONCILING** | Đang kiểm tra/điều chỉnh nơi tham chiếu | Retry bounded, xử lý ACL/concurrency |
| **EXTERNAL_SYNC_PENDING** | LDAP ổn nhưng DB/cache/ứng dụng khác chưa đồng bộ | Outbox/event và reconciliation |
| **COMPLETED** | Đã kiểm chứng mọi invariant của nghiệp vụ | Kết thúc và audit |
| **NEEDS_RECONCILIATION** | State mâu thuẫn, sửa tự động không an toàn | Điều tra, can thiệp được phê duyệt |

Không biến **LDAP_RENAME_APPLIED** thành **COMPLETED** nếu hợp đồng yêu cầu group membership, authorization và database key cũng đã đúng. Đây là nguyên tắc chung cho **Spring LDAP compensating transactions**: client có thể cố bù trừ nhưng **không có transaction ACID nguyên tử giữa LDAP, SQL và cache**.

### 14.3. Khi LDAP rename trả lỗi mạng

~~~mermaid
sequenceDiagram
    participant App as Spring service
    participant LDAP as LDAP server
    App->>LDAP: Modify DN oldDn -> newDn
    LDAP->>LDAP: Đổi tên entry thành công
    LDAP--xApp: Mất kết nối trước response
    Note over App: CommunicationException, outcome chưa rõ
    App->>LDAP: Lookup oldDn và newDn khi kết nối phục hồi
    LDAP-->>App: Actual directory state
~~~

Nếu oldDn không còn và newDn tồn tại, **chưa đủ** để kết luận đó là đúng entry do request này chuyển. Nên đối chiếu **server-managed object identity**, thông tin journal và concurrency theo chính sách. Nếu cả hai DN tồn tại, hoặc cả hai đều không tồn tại, không thực hiện rename lại/xóa tự động.

Đừng retry **LdapTemplate.rename(oldDn,newDn)** vô điều kiện sau **CommunicationException**: lần đầu có thể đã thành công, và lần lặp có thể trả **noSuchObject (32)** hoặc xung đột, khiến ứng dụng hiểu sai trạng thái.

### 14.4. Idempotency và đồng bộ tham chiếu ngoài LDAP

Một workflow tốt cần phân biệt:

- **Cùng operationId được gọi lại**: không gửi lại Modify DN nếu đã xác nhận hoặc đang đối soát.
- **Cùng user nhưng hai yêu cầu move khác nhau**: có thể cạnh tranh, phải dùng version/lease hoặc cơ chế ownership.
- **LDAP server tự sửa group**: app chỉ xác minh, không chạy repair trùng.
- **Ứng dụng chịu trách nhiệm custom attribute**: cập nhật có điều kiện, ghi checkpoint từng entry.
- **DB/cache**: dùng outbox/event có idempotency key, invalidate cache bằng định danh ổn định hơn DN nếu có thể.
- **Có replication lag**: đừng trả negative verdict khi mới đọc từ replica chưa đồng bộ.

Với **entryUUID** của OpenLDAP hoặc **objectGUID** của AD, có thể dùng làm bằng chứng danh tính mạnh hơn chuỗi DN qua rename nội bộ, nhưng phải xác minh khả năng đọc và tính ổn định theo môi trường; không coi ID giữ nguyên trong mọi migration giữa directory/forest.

## 15. Bảo mật của chức năng đổi tên và tự cập nhật tham chiếu

Đổi tên/move LDAP entry thường nhạy cảm vì có thể thay đổi **vùng ACL, phạm vi search, policy áp dụng và group/authorization side effects**.

Các nguyên tắc:

1. **Xác thực và phân quyền HTTP** tách biệt với ACL của service account LDAP. Không cho một caller thường tự di chuyển người dùng đến **ou=admins**.
2. **Allowlist parent DN**, naming context và loại entry có thể move; không nhận raw DN từ request rồi đưa thẳng vào **ldapTemplate.rename**.
3. Tạo DN bằng **LdapNameBuilder/Rdn**; tạo filter bằng **LdapQueryBuilder**. DN escaping khác filter escaping.
4. Dùng **LDAPS/StartTLS** với CA và hostname verification, không tắt trust validation để vượt lỗi Modify DN.
5. Chỉ cấp quyền **rename, đọc group, sửa reference** cho các account thực sự cần; phân quyền sửa membership thường phải chặt hơn đọc LDAP.
6. Không log bind password, token, toàn bộ LDAP attributes, raw DN chứa PII hoặc diagnosticMessage chưa xử lý.
7. Không cho API sửa **member** hoặc **memberOf** tùy tiện để “khôi phục” nếu không có chính sách IAM xác định đúng quyền.
8. Hạn chế **rate/concurrency** của operation có thể kích hoạt refint search trên nhiều nhóm; log metric nhưng tránh rò rỉ danh sách users/groups.
9. Kiểm tra hậu điều kiện **không cấp quyền ngoài ý muốn**, nhất là khi chuyển user vào/ra OU chịu chính sách đặc biệt.
10. Các tác vụ repair hoặc xóa dangling reference phải có audit, dry-run và quyền operator phù hợp.

**Một refint overlay/plugin có thể chạy bằng quyền cao ở server** để sửa các attribute mà client không tự sửa được. Vì vậy nó cũng cần kiểm soát cấu hình và theo dõi thay đổi: không cho người dùng ít quyền tự đăng ký attribute tùy ý vào danh sách refint.

## 16. Kiểm thử tích hợp: rename thành công chưa đủ để khẳng định refint

Cần có hai nhóm kiểm thử:

- **Kiểm thử LDAP Modify DN**: entry thực sự có DN mới, DN cũ không còn, thuộc tính RDN và children xử lý đúng schema.
- **Kiểm thử referential integrity**: từng reference attribute được cập nhật/xóa theo **cấu hình server cụ thể**, đúng cả khi chuyển người dùng, đổi tên OU cha, xóa entry hoặc gặp replication delay.

Không chỉ mock **LdapTemplate.rename** rồi tuyên bố plugin server hoạt động: plugin/linked attributes chạy trong LDAP server, không chạy trong Java mock.

### 16.1. Chuẩn bị LDIF fixture

Ví dụ sau dành cho directory test, không áp thẳng vào production:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: employees

dn: ou=alumni,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: alumni

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=an,ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran

dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

**Lưu ý:** Import chỉ những entry chưa tồn tại. Một LDAP server AD DS không nhận nguyên mẫu schema/LDIF OpenLDAP này theo cùng cách; với AD, chuẩn bị fixture bằng phương thức tạo user/group được AD hỗ trợ. Nhóm **groupOfNames** phải có ít nhất một member, vì vậy fixture tạo member trước khi thử rename.

### 16.2. Xác minh bằng ldapsearch

Tại một OpenLDAP/389 test có LDAPS hợp lệ, dùng tài khoản read-only:

~~~bash
# Trước move: tìm nhóm đang giữ full DN cũ.
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(member=uid=an,ou=employees,ou=people,dc=example,dc=org)" \
  dn cn member
~~~

Sau khi chạy service move user, kiểm tra cả filter cũ và mới:

~~~bash
# Nhóm nào còn trỏ tới DN cũ?
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(member=uid=an,ou=employees,ou=people,dc=example,dc=org)" \
  dn member

# Nhóm nào đã trỏ tới DN mới?
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(member=uid=an,ou=alumni,ou=people,dc=example,dc=org)" \
  dn member
~~~

Giá trị DN trong các filter trên là **fixture cố định**. Trong ứng dụng thật, không nối raw input vào LDAP filter; dùng LdapQueryBuilder/Filter API. Không ghi password vào command; **-W** yêu cầu nhập tương tác. Kiểm tra certificate chain/hostname của server.

### 16.3. Integration test Java kiểm tra entry mới

~~~java
package org.example.directory;

import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DirectoryMoveIntegrationTest {
    @Autowired DirectoryMoveService moveService;
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void moveChangesEntryDn() {
        // Precondition: uid=test-move được seed dưới ou=employees;
        // uid=test-move chưa tồn tại dưới ou=alumni.
        String uid = "test-move";

        Name oldDn = LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid).build();
        Name newDn = LdapNameBuilder
                .newInstance("ou=alumni,ou=people")
                .add("uid", uid).build();

        moveService.moveKnownUidFromEmployeesToAlumni(uid);

        String newUid = ldapTemplate.lookup(
                newDn,
                new String[]{"uid"},
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());

        assertEquals(uid, newUid);
        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldapTemplate.lookup(
                        oldDn,
                        (AttributesMapper<String>) attrs ->
                                (String) attrs.get("uid").get()));
    }
}
~~~

**Test này chỉ xác minh DN của entry**, không xác minh các group references. Fixture cần seed một user test có cn/sn hợp lệ và quyền rename, dọn dữ liệu sau test bằng workflow an toàn. Trên môi trường có LDAP alias/referral, cách diễn giải DN cũ có thể khác; phải dùng đúng naming/context policy.

### 16.4. Integration test referential integrity có cấu hình mong đợi

Để kiểm chứng plugin, cần một fixture riêng **uid=test-refint** và group chỉ dành cho test. Pseudocode JUnit:

~~~java
// Giả định preflight đã xác nhận:
//   oldFullDn = uid=test-refint,ou=employees,ou=people,dc=example,dc=org
//   newFullDn = uid=test-refint,ou=alumni,ou=people,dc=example,dc=org
//   expectedGroups = [cn=refint-test,ou=groups] (Name tương đối)
//
// 1. assert old references tồn tại trước rename
// 2. moveService.moveKnownUidFromEmployeesToAlumni("test-refint")
// 3. Đọc entry mới và chờ bounded nếu plugin async/replication chậm
// 4. oldRefs = finder.findGroupDnsReferencing(oldFullDn)
// 5. newRefs = finder.findGroupDnsReferencing(newFullDn)
//
// Khi test profile được khai báo refintEnabled = true:
//     assert oldRefs không chứa expectedGroups
//     assert newRefs chứa expectedGroups
//
// Khi test profile khai báo refintEnabled = false:
//     kiểm chứng reference có thể còn oldDn;
//     không dùng kết quả đó để kết luận server khác.
//
// 6. Nếu yêu cầu offboarding, kiểm tra quyền nhóm thật đã bị
//    thu hồi theo policy, không chỉ kiểm tra DN trong member.
// 7. Cleanup group + user thuộc đúng OU test theo runbook.
~~~

Không dùng vòng sleep vô hạn trong test. Với asynchronous plugin hoặc replication, dùng **deadline hữu hạn**, kiểm tra trạng thái khi timeout và ghi lại server endpoint mà test đọc. Mỗi test phải biết **kỳ vọng theo cấu hình backend**, không gọi “refint đã lỗi” chỉ vì server test cố ý tắt plugin.

### 16.5. Ma trận test quan trọng

| Kịch bản | Thiết lập | Điều phải xác minh |
| --- | --- | --- |
| Rename RDN trong cùng OU | uid hoặc cn đổi RDN | Entry có DN mới, thuộc tính RDN xử lý đúng server policy |
| Move giữa OU cùng suffix | employees → alumni | Entry ở newDn, không còn oldDn |
| **member** khi refint bật | Group trỏ tới oldDn | Group tham chiếu newDn theo cấu hình |
| **member** khi refint tắt | Group trỏ tới oldDn | Reference stale được phát hiện, workflow repair đúng trách nhiệm |
| **uniqueMember** | GroupOfUniqueNames | Kết quả theo khả năng/plugin/cú pháp đích, không suy từ member |
| **manager** hoặc **seeAlso** | Thuộc tính DN-valued | Chỉ được sửa khi server quản lý attribute ấy |
| **memberUid** | posixGroup lưu username | Move OU không làm thay đổi memberUid theo refint DN |
| GroupOfNames member cuối | Thử delete user trong nhóm một member | Kiểm tra policy/schema/placeholder hoặc lỗi |
| Rename OU có child | Một OU chứa nhiều user | Test references tới OU cha **và** descendants |
| AD **member/memberOf** | Linked group relationship | Auto update, primary group ngoại lệ |
| Group dynamic | memberURL và filter | Re-evaluate membership, không mặc định rewrite URL |
| Custom text DN | description/legacyMemberText | Không kỳ vọng server tự sửa |
| Cross-directory | Một reference tới LDAP khác | Không có tính toàn vẹn liên server tự động |
| Replication lag | Hai servers/replicas | Đo độ trễ, không kết luận sai từ stale read |
| Rename bị từ chối ACL | Account read-only | LDAP operation thất bại; group/reference không được coi là đã đồng bộ |
| Move vào OU có policy khác | employees → alumni | Kiểm tra authentication/group access đúng policy |
| Kết nối mất sau rename | Fault injection test | OUTCOME_UNKNOWN và recovery đọc actual state |
| External DB/cache | Có cache oldDn | Làm mới qua event/outbox, không dựa refint của LDAP |
| Concurrent group modify | Client khác sửa member cùng lúc | Repair không làm mất membership mới |

**Đừng chạy thử delete hoặc rename subtree lớn trên production**. Thử trong OU test, dữ liệu giả hoặc directory được sao chép có kiểm soát, với người vận hành phê duyệt.

## 17. Lỗi thường gặp và cách điều tra

| Hiện tượng | Giải thích có thể | Hướng xử lý |
| --- | --- | --- |
| LDAP rename success nhưng member vẫn oldDn | Refint chưa bật, không quản lý member hoặc đang delay | Kiểm tra plugin/overlay, phạm vi và replication; đối soát |
| member ở group A đã sửa, group B chưa sửa | Scope plugin, ACL, index, replication hoặc group ngoài vùng | Ghi danh sách expectedGroups và kiểm tra từng group |
| Trong AD, group.member đúng nhưng ứng dụng vẫn thấy DN cũ | Cache, replica/GC stale hoặc snapshot của app | Đọc endpoint phù hợp, invalidate cache |
| group.memberOf không có group mong đợi | AD primaryGroupID, nested semantics, ACL hoặc membership khác | Kiểm tra group/member và policy AD, không coi backlink là toàn bộ quyền |
| **noSuchObject (32)** | OldDn bị move rồi, hoặc base/parent sai | Kiểm tra old/new DN và identity trước khi retry |
| **entryAlreadyExists (68)** | New DN đã bị chiếm | Không overwrite, giải quyết xung đột tên |
| **invalidDNSyntax (34)** | DN được ghép chuỗi/escape sai | Dùng LdapNameBuilder/Rdn |
| **insufficientAccessRights (50)** | Bind identity thiếu quyền rename/move hoặc modify group | Kiểm tra ACL theo thao tác; không dùng admin quyền rộng theo mặc định |
| **objectClassViolation (65)** | RDN hoặc attributes vi phạm schema, refint xóa member cuối | Kiểm tra MUST/MAY, refint_nothing/placeholder policy |
| **notAllowedOnNonLeaf (66)** | Server từ chối thao tác trên entry có con theo policy | Kiểm tra loại operation và ràng buộc server |
| **affectsMultipleDSAs (71)** | Rename/move vượt vùng quản lý DSA | Không dùng rename đơn giản; thiết kế migration riêng |
| **unwillingToPerform (53)** | Server policy từ chối rename/modify hoặc AD có quy tắc riêng | Xem diagnostic nội bộ và chính sách vendor |
| **busy (51) / unavailable (52)** | Directory quá tải/không sẵn sàng | Backoff, rate-limit, giữ trạng thái workflow |
| Modify member trả 16/20 | Server đã tự sửa hoặc client khác sửa trong lúc preflight | Đọc lại actual state, không retry sửa mù |
| Tài khoản vẫn có quyền sau offboarding | Refint giữ nguyên group membership | Thực hiện thu hồi quyền theo policy, không dựa move OU |

### 17.1. Quy trình chẩn đoán theo thứ tự

1. **Entry đã đổi DN chưa?** Lookup DN cũ/mới bằng một tài khoản đủ quyền và đúng ContextSource.
2. **Đang kiểm tra reference nào?** Xác định member/uniqueMember/manager/custom và syntax thực tế.
3. **Server sở hữu reference ấy không?** Kiểm tra refint overlay/plugin/AD linked attributes.
4. **Vùng tìm reference đúng chưa?** Base DN, OU, ACL, naming contexts, directoryAlias.
5. **Đã xét độ trễ chưa?** Plugin async, replication hoặc cache của client.
6. **Có thay đổi đồng thời không?** Audit log/operationId, group cập nhật bởi client khác.
7. **Nghiệp vụ cần giữ hay thu hồi quan hệ?** Đừng mặc định refint đúng về IAM.
8. **Nếu thiếu update, ai sửa?** Server config hay app repair; không để hai cơ chế sửa cùng dữ liệu vô điều kiện.

## 18. Tổng kết và bài tập tự luyện

**Cơ chế tự cập nhật tham chiếu theo máy chủ có giới hạn rõ ràng.** **LDAP Modify DN** đổi tên/vị trí entry, nhưng không yêu cầu mọi attribute chứa DN hoặc mọi hệ thống bên ngoài phải tự cập nhật. **OpenLDAP** cần **slapo-refint** và danh sách DN attributes phù hợp; **Red Hat/389 Directory Server** dùng plugin với scope/delay/replication riêng; **AD DS** có linked attributes như **member** được duy trì theo object link. **Không thể dùng hành vi của một directory làm cam kết cho mọi directory khác.**

Trong ứng dụng **Spring Data LDAP**, hãy dùng **LdapTemplate.rename** cho thao tác rõ nghĩa, lấy DN thực tế thay vì đoán từ username khi naming convention không đảm bảo, kiểm tra reference trước/sau, phân biệt dữ liệu server có thể sửa với dữ liệu ứng dụng phải sửa và dùng reconciliation có điều kiện. Đặc biệt, **bảo toàn tham chiếu không thay thế quy tắc cấp/thu hồi quyền**: move user sang alumni có thể vẫn để user thuộc nhóm đặc quyền nếu không có bước nghiệp vụ bổ sung.

**Bài tập:**

1. Trong ví dụ An chuyển employees → alumni, hãy chỉ ra **old DN**, **new DN** và giá trị **member** mong đợi nếu server bật refint cho member.
2. Vì sao rename thành công không chứng minh bảng SQL lưu **ldap_dn** hoặc cache Redis đã được cập nhật?
3. So sánh **slapo-refint** của OpenLDAP, Referential Integrity plugin của 389 DS và **linked attribute member** của AD DS.
4. Vì sao một giá trị **legacyMemberText** trông giống DN có thể không được refint cập nhật? Khác biệt của **memberUid** là gì?
5. Nếu OpenLDAP groupOfNames chỉ có một member và user bị xóa, cần xét schema/placeholder policy nào? Rủi ro bảo mật của placeholder?
6. Đề xuất một bộ integration test kiểm tra **rename user**, **rename OU cha**, **member**, **manager**, **uniqueMember** và **custom string**.
7. Viết cách tìm các group trỏ tới oldFullDn bằng LdapTemplate/LdapQueryBuilder mà không ghép filter raw.
8. Nếu group đã có newDn và không còn oldDn sau move, tại sao app không nên gửi lệnh REMOVE oldDn + ADD newDn?
9. Trong AD, vì sao **memberOf** đơn thuần có thể không phản ánh primary group hoặc toàn bộ quyền của user?
10. Một user chuyển vào **ou=alumni** nhưng vẫn ở **cn=production-admins**. Bạn sẽ thiết kế workflow offboarding thế nào cho đúng bảo mật?
11. Khi LDAP Modify DN bị mất response, làm sao phân biệt request chưa thực hiện và đã thực hiện trước khi retry?
12. Nếu plugin cập nhật references sau operation với delay, ứng dụng nên trả trạng thái và áp dụng polling/timeout như thế nào?

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Modify DN, Modify, result codes và giới hạn thao tác LDAP.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — DN, objectClass, attribute syntaxes, naming contexts.
- [RFC 4514 — String Representation of DNs](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — cú pháp escaping DN/filter.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) — rename(Name, Name), lookup, search, modifyAttributes.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ODM @Entry/@Id/@Attribute và repository.
- [OpenLDAP 2.6 Administrator's Guide — Referential Integrity](https://cvs.openldap.org/doc/admin26/guide.html) — refint overlay, lựa chọn DN attributes, placeholder và giới hạn cấu hình.
- [OpenLDAP slapo-refint(5)](https://man7.org/linux/man-pages/man5/slapo-refint.5.html) — tham số refint, hạn chế cú pháp DN/replication.
- [Red Hat Directory Server 13 — Referential Integrity plugin](https://docs.redhat.com/en/documentation/red_hat_directory_server/13/html/security_and_access_control/user-management-and-authentication) — cấu hình plugin và bảo trì group/member references.
- [Red Hat Directory Server 12 — Using Referential Integrity](https://docs.redhat.com/en/documentation/red_hat_directory_server/12/html/user_management_and_authentication/assembly_using-referential-integrity-to-maintain-relationships-between-entries) — chính sách delay và hoạt động sau rename/delete.
- [Microsoft Learn — Active Directory Group Objects](https://learn.microsoft.com/en-us/windows/win32/ad/group-objects) — thuộc tính member và tự cập nhật DN của linked member khi move/rename.
- [Microsoft Learn — Active Directory Domain Services](https://learn.microsoft.com/en-us/windows/win32/ad/active-directory-domain-services) — đặc điểm AD DS, schema và các quy tắc khác LDAP thông thường.
