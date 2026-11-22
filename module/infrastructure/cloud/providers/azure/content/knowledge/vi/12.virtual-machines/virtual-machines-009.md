# Patch và quản lý cập nhật bằng Azure Update Manager

Khi một ứng dụng chạy trên Azure Virtual Machines (VM), người vận hành vẫn phải cập nhật hệ điều hành và những thành phần phần mềm thuộc phạm vi mình quản lý. Tạo VM trong subscription, đặt nó vào virtual network (VNet), bật mã hóa và cấu hình Network Security Group (NSG) **không đồng nghĩa VM đã được vá các lỗ hổng hệ điều hành mới**. Nếu trì hoãn cập nhật quá lâu, VM có thể có rủi ro bảo mật; nếu cập nhật thiếu kiểm soát, VM có thể khởi động lại trong giờ cao điểm, mất khả năng kết nối tới database hoặc chạy phiên bản package không tương thích.

**Azure Update Manager** (AUM) giúp đánh giá và điều phối việc cài đặt các bản cập nhật hệ điều hành trên những máy được hỗ trợ, bao gồm Azure VM và máy chủ kết nối Azure qua **Azure Arc**. Dịch vụ cung cấp thông tin đánh giá patch, khả năng cài đặt theo yêu cầu và lập lịch bảo trì theo các cơ chế Azure tương ứng. AUM **không phải kho phát hành mọi bản vá**, **không sửa tất cả lỗ hổng ứng dụng** và **không bảo đảm không có gián đoạn chỉ bằng một công tắc**.

Bài thuộc chương **Máy ảo Azure**, trong module **CLOUD_PROVIDERS_AZURE**. Nó liên kết kiến thức subscription/resource group và Microsoft Entra ID với hạ tầng VM, mạng ảo, dịch vụ dữ liệu, giám sát, bảo vệ và kiểm soát chi phí một hệ thống ứng dụng Azure. Trọng tâm là xây dựng quy trình vá lỗi có thể kiểm chứng, an toàn với workload thực tế thay vì chỉ nhấn nút **Install updates**.

Sau bài học, bạn có thể:

- Giải thích các khái niệm *assessment*, *patch installation*, *maintenance window*, *reboot* và *compliance* trong Azure Update Manager.
- Phân biệt cập nhật guest OS với bảo trì hạ tầng Azure, bản vá phần mềm ứng dụng, cập nhật image/container và công cụ quét lỗ hổng.
- Thiết kế vòng triển khai patch theo nhóm kiểm thử, canary, production, với lịch và phạm vi phù hợp.
- Thực hiện đánh giá/cài đặt theo nhu cầu, xây dựng lịch cập nhật qua giao diện Azure và kiểm chứng kết quả.
- Kết hợp AUM với backup, health probe, Load Balancer, cảnh báo, quyền tối thiểu và quy trình ứng phó sự cố.
- Điều tra các trường hợp VM không xuất hiện, không quét được cập nhật, cài đặt thất bại hoặc yêu cầu khởi động lại.

## 1. Tại sao cần một quy trình patch tập trung?

Giả sử công ty có 40 VM chạy Windows Server và Ubuntu, rải trên ba subscription: development, testing và production. Một số VM đóng vai trò API, một số chạy batch processing, số khác là máy chủ kết nối hệ thống on-premises qua VPN/ExpressRoute. Nếu quản trị viên đăng nhập từng VM để kiểm tra và cập nhật thủ công:

- Khó biết toàn bộ VM còn thiếu bản vá quan trọng nào.
- Khó xác định VM nào đã được vá, VM nào thất bại và ai chịu trách nhiệm khắc phục.
- Dễ vá nhiều backend cùng lúc, gây gián đoạn dù ứng dụng đã có load balancer.
- Những bản vá yêu cầu reboot có thể bị trì hoãn mãi hoặc xảy ra ngoài giờ bảo trì.
- Các VM bị tắt, bị cô lập mạng hoặc dùng hệ điều hành hết hỗ trợ có thể bị bỏ sót.
- Khó có bằng chứng cập nhật cho yêu cầu kiểm toán và quản trị rủi ro.

AUM giúp hình thành một **mặt phẳng quản lý tập trung** để đánh giá, phân nhóm, lập lịch và theo dõi. Tuy vậy, đội vận hành vẫn cần chính sách lựa chọn bản vá, xác nhận nguồn cập nhật, kiểm thử tương thích, backup/rollback và xử lý VM ngoại lệ.

### Patch không chỉ là cài package

Một chu kỳ patch đầy đủ:

~~~mermaid
flowchart LR
    INVENTORY[Kiểm kê VM và owner] --> ASSESS[Đánh giá bản cập nhật]
    ASSESS --> RISK[Phân loại rủi ro và ưu tiên]
    RISK --> TEST[Kiểm thử / canary]
    TEST --> SCHED[Lập lịch, phê duyệt]
    SCHED --> INSTALL[Cài đặt cập nhật]
    INSTALL --> REBOOT[Khởi động lại nếu cần]
    REBOOT --> VERIFY[Kiểm tra OS và ứng dụng]
    VERIFY --> REPORT[Đối soát, xử lý ngoại lệ]
    REPORT --> ASSESS
~~~

Một report “cài đặt thành công” mới phản ánh kết quả thao tác patch ở phạm vi được báo cáo. Để xác nhận dịch vụ khỏe, cần thêm health probe, kiểm tra giao dịch nghiệp vụ, log ứng dụng và bằng chứng dữ liệu hoạt động đúng.

## 2. Azure Update Manager quản lý được gì và không quản lý được gì?

| Phạm vi | Azure Update Manager hỗ trợ ở mức nào? | Phần vẫn do đội vận hành chịu trách nhiệm |
|---|---|---|
| Guest OS của Azure VM được hỗ trợ | Đánh giá, cài cập nhật, lên lịch và xem lịch sử | Chọn chính sách, kiểm thử, reboot, kiểm tra workload |
| Server được Azure Arc-enabled và đủ điều kiện | Đưa các máy ngoài Azure vào luồng đánh giá/vá được hỗ trợ | Kết nối Arc, mạng, agent/extension, license và nguồn cập nhật |
| Windows Update / WSUS và repository Linux | Điều phối qua cơ chế cập nhật của hệ điều hành | Nguồn package, proxy, repository, trạng thái dịch vụ và GPO |
| VM Scale Sets / kiến trúc autoscale | Một số loại VM/tình huống được hỗ trợ theo chế độ cụ thể | Kiểm tra mode, khả năng cập nhật image, rolling upgrade và đối tượng quản lý |
| Ứng dụng tự cài trên VM | Không tự động bảo đảm sửa mọi dependency/CVE ứng dụng | CI/CD, package manager của ứng dụng, restart và regression test |
| Container image, managed PaaS, database engine được quản lý | Không thay thế quy trình cập nhật riêng của từng nền tảng | Pipeline dựng image mới, AKS node/cluster upgrade, PaaS maintenance |
| Host Azure, hypervisor và hạ tầng datacenter | Không phải công cụ khách hàng dùng để vá phần nền tảng do Azure quản lý | Theo dõi thông báo/maintenance Azure và yêu cầu SLA |

**Guest OS** là hệ điều hành bên trong VM. **Host OS/hypervisor** thuộc hạ tầng chạy VM. Azure quản lý phần lớn hạ tầng vật lý theo mô hình trách nhiệm chia sẻ, trong khi chủ workload phải quản lý bản vá guest OS trừ các cơ chế cập nhật tự động và cam kết quản lý cụ thể đã cấu hình.

### Kiến trúc logic

~~~mermaid
flowchart TB
    ADMIN[Nhóm vận hành] --> PORTAL[Azure Update Manager]
    PORTAL --> ASSESS[Assessment / Install]
    PORTAL --> MAINT[Maintenance configuration / Lịch cập nhật]
    ASSESS --> VM1[Azure VM Windows]
    ASSESS --> VM2[Azure VM Linux]
    ASSESS --> ARC[Azure Arc-enabled server]
    MAINT -. Chọn lịch và phạm vi .-> VM1
    MAINT -. Chọn lịch và phạm vi .-> VM2
    MAINT -. Chọn lịch và phạm vi .-> ARC
    VM1 --> WU[Windows Update / WSUS]
    VM2 --> REPO[Repository apt / dnf / yum / zypper]
    ARC --> SOURCE[Nguồn cập nhật của OS]
    PORTAL --> HISTORY[Lịch sử kết quả và báo cáo]
~~~

Sơ đồ chỉ biểu thị quan hệ khái niệm. Cách AUM tương tác với máy, extension và nguồn bản vá phụ thuộc loại máy, hệ điều hành và phiên bản dịch vụ; không nên suy rằng Azure Update Manager tự lưu bản cài đặt của tất cả sản phẩm. Lịch cập nhật guest OS được tích hợp với các thành phần của **Azure Maintenance** theo mô hình được hỗ trợ.

## 3. Những khái niệm cốt lõi cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ thực tế |
|---|---|---|
| **Patch assessment** | Kiểm tra danh sách bản cập nhật còn thiếu theo thông tin OS/repository | VM còn thiếu 2 security updates và 1 critical update |
| **Periodic assessment** | Đánh giá tự động định kỳ trên máy được cấu hình và hỗ trợ | Có báo cáo mới theo chu kỳ của nền tảng |
| **On-demand assessment** | Chủ động yêu cầu đánh giá tại thời điểm kiểm tra | Quét lại trước cửa sổ patch |
| **One-time update installation** | Cài bản cập nhật theo yêu cầu, không đòi lịch lặp | Khắc phục CVE khẩn cấp trên VM lab |
| **Scheduled patching** | Áp dụng cập nhật trong các cửa sổ theo lịch | Nhóm canary thứ Ba, production thứ Năm |
| **Maintenance configuration** | Tài nguyên mô tả thời gian, scope và cấu hình bảo trì phù hợp | Lịch cuối tuần cho một nhóm VM |
| **Dynamic scoping** | Chọn máy tự động theo tiêu chí được hỗ trợ | Tất cả VM production của ứng dụng X có tag đúng |
| **Patch classification** | Phân loại cập nhật theo OS và nguồn update | Security, Critical, Updates, Update Rollups tùy OS |
| **Reboot setting** | Chính sách xử lý khởi động lại theo lựa chọn được hỗ trợ | If required / Always / Never |
| **Patch compliance** | Trạng thái đánh giá về các bản cập nhật còn thiếu theo chính sách và thời điểm | “Không phát hiện thiếu patch thuộc phạm vi chọn” |

**Assessment khác installation.** Một VM hiển thị thiếu nhiều bản cập nhật chưa chứng minh chúng đã được cài hoặc đã lên lịch cài. Ngược lại, một lần cài thành công chưa bảo đảm trạng thái hiện tại không còn cập nhật mới kể từ khi danh sách được đánh giá.

**Compliance là ảnh chụp có thời điểm.** Nó còn phụ thuộc tính mới của assessment, danh mục bản vá, repo/WSUS và phạm vi chính sách; không nên coi một trạng thái xanh là chứng chỉ VM không có CVE.

### Dòng thời gian minh họa

~~~text
T1: Assessment → phát hiện 4 cập nhật còn thiếu
T2: Lịch bảo trì → cài 3 cập nhật phù hợp bộ lọc; 1 bị loại khỏi phạm vi
T3: Reboot → hoàn thành bước khởi động lại nếu cần
T4: Assessment mới → kiểm tra lại thực trạng
T5: Health check → xác nhận ứng dụng và dependency hoạt động
~~~

Việc cài đúng ba cập nhật đã chọn **không tự làm bản cập nhật thứ tư biến mất**. Hãy theo dõi các patch bị loại trừ, cập nhật thất bại và trạng thái cần reboot.

## 4. Các chế độ patch orchestration của Azure VM

Trước khi lập lịch với Update Manager, cần biết **ai điều khiển thời điểm cài đặt patch**. Azure VM có các chế độ/thiết lập patching khác nhau theo OS, image và khả năng hỗ trợ. Tên hiển thị trong portal hoặc API có thể khác theo phiên bản.

| Kiểu điều phối | Ý tưởng | Lưu ý vận hành |
|---|---|---|
| **OS-orchestrated / Automatic by OS** | Hệ điều hành và chính sách cập nhật bên trong VM quyết định thời điểm | Windows Update/GPO, unattended upgrades hoặc package service có thể ảnh hưởng lịch |
| **Azure-orchestrated / Automatic by platform** | Nền tảng Azure điều phối cập nhật guest OS khi loại VM và cấu hình được hỗ trợ | Có chính sách/safety controls riêng; không đánh đồng với lịch do khách hàng tạo |
| **Customer Managed Schedules** | Khách hàng đặt cửa sổ bảo trì phù hợp và Azure Update Manager điều phối cài đặt | Cần cấu hình patch orchestration, hỗ trợ OS/image và maintenance configuration đúng loại |
| **Manual** | Chủ workload điều khiển việc cài cập nhật, có thể dùng công cụ riêng/on-demand khi được hỗ trợ | Đừng để vừa automation nội bộ vừa một lịch khác cùng cài patch không có phối hợp |

**Một VM không nên đồng thời chịu hai cơ chế reboot/cài cập nhật cạnh tranh mà đội vận hành không kiểm soát.** Ví dụ Windows Server vừa bật cập nhật tự động bằng Group Policy, vừa gắn lịch AUM có thể dẫn đến thời điểm cài đặt ngoài dự kiến. Trên Linux, cần kiểm tra tác vụ unattended-upgrades hoặc cơ chế cập nhật tự động của distro.

### Chọn chế độ theo mục tiêu

- Nếu yêu cầu **cửa sổ bảo trì cố định** cho workload nhạy cảm, đánh giá **Customer Managed Schedules** cùng maintenance configuration và các điều kiện tiên quyết được Azure hỗ trợ.
- Nếu workload chấp nhận việc nền tảng tự điều phối cập nhật theo chế độ phù hợp, kiểm tra **Azure-orchestrated** và hành vi an toàn triển khai trước khi chọn.
- Nếu team vận hành một patch engine riêng, thống nhất một nguồn điều phối và đưa trạng thái của engine đó vào kiểm soát thay đổi.

Đừng đổi patch mode của VM production mà không kiểm tra tính tương thích, các tác vụ hiện hữu, khả năng rollback và ảnh hưởng đến lịch bảo trì. **Mode hiển thị trong Azure Portal và cấu hình máy thực tế** cần được đối chiếu, nhất là sau migration hoặc cấu hình bằng IaC.

## 5. Điều kiện tiên quyết: VM, OS, quyền, agent và mạng

Trước khi cài patch, cần xác định máy có thể được quản lý và nhận bản cập nhật.

### 5.1. Azure VM và Azure Arc

Azure VM cần được tạo bằng image/OS được dịch vụ hỗ trợ, trạng thái máy cho phép đánh giá và có các thành phần điều phối guest được hỗ trợ. Các thao tác có thể phụ thuộc vào **VM agent/patch extension** hoặc cơ chế tích hợp tương ứng; phải kiểm tra trạng thái extension khi assessment/install thất bại.

Với máy ngoài Azure, cần **Azure Arc-enabled Servers** được onboard và kết nối bình thường trước khi sử dụng các khả năng được hỗ trợ của Update Manager. Arc server có ràng buộc về OS, máy kết nối, cấu hình mạng, agent/extension và license/chi phí riêng; không phải cứ có bất kỳ hostname nào trong Azure là có thể vá.

### 5.2. Windows và Linux sử dụng nguồn update nào?

| Hệ điều hành | Nguồn thông tin cập nhật thường gặp | Vấn đề thường gây thất bại |
|---|---|---|
| Windows Server | Windows Update hoặc WSUS theo chính sách tổ chức | WSUS unreachable, GPO, lỗi Windows Update Agent, pending reboot |
| Ubuntu/Debian | Repository qua APT và chính sách cập nhật distro | Repository không truy cập được, cache hết hạn, apt/dpkg lock, EOL |
| RHEL và distro dùng RPM | DNF/YUM cùng subscription/repo phù hợp | Repo subscription, mirror/proxy, dependency conflict |
| SUSE và môi trường tương tự | Zypper/repository được cấu hình | Repository không hợp lệ, entitlement, dependency hoặc metadata |

Update Manager **dùng nguồn cập nhật được OS cấu hình**, không tự bảo đảm một bản vá xuất hiện nếu repository/WSUS chưa phát hành hoặc chưa được phê duyệt. Với Linux, danh mục phân loại như Security/Critical có thể dựa trên metadata của distro, và không phải mọi distro đều cung cấp các classification giống Windows. Luôn xác nhận kết quả trên bản phân phối/phiên bản thực tế.

### 5.3. Kết nối mạng cần có

Trên VM chạy trong VNet riêng hoặc hub-spoke:

1. Máy và extension/agent cần truy cập các **endpoint Azure điều khiển/giám sát** được dịch vụ yêu cầu.
2. Guest OS cần truy cập **Windows Update/WSUS hoặc package repositories** theo cấu hình; nhiều repository nằm ngoài Azure.
3. Firewall, NSG, proxy và User Defined Route không được chặn những luồng cần thiết.
4. DNS phải phân giải được endpoint của dịch vụ, repository và máy chủ proxy.
5. Máy cần dung lượng đĩa, CPU/RAM và thời gian hoạt động đủ để đánh giá/cài đặt.

**Có Private Endpoint tới Storage hoặc VM có private IP không có nghĩa VM tự truy cập được Windows Update.** Nếu forced tunneling đưa mọi outbound qua Azure Firewall/on-premises, đội mạng phải cho phép đúng đích/cổng và có DNS phù hợp. Không mở toàn bộ Internet từ mọi VM chỉ để sửa lỗi một repository.

### 5.4. Quyền Azure RBAC

Tách ít nhất ba nhóm quyền:

- **Người chỉ xem** posture/assessment và lịch sử cài đặt.
- **Người vận hành patch** được phép đánh giá, cài đặt trên đúng nhóm máy và gán/lập lịch maintenance phù hợp.
- **Người quản trị nền tảng** quản lý policy, quyền, subscription, network và các cấu hình chung.

Dùng role có sẵn hoặc custom role chứa các hành động cần thiết của Update Manager, Azure Compute, Azure Maintenance và Azure Arc theo scope được hỗ trợ; không cấp **Owner** toàn subscription cho mọi người chỉ cần cài patch. Kiểm tra cả quyền tạo maintenance configuration **và** quyền gán configuration tới VM hoặc tạo dynamic scope.

## 6. Assessment: từ “còn thiếu” tới quyết định vá

### 6.1. Đánh giá theo yêu cầu

Một quy trình trên Azure Portal:

1. Mở **Azure Update Manager** hoặc phần cập nhật của VM.
2. Chọn subscription, resource group, region hoặc máy theo bộ lọc phù hợp.
3. Kiểm tra danh sách máy, trạng thái hỗ trợ và thời gian assessment gần nhất.
4. Yêu cầu **Check for updates / Assess updates** trên VM được phép.
5. Đợi kết quả rồi xem **Available updates**, loại bản vá, reboot pending và lỗi nếu có.
6. Ghi nhận báo cáo làm baseline trước thay đổi.

Tên menu có thể thay đổi theo phiên bản Azure Portal. Điều quan trọng là chọn đúng **resource ID của VM**, không dựa duy nhất vào tên hiển thị vì hai subscription có thể trùng tên VM.

### 6.2. Kết quả assessment cần đọc ra sao?

Ví dụ một VM Windows:

| Trường quan sát | Giá trị minh họa | Câu hỏi vận hành |
|---|---|---|
| Machine | `vm-orders-prod-01` | Đúng subscription/owner không? |
| Last assessed | 2026-11-20 09:00 UTC | Kết quả còn đủ mới không? |
| Critical | 1 | Có khai thác thực tế hoặc mức ưu tiên đặc biệt không? |
| Security | 3 | Bản nào cần kiểm thử tương thích? |
| Update Rollups / Updates | 2 | Có nằm trong phạm vi policy hiện tại không? |
| Pending reboot | Yes | Có thể đang chờ reboot từ lần cài trước? |
| Assessment status | Succeeded | Thành công về scan, không có nghĩa patch đã cài |

Không chọn một bản vá chỉ theo classification. Nên kết hợp mức độ nghiêm trọng, khả năng bị khai thác, tài sản bị ảnh hưởng, yêu cầu pháp lý, chức năng của máy và độ khẩn cấp của vendor advisory.

### 6.3. Periodic assessment

Periodic assessment có thể giúp làm mới thông tin patch định kỳ trên máy hỗ trợ. Tần suất/khả năng cập nhật báo cáo có thể chịu ảnh hưởng chính sách dịch vụ, thời điểm VM chạy, trạng thái agent và kết nối mạng. **Không dùng periodic assessment như đồng hồ thời gian thực**: kết quả có thể trễ hoặc stale đối với VM vừa mới deploy, đã tắt hoặc lâu không liên lạc.

Đối với CVE khẩn cấp, hãy thực hiện assessment theo yêu cầu hoặc kiểm tra trực tiếp nguồn update trên OS theo runbook thay vì chờ dashboard tự làm mới.

## 7. Chọn loại bản vá, tiêu chí include/exclude và chính sách

Thông thường một cài đặt có thể chọn bản vá theo **classifications** hoặc theo **package/KB identifier**, kèm các điều kiện được nền tảng hỗ trợ. Nhưng khái niệm “Security” trên Linux không luôn tương ứng 1:1 với danh mục Windows.

| Chính sách | Ví dụ | Rủi ro |
|---|---|---|
| Security + Critical | Nhóm VM production ưu tiên các cập nhật an ninh/quan trọng | Bỏ sót bản sửa lỗi cần thiết nếu classification không được repo cung cấp |
| Explicit include | Chỉ chọn KB/package theo danh sách khắc phục khẩn cấp | Dễ thiếu dependency hoặc bỏ qua patch thay thế/supersedence |
| Explicit exclude | Hoãn một bản có lỗi tương thích đã biết, kèm hạn xử lý | Ngoại lệ kéo dài làm lỗ hổng tồn tại |
| All applicable updates | Hợp lý cho lab hoặc một số máy được kiểm soát | Có thể cài thay đổi chức năng/kernel ngoài phạm vi bảo trì dự kiến |

Trên Windows, các bộ lọc thường dựa vào taxonomy của Windows Update/WSUS như Critical, Security, Update Rollups hoặc Updates. Trên Linux, hãy kiểm tra khả năng OS distro cung cấp severity/classification và cách SDK/Update Manager ánh xạ; nếu metadata không phân loại chính xác, cần xây chính sách theo bản phân phối, repository hoặc package cụ thể.

**Không giả định có thể cài “chỉ một CVE” bằng cách nhập mã CVE vào Update Manager.** Một advisory có thể liên quan nhiều package/KB; có dependency và bản cập nhật superseding. Cần xác định update/package thực tế từ nguồn được tin cậy và kiểm tra kết quả sau cài.

### Chính sách ngoại lệ

Khi một patch bị hoãn do lỗi ứng dụng, hãy ghi:

- Bản cập nhật/package hoặc KB, OS, VM/nhóm chịu ảnh hưởng.
- Lý do và mức rủi ro chưa khắc phục.
- Người phê duyệt, ngày hết hạn ngoại lệ và các biện pháp giảm thiểu tạm thời.
- Kế hoạch test lại hoặc nâng cấp ứng dụng.

Không sử dụng `exclude` như công tắc bỏ qua vĩnh viễn mọi security updates trên một máy quan trọng.

## 8. Cài đặt patch một lần (on-demand installation)

One-time installation phù hợp để vá một VM lab, xử lý CVE khẩn cấp đã được phê duyệt hoặc kiểm chứng trước khi đưa cấu hình vào lịch lặp. **Cài đặt patch là một thay đổi trên hệ điều hành**, có thể restart dịch vụ, cập nhật kernel hoặc yêu cầu reboot. Không dùng máy production để thử cú pháp lần đầu.

### 8.1. Các bước qua Azure Portal

1. Chọn VM đúng subscription/resource group rồi mở chức năng cập nhật của **Azure Update Manager**.
2. Kiểm tra assessment mới nhất và trạng thái `Pending reboot`.
3. Chọn **Install one-time updates** hoặc thao tác tương đương, xác nhận tên VM và phạm vi cập nhật.
4. Chọn classifications/KB/package phù hợp với OS và policy đã phê duyệt.
5. Chọn **reboot setting**: theo nhu cầu, luôn reboot hoặc không reboot (tùy tùy chọn được hỗ trợ).
6. Đặt **maximum duration/maintenance window** theo khả năng của dịch vụ, có dự phòng cho cài đặt và kiểm tra.
7. Xem lại lựa chọn, thực hiện và theo dõi **installation status** đến khi có kết quả.
8. Đánh giá lại VM và thực hiện health check ứng dụng sau cài.

Một lần chạy hoàn thành với kết quả “Completed” cần được xem kèm **số update thành công, thất bại, không áp dụng, reboot status và thông tin kết thúc**. Nếu một package yêu cầu restart ứng dụng mà không được tự khởi động lại, người vận hành phải xử lý riêng.

### 8.2. Ví dụ Azure CLI cho Azure VM

Đoạn Bash sau dùng VM **thử nghiệm đã tồn tại**; chỉ phần `assess-patches` dùng để kiểm tra, còn `install-patches` tạo thay đổi thật trên guest OS. Không chạy ở production nếu chưa có phê duyệt thay đổi và phương án phục hồi.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-ops-lab"
VM="vm-patch-lab-01"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name}" -o table

# Kiểm tra VM và trạng thái trước khi đánh giá
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{id:id, os:storageProfile.osDisk.osType, power:powerState}" \
  --output json

# Yêu cầu đánh giá các bản cập nhật còn thiếu
az vm assess-patches \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

Ví dụ cài bản vá phân loại **Critical** và **Security**, giới hạn thời lượng và chỉ reboot khi cần:

~~~bash
# CHỈ CHẠY trên VM lab sau khi đã review thay đổi.
# Xác nhận lệnh/giá trị hỗ trợ với: az vm install-patches --help
az vm install-patches \
  --resource-group "$RG" \
  --name "$VM" \
  --classifications-to-include Critical Security \
  --maximum-duration "PT2H" \
  --reboot-setting IfRequired \
  --output json
~~~

`PT2H` là ký hiệu thời lượng ISO 8601, ở đây tương đương hai giờ. Phân loại, tùy chọn và khả năng hỗ trợ có thể khác theo phiên bản Azure CLI, OS, image và mode patch; **đối chiếu `az vm install-patches --help` trước khi chạy thật**. Lệnh không cài patch cho mọi VM tự động: nó nhắm đúng VM đã khai báo. Với Arc-enabled servers, dùng quy trình/API tương ứng với Arc thay vì mặc định `az vm` áp dụng cho một máy Arc.

### 8.3. Khi nào cài một lần thay vì theo lịch?

| Bối cảnh | Cách phù hợp |
|---|---|
| Một VM test để xác nhận bản vá cụ thể | Assessment → one-time installation → reboot/health check |
| CVE có nguy cơ khẩn cấp cần xử lý ngay | Quy trình emergency change, chọn scope nhỏ, giám sát và xác minh |
| Hàng trăm VM production cần vá định kỳ | Thiết kế lịch/maintenance configuration và rollout rings |
| VM phục vụ ứng dụng có nhiều dependency phức tạp | Kiểm thử và bảo trì theo nhóm có phê duyệt, có kế hoạch rollback |

Không lặp lại thao tác “one-time” thủ công mỗi tháng cho cả công ty nếu mục tiêu là quản trị có thể kiểm toán. Lịch và inventory giúp ngăn bỏ sót máy mới.

## 9. Scheduled patching: Maintenance configuration và dynamic scope

**Scheduled patching** kết hợp chính sách cài đặt với **maintenance configuration** có cửa sổ thời gian và tập máy áp dụng. Trong các cấu hình được hỗ trợ, Azure Maintenance cung cấp tài nguyên phục vụ điều phối lịch và lựa chọn **InGuestPatch** cho việc cài patch guest OS; không nhầm với bảo trì host/platform của Azure.

### 9.1. Một lịch bảo trì cần những thông tin nào?

| Thuộc tính | Ví dụ minh họa | Vì sao quan trọng? |
|---|---|---|
| Name/owner | `mc-guestpatch-orders-canary` / platform team | Theo dõi lịch và người chịu trách nhiệm |
| Maintenance scope | In-guest patching (`InGuestPatch`) | Khác loại bảo trì hạ tầng do nền tảng thực hiện |
| Time zone | Asia/Ho_Chi_Minh | Tránh áp dụng nhầm UTC vào giờ vận hành địa phương |
| Start time / recurrence | Thứ Ba 23:00, mỗi tuần | Xác định thời điểm dự kiến |
| Maintenance duration | Ví dụ 3 giờ, nếu được phép | Đủ cho patch, reboot và xác minh |
| Patch classification | Security, Critical theo OS | Phạm vi thay đổi |
| Include/exclude | KB/package đã được phê duyệt | Kiểm soát ngoại lệ |
| Reboot setting | IfRequired | Quy định hành vi restart |
| Target scope | Nhóm canary; VM ID hoặc dynamic scope | Không vô tình chọn toàn production |

Thiết lập múi giờ cần chú ý khi phục vụ nhiều vùng địa lý. Nếu dùng timezone có Daylight Saving Time (DST), kiểm tra lịch thực tế quanh thời điểm đổi giờ; Việt Nam không áp dụng DST, nhưng VM trong hệ thống đa quốc gia có thể dùng timezone khác.

### 9.2. Lập lịch qua Azure Portal

Quy trình có thể theo hướng sau:

1. Truy cập **Azure Update Manager → Schedule updates** hoặc phần **Maintenance configurations** thích hợp.
2. Tạo cấu hình với **maintenance scope** phù hợp cho guest patching.
3. Chọn thời gian bắt đầu, múi giờ, recurrence và maintenance window có thể đáp ứng.
4. Chọn bộ lọc cập nhật theo OS/classification/KB/package và reboot setting.
5. Chọn **Machines / Dynamic scoping** để liên kết những VM được phép.
6. Kiểm tra điều kiện **patch orchestration = Customer Managed Schedules** trên các Azure VM cần dùng lịch theo cơ chế được hỗ trợ; thực hiện chuyển mode nếu cần theo quy trình được phê duyệt.
7. Review số lượng và danh sách VM **thực sự nằm trong scope**, đặc biệt khi áp dụng qua nhiều subscription.
8. Lưu, kiểm tra lịch chạy kế tiếp, theo dõi đợt đầu và xác minh lịch sử cài đặt.

Các tên màn hình có thể thay đổi; một số loại VM/OS có ràng buộc đặc biệt. Đừng coi việc tạo maintenance configuration **tự động** đảm bảo mọi máy đã sẵn sàng hoặc sẽ chạy đúng lịch nếu VM không đáp ứng điều kiện áp dụng.

### 9.3. Dynamic scoping: lợi ích và rủi ro

Dynamic scope giúp áp dụng lịch cho VM đáp ứng tiêu chí như subscription, resource group, region, resource type, OS type hoặc tag (tùy khả năng bộ lọc tại thời điểm cấu hình). Ví dụ:

~~~text
Subscription      = app-production
Resource type     = Azure Virtual Machines
Tag application   = orders
Tag patchRing     = canary
Tag patchManaged  = true
~~~

Các tiêu chí trên là **mô hình policy minh họa**, không phải cú pháp máy đọc của Azure Update Manager. Trong portal/API thực tế, hãy cấu hình đúng tên trường và tập hợp bộ lọc được hỗ trợ.

**Ưu điểm:** VM mới được tạo theo cùng quy ước tag có thể được đưa vào phạm vi khi đánh giá dynamic scope, giảm thao tác gán từng VM.

**Rủi ro:** một thao tác đổi tag sai hoặc cấu hình bộ lọc quá rộng có thể khiến máy production tham gia lịch canary hoặc bỏ lỡ mọi lịch. Cần:

- Quản lý tag bằng Azure Policy/IaC và quy trình phê duyệt.
- Kiểm tra preview/target membership và đợt chạy đầu tiên sau khi sửa scope.
- Có bộ lọc môi trường và ring riêng, không chỉ dùng `patchManaged=true`.
- Theo dõi VM **không thuộc bất kỳ lịch nào** và máy **bị trùng nhiều lịch**.
- Kiểm tra các VM tắt máy, Arc mất kết nối hoặc không hỗ trợ mode patch hiện tại.

### 9.4. Kết hợp Azure Policy và IaC

Azure Policy có thể hỗ trợ đánh giá/triển khai một số cấu hình nền tảng và gắn chuẩn quản trị phù hợp; IaC (Bicep, ARM template, Terraform) giúp định nghĩa máy, tag, maintenance configuration và assignment theo cách review được. Nhưng **policy compliance không bảo đảm guest OS đã cài đúng patch**. Hãy đo kết quả assessment/installation song song với tính tuân thủ cấu hình.

## 10. Thiết kế patch rings: tránh cập nhật tất cả VM cùng lúc

Hãy tổ chức VM thành nhóm kiểm thử và rollout có thứ tự. Ví dụ hệ thống đơn hàng gồm sáu VM ứng dụng đứng sau Azure Standard Load Balancer, phân bố qua các Availability Zone:

| Ring | VM | Thời điểm minh họa | Điều kiện được tiếp tục |
|---|---|---|---|
| `lab` | VM test độc lập | Thứ Hai 21:00 | OS boot, dependency/CI tests đạt |
| `canary` | Một VM production ít ảnh hưởng | Thứ Ba 23:00 | Probe khỏe, lỗi API/latency không tăng bất thường |
| `prod-a` | Hai VM production | Thứ Năm 23:00 | Canary ổn qua thời gian quan sát |
| `prod-b` | Các VM production còn lại | Thứ Bảy 23:00 | Đủ capacity phục vụ khi một nhóm được reboot |

Đây là **lịch mẫu**, không phải lịch Azure Update Manager mặc định. Nhóm canary có thể là VM ít tải, hoặc VM có cùng OS/image/dependency với production để kết quả đại diện hơn; chọn sao cho một lỗi canary ít gây tác động.

### 10.1. Cách tránh downtime khi có Load Balancer

Giả sử một API chạy trên bốn backend VM. Nếu AUM cài và reboot **cả bốn cùng lúc**, LB sẽ không tạo phép màu để ứng dụng tiếp tục phục vụ. Vì vậy:

1. Xác định số backend tối thiểu cần chạy để đáp ứng tải (`N_min`).
2. Chia nhóm bảo trì sao cho trong bất kỳ cửa sổ nào còn đủ `N_min` backend khỏe.
3. Trước patch, kiểm tra readiness/health probe và khả năng tiếp nhận kết nối của những VM còn lại.
4. Điều phối traffic draining, shutdown và restart ứng dụng theo khả năng, không giả định AUM tự phối hợp chi tiết với application health probe.
5. Sau reboot, chỉ đưa VM trở lại phục vụ khi kiểm tra OS, ứng dụng và dependency đạt tiêu chí.
6. Nếu gặp lỗi trên canary, **dừng ring tiếp theo** và triển khai runbook khắc phục.

~~~mermaid
sequenceDiagram
    participant OPS as Operations
    participant LB as Azure Load Balancer
    participant VMA as VM-A (canary)
    participant VMB as VM-B (active)
    OPS->>LB: Kiểm tra có backend khỏe khác
    OPS->>VMA: Đưa readiness về trạng thái bảo trì (nếu cần)
    LB-->>OPS: Không chọn VM-A cho flow mới sau điều kiện probe
    OPS->>VMA: Cài patch / reboot trong window
    VMB-->>LB: Tiếp tục phục vụ
    OPS->>VMA: Kiểm tra OS, dịch vụ và ứng dụng
    VMA-->>LB: Readiness 200 khi đã sẵn sàng
    OPS->>OPS: Đối chiếu SLO rồi quyết định ring tiếp theo
~~~

**Probe không tự đóng ngay mọi kết nối cũ.** Với ứng dụng stateful hoặc kết nối lâu dài, cần có kế hoạch draining và shutdown an toàn. Bảo trì một DB/queue khác với một web tier stateless; không áp dụng cùng một số VM patch đồng thời cho mọi loại workload.

### 10.2. Khác biệt giữa Availability Set, Zone và Scale Set

- **Availability Set** chia VM theo fault/update domains, nhưng không đồng nghĩa mọi lịch guest patch sẽ tự động tuân theo những nhóm này theo ý định của bạn.
- **Availability Zones** giúp phân tán hạ tầng vật lý ở region hỗ trợ; một maintenance configuration nhắm toàn bộ zone vẫn có thể gây ảnh hưởng diện rộng.
- **VM Scale Sets** cần đánh giá mode (Flexible/Uniform), upgrade/patch behavior và chiến lược image-based update. Với đội vận hành dùng golden image, có thể ưu tiên dựng image đã vá rồi rolling replace instance thay vì vá “tại chỗ” mọi node.
- **Ephemeral OS disks** và workload stateless đặc biệt cần thiết kế lại mô hình cập nhật/replace; không giả định cập nhật in-place được lưu bền qua reimage.

## 11. Reboot: điểm phân biệt “đã cài” và “đã hoạt động”

Nhiều bản vá hệ điều hành, driver hoặc kernel chỉ có hiệu lực đầy đủ sau reboot. AUM có thể cho chọn chính sách reboot theo các tùy chọn được hỗ trợ; cách hiển thị chính xác và tính hợp lệ phụ thuộc OS và thao tác.

| Reboot setting | Ý nghĩa dự kiến | Cần lưu ý |
|---|---|---|
| `IfRequired` | Reboot khi patch/OS cho biết cần | Có thể gián đoạn dịch vụ, phải tính vào maintenance window |
| `Never` | Không chủ động reboot theo lựa chọn | Cập nhật có thể vẫn ở trạng thái pending; rủi ro có thể chưa được giảm hoàn toàn |
| `Always` | Reboot theo chính sách sau quá trình cài | Có thể reboot ngay cả khi không cần cho patch; cần phê duyệt |

**Không xem `Never` là phương án an toàn vì “tránh downtime”.** Nếu kernel được cập nhật trên Linux nhưng máy chưa reboot, kernel đang chạy có thể vẫn là phiên bản cũ. Trên Windows, các cập nhật có yêu cầu reboot cũng có thể chưa có hiệu lực đầy đủ.

### Trước reboot

- Xác nhận đã có **backup/recovery point phù hợp** và đã thử quy trình khôi phục ở mức cần thiết.
- Kiểm tra mức tải, dependency, giao dịch đang thực hiện và khả năng draining.
- Với DB/stateful service, kiểm tra replication/quorum, trạng thái backup, vai trò leader/primary và quy trình failover.
- Xác định máy có yêu cầu bảo trì thủ công sau reboot không (decrypt, unlock, mount, license, reconnect).
- Kiểm tra thời lượng window đủ cho OS startup, application warm-up và health verification.

### Sau reboot

- OS boot, network, DNS, disks, mount points và các dịch vụ nền tảng hoạt động.
- Windows service/systemd service cần thiết đang chạy.
- Phiên bản kernel/package/KB hoặc thông tin cập nhật phù hợp với mục tiêu.
- Application health probe, giao dịch nghiệp vụ và kết nối đến data store/queue/API ngoài đều đạt.
- Agent/log/alert vẫn hoạt động, không xuất hiện lỗi mới bất thường.

### Reboot ngoài cửa sổ

Kiểm tra cài đặt auto-update hiện có của Windows/WSUS và Linux OS. AUM chỉ là một trong những cơ chế có thể kích hoạt cập nhật; OS-orchestrated, auto-upgrade ứng dụng, extension hoặc automation khác có thể tạo restart độc lập. Nếu bị reboot ngoài lịch, điều tra **tác nhân thực sự** qua event logs, package manager history và Azure Activity Log trước khi đổ lỗi cho một maintenance configuration.

## 12. Kiểm thử và kế hoạch rollback trước khi patch production

Patch là thay đổi có rủi ro, đặc biệt với VM chứa middleware, driver hoặc legacy application. Một chiến lược patch tốt phải trả lời: **nếu ứng dụng không lên sau reboot, đưa dịch vụ trở lại bằng cách nào?**

### 12.1. Chuẩn bị bản khôi phục

- Với VM thông thường, dùng **Azure Backup** hoặc cơ chế backup đúng RPO/RTO, bảo đảm recovery point có thể phục hồi.
- Với ứng dụng có database, xem xét **application-consistent backup** và các bước restore dữ liệu riêng; không cho rằng snapshot ổ đĩa là bảo đảm tính nhất quán mọi giao dịch.
- Lưu **image/configuration/manifest** trước khi cập nhật, gồm OS version, package inventory, cấu hình dịch vụ và release ứng dụng.
- Với VM được xây từ IaC/image, cân nhắc tạo bản image mới đã vá và rolling replacement thay vì sửa đổi khó khôi phục trên máy đang chạy.
- Xác định thời gian rollback tối đa và người có quyền thực hiện thao tác khôi phục.

**Rollback không phải lúc nào cũng là “uninstall patch”.** Một số cập nhật không thể gỡ hoặc gỡ bỏ có thể làm hỏng dependency. Tùy tình huống, phương án đúng là restore recovery point, thay VM bằng image cũ, failover workload hoặc khôi phục ứng dụng.

### 12.2. Tiêu chí thành công

| Lớp kiểm tra | Ví dụ |
|---|---|
| OS | VM boot thành công, disk mounted, không pending reboot ngoài kế hoạch |
| Security | Bản vá mục tiêu có mặt, phiên bản bị ảnh hưởng không còn theo advisory phù hợp |
| Network | DNS, NSG, firewall, private endpoint, route và kết nối outbound còn đúng |
| Application | Health probe, login/API, một giao dịch thử và xử lý queue thành công |
| Data | DB/Storage truy cập được, backup/replication còn khỏe |
| SLO | Error rate, latency, CPU/RAM và throughput trở lại ngưỡng chấp nhận |
| Observability | Agent, log, alert và dashboard không bị gián đoạn sau reboot |

Nếu canary thất bại, không chạy tiếp lịch production khác chỉ vì giờ bắt đầu đã đến. Cần cơ chế **hold/phê duyệt** các ring kế tiếp phù hợp với công cụ và quy trình tổ chức.

## 13. Giám sát, báo cáo và đo patch compliance

Để vận hành nhiều subscription, cần một bản ghi nhất quán cho từng máy: **ai sở hữu, chính sách nào áp dụng, đánh giá gần nhất lúc nào, đã cài gì, có lỗi không và trạng thái ứng dụng sau patch**.

### 13.1. Tách trạng thái kỹ thuật thành nhiều chiều

| Trạng thái | Ý nghĩa | Bằng chứng nên lưu |
|---|---|---|
| Assessment succeeded | Đánh giá lấy được thông tin update tại thời điểm tương ứng | Thời gian đánh giá, OS, bản vá còn thiếu, resource ID |
| Assessment failed | Không xác định được patch status | Error code, extension/agent status, nguồn update và log |
| Installation succeeded | Cài đặt hoàn thành trong phạm vi thao tác | Run ID, patch được cài, kết quả, thời lượng |
| Installation partially succeeded/failed | Có patch lỗi, bị bỏ qua hoặc không được cài | Lỗi từng package/KB, reboot status, hành động khắc phục |
| Pending reboot | Có thay đổi cần restart để hoàn tất | OS state, maintenance window kế tiếp, owner |
| Workload verified | Ứng dụng hoạt động theo tiêu chí kiểm chứng | Health checks, synthetic test, SLO, xác nhận owner |
| Exception approved | Một hoặc nhiều patch được tạm hoãn có kiểm soát | Rủi ro, biện pháp bù trừ, hạn xử lý, người phê duyệt |

Nếu một VM hiển thị assessment cũ hơn 10 ngày, **đừng tính nó là “compliant” chỉ vì lần đánh giá cuối không có bản vá còn thiếu**. Nó phải nằm trong nhóm `unknown/stale` cho tới khi đánh giá mới thành công.

### 13.2. Nguồn dữ liệu có thể sử dụng

- **Azure Update Manager**: dashboard, assessment, lịch sử cài đặt và danh sách VM được quản lý.
- **Azure Resource Graph**: giúp truy vấn trạng thái tài nguyên/patch theo loại dữ liệu và quyền được hỗ trợ, hữu ích khi quản lý nhiều subscription.
- **Azure Monitor / Log Analytics**: thu thập telemetry hệ thống và ứng dụng, tạo cảnh báo theo nhu cầu.
- **Azure Activity Log**: ghi dấu thay đổi control plane như lịch bảo trì, assignment, cấu hình VM và quyền trong phạm vi hoạt động được hỗ trợ.
- **Microsoft Defender for Cloud**: cung cấp góc nhìn về tư thế bảo mật, CVE hoặc khuyến nghị liên quan theo các khả năng/gói được bật.
- **ITSM/change management**: liên kết lần chạy patch với ticket, phê duyệt, bằng chứng hồi quy và incident.

Không mặc định dữ liệu AUM đã xuất vào một bảng Log Analytics cụ thể. Loại bản ghi, schema và cách truy vấn có thể khác giữa **Azure Resource Graph**, AUM và agent-based logs; trước khi viết dashboard/KQL, xác định nguồn dữ liệu thực tế và xem schema được dịch vụ cung cấp.

### 13.3. Chỉ số KPI có ý nghĩa

| KPI | Gợi ý đo | Lưu ý |
|---|---|---|
| **Coverage** | VM thuộc phạm vi quản lý / tổng số VM cần patch | Tách VM ngoại lệ và OS không hỗ trợ |
| **Freshness** | VM có assessment thành công trong khoảng thời gian quy định | Tránh đếm trạng thái stale là khỏe |
| **Critical patch latency** | Thời gian từ khi patch được phê duyệt/khả dụng đến khi cài đặt và hoàn tất reboot | Phân tầng theo mức rủi ro của ứng dụng |
| **Installation success** | Số run VM thành công / số run VM đã thực thi | Nên phân tích cả kết quả từng update |
| **Pending reboot age** | VM còn pending reboot quá thời gian cho phép | Patch có thể chưa có hiệu lực đầy đủ |
| **Unmanaged machines** | VM không gắn chính sách/schedule hoặc không được assessment | Dễ bỏ sót máy mới/máy Arc |
| **Application regression** | Lỗi/latency sau patch so với baseline | Đo chất lượng dịch vụ, không chỉ thao tác OS |
| **Exception aging** | Bản vá bị hoãn quá hạn phê duyệt | Ngăn bỏ qua bảo mật vô thời hạn |

Các KPI phải có **mẫu số rõ ràng**, không gộp máy đã tắt vĩnh viễn hoặc chưa onboard vào tỷ lệ “đã vá” mà không giải thích. Một đội có thể đạt tỷ lệ cài đặt cao nhưng vẫn bỏ sót một số máy Internet-facing quan trọng nhất; nên báo cáo theo **mức độ rủi ro**, không chỉ phần trăm trung bình.

### 13.4. Alert và runbook

Tạo cảnh báo có người xử lý cho những tình huống:

1. VM mới không có owner, ring hoặc patch schedule sau ngưỡng thời gian quy định.
2. Assessment không thành công qua nhiều chu kỳ.
3. Security update quan trọng còn thiếu quá SLA của tổ chức.
4. Installation run thất bại hoặc dừng do vượt maintenance window.
5. Reboot pending kéo dài.
6. Health probe/availability của ứng dụng giảm sau cửa sổ patch.
7. Maintenance configuration bị sửa hoặc dynamic scope mở rộng ngoài dự kiến.

Mỗi alert cần chỉ rõ **VM resource ID, subscription, ring, tác vụ vừa chạy, người trực, thời hạn phản hồi và cách tạm dừng ring tiếp theo**. Không tạo cảnh báo chỉ ghi `VM non-compliant` rồi không có bước khắc phục hoặc người chịu trách nhiệm.

## 14. Troubleshooting: khi Update Manager không thực hiện đúng kỳ vọng

### 14.1. VM không xuất hiện hoặc không thể assessment

Các nguyên nhân có thể bao gồm:

- Subscription/resource group/region không nằm trong bộ lọc hoặc tài khoản thiếu quyền xem.
- VM bị dừng, bị xóa, đổi resource ID hoặc đã chuyển subscription.
- OS/image hoặc patch orchestration mode không tương thích với thao tác mong muốn.
- Agent/extension có lỗi, không được hỗ trợ hoặc chưa sẵn sàng.
- Windows Update/WSUS hoặc Linux repository không truy cập được.
- Arc server mất kết nối Azure, không đủ điều kiện hoặc agent không khỏe.
- DNS, proxy hoặc egress firewall chặn endpoint update/management.
- Assessment cũ chưa được làm mới, hoặc đang chờ một thao tác khác hoàn tất.

Quy trình kiểm tra:

1. Xác nhận **Azure resource ID**, nguồn onboarding và OS/version.
2. Đọc trạng thái Power/Arc connectivity, agent/extension.
3. Kiểm tra patch mode, periodic assessment, schedule assignment và role assignment.
4. Kiểm tra DNS/network tới service endpoints và repository update theo OS.
5. Xem log OS và thông báo lỗi chi tiết của AUM.
6. Thực hiện on-demand assessment trong lab/test sau khi sửa nguyên nhân để xác minh.

### 14.2. Windows Update lỗi

Trong guest Windows, từ PowerShell với quyền đọc phù hợp:

~~~powershell
# Tình trạng OS và thời điểm boot gần nhất
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, BuildNumber, LastBootUpTime

# Danh sách một số hotfix có thể được ghi nhận qua API tương ứng
Get-HotFix | Sort-Object InstalledOn -Descending |
  Select-Object -First 15

# Kiểm tra tình trạng Windows Update service
Get-Service wuauserv
~~~

`Get-HotFix` **không liệt kê chắc chắn mọi loại update/package đã cài**. Dùng thêm Update History/Windows Update logs, thông tin bản build và tooling của OS để xác nhận patch mục tiêu. Nếu máy thuộc WSUS, kiểm tra policy/GPO, quyền truy cập server WSUS, approval và đồng bộ catalog; không ép chuyển trực tiếp sang public Windows Update nếu chính sách tổ chức yêu cầu WSUS.

Những trường hợp thường gặp:

- Đang có pending reboot từ lần cập nhật trước.
- Windows Update Agent, service hoặc servicing stack có lỗi.
- Thiếu dung lượng ổ hệ điều hành.
- GPO/WSUS và lịch AUM tạo xung đột.
- Update bị superseded, chưa được WSUS approve hoặc không phù hợp với image đang chạy.

Khi có lỗi, ghi nhận **Windows Update error code** và đối chiếu log chính thức, không chạy script reset Windows Update Agent hàng loạt chỉ vì một patch hiển thị failed.

### 14.3. Linux repository, package locks và kernel

Trên Ubuntu/Debian:

~~~bash
# Thông tin distro và kernel đang chạy
cat /etc/os-release
uname -r

# Liệt kê package có thể nâng cấp từ metadata hiện có
apt list --upgradable

# Tình trạng disk và khả năng phân giải DNS
df -h /
getent hosts archive.ubuntu.com
~~~

Trên các distro dùng RPM/DNF, có thể kiểm tra:

~~~bash
cat /etc/os-release
uname -r

# Lệnh đọc trạng thái, không phải lệnh cài patch
sudo dnf check-update
sudo dnf history list
~~~

`dnf check-update` có thể trả về **exit code 100 khi có cập nhật**, không nhất thiết là lỗi command; cần đọc cả output. Với SUSE, dùng công cụ phù hợp như `zypper` và repository được doanh nghiệp cấu hình. Các command minh họa không phải tập lệnh tự động sửa mọi distro và có thể yêu cầu quyền khác nhau.

Nguồn vấn đề phổ biến trên Linux:

- Repository unreachable, DNS/proxy/firewall hoặc CA/TLS bị lỗi.
- OS đã hết vòng đời hỗ trợ hoặc repo không còn phát hành metadata đúng.
- APT/DPKG/DNF lock do một tác vụ cập nhật khác đang chạy.
- Dependency conflict, thiếu disk space/inode hoặc package bị hold/pin.
- Kernel mới đã cài nhưng `uname -r` vẫn là kernel cũ do chưa reboot.
- Bản vá mang nhãn security không được distro phân loại theo metadata mà Update Manager mong đợi.

Không xóa file lock của package manager hoặc cưỡng bức kill tiến trình đang cài cập nhật khi chưa xác định tác vụ thực sự đang làm gì; việc đó có thể gây hỏng package database.

### 14.4. Azure VM agent, extension và trạng thái máy

Ví dụ lệnh **chỉ đọc** cho Azure VM:

~~~bash
az account set --subscription "$SUBSCRIPTION_ID"

az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --output json

az vm extension list \
  --resource-group "$RG" \
  --vm-name "$VM" \
  --output table
~~~

Đừng mặc định một extension có tên cụ thể phải hiện trên mọi OS/SKU trong cùng trạng thái. Kiểm tra yêu cầu patch extension theo loại máy tại thời điểm vận hành và đọc **substatus/error message** trước khi reinstall extension. Reinstall/repair extension là thao tác thay đổi hệ thống, cần phê duyệt và cân nhắc tác động.

### 14.5. Cài đặt vượt maintenance window hoặc reboot không hoàn tất

Nếu việc cài đặt kéo dài hơn dự tính, cần xác định:

- Có package lớn, dependency/servicing stack hay tốc độ repository chậm?
- Máy bị nghẽn disk/CPU/network, hoặc service update phải chạy nhiều giai đoạn?
- Window có đủ thời gian cho **cài + reboot + kiểm tra ứng dụng** không?
- AUM đã dừng yêu cầu nhưng guest OS còn đang xử lý hay pending reboot?
- Còn một tác vụ cập nhật độc lập đang chạy song song?

**Không tăng window vô hạn** để “tỷ lệ thành công 100%” mà không hiểu nguyên nhân. Với VM có downtime đắt đỏ, tốt hơn chia nhóm hoặc thay image theo rolling deployment.

## 15. Bảo mật quyền quản trị và quản lý chi phí

### 15.1. Mô hình phân quyền

Một nhóm phát triển có thể cần xem trạng thái patch của VM ứng dụng, nhưng không nhất thiết được quyền thay lịch bảo trì của toàn bộ production. Nhóm bảo mật có thể cần xem reporting và theo dõi SLA, trong khi nhóm nền tảng giữ quyền tạo maintenance configuration và lập lịch.

Các guardrail nên có:

- **Azure RBAC** theo scope nhỏ nhất, ưu tiên group Microsoft Entra cho role assignment.
- **Privileged Identity Management** khi dùng quyền cao và tính năng được phép.
- **Azure Policy** để kiểm kê/tag/đánh giá posture theo khả năng policy được triển khai.
- **Azure Activity Log** cho thay đổi config và **change ticket** cho phê duyệt patch.
- **Private networking/controlled egress** để guest chỉ kết nối nguồn update/endpoints đã phê duyệt.
- Giữ an toàn secret/proxy credentials, không ghi token hoặc mật khẩu repository vào log.

Patch management không nên trở thành lý do cấp quyền quản lý subscription quá rộng cho script automation. Với pipeline dùng managed identity hoặc service principal, hãy cấp hành động cần thiết và phân tách môi trường lab/production.

### 15.2. Chi phí Azure Update Manager

Chi phí không chỉ là giá dịch vụ AUM. Cần dự toán:

| Hạng mục | Điểm cần kiểm tra |
|---|---|
| **Azure VM** | Điều kiện sử dụng Update Manager trên Azure VM và mô hình phí hiện hành |
| **Azure Arc-enabled servers** | Có thể có phí quản lý cập nhật trên mỗi server, trừ các trường hợp được hưởng quyền/giấy phép phù hợp |
| **Microsoft Defender for Servers** | Một số gói có thể mang theo quyền sử dụng AUM; kiểm tra gói, scope và điều kiện áp dụng |
| **Băng thông và proxy** | Dữ liệu tải từ Windows Update/WSUS hoặc Linux repository, NAT/Firewall, hybrid network |
| **Log Analytics/Monitor** | Ingest, retention, alert hoặc xuất báo cáo theo quy mô |
| **Backup/snapshot** | Recovery points và dung lượng giữ thêm trước/đợt cập nhật |
| **Tính sẵn sàng** | VM dự phòng, thêm zone/instance, đội trực và chi phí ngừng dịch vụ |

Đừng ghi cứng giá tiền vào tài liệu hạ tầng vì thay đổi theo điều khoản và khu vực. Dùng thông tin thanh toán/giá hiện hành của Azure subscription và Azure Cost Management để xác nhận **máy nào có phí, máy nào thuộc diện hưởng quyền**, nhất là máy được kết nối qua Azure Arc.

### 15.3. Bài toán cân bằng rủi ro và chi phí

Giả sử cài patch mỗi tuần giảm thời gian tồn tại CVE nhưng làm tăng số lần reboot, rủi ro gián đoạn và giờ trực. Ngược lại, chỉ vá mỗi quý có thể khiến hệ thống chịu rủi ro lớn trước lỗ hổng đang bị khai thác.

Một mô hình hợp lý là:

- **Emergency patches:** quy trình nhanh dựa trên mức rủi ro thực tế, thay vì chờ lịch thường kỳ.
- **Routine security patches:** chu kỳ tương đối ngắn, có canary và theo dõi.
- **Non-security updates:** áp dụng sau đánh giá tương thích hoặc trong đợt cập nhật nền tảng.
- **End-of-support OS:** có kế hoạch nâng cấp/migrate, vì AUM không thể tạo ra bản vá mà vendor không còn phát hành.

Tối ưu bằng kết quả **time-to-remediate**, tỷ lệ thành công, thời gian gián đoạn và công vận hành, không chỉ bằng cách giảm số lần cài cập nhật.

## 16. Ví dụ hoàn chỉnh: hệ thống đơn hàng nhiều subscription

**Bối cảnh doanh nghiệp giả định:**

- Subscription `platform-management` chứa tài nguyên giám sát, policy và quy trình vận hành chung.
- Subscription `app-orders-prod` chứa sáu VM web/API phân bố qua các Availability Zone, phía trước là Azure Load Balancer.
- Subscription `app-orders-test` có môi trường giống production để thử nghiệm.
- Hai Windows VM riêng chạy các tác vụ batch kết nối Azure SQL; sáu Linux VM nêu trên dùng cho API không trạng thái.
- Một máy chủ Windows on-premises kết nối bằng Azure Arc, phụ thuộc WSUS và đường VPN.
- Yêu cầu RTO dịch vụ đơn hàng thấp; mỗi lần bảo trì phải giữ ít nhất bốn backend khỏe.

**Mục tiêu:** cài cập nhật bảo mật đúng hạn, không reboot đồng loạt và có thể chứng minh tình trạng sau patch.

### 16.1. Kiến trúc điều phối

~~~mermaid
flowchart TB
    AUM[Azure Update Manager]
    AUM --> MC1[Maintenance config - Lab/Test]
    AUM --> MC2[Maintenance config - Canary]
    AUM --> MC3[Maintenance config - Prod A]
    AUM --> MC4[Maintenance config - Prod B]
    MC1 --> TEST[VM test]
    MC2 --> CANARY[1 VM canary]
    MC3 --> PROD1[2 VM production]
    MC4 --> PROD2[3 VM production]
    CANARY --> LB[Health probe / Application monitoring]
    PROD1 --> LB
    PROD2 --> LB
    AUM -. Báo cáo kết quả .-> OPS[Nhóm vận hành / ITSM]
    OPS -. Phê duyệt rollout .-> MC3
    OPS -. Phê duyệt rollout .-> MC4
    ARC[Arc server dùng WSUS] --> AUM
~~~

Sơ đồ biểu diễn luồng quyết định. **Không mặc định AUM tự tạo bước phê duyệt bắt buộc giữa các maintenance configuration.** Nếu lịch được tạo độc lập, chúng có thể chạy theo giờ đã đặt ngay cả khi canary thất bại. Cần thiết kế cơ chế thủ công hoặc automation thực sự thực hiện “hold/release” các ring kế tiếp.

### 16.2. Kế hoạch triển khai theo ngày

| Ngày/giờ giả định | Hoạt động | Người chịu trách nhiệm | Điểm kiểm soát |
|---|---|---|---|
| Thứ Hai 09:00 | Assessment tất cả VM và xuất baseline | Platform/Security | Còn VM chưa scan hoặc EOL không? |
| Thứ Hai 22:00 | Patch test, reboot, smoke test | QA/Operations | Các tác vụ giao dịch thử đạt |
| Thứ Ba 23:00 | Patch một VM canary production | Operations | Ít nhất năm backend khỏe; error rate ổn |
| Thứ Tư 09:00 | Xem kết quả canary, quyết định tiếp tục | Service owner | Review logs, latency và database |
| Thứ Năm 23:00 | Patch nhóm production A | Operations | Còn đủ bốn backend khi nhóm A bảo trì |
| Thứ Bảy 23:00 | Patch nhóm production B | Operations | Nhóm A đã hoạt động ổn định |
| Chủ Nhật 09:00 | Re-assessment, audit và đóng change | Security/Operations | Đủ bằng chứng hoặc có incident/ngoại lệ |

Mốc thời gian chỉ để minh họa; tổ chức phải tính giờ địa phương, múi giờ Azure, SLA nghiệp vụ và tải thực tế. Các máy batch/Arc có thể cần **lịch riêng** vì dependency, WSUS và cửa sổ downtime khác web tier.

### 16.3. Các quyết định kiến trúc

**Một:** không cập nhật VM của cùng workload chỉ dựa vào vị trí resource group. Gắn tag `application`, `environment`, `patchRing` và `owner` để chia scope; kiểm tra danh sách máy thực tế mỗi khi thay đổi lịch.

**Hai:** không dùng health probe HTTP `200` đơn giản làm tiêu chí duy nhất. Sau reboot, phải kiểm tra đường vào Load Balancer, xác thực API, kết nối SQL qua private endpoint, xử lý một đơn hàng giả lập và khả năng truy cập đối tác.

**Ba:** với Windows batch VM, cần xác định WSUS/GPO có cho phép cài đúng lịch và liệu job batch có thể dừng/tiếp tục an toàn sau reboot hay không.

**Bốn:** với Linux API VM, theo dõi version kernel đang chạy và trạng thái pending reboot. Nếu repository thiếu metadata security, team security phải đối chiếu advisory ngoài dashboard.

**Năm:** Arc server có thể dùng lịch bảo trì phù hợp nhưng cần kiểm tra kết nối Arc, nguồn WSUS và licensing; không gộp nó vào một nhóm giả định reboot giống Azure VM.

## 17. Checklist thao tác trước, trong và sau mỗi đợt

### Trước khi bắt đầu

- [ ] Đã xác định chủ sở hữu, mức độ quan trọng và nhóm patch của từng VM.
- [ ] Assessment mới được thực hiện, danh mục patch được phê duyệt.
- [ ] VM/OS/image/extension/Arc đủ điều kiện theo tài liệu vận hành.
- [ ] Nguồn Windows Update/WSUS hoặc Linux repo truy cập được từ mạng máy.
- [ ] Patch orchestration và schedule không trùng hoặc xung đột với tác vụ tự động khác.
- [ ] Maintenance configuration có scope, múi giờ, thời lượng và reboot policy chính xác.
- [ ] Có backup/recovery point và phương án rollback đã được kiểm tra.
- [ ] Canaries, giới hạn số backend bảo trì đồng thời và người trực đã được xác nhận.
- [ ] Hệ thống monitoring/health probe và lưu trữ log đang hoạt động.

### Trong thời gian bảo trì

- [ ] Theo dõi trạng thái installation và lỗi từng KB/package.
- [ ] Theo dõi CPU, disk, network, response time và trạng thái máy.
- [ ] Phối hợp draining/quorum và reboot theo kế hoạch.
- [ ] Theo dõi SLO, cảnh báo ứng dụng, kết nối dữ liệu và trải nghiệm client.
- [ ] Tạm dừng nhóm tiếp theo nếu canary hoặc phụ thuộc quan trọng gặp lỗi.

### Sau khi bảo trì

- [ ] Kiểm tra máy boot trở lại, service chạy và network/DNS hoạt động.
- [ ] Xác minh update mục tiêu và trạng thái pending reboot.
- [ ] Chạy synthetic transaction/smoke test và kiểm tra DB/queue/API.
- [ ] Yêu cầu assessment mới; đối chiếu patch còn thiếu, failed và excluded.
- [ ] Thu thập logs, run history, ticket và xác nhận từ service owner.
- [ ] Tạo incident hoặc exception có thời hạn cho VM chưa hoàn tất.
- [ ] Xem chi phí phát sinh và điều chỉnh lịch/capacity cho đợt kế tiếp.

Checklist cần được tích hợp vào runbook thực tế. “Thành công” phải nghĩa là **bản vá đạt mục tiêu và workload tiếp tục phục vụ trong giới hạn chấp nhận**, không chỉ một thao tác API trả về thành công.

## 18. Các tình huống nâng cao thường bị hiểu sai

### 18.1. Assessment xanh nhưng Defender vẫn báo CVE

Không phải lúc nào hai hệ thống cũng đánh giá giống nhau:

- Update Manager báo các **bản cập nhật OS còn thiếu** theo nguồn catalog/repository và thời điểm assessment.
- Defender for Cloud hoặc vulnerability scanner có thể đánh giá **CVE, phần mềm cài thêm, cấu hình hoặc artifact** theo nguồn advisory riêng.
- Vendor có thể chưa phát hành package phù hợp cho phiên bản OS; máy đã hết hỗ trợ hoặc package bị hold.
- Một số bản vá đã cài nhưng chưa reboot, hoặc scanner nhận diện theo bản build và trạng thái OS khác.

Khi hai kết quả mâu thuẫn, hãy đối chiếu **resource ID, OS version, package/KB, bản phát hành được hỗ trợ, thời điểm scan và yêu cầu reboot**. Không đơn giản đánh dấu false positive hoặc kết luận Azure Update Manager đã bỏ sót.

### 18.2. Patch thành công nhưng ứng dụng không khỏe

Ví dụ một bản cập nhật hệ thống thay đổi runtime, driver hoặc TLS behavior khiến ứng dụng trả HTTP 500. AUM có thể báo cài thành công vì package được cài đúng, nhưng người dùng vẫn gặp lỗi. Chính vì vậy cần:

1. Giữ liên kết giữa **patch run ID** và **application deployment/change ticket**.
2. So sánh latency, error rate, restart count và dependency failures trước/sau patch.
3. Dừng rollout, chuyển traffic khỏi VM lỗi nếu kiến trúc cho phép.
4. Khôi phục theo recovery point/image hoặc sửa cấu hình ứng dụng theo runbook.
5. Sau khôi phục, đối chiếu lại tình trạng patch để xác định lỗ hổng nào có thể tái xuất hiện.

### 18.3. VM tắt trong toàn bộ cửa sổ bảo trì

Không nên giả định một maintenance configuration tự bảo đảm bật máy, cài đủ patch, rồi tắt lại đúng trạng thái cũ. Hành vi với máy đang stopped/deallocated phụ thuộc thao tác và khả năng hỗ trợ; nếu VM không chạy khi lịch diễn ra, cần kiểm tra lịch sử và thiết kế **catch-up process**. Một số đội có thể lên lịch bật VM trước, patch, đánh giá rồi đưa máy về trạng thái mong muốn bằng automation đã được kiểm thử.

VM thường xuyên tắt cũng cần tuân thủ SLA patch: phải có thời điểm đánh giá/cài đặt trước khi mở lại để phục vụ workload, không để máy cũ quay lại mạng production với lỗ hổng chưa xử lý.

### 18.4. Hotpatch có loại bỏ nhu cầu reboot không?

Một số phiên bản/edition Windows Server và cơ chế Linux có khả năng **hotpatch/live patch** trong phạm vi cụ thể. Những tính năng này phụ thuộc hỗ trợ OS, image, bản cập nhật và điều kiện licensing. Không suy rộng rằng “bật AUM” sẽ khiến mọi bản vá được áp dụng không reboot.

Ngay cả khi hệ điều hành hỗ trợ hotpatch cho một số security fix, vẫn có cập nhật nền tảng, phiên bản kernel lớn, driver hoặc baseline cần reboot. Thiết kế maintenance window và khả năng chịu lỗi vẫn cần thiết.

### 18.5. Golden image được vá rồi có cần quản lý patch VM không?

Có. Một image chuẩn chỉ cho biết trạng thái **tại thời điểm build**. Khi instance hoạt động nhiều tuần hoặc nhiều tháng, các cập nhật mới xuất hiện. Có hai cách tiếp cận:

- **In-place patching:** quản lý các VM đang tồn tại và theo dõi trạng thái của chúng.
- **Image-based replacement:** pipeline dựng image mới đã cập nhật, kiểm thử, rồi rolling replace VM/instance.

Một hệ thống có thể kết hợp cả hai nhưng phải xác định nguồn sự thật, điều kiện rollback, dữ liệu lưu bền và lịch bảo trì. Với VM Scale Sets và workload stateless, image-based replacement có thể là phương án dễ kiểm soát hơn; với server stateful/legacy, in-place patching có thể phù hợp khi có phương án phục hồi rõ ràng.

### 18.6. Azure Arc dùng cùng một lịch với Azure VM được không?

Ở những kịch bản được hỗ trợ, đội vận hành có thể quản lý cả Azure VM và Arc server qua Update Manager, nhưng **không có nghĩa điều kiện mạng, extension, OS, phí và reboot giống nhau**. Ví dụ một Arc Windows Server dùng WSUS nội bộ chỉ tải được patch khi VPN và WSUS hoạt động; còn Azure VM Linux có thể dùng repository riêng qua firewall.

Tách runbook theo loại máy, có bước kiểm tra kết nối/nguồn cập nhật và xác nhận đối tượng được hỗ trợ trước khi đưa cả hai vào cùng một lịch.

## 19. Bài thực hành: lập kế hoạch patch cho kiến trúc Azure

**Bối cảnh:** Doanh nghiệp có 12 VM:

- 6 Linux VM chạy web/API trong subscription `prod-orders`, đặt sau Standard Load Balancer và phân tán theo zone.
- 2 Windows Server VM chạy batch jobs, phải hoàn tất tác vụ thanh toán trước khi reboot.
- 2 VM ở subscription `test-orders` dùng để kiểm tra cập nhật trước production.
- 2 máy chủ on-premises chạy Windows, đã onboard Azure Arc, dùng WSUS nội bộ.

Hệ thống có một CVE critical cần xử lý theo chính sách khẩn cấp trong vòng 72 giờ. Nhóm phát triển báo một patch trước đó từng khiến ứng dụng lỗi TLS khi gọi API thanh toán. Doanh nghiệp yêu cầu ít nhất bốn backend web còn phục vụ trong giờ bảo trì, dữ liệu đơn hàng không được mất và phải lưu bằng chứng cho kiểm toán.

### Yêu cầu thực hiện

1. **Kiểm kê:** lập bảng 12 máy gồm resource ID/Arc ID, OS/version, subscription, owner, app, environment, patch ring, update source và mức độ quan trọng.
2. **Đánh giá:** chọn thao tác assessment phù hợp và giải thích vì sao phải ghi thời điểm đánh giá, patch classification, pending reboot, source update và lỗi agent.
3. **Phân nhóm:** chia test, canary, prod-a/prod-b, Windows batch và Arc. Quyết định nhóm nào không được reboot cùng lúc.
4. **Lập lịch:** thiết kế maintenance configuration, timezone, recurrence, duration, reboot setting và cách áp dụng dynamic scope bằng tag đủ hẹp.
5. **Patch policy:** chọn cách xác định KB/package thực sự xử lý CVE; mô tả trường hợp metadata Linux thiếu classification Security và cách xử lý.
6. **Pre-check:** nêu quy trình backup, phục hồi, kiểm tra tải, đóng luồng batch và health probe trước đợt vá.
7. **Canary:** mô tả bước xác nhận TLS của API thanh toán, database connectivity và tiêu chí dừng rollout sau canary.
8. **Arc:** giải thích cách xác minh WSUS và Arc connectivity trước khi cài patch cho máy on-premises.
9. **Sau patch:** trình bày cách xác nhận bản vá đã có hiệu lực sau reboot; theo dõi lỗi ứng dụng và tạo báo cáo cho security owner.
10. **Sự cố:** lập runbook khi hai VM reboot đồng thời và health probe báo số backend khỏe giảm xuống dưới ngưỡng cho phép.
11. **Chi phí và quyền:** xác định phần nào có thể phát sinh phí AUM/Arc, monitoring/backup và role assignment nhỏ nhất cho patch operator.
12. **Ngoại lệ:** giả sử một Windows batch VM không thể cài patch do tương thích; viết các trường bắt buộc của risk exception cùng ngày hết hạn.

### Khung trả lời mẫu

| Máy/nhóm | Scope và patch mode cần xác minh | Window | Bằng chứng sau patch |
|---|---|---|---|
| Linux test | Azure VM, mode hỗ trợ cài theo lịch | Thứ Hai 21:00 | Kernel/package, smoke test, API TLS |
| Một canary Linux production | `patchRing=canary`, duy trì backend khác | Thứ Ba 23:00 | Probe 200, SLO ổn, cài patch mục tiêu |
| Hai Linux production tiếp theo | `patchRing=prod-a`, đủ backend hoạt động | Sau khi canary được phê duyệt | Error rate/latency không tăng, assessment mới |
| Ba Linux production cuối | `patchRing=prod-b` | Đợt tiếp theo có kiểm soát | Đã trở lại pool, không pending reboot |
| Hai Windows batch | Lịch riêng phối hợp hoàn tất batch/DB | Cuối kỳ batch được phép | Windows build/hotfix, job integrity |
| Hai Arc Windows | Arc connectivity + WSUS + licensing | Lịch riêng theo on-premises | Patch history, reboot state, hệ thống nội bộ |

*Lưu ý:* Với sáu VM web, nếu một lúc bảo trì ba VM mà yêu cầu tối thiểu bốn backend hoạt động, bảng `prod-b` trên **không thể được thực thi đồng thời cả ba VM**. Cần phân bổ thành các lượt **tối đa hai VM** (và ít hơn nếu hệ thống đang thiếu instance khỏe), hoặc điều chỉnh capacity/kiến trúc trước bảo trì. Đây là một phần chủ ý của bài tập: **lịch bảo trì phải kiểm chứng điều kiện N_min, không chỉ gắn nhãn ring**.

### Ví dụ cách chứng minh tính sẵn sàng

Giả sử sáu backend khỏe trước khi cài:

~~~text
N_total = 6 backend
N_min   = 4 backend phải sẵn sàng
N_max_maintenance = N_total - N_min = 2 backend

Trước mỗi lượt:
- Đếm backend HEALTHY thật (không chỉ VM Running).
- Nếu có 1 backend lỗi sẵn: chỉ còn 5 healthy, tối đa 1 VM bảo trì.
- Nếu có 2 backend lỗi sẵn: chỉ còn 4 healthy, không patch thêm VM nào.
~~~

Tính toán đơn giản trên phù hợp khi backend có công suất tương đương và traffic phân phối hợp lý. Với capacity không đồng đều, phải dùng **khả năng chịu tải thực tế** thay vì chỉ đếm số VM. Ngoài ra, cần kiểm tra giới hạn failover của database và dịch vụ dùng chung.

### Tiêu chí chấm tự đánh giá

Bài thực hành đạt yêu cầu khi người học giải thích được:

- **Máy nào** được patch, **khi nào**, **bởi ai**, **dựa trên policy nào**.
- Nguồn Windows Update/WSUS hoặc repository Linux cung cấp bản cập nhật từ đâu.
- Vì sao assessment thành công, installation thành công và workload khỏe là **ba trạng thái khác nhau**.
- Cách tránh reboot quá nhiều backend cùng lúc, bao gồm trường hợp một VM đã unhealthy trước cửa sổ.
- Cách xử lý canary thất bại, pending reboot, patch thất bại hoặc máy không thể được đánh giá.
- Cách lưu bằng chứng hoàn tất và ngoại lệ mà không làm lộ credential hoặc dữ liệu nhạy cảm.

## 20. Ghi nhớ

**Azure Update Manager** là công cụ giúp **đánh giá, điều phối cài đặt theo nhu cầu hoặc theo lịch, và theo dõi bản vá guest OS** của các máy được hỗ trợ trên Azure và Azure Arc. Nó **không thay thế** nguồn cập nhật Windows Update/WSUS/Linux repository, CI/CD cho phần mềm ứng dụng, quản lý image/container hay kế hoạch khôi phục workload.

Một quy trình patch đáng tin cậy có năm lớp bảo vệ:

1. **Inventory và assessment chính xác:** biết máy nào chưa được vá, nguồn bản vá và thời điểm đánh giá.
2. **Policy và phạm vi phù hợp:** chọn update/KB/package, patch mode, scope, maintenance window và reboot setting theo OS/workload.
3. **Rollout có kiểm soát:** thử ở test/canary, giữ đủ backend, không cập nhật mọi VM cùng lúc.
4. **Xác minh sau reboot:** kiểm tra kernel/KB, ứng dụng, dữ liệu, mạng, log và trải nghiệm người dùng.
5. **Vận hành liên tục:** theo dõi máy bỏ sót, report stale, ngoại lệ quá hạn, lỗi update, chi phí và khả năng phục hồi.

Khi đánh giá một dự án Azure thực tế, đừng chỉ hỏi **“VM đã cài patch chưa?”** mà còn phải trả lời **“bản vá nào đã có hiệu lực, dịch vụ có còn hoạt động không, và tổ chức có bằng chứng để khắc phục phần còn thiếu hay không?”**
