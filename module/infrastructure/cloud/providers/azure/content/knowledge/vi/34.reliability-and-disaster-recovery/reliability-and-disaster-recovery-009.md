# Runbook failover, failback và điều phối phục hồi

## Mục tiêu bài học

Trong chương **Độ tin cậy và khôi phục thảm họa** của lộ trình **CLOUD_PROVIDERS_AZURE**, chúng ta chuyển từ chuẩn bị hạ tầng dự phòng sang **điều hành một lần khôi phục có kiểm soát**. Azure cung cấp subscription, resource group, Microsoft Entra ID, mạng ảo, máy ảo, lưu trữ và dữ liệu; tuy nhiên từng máy ảo khởi động thành công chưa có nghĩa là ứng dụng đã hoạt động trở lại. Cần runbook xác định quyền ra quyết định, thứ tự khôi phục, điều kiện chuyển lưu lượng và cách trở về môi trường chính.

Sau bài này, bạn có thể:

- Phân biệt failover, failback, test failover, planned/unplanned failover và re-protect.
- Thiết kế runbook có người chịu trách nhiệm, điều kiện kích hoạt, điểm chặn (gate), bằng chứng và phương án xử lý khi không đạt.
- Dùng **Azure Site Recovery (ASR)** và **Recovery Plan** để điều phối khôi phục máy ảo theo phụ thuộc ứng dụng.
- Kiểm chứng dữ liệu, bảo mật, kết nối, dịch vụ và trải nghiệm người dùng trước khi định tuyến lưu lượng.
- Lập kế hoạch failback, diễn tập và đánh giá RTO/RPO thực tế.

## 1. Runbook và các khái niệm nền tảng

**Runbook khôi phục thảm họa (Disaster Recovery Runbook)** là tài liệu thao tác có thể thực thi khi vùng chính hoặc chuỗi phụ thuộc quan trọng bị hỏng. Nó trả lời sáu câu hỏi: **khi nào kích hoạt, ai quyết định, làm gì theo thứ tự nào, kiểm chứng ra sao, dừng khi nào và chuyển về trạng thái thường như thế nào**.

| Khái niệm | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| **Failover** | Đưa workload sang vùng/hệ thống dự phòng | Chỉ hoàn tất khi nghiệp vụ đã phục vụ, không chỉ khi VM bật |
| **Planned failover** | Chủ động chuyển khi phía chính còn truy cập để phối hợp đồng bộ | Có cơ hội giảm mất dữ liệu nhưng cần kiểm chứng |
| **Unplanned failover** | Chuyển khi phía chính không khả dụng hoặc không thể chờ | Có thể mất ghi chưa đến recovery point |
| **Test failover** | Diễn tập khởi chạy môi trường DR, không chuyển lưu lượng sản xuất | Dùng mạng cô lập và dọn dẹp sau thử nghiệm |
| **Failback** | Chuyển từ DR về nơi chính sau khi phục hồi | Phải bảo toàn dữ liệu phát sinh tại DR |
| **Re-protect** | Thiết lập lại hướng bảo vệ/nhân bản sau chuyển vùng | Sau failover thường cần nhân bản ngược; sau failback cần bảo vệ DR trở lại |

**Azure Backup** lưu các điểm phục hồi và cho phép restore, trong khi **Azure Site Recovery** bảo vệ các workload được hỗ trợ bằng nhân bản và điều phối failover. Chúng bổ sung nhau. Nhân bản không thay thế backup: xóa nhầm, logic ghi sai hoặc dữ liệu hỏng cũng có thể được nhân bản.

Hai chỉ tiêu phải ghi trước khi thiết kế:

- **RPO (Recovery Point Objective)**: độ mất dữ liệu tối đa được chấp nhận, biểu thị bằng thời gian giữa dữ liệu khôi phục được và thời điểm sự cố.
- **RTO (Recovery Time Objective)**: thời gian tối đa để các chức năng nghiệp vụ thiết yếu hoạt động lại kể từ sự cố. Bao gồm phát hiện, quyết định, phục hồi, kiểm chứng và chuyển lưu lượng.

Đây là mục tiêu nghiệp vụ, **không phải cam kết tự động** khi bật ASR. Cần đo chúng trong diễn tập và sự cố thực tế.

## 2. Kiến trúc ví dụ trên hai region

Giả sử một ứng dụng đặt hàng hoạt động tại:

- **Region A (primary)**: VM API, VM frontend, VM cơ sở dữ liệu, mạng riêng, cân bằng tải và các dependency.
- **Region B (DR)**: VNet/subnet, NSG, route, hạn mức tính toán và cấu hình mạng đã chuẩn bị; các VM được ASR bảo vệ có khả năng khôi phục tại đây.
- **Recovery Services vault**: quản trị nhân bản và ASR Recovery Plan.
- **Azure Front Door** hoặc **Azure Traffic Manager**: chuyển hướng truy cập theo thiết kế định tuyến đã triển khai trước.
- **Azure Monitor, Application Insights, Log Analytics**: phát hiện lỗi, kiểm chứng và lưu dữ liệu quan sát.

~~~mermaid
flowchart LR
    U[Người dùng] --> R[Front Door / Traffic Manager]
    R --> A[Region A - Primary]
    R -. chuyển lưu lượng khi đạt điều kiện .-> B[Region B - DR]
    A --> VA[API / Web / DB VMs]
    B --> VB[VMs phục hồi]
    VA -. ASR replication .-> VB
    S[Recovery Services vault] --> P[Recovery Plan]
    P --> VB
    O[Monitor và incident log] --> P
~~~

Sơ đồ thể hiện trường hợp VM; **ASR không tự khôi phục mọi thành phần PaaS**. Nếu ứng dụng dùng Azure SQL Database, Azure Storage, Service Bus, Key Vault hay dịch vụ managed khác, chúng cần cơ chế dự phòng/replication và điều phối riêng. Cả Front Door lẫn Traffic Manager cũng cần cấu hình endpoint/origin DR và health probe trước khi sự cố.

**Nguy cơ split-brain:** khi Region A phục hồi một phần, hai phía có thể cùng tưởng mình là nơi nhận ghi hợp lệ. Runbook phải quy định **một nguồn dữ liệu được quyền ghi** hoặc sử dụng kiến trúc multi-writer đã được thiết kế và thử nghiệm riêng. Không chỉ dựa vào thay đổi DNS để ngăn ghi từ vùng cũ.

Giả định của ví dụ: **RTO mục tiêu 60 phút, RPO mục tiêu 15 phút**. Các giá trị là minh họa; hệ thống thực phải có kết quả kiểm thử và quyết định của chủ nghiệp vụ.

## 3. Chuẩn bị runbook trước sự cố

Một runbook vận hành phải ghi được:

| Mục | Nội dung cần điền |
| --- | --- |
| Định danh | Dịch vụ, subscription, Entra tenant, resource group, Region A/B, vault, tên Recovery Plan, phiên bản |
| Trách nhiệm | Incident Commander (IC), vận hành Azure, nhóm dữ liệu, mạng/DNS, chủ ứng dụng, người duyệt và phương thức liên lạc dự phòng |
| Kích hoạt | SLI/SLO, mức ảnh hưởng người dùng, thời điểm bắt đầu sự cố, thời hạn ra quyết định |
| Phụ thuộc | Database, API, web, DNS riêng, identity, secret, chứng chỉ, firewall, queue, scheduler, tích hợp ngoài |
| Mục tiêu | RTO, RPO, giới hạn mất dữ liệu, các điều kiện Go/No-Go |
| Thao tác | Recovery Plan, script kiểm tra, dashboard, nơi lưu nhật ký và cách khắc phục |
| Bằng chứng | Job ID, timestamps, recovery point, kết quả smoke test, kết quả đối soát dữ liệu |
| Kết thúc | Trạng thái DR active, failback, re-protect, chủ vận hành kế tiếp |

Không lưu mật khẩu, khóa truy cập hoặc token rõ trong tài liệu. Dùng quyền Azure RBAC theo phạm vi, Managed Identity và quy trình truy cập khẩn cấp được kiểm soát. Kênh xử lý sự cố cũng không nên phụ thuộc duy nhất vào Region A.

### Checklist sẵn sàng

1. **Replication:** các VM có protection/replication health tốt; recovery point và độ trễ phù hợp mục tiêu; lỗi đồng bộ đã xử lý.
2. **Sức chứa:** region DR còn quota/SKU, disk, IP, khả năng mạng và vùng sẵn sàng phù hợp; các thành phần nền như load balancer, firewall và egress được chuẩn bị.
3. **Mạng và danh tính:** VNet/subnet/NSG/route, private DNS, TLS, chứng chỉ, Key Vault, Entra ID, RBAC và Managed Identity không cản trở VM chạy ở B.
4. **Dữ liệu và tích hợp:** hiểu ứng dụng dừng ghi ở đâu, database khôi phục như thế nào, queue/scheduler nào có thể chạy trùng; dependency PaaS có kế hoạch riêng.
5. **Quan sát và diễn tập:** health check, synthetic monitoring, log và thông báo sẵn; đã thử test failover trong môi trường cô lập, có dọn dẹp và cải tiến.

Replication healthy **không** khẳng định ứng dụng ở DR chạy đúng hoặc đạt RTO.

## 4. Quyết định kích hoạt: planned hay unplanned?

IC cần xác định sự cố có thực sự yêu cầu chuyển vùng. Ví dụ: health check từ bên ngoài và trong hệ thống đều thất bại, thành phần cốt lõi không thể khôi phục trong thời hạn chấp nhận, việc tiếp tục xử lý tại A có nguy cơ vượt RTO. Các ngưỡng phát hiện và thời gian chờ là **tham số do từng tổ chức xác định theo SLO**, không phải giá trị mặc định của Azure.

~~~mermaid
flowchart TD
    I[Phát hiện sự cố] --> V{Ảnh hưởng nghiệp vụ nghiêm trọng?}
    V -- Không --> X[Khắc phục thông thường]
    V -- Có --> Q{Region A còn an toàn và đồng bộ được?}
    Q -- Có --> P[Đánh giá planned failover]
    Q -- Không --> U[Đánh giá unplanned failover]
    P --> G{Được duyệt và đạt điều kiện dữ liệu?}
    U --> G
    G -- Không --> H[Dừng và xử lý điều kiện thiếu]
    G -- Có --> F[Khởi chạy Recovery Plan]
    F --> B{Ứng dụng và dữ liệu đạt kiểm chứng?}
    B -- Không --> C[Chặn lưu lượng, khắc phục]
    B -- Có --> T[Chuyển lưu lượng sang DR]
~~~

Trước khi nhấn failover, người điều hành ghi: thời điểm sự cố, người phê duyệt, hướng bảo vệ, replication lag, recovery point định chọn, mức dữ liệu có nguy cơ mất, và lý do sử dụng planned/unplanned. Điểm khôi phục mới nhất có thể giảm mất dữ liệu; điểm **application-consistent** có thể hỗ trợ khôi phục trạng thái ứng dụng phù hợp. Nhưng application-consistent không tự bảo đảm giao dịch phân tán giữa DB, queue và hệ thống ngoài hoàn toàn nhất quán.

## 5. Orchestration bằng Azure Site Recovery Recovery Plan

**Recovery Plan** trong ASR tổ chức các VM được bảo vệ thành nhóm, điều phối thứ tự thực hiện và có thể lồng các bước thủ công hoặc Azure Automation runbook. Các nhóm nên bám vào **phụ thuộc ứng dụng**, không chỉ tên resource group.

| Nhóm / gate | Hành động | Chủ trách nhiệm | Tiêu chí đi tiếp |
| --- | --- | --- | --- |
| **G0 – Công bố DR** | IC quyết định; ngừng deployment, đánh giá recovery point, kích hoạt bảo vệ single-writer | IC + dữ liệu | Có quyết định, timestamp, chấp nhận rủi ro |
| **G1 – Nền tảng** | Xác minh VNet, DNS nội bộ, route, firewall, secret, quyền và các dịch vụ nền tại B | Mạng + platform | Kết nối phụ thuộc thiết yếu hoạt động |
| **G2 – Database** | Phục hồi VM dữ liệu, xác minh trạng thái DB, integrity và quyền ghi | Nhóm dữ liệu | Chỉ có một primary được ghi, DB đủ khỏe |
| **G3 – Backend/API** | Bật VM ứng dụng, nạp cấu hình DR và kết nối DB | Chủ ứng dụng | API readiness + log/trace bình thường |
| **G4 – Web/tích hợp** | Bật frontend, kiểm tra TLS, login, queue, callback, scheduler | Ứng dụng + vận hành | Smoke test nghiệp vụ thành công |
| **G5 – Cutover** | Chuyển routing qua Front Door/Traffic Manager, kiểm tra từ ngoài | IC + mạng | Người dùng thực đến B, SLI phục hồi |
| **G6 – Ổn định** | Theo dõi, xử lý backlog, ghi nhận trạng thái và commit theo quy trình | IC + mọi nhóm | Có bằng chứng vận hành DR ổn định |

Các tên **G0–G6 chỉ là cấu trúc runbook minh họa**, không phải tên nhóm cố định của ASR. Hạ tầng ở G1 thường được triển khai sẵn bằng IaC hoặc quy trình chuẩn; Recovery Plan không tự cung cấp mọi dependency ngoài máy ảo.

### Quy trình thao tác trong Azure Portal

Trong **Recovery Services vault**, tìm phần **Site Recovery → Recovery Plans** (đường dẫn menu có thể thay đổi theo giao diện), mở kế hoạch được phê duyệt:

1. Kiểm tra hướng replication, VM trong kế hoạch, vùng đích, mạng đích và các bước manual/automation.
2. Khi diễn tập, chọn **Test failover** và mạng kiểm thử cô lập. Khi xử lý sự cố, chọn hình thức **Planned failover / Failover** thích hợp.
3. Theo dõi ASR job theo từng nhóm; kiểm chứng trạng thái máy ảo và ứng dụng, ghi lại job ID. Không tự cho qua manual gate nếu kiểm tra chưa đạt.
4. Kiểm tra tầng dữ liệu, API và nghiệp vụ độc lập với thông báo “VM running”; chỉ sau khi pass mới chuyển routing.
5. Khi kết quả failover đã được chấp nhận, thực hiện **Commit** theo điều kiện của ASR. Commit chốt kết quả và có thể làm mất khả năng lựa chọn lại các recovery point cũ của phiên failover đó.
6. Bắt đầu **Re-protect** theo hướng cần thiết để bảo vệ môi trường đang active ở DR và chuẩn bị cho failback.

Trong sự cố, **tự động hóa giúp thi hành**, nhưng quyết định chấp nhận mất dữ liệu, khóa ghi tại A, mở lưu lượng và commit cần quyền và bằng chứng rõ ràng. Đừng giả định một script lỗi sẽ tự dừng những thay đổi routing do hệ thống khác thực hiện.

## 6. Ví dụ runbook tự động kiểm tra sau khi VM phục hồi

Ví dụ dùng **Azure Automation PowerShell runbook** để xác minh VM đang chạy và endpoint HTTP readiness của ứng dụng đã phản hồi. Đây là bước kiểm tra, **không phải lệnh kích hoạt failover hay đổi DNS**.

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $VmName,

    [Parameter(Mandatory = $true)]
    [string] $HealthUrl
)

$ErrorActionPreference = 'Stop'

# Azure Automation da bat system-assigned managed identity.
Disable-AzContextAutosave -Scope Process | Out-Null
Connect-AzAccount -Identity | Out-Null

$vm = Get-AzVM -ResourceGroupName $ResourceGroupName -Name $VmName -Status
$powerState = $vm.Statuses |
    Where-Object { $_.Code -like 'PowerState/*' } |
    Select-Object -First 1 -ExpandProperty Code

if ($powerState -ne 'PowerState/running') {
    throw "VM $VmName chua o trang thai running: $powerState"
}

$response = Invoke-WebRequest -Uri $HealthUrl -Method Get -TimeoutSec 15
if ($response.StatusCode -ne 200) {
    throw "Health endpoint tra ve HTTP $($response.StatusCode)"
}

Write-Output "PASS: VM running va health endpoint san sang."
~~~

Điều kiện chạy:

- Azure Automation Account đã bật Managed Identity, có quyền đọc VM ở resource group tương ứng và có module **Az.Accounts/Az.Compute** đúng runtime.
- Địa chỉ **HealthUrl** trỏ về dịch vụ đã phục hồi ở B; không được vô tình kiểm tra Region A. Nếu endpoint chỉ nằm trên mạng riêng, cần đường kết nối thích hợp, ví dụ **Hybrid Runbook Worker**, thay vì giả định cloud worker truy cập được VNet.
- Endpoint **/health/ready** phải kiểm tra ít nhất những phụ thuộc cốt lõi (chẳng hạn database), không chỉ trạng thái tiến trình web.
- Không log token/secret, không dùng kết quả HTTP 200 làm đủ bằng chứng cutover. Bổ sung test giao dịch, dữ liệu, TLS, queue và xem cả **Automation job** lẫn **ASR job**.
- Với VM mới lên, có thể dùng retry hữu hạn và timeout rõ ràng; mọi lỗi cuối cùng vẫn phải được báo cho người chịu trách nhiệm.

Một bộ smoke test nghiệp vụ có thể tạo **đơn thử với idempotency key duy nhất**, đọc lại đúng đơn ở B, xác nhận queue xử lý không trùng, theo dõi trace và kiểm tra không có worker tại A còn nhận ghi. Dữ liệu thử phải được đánh dấu và có thủ tục dọn.

## 7. Chạy failover theo các điểm kiểm soát

**Bước A – Mở incident, khóa thay đổi.** IC công bố cấp sự cố, tạo kênh phối hợp và nhật ký thời gian. Tạm dừng deployment, migration, scheduler hoặc batch có thể gây sai khác dữ liệu. Phân vai người thao tác ASR, người kiểm DB, người sửa routing và người chấp nhận nghiệp vụ.

**Bước B – Bảo vệ quyền ghi.** Nếu Region A còn truy cập, dừng ghi, xử lý giao dịch đang chạy, đồng bộ cuối theo kế hoạch. Nếu A không thể liên lạc, thực thi cơ chế **fencing** hoặc kiểm tra quyền primary nhằm tránh A hồi phục rồi ghi song song với B. Với DB có cơ chế leader election, nhóm dữ liệu cần xác minh chỉ một leader được phép ghi.

**Bước C – Khởi động Recovery Plan.** Chọn recovery point và failover mode có ghi nhận lý do. Theo dõi từng job, kiểm tra nhóm G1–G4 theo phụ thuộc. Lỗi DB, secret, DNS nội bộ hoặc thiếu quota là lý do **dừng trước G5**.

**Bước D – Kiểm chứng ba lớp.** Tầng hạ tầng: VM, NSG, route, DNS, cert. Tầng dịch vụ: readiness, login, API, error rate, trace. Tầng dữ liệu/nghiệp vụ: giao dịch thử có kiểm soát, tính toàn vẹn, queue lag, ghi đơn và đọc lại, xử lý request lặp. Chỉ cho phép DR nhận người dùng khi cả ba lớp qua kiểm tra.

**Bước E – Chuyển lưu lượng.** Cập nhật origin/routing trong **Front Door**, hoặc trạng thái/ưu tiên endpoint trong **Traffic Manager**, theo kiến trúc đã triển khai. Với giải pháp dựa trên DNS, tính đến TTL và cache tại resolver. Kiểm tra từ nhiều đường mạng, theo dõi lỗi và đảm bảo đường tới A không còn nhận ghi.

**Bước F – Ổn định và chấp nhận.** IC ghi thời điểm người dùng thực sự được phục vụ ở B, kiểm tra SLI quan trọng, tải hệ thống, DB, queue và chi phí; thông báo DR active. Chỉ commit thao tác ASR khi đã hiểu tác động tới recovery point và chấp nhận kết quả. Thiết lập re-protect hướng từ B về A theo trạng thái thực tế.

**No-Go:** nếu không kiểm soát được quyền ghi, có nguy cơ nhân đôi giao dịch, dữ liệu không toàn vẹn, DR thiếu sức chứa hoặc test giao dịch cốt lõi lỗi, **chưa mở lưu lượng**. Một Recovery Plan thành công về hạ tầng không thay thế quyết định nghiệp vụ.

## 8. Failback: trở lại Region A mà không mất dữ liệu tại DR

Sau failover, **Region B là môi trường phát sinh dữ liệu mới**. Nếu đơn giản bật lại VM cũ ở A và đổi DNS về, dữ liệu đặt hàng trong thời gian B phục vụ có thể mất. Failback là một lần chuyển vùng riêng với quy trình dữ liệu và phê duyệt riêng.

### Điều kiện bắt đầu failback

- Region A đã ổn định, nguyên nhân lỗi được giải quyết, hạ tầng, quyền, chứng chỉ và dịch vụ phụ thuộc đã kiểm tra.
- Dữ liệu, backlog, giao dịch và schema tại B được kiểm kê; có bản backup phù hợp với trạng thái mới.
- **Re-protect/replication ngược B → A** đã sẵn sàng theo cơ chế ASR của workload; dữ liệu PaaS/queue ngoài ASR có giải pháp đồng bộ riêng.
- Có lịch chuyển đổi, chủ sở hữu, bước chặn, phương án giữ B tiếp tục phục vụ nếu kiểm tra A không đạt.

### Trình tự thực hiện

1. **Khôi phục và kiểm chứng A:** sửa nguyên nhân sự cố, kiểm tra quota, mạng, identity, cấu hình và endpoint của môi trường đích.
2. **Nhân bản ngược:** sau commit phù hợp với quy trình ASR, dùng **Re-protect** để sao chép từ môi trường đang active ở B về A; chờ health/recovery point đạt yêu cầu. Đồng bộ dịch vụ ngoài ASR bằng cơ chế của chúng.
3. **Đối soát dữ liệu:** kiểm tra số lượng đơn, giao dịch trùng, message id, queue, thay đổi schema và số liệu tài chính liên quan. Replication của VM không thay thế đối soát nghiệp vụ.
4. **Chuẩn bị planned failover B → A:** thông báo cửa sổ, giảm hoặc đóng ghi tại B, chờ giao dịch đang chạy, xác nhận điểm đồng bộ cuối và thực hiện chuyển có kế hoạch.
5. **Kiểm chứng tại A:** khôi phục theo phụ thuộc DB → API → web, chạy health check và smoke test, xác minh tính toàn vẹn và chỉ một nguồn ghi.
6. **Chuyển routing về A:** thực hiện cutover bằng Front Door/Traffic Manager theo thiết kế; kiểm tra từ ngoài và giám sát các client còn giữ cache.
7. **Commit và tái bảo vệ:** chấp nhận kết quả, commit, rồi **Re-protect A → B**; theo dõi replication healthy và điều chỉnh giám sát theo vai trò mới.
8. **Đóng incident:** ghi RPO/RTO thực tế, lịch sử job, vấn đề chưa giải quyết, chi phí và các thay đổi runbook.

Nếu A thất bại **trước cutover**, giữ B tiếp tục phục vụ và sửa lỗi. Nếu đã chuyển sang A rồi lại lỗi, chuyển ngược về B là một lần failover mới: phải kiểm tra dữ liệu phát sinh ở A trước khi thay đổi routing, tránh làm mất giao dịch.

~~~mermaid
stateDiagram-v2
    [*] --> ActiveA
    ActiveA --> Decision: Sự cố hoặc lịch chuyển
    Decision --> ActiveB: Failover + kiểm chứng + cutover
    ActiveB --> ReverseReplication: Commit / re-protect B sang A
    ReverseReplication --> FailbackReady: A ổn định, dữ liệu đồng bộ
    FailbackReady --> ActiveA: Planned failover về A + cutover
    ActiveA --> ProtectedA: Commit / re-protect A sang B
    ProtectedA --> [*]
~~~

Đây là sơ đồ **trạng thái dịch vụ để điều hành**, không phải mã trạng thái job của ASR. Luôn kiểm tra hướng replication thực tế trong vault.

## 9. Mẫu runbook đội vận hành có thể tùy biến

Đoạn YAML dưới đây là **mẫu tài liệu thao tác**, không phải cấu hình có thể import trực tiếp vào Azure Recovery Plan.

~~~yaml
runbook:
  service: order-service
  primary_region: "<region-A>"
  dr_region: "<region-B>"
  rto_target_minutes: 60
  rpo_target_minutes: 15
  incident_commander: "<on-call-owner>"
  recovery_plan: "<vault/recovery-plan>"
  traffic_controller: "<front-door-or-traffic-manager>"
  gates:
    - id: declare
      pass_when: "IC approves; incident time and mode recorded"
      evidence: "incident ID, approver"
    - id: protect_data
      pass_when: "single write authority is verified"
      evidence: "primary/fencing checks"
    - id: recover
      pass_when: "ASR jobs finish; dependencies are healthy"
      evidence: "job IDs, recovery point, VM/DB status"
    - id: validate
      pass_when: "critical business transactions succeed"
      evidence: "test IDs and traces"
    - id: cutover
      pass_when: "external clients reach DR and SLIs recover"
      evidence: "routing change and external checks"
    - id: stabilize
      pass_when: "IC accepts DR-active status"
      evidence: "dashboard and handover notes"
  failback_requirements:
    - "region A stable and secured"
    - "reverse replication healthy"
    - "DR data reconciled"
    - "change window approved"
~~~

Trong runbook thực, thay placeholder bằng tên tài nguyên, vị trí dashboard, đường dẫn tới script đã kiểm thử, danh sách liên lạc, mẫu lưu chứng cứ và phương án xử lý từng lỗi. Không đưa password hoặc thông tin khách hàng vào file runbook.

### Ví dụ đo RTO/RPO

Giả sử Region A ngừng phục vụ lúc **09:00**. IC phê duyệt failover **09:12**; khôi phục VM xong **09:34**; kiểm chứng giao dịch và cutover xong **09:46**. Điểm dữ liệu cuối cùng khôi phục được tới **08:53**.

- **RTO thực tế:** 09:00 → 09:46 = **46 phút**; đạt mục tiêu 60 phút **nếu** các nghiệp vụ thiết yếu đã chạy đúng lúc 09:46.
- **Độ lệch điểm khôi phục:** 08:53 → 09:00 = **7 phút**; nằm trong RPO 15 phút nhưng không cho biết chính xác bao nhiêu giao dịch mất.
- **Đối soát:** kiểm tra các giao dịch 08:53–09:00 và sự kiện từ dịch vụ ngoài region, vì một số yêu cầu có thể được thực hiện một phần hoặc gửi lại.

Nếu VM và health endpoint xanh lúc 09:46 nhưng đến 10:05 mới tạo đơn được, RTO nghiệp vụ **phải tính đến 10:05**. Đừng dùng thời gian hoàn thành ASR job thay thế thời điểm dịch vụ thiết yếu phục hồi.

## 10. Diễn tập và xử lý lỗi thường gặp

Nên diễn tập theo lịch tổ chức phê duyệt, ví dụ mỗi quý hoặc sau thay đổi lớn. Sử dụng **ASR Test failover** với **VNet cô lập**; ngăn gửi email thật, thanh toán thật, callback, worker hoặc scheduler có thể tạo tác động lên sản xuất. Thu thập bằng chứng, sau đó **Cleanup test failover**. Thử nghiệm failback cần kịch bản riêng vì liên quan đảo chiều bảo vệ và dữ liệu mới tại DR.

| Chỉ số | Bằng chứng cần thu |
| --- | --- |
| Phát hiện và quyết định | Timestamp sự cố, phê duyệt, lý do planned/unplanned |
| Replication | Health, lag, recovery point, dữ liệu có nguy cơ mất |
| Hạ tầng | ASR job IDs, thời gian VM/DB ready, thiếu quota/quyền |
| Nghiệp vụ | Thời điểm giao dịch thiết yếu đầu tiên thành công, dữ liệu thiếu/trùng, backlog |
| Routing | Thời gian cutover, lỗi người dùng, cache DNS, latency |
| Failback | Reverse replication, đồng bộ cuối, cutover về A, re-protect A → B |
| Tài liệu | Lỗi script, gate chưa rõ, người liên lạc thiếu, thời gian xử lý thực tế |

**Lỗi 1 – VM bật nhưng API trả 500.** Kiểm tra DNS nội bộ, firewall, DB connection, Key Vault/secret, TLS và distributed trace. Dừng tại gate kiểm chứng, không mở lưu lượng.

**Lỗi 2 – DR thiếu quota hoặc SKU.** Kiểm tra job và giới hạn của region. Chỉ dùng phương án VM/SKU dự phòng đã đánh giá; chuẩn bị sức chứa trước sự cố vì bổ sung quota gấp có thể làm vượt RTO.

**Lỗi 3 – Một số client vẫn ghi vào A sau cutover.** Kiểm tra DNS cache, origin cũ, đường truy cập trực tiếp và cơ chế fencing/single-writer; đưa các giao dịch sai vùng vào đối soát, không dựa duy nhất vào DNS.

**Lỗi 4 – Failback về A nhưng thiếu dữ liệu tại B.** Dừng cho A nhận ghi, kiểm tra hướng re-protect, trạng thái nhân bản và cơ chế đồng bộ của từng nguồn dữ liệu; chỉ tiếp tục khi nhóm dữ liệu xác nhận toàn vẹn.

**Lỗi 5 – Bước tự động chạy thành công nhưng giao dịch thất bại.** Phân biệt trạng thái job, VM, endpoint HTTP và nghiệp vụ. Bổ sung synthetic transaction có idempotency và manual approval trước cutover.

Sau diễn tập/sự cố, cập nhật runbook theo lỗi thực tế và tổ chức postmortem tập trung vào nguyên nhân, thời gian, tác động, quyết định và cải tiến có người chịu trách nhiệm.

## 11. Bài tập áp dụng

Một dịch vụ gồm hai VM API, một VM xử lý hàng đợi và một cơ sở dữ liệu; RTO mục tiêu **45 phút**, RPO **10 phút**. Hệ thống đã có Azure Front Door và ASR Recovery Plan nhưng chưa có bước kiểm tra queue, giao dịch và failback.

1. **Thiết kế thứ tự nhóm khôi phục** từ dữ liệu tới API và worker. Điểm nào có thể chạy tự động? Điểm nào cần người phê duyệt? Làm sao ngăn worker chạy trùng ở hai vùng?
2. **Viết tối thiểu năm tiêu chí Go/No-Go** trước khi Front Door chuyển người dùng sang DR. Tách kiểm tra hạ tầng, API, dữ liệu và nghiệp vụ.
3. **Lập kế hoạch failback** gồm: điều kiện Region A, đồng bộ B → A, thời điểm ngừng ghi, xác nhận giao dịch, cutover và tái bảo vệ A → B.

Một phương án đầy đủ phải thể hiện được **một nơi nhận ghi hợp lệ, người ra quyết định, kiểm chứng nghiệp vụ trước cutover, đối soát dữ liệu và re-protect sau chuyển vùng**. Việc Recovery Plan báo hoàn tất chỉ chứng minh một phần hạ tầng đã được khôi phục.

## Kết luận

Runbook biến cấu hình dự phòng Azure thành quy trình phục hồi lặp lại, kiểm tra được và có người chịu trách nhiệm. **ASR Recovery Plan** điều phối các VM được hỗ trợ; còn mạng, danh tính, dữ liệu, dịch vụ PaaS, định tuyến và giao dịch phải được kiểm chứng với cơ chế riêng. **Failover kết thúc khi nghiệp vụ phục vụ từ DR; failback chỉ an toàn sau khi dữ liệu phát sinh tại DR đã được bảo toàn và hướng bảo vệ được thiết lập lại.**
