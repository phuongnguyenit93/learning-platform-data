# Rule sprawl trong firewall: Nhận diện, đánh giá và kiểm soát

## 1. Rule sprawl là gì?

**Rule sprawl** là hiện tượng các quy tắc kiểm soát truy cập mạng liên tục được bổ sung, sao chép hoặc mở rộng mà thiếu cơ chế rà soát, hợp nhất và thu hồi. Theo thời gian, rulebase có thể chứa các rule **trùng lặp (duplicate)**, **chồng lấn (overlapping)**, **bị che khuất (shadowed)**, **dư thừa (redundant)**, **đã hết nhu cầu (stale)** hoặc **cấp quyền rộng hơn cần thiết (overly permissive)**. Người vận hành khó trả lời câu hỏi đơn giản: *từ nguồn nào có thể truy cập tài sản nào, qua giao thức gì và vì sao quyền đó tồn tại?*

Vấn đề có thể xuất hiện trên firewall biên Internet, firewall nội bộ giữa các VLAN, host firewall, VPN policy, firewall cloud, security group, network ACL hoặc chính sách microsegmentation. Đây vừa là vấn đề kỹ thuật (xử lý rule, routing, NAT, trạng thái kết nối), vừa là vấn đề quản trị (chủ sở hữu, quy trình cấp quyền, thời hạn ngoại lệ, kiểm toán).

Trong module **SECURITY_NETWORK_SECURITY**, việc xử lý rule sprawl trực tiếp hỗ trợ **phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng cloud**. Rulebase khó kiểm soát có thể khiến kiến trúc “default deny” trên giấy không phản ánh đường truy cập thực tế, hoặc khiến thay đổi nhỏ làm gián đoạn dịch vụ quan trọng.

**Mục tiêu sau bài học:**

- Phân biệt chính xác các dạng rule sprawl và hệ quả lên quyền truy cập hiệu lực.
- Hiểu thứ tự rule, tập điều kiện khớp và sự khác biệt giữa firewall first-match, security group và NetworkPolicy.
- Thiết lập danh mục rule gắn với tài sản, nhu cầu nghiệp vụ, chủ sở hữu và bằng chứng.
- Phân tích rủi ro giữ hoặc thu hồi từng rule, không suy luận chỉ từ hit count.
- Lập kế hoạch thu gọn rule có test **ALLOW/DENY**, theo dõi và rollback.
- Ngăn sprawl tái diễn bằng quản trị vòng đời, policy as code và rà soát định kỳ.

> **Điểm cần nhớ:** một rulebase có ít rule chưa chắc an toàn; một rule `ALLOW ANY → ANY` có thể nguy hiểm hơn hàng chục rule được giới hạn hợp lý. Mục đích của tối ưu hóa là **quyền hiệu lực đúng với nhu cầu**, có thể giải thích và kiểm chứng.

## 2. Một firewall rule mô tả những điều kiện gì?

| Thuộc tính | Ví dụ | Câu hỏi kiểm tra |
|---|---|---|
| **ID / tên rule** | FW-APP-014 | Có định danh để tìm trong log, ticket và lịch sử thay đổi không? |
| **Nguồn (source)** | App subnet, nhóm VPN, workload identity | Có giới hạn tới đúng đối tượng cần quyền không? |
| **Đích (destination)** | orders-db, mạng DATA, service group | Rule có mở tới tài sản nhạy cảm không liên quan không? |
| **Giao thức / cổng** | TCP/5432, UDP/TCP 53 | Có đang dùng `any` thay vì giao thức cần thiết không? |
| **Chiều / security zone** | APP → DATA, egress | Traffic thực có đi qua đúng điểm thực thi không? |
| **Action** | ALLOW, DENY, REJECT | Nếu nhiều rule khớp, hành động nào thực sự được thực thi? |
| **Thứ tự / priority** | Rule 10 trước rule 20 | Có một rule rộng phía trước che rule cụ thể không? |
| **NAT / route** | IP trước và sau DNAT | Thiết bị nhìn thấy địa chỉ nào tại giai đoạn so khớp? |
| **Điều kiện mở rộng** | User, application, lịch, tag | Hai rule nhìn giống IP/port nhưng khác điều kiện không? |
| **Giám sát** | Log allow/deny, hit counter | Số liệu đo trong khoảng nào, có bị giới hạn hoặc reset không? |
| **Vòng đời** | Owner, ticket, ngày hết hạn | Vì sao rule tồn tại và khi nào cần rà soát? |

Không thể đánh giá hoàn toàn dựa trên bảng rule của **một** thiết bị. Một kết nối còn phụ thuộc route, firewall ở các chặng khác, NAT, load balancer, host policy, cloud security group và kiểm soát danh tính. Quy tắc ALLOW trên một firewall không chứng minh dịch vụ đích đang lắng nghe; một quy tắc DENY trên firewall A không có hiệu quả nếu gói đi theo đường khác.

## 3. Sáu biểu hiện quan trọng của rule sprawl

### 3.1. Duplicate: trùng lặp hoàn toàn

Hai rule có cùng phạm vi khớp, cùng action và các điều kiện bổ sung tương đương. Trong firewall xử lý theo thứ tự, rule thứ hai có thể không được chọn vì rule thứ nhất đã xử lý lưu lượng. Tuy vậy, cần so sánh đầy đủ **zone, identity, logging, time schedule, NAT, security profile** trước khi kết luận trùng hoàn toàn.

### 3.2. Overlap: chồng lấn tập lưu lượng

~~~text
ALLOW  10.20.0.0/16  -> 10.30.0.0/16  TCP/5432
ALLOW  10.20.10.0/24 -> 10.30.10.15  TCP/5432
~~~

Rule dưới mô tả một tập con của rule trên nếu các điều kiện khác tương đương. Overlap không nhất thiết là lỗi: có thể tồn tại có chủ đích khi thay đổi ứng dụng. Nhưng nếu không có lý do, nhóm vận hành sẽ khó xác định chính sách nào là cơ sở và thời điểm có thể thu hồi rule cũ.

### 3.3. Shadowed: bị che khuất

Với firewall **first matching rule**, rule phía trước có thể khớp **toàn bộ** tập lưu lượng của rule phía sau và làm rule phía sau không bao giờ được chọn:

~~~text
10  ALLOW  10.10.0.0/16  -> 10.30.0.0/16  ANY
20  DENY   10.10.50.0/24 -> 10.30.10.15   TCP/5432
~~~

Kết nối từ `10.10.50.21` đến `10.30.10.15:5432` khớp rule 10 trước và được **ALLOW** nếu các điều kiện về zone, lịch, NAT và identity đều tương ứng. Rule 20 bị che hoàn toàn trong mô hình này. Nếu chỉ **một phần** tập lưu lượng của rule phía sau bị bao phủ, đó là **partial shadowing**.

### 3.4. Redundant: dư thừa về hiệu lực

Một rule là ứng viên dư thừa khi xóa nó **không thay đổi quyết định cho phép/từ chối** đối với tập lưu lượng được xét. Ví dụ một explicit DENY cụ thể có thể dư thừa so với default deny. Tuy nhiên, vẫn có thể cần rule cụ thể để **ghi log, biểu đạt yêu cầu kiểm toán hoặc tạo hàng rào trước thay đổi**. Vì vậy, tương đương về ALLOW/DENY chưa đủ nếu rule có các tác dụng khác.

### 3.5. Stale/orphaned: cũ hoặc thiếu người sở hữu

Rule cho đối tác đã kết thúc hợp đồng, IP máy chủ đã di chuyển, dự án thử nghiệm đóng, ngoại lệ bảo trì quá hạn hoặc rule không còn chủ sở hữu. **Không thấy lượt truy cập trong 30 ngày không chứng minh rule không còn cần**: failover, sao lưu, tác vụ cuối quý hay ứng cứu khẩn cấp có thể hiếm xảy ra. Cần kiểm chứng bằng dữ liệu nghiệp vụ và thời gian quan sát phù hợp.

### 3.6. Overly permissive: cấp quyền quá rộng

Ví dụ đáng quan tâm là **Internet → quản trị nội bộ**, **guest Wi-Fi → DATA**, **VPN → toàn bộ subnet**, **APP → Internet ANY**, hoặc mở mọi port trong khi chỉ cần một dịch vụ. Một rule `source=any` dành cho reverse proxy công khai có thể là thiết kế hợp lệ; đánh giá cần dựa vào **đích, chức năng, biện pháp bổ sung và yêu cầu nghiệp vụ** thay vì gắn cờ bất cứ rule nào có chữ ANY.

| Hiện tượng | Rủi ro chính | Cách xác minh |
|---|---|---|
| Duplicate | Khó bảo trì, metadata rời rạc | So sánh tất cả điều kiện và tác động |
| Overlap | Quyền hiệu lực khó dự đoán | So sánh tập nguồn, đích, service, zone và ưu tiên |
| Shadowed | Rule chặn có thể vô hiệu | Mô phỏng thứ tự và kiểm thử kết nối thực tế |
| Redundant | Tăng độ phức tạp không cần thiết | Kiểm tra thay đổi hành vi khi bỏ rule, cả log |
| Stale | Quyền tồn tại sau khi hết nhu cầu | Đối chiếu owner, ticket, lịch batch/DR và log |
| Overly permissive | Phơi lộ rộng, lateral movement | So với ma trận nghiệp vụ và tài sản cần bảo vệ |

## 4. Nguyên nhân khiến rulebase ngày càng phình to

Rule sprawl hiếm khi xuất hiện chỉ sau một thay đổi. Nó thường tích lũy từ hàng trăm quyết định nhỏ:

1. **Mở tạm rồi quên đóng:** trong sự cố, đội vận hành cho phép cả subnet, nhưng không ghi thời hạn hoặc người chịu trách nhiệm.
2. **Quy trình chỉ có chiều cấp quyền:** có ticket mở port khi triển khai, không có bước thu hồi khi ứng dụng ngừng sử dụng.
3. **Sao chép cấu hình không đối chiếu:** rule từ staging sang production có địa chỉ hoặc tài nguyên không phù hợp.
4. **Thay đổi địa chỉ và nền tảng:** chuyển server lên cloud, thay load balancer hoặc đổi tên service nhưng vẫn giữ IP/nhóm cũ.
5. **Thiếu danh mục tài sản:** không rõ rule phục vụ dịch vụ nào, nên không ai dám xóa.
6. **Nhóm object thiếu quản trị:** nhiều address group giống nhau hoặc một group dùng chung chứa quá nhiều tài sản.
7. **Nhiều điểm kiểm soát:** firewall vật lý, cloud SG, NACL, host firewall và Kubernetes NetworkPolicy cùng quản lý lưu lượng, nhưng không có bản đồ hiệu lực thống nhất.
8. **Đo lường sai mục tiêu:** chỉ ghi nhận “ứng dụng kết nối được”, không kiểm tra các đường bị cấm.
9. **Không theo dõi phiên bản và review:** không có diff, owner, expiry hay positive/negative test trước khi deploy.

Một quy trình tốt cần quản lý **toàn bộ vòng đời** từ yêu cầu → phê duyệt → triển khai → kiểm chứng → rà soát → thu hồi.

## 5. Hệ quả bảo mật, vận hành và kiểm toán

### 5.1. Rủi ro đối với tài sản

Nếu máy nhân viên bị chiếm quyền và mạng USER được phép vào DATA qua nhiều port, attacker có thể sử dụng những kết nối này để tìm thêm tài sản. Nếu tài khoản VPN của đối tác có quyền truy cập cả mạng quản trị, việc lộ tài khoản có thể lan rộng phạm vi ảnh hưởng. **Segmentation và default deny** chỉ có tác dụng khi các ngoại lệ không âm thầm mở lại các đường đã dự định đóng.

Trong threat modeling, phải xem xét **tài sản mục tiêu**, **mức tin cậy của nguồn**, **khả năng lạm dụng đường truy cập**, **phụ thuộc** và **khả năng phát hiện/phục hồi**. Một rule ở DNS/IdP quan trọng có thể cần giữ dù ít lưu lượng; một rule quản trị từ Internet có thể cần xem xét khẩn cấp dù chỉ có một mục trong bảng.

### 5.2. Rủi ro vận hành

- Việc đọc policy và tìm nguyên nhân một luồng được phép trở nên chậm và dễ sai.
- Một rule mới có thể vô tình bao phủ rule chặn cũ hoặc cho phép nhiều đối tượng hơn dự kiến.
- Xóa rule thiếu kiểm chứng có thể làm hỏng backup, DR, logging, DNS, xác thực hoặc ứng dụng nghiệp vụ.
- Thao tác thay đổi, review, audit và phản ứng sự cố tốn thời gian vì thiếu chủ sở hữu và chứng cứ.
- Một tập policy rất phức tạp **có thể** ảnh hưởng tài nguyên, thời gian commit hoặc cách thiết bị tối ưu hóa, tùy nền tảng; không có quy luật “cứ thêm rule là throughput tự động giảm”.

### 5.3. Ảnh hưởng đến khả năng giám sát

IDS/IPS và SIEM có thể thấy lưu lượng bất thường nhưng không tự trả lời được **lý do firewall cho phép kết nối**. Nếu không có rule ID trong log, không biết IP trước/sau NAT và thiếu phiên bản policy, điều tra sẽ khó liên hệ gói tin với quyết định cấp quyền. Ngược lại, ghi mọi gói deny không giới hạn có thể gây quá tải log: nên chọn dữ liệu quan trọng, counters và chính sách lưu giữ phù hợp.

## 6. Case study: rule cho phép rộng che rule chặn

### 6.1. Mạng giả định

| Zone | Dải địa chỉ / IP giả định | Mục đích |
|---|---|---|
| USER | 10.10.0.0/16 | Máy trạm nhân viên |
| GUEST | 10.10.50.0/24 | Thiết bị khách, nằm trong dải USER về mặt IP |
| APP | 10.20.10.0/24 | Ứng dụng nghiệp vụ |
| DATA | 10.30.0.0/16; DB = 10.30.10.15 | Cơ sở dữ liệu nhạy cảm |
| MGMT | 10.40.0.0/24; bastion = 10.40.0.10 | Truy cập quản trị |
| VENDOR | 198.51.100.0/24 | Đối tác hỗ trợ trong mô hình giả định |

Yêu cầu nghiệp vụ: chỉ APP gọi **DB TCP/5432**; USER và GUEST không vào DB trực tiếp. Đối tác chỉ truy cập bastion khi có phê duyệt và đúng điều kiện danh tính.

~~~mermaid
flowchart LR
    U["USER / GUEST"] -. "Cần DENY tới DATA" .-> DB["DATA: Database"]
    A["APP: API"] -->|"ALLOW TCP/5432"| DB
    V["VENDOR"] -. "Quyền tạm cần kiểm chứng" .-> B["MGMT: Bastion"]
~~~

### 6.2. Rulebase đang có

~~~text
# Pseudocode - firewall FIRST MATCH, từ trên xuống.
# Không phải cấu hình chạy trực tiếp trên thiết bị.

ID  ACTION  SOURCE             DESTINATION        SERVICE     MỤC ĐÍCH
10  ALLOW   10.10.0.0/16       10.30.0.0/16       ANY         Mở tạm từ năm trước
20  DENY    10.10.50.0/24      10.30.10.15        TCP/5432    Chặn GUEST đến DB
30  ALLOW   10.20.10.0/24      10.30.10.15        TCP/5432    APP kết nối DB
35  ALLOW   10.20.10.0/24      10.30.10.15        TCP/5432    Bản sao từ ticket khác
40  ALLOW   198.51.100.0/24   10.40.0.10         TCP/22      VENDOR bảo trì
99  DENY    ANY                ANY                ANY         Chặn còn lại
~~~

**Phân tích:**

1. Rule **10** cho USER truy cập toàn bộ DATA với bất kỳ service nào, vượt quá yêu cầu.
2. Rule **20** bị che vì source GUEST là tập con của USER, đích DB là tập con DATA và TCP/5432 nằm trong ANY. Với first match và các điều kiện còn lại tương ứng, GUEST → DB **khớp rule 10 trước và được cho phép**.
3. Rule **35** có thể là duplicate/shadow của rule 30 nếu các thuộc tính khác (zone, identity, log, lịch, security profile) cũng tương đương.
4. Rule **40** có dấu hiệu stale vì mô tả dự án cũ, nhưng phải hỏi owner, xác minh hợp đồng và lịch bảo trì trước khi thu hồi.
5. Rule **99** không cứu được rulebase nếu luồng đã được một rule rộng phía trên cho phép.

Điều này minh họa vì sao **thấy DENY trong cấu hình không đủ chứng minh đường đi bị chặn**.

### 6.3. Tập quyền mục tiêu sau khi rà soát

~~~text
# Minh họa mục tiêu, chưa phải đề xuất áp dụng ngay vào production.

ALLOW  APP -> DB TCP/5432
ALLOW  từng phụ thuộc hợp lệ: DNS, IdP, telemetry, backup, quản trị được duyệt
DENY   USER/GUEST -> DATA (explicit rule khi cần log riêng)
DENY   mọi kết nối NEW không được phép còn lại theo chính sách
~~~

Các bước cần thực hiện:

- Xác nhận không còn luồng hợp lệ lệ thuộc rule 10, rồi **thu hẹp hoặc thu hồi quyền rộng**.
- Hợp nhất rule 30/35 chỉ khi xác minh đầy đủ mọi điều kiện và yêu cầu logging.
- Xác minh owner và ngày hết hạn của rule 40; nếu không còn nhu cầu, thu hồi qua quy trình thay đổi.
- Test APP → DB (ALLOW), USER → DB (DENY), GUEST → DB (DENY), cùng các phụ thuộc nghiệp vụ.
- Ghi lại trạng thái kết nối mới và cũ, NAT, IPv4/IPv6 và đường đi thực tế.

## 7. Khác biệt giữa các mô hình firewall

Không được dùng cùng một thuật toán “rule trên che rule dưới” cho mọi nền tảng.

| Nền tảng | Hành vi điển hình | Hướng phân tích rule sprawl |
|---|---|---|
| Firewall **first match** | Rule đầu tiên khớp quyết định hành động | Phân tích thứ tự, shadowing đầy đủ/một phần |
| **AWS Security Group** | Chỉ gồm rule ALLOW, stateful; quyền từ nhiều SG gắn cùng tài nguyên được hợp | Tìm allow rộng và chồng lấn; không dùng khái niệm explicit deny phía sau |
| **AWS Network ACL** | ALLOW/DENY theo thứ tự, stateless | Xem thứ tự và rule chiều phản hồi với ephemeral port |
| **Azure NSG** | ALLOW/DENY theo priority và các default rules; stateful | Xem effective rules tại subnet/NIC, direction và priority |
| **Kubernetes NetworkPolicy** | Quyền ALLOW từ nhiều policy chọn pod cộng gộp khi CNI hỗ trợ; isolation theo ingress/egress | Xem toàn bộ selector, chiều và policy chọn workload; tên “deny” không tạo độ ưu tiên chặn |
| **nftables/iptables** | Tùy chain, hook, jump, priority, rule và state | Cần phân tích đường đi qua các chain và bảng liên quan |
| Firewall có **identity/app/time conditions** | Có điều kiện ngoài IP, port | Tránh gắn nhãn duplicate chỉ vì IP/port giống nhau |

Một firewall thật có thể thực thi policy trước hoặc sau các giai đoạn NAT/routing tùy thiết bị. Nền tảng cũng có thể dùng đối tượng FQDN, nhóm địa chỉ động, nhiều zones và tầng kiểm tra ứng dụng. Công cụ phát hiện chồng lấn phải hiểu **cấu hình hiệu lực** của đúng nền tảng.

## 8. Chỉ số giúp nhận diện sprawl

### 8.1. Nhóm chỉ số quản trị

| Chỉ số | Cách tính / ghi nhận | Giới hạn |
|---|---|---|
| Số rule đang bật | Đếm rule hiệu lực theo policy/thiết bị và môi trường | Mạng phức tạp có thể cần nhiều rule hợp lệ |
| Rule thiếu owner | Rule không có đơn vị chịu trách nhiệm | Thiếu owner chưa chứng minh rule vô dụng |
| Rule thiếu mục đích/ticket | Không có lý do nghiệp vụ hoặc bằng chứng phê duyệt | Có thể do dữ liệu CMDB chưa cập nhật |
| Rule quá hạn | Ngoại lệ tạm quá hạn xem xét | Cần xác minh trước khi xóa |
| Duplicate / overlap / shadow | Phân tích tập điều kiện theo nền tảng | Có thể phụ thuộc group động, NAT, thời gian và thứ tự |
| Rule quá rộng | Quyền vượt ma trận lưu lượng đã duyệt | Cần xét trường hợp dịch vụ công khai hợp lệ |
| Rule ít hit | Thống kê hit và last-hit theo khoảng quan sát | Có thể reset counter, log sampling, tác vụ hiếm |
| Tỷ lệ test PASS | Positive/negative test theo ma trận | Không có ý nghĩa nếu bỏ sót luồng nhạy cảm |
| Thời gian xử lý thay đổi | Từ yêu cầu đến triển khai và xác minh | Không tối ưu tốc độ bằng cách bỏ review |

**Ví dụ định lượng:** tổng có 240 rule đang bật, 36 rule chưa rõ owner:

~~~text
Tỷ lệ thiếu owner = 36 / 240 × 100 = 15%
Tỷ lệ có owner    = 204 / 240 × 100 = 85%
~~~

Chỉ số 15% cho thấy tồn tại **khoảng trống trách nhiệm quản trị**, không có nghĩa 15% rule chắc chắn nguy hiểm hoặc chắc chắn có thể xóa. Để ưu tiên, cần xét nội dung và mức độ ảnh hưởng tới tài sản.

### 8.2. Vì sao hit count không đủ?

**0 hit trong 30 ngày** chỉ là tín hiệu để điều tra. Một số kết nối diễn ra khi chạy DR, backup cuối tháng/quý, failover hoặc hoạt động khẩn cấp. Counter có thể bị reset khi commit/failover, log có thể chỉ lấy mẫu, rule bị shadow khiến counter bằng 0 và kết nối stateful đang có thể không được ghi nhận giống kết nối NEW.

Chỉ đưa rule vào danh sách **ứng viên rà soát** dựa trên số lượt truy cập, rồi kiểm tra nhu cầu với owner, chu kỳ công việc, cấu hình hiệu lực và các điểm đo bổ sung. Không dùng một lần timeout hoặc counters bằng 0 làm bằng chứng thu hồi an toàn.

## 9. Phương pháp rà soát rulebase từng bước

### Bước 1 — Chốt phạm vi và phiên bản chính sách

Xác định firewall, cloud account, VPC/VNet, phân đoạn, policy package, môi trường và thời điểm lấy dữ liệu. Đánh dấu rule đang bật/tắt, các policy gắn tài sản, thay đổi chưa commit, các nhóm địa chỉ và rule theo danh tính. Tài liệu thiết kế và topology là cơ sở nhưng phải so với **running/effective configuration**.

### Bước 2 — Thu thập rule cùng object và đường đi

Xuất cấu hình có **ID, thứ tự, source, destination, service, action, zone, NAT, identity, log, hit count**, rồi nối với CMDB/IPAM, firewall logs, flow logs, change tickets và thông tin chủ hệ thống. Nếu chỉ có một bảng rule nhưng không biết một object chứa những địa chỉ nào, việc tìm overlap sẽ không đáng tin.

### Bước 3 — Chuẩn hóa trước khi so sánh

Đối chiếu dải IP/subnet, IPv4/IPv6, port range, service alias, schedule, object group và các lớp điều kiện. Phân biệt:

- Hai rule hoàn toàn giống nhau.
- Một rule là tập con của rule khác.
- Hai rule giao nhau một phần.
- Hai rule không giao nhau.
- Hai rule chỉ có vẻ giống nhưng thuộc zone/policy layer khác nhau.

**Lưu ý:** việc giải tham chiếu nhóm động chỉ đúng cho trạng thái hiện tại; thành viên nhóm có thể thay đổi sau đó. Cần ghi phiên bản/nguồn object để theo dõi mở rộng quyền về sau.

### Bước 4 — Phân loại ứng viên

Đánh nhãn **duplicate, shadowed, overlap, stale, overly permissive, orphaned** kèm bằng chứng. Quy tắc không khớp log có thể cần điều tra thêm thay vì kết luận thừa. Những rule ảnh hưởng DATA/MGMT hoặc mở từ Internet/guest/đối tác thường cần ưu tiên đánh giá tác động.

### Bước 5 — Xác nhận với chủ sở hữu

Mỗi rule phải trả lời được **ai cần, cần để làm gì, dùng ở đâu, vào thời điểm nào, với quyền gì**. Nếu chủ sở hữu không rõ, tìm từ change history, chủ ứng dụng, cấu hình IaC và nhà cung cấp. Với luồng hiếm, cân nhắc kế hoạch kiểm tra vào thời điểm phù hợp.

### Bước 6 — Xây policy mục tiêu và đánh giá thay đổi

Thiết kế quyền **theo cặp ứng dụng/tài nguyên**, giảm ANY, giữ đúng DNS, IdP, VPN, logging, backup và đường quản trị. Đánh giá hai loại rủi ro: **giữ quyền thừa** và **xóa nhầm quyền đang dùng**. Chuẩn bị kế hoạch khôi phục và người phê duyệt thay đổi.

### Bước 7 — Thử nghiệm, áp dụng và xác minh

Đo **positive tests** (luồng hợp lệ) và **negative tests** (luồng phải bị chặn) ở đúng nguồn/đích, có log/capture tại điểm thực thi. Thực hiện rollout phạm vi nhỏ, đối chiếu chỉ số ứng dụng và theo dõi sau thay đổi. Cập nhật inventory, ticket, phiên bản policy, owner và kỳ rà soát.

~~~mermaid
flowchart TD
    A["Lấy policy + object + NAT/zone"] --> B["Chuẩn hóa tập điều kiện"]
    B --> C["Phát hiện duplicate, overlap, shadow"]
    C --> D["Liên kết owner, logs, mục đích"]
    D --> E["Đánh giá rủi ro và phụ thuộc"]
    E --> F{"Đủ bằng chứng thay đổi?"}
    F -- "Chưa" --> G["Bổ sung dữ liệu và xác nhận owner"]
    G --> E
    F -- "Có" --> H["Thiết kế policy mục tiêu + rollback"]
    H --> I["Test allow/deny và triển khai từng phần"]
    I --> J["Regression test, giám sát, cập nhật hồ sơ"]
~~~

## 10. Mẫu bản ghi một rule có thể kiểm toán

~~~yaml
rule_id: FW-APP-014
environment: production
enforcement_point: internal-segmentation-firewall
direction: APP-to-DATA
source: app-services
destination: orders-db
protocol: TCP
destination_port: 5432
action: ALLOW
business_purpose: orders-api accesses orders-db
owner: application-platform-team
change_reference: CHG-EXAMPLE-014
temporary_exception: false
review_due: "2027-02-28"
validation:
  positive_test: APP-to-DB-TCP-5432
  negative_test: USER-to-DB-TCP-5432
  result: pending
~~~

Đây là **mẫu minh họa**, không phải quy tắc đã cấu hình trong môi trường thật. Có thể bổ sung thời gian áp dụng, user group, application ID, object version, NAT context, kết quả kiểm thử và liên kết rule ID với audit logs. Tránh lưu mật khẩu hoặc bí mật vào metadata.

## 11. Thu gọn rule mà không gây gián đoạn

### 11.1. Đánh giá đồng thời hai loại rủi ro

**Rủi ro nếu giữ rule** tăng theo độ nhạy của đích, mức phơi lộ nguồn, phạm vi quyền, khả năng bị lạm dụng và thiếu giám sát. **Rủi ro nếu xóa rule** phụ thuộc tác vụ đang dùng, đường DR/backup, quản trị dự phòng, thay đổi NAT/route và chính sách kết nối đã thiết lập.

| Ứng viên | Rủi ro giữ | Rủi ro sửa/xóa | Hành động hợp lý |
|---|---|---|---|
| Internet → cổng quản trị rộng ngoài dự kiến | Rất cao | Có thể cao nếu kênh vận hành đang dùng | Xác nhận khẩn, xây đường quản trị phù hợp rồi thu hẹp |
| Rule APP → DB bị trùng điều kiện nhưng khác log | Thấp/trung bình | Thấp/trung bình | So sánh logging và hiệu lực trước khi hợp nhất |
| Rule backup không hit 30 ngày | Chưa rõ | Có thể cao khi cần khôi phục | Xác nhận lịch, owner và thử DR đúng quy trình |
| Rule đối tác quá hạn | Có thể cao | Phải xác minh tác vụ đang mở | Tra hợp đồng và owner, thu hồi khi đủ bằng chứng |
| Rule DNS tới resolver được duyệt | Có nhu cầu rõ | Cao nếu xóa nhầm | Giữ quyền tối thiểu, không gộp thành ANY |

### 11.2. Kiểm thử cả ALLOW và DENY

Ví dụ sau khi thu hồi quyền USER → DATA:

| Test ID | Nguồn → Đích | Kỳ vọng | Bằng chứng tối thiểu |
|---|---|---|---|
| ALLOW-01 | APP → DB TCP/5432 | Kết nối thành công | TCP connect, ứng dụng hoạt động, log allow tương ứng |
| DENY-01 | USER → DB TCP/5432 | Chặn ở ranh giới | Firewall deny/counter khớp 5-tuple, không có session |
| DENY-02 | GUEST → DB TCP/5432 | Chặn ở ranh giới | Log policy và nguồn thuộc đúng GUEST zone |
| DENY-03 | WEB → DB TCP/5432 | Chặn kết nối trực tiếp | Xác minh đường đúng và log/capture liên quan |
| ALLOW-02 | APP → resolver UDP/TCP 53 | DNS hoạt động | Truy vấn đến đúng resolver với phản hồi phù hợp |

**Timeout không tự động chứng minh DENY.** Đích có thể tắt, route lỗi hoặc firewall nằm ngoài đường đi. Cần **positive control** từ nguồn được phép và log/capture tại đúng điểm kiểm soát. Ngược lại, HTTP 403 sau TCP/TLS thành công có thể chứng minh ứng dụng từ chối quyền, **không phải** bằng chứng phân đoạn mạng đã chặn.

### 11.3. Phiên cũ và chiều phản hồi

Firewall stateful có thể giữ các phiên đã thiết lập trước khi rule đổi, tùy thiết bị và cấu hình. Kiểm tra bằng **kết nối NEW** sau thay đổi và quan sát state table khi cần. Không xóa conntrack trên production chỉ để chứng minh rule mới.

Với ACL stateless, cần xét **cả chiều đi và chiều về**, đặc biệt các cổng nguồn động (ephemeral ports). NAT và định tuyến bất đối xứng có thể làm rule trông hợp lệ nhưng kết nối không hoạt động. Tất cả những yếu tố này cần đưa vào regression test.

### 11.4. Rollback và vận hành

Lưu phiên bản policy trước thay đổi, xác minh đường truy cập quản trị, thống nhất cửa sổ thay đổi và người phụ trách. Triển khai theo nhóm rule có phạm vi vừa đủ quan sát. Theo dõi **DNS, IdP, VPN, health check, log, ứng dụng, backup** và truy cập của đối tác. Nếu phát hiện tác động ngoài dự kiến, sử dụng kế hoạch rollback đã chuẩn bị rồi phân tích nguyên nhân trước khi áp dụng lại.

## 12. Ngăn rule sprawl tái diễn

### 12.1. Chuẩn hóa yêu cầu mở rule

Mỗi yêu cầu cần mô tả **source, destination, giao thức/cổng, chiều, zone, môi trường, mục đích, owner, thời hạn, người phê duyệt, test cases và kế hoạch thu hồi**. Không duyệt một yêu cầu chỉ ghi “mở port cho app” mà thiếu nguồn/đích và ranh giới.

### 12.2. Ưu tiên phân đoạn theo ứng dụng và danh tính

Thay vì cho toàn subnet đến một vùng, mô tả **ứng dụng nào cần gọi dịch vụ nào**. Nhóm object, tag hoặc service identity có thể giảm nhu cầu sửa IP thủ công, nhưng chính bản thân nhóm cũng phải có owner và kiểm soát thành viên. Một nhóm quá lớn dùng chung cho mọi ứng dụng có thể làm quyền hiệu lực ngày càng rộng.

### 12.3. Quản lý rule tạm thời

Rule bảo trì, truy cập nhà thầu hoặc ứng cứu cần có **hạn hết hiệu lực, nhắc rà soát và người có quyền gia hạn**. Khi hết hạn, kiểm tra đang có tác vụ nào sử dụng rồi thu hồi có kiểm soát. Giữ lịch sử để lần sau không lặp lại cùng một ngoại lệ quá rộng.

### 12.4. Policy as code và kiểm tra tự động

Nếu nền tảng hỗ trợ IaC/Policy as Code, có thể review thay đổi qua version control và chạy kiểm tra đối với:

- Rule không có owner, purpose, expiration hoặc ticket.
- Rule mới mở rộng ANY, CIDR hoặc service vào vùng DATA/MGMT.
- Rule trùng lặp hoặc chồng lấn rõ ràng.
- Rule thay đổi group dùng chung hoặc tham chiếu đối tượng không còn tồn tại.
- Policy bỏ sót IPv6, egress hoặc luồng bắt buộc theo ma trận.

**Không tự động xóa rule chỉ vì linter báo redundant.** Công cụ có thể chưa mô hình hóa đúng NAT, time schedule, identity, connection state, FQDN động hoặc yêu cầu log. Vẫn cần owner review và kiểm thử đường mạng thực tế.

### 12.5. Lịch rà soát theo mức rủi ro

Ngoại lệ tạm và quyền truy cập từ bên ngoài cần rà soát sớm, rule ảnh hưởng tài sản nhạy cảm phải có tiêu chí xác minh chặt chẽ, còn các rule nền ổn định có thể rà soát theo chu kỳ thích hợp. Lịch cụ thể tùy tổ chức; quan trọng hơn là **khi ứng dụng thay đổi, giải thể, chuyển môi trường hoặc hợp đồng kết thúc, quy trình cũng phải thu hồi quyền**.

## 13. Công cụ và bằng chứng hỗ trợ rà soát

| Nguồn bằng chứng | Cho biết điều gì | Giới hạn |
|---|---|---|
| Running config / policy export | Rule đang bật, thứ tự, nhóm object, NAT, zone | Có thể không chứa điểm thực thi khác trên tuyến |
| Hit counter / last hit | Rule có khớp traffic trong thời gian quan sát không | Counter reset, dữ liệu hiếm, log sampling |
| Firewall allow/deny logs | Gói/phiên nào khớp rule nào, thời điểm nào | Có thể chỉ ghi một phần hoặc thiếu NAT context |
| NetFlow/IPFIX/VPC flow logs | Luồng thực tế giữa các địa chỉ | Không tự chứng minh quyền hợp lệ ở tầng ứng dụng |
| DNS, IdP, VPN, application logs | Phụ thuộc, tài khoản và hành vi nghiệp vụ | Phải khớp thời gian, định danh và địa chỉ dịch NAT |
| CMDB, ticket, IaC history | Owner, mục đích và thay đổi đã duyệt | Có thể cũ hoặc thiếu thông tin |
| Positive/negative connectivity tests | Đường được phép hoạt động và đường cấm bị chặn không | Phản ánh tuyến, bối cảnh và thời điểm đã test |

### 13.1. Lệnh chỉ đọc trên Linux (nếu đang quản trị host phù hợp)

~~~bash
# Đọc cấu hình nftables đang áp dụng trên host
sudo nft list ruleset

# Nếu hệ thống dùng iptables tương thích hoặc legacy
sudo iptables -S

# Xem rule IPv6 khi dùng ip6tables
sudo ip6tables -S

# Xem đường đi theo routing table đến DB giả định
ip route get 10.30.10.15

# Quan sát kết nối TCP hiện tại
ss -tn
~~~

Các lệnh này giúp **thu thập trạng thái**, không tự phát hiện chính xác shadowing. Nhiều hệ thống dùng chain/hook, eBPF, NAT và thiết bị trung gian, nên chỉ đọc một bảng lệnh không thể chứng minh toàn bộ đường đi đã an toàn.

### 13.2. Mẫu log để truy vết rule gây mở quyền

~~~text
# Bản ghi mô phỏng, không phải dữ liệu vận hành thật
time=2026-11-28T04:00:00Z
rule=FW-LEGACY-010
src=10.10.50.21:51920
dst=10.30.10.15:5432
proto=tcp
action=allow
source_zone=USER
destination_zone=DATA

Nhận định cần xác minh:
- Đây có phải phiên mới, và có NAT hay thay đổi địa chỉ không?
- Rule 10 có mở rộng hơn ma trận lưu lượng được duyệt không?
- Rule DENY cụ thể có bị rule trước che khuất không?
- Có đường đi khác mà chính sách cần bao phủ không?
~~~

Mỗi bằng chứng nên ghi **timestamp, rule ID, policy version, nguồn/đích/port/protocol, zone, chiều, NAT, session state** và người thực hiện kiểm thử. Tránh dùng log đơn lẻ để kết luận một rule không còn cần thiết.

## 14. Rule sprawl trên cloud, Kubernetes, VPN và mạng không dây

### 14.1. Security group và nhóm tài nguyên cloud

Một group được gắn cho nhiều workload có thể khiến thay đổi một rule ảnh hưởng tất cả thành viên. Nhiều security group gắn chung một tài nguyên cũng có thể làm quyền allow được hợp nhất. Vì vậy, giảm số lượng group chưa chắc tốt nếu tạo ra nhóm “dùng chung mọi thứ”. Cần tổ chức group theo vai trò, theo dõi thành viên và xem quyền hiệu lực ở **đúng workload**.

### 14.2. Kubernetes NetworkPolicy

NetworkPolicy chọn pod theo label/namespace và khai báo những traffic được phép. Nếu nhiều policy chọn cùng pod, các quyền allow thường cộng gộp. Một policy tên `default-deny` không phủ định được một rule allow khác. Nếu CNI không hỗ trợ NetworkPolicy, việc tạo tài nguyên không chứng minh traffic bị chặn.

Lệnh chỉ đọc để rà soát ban đầu:

~~~bash
kubectl get networkpolicy -A
kubectl get pods -n orders --show-labels
kubectl describe networkpolicy -n orders
~~~

Cần xác minh cả ingress và egress, label động, service/ClusterIP, CNI dataplane, luồng qua mesh hoặc load balancer. Không chuyển thuật toán rule first-match của firewall truyền thống sang NetworkPolicy.

### 14.3. VPN và Wi-Fi

Sau khi người dùng xác thực VPN, chính sách vẫn nên giới hạn **chỉ các ứng dụng cần thiết**. Một rule “mọi nhóm VPN → toàn bộ intranet” có thể tạo quyền thừa. Tương tự, Wi-Fi khách/BYOD phải được phân đoạn khỏi mạng quản trị hoặc DATA phù hợp với yêu cầu; không gộp guest và staff vào cùng object nhóm chỉ để giảm số rule.

### 14.4. IPv6, DNS và giao thức hỗ trợ

Nếu kiểm kê chỉ tập trung IPv4, quyền IPv6 có thể bị bỏ quên. DNS cần cả UDP/TCP 53 trong các trường hợp phù hợp; QUIC dùng UDP/443; ICMPv4 Fragmentation Needed và ICMPv6 Packet Too Big quan trọng cho PMTUD, còn IPv6 Neighbor Discovery cần xử lý đúng vai trò. Khi thu gọn policy, đừng xóa các kết nối nền cần thiết chỉ vì chúng không phải traffic của ứng dụng chính.

## 15. Ví dụ quy trình quản trị hoàn chỉnh

Giả sử một doanh nghiệp nhận thấy có nhiều rule cũ giữa các vùng USER, APP và DATA. Đội bảo mật muốn cải thiện chính sách trước khi triển khai thêm microsegmentation.

**Giai đoạn 1 — Hiểu hiện trạng.** Xuất rulebase và object groups, xác định tuyến gói, NAT, policy hiện hành và owner. Liên hệ log/counters với CMDB và ma trận kết nối. Ghi lại rule thiếu thông tin thay vì tự điền owner theo suy đoán.

**Giai đoạn 2 — Chọn nhóm ứng viên.** Ưu tiên rule từ nguồn ít tin cậy đến DATA/MGMT, ngoại lệ tạm đã quá hạn và những rule first-match đang che quyết định chặn. Rule zero-hit nằm trong danh sách cần điều tra, không bị xóa hàng loạt.

**Giai đoạn 3 — Mô hình hóa policy mục tiêu.** Chỉ giữ APP → DB theo giao thức cần thiết; tách quyền bastion, VPN, DNS, IdP và các dịch vụ nền; chuyển quyền rộng thành ngoại lệ có mục đích và chủ sở hữu.

**Giai đoạn 4 — Xác minh.** Trước khi thay đổi, đo đường API → DB; USER → DB; GUEST → DB; dịch vụ DNS, log, backup. Sau khi deploy, lặp lại positive/negative tests, đối chiếu rule ID và thông số vận hành, xác định được điều kiện PASS/FAIL/INCONCLUSIVE.

**Giai đoạn 5 — Duy trì.** Đính kèm kết quả vào change ticket, lưu diff và rollback plan, đặt hạn rà soát rule tạm, tích hợp review/policy checks vào quy trình tạo dịch vụ mới và ngừng sử dụng.

~~~text
# Biên bản ví dụ, tất cả dữ liệu đều giả định
Change: CHG-EXAMPLE-014
Scope: USER / APP / DATA
Candidate:
  - Legacy ALLOW USER -> DATA ANY
  - Duplicate APP -> DB TCP/5432
  - Expired VENDOR -> bastion TCP/22
Expected:
  APP -> DB TCP/5432       ALLOW
  USER -> DB TCP/5432      DENY
  GUEST -> DB TCP/5432     DENY
Evidence required:
  - Approved flow matrix and owner confirmation
  - Rulebase diff and effective configuration
  - Connection tests, deny logs, application health
  - Rollback plan and regression evidence
Status: PROPOSED, pending validation
~~~

## 16. Những nhầm lẫn thường gặp

| Nhận định sai | Giải thích đúng |
|---|---|
| “Ít rule hơn chắc chắn an toàn hơn.” | Quyền hiệu lực và khả năng kiểm chứng mới là tiêu chí chính. |
| “Rule có hit count bằng 0 thì được phép xóa.” | Cần xem lịch DR/backup, owner, thời gian đo và reset counters. |
| “Đã viết rule DENY tức traffic bị chặn.” | ALLOW trước đó có thể che DENY trên first-match firewall. |
| “Rule cùng IP/port là duplicate.” | Có thể khác zone, identity, schedule, NAT, log hoặc profile. |
| “Gộp mọi object thành một group lớn giúp an toàn.” | Group quá rộng có thể mở thêm quyền cho tất cả rule tham chiếu. |
| “Implicit deny đủ bảo vệ mọi đường.” | Quy tắc ALLOW phía trên và đường bypass vẫn phải được đánh giá. |
| “Cloud SG có deny priority như firewall truyền thống.” | AWS SG chỉ có allow rules; xem quyền được hợp từ các group. |
| “Không có log tức không có traffic.” | Log có thể chưa bật, bị sampling hoặc ở thiết bị khác. |
| “Phân tích tự động chính xác mọi trường hợp.” | NAT, identity, object động và đường truyền có thể làm sai kết luận. |
| “Xóa rule rồi test một lần là xong.” | Cần kiểm thử nhiều luồng, phiên mới, IPv6 và phụ thuộc ứng dụng. |

## 17. Bài tập vận dụng

**Bài 1 — Nhận diện shadowing.** Firewall first-match có:

~~~text
10 ALLOW 10.0.0.0/8   -> 10.30.0.0/16 TCP/443
20 DENY  10.10.0.0/16 -> 10.30.10.5  TCP/443
30 DENY  ANY          -> ANY         ANY
~~~

Máy `10.10.2.4` gọi `10.30.10.5:443` sẽ được xử lý bởi rule nào? **Đáp án:** rule 10, được ALLOW nếu các điều kiện khác tương đương, vì tập nguồn và đích của rule 20 nằm trong rule 10.

**Bài 2 — Duplicate hay không?** Hai rule giống IP/port, nhưng một rule chỉ áp dụng giờ bảo trì và một rule luôn hoạt động, với mức log khác. Có thể xóa một rule vì trùng không? **Gợi ý:** chưa; cần xét time schedule, logging, security profile, owner và thứ tự.

**Bài 3 — Đọc chỉ số.** Trong 300 rule có 45 rule không có chủ sở hữu. Tỷ lệ bao nhiêu? Kết luận gì? **Đáp án:** 15% thiếu owner. Đây là khoảng trống quản trị, chưa chứng minh chính xác bao nhiêu rule có thể xóa.

**Bài 4 — Zero hit.** Rule backup không có hit trong tháng qua. Hãy liệt kê các bằng chứng cần thu thập. **Gợi ý:** lịch backup/DR, chủ hệ thống, chu kỳ truy cập, giai đoạn đo, log nguồn/đích và kịch bản kiểm thử phù hợp.

**Bài 5 — AWS Security Group.** Một tài nguyên có hai SG, một SG cho phép chỉ từ APP và SG còn lại mở rộng từ toàn subnet USER. Kết quả effective allow có được giới hạn chỉ theo SG APP không? **Gợi ý:** không. Với AWS Security Group, các allow của các group gắn tài nguyên được hợp; phải thu hẹp quyền trong tất cả group liên quan.

**Bài 6 — Negative test.** Sau khi thu hồi rule, USER → DB bị timeout nhưng DB cũng đang dừng dịch vụ. Có thể ghi PASS chặn kết nối không? **Gợi ý:** chưa; cần positive control từ APP và log/capture xác nhận điểm kiểm soát deny, nếu thiếu dữ liệu thì INCONCLUSIVE.

**Bài 7 — Rule tạm.** Một đối tác cần VPN để bảo trì 14 ngày. Hãy thiết kế hồ sơ rule gồm người sở hữu, nguồn/đích, cổng, điều kiện danh tính, thời hạn, kiểm tra và bước thu hồi. **Gợi ý:** ghi rõ phạm vi truy cập tối thiểu, MFA/thiết bị nếu có, ticket, ngày hết hạn và kiểm thử allow/deny trước, trong và sau đợt bảo trì.

## 18. Checklist rà soát trước khi hoàn tất

- Đã biết **thiết bị thực thi, policy hiệu lực, zone, NAT, routing, thứ tự và identity**.
- Đã phân loại các ứng viên **duplicate, overlap, shadowed, stale, overly permissive** theo đúng ngữ nghĩa nền tảng.
- Rule cần thay đổi có **owner, mục đích, tình trạng phụ thuộc, bằng chứng và phê duyệt**.
- Không dùng **0 hit** hoặc **timeout** đơn lẻ để quyết định xóa rule hay công nhận DENY.
- Đã kiểm tra các phụ thuộc **DNS, VPN, IdP, backup, logging, DR, cloud, IPv4/IPv6**.
- Có **positive và negative tests** cho ranh giới quan trọng, kèm kết quả PASS/FAIL/INCONCLUSIVE.
- Có **phiên bản trước thay đổi, rollback, kênh quản trị an toàn** và người xử lý sự cố.
- Đã xác minh **kết nối NEW**, xem xét phiên stateful cũ và kiểm tra hồi quy.
- Rule còn lại có **ngày rà soát và chủ sở hữu** để hạn chế sprawl tái phát.

**Ghi nhớ:** rule sprawl là hậu quả của việc cấp quyền mà thiếu quản trị vòng đời. Phương pháp bền vững là **chỉ mở đúng đường được phép, ghi rõ chủ sở hữu và mục đích, kiểm tra hiệu lực trước/sau thay đổi và thu hồi khi nhu cầu kết thúc**. Rulebase có chất lượng khi người vận hành có thể giải thích và chứng minh quyền truy cập thực sự đang tồn tại.

### Tài liệu tham khảo

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): thiết kế, vận hành và bảo trì chính sách firewall.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): least privilege, kiểm soát thay đổi và giám sát.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát truy cập theo tài nguyên, danh tính và ngữ cảnh.
- [NIST SP 800-115 — Technical Guide to Information Security Testing and Assessment](https://csrc.nist.gov/pubs/sp/800/115/final): kiểm thử và đánh giá an toàn kỹ thuật.
- [AWS VPC — Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html): mô hình stateful và quyền từ nhiều security group.
- [AWS VPC — Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html): rule theo thứ tự và stateless.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): cô lập workload và quyền ALLOW cộng gộp.
- [Microsoft Learn — Azure Network Security Groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview): priority, default rules và chính sách hiệu lực.
