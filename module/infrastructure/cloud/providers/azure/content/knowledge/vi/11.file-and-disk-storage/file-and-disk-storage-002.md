# Xác thực và phân quyền truy cập file share

Trong module **CLOUD_PROVIDERS_AZURE**, người học tìm hiểu Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu, đồng thời học triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ở chương **Lưu trữ tệp và đĩa**, việc chọn đúng cơ chế **xác thực (authentication)** và **phân quyền (authorization)** cho **Azure Files file share** quyết định ai có thể kết nối, đọc, chỉnh sửa hoặc quản trị tệp trong hệ thống.

Một tình huống phổ biến: đội Kế toán cần sửa báo cáo trong thư mục `Finance`; đội Kiểm toán chỉ được đọc; các đội khác không được mở tài liệu. Người quản trị muốn dùng danh tính tập trung thay vì chia sẻ một mật khẩu chung. Azure Files có các lựa chọn khác nhau cho SMB, NFS và FileREST, vì thế không thể áp dụng máy móc một cơ chế cho mọi giao thức.

Sau bài học, bạn có thể:

- Phân biệt danh tính đăng nhập, quyền ở cấp file share, ACL thư mục/tệp và hạn chế mạng.
- Lựa chọn xác thực Azure Files qua **SMB với danh tính** hoặc **storage account key** theo nhu cầu và rủi ro.
- Hiểu ba nguồn danh tính SMB quan trọng: **Active Directory Domain Services (AD DS)**, **Microsoft Entra Domain Services** và **Microsoft Entra Kerberos**.
- Gán Azure RBAC ở cấp share, cấu hình quyền NTFS và kiểm tra **quyền hiệu lực**.
- Giải thích vì sao **SAS dành cho FileREST không thay thế xác thực SMB**, và vì sao **NFS** có mô hình kiểm soát khác.
- Thực hiện kiểm tra Azure CLI/PowerShell và chẩn đoán lỗi quyền hoặc kết nối cổng 445.

## 1. Azure Files và các đường truy cập file share

**Azure Files** cung cấp các file share được Azure quản lý, cho phép ứng dụng hoặc người dùng truy cập tệp qua giao thức được hỗ trợ. File share nằm trong một **storage account**. Những lựa chọn truy cập cần phân biệt:

| Giao diện | Trường hợp sử dụng | Cơ chế truy cập cần quan tâm |
|---|---|---|
| **SMB** | Windows/Linux VM, file share doanh nghiệp, thư mục dùng chung | Danh tính dựa trên Kerberos khi cấu hình, hoặc storage account key; share-level permission và NTFS ACL |
| **NFS 4.1** | Workload Linux và một số ứng dụng chuyên biệt | Ràng buộc mạng, UID/GID và quyền POSIX; không dùng trực tiếp cùng quy trình Kerberos/RBAC SMB |
| **FileREST API** | Ứng dụng hoặc tự động hóa gọi API HTTPS tới Azure Files | Shared Key, SAS và các phương án xác thực được API/version hỗ trợ; không phải phiên SMB |

Khả năng hỗ trợ giao thức, cơ chế xác thực và tính năng đi kèm còn phụ thuộc **loại storage account, SKU/tier, region và thời điểm triển khai**. Hãy xác minh những điều kiện đó trước khi thiết kế. Bài học tập trung chủ yếu vào **Azure Files qua SMB**, nơi nhu cầu phân quyền theo người dùng và nhóm thường gặp nhất.

**Không nhầm Azure Files với Azure Managed Disks**: managed disk là thiết bị lưu trữ khối cho VM; việc phân quyền tệp bên trong disk do hệ điều hành/file system thực hiện. Azure Files là dịch vụ chia sẻ tệp qua giao thức mạng, có lớp bảo mật của Storage và lớp quyền tệp/thư mục.

### 1.1. Ba lớp kiểm soát

```text
Máy người dùng / ứng dụng
        |
        | 1. Kết nối mạng (DNS, route, TCP 445, firewall, private endpoint)
        v
Azure Files endpoint
        |
        | 2. Xác thực: Kerberos danh tính SMB hoặc storage account key
        v
Quyền truy cập ở cấp file share
        |
        | 3. Share-level authorization (ví dụ Azure RBAC)
        v
Quyền NTFS trên thư mục và tệp
        |
        | 4. DACL/ACE, chủ sở hữu, nhóm, quyền hiệu lực
        v
Đọc / ghi / đổi tên / xóa (hoặc bị từ chối)
```

Đây là sơ đồ khái niệm cho luồng SMB sử dụng danh tính. Với truy cập bằng account key hoặc FileREST, mô hình đánh giá quyền có những khác biệt quan trọng được trình bày phía sau.

Một kết nối SMB thành công ở lớp mạng **không chứng minh** người dùng có quyền đọc thư mục. Ngược lại, người dùng có cả share-level role và NTFS ACL phù hợp vẫn không truy cập được nếu DNS, route hoặc cổng 445 bị chặn.

## 2. Authentication và authorization khác nhau thế nào?

**Authentication** trả lời câu hỏi *“Ai đang truy cập?”*. Khi dùng SMB identity-based authentication, máy khách chứng minh danh tính với cơ chế Kerberos được cấu hình. Khi dùng account key, phía dịch vụ nhận thông tin xác thực dựa trên khóa lưu trữ, không phải chứng minh từng danh tính người dùng theo cùng cách.

**Authorization** trả lời câu hỏi *“Danh tính đó có được làm thao tác này không?”*. Ở SMB sử dụng danh tính, cần xem cả:

1. **Share-level permissions**: vai trò/quyền ở mức file share được Azure Files áp dụng.
2. **File/directory permissions**: ACL kiểu NTFS (các quyền ở cấp thư mục/tệp) được lưu trên share.

Ví dụ: nhân viên có thể được gán vai trò `Storage File Data SMB Share Reader` tại share nhưng có NTFS `Modify` ở thư mục `Finance`. Quyền thực tế vẫn bị giới hạn bởi **lớp share-level chỉ cho đọc**. Nếu share-level cho Modify nhưng ACL chỉ cho Read, người dùng cũng không thể ghi. Hai lớp cùng tham gia và mức quyền hiệu lực không thể vượt qua giới hạn của lớp chặt hơn.

## 3. Các phương thức xác thực SMB trong Azure Files

Azure Files hỗ trợ các tích hợp danh tính dựa trên Kerberos, với giới hạn theo tính năng và SKU. Những lựa chọn phổ biến là:

| Nguồn danh tính | Tình huống phù hợp | Điểm cần chuẩn bị |
|---|---|---|
| **On-premises AD DS** | Doanh nghiệp có domain controller AD DS truyền thống, người dùng/VM gắn domain | Thiết lập tích hợp storage account với AD DS, danh tính được đồng bộ khi dùng RBAC theo Entra ID, Kerberos, DNS, kết nối DC |
| **Microsoft Entra Domain Services** | Muốn domain services do Azure quản lý cho workload dùng Kerberos/LDAP/NTLM theo khả năng dịch vụ | Managed domain, domain join và mạng/DNS đến managed domain, tài khoản/nhóm được hỗ trợ |
| **Microsoft Entra Kerberos** | Thiết kế đăng nhập SMB bằng Entra Kerberos trong điều kiện được hỗ trợ, thường liên quan danh tính hybrid | Thiết bị và người dùng đáp ứng điều kiện, đồng bộ/ủy thác danh tính theo tính năng, cấu hình Entra Kerberos và Kerberos tickets |

**Lưu ý:** Không phải tất cả loại người dùng, thiết bị, cấu hình domain, SKU hoặc tình huống cross-tenant đều được hỗ trợ như nhau. Chẳng hạn khả năng dùng **cloud-only identities** với Entra Kerberos có thể phụ thuộc trạng thái tính năng/điều kiện triển khai; hãy xác minh trước khi cam kết với một nhóm người dùng chỉ tồn tại trên cloud. Microsoft Entra ID thông thường **không tự động cung cấp phiên SMB Kerberos** chỉ vì người dùng đã đăng nhập Azure Portal.

Trong một storage account, không nên giả định có thể bật đồng thời tùy ý nhiều **directory service identity sources** cho SMB. Hãy chọn một nguồn danh tính theo điều kiện hỗ trợ rồi lập kế hoạch chuyển đổi khi cần thay đổi.

### 3.1. AD DS: danh tính và nhóm của doanh nghiệp

Với **Active Directory Domain Services**, người dùng đăng nhập bằng tài khoản domain, máy khách có thể lấy Kerberos ticket cho dịch vụ SMB. Storage account được cấu hình để tham gia mô hình xác thực tương ứng. Các nhóm trong AD giúp cấp quyền theo vai trò công việc thay vì gán từng nhân viên.

Ví dụ:

- `CONTOSO\FinanceEditors`: có thể thay đổi nội dung thư mục kế toán.
- `CONTOSO\FinanceAuditors`: chỉ đọc.
- `CONTOSO\IT-FileAdmins`: được ủy quyền quản trị ACL theo quy trình.

Để dùng Azure RBAC ở cấp share cho danh tính tương ứng, cần bảo đảm cách ánh xạ/đồng bộ các tài khoản và nhóm với Microsoft Entra ID theo mô hình được hỗ trợ. Với một số danh tính không đồng bộ được, tổ chức có thể cần dùng **default share-level permission** theo tính năng Azure Files hỗ trợ, nhưng phải hiểu ảnh hưởng rộng của quyền mặc định.

### 3.2. Microsoft Entra Domain Services

**Microsoft Entra Domain Services** cung cấp managed domain có các khả năng domain truyền thống cần thiết cho nhiều ứng dụng legacy. VM và người dùng đáp ứng điều kiện có thể truy cập Azure Files qua SMB với mô hình xác thực dựa trên domain này.

Đây **không** phải cách gọi khác của Entra ID: Entra Domain Services là dịch vụ domain riêng cần cấu hình, mạng, DNS và quản trị phù hợp. Tài khoản người dùng có thể cần thực hiện bước đáp ứng yêu cầu credential đồng bộ trước khi xác thực hoạt động, tùy lịch sử và cấu hình domain.

### 3.3. Microsoft Entra Kerberos

Entra Kerberos giúp một số môi trường Windows sử dụng Kerberos để truy cập Azure Files bằng danh tính Microsoft Entra ID trong các điều kiện được hỗ trợ. Đây là một lựa chọn hấp dẫn khi tổ chức muốn giảm phụ thuộc vào domain controller truyền thống trong một phần luồng truy cập.

Tuy nhiên, không được coi mọi máy tính đã **Entra joined** là mặc nhiên mount được mọi share. Các yếu tố cần kiểm tra gồm:

- Đối tượng người dùng thuộc nhóm danh tính được tính năng hỗ trợ.
- Trạng thái join của thiết bị, OS version và cấu hình sign-in.
- Cấu hình Kerberos cho storage account và tenant.
- Tên miền/realm, SPN, ticket và các điều kiện mạng/DNS.
- Share-level permissions và NTFS ACL đã được thiết lập cho đúng principal/nhóm chưa.

**Điểm chung của cả ba cách xác thực bằng danh tính:** có danh tính hợp lệ mới chỉ giải quyết một phần. Share-level permission và NTFS ACL vẫn quyết định quyền thao tác với tệp.

## 4. Xác thực bằng storage account key: đơn giản nhưng đặc quyền rộng

Azure Files qua SMB cũng có thể được mount bằng **storage account key** nếu loại account và chính sách cho phép. Một ví dụ cấu hình cũ có thể đặt storage account name làm thông tin user và account key làm password khi mount share.

Account key là một bí mật có **đặc quyền rất rộng** đối với storage account. Khi SMB mount bằng key, cách kiểm soát theo user/group và NTFS ACL không tương đương với phiên Kerberos của một nhân viên: truy cập bằng key mang tính chất quản trị/siêu người dùng và có thể **vượt qua các giới hạn ACL NTFS của người dùng thông thường**.

Vì vậy:

- Không gửi account key cho toàn bộ nhân viên để họ tự mount share.
- Không đặt key trong mã nguồn, file `.ps1`, container image, Git repository, chat hoặc ticket hỗ trợ.
- Không xem một mount bằng account key là bằng chứng rằng các NTFS ACL đã đúng.
- Khi buộc phải dùng key với workload cũ, lưu trong kho bí mật có kiểm soát; giới hạn danh tính có thể đọc hoặc regenerate key.
- Có kế hoạch chuyển sang **identity-based SMB authentication** khi nhu cầu sử dụng và môi trường hỗ trợ.

**Key rotation:** storage account thường có hai access keys để hỗ trợ xoay vòng. Regenerate một khóa làm mất hiệu lực các client đang sử dụng khóa đó và những chữ ký/SAS phụ thuộc vào nó. Việc xoay key cần kế hoạch cập nhật client, giám sát và rollback; không phải thao tác vô hại khi hàng trăm máy đang mount share.

## 5. Share-level RBAC: lớp quyền thứ nhất

Khi dùng **identity-based SMB authentication**, Azure Files sử dụng quyền ở cấp share để quyết định danh tính có thể truy cập share ở mức nào. Azure RBAC cung cấp các vai trò tích hợp chuyên cho **SMB file share**:

| Vai trò | Mục đích điển hình | Lưu ý |
|---|---|---|
| `Storage File Data SMB Share Reader` | Quyền đọc ở cấp share | Không biến NTFS ACL bị từ chối thành cho phép |
| `Storage File Data SMB Share Contributor` | Quyền đọc/ghi ở cấp share | Quyền NTFS vẫn có thể hạn chế thư mục/tệp |
| `Storage File Data SMB Share Elevated Contributor` | Cho phép các thao tác nâng cao được hỗ trợ, thường dùng khi quản trị phân quyền tệp | Chỉ cấp cho nhóm quản trị được ủy quyền; không cấp đại trà |

Tên các vai trò tích hợp phải được dùng chính xác khi cấu hình; không nhầm với `Storage File Data Contributor` hay những vai trò dành riêng cho Blob Storage, hoặc với role ARM `Contributor`.

Một role assignment có ba phần chính:

```text
Principal:  nhóm Entra ID / người dùng được hỗ trợ
Role:       Storage File Data SMB Share Contributor
Scope:      .../fileServices/default/shares/team-docs
```

Azure RBAC có thể được gán tại **file share**, storage account hoặc scope cha phù hợp. Để tuân thủ least privilege, nên dùng **scope nhỏ nhất** đáp ứng nhu cầu. Vai trò ở cấp storage account có thể tác động tới nhiều shares trong account và vì vậy cần cân nhắc kỹ.

### 5.1. Share-level permission mặc định

Trong những trường hợp được Azure Files hỗ trợ, có thể đặt **default share-level permission** cho các danh tính đã xác thực bằng nguồn Kerberos đã cấu hình. Đây là cách xử lý một số trường hợp không thể gán RBAC cho từng principal, ví dụ các danh tính AD DS không đồng bộ vào Entra ID.

Nhưng quyền mặc định là lựa chọn **rộng hơn** một role assignment dành cho một nhóm cụ thể. Nếu cấu hình mức Contributor hoặc Elevated Contributor làm mặc định, mọi danh tính đã xác thực thuộc phạm vi áp dụng có thể được cấp lớp share-level tương ứng, sau đó mới bị giới hạn bởi ACL. Điều này làm tăng rủi ro khi NTFS ACL đặt sai.

Ưu tiên gán role cho **nhóm theo chức năng** được hỗ trợ; chỉ dùng default permission khi có lý do rõ ràng và đã đánh giá tác động. Không coi default permission là cách bỏ qua việc quản lý ACL.

### 5.2. Không nhầm management plane với SMB data plane

Vai trò Azure `Reader` ở resource group cho phép xem một số thông tin quản lý, không đồng nghĩa được đọc file qua SMB. `Contributor` tại subscription cho phép nhiều thao tác quản trị resource nhưng **không tự động là một phiên Kerberos có quyền NTFS đọc mọi file**.

Ngược lại, quyền đọc một share qua SMB không đồng nghĩa có quyền thay storage account settings, lấy account key hoặc tạo role assignment. Cần phân tách người **quản lý tài nguyên Azure**, người **quản lý danh tính/quyền** và người **sử dụng nội dung tệp**.

## 6. NTFS ACL: lớp quyền thứ hai

Azure Files SMB hỗ trợ quyền trên thư mục/tệp theo mô hình **Windows-style NTFS ACL**. ACL (Access Control List) gồm các **ACE** (Access Control Entries), diễn tả những principal hoặc nhóm được phép/bị từ chối các thao tác cụ thể.

Những quyền thường gặp:

| Quyền NTFS | Ý nghĩa điển hình |
|---|---|
| `Read` / `Read & Execute` | Xem nội dung, thuộc tính và thực thi theo loại file |
| `Write` | Tạo hoặc ghi dữ liệu theo phạm vi quyền |
| `Modify` | Đọc, ghi, sửa và thường bao gồm xóa trong phạm vi phù hợp |
| `Full Control` | Các quyền cao nhất của ACL, kể cả quản lý quyền theo mô hình hỗ trợ |
| `Deny` | Từ chối quyền đã khai báo đối với principal hoặc nhóm |

Quyền được đánh giá theo identity và group membership, ACE cho phép/từ chối, inheritance, owner và quy tắc Windows access check. Các ACE `Deny` có thể dẫn đến kết quả ngoài dự kiến khi một người thuộc nhiều nhóm. Vì thế, quản trị theo **Allow tối thiểu trên nhóm phù hợp** và tránh Deny tường minh tràn lan nếu có thể.

### 6.1. Kế thừa ACL

Một thư mục có thể chứa ACE được kế thừa bởi file và thư mục con. Ví dụ:

```text
Share: team-docs
  |
  +-- Finance
  |     +-- Reports
  |           +-- Q4.xlsx
  |
  +-- Engineering
        +-- Designs
```

Đội Kế toán cần `Modify` trong `Finance` nhưng không được truy cập `Engineering`. Có thể gán ACL trên thư mục gốc của từng bộ phận, cho phép kế thừa xuống đối tượng con. Khi tạo ACL, cần kiểm tra **đúng SID/nhóm** và quy tắc inheritance, đồng thời loại bỏ quyền quá rộng nếu chính sách yêu cầu.

Một thành viên có `Contributor` ở cấp share nhưng không có ACL cho `Finance\Reports` vẫn sẽ bị từ chối đọc hoặc ghi những file đó. Ngược lại, nhóm có `Reader` ở cấp share không ghi được dù ACL ở `Finance` có `Modify`.

### 6.2. Ví dụ ma trận quyền

| Nhóm | Share-level RBAC | ACL `Finance` | ACL `Engineering` | Kết quả mong muốn |
|---|---|---|---|---|
| `FinanceEditors` | SMB Share Contributor | Modify | Không có quyền | Chỉnh sửa trong Finance |
| `FinanceAuditors` | SMB Share Reader | Read | Không có quyền | Chỉ đọc Finance |
| `EngineeringEditors` | SMB Share Contributor | Không có quyền | Modify | Chỉnh sửa Engineering |
| `FileShareAclAdmins` | Quyền quản trị share/ACL được phê duyệt | Quyền quản lý ACL phù hợp | Quyền quản lý ACL phù hợp | Duy trì phân quyền theo quy trình |

Đây là mô hình mục tiêu, không phải quy tắc tự có sẵn của Azure Files. Bạn phải tạo nhóm, gán role và cấu hình ACL thực tế. Ngoài ra cần xem xét quyền trên **thư mục gốc của share** và khả năng traverse đến thư mục con; nếu không thiết kế đúng, một người có quyền trên `Finance` vẫn có thể gặp lỗi khi đi từ root tới thư mục đó.

## 7. Quyền hiệu lực: phải vượt qua cả hai lớp

Với SMB identity-based access:

```text
Quyền hiệu lực = giới hạn của share-level permission
                GIAO VỚI quyền NTFS ACL của file/thư mục
```

Đây là cách diễn đạt khái niệm: hệ thống kiểm tra các quyền được cấp và các điều kiện cho phép/từ chối theo quy tắc kỹ thuật của từng lớp, không phải phép giao tập hợp đơn giản cho mọi loại quyền Windows nâng cao.

Ví dụ:

| Share-level | NTFS ACL | Thao tác Read | Thao tác Write |
|---|---|---|---|
| Reader | Read | Có, nếu các điều kiện khác cho phép | Không |
| Contributor | Read | Có | Không |
| Contributor | Modify | Có | Có |
| Reader | Modify | Có | Không |
| Không có quyền share-level phù hợp | Full Control | Không | Không |

Đối với các hành động **thay đổi ACL, quyền sở hữu, xóa** hoặc truy cập dữ liệu qua cơ chế khác, phải xét quyền cụ thể và cơ chế hỗ trợ. Đừng suy luận rằng `Full Control` trên một thư mục luôn đủ để thay mọi thiết lập Azure RBAC.

## 8. Kiến trúc triển khai mẫu

Giả sử doanh nghiệp có đội Finance và Engineering, sử dụng SMB từ Windows VM trong VNet. Share nằm trong Azure Files, được kết nối qua **private endpoint** theo chính sách mạng.

```text
Người dùng Finance / Engineering
           |
           | Đăng nhập trên Windows VM thuộc môi trường identity được hỗ trợ
           v
Windows SMB client (Kerberos ticket)
           |
           | DNS: <account>.file.core.windows.net
           | -> địa chỉ private endpoint theo Private DNS cấu hình
           | TCP 445 trong mạng riêng
           v
Azure Files: storage account stfilesprod001
           |
           +-- Share: team-docs
                 |
                 +-- Finance (ACL nhóm Finance)
                 +-- Engineering (ACL nhóm Engineering)
```

Ở lớp **mạng**, kiểm soát VNet, DNS, firewall, NSG, private endpoint và route. Ở lớp **danh tính**, dùng Kerberos theo nguồn đã chọn. Ở lớp **phân quyền**, dùng share-level RBAC và NTFS ACL. Ở lớp **bảo vệ dữ liệu**, bật các tính năng backup, snapshot/soft delete, logging và chính sách lưu trữ phù hợp.

Private endpoint **không thay thế** Kerberos hoặc ACL. Nó thay đổi đường kết nối mạng tới Storage nhưng không tự xác minh nhân viên có được mở `Finance\Reports` hay không.

## 9. Quy trình cấu hình identity-based SMB access

Việc tích hợp Azure Files với một nguồn danh tính là thao tác hạ tầng có thể ảnh hưởng người dùng đang mount share. Hãy làm trong môi trường thử nghiệm trước và có kế hoạch chuyển đổi nếu share đang dùng account key.

### Bước 1: Chọn và chuẩn bị nguồn danh tính

Với từng môi trường, xác nhận:

1. Azure Files account/SKU và giao thức SMB hỗ trợ tích hợp danh tính đã chọn.
2. Người dùng, nhóm, máy khách và phương thức join đáp ứng yêu cầu.
3. Domain/tenant, DNS, Kerberos tickets, thời gian đồng hồ và khả năng kết nối tới thành phần danh tính.
4. Nhóm người dùng cần cấp quyền đã được tạo và đồng bộ/ánh xạ theo cơ chế hỗ trợ.
5. Network rules và đường SMB TCP 445 đã được thiết kế.

Trong Azure Portal, chọn storage account → cấu hình **File shares / Identity-based access** hoặc khu vực cấu hình tương ứng theo giao diện hiện hành. Thiết lập AD DS, Microsoft Entra Domain Services hoặc Microsoft Entra Kerberos theo tính năng đã chọn. Nếu dùng AD DS, việc nhập thông tin domain, SID, SPN và tài khoản liên quan cần thực hiện theo hướng dẫn tích hợp Azure Files cho domain của tổ chức; không tự suy các giá trị danh tính.

Sau khi cấu hình, xác nhận trạng thái identity-based authentication trên storage account và thử xác thực bằng **một tài khoản test đúng loại**. Đừng vội gán quyền rộng cho mọi người dùng khi chưa kiểm chứng Kerberos hoạt động.

### Bước 2: Cấp share-level permission bằng nhóm

Tạo Azure RBAC role assignment cho nhóm thích hợp tại đúng file share. Ví dụ nhóm `FinanceEditors` được gán `Storage File Data SMB Share Contributor` ở share `team-docs`, trong khi `FinanceAuditors` được gán vai trò Reader.

Đây là quyền ở mức toàn share. Việc giới hạn chỉ thư mục `Finance` và không cho đụng tới `Engineering` sẽ được thực hiện ở lớp NTFS ACL trong bước sau.

### Bước 3: Mount share với danh tính

Trên Windows client được hỗ trợ, người dùng đã đăng nhập bằng danh tính tương ứng, có Kerberos ticket và có mạng tới Azure Files, mount share bằng đường UNC chuẩn:

```text
\\<storage-account>.file.core.windows.net\<share-name>
```

Không đặt account key làm password nếu mục tiêu là thử nghiệm quyền Kerberos của từng nhân viên. Một phiên SMB đã tồn tại đến cùng server bằng credential khác có thể khiến quá trình test bị sai lệch; cần kiểm tra credential cache và session đang hoạt động.

### Bước 4: Gán ACL trên thư mục và tệp

Người quản trị được ủy quyền kết nối bằng danh tính có quyền phù hợp, tạo hoặc lựa chọn thư mục và cấu hình ACL theo nhóm. Bắt đầu ở thư mục test, kiểm tra inheritance, rồi mới nhân rộng tới dữ liệu thật.

### Bước 5: Kiểm thử ma trận cho phép/từ chối

Đăng nhập **thật** bằng từng loại người dùng test (Editor, Auditor, người không có quyền), thực hiện đọc/tạo/sửa/xóa tệp trong phạm vi thử nghiệm và xác nhận đúng ma trận. Không chỉ dựa vào việc nhìn thấy drive letter trong File Explorer.

### Bước 6: Ghi nhận và vận hành

Lưu cấu hình nguồn danh tính, RBAC scope, nhóm AD/Entra, ACL quan trọng, chủ sở hữu share, quy trình thêm/xóa thành viên nhóm, backup và runbook xử lý lỗi. Khi nhân viên đổi bộ phận hoặc rời công ty, cập nhật membership và xác minh quyền không còn cần thiết đã được loại bỏ.

## 10. Thực hành kiểm tra và cấp RBAC bằng Azure CLI

Ví dụ sau giả định **Azure Files SMB share đã được tạo**, storage account và hệ thống danh tính đã cấu hình, người thực hiện có quyền xem tài nguyên và (ở bước cấp quyền) có quyền tạo role assignment. Các lệnh dùng Azure CLI trong Bash/Azure Cloud Shell. Không cần đọc account key để gán share-level RBAC.

Đặt biến cho môi trường **minh họa**:

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-files-dev"
ACCOUNT="stfilesdev001"
SHARE="team-docs"
```

### 10.1. Kiểm tra storage account và cấu hình danh tính

```bash
az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,kind:kind,identityBasedAuth:azureFilesIdentityBasedAuthentication}" \
  --output json
```

Trường `identityBasedAuth` giúp xem thông tin cấu hình SMB identity-based authentication nếu account/API trả về trường tương ứng. Một giá trị trống, không xuất hiện hoặc chưa cấu hình cần được xác minh thêm trong Portal và theo khả năng dịch vụ; không diễn giải rằng Entra ID của tổ chức tự động được dùng cho SMB.

### 10.2. Xem File Share và lấy Azure Resource ID

```bash
az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$ACCOUNT" \
  --name "$SHARE" \
  --output json

SHARE_RESOURCE_ID=$(az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$ACCOUNT" \
  --name "$SHARE" \
  --query id --output tsv)
```

`share-rm` là lệnh quản lý tài nguyên share qua control plane; nó khác với thao tác đọc nội dung tệp qua SMB hoặc FileREST data plane. Định danh share thường có dạng:

```text
/subscriptions/<subscription-id>/resourceGroups/<resource-group>
/providers/Microsoft.Storage/storageAccounts/<account>
/fileServices/default/shares/<share>
```

Sử dụng **Resource ID thực tế** do CLI trả về thay vì tự nối string cho một resource đang tồn tại.

### 10.3. Cấp share-level role cho một nhóm Entra ID

Người quản trị RBAC có thể cấp role như sau:

```bash
FINANCE_GROUP_OBJECT_ID="<entra-group-object-id>"

az role assignment create \
  --assignee-object-id "$FINANCE_GROUP_OBJECT_ID" \
  --assignee-principal-type Group \
  --role "Storage File Data SMB Share Contributor" \
  --scope "$SHARE_RESOURCE_ID"
```

Đối với một nhóm chỉ đọc:

```bash
AUDIT_GROUP_OBJECT_ID="<entra-auditors-group-object-id>"

az role assignment create \
  --assignee-object-id "$AUDIT_GROUP_OBJECT_ID" \
  --assignee-principal-type Group \
  --role "Storage File Data SMB Share Reader" \
  --scope "$SHARE_RESOURCE_ID"
```

Chỉ dùng **Object ID của đúng nhóm Entra ID** gắn với các danh tính được phương thức SMB hỗ trợ. Khi quyền được gán cho nhóm, cần xác nhận ánh xạ group/SID và membership trong môi trường AD/Kerberos thực tế. Không gán role cho một nhóm có tên gần giống chỉ vì dễ tìm trong Portal.

Xem lại role assignments:

```bash
az role assignment list \
  --scope "$SHARE_RESOURCE_ID" \
  --include-inherited \
  --output table
```

`--include-inherited` giúp xem những vai trò có hiệu lực do được gán tại scope cha; việc lọc/hiển thị role tùy phiên bản CLI. Role assignment có thể cần thời gian để lan truyền. Người dùng cũng có thể cần làm mới Kerberos ticket hoặc đăng nhập lại để group membership mới được thể hiện.

**Tính an toàn:** Khi môi trường thật đang có dữ liệu nhạy cảm, không trao `Storage File Data SMB Share Elevated Contributor` cho nhóm Editors thông thường chỉ để họ tạo/sửa file. Phân biệt rõ đội quản trị ACL với người sửa nội dung.

## 11. Thực hành trên Windows: kết nối và kiểm tra NTFS ACL

Ví dụ dưới đây dùng Windows PowerShell trong VM/thiết bị có danh tính và khả năng truy cập SMB phù hợp. Thay tên account, share và nhóm domain bằng giá trị thật. **Không dùng account key trong các bước xác minh quyền người dùng**, vì nó làm sai mục tiêu thử Kerberos/ACL.

### 11.1. Kiểm tra DNS và TCP 445

```powershell
$server = "stfilesdev001.file.core.windows.net"
Resolve-DnsName $server
Test-NetConnection -ComputerName $server -Port 445
```

Nếu dùng private endpoint, kết quả DNS phải phù hợp với đường dẫn private network và resolver đã cấu hình. Các thành phần như Azure Private DNS, route, NSG hoặc firewall doanh nghiệp có thể làm kết nối thất bại. Không suy ra “thiếu quyền NTFS” khi bước TCP 445 còn chưa thành công.

### 11.2. Kiểm tra danh tính và Kerberos

```powershell
whoami
whoami /groups
klist
```

`whoami` và `whoami /groups` giúp xem phiên người dùng và các nhóm được nhận diện trong Windows access token. `klist` giúp xem Kerberos tickets hiện có. Tùy phương thức danh tính, có thể cần kiểm tra ticket/SPN phù hợp với dịch vụ SMB và làm mới phiên đăng nhập sau khi thay group membership.

Đừng sao chép toàn bộ danh sách group SID, ticket hoặc thông tin domain nhạy cảm vào public support ticket. Hãy ghi nhận phần chẩn đoán cần thiết với quyền xem phù hợp.

### 11.3. Mount file share bằng danh tính đang đăng nhập

```powershell
net use Z: \\stfilesdev001.file.core.windows.net\team-docs /persistent:no
Get-SmbConnection
```

Lệnh trên dự kiến sử dụng phiên người dùng Windows/Kerberos đã được chuẩn bị. Nếu yêu cầu credential hoặc bị từ chối, hãy kiểm tra nguồn danh tính, trạng thái join, Kerberos tickets, các SMB sessions tới cùng server và chính sách mạng. **Không “sửa lỗi” bằng cách nhập storage account key**, vì khi đó quá trình thử quyền user/group không còn giá trị.

### 11.4. Xem ACL hiện tại

```powershell
icacls "Z:\"
icacls "Z:\Finance"
```

Kết quả mô tả các ACE hiện có và quyền kế thừa. Nếu thư mục `Finance` chưa được tạo, tạo nó bằng tài khoản được ủy quyền và có quyền cần thiết theo quy trình quản trị share; đừng chạy thay đổi trên thư mục production chưa sao lưu metadata ACL.

### 11.5. Gán ACL cho nhóm trong môi trường test

Giả sử nhóm `CONTOSO\FinanceEditors` cần Modify trên thư mục `Finance` và con cháu, người quản trị ACL có thể dùng:

```powershell
# Chỉ chạy khi đã được cấp quyền quản trị ACL và review tên nhóm.
icacls "Z:\Finance" /grant "CONTOSO\FinanceEditors:(OI)(CI)M"

# Cho nhóm kiểm toán chỉ đọc, cũng áp dụng cho file/thư mục con.
icacls "Z:\Finance" /grant "CONTOSO\FinanceAuditors:(OI)(CI)RX"

# Đọc lại ACL:
icacls "Z:\Finance"
```

Trong `icacls`, `(OI)` là object inheritance cho file, `(CI)` là container inheritance cho thư mục, `M` là Modify, `RX` là Read & Execute. Cần thiết kế inheritance và ACE hiện có; `/grant` không có nghĩa tự động xóa mọi quyền cũ quá rộng. Nếu yêu cầu loại bỏ quyền cho nhóm khác, cần review và chỉnh ACL theo quy trình an toàn trước.

Tài khoản chạy `icacls` phải có quyền **thay đổi ACL trên thư mục** và quyền share-level phù hợp. Nếu `icacls` báo `Access is denied`, kiểm tra cả hai lớp quyền thay vì dùng account key hoặc cấp Full Control cho mọi người.

### 11.6. Kiểm thử bằng ba tài khoản

| Tài khoản thử | Đọc `Finance\Report.txt` | Tạo/sửa file trong `Finance` | Đọc `Engineering` |
|---|---|---|---|
| Thành viên `FinanceEditors` | Thành công | Thành công | Bị từ chối theo thiết kế |
| Thành viên `FinanceAuditors` | Thành công | Bị từ chối | Bị từ chối |
| Người dùng không thuộc hai nhóm | Bị từ chối | Bị từ chối | Tùy quyền được cấp riêng, không mặc định cho phép |

Phải kiểm thử bằng **phiên xác thực thật** của từng người dùng. Nếu bạn thử mọi kết nối bằng một account key, cả ba trường hợp có thể cho kết quả giống nhau và không phản ánh phân quyền mục tiêu.

## 12. SAS và FileREST: không phải cơ chế đăng nhập SMB

**Shared Access Signature (SAS)** là một cách ủy quyền có thời hạn cho request tới những API Storage hỗ trợ. Với Azure Files, SAS có thể được dùng cho **FileREST** theo phạm vi/quyền và loại tài khoản được hỗ trợ; các cách gọi REST được ký bằng Shared Key hoặc những phương thức Microsoft Entra ID/OAuth được từng API version hỗ trợ cần được phân biệt theo tài liệu tính năng tương ứng.

**SAS URL không thay thế username/password hoặc Kerberos của lệnh mount SMB**. Bạn không thể mount một share bằng cách dán nguyên query string SAS vào đường UNC:

```text
# Không phải cú pháp mount SMB hợp lệ:
\\account.file.core.windows.net\team-docs?sv=...&sig=...
```

Khi ứng dụng thao tác FileREST, quyền của SAS/REST request áp dụng theo mô hình API đó; không giả định cơ chế này có cùng kết quả với share-level SMB RBAC và NTFS ACL của một phiên Kerberos. Đặc biệt, các request dùng account key có thể mang quyền cao và phải được quản lý riêng.

**User delegation SAS cho Azure Blob Storage** không phải là một token có thể mặc nhiên dùng cho Azure Files. Không nhầm `Blob SAS` với `File SAS` và không dùng tài liệu hướng dẫn Blob API để suy diễn khả năng ủy quyền của FileREST.

### 12.1. Ứng dụng backend nên chọn phương thức nào?

| Workload | Cách tiếp cận |
|---|---|
| Người dùng Windows cần `Z:\Finance` | SMB + Kerberos + share-level permission + NTFS ACL |
| Ứng dụng cần gọi API quản lý Storage | Azure Resource Manager/RBAC management plane theo nhu cầu |
| Ứng dụng gọi FileREST | Cơ chế xác thực/ủy quyền mà FileREST API và version đang dùng hỗ trợ; ưu tiên danh tính khi có khả năng phù hợp |
| Hệ thống legacy mount SMB bằng account key | Kiểm soát bí mật/đặc quyền, lập kế hoạch chuyển dần sang danh tính |
| Client chỉ cần tệp tải tạm thời | Đánh giá kiến trúc API/backend, thời hạn token và cơ chế chia sẻ được FileREST hỗ trợ; không đưa account key cho client |

Không phải mọi SDK và giao thức xử lý Entra ID theo cùng một cách. **Managed identity của một Azure VM không tự biến thành Kerberos ticket của người dùng đang mount SMB**. Với SMB dùng user identity, cần danh tính và môi trường Kerberos phù hợp; với request HTTP/REST, có thể có luồng xác thực ứng dụng riêng.

## 13. NFS file share: mô hình bảo mật khác SMB

Đối với **Azure Files NFS 4.1**, không nên áp dụng share-level SMB roles hay NTFS ACL như thể đó là cùng giao thức. Các yếu tố kiểm soát thường gồm:

- Kết nối mạng riêng, network restrictions, route và private endpoint theo loại triển khai được hỗ trợ.
- UID/GID và quyền **POSIX mode bits** trên các thư mục/tệp.
- **Root squash** khi tính năng được hỗ trợ và cấu hình phù hợp, để hạn chế quyền root đến từ client.
- Quản trị máy NFS client, user/group mapping và các dịch vụ network liên quan.

NFS mount theo mô hình phổ biến ở Azure Files không sử dụng trực tiếp Kerberos user identity/RBAC SMB để xác thực từng người dùng như SMB. Bảo vệ mạng và bảo vệ host có vai trò đặc biệt quan trọng.

Ví dụ Linux:

```bash
# Kiểm tra quyền POSIX của thư mục sau khi share NFS được mount.
id
ls -ld /mnt/azfiles/team-docs
ls -l /mnt/azfiles/team-docs
```

Thay đổi `chmod` hoặc `chown` trên share NFS phải dựa theo UID/GID và quyền root squash thực tế. Đừng áp dụng trực tiếp ví dụ `icacls` của SMB lên một NFS mount.

## 14. Cách chẩn đoán theo từng lớp

Khi người dùng báo `Access is denied`, `System error 53`, không mount được share hoặc nhìn thấy thư mục nhưng không mở được file, hãy điều tra **theo thứ tự**, tránh cấp quyền rộng để thử ngẫu nhiên.

| Triệu chứng | Khả năng xảy ra | Điều cần kiểm tra |
|---|---|---|
| Không phân giải được hostname Storage | DNS sai, private DNS zone/link chưa đúng | `Resolve-DnsName`, endpoint và resolver |
| TCP 445 không kết nối | Firewall/ISP, NSG, UDR, private endpoint hoặc tuyến mạng | `Test-NetConnection -Port 445`, effective routes |
| SMB liên tục hỏi credential | Phiên Kerberos không hợp lệ, sai domain/tenant, máy chưa đáp ứng điều kiện | Join status, `klist`, SPN, account source |
| Một người mount được, người khác không | Share-level RBAC/default permission, group membership hoặc Kerberos ticket khác nhau | Role assignments, SID/nhóm, trạng thái đồng bộ |
| Mount được nhưng không đọc được `Finance` | NTFS ACL/inheritance hoặc traverse trên thư mục cha | `icacls` root, `Finance` và file đích |
| Đọc được nhưng không tạo hoặc sửa file | Reader share-level role, ACL chỉ đọc hoặc quyền cần cho thao tác tạo/xóa | RBAC share-level + NTFS Modify |
| Người dùng không có quyền vẫn đọc được | Account key session, nhóm/ACL quá rộng hoặc quyền mặc định share-level | `Get-SmbConnection`, ACL và role/default permission |
| Sau đổi nhóm vẫn truy cập sai | Membership/ticket hoặc RBAC chưa cập nhật trên phiên hiện tại | Đăng nhập lại, làm mới ticket theo quy trình, thời gian lan truyền |
| Một ứng dụng mất kết nối sau key rotation | Đang dùng account key cũ | Kiểm kê client legacy và quy trình cập nhật secrets |
| FileREST thành công nhưng SMB từ chối | Hai cơ chế xác thực/ủy quyền khác nhau | Không suy ra SMB permissions từ REST call |

### 14.1. Quy trình điều tra tám bước

1. **Xác định giao thức:** SMB, NFS hay FileREST; không dùng chung một bộ giả định.
2. **Kiểm tra đích:** subscription, storage account, share và hostname; tránh nhầm môi trường dev/prod.
3. **Kiểm tra mạng:** DNS, cổng, firewall/NSG, private endpoint, routing; thu thập mã lỗi cụ thể.
4. **Xác định danh tính thực:** Kerberos user/group nào hoặc account key; xác minh có phiên SMB khác đang dùng credential cũ không.
5. **Kiểm tra share-level authorization:** Azure RBAC của principal/nhóm, quyền kế thừa và default share-level permission nếu cấu hình.
6. **Kiểm tra NTFS ACL:** ACE ở thư mục cha/đích, inheritance, Deny và các quyền cần cho từng thao tác.
7. **Đối chiếu thời điểm thay đổi:** quyền RBAC, group membership, Kerberos tickets, key rotation hoặc cấu hình identity vừa đổi.
8. **Sửa tối thiểu và kiểm thử lại:** dùng tài khoản Editor, Auditor và người không có quyền; ghi nhận kết quả thành công/thất bại.

Đối với ứng dụng production, lưu log và request correlation có kiểm soát. Azure Monitor, Storage metrics, file service logs và hệ thống event logs trên client/domain controller có thể giúp phân tích, nhưng loại log và thông tin có sẵn phụ thuộc cấu hình và giao thức.

## 15. Các sai lầm phổ biến

**Chỉ cấp Azure RBAC rồi bỏ qua NTFS ACL.** Share-level Contributor không cho phép ghi vào thư mục mà ACL chỉ Read hoặc Deny.

**Chỉ cấu hình NTFS Full Control rồi bỏ qua quyền share-level.** Dù ACL ở file cho Full Control, một phiên identity-based SMB vẫn cần quyền ở lớp share phù hợp.

**Test quyền bằng storage account key.** Kết quả không chứng minh quyền Kerberos của nhân viên; key có đặc quyền rộng và có thể vượt qua ACL dành cho người dùng.

**Lẫn Azure RBAC resource management với dữ liệu SMB.** `Reader`/`Contributor` cấp resource group không tương đương `Storage File Data SMB Share Reader`/`Contributor`.

**Nghĩ rằng “Entra joined” đồng nghĩa mount SMB thành công.** Phải có identity source phù hợp, hỗ trợ người dùng/OS, Kerberos, RBAC, ACL và đường mạng.

**Gán Elevated Contributor cho toàn bộ nhân viên.** Quyền quản lý ACL cần tách khỏi quyền sửa nội dung tệp thông thường.

**Mở default share-level Contributor cho tất cả mà không kiểm tra ACL.** Quyền mặc định mở rộng bề mặt ảnh hưởng nếu một thư mục chứa ACE quá thoáng.

**Cho rằng SAS hoặc user delegation SAS của Blob dùng làm password SMB.** SAS là cơ chế request API được hỗ trợ, không phải Kerberos session hoặc SMB password.

**Chỉ kiểm tra port 445 rồi kết luận có quyền truy cập.** Port mở không đồng nghĩa Kerberos, RBAC và ACL đều đúng.

**Quên tính kế thừa và quyền từ nhóm khác.** Người dùng có thể thuộc nhiều nhóm; ACE và share-level role nhận được từ các phạm vi khác có thể thay đổi kết quả.

## 16. Checklist vận hành và bảo mật

- [ ] Đã xác định Azure Files share sử dụng SMB, NFS hay FileREST và các điều kiện SKU hỗ trợ.
- [ ] Đã chọn một nguồn SMB identity-based authentication phù hợp với thiết bị và người dùng.
- [ ] Đã kiểm tra DNS, route, private endpoint, network restrictions và TCP 445 (với SMB).
- [ ] Đã lập nhóm theo chức năng, tránh gán quyền thủ công tràn lan cho từng người.
- [ ] Đã gán role `Storage File Data SMB Share Reader/Contributor` ở scope hẹp phù hợp.
- [ ] Đã xem xét default share-level permission; tránh dùng mức quyền quá rộng.
- [ ] Đã gán NTFS ACL đúng theo thư mục/file và kiểm tra inheritance, Deny, traverse.
- [ ] Người quản trị ACL được cấp quyền riêng; Editors/Auditors không có quyền quản trị không cần thiết.
- [ ] Đã thử với danh tính Kerberos thật, không chỉ mount bằng account key.
- [ ] Đã kiểm tra user/group mapping, Kerberos tickets và độ trễ đồng bộ/role assignments.
- [ ] Đã phân biệt quyền của SMB với FileREST/SAS và NFS.
- [ ] Đã bảo vệ account keys, có kế hoạch rotation và kiểm kê các client legacy.
- [ ] Đã cấu hình backup/snapshots, soft delete khi hỗ trợ, logging và quy trình phục hồi.
- [ ] Đã thử các ca thành công, bị từ chối, mất mạng và thay đổi nhóm/quyền.

## 17. Bài tập tình huống

Một công ty dùng Azure Files share `company-docs` qua SMB với nguồn danh tính được hỗ trợ. Các thư mục `Finance` và `Engineering` nằm trong cùng share. Yêu cầu:

1. Kế toán được tạo/sửa/xóa các file nghiệp vụ trong `Finance`.
2. Kiểm toán chỉ được đọc `Finance`.
3. Kỹ sư được sửa trong `Engineering` nhưng không được đọc `Finance`.
4. Nhóm quản trị ACL là nhóm riêng, không chia sẻ account key với nhân viên.
5. Windows client kết nối qua private endpoint, dùng danh tính tương ứng.

**Nhiệm vụ:** Đề xuất RBAC cho từng nhóm ở cấp share, ACL tại thư mục gốc và hai thư mục con, cách kiểm tra Kerberos/DNS/cổng 445, và ma trận test cho ít nhất ba người dùng. Giải thích hai trường hợp: Auditor có ACL Modify nhưng share-level Reader; Engineer có share-level Contributor nhưng không có ACL Finance.

**Hướng giải tham khảo:** Các nhóm cần sửa nội dung có share-level Contributor, Audit có Reader. Ở NTFS ACL, FinanceEditors có Modify trên `Finance`, FinanceAuditors có Read, EngineeringEditors có Modify trên `Engineering`; nhóm còn lại không được cấp quyền trên thư mục không thuộc trách nhiệm. Trên share root, cấu hình traversal và inheritance phù hợp để không vô tình cấp quyền rộng. Kiểm tra người dùng thật bằng `whoami`, `klist`, `net use`, `icacls` và các thao tác đọc/ghi; hai trường hợp đối chiếu vẫn bị hạn chế bởi lớp chặt hơn.

### Câu hỏi tự kiểm tra

**1. Hai lớp phân quyền quan trọng của SMB identity-based Azure Files là gì?** Share-level permission và NTFS file/directory ACL.

**2. Gán role `Contributor` ở resource group có tự động cho phép mọi người đọc share qua SMB không?** Không. Cần xác thực SMB với danh tính và quyền dữ liệu tương ứng.

**3. Vì sao không đưa account key cho nhân viên để mount share?** Account key có đặc quyền rất rộng, không phù hợp phân quyền theo danh tính người dùng và làm sai lệch việc kiểm thử ACL.

**4. Microsoft Entra Domain Services có giống tài khoản Entra ID thông thường không?** Không; đó là managed domain với các khả năng domain cần cấu hình riêng.

**5. Có thể dùng Blob user delegation SAS làm đường dẫn mount SMB không?** Không. Đó là cơ chế token dành cho các request Blob API được hỗ trợ.

**6. Với NFS, có dùng `icacls` và các role `Storage File Data SMB Share` để quản lý truy cập trực tiếp không?** Không. NFS có mô hình mạng và quyền POSIX phù hợp riêng.

**7. Nếu Test-NetConnection cổng 445 thất bại, bước tiếp theo là đổi NTFS ACL đúng không?** Không. Phải khắc phục vấn đề mạng/DNS/route trước.

## Kết luận

Đối với **Azure Files SMB**, thiết kế an toàn cần xác định đúng **ai đang đăng nhập**, **quyền ở cấp share** và **NTFS ACL ở tệp/thư mục**. AD DS, Microsoft Entra Domain Services và Microsoft Entra Kerberos là những nguồn danh tính cần chọn theo môi trường được hỗ trợ; Azure RBAC và ACL bổ sung cho nhau chứ không thay thế nhau.

Account key có thể thuận tiện cho hệ thống cũ nhưng mang đặc quyền rộng; SAS dành cho những API được hỗ trợ không phải cơ chế đăng nhập SMB; NFS lại có một mô hình bảo mật khác. Hãy kết hợp danh tính, RBAC, ACL, kết nối mạng riêng, logging, backup và kiểm thử quyền theo từng nhóm để file share của ứng dụng Azure vừa dễ sử dụng vừa được bảo vệ đúng mức.
