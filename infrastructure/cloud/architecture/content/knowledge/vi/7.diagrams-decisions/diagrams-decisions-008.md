# Giữ tài liệu và sơ đồ đồng bộ với hệ thống triển khai

Một sơ đồ kiến trúc chỉ hữu ích khi người đọc có thể dùng nó để hiểu **hệ thống đang thực sự chạy** và đưa ra quyết định đúng. Sơ đồ đẹp nhưng thiếu database mới được tạo, vẽ nhầm kết nối Internet thành kết nối riêng tư, hoặc vẫn mô tả một vùng triển khai đã ngừng sử dụng có thể khiến nhóm vận hành xử lý sự cố sai, đánh giá rủi ro bảo mật thiếu sót và lập kế hoạch khôi phục không khả thi.

Trong hệ thống cloud, kiến trúc có thể thay đổi qua từng bản phát hành: một nhóm tạo thêm service, đổi cấu hình mạng, bật replication, thay nhà cung cấp thanh toán hoặc thêm vùng dự phòng. Việc cập nhật tài liệu bằng trí nhớ của một người khó theo kịp nhịp thay đổi đó. Vì vậy, **đồng bộ tài liệu và sơ đồ với hệ thống triển khai phải trở thành một phần của quy trình phát triển và vận hành**.

Bài này thuộc chương **Sơ đồ và quyết định** của module **CLOUD_ARCHITECTURE**. Trọng tâm là nối yêu cầu nghiệp vụ, quyết định về mạng/compute/dữ liệu/mô hình triển khai và kiểm chứng Well-Architected với những tài nguyên, cấu hình, luồng dữ liệu và cơ chế vận hành có thể quan sát. Mục đích không phải tạo một tài liệu bất biến, mà là thiết lập quy trình giúp mọi thay đổi quan trọng đều có người chịu trách nhiệm, được kiểm tra và để lại bằng chứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **kiến trúc dự kiến**, **kiến trúc đã triển khai** và **trạng thái đang vận hành**, hiểu tại sao không thể dùng một nguồn làm bằng chứng tuyệt đối cho cả ba.
2. Chọn đúng loại tài liệu: sơ đồ ngữ cảnh, container, thành phần, triển khai, luồng dữ liệu, mạng, runbook và Architecture Decision Record (ADR).
3. Gắn thay đổi kiến trúc vào pull request, Infrastructure as Code (IaC), pipeline triển khai, kiểm thử và quy trình phát hành.
4. Xây dựng quy trình đối chiếu tài liệu với tài nguyên cloud, cấu hình production và dữ liệu quan sát.
5. Thiết kế cách phát hiện, phân loại, xử lý **architecture drift** và các thay đổi khẩn cấp ngoài quy trình.
6. Đo mức độ cập nhật, chất lượng bằng chứng và thời gian sửa sai lệch thay vì chỉ kiểm tra “đã có tài liệu”.
7. Đánh giá đánh đổi độ tin cậy, bảo mật, hiệu năng, chi phí và công sức vận hành theo Well-Architected.

## 2. Thế nào là “đồng bộ”?

### 2.1. Ba góc nhìn về một hệ thống

| Góc nhìn | Câu hỏi | Nguồn bằng chứng thường dùng | Điều có thể thiếu |
|---|---|---|---|
| **Intended / planned architecture** – kiến trúc dự kiến | Hệ thống **nên** gồm những gì, vì sao quyết định như vậy? | Yêu cầu, ADR, sơ đồ thiết kế, policy, IaC đang được đề xuất | Chưa chắc đã triển khai hoặc kích hoạt |
| **Deployed / configured architecture** – kiến trúc đã triển khai | Những tài nguyên và cấu hình nào **đang tồn tại** trong môi trường mục tiêu? | Inventory, API của cloud, trạng thái IaC, cấu hình Kubernetes, deployment manifest, catalog dịch vụ | Chưa phản ánh đầy đủ runtime, feature flags hoặc lưu lượng thực tế |
| **Observed / runtime architecture** – kiến trúc quan sát | Những thành phần và đường gọi nào **đang hoạt động**, gặp lỗi hay phát sinh dữ liệu? | Traces, metrics, logs, flow logs, service mesh telemetry, kết quả kiểm thử | Chỉ thấy những gì được instrument; có thể bỏ sót luồng hiếm hoặc tài nguyên đang chờ |

Ví dụ: IaC khai báo một database phụ để phục vụ đọc; inventory xác nhận instance đã được tạo; nhưng telemetry cho thấy ứng dụng vẫn đọc trực tiếp từ database chính. Nếu sơ đồ đánh dấu database phụ đang gánh đọc production, tài liệu đã đi trước thực tế.

Một ví dụ khác: load balancer có hai target ở hai zone, nhưng một target liên tục không vượt health check. Sơ đồ triển khai vẫn đúng về mặt số tài nguyên; mô tả “đang chịu lỗi một zone” lại cần kiểm chứng bằng khả năng phục vụ thực tế.

**Nguyên tắc:** xác định rõ mỗi sơ đồ đang mô tả *desired*, *deployed* hay *observed*, môi trường nào và thời điểm/bản phát hành nào. Tính “đồng bộ” là sự nhất quán có thể kiểm chứng giữa tuyên bố của tài liệu và phạm vi hệ thống được tuyên bố đó mô tả.

### 2.2. Không tồn tại một nguồn sự thật cho mọi lớp

Khái niệm *single source of truth* hữu ích khi áp dụng **theo từng loại thông tin**, nhưng dễ gây hiểu nhầm nếu coi một repository hoặc một dashboard chứa toàn bộ sự thật.

| Loại thông tin | Nguồn có thẩm quyền nên xác định | Cách đối chiếu |
|---|---|---|
| **Lý do chọn kiến trúc** | ADR đã được duyệt | So sánh quyết định với cấu hình và mục tiêu nghiệp vụ hiện tại |
| **Cấu hình hạ tầng mong muốn** | IaC, GitOps manifest và policy được duyệt | Plan/diff với trạng thái tài nguyên thực |
| **Tài nguyên cloud đang tồn tại** | API inventory/configuration của nhà cung cấp theo tài khoản/region | So với IaC và danh mục owner |
| **Phiên bản phần mềm đang chạy** | Hệ thống triển khai và runtime rollout status | So với commit, artifact và release record |
| **Phụ thuộc và lưu lượng runtime** | Distributed tracing, network telemetry và kiểm thử chủ động | So với sơ đồ luồng giao tiếp và trust boundary |
| **Cách vận hành/khôi phục** | Runbook có owner, được kiểm thử định kỳ | Diễn tập lỗi, kết quả restore/failover thực tế |
| **Chính sách bảo mật và dữ liệu** | Policy, phân loại dữ liệu, yêu cầu pháp lý/hợp đồng được phê duyệt | Config scan, IAM review, data-flow review và audit evidence |

Các hệ thống trên có thể mâu thuẫn; chính việc phát hiện mâu thuẫn là tín hiệu cần điều tra. Không nên tự chọn nguồn thuận tiện nhất rồi tuyên bố hệ thống “đã đồng bộ”.

## 3. Chọn sơ đồ đúng mục đích và mức trừu tượng

Một bộ tài liệu tốt giúp người đọc chuyển từ câu hỏi **ai sử dụng hệ thống** đến **dịch vụ nào chạy ở đâu, giao tiếp ra sao và phục hồi thế nào**. Không cần gom tất cả vào một sơ đồ dày đặc.

### 3.1. Các mức sơ đồ nên duy trì

| Tài liệu / sơ đồ | Đối tượng đọc | Nội dung tối thiểu cần cập nhật | Khi nào cần sửa |
|---|---|---|---|
| **System Context – bối cảnh hệ thống** | Product, architect, security, bên tích hợp | Người dùng, hệ thống ngoài, ranh giới trách nhiệm, luồng nghiệp vụ chính | Thêm đối tác, hệ thống ngoài, luồng dữ liệu hoặc nhóm người dùng |
| **Container – ứng dụng/dịch vụ và kho dữ liệu** | Developer, architect, SRE | Các service, API, queue, database, owner và quan hệ giao tiếp | Thêm/tách/gộp service, đổi datastore, thay giao thức |
| **Component / sequence – thành phần hoặc quy trình** | Developer, reviewer | Các thành phần quan trọng và trình tự xử lý; transaction, retry, timeout, consistency | Đổi quy trình nghiệp vụ hoặc hợp đồng liên dịch vụ |
| **Deployment topology – triển khai** | SRE, cloud/platform, security | Tài khoản/subscription, region, zone, cụm, compute, database, load balancer, đường kết nối | Thêm zone/region, thay mô hình HA/DR, thay compute |
| **Network / trust boundaries** | Security, network, SRE | Public/private ingress, egress, cổng/giao thức, subnet, security group, IAM boundary | Mở endpoint, thay DNS, routing, firewall, private link |
| **Data-flow / data classification** | Security, data, compliance | Dữ liệu nhạy cảm, nơi xử lý/lưu/backup, chuyển qua biên giới, ai có quyền truy cập | Thêm trường dữ liệu, replica, analytics, CDN, đối tác |
| **ADR – hồ sơ quyết định** | Người phát triển tương lai, reviewer | Bối cảnh, lựa chọn, lý do, đánh đổi, hệ quả và quyết định thay thế | Khi ra hoặc thay một quyết định đáng kể |
| **Runbook / DR plan** | On-call, incident commander | Dấu hiệu lỗi, quyền truy cập, lệnh/đường thao tác, rollback, phục hồi, xác nhận | Khi quy trình vận hành, đường kết nối hoặc công cụ thay đổi |

Một ADR trả lời **vì sao**; sơ đồ trả lời **thành phần nào kết nối thế nào**; IaC trả lời **cấu hình mong muốn nào có thể áp dụng**; telemetry trả lời **hệ thống đã hành xử ra sao**. Chúng bổ sung lẫn nhau.

### 3.2. Cấu trúc sơ đồ nhất quán

Mỗi sơ đồ cần metadata để người đọc nhận biết phạm vi. Mẫu tiêu đề:

~~~text
Tên: Nền tảng đặt chỗ - Deployment topology
Environment: production
Cloud account / project: <mã không nhạy cảm theo quy ước nội bộ>
Region: region-primary; region-dr (DR khi được kích hoạt)
View: deployed topology / thiết kế đã được duyệt
Owner: nhóm Platform + nhóm Booking
Revision: release-2026.11 / commit liên quan
Last verified: ngày kiểm chứng gần nhất
Evidence: link tới inventory, IaC, release và dashboard
Assumptions: DR đang ở chế độ warm standby
~~~

Không nhúng private key, token, mật khẩu hoặc thông tin nhận dạng nhạy cảm vào hình. Khi cần địa chỉ/IP, tên tài khoản hoặc mã tài nguyên cụ thể để vận hành, đưa vào kho tài liệu có phân quyền thay vì công bố công khai.

### 3.3. Ví dụ hai góc nhìn của một sản phẩm

**Góc nhìn logic** mô tả quan hệ dịch vụ và dữ liệu:

~~~mermaid
flowchart LR
    C[Người dùng] --> EDGE[Web / API Gateway]
    EDGE --> BOOK[Booking Service]
    EDGE --> LIST[Listing Service]
    BOOK --> DBB[(Booking DB)]
    LIST --> DBL[(Listing DB)]
    BOOK --> BUS[(Event Broker)]
    BUS --> NOTIFY[Notification Service]
    BOOK --> PAY[Payment Provider]
~~~

**Góc nhìn triển khai** mô tả failure domain và các thành phần chạy trong một region:

~~~mermaid
flowchart TB
    CLIENT[Người dùng Internet] --> WAF[WAF + Public Load Balancer]
    subgraph REGION[Region chính]
        subgraph AZ1[Availability Zone A]
            APP1[App instance A]
        end
        subgraph AZ2[Availability Zone B]
            APP2[App instance B]
        end
        WAF --> APP1
        WAF --> APP2
        APP1 --> DB[(Managed DB - HA)]
        APP2 --> DB
    end
    APP1 --> EXT[Đối tác thanh toán]
    APP2 --> EXT
~~~

Hai sơ đồ biểu diễn các khía cạnh khác nhau của cùng hệ thống. Không nên suy ra DB thực tế trải nhiều zone chỉ từ nhãn “Managed DB - HA”; trong triển khai thật, phải kiểm tra tính năng HA đã bật, trạng thái replication/failover và failure domain của dịch vụ cụ thể. Đường kết nối ngoài region cũng cần thể hiện trên sơ đồ trust boundary/data flow khi có dữ liệu nhạy cảm.

## 4. Architecture drift: sai lệch xuất hiện từ đâu?

**Architecture drift** là sự khác biệt có ý nghĩa giữa kiến trúc được mô tả/được duyệt và hệ thống thực tế. Nó khác với **configuration drift** ở chỗ còn bao gồm ranh giới dịch vụ, đường dữ liệu, phụ thuộc runtime, mức sẵn sàng và quyết định vận hành, không chỉ chênh lệch thuộc tính tài nguyên.

Các nguồn thường gặp:

1. **Thao tác thủ công:** người vận hành mở cổng firewall, thêm instance hoặc đổi quyền IAM trực tiếp trên console nhưng không cập nhật IaC/tài liệu.
2. **Thay đổi qua nhiều pipeline:** một nhóm chỉnh service, nhóm khác chỉnh mạng; sơ đồ chỉ cập nhật một phần.
3. **Cấu hình runtime:** feature flag, routing rule, service discovery, autoscaling hoặc canary làm lưu lượng khác với cấu hình thiết kế ban đầu.
4. **Managed service tự thay đổi:** nhà cung cấp nâng cấp hạ tầng hoặc thay hành vi trong phạm vi hợp đồng; không phải thay đổi nội bộ nào cũng hiện trong inventory.
5. **Thiết bị và công cụ ngoài cloud:** CDN, DNS, SaaS, on-premises, bên thanh toán và hệ thống giám sát nằm ngoài phạm vi IaC của một cloud account.
6. **Tài liệu chỉ cập nhật lúc khởi tạo:** không có owner, trigger hoặc lịch rà soát định kỳ.
7. **Nhiều môi trường:** staging được nâng cấp nhưng sơ đồ production vẫn ghi kiến trúc staging, hoặc ngược lại.
8. **Thay đổi khẩn cấp:** xử lý incident vượt quy trình bình thường, sau đó quên ghi lại lý do và trạng thái cuối.

### 4.1. Không phải mọi khác biệt đều là lỗi

| Khác biệt | Có thể chấp nhận? | Quyết định xử lý |
|---|---|---|
| Tăng từ 3 lên 8 pod do autoscaling theo policy | Có, nếu sơ đồ mô tả nhóm workload và giới hạn capacity thay vì từng pod | Giữ sơ đồ ở mức ổn định; xác minh autoscaler hoạt động theo policy |
| Canary đưa 10% traffic sang phiên bản mới trong thời gian ngắn | Có, nếu nằm trong release được duyệt | Gắn thông tin rollout vào release record/runtime dashboard |
| Một public endpoint mới xuất hiện không nằm trong sơ đồ và policy | Thường là bất thường nghiêm trọng | Kiểm tra exposure, owner và nguồn thay đổi; xử lý theo mức rủi ro |
| Production dùng DB một zone, nhưng sơ đồ vẽ HA đa zone | Không đạt yêu cầu nếu sơ đồ khẳng định khả năng chịu lỗi zone | Điều chỉnh hạ tầng hoặc sửa thiết kế/đánh giá rủi ro, ghi ADR |
| Runbook chỉ đường khôi phục tới cluster đã xóa | Không chấp nhận khi ảnh hưởng phục hồi | Cập nhật và diễn tập runbook |
| Một môi trường sandbox tạm thời không xuất hiện trong sơ đồ production | Có thể chấp nhận nếu tách rõ phạm vi, owner và thời hạn | Theo dõi trong inventory riêng và policy dành cho sandbox |

Không nên tự động thêm mọi instance ngắn hạn vào sơ đồ chính: điều đó làm mất khả năng đọc và gây churn không cần thiết. Hãy quản lý **các thành phần kiến trúc bền vững, ranh giới bảo mật, chính sách và đặc tính vận hành**, còn số lượng tài nguyên động nên biểu diễn bằng nhãn và dashboard.

## 5. “Documentation as Code” tạo nhịp cập nhật cùng phần mềm

### 5.1. Đặt tài liệu gần thay đổi liên quan

Lưu tài liệu dạng text (Markdown, Mermaid, PlantUML hoặc định dạng khai báo khác) trong hệ thống quản lý phiên bản giúp review, diff, truy nguyên commit và rollback dễ hơn so với một tệp hình nhị phân không có bản nguồn.

Một cấu trúc tham khảo cho repository:

~~~text
repository/
  docs/
    architecture/
      README.md
      context.md
      containers.md
      deployment-prod.md
      data-flows.md
      decisions/
        0001-database-ha.md
        0002-event-broker.md
    operations/
      incident-response.md
      disaster-recovery.md
  infrastructure/
    network/
    compute/
    data/
  services/
    booking/
    listing/
  .ci/
    architecture-checks.yml
~~~

Đây là **ví dụ bố trí**, không phải yêu cầu mọi dự án dùng các tên thư mục trên. Dù tài liệu ở cùng monorepo hay repository riêng, điều quan trọng là có đường liên kết hai chiều giữa thay đổi triển khai và tài liệu liên quan.

### 5.2. Các thành phần nên được quản lý bằng mã

| Thành phần | Biểu diễn nên có | Mức tự động hóa khả thi |
|---|---|---|
| Hạ tầng cloud | Terraform/OpenTofu, CloudFormation, Pulumi hoặc công cụ IaC phù hợp | Plan, validate, policy check và inventory diff |
| Kubernetes | Manifest, Helm/Kustomize, GitOps state | Kiểm tra cấu hình và trạng thái reconcile/rollout |
| API | OpenAPI, protobuf, AsyncAPI hoặc contract schema | Kiểm tra compatibility và phát hiện endpoint/event mới |
| Phụ thuộc dịch vụ | Service catalog, metadata, traces và sơ đồ quan hệ | So sánh danh mục khai báo với dependency quan sát |
| Sơ đồ kiến trúc | Mermaid/C4/PlantUML ở dạng văn bản có review | Kiểm tra cú pháp, link và các ID được khai báo |
| Quyết định kiến trúc | ADR có trạng thái, ngày và owner | Kiểm tra mẫu bắt buộc và liên kết PR |
| Runbook / DR | Markdown + script/đường thao tác có kiểm soát | Kiểm tra liên kết; diễn tập thật để xác minh tính đúng đắn |

**Giới hạn:** công cụ tạo sơ đồ từ IaC có thể nhìn thấy subnet, VM và database nhưng không tự hiểu giao dịch nghiệp vụ, sự phụ thuộc ẩn, ranh giới dữ liệu cá nhân hoặc lý do lựa chọn thiết kế. Do đó, sơ đồ sinh tự động nên được xem là **bằng chứng đầu vào** và phải được bổ sung ngữ nghĩa, owner và review con người.

### 5.3. Liên kết thay đổi với tài liệu

Một pull request có thay đổi kiến trúc nên trả lời:

- Thay đổi nào của production hoặc môi trường mục tiêu sẽ xảy ra?
- Những tài liệu/sơ đồ nào chịu tác động?
- Có bổ sung hoặc thay đổi public endpoint, quyền IAM, dữ liệu, dependency, region, zone hoặc cơ chế DR không?
- Quyết định này đã có ADR chưa, hay chỉ là chi tiết triển khai trong quyết định cũ?
- Làm sao xác nhận sau deploy rằng hệ thống thực tế khớp với tuyên bố?
- Ai chịu trách nhiệm review kiến trúc, security, data và vận hành?

Mẫu ngắn có thể đặt trong PR:

~~~markdown
## Architectural impact
- [ ] Không thay đổi topology / trust boundary / data flow
- [ ] Đã cập nhật sơ đồ hoặc tài liệu bị ảnh hưởng
- [ ] Đã cập nhật hoặc liên kết ADR liên quan
- [ ] Đã cập nhật runbook và yêu cầu quan sát/DR
- [ ] Đã kiểm tra IAM, network, vị trí dữ liệu và chi phí

Evidence / links:
- Diagram:
- ADR:
- IaC plan:
- Release / deployment:
- Verification after deploy:
~~~

Không nên bắt mọi thay đổi chính tả hoặc refactor nội bộ tạo ADR mới. Dùng tiêu chí tác động thực tế: giao thức, dữ liệu, bảo mật, failure domain, chi phí, triển khai, hợp đồng và hành vi hệ thống.

## 6. Quy trình chuẩn từ quyết định đến hệ thống đang chạy

### Bước 1 — Mô tả yêu cầu và ràng buộc

Xác định chức năng nghiệp vụ, dự kiến tải, SLO, RTO/RPO, vùng dữ liệu được phép, rủi ro bảo mật, ngân sách và năng lực vận hành. Ví dụ: “Booking API phải tiếp tục xử lý nếu một instance lỗi” là yêu cầu; “dùng ba instance” chỉ là một cách thực hiện.

### Bước 2 — Ghi ADR cho lựa chọn có tác động đáng kể

ADR nên nêu bối cảnh, phương án, lý do chọn, phương án không chọn, đánh đổi và hệ quả. Trạng thái như **Proposed / Accepted / Superseded** giúp biết quyết định nào còn hiệu lực. Nếu thay một quyết định cũ, tạo hoặc cập nhật liên kết tới ADR thay thế; giữ lịch sử để điều tra vì sao hệ thống từng được thiết kế như vậy.

### Bước 3 — Cập nhật sơ đồ thiết kế và hợp đồng

Vẽ lại các view bị tác động: context/container, deployment topology, network/trust boundary, data flow và quy trình nghiệp vụ nếu cần. Ghi rõ môi trường, region và trạng thái **proposed** khi chưa deploy. Thay đổi hợp đồng API/event cần kiểm tra khả năng tương thích với consumer.

### Bước 4 — Thay đổi IaC / ứng dụng trong cùng luồng review

Thay đổi kiến trúc được thể hiện trong những artifact triển khai phù hợp. CI kiểm tra cú pháp, policy, quyền mạng, security scan và những liên kết tài liệu bắt buộc. Reviewer xác nhận tính nhất quán giữa yêu cầu, sơ đồ, ADR và diff của IaC, thay vì chỉ dựa vào biểu tượng cloud trong hình.

### Bước 5 — Triển khai có thể truy nguyên

Liên kết mỗi deployment với commit, artifact, môi trường, người/phương thức phê duyệt và kế hoạch rollback. Nếu staging và production có thời điểm triển khai khác nhau, tài liệu phải nói rõ view áp dụng cho môi trường nào. Cảnh báo khi cấu hình production khác dự kiến hoặc rollout không hoàn tất.

### Bước 6 — Kiểm chứng sau deploy bằng hệ thống thực

Đối chiếu inventory, trạng thái controller, service discovery, health check, metric/trace và cấu hình IAM/network/backup với kỳ vọng. Cập nhật trạng thái tài liệu từ **proposed** sang **verified deployed** khi có bằng chứng. Nếu kết quả khác thiết kế, tạo drift item và phân công xử lý.

### Bước 7 — Quan sát và rà soát liên tục

Đặt lịch reconciliation cho hạ tầng, dependency, ownership, sơ đồ, runbook và cấu hình bảo mật. Không đợi đến khi có sự cố mới phát hiện sơ đồ sai. Tần suất tùy mức rủi ro và tốc độ thay đổi; những kết nối public, quyền nhạy cảm và dữ liệu có thể cần theo dõi gần thời gian thực.

### Luồng tổng quát

~~~mermaid
flowchart TD
    REQ[Yêu cầu nghiệp vụ / SLO / ràng buộc] --> ADR[ADR và sơ đồ proposed]
    ADR --> PR[PR thay đổi app / API / IaC / tài liệu]
    PR --> CI{Kiểm tra tự động + review}
    CI -->|Không đạt| PR
    CI -->|Đạt| DEP[Triển khai có release record]
    DEP --> VERIFY[Inventory + runtime + policy verification]
    VERIFY --> OK{Khớp kỳ vọng?}
    OK -->|Có| DOC[Đánh dấu verified và lưu evidence]
    OK -->|Không| DRIFT[Phân loại drift + owner + hạn xử lý]
    DRIFT --> FIX[Chỉnh hạ tầng hoặc cập nhật thiết kế có duyệt]
    FIX --> PR
    DOC --> OBS[Giám sát và rà soát định kỳ]
    OBS --> VERIFY
~~~

Trong thực tế, hệ thống có thể có nhiều pipeline và công cụ; sơ đồ mô tả **các điểm kiểm soát cần đạt**, không yêu cầu tất cả trong một pipeline duy nhất.

## 7. Tự động hóa kiểm tra mà không đánh đồng “có sơ đồ” với “đúng”

### 7.1. Những kiểm tra CI nên triển khai trước

1. **Tính hợp lệ của nguồn:** Markdown/diagram source parse được, liên kết nội bộ còn tồn tại, không thiếu metadata bắt buộc.
2. **Tác động thay đổi:** đường dẫn IaC, API schema, manifest, IAM/network đã thay đổi thì yêu cầu khai báo ảnh hưởng kiến trúc và liên kết tài liệu tương ứng.
3. **So sánh schema:** endpoint/event hoặc cấu trúc dữ liệu có breaking change phải bị phát hiện, cần kế hoạch tương thích và rollout.
4. **Policy as code:** ngăn các cấu hình nguy hiểm như public storage trái chính sách, security group mở rộng, hoặc triển khai tài nguyên ở vùng bị cấm.
5. **Kiểm tra sở hữu:** service mới phải có owner, môi trường, mức quan trọng, đầu mối cảnh báo và đường dẫn runbook tối thiểu.
6. **Kiểm chứng sau deploy:** lưu trạng thái triển khai, version và inventory; phát hiện chênh lệch với topology dự kiến.

Chính sách có thể yêu cầu **bằng chứng review** cho thay đổi nhạy cảm thay vì tự động chặn mọi khác biệt. Ví dụ, thêm một loại quan hệ nghiệp vụ mới khó được phát hiện chính xác chỉ bằng việc đếm dòng thay đổi của IaC.

### 7.2. Ví dụ kiểm tra bằng một bảng ánh xạ

Giả sử nhóm duy trì danh mục dịch vụ ở dạng khai báo:

~~~yaml
services:
  - id: booking-api
    owner: booking-team
    environments: [staging, production]
    source: services/booking
    deploy_manifest: infrastructure/compute/booking
    diagram_node: BOOK
    runtime_name: booking-api
    data_classification: internal
    runbook: docs/operations/booking.md

  - id: notification-worker
    owner: communications-team
    environments: [production]
    source: services/notification
    deploy_manifest: infrastructure/compute/notification
    diagram_node: NOTIFY
    runtime_name: notification-worker
    data_classification: internal
    runbook: docs/operations/notification.md
~~~

Từ cùng danh mục này, pipeline **có thể** kiểm tra mỗi ID khai báo tham chiếu tới một node trên sơ đồ và một tài nguyên/runtime phù hợp với môi trường. Ví dụ logic kiểm tra:

~~~text
for each service in catalog:
    assert service.owner is assigned
    assert service.deploy_manifest exists
    assert service.diagram_node exists in logical diagram
    assert service.runbook exists
    if service is deployed to production:
        assert observed_runtime_contains(service.runtime_name)

for each observed production service:
    if not exists_in_catalog(service) and not has_approved_exception:
        report_architecture_drift(service)
~~~

Đây là **pseudocode minh họa**, không phải script có thể chạy trực tiếp. Tên runtime cần ánh xạ rõ theo môi trường và hệ thống đang dùng; một thành phần logical có thể triển khai thành nhiều workload. CI nên báo khác biệt và bằng chứng, còn quyết định tự động chặn hay tạo cảnh báo tùy mức nghiêm trọng.

### 7.3. Kiểm tra bằng API cloud và trạng thái runtime

Một tác vụ reconciliation có thể lấy inventory theo tài khoản/project và region rồi chuẩn hóa các thuộc tính bền vững:

- Resource type, ID, owner, environment và nhãn quản lý.
- Region/zone, subnet/VPC/VNet, public endpoint, route và security policy.
- Dịch vụ compute cùng version/image và đối tượng triển khai.
- Database, replication/failover, backup policy và encryption configuration.
- Messaging topics/subscriptions và endpoint bên thứ ba đã khai báo.

Đối chiếu các trường trên với IaC state/plan, service catalog và sơ đồ kiến trúc. Hãy tách **tài nguyên phát hiện nhưng chưa khai báo**, **tài nguyên dự kiến nhưng không tồn tại**, **cấu hình khác kỳ vọng** và **đường phụ thuộc bất ngờ** thành các loại drift khác nhau. Hệ thống inventory không tự chứng minh luồng nghiệp vụ hoạt động đúng; telemetry và thử nghiệm thật vẫn cần thiết.

### 7.4. Cảnh giác với giới hạn quan sát

- Trace chỉ hiển thị các request được instrument và sample; một luồng ít xảy ra có thể vắng mặt trong cửa sổ thu thập.
- IaC không phản ánh mọi cấu hình SaaS, cấu hình tạm thời hoặc can thiệp trực tiếp ngoài công cụ.
- Inventory cloud có thể thiếu kết nối ra đối tác hoặc dịch vụ được điều khiển ở tài khoản khác.
- Feature flag có thể khiến luồng đang chạy khác luồng mặc định dù binary và manifest giống nhau.
- Diagram generator có thể đưa nhiều tài nguyên hạ tầng chi tiết vào hình nhưng bỏ qua ngữ nghĩa nghiệp vụ.

Kết quả kiểm tra nên ghi **phạm vi bao phủ, mốc thời gian và mức tin cậy**, tránh nhãn “100% synchronized” khi chưa thể quan sát toàn bộ hệ thống.

## 8. Quản lý thay đổi kiến trúc khẩn cấp

Trong sự cố production, nhóm on-call có thể cần mở route tạm, tắt tính năng, tăng quota hoặc chuyển traffic để phục hồi. Quy trình tài liệu phải hỗ trợ tình huống khẩn cấp mà vẫn bảo toàn khả năng điều tra và hoàn nguyên.

Một luồng tối thiểu:

1. **Ghi nhận thao tác:** thời gian, người thực hiện, incident ID, mục đích và đối tượng bị thay đổi; lưu log/audit nếu công cụ hỗ trợ.
2. **Đánh giá rủi ro tức thời:** quyền public, dữ liệu nhạy cảm, thay đổi vùng, chi phí, điểm lỗi đơn và giới hạn ảnh hưởng.
3. **Khôi phục dịch vụ:** thay đổi trong phạm vi quyền được ủy quyền; theo dõi tín hiệu nghiệp vụ, lỗi và bảo mật.
4. **Đối chiếu sau sự cố:** ghi khác biệt giữa trạng thái runtime và IaC/tài liệu; quyết định hợp thức hóa thay đổi hay rollback.
5. **Cập nhật qua PR/ADR:** đưa trạng thái được chấp nhận vào nguồn cấu hình có quản lý, sửa sơ đồ và runbook, đóng ngoại lệ có bằng chứng.
6. **Rút kinh nghiệm:** kiểm tra vì sao tài liệu không đủ hoặc runbook không đáp ứng; bổ sung cảnh báo và tự động hóa cần thiết.

**Đừng tự động “reconcile” bằng cách hoàn nguyên mọi thay đổi thủ công đang cứu dịch vụ** khi chưa hiểu trạng thái incident. Ngược lại, một thay đổi khẩn cấp mở public access cũng không thể trở thành ngoại lệ vĩnh viễn vì “hệ thống đã ổn”. Cần hạn xử lý, owner và phê duyệt chấp nhận rủi ro phù hợp.

## 9. Ví dụ: thêm database replica và đổi luồng đọc trong hệ thống đặt chỗ

Giả sử một sản phẩm đặt chỗ có Booking API và database chính. Khi nhu cầu xem lịch sử đặt chỗ tăng, nhóm đề xuất thêm **read replica** để giảm tải truy vấn đọc. Yêu cầu nghiệp vụ là giữ thời gian phản hồi ổn định mà không làm sai dữ liệu xác nhận giao dịch.

### 9.1. Trước thay đổi

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> API[Booking API]
    API --> DB[(Primary DB)]
~~~

Tại thời điểm này, sơ đồ logic và sơ đồ deployment có thể dùng một primary DB. Nhóm cần biết các truy vấn nào đòi hỏi đọc ngay sau ghi, các báo cáo nào chịu được dữ liệu trễ và tình trạng HA/backup thực tế của primary.

### 9.2. Quyết định và thay đổi có kiểm soát

Nhóm tạo ADR: “Dùng read replica cho truy vấn lịch sử chấp nhận độ trễ; các thao tác kiểm tra booking mới tạo tiếp tục đọc từ primary”. Các thành phần thay đổi gồm:

- **Kiến trúc logic:** Booking API phân loại truy vấn cần strong/read-your-writes consistency so với danh sách lịch sử có thể chậm cập nhật.
- **Hạ tầng:** thêm replica trong region/zone đáp ứng yêu cầu; cấu hình connection, secret, monitoring, quota và cảnh báo replication lag.
- **Ứng dụng:** đưa các truy vấn phù hợp sang endpoint replica, có fallback được thiết kế rõ và giới hạn tải.
- **Tài liệu:** cập nhật sơ đồ container/deployment, ADR, data-flow, runbook và dashboard.
- **Kiểm thử:** xác minh truy vấn mới sau ghi vẫn nhất quán; kiểm tra trường hợp replica lag hoặc không sẵn sàng; xem cách vận hành khi primary lỗi.

**Sơ đồ dự kiến sau thay đổi:**

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> API[Booking API]
    API -->|Ghi + đọc yêu cầu dữ liệu mới nhất| PRI[(Primary DB)]
    PRI -->|Replication| REP[(Read replica)]
    API -->|Đọc lịch sử chấp nhận trễ| REP
    REP --> LAG[Metric: replication lag]
~~~

### 9.3. Lưu lại bằng chứng theo thời điểm

| Mốc | Tài liệu/bằng chứng | Người chịu trách nhiệm |
|---|---|---|
| Trước deploy | ADR Accepted, sơ đồ Proposed, IaC plan, kiểm thử tương thích ứng dụng | Architect, Booking lead, Platform |
| Sau staging | Replica tồn tại, health/lag đo được, truy vấn đúng route, tình huống lỗi đã thử | Booking + SRE |
| Sau production | Deployment version, inventory replica, log/trace luồng đọc và dashboard replication lag | SRE/Platform |
| Khi kiểm chứng | Sơ đồ đánh dấu Verified for production với mốc và đường dẫn bằng chứng | Owner tài liệu |
| Sau một đợt vận hành | Review chi phí, hiệu năng, số liệu lag, rủi ro còn lại; ADR được giữ hay thay thế | Owner hệ thống |

Nếu replica đã tạo nhưng ứng dụng chưa chuyển lưu lượng, sơ đồ “deployed resources” có thể hiển thị replica, còn sơ đồ “observed read path” phải cho thấy ứng dụng vẫn đọc primary. Cách phân biệt này tránh việc một hình cố tình hoặc vô ý khẳng định tính năng chưa sử dụng.

### 9.4. Tình huống drift cần phát hiện

**Tình huống A:** một kỹ sư chuyển các truy vấn yêu cầu dữ liệu tức thời sang replica, làm người dùng không thấy booking vừa xác nhận. CI test của nghiệp vụ và trace có thể bắt được, dù IaC không đổi.

**Tình huống B:** replication lag tăng cao sau sự cố. Cấu hình hạ tầng vẫn khớp sơ đồ, nhưng cam kết của read model không còn đạt; dashboard/alert cần đưa người vận hành tới runbook và chế độ giảm chức năng.

**Tình huống C:** một replica mới được tạo ở region khác mà chưa đánh giá vị trí dữ liệu, backup và luồng truy cập. Inventory diff và policy check phải phát hiện; nếu có dữ liệu bị hạn chế di chuyển, cần đánh giá tuân thủ trước khi công nhận kiến trúc mới.

## 10. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi kiểm chứng | Ví dụ bằng chứng/tác động |
|---|---|---|
| **Operational Excellence** | Owner và runbook có đúng với môi trường production? Thay đổi có liên kết PR, ADR và deployment? | Incident drill, lịch sử change, last verified, coverage của service catalog |
| **Security** | Sơ đồ trust boundary và dữ liệu có phản ánh public endpoint, IAM và nơi xử lý thực? | Security group scan, policy report, access log, data-flow review |
| **Reliability** | Sơ đồ thể hiện failure domain đúng? HA/DR, backup/failover có được thử? | Test mất zone, kết quả restore, RTO/RPO đo thực tế và dependency map |
| **Performance Efficiency** | Sơ đồ có giúp tìm đường gọi dài, nút cổ chai hoặc cross-region hop? | Trace latency, throughput, replication lag, load test |
| **Cost Optimization** | Tài nguyên có owner; thay đổi topology đã tính compute, storage, network và log? | Inventory có nhãn, cost allocation, PR cost estimate và báo cáo tài nguyên nhàn rỗi |
| **Sustainability** | Có loại bỏ resource hoặc bản sao không còn dùng? | Tài nguyên idle, utilization, retention hợp lý, mức nhân bản phù hợp nhu cầu |

Một sơ đồ đồng bộ giúp **đánh giá** các trụ cột, nhưng không tự tạo độ tin cậy hay tuân thủ. Kết quả phải được chứng minh bằng kiểm thử, audit, số liệu production và quyền quyết định rõ ràng.

### 10.1. Mức độ chi tiết và chi phí duy trì

Vẽ từng pod, địa chỉ IP thay đổi liên tục hay mọi message queue tạm thời khiến sơ đồ nhanh lỗi thời. Ngược lại, chỉ ghi “Frontend → Backend → Database” lại thiếu dữ liệu để đánh giá HA, IAM hoặc data residency. Chọn chi tiết theo câu hỏi thực tế:

- **Sơ đồ logic** thể hiện ranh giới trách nhiệm, hợp đồng và phụ thuộc bền vững.
- **Sơ đồ deployment** thể hiện môi trường, region/zone, fault boundary và các tài nguyên có ý nghĩa vận hành.
- **Dashboard/inventory** đảm nhận số lượng instance hiện tại, pod, IP và trạng thái theo thời gian.
- **Data-flow và trust boundary** thể hiện nơi dữ liệu nhạy cảm đi qua, quyền truy cập và xử lý.

Mục tiêu là giảm **chi phí giữ tài liệu đúng** nhưng vẫn đủ độ chính xác cho quyết định kiến trúc và xử lý sự cố.

## 11. Đo chất lượng đồng bộ

Chỉ số “số lượng sơ đồ đã viết” không phản ánh độ tin cậy. Nên đo một số chỉ số có thể kiểm chứng:

| Chỉ số | Cách hiểu | Hạn chế cần tránh |
|---|---|---|
| **Coverage** | Tỷ lệ dịch vụ/tài nguyên quan trọng có owner và liên kết tài liệu trong phạm vi kiểm tra | Không đếm tài nguyên tự động scale như dịch vụ mới |
| **Freshness** | Thời gian từ lần thay đổi production có ảnh hưởng đến lần cập nhật/kiểm chứng tài liệu | “Mới sửa file” không đồng nghĩa nội dung chính xác |
| **Drift count và mức nghiêm trọng** | Số khác biệt mở, chia theo bảo mật/độ tin cậy/hợp đồng/hiển thị | Tránh so tổng số khi phạm vi quét thay đổi |
| **Time to reconcile** | Thời gian từ phát hiện đến xử lý hoặc chấp thuận khác biệt với owner rõ | Không âm thầm đóng bằng cách xóa cảnh báo |
| **Post-deploy verification rate** | Tỷ lệ lần triển khai có xác minh cấu hình/runtime sau deploy | Không coi CI thành công là đã kiểm thử behavior production |
| **Runbook exercise success** | Kết quả diễn tập khôi phục/sự cố theo phạm vi đã định | Bài kiểm tra “mở được link” không chứng minh runbook dùng được |

**Ví dụ về cách tính**, khi một dự án có 20 dịch vụ quan trọng và 17 dịch vụ có đủ owner + runbook + sơ đồ đã xác minh theo tiêu chí:

~~~text
Documentation coverage = 17 / 20 = 85%
~~~

Đây chỉ là minh họa công thức. Cần ghi rõ mẫu số, điều kiện “đủ” và ngày kiểm tra. Không đặt một ngưỡng duy nhất cho tất cả dự án mà không cân nhắc mức nghiêm trọng và khả năng quan sát.

## 12. Checklist thực hành

### 12.1. Trước khi duyệt thay đổi kiến trúc

- [ ] Mục tiêu nghiệp vụ, SLO, RTO/RPO, vùng dữ liệu và rủi ro chính được xác định.
- [ ] Có owner cho dịch vụ, tài liệu, sơ đồ, ADR và các khâu vận hành liên quan.
- [ ] Sơ đồ ghi rõ môi trường, phạm vi, ngày/phiên bản và trạng thái proposed hay deployed.
- [ ] Đã kiểm tra các thành phần mới/đã xóa và đường giao tiếp, IAM, mạng, vùng, dữ liệu, dependency.
- [ ] Thay đổi đáng kể có ADR ghi lựa chọn, đánh đổi và hệ quả.
- [ ] IaC/API schema/deployment manifest có review và liên kết được tới các tài liệu chịu tác động.
- [ ] Runbook, DR, monitoring, chi phí và kiểm tra bảo mật đã được xét theo phạm vi thay đổi.

### 12.2. Sau deploy và trong vận hành

- [ ] Có release record, commit/version và môi trường tương ứng với cấu hình đang chạy.
- [ ] Inventory và cấu hình thực đã được so sánh với IaC/manifest và sơ đồ.
- [ ] Các liên kết và phụ thuộc quan trọng được xác nhận bằng telemetry hoặc thử nghiệm.
- [ ] Đã kiểm tra những tuyên bố về HA, backup, access và data flow có bằng chứng phù hợp.
- [ ] Sai lệch được ghi nhận theo mức độ, có owner, ngày phát hiện và cách xử lý.
- [ ] Runbook đã được diễn tập theo tần suất dựa trên mức rủi ro; sửa lại nếu thao tác không còn đúng.
- [ ] Thay đổi khẩn cấp được đối chiếu và đưa vào quy trình quản lý phiên bản sau sự cố.
- [ ] Tài liệu/ADR cũ có trạng thái superseded hoặc archived rõ ràng, tránh người đọc nhầm với kiến trúc hiện tại.

## 13. Bài tập áp dụng

### Bài tập A — Hệ thống chạy khác sơ đồ

Sơ đồ production vẽ hai availability zone và database HA. Trong inventory, nhóm phát hiện tất cả compute ở một zone và database chỉ có một instance không bật dự phòng.

**Câu hỏi:** Có thể sửa tên các node trong sơ đồ rồi coi như hoàn thành không?

**Gợi ý:** Chưa đủ. Phải kiểm tra yêu cầu chịu lỗi zone đã được duyệt, xác định vì sao triển khai sai lệch, đánh giá rủi ro hiện tại và quyết định sửa hạ tầng hay chấp thuận thay đổi thiết kế bằng ADR. Cập nhật sơ đồ theo trạng thái hiện hữu, lưu bằng chứng và diễn tập chịu lỗi trước khi khẳng định đạt HA.

### Bài tập B — Thêm webhook của đối tác

Nhóm Payment thêm webhook callback qua Internet vào một endpoint mới. PR cập nhật code nhưng không đổi IaC vì endpoint đã có sẵn trên gateway.

**Câu hỏi:** Cần cập nhật tài liệu nào và kiểm tra gì?

**Gợi ý:** Cập nhật context/container hoặc sequence cho luồng thanh toán, sơ đồ trust boundary/data-flow và contract của webhook. Kiểm tra xác thực chữ ký, replay, idempotency, quyền truy cập, xử lý payload nhạy cảm, log, timeout, retry, rate limit và owner/cảnh báo. Không dùng chỉ điều kiện “IaC có thay đổi” làm trigger cập nhật tài liệu.

### Bài tập C — Thao tác cứu hộ production

Trong sự cố, on-call đổi route để chuyển 100% traffic sang cụm dự phòng. Sau đó hệ thống ổn định nhưng repository vẫn khai báo route cũ.

**Câu hỏi:** Làm sao tránh GitOps/IaC vô tình đảo ngược trạng thái đang cứu hệ thống?

**Gợi ý:** Ghi incident và thay đổi khẩn cấp, kiểm tra reconcile policy trước khi khôi phục tự động, tạo PR hợp thức hóa trạng thái cần giữ hoặc lập kế hoạch rollback có kiểm soát; xác minh runbook và sơ đồ theo trạng thái production. Đưa ngoại lệ vào danh sách có owner, hạn xử lý và điều kiện đóng.

### Bài tập D — Sơ đồ sinh tự động

Một công cụ quét cloud và sinh hình với 300 resource. Nó hiển thị đủ các máy ảo, nhưng không có thông tin ai sở hữu dịch vụ, dữ liệu nào là nhạy cảm hay API nào gọi API nào.

**Câu hỏi:** Có nên coi đây là tài liệu kiến trúc hoàn chỉnh?

**Gợi ý:** Không. Có thể sử dụng hình/inventory làm bằng chứng deployed topology, nhưng cần bổ sung logical view, trust/data-flow, owner, ADR, dependency runtime, SLO và runbook. Chọn mức trừu tượng phù hợp để hỗ trợ review thay vì nhồi mọi tài nguyên vào một hình.

## 14. Kết luận thực hành

Giữ tài liệu và sơ đồ đồng bộ với cloud không phải hoạt động “vẽ lại sau mỗi sprint”. Đó là một vòng kiểm soát liên tục:

**Yêu cầu → Quyết định → Sơ đồ → Cấu hình có quản lý → Triển khai → Kiểm chứng trạng thái thực → Ghi nhận sai lệch → Cập nhật.**

Sơ đồ cần nói rõ **đang mô tả điều gì, ở môi trường nào, vào thời điểm nào và ai xác minh**. IaC giúp kiểm soát hạ tầng mong muốn; inventory phản ánh tài nguyên đang tồn tại; telemetry và diễn tập cho thấy hệ thống thực sự hoạt động thế nào; ADR lưu lại lý do và đánh đổi. Khi các nguồn này liên kết với nhau và có quy trình xử lý khác biệt, nhóm mới có thể dùng tài liệu để đánh giá tính đúng đắn của kiến trúc, ứng phó sự cố và cải tiến hệ thống theo Well-Architected.
