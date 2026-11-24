# Directory replication – nhân bản dữ liệu thư mục trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **directory replication** là gì, vì sao cần nhân bản danh tính giữa các máy chủ thư mục và phân biệt nó với **LDAP query**, **đồng bộ HRIS–IdP**, **SCIM provisioning** và sao lưu.
- Mô tả cách **Active Directory Domain Services (AD DS)** nhân bản dữ liệu giữa các domain controller; phân biệt **domain, site, naming context/partition, Global Catalog (GC)** và **Read-Only Domain Controller (RODC)**.
- Hiểu các khái niệm **multi-master**, **eventual consistency**, **replication topology**, **update sequence number (USN)**, **invocation ID**, **high-watermark**, **up-to-dateness vector**, metadata thay đổi, đối tượng bị xóa và xung đột.
- Nhận biết mô hình nhân bản của một số hệ thư mục LDAP khác, chẳng hạn **OpenLDAP syncrepl**, mà không đồng nhất giao thức LDAP với một thuật toán replication duy nhất.
- Phân tích tác động của replication delay đến **Joiner–Mover–Leaver (JML)**, **IdP/SSO**, xác thực, **RBAC/ABAC**, đồng bộ **SCIM**, tài khoản dịch vụ và thu hồi quyền truy cập.
- Đề xuất kiến trúc, kiểm soát bảo mật, giám sát, khắc phục sự cố và bằng chứng kiểm toán cho hệ thống thư mục phân tán.

## 1. Directory replication là gì?

**Directory replication (nhân bản dữ liệu thư mục)** là quá trình **truyền và áp dụng những thay đổi của dữ liệu thư mục giữa các bản sao** để các máy chủ phục vụ truy vấn/xác thực có thể tiến tới trạng thái nhất quán theo cơ chế của hệ thư mục.

Dữ liệu thường được quản lý trong directory service gồm:

- Đối tượng người dùng, nhóm và máy tính.
- Thuộc tính định danh: mã đối tượng, tên, đơn vị, bộ phận, trạng thái tài khoản.
- Tư cách thành viên nhóm và một số dữ liệu liên quan tới phân quyền.
- Đối tượng chính sách, cấu hình hoặc tài nguyên phụ thuộc nền tảng.
- Danh tính phi con người: service principal, service account, tài khoản máy tính, một số nhóm hoặc credential metadata.

**Ví dụ:** tổ chức có hai domain controller (DC) đặt tại Hà Nội và Thành phố Hồ Chí Minh. IAM vô hiệu hóa tài khoản người đã nghỉ trên một DC. Nếu DC còn lại chưa nhận thay đổi, một ứng dụng vẫn truy vấn bản sao cũ có thể tiếp tục thấy tài khoản ở trạng thái trước khi vô hiệu hóa.

Replication giúp các DC **hội tụ dữ liệu**, nhưng không có nghĩa mọi DC lập tức có cùng trạng thái tại mọi thời điểm. Cửa sổ chưa hội tụ là rủi ro đặc biệt quan trọng đối với **thu hồi quyền sau Mover hoặc Leaver**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, replication là lớp hạ tầng hỗ trợ danh tính số được dùng xuyên suốt **Joiner–Mover–Leaver**. Nó không thay thế identity proofing, quản trị nguồn nhân sự, authorization hay đối soát quyền thực tế ở các ứng dụng.

### 1.1. Vì sao cần nhiều bản sao?

| Nhu cầu | Giá trị của replication | Giới hạn cần kiểm soát |
| --- | --- | --- |
| **Sẵn sàng** | Một DC ngừng hoạt động, DC khác vẫn phục vụ trong phạm vi khả năng hệ thống | Bản sao còn hoạt động có thể chưa có cập nhật mới nhất |
| **Hiệu năng** | Người dùng truy vấn/xác thực qua DC gần hơn | Việc chọn DC ảnh hưởng thời điểm thấy thay đổi |
| **Phân tán địa lý** | Nhiều site dùng chung dữ liệu danh tính cần thiết | WAN, lịch replication và topology tạo độ trễ |
| **Quản lý tập trung** | Thay đổi từ nơi được phép có thể lan sang các bản sao | Không được giả định mọi thành phần IAM đều cùng dùng một nguồn |
| **Khả năng phục hồi** | Dữ liệu được lưu ở nhiều nơi và có thể tiếp tục phục vụ khi một nút lỗi | Replication không phải backup hoặc cách khôi phục mọi sai sót |

**Một thay đổi sai cũng có thể được nhân bản rất nhanh.** Nếu quản trị viên vô tình thêm người dùng vào nhóm đặc quyền, replication sẽ lan truyền trạng thái sai; nó không tự kiểm chứng sự thay đổi có được phê duyệt hay không.

## 2. Replication khác query, synchronization, provisioning và backup

| Hoạt động | Mục đích chính | Ví dụ |
| --- | --- | --- |
| **Directory query** | Đọc dữ liệu đã có ở một máy chủ thư mục | Ứng dụng gọi LDAP search tìm user và group |
| **Directory replication** | Truyền thay đổi giữa các bản sao trong cùng cơ chế thư mục | AD DS nhân bản đối tượng từ DC A sang DC B |
| **Directory synchronization** | Chuyển đổi/đồng bộ dữ liệu giữa các hệ thống hoặc miền khác nhau | HRIS cập nhật thuộc tính vào AD hoặc AD đồng bộ với cloud IdP |
| **Account provisioning** | Tạo, sửa, cấp quyền hoặc vô hiệu hóa account ở hệ thống đích | IAM dùng SCIM để disable user SaaS |
| **Federation/SSO** | Sử dụng kết quả xác thực của IdP cho ứng dụng | OIDC/SAML SSO vào cổng báo cáo |
| **Backup/restore** | Có điểm khôi phục dữ liệu khi lỗi, xóa nhầm hoặc sự cố lớn | System State backup hoặc bản sao lưu theo sản phẩm |
| **Reconciliation** | So sánh quyền/tài khoản mong muốn với trạng thái thực tế | Đọc lại AD và SaaS để phát hiện quyền còn tồn dư |

**LDAP không tự định nghĩa một cơ chế replication duy nhất.** LDAP là giao thức truy cập và thay đổi thư mục; AD DS, OpenLDAP và các sản phẩm khác có mô hình sao chép, topology, metadata và conflict resolution khác nhau.

**SCIM không phải giao thức replication giữa các AD domain controller.** SCIM phục vụ quản lý tài khoản/nhóm qua ranh giới hệ thống. Việc SCIM trả thành công cũng không chứng minh mọi DC hay mọi ứng dụng đã hội tụ dữ liệu.

### 2.1. Ví dụ hai đường truyền thay đổi

~~~text
Nguồn HRIS phát Leaver
   |
   v
IAM / IGA / provisioning
   |
   +--> AD DS trên DC-A
   |       |
   |       +--(AD replication)--> DC-B
   |       +--(AD replication)--> DC-C
   |
   +--(SCIM/API)--> SaaS X
   +--(SCIM/API)--> SaaS Y
   +--(Cloud IAM API)--> Cloud permissions
~~~

Hai nhóm mũi tên phục vụ mục đích khác nhau. Việc DC-B đã nhận thay đổi từ DC-A **không bảo đảm** SaaS X nhận được lệnh deprovision. Ngược lại, SaaS X đã vô hiệu hóa user cũng không chứng minh mọi DC đã cập nhật.

## 3. Những dữ liệu nào nằm trong thư mục?

Một hệ directory thường tổ chức dữ liệu theo **đối tượng (object)** và **thuộc tính (attribute)**. Ví dụ:

| Đối tượng | Thuộc tính hoặc liên kết | Vì sao ảnh hưởng IAM |
| --- | --- | --- |
| **User** | ID bền vững, tên, UPN, account status, thông tin tổ chức | Xác thực và ánh xạ danh tính |
| **Group** | ID nhóm, loại nhóm, membership | Nhiều chính sách RBAC dựa vào tư cách thành viên |
| **Computer / device** | Định danh máy, trust liên quan | Xác thực thiết bị và điều kiện truy cập |
| **Service account** | Account phục vụ tác vụ hoặc dịch vụ | Phải có owner, quyền và credential lifecycle |
| **Organizational Unit (OU)** | Cấu trúc tổ chức và policy delegation | Ảnh hưởng quản trị và một số chính sách |
| **Directory configuration** | Metadata schema, topology, policy tùy nền tảng | Quyết định hệ thống hoạt động ra sao |
| **Deletion metadata** | Trạng thái đã xóa và marker hỗ trợ nhân bản | Giúp DC khác biết đối tượng cần bị loại bỏ |

**Distinguished Name (DN)** giúp định vị đối tượng trong cây LDAP, nhưng có thể thay đổi khi đối tượng được đổi tên hoặc chuyển OU. Trong AD, nên phân biệt DN với **objectGUID**, **objectSID** và các mã định danh nghiệp vụ. Không dùng mỗi DN hoặc email làm khóa duy nhất cho account linking qua vòng đời JML.

### 3.1. Ví dụ biểu diễn user theo LDAP

~~~ldif
dn: cn=an.nguyen,ou=Employees,dc=example,dc=org
objectClass: inetOrgPerson
cn: an.nguyen
sn: Nguyen
givenName: An
mail: an.nguyen@example.org
employeeNumber: 1042
~~~

Đoạn LDIF chỉ **minh họa dạng dữ liệu LDAP**. Không phải bản ghi AD DS có thể import nguyên xi; schema của AD có object classes, thuộc tính và quy tắc khác. Mã employeeNumber có thể thay đổi hoặc chịu ràng buộc nghiệp vụ; không nên tự xem nó luôn là ID bền vững toàn doanh nghiệp.

## 4. Nhân bản trong Active Directory Domain Services

**AD DS** là một ví dụ phổ biến của directory service hỗ trợ replication giữa các **domain controller**. Trong một domain thông thường, các DC có thể nhận thay đổi vào những bản sao có thể ghi và sao chép sang đối tác theo topology được hệ thống quản lý.

### 4.1. Những phạm vi dữ liệu chính

| Phạm vi | Mô tả | Ghi chú về replication |
| --- | --- | --- |
| **Domain naming context** | Người dùng, nhóm và đối tượng trong một domain | Được nhân bản giữa các DC lưu partition của domain đó |
| **Configuration partition** | Cấu hình dùng ở mức forest | Được nhân bản trong phạm vi DC của forest |
| **Schema partition** | Định nghĩa object classes và attributes | Được nhân bản trong phạm vi forest |
| **Application partition** | Dữ liệu ứng dụng sử dụng partition riêng | Chỉ tới các DC được chỉ định lưu partition |
| **Global Catalog (GC)** | Bản sao đầy đủ domain local và bản sao một phần các domain khác trong forest | Không đồng nghĩa giữ mọi thuộc tính của mọi domain |

**Không phải mọi DC trong forest lưu bản sao ghi được của tất cả domain.** Một DC thông thường lưu domain partition của domain nó thuộc về và những partition khác theo vai trò được cấu hình. GC chứa **partial attribute set** của các domain khác, nên không thể mặc định đọc mọi thuộc tính nhạy cảm từ GC.

### 4.2. RODC – domain controller chỉ đọc

**Read-Only Domain Controller (RODC)** giữ một bản sao chỉ đọc theo mô hình AD DS và có quy tắc riêng về dữ liệu/credential được lưu đệm. RODC phù hợp một số chi nhánh có mức độ tin cậy vật lý thấp hơn.

Cần phân biệt:

- RODC **nhận** dữ liệu nhân bản theo mô hình hệ thống; không tiếp nhận các thay đổi ghi như writable DC.
- **Password Replication Policy** và các cơ chế bảo vệ thuộc tính/secret ảnh hưởng dữ liệu nhạy cảm nào có thể được lưu đệm tại RODC.
- Ứng dụng cần ghi dữ liệu phải được dẫn đến DC có khả năng ghi phù hợp.
- Một RODC mất kết nối có thể tiếp tục phục vụ một số thao tác dựa trên dữ liệu đã có, nhưng không được xem là nguồn dữ liệu JML mới nhất.

RODC **không phải** cách thay thế cho offboarding ở ứng dụng. Quyền còn ở phiên SaaS hoặc cloud API vẫn phải xử lý riêng.

## 5. Topology: nhân bản giữa DC và các site

**Replication topology** là tập quan hệ kết nối giúp các bản sao nhận thay đổi. Trong AD DS, cấu hình **site, subnet, site link** và cơ chế tự tạo kết nối hỗ trợ việc lựa chọn các đường replication.

~~~mermaid
flowchart LR
  subgraph HA["Site Hà Nội"]
    A["DC-HN-01"]
    B["DC-HN-02"]
    A <-->|"Trong site"| B
  end
  subgraph HCM["Site TP.HCM"]
    C["DC-HCM-01"]
    D["DC-HCM-02"]
    C <-->|"Trong site"| D
  end
  B <-->|"Site link / WAN"| C
  IAM["IAM / HRIS workflow"] -->|"Cập nhật user"| A
  APP["Ứng dụng ở TP.HCM"] -->|"LDAP / auth query"| D
~~~

Sơ đồ biểu diễn cấu trúc logic minh họa. Topology thực có thể phức tạp hơn, do AD tự tính toán và thay đổi theo kết nối, site hoặc trạng thái DC.

### 5.1. Intra-site và inter-site

- **Intra-site replication:** thường được tối ưu để thay đổi lan nhanh trong cùng site có kết nối tốt.
- **Inter-site replication:** có thể được quản lý theo site link, lịch, chi phí đường truyền và cơ chế topology phù hợp.
- **Knowledge Consistency Checker (KCC):** thành phần của AD DS hỗ trợ tạo/quản lý topology kết nối replication.
- **Bridgehead/connection objects:** tham gia vận chuyển thay đổi giữa đối tác/site trong cấu trúc AD.

**Site không phải domain.** Một domain có thể trải nhiều site, và một site có thể chứa DC của nhiều domain. Không thiết kế quyền IAM dựa trên giả định “người cùng domain luôn đọc cùng một DC”.

### 5.2. Hệ quả của độ trễ WAN

Nếu người dùng bị vô hiệu hóa lúc 18:00 tại DC-A nhưng một site kết nối WAN chập chờn, DC-B có thể vẫn giữ dữ liệu cũ cho tới khi nhân bản thành công. Điều này ảnh hưởng các thành phần phụ thuộc vào **bản sao nào được truy vấn** và **cơ chế xác thực nào được dùng**.

Không được lấy thời gian gửi lệnh ở DC-A làm bằng chứng rằng tất cả site đã cập nhật. Với các thao tác rủi ro cao, cần có chiến lược **phủ quyết truy cập ở lớp ứng dụng/API**, thu hồi phiên và theo dõi hội tụ.

## 6. Multi-master, single-writer và hướng replication

### 6.1. Multi-master là gì?

Trong một mô hình **multi-master**, nhiều bản sao có thể nhận thao tác ghi và các thay đổi được lan truyền. AD DS hỗ trợ nhiều DC ghi được cho nhiều loại dữ liệu directory, thay vì chỉ một máy chủ duy nhất giữ quyền ghi mọi đối tượng.

Ưu điểm:

- Có thể thực hiện thay đổi gần nơi người dùng hoặc ứng dụng hoạt động.
- Không phụ thuộc vào duy nhất một DC ghi cho mọi thao tác.
- Tăng khả năng tiếp tục phục vụ khi một DC lỗi.

Thách thức:

- Có thể có **hai thay đổi cạnh tranh** trên cùng đối tượng/thuộc tính.
- Các DC không luôn nhìn thấy các thay đổi theo cùng thứ tự.
- Hệ thống cần metadata, quy tắc xử lý xung đột và cơ chế chống trùng.

### 6.2. Multi-master không có nghĩa mọi thao tác đều multi-master

AD DS còn có các vai trò **Flexible Single Master Operations (FSMO)**, dùng cho các thao tác đặc thù như schema, domain naming, RID allocation, PDC emulator và infrastructure master. Vì vậy:

**Không kết luận “AD multi-master nên có thể ghi mọi loại thay đổi ở bất cứ DC nào mà không có ràng buộc”.** Loại đối tượng/thuộc tính, role, quyền ghi và yêu cầu nghiệp vụ có thể giới hạn nguồn thay đổi.

### 6.3. Single-provider hoặc consumer replica ở sản phẩm khác

Một sản phẩm LDAP có thể dùng mô hình **một provider ghi, nhiều consumer nhận**, hoặc mô hình đa provider được cấu hình riêng. Không dùng cùng một thuật toán hòa giải cho mọi công nghệ chỉ vì chúng đều giao tiếp qua LDAP.

## 7. Cơ chế thay đổi và hội tụ trong AD DS

AD DS không đơn thuần copy toàn bộ tệp cơ sở dữ liệu theo định kỳ. Nó theo dõi những thay đổi và metadata để gửi phần cần thiết cho replication partner.

### 7.1. Những khái niệm quan trọng

| Khái niệm | Ý nghĩa | Điều không nên nhầm |
| --- | --- | --- |
| **Update Sequence Number (USN)** | Số thứ tự thay đổi được quản lý trong ngữ cảnh một DC/database | USN không phải đồng hồ tăng thống nhất toàn forest |
| **Invocation ID** | Định danh một phiên bản instance cơ sở dữ liệu AD trên DC | Không đồng nhất vĩnh viễn với hostname hoặc objectGUID DC |
| **High-watermark** | Dấu mốc giúp một đối tác biết những cập nhật đã nhận từ một nguồn cụ thể | Không đủ để suy ra mọi DC đã hội tụ |
| **Up-to-dateness vector** | Thông tin giúp theo dõi cập nhật nguồn gốc đã biết, tránh gửi lại không cần thiết | Cần diễn giải theo nguồn và partition |
| **Originating update metadata** | Metadata về cập nhật gốc, phiên bản và nguồn | Không đồng nhất với ngày giờ theo đồng hồ địa phương của người dùng |
| **Replicated update** | Thay đổi nhận từ đối tác và được áp vào bản sao | Không có nghĩa đây là một thay đổi nghiệp vụ mới |
| **Link-value replication** | Cách AD nhân bản một số thuộc tính liên kết đa giá trị, như membership | Không nên xem mọi group membership là một chuỗi text duy nhất |

### 7.2. USN là cục bộ, không phải mã sự kiện HRIS

Một DC có USN 150000 và DC khác có USN 500000 **không chứng minh DC thứ hai “mới hơn”** về mọi đối tượng. USN là cơ chế theo dõi thay đổi của một replica trong phạm vi cụ thể.

Khi quản trị IAM cần xác định người dùng đã Leaver hay chưa, **không so sánh USN giữa hai DC rồi chọn số lớn**. Cần đọc trạng thái từ nguồn có thẩm quyền và quan sát tình trạng replication của các bản sao liên quan.

### 7.3. Invocation ID và những trường hợp phải cảnh giác

Invocation ID giúp phân biệt một instance dữ liệu trong quá trình replication. Khi database được phục hồi hoặc có những thay đổi trạng thái nhất định, ngữ nghĩa invocation ID và USN cần được hệ thống bảo vệ để tránh **USN rollback** hoặc mất dấu thay đổi.

**Không khôi phục một DC bằng cách sao chép tùy tiện snapshot đĩa/VM rồi cho nó hoạt động như replica bình thường** nếu không theo quy trình backup/restore và khả năng hỗ trợ của AD DS/hypervisor. Thiết kế phục hồi phải tuân theo hướng dẫn sản phẩm và kiểm tra metadata replication.

### 7.4. Replication metadata giúp điều tra gì?

Metadata cấp đối tượng hoặc thuộc tính giúp trả lời:

- Bản sao nhận thay đổi gốc từ DC nào?
- Thuộc tính department, userAccountControl hoặc group membership đổi khi nào?
- Có một thay đổi khác ghi đè sau đó không?
- Đối tác replication nào chưa nhận đủ cập nhật?
- Lỗi là **chưa nhân bản**, **thay đổi bị xung đột** hay **đã nhân bản nhưng ứng dụng vẫn cache quyền**?

**Audit nghiệp vụ vẫn cần nguồn riêng.** Replication metadata có thể cho biết attribute được thay ở đâu, nhưng không luôn nói đủ **vì sao**, ai phê duyệt, ticket nào hay quyền nào đáng lẽ phải tồn tại.

## 8. Ví dụ diễn tiến replication và độ trễ

Giả sử:

~~~text
17:59:55  HRIS phát Leaver cho identity person-1042
18:00:00  IAM gửi lệnh disable account lên DC-HN-01
18:00:02  DC-HN-01 ghi thay đổi thành công
18:00:03  Ứng dụng A đọc DC-HN-01 -> account disabled
18:00:04  Ứng dụng B đọc DC-HCM-02 -> vẫn thấy trạng thái cũ
18:00:12  Replication tới DC-HN-02 thành công
18:01:30  Replication liên site tới DC-HCM-01 thành công
18:01:32  Replication tới DC-HCM-02 thành công
18:01:34  Ứng dụng B đọc lại -> account disabled
~~~

Các thời điểm là **giả định minh họa**, không phản ánh SLA mặc định của AD DS. Độ trễ thực phụ thuộc site topology, cấu hình, trạng thái mạng, đối tác, tải và các cơ chế phát hiện/thông báo thay đổi.

### 8.1. Ba thời điểm không được gộp

1. **RequestedAt:** IAM yêu cầu thay đổi.
2. **AppliedAt:** DC nhận lệnh ghi đã áp dụng.
3. **Converged/VerifiedAt:** các replica nằm trong **phạm vi yêu cầu** đã được kiểm tra và đạt trạng thái mong muốn.

Đối với Leaver, thêm một mốc khác: **AccessRevokedAt** tại ứng dụng/API/phiên. Nó không nhất thiết trùng với thời điểm tất cả DC hội tụ, do có cache, token hoặc hệ thống không phụ thuộc AD ở thời điểm truy cập.

### 8.2. Eventual consistency

**Eventual consistency** có nghĩa các bản sao có thể nhất thời khác nhau nhưng sẽ tiến tới cùng trạng thái khi thay đổi được phân phối thành công và xung đột được giải quyết theo cơ chế hệ thống.

Điều đó **không đảm bảo**:

- Thời gian hội tụ luôn bằng một giá trị cố định.
- Mọi lần truy vấn LDAP đều trả trạng thái mới nhất.
- Toàn bộ ứng dụng SaaS được cập nhật khi DC hội tụ.
- Phiên hiện tại của người dùng tự mất quyền khi dữ liệu directory được cập nhật.
- Một thay đổi hợp lệ có thể được xem là hoàn tất dù một replica lỗi kéo dài không có người xử lý.

## 9. Xử lý cập nhật cạnh tranh và xung đột

Trong hệ multi-master, hai DC có thể nhận cập nhật gần như đồng thời cho cùng đối tượng hoặc thuộc tính. Hệ thống cần cơ chế **conflict resolution** dựa trên metadata.

### 9.1. Cạnh tranh trên thuộc tính

Ví dụ:

~~~text
DC-A: department của An được đổi từ Support -> Finance
DC-B: department của An được đổi từ Support -> Operations

Hai thay đổi xuất phát trước khi mỗi DC nhận cập nhật của bên kia.
Cơ chế directory cần xác định một trạng thái cuối.
~~~

Trong AD DS, những cơ chế giải quyết xung đột sử dụng metadata như **version, timestamp và định danh nguồn** theo loại thay đổi và quy tắc hệ thống. Không nên diễn giải đơn giản rằng “DC nhận trước thắng” hoặc “thời gian đồng hồ lớn nhất luôn thắng” cho mọi trường hợp.

**Trạng thái hội tụ kỹ thuật vẫn có thể sai nghiệp vụ.** Nếu hai hệ thống tích hợp cùng có quyền ghi department, AD có thể chọn ra một giá trị cuối nhưng điều đó không chứng minh đây là giá trị **được HRIS phê duyệt**.

### 9.2. Conflict resolution không thay thế source of truth

Để tránh xung đột nghiệp vụ:

- Chỉ rõ hệ thống có thẩm quyền cho từng thuộc tính.
- Giới hạn quyền ghi ở connector và quản trị viên.
- Không để HRIS, script riêng và portal tự phục vụ đồng thời ghi những thuộc tính có chính sách sở hữu độc lập mà không có điều phối.
- Dùng version, correlation ID và audit nghiệp vụ khi triển khai update từ nhiều nguồn.
- Đối soát trạng thái directory với HRIS/IGA sau khi hội tụ.

### 9.3. Group membership và cập nhật song song

Các nhóm có thể được cập nhật bởi nhiều người hoặc hệ thống. Với một số thuộc tính liên kết đa giá trị trong AD, **link-value replication** giúp xử lý thay đổi membership theo từng liên kết thay vì ghi đè cả danh sách như một trường text đơn giản.

Dù vậy, nếu nhóm đặc quyền được thêm thành viên sai, replication vẫn lan truyền membership đó. **Least privilege, phê duyệt và kiểm tra SoD** phải bảo vệ quyền ghi và quá trình cấp nhóm.

## 10. Xóa đối tượng, tombstone và lingering objects

Xóa user hoặc group trong một directory phân tán không chỉ là xóa bản ghi tại một máy chủ. Các DC khác cần **biết rằng đối tượng đã bị xóa** để không coi nó là bản ghi mới cần phục hồi.

### 10.1. Tombstone và trạng thái xóa

AD DS sử dụng những trạng thái/metadata liên quan tới deletion và garbage collection; cách giữ và khôi phục đối tượng chịu ảnh hưởng cấu hình như **tombstone lifetime** và **Active Directory Recycle Bin** khi được bật.

Các khái niệm cần phân biệt:

- **Disable account:** tài khoản vẫn tồn tại nhưng bị hạn chế đăng nhập theo trạng thái/chính sách.
- **Delete account:** đối tượng được chuyển qua vòng đời xóa, thông tin xóa cần được nhân bản.
- **Tombstone/deleted object:** dạng biểu diễn giúp các replica biết việc xóa đã xảy ra.
- **Garbage collection:** cuối vòng giữ, dữ liệu có thể được loại bỏ theo cơ chế hệ thống.
- **Recycle Bin:** nếu được hỗ trợ/bật, giúp phục hồi một số đối tượng/thuộc tính theo điều kiện; không đồng nghĩa backup toàn hệ thống.

**Không dùng thao tác delete vội vàng thay cho Leaver.** Offboarding thường cần chặn truy cập, bàn giao dữ liệu, áp retention và audit trước khi xóa account theo policy.

### 10.2. Lingering object

**Lingering object** có thể xuất hiện khi một DC không nhận được cập nhật xóa trong thời gian dài, ví dụ offline vượt quá cửa sổ phù hợp, trong khi thông tin deletion đã bị dọn khỏi các replica khác.

Vì sao nguy hiểm?

- DC cũ còn đối tượng mà các DC khác xem đã xóa.
- Một số quá trình replication có thể phát hiện/từ chối trạng thái không nhất quán.
- Truy vấn từ site phụ thuộc DC cũ có thể phản ánh account không đáng tồn tại.
- Khắc phục không đúng cách có thể làm mất hoặc làm tái xuất dữ liệu.

**Không tự sửa lingering object bằng cách chỉnh metadata hoặc bật các tùy chọn replication rủi ro mà không có runbook và backup hợp lệ.** Cần đánh giá tình trạng forest, thời gian offline, strict replication consistency và tài liệu vận hành của nền tảng trước khi xử lý.

### 10.3. Sao lưu không phải nhân bản

Nếu quản trị viên xóa nhầm một OU, việc xóa hợp lệ có thể được nhân bản tới mọi DC. **Replication sẽ lan truyền thao tác sai**, còn backup phù hợp và quy trình khôi phục được kiểm soát mới giúp phục hồi trạng thái theo chính sách.

## 11. OpenLDAP và các mô hình replication khác

Không chỉ AD DS mới có nhân bản directory. Ví dụ **OpenLDAP** hỗ trợ các cấu hình replication dựa trên **syncrepl**; tùy thiết kế có thể có một provider và nhiều consumer hoặc các mô hình đa provider được cấu hình riêng.

### 11.1. Syncrepl ở mức khái niệm

- **Provider:** bên cung cấp trạng thái/thay đổi LDAP cho consumer.
- **Consumer:** bản sao nhận và áp dụng dữ liệu từ provider.
- **refreshOnly:** consumer định kỳ đồng bộ theo chu kỳ.
- **refreshAndPersist:** consumer duy trì việc theo dõi thay đổi sau giai đoạn refresh.
- **Cookie/CSN:** hỗ trợ theo dõi điểm tiến độ đồng bộ của consumer/nguồn theo mô hình sản phẩm.
- **Delta-syncrepl:** có thể dùng dữ liệu log thay đổi hỗ trợ đồng bộ theo delta trong cấu hình phù hợp.

Ví dụ logic:

~~~text
Ứng dụng IAM ghi vào OpenLDAP Provider
           |
           v
Provider cập nhật entry/attribute
           |
           +--(syncrepl)--> Consumer A
           +--(syncrepl)--> Consumer B
           |
           v
Consumer cập nhật và lưu tiến độ
~~~

**Không dùng từ USN/high-watermark theo AD để giải thích mọi trường hợp OpenLDAP.** Metadata như contextCSN, cookie và mô hình đồng bộ phải được diễn giải theo phiên bản/cấu hình OpenLDAP thực tế.

### 11.2. Multi-provider cần thiết kế xung đột

Khi cấu hình nhiều provider có thể ghi, đội vận hành phải hiểu giới hạn conflict resolution, uniqueness và quy tắc sở hữu thuộc tính của giải pháp. **Không giả định syncrepl là giao thức consensus** hoặc tự bảo đảm mọi thay đổi nghiệp vụ được tuần tự hóa tuyệt đối.

### 11.3. Khi nào cần chọn công nghệ nào?

Việc chọn AD DS, OpenLDAP hoặc một directory khác phụ thuộc kiến trúc hạ tầng, ứng dụng LDAP/Kerberos cần dùng, sơ đồ identity, cơ chế replication, bảo mật, khả năng giám sát và vận hành. **Bài học tập trung vào nguyên lý replication**, không khuyến nghị thay thế một sản phẩm bằng sản phẩm khác chỉ dựa trên một tính năng.

## 12. Tác động tới xác thực, SSO và IdP

Một IdP có thể đọc tài khoản, group hoặc trạng thái từ directory; nhưng tác động của replication phụ thuộc vào kiến trúc cụ thể.

### 12.1. LDAP bind, Kerberos và directory lookup

Một hệ thống có thể:

- Dùng LDAP để tìm account và thuộc tính.
- Sử dụng cơ chế xác thực được hỗ trợ bởi directory/AD DS, chẳng hạn Kerberos.
- Đồng bộ danh tính vào IdP cloud rồi xác thực ở cloud.
- Dùng federation OIDC/SAML qua IdP trong khi ứng dụng giữ session riêng.

**Không phải mọi lần OIDC/SAML login đều trực tiếp truy vấn một DC tại thời điểm đó.** IdP cloud có thể dùng dữ liệu đã đồng bộ hoặc nguồn xác thực riêng. Vì vậy khi đánh giá Leaver, cần biết **đường đi thực tế từ directory tới quyết định truy cập**.

### 12.2. Nhóm được nhân bản, nhưng token có thể giữ quyền cũ

Một membership bị gỡ ở AD có thể cần thời gian để:

1. Replicate đến DC mà dịch vụ đăng nhập thực sự dùng.
2. Được IdP hoặc ứng dụng đọc/đồng bộ lại.
3. Làm mới token, ticket hoặc cache/phiên liên quan.
4. Ảnh hưởng tới authorization ở tài nguyên cuối.

Trong một số môi trường Kerberos, thông tin group có thể được đưa vào ticket/PAC và tiếp tục có ý nghĩa trong thời gian ticket còn hiệu lực. Với OIDC, group claim trong ID/access token cũng có thể còn cũ. **Replication hoàn tất chỉ giải quyết một lớp**, không đồng nghĩa mọi phiên đã mất quyền.

### 12.3. SSO không thay thế deprovisioning

Nếu account đã bị vô hiệu hóa trong directory nhưng ứng dụng SaaS có user local, API token và session độc lập, quy trình Leaver cần **SCIM/API deprovisioning, token/session controls và reconciliation** bên cạnh thay đổi directory.

## 13. Directory replication và đồng bộ cloud/hybrid

Trong môi trường hybrid, dữ liệu có thể đi qua nhiều pipeline:

~~~mermaid
flowchart TD
  HR["HRIS / IAM"] --> A["AD DC-A"]
  A <-->|"AD replication"| B["AD DC-B"]
  A --> SYNC["Hybrid identity synchronization"]
  SYNC --> CLOUD["Cloud IdP"]
  CLOUD -->|"OIDC / SAML"| SAAS["SaaS SSO"]
  CLOUD -->|"SCIM hoặc API riêng"| TARGET["SaaS account / groups"]
  TARGET --> VERIFY["Observed state / audit"]
  B --> VERIFY
  SAAS --> VERIFY
~~~

Cần phân biệt:

- **AD DC replication:** cập nhật giữa các replica của AD DS.
- **Hybrid synchronization:** chuyển/ánh xạ thay đổi từ on-prem directory sang cloud IdP theo khả năng công cụ.
- **Cloud directory internal replication:** cơ chế nội bộ nhà cung cấp cloud; người dùng dịch vụ thường không kiểm soát chi tiết DC như AD on-prem.
- **SCIM provisioning:** quản lý user/group ở SaaS đích.
- **Federation/OIDC/SAML:** xác thực đăng nhập qua IdP.
- **Authorization:** role/permission thực thi tại ứng dụng/API.

**Một dấu tích “sync thành công” ở pipeline hybrid không đủ chứng minh mọi SaaS đã thu hồi quyền và mọi local session đã hết hạn.** Cần đánh giá độ trễ end-to-end và trạng thái đích.

### 13.1. Những câu hỏi thiết kế quan trọng

- Thuộc tính nào có nguồn HRIS, thuộc tính nào do AD hoặc cloud IdP quản lý?
- Khi cùng người có cả account on-prem và cloud, bản đồ identity/account được xác minh bằng khóa nào?
- Nếu AD replication đang lỗi, hybrid sync đọc DC nào và dữ liệu mới đến đâu?
- Nếu pipeline tạm ngừng, có cơ chế cảnh báo Leaver chậm không?
- Ứng dụng SaaS có dữ liệu quyền cục bộ hoặc JIT account ngoài SCIM không?
- Ai sở hữu quy trình khắc phục khi AD đã đúng nhưng cloud/SaaS còn sai?

## 14. Joiner: nhân bản tài khoản mới và điều kiện kích hoạt

Trong Joiner lifecycle, HRIS hoặc nguồn hợp đồng xác nhận một người bắt đầu quan hệ làm việc. IAM sau đó có thể tạo account directory, gán nhóm và đồng bộ các ứng dụng.

### 14.1. Quy trình Joiner minh họa

1. Xác minh nguồn, identityId, loại quan hệ, **effectiveAt** và người quản lý.
2. Thực hiện identity proofing và liên kết đúng tài khoản cần tạo.
3. IAM tạo object user và các thuộc tính được phép ở writable DC.
4. Directory replication lan thay đổi tới những DC trong scope.
5. IdP/SSO và ứng dụng lấy dữ liệu, provisioning SCIM/API hoặc JIT theo thiết kế.
6. RBAC/ABAC tính quyền tối thiểu và approval phù hợp.
7. Reconciliation xác minh account/entitlement thật tại từng đích.

### 14.2. Tạo account trước ngày đi làm

Tổ chức có thể **pre-provision** account trước effectiveAt nhưng hạn chế đăng nhập/quyền. Nếu tài khoản đã được nhân bản tới các DC, điều đó **không tự hợp thức hóa việc mở quyền trước ngày bắt đầu**.

Khi HRIS thay đổi ngày hoặc hủy nhận việc, cần:

- Hủy lịch kích hoạt cũ.
- Cập nhật account và các nhóm đã chuẩn bị.
- Đảm bảo thao tác hủy/disable được nhân bản tới các DC liên quan.
- Thu hồi account/quyền đã provision ở ứng dụng khác.
- Kiểm tra sự kiện trễ hoặc workflow cũ không tạo lại tài khoản.

### 14.3. Thấy account ở DC này, không thấy ở DC khác

Với Joiner, độ trễ có thể khiến người mới đăng nhập thất bại khi ứng dụng liên hệ DC chưa nhận user. Đây có thể là **MISSING_ACCOUNT tạm thời**, nhưng cần phân biệt với lỗi nguồn, account linking, định tuyến site hoặc quyền ứng dụng chưa được cấp.

**Không xử lý bằng cách tạo thêm account thứ hai ở DC khác** nếu nguyên nhân là replication lag. Điều đó dễ gây trùng định danh và sự cố account linking.

## 15. Mover: group, thuộc tính và quyền tồn dư

**Mover** xảy ra khi người dùng thay đổi bộ phận, vị trí, dự án, người quản lý, pháp nhân hoặc nhiệm vụ. Một thay đổi có thể ảnh hưởng cùng lúc:

- **Department / manager / OU** và những policy dùng các thuộc tính đó.
- **Group membership** tại directory.
- **Vai trò ứng dụng** được ánh xạ từ nhóm.
- **RBAC/ABAC** tại API và tài nguyên.
- **Phiên/token** mang thông tin cũ.
- **Service account ownership** nếu người dùng đang quản lý workload.

### 15.1. Ví dụ thay đổi vai trò

~~~text
Trước Mover:
  department = Support
  group      = CRM-SupportReaders
  app role   = SupportRead

Sau Mover được phê duyệt:
  department = Finance
  group      = FinanceReaders
  app role   = FinanceRead

Tại DC-A:
  Support group = removed; Finance group = added

Tại DC-B (chưa hội tụ):
  Support group = present; Finance group = missing

Tại SaaS:
  SupportRead vẫn còn vì session hoặc provisioning chậm
~~~

Nếu chỉ nhìn DC-A, đội IAM dễ kết luận đã gỡ quyền Support, nhưng người dùng vẫn có thể sở hữu quyền qua DC-B hoặc SaaS. Cần theo dõi **cả directory convergence lẫn quyền hiệu lực** tại đích.

### 15.2. Quyền mẫu tích lũy

Một chiến lược sai là chỉ **thêm nhóm mới** khi Mover. Qua nhiều lần chuyển bộ phận, người dùng tích lũy nhóm, gây **privilege creep**.

Thực hiện đúng:

1. Tính **desired access** từ role/thuộc tính/approval hiện hành.
2. So với **observed access**, bao gồm group directory, role trực tiếp và quyền SaaS.
3. Thu hồi những quyền không còn hợp lệ.
4. Kiểm tra replication và trạng thái ứng dụng.
5. Xử lý token/phiên cũ khi chính sách cần thu hồi nhanh.
6. Lưu audit từ sự kiện HRIS đến bằng chứng cuối.

## 16. Leaver: tốc độ vô hiệu hóa và rủi ro còn truy cập

**Leaver** là thời điểm dữ liệu replication có tác động bảo mật rất rõ. Một chênh lệch nhỏ ở trạng thái **enabled/disabled** hoặc group đặc quyền có thể mở thêm cửa sổ truy cập.

### 16.1. Một luồng Leaver cần nhiều kiểm soát

~~~mermaid
flowchart TD
  HR["HRIS: Leaver có hiệu lực"] --> IAM["IAM: tính trạng thái cần thu hồi"]
  IAM --> AD["Disable / remove groups ở writable DC"]
  AD --> R["Directory replication giữa các DC"]
  IAM --> S["SCIM/API: thu hồi SaaS và cloud"]
  IAM --> T["Thu hồi session/token/credential trong scope"]
  R --> V["Reconciliation"]
  S --> V
  T --> V
  V --> X{"Các đường truy cập bắt buộc đã chặn?"}
  X -->|"Chưa"| E["Exception + owner + escalation"]
  X -->|"Đã có bằng chứng"| F["Đóng workflow + audit"]
  E --> V
~~~

### 16.2. Trạng thái disabled không tự là bằng chứng hoàn tất

Một tài khoản có thể đã disabled trên DC chính nhưng:

- DC ở site khác chưa nhận thay đổi.
- IdP cloud chưa đồng bộ.
- Ứng dụng SaaS giữ local account.
- Phiên OIDC/SAML đã lập vẫn hoạt động.
- API token, SSH key, chứng chỉ hoặc quyền cloud IAM độc lập chưa bị xử lý.
- Nhóm đặc quyền đã gỡ trong directory nhưng quyền kế thừa hoặc cache vẫn tồn tại.

Do đó, **không kết luận Leaver hoàn tất chỉ bằng một lệnh LDAP modify hoặc một bản ghi HRIS TERMINATED**. Cần chứng minh các đường truy cập nằm trong scope đã bị vô hiệu hóa hoặc có biện pháp kiểm soát phù hợp.

### 16.3. Biện pháp bổ sung khi thu hồi khẩn cấp

Với tài khoản bị nghi chiếm quyền hoặc nghỉ việc rủi ro cao, việc chờ replication hội tụ có thể chưa đủ. Tùy kiến trúc và thẩm quyền, tổ chức có thể cần:

- Vô hiệu hóa account tại các control plane quan trọng.
- Chấm dứt phiên và revoke token có thể thu hồi.
- Gỡ/khóa quyền trực tiếp tại cloud/SaaS/ứng dụng.
- Tăng kiểm tra quyền hiện hành ở backend cho hành động nhạy cảm.
- Hạn chế credential hoặc đường truy cập thiết bị riêng.
- Theo dõi các DC/đích chưa hội tụ và xử lý ngoại lệ đến khi có bằng chứng.

**Không biến thao tác “force replicate” thành thay thế cho khẩn cấp deprovisioning** ở các hệ thống không chia sẻ directory.

## 17. RBAC/ABAC và độ mới của dữ liệu

### 17.1. RBAC dựa trên group

Nhiều ứng dụng ánh xạ directory group sang role. Khi group được thêm hoặc gỡ:

- Replication phải đưa group membership tới DC liên quan.
- IdP/ứng dụng có thể cần đọc lại hoặc đồng bộ group.
- Token/ticket hoặc session cũ có thể giữ các claim trước thay đổi.
- Tài nguyên cuối cùng vẫn phải kiểm tra role/permission phù hợp.

Đó là lý do **directory replication hoàn tất không bằng authorization convergence**.

### 17.2. ABAC dựa trên thuộc tính

Một policy minh họa:

~~~text
ALLOW invoice.read IF
  identity.lifecycleStatus == ACTIVE
  AND identity.department == resource.ownerDepartment
  AND identity.hasApprovedRole("FinanceReader")
  AND session.assuranceSatisfies(requiredAssurance)
ELSE DENY
~~~

Nếu **department** chưa replicate hoặc dữ liệu trong token cũ, ABAC có thể ra quyết định theo thuộc tính cũ. Chính sách phải xác định:

- Nguồn nào có thẩm quyền cho department.
- Tuổi dữ liệu tối đa cho phép.
- Có cần truy vấn quyền/thông tin mới trước hành động nhạy cảm không.
- Cách phản ứng nếu nguồn không sẵn sàng.
- Cơ chế chặn trong sự cố Leaver hoặc tài khoản bị khóa.

### 17.3. Quyền hiệu lực khác membership được lưu

Một người có thể có group FinanceReaders tại directory nhưng ứng dụng vẫn từ chối vì **resource scope không khớp**. Ngược lại, người đã bị gỡ khỏi nhóm có thể còn quyền trực tiếp ở ứng dụng.

Do đó reconciliation cần kiểm tra **effective entitlement** ở đích, không chỉ nhóm AD.

## 18. Replication với tài khoản dịch vụ và danh tính phi con người

**Service account, computer account, group-managed service account (gMSA), workload identity** hoặc principal phục vụ connector là những danh tính có vòng đời riêng.

### 18.1. Điều gì có thể bị nhân bản?

Tùy công nghệ, directory có thể chứa:

- Object service account hoặc computer account.
- Group membership và thuộc tính quyền liên quan.
- Metadata cho các cơ chế credential/secret của hệ thống.
- Các thuộc tính phục vụ việc xác định máy/dịch vụ được phép sử dụng một principal.

**Không phải mọi workload credential đều được lưu hoặc nhân bản trong AD DS.** Managed identity của cloud, khóa trong secret manager hoặc OAuth client credential có thể nằm ở control plane khác.

### 18.2. Rủi ro và kiểm soát

| Tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| Owner service account Mover/Leaver | Quyền quản trị của người cũ còn tồn tại | Chuyển owner, gỡ quyền người cũ, xác minh trên mọi hệ thống |
| Secret/credential thay đổi | Replica hoặc consumer cũ chưa cập nhật | Theo dõi khả năng hội tụ và phụ thuộc ứng dụng |
| Workload bị decommission | Service account/group vẫn hoạt động | Inventory, end-of-life, thu hồi quyền và audit |
| Replication lỗi ở site đặt workload | Dịch vụ đọc dữ liệu cũ | Xác định mục tiêu RPO/availability và cơ chế khôi phục |
| Service principal có quyền replication cao | Kẻ tấn công có thể khai thác dữ liệu directory nhạy cảm | Least privilege, phân quyền chặt, giám sát hành vi và credential |
| RODC ở chi nhánh | Rủi ro lộ thông tin xác thực nếu thiết bị bị chiếm | Cấu hình Password Replication Policy và bảo vệ thiết bị |

**Không dùng event Leaver của owner để xóa ngay workload còn phục vụ sản xuất.** Cần gỡ quyền người cũ, bàn giao owner và quản trị credential mà không gây gián đoạn ngoài ý muốn.

## 19. Bảo vệ kênh replication và dữ liệu nhạy cảm

Nhân bản directory có thể chuyển dữ liệu quan trọng đối với toàn bộ tổ chức. Một sự cố ở DC hoặc tài khoản có quyền replication cao có thể lan ảnh hưởng lớn hơn lỗi của một ứng dụng.

### 19.1. Các kiểm soát chính

1. **Giới hạn quyền quản trị:** chỉ tài khoản/dịch vụ thực sự cần mới có quyền thao tác replication hoặc thay đổi topology.
2. **Bảo vệ danh tính DC:** hardening hệ điều hành, quản lý bản vá, truy cập vật lý và bảo vệ khóa/credential.
3. **Bảo vệ kênh:** dùng giao thức xác thực và bảo mật được nền tảng hỗ trợ cho replication; tránh cấu hình hạ bảo mật.
4. **Phân đoạn mạng:** chỉ cho lưu lượng replication cần thiết giữa các DC/site, theo sơ đồ và chính sách mạng.
5. **Giám sát thay đổi đặc quyền:** theo dõi bổ sung membership nhóm đặc quyền, thay đổi quyền replication, sửa chính sách xác thực và trust.
6. **Quản lý credential:** secret/khóa phải được bảo vệ theo cơ chế sản phẩm; không log dữ liệu bí mật.
7. **Bảo vệ backup:** quyền truy cập, mã hóa, thử khôi phục và quy trình xử lý sự cố phù hợp.
8. **Bảo vệ audit:** ghi thay đổi cấu hình, danh tính quản trị, lỗi replication và xử lý ngoại lệ.
9. **Giới hạn DC/site bị rủi ro:** đánh giá RODC, credential caching, phân quyền chi nhánh.
10. **Định nghĩa nguồn có thẩm quyền:** replication không có trách nhiệm hợp thức hóa dữ liệu bị viết sai.

### 19.2. Cẩn trọng với quyền nhân bản dữ liệu nhạy cảm

Một số quyền replication trong AD có thể cho phép đọc những loại dữ liệu rất nhạy cảm qua cơ chế riêng của directory. Không cấp quyền nhân bản rộng chỉ để một connector đọc vài thuộc tính cơ bản.

**Đừng coi quyền đọc LDAP bình thường và quyền replication đặc quyền là tương đương.** Khi connector hoặc service principal có quyền cao, phải phân loại rủi ro, giám sát và có quy trình rotation/revoke phù hợp.

### 19.3. Quyền riêng tư và kiểm toán

Directory có thể chứa email, thông tin tổ chức, người quản lý, số nhân viên và thuộc tính nhạy cảm. Log replication không nên trở thành nơi sao chép toàn bộ dữ liệu cá nhân hoặc bí mật. Nên lưu **object reference, thời điểm, loại thay đổi, trạng thái, người chịu trách nhiệm và correlation ID** ở mức cần thiết.

## 20. Giám sát replication và chẩn đoán lỗi

### 20.1. Các nhóm tín hiệu

| Tín hiệu | Mục tiêu | Rủi ro khi bỏ qua |
| --- | --- | --- |
| **Replication health** | Biết cặp DC/partition nào lỗi hoặc quá hạn | Replica giữ dữ liệu cũ |
| **Last successful replication** | Đo thời gian từ lần nhân bản thành công | Leaver có thể không lan tới site |
| **Replication queue/backlog** | Theo dõi thay đổi đang chờ xử lý | Độ trễ tăng dù kết nối còn |
| **Topology/site link health** | Kiểm tra đường truyền, lịch, đối tác | Site bị cô lập |
| **DNS/DC locator** | Đảm bảo ứng dụng và DC tìm đúng dịch vụ | Gặp DC không mong muốn hoặc không thể kết nối |
| **Authentication/time health** | Hỗ trợ giao thức bảo mật và xử lý metadata | Lỗi Kerberos, RPC hoặc chẩn đoán sai |
| **Lingering object/tombstone warnings** | Phát hiện DC quá lâu không nhận dữ liệu xóa | Đối tượng cũ tồn tại hoặc replication bị chặn |
| **Provisioning vs observed data** | Đối chiếu IAM và directory | Lệnh thành công nhưng quyền sai |
| **Token/session propagation** | Phát hiện đường truy cập tồn dư sau Mover/Leaver | Nhân bản xong nhưng vẫn truy cập được |

### 20.2. Ví dụ công cụ kiểm tra AD DS

Các lệnh sau chỉ để **minh họa lệnh kiểm tra/troubleshooting**, không được thực thi trong bài học và cần quyền/công cụ thích hợp khi áp dụng thực tế:

~~~powershell
# Tóm tắt tình trạng replication giữa các DC.
repadmin /replsummary

# Xem trạng thái inbound replication trên DC liên quan.
repadmin /showrepl DC-HN-01

# Kiểm thử sức khỏe replication với dcdiag.
dcdiag /test:Replications

# Ví dụ PowerShell Active Directory module khi có sẵn:
Get-ADReplicationPartnerMetadata -Target "DC-HN-01" -Scope Server
~~~

**Đọc kết quả theo forest/domain/site/partition thực tế.** Một báo cáo không có lỗi ở một DC chưa chứng minh mọi DC khác hoặc tất cả ứng dụng đã hội tụ.

### 20.3. Cách tiếp cận OpenLDAP

Có thể kiểm tra trạng thái provider/consumer, kết quả syncrepl, các giá trị theo dõi **contextCSN** nếu hệ thống công bố và log phù hợp.

Không tự giả định **contextCSN giống USN của AD** hoặc chỉ so một chuỗi timestamp là đủ chứng minh toàn bộ nội dung đã nhất quán. Cần xét quyền đọc, scope, cookie/CSN và cơ chế sản phẩm.

## 21. Quy trình xử lý lỗi nhân bản

### 21.1. Các bước điều tra an toàn

1. **Khoanh vùng:** DC, site, domain, partition, đối tượng và thời gian bắt đầu sai lệch.
2. **Gắn mức rủi ro:** có liên quan Leaver, quyền admin, credential hoặc dữ liệu nhạy cảm không?
3. **Kiểm tra nguồn nghiệp vụ:** HRIS/IGA đang yêu cầu trạng thái nào? Có sự kiện Mover/Leaver mới hơn không?
4. **Đọc trạng thái từng replica liên quan:** xác minh ID đối tượng và giá trị, không so theo email đơn thuần.
5. **Kiểm replication health:** đối tác, lần thành công gần nhất, mạng, DNS, thời gian, lỗi xác thực và backlog.
6. **Đánh giá topology/site link:** xác định site bị cô lập hoặc schedule không phù hợp.
7. **Xác định dạng sự cố:** lag tạm thời, quyền truy cập, conflict, dữ liệu xóa, snapshot/restore lỗi hay lingering object.
8. **Chọn biện pháp có runbook:** sửa kết nối/cấu hình hoặc khôi phục theo tài liệu sản phẩm; tránh thao tác phá hủy khi chưa rõ nguyên nhân.
9. **Đọc lại và đối soát:** xác minh trạng thái directory và các hệ thống đích, gồm token/phiên khi có yêu cầu.
10. **Đóng sự cố với audit:** nguyên nhân, thời điểm phát hiện, hành động, ai duyệt và bằng chứng hội tụ.

### 21.2. Phân loại lỗi để xử lý

| Hiện tượng | Khả năng nguyên nhân | Kiểm tra/điều phối |
| --- | --- | --- |
| DC trong site có user mới, DC khác chưa có | Replication lag hoặc lỗi đối tác | Kiểm trạng thái liên kết và thời gian replication |
| Không có thay đổi giữa hai site | WAN, site link, lịch, topology | Kiểm site/network, lịch và đối tác |
| Chỉ một loại object/attribute không như mong đợi | Scope partition, GC/RODC, schema, ACL hoặc mapping | Kiểm thuộc tính/partition và khả năng replica |
| Xóa đối tượng nhưng site cũ còn | Offline lâu, deletion metadata, lingering object | Điều tra theo runbook, không vội cho phép replication rủi ro |
| IdP vẫn thấy department cũ dù AD DC đã đúng | Hybrid sync/cache hoặc đọc replica khác | Kiểm đường đồng bộ end-to-end |
| Sai role dù group đúng ở AD | Mapping, quyền local, token/session cũ | Kiểm RBAC/ABAC và ứng dụng đích |
| Event Leaver cũ bị đảo bằng Joiner trễ | Lỗi version guard ở provisioning | Chặn task cũ, so trạng thái nguồn hiện hành |
| Service account không còn owner | Quy trình bàn giao/IGA thiếu | Gắn owner và kiểm credential, không xóa tùy tiện |

### 21.3. Không dùng “ép đồng bộ” như thuốc chữa mọi lỗi

Một hành động yêu cầu replication ngay có thể hữu ích trong điều kiện thích hợp, nhưng nếu lỗi là **sai nguồn thuộc tính, account linking, cache token hoặc SCIM thất bại**, chạy replication lại sẽ không giải quyết gốc vấn đề. Cần xác minh **đúng lớp bị lỗi** trước khi khắc phục.

## 22. Thiết kế chỉ số và SLA cho IAM

| Chỉ số | Cách hiểu | Ý nghĩa |
| --- | --- | --- |
| **Replication success rate** | Tỷ lệ lần nhân bản thành công trong phạm vi giám sát | Độ tin cậy directory |
| **Replication latency** | Khoảng từ thay đổi gốc tới lúc replica liên quan áp dụng | Nhìn thấy cửa sổ dữ liệu cũ |
| **Last successful replication age** | Thời gian kể từ lần đối tác đồng bộ thành công | Phát hiện DC/site cô lập |
| **Backlog size** | Số thay đổi hoặc độ chênh tồn đọng theo công cụ | Nguy cơ hội tụ chậm |
| **JML provisioning latency** | Từ effectiveAt tới khi account/quyền đích đúng | Ảnh hưởng hoạt động Joiner |
| **Mover revoke latency** | Từ khi quyền cũ hết hợp lệ tới khi được xác minh đã gỡ | Đo privilege creep |
| **Leaver access revocation latency** | Từ thời điểm Leaver có hiệu lực tới bằng chứng chặn truy cập | Đo quyền tồn dư |
| **Inconsistent replica count** | Số replica nằm ngoài trạng thái mong muốn trong scope | Điểm mù dữ liệu |
| **Account-linking exceptions** | Account chưa nối hoặc nối mơ hồ | Nguy cơ sai chủ thể |
| **Unresolved replication incidents** | Sự cố quá hạn remediation | Tích tụ rủi ro vận hành |
| **Stale authorization evidence** | Số quyết định quyền dùng claim/phiên quá cũ | Khoảng trống giữa directory và ứng dụng |
| **Workload owner coverage** | Tỷ lệ service identity có owner hợp lệ | Giảm principal mồ côi |

**Không đặt một con số SLA chung cho mọi thành phần** rồi cho rằng đó là đặc tính mặc định của AD/LDAP. Mỗi tổ chức cần xác định tiêu chí theo **site, loại thay đổi, mức nhạy cảm và đường truy cập cuối cùng**.

Ví dụ: yêu cầu chuẩn bị user cho Joiner có thể cho phép thời gian hội tụ lâu hơn so với thu hồi quyền admin production trong tình huống khẩn cấp. Một hệ thống yêu cầu revoke tức thời phải có **kiểm soát tại điểm thực thi**, không chỉ dựa vào eventual consistency.

## 23. Tình huống tổng hợp: Joiner, Mover và Leaver qua hai site

Giả sử doanh nghiệp có DC-A ở site Hà Nội và DC-B ở site TP.HCM, một IdP tích hợp directory và một SaaS có SCIM provisioning.

### 23.1. Joiner – ngày đầu đi làm

Nhân viên **Lan** bắt đầu ngày 01/12/2026.

- HRIS xác nhận nguồn, ngày hiệu lực, bộ phận Finance và manager.
- IAM tạo account ở DC-A, gán nhóm FinanceReaders.
- DC-B chưa nhận thay đổi vì WAN bị gián đoạn trong thời gian ngắn.
- Người dùng ở TP.HCM thử đăng nhập ứng dụng đang truy vấn DC-B và gặp lỗi chưa thấy user.
- Đội vận hành kiểm tra replication thay vì tạo thêm một account Lan mới.
- Sau khi DC-B hội tụ, IdP và ứng dụng nhận dữ liệu phù hợp; reconciliation xác minh đúng account/quyền.

**Kết luận:** tạo account ở DC-A thành công chưa đồng nghĩa mọi điểm truy vấn đã có user.

### 23.2. Mover – chuyển sang Operations

Ba tháng sau, Lan chuyển Finance sang Operations:

- IAM gỡ FinanceReaders, thêm OperationsReaders trên directory.
- Một site nhận cập nhật muộn; IdP vẫn giữ claim Finance trong phiên cũ.
- SaaS còn role FinanceReportRead dù claim directory hiện hành đã đổi.
- Reconciliation phát hiện **EXTRA_ACCESS** ở SaaS và tiếp tục yêu cầu thu hồi.
- Đối với dữ liệu nhạy cảm, API kiểm tra quyền hiện hành thay vì chỉ tin token cũ.

**Kết luận:** nhân bản group và thay đổi token/role ứng dụng là các bước riêng. Step-up, nếu có, chỉ bổ sung bảo đảm xác thực; **không thay thế gỡ quyền**.

### 23.3. Leaver – nghỉ việc

Lan nghỉ lúc 18:00 theo HRIS:

- IAM yêu cầu disable account tại writable DC và đồng thời deprovision SaaS.
- DC-B đang lỗi replication nên vẫn thấy trạng thái trước 18:00.
- Quy trình offboarding khẩn cấp chặn phiên IdP/SaaS theo khả năng, thu hồi role nhạy cảm tại ứng dụng và tạo exception cho DC-B.
- Sau sửa kết nối, DC-B nhận thay đổi; đội vận hành đọc lại trạng thái và so với desired state.
- Audit ghi rõ **requestedAt, appliedAt, verifiedAt**, đường truy cập đã chặn và ngoại lệ nào đã đóng.

**Kết luận:** nếu chỉ nhìn log “disable user thành công trên DC-A”, tổ chức chưa đủ cơ sở chứng minh Leaver hoàn tất.

## 24. Checklist triển khai directory replication

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Đã xác định domain, DC, site, partition trong scope? | Topology và danh mục DC được quản lý |
| Có phân biệt AD DS replication, LDAP query và SCIM provisioning? | Sơ đồ các đường dữ liệu và chủ sở hữu |
| Có hiểu GC/RODC giữ dữ liệu gì? | Partition/attribute/credential caching policy |
| Có cấu hình site link, lịch và khả năng WAN phù hợp? | Health và latency theo site |
| Có theo dõi USN/invocation ID/metadata theo ngữ cảnh đúng? | Báo cáo replication, không so USN thô giữa DC |
| Có giám sát tombstone và DC offline quá lâu? | Cảnh báo, runbook lingering object |
| Có quy trình backup/restore phù hợp AD DS? | Backup đã được thử, runbook được phê duyệt |
| Connector có quyền tối thiểu để đọc/ghi directory? | Role/ACL, inventory và audit |
| Có bảo vệ các quyền replication đặc quyền? | Review quyền, giám sát, credential security |
| Có đồng bộ source-of-truth cho từng thuộc tính? | HRIS/IGA ownership và conflict handling |
| Có đo độ trễ từ HRIS tới từng replica quan trọng? | EffectiveAt, appliedAt, verifiedAt |
| Có kiểm tra account linking bằng ID bền vững? | identityId, objectGUID/SID theo scope, target IDs |
| Joiner có tránh tạo account trùng khi lag? | Retry/idempotency và xác minh danh tính |
| Mover có gỡ nhóm/role cũ trên mọi đích cần thiết? | Desired vs observed, reconciliation |
| Leaver có chặn token/phiên độc lập directory? | Session controls, SCIM/API và audit |
| Có kiểm tra GC, token cache và SSO khi truy cập nhạy cảm? | Policy kiểm quyền hiện hành phù hợp |
| Có quản lý service account/gMSA và owner? | Inventory, quyền và credential lifecycle |
| Có báo cáo UNKNOWN khi replica/connector không đọc được? | Completeness flag, exception có owner |
| Có test WAN outage và DC restore? | Kế hoạch sự cố và kết quả kiểm thử |
| Có KPI cho latency, failure, backlog và quyền tồn dư? | Dashboard theo rủi ro và site |

## 25. Những nhầm lẫn thường gặp

1. **“LDAP có sẵn một thuật toán replication chung.”** LDAP là giao thức truy cập; cơ chế nhân bản do sản phẩm định nghĩa.
2. **“Ghi vào một DC nghĩa là mọi DC đã cập nhật.”** Replication có thể trễ hoặc thất bại.
3. **“USN lớn hơn nghĩa là DC mới hơn.”** USN có ý nghĩa trong ngữ cảnh DC/database, không phải số toàn cục.
4. **“Multi-master có nghĩa mọi thuộc tính/operation đều ghi ở mọi DC.”** Cần xét FSMO, schema, partition và quyền.
5. **“Global Catalog giữ mọi thuộc tính của mọi domain.”** GC chứa một phần thông tin của các domain khác theo mô hình AD.
6. **“RODC có thể ghi mọi thay đổi user như writable DC.”** RODC là mô hình chỉ đọc với quy tắc replication riêng.
7. **“Đã xóa user ở một DC thì không thể còn đối tượng ở DC cũ.”** Cần xử lý deletion metadata và lingering object.
8. **“Replication là backup.”** Thao tác xóa/cấu hình sai cũng được nhân bản.
9. **“AD replication hoàn tất thì SaaS đã disable.”** SCIM/API và local account có pipeline riêng.
10. **“IdP bị disable là mọi phiên OIDC/Kerberos tự chấm dứt.”** Session và ticket/token có vòng đời khác.
11. **“Group đã gỡ nghĩa là không còn quyền hiệu lực.”** Token cũ hoặc role cục bộ có thể còn.
12. **“Ép đồng bộ là chữa mọi lỗi IAM.”** Sai nguồn, mapping, JIT account hoặc cache cần cách khác.
13. **“Không thấy account từ một replica là account đã bị xóa.”** Có thể lag, sai partition, GC partial hoặc lỗi truy vấn.
14. **“Replication tự biết thay đổi HRIS nào đúng.”** Conflict resolution kỹ thuật không thay thế source of truth nghiệp vụ.
15. **“Service account phải Leaver cùng lúc owner.”** Workload có vòng đời riêng; owner transfer và revoke quyền người cũ là trọng tâm.

## 26. Câu hỏi tự đánh giá

1. Directory replication giải quyết nhu cầu gì và vì sao nó không đồng nghĩa LDAP search hoặc backup?
2. Phân biệt AD DC writable, Global Catalog và Read-Only Domain Controller.
3. Domain naming context, Configuration và Schema partition khác nhau thế nào?
4. Intra-site và inter-site replication có thể tạo độ trễ khác nhau vì sao?
5. Tại sao không so hai USN của hai DC để quyết định bản sao nào mới hơn?
6. Invocation ID, high-watermark và up-to-dateness vector giúp quản lý điều gì?
7. Trong multi-master, việc hai DC sửa cùng department dẫn đến rủi ro nào cho IAM?
8. Vì sao conflict resolution không bảo đảm thuộc tính cuối cùng là giá trị HRIS có thẩm quyền?
9. Tombstone/deletion metadata dùng để giải quyết vấn đề gì? Lingering object thường xuất hiện trong bối cảnh nào?
10. OpenLDAP syncrepl khác gì với việc gán một cơ chế replication chung cho mọi hệ LDAP?
11. Tại sao người dùng mới có thể đăng nhập lỗi ở DC-B khi account đã được tạo ở DC-A?
12. Khi Mover gỡ nhóm Support ở một DC, còn những lớp nào cần xác minh trước khi kết luận đã thu hồi quyền?
13. Vì sao Leaver cần SCIM/API, thu hồi phiên và kiểm tra ứng dụng, không chỉ disable user trong directory?
14. Nếu hybrid sync đọc DC chưa hội tụ, cloud IdP hoặc SaaS có thể chịu tác động gì?
15. Một người là owner của gMSA và nghỉ việc. Những bước nào giảm rủi ro mà không làm gián đoạn workload?
16. Khi thấy replica lỗi, tại sao không tự restore snapshot tùy tiện?
17. Những chỉ số nào đo được độ trễ directory và quyền truy cập tồn dư end-to-end?
18. Nếu AD replication đã ổn nhưng SaaS vẫn giữ role cũ, nên điều tra ở tầng nào?

## 27. Ghi nhớ

**Directory replication** là cơ chế nhân bản **đối tượng, thuộc tính và thay đổi** giữa các bản sao của một dịch vụ thư mục để tăng khả năng sẵn sàng và phục vụ truy vấn phân tán. Trong **AD DS**, việc hiểu **DC, domain/site/partition, topology, USN, invocation ID, metadata và deletion lifecycle** giúp chẩn đoán sự không nhất quán; trong **OpenLDAP**, cần hiểu mô hình **syncrepl** và cấu hình provider/consumer riêng. **LDAP không tự đồng nghĩa một giao thức replication duy nhất**.

Đối với IAM **Joiner–Mover–Leaver**, replication chỉ là một lớp trong luồng cập nhật. **HRIS/IGA** xác định danh tính và trạng thái nghiệp vụ, **directory** lưu bản sao dữ liệu, **IdP/SSO** phục vụ xác thực, **SCIM/API** quản lý account ứng dụng, **RBAC/ABAC** quyết định quyền và **reconciliation/audit** chứng minh quyền đã được cấp/đổi/thu hồi. Vì dữ liệu có thể nhất thời khác nhau và phiên/token có vòng đời riêng, **một thao tác thành công trên một DC không chứng minh mọi đường truy cập đã bị chặn**. Thiết kế an toàn phải giám sát hội tụ, xử lý ngoại lệ, bảo vệ quyền replication đặc quyền và xác minh quyền thực tế để giảm **tài khoản mồ côi, privilege creep và quyền truy cập tồn dư**.
