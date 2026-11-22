# Azure Files với SMB và NFS

Trong hệ sinh thái Microsoft Azure, không phải ứng dụng nào cũng lưu dữ liệu dưới dạng object trong Blob Storage hoặc dùng ổ đĩa gắn riêng vào máy ảo. Nhiều ứng dụng cần một **thư mục dùng chung** mà nhiều máy chủ hay container có thể truy cập bằng đường dẫn tệp quen thuộc. Ví dụ: một nhóm nhân viên cần mở tài liệu qua ổ mạng trên Windows; nhiều máy Linux cần đọc một thư mục tài nguyên chung; hoặc ứng dụng được chuyển từ trung tâm dữ liệu lên Azure vẫn đang sử dụng giao diện file system.

**Azure Files** cung cấp các file share được Azure quản lý, truy cập qua những giao thức chia sẻ tệp phổ biến: **SMB (Server Message Block)** và **NFS (Network File System)**, tùy cấu hình được hỗ trợ. Bạn không phải tự duy trì file server, hệ điều hành và cụm máy lưu trữ cho các file share này. Tuy nhiên, quyền truy cập, mạng, hiệu năng, sao lưu và chi phí vẫn cần được thiết kế cẩn thận.

Bài học thuộc chương **Lưu trữ tệp và đĩa** của mô-đun CLOUD_PROVIDERS_AZURE, kết nối Azure Files với resource group, Storage Account, Microsoft Entra ID, mạng ảo, private endpoint, giám sát và kiểm soát chi phí khi vận hành ứng dụng trên Microsoft Azure.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Azure Files là gì và phân biệt với Azure Blob Storage, Managed Disks và Azure NetApp Files.
2. Lựa chọn **SMB** hoặc **NFS 4.1** theo hệ điều hành, mô hình xác thực và ứng dụng.
3. Thiết kế Storage Account, file share, mạng riêng, DNS và quyền truy cập phù hợp.
4. Tạo và kiểm tra file share bằng Azure CLI; hiểu các bước mount share từ Windows và Linux.
5. Phân biệt quyền Azure RBAC, quyền tệp SMB/NTFS và UID/GID của NFS.
6. Đánh giá hiệu năng, tính sẵn sàng, backup/snapshot, bảo mật, giám sát và chi phí.
7. Khắc phục các lỗi thường gặp như không kết nối được cổng 445/2049, sai DNS, thiếu quyền hoặc lỗi hiệu năng.

Các ví dụ sử dụng tên tài nguyên minh họa và không được thực thi tự động. Một số lựa chọn account, tier, region và protocol phụ thuộc khả năng hỗ trợ tại thời điểm triển khai; hãy đối chiếu tài liệu Microsoft cho môi trường của bạn.

## 2. Azure Files là gì?

### 2.1. File share được quản lý trên Azure

Mô hình cơ bản:

~~~text
Azure subscription
└── Resource group: rg-files-demo
    └── Storage Account: <storage-account>
        ├── File share: teamdocs   (SMB)
        └── File share: ...        (giao thức và tier theo hỗ trợ)
~~~

**Storage Account** là tài nguyên Azure chứa cấu hình mạng, bảo mật, chính sách dự phòng và các dịch vụ lưu trữ được hỗ trợ. **File share** là đơn vị chia sẻ tệp bên trong account; thư mục và file nằm trong share.

Azure Files có thể được truy cập:

- Qua **SMB** từ client hoặc dịch vụ hỗ trợ SMB, thường gặp trên Windows và cũng có trên Linux.
- Qua **NFS 4.1** trong các kịch bản được hỗ trợ, đặc biệt hữu ích cho workload Linux/Unix.
- Qua API, SDK hoặc công cụ quản lý tương ứng để thao tác file share hoặc dữ liệu ở những kịch bản được hỗ trợ; không nên suy ra mọi chức năng đều giống giữa SMB và NFS.

Ví dụ về đường dẫn:

~~~text
SMB UNC:
  \\stfilesdemo001.file.core.windows.net\teamdocs

NFS export:
  stnfsdemo001.file.core.windows.net:/stnfsdemo001/appsdata
~~~

Các ví dụ này chỉ có thể dùng sau khi tài nguyên, DNS, mạng và quyền truy cập được cấu hình chính xác. Chúng không phải địa chỉ file server do người dùng tự quản trị.

### 2.2. Azure Files so với các dịch vụ khác

| Nhu cầu | Dịch vụ thường phù hợp | Vì sao |
|---|---|---|
| Ổ mạng/thư mục dùng chung cho nhiều máy Windows | Azure Files với SMB | Sử dụng giao thức SMB quen thuộc |
| Thư mục chung cho ứng dụng Linux hỗ trợ NFS | Azure Files với NFS | Hỗ trợ mount file share qua NFS 4.1 |
| Lưu object như ảnh, video, bản sao lưu xuất qua HTTP/SDK | Azure Blob Storage | Truy cập kiểu object, không mặc định là file share SMB/NFS |
| Ổ hệ điều hành hoặc data disk của một Azure VM | Azure Managed Disks | Mô hình block storage gắn với VM |
| Workload NFS/SMB cần tính năng hoặc đặc tính hiệu năng chuyên biệt | Azure NetApp Files, sau khi đánh giá | Dịch vụ khác với Azure Files, có thiết kế và mô hình giá riêng |
| File server Windows tại chỗ cần đồng bộ và cache với cloud | Azure Files SMB kết hợp Azure File Sync khi đáp ứng điều kiện | Phù hợp kịch bản hybrid có Windows Server làm điểm truy cập |

Không xem Azure Files là lựa chọn duy nhất cho mọi workload: hệ thống database cần block storage, transaction và độ trễ rất thấp có thể không phù hợp với việc đặt data file trên một share mạng. Luôn dựa trên yêu cầu ứng dụng và hỗ trợ chính thức của nhà cung cấp phần mềm.

## 3. SMB và NFS khác nhau như thế nào?

### 3.1. Bảng so sánh giao thức

| Khía cạnh | SMB trên Azure Files | NFS trên Azure Files |
|---|---|---|
| Giao thức tiêu biểu | SMB 3.x, theo client và cấu hình được hỗ trợ | NFS 4.1 |
| Client thường gặp | Windows; Linux/macOS hoặc môi trường khác khi hỗ trợ SMB | Linux/Unix và workload dùng NFS phù hợp |
| Kiểu đường dẫn | UNC: \\account.file.core.windows.net\share | Export: account.file.core.windows.net:/account/share |
| Cổng mạng dữ liệu | TCP 445 | TCP 2049 |
| Xác thực/truy cập | Account key hoặc identity-based SMB authentication theo khả năng hỗ trợ | Chủ yếu dựa vào network controls và quyền POSIX UID/GID của mô hình NFS được hỗ trợ |
| Quyền ở cấp file | Windows/NTFS ACL trong kịch bản identity-based SMB | POSIX owner, group, mode và các cơ chế NFS được hỗ trợ |
| Mã hóa đường truyền | SMB 3.x hỗ trợ mã hóa khi client/cấu hình phù hợp | Không mặc định coi NFS 4.1 là kết nối được mã hóa ở tầng truyền tải; cần xem giải pháp bảo vệ mạng và tính năng hiện hành |
| Kiểu ứng dụng | Home directories, share tài liệu, ứng dụng dùng UNC | Dữ liệu chung cho ứng dụng Linux, thư mục làm việc, workload HPC hoặc container khi thích hợp |
| Tương thích tính năng | Có các lựa chọn identity và Azure File Sync theo điều kiện | Tập tính năng riêng; phải xác minh snapshot/backup/management và tier trước khi thiết kế |

**Một file share không tự động đồng thời là share SMB và NFS.** Giao thức được xác định khi tạo share theo mô hình sản phẩm; không thể giả định việc đổi giao thức chỉ là sửa một trường cấu hình. Nếu muốn phục vụ cả Windows và Linux, cân nhắc SMB cho cả hai khi ứng dụng cho phép, hoặc thiết kế những share và luồng đồng bộ dữ liệu riêng nếu cần NFS.

### 3.2. Nên chọn giao thức nào?

**Chọn SMB khi** bạn cần ổ đĩa mạng trên Windows, tích hợp với danh tính doanh nghiệp, làm việc với ACL kiểu Windows hoặc muốn dùng mô hình Azure File Sync cho file server Windows Server hỗ trợ.

**Chọn NFS khi** ứng dụng Linux đã được thiết kế để mount NFS 4.1, dựa trên UID/GID/POSIX permission, và có đường mạng riêng đáng tin cậy tới Azure. Với workload phụ thuộc nhiều vào file locking và semantics POSIX, phải kiểm thử tính tương thích thực tế.

**Không chọn chỉ theo tên hệ điều hành.** Linux vẫn có thể mount SMB; ứng dụng chạy container vẫn có thể cần SMB; còn một ứng dụng đa nền tảng có thể buộc phải dùng giao thức mà nhà cung cấp phần mềm chứng nhận.

## 4. Kiến trúc thành phần và luồng truy cập

### 4.1. Một kiến trúc hub-spoke có mạng riêng

~~~mermaid
flowchart LR
    W["Windows VM / client SMB"] --> V["VNet hoặc mạng hybrid"]
    L["Linux VM / ứng dụng NFS"] --> V
    O["On-premises"] --> H["VPN / ExpressRoute"]
    H --> V
    V --> P["Private Endpoint cho file"]
    P --> A["Azure Storage Account"]
    A --> S["SMB File Share"]
    A --> N["NFS File Share\nkhi account/tier hỗ trợ"]
    D["Private DNS / DNS forwarder"] -.-> V
~~~

Sơ đồ nêu hai kiểu share như những khái niệm có thể có trong hệ thống. Không khẳng định mọi SKU hoặc loại Storage Account đều hỗ trợ cả hai trong một account. Khi thiết kế, kiểm tra giới hạn cho protocol, account kind, tier và region.

Để client dùng private endpoint:

1. Client kết nối tới VNet qua cùng mạng ảo, peering, VPN hoặc ExpressRoute phù hợp.
2. DNS trả về địa chỉ **private** của endpoint cho tên account.file.core.windows.net.
3. NSG, firewall, route và chính sách storage account cho phép kết nối.
4. Client mở đúng cổng SMB hoặc NFS và vượt qua bước xác thực/kiểm tra quyền tương ứng.

**Private Endpoint không tự tạo quyền đọc dữ liệu.** Nó điều khiển đường mạng đến dịch vụ; quyền truy cập file vẫn được quyết định bởi cơ chế SMB hoặc NFS. Ngược lại, có quyền đọc share nhưng không có đường mạng/DNS hợp lệ vẫn không mount được.

### 4.2. Vùng lỗi và tính sẵn sàng

Azure Files là dịch vụ managed, nhưng vẫn cần quyết định:

- Storage Account đặt ở region nào, gần client và ứng dụng nào?
- Dữ liệu cần tính sẵn sàng trong một region hay chiến lược phục hồi giữa các region?
- SKU và giao thức đang dùng hỗ trợ lựa chọn redundancy nào?
- Ứng dụng có xử lý được kết nối ngắt tạm thời, stale handle hoặc lỗi retry không?
- Có cần backup độc lập và thử restore định kỳ không?

Các mô hình LRS, ZRS, GRS/GZRS và các biến thể có phạm vi hỗ trợ khác nhau theo loại account, giao thức, tier và khu vực. Không mặc định NFS và SMB đều có mọi lựa chọn redundancy. Bảo vệ bằng redundancy cũng **không thay thế backup** trước xóa nhầm, ransomware hoặc thao tác sai.

## 5. Chọn loại Storage Account và mức hiệu năng

### 5.1. Hai nhóm quyết định: protocol và mô hình tính phí

Đầu tiên xác định giao thức. Sau đó chọn tier/model hiệu năng phù hợp:

- **HDD/standard file shares:** có các lựa chọn theo dung lượng, giao dịch và/hoặc cấp phát theo mô hình sản phẩm. Phù hợp khi độ trễ và IOPS không phải yêu cầu quá cao.
- **SSD/premium file shares:** phục vụ nhu cầu IOPS, throughput và độ trễ tốt hơn theo cấu hình hỗ trợ; chi phí và lượng tài nguyên được cấp phát cần theo dõi cẩn thận.
- **Mô hình provisioned:** hiệu năng/công suất có thể gắn với dung lượng hoặc các thông số cấp phát. Việc cấp phát quá mức so với nhu cầu thực tế dẫn tới lãng phí.
- **Mô hình pay-as-you-go:** chi phí có thể bao gồm dung lượng, giao dịch, truyền dữ liệu và các hạng mục khác tùy tier.

Tên tier/model và các khả năng hỗ trợ NFS có thể phát triển theo thời gian. Khi thực hành, hãy chọn account kind và SKU theo tài liệu hiện hành của **Azure Files**, thay vì áp một ví dụ CLI của SMB HDD cho NFS.

### 5.2. Bảng lựa chọn theo workload

| Workload | Đặc điểm | Khuyến nghị khởi đầu |
|---|---|---|
| Chia sẻ tài liệu Office cho người dùng Windows | File nhỏ/vừa, cần danh tính và ACL | SMB, identity-based authentication, đo tải thực tế |
| Máy chủ ứng dụng Windows dùng thư mục chung | Nhiều thao tác mở/đóng file, lock | SMB, kiểm thử phần mềm và latency |
| Ứng dụng Linux đọc model/tài nguyên chung | POSIX UID/GID, nhiều máy Linux | NFS 4.1 trên tier/account được hỗ trợ |
| Xử lý dữ liệu có lượng I/O lớn | Nhiều thao tác nhỏ hoặc throughput cao | Đo IOPS/throughput, cân nhắc SSD hoặc dịch vụ khác |
| Lưu file ít sử dụng | Dung lượng quan trọng hơn độ trễ | Đánh giá HDD/cost model hoặc Blob tùy cách truy cập |
| File server on-premises đang dùng SMB | Muốn cache tại chỗ và đồng bộ cloud | SMB với Azure File Sync nếu đáp ứng điều kiện |

Nên tạo workload proof-of-concept trước khi chuyển ứng dụng có yêu cầu file-locking, dung lượng lớn hoặc sử dụng nhiều metadata operation.

## 6. Bảo mật và xác thực SMB

### 6.1. Ba lớp cần hiểu

Với SMB, thường có ba lớp khác nhau:

1. **Mạng:** client có kết nối được đến account qua cổng 445 và đường mạng được cho phép không?
2. **Xác thực:** client chứng minh danh tính bằng phương thức mà storage account/share hỗ trợ như danh tính doanh nghiệp hoặc account key.
3. **Phân quyền:** danh tính có quyền trên share và file/thư mục cụ thể hay không?

Mở cổng TCP 445 không có nghĩa được đọc file. Ngược lại, một người đã được cấp role nhưng DNS đang trỏ sai hoặc ISP chặn cổng 445 vẫn không sử dụng được share.

### 6.2. Identity-based SMB authentication

Azure Files có các hình thức tích hợp danh tính tùy điều kiện:

- **Active Directory Domain Services (AD DS):** phù hợp với tổ chức có domain Windows truyền thống/hybrid.
- **Microsoft Entra Domain Services:** dùng khả năng domain được Azure quản lý khi môi trường đáp ứng yêu cầu.
- **Microsoft Entra Kerberos:** hỗ trợ một số mô hình danh tính hiện đại/hybrid theo điều kiện hệ điều hành, domain và cách triển khai.

Không phải chỉ cần gán một role Azure RBAC là client Windows bất kỳ có thể tự đăng nhập SMB. Danh tính lưu trữ, Kerberos ticket, trạng thái join, DNS, đồng bộ định danh và phiên bản client cần được cấu hình đầy đủ.

Trong thiết kế identity-based SMB, hai mức quyền thường đều quan trọng:

| Phạm vi | Cơ chế | Ý nghĩa |
|---|---|---|
| Share-level | Các role dữ liệu SMB của Azure, ví dụ Storage File Data SMB Share Reader/Contributor theo quyền cần thiết | Quyền bước đầu để truy cập share |
| Directory/file-level | NTFS ACL và nhóm/người dùng | Quyền thực tế trên thư mục, file và thao tác cụ thể |

Cấp share-level role rộng không tự động loại bỏ mọi hạn chế NTFS ACL. Một người có quyền vào share nhưng không có quyền trong thư mục vẫn có thể gặp Access denied.

### 6.3. Account key và vì sao phải thận trọng

Storage Account key là một phương thức truy cập mạnh. Trong một số kịch bản SMB, có thể dùng account name/key để mount mà không cần tích hợp danh tính domain. Tuy nhiên:

- Key có phạm vi quyền rộng đối với dữ liệu liên quan trong account.
- Mất key có thể dẫn tới truy cập dữ liệu không mong muốn.
- Key dễ bị lộ nếu viết trực tiếp trong script, command history, log, YAML hoặc repository.
- Việc xoay key có thể làm gián đoạn những client đang sử dụng nếu không có kế hoạch.

Ưu tiên identity-based SMB authentication khi phù hợp. Nếu bắt buộc dùng key cho lab hoặc một ứng dụng tương thích hạn chế, lưu bằng secret management được phê duyệt, giới hạn người sử dụng và lập kế hoạch xoay/thu hồi. Không đưa giá trị key thật vào ví dụ hoặc tài liệu chia sẻ.

### 6.4. Encryption và kiểm soát truy cập

Azure Storage cung cấp mã hóa dữ liệu lưu trên dịch vụ. Đối với SMB, nên sử dụng phiên bản giao thức và cấu hình hỗ trợ mã hóa trên đường truyền theo yêu cầu bảo mật. Vẫn nên ưu tiên kết nối qua mạng riêng khi có thể.

Các thiết lập như minimum TLS version của Storage Account liên quan endpoint giao tiếp dùng TLS, **không thay thế cấu hình bảo mật của phiên SMB**. Không lấy việc đã đặt TLS 1.2 cho account làm bằng chứng duy nhất rằng mọi mount SMB đang mã hóa đúng.

## 7. Bảo mật và quyền truy cập NFS

### 7.1. NFS 4.1 và POSIX identity

Với share NFS, ứng dụng Linux thường xác định quyền thông qua **UID, GID, owner/group và mode bits** của tệp. Ví dụ:

~~~bash
id
ls -ln /mnt/appsdata
stat /mnt/appsdata/example.txt
~~~

Nếu một file thuộc UID 1001 và GID 2001, máy khác dùng NFS cần có quy ước ánh xạ danh tính phù hợp để hành vi quyền được nhất quán. Hai máy có cùng tên tài khoản Linux nhưng UID khác nhau có thể gặp lỗi hoặc quyền không như kỳ vọng.

Đừng giả định vai trò Azure RBAC được gán cho người dùng Entra sẽ tự động kiểm soát thao tác đọc/ghi tệp của mount NFS. Azure RBAC bảo vệ nhiều thao tác quản trị tài nguyên, còn quyền truy cập dữ liệu NFS cần được thiết kế theo mô hình protocol và network controls.

### 7.2. Mạng là lớp bảo vệ thiết yếu

NFS không nên được triển khai như dịch vụ file share không kiểm soát trên Internet. Khi dùng Azure Files NFS:

1. Chọn account/tier và kiểu network access hỗ trợ NFS.
2. Tạo private endpoint hoặc kết nối mạng được sản phẩm hỗ trợ để client ở mạng tin cậy truy cập.
3. Cấu hình DNS giải account.file.core.windows.net về endpoint phù hợp, đặc biệt khi kết nối hybrid.
4. Chỉ mở TCP 2049 từ những subnet/workload cần thiết.
5. Sử dụng network segmentation, NSG/firewall và kiểm toán thay đổi chính sách mạng.
6. Xem xét quyền POSIX, quy tắc UID/GID và những tính năng như root squash theo hỗ trợ hiện hành nếu có.

**Không tự coi NFS 4.1 là dữ liệu được mã hóa trên đường truyền.** Giao thức NFS khác SMB về bảo mật transport. Nếu dữ liệu yêu cầu mã hóa in transit, cần đánh giá tính năng mã hóa NFS được Azure hỗ trợ, network encryption hoặc phương án thích hợp theo yêu cầu tổ chức; không chỉ dựa vào mã hóa at rest.

Một số cấu hình liên quan secure transfer requirement và loại share có hạn chế riêng với NFS. Không nên bật/tắt thiết lập bảo mật theo ví dụ cũ trước khi kiểm tra tài liệu phiên bản dịch vụ đang áp dụng.

### 7.3. UID/GID và quyền ghi trong ứng dụng container

Nếu ứng dụng chạy trong container/Kubernetes, hãy xem UID/GID mà process thực sự dùng, chứ không chỉ username trong image. Một ứng dụng chạy bằng UID 1000 trong pod nhưng thư mục NFS chỉ cho UID 2000 có quyền ghi sẽ thất bại mặc dù mount thành công.

Kiểm tra securityContext, runAsUser, runAsGroup và fsGroup theo cách được NFS client/CSI driver và môi trường hỗ trợ. Không dùng chmod 777 rộng rãi để giải quyết lỗi quyền trong production; sửa ownership/group và quy trình provision sẽ an toàn hơn.

## 8. Thiết kế mạng: Private Endpoint, DNS và cổng kết nối

### 8.1. Private Endpoint cho Azure Files

Private Endpoint tạo một network interface với địa chỉ riêng trong VNet để kết nối tới subresource Azure Storage tương ứng. Với Azure Files, subresource thường dùng là **file**.

Mô hình:

~~~text
Windows/Linux client
    |
    | TCP 445 (SMB) hoặc TCP 2049 (NFS)
    v
Private IP của file private endpoint
    |
    v
<account>.file.core.windows.net (Azure Files)
~~~

Tên truy cập vẫn thường là account.file.core.windows.net, trong khi DNS private link đưa client đến private IP. Điều này giúp các công cụ và ứng dụng sử dụng hostname được dịch vụ hỗ trợ và kiểm tra TLS/SMB identity phù hợp.

### 8.2. DNS phải đúng cả trong Azure lẫn on-premises

Trong mô hình VNet dùng Private DNS, zone liên quan thường là:

~~~text
privatelink.file.core.windows.net
~~~

Cần link zone với VNet được phép truy vấn hoặc thiết lập DNS forwarding thích hợp nếu dùng custom DNS và các mạng on-premises. Từ một VM trong mạng dự kiến mount, có thể kiểm tra:

~~~bash
nslookup <ACCOUNT>.file.core.windows.net
~~~

Lệnh phải cho thấy địa chỉ IP phù hợp với thiết kế mạng private endpoint. Nếu client giải tên ra public IP trong khi storage account chỉ nhận private traffic, việc mount có thể thất bại dù resource ở trạng thái Succeeded.

Không khắc phục DNS bằng cách hard-code một private IP tạm thời vào cấu hình ứng dụng lâu dài. Private endpoint, tài nguyên hoặc DNS có thể thay đổi; hãy sửa zone/link/forwarding đúng nguyên nhân.

### 8.3. Kiểm tra cổng mạng

| Client/protocol | Kiểm tra | Port chính |
|---|---|---|
| Windows SMB | Test-NetConnection -Port 445 | TCP 445 |
| Linux SMB | nc -vz hoặc công cụ tương đương | TCP 445 |
| Linux NFS | nc -vz hoặc kiểm tra kết nối từ môi trường cho phép | TCP 2049 |

Ví dụ PowerShell:

~~~powershell
Test-NetConnection -ComputerName "<ACCOUNT>.file.core.windows.net" -Port 445
~~~

Ví dụ Linux:

~~~bash
nc -vz <ACCOUNT>.file.core.windows.net 2049
~~~

Việc một cổng thông báo open chỉ cho biết luồng TCP có thể đi qua, không chứng minh xác thực thành công, quyền file đúng hoặc giao thức mount tương thích. Với client ngoài Azure, một ISP hoặc firewall có thể chặn cổng 445; VPN/ExpressRoute và DNS private thường giúp thiết kế đường truy cập nhất quán hơn.

### 8.4. Kiểm tra NSG, firewall và routing hai chiều

Một client có quyền dữ liệu nhưng thất bại do:

- VNet/subnet không có route đến private endpoint.
- DNS forwarding sai hoặc không link Private DNS zone với VNet.
- NSG hoặc firewall chặn cổng 445/2049.
- Network rule của Storage Account không cho phép đường đi thực tế.
- Kết nối VPN/ExpressRoute có đường đi nhưng thiếu tuyến quay về.
- Thiết bị trung gian thay đổi hoặc lọc lưu lượng giao thức.

Khi chẩn đoán, kiểm tra theo thứ tự **DNS → TCP → xác thực/mount → thao tác file** để giảm thời gian tìm nguyên nhân.

## 9. Thực hành 1: Tạo SMB file share bằng Azure CLI

Ví dụ tạo tài nguyên SMB cho nhóm tài liệu trong môi trường thử nghiệm. Các lệnh là minh họa Bash, **không được tự động chạy**; cần quyền Azure phù hợp, subscription được chọn chính xác và dự trù chi phí.

### 9.1. Kiểm tra subscription

~~~bash
az login
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Xác nhận bạn đang ở đúng tenant/subscription trước mọi thao tác tạo tài nguyên. Nếu dùng CI/CD, ưu tiên managed identity hoặc workload identity federation thay vì hard-code account password.

### 9.2. Tạo resource group và Storage Account

Ví dụ sử dụng loại account standard cho share SMB:

~~~bash
az group create \
  --name rg-files-lab \
  --location southeastasia

az storage account create \
  --resource-group rg-files-lab \
  --name <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --location southeastasia \
  --kind StorageV2 \
  --sku Standard_LRS
~~~

Storage Account name phải tuân thủ quy tắc tên riêng: chữ thường và chữ số, duy nhất theo phạm vi áp dụng. Hãy thay placeholder bằng tên hợp lệ, chẳng hạn stfileslababc123 nếu còn khả dụng.

Lựa chọn Standard_LRS phù hợp cho ví dụ học tập SMB cơ bản, **không phải đề xuất mặc định cho production**. Cần đánh giá redundancy, chi phí, network access và mô hình Azure Files phù hợp.

### 9.3. Tạo share SMB

Azure CLI có nhóm lệnh quản lý share ở management plane:

~~~bash
az storage share-rm create \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --name teamdocs \
  --enabled-protocols SMB \
  --quota 100 \
  --output json
~~~

Lệnh trên minh họa quota 100 GiB và giao thức SMB. Tùy loại account/model, các lựa chọn quota, provisioned capacity và flag của CLI có thể khác; xem trợ giúp lệnh nếu phiên bản CLI yêu cầu cú pháp khác.

Liệt kê và xem cấu hình share:

~~~bash
az storage share-rm list \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --output table

az storage share-rm show \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_STORAGE_ACCOUNT_NAME> \
  --name teamdocs \
  --output json
~~~

**Tạo share chưa có nghĩa có thể mount ngay.** Bạn còn cần cấu hình networking/Private Endpoint theo thiết kế và chọn phương thức xác thực SMB.

### 9.4. Mount trên Windows bằng danh tính doanh nghiệp

Giả sử quản trị viên đã:

- Cấu hình identity-based SMB authentication cho account.
- Cấp share-level permission thích hợp.
- Cấu hình NTFS ACL hoặc quyền thư mục phù hợp.
- Đảm bảo client đăng nhập bằng danh tính tương thích và có Kerberos theo mô hình triển khai.
- Thiết lập DNS và đường mạng tới TCP 445.

Trên máy Windows client:

~~~powershell
$account = "<UNIQUE_STORAGE_ACCOUNT_NAME>"
$server = "$account.file.core.windows.net"
Test-NetConnection -ComputerName $server -Port 445

$unc = "\\$server\teamdocs"
net use Z: $unc /persistent:yes
~~~

Sau khi mount, người dùng có thể truy cập Z:\ như một ổ mạng và thử tạo file trong thư mục mà mình được cấp quyền ghi. Lệnh net use không tự cấu hình danh tính: nếu chưa có domain/Entra Kerberos và quyền phù hợp, quá trình xác thực sẽ thất bại.

Để bỏ mapping được tạo cho bài thực hành:

~~~powershell
net use Z: /delete
~~~

Hành động này chỉ tháo mapping trên client, không xóa file share Azure.

### 9.5. Mount SMB trên Linux khi cần

Linux có thể mount Azure Files SMB bằng CIFS client nếu kernel, cifs-utils, DNS và phương thức xác thực phù hợp. Trong môi trường đã cấu hình Kerberos, một mẫu lệnh minh họa là:

~~~bash
sudo mkdir -p /mnt/teamdocs

sudo mount -t cifs \
  //<ACCOUNT>.file.core.windows.net/teamdocs \
  /mnt/teamdocs \
  -o vers=3.1.1,sec=krb5
~~~

Lệnh yêu cầu ticket Kerberos và cấu hình client phù hợp; không phải lúc nào cũng hoạt động nguyên trạng trên VM Linux chưa tích hợp domain. Với phương án account key, cần cơ chế credentials file được bảo vệ chặt và quy trình xoay key; không đưa key vào command line hoặc lịch sử shell.

## 10. Thực hành 2: Tạo và mount share NFS 4.1

### 10.1. Chọn loại account hỗ trợ NFS

Một ví dụ phổ biến cho NFS sử dụng Storage Account dành cho Azure Files SSD/premium. Trước khi tạo, xác minh loại account, tier, region và các yêu cầu network/NFS hiện hành có hỗ trợ đúng kịch bản.

~~~bash
az storage account create \
  --resource-group rg-files-lab \
  --name <UNIQUE_NFS_ACCOUNT_NAME> \
  --location southeastasia \
  --kind FileStorage \
  --sku Premium_LRS
~~~

Đây là ví dụ cấu hình, không bảo đảm mọi account/tier mới đều cần hoặc chỉ chấp nhận cùng lựa chọn SKU. Các mẫu provisioned mới có thể có tham số khác theo phiên bản Azure CLI. Hãy xác nhận điều kiện hỗ trợ trước khi thao tác.

### 10.2. Tạo share NFS

~~~bash
az storage share-rm create \
  --resource-group rg-files-lab \
  --storage-account <UNIQUE_NFS_ACCOUNT_NAME> \
  --name appsdata \
  --enabled-protocols NFS \
  --quota 100 \
  --output json
~~~

Nếu lệnh bị từ chối, cần phân biệt:

- Account kind/tier không hỗ trợ NFS.
- Vùng triển khai hoặc quota không phù hợp.
- Secure transfer/network access settings không tương thích với loại giao thức đang chọn.
- CLI/API version hoặc tham số của lệnh không khớp sản phẩm hiện tại.
- Principal không có quyền tạo file share ở management plane.

Không tự vô hiệu hóa bảo mật hay mở account ra Internet chỉ để vượt qua lỗi tạo NFS. Đối chiếu yêu cầu sản phẩm và tạo đường truy cập riêng đúng quy trình.

### 10.3. Cấu hình mạng riêng và máy Linux

Trước khi mount:

1. Tạo hoặc xác nhận Private Endpoint cho subresource file của account.
2. Cấu hình Private DNS, VNet link hoặc DNS forwarding phù hợp.
3. Đảm bảo client Linux đi đến private IP qua VNet/VPN/ExpressRoute.
4. Cho phép TCP 2049 theo phạm vi tối thiểu.
5. Cài NFS client package phù hợp distro; sử dụng NFS 4.1.
6. Thống nhất UID/GID ứng dụng và quyền trên thư mục đích.

Ví dụ trên Linux:

~~~bash
sudo mkdir -p /mnt/appsdata

sudo mount -t nfs \
  -o vers=4,minorversion=1,sec=sys \
  <UNIQUE_NFS_ACCOUNT_NAME>.file.core.windows.net:/<UNIQUE_NFS_ACCOUNT_NAME>/appsdata \
  /mnt/appsdata

findmnt /mnt/appsdata
df -h /mnt/appsdata
~~~

Tùy distro và khả năng NFS client, có thể cần điều chỉnh cú pháp mount. Thư mục đích phải tồn tại, export path phải đúng và share phải hỗ trợ NFS 4.1. Đặc biệt, sec=sys cho thấy mô hình xác định user qua UID/GID; nó **không phải bằng chứng rằng nội dung đã được mã hóa trong lúc truyền**.

Để kiểm tra thao tác trong thư mục được cấp quyền:

~~~bash
id
ls -lan /mnt/appsdata
touch /mnt/appsdata/connectivity-check.txt
ls -lan /mnt/appsdata/connectivity-check.txt
~~~

Nếu touch báo Permission denied, kiểm tra UID/GID, owner và mode trước khi thay đổi mạng hoặc cấp quyền rộng. Chỉ xóa file thử nghiệm khi chắc chắn đúng file do bạn tạo.

Tháo share khỏi máy Linux khi không còn sử dụng:

~~~bash
sudo umount /mnt/appsdata
~~~

Không dùng lệnh mount/unmount tùy tiện trên production nếu ứng dụng đang giữ file mở; cần dừng tác vụ hoặc có cửa sổ bảo trì phù hợp.

### 10.4. Duy trì mount sau khi khởi động lại

Nếu dùng cấu hình hệ thống như /etc/fstab, cần cân nhắc:

- Phụ thuộc mạng và DNS sẵn sàng lúc boot.
- Các tùy chọn systemd automount hoặc nofail phù hợp distro.
- Hành vi timeout/retry của SMB hoặc NFS.
- Không để key/plaintext credential trong file cấu hình đọc được bởi người không có quyền.
- Bảo đảm workload vẫn an toàn khi share tạm thời không khả dụng.

Đối với container/AKS, nên đánh giá Azure Files CSI driver và StorageClass/PersistentVolume phù hợp thay vì tự mount thủ công bên trong từng container. Tùy protocol, cấu hình và tính năng của CSI driver có thể khác; không copy StorageClass SMB và chỉ thay một chuỗi thành NFS mà chưa kiểm tra hướng dẫn chính thức.

## 11. Azure Files trong Kubernetes và ứng dụng

### 11.1. Khi dùng Azure Files CSI driver

Azure Files CSI driver cho phép Kubernetes dùng PersistentVolume/PersistentVolumeClaim cho các kịch bản SMB hoặc NFS được hỗ trợ. Điều này thuận tiện khi nhiều pod cần truy cập file chung, nhưng cần hiểu:

- StorageClass quyết định driver, SKU và giao thức.
- CSI driver có thể cần cấu hình network hoặc private endpoint trước để node mount được.
- Quyền của ứng dụng vẫn dựa trên cơ chế SMB hoặc NFS phù hợp, không tự động đồng nhất với Kubernetes RBAC.
- Access mode của Kubernetes không thay thế semantics file locking/UID/GID của hệ điều hành.
- Chi phí và dữ liệu vẫn thuộc Azure Storage, không tự mất khi pod bị xóa trong mọi cấu hình reclaim policy.

Ví dụ luồng logic:

~~~text
Application Pod
    ↓
PVC → PV → Azure Files CSI Driver
    ↓
Azure Files Share
    ↓
Storage Account (mạng, tier, redundancy)
~~~

Khi sử dụng nhiều replica ghi vào cùng đường dẫn, ứng dụng cần xử lý concurrent writes. Một file share có thể cho phép nhiều client mount, nhưng điều đó **không bảo đảm ứng dụng tự giải quyết tranh chấp ghi, khóa tệp hay transaction**.

### 11.2. Ví dụ ứng dụng xử lý tài liệu

Một service nhận tài liệu có thể ghi file tải lên vào share rồi gửi metadata vào database. Cần lưu ý:

1. Dùng tên file an toàn, tránh path traversal, file trùng tên và ghi đè ngoài ý muốn.
2. Phân quyền thư mục theo role hoặc workload.
3. Sử dụng kiểm soát concurrency và atomic operation phù hợp semantics của giao thức.
4. Quét nội dung có nguy cơ độc hại theo yêu cầu bảo mật tổ chức.
5. Lưu metadata nghiệp vụ trong database; không dựa duy nhất vào đường dẫn file để phản ánh trạng thái giao dịch.
6. Thiết kế retry/idempotency nếu mạng hoặc share tạm thời bị mất.

Nếu ứng dụng chủ yếu thao tác object qua HTTP, Blob Storage và mô hình event/queue có thể đơn giản hơn một mạng file share. Không đưa Azure Files vào kiến trúc nếu ứng dụng không thực sự cần file system semantics.

## 12. Hiệu năng: latency, IOPS, throughput và metadata operations

### 12.1. Những yếu tố chi phối

Hiệu năng file share phụ thuộc vào:

- Loại tài khoản/tier (HDD hoặc SSD) và mô hình cấp phát.
- Dung lượng và giới hạn IOPS/throughput theo share/account.
- Kích thước block/file và tỷ lệ đọc-ghi.
- Tỷ lệ file nhỏ, thao tác create/open/list/stat/close.
- Số client đồng thời và mức độ cạnh tranh truy cập cùng thư mục.
- Độ trễ mạng giữa client và storage region.
- Chế độ caching, mount options, encryption và khả năng của client.
- Workload có sử dụng nhiều file lock hoặc thao tác metadata liên tiếp hay không.

**Latency đo trên ứng dụng** có thể khác metric phía dịch vụ. Ví dụ network RTT từ data center lên Azure cộng thêm thời gian xử lý ở client, DNS, retry và serialization. Để đánh giá chính xác, cần đo từ client thực tế.

### 12.2. Phân biệt IOPS và throughput

- **IOPS:** số thao tác I/O mỗi giây, quan trọng với workload nhiều file nhỏ hoặc block nhỏ.
- **Throughput:** khối lượng dữ liệu truyền mỗi giây, quan trọng với đọc/ghi file lớn.
- **Latency:** thời gian một thao tác hoàn tất, ảnh hưởng trực tiếp tới trải nghiệm ứng dụng.
- **Concurrency:** số luồng/client cùng tạo yêu cầu; tăng concurrency không nhất thiết cải thiện tốc độ nếu đã gặp giới hạn tier hoặc mạng.

Ví dụ: một batch đọc 100.000 file vài KB có thể cần nhiều metadata operation; một pipeline đọc 20 file vài GB lại bị giới hạn bởi throughput. Hai workload có cùng tổng dung lượng nhưng yêu cầu hiệu năng khác nhau.

### 12.3. Quy trình benchmark

1. Xác định mẫu tải thật: dung lượng file, số lượng, tỷ lệ đọc/ghi và concurrency.
2. Thử trên VM/node tương đương production trong đúng network path.
3. Đo p50/p95 latency, IOPS, throughput, error rate và trạng thái throttling.
4. Thay đổi một yếu tố mỗi lần: tier, share size/provisioned performance, số worker, region hoặc protocol.
5. Theo dõi chi phí trong cùng phép thử.
6. Ghi kết quả và ngưỡng cần alert trước khi cutover.

Đừng chỉ dùng tốc độ copy một file lớn để kết luận NFS hoặc SMB “nhanh hơn”. Kết quả có thể bị tác động bởi cache của hệ điều hành và workload cụ thể.

## 13. Backup, snapshot và phục hồi

### 13.1. Vì sao redundancy chưa phải backup?

Redundancy bảo vệ khỏi một số sự cố hạ tầng theo mô hình dịch vụ, nhưng không ngăn thao tác xóa dữ liệu hợp lệ, file bị mã hóa bởi ransomware hoặc lỗi ứng dụng ghi đè. Do đó:

- Xác định RPO (mức dữ liệu có thể mất) và RTO (thời gian phục hồi).
- Chọn cơ chế snapshot/backup được hỗ trợ cho loại share, protocol và tier.
- Cấu hình retention, kiểm soát quyền xóa backup và tách quyền quản trị khi có thể.
- Kiểm thử restore một file và cả thư mục/share theo nhu cầu.
- Ghi nhận kết quả phục hồi, không chỉ kiểm tra trạng thái job backup thành công.

### 13.2. Snapshot, soft delete và Azure Backup

Azure Files có những tính năng liên quan đến share snapshot, soft delete, backup và bảo vệ dữ liệu theo cấu hình/kịch bản được hỗ trợ. **Khả năng sử dụng có thể khác giữa SMB/NFS và các tier/account model**; cần kiểm tra feature matrix hiện hành trước khi viết runbook.

Bảng định hướng:

| Cơ chế | Vai trò | Câu hỏi phải kiểm tra |
|---|---|---|
| Share snapshot | Ghi trạng thái dữ liệu share tại một thời điểm theo khả năng hỗ trợ | Share/protocol/tier hỗ trợ không? Ai tạo/xóa? Cách restore? |
| Soft delete | Hỗ trợ khôi phục trong một số kịch bản xóa share | Có áp dụng cho share này không? Thời hạn giữ bao lâu? |
| Azure Backup | Quản lý lịch và vòng đời backup theo workload được hỗ trợ | Tính năng hỗ trợ cho SMB/NFS/tier/region hiện tại? |
| Replication/DR | Giảm rủi ro mất khả năng phục vụ khi xảy ra sự cố hạ tầng | Redundancy có tương thích protocol/tier? Failover cần thao tác gì? |
| Bản sao độc lập theo chính sách | Phục hồi khỏi sự cố logic hoặc mất dữ liệu diện rộng | Có được bảo vệ khỏi xóa bởi cùng credential không? |

Không suy ra khi đổi protocol, share tự kế thừa đầy đủ những tính năng backup vốn chỉ được triển khai cho share SMB trong mô hình hiện tại.

### 13.3. Azure File Sync trong hybrid

**Azure File Sync** là giải pháp đồng bộ những file share SMB được hỗ trợ giữa Azure Files và Windows Server, phục vụ kịch bản giữ cache/tệp truy cập thường xuyên tại on-premises.

Không dùng Azure File Sync như giải pháp mặc định đồng bộ share NFS. Nếu cần chia sẻ dữ liệu giữa ứng dụng Linux và file server Windows, phải thiết kế workflow đồng bộ hoặc lớp ứng dụng phù hợp và kiểm thử tính nhất quán.

## 14. Giám sát và quản trị chi phí

### 14.1. Chỉ số nên theo dõi

| Nhóm | Tín hiệu hoặc chỉ số | Mục đích |
|---|---|---|
| Dung lượng | Used capacity, quota hoặc provisioned capacity | Phát hiện tăng trưởng bất thường |
| Hiệu năng | Transactions, latency, ingress/egress, throttling nếu được hỗ trợ | Xác định nút cổ chai và workload vượt giới hạn |
| Tính sẵn sàng | Availability, request errors, timeout | Phát hiện sự cố truy cập |
| Mạng | Private endpoint, DNS resolution, TCP 445/2049, VPN/ExpressRoute | Tách lỗi mạng khỏi lỗi dữ liệu |
| Bảo mật | Thay đổi access/network configuration, role assignments, key operations | Điều tra truy cập hoặc cấu hình trái phép |
| Sao lưu | Job, snapshot, retention và restore test | Kiểm tra khả năng phục hồi |
| Chi phí | Dung lượng/provisioned tier, transactions, egress và backup | Đánh giá hiệu quả kinh tế |

Azure Monitor có thể cung cấp metrics và các loại diagnostic logs theo tài nguyên/dịch vụ; sự hỗ trợ chi tiết phụ thuộc cấu hình. Khi tạo alert, cần kiểm tra metric namespace và aggregation đang khả dụng, không tự giả định mọi sự kiện file access của SMB/NFS đều được ghi đầy đủ trong một log duy nhất.

### 14.2. Ước tính tổng chi phí

Khi so sánh SMB và NFS, hãy xem:

- Dung lượng lưu và mức dung lượng được cấp phát (nếu mô hình dùng provisioned).
- Tier SSD/HDD, IOPS/throughput được cấp và giới hạn cần thiết.
- Số giao dịch và thao tác metadata theo mô hình giá áp dụng.
- Phí dữ liệu truyền ra khỏi region/Storage hoặc qua kết nối mạng theo bảng giá hiện hành.
- Private Endpoint, VPN Gateway/ExpressRoute, Azure Monitor/Log Analytics.
- Backup, snapshot, retention và bản sao dữ liệu độc lập.
- Chi phí migration, vận hành, quyền danh tính và xử lý sự cố.

Ví dụ minh họa quyết định: workload có 2 TiB dữ liệu nhưng đọc rất ít có thể không cần chọn SSD hiệu năng cao. Ngược lại, workload chỉ lưu vài chục GiB nhưng truy cập hàng nghìn file nhỏ mỗi giây có thể bị chi phối bởi IOPS/metadata latency, không phải dung lượng. Không lấy dung lượng làm tiêu chí duy nhất.

Azure Cost Management giúp phân tích chi phí theo resource group hoặc tag. Cần gắn tag như Application, Environment, Owner và CostCenter theo chuẩn tổ chức; lưu ý tag không tự làm giảm phí hoặc đóng share khi vượt budget.

## 15. Kịch bản thực tế: nâng cấp file server doanh nghiệp

Một doanh nghiệp vận hành hai loại workload:

- **Nhóm A:** nhân viên Windows sử dụng thư mục dùng chung cho báo cáo và biểu mẫu, cần danh tính doanh nghiệp và phân quyền theo phòng ban.
- **Nhóm B:** ứng dụng xử lý ảnh chạy trên Linux/AKS, cần một filesystem NFS để nhiều worker đọc dữ liệu chung.

### 15.1. Thiết kế cho nhóm A: SMB

1. Tạo Storage Account và SMB share trong subscription/resource group được quản trị.
2. Chọn vùng gần nơi ứng dụng/nhân viên kết nối để giảm RTT.
3. Tạo private endpoint và DNS cho VNet/hybrid theo yêu cầu.
4. Tích hợp AD DS hoặc phương án identity-based SMB được hỗ trợ.
5. Cấp quyền share-level theo nhóm, sau đó cấu hình NTFS ACL.
6. Nếu file server Windows tại chỗ vẫn cần phục vụ nhân viên, xem xét Azure File Sync và cloud tiering theo hỗ trợ.
7. Kiểm thử mở/sửa/xóa file, lock, concurrency và restore.
8. Theo dõi dung lượng, lỗi truy cập và chi phí.

**Lỗi cần tránh:** cấp Storage Account key rộng rãi cho mọi người chỉ để tránh cấu hình identity, vì khó kiểm toán theo từng user và tăng nguy cơ lộ dữ liệu.

### 15.2. Thiết kế cho nhóm B: NFS

1. Chọn account/tier hỗ trợ Azure Files NFS 4.1 và khả năng hiệu năng cần thiết.
2. Tạo share NFS và private endpoint/network rules.
3. Cấu hình DNS cho các node Linux/AKS.
4. Xác nhận UID/GID của process, thư mục và quyền truy cập.
5. Dùng NFS mount hoặc Azure Files CSI driver theo mô hình được hỗ trợ.
6. Chạy benchmark với số worker và mẫu file tương tự production.
7. Thiết lập chính sách dữ liệu, backup/restore và giám sát.
8. Kiểm thử phục hồi khi một node mất kết nối hoặc pod được lên lịch ở node khác.

**Lỗi cần tránh:** cho tất cả container chạy với quyền root và chmod 777 để “giải quyết nhanh” lỗi permission. Điều này làm yếu phân quyền và gây khó khăn khi kiểm toán.

### 15.3. Kế hoạch migration và cutover

Khi chuyển dữ liệu từ file server cũ lên Azure Files:

1. Khảo sát tổng file, kích thước, ký tự tên đường dẫn, permission, file lock và mức thay đổi hằng ngày.
2. Chọn công cụ migration tương thích SMB/NFS và cách giữ metadata cần thiết.
3. Thực hiện bản sao ban đầu khi workload đang hoạt động nếu công cụ/quy trình hỗ trợ.
4. Đồng bộ thay đổi bổ sung và đo hiệu năng truy cập cloud.
5. Chạy thử nhóm người dùng/worker nhỏ; xác minh ứng dụng và ACL/UID/GID.
6. Chuẩn bị thời điểm freeze write hoặc cutover để tránh hai nơi đồng thời nhận ghi.
7. Cập nhật UNC path/mount target, ứng dụng, DNS hoặc cấu hình CSI.
8. Theo dõi lỗi, cung cấp rollback plan, đối chiếu dữ liệu và quyền.
9. Chỉ ngừng file server cũ sau khi xác nhận giữ đủ dữ liệu và backup theo quy trình.

Không dùng lệnh mirror có hành vi xóa phía đích mà chưa kiểm tra tác động; một script đồng bộ sai có thể nhân rộng lỗi xóa file sang share cloud.

## 16. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Windows không truy cập được UNC | TCP 445 bị chặn, DNS sai, firewall hoặc route | Test-NetConnection, DNS, Private Endpoint, network rules |
| SMB mount trả Access denied | Chưa có share-level role, ACL không cho phép hoặc auth sai | Kiểm tra identity, ticket Kerberos, role và NTFS ACL |
| SMB chỉ hoạt động với account key | Identity integration chưa hoàn chỉnh | Kiểm tra AD DS/Entra Kerberos, domain join, permission và cấu hình account |
| Client từ on-premises không mount được | DNS forwarder chưa phân giải private endpoint hoặc VPN/ER thiếu route | Kiểm tra private DNS, TCP 445/2049, định tuyến hai chiều |
| NFS mount: Permission denied | UID/GID/mode không phù hợp hoặc export/network rules không cho phép | Kiểm tra id, ls -ln, DNS, NFS endpoint, cấu hình client |
| NFS mount treo hoặc timeout | TCP 2049 không tới được, DNS/route sai hoặc vấn đề gateway | Kiểm tra connectivity từ máy client và trạng thái network |
| Share tạo lỗi Unsupported protocol | Account kind, tier, SKU hoặc region không hỗ trợ | Kiểm tra feature matrix Azure Files và phiên bản CLI |
| Không thể thấy file sau mount | Sai share/path, mount point bị che bởi mount khác hoặc đồng bộ chưa hoàn tất | findmnt, đường dẫn UNC/export, listing, sync status |
| Ứng dụng ghi chậm | RTT cao, giới hạn IOPS/throughput, quá nhiều metadata ops | Benchmark từ client, Azure Monitor và tier/model hiệu năng |
| Quyền Linux trên NFS khác giữa các node | Không thống nhất UID/GID hoặc pod securityContext | Kiểm tra ID số và quyền thư mục, không chỉ username |
| Có snapshot nhưng restore vẫn thất bại | Không thử quy trình restore, snapshot bị hết hạn/không tương thích | Kiểm tra feature support, quyền, retention và thử khôi phục |
| Chi phí cao hơn dự kiến | Provisioned capacity/IOPS quá lớn, nhiều transaction, network/backup phí | Xem Cost Management và workload metrics |

**Nguyên tắc điều tra:** đừng kết luận “Azure Files bị lỗi” chỉ từ một thông báo mount thất bại. Hãy tách theo chuỗi account/share tồn tại → DNS → network/port → protocol → authentication → file permissions → application semantics.

## 17. Quy trình kiểm tra trước khi đưa vào production

### Thiết kế

- [ ] Xác định rõ share SMB hay NFS và client/ứng dụng nào phải truy cập.
- [ ] Kiểm tra account kind, tier, region, limits và mô hình tính phí hỗ trợ.
- [ ] Xác định data classification, RPO/RTO, retention và yêu cầu khôi phục.
- [ ] Lập kế hoạch CIDR, Private Endpoint, DNS và kết nối hybrid nếu cần.
- [ ] Chọn identity-based SMB hoặc phương án truy cập NFS nhất quán.
- [ ] Tránh đưa account key vào code, CI logs, file cấu hình công khai.

### Kiểm tra chức năng

- [ ] DNS trả đúng endpoint theo thiết kế.
- [ ] Client mở được TCP 445 (SMB) hoặc 2049 (NFS).
- [ ] Mount thành công với đúng danh tính/quyền dự kiến.
- [ ] User không có quyền bị từ chối đúng cách.
- [ ] Thử thao tác create/read/write/rename/delete theo use case.
- [ ] Thử đồng thời nhiều client, xử lý lock và reconnect.
- [ ] Đo latency, IOPS/throughput và khả năng chịu tải.
- [ ] Thử backup/restore ở phạm vi nhỏ và xác minh dữ liệu.

### Vận hành

- [ ] Có owner, tag, dashboard, alert, runbook xử lý lỗi.
- [ ] Có giới hạn quyền quản trị và quy trình thay đổi network access.
- [ ] Đã thống nhất policy quay vòng key nếu có dùng shared-key auth.
- [ ] Đã dự trù chi phí share, backup, network và monitoring.
- [ ] Đã chuẩn bị kế hoạch dọn dẹp tài nguyên thực hành và lưu dữ liệu cần giữ.

## 18. Câu hỏi tự kiểm tra

1. **Azure Files khác Managed Disk ở đâu?** Azure Files cung cấp file share mạng cho nhiều client theo giao thức được hỗ trợ; Managed Disk cung cấp block storage cho VM và mô hình gắn đĩa.
2. **SMB thường dùng cổng nào?** TCP 445.
3. **Azure Files NFS dùng phiên bản giao thức nào trong kịch bản phổ biến?** NFS 4.1.
4. **Một file share Azure Files có tự phục vụ SMB và NFS cùng lúc không?** Không nên giả định như vậy; protocol là thuộc tính của share khi tạo và khả năng hỗ trợ khác nhau.
5. **Private Endpoint có tự cấp quyền đọc file cho client không?** Không. Nó giải quyết đường mạng, không thay thế xác thực và phân quyền dữ liệu.
6. **Với SMB identity-based, chỉ cấp Azure RBAC share-level role đã đủ mọi thao tác file chưa?** Chưa. Còn có NTFS ACL và điều kiện đăng nhập bằng danh tính được hỗ trợ.
7. **NFS mount thành công nhưng ghi bị từ chối, cần xem gì?** UID/GID, owner/mode và các quyền tương ứng.
8. **Tại sao không nên đưa Storage Account key vào command line production?** Key có phạm vi quyền rộng và có nguy cơ lộ qua lịch sử, log hoặc script.
9. **Có nên dùng NFS qua Internet không kiểm soát?** Không. Phải thiết kế mạng tin cậy, policy và bảo vệ dữ liệu trong đường truyền theo yêu cầu.
10. **Redundancy có thay thế backup không?** Không. Nó không giải quyết đầy đủ xóa nhầm hoặc ransomware.
11. **SMB trên Linux có được không?** Có trong các môi trường hỗ trợ CIFS/SMB và phương thức xác thực phù hợp.
12. **Khi không mount được từ on-premises, cần kiểm tra theo thứ tự nào?** DNS, network/port, protocol, authentication, quyền file và ứng dụng.
13. **Tại sao dung lượng file ít không luôn đồng nghĩa giá/hiệu năng thấp?** Workload nhiều thao tác nhỏ có thể bị chi phối bởi transactions, IOPS và tier/provisioned performance.
14. **Azure File Sync có mặc nhiên đồng bộ share NFS không?** Không. Cần xem khả năng hỗ trợ; kịch bản điển hình là Azure Files SMB với Windows Server.
15. **Sau migration nên kiểm tra gì trước khi bỏ file server cũ?** Nội dung, metadata/quyền, ứng dụng, dữ liệu cập nhật cuối, backup, rollback và xác nhận của owner.

## 19. Tài liệu tham khảo

- [Azure Files documentation](https://learn.microsoft.com/azure/storage/files/) — tổng quan, tính năng và quản lý Azure Files.
- [Planning for an Azure Files deployment](https://learn.microsoft.com/azure/storage/files/storage-files-planning) — chọn account, giao thức, mạng và hiệu năng.
- [Azure Files SMB authentication](https://learn.microsoft.com/azure/storage/files/storage-files-active-directory-overview) — các lựa chọn identity-based SMB authentication.
- [Azure Files networking](https://learn.microsoft.com/azure/storage/files/storage-files-networking-overview) — Private Endpoint, firewall và kết nối hybrid.
- [Mount an SMB Azure file share on Windows](https://learn.microsoft.com/azure/storage/files/storage-how-to-use-files-windows) — cấu hình và kết nối Windows client.
- [Mount an Azure Files NFS share](https://learn.microsoft.com/azure/storage/files/storage-files-how-to-mount-nfs-shares) — điều kiện và lệnh mount NFS.
- [Azure File Sync overview](https://learn.microsoft.com/azure/storage/file-sync/file-sync-introduction) — đồng bộ file server và cloud trong kịch bản hỗ trợ.
- [Azure Files scalability and performance targets](https://learn.microsoft.com/azure/storage/files/storage-files-scale-targets) — giới hạn tài nguyên và khả năng hiệu năng.
- [Azure Storage monitoring](https://learn.microsoft.com/azure/storage/common/monitor-storage) — metrics, diagnostics và phân tích vận hành.
- [Azure Storage pricing](https://azure.microsoft.com/pricing/details/storage/files/) — kiểm tra mô hình giá hiện hành.

Khả năng hỗ trợ NFS, tier, mô hình cấp phát, mã hóa đường truyền, identity-based SMB, redundancy, snapshot và backup có thể thay đổi theo thời điểm, region và SKU. **Nguyên tắc vận hành:** chọn giao thức theo yêu cầu ứng dụng, giới hạn mạng và quyền theo đúng mô hình xác thực, đo hiệu năng từ client thật, rồi thử khôi phục trước khi đưa dữ liệu quan trọng lên production.
