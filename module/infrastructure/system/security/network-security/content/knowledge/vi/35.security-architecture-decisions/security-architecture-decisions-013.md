# Architecture Decision Record cho Network Security

## 1. Vì sao quyết định kiến trúc bảo mật cần được ghi lại?

Khi thiết kế một mạng an toàn, nhóm kỹ thuật phải đưa ra những quyết định có tác động dài hạn: đặt firewall ở đâu, chia vùng tin cậy thế nào, quản trị VPN/ZTNA ra sao, có kiểm soát lưu lượng east–west ở từng workload không, DNS được bảo vệ ở lớp nào, hay thu thập nhật ký và phát hiện xâm nhập tại những điểm nào. Một sơ đồ mạng có thể cho thấy **đã triển khai gì**, nhưng thường không giải thích **vì sao chọn phương án đó, phương án nào đã bị loại và điều kiện nào buộc phải xem xét lại**.

**Architecture Decision Record (ADR)** là một bản ghi ngắn, có cấu trúc, lưu lại **một quyết định kiến trúc quan trọng** tại thời điểm đưa ra: bối cảnh, động lực, các lựa chọn, kết luận, đánh đổi, hệ quả và cách kiểm chứng. ADR không phải là tài liệu thiết kế chi tiết cho mọi interface, cũng không thay thế một chính sách bảo mật, sơ đồ mạng hoặc kế hoạch thay đổi. ADR giúp những tài liệu và hoạt động đó nhất quán với **lý do kiến trúc** đã được chấp thuận.

Bài học thuộc chương **Quyết định kiến trúc bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Việc ghi ADR đặc biệt hữu ích khi lựa chọn kiến trúc phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, mạng đám mây và cơ chế giám sát. Mỗi quyết định ảnh hưởng đồng thời đến **khả năng ngăn chặn, tính sẵn sàng, khả năng quan sát, chi phí và cách vận hành**.

Sau bài học, người học có thể:

1. Phân biệt ADR với threat model, tài liệu thiết kế chi tiết, chính sách bảo mật và change request.
2. Xác định quyết định nào đủ quan trọng để tạo ADR và phạm vi của một ADR tốt.
3. Viết bối cảnh, giả định, ràng buộc, tiêu chí đánh giá và phương án thay thế một cách kiểm chứng được.
4. So sánh đánh đổi giữa các mô hình kiểm soát mạng theo đặc thù hệ thống, thay vì chỉ dựa trên sở thích công nghệ.
5. Viết một ADR hoàn chỉnh về phân đoạn mạng hybrid, có tiêu chí nghiệm thu và phương án rollback.
6. Duy trì lịch sử quyết định, xử lý khi giả định thay đổi và liên kết ADR với triển khai, kiểm thử và vận hành.

> **Nguyên tắc:** ADR cần giải thích **vì sao và trong điều kiện nào quyết định là phù hợp**, đồng thời chỉ rõ **cách chứng minh kết quả**. Câu “chọn giải pháp X vì bảo mật hơn” chưa phải một lập luận kiến trúc đủ tốt.

## 2. Khi nào cần tạo ADR?

### 2.1. Những tình huống nên có ADR

Một quyết định đáng ghi ADR khi nó tác động nhiều hệ thống, khó đảo ngược, cần phối hợp nhiều nhóm hoặc tạo đánh đổi đáng kể giữa bảo mật và vận hành.

| Quyết định | Câu hỏi kiến trúc | Vì sao cần ADR |
| --- | --- | --- |
| **Phân đoạn mạng** | Dùng firewall tập trung, distributed firewall hay kết hợp? | Ảnh hưởng đường đi east–west, vận hành policy, độ trễ và khả năng kiểm chứng |
| **Quản trị truy cập từ xa** | Tiếp tục VPN theo network access hay chuyển dần sang ZTNA theo ứng dụng? | Thay đổi ranh giới tin cậy, xác thực, thiết bị và trải nghiệm người dùng |
| **Network management plane** | Tách VRF/OOB và bastion theo cấu trúc nào? | Quyết định khả năng quản trị trong sự cố và bề mặt tấn công |
| **IDS/IPS/NDR** | Quan sát ở biên, giữa các vùng hay tại workload? | Đánh đổi mức bao phủ, dữ liệu mã hóa, tài nguyên giám sát và chi phí |
| **DNS security** | Dùng resolver nội bộ tập trung, phân tán hay managed service? | Quyết định kiểm soát truy vấn, độ sẵn sàng, split-horizon và log |
| **Cloud network security** | Security group, network ACL, cloud firewall và policy-as-code phối hợp ra sao? | Liên quan chia sẻ trách nhiệm, môi trường động và tính nhất quán chính sách |
| **Kết nối đối tác** | Private interconnect, VPN hoặc proxy ứng dụng được phép cho luồng nào? | Tác động phạm vi tin cậy, xác thực, dữ liệu và điều khoản với bên thứ ba |

Không cần một ADR cho **mỗi lần thêm một rule firewall** đã nằm trong kiến trúc được phê duyệt. Những thay đổi vận hành thông thường có thể dùng change ticket, rule request hoặc runbook. Tuy vậy, nếu một ngoại lệ tạo **nguyên tắc mới** (ví dụ cho phép một vùng kém tin cậy đi thẳng tới cơ sở dữ liệu) thì có thể cần ADR hoặc cập nhật quyết định kiến trúc liên quan.

### 2.2. Một ADR nên giải quyết một quyết định chính

Ví dụ, quyết định “chọn mô hình phân đoạn traffic giữa on-premises và cloud” có thể là một ADR. “Thay toàn bộ VPN, DNS, firewall, SIEM, Wi-Fi và chính sách IAM” là nhiều quyết định khác nhau, nên tách thành các ADR liên kết với nhau. Nếu một quyết định phụ thuộc quyết định khác, hãy ghi rõ *dependency* thay vì dồn mọi phương án vào một tài liệu quá lớn.

Đặt tên ADR theo vấn đề hoặc lựa chọn rõ ràng, ví dụ **“Dùng phân đoạn workload cho lưu lượng east–west trong hybrid network”**, thay vì tên chung chung như “Nâng cấp bảo mật mạng”.

## 3. Cấu trúc tối thiểu của một ADR

Các tổ chức có thể dùng các mẫu khác nhau. Một ADR cho network security nên có những trường sau:

| Phần | Nội dung | Câu hỏi kiểm chứng |
| --- | --- | --- |
| **ID, title, status, date** | Mã ổn định, tên quyết định, trạng thái, thời điểm | Đây là quyết định nào và còn hiệu lực không? |
| **Owners/decision makers** | Người đề xuất, chủ hệ thống, nhóm phê duyệt | Ai chịu trách nhiệm đánh giá và thực thi? |
| **Context/problem** | Kiến trúc hiện tại, rủi ro, lý do thay đổi | Vấn đề thật là gì và ranh giới ở đâu? |
| **Decision drivers** | Yêu cầu bảo mật, vận hành, tuân thủ, chi phí, performance | Tiêu chí nào là bắt buộc, tiêu chí nào là đánh đổi? |
| **Assumptions/constraints** | Giả định, phụ thuộc, hạn chế của sản phẩm, mạng và tổ chức | Điều gì có thể khiến lựa chọn không còn đúng? |
| **Options considered** | Các phương án khả thi, bao gồm giữ nguyên hiện trạng khi phù hợp | Phương án nào bị loại và vì sao? |
| **Decision** | Lựa chọn và phạm vi áp dụng, nguyên tắc cần giữ | Chính xác điều gì được chấp thuận? |
| **Consequences/trade-offs** | Lợi ích, chi phí, rủi ro tồn dư, ảnh hưởng vận hành | Tác động tích cực và bất lợi nào được chấp nhận? |
| **Validation/acceptance** | Test dương/âm, telemetry, SLO/SLA, bằng chứng | Làm sao biết kiến trúc hoạt động như mong đợi? |
| **Rollout/rollback** | Giai đoạn chuyển đổi, điểm dừng, phương án phục hồi | Có thể triển khai và quay lui an toàn không? |
| **Revisit triggers** | Điều kiện xem xét lại, sự kiện thay đổi giả định | Khi nào phải ra quyết định mới? |
| **References/links** | Threat model, diagram, risk register, ticket, bằng chứng | Có thể truy vết các căn cứ không? |

Các trạng thái phổ biến: **Proposed** (đang đề xuất), **Accepted** (đã chấp thuận), **Rejected** (đã cân nhắc nhưng không chọn), **Deprecated** (không còn được khuyến nghị) và **Superseded** (đã được ADR mới thay thế). Nhiều nhóm còn dùng **Draft**, **Under review** hoặc **Implemented**; cần công bố định nghĩa nội bộ. **Accepted không có nghĩa đã triển khai hoàn toàn**, nên theo dõi tiến độ triển khai trong change/project tracker riêng.

Không viết lại lý do lịch sử của ADR đã chấp thuận chỉ để phù hợp với thực tế mới. Khi hoàn cảnh thay đổi đáng kể, tạo **ADR mới thay thế**, liên kết hai chiều, ghi rõ quyết định cũ áp dụng trong điều kiện nào và thời điểm nào được thay thế. Có thể chỉnh lỗi chính tả hoặc liên kết hỏng theo quy trình tài liệu, nhưng cần giữ dấu vết của thay đổi có ý nghĩa.

## 4. Thu thập bối cảnh và chứng cứ trước khi quyết định

Trong network security, một phương án nhìn có vẻ hợp lý trên sơ đồ tổng thể có thể thất bại khi xét **đường đi thực**, **phiên dài**, **traffic nội bộ cùng subnet**, **IPv6**, **NAT**, **VPN split tunnel** hoặc **quản trị khi mất kết nối**. Vì vậy bối cảnh ADR phải dựa trên thông tin đủ để hình dung ranh giới tin cậy và phụ thuộc dịch vụ.

### 4.1. Những dữ liệu đầu vào nên có

1. **Asset inventory:** router, switch, firewall, gateway, AP, VPN, DNS, workload, tài khoản máy, vùng mạng, nhà cung cấp và phiên bản firmware/OS khi liên quan.
2. **Sơ đồ mạng và luồng dữ liệu:** site, VLAN/VRF, subnet, route, interconnect, cloud VPC/VNet, container overlay, đường quản trị và đường dự phòng.
3. **Ma trận kết nối:** nguồn–đích–giao thức/cổng–ứng dụng–danh tính–chủ dịch vụ–mức độ cần thiết; phân biệt ingress, egress, east–west và control/management plane.
4. **Threat model:** tài sản cần bảo vệ, điểm tin cậy, các giả thuyết đe dọa, đường có thể dẫn tới ảnh hưởng, kiểm soát hiện hữu và rủi ro tồn dư.
5. **Hiện trạng phòng vệ:** firewall/ACL, IDS/IPS/NDR, VPN/ZTNA, xác thực, DNS, Wi-Fi isolation, bảo vệ cloud, SIEM, log và khả năng ứng phó.
6. **Yêu cầu phi chức năng:** throughput, latency, availability, failover, RTO/RPO của dịch vụ liên quan, năng lực nhóm vận hành và giới hạn ngân sách.
7. **Ràng buộc:** thiết bị không hỗ trợ tính năng, thời gian bảo trì, phụ thuộc nhà cung cấp, yêu cầu dữ liệu, hợp đồng và kế hoạch chuyển đổi.

**RTO/RPO** có thể là điều kiện thiết kế phục hồi cho dịch vụ phụ thuộc; không nên dùng chúng như số đo trực tiếp của hiệu năng firewall. **Threat model** mô tả điều kiện, ranh giới và đường đe dọa, còn **ADR** lựa chọn cách xử lý một vấn đề kiến trúc dưới những điều kiện đó.

### 4.2. Sơ đồ luồng và ranh giới tin cậy

Ví dụ một môi trường hybrid:

~~~mermaid
flowchart LR
    User["Vùng USER / VPN"] -->|"HTTPS cần thiết"| App["Vùng APP"]
    App -->|"DB traffic cần thiết"| Db["Vùng DATA"]
    User -.->|"Không được phép trực tiếp"| Db
    App -->|"Kết nối hybrid"| Cloud["Cloud workloads"]
    Admin["Bastion / MGMT"] -->|"Quản trị giới hạn"| App
    Admin -->|"Quản trị giới hạn"| Cloud
    Fw["Firewall / Security Groups"] --- App
    Fw --- Cloud
    Logs["Log + SIEM / NDR"] --- Fw
~~~

Sơ đồ là ví dụ về **ý định truy cập**, chưa đại diện đường đi hay điểm kiểm soát đầy đủ. ADR phải xác định ai **thực thi** chặn USER → DATA: firewall vùng, host firewall, cloud security group hoặc phối hợp nhiều lớp? Nếu hai workload cùng subnet không đi qua firewall tập trung, một đường cấm trên sơ đồ có thể vẫn thông nếu thiếu chính sách ở workload.

### 4.3. Ghi nguồn và chất lượng chứng cứ

Mỗi khẳng định có tác động tới quyết định nên liên kết nguồn: kết quả inventory có thời điểm, cấu hình đang chạy, firewall/flow logs, đo tải, kết quả thử nghiệm, threat model, advisory, release notes, SLA hoặc ý kiến chủ dịch vụ. Phân biệt rõ:

- **Fact:** dữ liệu đã quan sát và có bằng chứng, ví dụ “đường east–west giữa hai VM cùng subnet không đi qua firewall biên trong topology hiện tại”.
- **Assumption:** giả định chưa xác minh hoặc chỉ đúng trong thời điểm hiện tại, ví dụ “tất cả workload sắp tới đều được gắn tag zone chuẩn”.
- **Constraint:** giới hạn buộc phải tuân thủ, ví dụ “hệ thống kiểm soát phải duy trì hoạt động khi controller mất kết nối trong 30 phút”.
- **Decision:** lựa chọn được chấp thuận sau khi xem xét chứng cứ và đánh đổi.

Không ghi số liệu giả định dưới dạng số đo thực. Khi chưa đủ dữ liệu, nêu **unknown** và kế hoạch đo trước khi chấp thuận hoặc triển khai toàn bộ.

## 5. Viết các tiêu chí quyết định có thể kiểm chứng

Không thể so sánh phương án nếu tiêu chí chỉ là “an toàn”, “hiệu năng tốt” hoặc “dễ quản trị”. Cần chuyển thành những điều kiện cụ thể, có người xác nhận và phương pháp đo.

### 5.1. Phân biệt yêu cầu bắt buộc và tiêu chí đánh đổi

| Nhóm | Ví dụ điều kiện bắt buộc (gating constraint) | Ví dụ tiêu chí để so sánh |
| --- | --- | --- |
| **Phân đoạn** | Luồng USER → DATA trực tiếp bị chặn mặc định ở mọi đường được bao phủ | Dễ mô hình hóa và chứng minh chính sách east–west |
| **Danh tính** | Quản trị qua kênh xác thực, phân quyền, audit; chỉ tài khoản được duyệt có quyền thay đổi | Mức tích hợp IdP/MFA/service identity |
| **Phát hiện** | Có bản ghi cho các kết nối trọng yếu và sự kiện deny cần điều tra | Độ phủ telemetry, chi phí log, độ phức tạp correlation |
| **Sẵn sàng** | Không tạo single point of failure vượt mức chấp nhận; có đường cứu hộ | Mức độ failover, độ phụ thuộc controller/cloud |
| **Hiệu năng** | Đáp ứng SLO đã được chủ dịch vụ thống nhất trong điều kiện tải thiết kế | Độ trễ thêm, throughput, độ ổn định khi tải tăng |
| **Vận hành** | Có owner, rollback, quy trình cập nhật rule và xử lý ngoại lệ | Thời gian triển khai thay đổi, chất lượng policy-as-code |
| **Ngân sách** | Không vượt hạn mức đã phê duyệt khi tính toàn bộ chi phí | License, băng thông hairpin, telemetry, nhân lực và đào tạo |

Nếu một phương án không đạt **điều kiện bắt buộc**, không nên cho điểm cao ở tiêu chí khác để hợp thức hóa nó. Khi cần ngoại lệ, phải chỉ rõ rủi ro, người phê duyệt và biện pháp bù trừ.

### 5.2. Phương pháp so sánh phương án

Có thể lập **decision matrix** với đánh giá định tính hoặc điểm trọng số. Điểm số chỉ giúp minh bạch quan điểm, không tự thay thế phê duyệt kỹ thuật.

Ví dụ thang đánh giá định tính:

| Tiêu chí | Phương án A: Firewall tập trung | Phương án B: Distributed controls | Phương án C: Kết hợp |
| --- | --- | --- | --- |
| Bảo vệ traffic giữa workload cùng subnet | Cần đổi đường đi hoặc có host-level control | Có thể áp dụng tại workload nếu platform hỗ trợ | Có thể bảo vệ bằng lớp phân tán |
| Phụ thuộc đường hairpin qua trung tâm | Có thể cao | Thường thấp hơn trong east–west | Tùy luồng; thường tách luồng trọng yếu |
| Kiểm toán chính sách toàn cục | Tập trung nếu rulebase đầy đủ | Cần tổng hợp nhiều nơi | Cần policy inventory và reconciliation |
| Rủi ro cấu hình lệch giữa môi trường | Theo thiết bị/chính sách trung tâm | Theo workload/team/tag | Cần cơ chế thống nhất giữa hai lớp |
| Mức phức tạp triển khai | Có thể phải đổi route/topology | Cần inventory và automation chính xác | Cần vận hành hai lớp kiểm soát |
| Khả năng quan sát traffic mã hóa/east–west | Tùy đường thực tế đi qua sensor | Cần telemetry tại workload/vSwitch/cloud | Phải thiết kế telemetry nhiều điểm |
| Ràng buộc với nền tảng | Phụ thuộc thiết bị/capacity trung tâm | Phụ thuộc cloud/CNI/agent và policy API | Kết hợp giới hạn của cả hai |

Các nhận xét trên là **đánh đổi chung**, không phải benchmark nhà cung cấp. Để dùng làm quyết định thực, bổ sung số liệu đo, kiến trúc thực tế, chi phí triển khai và các điều kiện failover của từng lựa chọn.

Nếu dùng điểm có trọng số, nên ghi rõ **trọng số, thang điểm, căn cứ chấm, các tiêu chí không thể bù trừ**. Ví dụ:

\[
Score(option) = \sum_i w_i \cdot s_i,\qquad \sum_i w_i = 1
\]

Điểm là công cụ **hỗ trợ hội thoại**. Không chọn một phương án có điểm tổng cao nhưng vi phạm yêu cầu hard deny hoặc vượt rủi ro được chấp nhận.

## 6. Mẫu ADR Markdown có thể tái sử dụng

Mẫu dưới đây giữ quyết định trong một tệp có mã định danh ổn định. Những trường chưa có dữ liệu nên ghi **Chưa xác minh / cần quyết định**, không tự điền để bảng trông đầy đủ.

~~~markdown
# ADR-NS-XXX: [Tên quyết định kiến trúc]

- **Status:** Proposed | Accepted | Rejected | Deprecated | Superseded
- **Date:** YYYY-MM-DD
- **Owner:** [nhóm hoặc vai trò]
- **Decision makers:** [vai trò có thẩm quyền]
- **Scope:** [hệ thống, vùng mạng, môi trường áp dụng]
- **Related:** [threat model, ADR phụ thuộc, design, change ticket]

## Context and problem
[Kiến trúc hiện hành, vấn đề, tác động kinh doanh, chứng cứ.]

## Decision drivers
- Must-have: [yêu cầu bảo mật/sẵn sàng/tuân thủ không được vi phạm]
- Trade-off criteria: [độ trễ, chi phí, khả năng vận hành...]
- Assumptions: [giả định có thể bị bác bỏ]
- Constraints: [hạn chế công nghệ, nhân lực, thời gian, nhà cung cấp]

## Options considered
### Option A: [...]
- Ưu điểm: [...]
- Hạn chế/rủi ro: [...]
- Evidence: [...]
### Option B: [...]
...
### Option C: Giữ nguyên hiện trạng (nếu khả thi)
...

## Decision
[Chọn phương án; phạm vi, điều kiện và lý do chọn.]

## Consequences
- Positive: [...]
- Negative: [...]
- Residual risks / compensating controls: [...]
- Responsibilities and operational impact: [...]

## Validation and acceptance criteria
- Positive tests: [...]
- Negative tests: [...]
- Security telemetry and response tests: [...]
- Reliability/performance tests and thresholds: [...]
- Evidence owners: [...]

## Rollout and rollback
[Thứ tự triển khai, dependencies, ngưỡng dừng, cách quay về trạng thái an toàn.]

## Revisit triggers
[Sự kiện bắt buộc rà soát lại quyết định.]

## References
[Link tới bằng chứng, sơ đồ, risk register, approvals.]
~~~

Mẫu này có thể lưu trong Git để review bằng pull request hoặc trong hệ thống quản lý kiến trúc có version history. **Quyết định và phê duyệt** cần người có thẩm quyền thực hiện; việc merge văn bản vào repository không tự chứng minh mọi yêu cầu rủi ro đã được phê duyệt, trừ khi tổ chức đã định nghĩa quy trình như vậy.

## 7. ADR mẫu hoàn chỉnh: phân đoạn mạng hybrid

### 7.1. Bối cảnh giả lập và yêu cầu

Một doanh nghiệp có mạng nội bộ on-premises, ứng dụng được triển khai thêm trong cloud và kết nối riêng/VPN giữa hai môi trường. Hiện tại, firewall tập trung kiểm soát luồng giữa các VLAN lớn, nhưng một số workload cùng subnet hoặc cùng cloud security group có thể trao đổi trực tiếp. Nhóm an ninh muốn **default deny giữa nhóm ứng dụng** trong khi không làm gián đoạn các luồng nghiệp vụ hợp lệ.

**Lưu ý:** ADR tiếp theo là **ví dụ giả lập để học phương pháp**. Tên chủ sở hữu, trạng thái, thông số, phương án đã chọn đều là dữ liệu minh họa, không đại diện quyết định đang có hiệu lực của một doanh nghiệp cụ thể.

### 7.2. Bản ghi ADR-NS-014 (ví dụ)

**ADR-NS-014 — Kết hợp firewall vùng với chính sách phân đoạn tại workload cho mạng hybrid**

| Thuộc tính | Giá trị giả lập |
| --- | --- |
| **Status** | Accepted (giả định đã được chấp thuận trong kịch bản) |
| **Date** | 2026-11-28 |
| **Owner** | Network Security Architecture |
| **Decision makers** | Security Architect, Network Operations, Cloud Platform, Application Owner |
| **Scope** | Các luồng mới giữa vùng USER, APP và DATA tại on-premises và cloud |
| **Out of scope** | Thay toàn bộ giải pháp VPN, xử lý ứng dụng legacy chưa có inventory, hệ thống bên thứ ba |
| **Related inputs** | Threat model, flow matrix, topology snapshot, risk register, change plan của kịch bản |

#### Context — Vấn đề cần giải quyết

Trong sơ đồ hiện tại, USER chỉ cần truy cập APP qua HTTPS; APP được truy cập DATA qua cổng database xác định; người dùng không được kết nối trực tiếp tới DATA. Firewall vùng có thể bảo vệ những luồng đi qua nó, nhưng **không quan sát hoặc lọc mọi lưu lượng nội bộ cùng segment**. Nếu một máy APP bị xâm nhập, việc thiếu ranh giới giữa các workload có thể làm tăng mức độ lan truyền.

Giải pháp cần bảo vệ đồng thời:

- Luồng **north–south** tại biên mạng và luồng **east–west** giữa các nhóm workload.
- Các thiết bị mạng on-premises và VM/workload cloud, có thể tăng giảm số lượng theo thời gian.
- Đường quản trị từ bastion, VPN người dùng, DNS, NTP, IdP, nhật ký và các dịch vụ nền tảng.
- Khả năng xác minh chính sách được triển khai thật, bao gồm IPv6 nếu môi trường hỗ trợ.

#### Decision drivers — Yêu cầu

**Bắt buộc:**

1. Mặc định chặn kết nối giữa các vùng workload trừ những luồng được phê duyệt; kiểm tra cả chiều kết nối mới và điều kiện reply.
2. USER không thể truy cập trực tiếp DATA theo bất kỳ đường áp dụng nào trong phạm vi; APP chỉ được tới các đích/cổng database cần thiết.
3. Đường quản trị qua bastion/OOB có phân quyền và log; không tạo đường bypass ngoài danh mục.
4. Có kiểm thử dương/âm, flow logs hoặc tín hiệu phù hợp để điều tra rule hit và chẩn đoán khi chặn nhầm.
5. Có pilot, rollback, owner và cơ chế kiểm soát drift giữa cấu hình phê duyệt với runtime.

**Đánh đổi:** độ phức tạp vận hành, lượng rule, hiệu năng, năng lực hỗ trợ từ cloud/CNI/host firewall, chi phí telemetry, mức độ ảnh hưởng của mạng kết nối giữa các site và thời gian triển khai.

**Giả định cần xác minh trước rollout:** inventory liên kết workload với tag/zone đủ chính xác; các lớp kiểm soát phân tán được hỗ trợ ở tất cả môi trường trong phạm vi; policy controller và pipeline log đáp ứng năng lực quản trị; các đường failover được vẽ đúng.

#### Options considered — Những phương án đã cân nhắc

**A. Chỉ sử dụng firewall tập trung:** dễ đặt một điểm phê duyệt chính sách và tập trung log, nhưng các luồng cùng subnet hoặc trong cloud có thể không đi qua đó nếu không điều chỉnh topology. Chuyển traffic east–west qua một chỗ có thể tăng độ trễ, chi phí băng thông và phụ thuộc thiết bị trung tâm.

**B. Chỉ dùng kiểm soát phân tán tại workload:** bao phủ đường liên lạc sát host/VM/container và phù hợp scale động, nhưng yêu cầu quản trị lifecycle danh tính workload/tag, nhiều loại agent/CNI/cloud platform, log phân tán và khả năng vận hành khi control plane lỗi.

**C. Kết hợp firewall vùng và kiểm soát phân tán:** firewall vùng tiếp tục giữ vai trò phân tách zone và biên; tại các nhóm workload cần bảo vệ east–west, dùng security group, host firewall hoặc network policy theo khả năng nền tảng. Một policy inventory trung tâm quản lý **ý định luồng**, chuyển thành cấu hình phù hợp từng điểm thực thi, đồng thời có reconciliation và kiểm tra runtime.

**D. Giữ nguyên hiện trạng:** chi phí thay đổi thấp nhưng không xử lý khoảng trống phân đoạn đã xác định; không đáp ứng mục tiêu bảo mật trong phạm vi kịch bản.

#### Decision — Lựa chọn và giới hạn

**Chọn phương án C**, với điều kiện tất cả yêu cầu bắt buộc được chứng minh trong pilot.

1. Giữ firewall vùng cho các luồng giữa zone và kết nối biên; rà soát policy deny mặc định ở những ranh giới đã xác định.
2. Áp dụng kiểm soát phân tán cho APP/DATA và các workload cloud có nhu cầu cô lập east–west, dựa trên **nhóm workload/nhãn tài sản được quản lý** khi nền tảng hỗ trợ.
3. Mọi allow rule mới phải có **nguồn, đích, dịch vụ, lý do, owner, phê duyệt và bằng chứng test**. Không tạo rule `any/any` để sửa lỗi nhất thời.
4. Kết nối quản trị chỉ từ bastion hoặc hệ thống automation có quyền; log và flow metadata phải được gửi về hệ thống quan sát tin cậy.
5. Chia rollout theo ứng dụng/vùng mạng. Nhóm legacy chưa đủ điều kiện được ghi ngoại lệ có thời hạn và biện pháp bảo vệ riêng, không được mặc định là đã tuân thủ.

**Không kết luận policy đã đạt chỉ từ bản IaC được merge:** cần chứng minh rule đã được áp dụng trên firewall/host/cloud thực sự và không có đường đi không đi qua kiểm soát.

#### Consequences — Hệ quả của lựa chọn

| Tích cực | Bất lợi/chi phí và biện pháp xử lý |
| --- | --- |
| Cô lập được một số luồng east–west mà firewall tập trung không thấy | Tăng số điểm thực thi; dùng inventory, policy-as-code, kiểm soát drift và người chịu trách nhiệm |
| Giữ firewall biên và kiểm toán zone hiện có | Có thể phát sinh rule trùng/chồng lấn; cần mô hình nguồn–đích và test trên đường thực |
| Cho phép policy gần workload trong cloud | Tag/identity sai có thể cho phép quá rộng hoặc chặn nhầm; dùng admission/check, review và kiểm chứng |
| Có cơ hội cải thiện telemetry tại ranh giới ứng dụng | Log phân tán, định dạng khác nhau; cần normalized fields, thời gian, correlation ID và retention |
| Có thể chuyển đổi từng nhóm hệ thống | Giai đoạn chuyển đổi tạo trạng thái lai; cần kế hoạch test, thời hạn ngoại lệ và tiêu chí hoàn tất |

**Rủi ro tồn dư:** bất đối xứng định tuyến, đường bypass do overlay, IPv6 chưa được kiểm kê, policy không đồng nhất sau failover, traffic mã hóa không đủ thông tin ứng dụng, thiếu telemetry từ workload cũ và phụ thuộc vào hạ tầng quản lý danh tính. Mỗi rủi ro phải có owner, biện pháp giám sát và điểm xét lại.

#### Validation — Điều kiện nghiệm thu

Ma trận kiểm thử minh họa, dùng các địa chỉ riêng:

| ID | Nguồn → đích | Luồng | Kết quả mong đợi | Chứng cứ |
| --- | --- | --- | --- | --- |
| P1 | USER `10.10.10.21` → APP `10.20.20.10` | TCP/443 | **Allow** kèm xác thực ứng dụng | Host probe, ứng dụng, firewall logs |
| N1 | USER `10.10.10.21` → DATA `10.30.30.10` | TCP/5432 | **Deny** | Firewall/host deny, route và source xác minh |
| P2 | APP `10.20.20.10` → DATA `10.30.30.10` | TCP/5432 | **Allow** đúng service identity | Flow log, database auth, giao dịch mẫu |
| N2 | APP khác cùng subnet → DATA | TCP/5432 | **Deny** khi không có quyền | Workload policy hit + test |
| N3 | USER → APP | TCP/22 | **Deny** | Rule/flow evidence |
| P3 | Bastion được duyệt → điểm quản trị APP | SSH/HTTPS cần thiết | **Allow**, có audit | AAA, login và change log |
| N4 | USER/VPN thông thường → management interface | SSH/HTTPS | **Deny** | ACL/firewall, log xác minh |
| N5 | Workload không thuộc nhóm cho phép → workload cloud DATA | Dịch vụ DATA | **Deny** | Cloud/host policy, runtime test |

Các phép thử cần chạy từ **đúng nguồn và đúng đường đi**, gồm đường dự phòng và IPv6 khi dùng. Một kết quả timeout đơn lẻ không chứng minh firewall đã chặn; cần đối chiếu nơi thực thi và log. Với rule stateful, kiểm chứng **phiên mới sau thay đổi**, không chỉ phiên đã tồn tại.

Định nghĩa ngưỡng nghiệm thu hiệu năng và sẵn sàng dựa trên **baseline và SLO của dịch vụ**, đo tại tải đại diện và khi failover; chưa có số đo thì ghi **pending measurement**, không tự đặt số cụ thể. Xác nhận log ingress/egress và cảnh báo đã đến SIEM, nhưng không đồng nhất IDS alert với hành động chặn của firewall.

#### Rollout — Triển khai theo từng bước

~~~mermaid
flowchart TD
    A["Inventory, flow matrix, threat model"] --> B["Mẫu policy và phương án rollback"]
    B --> C["Pilot: một nhóm APP/DATA đã kiểm tra"]
    C --> D["Positive/negative tests + telemetry"]
    D --> E{"Đạt tiêu chí?"}
    E -->|"Không"| F["Dừng rollout, phục hồi cấu hình an toàn"]
    F --> B
    E -->|"Có"| G["Mở rộng theo zone/workload"]
    G --> H["Kiểm chứng HA, IPv6, drift và nghiệp vụ"]
    H --> I["Bàn giao vận hành và theo dõi ngoại lệ"]
~~~

Điều kiện **dừng/rollback** gồm mất luồng nghiệp vụ thiết yếu ngoài ngưỡng chấp nhận, xuất hiện kết nối trái policy, mất log tại các ranh giới quan trọng hoặc không còn đường quản trị cứu hộ. Quay lại cấu hình **đã biết an toàn**; không dùng mở rộng `allow any any` làm phương án rollback mặc định.

#### Revisit triggers — Khi nào phải ra quyết định lại?

- Thay đổi topology lớn: thêm cloud/region, kết nối đối tác, SD-WAN, service mesh hoặc mô hình identity mới.
- Nền tảng workload/firmware không còn hỗ trợ loại policy đã chọn hoặc có lỗ hổng ảnh hưởng kiến trúc.
- Số ngoại lệ và cấu hình lệch vượt khả năng quản trị; xuất hiện nhiều đường bypass thực tế.
- Hiệu năng, khả năng quan sát hoặc chi phí không đạt các tiêu chí đã chấp thuận sau rollout.
- Kết quả incident, red/purple team hoặc kiểm toán chứng minh giả định chính bị sai.

**Tham chiếu:** Threat model, service inventory, network flow matrix, topology as-built, rulebase snapshot, dashboard, test report, risk register và change records của kịch bản. Trong bài học không tạo URL hoặc mã ticket giả như bằng chứng đã tồn tại.

## 8. Liên kết ADR với triển khai và kiểm chứng thực tế

Một ADR được chấp thuận tạo ra **hướng kiến trúc**, nhưng triển khai cần các artefact cụ thể. Nên duy trì chuỗi truy vết:

~~~mermaid
flowchart LR
    T["Threat model / rủi ro"] --> A["ADR: quyết định"]
    A --> D["Design & policy matrix"]
    D --> I["IaC / rule change"]
    I --> R["Runtime state"]
    R --> V["Kiểm thử & quan sát"]
    V --> E["Evidence / acceptance"]
    E --> A
~~~

Ví dụ: ADR chọn distributed segmentation, design xác định vùng APP/DATA, policy matrix ghi TCP/5432 từ nhóm APP tới host DATA, change ticket triển khai security group/host firewall, test âm xác nhận một host ngoài nhóm **không** kết nối được. Nếu test âm thất bại, không đánh dấu ADR “đã triển khai thành công” chỉ vì thay đổi đã được merge.

### 8.1. Tách bốn trạng thái quan trọng

- **Decision accepted:** kiến trúc đã được người có thẩm quyền chấp thuận.
- **Implementation deployed:** cấu hình đã được phát hành/tạo trên các điểm thực thi.
- **Control verified:** các kiểm thử dương/âm, vận hành và log chứng minh kiểm soát hoạt động trong phạm vi.
- **Operations handed over:** có owner, runbook, dashboard, ngoại lệ, khả năng rollback và quy trình thay đổi.

Bốn trạng thái trên có thể diễn ra ở các thời điểm khác nhau và không nên gộp thành một trường “done”.

### 8.2. Bằng chứng kỹ thuật nên đính kèm

| Nhóm bằng chứng | Minh chứng mong muốn |
| --- | --- |
| **Topology/route** | Sơ đồ đường đi, VRF/VLAN, cloud subnet, NAT và đường HA thực tế |
| **Policy** | Rule ID, security group/ACL/network policy version, trạng thái commit/applied |
| **Chức năng** | Kết nối cần thiết và giao dịch ứng dụng đạt điều kiện |
| **Bảo mật** | Test âm chặn đúng nơi, quyền quản trị bị giới hạn, không có bypass ngoài phạm vi |
| **Telemetry** | Log firewall/VPN/DNS/IDS/IPS/EDR/NDR đúng nguồn, thời gian và asset mapping |
| **Sẵn sàng** | Kết quả failover/khôi phục đường dự phòng, các chỉ số dịch vụ |
| **Vận hành** | Change ticket, owners, exceptions, runbook, kế hoạch nâng cấp và rollback |

Đối với mỗi chỉ số, cần ghi **phạm vi đo, phương pháp và thời điểm**. Một đồ thị “không có traffic bị chặn” có thể vì hệ thống không ghi log deny, chứ không chứng minh không có nỗ lực truy cập ngoài quyền.

## 9. Vòng đời phê duyệt, thay thế và quản trị ADR

### 9.1. Chu trình thường gặp

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Accepted: Review và phê duyệt
    Proposed --> Rejected: Không chọn
    Accepted --> Deprecated: Không còn được khuyến nghị
    Accepted --> Superseded: ADR mới thay thế
    Rejected --> [*]
    Deprecated --> Superseded: Quyết định thay thế
~~~

Đây là **mô hình trạng thái minh họa**. Một tổ chức có thể sử dụng tên trạng thái khác nhưng cần thống nhất định nghĩa và quyền chuyển trạng thái.

Quy trình thực tế:

1. **Tạo Proposed:** tác giả ghi vấn đề, tác động, lựa chọn, chứng cứ và phần chưa biết.
2. **Review đa bên:** Network, Security, Cloud, IAM, SRE, chủ dịch vụ hoặc Risk/Compliance góp ý đúng phạm vi ảnh hưởng.
3. **Kiểm tra tiêu chí bắt buộc:** đánh giá risk acceptance, khả năng vận hành, phương án rollback và bằng chứng còn thiếu.
4. **Accepted/Rejected:** người có thẩm quyền ghi rõ quyết định, thời điểm và điều kiện chấp thuận.
5. **Triển khai và nghiệm thu:** xử lý qua project/change records, liên kết bằng chứng và ngoại lệ.
6. **Theo dõi giả định:** đánh giá khi có thay đổi kiến trúc, sự cố, advisory hoặc kết quả kiểm thử mới.
7. **Supersede khi cần:** tạo ADR mới, ghi rõ ADR cũ được thay thế, migrate phạm vi theo kế hoạch và giữ lịch sử.

### 9.2. Cơ chế review và bảo vệ nội dung

Nên có **template nhất quán**, quy tắc đặt ID, quyền review theo lĩnh vực, đường dẫn tới sơ đồ và trạng thái test, người sở hữu trang ADR và lịch xem lại theo trigger. Nếu quản lý ADR trong Git, review diff và lịch sử commit giúp biết quyết định thay đổi ra sao; đồng thời cần lưu bằng chứng chấp thuận ngoài Git nếu quy trình yêu cầu.

ADR network security có thể chứa topology, IP quản trị, lỗ hổng hay thông tin về đường kiểm soát. Chỉ lưu mức dữ liệu cần thiết trong tài liệu có phạm vi truy cập phù hợp; chi tiết nhạy cảm có thể đặt tại kho chứng cứ hạn chế quyền và liên kết bằng ID. **Không nhúng credential, secret, API token hoặc private key** vào ADR.

### 9.3. Mối quan hệ với các artefact khác

| Artefact | Trả lời câu hỏi | Quan hệ với ADR |
| --- | --- | --- |
| **Security policy/standard** | Tổ chức bắt buộc hoặc ưu tiên kiểm soát gì? | Là ràng buộc/driver của ADR |
| **Threat model** | Tài sản, đường tấn công, trust boundary và giả thuyết rủi ro? | Là nguồn bối cảnh và tình huống cần giải quyết |
| **ADR** | Chọn kiến trúc nào và vì sao? | Ghi quyết định cùng đánh đổi và điều kiện |
| **Detailed design/diagram** | Thành phần nào kết nối thế nào, địa chỉ/route/rule cụ thể ra sao? | Cụ thể hóa quyết định vào triển khai |
| **Change request/RFC** | Thay đổi nào, vào lúc nào, ai thực hiện và rollback? | Phê duyệt và kiểm soát thay đổi vận hành |
| **Risk register/exception** | Rủi ro tồn dư nào, ai chấp nhận, thời hạn ra sao? | Lưu xử lý rủi ro và ngoại lệ gắn với ADR |
| **Test report/runbook** | Kiểm soát có hoạt động, vận hành và phục hồi thế nào? | Xác minh quyết định trong thực tế |

Một ADR tốt **không sao chép toàn bộ** các tài liệu trên. Nó tóm tắt các yếu tố ảnh hưởng đến quyết định và dẫn tới nguồn chi tiết.

## 10. Sai lầm phổ biến khi viết ADR network security

1. **Ghi giải pháp trước rồi mới dựng bối cảnh:** “chọn sản phẩm X” nhưng không mô tả vấn đề, yêu cầu và các lựa chọn hợp lý. Hãy bắt đầu bằng rủi ro, phạm vi và tiêu chí.
2. **Chỉ nêu ưu điểm của phương án được chọn:** thiếu trade-off và rủi ro tồn dư khiến người sau không hiểu lý do cần biện pháp bù trừ.
3. **Dùng tiêu chí chung chung:** “an toàn hơn”, “nhanh hơn” không thể nghiệm thu. Chuyển thành kiểm chứng truy cập, độ phủ log, SLO và điều kiện failover cụ thể.
4. **Bỏ qua luồng dữ liệu thực:** firewall tập trung không bảo đảm lọc mọi east–west nếu traffic không đi qua nó. Vẽ đường đi và kiểm thử runtime.
5. **Không kể đến IPv6, NAT, VPN, cloud overlay và HA:** những đường phụ có thể vượt ranh giới tưởng đã kín.
6. **Không phân biệt nguồn thật với giả định:** khiến một lựa chọn dựa trên inventory không đầy đủ được trình bày như kết luận chắc chắn.
7. **Đánh dấu Accepted đồng nghĩa triển khai xong:** bỏ qua rollout, kiểm thử, logging và bàn giao.
8. **Không có phương án rollback:** một quyết định bảo mật có thể làm gián đoạn ứng dụng hoặc khóa đường quản trị cứu hộ.
9. **Không ghi owner và trigger xem lại:** ADR trở thành văn bản lịch sử không ai chăm sóc khi nhà cung cấp thay đổi hoặc phát sinh rủi ro mới.
10. **Sửa lại ADR cũ để che quyết định sai:** làm mất lịch sử và điều kiện áp dụng; tạo ADR thay thế, ghi nguyên nhân và cách chuyển đổi.
11. **Quá nhiều chi tiết cấu hình:** ADR trở thành runbook 500 trang, khó review; chuyển lệnh/rule cụ thể sang design hoặc change ticket có liên kết.
12. **Không thử đường phải bị chặn:** kiểm tra ứng dụng chạy được không chứng minh phân đoạn đang bảo vệ đúng.

## 11. Bài tập ứng dụng: ADR cho truy cập từ xa

**Tình huống:** Một tổ chức đang dùng VPN truyền thống để nhân viên truy cập mạng nội bộ. Mục tiêu mới là giới hạn truy cập theo ứng dụng, danh tính và trạng thái thiết bị, đồng thời giảm quyền nhìn thấy những subnet không cần thiết.

Hãy viết **ADR-NS-015 (Proposed)** với:

- **Context:** hệ thống VPN hiện tại, các nhóm người dùng, ứng dụng cần truy cập và hạn chế về thiết bị/IdP.
- **Options:** tiếp tục VPN với ACL chặt hơn; dùng ZTNA theo ứng dụng; hoặc chuyển đổi theo mô hình hybrid theo từng nhóm dịch vụ.
- **Drivers:** mặc định không truy cập subnet ngoài quyền, MFA, device posture, log đầy đủ, hỗ trợ tài khoản đặc biệt và dịch vụ legacy.
- **Validation:** user đúng quyền vào được ứng dụng; user sai quyền, device không đạt điều kiện và luồng đến subnet khác bị từ chối; đánh giá gián đoạn IdP/controller và khả năng cứu hộ.
- **Consequences:** chi phí đào tạo, tương thích ứng dụng, phức tạp policy, vận hành và mức phụ thuộc nhà cung cấp.
- **Revisit triggers:** thêm ứng dụng legacy, đổi IdP, xuất hiện đường bypass hoặc chất lượng truy cập giảm.

**Gợi ý đánh giá:** không kết luận “ZTNA luôn an toàn hơn VPN” cho mọi kiến trúc. ZTNA có thể giảm mức truy cập theo mạng nếu được cấu hình đúng, nhưng vẫn phụ thuộc nhận diện ứng dụng, xác thực, proxy/connector và chính sách. VPN với phân đoạn, ACL, MFA và kiểm soát thiết bị có thể đạt những yêu cầu cụ thể trong một số bối cảnh. Một ADR tốt phải nêu **điều kiện có thể bác bỏ quyết định**.

## 12. Checklist ADR trước khi đưa vào phê duyệt

| Câu hỏi | Đã có bằng chứng? |
| --- | --- |
| ADR chỉ giải quyết **một quyết định chính**, có ID, owner, date và trạng thái? | |
| Có mô tả vấn đề, phạm vi, tài sản, zone, traffic, threat model và ràng buộc? | |
| Có phân biệt **fact**, **assumption**, **constraint** và **decision**? | |
| Có yêu cầu bắt buộc rõ ràng và tiêu chí đánh đổi đo được? | |
| Có từ hai phương án khả thi trở lên, cùng lợi ích và hạn chế? | |
| Có ghi rõ vì sao chọn phương án này, vì sao loại phương án khác? | |
| Có mô tả tác động tới firewall, VPN, DNS, IDS/IPS, xác thực, cloud và quản trị khi liên quan? | |
| Có kiểm tra east–west, egress/ingress, IPv4/IPv6, NAT, HA và các đường bypass? | |
| Có positive/negative tests, telemetry, hiệu năng, failover và tiêu chí nghiệm thu? | |
| Có rollout, người chịu trách nhiệm, điều kiện dừng, rollback và tài liệu vận hành? | |
| Có rủi ro tồn dư, ngoại lệ, biện pháp bù trừ và thời hạn xem lại? | |
| Có liên kết threat model, policy, design, change, risk register và test evidence? | |
| Có trigger xem lại và phương án tạo ADR thay thế khi giả định thay đổi? | |

### Câu hỏi tự kiểm tra

1. ADR khác threat model và change ticket ở câu hỏi trung tâm như thế nào?
2. Vì sao “mặc định chặn ở firewall biên” không đủ chứng minh APP và DATA đã được phân đoạn khi ở cùng subnet?
3. Tại sao một phương án điểm tổng cao vẫn có thể không được lựa chọn?
4. Trong mẫu ADR hybrid, những kiểm thử âm nào chứng minh rule không cho phép cả subnet truy cập database?
5. Khi một node HA chưa nhận policy, “decision accepted” và “control verified” khác nhau ra sao?
6. Vì sao nên tạo ADR mới để thay thế quyết định cũ khi các giả định trọng yếu thay đổi?
7. Thế nào là một **revisit trigger** tốt so với câu “xem lại sau này”?
8. Nếu chưa đo được độ trễ và chi phí telemetry, người viết ADR nên trình bày tình trạng đó thế nào?

**Gợi ý trả lời:** (1) Threat model phân tích đe dọa, ADR giải thích lựa chọn kiến trúc, change ticket quản lý thay đổi triển khai. (2) Traffic cùng subnet có thể không qua firewall biên; phải xác định và kiểm thử điểm lọc tại đường đi thực. (3) Có thể vi phạm yêu cầu bắt buộc không thể đánh đổi. (4) Thử host khác cùng subnet APP hoặc user không có quyền tới DATA và kiểm tra nơi chặn. (5) Accepted là phê duyệt lựa chọn; verified cần bằng chứng runtime ở từng điểm thực thi. (6) Giữ lịch sử lý do và đánh đổi theo thời điểm. (7) Trigger gắn sự kiện đo/quan sát được như thay đổi topology hoặc vượt ngưỡng SLO. (8) Ghi unknown/pending measurement cùng owner, phương pháp đo và điều kiện chấp thuận.

**Ghi nhớ:** ADR cho network security lưu **lý do quyết định, lựa chọn thay thế, đánh đổi và tiêu chí chứng minh hiệu quả** trong đúng bối cảnh. Giá trị của ADR không dừng ở chấp thuận tài liệu: nó giúp thiết kế, triển khai, kiểm thử, giám sát và thay đổi kiến trúc một cách có thể giải thích và truy vết khi rủi ro hoặc nhu cầu mạng thay đổi.
