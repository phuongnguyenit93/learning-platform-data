# Phân bổ chi phí bằng mô hình showback và chargeback

Một doanh nghiệp có thể có nhiều nhóm sản phẩm cùng sử dụng một subscription, cụm Azure Kubernetes Service (AKS), hệ thống mạng, nền tảng giám sát và các dịch vụ dữ liệu. Khi hóa đơn Azure tăng, câu hỏi “nhóm nào phải chịu khoản tăng đó?” thường khó trả lời hơn câu hỏi “dịch vụ nào phát sinh phí?”. Một phần chi phí có thể truy thẳng đến ứng dụng qua resource ID hoặc tag, nhưng nhiều khoản là **chi phí dùng chung**, khoản mua cam kết hoặc khoản phí không có chủ sở hữu tài nguyên rõ ràng.

Trong chương **Quản lý chi phí** của lộ trình Microsoft Azure (**CLOUD_PROVIDERS_AZURE**), bài học này hướng dẫn thiết kế hai cơ chế phân bổ: **showback** (minh bạch chi phí cho nhóm tiêu thụ) và **chargeback** (ghi nhận khoản chi phí phải chịu vào ngân sách hoặc hệ thống hạch toán nội bộ). Nội dung liên kết quản lý subscription/resource group, Microsoft Entra ID, mạng, compute, storage, database, giám sát, bảo mật và vận hành một ứng dụng trên Azure.

Mục tiêu là xây dựng một cách phân bổ **công bằng, giải thích được, tái lập được và đối soát về tổng tiền**. Mô hình tốt giúp nhóm sản phẩm thấy tác động của quyết định kỹ thuật đến chi phí mà không làm sai lệch hóa đơn hoặc tạo khoản thu trùng.

> **Quy ước ví dụ:** Các khoản tiền, tỷ lệ, giao dịch và mã chi phí trong bài là dữ liệu giả định phục vụ thực hành, không phải hóa đơn hoặc đơn giá Azure hiện hành. Phương thức xuất dữ liệu, quyền truy cập và khả năng phân bổ tự động còn phụ thuộc agreement, billing scope và tính năng Azure được hỗ trợ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt showback, chargeback, direct cost, shared cost, unallocated cost và đơn vị chịu trách nhiệm chi phí.
2. Xây dựng mô hình liên kết **billing scope → subscription → resource → ứng dụng → cost center**.
3. Thiết lập chuẩn tag/metadata và xử lý chi phí không gắn tag, không có resource ID hoặc thuộc tài nguyên chia sẻ.
4. Chọn tiêu thức phân bổ chi phí mạng, node AKS, database dùng chung, observability và dịch vụ nền tảng.
5. Tính phân bổ theo tỷ lệ cố định, theo mức tiêu thụ và theo trọng số; kiểm tra tổng chi phí trước/sau.
6. Phân biệt actual cost, amortized cost, purchases, credit, taxes và dữ liệu invoice khi lập báo cáo nội bộ.
7. Tạo quy trình showback rồi tiến tới chargeback có kiểm soát, giải quyết khiếu nại và ghi nhận thay đổi.
8. Đề xuất cấu trúc dữ liệu, dashboard, ngưỡng chất lượng và lịch vận hành cho chương trình FinOps.

## 2. Showback và chargeback khác nhau ở đâu?

**Showback** là báo cáo chi phí mà một nhóm hoặc sản phẩm đang sử dụng. Nhóm được nhìn thấy các khoản trực tiếp, khoản dùng chung được phân bổ và xu hướng sử dụng, nhưng chưa nhất thiết có giao dịch chuyển ngân sách hoặc bút toán kế toán.

**Chargeback** dùng quy tắc phân bổ đã được chấp thuận để **ghi nhận chi phí vào cost center, ngân sách, đơn vị kinh doanh hoặc sổ cái nội bộ**. Đây là quyết định quản trị tài chính. Nó không đồng nghĩa Azure sẽ phát hành hóa đơn riêng cho từng nhóm ứng dụng.

| Tiêu chí | Showback | Chargeback |
| --- | --- | --- |
| Mục tiêu | Tạo minh bạch và trách nhiệm sử dụng | Gắn trách nhiệm tài chính thực tế |
| Đầu ra | Dashboard, bảng phân tích, báo cáo chi phí | Bảng phân bổ đã chốt, đề nghị chuyển ngân sách/bút toán nội bộ |
| Độ chặt của dữ liệu | Cần nhất quán, cho phép hiển thị ước lượng được gắn nhãn | Cần đối soát, chứng từ, phiên bản quy tắc và phê duyệt |
| Cách xử lý tranh chấp | Trao đổi để sửa mapping và tiêu thức | Có quy trình khiếu nại, điều chỉnh và audit |
| Lợi ích | Người dùng hiểu driver chi phí | Khuyến khích tối ưu gắn với ngân sách |
| Rủi ro | Báo cáo bị bỏ qua nếu không có hành động | Phân bổ thiếu công bằng có thể tạo động cơ sai |

**Ví dụ:** AKS node pool chung tốn 1.800 USD trong một tháng. Báo cáo showback nói nhóm Orders chịu 900 USD, Catalog 540 USD, Analytics 360 USD. Chargeback dùng cùng kết quả đã được đối soát và phê duyệt để ghi nhận phần chi phí vào ba cost center. **Hóa đơn Azure ban đầu vẫn là nguồn chi phí của tổ chức**.

Một lộ trình triển khai hợp lý thường bắt đầu bằng showback, kiểm chứng dữ liệu và phương pháp, rồi mới triển khai chargeback. Không bắt đầu bằng việc tính phí cho các nhóm khi còn quá nhiều khoản không xác định nguồn gốc.

## 3. Định nghĩa rõ đối tượng cần phân bổ

Muốn phân bổ đúng, trước tiên phải trả lời **“ai là người chịu trách nhiệm?”** và **“chi phí thuộc sản phẩm nào?”**. Hai câu trả lời không phải lúc nào cũng trùng nhau.

| Đối tượng | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Business unit** | Commerce | Quản lý ngân sách ở cấp kinh doanh |
| **Cost center** | CC-410 | Đơn vị nhận khoản chargeback |
| **Application / product** | orders-api | Sản phẩm được đo chi phí |
| **Workload** | online-checkout | Luồng nghiệp vụ tiêu thụ tài nguyên |
| **Team / owner** | orders-platform | Chịu trách nhiệm vận hành và tối ưu |
| **Environment** | dev, staging, prod | Phân biệt chi phí thử nghiệm với production |
| **Shared service** | AKS platform, API gateway, monitoring | Tạo nguồn phí cho nhiều sản phẩm |
| **Billing scope** | Billing account/profile/section, subscription | Nguồn dữ liệu và phạm vi thanh toán |

**Cost center** là đơn vị kế toán hoặc quản trị ngân sách. Một ứng dụng có thể có hai nhóm hỗ trợ, còn một cost center có thể chịu nhiều ứng dụng. Cần có bảng mapping được quản lý phiên bản thay vì suy luận từ tên resource.

### 3.1. Phạm vi quản trị không hoàn toàn trùng phạm vi thanh toán

Trên Azure, tài nguyên được tổ chức theo subscription và resource group; billing account/profile/section có thể có cấu trúc riêng theo agreement. Hóa đơn có thể bao gồm nhiều subscription và các khoản không gắn với resource group.

~~~mermaid
flowchart TD
    B["Billing scope / kỳ chi phí"] --> E["Cost Details và các khoản phí khác"]
    E --> D["Chi phí gắn owner/resource"]
    E --> S["Shared cost pools"]
    E --> U["Unallocated / pending review"]
    D --> A["Ứng dụng và cost center"]
    S --> R["Allocation rules + driver metrics"]
    R --> A
    A --> SH["Showback report"]
    SH --> CH["Approved chargeback ledger"]
    U --> GOV["FinOps / chủ ngân sách xử lý"]
~~~

Trong một số agreement, quyền xem dữ liệu tài chính khác Azure RBAC để quản lý tài nguyên. Người có quyền Contributor trên resource group chưa chắc được tải hóa đơn hoặc nhìn thấy chiết khấu hợp đồng. Vì vậy nguồn dữ liệu cần được cấp quyền đọc đúng billing scope và lưu trữ có kiểm soát.

## 4. Phân loại chi phí trước khi phân bổ

Không đưa mọi dòng dữ liệu cost vào một phép chia theo tỷ lệ. Hãy phân loại trước:

| Loại | Ý nghĩa | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| **Direct cost** | Có thể gắn hợp lý với một ứng dụng/cost center | App Service plan riêng, database riêng của Orders | Phân bổ trực tiếp 100% |
| **Shared cost** | Nhiều ứng dụng cùng tiêu thụ | AKS nodes chung, NAT Gateway, Log Analytics workspace | Phân bổ bằng driver đo được hoặc quy tắc được phê duyệt |
| **Platform overhead** | Phục vụ toàn bộ nền tảng/tổ chức | Security baseline, nền tảng CI/CD dùng chung | Tính theo policy tổ chức hoặc để ở cost center nền tảng |
| **Unallocated cost** | Chưa đủ bằng chứng xác định người chịu | Chi phí không tag, resource lạ, dữ liệu thiếu mapping | Giữ trong nhóm cần xử lý; không ép phân bổ tùy tiện |
| **Commitment/purchase** | Khoản mua reservation/savings plan hoặc quyền lợi | Phí reservation trả trước | Chọn actual/amortized theo mục tiêu và tránh đếm trùng |
| **Non-usage / financial** | Thuế, support, refund, credit, Marketplace... | Phí hỗ trợ và khoản điều chỉnh | Áp dụng chính sách tài chính riêng hoặc giữ ở cấp billing |

Một **khoản phí có Resource ID** vẫn có thể là shared cost. Ví dụ tất cả node AKS thuộc resource group quản lý cụm, nhưng node pool phục vụ nhiều namespace; không thể gán toàn bộ node cost cho nhóm sở hữu cụm chỉ dựa trên resource group.

Một **resource không có tag** cũng chưa chắc là “không có owner”. Có thể suy ra từ inventory, IaC state, CMDB, naming convention hoặc mapping subscription được xác minh. Tuy nhiên phải ghi **nguồn suy luận và mức độ tin cậy**, không điền owner bằng suy đoán không kiểm chứng.

## 5. Chọn cơ sở chi phí trước khi tính

**Actual cost** và **amortized cost** phục vụ hai góc nhìn khác nhau. Với reservations/savings plan, một khoản mua có thể được ghi nhận ở thời điểm mua trong actual cost, trong khi amortized cost phân bổ chi phí cam kết theo thời gian và/hoặc mức hưởng lợi.

| Mục đích | Cơ sở nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Đối chiếu tiền với hóa đơn | Dữ liệu invoice/actual phù hợp agreement | Cần xét tax, credit, refund, support, Marketplace, kỳ chốt |
| Phân tích chi phí vận hành theo ứng dụng | Amortized cost khi có cam kết đủ điều kiện | Xem cả phần cam kết chưa sử dụng |
| Showback ngắn hạn | Một cơ sở được chọn và ghi rõ trên dashboard | Không trộn actual và amortized trong cùng tổng |
| Chargeback tháng | Cơ sở chính sách được Finance phê duyệt | Gắn phiên bản báo cáo, nguồn, rounding và adjustment |

**Không cộng actual cost với amortized cost** để ra tổng. Chúng có thể mô tả cùng một khoản chi theo thời điểm khác nhau. Với dữ liệu chuẩn hóa theo FOCUS hoặc Cost Management exports, cần đọc đúng các trường cost, pricing/charge category và nguồn dữ liệu hiện có; không giả định mọi export của Azure dùng cùng tên cột.

### 5.1. Kỳ phân bổ và đồng tiền

Mỗi lần phân bổ cần cố định:

- Billing account/section/subscription scope được phép xem.
- Tháng hoặc kỳ theo **hóa đơn** và khoảng thời gian sử dụng được chọn.
- Timezone, ngày dữ liệu được xuất và trạng thái đã chốt/chưa chốt.
- Currency của nguồn dữ liệu; tỷ giá/nguồn quy đổi nếu có.
- Loại cost (actual/amortized), treatment của credit/tax/support.
- Các dòng đã loại trừ và lý do.

Không phân bổ một phần bằng USD và phần khác bằng VND rồi cộng trực tiếp; không dùng tỷ giá thời điểm hiện tại để thay đổi số tiền hóa đơn đã phát hành.

## 6. Mô hình ownership: từ tag đến bảng mapping

### 6.1. Chuẩn metadata tối thiểu

Một chính sách tag tham khảo:

~~~yaml
application: orders-api
businessUnit: commerce
costCenter: CC-410
owner: orders-platform
environment: prod
managedBy: iac
dataClassification: internal
~~~

Đây là **mẫu metadata**, không phải file để tự động áp tag cho Azure. Các tag cần được tích hợp vào IaC/pipeline và kiểm soát bằng policy nếu phù hợp. Không đặt thông tin cá nhân nhạy cảm, token hay mật khẩu trong tag.

Tag giúp phân tích khi được dịch vụ hỗ trợ và khi xuất hiện trong dữ liệu cost. Nhưng **không phải mọi charge có tag, không phải mọi tài nguyên hỗ trợ tag theo cùng cách, và gắn tag hôm nay không mặc nhiên sửa được lịch sử**.

### 6.2. Thứ tự xác định owner

Một chính sách nhất quán có thể đi theo thứ tự:

1. **Mapping trực tiếp đã phê duyệt** theo resource ID/ứng dụng và khoảng hiệu lực.
2. **Tag costCenter/application** hợp lệ, có đối chiếu với danh mục chủ sở hữu.
3. **Subscription/resource group ownership** nếu ranh giới thực sự chỉ phục vụ một sản phẩm.
4. **Bảng mapping từ nền tảng/IaC/CMDB** được nhóm vận hành xác minh.
5. **Shared pool** nếu nhiều ứng dụng cùng tiêu thụ.
6. **Unallocated** nếu còn thiếu bằng chứng.

Không cho rule đơn giản “mọi tài nguyên trong subscription này thuộc Orders” ghi đè một mapping chi tiết đã được duyệt cho nền tảng dùng chung. Quy tắc ưu tiên cần công bố rõ.

### 6.3. Mapping phải có hiệu lực theo thời gian

Ví dụ:

| Resource / nhóm resource | Owner | Có hiệu lực từ | Có hiệu lực đến | Nguồn |
| --- | --- | --- | --- | --- |
| /subscriptions/.../orders-db | CC-410 | 2026-01-01 | Chưa xác định | CMDB đã duyệt |
| rg-commerce-shared | Shared-commerce | 2026-01-01 | Chưa xác định | Platform inventory |
| orders-api (app ID) | CC-410 | 2026-01-01 | 2026-09-30 | Product catalog |
| orders-api (app ID) | CC-510 | 2026-10-01 | Chưa xác định | Thay đổi tổ chức |

Khi owner đổi trong tháng, phải định nghĩa cách phân bổ theo **ngày sử dụng** hoặc theo một chính sách cutover được phê duyệt. Nếu chỉ sửa bảng owner hiện tại rồi tính lại dữ liệu quá khứ, báo cáo tháng trước có thể thay đổi không kiểm soát.

## 7. Các phương pháp phân bổ shared cost

Không có một công thức công bằng cho mọi loại tài nguyên. Hãy chọn **driver gần với nguyên nhân phát sinh phí**, có số liệu đáng tin và có thể kiểm toán.

### 7.1. Phân bổ tỷ lệ cố định

Khi chưa có telemetry tốt, tổ chức có thể duyệt chia pool theo phần trăm:

\[
A_{i,p}=C_p \times w_{i,p}
\]

Với \(C_p\) là chi phí pool \(p\), \(w_{i,p}\) là tỷ lệ gán cho nhóm \(i\). Điều kiện:

\[
\sum_i w_{i,p}=1,\qquad 0\leq w_{i,p}\leq 1
\]

Ví dụ network gateway 600 USD: Orders 50%, Catalog 35%, Analytics 15% → lần lượt 300, 210, 90 USD.

Ưu điểm: dễ giải thích, dễ triển khai. Hạn chế: không phản ánh thay đổi mức tiêu thụ hằng ngày; nếu giữ lâu có thể làm nhóm dùng ít phải chịu quá nhiều. Phù hợp như giải pháp chuyển tiếp có thời hạn.

### 7.2. Phân bổ theo số lượng tiêu thụ

Với số liệu driver \(u_{i,p}\) của từng nhóm:

\[
w_{i,p}=\frac{u_{i,p}}{\sum_j u_{j,p}},\qquad
A_{i,p}=C_p \times w_{i,p}
\]

Ví dụ gateway có 20 TiB egress đã xác minh: Orders 10 TiB, Catalog 7 TiB, Analytics 3 TiB. Tỷ lệ lần lượt 50%, 35%, 15%. Chia pool gateway 600 USD thành 300, 210, 90 USD.

**Chỉ dùng cùng một driver cho cùng một ranh giới:** số byte đo ở ingress không luôn tương ứng byte outbound tính phí; tổng request của API không nhất thiết là driver tốt cho phí truyền dữ liệu. Cần kiểm tra tên meter và loại lưu lượng được đo.

### 7.3. Phân bổ bằng trọng số

Khi workload có profile khác nhau, dùng một tiêu thức trọng số được công bố. Ví dụ pool compute chung có thể dùng tỷ trọng **CPU request-hours** và **memory request-GiB-hours** theo một cách kết hợp đã duyệt; hoặc xây mô hình chi phí từng node dựa trên resource usage/request và node price.

Giả sử chính sách nội bộ chọn driver:

\[
s_i = 0{,}7 \times \frac{cpu_i}{\sum_j cpu_j}
      + 0{,}3 \times \frac{memory_i}{\sum_j memory_j}
\]

Vì mỗi thành phần tỷ lệ đều có tổng bằng 1 nên tổng \(s_i\) bằng 1. Tỷ trọng **70% CPU / 30% memory** là giả định quản trị, không phải quy tắc Azure; có thể không phù hợp nếu node bị hạn chế chủ yếu bởi memory hoặc GPU. Trước khi áp dụng, đo kết quả và thống nhất với các nhóm chịu phí.

### 7.4. Phân bổ theo đơn vị nghiệp vụ

Với nền tảng phục vụ giao dịch đồng nhất, một số khoản có thể phân bổ theo **số giao dịch thành công, số đơn hàng, số tài khoản hoạt động hoặc số job hoàn tất**. Không áp cùng một đơn vị cho những sản phẩm có cấu trúc chi phí khác hẳn nhau.

Nếu một nền tảng thanh toán có 100.000 giao dịch hợp lệ từ Orders và 50.000 từ Marketplace, phân bổ một khoản phí nền tảng theo giao dịch có thể hợp lý. Tuy nhiên nếu phí chủ yếu theo dung lượng payload, request count đơn thuần sẽ gây sai lệch.

### 7.5. Khi nào không nên phân bổ?

Một khoản chi phí chưa có owner hoặc driver đáng tin nên để **unallocated** và gắn người xử lý. Đừng chia đều chỉ để báo cáo nhìn có vẻ “đủ 100%”. Phí bảo mật nền tảng hoặc support doanh nghiệp cũng có thể thuộc **central IT** theo quyết định tổ chức; không có yêu cầu mọi khoản phải chuyển về sản phẩm.

## 8. Thiết kế cost pool rõ ràng

**Cost pool** là tập hợp charge có cùng bản chất và cùng quy tắc phân bổ.

| Cost pool | Dữ liệu nguồn | Driver gợi ý | Điều kiện kiểm tra |
| --- | --- | --- | --- |
| **AKS shared nodes** | Node VM/disk liên quan đã xác định | CPU/memory consumption hoặc requests theo Pod/namespace | Tổng usage, idle node, DaemonSet, namespace hệ thống |
| **API gateway** | Gateway compute/requests | Request hoặc traffic byte theo route/app | Phân biệt route, retry và health probe |
| **Shared NAT/egress** | NAT/network meter được nhóm đúng | Egress bytes hoặc connection usage liên quan | Khác biệt tuyến mạng và loại traffic |
| **Log Analytics workspace** | Ingestion/retention charges | GiB ingest theo app/team và retention | Quy tắc sampling, log chung, bản ghi thiếu application |
| **CI/CD runners** | Node/agent/compute hoặc license | Build minutes, agent-hours, pipeline execution | Idle agent capacity và thời gian chờ |
| **Shared database** | SQL compute/storage/backup | Query/DTU/vCore metrics, storage, transaction hoặc agreed key | Tránh coi mọi query có chi phí bằng nhau |
| **Security baseline** | Công cụ quản trị/bảo mật | Số tài nguyên, bảo vệ theo workload hoặc central policy | Tránh double count với direct security fees |

**Pool phải không trùng nhau.** Nếu VM node của AKS đã nằm trong pool AKS shared nodes, không cộng lại cùng dòng vào direct compute của ứng dụng. Nên có ID dòng chi phí gốc và điều kiện “mỗi charge thuộc tối đa một phân loại đầu vào”.

Một pool có thể được chia nhỏ: ví dụ log ingestion của ba ứng dụng phân bổ theo ingestion bytes, còn phí vận hành chung của workspace giữ ở central IT. Tách theo bản chất chi phí giúp cách chia dễ chấp nhận hơn.

## 9. Đặc thù phân bổ chi phí AKS

AKS minh họa rõ sự khác biệt giữa **cách Azure tính phí** và **cách doanh nghiệp muốn hạch toán**. Hóa đơn thường thể hiện các tài nguyên hạ tầng liên quan như node VM, disks, load balancer, network và dịch vụ/tier tương ứng; Kubernetes namespace hoặc Pod không nhất thiết là đối tượng có hóa đơn riêng.

### 9.1. Phân biệt ba lớp chi phí

1. **Node capacity cost:** VM/node đang được provision để chạy workload.
2. **Pod consumption/request cost:** mức CPU/memory mà từng workload yêu cầu hoặc sử dụng.
3. **Unallocated/idle/system overhead:** năng lực còn trống, DaemonSet, system pods, chi phí nền tảng và phần không truy vết được.

Nếu tổng node cost là 1.800 USD và chỉ 70% capacity thực sự được ứng dụng sử dụng, phải quyết định **30% idle cost** được xử lý thế nào. Có thể phân bổ idle theo tỷ trọng active usage, hoặc giữ riêng trong cost center platform để thúc đẩy rightsizing. Hai cách đều hợp lệ nếu đã được thống nhất và công bố.

**Không đồng nhất CPU usage với CPU request.** Trong Kubernetes, requests ảnh hưởng scheduling và khả năng giữ chỗ; usage phản ánh mức thực dùng. Đội dùng request quá cao có thể chiếm chỗ khiến cần thêm node dù usage thấp. Một mô hình công bằng có thể báo cáo **cả allocated by request và allocated by usage** để phân tích, rồi lựa chọn cơ sở tính chargeback phù hợp.

### 9.2. Dữ liệu cần cho AKS allocation

- Pod/workload/namespace, labels **application**, **team**, **environment**.
- Node pool, node SKU, zone và chi phí VM/node liên quan.
- CPU/memory requests, usage theo cửa sổ thời gian.
- Thời điểm Pod chạy, thời điểm node được provision và phần idle/system.
- Persistent volumes/disks thuộc workload nào.
- Dịch vụ ingress, load balancer và outbound network dùng chung.

Có thể triển khai công cụ phân tích cost của container/Kubernetes, đo từ Prometheus/Azure Monitor hoặc một hệ thống phù hợp. Hãy kiểm tra schema, phiên bản và chức năng thực tế; một công cụ hiển thị estimated workload cost **không tự thay đổi hóa đơn Azure**.

## 10. Azure Cost Management và nguồn dữ liệu phân bổ

### 10.1. Dữ liệu chi phí gốc

Trên Azure Portal, **Cost Management → Cost Analysis** giúp khám phá cost theo scope, dịch vụ, resource, resource group, tag hoặc nhóm thuộc tính khả dụng. **Cost Details** và **Cost Management Exports** phù hợp để trích xuất chi tiết cho mô hình phân bổ nội bộ.

Các trường khái niệm cần ánh xạ:

~~~text
BillingScope
BillingPeriod / UsageDate
SubscriptionId
ResourceId / ResourceGroup
Product / Service / MeterId / MeterName
ChargeType / PricingModel
Quantity / UnitOfMeasure
CostAmount / BillingCurrency
Tags
~~~

Đây là **khung chuẩn hóa khái niệm**, không khẳng định mọi file Azure Cost Details có chính xác tên cột đó. Các schema xuất thay đổi theo agreement, phiên bản và chuẩn dữ liệu (ví dụ FOCUS). Khi triển khai ETL, phải đọc schema thực và lập bảng mapping field.

### 10.2. Azure Cost Management cost allocation rules

Azure Cost Management có khả năng **cost allocation** tại các phạm vi/tình huống được hỗ trợ. Những rule này phục vụ tái phân bổ chi phí trong phân tích và có giới hạn về nguồn, đích, kiểu phân bổ và phạm vi áp dụng. Cần xác nhận khả năng, quyền và coverage thực tế của billing account trước khi dùng.

**Không mặc định một allocation rule của Cost Management sẽ:**

- Viết lại lịch sử hóa đơn đã phát hành.
- Tự tạo bút toán kế toán chargeback cho cost center.
- Phân bổ được mọi loại phí Marketplace, tax, purchases hoặc tài nguyên không có metadata.
- Thay thế cho dữ liệu tiêu thụ chi tiết của Pod, query hoặc transaction trong các pool phức tạp.

Với nhu cầu đặc thù, xây một pipeline phân bổ nội bộ dựa trên export đã chốt và telemetry đã được kiểm tra, rồi xuất báo cáo showback và ledger đề nghị chargeback. Dù dùng chức năng tích hợp hay tự xây, phải luôn có **kiểm tra bảo toàn tổng chi phí và lịch sử quy tắc**.

### 10.3. Nguồn bổ trợ ngoài hóa đơn

| Nguồn | Dữ liệu cung cấp | Vai trò |
| --- | --- | --- |
| Azure Cost Details/Exports | Số tiền, service, meter, scope, ngày | Nguồn cost |
| Azure Resource Graph / inventory | Resource ID, subscription, tags, loại tài nguyên | Làm giàu ownership |
| IaC / CMDB / product catalog | App-to-team, cost center, hiệu lực mapping | Xác định chủ sở hữu |
| Azure Monitor / Application Insights | Requests, dependencies, bytes, log ingestion theo app | Driver phân bổ |
| Kubernetes metrics / cost tooling | CPU/memory request/usage và namespace | Driver AKS |
| Finance billing records | Invoice, credits, tax, adjustments, commitment purchase | Đối soát và hạch toán |

Giữ ranh giới giữa **meter cost chính thức** và **driver suy ra từ telemetry**. Nếu metric bị sampling hoặc thiếu dữ liệu, tỷ lệ phân bổ là ước lượng; báo cáo phải gắn nhãn chất lượng dữ liệu.

## 11. Pipeline xử lý phân bổ end-to-end

~~~mermaid
flowchart TD
    E["Azure Cost Export - dữ liệu gốc"] --> N["Chuẩn hóa schema, currency, scope, charge type"]
    N --> R["Loại trừ/tránh dòng trùng"]
    R --> D["Direct ownership mapping"]
    R --> P["Shared cost pool assignment"]
    R --> U["Unallocated"]
    M["Metrics/driver theo ứng dụng"] --> V["Tính tỷ lệ từng pool"]
    P --> V
    V --> A["Allocated ledger theo cost center"]
    D --> A
    A --> C["Reconciliation: direct + allocated + unallocated"]
    U --> C
    C --> S["Showback dashboard"]
    S --> Q["Review, dispute, freeze"]
    Q --> F["Approved chargeback"]
~~~

### 11.1. Các bước thực hiện

1. **Thu nguồn:** lấy export đúng billing scope/kỳ/loại cost, giữ file gốc bất biến và dấu thời gian xuất.
2. **Chuẩn hóa:** mapping cột, currency, account, service/meter, charge type, resource ID, tags.
3. **Lọc phạm vi:** loại trừ/tách các khoản không thuộc cost basis theo chính sách, ví dụ tax hay support.
4. **Gán trực tiếp:** nối với bảng ownership mapping có ngày hiệu lực.
5. **Tạo pool:** phân nhóm các dòng dùng chung, tránh cùng dòng xuất hiện ở hai pool.
6. **Gắn driver:** lấy metrics phù hợp cùng kỳ, cùng phạm vi và đơn vị đo.
7. **Tính tỷ lệ:** kiểm tra driver hợp lệ, tổng tỷ lệ, fallback khi thiếu dữ liệu.
8. **Phân bổ:** tạo các dòng ledger có tham chiếu charge/pool, rule version và owner.
9. **Đối soát:** cộng direct + allocated + unallocated; kiểm tra chênh lệch, rounding và ngoại lệ.
10. **Công bố showback:** hiển thị số tiền và driver, thu thập phản hồi của các nhóm.
11. **Phê duyệt chargeback:** Finance chốt kỳ, phát hành bảng phân bổ/bút toán theo quy trình nội bộ.
12. **Theo dõi:** kiểm tra thay đổi bất thường, giải quyết dispute và cập nhật quy tắc cho kỳ sau.

**Một kỳ phân bổ cần tái lập được.** Cùng data snapshot, mapping version, driver version và rule version phải cho ra cùng kết quả. Khi sửa rule, không ghi đè mất báo cáo đã chốt; tạo version và adjustment có dấu vết.

## 12. Ví dụ hoàn chỉnh: ba nhóm sử dụng Azure

Giả sử trong một kỳ phân bổ giả định, doanh nghiệp có ba sản phẩm:

- **Orders** – cost center **CC-410**.
- **Catalog** – cost center **CC-420**.
- **Analytics** – cost center **CC-430**.

Dữ liệu nền tảng đã được chuẩn hóa trên một cơ sở chi phí nhất quán cho mục đích phân tích. Để tránh tính trùng, nhóm **direct compute** ở đây là các resource được sử dụng riêng cho từng ứng dụng, còn **shared AKS nodes** chỉ chứa những node có chi phí chưa xuất hiện ở bảng direct.

### 12.1. Direct costs

| Direct cost | Orders | Catalog | Analytics | Tổng |
| --- | ---: | ---: | ---: | ---: |
| Compute/dịch vụ ứng dụng riêng | 1.240 USD | 820 USD | 590 USD | 2.650 USD |
| Database riêng | 360 USD | 280 USD | 210 USD | 850 USD |
| Storage riêng | 150 USD | 100 USD | 50 USD | 300 USD |
| **Tổng trực tiếp** | **1.750 USD** | **1.200 USD** | **850 USD** | **3.800 USD** |

Các khoản này được gắn owner 100% theo resource ID/IaC và cost center còn hiệu lực tại ngày sử dụng.

### 12.2. Shared cost pools và driver

| Pool | Tổng tiền | Driver được chọn | Orders | Catalog | Analytics |
| --- | ---: | --- | ---: | ---: | ---: |
| AKS shared nodes | 1.800 USD | CPU/memory share đã xác minh | 50% | 30% | 20% |
| Gateway/network | 600 USD | Egress bytes theo ứng dụng | 50% | 35% | 15% |
| Observability | 400 USD | Ingest GiB theo ứng dụng | 45% | 25% | 30% |
| Shared security | 200 USD | Số tài nguyên được bảo vệ có trọng số | 50% | 30% | 20% |
| **Tổng shared pools** | **3.000 USD** | | | | |

Tổng phần trăm của **từng hàng** là 100%. Chưa được phép lấy tỷ lệ Orders 50% áp lên tất cả pool nếu mỗi pool có driver khác nhau.

### 12.3. Kết quả phân bổ shared pools

| Pool | Orders | Catalog | Analytics | Check |
| --- | ---: | ---: | ---: | ---: |
| AKS shared nodes | 900 USD | 540 USD | 360 USD | 1.800 USD |
| Gateway/network | 300 USD | 210 USD | 90 USD | 600 USD |
| Observability | 180 USD | 100 USD | 120 USD | 400 USD |
| Shared security | 100 USD | 60 USD | 40 USD | 200 USD |
| **Shared allocated** | **1.480 USD** | **910 USD** | **610 USD** | **3.000 USD** |

Phép tính một dòng:

\[
A_{\text{Catalog, Gateway}}=600\times 35\%=210\ \text{USD}
\]

### 12.4. Showback sau phân bổ

Giả sử còn **200 USD** phát sinh từ meter chưa xác minh được owner. Quyết định tạm thời là giữ ở **Unallocated** và không ép chia cho ba nhóm.

| Thành phần | Orders | Catalog | Analytics | Unallocated | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 1.750 | 1.200 | 850 | 0 | 3.800 |
| Shared allocated | 1.480 | 910 | 610 | 0 | 3.000 |
| Chưa xác định owner | 0 | 0 | 0 | 200 | 200 |
| **Tổng (USD)** | **3.230** | **2.110** | **1.460** | **200** | **7.000** |

**Kiểm tra bảo toàn:**

\[
3.800+3.000+200=7.000
\]

\[
3.230+2.110+1.460+200=7.000
\]

Tổng phân bổ vào ba nhóm là **6.800 USD**, tức khoảng **97,14%** cơ sở chi phí 7.000 USD. **200 USD (2,86%)** chưa có owner và vẫn được nhìn thấy. Phần chưa phân bổ cần có người chịu trách nhiệm giải quyết, thời hạn và mã lý do.

**Phạm vi quan trọng:** 7.000 USD ở đây là **cost basis nội bộ đã chọn** và đã được chuẩn hóa cho tình huống học tập, chưa bao gồm các khoản được loại trừ như thuế hoặc các dòng tài chính khác. Nó không tự động bằng số tiền hóa đơn Azure phải thanh toán.

### 12.5. Chuyển từ showback sang chargeback

Trong vòng showback, ba nhóm nhận báo cáo cùng driver và được phép phản hồi. Khi Finance và chủ ngân sách thống nhất:

| Cost center | Số tiền chargeback đề nghị | Ghi chú |
| --- | ---: | --- |
| CC-410 / Orders | 3.230 USD | Chi phí trực tiếp + shared cost |
| CC-420 / Catalog | 2.110 USD | Chi phí trực tiếp + shared cost |
| CC-430 / Analytics | 1.460 USD | Chi phí trực tiếp + shared cost |
| Central / Unallocated | 200 USD | Chờ xác minh owner |

Chargeback có thể là **bút toán phân bổ ngân sách hoặc bù trừ nội bộ**, tùy hệ thống kế toán. Khi ghi nhận, phải bảo đảm một khoản gốc chỉ bị chargeback một lần. Không được vừa ghi toàn bộ 7.000 USD vào central IT như chi phí cuối cùng, vừa ghi thêm 6.800 USD vào ba nhóm mà không có bút toán đối ứng phù hợp.

## 13. Làm tròn mà vẫn giữ nguyên tổng

Trong thực tế, tỷ lệ không luôn tạo số tiền tròn đến cent. Một pool 100 USD chia đều cho ba nhóm:

\[
100/3=33{,}3333\ldots
\]

Nếu làm tròn từng nhóm thành 33,33 USD, tổng chỉ còn 99,99 USD. Nếu làm tròn cả ba thành 33,34 USD, tổng thành 100,02 USD.

Một phương án đơn giản là **largest remainder** ở đơn vị nhỏ nhất:

1. Tính giá trị chính xác trước làm tròn.
2. Chuyển sang đơn vị cent hoặc đơn vị nhỏ nhất theo currency.
3. Lấy phần nguyên xuống cho từng nhóm.
4. Phân phối số cent còn lại cho các phần lẻ lớn nhất, có thứ tự tie-break ổn định.
5. Kiểm tra tổng các khoản phân bổ bằng đúng tổng pool.

Với 100 USD chia ba, kết quả có thể là **33,34 + 33,33 + 33,33 = 100 USD**, theo quy tắc chọn nhóm nhận 1 cent còn lại đã được công bố.

Đừng tính bằng số thực dấu phẩy động để quyết toán nếu có thể tránh. Ưu tiên số thập phân chính xác hoặc đơn vị nhỏ nhất của currency, và quy định nhất quán **làm tròn ở mức pool/dòng hay ở tổng cost center**.

## 14. Thiết kế schema dữ liệu phân bổ

Một mô hình nội bộ tối thiểu nên tách **charge gốc**, **owner mapping**, **driver measurement**, **rule** và **ledger đầu ra**.

### 14.1. Bảng dữ liệu gợi ý

| Bảng | Trường chính | Ý nghĩa |
| --- | --- | --- |
| **cost_source** | source_row_id, period, subscription, resource_id, meter_id, charge_type, amount, currency | Charge gốc đã chuẩn hóa |
| **ownership_map** | resource_pattern, application, cost_center, effective_from, effective_to, approved_by | Mapping theo thời gian |
| **pool_membership** | source_row_id, pool_id, classification_reason | Xác định một charge thuộc pool nào |
| **allocation_rule** | rule_id, version, pool_id, driver, fallback, valid_from, valid_to | Quy tắc phân bổ |
| **driver_values** | period, pool_id, application, measured_value, unit, data_quality | Số liệu driver |
| **allocation_ledger** | allocation_id, period, source_or_pool_id, rule_version, target, allocated_amount, currency | Kết quả có thể truy vết |
| **reconciliation** | period, basis_total, direct_total, allocated_total, unallocated_total, diff, status | Kiểm tra tổng |

**source_row_id** phải đủ ổn định để chống duplicate khi import lại cùng export. Nếu nguồn không có ID duy nhất, tạo khóa có điều kiện từ các trường phù hợp và snapshot ID; kiểm tra trường hợp hai dòng giống nhau nhưng là hai charges hợp lệ.

### 14.2. Ví dụ các rule dạng dữ liệu

~~~yaml
period: "2026-11"
costBasis: amortized-operating-cost
currency: USD
rules:
  - pool: shared-aks-nodes
    method: measured-proportional
    driver: weighted-cpu-memory-consumption
    ruleVersion: 3
    missingDriverBehavior: keep-unallocated
  - pool: gateway-egress
    method: measured-proportional
    driver: attributable-egress-gib
    ruleVersion: 2
    missingDriverBehavior: keep-unallocated
  - pool: security-platform
    method: approved-fixed-percent
    weights:
      orders: 0.50
      catalog: 0.30
      analytics: 0.20
    ruleVersion: 1
    missingDriverBehavior: reject-rule
~~~

Đây là **schema minh họa do bài học định nghĩa**, không phải cấu hình Azure Cost Management allocation rule hay API có thể gửi nguyên văn vào Azure.

### 14.3. Pseudocode cho một lần phân bổ

~~~text
source = load_frozen_cost_snapshot(period, scope, basis, currency)
assert no_duplicate_source_rows(source)

direct, shared, unallocated = classify_each_source_once(source)

ledger = assign_direct_costs(direct, ownership_map_version)

for pool in shared:
    rule = approved_rule_for(pool, period)
    driver = validated_driver_values(pool, period, rule.version)
    if driver.missing_or_invalid:
        unallocated.add(pool, reason="MISSING_DRIVER")
        continue

    shares = normalize_nonnegative_driver(driver)
    assert sum(shares) == 1
    amounts = allocate_with_deterministic_rounding(pool.amount, shares)
    assert sum(amounts) == pool.amount
    ledger.add(amounts, source_pool=pool.id, rule=rule.version)

assert source.in_scope_total == (
    sum(ledger.amounts) + sum(unallocated.amounts)
)
publish_showback(ledger, unallocated, source.snapshot_id)
~~~

Với một pool có nhiều source rows, cần thống nhất cách cộng và làm tròn từng source hoặc tổng pool. Không phân bổ lại chính ledger đầu ra như thể đó là nguồn charge mới, vì dễ tạo vòng lặp và đếm trùng.

## 15. Quy tắc chất lượng dữ liệu và đối soát

**Phân bổ chi phí là một phép biến đổi dữ liệu tài chính**, vì vậy cần kiểm tra giống các hệ thống báo cáo quan trọng.

### 15.1. Các invariant bắt buộc

Với một scope/kỳ/currency/cost basis cố định:

\[
\text{Source total}
=\text{Direct allocated}
+\text{Shared allocated}
+\text{Unallocated}
\]

Ở mức từng pool:

\[
\text{Pool amount}=\sum_{i} \text{Allocated amount}_{i}
\]

Và:

- Mỗi source charge được phân loại đúng một lần.
- Không có rule với tỷ lệ âm hoặc tổng tỷ lệ không bằng 100% nếu rule yêu cầu chia hết.
- Owner mapping có ngày hiệu lực, không có hai owner cạnh tranh cho cùng một khoản nếu không có luật ưu tiên.
- Driver có đơn vị, khoảng đo, nguồn và trạng thái chất lượng.
- Kết quả làm tròn không làm mất hoặc tạo tiền.
- Dòng thuộc currency khác được xử lý riêng cho đến khi có quy tắc quy đổi đã duyệt.

### 15.2. Chỉ số chất lượng chương trình FinOps

| Chỉ số | Công thức gợi ý | Giải thích |
| --- | --- | --- |
| **Allocation coverage** | (Direct + shared allocated) / in-scope total | Bao nhiêu chi phí đã có nơi chịu |
| **Unallocated rate** | Unallocated / in-scope total | Phần phải điều tra hoặc giữ central |
| **Tag compliance** | Tài nguyên đủ tag / tài nguyên áp dụng quy tắc | Không phản ánh trực tiếp chi phí untagged |
| **Rule coverage** | Shared pool có rule hợp lệ / tổng shared pool | Sẵn sàng phân bổ |
| **Data freshness** | Kỳ đến mốc dữ liệu mới nhất | Dữ liệu có đủ để chốt tháng? |
| **Reconciliation difference** | Source total − output total | Phải bằng 0 trong phạm vi đã định |
| **Disputed allocated cost** | Tổng đang tranh chấp / tổng đề nghị chargeback | Đo mức chấp nhận của owner |

Một mục tiêu mẫu có thể là **coverage trên 95% và reconciliation difference bằng 0**. Ngưỡng 95% là quyết định của tổ chức, không phải chuẩn Azure. Không che 5% còn lại bằng cách gán vào owner mặc định mà không có bằng chứng.

### 15.3. Late-arriving data và correction

Dữ liệu Cost Management có thể được ghi nhận trễ, điều chỉnh, refund hoặc thay đổi kỳ. Do đó:

1. Tạo báo cáo **provisional** cho kỳ đang chạy.
2. Chốt theo mốc dữ liệu đủ độ trễ và hóa đơn phù hợp.
3. Lưu immutable snapshot, rule version, tỷ lệ và kết quả.
4. Nếu có adjustment về sau, tạo **correction ledger** cho kỳ liên quan hoặc kỳ kế tiếp theo chính sách Finance.
5. Tránh ghi đè mất lịch sử showback/chargeback đã phát hành.

Không xem báo cáo hôm nay là con số final chỉ vì đã hết ngày cuối tháng.

## 16. Reservation, savings plan và chi phí cam kết

Commitment tạo thách thức đặc biệt: giá trị thanh toán và chi phí kinh tế của usage có thể xuất hiện ở những thời điểm khác nhau.

### 16.1. Chọn cơ sở phù hợp

Nếu mục đích là xem **đơn vị sử dụng compute thực sự chịu chi phí kinh tế bao nhiêu**, một cơ sở amortized có thể hữu ích vì phân bổ commitment qua thời gian và theo lợi ích được hưởng. Nếu mục đích là đối soát **hóa đơn tháng**, phải dựa vào dòng mua/chi phí có thật trên chứng từ và dữ liệu actual thích hợp.

**Không lấy khoản mua reservation trả trước cộng lại vào tất cả cost center** khi dữ liệu amortized của cùng quyền lợi đã được tính trong base. Làm vậy đếm trùng chi phí.

### 16.2. Unused commitment

Giả sử mua cam kết đủ điều kiện trị giá giả định 1.200 USD cho một kỳ kinh tế nhưng chỉ dùng được 80% giá trị theo quy tắc đánh giá nội bộ:

| Thành phần minh họa | Giá trị |
| --- | ---: |
| Tổng chi phí cam kết phân bổ cho kỳ | 1.200 USD |
| Phần gắn với usage đủ điều kiện (80%) | 960 USD |
| Phần chưa sử dụng (20%) | 240 USD |

Tổ chức có thể quyết định:

- Ghi 960 USD cho các sản phẩm hưởng lợi và 240 USD cho central FinOps/platform để thúc đẩy tối ưu coverage; hoặc
- Phân bổ cả phần chưa sử dụng cho các đơn vị đã yêu cầu cam kết theo chính sách được duyệt.

**Đây là bài toán chính sách nội bộ**, không mô tả chính xác thuật toán Azure dùng phân bổ từng giao dịch savings plan/reservation. Khi thực hành, dùng báo cáo utilization, coverage và dữ liệu amortized thực của account.

### 16.3. Quyền lợi không đồng nghĩa khoản phí âm

Một workload được hưởng reservation có thể hiển thị usage cost khác pay-as-you-go, trong khi purchase được ghi ở phạm vi billing khác. Cần đối chiếu **benefit utilization, unused commitments, scope chia sẻ và charge categories** trước khi đưa khoản đó vào báo cáo cost center.

## 17. Credit, taxes, Marketplace, support và phí tài chính

Đối với các khoản ngoài usage, chính sách phải nói rõ **được chia hay để trung tâm**:

| Khoản | Cách xử lý thường cân nhắc | Cần lưu ý |
| --- | --- | --- |
| **Promotional credit** | Theo chủ thể được hưởng hoặc giữ riêng ở cấp billing | Điều kiện áp dụng có thể giới hạn dịch vụ và kỳ |
| **Refund / adjustment** | Hoàn về đúng cost center/pool của chi phí gốc nếu đủ thông tin | Có thể xuất hiện kỳ sau |
| **Tax** | Theo Finance/legal, có thể không đưa vào showback kỹ thuật | Pháp nhân, địa điểm, điều kiện thuế |
| **Support plan** | Central IT hoặc phân bổ theo chính sách doanh nghiệp | Không phải mọi khoản có resource ID |
| **Marketplace** | Gán trực tiếp sản phẩm mua hoặc chính sách dùng chung | Hợp đồng publisher và hình thức hóa đơn có thể khác |
| **Exchange difference** | Giữ riêng hoặc phân bổ theo quy tắc tài chính | Không dùng tỷ giá hiện tại sửa hóa đơn đã chốt |
| **Security compliance overhead** | Theo tài nguyên được bảo vệ hoặc central policy | Không tính hai lần phí đã nằm trong dịch vụ |

**Không có một bộ quy tắc universal** cho các khoản này. Với chargeback có tính pháp lý/kế toán, quyết định về tax, credit và điều chỉnh thuộc Finance và chính sách của tổ chức; nhóm kỹ thuật cung cấp dữ liệu và công thức minh bạch.

## 18. Showback dashboard nên hiển thị gì?

Một dashboard dành cho đội kỹ thuật cần giúp tìm **nguyên nhân** chứ không chỉ xem số tiền.

| Màn hình | Nội dung | Câu hỏi được trả lời |
| --- | --- | --- |
| **Overview** | Tổng theo cost center, xu hướng, direct/shared/unallocated | Chúng ta đang tốn bao nhiêu? |
| **Cost drivers** | Compute, database, storage, network, logs, commitments | Meter nào làm tăng chi phí? |
| **Shared allocation** | Pool amount, driver, weight, rule version | Tại sao nhóm bị tính 900 USD AKS? |
| **Quality** | Missing tags, missing driver, unallocated, reconciliation | Báo cáo tin cậy đến đâu? |
| **Unit economics** | Cost trên đơn hàng/job/transaction thành công | Chi phí kinh doanh trên một đơn vị ra sao? |
| **Actions** | Rightsizing, idle resources, log ingestion, storage retention | Nhóm có thể thay đổi điều gì? |
| **Governance** | Kỳ, currency, cost basis, snapshot, owner, trạng thái duyệt | Đây có phải số liệu đã chốt? |

### 18.1. Unit economics sau phân bổ

Giả sử Orders hoàn tất **250.000 đơn hàng hợp lệ** trong kỳ và chịu cost basis **3.230 USD**:

\[
\text{Cost/order} = 3.230/250.000 = 0{,}01292\ \text{USD}
\]

\[
\text{Cost/1.000 orders}=12{,}92\ \text{USD}
\]

Đây là phép tính ví dụ, chưa bao gồm tất cả loại chi phí doanh nghiệp. Khi so sánh theo tháng, phải giữ **định nghĩa đơn hàng thành công, phạm vi cost và cách phân bổ** nhất quán. Không so trực tiếp cost/order của Orders với cost/job của Analytics như cùng một thước đo.

### 18.2. Đo hiệu quả mà không tạo động cơ sai

Nếu chỉ thưởng cho nhóm giảm Azure cost, nhóm có thể tắt log cần thiết, hạ backup retention hoặc giảm replica khiến SLO suy giảm. Showback cần kèm **availability, latency, error budget, security/compliance và chi phí trên giao dịch thành công**.

Mục tiêu FinOps là giúp ra quyết định tốt hơn về **giá trị và hiệu quả**, chứ không buộc mọi khoản chi phí của hệ thống phải luôn giảm.

## 19. Chargeback: quy trình phê duyệt và bút toán nội bộ

Chargeback cần thêm kiểm soát so với showback:

1. **Kỳ được chốt:** chi phí gốc, drivers, rule version và unallocated đã được kiểm tra.
2. **Owner xác nhận:** từng nhóm có thời gian xem và khiếu nại nếu mapping/driver sai.
3. **FinOps phê duyệt:** xác nhận mô hình, consistency và phân loại ngoại lệ.
4. **Finance xác nhận:** policy thuế, credit, adjustment, tài khoản kế toán và đồng tiền.
5. **Phát hành ledger:** định danh kỳ, chứng từ nội bộ, cost center nhận, số tiền, nguồn, người duyệt.
6. **Ghi nhận đối ứng:** tuân thủ hệ thống sổ cái để không tính trùng chi phí tổ chức.
7. **Điều chỉnh sau phát hành:** tạo reversal/correction hoặc dòng điều chỉnh có giải thích.

### 19.1. Bút toán minh họa

Giả sử central IT ban đầu nhận 6.800 USD chi phí thuộc ba nhóm đã được xác định và tổ chức dùng cơ chế hạch toán nội bộ:

~~~text
Debit  CC-410 Orders:     3,230 USD
Debit  CC-420 Catalog:    2,110 USD
Debit  CC-430 Analytics:  1,460 USD
Credit Central IT pool:   6,800 USD
~~~

Đây là **sơ đồ chuyển trách nhiệm nội bộ để giải thích tổng**, không phải hướng dẫn định khoản theo chuẩn kế toán cụ thể. Mã tài khoản, đối tượng debit/credit, thuế và cách đăng ký trong ERP phải theo Finance. Khoản **200 USD unallocated** vẫn được quản lý ở trung tâm hoặc khoản chờ xử lý theo chính sách.

**Không xuất hóa đơn Azure giả** hoặc coi bảng chargeback là invoice từ Microsoft. Nếu tổ chức sử dụng intercompany billing, phải xử lý riêng điều kiện pháp lý và thuế.

### 19.2. Quy trình giải quyết tranh chấp

Tình huống: Catalog cho rằng một resource trị giá 120 USD trong pool network đã chuyển chủ cho Orders từ ngày 15 của tháng. Bước xử lý:

1. Ghi ticket dispute với kỳ, cost row/pool, owner và bằng chứng.
2. Kiểm tra mốc chuyển ownership, measurement period và mapping có hiệu lực.
3. Tính lại theo chính sách ngày có hiệu lực nếu dữ liệu hỗ trợ.
4. Cho hai owner và FinOps xác nhận.
5. Nếu kỳ đã chốt, tạo adjustment có mã tham chiếu; không sửa âm thầm ledger cũ.
6. Kiểm tra reconciliation sau adjustment.

Hạn xử lý tranh chấp cần được công bố. Nếu nhóm không phản hồi trong hạn, áp dụng quy tắc phê duyệt mặc định đã được thống nhất trước, tránh tùy tiện.

## 20. Governance và trách nhiệm của từng vai trò

| Vai trò | Trách nhiệm |
| --- | --- |
| **FinOps / Cloud economics** | Quy tắc phân bổ, chất lượng dữ liệu, cost drivers, theo dõi hiệu quả |
| **Platform/SRE** | Inventory shared services, Kubernetes/observability/network metrics, tối ưu hạ tầng |
| **Product owner** | Xác nhận ownership, tiêu thụ dịch vụ, kế hoạch tối ưu và dispute |
| **Finance** | Cost center, chính sách chargeback, invoice reconciliation, ledger và phê duyệt |
| **Cloud administrator** | Billing/Cost Management access, tagging policy, exports và quản trị subscription |
| **Security/Compliance** | Kiểm soát quyền dữ liệu tài chính, lưu giữ chứng từ và bằng chứng |

Mỗi shared pool cần tối thiểu **một owner rule**, **một owner dữ liệu driver**, **ngày review tiếp theo** và **cơ chế xử lý khi mất dữ liệu**. Nếu không ai chịu trách nhiệm về rule, kết quả chargeback khó được tin cậy.

### 20.1. Bảo vệ dữ liệu tài chính

Dữ liệu cost có thể làm lộ giá hợp đồng, discounts, cấu trúc tổ chức, workload, tài nguyên và thông tin kinh doanh. Cần:

- Dùng Microsoft Entra ID và quyền truy cập theo vai trò, giới hạn scope.
- Tách quyền xem showback của một nhóm khỏi quyền xem giá/hóa đơn toàn tổ chức.
- Bảo vệ storage chứa exports bằng access control, networking và retention phù hợp.
- Không nhúng access key hoặc bí mật billing vào báo cáo.
- Dùng managed identity/service principal có quyền tối thiểu khi tự động xuất dữ liệu.
- Có audit trail cho rule changes, exceptions, approvals và truy cập nhạy cảm.

Trong dashboard cho product team, có thể chỉ hiển thị **allocated cost** và driver đã được phép công bố; hạn chế để lộ giá thương lượng hoặc thông tin của nhóm khác nếu không cần thiết.

## 21. Những sai lầm thường gặp

| Vấn đề | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Lấy tổng invoice chia đều cho mọi nhóm | Nhóm dùng ít chịu phí bất công | Phân loại direct/shared/non-usage trước |
| Phân bổ toàn bộ AKS theo số Pod | Pod lớn/nhỏ và thời gian tồn tại bị coi như nhau | Dùng CPU/memory requests/usage và xác định idle |
| Lấy ingress bytes chia phí outbound egress | Driver khác bản chất meter | Đo đúng outbound hoặc driver gần hơn |
| Mọi khoản không tag đều gán cho Platform | Sai ownership và tạo động cơ bỏ tag | Mapping theo nguồn tin cậy, nhóm pending riêng |
| Cộng actual và amortized | Đếm trùng khoản mua cam kết | Chọn một cost basis nhất quán |
| Bỏ phần unused reservation | Tổng allocated nhỏ hơn cost basis | Giữ unused commitment ở central hoặc theo policy |
| Dùng tag hiện tại áp lên lịch sử | Thay đổi chargeback quá khứ | Mapping hiệu lực theo ngày và snapshot |
| Chia phần trăm nhưng tổng không bằng 100% | Mất/tạo tiền | Validate và rounding deterministic |
| Cùng một charge xuất hiện hai pool | Đếm trùng | ID charge gốc và unique classification |
| Dùng số request có sampling như số tuyệt đối | Allocation sai | Kiểm tra telemetry sampling, dùng metric đáng tin |
| Giảm unallocated bằng cách ép 100% mọi khoản | Mất minh bạch dữ liệu yếu | Giữ unallocated với lý do và owner xử lý |
| Cost Management allocation được xem là chuyển tiền thật | Kỳ vọng sai về hóa đơn/bút toán | Tách cost analytics và ERP chargeback |
| Không có dispute process | Nhóm mất niềm tin | Công bố rule, bằng chứng và correction ledger |
| Dashboard chi phí thiếu SLO | Tối ưu làm giảm chất lượng dịch vụ | Kèm latency, availability, security và unit economics |
| Không theo dõi currency và kỳ | Tổng không khớp | Cố định scope, cost basis, billing period, currency |

## 22. Bài thực hành: xây báo cáo showback và chargeback

**Bối cảnh:** Ba nhóm Orders, Catalog, Analytics tiêu thụ tài nguyên Azure, có một cụm AKS chung, gateway chung, workspace logs và nền tảng bảo mật. Bạn là kỹ sư phối hợp FinOps triển khai phân bổ.

### Bước 1 — Xác lập phạm vi

Viết thông tin về billing scope, subscription, cost basis, currency, kỳ, ngày chốt, dữ liệu source và danh sách cost center. Ghi riêng các khoản ngoài cơ sở phân bổ như tax/credit nếu chính sách yêu cầu.

**Đầu ra:** một tờ khai phương pháp (methodology sheet) có người duyệt và phiên bản.

### Bước 2 — Chuẩn hóa direct ownership

Dùng bảng direct cost phần 12.1 và tạo mapping ứng dụng → cost center. Kiểm tra 3.800 USD direct được phân loại một lần, không có dòng nào cũng nằm trong AKS pool.

**Đầu ra:** bảng direct ledger có resource/cost row reference.

### Bước 3 — Tạo shared pools và driver

Dùng bảng pool ở phần 12.2. Với mỗi pool:

- Nêu vì sao driver phù hợp bản chất meter.
- Ghi nguồn driver, kỳ đo và rule version.
- Kiểm tra tỷ lệ không âm, tổng mỗi hàng bằng 100%.
- Nêu phương án khi data thiếu và ai phê duyệt fallback.

**Đầu ra:** bảng rules và driver rõ ràng.

### Bước 4 — Tính phân bổ

Tính từng khoản:

- AKS: 900 / 540 / 360 USD.
- Gateway: 300 / 210 / 90 USD.
- Observability: 180 / 100 / 120 USD.
- Security: 100 / 60 / 40 USD.

Cộng với direct cost và giữ riêng 200 USD unallocated.

**Kết quả mong đợi:** Orders **3.230 USD**, Catalog **2.110 USD**, Analytics **1.460 USD**, Unallocated **200 USD**, tổng **7.000 USD**.

### Bước 5 — Diễn tập dispute

Giả sử 120 USD direct cost đã được gắn nhầm Catalog nhưng bằng chứng cho thấy thuộc Orders. Đề xuất cách sửa mapping và tính lại:

- Orders tăng từ **3.230** lên **3.350 USD**.
- Catalog giảm từ **2.110** xuống **1.990 USD**.
- Analytics và Unallocated giữ nguyên.
- Tổng toàn bộ vẫn là **7.000 USD**.

Đây là tình huống thay đổi **ownership của dòng direct cost**, không thay đổi hóa đơn gốc. Nếu kỳ đã chốt, cần adjustment/version thay vì sửa âm thầm.

### Bước 6 — Chuẩn bị chargeback

Tạo một bảng chuyển trách nhiệm nội bộ có cost center, period, currency, số tiền, nguồn snapshot, rule version, dispute status và người phê duyệt. Giải thích bút toán đối ứng để không ghi nhận trùng.

**Tiêu chí đạt:** có thể truy ngược từ số tiền chargeback đến dòng chi phí gốc/driver; kiểm tra tổng bằng 0 chênh lệch và ghi rõ 200 USD chưa phân bổ.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Showback và chargeback khác nhau ở kết quả nào?  
**Đáp án:** Showback báo cáo cho nhóm biết chi phí; chargeback dùng số liệu đã duyệt để ghi nhận trách nhiệm ngân sách/hạch toán nội bộ.

**Câu 2.** Chi phí AKS node pool dùng chung có nên gán toàn bộ theo resource group quản lý cluster?  
**Đáp án:** Không tự động. Phải xem những workload sử dụng node, idle capacity và phương pháp phân bổ phù hợp.

**Câu 3.** Tại sao không dùng chung request count làm driver cho mọi pool?  
**Đáp án:** Bản chất phí khác nhau: log ingestion theo GiB, egress theo byte, compute theo capacity, database theo nhu cầu xử lý. Request count có thể không tương quan đủ tốt.

**Câu 4.** Trong ví dụ, Orders chịu bao nhiêu shared cost?  
**Đáp án:** 900 + 300 + 180 + 100 = **1.480 USD**.

**Câu 5.** Tổng showback có 7.000 USD nhưng chỉ 6.800 USD gắn ba nhóm. Có sai không?  
**Đáp án:** Không; còn 200 USD unallocated đã được công bố. Tổng tất cả các nhóm cộng unallocated vẫn bằng 7.000 USD.

**Câu 6.** Có thể cộng actual và amortized cost để tính chargeback không?  
**Đáp án:** Không. Đây có thể là hai góc nhìn của cùng khoản phí, đặc biệt với commitment, dễ đếm trùng.

**Câu 7.** Tại sao phải giữ mapping ownership theo thời gian?  
**Đáp án:** Vì owner có thể thay đổi; dùng owner hiện tại cho chi phí quá khứ có thể sửa sai báo cáo đã chốt.

**Câu 8.** Bật cost allocation rule trong Cost Management có làm Microsoft phát hành hóa đơn riêng cho từng namespace không?  
**Đáp án:** Không. Quy tắc phân bổ phục vụ phân tích trong phạm vi được hỗ trợ; chargeback tài chính cần quy trình nội bộ riêng.

**Câu 9.** Pool 100 USD chia đều ba nhóm nên làm tròn thế nào?  
**Đáp án:** Dùng quy tắc phân bổ phần dư ổn định, ví dụ 33,34 + 33,33 + 33,33 = 100 USD.

**Câu 10.** Nếu nguồn telemetry bị sampling và thiếu data, có nên tự động chia hết pool cho các nhóm theo ước lượng không?  
**Đáp án:** Chỉ khi có fallback policy đã duyệt và nêu rõ mức tin cậy; nếu không, giữ unallocated để điều tra.

**Câu 11.** Vì sao khoản reservation trả trước có thể làm actual cost và amortized cost khác nhau?  
**Đáp án:** Actual có thể ghi nhận purchase tại thời điểm mua, còn amortized phân bổ giá trị cam kết cho thời gian/mức hưởng lợi để phân tích kinh tế.

**Câu 12.** Chargeback có được làm tăng tổng tiền chi phí của tổ chức không?  
**Đáp án:** Không. Chargeback là phân bổ trách nhiệm nội bộ; cần bút toán đối ứng và reconciliation để không nhân đôi chi phí gốc.

## 24. Checklist triển khai tại doanh nghiệp

- [ ] Xác định rõ showback hay chargeback, mục tiêu và các bên phê duyệt.
- [ ] Có danh mục ứng dụng, owner, cost center, shared service và kỳ hiệu lực.
- [ ] Chọn cost basis, currency, billing scope và cách xử lý invoice/non-usage.
- [ ] Thu Azure Cost Details/Exports từ nguồn tin cậy, giữ snapshot và schema mapping.
- [ ] Có chuẩn tag, ownership mapping và cơ chế xử lý thiếu tag.
- [ ] Mỗi source charge được phân loại một lần thành direct/shared/unallocated hoặc loại khác theo chính sách.
- [ ] Mỗi shared pool có driver phù hợp, nguồn metric, owner, rule version và fallback policy.
- [ ] Có quy tắc phân bổ idle AKS, shared database, network, logs và commitments.
- [ ] Không đếm trùng purchase với amortized usage, và không ép chia những khoản không có căn cứ.
- [ ] Kiểm tra tổng shared allocation, rounding, reconciliation và allocation coverage.
- [ ] Dashboard hiển thị direct/shared/unallocated, driver, xu hướng và unit economics.
- [ ] Cost center owner có quyền xem và quy trình dispute rõ ràng.
- [ ] Chargeback có Finance approval, chứng từ nội bộ và bút toán đối ứng.
- [ ] Có lịch chốt kỳ, snapshot bất biến, correction ledger và audit trail.
- [ ] Báo cáo chi phí gắn với SLO, bảo mật và nhu cầu độ tin cậy của ứng dụng.

Showback tạo **sự minh bạch về nơi chi phí phát sinh**, còn chargeback biến thông tin đó thành **trách nhiệm tài chính có quy tắc**. Trên Microsoft Azure, nền tảng của cả hai là dữ liệu cost đủ chất lượng, ownership rõ ràng, driver phản ánh mức tiêu thụ, cơ chế kiểm tra bảo toàn tổng và một quy trình phê duyệt có thể truy vết. Khi kết hợp những yếu tố đó, tổ chức có thể tối ưu hạ tầng một cách hợp tác và công bằng, đồng thời giữ nguyên tính đúng đắn của hóa đơn và báo cáo tài chính.
