# Centralized control và distributed control trong kiến trúc bảo mật mạng

## 1. Vì sao đây là một quyết định kiến trúc quan trọng?

Một tổ chức vận hành nhiều chi nhánh, trung tâm dữ liệu và tài khoản cloud cần xác định **ai quyết định chính sách bảo mật** và **thiết bị nào thực thi quyết định đó**. Chẳng hạn, quy tắc “thiết bị chưa tuân thủ không được truy cập mạng quản trị” có thể được đưa ra ở một hệ thống trung tâm, được áp dụng ở từng VPN gateway, firewall hoặc agent và phải tiếp tục hoạt động khi kết nối WAN gián đoạn.

Hai mô hình thiết kế phổ biến là:

- **Centralized control (điều khiển tập trung):** một cơ chế điều phối hoặc tập hợp dịch vụ trung tâm có thẩm quyền xác định, phân phối hay phê duyệt trạng thái/chính sách đối với nhiều thành phần. “Tập trung” có thể là **tập trung về logic** dù dịch vụ chạy trên nhiều node và nhiều vùng dự phòng.
- **Distributed control (điều khiển phân tán):** nhiều thành phần độc lập hoặc bán độc lập tham gia ra quyết định, tính toán hoặc quản lý trạng thái tại các miền mạng; chúng có thể đồng bộ thông tin, phối hợp theo giao thức hay tuân theo một bộ nguyên tắc chung.

Không có mô hình nào luôn an toàn hơn. **Tập trung** giúp thống nhất chính sách và quan sát, nhưng làm tăng mức phụ thuộc và thiệt hại khi đầu mối điều khiển bị chiếm quyền. **Phân tán** có thể tiếp tục vận hành cục bộ khi mất đường trung tâm, nhưng tạo thách thức về nhất quán chính sách, phiên bản, phân quyền và điều tra.

Bài học thuộc chương **Quyết định kiến trúc bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**. Quyết định centralized/distributed control xuất hiện trong phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, xác thực kết nối, zero trust, mạng không dây, cloud networking và mô hình hóa mối đe dọa.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **control plane, management plane, data plane**, và mô hình **policy decision/policy enforcement**.
2. Giải thích sự khác nhau giữa điều khiển tập trung về logic với hệ thống tập trung trên một máy; giữa điều khiển phân tán với thực thi phân tán.
3. Phân tích trade-off về tính nhất quán, latency, availability, blast radius, độ phức tạp và quyền tự chủ của từng vùng.
4. Thiết kế kiến trúc **hybrid** có chính sách chung, thực thi tại chỗ, dự phòng và cơ chế ứng xử khi mất kết nối.
5. Xây dựng ma trận ra quyết định, hồ sơ ADR, phương án triển khai, kiểm thử failure mode và đo hiệu quả.
6. Nhận diện rủi ro từ tài khoản điều khiển đặc quyền, policy propagation, drift, stale policy và split-brain.
7. Đặt tiêu chí kiểm chứng phù hợp cho các hệ thống firewall, VPN/ZTNA, IDS/IPS, cloud, Kubernetes và DNS.

> **Điểm mấu chốt:** Cần phân biệt **nơi hình thành quyết định** với **nơi ra quyết định cuối cùng cho từng yêu cầu** và **nơi chặn/cho phép lưu lượng**. Tập trung quản lý chính sách không nhất thiết buộc toàn bộ gói tin đi qua một điểm trung tâm.

## 2. Thuật ngữ: control, management, data và policy

### 2.1. Ba mặt phẳng trong mạng

| Mặt phẳng | Vai trò | Ví dụ |
|---|---|---|
| **Data plane (forwarding plane)** | Chuyển tiếp, chặn, định tuyến hoặc xử lý lưu lượng thực tế theo trạng thái đã có | Switch ASIC, firewall packet engine, proxy, eBPF datapath |
| **Control plane** | Tính toán và cập nhật trạng thái điều khiển mạng: tuyến đường, adjacency, policy decision hoặc cấu hình forwarding | BGP/OSPF, SDN controller, network policy controller |
| **Management plane** | Quản trị thiết bị, tài khoản, cấu hình, giám sát và điều phối vòng đời | CLI/API, controller UI, GitOps, inventory, AAA, telemetry |

Tùy nền tảng, một chức năng có thể nằm ở ranh giới giữa các mặt phẳng. Ví dụ controller quản lý policy thông qua API (management) rồi tính và phân phối rule (control); firewall áp rule khi xử lý flow (data).

**Không đánh đồng centralized control với hairpin traffic qua trung tâm.** Có thể có một nơi định nghĩa chính sách nhưng hàng trăm node ở edge tự thực thi. Ngược lại, một firewall gateway trung tâm có thể tập trung đường đi của lưu lượng mà hệ thống ra quyết định cấu hình vẫn được phân tán giữa các đội.

### 2.2. Policy Administration, Decision, Enforcement và Information

Trong kiến trúc kiểm soát truy cập, có thể phân công các chức năng:

- **Policy Administration Point (PAP):** nơi tác giả và người quản trị tạo, sửa và phê duyệt policy.
- **Policy Decision Point (PDP):** thành phần đánh giá thuộc tính/yêu cầu và quyết định permit, deny hoặc yêu cầu điều kiện bổ sung.
- **Policy Enforcement Point (PEP):** thành phần thực thi quyết định: firewall, reverse proxy, VPN gateway, service-mesh proxy hay workload agent.
- **Policy Information Point (PIP):** nguồn thuộc tính hỗ trợ quyết định: identity, device posture, asset labels, location, risk signal.

Các chức năng có thể đặt chung hoặc tách rời. Chúng là **vai trò logic**, không bắt buộc tương ứng với một process/máy cụ thể.

Ví dụ: PAP tập trung lưu policy “chỉ nhóm quản trị vào subnet quản lý”; PDP đặt ở controller hoặc từng gateway; PEP là firewall tại chi nhánh. Trường hợp PDP chạy cục bộ không đồng nghĩa PAP cũng phải phân tán.

### 2.3. Những chiều “tập trung/phân tán” khác nhau

Một hệ thống có thể đồng thời:

- Tập trung **việc viết/phê duyệt policy**.
- Phân tán **nơi chạy PDP**.
- Phân tán **nơi chạy PEP**.
- Tập trung **thu nhận audit/telemetry**, nhưng có buffer log cục bộ.
- Tập trung **quản lý danh tính**, với cache/credential ngắn hạn tại site.
- Phân tán **hệ thống dự phòng** nhưng chỉ một leader hợp lệ tại một thời điểm.

Khi mô tả một phương án, hãy nêu rõ **đang tập trung cái gì**; câu “kiến trúc dùng mô hình centralized” mà không chỉ ra chức năng là chưa đủ cho một Architecture Decision Record (ADR).

## 3. Ba mô hình bố trí phổ biến

### 3.1. Centralized control: một quyền điều phối logic

~~~mermaid
flowchart TD
    A["Policy authors / Security governance"] --> P["PAP + Controller logic"]
    P --> R["Policy version, approval, audit"]
    P --> E1["PEP: Firewall site A"]
    P --> E2["PEP: Cloud gateway site B"]
    P --> E3["PEP: Workload agent site C"]
    E1 --> D1["Traffic A được xử lý tại A"]
    E2 --> D2["Traffic B được xử lý tại B"]
    E3 --> D3["Traffic C được xử lý tại C"]
~~~

Một controller trung tâm có thể phát policy tới các node phân tán. **Không cần đưa mọi packet tới controller**: node thực thi rule trong data plane. Controller nên được triển khai HA, kiểm soát phiên bản và phân quyền nghiêm ngặt.

**Ưu điểm:** tạo một nguồn tham chiếu chính sách, giảm lệch tiêu chuẩn, dễ kiểm toán và triển khai thay đổi đồng bộ ở nhiều nơi.

**Rủi ro:** lộ tài khoản controller có thể tác động nhiều site; sự cố control plane hoặc đường WAN có thể ngăn policy update/onboarding; rollout sai đồng loạt có blast radius lớn.

### 3.2. Distributed control: các miền có quyền quyết định

~~~mermaid
flowchart LR
    G["Nguyên tắc chung / Governance"] --> A["Local controller A"]
    G --> B["Local controller B"]
    G --> C["Local controller C"]
    A <--> B
    B <--> C
    A --> EA["PEP site A"]
    B --> EB["PEP site B"]
    C --> EC["PEP site C"]
~~~

Mỗi site hoặc domain có thể duy trì policy/decision state, quyết định trong ranh giới đã được ủy quyền và đồng bộ qua các giao thức hoặc cơ chế quản trị.

**Ưu điểm:** khả năng hoạt động độc lập theo vùng, phản hồi cục bộ nhanh, cô lập sự cố của một controller nếu thiết kế đúng.

**Rủi ro:** drift, xung đột phiên bản, nhất quán khó kiểm chứng, khó thu hồi quyền tức thì trên mọi miền và nhiều đường quản trị phải bảo vệ hơn.

### 3.3. Hybrid: quản trị chung, quyết định hoặc thực thi tại chỗ

~~~mermaid
flowchart TD
    GOV["Central governance / PAP / IAM"] --> V["Signed versioned policy release"]
    V --> C1["Local PDP site A"]
    V --> C2["Local PDP site B"]
    V --> C3["Local PDP cloud region C"]
    C1 --> P1["PEP A"]
    C2 --> P2["PEP B"]
    C3 --> P3["PEP C"]
    P1 --> L1["Local audit buffer"]
    P2 --> L2["Local audit buffer"]
    P3 --> L3["Local audit buffer"]
    L1 --> SIEM["Central SIEM / analytics"]
    L2 --> SIEM
    L3 --> SIEM
~~~

Đây là phương án thường đáng cân nhắc khi mạng nhiều chi nhánh/cloud: **policy intent** có chủ sở hữu chung, còn việc đánh giá thuộc tính hay thực thi được triển khai gần dịch vụ, có cơ chế kiểm tra freshness, đồng bộ, phiên bản và quyền ngoại lệ rõ ràng.

Hybrid không tự loại bỏ mọi rủi ro: nếu policy chung sai và được phát tán rộng, nhiều site vẫn bị ảnh hưởng. Do đó thiết kế rollout theo canary, emergency stop, validation và rollback vẫn cần thiết.

## 4. So sánh trade-off theo đặc tính hệ thống

| Tiêu chí | Control tập trung | Control phân tán | Câu hỏi khi quyết định |
|---|---|---|---|
| Tính nhất quán chính sách | Dễ quản trị nguồn chuẩn; trạng thái trên các PEP vẫn có trễ truyền | Khó hơn khi local owner thay đổi độc lập | Có cần thay đổi có hiệu lực cùng lúc không? |
| Độ trễ quyết định | Có thể cao nếu mỗi yêu cầu phải hỏi PDP ở xa | PDP gần người dùng/workload có thể nhanh hơn | PDP nằm trên critical path của request? |
| Khả năng hoạt động khi mất WAN | Phụ thuộc local cache và fail behavior | Local controller có thể tự tiếp tục nếu thiết kế phù hợp | Site phải chạy độc lập bao lâu? |
| Blast radius lỗi cấu hình | Có thể lớn nếu đẩy policy sai diện rộng | Thường có thể cô lập theo miền; lỗi đồng bộ vẫn lan | Lỗi ở một quyết định có thể ảnh hưởng bao nhiêu site? |
| Blast radius khi compromise | Controller/credential trung tâm là mục tiêu giá trị cao | Nhiều controller/keys, điểm xâm nhập tăng | Ai có quyền sửa policy cho toàn mạng? |
| Audit và compliance | Dễ tổng hợp nguồn phê duyệt; cần kiểm tra thực thi từng site | Chứng cứ phân tán, phải chuẩn hóa collector/timestamp | Có chứng minh toàn bộ PEP đang dùng rule nào? |
| Khả năng mở rộng | Cần phân vùng/HA để không nghẽn controller | Có thể scale theo miền; tăng gánh đồng bộ | Số node, yêu cầu cập nhật và event rate? |
| Vận hành và chi phí | Ít nơi quản trị logic, nhưng controller cần bảo vệ/HA | Tốn điều phối, chuẩn hóa và chuyên gia vùng | Đội vận hành có khả năng quản lý bao nhiêu domain? |
| Quyền tự chủ vùng | Phải thiết kế exceptions/delegation | Phù hợp khi vùng có yêu cầu riêng | Site có quyền tuân thủ địa phương nào? |
| Khắc phục khi sự cố | Thay đổi toàn mạng nhanh nếu controller hoạt động | Có thể xử lý vùng bị ảnh hưởng độc lập | Quyền emergency và quy trình rollback ra sao? |

**Không có điểm số tuyệt đối.** Cần đo/ước lượng trên môi trường thực tế: kiến trúc tập trung logic vẫn có thể phân tán vật lý để HA; kiến trúc phân tán vẫn có thể phụ thuộc một nguồn IAM hoặc DNS chung.

## 5. Điều khiển không đồng nghĩa thực thi

Đây là ranh giới quan trọng nhất khi đưa ra quyết định.

Giả sử có một quy tắc: *Workload nhóm Payments chỉ được kết nối đến cơ sở dữ liệu qua TLS, từ các identity được cấp phép.*

Có ít nhất ba cách:

1. **Trung tâm quyết định từng yêu cầu:** PEP hỏi PDP từ xa khi cần; quyết định có thể phụ thuộc thuộc tính mới nhất nhưng làm tăng độ trễ và nguy cơ khi PDP/WAN không đáp ứng.
2. **Trung tâm phân phối rule, PEP quyết định cục bộ:** bộ rule hoặc policy snapshot được đẩy tới sidecar/firewall; latency thấp, nhưng cần quản lý **độ mới** và cách xử lý khi rule đã quá hạn.
3. **Local authority tự xây rule trong phạm vi ủy quyền:** phù hợp vùng độc lập, nhưng phải ngăn local exception vượt rào chắn bắt buộc toàn tổ chức.

Tách ba câu hỏi:

- **Ai là nguồn chân lý cho intent?**
- **Ai tính quyết định từ intent và thuộc tính hiện tại?**
- **Ai chặn traffic nếu quyết định là deny?**

Nếu không tách, một tài liệu thiết kế có thể vô tình đặt một dịch vụ trung tâm trên mọi request nóng và tạo bottleneck/SPOF, dù chỉ cần đồng bộ policy định kỳ.

### 5.1. Thời điểm quyết định và tính nhất quán

Một PDP cục bộ có thể dùng cache. Khi một người dùng bị thu hồi quyền ở trung tâm, các PDP đã offline có thể chưa biết quyết định mới. Bởi vậy:

- Với **lệnh thay đổi cấu hình đặc quyền** hoặc quyền có rủi ro cao, có thể yêu cầu kiểm tra online hoặc credential rất ngắn hạn.
- Với **kết nối đã được cho phép** và hệ thống yêu cầu khả năng tự vận hành, có thể cho phép dùng last-known-good trong thời gian ngắn có giới hạn, nếu rủi ro được chấp nhận.
- Với **tài sản cực nhạy cảm**, thiếu dữ liệu chứng thực hoặc policy không hợp lệ có thể cần deny mặc định.
- Với **hệ thống an toàn vận hành**, đóng toàn bộ kết nối khi controller mất có thể gây tác hại lớn. Cần thiết kế trạng thái an toàn theo từng loại luồng, không dùng một công thức fail-open/fail-closed cho toàn mạng.

Phải ghi rõ **thời gian hiệu lực, phiên bản, đồng hồ, cơ chế thu hồi và ngoại lệ khẩn cấp**. “Cache giúp HA” là phát biểu thiếu nếu không xác định stale policy được phép tồn tại bao lâu.

## 6. Failure modes: điều gì xảy ra khi control plane lỗi?

### 6.1. Những lỗi cần mô hình hóa

| Sự cố | Centralized control | Distributed/hybrid | Biện pháp đi kèm |
|---|---|---|---|
| WAN tới controller bị đứt | Các PEP có thể tiếp tục rule cũ, hoặc ngừng xin quyết định mới | PDP cục bộ có thể tiếp tục trong giới hạn | LKG, TTL, health checks, quy tắc fail behavior |
| Controller/leader ngừng hoạt động | Nguy cơ update/authorize bị gián đoạn | Miền khác có thể tiếp tục nếu thực sự độc lập | HA, quorum, backup, multi-zone |
| Controller trung tâm bị chiếm quyền | Policy độc hại có thể lan tới mọi site | Quyền tấn công có thể giới hạn theo domain | Least privilege, ký/duyệt policy, canary, audit tách quyền |
| Site controller bị chiếm quyền | Không có bản local nếu hoàn toàn centralized | Có thể ảnh hưởng riêng một vùng, hoặc lan qua federation | Boundary của quyền, key scope, kiểm tra cross-domain |
| Đồng bộ chậm hoặc mất sự kiện | PEP chưa áp rule đã phê duyệt | Các vùng khác nhau về policy | Version/ack, convergence SLO, drift monitoring |
| Split-brain, concurrent write | Nhiều leader có thể phát lệnh xung đột nếu HA sai | Multi-writer có thể tạo rule không tương thích | Consensus/lease/fencing, conflict policy |
| Metadata danh tính lỗi | PDP không đủ thuộc tính để quyết định | Mỗi site có cache identity khác nhau | Freshness, revoke/lease, đánh giá fail behavior |
| Policy phát hành sai | Rollout đồng loạt có thể gây sự cố rộng | Nếu từng site tự chọn, sự cố có thể cục bộ nhưng khó phát hiện | Staging, diff, canary, rollback |
| Mất logging/SIEM | Khó điều tra toàn cục | Local queue có thể giảm mất log, nhưng tiêu hao tài nguyên | Buffer, integrity, retention, backpressure |

Trong mọi trường hợp, cần biết rõ **data plane vẫn đang làm gì**. Một switch có thể tiếp tục chuyển tiếp theo forwarding table khi controller rớt, nhưng các thay đổi tuyến mới hoặc cấp quyền mới có thể không hoạt động. Không thể suy ra hành vi chung chỉ từ nhãn “SDN” hoặc “distributed”.

### 6.2. Fail-open, fail-closed và fail-static

- **Fail-open:** khi không có quyết định, cho phép một số lưu lượng tiếp tục. Tăng availability nhưng có thể nới kiểm soát truy cập.
- **Fail-closed:** khi thiếu điều kiện xác thực/decision, từ chối. Giảm rủi ro truy cập trái phép nhưng có thể gây gián đoạn.
- **Fail-static / last-known-good (LKG):** giữ rule đã kiểm chứng trong một khoảng xác định. Có thể duy trì dịch vụ nhưng phát sinh rủi ro **policy stale** và thu hồi quyền chậm.

Các thuật ngữ có thể khác theo sản phẩm. Trong ADR nên mô tả **hành vi cụ thể**, chẳng hạn:

> Khi kết nối tới PDP trung tâm mất trong 10 phút, các flow đã thiết lập thuộc nhóm dịch vụ A được tiếp tục theo rule đã xác minh; kết nối quản trị mới cần kiểm tra online sẽ bị từ chối; sau khi hết TTL, policy B được áp dụng theo trạng thái khẩn cấp đã phê duyệt.

Con số 10 phút chỉ là **ví dụ minh họa**, không phải tiêu chuẩn an toàn chung. Hành vi cuối phải dựa trên nhu cầu dịch vụ, mức nhạy cảm, luật áp dụng và khả năng kỹ thuật của PEP.

### 6.3. Phân biệt sự cố availability và sự cố integrity

Controller không hoạt động là một kiểu lỗi; controller **hoạt động nhưng trả policy sai hoặc bị chiếm quyền** thường nguy hiểm hơn. Dự phòng HA chỉ giúp availability; nếu tất cả node HA dùng chung credential/đường phát hành bị xâm phạm, chúng có thể cùng phân phối rule độc hại.

Cần tách các biện pháp:

- **Availability:** HA, các vùng dự phòng, queue và khả năng áp rule cục bộ, capacity planning.
- **Integrity:** policy review, tách quyền, release signing/verification khi khả thi, audit, drift detection và rollback.
- **Confidentiality:** bảo mật API/secret và state, bảo vệ management plane, mã hóa các kênh điều khiển.
- **Accountability:** xác thực tác giả/chủ thể triển khai, lưu lịch sử approval và điều tra thay đổi.

## 7. Tính nhất quán và thời gian hội tụ của policy

Trong hệ phân tán, câu hỏi không chỉ là policy đã được phê duyệt hay chưa mà là **bao nhiêu nơi đã áp dụng đúng phiên bản đó**, vào lúc nào và xác nhận bằng cách nào.

Giả sử policy `P42` được phát lúc 09:00 UTC tới 300 firewall/agent. Có thể có node áp dụng ở 09:00:02, node ở 09:00:12 và node offline tới 10:00. Trong cửa sổ này, một kết nối có thể được cho phép ở site A nhưng bị từ chối ở site B.

### 7.1. Desired state và observed state

~~~mermaid
flowchart TD
    A["Author & approve policy version P42"] --> B["Publish signed/validated release"]
    B --> C["Distribute to PEPs / local PDPs"]
    C --> D["Validate syntax, dependency, signature"]
    D --> E{"Can apply safely?"}
    E -->|"Yes"| F["Atomically activate compatible snapshot"]
    E -->|"No"| G["Reject, keep approved LKG, alert"]
    F --> H["Report applied version / result"]
    G --> H
    H --> I["Reconcile desired vs observed"]
    I --> J{"All required nodes within SLO?"}
    J -->|"No"| K["Investigate gaps; pause rollout / rollback"]
    J -->|"Yes"| L["Close change with evidence"]
~~~

Các hệ thống có thể triển khai cơ chế áp rule atomically khác nhau; **không mặc định** một thiết bị bảo đảm all-or-nothing khi thay đổi hàng loạt rule. Trước khi quyết định kiến trúc, cần biết rõ tính chất thực thi của sản phẩm và yêu cầu bảo toàn kết nối.

### 7.2. Các vấn đề phải ghi trong thiết kế

- **Versioning:** policy ID/hash, author, approver, thời điểm phát hành, effective-from, TTL.
- **Acknowledgement:** nhận bản phân phối khác với *đã kích hoạt thành công*. Cần xác minh actual applied version/health.
- **Convergence:** độ trễ giữa thời điểm publish và lúc các PEP quan trọng áp rule mới.
- **Reconciliation:** tự phát hiện khác biệt giữa desired và observed, đặc biệt sau mất mạng/restart.
- **Conflict resolution:** global guardrail với local exception; quy tắc nào thắng khi chồng lấn?
- **Rollback:** quay lại snapshot tương thích, không vô tình phục hồi một rule đã bị thu hồi vì lỗ hổng.
- **Audit:** bản ghi thay đổi không chỉ của controller mà của cả PEP, kèm thời gian và kết quả.
- **Time sync:** NTP/PTP và clock uncertainty khi policy có ngày giờ hiệu lực hoặc cert/token TTL.

Cần định nghĩa mức nhất quán theo **loại quyết định**, không ép toàn bộ thành phần mạng dùng một mức. Thu hồi quyền của một admin bị chiếm có yêu cầu khác với cập nhật một rule phân loại telemetry.

### 7.3. Consistency và availability khi phân vùng mạng

Khi controller/site bị ngăn bởi network partition, hệ thống không thể tự có cả truy cập không hạn chế vào state mới nhất và khả năng trả quyết định đầy đủ trong mọi trường hợp. Thiết kế phải chỉ rõ ưu tiên:

- Giữ **quyết định đã xác minh cục bộ**, chấp nhận trạng thái có thể cũ.
- Từ chối **quyết định mới** cần thông tin trung tâm chưa đồng bộ.
- Cho phép **chế độ vận hành khẩn cấp được phê duyệt** cho một số luồng thiết yếu.
- Chờ khôi phục liên lạc rồi reconcile theo policy/version ưu tiên.

Không nên giản lược thành “distributed luôn có availability” hoặc “centralized luôn nhất quán”. HA, quorum, lease, chất lượng mạng và cấu trúc truy cập dữ liệu quyết định hành vi thực tế.

## 8. Ranh giới tin cậy và threat model của control plane

Control plane là **high-value target**: chiếm quyền viết policy có thể tương đương mở đường truy cập vào nhiều tài sản cùng lúc.

### 8.1. Tài sản cần bảo vệ

- Policy repository, approval record và workflow phát hành.
- Controller API, service accounts, authentication tokens, khóa ký và chứng chỉ mTLS.
- Kênh phân phối rule tới firewall, SDN switch, agent hoặc proxy.
- State và credential từ IAM/IdP, device posture, CMDB, cloud metadata.
- Local cache, bootstrap config và emergency override.
- Log audit/config diff/telemetry phục vụ phát hiện và điều tra.

### 8.2. Các hướng tấn công cần phân tích

| Threat scenario | Điểm yếu có thể có | Kiểm soát phù hợp |
|---|---|---|
| Credential controller bị lộ | Shared admin, token dài hạn, thiếu MFA | SSO/MFA, scoped service identity, JIT/PAM, rotate/revoke |
| Kẻ tấn công chèn policy độc hại | API write rộng quyền, không review | RBAC, approval, schema validation, policy tests, audit |
| Giả mạo node nhận policy | Thiếu xác thực hai chiều | mTLS/host identity, device attestation khi hỗ trợ |
| Thay gói policy trên đường | Transport hoặc signing yếu | TLS được xác minh, checksum/signature, version binding |
| Local site cố vượt rào chắn | Quyền exception quá rộng | Global invariant, policy hierarchy, quyền viết hạn chế |
| Replay policy cũ | Không có anti-rollback/version gate | Monotonic revision/lease, expiry, revocation channel |
| Controller overload/DoS | PDP nằm trên mọi request, thiếu limit | Cache, capacity, rate limit, HA, circuit breaker |
| Log bị thay hoặc không gửi | Cùng quyền admin điều khiển cả log | Remote audit, tách quyền, integrity, local buffer |
| Federation trust bị lợi dụng | Controller A được tin vô điều kiện ở B | Trust boundary, phân scope identity và policy |
| Bootstrap mặc định yếu | Shared bootstrap secret, không rotate | Onboarding an toàn, short-lived enrollment, secret vault |

**Zero trust** không đồng nghĩa bắt buộc một PDP trung tâm kiểm tra từng packet. Triết lý này nhấn mạnh kiểm tra danh tính/bối cảnh, hạn chế đặc quyền, không tin mặc định dựa trên vị trí mạng và giám sát liên tục theo khả năng kỹ thuật. Cách đặt PDP/PEP có thể kết hợp tập trung và phân tán.

### 8.3. Phân quyền giữa policy author và operator

Một số cấu hình cần người viết và người phê duyệt độc lập; một số thay đổi khẩn được xử lý theo quy trình riêng, có audit sau. Quy tắc nên trả lời:

- Ai được đề xuất rule, ai được duyệt, ai được phát hành toàn mạng?
- Ai được sửa only-local exception và giới hạn của exception là gì?
- Ai có quyền tạo service account/controller key, ai có thể thu hồi?
- Có thể phân chia cấp trung tâm, site, ứng dụng, tenant và read-only auditor không?
- Nếu identity provider down, thiết bị còn được phép làm gì và trong bao lâu?

Đây là vấn đề **organizational design** đồng thời là vấn đề protocol/software.

## 9. Những ứng dụng thực tế trong bảo mật mạng

### 9.1. Firewall policy và segmentation

**Tập trung:** tổ chức định nghĩa network policy intent và quản lý qua firewall manager, có quy trình review, export baseline và phát hành theo nhóm.

**Phân tán:** nhiều firewall site tự thực thi; site có thể có local emergency rule trong ranh giới đã cho phép.

**Quyết định khó:** global policy có ưu tiên hơn local exception không? Làm sao ngăn một rule rộng ở trung tâm mở truy cập trái phép giữa các VLAN/VRF? Nếu firewall offline, nó tiếp tục dùng bản policy nào?

**Cần kiểm thử:** đường user→management bị deny; app→DB theo đúng cổng; IPv4 và IPv6; NAT/route/overlay; kiểm tra allow/deny từ nhiều source zone.

### 9.2. SDN và controller

Trong nhiều kiến trúc SDN, việc lập trình mạng được điều phối bởi một control plane logic tập trung; nhưng controller cluster có thể phân tán vật lý và các forwarding devices vẫn thực hiện xử lý packet cục bộ.

Các điều cần thiết kế:

- HA cluster, leader/quorum, failure domains và recovery time.
- Bảo mật southbound API, TLS/mTLS và quyền thay đổi flow table.
- Giới hạn ảnh hưởng nếu controller bị compromise hoặc policy sai.
- Hành vi khi controller bị mất: forwarding state hiện tại, expiration của flow, fail-safe rule và kết nối mới.
- Giám sát bảng flow và drift giữa desired/applied state.

Không nên suy luận hành vi “controller chết thì mạng ngừng” hoặc “vẫn hoạt động hoàn toàn” khi chưa xem thiết kế sản phẩm, TTL flow và khả năng cục bộ.

### 9.3. Identity, VPN và ZTNA

**PAP/identity tập trung** có thể giữ quyền tổ chức, nhóm người dùng, thiết bị đáng tin và policy theo ứng dụng. **PEP phân tán** ở các VPN concentrator/ZTNA connector gần site.

Đối với truy cập đặc quyền, thường cần thu hồi nhanh và xác minh online hoặc token ngắn hạn. Đối với một số traffic có tính sẵn sàng cao, có thể duy trì phiên đã cấp và bị giám sát trong phạm vi ngắn khi mất IdP, theo policy rủi ro đã duyệt.

Cần phân biệt:

- Mất kết nối tới **IdP/PDP** có ngăn phiên mới, phiên hiện tại hay cả hai?
- Thu hồi user sau khi offboarding tới tất cả site trong bao lâu?
- Credential cache có hạn, được mã hóa và audit không?
- VPN/ZTNA có mặc định cho phép truy cập mọi segment sau authentication không? (Không nên.)

### 9.4. IDS/IPS và NDR

**Phát hiện tập trung:** SIEM/analytics lấy alert từ nhiều cảm biến và dùng ngữ cảnh liên vùng; thuận tiện correlation và săn tìm mối đe dọa.

**Phát hiện/phòng ngừa phân tán:** IPS/NDR sensors đặt ở site/segment xử lý lưu lượng tại chỗ; không cần đưa toàn bộ PCAP qua WAN. Có thể chia sẻ signatures và rule qua manager trung tâm.

Quyết định cần tách:

- Trả alert/log về trung tâm **khác** với bắt buộc mọi traffic đi qua một sensor.
- Một signature sai nếu được đẩy đồng loạt có thể chặn traffic hợp lệ ở nhiều site.
- Site mất WAN cần khả năng tiếp tục chặn theo local rules nhưng có thể thiếu cập nhật IOC.
- Cần buffer log, kiểm tra tính nguyên vẹn, retention và cảnh báo mất telemetry.
- Phân phối signature nên có canary/rollback, loại bỏ exception lỗi thời.

### 9.5. DNS security

Một tổ chức có thể có **chính sách lọc DNS tập trung** (domain/category/threat feed) nhưng resolver thực thi ở từng site hoặc vùng cloud.

Trade-off quan trọng: latency DNS, caching, DNSSEC validation khi áp dụng, split-horizon, stale blocklists, DoH/DoT ngoài resolver được quản lý và hoạt động khi WAN mất. Khi blocklist không cập nhật, cần rule cục bộ, thời hạn hiệu lực và mức rủi ro chấp nhận. Việc cưỡng bức đưa mọi query qua resolver xa có thể làm tăng độ trễ hoặc tạo điểm nghẽn.

### 9.6. Wi-Fi, NAC và điều khiển truy cập kết nối

Wireless controller/NAC tập trung có thể cấp policy SSID/VLAN/role, còn AP/switch thực thi 802.1X, dynamic VLAN hoặc ACL tùy nền tảng.

Điều cần đánh giá:

- Khi controller hoặc RADIUS/AAA không sẵn sàng, client mới có được xác thực không?
- Client đã kết nối sẽ tiếp tục trong bao lâu? Có cơ chế fallback an toàn cho thiết bị đặc biệt không?
- Site có cần offline survivability, local authentication hoặc cached authorization không?
- Một thay đổi role mapping có thể gây gián đoạn diện rộng hay không?

Không giả định tất cả AP hoạt động giống nhau; các đặc tính phụ thuộc chế độ controller, firmware và AAA implementation.

### 9.7. Cloud networking và Kubernetes

Trong cloud, policy intent có thể được quản lý tập trung qua IaC/GitOps và organization guardrails, nhưng được thực thi ở nhiều VPC/VNet, security groups, gateway và workload.

Trong Kubernetes, một control plane có thể phân phối **NetworkPolicy** tới các node; enforcement tùy network plugin/CNI và khả năng của nền tảng. Cùng một tên NetworkPolicy không bảo đảm mọi loại traffic hoặc egress được xử lý như nhau nếu plugin, route hay host networking khác nhau.

Các câu hỏi cần trả lời: policy version đã áp ở node nào, label động được cập nhật thế nào, service mesh và network policy chồng lấn ra sao, cluster bị tách khỏi GitOps/controller thì giữ trạng thái gì, ai có quyền sửa namespace ngoại lệ?

## 10. Ra quyết định bằng yêu cầu phi chức năng và rủi ro

Không nên bắt đầu bằng “công nghệ nào phổ biến” mà bằng câu hỏi: **điều gì cần đúng khi hệ thống hoạt động và khi nó hỏng?**

### 10.1. Các chiều cần đo

| Tiêu chí | Định nghĩa kiểm chứng được |
|---|---|
| **Latency decision** | p95/p99 thời gian cho phép/từ chối yêu cầu khi PDP online/offline |
| **Policy propagation SLO** | Tỷ lệ PEP áp bản policy mục tiêu trong một khoảng thời gian |
| **Availability** | Khả năng duy trì luồng được phép và chặn luồng không hợp lệ khi controller/WAN lỗi |
| **RTO** | Thời gian khôi phục điều khiển/phân phối policy sau một sự cố |
| **RPO** | Lượng trạng thái/quản trị thay đổi chấp nhận mất khi khôi phục, nếu có |
| **Revocation delay** | Thời gian tối đa từ quyết định thu hồi đến các PEP liên quan không còn cho phép |
| **Blast radius** | Số site/tài sản/flow có thể bị ảnh hưởng bởi một policy/config/credential lỗi |
| **Audit completeness** | Tỷ lệ node báo applied version, change actor, kết quả và timestamp |
| **Operational autonomy** | Site phải tiếp tục nhiệm vụ quan trọng trong bao lâu nếu WAN/central mất |
| **Complexity/cost** | Chi phí HA, controller, vận hành domain, đào tạo và kiểm soát drift |

Không tự đưa giá trị `five nines` hoặc “policy hội tụ trong 1 giây” vào thiết kế mà chưa có khả năng đo và xác nhận. SLO phải gắn workload, số node, vùng mạng, điểm đo và điều kiện lỗi cụ thể.

### 10.2. Mẫu ma trận đánh giá có trọng số

Ví dụ **chỉ để minh họa phương pháp**, không phải kết quả thực nghiệm:

| Tiêu chí | Trọng số ví dụ | Tập trung | Phân tán | Hybrid |
|---|---:|---:|---:|---:|
| Quản trị thống nhất | 25% | 5 | 2 | 4 |
| Site sống được khi mất WAN | 25% | 2 | 5 | 4 |
| Cô lập lỗi cấu hình | 20% | 2 | 4 | 4 |
| Thu hồi quyền nhanh | 15% | 4 | 2 | 4 |
| Độ phức tạp vận hành thấp | 15% | 4 | 2 | 3 |

Thang điểm ví dụ từ **1 (kém phù hợp) đến 5 (phù hợp)**. Điểm số do nhóm thiết kế thảo luận và phải dựa trên **dữ liệu thực tế**, không mặc định các số trong bảng là sự thật về mọi sản phẩm. Đặc biệt, central controller HA có local cache có thể có mức survivability cao hơn central PDP online-only; hybrid có thể phức tạp hơn một số mô hình phân tán.

Ví dụ công thức (nếu điểm và trọng số đã được chấp thuận):

\[
\text{Weighted score} = \sum_i \text{Weight}_i \times \text{Rating}_i
\]

Cách chấm chỉ hỗ trợ ưu tiên thảo luận. Với yêu cầu **bắt buộc** như giữ quyền truy cập mạng trong điều kiện an toàn hoặc bảo vệ dữ liệu, phương án không đáp ứng phải bị loại bất kể điểm tổng cao.

### 10.3. Câu hỏi quyết định về thời gian thực

Một ứng dụng có 100.000 yêu cầu/giây không nên tự động gọi một PDP cách hàng trăm mili giây cho *mỗi packet* chỉ vì chính sách được quản trị tập trung. Nhưng điều đó không có nghĩa PDP cục bộ phù hợp với mọi quyết định: một lệnh cấu hình firewall đặc quyền có thể chấp nhận chờ xác minh online.

Tách:

- **Per-packet enforcement:** thiết kế gần data plane, cực nhạy latency.
- **Per-session/per-request authorization:** có thể dùng local PDP/cache hoặc gọi online theo rủi ro và ngân sách latency.
- **Policy deployment:** diễn ra theo sự kiện hoặc vòng điều phối, cần kiểm soát consistency, approval và rollback.
- **Emergency revocation:** có thể cần đường phát cảnh báo/thu hồi ưu tiên và lease rất ngắn.

Mỗi loại có cơ chế thất bại và SLO khác nhau.

## 11. Thiết kế hybrid có guardrails và quyền tự chủ cục bộ

Một mẫu thường hữu ích: **central intent + local execution + bounded autonomy**.

### 11.1. Thành phần đề xuất

1. **PAP/policy repository trung tâm:** có phiên bản, code review, tách người duyệt/phát hành và audit; xác định rào chắn toàn tổ chức.
2. **Release controller:** kiểm tra schema, tính tương thích, quy tắc ưu tiên; phát hành theo canary và có rollback.
3. **Local PDP hoặc rule compiler:** nhận policy version, xác minh nguồn, áp dụng ràng buộc tại site, từ chối bản lỗi hoặc quá cũ khi cần.
4. **PEP cục bộ:** firewall, sidecar, gateway, agent; không phụ thuộc network RTT để xử lý mỗi packet.
5. **Identity/attribute sources:** có trust, TTL và giới hạn cache; cập nhật revocation qua kênh đã định.
6. **Telemetry và reconciliation:** applied version, policy hash, drift, denied/allowed flow, latency, health.
7. **Emergency channel:** đường quản lý OOB, quyền break-glass có thời hạn, kiểm toán và ràng buộc phạm vi.

### 11.2. Phân cấp chính sách

Một thiết kế có thể chia:

- **Global mandatory guardrails:** không được cho phép một số luồng, luôn mã hóa traffic quản trị, không mở port nhạy cảm ra Internet.
- **Regional policy:** phù hợp quy định dữ liệu, ISP/site topology và yêu cầu khu vực nhưng không làm yếu guardrails.
- **Application/team policy:** cho phép workload access trong giới hạn đã duyệt.
- **Emergency exception:** có owner, lý do, phạm vi nhỏ, thời hạn, phê duyệt và hậu kiểm.

Quy tắc ưu tiên nên rõ ràng. Ví dụ **deny của mandatory guardrail luôn thắng allow của local policy**; nhưng cần kiểm thử xung đột giữa các lớp, bao gồm exception có hiệu lực, rule ordering và cách thiết bị hiện thực hóa chính sách.

### 11.3. Ví dụ bản mô tả policy (không chạy trực tiếp)

~~~yaml
policy_release:
  id: "network-security-P42"
  created_at_utc: "2026-11-28T09:00:00Z"
  approved_by_role: "security-architecture"
  global_guardrails:
    - "deny direct user-zone to management-zone"
    - "require encrypted administrative channels"
  local_delegation:
    allowed:
      - "allow app-to-db on approved ports within owned site"
    forbidden:
      - "override global mandatory guardrails"
  delivery:
    rollout: "canary-then-waves"
    require_approved_source: true
    verify_release_signature: true
  local_runtime:
    keep_last_verified_snapshot: true
    # Giá trị dưới là giả định học tập, không phải khuyến nghị chung.
    max_stale_minutes: 15
    deny_new_privileged_sessions_when_stale: true
  assurance:
    report_applied_version: true
    report_policy_hash: true
    alert_on_drift: true
    protect_audit_log: true
~~~

Đây là **mô hình logic** minh họa chứ không phải cú pháp của firewall, CNI hay controller cụ thể. Tính năng ký policy, TTL, rollback, atomic apply và quyền local override phải được xác nhận với sản phẩm trước khi đưa vào ADR.

Không tự mặc định “stale 15 phút” an toàn. Một số quyền nguy hiểm cần thời gian ngắn hơn đáng kể; một số site quan trọng cần kịch bản offline riêng và kiểm soát bù trừ.

## 12. Kiến trúc HA và xử lý split-brain

**Centralized về logic** không có nghĩa một máy chủ. Có thể triển khai nhiều replica của controller/API qua nhiều availability zone. Tuy nhiên, HA cần làm rõ:

- Nhiều replica được phép **đọc/ghi đồng thời** hay chỉ một leader được viết?
- Các node biết ai là leader hiện tại như thế nào? Có quorum/lease/fencing tránh split-brain?
- Khi vùng mạng bị chia đôi, mỗi bên có được chấp nhận thay đổi policy mới không?
- Một thay đổi đang triển khai nửa chừng được xử lý ra sao?
- Certificate/secret rotation được thực hiện như thế nào khi các replica mất liên lạc?
- Audit log nào là nguồn có thẩm quyền trong trường hợp sự kiện bị trùng/sai thứ tự?
- Chính sách rollback ngăn replay phiên bản đã bị thu hồi vì lý do an ninh ra sao?

**Quorum** có thể ngăn hai nhóm node cùng nghĩ mình được phép ghi, nhưng nếu thiếu quorum thì một phần hệ thống có thể không chấp nhận thay đổi mới. Điều này cần được phản ánh rõ trong tiêu chí availability: *điều khiển thay đổi có thể gián đoạn trong khi PEP vẫn tiếp tục thực thi rule đã có*.

### 12.1. Disaster recovery không chỉ là khôi phục controller

Khả năng phục hồi còn phụ thuộc:

- Backup policy repository, secret/CA, schema và quyền truy cập đúng.
- Các PEP có thể xác minh bản policy và tin certificate mới sau DR không.
- DNS, NTP, IAM, VPN, mạng quản trị và route tới controller có phục hồi theo thứ tự đúng không.
- RTO/RPO của **quyền phát hành policy mới** khác RTO của **traffic được bảo vệ**.
- Việc chuyển sang controller dự phòng có làm phân phối đồng loạt policy chưa được kiểm tra không.

Nên có diễn tập DR gắn cả kiểm tra data-plane traffic, audit log và quyền admin, không chỉ kiểm tra trang UI controller hiện lên.

## 13. Triển khai thay đổi theo pha để giảm blast radius

Một phương án dù tốt trên sơ đồ vẫn có thể gây outage vì cách rollout. Quy trình triển khai nên:

~~~mermaid
flowchart TD
    A["Define requirements, threat model, ADR"] --> B["Inventory PEP, identities, policy dependencies"]
    B --> C["Lab: validate precedence + failure behavior"]
    C --> D["Canary low-risk site"]
    D --> E{"Health, deny/allow, audit đạt ngưỡng?"}
    E -->|"No"| F["Pause, rollback, investigate"]
    F --> C
    E -->|"Yes"| G["Wave rollout by failure domain"]
    G --> H["Check applied version + drift"]
    H --> I{"All critical paths pass?"}
    I -->|"No"| F
    I -->|"Yes"| J["Operational handover + continuous monitoring"]
~~~

### 13.1. Trước rollout

- Kiểm kê các controller, PEP, service owners, site, network paths và các đường quản trị ngoài băng.
- Thu baseline cấu hình và kiểm tra traffic hợp lệ từ các zone: VPN→app, app→DB, user→management (deny), DNS resolver, cloud egress, IDS/IPS telemetry.
- Xác định các rào chắn không được nới lỏng dù đang rollback.
- Kiểm tra controller HA, IAM, certificate, policy signing/validation và chế độ offline.
- Thiết lập SLO cho propagation, revocation và hiệu quả logging.
- Có change approval, contact, cửa sổ, stop condition, kế hoạch rollback và quyền khôi phục.

### 13.2. Trong rollout

- Dùng canary/waves theo **failure domain**: từng site, region, tenant, nhóm workload; không triển khai tất cả cùng lúc chỉ vì controller cho phép.
- Quan sát allow/deny, error rate, CPU của firewall/agent, latency, session drops, propagation lag, applied policy version và drift.
- Kiểm tra nhiều nguồn: management VLAN, user VLAN, VPN, cloud VPC, IPv4/IPv6.
- Nếu một PEP báo nhận bản mới nhưng chưa áp hoặc rollback một phần, không đánh dấu hoàn tất.
- Tạm dừng khi phát hiện traffic hợp lệ bị chặn, đường quản trị bị khóa, xuất hiện permit ngoài policy hoặc audit mất hiệu lực.

### 13.3. Sau rollout

- Thu config diff, hash/version, lịch sử ai duyệt/phát hành và xác nhận của asset owner.
- Thử chế độ WAN partition/IdP outage theo kế hoạch có kiểm soát.
- Dọn exception tạm, token/controller credentials không còn cần và những phiên bản có rủi ro.
- Đánh giá drift định kỳ và phân loại findings theo mức ảnh hưởng.

## 14. Kiểm thử failure mode và phương pháp quan sát

Các phép thử sự cố phải diễn ra trên lab/staging hoặc production **đã được duyệt** với phương án dừng và khôi phục. Không tự tắt controller hoặc ngắt WAN thật để chứng minh thiết kế nếu chưa có authorization.

| Bài kiểm thử | Mục tiêu | Bằng chứng cần thu |
|---|---|---|
| Mất kết nối site→controller | Kiểm tra local decisions, TTL và data-plane survival | Policy version, connection outcome, logs, time to recovery |
| Một replica/controller ngừng | Đánh giá HA/leader election | Thời gian failover, API errors, split-brain alert |
| Policy sai ở canary | Kiểm tra rollback và blast radius | Số PEP bị ảnh hưởng, phát hiện, thời gian rollback |
| Thu hồi user/token | Đo revocation propagation | Mốc revoke, PDP/PEP outcome và sai số clock |
| PEP khởi động lại khi offline | Kiểm tra bootstrap/last-known-good và trust | Rule version được load, verify thành công/thất bại |
| Local policy xung đột global deny | Kiểm tra thứ tự ưu tiên | Kết quả allow/deny, applied configuration |
| Controller bị mô phỏng mất quyền/khóa | Kiểm tra khôi phục định danh/secret | Revocation, rotate, logs, không nhận policy giả |
| SIEM collector unreachable | Kiểm tra local buffering và integrity | Queue depth, log loss, restore/replay đúng |
| NTP hoặc certificate lỗi | Kiểm tra fail behavior và alarm | Thông báo, quyết định được phép/từ chối, phục hồi |
| Site phát policy cũ | Kiểm tra anti-rollback và stale handling | Rejection log, release version, vận hành an toàn |

**Kết quả của một nguồn không đủ** để khẳng định “tất cả site áp đúng”. Kết hợp trạng thái trực tiếp trên PEP, logs, config hash và traffic thử end-to-end. Ghi vị trí sensor, timestamp UTC, network topology và những data gaps.

### 14.1. Các metric đáng theo dõi

~~~text
Policy propagation lag:
  applied_at_utc(PEP) - published_at_utc(release)

Convergence coverage:
  số PEP bắt buộc đã áp đúng version / tổng PEP bắt buộc

Policy drift rate:
  số PEP có actual config khác desired / tổng PEP kiểm tra

Revocation latency:
  thời gian từ revoke đã ghi nhận -> deny được xác nhận trên PEP

Control-plane availability:
  tỷ lệ thời gian API/PDP đáp ứng theo SLO đã định nghĩa

Protected service availability:
  tỷ lệ thời gian dịch vụ hợp lệ duy trì được kết nối theo SLO riêng
~~~

Không gộp hai availability cuối làm một. Controller hoạt động 100% không đồng nghĩa service không bị block sai; controller tạm ngừng không đồng nghĩa mọi session ngưng nếu PEP có thể tiếp tục rule đã xác minh.

Ngoài trung bình, dùng p95/p99 propagation và phân tách theo region/site/firmware/plugin version, đặc biệt với site xa hoặc đường truyền kém.

## 15. Ví dụ ADR: chính sách mạng cho tổ chức nhiều chi nhánh

### 15.1. Bối cảnh

Giả sử một tổ chức có 30 chi nhánh, hai vùng cloud và một nhóm ứng dụng trọng yếu. Mỗi site có firewall riêng, hệ thống VPN cho người quản trị và DNS resolver địa phương. Công ty cần kiểm soát truy cập nhất quán, xử lý incident nhanh nhưng một số chi nhánh thường mất kết nối WAN ngắn.

Nhóm thiết kế cân nhắc:

- **A — PDP hoàn toàn trung tâm:** mọi quyết định quan trọng phụ thuộc liên lạc tới dịch vụ trung tâm.
- **B — Điều khiển độc lập từng site:** mỗi chi nhánh tự quản rule, phải đồng bộ thủ công/qua federation.
- **C — Policy intent trung tâm + local PDP/PEP:** version policy chung, local enforcement và ngoại lệ giới hạn, audit trung tâm với buffer cục bộ.

Các con số của ví dụ là giả định học tập, không phải mô tả hệ thống thực.

### 15.2. Yêu cầu và ràng buộc

- Cấm truy cập trực tiếp từ user zone tới management zone ở mọi chi nhánh.
- VPN admin phải được xác thực mạnh, quyền có thể thu hồi theo quy định tổ chức.
- Mất WAN không được làm ngừng traffic nội bộ thiết yếu đã được cấp quyền, nhưng không được biến thành mở rộng truy cập mặc định.
- Global policy phải có approval, version/rollback và có khả năng chứng minh applied state.
- Các thay đổi có blast radius lớn phải được rollout theo đợt.
- Log phải phục vụ điều tra sự cố mạng, có timestamp và giới hạn retention phù hợp.

### 15.3. Lý do lựa chọn

**A** có thuận lợi về governance nhưng mỗi quyết định online từ xa có thể bị ảnh hưởng latency/WAN; nếu xây local cache thì thực tế đã đưa một phần quyết định xuống site.

**B** đáp ứng quyền tự chủ vùng nhưng dễ drift và khó thu hồi quyền/phê duyệt đồng nhất khi nhân sự và firmware mỗi site khác nhau.

**C** cho phép kiểm soát intent tại một nơi, **PEP ở từng site** không phải đưa traffic về trung tâm, local PDP có thể tiếp tục theo policy đã được xác minh khi offline, với giới hạn TTL và deny cho quyền đặc quyền mới khi không có xác thực phù hợp.

**Quyết định minh họa:** chọn **C**, với điều kiện kiểm chứng được convergence, emergency revocation, global deny precedence, audit và WAN failure behavior. Đây không phải đề xuất mặc định cho mọi mạng.

### 15.4. Đánh đổi được chấp nhận

- Chấp nhận **độ phức tạp** của cache, reconciliation và rollback để tăng site survivability.
- Chấp nhận một **khoảng policy stale có giới hạn** cho luồng không đặc quyền, nhưng không tự áp dụng tương tự cho quyền admin.
- Chấp nhận local exception **chỉ trong phạm vi được ủy quyền**, có TTL và review.
- Yêu cầu bảo vệ policy publisher, signing keys và IAM trung tâm như tài sản đặc quyền cao.
- Yêu cầu HA/quorum và khả năng chứng minh không xuất hiện hai writer cùng hợp lệ khi partition.

### 15.5. Điều kiện kiểm chứng trước khi phê duyệt triển khai

1. Canary áp bản P42, các PEP ghi chính xác applied version; traffic hợp lệ/deny đúng.
2. Mô phỏng site offline trong lab: luồng đã được phép tồn tại trong ngưỡng đã chọn, admin session mới cần xác minh bị xử lý đúng policy.
3. Thu hồi test user: đo khoảng thời gian tất cả PEP liên quan thực sự từ chối theo giới hạn mục tiêu.
4. Local override không thể cho phép truy cập bị global guardrail deny.
5. Một policy lỗi tại canary kích hoạt stop/rollback trước khi lan diện rộng.
6. Khôi phục controller dự phòng không làm mất audit hoặc đẩy lại policy không hợp lệ.
7. Mỗi site có owner, runbook, OOB và bằng chứng phục hồi.

## 16. Mẫu Architecture Decision Record (ADR) dùng được

~~~markdown
# ADR-SEC-NET-004 — Centralized vs Distributed Control

## Trạng thái
Proposed / Accepted / Superseded
Ngày và người phê duyệt:

## Context / Problem
- Mục tiêu bảo mật và nhu cầu kinh doanh:
- Các failure domains, site, cloud regions:
- Data plane, control plane, management plane hiện tại:
- Vấn đề: drift / outage / latency / privilege concentration:
- Các giả định và dữ liệu còn thiếu:

## Decision drivers
- Chính sách bắt buộc / compliance:
- SLO: policy propagation, revocation, availability, RTO:
- Phạm vi quyền tự chủ cục bộ và offline behavior:
- Khả năng vận hành, chi phí, blast radius:

## Options considered
1. Central PDP / controller:
2. Distributed local controllers:
3. Hybrid global intent + local PDP/PEP:

## Decision
- Phương án được chọn:
- PAP/PDP/PIP/PEP ở đâu?
- Authority hierarchy và local exception:
- Fail-open/fail-closed/LKG theo loại request:
- Policy version, TTL, rollout/rollback, HA và audit:
- Owner của global/local policy:

## Consequences
- Lợi ích:
- Rủi ro mới và điều kiện bù trừ:
- Quyền đặc biệt / key management:
- Giới hạn khi partition, identity outage hoặc policy stale:

## Validation
- Canary và acceptance criteria:
- Fault injection / DR test được duyệt:
- Các bằng chứng phải thu:
- Người phê duyệt go/no-go và lịch review:

## Follow-up action items
- Action, owner, deadline, verification, evidence link:
~~~

Mẫu cần điền dựa trên hiện trạng tổ chức; không sử dụng làm văn bản phê duyệt nếu các giá trị về quyền, SLO, rủi ro và điều kiện dừng còn trống.

## 17. Governance, audit và phân định trách nhiệm

Dù điều khiển tập trung hay phân tán, **policy ownership** phải rõ ràng:

| Hoạt động | Vai trò chịu trách nhiệm chính | Kiểm soát |
|---|---|---|
| Global policy intent | Security architecture / governance | Version, review, approval, mandatory guardrails |
| Policy vận hành tại site | Site/network operations | Quyền giới hạn, local audit, exception expiry |
| Phát hành và phân phối | Platform/controller operations | Signed release khi có, canary, health, rollback |
| Danh tính/thu hồi quyền | IAM/security identity owner | MFA, scoped credentials, revocation, audit |
| PEP và local PDP | Workload/site owner | Applied version, device health, drift, logs |
| SOC/Incident Response | Detection/response team | Monitor, correlate, triage và điều phối containment |
| Risk acceptance | Chủ rủi ro có thẩm quyền | Quyết định có hạn, lý do và đánh giá lại |
| Internal audit | Auditor độc lập theo chính sách | Kiểm tra nguồn phê duyệt vs trạng thái thực tế |

### 17.1. Ngoại lệ và rủi ro tồn đọng

Nếu một chi nhánh cần cho phép đường truy cập đặc biệt trong một tuần, cần ghi:

- Business reason, owner, đối tượng/đích/cổng cụ thể.
- Vì sao global policy không đáp ứng; đã xem phương án ít quyền hơn chưa?
- Phê duyệt có thẩm quyền, hiệu lực, thời hạn tự hết hạn và điều kiện thu hồi.
- Giám sát bổ sung và bằng chứng kiểm tra traffic.
- Việc kết thúc ngoại lệ có được xác minh trên PEP không?

**Exception tồn tại vô thời hạn** dễ biến thành policy drift hoặc “quy tắc bí mật”. Quản trị tập trung không giải quyết được nếu local override không có audit, còn mô hình phân tán không có nghĩa mọi vùng được tự do phá guardrail chung.

## 18. Những ngộ nhận và sai lầm phổ biến

1. **“Centralized control buộc mọi packet đi qua trung tâm.”** Sai: data-plane enforcement có thể phân tán.
2. **“Có controller cluster HA nên không có SPOF.”** Sai: có thể cùng phụ thuộc IAM, DNS, khóa ký hoặc policy publisher.
3. **“Distributed nghĩa là nhất quán tự nhiên.”** Sai: cần giao thức đồng bộ, quy tắc conflict và kiểm tra drift.
4. **“Local cache luôn tăng an toàn.”** Cache tăng survivability nhưng có thể cho phép quyền đã bị thu hồi.
5. **“Mất controller thì PEP chắc chắn ngừng chặn.”** Phụ thuộc product, lease và local state.
6. **“Fail-closed luôn là lựa chọn tốt nhất.”** Có thể gây sự cố với dịch vụ thiết yếu; phải phân loại theo rủi ro và điều kiện.
7. **“Fail-open giúp tránh outage nên chấp nhận mọi nơi.”** Có thể mở đường trái policy, đặc biệt với management plane.
8. **“Có cùng policy file nghĩa là các site áp cùng trạng thái.”** Cần kiểm tra applied version, rule compiler, plugin/firmware và nguồn tương ứng.
9. **“Mọi policy thay đổi cần hội tụ cùng thời điểm.”** Nhiều thiết bị không hỗ trợ atomic rollout toàn mạng; cần canary và consistency model rõ.
10. **“Cứ phân tán controller sẽ tự cô lập compromise.”** Federation trust hoặc khóa chung có thể làm compromise lan rộng.
11. **“Ký policy là đủ.”** Nếu khóa ký bị lộ, quy trình duyệt/yêu cầu thực thi yếu hoặc log bị sửa, vẫn có rủi ro.
12. **“Cảnh báo tập trung là kiểm soát tập trung.”** Analytics tập trung không đồng nghĩa PDP hay PEP cũng tập trung.
13. **“Một test từ bastion chứng minh mọi phân đoạn.”** Cần test từ đúng source zone, IPv4/IPv6 và cloud networking paths.
14. **“Controller availability cao đồng nghĩa traffic an toàn.”** Phải đo riêng enforcement correctness và service availability.
15. **“Policy rollback luôn vô hại.”** Có thể tái kích hoạt rule đã bị thu hồi; cần ranh giới an toàn và version gate.
16. **“Đưa thêm local exception là đủ cho regional autonomy.”** Cần delegation, TTL, mandatory guardrails và risk owner.

## 19. Checklist đưa ra quyết định và vận hành

### Phân tích trước khi chọn kiến trúc

- [ ] Xác định **chính xác** chức năng cần tập trung/phân tán: PAP, PDP, PEP, IAM, telemetry, management.
- [ ] Vẽ ranh giới giữa data/control/management plane và vị trí các trust boundaries.
- [ ] Mô tả các nguồn truy cập quan trọng, yêu cầu segmentation, firewall, VPN, DNS, IDS/IPS, cloud và Wi-Fi.
- [ ] Ghi các yêu cầu availability, latency, propagation, revocation, RTO/RPO, compliance và autonomy.
- [ ] Xác định các failure domains (WAN, controller, IAM, DNS, NTP, certificate/keys, regional outage).
- [ ] Đánh giá blast radius của policy lỗi, tài khoản/controller bị compromise và local exception.
- [ ] Lập ADR với nhiều phương án, đánh đổi, quyết định và điều kiện go/no-go.

### Thiết kế và triển khai

- [ ] Có global policy guardrail và quy tắc ưu tiên trước local exception.
- [ ] Có RBAC/MFA, tách quyền tác giả/phê duyệt/phát hành, quản lý key và audit.
- [ ] Có phương pháp bảo vệ kênh controller→PEP và xác minh nguồn policy.
- [ ] Có policy version/hash, TTL khi cần, observed applied version, reconciliation và drift alert.
- [ ] Fail behavior được định nghĩa **theo loại yêu cầu**, không một chế độ mặc định cho tất cả.
- [ ] Controller cluster có HA/fencing/quorum phù hợp, DR và bootstrap đáng tin cậy.
- [ ] Có phương án local buffer log, OOB, break-glass có kiểm soát và rollback.
- [ ] Triển khai theo canary/waves theo failure domain; stop conditions và owners rõ ràng.

### Kiểm thử và hậu kiểm

- [ ] Đã kiểm tra traffic hợp lệ và trái policy từ nhiều source zone, IPv4/IPv6.
- [ ] Đã đo propagation lag, revocation delay, drift và enforcement correctness.
- [ ] Đã mô phỏng controller/WAN/IdP mất kết nối ở môi trường được phép.
- [ ] Đã kiểm tra policy sai, rollback, anti-rollback và ranh giới global/local overrides.
- [ ] Đã xác minh applied version trên PEP, không chỉ success từ controller.
- [ ] Đã bảo vệ log, ghi UTC/clock uncertainty và phân biệt thiếu telemetry với thiếu sự kiện.
- [ ] Đã phân công action owner cho ngoại lệ, rủi ro còn lại và lịch review kiến trúc.

## 20. Câu hỏi tự kiểm tra

**1. Một trung tâm điều phối phát policy tới 200 firewall ở chi nhánh, nhưng các firewall tự xử lý packet. Đây là centralized hay distributed?**

**Cả hai ở các chức năng khác nhau:** việc tạo/phát policy tập trung về logic, enforcement phân tán. Cần kiểm tra PDP có yêu cầu online không và firewall xử lý thế nào khi mất controller.

**2. Tại sao HA ba node controller không tự động loại bỏ rủi ro kiến trúc tập trung?**

Cả ba có thể phụ thuộc IAM, nguồn policy, key ký, dữ liệu sai hoặc admin credential chung. HA thường tăng availability của controller; không tự giải quyết integrity và blast radius khi lỗi cấu hình hoặc compromise.

**3. Khi WAN mất, local PDP tiếp tục cho admin đã bị thu hồi đăng nhập. Vấn đề là gì?**

Local state có thể **stale** và chưa nhận revocation. Cần quy tắc TTL/lease và fail behavior cho truy cập đặc quyền: kiểm tra online hoặc credential ngắn hạn theo rủi ro, đồng thời có cơ chế xử lý sự cố offline.

**4. Vì sao policy version “đã phân phối” chưa đồng nghĩa policy “đã có hiệu lực”?**

Thiết bị có thể chưa nhận, từ chối do syntax/dependency, chưa activate hoặc rollback. Cần **observed applied version**, hash/config diff, ack theo trạng thái và kiểm thử traffic.

**5. Hybrid có thể vừa giảm latency vừa giữ governance thống nhất như thế nào?**

PAP/policy intent và approval ở trung tâm; PDP/PEP tại vùng để quyết định/thực thi gần traffic, có versioned policy, guardrails, freshness và reconciliation. Chính sách vẫn cần kiểm thử và audit.

**6. Nếu local exception cho phép user zone vào management zone nhưng global guardrail cấm, rule nào nên ưu tiên?**

Theo ví dụ trong bài, **mandatory deny** thắng; local exception không được vượt rào chắn toàn tổ chức. Quy tắc ưu tiên phải được viết rõ và kiểm thử trên sản phẩm thực tế.

**7. Vì sao fail-closed mọi nơi có thể không phù hợp?**

Một số dịch vụ thiết yếu có thể bị gián đoạn nghiêm trọng khi WAN/IdP/controller mất. Cần tách quyền mới/nguy hiểm khỏi flow đã được xác nhận và chọn cơ chế an toàn theo workload, thẩm quyền và rủi ro đã duyệt.

**8. Khi SIEM không nhận log từ một chi nhánh, có thể kết luận IPS ở đó ngừng chặn traffic không?**

Không. Có thể chỉ đứt đường telemetry hoặc collector. Cần xem local IPS counters, policy applied, packet/flow evidence và health của pipeline trước khi kết luận.

**9. Khi nào mô hình điều khiển phân tán thuần túy có thể được cân nhắc?**

Khi các miền có quyền tự chủ rõ ràng, yêu cầu offline cao, ranh giới trust chặt và tổ chức đủ năng lực quản lý conflict/drift/audit. Nó không đồng nghĩa cho phép mỗi site thay guardrail bắt buộc tùy ý.

---

**Ghi nhớ:** Quyết định giữa **centralized control** và **distributed control** thực chất là quyết định về **nguồn thẩm quyền, vị trí ra quyết định, vị trí thực thi, độ mới chính sách và hành vi khi lỗi**. Kiến trúc tốt chứng minh được ai có quyền thay đổi, thay đổi tới đâu, hoạt động thế nào khi mất kết nối và cách giới hạn thiệt hại khi chính sách hoặc controller có vấn đề.
