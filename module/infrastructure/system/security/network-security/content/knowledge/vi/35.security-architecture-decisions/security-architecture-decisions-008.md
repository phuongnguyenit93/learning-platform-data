# Network control dùng chung và ownership

## 1. Vì sao phải xác định ownership cho network control dùng chung?

Trong chương **Quyết định kiến trúc bảo mật mạng** của học phần **SECURITY_NETWORK_SECURITY**, chủ đề này xem xét cách thiết kế, phân quyền và vận hành những **kiểm soát an ninh mạng dùng chung** (shared network security controls). Đây là vấn đề cốt lõi khi một tổ chức có nhiều nhóm ứng dụng, nhiều môi trường cloud, trung tâm dữ liệu, văn phòng và người dùng truy cập từ xa.

Network security không chỉ là lựa chọn firewall, VPN, IDS/IPS, DNS security hay phân đoạn mạng. Cần biết **ai quyết định chính sách, ai triển khai, ai giám sát, ai khắc phục sự cố và ai chấp nhận rủi ro**. Cùng một firewall có thể phục vụ hàng trăm ứng dụng; một thay đổi rule sai có thể chặn nhiều dịch vụ hoặc mở ra đường truy cập không mong muốn. Khi trách nhiệm bị chia mơ hồ, sự cố thường xảy ra ở điểm nối giữa các nhóm.

**Ví dụ thực tế:** Doanh nghiệp vận hành DNS resolver tập trung cho toàn bộ mạng nội bộ. Nhóm nền tảng sở hữu resolver, nhóm an ninh sở hữu danh mục tên miền bị chặn, nhóm ứng dụng yêu cầu ngoại lệ, SOC theo dõi truy vấn bất thường. Nếu resolver ngừng hoạt động, không thể chỉ nói “đây là dịch vụ bảo mật” mà bỏ ngỏ ai khôi phục. Nếu một ứng dụng cần giải phóng tên miền khỏi blocklist, cũng không thể để người có quyền vận hành máy chủ tự ý quyết định rủi ro kinh doanh.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt control dùng chung, control riêng của workload và control được kế thừa; xác định ranh giới thực tế của từng control.
2. Thiết lập ownership theo các khía cạnh: chính sách, nền tảng, thay đổi, vận hành, bằng chứng và rủi ro.
3. Thiết kế mô hình tập trung, phân tán hoặc liên kết (federated) phù hợp với firewall, DNS, VPN/ZTNA, IDS/IPS, cloud networking và Kubernetes.
4. Xây dựng ma trận RACI, inventory, hợp đồng dịch vụ, quy trình ngoại lệ và quy trình xử lý sự cố.
5. Đánh giá hiệu lực, độ sẵn sàng và khả năng kiểm toán của các control dùng chung qua bằng chứng và các chỉ số cụ thể.

## 2. Khái niệm nền tảng

### 2.1. Network control là gì?

**Network control** là cơ chế kỹ thuật hoặc quy trình giúp quyết định, giới hạn, phát hiện hoặc ghi nhận các tương tác qua mạng. Nó có thể thực hiện một hay nhiều chức năng:

- **Prevent:** chặn truy cập, giới hạn lưu lượng, xác thực kết nối; ví dụ ACL, firewall, security group, NAC, ZTNA.
- **Detect:** nhận diện tín hiệu nghi vấn; ví dụ IDS, NDR, cảnh báo bất thường từ DNS hoặc flow logs.
- **Observe:** tạo log, flow records, packet metadata, telemetry và bằng chứng phục vụ kiểm tra.
- **Recover/contain:** cô lập segment, thu hồi route hoặc phiên truy cập, đưa cấu hình về trạng thái an toàn khi xử lý sự cố.

**Control dùng chung** là control được nhiều ứng dụng, mạng, tài khoản cloud, cụm hạ tầng hoặc nhóm sử dụng dưới cùng một mô hình cung cấp dịch vụ và quản trị. Tính “dùng chung” là quan hệ giữa người cung cấp control và nhiều bên tiêu thụ, không nhất thiết đồng nghĩa với một thiết bị vật lý tập trung.

**Control riêng** là cơ chế chuyên biệt cho một workload hoặc nhóm tài sản, chẳng hạn network policy trong một namespace Kubernetes hoặc firewall policy bổ sung cho một ứng dụng nhạy cảm.

**Control được kế thừa** (inherited control) là control được một workload sử dụng nhờ nằm trong phạm vi bảo vệ của nền tảng. Việc “kế thừa” chỉ có ý nghĩa nếu có bằng chứng về phạm vi áp dụng, cấu hình thực thi, trạng thái vận hành và các phần trách nhiệm còn lại của workload.

### 2.2. Ownership không đồng nghĩa với toàn bộ quyền thực hiện

Từ “owner” thường bị dùng cho nhiều vai trò khác nhau:

| Vai trò | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| **Control owner** | Ai chịu trách nhiệm cuối cùng về mục tiêu và hiệu lực của control? | Trưởng nhóm Network Security |
| **Platform/service owner** | Ai chịu trách nhiệm về nền tảng cung cấp control, vòng đời, năng lực và tính sẵn sàng? | Nhóm Network Platform |
| **Policy owner** | Ai xác định chính sách allow/deny, ngoại lệ, tiêu chuẩn bảo mật? | Nhóm Security Architecture |
| **Operational owner** | Ai giám sát sức khỏe dịch vụ, thực hiện thao tác, trực sự cố? | Network Operations/SRE |
| **Application/resource owner** | Ai biết nhu cầu kết nối và kiểm soát phụ thuộc của ứng dụng? | Nhóm ứng dụng hoặc product team |
| **Risk owner** | Ai có thẩm quyền chấp nhận rủi ro còn lại trong phạm vi tài sản hoặc nghiệp vụ? | Chủ sở hữu dịch vụ kinh doanh theo phân cấp |
| **Detection/response owner** | Ai đánh giá alert, điều tra và điều phối phản ứng? | SOC/Incident Response |

Một cá nhân hoặc nhóm có thể đảm nhận nhiều vai trò. Tuy nhiên, **quyền quyết định thay đổi policy, quyền triển khai thay đổi và quyền chấp nhận rủi ro cần được phân định rõ**. Chủ sở hữu ứng dụng không mặc nhiên có quyền bỏ qua tiêu chuẩn bảo mật chung; nhóm vận hành không mặc nhiên được chấp nhận rủi ro thay cho lãnh đạo nghiệp vụ.

### 2.3. Đơn vị ownership cần được mô tả chính xác

Không nên ghi chung một trường owner cho “network security của công ty” rồi giả định mọi vấn đề đã có người phụ trách. Cần xác định phạm vi theo từng lớp:

- **Service:** dịch vụ dùng chung, ví dụ dịch vụ DNS resolver hoặc cổng VPN.
- **Control:** mục tiêu cụ thể, ví dụ chặn egress theo tên miền hoặc bắt buộc xác thực thiết bị.
- **Policy:** bộ rule và tiêu chuẩn định nghĩa hành vi nào được phép.
- **Instance/segment/tenant:** nơi control có hiệu lực, ví dụ một VPC, một site, một cluster.
- **Exception:** ngoại lệ được phê duyệt cho một tài sản hoặc kết nối cụ thể.
- **Incident:** đầu mối điều phối sự cố theo loại tác động và độ ưu tiên.

Khi mỗi đơn vị có phạm vi, người chịu trách nhiệm và nguồn bằng chứng rõ ràng, hệ thống kiểm soát có thể được vận hành và kiểm toán.

## 3. Những network control thường được chia sẻ

| Control | Dạng cung cấp dùng chung | Phụ thuộc và ranh giới cần chú ý |
| --- | --- | --- |
| Firewall/segmentation | Firewall hub, policy mặc định giữa zone, security group baseline | Không nhìn thấy toàn bộ east–west nếu lưu lượng không đi qua; route có thể vòng tránh |
| Internet egress | Secure web gateway, proxy, NAT gateway và egress firewall | DNS, proxy bypass, direct Internet access, độ sẵn sàng và băng thông |
| DNS security | Resolver tập trung, logging, RPZ, phân giải private zone | Split-horizon DNS, cache, DoH/DoT, quyền riêng tư và tính liên tục |
| VPN/ZTNA | Cổng truy cập từ xa, kiểm tra identity và device posture | IdP, MFA, phân quyền theo tài nguyên, vòng đời phiên và thiết bị |
| NAC/Wi-Fi | 802.1X, posture, gán VLAN, guest isolation | Thiết bị không hỗ trợ 802.1X, roaming, chứng chỉ, tài sản IoT |
| IDS/IPS/NDR | Sensor hoặc nền tảng phát hiện tập trung | Vị trí đặt sensor, lưu lượng mã hóa, thời gian cập nhật rule |
| TLS/PKI | CA, cấp phát và gia hạn chứng chỉ, mTLS trust anchors | Phân quyền cấp chứng chỉ, khóa riêng, rotation, thu hồi và thời gian hết hạn |
| DDoS/WAF/API gateway | Lớp bảo vệ biên cung cấp cho nhiều dịch vụ | Cấu hình riêng từng ứng dụng, API schema, false positive, routing |
| Cloud network guardrails | SCP/organization policy, network policy baseline, routing hub | Trách nhiệm cloud provider, tài khoản/vùng chưa được onboard |
| Kubernetes/service mesh | NetworkPolicy mặc định, egress gateway, mTLS | Chính sách theo namespace/service, CNI/mesh coverage, traffic ngoài mesh |
| Telemetry pipeline | Flow logs, syslog, collector, SIEM, NDR | Độ đầy đủ trường, quyền truy cập log, mất dữ liệu và retention |

Bảng trên mô tả các **ứng viên** dùng chung, không quy định phải gom mọi chức năng vào một hệ thống. Có những kiểm soát nên triển khai theo từng khu vực để giảm độ trễ và rủi ro lan rộng; quản trị và chuẩn hóa chính sách vẫn có thể dùng chung.

## 4. Chọn mô hình sở hữu: central, local hay federated?

Ba mô hình kiến trúc thường gặp:

| Mô hình | Cách vận hành | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **Tập trung (centralized)** | Một nhóm thiết kế, vận hành và thay đổi control cho nhiều đơn vị | Nhất quán, dễ thu bằng chứng, giảm trùng lặp năng lực | Nghẽn yêu cầu, ảnh hưởng nhiều hệ thống khi lỗi chung |
| **Phân tán (decentralized)** | Mỗi nhóm/ứng dụng tự triển khai phần lớn control | Linh hoạt, bám sát workload, quyết định nhanh | Dễ cấu hình lệch chuẩn, khó kiểm tra độ phủ và ownership |
| **Liên kết (federated)** | Nền tảng đưa ra baseline, guardrail, API; nhóm workload sở hữu rule chi tiết trong giới hạn | Cân bằng tự phục vụ và chuẩn chung; dễ mở rộng | Cần hợp đồng rõ, phân quyền chặt, kiểm tra drift và giải quyết xung đột |

Không có mô hình nào tối ưu cho tất cả các lớp. Thường chọn:

- **Tập trung** với hạ tầng tin cậy dùng chung: resolver gốc, PKI nền tảng, transit gateway, chuẩn log, đường kết nối site-to-site.
- **Federated** với policy có nhiều biến thể theo ứng dụng: firewall allow rules, WAF tuning, Kubernetes network policies, egress exception.
- **Local** với những control chỉ hiểu được ngữ cảnh nghiệp vụ và rủi ro cụ thể: rule giữa các microservice, truy cập tới cơ sở dữ liệu ứng dụng, response logic riêng của một workload.

### 4.1. Các câu hỏi quyết định

Trước khi chọn mô hình, đánh giá:

1. **Blast radius:** một lỗi control có thể ảnh hưởng bao nhiêu người dùng, site hoặc workload?
2. **Tính đồng nhất:** chính sách có thể biểu diễn dưới dạng chuẩn chung hay rất phụ thuộc từng ứng dụng?
3. **Độ trễ và tuyến lưu lượng:** datapath tập trung có làm phát sinh hairpin, chi phí hoặc điểm nghẽn không?
4. **Mức rủi ro:** kiểm soát nào cần duyệt tập trung, tách nhiệm vụ hoặc bằng chứng kiểm toán?
5. **Khả năng tự phục vụ:** ứng dụng có thể tự tạo rule trong guardrail mà không mở lỗ hổng xuyên zone không?
6. **Sẵn sàng và khôi phục:** có cơ chế dự phòng, failover, break-glass, rollback rõ ràng không?
7. **Giới hạn nhà cung cấp:** cloud provider hoặc dịch vụ SaaS chịu trách nhiệm phần nào; khách hàng còn phải cấu hình phần nào?
8. **Quan sát và đo lường:** mọi đơn vị có lấy được log, owner và trạng thái policy khi điều tra không?

**Nguyên tắc:** tập trung **tiêu chuẩn và bằng chứng** không bắt buộc tập trung **mọi gói tin**. Chẳng hạn, policy baseline có thể được phân phối đến nhiều VPC/cluster và thực thi tại chỗ để giảm phụ thuộc vào một gateway chung.

## 5. Kiến trúc tham chiếu: phân biệt policy plane và enforcement plane

Một hệ thống dùng chung an toàn phải phân biệt nơi thiết kế/quản trị chính sách với nơi chính sách được thực thi trên kết nối.

~~~mermaid
flowchart TB
    G["Security Architecture\nBaseline / guardrail / risk policy"] --> P["Policy repository\nversion, review, approval"]
    A["Application owner\nConnectivity request / context"] --> P
    P --> C["Validation + CI checks\nscope, owner, expiry, conflicts"]
    C --> O["Platform automation\nApply, reconcile, audit"]
    O --> F1["Firewall / cloud controls\nZone and VPC"]
    O --> F2["DNS / egress / proxy\nSite or region"]
    O --> F3["Kubernetes / service mesh\nCluster or namespace"]
    U["Users / workloads\nTraffic"] --> F1
    U --> F2
    U --> F3
    F1 --> T["Central telemetry\nLogs, health, coverage"]
    F2 --> T
    F3 --> T
    T --> S["SOC / operations\nMonitoring and incident handling"]
    S --> R["Issue / exception / remediation"]
    R --> P
~~~

- **Policy/control plane:** nơi xác định mong muốn về truy cập, baseline, nhận diện các thay đổi và phân phối cấu hình.
- **Enforcement/data plane:** nơi một kết nối cụ thể thực sự bị cho phép, từ chối, giới hạn hoặc giám sát.
- **Telemetry/assurance plane:** nơi đối chiếu trạng thái đã cấu hình với thực tế, theo dõi tính sẵn sàng và hiệu lực control.

Nếu policy đã được phê duyệt nhưng chưa triển khai tại một VPC, chưa thể tuyên bố VPC đó được bảo vệ. Nếu datapath thực thi rule nhưng log không đến SOC, hệ thống vẫn có lỗ hổng giám sát. Cần đo cả **desired state**, **deployed state** và **observed state**.

### 5.1. Ranh giới tin cậy của mô hình dùng chung

Cần chỉ ra và kiểm chứng các ranh giới quan trọng:

- **Giữa tenant:** nhóm ứng dụng A không được đọc/sửa policy hay log nhạy cảm của nhóm B nếu không có quyền tương ứng.
- **Giữa control plane và data plane:** kho cấu hình bị xâm nhập không được tự động thay đổi mọi môi trường mà không qua kiểm soát.
- **Giữa vùng mạng:** sự hiện diện của một gateway chung không được tạo đường đi mặc định giữa vùng nhạy cảm và vùng kém tin cậy.
- **Giữa các lớp nhận diện:** DNS, NAT, IP động, identity và workload ID phải được ánh xạ đúng khi áp policy và điều tra.
- **Giữa môi trường:** dev/test không được kéo theo quyền truy cập production chỉ vì dùng chung công cụ triển khai.

Một chính sách an toàn thường dựa trên **default deny tại các ranh giới nhạy cảm**, cấp phép tối thiểu, danh tính có thể kiểm chứng và các ngoại lệ có thời hạn. “Đã ở trong mạng nội bộ” không đủ để mặc nhiên cấp quyền cho workload khác.

## 6. Ma trận ownership và RACI

RACI là cách phân công người thực hiện, người chịu trách nhiệm cuối cùng, người cần tham vấn và người cần được thông báo:

- **R — Responsible:** trực tiếp thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng đối với quyết định hoặc kết quả.
- **C — Consulted:** được lấy ý kiến trước khi thực hiện.
- **I — Informed:** được thông báo tình trạng hoặc kết quả.

Đối với **mỗi hoạt động/đầu ra**, nên có **một A rõ ràng** trong sơ đồ phân công của tổ chức; có thể có nhiều R và C. RACI không thay thế quy định phê duyệt rủi ro hay thẩm quyền kiểm soát thay đổi.

### 6.1. Ví dụ RACI cho egress firewall dùng chung

Giả sử có các vai trò: **SecArch** (kiến trúc an ninh), **NetPlat** (nền tảng mạng), **App** (ứng dụng), **SOC** (giám sát), **BizRisk** (chủ sở hữu rủi ro nghiệp vụ).

| Hoạt động | SecArch | NetPlat | App | SOC | BizRisk |
| --- | :---: | :---: | :---: | :---: | :---: |
| Định nghĩa baseline deny/allow và guardrail | **A/R** | C | C | C | I |
| Thiết kế HA, capacity và triển khai nền tảng gateway | C | **A/R** | I | C | I |
| Khai báo nhu cầu kết nối của ứng dụng | C | C | **A/R** | I | I |
| Triển khai rule đã được phê duyệt | C | **A/R** | C | I | I |
| Phân tích alert bất thường từ egress | C | C | C | **A/R** | I |
| Phê duyệt chấp nhận rủi ro ngoại lệ vượt baseline | C | C | R | I | **A** |
| Khôi phục nền tảng sau outage gateway | C | **A/R** | C | C | I |
| Đánh giá hiệu lực baseline định kỳ | **A** | R | C | R | I |

**Lưu ý:** Đây là ví dụ minh họa, không phải cơ cấu bắt buộc. Có tổ chức giao baseline cho CISO, vận hành cho SRE, phê duyệt ngoại lệ cho hội đồng rủi ro. Bản RACI chính thức phải được các nhóm chấp thuận và có người thay thế khi owner vắng mặt.

### 6.2. Tách những câu hỏi dễ bị nhầm

**Ai có quyền tạo request?** Nhóm ứng dụng và người vận hành có thể đề xuất; không đồng nghĩa được phê duyệt.

**Ai được quyết định cho phép lưu lượng?** Theo loại kết nối và mức độ rủi ro. Policy owner định nghĩa guardrail; resource owner giải trình nhu cầu; người có thẩm quyền phê duyệt phần vượt chuẩn.

**Ai có quyền bấm nút triển khai?** Platform service account hoặc nhóm vận hành được ủy quyền, với nhật ký thay đổi và kiểm soát quyền.

**Ai quyết định đóng ngoại lệ?** Người sở hữu policy phối hợp bên chịu rủi ro, có quy tắc hết hạn từ trước; phải biết ứng dụng nào sẽ bị ảnh hưởng.

**Ai xử lý sự cố?** Incident commander do quy trình ứng cứu xác định, còn kỹ sư nền tảng có thể là người thực thi biện pháp kỹ thuật. Người quyết định và người thao tác là hai trách nhiệm khác nhau.

## 7. Inventory: xác định control nào đang bảo vệ tài sản nào

Ownership phải đi kèm inventory có thể truy vết. Mỗi shared control nên có ít nhất các trường:

| Trường | Ý nghĩa |
| --- | --- |
| control_id / service_id | Định danh bất biến cho control và dịch vụ |
| purpose / threat_scenario | Mục tiêu phòng vệ, hành vi nguy cơ được giải quyết |
| policy_owner / platform_owner | Người quyết định policy, người vận hành nền tảng |
| risk_owner / incident_contact | Người chấp nhận rủi ro và đầu mối khẩn cấp |
| coverage_scope | Site, zone, VPC, cluster, subnet hoặc nhóm workload được bảo vệ |
| enforcement_point | Thiết bị / dịch vụ thực thi chính sách thực tế |
| dependencies | IdP, DNS, PKI, routing, cloud API, logging và các phụ thuộc khác |
| policy_source / version | Nguồn cấu hình chuẩn và phiên bản đang triển khai |
| exceptions / expiry | Ngoại lệ hiện hành, người phê duyệt và thời hạn |
| telemetry / evidence | Nơi lưu log, chỉ số health, chứng cứ hiệu lực |
| SLO / recovery | Mục tiêu sẵn sàng, thời gian phục hồi và chiến lược failover |
| last_review / next_review | Ngày rà soát và trách nhiệm tái kiểm tra |

Ví dụ metadata **minh họa**, không phải cấu hình thực thi cho sản phẩm cụ thể:

~~~yaml
control_id: NET-CTRL-014
name: shared-egress-policy
purpose: Restrict outbound connectivity from production workloads
scope:
  environment: production
  regions:
    - region-a
    - region-b
  network_zones:
    - app-prod
policy_owner: security-architecture
platform_owner: network-platform
risk_owner: business-service-owner
incident_contact: network-operations-oncall
enforcement:
  type: regional-egress-firewall
  reference: gateway-inventory
policy:
  source: security-policy-repository
  baseline_version: v3
observability:
  source: centralized-network-logs
  required_fields:
    - timestamp_utc
    - source_workload
    - destination
    - action
    - policy_id
dependencies:
  - regional-routing
  - identity-service
  - log-collector
availability:
  target_slo: organization-defined
  failover: regional-redundancy
review:
  last_reviewed: 2026-11-01
  next_review_due: 2027-02-01
~~~

Không đưa bí mật, token, khóa riêng hoặc địa chỉ quản trị nhạy cảm vào inventory mở. Có thể lưu link tới kho cấu hình và bằng chứng có kiểm soát truy cập thay vì sao chép dữ liệu nhạy cảm vào nhiều nơi.

### 7.1. Quan hệ giữa asset owner và control owner

Một workload thường được bảo vệ bởi nhiều control. Nên biểu diễn quan hệ dưới dạng **asset → zone → enforcement point → policy version → control owner**. Nếu workload di chuyển từ VPC A sang VPC B hoặc chuyển sang một cluster khác, cơ chế onboarding phải kiểm tra lại toàn bộ quan hệ này.

**Ví dụ:** Ứng dụng đặt sau WAF chung vẫn cần nhóm ứng dụng phụ trách cấu hình xác thực và phân quyền ở lớp ứng dụng. Dịch vụ WAF không “sở hữu thay” logic nghiệp vụ, cũng không cam kết ngăn mọi lỗ hổng API. Việc chia sẻ control phải đi cùng bản mô tả giới hạn bảo vệ.

## 8. Control contract: thỏa thuận giữa nền tảng và nhóm sử dụng

Một shared control chỉ vận hành bền vững khi có **hợp đồng dịch vụ rõ ràng**. Đây có thể là tài liệu kiến trúc, API contract hoặc policy-as-code, không nhất thiết là hợp đồng pháp lý.

Hợp đồng nên quy định:

1. **Phạm vi bảo vệ:** những môi trường, giao thức, nguồn/đích nào được kiểm soát; điều gì ngoài phạm vi.
2. **Default và guardrail:** cơ chế deny mặc định, rule ưu tiên, cổng và tài nguyên được phép sử dụng, tiêu chuẩn định danh.
3. **Giao diện yêu cầu:** mẫu dữ liệu cần có khi onboarding hoặc xin kết nối: workload, nguồn, đích, giao thức, port, mục đích, owner.
4. **Phê duyệt và hạn mức:** loại yêu cầu nào được tự động duyệt, loại nào cần review; thời hạn tối đa của exception.
5. **SLO/SLA:** tình trạng vận hành, thời gian áp thay đổi, độ trễ telemetry, phản hồi sự cố.
6. **Observability:** nơi người dùng xem được kết quả apply, lỗi cấu hình, log allow/deny và đường dẫn hỗ trợ.
7. **Failure behavior:** control bị lỗi sẽ chặn, cho phép theo chính sách dự phòng hay chuyển sang đường dự phòng; do ai quyết định.
8. **Vòng đời:** onboarding, thay đổi, thu hồi, dọn rule không dùng và chuẩn bị di chuyển kiến trúc.

Không thể giả định một dịch vụ luôn **fail-open** hoặc luôn **fail-closed**. Ví dụ kết nối tới hệ thống thanh toán có thể ưu tiên chặn nếu mất xác thực; dịch vụ khẩn cấp có yêu cầu tính sẵn sàng khác. Kiến trúc phải phân tích tác động kinh doanh, thiết kế redundancy, giới hạn chế độ suy giảm và kiểm thử thực tế.

### 8.1. Luồng thay đổi một policy dùng chung

~~~mermaid
sequenceDiagram
    participant App as Application owner
    participant Policy as Security policy owner
    participant Repo as Policy repo & checks
    participant Ops as Network platform
    participant SOC as SOC
    App->>Repo: Tạo change request (asset, flow, lý do, expiry)
    Repo->>Repo: Kiểm tra schema, scope, trùng lặp, guardrail
    alt Tuân thủ baseline
        Repo->>Ops: Request đã đạt kiểm tra tự động
    else Vượt guardrail
        Repo->>Policy: Yêu cầu review và phê duyệt ngoại lệ
        Policy-->>Repo: Quyết định có ghi nhận rủi ro
        Repo->>Ops: Request được phê duyệt hợp lệ
    end
    Ops->>Ops: Kiểm tra impact, triển khai có kiểm soát
    Ops->>SOC: Thông báo thay đổi ảnh hưởng giám sát
    Ops-->>App: Kết quả apply + đường dẫn bằng chứng
    App->>App: Kiểm tra kết nối và hoạt động ứng dụng
    SOC->>SOC: Theo dõi log, alert và dấu hiệu bất thường
~~~

Một request bị từ chối phải có lý do và đường dẫn xử lý; không nên dẫn tới việc nhóm ứng dụng tự tạo một đường Internet khác để “đi vòng” kiểm soát.

## 9. Chính sách chung, quyền tự phục vụ và guardrail

Mô hình federated cần tạo không gian tự phục vụ có giới hạn để tránh quá tải nhóm nền tảng.

**Ví dụ phân tầng policy:**

| Tầng | Owner | Phạm vi | Ví dụ |
| --- | --- | --- | --- |
| Organization baseline | Security Architecture | Áp dụng toàn tổ chức | Không cho truy cập quản trị từ Internet công cộng |
| Platform baseline | Network/Cloud Platform | Site, VPC, cluster | Bật flow log, chặn mặc định giữa các zone |
| Workload policy | Application team | Ứng dụng, namespace, service | Chỉ cho backend kết nối DB đúng port |
| Exception | Risk owner + policy owner theo quy trình | Một asset, flow, thời hạn | Cho kết nối tạm đến đối tác được duyệt |
| Emergency override | Incident authority được ủy quyền | Phạm vi cô lập/khôi phục có hạn | Tạm thời hạn chế egress khi ứng cứu |

**Quy tắc precedence** phải rõ và được kiểm thử. Nhiều hệ thống firewall/ACL có logic ưu tiên, deny hoặc evaluation order khác nhau. Không được suy diễn rằng “deny ở lớp trên luôn thắng” nếu sản phẩm thực thi không như vậy. Thiết kế nên định nghĩa *effective policy* và kiểm tra nó trên môi trường đích.

### 9.1. Ví dụ yêu cầu kết nối tự phục vụ

Nhóm ứng dụng cần cho frontend gọi API nội bộ qua HTTPS. Một yêu cầu có cấu trúc có thể dùng định dạng:

~~~yaml
request_id: NET-REQ-204
requester_team: customer-portal
source:
  workload: frontend
  environment: production
  zone: web
destination:
  service: internal-api
  environment: production
  zone: application
protocol: TCP
destination_port: 443
business_reason: Frontend communicates with internal API
data_classification: internal
risk_class: standard
requested_valid_until: 2027-01-31
application_owner: customer-portal-lead
~~~

Công cụ kiểm tra không chỉ xác nhận cổng 443. Nó cần biết **destination thật là gì**, policy cho phép đường đi giữa hai zone không, có yêu cầu mTLS hay identity hay không, log có đủ không và kết nối có làm mất ý nghĩa của phân đoạn mạng không. Nếu port hợp lệ nhưng đích là tài sản cấm, request phải bị chặn theo guardrail.

Ví dụ pseudo-policy:

~~~text
allow_request(request) IF
    source and destination exist in approved inventory
    AND both owners are active and identifiable
    AND destination is within permitted zone-to-zone flows
    AND requested service/protocol is explicitly approved
    AND requested validity is within policy limit
    AND required telemetry and enforcement points are present

otherwise:
    route request to policy review or reject with reason
~~~

Đây là **giả mã kiểm tra quy trình**, không phải syntax của firewall hay một cloud provider. Chính sách triển khai thực tế cần được kiểm thử trên đúng công cụ và version đang sử dụng.

### 9.2. Bảo vệ quyền quản trị

- Phân quyền theo vai trò, môi trường và loại control; tách quyền xem, yêu cầu, phê duyệt, triển khai và emergency override.
- Ưu tiên identity cá nhân, MFA, tài khoản tự động ngắn hạn, nhật ký thao tác và review quyền định kỳ.
- Không cho một tài khoản dịch vụ có quyền thay đổi toàn bộ tổ chức nếu phạm vi nhiệm vụ chỉ thuộc một tenant.
- Với thay đổi rủi ro cao, áp dụng người kiểm tra độc lập và yêu cầu đánh giá tác động.
- Chế độ break-glass phải có điều kiện kích hoạt, thời hạn, giám sát riêng và review sau sự kiện.

## 10. Quản lý ngoại lệ và debt của network control

Ngoại lệ là điều có thể cần trong kiến trúc thực tế nhưng không được biến thành chính sách vĩnh viễn, không có owner.

Ví dụ: Một hệ thống cũ chưa dùng được mTLS hoặc đối tác chỉ hỗ trợ một dải IP cố định. Trước khi chấp thuận, cần mô tả tác động, các biện pháp bù trừ, thời gian hiệu lực và kế hoạch khắc phục lâu dài.

| Trường của exception | Ví dụ |
| --- | --- |
| ID, control bị ảnh hưởng | EX-NET-019 / egress allowlist |
| Business reason | Tích hợp với hệ thống đối tác trong đợt chuyển đổi |
| Asset/flow | Workload X đến endpoint Y qua TCP 443 |
| Requested by | Application owner |
| Approved by | Risk owner có thẩm quyền, có review từ policy owner |
| Compensating controls | Logging nâng cao, giới hạn nguồn, xác thực phía ứng dụng |
| Validity | Từ ngày phê duyệt đến hạn hết hiệu lực đã định |
| Closure criteria | Chuyển sang kết nối chuẩn, xác minh kết nối cũ không còn |
| Evidence | Change ID, log, kết quả thử nghiệm, ticket |

**Vòng đời chuẩn:** tạo ngoại lệ → đánh giá rủi ro → phê duyệt có thời hạn → áp dụng đúng phạm vi → giám sát → cảnh báo sắp hết hạn → thu hồi hoặc gia hạn có đánh giá mới → kiểm chứng rule đã bị xóa.

Thời hạn trong CMDB mà không liên kết đến logic thu hồi thực tế chưa đủ. Nếu quá hạn mà rule vẫn còn active, đó là **control drift** cần có người xử lý.

### 10.1. Hạn chế rủi ro từ quy tắc tồn đọng

Các dấu hiệu policy debt:

- Rule any-to-any hoặc phạm vi CIDR quá rộng không có giải trình.
- Rule không còn tài sản đích nhưng chưa bị dọn.
- Ngoại lệ không có ngày hết hạn hoặc không tìm thấy người phê duyệt.
- Một đường truy cập được cấp lặp ở nhiều firewall mà không biết đường nào là đường có hiệu lực.
- Dấu vết IP không ánh xạ được sang workload/owner; NAT làm che khuất chủ thể.
- Rule emergency còn tồn tại nhiều tháng sau khi sự cố khép lại.

Dùng log hit count, inventory, bản đồ luồng mạng và lịch review để đề xuất dọn. **Không xóa rule chỉ vì không thấy traffic ngắn hạn**: có workload theo tháng, luồng phục hồi thảm họa hoặc kết nối hiếm. Phải xác nhận với asset owner, xét cửa sổ quan sát phù hợp và có rollback.

## 11. Shared responsibility trong hybrid cloud và Kubernetes

### 11.1. Trách nhiệm nhà cung cấp và khách hàng

Với cloud hoặc dịch vụ managed, nhà cung cấp có thể chịu trách nhiệm về hạ tầng vật lý, nền tảng dịch vụ và một phần vận hành. Khách hàng thường vẫn phải xác định các chính sách kết nối, identity, địa chỉ mạng, dữ liệu log và yêu cầu giám sát. Phân định cụ thể tùy loại dịch vụ và hợp đồng.

**Ví dụ:** Một managed firewall có thể được cloud provider bảo trì phần mềm lõi, nhưng tổ chức phải quyết định ai tạo rule, ai phát hiện cấu hình quá rộng, ai bật logging, ai xác nhận vùng VPC mới đã được bảo vệ và ai chịu trách nhiệm nếu route đi vòng qua firewall.

### 11.2. Mẫu kiến trúc hub-and-spoke

Một tổ chức có mạng hub cho dịch vụ chung (DNS, egress inspection, VPN) và nhiều spoke VPC cho workload.

~~~mermaid
flowchart TB
    R["Remote users\nVPN / ZTNA"] --> H["Shared services hub"]
    S1["Spoke A\nApplication VPC"] --> H
    S2["Spoke B\nData VPC"] --> H
    S3["Spoke C\nPlatform VPC"] --> H
    H --> D["DNS / Egress / Inspection"]
    D --> I["External services"]
    S1 -. "Flow logs / audit" .-> L["Telemetry and SOC"]
    S2 -. "Flow logs / audit" .-> L
    S3 -. "Flow logs / audit" .-> L
    H -. "Gateway logs" .-> L
~~~

Sơ đồ là mô hình khái niệm, không xác nhận rằng **mọi** đường spoke-to-spoke đều được inspection. Cần xác minh từng route table, attachment, peering, private endpoint, direct connect, firewall policy và security group; một số đường có thể bypass hub. Tập trung hub tăng chuẩn hóa nhưng cũng có nguy cơ nghẽn, tăng chi phí truyền dữ liệu và tác động rộng khi lỗi.

Phân trách nhiệm gợi ý:

- **Cloud/network platform:** topology, routing, service attachment, gateway availability, logging pipeline.
- **Security Architecture:** tiêu chuẩn segmentation, yêu cầu inspection và rule baseline.
- **Application/asset owners:** danh sách luồng hợp lệ, danh tính workload, thử nghiệm sau thay đổi.
- **SOC:** giám sát và điều tra các tín hiệu đi qua hub, đối chiếu telemetry từ spoke.
- **Risk owner:** chấp thuận rủi ro ngoại lệ khi luồng không thể tuân thủ yêu cầu chung.

### 11.3. Control dùng chung trong Kubernetes

Nhiều nhóm dùng chung một cluster không có nghĩa các namespace tự động cô lập an toàn. Kết quả phụ thuộc CNI, NetworkPolicy, RBAC, chính sách ingress/egress và các kết nối ngoài cluster.

Có thể dùng mô hình:

- **Platform:** cài đặt CNI hỗ trợ policy, chính sách cô lập mặc định, phân quyền cluster, log và cơ chế giám sát thay đổi.
- **Workload team:** khai báo nguồn/đích giao tiếp hợp lệ của service; thử nghiệm ứng dụng khi policy thay đổi.
- **Security:** định nghĩa guardrail như không cho đường quản trị không xác thực, chuẩn mTLS nếu áp dụng, yêu cầu egress logging.
- **SOC:** giám sát network flow hoặc audit phù hợp; điều tra kết nối bất thường.

Ví dụ NetworkPolicy minh họa mô hình deny ingress mặc định cho pod trong một namespace (khả năng áp dụng phải được xác minh với CNI đang dùng):

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: application-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Policy trên chỉ chọn **Ingress**. Nó **không** tự đặt default-deny egress. Trước khi dùng, workload team và platform owner phải xác định rule bổ sung cho lưu lượng hợp lệ, DNS, health checks và service dependencies. Kiểm thử connectivity từ các namespace/tài khoản khác nhau sau khi áp dụng; không suy đoán cô lập mạng chỉ từ sự tồn tại của manifest.

## 12. Độ tin cậy, sự cố và cơ chế tiếp quản

Một shared network control có thể trở thành **shared failure domain**: cùng một lỗi khiến nhiều hệ thống bị gián đoạn. Ownership vì vậy phải đi cùng kế hoạch chịu lỗi.

### 12.1. Những hỏng hóc cần mô hình hóa

| Failure mode | Tác động có thể có | Biện pháp và owner |
| --- | --- | --- |
| DNS resolver chung ngừng hoạt động | Nhiều ứng dụng không phân giải được tên | Dự phòng đa vùng, health checks, runbook failover – Platform |
| Egress firewall quá tải | Latency cao, kết nối timeout | Capacity planning, autoscale nếu hỗ trợ, giới hạn lưu lượng – Network Platform |
| Đẩy rule sai trên nhiều zone | Chặn dịch vụ hoặc mở rộng truy cập ngoài ý muốn | Canary rollout, policy tests, approval và rollback – Platform + Policy owner |
| Policy repo/automation bị chiếm quyền | Thay đổi diện rộng trái phép | Tách quyền, ký/duyệt thay đổi, audit immutable – Platform/Security |
| Log collector ngừng nhận sự kiện | Mất tầm nhìn và bằng chứng điều tra | Monitoring pipeline, backlog và replay nếu hỗ trợ – Operations/SOC |
| IdP/ZTNA bị lỗi | Người dùng không thể truy cập tài nguyên | Thiết kế khả dụng và thủ tục khẩn cấp giới hạn – IAM + Platform |
| Ngoại lệ không được thu hồi | Đường truy cập mở lâu hơn cần thiết | Expiry enforcement và drift detection – Policy/Platform |
| Asset owner rời nhóm | Quy tắc “mồ côi” không ai chịu trách nhiệm | Tự động mapping owner và quy trình bàn giao – Asset inventory owner |

Một quy trình sự cố cần xác định:

1. **Phát hiện:** health checks, SLO breach, telemetry drop, alert sai lệch hay báo cáo của ứng dụng.
2. **Phân loại:** lỗi nền tảng, lỗi policy, kết nối ngoài phạm vi, hoặc sự cố an ninh.
3. **Điều phối:** chỉ định incident commander và người thực hiện thao tác cho từng hệ thống.
4. **Giới hạn tác động:** chặn luồng nguy hiểm hoặc chuyển lưu lượng sang phương án dự phòng đã kiểm thử.
5. **Khôi phục:** rollback, khôi phục cấu hình/route, xác minh log và chức năng nghiệp vụ.
6. **Hậu kiểm:** nguyên nhân gốc, timeline, ảnh hưởng, thiếu sót phân quyền và hành động sửa có owner.

### 12.2. Fail-open, fail-closed và degraded mode

- **Fail-closed:** từ chối kết nối khi không thể kiểm chứng quyền. Hạn chế rủi ro truy cập nhưng có thể gián đoạn dịch vụ.
- **Fail-open:** cho phép tiếp tục kết nối khi kiểm soát lỗi. Hỗ trợ sẵn sàng nhưng có thể tạo lỗ hổng; không được mặc nhiên chọn vì “đỡ downtime”.
- **Degraded mode có kiểm soát:** sử dụng policy đã cache, đường dự phòng, vùng cô lập hoặc truy cập giới hạn thời gian và khả năng kiểm toán.

Quyết định phải xuất phát từ threat model, mục tiêu tính sẵn sàng, phân loại dữ liệu và nghĩa vụ vận hành. Đội vận hành cần chạy game day hoặc diễn tập định kỳ; sơ đồ HA chưa chứng minh failover hoạt động.

## 13. Đo hiệu quả và thu bằng chứng ownership

Một control “đã triển khai” chưa đồng nghĩa “đang bảo vệ hiệu quả”. Nên đánh giá bốn chiều: **coverage**, **configuration**, **runtime health** và **operational accountability**.

| Chỉ số | Cách hiểu | Bằng chứng |
| --- | --- | --- |
| Coverage theo asset | Tỷ lệ asset mục tiêu thực sự đi qua enforcement hoặc được áp policy | Inventory asset và kết quả mapping tới control |
| Policy compliance | Tỷ lệ policy/instance tuân thủ baseline đã định | Compliance scan, policy-as-code test, audit record |
| Exception hygiene | Ngoại lệ còn hiệu lực, có owner, có ngày hết hạn | Exception register, approval và auto-expiry |
| Owner completeness | Tỷ lệ control/policy có owner hợp lệ và người dự phòng | CMDB/service catalog, nhóm on-call |
| Telemetry completeness | Tỷ lệ control phát đủ log/trường bắt buộc | Log ingest, parser health, đối chiếu sự kiện |
| Detection effectiveness | Tỷ lệ kịch bản tấn công mô phỏng được phát hiện đúng | Purple-team/red-team test và ground truth |
| Availability/SLO | Uptime, latency, packet drop hoặc SLA phục vụ | Metrics, synthetic checks, incident report |
| Change quality | Tỷ lệ thay đổi thành công, rollback, sự cố do thay đổi | Change record, CI/CD logs, postmortem |
| Recovery readiness | RTO/RPO khả thi, mức hoàn thành diễn tập | DR report, game day evidence, backup restore |

**Ví dụ:** Tổ chức có 120 VPC trong phạm vi bắt buộc inspection, nhưng chỉ 108 VPC có route phù hợp và log đầy đủ. Coverage end-to-end = 108/120 = **90%**. Nếu 12 VPC còn lại chưa onboard, không được âm thầm loại khỏi mẫu số để công bố 100%.

**Owner completeness** có thể đo: số shared control có đầy đủ policy owner, platform owner và incident contact / tổng số shared control thuộc diện phải kiểm kê. Cần báo cả số lượng, mẫu số và ngày chụp snapshot; một tên nhóm không còn trực hoặc mailbox không có người xử lý không phải ownership hiệu quả.

### 13.1. Cách xác minh control được kế thừa

Một application owner muốn tuyên bố ứng dụng được bảo vệ bởi firewall chung cần ít nhất:

1. **Scope:** xác nhận subnet, zone, route hoặc workload thực sự thuộc phạm vi enforcement.
2. **Policy:** xác nhận phiên bản baseline được triển khai và rule không có ngoại lệ rộng không kiểm soát.
3. **Runtime:** kiểm tra thử nghiệm allow/deny trong phạm vi cho phép, bao gồm các đường đi thay thế.
4. **Telemetry:** chứng minh sự kiện kiểm thử xuất hiện ở log/kho giám sát với trường cần thiết.
5. **Ownership:** xác nhận người tiếp nhận thay đổi và sự cố, ngày kiểm tra và phương thức escalations.

Nếu thiếu một bước, phải nêu lỗ hổng bằng chứng thay vì kết luận control không tồn tại hoặc chắc chắn hoạt động.

## 14. Tình huống thiết kế hoàn chỉnh: nhiều ứng dụng cùng dùng egress security

### 14.1. Bài toán

Một tổ chức có ba nhóm:

- **Payments:** kết nối với API đối tác thanh toán qua TLS.
- **Analytics:** tải metadata từ dịch vụ cloud được phê duyệt.
- **Internal tools:** truy cập repository cập nhật phần mềm.

Tất cả dùng dịch vụ egress security chung. Yêu cầu: giới hạn đích truy cập, ghi nhận log, giảm đường kết nối Internet trực tiếp, phân định rõ owner khi cần thay đổi hoặc có sự cố.

### 14.2. Hai phương án kiến trúc

**Phương án A — Gateway egress duy nhất cho toàn bộ workload.**

Ưu điểm: một điểm enforcement, dễ chuẩn hóa rule và giám sát. Nhược điểm: tạo miền lỗi lớn, có thể tăng latency, chi phí truyền dữ liệu, khó đáp ứng đa vùng; yêu cầu routing và dự phòng chặt chẽ.

**Phương án B — Egress gateway theo vùng, policy và telemetry quản lý tập trung.**

Ưu điểm: giảm phụ thuộc datapath xuyên vùng; quy mô và failover linh hoạt hơn; policy dùng chung vẫn được version hóa. Nhược điểm: nhiều instance cần kiểm tra drift, mapping coverage và chuẩn hóa log.

Giả sử hệ thống có nhiều vùng và yêu cầu sẵn sàng cao, chọn **B** với điều kiện nền tảng có khả năng đồng bộ và kiểm chứng chính sách. Đây là quyết định theo giả định của ví dụ, không phải mẫu bắt buộc.

### 14.3. Ownership quyết định

| Phần việc | Owner | Điều kiện hoàn thành |
| --- | --- | --- |
| Chuẩn outbound mặc định | Security Architecture | Baseline đã phê duyệt, có kiểm thử |
| Gateway HA và routing tại mỗi vùng | Network Platform | Có synthetic checks, failover test và on-call |
| Danh mục domain/API theo nghiệp vụ | Mỗi Application owner | Đích có business reason và nguồn/tài sản cụ thể |
| Duyệt ngoại lệ vượt baseline | Risk owner được ủy quyền theo chính sách | Có lý do, bằng chứng, biện pháp bù trừ và expiry |
| Log/alert và quy trình xử lý | SOC phối hợp Network Platform | Sự kiện truy vết được source workload, rule, action |
| Báo cáo coverage và drift | Control owner phối hợp Platform | Tất cả VPC mục tiêu có trạng thái và người phụ trách |

### 14.4. Một thay đổi cụ thể

Nhóm Payments yêu cầu cho workload **payments-worker** kết nối tới endpoint đối tác trên TCP 443.

1. Application owner khai báo source workload, destination định danh, lý do nghiệp vụ, thời hạn và phụ thuộc.
2. Policy pipeline kiểm tra vùng nguồn, phân loại dữ liệu, allowlist đích, tiêu chuẩn TLS, phạm vi thay đổi và quyền của người yêu cầu.
3. Nếu thuộc baseline cho phép, NetPlat áp dụng rule qua pipeline đã được duyệt. Nếu nằm ngoài baseline, request được chuyển sang policy/risk review.
4. Gateway của vùng được cập nhật theo cơ chế triển khai có kiểm soát; ghi lại change ID, policy version và kết quả apply.
5. Application owner kiểm thử kết nối thành công; nhóm kiểm thử kiểm tra một đích không được phép vẫn bị chặn.
6. SOC xác nhận log allow/deny đủ định danh và không tạo cảnh báo sai lệch ngoài kỳ vọng.
7. Quy trình thu hồi rule khi hết nhu cầu được lên lịch, có người chịu trách nhiệm.

### 14.5. Một sự cố

Sau khi cập nhật policy, Payments báo timeout trong khi Analytics vẫn hoạt động.

- **NetPlat** kiểm tra health, routing vùng, log deny, policy version và rollback candidate.
- **Payments** cung cấp thời điểm lỗi, source identity, destination và tác động nghiệp vụ.
- **Security Architecture** đánh giá xem thay đổi policy có làm vô hiệu mục tiêu bảo vệ hay không.
- **SOC** đối chiếu alert và thông tin đe dọa nếu có dấu hiệu bất thường.
- **Incident commander** quyết định cách phối hợp theo mức độ sự cố. Quyền khôi phục thuộc nhóm được ủy quyền trong runbook.

Sau khôi phục, nhóm ghi lại nguyên nhân, cập nhật kiểm thử canary và bổ sung negative tests để lần sau phát hiện việc chặn nhầm trước khi rollout toàn vùng.

## 15. Tài liệu ADR cho quyết định ownership

**Architecture Decision Record (ADR)** giúp ghi lại vì sao một mô hình được chọn, giả định nào có thể thay đổi và trách nhiệm cụ thể. Một ADR cho shared network control có thể theo cấu trúc:

~~~text
ADR-008: Ownership của dịch vụ egress security dùng chung

Status: Accepted
Date: YYYY-MM-DD
Decision owners: Security Architecture + Network Platform
Context:
  - Nhiều workload ở nhiều vùng cần egress protection đồng nhất
  - Yêu cầu HA và telemetry liên vùng
  - Các application team cần tự phục vụ yêu cầu kết nối
Options:
  A. Gateway tập trung toàn tổ chức
  B. Gateway theo vùng, policy tập trung
Decision:
  - Chọn B; policy-as-code áp dụng baseline và guardrails
  - App team sở hữu flow request; Platform triển khai; Security duyệt baseline
  - Ngoại lệ vượt baseline cần phê duyệt risk owner theo quy trình
Consequences:
  - Thêm nhu cầu kiểm tra drift giữa gateway
  - Giảm phụ thuộc vào một datapath chung
Validation:
  - Route coverage, allow/deny tests, log quality, failover drills
Rollback:
  - Trở về policy version được xác nhận tốt và tuyến dự phòng đã thử
Review triggers:
  - Thêm vùng mới, thay đổi nhà cung cấp, SLO breach, incident lớn
~~~

ADR nên liên kết đến service catalog, RACI, threat model, yêu cầu vận hành và bằng chứng kiểm thử. Khi một trong các giả định trọng yếu thay đổi, ví dụ nhu cầu Internet egress tăng gấp nhiều lần hoặc tổ chức chuyển sang kiến trúc multi-cloud, owner phải đánh giá lại quyết định thay vì duy trì mô hình cũ theo quán tính.

## 16. Anti-pattern và cách sửa

### 16.1. “Control là của Security, nên Security làm tất cả”

Hệ quả: Security trở thành điểm nghẽn yêu cầu và không có năng lực vận hành 24/7 cho mọi nền tảng. Cách sửa là chia rõ **policy ownership** và **platform operations**, xác định quyền triển khai, SLO và quy trình escalation.

### 16.2. “Đã có firewall chung nên ứng dụng mặc nhiên an toàn”

Hệ quả: nhóm ứng dụng bỏ qua policy cụ thể, data flow, identity, kiểm soát service-to-service và kiểm thử bypass. Cách sửa là xác định **điều kiện kế thừa control** và trách nhiệm còn lại của workload.

### 16.3. “Mỗi đội mở rule riêng cho nhanh”

Hệ quả: xuất hiện đường kết nối vòng qua inspection, cấu hình không đồng bộ và khó điều tra. Cách sửa là cung cấp API self-service nằm trong guardrail, kiểm soát drift và onboarding tự động.

### 16.4. “Owner là một cá nhân ghi trong bảng tính cũ”

Hệ quả: khi nhân sự nghỉ hoặc đổi nhóm, không ai nhận alert, change request hay review ngoại lệ. Cách sửa là ánh xạ owner tới nhóm duy trì, on-call schedule và người dự phòng; đối chiếu định kỳ với inventory.

### 16.5. “Sẵn sàng cao thì cứ fail-open”

Hệ quả: khi control lỗi, traffic nguy hiểm có thể đi qua mà không được kiểm soát. Cách sửa là phân tích rủi ro, thiết kế HA, degraded mode và kiểm thử outage, có cơ chế chấp thuận rủi ro rõ ràng.

### 16.6. “Báo cáo compliance từ cấu hình là đủ”

Hệ quả: rule tồn tại nhưng route đi vòng; log thiếu; parser lỗi; một phần VPC chưa onboard. Cách sửa là kiểm tra cả cấu hình, datapath, telemetry và khả năng xử lý sự cố với bằng chứng thực nghiệm.

## 17. Bài thực hành kiến trúc

**Đề bài:** Một công ty vận hành hai khu vực cloud, một trung tâm dữ liệu và 12 nhóm ứng dụng. Các nhóm sử dụng chung DNS security, VPN/ZTNA, egress firewall, IDS/NDR và logging. Đội vận hành thường gặp yêu cầu mở kết nối gấp, một số rule đã quá hạn và không rõ ai xử lý khi collector mất log.

**Yêu cầu đầu ra:**

1. Lập danh sách control dùng chung, đối tượng sử dụng, điểm thực thi và giới hạn coverage.
2. Chọn centralized, decentralized hay federated cho mỗi control; giải thích theo rủi ro, độ trễ và khả dụng.
3. Lập RACI tối thiểu cho baseline policy, request kết nối, triển khai, giám sát, xử lý sự cố, chấp nhận ngoại lệ và retest.
4. Viết metadata inventory cho một control, gồm control_id, scope, policy_owner, platform_owner, risk_owner, telemetry và SLO.
5. Thiết kế quy trình request → validation → approval → deployment → evidence → expiry, với một trường hợp vượt guardrail.
6. Đề xuất ba phép thử thực tế: một allow, một deny và một tình huống lỗi telemetry hoặc failover.
7. Mô tả hậu quả nếu một VPC mới chưa được định tuyến qua inspection và cách phát hiện qua coverage scan.
8. Viết một ADR ngắn cho quyết định có ảnh hưởng lớn nhất đến blast radius.

**Tiêu chí chấm:** Rõ vai trò quyết định và thực thi; xác định được ranh giới truy cập; có cơ chế tránh bypass; quyền ngoại lệ có thời hạn; đề cập tính liên tục vận hành và bằng chứng đo được. Một sơ đồ đẹp nhưng không xác định ai chịu trách nhiệm với sự cố không đạt yêu cầu.

## 18. Câu hỏi ôn tập

**1. Một VPC có security group chuẩn nhưng luồng ra Internet đi trực tiếp, không qua egress gateway dùng chung. Có thể tính VPC đó được bảo vệ đầy đủ bởi gateway không?**

Không. Phải kiểm tra đường thực thi thực tế. Security group có thể là control riêng, nhưng không thay thế bằng chứng traffic đi qua egress inspection.

**2. Một team ứng dụng muốn cấp quyền truy cập vĩnh viễn tới subnet quản trị vì đang gặp lỗi triển khai. Ai nên phê duyệt?**

Không thể chấp thuận chỉ dựa trên nhu cầu “triển khai nhanh”. Cần review theo baseline, least privilege, phạm vi tài sản và thời hạn; nếu vượt chính sách thì đưa đến policy owner/risk owner có thẩm quyền để phê duyệt, hoặc chọn biện pháp kỹ thuật an toàn hơn.

**3. SOC phát hiện DNS query nghi vấn nhưng không biết owner của source IP. Đây chỉ là lỗi SOC không?**

Không. Việc mapping IP, identity, asset và owner thuộc nhiều thành phần của nền tảng và quản lý tài sản. Cần xác định RACI cho enrichment và cập nhật inventory, sau đó cải thiện khả năng truy vết của SOC.

**4. Tại sao mô hình federated vẫn cần guardrail tập trung?**

Vì khả năng tự phục vụ không được làm mất tiêu chuẩn tối thiểu hoặc tạo đường bypass giữa các vùng/tenant. Guardrail xác định giới hạn, còn nhóm ứng dụng triển khai policy chi tiết trong giới hạn được phép.

**5. Shared control có SLO 99,9% uptime thì đã đủ chứng minh hiệu lực an ninh mạng chưa?**

Chưa. Uptime không chứng minh policy đúng, đủ coverage, không bypass, alert có chất lượng hay exception được xử lý đúng hạn. Cần kết hợp chỉ số vận hành và kiểm thử hiệu lực bảo mật.

---

## 19. Checklist trước khi đưa shared network control vào vận hành

- [ ] Mục tiêu control và kịch bản rủi ro được mô tả.
- [ ] Phạm vi áp dụng, điểm enforcement, các đường có thể bypass được xác minh.
- [ ] Có control/policy owner, platform owner, risk owner và đầu mối incident cùng người dự phòng.
- [ ] RACI cho thay đổi, ngoại lệ, phản ứng sự cố và recovery đã được xác nhận.
- [ ] Baseline, policy precedence, giới hạn tự phục vụ và quyền quản trị được định nghĩa.
- [ ] Có quy trình request, review, áp dụng, rollback và thu hồi rule.
- [ ] Ngoại lệ có thời hạn, bằng chứng phê duyệt và phương án kiểm tra sau khi hết hạn.
- [ ] Log và telemetry đầy đủ, có các cảnh báo về mất nguồn log.
- [ ] Failover, degraded mode và tác động blast radius đã được kiểm thử.
- [ ] Asset inventory kết nối với control inventory và trạng thái triển khai.
- [ ] Có KPI coverage, drift, compliance, detection và trách nhiệm vận hành.
- [ ] Tài liệu ADR, service catalog, runbook và ngày review tiếp theo đã sẵn sàng.

**Ghi nhớ:** Network control dùng chung hiệu quả khi một tổ chức có thể chỉ ra **kiểm soát nào bảo vệ kết nối nào, chính sách nào đang có hiệu lực, ai có quyền quyết định thay đổi, ai vận hành khi có lỗi và bằng chứng nào chứng minh control hoạt động**. Ownership rõ ràng biến kiến trúc phòng vệ thành hệ thống có thể vận hành, kiểm toán và cải tiến liên tục.
