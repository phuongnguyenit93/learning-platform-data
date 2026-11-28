# Rule hit count: đo lường và tối ưu chính sách firewall bằng dữ liệu

Giả sử một firewall có 800 rule. Có rule được tạo khi thử nghiệm cách đây ba năm, rule khác cho phép kết nối đến hệ thống thanh toán, và một số rule chặn lưu lượng bất thường. Nhìn tên và địa chỉ IP trong cấu hình chưa đủ để biết **rule nào đang thực sự được sử dụng**, rule nào bị rule khác che khuất hoặc rule nào xuất hiện lưu lượng tăng đột ngột. **Rule hit count** là một chỉ số hữu ích để bắt đầu điều tra, nhưng nó không tự trả lời các câu hỏi bảo mật đó.

Trong chương **Firewall** của module **SECURITY_NETWORK_SECURITY**, bài này hướng dẫn cách hiểu counter, diễn giải số đo theo thời gian, kết hợp log và luồng kết nối để đánh giá hiệu quả của chính sách. Kiến thức áp dụng cho việc phân đoạn mạng, firewall truyền thống và next-generation firewall (NGFW), kết nối VPN/ZTNA, IDS/IPS cũng như kiến trúc hybrid/cloud. Mục tiêu là **giữ đúng luồng nghiệp vụ, giảm phạm vi truy cập dư thừa và phát hiện dấu hiệu bất thường** dựa trên bằng chứng thay vì suy đoán.

## 1. Rule hit count là gì?

**Rule hit count** là số lần một quy tắc firewall được bộ máy xử lý lưu lượng ghi nhận là **khớp với điều kiện đếm** của quy tắc đó. Điều kiện và đơn vị đếm **phụ thuộc sản phẩm, phiên bản và loại rule**:

- Có nền tảng tăng counter theo **packet** khớp rule.
- Có nền tảng ghi nhận theo **flow, session, connection hoặc lượt thiết lập phiên**.
- Có nền tảng hiển thị **bytes**, số packet, session đồng thời, hoặc nhiều counter khác nhau.
- Có nền tảng chỉ cung cấp **log cho phép/từ chối**, thống kê tổng hợp hoặc chỉ số ở tầng khác, chứ không cung cấp hit count cho từng rule.

Do đó, giá trị `10,000 hits` **không đồng nghĩa mặc định** với 10.000 người dùng, 10.000 HTTP request, 10.000 kết nối TCP hay 10.000 packet. Luôn xác minh **đơn vị đếm**, thời điểm counter tăng và chính sách nào được ghi nhận.

### 1.1. Rule gồm những gì?

Một rule điển hình:

~~~text
Rule ID: 120
Name: allow-app-to-db
Source zone: application
Source: 10.20.10.0/24
Destination zone: data
Destination: 10.30.5.20/32
Service: TCP/5432
Action: ALLOW
Logging: enabled
Hit count: 18432
~~~

Đây là **bản ghi minh họa**, không phải cú pháp hay output của một thiết bị cụ thể. Nó nêu điều kiện phân vùng, nguồn/đích, dịch vụ, hành động và dữ liệu quan sát. Các firewall khác còn có identity, application ID, URL category, schedule, user group, thiết bị, interface hoặc rule profile.

### 1.2. Phân biệt các thước đo

| Thước đo | Ý nghĩa thường gặp | Không nên suy ra |
|---|---|---|
| **Hit count** | Lần rule được đánh giá là trúng, theo ngữ nghĩa của engine | Số người dùng, request ứng dụng hoặc mức độ cần thiết nghiệp vụ |
| **Packet counter** | Số packet đi qua một điểm đếm | Số session hoặc số hành động nghiệp vụ |
| **Byte counter** | Số byte được ghi tại điểm đếm | Có/không có truy cập trái quyền; mọi byte đều hợp lệ |
| **Session/flow counter** | Số phiên/luồng được tạo hoặc ghi nhận | Toàn bộ request trong một kết nối giữ lâu |
| **Last-hit timestamp** | Thời điểm ghi nhận hit gần nhất, nếu sản phẩm hỗ trợ | Tần suất truy cập trước đó; lịch sử vĩnh viễn |
| **Log count** | Số sự kiện log đã được lưu hoặc xuất | Mọi packet/session đều có log; log có thể sampling, lọc hoặc mất |
| **Throughput/rate** | Tốc độ byte, packet hoặc session theo thời gian | Quyền truy cập đang đúng thiết kế |

Ví dụ một kết nối HTTPS dùng HTTP/2 có thể chở nhiều request trên cùng connection. Một **session-based** counter có thể tăng một lần cho kết nối đó, trong khi bộ đếm packet tăng nhiều lần; log ở gateway có thể ghi mỗi HTTP request riêng.

### 1.3. Counter thường nằm ở đâu?

~~~mermaid
flowchart LR
    A["Luồng đi vào"] --> B["Interface / zone"]
    B --> C["NAT, routing và phân loại theo pipeline"]
    C --> D["Policy lookup"]
    D --> E{"Khớp rule nào?"}
    E -->|"ALLOW"| F["State/session và xử lý tiếp"]
    E -->|"DENY"| G["Drop hoặc reject"]
    F --> H["Log / Counter / Telemetry"]
    G --> H
~~~

Đây là **mô hình logic để đặt câu hỏi**, không phải thứ tự xử lý cố định của mọi firewall. NAT trước/sau policy lookup, thứ tự security profile, hardware offload, state table và điểm cập nhật counter khác nhau theo sản phẩm. Muốn biết hit count đang đo ở giai đoạn nào, phải đối chiếu tài liệu và thực nghiệm trong phạm vi được phép.

## 2. Hit count liên quan gì đến thứ tự và hành động của rule?

### 2.1. Thứ tự rule và rule shadowing

Nhiều firewall xử lý danh sách rule tuần tự theo thứ tự ưu tiên: gặp rule áp dụng đầu tiên thì chọn hành động tương ứng. Tuy nhiên, điều này **không phổ quát**; rule base có thể phân tầng, dùng ưu tiên riêng, nhóm policy hoặc các chuỗi/chain. Vì vậy cần xác minh ngữ nghĩa thực tế.

Ví dụ **giả định firewall kiểu first-match**:

| Thứ tự | Rule | Nguồn | Đích | Cổng | Action |
|---|---|---|---|---|---|
| 10 | `allow-internal-db` | `10.20.0.0/16` | DB | TCP/5432 | ALLOW |
| 20 | `allow-app-db` | `10.20.10.0/24` | DB | TCP/5432 | ALLOW |
| 30 | `deny-other-db` | ANY | DB | TCP/5432 | DENY |

Mọi địa chỉ của `10.20.10.0/24` cũng thuộc `10.20.0.0/16`; nếu không có điều kiện khác và hệ thống thật sự áp dụng **first-match**, rule 20 có thể bị rule 10 **shadow** hoàn toàn. Khi đó rule 20 không có hit **không phải** vì API không gọi DB, mà vì lưu lượng đã khớp rule 10.

Phân biệt:

- **Shadowed:** một rule không được đánh giá tới hoặc không thể trúng vì rule ưu tiên cao đã xử lý hết lưu lượng phù hợp.
- **Redundant:** một rule có thể không cần thiết vì bỏ nó đi vẫn giữ nguyên kết quả hiệu lực mong muốn; cần phân tích hành vi sau thay đổi.
- **Overbroad:** rule cho phép phạm vi lớn hơn nhu cầu thực tế, dù hit count cao.
- **Unused:** rule không ghi nhận hit trong một khoảng quan sát cụ thể; chưa chắc không còn cần.
- **Expired:** rule dùng tạm đã hết thời hạn/ngữ cảnh nghiệp vụ; việc xác nhận có thể khác với quan sát hit.

**Không thể chứng minh redundant hay an toàn để xóa chỉ bằng hit count bằng 0.** Cần phân tích thứ tự/ưu tiên, điều kiện match, rule khác, chiều lưu lượng, lịch công việc và các ngoại lệ.

### 2.2. Implicit deny và rule cuối cùng

Nhiều hệ thống có cơ chế **deny ngầm định** khi không có rule cho phép. Deny ngầm định có thể không xuất hiện như một rule thông thường hoặc không có counter riêng. Vì vậy:

- Không thấy deny hit ở giao diện không có nghĩa là mọi truy cập đều được phép.
- Một lưu lượng bị chặn có thể xuất hiện trong log mặc định hoặc chỉ ở thống kê tổng của thiết bị.
- Các rule có quyền ưu tiên đặc biệt như chính sách hệ thống hoặc rule mặc định của sản phẩm cần được kiểm kê.

Khi tối ưu, phân biệt rule cho phép không dùng, rule chặn ít trúng và rule deny quan trọng cho mục tiêu phân đoạn. **Rule deny bằng 0 chưa phải lý do để gỡ bỏ rào chắn dự phòng.**

### 2.3. Stateful firewall và lưu lượng phản hồi

Stateful firewall lưu trạng thái các kết nối đã được cho phép. Trong nhiều triển khai, packet trả lời của một session hợp lệ được xử lý dựa trên **state table**, không nhất thiết đi qua lại toàn bộ quá trình tìm rule như packet tạo session.

Ví dụ client mở TCP tới HTTPS server:

~~~mermaid
sequenceDiagram
    participant C as Client (zone user)
    participant F as Stateful firewall
    participant W as Web server (zone app)
    C->>F: TCP SYN đến W:443
    F->>F: Match allow rule, tạo/ghi state
    F->>W: Chuyển SYN
    W-->>F: SYN-ACK
    F->>F: Xử lý qua state đã ghi
    F-->>C: SYN-ACK
    C->>F: Packet tiếp theo của phiên
    F->>W: Chuyển theo state/policy tương ứng
~~~

Ngữ nghĩa counter thay đổi theo sản phẩm; đừng kỳ vọng số hit của allow rule phải tăng theo mọi packet trả lời. Với routing bất đối xứng, NAT hoặc phiên đã tồn tại trước khi đổi policy, hiện tượng còn phức tạp hơn.

## 3. Hiểu số đo theo thời gian: counter tuyệt đối và delta

### 3.1. Counter tích lũy không nói lên hoạt động hiện tại

Giả định thiết bị cung cấp counter tích lũy theo **số lần rule match**, và quy tắc không bị reset trong kỳ:

| Rule | 09:00 | 09:10 | Delta 10 phút | Diễn giải ban đầu |
|---|---:|---:|---:|---|
| R-101: allow-app-db | 1.200 | 1.680 | 480 | Có lưu lượng khớp rule |
| R-102: allow-backup | 80 | 80 | 0 | Không ghi nhận hit mới trong 10 phút |
| R-103: deny-public-db | 4 | 1.204 | 1.200 | Tăng mạnh; cần phân tích nguồn |
| R-104: allow-legacy | 2.300 | 15 | Không xác định | Counter có thể reset hoặc dữ liệu không cùng nguồn |

Với R-101:

\[
\Delta H = H(t_2) - H(t_1) = 1680 - 1200 = 480
\]

Nếu thời gian là 10 phút và cách đếm không thay đổi:

\[
\text{Hit rate} = \frac{480}{10} = 48\ \text{hits/phút} = 0{,}8\ \text{hits/giây}
\]

Đây là **tốc độ khớp rule**; không thể đổi thành requests/second hay packets/second nếu chưa xác minh định nghĩa hit. R-102 có delta 0 trong 10 phút, nhưng nếu chạy backup mỗi chủ nhật thì quan sát này hoàn toàn bình thường. Với R-104, **không tính delta âm rồi kết luận “lưu lượng âm”**; cần điều tra reset, failover, reboot, thay rule hoặc nguồn dữ liệu.

### 3.2. Những nguyên nhân khiến counter không so sánh trực tiếp được

| Nguyên nhân | Dấu hiệu | Cách xử lý |
|---|---|---|
| Reboot hoặc manual reset | Counter đột ngột về 0 hoặc giảm | Ghi epoch/reset marker; bắt đầu cửa sổ mới |
| Deploy/reorder policy | Rule ID, counter hoặc ngữ nghĩa có thể thay đổi | Đối chiếu phiên bản policy và ID ổn định, không ghép theo số thứ tự đơn thuần |
| HA failover/chuyển active node | Thay node quan sát hoặc counter không đồng bộ | Ghi device/node/cluster ID; xác nhận cách đồng bộ counter |
| Nhiều thiết bị/multi-region | Mỗi node có một bộ đếm riêng | Tổng hợp có chủ đích, loại trừ trùng lặp |
| Cơ chế đếm khác nhau | Một nền tảng đếm session, nền tảng khác đếm packet | Không cộng/thay thế khi chưa chuẩn hóa |
| Counter tràn/rollover | Giá trị giảm không do reset; hiếm tùy kích thước counter | Đọc tài liệu kiểu counter và sự kiện hệ thống |
| Hardware offload/fast path | Packet đi đường tối ưu không tăng counter theo kỳ vọng | Kiểm tra phạm vi điểm đếm và dấu hiệu liên quan của thiết bị |
| Thay NAT/routing/policy route | Flow thay đổi đường đi, rule match khác | Liên kết với thay đổi topology và thời gian hiệu lực |

Không tự chỉnh sửa counter để số trông “đẹp”. Lưu bản đọc có **timestamp, múi giờ, device ID, rule ID, policy version, loại counter và khoảng quan sát**. Các trường này giúp truy vết dữ liệu khi so sánh trước/sau thay đổi.

### 3.3. Cửa sổ quan sát thế nào là đủ?

Thời gian nên theo **chu kỳ nghiệp vụ**, không có số ngày chuẩn cho mọi hệ thống:

- Lưu lượng API liên tục có thể quan sát theo giờ/ngày và so sánh với giờ cao điểm.
- Backup, DR, kiểm toán hoặc đồng bộ báo cáo có thể chỉ chạy theo tuần/tháng/quý.
- Hệ thống dự phòng có thể không được dùng trong vận hành bình thường nhưng **rất quan trọng trong failover**.
- Rule phục vụ sự cố hiếm, tình huống khôi phục hoặc hoạt động triển khai có thể có hit rất thấp.

Khi gắn nhãn “không dùng”, ghi rõ **không ghi nhận hit mới từ ngày X đến ngày Y**, phạm vi hệ thống được kiểm tra và các ngoại lệ đã được rà soát. Không viết “rule vô dụng” chỉ dựa vào một snapshot.

## 4. Điều tra nguyên nhân khi hit tăng cao

Hit count cao **không tự động là tấn công**, và hit count thấp **không tự động là an toàn**. Kết hợp dấu hiệu:

| Quan sát | Khả năng hợp lệ | Khả năng cần điều tra |
|---|---|---|
| Allow rule cho API tăng mạnh | Chiến dịch bán hàng, tăng người dùng, autoscaling | Bot, hệ thống retry lỗi, DDoS tầng ứng dụng, truy cập ngoài phạm vi |
| Deny rule đến DB tăng mạnh | Thử nghiệm security có phê duyệt, quét kiểm kê nội bộ | Quét cổng ngoài Internet, lateral movement, workload cấu hình sai |
| Deny tới DNS resolver không được phép | Chính sách egress hoạt động | Ứng dụng bỏ qua resolver chuẩn, DNS tunneling cần rà soát |
| Rule remote admin có hit ngoài giờ | Ca trực khẩn cấp | Tài khoản/quy trình quản trị bị lạm dụng |
| Rule allow-backup có hit đột ngột về 0 | Lịch backup thay đổi | Backup thất bại, routing bị đứt, policy chưa đúng |
| Một rule rất rộng có hàng triệu hit | NAT/gateway phục vụ đúng tải | Lưu lượng khác mục đích đang dùng chung rule rộng |

### 4.1. Chuỗi phân tích điều tra

~~~mermaid
flowchart TD
    A["Phát hiện thay đổi hit count"] --> B{"Counter có cùng đơn vị và epoch?"}
    B -->|"Không"| C["Kiểm tra reset, failover, đổi rule, nguồn đo"]
    B -->|"Có"| D["So sánh baseline và thời gian nghiệp vụ"]
    D --> E["Ghép rule với log flow, source, destination, application"]
    E --> F{"Lưu lượng có được phê duyệt?"}
    F -->|"Có"| G["Ghi nhận baseline, cân nhắc tối ưu rule"]
    F -->|"Chưa rõ"| H["Xác minh owner, topology và sự kiện liên quan"]
    F -->|"Không"| I["Điều tra sự cố và giới hạn rủi ro theo quy trình"]
~~~

Điều tra nên xem:

1. **Nguồn:** subnet, host, workload, danh tính người dùng/thiết bị nếu có bằng chứng.
2. **Đích:** IP trước/sau NAT khi cần, dịch vụ, zone, cổng, DNS và tài sản chịu ảnh hưởng.
3. **Hành động:** allow, deny, drop, reject, reset, các policy đặc biệt khác.
4. **Thời gian:** giờ, ngày, sự kiện deploy, thay routing, bảo trì, lịch backup.
5. **Ngữ cảnh:** ứng dụng, loại luồng, session, packet/byte, log từ IDS/IPS/WAF và cảnh báo endpoint.
6. **Tính hợp lệ:** yêu cầu nghiệp vụ có owner, danh sách luồng được duyệt và ticket thay đổi tương ứng hay không.

**Counter cho biết số lần khớp, không cho biết payload có độc hại hoặc user có được phép sử dụng tính năng.** Dù allow rule hoạt động đúng, ứng dụng và DB vẫn cần xác thực/ phân quyền theo đối tượng dữ liệu.

### 4.2. Counter của rule DENY

Một rule chặn với hit tăng có thể cho thấy **kiểm soát đang ngăn lưu lượng không được phép**. Tuy nhiên cần phân biệt:

- Một lỗi ứng dụng lặp retry nhiều lần tới cổng sai.
- Công cụ giám sát hoặc quét cấu hình được phê duyệt.
- Thiết bị bị chiếm đang tìm đường sang mạng khác.
- Lưu lượng Internet ngẫu nhiên đến địa chỉ công khai.

Không nên tắt deny hoặc mở allow ngay để “dọn log”. Trước hết xác minh luồng, mức độ quan trọng của đích, khoảng thời gian, tần suất và có cảnh báo trên các lớp khác không.

## 5. Zero-hit rule: khi nào có thể xem xét gỡ bỏ?

Một rule có **0 hit trong cửa sổ quan sát** là **ứng viên rà soát**, không phải kết luận cuối cùng. Có ít nhất sáu tình huống:

1. **Không còn tài sản hoặc nghiệp vụ:** máy chủ đã ngừng, ứng dụng đã thay tuyến; có thể là rule dư.
2. **Bị rule trước che khuất:** cần phân tích shadowing và hành vi sau khi thay đổi.
3. **Đường đi chưa qua firewall này:** routing/NAT/SD-WAN hoặc thiết bị khác đang xử lý.
4. **Lưu lượng rất hiếm:** backup, failover, khắc phục thảm họa, đợt đóng sổ.
5. **Rule dự phòng bắt buộc:** chặn một đường tấn công chưa từng xảy ra, không nên xóa chỉ vì không có hit.
6. **Telemetry không đầy đủ:** reset, offload, lỗi thu thập, counter chỉ đo session mới hoặc thiếu node HA.

### 5.1. Quy trình khử rule an toàn

~~~mermaid
flowchart TD
    A["Danh sách rule zero-hit / low-hit"] --> B["Xác định owner, mục đích, ngày tạo, ticket"]
    B --> C["Đối chiếu logs, flow, topology và phụ thuộc"]
    C --> D{"Có nhu cầu dự phòng hoặc sự kiện định kỳ?"}
    D -->|"Có"| E["Giữ và ghi lý do; review lại theo kỳ"]
    D -->|"Chưa rõ"| F["Tiếp tục thu thập bằng chứng / xác minh owner"]
    D -->|"Không"| G["Phân tích shadowing và tác động nếu xóa"]
    G --> H["Phê duyệt thay đổi và kế hoạch rollback"]
    H --> I["Thử ở staging/canary hoặc cửa sổ bảo trì"]
    I --> J["Theo dõi lỗi, hit rule khác và kết nối nghiệp vụ"]
    J --> K["Chốt thay đổi hoặc rollback"]
~~~

Trình tự khuyến nghị:

1. **Kiểm kê:** rule ID, tên, action, source/destination zone, địa chỉ, dịch vụ, owner, lý do tồn tại, ngày đổi gần nhất.
2. **Cửa sổ quan sát đủ dài:** thu delta theo ngày/tuần và đối chiếu lịch công việc.
3. **Xác minh kỹ thuật:** xem shadowing, rule ưu tiên khác, NAT, đường routing, HA, bất kỳ địa chỉ động hoặc identity mapping nào.
4. **Xác minh nghiệp vụ:** hỏi owner, hệ thống dự phòng, quy trình khôi phục, yêu cầu tuân thủ.
5. **Phân tích thay đổi:** loại bỏ rule làm **mất allow cần thiết**, **mở đường không mong muốn** hay chuyển lưu lượng sang rule khác không?
6. **Phê duyệt/triển khai:** theo quy trình change management, có backup cấu hình và rollback đã thử.
7. **Theo dõi:** log drop/allow, health check, SLO, lỗi kết nối và chủ thể liên quan sau triển khai.

Việc xóa một allow rule có thể khiến traffic rơi vào deny mặc định, nhưng cũng có thể làm traffic khớp **một allow rule rộng hơn** ở vị trí khác. Vì vậy **xóa rule không phải lúc nào cũng đồng nghĩa thu hẹp quyền hiệu dụng**. Đánh giá chính sách sau thay đổi, không chỉ nhìn số rule giảm.

### 5.2. Rule có hit cao nhưng vẫn cần tối ưu

Giả sử một allow rule cho phép `10.0.0.0/8` truy cập database `10.30.5.20:5432` và có 50.000 hits/ngày. Đây không phải lý do để giữ phạm vi `/8`: đa số hit có thể chỉ đến từ một cụm API nhỏ.

Cách cải tiến:

- Tập hợp source thực tế trong cửa sổ đủ đại diện, có xét NAT và proxy.
- Đối chiếu danh sách workload/hệ thống được phê duyệt và các luồng dự phòng.
- Viết rule mới **hẹp hơn** theo zone, group, IP, service/identity nếu nền tảng hỗ trợ.
- Kiểm thử positive/negative theo từng đường và đánh giá rule ordering.
- Theo dõi hit trên rule mới và hành vi mạng trước khi thu hồi rule cũ.

**Độ phổ biến của lưu lượng không phải chứng cứ cho tính hợp lệ của toàn bộ phạm vi được phép.**

## 6. Ví dụ phân tích từ hai bản snapshot

Giả định nhóm vận hành xuất bộ đếm hit từ **cùng một thiết bị**, cùng phiên bản policy, không reset giữa 09:00 và 09:10:

~~~csv
rule_id,rule_name,action,hits_0900,hits_0910
101,allow-api-db,allow,1200,1680
102,allow-weekly-backup,allow,80,80
103,deny-internet-db,deny,4,1204
104,allow-legacy-admin,allow,0,0
~~~

### 6.1. Phân tích bằng PowerShell trên dữ liệu đã xuất

Ví dụ bên dưới **chỉ thao tác dữ liệu CSV giả định đã được người dùng lưu và cho phép đọc**, không kết nối firewall, không reset counter và không sửa cấu hình:

~~~powershell
$rows = Import-Csv -LiteralPath ".\rule-hit-snapshots.csv"

$rows | ForEach-Object {
    $before = [long]$_.hits_0900
    $after  = [long]$_.hits_0910
    $delta  = if ($after -ge $before) { $after - $before } else { $null }

    [pscustomobject]@{
        RuleId      = $_.rule_id
        RuleName    = $_.rule_name
        Action      = $_.action
        Delta       = $delta
        HitsPerMin  = if ($null -ne $delta) { [math]::Round($delta / 10.0, 2) } else { $null }
        NeedsReview = ($null -eq $delta) -or ($delta -eq 0)
    }
} | Format-Table -AutoSize
~~~

Với mẫu giả định, kết quả cần hiểu như sau:

| Rule | Delta | Hits/phút | Hướng điều tra |
|---|---:|---:|---|
| `allow-api-db` | 480 | 48 | So sánh với lưu lượng API hợp lệ |
| `allow-weekly-backup` | 0 | 0 | Kiểm tra lịch backup, không xóa vội |
| `deny-internet-db` | 1.200 | 120 | Phân tích nguồn deny, cảnh báo và baseline |
| `allow-legacy-admin` | 0 | 0 | Rà soát owner, điều kiện truy cập dự phòng |

Để phân tích sản xuất, nên lưu thêm **timestamp có múi giờ, device ID, policy version, epoch reset, rule identifier ổn định, đơn vị hit**. Ví dụ trên dùng hai tên cột thời gian cố định chỉ để minh họa cách tính; không phải pipeline giám sát hoàn chỉnh.

### 6.2. Trường hợp counter reset

Nếu rule có `hits_0900=2300` và `hits_0910=15`, script gán delta bằng `null` để tránh báo âm. Nhưng ngay cả khi counter **tăng** cũng chưa chắc hai bản ghi so sánh được (ví dụ HA switch sang node có counter cao hơn, hoặc rule bị thay đổi nội dung mà giữ tên). Cần xác nhận cùng **chu kỳ đo và ngữ nghĩa rule** trước khi tính toán.

## 7. Đọc counter trên các hệ thống khác nhau

Không có lệnh chuẩn duy nhất cho mọi firewall. Các ví dụ dưới đây mang tính **kiểm kê/đọc**, chỉ chạy trên thiết bị hoặc môi trường được ủy quyền.

### 7.1. Linux iptables

~~~bash
# Xem counters của chain FORWARD; không reset counter.
sudo iptables -L FORWARD -n -v --line-numbers

# Chỉ xem cấu hình và counter trong bảng filter của IPv4.
sudo iptables -t filter -L -n -v
~~~

`pkts` và `bytes` là bộ đếm **packet và byte** được ghi ở rule/chain tương ứng, **không phải mặc nhiên số session**. Chỉ xem chain `FORWARD` sẽ bỏ qua luồng `INPUT`/`OUTPUT`; NAT hoặc các bảng/chain khác cần được xác định nếu liên quan. Với traffic đi fast path hoặc có phần xử lý offload, cần kiểm tra khả năng đo của nền tảng.

**Không dùng tùy chọn reset như `-Z` khi chỉ định kiểm tra**; reset counter làm mất dữ liệu tham chiếu và ảnh hưởng người khác đang theo dõi.

### 7.2. Linux nftables

~~~bash
# Xem ruleset hiện có, gồm counter nếu rule có cấu hình biểu thức counter.
sudo nft -a list ruleset
~~~

Không phải rule nftables nào cũng hiển thị counter; thông thường phải có biểu thức `counter` thích hợp. Các cấu trúc map/set/chain và ưu tiên xử lý có thể làm thống kê xuất hiện ở điểm khác so với mô hình firewall tuyến tính.

### 7.3. NGFW, cloud và container

| Nền tảng | Dữ liệu thường có | Cần xác minh |
|---|---|---|
| **NGFW thương mại** | Policy hit, last hit, session/byte, log traffic, application, user; tùy sản phẩm | Counter đếm session hay packet, reset khi nào, policy layer/order, HA sync |
| **Cloud security group / network ACL** | Rule, audit changes, flow telemetry hoặc số liệu nhà cung cấp | Flow log **không mặc nhiên là hit counter của từng rule SG**; mapping log → rule có thể không có hoặc không duy nhất |
| **Cloud firewall tập trung** | Rule logging và metrics theo chính sách khi hỗ trợ | Trường rule ID, sampling, vùng/instance, thời gian lưu log |
| **Kubernetes NetworkPolicy** | Đối tượng policy, cộng thêm metrics/log của CNI nếu có | **NetworkPolicy chuẩn không bắt buộc cung cấp hit count**; tùy plugin mạng và loại policy |
| **Service mesh / proxy** | Số request/connection, authorization deny, telemetry danh tính L7 | Đây là dữ liệu ở lớp proxy/L7, không tự đồng nhất với firewall L3/L4 |

Một cloud VPC Flow Log cho biết **flow và trạng thái accept/reject theo thông tin nền tảng có thể xuất ra**, thường không nói chính xác rule nào quyết định kết quả nếu không có trường/cơ chế tương quan phù hợp. Tránh tạo một bảng “rule hits” bằng cách đếm tất cả bản ghi accept rồi gán tùy tiện cho một security group rule.

## 8. Tối ưu quan sát: log, sampling và chi phí

### 8.1. Hit count không thay thế log

Counter hữu ích vì gọn, nhưng không cho biết toàn bộ **source, destination, user, thời gian của từng event và ngữ cảnh an ninh**. Log có thể hỗ trợ điều tra, song cũng có giới hạn:

- Không phải rule nào cũng bật logging, hoặc chỉ log khi tạo/kết thúc session.
- Có thể sampling, aggregation, rate limit, packet loss tại pipeline xuất log.
- Log nhiều có thể gây tải, tăng chi phí lưu trữ và làm trễ xử lý.
- Log có thể chứa IP cá nhân, tài khoản, domain, URI hoặc dữ liệu nhạy cảm; phải áp quyền và chính sách lưu trữ phù hợp.

Phương án cân bằng là dùng **counter định kỳ để phát hiện biến động**, rồi đối chiếu log có chọn lọc cho rule, thời gian hoặc nhóm flow cần điều tra. Nếu chỉ bật log deny, không thể suy ra mức sử dụng chi tiết của allow rule từ log deny.

### 8.2. Mô hình giám sát

~~~mermaid
flowchart LR
    FW["Firewall / NGFW"] -->|"Counter snapshot"| M["Thu thập có timestamp và rule ID"]
    FW -->|"Traffic / threat logs"| L["Kho log có kiểm soát"]
    M --> D["Tính delta/rate, phân tích reset"]
    D --> B["Baseline theo giờ/ngày/chu kỳ"]
    L --> C["Source, destination, action và ngữ cảnh"]
    B --> A["Cảnh báo và dashboard"]
    C --> A
    A --> R["Điều tra và phê duyệt thay đổi"]
~~~

Ví dụ dashboard nội bộ nên tách:

- **Rule usage:** delta hits trong cửa sổ, last hit, xu hướng theo giờ/ngày.
- **Deny anomaly:** thay đổi deny rate so với baseline cùng khoảng thời gian.
- **Policy hygiene:** rule zero-hit/low-hit cần review, rule quá rộng, rule sắp hết hạn, rule thiếu owner.
- **Telemetry quality:** thiết bị không gửi snapshot, counter reset, dữ liệu từ HA không nhất quán.
- **Security outcome:** số luồng trái phép bị chặn, lỗi kết nối hợp lệ, tác động tới dịch vụ và rủi ro còn lại.

Không nên chọn một **ngưỡng hit count tuyệt đối** áp cho mọi rule. Rule quản trị dùng một lần mỗi tháng và rule web gateway dùng hàng triệu lần/ngày đòi hỏi ngưỡng khác nhau.

## 9. Rule hit count trong kiến trúc phân đoạn và Zero Trust

### 9.1. Rule hoạt động nhưng ranh giới vẫn có thể yếu

Giả định một rule `allow-any-internal-to-db` có hit count rất lớn. Nó chứng minh có lưu lượng khớp rule (nếu counter đang hoạt động đúng), nhưng không chứng minh:

- Các workload nguồn đều được phê duyệt.
- Danh tính kết nối đã được xác thực bằng mTLS hoặc cơ chế tương ứng.
- API chỉ truy vấn dữ liệu của tenant được phép.
- Không có dịch vụ dùng chung bị lợi dụng để đi xuyên segment.

Trong kiến trúc **microsegmentation**, counter giúp xác định luồng thực tế để lập ma trận allow hẹp. Tuy nhiên phải kết hợp **identity/group/tag, traffic observation, danh sách luồng nghiệp vụ và xác thực ứng dụng**.

### 9.2. Những luồng khó nhìn thấy

Đừng chỉ rà các rule Internet → web. Các luồng dễ bị bỏ sót:

| Luồng | Vì sao có thể ít hit hoặc thiếu log | Hậu quả khi sửa sai |
|---|---|---|
| Backup → database | Theo lịch đêm/tuần | Mất khả năng sao lưu hoặc restore |
| Hệ thống DR → ứng dụng | Chỉ chạy khi failover | Dịch vụ không phục hồi được |
| API → DNS/NTP/IdP | Có cache, theo chu kỳ, phụ thuộc xử lý | Hết phiên xác thực, lỗi TLS hoặc phân giải |
| CI/CD → control plane | Theo lịch release | Không triển khai được, mất khả năng rollback |
| Admin qua VPN/ZTNA | Ít sử dụng, chỉ truy cập sự cố | Không xử lý được sự cố |
| Telemetry → collector | Log có sampling, luồng gộp | Mất bằng chứng an ninh/giám sát |
| Tenant A → dịch vụ chung | Qua proxy/NAT nên nguồn bị gộp | Không phân biệt quyền theo tenant |

Mỗi rule cần được đối chiếu với sơ đồ data flow, trust boundary và **nguồn dữ liệu định danh** phù hợp. Firewall cho phép kết nối tới DB không quyết định quyền xem bản ghi trong DB.

## 10. Phân tích rủi ro và tình huống thay đổi

### 10.1. Các lỗi tư duy thường gặp

| Nhận định sai | Vì sao sai | Cách đánh giá đúng |
|---|---|---|
| “0 hit nghĩa là xóa được” | Có thể là lưu lượng định kỳ, rule dự phòng, shadowing hoặc thiếu telemetry | Xác minh owner, lịch, hiệu lực, shadowing, rollback |
| “Hit cao nghĩa là rule tốt” | Rule rộng có thể được nhiều chủ thể không được phép dùng | Kiểm tra nguồn thực tế và nhu cầu truy cập |
| “Hit cao nghĩa là đang bị tấn công” | Có thể do lưu lượng hợp lệ và cấu hình count theo packet | So sánh baseline và dữ liệu điều tra |
| “Deny hit tăng thì nên mở allow” | Có thể firewall đang ngăn tấn công | Kiểm tra nguồn, đích, cảnh báo, thay đổi ứng dụng |
| “Đếm flow log chính là hit SG rule” | Không có mapping rule quyết định duy nhất trong nhiều nền tảng | Đối chiếu khả năng telemetry của provider |
| “Counter của các node HA có thể cộng trực tiếp” | Có thể trùng lặp, reset hoặc đồng bộ khác nhau | Ghi node/epoch và quy tắc tổng hợp |
| “Xóa một allow luôn siết quyền” | Traffic có thể rơi vào allow khác rộng hơn | Phân tích toàn bộ policy hiệu dụng |

### 10.2. Ví dụ review rule SSH ít dùng

Rule `allow-admin-ssh` cho phép nhóm quản trị kết nối qua TCP/22 tới hai máy chủ production. Counter không tăng trong ba tuần.

Thực hiện review:

1. Đối chiếu lịch công việc: đường này có chỉ dùng khi khôi phục hoặc xử lý sự cố không?
2. Xác minh đường SSH hiện có qua bastion/VPN/ZTNA, mapping identity và rule khác.
3. Kiểm tra counter ở đúng thiết bị, đúng node HA, epoch và loại session.
4. Xác định owner, yêu cầu truy cập khẩn cấp, biện pháp thay thế đã được thử.
5. Nếu không còn cần, lên change request **với rollback**, xác minh truy cập quản trị hợp lệ và không mở đường thay thế rộng hơn.

Không dùng một lệnh ngắt hoặc reset firewall để “thử” trên production. Khi cần kiểm thử tác động, ưu tiên staging hoặc thay đổi từng phần theo quy trình được phê duyệt.

### 10.3. Ví dụ deny rate tăng bất thường

Rule `deny-internet-db` bình thường ghi 3–10 hits/phút. Trong 10 phút mới nhất, delta lên 1.200 (120 hits/phút). Đây là tín hiệu cần điều tra, **chưa phải kết luận chắc chắn có tấn công**.

Kiểm tra nguồn IP và zone, đích DB có thật hay không, cổng, phân bố theo thời gian, thay đổi NAT/routing, lịch kiểm thử bảo mật, log IDS/IPS và tình trạng ứng dụng. Nếu nhiều nguồn bên ngoài dò cổng quản trị/DB, xác minh firewall đang chặn đúng và theo dõi nguồn. Nếu chỉ một ứng dụng nội bộ bị cấu hình sai, sửa luồng ứng dụng thay vì mở rộng quyền firewall không kiểm soát.

## 11. Bài tập thực hành

Một tổ chức vận hành firewall trước vùng API, database và mạng quản trị. Bảng dưới đây mô phỏng snapshot từ cùng thiết bị, mỗi hit là **một lần rule match theo định nghĩa do thiết bị cung cấp**, không có reset trong 60 phút:

| Rule | Action | Hits 13:00 | Hits 14:00 | Ghi chú |
|---|---|---:|---:|---|
| A: allow-web-api | ALLOW | 15.000 | 21.000 | Truy cập website liên tục |
| B: allow-backup-db | ALLOW | 40 | 40 | Backup chạy lúc 02:00 hằng ngày |
| C: deny-guest-to-db | DENY | 200 | 3.800 | Mạng khách không được vào DB |
| D: allow-old-vpn-admin | ALLOW | 0 | 0 | Đã chuyển sang ZTNA, chưa xác nhận DR |
| E: allow-all-internal-db | ALLOW | 5.000 | 13.000 | Rule cho phép cả mạng nội bộ vào DB |

**Yêu cầu:**

1. Tính delta hits và hit rate/phút cho từng rule.
2. Rule nào nên ưu tiên **điều tra an ninh**, rule nào cần **review hygiene**, và vì sao?
3. Tại sao không xóa B/D chỉ vì không có hit trong một giờ?
4. Rule E có nhiều hit: kế hoạch giảm bề rộng của rule nên gồm những bước gì?
5. Nếu rule D đứng sau một allow rule rộng hơn, hit count 0 nói lên điều gì?

**Gợi ý giải:**

- A: 6.000 hits/giờ = 100 hits/phút.
- B: 0 hits trong một giờ; cần so với cửa sổ backup.
- C: 3.600 hits/giờ = 60 hits/phút; điều tra nguồn mạng khách, số thiết bị và hoạt động bất thường.
- D: 0 hits; có thể là rule dư sau chuyển ZTNA, nhưng cần xác nhận đường DR/break-glass.
- E: 8.000 hits/giờ ≈ 133,33 hits/phút; hit cao **không chứng minh tất cả máy nội bộ phải được kết nối DB**. Kiểm kê source thực tế, owner, ứng dụng, dự phòng; thử rule hẹp mới và quan sát trước khi bỏ rule cũ.
- Nếu D bị rule phía trước shadow, `0 hit` có thể phản ánh **thứ tự match**, không phải kết luận đường quản trị đã ngừng sử dụng.

## 12. Checklist review Rule hit count

- [ ] Xác định đúng đơn vị counter: packet, byte, flow, session hay loại khác theo sản phẩm.
- [ ] Biết counter tăng ở bước nào trong pipeline xử lý, có bao gồm packet trả lời/state/offload không.
- [ ] Gắn snapshot với timestamp, timezone, device/node, rule ID, policy version và reset epoch.
- [ ] Không tính chênh lệch trực tiếp khi có reset, failover, counter rollover hoặc thay đổi rule.
- [ ] Chọn cửa sổ quan sát đủ dài cho backup, DR, triển khai, quản trị khẩn cấp và lưu lượng định kỳ.
- [ ] Phân biệt rule zero-hit, shadowed, redundant, overbroad và deny dự phòng.
- [ ] Đánh giá thứ tự/ưu tiên, implicit deny, NAT, routing và quy tắc mặc định của sản phẩm.
- [ ] Kết hợp hit với log/flow, địa chỉ nguồn-đích, danh tính, ứng dụng, baseline và thông tin IDS/IPS.
- [ ] Không coi hit cao là hợp lệ hoặc tấn công nếu chưa có bằng chứng.
- [ ] Không tự tạo mapping flow log → SG rule khi provider không có thông tin tương ứng.
- [ ] Khi thu hẹp rule, kiểm tra hiệu lực **toàn bộ chính sách**, không chỉ một dòng cấu hình.
- [ ] Xác nhận owner, ticket thay đổi, thử positive/negative, giám sát sau thay đổi và kế hoạch rollback.
- [ ] Bảo vệ log, giới hạn thông tin nhạy cảm và kiểm soát chi phí quan sát.
- [ ] Giữ kiểm soát phân quyền ứng dụng/DB và danh tính workload độc lập với firewall.

**Ghi nhớ:** **Rule hit count là tín hiệu về việc sử dụng một quy tắc theo cách thiết bị đếm**, không phải thước đo trực tiếp về mức an toàn hay tính cần thiết nghiệp vụ. Đọc đúng đơn vị, đo delta trên một cửa sổ đáng tin, đối chiếu logs và topology, rồi dùng quy trình thay đổi có kiểm chứng mới giúp tối ưu firewall mà không làm mất bảo vệ hoặc gián đoạn hệ thống.
