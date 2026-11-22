# Đồng bộ file server bằng Azure File Sync

Nhiều doanh nghiệp đã có file server Windows phục vụ nhân viên qua SMB, chứa tài liệu dự án, hồ sơ vận hành, hình ảnh và các thư mục chia sẻ theo phòng ban. Khi mở rộng lên Microsoft Azure, họ muốn giữ trải nghiệm mở tệp qua ổ mạng quen thuộc, giảm dung lượng đĩa phải duy trì tại văn phòng, đồng bộ dữ liệu giữa các chi nhánh và có điểm lưu trữ tập trung trên cloud.

**Azure File Sync** là dịch vụ hỗ trợ đồng bộ dữ liệu của **Windows Server** với **Azure Files**, đồng thời có thể dùng **cloud tiering** để lưu bộ nhớ đệm (cache) những tệp thường truy cập tại máy chủ cục bộ và đưa nội dung tệp ít dùng lên Azure. Người dùng vẫn truy cập file server qua SMB như trước; phía Azure chứa bản sao trung tâm trong một Azure file share.

Bài học thuộc chương **Lưu trữ tệp và đĩa** của module **CLOUD_PROVIDERS_AZURE**. Từ kiến thức về subscription, resource group, danh tính, mạng, dịch vụ tính toán, lưu trữ và chi phí, ta xây dựng một giải pháp đồng bộ file server có thể triển khai, giám sát, bảo vệ và phục hồi một cách có kiểm soát.

> **Trọng tâm:** Azure File Sync là **đồng bộ hai chiều với Azure Files và bộ nhớ đệm cục bộ**, không phải công cụ sao lưu độc lập, không phải block-level disk replication và không tự tạo đồng bộ file lock theo thời gian thực giữa mọi máy chủ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khi nào dùng Azure File Sync thay vì truy cập trực tiếp Azure Files qua SMB.
2. Phân biệt **Storage Sync Service**, **sync group**, **cloud endpoint**, **server endpoint**, **registered server** và **Azure File Sync agent**.
3. Thiết kế đồng bộ một hoặc nhiều Windows file server với một Azure file share.
4. Hiểu quy trình đồng bộ, cloud change detection, cloud tiering và cách tệp được tải lại (recall) khi mở.
5. Chuẩn bị Windows Server, volume NTFS, Azure Storage, danh tính và kết nối HTTPS phù hợp.
6. Thiết lập Azure File Sync qua Azure Portal và xác minh từ Windows Server.
7. Theo dõi sync health, xử lý file không đồng bộ, lỗi agent, thiếu dung lượng và mạng.
8. Thiết kế bảo vệ dữ liệu, sao lưu và khôi phục khi file server hoặc địa điểm gặp sự cố.
9. Đánh giá các giới hạn về khả năng đồng bộ đồng thời, quyền truy cập, bảo mật và chi phí.

## 2. Bài toán: giữ file server tại chỗ nhưng đưa dữ liệu lên Azure

Giả sử công ty có hai văn phòng, mỗi nơi dùng một file server Windows cho thư mục **D:\Shares\Projects**. Nhân viên truy cập qua đường dẫn SMB như:

~~~text
\\fileserver-hcm\Projects
\\fileserver-hn\Projects
~~~

Các khó khăn thường gặp:

- Một chi nhánh phải thường xuyên truy cập dữ liệu từ chi nhánh khác qua WAN có độ trễ.
- File server hiện tại có đĩa gần đầy, nhưng phần lớn tài liệu cũ hiếm khi được mở.
- Khi máy chủ gặp sự cố, cần khôi phục dữ liệu và tạo máy chủ thay thế.
- Đội IT muốn có điểm lưu trữ tập trung trên Azure và khả năng theo dõi trạng thái đồng bộ.

Có ba cách tiếp cận khác nhau:

| Phương án | Người dùng truy cập vào đâu? | Đặc điểm |
|---|---|---|
| File server truyền thống | SMB share trên một Windows Server | Không tự có bản sao cloud hoặc dữ liệu cho chi nhánh khác |
| Azure Files trực tiếp | SMB/NFS endpoint của Azure Files theo khả năng dịch vụ | Không cần Windows file server làm cache, nhưng client phải có đường mạng và cơ chế xác thực thích hợp |
| **Azure File Sync** | SMB share trên Windows Server cục bộ; agent đồng bộ với Azure Files | Giữ giao diện truy cập local, có cloud endpoint chung và tùy chọn cloud tiering |

Azure File Sync phù hợp khi tổ chức **muốn tiếp tục cung cấp chia sẻ SMB tại địa điểm** nhưng sử dụng Azure Files để tập trung dữ liệu và đồng bộ giữa các máy chủ. Nếu không cần máy chủ cục bộ, truy cập trực tiếp Azure Files có thể đơn giản hơn.

## 3. Kiến trúc và các thành phần

~~~mermaid
flowchart TB
    U1["Nhân viên văn phòng A"] -->|"SMB đến máy chủ nội bộ"| S1["Windows Server A<br/>D:\Shares\Projects<br/>Azure File Sync agent"]
    U2["Nhân viên văn phòng B"] -->|"SMB đến máy chủ nội bộ"| S2["Windows Server B<br/>D:\Shares\Projects<br/>Azure File Sync agent"]
    S1 <-->|"Đồng bộ nội dung qua HTTPS"| F["Azure Files<br/>file share: projects"]
    S2 <-->|"Đồng bộ nội dung qua HTTPS"| F
    M["Storage Sync Service<br/>Sync group: projects-sync"] -. "Đăng ký, cấu hình, theo dõi" .-> S1
    M -. "Đăng ký, cấu hình, theo dõi" .-> S2
    M -. "Cloud endpoint" .-> F
~~~

Sơ đồ minh họa **một sync group** liên kết **một Azure file share** với **hai thư mục server endpoint**. Các máy chủ không nhất thiết giao tiếp trực tiếp với nhau; đồng bộ nội dung đi qua Azure file share. Storage Sync Service cung cấp khả năng quản lý quan hệ đồng bộ, còn dữ liệu tệp được lưu trong Azure Files.

### 3.1. Bảng thuật ngữ

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Storage Account** | Tài khoản Azure chứa Azure file share, chịu trách nhiệm cấu hình mạng, bảo mật, redundancy và billing | stfilesordersdemo |
| **Azure file share** | Điểm lưu trữ file tập trung của Azure Files | projects |
| **Storage Sync Service** | Tài nguyên Azure quản lý máy chủ được đăng ký và các nhóm đồng bộ | stsync-projects |
| **Sync group** | Quan hệ đồng bộ giữa một cloud endpoint và các server endpoint liên quan | projects-sync |
| **Cloud endpoint** | Tham chiếu một Azure file share trong sync group | Azure file share projects |
| **Registered server** | Windows Server đã cài agent và đăng ký với một Storage Sync Service | fileserver-hcm |
| **Server endpoint** | Đường dẫn trên volume của server được đưa vào một sync group | D:\Shares\Projects |
| **Azure File Sync agent** | Thành phần cài trên Windows Server để theo dõi thay đổi, đồng bộ và thực hiện cloud tiering | Agent phiên bản được hỗ trợ |

Một **sync group có một cloud endpoint** và có thể có nhiều server endpoint theo giới hạn hỗ trợ. Mỗi Azure file share chỉ nên được đưa vào mô hình cloud endpoint theo các quy tắc tính duy nhất của dịch vụ; không tự sử dụng cùng một share trong nhiều sync group.

### 3.2. Cloud endpoint và server endpoint khác nhau ở đâu?

**Cloud endpoint** đại diện cho Azure file share, nơi lưu dữ liệu tập trung. **Server endpoint** đại diện cho đường dẫn cục bộ do agent quản lý, nơi nhân viên có thể sử dụng SMB share để đọc và ghi.

Ví dụ:

~~~text
Storage Sync Service: stsync-projects
└── Sync group: projects-sync
    ├── Cloud endpoint: stfilesordersdemo / projects
    ├── Server endpoint: fileserver-hcm / D:\Shares\Projects
    └── Server endpoint: fileserver-hn  / D:\Shares\Projects
~~~

Điều quan trọng là **đường dẫn cục bộ của các server endpoint không nhất thiết phải giống nhau**, miễn mỗi đường dẫn tuân theo giới hạn dịch vụ. Sync group quyết định các endpoint nào chia sẻ một tập dữ liệu.

### 3.3. File share trên Windows Server vẫn là một cấu hình riêng

Một server endpoint không tự đồng nghĩa với SMB share đã được chia sẻ đúng tên và quyền. Bạn vẫn cần quản lý:

- Tên SMB share, ví dụ **Projects**.
- Share-level permissions.
- NTFS Access Control Lists (ACL).
- Danh tính người dùng/nhóm (thường trong Active Directory).
- DNS và đường mạng từ client đến máy chủ.

Azure File Sync đồng bộ dữ liệu và metadata được hỗ trợ, trong đó có NTFS ACL, nhưng **cấu hình SMB share trên từng Windows Server không tự được tái tạo thành một cấu hình share-level giống hệt** khi thêm máy chủ mới.

## 4. Luồng đồng bộ hoạt động như thế nào?

### 4.1. Tệp được tạo ở máy chủ A

Giả sử nhân viên lưu tệp:

~~~text
\\fileserver-hcm\Projects\Design\diagram-v2.pptx
~~~

Một chu kỳ điển hình:

1. Windows Server A nhận thao tác ghi qua SMB và lưu dữ liệu trên volume NTFS.
2. Azure File Sync agent phát hiện thay đổi qua cơ chế theo dõi file system.
3. Agent đồng bộ nội dung và metadata được hỗ trợ lên Azure file share.
4. Windows Server B nhận thay đổi thông qua quy trình đồng bộ với cùng cloud endpoint.
5. Nhân viên văn phòng B nhìn thấy tệp trong thư mục tương ứng khi quá trình đồng bộ hoàn tất.

**Đây không phải ghi đồng bộ toàn hệ thống trong cùng một giao dịch.** Có thể có độ trễ giữa lúc máy chủ A ghi xong và lúc máy chủ B nhìn thấy phiên bản mới.

### 4.2. Thay đổi đi theo cả hai chiều

Azure File Sync có thể đồng bộ:

- **Server → Azure file share:** tạo, chỉnh sửa, đổi tên, xóa trong phạm vi hỗ trợ.
- **Azure file share → server:** các thay đổi từ cloud endpoint được phát hiện và đưa xuống server endpoint.
- **Server A → cloud → Server B:** chia sẻ dữ liệu qua cloud endpoint chung.

Vì xóa hoặc ghi đè cũng là thay đổi, lỗi do con người hoặc ransomware **có thể lan truyền**. Bảo vệ dữ liệu phải có backup, snapshot và chính sách quyền riêng.

### 4.3. Cloud change detection không nhất thiết tức thì

Thay đổi phát sinh trực tiếp trên Windows Server thường được agent theo dõi nhanh hơn thay đổi được thực hiện **trực tiếp trên Azure file share** bằng công cụ hoặc client bên ngoài.

Azure File Sync có cơ chế **cloud change detection** định kỳ để phát hiện những thay đổi trực tiếp ở cloud endpoint. Vì vậy, nếu một tệp được ghi trực tiếp lên Azure Files, không nên giả định mọi server endpoint nhìn thấy tệp ngay lập tức. Trong tài liệu vận hành, chu kỳ phát hiện thường được mô tả ở mức khoảng **một lần mỗi 24 giờ**; lịch trình cụ thể và khả năng gọi job phát hiện theo yêu cầu phải đối chiếu với phiên bản dịch vụ hiện tại.

Nếu cần đồng bộ từ một nguồn cập nhật cloud liên tục, hãy đánh giá cách ứng dụng thực hiện thay đổi, thời gian chấp nhận dữ liệu chậm và công cụ cloud change detection được Azure hỗ trợ.

### 4.4. Azure File Sync không đồng bộ file locks giữa các máy chủ

Hai người có thể mở cùng một tệp tại hai văn phòng trước khi bản cập nhật của người kia đồng bộ xong. SMB file lock được quản lý bởi file server mà client đang sử dụng, **không tự trở thành một distributed lock áp dụng đồng thời trên mọi server endpoint**.

Khi hai bản sao bị chỉnh sửa đồng thời, có thể xảy ra **sync conflict** hoặc tạo bản sao xung đột theo hành vi dịch vụ, tùy kịch bản. Không nên dùng Azure File Sync làm nền tảng ghi đồng thời cho cơ sở dữ liệu, ứng dụng đòi hỏi khóa phân tán hoặc file đa người sửa theo thời gian thực mà chưa có cơ chế phối hợp phù hợp.

Đối với tài liệu cần đồng biên tập, xem xét công cụ cộng tác có quản lý phiên bản và tranh chấp ở lớp ứng dụng.

## 5. Cloud tiering: giữ dữ liệu nóng tại chỗ

Cloud tiering là một tính năng quan trọng của Azure File Sync. Khi bật, agent có thể **giữ namespace và metadata của tệp ở Windows Server** nhưng chuyển nội dung của một số tệp ít dùng lên Azure để giải phóng dung lượng đĩa cục bộ.

### 5.1. Tệp được tiered là gì?

Ví dụ thư mục 4 TB gồm:

- 400 GB tài liệu nhân viên đang chỉnh sửa thường xuyên.
- 3,6 TB tài liệu lịch sử ít truy cập.

Nếu cấu hình cloud tiering phù hợp, máy chủ có thể giữ nội dung cục bộ của nhóm file thường dùng và để các file cũ ở trạng thái **tiered**. Người dùng vẫn thấy tên, thư mục và metadata, nhưng khi mở một tệp tiered, agent cần **recall** nội dung từ Azure.

~~~mermaid
flowchart LR
    U["Người dùng mở file"] --> S["File server"]
    S --> D{"Nội dung file còn cục bộ?"}
    D -->|Có| L["Đọc từ đĩa local"]
    D -->|Không| C["Recall qua Azure File Sync<br/>từ Azure Files"]
    C --> L
~~~

**Cloud tiering không giống Blob Archive tier**: đó là khả năng quản lý bộ nhớ đệm của Azure File Sync trên server endpoint, không phải yêu cầu chuyển Azure file share thành Azure Blob Archive.

### 5.2. Chính sách cloud tiering

Các chính sách phổ biến gồm:

| Chính sách | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **Volume free space** | Duy trì tỷ lệ dung lượng trống mục tiêu trên volume, tier các file phù hợp khi cần | Mục tiêu giữ 20% volume trống |
| **Date policy** | Cho phép tier các file không được truy cập trong một khoảng thời gian theo cấu hình | Tệp không được truy cập trong 60 ngày |
| **Tiering disabled** | Giữ toàn bộ nội dung file được đồng bộ trên server endpoint theo cơ chế bình thường | Máy chủ có đủ ổ đĩa và cần đọc offline |

Đây là **ví dụ cấu hình**, không phải mặc định bắt buộc. Hành vi lựa chọn file để tier còn phụ thuộc vào những điều kiện và ngoại lệ của agent.

Lưu ý: mục tiêu free space là mục tiêu của **volume chứa endpoint**, không phải một quota độc lập cho mỗi thư mục. Nếu trên cùng volume có dữ liệu của ứng dụng khác, việc đặt chính sách có thể ảnh hưởng đến phần dung lượng dùng chung.

### 5.3. Điều gì xảy ra khi máy chủ mất Internet?

Một file đã có nội dung **đầy đủ trong cache cục bộ** thường vẫn có thể được đọc trong phạm vi quyền truy cập và trạng thái local. Nhưng file đã tiered mà nội dung **chỉ còn ở Azure** không thể được recall khi mất kết nối đến cloud endpoint.

Vì vậy:

- Không nên bật tiering quá mạnh ở chi nhánh có Internet thường xuyên gián đoạn nếu người dùng cần đọc offline.
- Những ứng dụng đòi hỏi truy cập tức thời và ổn định vào toàn bộ dữ liệu có thể cần tiering disabled hoặc kế hoạch cache phù hợp.
- Recall file lớn có thể làm tăng độ trễ mở file và tải WAN.
- Cần ước lượng những file nào “nóng”, tốc độ mạng thực và lượng dung lượng cục bộ tối thiểu.

### 5.4. Đánh giá khả năng tiết kiệm dung lượng

Giả sử tổng dataset là **6 TB**, trong đó **1,2 TB** được truy cập thường xuyên. Không nên mặc định máy chủ chỉ cần đúng 1,2 TB. Phải chừa chỗ cho hệ điều hành, metadata, các file đang recall, thay đổi ngắn hạn, dữ liệu mới, hoạt động của agent và tỷ lệ free space mục tiêu.

Một quy trình dự toán hợp lý:

1. Đo dung lượng đang sử dụng và tăng trưởng theo tháng.
2. Quan sát lịch sử truy cập file và tỷ lệ dữ liệu thường xuyên dùng.
3. Xác định mục tiêu free space phù hợp cho volume.
4. Kiểm tra băng thông và latency từ server đến Azure.
5. Thử nghiệm hành vi recall ở nhóm người dùng đại diện.
6. Theo dõi dung lượng local và lượng dữ liệu tiered sau khi triển khai.

Cloud tiering giúp quản lý **dung lượng cục bộ**, nhưng không tự giảm lượng dữ liệu phải lưu trong Azure Files theo cùng tỷ lệ.

## 6. Điều kiện tiên quyết và giới hạn cần biết

### 6.1. Windows Server và hệ thống tệp

Azure File Sync agent được cài trên **Windows Server** có phiên bản, bản vá và kiến trúc nằm trong danh sách hỗ trợ hiện hành của Azure. Không giả định mọi Windows Server đời cũ hoặc Windows client đều được phép đăng ký.

Đường dẫn server endpoint cần nằm trên hệ thống tệp và loại volume được Azure File Sync hỗ trợ; **NTFS** là nền tảng thường dùng. Cần kiểm tra các giới hạn về đường dẫn, volume, tính năng file system, điểm mount và số lượng endpoint trước khi triển khai.

Các loại dữ liệu đặc thù như file hệ thống, dữ liệu ứng dụng đang khóa liên tục, reparse point, file được mã hóa theo cơ chế đặc biệt hoặc filesystem không được hỗ trợ cần được đánh giá riêng. Azure File Sync không phải cơ chế sao chép toàn bộ Windows Server, registry, boot volume hay ứng dụng.

### 6.2. Azure Storage

Cần có:

- Một **Storage Account** với account kind và performance tier tương thích với Azure Files/Azure File Sync.
- Một **Azure file share** đúng giao thức và cấu hình được Azure File Sync hỗ trợ.
- Đủ quota và hiệu năng cho dung lượng, số file và mức truy cập dự kiến.
- Redundancy phù hợp với yêu cầu: LRS, ZRS, GRS, GZRS hoặc lựa chọn được hỗ trợ theo SKU/region.
- Cấu hình bảo mật, truy cập mạng và khả năng backup/restore được phê duyệt.

Azure File Sync sử dụng **Azure Files** làm cloud endpoint; **không** chỉ một Blob container thông thường.

### 6.3. Vùng triển khai

**Storage Sync Service và Azure file share dùng làm cloud endpoint cần có vùng triển khai tương thích**, thông thường được đặt cùng Azure region theo yêu cầu dịch vụ. Các Windows Server có thể nằm ở on-premises hoặc vị trí khác và kết nối tới vùng đó qua mạng.

Đừng suy luận rằng có thể đặt Sync Service bất kỳ region nào rồi trỏ tới mọi storage share trong các region khác. Kiểm tra quy tắc region và giới hạn áp dụng trước khi triển khai.

### 6.4. Mạng và DNS

Máy chủ cần kết nối outbound HTTPS đến các endpoint Azure File Sync, Storage và dịch vụ xác thực/quản lý liên quan. Thông thường **TCP/443** là yêu cầu nền tảng cho agent sync; danh sách endpoint đầy đủ phụ thuộc cấu hình và phiên bản hiện hành.

Phân biệt rõ:

- **Client → Windows Server bằng SMB:** thường sử dụng TCP/445 trên mạng LAN hoặc đường mạng nội bộ.
- **Azure File Sync agent → Azure qua HTTPS:** kết nối outbound phục vụ đồng bộ và quản lý.
- **Client → Azure Files trực tiếp bằng SMB:** nếu tổ chức dùng mô hình này, TCP/445 cùng các điều kiện identity/networking có thể cần thiết; không đồng nghĩa agent bắt buộc có SMB 445 outbound tới Azure.

Cần kiểm tra DNS, proxy/firewall, TLS, chứng chỉ, các endpoint Azure được phép, quyền truy cập mạng của Storage Account và Private Endpoint nếu sử dụng.

### 6.5. Danh tính và quyền

Phải phân biệt:

1. **Quyền quản lý Azure:** quyền tạo Storage Sync Service, sync group, cloud endpoint và quản trị Storage Account.
2. **Danh tính đăng ký Windows Server:** quyền thao tác phù hợp trong Azure và trên máy chủ.
3. **Quyền truy cập dữ liệu của người dùng:** share-level permission, NTFS ACL và danh tính Active Directory/identity được hỗ trợ.
4. **Quyền của agent:** các quyền và cơ chế xác thực của dịch vụ để đồng bộ dữ liệu.

Không dùng một tài khoản Owner toàn subscription cho mọi bước chỉ vì thuận tiện. Cấp đúng phạm vi, ghi nhận thay đổi và xoay vòng credential theo chính sách.

## 7. Quy hoạch một mô hình triển khai mẫu

Giả sử doanh nghiệp muốn chuyển thư mục Projects lên Azure và đồng bộ hai văn phòng:

| Thành phần | Tên minh họa |
|---|---|
| Subscription | subscription lab đã được phê duyệt |
| Resource group | rg-filesync-lab |
| Region của tài nguyên Azure | southeastasia |
| Storage Account | stfilesyncdemo12345 *(phải duy nhất toàn cầu)* |
| Azure file share | projects |
| Storage Sync Service | stsync-projects |
| Sync group | projects-sync |
| Server A | fileserver-hcm |
| Server B | fileserver-hn |
| Server endpoint A | D:\Shares\Projects |
| Server endpoint B | E:\Department\Projects |
| SMB share của máy A | \\fileserver-hcm\Projects |
| SMB share của máy B | \\fileserver-hn\Projects |

Các tên và đường dẫn chỉ dùng để minh họa. Khi thao tác thật, kiểm tra tên, volume, quota, ACL và data ownership trước khi tạo endpoint.

### 7.1. Quyết định trước khi triển khai

- Azure file share là nguồn dữ liệu mới **rỗng**, hay đã chứa file được người dùng sử dụng?
- Có máy chủ nào đang giữ phiên bản dữ liệu chuẩn không?
- Hai file server có trùng namespace và file khác nội dung không?
- Có cần cloud tiering trên cả hai server hay chỉ một server có ổ đĩa nhỏ?
- Người dùng sẽ giữ SMB path cũ bằng DNS alias/DFS Namespace hay chuyển sang path mới?
- Quy trình khôi phục, backup và quyền người dùng đã được thử chưa?
- Có ứng dụng đang mở file liên tục, database nằm trong thư mục, hoặc chương trình chống virus quét quá mạnh không?

Nếu dữ liệu đã tồn tại ở nhiều nơi, phải lên kế hoạch **onboarding và xử lý xung đột**. Không thêm hàng loạt server endpoint rồi giả định các bản sao khác nhau sẽ tự hợp nhất đúng ý nghiệp vụ.

## 8. Triển khai bằng Azure Portal — từng bước

Thứ tự sau phù hợp với mô hình mới và môi trường thử nghiệm. Tên menu có thể thay đổi theo bản cập nhật Azure Portal.

### Bước 1: tạo Storage Account và Azure file share

1. Trong Azure Portal, chọn **Storage accounts → Create**.
2. Chọn đúng subscription và **rg-filesync-lab**.
3. Chọn region, account kind/performance tier và redundancy được Azure File Sync hỗ trợ.
4. Thiết lập bảo mật mạng, TLS, xác thực và các tùy chọn bảo vệ dữ liệu theo chính sách.
5. Hoàn tất tạo Storage Account.
6. Mở Storage Account, vào **File shares**, tạo Azure file share **projects**.
7. Chọn quota/tier phù hợp với dung lượng và workload.
8. Xác minh file share hiển thị và không có dữ liệu không chủ ý trước khi ghép với thư mục server hiện hữu.

Lưu ý chi phí: tạo Standard hay Premium file share, mức dung lượng/IOPS và mô hình billing có thể ảnh hưởng đáng kể đến giá. Không chọn một tier chỉ từ tên mà chưa đo loại workload.

### Bước 2: tạo Storage Sync Service

1. Tìm dịch vụ **Storage Sync Services** trong Portal.
2. Chọn **Create**.
3. Chọn subscription và resource group phù hợp.
4. Chọn region tương thích với Storage Account chứa Azure file share.
5. Đặt tên **stsync-projects** và tạo tài nguyên.
6. Mở Storage Sync Service để kiểm tra trạng thái.

Storage Sync Service là nơi tổ chức sync group, registered servers và health. Không coi bản thân dịch vụ này là ổ đĩa lưu toàn bộ dữ liệu: cloud endpoint mới trỏ tới Azure file share chứa nội dung tệp.

### Bước 3: tạo Sync group và Cloud endpoint

1. Trong Storage Sync Service, chọn **Sync groups → + Sync group**.
2. Đặt tên **projects-sync**.
3. Chọn subscription/Storage Account và Azure file share **projects** làm cloud endpoint.
4. Xác nhận khu vực và các yêu cầu kết nối.
5. Tạo sync group.
6. Kiểm tra rằng sync group hiển thị cloud endpoint đúng file share, không trỏ nhầm sang share có dữ liệu khác.

Một sync group chỉ có **một cloud endpoint**, còn server endpoint được thêm sau.

### Bước 4: chuẩn bị Windows Server

Trên mỗi file server:

1. Xác nhận Windows Server version được Azure File Sync hỗ trợ và đã cài bản vá thích hợp.
2. Kiểm tra volume NTFS và thư mục nguồn cần đồng bộ.
3. Kiểm tra dung lượng còn lại, file lock, dữ liệu trùng, tên file đặc biệt và NTFS ACL.
4. Bảo đảm outbound HTTPS đến các endpoint Azure cần thiết, DNS và TLS hoạt động.
5. Bảo đảm SMB share, quyền share, AD group và truy cập từ client vẫn đúng.
6. Chuẩn bị bản sao lưu và kế hoạch khôi phục dữ liệu ban đầu.

Không nên biến lần triển khai đầu tiên thành một thao tác đổi tất cả đường dẫn SMB trên production. Có thể chạy pilot trên một bộ dữ liệu nhỏ trước.

### Bước 5: cài Azure File Sync agent và đăng ký server

1. Tải **Azure File Sync agent** dành cho Windows Server từ nguồn Microsoft được tài liệu hiện hành chỉ định.
2. Chọn bản agent mới và **được hỗ trợ cho phiên bản Windows Server** đang dùng.
3. Cài agent trên máy chủ với quyền phù hợp; thực hiện restart nếu installer yêu cầu.
4. Mở **Server Registration** theo quy trình của agent.
5. Đăng nhập và chọn đúng Azure tenant/subscription, resource group và Storage Sync Service.
6. Hoàn tất đăng ký, sau đó quay lại Portal kiểm tra máy chủ trong **Registered servers**.

Nếu thông tin đăng ký chưa xuất hiện, cần kiểm tra agent, xác thực, quyền, kết nối tới Azure và thời gian đồng bộ hệ thống. Không lặp lại việc cài/đăng ký nhiều lần khi chưa xác minh trạng thái cũ.

### Bước 6: thêm Server endpoint

Trong **projects-sync**:

1. Chọn **Add server endpoint**.
2. Chọn registered server **fileserver-hcm**.
3. Chọn đường dẫn **D:\Shares\Projects**.
4. Quyết định bật hoặc tắt **cloud tiering**.
5. Nếu bật, cấu hình volume free space và các chính sách liên quan theo nhu cầu.
6. Tạo endpoint, sau đó theo dõi tiến trình initial sync và health.

Sau khi initial sync được xác nhận, thêm **fileserver-hn** với endpoint ở đường dẫn đã duyệt và kiểm tra dữ liệu từng bên. Nếu file share cloud đã có dữ liệu hoặc có nhiều file server nguồn, hãy xem quy trình onboarding/initial sync và xử lý conflict trước khi thêm endpoint.

### Bước 7: kiểm thử end-to-end

1. Trên máy A, tạo một file thử nghiệm mới trong thư mục được sync.
2. Xác nhận file xuất hiện trên Azure file share sau khi agent đồng bộ.
3. Xác nhận file xuất hiện ở thư mục của máy B.
4. Từ SMB client B, đọc nội dung file, kiểm tra quyền NTFS.
5. Sửa file ở **một nơi**, xác nhận thay đổi được truyền đến các endpoint còn lại.
6. Nếu bật cloud tiering, kiểm tra namespace, free space và quá trình recall của file thử nghiệm đủ an toàn.
7. Kiểm tra log, health và số lỗi đồng bộ.

**Không dùng tệp nghiệp vụ quan trọng làm dữ liệu test xóa hoặc ghi đè.** Sử dụng thư mục pilot hoặc tập file được phép chỉnh sửa.

## 9. Kiểm tra tài nguyên Azure bằng CLI

Azure Portal là lựa chọn thuận tiện cho các bước có agent/registration. Azure CLI có thể hỗ trợ bước xác nhận subscription, Storage Account và Azure file share. Ví dụ sau sử dụng Bash trong Azure Cloud Shell.

### 9.1. Xem Storage Account đã chọn

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-filesync-lab"
STORAGE_NAME="<storage-account-name>"

az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE_NAME" \
  --query "{name:name,location:location,kind:kind,sku:sku.name,publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Đọc kết quả và kiểm tra đúng region, kind, SKU, access policy. Lệnh này chỉ truy vấn cấu hình management plane; **không chứng minh agent đã đồng bộ thành công**.

### 9.2. Xác minh file share đã tồn tại

~~~bash
az storage share-rm list \
  --resource-group "$RG" \
  --storage-account "$STORAGE_NAME" \
  --output table

az storage share-rm show \
  --resource-group "$RG" \
  --storage-account "$STORAGE_NAME" \
  --name "projects" \
  --output json
~~~

Các lệnh **share-rm** dùng resource management API cho Azure file shares. Tùy phiên bản Azure CLI và mô hình tài khoản, tham số/extension có thể thay đổi; cần dùng help của phiên bản CLI trong môi trường thực tế khi thao tác.

### 9.3. Không dùng storage account key làm thói quen

Đối với thao tác quản trị và đọc metadata, ưu tiên Azure RBAC và danh tính được quản lý theo nhu cầu. Tránh xuất account key hoặc connection string vào log của pipeline, tài liệu hoặc command history.

Nếu cần thao tác data plane, hãy dùng phương thức xác thực thích hợp với khả năng của dịch vụ và danh tính, thay vì cho toàn bộ người vận hành giữ storage key.

## 10. Kiểm tra Windows Server bằng PowerShell

Trên Windows Server có quyền kiểm tra:

~~~powershell
# Kiểm tra phiên bản hệ điều hành và trạng thái máy chủ
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

# Kiểm tra volume và hệ thống tệp
Get-Volume | Select-Object DriveLetter, FileSystem, Size, SizeRemaining

# Thư mục dự kiến làm server endpoint có tồn tại không?
Test-Path -LiteralPath "D:\Shares\Projects"

# Xem SMB shares đang được công bố trên máy chủ
Get-SmbShare | Select-Object Name, Path, Description
~~~

Kiểm tra quyền local của thư mục và share:

~~~powershell
Get-Acl -LiteralPath "D:\Shares\Projects" | Format-List

Get-SmbShareAccess -Name "Projects" |
  Select-Object Name, AccountName, AccessControlType, AccessRight
~~~

Đây là các lệnh **kiểm tra**, không sửa ACL. Không dùng **Everyone: Full Control** như một cách giải quyết nhanh khi client bị từ chối truy cập. Phải xác định share permission, NTFS ACL và identity của người dùng.

### 10.1. Kiểm tra một số điều kiện kết nối

~~~powershell
# Ví dụ kiểm tra kết nối HTTPS đến Azure Files endpoint
Test-NetConnection -ComputerName "<storage-account-name>.file.core.windows.net" -Port 443

# Kiểm tra DNS resolution
Resolve-DnsName "<storage-account-name>.file.core.windows.net"
~~~

Kiểm tra một hostname/port chỉ giúp xác nhận một phần đường mạng; agent còn sử dụng các endpoint của Storage Sync Service và dịch vụ phụ trợ. Nếu dùng Private Endpoint, kết quả DNS phải phù hợp với thiết kế private IP. Không kết luận mạng hoàn toàn đúng chỉ từ một lần Test-NetConnection thành công.

### 10.2. Tạo dữ liệu thử nghiệm an toàn

Trong một thư mục thử nghiệm **đã thuộc server endpoint**:

~~~powershell
$testFile = "D:\Shares\Projects\sync-validation.txt"
"Azure File Sync validation - $(Get-Date -Format o)" |
  Set-Content -LiteralPath $testFile -Encoding UTF8

Get-Item -LiteralPath $testFile |
  Select-Object FullName, Length, LastWriteTimeUtc
~~~

Sau đó dùng Portal/Storage file share để xác minh tệp, chờ đồng bộ sang server còn lại và so sánh nội dung. Không dùng bài kiểm tra này để chứng minh file lock phân tán hoặc bảo đảm độ trễ đồng bộ cố định.

## 11. Cloud tiering trong vận hành thực tế

### 11.1. Mô hình cache và recall

Khi tiering bật:

- Những tệp đang được truy cập nhiều có xu hướng có nội dung cục bộ tùy cache và chính sách.
- Những tệp ít dùng có thể chỉ còn phần metadata/namespace tại máy chủ.
- Khi người dùng mở tệp tiered, agent phải lấy nội dung từ Azure.
- File lớn hoặc đường WAN chậm có thể làm ứng dụng chờ lâu khi mở lần đầu.
- Sau recall, mức dùng đĩa thay đổi; chính sách tiering có thể tiếp tục điều tiết cache theo thời gian.

Cloud tiering nên được xem là **một chiến lược phân tầng lưu trữ trong kiến trúc**, không phải chỉ bật nút giảm chi phí. Chi phí Azure Files vẫn tồn tại và lượt recall có thể tạo thêm transaction/network usage.

### 11.2. Tránh tiering gây lỗi ứng dụng

Không phải mọi ứng dụng đều thích hợp với file placeholder/tiered file. Trước khi bật cho thư mục chứa dữ liệu của phần mềm:

1. Xác định phần mềm truy cập file tuần tự hay ngẫu nhiên.
2. Đo độ trễ chấp nhận khi mở một file sau thời gian không dùng.
3. Kiểm tra tính tương thích của antivirus, backup và indexer với tiered files.
4. Thử xử lý lỗi khi mất kết nối Azure.
5. Xem tác động đến ứng dụng lưu file dưới dạng container lớn hoặc thường xuyên sửa.
6. Kiểm tra hành vi của phần mềm đối với file attributes và các thao tác filesystem.

Đối với workload database cần I/O độ trễ rất thấp hoặc cập nhật ngẫu nhiên liên tục, hãy sử dụng công nghệ storage phù hợp thay vì mặc định đặt data files vào Azure File Sync.

### 11.3. Theo dõi cache

Nên theo dõi:

- Dung lượng volume, tỷ lệ free space.
- Dung lượng file tiered so với tổng dataset.
- Số lượt recall và thời gian đọc file thường gặp.
- Mức sử dụng WAN trong giờ cao điểm.
- Các file không thể tier hoặc đang lỗi.
- Tình trạng agent và chính sách cloud tiering.

Nếu chỉ đo dung lượng trống mà không đo trải nghiệm người dùng, hệ thống có thể “tiết kiệm đĩa” nhưng gây chậm nghiêm trọng khi truy cập tệp.

## 12. Đồng bộ nhiều chi nhánh và quản lý xung đột

Hai hoặc nhiều Windows Server có thể là server endpoint của cùng sync group trong phạm vi hỗ trợ.

### 12.1. Thiết kế quyền truy cập và namespace

- Mỗi chi nhánh cung cấp SMB share local cho người dùng của mình.
- Tên share có thể được chuẩn hóa, hoặc dùng **DFS Namespace** nếu cần cung cấp đường dẫn logic thống nhất theo thiết kế được hỗ trợ.
- NTFS ACL trên dữ liệu phải được đánh giá khi đồng bộ và khôi phục.
- Share permissions, DNS alias và chính sách đăng nhập vẫn cần cấu hình tại từng server.
- Giới hạn quyền ghi cho nhóm phù hợp, giảm khả năng cùng file bị thay đổi đồng thời từ nhiều địa điểm.

### 12.2. Ví dụ về conflict

Tình huống:

1. Nhân viên A mở **plan.xlsx** tại HCM và sửa nội dung.
2. Trước khi thay đổi đồng bộ đến Hà Nội, nhân viên B mở bản cũ trên server B và cũng sửa.
3. Hai cập nhật đều được ghi ở endpoint cục bộ.
4. Dịch vụ phải xử lý xung đột trong quy trình đồng bộ.

Không nên hứa rằng Azure File Sync sẽ “merge” mọi thay đổi theo từng ô của Excel. Cách xử lý conflict phụ thuộc loại thao tác, thời gian và trạng thái sync, và có thể lưu các bản sao xung đột để tránh im lặng mất nội dung theo cơ chế được hỗ trợ.

Khuyến nghị vận hành:

- Giới hạn cùng lúc nhiều người sửa file quan trọng tại nhiều endpoint.
- Dùng phần mềm cộng tác thích hợp với file có yêu cầu đồng biên tập.
- Theo dõi mục conflict/error và huấn luyện người dùng nhận biết bản trùng.
- Cân nhắc chỉ định một địa điểm ghi chính cho những loại tài liệu có nguy cơ xung đột cao.

### 12.3. Nếu một server mất kết nối nhiều giờ

Các thay đổi local có thể tiếp tục được người dùng ghi trên dữ liệu còn sẵn trong server, nhưng chúng chưa đến được các endpoint khác cho đến khi kết nối và đồng bộ hoạt động trở lại. Trong lúc mất mạng, file đã tiered có thể không recall được.

Khi khôi phục mạng:

- Agent có thể xử lý backlog đồng bộ.
- Dữ liệu cần được xác minh, nhất là khi cùng file đã thay đổi tại địa điểm khác.
- Theo dõi bandwidth, sync errors và latency cho đến khi backlog giảm.
- Không thực hiện xóa/copy cưỡng bức để “làm cho đồng bộ nhanh hơn” khi chưa hiểu trạng thái dữ liệu.

## 13. Bảo mật: mạng, quyền và mã hóa

### 13.1. Network boundary

Hãy vẽ rõ ba luồng:

~~~mermaid
flowchart LR
    User["Người dùng LAN"] -->|"SMB nội bộ"| Server["Windows File Server"]
    Server -->|"Outbound HTTPS"| Cloud["Azure Files / File Sync"]
    Admin["Quản trị Azure"] -->|"Azure control plane"| Mgmt["Storage Sync Service"]
    Mgmt -. "Quản lý trạng thái" .-> Server
~~~

Mỗi luồng có một yêu cầu riêng:

- SMB nội bộ: giới hạn nguồn truy cập và phân đoạn mạng phù hợp.
- Đồng bộ agent: firewall/proxy outbound HTTPS tới các endpoint cần thiết.
- Azure Files: Storage Account network rules, public/private access, private endpoint, DNS và khả năng hỗ trợ của File Sync.
- Portal/control plane: Azure RBAC, MFA/Conditional Access và kiểm soát thay đổi.

Nếu dùng Private Endpoint cho Storage Account hoặc Storage Sync Service theo hỗ trợ, cần cấu hình private DNS, route, VPN/ExpressRoute hoặc kết nối mạng thích hợp. Không bật “Disable public network access” trên production trước khi chắc rằng agent còn đường đến endpoint riêng.

### 13.2. Bảo vệ nội dung

- Trên Windows Server, quản lý NTFS ACL, share-level permissions và quyền local admin.
- Trên Azure, cấu hình Azure Files, Storage Account, quyền quản trị và data-plane access.
- Tránh lưu storage account key trong script hoặc tài liệu vận hành.
- Sử dụng các cơ chế TLS/mã hóa mà dịch vụ hỗ trợ.
- Bật logging và audit theo yêu cầu compliance.
- Áp dụng bảo mật endpoint, cập nhật Windows Server và agent định kỳ.

**Không trộn lẫn** ba khái niệm: Azure RBAC quản trị Storage Account, xác thực SMB của client và cơ chế hoạt động của agent. Cấp quyền cho một principal ở management plane không đồng nghĩa người dùng tự có quyền đọc mọi file.

### 13.3. Ransomware và xóa nhầm

Azure File Sync có thể đồng bộ các thay đổi xấu từ file server lên cloud endpoint. Nếu một tài khoản có quyền xóa file bị chiếm quyền, xóa nhầm có thể lan đến các máy chủ khác.

Biện pháp nên kết hợp:

1. Backup Azure file share theo chính sách retention.
2. Sử dụng snapshot/khả năng khôi phục file theo dịch vụ và SKU hỗ trợ.
3. Bật các cơ chế bảo vệ file share khi phù hợp; phân biệt file share soft delete với phục hồi từng phiên bản file.
4. Giới hạn quyền sửa/xóa và tách quyền quản lý backup.
5. Theo dõi hoạt động xóa hàng loạt, sync errors và cảnh báo bảo mật.
6. Diễn tập khôi phục bản dữ liệu sạch và đối chiếu quyền NTFS.

Redundancy LRS/ZRS/GRS/GZRS không thay thế backup: xóa/ghi đè logic có thể được sao chép sang các bản sao khác.

## 14. Backup và disaster recovery

### 14.1. Cần backup ở đâu?

Cloud endpoint chứa tập dữ liệu trung tâm trong Azure file share; do đó giải pháp backup nên bao phủ **Azure file share** bằng công cụ và chính sách phù hợp, chẳng hạn Azure Backup cho Azure Files trong phạm vi hỗ trợ.

Tuy vậy, một chính sách DR hoàn chỉnh còn phải bảo vệ:

- Cấu hình Windows Server, SMB share và quyền share.
- NTFS ACL, identity và cấu hình Active Directory liên quan.
- Cấu hình Storage Sync Service, sync group, endpoint và network.
- Tài liệu nguồn, quyền sử dụng ứng dụng và quy trình phục hồi.
- Những file hoặc dữ liệu local nằm **ngoài** server endpoint.

Không giả định việc backup Azure file share tự tái tạo tất cả cấu hình máy chủ hoặc mọi ứng dụng chạy trên Windows.

### 14.2. Server ở chi nhánh hỏng

Kịch bản: máy **fileserver-hcm** bị lỗi ổ đĩa. Cloud endpoint vẫn chứa dữ liệu đã đồng bộ thành công.

Kế hoạch khôi phục tham khảo:

1. Xác định phạm vi lỗi, thu thập log và tình trạng đồng bộ gần nhất.
2. Chọn Windows Server thay thế có phiên bản/agent được hỗ trợ.
3. Cấu hình volume, thư mục, mạng, DNS, domain và bảo mật.
4. Cài Azure File Sync agent và đăng ký server vào Storage Sync Service phù hợp.
5. Thêm server endpoint mới vào sync group theo hướng dẫn phục hồi của Azure.
6. Cho phép đồng bộ namespace/nội dung từ cloud endpoint, áp dụng cloud tiering nếu phù hợp.
7. Tái tạo SMB share, share-level permission và xác minh NTFS ACL.
8. Kiểm tra tài liệu, quyền người dùng, ứng dụng và hiệu năng trước khi chuyển client sang máy mới.

Các thay đổi chưa kịp đồng bộ từ máy bị hỏng lên cloud có thể không tồn tại ở cloud endpoint. Cần xem log và backup local nếu nghiệp vụ yêu cầu bảo vệ chúng.

### 14.3. Mất cả địa điểm hoặc region

Azure file share có thể được cấu hình redundancy và khả năng DR theo SKU. Nhưng **File Sync không tự khôi phục toàn bộ AD, DNS, VPN, file server và SMB path** khi mất địa điểm.

Nếu Azure Storage region gặp sự cố nghiêm trọng:

- Kiểm tra cơ chế geo-redundancy và failover được hỗ trợ cho account/share cụ thể.
- Xem replication lag và nguy cơ mất ghi chưa đến secondary.
- Xác định ảnh hưởng của việc failover storage đối với cloud endpoint và cấu hình Azure File Sync.
- Phối hợp khôi phục compute, mạng, DNS và đăng ký server theo runbook được duyệt.
- Kiểm tra tính nhất quán của dữ liệu sau phục hồi.

Đừng kích hoạt storage account failover như một phép thử nhanh trên production; cần quy trình DR được tổ chức và Azure hỗ trợ.

### 14.4. Diễn tập khôi phục mà không phá dữ liệu thật

Trong lab, dùng file thử nghiệm riêng:

1. Tạo file test trên server, xác minh đã đồng bộ lên cloud.
2. Tạo snapshot/backup theo khả năng được bật.
3. Chỉnh sửa hoặc xóa file **test**, không dùng tài liệu thật.
4. Khôi phục file sang vị trí kiểm thử theo quy trình của dịch vụ.
5. Kiểm tra nội dung, ACL, tên file và đường dẫn.
6. Ghi nhận RTO và các giới hạn quan sát được.

Một backup chưa từng được thử restore chỉ là một kỳ vọng, chưa phải bằng chứng kế hoạch DR hoạt động.

## 15. Giám sát Azure File Sync

### 15.1. Những chỉ số cần theo dõi

| Chỉ số/trạng thái | Mục đích |
|---|---|
| Registered server health | Agent còn online và gửi trạng thái phù hợp không |
| Server endpoint sync health | Có lỗi đồng bộ, backlog hoặc trạng thái cần xử lý không |
| Số file không đồng bộ thành công | Phát hiện dữ liệu hoặc metadata bị kẹt |
| Thời gian đồng bộ gần nhất | Biết endpoint có cập nhật đều không |
| Cloud endpoint health | Azure file share còn sẵn sàng cho các endpoint không |
| Dung lượng local và free space | Đánh giá cloud tiering và nguy cơ đầy ổ |
| Recall/cache behavior | Phát hiện độ trễ đọc file và mức sử dụng WAN |
| Storage capacity/transactions | Theo dõi tải và giới hạn Azure Files |
| Kết nối HTTPS và agent events | Phân tích sự cố xác thực, TLS, proxy hoặc mạng |
| Chi phí Azure Files và dữ liệu | Kiểm soát tăng trưởng và vận hành |

Azure Portal cung cấp các trang trạng thái và giám sát của Storage Sync Service, sync group và server endpoint. Có thể tích hợp Azure Monitor hoặc các khả năng log/cảnh báo được Azure hỗ trợ theo môi trường.

### 15.2. Event log trên Windows

Agent có những log và sự kiện Windows phục vụ chẩn đoán. Trên một server thực, hãy xác định log channel theo phiên bản agent hiện hành bằng Event Viewer hoặc PowerShell:

~~~powershell
Get-WinEvent -ListLog "*FileSync*" -ErrorAction SilentlyContinue |
  Select-Object LogName, RecordCount, IsEnabled
~~~

Lệnh này có tính chất **khám phá log**, không khẳng định mọi phiên bản đều dùng cùng tên channel. Sau khi tìm đúng log, lọc theo thời gian và mã lỗi để đối chiếu với tình trạng sync trong Portal.

Không xóa agent log hoặc sửa trực tiếp cơ sở dữ liệu nội bộ của agent khi chưa có hướng dẫn chính thức.

### 15.3. Thiết kế alert

Nên có cảnh báo khi:

- Server endpoint offline quá ngưỡng cho phép.
- Sync errors không giảm hoặc backlog kéo dài.
- Dung lượng đĩa local xuống quá thấp.
- Azure file share gần quota/giới hạn hiệu năng.
- Nhiều file bị xóa/sửa bất thường trong thời gian ngắn.
- Lượng dữ liệu recall hoặc chi phí tăng đột biến.
- Thay đổi mạng, Storage Account, quyền hoặc chính sách backup ngoài kế hoạch.

Đừng chỉ dựa vào trạng thái “Healthy” chung để kết luận mọi file trong từng thư mục đều có bản sao mới nhất. Cần kiểm tra các lỗi chi tiết và mục tiêu đồng bộ nghiệp vụ.

## 16. Xử lý sự cố theo lớp

| Hiện tượng | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| Server không đăng ký được | Thiếu quyền, sai subscription, agent/OS không hỗ trợ, mạng/TLS/proxy | Kiểm tra agent, RBAC, đăng nhập, DNS và endpoint HTTPS |
| Sync group không thêm được cloud endpoint | Storage Account/file share/region không tương thích hoặc thiếu quyền | Kiểm tra region, account kind, share và service limits |
| Không thêm được server endpoint | Đường dẫn không hợp lệ, volume/file system không hỗ trợ, endpoint chồng lấn hoặc quyền không đủ | Kiểm tra registered server, NTFS path và giới hạn endpoint |
| Server A đã có file nhưng B chưa thấy | Sync lag, backlog, lỗi agent, conflict hoặc mạng | Xem sync health của cả hai endpoint và file cụ thể |
| File ghi trực tiếp lên Azure Files không thấy ngay ở server | Cloud change detection chưa phát hiện | Kiểm tra chu kỳ change detection và cách kích hoạt theo yêu cầu được hỗ trợ |
| File có tên nhưng mở báo lỗi | Nội dung đã tiered, Azure chưa reachable hoặc recall lỗi | Xem kết nối HTTPS, cloud tiering và agent event logs |
| Volume hết chỗ | Tiering disabled, cache quá lớn, policy chưa phù hợp hoặc file không thể tier | Kiểm tra free space, tiering policy và file không eligible |
| Người dùng bị Access Denied | NTFS ACL, share permissions, domain/identity không đúng | Kiểm tra quyền cả share và thư mục/file |
| Nhiều bản sao file xung đột | Ghi cùng file ở nhiều server trước khi đồng bộ | Kiểm tra conflict, quy trình làm việc và bản cần giữ |
| Đồng bộ chậm | Băng thông WAN, số file lớn, thay đổi liên tục, giới hạn service, scan antivirus | Đo WAN, queue/backlog, metadata rate và resource usage |
| Sync health tốt nhưng ứng dụng mở file chậm | Tiered file recall, DNS, SMB client hoặc file server thiếu tài nguyên | Kiểm tra cache hit, latency recall và ứng dụng |
| Dữ liệu bị xóa ở nhiều nơi | Thao tác xóa đã được sync | Dừng nguồn gây lỗi, bảo toàn bằng chứng, khôi phục backup/snapshot |
| Giá Azure cao hơn dự toán | Capacity, transactions, tiering recall, redundancy hoặc backup | Cost Management, metrics và quy tắc pricing |

### 16.1. Quy trình chẩn đoán từng bước

Khi file không xuất hiện ở server B:

1. **Xác nhận phạm vi:** file nằm trong đường dẫn server endpoint của server A?
2. **Xác nhận nguồn:** file đã lưu hoàn tất, không đang bị ứng dụng khóa hoặc tạo dưới loại dữ liệu không hỗ trợ?
3. **Xác nhận server A:** agent online, registered đúng Sync Service, endpoint Healthy?
4. **Xác nhận cloud endpoint:** file đã xuất hiện trong Azure file share chưa?
5. **Xác nhận server B:** agent online, cùng sync group, đúng folder và không có error/conflict?
6. **Xác nhận quyền:** NTFS ACL và share permission có cho người dùng xem file không?
7. **Xác nhận network:** DNS/TLS/HTTPS của server B có truy cập endpoint dịch vụ không?
8. **Xác nhận backlog:** có lượng file quá lớn, tiering/recall hoặc giới hạn service không?
9. **Đọc log chi tiết:** lấy mã lỗi, thời điểm và các sự kiện có thể liên quan.
10. **Khắc phục nguyên nhân và thử lại:** chỉ làm các thay đổi được hỗ trợ, kiểm tra nội dung và timestamps.

Tránh đổi tên/xóa hàng loạt file trong lúc cố sửa sync nếu chưa có backup và chưa hiểu cách dịch vụ xử lý thay đổi.

### 16.2. Khi cloud endpoint không cập nhật

Nếu file được sửa trực tiếp trên Azure file share và server endpoint không thấy ngay:

- Xác minh đúng share là cloud endpoint của sync group.
- Xác minh thay đổi cloud hợp lệ và không bị lỗi quyền.
- Kiểm tra thời điểm chạy cloud change detection gần nhất.
- Nếu yêu cầu nghiệp vụ cần nhanh hơn, xem lệnh/cơ chế **Invoke-AzStorageSyncChangeDetection** theo tài liệu và module PowerShell hiện hành.
- Đừng gọi job phát hiện liên tục với thư mục rất lớn mà chưa xem giới hạn và chi phí.

Azure File Sync không được thiết kế để phát hiện mọi thay đổi cloud-side ở độ trễ bằng không.

## 17. Kiến trúc triển khai: hiệu năng, giới hạn và chi phí

### 17.1. Kích thước dữ liệu và số lượng file

Khối lượng 10 TB gồm vài trăm file lớn có đặc điểm rất khác 10 TB gồm hàng chục triệu file nhỏ. Khi lập kế hoạch:

- Đo số lượng file/thư mục, độ sâu đường dẫn và kích thước trung bình.
- Xác định tỷ lệ thay đổi theo giờ và số thao tác metadata.
- Kiểm tra giới hạn số endpoint, file, sync group và kiểu file system theo dịch vụ hiện hành.
- Tính thời gian initial sync thực tế và lượng dữ liệu phải gửi qua WAN.
- Chừa dung lượng/IOPS phù hợp cho việc mở file, scan, backup và cloud tiering.
- Có kế hoạch cho thời điểm dữ liệu tăng nhanh.

Không lấy tổng dung lượng TB là chỉ số duy nhất để đánh giá tốc độ đồng bộ.

### 17.2. Chi phí

| Thành phần | Chi phí/tác động có thể có |
|---|---|
| Azure Files | Dung lượng lưu trữ, mô hình Standard/Premium, redundancy và các giao dịch |
| Azure File Sync | Thành phần dịch vụ tính phí theo mô hình hiện hành, bao gồm số server đã kết nối nếu áp dụng |
| Network | Truyền dữ liệu, egress, VPN/ExpressRoute, proxy hoặc Private Endpoint theo cấu hình |
| Cloud tiering | Cache và recall thay đổi lượng truy cập vào Azure Files; có thể tạo giao dịch/dữ liệu qua mạng |
| Backup/snapshot | Dung lượng bản sao/retention, tác vụ phục hồi và mức sử dụng storage |
| Windows file server | VM/hardware, license, disk, bảo trì và tài nguyên vận hành |
| Logging/monitoring | Ingestion, retention, cảnh báo và hệ thống phân tích log |

Chi phí cụ thể có thể thay đổi theo vùng triển khai, model billing Azure Files, tier, số máy chủ và tần suất truy cập. Hãy dùng Azure Pricing Calculator và bảng giá dịch vụ hiện hành, không mặc định tiering luôn làm tổng hóa đơn rẻ hơn.

### 17.3. Khi nào không nên dùng Azure File Sync?

Không nên mặc định chọn File Sync khi:

- Hệ thống cần **distributed file lock** mạnh và ghi đa điểm theo thời gian thực.
- Dữ liệu chủ yếu là database hoặc file ứng dụng với random I/O và latency cực thấp.
- Máy nguồn không phải Windows Server được hỗ trợ.
- Mạng đến Azure liên tục mất nhưng mọi file phải sẵn sàng ngay tại mọi thời điểm trong khi tiering được bật mạnh.
- Chỉ cần một share cloud dùng trực tiếp và không cần Windows Server cache.
- Dữ liệu phải ở một vị trí không thể phù hợp với region/replication Azure Files được chọn.

Lúc này cần đánh giá Azure Files trực tiếp, Azure NetApp Files, Azure Managed Disks, ứng dụng cộng tác chuyên dụng hoặc giải pháp replication/backup khác theo workload thực tế.

## 18. Vận hành, thay đổi và rollback

### 18.1. Quy trình thay đổi chuẩn

1. Xác định owner dữ liệu, file server, Storage Account và sync group.
2. Ghi lại endpoint paths, ACL, quota, cloud tiering policy và trạng thái health.
3. Có backup/snapshot gần nhất và đã thử restore.
4. Thử thay đổi trong lab với dữ liệu không nhạy cảm.
5. Triển khai từng server endpoint, không thêm mọi chi nhánh cùng lúc nếu chưa đo initial sync.
6. Theo dõi dữ liệu từ server → cloud → server, kiểm tra file cụ thể.
7. Xác minh quyền truy cập, độ trễ và trải nghiệm người dùng.
8. Ghi lại thay đổi, chỉ số trước/sau và phương án phục hồi.

### 18.2. Gỡ endpoint không phải là xóa dữ liệu

Việc bỏ một server endpoint, ngừng sync, gỡ agent hoặc xóa sync group có thể có điều kiện và quy trình dọn dữ liệu riêng, **đặc biệt khi có tiered files**.

Trước khi ngừng Azure File Sync trên một máy chủ:

- Xác định file nào đã tiered và còn cần recall.
- Đảm bảo dữ liệu phải giữ đã được hydrate/khôi phục theo quy trình hỗ trợ nếu máy chủ sẽ tiếp tục chạy độc lập.
- Sao lưu dữ liệu và cấu hình SMB/ACL.
- Thực hiện quy trình offboarding của Azure File Sync, không chỉ xóa thư mục.
- Xác minh các server endpoint khác vẫn hoạt động và cloud endpoint giữ dữ liệu đúng.

Không xóa Storage Account hoặc Azure file share khi vẫn còn sync group/server endpoint cần dữ liệu đó.

### 18.3. Sau khi hoàn tất lab

Chỉ xóa những tài nguyên **được tạo riêng cho lab** và không được các workload khác sử dụng. Cần kiểm tra:

1. Dữ liệu có cần giữ hoặc xuất ra nơi khác không.
2. Server endpoint đã được offboard theo hướng dẫn chưa.
3. Registered server và sync group có còn dependency không.
4. Azure file share có chứa dữ liệu thật không.
5. Backup/retention và chi phí còn phát sinh không.

Không dùng lệnh xóa resource group hàng loạt trong tài liệu bài học vì một resource group có thể chứa tài nguyên ngoài phạm vi thực hành.

## 19. Checklist đưa Azure File Sync vào production

- [ ] Mục tiêu nghiệp vụ rõ: cache cục bộ, đồng bộ đa site hay migration.
- [ ] Đã xác nhận Windows Server/agent và file system được hỗ trợ.
- [ ] Đã kiểm tra số file, loại file, dung lượng, ACL và ứng dụng đang giữ file.
- [ ] Storage Account/Azure file share có region, redundancy, quota và performance tier phù hợp.
- [ ] Storage Sync Service và cloud endpoint đúng region và đúng share.
- [ ] Một sync group có cấu trúc cloud endpoint/server endpoints hợp lệ.
- [ ] Server registration, quyền Azure và quyền Windows đã phân tách phù hợp.
- [ ] Firewall/DNS/TLS/HTTPS outbound được cấu hình; Private Endpoint được kiểm tra nếu sử dụng.
- [ ] Share-level permissions, NTFS ACL, danh tính và SMB path đã được kiểm thử.
- [ ] Cloud tiering có policy đúng nhu cầu và đã thử recall.
- [ ] Có phương án khi server offline, tiered file không recall được và sync backlog kéo dài.
- [ ] Đã thử sync hai chiều và phát hiện xung đột bằng bộ file thử nghiệm.
- [ ] Không giả định multi-server file locks được đồng bộ.
- [ ] Đã bật backup/snapshot và thực hành restore file bị xóa nhầm.
- [ ] Đã có runbook cho hỏng server, ransomware và sự cố mạng/region.
- [ ] Có alert cho agent offline, sync errors, storage quota và free space.
- [ ] Chi phí và tăng trưởng dữ liệu đã được dự toán.
- [ ] Quy trình cập nhật agent và offboarding endpoint đã được xác định.

## 20. Bài tập thực hành

### Bài 1: Vẽ mô hình một văn phòng

Doanh nghiệp có một file server Windows chứa 2 TB tài liệu, muốn giữ SMB share nội bộ và sao chép dữ liệu lên Azure. Hãy vẽ sơ đồ gồm Storage Account, Azure Files, Storage Sync Service, sync group, cloud endpoint, registered server và server endpoint. Giải thích vì sao Storage Sync Service không phải ổ đĩa chứa nội dung file.

### Bài 2: Thiết kế hai chi nhánh

Hai file server ở HCM và Hà Nội cần dùng chung thư mục Projects. Hãy:

1. Chọn cấu trúc sync group.
2. Xác định hai server endpoint.
3. Mô tả cách một file từ HCM đến Hà Nội.
4. Chỉ ra tình huống chỉnh sửa đồng thời gây conflict.
5. Đề xuất cách hạn chế sửa đồng thời với tài liệu nhạy cảm.

### Bài 3: Lựa chọn chính sách cloud tiering

Chi nhánh có đĩa 2 TB và dữ liệu 5 TB, trong đó phần lớn ít được truy cập. Người dùng cần mở nhanh các tài liệu trong 30 ngày gần nhất. Hãy lựa chọn sơ bộ volume free space và date policy, trình bày rủi ro khi Internet bị gián đoạn và cách kiểm tra recall performance.

Không cần tự suy diễn rằng tỷ lệ dữ liệu cũ có thể tier chính xác 100%; hãy dự trù cache, metadata, growth và thao tác mở file.

### Bài 4: Chẩn đoán file không xuất hiện

Một người dùng lưu **report.docx** ở máy A. File không xuất hiện ở B sau một thời gian. Viết bảng kiểm tra theo thứ tự: path, sync health A, Azure file share, sync health B, conflict, ACL, network và event logs.

### Bài 5: Phục hồi sau xóa nhầm

Một thư mục chứa 200 tệp bị xóa từ SMB share và sau đó đồng bộ sang Azure. Hãy giải thích vì sao redundancy không cứu được file, những thành phần backup/snapshot nào cần bật trước và trình tự phục hồi an toàn đến thư mục tạm.

### Bài 6: Lập kế hoạch migration

Một file server có 8 TB dữ liệu và 4 triệu file nhỏ. Hãy lập kế hoạch pilot, đo initial sync, giới hạn băng thông, đánh giá ACL, đào tạo người dùng và các mốc cutover sang hệ thống mới. Giải thích tại sao không nên chỉ xem dung lượng TB.

### Câu hỏi tự kiểm tra

1. Cloud endpoint khác server endpoint ở điểm nào?
2. Một sync group có bao nhiêu cloud endpoint?
3. Azure File Sync có tự tạo SMB share và share permissions trên máy chủ mới không?
4. Tại sao file tạo trực tiếp trên Azure file share không nhất thiết xuất hiện ngay ở Windows Server?
5. Cloud tiering khác Azure Blob Archive như thế nào?
6. Nếu một file đã tiered và máy chủ mất kết nối Azure, điều gì có thể xảy ra khi người dùng mở file?
7. Azure File Sync có đồng bộ file locks giữa hai server endpoint không?
8. Vì sao cần backup ngay cả khi storage account đã dùng GRS hoặc GZRS?
9. Khi tạo file server thay thế, ngoài dữ liệu bạn phải tái tạo những cấu hình nào?
10. Mạng SMB của client và mạng HTTPS của Azure File Sync agent khác nhau ra sao?

## 21. Tài liệu tham khảo

- [Azure File Sync overview — Microsoft Learn](https://learn.microsoft.com/azure/storage/file-sync/file-sync-introduction)
- [Plan for an Azure File Sync deployment](https://learn.microsoft.com/azure/storage/file-sync/file-sync-planning)
- [Deploy Azure File Sync](https://learn.microsoft.com/azure/storage/file-sync/file-sync-deployment-guide)
- [Cloud tiering overview](https://learn.microsoft.com/azure/storage/file-sync/file-sync-cloud-tiering-overview)
- [Troubleshoot Azure File Sync](https://learn.microsoft.com/azure/storage/file-sync/file-sync-troubleshoot)
- [Azure Files overview](https://learn.microsoft.com/azure/storage/files/storage-files-introduction)
- [Azure Files networking considerations](https://learn.microsoft.com/azure/storage/files/storage-files-networking-overview)
- [Azure Backup for Azure Files overview](https://learn.microsoft.com/azure/backup/azure-file-share-backup-overview)
- [Azure Files pricing](https://azure.microsoft.com/pricing/details/storage/files/)

